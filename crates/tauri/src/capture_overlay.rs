use std::sync::Mutex;

use base64::Engine;
use serde::Deserialize;
use tauri::{Emitter, Manager};

use crate::pinned_images::{main_only, PinState};

#[derive(Default)]
pub struct CaptureOverlayState {
    image: Option<Vec<u8>>,
    shown: bool,
    /// Which display the session's overlay covers: the overlay page grabs the
    /// screen itself now (live-screen mode), and it must grab the one it sits on.
    display_index: Option<usize>,
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
    /// Index into the monitor list, so the overlay page can grab the display it
    /// covers. Optional: older callers pass geometry only.
    #[serde(default)]
    pub index: Option<usize>,
}

fn overlay_only(window: &tauri::WebviewWindow) -> Result<(), String> {
    if window.label() == "capture-overlay" {
        Ok(())
    } else {
        Err("capture overlay window required".into())
    }
}

/// Asks the system to leave this window out of screen grabs.
///
/// Display affinity is a property, not a race: the window is never part of a
/// capture, whoever is grabbing. That is what lets the overlay stay ON SCREEN
/// while `capture_screen` runs — the grab happens behind the veil instead of in
/// the open (see `capture_overlay_show`). Input is unaffected; only capture APIs
/// skip the window. Needs Windows 10 2004; on older builds the call fails and
/// the caller's hiding still keeps the veil out of the pixels.
#[cfg(windows)]
fn exclude_from_capture(window: &tauri::WebviewWindow) {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        SetWindowDisplayAffinity, WDA_EXCLUDEFROMCAPTURE,
    };
    let Ok(handle) = window.hwnd() else {
        return;
    };
    let _ = unsafe { SetWindowDisplayAffinity(handle.0 as _, WDA_EXCLUDEFROMCAPTURE) };
}

#[cfg(not(windows))]
fn exclude_from_capture(_: &tauri::WebviewWindow) {}

/// Returns the overlay window, creating it (hidden) on first use. The window is
/// PRE-CREATED at app startup and REUSED for every capture: WebView2 cold start
/// and page boot would otherwise cost 1-3s per capture. transparent(true) so any
/// frame that slips out before the page paints shows the desktop through — never
/// white, never black. Every path applies display affinity, so a reused window
/// keeps the exclusion too.
fn ensure_window(app: &tauri::AppHandle) -> Result<tauri::WebviewWindow, String> {
    if let Some(existing) = app.get_webview_window("capture-overlay") {
        exclude_from_capture(&existing);
        // See the builder below: a reused window must lose the undecorated shadow
        // too, or the veil stays inset by the frame thickness.
        let _ = existing.set_shadow(false);
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
        // NO undecorated shadow. tao's shadow for a decorations(false) window keeps
        // WS_THICKFRAME so DWM can draw the drop shadow, and the client area is then
        // inset by the frame thickness (SM_CXSIZEFRAME + SM_CXPADDEDBORDER: 8px at
        // 100%, 10px at 125%) — a window sized to the monitor then paints its content
        // shifted inward, leaving an undimmed strip at the left/top edge and rounded
        // corners on Windows 11. The overlay must cover the screen edge to edge, so
        // the shadow goes (Verta does the same).
        .shadow(false)
        .visible(false)
        .build()
        .map_err(|error| format!("capture overlay window creation failed: {error}"))?;
    exclude_from_capture(&created);
    Ok(created)
}

/// Startup hook: pre-create the hidden overlay window so the first capture is as
/// fast as every other one.
pub fn precreate(app: &tauri::AppHandle) {
    let _ = ensure_window(app);
}

/// Puts the overlay on screen over the LIVE screen and arms a capture session.
///
/// Live-screen mode: nothing is hidden and nothing is grabbed here. The overlay
/// is a transparent always-on-top window laid over the monitor; the page paints a
/// 25% dim, grabs ONE frame for the loupe/colour picker, and pixels for the
/// actual result are taken only when an action needs them. That is what makes
/// capture flash-free: no window hide, no settle wait, no frozen frame swap.
/// The window is also excluded from captures, so the dim layer never lands in the
/// grabbed pixels.
#[tauri::command]
pub async fn capture_overlay_show(
    window: tauri::WebviewWindow,
    display: Option<DisplayRect>,
) -> Result<(), String> {
    main_only(&window)?;
    let app = window.app_handle().clone();
    // Same main-thread rule as capture_overlay_begin: window creation pumps the
    // event loop, so it must not run on the main thread.
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<Mutex<CaptureOverlayState>>();
        {
            let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
            if guard.shown {
                return Err("capture overlay is already open".into());
            }
            // Claim the session before any window work: a second show must not
            // race this one.
            guard.shown = true;
            guard.display_index = display.as_ref().and_then(|rect| rect.index);
        }
        let overlay = match ensure_window(&app) {
            Ok(overlay) => overlay,
            Err(error) => {
                let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
                guard.shown = false;
                return Err(error);
            }
        };
        let position = display.as_ref().map(|rect| tauri::PhysicalPosition::new(rect.x, rect.y)).unwrap_or(tauri::PhysicalPosition::new(0, 0));
        let size = display.as_ref().map(|rect| tauri::PhysicalSize::new(rect.width, rect.height)).unwrap_or(tauri::PhysicalSize::new(800, 600));
        if let Err(error) = overlay.set_position(position).and_then(|_| overlay.set_size(size)) {
            let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
            guard.shown = false;
            return Err(format!("capture overlay window setup failed: {error}"));
        }
        if let Err(error) = overlay.show().and_then(|()| overlay.set_focus()) {
            let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
            guard.shown = false;
            let _ = overlay.hide();
            return Err(format!("capture overlay show failed: {error}"));
        }
        // Session armed: bump the generation and tell the page. It answers by
        // grabbing one screen frame for the loupe/colour picker (a grab changes
        // nothing on screen) and switching from the veil to the live overlay.
        #[cfg(debug_assertions)]
        if let (Ok(outer), Ok(inner)) = (overlay.outer_position(), overlay.inner_size()) {
            eprintln!(
                "[capture] overlay outer {},{} inner {}x{} / monitor {},{} {}x{}",
                outer.x, outer.y, inner.width, inner.height,
                position.x, position.y, size.width, size.height
            );
        }
        {
            let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
            guard.generation += 1;
        }
        let _ = app.emit_to("capture-overlay", "capture-image", {});
        Ok(())
    })
    .await
    .map_err(|error| format!("capture overlay task failed: {error}"))?
}

/// The display the current session covers.
///
/// In live-screen mode the overlay page owns the grab (the screen stays live
/// while the user selects; the backend only reports geometry). The grab must
/// target the display the overlay sits on, which the page cannot know by itself.
#[tauri::command]
pub fn capture_overlay_display_index(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, Mutex<CaptureOverlayState>>,
) -> Result<Option<usize>, String> {
    overlay_only(&window)?;
    Ok(state
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .display_index)
}

/// Failure-path cleanup for the main window: `capture_overlay_show` put the veil
/// on screen and the session then failed before any image existed (grab error,
/// window setup error). Takes the veil away and clears the session state so the
/// next capture starts from a clean slate.
#[tauri::command]
pub fn capture_overlay_abandon(window: tauri::WebviewWindow) -> Result<(), String> {
    main_only(&window)?;
    let app = window.app_handle().clone();
    if let Some(overlay) = app.get_webview_window("capture-overlay") {
        let _ = overlay.hide();
    }
    let state = app.state::<Mutex<CaptureOverlayState>>();
    let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    guard.image = None;
    guard.shown = false;
    guard.display_index = None;
    Ok(())
}

/// Arms the session with a pre-taken screenshot (legacy / test path).
///
/// Live-screen mode does not need this: `capture_overlay_show` starts a session
/// whose pixels are grabbed per action. Scripts and native e2e still arm a
/// session with an image directly, so this stays and behaves the same — it
/// stores the PNG for `capture_overlay_image` and shows the overlay if the show
/// step was skipped.
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
            if guard.image.is_some() {
                return Err("capture overlay session is already armed".into());
            }
            guard.image = Some(png);
            guard.display_index = display.as_ref().and_then(|rect| rect.index);
            guard.generation += 1;
        }
        // The 8s fallback must only cancel ITS OWN session: a normal end()
        // also clears shown and bumps the generation, so without the generation
        // check the timer of an already-finished session fired later, judged it
        // "stuck", and corrupted the NEXT session (intermittent wedge after
        // pin/confirm in quick succession).
        let session_generation = {
            let state = app.state::<Mutex<CaptureOverlayState>>();
            let guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
            guard.generation
        };
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
        // Normally capture_overlay_show already put the veil on screen before the
        // grab; this is the fallback for callers that arm the session directly
        // (tests, native e2e), where nothing is visible yet.
        let armed_visible = {
            let guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
            guard.shown
        };
        if !armed_visible {
            if let Err(error) = overlay.show().and_then(|()| overlay.set_focus()) {
                let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
                guard.image = None;
                guard.generation += 1;
                return Err(format!("capture overlay show failed: {error}"));
            }
            let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
            guard.shown = true;
        }
        // The page fetches the image (proactively on boot, or via this event for
        // reused windows) and paints it over the veil.
        let _ = app.emit_to("capture-overlay", "capture-image", {});
        let app_for_fallback = app.clone();
        std::thread::spawn(move || {
            // Generous: a cold page boot measured up to ~7.5s once (serialized
            // behind the main window's own boot).
            std::thread::sleep(std::time::Duration::from_millis(8000));
            let state = app_for_fallback.state::<Mutex<CaptureOverlayState>>();
            let should_recover = {
                let mut guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
                let should = guard.image.is_some() && guard.generation == session_generation;
                if should {
                    guard.image = None;
                    guard.shown = false;
                    guard.display_index = None;
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
) -> Result<CaptureEndOutcome, String> {
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
        guard.display_index = None;
        // No generation bump here: the generation marks "a session STARTED", and
        // the page polls it to arm. Bumping on end would make the poll arm a new
        // overlay for a session that is over.
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
    // The generation AFTER settling. The page passes it to
    // capture_overlay_finish so that a DELAYED finish (hidden-page IPC can be
    // deferred for seconds) can never settle or hide a NEWER session — that
    // race intermittently wedged the next capture ("stuck on the main window").
    let generation = app
        .state::<Mutex<CaptureOverlayState>>()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .generation;
    Ok(CaptureEndOutcome { restored: show_main, generation })
}

/// The (now hidden) overlay page's belt-and-suspenders after capture_overlay_end:
/// settles a session that somehow survived, and hides the overlay.
#[derive(Debug, serde::Serialize)]
pub struct CaptureEndOutcome {
    pub restored: bool,
    pub generation: u64,
}

/// The (now hidden) overlay page's belt-and-suspenders after capture_overlay_end:
/// settles a session that somehow survived, and hides the overlay. Generation-
/// gated: a finish whose generation no longer matches means a NEW session has
/// begun — it must touch nothing.
#[tauri::command]
pub fn capture_overlay_finish(
    window: tauri::WebviewWindow,
    pins: tauri::State<'_, PinState>,
    generation: u64,
) -> Result<(), String> {
    overlay_only(&window)?;
    {
        let state = window.app_handle().state::<Mutex<CaptureOverlayState>>();
        let guard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        if guard.generation != generation {
            return Ok(());
        }
    }
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
