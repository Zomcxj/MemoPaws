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

    def test_tray_menu_toggles_window_and_floating_actions(self, qapp):
        class DummyFloating:
            def __init__(self):
                self._visible = False

            def isVisible(self):
                return self._visible

        class DummyTray(TrayMixin, QWidget):
            def __init__(self):
                super().__init__()
                self._floating_widget = DummyFloating()

            def windowIcon(self):
                from PySide6.QtGui import QIcon
                return QIcon()

        widget = DummyTray()
        widget._setup_tray()

        widget.hide()
        widget._floating_widget._visible = False
        widget._tray_icon.contextMenu().aboutToShow.emit()

        assert widget._tray_show_action.text() == "显示窗口"
        assert widget._tray_show_floating_action.text() == "显示悬浮窗"

        widget.show()
        widget._floating_widget._visible = True
        widget._tray_icon.contextMenu().aboutToShow.emit()

        assert widget._tray_show_action.text() == "隐藏窗口"
        assert widget._tray_show_floating_action.text() == "隐藏悬浮窗"

    def test_tray_toggle_actions_hide_when_already_visible(self, qapp):
        class DummyFloating:
            def __init__(self):
                self._visible = True

            def isVisible(self):
                return self._visible

            def show(self):
                self._visible = True

            def hide(self):
                self._visible = False

        class DummyTray(TrayMixin, QWidget):
            def __init__(self):
                super().__init__()
                self._floating_widget = DummyFloating()

            def windowIcon(self):
                from PySide6.QtGui import QIcon
                return QIcon()

            def _set_floating_widget_visible(self, visible):
                self._floating_widget._visible = bool(visible)

        widget = DummyTray()
        widget._setup_tray()
        widget.show()

        widget._toggle_window_from_tray()
        widget._toggle_floating_widget_from_tray()

        assert widget.isVisible() is False
        assert widget._floating_widget.isVisible() is False
