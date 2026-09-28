use std::time::Duration;

use memopaws_keys::{KeyEntry, KeyVault};
use memopaws_ocr::{ApiConfig, Client, Language, OcrResult, TranslateResult};
use zeroize::Zeroizing;



use super::{HistoryState, KeyVaultState};
use super::history::history_mut;
use super::keys::{is_settings_key, settings_note, upsert_settings_key, SETTINGS_KEY_NAME};

fn ai_client(
    state: tauri::State<'_, KeyVaultState>,
    key_entry_id: Option<u64>,
    model: Option<String>,
) -> Result<Client, String> {
    let picked = {
        let vault = lock_recover!(state);
        let entries = vault.list();
        let entry = match key_entry_id.filter(|id| *id != 0) {
            Some(id) => Some(
                entries
                    .into_iter()
                    .find(|entry| entry.id == id)
                    .ok_or_else(|| "key entry not found".to_string())?,
            ),
            None => entries.into_iter().find(is_settings_key),
        };
        match entry {
            Some(entry) => {
                if entry.entry_type != "llm" {
                    return Err("selected key entry is not an LLM key".into());
                }
                let key = Zeroizing::new(
                    vault
                        .get_value(entry.id)
                        .map_err(|error| error.to_string())?,
                );
                Some((entry, key))
            }
            None => None,
        }
    };
    match picked {
        Some((entry, key)) => resolve_ai_config(entry, key, model).map(Client::new),
        // Settings mode without a vault entry: fall back to the live settings
        // config so saved API settings are used immediately.
        None => {
            let config =
                memopaws_config::config::AppConfig::load().map_err(|error| error.to_string())?;
            settings_client_from(&config, model)
        }
    }
}

fn settings_client_from(
    config: &memopaws_config::config::AppConfig,
    model: Option<String>,
) -> Result<Client, String> {
    let key = config.api_key.clone().unwrap_or_default();
    if key.trim().is_empty() {
        return Err("API key is required".into());
    }
    let model = model
        .filter(|model| !model.trim().is_empty())
        .or_else(|| config.api_model.clone())
        .unwrap_or_else(|| memopaws_config::config::DEFAULT_MODEL.to_string());
    Ok(Client::new(ApiConfig::new(
        config.api_url.clone().unwrap_or_default(),
        model,
        key,
    )))
}

fn promote_key_to_settings(vault: &mut KeyVault, entry_id: u64) -> Result<(), String> {
    let entry = vault
        .list()
        .into_iter()
        .find(|entry| entry.id == entry_id)
        .ok_or_else(|| "key entry not found".to_string())?;
    if entry.entry_type != "llm" {
        return Err("selected key entry is not an LLM key".to_string());
    }
    let value = vault
        .get_value(entry.id)
        .map_err(|error| error.to_string())?;
    upsert_settings_key(vault, &value, &entry.url, &settings_note(&entry.note))
}

#[tauri::command]
pub fn set_settings_key(
    entry_id: u64,
    state: tauri::State<'_, KeyVaultState>,
) -> Result<(), String> {
    let (url, note) = {
        let vault = lock_recover!(state);
        let entry = vault
            .list()
            .into_iter()
            .find(|entry| entry.id == entry_id)
            .ok_or_else(|| "key entry not found".to_string())?;
        (entry.url.clone(), entry.note.clone())
    };
    // Keep the settings page in sync so its API URL and model reflect the promoted key.
    let mut config =
        memopaws_config::config::AppConfig::load().map_err(|error| error.to_string())?;
    if !url.trim().is_empty() {
        config.api_url = Some(url);
    }
    if !note.trim().is_empty() {
        config.api_model = Some(note);
    }
    config.save().map_err(|error| error.to_string())?;
    let mut vault = lock_recover!(state);
    promote_key_to_settings(&mut vault, entry_id)
}

fn resolve_ai_config(
    entry: KeyEntry,
    key: Zeroizing<String>,
    requested_model: Option<String>,
) -> Result<ApiConfig, String> {
    let model = if entry.name == SETTINGS_KEY_NAME {
        (!entry.note.trim().is_empty() && entry.note != "Settings API key")
            .then_some(entry.note)
            .or(requested_model
                .filter(|model| !model.trim().is_empty() && model != "Settings API key"))
            .or_else(|| {
                memopaws_config::config::AppConfig::load()
                    .ok()
                    .and_then(|config| config.api_model)
            })
            .unwrap_or_else(|| memopaws_config::config::DEFAULT_MODEL.to_string())
    } else {
        entry.note
    };
    let model = model.trim();
    if model.is_empty() || model.len() > 200 {
        return Err("model is required".into());
    }
    Ok(ApiConfig::new(entry.url, model, key.to_string()))
}

fn safe_ai_command_error(error: &str) -> String {
    if classify_api_error(error) == "unauthorized" {
        "API authorization failed. Check the selected key and endpoint, then try again.".into()
    } else {
        error.into()
    }
}

fn classify_api_error(error: &str) -> &'static str {
    let lower = error.to_ascii_lowercase();
    if lower.contains("timeout") || lower.contains("timed out") {
        "timeout"
    } else if lower.contains("401") || lower.contains("unauthorized") {
        "unauthorized"
    } else if lower.contains("403") || lower.contains("forbidden") {
        "forbidden"
    } else if lower.contains("429") || lower.contains("too many requests") {
        "rate_limit"
    } else if lower.contains("404") || lower.contains("not found") {
        "not_found"
    } else if lower.contains("408") || lower.contains("request timeout") {
        "request_timeout"
    } else if lower.contains("500") || lower.contains("internal server error") {
        "server_error"
    } else if lower.contains("502") || lower.contains("bad gateway") {
        "bad_gateway"
    } else if lower.contains("503") || lower.contains("service unavailable") {
        "service_unavailable"
    } else if lower.contains("400") || lower.contains("bad request") {
        "bad_request"
    } else if lower.contains("http ") {
        "http_error"
    } else if lower.contains("connect")
        || lower.contains("connection")
        || lower.contains("request failed")
    {
        "connect"
    } else if lower.contains("multimodal") || lower.contains("vision") || lower.contains("image") {
        "multimodal"
    } else {
        "generic"
    }
}

fn api_error_result(error: &str, elapsed_ms: u128) -> serde_json::Value {
    let kind = classify_api_error(error);
    let mut result = serde_json::json!({"error": kind, "elapsed_ms": elapsed_ms});
    if let Some(code) = error.split_whitespace().find_map(|part| {
        part.parse::<u16>()
            .ok()
            .filter(|code| (100..=599).contains(code))
    }) {
        result["status_code"] = serde_json::json!(code);
    }
    result
}

fn multimodal_probe_image() -> &'static [u8] {
    // Minimal 1x1 PNG used only to test the provider's image capability.
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
}

// Bounded so the UI never appears frozen: reachability probe plus a shorter vision probe.
const API_PROBE_TIMEOUT: Duration = Duration::from_secs(20);
const KEY_PROBE_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Clone, Copy)]
enum KeyProbeFamily {
    Claude,
    Grok,
    Compatible,
}

struct KeyProbeRequest {
    family: KeyProbeFamily,
    endpoint: String,
    payload: serde_json::Value,
}

fn key_probe_request(api_url: &str, model: &str) -> KeyProbeRequest {
    let family = if model.trim().to_ascii_lowercase().starts_with("claude") {
        KeyProbeFamily::Claude
    } else if model.trim().to_ascii_lowercase().starts_with("grok") {
        KeyProbeFamily::Grok
    } else {
        KeyProbeFamily::Compatible
    };
    let compatible_endpoint = ApiConfig::new(api_url, model, "").endpoint();
    let base = compatible_endpoint
        .trim_end_matches("/chat/completions")
        .trim_end_matches("/messages")
        .trim_end_matches("/responses");
    match family {
        KeyProbeFamily::Claude => KeyProbeRequest {
            family,
            endpoint: format!("{base}/messages"),
            payload: serde_json::json!({"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}),
        },
        KeyProbeFamily::Grok => KeyProbeRequest {
            family,
            endpoint: format!("{base}/responses"),
            payload: serde_json::json!({"model": model, "input": "hi", "max_output_tokens": 1}),
        },
        KeyProbeFamily::Compatible => KeyProbeRequest {
            family,
            endpoint: compatible_endpoint,
            payload: serde_json::json!({"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}),
        },
    }
}

async fn run_key_probe(
    api_url: &str,
    model: &str,
    api_key: &str,
) -> Result<serde_json::Value, String> {
    let request = key_probe_request(api_url, model);
    let client = reqwest::Client::builder()
        .no_proxy()
        .timeout(KEY_PROBE_TIMEOUT)
        .build()
        .map_err(|_| "API connection failed".to_string())?;
    let started = std::time::Instant::now();
    let response = match request.family {
        KeyProbeFamily::Claude => {
            client
                .post(&request.endpoint)
                .header("x-api-key", api_key)
                .header("anthropic-version", "2023-06-01")
                .json(&request.payload)
                .send()
                .await
        }
        KeyProbeFamily::Grok | KeyProbeFamily::Compatible => {
            client
                .post(&request.endpoint)
                .bearer_auth(api_key)
                .json(&request.payload)
                .send()
                .await
        }
    };
    let elapsed = started.elapsed().as_millis();
    match response {
        Ok(response) => Ok(key_probe_status_result(response.status().as_u16(), elapsed)),
        Err(error) => Ok(api_error_result(&error.to_string(), elapsed)),
    }
}

fn key_probe_status_result(status_code: u16, elapsed_ms: u128) -> serde_json::Value {
    if status_code == 200 {
        serde_json::json!({"status_code": 200, "elapsed_ms": elapsed_ms})
    } else {
        api_error_result(&format!("HTTP {status_code}"), elapsed_ms)
    }
}

// The probe reuses the same OCR path as real image recognition, so a working
// AI key/vision model is verified through the exact endpoint the app uses.
// A text-only probe runs first to validate the key/model, then a vision probe
// decides whether the model is multimodal.
async fn run_api_probe(config: ApiConfig) -> Result<serde_json::Value, String> {
    let client = Client::with_timeout(config, API_PROBE_TIMEOUT)
        .map_err(|_| "API connection failed".to_string())?;
    let started = std::time::Instant::now();
    let text_result = client
        .translate("ping", Language::English, Some(Language::Chinese))
        .await;
    let elapsed = started.elapsed().as_millis();
    match text_result {
        Ok(_) => {
            let vision_ok = client.ocr(multimodal_probe_image()).await.is_ok();
            Ok(
                serde_json::json!({"status_code": 200, "elapsed_ms": elapsed, "vision_result": {"success": vision_ok}}),
            )
        }
        Err(error) => Ok(api_error_result(&error.to_string(), elapsed)),
    }
}

#[tauri::command]
pub async fn test_api_connection(
    key_entry_id: Option<u64>,
    model: Option<String>,
    api_key: Option<String>,
    api_url: Option<String>,
    api_model: Option<String>,
    vault: tauri::State<'_, KeyVaultState>,
) -> Result<serde_json::Value, String> {
    let model = api_model.or(model).unwrap_or_default();
    if let Some(key) = api_key.filter(|key| !key.trim().is_empty()) {
        let model = model.trim();
        if model.is_empty() || model.len() > 200 {
            return Err("model is required".to_string());
        }
        let key = Zeroizing::new(key);
        return run_api_probe(ApiConfig::new(
            api_url.unwrap_or_default(),
            model,
            key.to_string(),
        ))
        .await;
    }
    // No inline key: fall back to the saved settings entry so a stored key still tests.
    let (api_url, anthropic_url, model, key) = {
        let vault = lock_recover!(vault);
        if !vault.status().unlocked {
            return Err("key vault is locked, unlock it first".to_string());
        }
        let entries = vault.list();
        let entry = match key_entry_id {
            Some(id) => entries
                .into_iter()
                .find(|entry| entry.id == id)
                .ok_or_else(|| "key entry not found".to_string())?,
            None => entries
                .into_iter()
                .find(is_settings_key)
                .ok_or_else(|| "API key is required".to_string())?,
        };
        if entry.entry_type != "llm" {
            return Err("selected key entry is not an LLM key".to_string());
        }
        let key = Zeroizing::new(
            vault
                .get_value(entry.id)
                .map_err(|_| "API connection failed".to_string())?,
        );
        let anthropic_url = entry.url_anthropic.clone();
        let config = resolve_ai_config(entry, key.clone(), Some(model.clone()))?;
        (
            config
                .endpoint()
                .trim_end_matches("/chat/completions")
                .to_string(),
            anthropic_url,
            config.model().to_string(),
            key,
        )
    };
    let probe_url = if model.trim().to_ascii_lowercase().starts_with("claude")
        && !anthropic_url.trim().is_empty()
    {
        anthropic_url.as_str()
    } else {
        api_url.as_str()
    };
    run_key_probe(probe_url, &model, key.as_str()).await
}

#[tauri::command]
pub async fn ai_ocr(
    image: Vec<u8>,
    key_entry_id: Option<u64>,
    model: Option<String>,
    vault: tauri::State<'_, KeyVaultState>,
    history: tauri::State<'_, HistoryState>,
) -> Result<OcrResult, String> {
    let result = ai_client(vault, key_entry_id, model)?
        .ocr(&image)
        .await
        .map_err(|error| safe_ai_command_error(&error.to_string()))?;
    // 历史是次要记录：写入失败不应把已成功的识别结果误报为失败
    let _ = history_mut(history, |manager| {
        manager.add_success("ocr", &result.text, Some(&result.text), None)
    });
    Ok(result)
}

#[tauri::command]
pub async fn ai_translate(
    text: String,
    target: Language,
    source: Option<Language>,
    key_entry_id: Option<u64>,
    model: Option<String>,
    vault: tauri::State<'_, KeyVaultState>,
    history: tauri::State<'_, HistoryState>,
) -> Result<TranslateResult, String> {
    if text.len() > 100_000 {
        return Err("translation input is too large".into());
    }
    let result = ai_client(vault, key_entry_id, model)?
        .translate(&text, target, source)
        .await
        .map_err(|error| safe_ai_command_error(&error.to_string()))?;
    // 历史是次要记录：写入失败不应把已成功的翻译结果误报为失败
    let _ = history_mut(history, |manager| {
        manager.add_success("translate", &result.text, Some(&text), Some(&result.text))
    });
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use memopaws_keys::KeyEntryInput;
    use std::{
        time::{Duration, SystemTime, UNIX_EPOCH},
    };

    #[test]
    fn api_errors_are_replaced_with_a_safe_connection_message() {
        let error = super::classify_api_error("API returned HTTP 401: secret response");
        assert_eq!(error, "unauthorized");
        assert!(!error.contains("secret"));
    }

    #[test]
    fn ai_config_uses_a_normal_llm_entrys_stored_endpoint_and_model() {
        let entry = memopaws_keys::KeyEntry {
            id: 7,
            name: "Vision provider".into(),
            entry_type: "llm".into(),
            url: "https://vision.example.test/v1".into(),
            url_anthropic: String::new(),
            note: "vision-model".into(),
            order: 0,
            created: String::new(),
        };

        let config =
            super::resolve_ai_config(entry, Zeroizing::new("test-secret".into()), None).unwrap();

        assert_eq!(
            config.endpoint(),
            "https://vision.example.test/v1/chat/completions"
        );
        assert_eq!(config.model(), "vision-model");
        assert!(!format!("{config:?}").contains("test-secret"));
    }

    #[test]
    fn test_connection_rejects_a_normal_llm_entry_without_a_persisted_model() {
        let entry = memopaws_keys::KeyEntry {
            id: 9,
            name: "Vision provider".into(),
            entry_type: "llm".into(),
            url: "https://vision.example.test/v1".into(),
            url_anthropic: String::new(),
            note: "   ".into(),
            order: 0,
            created: String::new(),
        };

        let error = super::resolve_ai_config(
            entry,
            Zeroizing::new("test-secret".into()),
            Some("frontend-model".into()),
        )
        .unwrap_err();

        assert_eq!(error, "model is required");
    }

    #[test]
    fn ai_config_keeps_a_settings_entrys_persisted_model() {
        let entry = memopaws_keys::KeyEntry {
            id: 8,
            name: "settings_api_key".into(),
            entry_type: "llm".into(),
            url: "https://settings.example.test/v1".into(),
            url_anthropic: String::new(),
            note: "settings-vision-model".into(),
            order: 0,
            created: String::new(),
        };

        let config = super::resolve_ai_config(
            entry,
            Zeroizing::new("test-secret".into()),
            Some("frontend-fixed-model".into()),
        )
        .unwrap();

        assert_eq!(
            config.endpoint(),
            "https://settings.example.test/v1/chat/completions"
        );
        assert_eq!(config.model(), "settings-vision-model");
    }

    #[test]
    fn unauthorized_ai_errors_are_generic_and_actionable() {
        let message = super::safe_ai_command_error(
            "API returned HTTP 401: provider response containing a secret",
        );

        assert_eq!(
            message,
            "API authorization failed. Check the selected key and endpoint, then try again."
        );
        assert!(!message.contains("secret"));
    }

    #[test]
    fn api_error_classification_covers_all_categories() {
        assert_eq!(super::classify_api_error("request timed out"), "timeout");
        assert_eq!(
            super::classify_api_error("API returned HTTP 401"),
            "unauthorized"
        );
        assert_eq!(
            super::classify_api_error("API returned HTTP 403"),
            "forbidden"
        );
        assert_eq!(
            super::classify_api_error("API returned HTTP 429"),
            "rate_limit"
        );
        assert_eq!(
            super::classify_api_error("API returned HTTP 503"),
            "service_unavailable"
        );
        assert_eq!(super::classify_api_error("404 not found"), "not_found");
        assert_eq!(super::classify_api_error("connection refused"), "connect");
        assert_eq!(
            super::classify_api_error("request failed: hyper error"),
            "connect"
        );
        assert_eq!(
            super::classify_api_error("model does not support vision"),
            "multimodal"
        );
        assert_eq!(
            super::classify_api_error("image decode error"),
            "multimodal"
        );
        assert_eq!(super::classify_api_error("something else"), "generic");
    }

    #[test]
    fn api_error_result_attaches_status_codes_only_when_meaningful() {
        let unauthorized = super::api_error_result("HTTP 401 unauthorized", 12);
        assert_eq!(unauthorized["error"], "unauthorized");
        assert_eq!(unauthorized["status_code"], 401);
        assert_eq!(unauthorized["elapsed_ms"], 12);

        let missing = super::api_error_result("404 not found", 3);
        assert_eq!(missing["status_code"], 404);

        for (message, kind, status) in [
            ("HTTP 403 forbidden", "forbidden", 403),
            ("HTTP 429 too many requests", "rate_limit", 429),
            ("HTTP 503 service unavailable", "service_unavailable", 503),
        ] {
            let result = super::api_error_result(message, 5);
            assert_eq!(result["error"], kind);
            assert_eq!(result["status_code"], status);
        }

        let timeout = super::api_error_result("timed out", 8000);
        assert!(timeout.get("status_code").is_none());
    }

    #[test]
    fn key_probe_accepts_only_http_200_and_preserves_other_statuses() {
        for status in [201, 204, 400, 408, 500, 502] {
            let result = super::key_probe_status_result(status, 7);
            assert_eq!(result["status_code"], status);
            assert!(result.get("error").is_some());
        }
        assert_eq!(super::key_probe_status_result(200, 7)["status_code"], 200);
        assert!(super::key_probe_status_result(200, 7)
            .get("error")
            .is_none());
        assert_eq!(
            super::key_probe_status_result(201, 7)["error"],
            "http_error"
        );
        assert_eq!(
            super::key_probe_status_result(408, 7)["error"],
            "request_timeout"
        );
        assert_eq!(
            super::key_probe_status_result(500, 7)["error"],
            "server_error"
        );
    }

    #[test]
    fn key_probe_selects_model_family_endpoint_and_payload() {
        let claude = super::key_probe_request("https://api.anthropic.com/v1/", "claude-3-5-haiku");
        assert_eq!(claude.endpoint, "https://api.anthropic.com/v1/messages");
        assert_eq!(
            claude.payload,
            serde_json::json!({
                "model": "claude-3-5-haiku",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}]
            })
        );

        let grok = super::key_probe_request("https://api.x.ai/v1/chat/completions", "grok-3");
        assert_eq!(grok.endpoint, "https://api.x.ai/v1/responses");
        assert_eq!(
            grok.payload,
            serde_json::json!({
                "model": "grok-3",
                "input": "hi",
                "max_output_tokens": 1
            })
        );

        for model in [
            "gpt-4o-mini",
            "glm-4v-flash",
            "deepseek-chat",
            "custom-model",
        ] {
            let request = super::key_probe_request("https://provider.example/v1/", model);
            assert_eq!(
                request.endpoint,
                "https://provider.example/v1/chat/completions"
            );
            assert_eq!(
                request.payload,
                serde_json::json!({
                    "model": model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1
                })
            );
        }
    }

    #[test]
    fn key_probe_timeout_is_ten_seconds() {
        assert_eq!(super::KEY_PROBE_TIMEOUT, Duration::from_secs(10));
    }

    #[test]
    fn settings_client_uses_the_saved_config_and_redacts_the_secret() {
        let mut config = memopaws_config::config::AppConfig::default();
        config.api_key = Some("super-secret-key".into());
        config.api_url = Some("https://settings.example.test/v1".into());
        config.api_model = Some("vision-model".into());

        let client = super::settings_client_from(&config, None).unwrap();

        assert_eq!(
            client.endpoint(),
            "https://settings.example.test/v1/chat/completions"
        );
        assert_eq!(client.model(), "vision-model");
        assert!(!format!("{client:?}").contains("super-secret-key"));
    }

    #[test]
    fn settings_client_requires_a_key() {
        let config = memopaws_config::config::AppConfig::default();
        let error = super::settings_client_from(&config, None).unwrap_err();
        assert_eq!(error, "API key is required");
    }

    #[test]
    fn promoting_a_key_to_settings_replaces_the_vault_entry() {
        let path = std::env::temp_dir().join(format!(
            "memopaws-promote-{}.json",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
        ));
        let mut vault = KeyVault::load(&path).unwrap();
        let added = vault
            .add(KeyEntryInput {
                name: "zai".into(),
                entry_type: "llm".into(),
                value: "zai-secret".into(),
                url: "https://open.bigmodel.cn/api/paas/v4/chat/completions".into(),
                url_anthropic: String::new(),
                note: "glm-4v-flash".into(),
            })
            .unwrap();

        super::promote_key_to_settings(&mut vault, added.id).unwrap();

        let entries = vault.list();
        assert_eq!(entries.len(), 2);
        let settings = entries
            .iter()
            .find(|entry| entry.name == "settings_api_key" && entry.entry_type == "llm")
            .unwrap();
        assert_eq!(vault.get_value(settings.id).unwrap(), "zai-secret");
        assert_eq!(
            settings.url,
            "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        );
        assert_eq!(settings.note, "glm-4v-flash");

        super::promote_key_to_settings(&mut vault, added.id).unwrap();
        assert_eq!(vault.list().len(), 2);
        let _ = std::fs::remove_file(path);
    }

}
