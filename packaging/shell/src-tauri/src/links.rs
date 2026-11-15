use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};
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
) -> WebviewWindowBuilder<'a, Wry, AppHandle<Wry>> {
    let origin = format!("http://127.0.0.1:{port}");
    let navigation_origin = origin.clone();
    builder = builder.on_navigation(move |url| {
        if same_origin(url, &navigation_origin) {
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
                Ok(window) => NewWindowResponse::Create { window },
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
    builder.on_download(move |webview, event| {
        match event {
            DownloadEvent::Requested { url, destination } => {
                let file_name = destination
                    .file_name()
                    .filter(|name| !name.is_empty())
                    .map(PathBuf::from)
                    .or_else(|| url.path_segments()?.next_back().map(PathBuf::from))
                    .unwrap_or_else(|| PathBuf::from("nightcrate-download"));
                *destination = unique_path(&downloads, &file_name);
            }
            DownloadEvent::Finished {
                path: Some(path),
                success: true,
                ..
            } => {
                let _ = webview.app_handle().emit_to(
                    "main",
                    "download-saved",
                    path.to_string_lossy().to_string(),
                );
            }
            _ => {}
        }
        true
    })
}

fn same_origin(url: &tauri::Url, origin: &str) -> bool {
    url.as_str() == origin || url.as_str().starts_with(&format!("{origin}/"))
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

    fn classification(url: &str) -> Classification {
        classify(&tauri::Url::parse(url).unwrap())
    }

    #[test]
    fn classifies_safe_navigation_and_external_schemes() {
        assert_eq!(classification("blob:http://127.0.0.1/value"), Classification::Allow);
        assert_eq!(classification("data:text/plain,value"), Classification::Allow);
        assert_eq!(classification("about:blank"), Classification::Allow);
        assert_eq!(classification("http://example.com"), Classification::External);
        assert_eq!(classification("https://example.com"), Classification::External);
        assert_eq!(classification("mailto:user@example.com"), Classification::External);
        assert_eq!(classification("file:///tmp/private"), Classification::Refuse);
        assert_eq!(classification("nightcrate://private"), Classification::Refuse);
    }
}
