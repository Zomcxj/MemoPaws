use std::{fs, io::Write, path::{Path, PathBuf}};

use aes_gcm::{aead::{Aead, KeyInit}, Aes256Gcm, Nonce};
use base64::{engine::general_purpose::STANDARD, Engine};
use rand::{Rng, RngCore};
use scrypt::{scrypt, Params};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tempfile::NamedTempFile;
use zeroize::{Zeroize, Zeroizing};

const VERIFIER: &str = "MemoPaws key verifier";
const MAX_SAFE_INTEGER: u64 = (1_u64 << 53) - 1;

pub type Result<T> = std::result::Result<T, KeyVaultError>;

pub struct KeyVaultError {
    message: String,
    locked_vault: Option<KeyVault>,
}

impl std::fmt::Debug for KeyVaultError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.debug_struct("KeyVaultError").field("message", &self.message).finish_non_exhaustive()
    }
}

impl KeyVaultError {
    fn new(message: impl Into<String>) -> Self { Self { message: message.into(), locked_vault: None } }
    fn load(message: impl Into<String>, path: PathBuf) -> Self {
        Self { message: message.into(), locked_vault: Some(KeyVault::failed(path)) }
    }
    pub fn into_locked_vault(mut self) -> KeyVault { self.locked_vault.take().expect("not a load error") }
}

impl std::fmt::Display for KeyVaultError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { formatter.write_str(&self.message) }
}
impl std::error::Error for KeyVaultError {}

#[derive(Deserialize)]
struct StoredEntry {
    id: u64,
    name: String,
    #[serde(rename = "type")]
    entry_type: String,
    #[serde(default)]
    value: Option<String>,
    #[serde(default)]
    enc_value: Option<String>,
    #[serde(default)]
    url: String,
    #[serde(default)]
    url_anthropic: String,
    #[serde(default)]
    note: String,
    order: Option<i64>,
    #[serde(default)]
    created: String,
}

#[derive(Clone)]
struct VaultEntry {
    id: u64,
    name: String,
    entry_type: String,
    value: Option<Zeroizing<String>>,
    enc_value: Option<String>,
    url: String,
    url_anthropic: String,
    note: String,
    order: i64,
    created: String,
}

impl VaultEntry {
    fn from_stored(entry: StoredEntry, default_order: i64) -> Self {
        Self { id: entry.id, name: entry.name, entry_type: entry.entry_type, value: entry.value.map(Zeroizing::new), enc_value: entry.enc_value, url: entry.url, url_anthropic: entry.url_anthropic, note: entry.note, order: entry.order.unwrap_or(default_order), created: entry.created }
    }
}

#[derive(Clone, Deserialize, Serialize)]
pub struct KdfConfig {
    pub name: String,
    pub salt: String,
    pub n: u64,
    pub r: u32,
    pub p: u32,
}

#[derive(Deserialize)]
struct StoredVault {
    #[serde(default = "version_two")]
    version: u8,
    #[serde(default)]
    master_hash: String,
    #[serde(default)]
    kdf: Option<KdfConfig>,
    #[serde(default)]
    verifier: String,
    #[serde(default)]
    entries: Vec<StoredEntry>,
}

fn version_two() -> u8 { 2 }

#[derive(Deserialize)]
pub struct KeyEntryInput {
    pub name: String,
    #[serde(rename = "type")]
    pub entry_type: String,
    pub value: String,
    #[serde(default)]
    pub url: String,
    #[serde(default)]
    pub url_anthropic: String,
    #[serde(default)]
    pub note: String,
}

impl Drop for KeyEntryInput {
    fn drop(&mut self) { self.value.zeroize(); }
}

#[derive(Clone, Serialize)]
pub struct KeyEntry {
    pub id: u64,
    pub name: String,
    #[serde(rename = "type")]
    pub entry_type: String,
    pub url: String,
    pub url_anthropic: String,
    pub note: String,
    pub order: i64,
    pub created: String,
}

impl From<&VaultEntry> for KeyEntry {
    fn from(entry: &VaultEntry) -> Self {
        Self { id: entry.id, name: entry.name.clone(), entry_type: entry.entry_type.clone(), url: entry.url.clone(), url_anthropic: entry.url_anthropic.clone(), note: entry.note.clone(), order: entry.order, created: entry.created.clone() }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct VaultStatus {
    pub has_master: bool,
    pub unlocked: bool,
    pub load_failed: bool,
    pub version: u8,
}

pub struct KeyVault {
    path: PathBuf,
    entries: Vec<VaultEntry>,
    master_hash: String,
    key: Option<SecretKey>,
    version: u8,
    kdf: Option<KdfConfig>,
    verifier: String,
    unlocked: bool,
    load_failed: bool,
    save_failure_for_test: bool,
}

impl std::fmt::Debug for KeyVault {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("KeyVault")
            .field("path", &self.path)
            .field("entry_count", &self.entries.len())
            .field("version", &self.version)
            .field("unlocked", &self.unlocked)
            .field("load_failed", &self.load_failed)
            .finish_non_exhaustive()
    }
}

impl KeyVault {
    pub fn load(path: impl Into<PathBuf>) -> Result<Self> {
        let path = path.into();
        if !path.exists() {
            return Ok(Self { path, entries: vec![], master_hash: String::new(), key: None, version: 3, kdf: None, verifier: String::new(), unlocked: true, load_failed: false, save_failure_for_test: false });
        }
        let loaded = (|| -> std::result::Result<Self, String> {
            let text = fs::read_to_string(&path).map_err(|e| e.to_string())?;
            let raw: StoredVault = serde_json::from_str(&text).map_err(|e| e.to_string())?;
            if !matches!(raw.version, 2 | 3) { return Err("unsupported key vault version".into()); }
            if raw.version == 3 && (raw.kdf.is_none() || raw.verifier.is_empty()) { return Err("v3 key vault is missing KDF or verifier".into()); }
            if raw.version == 3 && raw.kdf.as_ref().is_some_and(|kdf| kdf.name != "scrypt") { return Err("unsupported v3 KDF".into()); }
            let has_master = !raw.master_hash.is_empty() || !raw.verifier.is_empty();
            let mut entries: Vec<VaultEntry> = raw.entries.into_iter().enumerate().map(|(index, entry)| VaultEntry::from_stored(entry, index as i64)).collect();
            for entry in &mut entries {
                if has_master {
                    entry.value = None;
                } else if entry.value.is_none() {
                    entry.value = entry.enc_value.take().map(Zeroizing::new);
                }
            }
            Ok(Self { path: path.clone(), entries, master_hash: raw.master_hash, key: None, version: raw.version, kdf: raw.kdf, verifier: raw.verifier, unlocked: !has_master, load_failed: false, save_failure_for_test: false })
        })();
        loaded.map_err(|message| KeyVaultError::load(format!("failed to load key vault: {message}"), path))
    }

    fn failed(path: PathBuf) -> Self {
        Self { path, entries: vec![], master_hash: String::new(), key: None, version: 3, kdf: None, verifier: String::new(), unlocked: false, load_failed: true, save_failure_for_test: false }
    }

    pub fn path(&self) -> &Path { &self.path }
    pub fn status(&self) -> VaultStatus { VaultStatus { has_master: self.has_master(), unlocked: self.unlocked, load_failed: self.load_failed, version: self.version } }
    pub fn has_master(&self) -> bool { !self.master_hash.is_empty() || !self.verifier.is_empty() }
    pub fn list(&self) -> Vec<KeyEntry> {
        if !self.unlocked { return vec![]; }
        let mut entries: Vec<_> = self.entries.iter().map(KeyEntry::from).collect();
        entries.sort_by_key(|entry| (entry.entry_type.clone(), entry.order));
        entries
    }

    pub fn unlock(&mut self, password: &str) -> Result<bool> {
        if self.load_failed { return Err(KeyVaultError::new("key vault load failed")); }
        if !self.has_master() { return Ok(false); }
        let was_locked = self.snapshot();
        let key = if self.version == 3 {
            derive_scrypt(password, self.kdf.as_ref().ok_or_else(|| KeyVaultError::new("missing KDF"))?)?
        } else {
            let key: SecretKey = Zeroizing::new(Sha256::digest(password.as_bytes()).into());
            if hex_digest(&key[..]) != self.master_hash { return Ok(false); }
            key
        };
        if self.version == 3 && decrypt(&self.verifier, &key[..]).map_or(true, |value| value != VERIFIER) { return Ok(false); }
        let values: Result<Vec<_>> = self.entries.iter().map(|entry| {
            let ciphertext = entry.enc_value.as_deref().ok_or_else(|| KeyVaultError::new("encrypted entry is missing ciphertext"))?;
            Ok(Zeroizing::new(decrypt(ciphertext, &key[..])?))
        }).collect();
        for (entry, value) in self.entries.iter_mut().zip(values?) { entry.value = Some(value); }
        self.key = Some(key);
        self.unlocked = true;
        if self.version == 2 {
            if let Err(error) = self.configure_v3(password).and_then(|_| self.save()) { self.restore(was_locked); return Err(error); }
        }
        Ok(true)
    }

    pub fn lock(&mut self) {
        if !self.has_master() { return; }
        for entry in &mut self.entries { entry.value = None; }
        self.key = None;
        self.unlocked = false;
    }

    pub fn set_master(&mut self, password: &str) -> Result<()> {
        self.require_writable()?;
        let snapshot = self.snapshot();
        if let Err(error) = self.configure_v3(password).and_then(|_| self.save()) { self.restore(snapshot); return Err(error); }
        Ok(())
    }

    pub fn remove_master(&mut self) -> Result<()> {
        self.require_writable()?;
        let snapshot = self.snapshot();
        self.master_hash.clear(); self.verifier.clear(); self.kdf = None; self.key = None; self.version = 3; self.unlocked = true;
        for entry in &mut self.entries { entry.enc_value = None; }
        if let Err(error) = self.save() { self.restore(snapshot); return Err(error); }
        Ok(())
    }

    pub fn add(&mut self, mut input: KeyEntryInput) -> Result<KeyEntry> {
        self.require_writable()?;
        validate_input(&input)?;
        let snapshot = self.snapshot();
        let order = self.entries.iter().filter(|e| e.entry_type == input.entry_type).map(|e| e.order).max().unwrap_or(-1) + 1;
        let mut rng = rand::thread_rng();
        let id = loop { let value = rng.gen_range(1..=MAX_SAFE_INTEGER); if self.entries.iter().all(|e| e.id != value) { break value; } };
        let entry = VaultEntry { id, name: std::mem::take(&mut input.name), entry_type: std::mem::take(&mut input.entry_type), value: Some(Zeroizing::new(std::mem::take(&mut input.value))), enc_value: None, url: std::mem::take(&mut input.url), url_anthropic: std::mem::take(&mut input.url_anthropic), note: std::mem::take(&mut input.note), order, created: now_string() };
        // `save()` only touches `value`/`enc_value`, neither of which `KeyEntry`
        // exposes, so the view is taken before the write to avoid re-finding the
        // entry afterwards.
        let view = KeyEntry::from(&entry);
        self.entries.push(entry);
        if let Err(error) = self.save() { self.restore(snapshot); return Err(error); }
        Ok(view)
    }

    pub fn update(&mut self, id: u64, mut input: KeyEntryInput) -> Result<KeyEntry> {
        self.require_writable()?;
        validate_input(&input)?;
        let snapshot = self.snapshot();
        let entry = self.entries.iter_mut().find(|e| e.id == id).ok_or_else(|| KeyVaultError::new("key entry not found"))?;
        entry.name = std::mem::take(&mut input.name); entry.entry_type = std::mem::take(&mut input.entry_type); entry.value = Some(Zeroizing::new(std::mem::take(&mut input.value))); entry.url = std::mem::take(&mut input.url); entry.url_anthropic = std::mem::take(&mut input.url_anthropic); entry.note = std::mem::take(&mut input.note);
        let view = KeyEntry::from(&*entry);
        if let Err(error) = self.save() { self.restore(snapshot); return Err(error); }
        Ok(view)
    }

    pub fn delete(&mut self, id: u64) -> Result<()> {
        self.require_writable()?;
        let snapshot = self.snapshot();
        self.entries.retain(|entry| entry.id != id);
        if self.entries.len() == snapshot.entries.len() { return Err(KeyVaultError::new("key entry not found")); }
        if let Err(error) = self.save() { self.restore(snapshot); return Err(error); }
        Ok(())
    }

    pub fn reorder(&mut self, entry_type: &str, ids: &[u64]) -> Result<()> {
        self.require_writable()?;
        let mut current: Vec<u64> = self.entries.iter().filter(|entry| entry.entry_type == entry_type).map(|entry| entry.id).collect();
        let mut requested = ids.to_vec(); current.sort_unstable(); requested.sort_unstable();
        if current != requested { return Err(KeyVaultError::new("reorder IDs must exactly match the group")); }
        let snapshot = self.snapshot();
        // `current == requested` above proves every id resolves, so a lookup table
        // replaces the per-id linear scan (and its unwrap) with one pass.
        let positions: std::collections::HashMap<u64, i64> = ids.iter().enumerate().map(|(order, id)| (*id, order as i64)).collect();
        for entry in &mut self.entries { if let Some(order) = positions.get(&entry.id) { entry.order = *order; } }
        if let Err(error) = self.save() { self.restore(snapshot); return Err(error); }
        Ok(())
    }

    pub fn get_value(&self, id: u64) -> Result<String> {
        if !self.unlocked { return Err(KeyVaultError::new("key vault is locked")); }
        self.entries.iter().find(|entry| entry.id == id).and_then(|entry| entry.value.as_ref()).map(|value| value.to_string()).ok_or_else(|| KeyVaultError::new("key entry not found"))
    }

    #[doc(hidden)]
    pub fn set_save_failure_for_test(&mut self, value: bool) { self.save_failure_for_test = value; }

    fn configure_v3(&mut self, password: &str) -> Result<()> {
        if password.is_empty() { return Err(KeyVaultError::new("master password cannot be empty")); }
        let mut salt = [0_u8; 16]; rand::thread_rng().fill_bytes(&mut salt);
        let kdf = KdfConfig { name: "scrypt".into(), salt: STANDARD.encode(salt), n: 1 << 14, r: 8, p: 1 };
        let key = derive_scrypt(password, &kdf)?;
        self.verifier = encrypt(VERIFIER, key.as_ref())?; self.master_hash.clear(); self.kdf = Some(kdf); self.key = Some(key); self.version = 3; self.unlocked = true;
        Ok(())
    }

    fn require_writable(&self) -> Result<()> {
        if self.load_failed { return Err(KeyVaultError::new("key vault load failed; writes are disabled")); }
        if !self.unlocked { return Err(KeyVaultError::new("key vault is locked")); }
        Ok(())
    }

    fn save(&mut self) -> Result<()> {
        self.require_writable()?;
        if self.save_failure_for_test { return Err(KeyVaultError::new("injected save failure")); }
        if let Some(parent) = self.path.parent() { fs::create_dir_all(parent).map_err(|e| KeyVaultError::new(e.to_string()))?; }
        let mut saved = Vec::with_capacity(self.entries.len());
        let has_master = self.has_master();
        for entry in &mut self.entries {
            let (value, enc_value) = if has_master {
                let key = self.key.as_ref().ok_or_else(|| KeyVaultError::new("encryption key unavailable"))?;
                let plaintext = entry.value.as_ref().ok_or_else(|| KeyVaultError::new("entry plaintext unavailable"))?;
                let ciphertext = encrypt(plaintext, &key[..])?;
                entry.enc_value = Some(ciphertext.clone());
                (None, Some(ciphertext))
            } else {
                let plaintext = entry.value.as_ref().ok_or_else(|| KeyVaultError::new("entry plaintext unavailable"))?.to_string();
                entry.enc_value = None;
                (Some(plaintext), None)
            };
            saved.push(serde_json::json!({"id":entry.id,"name":entry.name,"type":entry.entry_type,"value":value,"enc_value":enc_value,"url":entry.url,"url_anthropic":entry.url_anthropic,"note":entry.note,"order":entry.order,"created":entry.created}));
        }
        // `json!({...})` above always yields objects; filter_map keeps that fact
        // local instead of asserting it with an unwrap.
        for item in saved.iter_mut().filter_map(serde_json::Value::as_object_mut) {
            if item.get("value").is_some_and(serde_json::Value::is_null) { item.remove("value"); }
            if item.get("enc_value").is_some_and(serde_json::Value::is_null) { item.remove("enc_value"); }
        }
        let mut root = serde_json::json!({"version":if self.has_master() { self.version } else { 2 },"master_hash":self.master_hash,"entries":saved});
        if self.has_master() && self.version == 3 {
            root["kdf"] = serde_json::to_value(&self.kdf).map_err(|e| KeyVaultError::new(e.to_string()))?;
            root["verifier"] = serde_json::Value::String(self.verifier.clone());
        }
        let parent = self.path.parent().unwrap_or_else(|| Path::new("."));
        let mut temporary = NamedTempFile::new_in(parent).map_err(|e| KeyVaultError::new(e.to_string()))?;
        serde_json::to_writer_pretty(&mut temporary, &root).map_err(|e| KeyVaultError::new(e.to_string()))?;
        temporary.write_all(b"\n").and_then(|_| temporary.as_file().sync_all()).map_err(|e| KeyVaultError::new(e.to_string()))?;
        temporary.persist(&self.path).map_err(|e| KeyVaultError::new(e.error.to_string()))?;
        Ok(())
    }

    fn snapshot(&self) -> Snapshot { Snapshot { entries: self.entries.clone(), master_hash: self.master_hash.clone(), key: self.key.clone(), version: self.version, kdf: self.kdf.clone(), verifier: self.verifier.clone(), unlocked: self.unlocked } }
    fn restore(&mut self, snapshot: Snapshot) { self.entries = snapshot.entries; self.master_hash = snapshot.master_hash; self.key = snapshot.key; self.version = snapshot.version; self.kdf = snapshot.kdf; self.verifier = snapshot.verifier; self.unlocked = snapshot.unlocked; }
}

type SecretKey = Zeroizing<[u8; 32]>;

struct Snapshot { entries: Vec<VaultEntry>, master_hash: String, key: Option<SecretKey>, version: u8, kdf: Option<KdfConfig>, verifier: String, unlocked: bool }

fn validate_input(input: &KeyEntryInput) -> Result<()> {
    if input.name.trim().is_empty() || input.value.is_empty() { return Err(KeyVaultError::new("name and value are required")); }
    if !matches!(input.entry_type.as_str(), "llm" | "secret") { return Err(KeyVaultError::new("type must be llm or secret")); }
    Ok(())
}

fn derive_scrypt(password: &str, config: &KdfConfig) -> Result<SecretKey> {
    if config.name != "scrypt" || !config.n.is_power_of_two() || config.n < 2 { return Err(KeyVaultError::new("invalid scrypt parameters")); }
    let log_n = config.n.trailing_zeros() as u8;
    let params = Params::new(log_n, config.r, config.p, 32).map_err(|e| KeyVaultError::new(e.to_string()))?;
    let salt = STANDARD.decode(&config.salt).map_err(|e| KeyVaultError::new(e.to_string()))?;
    let mut key = Zeroizing::new([0_u8; 32]);
    scrypt(password.as_bytes(), &salt, &params, &mut key[..]).map_err(|e| KeyVaultError::new(e.to_string()))?;
    Ok(key)
}

fn encrypt(plaintext: &str, key: &[u8]) -> Result<String> {
    let cipher = Aes256Gcm::new_from_slice(key).map_err(|e| KeyVaultError::new(e.to_string()))?;
    let mut nonce = [0_u8; 12]; rand::thread_rng().fill_bytes(&mut nonce);
    let encrypted = cipher.encrypt(Nonce::from_slice(&nonce), plaintext.as_bytes()).map_err(|e| KeyVaultError::new(e.to_string()))?;
    let mut output = nonce.to_vec(); output.extend(encrypted);
    Ok(format!("v2:{}", STANDARD.encode(output)))
}

fn decrypt(ciphertext: &str, key: &[u8]) -> Result<String> {
    let plaintext = if let Some(encoded) = ciphertext.strip_prefix("v2:") {
        let data = STANDARD.decode(encoded).map_err(|e| KeyVaultError::new(format!("invalid ciphertext: {e}")))?;
        if data.len() <= 12 { return Err(KeyVaultError::new("ciphertext is incomplete")); }
        let cipher = Aes256Gcm::new_from_slice(key).map_err(|e| KeyVaultError::new(e.to_string()))?;
        cipher.decrypt(Nonce::from_slice(&data[..12]), &data[12..]).map_err(|_| KeyVaultError::new("ciphertext authentication failed"))?
    } else {
        let data = STANDARD.decode(ciphertext).map_err(|e| KeyVaultError::new(format!("invalid legacy ciphertext: {e}")))?;
        data.iter().enumerate().map(|(index, byte)| byte ^ key[index % key.len()]).collect()
    };
    String::from_utf8(plaintext).map_err(|e| KeyVaultError::new(e.to_string()))
}

fn hex_digest(bytes: &[u8]) -> String { bytes.iter().map(|byte| format!("{byte:02x}")).collect() }
fn now_string() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now().duration_since(UNIX_EPOCH).map(|value| value.as_secs().to_string()).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn make_input(name: &str, kind: &str, value: &str) -> KeyEntryInput {
        KeyEntryInput {
            name: name.into(),
            entry_type: kind.into(),
            value: value.into(),
            url: String::new(),
            url_anthropic: String::new(),
            note: String::new(),
        }
    }

    fn make_input_full(name: &str, kind: &str, value: &str, url: &str) -> KeyEntryInput {
        KeyEntryInput {
            name: name.into(),
            entry_type: kind.into(),
            value: value.into(),
            url: url.into(),
            url_anthropic: String::new(),
            note: String::new(),
        }
    }

    // ── 1. set_master / unlock / lock / remove_master ──────────────────

    #[test]
    fn set_master_and_unlock_roundtrip() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test.json");
        let mut vault = KeyVault::load(path).unwrap();
        vault.add(make_input("k", "llm", "tok")).unwrap();

        vault.set_master("secret123").unwrap();
        assert!(vault.has_master());
        assert!(vault.status().unlocked);

        vault.lock();
        assert!(!vault.status().unlocked);
        assert!(vault.list().is_empty());

        assert!(vault.unlock("secret123").unwrap());
        assert!(vault.status().unlocked);
        assert_eq!(vault.get_value(vault.list()[0].id).unwrap(), "tok");
    }

    #[test]
    fn set_master_empty_password_rejected() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test.json");
        let mut vault = KeyVault::load(path).unwrap();
        vault.add(make_input("k", "llm", "v")).unwrap();
        assert!(vault.set_master("").is_err());
        assert!(!vault.has_master());
    }

    #[test]
    fn unlock_wrong_password_returns_false() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test.json");
        let mut vault = KeyVault::load(path).unwrap();
        vault.set_master("real").unwrap();
        vault.lock();
        assert!(!vault.unlock("wrong").unwrap());
        assert!(!vault.status().unlocked);
    }

    #[test]
    fn lock_then_unlock_preserves_all_entries() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test.json");
        let mut vault = KeyVault::load(path).unwrap();
        let ids: Vec<u64> = (0..5)
            .map(|i| vault.add(make_input(&format!("e{i}"), "secret", &format!("v{i}"))).unwrap().id)
            .collect();

        vault.set_master("pw").unwrap();
        vault.lock();
        assert!(vault.list().is_empty());
        vault.unlock("pw").unwrap();

        let listed = vault.list();
        assert_eq!(listed.len(), 5);
        for id in &ids {
            assert!(vault.get_value(*id).is_ok());
        }
    }

    #[test]
    fn remove_master_unlocks_and_clears_encryption() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test.json");
        let mut vault = KeyVault::load(&path).unwrap();
        let id = vault.add(make_input("a", "secret", "plain")).unwrap().id;

        vault.set_master("pw").unwrap();
        vault.remove_master().unwrap();
        assert!(!vault.has_master());
        assert!(vault.status().unlocked);
        assert_eq!(vault.get_value(id).unwrap(), "plain");

        let disk = fs::read_to_string(&path).unwrap();
        assert!(disk.contains("plain"));
        assert!(!disk.contains("enc_value"));
    }

    #[test]
    fn lock_noop_when_no_master_set() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test.json");
        let mut vault = KeyVault::load(path).unwrap();
        vault.add(make_input("k", "llm", "v")).unwrap();
        vault.lock();
        // Without master, lock() is a no-op; vault stays unlocked
        assert!(vault.status().unlocked);
        assert_eq!(vault.list().len(), 1);
    }

    #[test]
    fn duplicate_set_master_rekeys_entries() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test.json");
        let mut vault = KeyVault::load(path).unwrap();
        let id = vault.add(make_input("k", "llm", "tok")).unwrap().id;

        vault.set_master("old").unwrap();
        vault.set_master("new").unwrap();
        vault.lock();
        assert!(!vault.unlock("old").unwrap());
        assert!(vault.unlock("new").unwrap());
        assert_eq!(vault.get_value(id).unwrap(), "tok");
    }

    // ── 2. add / update / delete ──────────────────────────────────────

    #[test]
    fn add_requires_name_and_value() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        assert!(vault.add(make_input("", "llm", "v")).is_err());
        assert!(vault.add(make_input("  ", "llm", "v")).is_err());
        assert!(vault.add(make_input("n", "llm", "")).is_err());
        assert!(vault.list().is_empty());
    }

    #[test]
    fn add_rejects_invalid_type() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        assert!(vault.add(make_input("k", "other", "v")).is_err());
        assert!(vault.add(make_input("k", "LLM", "v")).is_err());
        assert!(vault.add(make_input("k", "Secret", "v")).is_err());
        assert!(vault.list().is_empty());
    }

    #[test]
    fn add_accepts_llm_and_secret_types() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let a = vault.add(make_input("l", "llm", "v1")).unwrap();
        let b = vault.add(make_input("s", "secret", "v2")).unwrap();
        assert_eq!(a.entry_type, "llm");
        assert_eq!(b.entry_type, "secret");
    }

    #[test]
    fn add_ids_are_unique_and_incrementing() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let mut ids = std::collections::HashSet::new();
        for i in 0..20 {
            let entry = vault.add(make_input(&format!("e{i}"), "llm", "v")).unwrap();
            assert!(ids.insert(entry.id), "duplicate id {}", entry.id);
        }
    }

    #[test]
    fn add_stores_url() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let e = vault.add(make_input_full("k", "llm", "v", "https://api.example.com")).unwrap();
        assert_eq!(e.url, "https://api.example.com");
    }

    #[test]
    fn update_validates_name_and_value_and_type() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let id = vault.add(make_input("k", "llm", "old")).unwrap().id;
        assert!(vault.update(id, make_input("", "llm", "x")).is_err());
        assert!(vault.update(id, make_input("ok", "llm", "")).is_err());
        assert!(vault.update(id, make_input("ok", "bad", "x")).is_err());
        assert_eq!(vault.get_value(id).unwrap(), "old");
    }

    #[test]
    fn update_nonexistent_id_fails() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        assert!(vault.update(999, make_input("n", "llm", "v")).is_err());
    }

    #[test]
    fn delete_nonexistent_id_fails() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        assert!(vault.delete(999).is_err());
    }

    #[test]
    fn delete_removes_only_target() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let a = vault.add(make_input("a", "llm", "1")).unwrap();
        let b = vault.add(make_input("b", "secret", "2")).unwrap();
        vault.delete(a.id).unwrap();
        assert_eq!(vault.list().len(), 1);
        assert_eq!(vault.list()[0].id, b.id);
    }

    // ── 3. get_value ──────────────────────────────────────────────────

    #[test]
    fn get_value_returns_plaintext() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let e = vault.add(make_input("k", "llm", "my-secret-value")).unwrap();
        assert_eq!(vault.get_value(e.id).unwrap(), "my-secret-value");
    }

    #[test]
    fn get_value_nonexistent_id_errors() {
        let dir = tempdir().unwrap();
        let vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        assert!(vault.get_value(12345).is_err());
    }

    #[test]
    fn get_value_locked_vault_errors() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("t.json");
        let mut vault = KeyVault::load(path).unwrap();
        let id = vault.add(make_input("k", "llm", "v")).unwrap().id;
        vault.set_master("pw").unwrap();
        vault.lock();
        let err = vault.get_value(id).unwrap_err();
        assert!(format!("{err}").contains("locked"));
    }

    // ── 4. 加密性：JSON 不含明文 ─────────────────────────────────────

    #[test]
    fn add_with_master_hidden_value_not_in_json() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("t.json");
        let mut vault = KeyVault::load(path.clone()).unwrap();
        vault.set_master("pw").unwrap();
        vault.add(make_input("mykey", "secret", "super-secret-123")).unwrap();

        let disk = fs::read_to_string(&path).unwrap();
        assert!(!disk.contains("super-secret-123"), "plaintext leaked to disk");
        assert!(disk.contains("enc_value"), "should have enc_value");
        assert!(!disk.contains("super-secret-123"));
    }

    #[test]
    fn list_output_never_contains_plaintext() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        vault.add(make_input("k", "llm", "secrettoken")).unwrap();
        let json = serde_json::to_string(&vault.list()).unwrap();
        assert!(!json.contains("secrettoken"));
    }

    // ── 5. reorder ────────────────────────────────────────────────────

    #[test]
    fn reorder_same_type_works() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let a = vault.add(make_input("a", "llm", "1")).unwrap();
        let b = vault.add(make_input("b", "llm", "2")).unwrap();
        let c = vault.add(make_input("c", "llm", "3")).unwrap();

        vault.reorder("llm", &[c.id, a.id, b.id]).unwrap();
        let ids: Vec<u64> = vault.list().iter().filter(|e| e.entry_type == "llm").map(|e| e.id).collect();
        assert_eq!(ids, vec![c.id, a.id, b.id]);
    }

    #[test]
    fn reorder_cross_type_isolation() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let s1 = vault.add(make_input("s1", "secret", "1")).unwrap();
        let s2 = vault.add(make_input("s2", "secret", "2")).unwrap();
        let l1 = vault.add(make_input("l1", "llm", "3")).unwrap();
        let l2 = vault.add(make_input("l2", "llm", "4")).unwrap();

        // Reorder secrets only; llm order unchanged
        vault.reorder("secret", &[s2.id, s1.id]).unwrap();
        let secret_ids: Vec<u64> = vault.list().iter().filter(|e| e.entry_type == "secret").map(|e| e.id).collect();
        let llm_ids: Vec<u64> = vault.list().iter().filter(|e| e.entry_type == "llm").map(|e| e.id).collect();
        assert_eq!(secret_ids, vec![s2.id, s1.id]);
        assert_eq!(llm_ids, vec![l1.id, l2.id]);
    }

    #[test]
    fn reorder_missing_id_rejected() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let a = vault.add(make_input("a", "llm", "1")).unwrap();
        let b = vault.add(make_input("b", "llm", "2")).unwrap();
        // Missing b.id
        assert!(vault.reorder("llm", &[a.id]).is_err());
        // Extra phantom id
        assert!(vault.reorder("llm", &[a.id, b.id, 999999]).is_err());
    }

    #[test]
    fn reorder_sets_order_indices_sequentially() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let a = vault.add(make_input("a", "secret", "1")).unwrap();
        let b = vault.add(make_input("b", "secret", "2")).unwrap();
        let c = vault.add(make_input("c", "secret", "3")).unwrap();

        vault.reorder("secret", &[c.id, a.id, b.id]).unwrap();
        // After reload, order persists
        let reloaded = KeyVault::load(dir.path().join("t.json")).unwrap();
        let ids: Vec<u64> = reloaded.list().iter().filter(|e| e.entry_type == "secret").map(|e| e.id).collect();
        assert_eq!(ids, vec![c.id, a.id, b.id]);
    }

    #[test]
    fn reorder_empty_vec_rejected() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let _a = vault.add(make_input("a", "llm", "1")).unwrap();
        assert!(vault.reorder("llm", &[]).is_err());
    }

    // ── 6. 持久化 save/load 往返 ─────────────────────────────────────

    #[test]
    fn save_load_roundtrip_without_master() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("t.json");
        let mut vault = KeyVault::load(path.clone()).unwrap();
        vault.add(make_input("k1", "llm", "val1")).unwrap();
        vault.add(make_input("k2", "secret", "val2")).unwrap();

        let reloaded = KeyVault::load(path).unwrap();
        assert!(reloaded.status().unlocked);
        assert!(!reloaded.status().has_master);
        assert_eq!(reloaded.list().len(), 2);
        let entries = reloaded.list();
        let k1 = entries.iter().find(|e| e.name == "k1").unwrap();
        let k2 = entries.iter().find(|e| e.name == "k2").unwrap();
        assert_eq!(reloaded.get_value(k1.id).unwrap(), "val1");
        assert_eq!(reloaded.get_value(k2.id).unwrap(), "val2");
    }

    #[test]
    fn save_load_roundtrip_with_master() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("t.json");
        let mut vault = KeyVault::load(path.clone()).unwrap();
        let id = vault.add(make_input("k", "llm", "secret-token")).unwrap().id;
        vault.set_master("pw").unwrap();
        vault.lock();

        let mut reloaded = KeyVault::load(path).unwrap();
        assert!(reloaded.status().has_master);
        assert!(!reloaded.status().unlocked);
        assert!(reloaded.unlock("pw").unwrap());
        assert_eq!(reloaded.get_value(id).unwrap(), "secret-token");
    }

    #[test]
    fn load_nonexistent_file_returns_empty_unlocked_vault() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("nonexistent.json");
        let vault = KeyVault::load(path).unwrap();
        assert!(vault.status().unlocked);
        assert!(!vault.status().has_master);
        assert!(vault.list().is_empty());
    }

    // ── 7. settings_api_key 幂等保存语义 ──────────────────────────────

    #[test]
    fn settings_api_key_idempotent_add_same_name() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("t.json");
        let mut vault = KeyVault::load(path.clone()).unwrap();

        // Source code has no dedup on name; each add creates a new entry
        vault.add(make_input("settings_api_key", "llm", "key-a")).unwrap();
        vault.add(make_input("settings_api_key", "llm", "key-b")).unwrap();
        assert_eq!(vault.list().len(), 2, "no name dedup — both entries exist");

        // list returns both; user would see duplicates
        let entries = vault.list();
        let names: Vec<&str> = entries.iter().map(|e| e.name.as_str()).collect();
        assert_eq!(names, vec!["settings_api_key", "settings_api_key"]);
    }

    #[test]
    fn settings_api_key_update_overwrites_value() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let e = vault.add(make_input("settings_api_key", "llm", "first")).unwrap();
        vault.update(e.id, make_input("settings_api_key", "llm", "second")).unwrap();
        assert_eq!(vault.get_value(e.id).unwrap(), "second");
    }

    // ── 8. 损坏 JSON load 容错 ────────────────────────────────────────

    #[test]
    fn load_corrupt_json_returns_load_failed() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("corrupt.json");
        fs::write(&path, "not valid json {{{").unwrap();
        let err = KeyVault::load(path.clone()).unwrap_err();
        let vault = err.into_locked_vault();
        assert!(vault.status().load_failed);
        assert!(!vault.status().unlocked);
    }

    #[test]
    fn load_unsupported_version_returns_error() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("old.json");
        fs::write(&path, r#"{"version":1,"entries":[]}"#).unwrap();
        let err = KeyVault::load(path).unwrap_err();
        let vault = err.into_locked_vault();
        assert!(vault.status().load_failed);
    }

    #[test]
    fn load_v3_missing_kdf_or_verifier_errors() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("bad3.json");
        fs::write(&path, r#"{"version":3,"kdf":null,"verifier":"","entries":[]}"#).unwrap();
        let vault = KeyVault::load(path).unwrap_err().into_locked_vault();
        assert!(vault.status().load_failed);
    }

    #[test]
    fn load_v3_unsupported_kdf_errors() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("badkdf.json");
        fs::write(&path, r#"{"version":3,"kdf":{"name":"argon2","salt":"x","n":1,"r":1,"p":1},"verifier":"v","entries":[]}"#).unwrap();
        let vault = KeyVault::load(path).unwrap_err().into_locked_vault();
        assert!(vault.status().load_failed);
    }

    #[test]
    fn load_corrupt_json_file_not_overwritten() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("keep.json");
        let original = r#"{"broken": true"#;
        fs::write(&path, original).unwrap();
        let _ = KeyVault::load(path.clone());
        assert_eq!(fs::read_to_string(&path).unwrap(), original);
    }

    // ── 额外覆盖：save_failure_for_test 回滚 ──────────────────────────

    #[test]
    fn save_failure_reverts_memory_state() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let e = vault.add(make_input("keep", "llm", "original")).unwrap();
        vault.set_save_failure_for_test(true);

        // update should fail, memory reverts
        let err = vault.update(e.id, make_input("changed", "llm", "new-val"));
        assert!(err.is_err());
        assert_eq!(vault.list()[0].name, "keep");
        assert_eq!(vault.get_value(e.id).unwrap(), "original");
    }

    #[test]
    fn add_failure_reverts_memory() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        vault.add(make_input("existing", "llm", "v")).unwrap();
        vault.set_save_failure_for_test(true);

        let _ = vault.add(make_input("new", "llm", "w"));
        assert_eq!(vault.list().len(), 1);
        assert_eq!(vault.list()[0].name, "existing");
    }

    // ── status / has_master / path ────────────────────────────────────

    #[test]
    fn status_reflects_lifecycle() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("t.json");
        let vault = KeyVault::load(path.clone()).unwrap();
        let s = vault.status();
        assert!(s.unlocked);
        assert!(!s.has_master);
        assert!(!s.load_failed);

        let mut vault = vault;
        vault.set_master("pw").unwrap();
        let s = vault.status();
        assert!(s.unlocked);
        assert!(s.has_master);

        vault.lock();
        let s = vault.status();
        assert!(!s.unlocked);
        assert!(s.has_master);
    }

    #[test]
    fn path_returns_correct_path() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("x.json");
        let vault = KeyVault::load(path.clone()).unwrap();
        assert_eq!(vault.path(), path.as_path());
    }

    // ── unlock on load_failed vault errors ────────────────────────────

    #[test]
    fn unlock_on_load_failed_vault_errors() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("bad.json");
        fs::write(&path, "{bad").unwrap();
        let mut vault = KeyVault::load(path).unwrap_err().into_locked_vault();
        let err = vault.unlock("anything");
        assert!(err.is_err());
        assert!(format!("{}", err.unwrap_err()).contains("load failed"));
    }

    // ── remove_master then set_master again ───────────────────────────

    #[test]
    fn remove_master_then_set_again_works() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("t.json");
        let mut vault = KeyVault::load(path.clone()).unwrap();
        let id = vault.add(make_input("k", "llm", "v")).unwrap().id;

        vault.set_master("pw1").unwrap();
        vault.remove_master().unwrap();
        assert!(!vault.has_master());
        assert_eq!(vault.get_value(id).unwrap(), "v");

        vault.set_master("pw2").unwrap();
        vault.lock();
        assert!(vault.unlock("pw2").unwrap());
        assert_eq!(vault.get_value(id).unwrap(), "v");
    }

    // ── KeyEntry serialization does not leak value ────────────────────

    #[test]
    fn key_entry_serialize_no_value_field() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        let entry = vault.add(make_input("k", "llm", "secret-xyz")).unwrap();
        let json = serde_json::to_string(&entry).unwrap();
        assert!(!json.contains("secret-xyz"));
        assert!(!json.contains("value"));
        assert!(!json.contains("enc_value"));
    }

    // ── Debug does not leak secrets ───────────────────────────────────

    #[test]
    fn debug_output_redacts_value() {
        let dir = tempdir().unwrap();
        let mut vault = KeyVault::load(dir.path().join("t.json")).unwrap();
        vault.add(make_input("k", "llm", "topsecret")).unwrap();
        let debug = format!("{vault:?}");
        assert!(!debug.contains("topsecret"));
    }

    // ── Reorder persistence across lock/unlock cycle ──────────────────

    #[test]
    fn reorder_survives_lock_unlock_cycle() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("t.json");
        let mut vault = KeyVault::load(path.clone()).unwrap();
        let a = vault.add(make_input("a", "llm", "1")).unwrap();
        let b = vault.add(make_input("b", "llm", "2")).unwrap();
        vault.set_master("pw").unwrap();
        vault.reorder("llm", &[b.id, a.id]).unwrap();
        vault.lock();
        vault.unlock("pw").unwrap();
        let ids: Vec<u64> = vault.list().iter().filter(|e| e.entry_type == "llm").map(|e| e.id).collect();
        assert_eq!(ids, vec![b.id, a.id]);
    }
}
