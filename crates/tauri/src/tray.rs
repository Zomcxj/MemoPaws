use tauri::{
    Manager,
    menu::{IsMenuItem, MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
};

use crate::commands::{self, KeyVaultState};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum TrayAction {
    ShowMain,
    HideMain,
    Quit,
}

/// The tray menu, as data: `(menu id, action, English label, Chinese label)`.
///
/// Both the menu build and the click handler read from this table, and the
/// handler matches on `TrayAction` rather than on id strings. An action can
/// therefore neither be shown without being handled nor handled without being
/// shown, and the ids stay assertable without a running app.
const TRAY_ITEMS: &[(&str, TrayAction, &str, &str)] = &[
    ("show-main", TrayAction::ShowMain, "Show Main Window", "显示主窗口"),
    ("hide-main", TrayAction::HideMain, "Hide Main Window", "隐藏主窗口"),
    ("quit", TrayAction::Quit, "Exit", "退出"),
];

fn tray_action(id: &str) -> Option<TrayAction> {
    TRAY_ITEMS
        .iter()
        .find(|(item_id, ..)| *item_id == id)
        .map(|(_, action, ..)| *action)
}

pub fn setup_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let is_english = memopaws_config::config::AppConfig::load().ok().and_then(|config| config.language).as_deref() == Some("en");
    let items = TRAY_ITEMS
        .iter()
        .map(|(id, _, english, chinese)| {
            MenuItemBuilder::with_id(*id, if is_english { *english } else { *chinese }).build(app)
        })
        .collect::<tauri::Result<Vec<_>>>()?;

    let refs: Vec<&dyn IsMenuItem<tauri::Wry>> =
        items.iter().map(|item| item as &dyn IsMenuItem<tauri::Wry>).collect();
    let menu = MenuBuilder::new(app).items(&refs).build()?;
    let icon = app
        .default_window_icon()
        .cloned()
        .ok_or(tauri::Error::AssetNotFound("default window icon".into()))?;

    let _tray = TrayIconBuilder::new()
        .icon(icon)
        .menu(&menu)
        .on_menu_event(move |app, event| {
            let Some(action) = tray_action(event.id().as_ref()) else { return };
            match action {
                TrayAction::ShowMain => {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
                TrayAction::HideMain => {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.hide();
                    }
                }
                TrayAction::Quit => {
                    commands::lock_vault_state(&app.state::<KeyVaultState>());
                    app.exit(0);
                }
            }
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
        })
        .build(app)?;

    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn default_capability_allows_only_the_main_window() {
        let capability = include_str!("../capabilities/default.json");
        let capability: serde_json::Value = serde_json::from_str(capability).unwrap();

        assert_eq!(capability["windows"], serde_json::json!(["main"]));
        let mut permissions: Vec<_> = capability["permissions"]
            .as_array()
            .unwrap()
            .iter()
            .map(|permission| permission.as_str().unwrap())
            .collect();
        permissions.sort_unstable();

        assert_eq!(
            permissions,
            [
                "core:default",
                "core:window:allow-hide",
                "core:window:allow-minimize",
                "core:window:allow-set-fullscreen",
                "core:window:allow-set-position",
                "core:window:allow-set-size",
                "core:window:allow-show",
                "shell:allow-open",
            ]
        );
    }

    #[test]
    fn every_menu_id_resolves_to_its_action_and_has_both_labels() {
        use super::{TrayAction, TRAY_ITEMS};

        let ids: Vec<_> = TRAY_ITEMS.iter().map(|(id, ..)| *id).collect();
        assert_eq!(ids, ["show-main", "hide-main", "quit"]);

        for (id, action, english, chinese) in TRAY_ITEMS {
            assert_eq!(super::tray_action(id), Some(*action), "id {id} must resolve");
            assert!(!english.is_empty() && !chinese.is_empty(), "id {id} needs both labels");
            assert_ne!(english, chinese, "id {id} label was left untranslated");
        }

        let actions: Vec<_> = TRAY_ITEMS.iter().map(|(_, action, ..)| *action).collect();
        assert_eq!(actions, [TrayAction::ShowMain, TrayAction::HideMain, TrayAction::Quit]);
    }

    #[test]
    fn removed_and_unknown_menu_ids_resolve_to_nothing() {
        // The floating widget was removed; its menu ids must not come back.
        assert_eq!(super::tray_action("show-floating"), None);
        assert_eq!(super::tray_action("hide-floating"), None);
        assert_eq!(super::tray_action(""), None);
        assert_eq!(super::tray_action("Show-Main"), None, "ids are case-sensitive");
    }
}
