use memopaws_ocr::{image_util::{grayscale_png, otsu_binary_png, prepare_image, MAX_INPUT_BYTES}, OcrError};

#[test]
fn image_is_detected_resized_and_encoded_as_png_data_uri() {
    let source = image::RgbImage::from_pixel(2048, 512, image::Rgb([10, 20, 30]));
    let bytes = encode(source);
    let prepared = prepare_image(&bytes).unwrap();
    assert_eq!((prepared.width, prepared.height), (1024, 256));
    assert!(prepared.data_uri.starts_with("data:image/png;base64,"));
}

#[test]
fn image_limits_and_invalid_formats_are_rejected() {
    assert!(matches!(prepare_image(&vec![0; MAX_INPUT_BYTES + 1]), Err(OcrError::InputTooLarge { .. })));
    assert!(matches!(prepare_image(b"not an image"), Err(OcrError::UnsupportedImage)));
    let header_only = make_png_header(50_000, 50_000);
    let result = prepare_image(&header_only);
    assert!(matches!(&result, Err(OcrError::PixelLimit { .. }) | Err(OcrError::UnsupportedImage)),
        "expected PixelLimit or UnsupportedImage, got {result:?}");
}

#[test]
fn grayscale_and_otsu_are_canvas_preprocessors() {
    let source = image::RgbImage::from_fn(4, 1, |x, _| image::Rgb([(x * 70) as u8, 30, 200]));
    let bytes = encode(source);
    let gray = image::load_from_memory(&grayscale_png(&bytes).unwrap()).unwrap().to_luma8();
    assert_eq!(gray.dimensions(), (4, 1));
    let binary = image::load_from_memory(&otsu_binary_png(&bytes).unwrap()).unwrap().to_luma8();
    assert!(binary.pixels().all(|pixel| matches!(pixel.0[0], 0 | 255)));
}

fn encode(image: image::RgbImage) -> Vec<u8> {
    let mut bytes = std::io::Cursor::new(Vec::new());
    image::DynamicImage::ImageRgb8(image).write_to(&mut bytes, image::ImageFormat::Png).unwrap();
    bytes.into_inner()
}

fn make_png_header(width: u32, height: u32) -> Vec<u8> {
    let mut bytes = vec![137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, b'I', b'H', b'D', b'R'];
    bytes.extend(width.to_be_bytes());
    bytes.extend(height.to_be_bytes());
    bytes.extend([8, 2, 0, 0, 0]);
    bytes
}
