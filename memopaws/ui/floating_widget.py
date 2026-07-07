"""悬浮快捷窗 - 常驻贴边，菜单左侧弹出"""

import json

from PySide6.QtCore import Qt, QPoint, QEvent, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QFrame, QGraphicsDropShadowEffect

from ..core.utils import get_icon_pixmap


class FloatingWidget(QWidget):
    DEFAULT_EDGE_MARGIN = 0
    DEFAULT_RIGHT_MARGIN = DEFAULT_EDGE_MARGIN

    def __init__(self, *, get_config_path, get_theme, on_capture_ocr, on_paste_ocr,
                 on_open_clipboard, on_open_memo, on_open_settings):
        super().__init__(None)
        self._get_config_path = get_config_path
        self._get_theme = get_theme
        self._on_capture_ocr = on_capture_ocr
        self._on_paste_ocr = on_paste_ocr
        self._on_open_clipboard = on_open_clipboard
        self._on_open_memo = on_open_memo
        self._on_open_settings = on_open_settings
        self._menu_open = False
        self._drag_offset = None
        self._dragging = False
        self.W = 56
        self._hover_close_timer = QTimer(self)
        self._hover_close_timer.setSingleShot(True)
        self._hover_close_timer.setInterval(120)
        self._hover_close_timer.timeout.connect(self._close_menu)

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(self.W)

        self._build_ui()
        self._load_position()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.main_btn = QPushButton()
        self.main_btn.setFixedSize(56, 56)
        self.main_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.main_btn.setMouseTracking(True)
        self.main_btn.setStyleSheet(
            "QPushButton { border-radius: 28px; border: none; background: #FDF4EA; }"
            "QPushButton:hover { background: #FDF4EA; }"
        )
        pix = get_icon_pixmap(30)
        self.main_btn.setIcon(QIcon(pix))
        self.main_btn.setIconSize(pix.size())
        self.main_btn.installEventFilter(self)
        layout.addWidget(self.main_btn, 0, Qt.AlignmentFlag.AlignCenter)

    def _toggle_menu(self):
        if self._menu_open:
            self._close_menu()
            return
        t = self._get_theme()
        panel = QFrame(None)
        panel.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        panel.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        panel.setMouseTracking(True)
        panel.installEventFilter(self)
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 70))
        panel_shell = QVBoxLayout(panel)
        panel_shell.setContentsMargins(10, 10, 10, 14)
        panel_shell.setSpacing(0)

        card = QFrame(panel)
        card.setObjectName("menuPanel")
        card.setGraphicsEffect(shadow)
        card.setStyleSheet(f"""
            QFrame#menuPanel {{
                background: {t.bg_panel};
                border: 1px solid {t.border_subtle};
                border-radius: 12px;
            }}
            QPushButton {{
                border-radius: 8px; padding: 8px 18px;
                background: {t.bg_neutral_button}; color: {t.text_primary};
                font-size: 13px; text-align: left; border: none;
            }}
            QPushButton:hover {{
                background: {t.bg_active}; color: {t.accent};
            }}
        """)

        panel_shell.addWidget(card)

        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(4)

        for text, handler in [
            ("截图OCR", self._on_capture_ocr),
            ("粘贴OCR", self._on_paste_ocr),
            ("剪切板", self._on_open_clipboard),
            ("备忘录", self._on_open_memo),
            ("设置", self._on_open_settings),
        ]:
            btn = QPushButton(text)
            btn.setFixedWidth(100)
            btn.clicked.connect(lambda checked=False, h=handler: self._on_menu_pick(h))
            vbox.addWidget(btn)

        card.adjustSize()
        panel.adjustSize()
        px = self.x() - panel.width() - 8
        global_btn = self.main_btn.mapToGlobal(QPoint(0, 0))
        py = global_btn.y() + (self.main_btn.height() - panel.height()) // 2
        panel.move(px, py)
        panel.show()
        self._menu_panel = panel
        self._menu_open = True

    def _on_menu_pick(self, handler):
        self._close_menu()
        handler()

    def _close_menu(self):
        if hasattr(self, '_menu_panel') and self._menu_panel:
            self._menu_panel.close()
            self._menu_panel.deleteLater()
            self._menu_panel = None
        self._menu_open = False

    def eventFilter(self, obj, event):
        if hasattr(self, 'main_btn') and obj is self.main_btn:
            if event.type() == QEvent.Type.Enter:
                self._hover_close_timer.stop()
                if not self._dragging and not self._menu_open:
                    self._toggle_menu()
                return False
            if event.type() == QEvent.Type.Leave:
                self._start_hover_close()
                return False
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._dragging = False
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self._close_menu()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
                self._dragging = True
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = None
                self._snap_inside_screen()
                self._save_position()
                QTimer.singleShot(0, lambda: setattr(self, '_dragging', False))
                return True
        if hasattr(self, '_menu_panel') and obj is self._menu_panel:
            if event.type() == QEvent.Type.Enter:
                self._hover_close_timer.stop()
            elif event.type() == QEvent.Type.Leave:
                self._start_hover_close()
        return super().eventFilter(obj, event)

    def _start_hover_close(self):
        self._hover_close_timer.start()

    def _snap_inside_screen(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        center_x = self.x() + self.width() // 2
        left_x = screen.left() + self.DEFAULT_EDGE_MARGIN
        right_x = screen.right() - self.width() - self.DEFAULT_EDGE_MARGIN
        x = left_x if abs(center_x - left_x) < abs(center_x - right_x) else right_x
        y = min(max(screen.top(), self.y()), screen.bottom() - self.height())
        self.move(QPoint(x, y))

    def _load_position(self):
        try:
            with open(self._get_config_path(), "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        screen = QGuiApplication.primaryScreen().availableGeometry()
        default_x = screen.right() - self.width() - self.DEFAULT_EDGE_MARGIN
        pos = config.get("floating_widget_pos", {"x": default_x, "y": 120})
        self.move(QPoint(pos.get("x", default_x), pos.get("y", 120)))
        self._snap_inside_screen()

    def _save_position(self):
        try:
            with open(self._get_config_path(), "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["floating_widget_pos"] = {"x": self.x(), "y": self.y()}
        with open(self._get_config_path(), "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
