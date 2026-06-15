"""历史记录管理模块"""

import os
import json
import time
from typing import Optional, Callable, List, Any


class HistoryManager:
    """历史记录管理器，独立于 UI"""

    def __init__(self, get_config_path: Callable[[], str]):
        """
        初始化历史记录管理器
        
        Args:
            get_config_path: 回调函数，返回配置文件路径
        """
        self._get_config_path = get_config_path
        self._history_file = self._derive_history_path(get_config_path())
        self.history_data: List[dict] = []
    
    @staticmethod
    def _derive_history_path(config_path: str) -> str:
        """从配置文件路径推导历史记录文件路径"""
        # 去掉 .json 后缀，加 _history.json
        if config_path.endswith('.json'):
            base = config_path[:-5]
        else:
            base = config_path
        return f"{base}_history.json"
    
    def load(self) -> List[dict]:
        """加载历史记录"""
        if os.path.exists(self._history_file):
            try:
                with open(self._history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.history_data = data
                    return data
            except Exception:
                pass
        self.history_data = []
        return self.history_data
    
    def save(self):
        """保存历史记录到文件"""
        try:
            from .utils import ensure_config_dir
            ensure_config_dir()
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def add_record(self, action_type: str, text: str, **extra):
        """添加操作历史记录
        
        Args:
            action_type: 显示前缀，如 "识别(本地)" / "翻译(英文)" / "翻译失败(AI)"
            text: 记录文本
            extra: 可选，存额外字段 (ocr_text, source, target, mode_name)
        """
        record = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": action_type,
            "text": text[:5000],
        }
        record.update(extra)
        self.history_data.insert(0, record)
        self.history_data = self.history_data[:100]
        self.save()
    
    def clear(self):
        """清空历史记录"""
        self.history_data.clear()
        self.save()
    
    @staticmethod
    def parse_translate_record(text: str) -> tuple:
        """解析老格式翻译记录 text，提取 source 和 target"""
        source = None
        target = None
        for line in text.split("\n"):
            if line.startswith("[原文] "):
                source = line[len("[原文] "):]
            elif line.startswith("[译文] "):
                target = line[len("[译文] "):]
        return source, target
    
    def update_status_list(self, status_list):
        """更新状态列表 UI
        
        Args:
            status_list: QListWidget 实例
        """
        from PySide6.QtWidgets import QListWidgetItem
        from PySide6.QtCore import Qt
        
        status_list.clear()
        for r in self.history_data[:50]:
            item = QListWidgetItem(f"[{r['time']}] {r['type']}")
            item.setData(Qt.ItemDataRole.UserRole, r)
            status_list.addItem(item)
    
    def on_history_clicked(self, item, ocr_text_widget, translate_text_widget, 
                          nav_sidebar, content_stack, switch_page_callback):
        """点击操作历史：恢复内容到识别/翻译结果框
        
        Args:
            item: QListWidgetItem
            ocr_text_widget: OCR 结果 QTextEdit
            translate_text_widget: 翻译结果 QTextEdit
            nav_sidebar: NavSidebar 实例（可为 None）
            content_stack: 页面栈 QStackedWidget
            switch_page_callback: 切换页面的回调函数
        """
        from PySide6.QtCore import Qt
        
        record = item.data(Qt.ItemDataRole.UserRole)
        if not record:
            return
        
        action_type = record.get("type", "")
        if action_type.startswith("识别"):
            ocr_text = record.get("ocr_text") or record.get("text", "")
            ocr_text_widget.setPlainText(ocr_text)
            translate_text_widget.clear()
        elif action_type.startswith("翻译失败"):
            err = record.get("text", "")
            translate_text_widget.setPlainText(err)
        elif action_type.startswith("翻译"):
            source = record.get("source")
            target = record.get("target")
            if source is None or target is None:
                # 兼容老 record：从 text 字段解析
                parsed_text = record.get("text", "")
                source, target = self.parse_translate_record(parsed_text)
            if source is not None:
                ocr_text_widget.setPlainText(source)
            if target is not None:
                translate_text_widget.setPlainText(target)
        
        # 切换到贴图识别页面
        if nav_sidebar:
            nav_sidebar.switch_page("贴图识别")
        else:
            switch_page_callback("贴图识别")
