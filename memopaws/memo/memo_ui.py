"""备忘录页面 UI 构建。"""

import os

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel, QLineEdit,
    QListWidget, QPushButton, QAbstractItemView, QSplitter,
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap

from ..core.utils import load_svg_icon
from ..core.themes import get_status_list_stylesheet, get_text_edit_stylesheet
from ..ui.segmented_control import AnimatedSegmentedControl
from .memo_widgets import MarkdownHighlighter, ZoomableTextEdit
from .markdown_viewer import MarkdownViewer


def build_memo_ui(page):
    """构建 MemoPage UI；逻辑回调仍由 MemoPage 提供。"""
    self = page
    layout = QVBoxLayout(self)
    layout.setContentsMargins(12, 8, 12, 12)
    layout.setSpacing(0)

    memo_splitter = QSplitter(Qt.Orientation.Horizontal)
    memo_splitter.setHandleWidth(6)
    memo_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")

    left_frame = QFrame()
    self._memo_left_frame = left_frame
    t = self._get_theme()
    left_frame.setStyleSheet(f"QFrame {{ border: 1px solid {t.border_subtle}; border-radius: 12px; background: {t.bg_panel}; }}")
    left_frame.setMinimumWidth(220)
    left_frame.setMaximumWidth(380)
    left_layout = QVBoxLayout(left_frame)
    left_layout.setContentsMargins(8, 8, 8, 8)
    left_layout.setSpacing(6)

    memo_btn_grid = QGridLayout()
    memo_btn_grid.setSpacing(4)
    memo_btn_ss = "QPushButton { padding: 4px 12px; font-size: 13px; }"
    icons_dir = self._get_icons_dir()
    icon_clr = self._get_icon_clr()

    btn_add_memo = QPushButton("新建")
    btn_add_memo.setIcon(QIcon(load_svg_icon(os.path.join(icons_dir, "add.svg"), 16, icon_clr)))
    btn_add_memo.setIconSize(QSize(16, 16))
    btn_add_memo.setStyleSheet(memo_btn_ss)
    self._memo_btn_add = btn_add_memo
    btn_add_memo.clicked.connect(self.add_memo)
    memo_btn_grid.addWidget(btn_add_memo, 0, 0)

    btn_import_memo = QPushButton("导入")
    btn_import_memo.setIcon(QIcon(load_svg_icon(os.path.join(icons_dir, "import.svg"), 16, icon_clr)))
    btn_import_memo.setIconSize(QSize(16, 16))
    btn_import_memo.setStyleSheet(memo_btn_ss)
    self._memo_btn_import = btn_import_memo
    btn_import_memo.clicked.connect(self._import_memo)
    memo_btn_grid.addWidget(btn_import_memo, 0, 1)

    btn_export_memo = QPushButton("导出")
    btn_export_memo.setIcon(QIcon(load_svg_icon(os.path.join(icons_dir, "save.svg"), 16, icon_clr)))
    btn_export_memo.setIconSize(QSize(16, 16))
    btn_export_memo.setStyleSheet(memo_btn_ss)
    self._memo_btn_export = btn_export_memo
    btn_export_memo.clicked.connect(self._export_memo)
    memo_btn_grid.addWidget(btn_export_memo, 1, 0)

    btn_delete_memo = QPushButton("删除")
    btn_delete_memo.setIcon(QIcon(load_svg_icon(os.path.join(icons_dir, "clear.svg"), 16, icon_clr)))
    btn_delete_memo.setIconSize(QSize(16, 16))
    btn_delete_memo.setStyleSheet(memo_btn_ss)
    self._memo_btn_delete = btn_delete_memo
    btn_delete_memo.clicked.connect(self.delete_memo)
    memo_btn_grid.addWidget(btn_delete_memo, 1, 1)
    left_layout.addLayout(memo_btn_grid)

    self.memo_search_input = QLineEdit()
    self.memo_search_input.setPlaceholderText("搜索备忘录...")
    self.memo_search_input.setFixedHeight(28)
    self.memo_search_input.setStyleSheet(f"""
        QLineEdit {{
            background: {t.bg_input};
            color: {t.text_primary};
            border: 1px solid {t.border_subtle};
            border-radius: 6px;
            padding: 0 8px;
            font-size: 12px;
        }}
        QLineEdit:focus {{ border: 1px solid {t.accent}; }}
    """)
    self.memo_search_input.textChanged.connect(self._filter_memo_list)
    left_layout.addWidget(self.memo_search_input)

    self.memo_list = QListWidget()
    self.memo_list.setStyleSheet(get_status_list_stylesheet(t))
    self.memo_list.setWordWrap(True)
    self.memo_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    self.memo_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    self.memo_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    self.memo_list.currentRowChanged.connect(self._on_memo_selection_changed)
    left_layout.addWidget(self.memo_list)

    self.memo_stat_label = QLabel("0 条")
    self.memo_stat_label.setStyleSheet(f"font-size:11px; color:{t.text_muted}; border:none; padding: 2px 4px; background:transparent;")
    left_layout.addWidget(self.memo_stat_label)
    memo_splitter.addWidget(left_frame)

    right_frame = QFrame()
    self._memo_right_frame = right_frame
    right_frame.setStyleSheet(f"QFrame {{ border: 1px solid {t.border_subtle}; border-radius: 12px; background: {t.bg_panel}; }}")
    right_layout = QVBoxLayout(right_frame)
    right_layout.setContentsMargins(12, 12, 12, 12)
    right_layout.setSpacing(8)

    self.memo_title_input = QLineEdit()
    self.memo_title_input.setPlaceholderText("标题")
    self.memo_title_input.setStyleSheet(f"""
        QLineEdit {{
            background: transparent;
            color: {t.accent};
            border: none;
            border-bottom: 1px solid {t.accent}33;
            padding: 6px 4px;
            font-size: 18px;
            font-weight: bold;
        }}
    """)
    right_layout.addWidget(self.memo_title_input)

    self.memo_time_label = QLabel("")
    self.memo_time_label.setStyleSheet(f"font-size:11px; color:{t.text_muted}; border:none; padding: 0 4px;")
    right_layout.addWidget(self.memo_time_label)

    tag_row = QHBoxLayout()
    tag_row.setSpacing(4)
    tag_lbl = QLabel("标签:")
    tag_lbl.setStyleSheet(f"font-size:11px; color:{t.text_muted}; border:none; background:transparent;")
    tag_row.addWidget(tag_lbl)
    self.memo_tags_input = QLineEdit()
    self.memo_tags_input.setPlaceholderText("逗号分隔，如：工作,重要")
    self.memo_tags_input.setFixedHeight(24)
    self.memo_tags_input.setStyleSheet(f"""
        QLineEdit {{
            background: {t.bg_input};
            color: {t.text_primary};
            border: 1px solid {t.border_subtle};
            border-radius: 4px;
            padding: 0 6px;
            font-size: 11px;
        }}
        QLineEdit:focus {{ border: 1px solid {t.accent}; }}
    """)
    self.memo_tags_input.editingFinished.connect(self._on_tags_changed)
    tag_row.addWidget(self.memo_tags_input, 1)
    right_layout.addLayout(tag_row)

    self._memo_editor_splitter = QSplitter(Qt.Orientation.Horizontal)
    self._memo_editor_splitter.setHandleWidth(4)
    self._memo_editor_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")

    self.memo_content_view = ZoomableTextEdit()
    self.memo_content_view.setReadOnly(False)
    self._md_highlighter = MarkdownHighlighter(self.memo_content_view.document(), is_dark_fn=self._is_dark)
    self.memo_content_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    self.memo_content_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    self.memo_content_view.setStyleSheet(get_text_edit_stylesheet(t))
    self._memo_editor_splitter.addWidget(self.memo_content_view)

    self.memo_split_preview = MarkdownViewer()
    self.memo_split_preview.set_background_color(self._get_theme().bg_main)
    self.memo_split_preview.setVisible(False)
    self.memo_split_preview.setProperty("mode", "preview")
    self._memo_editor_splitter.addWidget(self.memo_split_preview)

    self._memo_editor_splitter.setSizes([500, 500])
    right_layout.addWidget(self._memo_editor_splitter, 1)

    edit_row = QHBoxLayout()
    self.memo_btn_save = QPushButton("保存")
    self.memo_btn_save.setIcon(QIcon(load_svg_icon(os.path.join(icons_dir, "save.svg"), 16, icon_clr)))
    self.memo_btn_save.setIconSize(QSize(16, 16))
    self.memo_btn_save.setFixedHeight(32)
    self.memo_btn_save.setStyleSheet(f"""
        QPushButton {{
            background: {t.accent};
            color: #FFFFFF;
            border: none;
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton:hover {{ background: {t.accent_hover}; }}
    """)
    self.memo_btn_save.clicked.connect(self._save_memo_edit)
    edit_row.addWidget(self.memo_btn_save)
    edit_row.addStretch()

    self._memo_preview_mode = False
    self._memo_split_mode = False
    lang = self._get_current_lang()
    seg_container = QFrame()
    seg_container.setObjectName("memoSegContainer")
    seg_container.setFixedSize(242, 34)
    seg_container.setStyleSheet(f"""
        QFrame#memoSegContainer {{
            background: {t.bg_neutral_button};
            border: 1px solid {t.border_subtle};
            border-radius: 8px;
        }}
    """)
    seg_layout = QHBoxLayout(seg_container)
    seg_layout.setContentsMargins(0, 0, 0, 0)
    seg_layout.setSpacing(0)
    btn_ss = f"QPushButton {{ background: transparent; color: {t.text_secondary}; border: none; border-radius: 6px; font-size: 13px; padding: 0; }}"

    self.btn_memo_edit = QPushButton("编辑" if lang == "zh" else "Edit")
    self.btn_memo_edit.setCheckable(True)
    self.btn_memo_edit.setChecked(True)
    self.btn_memo_edit.setFixedWidth(80)
    self.btn_memo_edit.setFixedHeight(32)
    self.btn_memo_edit.setStyleSheet(btn_ss)
    self.btn_memo_edit.clicked.connect(lambda: self._switch_memo_mode("edit"))
    seg_layout.addWidget(self.btn_memo_edit)

    self.btn_memo_split = QPushButton()
    self.btn_memo_split.setCheckable(True)
    self.btn_memo_split.setFixedWidth(80)
    self.btn_memo_split.setFixedHeight(32)
    # 创建分屏图标：正方形中间有一居中竖线
    from PySide6.QtGui import QPainter, QPen, QColor
    _icon_size = 16
    _pixmap = QPixmap(_icon_size, _icon_size)
    _pixmap.fill(Qt.GlobalColor.transparent)
    _painter = QPainter(_pixmap)
    _painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _painter.setPen(QPen(QColor("#B7B5A9"), 1.5))
    _margin = 2
    _painter.drawRect(_margin, _margin, _icon_size - 2 * _margin, _icon_size - 2 * _margin)
    _painter.drawLine(_icon_size // 2, _margin, _icon_size // 2, _icon_size - _margin)
    _painter.end()
    self.btn_memo_split.setIcon(QIcon(_pixmap))
    self.btn_memo_split.setIconSize(QSize(_icon_size, _icon_size))
    self.btn_memo_split.setStyleSheet(btn_ss)
    self.btn_memo_split.clicked.connect(lambda: self._switch_memo_mode("split"))
    seg_layout.addWidget(self.btn_memo_split)

    self.btn_memo_preview = QPushButton("预览" if lang == "zh" else "Preview")
    self.btn_memo_preview.setCheckable(True)
    self.btn_memo_preview.setFixedWidth(80)
    self.btn_memo_preview.setFixedHeight(32)
    self.btn_memo_preview.setStyleSheet(btn_ss)
    self.btn_memo_preview.clicked.connect(lambda: self._switch_memo_mode("preview"))
    seg_layout.addWidget(self.btn_memo_preview)

    self._memo_seg_ctrl = AnimatedSegmentedControl(seg_container, self.btn_memo_edit, self.btn_memo_split, self.btn_memo_preview)
    edit_row.addWidget(seg_container)
    self.memo_preview_toggle = self.btn_memo_preview

    self.memo_content_view.textChanged.connect(self._on_memo_text_changed)
    self.memo_content_view.zoomChanged.connect(self._on_memo_zoom_changed)
    right_layout.addLayout(edit_row)

    memo_splitter.addWidget(right_frame)
    memo_splitter.setSizes([300, 500])
    memo_splitter.setCollapsible(0, False)
    layout.addWidget(memo_splitter, 1)

    self.memo_data = self.load_memo()
    self._update_memo_list()
    self.apply_theme()
    QTimer.singleShot(0, self._prewarm_preview)
