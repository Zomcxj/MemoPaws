"""OCR 识别模块 - 支持本地 RapidOCR 和多模态大模型"""

import os
import io
import sys
import json
import base64
import logging
import traceback

from .utils import BUNDLE_DIR

import numpy as np
import cv2
from PIL import Image
from PySide6.QtCore import Signal, QObject

logger = logging.getLogger(__name__)

# OCR 模式
MODE_LOCAL = "local"      # 本地 RapidOCR
MODE_CLOUD = "cloud"      # 多模态大模型


def image_to_base64(arr: np.ndarray) -> str:
    """将 numpy 数组转换为 base64 字符串"""
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    
    max_size = 1024
    if max(pil_img.size) > max_size:
        ratio = max_size / max(pil_img.size)
        new_size = (int(pil_img.width * ratio), int(pil_img.height * ratio))
        pil_img = pil_img.resize(new_size, Image.LANCZOS)
    
    buffer = io.BytesIO()
    pil_img.save(buffer, format="PNG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def test_vision_api(api_key: str, api_url: str = None, model: str = None) -> dict:
    """生成一张测试图片并调用多模态 API，返回 dict: {success, latency_ms, text, error}"""
    import time
    from PIL import Image, ImageDraw, ImageFont

    # 创建带文字的测试图片
    img = Image.new('RGB', (240, 60), color='white')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("simhei.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    draw.text((12, 14), "测试文字 OCR", fill='black', font=font)

    import io
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    start = time.perf_counter()
    try:
        text = call_llm_vision(image_base64, api_key, api_url, model)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {"success": True, "latency_ms": elapsed_ms, "text": text.strip(), "error": None}
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {"success": False, "latency_ms": elapsed_ms, "text": "", "error": str(e)}


def call_llm_vision(image_base64: str, api_key: str, api_url: str = None, model: str = None) -> str:
    """调用多模态大模型识别图片文字"""
    import httpx
    
    url = api_url or "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    model_name = model or "glm-4v-flash"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": "请识别这张图片中的所有文字内容，直接输出识别结果，不要添加任何解释或额外内容。保持原文的格式和换行。"
                    }
                ]
            }
        ],
        "temperature": 0.1,
    }
    
    logger.debug("调用多模态大模型 API... model=%s url=%s", model_name, url)
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, json=payload, headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        result = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return result
    else:
        raise Exception(f"API 错误: HTTP {resp.status_code} - {resp.text[:200]}")


class OCRManager:
    """OCR 管理器"""
    
    def __init__(self):
        self._ocr_mode = MODE_CLOUD
        self._api_key = ""
        self._api_url = ""
        self._api_model = ""
        self._rapid_engine = None
    
    def set_config(self, config: dict):
        """由主窗口调用，传入配置"""
        self._api_key = config.get("api_key", "")
        self._api_url = config.get("api_url", "")
        self._api_model = config.get("api_model", "")
        logger.info("OCR 配置已更新: has_key=%s, key_prefix=%s, model=%s", 
                    bool(self._api_key), self._api_key[:10] if self._api_key else "None",
                    self._api_model or "glm-4v-flash(默认)")
    
    @property
    def ocr_mode(self):
        return self._ocr_mode
    
    @ocr_mode.setter
    def ocr_mode(self, mode):
        self._ocr_mode = mode
    
    def _get_rapid_engine(self):
        """延迟初始化 RapidOCR 引擎"""
        if self._rapid_engine is None:
            try:
                from rapidocr import RapidOCR
                import os
                
                # 设置环境变量强制使用 CPU
                os.environ['ONNXRUNTIME_DISABLE_PROVIDERS'] = 'AzureExecutionProvider'
                
                # 使用自定义配置文件（禁用所有非 CPU 提供程序）
                config_path = os.path.join(
                    BUNDLE_DIR,
                    'snaptrans', 'resources', 'rapidocr_config.yaml'
                )
                
                if os.path.exists(config_path):
                    self._rapid_engine = RapidOCR(config_path=config_path)
                else:
                    # 回退到默认配置，但强制 CPU
                    self._rapid_engine = RapidOCR(params={
                        'EngineConfig': {
                            'onnxruntime': {
                                'use_cuda': False,
                                'use_dml': False,
                                'use_cann': False,
                                'use_coreml': False,
                            }
                        }
                    })
                logger.info("RapidOCR 引擎初始化成功")
            except Exception as e:
                logger.error("RapidOCR 初始化失败: %s", e)
                raise Exception(f"本地识别引擎初始化失败: {e}")
        return self._rapid_engine
    
    def run_ocr(self, arr: np.ndarray, mode: str = None) -> str:
        """运行 OCR 识别"""
        if mode is None:
            mode = self._ocr_mode
        
        if mode == MODE_CLOUD:
            return self._run_cloud_ocr(arr)
        else:
            return self._run_local_ocr(arr)
    
    def _run_cloud_ocr(self, arr: np.ndarray) -> str:
        """使用多模态大模型进行 OCR"""
        if not self._api_key:
            raise Exception("未配置 API Key，请在设置中配置大模型 API Key")
        
        image_base64 = image_to_base64(arr)
        return call_llm_vision(image_base64, self._api_key, self._api_url, self._api_model)
    
    def _run_local_ocr(self, arr: np.ndarray) -> str:
        """使用本地 RapidOCR 进行 OCR"""
        try:
            engine = self._get_rapid_engine()
            result = engine(arr)
            
            if result.txts:
                return "\n".join(result.txts)
            else:
                return "未识别到文字"
        except Exception as e:
            logger.error("本地识别失败: %s", e)
            raise Exception(f"[OCR 错误] 本地识别失败: {e}")


class OCRWorker(QObject):
    """OCR 工作线程"""
    finished = Signal(str)
    
    def __init__(self, ocr_manager, arr, mode=None):
        super().__init__()
        self.ocr_manager = ocr_manager
        self.arr = arr
        self.mode = mode
    
    def run(self):
        """执行 OCR 识别"""
        logger.debug("OCRWorker 开始运行, 模式=%s", self.mode or self.ocr_manager.ocr_mode)
        try:
            text = self.ocr_manager.run_ocr(self.arr, mode=self.mode)
            logger.debug("OCR 识别完成, 文本长度=%d", len(text))
            self.finished.emit(text)
        except Exception as e:
            logger.error("OCR 线程崩溃: %s", traceback.format_exc())
            self.finished.emit(f"[OCR 错误] {str(e)}")
