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
            result.push(LocalLanguage { tag: lang.LanguageTag()?.to_string(), name: lang.DisplayName()?.to_string() });
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
        let mut pixels = prepare(bytes, max)?;
        white_bgra(&mut pixels);
        let writer = DataWriter::new().map_err(|e| e.to_string())?;
        writer.WriteBytes(pixels.as_raw()).map_err(|e| e.to_string())?;
        let buffer = writer.DetachBuffer().map_err(|e| e.to_string())?;
        let bitmap = SoftwareBitmap::CreateCopyFromBuffer(&buffer, BitmapPixelFormat::Bgra8, pixels.width() as i32, pixels.height() as i32)
            .map_err(|e| e.to_string())?;
        let language = Language::CreateLanguage(&HSTRING::from(tag)).map_err(|e| e.to_string())?;
        let engine = OcrEngine::TryCreateFromLanguage(&language).map_err(|e| format!("Cannot create installed Windows OCR engine: {e}"))?;
        let result = engine.RecognizeAsync(&bitmap).map_err(|e| e.to_string())?.join().map_err(|e| format!("Windows OCR failed: {e}"))?;
        let lines = result.Lines().map_err(|e| e.to_string())?;
        let mut text = Vec::new();
        for i in 0..lines.Size().map_err(|e| e.to_string())? {
            text.push(lines.GetAt(i).map_err(|e| e.to_string())?.Text().map_err(|e| e.to_string())?.to_string());
        }
        Ok(text.join("\n").trim().to_string())
    }
}

#[cfg(windows)]
pub use win::{languages, recognize};

#[cfg(test)]
mod tests {
    use super::*;

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
