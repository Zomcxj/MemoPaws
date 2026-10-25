use std::{collections::HashMap, sync::Mutex};

use base64::Engine;

use tauri::Manager;

#[derive(Clone)]
struct PinData {
    /// The composed PNG on disk — the pin page loads it through the asset
    /// protocol (QuickClipboard's model). IPC image transport (JSON array AND
    /// base64) corrupted intermittently and left pins blank.
    path: std::path::PathBuf,
    radius: f64,
}

#[derive(Default)]
pub struct Pins {
    next: u64,
    images: HashMap<String, PinData>,
    capture_visible: Option<bool>,
    restore_visible: Option<bool>,
}

impl Pins {
    fn begin(&mut self, visible: bool) -> Result<(), String> {
        if self.capture_visible.is_some() { return Err("capture is already active".into()); }
        self.capture_visible = Some(visible);
        Ok(())
    }
    fn next_label(&mut self) -> String {
        self.next += 1;
        format!("pin-{}", self.next)
    }
    fn insert_with_label(&mut self, label: String, data: PinData) {
        self.restore_visible.get_or_insert(self.capture_visible.unwrap_or(false));
        self.images.insert(label, data);
    }
    fn insert(&mut self, data: PinData) -> String {
        self.next += 1;
        let label = format!("pin-{}", self.next);
        self.insert_with_label(label.clone(), data);
        label
    }
    fn remove(&mut self, label: &str) -> Option<bool> {
        if let Some(data) = self.images.remove(label) {
            let _ = std::fs::remove_file(&data.path);
        }
        if self.images.is_empty() && self.capture_visible.is_none() {
            self.restore_visible.take()
        } else { None }
    }
    fn finish(&mut self, outcome: &str) -> Result<bool, String> {
        if !matches!(outcome, "pin" | "confirm" | "cancel") {
            return Err("invalid capture outcome".into());
        }
        let before = self.capture_visible.take().ok_or("capture is not active")?;
        let pending = if self.images.is_empty() { self.restore_visible.take() } else { None };
        Ok(match outcome {
            "confirm" => true,
            "pin" if !self.images.is_empty() => false,
            "cancel" if !self.images.is_empty() => before,
            _ => pending.unwrap_or(true),
        })
    }
}

pub type PinState = Mutex<Pins>;

fn validate_radius(radius: f64) -> Result<f64, String> {
    if !radius.is_finite() || radius < 0.0 {
        return Err("invalid pin corner radius".into());
    }
    Ok(radius)
}

/// Caller-window lookup: a pin window may only read its own image, so the
/// label comes from the invoking window, never from frontend-supplied data.
fn lookup(pins: &Pins, label: &str) -> Result<(std::path::PathBuf, f64), String> {
    let data = pins
        .images
        .get(label)
        .ok_or_else(|| "pinned image not found".to_string())?;
    Ok((data.path.clone(), data.radius))
}

pub(crate) fn main_only(window: &tauri::WebviewWindow) -> Result<(), String> {
    if window.label() == "main" { Ok(()) } else { Err("main window required".into()) }
}

/// Capture-session commands are driven by the main window (session start) or by
/// the capture overlay window (pin/confirm/cancel actions).
pub(crate) fn capture_caller(window: &tauri::WebviewWindow) -> Result<(), String> {
    match window.label() {
        "main" | "capture-overlay" => Ok(()),
        _ => Err("main or capture overlay window required".into()),
    }
}

pub(crate) fn finish_session(pins: &PinState, outcome: &str) -> Result<bool, String> {
    pins.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).finish(outcome)
}

pub(crate) fn session_active(pins: &PinState) -> bool {
    let pins = pins.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    pins.capture_visible.is_some()
}

#[tauri::command]
pub fn capture_session_begin(
    window: tauri::WebviewWindow,
    visible: bool,
    state: tauri::State<'_, PinState>,
) -> Result<(), String> {
    main_only(&window)?;
    state.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).begin(visible)
}

#[tauri::command]
pub fn capture_session_finish(
    window: tauri::WebviewWindow,
    outcome: String,
    state: tauri::State<'_, PinState>,
) -> Result<bool, String> {
    main_only(&window)?;
    state.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).finish(&outcome)
}

#[tauri::command]
pub async fn pin_image(
    window: tauri::WebviewWindow,
    // The composed image travels base64: a JSON array of millions of elements
    // gets corrupted in transit and the pin renders an undecodable image.
    image_base64: Option<String>,
    image: Option<Vec<u8>>,
    radius: Option<f64>,
) -> Result<String, String> {
    let image = match image_base64 {
        Some(image_base64) => base64::engine::general_purpose::STANDARD
            .decode(image_base64)
            .map_err(|error| format!("pin image base64 decode failed: {error}"))?,
        None => image.unwrap_or_default(),
    };
    capture_caller(&window)?;
    let app = window.app_handle().clone();
    // The pin belongs to the MAIN window's display: the invoking window is now
    // the capture overlay (a separate fullscreen window), whose current monitor
    // can be missing or the wrong one - that put pins nowhere.
    let monitor = app
        .get_webview_window("main")
        .and_then(|main| main.current_monitor().ok().flatten())
        .or_else(|| window.current_monitor().ok().flatten())
        .ok_or_else(|| "pin display not found".to_string())?;
    // The pin lives on the invoking window's monitor, so that monitor's own
    // scale factor is the correct physical↔logical conversion (mixed-DPI safe).
    let factor = monitor.scale_factor();
    let area = monitor.work_area();
    let origin = area.position;
    let bounds = area.size;
    if !factor.is_finite() || factor <= 0.0 || bounds.width == 0 || bounds.height == 0 {
        return Err("invalid pin display geometry".into());
    }
    // Everything runs in spawn_blocking: window creation on the main thread
    // DEADLOCKS in this app (the overlay pre-create comment documents the same
    // lesson). The main-thread version left the pin window in a state where
    // show() returned Ok but the window never appeared and every later main
    // thread query failed with FailedToReceiveMessage.
    let app_bg = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let radius = validate_radius(radius.unwrap_or(0.0))?;
        let decoded = memopaws_ocr::image_util::decode_limited(&image).map_err(|error| error.to_string())?;
        let (w, h) = (decoded.width(), decoded.height());
        drop(decoded);
        // Builder sizes are logical pixels; clamp to the original-scale policy
        // and to the monitor work area so oversized pins stay on-screen.
        let scale = (800.0 * factor / w as f64)
            .min(600.0 * factor / h as f64)
            .min(bounds.width as f64 / w as f64)
            .min(bounds.height as f64 / h as f64)
            .min(1.0);
        // The composed PNG goes to DISK; the pin page fetches it via IPC.
        let pins_dir = app_bg
            .path()
            .app_data_dir()
            .map_err(|error| format!("pin data dir failed: {error}"))?
            .join("pins");
        std::fs::create_dir_all(&pins_dir).map_err(|error| format!("pin data dir failed: {error}"))?;
        let label = app_bg
            .state::<PinState>()
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .next_label();
        let image_path = pins_dir.join(format!("{label}.png"));
        std::fs::write(&image_path, &image).map_err(|error| format!("pin image write failed: {error}"))?;
        app_bg.state::<PinState>()
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .insert_with_label(label.clone(), PinData { path: image_path, radius });
        let created = tauri::WebviewWindowBuilder::new(&app_bg, &label, tauri::WebviewUrl::App("index.html#pin".into()))
            .title("钉图")
            .always_on_top(true)
            .decorations(false)
            .transparent(true)
            .resizable(false)
            .visible(false)
            .position(origin.x as f64 / factor, origin.y as f64 / factor)
            .inner_size(w as f64 * scale / factor, h as f64 * scale / factor)
            .build();
        let pin = match created {
            Ok(pin) => pin,
            Err(error) => {
                app_bg.state::<PinState>()
                    .lock()
                    .unwrap_or_else(|poisoned| poisoned.into_inner())
                    .remove(&label);
                return Err(format!("pin window creation failed: {error}"));
            }
        };
        let sized = pin
            .set_position(origin)
            .and_then(|_| {
                pin.set_size(tauri::PhysicalSize::new(
                    (w as f64 * scale).round() as u32,
                    (h as f64 * scale).round() as u32,
                ))
            });
        // Deliberately NOT shown here: the reveal happens inside
        // capture_overlay_end once the screen is clean (exit first, then show the
        // pin), with pin_show as the error-path fallback so a pin is never lost.
        if let Err(error) = sized {
            let _ = pin.close();
            app_bg.state::<PinState>()
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner())
                .remove(&label);
            return Err(format!("pin window setup failed: {error}"));
        }
        // The window stays HIDDEN until the page has loaded and drawn its
        // image (pin_ready + a belt-and-suspenders timer in capture_overlay_end).
        // Showing it earlier paints an empty transparent frame first.
        Ok::<String, String>(label)
    })
    .await
    .map_err(|error| format!("pin task failed: {error}"))?
}

/// The pin page calls this once it has actually drawn its image. Showing the
/// window before that paints an empty transparent frame (a blank pin).
#[tauri::command]
pub fn pin_ready(window: tauri::WebviewWindow) -> Result<(), String> {
    if !window.label().starts_with("pin-") {
        return Err("pin window required".into());
    }
    // Mark ready so capture_overlay_end's reveal timer knows it can show now.
    let app = window.app_handle().clone();
    let label = window.label().to_string();
    let app_for_closure = app.clone();
    let _ = app.run_on_main_thread(move || {
        if let Some(pin) = app_for_closure.get_webview_window(&label) {
            let _ = pin.show();
        }
    });
    Ok(())
}

/// Corner radius for a pin window (cheap metadata; the PNG itself travels over
/// the binary channel via get_pinned_image_bytes).
#[tauri::command]
pub fn get_pinned_image_radius(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, PinState>,
) -> Result<f64, String> {
    let pins = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    let (_, radius) = lookup(&pins, window.label())?;
    Ok(radius)
}

/// Disk path + radius for the pin page.
#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PinnedImageMeta {
    pub path: String,
    pub radius: f64,
}

#[tauri::command]
pub fn get_pinned_image_meta(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, PinState>,
) -> Result<PinnedImageMeta, String> {
    let pins = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    let (path, radius) = lookup(&pins, window.label())?;
    Ok(PinnedImageMeta { path: path.to_string_lossy().to_string(), radius })
}

/// Base64 handoff: the PNG is read from disk and sent as a base64 string.
/// The asset protocol scope did not match on Windows, and the binary IPC
/// channel (tauri::ipc::Response) failed intermittently. Base64 of a few
/// hundred KB PNG is a few hundred KB string - reliable for IPC.
#[tauri::command]
pub fn get_pinned_image_base64(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, PinState>,
) -> Result<String, String> {
    let pins = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    let (path, _) = lookup(&pins, window.label())?;
    let image = std::fs::read(&path).map_err(|error| format!("pin image read failed: {error}"))?;
    Ok(base64::engine::general_purpose::STANDARD.encode(image))
}

#[tauri::command]
pub fn pin_close(window: tauri::WebviewWindow) -> Result<(), String> {
    if !window.label().starts_with("pin-") {
        return Err("pin window required".into());
    }
    window.close().map_err(|error| error.to_string())
}

/// Pin-window destruction hook: cleanup is idempotent, and the main window is
/// only shown when the final pin of a visible-origin session closes.
pub fn destroyed(window: &tauri::Window) {
    let app = window.app_handle();
    let restore = app
        .state::<PinState>()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .remove(window.label());
    if restore == Some(true) {
        if let Some(main) = app.get_webview_window("main") {
            let _ = main.show();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn data() -> PinData { PinData { path: std::path::PathBuf::from("pin-test.png"), radius: 12.0 } }
    #[test]
    fn independent_close_restores_only_last() {
        let mut pins = Pins::default();
        pins.begin(true).unwrap();
        let a = pins.insert(data());
        assert!(!pins.finish("pin").unwrap());
        pins.begin(false).unwrap();
        let b = pins.insert(data());
        assert!(!pins.finish("pin").unwrap());
        assert_ne!(a, b);
        assert_eq!(pins.remove(&a), None);
        assert!(pins.images.contains_key(&b));
        assert_eq!(pins.remove(&b), Some(true));
        assert_eq!(pins.remove(&b), None);
    }
    #[test]
    fn hidden_first_pin_stays_hidden_after_last_close() {
        let mut pins = Pins::default();
        pins.begin(false).unwrap();
        let a = pins.insert(data());
        pins.finish("pin").unwrap();
        assert_eq!(pins.remove(&a), Some(false));
    }
    #[test]
    fn close_during_capture_preserves_first_visibility() {
        let mut pins = Pins::default();
        pins.begin(true).unwrap();
        let a = pins.insert(data());
        pins.finish("pin").unwrap();
        pins.begin(false).unwrap();
        assert_eq!(pins.remove(&a), None);
        let b = pins.insert(data());
        assert!(!pins.finish("pin").unwrap());
        assert_eq!(pins.remove(&b), Some(true));
    }
    #[test]
    fn failed_creation_can_be_rolled_back_before_capture_finishes() {
        let mut pins = Pins::default();
        pins.begin(true).unwrap();
        let a = pins.insert(data());
        pins.remove(&a);
        assert!(pins.finish("cancel").unwrap());
        assert!(pins.restore_visible.is_none());
        assert!(pins.begin(false).is_ok());
        assert!(pins.begin(true).is_err());
    }
    #[test]
    fn invalid_or_duplicate_finish_does_not_consume_a_new_session() {
        let mut pins = Pins::default();
        pins.begin(true).unwrap();
        assert!(pins.finish("invalid").is_err());
        assert!(pins.finish("confirm").unwrap());
        assert!(pins.finish("confirm").is_err());
    }
    #[test]
    fn invalid_radius_is_rejected() {
        assert!(validate_radius(0.0).is_ok());
        assert!(validate_radius(16.0).is_ok());
        assert!(validate_radius(-1.0).is_err());
        assert!(validate_radius(f64::NAN).is_err());
        assert!(validate_radius(f64::INFINITY).is_err());
    }
    #[test]
    fn corrupt_pin_image_fails_decoding() {
        assert!(memopaws_ocr::image_util::decode_limited(b"not a png").is_err());
        assert!(memopaws_ocr::image_util::decode_limited(&[]).is_err());
    }
    #[test]
    fn main_label_cannot_read_a_pin() {
        let mut pins = Pins::default();
        pins.begin(true).unwrap();
        let label = pins.insert(data());
        assert!(lookup(&pins, "main").is_err());
        assert_eq!(lookup(&pins, &label).unwrap(), (std::path::PathBuf::from("pin-test.png"), 12.0));
    }
    #[test]
    fn duplicate_destroy_does_not_signal_restoration() {
        let mut pins = Pins::default();
        pins.begin(true).unwrap();
        let label = pins.insert(data());
        pins.finish("pin").unwrap();
        assert_eq!(pins.remove(&label), Some(true));
        // Second destroy callback for the same window: no restoration signal.
        assert_eq!(pins.remove(&label), None);
    }
}
