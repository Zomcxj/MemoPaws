"""剪贴板页面单元测试"""

import os
import pytest

from PySide6.QtWidgets import QWidget

from snaptrans.clipboard.clipboard_page import ClipboardPage
from snaptrans.core.themes import DARK


class TestClipboardPage:
    @pytest.fixture
    def parent(self, qapp):
        return QWidget()

    @pytest.fixture
    def icons_dir(self):
        icons = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons")
        if os.path.isdir(icons):
            return icons
        pytest.skip("icons directory not found")

    def test_create(self, qapp, parent, icons_dir):
        page = ClipboardPage(
            parent,
            get_config_path=lambda: "",
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: [],
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )
        assert page is not None
