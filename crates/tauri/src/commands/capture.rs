
use image::{codecs::png::{CompressionType, FilterType, PngEncoder}, DynamicImage};
use memopaws_canvas::{CaptureManager, CaptureRecord};



use super::CaptureState;

#[derive(Debug, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CaptureRegion {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

#[tauri::command]
pub async fn capture_screen(
    region: Option<CaptureRegion>,
    display_index: Option<usize>,
) -> Result<tauri::ipc::Response, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let monitors =
            xcap::Monitor::all().map_err(|error| format!("screen capture failed: {error}"))?;
        // An explicit index selects that display; omitting it falls back to the primary display.
        let monitor = match display_index {
            Some(index) => monitors
                .get(index)
                .ok_or_else(|| format!("display index {index} is out of range"))?,
            None => monitors
                .iter()
                .find(|monitor| monitor.is_primary().unwrap_or(false))
                .or_else(|| monitors.first())
                .ok_or_else(|| "no display available for capture".to_string())?,
        };
        let image = match region {
            Some(region) => {
                if region.width == 0 || region.height == 0 {
                    return Err("capture region width and height must be positive".to_string());
                }
                monitor
                    .capture_region(region.x, region.y, region.width, region.height)
                    .map_err(|error| format!("screen capture failed: {error}"))?
            }
            None => monitor
                .capture_image()
                .map_err(|error| format!("screen capture failed: {error}"))?,
        };
        let mut png = Vec::new();
        DynamicImage::ImageRgba8(image)
            // Lossless fixed filtering avoids scoring five filters per screenshot row.
            .write_with_encoder(PngEncoder::new_with_quality(
                &mut png,
                CompressionType::Fast,
                FilterType::Sub,
            ))
            .map_err(|error| format!("screen capture failed: {error}"))?;
        // Binary IPC avoids serializing the full PNG as both numbers and base64.
        Ok(tauri::ipc::Response::new(png))
    })
    .await
    .map_err(|error| format!("screen capture task failed: {error}"))?
}

#[derive(Debug, serde::Serialize)]
pub struct ImageResult {
    pub image: Vec<u8>,
}

const DEFAULT_MOSAIC_BLOCK: u32 = 12;

// The frontend reads `result.image`, so this must stay an object, not a bare array.
#[tauri::command]
pub fn image_preprocess(image: Vec<u8>, mode: String) -> Result<ImageResult, String> {
    let processed =
        match mode.as_str() {
            "gray" => memopaws_ocr::image_util::grayscale_png(&image)
                .map_err(|error| error.to_string())?,
            "binary" => memopaws_ocr::image_util::otsu_binary_png(&image)
                .map_err(|error| error.to_string())?,
            "mosaic" => memopaws_ocr::image_util::mosaic_png(&image, DEFAULT_MOSAIC_BLOCK)
                .map_err(|error| error.to_string())?,
            _ => return Err(format!("unsupported preprocess mode: {mode}")),
        };
    Ok(ImageResult { image: processed })
}

#[tauri::command]
pub fn image_crop(
    image: Vec<u8>,
    x: u32,
    y: u32,
    width: u32,
    height: u32,
) -> Result<ImageResult, String> {
    memopaws_ocr::image_util::crop_png(&image, x, y, width, height)
        .map(|image| ImageResult { image })
        .map_err(|error| error.to_string())
}

#[derive(Debug, serde::Serialize)]
pub struct DisplayInfo {
    pub index: usize,
    pub name: String,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    pub is_primary: bool,
}

#[tauri::command]
pub fn list_displays() -> Result<Vec<DisplayInfo>, String> {
    let monitors =
        xcap::Monitor::all().map_err(|error| format!("failed to enumerate displays: {error}"))?;
    Ok(monitors
        .iter()
        .enumerate()
        .map(|(index, monitor)| DisplayInfo {
            index,
            name: monitor
                .name()
                .unwrap_or_else(|_| format!("Display {}", index + 1)),
            x: monitor.x().unwrap_or(0),
            y: monitor.y().unwrap_or(0),
            width: monitor.width().unwrap_or(0),
            height: monitor.height().unwrap_or(0),
            is_primary: monitor.is_primary().unwrap_or(false),
        })
        .collect())
}
fn capture_mut<T>(
    state: tauri::State<'_, CaptureState>,
    operation: impl FnOnce(&mut CaptureManager) -> Result<T, String>,
) -> Result<T, String> {
    let mut capture = lock_recover!(state);
    operation(&mut capture)
}

#[tauri::command]
pub fn capture_list(state: tauri::State<'_, CaptureState>) -> Result<Vec<CaptureRecord>, String> {
    capture_mut(state, |capture| Ok(capture.records().to_vec()))
}

#[tauri::command]
pub fn capture_get_image(
    id: u64,
    state: tauri::State<'_, CaptureState>,
) -> Result<Vec<u8>, String> {
    capture_mut(state, |capture| capture.get_capture_bytes(id))
}

#[tauri::command]
pub fn capture_delete(id: u64, state: tauri::State<'_, CaptureState>) -> Result<(), String> {
    capture_mut(state, |capture| capture.delete(id))
}
