from unittest.mock import MagicMock

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPixmap

from memopaws.ui.recognize_page import RecognizePage
from memopaws.core.themes import DARK


def test_paste_ocr_simple_reuses_main_recognize_layout(qapp):
    parent = QWidget()
    switched = []
    page = RecognizePage(
        parent,
        get_config_path=lambda: "",
        get_theme=lambda: DARK,
        is_dark=lambda: True,
        get_icons_dir=lambda: "",
        get_icon_clr=lambda: "#fff",
        ocr_manager=MagicMock(),
        translator=MagicMock(),
        on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: switched.append(name),
    )
    pixmap = QPixmap(20, 20)
    page._get_pixmap_from_clipboard = lambda: pixmap
    page._run_ocr_ai = MagicMock()

    page.paste_ocr_simple()

    assert switched == ["贴图识别"]
    assert page.canvas.display_pixmap is not None
    page._run_ocr_ai.assert_called_once()
