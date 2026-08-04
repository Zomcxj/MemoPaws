pub mod error;
pub mod paths;
pub mod theme;

pub use error::{Error, Result};
pub use theme::{Theme, ThemeTokens, DARK_TOKENS, LIGHT_TOKENS};

pub fn init() {
    let _ = paths::ensure_data_dir();
}
