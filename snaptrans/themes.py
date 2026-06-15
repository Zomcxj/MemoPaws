"""Theme system - stitch dark / light presets"""

from dataclasses import dataclass

@dataclass
class ThemeColors:
    name: str
    is_dark: bool
    accent: str
    accent_hover: str
    bg_main: str
    bg_panel: str
    bg_input: str
    bg_neutral_button: str
    bg_active: str
    text_primary: str
    text_secondary: str
    text_muted: str
    border_subtle: str
    border_strong: str
    error: str
    separator: str
    progress_bg: str
    progress_chunk: str
    scroll_handle: str


DARK = ThemeColors(
    name="Dark Theme", is_dark=True,
    accent="#E8875C", accent_hover="#D67A50",
    bg_main="#1A1717", bg_panel="#2A2525", bg_input="#1E1B1B",
    bg_neutral_button="#2A2525", bg_active="#353533",
    text_primary="#F0E8E4", text_secondary="#9E9590", text_muted="#7A7270",
    border_subtle="#3A3535", border_strong="#4A4545",
    error="#E74C3C",
    separator="#3A3535", progress_bg="#2A2525", progress_chunk="#E8875C",
    scroll_handle="#3A3535",
)

LIGHT = ThemeColors(
    name="Light Theme", is_dark=False,
    accent="#D97757", accent_hover="#C56646",
    bg_main="#FAF8F6", bg_panel="#FFFFFF", bg_input="#F5F3F0",
    bg_neutral_button="#F0EDE8", bg_active="#E8E5E0",
    text_primary="#1C1B1A", text_secondary="#6B6560", text_muted="#9A9590",
    border_subtle="#E0DCD8", border_strong="#C9C5BD",
    error="#BA1A1A",
    separator="#E5E2DD", progress_bg="#E5E2DD", progress_chunk="#D97757",
    scroll_handle="rgba(0,0,0,0.15)",
)


def _hover(t: ThemeColors) -> str:
    return t.bg_neutral_button if t.is_dark else "#E8E8E8"


def _inner_shadow(t: ThemeColors) -> str:
    return "inset 0 1px 3px rgba(0,0,0,0.5)" if t.is_dark else "inset 0 1px 2px rgba(0,0,0,0.1)"


def get_main_stylesheet(t: ThemeColors) -> str:
    return f"""
        QMainWindow {{ background: {t.bg_main}; }}
        QWidget {{ color: {t.text_primary}; font-size: 14px; font-family: 'Microsoft YaHei', 'JetBrains Mono', 'Inter', sans-serif; }}
        QFrame#card {{
            background: {t.bg_panel};
            border: 1px solid {t.border_subtle};
            border-radius: 12px;
        }}
        QFrame#navFrame, QFrame#navFrameCollapsed {{
            background: {t.bg_main};
            border: none;
            border-radius: 14px;
        }}
        QFrame#nav_active {{
            background: {t.bg_active};
            border: none;
            border-radius: 8px;
        }}
        QPushButton {{
            background: {t.bg_neutral_button};
            color: {t.text_primary};
            border: 1px solid {t.border_subtle};
            border-radius: 8px;
            padding: 4px 12px;
            font-size: 14px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background: {_hover(t)};
            border: 1px solid {t.border_strong};
        }}
        QPushButton:pressed {{
            background: {t.bg_active};
        }}
        QPushButton#accent {{
            background: {t.accent};
            color: #FFFFFF;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 14px;
            font-weight: 600;
        }}
        QPushButton#accent:hover {{
            background: {t.accent_hover};
        }}
        QTextEdit, QLineEdit, QSpinBox {{
            background: {t.bg_input};
            color: {t.text_primary};
            border: 1px solid {t.border_subtle};
            border-radius: 8px;
            padding: 8px 12px;
            selection-background-color: {t.accent};
            selection-color: white;
            {_inner_shadow(t)}
        }}
        QTextEdit:focus, QLineEdit:focus {{
            border: 1px solid {t.accent};
        }}
        QComboBox {{
            background: {t.bg_input};
            color: {t.text_primary};
            border: 1px solid {t.border_subtle};
            border-radius: 8px;
            padding: 4px 12px;
            font-size: 13px;
        }}
        QComboBox:hover {{ border: 1px solid {t.border_strong}; }}
        QComboBox QAbstractItemView {{
            background: {t.bg_panel};
            color: {t.text_primary};
            border: 1px solid {t.border_subtle};
            selection-background-color: {t.bg_active};
        }}
        QListWidget {{
            background: {t.bg_main};
            color: {t.text_primary};
            border: 1px solid {t.border_subtle};
            border-radius: 8px;
            padding: 4px;
        }}
        QListWidget::item {{ padding: 6px 8px; border-radius: 4px; }}
        QListWidget::item:hover {{ background: {t.bg_active}; }}
        QListWidget::item:selected {{ background: {t.accent}; color: #FFFFFF; }}
        QSlider::groove:horizontal {{ background: {t.bg_input}; height: 4px; border-radius: 2px; }}
        QSlider::handle:horizontal {{
            background: {t.accent}; width: 14px; height: 14px;
            margin: -5px 0; border-radius: 7px; border: none;
        }}
        QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
        QMessageBox, QDialog {{ background: {t.bg_panel}; color: {t.text_primary}; border: none; }}
        QMessageBox QLabel, QDialog QLabel {{ color: {t.text_primary}; border: none; background: transparent; }}
        QMessageBox QPushButton, QDialog QPushButton {{
            background: {t.bg_neutral_button}; color: {t.text_primary};
            border: 1px solid {t.border_subtle}; border-radius: 8px; padding: 6px 20px; min-width: 60px;
        }}
        QMessageBox QPushButton:hover, QDialog QPushButton:hover {{ background: {_hover(t)}; }}
        QMenu {{
            background: {t.bg_panel};
            color: {t.text_primary};
            border: 1px solid {t.border_subtle};
            border-radius: 8px;
            padding: 4px;
        }}
        QMenu::item {{
            background: transparent;
            color: {t.text_primary};
            padding: 6px 24px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background: {t.accent};
            color: #FFFFFF;
        }}
        QLabel#title {{
            color: {t.text_primary};
            font-size: 24px;
            font-weight: 700;
        }}
        QLabel#subtitle {{
            color: {t.text_secondary};
            font-size: 14px;
            font-weight: 400;
        }}
        QLabel#section {{
            color: {t.text_primary};
            font-size: 16px;
            font-weight: 600;
        }}
        QLabel#hint {{
            color: {t.text_secondary};
            font-size: 12px;
            font-style: italic;
        }}
        QFrame#titleBar {{
            background: transparent;
            border-bottom: 1px solid {t.border_subtle};
        }}
    """


def get_scroll_area_stylesheet(t: ThemeColors) -> str:
    return f"""
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 6px; border-radius: 3px; }}
        QScrollBar::handle:vertical {{ background: {t.scroll_handle}; border-radius: 3px; min-height: 30px; }}
        QScrollBar::handle:vertical:hover {{ background: {t.border_strong}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    """


def get_progress_bar_stylesheet(t: ThemeColors) -> str:
    return f"""
        QProgressBar {{ background: {t.progress_bg}; border:none; border-radius:3px; height:6px; }}
        QProgressBar::chunk {{ background: {t.progress_chunk}; border-radius:3px; }}
    """


def get_text_edit_stylesheet(t: ThemeColors) -> str:
    return f"""
        QTextEdit {{
            border: 1px solid {t.border_subtle};
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 14px;
            background: {t.bg_input};
            color: {t.text_primary};
            {_inner_shadow(t)}
        }}
        QTextEdit:focus {{ border: 1px solid {t.accent}; }}
    """


def get_status_list_stylesheet(t: ThemeColors) -> str:
    return f"""
        QListWidget {{
            background: {t.bg_main};
            border: none;
            font-size: 13px;
            color: {t.text_secondary};
            padding: 4px;
            outline: none;
        }}
        QListWidget::item {{ padding: 6px 8px; border: none; }}
        QListWidget::item:selected {{ background: {t.bg_active}; border: none; outline: none; }}
        QListWidget::item:focus {{ border: none; outline: none; }}
        QListWidget::item:hover {{ background: {t.bg_active}; }}
    """


def get_clear_history_stylesheet(t: ThemeColors) -> str:
    return f"""
        QPushButton {{
            background: {t.bg_neutral_button};
            color: {t.text_secondary};
            border: 1px solid {t.border_subtle};
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 13px;
        }}
        QPushButton:hover {{ background: {_hover(t)}; color: {t.text_primary}; }}
    """


def get_arrow_button_stylesheet(t: ThemeColors) -> str:
    return f"""
        QPushButton {{
            background: {t.bg_neutral_button};
            color: {t.accent};
            border: 1px solid {t.border_subtle};
            border-radius: 8px;
            font-size: 18px;
            font-weight: bold;
            padding: 0;
        }}
        QPushButton:hover {{ background: {_hover(t)}; }}
    """


def get_theme_button_stylesheet(t: ThemeColors) -> str:
    return f"""
        QPushButton {{
            background: {t.accent};
            color: #FFFFFF;
            border: none;
            border-radius: 8px;
            padding: 6px 16px;
            min-width: 80px;
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton:hover {{ background: {t.accent_hover}; }}
    """


def get_config_dialog_stylesheet(t: ThemeColors = None) -> str:
    if t is None:
        t = DARK
    return f"""
        QDialog {{ background: {t.bg_panel}; color: {t.text_primary}; }}
        QGroupBox {{ border: 1px solid {t.border_subtle}; border-radius: 8px; margin-top: 10px; padding-top: 10px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {t.text_secondary}; }}
        QRadioButton {{ spacing: 8px; }}
        QLineEdit {{
            background: {t.bg_input}; border: 1px solid {t.border_subtle}; border-radius: 8px;
            padding: 8px 12px; color: {t.text_primary};
            {_inner_shadow(t)}
        }}
        QLineEdit:focus {{ border: 1px solid {t.accent}; }}
        QPushButton {{
            background: {t.bg_neutral_button}; color: {t.text_primary};
            border: 1px solid {t.border_subtle}; border-radius: 8px; padding: 8px 20px;
        }}
        QPushButton:hover {{ background: {_hover(t)}; }}
    """


def get_canvas_stylesheet(t: ThemeColors, is_dragging: bool = False) -> str:
    if is_dragging:
        border_w = "2px"
        border_color = t.accent
    else:
        border_w = "1px"
        border_color = t.border_subtle
    return f"""
        QLabel {{
            background: {t.bg_input};
            border: {border_w} solid {border_color};
            border-radius: 12px;
        }}
    """
