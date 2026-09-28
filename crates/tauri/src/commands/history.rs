
use memopaws_config::history::{HistoryManager, HistoryRecord};



use super::HistoryState;
use super::config::validate_config_request;

pub(super) fn history_mut<T>(
    state: tauri::State<'_, HistoryState>,
    operation: impl FnOnce(&mut HistoryManager) -> memopaws_core::Result<T>,
) -> Result<T, String> {
    let mut history = lock_recover!(state);
    operation(&mut history).map_err(|_| "history operation failed".to_string())
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

#[tauri::command]
pub fn set_history_max_items(
    value: usize,
    state: tauri::State<'_, HistoryState>,
) -> Result<(), String> {
    validate_config_request(&serde_json::json!({"history_max_items": value as u64}))?;
    lock_recover!(state)
        .set_max_items(value)
        .map_err(|error| error.to_string())
}
