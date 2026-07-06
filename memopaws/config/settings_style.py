"""设置页样式刷新辅助。"""

from ..core.themes import DARK, LIGHT, _inner_shadow


def apply_input_styles(page):
    """根据当前主题应用 API/数字输入框样式。"""
    theme = DARK if page._is_dark() else LIGHT
    bg, fg, border = theme.bg_input, theme.text_primary, theme.border_subtle
    label_color = theme.text_secondary
    tip_color = theme.text_secondary
    accent_color = theme.accent
    shadow = _inner_shadow(theme)
    input_style = f"""
        QLineEdit {{
            background: {bg};
            color: {fg};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 6px 10px;
            font-size: 13px;
            {shadow}
        }}
        QLineEdit:focus {{ border: 1px solid {accent_color}; }}
    """
    for inp in (page.settings_key_input, page.settings_url_input, page.settings_model_input):
        inp.setStyleSheet(input_style)

    spin_style = f"""
        QSpinBox {{
            background: {bg};
            color: {fg};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 4px 8px;
            font-size: 13px;
            min-width: 50px;
            max-width: 60px;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            background: {bg};
            border: none;
            width: 16px;
        }}
    """
    page.settings_clip_max_input.setStyleSheet(spin_style)
    if hasattr(page, 'settings_hist_max_input'):
        page.settings_hist_max_input.setStyleSheet(spin_style)

    label_style = f"font-size:13px; color:{label_color}; border:none; background:transparent;"
    tip_style = f"font-size:12px; color:{tip_color}; border:none; background:transparent;"
    for lbl in (page.settings_key_label, page.settings_url_label, page.settings_model_label,
                page.settings_max_label, page.hist_max_label):
        lbl.setStyleSheet(label_style)
    page.settings_max_tip.setStyleSheet(tip_style)
    if hasattr(page, 'hist_max_tip'):
        page.hist_max_tip.setStyleSheet(tip_style)
