"""密钥管理对话框"""

import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QApplication, QDateEdit,
)
from PySide6.QtCore import Qt, QDate

# ── 中英文文本映射 ──
_T = {
    "设置主密码": {"en": "Set Master Password", "zh": "设置主密码"},
    "解锁密钥管理": {"en": "Unlock Key Manager", "zh": "解锁密钥管理"},
    "输入主密码": {"en": "Enter master password", "zh": "输入主密码"},
    "输入主密码解锁": {"en": "Enter master password to unlock", "zh": "输入主密码解锁"},
    "确认主密码": {"en": "Confirm master password", "zh": "确认主密码"},
    "编辑密钥": {"en": "Edit Key", "zh": "编辑密钥"},
    "添加密钥": {"en": "Add Key", "zh": "添加密钥"},
    "名称": {"en": "Name", "zh": "名称"},
    "大模型密钥": {"en": "LLM Key", "zh": "大模型密钥"},
    "普通密钥": {"en": "Secret Key", "zh": "普通密钥"},
    "密钥值": {"en": "Key value", "zh": "密钥值"},
    "地址": {"en": "URL", "zh": "地址"},
    "模型ID": {"en": "Model ID", "zh": "模型ID"},
    "API 密钥": {"en": "API Key", "zh": "API 密钥"},
    "编辑模型配置": {"en": "Edit Model Config", "zh": "编辑模型配置"},
    "取消": {"en": "Cancel", "zh": "取消"},
    "保存": {"en": "Save", "zh": "保存"},
    "错误": {"en": "Error", "zh": "错误"},
    "两次密码不一致": {"en": "Passwords do not match", "zh": "两次密码不一致"},
    "密码错误": {"en": "Wrong password", "zh": "密码错误"},
    "名称和密钥不能为空": {"en": "Name and key cannot be empty", "zh": "名称和密钥不能为空"},
    "解锁": {"en": "Unlock", "zh": "解锁"},
    "锁定": {"en": "Lock", "zh": "锁定"},
    "移除主密码": {"en": "Remove Master Password", "zh": "移除主密码"},
    "添加密钥按钮": {"en": "Add Key", "zh": "添加密钥"},
    "测试速度": {"en": "Test Speed", "zh": "测试速度"},
    "测试中": {"en": "Testing...", "zh": "测试中"},
    "暂无密钥": {"en": "No keys", "zh": "暂无密钥"},
    "复制": {"en": "Copy", "zh": "复制"},
    "编辑": {"en": "Edit", "zh": "编辑"},
    "删除": {"en": "Delete", "zh": "删除"},
    "模型": {"en": "Model", "zh": "模型"},
    "来源": {"en": "Source", "zh": "来源"},
    "多模态": {"en": "Multimodal", "zh": "多模态"},
    "文本": {"en": "Text", "zh": "文本"},
    "延迟": {"en": "Latency", "zh": "延迟"},
    "确认移除密码": {"en": "Confirm remove password", "zh": "确认移除密码"},
    "移除密码提示": {"en": "Are you sure to remove the master password?", "zh": "确定要移除主密码吗？"},
    "测试": {"en": "Test", "zh": "测试"},
    "备注": {"en": "Note", "zh": "备注"},
    "备注可选": {"en": "Note (optional)", "zh": "备注可选"},
}


def _t(key: str, lang: str = "zh") -> str:
    """获取翻译文本"""
    return _T.get(key, {}).get(lang, key)


class UnlockDialog(QDialog):
    """主密码输入对话框"""
    def __init__(self, parent, is_set=False, lang="zh"):
        super().__init__(parent)
        self._lang = lang
        self.setWindowTitle(_t("设置主密码", lang) if is_set else _t("解锁密钥管理", lang))
        self.setFixedSize(320, 160)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setPlaceholderText(_t("输入主密码", lang) if is_set else _t("输入主密码解锁", lang))
        self.pwd_input.setFixedHeight(32)
        layout.addWidget(self.pwd_input)

        if is_set:
            self.pwd2 = QLineEdit()
            self.pwd2.setEchoMode(QLineEdit.EchoMode.Password)
            self.pwd2.setPlaceholderText(_t("确认主密码", lang))
            self.pwd2.setFixedHeight(32)
            layout.addWidget(self.pwd2)
        else:
            self.pwd2 = None

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_password(self):
        return self.pwd_input.text().strip()

    def get_confirm(self):
        return self.pwd2.text().strip() if self.pwd2 else ""


class EntryDialog(QDialog):
    """添加/编辑密钥条目对话框"""
    def __init__(self, parent, entry=None, is_dark=True, lang="zh"):
        super().__init__(parent)
        self._lang = lang
        self._entry = entry
        self.setWindowTitle(_t("编辑密钥", lang) if entry else _t("添加密钥", lang))
        self.setFixedSize(420, 500)

        from ..core.themes import DARK, LIGHT
        t = DARK if is_dark else LIGHT

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 16, 20, 16)

        # 名称
        name_lbl = QLabel(_t("名称", lang))
        name_lbl.setStyleSheet(f"font-size:12px; color:{t.text_secondary}; border:none; background:transparent;")
        layout.addWidget(name_lbl)
        self.name_input = QLineEdit(entry.get("name", "") if entry else "")
        self.name_input.setPlaceholderText(_t("名称", lang))
        self.name_input.setFixedHeight(36)
        self.name_input.setStyleSheet(f"QLineEdit {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }}")
        layout.addWidget(self.name_input)

        # 类型选择
        self.type_combo = QComboBox()
        self.type_combo.addItems([_t("大模型密钥", lang), _t("普通密钥", lang)])
        if entry:
            self.type_combo.setCurrentText(_t("大模型密钥", lang) if entry.get("type") == "llm" else _t("普通密钥", lang))
        self.type_combo.setFixedHeight(36)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self.type_combo.setStyleSheet(f"QComboBox {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }} QComboBox::drop-down {{ border: none; }} QComboBox::down-arrow {{ image: none; }}")
        layout.addWidget(self.type_combo)

        # OpenAI 地址
        self.url_openai_label = QLabel("OpenAI " + _t("地址", lang))
        self.url_openai_label.setStyleSheet(f"font-size:12px; color:{t.text_secondary}; border:none; background:transparent;")
        layout.addWidget(self.url_openai_label)
        self.url_input = QLineEdit(entry.get("url", "") if entry else "")
        self.url_input.setPlaceholderText("https://api.openai.com/v1/chat/completions")
        self.url_input.setFixedHeight(36)
        self.url_input.setStyleSheet(f"QLineEdit {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }}")
        layout.addWidget(self.url_input)

        # Anthropic 地址
        self.url_anthropic_label = QLabel("Anthropic " + _t("地址", lang))
        self.url_anthropic_label.setStyleSheet(f"font-size:12px; color:{t.text_secondary}; border:none; background:transparent;")
        layout.addWidget(self.url_anthropic_label)
        self.url_anthropic_input = QLineEdit(entry.get("url_anthropic", "") if entry else "")
        self.url_anthropic_input.setPlaceholderText("https://api.anthropic.com/v1/messages")
        self.url_anthropic_input.setFixedHeight(36)
        self.url_anthropic_input.setStyleSheet(f"QLineEdit {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }}")
        layout.addWidget(self.url_anthropic_input)

        # 模型 ID（LLM密钥）
        self.model_id_label = QLabel(_t("模型ID", lang))
        self.model_id_label.setStyleSheet(f"font-size:12px; color:{t.text_secondary}; border:none; background:transparent;")
        layout.addWidget(self.model_id_label)
        self.model_id_input = QLineEdit(entry.get("note", "") if entry else "")
        self.model_id_input.setPlaceholderText("e.g. Qwen/Qwen-Coder")
        self.model_id_input.setFixedHeight(36)
        self.model_id_input.setStyleSheet(f"QLineEdit {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }}")
        layout.addWidget(self.model_id_input)

        # 备注（普通密钥）
        self.note_label = QLabel(_t("备注", lang))
        self.note_label.setStyleSheet(f"font-size:12px; color:{t.text_secondary}; border:none; background:transparent;")
        layout.addWidget(self.note_label)
        self.note_input = QLineEdit(entry.get("note", "") if entry else "")
        self.note_input.setPlaceholderText(_t("备注可选", lang))
        self.note_input.setFixedHeight(36)
        self.note_input.setStyleSheet(f"QLineEdit {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }}")
        layout.addWidget(self.note_input)

        # API 密钥
        key_lbl = QLabel(_t("API 密钥", lang))
        key_lbl.setStyleSheet(f"font-size:12px; color:{t.text_secondary}; border:none; background:transparent;")
        layout.addWidget(key_lbl)

        # 密钥输入框 + 复制 + 眼睛（8:1:1）
        key_container = QWidget()
        key_row = QHBoxLayout(key_container)
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.setSpacing(2)

        self.value_input = QLineEdit(entry.get("value", "") if entry else "")
        self.value_input.setPlaceholderText(_t("密钥值", lang))
        self.value_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.value_input.setFixedHeight(36)
        self.value_input.setStyleSheet(f"QLineEdit {{ background: {t.bg_input}; color: {t.text_primary}; border: 1px solid {t.border_subtle}; border-radius: 6px; padding: 4px 8px; font-size: 9px; letter-spacing: 2px; }}")
        key_row.addWidget(self.value_input, 8)

        copy_btn = QPushButton("📋")
        copy_btn.setFixedHeight(36)
        copy_btn.setStyleSheet(f"QPushButton {{ background: transparent; border: 1px solid {t.border_subtle}; border-radius: 4px; font-size: 10px; min-width:8px; max-width:8px; }} QPushButton:hover {{ background: {t.bg_active}; }}")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.value_input.text()))
        key_row.addWidget(copy_btn, 1)

        self.eye_btn = QPushButton("👁")
        self.eye_btn.setFixedHeight(36)
        self.eye_btn.setStyleSheet(f"QPushButton {{ background: transparent; border: 1px solid {t.border_subtle}; border-radius: 4px; font-size: 7px; min-width:8px; max-width:8px; }} QPushButton:hover {{ background: {t.bg_active}; }}")
        self.eye_btn.clicked.connect(self._toggle_eye)
        key_row.addWidget(self.eye_btn, 1)

        layout.addWidget(key_container)

        layout.addStretch()

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        cancel_btn = QPushButton(_t("取消", lang))
        cancel_btn.setFixedSize(80, 36)
        cancel_btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {t.text_secondary}; border: 1px solid {t.border_subtle}; border-radius: 6px; font-size: 12px; }} QPushButton:hover {{ background: {t.bg_active}; }}")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton(_t("保存", lang))
        save_btn.setFixedSize(80, 36)
        save_btn.setStyleSheet(f"QPushButton {{ background: {t.accent}; color: #FFFFFF; border: none; border-radius: 6px; font-size: 12px; font-weight: 600; }} QPushButton:hover {{ background: {t.accent_hover}; }}")
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
        self.note_label.setVisible(not is_llm)
        self.note_input.setVisible(not is_llm)

    def get_data(self) -> dict:
        is_llm = self.type_combo.currentText() == _t("大模型密钥", self._lang)
        note = self.model_id_input.text().strip() if is_llm else self.note_input.text().strip()
        return {
            "name": self.name_input.text().strip(),
            "type": "llm" if is_llm else "secret",
            "value": self.value_input.text().strip(),
            "url": self.url_input.text().strip(),
            "url_anthropic": self.url_anthropic_input.text().strip(),
            "expire": "",
            "note": note,
        }
