"""配置对话框模块"""

import logging

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton,
    QLineEdit, QPushButton, QLabel, QFormLayout, QMessageBox
)
from PySide6.QtCore import Qt

from ..core.themes import DARK, LIGHT, get_config_dialog_stylesheet
from ..core.utils import set_title_bar_color

logger = logging.getLogger(__name__)


class ConfigDialog(QDialog):
    """应用设置对话框"""

    def __init__(self, parent=None, config=None, is_dark=True):
        super().__init__(parent)
        self.setWindowTitle("应用设置")
        self.setFixedSize(520, 440)
        self.setWindowModality(Qt.WindowModality.WindowModal)

        # 读取已有配置
        cfg = config or {}

        self.api_key = cfg.get("api_key", "")
        self.api_url = cfg.get(
            "api_url",
            "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        )
        self.api_model = cfg.get("api_model", "glm-4-flash")
        self.close_behavior = cfg.get("close_behavior", "exit")  # "exit" or "tray"

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # ── API 配置 ──
        api_group = QGroupBox("API 配置（用于 AI 识别 / AI 翻译）")
        api_layout = QFormLayout(api_group)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("输入 API Key")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setText(self.api_key)
        self.api_key_input.setMinimumHeight(32)
        api_layout.addRow("API Key", self.api_key_input)

        self.api_url_input = QLineEdit()
        self.api_url_input.setPlaceholderText("输入 API Base URL")
        self.api_url_input.setText(self.api_url)
        self.api_url_input.setMinimumHeight(32)
        api_layout.addRow("API Base URL", self.api_url_input)

        self.api_model_input = QLineEdit()
        self.api_model_input.setPlaceholderText("如 glm-4v-flash, deepseek-vl2 等")
        self.api_model_input.setText(self.api_model)
        self.api_model_input.setMinimumHeight(32)
        api_layout.addRow("模型名", self.api_model_input)

        # 多模态模型提示
        note_label = QLabel("💡 AI 识别使用<b>多模态模型</b>（支持图片理解），非纯文本模型")
        note_label.setWordWrap(True)
        note_label.setStyleSheet("font-size:12px; color:#888; padding:2px 0;")
        api_layout.addRow("", note_label)

        # 测试按钮 + 结果显示框
        test_row = QHBoxLayout()
        self.test_btn = QPushButton("🔄 测试 API 连接")
        self.test_btn.setMinimumHeight(28)
        self.test_btn.clicked.connect(self._test_api_connection)
        test_row.addWidget(self.test_btn)

        self.test_result_label = QLabel("—")
        self.test_result_label.setMinimumWidth(160)
        self.test_result_label.setAlignment(Qt.AlignCenter)
        self.test_result_label.setStyleSheet(
            "font-size:13px; color:#888; padding:4px 8px; border:1px solid #ccc; border-radius:4px;"
        )
        test_row.addWidget(self.test_result_label)
        api_layout.addRow("", test_row)

        layout.addWidget(api_group)

        # ── 关闭行为 ──
        close_group = QGroupBox("关闭行为")
        close_layout = QVBoxLayout(close_group)

        self.rb_close_exit = QRadioButton("直接退出程序")
        self.rb_close_tray = QRadioButton("最小化到系统托盘")

        if self.close_behavior == "tray":
            self.rb_close_tray.setChecked(True)
        else:
            self.rb_close_exit.setChecked(True)

        close_layout.addWidget(self.rb_close_exit)
        close_layout.addWidget(self.rb_close_tray)
        layout.addWidget(close_group)

        # ── 快捷键提示 ──
        shortcut_label = QLabel("📷 截图快捷键：<b>Alt+X</b>（截图后自动加载到画布）")
        shortcut_label.setWordWrap(True)
        shortcut_label.setStyleSheet("font-size:13px; padding:4px 0;")
        layout.addWidget(shortcut_label)

        # ── 按钮 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setMinimumWidth(80)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("保存")
        self.btn_save.setMinimumWidth(80)
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._save_and_accept)
        btn_row.addWidget(self.btn_save)

        layout.addLayout(btn_row)

        # 样式
        theme = DARK if is_dark else LIGHT
        self.setStyleSheet(get_config_dialog_stylesheet(theme))
        self._is_dark = is_dark
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, lambda: set_title_bar_color(int(self.winId()), self._is_dark))

    def _save_and_accept(self):
        self.api_key = self.api_key_input.text().strip()
        self.api_url = self.api_url_input.text().strip()
        self.api_model = self.api_model_input.text().strip() or "glm-4-flash"
        self.close_behavior = "tray" if self.rb_close_tray.isChecked() else "exit"
        self.accept()

    def _test_api_connection(self):
        """测试多模态 API 连接"""
        api_key = self.api_key_input.text().strip()
        api_url = self.api_url_input.text().strip()
        model = self.api_model_input.text().strip() or "glm-4v-flash"

        if not api_key:
            QMessageBox.warning(self, "测试失败", "请先填写 API Key")
            return

        self.test_btn.setText("⏳ 测试中...")
        self.test_btn.setEnabled(False)
        # 强制刷新界面
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self._do_test(api_key, api_url, model))

    def _do_test(self, api_key, api_url, model):
        from ..ocr.ocr import test_vision_api
        from PySide6.QtCore import QTimer

        def update_display(success, latency_ms, text, error):
            """直接在右侧显示框中显示结果"""
            if not success:
                if error:
                    self.test_result_label.setText(f"❌ {error[:30]}")
                    self.test_result_label.setStyleSheet(
                        "font-size:13px; color:#ff6b6b; padding:4px 8px; border:1px solid #ff6b6b; border-radius:4px;"
                    )
                else:
                    self.test_result_label.setText("❌ 失败")
                    self.test_result_label.setStyleSheet(
                        "font-size:13px; color:#ff6b6b; padding:4px 8px; border:1px solid #ff6b6b; border-radius:4px;"
                    )
            else:
                if text:
                    self.test_result_label.setText(f"✅ {latency_ms}ms | {text[:20]}")
                else:
                    self.test_result_label.setText(f"✅ {latency_ms}ms")
                self.test_result_label.setStyleSheet(
                    "font-size:13px; color:#51cf66; padding:4px 8px; border:1px solid #51cf66; border-radius:4px;"
                )

        try:
            result = test_vision_api(api_key, api_url, model)

            if result["success"]:
                text = result["text"]
                latency = result["latency_ms"]
                # 检测文本模型回复特征（多模态模型应能准确读出测试图片文字）
                if not text or len(text) < 4 or "无法处理" in text or "cannot process" in text.lower() \
                        or "sorry" in text.lower() and ("image" in text.lower() or "text" in text.lower()) \
                        or "incomplete message" in text.lower():
                    update_display(False, latency, text, "请使用多模态模型（如 glm-4v-flash）")
                else:
                    update_display(True, latency, text, None)
            else:
                latency = result["latency_ms"]
                error = result["error"]
                update_display(False, latency, "", error)
        except Exception as e:
            update_display(False, 0, "", str(e)[:30])
        finally:
            self.test_btn.setText("🔄 测试 API 连接")
            self.test_btn.setEnabled(True)

    def get_config(self):
        """获取配置"""
        return {
            "api_key": self.api_key,
            "api_url": self.api_url,
            "api_model": self.api_model,
            "close_behavior": self.close_behavior,
        }
