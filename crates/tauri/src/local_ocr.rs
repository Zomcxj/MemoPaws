// Windows offline OCR: language enumeration, bounded image preparation and WinRT recognition.
// This module never touches the network, never downloads language packs and never writes image
// files; recognized text goes through the existing history. Pure functions (size scaling, resource
// limit checks, transparent-pixel whitening) live outside the Windows module for unit testing.
use memopaws_ocr::image_util::decode_limited_with_rgba_limit;

/// Local OCR decode memory budget: width × height × 4 bytes.
const MAX_RGBA: u64 = 128 * 1024 * 1024;

fn check_rgba_size(w: u32, h: u32) -> Result<(), String> {
    let n = u64::from(w)
        .checked_mul(u64::from(h))
        .and_then(|n| n.checked_mul(4))
        .ok_or("image dimensions overflow")?;
    if w == 0 || h == 0 || n > MAX_RGBA {
        Err("image exceeds local OCR resource limit".into())
    } else {
        Ok(())
    }
}

fn scaled_size(w: u32, h: u32, max: u32) -> Result<(u32, u32), String> {
    if w == 0 || h == 0 || max == 0 {
        return Err("invalid OCR image dimensions".into());
    }
    let f = (max as f64 / w as f64).min(max as f64 / h as f64).min(1.0);
    Ok(((w as f64 * f).round().max(1.0) as u32, (h as f64 * f).round().max(1.0) as u32))
}

// Bounded decode → resource-limit recheck → engine-max proportional downscale (shrink only) → RGBA.
fn prepare(bytes: &[u8], max: u32) -> Result<image::RgbaImage, String> {
    let decoded = decode_limited_with_rgba_limit(bytes, MAX_RGBA).map_err(|e| e.to_string())?;
    check_rgba_size(decoded.width(), decoded.height())?;
    let (w, h) = scaled_size(decoded.width(), decoded.height(), max)?;
    if w > i32::MAX as u32 || h > i32::MAX as u32 {
        return Err("OCR bitmap dimensions overflow".into());
    }
    let resized = if (w, h) == (decoded.width(), decoded.height()) {
        decoded
    } else {
        decoded.resize_exact(w, h, image::imageops::FilterType::Lanczos3)
    };
    Ok(resized.into_rgba8())
}

// WinRT SoftwareBitmap(Bgra8) requires: transparent pixels blended onto white (OCR hallucinates on
// transparency), RGBA→BGRA channel swap, alpha forced to 255.
fn white_bgra(pixels: &mut image::RgbaImage) {
    for pixel in pixels.pixels_mut() {
        let alpha = u16::from(pixel[3]);
        for c in 0..3 {
            pixel[c] = ((u16::from(pixel[c]) * alpha + 255 * (255 - alpha)) / 255) as u8;
        }
        pixel.0.swap(0, 2);
        pixel[3] = 255;
    }
}

// Narrow-image recovery: an empty result on a narrow crop gets one bounded
// enlargement retry (integer scale 2-3, 16px white border) before giving up.
const SMALL_EDGE: u32 = 128;
const RECOVERY_PADDING: u32 = 16;
const MAX_RECOVERY_SCALE: u32 = 3;

// Padded total size for the retry, or None when the image is not narrow, the
// integer scale is below 2, the padded size busts the engine max, or the RGBA
// budget would be exceeded.
fn recovery_size(w: u32, h: u32, max: u32) -> Option<(u32, u32)> {
    if w == 0 || h == 0 || max == 0 || w.min(h) > SMALL_EDGE {
        return None;
    }
    let available = max.checked_sub(2 * RECOVERY_PADDING)?;
    let scale = (available / w.max(h)).min(MAX_RECOVERY_SCALE);
    if scale < 2 {
        return None;
    }
    let total_w = w.checked_mul(scale)?.checked_add(2 * RECOVERY_PADDING)?;
    let total_h = h.checked_mul(scale)?.checked_add(2 * RECOVERY_PADDING)?;
    if total_w > max || total_h > max {
        return None;
    }
    check_rgba_size(total_w, total_h).ok()?;
    Some((total_w, total_h))
}

// Enlarges the content to fit inside a white-padded canvas of the given total
// size; pixels are copied raw so white_bgra can run exactly once afterwards.
fn padded_enlarged(image: &image::RgbaImage, total_w: u32, total_h: u32) -> Result<image::RgbaImage, String> {
    let content_w = total_w.checked_sub(2 * RECOVERY_PADDING).ok_or("invalid recovery size")?;
    let content_h = total_h.checked_sub(2 * RECOVERY_PADDING).ok_or("invalid recovery size")?;
    if content_w == 0 || content_h == 0 {
        return Err("invalid recovery size".into());
    }
        let scaled = if (content_w, content_h) == (image.width(), image.height()) {
            image.clone()
        } else {
            image::imageops::resize(image, content_w, content_h, image::imageops::FilterType::Lanczos3)
        };
    let mut padded = image::RgbaImage::from_pixel(total_w, total_h, image::Rgba([255, 255, 255, 255]));
    for (x, y, pixel) in scaled.enumerate_pixels() {
        padded.put_pixel(x + RECOVERY_PADDING, y + RECOVERY_PADDING, *pixel);
    }
    Ok(padded)
}

// First pass, then one bounded enlargement retry when the result is empty on a
// narrow crop. Errors from the retry propagate unchanged.
fn recognize_with_recovery(
    image: &image::RgbaImage,
    max: u32,
    mut recognize_image: impl FnMut(&image::RgbaImage) -> Result<String, String>,
) -> Result<String, String> {
    let text = recognize_image(image)?;
    if !text.trim().is_empty() {
        return Ok(text);
    }
    let Some((total_w, total_h)) = recovery_size(image.width(), image.height(), max) else {
        return Ok(text);
    };
    let recovery = padded_enlarged(image, total_w, total_h)?;
    recognize_image(&recovery)
}

/// Region words Windows puts into OCR language display names. The mention is noise in a language
/// picker ("中文（简体，中国大陆）" / "中文(中华人民共和国)" / "Chinese (Simplified, Mainland
/// China)"), so segments containing them are dropped and the leftover punctuation repaired.
const REGION_MARKERS: [&str; 4] = ["中国大陆", "中华人民共和国", "Mainland China", "People's Republic of China"];

fn display_name(raw: &str) -> String {
    let mut cleaned = raw.to_string();
    for marker in REGION_MARKERS {
        // Expand each marker to its enclosing segment: from the nearest opener/separator before it to
        // the nearest closer/separator after it ("简体，中国大陆）" → drop "，中国大陆"). Include the
        // leading separator so "简体，中国大陆）" does not become "简体，）".
        while let Some(start) = cleaned.find(marker) {
            // rfind returns the byte offset of the opener/separator itself; step over its full UTF-8
            // length (，is three bytes) so seg_start stays on a char boundary.
            let seg_start = cleaned[..start]
                .rfind(|c| c == '（' || c == '(' || c == '，' || c == ',')
                .map(|index| index + cleaned[index..].chars().next().unwrap().len_utf8())
                .unwrap_or(0);
            let seg_end = cleaned[start..]
                .find(|c| c == '）' || c == ')' || c == '，' || c == ',')
                .map(|index| start + index)
                .unwrap_or(cleaned.len());
            let mut drop_start = seg_start;
            if seg_start > 0 {
                // The separator may be multi-byte (，): step back by its UTF-8 length, not one byte.
                let previous = cleaned[..seg_start].chars().next_back();
                if previous == Some('，') || previous == Some(',') {
                    drop_start = seg_start - previous.unwrap().len_utf8();
                }
            }
            cleaned.replace_range(drop_start..seg_end, "");
        }
    }
    // A removal can leave empty parentheses behind ("中文(中华人民共和国)" → "中文()").
    cleaned.replace("（）", "").replace("()", "").trim().to_string()
}

/// An OCR language capability installed on this machine.
#[derive(serde::Serialize)]
pub struct LocalLanguage { pub tag: String, pub name: String }

/// Installed language list plus the system-preferred one (preferred is empty when the list is empty).
#[derive(serde::Serialize)]
pub struct LocalLanguages { pub languages: Vec<LocalLanguage>, pub preferred: String }

#[cfg(not(windows))]
pub fn languages() -> Result<LocalLanguages, String> { Err("offline OCR is only available on Windows".into()) }

#[cfg(not(windows))]
pub fn recognize(_: &[u8], _: &str) -> Result<String, String> { Err("offline OCR is only available on Windows".into()) }

#[cfg(windows)]
mod win {
    use super::*;
    use windows::{
        core::HSTRING,
        Globalization::Language,
        Graphics::Imaging::{BitmapPixelFormat, SoftwareBitmap},
        Media::Ocr::OcrEngine,
        Storage::Streams::DataWriter,
        System::UserProfile::GlobalizationPreferences,
        Win32::System::WinRT::{RoInitialize, RoUninitialize, RO_INIT_MULTITHREADED},
    };

    // Every blocking worker initializes its own WinRT apartment and uninitializes it when the scope
    // ends: no leaked initialization, no raw buffer pointers, no network clients.
    struct Apartment;
    impl Apartment {
        fn new() -> Result<Self, String> {
            unsafe { RoInitialize(RO_INIT_MULTITHREADED) }.map_err(|e| format!("Windows OCR initialization failed: {e}"))?;
            Ok(Self)
        }
    }
    impl Drop for Apartment {
        fn drop(&mut self) { unsafe { RoUninitialize(); } }
    }

    fn available() -> windows::core::Result<Vec<LocalLanguage>> {
        let langs = OcrEngine::AvailableRecognizerLanguages()?;
        let mut result = Vec::new();
        for i in 0..langs.Size()? {
            let lang = langs.GetAt(i)?;
            result.push(LocalLanguage { tag: lang.LanguageTag()?.to_string(), name: display_name(&lang.DisplayName()?.to_string()) });
        }
        Ok(result)
    }

    pub fn languages() -> Result<LocalLanguages, String> {
        let _apartment = Apartment::new()?;
        let languages = available().map_err(|e| format!("Cannot list installed OCR languages: {e}"))?;
        let mut preferred = languages.first().map(|l| l.tag.clone()).unwrap_or_default();
        let profile = GlobalizationPreferences::Languages().map_err(|e| e.to_string())?;
        for i in 0..profile.Size().map_err(|e| e.to_string())? {
            let tag = profile.GetAt(i).map_err(|e| e.to_string())?.to_string();
            if let Some(found) = languages.iter().find(|l| l.tag.eq_ignore_ascii_case(&tag)) {
                preferred = found.tag.clone();
                break;
            }
        }
        Ok(LocalLanguages { languages, preferred })
    }

    pub fn recognize(bytes: &[u8], tag: &str) -> Result<String, String> {
        let _apartment = Apartment::new()?;
        let installed = available().map_err(|e| e.to_string())?;
        if !installed.iter().any(|l| l.tag == tag) {
            // Explicit error: never auto-install language packs, never silently fall back to cloud OCR.
            return Err("Selected Windows OCR language is not installed; install its OCR language capability first".into());
        }
    let max = OcrEngine::MaxImageDimension().map_err(|e| e.to_string())?;
    let pixels = prepare(bytes, max)?;
    let language = Language::CreateLanguage(&HSTRING::from(tag)).map_err(|e| e.to_string())?;
        let engine = OcrEngine::TryCreateFromLanguage(&language).map_err(|e| format!("Cannot create installed Windows OCR engine: {e}"))?;
        recognize_with_recovery(&pixels, max, |image| {
            let mut bgra = image.clone();
            white_bgra(&mut bgra);
            let writer = DataWriter::new().map_err(|e| e.to_string())?;
            writer.WriteBytes(bgra.as_raw()).map_err(|e| e.to_string())?;
            let buffer = writer.DetachBuffer().map_err(|e| e.to_string())?;
            let bitmap = SoftwareBitmap::CreateCopyFromBuffer(&buffer, BitmapPixelFormat::Bgra8, bgra.width() as i32, bgra.height() as i32)
                .map_err(|e| e.to_string())?;
            let result = engine.RecognizeAsync(&bitmap).map_err(|e| e.to_string())?.join().map_err(|e| format!("Windows OCR failed: {e}"))?;
            let lines = result.Lines().map_err(|e| e.to_string())?;
            let mut text = Vec::new();
            for i in 0..lines.Size().map_err(|e| e.to_string())? {
                text.push(lines.GetAt(i).map_err(|e| e.to_string())?.Text().map_err(|e| e.to_string())?.to_string());
            }
            Ok(text.join("\n").trim().to_string())
        })
    }
}

#[cfg(windows)]
pub use win::{languages, recognize};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn display_name_drops_region_segments_in_any_writing() {
        assert_eq!(display_name("中文（简体，中国大陆）"), "中文（简体）");
        assert_eq!(display_name("中文(中华人民共和国)"), "中文");
        assert_eq!(display_name("中文（中国大陆）"), "中文");
        assert_eq!(display_name("中文(简体,中国大陆)"), "中文(简体)");
        assert_eq!(display_name("Chinese (Simplified, Mainland China)"), "Chinese (Simplified)");
        // 无地区词的显示名原样保留。
        assert_eq!(display_name("中文（简体）"), "中文（简体）");
        assert_eq!(display_name("English (US)"), "English (US)");
    }

    #[test]
    fn ocr_size_preserves_ratio_without_enlarging() {
        assert_eq!(scaled_size(8000, 4000, 2000).unwrap(), (2000, 1000));
        assert_eq!(scaled_size(100, 50, 2000).unwrap(), (100, 50));
        assert!(scaled_size(0, 50, 2000).is_err());
        assert!(scaled_size(100, 50, 0).is_err());
    }

    #[test]
    fn rgba_limit_is_checked_before_allocation() {
        assert!(check_rgba_size(8192, 4096).is_ok());
        assert!(check_rgba_size(8192, 4097).is_err());
        assert!(check_rgba_size(u32::MAX, u32::MAX).is_err());
    }

    #[test]
    fn transparent_pixels_are_white_and_opaque_red_is_bgra() {
        let mut pixels = image::RgbaImage::from_raw(2, 1, vec![255, 0, 0, 0, 255, 0, 0, 255]).unwrap();
        white_bgra(&mut pixels);
        assert_eq!(pixels.as_raw(), &vec![255, 255, 255, 255, 0, 0, 255, 255]);
    }

    #[test]
    fn non_empty_first_result_skips_recovery() {
        let image = image::RgbaImage::new(64, 32);
        let mut calls = 0;
        let text = recognize_with_recovery(&image, 1024, |_| { calls += 1; Ok("hello".into()) }).unwrap();
        assert_eq!(text, "hello");
        assert_eq!(calls, 1);
    }

    #[test]
    fn narrow_empty_result_retries_enlarged_and_padded() {
        let image = image::RgbaImage::new(64, 32);
        let mut sizes = Vec::new();
        let text = recognize_with_recovery(&image, 1024, |img| {
            sizes.push((img.width(), img.height()));
            if sizes.len() == 1 { Ok("  ".into()) } else { Ok("recovered".into()) }
        }).unwrap();
        assert_eq!(text, "recovered");
        assert_eq!(sizes, vec![(64, 32), (64 * 3 + 32, 32 * 3 + 32)]);
    }

    #[test]
    fn wide_strip_without_headroom_stays_single_pass() {
        let image = image::RgbaImage::new(600, 20);
        let mut calls = 0;
        let text = recognize_with_recovery(&image, 1024, |_| { calls += 1; Ok("".into()) }).unwrap();
        assert_eq!(text, "");
        assert_eq!(calls, 1);
    }

    #[test]
    fn non_narrow_image_stays_single_pass() {
        let image = image::RgbaImage::new(200, 300);
        let mut calls = 0;
        let text = recognize_with_recovery(&image, 1024, |_| { calls += 1; Ok("".into()) }).unwrap();
        assert_eq!(text, "");
        assert_eq!(calls, 1);
    }

    #[test]
    fn recovery_over_rgba_budget_stays_single_pass() {
        // max=120000, 59984×128 → scale 2 → 120000×288 ≈ 138MB > 128MiB budget.
        let image = image::RgbaImage::new(59984, 128);
        let mut calls = 0;
        let text = recognize_with_recovery(&image, 120000, |_| { calls += 1; Ok("".into()) }).unwrap();
        assert_eq!(text, "");
        assert_eq!(calls, 1);
    }

    #[test]
    fn recovery_retry_error_propagates() {
        let image = image::RgbaImage::new(64, 32);
        let outcome = recognize_with_recovery(&image, 1024, |img| {
            if img.width() == 64 { Ok("".into()) } else { Err("engine boom".into()) }
        });
        assert_eq!(outcome.unwrap_err(), "engine boom");
    }

    #[test]
    fn padded_enlarged_scales_content_and_whites_border() {
        let mut image = image::RgbaImage::new(2, 1);
        image.put_pixel(0, 0, image::Rgba([10, 20, 30, 255]));
        image.put_pixel(1, 0, image::Rgba([40, 50, 60, 255]));
        // No-resize branch: content is copied raw inside a white border.
        let padded = padded_enlarged(&image, 2 + 2 * RECOVERY_PADDING, 1 + 2 * RECOVERY_PADDING).unwrap();
        assert_eq!(padded.dimensions(), (34, 33));
        assert_eq!(*padded.get_pixel(0, 0), image::Rgba([255, 255, 255, 255]));
        assert_eq!(*padded.get_pixel(33, 32), image::Rgba([255, 255, 255, 255]));
        assert_eq!(*padded.get_pixel(16, 16), image::Rgba([10, 20, 30, 255]));
        assert_eq!(*padded.get_pixel(17, 16), image::Rgba([40, 50, 60, 255]));
        // Resize branch: content lands inside the border; resampled values may blend.
        let scaled = padded_enlarged(&image, 2 * 3 + 2 * RECOVERY_PADDING, 1 * 3 + 2 * RECOVERY_PADDING).unwrap();
        assert_eq!(scaled.dimensions(), (38, 35));
        assert_eq!(*scaled.get_pixel(0, 0), image::Rgba([255, 255, 255, 255]));
        assert_ne!(*scaled.get_pixel(20, 16), image::Rgba([255, 255, 255, 255]));
    }

    #[test]
    fn prepare_rejects_oversized_input() {
        // 6000×6000×4 = 144MiB > 128MiB: the bounded decode must reject it.
        let oversized = sample_png_bytes(6000, 6000);
        assert!(prepare(&oversized, 2000).is_err());
    }

    #[test]
    fn prepare_downscales_only_beyond_engine_max() {
        // 2000×1000 stays at its size within max=2000; 4000×2000 shrinks to 2000×1000.
        let within = prepare(&sample_png_bytes(2000, 1000), 2000).expect("within limit prepares");
        assert_eq!(within.dimensions(), (2000, 1000));
        let downscaled = prepare(&sample_png_bytes(4000, 2000), 2000).expect("downscale prepares");
        assert_eq!(downscaled.dimensions(), (2000, 1000));
        let small = prepare(&sample_png_bytes(120, 60), 2000).expect("small image prepares");
        assert_eq!(small.dimensions(), (120, 60));
    }

    fn sample_png_bytes(width: u32, height: u32) -> Vec<u8> {
        use image::RgbaImage;
        let buffer = RgbaImage::new(width, height);
        let mut output = std::io::Cursor::new(Vec::new());
        image::DynamicImage::ImageRgba8(buffer)
            .write_to(&mut output, image::ImageFormat::Png)
            .expect("sample encodes");
        output.into_inner()
    }
}
