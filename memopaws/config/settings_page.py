"""设置页面模块 - 从 main_window.py 提取"""

import os
import logging

from PySide6.QtWidgets import QWidget, QLineEdit, QFrame, QMessageBox
from PySide6.QtCore import Qt

from ..core.themes import DARK, LIGHT
from ..core.utils import (
    get_root_path, get_config_dir, normalize_api_url
)
from .api_config import load_api_to_inputs, test_api_connection
from .migration import ask_existing_data_mode, ask_restart, migrate_storage_root
from .settings_style import apply_input_styles as apply_settings_input_styles
from .settings_ui import build_settings_ui

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    """设置页面独立模块"""

    def __init__(self, parent, *,
                 get_config_path,
                 get_theme,
                 is_dark,
                 load_config,
                 save_config,
                 ocr_manager,
                 on_toggle_theme,
                 on_set_theme,
                 on_set_language,
                 get_current_lang,
                 get_current_theme_dark,
                 on_save_clipboard,
                 show_message,
                 shortcut_mgr=None,
                 text_replacer=None):
        super().__init__(parent)
        self._get_config_path = get_config_path
        self._get_theme = get_theme
        self._is_dark = is_dark
        self._load_config = load_config
        self._save_config = save_config
        self._ocr_manager = ocr_manager
        self._on_toggle_theme = on_toggle_theme
        self._set_theme = on_set_theme
        self._on_set_language = on_set_language
        self._get_current_lang = get_current_lang
        self._get_current_theme_dark = get_current_theme_dark
        self._on_save_clipboard = on_save_clipboard
        self._show_message = show_message
        self._shortcut_mgr = shortcut_mgr

        self._create_ui()
        self.apply_theme()  # 初始化时应用主题色

        if hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(lambda _: self.apply_theme())
        if hasattr(parent, 'language_changed'):
            parent.language_changed.connect(self.apply_language)

    def _create_ui(self):
        build_settings_ui(self)

    def _init_seg_indicators(self):
        """布局就绪后一次性设置分段按钮的初始状态（样式 + 指示器位置）"""
        self._update_theme_seg_style()
        self._update_lang_seg_style()
        self._update_close_seg_style()

    # ── 样式刷新 ──

    def apply_input_styles(self):
        """根据当前主题应用 API 输入框样式。"""
        apply_settings_input_styles(self)
        self._update_theme_seg_style()

    def apply_theme(self):
        """刷新设置页所有主题相关样式"""
        t = DARK if self._is_dark() else LIGHT

        # 刷新卡片背景
        for card in self.findChildren(QFrame):
            if card.objectName() == "card":
                card.setStyleSheet(f"""
                    QFrame#card {{
                        background: {t.bg_panel};
                        border: 1px solid {t.border_subtle};
                        border-radius: 12px;
                        padding: 16px;
                    }}
                """)

        # 刷新标题颜色
        self.theme_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        self.lang_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        self.api_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        self.clip_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        if hasattr(self, 'hist_title_lbl'):
            self.hist_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        self.shortcut_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        self.close_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")
        if hasattr(self, 'memo_path_title_lbl'):
            self.memo_path_title_lbl.setStyleSheet(f"font-size:16px; font-weight:600; color:{t.text_primary}; border:none; background:transparent;")

        # 快捷键输入框 + 重置按钮
        _input_ss = f"""
            QLineEdit {{
                background: {t.bg_input};
                color: {t.text_primary};
                border: 1px solid {t.border_subtle};
                border-radius: 6px;
                padding: 0 8px;
                font-size: 12px;
                font-weight: bold;
            }}
            QLineEdit:focus {{ border: 1px solid {t.accent}; }}
        """
        _reset_ss = f"""
            QPushButton {{
                background: {t.bg_neutral_button};
                color: {t.text_secondary};
                border: 1px solid {t.border_subtle};
                border-radius: 6px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {t.bg_active}; }}
        """
        if hasattr(self, '_shortcut_edit_rows'):
            for row_data in self._shortcut_edit_rows:
                if len(row_data) >= 3:
                    row_data[2].setStyleSheet(_input_ss)
                if len(row_data) >= 4:
                    row_data[3].setStyleSheet(_reset_ss)

        # 备忘录路径输入框 + 浏览按钮
        if hasattr(self, 'settings_memo_path_input'):
            self.settings_memo_path_input.setStyleSheet(_input_ss)
        if hasattr(self, '_memo_browse_btn'):
            self._memo_browse_btn.setStyleSheet(_reset_ss)
        if hasattr(self, 'memo_path_tip'):
            self.memo_path_tip.setStyleSheet(f"font-size:11px; color:{t.text_muted}; border:none; background:transparent;")

        # 主题分段按钮容器
        if hasattr(self, '_theme_seg'):
            self._theme_seg.setStyleSheet(f"""
                QFrame {{
                    background: {t.bg_neutral_button};
                    border: 1px solid {t.border_subtle};
                    border-radius: 8px;
                }}
            """)
        self._update_theme_seg_style()

        # 语言分段按钮容器
        if hasattr(self, '_lang_seg'):
            self._lang_seg.setStyleSheet(f"""
                QFrame {{
                    background: {t.bg_neutral_button};
                    border: 1px solid {t.border_subtle};
                    border-radius: 8px;
                }}
            """)
        self._update_lang_seg_style()

        # 关闭行为分段按钮容器
        if hasattr(self, '_close_seg'):
            self._close_seg.setStyleSheet(f"""
                QFrame {{
                    background: {t.bg_neutral_button};
                    border: 1px solid {t.border_subtle};
                    border-radius: 8px;
                }}
            """)
        self._update_close_seg_style()

        # 输入框样式
        self.apply_input_styles()

    def apply_language(self, lang: str):
        """刷新设置页所有文字"""
        if hasattr(self, 'settings_key_label'):
            self.settings_key_label.setText("API Key")
        if hasattr(self, 'settings_url_label'):
            self.settings_url_label.setText("API URL")
        if hasattr(self, 'settings_model_label'):
            self.settings_model_label.setText("Model" if lang == "en" else "模型")
        if hasattr(self, 'settings_max_label'):
            self.settings_max_label.setText("Max Records" if lang == "en" else "最大条数")
        if hasattr(self, 'theme_title_lbl'):
            self.theme_title_lbl.setText("Theme Mode" if lang == "en" else "主题模式")
        if hasattr(self, 'lang_title_lbl'):
            self.lang_title_lbl.setText("Language" if lang == "en" else "语言")
        if hasattr(self, 'api_title_lbl'):
            self.api_title_lbl.setText("API Configuration" if lang == "en" else "API 配置")
        if hasattr(self, 'clip_title_lbl'):
            self.clip_title_lbl.setText("Clipboard Settings" if lang == "en" else "剪切板设置")
        if hasattr(self, 'shortcut_title_lbl'):
            self.shortcut_title_lbl.setText("Keyboard Shortcuts" if lang == "en" else "键盘快捷键")
        if hasattr(self, 'close_title_lbl'):
            self.close_title_lbl.setText("Close Behavior" if lang == "en" else "关闭窗口")
        if hasattr(self, 'settings_test_btn'):
            self.settings_test_btn.setText("Test" if lang == "en" else "测试连接")
        if hasattr(self, 'settings_btn_save'):
            self.settings_btn_save.setText("Save" if lang == "en" else "保存")
        if hasattr(self, 'settings_max_tip'):
            self.settings_max_tip.setText(
                "(Max records; oldest unlocked items auto-deleted when exceeded)" if lang == "en"
                else "(总条数上限；超出时自动删除最旧的非锁定项)")
        # 操作历史
        if hasattr(self, 'hist_title_lbl'):
            self.hist_title_lbl.setText("History" if lang == "en" else "操作历史")
        if hasattr(self, 'hist_max_label'):
            self.hist_max_label.setText("Max Items" if lang == "en" else "最大条数")
        if hasattr(self, 'hist_max_tip'):
            self.hist_max_tip.setText(
                "(Oldest records auto-deleted when exceeded)" if lang == "en"
                else "(超出时自动删除最旧记录)")
        # 关闭行为分段按钮
        if hasattr(self, 'close_btn_exit'):
            self.close_btn_exit.setText("Exit" if lang == "en" else "直接关闭")
            self.close_btn_tray.setText("Tray" if lang == "en" else "最小化到任务栏")
        # 同步分段按钮选中状态
        self._update_close_seg_style()
        # 快捷键芯片名称
        if hasattr(self, 'shortcut_title_lbl'):
            self.shortcut_title_lbl.setText("Keyboard Shortcuts" if lang == "en" else "快捷键")
        # Reset 按钮文字同步
        if hasattr(self, '_shortcut_edit_rows'):
            for row_data in self._shortcut_edit_rows:
                if len(row_data) >= 4:
                    row_data[3].setText("Reset" if lang == "en" else "重置")
        # 快捷键标签名称同步
        _shortcut_names_zh = {"capture": "截图识别", "canvas_fit": "画布自适应", "new_memo": "新建备忘录", "toggle_clipboard": "开关剪切板"}
        _shortcut_names_en = {"capture": "Capture", "canvas_fit": "Canvas Fit", "new_memo": "New Memo", "toggle_clipboard": "Toggle Clipboard"}
        if hasattr(self, '_shortcut_edit_rows'):
            for row_data in self._shortcut_edit_rows:
                if len(row_data) >= 2:
                    action = row_data[0]
                    name_map = _shortcut_names_en if lang == "en" else _shortcut_names_zh
                    row_data[1].setText(name_map.get(action, action))
        # 备忘录路径
        if hasattr(self, 'memo_path_title_lbl'):
            self.memo_path_title_lbl.setText("Storage Directory" if lang == "en" else "存储目录")
        if hasattr(self, 'memo_path_tip'):
            self.memo_path_tip.setText(
                "Leave empty for default path, entire .memopaws folder will be moved"
                if lang == "en" else "留空则使用默认路径，切换后整个 .memopaws 文件夹会移动")
        if hasattr(self, '_memo_browse_btn'):
            self._memo_browse_btn.setText("Browse" if lang == "en" else "浏览")
        # 剪切板设置
        if hasattr(self, 'settings_max_label'):
            self.settings_max_label.setText("Max Items" if lang == "en" else "最大条数")
        if hasattr(self, 'settings_max_tip'):
            self.settings_max_tip.setText(
                "(Max items; oldest unlocked items auto-deleted when exceeded)"
                if lang == "en" else "(总条数上限；超出时自动删除最旧的非锁定项)")
        # 同步分段按钮选中状态
        self._update_lang_seg_style()

    def _update_lang_seg_style(self):
        """刷新语言分段按钮的选中样式"""
        if not hasattr(self, 'btn_lang_en'):
            return
        t = DARK if self._is_dark() else LIGHT
        is_en = self._get_current_lang() == "en"
        self.btn_lang_en.blockSignals(True)
        self.btn_lang_zh.blockSignals(True)
        self.btn_lang_en.setChecked(is_en)
        self.btn_lang_zh.setChecked(not is_en)
        self.btn_lang_en.blockSignals(False)
        self.btn_lang_zh.blockSignals(False)
        btn_ss = f"QPushButton {{ background: transparent; color: {t.text_secondary}; border: none; border-radius: 8px; font-size: 13px; padding: 0 0 2px 0; }}"
        active_text_ss = f"QPushButton {{ background: transparent; color: #FFFFFF; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; padding: 0 0 2px 0; }}"
        self.btn_lang_en.setStyleSheet(active_text_ss if is_en else btn_ss)
        self.btn_lang_zh.setStyleSheet(active_text_ss if not is_en else btn_ss)
        self._lang_seg_ctrl.set_accent(t.accent)
        self._lang_seg_ctrl.update_position(animated=False)

    def _update_theme_seg_style(self):
        """刷新主题分段按钮的选中样式"""
        if not hasattr(self, 'btn_theme_dark'):
            return
        t = DARK if self._is_dark() else LIGHT
        is_dark = self._is_dark()
        self.btn_theme_dark.setChecked(is_dark)
        self.btn_theme_light.setChecked(not is_dark)
        btn_ss = f"QPushButton {{ background: transparent; color: {t.text_secondary}; border: none; border-radius: 8px; font-size: 13px; padding: 0 0 2px 0; }}"
        active_text_ss = f"QPushButton {{ background: transparent; color: #FFFFFF; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; padding: 0 0 2px 0; }}"
        self.btn_theme_dark.setStyleSheet(active_text_ss if is_dark else btn_ss)
        self.btn_theme_light.setStyleSheet(active_text_ss if not is_dark else btn_ss)
        self._theme_seg_ctrl.set_accent(t.accent)
        self._theme_seg_ctrl.update_position(animated=True)

    def _set_close_behavior(self, behavior: str):
        self._close_behavior = behavior
        self._update_close_seg_style()
        # 立即持久化到配置文件，无需等用户点"保存"
        config = self._load_config()
        config["close_behavior"] = behavior
        self._save_config(config)

    def _update_close_seg_style(self):
        """刷新关闭行为分段按钮的选中样式"""
        if not hasattr(self, 'close_btn_exit'):
            return
        t = DARK if self._is_dark() else LIGHT
        is_tray = getattr(self, '_close_behavior', 'exit') == 'tray'
        self.close_btn_exit.setChecked(not is_tray)
        self.close_btn_tray.setChecked(is_tray)
        btn_ss = f"QPushButton {{ background: transparent; color: {t.text_secondary}; border: none; border-radius: 8px; font-size: 13px; padding: 0 0 2px 0; }}"
        active_text_ss = f"QPushButton {{ background: transparent; color: #FFFFFF; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; padding: 0 0 2px 0; }}"
        self.close_btn_exit.setStyleSheet(active_text_ss if not is_tray else btn_ss)
        self.close_btn_tray.setStyleSheet(active_text_ss if is_tray else btn_ss)
        self._close_seg_ctrl.set_accent(t.accent)
        self._close_seg_ctrl.update_position(animated=True)
        # 更新文字
        _lang = self._get_current_lang()
        self.btn_theme_dark.setText("Dark" if _lang == "en" else "暗色")
        self.btn_theme_light.setText("Light" if _lang == "en" else "亮色")

    # ── 快捷键编辑 ──

    def eventFilter(self, obj, event):
        """拦截快捷键输入框的按键事件，录制快捷键"""
        from PySide6.QtCore import QEvent
        if (hasattr(obj, '_shortcut_action')
                and isinstance(obj, QLineEdit)
                and event.type() == QEvent.Type.KeyPress):
            key = event.key()
            mods = event.modifiers()
            if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                return False
            parts = []
            if mods & Qt.KeyboardModifier.ControlModifier:
                parts.append("Ctrl")
            if mods & Qt.KeyboardModifier.AltModifier:
                parts.append("Alt")
            if mods & Qt.KeyboardModifier.ShiftModifier:
                parts.append("Shift")
            if mods & Qt.KeyboardModifier.MetaModifier:
                parts.append("Meta")
            from PySide6.QtGui import QKeySequence
            seq = QKeySequence(key)
            key_name = seq.toString()
            if key_name:
                parts.append(key_name)
            combo = "+".join(parts)
            obj.setText(combo)
            if self._shortcut_mgr:
                self._shortcut_mgr.update_shortcut(obj._shortcut_action, combo)
            return True
        return super().eventFilter(obj, event)

    def _reset_shortcut(self, action: str, edit: QLineEdit):
        """重置某个快捷键为默认值"""
        from .shortcut_manager import DEFAULT_SHORTCUTS
        default_key = DEFAULT_SHORTCUTS.get(action, "")
        edit.setText(default_key)
        if self._shortcut_mgr:
            self._shortcut_mgr.update_shortcut(action, default_key)

    # ── 备忘录存储路径 ──

    def _load_memo_path_setting(self):
        """从配置加载存储目录"""
        self.settings_memo_path_input.setText(get_root_path())

    def _browse_memo_path(self):
        """浏览选择备忘录存储目录"""
        from PySide6.QtWidgets import QFileDialog
        dir_path = QFileDialog.getExistingDirectory(self, "选择备忘录存储目录")
        if dir_path:
            self.settings_memo_path_input.setText(dir_path)

    # ── 文本替换 CRUD ──

    # ── 配置加载/保存 ──

    def _load_api_to_inputs(self):
        """加载配置到设置页面输入框。"""
        load_api_to_inputs(self)

    def _normalize_api_url(self, url: str) -> str:
        """兼容旧调用，实际实现位于 core.utils。"""
        return normalize_api_url(url)

    def _test_api_connection(self):
        """测试 API 连接。"""
        test_api_connection(self)

    def _save_api_config(self):
        """保存 API 配置"""
        config = self._load_config()
        config["api_key"] = self.settings_key_input.text().strip()
        config["api_url"] = self._normalize_api_url(self.settings_url_input.text().strip())
        config["api_model"] = self.settings_model_input.text().strip() or "glm-4-flash"
        config["close_behavior"] = getattr(self, '_close_behavior', 'exit')
        config["history_max_items"] = int(self.settings_hist_max_input.value())

        # 存储目录
        new_root = self.settings_memo_path_input.text().strip()
        current_root = os.path.dirname(get_config_dir())  # .memopaws 的父目录

        if new_root and new_root != current_root:
            dst_memopaws = os.path.join(new_root, ".memopaws")
            if os.path.exists(dst_memopaws):
                move_mode = ask_existing_data_mode(self, dst_memopaws, self._get_current_lang())
                if move_mode is None:
                    return
            else:
                move_mode = "move"

            if not migrate_storage_root(current_root, new_root, move_mode, logger=logger):
                self._show_message(QMessageBox.Icon.Warning, "错误", "移动文件夹失败")
                return

            self._save_config(config)
            self._ocr_manager.set_config(config)
            self.settings_url_input.setText(config["api_url"])
            self._save_clip_setting(config=config)

            if ask_restart(self, self._get_current_lang()):
                import sys
                import subprocess
                subprocess.Popen([sys.executable] + sys.argv)
                sys.exit(0)
        else:
            self._save_config(config)
            self._ocr_manager.set_config(config)
            self.settings_url_input.setText(config["api_url"])
            self._save_clip_setting(config=config)
            self._show_message(QMessageBox.Icon.Information, "提示", "配置已保存")

    def _load_clip_setting_to_input(self):
        config = self._load_config()
        try:
            v = int(config.get("clipboard_max_items", 50))
        except Exception:
            v = 50
        self.settings_clip_max_input.setValue(max(10, min(500, v)))

    def _save_clip_setting(self, config=None):
        if config is None:
            config = self._load_config()
        config["clipboard_max_items"] = int(self.settings_clip_max_input.value())
        self._save_config(config)
        self._on_save_clipboard()

    def _load_hist_setting_to_input(self):
        config = self._load_config()
        try:
            v = int(config.get("history_max_items", 100))
        except Exception:
            v = 100
        self.settings_hist_max_input.setValue(max(10, min(500, v)))

    def _save_hist_setting(self, config=None):
        if config is None:
            config = self._load_config()
        config["history_max_items"] = int(self.settings_hist_max_input.value())
        self._save_config(config)
