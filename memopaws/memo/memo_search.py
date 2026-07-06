"""备忘录搜索匹配。"""

from difflib import SequenceMatcher

from pypinyin import Style, lazy_pinyin


def memo_matches_query(memo: dict, query: str) -> bool:
    """匹配标题、内容、标签、拼音首字母和轻量模糊输入。"""
    keyword = (query or "").strip().lower()
    if not keyword:
        return True

    title = str(memo.get("title", "") or "")
    content = str(memo.get("content", "") or "")
    tags = [str(tag) for tag in memo.get("tags", [])]
    fields = [title, content, *tags]
    lowered = [field.lower() for field in fields]

    if any(keyword in field for field in lowered):
        return True
    if any(keyword in _pinyin_initials(field) for field in fields):
        return True
    return any(_is_fuzzy_match(keyword, field) for field in lowered)


def _pinyin_initials(text: str) -> str:
    return "".join(lazy_pinyin(text, style=Style.FIRST_LETTER)).lower()


def _is_fuzzy_match(keyword: str, text: str) -> bool:
    if len(keyword) < 4:
        return False
    words = text.replace("_", " ").replace("-", " ").split()
    return any(SequenceMatcher(None, keyword, word).ratio() >= 0.8 for word in words)
