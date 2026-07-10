import json
import os
import base64
import shutil
import tempfile

import pytest

from memopaws.keys.key_manager import _derive_key, _encrypt, _decrypt, KeyManager


class TestCrypto:
    def test_derive_key_consistency(self):
        k1 = _derive_key("hello123")
        k2 = _derive_key("hello123")
        assert k1 == k2
        assert len(k1) == 32

    def test_derive_key_different(self):
        k1 = _derive_key("password1")
        k2 = _derive_key("password2")
        assert k1 != k2

    def test_encrypt_decrypt_roundtrip(self):
        key = _derive_key("test_master")
        plain = "sk-abc123xyz"
        encrypted = _encrypt(plain, key)
        assert encrypted != plain
        assert encrypted.startswith("v2:")
        decrypted = _decrypt(encrypted, key)
        assert decrypted == plain

    def test_decrypt_legacy_xor_ciphertext(self):
        key = _derive_key("legacy_master")
        plain = "legacy-secret"
        encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(plain.encode("utf-8")))
        legacy_ciphertext = base64.b64encode(encrypted).decode("ascii")

        assert _decrypt(legacy_ciphertext, key) == plain

    def test_encrypt_empty_string(self):
        key = _derive_key("test")
        result = _encrypt("", key)
        assert result.startswith("v2:")
        assert _decrypt(result, key) == ""

    def test_decrypt_wrong_key(self):
        key1 = _derive_key("key1")
        key2 = _derive_key("key2")
        encrypted = _encrypt("secret", key1)
        decrypted = _decrypt(encrypted, key2)
        assert decrypted != "secret"

    def test_decrypt_invalid_base64(self):
        key = _derive_key("test")
        assert _decrypt("!!!invalid!!!", key) == ""


# ── KeyManager 测试用独立临时目录 ──

@pytest.fixture(autouse=True)
def _km_tmpdir(monkeypatch):
    """每个测试函数重定向 key_manager._get_keys_file"""
    tmp_dir = tempfile.mkdtemp()
    keys_file = os.path.join(tmp_dir, "keys.json")
    monkeypatch.setattr("memopaws.keys.key_manager._get_keys_file", lambda: keys_file)
    yield
    shutil.rmtree(tmp_dir, ignore_errors=True)


class TestKeyManager:
    def test_init_no_master(self):
        km = KeyManager()
        assert km.has_master() is False
        assert km.is_unlocked() is True

    def test_set_master_and_lock_unlock(self):
        km = KeyManager()
        km.set_master("mypassword")
        assert km.has_master() is True
        assert km.is_unlocked() is True

        km.lock()
        assert km.is_unlocked() is False

        ok = km.unlock("wrong")
        assert ok is False
        assert km.is_unlocked() is False

        ok = km.unlock("mypassword")
        assert ok is True
        assert km.is_unlocked() is True

    def test_add_entry(self):
        km = KeyManager()
        km.add_entry("test_key", "llm", "sk-xxx", url="https://api.test.com")
        entries = km.get_entries()
        assert len(entries) == 1
        assert entries[0]["name"] == "test_key"
        assert entries[0]["type"] == "llm"
        assert entries[0]["value"] == "sk-xxx"
        assert entries[0]["url"] == "https://api.test.com"
        assert entries[0]["order"] == 0

    def test_entry_order_is_scoped_per_type(self):
        km = KeyManager()
        km.add_entry("llm1", "llm", "a")
        km.add_entry("secret1", "secret", "b")
        km.add_entry("llm2", "llm", "c")

        entries = km.get_entries()
        llm_orders = [e["order"] for e in entries if e["type"] == "llm"]
        secret_orders = [e["order"] for e in entries if e["type"] == "secret"]

        assert llm_orders == [0, 1]
        assert secret_orders == [0]

    def test_add_entry_locked(self):
        km = KeyManager()
        km.set_master("pwd")
        km.lock()
        km.add_entry("test", "secret", "value")
        assert len(km.get_entries()) == 0

    def test_update_entry(self):
        km = KeyManager()
        km.add_entry("old_name", "secret", "old_value")
        eid = km.get_entries()[0]["id"]
        km.update_entry(eid, name="new_name", value="new_value")
        assert km.get_entries()[0]["name"] == "new_name"
        assert km.get_entries()[0]["value"] == "new_value"

    def test_delete_entry_vanilla(self):
        """完全绕开 KeyManager，纯 Python 列表操作验证删除逻辑"""
        entries = [
            {"id": 1, "name": "e1"}, {"id": 2, "name": "e2"},
        ]
        eid = entries[0]["id"]
        remaining = [e for e in entries if e["id"] != eid]
        assert len(remaining) == 1
        assert remaining[0]["name"] == "e2"

    def test_delete_entry(self):
        km = KeyManager()
        km.add_entry("e1", "secret", "v1")
        km.add_entry("e2", "secret", "v2")
        eid = km.get_entries()[0]["id"]
        km.delete_entry(eid)
        entries = km.get_entries()
        assert len(entries) == 1
        assert entries[0]["name"] == "e2"

    def test_get_plain_value(self):
        km = KeyManager()
        km.add_entry("k", "secret", "plain_value")
        eid = km.get_entries()[0]["id"]
        assert km.get_plain_value(eid) == "plain_value"
        assert km.get_plain_value(99999) == ""

    def test_persistence(self):
        km = KeyManager()
        km.add_entry("persistent_key", "llm", "persistent_value")
        del km
        km2 = KeyManager()
        entries = km2.get_entries()
        assert len(entries) == 1
        assert entries[0]["value"] == "persistent_value"

    def test_master_persistence_encrypted(self):
        km = KeyManager()
        km.set_master("mypass")
        km.add_entry("secret", "secret", "sensitive_value")
        eid = km.get_entries()[0]["id"]
        assert km.get_plain_value(eid) == "sensitive_value"
        km.lock()
        del km
        km2 = KeyManager()
        ok = km2.unlock("mypass")
        assert ok is True
        entries = km2.get_entries()
        assert len(entries) == 1
        assert entries[0]["value"] == "sensitive_value"

    def test_remove_master(self):
        km = KeyManager()
        km.set_master("pwd")
        km.add_entry("test", "secret", "plaintext_value")
        km.remove_master()
        assert km.has_master() is False
        assert km.is_unlocked() is True
        entries = km.get_entries()
        assert len(entries) == 1
        assert entries[0]["value"] == "plaintext_value"

    def test_encrypted_file_has_no_plaintext_value(self):
        km = KeyManager()
        km.set_master("pwd")
        km.add_entry("safe", "secret", "hidden_value")
        km.lock()
        from memopaws.keys.key_manager import _get_keys_file
        with open(_get_keys_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == 3
        assert data["kdf"]["salt"]
        assert data["verifier"].startswith("v2:")
        for e in data["entries"]:
            assert "value" not in e
            assert "enc_value" in e
            assert e["enc_value"].startswith("v2:")

    def test_failed_unlock_of_tampered_entry_preserves_source_file(self):
        km = KeyManager()
        km.set_master("pwd")
        km.add_entry("safe", "secret", "hidden_value")
        from memopaws.keys.key_manager import _get_keys_file
        with open(_get_keys_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        data["entries"][0]["enc_value"] = "v2:not-valid"
        with open(_get_keys_file(), "w", encoding="utf-8") as f:
            json.dump(data, f)
        original = open(_get_keys_file(), "rb").read()

        reloaded = KeyManager()

        assert reloaded.unlock("pwd") is False
        assert reloaded.is_unlocked() is False
        assert open(_get_keys_file(), "rb").read() == original

    def test_corrupted_json_is_not_treated_as_empty_writable_library(self):
        from memopaws.keys.key_manager import _get_keys_file
        with open(_get_keys_file(), "w", encoding="utf-8") as f:
            f.write("{")
        original = open(_get_keys_file(), "rb").read()
        km = KeyManager()

        assert km.is_unlocked() is False
        km.add_entry("new", "secret", "value")
        assert open(_get_keys_file(), "rb").read() == original

    def test_unlocking_v2_migrates_without_losing_data(self):
        key = _derive_key("legacy")
        from memopaws.keys.key_manager import _get_keys_file
        legacy = {
            "version": 2,
            "master_hash": __import__("hashlib").sha256(b"legacy").hexdigest(),
            "entries": [{"id": 1, "name": "old", "type": "secret", "enc_value": _encrypt("value", key)}],
        }
        with open(_get_keys_file(), "w", encoding="utf-8") as f:
            json.dump(legacy, f)

        km = KeyManager()

        assert km.unlock("legacy") is True
        assert km.get_plain_value(1) == "value"
        with open(_get_keys_file(), encoding="utf-8") as f:
            assert json.load(f)["version"] == 3

    def test_unlocking_v2_returns_false_and_restores_memory_when_migration_save_fails(self, monkeypatch):
        key = _derive_key("legacy")
        from memopaws.keys.key_manager import _get_keys_file
        legacy = {
            "version": 2,
            "master_hash": __import__("hashlib").sha256(b"legacy").hexdigest(),
            "entries": [{"id": 1, "name": "old", "type": "secret", "enc_value": _encrypt("value", key)}],
        }
        with open(_get_keys_file(), "w", encoding="utf-8") as f:
            json.dump(legacy, f)
        original = open(_get_keys_file(), "rb").read()
        km = KeyManager()
        monkeypatch.setattr(km, "_save", lambda: False)

        assert km.unlock("legacy") is False
        assert km.is_unlocked() is False
        assert km._version == 2
        assert km._master_hash == legacy["master_hash"]
        assert km._verifier == ""
        assert km._key == b""
        assert km._entries[0]["enc_value"] == legacy["entries"][0]["enc_value"]
        assert open(_get_keys_file(), "rb").read() == original

    def test_save_returns_false_when_config_directory_cannot_be_created(self, monkeypatch):
        km = KeyManager()
        monkeypatch.setattr("memopaws.keys.key_manager.os.makedirs", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("denied")))

        assert km._save() is False

    def test_set_master_restores_memory_when_save_fails(self, monkeypatch):
        km = KeyManager()
        previous_state = (km._entries, km._master_hash, km._key, km._unlocked, km._version, km._kdf, km._verifier)
        monkeypatch.setattr(km, "_save", lambda: False)

        assert km.set_master("pwd") is False
        assert (km._entries, km._master_hash, km._key, km._unlocked, km._version, km._kdf, km._verifier) == previous_state

    def test_remove_master_restores_entries_and_state_when_save_fails(self, monkeypatch):
        km = KeyManager()
        km.set_master("pwd")
        km.add_entry("secret", "secret", "value")
        previous_state = (km._master_hash, km._key, km._unlocked, km._version, dict(km._kdf), km._verifier)
        previous_entry = dict(km._entries[0])
        monkeypatch.setattr(km, "_save", lambda: False)

        assert km.remove_master() is False
        assert (km._master_hash, km._key, km._unlocked, km._version, km._kdf, km._verifier) == previous_state
        assert km._entries == [previous_entry]

    @pytest.mark.parametrize("operation", ["add", "update", "delete"])
    def test_entry_mutation_returns_false_and_restores_entries_when_save_fails(self, monkeypatch, operation):
        km = KeyManager()
        assert km.add_entry("old", "secret", "value") is True
        entry_id = km.get_entries()[0]["id"]
        before = [dict(entry) for entry in km.get_entries()]
        monkeypatch.setattr(km, "_save", lambda: False)

        if operation == "add":
            result = km.add_entry("new", "secret", "new-value")
        elif operation == "update":
            result = km.update_entry(entry_id, name="new")
        else:
            result = km.delete_entry(entry_id)

        assert result is False
        assert km.get_entries() == before

    def test_encrypted_empty_value_is_saved_as_ciphertext_and_unlocks_after_restart(self):
        km = KeyManager()
        assert km.set_master("pwd") is True
        assert km.add_entry("empty", "secret", "") is True
        from memopaws.keys.key_manager import _get_keys_file
        with open(_get_keys_file(), encoding="utf-8") as f:
            saved_entry = json.load(f)["entries"][0]
        assert "value" not in saved_entry
        assert saved_entry["enc_value"].startswith("v2:")

        reloaded = KeyManager()
        assert reloaded.unlock("pwd") is True
        assert reloaded.get_plain_value(saved_entry["id"]) == ""
