use std::fs;

use memopaws_config::config::AppConfig;

#[test]
fn missing_config_creates_defaults_and_round_trips_through_disk() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("setting.json");
    assert!(!path.exists());

    let defaults = AppConfig::load_from(&path).unwrap();
    assert_eq!(defaults.theme.as_deref(), Some("dark"));
    assert_eq!(defaults.language.as_deref(), Some("zh"));
    assert_eq!(defaults.close_behavior.as_deref(), Some("tray"));
    assert_eq!(defaults.clipboard_max_items, Some(50));
    assert!(path.exists());

    let reloaded = AppConfig::load_from(&path).unwrap();
    assert_eq!(reloaded.theme, defaults.theme);
    assert_eq!(reloaded.shortcuts, defaults.shortcuts);
}

#[test]
fn round_trip_preserves_all_user_fields() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("setting.json");

    let config = AppConfig {
        theme: Some("light".into()),
        language: Some("en".into()),
        close_behavior: Some("exit".into()),
        api_key: Some("plaintext-key".into()),
        api_url: Some("https://example.test/v1/chat/completions".into()),
        api_model: Some("vision-model".into()),
        clipboard_max_items: Some(120),
        shortcuts: Some(
            [
                ("capture".into(), "Ctrl+Shift+A".into()),
                ("toggle_clipboard".into(), "".into()),
            ]
            .into_iter()
            .collect(),
        ),
        text_replacements: vec![memopaws_config::config::TextReplacement {
            abbr: ":brb".into(),
            replacement: "be right back".into(),
        }],
    };
    config.save_to(&path).unwrap();

    let loaded = AppConfig::load_from(&path).unwrap();
    assert_eq!(
        serde_json::to_value(&loaded).unwrap(),
        serde_json::to_value(&config).unwrap()
    );
}

#[test]
fn legacy_floating_config_field_is_ignored_when_loading() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("setting.json");
    fs::write(
        &path,
        r#"{"theme":"light","show_floating_widget":false,"future_field":true}"#,
    )
    .unwrap();

    let loaded = AppConfig::load_from(&path).unwrap();
    assert_eq!(loaded.theme.as_deref(), Some("light"));
}

#[test]
fn non_standard_theme_and_language_values_are_preserved_verbatim() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("setting.json");
    fs::write(
        &path,
        r#"{"theme":"blue","language":"fr","close_behavior":"tray"}"#,
    )
    .unwrap();

    let loaded = AppConfig::load_from(&path).unwrap();
    assert_eq!(loaded.theme.as_deref(), Some("blue"));
    assert_eq!(loaded.language.as_deref(), Some("fr"));
}

#[test]
fn corrupt_config_file_errors_and_is_not_overwritten() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("setting.json");
    fs::write(&path, "{broken").unwrap();

    assert!(AppConfig::load_from(&path).is_err());
    assert_eq!(fs::read_to_string(&path).unwrap(), "{broken");
}

#[test]
fn save_overwrites_existing_file_content() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("setting.json");
    AppConfig::load_from(&path).unwrap();

    let mut config = AppConfig::default();
    config.theme = Some("light".into());
    config.save_to(&path).unwrap();

    let raw = fs::read_to_string(&path).unwrap();
    assert!(raw.contains("\"theme\": \"light\""));
    assert!(!raw.contains("\"theme\": \"dark\""));
}
