"""设置页 API 配置逻辑。"""

import time

from PySide6.QtWidgets import QApplication

from ..core.themes import DARK, LIGHT
from ..core.utils import normalize_api_url


def load_api_to_inputs(page):
    """加载配置到设置页面输入框。"""
    config = page._load_config()
    page.settings_key_input.setText(config.get("api_key", ""))
    page.settings_url_input.setText(config.get("api_url", "https://open.bigmodel.cn/api/paas/v4/chat/completions"))
    page.settings_model_input.setText(config.get("api_model", "glm-4-flash"))


def test_api_connection(page):
    """测试 API 连接。"""
    import httpx

    theme = DARK if page._is_dark() else LIGHT
    api_key = page.settings_key_input.text().strip()
    api_url = page.settings_url_input.text().strip()
    api_model = page.settings_model_input.text().strip() or "glm-4-flash"

    if not api_key:
        page.settings_test_label.setText("⚠ 请填写 API Key")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
        return

    page.settings_test_label.setText("⏳ 测试中...")
    page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.accent}; border:none;")
    QApplication.processEvents()

    t0 = time.perf_counter()
    try:
        url = normalize_api_url(api_url)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": api_model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}

        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json=payload, headers=headers)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        _show_api_test_response(page, resp, api_key, api_url, api_model, elapsed_ms, theme)
    except httpx.TimeoutException:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        page.settings_test_label.setText(f"❌ 网络超时 ({elapsed_ms} ms)")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
    except httpx.ConnectError:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        page.settings_test_label.setText(f"❌ 无法连接服务器 ({elapsed_ms} ms)")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
    except Exception as exc:
        page.settings_test_label.setText(f"❌ 失败: {type(exc).__name__}")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")


def _show_api_test_response(page, resp, api_key: str, api_url: str, api_model: str, elapsed_ms: int, theme):
    if resp.status_code == 200:
        from ..ocr.ocr import test_vision_api

        vision_result = test_vision_api(api_key, api_url, api_model)
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
    elif resp.status_code == 401:
        page.settings_test_label.setText("❌ API Key Invalid (401)")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
    elif resp.status_code == 404:
        msg = "❌ 路径错误 (404)"
        try:
            detail = (resp.text or "")[:120].replace("\n", " ")
            if detail:
                msg += f": {detail}"
        except Exception:
            pass
        page.settings_test_label.setText(msg)
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
    else:
        page.settings_test_label.setText(f"❌ HTTP {resp.status_code} ({elapsed_ms} ms)")
        page.settings_test_label.setStyleSheet(f"font-size:12px; color:{theme.error}; border:none;")
