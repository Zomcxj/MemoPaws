"""画布控件单元测试"""

import pytest

from PySide6.QtWidgets import QTextEdit, QListWidget

from memopaws.canvas.canvas import RoundedTextEdit, RoundedListWidget, CanvasWidget


class TestRoundedTextEdit:
    def test_create(self, qapp):
        w = RoundedTextEdit(radius=12)
        assert w is not None
        assert w._radius == 12

    def test_custom_radius(self, qapp):
        w = RoundedTextEdit(radius=8)
        assert w._radius == 8


class TestRoundedListWidget:
    def test_create(self, qapp):
        w = RoundedListWidget(radius=12)
        assert w is not None
        assert w._radius == 12


class TestCanvasWidget:
    def test_create(self, qapp):
        canvas = CanvasWidget()
        assert canvas is not None
        assert canvas._theme_dark is True

    def test_set_theme_dark(self, qapp):
        canvas = CanvasWidget()
        canvas.set_theme(dark=True)
        assert canvas._theme_dark is True

    def test_set_theme_light(self, qapp):
        canvas = CanvasWidget()
        canvas.set_theme(dark=False)
        assert canvas._theme_dark is False

    def test_set_pen_color(self, qapp):
        from PySide6.QtGui import QColor
        canvas = CanvasWidget()
        canvas.set_pen_color(QColor("#FF0000"))
        assert canvas.pen_color.name() == "#ff0000"

    def test_undo_stack_empty(self, qapp):
        canvas = CanvasWidget()
        assert canvas.undo_stack == []

    def test_push_undo_no_pixmap(self, qapp):
        canvas = CanvasWidget()
        canvas.push_undo()
        assert canvas.undo_stack == []
