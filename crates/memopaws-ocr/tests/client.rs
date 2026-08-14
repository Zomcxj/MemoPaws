use std::time::Duration;

use memopaws_ocr::{ApiConfig, Client, Language, OcrError};
use serde_json::json;
use wiremock::{matchers::{body_json, header, method, path}, Mock, MockServer, ResponseTemplate};

fn config(server: &MockServer, key: &str) -> ApiConfig {
    ApiConfig::new(server.uri(), "vision-model", key)
}

#[test]
fn normalizes_openai_compatible_urls() {
    assert_eq!(ApiConfig::new("", "m", "k").endpoint(), "https://open.bigmodel.cn/api/paas/v4/chat/completions");
    assert_eq!(ApiConfig::new("https://example.test/v1/", "m", "k").endpoint(), "https://example.test/v1/chat/completions");
    assert_eq!(ApiConfig::new("https://example.test/v1/chat/completions", "m", "k").endpoint(), "https://example.test/v1/chat/completions");
}

#[test]
fn config_debug_never_contains_the_key() {
    let config = ApiConfig::new("https://example.test/v1", "m", "super-secret-key");
    let debug = format!("{config:?}");
    assert!(!debug.contains("super-secret-key"), "debug should not leak the api key: {debug}");
    assert!(debug.contains("example.test"), "debug should still show the URL");
}

#[tokio::test]
async fn ocr_sends_multimodal_openai_payload_and_bearer_header() {
    let server = MockServer::start().await;
    let png = tiny_png();
    Mock::given(method("POST"))
        .and(path("/chat/completions"))
        .and(header("authorization", "Bearer test-secret"))
        .and(body_json(json!({
            "model": "vision-model",
            "messages": [{"role":"user","content":[
                {"type":"image_url","image_url":{"url": format!("data:image/png;base64,{}", base64::Engine::encode(&base64::engine::general_purpose::STANDARD, &png))}},
                {"type":"text","text":"请识别这张图片中的所有文字内容，直接输出识别结果，不要添加任何解释或额外内容。保持原文的格式和换行。"}
            ]}],
            "temperature": 0.1
        })))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({"choices":[{"message":{"content":"  hello\nworld  "}}]})))
        .mount(&server).await;

    let result = Client::new(config(&server, "test-secret")).ocr(&png).await.unwrap();
    assert_eq!(result.text, "hello\nworld");
}

#[tokio::test]
async fn translation_supports_languages_and_skips_same_language() {
    let server = MockServer::start().await;
    let client = Client::new(config(&server, "test-secret"));
    let unchanged = client.translate("bonjour", Language::French, Some(Language::French)).await.unwrap();
    assert_eq!(unchanged.text, "bonjour");
    assert!(!unchanged.requested);

    Mock::given(method("POST"))
        .and(path("/chat/completions"))
        .and(body_json(json!({
            "model":"vision-model",
            "messages":[
                {"role":"system","content":"You are a professional translator. Preserve meaning, formatting, and line breaks. Output only the translation."},
                {"role":"user","content":"Translate from English to Japanese.\n\nhello"}
            ],
            "temperature":0.3
        })))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({"choices":[{"message":{"content":"こんにちは"}}]})))
        .mount(&server).await;
    let translated = client.translate("hello", Language::Japanese, Some(Language::English)).await.unwrap();
    assert_eq!(translated.text, "こんにちは");
    assert!(translated.requested);
}

#[tokio::test]
async fn errors_are_safe_for_http_malformed_and_timeout_responses() {
    let server = MockServer::start().await;
    Mock::given(method("POST")).respond_with(ResponseTemplate::new(401).set_body_string("token=server-secret details".repeat(100))).mount(&server).await;
    let error = Client::new(config(&server, "client-secret")).translate("a", Language::Chinese, None).await.unwrap_err();
    let message = error.to_string();
    assert!(matches!(error, OcrError::HttpStatus { status: 401, .. }));
    assert!(!message.contains("client-secret"));
    assert!(!message.contains("server-secret"));
    assert!(message.len() < 400);

    let malformed_server = MockServer::start().await;
    Mock::given(method("POST")).respond_with(ResponseTemplate::new(200).set_body_json(json!({"choices":[]}))).mount(&malformed_server).await;
    assert!(matches!(Client::new(config(&malformed_server, "secret")).translate("a", Language::Chinese, None).await, Err(OcrError::MalformedResponse)));

    let timeout_server = MockServer::start().await;
    Mock::given(method("POST")).respond_with(ResponseTemplate::new(200).set_delay(Duration::from_millis(100))).mount(&timeout_server).await;
    let client = Client::with_timeout(config(&timeout_server, "secret"), Duration::from_millis(10)).unwrap();
    assert!(matches!(client.translate("a", Language::Chinese, None).await, Err(OcrError::Timeout)));
}

#[tokio::test]
async fn rejects_invalid_image_bytes_before_network_access() {
    let client = Client::new(config(&MockServer::start().await, "test-secret"));
    assert!(matches!(client.ocr(b"not-an-image").await, Err(OcrError::UnsupportedImage)));
}

#[tokio::test]
async fn rejects_oversized_translation_input_before_network_access() {
    let client = Client::new(config(&MockServer::start().await, "test-secret"));
    let text = "x".repeat(100_001);
    assert!(matches!(
        client.translate(&text, Language::Chinese, Some(Language::English)).await,
        Err(OcrError::TranslationInputTooLarge { max_bytes: 100_000 })
    ));
}

fn tiny_png() -> Vec<u8> {
    let image = image::RgbImage::from_pixel(1, 1, image::Rgb([255, 255, 255]));
    let mut bytes = std::io::Cursor::new(Vec::new());
    image::DynamicImage::ImageRgb8(image).write_to(&mut bytes, image::ImageFormat::Png).unwrap();
    bytes.into_inner()
}
