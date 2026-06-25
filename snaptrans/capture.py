"""截图覆盖层模块"""

from PySide6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QVBoxLayout, QLineEdit, QLabel, QTextEdit
from PySide6.QtCore import Qt, QPoint, QRect, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QGuiApplication, QPixmap, QFont, QPainterPath


class ScreenCaptureOverlay(QWidget):
    """全屏截图覆盖层"""

    captured = Signal(QPixmap, str, str)  # (pixmap, ocr_text, trans_text)
    saved = Signal(QPixmap)
    copy_requested = Signal(QPixmap)
    ocr_requested = Signal(QPixmap)
    translate_requested = Signal(QPixmap)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("截图")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        screen = QGuiApplication.primaryScreen()
        geo = screen.geometry()
        self.setGeometry(geo)
        self.full_pixmap = screen.grabWindow(0)
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.is_selecting = False
        self.selection_done = False
        self._is_dragging = False
        self._drag_offset = None
        self._drag_rect_width = 0
        self._drag_rect_height = 0

        # 闪烁状态
        self._flash_active = False
        self._flash_color = QColor("#d6b36a")
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._on_flash_tick)
        self._flash_phase = 0

        # 保存原始截图（居中前）
        self._original_cropped = None
        self._is_centered = False

        self._init_action_bar()
        self._init_result_panel()

    def _init_action_bar(self):
        self._btn_bar = QWidget(self)
        self._btn_bar.setFixedHeight(32)
        self._btn_bar.hide()

        bar = QHBoxLayout(self._btn_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(4)

        btn_css = """
            QPushButton {
                background: rgba(40,40,40,200); color: #FFF;
                border: 1px solid rgba(255,255,255,0.15); border-radius: 6px;
                padding: 4px 14px; font-size: 12px; font-weight: 600;
            }
            QPushButton:hover { background: rgba(60,60,60,220); }
        """
        input_css = """
            QLineEdit {
                background: rgba(0,0,0,200); color: #FFF;
                border: 1px solid rgba(255,255,255,0.3); border-radius: 4px;
                padding: 2px 6px; font-size: 12px; font-weight: bold;
            }
        """

        self.input_w = QLineEdit()
        self.input_w.setFixedSize(60, 28)
        self.input_w.setStyleSheet(input_css)
        self.input_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_w.returnPressed.connect(self._apply_size)
        bar.addWidget(self.input_w)

        x_label = QLabel("×")
        x_label.setStyleSheet("color: #FFF; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        bar.addWidget(x_label)

        self.input_h = QLineEdit()
        self.input_h.setFixedSize(60, 28)
        self.input_h.setStyleSheet(input_css)
        self.input_h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_h.returnPressed.connect(self._apply_size)
        bar.addWidget(self.input_h)

        self.btn_apply = QPushButton("确定")
        self.btn_apply.setFixedHeight(28)
        self.btn_apply.setStyleSheet(btn_css)
        self.btn_apply.clicked.connect(self._apply_size)
        bar.addWidget(self.btn_apply)

        self.btn_copy = QPushButton("复制")
        self.btn_copy.setFixedHeight(28)
        self.btn_copy.setStyleSheet(btn_css)
        self.btn_copy.clicked.connect(self._on_copy)
        bar.addWidget(self.btn_copy)

        self.btn_save = QPushButton("保存")
        self.btn_save.setFixedHeight(28)
        self.btn_save.setStyleSheet(btn_css)
        self.btn_save.clicked.connect(self._on_save)
        bar.addWidget(self.btn_save)

        self.btn_ocr = QPushButton("OCR")
        self.btn_ocr.setFixedHeight(28)
        self.btn_ocr.setStyleSheet(btn_css)
        self.btn_ocr.clicked.connect(self._on_ocr)
        bar.addWidget(self.btn_ocr)

        self.btn_trans = QPushButton("翻译")
        self.btn_trans.setFixedHeight(28)
        self.btn_trans.setStyleSheet(btn_css)
        self.btn_trans.clicked.connect(self._on_translate)
        bar.addWidget(self.btn_trans)

        # 分隔线
        sep = QLabel("|")
        sep.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 14px; background: transparent; border: none;")
        bar.addWidget(sep)

        # 确认和取消按钮（和其他按钮放一起）
        confirm_btn_css = """
            QPushButton {
                background: rgba(255,255,255,0.9); color: #000;
                border: none; border-radius: 6px;
                padding: 4px 10px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background: rgba(255,255,255,1); }
        """
        self.btn_confirm = QPushButton("确认")
        self.btn_confirm.setFixedHeight(28)
        self.btn_confirm.setStyleSheet(confirm_btn_css)
        self.btn_confirm.setToolTip("确认截图，返回界面")
        self.btn_confirm.clicked.connect(self._on_confirm)
        bar.addWidget(self.btn_confirm)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedHeight(28)
        self.btn_cancel.setStyleSheet(confirm_btn_css)
        self.btn_cancel.setToolTip("退出截图")
        self.btn_cancel.clicked.connect(self._on_cancel)
        bar.addWidget(self.btn_cancel)

    def _init_result_panel(self):
        """右侧结果面板（空白区域拖动，右下角缩放）"""
        self._result_panel = QWidget(self)
        self._result_panel.hide()
        self._result_panel.setFixedSize(316, 416)
        self._result_panel.setStyleSheet("""
            QWidget {
                background: #1a1a1a;
                border: 2px solid #333;
                border-radius: 10px;
            }
        """)
        self._result_panel_dragging = False
        self._result_panel_drag_offset = None

        # 脉动定时器（OCR框）
        self._pulse_ocr_timer = QTimer(self)
        self._pulse_ocr_timer.timeout.connect(self._on_pulse_ocr_tick)
        self._pulse_ocr_phase = 0
        self._pulse_ocr_active = False

        # 脉动定时器（翻译框）
        self._pulse_trans_timer = QTimer(self)
        self._pulse_trans_timer.timeout.connect(self._on_pulse_trans_tick)
        self._pulse_trans_phase = 0
        self._pulse_trans_active = False

        panel_lay = QVBoxLayout(self._result_panel)
        panel_lay.setContentsMargins(12, 10, 12, 10)
        panel_lay.setSpacing(8)

        header_css = "color: #FFFFFF; font-size: 12px; font-weight: 600; background: transparent; border: none;"
        text_css = """
            QTextEdit {
                background: #2a2a2a;
                color: #FFFFFF;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 6px;
                font-size: 12px;
            }
        """
        copy_btn_css = """
            QPushButton {
                background: rgba(255,255,255,0.1);
                color: #FFF;
                border: none;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.2); }
        """

        ocr_header = QHBoxLayout()
        ocr_lbl = QLabel("OCR 结果")
        ocr_lbl.setStyleSheet(header_css)
        ocr_header.addWidget(ocr_lbl)
        ocr_header.addStretch()
        ocr_copy_btn = QPushButton("复制")
        ocr_copy_btn.setStyleSheet(copy_btn_css)
        ocr_copy_btn.clicked.connect(lambda: self._copy_text(self.ocr_text_edit))
        ocr_header.addWidget(ocr_copy_btn)
        panel_lay.addLayout(ocr_header)

        self.ocr_text_edit = QTextEdit()
        self.ocr_text_edit.setMinimumHeight(80)
        self.ocr_text_edit.setReadOnly(True)
        self.ocr_text_edit.setStyleSheet(text_css)
        panel_lay.addWidget(self.ocr_text_edit, 1)

        trans_header = QHBoxLayout()
        trans_lbl = QLabel("翻译结果")
        trans_lbl.setStyleSheet(header_css)
        trans_header.addWidget(trans_lbl)
        trans_header.addStretch()
        trans_copy_btn = QPushButton("复制")
        trans_copy_btn.setStyleSheet(copy_btn_css)
        trans_copy_btn.clicked.connect(lambda: self._copy_text(self.trans_text_edit))
        trans_header.addWidget(trans_copy_btn)
        panel_lay.addLayout(trans_header)

        self.trans_text_edit = QTextEdit()
        self.trans_text_edit.setMinimumHeight(80)
        self.trans_text_edit.setReadOnly(True)
        self.trans_text_edit.setStyleSheet(text_css)
        panel_lay.addWidget(self.trans_text_edit, 1)

        # 底部栏：关闭 + 缩放手柄
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)

        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.1); color: #FFF;
                border: none; border-radius: 6px;
                padding: 6px; font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.2); }
        """)
        close_btn.clicked.connect(lambda: self._result_panel.hide())
        bottom_row.addWidget(close_btn)

        bottom_row.addStretch()

        # 缩放手柄
        resize_handle = QLabel("⤡")
        resize_handle.setFixedSize(16, 16)
        resize_handle.setCursor(Qt.CursorShape.SizeFDiagCursor)
        resize_handle.setStyleSheet("color: #555; font-size: 14px; background: transparent; border: none;")
        resize_handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        resize_handle.installEventFilter(self)
        self._resize_handle = resize_handle
        bottom_row.addWidget(resize_handle)

        panel_lay.addLayout(bottom_row)

        # 缩放状态
        self._resizing = False
        self._resize_start_pos = None
        self._resize_start_geo = None
        self._min_w, self._min_h = 300, 400
        self._max_w, self._max_h = 600, 600

        # 给面板安装事件过滤器（处理空白区域拖动）
        self._result_panel.installEventFilter(self)
        self._result_panel.setMouseTracking(True)

        # 给所有子控件安装事件过滤器
        for child in self._result_panel.findChildren(QWidget):
            child.installEventFilter(self)

    def showEvent(self, event):
        super().showEvent(event)
        self._position_action_bar()

    def _on_result_panel_resized(self):
        """结果框大小变化时，实时保持y中心与截图对齐"""
        self._position_result_to_screenshot()

    def _position_action_bar(self):
        """定位操作栏到选区下方右对齐"""
        rect = self.get_selection_rect()
        if rect.isNull() or rect.width() < 2:
            return
        bar_w = self._btn_bar.sizeHint().width()
        # 右对齐：按钮栏右边与选区右边对齐
        x = rect.right() - bar_w
        y = rect.bottom() + 8
        if y + 40 > self.height():
            y = rect.top() - 40
        self._btn_bar.move(max(10, x), y)
        self._btn_bar.show()
        self._btn_bar.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_btn_bar') and self._btn_bar.isVisible():
            self._position_action_bar()

    def _copy_text(self, text_edit):
        text = text_edit.toPlainText().strip()
        if text:
            QGuiApplication.clipboard().setText(text)

    def show_ocr_result(self, text):
        self.ocr_text_edit.setPlainText(text)
        self.stop_all_pulses()
        self._result_panel.show()
        self._result_panel.raise_()
        self._position_result_to_screenshot()

    def show_translate_result(self, text):
        self.trans_text_edit.setPlainText(text)
        self.stop_all_pulses()
        self._result_panel.show()
        self._result_panel.raise_()
        self._position_result_to_screenshot()

    def _start_pulse_ocr(self):
        """开始OCR框脉动"""
        self._stop_pulse_trans()
        self._pulse_ocr_active = True
        self._pulse_ocr_phase = 0
        self._pulse_ocr_timer.start(80)

    def _stop_pulse_ocr(self):
        """停止OCR框脉动"""
        self._pulse_ocr_active = False
        self._pulse_ocr_timer.stop()
        self._reset_text_edit_style(self.ocr_text_edit)

    def _on_pulse_ocr_tick(self):
        """OCR框脉动回调"""
        import math
        self._pulse_ocr_phase = (self._pulse_ocr_phase + 1) % 40
        brightness = 0.4 + 0.6 * abs(math.sin(self._pulse_ocr_phase * math.pi / 20))
        r = max(0, min(255, int(33 + (100 - 33) * brightness)))
        g = max(0, min(255, int(150 + (200 - 150) * brightness)))
        b = max(0, min(255, int(243 * brightness)))
        self.ocr_text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: #2a2a2a;
                color: #FFFFFF;
                border: 2px solid rgb({r},{g},{b});
                border-radius: 6px;
                padding: 6px;
                font-size: 12px;
            }}
        """)

    def _start_pulse_trans(self):
        """开始翻译框脉动"""
        self._stop_pulse_ocr()
        self._pulse_trans_active = True
        self._pulse_trans_phase = 0
        self._pulse_trans_timer.start(80)

    def _stop_pulse_trans(self):
        """停止翻译框脉动"""
        self._pulse_trans_active = False
        self._pulse_trans_timer.stop()
        self._reset_text_edit_style(self.trans_text_edit)

    def _on_pulse_trans_tick(self):
        """翻译框脉动回调"""
        import math
        self._pulse_trans_phase = (self._pulse_trans_phase + 1) % 40
        brightness = 0.4 + 0.6 * abs(math.sin(self._pulse_trans_phase * math.pi / 20))
        # 绿色 #4CAF50 脉动
        r = max(0, min(255, int(76 + (150 - 76) * brightness)))
        g = max(0, min(255, int(175 + (230 - 175) * brightness)))
        b = max(0, min(255, int(80 + (150 - 80) * brightness)))
        self.trans_text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: #2a2a2a;
                color: #FFFFFF;
                border: 2px solid rgb({r},{g},{b});
                border-radius: 6px;
                padding: 6px;
                font-size: 12px;
            }}
        """)

    def _reset_text_edit_style(self, text_edit):
        """重置单个文本框样式"""
        text_edit.setStyleSheet("""
            QTextEdit {
                background: #2a2a2a;
                color: #FFFFFF;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 6px;
                font-size: 12px;
            }
        """)

    def stop_all_pulses(self):
        """停止所有脉动"""
        self._stop_pulse_ocr()
        self._stop_pulse_trans()

    def _position_result_panel(self):
        rect = self.get_selection_rect()
        pw = 320
        ph = min(400, self.height() - 40)
        x = min(rect.right() + 10, self.width() - pw - 10)
        y = max(10, rect.top())
        self._result_panel.setGeometry(x, y, pw, ph)
        self._result_panel.show()
        self._result_panel.raise_()

    def get_selection_rect(self):
        return QRect(self.start_point, self.end_point).normalized()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.full_pixmap)

        rect = self.get_selection_rect()

        # 暗色遮罩（非居中模式）
        if not self._is_centered:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if rect.isNull() or rect.width() < 2 or rect.height() < 2:
            return

        # 居中模式：用保存的截图绘制 + 灰色圆角边框
        if self._is_centered and self._original_cropped is not None:
            painter.drawPixmap(rect, self._original_cropped)
            pen = QPen(QColor(100, 100, 100), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 6, 6)
        else:
            # 普通模式：绘制选区内容 + 金色边框
            painter.drawPixmap(rect, self.full_pixmap, rect)
            pen = QPen(QColor("#d6b36a"), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect)

            # 尺寸标签
            size_text = f"{rect.width()} × {rect.height()}"
            font = QFont("Inter", 11)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(size_text)
            th = fm.height()
            pad = 6
            lx = rect.right() + 4
            ly = rect.bottom() + 4
            if lx + tw + pad * 2 > self.width():
                lx = rect.left() - tw - pad * 2 - 4
            if ly + th + pad * 2 > self.height():
                ly = rect.bottom() - th - pad * 2 - 4
            bg = QRect(lx, ly, tw + pad * 2, th + pad * 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 180))
            painter.drawRoundedRect(bg, 4, 4)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(lx + pad, ly + pad + fm.ascent(), size_text)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()

        # 点击结果面板区域不处理
        if hasattr(self, '_result_panel') and self._result_panel.isVisible():
            panel_rect = self._result_panel.geometry()
            if panel_rect.contains(pos):
                return

        if self.selection_done:
            rect = self.get_selection_rect().adjusted(-4, -4, 4, 4)
            if rect.contains(pos):
                self._drag_offset = pos - self.start_point
                self._drag_rect_width = self.get_selection_rect().width()
                self._drag_rect_height = self.get_selection_rect().height()
                self._is_dragging = True
                self._btn_bar.hide()
                self.update()
                return
            else:
                self._reset()
                return
        # 新选区时清除居中截图
        self._centered_pixmap = None
        self._original_cropped = None
        self._is_centered = False
        self.start_point = pos
        self.end_point = pos
        self.is_selecting = True
        self._btn_bar.hide()
        self._result_panel.hide()
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._is_dragging:
            self.start_point = pos - self._drag_offset
            self.end_point = QPoint(
                self.start_point.x() + self._drag_rect_width - 1,
                self.start_point.y() + self._drag_rect_height - 1)
            # 同步移动结果框和按钮栏
            if self._is_centered:
                self._position_result_to_screenshot()
                bar_w = self._btn_bar.sizeHint().width()
                rect = self.get_selection_rect()
                self._btn_bar.move(rect.right() - bar_w, rect.bottom() + 10)
            self.update()
        elif self.is_selecting:
            self.end_point = pos
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._is_dragging:
            self._is_dragging = False
            self._drag_offset = None
            self.selection_done = True
            rect = self.get_selection_rect()
            self._show_action_bar(rect)
            self.update()
        elif self.is_selecting:
            self.is_selecting = False
            rect = self.get_selection_rect()
            if rect.width() > 5 and rect.height() > 5:
                self.selection_done = True
                self._show_action_bar(rect)
            self.update()

    def _show_action_bar(self, rect):
        self.input_w.setText(str(rect.width()))
        self.input_h.setText(str(rect.height()))
        bar_w = self._btn_bar.sizeHint().width()
        bar_h = 32
        x = max(0, rect.right() - bar_w)
        y = rect.bottom() + 6
        if y + bar_h > self.height():
            y = rect.bottom() - bar_h - 6
        self._btn_bar.setGeometry(x, y, bar_w, bar_h)
        self._btn_bar.show()
        self._btn_bar.raise_()

    def _apply_size(self):
        try:
            w = max(10, int(self.input_w.text()))
            h = max(10, int(self.input_h.text()))
        except ValueError:
            return
        self.end_point = QPoint(self.start_point.x() + w - 1, self.start_point.y() + h - 1)
        rect = self.get_selection_rect()
        self._show_action_bar(rect)
        self.update()

    def _on_copy(self):
        self.copy_requested.emit(self.full_pixmap.copy(self.get_selection_rect()))
        self.close()

    def _on_save(self):
        self.saved.emit(self.full_pixmap.copy(self.get_selection_rect()))
        self.close()

    def _on_ocr(self):
        """OCR按钮 - 只闪OCR框"""
        if self._original_cropped is None:
            self._original_cropped = self.full_pixmap.copy(self.get_selection_rect())
        if not self._is_centered:
            self._center_selection()
        self._result_panel.show()
        self._result_panel.raise_()
        self._position_result_to_screenshot()
        self._start_pulse_ocr()  # 只闪OCR框
        self.ocr_requested.emit(self._original_cropped)

    def _on_translate(self):
        """翻译按钮 - 只闪翻译框，未识别时先闪OCR再闪翻译"""
        if self._original_cropped is None:
            self._original_cropped = self.full_pixmap.copy(self.get_selection_rect())
        if not self._is_centered:
            self._center_selection()
        self._result_panel.show()
        self._result_panel.raise_()
        self._position_result_to_screenshot()

        has_ocr = hasattr(self, 'ocr_text_edit') and self.ocr_text_edit.toPlainText().strip()
        if has_ocr:
            # 已有OCR结果，只闪翻译框
            self._start_pulse_trans()
        else:
            # 未识别，先闪OCR框，识别完成后再闪翻译框
            self._start_pulse_ocr()
        self.translate_requested.emit(self._original_cropped)

    def _center_selection(self):
        """居中显示截图，结果框在右侧"""
        rect = self.get_selection_rect()
        if rect.isNull() or rect.width() < 2 or rect.height() < 2:
            return

        self._original_cropped = self.full_pixmap.copy(rect)
        self._is_centered = True

        screen_w, screen_h = self.width(), self.height()
        w, h = rect.width(), rect.height()

        # 截图移到屏幕中央偏左
        cx = (screen_w - w) // 2 - 160
        cy = (screen_h - h) // 2
        self.start_point = QPoint(cx, cy)
        self.end_point = QPoint(cx + w - 1, cy + h - 1)

        # 按钮栏：截图下方右对齐
        bar_w = self._btn_bar.sizeHint().width()
        self._btn_bar.move(cx + w - bar_w, cy + h + 10)
        self._btn_bar.show()
        self._btn_bar.raise_()

        # 结果框：固定间距16px，y中线对齐
        self._position_result_to_screenshot()

        self.update()

    def eventFilter(self, obj, event):
        """事件过滤器 - 处理缩放手柄和面板拖动"""
        from PySide6.QtCore import QEvent

        # 缩放手柄
        if obj is self._resize_handle:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._resizing = True
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geo = self._result_panel.geometry()
                return True
            elif event.type() == QEvent.Type.MouseMove and self._resizing:
                delta = event.globalPosition().toPoint() - self._resize_start_pos
                geo = self._resize_start_geo
                new_w = max(self._min_w, min(self._max_w, geo.width() + delta.x()))
                new_h = max(self._min_h, min(self._max_h, geo.height() + delta.y()))
                self._result_panel.setFixedSize(new_w, new_h)
                self._position_result_to_screenshot()
                return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._resizing = False
                self._resize_start_pos = None
                self._resize_start_geo = None
                return True

        # 面板空白区域拖动
        if obj is self._result_panel:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                child = self._result_panel.childAt(event.pos())
                if child is None:
                    self._result_panel_dragging = True
                    self._result_panel_drag_offset = event.globalPosition().toPoint() - self._result_panel.pos()
                    return True
            elif event.type() == QEvent.Type.MouseMove:
                if self._result_panel_dragging and self._result_panel_drag_offset:
                    new_pos = event.globalPosition().toPoint() - self._result_panel_drag_offset
                    self._result_panel.move(new_pos)
                    self._sync_screenshot_to_result()
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if self._result_panel_dragging:
                    self._result_panel_dragging = False
                    self._result_panel_drag_offset = None
                    return True

        return super().eventFilter(obj, event)

    def _position_result_to_screenshot(self):
        """根据截图位置定位结果框（固定x间距，y中心对齐）"""
        rect = self.get_selection_rect()
        if rect.isNull() or not self._result_panel.isVisible():
            return
        panel_geo = self._result_panel.geometry()
        result_x = rect.right() + 16
        result_y = rect.top() + rect.height() // 2 - panel_geo.height() // 2
        if result_x + panel_geo.width() > self.width() - 10:
            result_x = rect.left() - panel_geo.width() - 16
        self._result_panel.move(result_x, result_y)

    def _sync_screenshot_to_result(self):
        """根据结果框位置同步截图框位置"""
        panel_geo = self._result_panel.geometry()
        rect = self.get_selection_rect()
        if rect.isNull():
            return
        w, h = rect.width(), rect.height()
        # 截图框在结果框左侧，间距16px
        new_x = panel_geo.left() - w - 16
        new_y = panel_geo.top() + panel_geo.height() // 2 - h // 2
        self.start_point = QPoint(new_x, new_y)
        self.end_point = QPoint(new_x + w - 1, new_y + h - 1)
        # 同步按钮栏
        bar_w = self._btn_bar.sizeHint().width()
        self._btn_bar.move(new_x + w - bar_w, new_y + h + 10)
        self.update()

    def on_result_received(self):
        """结果返回时停止所有闪烁"""
        self.stop_all_pulses()
        self._stop_flash()

    def _on_confirm(self):
        """确认按钮：截图，返回主界面"""
        if self.selection_done:
            ocr_text = self.ocr_text_edit.toPlainText().strip()
            trans_text = self.trans_text_edit.toPlainText().strip()
            if self._is_centered and self._original_cropped is not None:
                self.captured.emit(self._original_cropped, ocr_text, trans_text)
            else:
                self.captured.emit(self.full_pixmap.copy(self.get_selection_rect()), ocr_text, trans_text)
        self._restore_main_window()
        self.close()

    def _on_cancel(self):
        """取消按钮：直接关闭，不返回主界面"""
        self._stop_flash()
        self.stop_all_pulses()
        self.close()

    def _start_flash(self, color: str):
        """开始闪烁边框（持续到手动停止）"""
        self._flash_active = True
        self._flash_color = QColor(color)
        self._flash_phase = 0
        self._flash_timer.start(80)  # 每80ms更新一次，形成流畅动画

    def _stop_flash(self):
        """停止闪烁"""
        self._flash_active = False
        self._flash_timer.stop()
        self._flash_phase = 0
        self.update()

    def _on_flash_tick(self):
        """闪烁定时器回调 - 亮暗渐变循环"""
        self._flash_phase = (self._flash_phase + 1) % 20  # 0-19 循环
        self.update()

    def _restore_main_window(self):
        """恢复主窗口显示"""
        from PySide6.QtWidgets import QApplication
        for widget in QApplication.topLevelWidgets():
            if widget.windowTitle() == "SnapTrans" or (hasattr(widget, '_is_main_window') and widget._is_main_window):
                widget.showNormal()
                widget.activateWindow()
                return
        # 备用：尝试通过 parent 找到主窗口
        parent = self.parent()
        while parent:
            if hasattr(parent, 'showNormal'):
                parent.showNormal()
                parent.activateWindow()
                return
            parent = parent.parent()

    def _reset(self):
        self.selection_done = False
        self.start_point = QPoint()
        self.end_point = QPoint()
        self._original_cropped = None
        self._is_centered = False
        self._btn_bar.hide()
        self._result_panel.hide()
        self.stop_all_pulses()
        if hasattr(self, 'ocr_text_edit'):
            self.ocr_text_edit.clear()
        if hasattr(self, 'trans_text_edit'):
            self.trans_text_edit.clear()
        self._stop_flash()
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.selection_done:
                self._reset()
            else:
                self._restore_main_window()
                self.close()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.selection_done:
                ocr_text = self.ocr_text_edit.toPlainText().strip()
                trans_text = self.trans_text_edit.toPlainText().strip()
                if self._is_centered and self._original_cropped is not None:
                    self.captured.emit(self._original_cropped, ocr_text, trans_text)
                else:
                    self.captured.emit(self.full_pixmap.copy(self.get_selection_rect()), ocr_text, trans_text)
                self._restore_main_window()
                self.close()
