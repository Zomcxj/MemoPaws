"""系统托盘 Mixin 单元测试"""

import pytest
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QWidget

from memopaws.ui.tray import TrayMixin


class TestTrayMixin:
    def test_mixin_has_required_methods(self):
        assert hasattr(TrayMixin, "_setup_tray")
        assert hasattr(TrayMixin, "_tray_activated")
        assert hasattr(TrayMixin, "_show_from_tray")
        assert hasattr(TrayMixin, "_quit_app")
