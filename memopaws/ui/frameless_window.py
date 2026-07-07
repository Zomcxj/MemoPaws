"""无边框窗口 Mixin - 通过 WM_NCCALCSIZE 隐藏标题栏但保留系统缩放/动画"""

import os
import ctypes
import ctypes.wintypes
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPainterPath, QIcon

from ..core.themes import DARK, LIGHT
from ..core.utils import load_svg_icon

# Windows API 常量
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
MONITOR_DEFAULTTONEAREST = 2
HTCLIENT = 1
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17
GWL_STYLE = -16
WS_THICKFRAME = 0x00040000


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", RECT * 3), ("lppos", ctypes.c_void_p)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]


def _svg_icon(svg_path, size=20, color=None):
    """加载 SVG 文件并返回 QIcon（包装 load_svg_icon）"""
    return QIcon(load_svg_icon(svg_path, size, color))


# 兼容既有测试和内部调用，实际实现统一在 utils.load_svg_icon。
_load_svg_icon = _svg_icon


class FramelessWindowMixin:
    """无边框窗口 Mixin：通过 WM_NCCALCSIZE 隐藏标题栏，保留系统缩放/动画。"""

    def _use_rounded_window(self) -> bool:
        return not self.isMaximized()

    def _setup_frameless(self):
        """在 __init__ 中调用，添加 WS_THICKFRAME 让系统处理缩放"""
        hwnd = int(self.winId())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_THICKFRAME)

    def _clamp_maximized_rect(self, monitor_rect, work_rect):
        return work_rect

    def _apply_maximized_work_area(self, message):
        params = NCCALCSIZE_PARAMS.from_address(int(message))
        monitor = ctypes.windll.user32.MonitorFromWindow(int(self.winId()), MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        left, top, right, bottom = self._clamp_maximized_rect(
            (info.rcMonitor.left, info.rcMonitor.top, info.rcMonitor.right, info.rcMonitor.bottom),
            (info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom),
        )
        params.rgrc[0].left = left
        params.rgrc[0].top = top
        params.rgrc[0].right = right
        params.rgrc[0].bottom = bottom

    def nativeEvent(self, event_type, message):
        """拦截 Windows 原生消息，实现无边框 + 系统缩放"""
        if event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCCALCSIZE and msg.wParam:
                if self.isMaximized():
                    self._apply_maximized_work_area(message)
                return True, 0
            elif msg.message == WM_NCHITTEST:
                result = self._hit_test(msg.lParam)
                if result is not None:
                    return True, result
        return super().nativeEvent(event_type, message)

    def _hit_test(self, lParam):
        """检测鼠标位置，返回 HT 值让系统处理缩放/光标"""
        x = ctypes.c_short(lParam & 0xFFFF).value
        y = ctypes.c_short((lParam >> 16) & 0xFFFF).value
        geo = self.frameGeometry()
        margin = 6
        left = geo.left()
        top = geo.top()
        right = geo.right()
        bottom = geo.bottom()

        # 四角
        if x <= left + margin and y <= top + margin:
            return HTTOPLEFT
        if x >= right - margin and y <= top + margin:
            return HTTOPRIGHT
        if x <= left + margin and y >= bottom - margin:
            return HTBOTTOMLEFT
        if x >= right - margin and y >= bottom - margin:
            return HTBOTTOMRIGHT
        # 四边
        if x <= left + margin:
            return HTLEFT
        if x >= right - margin:
            return HTRIGHT
        if y <= top + margin:
            return HTTOP
        if y >= bottom - margin:
            return HTBOTTOM
        # 客户区，显式返回 HTCLIENT
        return HTCLIENT

    def paintEvent(self, event):
        """画带圆角的窗口背景"""
        from PySide6.QtCore import QRectF
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _t = DARK if self._current_theme_dark else LIGHT
        bg = QColor(_t.bg_main)
        if not self._use_rounded_window():
            painter.fillRect(self.rect(), bg)
            painter.end()
            return
        path = QPainterPath()
        rect = QRectF(0, 0, self.width(), self.height())
        path.addRoundedRect(rect, self._window_radius, self._window_radius)
        painter.fillPath(path, bg)
        painter.end()

    def contextMenuEvent(self, event):
        """右键窗口空白处弹出窗口控制菜单"""
        if self._is_on_interactive_widget(self, event.pos()):
            return
        menu = QMenu(self)
        if self.isMaximized():
            act_restore = menu.addAction("❐  Restore")
        else:
            act_max = menu.addAction("□  Maximize")
        act_min = menu.addAction("─  Minimize")
        menu.addSeparator()
        act_close = menu.addAction("✕  Close")
        if self._current_theme_dark:
            menu.addSeparator()
            act_theme = menu.addAction("Switch to Light Theme")
        else:
            act_theme = menu.addAction("Switch to Dark Theme")
        if self._current_theme_dark:
            menu.setStyleSheet(self._window_menu_dark_style())
        else:
            menu.setStyleSheet(self._window_menu_light_style())
        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if self.isMaximized() and chosen.text() == "❐  Restore":
            self.showNormal()
        elif not self.isMaximized() and chosen.text() == "□  Maximize":
            self.showMaximized()
        elif chosen == act_min:
            self.showMinimized()
        elif chosen == act_close:
            self.close()
        elif chosen == act_theme:
            self.toggle_theme()

    def _is_on_interactive_widget(self, root_widget, pos):
        """检查 pos 是否在可交互子控件上"""
        from PySide6.QtWidgets import (
            QAbstractButton, QAbstractItemView, QAbstractSpinBox,
            QLineEdit, QTextEdit, QComboBox
        )
        interactive_types = (
            QAbstractButton, QAbstractItemView, QAbstractSpinBox,
            QLineEdit, QTextEdit, QComboBox
        )
        target_widget = root_widget.childAt(pos) if hasattr(root_widget, 'childAt') else None
        w = target_widget
        while w is not None and w is not root_widget:
            if isinstance(w, interactive_types):
                return True
            w = w.parentWidget()
        return False

    def _window_menu_dark_style(self):
        t = DARK
        return f"""
            QMenu {{
                background: {t.bg_panel};
                color: {t.text_primary};
                border: 1px solid {t.border_subtle};
                border-radius: 8px;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 8px 28px;
                border-radius: 8px;
                font-size: 13px;
            }}
            QMenu::item:selected {{
                background: rgba(255,255,255,0.06);
                color: {t.accent};
            }}
            QMenu::separator {{
                height: 1px;
                background: {t.border_subtle};
                margin: 4px 8px;
            }}
        """

    def _window_menu_light_style(self):
        t = LIGHT
        return f"""
            QMenu {{
                background: {t.bg_panel};
                color: {t.text_primary};
                border: 1px solid {t.border_subtle};
                border-radius: 8px;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 8px 28px;
                border-radius: 8px;
                font-size: 13px;
            }}
            QMenu::item:selected {{
                background: rgba(0,0,0,0.05);
                color: {t.accent};
            }}
            QMenu::separator {{
                height: 1px;
                background: {t.border_subtle};
                margin: 4px 8px;
            }}
        """

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event):
        """窗口状态变化时更新图标"""
        super().changeEvent(event)
        self._update_maximize_icon()

    def _update_maximize_icon(self):
        """根据最大化状态切换图标"""
        if hasattr(self, '_icons_dir'):
            icon_name = "restore.svg" if self.isMaximized() else "maximize.svg"
            self.maximize_btn.setIcon(_load_svg_icon(
                os.path.join(self._icons_dir, icon_name), 16, self._icon_clr))
