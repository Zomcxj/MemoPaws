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
            api_model: Some("glm-4-flash".into()),
            clipboard_max_items: Some(50),
            history_max_items: Some(100),
            shortcuts: Some(
                [
                    ("capture".into(), "Alt+X".into()),
                    ("canvas_fit".into(), "Ctrl+F".into()),
                    ("new_memo".into(), "Ctrl+N".into()),
                    ("global_search".into(), "Ctrl+Shift+F".into()),
                    ("toggle_clipboard".into(), "".into()),
                ]
                .into_iter()
                .collect(),
            ),
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
            let cfg = serde_json::from_str(&raw)?;
            Ok(cfg)
        } else {
            let cfg = Self::default();
            cfg.save_to(path)?;
            Ok(cfg)
        }
    }

    pub fn save(&self) -> Result<()> {
        self.save_to(&paths::config_path()?)
    }

    pub fn save_to(&self, path: &std::path::Path) -> Result<()> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let raw = serde_json::to_string_pretty(self)?;
        fs::write(&path, raw)?;
        Ok(())
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
}
