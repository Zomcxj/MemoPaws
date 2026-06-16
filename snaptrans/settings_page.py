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
from .utils import set_title_bar_color

logger = logging.getLogger(__name__)


def load_svg_icon(svg_path: str, size: int = 20, color: str = None):
    """加载 SVG 图标（从 main_window.py 复用）"""
    import re
    from PySide6.QtGui import QPixmap, QPainter
    from PySide6.QtSvg import QSvgRenderer

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


class AnimatedSegmentedControl:
    """带滑动指示器动画的分段按钮控制器"""

    def __init__(self, container, btn_left, btn_right):
        self.container = container
        self.btn_left = btn_left
        self.btn_right = btn_right
        self.accent_color = ""

        # 滑动指示器，作为 container 的子 widget，放在按钮下方
        self.indicator = QWidget(container)
        self.indicator.lower()

        # 动画
        self.anim = QPropertyAnimation(self.indicator, b"geometry")
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_accent(self, color):
        self.accent_color = color
        self.indicator.setStyleSheet(
            f"background: {color}; border-radius: 8px;"
        )

    def update_position(self, animated=True):
        """根据当前 checked 状态更新指示器位置"""
        btn = self.btn_left if self.btn_left.isChecked() else self.btn_right
        is_left = btn == self.btn_left
        w = btn.width() or self.btn_left.width()
        h = self.container.height() or 32
        x = 0 if is_left else w
        target = QRect(x, 0, w, h)
        cur = self.indicator.geometry()

        if animated and cur.isValid() and cur != target:
            self.anim.stop()
            self.anim.setStartValue(cur)
            self.anim.setEndValue(target)
            self.anim.start()
        else:
            self.indicator.setGeometry(target)


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
                 show_message):
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

        self._create_ui()

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
        self._theme_seg.setFixedHeight(32)
        self._theme_seg.setFixedWidth(160)
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
        self._lang_seg.setFixedHeight(32)
        self._lang_seg.setFixedWidth(160)
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
        self.settings_max_label = QLabel("最大条数")
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
        self.settings_max_tip = QLabel("(总条数上限；超出时自动删除最旧的非锁定项)")
        self.settings_max_tip.setStyleSheet(_init_tip_ss)
        max_row.addWidget(self.settings_max_tip, 0, Qt.AlignmentFlag.AlignVCenter)
        max_row.addStretch()
        clip_layout.addLayout(max_row)
        layout.addWidget(clip_group)

        self._load_clip_setting_to_input()

        # ── 快捷键 ──
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

        shortcuts = [("截图识别", "Alt+X"), ("画布自适应", "Ctrl+F"), ("粘贴图片", "Ctrl+V")]
        self._shortcut_name_labels = []
        self._shortcut_key_labels = []
        self._shortcut_chips = []
        shortcut_h_row = QHBoxLayout()
        shortcut_h_row.setSpacing(12)
        for name, key in shortcuts:
            chip = QFrame()
            chip.setObjectName("shortcutChip")
            from PySide6.QtWidgets import QSizePolicy
            chip.setMinimumHeight(28)
            chip.setMaximumHeight(28)
            chip.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed))
            chip.setStyleSheet(f"""
                QFrame {{
                    background: {_t.bg_neutral_button};
                    border: 1px solid {_t.border_subtle};
                    border-radius: 8px;
                    padding: 0;
                }}
            """)
            chip_lay = QHBoxLayout(chip)
            chip_lay.setContentsMargins(10, 4, 10, 4)
            chip_lay.setSpacing(8)
            n = QLabel(name)
            n.setStyleSheet(_init_sub_ss)
            chip_lay.addWidget(n)
            self._shortcut_name_labels.append(n)
            k = QLabel(key)
            k.setStyleSheet(f"font-size:12px; color:{_t.accent}; border:none; background:transparent; font-weight:bold;")
            chip_lay.addWidget(k)
            self._shortcut_key_labels.append(k)
            shortcut_h_row.addWidget(chip)
            self._shortcut_chips.append(chip)
        shortcut_h_row.addStretch()
        shortcut_layout.addLayout(shortcut_h_row)
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
        self._close_seg.setFixedHeight(32)
        self._close_seg.setFixedWidth(220)
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
        label_ss_sub = f"font-size:13px; color:{label_color}; border:none; background:transparent;"
        label_ss_tip = f"font-size:12px; color:{tip_color}; border:none; background:transparent;"
        for lbl in (self.settings_key_label, self.settings_url_label,
                     self.settings_model_label, self.settings_max_label):
            lbl.setStyleSheet(label_ss_sub)
        self.settings_max_tip.setStyleSheet(label_ss_tip)
        for lbl in self._shortcut_name_labels:
            lbl.setStyleSheet(f"font-size:13px; color:{label_color}; border:none; background:transparent;")
        for lbl in self._shortcut_key_labels:
            lbl.setStyleSheet(f"font-size:12px; color:{accent_color}; border:none; background:transparent; font-weight:bold;")
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
        self.shortcut_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        self.close_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")

        # 刷新快捷键 chip
        for chip in self._shortcut_chips:
            chip.setStyleSheet(f"""
                QFrame {{
                    background: {t.bg_neutral_button};
                    border: 1px solid {t.border_subtle};
                    border-radius: 8px;
                    padding: 0;
                }}
            """)
        for lbl in self._shortcut_name_labels:
            lbl.setStyleSheet(f"font-size:13px; color:{t.text_secondary}; border:none; background:transparent;")
        for lbl in self._shortcut_key_labels:
            lbl.setStyleSheet(f"font-size:12px; color:{t.accent}; border:none; background:transparent; font-weight:bold;")

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
        # 关闭行为分段按钮
        if hasattr(self, 'close_btn_exit'):
            self.close_btn_exit.setText("Exit" if lang == "en" else "直接关闭")
            self.close_btn_tray.setText("Tray" if lang == "en" else "最小化到任务栏")
        # 同步分段按钮选中状态
        self._update_close_seg_style()
        # 快捷键芯片名称
        if hasattr(self, '_shortcut_name_labels'):
            all_names = ["截图识别", "画布自适应", "粘贴图片"] if lang == "zh" else ["Screenshot", "Fit Canvas", "Paste Image"]
            for i, lbl in enumerate(self._shortcut_name_labels):
                if i < len(all_names):
                    lbl.setText(all_names[i])
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
