use std::{fs, path::PathBuf, time::{SystemTime, UNIX_EPOCH}};

use memopaws_core::paths;
use serde::{Deserialize, Serialize};

const MAX_CLIPBOARD_ITEMS: usize = 50;
const MAX_TEXT_LENGTH: usize = 50_000;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ClipboardItem {
    pub id: u64,
    pub time: String,
    pub content_type: String,
    pub text: Option<String>,
    pub image_path: Option<String>,
}

pub struct ClipboardManager {
    items: Vec<ClipboardItem>,
    path: PathBuf,
    images_dir: PathBuf,
    max_items: usize,
    next_id: u64,
}

impl ClipboardManager {
    pub fn load() -> Result<Self, String> {
        let path = paths::clipboard_path().map_err(|e| e.to_string())?;
        let images_dir = paths::clipboard_images_dir().map_err(|e| e.to_string())?;
        fs::create_dir_all(&images_dir).map_err(|e| e.to_string())?;

        let (items, next_id) = if path.exists() {
            let raw = fs::read_to_string(&path).map_err(|e| e.to_string())?;
            let items: Vec<ClipboardItem> = serde_json::from_str(&raw).unwrap_or_default();
            let next_id = items.iter().map(|i| i.id).max().unwrap_or(0) + 1;
            (items, next_id)
        } else {
            (Vec::new(), 1)
        };

        Ok(Self { items, path, images_dir, max_items: MAX_CLIPBOARD_ITEMS, next_id })
    }

    pub fn items(&self) -> &[ClipboardItem] { &self.items }

    pub fn max_items(&self) -> usize { self.max_items }

    pub fn set_max_items(&mut self, max_items: usize) -> Result<(), String> {
        let removed = self.items.split_off(max_items);
        for item in removed {
            if let Some(image_path) = item.image_path {
                let _ = fs::remove_file(self.images_dir.join(image_path));
            }
        }
        self.max_items = max_items;
        self.save()
    }

    pub fn add_text(&mut self, text: &str) -> Result<(), String> {
        let text = text.chars().take(MAX_TEXT_LENGTH).collect::<String>();
        if text.trim().is_empty() { return Ok(()); }
        if self.items.first().and_then(|i| i.text.as_deref()) == Some(&text) { return Ok(()); }
        self.add(ClipboardItem {
            id: self.next_id,
            time: now_str(),
            content_type: "text".into(),
            text: Some(text),
            image_path: None,
        })
    }

    pub fn add_image(&mut self, bytes: &[u8]) -> Result<(), String> {
        let filename = format!("{}.png", self.next_id);
        let image_path = self.images_dir.join(&filename);
        fs::create_dir_all(&self.images_dir).map_err(|e| e.to_string())?;
        fs::write(&image_path, bytes).map_err(|e| e.to_string())?;
        self.add(ClipboardItem {
            id: self.next_id,
            time: now_str(),
            content_type: "image".into(),
            text: None,
            image_path: Some(filename),
        })
    }

    fn add(&mut self, mut item: ClipboardItem) -> Result<(), String> {
        item.id = self.next_id;
        self.next_id += 1;
        self.items.insert(0, item);
        self.items.truncate(self.max_items);
        self.save()
    }

    pub fn delete(&mut self, id: u64) -> Result<(), String> {
        if let Some(pos) = self.items.iter().position(|i| i.id == id) {
            if let Some(ref image_path) = self.items[pos].image_path {
                let _ = fs::remove_file(self.images_dir.join(image_path));
            }
            self.items.remove(pos);
            self.save()?;
        }
        Ok(())
    }

    pub fn clear(&mut self) -> Result<(), String> {
        for item in &self.items {
            if let Some(ref image_path) = item.image_path {
                let _ = fs::remove_file(self.images_dir.join(image_path));
            }
        }
        self.items.clear();
        self.save()
    }

    pub fn get_image_bytes(&self, id: u64) -> Result<Vec<u8>, String> {
        let item = self.items.iter().find(|i| i.id == id).ok_or_else(|| "item not found".to_string())?;
        let image_path = item.image_path.as_ref().ok_or_else(|| "not an image item".to_string())?;
        fs::read(self.images_dir.join(image_path)).map_err(|e| e.to_string())
    }

    fn save(&self) -> Result<(), String> {
        if let Some(parent) = self.path.parent() { fs::create_dir_all(parent).map_err(|e| e.to_string())?; }
        let raw = serde_json::to_string_pretty(&self.items).map_err(|e| e.to_string())?;
        fs::write(&self.path, raw).map_err(|e| e.to_string())
    }
}

fn now_str() -> String {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs().to_string()).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manager(path: &std::path::Path) -> ClipboardManager {
        let images_dir = path.parent().unwrap().join("clipboard_images");
        let _ = std::fs::create_dir_all(&images_dir);
        let _ = std::fs::create_dir_all(path.parent().unwrap());
        ClipboardManager { items: vec![], path: path.to_path_buf(), images_dir, max_items: 3, next_id: 1 }
    }

    fn unique_dir() -> std::path::PathBuf {
        let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        std::env::temp_dir().join(format!("clip-test-{nanos}"))
    }

    #[test]
    fn add_text_deduplicates_consecutive_identical() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_text("hello").unwrap();
        m.add_text("hello").unwrap();
        assert_eq!(m.items.len(), 1);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn add_text_truncates_long_input() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        let long = "x".repeat(MAX_TEXT_LENGTH + 100);
        m.add_text(&long).unwrap();
        assert_eq!(m.items[0].text.as_deref().unwrap().len(), MAX_TEXT_LENGTH);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn add_image_stores_file_and_returns_item() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_image(b"png-data").unwrap();
        assert_eq!(m.items.len(), 1);
        assert_eq!(m.items[0].content_type, "image");
        assert!(m.items[0].image_path.is_some());
        let bytes = m.get_image_bytes(m.items[0].id).unwrap();
        assert_eq!(bytes, b"png-data");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn respects_max_items() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        for i in 0..5 { m.add_text(&format!("item-{i}")).unwrap(); }
        assert_eq!(m.items.len(), 3);
        assert_eq!(m.items[0].text.as_deref(), Some("item-4"));
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn runtime_max_items_truncates_items() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        for i in 0..3 { m.add_text(&format!("item-{i}")).unwrap(); }

        m.set_max_items(1).unwrap();

        assert_eq!(m.items().len(), 1);
        assert_eq!(m.items()[0].text.as_deref(), Some("item-2"));
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn delete_removes_item_and_image_file() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_image(b"img-data").unwrap();
        let id = m.items[0].id;
        let image_path = m.images_dir.join(format!("{id}.png"));
        assert!(image_path.exists());
        m.delete(id).unwrap();
        assert!(m.items.is_empty());
        assert!(!image_path.exists());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn clear_removes_all_items_and_images() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_image(b"img1").unwrap();
        m.add_image(b"img2").unwrap();
        m.clear().unwrap();
        assert!(m.items.is_empty());
        assert!(!m.images_dir.join("1.png").exists());
        assert!(!m.images_dir.join("2.png").exists());
        let _ = fs::remove_dir_all(&dir);
    }
}
