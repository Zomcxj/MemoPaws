
use std::{fs, path::Path, sync::Mutex, time::Duration};

use memopaws_canvas::{CaptureManager, CaptureRecord};
use memopaws_clipboard::{ClipboardItem, ClipboardManager};
use memopaws_keys::{KeyEntry, KeyEntryInput, KeyVault, VaultStatus};
use memopaws_config::history::{HistoryManager, HistoryRecord};
use memopaws_ocr::{ApiConfig, Client, Language, OcrResult, TranslateResult};
use memopaws_memo::model::Memo;
use memopaws_memo::renderer::{render_markdown, RenderTheme};
use memopaws_memo::search::MemoSearchResult;
use memopaws_memo::{migrate, search, storage};
use zeroize::Zeroizing;
use tauri::Emitter;
use tauri_plugin_dialog::DialogExt;

use crate::hotkeys;

fn memo_dir() -> Result<std::path::PathBuf, String> {
    storage::resolve_memo_dir(None).map_err(|error| error.to_string())
}

fn migrate_legacy(dir: &std::path::Path) -> Result<(), String> {
    let config_dir = dir.parent().ok_or_else(|| "memo directory has no parent".to_string())?;
    migrate::migrate_legacy_memos(&config_dir.join("memo.json"), dir)
        .map(|_| ())
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn memo_list() -> Result<Vec<Memo>, String> {
    let dir = memo_dir()?;
    migrate_legacy(&dir)?;
    storage::list_memos(&dir).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn memo_get(id: i64) -> Result<Memo, String> {
    storage::read_memo(&memo_dir()?, id).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn memo_create(memo: Memo) -> Result<Memo, String> {
    storage::create_memo(&memo_dir()?, memo).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn memo_update(memo: Memo) -> Result<Memo, String> {
    storage::update_memo(&memo_dir()?, memo).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn memo_delete(id: i64) -> Result<(), String> {
    storage::delete_memo(&memo_dir()?, id).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn memo_search(query: String) -> Result<Vec<MemoSearchResult>, String> {
    let memos = memo_list()?;
    Ok(search::search_memos(&memos, &query))
}

#[tauri::command]
pub fn memo_render(content: String, theme: RenderTheme) -> Result<String, String> {
    Ok(render_markdown(&content, theme))
}

fn validate_theme(theme: &str) -> Result<&str, String> {
    match theme {
        "dark" | "light" => Ok(theme),
        _ => Err("theme must be dark or light".to_string()),
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
        _ => "dark".to_string(),
    })
}

fn safe_config_value(config: serde_json::Value, has_vault_key: Option<bool>) -> serde_json::Value {
    let mut object = config.as_object().cloned().unwrap_or_default();
    let has_api_key = has_vault_key.unwrap_or_else(|| object.remove("api_key").is_some_and(|value| !value.is_null() && value.as_str().is_some_and(|key| !key.is_empty())));
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
    let has_vault_key = vault.lock().map_err(|_| "key vault state is unavailable".to_string())?
        .list().iter().any(|entry| entry.name == "settings_api_key" && entry.entry_type == "llm");
    memopaws_config::config::AppConfig::load()
        .map(|c| safe_config_value(serde_json::to_value(c).unwrap_or(serde_json::json!({})), Some(has_vault_key)))
        .map_err(|e| e.to_string())
}

fn set_theme_at(path: &std::path::Path, theme: &str) -> Result<(), String> {
    let theme = validate_theme(theme.trim())?.to_string();
    let mut config = memopaws_config::config::AppConfig::load_from(path)
        .map_err(|error| error.to_string())?;
    config.theme = Some(theme);
    config.save_to(path).map_err(|error| error.to_string())
}

fn normalize_theme(config: &mut memopaws_config::config::AppConfig) {
    if !matches!(config.theme.as_deref(), Some("dark") | Some("light")) {
        config.theme = Some("dark".to_string());
    }
}

fn validate_config_request(config: &serde_json::Value) -> Result<(), String> {
    if let Some(url) = config.get("api_url") {
        let url = url.as_str().ok_or_else(|| "api_url must be a string".to_string())?.trim();
        let has_scheme = url.strip_prefix("http://").or_else(|| url.strip_prefix("https://"));
        if has_scheme.is_none() || has_scheme.is_some_and(|rest| rest.split('/').next().unwrap_or_default().is_empty()) || url.chars().any(char::is_whitespace) {
            return Err("api_url must be a valid HTTP(S) URL".to_string());
        }
    }
    if let Some(model) = config.get("api_model") {
        let model = model.as_str().ok_or_else(|| "api_model must be a string".to_string())?.trim();
        if model.is_empty() || model.len() > 200 { return Err("api_model must be 1-200 characters".to_string()); }
    }
    for field in ["clipboard_max_items", "history_max_items"] {
        if let Some(value) = config.get(field) {
            let value = value.as_u64().ok_or_else(|| format!("{field} must be an integer"))?;
            if !(10..=500).contains(&value) { return Err(format!("{field} must be between 10 and 500")); }
        }
    }
    if let Some(behavior) = config.get("close_behavior") {
        let behavior = behavior.as_str().ok_or_else(|| "close_behavior must be a string".to_string())?;
        if !matches!(behavior, "exit" | "tray") { return Err("close_behavior must be exit or tray".to_string()); }
    }
    if let Some(value) = config.get("show_floating_widget") {
        if !value.is_boolean() { return Err("show_floating_widget must be a boolean".to_string()); }
    }
    if let Some(shortcuts) = config.get("shortcuts") {
        let shortcuts = shortcuts.as_object().ok_or_else(|| "shortcuts must be an object".to_string())?;
        for (action, shortcut) in shortcuts {
            let shortcut = shortcut.as_str().ok_or_else(|| format!("shortcut {action} must be a string"))?.trim();
            if action.trim().is_empty() || (shortcut.is_empty() && action != "toggle_clipboard") || (!shortcut.is_empty() && !valid_shortcut(shortcut)) {
                return Err(format!("shortcut {action} must be non-empty and at most 100 characters"));
            }
        }
    }
    Ok(())
}

fn valid_shortcut(shortcut: &str) -> bool {
    if shortcut.is_empty() || shortcut.len() > 100 { return false; }
    let parts: Vec<_> = shortcut.split('+').collect();
    parts.len() >= 2
        && parts[..parts.len() - 1].iter().all(|part| matches!(*part, "Ctrl" | "Alt" | "Shift" | "Meta"))
        && !parts.last().is_some_and(|part| part.is_empty() || part.chars().any(char::is_whitespace))
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
pub fn set_language(language: String) -> Result<(), String> {
    let language = language.trim();
    if !matches!(language, "zh" | "en") {
        return Err("language must be zh or en".to_string());
    }
    let path = memopaws_core::paths::config_path().map_err(|error| error.to_string())?;
    let mut config = memopaws_config::config::AppConfig::load_from(&path).map_err(|error| error.to_string())?;
    config.language = Some(language.to_string());
    config.save_to(&path).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn save_config(config: serde_json::Value, vault: tauri::State<'_, KeyVaultState>, history: tauri::State<'_, HistoryState>, clipboard: tauri::State<'_, ClipboardState>, app: tauri::AppHandle) -> Result<(), String> {
    let config = config.get("config").cloned().unwrap_or(config);
    validate_config_request(&config)?;
    if let Some(key) = config.get("api_key").and_then(|value| value.as_str()).filter(|key| !key.trim().is_empty()) {
        save_settings_key(&vault, key, config.get("api_url").and_then(|value| value.as_str()).unwrap_or_default())?;
    }
    let config_path = memopaws_core::paths::config_path().map_err(|e| e.to_string())?;
    let mut merged = memopaws_config::config::AppConfig::load_from(&config_path).map_err(|error| error.to_string())?;
    apply_config_patch(&mut merged, &config)?;
    if let Some(shortcuts) = merged.shortcuts.clone() {
        hotkeys::register_shortcuts(&app, shortcuts)?;
    }
    merged.save_to(&config_path).map_err(|error| error.to_string())?;
    if let Some(max) = config.get("history_max_items").and_then(|value| value.as_u64()) {
        history.lock().map_err(|_| "history state is unavailable".to_string())?.set_max_items(max as usize).map_err(|error| error.to_string())?;
    }
    if let Some(max) = config.get("clipboard_max_items").and_then(|value| value.as_u64()) {
        clipboard.lock().map_err(|_| "clipboard state is unavailable".to_string())?.set_max_items(max as usize)?;
    }
    if let Some(value) = config.get("close_behavior").and_then(|value| value.as_str()) { let _ = app.emit("close-behavior-changed", value); }
    if let Some(value) = config.get("show_floating_widget").and_then(|value| value.as_bool()) { let _ = app.emit("floating-widget-visibility-changed", value); }
    Ok(())
}

fn save_config_at(path: &std::path::Path, config: serde_json::Value) -> Result<(), String> {
    validate_config_request(&config)?;
    let mut app_config = memopaws_config::config::AppConfig::load_from(path).map_err(|e| e.to_string())?;
    normalize_theme(&mut app_config);
    apply_config_patch(&mut app_config, &config)?;
    app_config.api_key = None;
    app_config.save_to(path).map_err(|e| e.to_string())
}

fn apply_config_patch(app_config: &mut memopaws_config::config::AppConfig, config: &serde_json::Value) -> Result<(), String> {
    normalize_theme(app_config);
    if let Some(language) = config.get("language").and_then(|v| v.as_str()) { app_config.language = Some(language.to_owned()); }
    if let Some(close_behavior) = config.get("close_behavior").and_then(|v| v.as_str()) { app_config.close_behavior = Some(close_behavior.to_owned()); }
    if let Some(max) = config.get("clipboard_max_items").and_then(|v| v.as_u64()) { app_config.clipboard_max_items = Some(max as usize); }
    if let Some(max) = config.get("history_max_items").and_then(|v| v.as_u64()) { app_config.history_max_items = Some(max as usize); }
    if let Some(api_url) = config.get("api_url").and_then(|v| v.as_str()) { app_config.api_url = Some(api_url.trim().to_owned()); }
    if let Some(api_model) = config.get("api_model").and_then(|v| v.as_str()) { app_config.api_model = Some(api_model.trim().to_owned()); }
    if let Some(show) = config.get("show_floating_widget").and_then(|v| v.as_bool()) { app_config.show_floating_widget = Some(show); }
    if let Some(shortcuts) = config.get("shortcuts").and_then(|v| v.as_object()) {
        app_config.shortcuts = Some(shortcuts.iter().map(|(k, v)| (k.clone(), v.as_str().unwrap_or("").to_owned())).collect());
    }
    Ok(())
}

fn save_settings_key(state: &tauri::State<'_, KeyVaultState>, key: &str, url: &str) -> Result<(), String> {
    let mut vault = state.lock().map_err(|_| "key vault state is unavailable".to_string())?;
    let input = || KeyEntryInput { name: "settings_api_key".into(), entry_type: "llm".into(), value: key.to_owned(), url: url.to_owned(), url_anthropic: String::new(), note: "Settings API key".into() };
    let existing = vault.list().into_iter().find(|entry| entry.name == "settings_api_key" && entry.entry_type == "llm");
    if let Some(entry) = existing { vault.update(entry.id, input()).map_err(|_| "API key could not be stored securely".to_string())?; }
    else { vault.add(input()).map_err(|_| "API key could not be stored securely".to_string())?; }
    Ok(())
}

#[tauri::command]
pub fn get_data_dir() -> Result<String, String> {
    memopaws_core::paths::data_dir().map(|path| path.to_string_lossy().into_owned()).map_err(|error| error.to_string())
}

#[tauri::command]
pub async fn choose_data_dir(app: tauri::AppHandle) -> Result<Option<String>, String> {
    Ok(app.dialog().file().blocking_pick_folder().map(|path| path.to_string()))
}

fn migration_target(args: &serde_json::Value) -> Result<String, String> {
    args.get("data_dir").or_else(|| args.get("path")).and_then(|value| value.as_str()).map(str::trim).filter(|path| !path.is_empty()).map(str::to_owned).ok_or_else(|| "data_dir or path is required".to_string())
}

fn migration_mode(value: &str) -> Result<memopaws_core::paths::MigrationMode, String> {
    match value.trim().to_ascii_lowercase().as_str() {
        "merge" => Ok(memopaws_core::paths::MigrationMode::Merge),
        "overwrite" | "replace" | "move" => Ok(memopaws_core::paths::MigrationMode::Replace),
        "cancel" => Ok(memopaws_core::paths::MigrationMode::Cancel),
        _ => Err("migration mode must be merge, overwrite, or cancel".to_string()),
    }
}

#[derive(Debug, serde::Serialize)]
pub struct MigrationResult {
    pub path: Option<String>,
    pub requires_restart: bool,
    pub restart_required: bool,
}

#[tauri::command]
pub fn migrate_data_dir(data_dir: Option<String>, path: Option<String>, mode: Option<String>) -> Result<MigrationResult, String> {
    let args = serde_json::json!({"data_dir": data_dir, "path": path});
    let target = migration_target(&args)?;
    let mode = migration_mode(mode.as_deref().unwrap_or("merge"))?;
    let source = memopaws_core::paths::data_dir().map_err(|error| error.to_string())?;
    let result = memopaws_core::paths::migrate_data_dir(Path::new(&target), mode).map_err(|error| error.to_string())?;
    if let Some(path) = &result {
        fs::remove_dir_all(&source).map_err(|error| format!("migration succeeded but source cleanup failed: {error}"))?;
        return Ok(MigrationResult { path: Some(path.to_string_lossy().into_owned()), requires_restart: true, restart_required: true });
    }
    Ok(MigrationResult { path: None, requires_restart: false, restart_required: false })
}

pub type KeyVaultState = Mutex<KeyVault>;
pub type HistoryState = Mutex<HistoryManager>;
pub type ClipboardState = Mutex<ClipboardManager>;
pub type CaptureState = Mutex<CaptureManager>;

pub(crate) fn lock_vault_state(state: &KeyVaultState) {
    state.lock().unwrap_or_else(|error| error.into_inner()).lock();
}

fn with_vault<T>(state: tauri::State<'_, KeyVaultState>, operation: impl FnOnce(&mut KeyVault) -> memopaws_keys::Result<T>) -> Result<T, String> {
    let mut vault = state.lock().map_err(|_| "key vault state is unavailable".to_string())?;
    operation(&mut vault).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn status(state: tauri::State<'_, KeyVaultState>) -> Result<VaultStatus, String> { with_vault(state, |vault| Ok(vault.status())) }

#[tauri::command]
pub fn unlock(password: String, state: tauri::State<'_, KeyVaultState>) -> Result<bool, String> {
    let password = Zeroizing::new(password);
    with_vault(state, |vault| vault.unlock(password.as_str()))
}

#[tauri::command]
pub fn lock(state: tauri::State<'_, KeyVaultState>) -> Result<(), String> { with_vault(state, |vault| { vault.lock(); Ok(()) }) }

#[tauri::command]
pub fn set_master(password: String, state: tauri::State<'_, KeyVaultState>) -> Result<(), String> {
    let password = Zeroizing::new(password);
    with_vault(state, |vault| vault.set_master(password.as_str()))
}

#[tauri::command]
pub fn remove_master(state: tauri::State<'_, KeyVaultState>) -> Result<(), String> { with_vault(state, KeyVault::remove_master) }

#[tauri::command]
pub fn list(state: tauri::State<'_, KeyVaultState>) -> Result<Vec<KeyEntry>, String> { with_vault(state, |vault| Ok(vault.list())) }

#[tauri::command]
pub fn key_list(state: tauri::State<'_, KeyVaultState>) -> Result<Vec<KeyEntry>, String> { list(state) }

#[tauri::command]
pub fn add(entry: KeyEntryInput, state: tauri::State<'_, KeyVaultState>) -> Result<KeyEntry, String> { with_vault(state, |vault| vault.add(entry)) }

#[tauri::command]
pub fn update(id: u64, entry: KeyEntryInput, state: tauri::State<'_, KeyVaultState>) -> Result<KeyEntry, String> { with_vault(state, |vault| vault.update(id, entry)) }

#[tauri::command]
pub fn delete(id: u64, state: tauri::State<'_, KeyVaultState>) -> Result<(), String> { with_vault(state, |vault| vault.delete(id)) }

#[tauri::command]
pub fn reorder(entry_type: String, ids: Vec<u64>, state: tauri::State<'_, KeyVaultState>) -> Result<(), String> { with_vault(state, |vault| vault.reorder(&entry_type, &ids)) }

#[tauri::command]
pub fn get_value(id: u64, state: tauri::State<'_, KeyVaultState>) -> Result<String, String> { with_vault(state, |vault| vault.get_value(id)) }

fn ai_client(state: tauri::State<'_, KeyVaultState>, key_entry_id: u64, model: String) -> Result<Client, String> {
    if model.trim().is_empty() || model.len() > 200 { return Err("model is required".into()); }
    let (entry, key) = {
        let vault = state.lock().map_err(|_| "key vault state is unavailable".to_string())?;
        let entry = vault.list().into_iter().find(|entry| entry.id == key_entry_id).ok_or_else(|| "key entry not found".to_string())?;
        if entry.entry_type != "llm" { return Err("selected key entry is not an LLM key".into()); }
        let key = Zeroizing::new(vault.get_value(key_entry_id).map_err(|error| error.to_string())?);
        (entry, key)
    };
    let config = ApiConfig::new(entry.url, model.trim(), key.as_str().to_owned());
    Ok(Client::new(config))
}

fn classify_api_error(error: &str) -> &'static str {
    let lower = error.to_ascii_lowercase();
    if lower.contains("timeout") || lower.contains("timed out") { "timeout" }
    else if lower.contains("401") || lower.contains("unauthorized") { "unauthorized" }
    else if lower.contains("404") || lower.contains("not found") { "not_found" }
    else if lower.contains("connect") || lower.contains("connection") || lower.contains("request failed") { "connect" }
    else if lower.contains("multimodal") || lower.contains("vision") || lower.contains("image") { "multimodal" }
    else { "generic" }
}

fn api_error_result(error: &str, elapsed_ms: u128) -> serde_json::Value {
    let kind = classify_api_error(error);
    let mut result = serde_json::json!({"error": kind, "elapsed_ms": elapsed_ms});
    if matches!(kind, "unauthorized" | "not_found") {
        let code = if kind == "unauthorized" { 401 } else { 404 };
        result["status_code"] = serde_json::json!(code);
    }
    result
}

fn multimodal_probe_image() -> &'static [u8] {
    // Minimal 1x1 PNG used only to test the provider's image capability.
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
}

#[tauri::command]
pub async fn test_api_connection(key_entry_id: Option<u64>, model: Option<String>, api_key: Option<String>, api_url: Option<String>, api_model: Option<String>, vault: tauri::State<'_, KeyVaultState>) -> Result<serde_json::Value, String> {
    let model = api_model.or(model).unwrap_or_default();
    if model.trim().is_empty() || model.len() > 200 { return Err("model is required".to_string()); }
    if let Some(key) = api_key.filter(|key| !key.trim().is_empty()) {
        let key = Zeroizing::new(key);
        let url = api_url.unwrap_or_default();
        let client = Client::with_timeout(ApiConfig::new(url, model.trim(), key.to_string()), Duration::from_secs(10)).map_err(|_| "API connection failed".to_string())?;
        let started = std::time::Instant::now();
        return match client.translate("connection test", Language::English, None).await {
            Ok(_) => {
                let vision_result = client.ocr(multimodal_probe_image()).await.is_ok();
                Ok(serde_json::json!({"status_code": 200, "elapsed_ms": started.elapsed().as_millis(), "vision_result": {"success": vision_result}}))
            }
            Err(error) => Ok(api_error_result(&error.to_string(), started.elapsed().as_millis())),
        };
    }
    let key_entry_id = key_entry_id.ok_or_else(|| "API key is required".to_string())?;
    let (entry, key) = {
        let vault = vault.lock().map_err(|_| "key vault state is unavailable".to_string())?;
        let entry = vault.list().into_iter().find(|entry| entry.id == key_entry_id).ok_or_else(|| "key entry not found".to_string())?;
        if entry.entry_type != "llm" { return Err("selected key entry is not an LLM key".to_string()); }
        let key = Zeroizing::new(vault.get_value(key_entry_id).map_err(|_| "API connection failed".to_string())?);
        (entry, key)
    };
    let client = Client::with_timeout(ApiConfig::new(entry.url, model.trim(), key.as_str().to_owned()), Duration::from_secs(10))
        .map_err(|_| "API connection failed".to_string())?;
    let started = std::time::Instant::now();
    match client.translate("connection test", Language::English, None).await {
        Ok(_) => {
            let vision_result = client.ocr(multimodal_probe_image()).await.is_ok();
            Ok(serde_json::json!({"status_code": 200, "elapsed_ms": started.elapsed().as_millis(), "vision_result": {"success": vision_result}}))
        }
        Err(error) => Ok(api_error_result(&error.to_string(), started.elapsed().as_millis())),
    }
}

#[tauri::command]
pub fn set_close_behavior(value: String, app: tauri::AppHandle) -> Result<(), String> {
    let mut config = memopaws_config::config::AppConfig::load().map_err(|error| error.to_string())?;
    validate_config_request(&serde_json::json!({"close_behavior": value}))?;
    config.close_behavior = Some(value.clone());
    config.save().map_err(|error| error.to_string())?;
    let _ = app.emit("close-behavior-changed", value);
    Ok(())
}

#[tauri::command]
pub fn set_floating_widget_visible(visible: bool, app: tauri::AppHandle) -> Result<(), String> {
    let mut config = memopaws_config::config::AppConfig::load().map_err(|error| error.to_string())?;
    config.show_floating_widget = Some(visible);
    config.save().map_err(|error| error.to_string())?;
    let _ = app.emit("floating-widget-visibility-changed", visible);
    Ok(())
}

#[tauri::command]
pub fn set_clipboard_max_items(value: usize, state: tauri::State<'_, ClipboardState>) -> Result<(), String> {
    validate_config_request(&serde_json::json!({"clipboard_max_items": value as u64}))?;
    state.lock().map_err(|_| "clipboard state is unavailable".to_string())?.set_max_items(value)
}

#[tauri::command]
pub fn set_history_max_items(value: usize, state: tauri::State<'_, HistoryState>) -> Result<(), String> {
    validate_config_request(&serde_json::json!({"history_max_items": value as u64}))?;
    state.lock().map_err(|_| "history state is unavailable".to_string())?.set_max_items(value).map_err(|error| error.to_string())
}

fn history_mut<T>(state: tauri::State<'_, HistoryState>, operation: impl FnOnce(&mut HistoryManager) -> memopaws_core::Result<T>) -> Result<T, String> {
    let mut history = state.lock().map_err(|_| "history state is unavailable".to_string())?;
    operation(&mut history).map_err(|_| "history operation failed".to_string())
}

#[tauri::command]
pub async fn ai_ocr(image: Vec<u8>, key_entry_id: u64, model: String, vault: tauri::State<'_, KeyVaultState>, history: tauri::State<'_, HistoryState>) -> Result<OcrResult, String> {
    let result = ai_client(vault, key_entry_id, model)?.ocr(&image).await.map_err(|error| error.to_string())?;
    history_mut(history, |manager| manager.add_success("ocr", &result.text, Some(&result.text), None))?;
    Ok(result)
}

#[tauri::command]
pub async fn ai_translate(text: String, target: Language, source: Option<Language>, key_entry_id: u64, model: String, vault: tauri::State<'_, KeyVaultState>, history: tauri::State<'_, HistoryState>) -> Result<TranslateResult, String> {
    if text.len() > 100_000 { return Err("translation input is too large".into()); }
    let result = ai_client(vault, key_entry_id, model)?.translate(&text, target, source).await.map_err(|error| error.to_string())?;
    history_mut(history, |manager| manager.add_success("translate", &result.text, Some(&text), Some(&result.text)))?;
    Ok(result)
}

#[tauri::command]
pub fn history_list(state: tauri::State<'_, HistoryState>) -> Result<Vec<HistoryRecord>, String> {
    history_mut(state, |manager| Ok(manager.records().to_vec()))
}

#[tauri::command]
pub fn history_delete(index: usize, state: tauri::State<'_, HistoryState>) -> Result<(), String> {
    history_mut(state, |manager| manager.delete_record(index))
}

#[tauri::command]
pub fn history_clear(state: tauri::State<'_, HistoryState>) -> Result<(), String> {
    history_mut(state, HistoryManager::clear)
}

fn clipboard_mut<T>(state: tauri::State<'_, ClipboardState>, operation: impl FnOnce(&mut ClipboardManager) -> Result<T, String>) -> Result<T, String> {
    let mut clipboard = state.lock().map_err(|_| "clipboard state is unavailable".to_string())?;
    operation(&mut clipboard)
}

#[tauri::command]
pub fn clipboard_list(state: tauri::State<'_, ClipboardState>) -> Result<Vec<ClipboardItem>, String> {
    clipboard_mut(state, |clipboard| Ok(clipboard.items().to_vec()))
}

#[tauri::command]
pub fn clipboard_delete(id: u64, state: tauri::State<'_, ClipboardState>) -> Result<(), String> {
    clipboard_mut(state, |clipboard| clipboard.delete(id))
}

#[tauri::command]
pub fn clipboard_clear(state: tauri::State<'_, ClipboardState>) -> Result<(), String> {
    clipboard_mut(state, ClipboardManager::clear)
}

#[tauri::command]
pub fn clipboard_get_image(id: u64, state: tauri::State<'_, ClipboardState>) -> Result<Vec<u8>, String> {
    clipboard_mut(state, |clipboard| clipboard.get_image_bytes(id))
}

fn capture_mut<T>(state: tauri::State<'_, CaptureState>, operation: impl FnOnce(&mut CaptureManager) -> Result<T, String>) -> Result<T, String> {
    let mut capture = state.lock().map_err(|_| "capture state is unavailable".to_string())?;
    operation(&mut capture)
}

#[tauri::command]
pub fn capture_list(state: tauri::State<'_, CaptureState>) -> Result<Vec<CaptureRecord>, String> {
    capture_mut(state, |capture| Ok(capture.records().to_vec()))
}

#[tauri::command]
pub fn capture_get_image(id: u64, state: tauri::State<'_, CaptureState>) -> Result<Vec<u8>, String> {
    capture_mut(state, |capture| capture.get_capture_bytes(id))
}

#[tauri::command]
pub fn capture_delete(id: u64, state: tauri::State<'_, CaptureState>) -> Result<(), String> {
    capture_mut(state, |capture| capture.delete(id))
}

#[cfg(test)]
mod tests {
    use std::{sync::{Arc, Mutex}, time::{SystemTime, UNIX_EPOCH}};

    use memopaws_keys::KeyVault;

    #[test]
    fn validate_theme_accepts_supported_values_and_rejects_unknown_values() {
        assert_eq!(super::validate_theme("dark").unwrap(), "dark");
        assert_eq!(super::validate_theme("light").unwrap(), "light");
        assert!(super::validate_theme("blue").is_err());
    }

    #[test]
    fn public_set_theme_validation_rejects_before_config_load_or_save() {
        // Boundary: this pure request validation is the first operation in set_theme;
        // invalid input cannot resolve, load, or save the real config path.
        assert_eq!(super::validate_set_theme_request(" light ".to_string()).unwrap(), "light");
        assert_eq!(super::validate_set_theme_request("dark".to_string()).unwrap(), "dark");
        assert_eq!(super::validate_set_theme_request("blue".to_string()).unwrap_err(), "theme must be dark or light");
    }

    #[test]
    fn theme_commands_persist_to_an_explicit_config_path() {
        let path = std::env::temp_dir().join(format!(
            "memopaws-theme-{}.json",
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos(),
        ));

        assert_eq!(super::get_theme_from(&path).unwrap(), "dark");
        super::set_theme_at(&path, " light ").unwrap();
        assert_eq!(super::get_theme_from(&path).unwrap(), "light");

        let before_invalid = std::fs::read_to_string(&path).unwrap();
        assert!(super::set_theme_at(&path, "blue").is_err());
        assert_eq!(std::fs::read_to_string(&path).unwrap(), before_invalid);
        assert_eq!(super::get_theme_from(&path).unwrap(), "light");

        let raw = std::fs::read_to_string(&path).unwrap().replace("\"theme\": \"light\"", "\"theme\": \"blue\"");
        std::fs::write(&path, raw).unwrap();
        assert_eq!(super::get_theme_from(&path).unwrap(), "dark");

        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn malformed_existing_theme_is_normalized_before_save() {
        let path = std::env::temp_dir().join(format!(
            "memopaws-theme-save-{}.json",
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos(),
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
        })).is_err());
        assert!(super::validate_config_request(&serde_json::json!({
            "api_url": "https://example.test/v1",
            "api_model": ""
        })).is_err());
        assert!(super::validate_config_request(&serde_json::json!({
            "clipboard_max_items": 0
        })).is_err());
        assert!(super::validate_config_request(&serde_json::json!({
            "close_behavior": "minimize"
        })).is_err());
        assert!(super::validate_config_request(&serde_json::json!({
            "show_floating_widget": "yes"
        })).is_err());
        assert!(super::validate_config_request(&serde_json::json!({
            "shortcuts": {"screenshot_ocr": ""}
        })).is_err());
        assert!(super::validate_config_request(&serde_json::json!({
            "shortcuts": {"screenshot_ocr": "not-a-shortcut"}
        })).is_err());
    }

    #[test]
    fn config_validation_accepts_supported_partial_updates() {
        assert!(super::validate_config_request(&serde_json::json!({
            "api_url": "https://example.test/v1/chat/completions",
            "api_model": "vision",
            "clipboard_max_items": 50,
            "history_max_items": 100,
            "close_behavior": "tray",
            "show_floating_widget": true,
            "shortcuts": {"screenshot_ocr": "Alt+X"}
        })).is_ok());
    }

    #[test]
    fn api_errors_are_replaced_with_a_safe_connection_message() {
        let error = super::classify_api_error("API returned HTTP 401: secret response");
        assert_eq!(error, "unauthorized");
        assert!(!error.contains("secret"));
    }

    #[test]
    fn config_response_removes_api_key_and_exposes_presence_only() {
        let value = super::safe_config_value(serde_json::json!({"api_key": "secret", "api_model": "vision"}), None);
        assert_eq!(value["has_api_key"], true);
        assert!(value.get("api_key").is_none());
        assert_eq!(value["api_model"], "vision");
    }

    #[test]
    fn migration_mode_accepts_merge_overwrite_and_cancel() {
        assert_eq!(super::migration_target(&serde_json::json!({"data_dir": "a"})).unwrap(), "a");
        assert_eq!(super::migration_target(&serde_json::json!({"path": "b"})).unwrap(), "b");
        assert_eq!(super::migration_mode("merge").unwrap(), memopaws_core::paths::MigrationMode::Merge);
        assert_eq!(super::migration_mode("overwrite").unwrap(), memopaws_core::paths::MigrationMode::Replace);
        assert_eq!(super::migration_mode("cancel").unwrap(), memopaws_core::paths::MigrationMode::Cancel);
        assert!(super::migration_mode("unexpected").is_err());
    }

    #[test]
    fn lock_vault_state_recovers_from_a_poisoned_mutex() {
        let path = std::env::temp_dir().join(format!(
            "memopaws-close-lock-{}.json",
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos(),
        ));
        let mut vault = KeyVault::load(&path).unwrap();
        vault.set_master("test-password").unwrap();
        let state = Arc::new(Mutex::new(vault));
        let poisoned = Arc::clone(&state);
        let _ = std::thread::spawn(move || {
            let _guard = poisoned.lock().unwrap();
            panic!("poison test mutex");
        }).join();

        super::lock_vault_state(&state);

        assert!(!state.lock().unwrap_or_else(|error| error.into_inner()).status().unlocked);
        let _ = std::fs::remove_file(path);
    }
}
