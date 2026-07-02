"""翻译模块 - 支持在线翻译和大模型翻译"""

import logging
import threading

import httpx
from PySide6.QtCore import Signal, QObject

from ..core.utils import detect_lang

logger = logging.getLogger(__name__)


class SimpleTranslator:
    """翻译器 — 在线翻译（Youdao）/ 大模型翻译（OpenAI 兼容）"""
    
    MODE_ONLINE = "online"
    MODE_LLM = "llm"
    
    def __init__(self):
        self._ts_ok = False
        self._ts_tested = False
        self._ts_lock = threading.Lock()
        
        # 翻译模式配置
        self.mode = self.MODE_LLM
        self.api_key = ""
        self.api_url = self._normalize_api_url("https://open.bigmodel.cn/api/paas/v4")
        self.api_model = "glm-4-flash"
    
    @staticmethod
    def _normalize_api_url(url: str) -> str:
        """确保 URL 以 /chat/completions 结尾"""
        url = (url or "").rstrip("/")
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"
        return url

    def _to_code(self, name: str) -> str:
        """中文名 → 语言代码"""
        return {
            "中文": "zh",
            "英文": "en",
            "日文": "ja",
            "韩文": "ko",
            "法文": "fr",
            "德文": "de",
            "西班牙文": "es",
            "俄文": "ru",
        }.get(name, "zh")

    def set_mode(self, mode):
        """设置翻译模式"""
        self.mode = mode
    
    def set_llm_config(self, api_key, api_url, api_model="glm-4-flash"):
        """设置大模型 API 配置"""
        self.api_key = api_key
        self.api_url = self._normalize_api_url(api_url)
        self.api_model = api_model
    
    def _ensure_ts_ready(self):
        """首次翻译时延迟初始化在线翻译（不卡界面启动）"""
        if self._ts_tested:
            return self._ts_ok
        with self._ts_lock:
            if self._ts_tested:
                return self._ts_ok
            self._ts_tested = True
            try:
                import httpx
                r = httpx.get("https://fanyi.youdao.com", timeout=5)
                self._ts_ok = r.status_code == 200
            except Exception:
                self._ts_ok = False
            return self._ts_ok
    
    def translate(self, text, target_lang, source_lang=None):
        """翻译文本
        target_lang: 目标语言中文名
        source_lang: 源语言中文名（None=自动检测）
        """
        if not text or not text.strip():
            return text
        
        to_lang = self._to_code(target_lang)
        if source_lang and source_lang != "自动检测":
            from_lang = self._to_code(source_lang)
        else:
            from_lang = detect_lang(text)
        logger.info("翻译: target=%s, to_lang=%s, from_lang=%s, length=%d", target_lang, to_lang, from_lang, len(text))
        
        if from_lang == to_lang:
            logger.info("源语言与目标语言相同，跳过翻译")
            return text
        
        # 1. 大模型翻译（优先，当模式为 LLM 时）
        if self.mode == self.MODE_LLM and self.api_key:
            result = self._llm_translate(text, from_lang, to_lang)
            if result:
                logger.info("LLM 翻译成功: length=%d", len(result))
                return result
            else:
                logger.warning("LLM 翻译失败")
        
        # 2. Youdao 在线翻译
        if self.mode == self.MODE_ONLINE or not self.api_key:
            result = self._youdao_translate(text, from_lang, to_lang)
            if result:
                logger.info("有道翻译成功: length=%d", len(result))
                return result
        
        logger.warning("所有翻译方式都失败")
        return None
    
    def _llm_translate(self, text, from_lang, to_lang):
        """调用大模型 API 进行翻译（OpenAI 兼容格式）"""
        if not self.api_key:
            return None
        try:
            import httpx
            to_lang_name = {
                "zh": "中文", "en": "英文", "ja": "日文", "ko": "韩文",
                "fr": "法文", "de": "德文", "es": "西班牙文", "ru": "俄文"
            }.get(to_lang, "中文")
            prompt = f"请将以下内容翻译成{to_lang_name}，只输出翻译结果，不要添加任何解释或额外内容。"
            payload = {
                "model": self.api_model,
                "messages": [
                    {"role": "system", "content": "你是一个专业翻译助手，负责中文和英文之间的互译。根据用户输入的语言自动判断翻译方向，只输出翻译结果，不要添加任何解释。"},
                    {"role": "user", "content": f"{prompt}\n\n{text}"},
                ],
                "temperature": 0.7,
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            logger.debug("LLM 翻译请求: url=%s, model=%s", self.api_url, self.api_model)
            with httpx.Client(timeout=30) as client:
                resp = client.post(self.api_url, json=payload, headers=headers)
            logger.debug("LLM 翻译响应: status=%d", resp.status_code)
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if result and result != text:
                    return result
                logger.warning("LLM 翻译返回空或与原文相同")
            else:
                logger.warning("LLM 翻译 HTTP 错误: %d", resp.status_code)
        except httpx.TimeoutException:
            logger.warning("LLM 翻译超时: url=%s", self.api_url)
        except Exception as e:
            logger.warning("LLM 翻译异常: %s", e)
        return None
    
    def _youdao_translate(self, text, from_lang, to_lang):
        """调用在线翻译 API（备用）"""
        try:
            import httpx
            lang_map = {
                "zh": "zh-CN", "en": "en", "ja": "ja", "ko": "ko",
                "fr": "fr", "de": "de", "es": "es", "ru": "ru"
            }
            source_lang = lang_map.get(from_lang, "auto")
            target_lang = lang_map.get(to_lang, "en")
            
            # 尝试多个翻译 API
            apis = [
                # MyMemory
                {
                    "url": "https://api.mymemory.translated.net/get",
                    "params": {"q": text, "langpair": f"{source_lang}|{target_lang}"},
                    "method": "get",
                    "parse": lambda r: r.json().get("responseData", {}).get("translatedText", ""),
                },
                # Google Translate (unofficial)
                {
                    "url": f"https://translate.googleapis.com/translate_a/single",
                    "params": {"client": "gtx", "sl": source_lang, "tl": target_lang, "dt": "t", "q": text},
                    "method": "get",
                    "parse": lambda r: "".join([item[0] for item in r.json()[0]] if r.json() else ""),
                },
            ]
            
            with httpx.Client(timeout=10) as client:
                for api in apis:
                    try:
                        if api["method"] == "get":
                            r = client.get(api["url"], params=api["params"])
                        else:
                            r = client.post(api["url"], json=api["params"])
                        if r.status_code == 200:
                            result = api["parse"](r)
                            if result and result != text and len(result) > 1:
                                return result
                    except Exception:
                        continue
        except Exception as e:
            logger.warning("在线翻译异常: %s", e)
        return None


class TranslateWorker(QObject):
    """翻译工作线程"""
    finished = Signal(str)
    error = Signal(str)
    
    def __init__(self, translator, text, target_lang, source_lang=None):
        super().__init__()
        self.translator = translator
        self.text = text
        self.target_lang = target_lang
        self.source_lang = source_lang
    
    def run(self):
        """执行翻译"""
        try:
            translated = self.translator.translate(self.text, self.target_lang, self.source_lang)
            if translated:
                self.finished.emit(translated)
            else:
                self.error.emit("翻译失败，请检查网络连接或翻译配置")
        except Exception as e:
            logger.error("翻译线程崩溃: %s", e)
            self.error.emit(f"[翻译错误] {str(e)}")
