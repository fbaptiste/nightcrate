#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod links;
mod selftest;

use backend::{Backend, Output, StartFailure};
use selftest::{Mode, SelfTest};
use std::sync::{Arc, Mutex};
use std::thread;
use tauri::ipc::CapabilityBuilder;
#[cfg(test)]
use tauri::ipc::RuntimeCapability;
use tauri::menu::{MenuBuilder, SubmenuBuilder};
use tauri::webview::PageLoadEvent;
use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent};

struct BackendSlot(Mutex<Option<Arc<Backend>>>);

fn selftest_mode() -> Result<Mode, String> {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    if let Some(index) = arguments.iter().position(|value| value == "--selftest-fresh") {
        let path = arguments
            .get(index + 1)
            .ok_or("--selftest-fresh requires a workspace directory")?;
        return Ok(Mode::Fresh(path.clone()));
    }
    if arguments.iter().any(|value| value == "--selftest-configured") {
        return Ok(Mode::Configured);
    }
    Ok(Mode::Off)
}

fn capability_spec(port: u16, selftest: bool) -> (String, Vec<&'static str>) {
    let mut permissions = vec![
        "core:event:allow-listen",
        "core:event:allow-unlisten",
        "allow-install-update",
    ];
    if selftest {
        permissions.push("allow-selftest-report");
    }
    (format!("http://127.0.0.1:{port}/*"), permissions)
}

fn main_capability(port: u16, selftest: bool) -> CapabilityBuilder {
    let (origin, permissions) = capability_spec(port, selftest);
    permissions.into_iter().fold(
        CapabilityBuilder::new("main-window")
            .remote(origin)
            .local(false)
            .window("main"),
        |capability, permission| capability.permission(permission),
    )
}

#[tauri::command]
fn open_log_folder(app: AppHandle) -> Result<(), String> {
    let directory = backend::log_dir(&app)?;
    links::open_path(&directory);
    Ok(())
}

#[tauri::command]
fn install_update() -> Result<(), String> {
    Err("Updates are not enabled in this build.".to_owned())
}

fn loading_status(app: &AppHandle, message: &str) {
    if let Some(window) = app.get_webview_window("loading") {
        let message = serde_json::to_string(message).unwrap();
        let _ = window.eval(format!("window.nightcrateLoading.status({message})"));
    }
}

fn loading_failure(app: &AppHandle, failure: &StartFailure) {
    let (title, message, show_lines) = match (failure.exit_code, failure.locked_kind.as_deref()) {
        (Some(3), Some("source")) => (
            "NightCrate is already running",
            "NightCrate is already running from source code on this computer. Stop it, then open NightCrate again.",
            false,
        ),
        (Some(4), _) => (
            "NightCrate couldn't start",
            "NightCrate couldn't find a free port (8765–8775). Close the program using it, then open NightCrate again.",
            false,
        ),
        _ => (
            "NightCrate couldn't start",
            failure.reason.as_str(),
            true,
        ),
    };
    let title = serde_json::to_string(title).unwrap();
    let message = serde_json::to_string(message).unwrap();
    let lines = if show_lines {
        failure.last_lines.join("\n")
    } else {
        String::new()
    };
    let lines = serde_json::to_string(&lines).unwrap();
    if let Some(window) = app.get_webview_window("loading") {
        let _ = window.eval(format!(
            "window.nightcrateLoading.failure({title},{message},{lines})"
        ));
    }
    eprintln!(
        "[shell] {}: {}",
        failure.reason,
        failure.last_lines.join(" | ")
    );
    if let Some(exit_code) = app.state::<SelfTest>().start_failure_exit_code() {
        let backend = app.state::<BackendSlot>().0.lock().unwrap().take();
        if let Some(backend) = backend {
            backend.stop();
        }
        app.exit(exit_code);
    }
}

fn create_main(app: &AppHandle, port: u16, selftest: bool) -> Result<(), String> {
    app.add_capability(main_capability(port, selftest))
        .map_err(|error| error.to_string())?;
    let url = format!("http://127.0.0.1:{port}/")
        .parse()
        .map_err(|error| format!("invalid backend URL: {error}"))?;
    let builder = WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
        .title("NightCrate")
        .inner_size(1400.0, 900.0)
        .min_inner_size(1024.0, 700.0)
        .disable_drag_drop_handler()
        .zoom_hotkeys_enabled(true);
    let _window = links::configure_main(builder, app, port)
        .build()
        .map_err(|error| error.to_string())?;
    #[cfg(feature = "test-devtools")]
    {
        _window.open_devtools();
    }
    if let Some(loading) = app.get_webview_window("loading") {
        let _ = loading.hide();
    }
    Ok(())
}

fn start_backend(app: AppHandle) {
    let (backend, receiver) = match Backend::spawn(&app) {
        Ok(value) => value,
        Err(reason) => {
            loading_failure(
                &app,
                &StartFailure {
                    exit_code: None,
                    locked_kind: None,
                    last_lines: Vec::new(),
                    reason,
                },
            );
            return;
        }
    };
    *app.state::<BackendSlot>().0.lock().unwrap() = Some(Arc::clone(&backend));
    let result = backend.wait_until_ready(&receiver, |output| {
        if let Output::Step(step) = output {
            let message = match step.step.as_str() {
                "backing_up" => format!(
                    "Backing up {}…",
                    step.workspace.as_deref().unwrap_or("workspace")
                ),
                "upgrading" => format!(
                    "Upgrading {}…",
                    step.workspace.as_deref().unwrap_or("workspace")
                ),
                _ => "Starting NightCrate…".to_owned(),
            };
            loading_status(&app, &message);
        }
    });
    match result {
        Ok(port) => {
            let selftest = app.state::<SelfTest>().enabled();
            if let Err(reason) = create_main(&app, port, selftest) {
                loading_failure(
                    &app,
                    &StartFailure {
                        exit_code: None,
                        locked_kind: None,
                        last_lines: Vec::new(),
                        reason,
                    },
                );
            }
        }
        Err(failure) => loading_failure(&app, &failure),
    }
}

#[cfg(target_os = "macos")]
fn install_edit_menu(app: &tauri::App) -> tauri::Result<()> {
    let application = SubmenuBuilder::new(app, "NightCrate").quit().build()?;
    let edit = SubmenuBuilder::new(app, "Edit")
        .undo()
        .redo()
        .separator()
        .cut()
        .copy()
        .paste()
        .select_all()
        .build()?;
    let menu = MenuBuilder::new(app).item(&application).item(&edit).build()?;
    app.set_menu(menu)?;
    Ok(())
}

#[cfg(not(target_os = "macos"))]
fn install_edit_menu(_app: &tauri::App) -> tauri::Result<()> {
    Ok(())
}

fn main() {
    let mode = selftest_mode().unwrap_or_else(|error| {
        eprintln!("{error}");
        std::process::exit(2);
    });
    let app = tauri::Builder::default()
        .manage(BackendSlot(Mutex::new(None)))
        .manage(SelfTest::new(mode))
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .with_denylist(&["loading"])
                .build(),
        )
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app
                .get_webview_window("main")
                .or_else(|| app.get_webview_window("loading"))
            {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .invoke_handler(tauri::generate_handler![
            selftest::selftest_report,
            open_log_folder,
            install_update
        ])
        .on_page_load(|webview, payload| {
            if webview.label() == "main" && payload.event() == PageLoadEvent::Finished {
                let app = webview.app_handle();
                if let Some(script) = app.state::<SelfTest>().script() {
                    let _ = webview.eval(script);
                }
            }
        })
        .on_window_event(|window, event| {
            if matches!(window.label(), "main" | "loading")
                && matches!(event, WindowEvent::CloseRequested { .. })
            {
                window.app_handle().exit(0);
            }
        })
        .setup(|app| {
            SelfTest::start_timeout(app.handle().clone());
            install_edit_menu(app)?;
            WebviewWindowBuilder::new(app, "loading", WebviewUrl::App("index.html".into()))
                .title("NightCrate")
                .inner_size(560.0, 360.0)
                .resizable(false)
                .build()?;
            let handle = app.handle().clone();
            thread::spawn(move || start_backend(handle));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build NightCrate shell");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(backend) = handle.state::<BackendSlot>().0.lock().unwrap().take() {
                backend.stop();
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn main_capability_has_exact_origin_and_permissions() {
        let (origin, permissions) = capability_spec(8766, false);
        assert_eq!(origin, "http://127.0.0.1:8766/*");
        assert_eq!(
            permissions,
            vec![
                "core:event:allow-listen",
                "core:event:allow-unlisten",
                "allow-install-update"
            ]
        );
        let (_, selftest_permissions) = capability_spec(8766, true);
        assert_eq!(
            selftest_permissions,
            vec![
                "core:event:allow-listen",
                "core:event:allow-unlisten",
                "allow-install-update",
                "allow-selftest-report"
            ]
        );
        let _capability = main_capability(8766, true).build();
    }
}
