"""剪切板编辑对话框"""

from PySide6.QtWidgets import (
    QDialog, QLabel, QTextEdit, QVBoxLayout, QHBoxLayout, QPushButton
)
from PySide6.QtCore import Qt
from .themes import DARK, LIGHT


class ClipboardEditDialog(QDialog):
    """剪切板条目编辑对话框"""
    
    def __init__(self, parent=None, text: str = "", theme=None):
        super().__init__(parent)
        if theme is None:
            from .themes import DARK
            theme = DARK
        _dlg_t = theme
        self._dlg_t = _dlg_t
        is_dark = _dlg_t.is_dark

        self.setWindowTitle("编辑剪切板条目")
        self.setMinimumSize(500, 350)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        hint = QLabel("修改文本内容（最多 2000 字符）")
        hint.setStyleSheet(f"color:{_dlg_t.text_muted}; font-size:12px; border:none;")
        layout.addWidget(hint)
        
        self.editor = QTextEdit()
        self.editor.setPlainText(text)
        _dlg_accent_border = f"{_dlg_t.accent}33"
        if is_dark:
            self.editor.setStyleSheet(f"""
                QTextEdit {{
                    background: {_dlg_t.bg_panel};
                    color: {_dlg_t.text_primary};
                    border: 1px solid {_dlg_accent_border};
                    border-radius: 8px;
                    padding: 10px;
                    font-size: 14px;
                    font-family: 'JetBrains Mono', 'Consolas', monospace;
                }}
            """)
        else:
            self.editor.setStyleSheet(f"""
                QTextEdit {{
                    background: {_dlg_t.bg_panel};
                    color: {_dlg_t.text_primary};
                    border: 1px solid rgba(0,0,0,0.15);
                    border-radius: 8px;
                    padding: 10px;
                    font-size: 14px;
                    font-family: 'JetBrains Mono', 'Consolas', monospace;
                }}
            """)
        layout.addWidget(self.editor, 1)
        
        self.char_label = QLabel("")
        self.char_label.setStyleSheet(f"color:{_dlg_t.text_muted}; font-size:11px; border:none;")
        layout.addWidget(self.char_label)
        self.editor.textChanged.connect(self._update_char_count)
        self._update_char_count()
        
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        
        cancel = QPushButton("取消")
        if is_dark:
            cancel.setStyleSheet(f"""
                QPushButton {{
                    background: {_dlg_t.bg_neutral_button}; color: {_dlg_t.text_primary};
                    border: 1px solid {_dlg_accent_border};
                    border-radius: 8px; padding: 6px 20px;
                }}
                QPushButton:hover {{ background: {_dlg_t.bg_active}; }}
            """)
        else:
            cancel.setStyleSheet(f"""
                QPushButton {{
                    background: {_dlg_t.bg_neutral_button}; color: {_dlg_t.text_primary};
                    border: 1px solid rgba(0,0,0,0.15);
                    border-radius: 8px; padding: 6px 20px;
                }}
                QPushButton:hover {{ background: {_dlg_t.bg_active}; }}
            """)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        
        save = QPushButton("保存")
        if is_dark:
            save.setStyleSheet(f"""
                QPushButton {{
                    background: {_dlg_t.bg_active}; color: {_dlg_t.accent};
                    border: 1px solid {_dlg_t.accent}66;
                    border-radius: 8px; padding: 6px 20px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background: {_dlg_t.accent_hover}; }}
            """)
        else:
            save.setStyleSheet(f"""
                QPushButton {{
                    background: {_dlg_t.accent}; color: #fff;
                    border: 1px solid {_dlg_t.accent_hover};
                    border-radius: 8px; padding: 6px 20px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background: {_dlg_t.accent_hover}; }}
            """)
        save.clicked.connect(self._on_save)
        save.setDefault(True)
        btn_row.addWidget(save)
        layout.addLayout(btn_row)
        
        self.setStyleSheet(f"QDialog {{ background: {_dlg_t.bg_panel}; color: {_dlg_t.text_primary}; }}")
    
    def _update_char_count(self):
        text = self.editor.toPlainText()
        n = len(text)
        self.char_label.setText(f"字符数: {n} / 2000")
        if n > 2000:
            from .themes import DARK as _d, LIGHT as _l
            _t_err = _d if self._dlg_t.is_dark else _l
            self.char_label.setStyleSheet(f"color:{_t_err.error}; font-size:11px; border:none;")
        else:
            self.char_label.setStyleSheet(f"color:{self._dlg_t.text_muted}; font-size:11px; border:none;")
    
    def _on_save(self):
        if len(self.editor.toPlainText()) > 2000:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "内容超过 2000 字符，请删减。")
            return
        self.accept()
    
    def get_text(self) -> str:
        return self.editor.toPlainText().strip()
