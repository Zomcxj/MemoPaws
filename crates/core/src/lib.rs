pub mod error;
pub mod paths;
pub mod theme;

pub use error::{Error, Result};
pub use theme::{Theme, ThemeTokens, DARK_TOKENS, LIGHT_TOKENS};

pub fn init() {
    let _ = paths::ensure_data_dir();
}

/// 原子写文件：临时文件 + fsync + persist(rename)，崩溃不会留下截断的目标文件。
/// 与密钥库的落盘策略一致（keys crate save）。
pub fn write_file_atomic(path: &std::path::Path, contents: &[u8]) -> Result<()> {
    use std::io::Write;
    let parent = path.parent().filter(|parent| !parent.as_os_str().is_empty());
    if let Some(parent) = parent {
        std::fs::create_dir_all(parent)?;
    }
    let directory = parent.unwrap_or_else(|| std::path::Path::new("."));
    let mut temporary = tempfile::NamedTempFile::new_in(directory)?;
    temporary.write_all(contents)?;
    temporary.as_file().sync_all()?;
    temporary.persist(path).map_err(|error| Error::Io(error.error))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::write_file_atomic;

    #[test]
    fn writes_contents_and_creates_missing_parent_dirs() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("nested").join("data.json");
        write_file_atomic(&path, b"{\"ok\":true}").unwrap();
        assert_eq!(std::fs::read(&path).unwrap(), b"{\"ok\":true}");
    }
}
