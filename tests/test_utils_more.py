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
    def test_signature(self):
        from snaptrans.utils import test_api_connection
        result = test_api_connection("fake_key", "https://fake.url", timeout=0.001)
        assert isinstance(result, dict)
        assert "success" in result
        assert "elapsed_ms" in result
        assert "error" in result
        assert result["success"] is False
