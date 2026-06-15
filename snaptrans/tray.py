"""系统托盘逻辑 - TrayMixin"""

import logging

from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu
)
from PySide6.QtGui import QIcon, QAction

from .utils import get_icon_path

logger = logging.getLogger(__name__)


class TrayMixin:
    """系统托盘 Mixin：提供托盘图标、右键菜单、双击显示等功能"""

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
            action_show = QAction("显示窗口", self)
            action_show.triggered.connect(self._show_from_tray)
            tray_menu.addAction(action_show)
            tray_menu.addSeparator()
            action_quit = QAction("退出", self)
            action_quit.triggered.connect(self._quit_app)
            tray_menu.addAction(action_quit)

            self._tray_icon.setContextMenu(tray_menu)
            self._tray_icon.setToolTip("SnapTrans")
            self._tray_icon.activated.connect(self._tray_activated)
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

    def _quit_app(self):
        if self._tray_icon:
            self._tray_icon.hide()
        QApplication.instance().quit()
