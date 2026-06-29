import json
import os
import shutil
import tempfile

import pytest

from snaptrans.key_manager import _derive_key, _encrypt, _decrypt, KeyManager


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
        decrypted = _decrypt(encrypted, key)
        assert decrypted == plain

    def test_encrypt_empty_string(self):
        key = _derive_key("test")
        result = _encrypt("", key)
        assert result == ""
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


# ── 工具：在独立临时目录中创建 KeyManager ──

@pytest.fixture
def km():
    tmp_dir = tempfile.mkdtemp()
    keys_file = os.path.join(tmp_dir, "keys.json")

    original_get_keys_file = "snaptrans.key_manager._get_keys_file"
    import snaptrans.key_manager as km_mod
    original = km_mod._get_keys_file
    km_mod._get_keys_file = lambda: keys_file

    instance = KeyManager()
    instance._keys_file = keys_file
    yield instance

    km_mod._get_keys_file = original
    shutil.rmtree(tmp_dir, ignore_errors=True)


class TestKeyManager:
    def test_init_no_master(self, km):
        assert km.has_master() is False
        assert km.is_unlocked() is True

    def test_set_master_and_lock_unlock(self, km):
        assert km.has_master() is False
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

    def test_add_entry(self, km):
        km.add_entry("test_key", "llm", "sk-xxx", url="https://api.test.com")
        entries = km.get_entries()
        assert len(entries) == 1
        assert entries[0]["name"] == "test_key"
        assert entries[0]["type"] == "llm"
        assert entries[0]["value"] == "sk-xxx"
        assert entries[0]["url"] == "https://api.test.com"

    def test_add_entry_locked(self, km):
        km.set_master("pwd")
        km.lock()
        km.add_entry("test", "secret", "value")
        assert len(km.get_entries()) == 0

    def test_update_entry(self, km):
        km.add_entry("old_name", "secret", "old_value")
        eid = km.get_entries()[0]["id"]
        km.update_entry(eid, name="new_name", value="new_value")
        assert km.get_entries()[0]["name"] == "new_name"
        assert km.get_entries()[0]["value"] == "new_value"

    def test_delete_entry(self, km):
        km.add_entry("e1", "secret", "v1")
        km.add_entry("e2", "secret", "v2")
        eid = km.get_entries()[0]["id"]
        km.delete_entry(eid)
        assert len(km.get_entries()) == 1
        assert km.get_entries()[0]["name"] == "e2"

    def test_get_plain_value(self, km):
        km.add_entry("k", "secret", "plain_value")
        eid = km.get_entries()[0]["id"]
        assert km.get_plain_value(eid) == "plain_value"
        assert km.get_plain_value(99999) == ""

    def test_persistence(self, km):
        km.add_entry("persistent_key", "llm", "persistent_value")
        entries = km.get_entries()
        assert len(entries) == 1
        assert entries[0]["value"] == "persistent_value"

    def test_master_persistence_encrypted(self, km):
        km.set_master("mypass")
        km.add_entry("secret", "secret", "sensitive_value")
        eid = km.get_entries()[0]["id"]
        assert km.get_plain_value(eid) == "sensitive_value"
        km.lock()

    def test_remove_master(self, km):
        km.set_master("pwd")
        km.add_entry("test", "secret", "plaintext_value")
        km.remove_master()
        assert km.has_master() is False
        assert km.is_unlocked() is True
        entries = km.get_entries()
        assert len(entries) == 1
        assert entries[0]["value"] == "plaintext_value"

    def test_encrypted_file_has_no_plaintext_value(self, km):
        km.set_master("pwd")
        km.add_entry("safe", "secret", "hidden_value")
        km.lock()
        with open(km._keys_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for e in data["entries"]:
            assert "value" not in e
            assert "enc_value" in e
