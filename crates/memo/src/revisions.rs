use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::storage::MemoError;

/// Per-memo revision history: the previous content is snapshotted before every
/// content-changing update, newest first, capped so a chatty memo cannot grow
/// the store without bounds.
pub const REVISIONS_MAX: usize = 10;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Revision {
    pub time: String,
    pub content: String,
}

fn revisions_file(memo_dir: &Path, id: i64) -> PathBuf {
    memo_dir.join("revisions").join(format!("{id}.json"))
}

// Stored inside the memo directory as JSON (list_memos only reads top-level .md
// files, so the subfolder is invisible to the memo list and travels with data
// migrations).
pub fn list_revisions(memo_dir: &Path, id: i64) -> Result<Vec<Revision>, MemoError> {
    let text = match fs::read_to_string(revisions_file(memo_dir, id)) {
        Ok(text) => text,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(error.into()),
    };
    serde_json::from_str(&text)
        .map_err(|_| MemoError::InvalidData(format!("corrupt revision store for memo {id}")))
}

pub fn snapshot_revision(memo_dir: &Path, id: i64, previous_content: &str, time: &str) -> Result<(), MemoError> {
    let mut revisions = list_revisions(memo_dir, id)?;
    // Saving identical content must not accumulate noise entries.
    if revisions.first().map(|revision| revision.content.as_str()) == Some(previous_content) {
        return Ok(());
    }
    revisions.insert(0, Revision { time: time.to_string(), content: previous_content.to_string() });
    revisions.truncate(REVISIONS_MAX);
    write_revisions(memo_dir, id, &revisions)
}

pub fn delete_revision(memo_dir: &Path, id: i64, time: &str) -> Result<(), MemoError> {
    let mut revisions = list_revisions(memo_dir, id)?;
    let before = revisions.len();
    revisions.retain(|revision| revision.time != time);
    if revisions.len() == before {
        return Err(MemoError::InvalidData(format!("revision {time} not found")));
    }
    write_revisions(memo_dir, id, &revisions)
}

fn write_revisions(memo_dir: &Path, id: i64, revisions: &[Revision]) -> Result<(), MemoError> {
    let file = revisions_file(memo_dir, id);
    if let Some(parent) = file.parent() {
        fs::create_dir_all(parent)?;
    }
    let serialized = serde_json::to_string(revisions)
        .map_err(|_| MemoError::InvalidData("revisions failed to serialize".into()))?;
    crate::storage::atomic_write_replace(&file, &serialized)
}

#[cfg(test)]
mod tests {
    use super::*;

    struct TempDir(PathBuf);

    impl TempDir {
        fn new(tag: &str) -> Self {
            let path = std::env::temp_dir().join(format!(
                "memopaws-revisions-{tag}-{}",
                std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()
            ));
            fs::create_dir_all(&path).unwrap();
            TempDir(path)
        }
    }

    impl Drop for TempDir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn snapshots_are_newest_first_and_capped() {
        let dir = TempDir::new("cap");
        for index in 0..25 {
            snapshot_revision(&dir.0, 1, &format!("content {index}"), &format!("t{index}")).unwrap();
        }
        let revisions = list_revisions(&dir.0, 1).unwrap();
        assert_eq!(revisions.len(), REVISIONS_MAX);
        assert_eq!(revisions[0].content, "content 24");
        assert_eq!(revisions[0].time, "t24");
        assert_eq!(revisions.last().unwrap().content, "content 15");
    }

    #[test]
    fn delete_revision_removes_one_entry_and_rejects_unknown_times() {
        let dir = TempDir::new("delete");
        snapshot_revision(&dir.0, 3, "older", "t1").unwrap();
        snapshot_revision(&dir.0, 3, "newer", "t2").unwrap();
        delete_revision(&dir.0, 3, "t1").unwrap();
        let revisions = list_revisions(&dir.0, 3).unwrap();
        assert_eq!(revisions.len(), 1);
        assert_eq!(revisions[0].content, "newer");
        assert!(delete_revision(&dir.0, 3, "missing").is_err());
    }

    #[test]
    fn identical_content_does_not_accumulate_entries() {
        let dir = TempDir::new("dedupe");
        snapshot_revision(&dir.0, 2, "same", "t1").unwrap();
        snapshot_revision(&dir.0, 2, "same", "t2").unwrap();
        let revisions = list_revisions(&dir.0, 2).unwrap();
        assert_eq!(revisions.len(), 1);
        assert_eq!(revisions[0].time, "t1");
    }

    #[test]
    fn missing_store_lists_empty_and_unknown_ids_are_independent() {
        let dir = TempDir::new("missing");
        assert!(list_revisions(&dir.0, 7).unwrap().is_empty());
        snapshot_revision(&dir.0, 8, "kept", "t1").unwrap();
        assert!(list_revisions(&dir.0, 7).unwrap().is_empty());
        assert_eq!(list_revisions(&dir.0, 8).unwrap()[0].content, "kept");
    }
}
