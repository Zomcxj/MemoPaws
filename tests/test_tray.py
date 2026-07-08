"""系统托盘 Mixin 单元测试"""

import pytest
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QWidget

from memopaws.ui.tray import TrayMixin


class TestTrayMixin:
    def test_mixin_has_required_methods(self):
        assert hasattr(TrayMixin, "_setup_tray")
        assert hasattr(TrayMixin, "_tray_activated")
        assert hasattr(TrayMixin, "_show_from_tray")
        assert hasattr(TrayMixin, "_quit_app")

    def test_tray_menu_has_show_floating_action(self, qapp):
        class DummyTray(TrayMixin, QWidget):
            def __init__(self):
                super().__init__()
                self._floating_widget = MagicMock()

            def windowIcon(self):
                from PySide6.QtGui import QIcon
                return QIcon()

            def _show_floating_widget_from_tray(self):
                pass

        widget = DummyTray()
        widget._setup_tray()
        actions = [a.text() for a in widget._tray_icon.contextMenu().actions()]
        assert "显示悬浮窗" in actions
