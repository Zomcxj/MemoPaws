use std::path::{Path, PathBuf};

use image::{GenericImageView, ImageEncoder};
#[cfg(test)]
use memopaws_clipboard::ClipboardManager;
use memopaws_ocr::image_util::decode_limited_with_rgba_limit;

use super::ClipboardState;

const THUMBNAIL_MAX_EDGE: u32 = 512;
const THUMBNAIL_MAX_DECODE_RGBA: u64 = 128 * 1024 * 1024;
const SOURCE_MAX_BYTES: usize = 25 * 1024 * 1024;

pub struct ThumbnailImage {
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}

// Never enlarges; caps the longest edge at THUMBNAIL_MAX_EDGE.
pub(crate) fn thumbnail_dimensions(width: u32, height: u32) -> (u32, u32) {
    if width == 0 || height == 0 {
        return (1, 1);
    }
    let ratio = (THUMBNAIL_MAX_EDGE as f64 / width as f64)
        .min(THUMBNAIL_MAX_EDGE as f64 / height as f64)
        .min(1.0);
    (
        ((width as f64 * ratio).round().max(1.0)) as u32,
        ((height as f64 * ratio).round().max(1.0)) as u32,
    )
}

pub(crate) fn make_thumbnail(bytes: &[u8]) -> Result<ThumbnailImage, String> {
    let source = decode_limited_with_rgba_limit(bytes, THUMBNAIL_MAX_DECODE_RGBA)
        .map_err(|error| format!("thumbnail decode failed: {error}"))?;
    let (width, height) = source.dimensions();
    let (target_w, target_h) = thumbnail_dimensions(width, height);
    let scaled = source
        .resize_exact(target_w, target_h, image::imageops::FilterType::Lanczos3)
        .to_rgba8();
    Ok(ThumbnailImage { width: target_w, height: target_h, rgba: scaled.into_raw() })
}

pub(crate) fn encode_thumbnail_png(thumbnail: &ThumbnailImage) -> Result<Vec<u8>, String> {
    let buffer = image::RgbaImage::from_raw(thumbnail.width, thumbnail.height, thumbnail.rgba.clone())
        .ok_or_else(|| "thumbnail pixel buffer mismatch".to_string())?;
    let mut output = std::io::Cursor::new(Vec::new());
    image::codecs::png::PngEncoder::new(&mut output)
        .write_image(
            buffer.as_raw(),
            thumbnail.width,
            thumbnail.height,
            image::ExtendedColorType::Rgba8,
        )
        .map_err(|error| format!("thumbnail encode failed: {error}"))?;
    Ok(output.into_inner())
}

fn read_source_capped(path: &Path) -> Result<Vec<u8>, String> {
    let metadata = std::fs::metadata(path).map_err(|error| format!("thumbnail source read failed: {error}"))?;
    if !metadata.is_file() {
        return Err("thumbnail source is not a file".to_string());
    }
    if metadata.len() > SOURCE_MAX_BYTES as u64 {
        return Err("thumbnail source exceeds the 25MiB input limit".to_string());
    }
    std::fs::read(path).map_err(|error| format!("thumbnail source read failed: {error}"))
}

pub(crate) fn thumbnail_from_path(path: &Path) -> Result<Vec<u8>, String> {
    let image = make_thumbnail(&read_source_capped(path)?)?;
    encode_thumbnail_png(&image)
}

// Test-only glue: production resolves the path first so decode can run off-thread.
#[cfg(test)]
pub(crate) fn thumbnail_for_record(manager: &ClipboardManager, id: u64) -> Result<Vec<u8>, String> {
    thumbnail_from_path(&manager.image_path_for(id)?)
}

#[tauri::command]
pub async fn clipboard_get_thumbnail(
    id: u64,
    state: tauri::State<'_, ClipboardState>,
) -> Result<tauri::ipc::Response, String> {
    // Resolve the path under the lock; IO, decode and encode run off-thread.
    let path: PathBuf = lock_recover!(state).image_path_for(id)?;
    tauri::async_runtime::spawn_blocking(move || thumbnail_from_path(&path))
        .await
        .map_err(|error| format!("thumbnail task failed: {error}"))?
        .map(tauri::ipc::Response::new)
}

#[cfg(test)]
mod tests {
    use super::*;
    use image::{ExtendedColorType, ImageEncoder, Rgba, RgbaImage};

    fn encode_rgba(buffer: RgbaImage, width: u32, height: u32) -> Vec<u8> {
        let mut output = std::io::Cursor::new(Vec::new());
        image::codecs::png::PngEncoder::new(&mut output)
            .write_image(buffer.as_raw(), width, height, ExtendedColorType::Rgba8)
            .expect("sample encodes");
        output.into_inner()
    }

    fn sample_png(width: u32, height: u32) -> Vec<u8> {
        let mut buffer = RgbaImage::new(width, height);
        for (x, y, pixel) in buffer.enumerate_pixels_mut() {
            *pixel = Rgba([(x * 7) as u8, (y * 11) as u8, 0, 255]);
        }
        encode_rgba(buffer, width, height)
    }

    fn manager_with_image(dir: &tempfile::TempDir, width: u32, height: u32) -> (ClipboardManager, u64) {
        let mut manager = ClipboardManager::open_at(
            dir.path().join("clipboard.json"),
            dir.path().join("images"),
        )
        .expect("manager loads");
        manager.add_image(&sample_png(width, height)).expect("image added");
        let id = manager.items()[0].id;
        (manager, id)
    }

    #[test]
    fn thumbnail_scales_down_preserving_ratio_and_caps_edge() {
        let dir = tempfile::tempdir().expect("tempdir");
        let (manager, id) = manager_with_image(&dir, 2000, 1000);
        let png = thumbnail_for_record(&manager, id).expect("thumbnail succeeds");
        let decoded = memopaws_ocr::image_util::decode_limited(&png).expect("png decodes");
        assert_eq!(decoded.dimensions(), (512, 256));
    }

    #[test]
    fn thumbnail_never_enlarges_small_images() {
        let dir = tempfile::tempdir().expect("tempdir");
        let (manager, id) = manager_with_image(&dir, 120, 60);
        let png = thumbnail_for_record(&manager, id).expect("thumbnail succeeds");
        let decoded = memopaws_ocr::image_util::decode_limited(&png).expect("png decodes");
        assert_eq!(decoded.dimensions(), (120, 60));
    }

    #[test]
    fn thumbnail_preserves_transparency() {
        let dir = tempfile::tempdir().expect("tempdir");
        let mut manager = ClipboardManager::open_at(
            dir.path().join("clipboard.json"),
            dir.path().join("images"),
        )
        .expect("manager loads");
        let mut buffer = RgbaImage::new(4, 4);
        for (x, _, pixel) in buffer.enumerate_pixels_mut() {
            *pixel = Rgba([255, 0, 0, if x < 2 { 0 } else { 255 }]);
        }
        manager.add_image(&encode_rgba(buffer, 4, 4)).expect("image added");
        let id = manager.items()[0].id;
        let png = thumbnail_for_record(&manager, id).expect("thumbnail succeeds");
        let decoded = memopaws_ocr::image_util::decode_limited(&png).expect("png decodes").to_rgba8();
        assert_eq!(*decoded.get_pixel(0, 0), Rgba([255, 0, 0, 0]));
        assert_eq!(*decoded.get_pixel(3, 0), Rgba([255, 0, 0, 255]));
    }

    #[test]
    fn thumbnail_rejects_unknown_id_non_image_and_missing_file() {
        let dir = tempfile::tempdir().expect("tempdir");
        let mut manager = ClipboardManager::open_at(
            dir.path().join("clipboard.json"),
            dir.path().join("images"),
        )
        .expect("manager loads");
        manager.add_text("text-only").expect("text added");
        let text_id = manager.items()[0].id;
        assert!(thumbnail_for_record(&manager, 9999).is_err(), "unknown id errors");
        assert!(thumbnail_for_record(&manager, text_id).is_err(), "text item errors");
        manager.add_image(&sample_png(4, 4)).expect("image added");
        let image_id = manager
            .items()
            .iter()
            .find(|item| item.content_type == "image")
            .expect("image item present")
            .id;
        std::fs::remove_file(manager.image_path_for(image_id).expect("path")).expect("source removed");
        assert!(thumbnail_for_record(&manager, image_id).is_err(), "missing file errors");
    }

    #[test]
    fn thumbnail_rejects_oversized_source_without_unbounded_read() {
        let dir = tempfile::tempdir().expect("tempdir");
        let (manager, id) = manager_with_image(&dir, 4, 4);
        let path = manager.image_path_for(id).expect("path");
        std::fs::write(&path, vec![0_u8; SOURCE_MAX_BYTES + 1]).expect("oversized written");
        assert!(thumbnail_for_record(&manager, id).is_err(), "oversized source errors");
    }
}
