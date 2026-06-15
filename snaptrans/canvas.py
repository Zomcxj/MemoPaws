"""画布/编辑器模块"""

import cv2
import numpy as np
from PySide6.QtWidgets import QLabel, QTextEdit, QListWidget
from PySide6.QtCore import Qt, QPoint, QSize, QRect, Signal
from PySide6.QtGui import (
    QPixmap, QPainter, QPainterPath, QPen, QColor, QImage, QRegion
)

from .utils import qpixmap_to_numpy, numpy_to_qpixmap
from .themes import DARK, get_canvas_stylesheet


class RoundedTextEdit(QTextEdit):
    """QTextEdit with anti-aliased rounded corners via paintEvent clipping"""
    
    def __init__(self, radius=12, parent=None):
        super().__init__(parent)
        self._radius = radius
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), self._radius, self._radius)
        painter.setClipPath(path)
        painter.fillPath(path, QColor("#1a1a1a"))
        painter.end()
        super().paintEvent(event)
        # overlay rounded border
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#d6b36a"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(1, 1, self.width()-2, self.height()-2, self._radius-1, self._radius-1)
        painter.end()


class RoundedListWidget(QListWidget):
    """QListWidget with proper content clipping to rounded corners"""
    
    def __init__(self, radius=12, parent=None):
        super().__init__(parent)
        self._radius = radius
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_rounded_mask()
    
    def _apply_rounded_mask(self):
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), self._radius, self._radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))


class CanvasWidget(QLabel):
    """画布组件，支持图片显示、缩放、裁剪、绘制"""
    
    selection_changed = Signal(str)
    image_dropped = Signal(str)
    
    def __init__(self):
        super().__init__()
        # 默认 3:2 比例
        self.setMinimumSize(200, 150)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self._theme_dark = True
        self.setStyleSheet(get_canvas_stylesheet(DARK))
        
        self.original_pixmap = None
        self.display_pixmap = None
        self.zoom_level = 1.0
        
        self.current_tool = "select"
        self.drawing = False
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.selection_rect = None
        
        self.pen_color = QColor("#d6b36a")
        self.rect_line_width = 3
        self.mosaic_size = 20
        
        self.undo_stack = []
        self.redo_stack = []
    
    # ── 拖拽支持 ──
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(u.toLocalFile().lower().endswith(('.png','.jpg','.jpeg','.bmp','.gif','.tiff','.webp')) for u in urls):
                event.acceptProposedAction()
                self.setStyleSheet(get_canvas_stylesheet(DARK, is_dragging=True))
    
    def dragLeaveEvent(self, event):
        self.setStyleSheet(get_canvas_stylesheet(DARK))
    
    def dropEvent(self, event):
        self.dragLeaveEvent(event)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(('.png','.jpg','.jpeg','.bmp','.gif','.tiff','.webp')):
                self.image_dropped.emit(path)
                break
    
    def load_pixmap(self, pixmap: QPixmap):
        """加载 QPixmap"""
        if pixmap.isNull():
            return False
        self.original_pixmap = pixmap.copy()
        self.display_pixmap = pixmap.copy()
        self.selection_rect = None
        self.undo_stack = [self.display_pixmap.copy()]
        self.redo_stack = []
        self.zoom_fit()
        return True
    
    def load_image(self, file_path):
        """从文件加载图片"""
        pixmap = QPixmap(file_path)
        return self.load_pixmap(pixmap)
    
    def update_view(self):
        """更新显示"""
        if self.display_pixmap:
            target_size = QSize(
                int(self.display_pixmap.width() * self.zoom_level),
                int(self.display_pixmap.height() * self.zoom_level)
            )
            scaled = self.display_pixmap.scaled(
                target_size, Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled)
        else:
            self.setPixmap(QPixmap())
    
    def set_zoom(self, level):
        """设置缩放级别"""
        self.zoom_level = max(0.1, min(5.0, level))
        self.update_view()
    
    def zoom_in(self):
        """放大"""
        self.set_zoom(self.zoom_level * 1.2)
    
    def zoom_out(self):
        """缩小"""
        self.set_zoom(self.zoom_level / 1.2)
    
    def zoom_fit(self):
        """缩放图片使其完全显示在画布内"""
        if not self.display_pixmap:
            self.zoom_level = 1.0
            self.update_view()
            return
        margin = 10
        w_avail = max(self.width() - 2 * margin, 1)
        h_avail = max(self.height() - 2 * margin, 1)
        scale_w = w_avail / self.display_pixmap.width()
        scale_h = h_avail / self.display_pixmap.height()
        self.zoom_level = min(scale_w, scale_h, 1.0)
        self.update_view()
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_view()
    
    def wheelEvent(self, event):
        """Ctrl+滚轮缩放"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)
    
    def keyPressEvent(self, event):
        """Ctrl+F 自适应窗口"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_F:
            self.zoom_fit()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def set_tool(self, tool):
        """设置当前工具"""
        self.current_tool = tool
    
    def set_pen_color(self, color):
        """设置画笔颜色"""
        self.pen_color = color
    
    def set_rect_line_width(self, width):
        """设置矩形线宽"""
        self.rect_line_width = width
    
    def set_theme(self, dark: bool):
        """设置主题"""
        self._theme_dark = dark
        if dark:
            self.setStyleSheet(get_canvas_stylesheet(DARK))
            self.set_pen_color(QColor("#d6b36a"))
        else:
            from .themes import LIGHT
            self.setStyleSheet(get_canvas_stylesheet(LIGHT))
            self.set_pen_color(QColor("#222222"))
        self.update()
    
    def push_undo(self):
        """保存撤销点"""
        if self.display_pixmap:
            self.undo_stack.append(self.display_pixmap.copy())
            if len(self.undo_stack) > 50:
                self.undo_stack.pop(0)
            self.redo_stack.clear()
    
    def undo(self):
        """撤销"""
        if len(self.undo_stack) > 1:
            current = self.undo_stack.pop()
            self.redo_stack.append(current)
            self.display_pixmap = self.undo_stack[-1].copy()
            self.update_view()
    
    def redo(self):
        """重做"""
        if self.redo_stack:
            pix = self.redo_stack.pop()
            self.undo_stack.append(pix.copy())
            self.display_pixmap = pix.copy()
            self.update_view()
    
    def reset_image(self):
        """重置图片"""
        if self.original_pixmap:
            self.display_pixmap = self.original_pixmap.copy()
            self.selection_rect = None
            self.undo_stack = [self.display_pixmap.copy()]
            self.redo_stack = []
            self.update_view()
    
    def map_to_pixmap(self, pos):
        """将鼠标位置映射到图片坐标"""
        if not self.display_pixmap or not self.pixmap():
            return QPoint(-1, -1)
        
        label_size = self.size()
        pixmap_size = self.pixmap().size()
        
        x_offset = (label_size.width() - pixmap_size.width()) / 2
        y_offset = (label_size.height() - pixmap_size.height()) / 2
        
        x = pos.x() - x_offset
        y = pos.y() - y_offset
        
        if x < 0 or y < 0 or x > pixmap_size.width() or y > pixmap_size.height():
            return QPoint(-1, -1)
        
        scale_x = self.display_pixmap.width() / pixmap_size.width()
        scale_y = self.display_pixmap.height() / pixmap_size.height()
        
        return QPoint(int(x * scale_x), int(y * scale_y))
    
    def mousePressEvent(self, event):
        if not self.display_pixmap:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            point = self.map_to_pixmap(event.position().toPoint())
            if point.x() < 0 or point.y() < 0:
                return
            
            self.drawing = True
            self.start_point = point
            self.end_point = point
            
            if self.current_tool in ["rect", "select"]:
                self.push_undo()
    
    def mouseMoveEvent(self, event):
        if not self.display_pixmap or not self.drawing:
            return
        
        point = self.map_to_pixmap(event.position().toPoint())
        if point.x() < 0 or point.y() < 0:
            return
        
        if self.current_tool == "rect":
            temp = self.undo_stack[-1].copy()
            painter = QPainter(temp)
            pen = QPen(self.pen_color, self.rect_line_width, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            rect = QRect(self.start_point, point).normalized()
            painter.drawRect(rect)
            painter.end()
            self.display_pixmap = temp
            self.update_view()
        
        elif self.current_tool == "select":
            temp = self.undo_stack[-1].copy()
            painter = QPainter(temp)
            pen = QPen(QColor("#d6b36a"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            rect = QRect(self.start_point, point).normalized()
            painter.drawRect(rect)
            painter.end()
            self.display_pixmap = temp
            self.update_view()
        
        self.end_point = point
    
    def mouseReleaseEvent(self, event):
        if not self.display_pixmap:
            return
        if event.button() == Qt.MouseButton.LeftButton and self.drawing:
            self.drawing = False
            point = self.map_to_pixmap(event.position().toPoint())
            if point.x() < 0 or point.y() < 0:
                return
            
            if self.current_tool == "select":
                self.push_undo()
                rect = QRect(self.start_point, point).normalized()
                if rect.width() > 5 and rect.height() > 5:
                    self.display_pixmap = self.display_pixmap.copy(rect)
                    self.selection_rect = None
                    self.update_view()
                    text = f"已裁剪至：{rect.width()}×{rect.height()}"
                    self.selection_changed.emit(text)
                else:
                    text = "选区太小，未裁剪"
                    self.selection_changed.emit(text)
    
    def apply_mosaic_at(self, point):
        """在指定位置应用马赛克"""
        if not self.display_pixmap:
            return
        arr = qpixmap_to_numpy(self.display_pixmap)
        x, y = point.x(), point.y()
        size = max(8, self.mosaic_size)
        
        x1 = max(0, x - size // 2)
        y1 = max(0, y - size // 2)
        x2 = min(arr.shape[1], x1 + size)
        y2 = min(arr.shape[0], y1 + size)
        
        block = arr[y1:y2, x1:x2]
        if block.size == 0:
            return
        
        small = cv2.resize(block, (max(1, (x2-x1)//6), max(1, (y2-y1)//6)), interpolation=cv2.INTER_LINEAR)
        mosaic = cv2.resize(small, (x2-x1, y2-y1), interpolation=cv2.INTER_NEAREST)
        arr[y1:y2, x1:x2] = mosaic
        self.display_pixmap = numpy_to_qpixmap(arr)
    
    def get_current_qimage(self):
        """获取当前 QImage"""
        if not self.display_pixmap:
            return None
        return self.display_pixmap.toImage()
    
    def get_selected_image(self):
        """获取选区图片"""
        if not self.display_pixmap:
            return None
        if self.selection_rect and self.selection_rect.width() > 5 and self.selection_rect.height() > 5:
            return self.display_pixmap.copy(self.selection_rect)
        return self.display_pixmap.copy()
    
    def export_image(self, file_path):
        """导出图片"""
        if self.display_pixmap:
            self.display_pixmap.save(file_path)
