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
        self.entries.push(entry);
        if let Err(error) = self.save() { self.restore(snapshot); return Err(error); }
        Ok(KeyEntry::from(self.entries.last().unwrap()))
    }

    pub fn update(&mut self, id: u64, mut input: KeyEntryInput) -> Result<KeyEntry> {
        self.require_writable()?;
        validate_input(&input)?;
        let snapshot = self.snapshot();
        let entry = self.entries.iter_mut().find(|e| e.id == id).ok_or_else(|| KeyVaultError::new("key entry not found"))?;
        entry.name = std::mem::take(&mut input.name); entry.entry_type = std::mem::take(&mut input.entry_type); entry.value = Some(Zeroizing::new(std::mem::take(&mut input.value))); entry.url = std::mem::take(&mut input.url); entry.url_anthropic = std::mem::take(&mut input.url_anthropic); entry.note = std::mem::take(&mut input.note);
        if let Err(error) = self.save() { self.restore(snapshot); return Err(error); }
        Ok(KeyEntry::from(self.entries.iter().find(|e| e.id == id).unwrap()))
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
        for (order, id) in ids.iter().enumerate() { self.entries.iter_mut().find(|entry| entry.id == *id).unwrap().order = order as i64; }
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
        for item in &mut saved { if item["value"].is_null() { item.as_object_mut().unwrap().remove("value"); } if item["enc_value"].is_null() { item.as_object_mut().unwrap().remove("enc_value"); } }
        let mut root = serde_json::json!({"version":if self.has_master() { self.version } else { 2 },"master_hash":self.master_hash,"entries":saved});
        if self.has_master() && self.version == 3 { root["kdf"] = serde_json::to_value(&self.kdf).unwrap(); root["verifier"] = serde_json::Value::String(self.verifier.clone()); }
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
