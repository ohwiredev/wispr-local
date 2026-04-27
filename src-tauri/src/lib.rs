use tauri::{
    menu::{CheckMenuItemBuilder, MenuBuilder, MenuItemBuilder, PredefinedMenuItem, SubmenuBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, WindowEvent,
};
use tauri_plugin_shell::ShellExt;

const API_BASE: &str = "http://127.0.0.1:8001";

#[tauri::command]
fn toggle_dashboard(app: AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let visible = window.is_visible().unwrap_or(false);
        if visible {
            let _ = window.hide();
        } else {
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

#[tauri::command]
async fn update_tray_models(
    app: AppHandle,
    models: Vec<String>,
    current_model: String,
) -> Result<(), String> {
    rebuild_tray_menu(&app, &models, &current_model).map_err(|e| e.to_string())
}

fn rebuild_tray_menu(
    app: &AppHandle,
    models: &[String],
    current_model: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut submenu = SubmenuBuilder::new(app, "Model");
    for model in models {
        let item = CheckMenuItemBuilder::new(model)
            .id(format!("model:{}", model))
            .checked(model == current_model)
            .build(app)?;
        submenu = submenu.item(&item);
    }
    let models_submenu = submenu.build()?;

    let sep = PredefinedMenuItem::separator(app)?;
    let quit = MenuItemBuilder::new("Quit").id("quit").build(app)?;

    let menu = MenuBuilder::new(app)
        .item(&models_submenu)
        .item(&sep)
        .item(&quit)
        .build()?;

    if let Some(tray) = app.tray_by_id("main_tray") {
        tray.set_menu(Some(menu))?;
    }
    Ok(())
}

fn show_dashboard(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![toggle_dashboard, update_tray_models])
        .setup(|app| {
            #[cfg(not(dev))]
            {
                let resource_path = app
                    .path()
                    .resolve(
                        "resources/wispr-backend/wispr-backend.exe",
                        tauri::path::BaseDirectory::Resource,
                    )
                    .expect("failed to resolve backend path");

                let sidecar_command = app.shell().command(resource_path.to_str().unwrap());
                let (_rx, _child) = sidecar_command.spawn().expect("failed to spawn backend");
            }

            let quit = MenuItemBuilder::new("Quit").id("quit").build(app)?;
            let menu = MenuBuilder::new(app).item(&quit).build()?;

            let _tray = TrayIconBuilder::with_id("main_tray")
                .icon(
                    app.default_window_icon()
                        .expect("failed to get default window icon")
                        .clone(),
                )
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| {
                    let id = event.id().as_ref();
                    if id == "quit" {
                        app.exit(0);
                    } else if let Some(model_name) = id.strip_prefix("model:") {
                        let model = model_name.to_string();
                        let app_handle = app.clone();
                        tauri::async_runtime::spawn(async move {
                            let client = reqwest::Client::new();
                            let _ = client
                                .post(format!("{}/settings", API_BASE))
                                .json(&serde_json::json!({
                                    "transcription": {"model": model}
                                }))
                                .send()
                                .await;
                            // Emit event so frontend refreshes settings and updates tray
                            let _ = app_handle.emit("tray-model-changed", ());
                        });
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_dashboard(tray.app_handle());
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "main" {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
