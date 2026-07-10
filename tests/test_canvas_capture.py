"""截图覆盖层单元测试"""

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QPaintEvent
from PySide6.QtWidgets import QApplication

from memopaws.canvas.capture import ScreenCaptureOverlay


class TestScreenCaptureOverlay:
    def test_has_signals(self):
        assert hasattr(ScreenCaptureOverlay, "captured")
        assert hasattr(ScreenCaptureOverlay, "saved")
        assert hasattr(ScreenCaptureOverlay, "copy_requested")
        assert hasattr(ScreenCaptureOverlay, "ocr_requested")
        assert hasattr(ScreenCaptureOverlay, "translate_requested")

    def test_create(self, qapp):
        overlay = ScreenCaptureOverlay()
        assert overlay is not None
        assert overlay.is_selecting is False
        assert overlay.selection_done is False
        overlay.close()

    def test_capture_overlay_enables_mouse_tracking(self, qapp):
        overlay = ScreenCaptureOverlay()
        assert overlay.hasMouseTracking() is True
        overlay.close()

    def test_capture_toolbar_uses_icon_buttons_and_no_size_inputs(self, qapp):
        overlay = ScreenCaptureOverlay()
        assert not hasattr(overlay, "input_w")
        assert not hasattr(overlay, "input_h")
        assert not hasattr(overlay, "btn_apply")
        assert overlay.btn_copy.icon().isNull() is False
        assert overlay.btn_save.icon().isNull() is False
        assert overlay.btn_ocr.icon().isNull() is False
        assert overlay.btn_trans.icon().isNull() is False
        assert overlay.btn_confirm.icon().isNull() is False
        assert overlay.btn_copy.toolTip() == "发送到贴图识别"
        assert overlay.btn_confirm.toolTip() == "复制并退出"
        overlay.close()

    def test_capture_toolbar_uses_camera_icon_for_send_to_recognize(self, qapp):
        overlay = ScreenCaptureOverlay()
        assert overlay.btn_copy.icon().isNull() is False
        overlay.close()

    def test_capture_toolbar_button_order_matches_expected(self, qapp):
        overlay = ScreenCaptureOverlay()
        layout = overlay._btn_bar.layout()
        assert layout.itemAt(0).widget() is overlay.btn_copy
        assert layout.itemAt(1).widget() is overlay.btn_pick_color
        assert layout.itemAt(2).widget() is overlay.btn_save
        assert layout.itemAt(3).widget() is overlay.btn_trans
        assert layout.itemAt(4).widget() is overlay.btn_ocr
        assert layout.itemAt(5).widget() is overlay.btn_cancel
        assert layout.itemAt(6).widget() is overlay.btn_confirm
        overlay.close()

    def test_capture_toolbar_uses_text_style_icons_for_ocr_and_translate(self, qapp):
        overlay = ScreenCaptureOverlay()
        assert overlay.btn_ocr.toolTip() == "识别"
        assert overlay.btn_trans.toolTip() == "翻译"
        overlay.close()

    def test_capture_overlay_has_size_label(self, qapp):
        overlay = ScreenCaptureOverlay()
        assert hasattr(overlay, "size_label")
        assert overlay.size_label.font().family() == "JetBrains Mono"
        assert overlay.size_label.font().pointSize() < 11
        assert "border: 1px solid" in overlay.size_label.styleSheet()
        assert "border-radius:6px" in overlay.size_label.styleSheet()
        assert "background: transparent" in overlay.size_label.styleSheet()
        overlay.close()

    def test_capture_overlay_positions_size_label_on_left_outside(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.resize(400, 300)
        overlay.start_point = QPoint(180, 80)
        overlay.end_point = QPoint(280, 160)

        overlay.paintEvent(QPaintEvent(overlay.rect()))

        assert overlay.size_label.text() == "101 × 81"
        assert overlay.size_label.x() == overlay.get_selection_rect().left()
        assert overlay.size_label.y() < overlay.get_selection_rect().top()
        overlay.close()

    def test_mouse_release_after_selection_does_not_require_existing_resize_flag(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(10, 10)
        overlay.end_point = QPoint(30, 30)
        overlay.selection_done = True

        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(30, 30),
            QPointF(30, 30),
            QPointF(30, 30),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

        overlay.mouseReleaseEvent(event)
        assert overlay.selection_done is True
        overlay.close()

    def test_capture_overlay_has_eight_anchor_points(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(50, 60)
        overlay.end_point = QPoint(150, 160)
        points = overlay._get_anchor_points()
        assert len(points) == 8
        overlay.close()

    def test_capture_overlay_updates_magnifier_and_rgb_on_mouse_move(self, qapp):
        overlay = ScreenCaptureOverlay()
        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(40, 40),
            QPointF(40, 40),
            QPointF(40, 40),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mouseMoveEvent(move_event)
        assert hasattr(overlay, "magnifier_label")
        assert overlay.magnifier_label.isHidden() is False
        assert "RGB" in overlay.color_label.text()
        assert overlay.color_label.text().splitlines()[0].startswith("RGB(")
        assert overlay.color_label.text().splitlines()[1].startswith("#")
        assert "按住 C 复制色值" in overlay.color_label.text()
        assert overlay.color_label.width() == overlay.magnifier_label.width()
        assert hasattr(overlay, "_magnifier_crosshair")
        overlay.close()

    def test_capture_overlay_shows_magnifier_on_first_selection_press(self, qapp):
        overlay = ScreenCaptureOverlay()
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(40, 40),
            QPointF(40, 40),
            QPointF(40, 40),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mousePressEvent(event)
        assert overlay.is_selecting is True
        assert overlay.magnifier_label.isHidden() is False
        assert overlay.color_label.isHidden() is False
        overlay.close()

    def test_capture_overlay_crosshair_reaches_magnifier_edges(self, qapp):
        overlay = ScreenCaptureOverlay()
        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(40, 40),
            QPointF(40, 40),
            QPointF(40, 40),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mouseMoveEvent(move_event)
        image = overlay.magnifier_label.pixmap().toImage()
        center_x = image.width() // 2
        center_y = image.height() // 2
        crosshair_color = "#d6b36a"
        assert image.pixelColor(0, center_y).name() == crosshair_color
        assert image.pixelColor(image.width() - 1, center_y).name() == crosshair_color
        assert image.pixelColor(center_x, 0).name() == crosshair_color
        assert image.pixelColor(center_x, image.height() - 1).name() == crosshair_color
        overlay.close()

    def test_capture_overlay_hides_magnifier_while_dragging_selection(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay._is_dragging = True
        overlay._mouse_pos = QPoint(100, 100)
        overlay._draw_magnifier()
        assert overlay.magnifier_label.isHidden() is True
        assert overlay.color_label.isHidden() is True
        overlay.close()

    def test_capture_overlay_keeps_magnifier_hidden_after_selection_done(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay._mouse_pos = QPoint(100, 100)
        overlay._draw_magnifier()
        assert overlay.magnifier_label.isHidden() is True
        assert overlay.color_label.isHidden() is True
        overlay.close()

    def test_capture_overlay_shows_magnifier_in_pick_color_mode_after_selection(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay._mouse_pos = QPoint(100, 100)
        overlay._toggle_pick_color_mode()
        overlay._draw_magnifier()
        assert overlay.magnifier_label.isHidden() is False
        assert overlay.color_label.isHidden() is False
        overlay.close()

    def test_capture_overlay_keeps_magnifier_visible_while_resizing_selection(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay._is_resizing = True
        overlay._mouse_pos = QPoint(180, 160)
        overlay._draw_magnifier()
        assert overlay.magnifier_label.isHidden() is False
        assert overlay.color_label.isHidden() is False
        assert hasattr(overlay, "_magnifier_crosshair")
        overlay.close()

    def test_capture_overlay_uses_open_hand_cursor_after_selection_done(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.is_selecting = True

        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(140, 120),
            QPointF(140, 120),
            QPointF(140, 120),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

        overlay.mouseReleaseEvent(event)
        assert overlay.selection_done is True
        assert overlay.cursor().shape() == Qt.CursorShape.OpenHandCursor
        overlay.close()

    def test_capture_overlay_clicking_edge_enters_resize_instead_of_drag(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True

        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(180, 120),
            QPointF(180, 120),
            QPointF(180, 120),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        overlay.mousePressEvent(event)
        assert overlay._is_resizing is True
        assert overlay._is_dragging is False
        overlay.close()

    def test_capture_overlay_right_middle_handle_resizes_only_right_edge(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True

        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(180, 120),
            QPointF(180, 120),
            QPointF(180, 120),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mousePressEvent(press_event)

        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(200, 120),
            QPointF(200, 120),
            QPointF(200, 120),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mouseMoveEvent(move_event)

        rect = overlay.get_selection_rect()
        assert rect.left() == 80
        assert rect.top() == 80
        assert rect.right() == 200
        assert rect.bottom() == 160
        overlay.close()

    def test_capture_overlay_resize_keeps_selection_at_least_3x3(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True

        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(180, 160),
            QPointF(180, 160),
            QPointF(180, 160),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mousePressEvent(press_event)

        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(81, 81),
            QPointF(81, 81),
            QPointF(81, 81),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mouseMoveEvent(move_event)

        rect = overlay.get_selection_rect()
        assert rect.width() == 3
        assert rect.height() == 3
        overlay.close()

    def test_capture_overlay_uses_closed_hand_cursor_while_dragging_selection_done(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True

        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(100, 100),
            QPointF(100, 100),
            QPointF(100, 100),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mousePressEvent(event)

        assert overlay._is_dragging is True
        assert overlay.cursor().shape() == Qt.CursorShape.ClosedHandCursor
        overlay.close()

    def test_capture_overlay_uses_horizontal_resize_cursor_on_right_middle_handle(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True

        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(180, 120),
            QPointF(180, 120),
            QPointF(180, 120),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mousePressEvent(event)

        assert overlay._is_resizing is True
        assert overlay.cursor().shape() == Qt.CursorShape.SizeHorCursor
        overlay.close()

    def test_capture_overlay_uses_size_fdiag_cursor_while_selecting(self, qapp):
        overlay = ScreenCaptureOverlay()
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(40, 40),
            QPointF(40, 40),
            QPointF(40, 40),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        overlay.mousePressEvent(event)

        assert overlay.cursor().shape() == Qt.CursorShape.SizeFDiagCursor
        overlay.close()

    def test_capture_overlay_uses_open_hand_cursor_when_hovering_selection_area(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True

        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(100, 100),
            QPointF(100, 100),
            QPointF(100, 100),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mouseMoveEvent(move_event)

        assert overlay.cursor().shape() == Qt.CursorShape.OpenHandCursor
        overlay.close()

    def test_capture_overlay_uses_arrow_cursor_in_pick_color_mode(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay._toggle_pick_color_mode()

        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(100, 100),
            QPointF(100, 100),
            QPointF(100, 100),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mouseMoveEvent(move_event)

        assert overlay.cursor().shape() == Qt.CursorShape.ArrowCursor
        overlay.close()

    def test_capture_overlay_restores_open_hand_cursor_after_exiting_pick_color_mode(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay._toggle_pick_color_mode()

        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(100, 100),
            QPointF(100, 100),
            QPointF(100, 100),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mousePressEvent(event)

        assert overlay._pick_color_mode is False
        assert overlay.cursor().shape() == Qt.CursorShape.OpenHandCursor
        overlay.close()

    def test_capture_overlay_shows_magnifier_when_resizing_from_edge(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True

        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(180, 120),
            QPointF(180, 120),
            QPointF(180, 120),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mousePressEvent(press_event)

        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(190, 120),
            QPointF(190, 120),
            QPointF(190, 120),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mouseMoveEvent(move_event)

        assert overlay._is_resizing is True
        assert overlay.magnifier_label.isHidden() is False
        assert overlay.color_label.isHidden() is False
        overlay.close()

    def test_capture_overlay_has_color_picker_button_after_selection(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay._show_action_bar(overlay.get_selection_rect())
        assert hasattr(overlay, "btn_pick_color")
        assert overlay.btn_pick_color.icon().isNull() is False
        layout = overlay._btn_bar.layout()
        assert layout.itemAt(1).widget() is overlay.btn_pick_color
        overlay.close()

    def test_capture_overlay_c_shortcut_copies_color_during_selection(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay._mouse_pos = QPoint(10, 10)

        class _KeyEvent:
            def key(self):
                return Qt.Key.Key_C

        overlay.keyPressEvent(_KeyEvent())
        assert QApplication.clipboard().text().startswith("RGB(")
        overlay.close()

    def test_capture_overlay_left_click_does_not_copy_color_after_selection(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        QApplication.clipboard().setText("")

        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(100, 100),
            QPointF(100, 100),
            QPointF(100, 100),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mousePressEvent(event)
        assert QApplication.clipboard().text() == ""
        overlay.close()

    def test_capture_overlay_c_shortcut_after_pick_button_copies_and_exits_pick_mode(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay._mouse_pos = QPoint(10, 10)
        overlay._toggle_pick_color_mode()

        class _KeyEvent:
            def key(self):
                return Qt.Key.Key_C

        overlay.keyPressEvent(_KeyEvent())
        assert QApplication.clipboard().text().startswith("RGB(")
        assert overlay._pick_color_mode is False
        overlay.close()

    def test_capture_overlay_right_click_after_selection_exits_pick_mode_only(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay._toggle_pick_color_mode()

        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(100, 100),
            QPointF(100, 100),
            QPointF(100, 100),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mousePressEvent(event)
        assert overlay._pick_color_mode is False
        assert overlay.selection_done is True

    def test_capture_overlay_confirm_button_emits_copy_request(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        captured = []
        copied = []
        overlay.captured.connect(lambda *args: captured.append(args))
        overlay.copy_requested.connect(lambda pixmap: copied.append(pixmap))

        overlay._on_confirm()

        assert captured == []
        assert len(copied) == 1
        overlay.close()

    def test_result_panel_can_resize_from_bottom_right_handle(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.show()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay.show_ocr_result("hello")
        panel = overlay._result_panel
        start_size = panel.size()

        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            QPointF(8, 8),
            QPointF(300, 300),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(20, 20),
            QPointF(20, 20),
            QPointF(360, 360),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(20, 20),
            QPointF(20, 20),
            QPointF(360, 360),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

        assert overlay.eventFilter(overlay._result_resize_handle, press_event) is True
        assert overlay.eventFilter(overlay._result_resize_handle, move_event) is True
        assert overlay.eventFilter(overlay._result_resize_handle, release_event) is True
        assert panel.width() > start_size.width()
        assert panel.height() > start_size.height()
        overlay.close()

    def test_result_panel_follows_selection_while_dragging(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.show()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay.show_ocr_result("hello")
        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(100, 100),
            QPointF(100, 100),
            QPointF(100, 100),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(130, 120),
            QPointF(130, 120),
            QPointF(130, 120),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        overlay.mousePressEvent(press_event)
        overlay.mouseMoveEvent(move_event)

        rect = overlay.get_selection_rect()
        panel = overlay._result_panel.geometry()
        expected_x = rect.right() + 16
        if expected_x + panel.width() > overlay.width() - 10:
            expected_x = rect.left() - panel.width() - 16
        expected_y = rect.top() + rect.height() // 2 - panel.height() // 2
        assert panel.left() == expected_x
        assert panel.top() == expected_y
        overlay.close()

    def test_result_panel_follows_selection_while_resizing(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.show()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay.show_ocr_result("hello")
        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(180, 120),
            QPointF(180, 120),
            QPointF(180, 120),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(220, 120),
            QPointF(220, 120),
            QPointF(220, 120),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        overlay.mousePressEvent(press_event)
        overlay.mouseMoveEvent(move_event)

        rect = overlay.get_selection_rect()
        panel = overlay._result_panel.geometry()
        expected_x = rect.right() + 16
        if expected_x + panel.width() > overlay.width() - 10:
            expected_x = rect.left() - panel.width() - 16
        expected_y = rect.top() + rect.height() // 2 - panel.height() // 2
        assert panel.left() == expected_x
        assert panel.top() == expected_y
        overlay.close()

    def test_result_panel_drag_moves_selection_by_the_same_delta(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)

        overlay._sync_screenshot_to_result(QPoint(30, -20))

        assert overlay.get_selection_rect().topLeft() == QPoint(110, 60)
        assert overlay.get_selection_rect().width() == 101
        assert overlay.get_selection_rect().height() == 81
        overlay.close()

    def test_result_panel_drag_handle_moves_panel_and_selection(self, qapp):
        overlay = ScreenCaptureOverlay()
        overlay.show()
        overlay.start_point = QPoint(80, 80)
        overlay.end_point = QPoint(180, 160)
        overlay.selection_done = True
        overlay.show_ocr_result("hello")
        panel_pos = overlay._result_panel.pos()

        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress, QPoint(10, 10), QPoint(10, 10),
            panel_pos + QPoint(10, 10), Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        )
        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove, QPoint(30, 0), QPoint(30, 0),
            panel_pos + QPoint(30, 0), Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        )
        release_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease, QPoint(30, 0), QPoint(30, 0),
            panel_pos + QPoint(30, 0), Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        )

        assert overlay.eventFilter(overlay._result_drag_handle, press_event) is True
        assert overlay.eventFilter(overlay._result_drag_handle, move_event) is True
        assert overlay.eventFilter(overlay._result_drag_handle, release_event) is True
        assert overlay._result_panel.pos() == panel_pos + QPoint(20, -10)
        assert overlay.get_selection_rect().topLeft() == QPoint(100, 70)
        overlay.close()

    def test_action_bar_uses_arrow_cursor(self, qapp):
        overlay = ScreenCaptureOverlay()

        assert overlay._btn_bar.cursor().shape() == Qt.CursorShape.ArrowCursor
        overlay.close()
