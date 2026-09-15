use std::{collections::HashMap, str::FromStr, sync::Mutex};

use tauri::{AppHandle, Manager};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut};

use memopaws_config::config::AppConfig;

/// Single source of truth lives in `memopaws_config::config` so the persisted
/// default and the registration table cannot drift apart.
pub use memopaws_config::config::DEFAULT_SHORTCUTS;

#[derive(Default)]
pub struct ShortcutActions(Mutex<HashMap<Shortcut, String>>);

impl ShortcutActions {
    pub fn action_for(&self, shortcut: &Shortcut) -> Option<String> {
        self.0.lock().ok()?.get(shortcut).cloned()
    }

    fn replace(&self, actions: HashMap<Shortcut, String>) {
        if let Ok(mut current) = self.0.lock() {
            *current = actions;
        }
    }

    fn snapshot(&self) -> HashMap<Shortcut, String> {
        self.0.lock().map(|current| current.clone()).unwrap_or_default()
    }
}

pub fn shortcut_actions(shortcuts: &HashMap<String, String>) -> Result<HashMap<Shortcut, String>, String> {
    let mut parsed = shortcuts
        .iter()
        .filter(|(_, key)| !key.trim().is_empty())
        .map(|(action, key)| {
            Shortcut::from_str(key)
                .map(|shortcut| (action.clone(), shortcut))
                .map_err(|error| format!("invalid shortcut {key} for {action}: {error}"))
        })
        .collect::<Result<Vec<_>, _>>()?;
    parsed.sort_by(|(left, _), (right, _)| left.cmp(right));

    let mut actions = HashMap::with_capacity(parsed.len());
    for (action, shortcut) in parsed {
        if let Some(previous_action) = actions.insert(shortcut, action.clone()) {
            return Err(format!(
                "duplicate shortcut {shortcut} for {action}; already assigned to {previous_action}"
            ));
        }
    }
    Ok(actions)
}

#[cfg(test)]
mod tests {
    use std::{collections::HashMap, str::FromStr};

    use tauri_plugin_global_shortcut::Shortcut;

    #[test]
    fn defaults_match_python_shortcut_manager() {
        assert_eq!(super::DEFAULT_SHORTCUTS[0], ("capture", "Alt+X"));
        assert_eq!(super::DEFAULT_SHORTCUTS[1], ("canvas_fit", "Ctrl+F"));
        assert_eq!(super::DEFAULT_SHORTCUTS[2], ("new_memo", "Ctrl+N"));
        assert_eq!(super::DEFAULT_SHORTCUTS[3], ("global_search", "Ctrl+Shift+F"));
        assert_eq!(super::DEFAULT_SHORTCUTS[4], ("toggle_clipboard", "Ctrl+Shift+V"));
    }

    fn map(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        pairs.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
    }

    #[test]
    fn valid_shortcuts_pass_and_empty_keys_are_skipped() {
        assert!(super::shortcut_actions(&map(&[("capture", "Alt+X")])).is_ok());
        assert!(super::shortcut_actions(&map(&[("global_search", "Ctrl+Shift+F")])).is_ok());
        assert!(super::shortcut_actions(&map(&[("toggle_clipboard", "")])).unwrap().is_empty());
        assert!(super::shortcut_actions(&map(&[("capture", "  ")])).unwrap().is_empty());
    }

    #[test]
    fn invalid_shortcuts_are_rejected_with_an_action_specific_message() {
        let error = super::shortcut_actions(&map(&[("capture", "not-a-shortcut")])).unwrap_err();
        assert!(error.contains("capture"));

        assert!(super::shortcut_actions(&map(&[("capture", "Ctrl+")])).is_err());
        assert!(super::shortcut_actions(&map(&[("capture", "Ctrl+Shift+F+")])).is_err());
        let long = "A".repeat(101);
        assert!(super::shortcut_actions(&map(&[("capture", &long)])).is_err());
    }

    #[test]
    fn canonical_duplicate_shortcuts_are_rejected_for_the_later_action() {
        let error = super::shortcut_actions(&map(&[
            ("capture", "Ctrl+Shift+F"),
            ("global_search", "Ctrl + Shift + F"),
        ]))
        .unwrap_err();

        assert!(error.contains("global_search"));
        assert!(error.contains("capture"));
    }

    #[test]
    fn shortcut_action_map_uses_actions_and_replaces_stale_bindings() {
        let shortcuts = map(&[("capture", "Alt+X"), ("new_memo", "Ctrl+N")]);
        let actions = super::shortcut_actions(&shortcuts).unwrap();

        assert_eq!(actions.get(&Shortcut::from_str("Alt+X").unwrap()).map(String::as_str), Some("capture"));
        assert_eq!(actions.get(&Shortcut::from_str("Ctrl+N").unwrap()).map(String::as_str), Some("new_memo"));

        let updated = map(&[("capture", "Ctrl+Shift+F")]);
        let actions = super::shortcut_actions(&updated).unwrap();
        assert_eq!(actions.get(&Shortcut::from_str("Alt+X").unwrap()), None);
        assert_eq!(actions.get(&Shortcut::from_str("Ctrl+Shift+F").unwrap()).map(String::as_str), Some("capture"));
    }

    #[test]
    fn restored_action_map_contains_only_successfully_restored_shortcuts() {
        let capture = Shortcut::from_str("Alt+X").unwrap();
        let search = Shortcut::from_str("Ctrl+Shift+F").unwrap();
        let restored = super::actions_for_registered(&[(capture, "capture".to_string())]);

        assert_eq!(restored.len(), 1);
        assert_eq!(restored.get(&capture).map(String::as_str), Some("capture"));
        assert_eq!(restored.get(&search), None);
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

pub fn register_shortcuts(app: &AppHandle, shortcuts: std::collections::HashMap<String, String>) -> Result<(), String> {
    let actions = shortcut_actions(&shortcuts)?;
    let previous_actions = app.state::<ShortcutActions>().snapshot();
    app.global_shortcut().unregister_all().map_err(|error| format!("failed to clear shortcuts: {error}"))?;
    for (shortcut, action) in &actions {
        if let Err(error) = app.global_shortcut().register(*shortcut) {
            let registration_error = format!("failed to register shortcut {shortcut} for {action}: {error}");
            return rollback_shortcuts(app, previous_actions, registration_error);
        }
    }
    app.state::<ShortcutActions>().replace(actions);
    Ok(())
}

fn rollback_shortcuts(
    app: &AppHandle,
    previous_actions: HashMap<Shortcut, String>,
    registration_error: String,
) -> Result<(), String> {
    if let Err(error) = app.global_shortcut().unregister_all() {
        app.state::<ShortcutActions>().replace(HashMap::new());
        return Err(format!("{registration_error}; failed to clear partial registrations: {error}"));
    }

    let mut previous = previous_actions.into_iter().collect::<Vec<_>>();
    previous.sort_by(|(_, left), (_, right)| left.cmp(right));
    let mut restored = Vec::with_capacity(previous.len());
    for (shortcut, action) in previous {
        if let Err(error) = app.global_shortcut().register(shortcut) {
            app.state::<ShortcutActions>().replace(actions_for_registered(&restored));
            return Err(format!(
                "{registration_error}; restored only {} previous shortcuts before failing to restore {shortcut} for {action}: {error}",
                restored.len()
            ));
        }
        restored.push((shortcut, action));
    }
    app.state::<ShortcutActions>().replace(actions_for_registered(&restored));
    Err(registration_error)
}

fn actions_for_registered(bindings: &[(Shortcut, String)]) -> HashMap<Shortcut, String> {
    bindings.iter().cloned().collect()
}
