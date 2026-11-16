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

## Licence inventory and notices

After freezing, inventory the exact native libraries and the shipped Python,
frontend, and Rust components, then render the installer notices and LGPL source
archive:

```bash
uv run --project backend python packaging/notices.py inventory \
  --backend-dir packaging/build/backend \
  --shell-dir packaging/shell/src-tauri \
  --out packaging/build/notices/inventory.json
uv run --project backend python packaging/notices.py render \
  --inventory packaging/build/notices/inventory.json \
  --out packaging/build/notices
cp -R packaging/build/notices/licences/. packaging/build/backend/licences/
```

Linux inventory additionally receives the extracted AppImage root through
`--appimage`. CI builds Linux twice: it inventories the first AppImage, puts the
rendered notices into the frozen backend, rebuilds, and requires the second
inventory to be byte-for-byte identical.

The policy is fail-closed. An unknown licence, an unowned native library, an
applied MPL incompatibility notice, or unavailable exact LGPL source stops the
build and names the component. Inventory follows the frozen files rather than
the build environment, so build-only tools appear only if they are actually
present in the frozen output. `cargo`, and on Linux `dpkg-query` and
source-package indexes, must be available.
