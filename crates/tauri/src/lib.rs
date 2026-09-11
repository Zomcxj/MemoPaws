mod clipboard_hook;
mod commands;
mod hotkeys;
mod text_replacer;
mod text_replacer_hook;
mod tray;

use std::sync::{Arc, Mutex};

use tauri::{Emitter, Manager};
use tauri_plugin_global_shortcut::ShortcutState;

use commands::{
    add, ai_ocr, ai_translate, capture_delete, capture_get_image, capture_list, capture_screen,
    choose_data_dir, clipboard_clear, clipboard_delete, clipboard_delete_many, clipboard_get_image,
    clipboard_list, clipboard_paste_image, clipboard_set_locked, clipboard_update_text, delete,
    get_config, get_data_dir, get_storage_dir_conflict, get_theme, get_value, global_search,
    history_clear, history_delete, history_list, image_crop, image_preprocess,
    key_list, list, list_displays, list_opencode_providers, lock,
    memo_create, memo_delete, memo_get, memo_list, memo_render, memo_search, memo_update,
    migrate_data_dir, remove_master, reorder, restart_app, save_config, set_clipboard_max_items,
    set_close_behavior, set_history_max_items, set_language, set_master, set_settings_key,
    set_theme, show_main_window_when_ready, status, test_api_connection, text_replacement_create,
    text_replacement_delete, text_replacement_list, text_replacement_update, unlock, update,
};
use commands::{KeyVaultState, TextReplacerState};
use tray::setup_tray;

#[derive(Debug, PartialEq, Eq)]
enum CloseAction {
    Exit,
    HideToTray,
}

#[derive(Debug, PartialEq, Eq)]
enum CloseOperation {
    PreventClose,
    LockVault,
    EmitVaultLocked,
    HideWindow,
    Exit,
}

fn close_behavior_action(close_behavior: Option<&str>) -> CloseAction {
    if close_behavior == Some("tray") {
        CloseAction::HideToTray
    } else {
        CloseAction::Exit
    }
}

fn close_operation_plan(action: CloseAction) -> &'static [CloseOperation] {
    match action {
        CloseAction::Exit => &[CloseOperation::LockVault, CloseOperation::Exit],
        CloseAction::HideToTray => &[
            CloseOperation::PreventClose,
            CloseOperation::LockVault,
            CloseOperation::EmitVaultLocked,
            CloseOperation::HideWindow,
        ],
    }
}

pub fn run() {
    std::panic::set_hook(Box::new(|info| {
        let message = info.to_string();
        eprintln!("[memopaws] panic: {message}");
        if let Ok(dir) = memopaws_core::paths::ensure_data_dir() {
            let stamp = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|duration| duration.as_secs())
                .unwrap_or(0);
            if let Ok(mut file) = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(dir.join("panic.log"))
            {
                use std::io::Write;
                let _ = writeln!(file, "[{stamp}] {message}");
            }
        }
    }));
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    if event.state == ShortcutState::Pressed {
                        if let Some(action) = app
                            .try_state::<hotkeys::ShortcutActions>()
                            .and_then(|actions| actions.action_for(&shortcut))
                        {
                            let _ = app.emit("global-shortcut", action);
                        }
                    }
                })
                .build(),
        )
        .setup(|app| {
            memopaws_core::init();
            app.manage(hotkeys::ShortcutActions::default());
            let path = memopaws_core::paths::keys_dir().map_err(|error| error.to_string())?;
            let vault = memopaws_keys::KeyVault::load(path)
                .unwrap_or_else(|error| error.into_locked_vault());
            app.manage(Mutex::new(vault));
            let history = memopaws_config::history::HistoryManager::new()
                .load()
                .map_err(|error| error.to_string())?;
            app.manage(Mutex::new(history));
            let clipboard =
                memopaws_clipboard::ClipboardManager::load().map_err(|error| error.to_string())?;
            app.manage(Mutex::new(clipboard));
            let capture =
                memopaws_canvas::CaptureManager::load().map_err(|error| error.to_string())?;
            app.manage(Mutex::new(capture));
            let config =
                memopaws_config::config::AppConfig::load().map_err(|error| error.to_string())?;
            commands::validate_text_replacements(&config.text_replacements)?;
            let text_replacer = Arc::new(TextReplacerState::new(config.text_replacements.clone()));
            app.manage(Arc::clone(&text_replacer));
            let _ = app.emit("theme-changed", "dark");
            if let Err(error) = hotkeys::register_from_config(&app.handle()) {
                eprintln!("global shortcut registration: {error}");
            }
            setup_tray(&app.handle())?;
            if let Err(error) = clipboard_hook::init(&app.handle()) {
                eprintln!("clipboard listener: {error}");
            }
            if config.text_replacements.iter().any(|r| !r.abbr.is_empty()) {
                if let Err(error) = text_replacer_hook::init(text_replacer) {
                    eprintln!("text replacement listener: {error}");
                }
            }
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
            get_storage_dir_conflict,
            migrate_data_dir,
            restart_app,
            show_main_window_when_ready,
            set_close_behavior,
            set_clipboard_max_items,
            set_history_max_items,
            ai_ocr,
            ai_translate,
            set_settings_key,
            history_list,
            history_delete,
            history_clear,
            clipboard_list,
            clipboard_delete,
            clipboard_clear,
            clipboard_get_image,
            clipboard_set_locked,
            clipboard_update_text,
            clipboard_delete_many,
            global_search,
            capture_list,
            capture_get_image,
            capture_delete,
            capture_screen,
            image_preprocess,
            image_crop,
            clipboard_paste_image,
            list_displays,
            list_opencode_providers,
            text_replacement_list,
            text_replacement_create,
            text_replacement_update,
            text_replacement_delete,
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let close_behavior = memopaws_config::config::AppConfig::load()
                    .ok()
                    .and_then(|config| config.close_behavior);
                let action = close_behavior_action(close_behavior.as_deref());
                for operation in close_operation_plan(action) {
                    match operation {
                        CloseOperation::PreventClose => api.prevent_close(),
                        CloseOperation::LockVault => {
                            commands::lock_vault_state(&window.state::<KeyVaultState>());
                        }
                        CloseOperation::EmitVaultLocked => {
                            let _ = window.emit("vault-locked", ());
                        }
                        CloseOperation::HideWindow => {
                            let _ = window.hide();
                        }
                        CloseOperation::Exit => window.app_handle().exit(0),
                    }
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app, _event| {});
}

#[cfg(test)]
mod tests {
    use super::{close_behavior_action, close_operation_plan, CloseAction, CloseOperation};

    #[test]
    fn close_behavior_exits_or_hides_the_existing_window() {
        assert_eq!(close_behavior_action(Some("exit")), CloseAction::Exit);
        assert_eq!(close_behavior_action(Some("tray")), CloseAction::HideToTray);
        assert_eq!(close_behavior_action(None), CloseAction::Exit);
    }

    #[test]
    fn exit_locks_before_exiting() {
        assert_eq!(
            close_operation_plan(CloseAction::Exit),
            &[CloseOperation::LockVault, CloseOperation::Exit]
        );
    }

    #[test]
    fn tray_prevents_close_before_locking_and_hiding() {
        assert_eq!(
            close_operation_plan(CloseAction::HideToTray),
            &[
                CloseOperation::PreventClose,
                CloseOperation::LockVault,
                CloseOperation::EmitVaultLocked,
                CloseOperation::HideWindow,
            ]
        );
    }
}
