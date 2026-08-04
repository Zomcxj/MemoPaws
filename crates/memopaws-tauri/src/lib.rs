mod commands;
mod hotkeys;
mod tray;

use std::sync::Mutex;

use tauri::{Emitter, Manager};
use tauri_plugin_global_shortcut::ShortcutState;

use commands::{
    get_config, get_theme, memo_create, memo_delete, memo_get, memo_list, memo_render,
    memo_search, memo_update, set_theme, set_language, save_config, status, unlock, lock, set_master, remove_master,
    list, key_list, add, update, delete, reorder, get_value, ai_ocr, ai_translate,
    history_list, history_delete, history_clear,
    clipboard_list, clipboard_delete, clipboard_clear, clipboard_get_image,
    capture_list, capture_get_image, capture_delete, test_api_connection, get_data_dir,
    choose_data_dir, migrate_data_dir, set_close_behavior, set_floating_widget_visible,
    set_clipboard_max_items, set_history_max_items,
};
use commands::KeyVaultState;
use tray::setup_tray;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().with_handler(move |app, shortcut, event| {
            if event.state == ShortcutState::Pressed {
                let _ = app.emit("global-shortcut", shortcut.to_string());
            }
        }).build())
        .setup(|app| {
            memopaws_core::init();
            let path = memopaws_core::paths::keys_dir().map_err(|error| error.to_string())?;
            let vault = memopaws_keys::KeyVault::load(path).unwrap_or_else(|error| error.into_locked_vault());
            app.manage(Mutex::new(vault));
            let history = memopaws_config::history::HistoryManager::new().load().map_err(|error| error.to_string())?;
            app.manage(Mutex::new(history));
            let clipboard = memopaws_clipboard::ClipboardManager::load().map_err(|error| error.to_string())?;
            app.manage(Mutex::new(clipboard));
            let capture = memopaws_canvas::CaptureManager::load().map_err(|error| error.to_string())?;
            app.manage(Mutex::new(capture));
            let _ = app.emit("theme-changed", "dark");
            let _ = hotkeys::register_from_config(&app.handle());
            setup_tray(&app.handle())?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_theme,
            get_config,
            set_theme,
            set_language,
            memo_list,
            memo_get,
            memo_create,
            memo_update,
            memo_delete,
            memo_search,
            memo_render,
            status,
            unlock,
            lock,
            set_master,
            remove_master,
            list,
            key_list,
            add,
            update,
            delete,
            reorder,
            get_value,
            save_config,
            test_api_connection,
            get_data_dir,
            choose_data_dir,
            migrate_data_dir,
            set_close_behavior,
            set_floating_widget_visible,
            set_clipboard_max_items,
            set_history_max_items,
            ai_ocr,
            ai_translate,
            history_list,
            history_delete,
            history_clear,
            clipboard_list,
            clipboard_delete,
            clipboard_clear,
            clipboard_get_image,
            capture_list,
            capture_get_image,
            capture_delete,
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let close_behavior = memopaws_config::config::AppConfig::load()
                    .ok()
                    .and_then(|config| config.close_behavior)
                    .unwrap_or_else(|| "exit".to_string());
                if close_behavior == "tray" {
                    commands::lock_vault_state(&window.state::<KeyVaultState>());
                    let _ = window.emit("vault-locked", ());
                    let _ = window.hide();
                    api.prevent_close();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app, _event| {});
}
