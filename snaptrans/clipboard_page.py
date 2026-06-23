"""剪切板页面模块"""

import os
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QMenu, QDialog, QLineEdit
)
from PySide6.QtGui import QIcon, QFont, QGuiApplication
from PySide6.QtCore import Qt

from .utils import get_config_dir, ensure_config_dir
from .themes import DARK, LIGHT, get_status_list_stylesheet, get_clear_history_stylesheet
from .clipboard_dialog import ClipboardEditDialog

import re
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtCore import QSize


def _load_svg_icon(svg_path: str, size: int = 20, color: str = None) -> QPixmap:
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


class ClipboardPage(QWidget):
    def __init__(self, parent, *,
                 get_config_path,
                 get_theme,
                 get_icons_dir,
                 get_icon_clr,
                 on_append_status,
                 get_clip_data,
                 set_clip_data,
                 get_current_lang,
                 ):
        super().__init__(parent)
        self._get_config_path = get_config_path
        self._get_theme = get_theme
        self._get_icons_dir = get_icons_dir
        self._get_icon_clr = get_icon_clr
        self._on_append_status = on_append_status
        self._get_clip_data = get_clip_data
        self._set_clip_data = set_clip_data
        self._get_current_lang = get_current_lang
        self.clipboard_list = None
        self.search_input = None
        self._multi_select_mode = False
        self._build_ui()
        if hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(lambda _: self.apply_theme())
        if hasattr(parent, 'language_changed'):
            parent.language_changed.connect(self.apply_language)

    @property
    def _clipboard_data(self):
        return self._get_clip_data()

    @_clipboard_data.setter
    def _clipboard_data(self, value):
        self._set_clip_data(value)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(16)

        t = self._get_theme()
        icons_dir = self._get_icons_dir()
        icon_clr = self._get_icon_clr()

        clip_frame = QFrame()
        clip_frame.setObjectName("clipFrame")
        clip_frame.setStyleSheet(f"""
            QFrame#clipFrame {{
                background: {t.bg_panel};
                border: 1px solid {t.border_subtle};
                border-radius: 8px;
            }}
        """)
        clip_vbox = QVBoxLayout(clip_frame)
        clip_vbox.setContentsMargins(10, 8, 10, 8)
        clip_vbox.setSpacing(6)

        # 顶部行：搜索框 + 按钮
        clip_header = QHBoxLayout()
        clip_header.setSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {t.bg_input};
                color: {t.text_primary};
                border: 1px solid {t.border_subtle};
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 13px;
            }}
        """)
        self.search_input.textChanged.connect(self._filter_clipboard)
        clip_header.addWidget(self.search_input, 1)

        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setStyleSheet(get_clear_history_stylesheet(t))
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_select_all.setVisible(False)
        clip_header.addWidget(self.btn_select_all)

        self.btn_cancel_select = QPushButton("取消")
        self.btn_cancel_select.setStyleSheet(get_clear_history_stylesheet(t))
        self.btn_cancel_select.clicked.connect(self._exit_selection_mode)
        self.btn_cancel_select.setVisible(False)
        clip_header.addWidget(self.btn_cancel_select)

        self.btn_delete_selected = QPushButton("删除选中")
        self.btn_delete_selected.setIcon(QIcon(_load_svg_icon(os.path.join(icons_dir, "clear.svg"), 16, icon_clr)))
        self.btn_delete_selected.setIconSize(QSize(16, 16))
        self.btn_delete_selected.setStyleSheet(get_clear_history_stylesheet(t))
        self.btn_delete_selected.clicked.connect(self._delete_selected)
        self.btn_delete_selected.setVisible(False)
        clip_header.addWidget(self.btn_delete_selected)

        clip_vbox.addLayout(clip_header)

        self.clipboard_list = QListWidget()
        self.clipboard_list.setStyleSheet(get_status_list_stylesheet(t))
        self.clipboard_list.setMinimumHeight(200)
        self.clipboard_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.clipboard_list.customContextMenuRequested.connect(self._on_clipboard_context_menu)
        self.clipboard_list.itemChanged.connect(self._on_item_changed)
        self.clipboard_list.itemClicked.connect(self._on_item_clicked)
        clip_vbox.addWidget(self.clipboard_list, 1)

        layout.addWidget(clip_frame, 1)

        bottom_row = QHBoxLayout()
        tip = QLabel("双击复制 · 右键菜单（多选/锁定/删除）")
        _tip_ss = f"font-size:11px; color:{t.text_muted}; border:none; background:transparent;"
        tip.setStyleSheet(_tip_ss)
        bottom_row.addWidget(tip)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        self._update_clipboard_list()

    def _on_clipboard_context_menu(self, pos):
        item = self.clipboard_list.itemAt(pos)
        if not item:
            return
        idx = self.clipboard_list.row(item)
        if not (0 <= idx < len(self._clipboard_data)):
            return
        record = self._clipboard_data[idx]
        menu = QMenu(self.clipboard_list)
        t = self._get_theme()
        menu.setStyleSheet(f"""
            QMenu {{
                background: {t.bg_panel};
                color: {t.text_primary};
                border: 1px solid {t.border_subtle};
                border-radius: 8px;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 8px 28px;
                border-radius: 8px;
                font-size: 13px;
            }}
            QMenu::item:selected {{
                background: {('rgba(255,255,255,0.06)' if t.is_dark else 'rgba(0,0,0,0.05)')};
                color: {t.accent};
            }}
            QMenu::separator {{
                height: 1px;
                background: {t.border_subtle};
                margin: 4px 8px;
            }}
        """)
        lang = self._get_current_lang()
        is_en = lang == "en"
        copy_action = menu.addAction("Copy" if is_en else "复制")
        edit_action = menu.addAction("Edit" if is_en else "编辑")
        lock_action = menu.addAction("Unlock  " if record.get("locked") else "Lock  ") if is_en else menu.addAction("解锁  " if record.get("locked") else "锁定  ")
        menu.addSeparator()
        multi_action = menu.addAction("Multi-select" if is_en else "多选")
        menu.addSeparator()
        del_action = menu.addAction("Delete" if is_en else "删除")
        for a in (copy_action, edit_action, lock_action, del_action):
            f = a.font()
            f.setStyleHint(QFont.StyleHint.Monospace)
            a.setFont(f)
        chosen = menu.exec(self.clipboard_list.mapToGlobal(pos))
        if chosen == copy_action:
            QGuiApplication.clipboard().setText(record["text"])
        elif chosen == edit_action:
            self._edit_clipboard_item(idx)
        elif chosen == lock_action:
            record["locked"] = not record.get("locked", False)
            self._sort_clipboard()
            self.save_clipboard()
            self._update_clipboard_list()
        elif chosen == multi_action:
            self._enter_selection_mode()
        elif chosen == del_action:
            first_visible = self.clipboard_list.indexAt(self.clipboard_list.viewport().rect().topLeft()).row()
            self._clipboard_data.pop(idx)
            self.save_clipboard()
            self._update_clipboard_list()
            target = min(first_visible, max(0, self.clipboard_list.count() - 1))
            if target >= 0:
                self.clipboard_list.scrollToItem(self.clipboard_list.item(target), QListWidget.ScrollHint.PositionAtTop)

    def _edit_clipboard_item(self, idx: int):
        if not (0 <= idx < len(self._clipboard_data)):
            return
        record = self._clipboard_data[idx]
        dlg = ClipboardEditDialog(self, record.get("text", ""), self._get_theme())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_text = dlg.get_text()
            if new_text and new_text != record.get("text"):
                record["text"] = new_text[:2000]
                self.save_clipboard()
                self._update_clipboard_list()
                self._on_append_status("剪切板条目已修改")

    def _on_clipboard_changed(self):
        clipboard = QGuiApplication.clipboard()
        text = clipboard.text().strip()
        if text and len(text) > 1:
            # 全量去重：检查所有条目
            for existing in self._clipboard_data:
                if existing.get("text", "").strip() == text:
                    return
            record = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "text": text[:2000],
                "locked": False,
            }
            self._clipboard_data.insert(0, record)
            self._sort_clipboard()
            self._trim_clipboard()
            self.save_clipboard()
            self._update_clipboard_list()

    def _get_clipboard_max(self) -> int:
        try:
            with open(self._get_config_path(), "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        try:
            v = int(config.get("clipboard_max_items", 50))
            return max(10, min(500, v))
        except Exception:
            return 50

    def _trim_clipboard(self):
        max_items = self._get_clipboard_max()
        if len(self._clipboard_data) <= max_items:
            return
        locked = [r for r in self._clipboard_data if r.get("locked")]
        unlocked = [r for r in self._clipboard_data if not r.get("locked")]
        keep_unlocked = max(0, max_items - len(locked))
        unlocked = unlocked[:keep_unlocked]
        self._clipboard_data = locked + unlocked

    def _sort_clipboard(self):
        locked = [r for r in self._clipboard_data if r.get("locked")]
        unlocked = [r for r in self._clipboard_data if not r.get("locked")]
        locked.sort(key=lambda r: r.get("time", ""), reverse=True)
        unlocked.sort(key=lambda r: r.get("time", ""), reverse=True)
        self._clipboard_data = locked + unlocked

    def _update_clipboard_list(self, restore_scroll=False, scroll_pos=None):
        """更新列表，restore_scroll=True 时保持滚动位置"""
        scroll_val = scroll_pos if scroll_pos is not None else (self.clipboard_list.verticalScrollBar().value() if restore_scroll else 0)
        self.clipboard_list.clear()
        icons_dir = self._get_icons_dir()
        icon_clr = self._get_icon_clr()
        lock_icon = _load_svg_icon(os.path.join(icons_dir, "lock.svg"), 14, icon_clr)
        lang = self._get_current_lang()
        lock_text = "[Locked]" if lang == "en" else "[锁定]"
        for r in self._clipboard_data[:200]:
            if r.get("locked"):
                preview = r["text"][:60].replace("\n", " ")
                item = QListWidgetItem(lock_icon, f"{lock_text} {r['time']} {preview}")
            else:
                preview = r["text"][:60].replace("\n", " ")
                item = QListWidgetItem(f"      {r['time']} {preview}")
            self.clipboard_list.addItem(item)
        if restore_scroll:
            self.clipboard_list.verticalScrollBar().setValue(min(scroll_val, self.clipboard_list.verticalScrollBar().maximum()))

    def _copy_clipboard_item(self, item: QListWidgetItem):
        idx = self.clipboard_list.row(item)
        if 0 <= idx < len(self._clipboard_data):
            text = self._clipboard_data[idx]["text"]
            QGuiApplication.clipboard().setText(text)

    def load_clipboard(self):
        clipboard_file = os.path.join(get_config_dir(), "clipboard.json")
        if os.path.exists(clipboard_file):
            try:
                with open(clipboard_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for r in data:
                    if "locked" not in r:
                        r["locked"] = False
                locked = [r for r in data if r.get("locked")]
                unlocked = [r for r in data if not r.get("locked")]
                locked.sort(key=lambda r: r.get("time", ""), reverse=True)
                unlocked.sort(key=lambda r: r.get("time", ""), reverse=True)
                # 去重：保留每条文本的最新一条
                seen = set()
                deduped = []
                for r in locked + unlocked:
                    t = r.get("text", "").strip()
                    if t and t in seen:
                        continue
                    if t:
                        seen.add(t)
                    deduped.append(r)
                return deduped
            except Exception:
                return []
        return []

    def save_clipboard(self):
        try:
            ensure_config_dir()
            clipboard_file = os.path.join(get_config_dir(), "clipboard.json")
            with open(clipboard_file, "w", encoding="utf-8") as f:
                json.dump(self._clipboard_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def clear_clipboard(self):
        before = len(self._clipboard_data)
        self._clipboard_data = [r for r in self._clipboard_data if r.get("locked")]
        removed = before - len(self._clipboard_data)
        self.save_clipboard()
        self._update_clipboard_list()
        if removed > 0:
            self._on_append_status(f"已清空 {removed} 条剪切板历史（保留 {len(self._clipboard_data)} 条锁定项）")

    def _filter_clipboard(self, text):
        text = text.lower().strip()
        for i in range(self.clipboard_list.count()):
            item = self.clipboard_list.item(i)
            if text:
                item.setHidden(text not in item.text().lower())
            else:
                item.setHidden(False)

    def _enter_selection_mode(self):
        """右键选择'多选'后进入多选模式，显示复选框"""
        self._multi_select_mode = True
        self.btn_select_all.setVisible(True)
        self.btn_cancel_select.setVisible(True)
        self.btn_delete_selected.setVisible(True)
        self._show_checkboxes(True)
        self._update_delete_btn_state()

    def _on_item_clicked(self, item):
        """点击条目直接切换复选框"""
        if not self._multi_select_mode:
            return
        # 锁定项不允许勾选
        idx = self.clipboard_list.row(item)
        if 0 <= idx < len(self._clipboard_data) and self._clipboard_data[idx].get("locked"):
            return
        item.setCheckState(Qt.CheckState.Checked if item.checkState() != Qt.CheckState.Checked else Qt.CheckState.Unchecked)
        self._update_delete_btn_state()

    def _on_item_changed(self, item):
        """复选框状态变化时更新计数"""
        if self._multi_select_mode:
            self._update_delete_btn_state()

    def _show_checkboxes(self, show):
        """显示/隐藏所有非锁定项的复选框"""
        self.clipboard_list.blockSignals(True)
        for i in range(self.clipboard_list.count()):
            item = self.clipboard_list.item(i)
            if show:
                # 锁定项不显示复选框
                if 0 <= i < len(self._clipboard_data) and self._clipboard_data[i].get("locked"):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                else:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    if item.checkState() != Qt.CheckState.Checked:
                        item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
        self.clipboard_list.blockSignals(False)

    def _select_all(self):
        """全选/取消全选切换"""
        # 检查是否已经全选
        all_checked = all(
            self.clipboard_list.item(i).checkState() == Qt.CheckState.Checked
            for i in range(self.clipboard_list.count())
            if 0 <= i < len(self._clipboard_data) and not self._clipboard_data[i].get("locked")
        )
        self.clipboard_list.blockSignals(True)
        for i in range(self.clipboard_list.count()):
            item = self.clipboard_list.item(i)
            if 0 <= i < len(self._clipboard_data) and not self._clipboard_data[i].get("locked"):
                item.setCheckState(Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked)
        self.clipboard_list.blockSignals(False)
        self._update_delete_btn_state()

    def _update_delete_btn_state(self):
        count = sum(1 for i in range(self.clipboard_list.count())
                    if self.clipboard_list.item(i).checkState() == Qt.CheckState.Checked)
        self.btn_delete_selected.setEnabled(count > 0)
        self.btn_delete_selected.setText(f"删除选中({count})" if count else "删除选中")

    def _delete_selected(self):
        """删除勾选的条目"""
        selected_indices = []
        for i in range(self.clipboard_list.count()):
            if self.clipboard_list.item(i).checkState() == Qt.CheckState.Checked:
                selected_indices.append(i)
        if not selected_indices:
            return
        # 保存当前可见的第一项索引
        first_visible = self.clipboard_list.indexAt(self.clipboard_list.viewport().rect().topLeft()).row()
        for i in reversed(selected_indices):
            if 0 <= i < len(self._clipboard_data):
                self._clipboard_data.pop(i)
        self.save_clipboard()
        self._multi_select_mode = False
        self.btn_select_all.setVisible(False)
        self.btn_cancel_select.setVisible(False)
        self.btn_delete_selected.setVisible(False)
        self.btn_delete_selected.setText("删除选中")
        self.clipboard_list.blockSignals(True)
        self._update_clipboard_list()
        # 恢复到删除前的可见位置附近
        target = min(first_visible, max(0, self.clipboard_list.count() - 1))
        if target >= 0:
            self.clipboard_list.scrollToItem(self.clipboard_list.item(target), QListWidget.ScrollHint.PositionAtTop)
        self.clipboard_list.blockSignals(False)
        self._on_append_status(f"已删除 {len(selected_indices)} 条记录")

    def _exit_selection_mode(self):
        """退出多选模式，重建列表去除复选框"""
        self._multi_select_mode = False
        self.btn_select_all.setVisible(False)
        self.btn_cancel_select.setVisible(False)
        self.btn_delete_selected.setVisible(False)
        self.btn_delete_selected.setText("删除选中")
        # 重建列表，新 item 没有复选框
        self.clipboard_list.blockSignals(True)
        self._update_clipboard_list()
        self.clipboard_list.blockSignals(False)

    def apply_theme(self):
        """刷新剪切板页主题样式"""
        t = self._get_theme()
        if hasattr(self, 'search_input'):
            self.search_input.setStyleSheet(f"""
                QLineEdit {{
                    background: {t.bg_input};
                    color: {t.text_primary};
                    border: 1px solid {t.border_subtle};
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 13px;
                }}
            """)
        for btn_attr in ('btn_select_all', 'btn_cancel_select', 'btn_delete_selected'):
            if hasattr(self, btn_attr):
                getattr(self, btn_attr).setStyleSheet(get_clear_history_stylesheet(t))

    def apply_language(self, lang: str):
        if hasattr(self, 'search_input'):
            self.search_input.setPlaceholderText("Search..." if lang == "en" else "搜索...")
        if hasattr(self, 'btn_delete_selected'):
            self.btn_delete_selected.setText("Delete Selected" if lang == "en" else "删除选中")
        if hasattr(self, 'btn_select_all'):
            self.btn_select_all.setText("Select All" if lang == "en" else "全选")
        if hasattr(self, 'btn_cancel_select'):
            self.btn_cancel_select.setText("Cancel" if lang == "en" else "取消")
        # 刷新列表中的锁定标记
        self._update_clipboard_list()
