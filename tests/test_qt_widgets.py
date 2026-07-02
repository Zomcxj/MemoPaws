import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QVBoxLayout
from PySide6.QtCore import Qt

import pytest


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class TestBorderGlowWidget:
    def test_create_and_accent(self, qapp):
        from memopaws.canvas.border_glow_widget import BorderGlowWidget
        w = BorderGlowWidget()
        assert w is not None
        assert w._opacity == 0.0

        w.set_accent("#FF0000")
        assert w._color.name() == "#ff0000"

    def test_start_stop(self, qapp):
        from memopaws.canvas.border_glow_widget import BorderGlowWidget
        w = BorderGlowWidget()
        assert w.isHidden() is True
        w.start()
        assert w.isHidden() is False
        w.stop()
        assert w.isHidden() is True

    def test_glow_opacity_property(self, qapp):
        from memopaws.canvas.border_glow_widget import BorderGlowWidget
        w = BorderGlowWidget()
        assert w.get_glow_opacity() == 0.0
        w.set_glow_opacity(0.5)
        assert w.get_glow_opacity() == 0.5

    def test_default_radius(self, qapp):
        from memopaws.canvas.border_glow_widget import BorderGlowWidget
        w = BorderGlowWidget(radius=12)
        assert w._radius == 12

    def test_custom_accent_color(self, qapp):
        from memopaws.canvas.border_glow_widget import BorderGlowWidget
        w = BorderGlowWidget(accent_color="#00FF00")
        assert w._color.name() == "#00ff00"


class TestSegmentedControl:
    def test_create(self, qapp):
        from memopaws.ui.segmented_control import AnimatedSegmentedControl
        container = QFrame()
        container.resize(200, 40)
        btn_left = QPushButton("编辑")
        btn_right = QPushButton("预览")
        btn_left.setCheckable(True)
        btn_right.setCheckable(True)
        btn_left.setChecked(True)

        sc = AnimatedSegmentedControl(container, btn_left, btn_right)
        assert sc is not None
        assert sc._accent == "#E8875C"

    def test_set_accent(self, qapp):
        from memopaws.ui.segmented_control import AnimatedSegmentedControl
        container = QFrame()
        btn_left = QPushButton("A")
        btn_right = QPushButton("B")
        btn_left.setCheckable(True)
        btn_right.setCheckable(True)
        btn_left.setChecked(True)

        sc = AnimatedSegmentedControl(container, btn_left, btn_right)
        sc.set_accent("#FF0000")
        assert sc._accent == "#FF0000"
