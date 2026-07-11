import re

import pytest

from memopaws.core.themes import DARK, LIGHT
from memopaws.memo.markdown_converter import markdown_to_html


@pytest.mark.parametrize("theme", [DARK, LIGHT])
def test_body_uses_preview_background_and_keeps_theme_formatting(theme):
    html = markdown_to_html("# 标题\n\n正文含有 `代码`", theme)
    body_style = re.search(r'<body style="([^"]*)">', html).group(1)

    assert "background:" not in body_style
    assert f"color:{theme.text_primary};" in body_style
    assert f'<h1 style="color:{theme.text_primary};' in html
    assert f'<code style="background:{theme.bg_input};' in html
