"""备忘录文件存储。"""

import json
import os
import re

from ..core.utils import get_config_dir, get_memo_dir


def resolve_memo_dir(custom_path: str | None = None) -> str:
    """返回备忘录目录，优先使用自定义路径。"""
    memo_dir = custom_path or get_memo_dir()
    os.makedirs(memo_dir, exist_ok=True)
    return memo_dir


def sanitize_filename(title: str, memo_id: int) -> str:
    """生成安全的文件名：{sanitized_title}_{id}.md"""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip()
    safe = re.sub(r'_+', '_', safe).strip('_. ')
    if not safe:
        safe = "memo"
    return f"{safe}_{memo_id}.md"


def safe_memo_path(memo_dir: str, fname: str) -> tuple[str, str]:
    """把旧数据中的文件名收窄到 memo 目录内。"""
    fname = os.path.basename(fname or "")
    if not fname.endswith(".md"):
        fname = f"{fname}.md"
    fpath = os.path.abspath(os.path.join(memo_dir, fname))
    memo_root = os.path.abspath(memo_dir)
    if os.path.commonpath([memo_root, fpath]) != memo_root:
        raise ValueError("无效的备忘录文件路径")
    return fname, fpath


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 YAML frontmatter，返回 (metadata_dict, content)。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = {}
    for line in parts[1].strip().split("\n"):
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()
        if key == "tags":
            meta[key] = [t.strip() for t in val.split(",") if t.strip()] if val else []
        else:
            meta[key] = val
    return meta, parts[2].strip()


def build_frontmatter(memo: dict) -> str:
    """生成 YAML frontmatter 字符串。"""
    title = memo.get("title", "备忘录")
    created = memo.get("created", memo.get("time", ""))
    modified = memo.get("modified", memo.get("time", ""))
    tags = memo.get("tags", [])
    tags_str = ", ".join(tags) if tags else ""
    lines = ["---", f"title: {title}", f"created: {created}", f"modified: {modified}"]
    if tags_str:
        lines.append(f"tags: {tags_str}")
    lines.append("---\n\n")
    return "\n".join(lines)


def migrate_legacy_memo(memo_dir: str):
    """迁移旧 JSON 格式备忘录。"""
    legacy_memo_file = os.path.join(get_config_dir(), "memo.json")
    if not os.path.exists(legacy_memo_file):
        return
    try:
        with open(legacy_memo_file, "r", encoding="utf-8") as f:
            old_data = json.load(f)
        if isinstance(old_data, list):
            for memo in old_data:
                if "_file" not in memo:
                    memo["_file"] = sanitize_filename(memo.get("title", "memo"), memo.get("id", 0))
                fname, fpath = safe_memo_path(memo_dir, memo["_file"])
                memo["_file"] = fname
                if not os.path.exists(fpath):
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(build_frontmatter(memo) + memo.get("content", ""))
            os.remove(legacy_memo_file)
    except Exception:
        pass


def load_memos(memo_dir: str) -> list[dict]:
    """从 memo/ 目录扫描 .md 文件并解析。"""
    migrate_legacy_memo(memo_dir)
    result = []
    for fname in os.listdir(memo_dir):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(memo_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
            meta, content = parse_frontmatter(text)
            name_part = fname.rsplit(".", 1)[0]
            try:
                file_id = int(name_part.rsplit("_", 1)[-1])
            except (ValueError, IndexError):
                file_id = int(os.path.getmtime(fpath) * 1000)
            result.append({
                "id": file_id,
                "time": meta.get("time", ""),
                "created": meta.get("created", meta.get("time", "")),
                "modified": meta.get("modified", meta.get("time", "")),
                "title": meta.get("title", name_part),
                "content": content,
                "tags": meta.get("tags", []),
                "_file": fname,
            })
        except Exception:
            continue
    result.sort(key=lambda m: m.get("modified", m.get("time", "")), reverse=True)
    for memo in result:
        memo.setdefault("_file", sanitize_filename(memo.get("title", "memo"), memo.get("id", 0)))
    return result


def save_memos(memo_data: list[dict], memo_dir: str):
    """每条 memo 保存为独立 .md 文件。"""
    for memo in memo_data:
        fname = memo.get("_file") or sanitize_filename(memo.get("title", "memo"), memo.get("id", 0))
        fname, fpath = safe_memo_path(memo_dir, fname)
        memo["_file"] = fname
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(build_frontmatter(memo) + memo.get("content", ""))
