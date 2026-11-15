use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use tauri::webview::{DownloadEvent, NewWindowResponse, WebviewWindowBuilder};
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, Wry};

static IMAGE_WINDOW: AtomicUsize = AtomicUsize::new(1);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Classification {
    Allow,
    External,
    Refuse,
}

pub fn configure_main<'a>(
    mut builder: WebviewWindowBuilder<'a, Wry, AppHandle<Wry>>,
    app_handle: &'a AppHandle<Wry>,
    port: u16,
    probe_url: Option<&'static str>,
) -> WebviewWindowBuilder<'a, Wry, AppHandle<Wry>> {
    let origin = format!("http://127.0.0.1:{port}");
    let navigation_origin = origin.clone();
    builder = builder.on_navigation(move |url| {
        if navigation_allowed(url, &navigation_origin, probe_url) {
            true
        } else {
            match classify(url) {
                Classification::Allow => true,
                Classification::External => {
                    open_external(url.as_str());
                    false
                }
                Classification::Refuse => {
                    refuse(url.as_str());
                    false
                }
            }
        }
    });

    let app = app_handle.clone();
    let image_origin = origin.clone();
    builder = builder.on_new_window(move |url, features| {
        if same_origin(&url, &image_origin) && url.path() == "/image-viewer" {
            let label = format!("image-{}", IMAGE_WINDOW.fetch_add(1, Ordering::Relaxed));
            match WebviewWindowBuilder::new(&app, label, WebviewUrl::External(url))
                .title("NightCrate image")
                .window_features(features)
                .build()
            {
                Ok(window) => {
                    center_on_main(&app, &window);
                    NewWindowResponse::Create { window }
                }
                Err(error) => {
                    eprintln!("[shell] failed to create image window: {error}");
                    NewWindowResponse::Deny
                }
            }
        } else {
            match classify(&url) {
                Classification::Allow => NewWindowResponse::Allow,
                Classification::External => {
                    open_external(url.as_str());
                    NewWindowResponse::Deny
                }
                Classification::Refuse => {
                    refuse(url.as_str());
                    NewWindowResponse::Deny
                }
            }
        }
    });

    let downloads = app_handle
        .path()
        .download_dir()
        .unwrap_or_else(|_| PathBuf::from("."));
    let pending = PendingDownloads::default();
    builder.on_download(move |webview, event| match event {
        DownloadEvent::Requested { url, destination } => {
            let file_name = destination
                .file_name()
                .filter(|name| !name.is_empty())
                .map(PathBuf::from)
                .or_else(|| url.path_segments()?.next_back().map(PathBuf::from))
                .unwrap_or_else(|| PathBuf::from("nightcrate-download"));
            let suggested = unique_path(&downloads, &file_name);
            // The user picks where it goes (Fred, 2026-11-15); cancelling saves
            // nothing. This runs on the main thread, where the dialog must open.
            let dialog = rfd::FileDialog::new()
                .set_directory(&downloads)
                .set_file_name(
                    suggested
                        .file_name()
                        .map(|name| name.to_string_lossy().into_owned())
                        .unwrap_or_default(),
                )
                .set_parent(&webview.window());
            match dialog.save_file() {
                Some(chosen) => {
                    pending.remember(url.as_str(), chosen.clone());
                    *destination = chosen;
                    true
                }
                None => false,
            }
        }
        DownloadEvent::Finished { url, path, success } => {
            // macOS never reports the saved path, so use the one chosen above.
            let saved = pending.take(url.as_str()).or(path);
            if success {
                if let Some(saved) = saved {
                    let _ = webview.app_handle().emit_to(
                        "main",
                        "download-saved",
                        saved.to_string_lossy().to_string(),
                    );
                }
            }
            true
        }
        _ => true,
    })
}

/// Centre a new window on the main window, inside that screen's usable area.
/// The page asks for a position, but the web view reads `window.screenX/Y` in
/// another frame of reference, and the image window opened half off screen
/// (Fred, 2026-11-15).
fn center_on_main(app: &AppHandle<Wry>, window: &tauri::WebviewWindow<Wry>) {
    let Some(main) = app.get_webview_window("main") else {
        return;
    };
    let (Ok(main_position), Ok(main_size), Ok(size), Ok(Some(monitor))) = (
        main.outer_position(),
        main.outer_size(),
        window.outer_size(),
        main.current_monitor(),
    ) else {
        let _ = window.center();
        return;
    };
    let area = monitor.work_area();
    let (x, y) = centered_within(
        (main_position.x, main_position.y, main_size.width, main_size.height),
        (size.width, size.height),
        (area.position.x, area.position.y, area.size.width, area.size.height),
    );
    let _ = window.set_position(tauri::PhysicalPosition::new(x, y));
}

/// Top-left corner that centres `size` on `parent` (x, y, width, height), kept
/// inside `area` (x, y, width, height); all in physical pixels.
fn centered_within(
    parent: (i32, i32, u32, u32),
    size: (u32, u32),
    area: (i32, i32, u32, u32),
) -> (i32, i32) {
    let axis = |parent_start: i32, parent_len: u32, len: u32, area_start: i32, area_len: u32| {
        let centred = parent_start + (parent_len as i32 - len as i32) / 2;
        let last = area_start + (area_len as i32 - len as i32).max(0);
        centred.clamp(area_start, last)
    };
    (
        axis(parent.0, parent.2, size.0, area.0, area.2),
        axis(parent.1, parent.3, size.1, area.1, area.3),
    )
}

/// Where each download in progress is being saved, by its URL.
#[derive(Clone, Default)]
struct PendingDownloads(Arc<Mutex<HashMap<String, PathBuf>>>);

impl PendingDownloads {
    fn remember(&self, url: &str, path: PathBuf) {
        self.0.lock().unwrap().insert(url.to_owned(), path);
    }

    fn take(&self, url: &str) -> Option<PathBuf> {
        self.0.lock().unwrap().remove(url)
    }
}

fn same_origin(url: &tauri::Url, origin: &str) -> bool {
    url.as_str() == origin || url.as_str().starts_with(&format!("{origin}/"))
}

fn navigation_allowed(url: &tauri::Url, origin: &str, probe_url: Option<&str>) -> bool {
    same_origin(url, origin) || probe_url.is_some_and(|probe| url.as_str() == probe)
}

fn classify(url: &tauri::Url) -> Classification {
    match url.scheme() {
        "blob" | "data" | "about" => Classification::Allow,
        "http" | "https" | "mailto" => Classification::External,
        _ => Classification::Refuse,
    }
}

fn unique_path(directory: &Path, file_name: &Path) -> PathBuf {
    let candidate = directory.join(file_name);
    if !candidate.exists() {
        return candidate;
    }
    let stem = file_name
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("download");
    let extension = file_name.extension().and_then(|value| value.to_str());
    for suffix in 2.. {
        let name = match extension {
            Some(extension) => format!("{stem}-{suffix}.{extension}"),
            None => format!("{stem}-{suffix}"),
        };
        let candidate = directory.join(name);
        if !candidate.exists() {
            return candidate;
        }
    }
    unreachable!()
}

pub fn open_external(target: &str) {
    match tauri::Url::parse(target) {
        Ok(url) if classify(&url) == Classification::External => open_target(target),
        _ => refuse(target),
    }
}

pub fn open_path(path: &Path) {
    open_target(&path.to_string_lossy());
}

fn refuse(target: &str) {
    eprintln!("[shell] refused to open {target}");
}

fn open_target(target: &str) {
    #[cfg(target_os = "macos")]
    let mut command = {
        let mut command = Command::new("open");
        command.arg(target);
        command
    };
    #[cfg(target_os = "windows")]
    let mut command = {
        let mut command = Command::new("explorer.exe");
        command.arg(target);
        command
    };
    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = {
        let mut command = Command::new("xdg-open");
        command.arg(target);
        command
    };
    let _ = command.spawn();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn image_window_is_centred_on_the_main_window_and_kept_on_screen() {
        let screen = (0, 50, 3000, 1900);
        // Centred on a main window in the middle of the screen.
        assert_eq!(
            centered_within((500, 200, 2000, 1400), (1200, 800), screen),
            (900, 500)
        );
        // A main window near the bottom right: pulled back inside the screen.
        assert_eq!(
            centered_within((2400, 1500, 600, 400), (1200, 800), screen),
            (1800, 1150)
        );
        // Larger than the screen: pinned to its top left.
        assert_eq!(
            centered_within((0, 50, 3000, 1900), (4000, 2500), screen),
            (0, 50)
        );
    }

    #[test]
    fn pending_download_path_is_taken_once_by_its_url() {
        let pending = PendingDownloads::default();
        pending.remember("blob:http://127.0.0.1:8765/a", PathBuf::from("/tmp/guide.csv"));
        assert_eq!(pending.take("blob:http://127.0.0.1:8765/b"), None);
        assert_eq!(
            pending.take("blob:http://127.0.0.1:8765/a"),
            Some(PathBuf::from("/tmp/guide.csv"))
        );
        assert_eq!(pending.take("blob:http://127.0.0.1:8765/a"), None);
    }

    fn classification(url: &str) -> Classification {
        classify(&tauri::Url::parse(url).unwrap())
    }

    #[test]
    fn classifies_safe_navigation_and_external_schemes() {
        assert_eq!(
            classification("blob:http://127.0.0.1/value"),
            Classification::Allow
        );
        assert_eq!(
            classification("data:text/plain,value"),
            Classification::Allow
        );
        assert_eq!(classification("about:blank"), Classification::Allow);
        assert_eq!(
            classification("http://example.com"),
            Classification::External
        );
        assert_eq!(
            classification("https://example.com"),
            Classification::External
        );
        assert_eq!(
            classification("mailto:user@example.com"),
            Classification::External
        );
        assert_eq!(
            classification("file:///tmp/private"),
            Classification::Refuse
        );
        assert_eq!(
            classification("nightcrate://private"),
            Classification::Refuse
        );
    }

    #[test]
    fn allows_only_the_exact_configured_probe_url() {
        let probe = "http://127.0.0.1:4567/probe.html?run=one";
        let allowed = tauri::Url::parse(probe).unwrap();
        let changed_path = tauri::Url::parse("http://127.0.0.1:4567/other").unwrap();
        let changed_query = tauri::Url::parse("http://127.0.0.1:4567/probe.html?run=two").unwrap();
        assert!(navigation_allowed(
            &allowed,
            "http://127.0.0.1:8765",
            Some(probe)
        ));
        assert!(!navigation_allowed(
            &changed_path,
            "http://127.0.0.1:8765",
            Some(probe)
        ));
        assert!(!navigation_allowed(
            &changed_query,
            "http://127.0.0.1:8765",
            Some(probe)
        ));
        assert!(!navigation_allowed(&allowed, "http://127.0.0.1:8765", None));
    }
}
