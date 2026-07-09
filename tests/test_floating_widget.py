import json
from PySide6.QtCore import QPointF, QEvent, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QPushButton

from memopaws.ui.floating_widget import FloatingWidget


def test_floating_widget_toggle_menu(qapp, tmp_path):
    config = tmp_path / "MemoPaws.json"
    config.write_text("{}", encoding="utf-8")
    widget = FloatingWidget(
        get_config_path=lambda: str(config),
        get_theme=lambda: type("T", (), {"bg_panel": "#fff", "border_subtle": "#ddd", "bg_neutral_button": "#eee", "text_primary": "#111", "bg_active": "#ccc", "accent": "#f60"})(),
        on_capture_ocr=lambda: None,
        on_paste_ocr=lambda: None,
        on_open_clipboard=lambda: None,
        on_open_memo=lambda: None,
        on_open_settings=lambda: None,
        on_hide_floating=lambda: None,
    )
    widget._toggle_menu()
    assert widget._menu_open
    assert widget._menu_panel is not None
    assert widget._menu_panel.isVisible()
    assert widget._menu_panel.windowFlags() & Qt.WindowType.Tool
    texts = [btn.text() for btn in widget._menu_panel.findChildren(QPushButton)]
    assert len(texts) == 6
    assert "退出悬浮窗" in texts
    widget._close_menu()
    assert not widget._menu_open


def test_floating_widget_saves_position(qapp, tmp_path):
    config = tmp_path / "MemoPaws.json"
    config.write_text("{}", encoding="utf-8")
    widget = FloatingWidget(
        get_config_path=lambda: str(config),
        get_theme=lambda: type("T", (), {"bg_panel": "#fff", "border_subtle": "#ddd", "bg_neutral_button": "#eee", "text_primary": "#111", "bg_active": "#ccc", "accent": "#f60"})(),
        on_capture_ocr=lambda: None,
        on_paste_ocr=lambda: None,
        on_open_clipboard=lambda: None,
        on_open_memo=lambda: None,
        on_open_settings=lambda: None,
        on_hide_floating=lambda: None,
    )
    widget.move(100, 140)
    widget._save_position()
    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["floating_widget_pos"] == {"x": 100, "y": 140}


def test_floating_widget_load_position_keeps_button_inside_screen(qapp, tmp_path):
    from PySide6.QtGui import QGuiApplication

    config = tmp_path / "MemoPaws.json"
    config.write_text('{"floating_widget_pos": {"x": 99999, "y": 120}}', encoding="utf-8")
    widget = FloatingWidget(
        get_config_path=lambda: str(config),
        get_theme=lambda: type("T", (), {"bg_panel": "#fff", "border_subtle": "#ddd", "bg_neutral_button": "#eee", "text_primary": "#111", "bg_active": "#ccc", "accent": "#f60"})(),
        on_capture_ocr=lambda: None,
        on_paste_ocr=lambda: None,
        on_open_clipboard=lambda: None,
        on_open_memo=lambda: None,
        on_open_settings=lambda: None,
        on_hide_floating=lambda: None,
    )
    screen = QGuiApplication.primaryScreen().availableGeometry()
    assert widget.x() <= screen.right() - widget.width() - widget.DEFAULT_RIGHT_MARGIN


def test_floating_widget_snaps_to_nearest_edge(qapp, tmp_path):
    from PySide6.QtGui import QGuiApplication

    config = tmp_path / "MemoPaws.json"
    config.write_text("{}", encoding="utf-8")
    widget = FloatingWidget(
        get_config_path=lambda: str(config),
        get_theme=lambda: type("T", (), {"bg_panel": "#fff", "border_subtle": "#ddd", "bg_neutral_button": "#eee", "text_primary": "#111", "bg_active": "#ccc", "accent": "#f60"})(),
        on_capture_ocr=lambda: None,
        on_paste_ocr=lambda: None,
        on_open_clipboard=lambda: None,
        on_open_memo=lambda: None,
        on_open_settings=lambda: None,
        on_hide_floating=lambda: None,
    )
    screen = QGuiApplication.primaryScreen().availableGeometry()
    widget.move(screen.center().x(), 140)
    widget._snap_inside_screen()
    assert widget.x() == screen.right() - widget.width() - widget.DEFAULT_EDGE_MARGIN
    assert widget.DEFAULT_EDGE_MARGIN == 0


def test_floating_widget_has_no_black_outer_frame(qapp, tmp_path):
    config = tmp_path / "MemoPaws.json"
    config.write_text("{}", encoding="utf-8")
    widget = FloatingWidget(
        get_config_path=lambda: str(config),
        get_theme=lambda: type("T", (), {"bg_panel": "#fff", "border_subtle": "#ddd", "bg_neutral_button": "#eee", "text_primary": "#111", "bg_active": "#ccc", "accent": "#f60"})(),
        on_capture_ocr=lambda: None,
        on_paste_ocr=lambda: None,
        on_open_clipboard=lambda: None,
        on_open_memo=lambda: None,
        on_open_settings=lambda: None,
        on_hide_floating=lambda: None,
    )
    assert widget.windowFlags() & Qt.WindowType.Tool
    assert not hasattr(widget, "outer")


def test_floating_widget_drag_cursor_changes_only_while_dragging(qapp, tmp_path):
    config = tmp_path / "MemoPaws.json"
    config.write_text("{}", encoding="utf-8")
    widget = FloatingWidget(
        get_config_path=lambda: str(config),
        get_theme=lambda: type("T", (), {"bg_panel": "#fff", "border_subtle": "#ddd", "bg_neutral_button": "#eee", "text_primary": "#111", "bg_active": "#ccc", "accent": "#f60"})(),
        on_capture_ocr=lambda: None,
        on_paste_ocr=lambda: None,
        on_open_clipboard=lambda: None,
        on_open_memo=lambda: None,
        on_open_settings=lambda: None,
        on_hide_floating=lambda: None,
    )
    assert widget.main_btn.cursor().shape() == Qt.CursorShape.OpenHandCursor

    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(8, 8),
        QPointF(8, 8),
        QPointF(widget.x() + 8, widget.y() + 8),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(8, 8),
        QPointF(8, 8),
        QPointF(widget.x() + 8, widget.y() + 8),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )

    widget.eventFilter(widget.main_btn, press)
    assert widget.main_btn.cursor().shape() == Qt.CursorShape.ClosedHandCursor
    widget.eventFilter(widget.main_btn, release)
    assert widget.main_btn.cursor().shape() == Qt.CursorShape.OpenHandCursor
