"""密钥管理页面"""

import logging
import os
import json
import random
import time
from functools import partial
from PySide6.QtCore import QThread, Signal as pyqtSignal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QComboBox, QScrollArea, QMessageBox,
    QDialog, QDialogButtonBox, QFormLayout, QApplication,
    QDateEdit, QGridLayout, QSizePolicy, QSplitter,
)
from PySide6.QtCore import Qt, QDate, QMimeData, QByteArray, QTimer
from PySide6.QtGui import QIcon, QDrag

from .key_manager import KeyManager
from .key_dialogs import UnlockDialog, EntryDialog, _t
from .utils import normalize_api_url as _normalize_url, test_api_connection, load_svg_icon as _load_svg

logger = logging.getLogger(__name__)


class DraggableCard(QFrame):
    """可拖拽的密钥卡片"""
    def __init__(self, entry_id: int, parent=None):
        super().__init__(parent)
        self.entry_id = entry_id
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is not None:
            distance = (event.pos() - self._drag_start_pos).manhattanLength()
            if distance > 10:
                drag = QDrag(self)
                mime_data = QMimeData()
                mime_data.setData("application/x-keycard", QByteArray(str(self.entry_id).encode()))
                drag.setMimeData(mime_data)
                drag.exec(Qt.DropAction.MoveAction)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-keycard"):
            event.acceptProposedAction()
            self.setStyleSheet(self.styleSheet().replace(
                self.property("original_border") or "",
                f"border: 2px solid {self.property('accent_color') or '#2563EB'};"
            ) if self.property("original_border") else None)

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.property("original_style") or "")

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-keycard"):
            source_id = int(event.mimeData().data("application/x-keycard").data().decode())
            target_id = self.entry_id
            if source_id != target_id:
                # 通知父窗口交换顺序
                parent = self.parent()
                while parent and not hasattr(parent, '_swap_entries'):
                    parent = parent.parent()
                if parent:
                    parent._swap_entries(source_id, target_id)
            event.acceptProposedAction()


class _MatrixAnimWorker(QThread):
    """Matrix Decode 动画线程（独立线程驱动，不阻塞UI）"""
    frame_ready = pyqtSignal(str, str)  # entry_id(str), html
    finished = pyqtSignal(str)  # entry_id(str)

    def __init__(self, entry_id, label, chars, target, parent=None):
        super().__init__(parent)
        self._entry_id = str(entry_id)
        self._label = label
        self._chars = chars
        self._target = target
        self._running = True
        self._start_ms = time.time() * 1000

    def stop(self):
        self._running = False

    def run(self):
        n = len(self._target)
        while self._running:
            chars = [random.choice(self._chars) for _ in range(n)]
            display = ''.join(f'<span style="color:#00ff41">{ch}</span>' for ch in chars)
            html = f'<span style="font-family:Consolas,monospace;font-size:12px;font-stretch:condensed;letter-spacing:-0.5px;color:#00ff41;text-shadow:0 0 4px #00ff41;">{display}</span>'
            self.frame_ready.emit(self._entry_id, html)
            time.sleep(0.050)

        self.finished.emit(self._entry_id)


class KeyPage(QWidget):
    """密钥管理页面"""

    # 跨线程信号：单个模型测试完成 (entry_id_str, status_code, elapsed_ms)
    _sig_test_one_done = pyqtSignal(str, int, int)

    def __init__(self, parent, *, get_theme, is_dark, show_message, get_icons_dir, get_icon_clr, get_current_lang):
        super().__init__(parent)
        self._get_theme = get_theme
        self._is_dark = is_dark
        self._show_message = show_message
        self._get_icons_dir = get_icons_dir
        self._get_icon_clr = get_icon_clr
        self._get_current_lang = get_current_lang
        self._km = KeyManager()
        self._sig_test_one_done.connect(self._on_test_one_done)
        self._build_ui()

        if hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(lambda _: self.apply_theme())
        if hasattr(parent, 'language_changed'):
            parent.language_changed.connect(self.apply_language)

    def _build_ui(self):
        t = self._get_theme()
        lang = self._get_current_lang()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(12)

        # 顶部：解锁状态 + 操作按钮
        top = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setStyleSheet(f"font-size:14px; color:{t.text_secondary}; border:none; background:transparent;")
        top.addWidget(self.status_label)
        top.addStretch()

        btn_css = f"""
            QPushButton {{
                background: {t.accent}; color: #FFFFFF;
                border: none; border-radius: 6px;
                padding: 6px 16px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {t.accent_hover}; }}
        """
        btn2_css = f"""
            QPushButton {{
                background: {t.bg_neutral_button}; color: {t.text_secondary};
                border: 1px solid {t.border_subtle}; border-radius: 6px;
                padding: 6px 16px; font-size: 12px;
            }}
            QPushButton:hover {{ background: {t.bg_active}; }}
        """

        self.btn_unlock = QPushButton(_t("解锁", lang))
        self.btn_unlock.setStyleSheet(btn_css)
        self.btn_unlock.clicked.connect(self._on_unlock)
        top.addWidget(self.btn_unlock)

        self.btn_lock = QPushButton(_t("锁定", lang))
        self.btn_lock.setStyleSheet(btn2_css)
        self.btn_lock.clicked.connect(self._on_lock)
        self.btn_lock.hide()
        top.addWidget(self.btn_lock)

        self.btn_remove_master = QPushButton(_t("移除主密码", lang))
        self.btn_remove_master.setStyleSheet(btn2_css)
        self.btn_remove_master.clicked.connect(self._on_remove_master)
        self.btn_remove_master.hide()
        top.addWidget(self.btn_remove_master)

        self.btn_add = QPushButton(_t("添加密钥按钮", lang))
        self.btn_add.setStyleSheet(btn_css)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_add.hide()
        top.addWidget(self.btn_add)

        # 一键测试全部按钮
        self.btn_test_all = QPushButton(_t("测试速度", lang))
        self.btn_test_all.setStyleSheet(btn2_css)
        self.btn_test_all.clicked.connect(self._test_all_entries)
        self.btn_test_all.hide()
        top.addWidget(self.btn_test_all)

        layout.addLayout(top)

        # 左右分栏：左侧大模型密钥，右侧普通密钥
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(10)
        self._splitter.setStyleSheet("QSplitter::handle { background: transparent; margin: 0 3px; }")
        self._splitter.setChildrenCollapsible(False)

        # 左侧：大模型密钥卡片网格
        left_frame = QFrame()
        left_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(4)

        left_title = QLabel("🤖 " + (_t("大模型密钥", lang)))
        self._left_title = left_title
        left_title.setFixedHeight(28)
        left_title.setStyleSheet(f"font-size:13px; font-weight:600; color:{t.text_secondary}; border:none; background:transparent;")
        left_title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        left_layout.addWidget(left_title)

        self._llm_container = QWidget()
        self._llm_container.setStyleSheet("background: transparent; margin:0; padding:0;")
        self._llm_grid = QGridLayout(self._llm_container)
        self._llm_grid.setContentsMargins(0, 0, 0, 0)
        self._llm_grid.setSpacing(10)
        self._llm_grid.setColumnStretch(0, 1)
        self._llm_grid.setColumnStretch(1, 1)
        self._llm_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        left_layout.addWidget(self._llm_container, 1)

        # 右侧：普通密钥列表（用 QWidget + 垂直布局，不用 QListWidget）
        right_frame = QFrame()
        right_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(4)

        right_title = QLabel("🔑 " + (_t("普通密钥", lang)))
        self._right_title = right_title
        right_title.setFixedHeight(28)
        right_title.setStyleSheet(f"font-size:13px; font-weight:600; color:{t.text_secondary}; border:none; background:transparent;")
        right_title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        right_layout.addWidget(right_title)

        self._secret_scroll = QScrollArea()
        self._secret_scroll.setWidgetResizable(True)
        self._secret_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._secret_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; margin:0; padding:0; }")
        self._secret_scroll.viewport().setContentsMargins(0, 0, 0, 0)
        self._secret_container = QWidget()
        self._secret_container.setStyleSheet("background: transparent; margin:0; padding:0;")
        self._secret_vbox = QVBoxLayout(self._secret_container)
        self._secret_vbox.setContentsMargins(0, 0, 0, 0)
        self._secret_vbox.setSpacing(4)
        self._secret_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._secret_scroll.setWidget(self._secret_container)
        right_layout.addWidget(self._secret_scroll, 1)

        self._splitter.addWidget(left_frame)
        self._splitter.addWidget(right_frame)
        self._splitter.setSizes([500, 300])
        self._splitter.setContentsMargins(0, 0, 0, 0)
        # 强制两个面板上对齐
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)

        layout.addWidget(self._splitter, 1)

        self._update_ui()

    def _update_ui(self):
        lang = self._get_current_lang()
        unlocked = self._km.is_unlocked()
        has_master = self._km.has_master()

        if not has_master:
            self.status_label.setText("")
            self.btn_unlock.setText(_t("设置主密码", lang))
            self.btn_unlock.show()
            self.btn_lock.hide()
            self.btn_remove_master.hide()
            self.btn_add.show()
            self.btn_test_all.show()
        elif unlocked:
            self.status_label.setText("")
            self.btn_unlock.hide()
            self.btn_lock.show()
            self.btn_remove_master.show()
            self.btn_add.show()
            self.btn_test_all.show()
        else:
            self.status_label.setText("")
            self.btn_unlock.setText(_t("解锁", lang))
            self.btn_unlock.show()
            self.btn_lock.hide()
            self.btn_remove_master.hide()
            self.btn_add.hide()
            self.btn_test_all.hide()

        self._rebuild_list()

    def _on_unlock(self):
        lang = self._get_current_lang()
        dlg = UnlockDialog(self, is_set=not self._km.has_master(), lang=lang)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        pwd = dlg.get_password()
        if not pwd:
            return
        if not self._km.has_master():
            confirm = dlg.get_confirm()
            if pwd != confirm:
                self._show_message(QMessageBox.Icon.Warning, _t("错误", lang), _t("两次密码不一致", lang))
                return
            self._km.set_master(pwd)
        else:
            if not self._km.unlock(pwd):
                self._show_message(QMessageBox.Icon.Warning, _t("错误", lang), _t("密码错误", lang))
                return
        self._update_ui()

    def _on_lock(self):
        self._km.lock()
        self._update_ui()

    def _on_remove_master(self):
        lang = self._get_current_lang()
        reply = QMessageBox.question(
            self, _t("确认移除密码", lang), _t("移除密码提示", lang),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._km.remove_master()
            self._update_ui()

    def _on_add(self):
        lang = self._get_current_lang()
        dlg = EntryDialog(self, is_dark=self._is_dark(), lang=lang)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        if not data["name"] or not data["value"]:
            self._show_message(QMessageBox.Icon.Warning, _t("错误", lang), _t("名称和密钥不能为空", lang))
            return
        self._km.add_entry(
            name=data["name"],
            entry_type=data["type"],
            value=data["value"],
            url=data["url"],
            url_anthropic=data.get("url_anthropic", ""),
            note=data["note"],
        )
        self._rebuild_list()

    def _rebuild_list(self):
        t = self._get_theme()
        lang = self._get_current_lang()

        # 清空左侧
        for i in reversed(range(self._llm_grid.count())):
            w = self._llm_grid.itemAt(i).widget()
            if w:
                w.deleteLater()
        # 清空右侧
        for i in reversed(range(self._secret_vbox.count())):
            w = self._secret_vbox.itemAt(i).widget()
            if w:
                w.deleteLater()

        if not self._km.is_unlocked():
            return

        entries = self._km.get_entries()
        llm_entries = [e for e in entries if e.get("type") == "llm"]
        secret_entries = [e for e in entries if e.get("type") != "llm"]

        # 左侧：大模型密钥卡片
        if not llm_entries:
            empty = QLabel(_t("暂无密钥", lang))
            empty.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent; padding:20px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._llm_grid.addWidget(empty, 0, 0, 1, 2)
        else:
            for idx, entry in enumerate(llm_entries):
                row_idx = idx // 2
                col_idx = idx % 2
                card = self._create_llm_card(entry, t, lang)
                self._llm_grid.addWidget(card, row_idx, col_idx)

        # 右侧：普通密钥（用 QFrame 行卡片）
        if not secret_entries:
            empty = QLabel(_t("暂无密钥", lang))
            empty.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent; padding:20px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._secret_vbox.addWidget(empty)
        else:
            for entry in secret_entries:
                row = self._create_secret_row(entry, t, lang)
                self._secret_vbox.addWidget(row)

    def _create_secret_row(self, entry, t, lang):
        """创建普通密钥单行卡片"""
        eid = entry["id"]
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {t.bg_panel};
                border: 1px solid {t.border_subtle};
                border-radius: 6px;
            }}
        """)
        card.setFixedHeight(44)
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda pos, eid=eid: self._show_secret_menu(pos, eid))
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(8)

        # 名称
        name_lbl = QLabel(entry.get("name", ""))
        name_lbl.setStyleSheet(f"font-size:13px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        row.addWidget(name_lbl, 1)

        # 掩码值
        value = entry.get("value", "")
        masked = "●" * min(len(value), 16)
        val_lbl = QLabel(masked)
        val_lbl.setStyleSheet(f"font-size:12px; color:{t.text_muted}; border:none; background:transparent;")
        row.addWidget(val_lbl, 1)

        # 复制按钮
        copy_btn = QPushButton(_t("复制", lang))
        copy_btn.setFixedSize(40, 24)
        copy_btn.setStyleSheet(f"""
            QPushButton {{ background: {t.bg_neutral_button}; color: {t.text_secondary};
                border: 1px solid {t.border_subtle}; border-radius: 4px; font-size: 10px; }}
            QPushButton:hover {{ background: {t.bg_active}; }}
        """)
        copy_btn.clicked.connect(lambda checked=False, eid=eid: self._copy_entry(eid))
        row.addWidget(copy_btn)

        # 编辑按钮
        edit_btn = QPushButton(_t("编辑", lang))
        edit_btn.setFixedSize(40, 24)
        edit_btn.setStyleSheet(f"""
            QPushButton {{ background: {t.bg_neutral_button}; color: {t.text_secondary};
                border: 1px solid {t.border_subtle}; border-radius: 4px; font-size: 10px; }}
            QPushButton:hover {{ background: {t.bg_active}; }}
        """)
        edit_btn.clicked.connect(lambda checked=False, eid=eid: self._edit_entry(eid))
        row.addWidget(edit_btn)

        # 删除按钮
        del_btn = QPushButton(_t("删除", lang))
        del_btn.setFixedSize(40, 24)
        del_btn.setStyleSheet(f"""
            QPushButton {{ background: {t.bg_neutral_button}; color: {t.text_secondary};
                border: 1px solid {t.border_subtle}; border-radius: 4px; font-size: 10px; }}
            QPushButton:hover {{ color: {t.error}; border-color: {t.error}; }}
        """)
        del_btn.clicked.connect(lambda checked=False, eid=eid: self._delete_entry(eid))
        row.addWidget(del_btn)

        return card

    def _show_secret_menu(self, pos, eid):
        """普通密钥右键菜单"""
        from PySide6.QtWidgets import QMenu
        lang = self._get_current_lang()
        card = self.sender()
        menu = QMenu(card)
        copy_act = menu.addAction(_t("复制", lang))
        edit_act = menu.addAction(_t("编辑", lang))
        del_act = menu.addAction(_t("删除", lang))
        action = menu.exec(card.mapToGlobal(pos))
        if action == copy_act:
            value = self._km.get_plain_value(eid)
            if value:
                QApplication.clipboard().setText(value)
        elif action == edit_act:
            self._edit_entry(eid)
        elif action == del_act:
            self._delete_entry(eid)

    def _create_llm_card(self, entry, t, lang):
        """创建大模型密钥卡片"""
        card = QFrame()
        card.setObjectName("key_card")
        card.setStyleSheet(f"""
            QFrame#key_card {{
                background: {t.bg_panel};
                border: 1px solid {t.border_subtle};
                border-radius: 10px;
                padding: 12px;
            }}
        """)
        card.setMinimumHeight(160)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(4)

        eid = entry["id"]

        # 顶部行：名称 + 删除 + 编辑
        top_row = QHBoxLayout()
        top_row.setSpacing(4)
        name_lbl = QLabel(entry.get("name", ""))
        name_lbl.setStyleSheet(f"font-size:16px; font-weight:700; color:{t.text_primary}; border:none; background:transparent;")
        name_lbl.setWordWrap(True)
        top_row.addWidget(name_lbl, 1)

        del_btn = QPushButton(f"[{_t('删除', lang)}]")
        del_btn.setStyleSheet(f"QPushButton {{ background:transparent; color:{t.text_muted}; border:none; font-size:12px; padding:0 4px; }} QPushButton:hover {{ color:{t.error}; }}")
        del_btn.clicked.connect(lambda checked=False, eid=eid: self._delete_entry(eid))
        top_row.addWidget(del_btn)

        edit_btn = QPushButton(f"[{_t('编辑', lang)}]")
        edit_btn.setStyleSheet(f"QPushButton {{ background:transparent; color:{t.text_muted}; border:none; font-size:12px; padding:0 4px; }} QPushButton:hover {{ color:{t.text_primary}; }}")
        edit_btn.clicked.connect(lambda checked=False, eid=eid: self._edit_entry(eid))
        top_row.addWidget(edit_btn)
        card_layout.addLayout(top_row)

        # 模型
        model_name = entry.get("note", "")
        if model_name:
            detail = QLabel(f"{_t('模型', lang)}: {model_name}")
            detail.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")
            card_layout.addWidget(detail)

        # 来源
        source = entry.get("url", "")
        if source:
            source_short = source.replace("https://", "").replace("http://", "")
            if len(source_short) > 30:
                source_short = source_short[:30] + "..."
            src_lbl = QLabel(f"{_t('来源', lang)}: {source_short}")
            src_lbl.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")
            card_layout.addWidget(src_lbl)

        # 延迟
        self._add_latency_label(card_layout, eid, t, lang)

        # 底部：协议标签 + 模型类型
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)
        url = entry.get("url", "")
        url_anthropic = entry.get("url_anthropic", "")
        if url:
            if "anthropic" in url.lower() or "claude" in url.lower():
                tag_lbl = QLabel("[Anthropic]")
            else:
                tag_lbl = QLabel("[OpenAI]")
            tag_lbl.setStyleSheet(f"font-size:12px; color:{t.text_muted}; border:none; background:transparent;")
            bottom_row.addWidget(tag_lbl)
        if url_anthropic:
            tag2 = QLabel("[Anthropic]")
            tag2.setStyleSheet(f"font-size:12px; color:{t.text_muted}; border:none; background:transparent;")
            bottom_row.addWidget(tag2)
        bottom_row.addStretch()

        if model_name:
            multimodal_kw = ["vision", "vl", "multi", "gpt-4o", "claude-3", "glm-4v"]
            if any(kw in model_name.lower() for kw in multimodal_kw):
                type_tag = QLabel(_t("多模态", lang))
                type_tag.setStyleSheet(f"font-size:11px; color:#10B981; border:1px solid #10B981; border-radius:4px; padding:2px 6px; background:transparent;")
            else:
                type_tag = QLabel(_t("文本", lang))
                type_tag.setStyleSheet(f"font-size:11px; color:{t.text_muted}; border:1px solid {t.border_subtle}; border-radius:4px; padding:2px 6px; background:transparent;")
            bottom_row.addWidget(type_tag)
        card_layout.addLayout(bottom_row)

        return card

    def _on_secret_context_menu(self, pos):
        """普通密钥右键菜单"""
        pass

    def _get_latency_color(self, ms: int) -> str:
        """根据延迟返回颜色"""
        if ms < 500:
            return "#10B981"  # 绿色
        elif ms < 1000:
            return "#F5A623"  # 黄色
        else:
            return "#F44336"  # 红色

    # ── Matrix Decode 动画 ──
    _MATRIX_CHARS = 'ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789'
    _MATRIX_TARGET = 'SNAPTRNS'

    def _start_matrix_decode(self, entry_id: int):
        """启动 Matrix Decode 动画"""
        lbl = self._latency_labels.get(entry_id)
        if not lbl:
            return
        # 停止旧动画
        self._stop_matrix_decode(entry_id)
        # 创建新动画线程
        worker = _MatrixAnimWorker(entry_id, lbl, self._MATRIX_CHARS, self._MATRIX_TARGET)
        worker.frame_ready.connect(self._on_matrix_frame)
        worker.finished.connect(self._on_matrix_anim_done)
        if not hasattr(self, '_matrix_workers'):
            self._matrix_workers = {}
        self._matrix_workers[str(entry_id)] = worker
        worker.start()

    def _stop_matrix_decode(self, entry_id: int):
        """停止 Matrix Decode 动画"""
        eid = str(entry_id)
        if hasattr(self, '_matrix_workers') and eid in self._matrix_workers:
            w = self._matrix_workers[eid]
            w.stop()
            w.wait(100)
            w.deleteLater()
            del self._matrix_workers[eid]

    def closeEvent(self, event):
        """页面关闭时清理所有矩阵动画线程"""
        if hasattr(self, '_matrix_workers'):
            for eid, w in list(self._matrix_workers.items()):
                w.stop()
                w.wait(100)
                w.deleteLater()
            self._matrix_workers.clear()
        super().closeEvent(event)

    def _on_matrix_frame(self, entry_id, html):
        """接收动画帧并更新UI"""
        lbl = self._latency_labels.get(int(entry_id))
        if lbl:
            lbl.setText(html)

    def _on_matrix_anim_done(self, entry_id):
        """动画自然结束"""
        if hasattr(self, '_matrix_workers') and entry_id in self._matrix_workers:
            del self._matrix_workers[entry_id]

    def _add_latency_label(self, layout, entry_id, t, lang):
        """添加延迟显示标签（用于测试后更新）"""
        row = QHBoxLayout()
        row.setSpacing(4)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        prefix = QLabel(f"{_t('延迟', lang)}:")
        prefix.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")
        prefix.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(prefix)
        value_lbl = QLabel(" --")
        value_lbl.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")
        value_lbl.setTextFormat(Qt.TextFormat.RichText)
        value_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        value_lbl.setFixedHeight(18)
        value_lbl.setObjectName(f"latency_{entry_id}")
        row.addWidget(value_lbl)
        row.addStretch()
        layout.addLayout(row)
        if not hasattr(self, '_latency_labels'):
            self._latency_labels = {}
        self._latency_labels[entry_id] = value_lbl

    def _copy_entry(self, entry_id: int):
        from PySide6.QtWidgets import QApplication
        value = self._km.get_plain_value(entry_id)
        if value:
            QApplication.clipboard().setText(value)

    def _delete_entry(self, entry_id: int):
        self._km.delete_entry(entry_id)
        self._rebuild_list()

    def _swap_entries(self, source_id: int, target_id: int):
        """交换两个密钥条目的顺序"""
        entries = self._km.get_entries()
        source_idx = next((i for i, e in enumerate(entries) if e["id"] == source_id), -1)
        target_idx = next((i for i, e in enumerate(entries) if e["id"] == target_id), -1)
        if source_idx >= 0 and target_idx >= 0:
            # 交换顺序
            entries[source_idx], entries[target_idx] = entries[target_idx], entries[source_idx]
            self._km._entries = entries
            self._km._save()
            self._rebuild_list()

    def _test_all_entries(self):
        """一键测试所有LLM密钥（异步逐个测试，参考 EchoBird）"""
        import threading

        entries = self._km.get_entries()
        llm_entries = [e for e in entries if e.get("type") == "llm"]
        if not llm_entries:
            return

        lang = self._get_current_lang()
        self.btn_test_all.setEnabled(False)
        self.btn_test_all.setText(_t("测试中", lang))

        # 为每个 LLM 条目启动 Matrix 动画
        for entry in llm_entries:
            self._start_matrix_decode(entry["id"])

        def _normalize_url(url: str) -> str:
            url = url.rstrip("/")
            if not url:
                return "https://open.bigmodel.cn/api/paas/v4/chat/completions"
            if url.endswith("/chat/completions"):
                return url
            return url + "/chat/completions"

        def do_test_all():
            import time
            import httpx

            client = httpx.Client(
                timeout=httpx.Timeout(10.0, connect=5.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
            try:
                for entry in llm_entries:
                    entry_id = entry["id"]
                    api_key = self._km.get_plain_value(entry_id)
                    api_url = entry.get("url", "")
                    model_id = entry.get("note", "") or "glm-4-flash"

                    if not api_key:
                        self._sig_test_one_done.emit(str(entry_id), 0, 0)
                        continue

                    t0 = time.perf_counter()
                    try:
                        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                        payload = {"model": model_id, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
                        resp = client.post(_normalize_url(api_url), json=payload, headers=headers)
                        elapsed_ms = int((time.perf_counter() - t0) * 1000)
                        status_code = resp.status_code
                    except Exception:
                        elapsed_ms = int((time.perf_counter() - t0) * 1000)
                        status_code = 0

                    self._sig_test_one_done.emit(str(entry_id), status_code, elapsed_ms)
            finally:
                client.close()
                # 全部完成信号：entry_id="__done__"
                self._sig_test_one_done.emit("__done__", 0, 0)

        threading.Thread(target=do_test_all, daemon=True).start()

    def _on_test_one_done(self, entry_id_str: str, status_code: int, elapsed_ms: int):
        """单个模型测试完成（主线程 slot）"""
        if entry_id_str == "__done__":
            # 全部测试完成
            lang = self._get_current_lang()
            self.btn_test_all.setEnabled(True)
            self.btn_test_all.setText(_t("测试速度", lang))
            return

        entry_id = int(entry_id_str)
        self._stop_matrix_decode(entry_id)
        lat_lbl = self._latency_labels.get(entry_id)
        if lat_lbl:
            if status_code == 200:
                lat_lbl.setText(f" {elapsed_ms}ms")
                lat_lbl.setStyleSheet(f"font-size:13px; color:{self._get_latency_color(elapsed_ms)}; border:none; background:transparent; font-weight:600;")
            elif status_code > 0:
                lat_lbl.setText(f" {status_code}")
                lat_lbl.setStyleSheet(f"font-size:13px; color:#F44336; border:none; background:transparent;")
            else:
                lat_lbl.setText(" --")
                lat_lbl.setStyleSheet(f"font-size:13px; color:#F44336; border:none; background:transparent;")

    def _edit_entry(self, entry_id: int):
        lang = self._get_current_lang()
        entry = None
        for e in self._km.get_entries():
            if e["id"] == entry_id:
                entry = e
                break
        if not entry:
            return
        dlg = EntryDialog(self, entry=entry, is_dark=self._is_dark(), lang=lang)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        if not data["name"] or not data["value"]:
            self._show_message(QMessageBox.Icon.Warning, _t("错误", lang), _t("名称和密钥不能为空", lang))
            return
        self._km.update_entry(
            entry_id,
            name=data["name"],
            type=data["type"],
            value=data["value"],
            url=data["url"],
            url_anthropic=data.get("url_anthropic", ""),
            note=data["note"],
        )
        self._rebuild_list()

    def apply_theme(self):
        t = self._get_theme()
        self.status_label.setStyleSheet(f"font-size:14px; color:{t.text_secondary}; border:none; background:transparent;")
        btn_css = f"""
            QPushButton {{
                background: {t.accent}; color: #FFFFFF;
                border: none; border-radius: 6px;
                padding: 6px 16px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {t.accent_hover}; }}
        """
        btn2_css = f"""
            QPushButton {{
                background: {t.bg_neutral_button}; color: {t.text_secondary};
                border: 1px solid {t.border_subtle}; border-radius: 6px;
                padding: 6px 16px; font-size: 12px;
            }}
            QPushButton:hover {{ background: {t.bg_active}; }}
        """
        self.btn_unlock.setStyleSheet(btn_css)
        self.btn_lock.setStyleSheet(btn2_css)
        self.btn_remove_master.setStyleSheet(btn2_css)
        self.btn_add.setStyleSheet(btn_css)
        self.btn_test_all.setStyleSheet(btn2_css)
        self._rebuild_list()

    def apply_language(self, lang: str):
        self._update_ui()
        # 更新标题
        if hasattr(self, '_left_title'):
            self._left_title.setText("🤖 " + _t("大模型密钥", lang))
        if hasattr(self, '_right_title'):
            self._right_title.setText("🔑 " + _t("普通密钥", lang))
