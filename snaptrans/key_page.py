"""密钥管理页面"""

import logging
import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QComboBox, QScrollArea, QMessageBox,
    QDialog, QDialogButtonBox, QFormLayout, QApplication,
    QDateEdit, QGridLayout, QSizePolicy, QSplitter,
)
from PySide6.QtCore import Qt, QDate, QMimeData, QByteArray
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


class KeyPage(QWidget):
    """密钥管理页面"""

    def __init__(self, parent, *, get_theme, is_dark, show_message, get_icons_dir, get_icon_clr, get_current_lang):
        super().__init__(parent)

        title_row.addStretch()

        layout.addLayout(title_row)

        # 名称
        name_lbl = QLabel(_t("名称", lang))
        name_lbl.setStyleSheet(f"font-size:12px; color:{t.text_secondary}; border:none; background:transparent;")
        layout.addWidget(name_lbl)
        self.name_input = QLineEdit(entry.get("name", "") if entry else "")
        self.name_input.setPlaceholderText(_t("名称", lang))
        self.name_input.setFixedHeight(36)
        self.name_input.setStyleSheet(f"""
            QLineEdit {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }}
        """)
        layout.addWidget(self.name_input)

        # 类型选择
        self.type_combo = QComboBox()
        self.type_combo.addItems([_t("大模型密钥", lang), _t("普通密钥", lang)])
        if entry:
            self.type_combo.setCurrentText(_t("大模型密钥", lang) if entry.get("type") == "llm" else _t("普通密钥", lang))
        self.type_combo.setFixedHeight(36)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self.type_combo.setStyleSheet(f"""
            QComboBox {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox::down-arrow {{ image: none; }}
        """)
        layout.addWidget(self.type_combo)

        # OpenAI 地址
        self.url_openai_label = QLabel("OpenAI " + _t("地址", lang))
        self.url_openai_label.setStyleSheet(f"font-size:12px; color:{t.text_secondary}; border:none; background:transparent;")
        layout.addWidget(self.url_openai_label)
        self.url_input = QLineEdit(entry.get("url", "") if entry else "")
        self.url_input.setPlaceholderText("https://api.openai.com/v1/chat/completions")
        self.url_input.setFixedHeight(36)
        self.url_input.setStyleSheet(f"""
            QLineEdit {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }}
        """)
        layout.addWidget(self.url_input)

        # Anthropic 地址（LLM密钥可见）
        self.url_anthropic_label = QLabel("Anthropic " + _t("地址", lang))
        self.url_anthropic_label.setStyleSheet(f"font-size:12px; color:{t.text_secondary}; border:none; background:transparent;")
        layout.addWidget(self.url_anthropic_label)
        self.url_anthropic_input = QLineEdit(entry.get("url_anthropic", "") if entry else "")
        self.url_anthropic_input.setPlaceholderText("https://api.anthropic.com/v1/messages")
        self.url_anthropic_input.setFixedHeight(36)
        self.url_anthropic_input.setStyleSheet(f"""
            QLineEdit {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }}
        """)
        layout.addWidget(self.url_anthropic_input)

        # 模型 ID
        self.model_id_label = QLabel(_t("模型ID", lang))
        self.model_id_label.setStyleSheet(f"font-size:12px; color:{t.text_secondary}; border:none; background:transparent;")
        layout.addWidget(self.model_id_label)
        self.model_id_input = QLineEdit(entry.get("note", "") if entry else "")
        self.model_id_input.setPlaceholderText("e.g. Qwen/Qwen-Coder")
        self.model_id_input.setFixedHeight(36)
        self.model_id_input.setStyleSheet(f"""
            QLineEdit {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }}
        """)
        layout.addWidget(self.model_id_input)

        # API 密钥
        key_lbl = QLabel(_t("API 密钥", lang))
        key_lbl.setStyleSheet(f"font-size:12px; color:{t.text_secondary}; border:none; background:transparent;")
        layout.addWidget(key_lbl)
        key_row = QHBoxLayout()
        key_row.setSpacing(4)
        self.value_input = QLineEdit(entry.get("value", "") if entry else "")
        self.value_input.setPlaceholderText(_t("密钥值", lang))
        self.value_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.value_input.setFixedHeight(36)
        self.value_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.value_input.setStyleSheet(f"""
            QLineEdit {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }}
        """)
        key_row.addWidget(self.value_input)

        copy_key_btn = QPushButton("📋")
        copy_key_btn.setFixedSize(28, 28)
        copy_key_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {t.border_subtle};
                border-radius: 4px;
                font-size: 11px;
                padding: 0px;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }}
            QPushButton:hover {{ background: {t.bg_active}; }}
        """)
        copy_key_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.value_input.text()))
        key_row.addWidget(copy_key_btn)

        self.eye_btn = QPushButton("👁")
        self.eye_btn.setFixedSize(28, 28)
        self.eye_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {t.border_subtle};
                border-radius: 4px;
                font-size: 8px;
                padding: 0px;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }}
            QPushButton:hover {{ background: {t.bg_active}; }}
        """)
        self.eye_btn.clicked.connect(self._toggle_eye)
        key_row.addWidget(self.eye_btn)

        layout.addLayout(key_row)

        layout.addStretch()

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        cancel_btn = QPushButton(_t("取消", lang))
        cancel_btn.setFixedSize(80, 36)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {t.text_secondary}; border: 1px solid {t.border_subtle}; border-radius: 6px; font-size: 12px; }}
            QPushButton:hover {{ background: {t.bg_active}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton(_t("保存", lang))
        save_btn.setFixedSize(80, 36)
        save_btn.setStyleSheet(f"""
            QPushButton {{ background: {t.accent}; color: #FFFFFF; border: none; border-radius: 6px; font-size: 12px; font-weight: 600; }}
            QPushButton:hover {{ background: {t.accent_hover}; }}
        """)
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

        self._on_type_changed(self.type_combo.currentText())

    def _toggle_eye(self):
        if self.value_input.echoMode() == QLineEdit.EchoMode.Password:
            self.value_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.eye_btn.setText("🔒")
        else:
            self.value_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.eye_btn.setText("👁")

    def _on_type_changed(self, text):
        is_llm = text == _t("大模型密钥", self._lang)
        self.url_input.setVisible(is_llm)
        self.url_openai_label.setVisible(is_llm)
        self.url_anthropic_input.setVisible(is_llm)
        self.url_anthropic_label.setVisible(is_llm)
        self.model_id_input.setVisible(is_llm)
        self.model_id_label.setVisible(is_llm)

    def _normalize_url(self, url: str) -> str:
        url = url.rstrip("/")
        if not url:
            return "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        if url.endswith("/chat/completions"):
            return url
        return url + "/chat/completions"

    def get_data(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
            "type": "llm" if self.type_combo.currentText() == _t("大模型密钥", self._lang) else "secret",
            "value": self.value_input.text().strip(),
            "url": self.url_input.text().strip(),
            "url_anthropic": self.url_anthropic_input.text().strip(),
            "note": self.model_id_input.text().strip(),
        }


class KeyPage(QWidget):
    """密钥管理页面"""

    def __init__(self, parent, *, get_theme, is_dark, show_message, get_icons_dir, get_icon_clr, get_current_lang):
        super().__init__(parent)
        self._get_theme = get_theme
        self._is_dark = is_dark
        self._show_message = show_message
        self._get_icons_dir = get_icons_dir
        self._get_icon_clr = get_icon_clr
        self._get_current_lang = get_current_lang
        self._km = KeyManager()
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

    def _add_latency_label(self, layout, entry_id, t, lang):
        """添加延迟显示标签（用于测试后更新）"""
        row = QHBoxLayout()
        row.setSpacing(0)
        # "延迟:" 固定颜色
        prefix = QLabel(f"{_t('延迟', lang)}:")
        prefix.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")
        row.addWidget(prefix)
        # 数字部分 可变颜色
        value_lbl = QLabel(" --")
        value_lbl.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")
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

    def _test_entry(self, entry_id: int, btn: QPushButton):
        """从卡片一键测试大模型密钥连接"""
        import time
        import httpx

        entry = None
        for e in self._km.get_entries():
            if e["id"] == entry_id:
                entry = e
                break
        if not entry:
            return

        api_key = self._km.get_plain_value(entry_id)
        api_url = entry.get("url", "")
        if not api_key:
            return

        # 使用条目中存储的模型ID，默认 glm-4-flash
        model_id = entry.get("note", "") or "glm-4-flash"

        def _normalize_url(url: str) -> str:
            url = url.rstrip("/")
            if not url:
                return "https://open.bigmodel.cn/api/paas/v4/chat/completions"
            if url.endswith("/chat/completions"):
                return url
            return url + "/chat/completions"

        # 更新延迟标签为"测试中..."
        lat_lbl = self._latency_labels.get(entry_id)
        if lat_lbl:
            lang = self._get_current_lang()
            t = self._get_theme()
            lat_lbl.setText(" ...")
            lat_lbl.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")

        btn.setEnabled(False)
        btn.setText("...")
        QApplication.processEvents()

        # 使用持久连接池，减少建连开销
        if not hasattr(self, '_http_client'):
            self._http_client = httpx.Client(
                timeout=httpx.Timeout(10.0, connect=5.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )

        t0 = time.perf_counter()
        try:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            # 只测 1 token，减少响应时间
            payload = {"model": model_id, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}

            resp = self._http_client.post(_normalize_url(api_url), json=payload, headers=headers)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)

            elapsed_ms = int((time.perf_counter() - t0) * 1000)

            if resp.status_code == 200:
                btn.setText(f"✓ {elapsed_ms}ms")
                btn.setStyleSheet("""
                    QPushButton { background: rgba(16,185,129,0.15); color: #10B981; border: 1px solid #10B981; border-radius: 4px; font-size: 12px; font-weight:600; padding: 0 12px; }
                """)
                if lat_lbl:
                    lat_lbl.setText(f" {elapsed_ms}ms")
                    lat_lbl.setStyleSheet(f"font-size:13px; color:{self._get_latency_color(elapsed_ms)}; border:none; background:transparent; font-weight:600;")
            else:
                btn.setText(f"✗ {resp.status_code}")
                btn.setStyleSheet("""
                    QPushButton { background: rgba(244,67,54,0.15); color: #F44336; border: 1px solid #F44336; border-radius: 4px; font-size: 12px; font-weight:600; padding: 0 12px; }
                """)
                if lat_lbl:
                    lat_lbl.setText(f" {elapsed_ms}ms")
                    lat_lbl.setStyleSheet(f"font-size:13px; color:{self._get_latency_color(elapsed_ms)}; border:none; background:transparent;")
        except (httpx.TimeoutException, httpx.ConnectError, Exception) as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            btn.setText(f"✗ {elapsed_ms}ms")
            btn.setStyleSheet("""
                QPushButton { background: rgba(244,67,54,0.15); color: #F44336; border: 1px solid #F44336; border-radius: 4px; font-size: 12px; font-weight:600; padding: 0 12px; }
            """)
            if lat_lbl:
                lat_lbl.setText(f" {elapsed_ms}ms")
                lat_lbl.setStyleSheet(f"font-size:13px; color:{self._get_latency_color(elapsed_ms)}; border:none; background:transparent;")
        finally:
            # 2 秒后恢复按钮
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self._reset_test_btn(btn))

    def _reset_test_btn(self, btn: QPushButton):
        lang = self._get_current_lang()
        t = self._get_theme()
        btn.setEnabled(True)
        btn.setText(_t("测试", lang))
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.bg_neutral_button}; color: {t.text_secondary};
                border: 1px solid {t.border_subtle}; border-radius: 4px;
                font-size: 12px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: {t.bg_active}; }}
        """)

    def _test_all_entries(self):
        """一键测试所有LLM密钥"""
        import time
        import httpx

        lang = self._get_current_lang()
        t = self._get_theme()
        entries = self._km.get_entries()
        llm_entries = [e for e in entries if e.get("type") == "llm"]
        if not llm_entries:
            return

        self.btn_test_all.setEnabled(False)
        self.btn_test_all.setText(_t("测试中", lang))
        QApplication.processEvents()

        # 使用持久连接池
        if not hasattr(self, '_http_client'):
            self._http_client = httpx.Client(
                timeout=httpx.Timeout(10.0, connect=5.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )

        def _normalize_url(url: str) -> str:
            url = url.rstrip("/")
            if not url:
                return "https://open.bigmodel.cn/api/paas/v4/chat/completions"
            if url.endswith("/chat/completions"):
                return url
            return url + "/chat/completions"

        for entry in llm_entries:
            entry_id = entry["id"]
            api_key = self._km.get_plain_value(entry_id)
            api_url = entry.get("url", "")
            if not api_key:
                continue

            model_id = entry.get("note", "") or "glm-4-flash"

            lat_lbl = self._latency_labels.get(entry_id)
            if lat_lbl:
                lat_lbl.setText(" ...")
                lat_lbl.setStyleSheet(f"font-size:13px; color:{t.text_muted}; border:none; background:transparent;")

            try:
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {"model": model_id, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}

                t0 = time.perf_counter()
                resp = self._http_client.post(_normalize_url(api_url), json=payload, headers=headers)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)

                if lat_lbl:
                    if resp.status_code == 200:
                        lat_lbl.setText(f" {elapsed_ms}ms")
                        lat_lbl.setStyleSheet(f"font-size:13px; color:{self._get_latency_color(elapsed_ms)}; border:none; background:transparent; font-weight:600;")
                    else:
                        lat_lbl.setText(f" {resp.status_code}")
                        lat_lbl.setStyleSheet(f"font-size:13px; color:{self._get_latency_color(elapsed_ms)}; border:none; background:transparent;")
            except Exception:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                if lat_lbl:
                    lat_lbl.setText(f" {elapsed_ms}ms")
                    lat_lbl.setStyleSheet(f"font-size:13px; color:{self._get_latency_color(elapsed_ms)}; border:none; background:transparent;")

        self.btn_test_all.setEnabled(True)
        self.btn_test_all.setText(_t("测试速度", lang))

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
