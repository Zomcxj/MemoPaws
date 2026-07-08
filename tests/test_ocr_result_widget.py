from memopaws.core.themes import DARK
from memopaws.ui.ocr_result_widget import OCRResultWidget


def test_ocr_result_widget_create(qapp):
    widget = OCRResultWidget(DARK)

    assert widget.ocr_text_edit is not None
    assert widget.trans_text_edit is not None
    assert widget.close_btn.text() == "关闭"
