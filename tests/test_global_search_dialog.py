from memopaws.search.global_search_dialog import GlobalSearchDialog


def test_global_search_dialog_collects_results(qapp):
    opened = []
    dialog = GlobalSearchDialog(
        search_provider=lambda query, scopes: [
            {"source": "memo", "title": "项目计划", "snippet": "实施 F6", "target_id": 1}
        ] if "memo" in scopes else [],
        open_result=lambda result: opened.append(result),
    )

    dialog.search_input.setText("F6")
    dialog.refresh_results()

    assert dialog.result_list.count() == 1
    dialog._open_selected(dialog.result_list.item(0))
    assert opened[0]["target_id"] == 1


def test_global_search_dialog_scope_filters_results(qapp):
    dialog = GlobalSearchDialog(
        search_provider=lambda query, scopes: [
            {"source": "clipboard", "title": "剪切板", "snippet": "hit", "target_id": None}
        ] if "clipboard" in scopes else [],
        open_result=lambda result: None,
    )

    dialog.chk_clipboard.setChecked(False)
    dialog.search_input.setText("hit")
    dialog.refresh_results()

    assert dialog.result_list.count() == 0


def test_global_search_dialog_accepts_search_provider_with_scope_indexes(qapp):
    opened = []
    dialog = GlobalSearchDialog(
        search_provider=lambda query, scopes: [
            {"source": "memo", "title": "项目计划", "snippet": "第二行命中", "target_id": 1, "index": 0, "line_number": 2}
        ],
        open_result=lambda result: opened.append(result),
    )

    dialog.search_input.setText("项目")
    dialog.refresh_results()
    dialog._open_selected(dialog.result_list.item(0))

    assert opened[0]["line_number"] == 2
