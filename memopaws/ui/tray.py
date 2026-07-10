"""系统托盘逻辑 - TrayMixin"""

import logging

from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu
)
from PySide6.QtGui import QIcon, QAction

from ..core.utils import APP_NAME, get_icon_path

logger = logging.getLogger(__name__)


class TrayMixin:
    """系统托盘 Mixin：提供托盘图标、右键菜单、双击显示等功能"""

    def _is_floating_widget_visible(self):
        widget = getattr(self, "_floating_widget", None)
        if not widget or not hasattr(widget, "isVisible"):
            return False
        visible = widget.isVisible()
        return visible if isinstance(visible, bool) else False

    def _refresh_tray_menu(self):
        if not getattr(self, "_tray_icon", None):
            return
        if hasattr(self, "_tray_show_action"):
            self._tray_show_action.setText("隐藏窗口" if self.isVisible() else "显示窗口")
        if hasattr(self, "_tray_show_floating_action"):
            self._tray_show_floating_action.setText(
                "隐藏悬浮窗" if self._is_floating_widget_visible() else "显示悬浮窗"
            )

    def _setup_tray(self):
        """初始化系统托盘"""
        try:
            self._tray_icon = QSystemTrayIcon(self)
            icon_path = get_icon_path()
            if icon_path:
                self._tray_icon.setIcon(QIcon(icon_path))
            else:
                self._tray_icon.setIcon(self.windowIcon())

            tray_menu = QMenu(self)
            self._tray_menu = tray_menu
            self._tray_show_action = QAction("显示窗口", self)
            self._tray_show_action.triggered.connect(self._toggle_window_from_tray)
            tray_menu.addAction(self._tray_show_action)
            self._tray_show_floating_action = QAction("显示悬浮窗", self)
            self._tray_show_floating_action.triggered.connect(self._toggle_floating_widget_from_tray)
            tray_menu.addAction(self._tray_show_floating_action)
            tray_menu.addSeparator()
            action_quit = QAction("退出", self)
            action_quit.triggered.connect(self._quit_app)
            tray_menu.addAction(action_quit)
            tray_menu.aboutToShow.connect(self._refresh_tray_menu)

            self._tray_icon.setContextMenu(tray_menu)
            self._tray_icon.setToolTip(APP_NAME)
            self._tray_icon.activated.connect(self._tray_activated)
            self._refresh_tray_menu()
            self._tray_icon.show()
        except Exception as e:
            logger.warning("系统托盘创建失败: %s", e)
            self._tray_icon = None

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._refresh_tray_menu()

    def _hide_to_tray(self):
        self.hide()
        self._refresh_tray_menu()

    def _toggle_window_from_tray(self):
        if self.isVisible():
            self._hide_to_tray()
            return
        self._show_from_tray()

    def _show_floating_widget_from_tray(self):
        if hasattr(self, '_set_floating_widget_visible'):
            self._set_floating_widget_visible(True)

    def _hide_floating_widget_from_tray(self):
        if hasattr(self, '_set_floating_widget_visible'):
            self._set_floating_widget_visible(False)

    def _toggle_floating_widget_from_tray(self):
        if self._is_floating_widget_visible():
            self._hide_floating_widget_from_tray()
            return
        self._show_floating_widget_from_tray()

    def _quit_app(self):
        if self._tray_icon:
            self._tray_icon.hide()
        QApplication.instance().quit()
