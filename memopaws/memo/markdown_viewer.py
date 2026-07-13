"""Markdown 预览控件 - VSCode 风格，基于 QWebEngineView"""

import os
import sys
import re
import html as _html_mod
import uuid as _uuid

try:
    import markdown as _md_lib
except ImportError:
    _md_lib = None

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer, ClassNotFound
    from pygments.formatters import HtmlFormatter
    _HAS_PYGMENTS = True
except ImportError:
    _HAS_PYGMENTS = False

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings


# VSCode 风格 QSS 滚动条
VSCODE_SCROLLBAR_QSS = """
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
    border: none;
}
QScrollBar::handle:vertical {
    background: rgba(121, 121, 121, 0.4);
    min-height: 30px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(121, 121, 121, 0.7);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
    border: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
    border: none;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
    border: none;
}
QScrollBar::handle:horizontal {
    background: rgba(121, 121, 121, 0.4);
    min-width: 30px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover {
    background: rgba(121, 121, 121, 0.7);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
    border: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
    border: none;
}
"""


_COPY_BTN_JS = """
function copyCode(id) {
    var el = document.getElementById(id);
    if (!el) return;
    var code = el.querySelector('.code-content');
    if (!code) return;
    var text = code.textContent;
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch(e) {}
    document.body.removeChild(ta);
    var btn = el.querySelector('.copy-btn');
    if (btn) { btn.textContent = 'Copied!'; setTimeout(function(){ btn.textContent = 'Copy'; }, 1500); }
}
"""


def _make_code_block(code_text: str, lang: str, code_fs: int, is_dark: bool) -> str:
    """用 Pygments 高亮代码并包裹为 VSCode 风格代码块（顶栏 + 复制按钮）"""
    code_bg = "#1e1e1e" if is_dark else "#f5f5f5"
    code_border = "#3c3c3c" if is_dark else "#e0e0e0"
    header_bg = "#2d2d2d" if is_dark else "#e8e8e8"
    mono = "'Consolas', 'Courier New', monospace"

    code_text = code_text.rstrip("\n")

    # Pygments 高亮：text/空语言跳过，避免树形字符被误染色
    lexer = None
    skip_langs = {"", "text", "txt", "plain", "raw"}
    if lang and lang.lower() not in skip_langs:
        try:
            lexer = get_lexer_by_name(lang)
        except ClassNotFound:
            pass

    if lexer and _HAS_PYGMENTS:
        formatter = HtmlFormatter(
            noclasses=True,
            nowrap=True,
            pygments_style="monokai" if is_dark else "default",
        )
        highlighted = highlight(code_text, lexer, formatter)
    else:
        highlighted = _html_mod.escape(code_text)

    uid = f"cb-{_uuid.uuid4().hex[:8]}"
    display_lang = (lang or "text").upper()

    return f'''<div class="code-block" id="{uid}">
<div class="code-header" style="background:{header_bg};border-bottom:1px solid {code_border};">
  <span class="lang-label">{display_lang}</span>
  <button class="copy-btn" onclick="copyCode('{uid}')">Copy</button>
</div>
<div class="code-content" style="font-family:{mono};font-size:{code_fs}px;">{highlighted}</div>
</div>'''


def markdown_to_html(md: str, theme=None, font_size: int = 14) -> str:
    """将 Markdown 转为 VSCode 风格 HTML"""
    if _md_lib is None:
        return f"<pre>{md}</pre>"

    if theme is None:
        from ..core.themes import DARK
        theme = DARK

    t = theme
    is_dark = getattr(t, 'is_dark', True)

    # 颜色定义
    bg_main = t.bg_main
    text_primary = t.text_primary
    text_secondary = t.text_secondary
    accent = t.accent
    border = t.border_subtle
    code_bg = "#1e1e1e" if is_dark else "#f5f5f5"
    code_border = "#3c3c3c" if is_dark else "#e0e0e0"
    code_text = "#d4d4d4" if is_dark else "#1e1e1e"
    table_header_bg = "#2d2d2d" if is_dark else "#f0f0f0"
    table_border = "#404040" if is_dark else "#d0d0d0"
    quote_bg = "#1e1e1e" if is_dark else "#f8f8f8"
    quote_border = accent

    # 字体
    sans = "'Segoe UI', 'Microsoft YaHei', sans-serif"
    mono = "'Consolas', 'Courier New', monospace"

    # 标题大小
    heading_scales = {1: 2.0, 2: 1.5, 3: 1.25, 4: 1.0, 5: 0.875, 6: 0.85}
    heading_px = {k: max(12, int(font_size * v)) for k, v in heading_scales.items()}
    code_fs = 14

    # ── 第一步：手动提取围栏代码块，用 Pygments 高亮 ──
    # 在 markdown 转换之前把 ```code``` 替换为占位符（用 <!-- --> HTML 注释包裹，防止 markdown 解析）
    code_blocks = []
    fenced_pattern = re.compile(r'^```(\w*)\n(.*?)^```', re.MULTILINE | re.DOTALL)

    def _replace_code_block(m):
        lang = m.group(1).strip()
        code_text = m.group(2)
        placeholder = f"CBLK{len(code_blocks)}ENDCBLK"
        code_blocks.append((lang, code_text))
        return placeholder

    md_processed = fenced_pattern.sub(_replace_code_block, md)
    # 预处理
    md_processed = re.sub(r'~~(.+?)~~', r'<del>\1</del>', md_processed)

    # 转换扩展（不使用 codehilite，我们自己处理代码块）
    extensions = ["tables", "nl2br", "sane_lists"]

    html_body = _md_lib.markdown(md_processed, extensions=extensions)

    # 还原代码块占位符（去掉 markdown 包裹的 <p> 标签）
    for i, (lang, code_text) in enumerate(code_blocks):
        block_html = _make_code_block(code_text, lang, code_fs, is_dark)
        html_body = re.sub(rf'<p>\s*CBLK{i}ENDCBLK\s*</p>', block_html, html_body)
        html_body = html_body.replace(f"CBLK{i}ENDCBLK", block_html)

    # 处理 <pre><code> 残留（非围栏代码块，markdown 库内联生成的）
    def _wrap_raw_code_block(m):
        code_content = m.group(1)
        code_content = _html_mod.unescape(code_content).strip("\n")
        return _make_code_block(code_content, "", code_fs, is_dark)
    html_body = re.sub(r'<pre><code[^>]*>(.*?)</code></pre>', _wrap_raw_code_block, html_body, flags=re.DOTALL)

    # 复选框
    html_body = re.sub(
        r'<li>\s*(?:<p>)?\[ \] (.+?)(?:</p>)?\s*</li>',
        lambda m: f'<li style="list-style:none;margin-left:-20px;"><input type="checkbox" disabled> {m.group(1).strip()}</li>',
        html_body,
        flags=re.DOTALL,
    )
    html_body = re.sub(
        r'<li>\s*(?:<p>)?\[[xX]\] (.+?)(?:</p>)?\s*</li>',
        lambda m: f'<li style="list-style:none;margin-left:-20px;"><input type="checkbox" checked disabled> {m.group(1).strip()}</li>',
        html_body,
        flags=re.DOTALL,
    )

    # 标题样式
    for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        level = int(tag[1])
        px = heading_px[level]
        border_b = f"border-bottom:1px solid {border};padding-bottom:4px;" if level <= 2 else ""
        html_body = html_body.replace(
            f"<{tag}>",
            f'<{tag} style="color:{text_primary};font-weight:600;font-size:{px}px;margin:20px 0 10px 0;{border_b}line-height:1.3;">',
        )

    # 段落
    html_body = html_body.replace("<p>", f'<p style="color:{text_primary};margin:8px 0;line-height:1.7;">')

    # 链接
    html_body = re.sub(r'<a href="([^"]*)">', f'<a href="\\1" style="color:{accent};text-decoration:none;" target="_blank">', html_body)

    # 行内代码：代码块已转为 .code-block div（不含 <code> 标签），无需保护
    if is_dark:
        inline_code_style = f'color:#e06c75;padding:1px 4px;border-radius:3px;font-family:{mono};font-size:0.9em;'
    else:
        inline_code_style = f'color:#c25;padding:1px 4px;border-radius:3px;font-family:{mono};font-size:0.9em;'
    html_body = html_body.replace(
        "<code>",
        f'<code style="{inline_code_style}">',
    )

    # 引用
    html_body = html_body.replace(
        "<blockquote>",
        f'<blockquote style="border-left:4px solid {quote_border};padding:12px 16px;margin:12px 0;color:{text_secondary};background:{quote_bg};border-radius:0 6px 6px 0;">',
    )

    # 列表
    html_body = html_body.replace("<ul>", f'<ul style="color:{text_primary};margin:8px 0;padding-left:24px;">')
    html_body = html_body.replace("<ol>", f'<ol style="color:{text_primary};margin:8px 0;padding-left:24px;">')
    html_body = html_body.replace("<li>", f'<li style="margin:4px 0;line-height:1.6;">')

    # 表格
    html_body = html_body.replace("<table>", f'<table style="border-collapse:collapse;width:100%;margin:12px 0;font-size:{font_size}px;">')
    html_body = html_body.replace("<th>", f'<th style="border:1px solid {table_border};padding:10px 12px;background:{table_header_bg};font-weight:600;text-align:left;color:{text_primary};">')
    html_body = html_body.replace("<td>", f'<td style="border:1px solid {table_border};padding:10px 12px;color:{text_primary};">')

    # 分隔线
    html_body = html_body.replace("<hr>", f'<hr style="border:none;border-top:1px solid {border};margin:16px 0;">')

    # 图片
    html_body = re.sub(r'<img ', '<img style="max-width:100%;height:auto;border-radius:4px;margin:8px 0;" ', html_body)

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<script>{_COPY_BTN_JS}</script>
<style>
body {{
    font-family: {sans};
    font-size: {font_size}px;
    line-height: 1.6;
    padding: 20px;
    color: {text_primary};
    background: {bg_main};
    margin: 0;
}}
::-webkit-scrollbar {{
    width: 10px;
    height: 10px;
}}
::-webkit-scrollbar-track {{
    background: transparent;
}}
::-webkit-scrollbar-thumb {{
    background: rgba(121, 121, 121, 0.5);
    border-radius: 5px;
}}
::-webkit-scrollbar-thumb:hover {{
    background: rgba(121, 121, 121, 0.8);
}}

/* ── 代码块容器 ── */
.code-block {{
    background: {code_bg};
    border: 1px solid {code_border};
    border-radius: 6px;
    margin: 16px 0;
    overflow: hidden;
}}
.code-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 16px;
    font-family: {sans};
    font-size: 12px;
}}
.lang-label {{
    color: {text_secondary};
    font-weight: 500;
    text-transform: uppercase;
}}
.copy-btn {{
    background: transparent;
    color: {text_secondary};
    border: 1px solid {code_border};
    border-radius: 4px;
    padding: 2px 10px;
    font-size: 12px;
    cursor: pointer;
    font-family: {sans};
}}
.copy-btn:hover {{
    background: rgba(255,255,255,0.1);
    color: {text_primary};
}}
.code-content {{
    flex: 1;
    padding: 16px;
    line-height: 1.5;
    white-space: pre;
    overflow-x: auto;
    color: {code_text};
}}
</style>
</head>
<body>
{html_body}
</body></html>"""


class MarkdownViewer(QWebEngineView):
    """Markdown 预览控件，VSCode 风格"""

    content_loaded = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_html = ""
        self._load_finished = False
        self._first_load = True
        self._current_theme = None

        page = self.page()
        page.loadFinished.connect(self._on_load_finished)

        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        self.setAcceptDrops(False)
        self.setStyleSheet(VSCODE_SCROLLBAR_QSS)

    def set_background_color(self, color: QColor):
        """设置背景色，消除白屏"""
        self.page().setBackgroundColor(color)

    def set_markdown(self, md: str, theme=None, font_size: int = 14):
        """设置 Markdown 内容并渲染"""
        self._current_theme = theme
        html = markdown_to_html(md, theme, font_size)
        if theme:
            from PySide6.QtGui import QColor
            bg_color = QColor(theme.bg_main)
            self.set_markdown_html(html, bg_color)
        else:
            self.set_markdown_html(html)

    def set_markdown_html(self, html: str, bg_color=None):
        """设置 HTML 并渲染"""
        if bg_color:
            self.set_background_color(bg_color)

        self._current_html = html

        if self._first_load:
            self._first_load = False
            self._load_finished = False
            self.setHtml(html, QUrl("about:blank"))
        else:
            # 后续更新：用 runJavaScript 替换 style + body，避免 setHtml 全页重载闪烁
            import re as _re
            import json as _json
            style_match = _re.search(r'<style>(.*?)</style>', html, _re.DOTALL)
            body_match = _re.search(r'<body>(.*?)</body>', html, _re.DOTALL)
            if style_match and body_match:
                css = style_match.group(1)
                body = body_match.group(1)
                js = f"""(function() {{
                    var s = document.querySelector('style');
                    if (s) s.textContent = {_json.dumps(css)};
                    document.body.innerHTML = {_json.dumps(body)};
                }})()"""
                self.page().runJavaScript(js)

    def _on_load_finished(self, ok):
        """页面加载完成回调"""
        self._load_finished = ok
        if ok:
            self.content_loaded.emit()

    def wheelEvent(self, event):
        """禁用缩放，只允许滚动"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            event.ignore()
            return
        super().wheelEvent(event)
