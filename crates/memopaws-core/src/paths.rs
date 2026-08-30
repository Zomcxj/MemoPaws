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
    dirs::home_dir().map(Into::into).ok_or(Error::HomeDir)
}

fn anchor_file() -> Result<PathBuf> {
    home_dir().map(|h| h.join(ANCHOR_FILE_NAME))
}

/// Resolve an anchor-stored path (base OR full `.../.memopaws-rust`, legacy)
/// to the concrete data directory, if it exists.
fn stored_path_to_data_dir(stored: &Path) -> Option<PathBuf> {
    if stored
        .file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name.eq_ignore_ascii_case(CONFIG_DIR_NAME))
        && stored.is_dir()
    {
        return Some(stored.to_path_buf());
    }
    let candidate = stored.join(CONFIG_DIR_NAME);
    if candidate.is_dir() {
        return Some(candidate);
    }
    None
}

fn detect_data_dir() -> Result<PathBuf> {
    let anchor = anchor_file()?;
    if anchor.exists() {
        if let Ok(raw) = fs::read_to_string(&anchor) {
            let val: serde_json::Value = serde_json::from_str(&raw)?;
            if let Some(data_dir) = val.get("data_dir").and_then(|v| v.as_str()) {
                let raw_path = PathBuf::from(data_dir);
                if let Some(dir) = stored_path_to_data_dir(&raw_path) {
                    return Ok(dir);
                }
            }
        }
    }
    Ok(home_dir()?.join(CONFIG_DIR_NAME))
}

pub fn data_dir() -> Result<PathBuf> {
    detect_data_dir()
}

/// Storage base directory (parent of `.memopaws-rust`).
/// Anchor stores this path; UI shows it for migration targets.
pub fn data_base_dir() -> Result<PathBuf> {
    let dir = data_dir()?;
    if dir
        .file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name.eq_ignore_ascii_case(CONFIG_DIR_NAME))
    {
        if let Some(parent) = dir.parent() {
            return Ok(parent.to_path_buf());
        }
    }
    home_dir()
}

/// Normalize a user-selected path to the migration base directory.
/// Accepts either the base folder or a path ending in `.memopaws-rust`.
pub fn normalize_migration_base(path: &Path) -> PathBuf {
    if path
        .file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name.eq_ignore_ascii_case(CONFIG_DIR_NAME))
    {
        path.parent()
            .map(Path::to_path_buf)
            .unwrap_or_else(|| path.to_path_buf())
    } else {
        path.to_path_buf()
    }
}

pub fn storage_dir_conflict(target_base: &Path) -> Result<bool> {
    let base = normalize_migration_base(target_base);
    let preview = preview_data_migration(&base)?;
    Ok(preview.target_exists)
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
    validate_migration_paths(&target_data_dir)?;
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
    let base = normalize_migration_base(target_base);
    migrate_data_from(&source, &base, mode, &anchor)
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
    // Migrating onto the active data directory is a no-op, not an error:
    // never delete (or copy onto) the tree the app is currently using.
    if paths_refer_to_same_dir(source, &target) {
        return Ok(None);
    }
    if target_base.exists() && !target_base.is_dir() {
        return Err(Error::Custom("target base path is not a directory".into()));
    }
    validate_migration_paths(&target)?;
    if !source.is_dir() {
        return Err(Error::Custom(
            "source data directory is not a directory".into(),
        ));
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
    ensure_tree_layout(&target)?;
    write_anchor(anchor, target_base)
        .map_err(|error| Error::Custom(format!("data copied but anchor update failed: {error}")))?;
    Ok(Some(target))
}

fn paths_refer_to_same_dir(left: &Path, right: &Path) -> bool {
    let left = fs::canonicalize(left).unwrap_or_else(|_| left.to_path_buf());
    let right = fs::canonicalize(right).unwrap_or_else(|_| right.to_path_buf());
    if left == right {
        return true;
    }
    #[cfg(windows)]
    {
        left.to_string_lossy()
            .eq_ignore_ascii_case(&right.to_string_lossy())
    }
    #[cfg(not(windows))]
    {
        false
    }
}

fn validate_migration_paths(target: &Path) -> Result<()> {
    let target = fs::canonicalize(target).unwrap_or_else(|_| target.to_path_buf());
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
            } else if entry.path().is_dir() || destination.is_dir() {
                return Err(Error::Custom(format!(
                    "merge conflict at {}",
                    destination.display()
                )));
            }
            // Both are files: source wins (overwrite).
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

/// Write the anchor atomically: a partial write here would orphan the whole data tree,
/// because the next launch resolves the data directory from this single file.
fn write_anchor(anchor: &Path, base: &Path) -> Result<()> {
    if let Some(parent) = anchor.parent() {
        fs::create_dir_all(parent)?;
    }
    let json = serde_json::json!({ "data_dir": base });
    let raw = serde_json::to_string_pretty(&json)?;
    let temporary = anchor.with_extension("tmp");
    fs::write(&temporary, &raw)?;
    if let Err(error) = fs::rename(&temporary, anchor) {
        // Windows rename can fail if the destination exists; fall back to replace.
        let _ = fs::remove_file(anchor);
        if let Err(fallback) = fs::rename(&temporary, anchor) {
            let _ = fs::remove_file(&temporary);
            return Err(Error::Custom(format!(
                "anchor update failed: {error} / {fallback}"
            )));
        }
    }
    Ok(())
}

/// Ensure the migrated tree has every directory the app expects, so a source tree
/// missing a folder does not leave the target unusable before the next launch.
fn ensure_tree_layout(data_dir: &Path) -> Result<()> {
    for child in ["memo", "keys", "clipboard_images", "captures"] {
        fs::create_dir_all(data_dir.join(child))?;
    }
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
        assert_eq!(
            fs::read_to_string(target.join(CONFIG_DIR_NAME).join("memo/item.txt")).unwrap(),
            "source"
        );
        let anchor_value: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(anchor).unwrap()).unwrap();
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

        let result = migrate_data_from(&source, &target, MigrationMode::Merge, &anchor).unwrap();
        assert_eq!(result, Some(target.join(CONFIG_DIR_NAME)));
        // Source wins for file conflicts.
        assert_eq!(
            fs::read_to_string(target_data.join("memo/item.txt")).unwrap(),
            "source"
        );
        let anchor_value: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(anchor).unwrap()).unwrap();
        assert_eq!(anchor_value["data_dir"].as_str(), target.to_str());
    }

    #[test]
    fn cancel_performs_no_write() {
        let dirs = TempDirs::new();
        let source = source_with_file(&dirs);
        let target = dirs.path("target");
        let anchor = dirs.path("anchor.json");
        fs::write(&anchor, "old-anchor").unwrap();

        assert_eq!(
            migrate_data_from(&source, &target, MigrationMode::Cancel, &anchor).unwrap(),
            None
        );
        assert!(!target.exists());
        assert_eq!(fs::read_to_string(anchor).unwrap(), "old-anchor");
    }

    #[test]
    fn same_path_migration_is_noop_and_keeps_anchor() {
        let dirs = TempDirs::new();
        let source = source_with_file(&dirs);
        let anchor = dirs.path("anchor.json");
        fs::write(&anchor, "old-anchor").unwrap();

        let result = migrate_data_from(
            &source,
            source.parent().unwrap(),
            MigrationMode::Replace,
            &anchor,
        )
        .unwrap();

        assert_eq!(result, None);
        assert!(source.join("memo/item.txt").exists());
        assert_eq!(fs::read_to_string(&anchor).unwrap(), "old-anchor");
    }

    #[test]
    fn migration_anchor_reads_back_as_data_dir() {
        let dirs = TempDirs::new();
        let source = source_with_file(&dirs);
        let target = dirs.path("target");
        let anchor = dirs.path("anchor.json");
        fs::write(&anchor, r#"{"data_dir":"old"}"#).unwrap();

        let migrated = migrate_data_from(&source, &target, MigrationMode::Merge, &anchor)
            .unwrap()
            .unwrap();

        let raw = fs::read_to_string(&anchor).unwrap();
        let value: serde_json::Value = serde_json::from_str(&raw).unwrap();
        let stored = PathBuf::from(value["data_dir"].as_str().unwrap());
        assert_eq!(stored, target);
        assert_eq!(stored_path_to_data_dir(&stored), Some(migrated));
    }

    #[test]
    fn stored_path_resolves_when_directory_exists() {
        let dirs = TempDirs::new();
        let base = dirs.path("base");
        assert_eq!(stored_path_to_data_dir(&base), None);

        fs::create_dir_all(base.join(CONFIG_DIR_NAME)).unwrap();
        assert_eq!(
            stored_path_to_data_dir(&base),
            Some(base.join(CONFIG_DIR_NAME))
        );
        assert_eq!(
            stored_path_to_data_dir(&base.join(CONFIG_DIR_NAME)),
            Some(base.join(CONFIG_DIR_NAME))
        );
    }

    #[test]
    fn normalize_strips_config_dir_suffix() {
        let path = PathBuf::from(r"D:\data\.memopaws-rust");
        assert_eq!(normalize_migration_base(&path), PathBuf::from(r"D:\data"));
        assert_eq!(
            normalize_migration_base(Path::new(r"D:\data")),
            PathBuf::from(r"D:\data")
        );
    }

    #[test]
    fn migration_creates_the_full_expected_tree_layout() {
        let dirs = TempDirs::new();
        let source = dirs.path("source/.memopaws-rust");
        fs::create_dir_all(source.join("memo")).unwrap();
        fs::write(source.join("setting.json"), "{}").unwrap();
        let target = dirs.path("target");
        let anchor = dirs.path("anchor.json");
        fs::write(&anchor, r#"{"data_dir":"old"}"#).unwrap();

        let migrated = migrate_data_from(&source, &target, MigrationMode::Merge, &anchor)
            .unwrap()
            .unwrap();

        for child in ["memo", "keys", "clipboard_images", "captures"] {
            assert!(
                migrated.join(child).is_dir(),
                "missing {child} after migration"
            );
        }
        assert!(migrated.join("setting.json").is_file());
        let anchor_value: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(&anchor).unwrap()).unwrap();
        assert_eq!(anchor_value["data_dir"].as_str(), target.to_str());
        assert!(
            !anchor.with_extension("tmp").exists(),
            "temp anchor file was left behind"
        );
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

    #[test]
    fn replace_mode_wipes_existing_target_and_copies_fresh_tree() {
        let dirs = TempDirs::new();
        let source = source_with_file(&dirs);
        let target = dirs.path("target");
        let target_data = target.join(CONFIG_DIR_NAME);
        fs::create_dir_all(&target_data).unwrap();
        fs::write(target_data.join("stale.txt"), "stale").unwrap();
        fs::write(target_data.join("memo"), "clashing").unwrap();
        let anchor = dirs.path("anchor.json");
        fs::write(&anchor, "old-anchor").unwrap();

        let result = migrate_data_from(&source, &target, MigrationMode::Replace, &anchor)
            .unwrap()
            .unwrap();

        assert_eq!(result, target_data);
        assert_eq!(
            fs::read_to_string(target_data.join("memo/item.txt")).unwrap(),
            "source"
        );
        assert!(!target_data.join("stale.txt").exists());
        assert!(target_data.join("memo").is_dir());
        let anchor_value: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(anchor).unwrap()).unwrap();
        assert_eq!(anchor_value["data_dir"].as_str(), target.to_str());
    }

    #[test]
    fn merge_conflict_dir_versus_file_is_rejected_and_state_is_preserved() {
        let dirs = TempDirs::new();
        let source = dirs.path("source");
        fs::create_dir_all(source.join(CONFIG_DIR_NAME).join("docs")).unwrap();
        fs::write(source.join(CONFIG_DIR_NAME).join("docs/note.txt"), "source").unwrap();
        let target = dirs.path("target");
        fs::create_dir_all(target.join(CONFIG_DIR_NAME)).unwrap();
        fs::write(
            target.join(CONFIG_DIR_NAME).join("docs"),
            "target file in the way",
        )
        .unwrap();
        let anchor = dirs.path("anchor.json");
        fs::write(&anchor, "old-anchor").unwrap();

        assert!(migrate_data_from(
            source.join(CONFIG_DIR_NAME).as_path(),
            &target,
            MigrationMode::Merge,
            &anchor
        )
        .is_err());
        assert_eq!(
            fs::read_to_string(target.join(CONFIG_DIR_NAME).join("docs")).unwrap(),
            "target file in the way"
        );
        assert_eq!(fs::read_to_string(anchor).unwrap(), "old-anchor");
    }

    #[test]
    fn normalize_migration_base_is_case_insensitive_about_config_dir() {
        assert_eq!(
            normalize_migration_base(Path::new(r"D:\Data\.MEMOPAWS-RUST")),
            PathBuf::from(r"D:\Data")
        );
        assert_eq!(
            normalize_migration_base(Path::new(r"D:\Data-ish")),
            PathBuf::from(r"D:\Data-ish")
        );
    }

    #[test]
    fn replace_migration_rejects_nonexistent_or_file_target_base() {
        let dirs = TempDirs::new();
        let source = source_with_file(&dirs);
        let anchor = dirs.path("anchor.json");

        let target_base_file = dirs.path("target-as-file");
        fs::write(&target_base_file, "not a directory").unwrap();
        assert!(
            migrate_data_from(&source, &target_base_file, MigrationMode::Replace, &anchor).is_err()
        );

        let source_itself = dirs.path("missing-source");
        assert!(migrate_data_from(
            &source_itself,
            dirs.path("t").as_path(),
            MigrationMode::Merge,
            &anchor
        )
        .is_err());
    }

    #[test]
    fn same_path_replace_never_removes_source_tree() {
        let dirs = TempDirs::new();
        let source = source_with_file(&dirs);
        let anchor = dirs.path("anchor.json");
        fs::write(&anchor, "keep-me").unwrap();

        let result = migrate_data_from(
            &source,
            source.parent().unwrap(),
            MigrationMode::Replace,
            &anchor,
        )
        .unwrap();
        assert_eq!(result, None);
        assert!(source.join("memo/item.txt").exists());
        assert_eq!(fs::read_to_string(anchor).unwrap(), "keep-me");
    }
}
