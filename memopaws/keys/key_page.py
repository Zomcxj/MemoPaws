"""密钥管理页面"""

import logging
import os
import json
import random
import time
from functools import partial
from PySide6.QtCore import QThread, Signal as pyqtSignal, QEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QComboBox, QScrollArea, QMessageBox,
    QDialog, QDialogButtonBox, QFormLayout, QApplication,
    QDateEdit, QGridLayout, QSizePolicy, QSplitter,
)
from PySide6.QtCore import Qt, QDate, QMimeData, QByteArray, QTimer
from PySide6.QtGui import QIcon, QDrag, QColor

from .key_manager import KeyManager
from .key_dialogs import UnlockDialog, EntryDialog, _t
from ..core.utils import normalize_api_url as _normalize_url, test_api_connection, load_svg_icon as _load_svg

logger = logging.getLogger(__name__)


def _run_llm_entry_tests(entries, get_plain_value, emit):
    """后台测试 LLM 密钥；无论网络层哪里失败，都必须通知 UI 收尾。"""
    def normalize_url(url: str) -> str:
        return _normalize_url(url)

    client = None
    try:
        import httpx

        client = httpx.Client(
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        for entry in entries:
            entry_id = entry["id"]
            api_key = get_plain_value(entry_id)
            api_url = entry.get("url", "")
            model_id = entry.get("note", "") or "glm-4-flash"

            if not api_key:
                emit(str(entry_id), 0, 0)
                continue

            t0 = time.perf_counter()
            try:
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {"model": model_id, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
                resp = client.post(normalize_url(api_url), json=payload, headers=headers)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                status_code = resp.status_code
            except Exception as exc:
                logger.warning("密钥测试失败: entry_id=%s, error=%s", entry_id, exc)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                status_code = 0

            emit(str(entry_id), status_code, elapsed_ms)
    except Exception as exc:
        logger.warning("密钥测试线程初始化失败: %s", exc)
        for entry in entries:
            emit(str(entry["id"]), 0, 0)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                logger.warning("密钥测试 HTTP 客户端关闭失败: %s", exc)
        emit("__done__", 0, 0)


class DraggableCard(QFrame):
    """可拖拽的密钥卡片"""
    def __init__(self, entry_id: int, parent=None):
        super().__init__(parent)
        self.entry_id = entry_id
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start_pos = None
        self._drag_hint = QLabel("拖动中", self)
        self._drag_hint.hide()
        self._drag_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drag_hint.setStyleSheet("background: rgba(0,0,0,0.35); color: white; border-radius: 8px; font-size: 12px;")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.DragEnter and hasattr(event, "mimeData") and event.mimeData().hasFormat("application/x-keycard"):
            self.dragEnterEvent(event)
            return True
        if event.type() == QEvent.Type.DragLeave:
            self.dragLeaveEvent(event)
            return True
        if event.type() == QEvent.Type.Drop and hasattr(event, "mimeData") and event.mimeData().hasFormat("application/x-keycard"):
            self.dropEvent(event)
            return True
        return super().eventFilter(obj, event)

    def _install_drag_forwarding(self):
        for child in self.findChildren(QWidget):
            if child is not self:
                child.setAcceptDrops(True)
                child.installEventFilter(self)

    def resizeEvent(self, event):
        self._drag_hint.setGeometry(self.rect())
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is not None:
            current_pos = event.position().toPoint()
            distance = (current_pos - self._drag_start_pos).manhattanLength()
            if distance > 10:
                pixmap = self.grab()
                for child in self.findChildren(QWidget):
                    if child is not self._drag_hint:
                        child.hide()
                self._drag_hint.show()
                drag = QDrag(self)
                mime_data = QMimeData()
                mime_data.setData("application/x-keycard", QByteArray(str(self.entry_id).encode()))
                drag.setMimeData(mime_data)
                drag.setPixmap(pixmap)
                drag.setHotSpot(current_pos)
                drag.exec(Qt.DropAction.MoveAction)
                self._drag_hint.hide()
                for child in self.findChildren(QWidget):
                    if child is not self._drag_hint:
                        child.show()
                self._drag_start_pos = None
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-keycard"):
            event.acceptProposedAction()
            original_style = self.property("original_style") or self.styleSheet() or ""
            accent = self.property("accent_color") or "#2563EB"
            highlighted = f"{original_style}\nDraggableCard, QFrame#key_card, QFrame {{ border: 2px solid {accent}; }}"
            self.setStyleSheet(highlighted)

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.property("original_style") or "")

    def dropEvent(self, event):
        try:
            source_id = int(event.mimeData().data("application/x-keycard").data().decode())
        except (UnicodeDecodeError, ValueError):
            self.setStyleSheet(self.property("original_style") or "")
            return
        if event.mimeData().hasFormat("application/x-keycard"):
            target_id = self.entry_id
            if source_id != target_id:
                # 通知父窗口交换顺序
                parent = self.parent()
                while parent and not hasattr(parent, '_swap_entries'):
                    parent = parent.parent()
                if parent:
                    parent._swap_entries(source_id, target_id)
            event.acceptProposedAction()
        self.setStyleSheet(self.property("original_style") or "")


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
        self._copy_generation = 0
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
        self._splitter.setOpaqueResize(True)

        # 左侧：大模型密钥卡片网格
        left_frame = QFrame()
        left_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
        self._llm_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
        right_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
        self._secret_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
        left_frame.setMinimumWidth(0)
        right_frame.setMinimumWidth(0)
        self._llm_container.setMinimumWidth(0)
        self._secret_container.setMinimumWidth(0)

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
            if not self._km.set_master(pwd):
                self._show_message(QMessageBox.Icon.Warning, _t("错误", lang), "保存密码失败")
                return
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
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(_t("确认移除密码", lang))
        box.setText(_t("移除密码提示", lang))
        remove_btn = box.addButton("Remove" if lang == "en" else "移除", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = box.addButton("Cancel" if lang == "en" else "取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.exec()
        if box.clickedButton() == remove_btn:
            if not self._km.remove_master():
                self._show_message(QMessageBox.Icon.Warning, _t("错误", lang), "移除密码失败")
                return
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
        if not self._km.add_entry(
            name=data["name"],
            entry_type=data["type"],
            value=data["value"],
            url=data["url"],
            url_anthropic=data.get("url_anthropic", ""),
            note=data["note"],
        ):
            self._show_message(QMessageBox.Icon.Warning, _t("错误", lang), "保存密钥失败")
            return
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
        llm_entries = sorted((e for e in entries if e.get("type") == "llm"), key=lambda e: (e.get("order", 0), e.get("created", "")))
        secret_entries = sorted((e for e in entries if e.get("type") != "llm"), key=lambda e: (e.get("order", 0), e.get("created", "")))

        # 左侧：大模型密钥卡片
        if not llm_entries:
            empty = QLabel(_t("暂无密钥", lang))
            empty.setProperty("i18n_key", "暂无密钥")
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
            empty.setProperty("i18n_key", "暂无密钥")
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
        card = DraggableCard(eid)
        card.setStyleSheet(f"""
            QFrame {{
                background: {t.bg_panel};
                border: 1px solid {t.border_subtle};
                border-radius: 6px;
            }}
        """)
        card.setProperty("original_style", card.styleSheet())
        card.setProperty("accent_color", t.accent)
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
        val_lbl.setStyleSheet(f"font-size:9px; letter-spacing: 2px; color:{t.text_muted}; border:none; background:transparent;")
        row.addWidget(val_lbl, 1)

        # 复制按钮
        copy_btn = QPushButton(_t("复制", lang))
        copy_btn.setProperty("i18n_key", "复制")
        copy_btn.setFixedSize(48, 28)
        copy_btn.setStyleSheet(f"""
            QPushButton {{ background: {t.bg_neutral_button}; color: {t.text_secondary};
                border: 1px solid {t.border_subtle}; border-radius: 4px; font-size: 12px; }}
            QPushButton:hover {{ background: {t.bg_active}; }}
        """)
        copy_btn.clicked.connect(lambda checked=False, eid=eid: self._copy_entry(eid))
        row.addWidget(copy_btn)

        # 编辑按钮
        edit_btn = QPushButton(_t("编辑", lang))
        edit_btn.setProperty("i18n_key", "编辑")
        edit_btn.setFixedSize(48, 28)
        edit_btn.setStyleSheet(f"""
            QPushButton {{ background: {t.bg_neutral_button}; color: {t.text_secondary};
                border: 1px solid {t.border_subtle}; border-radius: 4px; font-size: 12px; }}
            QPushButton:hover {{ background: {t.bg_active}; }}
        """)
        edit_btn.clicked.connect(lambda checked=False, eid=eid: self._edit_entry(eid))
        row.addWidget(edit_btn)

        # 删除按钮
        del_btn = QPushButton(_t("删除", lang))
        del_btn.setProperty("i18n_key", "删除")
        del_btn.setFixedSize(48, 28)
        del_btn.setStyleSheet(f"""
            QPushButton {{ background: {t.bg_neutral_button}; color: {t.text_secondary};
                border: 1px solid {t.border_subtle}; border-radius: 4px; font-size: 12px; }}
            QPushButton:hover {{ color: {t.error}; border-color: {t.error}; }}
        """)
        del_btn.clicked.connect(lambda checked=False, eid=eid: self._delete_entry(eid))
        row.addWidget(del_btn)

        card._install_drag_forwarding()
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
            self._copy_entry(eid)
        elif action == edit_act:
            self._edit_entry(eid)
        elif action == del_act:
            self._delete_entry(eid)

    def _create_llm_card(self, entry, t, lang):
        """创建大模型密钥卡片"""
        eid = entry["id"]
        card = DraggableCard(eid)
        card.setObjectName("key_card")
        card.setStyleSheet(f"""
            QFrame#key_card {{
                background: {t.bg_panel};
                border: 1px solid {t.border_subtle};
                border-radius: 10px;
                padding: 12px;
            }}
        """)
        card.setProperty("original_style", card.styleSheet())
        card.setProperty("accent_color", t.accent)
        card.setMinimumHeight(160)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(4)

        # 顶部行：名称 + 删除 + 编辑
        top_row = QHBoxLayout()
        top_row.setSpacing(4)
        name_lbl = QLabel(entry.get("name", ""))
        name_lbl.setStyleSheet(f"font-size:16px; font-weight:700; color:{t.text_primary}; border:none; background:transparent;")
        name_lbl.setWordWrap(True)
        top_row.addWidget(name_lbl, 1)

        del_btn = QPushButton(f"[{_t('删除', lang)}]")
        del_btn.setProperty("i18n_key", "删除")
        del_btn.setProperty("i18n_bracket", True)
        del_btn.setStyleSheet(f"QPushButton {{ background:transparent; color:{t.text_muted}; border:none; font-size:12px; padding:0 4px; }} QPushButton:hover {{ color:{t.error}; }}")
        del_btn.clicked.connect(lambda checked=False, eid=eid: self._delete_entry(eid))
        top_row.addWidget(del_btn)

        edit_btn = QPushButton(f"[{_t('编辑', lang)}]")
        edit_btn.setProperty("i18n_key", "编辑")
        edit_btn.setProperty("i18n_bracket", True)
        edit_btn.setStyleSheet(f"QPushButton {{ background:transparent; color:{t.text_muted}; border:none; font-size:12px; padding:0 4px; }} QPushButton:hover {{ color:{t.text_primary}; }}")
        edit_btn.clicked.connect(lambda checked=False, eid=eid: self._edit_entry(eid))
        top_row.addWidget(edit_btn)
        card_layout.addLayout(top_row)

        # 模型
        model_name = entry.get("note", "")
        if model_name:
            row_m = QHBoxLayout()
            row_m.setSpacing(2)
            row_m.setContentsMargins(0, 0, 0, 0)
            prefix_m = QLabel(f"{_t('模型', lang)}:")
            prefix_m.setProperty("i18n_key", "模型")
            prefix_m.setProperty("i18n_suffix", ":")
            prefix_m.setFixedWidth(72 if lang == "en" else 45)
            prefix_m.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")
            row_m.addWidget(prefix_m)
            val_m = QLabel(model_name)
            val_m.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")
            row_m.addWidget(val_m, 1)
            card_layout.addLayout(row_m)

        # 来源
        source = entry.get("url", "")
        if source:
            source_short = source.replace("https://", "").replace("http://", "")
            if len(source_short) > 30:
                source_short = source_short[:30] + "..."
            row_s = QHBoxLayout()
            row_s.setSpacing(2)
            row_s.setContentsMargins(0, 0, 0, 0)
            prefix_s = QLabel(f"{_t('来源', lang)}:")
            prefix_s.setProperty("i18n_key", "来源")
            prefix_s.setProperty("i18n_suffix", ":")
            prefix_s.setFixedWidth(72 if lang == "en" else 45)
            prefix_s.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")
            row_s.addWidget(prefix_s)
            val_s = QLabel(source_short)
            val_s.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")
            row_s.addWidget(val_s, 1)
            card_layout.addLayout(row_s)

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
                type_tag.setProperty("i18n_key", "多模态")
                type_tag.setStyleSheet(f"font-size:11px; color:#10B981; border:1px solid #10B981; border-radius:4px; padding:2px 6px; background:transparent;")
            else:
                type_tag = QLabel(_t("文本", lang))
                type_tag.setProperty("i18n_key", "文本")
                type_tag.setStyleSheet(f"font-size:11px; color:{t.text_muted}; border:1px solid {t.border_subtle}; border-radius:4px; padding:2px 6px; background:transparent;")
            bottom_row.addWidget(type_tag)
        card_layout.addLayout(bottom_row)

        card._install_drag_forwarding()
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
        row.setSpacing(2)
        row.setContentsMargins(0, 0, 0, 0)
        prefix = QLabel(f"{_t('延迟', lang)}:")
        prefix.setProperty("i18n_key", "延迟")
        prefix.setProperty("i18n_suffix", ":")
        prefix.setFixedWidth(72 if lang == "en" else 45)
        prefix.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")
        row.addWidget(prefix)
        value_lbl = QLabel("--")
        value_lbl.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")
        row.addWidget(value_lbl, 1)
        layout.addLayout(row)
        if not hasattr(self, '_latency_labels'):
            self._latency_labels = {}
        self._latency_labels[entry_id] = value_lbl

    def _copy_entry(self, entry_id: int):
        from PySide6.QtWidgets import QApplication
        value = self._km.get_plain_value(entry_id)
        if value:
            clipboard = QApplication.clipboard()
            clipboard.setText(value)
            self._copy_generation += 1
            generation = self._copy_generation
            changed = [False]

            def _invalidate_cleanup():
                changed[0] = True

            clipboard.dataChanged.connect(_invalidate_cleanup)

            def _clear_if_unchanged(expected=value, expected_generation=generation):
                clipboard.dataChanged.disconnect(_invalidate_cleanup)
                if not changed[0] and self._copy_generation == expected_generation and clipboard.text() == expected:
                    clipboard.clear()

            # ponytail: 30 秒后仅清理本次复制，后续任意剪贴板写入都会使清理失效。
            QTimer.singleShot(30000, _clear_if_unchanged)

    def _delete_entry(self, entry_id: int):
        if not self._km.delete_entry(entry_id):
            self._show_message(QMessageBox.Icon.Warning, _t("错误", self._get_current_lang()), "保存密钥失败")
            return
        self._rebuild_list()

    def _swap_entries(self, source_id: int, target_id: int):
        """仅在同类型分区内交换两个密钥条目的顺序。"""
        entries = self._km.get_entries()
        source_idx = next((i for i, e in enumerate(entries) if e["id"] == source_id), -1)
        target_idx = next((i for i, e in enumerate(entries) if e["id"] == target_id), -1)
        if source_idx >= 0 and target_idx >= 0:
            if entries[source_idx].get("type") != entries[target_idx].get("type"):
                return
            source_order = entries[source_idx].get("order", source_idx)
            target_order = entries[target_idx].get("order", target_idx)
            previous_entries = [dict(entry) for entry in entries]
            entries[source_idx]["order"] = target_order
            entries[target_idx]["order"] = source_order
            if not self._km._save():
                self._km._entries = previous_entries
                self._show_message(QMessageBox.Icon.Warning, _t("错误", self._get_current_lang()), "保存密钥失败")
                return
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

        def do_test_all():
            _run_llm_entry_tests(llm_entries, self._km.get_plain_value, self._sig_test_one_done.emit)

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
                lat_lbl.setText(f"{elapsed_ms}ms")
                lat_lbl.setToolTip("")
                lat_lbl.setStyleSheet(f"font-size:13px; color:{self._get_latency_color(elapsed_ms)}; border:none; background:transparent;")
            elif status_code > 0:
                lang = self._get_current_lang()
                status_text = {
                    401: "Invalid Key" if lang == "en" else "密钥无效",
                    403: "Forbidden" if lang == "en" else "无权限",
                    429: "Rate Limited" if lang == "en" else "被限流",
                    503: "Unavailable" if lang == "en" else "服务不可用",
                }.get(status_code, str(status_code))
                lat_lbl.setText(status_text)
                lat_lbl.setToolTip(f"HTTP {status_code}")
                lat_lbl.setStyleSheet(f"font-size:13px; color:#F44336; border:none; background:transparent;")
            else:
                lat_lbl.setText("--")
                lat_lbl.setToolTip("")
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
        if not self._km.update_entry(
            entry_id,
            name=data["name"],
            type=data["type"],
            value=data["value"],
            url=data["url"],
            url_anthropic=data.get("url_anthropic", ""),
            note=data["note"],
        ):
            self._show_message(QMessageBox.Icon.Warning, _t("错误", lang), "保存密钥失败")
            return
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
        has_master = self._km.has_master()
        unlocked = self._km.is_unlocked()
        self.btn_unlock.setText(_t("设置主密码", lang) if not has_master else _t("解锁", lang))
        self.btn_unlock.setVisible((not has_master) or (not unlocked))
        self.btn_lock.setVisible(has_master and unlocked)
        self.btn_remove_master.setVisible(has_master and unlocked)
        self.btn_add.setVisible((not has_master) or unlocked)
        self.btn_test_all.setVisible((not has_master) or unlocked)
        self.btn_lock.setText(_t("锁定", lang))
        self.btn_remove_master.setText(_t("移除主密码", lang))
        self.btn_add.setText(_t("添加密钥按钮", lang))
        if self.btn_test_all.isEnabled():
            self.btn_test_all.setText(_t("测试速度", lang))
        else:
            self.btn_test_all.setText(_t("测试中", lang))
        # 更新标题
        if hasattr(self, '_left_title'):
            self._left_title.setText("🤖 " + _t("大模型密钥", lang))
        if hasattr(self, '_right_title'):
            self._right_title.setText("🔑 " + _t("普通密钥", lang))
        self._update_i18n_texts(lang)

    def _update_i18n_texts(self, lang: str):
        """更新密钥卡片内部文案，不重建卡片避免频繁切语言卡退。"""
        for widget in self.findChildren(QWidget):
            key = widget.property("i18n_key")
            if not key or not hasattr(widget, "setText"):
                continue
            text = _t(str(key), lang)
            if widget.property("i18n_bracket"):
                text = f"[{text}]"
            suffix = widget.property("i18n_suffix")
            if suffix:
                text = f"{text}{suffix}"
                if hasattr(widget, "setFixedWidth"):
                    widget.setFixedWidth(72 if lang == "en" else 45)
            widget.setText(text)
