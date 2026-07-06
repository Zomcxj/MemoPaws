"""MainWindow 的 UI 装配辅助函数。"""

import os

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QHBoxLayout, QStackedWidget

from ..clipboard.clipboard_page import ClipboardPage
from ..config.settings_page import SettingsPage
from ..core.themes import DARK, LIGHT, _hover
from ..core.utils import BUNDLE_DIR, get_icon_pixmap, load_svg_icon
from ..memo.memo_page import MemoPage
from .nav_sidebar import NavSidebar
from .recognize_page import RecognizePage


def build_title_bar(window, theme):
    """创建主窗口标题栏。"""
    title_bar = QFrame()
    title_bar.setFixedHeight(36)
    title_bar.setObjectName("titleBar")
    title_bar_layout = QHBoxLayout(title_bar)
    title_bar_layout.setContentsMargins(8, 0, 8, 0)
    title_bar_layout.setSpacing(0)

    title_icon_label = QLabel()
    title_icon_label.setPixmap(get_icon_pixmap(20))
    title_label = QLabel(window.windowTitle())
    title_label.setStyleSheet(f"font-size:16px; font-weight:bold; color:{theme.accent}; border:none; background:transparent;")
    title_bar_layout.addWidget(title_icon_label)
    title_bar_layout.addSpacing(6)
    title_bar_layout.addWidget(title_label)
    title_bar_layout.addStretch()

    icons_dir = os.path.join(BUNDLE_DIR, "assets", "icons")
    icon_color = theme.text_secondary
    window.minimize_btn = _title_button("minimize.svg", icons_dir, icon_color, theme)
    window.minimize_btn.clicked.connect(window.showMinimized)
    title_bar_layout.addWidget(window.minimize_btn)

    window.maximize_btn = _title_button("maximize.svg", icons_dir, icon_color, theme)
    window.maximize_btn.clicked.connect(window._toggle_maximize)
    title_bar_layout.addWidget(window.maximize_btn)

    window.close_btn = _title_button("close.svg", icons_dir, icon_color, theme, close=True)
    window.close_btn.clicked.connect(window.close)
    title_bar_layout.addWidget(window.close_btn)

    title_bar.mousePressEvent = lambda e: setattr(window, '_drag_pos', e.globalPosition().toPoint() - window.frameGeometry().topLeft()) if e.button() == Qt.MouseButton.LeftButton else None
    title_bar.mouseMoveEvent = lambda e: window.move(e.globalPosition().toPoint() - window._drag_pos) if e.buttons() & Qt.MouseButton.LeftButton and getattr(window, '_drag_pos', None) else None
    title_bar.mouseReleaseEvent = lambda e: setattr(window, '_drag_pos', None)
    title_bar.mouseDoubleClickEvent = lambda e: window._toggle_maximize()
    return title_bar


def build_pages(window):
    """创建导航栏和页面栈。"""
    window._icons_dir = os.path.join(BUNDLE_DIR, "assets", "icons")
    window.content_stack = QStackedWidget()
    window.nav_sidebar = NavSidebar(
        window,
        get_theme=lambda: DARK if window._current_theme_dark else LIGHT,
        is_dark=lambda: window._current_theme_dark,
        get_icons_dir=lambda: window._icons_dir,
        get_icon_clr=lambda: window._icon_clr,
        on_switch_page=lambda pk: window.content_stack.setCurrentIndex(
            {"设置": 0, "贴图识别": 1, "剪切板": 2, "备忘录": 3, "密钥": 4}.get(pk, 1)
        ),
        nav_items=[
            ("settings.svg", "设置"),
            ("camera.svg", "贴图识别"),
            ("clipboard.svg", "剪切板"),
            ("memo.svg", "备忘录"),
            ("key.svg", "密钥"),
        ],
    )
    _setup_managers(window)
    _setup_pages(window)
    return window.nav_sidebar, window.content_stack


def _title_button(icon_name, icons_dir, icon_color, theme, close=False):
    btn = QPushButton()
    btn.setIcon(QIcon(load_svg_icon(os.path.join(icons_dir, icon_name), 16, icon_color)))
    btn.setIconSize(QSize(16, 16))
    btn.setFixedSize(32, 28)
    hover_color = theme.error if close else _hover(theme)
    btn.setStyleSheet(f"""
        QPushButton {{ background: transparent; border: none; }}
        QPushButton:hover {{ background: {hover_color}; }}
    """)
    return btn


def _setup_managers(window):
    from ..config.shortcut_manager import ShortcutManager
    from ..config.text_replacer import TextReplacerManager

    window.shortcut_mgr = ShortcutManager(window._get_config_path, window.save_config, window)
    window.shortcut_mgr.register("capture", "Alt+X", lambda: window.recognize_page.start_capture())
    window.shortcut_mgr.register("canvas_fit", "Ctrl+F", lambda: window.recognize_page.canvas.zoom_fit())
    window.shortcut_mgr.register("new_memo", "Ctrl+N", lambda: window.memo_page.add_memo())
    window.text_replacer = TextReplacerManager(window._get_config_path, window.save_config)
    window.text_replacer.load()


def _setup_pages(window):
    window.settings_page = SettingsPage(
        window,
        get_config_path=window._get_config_path,
        get_theme=lambda: DARK if window._current_theme_dark else LIGHT,
        is_dark=lambda: window._current_theme_dark,
        load_config=window.load_config,
        save_config=window.save_config,
        ocr_manager=window.ocr_manager,
        on_toggle_theme=window.toggle_theme,
        on_set_theme=window._set_theme,
        on_set_language=window._set_language,
        get_current_lang=lambda: window._current_lang,
        get_current_theme_dark=lambda: window._current_theme_dark,
        on_save_clipboard=lambda: (
            window.clipboard_page._trim_clipboard(),
            window.clipboard_page._update_clipboard_list(),
        ),
        show_message=window.show_themed_message,
        shortcut_mgr=window.shortcut_mgr,
        text_replacer=window.text_replacer,
    )
    window.recognize_page = RecognizePage(
        window,
        get_config_path=window._get_config_path,
        get_theme=lambda: DARK if window._current_theme_dark else LIGHT,
        is_dark=lambda: window._current_theme_dark,
        get_icons_dir=lambda: window._icons_dir,
        get_icon_clr=lambda: window._icon_clr,
        ocr_manager=window.ocr_manager,
        translator=window.translator,
        on_append_status=window._append_status,
        on_switch_to_page=window._switch_page,
    )
    window.clipboard_page = _create_clipboard_page(window)
    window._clipboard.dataChanged.connect(window.clipboard_page._on_clipboard_changed)
    window.memo_page = MemoPage(
        window,
        get_config_path=window._get_config_path,
        get_theme=lambda: DARK if window._current_theme_dark else LIGHT,
        get_icons_dir=lambda: window._icons_dir,
        get_icon_clr=lambda: window._icon_clr,
        on_append_status=window._append_status,
        is_dark=lambda: window._current_theme_dark,
        show_message=window.show_themed_message,
        get_current_lang=lambda: window._current_lang,
    )

    from ..keys.key_page import KeyPage
    window.key_page = KeyPage(
        window,
        get_theme=lambda: DARK if window._current_theme_dark else LIGHT,
        is_dark=lambda: window._current_theme_dark,
        show_message=window.show_themed_message,
        get_icons_dir=lambda: window._icons_dir,
        get_icon_clr=lambda: window._icon_clr,
        get_current_lang=lambda: window._current_lang,
    )
    for page in (window.settings_page, window.recognize_page, window.clipboard_page, window.memo_page, window.key_page):
        window.content_stack.addWidget(page)


def _create_clipboard_page(window):
    page = ClipboardPage(
        window,
        get_config_path=window._get_config_path,
        get_theme=lambda: DARK if window._current_theme_dark else LIGHT,
        get_icons_dir=lambda: window._icons_dir,
        get_icon_clr=lambda: window._icon_clr,
        on_append_status=window._append_status,
        get_clip_data=lambda: window.clipboard_data,
        set_clip_data=lambda v: setattr(window, 'clipboard_data', v),
        get_current_lang=lambda: window._current_lang,
    )
    window.clipboard_data = page.load_clipboard()
    window.clipboard_list = page.clipboard_list
    page._update_clipboard_list()
    return page
