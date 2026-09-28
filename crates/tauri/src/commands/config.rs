use std::{
    collections::HashSet,
    sync::Arc,
};

use tauri::{Emitter, Manager};

use crate::hotkeys;


use super::{ClipboardState, HistoryState, KeyVaultState};
use super::keys::{is_settings_key, save_settings_key};
use super::textrep::TextReplacerState;

fn validate_theme(theme: &str) -> Result<&str, String> {
    match theme {
        "dark" | "light" | "auto" => Ok(theme),
        _ => Err("theme must be dark, light or auto".to_string()),
    }
}

// This is the public command's validation boundary; it runs before config path resolution or I/O.
fn validate_set_theme_request(theme: String) -> Result<String, String> {
    Ok(validate_theme(theme.trim())?.to_string())
}

fn get_theme_from(path: &std::path::Path) -> Result<String, String> {
    let theme = memopaws_config::config::AppConfig::load_from(path)
        .map_err(|error| error.to_string())?
        .theme;
    Ok(match theme.as_deref() {
        Some("light") => "light".to_string(),
        Some("dark") => "dark".to_string(),
        Some("auto") => "auto".to_string(),
        _ => "dark".to_string(),
    })
}

fn safe_config_value(config: serde_json::Value, has_vault_key: Option<bool>) -> serde_json::Value {
    let mut object = config.as_object().cloned().unwrap_or_default();
    let has_api_key = has_vault_key.unwrap_or_else(|| {
        object.remove("api_key").is_some_and(|value| {
            !value.is_null() && value.as_str().is_some_and(|key| !key.is_empty())
        })
    });
    object.remove("api_key");
    object.insert("has_api_key".into(), serde_json::Value::Bool(has_api_key));
    serde_json::Value::Object(object)
}

#[tauri::command]
pub fn get_theme() -> Result<String, String> {
    get_theme_from(&memopaws_core::paths::config_path().map_err(|error| error.to_string())?)
}

#[tauri::command]
pub fn get_config(vault: tauri::State<'_, KeyVaultState>) -> Result<serde_json::Value, String> {
    let has_vault_key = lock_recover!(vault)
        .list()
        .iter()
        .any(is_settings_key);
    memopaws_config::config::AppConfig::load()
        .map(|c| {
            safe_config_value(
                serde_json::to_value(c).unwrap_or(serde_json::json!({})),
                Some(has_vault_key),
            )
        })
        .map_err(|e| e.to_string())
}

fn set_theme_at(path: &std::path::Path, theme: &str) -> Result<(), String> {
    let theme = validate_theme(theme.trim())?.to_string();
    let mut config =
        memopaws_config::config::AppConfig::load_from(path).map_err(|error| error.to_string())?;
    config.theme = Some(theme);
    config.save_to(path).map_err(|error| error.to_string())
}

fn normalize_theme(config: &mut memopaws_config::config::AppConfig) {
    if !matches!(config.theme.as_deref(), Some("dark") | Some("light") | Some("auto")) {
        config.theme = Some("dark".to_string());
    }
}

pub(super) fn validate_config_request(config: &serde_json::Value) -> Result<(), String> {
    if let Some(url) = config.get("api_url") {
        let url = url
            .as_str()
            .ok_or_else(|| "api_url must be a string".to_string())?
            .trim();
        let has_scheme = url
            .strip_prefix("http://")
            .or_else(|| url.strip_prefix("https://"));
        if has_scheme.is_none()
            || has_scheme.is_some_and(|rest| rest.split('/').next().unwrap_or_default().is_empty())
            || url.chars().any(char::is_whitespace)
        {
            return Err("api_url must be a valid HTTP(S) URL".to_string());
        }
    }
    if let Some(model) = config.get("api_model") {
        let model = model
            .as_str()
            .ok_or_else(|| "api_model must be a string".to_string())?
            .trim();
        if model.is_empty() || model.len() > 200 {
            return Err("api_model must be 1-200 characters".to_string());
        }
    }
    for field in ["clipboard_max_items", "history_max_items"] {
        if let Some(value) = config.get(field).filter(|value| !value.is_null()) {
            let value = value
                .as_u64()
                .ok_or_else(|| format!("{field} must be an integer"))?;
            if !(10..=500).contains(&value) {
                return Err(format!("{field} must be between 10 and 500"));
            }
        }
    }
    if let Some(behavior) = config.get("close_behavior") {
        let behavior = behavior
            .as_str()
            .ok_or_else(|| "close_behavior must be a string".to_string())?;
        if !matches!(behavior, "exit" | "tray") {
            return Err("close_behavior must be exit or tray".to_string());
        }
    }
    if let Some(shortcuts) = config.get("shortcuts") {
        let shortcuts = shortcuts
            .as_object()
            .ok_or_else(|| "shortcuts must be an object".to_string())?;
        for (action, shortcut) in shortcuts {
            let shortcut = shortcut
                .as_str()
                .ok_or_else(|| format!("shortcut {action} must be a string"))?
                .trim();
            if action.trim().is_empty()
                || (shortcut.is_empty() && action != "toggle_clipboard")
                || (!shortcut.is_empty() && !valid_shortcut(shortcut))
            {
                return Err(format!(
                    "shortcut {action} must be non-empty and at most 100 characters"
                ));
            }
        }
    }
    if let Some(replacements) = config.get("text_replacements") {
        let replacements: Vec<memopaws_config::config::TextReplacement> =
            serde_json::from_value(replacements.clone()).map_err(|_| {
                "text_replacements must be an array of replacement rules".to_string()
            })?;
        validate_text_replacements(&replacements)?;
    }
    Ok(())
}

pub(crate) fn validate_text_replacements(
    replacements: &[memopaws_config::config::TextReplacement],
) -> Result<(), String> {
    let mut abbreviations = HashSet::new();
    for rule in replacements {
        let abbr_len = rule.abbr.chars().count();
        if !(1..=64).contains(&abbr_len) || rule.abbr.trim().is_empty() {
            return Err("text replacement abbreviation must be 1-64 characters".to_string());
        }
        if rule.replacement.len() > 4096 {
            return Err("text replacement replacement must be at most 4096 bytes".to_string());
        }
        if !abbreviations.insert(&rule.abbr) {
            return Err("text replacement abbreviations must be unique".to_string());
        }
    }
    Ok(())
}

fn valid_shortcut(shortcut: &str) -> bool {
    if shortcut.is_empty() || shortcut.len() > 100 {
        return false;
    }
    let parts: Vec<_> = shortcut.split('+').collect();
    parts.len() >= 2
        && parts[..parts.len() - 1]
            .iter()
            .all(|part| matches!(*part, "Ctrl" | "Alt" | "Shift" | "Meta"))
        && !parts
            .last()
            .is_some_and(|part| part.is_empty() || part.chars().any(char::is_whitespace))
}

#[tauri::command]
pub fn set_theme(theme: String) -> Result<(), String> {
    let theme = validate_set_theme_request(theme)?;
    set_theme_at(
        &memopaws_core::paths::config_path().map_err(|error| error.to_string())?,
        &theme,
    )
}

#[tauri::command]
pub fn set_language(language: String, app: tauri::AppHandle) -> Result<(), String> {
    let language = language.trim();
    if !matches!(language, "zh" | "en") {
        return Err("language must be zh or en".to_string());
    }
    let path = memopaws_core::paths::config_path().map_err(|error| error.to_string())?;
    let mut config =
        memopaws_config::config::AppConfig::load_from(&path).map_err(|error| error.to_string())?;
    config.language = Some(language.to_string());
    config.save_to(&path).map_err(|error| error.to_string())?;
    crate::tray::setup_tray(&app).map_err(|error| error.to_string())
}

#[tauri::command]
pub async fn save_config(
    config: serde_json::Value,
    vault: tauri::State<'_, KeyVaultState>,
    history: tauri::State<'_, HistoryState>,
    clipboard: tauri::State<'_, ClipboardState>,
    text_replacer: tauri::State<'_, Arc<TextReplacerState>>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    // Async so the vault I/O, hotkey re-registration and config writes never block the UI.
    let config = config.get("config").cloned().unwrap_or(config);
    validate_config_request(&config)?;
    if let Some(key) = config
        .get("api_key")
        .and_then(|value| value.as_str())
        .filter(|key| !key.trim().is_empty())
    {
        if !lock_recover!(vault).status().unlocked {
            return Err(
                "key vault is locked; unlock it on the Keys page before saving an API key"
                    .to_string(),
            );
        }
        let model = config
            .get("api_model")
            .and_then(|value| value.as_str())
            .unwrap_or(memopaws_config::config::DEFAULT_MODEL);
        save_settings_key(
            &vault,
            key,
            config
                .get("api_url")
                .and_then(|value| value.as_str())
                .unwrap_or_default(),
            model,
        )?;
    }
    let config_path = memopaws_core::paths::config_path().map_err(|e| e.to_string())?;
    let mut merged = memopaws_config::config::AppConfig::load_from(&config_path)
        .map_err(|error| error.to_string())?;
    let previous_shortcuts = merged.shortcuts.clone();
    apply_config_patch(&mut merged, &config)?;
    if merged.shortcuts != previous_shortcuts {
        let shortcuts = merged.shortcuts.clone().unwrap_or_default();
        hotkeys::register_shortcuts(&app, shortcuts)?;
    }
    merged
        .save_to(&config_path)
        .map_err(|error| error.to_string())?;
    if config.get("text_replacements").is_some() {
        *lock_recover!(text_replacer.rules) = merged.text_replacements.clone();
    }
    if let Some(max) = config
        .get("clipboard_max_items")
        .and_then(|value| value.as_u64())
    {
        lock_recover!(clipboard).set_max_items(max as usize)?;
    }
    if let Some(max) = config
        .get("history_max_items")
        .and_then(|value| value.as_u64())
    {
        lock_recover!(history)
            .set_max_items(max as usize)
            .map_err(|error| error.to_string())?;
    }
    if let Some(value) = config
        .get("close_behavior")
        .and_then(|value| value.as_str())
    {
        let _ = app.emit("close-behavior-changed", value);
    }
    Ok(())
}

#[cfg(test)]
fn save_config_at(path: &std::path::Path, config: serde_json::Value) -> Result<(), String> {
    validate_config_request(&config)?;
    let mut app_config =
        memopaws_config::config::AppConfig::load_from(path).map_err(|error| error.to_string())?;
    normalize_theme(&mut app_config);
    apply_config_patch(&mut app_config, &config)?;
    app_config.api_key = None;
    app_config.save_to(path).map_err(|error| error.to_string())
}

fn apply_config_patch(
    app_config: &mut memopaws_config::config::AppConfig,
    config: &serde_json::Value,
) -> Result<(), String> {
    normalize_theme(app_config);
    if let Some(language) = config.get("language").and_then(|v| v.as_str()) {
        app_config.language = Some(language.to_owned());
    }
    if let Some(close_behavior) = config.get("close_behavior").and_then(|v| v.as_str()) {
        app_config.close_behavior = Some(close_behavior.to_owned());
    }
    if let Some(max) = config.get("clipboard_max_items").and_then(|v| v.as_u64()) {
        app_config.clipboard_max_items = Some(max as usize);
    }
    if let Some(max) = config.get("history_max_items").and_then(|v| v.as_u64()) {
        app_config.history_max_items = Some(max as usize);
    }
    if let Some(api_url) = config.get("api_url").and_then(|v| v.as_str()) {
        app_config.api_url = Some(api_url.trim().to_owned());
    }
    if let Some(api_model) = config.get("api_model").and_then(|v| v.as_str()) {
        app_config.api_model = Some(api_model.trim().to_owned());
    }
    if let Some(shortcuts) = config.get("shortcuts").and_then(|v| v.as_object()) {
        app_config.shortcuts = Some(
            shortcuts
                .iter()
                .map(|(k, v)| (k.clone(), v.as_str().unwrap_or("").to_owned()))
                .collect(),
        );
    }
    if let Some(replacements) = config.get("text_replacements") {
        app_config.text_replacements = serde_json::from_value(replacements.clone())
            .map_err(|_| "text_replacements must be an array of replacement rules".to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn set_close_behavior(value: String, app: tauri::AppHandle) -> Result<(), String> {
    let mut config =
        memopaws_config::config::AppConfig::load().map_err(|error| error.to_string())?;
    validate_config_request(&serde_json::json!({"close_behavior": value}))?;
    config.close_behavior = Some(value.clone());
    config.save().map_err(|error| error.to_string())?;
    let _ = app.emit("close-behavior-changed", value);
    Ok(())
}

fn e2e_hidden_mode() -> bool {
    std::env::var_os("MEMOPAWS_E2E_HIDDEN").is_some_and(|value| value == "1")
}

#[tauri::command]
pub fn show_main_window_when_ready(app: tauri::AppHandle) -> Result<(), String> {
    if e2e_hidden_mode() {
        return Ok(());
    }
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "main window not found".to_string())?;
    window.show().map_err(|error| error.to_string())?;
    window.set_focus().map_err(|error| error.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn set_clipboard_max_items(
    value: usize,
    state: tauri::State<'_, ClipboardState>,
) -> Result<(), String> {
    validate_config_request(&serde_json::json!({"clipboard_max_items": value as u64}))?;
    lock_recover!(state).set_max_items(value)
}

#[cfg(test)]
mod tests {
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn validate_theme_accepts_supported_values_and_rejects_unknown_values() {
        assert_eq!(super::validate_theme("dark").unwrap(), "dark");
        assert_eq!(super::validate_theme("light").unwrap(), "light");
        assert!(super::validate_theme("blue").is_err());
    }

    #[test]
    fn validate_theme_accepts_auto_and_rejects_other_modes() {
        assert_eq!(super::validate_theme("auto").unwrap(), "auto");
        assert!(super::validate_theme("system").is_err());
        assert!(super::validate_theme("AUTO").is_err());
    }

    #[test]
    fn get_theme_from_preserves_auto_and_falls_back_to_dark() {
        let dir = std::env::temp_dir().join(format!(
            "memopaws-theme-auto-{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).unwrap();

        let auto_path = dir.join("auto.json");
        std::fs::write(&auto_path, r#"{"theme":"auto"}"#).unwrap();
        assert_eq!(super::get_theme_from(&auto_path).unwrap(), "auto");

        let unknown_path = dir.join("unknown.json");
        std::fs::write(&unknown_path, r#"{"theme":"blue"}"#).unwrap();
        assert_eq!(super::get_theme_from(&unknown_path).unwrap(), "dark");

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn normalize_theme_keeps_auto_and_resets_unknown() {
        let dir = std::env::temp_dir().join(format!(
            "memopaws-theme-normalize-{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).unwrap();

        let auto_path = dir.join("auto.json");
        std::fs::write(&auto_path, r#"{"theme":"auto"}"#).unwrap();
        let mut auto_config =
            memopaws_config::config::AppConfig::load_from(&auto_path).unwrap();
        super::normalize_theme(&mut auto_config);
        assert_eq!(auto_config.theme.as_deref(), Some("auto"));

        let unknown_path = dir.join("unknown.json");
        std::fs::write(&unknown_path, r#"{"theme":"blue"}"#).unwrap();
        let mut unknown_config =
            memopaws_config::config::AppConfig::load_from(&unknown_path).unwrap();
        super::normalize_theme(&mut unknown_config);
        assert_eq!(unknown_config.theme.as_deref(), Some("dark"));

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn public_set_theme_validation_rejects_before_config_load_or_save() {
        // Boundary: this pure request validation is the first operation in set_theme;
        // invalid input cannot resolve, load, or save the real config path.
        assert_eq!(
            super::validate_set_theme_request(" light ".to_string()).unwrap(),
            "light"
        );
        assert_eq!(
            super::validate_set_theme_request("dark".to_string()).unwrap(),
            "dark"
        );
        assert_eq!(
            super::validate_set_theme_request("blue".to_string()).unwrap_err(),
            "theme must be dark, light or auto"
        );
    }

    #[test]
    fn theme_commands_persist_to_an_explicit_config_path() {
        let path = std::env::temp_dir().join(format!(
            "memopaws-theme-{}.json",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
        ));

        assert_eq!(super::get_theme_from(&path).unwrap(), "dark");
        super::set_theme_at(&path, " light ").unwrap();
        assert_eq!(super::get_theme_from(&path).unwrap(), "light");

        let before_invalid = std::fs::read_to_string(&path).unwrap();
        assert!(super::set_theme_at(&path, "blue").is_err());
        assert_eq!(std::fs::read_to_string(&path).unwrap(), before_invalid);
        assert_eq!(super::get_theme_from(&path).unwrap(), "light");

        let raw = std::fs::read_to_string(&path)
            .unwrap()
            .replace("\"theme\": \"light\"", "\"theme\": \"blue\"");
        std::fs::write(&path, raw).unwrap();
        assert_eq!(super::get_theme_from(&path).unwrap(), "dark");

        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn malformed_existing_theme_is_normalized_before_save() {
        let path = std::env::temp_dir().join(format!(
            "memopaws-theme-save-{}.json",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
        ));
        let mut config = memopaws_config::config::AppConfig::default();
        config.theme = Some("blue".to_string());
        config.save_to(&path).unwrap();

        super::save_config_at(&path, serde_json::json!({ "theme": "light" })).unwrap();

        let saved = memopaws_config::config::AppConfig::load_from(&path).unwrap();
        assert_eq!(saved.theme.as_deref(), Some("dark"));
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn config_validation_rejects_invalid_connection_and_runtime_settings() {
        assert!(super::validate_config_request(&serde_json::json!({
            "api_url": "not-a-url",
            "api_model": "vision"
        }))
        .is_err());
        assert!(super::validate_config_request(&serde_json::json!({
            "api_url": "https://example.test/v1",
            "api_model": ""
        }))
        .is_err());
        assert!(super::validate_config_request(&serde_json::json!({
            "clipboard_max_items": 0
        }))
        .is_err());
        assert!(super::validate_config_request(&serde_json::json!({
            "close_behavior": "minimize"
        }))
        .is_err());
        assert!(super::validate_config_request(&serde_json::json!({
            "shortcuts": {"screenshot_ocr": ""}
        }))
        .is_err());
        assert!(super::validate_config_request(&serde_json::json!({
            "shortcuts": {"screenshot_ocr": "not-a-shortcut"}
        }))
        .is_err());
    }

    #[test]
    fn config_validation_accepts_supported_partial_updates() {
        assert!(super::validate_config_request(&serde_json::json!({
            "api_url": "https://example.test/v1/chat/completions",
            "api_model": "vision",
            "clipboard_max_items": 50,
             "close_behavior": "tray",
            "shortcuts": {"screenshot_ocr": "Alt+X"}
        }))
        .is_ok());
    }

    #[test]
    fn text_replacement_validation_enforces_bounds_and_unique_abbreviations() {
        let valid = serde_json::json!({
            "text_replacements": [{"abbr": "brb", "replacement": "be right back"}]
        });
        assert!(super::validate_config_request(&valid).is_ok());

        let duplicate = serde_json::json!({
            "text_replacements": [
                {"abbr": "brb", "replacement": "one"},
                {"abbr": "brb", "replacement": "two"}
            ]
        });
        assert!(super::validate_config_request(&duplicate).is_err());

        let oversized = serde_json::json!({
            "text_replacements": [{"abbr": "a", "replacement": "x".repeat(4097)}]
        });
        assert!(super::validate_config_request(&oversized).is_err());
    }

    #[test]
    fn config_patch_persists_typed_text_replacements() {
        let path = std::env::temp_dir().join(format!(
            "memopaws-text-replacements-{}.json",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
        ));
        memopaws_config::config::AppConfig::default()
            .save_to(&path)
            .unwrap();

        super::save_config_at(
            &path,
            serde_json::json!({
                "text_replacements": [{"abbr": ":brb", "replacement": "be right back"}]
            }),
        )
        .unwrap();

        let saved = memopaws_config::config::AppConfig::load_from(&path).unwrap();
        assert_eq!(saved.text_replacements.len(), 1);
        assert_eq!(saved.text_replacements[0].abbr, ":brb");
        assert_eq!(saved.text_replacements[0].replacement, "be right back");
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn config_response_removes_api_key_and_exposes_presence_only() {
        let value = super::safe_config_value(
            serde_json::json!({"api_key": "secret", "api_model": "vision"}),
            None,
        );
        assert_eq!(value["has_api_key"], true);
        assert!(value.get("api_key").is_none());
        assert_eq!(value["api_model"], "vision");
    }

    #[test]
    fn config_response_reports_missing_or_null_api_keys_as_absent() {
        let null_key = super::safe_config_value(
            serde_json::json!({"api_key": null, "api_model": "vision"}),
            None,
        );
        assert_eq!(null_key["has_api_key"], false);
        assert!(null_key.get("api_key").is_none());

        let empty_key = super::safe_config_value(
            serde_json::json!({"api_key": "", "api_model": "vision"}),
            None,
        );
        assert_eq!(empty_key["has_api_key"], false);

        let forced = super::safe_config_value(serde_json::json!({"api_key": "hidden"}), Some(true));
        assert_eq!(forced["has_api_key"], true);
        assert!(forced.get("api_key").is_none());
    }

    #[test]
    fn shortcut_validation_allows_empty_only_for_toggle_clipboard() {
        assert!(super::validate_config_request(
            &serde_json::json!({"shortcuts": {"toggle_clipboard": ""}})
        )
        .is_ok());
        assert!(super::validate_config_request(
            &serde_json::json!({"shortcuts": {"toggle_clipboard": "Alt+V"}})
        )
        .is_ok());
        assert!(
            super::validate_config_request(&serde_json::json!({"shortcuts": {"capture": ""}}))
                .is_err()
        );
        assert!(super::validate_config_request(
            &serde_json::json!({"shortcuts": {"capture": "Ctrl+Alt+Shift+Meta+X+Y+Z"}})
        )
        .is_err());
        assert!(super::validate_config_request(
            &serde_json::json!({"shortcuts": {"capture": "Ctrl+ "}})
        )
        .is_err());
        assert!(super::validate_config_request(
            &serde_json::json!({"shortcuts": {"capture": "Ctrl+"}})
        )
        .is_err());
        assert!(super::validate_config_request(
            &serde_json::json!({"shortcuts": {"capture": "Ctrl+Alt"}})
        )
        .is_ok());
    }

    #[test]
    fn config_patch_updates_every_supported_field() {
        let mut config = memopaws_config::config::AppConfig::default();
        super::apply_config_patch(
            &mut config,
            &serde_json::json!({
                "language": "en",
                "close_behavior": "exit",
                "clipboard_max_items": 60,
                "api_url": " https://example.test/v1 ",
                 "api_model": " model-x ",
                "shortcuts": {"capture": "Ctrl+Shift+C", "screenshot_ocr": "Ctrl+Shift+D"},
                "text_replacements": [{"abbr": ":w", "replacement": "welcome"}]
            }),
        )
        .unwrap();

        assert_eq!(config.language.as_deref(), Some("en"));
        assert_eq!(config.close_behavior.as_deref(), Some("exit"));
        assert_eq!(config.clipboard_max_items, Some(60));
        assert_eq!(config.api_url.as_deref(), Some("https://example.test/v1"));
        assert_eq!(config.api_model.as_deref(), Some("model-x"));
        assert_eq!(
            config.shortcuts.as_ref().unwrap()["capture"],
            "Ctrl+Shift+C"
        );
        assert_eq!(
            config.shortcuts.as_ref().unwrap()["screenshot_ocr"],
            "Ctrl+Shift+D"
        );
        assert_eq!(config.text_replacements[0].abbr, ":w");

        super::apply_config_patch(&mut config, &serde_json::json!({})).unwrap();
        assert_eq!(config.language.as_deref(), Some("en"));
    }

    #[test]
    fn config_patch_rejects_malformed_text_replacements() {
        let mut config = memopaws_config::config::AppConfig::default();
        assert_eq!(
            super::apply_config_patch(
                &mut config,
                &serde_json::json!({"text_replacements": [{"abbr": 1}]})
            )
            .unwrap_err(),
            "text_replacements must be an array of replacement rules"
        );
    }

    #[test]
    fn save_config_at_strips_api_key_and_rejects_invalid_payloads() {
        let path = std::env::temp_dir().join(format!(
            "memopaws-save-config-{}.json",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
        ));
        memopaws_config::config::AppConfig::default()
            .save_to(&path)
            .unwrap();

        super::save_config_at(
            &path,
            serde_json::json!({
                "api_key": "never-keep-me",
                "language": "en",
                "clipboard_max_items": 70
            }),
        )
        .unwrap();

        let raw = std::fs::read_to_string(&path).unwrap();
        assert!(!raw.contains("never-keep-me"));
        let value: serde_json::Value = serde_json::from_str(&raw).unwrap();
        assert!(value.get("api_key").is_none_or(|v| v.is_null()));
        let saved = memopaws_config::config::AppConfig::load_from(&path).unwrap();
        assert_eq!(saved.language.as_deref(), Some("en"));
        assert_eq!(saved.clipboard_max_items, Some(70));

        assert!(
            super::save_config_at(&path, serde_json::json!({"clipboard_max_items": 5})).is_err()
        );
        assert!(super::save_config_at(&path, serde_json::json!({"api_url": "not a url"})).is_err());
        // 旧版配置缺字段时前端会回传 null，校验必须跳过而非报错
        assert!(
            super::save_config_at(&path, serde_json::json!({"history_max_items": null})).is_ok()
        );
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn text_replacement_validation_covers_abbreviation_bounds() {
        let empty = memopaws_config::config::TextReplacement {
            abbr: "".into(),
            replacement: "x".into(),
        };
        assert!(super::validate_text_replacements(&[empty]).is_err());

        let whitespace = memopaws_config::config::TextReplacement {
            abbr: "   ".into(),
            replacement: "x".into(),
        };
        assert!(super::validate_text_replacements(&[whitespace]).is_err());

        let long = memopaws_config::config::TextReplacement {
            abbr: "a".repeat(65),
            replacement: "x".into(),
        };
        assert!(super::validate_text_replacements(&[long]).is_err());

        let boundary = memopaws_config::config::TextReplacement {
            abbr: "a".repeat(64),
            replacement: "x".into(),
        };
        assert!(super::validate_text_replacements(&[boundary]).is_ok());
    }

    #[test]
    fn e2e_hidden_mode_reads_env_flag() {
        let key = "MEMOPAWS_E2E_HIDDEN";
        let previous = std::env::var_os(key);
        std::env::remove_var(key);
        assert!(!super::e2e_hidden_mode());
        std::env::set_var(key, "1");
        assert!(super::e2e_hidden_mode());
        std::env::set_var(key, "0");
        assert!(!super::e2e_hidden_mode());
        match previous {
            Some(value) => std::env::set_var(key, value),
            None => std::env::remove_var(key),
        }
    }
}
