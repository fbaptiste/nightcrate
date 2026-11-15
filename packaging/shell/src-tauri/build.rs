fn main() {
    let manifest = tauri_build::AppManifest::new().commands(&[
        "selftest_report",
        "open_log_folder",
        "install_update",
    ]);
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(manifest))
        .expect("failed to build NightCrate shell metadata");
}
