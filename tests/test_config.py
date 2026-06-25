"""配置管理单元测试"""

import os
import sys
import json
import tempfile
import shutil

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snaptrans.utils import CONFIG_DIR, CONFIG_FILE, ensure_config_dir


def get_default_config():
    return {
        "api_key": "",
        "api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "api_model": "glm-4-flash",
        "close_behavior": "exit",
        "theme": "dark",
        "language": "zh",
        "clipboard_max_items": 50,
    }


def test_load_config_default():
    config = get_default_config()
    assert config["theme"] == "dark"
    assert config["language"] == "zh"
    assert config["clipboard_max_items"] == 50
    assert config["api_model"] == "glm-4-flash"


def test_save_load_config(tmp_path):
    config_path = os.path.join(str(tmp_path), "test_config.json")
    config = get_default_config()
    config["theme"] = "light"
    config["api_key"] = "test_key_123"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    with open(config_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["theme"] == "light"
    assert loaded["api_key"] == "test_key_123"


def test_config_path():
    assert CONFIG_FILE.endswith("setting.json")
    assert os.path.basename(CONFIG_FILE) == "setting.json"
    assert ".snaptrans" in CONFIG_DIR
