"""设置页面模块 - 从 main_window.py 提取"""

import os
import time
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QComboBox, QFrame, QApplication, QMessageBox,
    QScrollArea,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtWidgets import QWidget

from .themes import (
    DARK, LIGHT,
    get_theme_button_stylesheet, _inner_shadow,
)
from .utils import (
    set_title_bar_color, get_root_path, get_config_dir,
    move_snaptrans_folder, save_anchor, normalize_api_url,
    test_api_connection, load_svg_icon as _load_svg
)
from .segmented_control import AnimatedSegmentedControl


def load_svg_icon(svg_path, size=20, color=None):
    """兼容旧调用，委托给 utils"""
    return _load_svg(svg_path, size, color)

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    """设置页面独立模块"""

    def __init__(self, parent, *,
                 get_config_path,
                 get_theme,
                 is_dark,
                 load_config,
                 save_config,
                 ocr_manager,
                 on_toggle_theme,
                 on_set_theme,
                 on_set_language,
                 get_current_lang,
                 get_current_theme_dark,
                 on_save_clipboard,
                 show_message,
                 shortcut_mgr=None,
                 text_replacer=None):
        super().__init__(parent)
        self._get_config_path = get_config_path
        self._get_theme = get_theme
        self._is_dark = is_dark
        self._load_config = load_config
        self._save_config = save_config
        self._ocr_manager = ocr_manager
        self._on_toggle_theme = on_toggle_theme
        self._set_theme = on_set_theme
        self._on_set_language = on_set_language
        self._get_current_lang = get_current_lang
        self._get_current_theme_dark = get_current_theme_dark
        self._on_save_clipboard = on_save_clipboard
        self._show_message = show_message
        self._shortcut_mgr = shortcut_mgr

        self._create_ui()
        self.apply_theme()  # 初始化时应用主题色

        if hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(lambda _: self.apply_theme())
        if hasattr(parent, 'language_changed'):
            parent.language_changed.connect(self.apply_language)

    def _create_ui(self):
        _t = DARK if self._is_dark() else LIGHT

        # 外层滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        # 内容容器
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 8, 12, 32)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── 主题设置（分段按钮）──
        theme_group = QFrame()
        theme_group.setObjectName("card")
        theme_group.setStyleSheet(f"""
            QFrame#card {{
                background: {_t.bg_panel};
                border: 1px solid {_t.border_subtle};
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        theme_layout = QVBoxLayout(theme_group)
        theme_main_row = QHBoxLayout()
        theme_main_row.setContentsMargins(0, 0, 0, 0)
        theme_main_row.setSpacing(8)
        self.theme_title_lbl = QLabel("Theme Mode")
        self.theme_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{_t.text_primary}; border:none; background:transparent;")
        self.theme_title_lbl.setFixedHeight(24)
        self.theme_title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        theme_main_row.addWidget(self.theme_title_lbl)
        theme_main_row.addStretch()

        # 主题分段按钮
        self._theme_seg = QFrame()
        self._theme_seg.setFixedHeight(34)
        self._theme_seg.setFixedWidth(162)
        self._theme_seg.setStyleSheet(f"""
            QFrame {{
                background: {_t.bg_neutral_button};
                border: 1px solid {_t.border_subtle};
                border-radius: 8px;
            }}
        """)
        seg_layout_theme = QHBoxLayout(self._theme_seg)
        seg_layout_theme.setContentsMargins(0, 0, 0, 0)
        seg_layout_theme.setSpacing(0)

        is_dark = self._is_dark()
        self.btn_theme_dark = QPushButton("Dark" if self._get_current_lang() == "en" else "暗色")
        self.btn_theme_dark.setCheckable(True)
        self.btn_theme_dark.setChecked(is_dark)
        self.btn_theme_dark.setFixedWidth(80)
        self.btn_theme_dark.setFixedHeight(32)
        self.btn_theme_dark.clicked.connect(lambda: self._set_theme(True))
        seg_layout_theme.addWidget(self.btn_theme_dark)

        self.btn_theme_light = QPushButton("Light" if self._get_current_lang() == "en" else "亮色")
        self.btn_theme_light.setCheckable(True)
        self.btn_theme_light.setChecked(not is_dark)
        self.btn_theme_light.setFixedWidth(80)
        self.btn_theme_light.setFixedHeight(32)
        self.btn_theme_light.clicked.connect(lambda: self._set_theme(False))
        seg_layout_theme.addWidget(self.btn_theme_light)

        self._theme_seg_ctrl = AnimatedSegmentedControl(
            self._theme_seg, self.btn_theme_dark, self.btn_theme_light)
        theme_main_row.addWidget(self._theme_seg)
        theme_layout.addLayout(theme_main_row)
        layout.addWidget(theme_group)

        # ── 语言设置（分段按钮）──
        lang_group = QFrame()
        lang_group.setObjectName("card")
        lang_group.setStyleSheet(f"""
            QFrame#card {{
                background: {_t.bg_panel};
                border: 1px solid {_t.border_subtle};
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        lang_layout = QVBoxLayout(lang_group)
        lang_main_row = QHBoxLayout()
        lang_main_row.setContentsMargins(0, 0, 0, 0)
        lang_main_row.setSpacing(8)
        self.lang_title_lbl = QLabel("Language")
        self.lang_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{_t.text_primary}; border:none; background:transparent;")
        self.lang_title_lbl.setFixedHeight(24)
        self.lang_title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lang_main_row.addWidget(self.lang_title_lbl)
        lang_main_row.addStretch()

        # 分段按钮容器
        self._lang_seg = QFrame()
        self._lang_seg.setFixedHeight(34)
        self._lang_seg.setFixedWidth(162)
        seg_t = DARK if self._is_dark() else LIGHT
        is_en = self._get_current_lang() == "en"
        self._lang_seg.setStyleSheet(f"""
            QFrame {{
                background: {seg_t.bg_neutral_button};
                border: 1px solid {seg_t.border_subtle};
                border-radius: 8px;
            }}
        """)
        seg_layout = QHBoxLayout(self._lang_seg)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(0)

        self.btn_lang_en = QPushButton("English")
        self.btn_lang_en.setCheckable(True)
        self.btn_lang_en.setChecked(is_en)
        self.btn_lang_en.setFixedWidth(80)
        self.btn_lang_en.setFixedHeight(32)
        self.btn_lang_en.clicked.connect(lambda: self._on_set_language("en"))
        seg_layout.addWidget(self.btn_lang_en)

        self.btn_lang_zh = QPushButton("中文")
        self.btn_lang_zh.setCheckable(True)
        self.btn_lang_zh.setChecked(not is_en)
        self.btn_lang_zh.setFixedWidth(80)
        self.btn_lang_zh.setFixedHeight(32)
        self.btn_lang_zh.clicked.connect(lambda: self._on_set_language("zh"))
        seg_layout.addWidget(self.btn_lang_zh)

        self._lang_seg_ctrl = AnimatedSegmentedControl(
            self._lang_seg, self.btn_lang_en, self.btn_lang_zh)
        self._update_lang_seg_style()
        lang_main_row.addWidget(self._lang_seg)
        lang_layout.addLayout(lang_main_row)
        layout.addWidget(lang_group)

        # ── API 配置 ──
        api_group = QFrame()
        api_group.setObjectName("card")
        api_group.setStyleSheet(f"""
            QFrame#card {{
                background: {_t.bg_panel};
                border: 1px solid {_t.border_subtle};
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        api_layout = QVBoxLayout(api_group)
        api_header_row = QHBoxLayout()
        api_header_row.setSpacing(6)
        self.api_title_lbl = QLabel("API Configuration")
        self.api_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{_t.text_primary}; border:none; background:transparent;")
        self.api_title_lbl.setFixedHeight(24)
        self.api_title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        api_header_row.addWidget(self.api_title_lbl)
        api_header_row.addStretch()
        api_layout.addLayout(api_header_row)

        _init_sub_ss = f"font-size:13px; color:{_t.text_secondary}; border:none; background:transparent;"

        # API Key
        key_row = QHBoxLayout()
        self.settings_key_label = QLabel("API Key")
        self.settings_key_label.setStyleSheet(_init_sub_ss)
        self.settings_key_label.setFixedWidth(90)
        key_row.addWidget(self.settings_key_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.settings_key_input = QLineEdit()
        self.settings_key_input.setPlaceholderText("输入 API Key")
        self.settings_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.settings_key_input.setMinimumHeight(42)
        self.settings_key_input.setMaximumHeight(42)
        key_row.addWidget(self.settings_key_input, 1)
        api_layout.addLayout(key_row)

        # API URL
        url_row = QHBoxLayout()
        self.settings_url_label = QLabel("API URL")
        self.settings_url_label.setStyleSheet(_init_sub_ss)
        self.settings_url_label.setFixedWidth(90)
        url_row.addWidget(self.settings_url_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.settings_url_input = QLineEdit()
        self.settings_url_input.setPlaceholderText("API Base URL")
        self.settings_url_input.setMinimumHeight(42)
        self.settings_url_input.setMaximumHeight(42)
        url_row.addWidget(self.settings_url_input, 1)
        api_layout.addLayout(url_row)

        # 模型名
        model_row = QHBoxLayout()
        self.settings_model_label = QLabel("模型")
        self.settings_model_label.setStyleSheet(_init_sub_ss)
        self.settings_model_label.setFixedWidth(90)
        model_row.addWidget(self.settings_model_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.settings_model_input = QLineEdit()
        self.settings_model_input.setPlaceholderText("模型名")
        self.settings_model_input.setMinimumHeight(42)
        self.settings_model_input.setMaximumHeight(42)
        model_row.addWidget(self.settings_model_input, 1)
        api_layout.addLayout(model_row)

        # 测试连接按钮
        btn_row = QHBoxLayout()
        self.settings_test_btn = QPushButton("测试连接")
        btn_test = self.settings_test_btn
        btn_test.setObjectName("accent")
        btn_test.setFixedWidth(80)
        btn_test.setStyleSheet(f"""
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
        btn_test.clicked.connect(self._test_api_connection)
        btn_row.addWidget(btn_test)
        self.settings_test_label = QLabel("")
        _init_tip_ss = f"font-size:12px; color:{_t.text_muted}; border:none;"
        self.settings_test_label.setStyleSheet(_init_tip_ss)
        btn_row.addWidget(self.settings_test_label, 1)
        api_layout.addLayout(btn_row)

        layout.addWidget(api_group)

        # 加载已保存的配置到输入框
        self._load_api_to_inputs()

        # ── 剪切板设置 ──
        clip_group = QFrame()
        clip_group.setObjectName("card")
        clip_group.setStyleSheet(f"""
            QFrame#card {{
                background: {_t.bg_panel};
                border: 1px solid {_t.border_subtle};
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        clip_layout = QVBoxLayout(clip_group)
        clip_header_row = QHBoxLayout()
        clip_header_row.setSpacing(6)
        self.clip_title_lbl = QLabel("Clipboard Settings")
        self.clip_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{_t.text_primary}; border:none; background:transparent;")
        self.clip_title_lbl.setFixedHeight(24)
        self.clip_title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        clip_header_row.addWidget(self.clip_title_lbl)
        clip_header_row.addStretch()
        clip_layout.addLayout(clip_header_row)

        max_row = QHBoxLayout()
        self.settings_max_label = QLabel("最大条数" if self._get_current_lang() == "zh" else "Max Items")
        self.settings_max_label.setStyleSheet(_init_sub_ss)
        self.settings_max_label.setFixedWidth(90)
        max_row.addWidget(self.settings_max_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.settings_clip_max_input = QSpinBox()
        self.settings_clip_max_input.setRange(10, 500)
        self.settings_clip_max_input.setValue(50)
        self.settings_clip_max_input.setSingleStep(10)
        self.settings_clip_max_input.setFixedWidth(60)
        self.settings_clip_max_input.setMinimumHeight(28)
        self.settings_clip_max_input.setMaximumHeight(28)
        max_row.addWidget(self.settings_clip_max_input)
        self.settings_max_tip = QLabel("(总条数上限；超出时自动删除最旧的非锁定项)" if self._get_current_lang() == "zh" else "(Max items; oldest unlocked items auto-deleted when exceeded)")
        self.settings_max_tip.setStyleSheet(_init_tip_ss)
        max_row.addWidget(self.settings_max_tip, 0, Qt.AlignmentFlag.AlignVCenter)
        max_row.addStretch()
        clip_layout.addLayout(max_row)
        layout.addWidget(clip_group)

        self._load_clip_setting_to_input()

        # ── 操作历史设置 ──
        hist_group = QFrame()
        hist_group.setObjectName("card")
        hist_group.setStyleSheet(f"""
            QFrame#card {{
                background: {_t.bg_panel};
                border: 1px solid {_t.border_subtle};
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        hist_layout = QVBoxLayout(hist_group)
        hist_header_row = QHBoxLayout()
        hist_header_row.setSpacing(6)
        self.hist_title_lbl = QLabel("操作历史" if self._get_current_lang() == "zh" else "History")
        self.hist_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{_t.text_primary}; border:none; background:transparent;")
        self.hist_title_lbl.setFixedHeight(24)
        hist_header_row.addWidget(self.hist_title_lbl)
        hist_header_row.addStretch()
        hist_layout.addLayout(hist_header_row)

        hist_max_row = QHBoxLayout()
        self.hist_max_label = QLabel("最大条数" if self._get_current_lang() == "zh" else "Max Items")
        self.hist_max_label.setStyleSheet(_init_sub_ss)
        self.hist_max_label.setFixedWidth(90)
        hist_max_row.addWidget(self.hist_max_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.settings_hist_max_input = QSpinBox()
        self.settings_hist_max_input.setRange(10, 500)
        self.settings_hist_max_input.setValue(100)
        self.settings_hist_max_input.setSingleStep(10)
        self.settings_hist_max_input.setFixedWidth(60)
        self.settings_hist_max_input.setMinimumHeight(28)
        self.settings_hist_max_input.setMaximumHeight(28)
        hist_max_row.addWidget(self.settings_hist_max_input)
        self.hist_max_tip = QLabel("(超出时自动删除最旧记录)" if self._get_current_lang() == "zh" else "(Oldest records auto-deleted when exceeded)")
        self.hist_max_tip.setStyleSheet(_init_tip_ss)
        hist_max_row.addWidget(self.hist_max_tip, 0, Qt.AlignmentFlag.AlignVCenter)
        hist_max_row.addStretch()
        hist_layout.addLayout(hist_max_row)
        layout.addWidget(hist_group)

        self._load_hist_setting_to_input()

        # ── 备忘录存储路径 ──
        memo_path_group = QFrame()
        memo_path_group.setObjectName("card")
        memo_path_group.setStyleSheet(f"""
            QFrame#card {{
                background: {_t.bg_panel};
                border: 1px solid {_t.border_subtle};
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        memo_path_layout = QVBoxLayout(memo_path_group)
        memo_path_header = QHBoxLayout()
        memo_path_header.setSpacing(6)
        self.memo_path_title_lbl = QLabel("Storage Directory")
        self.memo_path_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{_t.text_primary}; border:none; background:transparent;")
        self.memo_path_title_lbl.setFixedHeight(24)
        self.memo_path_title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        memo_path_header.addWidget(self.memo_path_title_lbl)
        memo_path_header.addStretch()
        memo_path_layout.addLayout(memo_path_header)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.settings_memo_path_input = QLineEdit()
        self.settings_memo_path_input.setPlaceholderText(get_root_path())
        self.settings_memo_path_input.setFixedHeight(28)
        self.settings_memo_path_input.setStyleSheet(f"""
            QLineEdit {{
                background: {_t.bg_input};
                color: {_t.text_primary};
                border: 1px solid {_t.border_subtle};
                border-radius: 6px;
                padding: 0 8px;
                font-size: 12px;
            }}
            QLineEdit:focus {{ border: 1px solid {_t.accent}; }}
        """)
        path_row.addWidget(self.settings_memo_path_input, 1)

        browse_btn = QPushButton("Browse" if self._get_current_lang() == "en" else "浏览")
        browse_btn.setFixedSize(64, 28)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_t.bg_neutral_button};
                color: {_t.text_secondary};
                border: 1px solid {_t.border_subtle};
                border-radius: 6px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {_t.bg_active}; }}
        """)
        self._memo_browse_btn = browse_btn
        browse_btn.clicked.connect(self._browse_memo_path)
        path_row.addWidget(browse_btn)
        memo_path_layout.addLayout(path_row)

        # 迁移提示
        self.memo_path_tip = QLabel("留空则使用默认路径，切换后整个 .snaptrans 文件夹会移动")
        self.memo_path_tip.setStyleSheet(_init_tip_ss)
        memo_path_layout.addWidget(self.memo_path_tip)

        layout.addWidget(memo_path_group)

        self._load_memo_path_setting()

        # ── 快捷键（可编辑）──
        shortcut_group = QFrame()
        shortcut_group.setObjectName("card")
        shortcut_group.setStyleSheet(f"""
            QFrame#card {{
                background: {_t.bg_panel};
                border: 1px solid {_t.border_subtle};
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        shortcut_layout = QVBoxLayout(shortcut_group)
        shortcut_header_row = QHBoxLayout()
        shortcut_header_row.setSpacing(6)
        self.shortcut_title_lbl = QLabel("Keyboard Shortcuts")
        self.shortcut_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{_t.text_primary}; border:none; background:transparent;")
        self.shortcut_title_lbl.setFixedHeight(24)
        self.shortcut_title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        shortcut_header_row.addWidget(self.shortcut_title_lbl)
        shortcut_header_row.addStretch()
        shortcut_layout.addLayout(shortcut_header_row)

        self._shortcut_edit_rows = []
        if self._shortcut_mgr:
            for action, display_name, current_key in self._shortcut_mgr.get_all_actions():
                row = QHBoxLayout()
                row.setSpacing(8)
                lbl = QLabel(display_name)
                lbl.setStyleSheet(f"font-size:13px; color:{_t.text_secondary}; border:none; background:transparent;")
                lbl.setFixedWidth(120)
                row.addWidget(lbl)
                edit = QLineEdit(current_key)
                edit.setReadOnly(True)
                edit.setFixedWidth(160)
                edit.setFixedHeight(28)
                edit.setStyleSheet(f"""
                    QLineEdit {{
                        background: {_t.bg_input};
                        color: {_t.text_primary};
                        border: 1px solid {_t.border_subtle};
                        border-radius: 6px;
                        padding: 0 8px;
                        font-size: 12px;
                        font-weight: bold;
                    }}
                    QLineEdit:focus {{
                        border: 1px solid {_t.accent};
                    }}
                """)
                edit.installEventFilter(self)
                edit._shortcut_action = action
                row.addWidget(edit)
                reset_btn = QPushButton("Reset" if self._get_current_lang() == "en" else "重置")
                reset_btn.setFixedSize(56, 28)
                reset_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {_t.bg_neutral_button};
                        color: {_t.text_secondary};
                        border: 1px solid {_t.border_subtle};
                        border-radius: 6px;
                        font-size: 11px;
                    }}
                    QPushButton:hover {{
                        background: {_t.bg_active};
                    }}
                """)
                reset_btn._shortcut_action = action
                reset_btn.clicked.connect(lambda checked=False, a=action, e=edit: self._reset_shortcut(a, e))
                row.addWidget(reset_btn)
                row.addStretch()
                shortcut_layout.addLayout(row)
                self._shortcut_edit_rows.append((action, lbl, edit, reset_btn))
        else:
            # 无管理器时静态展示
            shortcuts = [("截图识别", "Alt+X"), ("画布自适应", "Ctrl+F"), ("粘贴图片", "Ctrl+V")]
            for name, key in shortcuts:
                row = QHBoxLayout()
                row.setSpacing(8)
                lbl = QLabel(name)
                lbl.setStyleSheet(f"font-size:13px; color:{_t.text_secondary}; border:none; background:transparent;")
                row.addWidget(lbl)
                k = QLabel(key)
                k.setStyleSheet(f"font-size:12px; color:{_t.accent}; border:none; background:transparent; font-weight:bold;")
                row.addWidget(k)
                row.addStretch()
                shortcut_layout.addLayout(row)

        layout.addWidget(shortcut_group)

        # ── 关闭窗口行为（分段按钮）──
        close_group = QFrame()
        close_group.setObjectName("card")
        close_group.setStyleSheet(f"""
            QFrame#card {{
                background: {_t.bg_panel};
                border: 1px solid {_t.border_subtle};
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        close_layout = QVBoxLayout(close_group)
        close_main_row = QHBoxLayout()
        close_main_row.setContentsMargins(0, 0, 0, 0)
        close_main_row.setSpacing(8)
        self.close_title_lbl = QLabel("Close Behavior")
        self.close_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{_t.text_primary}; border:none; background:transparent;")
        self.close_title_lbl.setFixedHeight(24)
        self.close_title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        close_main_row.addWidget(self.close_title_lbl)
        close_main_row.addStretch()

        config = self._load_config()
        is_tray = config.get("close_behavior") == "tray"
        self._close_behavior = "tray" if is_tray else "exit"

        self._close_seg = QFrame()
        self._close_seg.setFixedHeight(34)
        self._close_seg.setFixedWidth(222)
        self._close_seg.setStyleSheet(f"""
            QFrame {{
                background: {_t.bg_neutral_button};
                border: 1px solid {_t.border_subtle};
                border-radius: 8px;
            }}
        """)
        close_seg_layout = QHBoxLayout(self._close_seg)
        close_seg_layout.setContentsMargins(0, 0, 0, 0)
        close_seg_layout.setSpacing(0)

        self.close_btn_exit = QPushButton("Exit")
        self.close_btn_exit.setCheckable(True)
        self.close_btn_exit.setChecked(not is_tray)
        self.close_btn_exit.setFixedWidth(110)
        self.close_btn_exit.setFixedHeight(32)
        self.close_btn_exit.clicked.connect(lambda: self._set_close_behavior("exit"))
        close_seg_layout.addWidget(self.close_btn_exit)

        self.close_btn_tray = QPushButton("Tray")
        self.close_btn_tray.setCheckable(True)
        self.close_btn_tray.setChecked(is_tray)
        self.close_btn_tray.setFixedWidth(110)
        self.close_btn_tray.setFixedHeight(32)
        self.close_btn_tray.clicked.connect(lambda: self._set_close_behavior("tray"))
        close_seg_layout.addWidget(self.close_btn_tray)

        self._close_seg_ctrl = AnimatedSegmentedControl(
            self._close_seg, self.close_btn_exit, self.close_btn_tray)
        self._update_close_seg_style()
        close_main_row.addWidget(self._close_seg)
        close_layout.addLayout(close_main_row)
        layout.addWidget(close_group)

        # ── 保存按钮 ──
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        self.settings_btn_save = QPushButton("保存")
        self.settings_btn_save.setObjectName("accent")
        self.settings_btn_save.setStyleSheet(f"""
            QPushButton#accent {{
                background: {_t.accent};
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 6px 24px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton#accent:hover {{ background: {_t.accent_hover}; }}
        """)
        self.settings_btn_save.setMinimumHeight(28)
        self.settings_btn_save.setMaximumHeight(28)
        self.settings_btn_save.setFixedWidth(100)
        self.settings_btn_save.clicked.connect(self._save_api_config)
        bottom_row.addWidget(self.settings_btn_save)
        layout.addLayout(bottom_row)

        self.apply_input_styles()

        # 末尾：设置滚动区域
        scroll.setWidget(content)

        # 将 scroll 添加到 self
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

        # 延迟初始化：等布局计算完毕后再定位三个指示器并应用初始样式
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._init_seg_indicators)

    def _init_seg_indicators(self):
        """布局就绪后一次性设置分段按钮的初始状态（样式 + 指示器位置）"""
        self._update_theme_seg_style()
        self._update_lang_seg_style()
        self._update_close_seg_style()
        self._update_lang_seg_style()
        self._update_close_seg_style()

    # ── 样式刷新 ──

    def apply_input_styles(self):
        """根据当前主题应用 API 输入框样式"""
        t = DARK if self._is_dark() else LIGHT
        bg, fg, border = t.bg_input, t.text_primary, t.border_subtle
        label_color = t.text_secondary
        tip_color = t.text_secondary
        accent_color = t.accent
        shadow = _inner_shadow(t)
        ss = f"""
            QLineEdit {{
                background: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 13px;
                {shadow}
            }}
            QLineEdit:focus {{ border: 1px solid {accent_color}; }}
        """
        for inp in (self.settings_key_input, self.settings_url_input,
                     self.settings_model_input):
            inp.setStyleSheet(ss)
        self.settings_clip_max_input.setStyleSheet(f"""
            QSpinBox {{
                background: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 13px;
                min-width: 50px;
                max-width: 60px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background: {bg};
                border: none;
                width: 16px;
            }}
        """)
        if hasattr(self, 'settings_hist_max_input'):
            self.settings_hist_max_input.setStyleSheet(f"""
                QSpinBox {{
                    background: {bg};
                    color: {fg};
                    border: 1px solid {border};
                    border-radius: 8px;
                    padding: 4px 8px;
                    font-size: 13px;
                    min-width: 50px;
                    max-width: 60px;
                }}
                QSpinBox::up-button, QSpinBox::down-button {{
                    background: {bg};
                    border: none;
                    width: 16px;
                }}
            """)
        label_ss_sub = f"font-size:13px; color:{label_color}; border:none; background:transparent;"
        label_ss_tip = f"font-size:12px; color:{tip_color}; border:none; background:transparent;"
        for lbl in (self.settings_key_label, self.settings_url_label,
                     self.settings_model_label, self.settings_max_label,
                     self.hist_max_label):
            lbl.setStyleSheet(label_ss_sub)
        self.settings_max_tip.setStyleSheet(label_ss_tip)
        if hasattr(self, 'hist_max_tip'):
            self.hist_max_tip.setStyleSheet(label_ss_tip)
        self._update_theme_seg_style()

    def apply_theme(self):
        """刷新设置页所有主题相关样式"""
        t = DARK if self._is_dark() else LIGHT

        # 刷新卡片背景
        for card in self.findChildren(QFrame):
            if card.objectName() == "card":
                card.setStyleSheet(f"""
                    QFrame#card {{
                        background: {t.bg_panel};
                        border: 1px solid {t.border_subtle};
                        border-radius: 12px;
                        padding: 16px;
                    }}
                """)

        # 刷新标题颜色
        self.theme_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        self.lang_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        self.api_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        self.clip_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        if hasattr(self, 'hist_title_lbl'):
            self.hist_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        self.shortcut_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        self.close_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        if hasattr(self, 'memo_path_title_lbl'):
            self.memo_path_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")

        # 快捷键输入框 + 重置按钮
        _input_ss = f"""
            QLineEdit {{
                background: {t.bg_input};
                color: {t.text_primary};
                border: 1px solid {t.border_subtle};
                border-radius: 6px;
                padding: 0 8px;
                font-size: 12px;
                font-weight: bold;
            }}
            QLineEdit:focus {{ border: 1px solid {t.accent}; }}
        """
        _reset_ss = f"""
            QPushButton {{
                background: {t.bg_neutral_button};
                color: {t.text_secondary};
                border: 1px solid {t.border_subtle};
                border-radius: 6px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {t.bg_active}; }}
        """
        if hasattr(self, '_shortcut_edit_rows'):
            for row_data in self._shortcut_edit_rows:
                if len(row_data) >= 3:
                    row_data[2].setStyleSheet(_input_ss)
                if len(row_data) >= 4:
                    row_data[3].setStyleSheet(_reset_ss)

        # 备忘录路径输入框 + 浏览按钮
        if hasattr(self, 'settings_memo_path_input'):
            self.settings_memo_path_input.setStyleSheet(_input_ss)
        if hasattr(self, '_memo_browse_btn'):
            self._memo_browse_btn.setStyleSheet(_reset_ss)
        if hasattr(self, 'memo_path_tip'):
            self.memo_path_tip.setStyleSheet(f"font-size:11px; color:{t.text_muted}; border:none; background:transparent;")

        # 主题分段按钮容器
        if hasattr(self, '_theme_seg'):
            self._theme_seg.setStyleSheet(f"""
                QFrame {{
                    background: {t.bg_neutral_button};
                    border: 1px solid {t.border_subtle};
                    border-radius: 8px;
                }}
            """)
        self._update_theme_seg_style()

        # 语言分段按钮容器
        if hasattr(self, '_lang_seg'):
            self._lang_seg.setStyleSheet(f"""
                QFrame {{
                    background: {t.bg_neutral_button};
                    border: 1px solid {t.border_subtle};
                    border-radius: 8px;
                }}
            """)
        self._update_lang_seg_style()

        # 关闭行为分段按钮容器
        if hasattr(self, '_close_seg'):
            self._close_seg.setStyleSheet(f"""
                QFrame {{
                    background: {t.bg_neutral_button};
                    border: 1px solid {t.border_subtle};
                    border-radius: 8px;
                }}
            """)
        self._update_close_seg_style()

        # 输入框样式
        self.apply_input_styles()

    def apply_language(self, lang: str):
        """刷新设置页所有文字"""
        if hasattr(self, 'settings_key_label'):
            self.settings_key_label.setText("API Key")
        if hasattr(self, 'settings_url_label'):
            self.settings_url_label.setText("API URL")
        if hasattr(self, 'settings_model_label'):
            self.settings_model_label.setText("Model" if lang == "en" else "模型")
        if hasattr(self, 'settings_max_label'):
            self.settings_max_label.setText("Max Records" if lang == "en" else "最大条数")
        if hasattr(self, 'theme_title_lbl'):
            self.theme_title_lbl.setText("Theme Mode" if lang == "en" else "主题模式")
        if hasattr(self, 'lang_title_lbl'):
            self.lang_title_lbl.setText("Language" if lang == "en" else "语言")
        if hasattr(self, 'api_title_lbl'):
            self.api_title_lbl.setText("API Configuration" if lang == "en" else "API 配置")
        if hasattr(self, 'clip_title_lbl'):
            self.clip_title_lbl.setText("Clipboard Settings" if lang == "en" else "剪切板设置")
        if hasattr(self, 'shortcut_title_lbl'):
            self.shortcut_title_lbl.setText("Keyboard Shortcuts" if lang == "en" else "键盘快捷键")
        if hasattr(self, 'close_title_lbl'):
            self.close_title_lbl.setText("Close Behavior" if lang == "en" else "关闭窗口")
        if hasattr(self, 'settings_test_btn'):
            self.settings_test_btn.setText("Test" if lang == "en" else "测试连接")
        if hasattr(self, 'settings_btn_save'):
            self.settings_btn_save.setText("Save" if lang == "en" else "保存")
        if hasattr(self, 'settings_max_tip'):
            self.settings_max_tip.setText(
                "(Max records; oldest unlocked items auto-deleted when exceeded)" if lang == "en"
                else "(总条数上限；超出时自动删除最旧的非锁定项)")
        # 操作历史
        if hasattr(self, 'hist_title_lbl'):
            self.hist_title_lbl.setText("History" if lang == "en" else "操作历史")
        if hasattr(self, 'hist_max_label'):
            self.hist_max_label.setText("Max Items" if lang == "en" else "最大条数")
        if hasattr(self, 'hist_max_tip'):
            self.hist_max_tip.setText(
                "(Oldest records auto-deleted when exceeded)" if lang == "en"
                else "(超出时自动删除最旧记录)")
        # 关闭行为分段按钮
        if hasattr(self, 'close_btn_exit'):
            self.close_btn_exit.setText("Exit" if lang == "en" else "直接关闭")
            self.close_btn_tray.setText("Tray" if lang == "en" else "最小化到任务栏")
        # 同步分段按钮选中状态
        self._update_close_seg_style()
        # 快捷键芯片名称
        if hasattr(self, 'shortcut_title_lbl'):
            self.shortcut_title_lbl.setText("Keyboard Shortcuts" if lang == "en" else "快捷键")
        # Reset 按钮文字同步
        if hasattr(self, '_shortcut_edit_rows'):
            for row_data in self._shortcut_edit_rows:
                if len(row_data) >= 4:
                    row_data[3].setText("Reset" if lang == "en" else "重置")
        # 快捷键标签名称同步
        _shortcut_names_zh = {"capture": "截图识别", "canvas_fit": "画布自适应", "new_memo": "新建备忘录", "toggle_clipboard": "开关剪切板"}
        _shortcut_names_en = {"capture": "Capture", "canvas_fit": "Canvas Fit", "new_memo": "New Memo", "toggle_clipboard": "Toggle Clipboard"}
        if hasattr(self, '_shortcut_edit_rows'):
            for row_data in self._shortcut_edit_rows:
                if len(row_data) >= 2:
                    action = row_data[0]
                    name_map = _shortcut_names_en if lang == "en" else _shortcut_names_zh
                    row_data[1].setText(name_map.get(action, action))
        # 备忘录路径
        if hasattr(self, 'memo_path_title_lbl'):
            self.memo_path_title_lbl.setText("Storage Directory" if lang == "en" else "存储目录")
        if hasattr(self, 'memo_path_tip'):
            self.memo_path_tip.setText(
                "Leave empty for default path, entire .snaptrans folder will be moved"
                if lang == "en" else "留空则使用默认路径，切换后整个 .snaptrans 文件夹会移动")
        if hasattr(self, '_memo_browse_btn'):
            self._memo_browse_btn.setText("Browse" if lang == "en" else "浏览")
        # 剪切板设置
        if hasattr(self, 'settings_max_label'):
            self.settings_max_label.setText("Max Items" if lang == "en" else "最大条数")
        if hasattr(self, 'settings_max_tip'):
            self.settings_max_tip.setText(
                "(Max items; oldest unlocked items auto-deleted when exceeded)"
                if lang == "en" else "(总条数上限；超出时自动删除最旧的非锁定项)")
        # 同步分段按钮选中状态
        self._update_lang_seg_style()

    def _update_lang_seg_style(self):
        """刷新语言分段按钮的选中样式"""
        if not hasattr(self, 'btn_lang_en'):
            return
        t = DARK if self._is_dark() else LIGHT
        is_en = self._get_current_lang() == "en"
        self.btn_lang_en.setChecked(is_en)
        self.btn_lang_zh.setChecked(not is_en)
        btn_ss = f"QPushButton {{ background: transparent; color: {t.text_secondary}; border: none; border-radius: 8px; font-size: 13px; padding: 0 0 2px 0; }}"
        active_text_ss = f"QPushButton {{ background: transparent; color: #FFFFFF; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; padding: 0 0 2px 0; }}"
        self.btn_lang_en.setStyleSheet(active_text_ss if is_en else btn_ss)
        self.btn_lang_zh.setStyleSheet(active_text_ss if not is_en else btn_ss)
        self._lang_seg_ctrl.set_accent(t.accent)
        self._lang_seg_ctrl.update_position(animated=True)

    def _update_theme_seg_style(self):
        """刷新主题分段按钮的选中样式"""
        if not hasattr(self, 'btn_theme_dark'):
            return
        t = DARK if self._is_dark() else LIGHT
        is_dark = self._is_dark()
        self.btn_theme_dark.setChecked(is_dark)
        self.btn_theme_light.setChecked(not is_dark)
        btn_ss = f"QPushButton {{ background: transparent; color: {t.text_secondary}; border: none; border-radius: 8px; font-size: 13px; padding: 0 0 2px 0; }}"
        active_text_ss = f"QPushButton {{ background: transparent; color: #FFFFFF; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; padding: 0 0 2px 0; }}"
        self.btn_theme_dark.setStyleSheet(active_text_ss if is_dark else btn_ss)
        self.btn_theme_light.setStyleSheet(active_text_ss if not is_dark else btn_ss)
        self._theme_seg_ctrl.set_accent(t.accent)
        self._theme_seg_ctrl.update_position(animated=True)

    def _set_close_behavior(self, behavior: str):
        self._close_behavior = behavior
        self._update_close_seg_style()
        # 立即持久化到配置文件，无需等用户点"保存"
        config = self._load_config()
        config["close_behavior"] = behavior
        self._save_config(config)

    def _update_close_seg_style(self):
        """刷新关闭行为分段按钮的选中样式"""
        if not hasattr(self, 'close_btn_exit'):
            return
        t = DARK if self._is_dark() else LIGHT
        is_tray = getattr(self, '_close_behavior', 'exit') == 'tray'
        self.close_btn_exit.setChecked(not is_tray)
        self.close_btn_tray.setChecked(is_tray)
        btn_ss = f"QPushButton {{ background: transparent; color: {t.text_secondary}; border: none; border-radius: 8px; font-size: 13px; padding: 0 0 2px 0; }}"
        active_text_ss = f"QPushButton {{ background: transparent; color: #FFFFFF; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; padding: 0 0 2px 0; }}"
        self.close_btn_exit.setStyleSheet(active_text_ss if not is_tray else btn_ss)
        self.close_btn_tray.setStyleSheet(active_text_ss if is_tray else btn_ss)
        self._close_seg_ctrl.set_accent(t.accent)
        self._close_seg_ctrl.update_position(animated=True)
        # 更新文字
        _lang = self._get_current_lang()
        self.btn_theme_dark.setText("Dark" if _lang == "en" else "暗色")
        self.btn_theme_light.setText("Light" if _lang == "en" else "亮色")

    # ── 快捷键编辑 ──

    def eventFilter(self, obj, event):
        """拦截快捷键输入框的按键事件，录制快捷键"""
        from PySide6.QtCore import QEvent
        if (hasattr(obj, '_shortcut_action')
                and isinstance(obj, QLineEdit)
                and event.type() == QEvent.Type.KeyPress):
            key = event.key()
            mods = event.modifiers()
            if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                return False
            parts = []
            if mods & Qt.KeyboardModifier.ControlModifier:
                parts.append("Ctrl")
            if mods & Qt.KeyboardModifier.AltModifier:
                parts.append("Alt")
            if mods & Qt.KeyboardModifier.ShiftModifier:
                parts.append("Shift")
            if mods & Qt.KeyboardModifier.MetaModifier:
                parts.append("Meta")
            from PySide6.QtGui import QKeySequence
            seq = QKeySequence(key)
            key_name = seq.toString()
            if key_name:
                parts.append(key_name)
            combo = "+".join(parts)
            obj.setText(combo)
            if self._shortcut_mgr:
                self._shortcut_mgr.update_shortcut(obj._shortcut_action, combo)
            return True
        return super().eventFilter(obj, event)

    def _reset_shortcut(self, action: str, edit: QLineEdit):
        """重置某个快捷键为默认值"""
        from .shortcut_manager import DEFAULT_SHORTCUTS
        default_key = DEFAULT_SHORTCUTS.get(action, "")
        edit.setText(default_key)
        if self._shortcut_mgr:
            self._shortcut_mgr.update_shortcut(action, default_key)

    # ── 备忘录存储路径 ──

    def _load_memo_path_setting(self):
        """从配置加载存储目录"""
        self.settings_memo_path_input.setText(get_root_path())

    def _browse_memo_path(self):
        """浏览选择备忘录存储目录"""
        from PySide6.QtWidgets import QFileDialog
        dir_path = QFileDialog.getExistingDirectory(self, "选择备忘录存储目录")
        if dir_path:
            self.settings_memo_path_input.setText(dir_path)

    # ── 文本替换 CRUD ──

    # ── 配置加载/保存 ──

    def _load_api_to_inputs(self):
        """加载配置到设置页面输入框"""
        config = self._load_config()
        self.settings_key_input.setText(config.get("api_key", ""))
        self.settings_url_input.setText(config.get("api_url", "https://open.bigmodel.cn/api/paas/v4/chat/completions"))
        self.settings_model_input.setText(config.get("api_model", "glm-4-flash"))

    def _normalize_api_url(self, url: str) -> str:
        """规范化 API URL：确保以 /chat/completions 结尾，且不重复"""
        url = (url or "").rstrip("/")
        if not url:
            return "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        if url.endswith("/chat/completions"):
            return url
        return url + "/chat/completions"

    def _test_api_connection(self):
        """测试 API 连接"""
        import httpx
        _t_test = DARK if self._is_dark() else LIGHT
        api_key = self.settings_key_input.text().strip()
        api_url = self.settings_url_input.text().strip()
        api_model = self.settings_model_input.text().strip() or "glm-4-flash"

        if not api_key:
            self.settings_test_label.setText("⚠ 请填写 API Key")
            self.settings_test_label.setStyleSheet(f"font-size:12px; color:{_t_test.error}; border:none;")
            return

        self.settings_test_label.setText("⏳ 测试中...")
        self.settings_test_label.setStyleSheet(f"font-size:12px; color:{_t_test.accent}; border:none;")
        QApplication.processEvents()

        t0 = time.perf_counter()
        try:
            url = self._normalize_api_url(api_url)
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"model": api_model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}

            with httpx.Client(timeout=10) as client:
                resp = client.post(url, json=payload, headers=headers)

            elapsed_ms = int((time.perf_counter() - t0) * 1000)

            if resp.status_code == 200:
                from .ocr import test_vision_api
                vision_result = test_vision_api(api_key, api_url, api_model)
                err = vision_result.get("error", "")
                txt = vision_result.get("text", "")
                is_vision = (vision_result["success"] and not err
                             and ("测试" in txt or "OCR" in txt or "ocr" in txt))
                if is_vision:
                    self.settings_test_label.setText(
                        f"✅ 连接成功 ({elapsed_ms} ms) | 多模态模型，支持图片识别")
                    self.settings_test_label.setStyleSheet("font-size:12px; color:#2ecc71; border:none;")
                else:
                    self.settings_test_label.setText(
                        f"✅ 连接成功 ({elapsed_ms} ms) | ⚠ 文本模型，不支持图片文字识别")
                    _t_warn = DARK if self._is_dark() else LIGHT
                    self.settings_test_label.setStyleSheet(f"font-size:12px; color:{_t_warn.accent}; border:none;")
            elif resp.status_code == 401:
                self.settings_test_label.setText("❌ API Key 无效 (401)")
                self.settings_test_label.setStyleSheet(f"font-size:12px; color:{_t_test.error}; border:none;")
            elif resp.status_code == 404:
                msg = "❌ 路径错误 (404)"
                try:
                    detail = (resp.text or "")[:120].replace("\n", " ")
                    if detail:
                        msg += f": {detail}"
                except Exception:
                    pass
                self.settings_test_label.setText(msg)
                self.settings_test_label.setStyleSheet(f"font-size:12px; color:{_t_test.error}; border:none;")
            else:
                self.settings_test_label.setText(f"❌ HTTP {resp.status_code} ({elapsed_ms} ms)")
                self.settings_test_label.setStyleSheet(f"font-size:12px; color:{_t_test.error}; border:none;")
        except httpx.TimeoutException:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            self.settings_test_label.setText(f"❌ 网络超时 ({elapsed_ms} ms)")
            self.settings_test_label.setStyleSheet(f"font-size:12px; color:{_t_test.error}; border:none;")
        except httpx.ConnectError:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            self.settings_test_label.setText(f"❌ 无法连接服务器 ({elapsed_ms} ms)")
            self.settings_test_label.setStyleSheet(f"font-size:12px; color:{_t_test.error}; border:none;")
        except Exception as e:
            self.settings_test_label.setText(f"❌ 失败: {type(e).__name__}")
            self.settings_test_label.setStyleSheet(f"font-size:12px; color:{_t_test.error}; border:none;")

    def _save_api_config(self):
        """保存 API 配置"""
        config = self._load_config()
        config["api_key"] = self.settings_key_input.text().strip()
        config["api_url"] = self._normalize_api_url(self.settings_url_input.text().strip())
        config["api_model"] = self.settings_model_input.text().strip() or "glm-4-flash"
        config["close_behavior"] = getattr(self, '_close_behavior', 'exit')
        config["history_max_items"] = int(self.settings_hist_max_input.value())

        # 存储目录
        new_root = self.settings_memo_path_input.text().strip()
        current_dir = get_config_dir()
        current_root = os.path.dirname(current_dir)  # .snaptrans 的父目录

        if new_root and new_root != current_root:
            # 检查目标目录是否存在 .snaptrans
            dst_snaptrans = os.path.join(new_root, ".snaptrans")
            if os.path.exists(dst_snaptrans):
                reply = QMessageBox.question(
                    self,
                    "目标目录已存在数据",
                    f"{dst_snaptrans} 已存在\n\n如何处理？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                elif reply == QMessageBox.StandardButton.Yes:
                    move_mode = "merge"
                else:
                    move_mode = "overwrite"
            else:
                move_mode = "move"

            # 直接移动
            success = move_snaptrans_folder(current_root, new_root, mode=move_mode)
            if not success:
                self._show_message(QMessageBox.Icon.Warning, "错误", "移动文件夹失败")
                return

            # 保存锚点文件
            save_anchor(new_root)

            self._save_config(config)
            self._ocr_manager.set_config(config)
            self.settings_url_input.setText(config["api_url"])
            self._save_clip_setting(config=config)

            reply = QMessageBox.question(
                self,
                "重启生效",
                "存储目录已修改，需要重启生效。\n\n是否立即重启？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                import sys
                import subprocess
                subprocess.Popen([sys.executable] + sys.argv)
                sys.exit(0)
        else:
            self._save_config(config)
            self._ocr_manager.set_config(config)
            self.settings_url_input.setText(config["api_url"])
            self._save_clip_setting(config=config)
            self._show_message(QMessageBox.Icon.Information, "提示", "配置已保存")

    def _load_clip_setting_to_input(self):
        config = self._load_config()
        try:
            v = int(config.get("clipboard_max_items", 50))
        except Exception:
            v = 50
        self.settings_clip_max_input.setValue(max(10, min(500, v)))

    def _save_clip_setting(self, config=None):
        if config is None:
            config = self._load_config()
        config["clipboard_max_items"] = int(self.settings_clip_max_input.value())
        self._save_config(config)
        self._on_save_clipboard()

    def _load_hist_setting_to_input(self):
        config = self._load_config()
        try:
            v = int(config.get("history_max_items", 100))
        except Exception:
            v = 100
        self.settings_hist_max_input.setValue(max(10, min(500, v)))

    def _save_hist_setting(self, config=None):
        if config is None:
            config = self._load_config()
        config["history_max_items"] = int(self.settings_hist_max_input.value())
        self._save_config(config)
