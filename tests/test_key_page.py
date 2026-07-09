"""密钥页面单元测试"""

import pytest
import tempfile
import shutil
import os

from PySide6.QtCore import QByteArray, QMimeData, QPoint, Qt
from PySide6.QtGui import QDragEnterEvent, QMouseEvent
from PySide6.QtWidgets import QLabel, QWidget

from memopaws.keys.key_page import KeyPage, DraggableCard, _run_llm_entry_tests
from memopaws.core.themes import DARK


class TestKeyPage:
    @pytest.fixture(autouse=True)
    def _km_tmpdir(self, monkeypatch):
        tmp_dir = tempfile.mkdtemp()
        keys_file = os.path.join(tmp_dir, "keys.json")
        monkeypatch.setattr("memopaws.keys.key_manager._get_keys_file", lambda: keys_file)
        yield
        shutil.rmtree(tmp_dir, ignore_errors=True)

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

    def test_swap_entries_blocks_cross_type_swap(self, qapp, parent):
        page = KeyPage(
            parent,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            show_message=lambda *a, **kw: None,
            get_icons_dir=lambda: "",
            get_icon_clr=lambda: "#fff",
            get_current_lang=lambda: "zh",
        )
        page._km.add_entry("llm", "llm", "a")
        page._km.add_entry("secret", "secret", "b")
        entries = page._km.get_entries()

        page._swap_entries(entries[0]["id"], entries[1]["id"])

        assert [e["order"] for e in page._km.get_entries()] == [0, 0]

    def test_rebuild_list_supports_draggable_llm_cards(self, qapp, parent):
        page = KeyPage(
            parent,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            show_message=lambda *a, **kw: None,
            get_icons_dir=lambda: "",
            get_icon_clr=lambda: "#fff",
            get_current_lang=lambda: "zh",
        )
        page._km.add_entry("llm", "llm", "a")

        page._rebuild_list()

        cards = [page._llm_grid.itemAt(i).widget() for i in range(page._llm_grid.count())]
        assert any(isinstance(card, DraggableCard) for card in cards)

    def test_drag_enter_keeps_card_stylesheet_valid(self, qapp):
        card = DraggableCard(1)
        card.setStyleSheet("QFrame { border: 1px solid #333; background: #111; }")
        card.setProperty("original_style", card.styleSheet())
        card.setProperty("accent_color", "#2563EB")
        mime = QMimeData()
        mime.setData("application/x-keycard", QByteArray(b"2"))
        event = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)

        card.dragEnterEvent(event)

        assert "border: 2px solid #2563EB;" in card.styleSheet()

    def test_drop_event_on_child_forwards_to_card_drop_handler(self, qapp, parent):
        page = KeyPage(
            parent,
            get_theme=lambda: DARK,
            is_dark=lambda: True,
            show_message=lambda *a, **kw: None,
            get_icons_dir=lambda: "",
            get_icon_clr=lambda: "#fff",
            get_current_lang=lambda: "zh",
        )
        page._km.add_entry("llm", "llm", "a")
        page._km.add_entry("llm", "llm", "b")
        page._rebuild_list()
        target_card = page._llm_grid.itemAt(1).widget()
        source_id = page._km.get_entries()[0]["id"]
        child = target_card.findChildren(QWidget)[0]
        called = []
        target_card.dropEvent = lambda event: called.append(True)

        class FakeDropEvent:
            def type(self):
                return QtCore.QEvent.Type.Drop

            def mimeData(self):
                mime = QMimeData()
                mime.setData("application/x-keycard", QByteArray(str(source_id).encode()))
                return mime

            def acceptProposedAction(self):
                pass

        from PySide6 import QtCore
        event = FakeDropEvent()

        target_card.eventFilter(child, event)

        assert called == [True]

    def test_drag_preview_uses_original_card_content_before_placeholder(self, qapp, monkeypatch):
        card = DraggableCard(1)
        child = QLabel("original", card)
        child.show()
        card.resize(120, 60)
        card.show()
        card._drag_start_pos = QPoint(0, 0)
        states = []

        original_grab = card.grab

        def capture_grab(*args, **kwargs):
            states.append(child.isHidden())
            return original_grab(*args, **kwargs)

        monkeypatch.setattr(card, "grab", capture_grab)

        class FakeDrag:
            def __init__(self, widget):
                pass

            def setMimeData(self, mime):
                pass

            def setPixmap(self, pixmap):
                pass

            def setHotSpot(self, pos):
                pass

            def exec(self, action):
                return action

        monkeypatch.setattr("memopaws.keys.key_page.QDrag", FakeDrag)

        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPoint(20, 0),
            QPoint(20, 0),
            QPoint(20, 0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        card.mouseMoveEvent(move_event)

        assert states == [False]
