use std::sync::{Arc, Mutex};


use crate::text_replacer::TextReplacer;


use super::config::validate_text_replacements;

pub struct TextReplacerState {
    pub machine: Mutex<TextReplacer>,
    pub rules: Mutex<Vec<memopaws_config::config::TextReplacement>>,
}

impl TextReplacerState {
    pub fn new(rules: Vec<memopaws_config::config::TextReplacement>) -> Self {
        Self {
            machine: Mutex::new(TextReplacer::default()),
            rules: Mutex::new(rules),
        }
    }
}

#[tauri::command]
pub fn text_replacement_list(
    state: tauri::State<'_, Arc<TextReplacerState>>,
) -> Result<Vec<memopaws_config::config::TextReplacement>, String> {
    Ok(lock_recover!(state.rules).clone())
}

#[tauri::command]
pub fn text_replacement_create(
    rule: memopaws_config::config::TextReplacement,
    state: tauri::State<'_, Arc<TextReplacerState>>,
) -> Result<(), String> {
    let mut rules = lock_recover!(state.rules);
    let mut updated = rules.clone();
    updated.push(rule);
    validate_text_replacements(&updated)?;
    persist_text_replacements(&updated)?;
    *rules = updated;
    Ok(())
}

#[tauri::command]
pub fn text_replacement_update(
    abbr: String,
    rule: memopaws_config::config::TextReplacement,
    state: tauri::State<'_, Arc<TextReplacerState>>,
) -> Result<(), String> {
    let mut rules = lock_recover!(state.rules);
    let index = rules
        .iter()
        .position(|item| item.abbr == abbr)
        .ok_or_else(|| "text replacement not found".to_string())?;
    let mut updated = rules.clone();
    updated[index] = rule;
    validate_text_replacements(&updated)?;
    persist_text_replacements(&updated)?;
    *rules = updated;
    Ok(())
}

#[tauri::command]
pub fn text_replacement_delete(
    abbr: String,
    state: tauri::State<'_, Arc<TextReplacerState>>,
) -> Result<(), String> {
    let mut rules = lock_recover!(state.rules);
    let before = rules.len();
    let mut updated = rules.clone();
    updated.retain(|item| item.abbr != abbr);
    if updated.len() == before {
        return Err("text replacement not found".to_string());
    }
    persist_text_replacements(&updated)?;
    *rules = updated;
    Ok(())
}

fn persist_text_replacements(
    rules: &[memopaws_config::config::TextReplacement],
) -> Result<(), String> {
    let mut config =
        memopaws_config::config::AppConfig::load().map_err(|error| error.to_string())?;
    config.text_replacements = rules.to_vec();
    config.save().map_err(|error| error.to_string())
}
