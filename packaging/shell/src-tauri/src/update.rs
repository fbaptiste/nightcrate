use crate::{restart_backend, BackendSlot};
use serde::Serialize;
use serde_json::Value;
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_updater::UpdaterExt;

static INSTALLING: AtomicBool = AtomicBool::new(false);

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum InstallStage {
    Busy,
    Download,
    #[allow(dead_code)] // Constructed only by the Windows build.
    Launch,
    Install,
}

#[derive(Clone, Debug, Serialize)]
pub struct InstallError {
    stage: InstallStage,
    message: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "lowercase")]
enum ProgressStage {
    Downloading,
    Installing,
    Restarting,
}

#[derive(Clone, Debug, Serialize)]
struct InstallProgress {
    stage: ProgressStage,
    #[serde(skip_serializing_if = "Option::is_none")]
    downloaded: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    total: Option<u64>,
}

#[derive(Debug)]
struct InstallGuard;

impl InstallGuard {
    fn acquire() -> Result<Self, InstallError> {
        INSTALLING
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map(|_| Self)
            .map_err(|_| failure(InstallStage::Busy, "An update is already being installed."))
    }
}

impl Drop for InstallGuard {
    fn drop(&mut self) {
        INSTALLING.store(false, Ordering::Release);
    }
}

fn failure(stage: InstallStage, message: impl Into<String>) -> InstallError {
    InstallError {
        stage,
        message: message.into(),
    }
}

fn changed_failure() -> InstallError {
    failure(
        InstallStage::Download,
        "The available version changed; check again.",
    )
}

fn interrupted_failure() -> InstallError {
    failure(
        InstallStage::Download,
        "Something started while downloading; try again.",
    )
}

fn is_expected_version(available: Option<&str>, expected: &str) -> bool {
    available == Some(expected)
}

fn should_release_reservation(owns_install_guard: bool, install_failed: bool) -> bool {
    owns_install_guard && install_failed
}

fn numeric_version(value: &str) -> Option<Vec<u64>> {
    let parts: Option<Vec<_>> = value
        .split('.')
        .map(|part| {
            if part.is_empty() || !part.bytes().all(|byte| byte.is_ascii_digit()) {
                None
            } else {
                part.parse().ok()
            }
        })
        .collect();
    parts.filter(|parts| !parts.is_empty())
}

fn version_is_older(current: &str, required: &str) -> Option<bool> {
    let (Some(mut current), Some(mut required)) =
        (numeric_version(current), numeric_version(required))
    else {
        return None;
    };
    let length = current.len().max(required.len());
    current.resize(length, 0);
    required.resize(length, 0);
    Some(current < required)
}

fn platform_min_os<'a>(manifest: &'a Value, target: &str) -> Option<&'a str> {
    let platforms = manifest.get("platforms")?;
    let qualified_target = format!("{target}-{}", std::env::consts::ARCH);
    platforms
        .get(target)
        .or_else(|| platforms.get(&qualified_target))?
        .get("min_os")?
        .as_str()
}

fn macos_requirement(required: &str) -> String {
    let Some(mut parts) = numeric_version(required) else {
        return required.to_owned();
    };
    while parts.len() > 1 && parts.last() == Some(&0) {
        parts.pop();
    }
    parts
        .iter()
        .map(u64::to_string)
        .collect::<Vec<_>>()
        .join(".")
}

fn minimum_os_error(current: Option<&str>, required: &str) -> Option<String> {
    if numeric_version(required).is_none() {
        return Some("This update can't be checked against this Mac's system version.".to_owned());
    }
    if current.and_then(|value| version_is_older(value.trim(), required)) == Some(false) {
        return None;
    }
    Some(format!(
        "This update needs macOS {} or later.",
        macos_requirement(required)
    ))
}

#[cfg(target_os = "macos")]
fn enforce_minimum_os(manifest: &Value, target: &str) -> Result<(), InstallError> {
    use std::process::Command;

    let Some(required) = platform_min_os(manifest, target) else {
        return Ok(());
    };
    let current = Command::new("/usr/bin/sw_vers")
        .arg("-productVersion")
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok());
    if let Some(message) = minimum_os_error(current.as_deref(), required) {
        return Err(failure(InstallStage::Download, message));
    }
    Ok(())
}

#[cfg(not(target_os = "macos"))]
fn enforce_minimum_os(_manifest: &Value, _target: &str) -> Result<(), InstallError> {
    Ok(())
}

pub fn allowed_test_url(value: &str) -> bool {
    tauri::Url::parse(value).is_ok_and(|url| {
        matches!(url.scheme(), "https")
            || (url.scheme() == "http" && url.host_str() == Some("127.0.0.1"))
    })
}

fn endpoint_builder(app: &AppHandle) -> Result<tauri_plugin_updater::UpdaterBuilder, InstallError> {
    let builder = app.updater_builder();
    let Some(value) = option_env!("NIGHTCRATE_TEST_MANIFEST_URL") else {
        return Ok(builder);
    };
    if !allowed_test_url(value) {
        return Err(failure(
            InstallStage::Download,
            "The test update URL is not allowed.",
        ));
    }
    let url = tauri::Url::parse(value)
        .map_err(|error| failure(InstallStage::Download, error.to_string()))?;
    builder
        .endpoints(vec![url])
        .map_err(|error| failure(InstallStage::Download, error.to_string()))
}

fn api_request(port: u16, method: &str, route: &str, token: &str) -> Result<(), String> {
    if !token
        .bytes()
        .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
    {
        return Err("invalid reservation token".to_owned());
    }
    let address = ("127.0.0.1", port)
        .to_socket_addrs()
        .map_err(|error| error.to_string())?
        .next()
        .ok_or("loopback address unavailable")?;
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_secs(5))
        .map_err(|error| error.to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .map_err(|error| error.to_string())?;
    stream
        .set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|error| error.to_string())?;
    write!(
        stream,
        "{method} {route}?token={token} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    )
    .map_err(|error| error.to_string())?;
    stream.flush().map_err(|error| error.to_string())?;
    let mut status = String::new();
    BufReader::new(stream)
        .read_line(&mut status)
        .map_err(|error| error.to_string())?;
    let code = status
        .split_whitespace()
        .nth(1)
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or_else(|| format!("invalid backend response: {status}"))?;
    if (200..300).contains(&code) {
        Ok(())
    } else {
        Err(format!("backend returned {code}"))
    }
}

fn release(port: u16, token: &str) {
    let _ = api_request(port, "DELETE", "/api/app/install-reservation", token);
}

struct Renewal {
    stop: mpsc::Sender<()>,
    failed: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
}

enum DownloadOutcome {
    Complete(tauri_plugin_updater::Result<Vec<u8>>),
    RenewalFailed,
}

impl Renewal {
    fn start(port: u16, token: String) -> Self {
        let (stop, receiver) = mpsc::channel();
        let failed = Arc::new(AtomicBool::new(false));
        let thread_failed = Arc::clone(&failed);
        let thread = thread::spawn(move || loop {
            match receiver.recv_timeout(Duration::from_secs(30)) {
                Ok(()) | Err(mpsc::RecvTimeoutError::Disconnected) => break,
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    if api_request(port, "PUT", "/api/app/install-reservation", &token).is_err() {
                        thread_failed.store(true, Ordering::Release);
                        break;
                    }
                }
            }
        });
        Self {
            stop,
            failed,
            thread: Some(thread),
        }
    }

    fn failed(&self) -> bool {
        self.failed.load(Ordering::Acquire)
    }
}

impl Drop for Renewal {
    fn drop(&mut self) {
        let _ = self.stop.send(());
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

fn emit(app: &AppHandle, stage: ProgressStage, downloaded: Option<u64>, total: Option<u64>) {
    let _ = app.emit_to(
        "main",
        "update-progress",
        InstallProgress {
            stage,
            downloaded,
            total,
        },
    );
}

#[tauri::command]
pub async fn install_update(
    app: AppHandle,
    expected_version: String,
    token: String,
) -> Result<(), InstallError> {
    let port = app
        .state::<BackendSlot>()
        .0
        .lock()
        .unwrap()
        .as_ref()
        .and_then(|backend| backend.port())
        .ok_or_else(|| failure(InstallStage::Busy, "The NightCrate backend is unavailable."))?;
    let _guard = InstallGuard::acquire()?;

    let result = install_inner(&app, port, &expected_version, &token).await;
    if should_release_reservation(true, result.is_err()) {
        let error = result
            .as_ref()
            .expect_err("a failed install must have an error");
        if let Some(backend) = app.state::<BackendSlot>().0.lock().unwrap().clone() {
            backend.log_shell_event(&format!(
                "install_update failed at {:?}: {}",
                error.stage, error.message
            ));
        }
        release(port, &token);
    }
    result
}

async fn install_inner(
    app: &AppHandle,
    port: u16,
    expected_version: &str,
    token: &str,
) -> Result<(), InstallError> {
    let updater = endpoint_builder(app)?
        .build()
        .map_err(|error| failure(InstallStage::Download, error.to_string()))?;
    let update = updater
        .check()
        .await
        .map_err(|error| failure(InstallStage::Download, error.to_string()))?;
    if !is_expected_version(
        update.as_ref().map(|value| value.version.as_str()),
        expected_version,
    ) {
        return Err(changed_failure());
    }
    let update = update.expect("the version check accepted an available update");
    enforce_minimum_os(&update.raw_json, &update.target)?;

    let renewal = Renewal::start(port, token.to_owned());
    let failed = Arc::clone(&renewal.failed);
    let download_app = app.clone();
    let download_update = update.clone();
    let (sender, receiver) = mpsc::sync_channel(1);
    let download_task = tauri::async_runtime::spawn(async move {
        let mut downloaded = 0_u64;
        let result = download_update
            .download(
                |chunk, total| {
                    downloaded = downloaded.saturating_add(chunk as u64);
                    emit(
                        &download_app,
                        ProgressStage::Downloading,
                        Some(downloaded),
                        total,
                    );
                },
                || {},
            )
            .await;
        let _ = sender.send(result);
    });
    let outcome = tauri::async_runtime::spawn_blocking(move || loop {
        if failed.load(Ordering::Acquire) {
            return DownloadOutcome::RenewalFailed;
        }
        match receiver.recv_timeout(Duration::from_millis(100)) {
            Ok(result) => return DownloadOutcome::Complete(result),
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                return DownloadOutcome::Complete(Err(
                    tauri_plugin_updater::Error::ReleaseNotFound,
                ));
            }
        }
    })
    .await
    .map_err(|error| failure(InstallStage::Download, error.to_string()))?;
    let bytes = match outcome {
        DownloadOutcome::Complete(result) => {
            result.map_err(|error| failure(InstallStage::Download, error.to_string()))?
        }
        DownloadOutcome::RenewalFailed => {
            download_task.abort();
            return Err(interrupted_failure());
        }
    };
    if renewal.failed() {
        download_task.abort();
        return Err(interrupted_failure());
    }
    api_request(port, "POST", "/api/app/install-barrier", token)
        .map_err(|_| interrupted_failure())?;
    drop(renewal);

    emit(app, ProgressStage::Installing, None, None);
    if let Some(backend) = app.state::<BackendSlot>().0.lock().unwrap().take() {
        backend.stop();
    }

    if let Err(error) = update.install(&bytes) {
        let recovery = restart_backend(app.clone(), port);
        let current = app.package_info().version.to_string();
        #[cfg(windows)]
        let stage = InstallStage::Launch;
        #[cfg(not(windows))]
        let stage = InstallStage::Install;
        let message = if recovery.is_ok() {
            format!(
                "NightCrate couldn't install {expected_version} and is still on {current}. ({error})"
            )
        } else {
            format!(
                "NightCrate couldn't install {expected_version}, and its backend couldn't restart. ({error})"
            )
        };
        return Err(failure(stage, message));
    }

    #[cfg(not(windows))]
    {
        emit(app, ProgressStage::Restarting, None, None);
        app.restart();
    }
    #[cfg(windows)]
    unreachable!("a successful Windows install exits the process");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_urls_allow_https_and_loopback_http_only() {
        assert!(allowed_test_url("https://updates.example/latest.json"));
        assert!(allowed_test_url("http://127.0.0.1:48123/latest.json"));
        assert!(!allowed_test_url("http://localhost:48123/latest.json"));
        assert!(!allowed_test_url("http://192.168.1.20/latest.json"));
        assert!(!allowed_test_url("file:///tmp/latest.json"));
        assert!(!allowed_test_url("not a URL"));
    }

    #[test]
    fn single_install_guard_rejects_a_second_install_and_resets() {
        let first = InstallGuard::acquire().unwrap();
        let second = InstallGuard::acquire().unwrap_err();
        assert!(matches!(second.stage, InstallStage::Busy));
        drop(first);
        assert!(InstallGuard::acquire().is_ok());
    }

    #[test]
    fn aborts_when_the_available_version_is_missing_or_changed() {
        assert!(!is_expected_version(None, "0.0.2"));
        assert!(!is_expected_version(Some("0.0.3"), "0.0.2"));
        assert!(is_expected_version(Some("0.0.2"), "0.0.2"));
    }

    #[test]
    fn releases_only_a_failed_install_owned_by_the_guard_holder() {
        assert!(!should_release_reservation(false, false));
        assert!(!should_release_reservation(false, true));
        assert!(!should_release_reservation(true, false));
        assert!(should_release_reservation(true, true));
    }

    #[test]
    fn compares_macos_versions_numerically_and_reads_platform_minimum() {
        assert_eq!(version_is_older("13.6.9", "14.0"), Some(true));
        assert_eq!(version_is_older("14.0", "14.0"), Some(false));
        assert_eq!(version_is_older("14.0.1", "14.0"), Some(false));
        assert_eq!(version_is_older("15.0", "14.0"), Some(false));
        assert_eq!(version_is_older("14.10", "14.2"), Some(false));
        assert_eq!(version_is_older("unknown", "14.0"), None);
        let manifest = serde_json::json!({
            "platforms": {
                "darwin-aarch64": {"url": "https://example.test", "signature": "x", "min_os": "14.0"}
            }
        });
        assert_eq!(platform_min_os(&manifest, "darwin-aarch64"), Some("14.0"));
        if std::env::consts::ARCH == "aarch64" {
            assert_eq!(platform_min_os(&manifest, "darwin"), Some("14.0"));
        }
        assert_eq!(platform_min_os(&manifest, "linux-x86_64"), None);
        assert_eq!(macos_requirement("14.0"), "14");
    }

    #[test]
    fn minimum_macos_check_fails_closed() {
        assert_eq!(minimum_os_error(Some("14.0"), "14.0"), None);
        assert_eq!(
            minimum_os_error(Some("13.6.9"), "14.0").as_deref(),
            Some("This update needs macOS 14 or later.")
        );
        assert_eq!(
            minimum_os_error(None, "14.0").as_deref(),
            Some("This update needs macOS 14 or later.")
        );
        assert_eq!(
            minimum_os_error(Some("unknown"), "14.0").as_deref(),
            Some("This update needs macOS 14 or later.")
        );
        assert_eq!(
            minimum_os_error(Some("15.0"), "unknown").as_deref(),
            Some("This update can't be checked against this Mac's system version.")
        );
    }
}
