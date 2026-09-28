
use memopaws_memo::model::Memo;
use memopaws_memo::renderer::{render_markdown, RenderTheme};
use memopaws_memo::search::MemoSearchResult;
use memopaws_memo::{migrate, search, storage};




fn memo_dir() -> Result<std::path::PathBuf, String> {
    storage::resolve_memo_dir(None).map_err(|error| error.to_string())
}

fn migrate_legacy(dir: &std::path::Path) -> Result<(), String> {
    let config_dir = dir
        .parent()
        .ok_or_else(|| "memo directory has no parent".to_string())?;
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

