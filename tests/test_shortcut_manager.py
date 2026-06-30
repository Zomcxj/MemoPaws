"""快捷键管理器单元测试"""

import json
import os
import tempfile
import shutil

import pytest

from snaptrans.config.shortcut_manager import (
    _load_shortcuts,
    _save_shortcuts,
    DEFAULT_SHORTCUTS,
    ShortcutManager,
)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def config_path(temp_dir):
    return os.path.join(temp_dir, "SnapTrans.json")


def test_load_shortcuts_empty_file(config_path):
    result = _load_shortcuts(lambda: config_path)
    assert result == DEFAULT_SHORTCUTS


def test_load_shortcuts_nonexistent_file():
    result = _load_shortcuts(lambda: "/nonexistent/path.json")
    assert result == DEFAULT_SHORTCUTS


def test_load_shortcuts_with_saved(config_path):
    with open(config_path, "w") as f:
        json.dump({"shortcuts": {"capture": "Ctrl+Shift+X"}}, f)
    result = _load_shortcuts(lambda: config_path)
    assert result["capture"] == "Ctrl+Shift+X"
    assert result["canvas_fit"] == DEFAULT_SHORTCUTS["canvas_fit"]


def test_save_shortcuts(config_path):
    _save_shortcuts(lambda: config_path, lambda c: json.dump(c, open(config_path, "w")), {"capture": "F1"})
    with open(config_path) as f:
        data = json.load(f)
    assert data["shortcuts"]["capture"] == "F1"


def test_default_shortcuts_keys():
    assert "capture" in DEFAULT_SHORTCUTS
    assert "canvas_fit" in DEFAULT_SHORTCUTS
    assert "new_memo" in DEFAULT_SHORTCUTS


class TestShortcutManagerParseHotkey:
    @pytest.fixture
    def mgr(self, qapp, config_path, temp_dir):
        save_fn = lambda c: json.dump(c, open(config_path, "w"))
        return ShortcutManager(lambda: config_path, save_fn, None)

    def test_parse_alt_x(self, mgr):
        mods, vk = mgr._parse_hotkey("Alt+X")
        assert mods & 0x0001  # MOD_ALT
        assert vk == 0x58  # X

    def test_parse_ctrl_f(self, mgr):
        mods, vk = mgr._parse_hotkey("Ctrl+F")
        assert mods & 0x0002  # MOD_CONTROL
        assert vk == 0x46  # F

    def test_parse_ctrl_shift_n(self, mgr):
        mods, vk = mgr._parse_hotkey("Ctrl+Shift+N")
        assert mods & 0x0002  # MOD_CONTROL
        assert mods & 0x0004  # MOD_SHIFT
        assert vk == 0x4E  # N

    def test_parse_empty(self, mgr):
        mods, vk = mgr._parse_hotkey("")
        assert mods == 0
        assert vk == 0

    def test_parse_unknown_key(self, mgr):
        mods, vk = mgr._parse_hotkey("Alt+UnknownKey")
        assert mods & 0x0001
        assert vk == 0

    def test_parse_f1(self, mgr):
        mods, vk = mgr._parse_hotkey("Ctrl+F1")
        assert mods & 0x0002
        assert vk == 0x70

    def test_parse_f12(self, mgr):
        mods, vk = mgr._parse_hotkey("F12")
        assert mods == 0
        assert vk == 0x7B  # 0x70 + 11

    def test_parse_win_key(self, mgr):
        mods, vk = mgr._parse_hotkey("Win+X")
        assert mods & 0x0008  # MOD_WIN
        assert vk == 0x58


class TestShortcutManagerRegister:
    @pytest.fixture
    def mgr(self, qapp, config_path, temp_dir):
        save_fn = lambda c: json.dump(c, open(config_path, "w"))
        return ShortcutManager(lambda: config_path, save_fn, None)

    def test_register(self, mgr):
        handler = lambda: None
        mgr.register("capture", "Alt+X", handler)
        assert "capture" in mgr._handlers
        assert mgr._handlers["capture"] is handler
        assert mgr._keys["capture"] == "Alt+X"

    def test_get_current_keys_empty(self, mgr):
        result = mgr.get_current_keys()
        assert result == {}

    def test_get_current_keys_after_register(self, mgr):
        mgr.register("capture", "Alt+X", lambda: None)
        keys = mgr.get_current_keys()
        assert "capture" in keys

    def test_get_all_actions(self, mgr):
        mgr.register("capture", "Alt+X", lambda: None)
        actions = mgr.get_all_actions()
        assert len(actions) == 1
        assert actions[0][0] == "capture"
        assert actions[0][1] == "截图识别"
