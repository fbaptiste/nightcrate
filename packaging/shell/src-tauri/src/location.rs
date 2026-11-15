//! "Use my location" in the app window (Fred, 2026-11-15).
//!
//! WebKit on macOS asks the app whether a page may have the location, through
//! a delegate method wry doesn't implement (wry 0.57 lists geolocation as
//! unsupported there), so WebKit refused every request without asking anyone.
//! `allow_on_macos` adds that method to wry's delegate class. It grants the
//! backend's page, and macOS then shows its own location prompt.
//!
//! WebKitGTK refuses unless the app allows, and WebView2 would add its own
//! prompt. `permission` allows the backend's page on both, so the system's
//! location settings are the one gate everywhere.

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

#[cfg(target_os = "macos")]
pub use macos::allow_on_macos;

#[cfg(target_os = "macos")]
mod macos {
    use super::is_backend;
    use block2::Block;
    use objc2::ffi::class_addMethod;
    use objc2::runtime::{AnyClass, AnyObject, Imp, Sel};
    use objc2::{msg_send, sel};
    use std::ffi::{c_char, CStr};
    use std::sync::atomic::{AtomicU16, Ordering};

    static BACKEND_PORT: AtomicU16 = AtomicU16::new(0);

    // WKPermissionDecision values.
    const GRANT: isize = 1;
    const DENY: isize = 2;

    type Decide = unsafe extern "C-unwind" fn(
        *mut AnyObject,
        Sel,
        *mut AnyObject,
        *mut AnyObject,
        *mut AnyObject,
        *mut Block<dyn Fn(isize)>,
    );

    /// Lets the backend's page in this window ask macOS for the location.
    pub fn allow_on_macos(window: &tauri::WebviewWindow, backend_port: u16) {
        BACKEND_PORT.store(backend_port, Ordering::Release);
        let result = window.with_webview(|webview| {
            // SAFETY: `inner` is this window's live WKWebView, and Tauri runs
            // this closure on the main thread, where WebKit must be used.
            unsafe { install(webview.inner().cast()) }
        });
        if let Err(error) = result {
            eprintln!("[shell] location: couldn't reach the window's webview: {error}");
        }
    }

    unsafe fn install(webview: *mut AnyObject) {
        if webview.is_null() {
            return;
        }
        let delegate: *mut AnyObject = unsafe { msg_send![webview, UIDelegate] };
        let Some(delegate_object) = (unsafe { delegate.as_ref() }) else {
            eprintln!("[shell] location: the window has no WebKit UI delegate");
            return;
        };
        let class: *const AnyClass = delegate_object.class();
        let decide: Decide = decide;
        // SAFETY: the signature matches the selector's type encoding, which is
        // WebKit's own (v48@0:8@16@24@32@?40, read from WKUIDelegatePrivate).
        let imp: Imp = unsafe { std::mem::transmute::<Decide, Imp>(decide) };
        // Adds nothing if the class already answers: a later wry may, and it
        // then asks the window's permission handler instead.
        unsafe {
            class_addMethod(
                class.cast_mut(),
                sel!(_webView:requestGeolocationPermissionForOrigin:initiatedByFrame:decisionHandler:),
                imp,
                c"v@:@@@@?".as_ptr(),
            );
        }
        // WebKit records which methods a delegate answers when the delegate is
        // set, so set the same delegate again for the new method to count.
        let _: () = unsafe { msg_send![webview, setUIDelegate: delegate] };
    }

    unsafe fn text(string: *mut AnyObject) -> String {
        if string.is_null() {
            return String::new();
        }
        let utf8: *const c_char = unsafe { msg_send![string, UTF8String] };
        if utf8.is_null() {
            return String::new();
        }
        unsafe { CStr::from_ptr(utf8) }
            .to_string_lossy()
            .into_owned()
    }

    unsafe extern "C-unwind" fn decide(
        _delegate: *mut AnyObject,
        _command: Sel,
        _webview: *mut AnyObject,
        origin: *mut AnyObject,
        _frame: *mut AnyObject,
        decision_handler: *mut Block<dyn Fn(isize)>,
    ) {
        let allowed = !origin.is_null() && {
            let scheme = unsafe { text(msg_send![origin, protocol]) };
            let host = unsafe { text(msg_send![origin, host]) };
            let port: isize = unsafe { msg_send![origin, port] };
            is_backend(
                &scheme,
                &host,
                u16::try_from(port).ok(),
                BACKEND_PORT.load(Ordering::Acquire),
            )
        };
        if let Some(handler) = unsafe { decision_handler.as_ref() } {
            handler.call((if allowed { GRANT } else { DENY },));
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
}
