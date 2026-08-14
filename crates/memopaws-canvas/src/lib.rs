use std::{fs, path::PathBuf, time::{SystemTime, UNIX_EPOCH}};

use memopaws_core::paths;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CaptureRecord {
    pub id: u64,
    pub time: String,
    pub filename: String,
}

pub struct CaptureManager {
    captures_dir: PathBuf,
    records: Vec<CaptureRecord>,
    next_id: u64,
}

impl CaptureManager {
    pub fn load() -> Result<Self, String> {
        let captures_dir = paths::captures_dir().map_err(|e| e.to_string())?;
        fs::create_dir_all(&captures_dir).map_err(|e| e.to_string())?;
        let records_path = captures_dir.join("captures.json");
        let (records, next_id) = if records_path.exists() {
            let raw = fs::read_to_string(&records_path).map_err(|e| e.to_string())?;
            let records: Vec<CaptureRecord> = serde_json::from_str(&raw).unwrap_or_default();
            let next_id = records.iter().map(|r| r.id).max().unwrap_or(0) + 1;
            (records, next_id)
        } else {
            (Vec::new(), 1)
        };
        Ok(Self { captures_dir, records, next_id })
    }

    pub fn records(&self) -> &[CaptureRecord] { &self.records }

    pub fn add_capture(&mut self, bytes: &[u8]) -> Result<CaptureRecord, String> {
        let id = self.next_id;
        self.next_id += 1;
        let filename = format!("capture-{id}.png");
        fs::create_dir_all(&self.captures_dir).map_err(|e| e.to_string())?;
        fs::write(self.captures_dir.join(&filename), bytes).map_err(|e| e.to_string())?;
        let record = CaptureRecord { id, time: now_str(), filename: filename.clone() };
        self.records.insert(0, record.clone());
        self.save_records()?;
        Ok(record)
    }

    pub fn get_capture_path(&self, id: u64) -> Result<PathBuf, String> {
        let record = self.records.iter().find(|r| r.id == id).ok_or_else(|| "capture not found".to_string())?;
        Ok(self.captures_dir.join(&record.filename))
    }

    pub fn get_capture_bytes(&self, id: u64) -> Result<Vec<u8>, String> {
        let path = self.get_capture_path(id)?;
        fs::read(&path).map_err(|e| e.to_string())
    }

    pub fn delete(&mut self, id: u64) -> Result<(), String> {
        if let Some(pos) = self.records.iter().position(|r| r.id == id) {
            let path = self.captures_dir.join(&self.records[pos].filename);
            let _ = fs::remove_file(&path);
            self.records.remove(pos);
            self.save_records()?;
        }
        Ok(())
    }

    pub fn clear(&mut self) -> Result<(), String> {
        for record in &self.records {
            let _ = fs::remove_file(self.captures_dir.join(&record.filename));
        }
        self.records.clear();
        self.save_records()
    }

    fn save_records(&self) -> Result<(), String> {
        let path = self.captures_dir.join("captures.json");
        if let Some(parent) = path.parent() { fs::create_dir_all(parent).map_err(|e| e.to_string())?; }
        let raw = serde_json::to_string_pretty(&self.records).map_err(|e| e.to_string())?;
        fs::write(&path, raw).map_err(|e| e.to_string())
    }
}

fn now_str() -> String {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs().to_string()).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn unique_dir() -> std::path::PathBuf {
        let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let dir = std::env::temp_dir().join(format!("capture-test-{nanos}"));
        let _ = std::fs::create_dir_all(&dir);
        dir
    }

    #[test]
    fn add_capture_stores_file_and_returns_record() {
        let dir = unique_dir();
        let mut m = CaptureManager { captures_dir: dir.clone(), records: vec![], next_id: 1 };
        let record = m.add_capture(b"png-data").unwrap();
        assert_eq!(record.id, 1);
        assert!(dir.join("capture-1.png").exists());
        let bytes = m.get_capture_bytes(1).unwrap();
        assert_eq!(bytes, b"png-data");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn delete_removes_record_and_file() {
        let dir = unique_dir();
        let mut m = CaptureManager { captures_dir: dir.clone(), records: vec![], next_id: 1 };
        m.add_capture(b"data").unwrap();
        assert!(dir.join("capture-1.png").exists());
        m.delete(1).unwrap();
        assert!(m.records.is_empty());
        assert!(!dir.join("capture-1.png").exists());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn clear_removes_all() {
        let dir = unique_dir();
        let mut m = CaptureManager { captures_dir: dir.clone(), records: vec![], next_id: 1 };
        m.add_capture(b"a").unwrap();
        m.add_capture(b"b").unwrap();
        m.clear().unwrap();
        assert!(m.records.is_empty());
        assert!(!dir.join("capture-1.png").exists());
        assert!(!dir.join("capture-2.png").exists());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn persistence_round_trip_reloads_records_and_files() {
        let dir = unique_dir();
        let mut m = CaptureManager { captures_dir: dir.clone(), records: vec![], next_id: 1 };
        m.add_capture(b"first").unwrap();
        m.add_capture(b"second").unwrap();
        let first_id = m.records()[1].id;
        drop(m);

        let raw = fs::read_to_string(dir.join("captures.json")).unwrap();
        let records: Vec<CaptureRecord> = serde_json::from_str(&raw).unwrap();
        let next_id = records.iter().map(|r| r.id).max().unwrap_or(0) + 1;
        let reloaded = CaptureManager { captures_dir: dir.clone(), records, next_id };

        assert_eq!(reloaded.records().len(), 2);
        assert_eq!(reloaded.records()[0].id, 2);
        assert_eq!(reloaded.records()[0].filename, "capture-2.png");
        assert_eq!(reloaded.get_capture_bytes(first_id).unwrap(), b"first");

        let mut writable = reloaded;
        let record = writable.add_capture(b"third").unwrap();
        assert_eq!(record.id, 3);
        assert_eq!(record.filename, "capture-3.png");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn missing_record_lookup_and_delete_are_safe() {
        let dir = unique_dir();
        let mut m = CaptureManager { captures_dir: dir.clone(), records: vec![], next_id: 1 };
        m.add_capture(b"data").unwrap();

        assert!(m.get_capture_path(999).is_err());
        assert!(m.get_capture_bytes(999).is_err());
        m.delete(999).unwrap();
        assert_eq!(m.records().len(), 1);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn ids_and_filenames_increment_from_stored_next_id() {
        let dir = unique_dir();
        let mut m = CaptureManager { captures_dir: dir.clone(), records: vec![], next_id: 5 };
        let first = m.add_capture(b"a").unwrap();
        let second = m.add_capture(b"b").unwrap();
        assert_eq!(first.id, 5);
        assert_eq!(second.id, 6);
        assert_eq!(first.filename, "capture-5.png");
        assert_eq!(second.filename, "capture-6.png");
        assert!(dir.join("capture-5.png").exists());
        assert!(dir.join("capture-6.png").exists());
        let _ = fs::remove_dir_all(&dir);
    }
}
