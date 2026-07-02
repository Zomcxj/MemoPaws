import json
import os
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
        for e in data["entries"]:
            assert "value" not in e
            assert "enc_value" in e
