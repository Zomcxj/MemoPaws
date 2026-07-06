from memopaws.search.global_search import search_all


def test_search_all_returns_results_from_multiple_sources():
    results = search_all(
        memos=[{"id": 1, "title": "项目计划", "content": "实施 F6 全局搜索", "tags": ["工作"]}],
        clipboard=[{"text": "全局搜索关键字"}],
        history=[{"type": "识别", "text": "全局搜索命中"}],
        query="全局搜索",
    )

    assert [item["source"] for item in results] == ["memo", "clipboard", "history"]


def test_search_all_exposes_title_snippet_and_target_id():
    results = search_all(
        memos=[{"id": 7, "title": "待办", "content": "修复 API 测试", "tags": []}],
        clipboard=[],
        history=[],
        query="api",
    )

    assert results[0]["title"] == "待办"
    assert results[0]["target_id"] == 7
    assert "API" in results[0]["snippet"]
    assert results[0]["line_number"] == 1


def test_search_all_returns_matching_memo_line_number():
    results = search_all(
        memos=[{"id": 1, "title": "待办", "content": "第一行\n第二行命中 API\n第三行", "tags": []}],
        clipboard=[],
        history=[],
        query="api",
    )

    assert results[0]["line_number"] == 2


def test_search_all_respects_scopes():
    results = search_all(
        memos=[{"id": 1, "title": "memo hit", "content": "memo hit", "tags": []}],
        clipboard=[{"text": "memo hit"}],
        history=[{"type": "历史", "text": "memo hit"}],
        query="memo",
        scopes=["clipboard"],
    )

    assert [item["source"] for item in results] == ["clipboard"]
