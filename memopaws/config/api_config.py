"""设置页 API 配置逻辑。"""

import asyncio
import time

from PySide6.QtCore import QThread, Signal

from ..core.themes import DARK, LIGHT
from ..core.utils import normalize_api_url


class ApiTestThread(QThread):
    """在后台线程中执行 API 连通性测试，避免阻塞设置页 UI。"""

    result_ready = Signal(dict)

    def __init__(self, api_key: str, api_url: str, api_model: str):
        super().__init__()
        self.api_key = api_key
        self.api_url = api_url
        self.api_model = api_model

    def run(self):
        result = asyncio.run(_run_api_test_async(self.api_key, self.api_url, self.api_model))
        if self.isInterruptionRequested():
            result["cancelled"] = True
        self.result_ready.emit(result)


async def _run_api_test_async(api_key: str, api_url: str, api_model: str) -> dict:
    """异步执行文本接口测试；成功后在线程池中执行图片能力探测。"""
    import httpx

    t0 = time.perf_counter()
    try:
        url = normalize_api_url(api_url)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": api_model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        result = {"status_code": resp.status_code, "text": resp.text, "elapsed_ms": elapsed_ms}
        if resp.status_code == 200:
            from ..ocr.ocr import test_vision_api

            result["vision_result"] = await asyncio.to_thread(test_vision_api, api_key, api_url, api_model)
        return result
    except httpx.TimeoutException:
        return {"error": "timeout", "elapsed_ms": int((time.perf_counter() - t0) * 1000)}
    except httpx.ConnectError:
        return {"error": "connect", "elapsed_ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        return {"error": "exception", "exception_type": type(exc).__name__, "elapsed_ms": int((time.perf_counter() - t0) * 1000)}


def load_api_to_inputs(page):
    """加载配置到设置页面输入框。"""
    config = page._load_config()
    page.settings_key_input.setText(config.get("api_key", ""))
    page.settings_url_input.setText(config.get("api_url", "https://open.bigmodel.cn/api/paas/v4/chat/completions"))
    page.settings_model_input.setText(config.get("api_model", "glm-4-flash"))


def test_api_connection(page):
    """测试 API 连接。再次点击测试按钮可请求取消当前测试。"""

    theme = DARK if page._is_dark() else LIGHT

    running_thread = getattr(page, "_api_test_thread", None)
    if running_thread is not None and running_thread.isRunning():
        running_thread.requestInterruption()
        page.settings_test_label.setText("⏹ 正在取消...")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.text_muted}; border:none;")
        return

    api_key = page.settings_key_input.text().strip()
    api_url = page.settings_url_input.text().strip()
    api_model = page.settings_model_input.text().strip() or "glm-4-flash"

    if not api_key:
        page.settings_test_label.setText("⚠ 请填写 API Key")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
        return

    page.settings_test_label.setText("⏳ 测试中...")
    page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.accent}; border:none;")
    if hasattr(page, "settings_test_btn"):
        page.settings_test_btn.setText("取消")

    thread = ApiTestThread(api_key, api_url, api_model)
    page._api_test_thread = thread
    thread.result_ready.connect(lambda result: _show_api_test_result(page, result, theme))
    thread.finished.connect(thread.deleteLater)
    thread.start()


def _show_api_test_result(page, result: dict, theme):
    if getattr(page, "_api_test_thread", None):
        page._api_test_thread = None
    if hasattr(page, "settings_test_btn"):
        page.settings_test_btn.setText("测试连接")

    elapsed_ms = result.get("elapsed_ms", 0)
    if result.get("cancelled"):
        page.settings_test_label.setText("⏹ 已取消")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.text_muted}; border:none;")
        return
    if result.get("error") == "timeout":
        page.settings_test_label.setText(f"❌ 网络超时 ({elapsed_ms} ms)")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
        return
    if result.get("error") == "connect":
        page.settings_test_label.setText(f"❌ 无法连接服务器 ({elapsed_ms} ms)")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
        return
    if result.get("error"):
        page.settings_test_label.setText(f"❌ 失败: {result.get('exception_type', 'Exception')}")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
        return

    status_code = result.get("status_code")
    if status_code == 200:
        vision_result = result.get("vision_result") or {"success": False, "error": "", "text": ""}
        err = vision_result.get("error", "")
        txt = vision_result.get("text", "")
        is_vision = vision_result["success"] and not err and ("测试" in txt or "OCR" in txt or "ocr" in txt)
        if is_vision:
            page.settings_test_label.setText(f"✅ 连接成功 ({elapsed_ms} ms) | 多模态模型，支持图片识别")
            page.settings_test_label.setStyleSheet("font-size:12px; color:#2ecc71; border:none;")
        else:
            page.settings_test_label.setText(f"✅ 连接成功 ({elapsed_ms} ms) | ⚠ 文本模型，不支持图片文字识别")
            warn_theme = DARK if page._is_dark() else LIGHT
            page.settings_test_label.setStyleSheet(f"font-size:12px; color:{warn_theme.accent}; border:none;")
    elif status_code == 401:
        page.settings_test_label.setText("❌ API Key Invalid (401)")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
    elif status_code == 404:
        msg = "❌ 路径错误 (404)"
        try:
            detail = (result.get("text") or "")[:120].replace("\n", " ")
            if detail:
                msg += f": {detail}"
        except Exception:
            pass
        page.settings_test_label.setText(msg)
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
    else:
        page.settings_test_label.setText(f"❌ HTTP {status_code} ({elapsed_ms} ms)")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
