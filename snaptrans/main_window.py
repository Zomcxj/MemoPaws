"""主窗口模块 - 剪切板/备忘录版"""

import os
import sys
import json
import time
import pickle
import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QMessageBox,
    QLabel, QPushButton, QTextEdit, QVBoxLayout, QHBoxLayout,
    QSplitter, QFrame, QColorDialog, QSlider,
    QListWidget, QListWidgetItem, QScrollArea, QProgressBar,
    QSizePolicy, QDialog, QSystemTrayIcon, QMenu, QStackedWidget,
    QLineEdit, QSpinBox, QAbstractItemView, QCheckBox, QComboBox
)
from PySide6.QtCore import Qt, QTimer, QThread, QSize, QRect, Signal
from PySide6.QtGui import (
    QIcon, QFont, QGuiApplication, QShortcut, QKeySequence, QAction,
    QPixmap, QPainter, QColor, QFontDatabase
)
from PySide6.QtSvg import QSvgRenderer

from .utils import (
    APP_NAME, BUNDLE_DIR, get_icon_path,
    set_title_bar_color, get_config_dir, ensure_config_dir
)
from .themes import (
    DARK, LIGHT, ThemeColors,
    get_main_stylesheet, get_scroll_area_stylesheet,
    get_progress_bar_stylesheet, get_text_edit_stylesheet,
    get_status_list_stylesheet, get_clear_history_stylesheet,
    get_theme_button_stylesheet, _hover, _inner_shadow
)
from .ocr import OCRManager
from .translator import SimpleTranslator
from .config_dialog import ConfigDialog
from .clipboard_dialog import ClipboardEditDialog
from .clipboard_page import ClipboardPage
from .recognize_page import RecognizePage
from .frameless_window import FramelessWindowMixin
from .tray import TrayMixin
from .memo_page import MemoPage
from .settings_page import SettingsPage
from .nav_sidebar import NavSidebar

logger = logging.getLogger(__name__)

def load_svg_icon(svg_path: str, size: int = 20, color: str = None) -> QPixmap:
    """加载 SVG 文件并返回指定大小的 QPixmap，支持动态换色"""
    import re
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


def _icon_color(is_dark: bool) -> str:
    """根据主题返回图标颜色"""
    t = DARK if is_dark else LIGHT
    return t.text_secondary
 
# 数据文件路径（统一从 snaptrans.utils 导入，存放在 ~/.SnapTrans/ 目录下）



def markdown_to_html(md: str, is_dark: bool = True) -> str:
    """使用 Python markdown 库将 Markdown 转为 HTML，带主题样式"""
    import markdown as md_lib
    import re

    t = DARK if is_dark else LIGHT
    text_color = t.text_primary
    heading_color = "#FFFFFF" if is_dark else t.text_primary
    link_color = t.accent
    code_bg = t.bg_panel
    code_color = t.text_secondary
    border_color = t.border_subtle
    quote_color = t.text_secondary
    th_bg = t.bg_panel

    html_body = md_lib.markdown(
        md,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
    )

    # QTextEdit 对 <style> 支持有限，用内联样式替换标签
    # h1-h6
    for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        html_body = html_body.replace(
            f"<{tag}>",
            f'<{tag} style="color:{heading_color};font-weight:bold;margin:12px 0 6px 0;border-bottom:1px solid {border_color};padding-bottom:3px;">'
        )
    # <p>
    html_body = html_body.replace("<p>", f'<p style="color:{text_color};margin:4px 0;">')
    # <a>
    html_body = re.sub(
        r'<a href="([^"]*)">',
        f'<a href="\\1" style="color:{link_color};text-decoration:underline;">',
        html_body,
    )
    # <code> (inline)
    html_body = html_body.replace(
        "<code>",
        f'<code style="background:{code_bg};color:{code_color};padding:1px 4px;border-radius:3px;font-family:Consolas,monospace;font-size:13px;">',
    )
    # <pre><code> (block)
    html_body = html_body.replace(
        "<pre>",
        f'<pre style="background:{code_bg};border:1px solid {border_color};border-radius:6px;padding:10px 12px;margin:8px 0;">',
    )
    html_body = html_body.replace(
        "<pre><code>",
        f'<pre style="background:{code_bg};border:1px solid {border_color};border-radius:6px;padding:10px 12px;margin:8px 0;"><code style="color:{code_color};font-family:Consolas,monospace;font-size:13px;">',
    )
    # <blockquote>
    html_body = html_body.replace(
        "<blockquote>",
        f'<blockquote style="border-left:4px solid {border_color};padding:6px 12px;margin:8px 0;color:{quote_color};">',
    )
    # <table>
    html_body = html_body.replace(
        "<table>",
        f'<table style="border-collapse:collapse;width:100%;margin:8px 0;">',
    )
    # <th>
    html_body = html_body.replace(
        "<th>",
        f'<th style="background:{th_bg};border:1px solid {border_color};padding:6px 10px;color:{heading_color};font-weight:bold;text-align:left;">',
    )
    # <td>
    html_body = html_body.replace(
        "<td>",
        f'<td style="border:1px solid {border_color};padding:6px 10px;color:{text_color};">',
    )
    # <hr>
    html_body = html_body.replace("<hr />", f'<hr style="border:none;border-top:1px solid {border_color};margin:12px 0;">')
    html_body = html_body.replace("<hr/>", f'<hr style="border:none;border-top:1px solid {border_color};margin:12px 0;">')
    # <li>
    html_body = html_body.replace("<li>", f'<li style="color:{text_color};margin:2px 0;">')

    return f'<div style="font-family:JetBrains Mono,宋体,Inter,Noto Sans SC,sans-serif;font-size:14px;line-height:1.7;color:{text_color};">{html_body}</div>'


class MainWindow(TrayMixin, FramelessWindowMixin, QMainWindow):
    """SnapTrans 主窗口 - 侧边栏导航版"""

    theme_changed = Signal(bool)
    language_changed = Signal(str)
    
    def __init__(self):
        super().__init__()

        # 加载字体
        fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "fonts")
        for fname in ["Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf",
                       "JetBrainsMono-Regular.ttf", "JetBrainsMono-Medium.ttf", "JetBrainsMono-Bold.ttf"]:
            fpath = os.path.join(fonts_dir, fname)
            if os.path.exists(fpath):
                QFontDatabase.addApplicationFont(fpath)
        _app_font = QFont()
        _app_font.setFamilies(["Microsoft YaHei", "JetBrains Mono", "Inter"])
        _app_font.setPointSize(10)
        _app_font.setStyleHint(QFont.StyleHint.SansSerif)
        QApplication.instance().setFont(_app_font)

        self.setWindowTitle(APP_NAME)
        self.resize(1460, 960)
        self.setMinimumSize(800, 600)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        icon_path = get_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))
        
        self.ocr_manager = OCRManager()
        self.translator = SimpleTranslator()
        
        saved_config = self.load_config()
        if saved_config:
            self.ocr_manager.set_config(saved_config)
            if saved_config.get("api_key"):
                self.translator.set_llm_config(
                    saved_config.get("api_key", ""),
                    saved_config.get("api_url", "https://open.bigmodel.cn/api/paas/v4/chat/completions"),
                    saved_config.get("api_model", "glm-4-flash"),
                )
        
        self.clipboard_data = []
        
        self._current_theme_dark = saved_config.get("theme", "dark") == "dark"
        self._current_lang = saved_config.get("language", "zh")
        
        # 无边框窗口 mixin 所需属性
        self._window_radius = 14
        self._drag_pos = None
        
        self.setStyleSheet(get_main_stylesheet(DARK if self._current_theme_dark else LIGHT))
        
        QTimer.singleShot(100, lambda: self._safe_set_title_bar_color())
        
        self._tray_icon = None
        self._setup_tray()
        
        # 剪贴板监听（延迟连接，等待 clipboard_page 创建）
        self._clipboard = QGuiApplication.clipboard()
        
        self.init_ui()
        self._setup_frameless()
        QTimer.singleShot(0, lambda: self.recognize_page._update_status_list())
        QTimer.singleShot(100, lambda: self._apply_language(self._current_lang))
    
    def closeEvent(self, event):
        config = self.load_config()
        if config.get("close_behavior") == "tray":
            event.ignore()
            self.hide()
            if self._tray_icon:
                self._tray_icon.showMessage(
                    "SnapTrans", "应用已最小化到系统托盘",
                    QSystemTrayIcon.MessageIcon.Information, 2000
                )
        else:
            if self._tray_icon:
                self._tray_icon.hide()
            event.accept()

    def init_ui(self):
        # 当前主题下的图标颜色
        _t = DARK if self._current_theme_dark else LIGHT
        self._icon_clr = _t.text_secondary
        """初始化界面：左侧导航栏 + 右侧页面（无标题栏）"""
        # ── 无标题栏窗口 ──
        # 操作说明：用户用左下角"退出"按钮关闭；
        # 整个窗口空白区域可按住拖动；边缘 6px 可拖动调整大小。
        self.setWindowFlags(Qt.WindowType.Window)
        # 启用透明背景，让 paintEvent 画圆角矩形（消除 4 角直角）
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        central = QWidget()
        self.setCentralWidget(central)
        
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # ── 标题栏 ──
        title_bar = QFrame()
        title_bar.setFixedHeight(36)
        title_bar.setObjectName("titleBar")
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(8, 0, 8, 0)
        title_bar_layout.setSpacing(0)
        
        # 左侧：图标 + "SnapTrans"
        from PySide6.QtGui import QPixmap, QPainter, QPainterPath
        from PySide6.QtCore import QRectF
        class _TitleIconWidget(QWidget):
            def __init__(self, pix, parent=None):
                super().__init__(parent)
                self._pix = pix
                self.setFixedSize(20, 20)
            def paintEvent(self, _):
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                path = QPainterPath()
                path.addRoundedRect(QRectF(0, 0, 20, 20), 5, 5)
                p.setClipPath(path)
                p.drawPixmap(0, 0, self._pix)
        from .utils import get_icon_pixmap
        title_icon = _TitleIconWidget(get_icon_pixmap(20))
        title_label = QLabel("SnapTrans")
        title_label.setStyleSheet(f"font-size:16px; font-weight:bold; color:{_t.accent}; border:none; background:transparent;")
        title_bar_layout.addWidget(title_icon)
        title_bar_layout.addSpacing(6)
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()
        
        # 右侧：最小化、最大化、关闭按钮
        _icons_dir = os.path.join(BUNDLE_DIR, "assets", "icons")
        _w_icon_clr = _t.text_secondary
        self.minimize_btn = QPushButton()
        self.minimize_btn.setIcon(QIcon(load_svg_icon(os.path.join(_icons_dir, "minimize.svg"), 16, _w_icon_clr)))
        self.minimize_btn.setIconSize(QSize(16, 16))
        self.minimize_btn.setFixedSize(32, 28)
        self.minimize_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; }}
            QPushButton:hover {{ background: {_hover(_t)}; }}
        """)
        self.minimize_btn.clicked.connect(self.showMinimized)
        title_bar_layout.addWidget(self.minimize_btn)
        
        self.maximize_btn = QPushButton()
        self.maximize_btn.setIcon(QIcon(load_svg_icon(os.path.join(_icons_dir, "maximize.svg"), 16, _w_icon_clr)))
        self.maximize_btn.setIconSize(QSize(16, 16))
        self.maximize_btn.setFixedSize(32, 28)
        self.maximize_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; }}
            QPushButton:hover {{ background: {_hover(_t)}; }}
        """)
        self.maximize_btn.clicked.connect(self._toggle_maximize)
        title_bar_layout.addWidget(self.maximize_btn)
        
        self.close_btn = QPushButton()
        self.close_btn.setIcon(QIcon(load_svg_icon(os.path.join(_icons_dir, "close.svg"), 16, _w_icon_clr)))
        self.close_btn.setIconSize(QSize(16, 16))
        self.close_btn.setFixedSize(32, 28)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; }}
            QPushButton:hover {{ background: {_t.error}; }}
        """)
        self.close_btn.clicked.connect(self.close)
        title_bar_layout.addWidget(self.close_btn)
        
        title_bar.mousePressEvent = lambda e: setattr(self, '_drag_pos', e.globalPosition().toPoint() - self.frameGeometry().topLeft()) if e.button() == Qt.MouseButton.LeftButton else None
        title_bar.mouseMoveEvent = lambda e: self.move(e.globalPosition().toPoint() - self._drag_pos) if e.buttons() & Qt.MouseButton.LeftButton and getattr(self, '_drag_pos', None) else None
        title_bar.mouseReleaseEvent = lambda e: setattr(self, '_drag_pos', None)
        title_bar.mouseDoubleClickEvent = lambda e: self._toggle_maximize()
        
        root_layout.addWidget(title_bar)
        
        # ── 内容行（导航栏 + 内容区）──
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)
        
        # ── 左侧导航栏 ──
        self._icons_dir = os.path.join(BUNDLE_DIR, "assets", "icons")
        self.nav_sidebar = NavSidebar(
            self,
            get_theme=lambda: DARK if self._current_theme_dark else LIGHT,
            is_dark=lambda: self._current_theme_dark,
            get_icons_dir=lambda: self._icons_dir,
            get_icon_clr=lambda: self._icon_clr,
            on_switch_page=lambda pk: self.content_stack.setCurrentIndex(
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
        
        # ── 右侧内容区 ──
        self.content_stack = QStackedWidget()
        
        # 快捷键管理器 + 文本替换管理器（在页面创建前初始化）
        from .shortcut_manager import ShortcutManager
        from .text_replacer import TextReplacerManager
        self.shortcut_mgr = ShortcutManager(
            self._get_config_path, self.save_config, self)
        # 注册快捷键动作（在 SettingsPage 创建前，这样设置页能读到列表）
        self.shortcut_mgr.register("capture", "Alt+X",
                                   lambda: self.recognize_page.start_capture())
        self.shortcut_mgr.register("canvas_fit", "Ctrl+F",
                                   lambda: self.recognize_page.canvas.zoom_fit())
        self.shortcut_mgr.register("new_memo", "Ctrl+N",
                                   lambda: self.memo_page.add_memo())
        self.text_replacer = TextReplacerManager(
            self._get_config_path, self.save_config)
        self.text_replacer.load()
        
        self.settings_page = SettingsPage(
            self,
            get_config_path=lambda: self._get_config_path(),
            get_theme=lambda: DARK if self._current_theme_dark else LIGHT,
            is_dark=lambda: self._current_theme_dark,
            load_config=lambda: self.load_config(),
            save_config=lambda cfg: self.save_config(cfg),
            ocr_manager=self.ocr_manager,
            on_toggle_theme=self.toggle_theme,
            on_set_theme=self._set_theme,
            on_set_language=self._set_language,
            get_current_lang=lambda: self._current_lang,
            get_current_theme_dark=lambda: self._current_theme_dark,
            on_save_clipboard=lambda: (
                self.clipboard_page._trim_clipboard(),
                self.clipboard_page._update_clipboard_list(),
            ),
            show_message=lambda icon, title, text: self.show_themed_message(icon, title, text),
            shortcut_mgr=self.shortcut_mgr,
            text_replacer=self.text_replacer,
        )
        self.recognize_page = RecognizePage(
            self,
            get_config_path=self._get_config_path,
            get_theme=lambda: DARK if self._current_theme_dark else LIGHT,
            is_dark=lambda: self._current_theme_dark,
            get_icons_dir=lambda: self._icons_dir,
            get_icon_clr=lambda: self._icon_clr,
            ocr_manager=self.ocr_manager,
            translator=self.translator,
            on_append_status=self._append_status,
            on_switch_to_page=self._switch_page,
        )
        self.clipboard_page = self._create_clipboard_page()
        self._clipboard.dataChanged.connect(self.clipboard_page._on_clipboard_changed)
        self.memo_page = MemoPage(
            self,
            get_config_path=lambda: self._get_config_path(),
            get_theme=lambda: DARK if self._current_theme_dark else LIGHT,
            get_icons_dir=lambda: self._icons_dir,
            get_icon_clr=lambda: self._icon_clr,
            on_append_status=lambda msg: self._append_status(msg),
            is_dark=lambda: self._current_theme_dark,
            show_message=lambda icon, title, text: self.show_themed_message(icon, title, text),
        )
        self.memo_data = self.memo_page.memo_data
        self.memo_list = self.memo_page.memo_list
        self.memo_title_input = self.memo_page.memo_title_input
        self.memo_content_view = self.memo_page.memo_content_view
        self.memo_stat_label = self.memo_page.memo_stat_label
        self.memo_time_label = self.memo_page.memo_time_label
        self.memo_btn_save = self.memo_page.memo_btn_save
        self.memo_preview_toggle = self.memo_page.memo_preview_toggle
        self._memo_left_frame = self.memo_page._memo_left_frame
        self._memo_right_frame = self.memo_page._memo_right_frame
        self._memo_btn_add = self.memo_page._memo_btn_add
        self._memo_btn_import = self.memo_page._memo_btn_import
        self._memo_btn_export = self.memo_page._memo_btn_export
        self._memo_btn_delete = self.memo_page._memo_btn_delete
        self._memo_editing = True
        self._memo_saving = False
        self._memo_current_idx = -1
        self._memo_original = None
        self._memo_md_source = ""

        from .key_page import KeyPage
        self.key_page = KeyPage(
            self,
            get_theme=lambda: DARK if self._current_theme_dark else LIGHT,
            is_dark=lambda: self._current_theme_dark,
            show_message=lambda icon, title, text: self.show_themed_message(icon, title, text),
            get_icons_dir=lambda: self._icons_dir,
            get_icon_clr=lambda: self._icon_clr,
            get_current_lang=lambda: self._current_lang,
        )

        self.content_stack.addWidget(self.settings_page)
        self.content_stack.addWidget(self.recognize_page)
        self.content_stack.addWidget(self.clipboard_page)
        self.content_stack.addWidget(self.memo_page)
        self.content_stack.addWidget(self.key_page)
        content_row.addWidget(self.nav_sidebar)
        content_row.addWidget(self.content_stack, 1)
        
        root_layout.addLayout(content_row)
        
        # 默认选中"贴图识别"
        self.nav_sidebar.switch_page("贴图识别")
        central.show()
        
        # 整体拖拽：侧边栏空白区域可拖拽窗口
        self.nav_sidebar.nav_frame.installEventFilter(self)
        
        # 全局快捷键（统一由 shortcut_mgr 管理）
        self.shortcut_mgr.load_and_apply()
        
        if not self._current_theme_dark:
            self._apply_theme(False)
    
    def _switch_page(self, page_name: str):
        self.nav_sidebar.switch_page(page_name)
    
    def _rebuild_logo_row(self, centered: bool):
        pass
    
    # ── 窗口拖拽 ──
    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj == self.nav_sidebar.nav_frame:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return False
            elif event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
                if self._drag_pos:
                    self.move(event.globalPosition().toPoint() - self._drag_pos)
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_pos = None
                return False
        return super().eventFilter(obj, event)
    
    # ══════════════════════════════════════════════
    #  剪切板页面
    # ══════════════════════════════════════════════
    def _create_clipboard_page(self):
        page = ClipboardPage(
            self,
            get_config_path=self._get_config_path,
            get_theme=lambda: DARK if self._current_theme_dark else LIGHT,
            get_icons_dir=lambda: self._icons_dir,
            get_icon_clr=lambda: self._icon_clr,
            on_append_status=self._append_status,
            get_clip_data=lambda: self.clipboard_data,
            set_clip_data=lambda v: setattr(self, 'clipboard_data', v),
            get_current_lang=lambda: self._current_lang,
        )
        self.clipboard_data = page.load_clipboard()
        self.clipboard_list = page.clipboard_list
        page._update_clipboard_list()
        return page
    
    # ══════════════════════════════════════════════
    #  备忘录页面（已提取到 memo_page.py）
    # ══════════════════════════════════════════════
    def add_memo(self):
        self.memo_page.add_memo()

    def delete_memo(self):
        self.memo_page.delete_memo()

    def _update_memo_list(self):
        self.memo_page._update_memo_list()

    def _select_memo(self, idx):
        self.memo_page._select_memo(idx)

    def _on_memo_selection_changed(self, idx):
        self.memo_page._on_memo_selection_changed(idx)

    def _show_memo_detail(self, idx):
        self.memo_page._show_memo_detail(idx)

    def _save_memo_edit(self, silent=False):
        self.memo_page._save_memo_edit(silent)

    def _toggle_memo_preview(self, checked):
        self.memo_page._toggle_memo_preview(checked)

    def _on_memo_text_changed(self):
        self.memo_page._on_memo_text_changed()

    def _import_memo(self):
        self.memo_page._import_memo()

    def _export_memo(self):
        self.memo_page._export_memo()

    def load_memo(self):
        return self.memo_page.load_memo()

    def save_memo(self):
        self.memo_page.save_memo()

    def _clear_memo_detail(self):
        self.memo_page._clear_memo_detail()
    
    # ══════════════════════════════════════════════
    #  通用功能
    # ══════════════════════════════════════════════
    def toggle_theme(self):
        dark = not self._current_theme_dark
        self._set_theme(dark)

    def _set_theme(self, dark: bool):
        if self._current_theme_dark == dark:
            return
        self._current_theme_dark = dark
        if hasattr(self, 'recognize_page') and self.recognize_page.canvas:
            self.recognize_page.canvas._theme_dark = dark
        self._apply_theme(dark)
        config = self.load_config()
        config["theme"] = "dark" if dark else "light"
        self.save_config(config)

    
    def _set_language(self, lang: str):
        """设置界面语言：en=English, zh=中文"""
        self._current_lang = lang
        config = self.load_config()
        config["language"] = lang
        self.save_config(config)
        self._apply_language(lang)
    
    def _apply_language(self, lang: str):
        """应用语言设置，通过信号分发给各模块"""
        self.language_changed.emit(lang)
    def show_themed_message(self, icon, title, text):
        msg = QMessageBox(icon, title, text, QMessageBox.StandardButton.Ok, self)
        set_title_bar_color(int(msg.winId()), self._current_theme_dark)
        msg.exec()
    
    def _safe_set_title_bar_color(self):
        try:
            set_title_bar_color(int(self.winId()), self._current_theme_dark)
        except Exception:
            pass

    def _apply_theme(self, dark: bool):
        t = DARK if dark else LIGHT
        try:
            hwnd = int(self.winId())
            set_title_bar_color(hwnd, dark)
        except Exception:
            pass
        _font = QFont()
        _font.setFamilies(["Microsoft YaHei", "JetBrains Mono", "Inter"])
        _font.setPointSize(10)
        _font.setStyleHint(QFont.StyleHint.SansSerif)
        QApplication.instance().setFont(_font)
        self.setStyleSheet(get_main_stylesheet(t))
        self._icon_clr = t.text_primary

        # 刷新标题栏按钮样式
        _w_icon_clr = t.text_secondary
        if hasattr(self, "minimize_btn"):
            self.minimize_btn.setIcon(QIcon(load_svg_icon(os.path.join(self._icons_dir, "minimize.svg"), 16, _w_icon_clr)))
            self.minimize_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none; }}
                QPushButton:hover {{ background: {_hover(t)}; }}
            """)
        if hasattr(self, "maximize_btn"):
            self.maximize_btn.setIcon(QIcon(load_svg_icon(os.path.join(self._icons_dir, "maximize.svg"), 16, _w_icon_clr)))
            self.maximize_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none; }}
                QPushButton:hover {{ background: {_hover(t)}; }}
            """)
        if hasattr(self, "close_btn"):
            self.close_btn.setIcon(QIcon(load_svg_icon(os.path.join(self._icons_dir, "close.svg"), 16, _w_icon_clr)))
            self.close_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none; }}
                QPushButton:hover {{ background: {t.error}; }}
            """)

        # 刷新剪切板列表样式
        if hasattr(self, 'clipboard_list'):
            self.clipboard_list.setStyleSheet(get_status_list_stylesheet(t))
        if hasattr(self, 'clipboard_list'):
            _clip_frame = self.clipboard_list.parentWidget()
            if _clip_frame and _clip_frame != self:
                _clip_frame.setStyleSheet(f"QFrame {{ background: {t.bg_panel}; border: 1px solid {t.border_subtle}; border-radius: 8px; }}")
        if hasattr(self, 'clipboard_page') and hasattr(self.clipboard_page, 'apply_theme'):
            self.clipboard_page.apply_theme()

        # 信号通知各模块更新主题
        self.theme_changed.emit(dark)

    
    def _append_status(self, msg: str):
        """在贴图识别页面的操作历史里追加一条简短的提示"""
        if hasattr(self, 'recognize_page'):
            self.recognize_page._append_status(msg)
    
    def open_config(self):
        config = self.load_config()
        dlg = ConfigDialog(self, config, is_dark=self._current_theme_dark)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_config = dlg.get_config()
            self.save_config(new_config)
            self.ocr_manager.set_config(new_config)
            self.settings_page._load_api_to_inputs()
            self.show_themed_message(QMessageBox.Icon.Information, "提示", "配置已保存")
    
    def _get_config_path(self):
        ensure_config_dir()
        return os.path.join(get_config_dir(), "setting.json")

    def save_config(self, config):
        config_path = self._get_config_path()
        ensure_config_dir()
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def load_config(self):
        config_path = self._get_config_path()
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # 补全缺失字段
            cfg.setdefault("clipboard_max_items", 50)
            cfg.setdefault("history_max_items", 100)
            cfg.setdefault("language", "zh")
            cfg.setdefault("close_behavior", "exit")
            cfg.setdefault("shortcuts", {})
            cfg.setdefault("text_replacements", [])
            return cfg
        return {
            "api_key": "",
            "api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            "api_model": "glm-4-flash",
            "close_behavior": "exit",
            "theme": "dark",
            "language": "zh",
            "clipboard_max_items": 50,
            "shortcuts": {},
            "text_replacements": [],
        }



