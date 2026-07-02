"""OCR 模块单元测试"""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from memopaws.ocr.ocr import (
    image_to_base64,
    OCRManager,
    OCRWorker,
    MODE_LOCAL,
    MODE_CLOUD,
)


class TestImageToBase64:
    def test_returns_string(self):
        arr = np.zeros((100, 100, 3), dtype=np.uint8)
        result = image_to_base64(arr)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_large_image_downscaled(self):
        arr = np.zeros((2000, 2000, 3), dtype=np.uint8)
        result = image_to_base64(arr)
        assert isinstance(result, str)

    def test_small_image_not_downscaled(self):
        arr = np.zeros((50, 50, 3), dtype=np.uint8)
        result = image_to_base64(arr)
        assert isinstance(result, str)


class TestOCRManager:
    def test_init_defaults(self):
        mgr = OCRManager()
        assert mgr.ocr_mode == MODE_CLOUD
        assert mgr._api_key == ""
        assert mgr._api_url == ""
        assert mgr._api_model == ""
        assert mgr._rapid_engine is None

    def test_set_config(self):
        mgr = OCRManager()
        mgr.set_config({
            "api_key": "sk-test",
            "api_url": "https://api.test.com/v1",
            "api_model": "gpt-4",
        })
        assert mgr._api_key == "sk-test"
        assert mgr._api_url == "https://api.test.com/v1"
        assert mgr._api_model == "gpt-4"

    def test_set_config_partial(self):
        mgr = OCRManager()
        mgr.set_config({"api_key": "only-key"})
        assert mgr._api_key == "only-key"
        assert mgr._api_url == ""

    def test_ocr_mode_setter(self):
        mgr = OCRManager()
        mgr.ocr_mode = MODE_LOCAL
        assert mgr.ocr_mode == MODE_LOCAL

    def test_run_ocr_dispatches_to_cloud(self):
        mgr = OCRManager()
        mgr._api_key = "test-key"
        arr = np.zeros((100, 100, 3), dtype=np.uint8)
        with patch("memopaws.ocr.ocr.call_llm_vision", return_value="recognized text") as mock:
            result = mgr.run_ocr(arr, mode=MODE_CLOUD)
            assert result == "recognized text"
            mock.assert_called_once()

    def test_run_cloud_ocr_no_key_raises(self):
        mgr = OCRManager()
        arr = np.zeros((100, 100, 3), dtype=np.uint8)
        with pytest.raises(Exception, match="未配置 API Key"):
            mgr._run_cloud_ocr(arr)

    def test_mode_constants(self):
        assert MODE_LOCAL == "local"
        assert MODE_CLOUD == "cloud"


class TestOCRWorker:
    def test_init(self, qapp):
        mgr = OCRManager()
        arr = np.zeros((100, 100, 3), dtype=np.uint8)
        worker = OCRWorker(mgr, arr, mode=MODE_CLOUD)
        assert worker.ocr_manager is mgr
        assert worker.arr is arr
        assert worker.mode == MODE_CLOUD

    def test_run_emits_finished(self, qapp):
        mgr = OCRManager()
        arr = np.zeros((100, 100, 3), dtype=np.uint8)
        worker = OCRWorker(mgr, arr, mode=MODE_CLOUD)

        received = []
        worker.finished.connect(lambda text: received.append(text))

        with patch.object(mgr, "run_ocr", return_value="result text"):
            worker.run()

        assert received == ["result text"]
