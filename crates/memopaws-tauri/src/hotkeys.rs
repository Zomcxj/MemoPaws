use std::str::FromStr;

use tauri::AppHandle;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut};

use memopaws_config::config::AppConfig;

pub const DEFAULT_SHORTCUTS: &[(&str, &str)] = &[
    ("capture", "Alt+X"),
    ("canvas_fit", "Ctrl+F"),
    ("new_memo", "Ctrl+N"),
    ("global_search", "Ctrl+Shift+F"),
    ("toggle_clipboard", ""),
];

#[cfg(test)]
mod tests {
    #[test]
    fn defaults_match_python_shortcut_manager() {
        assert_eq!(super::DEFAULT_SHORTCUTS[0], ("capture", "Alt+X"));
        assert_eq!(super::DEFAULT_SHORTCUTS[1], ("canvas_fit", "Ctrl+F"));
        assert_eq!(super::DEFAULT_SHORTCUTS[2], ("new_memo", "Ctrl+N"));
        assert_eq!(super::DEFAULT_SHORTCUTS[3], ("global_search", "Ctrl+Shift+F"));
        assert_eq!(super::DEFAULT_SHORTCUTS[4], ("toggle_clipboard", ""));
    }
}

pub fn register_from_config(app: &AppHandle) -> Result<(), String> {
    let config = AppConfig::load().map_err(|e| e.to_string())?;
    let mut shortcuts = DEFAULT_SHORTCUTS.iter().map(|(action, key)| ((*action).to_string(), (*key).to_string())).collect::<std::collections::HashMap<_, _>>();
    if let Some(saved) = config.shortcuts {
        for (action, key) in saved {
            let action = match action.as_str() {
                "screenshot_ocr" => "capture".to_string(),
                "paste_image" => continue,
                _ => action,
            };
            shortcuts.insert(action, key);
        }
    }
    register_shortcuts(app, shortcuts)
}

pub fn validate_shortcuts(shortcuts: &std::collections::HashMap<String, String>) -> Result<(), String> {
    for (action, key) in shortcuts {
        if key.trim().is_empty() { continue; }
        Shortcut::from_str(key).map_err(|error| format!("invalid shortcut {key} for {action}: {error}"))?;
    }
    Ok(())
}

pub fn register_shortcuts(app: &AppHandle, shortcuts: std::collections::HashMap<String, String>) -> Result<(), String> {
    validate_shortcuts(&shortcuts)?;
    let previous = AppConfig::load().ok().and_then(|config| config.shortcuts);
    app.global_shortcut().unregister_all().map_err(|error| format!("failed to clear shortcuts: {error}"))?;
    let mut registered = Vec::new();
    for (action, key) in &shortcuts {
        if key.trim().is_empty() { continue; }
        let shortcut = Shortcut::from_str(key).map_err(|error| format!("invalid shortcut {key} for {action}: {error}"))?;
        if let Err(error) = app.global_shortcut().register(shortcut) {
            let _ = app.global_shortcut().unregister_all();
            if let Some(previous) = previous {
                let _ = register_without_rollback(app, &previous);
            }
            return Err(format!("failed to register shortcut {key} for {action}: {error}"));
        }
        registered.push(shortcut);
    }
    let _ = registered;
    Ok(())
}

fn register_without_rollback(app: &AppHandle, shortcuts: &std::collections::HashMap<String, String>) -> Result<(), String> {
    for key in shortcuts.values().filter(|key| !key.trim().is_empty()) {
        app.global_shortcut().register(Shortcut::from_str(key).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    }
    Ok(())
}
