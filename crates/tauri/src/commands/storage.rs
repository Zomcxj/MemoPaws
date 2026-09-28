use std::path::Path;

use tauri_plugin_dialog::DialogExt;




#[tauri::command]
pub fn get_data_dir() -> Result<String, String> {
    // UI shows the base directory (parent of `.memopaws`), matching migration targets.
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
    args.get("data_dir")
        .or_else(|| args.get("path"))
        .and_then(|value| value.as_str())
        .map(str::trim)
        .filter(|path| !path.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| "data_dir or path is required".to_string())
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
                restart_required: true,
            });
        }
        Ok(MigrationResult {
            path: None,
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

#[cfg(test)]
mod tests {
    #[test]
    fn migration_mode_accepts_merge_overwrite_and_cancel() {
        assert_eq!(
            super::migration_target(&serde_json::json!({"data_dir": "a"})).unwrap(),
            "a"
        );
        assert_eq!(
            super::migration_target(&serde_json::json!({"path": "b"})).unwrap(),
            "b"
        );
        assert_eq!(
            super::migration_mode("merge").unwrap(),
            memopaws_core::paths::MigrationMode::Merge
        );
        assert_eq!(
            super::migration_mode("overwrite").unwrap(),
            memopaws_core::paths::MigrationMode::Replace
        );
        assert_eq!(
            super::migration_mode("cancel").unwrap(),
            memopaws_core::paths::MigrationMode::Cancel
        );
        assert!(super::migration_mode("unexpected").is_err());
    }

    #[test]
    fn migration_target_requires_a_non_empty_string() {
        assert!(super::migration_target(&serde_json::json!({})).is_err());
        assert!(super::migration_target(&serde_json::json!({"data_dir": null})).is_err());
        assert!(super::migration_target(&serde_json::json!({"data_dir": "   "})).is_err());
        assert!(super::migration_target(&serde_json::json!({"path": 42})).is_err());
        assert_eq!(
            super::migration_target(&serde_json::json!({"path": " d:\\data "})).unwrap(),
            "d:\\data"
        );
    }

    #[test]
    fn migration_mode_is_case_insensitive_and_accepts_aliases() {
        assert_eq!(
            super::migration_mode("MERGE").unwrap(),
            memopaws_core::paths::MigrationMode::Merge
        );
        assert_eq!(
            super::migration_mode("Overwrite").unwrap(),
            memopaws_core::paths::MigrationMode::Replace
        );
        assert_eq!(
            super::migration_mode("move").unwrap(),
            memopaws_core::paths::MigrationMode::Replace
        );
        assert_eq!(
            super::migration_mode("Cancel").unwrap(),
            memopaws_core::paths::MigrationMode::Cancel
        );
        assert_eq!(
            super::migration_mode(" delete ").unwrap_err(),
            "migration mode must be merge, overwrite, or cancel"
        );
    }

}
