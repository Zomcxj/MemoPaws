"""截图覆盖层模块"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QGuiApplication, QPixmap


class ScreenCaptureOverlay(QWidget):
    """全屏截图覆盖层"""
    
    captured = Signal(QPixmap)
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("截图")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        screen = QGuiApplication.primaryScreen()
        self.full_pixmap = screen.grabWindow(0)
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.is_selecting = False
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.full_pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
        
        if self.is_selecting:
            rect = QRect(self.start_point, self.end_point).normalized()
            if not rect.isNull():
                painter.drawPixmap(rect, self.full_pixmap, rect)
                pen = QPen(QColor("#d6b36a"), 2, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                painter.drawRect(rect)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.position().toPoint()
            self.end_point = self.start_point
            self.is_selecting = True
            self.update()
    
    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end_point = event.position().toPoint()
            self.update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.end_point = event.position().toPoint()
            self.is_selecting = False
            rect = QRect(self.start_point, self.end_point).normalized()
            if rect.width() > 5 and rect.height() > 5:
                cropped = self.full_pixmap.copy(rect)
                self.captured.emit(cropped)
            self.close()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
