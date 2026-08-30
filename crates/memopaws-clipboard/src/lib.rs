use std::{
    collections::hash_map::DefaultHasher,
    fs,
    hash::{Hash, Hasher},
    path::PathBuf,
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use arboard::ImageData;
use memopaws_core::paths;
use serde::{Deserialize, Serialize};

const MAX_CLIPBOARD_ITEMS: usize = 50;
const MAX_TEXT_LENGTH: usize = 50_000;
const LISTEN_POLL_INTERVAL: Duration = Duration::from_millis(700);

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ClipboardItem {
    pub id: u64,
    pub time: String,
    pub content_type: String,
    pub text: Option<String>,
    pub image_path: Option<String>,
    pub locked: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hash: Option<u64>,
}

impl<'de> Deserialize<'de> for ClipboardItem {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        #[derive(Deserialize)]
        struct Raw {
            #[serde(default)]
            id: Option<u64>,
            #[serde(default)]
            time: Option<String>,
            #[serde(default)]
            content_type: Option<String>,
            #[serde(default)]
            kind: Option<String>,
            #[serde(default)]
            text: Option<String>,
            #[serde(default)]
            image_path: Option<String>,
            #[serde(default)]
            locked: bool,
            #[serde(default)]
            hash: Option<u64>,
        }
        let raw = Raw::deserialize(deserializer)?;
        let content_type = raw.content_type.or(raw.kind).unwrap_or_else(|| "text".into());
        let image_path = match raw.image_path {
            Some(path) if !path.is_empty() => Some(path),
            _ if content_type == "image" => raw.text.clone(),
            _ => None,
        };
        let text = if content_type == "image" { None } else { raw.text };
        Ok(ClipboardItem {
            id: raw.id.unwrap_or(0),
            time: raw.time.unwrap_or_default(),
            content_type,
            text,
            image_path,
            locked: raw.locked,
            hash: raw.hash,
        })
    }
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
        Self::load_from(path, images_dir)
    }

    fn load_from(path: PathBuf, images_dir: PathBuf) -> Result<Self, String> {
        fs::create_dir_all(&images_dir).map_err(|e| e.to_string())?;

        let (items, dirty, next_id) = if path.exists() {
            let raw = fs::read_to_string(&path).map_err(|e| e.to_string())?;
            let parsed: Vec<ClipboardItem> = serde_json::from_str(&raw).unwrap_or_default();
            let mut dirty = false;
            let mut items = Vec::with_capacity(parsed.len());
            for mut item in parsed {
                if item.id == 0 {
                    item.id = items.len() as u64 + 1;
                    dirty = true;
                }
                if let Some(unix) = python_time_to_unix(&item.time) {
                    item.time = unix.to_string();
                    dirty = true;
                }
                items.push(item);
            }
            let next_id = items.iter().map(|i| i.id).max().unwrap_or(0) + 1;
            (items, dirty, next_id)
        } else {
            (Vec::new(), false, 1)
        };

        let manager = Self { items, path, images_dir, max_items: MAX_CLIPBOARD_ITEMS, next_id };
        if dirty { manager.save()?; }
        Ok(manager)
    }

    #[cfg(test)]
    fn load_with(path: &std::path::Path) -> Result<Self, String> {
        Self::load_from(path.to_path_buf(), path.parent().unwrap().join("clipboard_images"))
    }

    pub fn items(&self) -> &[ClipboardItem] { &self.items }

    pub fn max_items(&self) -> usize { self.max_items }

    pub fn set_max_items(&mut self, max_items: usize) -> Result<(), String> {
        let removed = self.items.split_off(max_items.min(self.items.len()));
        let mut kept = Vec::new();
        for item in removed {
            if item.locked {
                kept.push(item);
                continue;
            }
            if let Some(image_path) = item.image_path {
                let _ = fs::remove_file(self.images_dir.join(image_path));
            }
        }
        self.items.extend(kept);
        self.items.sort_by(|left, right| right.time.cmp(&left.time).then(right.id.cmp(&left.id)));
        self.max_items = max_items;
        self.save()
    }

    pub fn add_text(&mut self, text: &str) -> Result<(), String> {
        let text = text.chars().take(MAX_TEXT_LENGTH).collect::<String>();
        if text.trim().is_empty() { return Ok(()); }
        // 同内容只保存一条；重复复制旧记录时刷新时间并置顶
        if let Some(pos) = self.items.iter().position(|i| i.text.as_deref() == Some(&text)) {
            return self.promote(pos, None);
        }
        self.add(ClipboardItem {
            id: self.next_id,
            time: now_str(),
            content_type: "text".into(),
            text: Some(text),
            image_path: None,
            locked: false,
            hash: None,
        })
    }

    pub fn add_image(&mut self, bytes: &[u8]) -> Result<(), String> {
        let hash = bytes_hash(bytes);
        if let Some(pos) = self.find_image(hash)? {
            return self.promote(pos, Some(hash));
        }
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
            locked: false,
            hash: Some(hash),
        })
    }

    /// 按内容哈希查找已存的同图记录；旧记录缺哈希时读文件惰性补算
    fn find_image(&self, hash: u64) -> Result<Option<usize>, String> {
        for (pos, item) in self.items.iter().enumerate() {
            if item.content_type != "image" { continue; }
            match item.hash {
                Some(existing) if existing == hash => return Ok(Some(pos)),
                Some(_) => {}
                None => {
                    let path = item.image_path.as_ref().map(|p| self.images_dir.join(p));
                    let matched = path
                        .and_then(|path| fs::read(path).ok())
                        .map(|stored| bytes_hash(&stored) == hash)
                        .unwrap_or(false);
                    if matched { return Ok(Some(pos)); }
                }
            }
        }
        Ok(None)
    }

    /// 刷新时间并移到列表顶部；顺带回填旧记录缺失的哈希
    fn promote(&mut self, pos: usize, backfill_hash: Option<u64>) -> Result<(), String> {
        let mut item = self.items.remove(pos);
        item.time = now_str();
        if backfill_hash.is_some() { item.hash = backfill_hash; }
        self.items.insert(0, item);
        self.save()
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
            if self.items[pos].locked { return Err("clipboard item is locked".into()); }
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
            if item.locked { continue; }
            if let Some(ref image_path) = item.image_path {
                let _ = fs::remove_file(self.images_dir.join(image_path));
            }
        }
        self.items.retain(|item| item.locked);
        self.save()
    }

    pub fn set_locked(&mut self, id: u64, locked: bool) -> Result<(), String> {
        let item = self.items.iter_mut().find(|item| item.id == id).ok_or_else(|| "item not found".to_string())?;
        item.locked = locked;
        self.save()
    }

    pub fn update_text(&mut self, id: u64, text: &str) -> Result<(), String> {
        let text = text.chars().take(MAX_TEXT_LENGTH).collect::<String>();
        if text.trim().is_empty() { return Err("clipboard text cannot be empty".into()); }
        let item = self.items.iter_mut().find(|item| item.id == id).ok_or_else(|| "item not found".to_string())?;
        if item.content_type != "text" { return Err("clipboard item is not text".into()); }
        item.text = Some(text);
        item.time = now_str();
        self.save()
    }

    pub fn delete_many(&mut self, ids: &[u64]) -> Result<usize, String> {
        let mut deleted = 0;
        let mut kept = Vec::with_capacity(self.items.len());
        for item in self.items.drain(..) {
            if ids.contains(&item.id) && !item.locked {
                if let Some(image_path) = item.image_path.as_ref() { let _ = fs::remove_file(self.images_dir.join(image_path)); }
                deleted += 1;
            } else { kept.push(item); }
        }
        self.items = kept;
        self.save()?;
        Ok(deleted)
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

/// 图片内容哈希，用于识别重复复制的同图
fn bytes_hash(bytes: &[u8]) -> u64 {
    use std::hash::{Hash, Hasher};
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    bytes.hash(&mut hasher);
    hasher.finish()
}

/// Convert a Python-edition timestamp (`"YYYY-MM-DD HH:MM:SS"`) to unix seconds.
/// Returns `None` when the string is not in that shape (e.g. already unix seconds).
fn python_time_to_unix(value: &str) -> Option<u64> {
    if value.len() != 19 {
        return None;
    }
    let bytes = value.as_bytes();
    if bytes[4] != b'-' || bytes[7] != b'-' || bytes[10] != b' ' || bytes[13] != b':' || bytes[16] != b':' {
        return None;
    }
    let year: u64 = value[0..4].parse().ok()?;
    let month: u64 = value[5..7].parse().ok()?;
    let day: u64 = value[8..10].parse().ok()?;
    let hour: u64 = value[11..13].parse().ok()?;
    let minute: u64 = value[14..16].parse().ok()?;
    let second: u64 = value[17..19].parse().ok()?;
    if month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59 || second > 60 {
        return None;
    }
    let days = days_from_civil(year, month, day)?;
    Some(days * 86_400 + hour * 3_600 + minute * 60 + second)
}

/// Days since 1970-01-01 (Howard Hinnant's days_from_civil algorithm).
fn days_from_civil(year: u64, month: u64, day: u64) -> Option<u64> {
    if year < 1970 { return None; }
    let year = year as i64;
    let month = month as i64;
    let day = day as i64;
    let year = year - (month <= 2) as i64;
    let era = (if year >= 0 { year } else { year - 399 }) / 400;
    let yoe = year - era * 400;
    let doy = (153 * (month + (if month > 2 { -3 } else { 9 })) + 2) / 5 + day - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    let days = era * 146_097 + doe - 719_468;
    if days < 0 { return None; }
    Some(days as u64)
}

/// Spawn a background thread that polls the system clipboard every ~700ms.
/// `on_text` is invoked with new text and `on_image` with PNG-encoded bytes;
/// callbacks fire only after the clipboard content actually changes.
/// The thread runs until the process exits or the returned handle is joined;
/// transient read failures are retried silently without panicking.
pub fn spawn_listener(
    on_text: impl Fn(&str) + Send + 'static,
    on_image: impl Fn(Vec<u8>) + Send + 'static,
) -> Result<thread::JoinHandle<()>, String> {
    let mut clipboard = arboard::Clipboard::new().map_err(|error| error.to_string())?;
    thread::Builder::new()
        .name("clipboard-listener".into())
        .spawn(move || {
            let mut last_text_hash: u64 = 0;
            let mut last_image_hash: u64 = 0;
            loop {
                // Explorer's file copy puts BOTH a CF_HDROP file list AND the
                // file path as CF_UNICODETEXT on the clipboard. The file list
                // must win, otherwise the path is captured as plain text and
                // copied image files never reach the image pipeline.
                if let Some(png) = read_file_list_image() {
                    let hash = hash_of(&png);
                    if hash != last_image_hash {
                        last_image_hash = hash;
                        on_image(png);
                    }
                } else if let Ok(image) = clipboard.get_image() {
                    let hash = image_hash(&image);
                    if hash != last_image_hash {
                        last_image_hash = hash;
                        if let Ok(png) = encode_png(&image) {
                            on_image(png);
                        }
                    }
                } else if let Ok(text) = clipboard.get_text() {
                    // A delayed CF_HDROP read can lose a short clipboard lock race.
                    // Explorer also exposes the copied file as text, so recover the
                    // image directly from that path before treating it as text.
                    if let Some(png) = read_image_path(&text) {
                        let hash = hash_of(&png);
                        if hash != last_image_hash {
                            last_image_hash = hash;
                            on_image(png);
                        }
                        thread::sleep(LISTEN_POLL_INTERVAL);
                        continue;
                    }
                    let hash = hash_of(text.as_bytes());
                    if hash != last_text_hash && !text.is_empty() {
                        last_text_hash = hash;
                        on_text(&text);
                    }
                }
                thread::sleep(LISTEN_POLL_INTERVAL);
            }
        })
        .map_err(|error| error.to_string())
}

fn hash_of(bytes: &[u8]) -> u64 {
    let mut hasher = DefaultHasher::new();
    bytes.hash(&mut hasher);
    hasher.finish()
}

fn image_hash(image: &ImageData) -> u64 {
    let mut hasher = DefaultHasher::new();
    image.width.hash(&mut hasher);
    image.height.hash(&mut hasher);
    image.bytes.hash(&mut hasher);
    hasher.finish()
}

fn encode_png(image: &ImageData) -> Result<Vec<u8>, String> {
    let raw = image::RgbaImage::from_raw(
        image.width as u32,
        image.height as u32,
        image.bytes.as_ref().to_vec(),
    )
    .ok_or_else(|| "invalid clipboard image dimensions".to_string())?;
    let mut bytes = Vec::new();
    raw.write_to(&mut std::io::Cursor::new(&mut bytes), image::ImageFormat::Png)
        .map_err(|error| error.to_string())?;
    Ok(bytes)
}

/// Reads the Windows clipboard's file list (CF_HDROP, e.g. copying a file in Explorer)
/// and re-encodes the first image file as PNG. Mirrors the Python edition's
/// `mime.hasUrls()` handling. Returns `None` when no copyable image file is present.
pub fn read_file_list_image() -> Option<Vec<u8>> {
    use clipboard_win::Getter;
    let mut clip = None;
    for _ in 0..5 {
        if let Ok(candidate) = clipboard_win::Clipboard::new() {
            clip = Some(candidate);
            break;
        }
        thread::sleep(Duration::from_millis(5));
    }
    let _clip = clip?;
    let mut paths: Vec<String> = Vec::new();
    clipboard_win::formats::FileList.read_clipboard(&mut paths).ok()?;
    for path in paths {
        if let Some(png) = read_image_path(&path) {
            return Some(png);
        }
    }
    None
}

fn is_supported_image_extension(extension: &str) -> bool {
    matches!(extension.to_ascii_lowercase().as_str(), "png" | "jpg" | "jpeg" | "bmp" | "webp" | "gif")
}

fn is_supported_image_path(path: &str) -> bool {
    std::path::Path::new(path.trim())
        .extension()
        .and_then(|extension| extension.to_str())
        .is_some_and(is_supported_image_extension)
}

pub fn read_image_path(path: &str) -> Option<Vec<u8>> {
    if !is_supported_image_path(path) {
        return None;
    }
    let bytes = fs::read(path.trim()).ok()?;
    let decoded = image::load_from_memory(&bytes).ok()?;
    let mut png = Vec::new();
    decoded.write_to(&mut std::io::Cursor::new(&mut png), image::ImageFormat::Png).ok()?;
    Some(png)
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
    fn recopying_old_text_refreshes_time_and_promotes_to_top() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_text("old").unwrap();
        m.add_text("new").unwrap();
        assert_eq!(m.items[0].text.as_deref(), Some("new"));
        m.items[0].time = "1".into(); // 人为把顶部记录时间拨旧，确保断言不靠运气
        std::thread::sleep(std::time::Duration::from_millis(1100));
        m.add_text("old").unwrap();
        assert_eq!(m.items.len(), 2, "重复复制旧文本不应新增记录");
        assert_eq!(m.items[0].text.as_deref(), Some("old"), "旧记录应被置顶");
        let old_time: u64 = m.items[0].time.parse().unwrap();
        assert!(old_time > 1, "置顶记录时间应刷新");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn recopying_same_image_deduplicates_and_promotes() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_image(b"image-bytes").unwrap();
        m.add_text("later-text").unwrap();
        std::thread::sleep(std::time::Duration::from_millis(1100));
        m.add_image(b"image-bytes").unwrap();
        assert_eq!(m.items.len(), 2, "重复复制同图不应新增记录");
        assert_eq!(m.items[0].content_type, "image", "同图记录应被置顶");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn legacy_image_without_hash_is_deduplicated_by_file_content() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_image(b"legacy-image").unwrap();
        // 模拟旧版记录：清掉哈希字段
        m.items[0].hash = None;
        m.save().unwrap();
        let mut m = ClipboardManager::load_from(
            dir.join("clipboard.json"),
            dir.join("clipboard_images"),
        ).unwrap();
        m.add_image(b"legacy-image").unwrap();
        assert_eq!(m.items.len(), 1, "旧记录无哈希时应按文件内容去重");
        assert_eq!(m.items[0].hash, Some(bytes_hash(b"legacy-image")), "去重后应回填哈希");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn set_max_items_above_current_count_is_safe() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_text("one").unwrap();
        assert!(m.set_max_items(50).is_ok());
        assert_eq!(m.items().len(), 1);
        assert_eq!(m.max_items(), 50);
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

    #[test]
    fn locked_items_cannot_be_deleted_or_cleared() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_text("locked").unwrap();
        m.add_text("unlocked").unwrap();
        let locked_id = m.items[1].id;
        m.set_locked(locked_id, true).unwrap();

        assert_eq!(m.delete(locked_id), Err("clipboard item is locked".into()));
        m.clear().unwrap();

        assert_eq!(m.items().len(), 1);
        assert_eq!(m.items()[0].id, locked_id);
        assert!(m.items()[0].locked);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn old_json_without_locked_field_defaults_to_unlocked() {
        let json = r#"[{"id":1,"time":"1","content_type":"text","text":"legacy","image_path":null}]"#;

        let items: Vec<ClipboardItem> = serde_json::from_str(json).unwrap();

        assert_eq!(items.len(), 1);
        assert!(!items[0].locked);
    }

    #[test]
    fn python_format_text_record_is_decoded() {
        let json = r#"[{"time":"2026-08-07 14:30:00","text":"hello world","locked":false,"kind":"text"}]"#;

        let items: Vec<ClipboardItem> = serde_json::from_str(json).unwrap();

        assert_eq!(items.len(), 1);
        assert_eq!(items[0].content_type, "text");
        assert_eq!(items[0].text.as_deref(), Some("hello world"));
        assert_eq!(items[0].image_path, None);
        assert_eq!(items[0].id, 0);
        assert_eq!(items[0].time, "2026-08-07 14:30:00");
    }

    #[test]
    fn python_format_image_uses_kind_and_absolute_path() {
        let json = r#"[{"time":"2026-08-07 14:30:01","text":"5.png","locked":false,"kind":"image","image_path":"C:\\Memopaws\\.memopaws\\clipboard_images\\5.png","image_hash":"abc","image_size":[640,480]}]"#;

        let items: Vec<ClipboardItem> = serde_json::from_str(json).unwrap();

        assert_eq!(items.len(), 1);
        assert_eq!(items[0].content_type, "image");
        assert_eq!(items[0].text, None);
        assert_eq!(items[0].image_path.as_deref(), Some(r"C:\Memopaws\.memopaws\clipboard_images\5.png"));
        assert_eq!(items[0].id, 0);
    }

    #[test]
    fn python_time_normalized_to_unix_seconds() {
        assert_eq!(python_time_to_unix("2026-08-07 14:30:00"), Some(1786113000));
        assert_eq!(python_time_to_unix("1723000000"), None);
        assert_eq!(python_time_to_unix("garbage"), None);
    }

    #[test]
    fn load_python_clipboard_json_normalizes_ids_and_times_and_persists() {
        let dir = unique_dir();
        let json = r#"[{"time":"2026-08-07 14:30:00","text":"first","locked":false,"kind":"text"},{"time":"2026-08-07 15:00:00","text":"second","locked":true,"kind":"text"}]"#;
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("clipboard.json"), json).unwrap();

        let m = ClipboardManager::load_with(&dir.join("clipboard.json")).unwrap();
        assert_eq!(m.items().len(), 2);
        assert_eq!(m.items()[0].id, 1);
        assert_eq!(m.items()[1].id, 2);
        assert!(m.items()[0].time.parse::<u64>().is_ok());
        assert!(m.items()[1].time.parse::<u64>().is_ok());
        let raw = fs::read_to_string(dir.join("clipboard.json")).unwrap();
        assert!(raw.contains("\"content_type\""));
        assert!(raw.contains("\"id\""));
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn delete_many_keeps_locked_items_and_removes_requested_images() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_image(b"remove").unwrap();
        let image_id = m.items[0].id;
        let image_path = m.images_dir.join(format!("{image_id}.png"));
        m.add_text("locked").unwrap();
        let locked_id = m.items[0].id;
        m.set_locked(locked_id, true).unwrap();
        m.add_text("keep").unwrap();
        let kept_id = m.items[0].id;

        assert_eq!(m.delete_many(&[image_id, locked_id]), Ok(1));
        assert!(!image_path.exists());
        assert_eq!(m.items().len(), 2);
        assert!(m.items().iter().any(|item| item.id == locked_id && item.locked));
        assert!(m.items().iter().any(|item| item.id == kept_id));
        let _ = fs::remove_dir_all(&dir);
    }

    fn red_pixel() -> ImageData<'static> {
        ImageData {
            width: 2,
            height: 1,
            bytes: std::borrow::Cow::Owned(vec![255, 0, 0, 255, 255, 0, 0, 255]),
        }
    }

    #[test]
    fn image_hash_distinguishes_pixels_and_dimensions() {
        let mut same = red_pixel();
        assert_eq!(image_hash(&same), image_hash(&same));

        same.width = 1;
        assert_ne!(image_hash(&same), image_hash(&red_pixel()));

        let mut other = red_pixel();
        other.bytes = std::borrow::Cow::Owned(vec![0, 0, 0, 255, 255, 0, 0, 255]);
        assert_ne!(image_hash(&other), image_hash(&red_pixel()));
    }

    #[test]
    fn encode_png_produces_a_valid_png() {
        let bytes = encode_png(&red_pixel()).unwrap();
        assert!(bytes.len() > 8);
        assert_eq!(&bytes[..8], &[137, 80, 78, 71, 13, 10, 26, 10]);
    }

    #[test]
    fn encode_png_rejects_invalid_dimensions() {
        let invalid = ImageData { width: 0, height: 0, bytes: std::borrow::Cow::Owned(vec![]) };
        assert!(encode_png(&invalid).is_err());

        let mismatched = ImageData { width: 2, height: 1, bytes: std::borrow::Cow::Owned(vec![0; 3]) };
        assert!(encode_png(&mismatched).is_err());
    }

    #[test]
    fn empty_and_whitespace_text_is_ignored() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_text("").unwrap();
        m.add_text("   ").unwrap();
        m.add_text("\n\t").unwrap();
        assert!(m.items().is_empty());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn update_text_validates_and_persists() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_text("original").unwrap();
        let id = m.items()[0].id;

        assert_eq!(m.update_text(999, "nope"), Err("item not found".into()));
        assert_eq!(m.update_text(id, "  "), Err("clipboard text cannot be empty".into()));

        m.update_text(id, "edited").unwrap();
        assert_eq!(m.items()[0].text.as_deref(), Some("edited"));

        m.add_image(b"img").unwrap();
        let image_id = m.items()[0].id;
        assert_eq!(m.update_text(image_id, "not allowed"), Err("clipboard item is not text".into()));
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn update_text_truncates_long_input_and_touches_time() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_text("original").unwrap();
        let id = m.items()[0].id;
        m.update_text(id, &"y".repeat(MAX_TEXT_LENGTH + 50)).unwrap();
        assert_eq!(m.items()[0].text.as_deref().unwrap().len(), MAX_TEXT_LENGTH);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn set_locked_errors_on_missing_and_persists_toggle() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        assert_eq!(m.set_locked(123, true), Err("item not found".into()));

        m.add_text("item").unwrap();
        let id = m.items()[0].id;
        m.set_locked(id, true).unwrap();
        assert!(m.items()[0].locked);
        m.set_locked(id, false).unwrap();
        assert!(!m.items()[0].locked);
        m.delete(id).unwrap();
        assert!(m.items().is_empty());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn delete_missing_id_is_a_noop() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_text("only").unwrap();
        m.delete(404).unwrap();
        assert_eq!(m.items().len(), 1);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn delete_locked_item_is_rejected_and_file_survives() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_image(b"precious").unwrap();
        let id = m.items()[0].id;
        m.set_locked(id, true).unwrap();

        assert_eq!(m.delete(id), Err("clipboard item is locked".into()));
        assert_eq!(m.items().len(), 1);
        assert!(m.images_dir.join(format!("{id}.png")).exists());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn set_max_items_keeps_locked_items_and_deletes_lost_images() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_image(b"first").unwrap();
        let first_id = m.items()[0].id;
        m.add_text("locked").unwrap();
        let locked_id = m.items()[0].id;
        m.set_locked(locked_id, true).unwrap();
        m.add_text("newest").unwrap();

        m.set_max_items(2).unwrap();
        assert_eq!(m.items().len(), 2);
        assert!(m.items().iter().any(|item| item.id == locked_id && item.locked));
        assert!(m.items().iter().any(|item| item.id != first_id));
        assert!(!m.images_dir.join(format!("{first_id}.png")).exists());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn persistence_round_trip_reloads_items_and_image_files() {
        let dir = unique_dir();
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join("clipboard.json");
        {
            let mut m = manager(&path);
            m.add_text("kept text").unwrap();
            m.add_image(b"png-bytes").unwrap();
            let id = m.items()[0].id;
            m.set_locked(id, true).unwrap();
        }

        let reloaded = ClipboardManager::load_with(&path).unwrap();
        assert_eq!(reloaded.items().len(), 2);
        assert_eq!(reloaded.items()[0].content_type, "image");
        assert_eq!(reloaded.items()[0].image_path.as_deref(), Some(format!("{}.png", reloaded.items()[0].id).as_str()));
        assert_eq!(reloaded.get_image_bytes(reloaded.items()[0].id).unwrap(), b"png-bytes");
        assert!(reloaded.items().iter().any(|item| item.content_type == "image" && item.locked));

        let mut writable = reloaded;
        writable.add_text("third").unwrap();
        assert_eq!(writable.items()[0].id, 3);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn python_image_without_explicit_path_resolves_text_field() {
        let json = r#"[{"time":"2026-08-07 14:30:00","text":"7.png","locked":false,"kind":"image"}]"#;
        let items: Vec<ClipboardItem> = serde_json::from_str(json).unwrap();
        assert_eq!(items[0].content_type, "image");
        assert_eq!(items[0].image_path.as_deref(), Some("7.png"));
        assert_eq!(items[0].text, None);
    }

    #[test]
    fn explicit_content_type_wins_over_kind_and_empty_image_path_is_rejected() {
        let json = r#"[{"time":"1","kind":"image","content_type":"text","text":"real","image_path":""}]"#;
        let items: Vec<ClipboardItem> = serde_json::from_str(json).unwrap();
        assert_eq!(items[0].content_type, "text");
        assert_eq!(items[0].text.as_deref(), Some("real"));
        assert_eq!(items[0].image_path, None);

        let image = r#"[{"time":"2","kind":"image","content_type":"image","text":"a.png","image_path":""}]"#;
        let items: Vec<ClipboardItem> = serde_json::from_str(image).unwrap();
        assert_eq!(items[0].content_type, "image");
        assert_eq!(items[0].image_path.as_deref(), Some("a.png"));
    }

    #[test]
    fn python_time_normalization_rejects_invalid_calendar_values() {
        assert_eq!(python_time_to_unix("2026-13-01 00:00:00"), None);
        assert_eq!(python_time_to_unix("2026-00-10 00:00:00"), None);
        assert_eq!(python_time_to_unix("2026-08-32 00:00:00"), None);
        assert_eq!(python_time_to_unix("2026-08-07 24:00:00"), None);
        assert_eq!(python_time_to_unix("2026-08-07 14:30:60"), Some(1786113060));
        assert_eq!(python_time_to_unix("1969-12-31 23:59:59"), None);
        assert_eq!(python_time_to_unix("1970-01-01 00:00:00"), Some(0));
    }

    #[test]
    fn delete_many_handles_duplicate_and_missing_ids() {
        let dir = unique_dir();
        let mut m = manager(&dir.join("clipboard.json"));
        m.add_text("one").unwrap();
        let first = m.items()[0].id;
        m.add_text("two").unwrap();
        let second = m.items()[0].id;

        assert_eq!(m.delete_many(&[first, first, 999]), Ok(1));
        assert_eq!(m.items().len(), 1);
        assert_eq!(m.items()[0].id, second);
        assert_eq!(m.delete_many(&[]), Ok(0));
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn is_supported_image_extension_accepts_png_jpg_jpeg_bmp_webp_gif() {
        assert!(super::is_supported_image_extension("png"));
        assert!(super::is_supported_image_extension("jpg"));
        assert!(super::is_supported_image_extension("jpeg"));
        assert!(super::is_supported_image_extension("bmp"));
        assert!(super::is_supported_image_extension("webp"));
        assert!(super::is_supported_image_extension("gif"));
    }

    #[test]
    fn is_supported_image_extension_rejects_txt_and_unknown() {
        assert!(!super::is_supported_image_extension("txt"));
        assert!(!super::is_supported_image_extension("pdf"));
        assert!(!super::is_supported_image_extension("svg"));
        assert!(!super::is_supported_image_extension(""));
    }

    #[test]
    fn is_supported_image_extension_is_case_insensitive() {
        assert!(super::is_supported_image_extension("PNG"));
        assert!(super::is_supported_image_extension("JPG"));
        assert!(super::is_supported_image_extension("Gif"));
    }

    #[test]
    fn is_supported_image_path_rejects_empty_path() {
        assert!(!super::is_supported_image_path(""));
    }

    #[test]
    fn is_supported_image_path_accepts_image_files() {
        assert!(super::is_supported_image_path("photo.png"));
        assert!(super::is_supported_image_path("C:\\Users\\test\\image.jpg"));
        assert!(super::is_supported_image_path("/home/user/snap.bmp"));
    }

    #[test]
    fn is_supported_image_path_rejects_non_image_files() {
        assert!(!super::is_supported_image_path("notes.txt"));
        assert!(!super::is_supported_image_path("doc.pdf"));
    }
}
