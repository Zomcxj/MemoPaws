use std::io::Cursor;

use base64::{engine::general_purpose::STANDARD, Engine};
use image::{DynamicImage, GenericImageView, ImageFormat, ImageReader};

use crate::OcrError;

pub const MAX_INPUT_BYTES: usize = 25 * 1024 * 1024;
pub const MAX_PIXELS: u64 = 40_000_000;
const MAX_EDGE: u32 = 1024;

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
