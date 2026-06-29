"""分段按钮动画控件（支持 N 个按钮）"""

from PySide6.QtWidgets import QFrame, QWidget, QPushButton
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QColor


class AnimatedSegmentedControl(QFrame):
    """带滑动指示器的分段按钮控件"""

    def __init__(self, container: QFrame, *buttons):
        super().__init__(container.parent())
        self._container = container
        self._buttons = list(buttons)
        self._accent = "#E8875C"

        # 用 QWidget 做指示器
        self._indicator = QWidget(container)
        self._indicator.lower()
        self._indicator.setStyleSheet(f"background: {self._accent}; border-radius: 8px;")

        # 动画
        self._anim = QPropertyAnimation(self._indicator, b"geometry")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 内部连接点击信号
        for btn in self._buttons:
            btn.clicked.connect(lambda: self.update_position(animated=True))

    def set_accent(self, color: str):
        self._accent = color
        self._indicator.setStyleSheet(f"background: {color}; border-radius: 8px;")

    def update_position(self, animated=True):
        checked = None
        for btn in self._buttons:
            if btn.isChecked():
                checked = btn
                break
        if checked is None:
            if not self._buttons:
                return
            checked = self._buttons[0]

        w = checked.width() or 80
        h = checked.height() or self._container.height() or 32

        # 通过遍历前面的按钮累计 x 偏移
        x = 0
        for btn in self._buttons:
            if btn is checked:
                break
            x += btn.width()

        # 居中对齐，考虑容器边距
        container_h = self._container.height()
        y = max(0, (container_h - h) // 2)
        target = QRect(x, y, w, h)
        cur = self._indicator.geometry()

        if animated and cur.isValid() and cur != target:
            self._anim.stop()
            self._anim.setStartValue(cur)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._indicator.setGeometry(target)
