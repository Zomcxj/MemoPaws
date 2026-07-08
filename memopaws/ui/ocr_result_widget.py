"""OCR 结果展示组件。"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QApplication


class OCRResultWidget(QWidget):
    def __init__(self, theme, parent=None, *, ocr_title="OCR 结果", trans_title="翻译结果"):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header_css = f"color: {theme.text_primary}; font-size: 12px; font-weight: 600; background: transparent; border: none;"
        text_css = f"""
            QTextEdit {{
                background: {theme.bg_input};
                color: {theme.text_primary};
                border: 1px solid {theme.border_subtle};
                border-radius: 8px;
                padding: 6px;
                font-size: 12px;
            }}
        """
        copy_btn_css = f"""
            QPushButton {{
                background: {theme.bg_neutral_button};
                color: {theme.text_primary};
                border: none;
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {theme.border_subtle}; }}
        """

        ocr_header = QHBoxLayout()
        ocr_lbl = QLabel(ocr_title)
        ocr_lbl.setStyleSheet(header_css)
        ocr_header.addWidget(ocr_lbl)
        ocr_header.addStretch()
        self.ocr_copy_btn = QPushButton("复制")
        self.ocr_copy_btn.setStyleSheet(copy_btn_css)
        ocr_header.addWidget(self.ocr_copy_btn)
        layout.addLayout(ocr_header)

        self.ocr_text_edit = QTextEdit()
        self.ocr_text_edit.setReadOnly(True)
        self.ocr_text_edit.setMinimumHeight(80)
        self.ocr_text_edit.setStyleSheet(text_css)
        layout.addWidget(self.ocr_text_edit, 1)

        trans_header = QHBoxLayout()
        trans_lbl = QLabel(trans_title)
        trans_lbl.setStyleSheet(header_css)
        trans_header.addWidget(trans_lbl)
        trans_header.addStretch()
        self.trans_copy_btn = QPushButton("复制")
        self.trans_copy_btn.setStyleSheet(copy_btn_css)
        trans_header.addWidget(self.trans_copy_btn)
        layout.addLayout(trans_header)

        self.trans_text_edit = QTextEdit()
        self.trans_text_edit.setReadOnly(True)
        self.trans_text_edit.setMinimumHeight(80)
        self.trans_text_edit.setStyleSheet(text_css)
        layout.addWidget(self.trans_text_edit, 1)

        self.close_btn = QPushButton("关闭")
        self.close_btn.setStyleSheet(copy_btn_css)

        self.ocr_copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.ocr_text_edit.toPlainText()))
        self.trans_copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.trans_text_edit.toPlainText()))
