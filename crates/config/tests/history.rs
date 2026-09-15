use memopaws_config::history::HistoryManager;

#[test]
fn history_round_trips_compatible_records_and_trims_atomically() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("history.json");
    let mut manager = HistoryManager::with_path(&path, 2).unwrap();
    manager.add_success("ocr", "one", Some("one"), None).unwrap();
    manager.add_success("translate", "two", Some("source"), Some("译文")).unwrap();
    manager.add_success("ocr", "three", Some("three"), None).unwrap();

    let loaded = HistoryManager::with_path(&path, 2).unwrap();
    assert_eq!(loaded.records().len(), 2);
    assert_eq!(loaded.records()[0].text, "three");
    assert_eq!(loaded.records()[1].translate_text.as_deref(), Some("译文"));
    let json: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    assert_eq!(json[0]["type"], "ocr");
    assert!(directory.path().read_dir().unwrap().all(|entry| !entry.unwrap().file_name().to_string_lossy().contains(".tmp")));
}

#[test]
fn legacy_extra_fields_load_and_delete_and_clear_are_saved() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("history.json");
    std::fs::write(&path, r#"[{"type":"识别(AI)","text":"old","time":"2025-01-01 00:00:00","ocr_text":"old","legacy":true}]"#).unwrap();
    let mut manager = HistoryManager::with_path(&path, 100).unwrap();
    assert_eq!(manager.records()[0].ocr_text.as_deref(), Some("old"));
    manager.delete_record(0).unwrap();
    assert!(HistoryManager::with_path(&path, 100).unwrap().records().is_empty());
    manager.add_success("ocr", "new", Some("new"), None).unwrap();
    manager.clear().unwrap();
    assert!(HistoryManager::with_path(path, 100).unwrap().records().is_empty());
}

#[test]
fn corrupted_history_file_errors_without_destroying_the_file() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("history.json");
    std::fs::write(&path, "[{broken").unwrap();

    assert!(HistoryManager::with_path(&path, 100).is_err());
    assert_eq!(std::fs::read_to_string(&path).unwrap(), "[{broken");
}

#[test]
fn add_success_truncates_every_long_field_and_delete_out_of_range_is_a_noop() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("history.json");
    let mut manager = HistoryManager::with_path(&path, 100).unwrap();

    let long_text = "x".repeat(6000);
    let long_ocr = "y".repeat(6000);
    let long_translate = "z".repeat(6000);
    manager.add_success("ocr", &long_text, Some(&long_ocr), Some(&long_translate)).unwrap();
    assert_eq!(manager.records()[0].text.chars().count(), 5000);
    assert_eq!(manager.records()[0].ocr_text.as_ref().unwrap().chars().count(), 5000);
    assert_eq!(manager.records()[0].translate_text.as_ref().unwrap().chars().count(), 5000);

    // Truncation counts characters, not bytes, so multi-byte text is never split mid-codepoint.
    let long_multibyte = "译".repeat(6000);
    manager.add_success("translate", &long_multibyte, Some(&long_multibyte), Some(&long_multibyte)).unwrap();
    assert_eq!(manager.records()[0].text.chars().count(), 5000);
    assert_eq!(manager.records()[0].ocr_text.as_ref().unwrap().chars().count(), 5000);
    assert_eq!(manager.records()[0].translate_text.as_ref().unwrap().chars().count(), 5000);
    manager.delete_record(0).unwrap();

    manager.delete_record(99).unwrap();
    manager.delete_record(0).unwrap();
    assert!(manager.records().is_empty());
    assert!(HistoryManager::with_path(&path, 100).unwrap().records().is_empty());
}

#[test]
fn missing_history_file_starts_empty_and_max_items_controls_retention() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("history.json");
    let mut manager = HistoryManager::with_path(&path, 2).unwrap();
    assert!(manager.records().is_empty());
    assert_eq!(manager.max_items(), 2);

    for index in 0..4 {
        manager.add_record("test", format!("record-{index}")).unwrap();
    }
    assert_eq!(manager.records().len(), 2);
    assert_eq!(manager.records()[0].text, "record-3");
    assert_eq!(manager.into_records().len(), 2);
}
