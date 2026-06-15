"""备忘录页面模块"""

import os
import json
import time
import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
    QLineEdit, QTextEdit, QListWidget, QListWidgetItem,
    QPushButton, QCheckBox, QFileDialog, QMessageBox,
    QAbstractItemView, QSplitter
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from .utils import MEMO_FILE, ensure_config_dir


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
        f = self.font()
        f.setPointSize(self._font_size)
        self.setFont(f)
        # 同步更新默认样式中的字号
        ss = self.styleSheet()
        import re
        ss = re.sub(r'font-size:\s*\d+px', f'font-size: {self._font_size}px', ss)
        self.setStyleSheet(ss)
from .themes import DARK, LIGHT, get_status_list_stylesheet, get_text_edit_stylesheet

logger = logging.getLogger(__name__)


def load_svg_icon(svg_path: str, size: int = 20, color: str = None):
    """加载 SVG 文件并返回指定大小的 QPixmap，支持动态换色"""
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtGui import QPixmap, QPainter
    import re
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_data = f.read()
    if color:
        svg_data = svg_data.replace('currentColor', color)
        svg_data = re.sub(r'fill="#ccc"', f'fill="{color}"', svg_data)
    renderer = QSvgRenderer(svg_data.encode("utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def markdown_to_html(md: str, theme=None) -> str:
    """使用 Python markdown 库将 Markdown 转为 HTML，带主题样式"""
    import markdown as md_lib
    import re

    if theme is None:
        from .themes import DARK
        theme = DARK
    text_color = theme.text_primary
    heading_color = theme.text_primary
    link_color = theme.accent
    code_bg = theme.bg_input
    code_color = theme.text_muted
    border_color = theme.border_subtle
    quote_color = theme.text_muted
    th_bg = theme.bg_input

    html_body = md_lib.markdown(
        md,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
    )

    # QTextEdit 对 <style> 支持有限，用内联样式替换标签
    for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        html_body = html_body.replace(
            f"<{tag}>",
            f'<{tag} style="color:{heading_color};font-weight:bold;margin:12px 0 6px 0;border-bottom:1px solid {border_color};padding-bottom:3px;">'
        )
    html_body = html_body.replace("<p>", f'<p style="color:{text_color};margin:4px 0;">')
    html_body = re.sub(
        r'<a href="([^"]*)">',
        f'<a href="\\1" style="color:{link_color};text-decoration:underline;">',
        html_body,
    )
    html_body = html_body.replace(
        "<code>",
        f'<code style="background:{code_bg};color:{code_color};padding:1px 4px;border-radius:3px;font-family:Consolas,monospace;font-size:13px;">',
    )
    html_body = html_body.replace(
        "<pre>",
        f'<pre style="background:{code_bg};border:1px solid {border_color};border-radius:6px;padding:10px 12px;margin:8px 0;">',
    )
    html_body = html_body.replace(
        "<pre><code",
        f'<pre style="background:{code_bg};border:1px solid {border_color};border-radius:6px;padding:10px 12px;margin:8px 0;"><code style="background:transparent;color:{code_color};padding:0;font-family:Consolas,monospace;font-size:13px;">',
    )
    html_body = html_body.replace(
        "<blockquote>",
        f'<blockquote style="border-left:3px solid {border_color};padding-left:12px;margin:8px 0;color:{quote_color};font-style:italic;">',
    )
    html_body = html_body.replace(
        "<ul>",
        f'<ul style="color:{text_color};margin:4px 0;padding-left:20px;">',
    )
    html_body = html_body.replace(
        "<ol>",
        f'<ol style="color:{text_color};margin:4px 0;padding-left:20px;">',
    )
    html_body = html_body.replace(
        "<li>",
        f'<li style="margin:2px 0;">',
    )
    html_body = html_body.replace(
        "<table>",
        f'<table style="border-collapse:collapse;width:100%;margin:8px 0;">',
    )
    html_body = html_body.replace(
        "<th>",
        f'<th style="border:1px solid {border_color};padding:6px 8px;background:{th_bg};font-weight:bold;">',
    )
    html_body = html_body.replace(
        "<td>",
        f'<td style="border:1px solid {border_color};padding:6px 8px;">',
    )
    html_body = html_body.replace(
        "<hr>",
        f'<hr style="border:none;border-top:1px solid {border_color};margin:12px 0;">',
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:'Microsoft YaHei','Inter',sans-serif;font-size:14px;padding:8px;">
{html_body}
</body></html>"""
    return html


class MemoPage(QWidget):
    """备忘录页面"""

    def __init__(self, parent, *,
                 get_config_path,
                 get_theme,
                 get_icons_dir,
                 get_icon_clr,
                 on_append_status,
                 is_dark,
                 show_message=None,
                 ):
        super().__init__(parent)
        self._get_config_path = get_config_path
        self._get_theme = get_theme
        self._get_icons_dir = get_icons_dir
        self._get_icon_clr = get_icon_clr
        self._on_append_status = on_append_status
        self._is_dark = is_dark
        self._show_message = show_message

        self.memo_data = []
        self._memo_editing = True
        self._memo_saving = False
        self._memo_current_idx = -1
        self._memo_original = None
        self._memo_md_source = ""

        self._init_ui()

        if hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(lambda _: self.apply_theme())
        if hasattr(parent, 'language_changed'):
            parent.language_changed.connect(self.apply_language)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(0)

        # 左右面板使用 QSplitter 替代 QHBoxLayout
        memo_splitter = QSplitter(Qt.Orientation.Horizontal)
        memo_splitter.setHandleWidth(6)
        memo_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")

        # 左面板
        left_frame = QFrame()
        self._memo_left_frame = left_frame
        t = self._get_theme()
        left_frame.setStyleSheet(f"QFrame {{ border: 1px solid {t.border_subtle}; border-radius: 12px; background: {t.bg_panel}; }}")
        left_frame.setMinimumWidth(220)
        left_frame.setMaximumWidth(380)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        # 标题行
        # 操作按钮（2x2 网格）
        _memo_btn_ss = "QPushButton { padding: 4px 12px; font-size: 13px; }"
        memo_btn_grid = QGridLayout()
        memo_btn_grid.setSpacing(4)

        icons_dir = self._get_icons_dir()
        icon_clr = self._get_icon_clr()

        btn_add_memo = QPushButton("新建")
        btn_add_memo.setIcon(QIcon(load_svg_icon(os.path.join(icons_dir, "add.svg"), 16, icon_clr)))
        btn_add_memo.setIconSize(QSize(16, 16))
        btn_add_memo.setStyleSheet(_memo_btn_ss)
        self._memo_btn_add = btn_add_memo
        btn_add_memo.clicked.connect(self.add_memo)
        memo_btn_grid.addWidget(btn_add_memo, 0, 0)

        btn_import_memo = QPushButton("导入")
        btn_import_memo.setIcon(QIcon(load_svg_icon(os.path.join(icons_dir, "import.svg"), 16, icon_clr)))
        btn_import_memo.setIconSize(QSize(16, 16))
        btn_import_memo.setStyleSheet(_memo_btn_ss)
        self._memo_btn_import = btn_import_memo
        btn_import_memo.clicked.connect(self._import_memo)
        memo_btn_grid.addWidget(btn_import_memo, 0, 1)

        btn_export_memo = QPushButton("导出")
        btn_export_memo.setIcon(QIcon(load_svg_icon(os.path.join(icons_dir, "save.svg"), 16, icon_clr)))
        btn_export_memo.setIconSize(QSize(16, 16))
        btn_export_memo.setStyleSheet(_memo_btn_ss)
        self._memo_btn_export = btn_export_memo
        btn_export_memo.clicked.connect(self._export_memo)
        memo_btn_grid.addWidget(btn_export_memo, 1, 0)

        btn_delete_memo = QPushButton("删除")
        btn_delete_memo.setIcon(QIcon(load_svg_icon(os.path.join(icons_dir, "clear.svg"), 16, icon_clr)))
        btn_delete_memo.setIconSize(QSize(16, 16))
        btn_delete_memo.setStyleSheet(_memo_btn_ss)
        self._memo_btn_delete = btn_delete_memo
        btn_delete_memo.clicked.connect(self.delete_memo)
        memo_btn_grid.addWidget(btn_delete_memo, 1, 1)

        left_layout.addLayout(memo_btn_grid)

        # 列表
        self.memo_list = QListWidget()
        self.memo_list.setStyleSheet(get_status_list_stylesheet(t))
        self.memo_list.setWordWrap(True)
        self.memo_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.memo_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.memo_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.memo_list.currentRowChanged.connect(self._on_memo_selection_changed)
        left_layout.addWidget(self.memo_list)

        self.memo_stat_label = QLabel("0 条")
        _memo_tip_ss = f"font-size:11px; color:{t.text_muted}; border:none; padding: 2px 4px; background:transparent;"
        self.memo_stat_label.setStyleSheet(_memo_tip_ss)
        left_layout.addWidget(self.memo_stat_label)

        # 将左面板添加到 splitter
        memo_splitter.addWidget(left_frame)

        # 右面板
        right_frame = QFrame()
        self._memo_right_frame = right_frame
        right_frame.setStyleSheet(f"QFrame {{ border: 1px solid {t.border_subtle}; border-radius: 12px; background: {t.bg_panel}; }}")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)

        # 标题输入
        self.memo_title_input = QLineEdit()
        self.memo_title_input.setPlaceholderText("标题")
        memo_title_color = t.accent
        memo_title_border = f"{t.accent}33"
        self.memo_title_input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {memo_title_color};
                border: none;
                border-bottom: 1px solid {memo_title_border};
                padding: 6px 4px;
                font-size: 18px;
                font-weight: bold;
            }}
        """)
        right_layout.addWidget(self.memo_title_input)

        # 时间标签
        self.memo_time_label = QLabel("")
        _memo_time_ss = f"font-size:11px; color:{t.text_muted}; border:none; padding: 0 4px;"
        self.memo_time_label.setStyleSheet(_memo_time_ss)
        right_layout.addWidget(self.memo_time_label)

        # 内容
        self.memo_content_view = ZoomableTextEdit()
        self.memo_content_view.setReadOnly(False)
        self.memo_content_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.memo_content_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.memo_content_view.setStyleSheet(get_text_edit_stylesheet(t))
        right_layout.addWidget(self.memo_content_view, 1)

        # 操作按钮
        edit_row = QHBoxLayout()
        self.memo_btn_save = QPushButton("保存")
        self.memo_btn_save.setIcon(QIcon(load_svg_icon(os.path.join(icons_dir, "save.svg"), 16, icon_clr)))
        self.memo_btn_save.setIconSize(QSize(16, 16))
        self.memo_btn_save.setStyleSheet(f"""
            QPushButton {{
                background: {t.accent};
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background: {t.accent_hover}; }}
        """)
        self.memo_btn_save.clicked.connect(self._save_memo_edit)
        edit_row.addWidget(self.memo_btn_save)

        edit_row.addStretch()
        self.memo_preview_toggle = QCheckBox("预览模式")
        self.memo_preview_toggle.setStyleSheet(f"color: {t.text_muted};")
        self.memo_preview_toggle.toggled.connect(self._toggle_memo_preview)
        edit_row.addWidget(self.memo_preview_toggle)

        self.memo_content_view.textChanged.connect(self._on_memo_text_changed)

        right_layout.addLayout(edit_row)

        # 将右面板添加到 splitter
        memo_splitter.addWidget(right_frame)
        memo_splitter.setSizes([300, 500])  # 初始比例
        memo_splitter.setCollapsible(0, False)  # 左面板不可完全折叠

        # 将 splitter 添加到主布局
        layout.addWidget(memo_splitter, 1)

        self.memo_data = self.load_memo()
        self._update_memo_list()

    def add_memo(self):
        self._memo_saving = True
        try:
            record = {
                "id": int(time.time() * 1000),
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "title": "新备忘录",
                "content": ""
            }
            self.memo_data.insert(0, record)
            self.save_memo()
            self._update_memo_list()
        finally:
            self._memo_saving = False
        self._select_memo(0)
        self.memo_title_input.setFocus()
        self.memo_title_input.selectAll()

    def delete_memo(self):
        idx = self.memo_list.currentRow()
        if 0 <= idx < len(self.memo_data):
            self.memo_data.pop(idx)
            self.save_memo()
            self._update_memo_list()
            if self.memo_data:
                self._select_memo(min(idx, len(self.memo_data) - 1))
            else:
                self._clear_memo_detail()

    def _update_memo_list(self):
        self.memo_list.blockSignals(True)
        self.memo_list.clear()
        for m in self.memo_data:
            title = m.get("title", "备忘录") or "备忘录"
            first_line = (m.get("content", "") or "").split("\n", 1)[0][:40]
            if not first_line:
                first_line = "(空)"
            item = QListWidgetItem(f"{title}\n{first_line}")
            item.setSizeHint(QSize(-1, 50))
            self.memo_list.addItem(item)
        self.memo_stat_label.setText(f"{len(self.memo_data)} 条")
        self.memo_list.blockSignals(False)

    def _select_memo(self, idx: int):
        if idx < 0 or idx >= len(self.memo_data):
            return
        self._memo_saving = True
        self.memo_list.blockSignals(True)
        self.memo_list.setCurrentRow(idx)
        self.memo_list.blockSignals(False)
        self._memo_saving = False
        self._show_memo_detail(idx)

    def _on_memo_selection_changed(self, idx: int):
        if self._memo_saving:
            return
        if self._memo_editing and 0 <= self._memo_current_idx < len(self.memo_data):
            self._save_memo_edit(silent=True)
        if 0 <= idx < len(self.memo_data):
            self._show_memo_detail(idx)
        else:
            self._clear_memo_detail()

    def _show_memo_detail(self, idx: int):
        self._memo_current_idx = idx
        memo = self.memo_data[idx]
        self.memo_title_input.setText(memo.get("title", ""))
        self.memo_time_label.setText(f"创建/修改：{memo.get('time', '')}")
        self._memo_md_source = memo.get("content", "")
        if self.memo_preview_toggle.isChecked():
            html = markdown_to_html(self._memo_md_source, self._get_theme())
            self.memo_content_view.setHtml(html)
            self.memo_content_view.setReadOnly(True)
        else:
            self.memo_content_view.setPlainText(self._memo_md_source)

    def _save_memo_edit(self, silent: bool = False):
        if self._memo_saving:
            return
        if self._memo_current_idx < 0 or self._memo_current_idx >= len(self.memo_data):
            return
        self._memo_saving = True
        try:
            memo = self.memo_data[self._memo_current_idx]
            new_title = self.memo_title_input.text().strip() or "备忘录"
            if self.memo_preview_toggle.isChecked():
                new_content = self._memo_md_source
            else:
                new_content = self.memo_content_view.toPlainText()
            memo["title"] = new_title
            memo["content"] = new_content
            memo["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._memo_md_source = new_content
            self.save_memo()
            if 0 <= self._memo_current_idx < self.memo_list.count():
                first_line = (new_content or "").split("\n", 1)[0][:40] or "(空)"
                self.memo_list.blockSignals(True)
                self.memo_list.item(self._memo_current_idx).setText(f"{new_title}\n{first_line}")
                self.memo_list.blockSignals(False)
            self.memo_stat_label.setText(f"{len(self.memo_data)} 条")
            if not silent:
                self._on_append_status("备忘录已保存")
        except Exception as e:
            logger.exception("保存备忘录失败: %s", e)
            if not silent and self._show_message:
                self._show_message(QMessageBox.Icon.Warning, "保存失败", str(e))
        finally:
            self._memo_saving = False

    def _toggle_memo_preview(self, checked: bool):
        if checked:
            self._memo_md_source = self.memo_content_view.toPlainText()
            html = markdown_to_html(self._memo_md_source, self._get_theme())
            self.memo_content_view.setHtml(html)
            self.memo_content_view.setReadOnly(True)
        else:
            self.memo_content_view.setPlainText(self._memo_md_source)
            self.memo_content_view.setReadOnly(False)

    def _on_memo_text_changed(self):
        if self._memo_current_idx < 0:
            return
        if self.memo_preview_toggle.isChecked():
            return
        self._memo_md_source = self.memo_content_view.toPlainText()

    def _import_memo(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "导入备忘录",
            "", "文本/Markdown (*.md *.txt);;所有文件 (*)"
        )
        if not paths:
            return
        self._memo_saving = True
        try:
            imported = 0
            for p in paths:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        content = f.read()
                except UnicodeDecodeError:
                    try:
                        with open(p, "r", encoding="gbk") as f:
                            content = f.read()
                    except Exception as e:
                        if self._show_message:
                            self._show_message(QMessageBox.Icon.Warning, "导入失败",
                                f"无法读取 {os.path.basename(p)}: {e}")
                        continue
                except Exception as e:
                    if self._show_message:
                        self._show_message(QMessageBox.Icon.Warning, "导入失败",
                            f"{os.path.basename(p)}: {e}")
                    continue
                title = os.path.splitext(os.path.basename(p))[0] or "导入的备忘录"
                record = {
                    "id": int(time.time() * 1000) + imported,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "title": title,
                    "content": content,
                }
                self.memo_data.insert(0, record)
                imported += 1
            if imported > 0:
                self.save_memo()
                self._update_memo_list()
                self._on_append_status(f"已导入 {imported} 条备忘录")
        finally:
            self._memo_saving = False
        if imported > 0:
            self._select_memo(0)

    def _export_memo(self):
        idx = self.memo_list.currentRow()
        if idx < 0 or idx >= len(self.memo_data):
            if self._show_message:
                self._show_message(QMessageBox.Icon.Information, "提示", "请先选择一条备忘录")
            return
        memo = self.memo_data[idx]
        suggested = (memo.get("title", "备忘录") or "备忘录").strip() + ".md"
        suggested = "".join(c for c in suggested if c not in r'\/:*?"<>|')
        path, _ = QFileDialog.getSaveFileName(
            self, "导出备忘录", suggested,
            "Markdown (*.md);;Text (*.txt)"
        )
        if not path:
            return
        try:
            if path.lower().endswith(".txt"):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(memo.get("content", ""))
            else:
                body = f"# {memo.get('title', '备忘录')}\n\n{memo.get('content', '')}"
                with open(path, "w", encoding="utf-8") as f:
                    f.write(body)
            self._on_append_status(f"已导出：{os.path.basename(path)}")
        except Exception as e:
            if self._show_message:
                self._show_message(QMessageBox.Icon.Warning, "导出失败", str(e))

    def load_memo(self):
        if os.path.exists(MEMO_FILE):
            try:
                with open(MEMO_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_memo(self):
        try:
            ensure_config_dir()
            with open(MEMO_FILE, "w", encoding="utf-8") as f:
                json.dump(self.memo_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _clear_memo_detail(self):
        self._memo_current_idx = -1
        self.memo_title_input.clear()
        self.memo_time_label.clear()
        self.memo_content_view.clear()
        self._memo_md_source = ""

    def apply_theme(self):
        t = self._get_theme()
        self._memo_left_frame.setStyleSheet(f"QFrame {{ border: 1px solid {t.border_subtle}; border-radius: 12px; background: {t.bg_panel}; }}")
        self._memo_right_frame.setStyleSheet(f"QFrame {{ border: 1px solid {t.border_subtle}; border-radius: 12px; background: {t.bg_panel}; }}")
        self.memo_btn_save.setStyleSheet(f"QPushButton {{ background: {t.accent}; color: #FFFFFF; border: none; border-radius: 8px; padding: 6px 14px; font-size: 13px; font-weight: 500; }} QPushButton:hover {{ background: {t.accent_hover}; }}")
        self.memo_title_input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {t.accent};
                border: none;
                border-bottom: 1px solid {t.border_subtle};
                padding: 6px 4px;
                font-size: 18px;
                font-weight: bold;
            }}
        """)
        self.memo_list.setStyleSheet(get_status_list_stylesheet(t))
        self.memo_content_view.setStyleSheet(get_text_edit_stylesheet(t))
        if self.memo_preview_toggle.isChecked():
            html = markdown_to_html(self._memo_md_source, t)
            self.memo_content_view.setHtml(html)
        self.memo_preview_toggle.setStyleSheet(f"color: {t.text_muted};")

    def apply_language(self, lang: str):
        self.memo_btn_save.setText("Save" if lang == "en" else "保存")
        self.memo_preview_toggle.setText("Preview" if lang == "en" else "预览模式")
        self._memo_btn_add.setText("New" if lang == "en" else "新建")
        self._memo_btn_import.setText("Import" if lang == "en" else "导入")
        self._memo_btn_export.setText("Export" if lang == "en" else "导出")
        self._memo_btn_delete.setText("Delete" if lang == "en" else "删除")
        if hasattr(self, 'memo_title_input'):
            self.memo_title_input.setPlaceholderText("Title" if lang == "en" else "标题")
