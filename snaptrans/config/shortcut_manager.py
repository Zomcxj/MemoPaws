"""全局快捷键管理器"""

import json
import logging
import ctypes
import ctypes.wintypes
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QAbstractNativeEventFilter
from PySide6.QtGui import QKeySequence, QShortcut

logger = logging.getLogger(__name__)

# Windows API
user32 = ctypes.windll.user32
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

# 默认快捷键配置
DEFAULT_SHORTCUTS = {
    "capture": "Alt+X",
    "canvas_fit": "Ctrl+F",
    "new_memo": "Ctrl+N",
}


def _load_shortcuts(get_config_path) -> dict:
    """从配置文件加载快捷键，缺失字段用默认值补全"""
    try:
        with open(get_config_path(), "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    saved = cfg.get("shortcuts", {})
    result = dict(DEFAULT_SHORTCUTS)
    result.update(saved)
    return result


def _save_shortcuts(get_config_path, save_config, shortcuts: dict):
    """将快捷键保存到配置文件"""
    try:
        with open(get_config_path(), "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg["shortcuts"] = shortcuts
    save_config(cfg)


class HotkeyNativeFilter(QAbstractNativeEventFilter):
    """原生事件过滤器，处理 Windows 全局热键"""

    def __init__(self, hotkey_handlers: dict):
        super().__init__()
        self._handlers = hotkey_handlers

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG)).contents
            if msg.message == WM_HOTKEY:
                hotkey_id = msg.wParam
                handler = self._handlers.get(hotkey_id)
                if handler:
                    handler()
                    return True, 0
        return False, 0


class ShortcutManager:
    """管理全局快捷键的注册和更新"""

    def __init__(self, get_config_path, save_config, parent: QWidget):
        self._get_config_path = get_config_path
        self._save_config = save_config
        self._parent = parent
        self._shortcuts: dict[str, QShortcut] = {}
        self._handlers: dict[str, callable] = {}
        self._keys: dict[str, str] = {}
        self._global_hotkeys: dict[str, int] = {}
        self._hotkey_handlers: dict[int, callable] = {}
        # 安装原生事件过滤器到 QApplication
        from PySide6.QtWidgets import QApplication
        self._native_filter = HotkeyNativeFilter(self._hotkey_handlers)
        QApplication.instance().installNativeEventFilter(self._native_filter)

    def register(self, action: str, default_key: str, handler: callable):
        """注册一个快捷键动作"""
        self._handlers[action] = handler
        self._keys[action] = default_key

    def load_and_apply(self):
        """从配置加载快捷键并注册"""
        saved = _load_shortcuts(self._get_config_path)
        for action, handler in self._handlers.items():
            key = saved.get(action, self._keys.get(action, ""))
            self._bind(action, key, handler)

    def _bind(self, action: str, key: str, handler: callable):
        """绑定一个快捷键（同时注册全局热键）"""
        if action in self._shortcuts:
            self._shortcuts[action].setEnabled(False)
            self._shortcuts[action].deleteLater()

        # 注销旧的全局热键
        if action in self._global_hotkeys:
            self._unregister_global_hotkey(action)

        if not key:
            return

        # 注册全局热键
        self._register_global_hotkey(action, key, handler)

        logger.debug("快捷键注册: %s -> %s", action, key)

    def _parse_hotkey(self, key_str: str):
        """解析快捷键字符串，返回 (modifiers, vk_code)"""
        key_str = key_str.strip()
        modifiers = 0
        vk_code = 0

        if "Alt+" in key_str:
            modifiers |= MOD_ALT
            key_str = key_str.replace("Alt+", "")
        if "Ctrl+" in key_str or "Control+" in key_str:
            modifiers |= MOD_CONTROL
            key_str = key_str.replace("Ctrl+", "").replace("Control+", "")
        if "Shift+" in key_str:
            modifiers |= MOD_SHIFT
            key_str = key_str.replace("Shift+", "")
        if "Win+" in key_str or "Meta+" in key_str:
            modifiers |= MOD_WIN
            key_str = key_str.replace("Win+", "").replace("Meta+", "")

        # 按键映射
        key_map = {
            "X": 0x58, "F": 0x46, "N": 0x4E,
            "A": 0x41, "B": 0x42, "C": 0x43, "D": 0x44, "E": 0x45,
            "G": 0x47, "H": 0x48, "I": 0x49, "J": 0x4A, "K": 0x4B,
            "L": 0x4C, "M": 0x4D, "O": 0x4F, "P": 0x50, "Q": 0x51,
            "R": 0x52, "S": 0x53, "T": 0x54, "U": 0x55, "V": 0x56,
            "W": 0x57, "Y": 0x59, "Z": 0x5A,
            "Space": 0x20, "Return": 0x0D, "Escape": 0x1B,
            "Delete": 0x2E, "Backspace": 0x08, "Tab": 0x09,
        }
        vk_code = key_map.get(key_str.upper(), 0)
        if vk_code == 0:
            # 尝试 F1-F12
            if key_str.upper().startswith("F") and key_str[1:].isdigit():
                num = int(key_str[1:])
                if 1 <= num <= 12:
                    vk_code = 0x70 + num - 1

        return modifiers, vk_code

    def _register_global_hotkey(self, action: str, key_str: str, handler: callable):
        """注册 Windows 全局热键"""
        try:
            modifiers, vk_code = self._parse_hotkey(key_str)
            if not vk_code:
                logger.warning("无法解析快捷键: %s", key_str)
                return

            # 用 action 的 hash 作为 hotkey id
            hotkey_id = hash(action) & 0x7FFFFFFF
            if not user32.RegisterHotKey(None, hotkey_id, modifiers, vk_code):
                logger.warning("注册全局热键失败: %s (可能被其他程序占用)", key_str)
                return

            self._global_hotkeys[action] = hotkey_id
            self._hotkey_handlers[hotkey_id] = handler
            logger.info("全局热键注册: %s -> %s (id=%d)", action, key_str, hotkey_id)
        except Exception as e:
            logger.error("注册全局热键异常: %s", e)

    def _unregister_global_hotkey(self, action: str):
        """注销 Windows 全局热键"""
        hotkey_id = self._global_hotkeys.pop(action, None)
        if hotkey_id is not None:
            self._hotkey_handlers.pop(hotkey_id, None)
            user32.UnregisterHotKey(None, hotkey_id)
            logger.info("全局热键注销: %s (id=%d)", action, hotkey_id)

    def unregister_all(self):
        """注销所有全局热键"""
        for action in list(self._global_hotkeys.keys()):
            self._unregister_global_hotkey(action)

    def update_shortcut(self, action: str, new_key: str):
        """运行时更新某个快捷键"""
        handler = self._handlers.get(action)
        if handler is None:
            return
        self._bind(action, new_key, handler)
        self._save_to_config()

    def _save_to_config(self):
        """将当前所有快捷键写入配置文件"""
        keys = {}
        for action in self._handlers:
            sc = self._shortcuts.get(action)
            if sc and sc.isEnabled():
                keys[action] = sc.key().toString()
            else:
                keys[action] = self._keys.get(action, "")
        _save_shortcuts(self._get_config_path, self._save_config, keys)

    def get_current_keys(self) -> dict[str, str]:
        """获取当前所有快捷键的键值"""
        result = {}
        for action in self._handlers:
            sc = self._shortcuts.get(action)
            if sc and sc.isEnabled():
                result[action] = sc.key().toString()
            else:
                result[action] = self._keys.get(action, "")
        return result

    def get_all_actions(self) -> list[tuple[str, str, str]]:
        """返回 [(action, display_name, current_key), ...]"""
        names = {
            "capture": "截图识别",
            "canvas_fit": "画布自适应",
            "new_memo": "新建备忘录",
            "toggle_clipboard": "开关剪切板",
        }
        # 从配置文件读取快捷键（包括尚未 load_and_apply 的情况）
        saved = _load_shortcuts(self._get_config_path)
        result = []
        for action in self._handlers:
            sc = self._shortcuts.get(action)
            if sc and sc.isEnabled():
                key = sc.key().toString()
            else:
                key = saved.get(action, self._keys.get(action, ""))
            result.append((action, names.get(action, action), key))
        return result
