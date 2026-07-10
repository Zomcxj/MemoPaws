"""剪切板页面模块"""

import os
import json
import hashlib
import uuid
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QMenu, QDialog, QLineEdit,
    QScrollArea, QGridLayout, QStackedLayout, QSizePolicy, QCheckBox,
    QAbstractScrollArea
)
from PySide6.QtGui import QIcon, QFont, QGuiApplication, QPixmap, QImage
from PySide6.QtCore import Qt, QSize, QTimer

from ..core.utils import get_config_dir, ensure_config_dir, load_svg_icon
from ..core.themes import DARK, LIGHT, get_status_list_stylesheet, get_clear_history_stylesheet
from ..ui.segmented_control import AnimatedSegmentedControl
from .clipboard_dialog import ClipboardEditDialog


class ZoomableImageLabel(QLabel):
    """图片预览标签：滚轮缩放，双击恢复适配大小。"""

    FIT_SIZE = QSize(900, 700)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QPixmap()
        self.scale_factor = 1.0
        self._drag_pos = None
        self._drag_global_pos = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_image(self, pixmap: QPixmap):
        self._image = pixmap
        self.fit_to_view()

    def fit_to_view(self):
        self.scale_factor = 1.0
        self._render()

    def zoom(self, factor: float):
        self.scale_factor = max(0.2, min(8.0, self.scale_factor * factor))
        self._render()

    def _render(self):
        if self._image.isNull():
            return
        fit = self._image.scaled(
            self.FIT_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        size = fit.size() * self.scale_factor
        pixmap = self._image.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())

    def wheelEvent(self, event):
        self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.fit_to_view()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.position().toPoint()
            self._drag_global_pos = event.globalPosition().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is None:
            super().mouseMoveEvent(event)
            return
        scroll = self.parentWidget().parentWidget()
        delta = event.globalPosition().toPoint() - self._drag_global_pos
        scroll.horizontalScrollBar().setValue(scroll.horizontalScrollBar().value() - delta.x())
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().value() - delta.y())
        self._drag_pos = event.position().toPoint()
        self._drag_global_pos = event.globalPosition().toPoint()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self._drag_pos = None
            self._drag_global_pos = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ClipboardPage(QWidget):
    SEARCH_DEBOUNCE_MS = 180
    GRID_COLUMNS = 4

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
        self.btn_view_list = None
        self.btn_view_grid = None
        self._view_seg_container = None
        self._view_seg_ctrl = None
        self._view_mode = "list"
        self._clipboard_stack = None
        self._grid_scroll = None
        self._grid_container = None
        self._grid_layout = None
        self._grid_selected_indices = set()
        self._clipboard_read_queued = False
        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(self.SEARCH_DEBOUNCE_MS)
        self._search_debounce_timer.timeout.connect(self._apply_clipboard_filter)
        self._multi_select_mode = False
        self._build_ui()
        self._load_view_mode_setting()
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
        self.search_input.setFixedHeight(34)
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
        self.search_input.textChanged.connect(self._queue_clipboard_filter)
        clip_header.addWidget(self.search_input, 1)

        self._view_seg_container = QFrame()
        self._view_seg_container.setObjectName("clipViewSegContainer")
        self._view_seg_container.setFixedSize(162, 34)
        self._view_seg_container.setStyleSheet(f"""
            QFrame#clipViewSegContainer {{
                background: {t.bg_neutral_button};
                border: 1px solid {t.border_subtle};
                border-radius: 8px;
            }}
        """)
        seg_layout = QHBoxLayout(self._view_seg_container)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(0)
        self.btn_view_list = QPushButton("列表")
        self.btn_view_list.setCheckable(True)
        self.btn_view_list.setFixedSize(80, 32)
        self.btn_view_list.clicked.connect(lambda: self._set_view_mode("list"))
        seg_layout.addWidget(self.btn_view_list)
        self.btn_view_grid = QPushButton("组件")
        self.btn_view_grid.setCheckable(True)
        self.btn_view_grid.setFixedSize(80, 32)
        self.btn_view_grid.clicked.connect(lambda: self._set_view_mode("grid"))
        seg_layout.addWidget(self.btn_view_grid)
        self._view_seg_ctrl = AnimatedSegmentedControl(self._view_seg_container, self.btn_view_list, self.btn_view_grid)
        clip_header.addWidget(self._view_seg_container, 0, Qt.AlignmentFlag.AlignRight)

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
        self.btn_delete_selected.setIcon(QIcon(load_svg_icon(os.path.join(icons_dir, "clear.svg"), 16, icon_clr)))
        self.btn_delete_selected.setIconSize(QSize(16, 16))
        self.btn_delete_selected.setStyleSheet(get_clear_history_stylesheet(t))
        self.btn_delete_selected.clicked.connect(self._delete_selected)
        self.btn_delete_selected.setVisible(False)
        clip_header.addWidget(self.btn_delete_selected)

        clip_vbox.addLayout(clip_header)

        self._clipboard_stack = QStackedLayout()

        self.clipboard_list = QListWidget(clip_frame)
        self.clipboard_list.setStyleSheet(get_status_list_stylesheet(t))
        self.clipboard_list.setMinimumHeight(200)
        self.clipboard_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.clipboard_list.customContextMenuRequested.connect(self._on_clipboard_context_menu)
        self.clipboard_list.itemChanged.connect(self._on_item_changed)
        self.clipboard_list.itemClicked.connect(self._on_item_clicked)
        self._clipboard_stack.addWidget(self.clipboard_list)

        self._grid_scroll = QScrollArea()
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._grid_scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self._grid_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._grid_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; margin:0; padding:0; }")
        self._grid_container = QWidget()
        self._grid_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._grid_container.setMinimumWidth(0)
        self._grid_container.setStyleSheet("background: transparent; margin:0; padding:0;")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(8)
        for col in range(self.GRID_COLUMNS):
            self._grid_layout.setColumnStretch(col, 1)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._grid_scroll.setWidget(self._grid_container)
        self._clipboard_stack.addWidget(self._grid_scroll)

        clip_vbox.addLayout(self._clipboard_stack, 1)
        self._clipboard_stack.setCurrentIndex(0)

        layout.addWidget(clip_frame, 1)

        bottom_row = QHBoxLayout()
        tip = QLabel("双击复制 · 右键菜单（多选/锁定/删除）")
        _tip_ss = f"font-size:11px; color:{t.text_muted}; border:none; background:transparent;"
        tip.setStyleSheet(_tip_ss)
        bottom_row.addWidget(tip)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        self._update_clipboard_list()

    def _set_view_mode(self, mode: str, *, save: bool = True):
        self._view_mode = "grid" if mode == "grid" else "list"
        if save:
            self._save_view_mode_setting()
        self._update_view_seg_style()
        self._clipboard_stack.setCurrentIndex(0 if self._view_mode == "list" else 1)
        if self._view_mode == "grid":
            self._refresh_grid_view()

    def _load_view_mode_setting(self):
        try:
            with open(self._get_config_path(), "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        self._set_view_mode(config.get("clipboard_view_mode", "list"), save=False)

    def _update_view_seg_style(self):
        if not self.btn_view_list or not self.btn_view_grid:
            return
        t = self._get_theme()
        normal = f"QPushButton {{ background: transparent; color: {t.text_secondary}; border: none; border-radius: 6px; font-size: 13px; padding: 0; }}"
        active = "QPushButton { background: transparent; color: #FFFFFF; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; padding: 0; }"
        is_list = self._view_mode == "list"
        self.btn_view_list.setChecked(is_list)
        self.btn_view_grid.setChecked(not is_list)
        self.btn_view_list.setStyleSheet(active if is_list else normal)
        self.btn_view_grid.setStyleSheet(active if not is_list else normal)
        if self._view_seg_container:
            self._view_seg_container.setStyleSheet(f"""
                QFrame#clipViewSegContainer {{
                    background: {t.bg_neutral_button};
                    border: 1px solid {t.border_subtle};
                    border-radius: 8px;
                }}
            """)
        if self._view_seg_ctrl:
            self._view_seg_ctrl.set_accent(t.accent)
            self._view_seg_ctrl.update_position(animated=True)

    def _save_view_mode_setting(self):
        try:
            with open(self._get_config_path(), "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        config["clipboard_view_mode"] = self._view_mode
        try:
            with open(self._get_config_path(), "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _show_clipboard_menu(self, idx: int, global_pos):
        if not (0 <= idx < len(self._clipboard_data)):
            return
        record = self._clipboard_data[idx]
        menu = QMenu(self)
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
        """)
        lang = self._get_current_lang()
        is_en = lang == "en"
        copy_action = menu.addAction("Copy" if is_en else "复制")
        edit_action = menu.addAction("Edit" if is_en else "编辑")
        lock_action = menu.addAction("Unlock" if record.get("locked") else "Lock") if is_en else menu.addAction("解锁" if record.get("locked") else "锁定")
        delete_action = menu.addAction("Delete" if is_en else "删除")
        chosen = menu.exec(global_pos)
        if chosen == copy_action:
            QGuiApplication.clipboard().setText(record["text"])
        elif chosen == edit_action:
            self._edit_clipboard_item(idx)
        elif chosen == lock_action:
            record["locked"] = not record.get("locked", False)
            self._sort_clipboard()
            self.save_clipboard()
            self._update_clipboard_list()
        elif chosen == delete_action:
            self._delete_clipboard_row(idx)
            return

    def _show_clipboard_actions_menu(self, idx: int, global_pos):
        if not (0 <= idx < len(self._clipboard_data)):
            return
        record = self._clipboard_data[idx]
        lang = self._get_current_lang()
        is_en = lang == "en"
        menu = QMenu(self)
        copy_action = menu.addAction("Copy" if is_en else "复制")
        edit_action = menu.addAction("Edit" if is_en else "编辑")
        lock_action = menu.addAction("Unlock" if record.get("locked") else "Lock") if is_en else menu.addAction("解锁" if record.get("locked") else "锁定")
        multi_action = menu.addAction("Multi-select" if is_en else "多选")
        delete_action = menu.addAction("Delete" if is_en else "删除")
        chosen = menu.exec(global_pos)
        if chosen == copy_action:
            QGuiApplication.clipboard().setText(record.get("text", ""))
        elif chosen == edit_action:
            self._edit_clipboard_record(record)
        elif chosen == lock_action:
            QTimer.singleShot(0, lambda rec=record: self._toggle_clipboard_lock_record(rec))
        elif chosen == multi_action:
            self._enter_selection_mode()
        elif chosen == delete_action:
            QTimer.singleShot(0, lambda rec=record: self._delete_clipboard_record(rec))

    def _toggle_clipboard_lock(self, idx: int):
        if not (0 <= idx < len(self._clipboard_data)):
            return
        self._clipboard_data[idx]["locked"] = not self._clipboard_data[idx].get("locked", False)
        self._sort_clipboard()
        self.save_clipboard()
        self._update_clipboard_list()

    def _toggle_clipboard_lock_record(self, record):
        try:
            idx = self._clipboard_data.index(record)
        except ValueError:
            return
        self._toggle_clipboard_lock(idx)

    def _delete_clipboard_row(self, idx: int):
        if not (0 <= idx < len(self._clipboard_data)):
            return
        record = self._clipboard_data[idx]
        if record.get("kind") == "image" and record.get("image_path"):
            try:
                if os.path.exists(record["image_path"]):
                    os.remove(record["image_path"])
            except Exception:
                pass
        self._clipboard_data.pop(idx)
        self.save_clipboard()
        self._update_clipboard_list()

    def _delete_clipboard_record(self, record):
        try:
            idx = self._clipboard_data.index(record)
        except ValueError:
            return
        self._delete_clipboard_row(idx)

    def _on_clipboard_context_menu(self, pos):
        item = self.clipboard_list.itemAt(pos)
        if not item:
            return
        idx = self.clipboard_list.row(item)
        if not (0 <= idx < len(self._clipboard_data)):
            return
        self._show_clipboard_actions_menu(idx, self.clipboard_list.mapToGlobal(pos))

    def _edit_clipboard_item(self, idx: int):
        if not (0 <= idx < len(self._clipboard_data)):
            return
        self._edit_clipboard_record(self._clipboard_data[idx])

    def _edit_clipboard_record(self, record):
        dlg = ClipboardEditDialog(self, record.get("text", ""), self._get_theme())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_text = dlg.get_text()
            if new_text and new_text != record.get("text"):
                record["text"] = new_text[:2000]
                self.save_clipboard()
                self._update_clipboard_list()
                self._on_append_status("剪切板条目已修改")

    def _on_clipboard_changed(self):
        if self._clipboard_read_queued:
            return
        self._clipboard_read_queued = True
        QTimer.singleShot(0, self._read_clipboard)

    def _read_clipboard(self):
        self._clipboard_read_queued = False
        clipboard = QGuiApplication.clipboard()
        mime = clipboard.mimeData()
        pixmap = clipboard.pixmap()
        if not pixmap.isNull():
            self._add_clipboard_image_record(pixmap)
            return
        image = clipboard.image()
        if not image.isNull():
            self._add_clipboard_image_record(QPixmap.fromImage(image))
            return
        if mime and mime.hasImage():
            var = mime.imageData()
            if var.isValid():
                qimg = var.value()
                if isinstance(qimg, QImage) and not qimg.isNull():
                    self._add_clipboard_image_record(QPixmap.fromImage(qimg))
                    return
        if mime and mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    ext = os.path.splitext(path)[1].lower()
                    if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
                        loaded = QPixmap(path)
                        if not loaded.isNull():
                            self._add_clipboard_image_record(loaded)
                            return
        text = clipboard.text().strip()
        if text and len(text) > 1:
            self._add_clipboard_text_record(text)

    def _clipboard_images_dir(self) -> str:
        return os.path.join(get_config_dir(), "clipboard_images")

    def _add_clipboard_text_record(self, text: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for existing in self._clipboard_data:
            if existing.get("kind", "text") == "text" and existing.get("text", "").strip() == text:
                existing["time"] = now
                self._sort_clipboard()
                self.save_clipboard()
                self._update_clipboard_list()
                return
        record = {"time": now, "text": text[:2000], "locked": False, "kind": "text"}
        self._clipboard_data.insert(0, record)
        self._sort_clipboard()
        self._trim_clipboard()
        self.save_clipboard()
        self._update_clipboard_list()

    def _add_clipboard_image_record(self, pixmap: QPixmap):
        ensure_config_dir()
        image_bytes = self._pixmap_bytes(pixmap)
        image_hash = hashlib.md5(image_bytes).hexdigest()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for existing in self._clipboard_data:
            if existing.get("kind") == "image" and existing.get("image_hash") == image_hash:
                existing["time"] = now
                self._sort_clipboard()
                self.save_clipboard()
                self._update_clipboard_list()
                return
        os.makedirs(self._clipboard_images_dir(), exist_ok=True)
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
        image_path = os.path.join(self._clipboard_images_dir(), filename)
        pixmap.save(image_path, "PNG")
        record = {
            "time": now,
            "text": filename,
            "locked": False,
            "kind": "image",
            "image_path": image_path,
            "image_hash": image_hash,
            "image_size": [pixmap.width(), pixmap.height()],
        }
        self._clipboard_data.insert(0, record)
        self._sort_clipboard()
        self._trim_clipboard()
        self.save_clipboard()
        self._update_clipboard_list()

    def _pixmap_bytes(self, pixmap: QPixmap) -> bytes:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice

        array = QByteArray()
        buffer = QBuffer(array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        return bytes(array)

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
        self._clipboard_stack.setCurrentIndex(0 if self._view_mode == "list" else 1)
        icons_dir = self._get_icons_dir()
        icon_clr = self._get_icon_clr()
        lock_icon = load_svg_icon(os.path.join(icons_dir, "lock.svg"), 14, icon_clr)
        lang = self._get_current_lang()
        lock_text = "[Locked]" if lang == "en" else "[锁定]"
        for r in self._clipboard_data[:200]:
            if r.get("kind") == "image":
                preview = f"[图片] {os.path.basename(r.get('image_path', r.get('text', '')))}"
            else:
                preview = r["text"][:60].replace("\n", " ")
            if r.get("locked"):
                item = QListWidgetItem(lock_icon, f"{r['time']} {preview}")
            else:
                item = QListWidgetItem(f"{r['time']} {preview}")
            self.clipboard_list.addItem(item)
        if restore_scroll:
            self.clipboard_list.verticalScrollBar().setValue(min(scroll_val, self.clipboard_list.verticalScrollBar().maximum()))
        self._refresh_grid_view()

    def _filtered_clipboard_items(self):
        keyword = self.search_input.text().lower().strip() if self.search_input else ""
        if not keyword:
            return list(enumerate(self._clipboard_data[:200]))
        return [
            (idx, r)
            for idx, r in enumerate(self._clipboard_data[:200])
            if keyword in f"{r.get('time', '')} {r.get('text', '')}".lower()
        ]

    def _refresh_grid_view(self):
        if not self._grid_layout:
            return
        try:
            for i in reversed(range(self._grid_layout.count())):
                item = self._grid_layout.takeAt(i)
                widget = item.widget() if item else None
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()
        except RuntimeError:
            return
        entries = self._filtered_clipboard_items()
        for visible_idx, (source_idx, record) in enumerate(entries):
            row = visible_idx // self.GRID_COLUMNS
            col = visible_idx % self.GRID_COLUMNS
            self._grid_layout.addWidget(self._create_grid_card(source_idx, record), row, col)

    def _create_grid_card(self, source_idx: int, record):
        t = self._get_theme()
        card = QFrame()
        card.setObjectName("clipboardGridCard")
        card.setStyleSheet(f"""
            QFrame#clipboardGridCard {{
                background: {t.bg_panel};
                border: 1px solid {t.border_subtle};
                border-radius: 10px;
            }}
        """)
        card.setMinimumWidth(0)
        card.setMinimumHeight(160)
        card.setMaximumHeight(160)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        title = QLabel(record.get("time", ""))
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title.setStyleSheet(f"font-size:11px; color:{t.text_muted}; border:none;")
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)
        check = None
        if self._multi_select_mode and not record.get("locked"):
            check = QCheckBox()
            check.setChecked(source_idx in self._grid_selected_indices)
            check.stateChanged.connect(lambda state, row_idx=source_idx: self._toggle_grid_selection(row_idx, state == Qt.CheckState.Checked.value))
            top_row.addWidget(check)
        top_row.addWidget(title, 1)
        layout.addLayout(top_row)
        if record.get("kind") == "image" and record.get("image_path") and os.path.exists(record.get("image_path")):
            thumb = QLabel()
            thumb.setObjectName("clipboardThumb")
            pixmap = QPixmap(record["image_path"])
            thumb.setMinimumHeight(80)
            thumb.setMaximumHeight(80)
            thumb.setPixmap(pixmap.scaled(160, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(thumb)
            content_text = os.path.basename(record["image_path"])
        else:
            content_text = (record.get("text", "") or "")[:120].replace("\n", " ")
        content = QLabel(content_text)
        content.setWordWrap(True)
        content.setMinimumWidth(0)
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        content.setStyleSheet(f"font-size:12px; color:{t.text_primary}; border:none;")
        content.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(content, 1)
        badge = None
        if record.get("locked"):
            badge = QLabel("[锁定]" if self._get_current_lang() != "en" else "[Locked]")
            badge.setMinimumWidth(0)
            badge.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            badge.setStyleSheet(f"font-size:11px; color:{t.accent}; border:none;")
            layout.addWidget(badge)

        selected = source_idx in self._grid_selected_indices
        if self._multi_select_mode and selected:
            card.setStyleSheet(f"""
                QFrame#clipboardGridCard {{
                    background: {t.bg_panel};
                    border: 2px solid {t.accent};
                    border-radius: 10px;
                }}
            """)
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda pos, row_idx=source_idx, widget=card: self._show_clipboard_actions_menu(row_idx, widget.mapToGlobal(pos)))
        for widget in (title, content, badge, check):
            if widget is None:
                continue
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            widget.customContextMenuRequested.connect(lambda pos, row_idx=source_idx, w=widget: self._show_clipboard_actions_menu(row_idx, w.mapToGlobal(pos)))

        def mousePressEvent(event, row_idx=source_idx):
            if self._multi_select_mode and not record.get("locked"):
                self._toggle_grid_selection(row_idx, row_idx not in self._grid_selected_indices)
                event.accept()
                return
            if event.button() == Qt.MouseButton.LeftButton and record.get("kind") == "image":
                self._preview_clipboard_image(record.get("image_path"))
                event.accept()
                return
            QFrame.mousePressEvent(card, event)

        def mouseDoubleClickEvent(event):
            event.accept()

        card.mousePressEvent = mousePressEvent
        card.mouseDoubleClickEvent = mouseDoubleClickEvent
        return card

    def _toggle_grid_selection(self, row_idx: int, checked: bool):
        if checked:
            self._grid_selected_indices.add(row_idx)
        else:
            self._grid_selected_indices.discard(row_idx)
        self._refresh_grid_view()
        self._update_delete_btn_state()

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
        removed_records = [r for r in self._clipboard_data if not r.get("locked")]
        self._clipboard_data = [r for r in self._clipboard_data if r.get("locked")]
        for record in removed_records:
            if record.get("kind") == "image" and record.get("image_path"):
                try:
                    if os.path.exists(record["image_path"]):
                        os.remove(record["image_path"])
                except Exception:
                    pass
        removed = before - len(self._clipboard_data)
        self.save_clipboard()
        self._update_clipboard_list()
        if removed > 0:
            self._on_append_status(f"已清空 {removed} 条剪切板历史（保留 {len(self._clipboard_data)} 条锁定项）")

    def _queue_clipboard_filter(self, _text=None):
        self._search_debounce_timer.start()

    def _apply_clipboard_filter(self):
        text = self.search_input.text() if self.search_input is not None else ""
        self._filter_clipboard(text)
        self._refresh_grid_view()

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
        self._grid_selected_indices.clear()
        self.btn_select_all.setVisible(True)
        self.btn_cancel_select.setVisible(True)
        self.btn_delete_selected.setVisible(True)
        self._show_checkboxes(True)
        self._refresh_grid_view()
        self._update_delete_btn_state()

    def _on_item_clicked(self, item):
        """点击条目直接切换复选框"""
        if not self._multi_select_mode:
            idx = self.clipboard_list.row(item)
            if 0 <= idx < len(self._clipboard_data):
                record = self._clipboard_data[idx]
                if record.get("kind") == "image" and record.get("image_path"):
                    self._preview_clipboard_image(record.get("image_path"))
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
        if self._view_mode == "grid":
            visible = [idx for idx, record in self._filtered_clipboard_items() if not record.get("locked")]
            if all(idx in self._grid_selected_indices for idx in visible):
                self._grid_selected_indices.difference_update(visible)
            else:
                self._grid_selected_indices.update(visible)
            self._refresh_grid_view()
            self._update_delete_btn_state()
            return
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
        if self._view_mode == "grid":
            count = len(self._grid_selected_indices)
        else:
            count = sum(1 for i in range(self.clipboard_list.count())
                        if self.clipboard_list.item(i).checkState() == Qt.CheckState.Checked)
        self.btn_delete_selected.setEnabled(count > 0)
        self.btn_delete_selected.setText(f"删除选中({count})" if count else "删除选中")

    def _delete_selected(self):
        """删除勾选的条目"""
        if self._view_mode == "grid":
            selected_indices = sorted(self._grid_selected_indices)
            if not selected_indices:
                return
            for i in reversed(selected_indices):
                if 0 <= i < len(self._clipboard_data):
                    record = self._clipboard_data[i]
                    if record.get("kind") == "image" and record.get("image_path"):
                        try:
                            if os.path.exists(record["image_path"]):
                                os.remove(record["image_path"])
                        except Exception:
                            pass
                    self._clipboard_data.pop(i)
            self._grid_selected_indices.clear()
            self.save_clipboard()
            self._multi_select_mode = False
            self.btn_select_all.setVisible(False)
            self.btn_cancel_select.setVisible(False)
            self.btn_delete_selected.setVisible(False)
            self.btn_delete_selected.setText("删除选中")
            self._update_clipboard_list()
            self._on_append_status(f"已删除 {len(selected_indices)} 条记录")
            return
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
                record = self._clipboard_data[i]
                if record.get("kind") == "image" and record.get("image_path"):
                    try:
                        if os.path.exists(record["image_path"]):
                            os.remove(record["image_path"])
                    except Exception:
                        pass
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

    def _preview_clipboard_image(self, image_path: str):
        if not image_path or not os.path.exists(image_path):
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("图片预览")
        vbox = QVBoxLayout(dlg)
        tip = QLabel("滚轮缩放 · 双击恢复适配")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip.setStyleSheet(f"font-size:11px; color:{self._get_theme().text_muted}; border:none;")
        vbox.addWidget(tip)
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = ZoomableImageLabel()
        label.set_image(QPixmap(image_path))
        scroll.setWidget(label)
        vbox.addWidget(scroll)
        dlg.resize(920, 720)
        dlg.exec()

    def latest_image_record(self):
        for record in self._clipboard_data:
            if record.get("kind") == "image" and record.get("image_path") and os.path.exists(record.get("image_path")):
                return record
        return None

    def _exit_selection_mode(self):
        """退出多选模式，重建列表去除复选框"""
        self._multi_select_mode = False
        self._grid_selected_indices.clear()
        self.btn_select_all.setVisible(False)
        self.btn_cancel_select.setVisible(False)
        self.btn_delete_selected.setVisible(False)
        self.btn_delete_selected.setText("删除选中")
        # 重建列表，新 item 没有复选框
        self.clipboard_list.blockSignals(True)
        self._update_clipboard_list()
        self.clipboard_list.blockSignals(False)
        self._refresh_grid_view()

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
        self._update_view_seg_style()
        self._update_clipboard_list()

    def apply_language(self, lang: str):
        if hasattr(self, 'search_input'):
            self.search_input.setPlaceholderText("Search..." if lang == "en" else "搜索...")
        if hasattr(self, 'btn_delete_selected'):
            self.btn_delete_selected.setText("Delete Selected" if lang == "en" else "删除选中")
        if hasattr(self, 'btn_view_list'):
            self.btn_view_list.setText("List" if lang == "en" else "列表")
        if hasattr(self, 'btn_view_grid'):
            self.btn_view_grid.setText("Grid" if lang == "en" else "组件")
        self._update_view_seg_style()
        if hasattr(self, 'view_mode_combo'):
            self.view_mode_combo.setItemText(0, "List" if lang == "en" else "列表模式")
            self.view_mode_combo.setItemText(1, "Grid" if lang == "en" else "组件模式")
        if hasattr(self, 'btn_select_all'):
            self.btn_select_all.setText("Select All" if lang == "en" else "全选")
        if hasattr(self, 'btn_cancel_select'):
            self.btn_cancel_select.setText("Cancel" if lang == "en" else "取消")
        self._update_clipboard_list()
