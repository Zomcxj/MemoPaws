"""边框氛围进度条控件"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor, QPen


class BorderGlowWidget(QWidget):
    """边框氛围进度条 — 在目标控件边框绘制呼吸灯效果"""

    def __init__(self, parent=None, accent_color="#E8875C", radius=6):
        super().__init__(parent)
        self._opacity = 0.0
        self._color = QColor(accent_color)
        self._radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._anim = QPropertyAnimation(self, b"glow_opacity")
        self._anim.setDuration(1400)
        self._anim.setLoopCount(-1)
        self._anim.setStartValue(0.0)
        self._anim.setKeyValueAt(0.4, 1.0)
        self._anim.setKeyValueAt(0.6, 1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.hide()

    def get_glow_opacity(self):
        return self._opacity

    def set_glow_opacity(self, v):
        self._opacity = v
        self.update()

    glow_opacity = Property(float, get_glow_opacity, set_glow_opacity)

    def set_accent(self, color: str):
        self._color = QColor(color)

    def start(self):
        self.show()
        self.raise_()
        self._anim.start()

    def stop(self):
        self._anim.stop()
        self.hide()

    def paintEvent(self, event):
        if self._opacity < 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        # 3 层发光
        for i in range(3):
            alpha = int(self._opacity * (80 - i * 25))
            pen = QPen(QColor(self._color.red(), self._color.green(),
                              self._color.blue(), alpha))
            pen.setWidth(1 + i * 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            off = i * 2
            p.drawRoundedRect(r.adjusted(off, off, -off, -off),
                              self._radius, self._radius)
        p.end()
