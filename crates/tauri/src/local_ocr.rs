// Windows 离线 OCR：语言枚举、有界图片准备与 WinRT 识别。
// 本模块不访问网络、不下载语言包、不落任何图片文件；识别文本走既有历史。
// 纯函数（尺寸换算/资源上限检查/透明像素白底化）放在 Windows 模块外以便单测。
use memopaws_ocr::image_util::decode_limited_with_rgba_limit;

/// 本地 OCR 的解码内存上限：宽×高×4 字节。
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

// 有界解码 → 资源上限复核 → 按引擎上限等比缩小（只缩不放）→ RGBA。
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

// WinRT SoftwareBitmap(Bgra8) 需要：透明像素混到白底（OCR 对透明处吐垃圾），
// RGBA→BGRA 通道互换，alpha 强制 255。
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
        // 6000×6000×4 = 144MiB > 128MiB：有界解码必须拒绝。
        let oversized = sample_png_bytes(6000, 6000);
        assert!(prepare(&oversized, 2000).is_err());
    }

    #[test]
    fn prepare_downscales_only_beyond_engine_max() {
        // 2000×1000 在 max=2000 内保持原尺寸；4000×2000 缩到 2000×1000。
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
