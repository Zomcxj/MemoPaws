import pytest

from memopaws.keys.key_dialogs import _t, _T


class TestTFunction:
    def test_zh_translation(self):
        assert _t("设置主密码", "zh") == "设置主密码"
        assert _t("大模型密钥", "zh") == "大模型密钥"
        assert _t("延迟", "zh") == "延迟"

    def test_en_translation(self):
        assert _t("设置主密码", "en") == "Set Master Password"
        assert _t("大模型密钥", "en") == "LLM Key"
        assert _t("延迟", "en") == "Latency"

    def test_missing_key_returns_key(self):
        assert _t("不存在的键", "zh") == "不存在的键"
        assert _t("不存在的键", "en") == "不存在的键"

    def test_missing_lang_falls_back(self):
        result = _t("设置主密码", "jp")
        assert result == "设置主密码"


class TestTDict:
    REQUIRED_KEYS = [
        "设置主密码", "解锁密钥管理", "输入主密码", "编辑密钥", "添加密钥",
        "名称", "大模型密钥", "普通密钥", "密钥值", "地址", "模型ID",
        "API 密钥", "取消", "保存", "错误", "解锁", "锁定", "测试速度",
        "测试中", "复制", "编辑", "删除", "模型", "延迟",
    ]

    def test_all_required_keys_exist(self):
        for key in self.REQUIRED_KEYS:
            assert key in _T, f"缺少翻译键: {key}"

    def test_all_keys_have_zh_and_en(self):
        for key, value in _T.items():
            assert "zh" in value, f"键 {key} 缺少中文翻译"
            assert "en" in value, f"键 {key} 缺少英文翻译"
            assert value["zh"], f"键 {key} 中文翻译为空"
            assert value["en"], f"键 {key} 英文翻译为空"

    def test_translations_are_different(self):
        for key, value in _T.items():
            if key not in ("取消", "保存", "错误", "名称", "删除", "复制", "编辑", "测试"):
                continue
            if value["zh"] == value["en"]:
                continue
            assert value["zh"] != value["en"] or key in ("取消", "保存", "错误", "名称", "删除", "复制", "编辑", "测试"), \
                f"键 {key} 中英文相同: {value['zh']}"
