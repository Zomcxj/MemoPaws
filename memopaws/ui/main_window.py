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
from ..search.global_search import search_all
from ..search.global_search_dialog import GlobalSearchDialog
from .floating_widget import FloatingWidget
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
        self._floating_widget = None
        self._pending_show_floating_widget = saved_config.get("show_floating_widget", True)
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

    def _open_global_search(self):
        dialog = GlobalSearchDialog(
            parent=self,
            search_provider=self._search_all_content,
            open_result=self._open_search_result,
        )
        dialog.search_input.setFocus()
        dialog.exec()

    def _search_all_content(self, query: str, scopes=None):
        history = getattr(self.recognize_page.history_manager, "history_data", []) if hasattr(self, "recognize_page") else []
        return search_all(
            memos=getattr(self.memo_page, "memo_data", []),
            clipboard=getattr(self, "clipboard_data", []),
            history=history,
            query=query,
            scopes=scopes,
        )

    def _open_search_result(self, result: dict):
        source = result.get("source")
        if source == "memo":
            self.nav_sidebar.switch_page("备忘录")
            idx = result.get("index")
            if idx is not None:
                line_number = result.get("line_number", 1)
                QTimer.singleShot(0, lambda i=idx, ln=line_number: self.memo_page.open_memo_at_line(i, ln) if 0 <= i < len(self.memo_page.memo_data) else None)
        elif source == "clipboard":
            self.nav_sidebar.switch_page("剪切板")
            idx = result.get("target_id")
            if idx is not None:
                def select_clipboard(row=idx):
                    if 0 <= row < self.clipboard_page.clipboard_list.count():
                        self.clipboard_page.clipboard_list.setCurrentRow(row)
                        self.clipboard_page.clipboard_list.scrollToItem(self.clipboard_page.clipboard_list.item(row), self.clipboard_page.clipboard_list.ScrollHint.PositionAtCenter)
                QTimer.singleShot(0, select_clipboard)
        elif source == "history":
            self.nav_sidebar.switch_page("贴图识别")
            idx = result.get("target_id")
            if idx is not None:
                def select_history(row=idx):
                    records = self.recognize_page.history_manager.history_data
                    if 0 <= row < len(records):
                        self.recognize_page.show_history_record(records[row])
                        if row < self.recognize_page.status_list.count():
                            self.recognize_page.status_list.setCurrentRow(row)
                            self.recognize_page.status_list.scrollToItem(self.recognize_page.status_list.item(row), self.recognize_page.status_list.ScrollHint.PositionAtCenter)
                QTimer.singleShot(0, select_history)

    def _setup_floating_widget(self):
        if self._floating_widget is not None:
            return
        self._floating_widget = FloatingWidget(
            get_config_path=self._get_config_path,
            get_theme=lambda: DARK if self._current_theme_dark else LIGHT,
            on_capture_ocr=lambda: self.recognize_page.start_capture(),
            on_paste_ocr=self.recognize_page.paste_ocr_simple,
            on_open_clipboard=lambda: self.nav_sidebar.switch_page("剪切板"),
            on_open_memo=lambda: self.nav_sidebar.switch_page("备忘录"),
            on_open_settings=lambda: self.nav_sidebar.switch_page("设置"),
            on_hide_floating=lambda: self._set_floating_widget_visible(False),
        )
    
    # ── 窗口拖拽 ──
    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj == self.nav_sidebar.nav_frame:
            if self.isMaximized():
                self._drag_pos = None
                return False
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

    def changeEvent(self, event):
        super().changeEvent(event)
        self._sync_window_surface()

    def showEvent(self, event):
        super().showEvent(event)
        if self._floating_widget is None:
            self._setup_floating_widget()
        if self._pending_show_floating_widget and self._floating_widget and not self._floating_widget.isVisible():
            self._pending_show_floating_widget = False
            QTimer.singleShot(0, self._floating_widget.show)

    def _sync_window_surface(self):
        # 最大化时不要透明外壳，避免无边框窗口客户区边缘被系统裁掉。
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, not self.isMaximized())
        self.update()

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
        if msg.startswith("悬浮窗"):
            return
        if hasattr(self, 'recognize_page'):
            self.recognize_page._append_status(msg)

    def _set_floating_widget_visible(self, visible: bool):
        self._pending_show_floating_widget = bool(visible)
        if not self._floating_widget:
            if not visible:
                config = self.load_config()
                config["show_floating_widget"] = False
                self.save_config(config)
                if hasattr(self, 'settings_page'):
                    self.settings_page._sync_floating_widget_visibility(False)
                return
            self._setup_floating_widget()
        config = self.load_config()
        config["show_floating_widget"] = bool(visible)
        self.save_config(config)
        if hasattr(self, 'settings_page'):
            self.settings_page._sync_floating_widget_visibility(bool(visible))
        if visible:
            self._floating_widget.show()
            self._floating_widget.raise_()
        else:
            self._floating_widget.hide()
    
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



