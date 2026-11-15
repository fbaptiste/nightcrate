use serde::Deserialize;
use std::collections::VecDeque;
use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, ExitStatus, Stdio};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager};

const LOG_LIMIT: u64 = 10 * 1024 * 1024;
const LOG_LIMIT_MESSAGE: &str = "[shell] log limit reached; further backend output omitted";
const START_SILENCE: Duration = Duration::from_secs(60);
const STOP_TIMEOUT: Duration = Duration::from_secs(15);

#[derive(Debug, Deserialize)]
pub struct Step {
    pub step: String,
    pub workspace: Option<String>,
}

#[derive(Debug, Deserialize)]
struct Ready {
    port: u16,
}

#[derive(Debug, Deserialize)]
struct Locked {
    kind: Option<String>,
}

#[derive(Debug)]
pub enum Output {
    Step(Step),
    Alive,
    Ready(u16),
    Locked(Option<String>),
    Line,
}

#[derive(Debug)]
pub struct StartFailure {
    pub exit_code: Option<i32>,
    pub locked_kind: Option<String>,
    pub last_lines: Vec<String>,
    pub reason: String,
}

struct Process {
    child: Child,
    stdin: Option<ChildStdin>,
    #[cfg(windows)]
    job: windows_job::Job,
}

struct ShellLog {
    file: File,
    bytes_written: u64,
    limited: bool,
}

impl ShellLog {
    fn write_line(&mut self, line: &str) {
        if self.limited {
            return;
        }
        let line_bytes = line.len() as u64 + 1;
        if self.bytes_written.saturating_add(line_bytes) <= LOG_LIMIT {
            if writeln!(self.file, "{line}").is_ok() {
                self.bytes_written += line_bytes;
            }
        } else {
            let _ = writeln!(self.file, "{LOG_LIMIT_MESSAGE}");
            self.limited = true;
        }
    }
}

#[derive(Default)]
pub struct Backend {
    process: Mutex<Option<Process>>,
    last_lines: Arc<Mutex<VecDeque<String>>>,
}

impl Backend {
    pub fn spawn(app: &AppHandle) -> Result<(Arc<Self>, mpsc::Receiver<Output>), String> {
        let executable = app
            .path()
            .resource_dir()
            .map_err(|error| error.to_string())?
            .join("backend")
            .join(if cfg!(windows) {
                "nightcrate-backend.exe"
            } else {
                "nightcrate-backend"
            });
        let mut command = Command::new(&executable);
        command.arg("--shell");
        if let Some(app_dir) = option_env!("NIGHTCRATE_TEST_APP_DIR") {
            command.arg("--app-dir").arg(app_dir);
        }
        if let Some(port) = option_env!("NIGHTCRATE_TEST_PORT") {
            command.arg("--port").arg(port);
        }
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        configure_process_group(&mut command);

        let mut child = command
            .spawn()
            .map_err(|error| format!("failed to start {}: {error}", executable.display()))?;
        #[cfg(windows)]
        let job = windows_job::Job::assign(&child)?;
        let stdin = child.stdin.take();
        let stdout = child.stdout.take().ok_or("backend stdout was not piped")?;
        let stderr = child.stderr.take().ok_or("backend stderr was not piped")?;
        let backend = Arc::new(Self {
            process: Mutex::new(Some(Process {
                child,
                stdin,
                #[cfg(windows)]
                job,
            })),
            last_lines: Arc::new(Mutex::new(VecDeque::with_capacity(20))),
        });
        let log_path = shell_log_path(app)?;
        let log = Arc::new(Mutex::new(open_log(&log_path)?));
        let (sender, receiver) = mpsc::channel();
        read_stream(stdout, Arc::clone(&log), Arc::clone(&backend.last_lines), sender.clone());
        read_stream(stderr, log, Arc::clone(&backend.last_lines), sender);
        Ok((backend, receiver))
    }

    pub fn wait_until_ready(
        &self,
        receiver: &mpsc::Receiver<Output>,
        mut on_output: impl FnMut(&Output),
    ) -> Result<u16, StartFailure> {
        let mut locked_kind = None;
        loop {
            match receiver.recv_timeout(START_SILENCE) {
                Ok(output) => {
                    on_output(&output);
                    match output {
                        Output::Ready(port) => return Ok(port),
                        Output::Locked(kind) => locked_kind = kind,
                        _ => {}
                    }
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    return Err(self.failure(None, locked_kind, "no backend output for 60 seconds"));
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    let status = self.wait_for_exit(Duration::from_secs(2));
                    return Err(self.failure(
                        status.and_then(|value| value.code()),
                        locked_kind,
                        "backend exited before it was ready",
                    ));
                }
            }
        }
    }

    fn failure(
        &self,
        exit_code: Option<i32>,
        locked_kind: Option<String>,
        reason: &str,
    ) -> StartFailure {
        StartFailure {
            exit_code,
            locked_kind,
            last_lines: self.last_lines.lock().unwrap().iter().cloned().collect(),
            reason: reason.to_owned(),
        }
    }

    fn wait_for_exit(&self, timeout: Duration) -> Option<ExitStatus> {
        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            let status = {
                let mut guard = self.process.lock().unwrap();
                guard
                    .as_mut()
                    .and_then(|process| process.child.try_wait().ok().flatten())
            };
            if status.is_some() {
                return status;
            }
            thread::sleep(Duration::from_millis(50));
        }
        None
    }

    pub fn stop(&self) {
        {
            let mut guard = self.process.lock().unwrap();
            let Some(process) = guard.as_mut() else {
                return;
            };
            process.stdin.take();
        }
        if self.wait_for_exit(STOP_TIMEOUT).is_none() {
            let mut guard = self.process.lock().unwrap();
            if let Some(process) = guard.as_mut() {
                kill_process_tree(process);
                let _ = process.child.wait();
            }
        }
        self.process.lock().unwrap().take();
    }
}

fn shell_log_path(app: &AppHandle) -> Result<PathBuf, String> {
    let directory = app.path().app_log_dir().map_err(|error| error.to_string())?;
    fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
    Ok(directory.join("shell.log"))
}

pub fn log_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let directory = app.path().app_log_dir().map_err(|error| error.to_string())?;
    fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
    Ok(directory)
}

fn open_log(path: &Path) -> Result<ShellLog, String> {
    let previous = path.with_file_name("shell.previous.log");
    if previous.exists() {
        fs::remove_file(&previous)
            .map_err(|error| format!("failed to remove {}: {error}", previous.display()))?;
    }
    if path.exists() {
        fs::rename(path, &previous).map_err(|error| {
            format!(
                "failed to rotate {} to {}: {error}",
                path.display(),
                previous.display()
            )
        })?;
    }
    let file = OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(path)
        .map_err(|error| format!("failed to open {}: {error}", path.display()))?;
    Ok(ShellLog {
        file,
        bytes_written: 0,
        limited: false,
    })
}

fn read_stream(
    stream: impl std::io::Read + Send + 'static,
    log: Arc<Mutex<ShellLog>>,
    last_lines: Arc<Mutex<VecDeque<String>>>,
    sender: mpsc::Sender<Output>,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let mut sender = Some(sender);
        for line in BufReader::new(stream).lines().map_while(Result::ok) {
            if let Ok(mut file) = log.lock() {
                file.write_line(&line);
            }
            {
                let mut recent = last_lines.lock().unwrap();
                if recent.len() == 20 {
                    recent.pop_front();
                }
                recent.push_back(line.clone());
            }
            if sender
                .as_ref()
                .is_some_and(|sender| sender.send(parse_line(&line)).is_err())
            {
                sender = None;
            }
        }
    })
}

fn parse_line(line: &str) -> Output {
    if line == "NIGHTCRATE_ALIVE" {
        return Output::Alive;
    }
    if let Some(value) = line.strip_prefix("NIGHTCRATE_STEP ") {
        if let Ok(step) = serde_json::from_str(value) {
            return Output::Step(step);
        }
    }
    if let Some(value) = line.strip_prefix("NIGHTCRATE_READY ") {
        if let Ok(Ready { port }) = serde_json::from_str(value) {
            return Output::Ready(port);
        }
    }
    if let Some(value) = line.strip_prefix("NIGHTCRATE_LOCKED ") {
        if let Ok(Locked { kind }) = serde_json::from_str(value) {
            return Output::Locked(kind);
        }
    }
    Output::Line
}

#[cfg(unix)]
fn configure_process_group(command: &mut Command) {
    use std::os::unix::process::CommandExt;
    unsafe {
        command.pre_exec(|| {
            if setsid() == -1 {
                Err(std::io::Error::last_os_error())
            } else {
                Ok(())
            }
        });
    }
}

#[cfg(windows)]
fn configure_process_group(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    command.creation_flags(0x0800_0000);
}

#[cfg(not(any(unix, windows)))]
fn configure_process_group(_command: &mut Command) {}

#[cfg(unix)]
fn kill_process_tree(process: &mut Process) {
    unsafe {
        kill(-(process.child.id() as i32), 9);
    }
}

#[cfg(windows)]
fn kill_process_tree(process: &mut Process) {
    process.job.terminate();
}

#[cfg(not(any(unix, windows)))]
fn kill_process_tree(process: &mut Process) {
    let _ = process.child.kill();
}

#[cfg(unix)]
unsafe extern "C" {
    fn setsid() -> i32;
    fn kill(pid: i32, signal: i32) -> i32;
}

#[cfg(windows)]
mod windows_job {
    use std::ffi::c_void;
    use std::mem::size_of;
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;

    type Handle = *mut c_void;
    const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: i32 = 9;
    const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: u32 = 0x0000_2000;

    #[repr(C)]
    #[derive(Default)]
    struct IoCounters {
        read_operation_count: u64,
        write_operation_count: u64,
        other_operation_count: u64,
        read_transfer_count: u64,
        write_transfer_count: u64,
        other_transfer_count: u64,
    }

    #[repr(C)]
    #[derive(Default)]
    struct BasicLimitInformation {
        per_process_user_time_limit: i64,
        per_job_user_time_limit: i64,
        limit_flags: u32,
        minimum_working_set_size: usize,
        maximum_working_set_size: usize,
        active_process_limit: u32,
        affinity: usize,
        priority_class: u32,
        scheduling_class: u32,
    }

    #[repr(C)]
    #[derive(Default)]
    struct ExtendedLimitInformation {
        basic_limit_information: BasicLimitInformation,
        io_info: IoCounters,
        process_memory_limit: usize,
        job_memory_limit: usize,
        peak_process_memory_used: usize,
        peak_job_memory_used: usize,
    }

    pub struct Job(Handle);
    unsafe impl Send for Job {}

    impl Job {
        pub fn assign(child: &Child) -> Result<Self, String> {
            unsafe {
                let job = CreateJobObjectW(std::ptr::null_mut(), std::ptr::null());
                if job.is_null() {
                    return Err(std::io::Error::last_os_error().to_string());
                }
                let mut info = ExtendedLimitInformation::default();
                info.basic_limit_information.limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                if SetInformationJobObject(
                    job,
                    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                    &mut info as *mut _ as *mut c_void,
                    size_of::<ExtendedLimitInformation>() as u32,
                ) == 0
                    || AssignProcessToJobObject(job, child.as_raw_handle() as Handle) == 0
                {
                    CloseHandle(job);
                    return Err(std::io::Error::last_os_error().to_string());
                }
                Ok(Self(job))
            }
        }

        pub fn terminate(&self) {
            unsafe {
                TerminateJobObject(self.0, 1);
            }
        }
    }

    impl Drop for Job {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.0);
            }
        }
    }

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn CreateJobObjectW(attributes: *mut c_void, name: *const u16) -> Handle;
        fn SetInformationJobObject(job: Handle, class: i32, info: *mut c_void, length: u32) -> i32;
        fn AssignProcessToJobObject(job: Handle, process: Handle) -> i32;
        fn TerminateJobObject(job: Handle, exit_code: u32) -> i32;
        fn CloseHandle(handle: Handle) -> i32;
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::os::unix::net::UnixStream;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn reader_keeps_draining_after_receiver_is_dropped() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let log_path = std::env::temp_dir().join(format!(
            "nightcrate-read-stream-{}-{unique}.log",
            std::process::id()
        ));
        let log = Arc::new(Mutex::new(open_log(&log_path).unwrap()));
        let last_lines = Arc::new(Mutex::new(VecDeque::new()));
        let (reader, mut writer) = UnixStream::pair().unwrap();
        let (sender, receiver) = mpsc::channel();
        let reader_thread = read_stream(reader, Arc::clone(&log), last_lines, sender);

        writer.write_all(b"before drop\n").unwrap();
        receiver.recv_timeout(Duration::from_secs(2)).unwrap();
        drop(receiver);

        let mut payload = Vec::with_capacity(1024 * 1024);
        for _ in 0..1024 {
            payload.extend(std::iter::repeat_n(b'x', 1023));
            payload.push(b'\n');
        }
        let expected_payload = payload.clone();
        let (done_sender, done_receiver) = mpsc::channel();
        thread::spawn(move || {
            writer.write_all(&payload).unwrap();
            drop(writer);
            done_sender.send(()).unwrap();
        });
        done_receiver
            .recv_timeout(Duration::from_secs(5))
            .expect("writer blocked after the output receiver was dropped");
        reader_thread.join().unwrap();
        log.lock().unwrap().file.flush().unwrap();

        let mut expected = b"before drop\n".to_vec();
        expected.extend(expected_payload);
        assert_eq!(fs::read(&log_path).unwrap(), expected);
        fs::remove_file(log_path).unwrap();
    }
}
