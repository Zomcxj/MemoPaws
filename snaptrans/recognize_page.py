"""贴图识别页面模块"""

import os
import re
import cv2
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QSplitter, QFrame, QSlider, QSizePolicy, QListWidget,
    QListWidgetItem, QComboBox, QFileDialog, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, QTimer, QThread, QSize, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QIcon, QPixmap, QShortcut, QKeySequence, QPainter, QColor, QPen
from PySide6.QtSvg import QSvgRenderer

from .themes import (
    DARK, LIGHT, ThemeColors,
    get_text_edit_stylesheet, get_status_list_stylesheet,
    get_clear_history_stylesheet,
)
from .ocr import OCRManager, MODE_LOCAL, MODE_CLOUD
from .translator import SimpleTranslator
from .canvas import CanvasWidget
from .history import HistoryManager
from .capture import ScreenCaptureOverlay
from .utils import qpixmap_to_numpy, numpy_to_qpixmap, ensure_config_dir
from .ocr_translate import OCRTranslateMixin


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


def _load_svg_icon(svg_path: str, size: int = 20, color: str = None):
    """加载 SVG 图标"""
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_data = f.read()
    if color:
        svg_data = svg_data.replace('currentColor', color)
        svg_data = re.sub(r'fill="#ccc"', f'fill="{color}"', svg_data)
    renderer = QSvgRenderer(svg_data.encode("utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


class RecognizePage(OCRTranslateMixin, QWidget):
    def __init__(self, parent, *,
                 get_config_path,
                 get_theme,
                 is_dark,
                 get_icons_dir,
                 get_icon_clr,
                 ocr_manager,
                 translator,
                 on_append_status,
                 on_switch_to_page,
                 ):
        super().__init__(parent)
        self._get_config_path = get_config_path
        self._get_theme = get_theme
        self._is_dark = is_dark
        self._get_icons_dir = get_icons_dir
        self._get_icon_clr = get_icon_clr
        self.ocr_manager = ocr_manager
        self.translator = translator
        self._on_append_status = on_append_status
        self._on_switch_to_page = on_switch_to_page

        self.ocr_thread = None
        self.ocr_worker = None
        self.ocr_running = False
        self.translate_thread = None
        self.translate_worker = None
        self.translate_target = "英文"
        self.history_manager = HistoryManager(get_config_path)
        self.history_data = self.history_manager.load()

        self.canvas = None
        self.capture_overlay = None
        self._ocr_pending_callback = None
        self._ocr_mode_name = ""
        self._translate_source_text = ""
        self._translate_mode = ""
        self._current_lang = "zh"

        self._build_ui()

        if hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(lambda _: self.apply_theme())
        if hasattr(parent, 'language_changed'):
            parent.language_changed.connect(self.apply_language)

    def _show_message(self, icon, title, text):
        """Show themed message box (delegates to parent window)"""
        w = self.window()
        if hasattr(w, 'show_themed_message'):
            w.show_themed_message(icon, title, text)
        else:
            QMessageBox(icon, title, text, QMessageBox.StandardButton.Ok, self).exec()

    def _build_ui(self):
        """构建识别页 UI（原 _create_recognize_page）"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)

        _icons_dir = self._get_icons_dir()
        _icon_clr = self._get_icon_clr()
        _t = self._get_theme()

        # 工具栏
        toolbar = QHBoxLayout()
        _tb_btn_ss = "QPushButton { padding: 4px 12px; font-size: 13px; }"

        self.btn_open = QPushButton("导入")
        self.btn_open.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "import.svg"), 16, _icon_clr)))
        self.btn_open.setIconSize(QSize(16, 16))
        self.btn_open.setMinimumWidth(80)
        self.btn_open.setStyleSheet(_tb_btn_ss)
        self.btn_open.clicked.connect(self.open_image)
        toolbar.addWidget(self.btn_open)

        self.btn_capture = QPushButton("截图")
        self.btn_capture.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "capture.svg"), 16, _icon_clr)))
        self.btn_capture.setIconSize(QSize(16, 16))
        self.btn_capture.setMinimumWidth(80)
        self.btn_capture.setStyleSheet(_tb_btn_ss)
        self.btn_capture.clicked.connect(self.start_capture)
        toolbar.addWidget(self.btn_capture)

        self.tool_select = QPushButton("裁剪")
        self.tool_select.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "crop.svg"), 16, _icon_clr)))
        self.tool_select.setIconSize(QSize(16, 16))
        self.tool_select.setMinimumWidth(80)
        self.tool_select.setStyleSheet(_tb_btn_ss)
        self.tool_select.clicked.connect(lambda: self.set_tool("select"))
        toolbar.addWidget(self.tool_select)

        self.tool_rect = QPushButton("矩形")
        self.tool_rect.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "rect.svg"), 16, _icon_clr)))
        self.tool_rect.setIconSize(QSize(16, 16))
        self.tool_rect.setMinimumWidth(80)
        self.tool_rect.setStyleSheet(_tb_btn_ss)
        self.tool_rect.clicked.connect(lambda: self.set_tool("rect"))
        toolbar.addWidget(self.tool_rect)

        self.rect_slider = QSlider(Qt.Orientation.Horizontal)
        self.rect_slider.setRange(1, 12)
        self.rect_slider.setValue(3)
        self.rect_slider.setFixedWidth(80)
        self.rect_slider.valueChanged.connect(self.change_rect_width)
        toolbar.addWidget(QLabel("线宽"))
        toolbar.addWidget(self.rect_slider)
        self.rect_value_label = QLabel("3")
        self.rect_value_label.setStyleSheet("border:none; background:transparent; min-width:18px;")
        toolbar.addWidget(self.rect_value_label)

        # 灰度/二值化/重置 紧跟线宽后面
        toolbar.addSpacing(8)
        self.btn_pre_gray = QPushButton("灰度")
        self.btn_pre_gray.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "grayscale.svg"), 16, _icon_clr)))
        self.btn_pre_gray.setIconSize(QSize(16, 16))
        self.btn_pre_gray.setMinimumWidth(80)
        self.btn_pre_gray.setStyleSheet(_tb_btn_ss)
        self.btn_pre_gray.clicked.connect(lambda: self.preprocess("gray"))
        toolbar.addWidget(self.btn_pre_gray)

        self.btn_pre_binary = QPushButton("二值化")
        self.btn_pre_binary.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "binary.svg"), 16, _icon_clr)))
        self.btn_pre_binary.setIconSize(QSize(16, 16))
        self.btn_pre_binary.setMinimumWidth(80)
        self.btn_pre_binary.setStyleSheet(_tb_btn_ss)
        self.btn_pre_binary.clicked.connect(lambda: self.preprocess("binary"))
        toolbar.addWidget(self.btn_pre_binary)

        self.btn_reset = QPushButton("重置")
        self.btn_reset.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "reset.svg"), 16, _icon_clr)))
        self.btn_reset.setIconSize(QSize(16, 16))
        self.btn_reset.setMinimumWidth(80)
        self.btn_reset.setStyleSheet(_tb_btn_ss)
        self.btn_reset.clicked.connect(self.reset_image)
        toolbar.addWidget(self.btn_reset)

        self.btn_clear = QPushButton("清空")
        self.btn_clear.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "clear.svg"), 16, _icon_clr)))
        self.btn_clear.setIconSize(QSize(16, 16))
        self.btn_clear.setMinimumWidth(80)
        self.btn_clear.setStyleSheet(_tb_btn_ss)
        self.btn_clear.clicked.connect(self.clear_image)
        toolbar.addWidget(self.btn_clear)

        self.btn_save_image = QPushButton("保存图片")
        self.btn_save_image.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "save.svg"), 16, _icon_clr)))
        self.btn_save_image.setIconSize(QSize(16, 16))
        self.btn_save_image.setMinimumWidth(100)
        self.btn_save_image.setStyleSheet(_tb_btn_ss)
        self.btn_save_image.clicked.connect(self.export_image)
        toolbar.addWidget(self.btn_save_image)

        toolbar.addStretch()

        # One Punch 按钮（工具栏最右）
        self.btn_one_click = QPushButton("One Punch")
        self.btn_one_click.setObjectName("accent")
        self.btn_one_click.setMinimumWidth(80)
        self.btn_one_click.setStyleSheet(f"""
            QPushButton#accent {{
                background: {_t.accent};
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 4px 12px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#accent:hover {{ background: {_t.accent_hover}; }}
        """)
        self.btn_one_click.clicked.connect(self._run_one_click)
        toolbar.addWidget(self.btn_one_click)

        layout.addLayout(toolbar)

        # 主内容区
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setChildrenCollapsible(False)

        # 左：图片（画布）+ 操作历史（下方）— 用 QSplitter 可拖拽调整比例
        canvas_history_splitter = QSplitter(Qt.Orientation.Vertical)
        canvas_history_splitter.setHandleWidth(6)
        canvas_history_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")
        canvas_history_splitter.setChildrenCollapsible(False)

        canvas_frame = QFrame()
        canvas_frame.setStyleSheet("QFrame{border:none;background:transparent;}")
        canvas_layout = QVBoxLayout(canvas_frame)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        self.canvas = CanvasWidget()
        self.canvas.image_dropped.connect(self._on_image_dropped)
        canvas_layout.addWidget(self.canvas)
        canvas_history_splitter.addWidget(canvas_frame)

        # 操作历史（图片下方）— 带边框容器
        _t_hist = self._get_theme()
        history_frame = QFrame()
        history_frame.setObjectName("historyFrame")
        history_frame.setStyleSheet(f"""
            QFrame#historyFrame {{
                background: {_t_hist.bg_panel};
                border: 1px solid {_t_hist.border_subtle};
                border-radius: 8px;
            }}
        """)
        history_frame.setMaximumHeight(330)

        history_vbox = QVBoxLayout(history_frame)
        history_vbox.setContentsMargins(10, 4, 10, 4)
        history_vbox.setSpacing(2)

        history_row = QHBoxLayout()
        history_row.setSpacing(0)
        history_row.setContentsMargins(0, 0, 0, 0)
        self.history_label = QLabel("操作历史")
        self.history_label.setStyleSheet(f"font-size:12px; font-weight:bold; color:{_t_hist.accent}; border:none; background:transparent;")
        self.history_label.setFixedHeight(20)
        history_row.addWidget(self.history_label)
        history_row.addStretch()
        self.btn_clear_history = QPushButton("清空")
        self.btn_clear_history.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "clear.svg"), 16, _icon_clr)))
        self.btn_clear_history.setIconSize(QSize(16, 16))
        self.btn_clear_history.setStyleSheet(get_clear_history_stylesheet(_t_hist))
        self.btn_clear_history.clicked.connect(self.clear_history)
        history_row.addWidget(self.btn_clear_history)
        history_vbox.addLayout(history_row)

        self.status_list = QListWidget()
        self.status_list.setStyleSheet(get_status_list_stylesheet(_t_hist))
        self.status_list.setMinimumHeight(120)
        self.status_list.setMaximumHeight(280)
        self.status_list.itemClicked.connect(self._on_history_clicked)
        self.status_list.itemDoubleClicked.connect(self._on_history_clicked)
        self.status_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.status_list.customContextMenuRequested.connect(self._on_history_context_menu)
        history_vbox.addWidget(self.status_list)

        history_tip = QLabel("点击恢复 | 右键删除")
        _init_tip2_ss = f"font-size:11px; color:{_t_hist.text_muted}; border:none; background:transparent;"
        history_tip.setStyleSheet(_init_tip2_ss)
        self._history_tip = history_tip
        history_vbox.addWidget(history_tip)

        canvas_history_splitter.addWidget(history_frame)
        canvas_history_splitter.setSizes([500, 160])  # 初始比例：图片区大，历史区小

        self.shortcut_fit = QShortcut(QKeySequence("Ctrl+F"), self.window())
        self.shortcut_fit.activated.connect(self.canvas.zoom_fit)

        # 右：识别/翻译（两个带边框容器）
        result_container = QFrame()
        result_container.setStyleSheet("QFrame{border:none;background:transparent;}")
        result_container_layout = QVBoxLayout(result_container)
        result_container_layout.setContentsMargins(0, 0, 0, 0)
        result_container_layout.setSpacing(8)

        # ── 识别结果容器 ──
        ocr_frame = QFrame()
        ocr_frame.setObjectName("ocrFrame")
        ocr_frame.setStyleSheet(f"""
            QFrame#ocrFrame {{
                background: {_t.bg_panel};
                border: 1px solid {_t.border_subtle};
                border-radius: 8px;
            }}
        """)
        ocr_vbox = QVBoxLayout(ocr_frame)
        ocr_vbox.setContentsMargins(10, 8, 10, 8)
        ocr_vbox.setSpacing(6)

        ocr_header = QHBoxLayout()
        ocr_header.setSpacing(0)
        self.result_label_ocr = QLabel("识别结果")
        self.result_label_ocr.setStyleSheet(f"font-size:13px; font-weight:bold; color:{_t.accent}; border:none; background:transparent;")
        ocr_header.addWidget(self.result_label_ocr)
        ocr_header.addStretch()
        ocr_vbox.addLayout(ocr_header)

        ocr_btn_row = QHBoxLayout()
        ocr_btn_row.setSpacing(4)
        _ocr_btn_ss = f"QPushButton {{ padding: 4px 12px; font-size: 13px; }}"
        self.btn_ocr_local = QPushButton("本地识别")
        self.btn_ocr_local.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "local-ocr.svg"), 16, _icon_clr)))
        self.btn_ocr_local.setIconSize(QSize(16, 16))
        self.btn_ocr_local.setFixedHeight(28)
        self.btn_ocr_local.setStyleSheet(_ocr_btn_ss)
        self.btn_ocr_local.clicked.connect(lambda: self._run_ocr_local())
        ocr_btn_row.addWidget(self.btn_ocr_local)
        self.btn_ocr_ai = QPushButton("AI识别")
        self.btn_ocr_ai.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "ai-ocr.svg"), 16, _icon_clr)))
        self.btn_ocr_ai.setIconSize(QSize(16, 16))
        self.btn_ocr_ai.setFixedHeight(28)
        self.btn_ocr_ai.setStyleSheet(_ocr_btn_ss)
        self.btn_ocr_ai.clicked.connect(lambda: self._run_ocr_ai())
        ocr_btn_row.addWidget(self.btn_ocr_ai)
        self.translate_source_combo = QComboBox()
        self.translate_source_combo.addItems(["中文", "英文", "日文", "韩文", "法文", "德文", "西班牙文", "俄文"])
        self.translate_source_combo.setCurrentText("中文")
        self.translate_source_combo.setFixedHeight(28)
        ocr_btn_row.addWidget(self.translate_source_combo)
        ocr_vbox.addLayout(ocr_btn_row)

        self.ocr_text = QTextEdit()
        self.ocr_text.setStyleSheet(get_text_edit_stylesheet(_t))
        self.ocr_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.ocr_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.ocr_text.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
        ocr_vbox.addWidget(self.ocr_text, 1)

        result_container_layout.addWidget(ocr_frame, 1)

        # ── 翻译结果容器 ──
        trans_frame = QFrame()
        trans_frame.setObjectName("transFrame")
        trans_frame.setStyleSheet(f"""
            QFrame#transFrame {{
                background: {_t.bg_panel};
                border: 1px solid {_t.border_subtle};
                border-radius: 8px;
            }}
        """)
        trans_vbox = QVBoxLayout(trans_frame)
        trans_vbox.setContentsMargins(10, 8, 10, 8)
        trans_vbox.setSpacing(6)

        trans_header = QHBoxLayout()
        trans_header.setSpacing(0)
        self.result_label_trans = QLabel("翻译结果")
        self.result_label_trans.setStyleSheet(f"font-size:13px; font-weight:bold; color:{_t.accent}; border:none; background:transparent;")
        trans_header.addWidget(self.result_label_trans)
        trans_header.addStretch()
        trans_vbox.addLayout(trans_header)

        trans_btn_row = QHBoxLayout()
        trans_btn_row.setSpacing(4)
        _trans_btn_ss = f"QPushButton {{ padding: 4px 12px; font-size: 13px; }}"
        self.btn_trans_online = QPushButton("在线翻译")
        self.btn_trans_online.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "online-trans.svg"), 16, _icon_clr)))
        self.btn_trans_online.setIconSize(QSize(16, 16))
        self.btn_trans_online.setFixedHeight(28)
        self.btn_trans_online.setStyleSheet(_trans_btn_ss)
        self.btn_trans_online.clicked.connect(lambda: self._run_translate_online())
        trans_btn_row.addWidget(self.btn_trans_online)
        self.btn_trans_ai = QPushButton("AI翻译")
        self.btn_trans_ai.setIcon(QIcon(_load_svg_icon(os.path.join(_icons_dir, "ai-ocr.svg"), 16, _icon_clr)))
        self.btn_trans_ai.setIconSize(QSize(16, 16))
        self.btn_trans_ai.setFixedHeight(28)
        self.btn_trans_ai.setStyleSheet(_trans_btn_ss)
        self.btn_trans_ai.clicked.connect(lambda: self._run_translate_ai())
        trans_btn_row.addWidget(self.btn_trans_ai)
        self.translate_target_combo = QComboBox()
        self.translate_target_combo.addItems(["英文", "中文", "日文", "韩文", "法文", "德文", "西班牙文", "俄文"])
        self.translate_target_combo.setCurrentText(self.translate_target)
        self.translate_target_combo.currentTextChanged.connect(self._on_translate_target_changed)
        self.translate_target_combo.setFixedHeight(28)
        trans_btn_row.addWidget(self.translate_target_combo)
        trans_vbox.addLayout(trans_btn_row)

        self.translate_text = QTextEdit()
        self.translate_text.setReadOnly(True)
        self.translate_text.setStyleSheet(get_text_edit_stylesheet(_t))
        self.translate_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.translate_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.translate_text.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
        trans_vbox.addWidget(self.translate_text, 1)

        result_container_layout.addWidget(trans_frame, 1)

        # 边框氛围进度条 — 覆盖在 ocr_text / translate_text 上
        self._glow_ocr = BorderGlowWidget(self.ocr_text, accent_color=_t.accent)
        self._glow_trans = BorderGlowWidget(self.translate_text, accent_color=_t.accent)
        self.ocr_text.installEventFilter(self)
        self.translate_text.installEventFilter(self)

        content_splitter.addWidget(canvas_history_splitter)
        content_splitter.addWidget(result_container)
        content_splitter.setSizes([700, 400])
        content_splitter.setHandleWidth(6)
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 2)
        content_splitter.setStyleSheet("QSplitter { background: transparent; } QSplitter::handle { background: transparent; }")

        layout.addWidget(content_splitter, 1)

    def eventFilter(self, obj, event):
        """跟踪 ocr_text / translate_text 尺寸变化，同步 glow 覆盖层"""
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.Resize:
            if obj is self.ocr_text:
                self._glow_ocr.setGeometry(0, 0, obj.width(), obj.height())
            elif obj is self.translate_text:
                self._glow_trans.setGeometry(0, 0, obj.width(), obj.height())
        return super().eventFilter(obj, event)

    # ══════════════════════════════════════════════
    #  工具 / 画布操作
    # ══════════════════════════════════════════════

    def set_tool(self, tool):
        self.canvas.set_tool(tool)

    def change_rect_width(self, value):
        self.canvas.set_rect_line_width(value)
        self.rect_value_label.setText(str(value))

    def open_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self.window(), "选择图片", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            ok = self.canvas.load_image(file_path)
            if not ok:
                self._show_message(QMessageBox.Icon.Warning, "错误", "图片加载失败")

    def start_capture(self):
        w = self.window()
        w.showMinimized()
        w.hide()
        QTimer.singleShot(100, self._start_capture_overlay)

    def _start_capture_overlay(self):
        self.capture_overlay = ScreenCaptureOverlay()
        self.capture_overlay.captured.connect(self.on_capture_finished)
        self.capture_overlay.copy_requested.connect(self._on_capture_copy)
        self.capture_overlay.saved.connect(self._on_capture_save)
        self.capture_overlay.ocr_requested.connect(self._on_capture_ocr)
        self.capture_overlay.translate_requested.connect(self._on_capture_translate)
        self.capture_overlay.showFullScreen()
        self.capture_overlay.activateWindow()
        self.capture_overlay.raise_()

    def on_capture_finished(self, pixmap, ocr_text="", trans_text=""):
        w = self.window()
        w.showNormal()
        QApplication.processEvents()
        self.canvas.load_pixmap(pixmap)
        # 同步 OCR/翻译结果到界面
        if ocr_text:
            self.ocr_text.setPlainText(ocr_text)
        if trans_text:
            self.translate_text.setPlainText(trans_text)

    def _on_capture_copy(self, pixmap):
        """截图覆盖层：复制图片到剪切板，恢复主窗口但不抢焦点"""
        QApplication.clipboard().setImage(pixmap.toImage())
        self.window().showMinimized()

    def _on_capture_save(self, pixmap):
        """截图覆盖层：保存图片到文件，恢复主窗口但不抢焦点"""
        file_path, _ = QFileDialog.getSaveFileName(
            None, "保存截图", "screenshot.png", "PNG Files (*.png)")
        if file_path:
            pixmap.save(file_path, "PNG")
        self.window().showMinimized()

    def _on_capture_ocr(self, pixmap):
        """截图覆盖层：OCR 识别，结果显示在覆盖层"""
        # 用线程异步执行，不阻塞 UI
        import numpy as np
        from PySide6.QtCore import QThread, Signal

        class OCRWorker(QThread):
            finished = Signal(str)
            def __init__(self, ocr_manager, pixmap):
                super().__init__()
                self.ocr_manager = ocr_manager
                self.pixmap = pixmap
            def run(self):
                arr = qpixmap_to_numpy(self.pixmap)
                text = self.ocr_manager.run_ocr(arr)
                self.finished.emit(text or "(无识别结果)")

        def on_done(text):
            if hasattr(self, 'capture_overlay') and self.capture_overlay:
                self.capture_overlay.show_ocr_result(text)
                self.capture_overlay.on_result_received()

        self._ocr_worker = OCRWorker(self.ocr_manager, pixmap)
        self._ocr_worker.finished.connect(on_done)
        self._ocr_worker.start()

    def _on_capture_translate(self, pixmap):
        """截图覆盖层：先 OCR 再翻译，结果显示在覆盖层"""
        from PySide6.QtCore import QThread, Signal

        class TranslateWorker(QThread):
            ocr_done = Signal(str)
            translate_done = Signal(str, str)  # (ocr_text, translated)
            def __init__(self, ocr_manager, translator, target, pixmap):
                super().__init__()
                self.ocr_manager = ocr_manager
                self.translator = translator
                self.target = target
                self.pixmap = pixmap
            def run(self):
                import numpy as np
                arr = qpixmap_to_numpy(self.pixmap)
                text = self.ocr_manager.run_ocr(arr)
                if not text:
                    self.translate_done.emit("", "(无识别结果)")
                    return
                self.ocr_done.emit(text)
                result = self.translator.translate(text, target_lang=self.target)
                self.translate_done.emit(text, result or "(翻译失败)")

        def on_ocr_done(text):
            if hasattr(self, 'capture_overlay') and self.capture_overlay:
                self.capture_overlay.show_ocr_result(text)
                # OCR完成，切换到翻译框脉动
                self.capture_overlay.stop_all_pulses()
                self.capture_overlay._start_pulse_trans()

        def on_translate_done(ocr_text, translated):
            if hasattr(self, 'capture_overlay') and self.capture_overlay:
                if ocr_text:
                    self.capture_overlay.show_ocr_result(ocr_text)
                self.capture_overlay.show_translate_result(translated)
                self.capture_overlay.on_result_received()

        target = getattr(self, 'translate_target', '英文')
        self._translate_worker = TranslateWorker(self.ocr_manager, self.translator, target, pixmap)
        self._translate_worker.ocr_done.connect(on_ocr_done)
        self._translate_worker.translate_done.connect(on_translate_done)
        self._translate_worker.start()

    def _on_image_dropped(self, file_path):
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            self.canvas.load_pixmap(pixmap)

    def preprocess(self, mode):
        if not self.canvas.display_pixmap:
            self._show_message(QMessageBox.Icon.Information, "提示", "请先导入图片")
            return
        self.canvas.push_undo()
        arr = qpixmap_to_numpy(self.canvas.display_pixmap)
        if mode == "gray":
            gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
            arr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        elif mode == "binary":
            gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            arr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        self.canvas.display_pixmap = numpy_to_qpixmap(arr)
        self.canvas.update_view()

    # ══════════════════════════════════════════════
    #  导出 / 重置
    # ══════════════════════════════════════════════

    def export_text(self):
        file_path, _ = QFileDialog.getSaveFileName(self.window(), "导出文本", "snaptrans_result.txt", "Text Files (*.txt)")
        if file_path:
            content = "识别结果：\n" + self.ocr_text.toPlainText() + "\n\n翻译结果：\n" + self.translate_text.toPlainText()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

    def export_image(self):
        if not self.canvas.display_pixmap:
            self._show_message(QMessageBox.Icon.Information, "提示", "没有可导出的图片")
            return
        file_path, _ = QFileDialog.getSaveFileName(self.window(), "导出图片", "snaptrans_output.png", "PNG Files (*.png)")
        if file_path:
            self.canvas.export_image(file_path)

    def reset_image(self):
        self.canvas.reset_image()

    def clear_image(self):
        """清空图片和识别结果"""
        self.canvas.original_pixmap = None
        self.canvas.display_pixmap = None
        self.canvas.update_view()
        self.ocr_text.clear()
        self.translate_text.clear()

    # ══════════════════════════════════════════════
    #  历史记录
    # ══════════════════════════════════════════════

    def load_history(self):
        return self.history_manager.load()

    def save_history(self):
        self.history_manager.save()

    def add_history_record(self, action_type, text, **extra):
        self.history_manager.add_record(action_type, text, **extra)
        self.history_manager.update_status_list(self.status_list)

    def clear_history(self):
        self.history_manager.clear()
        self.status_list.clear()

    def _update_status_list(self):
        self.history_manager.update_status_list(self.status_list)

    def _on_history_clicked(self, item: QListWidgetItem):
        self.history_manager.on_history_clicked(
            item,
            self.ocr_text,
            self.translate_text,
            self.window().nav_sidebar if hasattr(self.window(), 'nav_sidebar') else None,
            None,
            self._on_switch_to_page,
        )

    def _on_history_context_menu(self, pos):
        """右键菜单：删除单条历史记录"""
        item = self.status_list.itemAt(pos)
        if not item:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        lang = self._current_lang
        delete_action = menu.addAction("删除" if lang == "zh" else "Delete")
        clear_action = menu.addAction("清空全部" if lang == "zh" else "Clear All")
        action = menu.exec(self.status_list.mapToGlobal(pos))
        if action == delete_action:
            row = self.status_list.row(item)
            self.history_manager.delete_record(row)
            self.status_list.takeItem(row)
        elif action == clear_action:
            self.clear_history()

    def _append_status(self, msg: str):
        try:
            self.history_manager.add_record("系统", msg)
            self.history_manager.update_status_list(self.status_list)
        except Exception:
            pass

    # ══════════════════════════════════════════════
    #  主题 / 语言
    # ══════════════════════════════════════════════

    def apply_theme(self):
        """刷新主题样式（被 MainWindow._apply_theme 调用）"""
        t = self._get_theme()
        self.ocr_text.setStyleSheet(get_text_edit_stylesheet(t))
        self.translate_text.setStyleSheet(get_text_edit_stylesheet(t))
        heading_color = t.accent
        self.result_label_ocr.setStyleSheet(f"font-size:13px; font-weight:bold; color:{heading_color}; border:none; background:transparent;")
        self.result_label_trans.setStyleSheet(f"font-size:13px; font-weight:bold; color:{heading_color}; border:none; background:transparent;")
        self.history_label.setStyleSheet(f"font-size:13px; font-weight:bold; color:{heading_color}; border:none;")
        self.status_list.setStyleSheet(get_status_list_stylesheet(t))
        # 刷新操作历史容器
        _hist_frame = self.status_list.parentWidget()
        if _hist_frame and _hist_frame != self:
            _hist_frame.setStyleSheet(f"QFrame {{ background: {t.bg_panel}; border: 1px solid {t.border_subtle}; border-radius: 8px; }}")
            for child in _hist_frame.findChildren(QLabel):
                if child == self.history_label:
                    continue
                child.setStyleSheet(f"font-size:11px; color:{t.text_muted}; border:none; background:transparent;")
        # 刷新识别结果容器
        _ocr_frame = self.ocr_text.parentWidget()
        if _ocr_frame and _ocr_frame != self:
            _ocr_frame.setStyleSheet(f"QFrame {{ background: {t.bg_panel}; border: 1px solid {t.border_subtle}; border-radius: 8px; }}")
        # 刷新翻译结果容器
        _trans_frame = self.translate_text.parentWidget()
        if _trans_frame and _trans_frame != self:
            _trans_frame.setStyleSheet(f"QFrame {{ background: {t.bg_panel}; border: 1px solid {t.border_subtle}; border-radius: 8px; }}")
        self.btn_clear_history.setStyleSheet(get_clear_history_stylesheet(t))
        self.canvas.set_theme(self._is_dark())
        self._glow_ocr.set_accent(t.accent)
        self._glow_trans.set_accent(t.accent)

    def apply_language(self, lang: str):
        """刷新语言文字（被 MainWindow._apply_language 调用）"""
        self._current_lang = lang
        self.btn_open.setText("Import" if lang == "en" else "导入")
        self.btn_capture.setText("Capture" if lang == "en" else "截图")
        self.tool_select.setText("Crop" if lang == "en" else "裁剪")
        self.tool_rect.setText("Draw" if lang == "en" else "矩形")
        self.btn_pre_gray.setText("Grayscale" if lang == "en" else "灰度")
        self.btn_pre_binary.setText("Binarize" if lang == "en" else "二值化")
        self.btn_reset.setText("Reset" if lang == "en" else "重置")
        if hasattr(self, 'btn_save_image'):
            self.btn_save_image.setText("Save Image" if lang == "en" else "保存图片")
        if hasattr(self, 'btn_one_click'):
            self.btn_one_click.setText("One Punch")
        self.btn_ocr_local.setText("Local OCR" if lang == "en" else "本地识别")
        self.btn_ocr_ai.setText("Cloud AI" if lang == "en" else "AI识别")
        self.btn_trans_online.setText("Online Trans" if lang == "en" else "在线翻译")
        self.btn_trans_ai.setText("AI Trans" if lang == "en" else "AI翻译")
        self.result_label_ocr.setText("Recognition Result" if lang == "en" else "识别结果")
        self.result_label_trans.setText("Translation Result" if lang == "en" else "翻译结果")
        self.history_label.setText("Operation History" if lang == "en" else "操作历史")
        self.btn_clear_history.setText("Clear" if lang == "en" else "清空")
        if hasattr(self, '_history_tip'):
            self._history_tip.setText("Click to restore | Right-click to delete" if lang == "en" else "点击恢复 | 右键删除")
        _zh_items = ["中文", "英文", "日文", "韩文", "法文", "德文", "西班牙文", "俄文"]
        _en_items = ["Chinese", "English", "Japanese", "Korean", "French", "German", "Spanish", "Russian"]
        _map_zh_to_en = dict(zip(_zh_items, _en_items))
        _map_en_to_zh = dict(zip(_en_items, _zh_items))
        for combo in (self.translate_source_combo, self.translate_target_combo):
            current = combo.currentText()
            if current in _map_zh_to_en:
                key_zh = current
            elif current in _map_en_to_zh:
                key_zh = _map_en_to_zh[current]
            else:
                key_zh = "中文"
            new_items = _en_items if lang == "en" else _zh_items
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(new_items)
            target = _map_zh_to_en[key_zh] if lang == "en" else key_zh
            idx = combo.findText(target)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)
