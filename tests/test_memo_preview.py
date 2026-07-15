from types import SimpleNamespace

from PySide6.QtGui import QColor

from memopaws.memo.markdown_viewer import MarkdownViewer
from memopaws.memo.memo_page import MemoPage


class _PreviewStub:
    def __init__(self):
        self.calls = []

    def set_markdown_html(self, html, bg_color):
        self.calls.append((html, bg_color))


class _WebPageStub:
    def __init__(self):
        self.javascript = []

    def runJavaScript(self, script):
        self.javascript.append(script)


def test_prewarm_preview_loads_rendered_html_into_hidden_viewer():
    page = MemoPage.__new__(MemoPage)
    page._memo_md_source = "# Current memo"
    page.memo_data = []
    page._get_theme = lambda: SimpleNamespace(bg_main="#123456")
    page._render_preview = lambda content: "<html>rendered</html>"
    page.memo_split_preview = _PreviewStub()

    page._prewarm_preview()

    assert page.memo_split_preview.calls == [
        ("<html>rendered</html>", QColor("#123456"))
    ]


def test_first_load_queues_newest_html_until_navigation_finishes(monkeypatch):
    viewer = MarkdownViewer.__new__(MarkdownViewer)
    web_page = _WebPageStub()
    viewer._current_html = ""
    viewer._first_load = True
    viewer._load_finished = False
    viewer.page = lambda: web_page
    viewer.setHtml = lambda html, _url: None
    monkeypatch.setattr(
        MarkdownViewer,
        "content_loaded",
        SimpleNamespace(emit=lambda: None),
    )

    viewer.set_markdown_html("<html><style>old</style><body>old</body></html>")
    viewer.set_markdown_html("<html><style>new</style><body>newest</body></html>")

    assert web_page.javascript == []

    viewer._on_load_finished(True)

    assert len(web_page.javascript) == 1
    assert "newest" in web_page.javascript[0]
