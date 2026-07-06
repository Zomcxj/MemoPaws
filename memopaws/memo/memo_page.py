"""备忘录页面模块"""

import os
import time
import logging
from datetime import datetime

from PySide6.QtWidgets import QWidget, QListWidgetItem, QFileDialog, QMessageBox
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QTextCursor

from ..core.utils import ensure_config_dir
from .markdown_converter import markdown_to_html
from .memo_search import memo_matches_query
from .memo_storage import load_memos, resolve_memo_dir, safe_memo_path, save_memos
from .memo_ui import build_memo_ui
from ..core.themes import DARK, LIGHT, get_status_list_stylesheet, get_text_edit_stylesheet

logger = logging.getLogger(__name__)


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
                 get_memo_path=None,
                 get_current_lang=None,
                 ):
        super().__init__(parent)
        self._get_config_path = get_config_path
        self._get_theme = get_theme
        self._get_icons_dir = get_icons_dir
        self._get_icon_clr = get_icon_clr
        self._on_append_status = on_append_status
        self._is_dark = is_dark
        self._show_message = show_message
        self._get_memo_path = get_memo_path
        self._get_current_lang = get_current_lang or (lambda: "zh")

        self.memo_data = []
        self._memo_editing = True
        self._memo_saving = False
        self._memo_current_idx = -1
        self._memo_original = None
        self._memo_md_source = ""
        self._memo_is_dirty = False
        self._memo_split_mode = False
        self._memo_font_size = 14

        # 预览渲染缓存：(content, theme_hash, font_size) -> html
        self._preview_cache = None
        self._preview_cache_key = None

        # 草稿自动保存定时器（每 30 秒）
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setInterval(30000)
        self._auto_save_timer.timeout.connect(self._auto_save_draft)

        # 预览 debounce 定时器（同步模式下按键延迟渲染）
        self._preview_debounce_timer = QTimer(self)
        self._preview_debounce_timer.setSingleShot(True)
        self._preview_debounce_timer.setInterval(150)
        self._preview_debounce_timer.timeout.connect(self._do_debounced_preview)

        self._init_ui()

        if hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(lambda _: self.apply_theme())
        if hasattr(parent, 'language_changed'):
            parent.language_changed.connect(self.apply_language)

    def _init_ui(self):
        build_memo_ui(self)

    def _prewarm_preview(self):
        """预热当前备忘录预览，避免首次点击同步/预览卡顿"""
        try:
            theme = self._get_theme()
            content = self._memo_md_source or (self.memo_data[0].get("content", "") if self.memo_data else "# 预热")
            if content:
                self._render_preview(content, theme, self._memo_font_size)
            else:
                markdown_to_html("# 预热", theme, self._memo_font_size)
        except Exception:
            pass

    def add_memo(self):
        self._memo_saving = True
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            record = {
                "id": int(time.time() * 1000),
                "time": now_str,
                "created": now_str,
                "modified": now_str,
                "title": "新备忘录",
                "content": "",
                "tags": []
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
            # 删除 .md 文件
            memo = self.memo_data[idx]
            fname = memo.get("_file", "")
            if fname:
                try:
                    _fname, fpath = safe_memo_path(self._get_memo_dir(), fname)
                    if os.path.exists(fpath):
                        os.remove(fpath)
                except Exception:
                    pass
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
        keyword = self.memo_search_input.text().strip() if hasattr(self, 'memo_search_input') else ""
        visible_count = 0
        for m in self.memo_data:
            title = m.get("title", "备忘录") or "备忘录"
            content = m.get("content", "") or ""
            tags = m.get("tags", [])
            if not memo_matches_query(m, keyword):
                continue
            first_line = content.split("\n", 1)[0][:40]
            if not first_line:
                first_line = "(空)"
            tag_str = " ".join(f"#{t}" for t in tags) if tags else ""
            display = f"{title}\n{first_line}"
            if tag_str:
                display = f"{title}  {tag_str}\n{first_line}"
            item = QListWidgetItem(display)
            item.setSizeHint(QSize(-1, 50))
            self.memo_list.addItem(item)
            visible_count += 1
        self.memo_stat_label.setText(f"{visible_count}/{len(self.memo_data)} 条" if keyword else f"{len(self.memo_data)} 条")
        self.memo_list.blockSignals(False)

    def _filter_memo_list(self):
        """搜索框文本变化时刷新列表"""
        self._update_memo_list()

    def _on_tags_changed(self):
        """标签输入框编辑完成时保存标签"""
        if self._memo_current_idx < 0 or self._memo_current_idx >= len(self.memo_data):
            return
        text = self.memo_tags_input.text().strip()
        tags = [t.strip() for t in text.replace("，", ",").split(",") if t.strip()]
        self.memo_data[self._memo_current_idx]["tags"] = tags
        self.save_memo()
        self._update_memo_list()

    def _select_memo(self, idx: int):
        if idx < 0 or idx >= len(self.memo_data):
            return
        self._memo_saving = True
        self.memo_list.blockSignals(True)
        self.memo_list.setCurrentRow(idx)
        self.memo_list.blockSignals(False)
        self._memo_saving = False
        self._show_memo_detail(idx)

    def open_memo_at_line(self, idx: int, line_number: int):
        """选中备忘录并将编辑器滚动到指定行。"""
        self._select_memo(idx)
        if line_number <= 1:
            return
        editor = self.memo_content_view
        def _locate():
            doc = editor.document()
            block = doc.findBlockByNumber(max(0, line_number - 1))
            if not block.isValid():
                return
            cursor = QTextCursor(block)
            editor.setTextCursor(cursor)
            editor.ensureCursorVisible()
            scrollbar = editor.verticalScrollBar()
            if scrollbar is not None:
                scrollbar.setValue(max(0, scrollbar.value() - 40))
        QTimer.singleShot(0, _locate)

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
        self.memo_time_label.setText(f"创建：{memo.get('created', '')}　修改：{memo.get('modified', '')}")
        new_content = memo.get("content", "")
        tags = memo.get("tags", [])
        self.memo_tags_input.setText(", ".join(tags))
        # 内容未变化则跳过渲染
        if new_content == self._memo_md_source:
            return
        self._memo_md_source = new_content
        self._invalidate_preview_cache()
        if self._memo_split_mode:
            html = self._render_preview(self._memo_md_source)
            self.memo_content_view.blockSignals(True)
            self.memo_content_view.setPlainText(self._memo_md_source)
            self.memo_content_view.blockSignals(False)
            self.memo_content_view.setReadOnly(False)
            self.memo_split_preview.setHtml(html)
        elif self._memo_preview_mode:
            html = self._render_preview(self._memo_md_source)
            self.memo_content_view.setHtml(html)
            self.memo_content_view.setReadOnly(True)
        else:
            self.memo_content_view.blockSignals(True)
            self.memo_content_view.setPlainText(self._memo_md_source)
            self.memo_content_view.blockSignals(False)
        QTimer.singleShot(0, self._prewarm_preview)

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
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if not memo.get("created"):
                memo["created"] = now_str
            memo["modified"] = now_str
            memo["time"] = now_str
            self._memo_md_source = new_content
            self.save_memo()
            self._memo_is_dirty = False
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

    def _sync_split_scroll(self, value: int, from_editor: bool):
        """分屏模式下同步两个视图的滚动位置"""
        if not self._memo_split_mode or self._memo_syncing_scroll:
            return
        self._memo_syncing_scroll = True
        target = self.memo_split_preview.verticalScrollBar() if from_editor else self.memo_content_view.verticalScrollBar()
        target.setValue(value)
        self._memo_syncing_scroll = False

    def _on_memo_zoom_changed(self, font_size: int):
        """Ctrl+滚轮缩放后，重新渲染预览区域"""
        self._memo_font_size = font_size
        self._invalidate_preview_cache()
        if not self._memo_md_source:
            return
        if self._memo_split_mode:
            html = self._render_preview(self._memo_md_source, font_size=font_size)
            self.memo_split_preview.setHtml(html)
        elif self._memo_preview_mode:
            html = self._render_preview(self._memo_md_source, font_size=font_size)
            scrollbar = self.memo_content_view.verticalScrollBar()
            scroll_pos = scrollbar.value()
            self.memo_content_view.setHtml(html)
            scrollbar.setValue(scroll_pos)

    def _switch_memo_mode(self, mode: str):
        """切换编辑/同步/预览模式（保留滚动位置）"""
        self._memo_preview_mode = (mode == "preview")
        self._memo_split_mode = (mode == "split")
        t = self._get_theme()
        scroll_pos = self.memo_content_view.verticalScrollBar().value()

        # 显式管理按钮选中状态（未使用 QButtonGroup，确保互斥）
        self.btn_memo_edit.setChecked(mode == "edit")
        self.btn_memo_split.setChecked(mode == "split")
        self.btn_memo_preview.setChecked(mode == "preview")

        if mode == "preview":
            self._memo_md_source = self.memo_content_view.toPlainText()
            html = self._render_preview(self._memo_md_source, t, self._memo_font_size)
            self.memo_content_view.setHtml(html)
            self.memo_content_view.setReadOnly(True)
            self.memo_content_view.setVisible(True)
            self.memo_split_preview.setVisible(False)
        elif mode == "split":
            html = self._render_preview(self._memo_md_source, t, self._memo_font_size)
            self.memo_content_view.blockSignals(True)
            self.memo_content_view.setPlainText(self._memo_md_source)
            self.memo_content_view.blockSignals(False)
            self.memo_content_view.setReadOnly(False)
            self.memo_content_view.setVisible(True)
            self.memo_split_preview.setHtml(html)
            self.memo_split_preview.setVisible(True)
        else:  # edit
            self.memo_content_view.blockSignals(True)
            self.memo_content_view.setPlainText(self._memo_md_source)
            self.memo_content_view.blockSignals(False)
            self.memo_content_view.setReadOnly(False)
            self.memo_content_view.setVisible(True)
            self.memo_split_preview.setVisible(False)

        self.memo_content_view.verticalScrollBar().setValue(scroll_pos)

        # 更新按钮样式
        btn_ss = f"QPushButton {{ background: transparent; color: {t.text_secondary}; border: none; border-radius: 6px; font-size: 13px; padding: 0; }}"
        active_ss = f"QPushButton {{ background: transparent; color: #FFFFFF; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; padding: 0; }}"
        self.btn_memo_edit.setStyleSheet(active_ss if mode == "edit" else btn_ss)
        self.btn_memo_split.setStyleSheet(active_ss if mode == "split" else btn_ss)
        self.btn_memo_preview.setStyleSheet(active_ss if mode == "preview" else btn_ss)
        self._memo_seg_ctrl.update_position(animated=True)

    def _on_memo_text_changed(self):
        if self._memo_current_idx < 0:
            return
        if self._memo_preview_mode and not self._memo_split_mode:
            return
        self._memo_md_source = self.memo_content_view.toPlainText()
        self._invalidate_preview_cache()
        if self._memo_split_mode:
            # debounce：停止上一次定时器，150ms 后统一渲染
            self._preview_debounce_timer.stop()
            self._preview_debounce_timer.start()
        self._memo_is_dirty = True
        self._auto_save_timer.stop()
        self._auto_save_timer.start()

    def _auto_save_draft(self):
        """定时自动保存草稿"""
        if self._memo_is_dirty and self._memo_current_idx >= 0:
            self._save_memo_edit(silent=True)
            self._auto_save_timer.stop()

    # ── 预览渲染优化 ──

    def _invalidate_preview_cache(self):
        """清除预览缓存"""
        self._preview_cache = None
        self._preview_cache_key = None

    def _render_preview(self, content: str, theme=None, font_size: int = None) -> str:
        """带缓存的 Markdown→HTML 渲染，相同内容不重复计算"""
        if theme is None:
            theme = self._get_theme()
        if font_size is None:
            font_size = self._memo_font_size
        key = (content, id(theme), font_size)
        if self._preview_cache_key == key and self._preview_cache is not None:
            return self._preview_cache
        html = markdown_to_html(content, theme, font_size)
        self._preview_cache = html
        self._preview_cache_key = key
        return html

    def _do_debounced_preview(self):
        """debounce 定时器触发：执行延迟的预览渲染"""
        if self._memo_split_mode and self._memo_md_source is not None:
            html = self._render_preview(self._memo_md_source)
            self.memo_split_preview.setHtml(html)

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
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                record = {
                    "id": int(time.time() * 1000) + imported,
                    "time": now_str,
                    "created": now_str,
                    "modified": now_str,
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

    def _get_memo_dir(self) -> str:
        """获取备忘录存储目录"""
        custom_path = self._get_memo_path() if self._get_memo_path else None
        return resolve_memo_dir(custom_path)

    def _safe_memo_path(self, memo_dir: str, fname: str) -> tuple[str, str]:
        """兼容旧测试，实际实现位于 memo_storage。"""
        return safe_memo_path(memo_dir, fname)

    def load_memo(self):
        """加载备忘录数据。"""
        return load_memos(self._get_memo_dir())

    def save_memo(self):
        """保存备忘录数据。"""
        try:
            save_memos(self.memo_data, self._get_memo_dir())
        except Exception as e:
            logger.exception("保存备忘录失败: %s", e)

    def _clear_memo_detail(self):
        self._memo_current_idx = -1
        self.memo_title_input.clear()
        self.memo_time_label.clear()
        self.memo_content_view.clear()
        self.memo_tags_input.clear()
        self._memo_md_source = ""

    def resizeEvent(self, event):
        super().resizeEvent(event)

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
        self._md_highlighter._build_rules()
        self._md_highlighter.rehighlight()
        self.memo_content_view.setStyleSheet(get_text_edit_stylesheet(t))
        self.memo_split_preview.setStyleSheet(get_text_edit_stylesheet(t))
        if self._memo_preview_mode or self._memo_split_mode:
            self._invalidate_preview_cache()
            html = self._render_preview(self._memo_md_source, t, self._memo_font_size)
            if self._memo_split_mode:
                self.memo_split_preview.setHtml(html)
            else:
                self.memo_content_view.setHtml(html)
        # 分段控件主题（与设置页风格一致）
        self._memo_seg_ctrl.set_accent(t.accent)
        seg_container = self.btn_memo_edit.parent()
        if seg_container:
            seg_container.setStyleSheet(f"""
                QFrame#memoSegContainer {{
                    background: {t.bg_neutral_button};
                    border: 1px solid {t.border_subtle};
                    border-radius: 8px;
                }}
            """)
        btn_ss = f"QPushButton {{ background: transparent; color: {t.text_secondary}; border: none; border-radius: 6px; font-size: 13px; padding: 0; }}"
        active_ss = f"QPushButton {{ background: transparent; color: #FFFFFF; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; padding: 0; }}"
        mode = "split" if self._memo_split_mode else ("preview" if self._memo_preview_mode else "edit")
        self.btn_memo_edit.setChecked(mode == "edit")
        self.btn_memo_split.setChecked(mode == "split")
        self.btn_memo_preview.setChecked(mode == "preview")
        self.btn_memo_edit.setStyleSheet(active_ss if mode == "edit" else btn_ss)
        self.btn_memo_split.setStyleSheet(active_ss if mode == "split" else btn_ss)
        self.btn_memo_preview.setStyleSheet(active_ss if mode == "preview" else btn_ss)
        # 延迟更新滑块位置，确保按钮尺寸已计算
        QTimer.singleShot(0, lambda: self._memo_seg_ctrl.update_position(animated=False))
        # 搜索框 + 标签输入框
        _input_ss = f"""
            QLineEdit {{
                background: {t.bg_input};
                color: {t.text_primary};
                border: 1px solid {t.border_subtle};
                border-radius: 6px;
                padding: 0 8px;
                font-size: 12px;
            }}
            QLineEdit:focus {{ border: 1px solid {t.accent}; }}
        """
        if hasattr(self, 'memo_search_input'):
            self.memo_search_input.setStyleSheet(_input_ss)
        if hasattr(self, 'memo_tags_input'):
            self.memo_tags_input.setStyleSheet(f"""
                QLineEdit {{
                    background: {t.bg_input};
                    color: {t.text_primary};
                    border: 1px solid {t.border_subtle};
                    border-radius: 4px;
                    padding: 0 6px;
                    font-size: 11px;
                }}
                QLineEdit:focus {{ border: 1px solid {t.accent}; }}
            """)

    def apply_language(self, lang: str):
        self.memo_btn_save.setText("Save" if lang == "en" else "保存")
        self.btn_memo_edit.setText("Edit" if lang == "en" else "编辑")
        self.btn_memo_split.setText("Split" if lang == "en" else "同步")
        self.btn_memo_preview.setText("Preview" if lang == "en" else "预览")
        self._memo_btn_add.setText("New" if lang == "en" else "新建")
        self._memo_btn_import.setText("Import" if lang == "en" else "导入")
        self._memo_btn_export.setText("Export" if lang == "en" else "导出")
        self._memo_btn_delete.setText("Delete" if lang == "en" else "删除")
        if hasattr(self, 'memo_title_input'):
            self.memo_title_input.setPlaceholderText("Title" if lang == "en" else "标题")
        if hasattr(self, 'memo_search_input'):
            self.memo_search_input.setPlaceholderText("Search..." if lang == "en" else "搜索备忘录...")
        if hasattr(self, 'memo_tags_input'):
            self.memo_tags_input.setPlaceholderText("comma separated" if lang == "en" else "逗号分隔，如：工作,重要")
