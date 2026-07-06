"""主窗口模块 - 剪切板/备忘录版"""

import os
import json
import logging

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QMessageBox, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QSystemTrayIcon,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QGuiApplication, QFontDatabase

from ..core.utils import (
    APP_NAME, get_icon_path,
    set_title_bar_color, get_config_dir, ensure_config_dir,
    load_svg_icon
)
from ..core.themes import (
    DARK, LIGHT, get_main_stylesheet, get_status_list_stylesheet, _hover,
)
from ..ocr.ocr import OCRManager
from ..ocr.translator import SimpleTranslator
from .frameless_window import FramelessWindowMixin
from .tray import TrayMixin
from .main_window_ui import build_pages, build_title_bar

logger = logging.getLogger(__name__)


def _icon_color(is_dark: bool) -> str:
    """根据主题返回图标颜色"""
    t = DARK if is_dark else LIGHT
    return t.text_secondary
 
class MainWindow(TrayMixin, FramelessWindowMixin, QMainWindow):
    """MemoPaws 主窗口 - 侧边栏导航版"""

    theme_changed = Signal(bool)
    language_changed = Signal(str)
    
    def __init__(self):
        super().__init__()

        # 加载字体
        fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "fonts")
        for fname in ["JetBrainsMono-Regular.ttf", "JetBrainsMono-Medium.ttf", "JetBrainsMono-Bold.ttf"]:
            fpath = os.path.join(fonts_dir, fname)
            if os.path.exists(fpath):
                QFontDatabase.addApplicationFont(fpath)

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
                    APP_NAME, "应用已最小化到系统托盘",
                    QSystemTrayIcon.MessageIcon.Information, 2000
                )
        else:
            if self._tray_icon:
                self._tray_icon.hide()
            event.accept()
            from PySide6.QtWidgets import QApplication
            QApplication.instance().quit()

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
        
        root_layout.addWidget(build_title_bar(self, _t))
        
        # ── 内容行（导航栏 + 内容区）──
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)
        
        self.nav_sidebar, self.content_stack = build_pages(self)
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
        if lang == self._current_lang:
            return
        self._current_lang = lang
        config = self.load_config()
        config["language"] = lang
        self.save_config(config)
        self._apply_language(lang)
    
    def _apply_language(self, lang: str):
        """应用语言设置，通过信号分发给各模块"""
        self.language_changed.emit(lang)
    def show_themed_message(self, icon, title, text):
        msg = QMessageBox(self)
        msg.setIcon(icon)
        msg.setWindowTitle(title)
        msg.setText(text)
        ok_btn = msg.addButton("OK" if self._current_lang == "en" else "确定", QMessageBox.ButtonRole.AcceptRole)
        msg.setDefaultButton(ok_btn)
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



