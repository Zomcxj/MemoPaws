"""备忘录相关控件"""

from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont


class MarkdownHighlighter(QSyntaxHighlighter):
    """Markdown 语法高亮器"""

    STATE_NORMAL = 0
    STATE_CODE_BLOCK = 1

    def __init__(self, parent=None, is_dark_fn=None):
        super().__init__(parent)
        self._is_dark_fn = is_dark_fn
        self._rules = []
        self._code_block_fmt = QTextCharFormat()
        self._code_marker_fmt = QTextCharFormat()
        self._build_rules()

    def _build_rules(self):
        self._rules.clear()
        dark = self._is_dark_fn() if self._is_dark_fn else True

        h_color = "#E8875C" if dark else "#C05C2E"
        bold_color = "#F0E6D3" if dark else "#1A1A1A"
        italic_color = "#B8B8B8" if dark else "#555555"
        code_inline_color = "#A8D8A8" if dark else "#2E7D32"
        link_color = "#6FA3EF" if dark else "#1565C0"
        quote_color = "#999999" if dark else "#888888"
        list_color = "#D4A76A" if dark else "#8D6E2F"
        hr_color = "#666666" if dark else "#BBBBBB"
        code_marker_color = "#888888" if dark else "#AAAAAA"
        code_content_bg = QColor("#1E1E1E" if dark else "#F5F5F5")
        code_content_fg = QColor("#D4D4D4" if dark else "#333333")

        def fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.DemiBold)
            if italic:
                f.setFontItalic(True)
            return f

        # 代码块标记行 ```lang
        self._code_marker_fmt.setForeground(QColor(code_marker_color))
        self._code_marker_fmt.setFontItalic(True)

        # 代码块内容：背景 + 前景色
        self._code_block_fmt.setForeground(code_content_fg)
        self._code_block_fmt.setBackground(code_content_bg)

        # 标题
        self._rules.append((QRegularExpression(r"^#{1,6}\s+.+$"), fmt(h_color, bold=True)))
        # 粗体
        self._rules.append((QRegularExpression(r"\*\*[^*]+\*\*"), fmt(bold_color, bold=True)))
        self._rules.append((QRegularExpression(r"__[^_]+__"), fmt(bold_color, bold=True)))
        # 斜体
        self._rules.append((QRegularExpression(r"(?<!\*)\*(?!\*)[^*]+\*(?!\*)"), fmt(italic_color, italic=True)))
        self._rules.append((QRegularExpression(r"(?<!_)_(?!_)[^_]+_(?!_)"), fmt(italic_color, italic=True)))
        # 行内代码
        self._rules.append((QRegularExpression(r"`[^`\n]+`"), fmt(code_inline_color)))
        # 链接
        self._rules.append((QRegularExpression(r"\[([^\]]+)\]\([^\)]+\)"), fmt(link_color)))
        # 图片
        self._rules.append((QRegularExpression(r"!\[([^\]]*)\]\([^\)]+\)"), fmt(link_color)))
        # 引用
        self._rules.append((QRegularExpression(r"^>\s+.+$"), fmt(quote_color, italic=True)))
        # 无序列表
        self._rules.append((QRegularExpression(r"^[\s]*[-*+]\s"), fmt(list_color, bold=True)))
        # 有序列表
        self._rules.append((QRegularExpression(r"^[\s]*\d+\.\s"), fmt(list_color, bold=True)))
        # 分隔线
        self._rules.append((QRegularExpression(r"^[-*]{3,}\s*$"), fmt(hr_color)))

    def highlightBlock(self, text):
        stripped = text.strip()

        # 代码块标记行：``` 开头
        if stripped.startswith("```"):
            self.setFormat(0, len(text), self._code_marker_fmt)
            # 切换状态：进入或退出代码块
            if self.previousBlockState() == self.STATE_CODE_BLOCK:
                self.setCurrentBlockState(self.STATE_NORMAL)
            else:
                self.setCurrentBlockState(self.STATE_CODE_BLOCK)
            return

        # 代码块内容行
        if self.previousBlockState() == self.STATE_CODE_BLOCK:
            self.setFormat(0, len(text), self._code_block_fmt)
            self.setCurrentBlockState(self.STATE_CODE_BLOCK)
            return

        # 普通行：应用内联规则
        self.setCurrentBlockState(self.STATE_NORMAL)
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class ZoomableTextEdit(QTextEdit):
    """支持 Ctrl+滚轮 缩放字体大小的 QTextEdit"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._font_size = 14
        self._apply_font_size()

    def wheelEvent(self, event):
        if self.isReadOnly():
            super().wheelEvent(event)
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._font_size = min(40, self._font_size + 1)
            elif delta < 0:
                self._font_size = max(8, self._font_size - 1)
            self._apply_font_size()
            event.accept()
            return
        super().wheelEvent(event)

    def _apply_font_size(self):
        if self._font_size <= 0:
            self._font_size = 14
        f = self.font()
        f.setPointSize(self._font_size)
        self.setFont(f)
        # 同步更新默认样式中的字号
        ss = self.styleSheet()
        import re
        ss = re.sub(r'font-size:\s*\d+px', f'font-size: {self._font_size}px', ss)
        self.setStyleSheet(ss)
