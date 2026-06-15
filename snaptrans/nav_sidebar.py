"""导航栏侧边栏组件"""

import os
import re

from PySide6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt, QSize, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

from .themes import DARK, LIGHT, _hover


def _load_svg_icon(svg_path: str, size: int = 20, color: str = None) -> QPixmap:
    """加载 SVG 文件并返回指定大小的 QPixmap，支持动态换色"""
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_data = f.read()
    if color:
        svg_data = svg_data.replace('currentColor', color)
        svg_data = re.sub(r'fill="#ccc"', f'fill="{color}"', svg_data)
    renderer = QSvgRenderer(svg_data.encode("utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


class NavSidebar(QWidget):
    """左侧导航栏侧边栏"""

    def __init__(self, parent, *,
                 get_theme,
                 is_dark,
                 get_icons_dir,
                 get_icon_clr,
                 nav_expanded_width=180,
                 nav_collapsed_width=60,
                 on_switch_page,
                 nav_items,
                 initial_page=None,
                 ):
        super().__init__(parent)

        self._get_theme = get_theme
        self._is_dark = is_dark
        self._get_icons_dir = get_icons_dir
        self._get_icon_clr = get_icon_clr
        self._nav_expanded_width = nav_expanded_width
        self._nav_collapsed_width = nav_collapsed_width
        self._on_switch_page = on_switch_page
        self._nav_items = nav_items  # [(icon_filename, page_key), ...]
        self._nav_expanded = True

        self._page_labels = {
            "zh": {"设置": "设置", "贴图识别": "贴图识别", "剪切板": "剪切板", "备忘录": "备忘录"},
            "en": {"设置": "Settings", "贴图识别": "Recognition", "剪切板": "Clipboard", "备忘录": "Notes"},
        }

        self._setup_ui()

        if initial_page:
            self._switch_page(initial_page)

        if hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(lambda _: self.apply_theme())
        if hasattr(parent, 'language_changed'):
            parent.language_changed.connect(self.apply_language)

    def _setup_ui(self):
        t = self._get_theme()
        ic = self._get_icon_clr()
        icons_dir = self._get_icons_dir()

        self.nav_frame = QWidget(self)
        self.nav_frame.setFixedWidth(self._nav_expanded_width)
        self._nav_anim = QVariantAnimation()
        self._nav_anim.setDuration(200)
        self._nav_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._nav_anim.valueChanged.connect(self._on_nav_anim_update)
        self.nav_frame.setObjectName("navFrame")
        nav_layout = QVBoxLayout(self.nav_frame)
        nav_layout.setContentsMargins(8, 16, 8, 16)
        nav_layout.setSpacing(0)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(13, 0, 0, 0)
        toggle_row.setSpacing(0)
        self.btn_toggle_nav = QPushButton()
        self.btn_toggle_nav.setFixedSize(24, 24)
        self.btn_toggle_nav.setIcon(QIcon(_load_svg_icon(
            os.path.join(icons_dir, "collapse.svg"), 18, ic)))
        self.btn_toggle_nav.setIconSize(QSize(18, 18))
        self.btn_toggle_nav.setStyleSheet(self._get_toggle_button_style(t))
        self.btn_toggle_nav.setToolTip("折叠侧边栏")
        self.btn_toggle_nav.clicked.connect(self._toggle_nav)
        toggle_row.addWidget(self.btn_toggle_nav)
        toggle_row.addStretch()
        nav_layout.addLayout(toggle_row)
        nav_layout.addSpacing(8)

        self._nav_buttons = []
        for icon_filename, page_key in self._nav_items:
            icon_path = os.path.join(icons_dir, icon_filename)
            icon_pixmap = _load_svg_icon(icon_path, 18, ic)
            btn = QPushButton(page_key)
            btn.setIcon(QIcon(icon_pixmap))
            btn.setIconSize(QSize(18, 18))
            btn.setFixedHeight(42)
            btn.setCheckable(True)
            btn.setProperty("page_name", page_key)
            btn.setStyleSheet(self._get_nav_button_style(False))
            btn.clicked.connect(lambda checked, pk=page_key: self._switch_page(pk))
            nav_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        nav_layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.nav_frame)

    def _get_toggle_button_style(self, t) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {t.text_secondary};
                border: none;
                border-radius: 8px;
                padding: 0;
                margin: 0;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.08); }}
            QPushButton:pressed {{ background: rgba(255,255,255,0.12); }}
        """

    def _get_nav_button_style(self, active: bool) -> str:
        t = self._get_theme()
        pad, fsize, align = "12px 8px 12px 12px", "13px", "left"
        if active:
            return f"""
                QPushButton {{
                    background: {t.bg_active};
                    color: {t.accent};
                    border: none;
                    border-radius: 12px;
                    padding: {pad};
                    font-size: {fsize};
                    text-align: {align};
                    line-height: 42px;
                }}
            """
        else:
            return f"""
                QPushButton {{
                    background: transparent;
                    color: {t.text_muted};
                    border: none;
                    border-radius: 10px;
                    padding: {pad};
                    font-size: {fsize};
                    text-align: {align};
                    line-height: 42px;
                }}
                QPushButton:hover {{
                    background: rgba(255,255,255,0.04);
                    color: {t.text_secondary};
                }}
            """

    def switch_page(self, page_key: str):
        """切换到指定页面，更新按钮高亮并触发回调"""
        for btn in self._nav_buttons:
            is_active = btn.property("page_name") == page_key
            btn.setChecked(is_active)
            btn.setStyleSheet(self._get_nav_button_style(is_active))
        if self._on_switch_page:
            self._on_switch_page(page_key)

    # 保留私有别名供内部按钮点击使用
    _switch_page = switch_page

    def _on_nav_anim_update(self, value):
        w = int(value)
        self.nav_frame.setFixedWidth(w)

    def _toggle_nav(self):
        self._nav_expanded = not self._nav_expanded
        t = self._get_theme()
        ic = self._get_icon_clr()
        icons_dir = self._get_icons_dir()

        # 先更新图标和文字
        if self._nav_expanded:
            self.btn_toggle_nav.setIcon(QIcon(_load_svg_icon(
                os.path.join(icons_dir, "collapse.svg"), 18, ic)))
            self.btn_toggle_nav.setIconSize(QSize(18, 18))
            self.btn_toggle_nav.setToolTip("折叠侧边栏")
            # 立即显示文字
            for btn, (icon_filename, page_key) in zip(self._nav_buttons, self._nav_items):
                btn.setText(page_key)
                btn.setIcon(QIcon(_load_svg_icon(
                    os.path.join(icons_dir, icon_filename), 18, ic)))
        else:
            self.btn_toggle_nav.setIcon(QIcon(_load_svg_icon(
                os.path.join(icons_dir, "panel-left.svg"), 18, ic)))
            self.btn_toggle_nav.setIconSize(QSize(18, 18))
            self.btn_toggle_nav.setToolTip("展开侧边栏")
            # 折叠时先清空文字，避免动画过程中文字溢出
            for btn, (icon_filename, _page_key) in zip(self._nav_buttons, self._nav_items):
                btn.setText("")
                btn.setIcon(QIcon(_load_svg_icon(
                    os.path.join(icons_dir, icon_filename), 18, ic)))

        self.btn_toggle_nav.setStyleSheet(self._get_toggle_button_style(t))
        for btn in self._nav_buttons:
            btn.setStyleSheet(self._get_nav_button_style(btn.isChecked()))

        # 动画过渡宽度
        self._nav_anim.stop()
        start_w = self.nav_frame.width()
        end_w = self._nav_expanded_width if self._nav_expanded else self._nav_collapsed_width
        self._nav_anim.setStartValue(start_w)
        self._nav_anim.setEndValue(end_w)
        self.nav_frame.setObjectName("navFrame" if self._nav_expanded else "navFrameCollapsed")
        self._nav_anim.start()

    def _force_refresh_icons(self):
        ic = self._get_icon_clr()
        icons_dir = self._get_icons_dir()
        for btn, (icon_filename, _page_key) in zip(self._nav_buttons, self._nav_items):
            btn.setIcon(QIcon(_load_svg_icon(
                os.path.join(icons_dir, icon_filename), 18, ic)))
            btn.setIconSize(QSize(18, 18))
        toggle_icon = "collapse.svg" if self._nav_expanded else "panel-left.svg"
        self.btn_toggle_nav.setIcon(QIcon(_load_svg_icon(
            os.path.join(icons_dir, toggle_icon), 18, ic)))
        self.btn_toggle_nav.setIconSize(QSize(18, 18))

    def apply_theme(self):
        t = self._get_theme()
        for btn in self._nav_buttons:
            btn.setStyleSheet(self._get_nav_button_style(btn.isChecked()))
        self._force_refresh_icons()
        self.btn_toggle_nav.setStyleSheet(self._get_toggle_button_style(t))

    def apply_language(self, lang: str):
        labels = self._page_labels.get(lang, self._page_labels["zh"])
        for btn, (_icon_filename, page_key) in zip(self._nav_buttons, self._nav_items):
            if self._nav_expanded:
                btn.setText(labels.get(page_key, page_key))
            else:
                btn.setText("")
