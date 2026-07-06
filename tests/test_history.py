"""HistoryManager 单元测试"""

import os
import sys
import json
import tempfile
import shutil

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memopaws.config.history import HistoryManager


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def history_manager(temp_dir):
    """创建临时目录中的 HistoryManager"""
    config_path = os.path.join(temp_dir, "MemoPaws.json")
    manager = HistoryManager(lambda: config_path, flush_interval=0)
    yield manager
    manager.flush()


def test_add_record(history_manager):
    history_manager.add_record("识别(本地)", "Hello World")
    assert len(history_manager.history_data) == 1
    record = history_manager.history_data[0]
    assert record["type"] == "识别(本地)"
    assert record["text"] == "Hello World"
    assert "time" in record


def test_clear_history(history_manager):
    history_manager.add_record("识别", "text1")
    history_manager.add_record("翻译", "text2")
    assert len(history_manager.history_data) == 2
    history_manager.clear()
    assert len(history_manager.history_data) == 0


def test_load_save(history_manager):
    history_manager.add_record("识别", "test text")
    history_manager.flush()
    history_manager.load()
    assert len(history_manager.history_data) == 1
    assert history_manager.history_data[0]["text"] == "test text"


def test_add_record_defers_disk_write_until_flush(history_manager):
    history_manager.add_record("识别", "batched text")
    assert not os.path.exists(history_manager._history_file)
    history_manager.flush()
    assert os.path.exists(history_manager._history_file)
    with open(history_manager._history_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data[0]["text"] == "batched text"


def test_history_file_path(history_manager, temp_dir):
    """_history_file 应基于传入的 get_config_path 推断路径"""
    expected = os.path.join(temp_dir, "history.json")
    assert history_manager._history_file == expected


def test_max_records(history_manager):
    for i in range(150):
        history_manager.add_record("test", f"text_{i}")
    assert len(history_manager.history_data) == 100


def test_parse_translate_record():
    text = "[原文] Hello\n[译文] 你好"
    source, target = HistoryManager.parse_translate_record(text)
    assert source == "Hello"
    assert target == "你好"
