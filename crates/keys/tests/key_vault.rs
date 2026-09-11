use std::fs;

use aes_gcm::{aead::{Aead, KeyInit}, Aes256Gcm, Nonce};
use base64::{engine::general_purpose::STANDARD, Engine};
use memopaws_keys::{KeyEntryInput, KeyVault};
use scrypt::{scrypt, Params};
use sha2::{Digest, Sha256};
use tempfile::tempdir;

fn encrypted(key: &[u8; 32], plaintext: &str) -> String {
    let nonce = [7_u8; 12];
    let cipher = Aes256Gcm::new_from_slice(key).unwrap();
    let mut bytes = nonce.to_vec();
    bytes.extend(cipher.encrypt(Nonce::from_slice(&nonce), plaintext.as_bytes()).unwrap());
    format!("v2:{}", STANDARD.encode(bytes))
}

fn input(name: &str, kind: &str, value: &str) -> KeyEntryInput {
    KeyEntryInput { name: name.into(), entry_type: kind.into(), value: value.into(), url: String::new(), url_anthropic: String::new(), note: String::new() }
}

#[test]
fn unlocks_python_v2_aes_and_legacy_xor() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let key: [u8; 32] = Sha256::digest(b"correct").into();
    let xor: Vec<u8> = b"legacy".iter().enumerate().map(|(i, b)| b ^ key[i % key.len()]).collect();
    fs::write(&path, serde_json::json!({
        "version": 2, "master_hash": hex::encode(key),
        "entries": [
            {"id": 1, "name": "aes", "type": "secret", "enc_value": encrypted(&key, "modern")},
            {"id": 2, "name": "xor", "type": "secret", "enc_value": STANDARD.encode(xor)}
        ]
    }).to_string()).unwrap();

    let mut vault = KeyVault::load(path).unwrap();
    assert!(!vault.unlock("wrong").unwrap());
    assert!(vault.unlock("correct").unwrap());
    assert_eq!(vault.get_value(1).unwrap(), "modern");
    assert_eq!(vault.get_value(2).unwrap(), "legacy");
    assert_eq!(serde_json::from_str::<serde_json::Value>(&fs::read_to_string(vault.path()).unwrap()).unwrap()["version"], 3);
}

#[test]
fn unlocks_v3_using_dynamic_scrypt_parameters() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let salt = b"dynamic-test-salt";
    let params = Params::new(10, 4, 2, 32).unwrap();
    let mut key = [0_u8; 32];
    scrypt(b"password", salt, &params, &mut key).unwrap();
    fs::write(&path, serde_json::json!({
        "version": 3,
        "master_hash": "",
        "kdf": {"name":"scrypt", "salt":STANDARD.encode(salt), "n":1024, "r":4, "p":2},
        "verifier": encrypted(&key, "MemoPaws key verifier"),
        "entries": [{"id":3,"name":"dynamic","type":"llm","enc_value":encrypted(&key, "token") }]
    }).to_string()).unwrap();
    let mut vault = KeyVault::load(path).unwrap();
    assert!(vault.unlock("password").unwrap());
    assert_eq!(vault.get_value(3).unwrap(), "token");
}

#[test]
fn corrupt_ciphertext_never_unlocks_or_overwrites_file() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let key: [u8; 32] = Sha256::digest(b"password").into();
    let original = serde_json::json!({"version":2,"master_hash":hex::encode(key),"entries":[{"id":1,"name":"bad","type":"secret","enc_value":"v2:not-base64"}]}).to_string();
    fs::write(&path, &original).unwrap();
    let mut vault = KeyVault::load(path.clone()).unwrap();
    assert!(vault.unlock("password").is_err());
    assert!(!vault.status().unlocked);
    assert_eq!(fs::read_to_string(path).unwrap(), original);
}

#[test]
fn lock_crud_reorder_and_safe_serialization() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let mut vault = KeyVault::load(path.clone()).unwrap();
    let first = vault.add(input("first", "secret", "one")).unwrap();
    let second = vault.add(input("second", "secret", "two")).unwrap();
    let llm = vault.add(input("model", "llm", "three")).unwrap();
    vault.reorder("secret", &[second.id, first.id]).unwrap();
    assert_eq!(vault.list().iter().filter(|e| e.entry_type == "secret").map(|e| e.id).collect::<Vec<_>>(), vec![second.id, first.id]);
    vault.update(first.id, input("updated", "secret", "changed")).unwrap();
    vault.delete(llm.id).unwrap();
    let listed = serde_json::to_string(&vault.list()).unwrap();
    assert!(!listed.contains("changed") && !listed.contains("enc_value") && !listed.contains("value"));
    vault.set_master("master").unwrap();
    let disk = fs::read_to_string(&path).unwrap();
    assert!(!disk.contains("changed") && disk.contains("enc_value"));
    vault.lock();
    assert!(vault.list().is_empty());
    assert!(vault.get_value(first.id).is_err());
    assert!(vault.unlock("master").unwrap());
    assert_eq!(vault.get_value(first.id).unwrap(), "changed");
    vault.remove_master().unwrap();
    assert!(!vault.status().has_master && vault.status().unlocked);
}

#[test]
fn reorder_persists_explicit_zero_per_group_after_reload() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let mut vault = KeyVault::load(path.clone()).unwrap();
    let secret_first = vault.add(input("secret-first", "secret", "one")).unwrap();
    let secret_second = vault.add(input("secret-second", "secret", "two")).unwrap();
    let llm_first = vault.add(input("llm-first", "llm", "three")).unwrap();
    let llm_second = vault.add(input("llm-second", "llm", "four")).unwrap();

    vault.reorder("secret", &[secret_second.id, secret_first.id]).unwrap();
    vault.reorder("llm", &[llm_second.id, llm_first.id]).unwrap();
    drop(vault);

    let reloaded = KeyVault::load(path).unwrap();
    let listed = reloaded.list();
    assert_eq!(
        listed.iter().filter(|entry| entry.entry_type == "secret").map(|entry| entry.id).collect::<Vec<_>>(),
        vec![secret_second.id, secret_first.id],
    );
    assert_eq!(
        listed.iter().filter(|entry| entry.entry_type == "llm").map(|entry| entry.id).collect::<Vec<_>>(),
        vec![llm_second.id, llm_first.id],
    );
}

#[test]
fn public_serialization_and_debug_output_are_redacted() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let mut vault = KeyVault::load(path).unwrap();
    let entry = vault.add(input("visible-name", "secret", "never-print-this-secret")).unwrap();

    let serialized = serde_json::to_string(&entry).unwrap();
    assert!(!serialized.contains("never-print-this-secret"));
    assert!(!serialized.contains("value") && !serialized.contains("enc_value"));
    let debugged = format!("{vault:?}");
    assert!(!debugged.contains("never-print-this-secret"));
    assert!(!debugged.contains("visible-name"));
}

#[test]
fn validation_rejects_empty_names_values_and_unknown_types() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let mut vault = KeyVault::load(path.clone()).unwrap();

    assert!(vault.add(input("", "secret", "value")).is_err());
    assert!(vault.add(input("   ", "secret", "value")).is_err());
    assert!(vault.add(input("name", "secret", "")).is_err());
    assert!(vault.add(input("name", "other", "value")).is_err());
    assert!(vault.add(input("name", "LLM", "value")).is_err());
    assert!(vault.list().is_empty());
    assert_eq!(vault.status().has_master, false);

    let created = vault.add(input("settings_api_key", "llm", "key-value")).unwrap();
    assert_eq!(vault.list().len(), 1);
    assert!(vault.update(created.id, input("", "llm", "x")).is_err());
    vault.update(created.id, input("valid", "llm", "x")).unwrap();
}

#[test]
fn locked_vault_rejects_every_write_operation() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let mut vault = KeyVault::load(path.clone()).unwrap();
    let entry = vault.add(input("only", "secret", "value")).unwrap();
    vault.set_master("master-pw").unwrap();
    vault.lock();
    assert!(!vault.status().unlocked);

    assert!(vault.add(input("nope", "secret", "x")).is_err());
    assert!(vault.update(entry.id, input("nope", "secret", "x")).is_err());
    assert!(vault.delete(entry.id).is_err());
    assert!(vault.reorder("secret", &[entry.id]).is_err());
    assert!(vault.set_master("another").is_err());
    assert!(vault.remove_master().is_err());
    assert!(vault.get_value(entry.id).is_err());
    assert!(vault.list().is_empty());

    assert!(vault.unlock("master-pw").unwrap());
    vault.lock();
    assert!(!vault.unlock("wrong-pw").unwrap_or(false));
    assert!(vault.unlock("master-pw").unwrap());
    assert!(vault.status().unlocked);
}

#[test]
fn set_master_downgrades_and_remove_master_unlocks_with_plaintext_again() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let mut vault = KeyVault::load(path.clone()).unwrap();
    let id = vault.add(input("open", "secret", "plain-value")).unwrap().id;

    vault.remove_master().unwrap();
    assert!(!vault.status().has_master && vault.status().unlocked);
    assert_eq!(vault.get_value(id).unwrap(), "plain-value");
    let disk = fs::read_to_string(&path).unwrap();
    assert!(disk.contains("plain-value") && !disk.contains("enc_value"));

    vault.set_master("master").unwrap();
    assert!(vault.status().has_master && vault.status().unlocked);
    assert_eq!(vault.get_value(id).unwrap(), "plain-value");
    let disk = fs::read_to_string(&path).unwrap();
    assert!(!disk.contains("plain-value"));
    let value: serde_json::Value = serde_json::from_str(&disk).unwrap();
    assert_eq!(value["entries"][0]["type"], "secret");
    assert!(!disk.contains("entry_type"));
}

#[test]
fn reorder_rejects_missing_extra_or_foreign_ids() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let mut vault = KeyVault::load(path.clone()).unwrap();
    let a = vault.add(input("a", "secret", "1")).unwrap();
    let b = vault.add(input("b", "secret", "2")).unwrap();
    let llm = vault.add(input("llm", "llm", "3")).unwrap();

    assert!(vault.reorder("secret", &[a.id]).is_err());
    assert!(vault.reorder("secret", &[a.id, b.id, 999_999]).is_err());
    assert!(vault.reorder("secret", &[a.id, llm.id]).is_err());
    assert!(vault.reorder("llm", &[llm.id, a.id]).is_err());
    assert!(vault.reorder("secret", &[]).is_err());

    assert_eq!(vault.list().iter().filter(|e| e.entry_type == "llm").map(|e| e.id).collect::<Vec<_>>(), vec![llm.id]);
    assert_eq!(vault.reorder("llm", &[llm.id]).unwrap(), ());
}

#[test]
fn missing_entry_operations_are_rejected_but_leave_data_intact() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let mut vault = KeyVault::load(path.clone()).unwrap();
    let entry = vault.add(input("existing", "secret", "value")).unwrap();

    assert!(vault.get_value(424_242).is_err());
    assert!(vault.update(424_242, input("nope", "secret", "x")).is_err());
    assert!(vault.delete(424_242).is_err());
    assert_eq!(vault.list().len(), 1);

    assert_eq!(vault.get_value(entry.id).unwrap(), "value");
    assert!(vault.delete(entry.id).unwrap() == ());
    assert!(vault.list().is_empty());
}

#[test]
fn encrypted_disk_entry_uses_type_field_and_hides_plaintext_after_reload() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let mut vault = KeyVault::load(path.clone()).unwrap();
    let secret = vault.add(input("api-secret", "secret", "hunter2")).unwrap();
    vault.set_master("password").unwrap();
    vault.lock();
    vault.unlock("password").unwrap();

    let raw = fs::read_to_string(&path).unwrap();
    let value: serde_json::Value = serde_json::from_str(&raw).unwrap();
    let entry = &value["entries"][0];
    assert_eq!(entry["type"], "secret");
    assert!(entry.get("entry_type").is_none());
    assert!(entry["enc_value"].is_string());
    assert!(!raw.contains("hunter2"));

    let mut reloaded = KeyVault::load(path).unwrap();
    assert!(reloaded.unlock("password").unwrap());
    assert_eq!(reloaded.get_value(secret.id).unwrap(), "hunter2");
}

#[test]
fn save_load_round_trip_without_master_keeps_plaintext_and_order() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let mut vault = KeyVault::load(path.clone()).unwrap();
    let first = vault.add(input("first", "secret", "one")).unwrap();
    let second = vault.add(input("second", "secret", "two")).unwrap();

    let reloaded = KeyVault::load(path).unwrap();
    assert!(reloaded.status().unlocked && !reloaded.status().has_master);
    assert_eq!(reloaded.list().iter().map(|e| e.id).collect::<Vec<_>>(), vec![first.id, second.id]);
    assert_eq!(reloaded.get_value(first.id).unwrap(), "one");
    assert_eq!(reloaded.get_value(second.id).unwrap(), "two");
}

#[test]
fn empty_master_password_is_rejected_and_corrupt_json_fails_load() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let mut vault = KeyVault::load(path.clone()).unwrap();
    assert!(vault.set_master("").is_err());

    let broken = dir.path().join("broken.json");
    fs::write(&broken, "{\"version\":3,\"entries\":[}").unwrap();
    let failed = KeyVault::load(broken.clone()).unwrap_err().into_locked_vault();
    assert!(failed.status().load_failed && !failed.status().unlocked);
    assert_eq!(fs::read_to_string(broken).unwrap(), "{\"version\":3,\"entries\":[}");
}

#[test]
fn failed_save_rolls_memory_back_and_load_failure_stays_locked() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("keys.json");
    let mut vault = KeyVault::load(path.clone()).unwrap();
    let first = vault.add(input("safe", "secret", "value")).unwrap();
    vault.set_save_failure_for_test(true);
    assert!(vault.update(first.id, input("lost", "secret", "replacement")).is_err());
    assert_eq!(vault.list()[0].name, "safe");
    assert_eq!(vault.get_value(first.id).unwrap(), "value");

    let broken = dir.path().join("broken.json");
    fs::write(&broken, "{broken").unwrap();
    let mut failed = KeyVault::load(broken.clone()).unwrap_err().into_locked_vault();
    assert!(!failed.status().unlocked && failed.status().load_failed);
    assert!(failed.add(input("no", "secret", "write")).is_err());
    assert_eq!(fs::read_to_string(broken).unwrap(), "{broken");
}
