"""历史记录管理模块"""

import os
import json
import time
from typing import Optional, Callable, List, Any


class HistoryManager:
    """历史记录管理器，独立于 UI"""

    def __init__(self, get_config_path: Callable[[], str] = None):
        """
        初始化历史记录管理器
        """
        self.history_data: List[dict] = []
        self._get_config_path = get_config_path
    
    @property
    def _history_file(self) -> str:
        if self._get_config_path:
            config_dir = os.path.dirname(self._get_config_path())
            return os.path.join(config_dir, "history.json")
        from ..core.utils import HISTORY_FILE
        return HISTORY_FILE

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
            path = self._history_file
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def add_record(self, action_type: str, text: str, **extra):
        """添加操作历史记录"""
        record = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": action_type,
            "text": text[:5000],
        }
        record.update(extra)
        self.history_data.insert(0, record)
        # 读取配置中的最大条数
        max_items = 100
        try:
            cfg_path = self._get_config_path() if self._get_config_path else None
            if not cfg_path:
                from ..core.utils import CONFIG_FILE
                cfg_path = CONFIG_FILE
            if cfg_path and os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                max_items = int(cfg.get("history_max_items", 100))
        except Exception:
            pass
        self.history_data = self.history_data[:max_items]
        self.save()
    
    def clear(self):
        """清空历史记录"""
        self.history_data.clear()
        self.save()

    def delete_record(self, index: int):
        """删除指定索引的历史记录"""
        if 0 <= index < len(self.history_data):
            self.history_data.pop(index)
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
