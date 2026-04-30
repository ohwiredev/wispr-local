mod python_worker;
mod settings;
mod status;

use std::sync::Arc;
use tokio::sync::Mutex;
use tauri::{
    menu::{CheckMenuItemBuilder, MenuBuilder, MenuItemBuilder, PredefinedMenuItem, SubmenuBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Listener, Manager, WindowEvent,
};
use std::path::PathBuf;

use python_worker::PythonWorker;
use settings::{WisprSettings, WHISPER_MODEL_IDS};
use status::WisprStatus;

struct AppState {
    settings: Mutex<WisprSettings>,
    status: Mutex<WisprStatus>,
    python_worker: Mutex<Option<Arc<PythonWorker>>>,
}

fn get_settings_path(app: &AppHandle) -> PathBuf {
    app.path()
        .app_local_data_dir()
        .expect("failed to get app local data dir")
        .join("config")
        .join("settings.json")
}

async fn ensure_python_worker(app: &AppHandle, state: tauri::State<'_, AppState>) -> Result<Arc<PythonWorker>, String> {
    let mut worker_guard = state.python_worker.lock().await;
    if let Some(worker) = worker_guard.as_ref() {
        return Ok(worker.clone());
    }

    let (exe_path, args, cwd) = {
        #[cfg(dev)]
        {
            let mut p = std::env::current_dir().unwrap();
            p.pop(); // go up from src-tauri to root
            let python = p.join("venv").join("Scripts").join("python.exe"); // Assume venv
            let script = p.join("app.py");
            (python, vec![script.to_string_lossy().to_string()], Some(p))
        }
        #[cfg(not(dev))]
        {
            let exe = app.path()
                .resolve(
                    "resources/wispr-backend/wispr-backend.exe",
                    tauri::path::BaseDirectory::Resource,
                )
                .expect("failed to resolve backend path");
            (exe, vec![], None)
        }
    };

    let worker = PythonWorker::spawn(app, exe_path, args, cwd).await?;
    let arc_worker = Arc::new(worker);
    
    // Send initial settings
    let current_settings = {
        let s = state.settings.lock().await;
        serde_json::to_value(&*s).unwrap()
    };
    let _ = arc_worker.request("update_settings", serde_json::json!({"settings": current_settings})).await;

    *worker_guard = Some(arc_worker.clone());
    Ok(arc_worker)
}


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
async fn get_settings(state: tauri::State<'_, AppState>) -> Result<serde_json::Value, String> {
    let s = state.settings.lock().await;
    Ok(serde_json::to_value(&*s).unwrap())
}

#[tauri::command]
async fn save_settings(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    patch: serde_json::Value,
) -> Result<(), String> {
    let mut s = state.settings.lock().await;
    let base_val = serde_json::to_value(&*s).unwrap();
    let merged_val = settings::merge_json(&base_val, &patch);
    
    let new_settings: WisprSettings = serde_json::from_value(merged_val.clone())
        .map_err(|e| format!("Invalid settings patch: {}", e))?;
    
    // Validation
    settings::validate_model(&new_settings.transcription.model)?;
    settings::validate_device(&new_settings.transcription.device)?;

    let path = get_settings_path(&app);
    settings::save_settings(&path, &new_settings)?;
    *s = new_settings;
    
    // Sync with python if worker exists
    let worker_opt = state.python_worker.lock().await.clone();
    if let Some(worker) = worker_opt {
        let _ = worker.request("update_settings", serde_json::json!({"settings": merged_val})).await;
    }

    // Refresh tray
    let current_model = s.transcription.model.clone();
    drop(s); // unlock before tray building
    let _ = rebuild_tray_menu(&app, &WHISPER_MODEL_IDS.iter().map(|s| s.to_string()).collect::<Vec<_>>(), &current_model);

    Ok(())
}

#[tauri::command]
fn get_transcription_models() -> Vec<String> {
    WHISPER_MODEL_IDS.iter().map(|s| s.to_string()).collect()
}

#[tauri::command]
async fn get_status(app: AppHandle, state: tauri::State<'_, AppState>) -> Result<serde_json::Value, String> {
    let worker = ensure_python_worker(&app, state).await?;
    worker.request("get_status", serde_json::json!({})).await
}

#[tauri::command]
async fn get_capabilities(app: AppHandle, state: tauri::State<'_, AppState>) -> Result<serde_json::Value, String> {
    let worker = ensure_python_worker(&app, state).await?;
    worker.request("get_capabilities", serde_json::json!({})).await
}

#[tauri::command]
async fn install_gpu_pack(app: AppHandle, state: tauri::State<'_, AppState>) -> Result<serde_json::Value, String> {
    let worker = ensure_python_worker(&app, state).await?;
    worker.request("install_gpu_pack", serde_json::json!({})).await
}

#[tauri::command]
async fn start_recording(app: AppHandle, state: tauri::State<'_, AppState>) -> Result<serde_json::Value, String> {
    let worker = ensure_python_worker(&app, state).await?;
    worker.request("start_recording", serde_json::json!({})).await
}

#[tauri::command]
async fn stop_recording(app: AppHandle, state: tauri::State<'_, AppState>) -> Result<serde_json::Value, String> {
    let worker = ensure_python_worker(&app, state).await?;
    worker.request("stop_recording", serde_json::json!({})).await
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
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            toggle_dashboard,
            update_tray_models,
            get_settings,
            save_settings,
            get_transcription_models,
            get_status,
            get_capabilities,
            install_gpu_pack,
            start_recording,
            stop_recording
        ])
        .setup(|app| {
            let settings_path = get_settings_path(app.handle());
            let initial_settings = settings::load_settings(&settings_path);

            app.manage(AppState {
                settings: Mutex::new(initial_settings.clone()),
                status: Mutex::new(WisprStatus::default()),
                python_worker: Mutex::new(None),
            });
            
            // Listen to status updates
            let app_handle_for_listener = app.handle().clone();
            app.listen("wispr-status-update", move |event| {
                if let Ok(new_status) = serde_json::from_str::<WisprStatus>(event.payload()) {
                    let app_handle = app_handle_for_listener.clone();
                    tauri::async_runtime::spawn(async move {
                        let state: tauri::State<'_, AppState> = app_handle.state();
                        let mut s = state.status.lock().await;
                        *s = new_status;
                    });
                }
            });

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
                            let state: tauri::State<'_, AppState> = app_handle.state();
                            let patch = serde_json::json!({
                                "transcription": {"model": model}
                            });
                            let _ = save_settings(app_handle.clone(), state, patch).await;
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
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|_app_handle, _event| {
        if let tauri::RunEvent::Exit = _event {
            let app_handle = _app_handle.clone();
            tauri::async_runtime::spawn(async move {
                let state: tauri::State<'_, AppState> = app_handle.state();
                let worker_guard = state.python_worker.lock().await;
                if let Some(worker) = worker_guard.as_ref() {
                    worker.shutdown().await;
                }
            });
        }
    });
}
