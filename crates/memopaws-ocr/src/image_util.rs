use std::io::Cursor;

use base64::{engine::general_purpose::STANDARD, Engine};
use image::{DynamicImage, GenericImageView, ImageFormat, ImageReader, Rgba, RgbaImage};

use crate::OcrError;

pub const MAX_INPUT_BYTES: usize = 25 * 1024 * 1024;
pub const MAX_PIXELS: u64 = 40_000_000;
const MAX_EDGE: u32 = 1024;
const MIN_BLOCK: u32 = 2;
const MAX_BLOCK: u32 = 128;

#[derive(Debug)]
pub struct PreparedImage { pub data_uri: String, pub width: u32, pub height: u32 }

pub fn prepare_image(bytes: &[u8]) -> Result<PreparedImage, OcrError> {
    let image = decode_limited(bytes)?;
    let resized = resize(image);
    let (width, height) = resized.dimensions();
    let png = encode_png(&resized)?;
    Ok(PreparedImage { data_uri: format!("data:image/png;base64,{}", STANDARD.encode(png)), width, height })
}

pub fn grayscale_png(bytes: &[u8]) -> Result<Vec<u8>, OcrError> { encode_png(&DynamicImage::ImageLuma8(decode_limited(bytes)?.to_luma8())) }

pub fn otsu_binary_png(bytes: &[u8]) -> Result<Vec<u8>, OcrError> {
    let mut gray = decode_limited(bytes)?.to_luma8();
    let threshold = otsu_threshold(&gray);
    for pixel in gray.pixels_mut() { pixel.0[0] = if pixel.0[0] > threshold { 255 } else { 0 }; }
    encode_png(&DynamicImage::ImageLuma8(gray))
}

pub fn mosaic_png(bytes: &[u8], block: u32) -> Result<Vec<u8>, OcrError> {
    let mut image = decode_limited(bytes)?.to_rgba8();
    let (width, height) = image.dimensions();
    mosaic_area(&mut image, clamp_block(block), 0, 0, width, height);
    encode_png(&DynamicImage::ImageRgba8(image))
}

pub fn crop_png(bytes: &[u8], x: u32, y: u32, width: u32, height: u32) -> Result<Vec<u8>, OcrError> {
    if width == 0 || height == 0 { return Err(OcrError::Custom("crop width and height must be positive".into())); }
    let image = decode_limited(bytes)?;
    let (image_width, image_height) = image.dimensions();
    let right = x.saturating_add(width).min(image_width);
    let bottom = y.saturating_add(height).min(image_height);
    if right <= x || bottom <= y { return Err(OcrError::Custom("crop region is outside the image".into())); }
    let cropped = image.crop_imm(x, y, right - x, bottom - y);
    encode_png(&cropped)
}

fn clamp_block(block: u32) -> u32 { block.clamp(MIN_BLOCK, MAX_BLOCK) }

fn mosaic_area(image: &mut RgbaImage, block: u32, origin_x: u32, origin_y: u32, width: u32, height: u32) {
    let step = block as usize;
    for block_y in (0..height).step_by(step) {
        for block_x in (0..width).step_by(step) {
            let (end_x, end_y) = ((block_x + block).min(width), (block_y + block).min(height));
            let mut sums = [0_u64; 4];
            for y in block_y..end_y { for x in block_x..end_x {
                let pixel = image.get_pixel(origin_x + x, origin_y + y).0;
                for (sum, channel) in sums.iter_mut().zip(pixel) { *sum += u64::from(channel); }
            } }
            let count = u64::from(end_x - block_x) * u64::from(end_y - block_y);
            let average = Rgba([(sums[0] / count) as u8, (sums[1] / count) as u8, (sums[2] / count) as u8, (sums[3] / count) as u8]);
            for y in block_y..end_y { for x in block_x..end_x { image.put_pixel(origin_x + x, origin_y + y, average); } }
        }
    }
}

fn decode_limited(bytes: &[u8]) -> Result<DynamicImage, OcrError> {
    if bytes.len() > MAX_INPUT_BYTES { return Err(OcrError::InputTooLarge { max_bytes: MAX_INPUT_BYTES }); }
    let reader = ImageReader::new(Cursor::new(bytes)).with_guessed_format().map_err(|_| OcrError::UnsupportedImage)?;
    let format = reader.format().filter(|format| matches!(format, ImageFormat::Png | ImageFormat::Jpeg | ImageFormat::Gif | ImageFormat::WebP | ImageFormat::Bmp)).ok_or(OcrError::UnsupportedImage)?;
    let (width, height) = ImageReader::with_format(Cursor::new(bytes), format).into_dimensions().map_err(|_| OcrError::UnsupportedImage)?;
    if u64::from(width) * u64::from(height) > MAX_PIXELS { return Err(OcrError::PixelLimit { max_pixels: MAX_PIXELS }); }
    ImageReader::with_format(Cursor::new(bytes), format).decode().map_err(|_| OcrError::UnsupportedImage)
}

fn resize(image: DynamicImage) -> DynamicImage {
    let (width, height) = image.dimensions();
    if width <= MAX_EDGE && height <= MAX_EDGE { image } else { image.resize(MAX_EDGE, MAX_EDGE, image::imageops::FilterType::Lanczos3) }
}

fn encode_png(image: &DynamicImage) -> Result<Vec<u8>, OcrError> {
    let mut output = Cursor::new(Vec::new());
    image.write_to(&mut output, ImageFormat::Png).map_err(|_| OcrError::ImageEncoding)?;
    Ok(output.into_inner())
}

#[cfg(test)]
mod tests {
    use super::*;
    use image::RgbaImage;

    fn sample_png(width: u32, height: u32) -> Vec<u8> {
        let mut buffer = RgbaImage::new(width, height);
        for (x, y, pixel) in buffer.enumerate_pixels_mut() { *pixel = image::Rgba([(x * 10) as u8, (y * 10) as u8, 0, (x * 8) as u8]); }
        encode_png(&DynamicImage::ImageRgba8(buffer)).expect("sample encodes")
    }

    fn decode_rgba(bytes: &[u8]) -> RgbaImage { decode_limited(bytes).expect("decodes").to_rgba8() }

    #[test]
    fn mosaic_png_makes_each_block_uniform() {
        let original = sample_png(8, 8);
        let output = decode_rgba(&mosaic_png(&original, 4).expect("mosaic succeeds"));
        assert_eq!(output.dimensions(), (8, 8));
        for (block_x, block_y) in [(0, 0), (4, 0), (0, 4), (4, 4)] {
            let expected = *output.get_pixel(block_x, block_y);
            for y in block_y..block_y + 4 { for x in block_x..block_x + 4 { assert_eq!(*output.get_pixel(x, y), expected, "block ({block_x},{block_y}) pixel ({x},{y})"); } }
        }
        assert_eq!(output.get_pixel(0, 0).0, [15, 15, 0, 12]);
    }

    #[test]
    fn mosaic_png_clamps_block_size() {
        let original = sample_png(8, 8);
        for block in [0, 1, 999] {
            let output = decode_rgba(&mosaic_png(&original, block).expect("mosaic succeeds"));
            assert_eq!(output.dimensions(), (8, 8), "block {block}");
        }
        let coarse = decode_rgba(&mosaic_png(&original, 999).expect("mosaic succeeds"));
        let first = *coarse.get_pixel(0, 0);
        assert!(coarse.pixels().all(|pixel| *pixel == first), "clamped block covers whole image");
    }
}

fn otsu_threshold(image: &image::GrayImage) -> u8 {
    let mut histogram = [0_u64; 256];
    for pixel in image.pixels() { histogram[pixel.0[0] as usize] += 1; }
    let total = u64::from(image.width()) * u64::from(image.height());
    let sum: u64 = histogram.iter().enumerate().map(|(value, count)| value as u64 * count).sum();
    let (mut background_count, mut background_sum, mut best_variance, mut threshold) = (0_u64, 0_u64, 0_f64, 0_u8);
    for (value, count) in histogram.iter().enumerate() {
        background_count += count; if background_count == 0 { continue; }
        let foreground_count = total - background_count; if foreground_count == 0 { break; }
        background_sum += value as u64 * count;
        let background_mean = background_sum as f64 / background_count as f64;
        let foreground_mean = (sum - background_sum) as f64 / foreground_count as f64;
        let variance = background_count as f64 * foreground_count as f64 * (background_mean - foreground_mean).powi(2);
        if variance > best_variance { best_variance = variance; threshold = value as u8; }
    }
    threshold
}
