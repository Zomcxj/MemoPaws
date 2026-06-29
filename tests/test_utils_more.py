import pytest

from snaptrans.utils import (
    detect_lang,
    normalize_api_url,
)


class TestDetectLang:
    def test_chinese(self):
        assert detect_lang("你好世界") == "zh"
        assert detect_lang("这是一段中文") == "zh"
        assert detect_lang("混合英文 Chinese") == "zh"

    def test_english(self):
        assert detect_lang("Hello World") == "en"
        assert detect_lang("This is a test") == "en"

    def test_mixed_mostly_english(self):
        assert detect_lang("hello 你好") == "zh"

    def test_edge_single_cjk(self):
        assert detect_lang("你") == "zh"

    def test_edge_numbers_symbols(self):
        assert detect_lang("12345!@#$%") == "en"

    def test_empty_string(self):
        assert detect_lang("") == "en"

    def test_none(self):
        assert detect_lang(None) == "en"

    def test_whitespace_only(self):
        assert detect_lang("   ") == "en"

    def test_cjk_at_threshold(self):
        result = detect_lang("a你")
        assert result == "zh"


class TestNormalizeApiUrl:
    def test_already_full(self):
        assert normalize_api_url("https://api.openai.com/v1/chat/completions") == \
            "https://api.openai.com/v1/chat/completions"

    def test_partial_url(self):
        assert normalize_api_url("https://open.bigmodel.cn/api/paas/v4") == \
            "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def test_empty_returns_default(self):
        result = normalize_api_url("")
        assert result == "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def test_none_returns_default(self):
        result = normalize_api_url(None)
        assert result == "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def test_trailing_slash(self):
        assert normalize_api_url("https://api.test.com/v1/") == \
            "https://api.test.com/v1/chat/completions"

    def test_with_path_and_chat(self):
        result = normalize_api_url("https://api.test.com/chat/completions")
        assert result == "https://api.test.com/chat/completions"


class TestApiConnection:
    @staticmethod
    def _mock_client(status_code: int = 200, delay: float = 0):
        """创建 httpx.Client 的 mock，可配置状态码和延迟"""
        from unittest.mock import MagicMock
        import time

        mock_resp = MagicMock(status_code=status_code)

        def mock_post(*args, **kwargs):
            if delay > 0:
                time.sleep(delay)
            return mock_resp

        mock_instance = MagicMock()
        mock_instance.post = mock_post
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=None)

        return MagicMock(return_value=mock_instance)

    def test_success_200(self):
        from unittest.mock import patch
        from snaptrans.utils import test_api_connection

        with patch("httpx.Client", self._mock_client(200, delay=0.03)):
            result = test_api_connection("test_key", "https://api.test.com", timeout=5)

        assert result["success"] is True
        assert 25 <= result["elapsed_ms"] <= 200  # 模拟的 30ms 延迟
        assert result["status_code"] == 200
        assert result["error"] == ""

    def test_latency_increases_with_delay(self):
        from unittest.mock import patch
        from snaptrans.utils import test_api_connection

        with patch("httpx.Client", self._mock_client(200, delay=0.05)):
            r1 = test_api_connection("k", "https://api.test.com", timeout=5)
        with patch("httpx.Client", self._mock_client(200, delay=0.1)):
            r2 = test_api_connection("k", "https://api.test.com", timeout=5)

        assert r1["elapsed_ms"] < r2["elapsed_ms"]

    def test_auth_error_401(self):
        from unittest.mock import patch
        from snaptrans.utils import test_api_connection

        with patch("httpx.Client", self._mock_client(401)):
            result = test_api_connection("bad_key", "https://api.test.com", timeout=5)

        assert result["success"] is False
        assert result["status_code"] == 401

    def test_timeout_error(self):
        from unittest.mock import patch, MagicMock
        import httpx
        from snaptrans.utils import test_api_connection

        mock_instance = MagicMock()
        mock_instance.post = MagicMock(side_effect=httpx.TimeoutException("timeout", request=None))
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=None)

        with patch("httpx.Client", MagicMock(return_value=mock_instance)):
            result = test_api_connection("k", "https://slow.api.com", timeout=0.001)

        assert result["success"] is False
        assert result["error"] == "timeout"
        assert result["status_code"] == 0

    def test_connect_error(self):
        from unittest.mock import patch, MagicMock
        import httpx
        from snaptrans.utils import test_api_connection

        mock_instance = MagicMock()
        mock_instance.post = MagicMock(side_effect=httpx.ConnectError("connection refused"))
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=None)

        with patch("httpx.Client", MagicMock(return_value=mock_instance)):
            result = test_api_connection("k", "https://bad.api.com", timeout=5)

        assert result["success"] is False
        assert result["error"] == "connect_error"
        assert result["status_code"] == 0
