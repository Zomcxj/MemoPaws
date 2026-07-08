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
