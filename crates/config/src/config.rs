use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

use memopaws_core::{paths, Result};
use serde::{Deserialize, Deserializer, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CloseBehavior {
    Exit,
    Tray,
}

impl Default for CloseBehavior {
    fn default() -> Self {
        CloseBehavior::Exit
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextReplacement {
    pub abbr: String,
    pub replacement: String,
}

/// Single source of truth for the default global shortcuts.
///
/// `AppConfig::default()` builds its `shortcuts` map from this table and
/// `memopaws_tauri::hotkeys` re-exports it, so a default can never drift
/// between the persisted config and the registration path.
pub const DEFAULT_SHORTCUTS: &[(&str, &str)] = &[
    ("capture", "Alt+X"),
    ("canvas_fit", "Ctrl+F"),
    ("new_memo", "Ctrl+N"),
    ("global_search", "Ctrl+Shift+F"),
    ("toggle_clipboard", "Ctrl+Shift+V"),
];

fn default_shortcuts() -> HashMap<String, String> {
    DEFAULT_SHORTCUTS
        .iter()
        .map(|(action, key)| ((*action).to_string(), (*key).to_string()))
        .collect()
}

fn deserialize_text_replacements<'de, D>(
    deserializer: D,
) -> std::result::Result<Vec<TextReplacement>, D::Error>
where
    D: Deserializer<'de>,
{
    Ok(Option::<Vec<TextReplacement>>::deserialize(deserializer)?.unwrap_or_default())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub theme: Option<String>,
    pub language: Option<String>,
    pub close_behavior: Option<String>,
    pub api_key: Option<String>,
    pub api_url: Option<String>,
    pub api_model: Option<String>,
    pub clipboard_max_items: Option<usize>,
    pub history_max_items: Option<usize>,
    pub shortcuts: Option<HashMap<String, String>>,
    #[serde(default, deserialize_with = "deserialize_text_replacements")]
    pub text_replacements: Vec<TextReplacement>,
}

impl Default for AppConfig {
    fn default() -> Self {
        AppConfig {
            theme: Some("dark".into()),
            language: Some("zh".into()),
            close_behavior: Some("tray".into()),
            api_key: None,
            api_url: Some("https://open.bigmodel.cn/api/paas/v4/chat/completions".into()),
            api_model: Some("glm-4v-flash".into()),
            clipboard_max_items: Some(50),
            history_max_items: Some(100),
            shortcuts: Some(default_shortcuts()),
            text_replacements: Vec::new(),
        }
    }
}

impl AppConfig {
    pub fn preview_data_migration(target_base: &Path) -> Result<paths::MigrationPreview> {
        paths::preview_data_migration(target_base)
    }

    pub fn migrate_data_dir(
        target_base: &Path,
        mode: paths::MigrationMode,
    ) -> Result<Option<PathBuf>> {
        paths::migrate_data_dir(target_base, mode)
    }

    pub fn load() -> Result<Self> {
        Self::load_from(&paths::config_path()?)
    }

    pub fn load_from(path: &std::path::Path) -> Result<Self> {
        if path.exists() {
            let raw = fs::read_to_string(&path)?;
            let mut cfg: AppConfig = serde_json::from_str(&raw)?;
            // 旧默认模型 glm-4-flash 不支持图片识别，迁移到多模态默认值
            if cfg.api_model.as_deref() == Some("glm-4-flash") {
                cfg.api_model = Some("glm-4v-flash".into());
            }
            cfg.repair_blank_toggle_clipboard();
            Ok(cfg)
        } else {
            let cfg = Self::default();
            cfg.save_to(path)?;
            Ok(cfg)
        }
    }

    /// Restores `toggle_clipboard` for configs written by the buggy default.
    ///
    /// Until v0.0.1 `AppConfig::default()` stored `toggle_clipboard: ""` while
    /// the registration table used `Ctrl+Shift+V`. Because `load_from` persists
    /// the default on first run and `register_from_config` lets the saved value
    /// win, the shortcut was never actually registered. The settings UI cannot
    /// produce an empty binding (`recordShortcut` requires a modifier plus a
    /// named key, `resetShortcut` writes the default), so a blank value here is
    /// always that bug rather than a deliberate opt-out and is safe to repair.
    fn repair_blank_toggle_clipboard(&mut self) {
        let Some(shortcuts) = self.shortcuts.as_mut() else { return };
        if !shortcuts.get("toggle_clipboard").is_some_and(|key| key.trim().is_empty()) {
            return;
        }
        if let Some((_, default)) = DEFAULT_SHORTCUTS.iter().find(|(action, _)| *action == "toggle_clipboard") {
            shortcuts.insert("toggle_clipboard".into(), (*default).to_string());
        }
    }

    pub fn save(&self) -> Result<()> {
        self.save_to(&paths::config_path()?)
    }

    pub fn save_to(&self, path: &std::path::Path) -> Result<()> {
        let raw = serde_json::to_string_pretty(self)?;
        memopaws_core::write_file_atomic(path, raw.as_bytes())
    }
}

#[cfg(test)]
mod tests {
    use super::AppConfig;

    #[test]
    fn text_replacements_accept_missing_and_empty_legacy_values() {
        let missing: AppConfig = serde_json::from_str("{}").unwrap();
        assert!(missing.text_replacements.is_empty());

        let empty: AppConfig = serde_json::from_str(r#"{"text_replacements": []}"#).unwrap();
        assert!(empty.text_replacements.is_empty());

        let null: AppConfig = serde_json::from_str(r#"{"text_replacements": null}"#).unwrap();
        assert!(null.text_replacements.is_empty());
    }

    #[test]
    fn default_toggle_clipboard_matches_the_registration_table() {
        let shortcuts = AppConfig::default().shortcuts.unwrap();
        for (action, key) in super::DEFAULT_SHORTCUTS {
            assert_eq!(shortcuts.get(*action).map(String::as_str), Some(*key));
        }
        assert_eq!(shortcuts.get("toggle_clipboard").map(String::as_str), Some("Ctrl+Shift+V"));
    }

    #[test]
    fn blank_toggle_clipboard_written_by_the_old_default_is_repaired_on_load() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("setting.json");
        std::fs::write(&path, r#"{"theme":"dark","language":"zh","close_behavior":"tray","api_key":null,"api_url":"u","api_model":"glm-4v-flash","clipboard_max_items":50,"history_max_items":100,"shortcuts":{"capture":"Alt+X","toggle_clipboard":""}}"#).unwrap();

        let loaded = AppConfig::load_from(&path).unwrap();
        let shortcuts = loaded.shortcuts.unwrap();

        assert_eq!(shortcuts.get("toggle_clipboard").map(String::as_str), Some("Ctrl+Shift+V"));
        assert_eq!(shortcuts.get("capture").map(String::as_str), Some("Alt+X"));
    }

    #[test]
    fn deliberate_bindings_and_other_blank_actions_are_left_alone() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("setting.json");
        std::fs::write(&path, r#"{"theme":"dark","language":"zh","close_behavior":"tray","api_key":null,"api_url":"u","api_model":"glm-4v-flash","clipboard_max_items":50,"history_max_items":100,"shortcuts":{"capture":"","toggle_clipboard":"Alt+V"}}"#).unwrap();

        let shortcuts = AppConfig::load_from(&path).unwrap().shortcuts.unwrap();

        assert_eq!(shortcuts.get("toggle_clipboard").map(String::as_str), Some("Alt+V"));
        assert_eq!(shortcuts.get("capture").map(String::as_str), Some(""));
    }
}
