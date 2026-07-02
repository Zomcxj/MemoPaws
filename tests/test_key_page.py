"""密钥页面单元测试"""

import pytest

from PySide6.QtWidgets import QWidget

from memopaws.keys.key_page import KeyPage
from memopaws.core.themes import DARK


class TestKeyPage:
    @pytest.fixture
    def parent(self, qapp):
        return QWidget()

    def test_create(self, qapp, parent):
        page = KeyPage(
            parent,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            show_message=lambda *a, **kw: None,
            get_icons_dir=lambda: "",
            get_icon_clr=lambda: "#fff",
            get_current_lang=lambda: "zh",
        )
        assert page is not None

    def test_apply_language(self, qapp, parent):
        page = KeyPage(
            parent,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            show_message=lambda *a, **kw: None,
            get_icons_dir=lambda: "",
            get_icon_clr=lambda: "#fff",
            get_current_lang=lambda: "zh",
        )
        page.apply_language("en")
        page.apply_language("zh")

    def test_latency_color(self, qapp, parent):
        page = KeyPage(
            parent,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            show_message=lambda *a, **kw: None,
            get_icons_dir=lambda: "",
            get_icon_clr=lambda: "#fff",
            get_current_lang=lambda: "zh",
        )
        assert page._get_latency_color(100) is not None
        assert page._get_latency_color(500) is not None
        assert page._get_latency_color(2000) is not None
