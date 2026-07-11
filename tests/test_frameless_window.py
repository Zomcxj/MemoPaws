"""无边框窗口 Mixin 单元测试"""

import pytest
from unittest.mock import call, patch, MagicMock
import ctypes
import ctypes.wintypes

from PySide6.QtWidgets import QWidget

from memopaws.ui.frameless_window import (
    FramelessWindowMixin,
    _load_svg_icon,
    WM_NCCALCSIZE,
    WM_NCHITTEST,
    HTCLIENT,
    SWP_FRAMECHANGED,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_NOOWNERZORDER,
    SWP_NOZORDER,
)


class TestFramelessConstants:
    def test_wm_constants(self):
        assert WM_NCCALCSIZE == 0x0083
        assert WM_NCHITTEST == 0x0084
        assert HTCLIENT == 1

    def test_ht_constants(self):
        from memopaws.ui.frameless_window import (
            HTLEFT, HTRIGHT, HTTOP, HTBOTTOM,
            HTTOPLEFT, HTTOPRIGHT, HTBOTTOMLEFT, HTBOTTOMRIGHT,
        )
        assert HTLEFT == 10
        assert HTRIGHT == 11
        assert HTTOP == 12
        assert HTBOTTOM == 15


class TestFramelessWindowMixin:
    def test_mixin_has_required_methods(self):
        assert hasattr(FramelessWindowMixin, "_setup_frameless")
        assert hasattr(FramelessWindowMixin, "nativeEvent")
        assert hasattr(FramelessWindowMixin, "_hit_test")
        assert hasattr(FramelessWindowMixin, "_toggle_maximize")
        assert hasattr(FramelessWindowMixin, "_is_on_interactive_widget")

    def test_maximized_window_disables_rounded_paint(self, qapp):
        class DummyWindow(FramelessWindowMixin, QWidget):
            def __init__(self):
                super().__init__()

            def isMaximized(self):
                return True

        window = DummyWindow()
        assert window._use_rounded_window() is False

    def test_maximized_rect_uses_work_area(self):
        class DummyWindow(FramelessWindowMixin, QWidget):
            pass

        window = DummyWindow()
        assert window._clamp_maximized_rect((0, 0, 1920, 1080), (0, 0, 1920, 1040)) == (0, 0, 1920, 1040)

    def test_setup_frameless_refreshes_non_client_frame(self):
        class DummyWindow(FramelessWindowMixin):
            def winId(self):
                return 123

        with patch("memopaws.ui.frameless_window.ctypes.windll", create=True) as windll:
            windll.user32.GetWindowLongW.return_value = 0
            DummyWindow()._setup_frameless()

        user32 = windll.user32
        assert user32.method_calls == [
            call.GetWindowLongW(123, -16),
            call.SetWindowLongW(123, -16, 0x00040000),
            call.SetWindowPos(
                123, 0, 0, 0, 0, 0,
                SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOOWNERZORDER | 0x0010,
            ),
        ]

    def test_native_event_uses_msg_lparam_for_nccalcsize(self, qapp):
        class DummyWindow(FramelessWindowMixin, QWidget):
            def __init__(self):
                super().__init__()
                self.called_with = None

            def isMaximized(self):
                return True

            def _apply_maximized_work_area(self, message_ptr):
                self.called_with = message_ptr

        window = DummyWindow()
        msg = ctypes.wintypes.MSG()
        msg.message = WM_NCCALCSIZE
        msg.wParam = 1
        msg.lParam = 123456

        handled, result = window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg))

        assert handled is True
        assert result == 0
        assert window.called_with == 123456
