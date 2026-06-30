"""工具函数单元测试"""

import os
import sys
import tempfile
import shutil

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snaptrans.core.utils import detect_lang


def test_ensure_config_dir():
    test_dir = tempfile.mkdtemp()
    test_config_dir = os.path.join(test_dir, ".SnapTrans")
    os.makedirs(test_config_dir, exist_ok=True)
    assert os.path.isdir(test_config_dir)
    shutil.rmtree(test_dir)


def test_detect_lang_chinese():
    assert detect_lang("你好世界") == "zh"


def test_detect_lang_english():
    assert detect_lang("Hello World") == "en"


def test_detect_lang_empty():
    assert detect_lang("") == "en"
    assert detect_lang(None) == "en"
