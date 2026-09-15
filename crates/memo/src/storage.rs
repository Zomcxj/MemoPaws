use std::fs::{self, File};
use std::io::{self, Write};
use std::collections::HashSet;
use std::path::{Component, Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::model::Memo;

pub type Result<T> = std::result::Result<T, MemoError>;

#[derive(Debug)]
pub enum MemoError {
    Io(io::Error),
    InvalidPath(String),
    NotFound(i64),
    InvalidData(String),
    Conflict(String),
}

impl std::fmt::Display for MemoError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(error) => write!(f, "{error}"),
            Self::InvalidPath(path) => write!(f, "invalid memo path: {path}"),
            Self::NotFound(id) => write!(f, "memo {id} not found"),
            Self::InvalidData(message) => write!(f, "invalid memo data: {message}"),
            Self::Conflict(message) => write!(f, "memo conflict: {message}"),
        }
    }
}

impl std::error::Error for MemoError {}

impl From<io::Error> for MemoError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}

#[derive(Debug, Default, Eq, PartialEq)]
pub struct Frontmatter {
    pub time: String,
    pub created: String,
    pub modified: String,
    pub title: String,
    pub tags: Vec<String>,
}

pub fn resolve_memo_dir(custom_path: Option<&Path>) -> Result<PathBuf> {
    let dir = match custom_path {
        Some(path) => path.to_path_buf(),
        None => memopaws_core::paths::memos_dir()
            .map_err(|error| MemoError::InvalidData(error.to_string()))?,
    };
    fs::create_dir_all(&dir)?;
    Ok(dir)
}

pub fn sanitize_filename(title: &str, id: i64) -> String {
    let mut safe = String::with_capacity(title.len());
    let mut previous_underscore = false;
    for character in title.chars() {
        let invalid = character.is_control() || matches!(character, '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*');
        let character = if invalid { '_' } else { character };
        if character == '_' {
            if !previous_underscore {
                safe.push(character);
            }
            previous_underscore = true;
        } else {
            safe.push(character);
            previous_underscore = false;
        }
    }
    let safe = safe.trim().trim_matches(|c| matches!(c, '_' | '.' | ' '));
    format!("{}_{}.md", if safe.is_empty() { "memo" } else { safe }, id)
}

pub fn safe_memo_path(memo_dir: &Path, filename: &str) -> Result<PathBuf> {
    let path = Path::new(filename);
    if filename.is_empty()
        || path.extension().and_then(|value| value.to_str()) != Some("md")
        || path.components().count() != 1
        || !matches!(path.components().next(), Some(Component::Normal(_)))
    {
        return Err(MemoError::InvalidPath(filename.into()));
    }
    Ok(memo_dir.join(path))
}

pub fn parse_frontmatter(text: &str) -> Result<(Frontmatter, String)> {
    if !text.starts_with("---") {
        return Ok((Frontmatter::default(), text.to_string()));
    }
    let Some(remainder) = text.strip_prefix("---\n").or_else(|| text.strip_prefix("---\r\n")) else {
        return Ok((Frontmatter::default(), text.to_string()));
    };
    let Some((raw_metadata, content)) = remainder.split_once("\n---") else {
        return Ok((Frontmatter::default(), text.to_string()));
    };
    let mut metadata = Frontmatter::default();
    for line in raw_metadata.lines() {
        let Some((key, value)) = line.split_once(':') else { continue };
        let value = value.trim().to_string();
        match key.trim() {
            "time" => metadata.time = value,
            "created" => metadata.created = value,
            "modified" => metadata.modified = value,
            "title" => metadata.title = value,
            "tags" => metadata.tags = value.split(',').map(str::trim).filter(|tag| !tag.is_empty()).map(String::from).collect(),
            _ => {}
        }
    }
    // Two strips, not a repeat: `split_once("\n---")` leaves the newline that
    // ends the closing delimiter *and* the blank line `build_frontmatter` writes
    // after it (`"---\n\n"`). Dropping either one leaves the body indented by a
    // stray newline.
    let content = content.strip_prefix("\r\n").or_else(|| content.strip_prefix('\n')).unwrap_or(content);
    let content = content.strip_prefix("\r\n").or_else(|| content.strip_prefix('\n')).unwrap_or(content);
    Ok((metadata, content.trim_end_matches(['\r', '\n']).to_string()))
}

pub fn build_frontmatter(memo: &Memo) -> String {
    let created = if memo.created.is_empty() { &memo.time } else { &memo.created };
    let modified = if memo.modified.is_empty() { &memo.time } else { &memo.modified };
    let title = memo.title.replace(['\r', '\n'], " ");
    let tags = memo.tags.iter().map(|tag| tag.replace([',', '\r', '\n'], " ")).collect::<Vec<_>>().join(", ");
    let mut output = format!("---\ntitle: {title}\ncreated: {created}\nmodified: {modified}\n");
    if !memo.time.is_empty() {
        output.push_str(&format!("time: {}\n", memo.time.replace(['\r', '\n'], " ")));
    }
    if !tags.is_empty() {
        output.push_str(&format!("tags: {tags}\n"));
    }
    output.push_str("---\n\n");
    output
}

pub fn list_memos(memo_dir: &Path) -> Result<Vec<Memo>> {
    fs::create_dir_all(memo_dir)?;
    let mut memos = Vec::new();
    for entry in fs::read_dir(memo_dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("md") || !entry.file_type()?.is_file() {
            continue;
        }
        match memo_from_file(&path) {
            Ok(memo) => memos.push(memo),
            Err(MemoError::InvalidData(_)) => continue,
            Err(MemoError::Io(error)) if error.kind() == io::ErrorKind::InvalidData => continue,
            Err(error) => return Err(error),
        }
    }
    let mut ids = HashSet::new();
    if let Some(duplicate) = memos.iter().find(|memo| !ids.insert(memo.id)) {
        return Err(MemoError::Conflict(format!("duplicate memo id {}", duplicate.id)));
    }
    memos.sort_by(|left, right| right.modified.cmp(&left.modified));
    Ok(memos)
}

pub fn read_memo(memo_dir: &Path, id: i64) -> Result<Memo> {
    list_memos(memo_dir)?.into_iter().find(|memo| memo.id == id).ok_or(MemoError::NotFound(id))
}

pub fn create_memo(memo_dir: &Path, mut memo: Memo) -> Result<Memo> {
    fs::create_dir_all(memo_dir)?;
    if list_memos(memo_dir)?.iter().any(|existing| existing.id == memo.id) {
        return Err(MemoError::Conflict(format!("memo {} already exists", memo.id)));
    }
    let filename = sanitize_filename(&memo.title, memo.id);
    memo.file = Some(filename.clone());
    atomic_write_new(&safe_memo_path(memo_dir, &filename)?, &(build_frontmatter(&memo) + &memo.content))?;
    Ok(memo)
}

pub fn update_memo(memo_dir: &Path, mut memo: Memo) -> Result<Memo> {
    let existing = read_memo(memo_dir, memo.id)?;
    let filename = existing.file.ok_or_else(|| MemoError::InvalidData("memo filename missing".into()))?;
    let path = safe_memo_path(memo_dir, &filename)?;
    memo.file = Some(filename);
    atomic_write_replace(&path, &(build_frontmatter(&memo) + &memo.content))?;
    Ok(memo)
}

pub fn delete_memo(memo_dir: &Path, id: i64) -> Result<()> {
    let memo = read_memo(memo_dir, id)?;
    let filename = memo.file.ok_or_else(|| MemoError::InvalidData("memo filename missing".into()))?;
    fs::remove_file(safe_memo_path(memo_dir, &filename)?)?;
    Ok(())
}

fn memo_from_file(path: &Path) -> Result<Memo> {
    let text = fs::read_to_string(path)?;
    let (metadata, content) = parse_frontmatter(&text)?;
    let filename = path.file_name().and_then(|value| value.to_str()).ok_or_else(|| MemoError::InvalidData("non-UTF-8 filename".into()))?;
    let stem = path.file_stem().and_then(|value| value.to_str()).unwrap_or("memo");
    let id = stem.rsplit_once('_').and_then(|(_, id)| id.parse().ok()).unwrap_or_else(|| {
        fs::metadata(path).and_then(|value| value.modified()).ok().and_then(|value| value.duration_since(UNIX_EPOCH).ok()).map(|value| value.as_millis() as i64).unwrap_or(0)
    });
    let time = metadata.time;
    Ok(Memo {
        id,
        created: if metadata.created.is_empty() { time.clone() } else { metadata.created },
        modified: if metadata.modified.is_empty() { time.clone() } else { metadata.modified },
        time,
        title: if metadata.title.is_empty() { stem.to_string() } else { metadata.title },
        content,
        tags: metadata.tags,
        file: Some(filename.to_string()),
    })
}

pub(crate) fn write_migrated_memo(memo_dir: &Path, mut memo: Memo, filename: &str) -> Result<Memo> {
    let path = safe_memo_path(memo_dir, filename)?;
    memo.file = Some(filename.to_string());
    atomic_write_new(&path, &(build_frontmatter(&memo) + &memo.content))?;
    Ok(memo)
}

fn temporary_path(path: &Path) -> Result<PathBuf> {
    let parent = path.parent().ok_or_else(|| MemoError::InvalidPath(path.display().to_string()))?;
    let nonce = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_nanos();
    Ok(parent.join(format!(".memo-{nonce}-{}.tmp", std::process::id())))
}

fn write_temporary(path: &Path, contents: &str) -> Result<PathBuf> {
    let temporary = temporary_path(path)?;
    let mut file = File::create(&temporary)?;
    file.write_all(contents.as_bytes())?;
    file.sync_all()?;
    Ok(temporary)
}

fn atomic_write_replace(path: &Path, contents: &str) -> Result<()> {
    atomic_write_replace_with(path, contents, replace_file)
}

fn atomic_write_replace_with<F>(path: &Path, contents: &str, replace: F) -> Result<()>
where
    F: FnOnce(&Path, &Path) -> io::Result<()>,
{
    let temporary = write_temporary(path, contents)?;
    let result = (|| -> Result<()> {
        replace(&temporary, path)?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

fn atomic_write_new(path: &Path, contents: &str) -> Result<()> {
    let temporary = write_temporary(path, contents)?;
    let result = install_new_file(&temporary, path).map_err(|error| {
        if error.kind() == io::ErrorKind::AlreadyExists {
            MemoError::Conflict(format!("target file {} already exists", path.display()))
        } else {
            MemoError::Io(error)
        }
    });
    let _ = fs::remove_file(&temporary);
    result
}

#[cfg(not(windows))]
fn install_new_file(source: &Path, destination: &Path) -> io::Result<()> {
    fs::hard_link(source, destination)
}

#[cfg(windows)]
fn install_new_file(source: &Path, destination: &Path) -> io::Result<()> {
    move_file(source, destination, false)
}

#[cfg(not(windows))]
fn replace_file(source: &Path, destination: &Path) -> io::Result<()> {
    fs::rename(source, destination)
}

#[cfg(windows)]
fn replace_file(source: &Path, destination: &Path) -> io::Result<()> {
    move_file(source, destination, true)
}

#[cfg(windows)]
fn move_file(source: &Path, destination: &Path, replace: bool) -> io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH};

    let source: Vec<u16> = source.as_os_str().encode_wide().chain(Some(0)).collect();
    let destination: Vec<u16> = destination.as_os_str().encode_wide().chain(Some(0)).collect();
    let flags = MOVEFILE_WRITE_THROUGH | if replace { MOVEFILE_REPLACE_EXISTING } else { 0 };
    let success = unsafe { MoveFileExW(source.as_ptr(), destination.as_ptr(), flags) };
    if success == 0 { Err(io::Error::last_os_error()) } else { Ok(()) }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn atomic_replace_keeps_old_file_when_replace_fails() {
        let root = std::env::temp_dir().join(format!(
            "memopaws-rename-rollback-{}",
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos()
        ));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("Memo_1.md");
        fs::write(&path, "original").unwrap();

        let result = atomic_write_replace_with(&path, "replacement", |_, _| {
            Err(io::Error::new(io::ErrorKind::Other, "injected replace failure"))
        });

        assert!(result.is_err());
        assert_eq!(fs::read_to_string(&path).unwrap(), "original");
        assert_eq!(fs::read_dir(&root).unwrap().count(), 1);
        fs::remove_dir_all(root).unwrap();
    }
}
