"""剪贴板编辑对话框单元测试"""

import pytest

from snaptrans.clipboard.clipboard_dialog import ClipboardEditDialog
from snaptrans.core.themes import DARK, LIGHT


class TestClipboardEditDialog:
    def test_create_dark(self, qapp):
        dlg = ClipboardEditDialog(text="hello", theme=DARK)
        assert dlg is not None
        assert dlg.editor.toPlainText() == "hello"

    def test_create_light(self, qapp):
        dlg = ClipboardEditDialog(text="world", theme=LIGHT)
        assert dlg.editor.toPlainText() == "world"

    def test_empty_text(self, qapp):
        dlg = ClipboardEditDialog(theme=DARK)
        assert dlg.editor.toPlainText() == ""

    def test_get_text(self, qapp):
        dlg = ClipboardEditDialog(text="test content", theme=DARK)
        assert dlg.editor.toPlainText() == "test content"
