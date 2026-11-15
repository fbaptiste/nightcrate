fn main() {
    for name in [
        "NIGHTCRATE_TEST_APP_DIR",
        "NIGHTCRATE_TEST_PORT",
        "NIGHTCRATE_TEST_MANIFEST_URL",
        "NIGHTCRATE_TEST_RELEASES_URL",
        "NIGHTCRATE_TEST_AUTO_INSTALL",
        "NIGHTCRATE_TEST_PROBE_URL",
    ] {
        println!("cargo:rerun-if-env-changed={name}");
    }
    println!("cargo:rustc-check-cfg=cfg(nightcrate_test_auto_install)");

    if std::env::var_os("NIGHTCRATE_TEST_AUTO_INSTALL").is_some() {
        println!("cargo:rustc-cfg=nightcrate_test_auto_install");
    }

    if let Ok(endpoint) = std::env::var("NIGHTCRATE_TEST_MANIFEST_URL") {
        assert!(
            allowed_test_url(&endpoint),
            "NIGHTCRATE_TEST_MANIFEST_URL must use HTTPS or HTTP on 127.0.0.1"
        );
        if std::env::var_os("TAURI_CONFIG").is_none() {
            let override_json = format!(
                r#"{{"plugins":{{"updater":{{"dangerousInsecureTransportProtocol":true,"endpoints":["{endpoint}"]}}}}}}"#
            );
            std::env::set_var("TAURI_CONFIG", &override_json);
            println!("cargo:rustc-env=TAURI_CONFIG={override_json}");
        }
    }

    for name in ["NIGHTCRATE_TEST_RELEASES_URL", "NIGHTCRATE_TEST_PROBE_URL"] {
        if let Ok(value) = std::env::var(name) {
            assert!(
                allowed_test_url(&value),
                "{name} must use HTTPS or HTTP on 127.0.0.1"
            );
        }
    }

    let commands: &'static [&'static str] =
        if std::env::var_os("NIGHTCRATE_TEST_AUTO_INSTALL").is_some() {
            &[
                "selftest_report",
                "open_log_folder",
                "install_update",
                "test_auto_install_enabled",
            ]
        } else {
            &["selftest_report", "open_log_folder", "install_update"]
        };
    let manifest = tauri_build::AppManifest::new().commands(commands);
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(manifest))
        .expect("failed to build NightCrate shell metadata");
}

fn allowed_test_url(value: &str) -> bool {
    if value.contains(['"', '\\', '\n', '\r']) {
        return false;
    }
    value.starts_with("https://")
        || value.strip_prefix("http://127.0.0.1:").is_some_and(|rest| {
            let (port, path) = rest.split_once('/').unwrap_or((rest, ""));
            !port.is_empty()
                && port.bytes().all(|byte| byte.is_ascii_digit())
                && port.parse::<u16>().is_ok()
                && !path.contains(['"', '\\', '\n', '\r'])
        })
}
