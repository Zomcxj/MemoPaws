"""剪贴板页面单元测试"""

import os
import pytest

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from memopaws.clipboard.clipboard_page import ClipboardPage
from memopaws.core.themes import DARK


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

    def test_search_input_filters_after_debounce(self, qapp, parent, icons_dir):
        data = [
            {"time": "2024-01-01 10:00:00", "text": "needle text", "locked": False},
            {"time": "2024-01-01 09:00:00", "text": "other text", "locked": False},
        ]
        page = ClipboardPage(
            parent,
            get_config_path=lambda: "",
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: data,
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )

        page.search_input.setText("needle")
        qapp.processEvents()

        assert [page.clipboard_list.item(i).isHidden() for i in range(page.clipboard_list.count())] == [False, False]

        QTest.qWait(page.SEARCH_DEBOUNCE_MS + 50)
        qapp.processEvents()

        assert [page.clipboard_list.item(i).isHidden() for i in range(page.clipboard_list.count())] == [False, True]
