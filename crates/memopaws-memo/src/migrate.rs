use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;

use crate::model::Memo;
use crate::storage::{list_memos, safe_memo_path, sanitize_filename, write_migrated_memo, MemoError, Result};

pub fn migrate_legacy_memos(legacy_path: &Path, memo_dir: &Path) -> Result<usize> {
    if !legacy_path.exists() {
        return Ok(0);
    }
    fs::create_dir_all(memo_dir)?;
    let bytes = fs::read(legacy_path)?;
    let memos: Vec<Memo> = serde_json::from_slice(&bytes).map_err(|error| MemoError::InvalidData(error.to_string()))?;
    let mut source_ids = HashSet::new();
    let mut source_files = HashSet::new();
    let mut plan = Vec::new();
    let existing = list_memos(memo_dir)?;
    let existing_by_id: HashMap<_, _> = existing.iter().map(|memo| (memo.id, memo)).collect();

    for memo in memos {
        if !source_ids.insert(memo.id) {
            return Err(MemoError::Conflict(format!("duplicate legacy memo id {}", memo.id)));
        }
        let filename = memo.file.clone().unwrap_or_else(|| sanitize_filename(&memo.title, memo.id));
        safe_memo_path(memo_dir, &filename)?;
        if !source_files.insert(filename.clone()) {
            return Err(MemoError::Conflict(format!("duplicate legacy filename {filename}")));
        }
        let target = memo_dir.join(&filename);
        if let Some(found) = existing_by_id.get(&memo.id) {
            if found.file.as_deref() != Some(filename.as_str()) || !equivalent(found, &memo) {
                return Err(MemoError::Conflict(format!("legacy memo {} conflicts with existing data", memo.id)));
            }
        } else if target.exists() {
            return Err(MemoError::Conflict(format!("legacy target {filename} has different or unreadable content")));
        } else {
            plan.push((memo, filename));
        }
    }

    for (memo, filename) in &plan {
        write_migrated_memo(memo_dir, memo.clone(), filename)?;
    }
    let backup = available_backup_path(legacy_path);
    fs::rename(legacy_path, backup)?;
    Ok(plan.len())
}

fn equivalent(left: &Memo, right: &Memo) -> bool {
    left.id == right.id
        && left.time == right.time
        && left.created == right.created
        && left.modified == right.modified
        && left.title == right.title
        && left.content == right.content
        && left.tags == right.tags
}

fn available_backup_path(legacy_path: &Path) -> std::path::PathBuf {
    let name = legacy_path.file_name().and_then(|value| value.to_str()).unwrap_or("memo.json");
    let first = legacy_path.with_file_name(format!("{name}.migrated"));
    if !first.exists() {
        return first;
    }
    for suffix in 1.. {
        let candidate = legacy_path.with_file_name(format!("{name}.migrated.{suffix}"));
        if !candidate.exists() {
            return candidate;
        }
    }
    unreachable!()
}
