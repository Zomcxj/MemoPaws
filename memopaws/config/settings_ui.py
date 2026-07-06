"""设置页 UI 构建。"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QComboBox, QFrame, QMessageBox,
    QScrollArea,
)
from PySide6.QtCore import Qt, QTimer

from ..core.themes import DARK, LIGHT, get_theme_button_stylesheet, _inner_shadow
from ..core.utils import get_root_path, load_svg_icon
from ..ui.segmented_control import AnimatedSegmentedControl


def build_settings_ui(page):
    """构建 SettingsPage UI；回调和状态仍由 SettingsPage 提供。"""
    self = page
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
    browse_btn.setFixedSize(88, 28)
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
    self.memo_path_tip = QLabel("留空则使用默认路径，切换后整个 .memopaws 文件夹会移动")
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

