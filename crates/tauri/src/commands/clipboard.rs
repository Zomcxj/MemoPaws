
use memopaws_clipboard::{ClipboardItem, ClipboardManager};
use memopaws_memo::model::Memo;
use memopaws_memo::search;
use tauri::Emitter;



use super::ClipboardState;
use super::memo::memo_list;

#[tauri::command]
pub fn clipboard_paste_image(
    state: tauri::State<'_, ClipboardState>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    let mut clipboard =
        arboard::Clipboard::new().map_err(|error| format!("clipboard access failed: {error}"))?;
    let bytes = match clipboard.get_image() {
        Ok(image) => {
            let raw = image::RgbaImage::from_raw(
                image.width as u32,
                image.height as u32,
                image.bytes.as_ref().to_vec(),
            )
            .ok_or_else(|| "invalid clipboard image dimensions".to_string())?;
            let mut bytes = Vec::new();
            raw.write_to(
                &mut std::io::Cursor::new(&mut bytes),
                image::ImageFormat::Png,
            )
            .map_err(|error| format!("image encoding failed: {error}"))?;
            bytes
        }
        Err(_) => memopaws_clipboard::read_file_list_image()
            .or_else(|| {
                clipboard
                    .get_text()
                    .ok()
                    .and_then(|text| memopaws_clipboard::read_image_path(&text))
            })
            .ok_or_else(|| "no image or supported image file in clipboard".to_string())?,
    };
    lock_recover!(state)
        .add_image(&bytes)
        .map_err(|error| format!("failed to save clipboard image: {error}"))?;
    // Manual paste does not pass through the listener, so notify the frontend here.
    // The listener callbacks emit the same event for automatically captured content.
    let _ = app.emit("clipboard-changed", serde_json::json!({}));
    Ok(())
}
fn clipboard_mut<T>(
    state: tauri::State<'_, ClipboardState>,
    operation: impl FnOnce(&mut ClipboardManager) -> Result<T, String>,
) -> Result<T, String> {
    let mut clipboard = lock_recover!(state);
    operation(&mut clipboard)
}

#[tauri::command]
pub fn clipboard_list(
    state: tauri::State<'_, ClipboardState>,
) -> Result<Vec<ClipboardItem>, String> {
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
pub fn clipboard_get_image(
    id: u64,
    state: tauri::State<'_, ClipboardState>,
) -> Result<Vec<u8>, String> {
    clipboard_mut(state, |clipboard| clipboard.get_image_bytes(id))
}

#[tauri::command]
pub fn clipboard_set_locked(
    id: u64,
    locked: bool,
    state: tauri::State<'_, ClipboardState>,
) -> Result<(), String> {
    clipboard_mut(state, |clipboard| clipboard.set_locked(id, locked))
}

#[tauri::command]
pub fn clipboard_update_text(
    id: u64,
    text: String,
    state: tauri::State<'_, ClipboardState>,
) -> Result<(), String> {
    clipboard_mut(state, |clipboard| clipboard.update_text(id, &text))
}

#[tauri::command]
pub fn clipboard_delete_many(
    ids: Vec<u64>,
    state: tauri::State<'_, ClipboardState>,
) -> Result<usize, String> {
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
pub fn global_search(
    query: String,
    clipboard: tauri::State<'_, ClipboardState>,
) -> Result<Vec<serde_json::Value>, String> {
    let query = query.trim().to_lowercase();
    if query.is_empty() {
        return Ok(Vec::new());
    }
    let mut results = Vec::new();
    let clipboard = lock_recover!(clipboard);
    for item in clipboard.items() {
        let text = item.text.clone().unwrap_or_else(|| "[image]".into());
        if text.to_lowercase().contains(&query) {
            results.push(serde_json::json!({ "source": "clipboard", "id": item.id, "title": "Clipboard", "text": text, "time": item.time }));
        }
    }
    results.extend(memo_global_search_results(&query, &memo_list()?));
    Ok(results)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn memo_global_search_returns_empty_for_empty_query() {
        let memos = vec![Memo {
            title: "Visible".into(),
            content: "body".into(),
            ..Memo::default()
        }];

        assert_eq!(
            super::memo_global_search_results(" ", &memos),
            Vec::<serde_json::Value>::new()
        );
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
        assert_eq!(
            results[0],
            serde_json::json!({
                "source": "memo",
                "id": 7,
                "title": "Release notes",
                "text": "Memo body",
                "time": "2026-08-05T12:00:00Z"
            })
        );
        assert!(results[0].get("keys").is_none());
        assert!(results[0].get("secret").is_none());
    }

}
