"""备忘录控件单元测试"""

import pytest

from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Qt

from memopaws.memo.memo_widgets import MarkdownHighlighter, ZoomableTextEdit


class TestMarkdownHighlighter:
    def test_create(self, qapp):
        edit = QTextEdit()
        hl = MarkdownHighlighter(edit.document(), is_dark_fn=lambda: True)
        assert hl is not None

    def test_state_constants(self):
        assert MarkdownHighlighter.STATE_NORMAL == 0
        assert MarkdownHighlighter.STATE_CODE_BLOCK == 1

    def test_highlight_normal_text(self, qapp):
        edit = QTextEdit()
        hl = MarkdownHighlighter(edit.document(), is_dark_fn=lambda: True)
        edit.setPlainText("Hello World")
        assert edit.toPlainText() == "Hello World"

    def test_highlight_heading(self, qapp):
        edit = QTextEdit()
        hl = MarkdownHighlighter(edit.document(), is_dark_fn=lambda: True)
        edit.setPlainText("# Title")
        assert edit.toPlainText() == "# Title"

    def test_highlight_code_block(self, qapp):
        edit = QTextEdit()
        hl = MarkdownHighlighter(edit.document(), is_dark_fn=lambda: True)
        text = "```python\ncode\n```"
        edit.setPlainText(text)
        assert edit.toPlainText() == text

    def test_light_theme(self, qapp):
        edit = QTextEdit()
        hl = MarkdownHighlighter(edit.document(), is_dark_fn=lambda: False)
        assert hl is not None

    def test_no_is_dark_fn(self, qapp):
        edit = QTextEdit()
        hl = MarkdownHighlighter(edit.document())
        assert hl is not None


class TestZoomableTextEdit:
    def test_create(self, qapp):
        edit = ZoomableTextEdit()
        assert edit is not None
        assert edit.font_size == 14

    def test_set_font_size(self, qapp):
        edit = ZoomableTextEdit()
        edit.set_font_size(20)
        assert edit.font_size == 20

    def test_set_font_size_min_clamp(self, qapp):
        edit = ZoomableTextEdit()
        edit.set_font_size(2)
        assert edit.font_size == 8

    def test_set_font_size_max_clamp(self, qapp):
        edit = ZoomableTextEdit()
        edit.set_font_size(100)
        assert edit.font_size == 40

    def test_zoom_changed_signal(self, qapp):
        edit = ZoomableTextEdit()
        received = []
        edit.zoomChanged.connect(lambda s: received.append(s))
        edit.set_font_size(20)
        assert edit.font_size == 20
        assert received == []  # set_font_size 不发信号，只有 wheelEvent 才发
