//! "Use My Location" in the app window (Fred, 2026-11-15).
//!
//! macOS: WebKit only fetches a location for a page when the app gives it a
//! location provider, and wry doesn't, so the page's own request can never
//! succeed. The page calls `current_location` instead, which asks Core
//! Location directly; macOS shows its usual "allow location?" prompt the
//! first time. Verified on macOS 26.6 with an app signed like NightCrate
//! (ad hoc, hardened runtime, the location entitlement).
//!
//! Windows and Linux: the page keeps the browser's request (the command
//! answers "unsupported"). WebKitGTK refuses unless the app allows, and
//! WebView2 would add its own prompt; `permission` allows the backend's page
//! on both, so the system's location settings decide.

use serde::Serialize;
use tauri::webview::{PermissionKind, PermissionResponse};

/// Whether a page's scheme, host and port are the backend's.
fn is_backend(scheme: &str, host: &str, port: Option<u16>, backend_port: u16) -> bool {
    scheme == "http" && host == "127.0.0.1" && port == Some(backend_port)
}

/// The main window's answer to a page's permission request (Windows, Linux).
pub fn permission(
    kind: PermissionKind,
    page: Option<&tauri::Url>,
    backend_port: u16,
) -> PermissionResponse {
    let from_backend = page.is_some_and(|url| {
        is_backend(
            url.scheme(),
            url.host_str().unwrap_or_default(),
            url.port(),
            backend_port,
        )
    });
    if matches!(kind, PermissionKind::Geolocation) && from_backend {
        PermissionResponse::Allow
    } else {
        PermissionResponse::Default
    }
}

/// A position for the page. Coordinates are never logged.
#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub struct Fix {
    latitude: f64,
    longitude: f64,
    accuracy_m: f64,
}

/// Why no position came back; the page words each one.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Failure {
    /// The user refused, now or earlier.
    Denied,
    /// A device policy forbids location.
    Restricted,
    /// Location Services is off for the whole computer.
    ServicesOff,
    /// macOS never reported an answer to the authorization request.
    NoAnswer,
    /// Authorized, but no position before the deadline.
    Timeout,
    /// Core Location couldn't determine a position.
    Unavailable,
    /// A newer request replaced this one.
    Cancelled,
    /// Not macOS: the page uses the browser's request.
    Unsupported,
}

impl Failure {
    fn code(self) -> &'static str {
        match self {
            Self::Denied => "denied",
            Self::Restricted => "restricted",
            Self::ServicesOff => "services_off",
            Self::NoAnswer => "no_answer",
            Self::Timeout => "timeout",
            Self::Unavailable => "unavailable",
            Self::Cancelled => "cancelled",
            Self::Unsupported => "unsupported",
        }
    }
}

/// A Core Location reading as a `Fix`, or `Unavailable` when it isn't a
/// usable position (a negative accuracy means the reading is invalid).
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
fn fix_from(latitude: f64, longitude: f64, accuracy_m: f64) -> Result<Fix, Failure> {
    let usable = latitude.is_finite()
        && longitude.is_finite()
        && accuracy_m.is_finite()
        && (-90.0..=90.0).contains(&latitude)
        && (-180.0..=180.0).contains(&longitude)
        && accuracy_m >= 0.0;
    if usable {
        Ok(Fix {
            latitude,
            longitude,
            accuracy_m,
        })
    } else {
        Err(Failure::Unavailable)
    }
}

/// Core Location may first deliver a cached position, from wherever the
/// computer last was; a laptop moved to a dark site would get its old site
/// (Codex's review, 2026-11-15). Older readings are skipped.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
const MAX_FIX_AGE_S: f64 = 60.0;

/// A Core Location reading, with its age in seconds.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
#[derive(Debug, Clone, Copy)]
struct Reading {
    latitude: f64,
    longitude: f64,
    accuracy_m: f64,
    age_s: f64,
}

/// The fix to report from one delivery (oldest reading first, as Core
/// Location orders them), or `None` to keep waiting: the newest reading
/// counts only when it is recent and usable.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
fn current_fix(readings: &[Reading]) -> Option<Fix> {
    let newest = readings.last()?;
    if !(newest.age_s.is_finite() && newest.age_s <= MAX_FIX_AGE_S) {
        return None;
    }
    fix_from(newest.latitude, newest.longitude, newest.accuracy_m).ok()
}

/// What a request that hit its deadline reports.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
fn timed_out(still_undecided: bool) -> Failure {
    if still_undecided {
        Failure::NoAnswer
    } else {
        Failure::Timeout
    }
}

/// The computer's position, asking the user the first time (macOS only).
#[tauri::command]
pub async fn current_location(app: tauri::AppHandle) -> Result<Fix, String> {
    #[cfg(target_os = "macos")]
    let result = macos::locate(app).await;
    #[cfg(not(target_os = "macos"))]
    let result = {
        let _ = app;
        Err(Failure::Unsupported)
    };
    result.map_err(|failure| failure.code().to_owned())
}

#[cfg(target_os = "macos")]
mod macos {
    use super::{current_fix, timed_out, Failure, Fix, Reading};
    use objc2::rc::Retained;
    use objc2::runtime::ProtocolObject;
    use objc2::{define_class, msg_send, DefinedClass, MainThreadMarker, MainThreadOnly};
    use objc2_core_location::{
        kCLLocationAccuracyHundredMeters, CLAuthorizationStatus, CLError, CLLocation,
        CLLocationManager, CLLocationManagerDelegate,
    };
    use objc2_foundation::{NSArray, NSError, NSObject, NSObjectProtocol};
    use std::cell::{Cell, RefCell};
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::mpsc::{self, RecvTimeoutError, Sender};
    use std::sync::Mutex;
    use std::time::{Duration, Instant};

    /// The whole request, the first-time prompt included: answering it took
    /// Fred about a minute in the 2026-11-15 test, with an explanation to
    /// read first.
    const DEADLINE: Duration = Duration::from_secs(120);
    /// The Location Services check; if it stalls, the request goes ahead.
    const SERVICES_CHECK: Duration = Duration::from_secs(5);

    struct Pending {
        id: u64,
        sender: Sender<Result<Fix, Failure>>,
        undecided: bool,
    }

    /// The request the command is waiting on. A newer request replaces it,
    /// which drops the older sender: that command then reports `Cancelled`.
    static PENDING: Mutex<Option<Pending>> = Mutex::new(None);
    static NEXT_ID: AtomicU64 = AtomicU64::new(1);

    struct Active {
        id: u64,
        manager: Retained<CLLocationManager>,
        _delegate: Retained<LocationDelegate>,
    }

    thread_local! {
        /// Core Location objects live on the main thread, where they were
        /// made and where their callbacks arrive.
        static ACTIVE: RefCell<Option<Active>> = const { RefCell::new(None) };
    }

    fn finish(id: u64, outcome: Result<Fix, Failure>) {
        let mut pending = PENDING.lock().unwrap();
        if pending.as_ref().is_some_and(|request| request.id == id) {
            if let Some(request) = pending.take() {
                let _ = request.sender.send(outcome);
            }
        }
    }

    fn note_undecided(id: u64, undecided: bool) {
        if let Some(request) = PENDING.lock().unwrap().as_mut() {
            if request.id == id {
                request.undecided = undecided;
            }
        }
    }

    struct Ivars {
        id: u64,
        asked: Cell<bool>,
        locating: Cell<bool>,
    }

    define_class!(
        #[unsafe(super(NSObject))]
        #[thread_kind = MainThreadOnly]
        #[name = "NightCrateLocationDelegate"]
        #[ivars = Ivars]
        struct LocationDelegate;

        unsafe impl NSObjectProtocol for LocationDelegate {}

        unsafe impl CLLocationManagerDelegate for LocationDelegate {
            #[unsafe(method(locationManagerDidChangeAuthorization:))]
            fn did_change_authorization(&self, manager: &CLLocationManager) {
                self.evaluate(manager);
            }

            #[unsafe(method(locationManager:didUpdateLocations:))]
            fn did_update_locations(
                &self,
                _manager: &CLLocationManager,
                locations: &NSArray<CLLocation>,
            ) {
                let readings: Vec<Reading> = locations
                    .iter()
                    .map(|location| unsafe {
                        let coordinate = location.coordinate();
                        Reading {
                            latitude: coordinate.latitude,
                            longitude: coordinate.longitude,
                            accuracy_m: location.horizontalAccuracy(),
                            age_s: -location.timestamp().timeIntervalSinceNow(),
                        }
                    })
                    .collect();
                // A cached or unusable reading: updates continue until a
                // current one arrives or the deadline passes.
                if let Some(fix) = current_fix(&readings) {
                    finish(self.ivars().id, Ok(fix));
                }
            }

            #[unsafe(method(locationManager:didFailWithError:))]
            fn did_fail(&self, _manager: &CLLocationManager, error: &NSError) {
                let code = error.code();
                if code == CLError::LocationUnknown.0 {
                    // Temporary: Core Location keeps trying.
                    return;
                }
                let failure = if code == CLError::Denied.0 {
                    Failure::Denied
                } else {
                    Failure::Unavailable
                };
                finish(self.ivars().id, Err(failure));
            }
        }
    );

    impl LocationDelegate {
        fn new(mtm: MainThreadMarker, id: u64) -> Retained<Self> {
            let this = Self::alloc(mtm).set_ivars(Ivars {
                id,
                asked: Cell::new(false),
                locating: Cell::new(false),
            });
            unsafe { msg_send![super(this), init] }
        }

        /// Moves the request on from the current authorization: ask once,
        /// locate once when allowed, or finish with the refusal.
        fn evaluate(&self, manager: &CLLocationManager) {
            let id = self.ivars().id;
            let status = unsafe { manager.authorizationStatus() };
            if status == CLAuthorizationStatus::NotDetermined {
                note_undecided(id, true);
                if !self.ivars().asked.replace(true) {
                    unsafe { manager.requestWhenInUseAuthorization() };
                }
            } else if status == CLAuthorizationStatus::AuthorizedAlways
                || status == CLAuthorizationStatus::AuthorizedWhenInUse
            {
                note_undecided(id, false);
                if !self.ivars().locating.replace(true) {
                    // Continuous updates rather than `requestLocation`, which
                    // delivers one reading even when it is cached.
                    unsafe { manager.startUpdatingLocation() };
                }
            } else if status == CLAuthorizationStatus::Denied {
                finish(id, Err(Failure::Denied));
            } else if status == CLAuthorizationStatus::Restricted {
                finish(id, Err(Failure::Restricted));
            } else {
                finish(id, Err(Failure::Unavailable));
            }
        }
    }

    /// Runs on the main thread.
    fn start(id: u64) {
        let Some(mtm) = MainThreadMarker::new() else {
            finish(id, Err(Failure::Unavailable));
            return;
        };
        let previous = ACTIVE.with(|active| active.borrow_mut().take());
        if let Some(previous) = previous {
            release(previous);
        }
        let manager = unsafe { CLLocationManager::new() };
        let delegate = LocationDelegate::new(mtm, id);
        unsafe {
            manager.setDesiredAccuracy(kCLLocationAccuracyHundredMeters);
            manager.setDelegate(Some(ProtocolObject::from_ref(&*delegate)));
        }
        // Don't rely on the callback Core Location makes when a delegate is
        // set; the flags keep a second evaluation from asking twice.
        delegate.evaluate(&manager);
        ACTIVE.with(|active| {
            *active.borrow_mut() = Some(Active {
                id,
                manager,
                _delegate: delegate,
            });
        });
    }

    /// Runs on the main thread, after the command has its answer.
    fn stop(id: u64) {
        let finished = ACTIVE.with(|active| {
            let mut active = active.borrow_mut();
            if active.as_ref().is_some_and(|current| current.id == id) {
                active.take()
            } else {
                None
            }
        });
        if let Some(finished) = finished {
            release(finished);
        }
    }

    fn release(active: Active) {
        unsafe {
            active.manager.setDelegate(None);
            active.manager.stopUpdatingLocation();
        }
    }

    pub async fn locate(app: tauri::AppHandle) -> Result<Fix, Failure> {
        let deadline = Instant::now() + DEADLINE;
        // Apple asks callers not to check this on the main thread. A stalled
        // check leaves its thread waiting, but not the request.
        let services_on = tauri::async_runtime::spawn_blocking(|| {
            let (sender, receiver) = mpsc::channel();
            std::thread::spawn(move || {
                let _ = sender.send(unsafe { CLLocationManager::locationServicesEnabled_class() });
            });
            receiver.recv_timeout(SERVICES_CHECK).unwrap_or(true)
        })
        .await
        .unwrap_or(true);
        if !services_on {
            return Err(Failure::ServicesOff);
        }
        let id = NEXT_ID.fetch_add(1, Ordering::Relaxed);
        let (sender, receiver) = mpsc::channel();
        *PENDING.lock().unwrap() = Some(Pending {
            id,
            sender,
            undecided: false,
        });
        if app.run_on_main_thread(move || start(id)).is_err() {
            finish(id, Err(Failure::Unavailable));
        }
        let received = tauri::async_runtime::spawn_blocking(move || {
            receiver.recv_timeout(deadline.saturating_duration_since(Instant::now()))
        })
        .await;
        let undecided = {
            let mut pending = PENDING.lock().unwrap();
            if pending.as_ref().is_some_and(|request| request.id == id) {
                pending.take().is_some_and(|request| request.undecided)
            } else {
                false
            }
        };
        let _ = app.run_on_main_thread(move || stop(id));
        match received {
            Ok(Ok(outcome)) => outcome,
            Ok(Err(RecvTimeoutError::Timeout)) => Err(timed_out(undecided)),
            Ok(Err(RecvTimeoutError::Disconnected)) => Err(Failure::Cancelled),
            Err(_) => Err(Failure::Unavailable),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn answer(kind: PermissionKind, page: Option<&str>) -> PermissionResponse {
        let url = page.map(|page| page.parse::<tauri::Url>().unwrap());
        permission(kind, url.as_ref(), 8766)
    }

    #[test]
    fn the_backend_page_may_have_the_location() {
        assert!(matches!(
            answer(
                PermissionKind::Geolocation,
                Some("http://127.0.0.1:8766/locations")
            ),
            PermissionResponse::Allow
        ));
    }

    #[test]
    fn other_pages_get_the_platform_default() {
        for page in [
            "http://127.0.0.1:8767/locations",
            "http://localhost:8766/locations",
            "https://127.0.0.1:8766/locations",
            "https://example.com/",
            "tauri://localhost/index.html",
        ] {
            assert!(
                matches!(
                    answer(PermissionKind::Geolocation, Some(page)),
                    PermissionResponse::Default
                ),
                "{page}"
            );
        }
        assert!(matches!(
            answer(PermissionKind::Geolocation, None),
            PermissionResponse::Default
        ));
    }

    #[test]
    fn other_permissions_get_the_platform_default() {
        for kind in [PermissionKind::Microphone, PermissionKind::Camera] {
            assert!(matches!(
                answer(kind, Some("http://127.0.0.1:8766/")),
                PermissionResponse::Default
            ));
        }
    }

    #[test]
    fn the_backend_origin_needs_scheme_host_and_port() {
        assert!(is_backend("http", "127.0.0.1", Some(8766), 8766));
        assert!(!is_backend("https", "127.0.0.1", Some(8766), 8766));
        assert!(!is_backend("http", "localhost", Some(8766), 8766));
        assert!(!is_backend("http", "127.0.0.1", Some(8767), 8766));
        assert!(!is_backend("http", "127.0.0.1", None, 8766));
        assert!(!is_backend("", "", None, 0));
    }

    #[test]
    fn a_reading_becomes_a_fix_only_when_usable() {
        assert_eq!(
            fix_from(33.4484, -112.074, 35.0),
            Ok(Fix {
                latitude: 33.4484,
                longitude: -112.074,
                accuracy_m: 35.0
            })
        );
        assert!(fix_from(-90.0, 180.0, 0.0).is_ok());
        for (latitude, longitude, accuracy) in [
            (33.4, -112.0, -1.0),
            (90.5, 0.0, 10.0),
            (0.0, -180.5, 10.0),
            (f64::NAN, 0.0, 10.0),
            (0.0, f64::INFINITY, 10.0),
            (0.0, 0.0, f64::NAN),
        ] {
            assert_eq!(
                fix_from(latitude, longitude, accuracy),
                Err(Failure::Unavailable),
                "{latitude} {longitude} {accuracy}"
            );
        }
    }

    fn reading(age_s: f64, accuracy_m: f64) -> Reading {
        Reading {
            latitude: 33.4484,
            longitude: -112.074,
            accuracy_m,
            age_s,
        }
    }

    #[test]
    fn a_cached_reading_is_skipped_until_a_current_one_arrives() {
        // Cached from an hour ago: keep waiting.
        assert_eq!(current_fix(&[reading(3600.0, 35.0)]), None);
        // The next delivery is current.
        assert_eq!(
            current_fix(&[reading(3600.0, 35.0), reading(1.0, 65.0)]),
            Some(Fix {
                latitude: 33.4484,
                longitude: -112.074,
                accuracy_m: 65.0
            })
        );
        // Only the newest reading counts, even when an older one is current.
        assert_eq!(current_fix(&[reading(2.0, 35.0), reading(600.0, 35.0)]), None);
    }

    #[test]
    fn a_reading_counts_up_to_a_minute_old_and_usable() {
        assert!(current_fix(&[reading(60.0, 35.0)]).is_some());
        assert!(current_fix(&[reading(0.0, 35.0)]).is_some());
        assert_eq!(current_fix(&[reading(60.5, 35.0)]), None);
        assert_eq!(current_fix(&[reading(f64::NAN, 35.0)]), None);
        assert_eq!(current_fix(&[reading(1.0, -1.0)]), None);
        assert_eq!(current_fix(&[]), None);
    }

    #[test]
    fn a_deadline_reports_whether_macos_ever_answered() {
        assert_eq!(timed_out(true), Failure::NoAnswer);
        assert_eq!(timed_out(false), Failure::Timeout);
    }

    #[test]
    fn failures_have_the_codes_the_page_expects() {
        let codes: Vec<&str> = [
            Failure::Denied,
            Failure::Restricted,
            Failure::ServicesOff,
            Failure::NoAnswer,
            Failure::Timeout,
            Failure::Unavailable,
            Failure::Cancelled,
            Failure::Unsupported,
        ]
        .into_iter()
        .map(Failure::code)
        .collect();
        assert_eq!(
            codes,
            [
                "denied",
                "restricted",
                "services_off",
                "no_answer",
                "timeout",
                "unavailable",
                "cancelled",
                "unsupported"
            ]
        );
    }

    #[test]
    fn a_fix_reaches_the_page_with_these_field_names() {
        let fix = fix_from(1.5, -2.5, 35.0).unwrap();
        assert_eq!(
            serde_json::to_value(fix).unwrap(),
            serde_json::json!({"latitude": 1.5, "longitude": -2.5, "accuracy_m": 35.0})
        );
    }
}
