"""设置页面单元测试"""

import pytest
import tempfile
import os
import shutil
import time

from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QWidget

from memopaws.config.settings_page import SettingsPage
from memopaws.config import api_config
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
            on_set_floating_widget_visible=lambda visible: None,
            show_message=lambda *a, **kw: None,
        )
        assert page is not None
        assert getattr(page, '_floating_widget_visible', True) is True
        assert hasattr(page, "_floating_seg")

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
            on_set_floating_widget_visible=lambda visible: None,
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
            on_set_floating_widget_visible=lambda visible: None,
            show_message=lambda *a, **kw: None,
        )
        full_url = "https://api.test.com/v1/chat/completions"
        assert page._normalize_api_url(full_url) == full_url

    def test_toggle_floating_widget_saves_config(self, qapp, parent, tmp_config):
        saved = {}

        def load_config():
            return dict(saved)

        def save_config(config):
            saved.clear()
            saved.update(config)

        state = {"visible": None}
        page = SettingsPage(
            parent,
            get_config_path=lambda: tmp_config,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            load_config=load_config,
            save_config=save_config,
            ocr_manager=None,
            on_toggle_theme=lambda: None,
            on_set_theme=lambda t: None,
            on_set_language=lambda l: None,
            get_current_lang=lambda: "zh",
            get_current_theme_dark=lambda: True,
            on_save_clipboard=lambda c: None,
            on_set_floating_widget_visible=lambda visible: state.__setitem__("visible", visible),
            show_message=lambda *a, **kw: None,
        )
        page.floating_btn_hide.click()
        assert saved["show_floating_widget"] is False
        assert state["visible"] is False

    def test_api_test_starts_background_thread_without_blocking(self, qapp, monkeypatch):
        class SignalStub:
            def connect(self, callback):
                self.callback = callback

        class FakeThread:
            instances = []

            def __init__(self, api_key, api_url, api_model):
                self.api_key = api_key
                self.api_url = api_url
                self.api_model = api_model
                self.result_ready = SignalStub()
                self.finished = SignalStub()
                self.started = False
                FakeThread.instances.append(self)

            def isRunning(self):
                return False

            def start(self):
                self.started = True

            def deleteLater(self):
                pass

        monkeypatch.setattr(api_config, "ApiTestThread", FakeThread)

        page = QWidget()
        page._is_dark = lambda: True
        page.settings_key_input = QLineEdit()
        page.settings_key_input.setText("key")
        page.settings_url_input = QLineEdit()
        page.settings_url_input.setText("https://api.test.com/v1")
        page.settings_model_input = QLineEdit()
        page.settings_model_input.setText("model")
        page.settings_test_label = QLabel()
        page.settings_test_btn = QPushButton("测试连接")

        t0 = time.perf_counter()
        api_config.test_api_connection(page)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 100
        assert page.settings_test_label.text() == "⏳ 测试中..."
        assert page.settings_test_btn.text() == "取消"
        assert FakeThread.instances[0].started is True
        assert page._api_test_thread is FakeThread.instances[0]

    def test_api_test_second_click_requests_cancel(self, qapp):
        class RunningThread:
            def __init__(self):
                self.cancel_requested = False

            def isRunning(self):
                return True

            def requestInterruption(self):
                self.cancel_requested = True

        running = RunningThread()
        page = QWidget()
        page._is_dark = lambda: True
        page._api_test_thread = running
        page.settings_key_input = QLineEdit()
        page.settings_url_input = QLineEdit()
        page.settings_model_input = QLineEdit()
        page.settings_test_label = QLabel()

        api_config.test_api_connection(page)

        assert running.cancel_requested is True
        assert page.settings_test_label.text() == "⏹ 正在取消..."
