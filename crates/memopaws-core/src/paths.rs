use std::fs;
use std::path::{Path, PathBuf};

use crate::error::{Error, Result};

// Keep the Rust port's persisted data isolated from the Python application.
const CONFIG_DIR_NAME: &str = ".memopaws-rust";
const ANCHOR_FILE_NAME: &str = ".memopaws-rust.json";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MigrationMode {
    Merge,
    Replace,
    Cancel,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MigrationPreview {
    pub current_base: PathBuf,
    pub current_data_dir: PathBuf,
    pub target_base: PathBuf,
    pub target_data_dir: PathBuf,
    pub source_exists: bool,
    pub target_exists: bool,
}

fn home_dir() -> Result<PathBuf> {
    dirs::home_dir()
        .map(Into::into)
        .ok_or(Error::HomeDir)
}

fn anchor_file() -> Result<PathBuf> {
    home_dir().map(|h| h.join(ANCHOR_FILE_NAME))
}

fn detect_data_dir() -> Result<PathBuf> {
    let anchor = anchor_file()?;
    if anchor.exists() {
        if let Ok(raw) = fs::read_to_string(&anchor) {
            let val: serde_json::Value = serde_json::from_str(&raw)?;
            if let Some(data_dir) = val.get("data_dir").and_then(|v| v.as_str()) {
                let candidate = Path::new(data_dir).join(CONFIG_DIR_NAME);
                if candidate.is_dir() {
                    return Ok(candidate);
                }
            }
        }
    }
    Ok(home_dir()?.join(CONFIG_DIR_NAME))
}

pub fn data_dir() -> Result<PathBuf> {
    detect_data_dir()
}

pub fn ensure_data_dir() -> Result<PathBuf> {
    let dir = data_dir()?;
    fs::create_dir_all(&dir)?;
    let memos = dir.join("memo");
    fs::create_dir_all(&memos)?;
    let keys = dir.join("keys");
    fs::create_dir_all(&keys)?;
    let images = dir.join("clipboard_images");
    fs::create_dir_all(&images)?;
    let captures = dir.join("captures");
    fs::create_dir_all(&captures)?;
    Ok(dir)
}

pub fn config_path() -> Result<PathBuf> {
    data_dir().map(|d| d.join("setting.json"))
}

pub fn memos_dir() -> Result<PathBuf> {
    data_dir().map(|d| d.join("memo"))
}

pub fn keys_dir() -> Result<PathBuf> {
    data_dir().map(|d| d.join("keys.json"))
}

pub fn clipboard_path() -> Result<PathBuf> {
    data_dir().map(|d| d.join("clipboard.json"))
}

pub fn clipboard_images_dir() -> Result<PathBuf> {
    data_dir().map(|d| d.join("clipboard_images"))
}

pub fn captures_dir() -> Result<PathBuf> {
    data_dir().map(|d| d.join("captures"))
}

pub fn history_path() -> Result<PathBuf> {
    data_dir().map(|d| d.join("history.json"))
}

pub fn save_anchor(data_dir: &str) -> Result<()> {
    let anchor = anchor_file()?;
    let parent = anchor.parent().ok_or(Error::HomeDir)?;
    fs::create_dir_all(parent)?;
    let json = serde_json::json!({ "data_dir": data_dir });
    fs::write(&anchor, serde_json::to_string_pretty(&json)?)?;
    Ok(())
}

pub fn preview_data_migration(target_base: &Path) -> Result<MigrationPreview> {
    let current_data_dir = data_dir()?;
    let current_base = current_data_dir
        .parent()
        .map(Path::to_path_buf)
        .ok_or_else(|| Error::Custom("data directory has no base directory".into()))?;
    let target_base = target_base.to_path_buf();
    let target_data_dir = target_base.join(CONFIG_DIR_NAME);
    validate_migration_paths(&current_data_dir, &target_data_dir)?;
    Ok(MigrationPreview {
        current_base,
        current_data_dir: current_data_dir.clone(),
        target_base,
        target_data_dir: target_data_dir.clone(),
        source_exists: current_data_dir.is_dir(),
        target_exists: target_data_dir.exists(),
    })
}

pub fn migrate_data_dir(target_base: &Path, mode: MigrationMode) -> Result<Option<PathBuf>> {
    let source = data_dir()?;
    let anchor = anchor_file()?;
    migrate_data_from(&source, target_base, mode, &anchor)
}

fn migrate_data_from(
    source: &Path,
    target_base: &Path,
    mode: MigrationMode,
    anchor: &Path,
) -> Result<Option<PathBuf>> {
    if mode == MigrationMode::Cancel {
        return Ok(None);
    }
    let target = target_base.join(CONFIG_DIR_NAME);
    if target_base.exists() && !target_base.is_dir() {
        return Err(Error::Custom("target base path is not a directory".into()));
    }
    validate_migration_paths(source, &target)?;
    if !source.is_dir() {
        return Err(Error::Custom("source data directory is not a directory".into()));
    }
    if mode == MigrationMode::Merge {
        ensure_no_conflicts(source, &target)?;
    } else if target.exists() {
        if !target.is_dir() {
            return Err(Error::Custom("target data path is not a directory".into()));
        }
        fs::remove_dir_all(&target)?;
    }
    fs::create_dir_all(&target)?;
    copy_tree(source, &target)?;
    write_anchor(anchor, target_base)
        .map_err(|error| Error::Custom(format!("data copied but anchor update failed: {error}")))?;
    Ok(Some(target))
}

fn validate_migration_paths(source: &Path, target: &Path) -> Result<()> {
    let source = fs::canonicalize(source).unwrap_or_else(|_| source.to_path_buf());
    let target = fs::canonicalize(target).unwrap_or_else(|_| target.to_path_buf());
    if source == target {
        return Err(Error::Custom("source and target data directories are identical".into()));
    }
    if target.exists() && !target.is_dir() {
        return Err(Error::Custom("target data path is not a directory".into()));
    }
    Ok(())
}

fn ensure_no_conflicts(source: &Path, target: &Path) -> Result<()> {
    if !target.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let destination = target.join(entry.file_name());
        if destination.exists() {
            if entry.path().is_dir() && destination.is_dir() {
                ensure_no_conflicts(&entry.path(), &destination)?;
            } else {
                return Err(Error::Custom(format!("merge conflict at {}", destination.display())));
            }
        }
    }
    Ok(())
}

fn copy_tree(source: &Path, target: &Path) -> Result<()> {
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());
        if source_path.is_dir() {
            fs::create_dir_all(&target_path)?;
            copy_tree(&source_path, &target_path)?;
        } else {
            fs::copy(&source_path, &target_path)?;
        }
    }
    Ok(())
}

fn write_anchor(anchor: &Path, base: &Path) -> Result<()> {
    if let Some(parent) = anchor.parent() {
        fs::create_dir_all(parent)?;
    }
    let json = serde_json::json!({ "data_dir": base });
    fs::write(anchor, serde_json::to_string_pretty(&json)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    struct TempDirs {
        root: PathBuf,
    }

    impl TempDirs {
        fn new() -> Self {
            let suffix = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let root = std::env::temp_dir().join(format!("memopaws-paths-{suffix}"));
            fs::create_dir_all(&root).unwrap();
            Self { root }
        }

        fn path(&self, name: &str) -> PathBuf {
            self.root.join(name)
        }
    }

    impl Drop for TempDirs {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.root);
        }
    }

    fn source_with_file(dirs: &TempDirs) -> PathBuf {
        let source = dirs.path("source");
        fs::create_dir_all(source.join(CONFIG_DIR_NAME).join("memo")).unwrap();
        fs::write(source.join(CONFIG_DIR_NAME).join("memo/item.txt"), "source").unwrap();
        source.join(CONFIG_DIR_NAME)
    }

    #[test]
    fn migrates_complete_tree_and_updates_anchor_only_after_success() {
        let dirs = TempDirs::new();
        let source = source_with_file(&dirs);
        let target = dirs.path("target");
        let anchor = dirs.path("anchor.json");
        fs::write(&anchor, r#"{"data_dir":"old"}"#).unwrap();

        let result = migrate_data_from(&source, &target, MigrationMode::Merge, &anchor).unwrap();

        assert_eq!(result, Some(target.join(CONFIG_DIR_NAME)));
        assert_eq!(fs::read_to_string(target.join(CONFIG_DIR_NAME).join("memo/item.txt")).unwrap(), "source");
        let anchor_value: serde_json::Value = serde_json::from_str(&fs::read_to_string(anchor).unwrap()).unwrap();
        assert_eq!(anchor_value["data_dir"].as_str(), target.to_str());
    }

    #[test]
    fn merge_conflict_keeps_target_and_anchor_unchanged() {
        let dirs = TempDirs::new();
        let source = source_with_file(&dirs);
        let target = dirs.path("target");
        let target_data = target.join(CONFIG_DIR_NAME);
        fs::create_dir_all(target_data.join("memo")).unwrap();
        fs::write(target_data.join("memo/item.txt"), "target").unwrap();
        let anchor = dirs.path("anchor.json");
        fs::write(&anchor, "old-anchor").unwrap();

        assert!(migrate_data_from(&source, &target, MigrationMode::Merge, &anchor).is_err());
        assert_eq!(fs::read_to_string(target_data.join("memo/item.txt")).unwrap(), "target");
        assert_eq!(fs::read_to_string(anchor).unwrap(), "old-anchor");
    }

    #[test]
    fn cancel_performs_no_write() {
        let dirs = TempDirs::new();
        let source = source_with_file(&dirs);
        let target = dirs.path("target");
        let anchor = dirs.path("anchor.json");
        fs::write(&anchor, "old-anchor").unwrap();

        assert_eq!(migrate_data_from(&source, &target, MigrationMode::Cancel, &anchor).unwrap(), None);
        assert!(!target.exists());
        assert_eq!(fs::read_to_string(anchor).unwrap(), "old-anchor");
    }

    #[test]
    fn rejects_same_source_and_target_without_changing_anchor() {
        let dirs = TempDirs::new();
        let source = source_with_file(&dirs);
        let anchor = dirs.path("anchor.json");
        fs::write(&anchor, "old-anchor").unwrap();

        assert!(migrate_data_from(&source, source.parent().unwrap(), MigrationMode::Replace, &anchor).is_err());
        assert_eq!(fs::read_to_string(anchor).unwrap(), "old-anchor");
    }

    #[test]
    fn copy_failure_does_not_update_anchor() {
        let dirs = TempDirs::new();
        let source = source_with_file(&dirs);
        let target = dirs.path("target");
        let anchor = dirs.path("anchor.json");
        fs::write(&anchor, "old-anchor").unwrap();
        fs::create_dir_all(target.join(CONFIG_DIR_NAME)).unwrap();
        fs::write(target.join(CONFIG_DIR_NAME).join("memo"), "not-a-directory").unwrap();

        assert!(migrate_data_from(&source, &target, MigrationMode::Merge, &anchor).is_err());
        assert_eq!(fs::read_to_string(anchor).unwrap(), "old-anchor");
    }
}
