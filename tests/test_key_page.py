"""密钥页面单元测试"""

import pytest

from PySide6.QtWidgets import QWidget

from memopaws.keys.key_page import KeyPage, _run_llm_entry_tests
from memopaws.core.themes import DARK


class TestKeyPage:
    @pytest.fixture
    def parent(self, qapp):
        return QWidget()

    def test_create(self, qapp, parent):
        page = KeyPage(
            parent,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            show_message=lambda *a, **kw: None,
            get_icons_dir=lambda: "",
            get_icon_clr=lambda: "#fff",
            get_current_lang=lambda: "zh",
        )
        assert page is not None

    def test_apply_language(self, qapp, parent):
        page = KeyPage(
            parent,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            show_message=lambda *a, **kw: None,
            get_icons_dir=lambda: "",
            get_icon_clr=lambda: "#fff",
            get_current_lang=lambda: "zh",
        )
        page.apply_language("en")
        page.apply_language("zh")

    def test_latency_color(self, qapp, parent):
        page = KeyPage(
            parent,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            show_message=lambda *a, **kw: None,
            get_icons_dir=lambda: "",
            get_icon_clr=lambda: "#fff",
            get_current_lang=lambda: "zh",
        )
        assert page._get_latency_color(100) is not None
        assert page._get_latency_color(500) is not None
        assert page._get_latency_color(2000) is not None

    def test_llm_entry_tests_always_emit_done_when_client_fails(self, monkeypatch):
        def broken_client(*args, **kwargs):
            raise RuntimeError("client failed")

        monkeypatch.setattr("httpx.Client", broken_client)
        emitted = []

        _run_llm_entry_tests(
            [{"id": 1, "type": "llm", "url": "https://example.test/v1", "note": "model"}],
            get_plain_value=lambda entry_id: "key",
            emit=lambda *args: emitted.append(args),
        )

        assert emitted == [("1", 0, 0), ("__done__", 0, 0)]
