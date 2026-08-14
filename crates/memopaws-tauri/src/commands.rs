
use std::{collections::HashSet, path::Path, sync::{Arc, Mutex}, time::Duration};

use base64::{engine::general_purpose::STANDARD, Engine};
use image::{codecs::png::PngEncoder, DynamicImage};
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
use tauri::{Emitter, Manager};
use tauri_plugin_dialog::DialogExt;

use crate::hotkeys;
use crate::text_replacer::TextReplacer;

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

#[derive(Debug, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CaptureRegion {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CaptureResult {
    pub image: Vec<u8>,
    pub preview: String,
}

#[tauri::command]
pub async fn capture_screen(region: Option<CaptureRegion>, display_index: Option<usize>) -> Result<CaptureResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let monitors = xcap::Monitor::all().map_err(|error| format!("screen capture failed: {error}"))?;
        // An explicit index selects that display; omitting it falls back to the primary display.
        let monitor = match display_index {
            Some(index) => monitors.get(index).ok_or_else(|| format!("display index {index} is out of range"))?,
            None => monitors
                .iter()
                .find(|monitor| monitor.is_primary().unwrap_or(false))
                .or_else(|| monitors.first())
                .ok_or_else(|| "no display available for capture".to_string())?,
        };
        let image = match region {
            Some(region) => {
                if region.width == 0 || region.height == 0 { return Err("capture region width and height must be positive".to_string()); }
                monitor.capture_region(region.x, region.y, region.width, region.height).map_err(|error| format!("screen capture failed: {error}"))?
            }
            None => monitor.capture_image().map_err(|error| format!("screen capture failed: {error}"))?,
        };
        let mut png = Vec::new();
        DynamicImage::ImageRgba8(image).write_with_encoder(PngEncoder::new(&mut png))
            .map_err(|error| format!("screen capture failed: {error}"))?;
        Ok(CaptureResult { image: png.clone(), preview: format!("data:image/png;base64,{}", STANDARD.encode(&png)) })
    })
    .await
    .map_err(|error| format!("screen capture task failed: {error}"))?
}

#[derive(Debug, serde::Serialize)]
pub struct ImageResult {
    pub image: Vec<u8>,
}

const DEFAULT_MOSAIC_BLOCK: u32 = 12;

// The frontend reads `result.image`, so this must stay an object, not a bare array.
#[tauri::command]
pub fn image_preprocess(image: Vec<u8>, mode: String) -> Result<ImageResult, String> {
    let processed = match mode.as_str() {
        "gray" => memopaws_ocr::image_util::grayscale_png(&image).map_err(|error| error.to_string())?,
        "binary" => memopaws_ocr::image_util::otsu_binary_png(&image).map_err(|error| error.to_string())?,
        "mosaic" => memopaws_ocr::image_util::mosaic_png(&image, DEFAULT_MOSAIC_BLOCK).map_err(|error| error.to_string())?,
        _ => return Err(format!("unsupported preprocess mode: {mode}")),
    };
    Ok(ImageResult { image: processed })
}

#[tauri::command]
pub fn image_mosaic_region(image: Vec<u8>, block: Option<u32>, x: u32, y: u32, width: u32, height: u32) -> Result<ImageResult, String> {
    if width == 0 || height == 0 {
        return Err("mosaic region width and height must be positive".to_string());
    }
    let block = block.unwrap_or(DEFAULT_MOSAIC_BLOCK);
    memopaws_ocr::image_util::mosaic_region_png(&image, block, x, y, width, height)
        .map(|image| ImageResult { image })
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn image_crop(image: Vec<u8>, x: u32, y: u32, width: u32, height: u32) -> Result<ImageResult, String> {
    memopaws_ocr::image_util::crop_png(&image, x, y, width, height)
        .map(|image| ImageResult { image })
        .map_err(|error| error.to_string())
}

#[derive(Debug, serde::Serialize)]
pub struct DisplayInfo {
    pub index: usize,
    pub name: String,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    pub is_primary: bool,
}

#[tauri::command]
pub fn list_displays() -> Result<Vec<DisplayInfo>, String> {
    let monitors = xcap::Monitor::all().map_err(|error| format!("failed to enumerate displays: {error}"))?;
    Ok(monitors
        .iter()
        .enumerate()
        .map(|(index, monitor)| DisplayInfo {
            index,
            name: monitor.name().unwrap_or_else(|_| format!("Display {}", index + 1)),
            x: monitor.x().unwrap_or(0),
            y: monitor.y().unwrap_or(0),
            width: monitor.width().unwrap_or(0),
            height: monitor.height().unwrap_or(0),
            is_primary: monitor.is_primary().unwrap_or(false),
        })
        .collect())
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
    let has_vault_key = lock_recover!(vault)
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
    if let Some(replacements) = config.get("text_replacements") {
        let replacements: Vec<memopaws_config::config::TextReplacement> = serde_json::from_value(replacements.clone())
            .map_err(|_| "text_replacements must be an array of replacement rules".to_string())?;
        validate_text_replacements(&replacements)?;
    }
    Ok(())
}

pub(crate) fn validate_text_replacements(replacements: &[memopaws_config::config::TextReplacement]) -> Result<(), String> {
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
pub fn set_language(language: String, app: tauri::AppHandle) -> Result<(), String> {
    let language = language.trim();
    if !matches!(language, "zh" | "en") {
        return Err("language must be zh or en".to_string());
    }
    let path = memopaws_core::paths::config_path().map_err(|error| error.to_string())?;
    let mut config = memopaws_config::config::AppConfig::load_from(&path).map_err(|error| error.to_string())?;
    config.language = Some(language.to_string());
    config.save_to(&path).map_err(|error| error.to_string())?;
    crate::tray::setup_tray(&app).map_err(|error| error.to_string())
}

#[tauri::command]
pub async fn save_config(config: serde_json::Value, vault: tauri::State<'_, KeyVaultState>, history: tauri::State<'_, HistoryState>, clipboard: tauri::State<'_, ClipboardState>, text_replacer: tauri::State<'_, Arc<TextReplacerState>>, app: tauri::AppHandle) -> Result<(), String> {
    // Async so the vault I/O, hotkey re-registration and config writes never block the UI.
    let config = config.get("config").cloned().unwrap_or(config);
    validate_config_request(&config)?;
    if let Some(key) = config.get("api_key").and_then(|value| value.as_str()).filter(|key| !key.trim().is_empty()) {
        if !lock_recover!(vault).status().unlocked {
            return Err("key vault is locked; unlock it on the Keys page before saving an API key".to_string());
        }
        let model = config.get("api_model").and_then(|value| value.as_str()).unwrap_or("glm-4-flash");
        save_settings_key(&vault, key, config.get("api_url").and_then(|value| value.as_str()).unwrap_or_default(), model)?;
    }
    let config_path = memopaws_core::paths::config_path().map_err(|e| e.to_string())?;
    let mut merged = memopaws_config::config::AppConfig::load_from(&config_path).map_err(|error| error.to_string())?;
    let previous_shortcuts = merged.shortcuts.clone();
    apply_config_patch(&mut merged, &config)?;
    if merged.shortcuts != previous_shortcuts {
        let shortcuts = merged.shortcuts.clone().unwrap_or_default();
        hotkeys::register_shortcuts(&app, shortcuts)?;
    }
    merged.save_to(&config_path).map_err(|error| error.to_string())?;
    if config.get("text_replacements").is_some() {
        *lock_recover!(text_replacer.rules) = merged.text_replacements.clone();
    }
    if let Some(max) = config.get("history_max_items").and_then(|value| value.as_u64()) {
        lock_recover!(history).set_max_items(max as usize).map_err(|error| error.to_string())?;
    }
    if let Some(max) = config.get("clipboard_max_items").and_then(|value| value.as_u64()) {
        lock_recover!(clipboard).set_max_items(max as usize)?;
    }
    if let Some(value) = config.get("close_behavior").and_then(|value| value.as_str()) { let _ = app.emit("close-behavior-changed", value); }
    if let Some(value) = config.get("show_floating_widget").and_then(|value| value.as_bool()) { let _ = app.emit("floating-widget-visibility-changed", value); }
    Ok(())
}

#[cfg(test)]
fn save_config_at(path: &std::path::Path, config: serde_json::Value) -> Result<(), String> {
    validate_config_request(&config)?;
    let mut app_config = memopaws_config::config::AppConfig::load_from(path).map_err(|error| error.to_string())?;
    normalize_theme(&mut app_config);
    apply_config_patch(&mut app_config, &config)?;
    app_config.api_key = None;
    app_config.save_to(path).map_err(|error| error.to_string())
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
    if let Some(replacements) = config.get("text_replacements") {
        app_config.text_replacements = serde_json::from_value(replacements.clone())
            .map_err(|_| "text_replacements must be an array of replacement rules".to_string())?;
    }
    Ok(())
}

fn save_settings_key(state: &tauri::State<'_, KeyVaultState>, key: &str, url: &str, model: &str) -> Result<(), String> {
    let mut vault = lock_recover!(state);
    let note = if model.trim().is_empty() { "glm-4-flash".to_string() } else { model.trim().to_string() };
    let input = || KeyEntryInput { name: "settings_api_key".into(), entry_type: "llm".into(), value: key.to_owned(), url: url.to_owned(), url_anthropic: String::new(), note: note.clone() };
    let existing = vault.list().into_iter().find(|entry| entry.name == "settings_api_key" && entry.entry_type == "llm");
    if let Some(entry) = existing { vault.update(entry.id, input()).map_err(|_| "API key could not be stored securely".to_string())?; }
    else { vault.add(input()).map_err(|_| "API key could not be stored securely".to_string())?; }
    Ok(())
}

#[tauri::command]
pub fn get_data_dir() -> Result<String, String> {
    // UI shows the base directory (parent of `.memopaws-rust`), matching migration targets.
    memopaws_core::paths::data_base_dir()
        .map(|path| path.to_string_lossy().into_owned())
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub async fn choose_data_dir(app: tauri::AppHandle) -> Result<Option<String>, String> {
    let handle = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        handle
            .dialog()
            .file()
            .blocking_pick_folder()
            .map(|path| path.to_string())
    })
    .await
    .map_err(|error| format!("folder dialog failed: {error}"))
}

#[tauri::command]
pub fn get_storage_dir_conflict(path: String) -> Result<bool, String> {
    let path = path.trim();
    if path.is_empty() {
        return Ok(false);
    }
    memopaws_core::paths::storage_dir_conflict(Path::new(path)).map_err(|error| error.to_string())
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
pub async fn migrate_data_dir(
    data_dir: Option<String>,
    path: Option<String>,
    mode: Option<String>,
) -> Result<MigrationResult, String> {
    let args = serde_json::json!({"data_dir": data_dir, "path": path});
    let target = migration_target(&args)?;
    let mode = migration_mode(mode.as_deref().unwrap_or("merge"))?;
    // Do NOT delete the source tree while managers still hold old paths.
    // Anchor update is enough; leftover source is cleaned on a later launch if desired.
    tauri::async_runtime::spawn_blocking(move || {
        let result = memopaws_core::paths::migrate_data_dir(Path::new(&target), mode)
            .map_err(|error| error.to_string())?;
        if let Some(new_path) = &result {
            return Ok(MigrationResult {
                path: Some(new_path.to_string_lossy().into_owned()),
                requires_restart: true,
                restart_required: true,
            });
        }
        Ok(MigrationResult {
            path: None,
            requires_restart: false,
            restart_required: false,
        })
    })
    .await
    .map_err(|error| format!("migration task failed: {error}"))?
}

#[tauri::command]
pub fn restart_app(app: tauri::AppHandle) {
    app.restart();
}

pub type KeyVaultState = Mutex<KeyVault>;
pub type HistoryState = Mutex<HistoryManager>;
pub type ClipboardState = Mutex<ClipboardManager>;
pub type CaptureState = Mutex<CaptureManager>;

/// Acquire a state lock and recover from poisoning instead of failing the
/// command. A transient panic elsewhere must never permanently brick UI flows
/// with "… state is unavailable"; the recovered guard mirrors the recovery that
/// `lock_vault_state` already performs when the window closes.
macro_rules! lock_recover {
    ($lock:expr) => {
        ($lock).lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    };
}
use lock_recover;

pub struct TextReplacerState {
    pub machine: Mutex<TextReplacer>,
    pub rules: Mutex<Vec<memopaws_config::config::TextReplacement>>,
}

impl TextReplacerState {
    pub fn new(rules: Vec<memopaws_config::config::TextReplacement>) -> Self {
        Self { machine: Mutex::new(TextReplacer::default()), rules: Mutex::new(rules) }
    }
}

#[tauri::command]
pub fn text_replacement_list(state: tauri::State<'_, Arc<TextReplacerState>>) -> Result<Vec<memopaws_config::config::TextReplacement>, String> {
    Ok(lock_recover!(state.rules).clone())
}

#[tauri::command]
pub fn text_replacement_create(rule: memopaws_config::config::TextReplacement, state: tauri::State<'_, Arc<TextReplacerState>>) -> Result<(), String> {
    let mut rules = lock_recover!(state.rules);
    let mut updated = rules.clone();
    updated.push(rule);
    validate_text_replacements(&updated)?;
    persist_text_replacements(&updated)?;
    *rules = updated;
    Ok(())
}

#[tauri::command]
pub fn text_replacement_update(abbr: String, rule: memopaws_config::config::TextReplacement, state: tauri::State<'_, Arc<TextReplacerState>>) -> Result<(), String> {
    let mut rules = lock_recover!(state.rules);
    let index = rules.iter().position(|item| item.abbr == abbr).ok_or_else(|| "text replacement not found".to_string())?;
    let mut updated = rules.clone();
    updated[index] = rule;
    validate_text_replacements(&updated)?;
    persist_text_replacements(&updated)?;
    *rules = updated;
    Ok(())
}

#[tauri::command]
pub fn text_replacement_delete(abbr: String, state: tauri::State<'_, Arc<TextReplacerState>>) -> Result<(), String> {
    let mut rules = lock_recover!(state.rules);
    let before = rules.len();
    let mut updated = rules.clone();
    updated.retain(|item| item.abbr != abbr);
    if updated.len() == before { return Err("text replacement not found".to_string()); }
    persist_text_replacements(&updated)?;
    *rules = updated;
    Ok(())
}

fn persist_text_replacements(rules: &[memopaws_config::config::TextReplacement]) -> Result<(), String> {
    let mut config = memopaws_config::config::AppConfig::load().map_err(|error| error.to_string())?;
    config.text_replacements = rules.to_vec();
    config.save().map_err(|error| error.to_string())
}

pub(crate) fn lock_vault_state(state: &KeyVaultState) {
    state.lock().unwrap_or_else(|error| error.into_inner()).lock();
}

fn with_vault<T>(state: tauri::State<'_, KeyVaultState>, operation: impl FnOnce(&mut KeyVault) -> memopaws_keys::Result<T>) -> Result<T, String> {
    let mut vault = lock_recover!(state);
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

fn ai_client(state: tauri::State<'_, KeyVaultState>, key_entry_id: u64, model: Option<String>) -> Result<Client, String> {
    let (entry, key) = {
        let vault = lock_recover!(state);
        let entry = vault.list().into_iter().find(|entry| entry.id == key_entry_id).ok_or_else(|| "key entry not found".to_string())?;
        if entry.entry_type != "llm" { return Err("selected key entry is not an LLM key".into()); }
        let key = Zeroizing::new(vault.get_value(key_entry_id).map_err(|error| error.to_string())?);
        (entry, key)
    };
    resolve_ai_config(entry, key, model).map(Client::new)
}

fn resolve_ai_config(entry: KeyEntry, key: Zeroizing<String>, requested_model: Option<String>) -> Result<ApiConfig, String> {
    let model = if entry.name == "settings_api_key" {
        (!entry.note.trim().is_empty() && entry.note != "Settings API key")
            .then_some(entry.note)
            .or(requested_model.filter(|model| !model.trim().is_empty() && model != "Settings API key"))
            .or_else(|| memopaws_config::config::AppConfig::load().ok().and_then(|config| config.api_model))
            .unwrap_or_else(|| "glm-4-flash".to_string())
    } else {
        entry.note
    };
    let model = model.trim();
    if model.is_empty() || model.len() > 200 { return Err("model is required".into()); }
    Ok(ApiConfig::new(entry.url, model, key.to_string()))
}

fn safe_ai_command_error(error: &str) -> String {
    if classify_api_error(error) == "unauthorized" {
        "API authorization failed. Check the selected key and endpoint, then try again.".into()
    } else {
        error.into()
    }
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

// Bounded so the UI never appears frozen: reachability probe plus a shorter vision probe.
const API_PROBE_TIMEOUT: Duration = Duration::from_secs(8);

// The probe reuses the same OCR path as real image recognition, so a working
// AI key/vision model is verified through the exact endpoint the app uses.
// A text-only probe runs first to validate the key/model, then a vision probe
// decides whether the model is multimodal.
async fn run_api_probe(config: ApiConfig) -> Result<serde_json::Value, String> {
    let client = Client::with_timeout(config, API_PROBE_TIMEOUT)
        .map_err(|_| "API connection failed".to_string())?;
    let started = std::time::Instant::now();
    let text_result = client.translate("ping", Language::English, Some(Language::Chinese)).await;
    let elapsed = started.elapsed().as_millis();
    match text_result {
        Ok(_) => {
            let vision_ok = client.ocr(multimodal_probe_image()).await.is_ok();
            Ok(serde_json::json!({"status_code": 200, "elapsed_ms": elapsed, "vision_result": {"success": vision_ok}}))
        }
        Err(error) => Ok(api_error_result(&error.to_string(), elapsed)),
    }
}

#[tauri::command]
pub async fn test_api_connection(key_entry_id: Option<u64>, model: Option<String>, api_key: Option<String>, api_url: Option<String>, api_model: Option<String>, vault: tauri::State<'_, KeyVaultState>) -> Result<serde_json::Value, String> {
    let model = api_model.or(model).unwrap_or_default();
    if let Some(key) = api_key.filter(|key| !key.trim().is_empty()) {
        let model = model.trim();
        if model.is_empty() || model.len() > 200 { return Err("model is required".to_string()); }
        let key = Zeroizing::new(key);
        return run_api_probe(ApiConfig::new(api_url.unwrap_or_default(), model, key.to_string())).await;
    }
    // No inline key: fall back to the saved settings entry so a stored key still tests.
    let config = {
        let vault = lock_recover!(vault);
        if !vault.status().unlocked {
            return Err("key vault is locked, unlock it first".to_string());
        }
        let entries = vault.list();
        let entry = match key_entry_id {
            Some(id) => entries.into_iter().find(|entry| entry.id == id).ok_or_else(|| "key entry not found".to_string())?,
            None => entries
                .into_iter()
                .find(|entry| entry.name == "settings_api_key" && entry.entry_type == "llm")
                .ok_or_else(|| "API key is required".to_string())?,
        };
        if entry.entry_type != "llm" { return Err("selected key entry is not an LLM key".to_string()); }
        let key = Zeroizing::new(vault.get_value(entry.id).map_err(|_| "API connection failed".to_string())?);
        resolve_ai_config(entry, key, Some(model.clone()))?
    };
    run_api_probe(config).await
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
pub fn show_main_window_when_ready(app: tauri::AppHandle) -> Result<(), String> {
    let window = app.get_webview_window("main").ok_or_else(|| "main window not found".to_string())?;
    window.show().map_err(|error| error.to_string())?;
    window.set_focus().map_err(|error| error.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn set_floating_widget_visible(visible: bool, app: tauri::AppHandle) -> Result<(), String> {
    let mut config = memopaws_config::config::AppConfig::load().map_err(|error| error.to_string())?;
    config.show_floating_widget = Some(visible);
    config.save().map_err(|error| error.to_string())?;
    if visible {
        let window = app.get_webview_window("floating").ok_or_else(|| "floating window not found".to_string())?;
        window.show().map_err(|error| format!("failed to show floating window: {error}"))?;
        window.set_focus().map_err(|error| format!("failed to focus floating window: {error}"))?;
    } else if let Some(window) = app.get_webview_window("floating") {
        window.hide().map_err(|error| format!("failed to hide floating window: {error}"))?;
    }
    let _ = app.emit("floating-widget-visibility-changed", visible);
    Ok(())
}

#[tauri::command]
pub fn set_clipboard_max_items(value: usize, state: tauri::State<'_, ClipboardState>) -> Result<(), String> {
    validate_config_request(&serde_json::json!({"clipboard_max_items": value as u64}))?;
    lock_recover!(state).set_max_items(value)
}

#[tauri::command]
pub fn set_history_max_items(value: usize, state: tauri::State<'_, HistoryState>) -> Result<(), String> {
    validate_config_request(&serde_json::json!({"history_max_items": value as u64}))?;
    lock_recover!(state).set_max_items(value).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn clipboard_paste_image(state: tauri::State<'_, ClipboardState>, app: tauri::AppHandle) -> Result<(), String> {
    let mut clipboard = arboard::Clipboard::new().map_err(|error| format!("clipboard access failed: {error}"))?;
    let bytes = match clipboard.get_image() {
        Ok(image) => {
            let raw = image::RgbaImage::from_raw(
                image.width as u32,
                image.height as u32,
                image.bytes.as_ref().to_vec(),
            ).ok_or_else(|| "invalid clipboard image dimensions".to_string())?;
            let mut bytes = Vec::new();
            raw.write_to(&mut std::io::Cursor::new(&mut bytes), image::ImageFormat::Png)
                .map_err(|error| format!("image encoding failed: {error}"))?;
            bytes
        }
        Err(_) => memopaws_clipboard::read_file_list_image().or_else(|| {
            clipboard.get_text().ok().and_then(|text| memopaws_clipboard::read_image_path(&text))
        }).ok_or_else(|| "no image or supported image file in clipboard".to_string())?,
    };
    lock_recover!(state).add_image(&bytes)
        .map_err(|error| format!("failed to save clipboard image: {error}"))?;
    // Manual paste does not pass through the listener, so notify the frontend here.
    // The listener callbacks emit the same event for automatically captured content.
    let _ = app.emit("clipboard-changed", serde_json::json!({}));
    Ok(())
}

fn history_mut<T>(state: tauri::State<'_, HistoryState>, operation: impl FnOnce(&mut HistoryManager) -> memopaws_core::Result<T>) -> Result<T, String> {
    let mut history = lock_recover!(state);
    operation(&mut history).map_err(|_| "history operation failed".to_string())
}

#[tauri::command]
pub async fn ai_ocr(image: Vec<u8>, key_entry_id: u64, model: Option<String>, vault: tauri::State<'_, KeyVaultState>, history: tauri::State<'_, HistoryState>) -> Result<OcrResult, String> {
    let result = ai_client(vault, key_entry_id, model)?.ocr(&image).await.map_err(|error| safe_ai_command_error(&error.to_string()))?;
    history_mut(history, |manager| manager.add_success("ocr", &result.text, Some(&result.text), None))?;
    Ok(result)
}

#[tauri::command]
pub async fn ai_translate(text: String, target: Language, source: Option<Language>, key_entry_id: u64, model: Option<String>, vault: tauri::State<'_, KeyVaultState>, history: tauri::State<'_, HistoryState>) -> Result<TranslateResult, String> {
    if text.len() > 100_000 { return Err("translation input is too large".into()); }
    let result = ai_client(vault, key_entry_id, model)?.translate(&text, target, source).await.map_err(|error| safe_ai_command_error(&error.to_string()))?;
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
    let mut clipboard = lock_recover!(state);
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

#[tauri::command]
pub fn clipboard_set_locked(id: u64, locked: bool, state: tauri::State<'_, ClipboardState>) -> Result<(), String> {
    clipboard_mut(state, |clipboard| clipboard.set_locked(id, locked))
}

#[tauri::command]
pub fn clipboard_update_text(id: u64, text: String, state: tauri::State<'_, ClipboardState>) -> Result<(), String> {
    clipboard_mut(state, |clipboard| clipboard.update_text(id, &text))
}

#[tauri::command]
pub fn clipboard_delete_many(ids: Vec<u64>, state: tauri::State<'_, ClipboardState>) -> Result<usize, String> {
    clipboard_mut(state, |clipboard| clipboard.delete_many(&ids))
}

fn memo_global_search_results(query: &str, memos: &[Memo]) -> Vec<serde_json::Value> {
    if query.trim().is_empty() {
        return Vec::new();
    }
    search::search_memos(memos, query)
        .into_iter()
        .map(|result| {
            let memo = result.memo;
            serde_json::json!({
                "source": "memo",
                "id": memo.id,
                "title": memo.title,
                "text": memo.content,
                "time": memo.time,
            })
        })
        .collect()
}

#[tauri::command]
pub fn global_search(query: String, clipboard: tauri::State<'_, ClipboardState>, history: tauri::State<'_, HistoryState>) -> Result<Vec<serde_json::Value>, String> {
    let query = query.trim().to_lowercase();
    if query.is_empty() { return Ok(Vec::new()); }
    let mut results = Vec::new();
    let clipboard = lock_recover!(clipboard);
    for item in clipboard.items() {
        let text = item.text.clone().unwrap_or_else(|| "[image]".into());
        if text.to_lowercase().contains(&query) {
            results.push(serde_json::json!({ "source": "clipboard", "id": item.id, "title": "Clipboard", "text": text, "time": item.time }));
        }
    }
    let history = lock_recover!(history);
    for (index, item) in history.records().iter().enumerate() {
        if item.text.to_lowercase().contains(&query) {
            results.push(serde_json::json!({ "source": "history", "id": index, "title": item.typ, "text": item.text, "time": item.time }));
        }
    }
    results.extend(memo_global_search_results(&query, &memo_list()?));
    Ok(results)
}

fn capture_mut<T>(state: tauri::State<'_, CaptureState>, operation: impl FnOnce(&mut CaptureManager) -> Result<T, String>) -> Result<T, String> {
    let mut capture = lock_recover!(state);
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

    use memopaws_keys::{KeyEntryInput, KeyVault};
    use memopaws_memo::model::Memo;
    use zeroize::Zeroizing;

    #[test]
    fn memo_global_search_returns_empty_for_empty_query() {
        let memos = vec![Memo { title: "Visible".into(), content: "body".into(), ..Memo::default() }];

        assert_eq!(super::memo_global_search_results(" ", &memos), Vec::<serde_json::Value>::new());
    }

    #[test]
    fn memo_global_search_returns_the_unified_memo_source_shape() {
        let memos = vec![Memo {
            id: 7,
            time: "2026-08-05T12:00:00Z".into(),
            title: "Release notes".into(),
            content: "Memo body".into(),
            file: Some("internal-file-path".into()),
            ..Memo::default()
        }];

        let results = super::memo_global_search_results("body", &memos);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0], serde_json::json!({
            "source": "memo",
            "id": 7,
            "title": "Release notes",
            "text": "Memo body",
            "time": "2026-08-05T12:00:00Z"
        }));
        assert!(results[0].get("keys").is_none());
        assert!(results[0].get("secret").is_none());
    }

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
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos(),
        ));
        memopaws_config::config::AppConfig::default().save_to(&path).unwrap();

        super::save_config_at(&path, serde_json::json!({
            "text_replacements": [{"abbr": ":brb", "replacement": "be right back"}]
        })).unwrap();

        let saved = memopaws_config::config::AppConfig::load_from(&path).unwrap();
        assert_eq!(saved.text_replacements.len(), 1);
        assert_eq!(saved.text_replacements[0].abbr, ":brb");
        assert_eq!(saved.text_replacements[0].replacement, "be right back");
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn api_errors_are_replaced_with_a_safe_connection_message() {
        let error = super::classify_api_error("API returned HTTP 401: secret response");
        assert_eq!(error, "unauthorized");
        assert!(!error.contains("secret"));
    }

    #[test]
    fn ai_config_uses_a_normal_llm_entrys_stored_endpoint_and_model() {
        let entry = memopaws_keys::KeyEntry {
            id: 7,
            name: "Vision provider".into(),
            entry_type: "llm".into(),
            url: "https://vision.example.test/v1".into(),
            url_anthropic: String::new(),
            note: "vision-model".into(),
            order: 0,
            created: String::new(),
        };

        let config = super::resolve_ai_config(entry, Zeroizing::new("test-secret".into()), None).unwrap();

        assert_eq!(config.endpoint(), "https://vision.example.test/v1/chat/completions");
        assert_eq!(config.model(), "vision-model");
        assert!(!format!("{config:?}").contains("test-secret"));
    }

    #[test]
    fn test_connection_rejects_a_normal_llm_entry_without_a_persisted_model() {
        let entry = memopaws_keys::KeyEntry {
            id: 9,
            name: "Vision provider".into(),
            entry_type: "llm".into(),
            url: "https://vision.example.test/v1".into(),
            url_anthropic: String::new(),
            note: "   ".into(),
            order: 0,
            created: String::new(),
        };

        let error = super::resolve_ai_config(
            entry,
            Zeroizing::new("test-secret".into()),
            Some("frontend-model".into()),
        ).unwrap_err();

        assert_eq!(error, "model is required");
    }

    #[test]
    fn ai_config_keeps_a_settings_entrys_persisted_model() {
        let entry = memopaws_keys::KeyEntry {
            id: 8,
            name: "settings_api_key".into(),
            entry_type: "llm".into(),
            url: "https://settings.example.test/v1".into(),
            url_anthropic: String::new(),
            note: "settings-vision-model".into(),
            order: 0,
            created: String::new(),
        };

        let config = super::resolve_ai_config(entry, Zeroizing::new("test-secret".into()), Some("frontend-fixed-model".into())).unwrap();

        assert_eq!(config.endpoint(), "https://settings.example.test/v1/chat/completions");
        assert_eq!(config.model(), "settings-vision-model");
    }

    #[test]
    fn unauthorized_ai_errors_are_generic_and_actionable() {
        let message = super::safe_ai_command_error("API returned HTTP 401: provider response containing a secret");

        assert_eq!(message, "API authorization failed. Check the selected key and endpoint, then try again.");
        assert!(!message.contains("secret"));
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

    #[test]
    fn api_error_classification_covers_all_categories() {
        assert_eq!(super::classify_api_error("request timed out"), "timeout");
        assert_eq!(super::classify_api_error("API returned HTTP 401"), "unauthorized");
        assert_eq!(super::classify_api_error("404 not found"), "not_found");
        assert_eq!(super::classify_api_error("connection refused"), "connect");
        assert_eq!(super::classify_api_error("request failed: hyper error"), "connect");
        assert_eq!(super::classify_api_error("model does not support vision"), "multimodal");
        assert_eq!(super::classify_api_error("image decode error"), "multimodal");
        assert_eq!(super::classify_api_error("something else"), "generic");
    }

    #[test]
    fn api_error_result_attaches_status_codes_only_when_meaningful() {
        let unauthorized = super::api_error_result("HTTP 401 unauthorized", 12);
        assert_eq!(unauthorized["error"], "unauthorized");
        assert_eq!(unauthorized["status_code"], 401);
        assert_eq!(unauthorized["elapsed_ms"], 12);

        let missing = super::api_error_result("404 not found", 3);
        assert_eq!(missing["status_code"], 404);

        let timeout = super::api_error_result("timed out", 8000);
        assert!(timeout.get("status_code").is_none());
    }

    #[test]
    fn config_response_reports_missing_or_null_api_keys_as_absent() {
        let null_key = super::safe_config_value(serde_json::json!({"api_key": null, "api_model": "vision"}), None);
        assert_eq!(null_key["has_api_key"], false);
        assert!(null_key.get("api_key").is_none());

        let empty_key = super::safe_config_value(serde_json::json!({"api_key": "", "api_model": "vision"}), None);
        assert_eq!(empty_key["has_api_key"], false);

        let forced = super::safe_config_value(serde_json::json!({"api_key": "hidden"}), Some(true));
        assert_eq!(forced["has_api_key"], true);
        assert!(forced.get("api_key").is_none());
    }

    #[test]
    fn shortcut_validation_allows_empty_only_for_toggle_clipboard() {
        assert!(super::validate_config_request(&serde_json::json!({"shortcuts": {"toggle_clipboard": ""}})).is_ok());
        assert!(super::validate_config_request(&serde_json::json!({"shortcuts": {"toggle_clipboard": "Alt+V"}})).is_ok());
        assert!(super::validate_config_request(&serde_json::json!({"shortcuts": {"capture": ""}})).is_err());
        assert!(super::validate_config_request(&serde_json::json!({"shortcuts": {"capture": "Ctrl+Alt+Shift+Meta+X+Y+Z"}})).is_err());
        assert!(super::validate_config_request(&serde_json::json!({"shortcuts": {"capture": "Ctrl+ "}})).is_err());
        assert!(super::validate_config_request(&serde_json::json!({"shortcuts": {"capture": "Ctrl+"}})).is_err());
        assert!(super::validate_config_request(&serde_json::json!({"shortcuts": {"capture": "Ctrl+Alt"}})).is_ok());
    }

    #[test]
    fn migration_target_requires_a_non_empty_string() {
        assert!(super::migration_target(&serde_json::json!({})).is_err());
        assert!(super::migration_target(&serde_json::json!({"data_dir": null})).is_err());
        assert!(super::migration_target(&serde_json::json!({"data_dir": "   "})).is_err());
        assert!(super::migration_target(&serde_json::json!({"path": 42})).is_err());
        assert_eq!(super::migration_target(&serde_json::json!({"path": " d:\\data "})).unwrap(), "d:\\data");
    }

    #[test]
    fn migration_mode_is_case_insensitive_and_accepts_aliases() {
        assert_eq!(super::migration_mode("MERGE").unwrap(), memopaws_core::paths::MigrationMode::Merge);
        assert_eq!(super::migration_mode("Overwrite").unwrap(), memopaws_core::paths::MigrationMode::Replace);
        assert_eq!(super::migration_mode("move").unwrap(), memopaws_core::paths::MigrationMode::Replace);
        assert_eq!(super::migration_mode("Cancel").unwrap(), memopaws_core::paths::MigrationMode::Cancel);
        assert_eq!(super::migration_mode(" delete ").unwrap_err(), "migration mode must be merge, overwrite, or cancel");
    }

    #[test]
    fn config_patch_updates_every_supported_field() {
        let mut config = memopaws_config::config::AppConfig::default();
        super::apply_config_patch(&mut config, &serde_json::json!({
            "language": "en",
            "close_behavior": "exit",
            "clipboard_max_items": 60,
            "history_max_items": 200,
            "api_url": " https://example.test/v1 ",
            "api_model": " model-x ",
            "show_floating_widget": false,
            "shortcuts": {"capture": "Ctrl+Shift+C", "screenshot_ocr": "Ctrl+Shift+D"},
            "text_replacements": [{"abbr": ":w", "replacement": "welcome"}]
        })).unwrap();

        assert_eq!(config.language.as_deref(), Some("en"));
        assert_eq!(config.close_behavior.as_deref(), Some("exit"));
        assert_eq!(config.clipboard_max_items, Some(60));
        assert_eq!(config.history_max_items, Some(200));
        assert_eq!(config.api_url.as_deref(), Some("https://example.test/v1"));
        assert_eq!(config.api_model.as_deref(), Some("model-x"));
        assert_eq!(config.show_floating_widget, Some(false));
        assert_eq!(config.shortcuts.as_ref().unwrap()["capture"], "Ctrl+Shift+C");
        assert_eq!(config.shortcuts.as_ref().unwrap()["screenshot_ocr"], "Ctrl+Shift+D");
        assert_eq!(config.text_replacements[0].abbr, ":w");

        super::apply_config_patch(&mut config, &serde_json::json!({})).unwrap();
        assert_eq!(config.language.as_deref(), Some("en"));
    }

    #[test]
    fn config_patch_rejects_malformed_text_replacements() {
        let mut config = memopaws_config::config::AppConfig::default();
        assert_eq!(
            super::apply_config_patch(&mut config, &serde_json::json!({"text_replacements": [{"abbr": 1}]})).unwrap_err(),
            "text_replacements must be an array of replacement rules"
        );
    }

    #[test]
    fn save_config_at_strips_api_key_and_rejects_invalid_payloads() {
        let path = std::env::temp_dir().join(format!(
            "memopaws-save-config-{}.json",
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos(),
        ));
        memopaws_config::config::AppConfig::default().save_to(&path).unwrap();

        super::save_config_at(&path, serde_json::json!({
            "api_key": "never-keep-me",
            "language": "en",
            "clipboard_max_items": 70
        })).unwrap();

        let raw = std::fs::read_to_string(&path).unwrap();
        assert!(!raw.contains("never-keep-me"));
        let value: serde_json::Value = serde_json::from_str(&raw).unwrap();
        assert!(value.get("api_key").is_none_or(|v| v.is_null()));
        let saved = memopaws_config::config::AppConfig::load_from(&path).unwrap();
        assert_eq!(saved.language.as_deref(), Some("en"));
        assert_eq!(saved.clipboard_max_items, Some(70));

        assert!(super::save_config_at(&path, serde_json::json!({"clipboard_max_items": 5})).is_err());
        assert!(super::save_config_at(&path, serde_json::json!({"api_url": "not a url"})).is_err());
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn text_replacement_validation_covers_abbreviation_bounds() {
        let empty = memopaws_config::config::TextReplacement { abbr: "".into(), replacement: "x".into() };
        assert!(super::validate_text_replacements(&[empty]).is_err());

        let whitespace = memopaws_config::config::TextReplacement { abbr: "   ".into(), replacement: "x".into() };
        assert!(super::validate_text_replacements(&[whitespace]).is_err());

        let long = memopaws_config::config::TextReplacement { abbr: "a".repeat(65), replacement: "x".into() };
        assert!(super::validate_text_replacements(&[long]).is_err());

        let boundary = memopaws_config::config::TextReplacement { abbr: "a".repeat(64), replacement: "x".into() };
        assert!(super::validate_text_replacements(&[boundary]).is_ok());
    }

    #[test]
    fn settings_api_key_is_saved_idempotently_in_the_vault() {
        // save_settings_key requires a tauri::State handle, so this exercises the
        // exact same find-then-update-or-add flow against a real vault file.
        let path = std::env::temp_dir().join(format!(
            "memopaws-settings-key-{}.json",
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos(),
        ));
        let mut vault = KeyVault::load(&path).unwrap();
        let save = |vault: &mut KeyVault, key: &str| {
            let input = || KeyEntryInput { name: "settings_api_key".into(), entry_type: "llm".into(), value: key.to_owned(), url: "https://example.test/v1".into(), url_anthropic: String::new(), note: "Settings API key".into() };
            if let Some(entry) = vault.list().into_iter().find(|entry| entry.name == "settings_api_key" && entry.entry_type == "llm") {
                vault.update(entry.id, input()).unwrap();
            } else {
                vault.add(input()).unwrap();
            }
        };
        save(&mut vault, "first-key");
        save(&mut vault, "second-key");

        let entries = vault.list();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].name, "settings_api_key");
        assert_eq!(vault.get_value(entries[0].id).unwrap(), "second-key");

        let reloaded = KeyVault::load(&path).unwrap();
        assert_eq!(reloaded.list().len(), 1);
        let _ = std::fs::remove_file(path);
    }
}
