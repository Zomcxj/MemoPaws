from memopaws.memo.memo_search import memo_matches_query


def test_memo_matches_pinyin_initials():
    memo = {"title": "项目计划", "content": "", "tags": []}

    assert memo_matches_query(memo, "xmjh") is True
    assert memo_matches_query(memo, "xm") is True


def test_memo_matches_fuzzy_typo():
    memo = {"title": "Project Plan", "content": "", "tags": []}

    assert memo_matches_query(memo, "projct") is True


def test_memo_search_still_matches_content_and_tags():
    memo = {"title": "日记", "content": "今天修复 OCR", "tags": ["工作"]}

    assert memo_matches_query(memo, "ocr") is True
    assert memo_matches_query(memo, "工作") is True
