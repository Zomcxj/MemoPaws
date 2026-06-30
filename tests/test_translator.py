from snaptrans.ocr.translator import SimpleTranslator


class TestTranslatorPure:
    def test_normalize_api_url_already_full(self):
        url = "https://api.openai.com/v1/chat/completions"
        assert SimpleTranslator._normalize_api_url(url) == url

    def test_normalize_api_url_partial(self):
        result = SimpleTranslator._normalize_api_url("https://open.bigmodel.cn/api/paas/v4")
        assert result == "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def test_normalize_api_url_empty(self):
        result = SimpleTranslator._normalize_api_url("")
        assert result == "/chat/completions"

    def test_to_code_all_languages(self):
        t = SimpleTranslator()
        assert t._to_code("中文") == "zh"
        assert t._to_code("英文") == "en"
        assert t._to_code("日文") == "ja"
        assert t._to_code("韩文") == "ko"
        assert t._to_code("法文") == "fr"
        assert t._to_code("德文") == "de"
        assert t._to_code("西班牙文") == "es"
        assert t._to_code("俄文") == "ru"

    def test_to_code_unknown(self):
        t = SimpleTranslator()
        assert t._to_code("火星文") == "zh"

    def test_set_mode(self):
        t = SimpleTranslator()
        assert t.mode == SimpleTranslator.MODE_LLM
        t.set_mode(SimpleTranslator.MODE_ONLINE)
        assert t.mode == SimpleTranslator.MODE_ONLINE

    def test_set_llm_config(self):
        t = SimpleTranslator()
        t.set_llm_config("my-key", "https://api.test.com/v1", "gpt-4")
        assert t.api_key == "my-key"
        assert t.api_url == "https://api.test.com/v1/chat/completions"
        assert t.api_model == "gpt-4"

    def test_init_defaults(self):
        t = SimpleTranslator()
        assert t.mode == SimpleTranslator.MODE_LLM
        assert t.api_model == "glm-4-flash"

    def test_translate_same_returns_original(self):
        t = SimpleTranslator()
        result = t.translate("Hello", "英文", "英文")
        assert result == "Hello"

    def test_translate_empty_text(self):
        t = SimpleTranslator()
        assert t.translate("", "中文") == ""
        assert t.translate("   ", "中文") == "   "

    def test_translate_none_text(self):
        t = SimpleTranslator()
        assert t.translate(None, "中文") is None
