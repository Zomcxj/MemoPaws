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
