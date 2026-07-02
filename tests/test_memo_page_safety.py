import os

from memopaws.memo.memo_page import MemoPage


def test_safe_memo_path_strips_legacy_path_traversal(tmp_path):
    page = MemoPage.__new__(MemoPage)

    fname, fpath = page._safe_memo_path(str(tmp_path), "../secret.md")

    assert fname == "secret.md"
    assert os.path.commonpath([str(tmp_path), fpath]) == str(tmp_path)
