
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn display_messages_are_human_readable() {
        assert_eq!(Error::HomeDir.to_string(), "home directory not found");
        assert_eq!(Error::Custom("boom".into()).to_string(), "custom error: boom");
        assert!(Error::Io(std::io::Error::new(std::io::ErrorKind::NotFound, "missing")).to_string().contains("IO error"));
        assert!(Error::Json(serde_json::from_str::<serde_json::Value>("{").unwrap_err()).to_string().contains("JSON error"));
    }

    #[test]
    fn conversion_from_io_and_json_errors() {
        let io_error: Result<()> = Err(Error::from(std::io::Error::new(std::io::ErrorKind::Other, "io")));
        assert!(matches!(io_error, Err(Error::Io(_))));

        let json_error: Result<()> = Err(Error::from(serde_json::from_str::<serde_json::Value>("x").unwrap_err()));
        assert!(matches!(json_error, Err(Error::Json(_))));
    }
}
