use std::sync::Mutex;

use memopaws_canvas::CaptureManager;
use memopaws_clipboard::ClipboardManager;
use memopaws_config::history::HistoryManager;
use memopaws_keys::KeyVault;

pub type KeyVaultState = Mutex<KeyVault>;
pub type HistoryState = Mutex<HistoryManager>;
pub type ClipboardState = Mutex<ClipboardManager>;
pub type CaptureState = Mutex<CaptureManager>;

/// Acquire a state lock and recover from poisoning instead of failing the
/// command. A transient panic elsewhere must never permanently brick UI flows
/// with "… state is unavailable"; the recovered guard mirrors the recovery that
/// `lock_vault_state` already performs when the window closes.
macro_rules! lock_recover {
    ($lock:expr) => {
        ($lock)
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    };
}

mod capture;
mod clipboard;
mod config;
mod history;
mod keys;
mod memo;
mod ocr;
mod storage;
mod textrep;
mod update;

pub use capture::*;
pub use clipboard::*;
pub use config::*;
pub use history::*;
pub use keys::*;
pub use memo::*;
pub use ocr::*;
pub use storage::*;
pub use textrep::*;
pub use update::*;
