"""密钥管理器 — 加密存储账号密码/API密钥"""

import json
import os
import logging
import hashlib
import base64
import time
import uuid
from datetime import datetime

from ..core.utils import get_config_dir

logger = logging.getLogger(__name__)


def _get_keys_file():
    return os.path.join(get_config_dir(), "keys.json")


def _derive_key(master_password: str) -> bytes:
    """从主密码派生 32 字节密钥"""
    return hashlib.sha256(master_password.encode("utf-8")).digest()


def _encrypt(plaintext: str, key: bytes) -> str:
    """简单 XOR 加密 + base64 编码"""
    data = plaintext.encode("utf-8")
    encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.b64encode(encrypted).decode("ascii")


def _decrypt(ciphertext: str, key: bytes) -> str:
    """base64 解码 + XOR 解密"""
    try:
        data = base64.b64decode(ciphertext)
        decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        return decrypted.decode("utf-8")
    except Exception:
        return ""


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
        # 启动时自动加载：无密码则直接可用，有密码则需 unlock()
        self._load_raw()
        if not self._master_hash:
            # 无主密码 → 明文模式，直接标记解锁
            self._unlocked = True

    def has_master(self) -> bool:
        """是否已设置主密码"""
        return bool(self._master_hash)

    def set_master(self, password: str):
        """设置主密码并加密存储"""
        self._master_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        self._key = _derive_key(password)
        self._unlocked = True
        self._save()

    def remove_master(self):
        """移除主密码，将所有条目解密后明文存储"""
        if self._master_hash and self._unlocked:
            # 解密所有条目到明文
            self._decrypt_all()
        self._master_hash = ""
        self._key = b""
        self._unlocked = True
        # 明文保存
        self._save()

    def unlock(self, password: str) -> bool:
        """验证主密码并解锁"""
        h = hashlib.sha256(password.encode("utf-8")).hexdigest()
        if h == self._master_hash:
            self._key = _derive_key(password)
            self._unlocked = True
            self._decrypt_all()
            return True
        return False

    def lock(self):
        """锁定（仅在有主密码时有效）"""
        if not self._master_hash:
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
            return
        entry = {
            "id": uuid.uuid4().int & ((1 << 53) - 1),
            "name": name,
            "type": entry_type,
            "value": value,
            "url": url,
            "url_anthropic": url_anthropic,
            "note": note,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._entries.append(entry)
        self._save()

    def update_entry(self, entry_id: int, **kwargs):
        for e in self._entries:
            if e["id"] == entry_id:
                e.update(kwargs)
                self._save()
                return

    def delete_entry(self, entry_id: int):
        self._entries = [e for e in self._entries if e["id"] != entry_id]
        self._save()

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
            self._master_hash = data.get("master_hash", "")
            raw_entries = data.get("entries", [])
            # 无主密码时，entries 直接含 value 明文
            if not self._master_hash:
                self._entries = []
                for e in raw_entries:
                    entry = dict(e)
                    # 兼容旧数据：有 enc_value 但无 value 时解密（理论上无密码不会有）
                    if "value" not in entry and "enc_value" in entry:
                        entry["value"] = entry.get("enc_value", "")
                    self._entries.append(entry)
            else:
                self._entries = raw_entries
        except Exception:
            self._entries = []
            self._master_hash = ""

    def _decrypt_all(self):
        """解锁后解密所有条目的 value"""
        for e in self._entries:
            enc = e.get("enc_value", "")
            if enc:
                e["value"] = _decrypt(enc, self._key)

    def _save(self):
        """保存到文件"""
        os.makedirs(os.path.dirname(_get_keys_file()), exist_ok=True)
        save_entries = []
        for e in self._entries:
            se = dict(e)
            if self._master_hash and self._key and e.get("value"):
                # 有主密码 → 加密存储
                se["enc_value"] = _encrypt(e["value"], self._key)
                se.pop("value", None)
            else:
                # 无主密码 → 明文存储
                se.pop("enc_value", None)
            save_entries.append(se)
        data = {
            "master_hash": self._master_hash,
            "entries": save_entries,
        }
        try:
            with open(_get_keys_file(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("保存密钥失败: %s", e)
