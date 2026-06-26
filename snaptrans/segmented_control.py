"""分段按钮动画控件"""

from PySide6.QtWidgets import QFrame, QWidget, QPushButton
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QPainter, QColor


class AnimatedSegmentedControl(QFrame):
    """带滑动指示器的分段按钮控件"""

    def __init__(self, container: QFrame, btn_left: QPushButton, btn_right: QPushButton):
        super().__init__(container.parent())
        self._container = container
        self._btn_left = btn_left
        self._btn_right = btn_right
        self._accent = "#E8875C"

        # 用 QWidget 做指示器
        self._indicator = QWidget(container)
        self._indicator.lower()
        self._indicator.setStyleSheet(f"background: {self._accent}; border-radius: 8px;")

        # 动画
        self._anim = QPropertyAnimation(self._indicator, b"geometry")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 初始位置
        btn_left.clicked.connect(lambda: self.update_position(animated=True))
        btn_right.clicked.connect(lambda: self.update_position(animated=True))

    def set_accent(self, color: str):
        self._accent = color
        self._indicator.setStyleSheet(f"background: {color}; border-radius: 8px;")

    def update_position(self, animated=True):
        btn = self._btn_left if self._btn_left.isChecked() else self._btn_right
        is_left = btn == self._btn_left
        w = btn.width() or self._btn_left.width()
        h = btn.height() or self._container.height() or 32
        x = 0 if is_left else w
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
