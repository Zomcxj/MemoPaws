pub mod image_util;

use std::{fmt, time::Duration};

use reqwest::StatusCode;
use serde::{Deserialize, Serialize};
use serde_json::json;
use zeroize::Zeroizing;

const DEFAULT_ENDPOINT: &str = "https://open.bigmodel.cn/api/paas/v4/chat/completions";
const DEFAULT_TIMEOUT: Duration = Duration::from_secs(15);
const OCR_PROMPT: &str = "请识别这张图片中的所有文字内容，直接输出识别结果，不要添加任何解释或额外内容。保持原文的格式和换行。";

#[derive(Clone)]
pub struct ApiConfig {
    api_url: String,
    model: String,
    api_key: Zeroizing<String>,
}

impl ApiConfig {
    pub fn new(api_url: impl Into<String>, model: impl Into<String>, api_key: impl Into<String>) -> Self {
        Self { api_url: api_url.into(), model: model.into(), api_key: Zeroizing::new(api_key.into()) }
    }

    pub fn endpoint(&self) -> String {
        let url = self.api_url.trim().trim_end_matches('/');
        if url.is_empty() { DEFAULT_ENDPOINT.into() }
        else if url.ends_with("/chat/completions") { url.into() }
        else { format!("{url}/chat/completions") }
    }

    pub fn model(&self) -> &str { &self.model }
}

impl fmt::Debug for ApiConfig {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.debug_struct("ApiConfig").field("api_url", &self.api_url).field("model", &self.model).field("api_key", &"[REDACTED]").finish()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
pub enum Language {
    #[serde(rename = "zh")] Chinese,
    #[serde(rename = "en")] English,
    #[serde(rename = "ja")] Japanese,
    #[serde(rename = "ko")] Korean,
    #[serde(rename = "fr")] French,
    #[serde(rename = "de")] German,
    #[serde(rename = "es")] Spanish,
    #[serde(rename = "ru")] Russian,
}

impl Language {
    pub const fn code(self) -> &'static str { match self { Self::Chinese => "zh", Self::English => "en", Self::Japanese => "ja", Self::Korean => "ko", Self::French => "fr", Self::German => "de", Self::Spanish => "es", Self::Russian => "ru" } }
    const fn name(self) -> &'static str { match self { Self::Chinese => "Chinese", Self::English => "English", Self::Japanese => "Japanese", Self::Korean => "Korean", Self::French => "French", Self::German => "German", Self::Spanish => "Spanish", Self::Russian => "Russian" } }
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct OcrResult { pub text: String }

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct TranslateResult { pub text: String, pub requested: bool }

#[derive(Debug, thiserror::Error)]
pub enum OcrError {
    #[error("image input exceeds {max_bytes} bytes")]
    InputTooLarge { max_bytes: usize },
    #[error("unsupported or invalid image")]
    UnsupportedImage,
    #[error("image exceeds pixel limit of {max_pixels}")]
    PixelLimit { max_pixels: u64 },
    #[error("failed to encode image")]
    ImageEncoding,
    #[error("API request timed out")]
    Timeout,
    #[error("API request failed")]
    Request,
    #[error("API returned HTTP {status}: {message}")]
    HttpStatus { status: u16, message: String },
    #[error("API returned a malformed response")]
    MalformedResponse,
    #[error("translation input exceeds {max_bytes} bytes")]
    TranslationInputTooLarge { max_bytes: usize },
    #[error("{0}")]
    Custom(String),
}

#[derive(Debug)]
pub struct Client { config: ApiConfig, http: reqwest::Client }

impl Client {
    pub fn new(config: ApiConfig) -> Self { Self::with_timeout(config, DEFAULT_TIMEOUT).expect("static timeout is valid") }

    pub fn endpoint(&self) -> String { self.config.endpoint() }

    pub fn model(&self) -> &str { &self.config.model }

    pub fn with_timeout(config: ApiConfig, timeout: Duration) -> Result<Self, OcrError> {
        let http = reqwest::Client::builder().no_proxy().timeout(timeout).build().map_err(|_| OcrError::Request)?;
        Ok(Self { config, http })
    }

    pub async fn ocr(&self, image_bytes: &[u8]) -> Result<OcrResult, OcrError> {
        let image = image_util::prepare_image(image_bytes)?;
        let payload = json!({
            "model": self.config.model,
            "messages": [{"role":"user","content":[
                {"type":"image_url","image_url":{"url":image.data_uri}},
                {"type":"text","text":OCR_PROMPT}
            ]}],
            "temperature": 0.1
        });
        self.request(payload).await.map(|text| OcrResult { text })
    }

    pub async fn translate(&self, text: &str, target: Language, source: Option<Language>) -> Result<TranslateResult, OcrError> {
        if text.len() > 100_000 {
            return Err(OcrError::TranslationInputTooLarge { max_bytes: 100_000 });
        }
        if source == Some(target) || text.trim().is_empty() { return Ok(TranslateResult { text: text.into(), requested: false }); }
        let direction = source.map(|language| format!("from {} ", language.name())).unwrap_or_default();
        let payload = json!({
            "model": self.config.model,
            "messages": [
                {"role":"system","content":"You are a professional translator. Preserve meaning, formatting, and line breaks. Output only the translation."},
                {"role":"user","content":format!("Translate {direction}to {}.\n\n{text}", target.name())}
            ],
            "temperature":0.3
        });
        self.request(payload).await.map(|text| TranslateResult { text, requested: true })
    }

    async fn request(&self, payload: serde_json::Value) -> Result<String, OcrError> {
        let response = self.http.post(self.config.endpoint()).bearer_auth(self.config.api_key.as_str()).json(&payload).send().await.map_err(map_reqwest)?;
        let status = response.status();
        if !status.is_success() {
            let body = response.text().await.unwrap_or_default();
            return Err(OcrError::HttpStatus { status: status.as_u16(), message: safe_message(status, &body) });
        }
        let response: ChatResponse = response.json().await.map_err(|_| OcrError::MalformedResponse)?;
        response.choices.into_iter().next().map(|choice| choice.message.content.trim().to_owned()).filter(|text| !text.is_empty()).ok_or(OcrError::MalformedResponse)
    }
}

fn map_reqwest(error: reqwest::Error) -> OcrError { if error.is_timeout() { OcrError::Timeout } else { OcrError::Request } }

fn safe_message(status: StatusCode, _body: &str) -> String {
    status.canonical_reason().unwrap_or("request rejected").into()
}

#[derive(Deserialize)]
struct ChatResponse { choices: Vec<Choice> }
#[derive(Deserialize)]
struct Choice { message: Message }
#[derive(Deserialize)]
struct Message { content: String }
