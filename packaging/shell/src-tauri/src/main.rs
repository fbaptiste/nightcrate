#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod links;
mod selftest;
mod update;

use backend::{Backend, Output, StartFailure};
use selftest::{Mode, SelfTest};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use tauri::ipc::CapabilityBuilder;
#[cfg(test)]
use tauri::ipc::RuntimeCapability;
use tauri::menu::{MenuBuilder, SubmenuBuilder};
use tauri::webview::PageLoadEvent;
use tauri::{
    AppHandle, LogicalSize, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent,
};

struct BackendSlot(Mutex<Option<Arc<Backend>>>);

static PROBE_STARTED: AtomicBool = AtomicBool::new(false);

fn selftest_mode() -> Result<Mode, String> {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    if let Some(index) = arguments
        .iter()
        .position(|value| value == "--selftest-fresh")
    {
        let path = arguments
            .get(index + 1)
            .ok_or("--selftest-fresh requires a workspace directory")?;
        return Ok(Mode::Fresh(path.clone()));
    }
    if arguments
        .iter()
        .any(|value| value == "--selftest-configured")
    {
        return Ok(Mode::Configured);
    }
    Ok(Mode::Off)
}

fn capability_spec(port: u16, selftest: bool) -> (String, Vec<&'static str>) {
    let mut permissions = vec![
        "core:event:allow-listen",
        "core:event:allow-unlisten",
        // The page's zoom shortcuts (Cmd/Ctrl +, -, 0; `lib/desktopZoom.ts`)
        // call this; it only sets the page's own zoom.
        "core:webview:allow-set-webview-zoom",
        "allow-install-update",
    ];
    if selftest {
        permissions.push("allow-selftest-report");
    }
    #[cfg(nightcrate_test_auto_install)]
    permissions.push("allow-test-auto-install-enabled");
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

#[cfg(nightcrate_test_auto_install)]
#[tauri::command]
fn test_auto_install_enabled() -> bool {
    true
}

fn loading_status(app: &AppHandle, message: &str) {
    if let Some(window) = app.get_webview_window("loading") {
        let message = serde_json::to_string(message).unwrap();
        let _ = window.eval(format!("window.nightcrateLoading.status({message})"));
    }
}

fn guarded_selftest_script(script: String) -> String {
    if cfg!(nightcrate_test_auto_install) {
        return script;
    }
    format!(
        r#"(async()=>{{try{{await window.__TAURI__.core.invoke('test_auto_install_enabled');await window.__TAURI__.core.invoke('selftest_report',{{report:{{phase:'forbidden-test-command',ok:false}}}});}}catch(_error){{{script}}}}})();"#
    )
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

const MAIN_SIZE: (f64, f64) = (1400.0, 900.0);
const MAIN_MIN_SIZE: (f64, f64) = (1024.0, 700.0);

/// Whether a remembered window size (in logical pixels) is usable.
fn remembered_size_usable(width: f64, height: f64) -> bool {
    width >= MAIN_MIN_SIZE.0 && height >= MAIN_MIN_SIZE.1
}

/// The window-state plugin restores whatever size was saved, and a 1400 x 100
/// window once came back from a test run (Fred, 2026-11-15). The minimum size
/// stops anyone dragging the window that small, so a too-small size can only
/// come from that restore, which happens after the window is built: put it
/// back to the default size, centred.
fn reset_if_too_small(window: &tauri::Window, size: tauri::PhysicalSize<u32>) {
    if window.is_minimized().unwrap_or(false) {
        return;
    }
    let Ok(scale) = window.scale_factor() else {
        return;
    };
    let logical = size.to_logical::<f64>(scale);
    if !remembered_size_usable(logical.width, logical.height) {
        let _ = window.set_size(LogicalSize::new(MAIN_SIZE.0, MAIN_SIZE.1));
        let _ = window.center();
    }
}

/// The main window's page: the backend's root, plus the flag that lets the
/// frontend start the rehearsal's install in auto-install test builds.
fn main_page_url(origin: &str, test_auto_install: bool) -> String {
    let suffix = if test_auto_install {
        "?nc-test-autoinstall=1"
    } else {
        ""
    };
    format!("{origin}/{suffix}")
}

fn create_main(app: &AppHandle, port: u16, selftest: bool) -> Result<(), String> {
    app.add_capability(main_capability(port, selftest))
        .map_err(|error| error.to_string())?;
    let url = main_page_url(
        &format!("http://127.0.0.1:{port}"),
        cfg!(nightcrate_test_auto_install),
    )
    .parse()
        .map_err(|error| format!("invalid backend URL: {error}"))?;
    let builder = WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
        .title("NightCrate")
        .inner_size(MAIN_SIZE.0, MAIN_SIZE.1)
        .min_inner_size(MAIN_MIN_SIZE.0, MAIN_MIN_SIZE.1)
        .disable_drag_drop_handler()
        // The page handles Cmd/Ctrl +, - and 0 itself (`lib/desktopZoom.ts`) so
        // it can show the level; Tauri's own shortcuts would zoom twice.
        .zoom_hotkeys_enabled(false);
    let _window =
        links::configure_main(builder, app, port, option_env!("NIGHTCRATE_TEST_PROBE_URL"))
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

fn stop_backend(app: &AppHandle, backend: &Arc<Backend>) {
    backend.stop();
    let state = app.state::<BackendSlot>();
    let mut slot = state.0.lock().unwrap();
    if slot
        .as_ref()
        .is_some_and(|current| Arc::ptr_eq(current, backend))
    {
        slot.take();
    }
}

fn launch_backend(
    app: &AppHandle,
    requested_port: Option<u16>,
) -> Result<(Arc<Backend>, u16), StartFailure> {
    let (backend, receiver) =
        Backend::spawn(app, requested_port).map_err(|reason| StartFailure {
            exit_code: None,
            locked_kind: None,
            last_lines: Vec::new(),
            reason,
        })?;
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
            loading_status(app, &message);
        }
    });
    let port = match result {
        Ok(port) => port,
        Err(failure) => {
            stop_backend(app, &backend);
            return Err(failure);
        }
    };
    Ok((backend, port))
}

fn start_backend(app: AppHandle) {
    let (backend, port) = match launch_backend(&app, None) {
        Ok(value) => value,
        Err(failure) => {
            loading_failure(&app, &failure);
            return;
        }
    };
    let selftest = app.state::<SelfTest>().enabled();
    if let Err(reason) = create_main(&app, port, selftest) {
        stop_backend(&app, &backend);
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

fn restart_backend(app: AppHandle, port: u16) -> Result<(), String> {
    launch_backend(&app, Some(port))
        .map(|_| ())
        .map_err(|failure| failure.reason)
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
    let menu = MenuBuilder::new(app)
        .item(&application)
        .item(&edit)
        .build()?;
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
    let builder = tauri::Builder::default()
        .manage(BackendSlot(Mutex::new(None)))
        .manage(SelfTest::new(mode))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .with_denylist(&["loading"])
                // Test builds keep their own file, so they can't change the size
                // a real install restores.
                .with_filename(if option_env!("NIGHTCRATE_TEST_APP_DIR").is_some() {
                    ".window-state-test.json"
                } else {
                    tauri_plugin_window_state::DEFAULT_FILENAME
                })
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
        }));
    #[cfg(not(nightcrate_test_auto_install))]
    let builder = builder.invoke_handler(tauri::generate_handler![
        selftest::selftest_report,
        open_log_folder,
        update::install_update
    ]);
    #[cfg(nightcrate_test_auto_install)]
    let builder = builder.invoke_handler(tauri::generate_handler![
        selftest::selftest_report,
        open_log_folder,
        update::install_update,
        test_auto_install_enabled
    ]);
    let app = builder
        .on_page_load(|webview, payload| {
            if webview.label() == "main" && payload.event() == PageLoadEvent::Finished {
                let app = webview.app_handle();
                let loaded = payload.url().as_str();
                let backend = app.state::<BackendSlot>().0.lock().unwrap().clone();
                if let Some(backend) = &backend {
                    backend.log_shell_event(&format!("main loaded {loaded}"));
                }
                let port = backend.and_then(|backend| backend.port());
                let backend_origin = port.map(|port| format!("http://127.0.0.1:{port}"));
                let on_backend = backend_origin.as_ref().is_some_and(|origin| {
                    loaded == origin || loaded.starts_with(&format!("{origin}/"))
                });
                if on_backend {
                    if let Some(script) = app.state::<SelfTest>().script() {
                        let _ = webview.eval(guarded_selftest_script(script));
                    }
                    if let Some(probe) = option_env!("NIGHTCRATE_TEST_PROBE_URL") {
                        if !PROBE_STARTED.swap(true, Ordering::AcqRel) {
                            if let Ok(url) = tauri::Url::parse(probe) {
                                let _ = webview.navigate(url);
                            }
                        }
                    }
                } else if option_env!("NIGHTCRATE_TEST_PROBE_URL") == Some(loaded) {
                    if let Some(origin) = backend_origin {
                        // Back to the same page the window started on, test flag
                        // included, or the frontend never starts the test install.
                        let target = serde_json::to_string(&main_page_url(
                            &origin,
                            cfg!(nightcrate_test_auto_install),
                        ))
                        .unwrap();
                        let _ = webview.eval(format!(
                            "window.__nightcrateProbeReturn=setInterval(()=>{{if(window.__nightcrateProbeReported){{clearInterval(window.__nightcrateProbeReturn);window.location.replace({target});}}}},50)"
                        ));
                    }
                }
            }
        })
        .on_window_event(|window, event| {
            if matches!(window.label(), "main" | "loading")
                && matches!(event, WindowEvent::CloseRequested { .. })
            {
                window.app_handle().exit(0);
            }
            if let (WindowEvent::Resized(size), "main") = (event, window.label()) {
                reset_if_too_small(window, *size);
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
    fn remembered_size_below_the_minimum_is_not_usable() {
        assert!(remembered_size_usable(1400.0, 900.0));
        assert!(remembered_size_usable(1024.0, 700.0));
        assert!(!remembered_size_usable(1400.0, 100.0));
        assert!(!remembered_size_usable(800.0, 900.0));
    }

    #[test]
    fn main_page_url_keeps_the_test_install_flag() {
        assert_eq!(
            main_page_url("http://127.0.0.1:48125", true),
            "http://127.0.0.1:48125/?nc-test-autoinstall=1"
        );
        assert_eq!(
            main_page_url("http://127.0.0.1:8765", false),
            "http://127.0.0.1:8765/"
        );
    }

    #[test]
    fn main_capability_has_exact_origin_and_permissions() {
        let (origin, permissions) = capability_spec(8766, false);
        assert_eq!(origin, "http://127.0.0.1:8766/*");
        assert_eq!(
            permissions,
            vec![
                "core:event:allow-listen",
                "core:event:allow-unlisten",
                "core:webview:allow-set-webview-zoom",
                "allow-install-update"
            ]
        );
        let (_, selftest_permissions) = capability_spec(8766, true);
        assert_eq!(
            selftest_permissions,
            vec![
                "core:event:allow-listen",
                "core:event:allow-unlisten",
                "core:webview:allow-set-webview-zoom",
                "allow-install-update",
                "allow-selftest-report"
            ]
        );
        let _capability = main_capability(8766, true).build();
    }

    #[cfg(not(nightcrate_test_auto_install))]
    #[test]
    fn production_selftest_requires_the_test_command_to_be_rejected() {
        let script = guarded_selftest_script("window.selftestContinued=true;".to_owned());
        assert!(script.contains("invoke('test_auto_install_enabled')"));
        assert!(script.contains("window.selftestContinued=true;"));
        assert!(script.contains("forbidden-test-command"));
    }
}
