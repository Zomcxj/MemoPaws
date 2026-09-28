
use memopaws_keys::{KeyEntry, KeyEntryInput, KeyVault, VaultStatus};
use zeroize::Zeroizing;



use super::KeyVaultState;

pub(super) const SETTINGS_KEY_NAME: &str = "settings_api_key";

/// Matches the one vault entry the Settings page reads and writes.
pub(super) fn is_settings_key(entry: &KeyEntry) -> bool {
    entry.name == SETTINGS_KEY_NAME && entry.entry_type == "llm"
}

/// Falls back to the default model when the caller supplied a blank one.
pub(super) fn settings_note(model: &str) -> String {
    if model.trim().is_empty() {
        memopaws_config::config::DEFAULT_MODEL.to_string()
    } else {
        model.trim().to_string()
    }
}

/// Writes the Settings API key into the vault, replacing the existing entry.
///
/// Shared by `save_settings_key` (value typed into Settings) and
/// `promote_key_to_settings` (value copied from another vault entry); both need
/// the same "exactly one `settings_api_key` LLM entry" invariant.
pub(super) fn upsert_settings_key(
    vault: &mut KeyVault,
    value: &str,
    url: &str,
    note: &str,
) -> Result<(), String> {
    let input = || KeyEntryInput {
        name: SETTINGS_KEY_NAME.into(),
        entry_type: "llm".into(),
        value: value.to_owned(),
        url: url.to_owned(),
        url_anthropic: String::new(),
        note: note.to_owned(),
    };
    let existing = vault
        .list()
        .into_iter()
        .find(is_settings_key);
    match existing {
        Some(entry) => vault.update(entry.id, input()),
        None => vault.add(input()),
    }
    .map_err(|_| "API key could not be stored securely".to_string())?;
    Ok(())
}

pub(super) fn save_settings_key(
    state: &tauri::State<'_, KeyVaultState>,
    key: &str,
    url: &str,
    model: &str,
) -> Result<(), String> {
    let mut vault = lock_recover!(state);
    upsert_settings_key(&mut vault, key, url, &settings_note(model))
}

pub(crate) fn lock_vault_state(state: &KeyVaultState) {
    state
        .lock()
        .unwrap_or_else(|error| error.into_inner())
        .lock();
}

fn with_vault<T>(
    state: tauri::State<'_, KeyVaultState>,
    operation: impl FnOnce(&mut KeyVault) -> memopaws_keys::Result<T>,
) -> Result<T, String> {
    let mut vault = lock_recover!(state);
    operation(&mut vault).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn status(state: tauri::State<'_, KeyVaultState>) -> Result<VaultStatus, String> {
    with_vault(state, |vault| Ok(vault.status()))
}

#[tauri::command]
pub fn unlock(password: String, state: tauri::State<'_, KeyVaultState>) -> Result<bool, String> {
    let password = Zeroizing::new(password);
    with_vault(state, |vault| vault.unlock(password.as_str()))
}

#[tauri::command]
pub fn lock(state: tauri::State<'_, KeyVaultState>) -> Result<(), String> {
    with_vault(state, |vault| {
        vault.lock();
        Ok(())
    })
}

#[tauri::command]
pub fn set_master(password: String, state: tauri::State<'_, KeyVaultState>) -> Result<(), String> {
    let password = Zeroizing::new(password);
    with_vault(state, |vault| vault.set_master(password.as_str()))
}

#[tauri::command]
pub fn remove_master(state: tauri::State<'_, KeyVaultState>) -> Result<(), String> {
    with_vault(state, KeyVault::remove_master)
}

#[tauri::command]
pub fn list(state: tauri::State<'_, KeyVaultState>) -> Result<Vec<KeyEntry>, String> {
    with_vault(state, |vault| Ok(vault.list()))
}

#[tauri::command]
pub fn key_list(state: tauri::State<'_, KeyVaultState>) -> Result<Vec<KeyEntry>, String> {
    list(state)
}

#[tauri::command]
pub fn add(
    entry: KeyEntryInput,
    state: tauri::State<'_, KeyVaultState>,
) -> Result<KeyEntry, String> {
    with_vault(state, |vault| vault.add(entry))
}

/// opencode 配置中的自定义提供商
#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OpencodeProvider {
    pub id: String,
    pub url: String,
    pub api_key: String,
    pub models: Vec<String>,
}

#[tauri::command]
pub fn list_opencode_providers() -> Result<Vec<OpencodeProvider>, String> {
    let path = dirs::home_dir()
        .ok_or_else(|| "无法定位用户目录".to_string())?
        .join(".config")
        .join("opencode")
        .join("opencode.json");
    let raw = std::fs::read_to_string(&path)
        .map_err(|_| format!("未找到 opencode 配置: {}", path.display()))?;
    parse_opencode_providers(&raw)
}

fn parse_opencode_providers(raw: &str) -> Result<Vec<OpencodeProvider>, String> {
    let value: serde_json::Value =
        serde_json::from_str(raw).map_err(|error| format!("opencode 配置解析失败: {error}"))?;
    // 兼容 "provider" 与 "providers" 两种顶层键名
    let providers = value
        .get("provider")
        .or_else(|| value.get("providers"))
        .and_then(|value| value.as_object())
        .ok_or_else(|| "opencode 配置中没有 provider 定义".to_string())?;
    let mut result = Vec::new();
    for (id, def) in providers {
        let options = def.get("options").cloned().unwrap_or_default();
        let api_key = options
            .get("apiKey")
            .and_then(|value| value.as_str())
            .unwrap_or_default()
            .trim()
            .to_string();
        if api_key.is_empty() {
            continue;
        }
        let url = options
            .get("baseURL")
            .and_then(|value| value.as_str())
            .unwrap_or_default()
            .trim()
            .to_string();
        let mut models: Vec<String> = def
            .get("models")
            .and_then(|models| models.as_object())
            .map(|models| models.keys().cloned().collect())
            .unwrap_or_default();
        models.sort();
        result.push(OpencodeProvider { id: id.clone(), url, api_key, models });
    }
    Ok(result)
}

#[tauri::command]
pub fn update(
    id: u64,
    entry: KeyEntryInput,
    state: tauri::State<'_, KeyVaultState>,
) -> Result<KeyEntry, String> {
    with_vault(state, |vault| vault.update(id, entry))
}

#[tauri::command]
pub fn delete(id: u64, state: tauri::State<'_, KeyVaultState>) -> Result<(), String> {
    with_vault(state, |vault| vault.delete(id))
}

#[tauri::command]
pub fn reorder(
    entry_type: String,
    ids: Vec<u64>,
    state: tauri::State<'_, KeyVaultState>,
) -> Result<(), String> {
    with_vault(state, |vault| vault.reorder(&entry_type, &ids))
}

#[tauri::command]
pub fn get_value(id: u64, state: tauri::State<'_, KeyVaultState>) -> Result<String, String> {
    with_vault(state, |vault| vault.get_value(id))
}

#[cfg(test)]
mod tests {
    use std::{
        sync::{Arc, Mutex},
        time::{SystemTime, UNIX_EPOCH},
    };

    #[test]
    fn opencode_providers_parse_provider_and_providers_keys_and_skip_keyless() {
        let raw = r#"{
            "provider": {
                "sensenova": {
                    "options": { "baseURL": "https://token.sensenova.cn/v1", "apiKey": "sk-abc" },
                    "models": { "b-model": {}, "a-model": {} }
                },
                "no-key": { "options": { "baseURL": "https://x.example/v1" }, "models": { "m": {} } }
            }
        }"#;
        let parsed = super::parse_opencode_providers(raw).unwrap();
        assert_eq!(parsed.len(), 1);
        assert_eq!(parsed[0].id, "sensenova");
        assert_eq!(parsed[0].url, "https://token.sensenova.cn/v1");
        assert_eq!(parsed[0].api_key, "sk-abc");
        assert_eq!(parsed[0].models, vec!["a-model".to_string(), "b-model".to_string()]);

        let legacy = r#"{ "providers": { "p": { "options": { "apiKey": "k" } } } }"#;
        let parsed = super::parse_opencode_providers(legacy).unwrap();
        assert_eq!(parsed.len(), 1);
        assert!(parsed[0].models.is_empty());

        assert!(super::parse_opencode_providers("{}").is_err());
    }

    use memopaws_keys::{KeyEntryInput, KeyVault};

    #[test]
    fn lock_vault_state_recovers_from_a_poisoned_mutex() {
        let path = std::env::temp_dir().join(format!(
            "memopaws-close-lock-{}.json",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
        ));
        let mut vault = KeyVault::load(&path).unwrap();
        vault.set_master("test-password").unwrap();
        let state = Arc::new(Mutex::new(vault));
        let poisoned = Arc::clone(&state);
        let _ = std::thread::spawn(move || {
            let _guard = poisoned.lock().unwrap();
            panic!("poison test mutex");
        })
        .join();

        super::lock_vault_state(&state);

        assert!(
            !state
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .status()
                .unlocked
        );
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn settings_api_key_is_saved_idempotently_in_the_vault() {
        // save_settings_key requires a tauri::State handle, so this exercises the
        // exact same find-then-update-or-add flow against a real vault file.
        let path = std::env::temp_dir().join(format!(
            "memopaws-settings-key-{}.json",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
        ));
        let mut vault = KeyVault::load(&path).unwrap();
        let save = |vault: &mut KeyVault, key: &str| {
            let input = || KeyEntryInput {
                name: "settings_api_key".into(),
                entry_type: "llm".into(),
                value: key.to_owned(),
                url: "https://example.test/v1".into(),
                url_anthropic: String::new(),
                note: "Settings API key".into(),
            };
            if let Some(entry) = vault
                .list()
                .into_iter()
                .find(|entry| entry.name == "settings_api_key" && entry.entry_type == "llm")
            {
                vault.update(entry.id, input()).unwrap();
            } else {
                vault.add(input()).unwrap();
            }
        };
        save(&mut vault, "first-key");
        save(&mut vault, "second-key");

        let entries = vault.list();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].name, "settings_api_key");
        assert_eq!(vault.get_value(entries[0].id).unwrap(), "second-key");

        let reloaded = KeyVault::load(&path).unwrap();
        assert_eq!(reloaded.list().len(), 1);
        let _ = std::fs::remove_file(path);
    }

}
