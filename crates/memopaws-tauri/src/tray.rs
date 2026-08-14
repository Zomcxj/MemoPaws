use tauri::{
    Manager,
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
};

use crate::commands::{self, KeyVaultState};

pub fn setup_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let is_english = memopaws_config::config::AppConfig::load().ok().and_then(|config| config.language).as_deref() == Some("en");
    let (show_main_text, hide_main_text, show_floating_text, hide_floating_text, quit_text) = if is_english {
        ("Show Main Window", "Hide Main Window", "Show Floating Widget", "Hide Floating Widget", "Exit")
    } else {
        ("显示主窗口", "隐藏主窗口", "显示悬浮窗", "隐藏悬浮窗", "退出")
    };
    let show_main = MenuItemBuilder::with_id("show-main", show_main_text).build(app)?;
    let hide_main = MenuItemBuilder::with_id("hide-main", hide_main_text).build(app)?;
    let show_floating = MenuItemBuilder::with_id("show-floating", show_floating_text).build(app)?;
    let hide_floating = MenuItemBuilder::with_id("hide-floating", hide_floating_text).build(app)?;
    let quit = MenuItemBuilder::with_id("quit", quit_text).build(app)?;

    let menu = MenuBuilder::new(app)
        .items(&[&show_main, &hide_main, &show_floating, &hide_floating, &quit])
        .build()?;
    let icon = app
        .default_window_icon()
        .cloned()
        .ok_or(tauri::Error::AssetNotFound("default window icon".into()))?;

    let _tray = TrayIconBuilder::new()
        .icon(icon)
        .menu(&menu)
        .on_menu_event(move |app, event| match event.id().as_ref() {
            "show-main" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "hide-main" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.hide();
                }
            }
            "show-floating" => {
                let _ = commands::set_floating_widget_visible(true, app.clone());
            }
            "hide-floating" => {
                let _ = commands::set_floating_widget_visible(false, app.clone());
            }
            "quit" => {
                commands::lock_vault_state(&app.state::<KeyVaultState>());
                app.exit(0);
            }
            _ => {}
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
    fn default_capability_allows_positioning_main_and_floating_windows() {
        let capability = include_str!("../capabilities/default.json");
        let capability: serde_json::Value = serde_json::from_str(capability).unwrap();

        assert_eq!(capability["windows"], serde_json::json!(["main", "floating"]));
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
                "core:window:allow-set-fullscreen",
                "core:window:allow-set-position",
                "core:window:allow-set-size",
                "shell:allow-open",
            ]
        );
    }

    #[test]
    fn tray_uses_the_default_window_icon() {
        let source = include_str!("tray.rs").split("#[cfg(test)]").next().unwrap();

        assert!(source.contains("app\n        .default_window_icon()\n        .cloned()\n        .ok_or("));
        assert!(source.contains(".icon(icon)"));
    }
}
