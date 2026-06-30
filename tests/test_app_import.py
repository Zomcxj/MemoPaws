"""验证整个应用能被成功导入，无缺失依赖或导入时错误"""

def test_main_window_import():
    """涵盖 main_window → recognize_page → OCRWorker 等全链路导入"""
    from snaptrans.ui.main_window import MainWindow  # noqa: F401
    assert MainWindow is not None
