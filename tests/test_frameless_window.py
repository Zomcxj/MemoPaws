"""无边框窗口 Mixin 单元测试"""

import pytest
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QWidget

from memopaws.ui.frameless_window import (
    FramelessWindowMixin,
    _load_svg_icon,
    WM_NCCALCSIZE,
    WM_NCHITTEST,
    HTCLIENT,
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
