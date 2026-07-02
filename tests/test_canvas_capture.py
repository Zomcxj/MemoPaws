"""截图覆盖层单元测试"""

import pytest

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
