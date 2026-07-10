"""密钥管理器 — 加密存储账号密码/API密钥"""

import json
import os
import logging
import hashlib
import base64
import time
import uuid
import tempfile
import copy
from datetime import datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..core.utils import get_config_dir

logger = logging.getLogger(__name__)


def _get_keys_file():
    return os.path.join(get_config_dir(), "keys.json")


def _derive_key(master_password: str) -> bytes:
    """从主密码派生 32 字节密钥"""
    return hashlib.sha256(master_password.encode("utf-8")).digest()


def _encrypt(plaintext: str, key: bytes) -> str:
    """AES-256-GCM 加密；v2 前缀用于兼容旧 XOR 密文。"""
    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return "v2:" + base64.b64encode(nonce + encrypted).decode("ascii")


def _decrypt(ciphertext: str, key: bytes) -> str:
    """解密 v2 AES-GCM 密文；无版本前缀时走旧 XOR 兼容路径。"""
    try:
        if ciphertext.startswith("v2:"):
            data = base64.b64decode(ciphertext[3:])
            nonce, encrypted = data[:12], data[12:]
            return AESGCM(key).decrypt(nonce, encrypted, None).decode("utf-8")
        data = base64.b64decode(ciphertext)
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data)).decode("utf-8")
    except Exception:
        return ""


def _decrypt_strict(ciphertext: str, key: bytes) -> str:
    """解密失败必须上抛，避免损坏密文被保存为空值。"""
    if ciphertext.startswith("v2:"):
        data = base64.b64decode(ciphertext[3:], validate=True)
        if len(data) <= 12:
            raise ValueError("密文不完整")
        return AESGCM(key).decrypt(data[:12], data[12:], None).decode("utf-8")
    data = base64.b64decode(ciphertext, validate=True)
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data)).decode("utf-8")


def _derive_scrypt_key(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)


class KeyManager:
    """密钥管理核心

    两种模式：
    - 有主密码 → 加密存储，需解锁后才能读取明文
    - 无主密码 → 明文存储，启动即可用
    """

    def __init__(self):
        self._entries: list[dict] = []
        self._master_hash: str = ""
        self._key: bytes = b""
        self._unlocked = False
        self._version = 3
        self._kdf: dict = {}
        self._verifier = ""
        self._load_failed = False
        # 启动时自动加载：无密码则直接可用，有密码则需 unlock()
        self._load_raw()
        if not self.has_master() and not self._load_failed:
            # 无主密码 → 明文模式，直接标记解锁
            self._unlocked = True

    def has_master(self) -> bool:
        """是否已设置主密码"""
        return bool(self._master_hash or self._verifier)

    def set_master(self, password: str):
        """设置主密码并加密存储"""
        if self._load_failed or not self._unlocked:
            return False
        previous_state = (
            copy.deepcopy(self._entries), self._master_hash, self._key, self._unlocked,
            self._version, copy.deepcopy(self._kdf), self._verifier,
        )
        salt = os.urandom(16)
        self._version = 3
        self._kdf = {"name": "scrypt", "salt": base64.b64encode(salt).decode("ascii"), "n": 2**14, "r": 8, "p": 1}
        self._master_hash = ""
        self._key = _derive_scrypt_key(password, salt)
        self._verifier = _encrypt("MemoPaws key verifier", self._key)
        self._unlocked = True
        if self._save():
            return True
        (
            self._entries, self._master_hash, self._key, self._unlocked,
            self._version, self._kdf, self._verifier,
        ) = previous_state
        return False

    def remove_master(self):
        """移除主密码，将所有条目解密后明文存储"""
        previous_state = (
            copy.deepcopy(self._entries), self._master_hash, self._key, self._unlocked,
            self._version, copy.deepcopy(self._kdf), self._verifier,
        )
        if self.has_master() and self._unlocked:
            # 解密所有条目到明文
            self._decrypt_all()
        self._master_hash = ""
        self._verifier = ""
        self._kdf = {}
        self._key = b""
        self._unlocked = True
        # 明文保存
        if self._save():
            return True
        (
            self._entries, self._master_hash, self._key, self._unlocked,
            self._version, self._kdf, self._verifier,
        ) = previous_state
        return False

    def unlock(self, password: str) -> bool:
        """验证主密码并解锁"""
        if self._load_failed or not self.has_master():
            return False
        try:
            if self._version == 3:
                salt = base64.b64decode(self._kdf["salt"], validate=True)
                key = _derive_scrypt_key(password, salt)
                if _decrypt_strict(self._verifier, key) != "MemoPaws key verifier":
                    return False
            else:
                if hashlib.sha256(password.encode("utf-8")).hexdigest() != self._master_hash:
                    return False
                key = _derive_key(password)
            entries = self._decrypt_entries(key)
        except Exception as exc:
            logger.warning("密钥库解锁失败，原文件未改动: %s", exc)
            return False
        previous_state = (
            self._key, self._entries, self._unlocked, self._version,
            self._kdf, self._master_hash, self._verifier,
        )
        self._key, self._entries, self._unlocked = key, entries, True
        if self._version == 2:
            salt = os.urandom(16)
            self._version = 3
            self._kdf = {"name": "scrypt", "salt": base64.b64encode(salt).decode("ascii"), "n": 2**14, "r": 8, "p": 1}
            self._key = _derive_scrypt_key(password, salt)
            self._master_hash = ""
            self._verifier = _encrypt("MemoPaws key verifier", self._key)
            if not self._save():
                (
                    self._key, self._entries, self._unlocked, self._version,
                    self._kdf, self._master_hash, self._verifier,
                ) = previous_state
                return False
        return True

    def lock(self):
        """锁定（仅在有主密码时有效）"""
        if not self.has_master():
            return
        self._unlocked = False
        self._key = b""
        self._entries = []

    def is_unlocked(self) -> bool:
        return self._unlocked

    def get_entries(self) -> list[dict]:
        if not self._unlocked:
            return []
        return self._entries

    def add_entry(self, name: str, entry_type: str, value: str,
                  url: str = "", url_anthropic: str = "", note: str = ""):
        """添加条目。entry_type: 'llm' | 'secret'"""
        if not self._unlocked:
            return False
        previous_entries = copy.deepcopy(self._entries)
        next_order = max((e.get("order", 0) for e in self._entries if e.get("type") == entry_type), default=-1) + 1
        entry = {
            "id": uuid.uuid4().int & ((1 << 53) - 1),
            "name": name,
            "type": entry_type,
            "value": value,
            "url": url,
            "url_anthropic": url_anthropic,
            "note": note,
            "order": next_order,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._entries.append(entry)
        if self._save():
            return True
        self._entries = previous_entries
        return False

    def update_entry(self, entry_id: int, **kwargs):
        if not self._unlocked:
            return False
        for e in self._entries:
            if e["id"] == entry_id:
                previous_entries = copy.deepcopy(self._entries)
                e.update(kwargs)
                if self._save():
                    return True
                self._entries = previous_entries
                return False
        return False

    def delete_entry(self, entry_id: int):
        if not self._unlocked:
            return False
        previous_entries = copy.deepcopy(self._entries)
        self._entries = [e for e in self._entries if e["id"] != entry_id]
        if len(self._entries) == len(previous_entries):
            return False
        if self._save():
            return True
        self._entries = previous_entries
        return False

    def get_plain_value(self, entry_id: int) -> str:
        """获取明文值（解锁状态下可用）"""
        if not self._unlocked:
            return ""
        for e in self._entries:
            if e["id"] == entry_id:
                return e.get("value", "")
        return ""

    # ── 持久化 ──

    def _load_raw(self):
        """加载原始数据"""
        if not os.path.exists(_get_keys_file()):
            self._entries = []
            self._master_hash = ""
            return
        try:
            with open(_get_keys_file(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or not isinstance(data.get("entries", []), list):
                raise ValueError("密钥库格式无效")
            self._version = data.get("version", 2)
            if self._version not in (2, 3):
                raise ValueError("不支持的密钥库版本")
            self._master_hash = data.get("master_hash", "")
            self._kdf = data.get("kdf", {})
            self._verifier = data.get("verifier", "")
            if self._version == 3 and (not isinstance(self._kdf, dict) or not self._verifier):
                raise ValueError("密钥库验证信息缺失")
            raw_entries = data.get("entries", [])
            # 无主密码时，entries 直接含 value 明文
            if not self.has_master():
                self._entries = []
                for idx, e in enumerate(raw_entries):
                    entry = dict(e)
                    # 兼容旧数据：有 enc_value 但无 value 时解密（理论上无密码不会有）
                    if "value" not in entry and "enc_value" in entry:
                        entry["value"] = entry.get("enc_value", "")
                    entry.setdefault("order", idx)
                    self._entries.append(entry)
            else:
                self._entries = []
                for idx, entry in enumerate(raw_entries):
                    normalized = dict(entry)
                    normalized.setdefault("order", idx)
                    self._entries.append(normalized)
        except Exception as exc:
            logger.error("加载密钥库失败，已保持锁定: %s", exc)
            self._entries = []
            self._master_hash = ""
            self._verifier = ""
            self._load_failed = True

    def _decrypt_all(self):
        """解锁后解密所有条目的 value"""
        for e in self._entries:
            enc = e.get("enc_value", "")
            if enc:
                e["value"] = _decrypt(enc, self._key)

    def _decrypt_entries(self, key: bytes) -> list[dict]:
        entries = []
        for entry in self._entries:
            decrypted = dict(entry)
            enc = decrypted.get("enc_value", "")
            if enc:
                decrypted["value"] = _decrypt_strict(enc, key)
            elif "value" not in decrypted:
                raise ValueError("条目缺少密文")
            entries.append(decrypted)
        return entries

    def _save(self):
        """保存到文件"""
        if self._load_failed or (self.has_master() and not self._unlocked):
            return False
        temp_path = None
        try:
            os.makedirs(os.path.dirname(_get_keys_file()), exist_ok=True)
            save_entries = []
            for e in self._entries:
                se = dict(e)
                if self.has_master() and self._key:
                    # 有主密码 → 加密存储
                    se["enc_value"] = _encrypt(e["value"], self._key)
                    se.pop("value", None)
                else:
                    # 无主密码 → 明文存储
                    se.pop("enc_value", None)
                save_entries.append(se)
            data = {
                "version": self._version if self.has_master() else 2,
                "master_hash": self._master_hash,
                "entries": save_entries,
            }
            if self._verifier:
                data["kdf"] = self._kdf
                data["verifier"] = self._verifier
            fd, temp_path = tempfile.mkstemp(prefix="keys.", suffix=".tmp", dir=os.path.dirname(_get_keys_file()))
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, _get_keys_file())
            return True
        except Exception as e:
            logger.error("保存密钥失败: %s", e)
            try:
                if temp_path:
                    os.unlink(temp_path)
            except OSError:
                pass
            return False
