use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Theme {
    Dark,
    Light,
}

impl Theme {
    pub fn is_dark(&self) -> bool {
        matches!(self, Theme::Dark)
    }

    pub fn tokens(&self) -> ThemeTokens {
        match self {
            Theme::Dark => DARK_TOKENS,
            Theme::Light => LIGHT_TOKENS,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThemeTokens {
    pub bg_primary: &'static str,
    pub bg_secondary: &'static str,
    pub bg_input: &'static str,
    pub bg_panel: &'static str,
    pub bg_neutral_button: &'static str,
    pub text_primary: &'static str,
    pub text_secondary: &'static str,
    pub text_muted: &'static str,
    pub accent: &'static str,
    pub accent_hover: &'static str,
    pub border: &'static str,
    pub border_subtle: &'static str,
    pub surface: &'static str,
    pub error: &'static str,
    pub is_dark: bool,
}

pub const DARK_TOKENS: ThemeTokens = ThemeTokens {
    bg_primary: "#262624",
    bg_secondary: "#2C2C2B",
    bg_input: "#1B1B19",
    bg_panel: "#2C2C2B",
    bg_neutral_button: "#2C2C2B",
    text_primary: "#F1F1EF",
    text_secondary: "#C3C0B6",
    text_muted: "#B7B5A9",
    accent: "#D97757",
    accent_hover: "#E08D6F",
    border: "#52514A",
    border_subtle: "#3E3E38",
    surface: "#3E3E38",
    error: "#EF4444",
    is_dark: true,
};

pub const LIGHT_TOKENS: ThemeTokens = ThemeTokens {
    bg_primary: "#FAF8F6",
    bg_secondary: "#FFFFFF",
    bg_input: "#F5F3F0",
    bg_panel: "#FFFFFF",
    bg_neutral_button: "#F0EDE8",
    text_primary: "#1C1B1A",
    text_secondary: "#6B6560",
    text_muted: "#9A9590",
    accent: "#D97757",
    accent_hover: "#C56646",
    border: "#C9C5BD",
    border_subtle: "#E0DCD8",
    surface: "#E8E5E0",
    error: "#BA1A1A",
    is_dark: false,
};
