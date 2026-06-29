from snaptrans.themes import (
    ThemeColors,
    DARK,
    LIGHT,
    _hover,
    _inner_shadow,
    get_main_stylesheet,
    get_scroll_area_stylesheet,
    get_progress_bar_stylesheet,
    get_text_edit_stylesheet,
    get_status_list_stylesheet,
    get_clear_history_stylesheet,
    get_arrow_button_stylesheet,
    get_theme_button_stylesheet,
    get_config_dialog_stylesheet,
    get_canvas_stylesheet,
    get_sidebar_stylesheet,
)


def test_theme_colors_dataclass():
    t = ThemeColors(
        name="Test", is_dark=True,
        accent="#FF0000", accent_hover="#FF1111",
        bg_main="#000", bg_panel="#111", bg_input="#222",
        bg_neutral_button="#333", bg_active="#444",
        text_primary="#fff", text_secondary="#eee", text_muted="#ddd",
        border_subtle="#555", border_strong="#666",
        error="#FF0000",
        separator="#777", progress_bg="#888", progress_chunk="#999",
        scroll_handle="#aaa",
    )
    assert t.name == "Test"
    assert t.is_dark is True
    assert t.accent == "#FF0000"


def test_dark_preset_values():
    assert DARK.is_dark is True
    assert DARK.accent == "#D97757"
    assert DARK.bg_main == "#262624"
    assert DARK.text_primary == "#F1F1EF"


def test_light_preset_values():
    assert LIGHT.is_dark is False
    assert LIGHT.accent == "#D97757"
    assert LIGHT.bg_main == "#FAF8F6"


def test_hover_dark():
    assert _hover(DARK) == DARK.bg_neutral_button


def test_hover_light():
    r = _hover(LIGHT)
    assert r == "#E8E8E8"


def test_inner_shadow_dark():
    s = _inner_shadow(DARK)
    assert "rgba(0,0,0,0.5)" in s
    assert "inset" in s


def test_inner_shadow_light():
    s = _inner_shadow(LIGHT)
    assert "rgba(0,0,0,0.1)" in s


def test_get_main_stylesheet_contains_accent():
    css = get_main_stylesheet(DARK)
    assert DARK.accent in css
    assert DARK.bg_main in css
    assert DARK.text_primary in css


def test_get_main_stylesheet_light():
    css = get_main_stylesheet(LIGHT)
    assert LIGHT.accent in css


def test_get_scroll_area_stylesheet():
    css = get_scroll_area_stylesheet(DARK)
    assert DARK.scroll_handle in css
    assert "QScrollBar:vertical" in css


def test_get_progress_bar_stylesheet():
    css = get_progress_bar_stylesheet(DARK)
    assert DARK.progress_bg in css
    assert DARK.progress_chunk in css
    assert "border-radius: 9999px" in css


def test_get_text_edit_stylesheet():
    css = get_text_edit_stylesheet(DARK)
    assert DARK.border_strong in css
    assert DARK.bg_input in css


def test_get_status_list_stylesheet():
    css = get_status_list_stylesheet(DARK)
    assert DARK.bg_main in css


def test_get_clear_history_stylesheet():
    css = get_clear_history_stylesheet(DARK)
    assert DARK.bg_neutral_button in css


def test_get_arrow_button_stylesheet():
    css = get_arrow_button_stylesheet(DARK)
    assert DARK.accent in css


def test_get_theme_button_stylesheet():
    css = get_theme_button_stylesheet(DARK)
    assert DARK.accent in css


def test_get_config_dialog_default():
    css = get_config_dialog_stylesheet()
    assert DARK.bg_panel in css


def test_get_config_dialog_custom():
    css = get_config_dialog_stylesheet(LIGHT)
    assert LIGHT.bg_panel in css


def test_get_canvas_stylesheet_normal():
    css = get_canvas_stylesheet(DARK, is_dragging=False)
    assert DARK.border_subtle in css


def test_get_canvas_stylesheet_dragging():
    css = get_canvas_stylesheet(DARK, is_dragging=True)
    assert DARK.accent in css


def test_get_sidebar_stylesheet():
    css = get_sidebar_stylesheet(DARK)
    assert DARK.border_subtle in css
    assert "#1F1E1D" in css or "1F1E1D" in css
