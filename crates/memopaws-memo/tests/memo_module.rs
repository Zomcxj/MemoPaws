use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use memopaws_memo::migrate::migrate_legacy_memos;
use memopaws_memo::model::Memo;
use memopaws_memo::renderer::{render_markdown, RenderTheme};
use memopaws_memo::search::search_memos;
use memopaws_memo::storage::{
    build_frontmatter, create_memo, delete_memo, list_memos, parse_frontmatter, read_memo,
    safe_memo_path, sanitize_filename, update_memo, MemoError,
};

struct TestDir(PathBuf);

impl TestDir {
    fn new(name: &str) -> Self {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("memopaws-{name}-{unique}"));
        fs::create_dir_all(&path).unwrap();
        Self(path)
    }

    fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TestDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn memo(id: i64, title: &str, content: &str, modified: &str) -> Memo {
    Memo {
        id,
        time: modified.into(),
        created: "2026-01-01 10:00:00".into(),
        modified: modified.into(),
        title: title.into(),
        content: content.into(),
        tags: vec!["工作".into(), "rust".into()],
        file: None,
    }
}

#[test]
fn model_serializes_python_file_field() {
    let mut value = memo(1, "Title", "Body", "2026-01-01 10:00:00");
    value.file = Some("Title_1.md".into());
    let json = serde_json::to_value(value).unwrap();
    assert_eq!(json["_file"], "Title_1.md");
    assert!(json.get("file").is_none());
}

#[test]
fn filename_and_path_stay_inside_memo_directory() {
    let dir = TestDir::new("paths");
    assert_eq!(sanitize_filename("a/b:*?", 7), "a_b_7.md");
    assert!(safe_memo_path(dir.path(), "../outside.md").is_err());
    assert!(safe_memo_path(dir.path(), "nested/memo.md").is_err());
    assert!(safe_memo_path(dir.path(), "valid.md").is_ok());
}

#[test]
fn frontmatter_round_trips_simplified_yaml() {
    let value = memo(9, "标题: 保留", "第一行\n第二行", "2026-02-03 04:05:06");
    let text = build_frontmatter(&value);
    let (metadata, content) = parse_frontmatter(&(text + &value.content)).unwrap();
    assert_eq!(metadata.title, "标题: 保留");
    assert_eq!(metadata.tags, vec!["工作", "rust"]);
    assert_eq!(content, "第一行\n第二行");
}

#[test]
fn crud_scans_markdown_and_sorts_by_modified_descending() {
    let dir = TestDir::new("crud");
    let first = create_memo(dir.path(), memo(10, "First", "old", "2026-01-01 10:00:00")).unwrap();
    let second = create_memo(dir.path(), memo(11, "Second", "new", "2026-02-01 10:00:00")).unwrap();

    assert_eq!(list_memos(dir.path()).unwrap()[0].id, second.id);
    assert_eq!(read_memo(dir.path(), first.id).unwrap().content, "old");

    let mut changed = first.clone();
    changed.title = "Renamed".into();
    changed.content = "updated".into();
    changed.modified = "2026-03-01 10:00:00".into();
    let changed = update_memo(dir.path(), changed).unwrap();
    assert_eq!(read_memo(dir.path(), changed.id).unwrap().content, "updated");
    assert_eq!(changed.file, first.file);
    assert!(dir.path().join(first.file.unwrap()).exists());
    assert_eq!(list_memos(dir.path()).unwrap()[0].title, "Renamed");

    delete_memo(dir.path(), second.id).unwrap();
    assert!(read_memo(dir.path(), second.id).is_err());
    assert!(fs::read_dir(dir.path()).unwrap().all(|entry| {
        let name = entry.unwrap().file_name().to_string_lossy().into_owned();
        !name.contains(".tmp")
    }));
}

#[test]
fn create_ignores_external_filename_and_never_overwrites() {
    let dir = TestDir::new("create-safety");
    fs::write(dir.path().join("Injected_99.md"), "keep").unwrap();
    let mut value = memo(20, "Safe", "new", "2026-01-01");
    value.file = Some("Injected_99.md".into());

    let created = create_memo(dir.path(), value).unwrap();
    assert_eq!(created.file.as_deref(), Some("Safe_20.md"));
    assert_eq!(fs::read_to_string(dir.path().join("Injected_99.md")).unwrap(), "keep");

    fs::write(dir.path().join("Blocked_21.md"), "occupied").unwrap();
    let error = create_memo(dir.path(), memo(21, "Blocked", "new", "2026-01-01")).unwrap_err();
    assert!(matches!(error, MemoError::Conflict(_)));
    assert_eq!(fs::read_to_string(dir.path().join("Blocked_21.md")).unwrap(), "occupied");
}

#[test]
fn update_keeps_existing_filename_when_title_changes() {
    let dir = TestDir::new("update-filename");
    let original = create_memo(dir.path(), memo(30, "Original", "old", "2026-01-01")).unwrap();
    let mut renamed = original.clone();
    renamed.title = "Renamed".into();
    renamed.content = "new".into();
    let updated = update_memo(dir.path(), renamed).unwrap();

    assert_eq!(updated.file, original.file);
    assert!(!dir.path().join("Renamed_30.md").exists());
    assert_eq!(read_memo(dir.path(), 30).unwrap().content, "new");
}

#[test]
fn incomplete_frontmatter_is_plain_markdown_and_bad_utf8_is_isolated() {
    let dir = TestDir::new("frontmatter-tolerance");
    let ordinary = "---\nThis is a horizontal rule followed by Markdown";
    let (metadata, content) = parse_frontmatter(ordinary).unwrap();
    assert_eq!(metadata, Default::default());
    assert_eq!(content, ordinary);

    fs::write(dir.path().join("Ordinary_40.md"), ordinary).unwrap();
    fs::write(dir.path().join("Broken_41.md"), [0xff, 0xfe, 0xfd]).unwrap();
    let values = list_memos(dir.path()).unwrap();
    assert_eq!(values.len(), 1);
    assert_eq!(values[0].content, ordinary);
}

#[test]
fn migration_preserves_existing_files_and_backs_up_json() {
    let root = TestDir::new("migration");
    let memo_dir = root.path().join("memo");
    fs::create_dir_all(&memo_dir).unwrap();
    let existing = Memo {
        id: 1,
        time: "old".into(),
        created: "old".into(),
        modified: "old".into(),
        title: "Existing".into(),
        content: "replace".into(),
        tags: vec![],
        file: Some("Existing_1.md".into()),
    };
    let existing_text = build_frontmatter(&existing) + &existing.content;
    fs::write(memo_dir.join("Existing_1.md"), &existing_text).unwrap();
    let legacy = root.path().join("memo.json");
    fs::write(
        &legacy,
        r#"[{"id":1,"time":"old","created":"old","modified":"old","title":"Existing","content":"replace","tags":[],"_file":"Existing_1.md"},{"id":2,"time":"old","created":"old","modified":"old","title":"New","content":"migrated","tags":[],"_file":"Legacy Custom_2.md"}]"#,
    )
    .unwrap();

    assert_eq!(migrate_legacy_memos(&legacy, &memo_dir).unwrap(), 1);
    assert_eq!(fs::read_to_string(memo_dir.join("Existing_1.md")).unwrap(), existing_text);
    assert!(!legacy.exists());
    assert!(root.path().join("memo.json.migrated").exists());
    assert!(memo_dir.join("Legacy Custom_2.md").exists());
    assert_eq!(read_memo(&memo_dir, 2).unwrap().content, "migrated");
}

#[test]
fn migration_rejects_duplicate_ids_without_backing_up_source() {
    let root = TestDir::new("migration-duplicate-id");
    let memo_dir = root.path().join("memo");
    let legacy = root.path().join("memo.json");
    fs::write(&legacy, r#"[{"id":1,"title":"One","content":"a"},{"id":1,"title":"Two","content":"b"}]"#).unwrap();

    let error = migrate_legacy_memos(&legacy, &memo_dir).unwrap_err();
    assert!(matches!(error, MemoError::Conflict(_)));
    assert!(legacy.exists());
    assert!(!root.path().join("memo.json.migrated").exists());
}

#[test]
fn migration_rejects_same_filename_with_different_content_and_can_retry() {
    let root = TestDir::new("migration-retry");
    let memo_dir = root.path().join("memo");
    fs::create_dir_all(&memo_dir).unwrap();
    let legacy = root.path().join("memo.json");
    fs::write(&legacy, r#"[{"id":2,"title":"Same","content":"legacy","_file":"Same_2.md"}]"#).unwrap();
    fs::write(memo_dir.join("Same_2.md"), "different").unwrap();

    let error = migrate_legacy_memos(&legacy, &memo_dir).unwrap_err();
    assert!(matches!(error, MemoError::Conflict(_)));
    assert!(legacy.exists());

    fs::remove_file(memo_dir.join("Same_2.md")).unwrap();
    assert_eq!(migrate_legacy_memos(&legacy, &memo_dir).unwrap(), 1);
    assert!(root.path().join("memo.json.migrated").exists());
}

#[test]
fn migration_uses_non_conflicting_backup_and_accepts_equivalent_existing_memo() {
    let root = TestDir::new("migration-backup");
    let memo_dir = root.path().join("memo");
    fs::create_dir_all(&memo_dir).unwrap();
    let legacy = root.path().join("memo.json");
    let value = memo(3, "Existing", "same", "2026-01-01");
    fs::write(memo_dir.join("Existing_3.md"), build_frontmatter(&value) + "same").unwrap();
    fs::write(&legacy, serde_json::to_vec(&vec![value]).unwrap()).unwrap();
    fs::write(root.path().join("memo.json.migrated"), "older backup").unwrap();

    assert_eq!(migrate_legacy_memos(&legacy, &memo_dir).unwrap(), 0);
    assert_eq!(fs::read_to_string(root.path().join("memo.json.migrated")).unwrap(), "older backup");
    assert!(root.path().join("memo.json.migrated.1").exists());
}

#[test]
fn search_supports_substrings_initials_fuzzy_words_and_line_numbers() {
    let values = vec![
        memo(1, "会议记录", "第一行\nRust ownership notes", "2026-01-01"),
        memo(2, "English", "nothing", "2026-01-02"),
    ];
    assert_eq!(search_memos(&values, "hyjl")[0].memo.id, 1);
    assert_eq!(search_memos(&values, "ownershp")[0].line_number, 2);
    assert_eq!(search_memos(&values, "工作")[0].line_number, 1);
    assert!(search_memos(&values, "onw").is_empty());
    assert_eq!(search_memos(&values, "").len(), 2);
}

#[test]
fn renderer_supports_extensions_themes_and_escapes_raw_html() {
    let markdown = "~~gone~~\n\n|a|b|\n|-|-|\n|1|2|\n\n- [x] task\n\nfootnote[^1]\n\n[^1]: note\n\n<script>alert(1)</script>";
    let html = render_markdown(markdown, RenderTheme::Dark);
    assert!(html.contains("<del>gone</del>"));
    assert!(html.contains("<table>"));
    assert!(html.contains("task-list-item"));
    assert!(html.contains("footnote"));
    assert!(html.contains("memo-markdown dark"));
    assert!(!html.to_ascii_lowercase().contains("<script"));
    assert!(html.contains("&lt;script&gt;"));
    assert!(render_markdown("text", RenderTheme::Light).contains("memo-markdown light"));
}

#[test]
fn renderer_highlights_known_fenced_code_and_escapes_unknown_code() {
    let highlighted = render_markdown("```rust\nfn main() { let answer = 42; }\n```", RenderTheme::Dark);
    assert!(highlighted.contains("<span style=\""));
    assert!(highlighted.contains("fn"));
    assert!(highlighted.contains("color:"));
    assert!(highlighted.contains("--memo-code:#2b2b2b"));
    assert!(!highlighted.contains("<pre class=\"memo-code\" style=\"background-color:"));

    let fallback = render_markdown("```not-a-language\n<script>alert(1)</script>\n```", RenderTheme::Light);
    assert!(!fallback.to_ascii_lowercase().contains("<script"));
    assert!(fallback.contains("&lt;script&gt;"));
}

#[test]
fn renderer_filters_unsafe_link_and_image_protocols() {
    let markdown = "[bad](javascript:alert(1)) ![bad](data:text/html,boom) [file](file:///tmp/a) [web](https://example.com) [mail](mailto:a@example.com) [relative](docs/page) [fragment](#part)";
    let html = render_markdown(markdown, RenderTheme::Light);

    assert!(!html.to_ascii_lowercase().contains("javascript:"));
    assert!(!html.to_ascii_lowercase().contains("data:text"));
    assert!(!html.to_ascii_lowercase().contains("file:///"));
    assert!(!html.contains("href=\"\""));
    assert!(!html.contains("src=\"\""));
    assert!(html.contains("href=\"https://example.com\""));
    assert!(html.contains("href=\"mailto:a@example.com\""));
    assert!(html.contains("href=\"docs/page\""));
    assert!(html.contains("href=\"#part\""));
}

#[test]
fn renderer_uses_vscode_dark_plus_palette_typography_and_core_markup_styles() {
    let markdown = "# Title\n\nParagraph with `inline`.\n\n- item\n\n> quote\n\n```rust\nfn main() {}\n```\n\n| a | b |\n| - | - |\n| 1 | 2 |\n\n---\n\n- [x] done\n\n![image](https://example.com/image.png)";
    let html = render_markdown(markdown, RenderTheme::Dark);

    for value in [
        "--memo-bg:#1e1e1e",
        "--memo-fg:#d4d4d4",
        "--memo-link:#3794ff",
        "--memo-code:#2b2b2b",
        "--memo-inline-code:#ce9178",
        "--memo-text:14px",
        "line-height: 1.6",
        "font-family: system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif",
        "font-family: Consolas, Monaco, \"Courier New\", monospace",
        ".memo-markdown h1",
        ".memo-markdown p",
        ".memo-markdown ul",
        ".memo-markdown blockquote",
        ".memo-markdown pre.memo-code",
        ".memo-markdown code",
        ".memo-markdown table",
        ".memo-markdown hr",
        ".memo-markdown .task-list-item",
        ".memo-markdown img",
    ] {
        assert!(html.contains(value), "missing {value}");
    }
    assert!(html.contains("memo-markdown dark"));
    assert!(html.contains("<h1"));
    assert!(html.contains("<p>Paragraph with <code>inline</code>"));
    assert!(html.contains("<ul>"));
    assert!(html.contains("<blockquote"));
    assert!(html.contains("memo-code"));
    assert!(html.contains("<table>"));
    assert!(html.contains("<hr"));
    assert!(html.contains("task-list-item"));
    assert!(html.contains("<img src=\"https://example.com/image.png\""));
}

#[test]
fn renderer_styles_lists_quotes_rules_and_task_checked_state() {
    let md = "> quote\n\n---\n\n1. one\n\n- [x] done\n- [ ] todo\n";
    let html = render_markdown(md, RenderTheme::Light);
    assert!(html.contains("<blockquote"));
    assert!(html.contains("<hr"));
    assert!(html.contains("<ol") || html.contains("<li>one"));
    assert!(html.contains("task-list-item"));
    assert!(html.contains("type=\"checkbox\"") || html.contains("type='checkbox'"));
    assert!(html.contains("memo-markdown light"));
    assert!(html.contains("--memo-link:"));
    assert!(html.contains(".memo-markdown a"));
}

#[test]
fn renderer_code_block_wrapped_as_memo_code() {
    let html = render_markdown("```rust\nfn main() {}\n```", RenderTheme::Dark);
    assert!(html.contains("memo-code"));
    assert!(html.contains("fn") || html.contains("main"));
}

#[test]
fn renderer_adds_safe_copy_controls_to_fenced_code_only() {
    let html = render_markdown("Inline `code`.\n\n```rust\nfn main() {}\n```", RenderTheme::Dark);

    assert!(html.contains("class=\"memo-code-block\""));
    assert!(html.contains("class=\"memo-code-copy\""));
    assert!(html.contains("data-memo-code-copy"));
    assert!(html.contains("<code>code</code>"));
    assert!(!html.contains("onclick="));
}
