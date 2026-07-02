"""设置页面单元测试"""

import pytest
import tempfile
import os
import shutil

from PySide6.QtWidgets import QWidget

from memopaws.config.settings_page import SettingsPage
from memopaws.core.themes import DARK, LIGHT


class TestSettingsPage:
    @pytest.fixture
    def parent(self, qapp):
        return QWidget()

    @pytest.fixture
    def tmp_config(self):
        d = tempfile.mkdtemp()
        cfg_path = os.path.join(d, "MemoPaws.json")
        yield cfg_path
        shutil.rmtree(d)

    def test_create(self, qapp, parent, tmp_config):
        page = SettingsPage(
            parent,
            get_config_path=lambda: tmp_config,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            load_config=lambda: {},
            save_config=lambda c: None,
            ocr_manager=None,
            on_toggle_theme=lambda: None,
            on_set_theme=lambda t: None,
            on_set_language=lambda l: None,
            get_current_lang=lambda: "zh",
            get_current_theme_dark=lambda: True,
            on_save_clipboard=lambda c: None,
            show_message=lambda *a, **kw: None,
        )
        assert page is not None

    def test_normalize_api_url(self, qapp, parent, tmp_config):
        page = SettingsPage(
            parent,
            get_config_path=lambda: tmp_config,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            load_config=lambda: {},
            save_config=lambda c: None,
            ocr_manager=None,
            on_toggle_theme=lambda: None,
            on_set_theme=lambda t: None,
            on_set_language=lambda l: None,
            get_current_lang=lambda: "zh",
            get_current_theme_dark=lambda: True,
            on_save_clipboard=lambda c: None,
            show_message=lambda *a, **kw: None,
        )
        url = page._normalize_api_url("https://api.test.com/v1")
        assert url.endswith("/chat/completions")

    def test_normalize_api_url_already_full(self, qapp, parent, tmp_config):
        page = SettingsPage(
            parent,
            get_config_path=lambda: tmp_config,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            load_config=lambda: {},
            save_config=lambda c: None,
            ocr_manager=None,
            on_toggle_theme=lambda: None,
            on_set_theme=lambda t: None,
            on_set_language=lambda l: None,
            get_current_lang=lambda: "zh",
            get_current_theme_dark=lambda: True,
            on_save_clipboard=lambda c: None,
            show_message=lambda *a, **kw: None,
        )
        full_url = "https://api.test.com/v1/chat/completions"
        assert page._normalize_api_url(full_url) == full_url
