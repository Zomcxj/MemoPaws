
use memopaws_memo::model::Memo;
use memopaws_memo::renderer::{render_markdown, RenderTheme};
use memopaws_memo::search::MemoSearchResult;
use memopaws_memo::{migrate, revisions, search, storage};




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
pub fn memo_revision_list(id: i64) -> Result<Vec<revisions::Revision>, String> {
    revisions::list_revisions(&memo_dir()?, id).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn memo_revision_restore(id: i64, time: String, now: String) -> Result<Memo, String> {
    let dir = memo_dir()?;
    let revisions = revisions::list_revisions(&dir, id).map_err(|error| error.to_string())?;
    let revision = revisions
        .iter()
        .find(|revision| revision.time == time)
        .ok_or_else(|| format!("revision {time} not found"))?;
    let mut memo = storage::read_memo(&dir, id).map_err(|error| error.to_string())?;
    memo.content = revision.content.clone();
    memo.modified = now;
    // update_memo snapshots the current content, so a restore never loses data.
    storage::update_memo(&dir, memo).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn memo_revision_delete(id: i64, time: String) -> Result<(), String> {
    revisions::delete_revision(&memo_dir()?, id, &time).map_err(|error| error.to_string())
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

