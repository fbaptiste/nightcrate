use crate::{restart_backend, BackendSlot};
use serde::Serialize;
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
    let _guard = match InstallGuard::acquire() {
        Ok(guard) => guard,
        Err(error) => {
            release(port, &token);
            return Err(error);
        }
    };

    let result = install_inner(&app, port, &expected_version, &token).await;
    if let Err(error) = &result {
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
}
