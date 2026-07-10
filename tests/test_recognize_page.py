from unittest.mock import MagicMock

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QCloseEvent, QPixmap

from memopaws.ui.recognize_page import RecognizePage
from memopaws.core.themes import DARK


def test_paste_ocr_simple_reuses_main_recognize_layout(qapp):
    parent = QWidget()
    switched = []
    page = RecognizePage(
        parent,
        get_config_path=lambda: "",
        get_theme=lambda: DARK,
        is_dark=lambda: True,
        get_icons_dir=lambda: "",
        get_icon_clr=lambda: "#fff",
        ocr_manager=MagicMock(),
        translator=MagicMock(),
        on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: switched.append(name),
    )
    pixmap = QPixmap(20, 20)
    page._get_pixmap_from_clipboard = lambda: pixmap
    page._run_ocr_ai = MagicMock()

    page.paste_ocr_simple()

    assert switched == ["贴图识别"]
    assert page.canvas.display_pixmap is not None
    page._run_ocr_ai.assert_called_once()


def test_start_capture_hides_window_without_minimize_and_starts_overlay(qapp, monkeypatch):
    parent = QWidget()
    page = RecognizePage(
        parent,
        get_config_path=lambda: "",
        get_theme=lambda: DARK,
        is_dark=lambda: True,
        get_icons_dir=lambda: "",
        get_icon_clr=lambda: "#fff",
        ocr_manager=MagicMock(),
        translator=MagicMock(),
        on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: None,
    )

    class FakeWindow:
        def __init__(self):
            self.minimized = False
            self.hidden = False
            self.visible = True

        def showMinimized(self):
            self.minimized = True

        def hide(self):
            self.hidden = True
            self.visible = False

        def isVisible(self):
            return self.visible

    called = []
    fake_window = FakeWindow()
    page.window = lambda: fake_window
    monkeypatch.setattr("memopaws.ui.recognize_page.QTimer.singleShot", lambda delay, fn: called.append((delay, fn)))

    page.start_capture()

    assert fake_window.minimized is False
    assert fake_window.hidden is True
    assert len(called) == 1
    assert called[0][0] == 220
    called[0][1]()
    assert fake_window.isVisible() is False


def test_clear_image_stops_running_workers_and_blocks_stale_result_writeback(qapp):
    parent = QWidget()
    page = RecognizePage(
        parent,
        get_config_path=lambda: "",
        get_theme=lambda: DARK,
        is_dark=lambda: True,
        get_icons_dir=lambda: "",
        get_icon_clr=lambda: "#fff",
        ocr_manager=MagicMock(),
        translator=MagicMock(),
        on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: None,
    )

    class FakeWorker:
        def __init__(self):
            self.quit_called = False
            self.wait_called = False

        def isRunning(self):
            return True

        def quit(self):
            self.quit_called = True

        def wait(self, timeout):
            self.wait_called = timeout == 500

    ocr_worker = FakeWorker()
    translate_worker = FakeWorker()
    page._ocr_worker = ocr_worker
    page._translate_worker = translate_worker
    page.ocr_text.setPlainText("old ocr")
    page.translate_text.setPlainText("old trans")

    page.clear_image()

    assert ocr_worker.quit_called is True
    assert ocr_worker.wait_called is True
    assert translate_worker.quit_called is True
    assert translate_worker.wait_called is True
    assert page.ocr_text.toPlainText() == ""
    assert page.translate_text.toPlainText() == ""


def test_capture_ocr_ignores_result_from_replaced_worker(qapp, monkeypatch):
    page = RecognizePage(
        QWidget(), get_config_path=lambda: "", get_theme=lambda: DARK,
        is_dark=lambda: True, get_icons_dir=lambda: "", get_icon_clr=lambda: "#fff",
        ocr_manager=MagicMock(), translator=MagicMock(), on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: None,
    )
    workers = []

    class FakeWorker:
        def __init__(self, *args):
            self.result_ready = MagicMock()
            self.finished = MagicMock()
            self.result_ready.connect.side_effect = lambda callback: setattr(self, "on_done", callback)
            workers.append(self)

        def isRunning(self): return False
        def start(self): pass
        def deleteLater(self): pass

    overlay = MagicMock()
    page.capture_overlay = overlay
    monkeypatch.setattr("memopaws.ui.recognize_page._CaptureOCRWorker", FakeWorker)

    page._on_capture_ocr(QPixmap(1, 1))
    page._on_capture_ocr(QPixmap(1, 1))
    workers[0].on_done("stale")
    workers[1].on_done("current")

    overlay.show_ocr_result.assert_called_once_with("current")


def test_capture_translate_ignores_result_from_replaced_worker(qapp, monkeypatch):
    page = RecognizePage(
        QWidget(), get_config_path=lambda: "", get_theme=lambda: DARK,
        is_dark=lambda: True, get_icons_dir=lambda: "", get_icon_clr=lambda: "#fff",
        ocr_manager=MagicMock(), translator=MagicMock(), on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: None,
    )
    workers = []

    class FakeWorker:
        def __init__(self, *args):
            self.ocr_done = MagicMock()
            self.translate_done = MagicMock()
            self.finished = MagicMock()
            self.ocr_done.connect.side_effect = lambda callback: setattr(self, "on_ocr_done", callback)
            self.translate_done.connect.side_effect = lambda callback: setattr(self, "on_translate_done", callback)
            workers.append(self)

        def isRunning(self): return False
        def start(self): pass
        def deleteLater(self): pass

    overlay = MagicMock()
    page.capture_overlay = overlay
    monkeypatch.setattr("memopaws.ui.recognize_page._CaptureTranslateWorker", FakeWorker)

    page._on_capture_translate(QPixmap(1, 1))
    page._on_capture_translate(QPixmap(1, 1))
    workers[0].on_ocr_done("stale ocr")
    workers[0].on_translate_done("stale ocr", "stale translation")
    workers[1].on_ocr_done("current ocr")
    workers[1].on_translate_done("current ocr", "current translation")

    assert overlay.show_ocr_result.call_args_list[-1].args == ("current ocr",)
    overlay.show_translate_result.assert_called_once_with("current translation")


def test_start_capture_overlay_waits_until_window_hidden(qapp, monkeypatch):
    parent = QWidget()
    page = RecognizePage(
        parent,
        get_config_path=lambda: "",
        get_theme=lambda: DARK,
        is_dark=lambda: True,
        get_icons_dir=lambda: "",
        get_icon_clr=lambda: "#fff",
        ocr_manager=MagicMock(),
        translator=MagicMock(),
        on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: None,
    )

    class FakeWindow:
        def __init__(self):
            self.visible = True

        def isVisible(self):
            return self.visible

    class FakeOverlay:
        def __init__(self):
            self.shown = False

        def show(self):
            self.shown = True

        def activateWindow(self):
            pass

        def raise_(self):
            pass

        @property
        def captured(self):
            return MagicMock(connect=lambda fn: None)

        @property
        def copy_requested(self):
            return MagicMock(connect=lambda fn: None)

        @property
        def capture_to_recognize_requested(self):
            return MagicMock(connect=lambda fn: None)

        @property
        def saved(self):
            return MagicMock(connect=lambda fn: None)

        @property
        def ocr_requested(self):
            return MagicMock(connect=lambda fn: None)

        @property
        def translate_requested(self):
            return MagicMock(connect=lambda fn: None)

        @property
        def closed(self):
            return MagicMock(connect=lambda fn: None)

    scheduled = []
    fake_window = FakeWindow()
    fake_overlay = FakeOverlay()
    page.window = lambda: fake_window
    monkeypatch.setattr("memopaws.ui.recognize_page.ScreenCaptureOverlay", lambda: fake_overlay)
    monkeypatch.setattr("memopaws.ui.recognize_page.QTimer.singleShot", lambda delay, fn: scheduled.append((delay, fn)))

    page._start_capture_overlay()

    assert fake_overlay.shown is False
    assert len(scheduled) == 1
    assert scheduled[0][0] == 50


def test_start_capture_overlay_shows_virtual_desktop_geometry_without_fullscreen(qapp, monkeypatch):
    parent = QWidget()
    page = RecognizePage(
        parent,
        get_config_path=lambda: "", get_theme=lambda: DARK, is_dark=lambda: True,
        get_icons_dir=lambda: "", get_icon_clr=lambda: "#fff", ocr_manager=MagicMock(),
        translator=MagicMock(), on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: None,
    )
    signals = [MagicMock(connect=lambda fn: None) for _ in range(7)]

    class FakeOverlay:
        def __init__(self):
            self.show_called = False
            (self.captured, self.copy_requested, self.capture_to_recognize_requested,
             self.saved, self.ocr_requested, self.translate_requested, self.closed) = signals

        def show(self):
            self.show_called = True

        def showFullScreen(self):
            raise AssertionError("覆盖层必须保留虚拟桌面 geometry")

        def activateWindow(self):
            pass

        def raise_(self):
            pass

    overlay = FakeOverlay()
    page.window = lambda: type("W", (), {"isVisible": lambda self: False})()
    monkeypatch.setattr("memopaws.ui.recognize_page.ScreenCaptureOverlay", lambda: overlay)

    page._start_capture_overlay()

    assert overlay.show_called is True


def test_capture_to_recognize_reuses_paste_ocr_simple(qapp):
    parent = QWidget()
    page = RecognizePage(
        parent,
        get_config_path=lambda: "",
        get_theme=lambda: DARK,
        is_dark=lambda: True,
        get_icons_dir=lambda: "D:/VsPro/MemoPaws/assets/icons",
        get_icon_clr=lambda: "#fff",
        ocr_manager=MagicMock(),
        translator=MagicMock(),
        on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: None,
    )
    pixmap = QPixmap(20, 20)
    called = []
    page.paste_ocr_simple = lambda: called.append(True)

    class FakeClipboardPage:
        def _add_clipboard_image_record(self, pixmap):
            pass

    class FakeWindow:
        clipboard_page = FakeClipboardPage()

    page.window = lambda: FakeWindow()

    page._on_capture_to_recognize(pixmap)

    assert called == [True]


def test_close_event_stops_running_capture_workers(qapp):
    parent = QWidget()
    page = RecognizePage(
        parent,
        get_config_path=lambda: "",
        get_theme=lambda: DARK,
        is_dark=lambda: True,
        get_icons_dir=lambda: "",
        get_icon_clr=lambda: "#fff",
        ocr_manager=MagicMock(),
        translator=MagicMock(),
        on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: None,
    )

    class FakeWorker:
        def __init__(self):
            self.interruption_requested = False
            self.wait_called = False
            self.running = True

        def requestInterruption(self):
            self.interruption_requested = True

        def isRunning(self):
            return self.running

        def wait(self, timeout=None):
            self.wait_called = True
            self.running = False
            return True

    page._ocr_worker = FakeWorker()
    page._translate_worker = FakeWorker()
    page._capture_workers = {page._ocr_worker, page._translate_worker}

    page.closeEvent(QCloseEvent())

    assert page._ocr_worker is None
    assert page._translate_worker is None


def test_capture_save_uses_memopaws_timestamp_name(qapp, monkeypatch):
    parent = QWidget()
    page = RecognizePage(
        parent,
        get_config_path=lambda: "",
        get_theme=lambda: DARK,
        is_dark=lambda: True,
        get_icons_dir=lambda: "",
        get_icon_clr=lambda: "#fff",
        ocr_manager=MagicMock(),
        translator=MagicMock(),
        on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: None,
    )
    pixmap = QPixmap(10, 10)
    seen = {}
    def fake_get_save_file_name(*args):
        seen["default"] = args[2]
        return ("", "")
    monkeypatch.setattr(
        "memopaws.ui.recognize_page.QFileDialog.getSaveFileName",
        fake_get_save_file_name,
    )
    page.window = lambda: type("W", (), {"showMinimized": lambda self: None})()

    page._on_capture_save(pixmap)

    assert seen["default"].startswith("memopaws_")
    assert seen["default"].endswith(".png")


def test_capture_overlay_closed_cleans_capture_workers(qapp):
    parent = QWidget()
    page = RecognizePage(
        parent,
        get_config_path=lambda: "",
        get_theme=lambda: DARK,
        is_dark=lambda: True,
        get_icons_dir=lambda: "",
        get_icon_clr=lambda: "#fff",
        ocr_manager=MagicMock(),
        translator=MagicMock(),
        on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: None,
    )

    class FakeWorker:
        def __init__(self):
            self.running = True
            self.interrupted = False

        def requestInterruption(self):
            self.interrupted = True

        def isRunning(self):
            return self.running

        def wait(self, timeout=None):
            self.running = False
            return True

    page._ocr_worker = FakeWorker()
    page._translate_worker = FakeWorker()
    page._capture_workers = {page._ocr_worker, page._translate_worker}

    page._on_capture_overlay_closed()

    assert page.capture_overlay is None
    assert page._ocr_worker is None
    assert page._translate_worker is None


def test_export_image_uses_memopaws_timestamp_name(qapp, monkeypatch):
    parent = QWidget()
    page = RecognizePage(
        parent,
        get_config_path=lambda: "",
        get_theme=lambda: DARK,
        is_dark=lambda: True,
        get_icons_dir=lambda: "",
        get_icon_clr=lambda: "#fff",
        ocr_manager=MagicMock(),
        translator=MagicMock(),
        on_append_status=lambda *args: None,
        on_switch_to_page=lambda name: None,
    )
    page.canvas.display_pixmap = QPixmap(10, 10)
    seen = {}
    def fake_get_save_file_name(*args):
        seen["default"] = args[2]
        return ("", "")
    monkeypatch.setattr(
        "memopaws.ui.recognize_page.QFileDialog.getSaveFileName",
        fake_get_save_file_name,
    )

    page.export_image()

    assert seen["default"].startswith("memopaws_")
    assert seen["default"].endswith(".png")
