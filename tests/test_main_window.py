from unittest.mock import MagicMock

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtWidgets import QFrame

from memopaws.ui.main_window import MainWindow


def test_maximized_window_does_not_drag_from_nav_frame(qapp, monkeypatch):
    window = MainWindow()
    monkeypatch.setattr(window, "isMaximized", lambda: True)
    move_mock = MagicMock()
    monkeypatch.setattr(window, "move", move_mock)
    window._drag_pos = None

    press_event = MagicMock()
    press_event.type.return_value = QEvent.Type.MouseButtonPress
    press_event.button.return_value = Qt.MouseButton.LeftButton
    press_event.globalPosition.return_value = QPointF(100, 100)
    window.eventFilter(window.nav_sidebar.nav_frame, press_event)

    move_event = MagicMock()
    move_event.type.return_value = QEvent.Type.MouseMove
    move_event.buttons.return_value = Qt.MouseButton.LeftButton
    move_event.globalPosition.return_value = QPointF(120, 120)
    handled = window.eventFilter(window.nav_sidebar.nav_frame, move_event)

    assert handled is False
    move_mock.assert_not_called()


def test_maximized_window_does_not_drag_from_title_bar(qapp, monkeypatch):
    window = MainWindow()
    monkeypatch.setattr(window, "isMaximized", lambda: True)
    move_mock = MagicMock()
    monkeypatch.setattr(window, "move", move_mock)
    window._drag_pos = None
    title_bar = window.findChild(QFrame, "titleBar")

    press_event = MagicMock()
    press_event.button.return_value = Qt.MouseButton.LeftButton
    press_event.globalPosition.return_value = QPointF(100, 100)
    title_bar.mousePressEvent(press_event)

    move_event = MagicMock()
    move_event.buttons.return_value = Qt.MouseButton.LeftButton
    move_event.globalPosition.return_value = QPointF(120, 120)
    title_bar.mouseMoveEvent(move_event)

    move_mock.assert_not_called()


def test_maximized_window_disables_translucent_background(qapp):
    from PySide6.QtCore import Qt as QtCoreQt

    window = MainWindow()
    window.showMaximized()
    window._sync_window_surface()

    assert window.testAttribute(QtCoreQt.WidgetAttribute.WA_TranslucentBackground) is False


def test_normal_window_keeps_translucent_background(qapp):
    from PySide6.QtCore import Qt as QtCoreQt

    window = MainWindow()
    window.showNormal()
    window._sync_window_surface()

    assert window.testAttribute(QtCoreQt.WidgetAttribute.WA_TranslucentBackground) is True


def test_floating_widget_created_after_show(qapp):
    window = MainWindow()
    assert window._floating_widget is None
    window.show()
    qapp.processEvents()
    assert window._floating_widget is not None


def test_first_show_reveals_window_after_surface_ready(qapp, monkeypatch):
    window = MainWindow()
    calls = []

    monkeypatch.setattr(window, "_sync_window_surface", lambda: calls.append("sync"))
    monkeypatch.setattr(window, "_safe_set_title_bar_color", lambda: calls.append("title"))

    assert window.windowOpacity() == 0.0

    window.show()
    qapp.processEvents()

    assert window.windowOpacity() == 1.0
    assert window._startup_reveal_pending is False
    assert "sync" in calls
    assert "title" in calls


def test_first_show_reveal_runs_only_once(qapp, monkeypatch):
    window = MainWindow()
    calls = []

    original_finish = window._finish_startup_reveal

    def wrapped_finish():
        calls.append("finish")
        original_finish()

    monkeypatch.setattr(window, "_finish_startup_reveal", wrapped_finish)

    window.show()
    qapp.processEvents()
    window.hide()
    window.show()
    qapp.processEvents()

    assert calls == ["finish"]


def test_main_window_starts_frameless_before_first_show(qapp):
    window = MainWindow()

    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint


def test_central_widget_stays_hidden_before_main_window_show(qapp):
    window = MainWindow()

    assert window.centralWidget().isVisible() is False


def test_list_widgets_are_not_top_level_windows(qapp):
    window = MainWindow()

    assert window.recognize_page.status_list.isWindow() is False
    assert window.clipboard_page.clipboard_list.isWindow() is False


def test_toggle_floating_widget_syncs_settings_page(qapp, monkeypatch):
    window = MainWindow()
    window.settings_page._sync_floating_widget_visibility = MagicMock()
    window._floating_widget = MagicMock()

    window._set_floating_widget_visible(False)

    window.settings_page._sync_floating_widget_visibility.assert_called_once_with(False)


def test_toggle_floating_widget_refreshes_tray_menu(qapp):
    window = MainWindow()
    window._floating_widget = MagicMock()
    window._refresh_tray_menu = MagicMock()

    window._set_floating_widget_visible(False)

    window._refresh_tray_menu.assert_called_once_with()
