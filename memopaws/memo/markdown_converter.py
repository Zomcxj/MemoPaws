"""Markdown 渲染工具。"""

import re

try:
    import markdown as _md_lib
except ImportError:
    _md_lib = None

try:
    import pygments  # noqa: F401
    _HAS_PYGMENTS = True
except ImportError:
    _HAS_PYGMENTS = False


def markdown_to_html(md: str, theme=None, font_size: int = 14) -> str:
    """将 Markdown 转为 HTML，带主题样式，可选字体大小与 pygments 代码高亮。"""
    if _md_lib is None:
        return f"<pre>{md}</pre>"

    if theme is None:
        from ..core.themes import DARK
        theme = DARK

    t = theme
    text_c = t.text_primary
    heading_c = t.text_primary
    link_c = t.accent
    code_bg = t.bg_input
    code_fg = t.text_muted
    border_c = t.border_subtle
    quote_c = t.text_muted
    code_block_bg = t.bg_input if t.is_dark else "#F5F3F0"
    quote_bg = t.bg_main if t.is_dark else "#F5F3F0"

    sans = "'JetBrains Mono', 'Microsoft YaHei', 'Segoe UI', monospace"
    mono = "'JetBrains Mono', 'Consolas', monospace"

    heading_scales = {1: 2.0, 2: 1.5, 3: 1.25, 4: 1.0, 5: 0.875, 6: 0.85}
    heading_px = {k: max(12, int(font_size * v)) for k, v in heading_scales.items()}
    code_fs = max(11, font_size - 1)

    md = re.sub(r'~~(.+?)~~', r'<del>\1</del>', md)
    md = re.sub(r'(\S)\n(?=\s*[-*+>]\s|\s*\d+\.\s)', r'\1\n\n', md)

    is_dark = getattr(t, 'is_dark', True)
    extensions = ["tables", "fenced_code", "nl2br", "sane_lists"]
    ext_configs = {}
    if _HAS_PYGMENTS:
        extensions.append("codehilite")
        ext_configs["codehilite"] = {
            "noclasses": True,
            "pygments_style": "monokai" if is_dark else "default",
        }

    html_body = _md_lib.markdown(md, extensions=extensions, extension_configs=ext_configs)

    html_body = re.sub(
        r'<li>\s*(?:<p>)?\[ \] (.+?)(?:</p>)?\s*</li>',
        lambda m: f'<li style="list-style:none;margin-left:-20px;"><span style="font-size:{code_fs}px;">&#x2610;</span> {m.group(1).strip()}</li>',
        html_body,
        flags=re.DOTALL,
    )
    html_body = re.sub(
        r'<li>\s*(?:<p>)?\[[xX]\] (.+?)(?:</p>)?\s*</li>',
        lambda m: f'<li style="list-style:none;margin-left:-20px;"><span style="font-size:{code_fs}px;color:{link_c};">&#x2611;</span> {m.group(1).strip()}</li>',
        html_body,
        flags=re.DOTALL,
    )

    for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        level = int(tag[1])
        px = heading_px[level]
        border_b = f"border-bottom:1px solid {border_c};padding-bottom:2px;" if level <= 2 else ""
        html_body = html_body.replace(
            f"<{tag}>",
            f'<{tag} style="color:{heading_c};font-weight:600;font-size:{px}px;margin:16px 0 8px 0;{border_b}line-height:1.3;">',
        )

    html_body = html_body.replace("<p>", f'<p style="color:{text_c};margin:6px 0;line-height:1.7;">')
    html_body = re.sub(r'<a href="([^"]*)">', f'<a href="\\1" style="color:{link_c};text-decoration:underline;">', html_body)
    html_body = html_body.replace(
        "<code>",
        f'<code style="background:{code_bg};color:{code_fg};padding:1px 5px;border-radius:3px;font-family:{mono};font-size:{code_fs}px;">',
    )

    if not _HAS_PYGMENTS:
        html_body = html_body.replace(
            "<pre>",
            f'<pre style="background:{code_block_bg};border:1px solid {border_c};border-radius:6px;padding:12px 14px;margin:10px 0;font-family:{mono};font-size:{code_fs}px;line-height:1.5;">',
        )
        html_body = re.sub(
            r'<pre><code[^>]*>',
            f'<pre style="background:{code_block_bg};border:1px solid {border_c};border-radius:6px;padding:12px 14px;margin:10px 0;font-family:{mono};font-size:{code_fs}px;line-height:1.5;"><code style="background:transparent;color:{code_fg};padding:0;font-family:{mono};font-size:{code_fs}px;">',
            html_body,
        )
    else:
        html_body = html_body.replace(
            '<div class="codehilite">',
            f'<div style="background:{code_block_bg};border:1px solid {border_c};border-radius:6px;padding:12px 14px;margin:10px 0;font-family:{mono};font-size:{code_fs}px;line-height:1.5;">',
        )

    html_body = html_body.replace(
        "<blockquote>",
        f'<blockquote style="border-left:4px solid {link_c};padding:8px 14px;margin:10px 0;color:{quote_c};background:transparent;border-radius:0;">',
    )
    html_body = html_body.replace("<ul>", f'<ul style="color:{text_c};margin:6px 0;padding-left:24px;">')
    html_body = html_body.replace("<ol>", f'<ol style="color:{text_c};margin:6px 0;padding-left:24px;">')
    html_body = html_body.replace("<li>", f'<li style="margin:3px 0;line-height:1.6;">')

    html_body = html_body.replace("<table>", f'<table style="border-collapse:collapse;width:100%;margin:12px 0;font-size:{font_size}px;">')
    html_body = html_body.replace("<th>", f'<th style="border:1px solid {border_c};padding:7px 10px;background:{code_block_bg};font-weight:600;text-align:left;color:{text_c};">')
    html_body = html_body.replace("<td>", f'<td style="border:1px solid {border_c};padding:7px 10px;color:{text_c};">')
    html_body = html_body.replace("<hr>", f'<hr style="border:none;border-top:1px solid {border_c};margin:14px 0;">')
    html_body = re.sub(r'<img ', '<img style="max-width:100%;height:auto;border-radius:4px;margin:8px 0;" ', html_body)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:{sans};font-size:{font_size}px;line-height:1.6;padding:8px;color:{text_c};">
{html_body}
</body></html>"""
