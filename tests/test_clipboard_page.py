"""剪贴板页面单元测试"""

import os
import json
import pytest

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QScrollArea, QWidget, QLabel
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent, QPixmap

from memopaws.clipboard.clipboard_page import ClipboardPage, ZoomableImageLabel
from memopaws.core.themes import DARK


class TestClipboardPage:
    @pytest.fixture
    def parent(self, qapp):
        return QWidget()

    @pytest.fixture
    def icons_dir(self):
        icons = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons")
        if os.path.isdir(icons):
            return icons
        pytest.skip("icons directory not found")

    def test_create(self, qapp, parent, icons_dir):
        page = ClipboardPage(
            parent,
            get_config_path=lambda: "",
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: [],
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )
        assert page is not None

    def test_preview_image_label_zooms_and_resets_to_fit(self, qapp):
        label = ZoomableImageLabel()
        label.resize(200, 100)
        label.set_image(QPixmap(400, 200))

        label.zoom(1.25)

        assert label.scale_factor == 1.25

        label.fit_to_view()

        assert label.scale_factor == 1.0

    def test_preview_image_label_drags_scroll_area_after_zooming(self, qapp):
        scroll = QScrollArea()
        scroll.resize(200, 100)
        label = ZoomableImageLabel()
        label.set_image(QPixmap(400, 200))
        label.zoom(2)
        scroll.setWidget(label)
        scroll.show()
        qapp.processEvents()

        QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=QPoint(150, 80))
        QTest.mouseMove(label, QPoint(100, 40))
        QTest.mouseRelease(label, Qt.MouseButton.LeftButton, pos=QPoint(100, 40))

        assert scroll.horizontalScrollBar().value() > 0
        assert scroll.verticalScrollBar().value() > 0

    def test_preview_image_drag_uses_pointer_delta_after_scrolls(self, qapp):
        scroll = QScrollArea()
        scroll.resize(200, 100)
        label = ZoomableImageLabel()
        label.set_image(QPixmap(400, 200))
        label.zoom(2)
        scroll.setWidget(label)
        scroll.show()
        qapp.processEvents()

        label.mousePressEvent(QMouseEvent(
            QMouseEvent.Type.MouseButtonPress, QPoint(150, 80), QPoint(150, 80),
            QPoint(150, 80), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ))
        label.mouseMoveEvent(QMouseEvent(
            QMouseEvent.Type.MouseMove, QPoint(100, 40), QPoint(100, 40),
            QPoint(100, 40), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ))
        # 内容已随第一次拖动滚动，局部坐标回到原点；全局指针仍继续移动。
        label.mouseMoveEvent(QMouseEvent(
            QMouseEvent.Type.MouseMove, QPoint(150, 80), QPoint(50, 0),
            QPoint(50, 0), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ))

        assert scroll.horizontalScrollBar().value() == 100
        assert scroll.verticalScrollBar().value() == 80

    def test_clipboard_change_queues_one_deferred_read(self, qapp, parent, icons_dir, monkeypatch):
        page = ClipboardPage(
            parent,
            get_config_path=lambda: "",
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: [],
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )
        queued = []
        monkeypatch.setattr(
            "memopaws.clipboard.clipboard_page.QTimer.singleShot",
            lambda delay, callback: queued.append((delay, callback)),
        )

        page._on_clipboard_changed()
        page._on_clipboard_changed()

        assert len(queued) == 1
        assert queued[0][0] == 0

    def test_search_input_filters_after_debounce(self, qapp, parent, icons_dir):
        data = [
            {"time": "2024-01-01 10:00:00", "text": "needle text", "locked": False},
            {"time": "2024-01-01 09:00:00", "text": "other text", "locked": False},
        ]
        page = ClipboardPage(
            parent,
            get_config_path=lambda: "",
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: data,
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )

        page.search_input.setText("needle")
        qapp.processEvents()

        assert [page.clipboard_list.item(i).isHidden() for i in range(page.clipboard_list.count())] == [False, False]

        QTest.qWait(page.SEARCH_DEBOUNCE_MS + 50)
        qapp.processEvents()

        assert [page.clipboard_list.item(i).isHidden() for i in range(page.clipboard_list.count())] == [False, True]

    def test_search_input_height_matches_view_switch_container(self, qapp, parent, icons_dir):
        page = ClipboardPage(
            parent,
            get_config_path=lambda: "",
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: [],
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )

        assert page.search_input.height() == page._view_seg_container.height()

    def test_duplicate_text_refreshes_time(self, qapp, parent, icons_dir):
        data = [{"time": "2024-01-01 09:00:00", "text": "same", "locked": False, "kind": "text"}]
        page = ClipboardPage(
            parent,
            get_config_path=lambda: "",
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: data,
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )

        page._add_clipboard_text_record("same")

        assert len(data) == 1
        assert data[0]["time"] != "2024-01-01 09:00:00"

    def test_add_clipboard_image_record_and_find_latest(self, qapp, parent, icons_dir, tmp_path, monkeypatch):
        data = []
        config = tmp_path / "MemoPaws.json"
        config.write_text("{}", encoding="utf-8")
        monkeypatch.setattr("memopaws.clipboard.clipboard_page.get_config_dir", lambda: str(tmp_path))
        page = ClipboardPage(
            parent,
            get_config_path=lambda: str(config),
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: data,
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )
        pixmap = QPixmap(20, 20)

        page._add_clipboard_image_record(pixmap)

        latest = page.latest_image_record()
        assert latest is not None
        assert latest["kind"] == "image"
        assert os.path.exists(latest["image_path"])

    def test_grid_locked_badge_updates_to_english(self, qapp, parent, icons_dir):
        data = [{"time": "2024-01-01 09:00:00", "text": "same", "locked": True, "kind": "text"}]
        lang = {"value": "zh"}
        page = ClipboardPage(
            parent,
            get_config_path=lambda: "",
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: data,
            set_clip_data=lambda d: None,
            get_current_lang=lambda: lang["value"],
        )

        page._set_view_mode("grid", save=False)
        lang["value"] = "en"
        page.apply_language("en")

        labels = [w.text() for w in page._grid_container.findChildren(QLabel)]
        assert "[Locked]" in labels

    def test_grid_card_height_is_increased(self, qapp, parent, icons_dir):
        data = [{"time": "2024-01-01 09:00:00", "text": "same", "locked": False, "kind": "text"}]
        page = ClipboardPage(
            parent,
            get_config_path=lambda: "",
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: data,
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )

        card = page._create_grid_card(0, data[0])

        assert card.minimumHeight() == 160
        assert card.maximumHeight() == 160

    def test_grid_image_thumbnail_area_height_is_increased(self, qapp, parent, icons_dir, tmp_path, monkeypatch):
        data = []
        config = tmp_path / "MemoPaws.json"
        config.write_text("{}", encoding="utf-8")
        monkeypatch.setattr("memopaws.clipboard.clipboard_page.get_config_dir", lambda: str(tmp_path))
        page = ClipboardPage(
            parent,
            get_config_path=lambda: str(config),
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: data,
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )
        pixmap = QPixmap(20, 20)
        page._add_clipboard_image_record(pixmap)

        card = page._create_grid_card(0, data[0])
        thumbs = card.findChildren(QLabel, "clipboardThumb")

        assert thumbs
        assert thumbs[0].minimumHeight() == 80
        assert thumbs[0].pixmap().height() == 80

    def test_grid_image_card_click_opens_one_preview(self, qapp, parent, icons_dir, tmp_path, monkeypatch):
        data = []
        config = tmp_path / "MemoPaws.json"
        config.write_text("{}", encoding="utf-8")
        monkeypatch.setattr("memopaws.clipboard.clipboard_page.get_config_dir", lambda: str(tmp_path))
        page = ClipboardPage(
            parent,
            get_config_path=lambda: str(config),
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: data,
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )
        page._add_clipboard_image_record(QPixmap(20, 20))
        previewed = []
        monkeypatch.setattr(page, "_preview_clipboard_image", previewed.append)
        card = page._create_grid_card(0, data[0])

        card.mousePressEvent(QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPoint(5, 5), QPoint(5, 5), QPoint(5, 5),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ))

        assert previewed == [data[0]["image_path"]]

    def test_grid_image_card_double_click_does_not_refresh_clipboard(self, qapp, parent, icons_dir, tmp_path, monkeypatch):
        data = []
        config = tmp_path / "MemoPaws.json"
        config.write_text("{}", encoding="utf-8")
        monkeypatch.setattr("memopaws.clipboard.clipboard_page.get_config_dir", lambda: str(tmp_path))
        page = ClipboardPage(
            parent,
            get_config_path=lambda: str(config),
            get_theme=lambda: DARK,
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: data,
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )
        page._add_clipboard_image_record(QPixmap(20, 20))
        refreshed = []
        monkeypatch.setattr(page, "_update_clipboard_list", lambda: refreshed.append(True))
        card = page._create_grid_card(0, data[0])

        card.mouseDoubleClickEvent(QMouseEvent(
            QMouseEvent.Type.MouseButtonDblClick,
            QPoint(5, 5), QPoint(5, 5), QPoint(5, 5),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ))

        assert refreshed == []

    def test_apply_theme_refreshes_grid_card_style(self, qapp, parent, icons_dir):
        class LightTheme:
            bg_panel = "#FFFFFF"
            border_subtle = "#E0DCD8"
            text_primary = "#1C1B1A"
            text_muted = "#9A9590"
            accent = "#D97757"
            bg_input = "#F5F3F0"
            bg_neutral_button = "#F0EDE8"
            bg_active = "#E8E5E0"
            text_secondary = "#6B6560"
            is_dark = False

        data = [{"time": "2024-01-01 09:00:00", "text": "same", "locked": False, "kind": "text"}]
        theme = {"value": DARK}
        page = ClipboardPage(
            parent,
            get_config_path=lambda: "",
            get_theme=lambda: theme["value"],
            get_icons_dir=lambda: icons_dir,
            get_icon_clr=lambda: "#fff",
            on_append_status=lambda *a: None,
            get_clip_data=lambda: data,
            set_clip_data=lambda d: None,
            get_current_lang=lambda: "zh",
        )

        page._set_view_mode("grid", save=False)
        theme["value"] = LightTheme()
        page.apply_theme()
        qapp.processEvents()

        card = page._grid_layout.itemAt(0).widget()
        assert card is not None
        assert "#FFFFFF" in card.styleSheet()
