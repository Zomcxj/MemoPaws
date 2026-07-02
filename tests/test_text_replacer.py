import json
import os
import shutil
import tempfile

import pytest

from memopaws.config.text_replacer import TextReplacerManager


@pytest.fixture
def config_file():
    tmp_dir = tempfile.mkdtemp()
    cfg_path = os.path.join(tmp_dir, "config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"text_replacements": []}, f)
    yield cfg_path
    shutil.rmtree(tmp_dir)


@pytest.fixture
def manager(config_file):
    saved = {}

    def get_path():
        return config_file

    def save_config(cfg):
        saved.update(cfg)
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

    m = TextReplacerManager(get_path, save_config)
    m.load()
    return m


class TestTextReplacerManager:
    def test_init_empty(self, manager):
        assert manager.get_replacements() == []

    def test_add_and_lookup(self, manager):
        manager.add("brb", "be right back")
        assert manager.lookup("brb") == "be right back"
        assert manager.lookup("nonexist") is None

    def test_add_saves(self, manager):
        manager.add("lol", "laugh out loud")
        manager.reload()
        assert len(manager.get_replacements()) == 1
        assert manager.get_replacements()[0]["abbr"] == "lol"

    def test_update(self, manager):
        manager.add("old", "old_value")
        manager.update(0, "new", "new_value")
        assert manager.get_replacements()[0] == {"abbr": "new", "replacement": "new_value"}

    def test_update_invalid_index(self, manager):
        manager.update(999, "x", "y")
        assert manager.get_replacements() == []

    def test_delete(self, manager):
        manager.add("a", "1")
        manager.add("b", "2")
        manager.delete(0)
        assert len(manager.get_replacements()) == 1
        assert manager.get_replacements()[0]["abbr"] == "b"

    def test_delete_invalid_index(self, manager):
        manager.delete(999)
        pass

    def test_get_replacements_returns_copy(self, manager):
        manager.add("x", "y")
        r = manager.get_replacements()
        r.append({"abbr": "z", "replacement": "w"})
        assert len(manager.get_replacements()) == 1

    def test_try_replace_no_match(self, manager):
        manager.add("brb", "be right back")
        manager._buffer = "hello "
        assert manager._try_replace() is False

    def test_try_replace_exact_match(self, manager):
        manager.add("brb", "be right back")
        manager._buffer = "brb"
        result = manager._try_replace()
        assert manager._buffer == ""
        assert result is True

    def test_try_replace_longest_match(self, manager):
        manager.add("idk", "i don't know")
        manager.add("idky", "i don't know you")
        manager._buffer = "idky"
        assert manager._try_replace() is True

    def test_try_replace_empty_buffer(self, manager):
        manager.add("a", "b")
        manager._buffer = ""
        assert manager._try_replace() is False

    def test_try_replace_empty_replacements(self, manager):
        manager._buffer = "abc"
        assert manager._try_replace() is False

    def test_try_replace_abbr_empty_string(self, manager):
        manager._replacements = [{"abbr": "", "replacement": "x"}]
        manager._buffer = "abc"
        assert manager._try_replace() is False

    def test_reload(self, manager):
        manager.add("a", "1")
        manager._replacements = []
        assert len(manager.get_replacements()) == 0
        manager.reload()
        assert len(manager.get_replacements()) == 1

    def test_stop_no_crash(self, manager):
        manager.stop()
        assert manager._running is False
