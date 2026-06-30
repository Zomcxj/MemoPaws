"""配置对话框单元测试"""

import pytest

from PySide6.QtWidgets import QApplication

from snaptrans.config.config_dialog import ConfigDialog


class TestConfigDialog:
    def test_create(self, qapp):
        dlg = ConfigDialog(config={"api_key": "test", "api_model": "gpt-4"})
        assert dlg is not None
        assert dlg.api_key == "test"
        assert dlg.api_model == "gpt-4"

    def test_defaults(self, qapp):
        dlg = ConfigDialog()
        assert dlg.api_key == ""
        assert dlg.api_model == "glm-4-flash"
        assert dlg.close_behavior == "exit"

    def test_get_config(self, qapp):
        dlg = ConfigDialog(config={"api_key": "k", "api_url": "u", "api_model": "m"})
        cfg = dlg.get_config()
        assert cfg["api_key"] == "k"
        assert cfg["api_url"] == "u"
        assert cfg["api_model"] == "m"

    def test_custom_theme(self, qapp):
        from snaptrans.core.themes import LIGHT
        dlg = ConfigDialog(config={}, is_dark=False)
        assert dlg is not None

    def test_close_behavior(self, qapp):
        dlg = ConfigDialog(config={"close_behavior": "tray"})
        assert dlg.close_behavior == "tray"
