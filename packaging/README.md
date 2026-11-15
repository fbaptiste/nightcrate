# NightCrate packaging

This folder contains the cx_Freeze backend build, its validation and smoke
tests, and the Tauri desktop shell. Build the frontend before freezing:

```bash
cd frontend && npm run build
cd ..
uv run --project backend --group packaging python packaging/freeze.py
uv run --project backend python packaging/check_build.py packaging/build/backend
uv run --project backend python packaging/smoke.py packaging/build/backend
```

The generated `packaging/build/` folder and Rust `target/` folder are ignored.
Installer builds are produced by the pinned CI workflow on each target system.
