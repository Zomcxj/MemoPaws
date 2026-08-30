use std::{fs, io::Write, path::{Path, PathBuf}, time::{SystemTime, UNIX_EPOCH}};

use memopaws_core::{paths, Result};
use serde::{Deserialize, Serialize};
use tempfile::NamedTempFile;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct HistoryRecord {
    pub time: String,
    #[serde(rename = "type")]
    pub typ: String,
    pub text: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ocr_text: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub translate_text: Option<String>,
    #[serde(flatten)]
    pub extra: serde_json::Map<String, serde_json::Value>,
}

pub struct HistoryManager { records: Vec<HistoryRecord>, max_items: usize, path: PathBuf }

impl Default for HistoryManager {
    fn default() -> Self { Self { records: Vec::new(), max_items: 100, path: PathBuf::new() } }
}

impl HistoryManager {
    pub fn new() -> Self { Self::default() }

    pub fn load(mut self) -> Result<Self> {
        self.max_items = crate::config::AppConfig::load().unwrap_or_default().history_max_items.unwrap_or(100);
        self.path = paths::history_path()?;
        self.read()?;
        Ok(self)
    }

    pub fn with_path(path: impl Into<PathBuf>, max_items: usize) -> Result<Self> {
        let mut manager = Self { records: Vec::new(), max_items, path: path.into() };
        manager.read()?;
        Ok(manager)
    }

    fn read(&mut self) -> Result<()> {
        if self.path.exists() { self.records = serde_json::from_str(&fs::read_to_string(&self.path)?)?; self.records.truncate(self.max_items); }
        Ok(())
    }

    pub fn save(&self) -> Result<()> {
        if let Some(parent) = self.path.parent() { fs::create_dir_all(parent)?; }
        let parent = self.path.parent().unwrap_or_else(|| Path::new("."));
        let mut temporary = NamedTempFile::new_in(parent)?;
        serde_json::to_writer_pretty(&mut temporary, &self.records)?;
        temporary.write_all(b"\n")?;
        temporary.as_file().sync_all()?;
        temporary.persist(&self.path).map_err(|error| error.error)?;
        Ok(())
    }

    pub fn records(&self) -> &[HistoryRecord] { &self.records }
    pub fn into_records(self) -> Vec<HistoryRecord> { self.records }

    pub fn max_items(&self) -> usize { self.max_items }

    pub fn set_max_items(&mut self, max_items: usize) -> Result<()> {
        self.max_items = max_items;
        self.records.truncate(max_items);
        self.save()
    }

    pub fn add_success(&mut self, typ: impl Into<String>, text: impl Into<String>, ocr_text: Option<&str>, translate_text: Option<&str>) -> Result<()> {
        self.records.insert(0, HistoryRecord { time: now_str(), typ: typ.into(), text: text.into().chars().take(5000).collect(), ocr_text: ocr_text.map(str::to_owned), translate_text: translate_text.map(str::to_owned), extra: serde_json::Map::new() });
        self.records.truncate(self.max_items);
        self.save()
    }

    pub fn add_record(&mut self, typ: impl Into<String>, text: impl Into<String>) -> Result<()> { self.add_success(typ, text, None, None) }
    pub fn clear(&mut self) -> Result<()> { self.records.clear(); self.save() }
    pub fn delete_record(&mut self, index: usize) -> Result<()> { if index < self.records.len() { self.records.remove(index); self.save()?; } Ok(()) }
}

fn now_str() -> String { SystemTime::now().duration_since(UNIX_EPOCH).map(|time| time.as_secs().to_string()).unwrap_or_default() }

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn runtime_max_items_truncates_and_persists_records() {
        let path = std::env::temp_dir().join(format!("memopaws-history-runtime-{}.json", now_str()));
        let mut manager = HistoryManager::with_path(&path, 3).unwrap();
        for index in 0..5 {
            manager.add_record("test", format!("record-{index}")).unwrap();
        }

        manager.set_max_items(2).unwrap();

        assert_eq!(manager.records().len(), 2);
        let reloaded = HistoryManager::with_path(&path, 2).unwrap();
        assert_eq!(reloaded.records().len(), 2);
        let _ = fs::remove_file(path);
    }
}
