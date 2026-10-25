use std::sync::Mutex;

use base64::Engine;
use serde::Deserialize;
use tauri::{Emitter, Manager};

use crate::pinned_images::{main_only, PinState};

#[derive(Default)]
pub struct CaptureOverlayState {
    image: Option<Vec<u8>>,
    shown: bool,
    /// Bumped on every state transition (session start / end): the overlay page
    /// polls this because WebView2 event delivery to HIDDEN windows is unreliable
    /// (a missed "capture-image" once stalled a whole session).
    generation: u64,
    result: Option<CaptureResult>,
    result_generation: u64,
}

/// A confirmed capture handed back to the (hidden) main window. Transported via
/// Rust state + polling for the same reason: events to hidden pages cannot be
/// trusted. The IMAGE is never serialized into an event/argument — it travels
/// over the binary channel (a JSON array wedged the IPC once).
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CaptureResult {
    pub image: Vec<u8>,
    pub ocr_text: String,
    pub translation: String,
}

#[derive(Debug, Deserialize)]
pub struct DisplayRect {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

fn overlay_only(window: &tauri::WebviewWindow) -> Result<(), String> {
    if window.label() == "capture-overlay" {
        Ok(())
    } else {
        Err("capture overlay window required".into())
    }
}

/// Returns the overlay window, creating it (hidden) on first use. The window is
/// PRE-CREATED at app startup and REUSED for every capture: WebView2 cold start
/// and page boot would otherwise cost 1-3s per capture. transparent(true) so any
/// frame that slips out before the page paints shows the desktop through — never
/// white, never black.
fn ensure_window(app: &tauri::AppHandle) -> Result<tauri::WebviewWindow, String> {
    if let Some(existing) = app.get_webview_window("capture-overlay") {
        return Ok(existing);
    }
    let created = tauri::WebviewWindowBuilder::new(app, "capture-overlay", tauri::WebviewUrl::App("index.html#capture-overlay".into()))
        .title("MemoPaws Capture")
        .always_on_top(true)
        .decorations(false)
        .resizable(false)
        .maximizable(false)
        .minimizable(false)
        .skip_taskbar(true)
        .transparent(true)
        .visible(false)
        .build();
    created.map_err(|error| format!("capture overlay window creation failed: {error}"))
}

/// Startup hook: pre-create the hidden overlay window so the first capture is as
/// fast as every other one.
pub fn precreate(app: &tauri::AppHandle) {
    let _ = ensure_window(app);
}

/// Stores the screenshot and shows the overlay on the requested display. The
/// overlay is a REAL separate window (the WeChat / Quark / Windows-snipping
/// architecture): the main window stays hidden for the whole session and never
/// participates, so there is no fullscreen dance, no saved placement to restore,
/// and no main-UI flash is structurally possible.
#[tauri::command]
pub async fn capture_overlay_begin(
    window: tauri::WebviewWindow,
    png: Vec<u8>,
    display: Option<DisplayRect>,
) -> Result<(), String> {
    main_only(&window)?;
    let app = window.app_handle().clone();
    // Window creation MUST NOT run on the main thread: build() pumps the event
    // loop, so from a sync (main-thread) command it waits for itself — the exact
    // deadlock the smoke check caught. pin_image uses the same pattern.
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<Mutex<CaptureOverlayState>>();
        {
            let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
            if guard.shown {
                return Err("capture overlay is already open".into());
            }
            guard.image = Some(png);
            guard.shown = false;
            guard.generation += 1;
        }
        let overlay = ensure_window(&app)?;
        // A borderless window sized to the monitor bounds is fullscreen to the eye
        // WITHOUT tao's fullscreen flag — nothing saves or restores a placement.
        let position = display.as_ref().map(|rect| tauri::PhysicalPosition::new(rect.x, rect.y)).unwrap_or(tauri::PhysicalPosition::new(0, 0));
        let size = display.as_ref().map(|rect| tauri::PhysicalSize::new(rect.width, rect.height)).unwrap_or(tauri::PhysicalSize::new(800, 600));
        if let Err(error) = overlay.set_position(position).and_then(|_| overlay.set_size(size)) {
            let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
            guard.image = None;
            guard.generation += 1;
            return Err(format!("capture overlay window setup failed: {error}"));
        }
        // The page fetches the image (proactively on boot, or via this event for
        // reused windows), paints, then signals capture_overlay_ready — only then
        // does the window appear, so the user goes desktop -> complete overlay
        // with no white/black intermediate frames.
        let _ = app.emit_to("capture-overlay", "capture-image", {});
        let app_for_fallback = app.clone();
        std::thread::spawn(move || {
            // Generous: a cold page boot measured up to ~7.5s once (serialized
            // behind the main window's own boot).
            std::thread::sleep(std::time::Duration::from_millis(8000));
            let state = app_for_fallback.state::<Mutex<CaptureOverlayState>>();
            let should_recover = {
                let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
                let should = !guard.shown;
                if should {
                    guard.image = None;
                    guard.generation += 1;
                }
                should
            };
            if should_recover {
                // Not ready in 8s: the page is stuck (crashed webview). Cancel the
                // session instead of showing an overlay nobody can dismiss.
                if let Ok(show_main) = crate::pinned_images::finish_session(&app_for_fallback.state::<PinState>(), "cancel") {
                    if let Some(overlay) = app_for_fallback.get_webview_window("capture-overlay") {
                        let _ = overlay.hide();
                    }
                    if show_main {
                        if let Some(main) = app_for_fallback.get_webview_window("main") {
                            let _ = main.show();
                        }
                    }
                }
            }
        });
        Ok(())
    })
    .await
    .map_err(|error| format!("capture overlay task failed: {error}"))?
}

/// Hands the stored screenshot to the overlay page (binary channel).
#[tauri::command]
pub fn capture_overlay_image(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, Mutex<CaptureOverlayState>>,
) -> Result<tauri::ipc::Response, String> {
    overlay_only(&window)?;
    let image = state
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .image
        .clone()
        .ok_or_else(|| "no capture session image".to_string())?;
    Ok(tauri::ipc::Response::new(image))
}

/// The overlay page signals "fully painted": only NOW does the window appear, so
/// the user goes desktop -> complete overlay with no white/black intermediate
/// frames. A ready arriving with no live session (fallback already cancelled) is
/// ignored — an empty always-on-top overlay would swallow every click.
#[tauri::command]
pub fn capture_overlay_ready(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, Mutex<CaptureOverlayState>>,
) -> Result<(), String> {
    overlay_only(&window)?;
    let should_show = {
        let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        if guard.image.is_none() {
            return Ok(());
        }
        let should = !guard.shown;
        guard.shown = true;
        should
    };
    if should_show {
        window.show().map_err(|error| error.to_string())?;
    }
    Ok(())
}

/// Ends the session. This command does EVERYTHING synchronously: settle the
/// session, decode the confirmed result (base64 — the JSON-array form wedged the
/// IPC), hide the overlay, bump the generation, then reveal pin / restore main.
/// Doing it here instead of from the (now hidden) page is the difference between
/// "everything exits" and "stuck on screen".
#[tauri::command]
pub fn capture_overlay_end(
    window: tauri::WebviewWindow,
    outcome: String,
    reveal_pin: Option<String>,
    ocr_text: Option<String>,
    translation: Option<String>,
    image_base64: Option<String>,
    pins: tauri::State<'_, PinState>,
) -> Result<bool, String> {
    overlay_only(&window)?;
    let show_main = crate::pinned_images::finish_session(&pins, &outcome)?;
    let result = match (outcome.as_str(), image_base64) {
        ("confirm", Some(image_base64)) => Some(CaptureResult {
            image: base64::engine::general_purpose::STANDARD
                .decode(image_base64)
                .map_err(|error| format!("confirm image base64 decode failed: {error}"))?,
            ocr_text: ocr_text.unwrap_or_default(),
            translation: translation.unwrap_or_default(),
        }),
        _ => None,
    };
    let app = window.app_handle().clone();
    let _ = window.hide();
    {
        let state = app.state::<Mutex<CaptureOverlayState>>();
        let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        if outcome == "confirm" {
            guard.result = result;
            guard.result_generation += 1;
        }
        guard.image = None;
        guard.shown = false;
        guard.generation += 1;
    }
    // Tell the main page the session is over (fast path; it also polls status).
    let _ = app.emit("capture-ended", {});
    if show_main {
        if let Some(main) = app.get_webview_window("main") {
            let _ = main.show();
        }
    }
    // A pin reveals only after the screen is clean: "everything exits, then the
    // pin appears". The overlay is already hidden above, so the desktop is
    // clean. The show itself happens inside pin_image on the MAIN thread (a
    // show() from the capture thread was accepted but never executed); this is
    // the belt-and-suspenders for a pin that somehow stayed hidden.
    // Belt-and-suspenders: pin_ready normally reveals the pin as soon as it has
    // painted its image. If that IPC never arrives (slow webview), reveal from a
    // timer so a pin is never lost.
    if let Some(pin_label) = reveal_pin.filter(|label| label.starts_with("pin-")) {
        let app_for_timer = app.clone();
        std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_millis(1500));
            let app_for_closure = app_for_timer.clone();
            let _ = app_for_timer.run_on_main_thread(move || {
                if let Some(pin) = app_for_closure.get_webview_window(&pin_label) {
                    if !matches!(pin.is_visible(), Ok(true)) {
                        let _ = pin.show();
                    }
                }
            });
        });
    }
    Ok(show_main)
}

/// The (now hidden) overlay page's belt-and-suspenders after capture_overlay_end:
/// settles a session that somehow survived, and hides the overlay.
#[tauri::command]
pub fn capture_overlay_finish(
    window: tauri::WebviewWindow,
    pins: tauri::State<'_, PinState>,
) -> Result<(), String> {
    overlay_only(&window)?;
    let _ = crate::pinned_images::finish_session(&pins, "cancel");
    let _ = window.hide();
    Ok(())
}

/// Overlay-page poll target: the session generation. A change means "new image
/// available" (begin) or "state cleared" (end).
#[tauri::command]
pub fn capture_overlay_generation(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, Mutex<CaptureOverlayState>>,
) -> Result<u64, String> {
    overlay_only(&window)?;
    Ok(state.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).generation)
}

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SessionStatus {
    pub active: bool,
    pub result_generation: u64,
    pub ocr_text: Option<String>,
    pub translation: Option<String>,
}

/// Main-page poll target while a capture session is in flight: session end
/// (re-arm the capture guard) and the confirmed result metadata both travel
/// through here, because events to hidden pages cannot be trusted.
#[tauri::command]
pub fn capture_session_status(
    window: tauri::WebviewWindow,
    pins: tauri::State<'_, PinState>,
    state: tauri::State<'_, Mutex<CaptureOverlayState>>,
) -> Result<SessionStatus, String> {
    main_only(&window)?;
    let active = crate::pinned_images::session_active(&pins);
    let guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    Ok(SessionStatus {
        active,
        result_generation: guard.result_generation,
        ocr_text: guard.result.as_ref().map(|result| result.ocr_text.clone()),
        translation: guard.result.as_ref().map(|result| result.translation.clone()),
    })
}

/// The main page fetches the confirmed image over the binary channel (a JSON
/// array argument wedged the IPC once).
#[tauri::command]
pub fn capture_session_result_image(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, Mutex<CaptureOverlayState>>,
) -> Result<tauri::ipc::Response, String> {
    main_only(&window)?;
    let image = state
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .result
        .as_ref()
        .map(|result| result.image.clone())
        .ok_or_else(|| "no confirmed capture result".to_string())?;
    Ok(tauri::ipc::Response::new(image))
}
