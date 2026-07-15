from pathlib import Path


def test_main_does_not_disable_qtwebengine_sandbox():
    main_source = (Path(__file__).parent.parent / "main.py").read_text(encoding="utf-8")

    assert "QTWEBENGINE_DISABLE_SANDBOX" not in main_source
