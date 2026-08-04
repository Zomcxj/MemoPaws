
#[derive(thiserror::Error, Debug)]
pub enum MemopawsError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("home directory not found")]
    HomeDir,
    #[error("custom error: {0}")]
    Custom(String),
}

pub type Error = MemopawsError;
pub type Result<T> = std::result::Result<T, Error>;
