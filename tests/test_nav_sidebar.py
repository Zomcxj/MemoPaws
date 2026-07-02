"""导航侧栏单元测试"""

import os
import pytest

from PySide6.QtWidgets import QWidget

from memopaws.ui.nav_sidebar import NavSidebar


class TestNavSidebar:
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
        from memopaws.core.themes import DARK
        sidebar = NavSidebar(
            parent,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_switch_page=lambda p: None,
            nav_items=[("capture.svg", "截图"), ("memo.svg", "备忘录")],
            initial_page="capture",
        )
        assert sidebar is not None

    def test_apply_language(self, qapp, parent, icons_dir):
        from memopaws.core.themes import DARK
        sidebar = NavSidebar(
            parent,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_switch_page=lambda p: None,
            nav_items=[("capture.svg", "截图")],
            initial_page="capture",
        )
        sidebar.apply_language("en")
        sidebar.apply_language("zh")
