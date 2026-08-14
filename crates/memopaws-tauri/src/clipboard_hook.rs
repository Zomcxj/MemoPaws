use std::sync::Mutex;

use memopaws_clipboard::ClipboardManager;
use tauri::{AppHandle, Emitter, Manager};

pub fn init(app: &AppHandle) -> Result<(), String> {
    let app_for_text = app.clone();
    let app_for_image = app.clone();
    let _handle = memopaws_clipboard::spawn_listener(
        move |text: &str| {
            let state = app_for_text.state::<Mutex<ClipboardManager>>();
            let mut clipboard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
            if clipboard.add_text(text).is_ok() {
                let _ = app_for_text.emit("clipboard-changed", serde_json::json!({}));
            }
        },
        move |png: Vec<u8>| {
            let state = app_for_image.state::<Mutex<ClipboardManager>>();
            let mut clipboard = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
            if clipboard.add_image(&png).is_ok() {
                let _ = app_for_image.emit("clipboard-changed", serde_json::json!({}));
            }
        },
    )?;
    Ok(())
}
