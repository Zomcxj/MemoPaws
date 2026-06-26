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
    accent="#D97757", accent_hover="#E08D6F",
    bg_main="#262624", bg_panel="#2C2C2B", bg_input="#1B1B19",
    bg_neutral_button="#2C2C2B", bg_active="#3E3E38",
    text_primary="#F1F1EF", text_secondary="#C3C0B6", text_muted="#B7B5A9",
    border_subtle="#3E3E38", border_strong="#52514A",
    error="#EF4444",
    separator="#3E3E38", progress_bg="#3E3E38", progress_chunk="#D97757",
    scroll_handle="#52514A",
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
        QWidget {{ color: {t.text_primary}; font-size: 14px; font-family: 'Poppins', 'Segoe UI', 'Microsoft YaHei', sans-serif; selection-background-color: {t.accent}; selection-color: #141413; }}
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
            background: {t.bg_active};
            border: 1px solid {t.border_strong};
        }}
        QPushButton:pressed {{
            background: {t.border_subtle};
        }}
        QPushButton#accent {{
            background: {t.accent};
            color: #141413;
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
            border: 1px solid {t.border_strong};
            border-radius: 8px;
            padding: 8px 12px;
            selection-background-color: {t.accent};
            selection-color: #141413;
        }}
        QTextEdit:focus, QLineEdit:focus {{
            border: 1px solid {t.accent};
        }}
        QComboBox {{
            background: {t.bg_input};
            color: {t.text_primary};
            border: 1px solid {t.border_strong};
            border-radius: 8px;
            padding: 4px 12px;
            font-size: 13px;
        }}
        QComboBox:hover {{ border: 1px solid {t.text_muted}; }}
        QComboBox:focus {{ border: 1px solid {t.accent}; }}
        QComboBox QAbstractItemView {{
            background: {t.bg_panel};
            color: {t.text_primary};
            border: 1px solid {t.border_subtle};
            selection-background-color: {t.accent};
            selection-color: #141413;
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
        QListWidget::item:selected {{ background: {t.accent}; color: #141413; }}
        QSlider::groove:horizontal {{ background: {t.border_subtle}; height: 4px; border-radius: 2px; }}
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
        QMessageBox QPushButton:hover, QDialog QPushButton:hover {{ background: {t.bg_active}; }}
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
            color: #141413;
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
            color: {t.text_muted};
            font-size: 12px;
            font-style: italic;
        }}
        QFrame#titleBar {{
            background: transparent;
            border: none;
        }}
    """


def get_scroll_area_stylesheet(t: ThemeColors) -> str:
    return f"""
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 8px; border: none; margin: 4px 2px 4px 2px; }}
        QScrollBar::handle:vertical {{ background: {t.scroll_handle}; border-radius: 4px; min-height: 30px; }}
        QScrollBar::handle:vertical:hover {{ background: {t.text_muted}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; border: none; background: none; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        QScrollBar:horizontal {{ background: transparent; height: 8px; border: none; margin: 2px 4px 2px 4px; }}
        QScrollBar::handle:horizontal {{ background: {t.scroll_handle}; border-radius: 4px; min-width: 30px; }}
        QScrollBar::handle:horizontal:hover {{ background: {t.text_muted}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; border: none; background: none; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
    """


def get_progress_bar_stylesheet(t: ThemeColors) -> str:
    return f"""
        QProgressBar {{ background: {t.progress_bg}; border: none; border-radius: 9999px; min-height: 6px; max-height: 6px; text-align: center; color: {t.text_primary}; font-size: 12px; }}
        QProgressBar::chunk {{ background: {t.progress_chunk}; border-radius: 9999px; }}
    """


def get_text_edit_stylesheet(t: ThemeColors) -> str:
    return f"""
        QTextEdit {{
            border: 1px solid {t.border_strong};
            border-radius: 8px;
            padding: 12px 14px;
            font-size: 14px;
            background: {t.bg_input};
            color: {t.text_primary};
            selection-background-color: {t.accent};
            selection-color: #141413;
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
        QListWidget::item {{ padding: 6px 8px; border: none; border-radius: 4px; }}
        QListWidget::item:selected {{ background: {t.bg_active}; border: none; outline: none; color: {t.text_primary}; }}
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
        QPushButton:hover {{ background: {t.bg_active}; color: {t.text_primary}; }}
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
        QPushButton:hover {{ background: {t.bg_active}; }}
    """


def get_theme_button_stylesheet(t: ThemeColors) -> str:
    return f"""
        QPushButton {{
            background: {t.accent};
            color: #141413;
            border: none;
            border-radius: 8px;
            padding: 6px 16px;
            min-width: 80px;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton:hover {{ background: {t.accent_hover}; }}
    """


def get_config_dialog_stylesheet(t: ThemeColors = None) -> str:
    if t is None:
        t = DARK
    return f"""
        QDialog {{ background: {t.bg_panel}; color: {t.text_primary}; }}
        QGroupBox {{ border: 1px solid {t.border_subtle}; border-radius: 12px; margin-top: 10px; padding-top: 10px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {t.text_muted}; }}
        QRadioButton {{ spacing: 8px; }}
        QLineEdit {{
            background: {t.bg_input}; border: 1px solid {t.border_strong}; border-radius: 8px;
            padding: 8px 12px; color: {t.text_primary};
        }}
        QLineEdit:focus {{ border: 1px solid {t.accent}; }}
        QPushButton {{
            background: {t.bg_neutral_button}; color: {t.text_primary};
            border: 1px solid {t.border_subtle}; border-radius: 8px; padding: 8px 20px;
        }}
        QPushButton:hover {{ background: {t.bg_active}; }}
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


# Claude Design System 侧边栏样式
def get_sidebar_stylesheet(t: ThemeColors) -> str:
    return f"""
        QFrame#sidebar, QWidget#sidebar {{
            background-color: #1F1E1D;
            border-right: 1px solid {t.border_subtle};
        }}
        QPushButton#navButton {{
            background-color: transparent;
            color: #C3C0B6;
            border: none;
            border-radius: 8px;
            padding: 10px 16px;
            font-size: 14px;
            font-weight: 500;
            text-align: left;
            min-height: 40px;
        }}
        QPushButton#navButton:hover {{
            background-color: #0F0F0E;
        }}
        QPushButton#navButton:checked,
        QPushButton#navButton:selected {{
            background-color: #343434;
            color: #FBFBFB;
        }}
    """
