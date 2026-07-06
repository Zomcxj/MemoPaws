"""跨备忘录、剪切板、历史记录的全局搜索。"""


def search_all(*, memos, clipboard, history, query: str, scopes=None):
    keyword = (query or "").strip().lower()
    if not keyword:
        return []
    scopes = set(scopes or ["memo", "clipboard", "history"])

    results = []
    for idx, memo in enumerate(memos if "memo" in scopes else []):
        haystack = "\n".join([memo.get("title", ""), memo.get("content", ""), " ".join(memo.get("tags", []))])
        if keyword in haystack.lower():
            line_number = _match_line_number(memo.get("title", ""), memo.get("content", ""), query)
            results.append({
                "source": "memo",
                "title": memo.get("title", "备忘录"),
                "snippet": _snippet(haystack, query),
                "target_id": memo.get("id"),
                "index": idx,
                "line_number": line_number,
            })
    for idx, record in enumerate(clipboard if "clipboard" in scopes else []):
        text = record.get("text", "")
        if keyword in text.lower():
            results.append({
                "source": "clipboard",
                "title": "剪切板",
                "snippet": _snippet(text, query),
                "target_id": idx,
            })
    for idx, record in enumerate(history if "history" in scopes else []):
        text = record.get("text", "")
        if keyword in text.lower():
            results.append({
                "source": "history",
                "title": record.get("type", "历史记录"),
                "snippet": _snippet(text, query),
                "target_id": idx,
            })
    return results


def _snippet(text: str, query: str) -> str:
    stripped = (text or "").replace("\n", " ").strip()
    if not stripped:
        return ""
    lower = stripped.lower()
    keyword = query.lower()
    idx = lower.find(keyword)
    if idx < 0:
        return stripped[:60]
    start = max(0, idx - 12)
    end = min(len(stripped), idx + len(query) + 24)
    return stripped[start:end]


def _match_line_number(title: str, content: str, query: str) -> int:
    keyword = query.lower()
    if keyword in (title or "").lower():
        return 1
    for idx, line in enumerate((content or "").splitlines(), start=1):
        if keyword in line.lower():
            return idx
    return 1
