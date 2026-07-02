"""文本替换工具管理器 — 系统级缩写自动替换"""

import json
import logging
import threading

from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


def _load_replacements(get_config_path) -> list[dict]:
    """从配置文件加载替换规则"""
    try:
        with open(get_config_path(), "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    return cfg.get("text_replacements", [])


def _save_replacements(get_config_path, save_config, replacements: list[dict]):
    """将替换规则保存到配置文件"""
    try:
        with open(get_config_path(), "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg["text_replacements"] = replacements
    save_config(cfg)


class TextReplacerManager:
    """文本替换核心逻辑 — 通过 pynput 全局键盘监听实现系统级替换"""

    def __init__(self, get_config_path, save_config):
        self._get_config_path = get_config_path
        self._save_config = save_config
        self._replacements: list[dict] = []
        self._buffer = ""
        self._max_abbr_len = 0
        self._listener = None
        self._running = False

    def load(self):
        """加载替换规则并启动全局监听"""
        self._replacements = _load_replacements(self._get_config_path)
        self._max_abbr_len = max((len(r["abbr"]) for r in self._replacements), default=0)
        self._start_listener()

    def reload(self):
        """重新加载规则（修改后调用）"""
        self._replacements = _load_replacements(self._get_config_path)
        self._max_abbr_len = max((len(r["abbr"]) for r in self._replacements), default=0)

    def save(self):
        """保存替换规则并刷新"""
        _save_replacements(self._get_config_path, self._save_config, self._replacements)
        self._max_abbr_len = max((len(r["abbr"]) for r in self._replacements), default=0)

    def get_replacements(self) -> list[dict]:
        return list(self._replacements)

    def add(self, abbr: str, replacement: str):
        self._replacements.append({"abbr": abbr, "replacement": replacement})
        self.save()

    def update(self, index: int, abbr: str, replacement: str):
        if 0 <= index < len(self._replacements):
            self._replacements[index] = {"abbr": abbr, "replacement": replacement}
            self.save()

    def delete(self, index: int):
        if 0 <= index < len(self._replacements):
            del self._replacements[index]
            self.save()

    def lookup(self, abbr: str) -> str | None:
        for r in self._replacements:
            if r["abbr"] == abbr:
                return r["replacement"]
        return None

    # ── 全局键盘监听 ──

    def _start_listener(self):
        """启动 pynput 全局键盘监听"""
        if self._running:
            return
        try:
            from pynput.keyboard import Listener, Key
            self._Key = Key

            def on_press(key):
                try:
                    if key == Key.tab:
                        if self._try_replace():
                            return
                        self._buffer = ""
                    elif key == Key.space or key == Key.enter:
                        self._buffer = ""
                    elif key == Key.backspace:
                        if self._buffer:
                            self._buffer = self._buffer[:-1]
                    elif hasattr(key, 'char') and key.char:
                        self._buffer += key.char
                        max_len = self._max_abbr_len + 5
                        if len(self._buffer) > max_len:
                            self._buffer = self._buffer[-max_len:]
                except Exception:
                    pass

            self._listener = Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener.start()
            self._running = True
            logger.info("文本替换全局监听已启动")
        except ImportError:
            logger.warning("pynput 未安装，文本替换功能不可用")
        except Exception as e:
            logger.warning("文本替换监听启动失败: %s", e)

    def _try_replace(self) -> bool:
        """检查缓冲区末尾是否匹配缩写，匹配则执行替换"""
        if not self._replacements or not self._buffer:
            return False
        # 从长到短匹配
        for r in sorted(self._replacements, key=lambda x: len(x["abbr"]), reverse=True):
            abbr = r["abbr"]
            if not abbr:
                continue
            if self._buffer.endswith(abbr):
                self._do_replace(len(abbr), r["replacement"])
                logger.debug("文本替换: '%s' -> '%s'", abbr, r["replacement"])
                return True
        return False

    def _do_replace(self, abbr_len: int, replacement: str):
        """通过 pynput 模拟删除缩写 + 输入替换文本"""
        try:
            from pynput.keyboard import Controller
            kb = Controller()
            # 删除缩写
            for _ in range(abbr_len):
                kb.press(self._Key.backspace)
                kb.release(self._Key.backspace)
            # 输入替换文本
            kb.type(replacement)
            self._buffer = ""
        except Exception as e:
            logger.error("替换执行失败: %s", e)

    def stop(self):
        """停止监听"""
        if self._listener:
            self._listener.stop()
            self._running = False
