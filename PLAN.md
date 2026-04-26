# NightCrate — Implementation Plan

Living document tracking implementation status. Check off items as they are completed.

## Table of Contents

- [v0.1.0 — Foundation + FITS Viewer](#v010--foundation--fits-viewer) ✅
- [v0.2.0 — Enhanced FITS Viewer](#v020--enhanced-fits-viewer) ✅
- [v0.3.0 — XISF Support + Image I/O Refactor](#v030--xisf-support--image-io-refactor) ✅
- [v0.3.0a — UI Polish + Frontend Redesign](#v030a--ui-polish--frontend-redesign) ✅
- [v0.4.0 — PixInsight Project Browsing](#v040--pixinsight-project-browsing) ✅
- [v0.4.1 — Image Histogram](#v041--image-histogram) ✅
- [v0.5.0 — Aberration Inspector](#v050--aberration-inspector-star-detection--sample-grid) ✅
- [v0.6.0 — Archive Browser](#v060--archive-browser) ✅
- [v0.6.1 — Performance & UX Polish](#v061--performance--ux-polish)
- [v0.7.0 — FITS Header Editing](#v070--fits-header-editing) ✅
- [v0.8.0 — Equipment Database Schema](#v080--equipment-database-schema) ✅
- [v0.9.0 — Equipment Management API + Core UI](#v090--equipment-management-api--core-ui) ✅
- [v0.9.1 — Equipment Management UI (Remaining Tabs)](#v091--equipment-management-ui-remaining-tabs) ✅
- [v0.10.0 — Equipment Seed Loader + Admin Page](#v0100--equipment-seed-loader--admin-page) ✅
- [v0.10.1 — Seed Data Population + UI Improvements + Locations](#v0101--seed-data-population--ui-improvements--locations) ✅
- [v0.11.0 — Astronomy Weather Forecast](#v0110--astronomy-weather-forecast) ✅
- [v0.12.0 — Rigs + My Equipment + Guide Calculators](#v0120--rigs--my-equipment--guide-calculators) ✅
- [v0.12.1 — Calculators + Maintenance & Architectural Review](#v0121--calculators--maintenance--architectural-review) ✅
- [v0.12.2 — Equipment Factory Refactor](#v0122--equipment-factory-refactor) ✅
- [v0.13.0 — Custom Horizons](#v0130--custom-horizons) ✅
- [v0.14.0 — DSO Catalog MVP (OpenNGC)](#v0140--dso-catalog-mvp-openngc) ✅
- [v0.15.0 — DSO Augmentation & VizieR Integration](#v0150--dso-augmentation--vizier-integration) ✅
- [v0.16.0 — Target Planner (Pass A)](#v0160--target-planner-pass-a) ✅
- [v0.17.0 — Target Planner Pass B (FOV Simulator + Rig-Framed Thumbnails)](#v0170--target-planner-pass-b-fov-simulator--rig-framed-thumbnails) ✅
- [v0.18.0 — Target Planner Pass C (Sky-Tile Cache + Seamless Stitching)](#v0180--target-planner-pass-c-sky-tile-cache--seamless-stitching) ✅
- [v0.18.1 — Target Planner UX Polish](#v0181--target-planner-ux-polish) ✅
- [v0.19.0 — Multi-Horizon + Planner Rewrite](#v0190--multi-horizon--planner-rewrite) ✅
- [v0.20.0 — DSO External References (Wikidata + Wikipedia)](#v0200--dso-external-references-wikidata--wikipedia) ✅
- [v0.21.0 — Target Planner Scoring Algorithm](#v0210--target-planner-scoring-algorithm) ✅
- [v0.21.1 — Scoring Polish + Planner UX + External Refs Extension](#v0211--scoring-polish--planner-ux--external-refs-extension) ✅
- [v0.22.0 — PHD2 Guide-Log Analyzer Pass A (Parser + Viewer Skeleton)](#v0220--phd2-guide-log-analyzer-pass-a-parser--viewer-skeleton) ✅
- [v0.23.0 — PHD2 Pass B (Drift + Oscillation + Scatter + Event List)](#v0230--phd2-pass-b-drift--oscillation--scatter--event-list) ✅
- [v0.24.0 — PHD2 Pass C (Range Selection + Copy Stats + Recent Files)](#v0240--phd2-pass-c-range-selection--copy-stats--recent-files) ✅
- [v0.25.0 — PHD2 Pass D-1 (Metric Foundation)](#v0250--phd2-pass-d-1-metric-foundation) ✅
- [v0.26.0 — PHD2 Pass D-2 (Spectrum Conformance + Worm Markers)](#v0260--phd2-pass-d-2-spectrum-conformance--worm-markers) ✅
- [v0.27.0 — PHD2 Analyzer Polish + Cleanup](#v0270--phd2-analyzer-polish--cleanup) ✅
- [v0.28.0 — Plate Solving (ASTAP Integration)](#v0280--plate-solving-astap-integration) ✅
- [FITS Equipment Resolver Spec](#fits-equipment-resolver-spec)
- [Imaging Core Schema — Rigs, Projects, Sessions, Sub Frames](#imaging-core-schema--rigs-projects-sessions-sub-frames)
- [Future Features to Consider](#future-features-to-consider)
- [Appendix: PHD2 Analyzer Roadmap](#appendix-phd2-analyzer-roadmap)
- [Appendix: Library Reference](#appendix-library-reference)

---

## v0.1.0 — Foundation + FITS Viewer

**Goal:** Working skeleton with a functional backend and frontend, theme switching, and the ability to open a FITS file, display its image and header.

**Status:** ✅ Complete

---

### 1. Environment Setup

Steps you'll need to follow (once) before development begins.

#### 1.1 Install uv

- [x] Install uv (Mac): installed via `brew install uv`

#### 1.2 Install Python 3.14

- [x] Python 3.14.0 already installed

#### 1.3 Node.js

- [x] Node.js v25.2.1 installed

---

### 2. Project Structure

- [x] Create the top-level directory layout:
  ```
  nightcrate/
  ├── backend/      ← Python/FastAPI
  ├── frontend/     ← React/TypeScript
  ├── CLAUDE.md
  └── PLAN.md
  ```

---

### 3. Backend — Project Initialization

#### 3.1 uv Project Setup

- [x] Initialize the backend project (`uv init --python 3.14 --lib`)
- [x] Add core dependencies (fastapi, uvicorn, aiosqlite, yoyo-migrations, astropy, pillow, numpy, aiofiles, python-multipart)
- [x] Add dev dependencies (ruff, pytest, pytest-asyncio, httpx)

  **Key uv commands you'll use daily:**
  | Command | What it does |
  |---------|-------------|
  | `uv add <pkg>` | Add a dependency (like `pip install` + saves to pyproject.toml) |
  | `uv add --dev <pkg>` | Add a dev-only dependency |
  | `uv run <cmd>` | Run a command inside the venv without activating it |
  | `uv sync` | Sync venv to match pyproject.toml (run after pulling changes) |
  | `uv python pin 3.14` | Pin this project to Python 3.14 |

#### 3.2 Ruff Configuration

- [x] Add ruff config to `backend/pyproject.toml`:
  ```toml
  [tool.ruff]
  target-version = "py314"
  line-length = 100

  [tool.ruff.lint]
  select = ["E", "F", "I", "UP"]   # pycodestyle, pyflakes, isort, pyupgrade

  [tool.ruff.format]
  quote-style = "double"
  ```

  **Key ruff commands:**
  | Command | What it does |
  |---------|-------------|
  | `uv run ruff check .` | Lint — shows issues |
  | `uv run ruff check --fix .` | Lint + auto-fix what it can |
  | `uv run ruff format .` | Format (replaces black) |
  | `uv run ruff format --check .` | Check formatting without changing files |

#### 3.3 Directory Structure

- [x] Create backend source layout:
  ```
  backend/
  ├── pyproject.toml
  ├── src/
  │   └── nightcrate/
  │       ├── __init__.py
  │       ├── main.py          # FastAPI app entry point
  │       ├── api/
  │       │   ├── __init__.py
  │       │   ├── fits.py      # FITS endpoints
  │       │   └── settings.py  # Settings endpoints
  │       ├── core/
  │       │   ├── __init__.py
  │       │   ├── config.py    # App settings (load/save settings.json)
  │       │   └── compute.py   # GPU/CPU compute backend abstraction
  │       ├── db/
  │       │   ├── __init__.py
  │       │   ├── base.py      # SQLAlchemy base
  │       │   └── session.py   # DB session factory
  │       └── services/
  │           ├── __init__.py
  │           └── fits.py      # FITS reading/rendering logic
  └── tests/
      └── __init__.py
  ```

#### 3.4 FastAPI App Shell

- [x] `main.py` — FastAPI instance with CORS configured for localhost, routers registered, startup/shutdown lifecycle
- [x] Health check endpoint: `GET /api/health` → `{"status": "ok"}`
- [ ] Configure FastAPI to serve the built React frontend as static files (deferred — production packaging)

#### 3.5 Settings System

- [x] `core/config.py` — Pydantic `Settings` model with fields:
  - `theme`: `"light" | "dark" | "browser"` (default: `"browser"`)
  - `gpu_acceleration`: `bool` (default: `true`)
  - `max_worker_cores`: `int | None` (default: `null` → uses `cpu_count - 1`)
- [x] Load from / save to `~/Library/Application Support/NightCrate/settings.json`
- [x] `GET /api/settings` — return current settings
- [x] `PUT /api/settings` — update and persist settings

#### 3.6 Compute Backend Stub

- [x] `core/compute.py` — thin module that detects available backends at startup (mlx if on Apple Silicon, else numpy) and respects the `gpu_acceleration` setting. Expose `get_array_module()` that returns the right backend. Rest of codebase always calls this, never imports mlx/numpy directly.

#### 3.7 Database Initialization

- [x] `db/session.py` — async aiosqlite connection factory pointing to `~/Library/Application Support/NightCrate/nightcrate.db`
- [x] `db/migrations.py` — calls `yoyo apply` on startup to run any pending SQL migration files
- [x] `db/migrations/0001.initial.sql` — empty placeholder migration (schema added in later versions)
- [x] Migrations run automatically when the app starts — no manual command needed

---

### 4. Backend — FITS Functionality

#### 4.1 FITS Header Endpoint

- [x] `GET /api/fits/header?path=<encoded_path>` — reads the FITS file at the given path using `astropy.io.fits`, returns all header cards as a JSON array of `{key, value, comment}` objects. Handles multi-HDU files (returns headers per HDU).

#### 4.2 FITS Image Endpoint

- [x] `GET /api/fits/image?path=<encoded_path>&hdu=0` — reads image data from the specified HDU, applies **linear min/max scaling** (maps actual data min→0, max→255 with no stretch curve), returns a PNG via `StreamingResponse`.
- [x] `GET /api/fits/hdus?path=<encoded_path>` — lists all HDUs with type and whether they contain image data.

---

### 5. Frontend — Project Initialization

#### 7.1 Vite + React + TypeScript

- [x] Scaffold the project (Vite + React + TypeScript)
- [x] Add dependencies (zustand, react-router-dom, @tanstack/react-query, MUI core + MUI X Community)

#### 7.2 MUI Theme Setup

- [x] `src/theme/theme.ts` — light and dark MUI theme definitions
- [x] `ThemeProvider` wraps the app and reads `theme` setting from Zustand store
- [x] "browser" mode uses `useMediaQuery('(prefers-color-scheme: dark)')` to select theme automatically

#### 7.3 Directory Structure

- [x] Establish frontend source layout:
  ```
  frontend/src/
  ├── api/             # Typed API client functions (calls backend)
  ├── components/      # Shared UI components
  ├── pages/           # Top-level route pages
  ├── stores/          # Zustand stores
  └── lib/             # Utilities
  ```

---

### 6. Frontend — Foundation

#### 6.1 API Client

- [x] `api/client.ts` — base fetch wrapper (uses Vite proxy, no hardcoded port)
- [x] `api/settings.ts` — `fetchSettings()`, `saveSettings()`
- [x] `api/fits.ts` — `fetchHdus()`, `fetchHeader()`, `fitsImageUrl()`

#### 6.2 Theme System

- [x] `stores/settingsStore.ts` — Zustand store; hydrates from `GET /api/settings` on app load; optimistic updates on change
- [x] `components/ThemeProvider.tsx` — MUI ThemeProvider selecting light/dark/browser theme
- [x] Theme persists across sessions (stored in `settings.json` via backend)

#### 6.3 App Shell + Routing

- [x] `main.tsx` / `App.tsx` — mount `ThemeProvider`, `QueryClientProvider`, `RouterProvider`
- [x] Sidebar layout with permanent MUI Drawer
- [x] Routes: `/`, `/fits-viewer`, `/settings`

#### 6.4 Settings Page

- [x] Theme selector (Light / Dark / Browser)
- [x] GPU acceleration toggle
- [x] Max worker cores input (number, blank = auto)
- [x] Optimistic updates via Zustand store → `PUT /api/settings`

---

### 7. Frontend — FITS Viewer

#### 7.1 File Selection

- [x] File path text input + Open button (native picker deferred until pywebview integration)

#### 7.2 FITS Header Panel

- [x] MUI X DataGrid showing Keyword / Value / Comment with sorting, pagination
- [x] HDU dropdown selector

#### 7.3 FITS Image Panel

- [x] PNG rendered from backend, displayed in viewer
- [x] HDU selector synced across image and header tabs
- [x] Fit-to-window / 1:1 pixel toggle

---

### 8. Running the App

- [x] Document the dev workflow in CLAUDE.md:
  ```bash
  # Terminal 1 — backend
  cd backend
  uv run uvicorn nightcrate.main:app --reload --port 8000

  # Terminal 2 — frontend
  cd frontend
  npm run dev          # Vite dev server on http://localhost:5173
  ```

---

### v0.1.0 Completion Criteria

- [x] Backend starts cleanly with `uv run uvicorn ...`
- [x] Frontend starts cleanly with `npm run dev`
- [x] `GET /api/health` returns 200
- [x] Settings load/save round-trip works
- [x] Theme switching (light/dark/browser) works and persists across app restarts
- [x] A FITS file can be opened and its header viewed
- [x] A FITS file's image data is displayed (linear-scaled, no stretch)
- [x] `uv run ruff check .` passes with no errors

---

---

## v0.2.0 — Enhanced FITS Viewer

**Goal:** Production-quality FITS viewer with auto-stretch, file browsing, zoom/pan, and mono+color support.

**Status:** ✅ Complete

---

### 1. Image Stretch System

#### 1.1 Backend Stretch Engine

- [x] Normalize FITS data to [0, 1] at load time based on data type (uint16 ÷ 65535, matching PixInsight convention)
- [x] Detect mono vs color images (NAXIS3=3 → RGB cube, handles both (3,H,W) and (H,W,3) layouts)
- [x] Implement three stretch types:
  - **STF (Auto):** PixInsight-compatible Screen Transfer Function — midtones transfer function with auto-computed shadow clip and midtones balance from median + MAD statistics (constants: target background 0.25, shadow clip −2.8σ)
  - **Linear:** Percentile-based black/white point clipping + gamma
  - **Asinh:** Arcsinh stretch for lifting faint detail
- [x] Per-channel statistics endpoint (`GET /api/fits/stats`) returning min, max, median, MAD, and auto-computed STF params per channel
- [x] For color linked mode: use dimmest channel's STF params across all three channels (preserves color balance)
- [x] Stretch params passed as query parameters to `GET /api/fits/image`
- [x] Per-channel (unlinked) stretch support for color images via per-channel query params

#### 1.2 Frontend Stretch Controls

- [x] Right sidebar panel with stretch controls
- [x] Stretch type selector: Auto / Linear / Asinh (context-dependent sliders per type)
- [x] STF sliders: Shadow (0–0.2), Midtone (0–0.5), Highlight (0.5–1.0) — step 0.000001, 6 decimal display
- [x] Linked / Unlinked toggle for color images (3-column layout when unlinked)
- [x] Auto-apply STF defaults from image stats on file open
- [x] "Reset to auto" button below sliders — resets to computed STF defaults
- [x] 300ms debounce on slider changes before triggering backend re-fetch
- [x] No horizontal scrollbar on sidebar (`overflowX: hidden`, `minWidth: 0`)

### 2. File Browser

- [x] Backend `GET /api/files/browse?path=<dir>` — lists subdirectories and FITS files, skips hidden entries
- [x] Backend `GET /api/files/volumes` — lists mounted volumes from `/Volumes/` + home directory
- [x] Browse dialog with:
  - Left sidebar showing volumes (home + all mounted drives)
  - Breadcrumb path navigation
  - Single-click to open folders, single-click to select files, double-click to open files
  - File sizes displayed for FITS files
- [x] **Favorites:** right-click a folder → "Add to favorites"; shown as chips with tooltip (full path on hover), click to navigate, X to remove
- [x] **Persistent state:** last browsed directory and favorites saved to `settings.json` — restored on app restart

### 3. Image Viewer Enhancements

#### 3.1 Zoom & Pan

- [x] Scroll-wheel zoom centered on mouse pointer (5%–4000% range)
- [x] Click-and-drag panning with grab/grabbing cursor
- [x] All zoom/pan is client-side CSS transforms (no backend calls)
- [x] Pixelated rendering at 2x+ zoom for clean pixel inspection
- [x] Default: fit-to-window; scroll wheel auto-transitions to free zoom
- [x] Fit and 1:1 buttons in right sidebar "IMAGE SIZE" section with icons
- [x] Live zoom percentage display

#### 3.2 Image Info Bar

- [x] Below the image: filename, capture date (local timezone, formatted), exposure time, filter
- [x] `DATE-OBS` treated as UTC, displayed in user's local timezone with timezone abbreviation
- [x] Missing values silently omitted

#### 3.3 UI Cleanup

- [x] Extension (HDU) selector hidden when file has only one image-bearing extension; renamed from "HDU" to "Extension"
- [x] Help text updated: "Enter a path or click Browse to open a FITS file"

### 4. Infrastructure

- [x] Version displayed in sidebar bottom-left, fetched from `GET /api/health` → `{"status": "ok", "version": "0.1.0"}`
- [x] README.md: fixed stale Stack section (removed SQLAlchemy/Tailwind references), added Open Source Acknowledgments
- [x] CLAUDE.md: added Dependency & License Policy section
- [x] PLAN.md: added Appendix: Library Reference with license evaluation for ~30 libraries
- [x] Identified GPL blocker: `xisf` (Python) — documented alternatives

### v0.2.0 Completion Criteria

- [x] FITS files display with auto-stretch matching PixInsight STF output
- [x] Both mono and color FITS files supported with linked/unlinked stretch
- [x] File browser with volumes, favorites, and persistent last-path
- [x] Zoom/pan works smoothly (client-side)
- [x] Image metadata displayed below image
- [x] `uv run ruff check .` passes
- [x] `npm run build` succeeds

---

---

## v0.3.0 — XISF Support + Image I/O Refactor

**Goal:** Support XISF files (PixInsight native format) alongside FITS, with a clean-room parser, a refactored image I/O layer, and settings moved to SQLite.

**Status:** ✅ Complete

---

### 1. Settings Moved to SQLite

Moved user settings from a standalone `settings.json` file into the SQLite database, so the entire app state is a single `nightcrate.db` file.

- [x] Migration `0002.settings_table.sql` — `settings` table with single-row constraint, JSON `data` column
- [x] Rewrote `core/config.py` — `get_settings()` and `update_settings()` are now async, read/write via `aiosqlite`
- [x] Removed `settings.json` file I/O, module-level singleton, and `APP_DIR` dependency from config
- [x] Updated `api/settings.py` endpoints to `await` async config functions
- [x] All existing settings (theme, GPU, worker cores, last browse path, favorites) preserved

### 2. Unit Tests + Quality Tooling

- [x] Added `bandit` as dev dependency for security scanning
- [x] 61 unit tests across 5 test files:
  - `test_normalize.py` (7) — data type normalization to [0, 1]
  - `test_stf.py` (11) — MTF math, STF auto-computation, stretch plane output
  - `test_fits_io.py` (10) — FITS header/HDU/stats/rendering, error cases
  - `test_config.py` (6) — settings model validation, DB round-trip persistence
  - `test_api.py` (15) — all HTTP endpoints including error cases
- [x] Pre-commit checklist added to CLAUDE.md: ruff lint → ruff format → bandit → pytest

### 3. Cross-Platform Support

- [x] App data directory via `platformdirs` — resolves correctly on Mac, Windows, Linux
- [x] File browser volumes endpoint handles macOS (`/Volumes/`), Windows (drive letters), Linux (`/media/`, `/mnt/`)
- [x] GPU compute abstraction supports `mlx` (Apple Silicon), `cupy` (NVIDIA CUDA), `numpy` (CPU fallback)
- [x] Removed async dependency from compute module (was broken after settings moved to SQLite)
- [x] Added `platformdirs` dependency (MIT, added to README acknowledgments)

### 4. Stretch Simplification

- [x] Removed Asinh stretch mode — only Auto (STF) and Linear remain
- [x] Linear mode is now simple min/max scaling with no sliders (identity transform)
- [x] Cleaned up backend `StretchParams`, API query params, frontend types, and tests

### 5. Refactor Image I/O Layer

Split `services/fits.py` into a clean multi-format architecture:

```
services/
├── imaging.py       # Shared: normalize, stretch, stats, render_image_png
├── fits_io.py       # FITS-specific: load data, read headers, list extensions
├── xisf_io.py       # XISF-specific: parse format, load data, read metadata
└── standard_io.py   # PNG/JPEG/TIFF: passthrough display + metadata extraction
```

- [x] `services/imaging.py` — all format-agnostic code: `normalize_to_01()`, `_mtf()`, `stretch_plane()`, `_compute_stf()`, `compute_image_stats()`, `render_image_png()`, data classes
- [x] `services/fits_io.py` — FITS-specific: `load_image_data()`, `read_header()`, `list_extensions()`
- [x] `services/standard_io.py` — PNG/JPEG/TIFF: `load_image_bytes()`, `read_header()` (EXIF/PNG text), `list_extensions()`
- [x] Deleted `services/fits.py` and `api/fits.py`
- [x] `api/images.py` — unified API replacing `api/fits.py`, dispatches by file type

### 6. XISF Clean-Room Parser

Clean-room read-only XISF parser based on the open XISF 1.0 specification. No dependency on the GPL `xisf` package. Uses `defusedxml` for safe XML parsing.

- [x] `lz4` (BSD 3-Clause), `zstandard` (BSD 3-Clause), `defusedxml` (PSF-2.0) added as dependencies
- [x] Updated `README.md` Open Source Acknowledgments

#### 6.2 Create `services/xisf_io.py`

##### File header parsing

- [x] Validate magic bytes (`XISF0100` at offset 0)
- [x] Read XML header length (uint32 LE at offset 8)
- [x] Parse XML header block (UTF-8, namespace `http://www.pixinsight.com/xisf`)

##### Image data loading

- [x] Parse `<Image>` element: `geometry` (W:H:C), `sampleFormat`, `colorSpace`, `location`, `compression`
- [x] Support sample formats: `UInt8`, `UInt16`, `UInt32`, `Float32`, `Float64`
- [x] Support color spaces: `Gray` (mono), `RGB` (planar channel layout: RRR...GGG...BBB)
- [x] Read attachment data at absolute file offset
- [x] Decompression: uncompressed, `zlib`, `lz4`, `lz4-hc`, `zstd` (with and without `+sh` byte shuffling)
- [x] Sub-block reading: 16-byte headers (compressed_size uint64 LE, uncompressed_size uint64 LE) per chunk
- [x] Byte unshuffle via numpy reshape/transpose
- [x] Normalize to [0, 1] via shared `normalize_to_01()` from `imaging.py`
- [x] Return normalized array shaped (H, W) for Gray or (3, H, W) for RGB

##### Metadata extraction

- [x] Parse `<FITSKeyword>` elements → `{key, value, comment}` dicts (same format as FITS headers)
- [x] Parse `<Property>` elements → extract key properties (scalar `value` attributes + inline base64 `String` type)
- [x] Map XISF properties to FITS-style display fields: `Instrument:Filter:Name` → FILTER, `Instrument:ExposureTime` → EXPTIME, `Observation:Time:Start` → DATE-OBS, etc.

##### Extension listing

- [x] `list_extensions(path) → list[dict]` — list all `<Image>` elements with id, geometry, sampleFormat, colorSpace, has_image

##### Deferred (not in v0.3.0)

- Complex32/Complex64, UInt8, UInt32, Float64 sample formats
- Inline base64 image data, external URL locations
- Writing XISF files
- Vector/Matrix property types

### 7. Unified API Layer

- [x] `api/images.py` replaces `api/fits.py` — new prefix `/api/images/*`
- [x] Accepts `.fits/.fit/.fts`, `.xisf`, `.png/.jpg/.jpeg/.tif/.tiff`
- [x] Dispatches to `fits_io`, `xisf_io`, or `standard_io` by extension
- [x] All endpoints (`/image`, `/stats`, `/header`, `/extensions`) work for all formats
- [x] `/stats` returns 404 for standard image formats (no stretch applicable)
- [x] File browser updated: `IMAGE_EXTENSIONS` includes all supported types
- [x] Frontend API module renamed from `api/fits.ts` to `api/images.ts`
- [x] Frontend `supportsStretch()` helper determines if stretch panel should show
- [x] Info bar: XISF files use FITS keywords when present, fall back to mapped XISF properties
- [x] Help text updated: "Enter a path or click Browse to open an image file"
- [x] Path input placeholder updated: "Path to image file…"

### 8. Recent Files

- [x] Migration `0003.recent_files.sql` — `recent_files` table with unique path, timestamp
- [x] `POST /api/images/recent` — records a file open, upserts path, prunes beyond 100
- [x] `GET /api/images/recent` — returns recent files ordered most recent first, prunes stale entries
- [x] MUI `Autocomplete` dropdown on the path input — shows recent files as suggestions
- [x] Selecting a recent file opens it immediately

### 9. Standard Image Format Support (PNG, JPEG, TIFF)

- [x] `services/standard_io.py` — loads via Pillow, converts to PNG for display
- [x] Extracts EXIF metadata (JPEG/TIFF) and PNG text chunks for the header table
- [x] Basic image info always shown (format, mode, dimensions)
- [x] Zoom/pan works identically to FITS/XISF
- [x] Stretch controls panel hidden when viewing standard images
- [x] File browser shows `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`

### v0.3.0 Completion Criteria

- [x] Settings stored in SQLite (single-file app state)
- [x] Cross-platform: app data directory, file browser volumes, GPU detection
- [x] Asinh stretch removed; Linear is simple min/max with no controls
- [x] 59 unit tests passing; bandit security scanning added
- [x] Pre-commit checklist enforced: ruff lint → ruff format → bandit → pytest
- [x] Existing FITS functionality works identically after I/O refactor (64 tests passing)
- [x] XISF parser: file header, image data, compression (zlib/lz4/zstd ±shuffle), sub-blocks, metadata
- [x] XISF metadata maps to FITS-style display fields via property-to-keyword mapping
- [x] Unified API: all formats through `/api/images/*` endpoints
- [x] File browser shows FITS, XISF, PNG, JPEG, TIFF files
- [x] Recent files: Autocomplete dropdown, SQLite persistence, stale entry pruning
- [x] PNG/JPEG/TIFF: display with zoom/pan, EXIF/PNG metadata, no stretch panel
- [x] `uv run ruff check .` passes
- [x] `uv run ruff format --check .` passes
- [x] `uv run bandit -r src/` passes
- [x] `uv run pytest` passes — 83 tests including 19 XISF parser tests
- [x] `npm run build` succeeds

---

---

---

## v0.3.0a — UI Polish + Frontend Redesign

**Goal:** Visual identity overhaul, better UX patterns, and quality-of-life improvements across the frontend.

**Status:** ✅ Complete

---

### 1. Naming + Branding

- [x] Renamed "FITS Viewer" → "Image Viewer" in nav, route (`/image-viewer`), and page component
- [x] Renamed `FitsViewerPage.tsx` → `ImageViewerPage.tsx`, updated `App.tsx` route and import
- [x] Fixed browser tab title: "frontend" → "NightCrate" in `index.html`

### 2. Custom Theme

- [x] Warm amber accent palette (`#c07b2b` light / `#d4993f` dark) — colorblind-safe
- [x] Cool slate surface colors for dark theme (`#1a1c20` base, `#24272c` paper, `#16181c` sidebar)
- [x] Warm off-white light theme (`#f5f4f2` base, `#eeecea` sidebar)
- [x] Component overrides: lowercase button text, rounded buttons/nav items, borderless drawer

### 3. Typography

- [x] **DM Sans** for body/heading text (loaded via Google Fonts)
- [x] **JetBrains Mono** for monospace elements (file paths, zoom percentage)
- [x] Shared typography config across both themes with tuned font sizes

### 4. Navigation Icons

- [x] Added MUI icons to sidebar nav: Home, ImageSearch (viewer), Settings
- [x] Sidebar width increased from 200px → 220px to accommodate icons

### 5. Image Viewer — Empty State

- [x] Centered empty state with ImageSearch icon, "Browse Files" button, format chips (FITS/XISF/PNG/JPEG/TIFF)
- [x] Keyboard shortcut hints displayed: ⌘O / Ctrl+O, F, 1

### 6. Image Viewer — Tab Persistence

- [x] Image and Header tabs now stay mounted (CSS `display: none` toggle instead of conditional render)
- [x] Switching between Image and Header no longer re-fetches the image from the API

### 7. Settings Page Layout

- [x] Settings grouped into outlined cards: "Appearance" and "Performance"
- [x] Centered layout with max-width 560px
- [x] Section headers with uppercase labels

### 8. Loading & Error States

- [x] Spinner (`CircularProgress`) shown while loading image extensions
- [x] Error notifications via MUI `Snackbar` toast (auto-dismiss 6s) instead of inline Alert

### 9. Keyboard Shortcuts

- [x] `Cmd/Ctrl+O` — open file browser
- [x] `F` — fit image to window (when image is open)
- [x] `1` — zoom to 1:1 (when image is open)
- [x] Shortcuts disabled when focus is in text inputs

### 10. Infrastructure

- [x] `make dev` shutdown fix: parent shell ignores SIGINT after launching children, waits for clean exit, `stty sane` restores terminal
- [x] Removed PyQt/Qt references from PLAN.md, CLAUDE.md, and nightcrate-brief.md
- [x] License changed to GPL-3.0 (later reverted to MIT in v0.11.0)

### v0.3.0a Completion Criteria

- [x] Both light and dark themes render correctly with custom palette and typography
- [x] Nav shows icons, route is `/image-viewer`, tab title is "NightCrate"
- [x] Empty state shows browse button, format chips, and shortcut hints
- [x] Tab switching preserves loaded image (no re-fetch)
- [x] Settings page uses card layout with section grouping
- [x] Error snackbar appears on load failures
- [x] Keyboard shortcuts work (⌘O, F, 1)
- [x] `npm run build` succeeds
- [x] `make dev` exits cleanly on Ctrl+C

---

---

## v0.4.0 — PixInsight Project Browsing

**Goal:** Browse into .pxiproject bundles from the image viewer, open referenced and embedded images, auto-detect linear/non-linear state, float TIFF support.

**Status:** ✅ Complete (merged via PR #1)

---

### Features delivered

- [x] .pxiproject browsing: XOSM manifest parser, embedded swap data decoder (all compression formats)
- [x] Multi-channel (RGB) embedded images decoded from planar channel sections
- [x] Auto-stretch linearity detection from XOSM STF params and auto-computed midtone
- [x] Float32 TIFF support via tifffile (BSD 3-Clause)
- [x] Backend-driven `supports_stretch` flag on `/extensions` endpoint
- [x] UI: "Auto Stretch" / "None" naming, Linked/Unlinked hidden when stretch is None
- [x] Loading spinner, recent files with project image names, virtual path display
- [x] Security: path traversal validation, absolute-path checks on virtual paths
- [x] 46 new tests (pxiproject_io + standard_io float TIFF). Total: 129 tests.

---

---

## v0.4.1 — Image Histogram

**Goal:** Add a real-time pixel value histogram to the image viewer sidebar, showing the data distribution for the currently loaded image.

**Status:** ✅ Complete

---

### 1. Histogram

- [x] `GET /api/images/histogram` endpoint — returns per-channel bins, luminosity, bin_edges
- [x] Works for all image types (FITS, XISF, float TIFF, pxiproject, standard PNG/JPEG/TIFF)
- [x] `HistogramData` type + `fetchHistogram()` in frontend API client
- [x] Canvas-based `Histogram.tsx` component with filled area curves
- [x] Gradient opacity fills, channel rendering order (Lum → B → G → R)
- [x] Channel visibility checkboxes with channel-colored labels
- [x] Log/Linear scale selector (two links, active one highlighted)
- [x] Auto-defaults: log scale for linear images, linear scale for non-linear
- [x] Hover crosshair with tooltip (bin value + per-channel counts)
- [x] Stretch indicator lines (shadow solid, midtone dashed, highlight solid) — appear on slider move, auto-hide after 3s
- [x] Histogram positioned below image in main content area (50% width)
- [x] Channel intensity bars next to histogram (color images only, normalized to max channel)
- [x] ResizeObserver for proper canvas sizing

### 2. Pixel Inspector

- [x] `GET /api/images/pixel` endpoint (backend, available but not used by inspector)
- [x] Client-side pixel sampling via offscreen canvas (zero API calls on hover)
- [x] Toggle ON/OFF in right sidebar
- [x] Shows X/Y coordinates, R/G/B/K values, hex color, named color (XKCD 949 colors)
- [x] Magnified patch preview with adjustable zoom slider
- [x] Amber reticle cursor with black outline for contrast
- [x] Default cursor when inspector off, reticle when on, grabbing hand when panning
- [x] UI persists when cursor leaves image (zeroed values, black patch)

### 3. Auto Stretch Algorithm Fix

- [x] Fixed to match PixInsight's AutoSTF algorithm
- [x] Uses avgDev (average deviation) instead of MAD for shadow clip computation
- [x] Correct constant: SHADOWS_CLIP = -1.25 (was -2.8)
- [x] Correct MTF self-inverse: `m = MTF(b0, TARGET_BG)` not `MTF(TARGET_BG, b0)`
- [x] Linked color mode: averages c0 and median across channels (was picking dimmest)
- [x] Stretch slider constraints: shadow < midtone < highlight, sliders push each other
- [x] Editable values: click any slider value to type an exact number

### 4. Statistics Panel

- [x] SNR per channel (median / σ) — key quality metric for astrophotography
- [x] avgDev column — matches PixInsight's Statistics process
- [x] Per-channel background deviation (Δbkg) — shows color balance at a glance
- [x] CIE L*a*b* a* median — color balance diagnostic (neutral / warm excess / cool excess)
- [x] Vertical card layout per channel (readable in 220px sidebar)
- [x] All tooltips on stat labels

### 5. Image Info Panel

- [x] Curated key fields: OBJECT, FILTER, EXPTIME, GAIN, CCD-TEMP, INSTRUME, TELESCOP
- [x] Extracted from existing header data (no new API call)
- [x] First section in sidebar (before Image Size)

### 6. UI Improvements

- [x] Format chip (FITS/XISF/PXI/PNG/etc.) next to tabs
- [x] Linear/Non-linear chip next to format chip
- [x] Stretch section hidden for non-linear images
- [x] Sidebar section headers: `── Label ────────` line style (no dividers)
- [x] Help section at sidebar bottom with keyboard shortcuts
- [x] Loading spinner in image viewer
- [x] Global minimum font size: 0.65rem
- [x] Named color lookup (XKCD 949 crowd-sourced colors, CC0 license)

### 7. Tests

- [x] 21 new tests: histogram endpoint (mono/color, bins sum, custom bins, monotonic edges), pixel endpoint (mono/color, out of bounds), SNR, avgDev, background delta, Lab a* (neutral/red/green, color/mono stats)
- [x] Updated STF tests for corrected algorithm
- [x] Total: 151 tests passing

### 8. FITS Header Ingestion Pipeline

- [x] `services/fits_header_map.py` — 108 keyword aliases across N.I.N.A., ASIAIR, SGPro, MaxIm DL, SharpCap, PixInsight
- [x] Priority resolution when multiple keywords map to same canonical field (e.g. EXPTIME wins over EXPOSURE)
- [x] Frame type normalization (IRAF short form, SBFITSEXT long form, other conventions → light/dark/flat/bias)
- [x] Filter name normalization (Luminance/L/LUM → Lum, H-Alpha → Ha, etc.; unknown filters pass through)
- [x] `extract_metadata()` — extracts canonical fields from any FITS header dict
- [x] `get_keyword_description()` — short UI descriptions for all 108 keywords
- [x] All four `read_header()` functions (fits_io, xisf_io, pxiproject_io, standard_io) annotate cards with `description` field
- [x] `GET /api/images/metadata` endpoint — returns canonical metadata + unrecognized keywords list
- [x] Header grid Comment column falls back to keyword description when FITS comment is empty
- [x] Image Info sidebar uses canonical fields — works regardless of capture software
- [x] Human-readable labels and formatting (120.0s, -10°C, 1960 mm, (f/6.3))
- [x] 56 new tests for header map (normalization, extraction, priority, map consistency)

### 9. UI Polish

- [x] Fixed sidebar width expansion bug (unlinked stretch stacked vertically, sidebar stays 220px)
- [x] Fixed favorites persistence race condition (generation counter in settings store, stale closure fix)
- [x] Stretch selector: dropdown replaced with toggle buttons (Auto Stretch / None)
- [x] Log/Linear selector: text links replaced with toggle buttons
- [x] All sidebar toggle button fonts aligned to 0.65rem
- [x] Section titles: centered between lines, secondary (slate blue) color
- [x] All sidebar sections collapsible (click header to toggle, ▸ indicator when collapsed)
- [x] Pixel Inspector: collapse/expand replaces ON/OFF toggle (collapsed = disabled)
- [x] Stretch and Pixel Inspector default to collapsed on image load
- [x] Help section defaults to collapsed
- [x] Image Info uses same grid layout and styling as Statistics section
- [x] Reset Stretch: renamed from "Reset to auto", repositioned closer to sliders
- [x] Theme toggle in left nav (cycles Light → Dark → System) next to version
- [x] Version read from `VERSION` file at repo root (no longer hardcoded)

### v0.4.1 Completion Criteria

- [x] Mono FITS/XISF → single gray filled curve
- [x] Color image → R/G/B overlaid with gradient fills + luminosity
- [x] Log/linear toggle works, auto-defaults based on linearity
- [x] Channel visibility checkboxes work
- [x] Hover crosshair + tooltip with values
- [x] Stretch indicator lines appear on slider move, hide after 3s
- [x] Pixel inspector: reticle cursor, magnified patch, R/G/B/K/hex/named color
- [x] Image Info, Statistics (SNR, avgDev, Δbkg, a*), Help sections in sidebar
- [x] Non-linear images: stretch section hidden
- [x] FITS header descriptions and canonical metadata working across all formats
- [x] Sidebar sections collapsible, consistent styling
- [x] Theme toggle accessible from main UI
- [x] `uv run pytest` passes — 210 tests
- [x] `npm run build` succeeds

---

---

## v0.5.0 — Aberration Inspector: Star Detection & Sample Grid

**Goal:** Detect and measure isolated star shapes across an astronomical image, display results in evenly-spaced sample squares with per-square aggregated metrics. Replaces N.I.N.A.'s basic aberration inspector with a configurable, interactive tool.

**Status:** ✅ Complete

**Implementation plan:** [`docs/superpowers/plans/2026-04-02-aberration-inspector.md`](docs/superpowers/plans/2026-04-02-aberration-inspector.md)

---

### New Dependencies

- `sep` (LGPL-3.0) — Source Extractor for star detection and shape measurement. Fast C library, gives eccentricity + position angle directly. LGPL fine as Python import; at distribution time (Tauri/PyInstaller), bundle sep's LICENSE file per LGPL §6.

### 1. Backend — Star Detection & Measurement

New service: `services/aberration.py`

- [x] `detect_stars(data, settings)` — detect isolated stars using `sep`, measure per-star metrics
- [x] Per-star output: x, y, FWHM, HFR, eccentricity, elongation_angle_deg, peak_adu, flux, SNR, semi_major, semi_minor, flag
- [x] Configurable `DetectionSettings`: detection_threshold, min/max FWHM, min SNR, max peak ADU, max semi_major, min separation
- [x] Background subtraction via `sep.Background`
- [x] Edge-of-frame exclusion (`edge_margin_px`)
- [x] Extended object filtering — rejects sources with semi_major > threshold (galaxy cores, nebula knots)
- [x] Blended source filtering — rejects sep flag `0x02` (crowded/blended)
- [x] Isolation filter — rejects stars with neighbor closer than `min_separation_px` (default 20px)

### 2. Backend — Sample Grid Aggregation

- [x] `compute_sample_grid(analysis, samples_across)` — evenly-spaced squares across the image
- [x] Square size computed relative to image: `image_width / (samples_across * 1.5)`
- [x] Rows auto-calculated from image aspect ratio
- [x] Per-square: star count, star indices, median/mean/std FWHM, median eccentricity, median HFR, median elongation angle
- [x] Re-gridding without re-analysis (different `samples_across` reuses cached star data)

### 3. Backend — API Endpoints

New router: `api/aberration.py`

- [x] `POST /api/aberration/analyze` — star detection with DB caching, accepts min_snr, min_fwhm, max_fwhm query params
- [x] `POST /api/aberration/samples` — compute sample grid, accepts samples_across + filter params, auto-triggers analysis if not cached
- [x] `GET /api/aberration/crop` — auto-stretched PNG of region (x0, y0, x1, y1 coordinates)
- [x] `GET /api/aberration/cache/size` — cache size in bytes
- [x] `DELETE /api/aberration/cache` — purge all cached data

### 4. Database — Analysis Storage

Migration: `0004.aberration_cache.sql`

- [x] `aberration_analysis` table: id, file_path, hdu, created_at, image_width/height, settings_json, global stats, star_count
- [x] `aberration_stars` table: id, analysis_id, per-star metrics (all 12 fields)
- [x] Indexes on `(analysis_id)` and `(file_path, hdu)`
- [x] UNIQUE constraint on (file_path, hdu, settings_json) for cache key
- [x] Cascade delete: removing analysis auto-removes stars
- [x] Cache TTL: `aberration_cache_ttl_days` setting (default 30 days)
- [x] Startup cleanup: purge expired entries on app launch
- [x] Settings page: cache size display in MB + "Clear All" button

### 5. Frontend — Aberration Inspector Tab

- [x] "Aberration" tab in image viewer tab bar (third tab after Image and Header)
- [x] Reuses currently loaded file — no separate file selection
- [x] Context-dependent right sidebar: image viewer controls for Image tab, aberration sidebar for Aberration tab
- [x] `SidebarSection` extracted to shared component (`components/SidebarSection.tsx`) for consistency

### 6. Frontend — Toolbar

- [x] Samples-across slider (3–9, default 5) — controls number of sample squares horizontally
- [x] Metric selector: Eccentricity (default), FWHM, HFR
- [x] Star filter sliders with tooltips: Min SNR (3–50), Min FWHM (1–10), Max FWHM (10–50)
- [x] Filters debounced (500ms) to avoid excessive backend calls
- [x] Different filter settings = different cache key (no stale results)

### 7. Frontend — Reference Thumbnail

- [x] Auto-stretched image thumbnail at top of aberration tab
- [x] Sample squares overlaid at actual image positions
- [x] Squares are draggable — constrained to their row/column lane (midpoint boundaries prevent overlap)
- [x] Client-side star re-aggregation on drag end (no backend call needed)
- [x] Reset button appears when squares are moved (vertically oriented, doesn't shift image)
- [x] Selected square highlighted with white border (colorblind-safe)

### 8. Frontend — Crop Grid View

- [x] Evenly-spaced sample tiles showing actual image regions (not single-star crops)
- [x] Tiles fill available space using CSS grid with `1fr` columns/rows
- [x] Viridis colorblind-safe color scale on tile borders based on selected metric
- [x] Color legend bar with min/max values and metric name
- [x] Metric value + star count overlay at bottom of each tile
- [x] Hover tooltips with all per-square metrics
- [x] Click tile opens centered preview popup (640×640px)

### 9. Frontend — Tile Preview Popup

- [x] Centered overlay with fade animation, close button, click-backdrop-to-dismiss
- [x] Auto-stretched image region with pixelated rendering
- [x] Toggleable star markers: rotated ellipses reflecting eccentricity + elongation angle
- [x] Dotted direction lines along major axis (offset below/above ellipse, not through it)
- [x] Eccentricity labels (`e: 0.35`) on opposite side of star from direction line
- [x] Labels positioned to stay within bounds (flips side if near edge)
- [x] Star hover tooltip with 216×216px zoomed crop + per-star metrics (FWHM, ecc, HFR, SNR, peak, angle, a/b)
- [x] Two-column metrics bar below image (not overlapping)
- [x] Clicking different tile while preview open switches to new tile

### 10. Frontend — Right Sidebar (Aberration Context)

- [x] Uses shared `SidebarSection` component (collapsible, centered title with lines)
- [x] Global Stats section: star count, median + range for FWHM/eccentricity/HFR, SNR range
- [x] Help section (collapsed by default): grouped into Grid View and Tile Preview with bullet points

### 11. Frontend — Additional Fixes

- [x] FitsImage ResizeObserver fix — prevents black image when switching tabs (container has 0 dimensions when hidden via `display: none`)

### 12. Tests

- [x] Star detection on synthetic image (5 stars, position matching, metric validation)
- [x] Edge exclusion, SNR filtering, extended object filtering
- [x] Sample grid aggregation (3×3, 5×5, different counts, coordinate validation, metrics, empty squares)
- [x] Square size scales with image dimensions
- [x] API endpoint tests: analyze, samples, crop (region), cache size, cache clear, caching behavior, error cases
- [x] Total: 241 tests passing

### v0.5.0 Completion Criteria

- [x] Star detection produces correct metrics on real FITS sub frame
- [x] Sample grid shows actual image regions with aggregated star metrics
- [x] Isolated star filtering excludes extended objects, blended sources, and crowded stars
- [x] User-adjustable filters (Min SNR, Min/Max FWHM) with debounced updates
- [x] Draggable sample squares with client-side re-aggregation
- [x] Tile preview with star ellipses, direction lines, and hover tooltips
- [x] Previously analyzed frames load instantly from cache
- [x] All visualizations use colorblind-safe palette (viridis) with white selection borders
- [x] `uv run pytest` passes — 241 tests
- [x] `npm run build` succeeds

---

---

## v0.6.0 — Archive Browser

**Goal:** Treat archive files (zip, tar, tar.gz, tar.bz2, tar.zst, 7z) as transparent folders in the file browser. Users navigate into archives, browse subdirectories, and select image files — which are extracted in-memory and loaded through the existing image pipeline with full viewer support.

**Status:** ✅ Complete

**Design spec:** [`docs/superpowers/specs/2026-04-02-archive-browser-design.md`](docs/superpowers/specs/2026-04-02-archive-browser-design.md)

**Implementation plan:** [`docs/superpowers/plans/2026-04-02-archive-browser.md`](docs/superpowers/plans/2026-04-02-archive-browser.md)

---

### New Dependencies

- `py7zr` (LGPL-2.1+) — pure Python 7z archive extraction. No external binaries required. LGPL fine as Python import; at distribution time, bundle py7zr's LICENSE file per LGPL §6.

### 1. Backend — Archive I/O Service

New service: `services/archive_io.py`

- [x] `is_archive(path)` — detect archive files by extension
- [x] `list_contents(archive_path, subdir)` — list entries at a directory level within the archive (TOC only, no extraction)
- [x] `extract_entry(archive_path, entry_path)` — extract single file to `BytesIO` buffer
- [x] Format dispatch: zip (`zipfile`), tar variants (`tarfile`), 7z (`py7zr`)
- [x] Compound suffix detection (`.tar.gz`, `.tar.bz2`, `.tar.zst`) — longest-first matching
- [x] Directory synthesis from entry paths (archives don't always have explicit dir entries)
- [x] Path traversal validation — reject `..`, absolute paths, suspicious entry names

### 2. Backend — I/O Service Widening

Widen load/read functions from `Path` to `Path | BinaryIO`:

- [x] `fits_io.py` — `load_image_data`, `read_header`, `list_extensions`
- [x] `xisf_io.py` — `load_image_data`, `read_header`, `list_extensions`
- [x] `standard_io.py` — `load_image_data`, `load_image_as_array`, `read_header`, `list_extensions`
- [x] New helper: `_file_type_from_ext(entry_name)` — extension-only type detection (no disk check)
- [x] Float TIFF detection on in-memory data via `tifffile.TiffFile(buf)`

### 3. Backend — API Endpoints

- [x] `GET /api/files/browse` — add `archives` array to response (alongside existing `dirs`, `files`, `projects`)
- [x] `GET /api/files/browse-archive?path={archive}&subdir={subdir}` — new endpoint, returns `{ path, subdir, parent, dirs, files }`
- [x] `_resolve_path()` in `api/images.py` — new archive branch for `::` virtual paths
- [x] Aberration inspector updated to use `_resolve_path()` for archive virtual path support

### 4. Frontend — File Browser

- [x] Archive entries in directory listing with `FolderZipIcon`
- [x] New browse mode: `activeArchive` + `archiveSubdir` state
- [x] `browseArchive(path, subdir)` API client function
- [x] Directory navigation within archives (click to descend, back to ascend)
- [x] Virtual path construction: `${archivePath}::${entryPath}`
- [x] Breadcrumb with archive name distinguished by zip icon
- [x] Back button: within archive → up one level, at root → exit archive

### 5. Tests

- [x] `archive_io` unit tests: list contents (zip, tar.gz, 7z), extract entry, directory synthesis, path traversal rejection (36 tests)
- [x] I/O service tests: verify `BytesIO` input works for FITS, XISF, standard formats (9 tests)
- [x] API tests: browse-archive endpoint, virtual path resolution, image loading from archive (13 tests)
- [x] Frontend build passes

### v0.6.0 Completion Criteria

- [x] All six archive formats browsable in file browser
- [x] Full directory navigation within archives
- [x] Images from archives load with full viewer support (stretch, histogram, stats, aberration, pixel inspector)
- [x] In-memory extraction (7z uses temp dir due to py7zr API, cleaned up immediately)
- [x] Path traversal protection on archive entry names
- [x] `uv run pytest` passes — 321 tests
- [x] `npm run build` succeeds

### v0.6.0 Post-Release Improvements

- [x] XISF: single-stream decompression support (zstd, lz4, zlib without sub-block headers)
- [x] XISF: `lz4hc` codec normalization (PixInsight writes codec name without hyphen)
- [x] FITS/XISF: strip surrounding single/double quotes from header values
- [x] Aberration inspector: retry with doubled threshold on sep pixstack overflow
- [x] Image viewer: `stretch=auto` backend mode — determines linearity and applies STF in one request, eliminating sequential frontend round trips
- [x] Image viewer: per-component loading spinners (image, histogram, channel bars load independently)
- [x] Image viewer: zoom/position preserved across tab switches (FitsImage stays mounted, `lastFitScale` cache)
- [x] File browser: opens to current file's directory with file pre-selected and scrolled into view
- [x] Activity console: ASGI middleware for request tracking, start-time timestamps, activity grouping, JSON export
- [x] TIFF: added `imagecodecs` dependency (BSD-3) for LZW and other compressed TIFF support
- [x] Pillow `MAX_IMAGE_PIXELS` disabled for large astrophotography images
- [x] Tests: 321 total (25 new — auto-stretch, diagnostics, XISF single-stream, header quotes, aberration retry)

---

## v0.6.1 — Performance & UX Polish

**Goal:** Faster image loading and better stretch control workflow. Focus on eliminating redundant computation, leveraging GPU acceleration, and replacing the live-updating debounced sliders with an explicit Apply workflow.

**Status:** In Progress

---

### 1. Stretch Controls UX — Apply Button

- [x] Split stretch state into local (slider display) and applied (what FitsImage renders)
- [x] Add Apply button — highlighted when pending changes exist, disabled when nothing to apply
- [x] Toggles (Auto/None, Linked/Unlinked) and Reset apply immediately — no Apply needed
- [x] Only manual slider adjustments require Apply
- [x] Remove 300ms debounce on stretch params
- [x] FitsImage shows spinner when src changes (Apply clicked)

### 2. Stats Caching

- [x] Per-key locking for image data cache — concurrent requests share a single load
- [x] Per-key locking for stats cache — concurrent requests share a single computation
- [x] `_resolve_auto_stretch()` accepts pre-computed stats to avoid redundant computation
- [x] Stats/stats-histogram endpoints use cached stats when available

### 3. Faster Median — `bottleneck`

- [x] Add `bottleneck` (BSD-2-Clause) for faster median computation
- [x] Replace `np.median()` with `bn.nanmedian()` in `_channel_stats()` and `_compute_lab_a_median()`

### 4. Histogram Subsampling

- [x] Subsample large images to ~2M pixels for histogram computation
- [x] 256-bin histogram is statistically identical at this sample size (0.015% max bin deviation)
- [x] Histogram computation: 7.9s → 0.05s for 91MP RGB images
- [x] Eliminate redundant histogram request — `histogramPending` prop prevents Histogram component from fetching independently when stats-histogram will provide data

### 5. GPU Acceleration (mlx)

- [x] Hook `set_gpu_enabled()` to settings PUT endpoint and startup lifespan
- [x] Integrate `get_array_module()` into `_channel_stats()` — GPU median, abs, mean, min, max
- [x] Integrate `get_array_module()` into `stretch_plane()` — GPU clip, rescale, MTF
- [x] Add `mlx` dependency (MIT) for Apple Silicon Metal acceleration
- [x] Add `mlx` to README acknowledgments and PLAN.md Library Reference

### 6. PNG Encoding

- [x] Reduce Pillow PNG `compress_level` from 6 (default) to 1 — local app, speed over size
- [x] PNG encoding: 3.6s → 2.5s for 91MP RGB

### Performance Results (91MP RGB XISF)

| Metric | Before | After | Speedup |
|--------|--------|-------|---------|
| Image endpoint | 7175ms | 3012ms | 2.4x |
| Stats-histogram endpoint | 10262ms | 1547ms | 6.6x |
| Total open time | 26741ms | 4724ms | 5.7x |

### New Dependencies

- `bottleneck` (BSD-2-Clause) — fast median computation via introselect algorithm
- `mlx` (MIT) — Apple Metal GPU acceleration for array operations

### 7. API Docs Page

- [x] New route `/api-docs` with `ApiDocsPage` component
- [x] Nav item in sidebar with Code icon
- [x] Swagger UI rendered in iframe with dark/light theme matching
- [x] Vite dev proxy for `/docs` and `/openapi.json`

### v0.6.1 Completion Criteria

- [x] All tests pass — 321 tests
- [x] Frontend builds (`npm run build`)
- [x] Ruff clean
- [x] Stretch Apply button works for linked and per-channel modes
- [x] GPU toggle in settings takes effect immediately (no restart)
- [x] README and PLAN.md Library Reference updated with new deps

---

## v0.7.0 — FITS Header Editing

**Status:** Complete
**Branch:** `v0.7.0/header-editing`

FITS header editing — modify existing keyword values/comments, add new keywords, delete keywords. Edits are written in place via astropy. Structural keywords (SIMPLE, BITPIX, NAXIS*, etc.) are protected.

### Tasks

- [x] `fits_io.update_header()` — in-place header editing via `mode="update"` + `flush()`
- [x] `PATCH /api/images/header` — batch edit endpoint with validation
- [x] Structural keyword protection (cannot edit/delete SIMPLE, BITPIX, NAXIS*, etc.)
- [x] Archive/virtual path rejection (edit only regular FITS files on disk)
- [x] Toggle edit mode in FitsHeaderTable (Edit/Done button)
- [x] Inline cell editing for value and comment columns
- [x] Inline key editing for newly added rows
- [x] Add keyword row with "Add to headers" button + auto-scroll
- [x] Delete keyword with undo support
- [x] Pending change tracking with visual highlights (modified/added/deleted)
- [x] Save/Discard with query invalidation and snackbar feedback
- [x] Save and Discard exit edit mode automatically
- [x] 20 backend tests (operations, validation, structural protection, on-disk verification)

### Also in this version
- [x] Fix archive image loading crash — concurrent cache bypass for BytesIO paths (v0.6.2 hotfix)

### v0.7.0 Completion Criteria

- [x] All tests pass — 342 tests
- [x] Frontend builds (`npm run build`)
- [x] Ruff clean
- [x] Code simplification pass

---

## v0.8.0 — Equipment Database Schema

**Status:** Complete
**Branch:** `v0.8.0/equipment-database`

Schema-only version: creates the full normalized equipment database with all tables, indexes, triggers, views, and seed tracking infrastructure. No API endpoints, no UI, no seed loader, no FITS resolver.

Based on the comprehensive schema revision spec reviewed by Claude Desktop.

### Design Decisions

- [x] Drop `custom_fields` JSON column and `custom_field_definition` table — add real columns via migration when needed
- [x] Collapse `filter_category` into a CHECK constraint on `filter_type.name`
- [x] Rewrite filter hierarchy: `filter_type` = role (narrowband_single, broadband_color, etc.), passbands on the physical `filter` via `filter_passband` table
- [x] Move native focal length/ratio/back_focus to `telescope_configuration` — every telescope must have at least one config with `is_native=1`
- [x] Replace `software.developer` with `software.manufacturer_id` FK
- [x] Replace `camera.connectivity`/`camera.usb_hub` text fields with `camera_interface` junction + `has_usb_hub`/`usb_hub_interface_id`
- [x] Add `connector_size` lookup table — used by camera, filter_wheel (both sides), OAG, guide_scope, telescope (junction)
- [x] Add `computer_type` lookup, rename `imaging_computer` → `computer`
- [x] Add `connection_interface.category` column (data, control, power, wireless)
- [x] Add `connector_size.diameter_mm` column

### Global Columns on Every Equipment Table

- [x] `created_at`, `updated_at` timestamps
- [x] `active` boolean (soft retirement — historical references preserved)
- [x] `source` ('seed' | 'user'), `seed_key`, `seed_hash` — seed tracking infrastructure
- [x] `updated_at` trigger per table
- [x] Partial unique index on `seed_key` per table

### Lookup / Reference Tables (9)

- [x] `manufacturer` — brands, referenced by all equipment types
- [x] `optical_design` — SCT, APO Triplet, RC, Newtonian, etc.
- [x] `mount_type` — GEM, Harmonic EQ, Alt-Az, Fork
- [x] `connection_interface` — USB 2.0, USB 3.0, USB-C, WiFi, ST-4, etc. (with category)
- [x] `connector_size` — M54, M48, T2, 1.25", 2", etc. (with diameter_mm)
- [x] `filter_size` — 1.25", 2", 36mm, 50mm
- [x] `computer_type` — imaging, processing, control, general
- [x] `filter_type` — closed vocabulary CHECK constraint: broadband_luminance, broadband_color, narrowband_single, narrowband_dual, narrowband_tri, uv_ir_cut, light_pollution, neutral_density, other
- [x] Seed `filter_type` rows in migration with `source='seed'`

### Core Equipment Tables

- [x] `sensor` — manufacturer FK, model_name, sensor_type CHECK (mono/color), pixel specs, bayer_pattern, dual_gain, UNIQUE(manufacturer_id, model_name)
- [x] `camera` — manufacturer FK, sensor FK, connector_size FK, has_usb_hub + usb_hub_interface_id, unity_gain
- [x] `camera_interface` junction table
- [x] `telescope` — manufacturer FK, optical_design FK, aperture (no focal length — that's on config)
- [x] `telescope_connector` junction table
- [x] `telescope_configuration` — telescope FK, config_name, reduction_factor, effective_focal_length/ratio, is_native + partial unique index
- [x] `filter` — manufacturer FK, filter_type FK, filter_size FK, peak_transmission, mounted_thickness
- [x] `filter_passband` — filter FK, line_name CHECK constraint, central_wavelength_nm, bandwidth_nm
- [x] `mount` — manufacturer FK, mount_type FK, payload, drive_type
- [x] `mount_interface` junction table
- [x] `focuser` — manufacturer FK, motorized, travel, steps, temp_compensation
- [x] `focuser_interface` junction table
- [x] `filter_wheel` — manufacturer FK, filter_size FK, camera_side_connector FK, telescope_side_connector FK
- [x] `filter_wheel_interface` junction table
- [x] `oag` — manufacturer FK, imaging_side_connector FK, guide_camera_connector FK
- [x] `guide_scope` — manufacturer FK, guide_camera_connector FK, aperture, focal_length
- [x] `computer` — manufacturer FK, computer_type FK
- [x] `software` — manufacturer FK, category CHECK constraint

### FITS Ingest Alias Tables

- [x] `camera_alias` — camera FK, alias TEXT UNIQUE, source CHECK, confirmed, first_seen_at, last_seen_at
- [x] `telescope_alias` — telescope FK, alias TEXT UNIQUE, source CHECK, confirmed, first_seen_at, last_seen_at
- [x] `filter_alias` — filter FK, alias TEXT UNIQUE, source CHECK, confirmed, first_seen_at, last_seen_at
- [x] `unresolved_equipment_observation` — for FITS ingest: records header values that couldn't be resolved

### Views

- [x] `filter_summary` — joins filter + filter_type + filter_passband with GROUP_CONCAT for passband lines

### Tests

- [x] Migration applies cleanly to empty database
- [x] Migration applies cleanly to existing v0.7.0 database
- [x] All CHECK constraints enforced (sensor_type, filter_type.name, line_name, etc.)
- [x] Partial unique indexes work (seed_key, is_native)
- [x] ON DELETE CASCADE propagates correctly
- [x] updated_at triggers fire
- [x] filter_summary view returns correct data
- [x] filter_type seed rows present after migration

### v0.8.0 Completion Criteria

- [x] All tests pass — 373 tests (29 new equipment schema tests)
- [x] Ruff clean
- [x] Migration script applies cleanly (IF NOT EXISTS throughout)
- [x] DB_SCHEMA.md and DB_SCHEMA_DDL.sql updated to match

---

## v0.9.0 — Equipment Management API + Core UI

**Status:** Done
**Branch:** `v0.9.0/equipment-management`

Full backend CRUD API for all equipment types. Frontend Equipment page with the three most complex categories (Cameras, Telescopes, Filters) to prove the pattern. Simpler equipment tabs follow in v0.9.1.

### Backend — API Endpoints

Pydantic models (`equipment_models.py`, 708 lines) and FastAPI CRUD router (`equipment.py`, ~2400 lines) for all equipment categories. All endpoints under `/api/equipment/`.

- [x] Lookup table CRUD: manufacturer, optical_design, mount_type, connection_interface, connector_size, filter_size, computer_type, filter_type (read-only)
- [x] Sensor CRUD: list, get, create, update, soft-delete (with manufacturer join)
- [x] Camera CRUD: list, get, create, update, soft-delete (with sensor + manufacturer + connector_size + interfaces joins)
- [x] Telescope CRUD: list, get, create, update, soft-delete (with configurations + connectors)
- [x] Telescope configuration CRUD: create, update, delete (scoped to parent telescope)
- [x] Filter CRUD: list, get, create, update, soft-delete (with passbands + filter_type + filter_size)
- [x] Filter passband CRUD: create, update, delete (scoped to parent filter)
- [x] Mount CRUD: list, get, create, update, soft-delete (with interfaces)
- [x] Focuser CRUD: list, get, create, update, soft-delete (with interfaces)
- [x] Filter wheel CRUD: list, get, create, update, soft-delete (with interfaces + connectors)
- [x] OAG CRUD: list, get, create, update, soft-delete
- [x] Guide scope CRUD: list, get, create, update, soft-delete
- [x] Computer CRUD: list, get, create, update, soft-delete
- [x] Software CRUD: list, get, create, update, soft-delete
- [x] Soft delete: DELETE sets `active=0`. `?include_retired=true` query param on list endpoints.
- [x] Migration 0006: `guide_sensor_id` FK added to camera table

### Frontend — Equipment Page (Core Tabs)

New nav item "Equipment" in the sidebar. TreeView sidebar navigation with grouped categories. v0.9.0 delivers the three most complex categories plus shared infrastructure.

- [x] Equipment page scaffolding with TreeView sidebar (all categories listed, unbuilt ones show "Coming soon")
- [x] Shared components: ManufacturerPicker, SensorPicker, LookupPicker, InterfaceMultiSelect, ConfirmDeleteDialog
- [x] Shared form utils: `parseOptionalFloat`, `parseOptionalInt`, `formatFilterType` in `lib/formUtils.ts`
- [x] **Cameras**: DataGrid with key columns (model, manufacturer, sensor, cooled, connector), add/edit dialog with sensor picker, interface multi-select
- [x] **Telescopes**: DataGrid with key columns (model, manufacturer, design, aperture, configs count), add/edit dialog with configuration accordions, connector multi-select
- [x] **Filters**: DataGrid with key columns (model, manufacturer, type, passbands summary, size), add/edit dialog with passband accordions

### Frontend — API Client

- [x] `frontend/src/api/equipment.ts` — TypeScript interfaces + fetch functions for all equipment CRUD (1043 lines)
- [x] Query invalidation on mutations
- [x] Shared types for all equipment entities (response + create interfaces)

### Tests

- [x] Backend: CRUD tests for each equipment type (create, read, update, soft-delete) — 45 new tests
- [x] Backend: validation tests (duplicate name 409, not found 404, CHECK constraints)
- [x] Backend: junction table and child table management tests (interface replacement, config uniqueness)
- [x] Frontend: build passes (1560 modules)
- [x] Full suite: 418 passed, 3 skipped

### v0.9.0 Completion Criteria

- [x] All tests pass (418 passed, 3 skipped)
- [x] Ruff clean
- [x] Frontend builds
- [x] Can add/edit/delete cameras, telescopes, and filters through the UI
- [x] Telescope configurations manageable via accordion sub-forms
- [x] Filter passbands manageable via accordion sub-forms
- [x] Soft delete works (retired equipment hidden from lists, still in DB)
- [x] All other equipment types have working API endpoints (tested) even if UI category is pending

---

## v0.9.1 — Equipment Management UI (Remaining Tabs)

**Status:** Done
**Branch:** `v0.9.1/equipment-ui`

Complete the frontend Equipment page with all remaining tabs, reusing the patterns established in v0.9.0.

### Architecture Improvements

- [x] Generic `EquipmentList<T>` component extracted — eliminates copy-paste scaffolding across all list views
- [x] Existing CameraList, TelescopeList, FilterList refactored to use EquipmentList (net -220 lines)
- [x] Error feedback added to all 12 form dialogs (catch block + Snackbar with error message)
- [x] Website columns render as clickable hyperlinks (Manufacturer, Software lists)

### Frontend — Remaining Tabs

- [x] **Sensors tab**: DataGrid + add/edit dialog (manufacturer, specs, bayer pattern, dual gain)
- [x] **Mounts tab**: DataGrid + add/edit dialog (manufacturer, mount type, payload, interfaces)
- [x] **Focusers tab**: DataGrid + add/edit dialog (manufacturer, motorized, steps, interfaces)
- [x] **Filter Wheels tab**: DataGrid + add/edit dialog (manufacturer, positions, filter size, connectors, interfaces)
- [x] **OAGs tab**: DataGrid + add/edit dialog (imaging/guide connectors, prism size)
- [x] **Guide Scopes tab**: DataGrid + add/edit dialog (guide connector, aperture, focal length)
- [x] **Computers tab**: DataGrid + add/edit dialog (manufacturer, computer type)
- [x] **Software tab**: DataGrid + add/edit dialog (manufacturer, category, website)
- [x] **Manufacturers tab**: DataGrid + add/edit (name, website as hyperlink, notes)
- [x] **Lookup Tables tab**: Accordion panel with inline CRUD for optical_design, mount_type, connection_interface, connector_size, filter_size, computer_type

### Bug Fixes

- [x] Telescope configuration `reduction_factor` defaults to 1.0 when empty (was sending null to NOT NULL column)

### v0.9.1 Completion Criteria

- [x] All tests pass (418 passed, 3 skipped)
- [x] Frontend builds (1576 modules)
- [x] Can add/edit/delete all equipment types through the UI ✅ User
- [x] All lookup tables editable ✅ User
- [x] Error messages shown on save failures ✅ User
- [x] No "Coming soon" placeholders remain

---

## v0.10.0 — Equipment Seed Loader + Admin Page

**Status:** Done
**Branch:** `v0.10.0/equipment-seed-loader`

Equipment seed loader that reads CSV files from the repo and populates the database on first run, with hash-based change detection to never overwrite user edits. Admin page for managing multiple databases with first-run setup wizard.

### Seed Loader

- [x] Hash function (`seed_loader/hash.py`) — SHA-256 contract v1, deterministic serialization, pinned test values
- [x] Seedable table registry (`seed_loader/registry.py`) — 29 tables (including filter_type) in dependency load order
- [x] CSV reader (`seed_loader/csv_reader.py`) — header validation, comment lines, FK seed_key column detection
- [x] Core loader (`seed_loader/loader.py`) — first_run/update modes, FK resolution, re-seed decision logic, junction/child handling, orphan detection
- [x] CLI entry point (`seed_loader/__main__.py`) — `python -m nightcrate.seed_loader` with --dry-run, --verbose, --json
- [x] 29 stub CSV files under `data/seed/` — header-only stubs for all tables, populated with test data for lookups + Fred's equipment
- [x] filter_type seeding moved from migration 0005 to CSV (no equipment data in migrations)
- [x] Auto-runs on app startup after migrations (sync connection, non-fatal)
- [x] 50 seed loader tests (hash + integration)

### Admin Page

- [x] App config module (`core/app_config.py`) — config.json read/write, tracks known databases + active DB
- [x] Dynamic DB_PATH (`db/session.py`) — hot-swap support via `set_db_path()`, no restart needed
- [x] Admin API (`api/admin.py`) — status, info, create, add existing, activate, remove (with optional file delete), browse, shortcuts, mkdir
- [x] First-run setup wizard — shows on startup when no DB configured, folder browser with shortcuts (Home/Documents/App Data) + new folder
- [x] Wizard handles three scenarios: fresh install, active DB unavailable (offers other available DBs), all DBs unavailable
- [x] Admin page — App Info section (config file, paths, versions) + Database Management (active DB card, other known DBs list, create/add/activate/remove)
- [x] Active database name shown in sidebar under NightCrate title
- [x] Remove dialog: "Remove from list only" or "Remove and delete file (irreversible)"
- [x] OTA rename (Telescopes → OTAs in sidebar and forms)
- [x] 13 admin API tests + 10 app config unit tests

### Seed CSV File Tracking

Lookup tables (populated):
- [x] `manufacturer.csv` — ZWO, Celestron, Optolong, Sony, Pegasus Astro, Open Source
- [x] `optical_design.csv` — SCT, APO Refractor, Newtonian, RC
- [x] `mount_type.csv` — German EQ, Harmonic EQ, Alt-Az
- [x] `connection_interface.csv` — USB 3.0, USB 2.0, WiFi, Ethernet
- [x] `connector_size.csv` — M54, M48, T2, 2 inch
- [x] `filter_size.csv` — 2 inch, 36mm, 1.25 inch
- [x] `computer_type.csv` — Imaging, Processing, Control
- [x] `filter_type.csv` — 9 standard types (moved from migration)

Equipment tables (test data):
- [x] `sensor.csv` — IMX571, IMX533
- [x] `camera.csv` — ASI2600MM Pro, ASI533MM Pro
- [x] `camera_interface.csv` — junction rows
- [x] `telescope.csv` — C11 EdgeHD
- [x] `telescope_connector.csv` — junction rows
- [x] `telescope_configuration.csv` — Native + 0.7x Reducer
- [x] `filter.csv` — Ha 7nm, OIII 6.5nm
- [x] `filter_passband.csv` — passband wavelength data
- [x] `mount.csv` — ZWO AM5
- [x] `mount_interface.csv` — junction rows
- [x] `software.csv` — N.I.N.A., PHD2

Empty stubs (to be populated):
- [ ] `focuser.csv`, `focuser_interface.csv`
- [ ] `filter_wheel.csv`, `filter_wheel_interface.csv`
- [ ] `oag.csv`, `guide_scope.csv`
- [ ] `computer.csv`
- [ ] `camera_alias.csv`, `telescope_alias.csv`, `filter_alias.csv`

### v0.10.0 Completion Criteria

- [x] All tests pass (488 passed, 3 skipped)
- [x] Ruff clean
- [x] Frontend builds
- [x] Seed loader populates equipment on first startup ✅ User
- [x] Re-seed preserves user-modified rows ✅ User
- [x] CLI works (--dry-run, --json) ✅ User
- [x] First-run wizard creates DB and transitions to app ✅ User
- [x] Admin page shows app info + database management ✅ User
- [x] Create/activate/remove databases works ✅ User
- [x] Hot-swap DB without restart ✅ User

---

## v0.10.1 — Seed Data Population + UI Improvements + Locations

**Status:** Done
**Branch:** `v0.10.1/seed-data-population`

Massive equipment seed data population, schema refinements, UI improvements, and new locations feature.

### Equipment Seed Data

OTAs (40 telescopes, 8 batches):
- [x] Celestron EdgeHD (800/925/1100/1400) with 0.7x reducer configs
- [x] Celestron RASA (8/11 V2) + Classic SCTs (C6/C8/C11) with f/6.3 reducer configs
- [x] Sky-Watcher Esprit (80ED/100ED/120ED) with 0.77x reducer config
- [x] Sky-Watcher Quattro (200P/250P/300P) with coma corrector configs
- [x] Sky-Watcher Evostar ED (72ED/80ED/100ED/120ED) with 0.85x reducer configs
- [x] Askar FRA (300 Pro/400/600), V60/V80 (split), 103APO, 107PHQ with flattener/reducer/extender configs
- [x] William Optics Cat series, GT81 IV, Z103, GuideStar 61 with P-FLAT6AIII configs
- [x] Sharpstar 15028HNT, 61EDPH II, 76EDPH, 94EDPH + Explore Scientific FCD100 series

Filters (74 filters, 7 batches):
- [x] Schema: filter_size_option junction table replacing filter_size_id on filter
- [x] Optolong narrowband (Ha/OIII/SII 3nm/6.5nm/7nm, L-eNhance, L-eXtreme, L-Ultimate, L-Para)
- [x] Optolong LRGB + light pollution + UV/IR + specialty (L-Pro, UHC, CLS, ND3.0, IR Pass 685)
- [x] Antlia narrowband (2.5nm Ultra, 3nm Pro, 3nm Pro Highspeed, 4.5nm EDGE, 7nm Prime + ALP-T dual-band)
- [x] Antlia LRGB-V Pro, LRGBR+ Dark (with R+ NIR), Triband RGB Ultra II, Quad Band ALP, 8-EL UHC
- [x] ZWO narrowband (Ha/OIII/SII 7nm Mark II + Duo-Band) + Premium LRGB + UV/IR Cut
- [x] Askar Colour Magic (C1/C2 budget, Super D1/D2 premium, Ultra E1/E2 3nm)

Cameras & Sensors (37 sensors, 101 cameras, 12 batches):
- [x] Schema: camera effective_* columns, hcg_threshold moved from sensor to camera
- [x] Sony IMX571 (APS-C) — ZWO ASI2600 Pro/Air/Duo, QHY268, Player One Poseidon, ToupTek ATR3CMOS26000
- [x] Sony IMX455 (full-frame) — ZWO ASI6200 Pro, QHY600, Player One Zeus, ToupTek SkyEye62
- [x] Sony IMX533 (1" square) — ZWO ASI533 Pro, QHY533, Player One Ares, ToupTek ATR533
- [x] Sony IMX585 (1/1.2" STARVIS 2) — ZWO ASI585 Pro/Air, QHY miniCAM8/5III585, Player One Uranus, ToupTek ATR585
- [x] Sony IMX294/IMX492 (4/3" dual-mode) — ZWO ASI294 Pro, QHY294 Pro, Player One Artemis, ToupTek ATR294
- [x] Sony IMX183 (1" legacy with amp glow) — ZWO ASI1600/183 Pro, QHY163/183 Pro
- [x] Sony IMX461/IMX411 (medium format) — ZWO ASI461MM Pro, QHY461/411 Pro
- [x] Small planetary/guide sensors (IMX174/178/290/462/464/662/678/715) — 22 cameras across ZWO/QHY/Player One
- [x] Sony IMX410 (full-frame 24MP) — ZWO ASI2400MC Pro, QHY410C Pro
- [x] Sony IMX485/IMX676 (niche) — ZWO ASI485MC, QHY5III676C, Player One Apollo-M Mini
- [x] Non-Sony: Panasonic MN34230 (ASI1600/QHY163), OnSemi AR0130 (ASI120 guide cameras)
- [x] SmartSens SC2210 standalone cameras — ZWO ASI220MM Mini, QHY5III200M
- [x] New connector_size: M63 (William Optics), usb_2_0_type_c interface
- [x] New manufacturers: SmartSens, Panasonic, OnSemi

### Schema Changes

- [x] `filter_size_option` junction table (filter × filter_size with mounted_thickness_mm)
- [x] Camera `effective_full_well_ke`, `effective_read_noise_lcg_e`, `effective_read_noise_hcg_e`, `effective_peak_qe_pct`, `hcg_threshold_gain` columns
- [x] Removed `hcg_threshold_gain` from sensor table
- [x] `R+` added to filter_passband line_name CHECK constraint
- [x] `location` table (migration 0007) with coordinates, timezone, Bortle, SQM, address fields
- [x] Seed loader child table re-seed fix (no longer crashes on UNIQUE constraint when parent updated)

### UI Improvements

- [x] Collapsible left nav sidebar with double-chevron toggle
- [x] Collapsible right sidebar (Image Viewer) with pinned chevron strip
- [x] Activity Console: draggable dialog, resizable, pop-out to separate browser window with auto-refresh
- [x] Activity Console moved from Image Viewer to global (AppShell)
- [x] Version number moved to title area next to "NightCrate"
- [x] Histogram: click-drag horizontal zoom with shaded selection, Reset Zoom button, stable vertical scale
- [x] Histogram: always open as Linear, Log/Linear centered, help section split into Image/Histogram
- [x] Stretch sliders: Shift+drag fine mode (10x sensitivity reduction), hover-to-show indicators
- [x] Stretch sliders: click-on-track disabled (drag thumb only)
- [x] Equipment lists: manufacturer-first column order with default sort
- [x] Telescope configuration pills with hover popover showing specs
- [x] Camera sensor links with hover popover and click-to-navigate (with auto-scroll)
- [x] Equipment sidebar seed data disclaimer footnote
- [x] Consistent toolbar heights (Browse, file path, Open buttons)
- [x] File path Autocomplete dropdown indicator (forcePopupIcon)
- [x] Admin "Add Existing" dialog Browse button height alignment
- [x] Aberration inspector slider label consistent spacing
- [x] OpenAPI/Swagger docs reorganized with proper tags, descriptions, and section ordering
- [x] Software list: name-first column order (unlike hardware lists)

### Locations Feature

- [x] Database table (migration 0007) with lat/lon, elevation, timezone, Bortle, SQM, address, is_default
- [x] Full CRUD API with set-default endpoint
- [x] Locations page with card-based layout, star icon for default, Bortle/SQM chips
- [x] Browser geolocation detection (Use My Location button)
- [x] Reverse geocoding via OpenStreetMap Nominatim (address from coordinates)
- [x] Forward geocoding via Nominatim (coordinates from address dialog)
- [x] Elevation lookup via Open-Meteo
- [x] Fetch-with-retry for rate-limited APIs
- [x] OpenStreetMap iframe map preview
- [x] Clear Outside forecast link per location
- [x] Bortle/SQM auto-conversion (enter one, get the other)
- [x] Clear Outside link for Bortle class lookup
- [x] Nav item with pin icon between Equipment and Settings

### Easter Eggs

- [x] Shared EasterEggWand component with shuffled no-repeat queue
- [x] Home page: 75 astrophotography hobby jokes ("Words of wisdom")
- [x] Locations page: 76 weather incantations with sparkle animation ("Cast a clear sky incantation")
- [x] Image Viewer: 75 image commentaries ("Expert analysis")

### v0.10.1 Completion Criteria

- [x] All tests pass (487 passed, 3 skipped)
- [x] Ruff clean
- [x] Frontend builds
- [x] Code review: route ordering fix, dedup, drag perf fix

---

## v0.11.0 — Astronomy Weather Forecast

**Status:** Done
**Branch:** `v0.11.0/weather-forecast`

Telescopius-style weather forecast dashboard for imaging session planning. 7-day daily cards + hourly detail view with darkness bar, moon polyline, score factor grid, and weather details.

### Data Sources & Services

- [x] Open-Meteo forecast API client (`services/weather.py`) — hourly temperature, dew point, humidity, cloud cover (total/low/mid/high), wind, visibility, precipitation
- [x] Open-Meteo ECMWF API for PWV (`fetch_pwv`) — total column integrated water vapour from ECMWF IFS 0.25° model
- [x] Open-Meteo Air Quality API for AOD (`fetch_air_quality`) — aerosol optical depth (CAMS Global, 3-hourly)
- [x] Pressure-level wind data for seeing model (200/300/500 hPa wind speed + geopotential heights)
- [x] Weather cache (`weather_cache` table, migration 0008) — TTL-based, supports forecast/archive/openmeteo_aq/ecmwf_pwv sources
- [x] Supplementary data fetched separately with `nearest_match` timestamp alignment and non-fatal cache

### Astronomy Service (`services/astronomy.py`)

- [x] Moon phase computation (Meeus method — barycentric positions, phase angle, illumination)
- [x] Twilight boundary detection (civil/nautical/astronomical, interpolated from 1-minute dense sampling)
- [x] Moonless dark hours (5-minute moon altitude sampling during darkness window)
- [x] Hourly astro data (moon altitude, darkness category per hour)
- [x] Moon altitude polyline (10-minute sampling for smooth rendering)
- [x] Polar latitude graceful degradation — all event fields Optional, independent per-crossing detection
- [x] `deepest_darkness_reached` and `no_imaging_window` fields
- [x] Renamed `phase_angle_deg` → `elongation_deg` in `MoonInfo`

### Seeing Model (`services/seeing.py`)

- [x] Surface model (JAG Lab methodology): temperature-dew point spread, wind, humidity, thermal stability
- [x] Wind-shear model (Trinquet & Vernin 2006, Cherubini & Businger 2013): jet stream + vertical shear at pressure levels, blended with surface model (60/40 split)

### Transparency Service (`services/transparency.py`)

- [x] Three-tier scoring: primary (PWV+AOD+humidity+visibility, 50/25/15/10), fallback (no AOD), degraded (no PWV)
- [x] PWV score: <5mm=100, 35mm=10, >40mm=0
- [x] AOD score: <0.05=100, 0.6=1, >0.6=0 (steep penalty for wildfire smoke/dust)

### Dew Service (`services/dew.py`)

- [x] Risk classification: low (>5°C spread), moderate (3-5°C), high (1-3°C), critical (<1°C)
- [x] Safe window computation for daily cards: all_night / until HH:MM / after HH:MM / none

### Imaging Quality Score (`services/imaging_quality.py`)

- [x] Weighted sky clarity from cloud layers (low×1.0, mid×0.9, high×0.6)
- [x] Cloud gating factor: √(sky_clarity/100) multiplied on all other factors
- [x] Broadband weights: Sky 35% / Seeing 25% / Transparency 15% / Moon 15% / Wind 10%
- [x] Narrowband weights: Sky 40% / Transparency 25% / Seeing 25% / Wind 10%
- [x] Quality labels: Excellent (80+), Good (55+), Marginal (30+), Poor (0+)

### API (`api/weather.py`, `api/weather_models.py`)

- [x] `GET /api/weather/forecast` — 7-day daily summaries with all scores
- [x] `GET /api/weather/hourly` — sunset±1h hourly detail with moon polyline
- [x] `GET /api/weather/methodology` — help text
- [x] Daily response: imaging quality, sky clarity, transparency, seeing, moon, wind calm, dew safe window, moon phase name, darkness info
- [x] Hourly response: all scores + raw weather + PWV + AOD + dew risk + darkness category
- [x] Settings: `weather_cache_ttl_hours` (default 6), `weather_moon_penalty` (default true)

### Frontend — Weather Page

- [x] Location selector dropdown (from saved locations)
- [x] "Include moon in quality score" toggle
- [x] 7-day daily cards: quality badge, factor bars (Sky Clarity, Transparency, Seeing, Moon Quality, Wind Calm), moon phase icon + name, moonless/dark hours, sun/astro times, dew-safe line, precipitation, no-imaging-window handling
- [x] Hourly timeline (D3): darkness gradient bar with twilight markers, moon altitude polyline (gold, clipped at horizon), unified hover tooltip
- [x] Score factor grid: Imaging Quality (emphasized), Sky Clarity, Transparency, Seeing, Moon Quality, Wind Calm — daylight padding hours grayed out
- [x] Weather details grid: Precip %/mm, Cloud layers, PWV, AOD, Temp, Dew Point, Humidity, Wind, Dew Risk (colorblind-safe blue palette), Moon %/Alt
- [x] Methodology accordion with factors table, cloud gating explanation, quality labels, dew risk definitions, data sources
- [x] Moon phase icon (terminator ellipse rendering from illumination percentage)
- [x] Quality badge component (sequential blue palette — darker = better)
- [x] Easter egg wand with astrophotography weather incantations

### Test Coverage Push

Comprehensive test quality improvement: from 564 tests / 77% coverage to 936 tests / 92% coverage. Added reference value regression tests, boundary conditions, error handling, constraint violations, polar latitude edge cases, and API schema validation. Found and fixed 1 bug (unvalidated date parameter on `/hourly` endpoint).

Key coverage achievements:
- 18 modules at 100%, 10 modules at 95%+, overall 92%
- `api/equipment.py`: 59% → 94% (the largest single gap, 1,398 statements)
- `api/locations.py`: 49% → 94%
- `main.py`: 48% → 95%
- `api/weather.py`: 72% → 96%
- Remaining gaps are platform-specific code (GPU detection, OS volume listing) and file-type branches requiring complex test fixtures

### Post-Review Fixes & Enhancements

- [x] Hourly endpoint: add `include_moon` query param (was reading only saved setting, ignoring UI toggle)
- [x] Weather page: moon toggle initializes from saved `weather_moon_penalty` setting
- [x] Hourly grid: Moon Quality row grayed out when moon excluded (matches daily card)
- [x] Hourly timeline: location timezone via `localTimeToMinutes` + `Intl.DateTimeFormat` (was using browser timezone)
- [x] Geographic timezone decoupling: `timezonefinder` derives geo_timezone from coordinates; astronomy uses geo_tz, display uses user's tz
- [x] `GET /api/locations/geo-timezone` endpoint for real-time coordinate lookup
- [x] `GET /api/locations/timezones` endpoint for backend-driven timezone dropdown
- [x] Location form: read-only "Coordinates timezone" field, auto-populates display timezone on create
- [x] Weather page: timezone mismatch indicator when display tz ≠ geo tz
- [x] Weather page reads settings from Zustand store (instant unit/moon toggle sync with Settings page)
- [x] Methodology accordion expand button adjacent to text (was floating far right)
- [x] Temperature display: primary unit larger, secondary unit smaller and muted
- [x] Colorblind-safe error text (warning.main instead of color="error")
- [x] Clear Outside link always visible when coordinates filled in (was hidden once Bortle set)

### v0.11.0 Completion Criteria

- [x] All backend tests pass (951 passed, 3 skipped)
- [x] Ruff clean, bandit clean (no new issues)
- [x] Frontend builds (TypeScript + Vite)
- [x] Test coverage push: 77% → 92% overall, no module below 75%
- [x] Code review (4 issues found and fixed)
- [x] Code simplification pass (extracted shared weather color helpers, eliminated redundant get_settings/location calls)
- [x] Visual testing in browser
- [x] Geo_timezone cross-timezone tests (15 new tests)

---

<!-- Old inline seed loader spec (sections 1-12) removed — implemented in v0.10.0.
     Full spec preserved at docs/superpowers/specs/2026-04-08-equipment-seed-loader-design.md -->


## v0.12.0 — Rigs + My Equipment + Guide Calculators

**Status:** Done
**Branch:** `v0.12.0/rig-builder`

Four feature clusters shipped together: the Rig Builder, a "My Equipment" ownership flag with sidebar surfacing, the Guide System suitability calculator, and the v2 tabbed rig detail panel with the Guiding Tolerance calculator and a tree-view Equipment tab.

Specs: `docs/superpowers/specs/2026-04-15-rig-builder-design.md`, `2026-04-16-my-equipment-design.md`, `2026-04-16-guide-suitability-design.md`. Implementation plans: `docs/superpowers/plans/2026-04-15-rig-builder.md`, `2026-04-16-my-equipment.md`.

### Rig Builder

- [x] Migration 0009 — `rig`, `rig_filter_slot`, `rig_software` junction, `rig_summary` view (edited in place to add `telescope_id`; migration 0010 recreates the view for already-migrated DBs)
- [x] Location seeing fields (`typical_seeing_low_arcsec`, `typical_seeing_high_arcsec`) on migration 0007 (edit in place, pre-release policy)
- [x] `services/rig_calculators.py` — pure math (image scale, FOV, Dawes/Rayleigh, sensor coverage, sampling assessment) with pinned regression tests for Fred's actual equipment
- [x] Full CRUD API under `/api/rigs`: list / get / create / update / soft-delete / restore / clone / calculators / equipment-options
- [x] Default-rig flag with single-active enforcement
- [x] Filter-slot sub-resource with wheel-size validation
- [x] `rig_software` junction (multi-select software per rig)
- [x] Warnings system on `RigOut.warnings` (retired equipment, guide-camera-equals-imaging-camera, both wheel + single filter)
- [x] Frontend `RigsPage` — card grid + expansion detail panel
- [x] `RigFormDialog` with equipment dropdowns grouped by manufacturer, software multi-select, `FilterSlotGrid` for wheel slots
- [x] `CalculatorPanel` with `SamplingChart` (pure D3, theme-aware, blue/orange/teal colorblind-safe palette)
- [x] Seeing slider (0.5″–6.0″) under the Sampling Assessment section, client-side binning recommendations
- [x] Nav reorder: Home, Locations, Weather, Rigs, Equipment, Image Viewer, Settings, Admin, API Docs

### My Equipment

- [x] `is_mine INTEGER NOT NULL DEFAULT 0 CHECK(...)` added to 10 owned equipment tables in migration 0005 (inline edit)
- [x] Partial index `idx_<table>_mine ... WHERE is_mine = 1` on each of the 10 tables
- [x] `<Type>Create` / `<Type>Update` / `<Type>Response` Pydantic models gain `is_mine` for all 10 owned types; TS interfaces updated
- [x] List endpoints accept `?mine=true` and order `is_mine DESC` by default
- [x] `POST /api/equipment/<type>/{id}/mine` toggle endpoint per type (10 endpoints, shared `MineToggle` body model)
- [x] `GET /api/equipment/mine-counts` — single round trip returning per-type counts for sidebar rendering
- [x] INSERT statements for all 10 create endpoints persist `is_mine` (caught during TDD — was originally missing)
- [x] Seed loader regression test: `is_mine=1` survives re-seed without triggering hash mismatch
- [x] Frontend `EquipmentList` — clickable star column (leftmost), optimistic toggle with Snackbar rollback, invalidates list + mine-counts
- [x] `mineOnly` prop wires `?mine=true` through TanStack Query; custom empty state for the filtered view
- [x] Shared `MineCheckbox` component wired into all 10 equipment form dialogs
- [x] `EquipmentPage` routes `my-*` slugs to per-type list wrappers with `mineOnly={true}`
- [x] `EquipmentSidebar` — new "MY EQUIPMENT" group at top, reactive sub-items driven by `mine-counts` (hides sub-items for unused types; friendly empty state when zero owned)
- [x] Rig-builder Autocompletes (`RigFormDialog`, `FilterSlotGrid`) surface owned equipment as a "My Equipment" virtual group at the top with a blue star indicator; owned items also appear in their manufacturer group with the same star
- [x] Shared `withMineGroup` helper in `components/rigs/mineGroup.ts`

### Guide System calculator (guide suitability)

- [x] `compute_guide_suitability` pure-math function + `GuideSuitability` service dataclass
- [x] Pydantic `GuideSuitability` model; breaking change — removed top-level `guide_image_scale_arcsec_per_pixel` / `guide_field_of_view_arcmin` from `RigCalculators`, nested under `guide_suitability: GuideSuitability | None`
- [x] Mode resolution — `guide_scope` mode uses guide scope focal length; `oag` mode uses main scope's `effective_focal_length_mm`
- [x] Effective guide precision (arcsec) + G-ratio + effective error in main pixels
- [x] Four rating bands on `effective_error_main_pixels`: Excellent ≤0.6, Good ≤1.0, Marginal ≤1.2, Poor >1.2
- [x] 6″/pixel absolute scale cap (applies to binned scale; forces Poor with `rating_reason='scale_cap'`)
- [x] Mode-specific caveats (differential flexure for guide-scope; off-axis star quality for OAG)
- [x] Two new query params: `guide_binning` (1–4, default 1), `centroid_accuracy_pixels` (0.05–0.5, default 0.2)
- [x] Two new warnings — missing guide-scope focal length; orphan guide camera with no optical path
- [x] Frontend `GuideSuitabilityPanel` — metrics table, rating chip (blue/light-blue/light-orange/orange), mode-aware subtitle, advanced disclosure with centroid-accuracy slider
- [x] Frontend `GuideSuitabilityChart` — pure D3 horizontal bar chart (main pixel vs guide error) with threshold markers at 0.6/1.0/1.2 px, scale-cap annotation when triggered
- [x] Shared `frontend/src/lib/rigColors.ts` — `RIG_BLUE`/`RIG_ORANGE`/`RIG_TEAL` + light variants, `samplingColor()` + `ratingColor()` helpers; SamplingChart refactored to import from it

### Calculators v2 — tabbed panel, Equipment tree, Guiding Tolerance

- [x] Rig detail panel refactored into three tabs: Equipment / Imaging / Guiding (Guiding disabled when no guide camera)
- [x] Location dropdown moved to the rig-name header row (single source of truth, flows to every calculator)
- [x] Default tab is Equipment (clicking a rig opens directly to its full details)
- [x] **Equipment tab as tree + detail pane** — left: SimpleTreeView grouped Imaging / Optics / Tracking / Accessories / Computing (mirroring the main Equipment sidebar); right: full detail for the selected item. Multi-item categories (filters, software, cameras when both imaging and guide present) expand to per-item leaves. Fetches full equipment objects via `/api/equipment/<type>/{id}` in parallel; TanStack Query caches across opens. Responsive (stacks below the tree on small screens).
- [x] Migration 0010 — `DROP VIEW; CREATE VIEW rig_summary` adding `telescope_id` so the Equipment tab can fetch the full telescope record directly (idempotent on fresh DBs that got the updated 0009)
- [x] `RigOut.telescope_id` exposed; TS type updated
- [x] `compute_guiding_tolerance` pure-math function + `GuidingTolerance` service dataclass + Pydantic/TS types
- [x] Tolerance thresholds: 0.5× (Tight), 1.0× (Acceptable), 1.5× (Noticeable) of the binned main scale
- [x] Binning-aware via new `image_binning` query param (1–4, default 1) on `GET /api/rigs/{id}/calculators`
- [x] Guide system comparison: `current_guide_precision_arcsec` vs thresholds → `guide_system_within_tight` / `_within_acceptable` / `headroom_arcsec`
- [x] Plain-language interpretation line generated server-side
- [x] Guiding tab has **two sub-tabs** (Guide System / Guiding Tolerance) each with its **own** binning selector above them — guide-camera binning drives Guide System, imaging-camera binning drives Guiding Tolerance; Imaging tab's binning is independent (purely display-side)
- [x] Imaging-tab binning selector renamed to "Imaging camera binning" with inline layout matching the Guiding tab controls
- [x] `GuidingTolerancePanel` — thresholds table (Tight / Acceptable / Over budget), shaded-zone visualization with current-precision marker, interpretation line, "Image Scale" metric row matching Imaging tab style
- [x] `CalculatorAboutSection` — shared collapsed-by-default disclosure; attribution and methodology for Guide Suitability (astronomy.tools, Open PHD Guiding, Stan Moore) and Guiding Tolerance (Cloudy Nights community rule of thumb) with external links
- [x] `RigWarning.severity` field (`"error"` | `"info"`, default `"error"`) on Pydantic + TS — reserved for future info-level advisories
- [x] Sub-exposure calculator (Robin Glover) was added mid-session then **reverted entirely** — the spec-sheet approximations (peak QE, spectrally flat sky, zero atmospheric extinction) produced numbers that didn't track reality. Removed all Pydantic/TS types, service functions, endpoint param, warnings, and unit tests. `RigWarning.severity` was kept for future use.

### v0.12.0 Completion Criteria

- [x] All backend tests pass (1121 passed, 3 skipped)
- [x] Ruff / format / bandit clean; frontend builds
- [x] New module coverage: `rig_calculators.py` 99%, `rig_models.py` 100%, `rigs.py` 90%, `equipment.py` 94% (overall project 94%)
- [x] Edge-condition tests added for `image_binning` query validation, guiding-tolerance linear scaling with binning, update-rig duplicate-name 409 path, retired-equipment warnings, guide-scope missing focal length, guide-camera-without-path orphan warning, mine-flag preservation across re-seed, rating-band thresholds (excellent/good/marginal/poor), 6″/px scale-cap precedence
- [x] Migration policy followed — pre-release inline edits to 0005 and 0007; added 0009 and 0010; seed CSVs unchanged

---

## v0.12.1 — Calculators + Maintenance & Architectural Review

**Status:** Done
**Branch:** `v0.12.1/maintenance-ui-polish`

Two halves: a new Calculators mini-app (12 astronomer/astrophotographer
utilities, each backed by an API endpoint so they're usable from any
client), and a maintenance pass that actioned 13 of 25 findings from a
full senior-engineer review of the Python backend + SQL schema.

### Calculators feature

- [x] Nav entry + routes under `/calculators[/:calcId]`, Equipment-style sidebar with four groups (Coordinates & Time, Angles & Distances, Imaging Math, Sky Conditions)
- [x] 13 backend endpoints under `/api/calculators/*`: lat/long sexagesimal (forward + reverse), RA/Dec ↔ Alt/Az (astropy SkyCoord + AltAz transform, location-aware), sidereal time, tonight, angular unit conversion, linear unit conversion, pixel scale, FOV, file size, airmass (Kasten-Young), SQM/Bortle/NELM, temperature
- [x] Shared `CalculatorLocationBar` — location-aware calculators (RA/Dec↔Alt/Az, LST, Tonight) dropdown-select any saved Location, default to the `is_default` row
- [x] 12 React calculator components, all consuming the backend API (no client-side math beyond live tick for clocks)
- [x] Drag-to-reorder Clocks view (dnd-kit) with the chosen order persisted to the `settings` table
- [x] Coordinate-format service (`services/coordinate_format.py`) with sexagesimal formatter used by Locations sexagesimal display fields
- [x] Two additional clocks: local time for the selected Location's Display Timezone and Location Timezone
- [x] Rig picker on Pixel Scale / Field of View / File Size — `RigPickerMenu` loads focal length / pixel size / sensor dims / ADC bit depth from the selected rig (load-defaults-then-editable)
- [x] KaTeX math rendering (`katex`, `react-katex`, MIT) for formulas in Pixel Scale, Field of View, File Size, Airmass (Kasten-Young), SQM/Bortle/NELM, Temperature, and the Weather methodology accordion
- [x] Migration 0013 extends `rig_summary` view with `sensor_adc_bit_depth` so File Size can auto-select 16- vs 32-bit storage from the rig's camera sensor

### Settings table redesigned (KV)

- [x] Migration 0011 — `settings(id, data JSON)` singleton reshaped into `settings(key, value_json, updated_at)` key-value table
- [x] `core/config.py` — Pydantic `Settings` still the source of truth; load path merges KV rows + skips bad JSON + falls back to defaults on ValidationError
- [x] `test_config.py` rewritten for the new schema — 14 tests including corrupt-single-row, unknown-key-ignored, type-drift-returns-defaults, empty-table, upsert-not-duplicating, updated_at-refresh, composite and null round-trips
- [x] Settings page — new "Forecast cache" row showing row count + KB with Clear All button
- [x] `DELETE /api/weather/cache` + `GET /api/weather/cache/stats` endpoints

### Locations polish

- [x] Clear Outside Bortle/SQM scraper (`GET /api/locations/clear-outside`) — regex-extracts `Est. Sky Quality: NN Magnitude. Class N Bortle` from the forecast HTML; NightCrate stores SQM and derives Bortle from it
- [x] Sexagesimal lat/lon display in detail panel + live editor helperText; decimal in parentheses in the muted text.secondary gray
- [x] Elevation shown in the user's preferred unit (ft for imperial, m for metric) with the other unit parenthesised in gray
- [x] UTC offset shown next to each timezone in the detail panel
- [x] Display Timezone / Location Timezone in the edit form, with Location Timezone locked behind a warning dialog (users rarely want to override the coordinate-derived value)
- [x] Location detail slide-up panel with embedded OSM map, mount delayed until `onEntered` so the map tiles fill the final iframe width
- [x] `geo_timezone` field on `LocationCreate` / `LocationUpdate` — user override wins over `timezonefinder` auto-derivation
- [x] Location soft-delete: migration 0012 adds `active` column, restore endpoint, `?include_retired` list param. Pre-empts v0.13 session-ingestion landmine (hard-delete of a referenced location)

### Activity console + logging

- [x] `[open-meteo]` + `[weather-cache]` structured log lines; `NIGHTCRATE_LOG_LEVEL` env var (INFO default) drives verbosity
- [x] `X-Activity` header sanitiser — non-Latin-1 chars (em-dashes, Unicode in rig names) stripped before `Headers.set()` so the header doesn't throw
- [x] Page-level activity labels set in AppShell on route change; per-page action labels on Weather (location + date), Rigs (rig open), Equipment (sub-category)
- [x] Activity Console close-X added to the dialog title
- [x] Forecast endpoint fires all three Open-Meteo sources (weather + PWV + AOD) concurrently via `asyncio.gather`

### Equipment

- [x] Column-filter dropdowns on common manufacturer column + per-type (Cameras: sensor, cooled; OTA: optical design; Filters: type, passbands; Mounts: type; Focusers: type, motorized; Filter Wheels: filter size, positions; Software: category)
- [x] Camera model names get a space after ASI/QHY/ATR prefixes in the seed CSV (80 rows updated)
- [x] Software Autocomplete in rig builder no longer duplicates starred items into a top "My Equipment" group (other equipment types still do)

### UI bug fixes

- [x] Tonight at a Glance: backend returns `HH:MM` strings already in the display timezone; frontend was treating them as ISO-UTC and showing em-dashes. Dropped `formatClockInTz` and passed through directly
- [x] JSX Unicode-escape sweep — `label="\u00B0C"` (and equivalents on Field of View, Airmass, SQM/Bortle, Pixel Scale) in JSX attribute form doesn't escape; wrapped in `{...}` expressions across 5 calculator files
- [x] `&approx;` isn't in React's named-entity table; replaced with `{"\u2248"}` in FileSize and LinearUnits calculators
- [x] Native form controls (date-input popup, scrollbars) now match theme via `MuiCssBaseline.body.colorScheme = "dark"/"light"`

### Code review + security hardening

- [x] Soft-delete filter added to `/api/calculators/*`, `/api/weather/*`, `/api/rigs/*` location helpers — migration 0012 added the `active` column but three downstream consumers weren't threaded through (reviewer-caught, commit `3740537`)
- [x] `SqmBortleCalc` error Alert downgraded from red → amber per colorblind palette (commit `3740537`)
- [x] Bandit annotation pass — 62 pre-existing false positives (59 B608 f-string SQL with internal allow-list tables; 2 B110 best-effort try/except fallbacks; 1 B311 `random.uniform` for HTTP retry jitter) annotated with per-call `# nosec`. Post-pass: 0 Low / 0 Medium / 0 High (commits `81c386e`, `9c15f54`)

### Admin

- [x] Create-DB workflow auto-activates the new DB + reloads
- [x] Database list alphabetical; active row inlined (no separate banner) with Activate/Remove disabled on the active row

### Architectural review pass (13 of 25 findings actioned)

- [x] `api/_common.py` — shared `row_to_dict`, `bool_fields`, `strip_seed`, `integrity_guard` context manager replacing ~44 `"UNIQUE" in str(exc)` sites via `sqlite_errorname` structured check
- [x] `integrity_guard` extended with `constraint_map` (dispatch on partial-index name) and `check_detail` (for `SQLITE_CONSTRAINT_CHECK`); 4 special-case blocks in `equipment.py` (telescope native-config, software category) collapse into guarded `with` blocks
- [x] `services/path_resolver.py` — `resolve_path`, `file_type`, `file_type_from_ext`, `detect_tiff_type_from_buf` moved out of `api/images.py`; `api/aberration.py` no longer imports privates from a sibling router
- [x] `services/http_client.py` — uniform 30s timeout, one 500ms-backoff retry on transient failures (`TimeoutException`, `ConnectError`, 5xx), structured logging. All 4 outbound HTTP sites migrated
- [x] `services/weather.py:NearestMatchIndex` — bisect-based O(log n) lookup over pre-parsed sorted timestamps; built once per forecast, reused across ~168 hour computations. Previous O(n) linear scan with per-call `datetime.fromisoformat` was ~100ms of wasted CPU per forecast
- [x] `LocationBase` — Create/Update share field definitions + validators instead of duplicating 80 lines
- [x] Startup maintenance blocks: silent `except Exception: pass` replaced with `logger.warning(exc_info=True)`; narrowed to `(sqlite3.Error, OSError)` tuple constant (sidesteps py314 ruff-format multi-exception bug); latent `app_settings` scoping bug fixed
- [x] Seed-loader exception narrowed to `(sqlite3.Error, OSError, ValueError)` — coding bugs now crash loudly
- [x] `api/images.py` — 8 bare `except Exception → HTTP 500` blocks gained `logger.exception(...)` so server bugs leave a traceback
- [x] `idx_camera_guide_sensor` added to migration 0006 (inline, pre-release policy)
- [x] README threat-model section documenting the single-user local-first posture

### Skipped with rationale (documented in commit message of review batch)

Items #3 (0011 transactional wrapping — yoyo already handles it), #4 (code-gen seed-tracking DDL), #5 (`rig_summary` view), #11 + #12 (`Depends(get_db)` refactor — no concrete forcing function), #17 (closed-vocab CHECK → lookup tables), #19 (composite sort indexes), #25 (`_build_calculators` indirection). #2 (equipment factory) explicitly deferred to a future branch — preparatory work (#1, #20) completed, so the next round starts from a stronger base.

### v0.12.1 Completion Criteria

- [x] All backend tests pass (1345 passed, 3 skipped)
- [x] Ruff / format / bandit clean (0 Low / 0 Medium / 0 High after per-call `# nosec` annotations for pre-existing false positives); frontend builds
- [x] Coverage: `core/config.py` 100%, `services/weather.py` 100%, `services/coordinate_format.py` 100%, `services/calculators.py` 99%, `api/calculators.py` 96%, `api/locations.py` 92%, `api/weather.py` 84%
- [x] 127-test calculators edge-cases suite, 15-test Clear Outside scraper suite, 24-test coordinate format suite, 5-test weather cache suite
- [x] New migrations: 0011 (settings KV), 0012 (location soft-delete), 0013 (rig_summary ADC bit depth); in-place pre-release edits to 0006
- [x] Dependency additions: @dnd-kit/core + /sortable + /utilities (MIT) for Clocks drag-to-reorder; `katex` + `react-katex` + `@types/react-katex` (MIT) for math rendering in calculator About sections; registered in README + PLAN

---

## v0.12.2 — Equipment Factory Refactor

**Status:** Done
**Branch:** `v0.12.2/equipment-factory`

Internal refactor of `api/equipment.py` (2,749 lines, 76 routes) to
consolidate duplicated CRUD patterns into shared factories. Addressed
item #2 from the v0.12.1 architectural review, which was deferred
until the shared helpers from #1 and #20 were in place. No user-visible
changes; zero change to API surface; all 1,345 tests stayed green.

Outcome: `api/equipment.py` went from 2,749 → 1,416 lines (−48%); the
new `api/equipment_factory.py` is ~300 lines. Combined equipment code
dropped from 2,749 → ~1,720 lines (−37%). Coverage on `equipment.py`
went from 96% → 98%.

### Phase A — Lookup-table factory

- [x] Coverage baseline recorded (`equipment.py` 96%, 1,355 stmts) before touching code
- [x] `build_lookup_router(...)` — single factory emitting list / get / create / update / soft-delete for the 9 lookup tables: `manufacturer`, `optical_design`, `mount_type`, `connection_interface`, `connector_size`, `filter_size`, `form_factor`, `focuser_type`, `filter_type`
- [x] Each lookup collapses to ~10 lines of config (table name, label, Create/Update/Response models). INSERT columns introspected from the Create model — no hand-written column list
- [x] ~655 lines → ~90 lines in this phase (9 × 5 endpoints collapsed to 9 factory calls)
- [x] All existing tests green; URL shape, status codes, conflict messages, return shapes preserved

### Phase B — Equipment-table factory (mid-complexity CRUD types)

- [x] `build_equipment_router(...)` covering 4 interface-junction types: `camera`, `mount`, `focuser`, `filter_wheel`. Factory handles the junction rebuild (via `executemany`), is_mine toggle, bool-field coercion
- [x] Same factory covering 3 simple equipment types: `computer`, `oag`, `guide_scope` — plain CRUD + `is_mine`, no junction
- [x] `software` handled via the same factory + a `check_detail_fn` hook for the `category` CHECK constraint → 422 response
- [x] Per-type `response_builder` callback for the nested response shape (manufacturer, interfaces, per-type lookups). The factory does NOT try to genericize nested joins — each type's response builder stays explicit
- [x] ~1,200 lines → ~90 lines in this phase (8 × 6 endpoints collapsed to 8 factory calls + 8 preserved `_build_X_response` helpers)

### Incremental improvements (from simplification review)

- [x] `_common.get_or_404` shared helper — previously inlined in every router (`equipment.py`, `rigs.py`, `locations.py`, `calculators.py`, `weather.py`). Factory + equipment.py now use the shared version; removing the local `_get_or_404` alias in `equipment.py` renamed 51 call sites
- [x] Junction rebuild uses `await conn.executemany(sql, rows)` instead of an await-in-loop — saves 3–4 round-trips per rebuild on typical interface counts
- [x] Single commit per CREATE (was two: one after INSERT, one after junction inserts). Transactional correctness + one less round-trip
- [x] PUT short-circuit when the body is empty AND no `interface_ids` — returns the existing row immediately instead of re-reading
- [x] `interface_junction_table` + `interface_fk_column` grouped into a single `interface_junction: tuple[str, str] | None` parameter

### Explicitly NOT in scope (kept hand-written)

- `sensor` — unique shape (no `is_mine`, no junction, no children); factoring it in would add accidental complexity
- `telescope` — 3 extra endpoints for `telescope_configuration` child table + `telescope_connector` junction; structure is unique enough that forcing it into the factory is a net loss
- `filter` — 6 extra endpoints (3 for passbands + 3 for size options); same rationale
- Extracting `_build_X_response` functions into a generic helper — nested joins differ enough per type that a generic is worse than explicit code
- `INSERT ... RETURNING *` to eliminate the post-write re-read (SQLite 3.35+ supports it). Flagged by the efficiency review as the single biggest remaining perf win; deferred to a follow-up because the behavior change warrants its own PR
- Any change to API URL shape, field names, response payloads, status codes, or error semantics
- Any change to the SQL schema or migrations

### v0.12.2 Completion Criteria

- [x] All backend tests pass (1,345 passed, 3 skipped) — same count as baseline
- [x] Coverage on `api/equipment.py` at 98% (up from 96% baseline); `equipment_factory.py` at 99%
- [x] Ruff / format / bandit clean (0 Low / 0 Medium / 0 High)
- [x] No change to `/api/equipment/*` request/response shapes — verified by the existing 199-test `test_equipment_api.py` suite passing unchanged
- [x] Line count reduction recorded: `equipment.py` 2,749 → 1,416 (−1,333 lines, −48%); total equipment code 2,749 → ~1,720 (−37%)

---

## v0.13.0 — Custom Horizons

**Status:** Done
**Branch:** `v0.13.0/custom-horizons`

Per-location custom horizon profile — the measured obstruction pattern
(trees, hills, buildings) visible from an observing site. Import from
N.I.N.A. `.hrz` / Telescopius / APCC / Theodolite iPhone CSV / generic
two-column text; draw, drag, add, delete, reduce, and trace over points
in a dedicated editor; export to N.I.N.A. `.hrz` (also works in APCC
and Telescopius), Stellarium polygonal landscape zip, and CSV. Per
v0.13.0 scope the horizon is stored and rendered but not yet consumed
by target planning, altitude overlays, or session scoring — those
come later.

### Schema

- [x] Migration 0014 — `location_horizon` (1:1 with location, `UNIQUE(location_id)`, CHECK on `source ∈ {'imported', 'drawn'}`) + `location_horizon_point` (composite PK on `horizon_id, azimuth_deg`, CHECK on `azimuth_deg ∈ [0, 360)` and `altitude_deg ∈ [-5, 90]`). `ON DELETE CASCADE` from location through horizon to points
- [x] Soft-deleting a location leaves the horizon rows intact (location is already soft-delete via `active = 0`); a hard delete cascades normally

### Backend

- [x] `services/horizon.py` — forgiving parser with sniff step: detects Theodolite CSV by header row (`HDG_DEG` / `VERT` columns); else falls through to generic 2-column `az alt` text with `#`/`;` comments. Normalizes azimuth to `[0, 360)`, validates altitude `[-5, 90]`, sorts, offsets exact duplicates by +0.01°, rejects files with <2 points. Three exporters — N.I.N.A. `.hrz`, Stellarium polygonal-landscape zip, CSV. Filename sanitizer for download dispositions
- [x] `api/horizons.py` — 7 endpoints under `/api/locations/{id}/horizon`: GET, PUT (drawn, ≥2 points via Pydantic validator), DELETE, POST /import, GET /export/nina.hrz, /export/stellarium.zip, /export/csv. Import persists; export allows soft-deleted locations for recovery. INSERT wrapped in `integrity_guard` for concurrent-save safety. Also exposes a sibling `parse_router` with stateless `POST /api/horizons/parse` (no DB write) supporting the frontend's staged-save flow; both endpoints share the `_parse_upload_file` helper
- [x] `api/horizon_models.py` — `HorizonPut`, `HorizonResponse`, `HorizonImportResponse`, `HorizonParseResponse` Pydantic models

### Frontend

- [x] `api/horizons.ts` — typed fetch clients plus `parseHorizonFile` (stateless) and `downloadHorizonExport` (browser anchor click, no frontend buffering)
- [x] `components/locations/HorizonChart.tsx` — SVG + D3 panorama. N-centered x-axis, auto-fit y, three stacked layers: solid-orange editable line + teal fill, dashed-orange trace-reference, dotted-blue original-comparison. Editable mode: double-click to add, drag to move, right-click for precision popover. Smooth mode: readonly centripetal Catmull-Rom; editing disabled. Raw-points toggle for measurement dots. Implicit 0° dashed baseline when <2 points
- [x] `components/locations/HorizonEditor.tsx` — modal dialog editor with toolbar (import, export dropdown, reduce, clear, undo/redo, altitude-range toggle, trace/reference chip, compare toggle, smooth toggle, point counter) + point-edit popover + reduce preview dialog + clear-trace confirm + too-few-points guard + unsaved-changes discard guard + keyboard shortcuts (⌘Z/⌘⇧Z)
- [x] `lib/horizonReduce.ts` — Douglas-Peucker simplification using vertical altitude distance as the error metric. Iterative (stack-based, safe on long point lists)
- [x] LocationsPage integration — compact readonly `LocationHorizonReadonly` card with Raw/Smoothed switch in the detail panel + full `LocationHorizonEditSection` inside the Location editor dialog (small preview chart + summary + Edit/Delete buttons + staged-delete Undo link)

### Staged-save flow

- [x] Horizon editor buttons renamed **Keep changes** (stages in parent) and **Discard changes** (dirty-checked). `onSave` no longer writes to the server; the outer Location editor's Save is the single persistence action
- [x] `LocationsPage` owns `stagedHorizon: {kind: "none" | "set" | "delete"}`. Horizon editor → parent flows points; parent persists on Location Save via `saveHorizon` / `deleteHorizon`. Dirty guard on Location editor Cancel/X/Escape now covers location fields AND staged horizon changes
- [x] Import flow routes through the stateless `/api/horizons/parse` endpoint — no DB write until outer Save
- [x] Export menu greys out when staged changes exist (stale data avoidance)

### UX polish

- [x] Reduce dialog — slider + live point-count + **before/after preview chart** (reduced solid, original dashed) + legend. Dialog widened to `maxWidth="md"`. Original line snapshots at dialog-open (not live `points`) so slider drag doesn't churn
- [x] Compare toggle — overlays the horizon as it was when the editor opened (dotted blue, linear not smoothed). On by default when there's an existing horizon
- [x] Trace-from-current — single toolbar button / chip with × toggle. Committed to history so Undo reverses the trace atomically; clear-with-edits prompts Discard / Keep / Cancel
- [x] Horizon section moved above Notes in the Location editor (Notes stays last)
- [x] SQM ↔ Bortle arrow button between the two fields — explicit recalc of Bortle from SQM even when Bortle already has a value (tooltip "Calculate approximate Bortle from this SQM value")
- [x] OsmMap wrapper — click-to-interact (iframe doesn't capture scroll by default), bottom-right reset button that remounts the iframe to restore initial bbox. Applied to both the editor map preview and the detail-panel map
- [x] Display Timezone field gained a helper text `"Used for showing times in the UI (weather, forecasts, clocks)."` matching the existing Location Timezone helper
- [x] Editor is a normal modal (not fullScreen) with `maxWidth="lg"` to match other editor dialogs

### Explicit non-goals for v0.13.0

- Horizon is **not** consumed by any downstream feature yet (planner, altitude overlay, session scoring) — those land when their features are built
- No frontend component tests — deferred for the broader frontend test suite effort
- No persistence of the smoothed/derived horizon — decided against (`woolly-snacking-eclipse` plan). Smoothing is deterministic from raw points; rendering re-computes

### v0.13.0 Completion Criteria

- [x] Backend tests: 1,408 passed, 3 skipped (baseline 1,405 + 63 new tests: parser 22, exporter 17, API 24)
- [x] Ruff lint / format / bandit — 0 Low / 0 Medium / 0 High
- [x] Frontend build — clean
- [x] Migration 0014 applied; existing databases get the two new tables on startup
- [x] Theodolite sample fixture committed at `backend/tests/fixtures/horizons/theodolite_sample.csv`
- [x] No new frontend or backend dependencies required (all new work uses existing D3, MUI, FastAPI, aiosqlite, astropy)

---

## v0.14.0 — DSO Catalog MVP (OpenNGC)

**Status:** Done
**Branch:** `v0.14.0/dso-catalog`

First-pass deep-sky object catalog. Data is NOT shipped in the repo —
on first run tables are empty and the DSO page shows a CTA pointing to
Admin → Catalogs, which fetches the latest OpenNGC release directly
from GitHub (`api.github.com/repos/mattiaverga/OpenNGC/releases/latest`
→ `raw.githubusercontent.com/.../database_files/*.csv`) into
`APP_DIR/catalogs/openngc/`. The existing loader then parses into `dso`
+ `dso_designation` + `dso_catalog_source` tables. Subsequent launches
load from the user dir silently with hash-based skip. Admin has an
"Update from GitHub" button for refreshes.

Surfaces as a flat list page under `/catalog/dso` with type-chip
filters, constellation dropdown (full names), free-text
designation/name search, and a slide-up detail panel. REST API under
`/api/dso/` for list, detail, `lookup` (exact designation → DSO),
`facets` (distinct types/constellations with counts), and
`catalog-sources` (attribution).

**Explicitly deferred:** VizieR-sourced catalogs (Sharpless, Barnard),
NightCrate editorial augmentation (surface brightness, popularity,
recommended filters), plate solving, FITS `OBJECT` header resolver,
DSS2 thumbnails, outlines, smart target planner, in-app catalog
updater, and the shared-filesystem catalog-bundling architecture.
Editorial columns (`popularity_rank`, `difficulty`,
`recommended_filter_id`) exist on `dso` as nullable placeholders for
the augmentation CSV that arrives in v0.15+.

### Schema

- [x] Migration 0015 — `dso_catalog_source` (loader registry + file hash), `dso` (canonical object + denormalized `primary_designation` + `source_row_hash`), `dso_designation` (many-per-dso with closed CHECK vocabulary of 29 catalog prefixes, `UNIQUE(catalog, identifier)`, partial unique index enforcing one primary per dso, `ON DELETE CASCADE` from dso)
- [x] Closed CHECK vocabulary on `dso.obj_type` covers the OpenNGC clean-set (minus `Dup`/`NonEx` which are handled pre-persistence) plus an `'Other'` escape hatch that preserves the upstream value in `raw_obj_type`

### Loader + remote fetcher

- [x] `catalog_loader/` sibling module to `seed_loader/` — `hash.py` (file-sha256 + normalized row-sha256), `registry.py` (`user_catalogs_root()` → `APP_DIR/catalogs`; hard-coded source metadata so missing `version.json` is fine; `read_installed_version()` for Admin display), `openngc_parser.py` (semicolon-delimited CSV, BOM tolerance, sexagesimal → degrees, leading-zero stripping, `Dup`/`NonEx` routing), `crossref_parser.py` (`Identifiers` column token-to-catalog dispatch with single-letter disambiguation, leading-zero normalization), `loader.py` (per-source transaction, file-hash idempotency check, `status="missing"` when files are absent, two-pass canonical-then-duplicate merge, `UNIQUE` collision drops with DEBUG log).
- [x] `catalog_loader/remote.py` — `fetch_latest_release()` hits GitHub releases API; `download_openngc(release, root)` downloads both CSVs to a `.download/` temp dir, computes sha256, atomically renames into place, writes `version.json`. 3-attempt outer retry on top of `http_client`'s 1 retry.
- [x] Dup-row resolution priority: NGC cross-ref → IC cross-ref → Messier cross-ref (the last handles the M102 → M101 historical-duplicate case in the addendum)
- [x] `search_key` built from display form (`m42`, `ngc1976`, `sh2281`) so user-typed short forms hit; the API also rewrites long-form prefixes (`messier42` → `m42`) at query time
- [x] Lifespan wiring — loader runs after migrations + equipment seed loader with a sync sqlite3 connection; if every source is `missing`, a single INFO line tells the user to fetch via Admin
- [x] `_initialize_database` helper in `api/admin.py` does NOT call the catalog loader (DBs start with empty DSO tables by design — user fetches from GitHub on first DSO page visit)

### Backend API

- [x] `/api/dso` — list with `q` (designation or common-name), `type` (CSV), `constellation`, `limit`/`offset`, `sort` (whitelist) / `sort_dir`. Shortlists each item's designations to primary + messier + caldwell for payload compactness; detail returns the full list. `sort=size` orders by major-axis; `NULLS LAST` so rows with missing values sink.
- [x] `/api/dso/{id}` — full detail + all designations + originating `CatalogSource` metadata; 404 on unknown id
- [x] `/api/dso/lookup?q=…` — exact search_key match, returns `null` on miss
- [x] `/api/dso/facets` — distinct obj_type + constellation values with counts, powers the chip filter bar
- [x] `/api/dso/catalog-sources` — list of loaded sources with license + attribution
- [x] `POST /api/admin/catalogs/reload?force=true` — re-parse the local cache (no GitHub call); returns the per-source load summary
- [x] `GET /api/admin/catalogs/remote-version` — hits GitHub releases API, compares against local `version.json`. 502 on network failure.
- [x] `POST /api/admin/catalogs/fetch-from-github` — downloads the latest release atomically into `APP_DIR/catalogs/openngc/` and then runs the loader. 502 on network failure; load summary + fetched tag on success.

### Frontend

- [x] `/catalog/dso` — single-column page: header (title + row count + attribution info icon), filter bar (debounced search 300ms, constellation dropdown showing full names sorted alphabetically with counts, colorblind-safe type-chip multi-select with counts, clear-filters button), server-side paginated/sorted MUI X DataGrid (Community tier, 9 columns including sexagesimal RA/Dec, size, magnitudes, ellipsized common name, truncated alt-designations list). Custom pagination actions with first/last buttons and a fit-to-digits go-to-page dropdown. Empty-state CTA when total=0 and no filters active — links to `/admin`.
- [x] `DsoDetailPanel` — slide-up drawer (65vh) with coordinates (sexagesimal + decimal), size/photometry, all designations as MUI chips (primary filled, others outlined), optional morphology/kinematics + central-star sections, source attribution footer with upstream link. Shows full constellation name (e.g., Orion not Ori).
- [x] `DsoAttributionPanel` — modal listing loaded catalog sources with version, row count, license, upstream URL, and citation
- [x] `lib/dsoTypeNames.ts` — display label map + 4-bucket categorical color map (galaxy/blue, nebula/orange, cluster/teal, other/gray) — no red/green anywhere
- [x] `lib/dsoFormatters.ts` — RA (`HHh MMm SS.Ss`), Dec (`±DD° MM' SS"`), size (arcmin/arcdeg auto), magnitude
- [x] `lib/constellations.ts` — IAU 3-letter → full-name map for all 88 modern constellations
- [x] `api/dsos.ts` — typed fetch wrappers for every endpoint + `reloadCatalogs` (force local re-parse) + `fetchRemoteVersion` (GitHub check) + `fetchCatalogsFromGitHub` (download + load)
- [x] Admin → Catalogs section — shows installed vs. latest remote version, Load / Update / Re-download primary button that calls the fetch endpoint, plus a "Reload local cache" secondary for the force-reload path. Inline error Alert on network failures with retry hint.
- [x] New nav entry "DSO Catalog" in `AppShell` between Calculators and Settings

### Tests

- [x] 39 catalog_loader tests (parser 11 · crossref 10 · loader 14 · registry 4) plus 8 remote-fetcher tests (happy path, retry, 4xx, empty body, atomic rename, prior-install safety)
- [x] 18 DSO API tests (list pagination/filter/search/sort, detail 404, lookup normalization across 4 input forms, facets, catalog-sources) plus 5 new admin-endpoint tests (remote-version happy/no-install/502, fetch-from-github happy/no-db/502)
- [x] Mini CSV fixtures for parser/loader tests — 11-row `mini_NGC.csv` covering HII/G/PN/OCl/Dup/NonEx/'Other'-fallback; 3-row `mini_addendum.csv` covering Barnard/Messier/Dup-via-Messier

### Data

- [x] No vendored catalog data. Repo ships only the schema + loader + fetch plumbing.
- [x] First fetch downloads the current tagged release from GitHub (e.g., v20260307) into `APP_DIR/catalogs/openngc/`. Typical install: 13,308 canonical DSOs from NGC.csv + 63 from the addendum. All 110 Messier and 109 Caldwell designations present.
- [x] `version.json` written on fetch records the tag, `fetched_at`, upstream URLs, license, sha256 per file. The registry reads the `version` field for display; the loader reads the raw CSVs.

### v0.14.0 Completion Criteria

- [x] Full backend suite green with 57 new tests (1,445+ passed)
- [x] Frontend build clean
- [x] Smoke test: `/api/health` + `/api/dso?q=M42` + `/api/dso/lookup?q=NGC1976` + `/api/dso/facets` + `/api/dso/catalog-sources` all return expected shapes on a real DB
- [x] Re-running the app with unchanged catalog files triggers zero reload work (file hash match)
- [x] Force reload via `/api/admin/catalogs/reload` returns a non-zero per-source load summary

---

## v0.15.0 — DSO Augmentation & VizieR Integration

**Status:** Done
**Branch:** `v0.15.0/dso-augmentation`

Extends the v0.14.0 DSO catalog with two VizieR-sourced catalogs
(Sharpless 2, Barnard), the **50 Mpc Galaxy Catalog** (Ohlson+ 2024,
fetched from a GitHub mirror because the CDS endpoint was intermittently
flaky), a NightCrate editorial augmentation layer (common names,
non-galaxy surface brightness, curated distances), and a post-load
Hubble-law redshift backfill for galaxies with no measured distance.
Adds Telescopius-style user-facing type groups, distance display with
pc/ly dual units, a B-Mag tooltip clarifying the Johnson-B ↔
photographic-magnitude approximation, and a distance help dialog with
KaTeX-rendered math. See `docs/dso-catalog-architecture.md` for the
precedence rules between sources.

### Schema

- [x] Migration 0016 adds four columns on `dso`: `distance_pc` (parsecs), `distance_method` (CHECK ∈ `{50mgc, curated, redshift}`, nullable), `common_name_augmented` / `surface_brightness_augmented` `{0,1}` provenance flags. Partial index on `distance_method WHERE NOT NULL`.

### Loader additions

- [x] `catalog_loader/vizier.py` + `vizier_tsv.py` — CDS VizieR TSV fetcher parallel to the v0.14.0 GitHub fetcher. Atomic `.download/` → rename, sha256, per-source entry in `vizier/version.json` as the commit marker. Raw HTTP via `services/http_client.get` — no astroquery dependency. Rotates through three CDS mirrors (Strasbourg → India → South Africa) on retry exhaustion.
- [x] `catalog_loader/sharpless_loader.py` — HII-region loader with crossref-aware creation (two-pass: merge-if-crossref, else standalone DSO with Sh2 primary designation). Crossref side-input hash is folded into the source's effective hash so a crossref edit alone invalidates the cache.
- [x] `catalog_loader/barnard_loader.py` — dark-nebula loader. No crossref merging — dark nebulae and emission regions at the same line of sight are physically distinct.
- [x] `catalog_loader/mgc50_fetch.py` + `mgc50_parser.py` + `mgc50_augmenter.py` — 50 Mpc Galaxy Catalog (Ohlson+ 2024, J/AJ/167/31). Fetched from the author's GitHub mirror (`github.com/davidohlson/50MGC`, default branch `master`) rather than VizieR because CDS has been flaky. The GitHub mirror distributes the catalog as a FITS binary table at `data/catalog.fits`; parsed via astropy, using the lowercase column names `pgc`, `bestdist`, `bestdist_error`, `bestdist_method`. Galaxy distance augmenter writes `distance_pc` with `distance_method='50mgc'` where NULL. About 83% of 50 MGC values are themselves flow-corrected redshift distances, but they remain preferred over NightCrate's naive Hubble-law fallback because the authors apply flow correction.
- [x] `catalog_loader/redshift_distance.py` — post-load Hubble-law backfill. Runs after every fetched source has loaded; fills `distance_pc` on galaxy DSOs with a positive `redshift` but no prior distance. Formula `d = z·c/H₀` with H₀ = 70 km/s/Mpc, non-relativistic. Method tag `'redshift'`. Skips z ≤ 0 (blueshift / measurement noise) and non-galaxy types. Not a fetched source — no `dso_catalog_source` row.
- [x] `catalog_loader/augment_loader.py` — NightCrate editorial CSV loader. Overrides common_name, fills non-galaxy surface_brightness (galaxy values ignored with DEBUG log — OpenNGC is authoritative), sets curated distances. Unresolved designations log WARNING and are skipped.
- [x] Load order updated in `loader.py:load_catalogs`: openngc → openngc_addendum → vizier_sharpless → vizier_barnard → nightcrate_* stubs → nightcrate_augment → github_50mgc → (post-load) `apply_redshift_distances`. Precedence is `curated > 50 MGC > redshift`, enforced structurally via the `WHERE distance_pc IS NULL` guard in each augmenter.
- [x] Shared loader primitives extracted into `catalog_loader/_common.py` (`maybe_float`, `maybe_str`, `normalize_designation`, `upsert_catalog_source`, `insert_dso`, `insert_designation`, `check_source_state`, generic `retry_with_backoff`). Replaces duplication that built up across the five per-source loaders.
- [x] Constellation codes for Sharpless/Barnard derived from RA/Dec via cached `astropy.SkyCoord.get_constellation()` in `services/astronomy.py`. Added `distance_modulus_to_parsecs`, `redshift_to_parsecs`, and the `SPEED_OF_LIGHT_KM_S` / `HUBBLE_CONSTANT_KM_S_MPC` constants alongside.

### Type grouping

- [x] `services/dso_type_groups.py` dispatch table maps OpenNGC's 19 `obj_type` codes to 13 user-facing groups (Galaxy / Emission Nebula / Open Cluster / Globular Cluster / Planetary Nebula / Reflection Nebula / Dark Nebula / Supernova Remnant / Other Nebula / Stellar Association / Star / Multiple / Galaxy Group / Other). `Cl+N` rolls up under Emission Nebula — amateurs imaging NGC 2264/7023 target the nebulosity.

### Seed data

- [x] `data/catalogs/nightcrate/dso_augment.csv` — ~65 curated rows covering iconic emission nebulae (Orion 412 pc, Lagoon 1.25 kpc, …), planetary nebulae (Ring 0.8 kpc with SB, Helix 200 pc, …), the Crab SNR, reflection nebulae, bright clusters (M44, Double Cluster, M13, M15, Omega Cen), Sharpless-only targets (Cave, Barnard's Loop, Tulip, …), and key Barnard dark nebulae (Horsehead, Snake, E-nebula).
- [x] `data/catalogs/nightcrate/sharpless_crossref.csv` — 25 Sh2 ↔ NGC/IC mappings.
- [x] `data/catalogs/nightcrate/barnard_crossref.csv` — intentionally empty (header only).
- [x] `data/catalogs/nightcrate/LICENSE-MIT.txt` + `version.json`.

### Backend API

- [x] `/api/dso` — new query params: `type_group` (comma-separated group names → union of raw types), `has_distance`. New sortable field: `distance_pc`.
- [x] `/api/dso/{id}` — response now includes `distance_pc`, `distance_method`, `common_name_augmented`, `surface_brightness_augmented`.
- [x] `/api/dso/facets` — response reshape. Returns `type_groups[]` (with counts + raw_types), `raw_types[]` (for Advanced filters), `constellations[]`.
- [x] Admin endpoints: `GET /api/admin/catalogs/vizier/{source_id}/remote-version`, `POST /api/admin/catalogs/vizier/{source_id}/fetch` for each of `sharpless|barnard`, `GET /api/admin/catalogs/50mgc/remote-version`, `POST /api/admin/catalogs/50mgc/fetch` (dedicated GitHub path — 50 MGC moved off VizieR), plus `POST /api/admin/catalogs/nightcrate/reload`.

### Frontend

- [x] `lib/distanceFormat.ts` — auto-scaling pc/kpc/Mpc + ly/kly/Mly formatter, 3 sig figs.
- [x] `lib/dsoTypeGroups.ts` — display-only style map referencing `rigColors`.
- [x] `pages/DsoCatalogPage.tsx` — type-group chips as primary filter, raw-type chips in an Advanced expander, Distance column in the grid.
- [x] `components/dso/DsoDetailPanel.tsx` — distance row with method chip, "~" prefix on redshift-derived values, help-icon button next to the Distance label that opens `DsoDistanceHelpDialog`, B-Mag tooltip, `AugmentedBadge` (star icon) next to augmented common_name / surface_brightness values.
- [x] `components/dso/DsoDistanceHelpDialog.tsx` — modal explaining the three distance methods with KaTeX-rendered formulas (`d = c·z/H₀`, distance modulus) and caveats on peculiar velocities, H₀ uncertainty, non-relativistic approximation, and the 50 MGC flow-correction note.
- [x] `components/dso/DsoAttributionPanel.tsx` — CDS VizieR acknowledgment block plus a "Redshift-derived distances" section.
- [x] `components/dso/CatalogsAdminSection.tsx` — new per-source table in Admin → Catalogs with individual fetch/reload buttons. OpenNGC + 2 VizieR (Sharpless, Barnard) + 50 MGC (GitHub fetch) + NightCrate bundled.

### Tests

- [x] 55+ new backend tests across VizieR TSV parser, 50 MGC FITS parser (happy path, PGC ≤ 0 sentinel, NaN / non-positive bestdist, optional error + method columns, column-missing hard error), VizieR + GitHub fetchers (mirror fallback, retry exhaustion, atomic rename, short-body rejection), Sharpless / Barnard loaders, augment loader, 50 MGC augmenter (precedence against curated), post-load redshift backfill (pinned cases incl. formula regression at z=0.02), type-group dispatch, and API extensions. Mini fixtures at `backend/tests/fixtures/catalogs/{openngc,vizier}/`; the 50 MGC FITS fixture is composed at test-time via astropy's `BinTableHDU.from_columns`.

### Docs

- [x] New `docs/dso-catalog-architecture.md` — ~1-page primer on source precedence, atomicity, galaxy-vs-non-galaxy surface brightness, type grouping, and how to add a new catalog source.
- [x] `DB_SCHEMA.md`, `DB_SCHEMA_DDL.sql`, `LLM_DB_SPECS.md`, `nightcrate-current-state.md`, `CLAUDE.md`, `PLAN.md` updated for v0.15.0.

### v0.15.0 Completion Criteria

- [x] Migration 0016 applies cleanly
- [x] Full backend suite green (new tests included)
- [x] Frontend build clean
- [x] ruff / format / bandit clean (0 / 0 / 0)

---

## v0.16.0 — Target Planner (Pass A)

**Status:** Done
**Branch:** `v0.16.0/target-planner`

First-pass "what's up tonight" planner: `/planner` shows a location-
driven list of DSOs geometrically visible during astro-dark, with
standard-framed DSS2 Color thumbnails, filterable by type group,
visibility hours, magnitude, and angular size. Selecting a rig adds a
FOV coverage column and the "frames well" filter. Detail panel has the
larger thumbnail + a D3 sky-position graph styled after the weather
hourly timeline. See `docs/target-planner.md` for architecture.

### Schema

- [x] Migration 0017 adds `thumbnail_cache` (metadata + LRU index). Thumbnail files live on disk under `APP_DIR/thumbnails/`.

### Settings additions (5)

- [x] `planner_min_altitude_deg` (30), `planner_min_visibility_hours` (2.0), `planner_max_magnitude` (12.0), `planner_min_size_arcmin` (5.0), `thumbnail_cache_max_mb` (20). All surface in the Settings page under a new **Target Planner** card with inline editors + cache-size readout + clear-cache button.

### Backend services

- [x] `services/planner_visibility.py` — vectorized astropy alt/az over the astro-dark window with 5-minute sampling. `PlannerLocation` / `DsoCoord` / `DsoVisibility` / `VisibilitySnapshot` value objects; in-process `VisibilityCache` keyed on `(location_id, date, updated_at, horizon_updated_at)` with a 4-entry LRU / 15-minute TTL.
- [x] `services/planner_sky_track.py` — per-DSO high-res track for the detail-panel graph (civil dusk − 30 min → civil dawn + 30 min, 5-minute spacing, moon altitude + per-azimuth horizon line).
- [x] `services/thumbnails.py` + `services/hips_client.py` — CDS Aladin hips2fits fetch (color → red fallback), atomic write, LRU eviction on successful fetch, 1-hour error backoff, in-flight-dedupe via `asyncio.create_task` + module-level map, concurrent-fetch cap of 4 via semaphore.
- [x] `services/rig_calculators.py` — added `compute_coverage_pct` (max of major/minor fill %) + `frames_well` (15–90%).
- [x] `services/horizon.py` — added `interpolate_horizon_altitude` (wrap-safe linear interpolation for numpy azimuth arrays).

### Backend API (`/api/planner`)

- [x] `GET /api/planner/targets` — list with type_group / min_hours / max_magnitude / min_size / frames_well filters; sortable by hours_visible / max_altitude / coverage_pct / mag_v / primary_designation. Response includes location summary, rig summary (if selected), dark_window, moon_phase, paginated items.
- [x] `GET /api/planner/targets/{dso_id}/sky-track` — per-DSO altitude / azimuth / moon altitude / horizon reference arrays + twilight band boundaries.
- [x] `GET /api/planner/thumbnails/{dso_id}?variant=list|detail` — 200 JPEG on hit, 202 placeholder PNG + background fetch on miss, 204 on error-backoff.
- [x] `POST /api/planner/thumbnails/cache/clear` + `GET /api/planner/thumbnails/cache/stats` for Settings.

### Frontend

- [x] `/planner` route + "Planner" nav entry (StarsIcon) wired between Calculators and DSO Catalog.
- [x] `pages/PlannerPage.tsx` — location + rig selectors, type-group chips, three sliders, frames-well toggle, DataGrid with thumbnail cell + 11 columns (10 + conditional FOV coverage), detail-panel dialog.
- [x] `components/planner/ThumbnailCell.tsx` — placeholder-detection via `naturalWidth`, 2-second retry with cache-buster, neutral-icon fallback on permanent failure.
- [x] `components/planner/SkyPositionGraph.tsx` — D3 SVG with twilight bands, object + moon + horizon lines, visible-area shading, hover tooltip.
- [x] `components/planner/PlannerDetailPanel.tsx` — MUI Dialog with detail thumbnail + metadata chips + sky graph + coverage narrative ("fills the frame nicely at 45%", "covers 173% — will be cropped").
- [x] `api/planner.ts` — typed fetchers + `thumbnailUrl()` composer. `thumbnailUrl` includes the `/api` prefix since `<img src>` bypasses the apiFetch wrapper.
- [x] Settings page — new **Target Planner** card with per-field inputs + cache-size readout + Clear All button.

### Spec deviations

- **Moon separation**: spec called for "at peak altitude"; implemented as **closest approach during visibility window** instead. At-peak can be wildly misleading when the moon is below the horizon at the object's transit but rises later during the visible window. Documented in the visibility-engine module docstring.

### Tests

- [x] `tests/services/test_planner_visibility.py` — 16 tests incl. Phoenix 2026-04-19 regression, southern target never rising, polar-summer empty-snapshot, custom-horizon-vs-flat comparison, cache reuse + invalidation on `updated_at` change, azimuth-interpolation bracketed by degree markers.
- [x] `tests/services/test_planner_sky_track.py` — sample count, array lengths, horizon flat-vs-custom, twilight boundaries, moon phase.
- [x] `tests/services/test_planner_coverage.py` — FOV coverage including null-axis fallback, clipped-on-minor, zero-FOV rejection, frames_well band.
- [x] `tests/services/test_planner_thumbnails.py` — 9 tests across cache hit/miss, color→red fallback, double-failure recording, error-backoff short-circuit, LRU eviction, clear-cache, FOV sizing.
- [x] `tests/test_planner_api.py` — integration coverage for all 5 routes.

### v0.16.0 Completion Criteria

- [x] Migration 0017 applies cleanly
- [x] Full backend suite green (1594 passed, 3 skipped — +45 new)
- [x] Frontend build clean
- [x] ruff / format / bandit clean (0 / 0 / 0)

---

## v0.17.0 — Target Planner Pass B (FOV Simulator + Rig-Framed Thumbnails)

**Status:** Done
**Branch:** `v0.17.0/target-planner-pass-b`

Extends v0.16.0's planner with two user-facing pieces: a second
thumbnail column showing each object framed in the selected rig's
sensor, and an interactive FOV simulator in the detail panel with a
drag-to-rotate overlay rectangle. See `docs/target-planner.md` for
architecture.

### Schema

- [x] Migration 0018 rebuilds `thumbnail_cache` to widen the `variant`
      CHECK (adds `rig_framed`, `fov_simulator`) and add nullable
      `fov_major_deg_x1000` / `fov_minor_deg_x1000` descriptor columns.
      Unique index wraps the FOV columns in `COALESCE(..,-1)` so
      rig-dependent and rig-independent entries share a namespace.
      Pass A rows are wiped on re-apply; files on disk are swept by the
      app-startup orphan helper.

### Backend services

- [x] `services/thumbnails.py` reworked end-to-end: `ThumbnailKey` value
      object + `make_key()` factory; `compute_angular_extent_deg()` unified
      across the four variants; rig-dependent variants raise `ValueError`
      on missing FOV; `sync_orphan_files()` added for the startup sweep
      + wired into `main.py` lifespan.
- [x] Pass A detail variant widened from 600×600 / 2.5× / 0.5° to
      800×800 / 3.5× / 1.0° so the FOV simulator has room for the
      rectangle at any rotation.

### Backend API

- [x] `GET /api/planner/thumbnails/{dso_id}` extended with
      `fov_major_deg` + `fov_minor_deg` query params. Validates that
      rig-dependent variants supply both (400 otherwise; 400 on
      non-positive values).

### Frontend

- [x] `components/planner/FovSimulator.tsx` — wide-view DSS2 background
      with a CSS-rotated orange sensor rectangle sized to the rig's
      angular FOV scaled against the image's pixel extent. Drag,
      numeric input, arrow keys (±5° / ±1° with Shift), R resets.
      North-up east-left convention; "what does this mean?" tooltip
      distinguishes sky rotation from real-capture rotation.
- [x] `components/planner/ThumbnailCell.tsx` learns the new variants
      + an `aspectRatio` prop that lets the "In my rig" column render
      a sensor-shaped bounding box that crops the square source via
      `object-fit: cover`.
- [x] `pages/PlannerPage.tsx` adds the "In my rig" column immediately
      after the Pass A thumbnail column when a rig is selected.
- [x] `components/planner/PlannerDetailPanel.tsx` swaps the hero image
      for the FOV simulator when a rig is selected; falls back to the
      Pass A `detail` variant when no rig is active.
- [x] `api/planner.ts:thumbnailUrl()` accepts an `opts` object with
      `fovMajorDeg` / `fovMinorDeg`; `ThumbnailVariant` type exported.

### Tests

- [x] ~17 new backend tests in `test_planner_thumbnails.py` +
      `test_planner_api.py`: angular extent (rig_framed + fov_simulator
      incl. small/large object crossover), FOV rounding, cache key
      separation at 0.01° vs sharing at 0.001°, orphan sweep, 400s
      for missing / non-positive FOV params, rig-framed cache miss
      enqueues a fetch. Full suite: 1611 passed / 3 skipped.

### Docs

- [x] `docs/target-planner.md` Pass B section (thumbnail variants,
      cache key, orphan sweep, FOV simulator).
- [x] `CLAUDE.md`, `DB_SCHEMA.md`, `DB_SCHEMA_DDL.sql`, `LLM_DB_SPECS.md`,
      `nightcrate-current-state.md` all updated for v0.17.0.

### Post-Pass-B refinements

- [x] Planner detail panel: transit altitude now uses astropy's
      apparent frame (fixes ≈0.02° J2000→apparent drift that made
      max-altitude disagree with altitude-at-transit by 1° on
      precession-drifted targets). Removed
      `transit_during_astro_dark` — transit is sidereal geometry,
      unrelated to astro-dark.
- [x] Sky-position graph: magnetic snap-to-meridian on hover (cursor
      locks to meridian line within 6 CSS px; tooltip annotates).
- [x] FOV simulator — annotation alignment overhaul:
      - `lib/dsoAnnotations.ts::projectRaDecToPixel` now uses gnomonic
        (tangent-plane TAN) projection matching hips2fits instead of
        the flat plate-carrée approximation. Fixes annotation drift
        within the centre tile at high declinations (≈47 px on the
        dec axis for Ursa Major targets).
      - New `projectRaDecToTilePixel` picks the grid tile whose
        tangent is nearest each annotation (four candidates around
        floor/ceil of col/row), then projects onto *that* tile's
        tangent. Annotations now align with the per-tile gnomonic
        image in neighbour tiles, not just the centre.
      - Shared `tileCenterAt` helper: `FovSimulator.computeTiles` and
        the per-tile projection derive tile positions from the same
        function, so their plate-carrée spacing can't drift apart.
- [x] FOV simulator — first-image latency:
      - Backend `get_thumbnail()` gains a `wait_timeout_s` kwarg; the
        `/api/planner/thumbnails/{id}` endpoint exposes it as
        `wait_ms` (capped at 10 s). On a miss the request holds open
        awaiting the background fetch task under `asyncio.shield`
        and returns the real image in the same round trip —
        eliminates the "CDS latency + next-poll cadence" overhead
        pollers pay. Frontend tiles long-poll with `waitMs=4000` on
        the first attempt only; retries send `waitMs=0` so a slow
        CDS can't stack 4 s connection holds.
      - `ThumbnailCell` catches the cached `<img>` race via `imgRef`
        + `useLayoutEffect([src])`: when the browser serves `src`
        synchronously from HTTP cache, `onLoad` can fire before
        React attaches its listener — the effect inspects
        `img.complete` and replays the load path. Fixes stuck
        spinners on revisit.
      - Retry cadence replaced the hardcoded 2 s with a backoff
        schedule (400 / 900 / 1500 / 2500 ms). Warm-backend revisits
        land in <0.5 s.
- [x] FOV simulator — 25-tile stampede fix: `<FovSimulator>` now
      carries a `key={dsoId:fovMajor:fovMinor}` at the call site.
      Without it, switching DSOs re-rendered the same instance with
      the new `dsoId` while `gridN` was still 5 from the prior
      target, so 25 neighbour tiles all fired CDS fetches before the
      reset useEffect could run. Remounting makes `gridN=1`
      synchronous with the prop change; only the centre tile makes
      a network request up front. Removed the now-redundant state-
      reset `useEffect`.
- [x] FOV simulator — faint dashed tile-boundary grid inside the pan
      group (opacity 0.14, stroke + dash counter-scale by zoom).
      Signals the mosaic so per-tile projection seams read as an
      intentional trade-off.
- [x] `.gitignore` broadened from `bug*.png` to `/*.png` to cover
      all ad-hoc testing screenshots at the repo root.

### v0.17.0 Completion Criteria

- [x] Migration 0018 applies cleanly, wipes the Pass A cache
- [x] App-startup orphan sweep runs and clears stale on-disk JPEGs
- [x] Full backend suite green (1630 passed, 3 skipped — +36 new
      across initial Pass B + post-Pass-B refinements)
- [x] Frontend build clean
- [x] ruff / format / bandit clean (0 / 0 / 0)

---

## v0.18.0 — Target Planner Pass C (Sky-Tile Cache + Seamless Stitching)

**Status:** ✅ Complete
**Branch:** `v0.18.0/target-planner-pass-c`

Rearchitects the FOV-simulator tile pipeline from per-DSO TAN fetches
to a DSO-agnostic **HEALPix-regional sky-tile cache** where every cell
in a region shares one tangent plane and therefore tiles pixel-perfectly.
Cells are keyed by `(hips_survey, healpix_nside, healpix_ipix, tier,
cell_i, cell_j)` rather than by DSO id, so neighbouring targets share
cache. The catalog detail preview reuses the same cells with an
auto-tier zoom-to-fit per object. Full design lives in
`/.claude/plans/lovely-hatching-swan.md`.

### Scope summary

Began life as v0.17.1 "minor revision" (layout polish on the DSO
detail panel) but re-scoped to v0.18.0 once the tile-cache rearchitecture
landed in the plan. The layout polish rides along; the headline feature
is the new cell cache.

### Catalog detail-panel polish (already in-branch)

- [x] `DsoDetailPanel` responsive layout (3-tier): 2-column metadata
      + right-hand image on lg+, 1-column metadata + right-hand image
      on md, full-stack with inline image on xs/sm. Image sticky on
      md+, inline on xs/sm.
- [x] "View full image" button overlay on the preview opens a modal
      showing the cached tile at 100% natural aspect
      (`object-fit: contain`). Close via X / backdrop / ESC.
- [x] No-coords fallback: DSOs with null RA/Dec show a "No image
      available — object has no coordinates on record" placeholder
      instead of a broken ThumbnailCell.
- [x] Close-button fix: added `display: flex` + `flexDirection: column`
      to the bottom Drawer's Paper so the body's `flex: 1 + overflowY:
      auto` actually bounds the scroll area, keeping the header + close
      button reachable on long entries.
- [x] New `fit` prop on `ThumbnailCell` — defaults to `"cover"` for
      list/grid use; the full-size preview passes `fit="contain"` so
      future non-square variants letterbox instead of cropping.

### Sky-tile cache architecture

- [x] Added `astropy_healpix` (BSD-3-Clause). `healpy` (GPL-2.0)
      explicitly rejected.
- [x] Migration 0020 creates `sky_tile_cache` table. Keys:
      `(hips_survey, healpix_nside, healpix_ipix, tier,
      cell_size_deg_x100, cell_width_px, cell_height_px, cell_i,
      cell_j)` + unique index. `center_ra_deg_x1000` /
      `center_dec_deg_x1000` columns kept on `thumbnail_cache` for the
      now-retired panned-simulator path (vestigial, still indexed).
- [x] `services/sky_tiles.py` — HEALPix region math (NSIDE=8, 768
      regions), cell-grid math, `cell_wcs_dict()`, `compute_grid_layout`.
- [x] `services/sky_tile_cache.py` — SQL helpers, LRU eviction, orphan
      file sweep (`sync_orphan_files`) on app lifespan startup.
- [x] `hips_client.build_hips2fits_wcs_url(hips, wcs_dict, fmt)`
      alongside the existing `build_hips2fits_url`.
- [x] `GET /api/planner/sky-tile` endpoint with `wait_ms` long-poll
      (mirrors `/thumbnails/{id}`).
- [x] `GET /api/planner/sky-tile-grid` layout endpoint (pure math).
- [x] Three resolution tiers selected by rig major FOV:
      `narrow` (≤1°, 0.5° cells @ 800×800), `med` (1–3°, 2° cells @
      800×800), `wide` (>3°, 8° cells @ 1024×1024).
- [x] CDS fetch semaphore bumped 4 → 8 for faster first-image latency
      on the 5×5 tile mosaic.

### Frontend cell composition

- [x] `api/planner.ts:skyTileUrl(cell, { waitMs, generation })` +
      `fetchSkyTileGrid`.
- [x] `components/planner/SkyTileCell.tsx` — single-cell loader with
      placeholder retry + cached-image `imgRef` safety net.
- [x] `components/planner/SkyTileComposite.tsx` — staged mount
      (centre first, then distance-sorted) so the backend's 8-slot
      semaphore focuses on the target cell first.
- [x] `FovSimulator` rewritten on top of `SkyTileComposite`. TAN-plane
      pixel coords; promotes 1 → 3 → 5 cells wide as the centre
      renders. Scroll-wheel zoom (native listener, not React
      `onWheel` — passive by default). Annotation click priority
      over pan (JSX z-order). Default zoom: rig rect fills 75% of
      viewport. Re-centre button preserves zoom + rotation.
- [x] `dsoAnnotations.ts` — `projectRaDecInRegion` (single region
      tangent). Counter-scale fonts/stroke by 1/zoom so labels stay
      constant CSS size.

### DSO catalog auto-tier preview

- [x] `<SkyPreview>` component replaces the old `ThumbnailCell
      variant="detail"` in `DsoDetailPanel` + the full-size modal.
- [x] `previewSpecForDsoSize(majArcmin)` in
      `lib/skyPreviewExtent.ts` picks tier + extent from the DSO's
      major axis.
- [x] Two-phase mount: centre cell first with a centred
      semi-transparent loading overlay until it paints.

### Planner UX polish (rode along)

- [x] Tonight / Anytime mode toggle promoted to a prominent
      header-level mode selector under the page title. Context-aware
      labels — "Tonight from {location}" / "Browse the full
      catalog".
- [x] Mode-adaptive filter bar: Location selector + Min-hours
      slider + Brighter-than slider + Min-size slider + Frames-well
      checkbox hidden in Anytime mode. Visibility columns (Hours,
      Max altitude, Meridian, Moon) dropped from the grid in
      Anytime.
- [x] Catalog-style filters added to match the DSO Catalog page:
      constellation `<Select>`, "Has distance" checkbox, raw-type
      chips under an "Advanced filters" disclosure, chip counts on
      both type-group and raw-type chips, "Clear filters" button.
- [x] Backend `/api/planner/targets` accepts `type` (comma-separated
      raw codes), `constellation`, `has_distance` to match the DSO
      Catalog API.
- [x] Fixed the Galaxy-Group-vanishes bug: Anytime mode no longer
      silently applies the user's saved imaging defaults
      (`planner_min_size_arcmin`, `planner_max_magnitude`) — a
      missing param in Anytime means "don't filter", not "apply
      5′ / mag 12 quietly".
- [x] Planner search box with DSO-catalog semantics (designation
      prefix + common-name substring).
- [x] Default sort per mode: `hours_visible desc` (Tonight) /
      `primary_designation asc` (Anytime). User-initiated sorts
      persist across mode toggles via `sortIsAutoRef`.
- [x] `noRowsOverlay` with mode-aware empty-state copy; Tonight
      nudges users to relax filters or switch modes.
- [x] Thumbnail cache default bumped 20 MB → 500 MB; slider max
      5 GB.

### Testing

- [x] WCS roundtrip (`test_sky_tiles.py`): pole-adjacent + RA=0
      coords; `world_to_pixel` round-trip within tolerance.
- [x] Cell layout math: grid arithmetic + HEALPix region
      assignment.
- [x] Cache-reuse test: two DSOs 2° apart in the same region share
      cells.
- [x] Orphan file sweep test.
- [x] Planner API regression: `restrict_tonight=false` skips
      visibility, `has_distance` / raw-type / constellation
      filters, Anytime bypasses imaging defaults, Galaxy-Group
      filter returns expected rowcount.

### Legacy cleanup

- [x] `thumbnail_cache` keeps serving `list` / `rig_framed`. The
      `fov_simulator` variant rows were wiped at migration time;
      `sync_orphan_files` sweeps the on-disk JPEGs on startup.
- [x] `FovSimulator` no longer sends `centerRaDeg` / `centerDecDeg`
      — panning is viewport-only under the regional-tangent scheme.
- [x] `center_ra_deg_x1000` / `center_dec_deg_x1000` columns
      retained but unreferenced by the new simulator path.

### v0.18.0 Completion Criteria

- [x] Migration 0020 applies cleanly; sky-tile cache table populated
      on first simulator open
- [x] Full backend suite green (1705 tests, 3 skipped)
- [x] Frontend build clean
- [x] ruff / format / bandit clean (0 / 0 / 0)
- [x] Manual end-to-end sanity across narrow / med / wide rigs +
      high-dec targets

---

## v0.18.1 — Target Planner UX Polish

**Status:** Done
**Branch:** `v0.18.1/planner-polish` (rolled forward into v0.19.0 branch)

Collected UX polish items surfaced during v0.18.0 manual testing.
None are bugs — small additive improvements deferred so v0.18.0 can
ship.

### Planner filter bar

- [ ] **Catalog multi-select filter.** Drop-down (chips-style) to
      filter the Planner results by designation catalog —
      Messier, NGC, IC, Sharpless 2, Barnard, PGC, UGC, Caldwell, etc.
      (the 29-catalog closed vocabulary from `dso_designation.catalog`).
      The DSO Catalog page should grow the same control for parity.
      Multi-select semantics: OR within the filter (a DSO is a match
      if it carries *any* of the selected catalog designations).

- [ ] **Filter-aware type-group chip counts.** Today the type-group
      (and raw-type) chips show full-catalog totals from
      `/api/dso/facets` — meaningful in Anytime but misleading in
      Tonight, where a "Galaxy Group (234)" chip can sit above a
      grid with zero rows because mag / size / visibility filters
      eliminate everything. Either compute filtered counts via a
      new facets-with-filters endpoint, or drop the parenthesised
      count in Tonight mode and only show it in Anytime.

- [ ] **Planner "Clear filters" discoverability.** The button only
      renders when `catalogFiltersActive` is true (at least one of:
      search, constellation, has-distance, type-group chip, raw-type
      chip). A user who just wants to reset their mag/size/min-hours
      sliders won't see it. Decide together with the catalog-filter
      redesign — options include always-rendering the button,
      adding a slider-specific "Reset to defaults" button, or
      rolling all of it under one Clear control.

- [ ] **Revisit type-group vs raw-type chip overlap** (bundle with
      the catalog-filter-redesign discussion below — not a separate
      decision). Main chips show user-facing group names (e.g.
      `Galaxy`) derived via `group_for_raw_type`; the Advanced
      section shows raw OpenNGC codes (e.g. `G` → "Galaxy" via
      `displayDsoType`). The labels collide ("Galaxy" appears in
      both) and should be resolved as part of whatever shape the
      filter controls take post-redesign.

### DSO Catalog

- [ ] **Survey of DSOs with no RA/Dec.** Rather more entries than
      expected have null coordinates. Worth investigating — are
      these canonical DSOs where OpenNGC itself is missing the
      coords, or a parser bug? Either way the DSO Catalog page
      should expose a "Has coordinates" filter and decide whether
      to hide / gray / flag them.

### FOV Simulator

- [ ] **Reconsider arrow-key controls.** Arrow keys currently step
      rotation ±5° / Shift-arrow ±1°. Options: (a) drop keyboard
      rotation entirely and rely on drag-to-rotate + numeric input,
      or (b) add `Ctrl-arrow` for panning the viewport (the obvious
      missing keyboard control, since rotation already has drag +
      numeric input).

- [ ] **Rig-frame-intersection tile load priority.** Currently cells
      render in order of distance-from-view-centre, with the centre
      cell gated behind its own `onReady`. When a rig is selected,
      the priority should instead be "tiles that intersect the rig
      rectangle first, then the rest centre-outward". The rig
      rectangle can span multiple cells at medium/wide tiers; today
      the user watches cells outside the frame light up before ones
      the rig actually covers.

### FOV Simulator background survey

- [x] **DSS2 plate-boundary seams are visible at wide extents.**
      Decision: accept as a known DSS2 data characteristic — same
      effect appears in Aladin / Stellarium. Mosaic stitches
      pixel-perfectly (verified on NGC 7000); the deltas are plate-
      to-plate exposure / development differences, not a NightCrate
      stitching bug. A proper survey picker (Pan-STARRS / DECaLS
      where available, DSS2 fallback) is a feature, not polish —
      deferred to its own future version rather than landing inside
      v0.18.1.

### Cache resilience across database recreation

- [ ] **Thumbnail cache: coordinate-keyed filenames.** v0.18.1
      added a startup rehydration path for ``thumbnail_cache`` that
      re-indexes on-disk JPEGs, but it's limited by the current
      filename format ``{dso_id}_{variant}_{w}x{h}.jpg``. The
      embedded ``dso_id`` isn't stable across fresh catalog loads
      (OpenNGC rows get auto-assigned integers in insertion order,
      and that order isn't guaranteed to match between databases),
      so a user who creates a new DB loses the thumbnails both
      pages rely on — the Planner's list thumbnails, the DSO
      Catalog grid's row thumbnails, and the "In my rig" column —
      even though the JPEGs are still on disk. Fix: encode
      ``(ra_deg_x10000, dec_deg_x10000)`` in the filename instead
      of / alongside ``dso_id``; rehydrate matches files to current
      ``dso`` rows by angular coordinate (≤1 arcsec tolerance).
      Migration note: current thumbnails would be orphaned once on
      rollout; the new format is cross-DB resilient thereafter.
      The sky-tile cache (FOV simulator backgrounds, DSO Catalog
      detail-panel preview) already survives DB recreation because
      its filenames encode HEALPix region identity, no DSO id.

### Admin / Settings restructure

- [ ] **Discuss: move cache management from Settings → Admin.** The
      thumbnail cache + sky-tile cache controls (size budget slider,
      current usage, clear button) currently live on the Settings
      page. Fred's take: these are operational controls, not user
      preferences — Admin feels like the right home, alongside the
      DB-management and catalogs sections. Applies broadly: any
      cache-management UI (aberration cache, weather cache, future
      caches) probably belongs on Admin, not Settings. Settings
      should reduce to pure preferences (theme, planner defaults,
      GPU on/off, worker cores).

### Planner detail panel

- [ ] **Discuss: date selector on the altitude chart.** The
      Sky position graph currently always renders "tonight" —
      there's no way for the user to preview a target's altitude
      curve on, say, next Saturday. The planner's core workflow
      assumes tonight, but the detail panel should let users pick
      any date while leaving the parent grid unchanged. Scope
      question: does the date picker live in the detail panel only
      (matches the existing in-panel location picker's pattern), or
      does it propagate up to the grid (changes the whole planner
      view to that date)? Decide together with the altitude-chart
      Anytime behaviour.

- [ ] **Discuss: altitude chart (SkyPositionGraph) behaviour in
      Anytime mode.** The detail dialog's "Sky position" section
      runs off a location — in Anytime there may be no parent
      location selected. Today the panel's own location dropdown
      defaults to the parent's selection, so Anytime can leave the
      graph in a spinner / empty state. Options to consider:
      (a) hide the Sky position section in Anytime unless the user
      explicitly picks a location in the panel's dropdown;
      (b) keep the section but render a friendly prompt
      ("Pick a location to see this object's sky track") instead of
      the spinner; (c) require a location in the panel dropdown
      unconditionally (auto-pick the default location even in
      Anytime).

### Planner grid

- [x] **Grid shows blank state during first fetch instead of a
      spinner.** Replaced with the custom opaque overlay on the
      Paper wrapper — covers the card list (v0.19.0 replaced the
      DataGrid with cards) during any `isLoading || isFetching`
      state. Bypasses MUI X Community's `loading` prop, which
      rendered a linear-progress bar inside the column-header row
      that peeked through as clipped artifacts.

---

## v0.19.0 — Multi-Horizon + Planner Rewrite

**Status:** Done
**Branch:** `v0.18.1/planner-polish` (kept the v0.18.1 branch name but
the scope outgrew polish — shipped as v0.19.0)

Two large feature rewrites shipped together because they touched
the same data-flow paths:

1. Locations gained a first-class **Horizons** concept — one
   optional custom polyline plus any number of named artificial
   (flat-altitude) horizons per location, with one marked default.
   Every compute path that used to branch on "does the location
   have a horizon?" now takes a `PlannerHorizon` argument and the
   30° fallback setting is gone.

2. The planner page got a **multi-sort drag-drop panel** and its
   DataGrid row layout was replaced with a **card-per-DSO list**.

Along the way: RA/Dec added to each card, now-status bug fixed,
Frames-Well turned into a dual-thumb coverage-range slider with
user-configurable defaults, annual chart default moon separation
made configurable, custom loading overlay replaces MUI's
linear-progress artifact.

### Multi-horizon per location

- [x] **Migration 0021 `location_horizon_multi.sql`** — reshapes
      `location_horizon` 1:1 → 1:N. One optional custom polyline
      plus artificial flat-altitude rows, partial unique index on
      `is_default` (exactly one per location), partial unique
      index `(location_id) WHERE type='custom'` (max one custom),
      CHECK-enforced `type ∈ {'custom', 'artificial'}` vocabulary.
      Reshape pattern recreates `location_horizon_point` too — the
      SQLite `ALTER TABLE RENAME` FK-rewrite trap (original FKs
      follow the rename to the legacy table) made a DROP + recreate
      necessary; `PRAGMA foreign_keys = OFF` + explicit index drop
      handles it atomically.

- [x] **Horizons CRUD API** — `GET/POST/PATCH/DELETE
      /api/locations/{id}/horizons[/{hid}]`. Auto-promote on
      default delete, 422 on last-horizon delete, 422 on demoting
      a default without promoting another, 409 on duplicate name
      or second custom. Artificial-horizon payloads are
      name + altitude only; custom-horizon payloads carry points.

- [x] **Auto-seed default** — `POST /api/locations` creates the
      location and a `0° flat` artificial horizon marked default
      in the same transaction. Migration backfills the same row
      for pre-existing locations that had no horizon.

- [x] **Locations Editor horizon section** — new
      `LocationHorizonsSection` with immediate persistence (no
      staged save); the existing custom-horizon editor dialog
      commits on its "Keep changes" button. Default radio per row,
      Add Artificial dialog, Edit/Delete icons, delete-confirm
      dialog.

- [x] **Planner compute path** — `services/planner_visibility.py`,
      `planner_sky_track.py`, `planner_annual_hours.py`,
      `planner_now_status.py` all take a `PlannerHorizon` argument.
      `services/horizon.py:resolve_horizon_altitude` dispatches
      artificial vs custom so the compute code has no branching
      left. Visibility cache key includes `horizon_id` +
      `horizon.updated_at`.

- [x] **`planner_min_altitude_deg` setting deleted** — altitude
      floor now lives per-horizon on the location.

### Planner multi-sort panel

- [x] **Backend multi-sort** — `GET /api/planner/targets` accepts
      `sort=field:dir,field:dir,...` with stable Timsort per key.
      Nulls and empty/whitespace strings always sort last
      regardless of per-key direction (`_sort_value` coerces blank
      strings to None). 14 sort fields registered in the
      `PLANNER_SORT_FIELDS` catalog with matching definitions in
      `frontend/lib/plannerSortFields.ts`.

- [x] **`PlannerSortPanel`** — collapsible accordion below the
      imaging sliders. "Sort by" area uses a `SortableContext`
      with `useSortable` pills (drag to reorder within). Available
      pills are plain `Chip`s with `onClick={addEntry}` — click
      to add. Removal via X on sort-by pills. Direction toggle
      (↑/↓) on each sort-by pill.

- [x] **Persist `sortBy` in `plannerStore`** — version 3 bump on
      the Zustand persist middleware flushes earlier broken-state
      localStorage. Default seeds `[{primary_designation, asc}]`.

- [x] **DataGrid sort disengaged** — `disableColumnSorting` on the
      grid; the panel is the sole sort UI. Server-side sort via
      the `sort` query param.

### Planner card list

- [x] **`PlannerTargetCard`** — one card per DSO, replaces the
      DataGrid rows. DSS2 thumbnail (with now-status glyph
      overlaid top-left), optional rig-framed thumbnail with
      coverage %, then a three-row info block (name + type pill +
      constellation; size / Mag V / distance / RA / Dec;
      tonight-only hours + meridian + max-alt + moon-sep). Whole
      card is a `CardActionArea` → opens detail panel.

- [x] **DataGrid deleted** — entire columns array (~240 lines) +
      `sortModel` / `onSortModelChange` / `onRowClick` / grid CSS
      overrides gone. Replaced with a `Stack` of cards +
      `TablePagination` (reusing the existing `PaginationActions`).

- [x] **Custom loading overlay** — opaque `background.paper`
      overlay on the Paper wrapper during
      `isLoading || isFetching`. Bypasses MUI X's built-in
      linear-progress bar that used to peek through as clipped
      text inside the column-header row.

### Planner detail panel polish

- [x] **Third selector (Location · Horizon · Rig)** — renamed the
      existing location + rig selectors to match the naming in
      the detail panel; added Horizon between them. Changing
      location resets the horizon to that location's default.

- [x] **Best-time-of-year chart** — moon-separation replaced
      the ToggleButton with a dropdown (`Ignore moon` / `Moon > N°`
      with values 0/15/30/45/60/75/90). Default sourced from new
      `planner_moon_sep_deg` user setting (default 0 = ignore
      moon). Chart line uses `curveMonotoneX` — monotone-preserving
      cosmetic rounding with no overshoot on horizon spikes.

- [x] **Scale row** — when a rig is selected, the detail panel
      shows a one-line caption with pixel size (μm), image scale
      (arcsec/px), and FOV below the image.

- [x] **Type + distance chips in header** — friendly
      `displayDsoType` name (not raw NGC code) and distance shown
      as `pc · ly` (both units).

- [x] **FovSimulator rotation slider** — added inline with the
      rotation-reset button.

### Now-status fix

- [x] **Daytime-before-tonight logic** — previously an afternoon
      fetch would sample `now → dark_end`, so an object that had
      set in the morning but would re-rise tonight read as "set".
      Fix: decision tree now splits on `now` vs dark window —
      post-dawn returns empty, daytime-before-tonight samples only
      the dark-window interval (with "up" never firing),
      in-astro-dark samples `now → dark_end` like before.
      `compute_now_status` takes an explicit `astro_dark_start_utc`
      parameter.

### Frames-Well + settings

- [x] **Frames Well dual-thumb slider** — replaced the boolean
      toggle with a 0–200 % range slider. Backend: `frames_well`
      boolean replaced with `coverage_min_pct` / `coverage_max_pct`
      query params. Frontend: slider hides synchronously when
      `rigId` goes null (gated on the local state, not the
      response's `rig` summary which lagged one round-trip).

- [x] **"Size in frame" label** — user-facing rename of "Frames
      Well" in both the planner page and Settings.

- [x] **New Settings** — `planner_moon_sep_deg` (default 0),
      `planner_frames_well_min_pct` / `_max_pct` (defaults
      15 / 90). Wired into `core/config.py` + `api/settings.ts`
      + `SettingsPage.tsx` (Target Planner section).

### Polish

- [x] DSO-annotation popover: type moved to a pill next to the
      designation; "Show details" → "Switch to object".
- [x] Location dropdown "(default)" suffix removed on the planner
      main page.
- [x] Meridian + Max alt always render as two separate lines on
      the card (collapse-when-equal removed — consistent vertical
      rhythm reads better in the card list).
- [x] Sort panel summary pills visible when the accordion is
      collapsed; expand/collapse chevron indicator.

### v0.19.0 Completion Criteria

- [x] Full backend test suite green (1779 passed, 3 skipped).
- [x] New tests: `test_planner_now_status.py` (6 tests covering
      all three day/night decision branches), updated
      `test_horizons_api.py` (24 tests for multi-horizon CRUD),
      updated `test_planner_annual_hours.py` + `_sky_track.py` +
      `_visibility.py` for the `PlannerHorizon` signature change.
- [x] Backend lint / format / bandit clean (0 / 0 / 0).
- [x] Frontend build clean.
- [x] Manual end-to-end: multi-horizon flow (create + set
      default + delete), planner sort panel (add / remove /
      reorder / flip direction), card list (scroll + click-to-
      open-detail + tonight/anytime toggle), now-status across
      day / night / post-dawn.

---

## v0.20.0 — DSO External References (Wikidata + Wikipedia)

**Status:** Done
**Branch:** `v0.20.0/dso-external-refs`

Adds a general-purpose `dso_external_ref` child table and populates
it from two sources: a Wikidata SPARQL fetch (bulk auto-matches) and
an editorial CSV override (bundled empty, ready for per-row fixes).
Wikipedia-article chips land on both the DSO catalog detail panel
and the planner detail panel. Wikidata QIDs are captured silently for
future features (cross-service enrichment, NED/SIMBAD lookups).

### Schema + loaders

- [x] **Migration 0022 `dso_external_refs.sql`** — new
      `dso_external_ref` table with `provider` CHECK enum
      `{wikidata, wikipedia}`, `UNIQUE (dso_id, provider, language)`,
      partial unique index `WHERE provider != 'wikipedia'` (Stephan's
      Quintet exception), `updated_at` trigger. Widens
      `dso_catalog_source.category` CHECK to include `'wikidata'`
      via the SQLite table-rewrite pattern. Uses
      `PRAGMA legacy_alter_table = ON` so the FK on
      `dso.source_catalog_id` doesn't get rewritten to follow the
      parent rename to the legacy table.

- [x] **SPARQL query (rewritten)** — the spec's per-catalog property
      IDs were mostly wrong (P774 = FIPS 55-3, P2024 = German cattle
      breed ID, P2581 = BabelNet ID, P3622 = Bandy player ID,
      P2295 = net profit). Replaced with the canonical Wikidata
      pattern: `P528` (catalog code) + `P972` (catalog) qualifier,
      filtered to the Q-items verified against live data (Q14530
      Messier, Q14534 NGC, Q190553 IC, Q14536 Caldwell, Q66381095
      Sharpless 2, Q3247327 Barnard, Q1479861 PGC, Q615925 UGC). Plus
      three direct-ID shortcuts (P3208 NGC, P4095 PGC, P6340 UGC) as
      a recall safety net. ~58k astronomical entities hit the query;
      only catalog-ID matches ingest.

- [x] **`catalog_loader/wikidata.py`** — SPARQL fetcher. GET to
      `query.wikidata.org/sparql` with UA
      `NightCrate/{version} (https://github.com/fbaptiste/nightcrate)`
      (UA is required by Wikidata's policy). TSV response lands
      atomically in `APP_DIR/catalogs/wikidata/`. `query_version` in
      `version.json` invalidates stored TSVs when the query changes.

- [x] **`catalog_loader/wikidata_tsv.py`** — parser. Strips SPARQL
      URI wrappers, un-quotes literals, strips catalog prefixes
      (`"NGC "`, `"M "`, `"SH 2-"`, etc.) and leading zeros. Direct
      -ID shortcuts take precedence over the P528 canonical form
      (they need no prefix stripping).

- [x] **`catalog_loader/wikidata_loader.py`** — matcher +
      inserter. Resolves Wikidata records to DSOs via
      `dso_designation.search_key`. Single match → upsert. Zero
      matches → skip silently (DEBUG log). **Multi-match → splay
      the refs across every matching DSO** (OpenNGC has per-catalog
      splits: NGC 1316 + PGC 12769 are the same galaxy, Crab Nebula
      has both NGC 1952 and Sh2-244 rows, Trifid has NGC 6514 + B 85,
      etc. — Wikidata unifies them under one entity; we duplicate
      the refs so the user sees the chip on whichever DSO they land
      on). Upserts both a `wikidata` row and (if enwiki sitelink
      present) a `wikipedia` row per matched DSO.

- [x] **`catalog_loader/external_refs_loader.py`** — editorial
      CSV override, mirroring `augment_loader.py`. Upsert rows
      overwrite Wikidata-sourced refs; suppression rows (empty
      identifier + url) delete. Strict validation: invalid
      provider / missing language for wikipedia / present language
      for wikidata → abort load with row number in the error.

- [x] **Registry + load order** — Wikidata runs last among remote
      sources (after Sharpless, Barnard, 50 MGC) so every DSO
      exists before matching. CSV override runs immediately after
      Wikidata — "later wins" precedence for overrides.

### API + admin

- [x] **`GET /api/dso/{id}` + `/lookup`** — response now includes
      `external_refs: list[ExternalRef]`. Ordering: `wikipedia`
      first, `wikidata` second. Empty array when no refs exist.
      List responses remain unchanged (detail-only per spec).

- [x] **Admin endpoints** —
      `GET /api/admin/catalogs/wikidata/remote-version` (sentinel
      response with `can_check_remote=false` because Wikidata has no
      remote version), `POST /api/admin/catalogs/wikidata/fetch`
      (runs the fetch + reload). Editorial CSV reloads via the
      existing `POST /api/admin/catalogs/nightcrate/reload`.

### Frontend

- [x] **Shared `DsoExternalRefs` component** — renders Wikipedia
      chips only (Wikidata QIDs stored but hidden). Returns null
      on empty array. Chips are `<a>` elements opening in new
      tabs with `rel="noopener noreferrer"` + aria-labels.

- [x] **Integration** — mounted after the Designations section in
      `DsoDetailPanel.tsx` (catalog page) and between the
      FOV-coverage block and Sky position in
      `PlannerDetailPanel.tsx`. The planner panel already
      re-fetches `GET /api/dso/{id}`, so it automatically picks
      up the new field.

- [x] **Admin → Catalogs rows** — two new rows: Wikidata (with
      `Fetch from Wikidata` button) and NightCrate external refs
      (bundled; reloaded via the existing top-of-panel
      "Reload all from local cache" action).

- [x] **Attribution** — automatic. Wikidata's `attribution` text
      (set in registry.py) covers both the CC0 source license and
      the Wikipedia note ("article content is not bundled; links
      load directly from wikipedia.org").

### Vendored

- [x] `data/catalogs/nightcrate/dso_external_refs.csv` — empty body
      with column header + explanatory comments.
- [x] `data/catalogs/nightcrate/LICENSE-CC0.txt` — full CC0 1.0
      dedication text (Wikidata's license; carried for
      transparency even though CC0 imposes no requirements).

### Horizon staging restoration (Option B)

v0.19.0's LocationHorizonsSection rewrite accidentally dropped the
v0.13.0 staged-save semantic — horizon edits persisted immediately
instead of being committed with the outer Location editor's Save
button. Option B restores the full staged flow.

- [x] **Backend atomic-create** — `LocationCreate.horizons:
      list[HorizonCreate] | None` optional field on `POST /api/
      locations`. When a non-empty list is supplied, the endpoint
      creates the location + all horizons in a single transaction
      and skips the `0° flat` auto-seed. 422 on empty list,
      duplicate-default, multiple-custom, duplicate-name.
      8 new validation tests.
- [x] **Frontend staged-state model** —
      `components/locations/horizonStaging.ts`. Defines
      `StagedHorizon` (state tag: `unchanged` / `new` / `modified`
      / `deleted`), lifecycle helpers, and the save-dispatch plan
      builder for existing-location diff.
- [x] **LocationHorizonsSection rewrite** — operates purely on the
      staged state + onChange prop passed by the parent. No network
      calls. Per-row `state` chips (new/modified/deleted) so the
      user sees exactly what'll commit.
- [x] **LocationsPage orchestration** — stagedHorizons state
      lifted; `openCreate` seeds a 0° default; `openEdit` fetches
      server horizons and populates the staged list;
      `hasUnsavedChanges` extends to include horizon diffs (matches
      v0.13.0); `handleSave` dispatches atomic-create for new
      locations and an ordered diff-apply
      (creates → updates → promote-default → deletes) for existing
      ones.

### v0.20.0 Completion Criteria

- [x] Full backend test suite green (1790 passed / 3 skipped).
      37 new tests:
      `test_wikidata_tsv.py` (10), `test_wikidata_loader.py` (9 —
      incl. NULL-language dedup regression + multi-match duplication),
      `test_external_refs_loader.py` (10),
      `test_locations_api.py` +8 (atomic create + validation),
      `test_dso_api.py` +4 (external_refs field presence,
      ordering, list-response omission, lookup shape),
      `test_admin_api.py` +3 (Wikidata remote-version sentinel,
      fetch-requires-db, network-failure 502).
- [x] Backend lint / format / bandit clean.
- [x] Frontend build clean.
- [x] SPARQL query verified against live Wikidata (M42, M31,
      Andromeda, Horsehead all resolved correctly).
- [x] Multi-match design (Option 2): Wikidata entities that cross-
      reference multiple NightCrate DSOs (Crab = NGC 1952 + Sh2-244,
      California Nebula = NGC 1499 + Sh2-220, etc.) splay the ref
      onto every matching DSO so the chip surfaces regardless of
      which DSO page the user lands on.
- [x] Horizon staging restoration (Option B): Location editor
      dialog owns horizon state end-to-end; Save commits atomically,
      Cancel discards; per-row new/modified/deleted chips visible.
- [x] CLAUDE.md guardrail + memory note added so the horizon
      staging contract doesn't get regressed again.

### Post-review polish

- [x] **Atomic horizon-replace endpoint** —
      `PUT /api/locations/{id}/horizons` takes the full desired
      horizon set and applies creates / updates / deletes in one
      SQL transaction. Replaces the retired client-side
      `_applyStagedHorizonsToExisting` helper which (a) couldn't
      offer true atomicity against mid-save network failures and
      (b) tripped `idx_location_horizon_one_custom` (409) on the
      "replace-custom" pattern (delete old custom + add new one).
      Frontend uses `replaceLocationHorizons` from `api/horizons.ts`.
      7 new tests covering atomic apply + custom-swap + validation.
- [x] **Parallel pytest** — `pytest-xdist` dev-dep + `make
      test-fast` target. Full suite 392s → 215s on a 10-core Mac
      with identical pass count.
- [x] **DSO catalog + Planner detail — Wikipedia as a link, not a
      chip.** Theme-primary color + underline-on-hover + trailing
      `OpenInNewIcon` (14 px). The chip form was
      indistinguishable from non-clickable designation chips.
- [x] **Planner detail header reorganisation.** Three lines:
      (name + constellation) · (common name) · (type pill + alt
      catalog chips). Distance moved out of the header entirely
      into the fact grid below the image. Removed the
      "fits comfortably at X%" narrative — the simulator already
      shows framing.
- [x] **Planner detail fact grid — three explicit rows.** Row 1
      Distance / Size / FOV coverage; Row 2 Hours / Max alt /
      Meridian / Moon sep; Row 3 Mag V / Mag B.
- [x] **SkyPositionGraph "now" indicator.** Teal vertical line,
      triangle anchor on the 90° grid, minute-aligned auto-tick
      (no mouse interaction needed). Magnetic snap integration.
      Meridian moved to its own tier (tier 4) so a
      meridian-near-sunset no longer collides.
- [x] **SkyPositionGraph hourly ticks** via `d3.timeHour.range`
      (was every-other-hour from the `.ticks(6)` auto-round).
- [x] **Best-time-of-year chart January label** — fixes a skipped
      `d3.timeMonths` boundary when the data range starts
      mid-month.

---

## v0.21.0 — Target Planner Scoring Algorithm

**Status:** Done
**Branch:** `v0.21.0/target-scoring`

Adds a per-target **0–100 quality score** with a categorical chip
(Excellent / Good / Fair / Poor) and a transparent breakdown on
every Tonight-mode planner card + detail panel. Answers the single
question *"how good a target is this for tonight's session, given
my equipment and what I plan to capture?"* by combining two hard
gates and four quality dimensions (observability, meridian timing,
moon impact, frame fit) via weighted geometric mean. 25+ user-
tunable parameters — every weight, threshold, and sensitivity —
live in a new Settings accordion with tooltips. Deferred: surface-
brightness modifier, in-app doc surfacing, Anytime-mode scoring.

### Backend

- [x] **`Settings` scoring fields + validator** — 25 new
      `scoring_*` fields on `core/config.py:Settings` (4 weights,
      7 moon sensitivities, 7 moon min-separations, cluster
      modifier, observability min-altitude, frame-fit ideal +
      spread, 3 quality-chip thresholds, 2 hard-gate caps). Pydantic
      `model_validator` enforces descending thresholds
      (`excellent > good > fair`) and non-negative weights. No
      migration — KV settings table absorbs the new rows via
      Pydantic defaults.
- [x] **`VisibilitySnapshot` retains time-series arrays** — new
      `VisibilityTimeSeries` dataclass on
      `services/planner_visibility.py` keeps per-target alt /
      visible-mask / moon-separation arrays + shared moon-altitude
      (T,) so scoring can evaluate per-timestep observability +
      moon dimensions without recomputing astropy transforms.
      Cache key unchanged; the arrays are free since they were
      already computed-and-discarded in `_reduce_per_dso`.
- [x] **`services/planner_scoring.py`** — pure service. Two-stage
      pipeline (hard gates → 4 quality dimensions → weighted
      geometric mean). `score_targets(inputs, snapshot, rig_fov,
      filter_intent, settings, tz)` returns `dict[dso_id,
      TargetScore]`. No DB / FastAPI deps; pure arithmetic over
      in-memory arrays. Cluster modifier triggers on `obj_type ∈
      {OCl, GCl, *Ass}` (Q5 scope).
- [x] **`services/planner_scoring_constants.py`** — closed
      `CLUSTER_OBJ_TYPES`, `FILTER_LINES = (Ha, SII, OIII, L, R,
      G, B)`, `QUALITY_LABELS`.
- [x] **API wiring in `list_targets`** — new `filter_intent`
      query param (comma-separated filter-line codes; 422 on
      unknown codes). After the filter loop, scoring runs over the
      surviving items in Tonight mode; results (score_pct +
      quality_label + score_breakdown) attach to each
      `PlannerTargetItem`. New sort field `score_pct` added to
      `PLANNER_SORT_FIELDS`. Default Tonight sort is now
      `[score_pct:desc, primary_designation:asc]` (Anytime unchanged).
- [x] **`GET /api/planner/targets/{dso_id}/score`** — single-target
      endpoint for the detail panel's preview-state refetch.
      Accepts `location_id` / `horizon_id` / `rig_id` /
      `filter_intent` / `date`; returns `{score_pct, quality_label,
      score_breakdown}`. Reuses the visibility cache + scoring
      service; one extra row per call.
- [x] **Pydantic response models** — `ScoreBreakdownOut`,
      `DimensionBreakdownOut`, `SingleTargetScoreResponse` added
      to `api/planner_models.py`; score fields added to
      `PlannerTargetItem` (all optional, null in Anytime).

### Frontend

- [x] **`api/planner.ts`** — new `FilterLine`, `DimensionBreakdown`,
      `ScoreBreakdown`, `QualityLabel`, `SingleTargetScoreResponse`
      types; score fields on `PlannerTargetItem`; `filter_intent`
      on `fetchPlannerTargets`; `fetchSingleTargetScore(dsoId, params)`.
- [x] **`api/settings.ts`** — 25 new scoring fields typed.
- [x] **`stores/plannerStore.ts`** — `filterIntent: FilterLine[]`
      persisted via Zustand (version bumped to 4).
- [x] **`lib/plannerScoreColors.ts`** — colorblind-safe chip
      palette (blue / lighter blue / neutral gray / muted orange —
      no red/green). Mirrors the rig-calculator guide-suitability
      palette.
- [x] **`lib/plannerSortFields.ts`** — `score_pct` entry
      (Tonight-only).
- [x] **`components/planner/ScoreChip.tsx`** — number + quality
      label with colored background; `—` outlined chip for gated
      targets; tooltip surfaces the first gate-failure reason.
- [x] **`components/planner/ScoreBreakdownSection.tsx`** — final
      section of the detail panel. Shows the big chip + per-
      dimension rows (name, score bar, weight, contribution,
      human-readable inputs) or gate-failure reasons for unscored
      targets.
- [x] **`components/planner/FilterIntentSelect.tsx`** — toggle
      buttons for Ha / SII / OIII / L / R / G / B with
      per-line hint tooltips. Rendered in the planner-page filter
      row in Tonight mode only.
- [x] **`components/settings/PlannerScoringSection.tsx`** — new
      Settings card with one collapsible Accordion per parameter
      family (Weights / Moon sensitivities / Moon min-separations /
      Cluster / Observability + frame fit / Hard gates / Quality
      labels). Every control wrapped in a Tooltip explaining the
      setting + default + one concrete example of changing it.
- [x] **`PlannerTargetCard.tsx`** — `ScoreChip` at the head of the
      info block (Line 1).
- [x] **`PlannerDetailPanel.tsx`** — `ScoreBreakdownSection`
      appended as the final section. A `previewScoreQuery`
      `useQuery` refetches score against panel-local preview state
      (rig / horizon / location differ from page) and splices the
      fresh score into the item before rendering the breakdown —
      fixes the "change rig in detail panel, score stays frozen"
      bug surfaced in Q&A during implementation.
- [x] **`PlannerPage.tsx`** — `FilterIntentSelect` in the filter
      row (between Rig dropdown and Clear filters); forwarded to
      `fetchPlannerTargets`; Tonight mode only.
- [x] **`SettingsPage.tsx`** — mounts `PlannerScoringSection`
      after the existing Target Planner card.

### Docs

- [x] **`docs/planner-scoring.md`** — new user-facing reference
      doc. Sections: conceptual model (gates → dimensions →
      combination), each dimension in plain language, filter-
      intent multi-select + limiting-filter rule, full parameter
      reference, three worked examples (§15), tuning playbook,
      colorblind-palette rationale. In-app surfacing deferred.

### Tests

- [x] **57 new scoring tests** across 6 files (plus a shared
      `scoring_helpers.py`):
      `test_scoring_gates.py` (10 — 5 gates + 5 chip display),
      `test_scoring_dimensions.py` (17 — 5 observability + 6
      meridian + 6 frame fit),
      `test_scoring_moon.py` (10 — including the Ha+OIII → OIII
      limiting-filter assertion, L+R+G+B → B, cluster modifier on/off),
      `test_scoring_combination.py` (9 — zero-collapses, weight-0
      drops, dropped-dimension renormalize, spec §9.2 pinned
      number),
      `test_scoring_settings.py` (7 — ordered thresholds,
      non-negative weights, defaults-match-spec regression),
      `test_scoring_worked_examples.py` (4 — spec §15.1 M42/Askar
      V, §15.2 M42/C11, §15.3 NGC 7000 / Ha / full moon, plus a
      pinned Ha-vs-Ha+OIII collapse check).
- [x] Full backend suite green: 1854 passed / 3 skipped.
      `services/planner_scoring.py` at 96% coverage.

### v0.21.0 Completion Criteria

- [x] Every Tonight-mode target renders a score chip (number +
      label, or `—` + tooltip for gated).
- [x] Default Tonight sort is score descending; gated targets
      sort last regardless of direction (nulls-last policy).
- [x] Filter-intent multi-select on the planner page; empty
      selection → moon dimension neutral; multi-filter → limiting
      filter rule demonstrably applied.
- [x] Detail panel's score breakdown recomputes when panel-local
      rig / horizon / location overrides differ from the page's
      values (new `/targets/{id}/score` endpoint).
- [x] All 25 scoring settings exposed in a collapsible accordion
      with tooltips; Pydantic validator rejects invalid ordering
      live.
- [x] Reference doc at `docs/planner-scoring.md` covers every
      section of the spec's user-facing material.
- [x] All three §15 worked examples reproduce within ±5 score
      points; the frame-fit-collapse case (C11 at 500% coverage)
      lands at ≤ 30 as spec dictates.
- [x] Backend lint / format / bandit clean. Frontend build clean.
- [x] No red / green anywhere in the scoring UI — palette mirrors
      the rig-calculator guide-suitability palette.
- [x] Code simplification pass completed — dead `DIMENSION_LABELS`
      constant removed, unused `alt_row` parameter removed,
      `_make_dimension_row` helper extracted, IIFE in detail panel
      replaced with inline ternary, misleading JSDoc on
      `fetchSingleTargetScore` corrected.

---

## v0.21.1 — Scoring Polish + Planner UX + External Refs Extension

**Status:** Done
**Branch:** `v0.21.1/scoring-polish`

Started as a narrow polish pass (PR #26 code-review findings + a
startup-race fix that v0.21.0 testing exposed) and grew to absorb
every small UX request that landed during manual testing: nav drag-
reorder, planner card layout, score-breakdown bar sizing, a
collapsible planner filter bar, an "Update available" indicator on
the admin Catalogs panel, and a SIMBAD + NED extension to the
external-refs infrastructure introduced in v0.20.0.

### Code-review findings fixed

- [x] **`test_observability_circumpolar_high_altitude` pinned** —
      replaced `obs.score > 0.9` with
      `pytest.approx(0.9647, abs=0.001)`. Constant 75° altitude
      makes the expected quality deterministic via `sin(75°) =
      0.96593`, `airmass = 1.03528`, `max_airmass = 2.0`, quality
      `= 1 - 0.03528 / 1 = 0.96472` everywhere.
- [x] **`test_observability_linear_rise` pinned** — replaced
      `0.45 < obs.score < 0.58` with
      `pytest.approx(0.5330, abs=0.001)` after computing the
      numeric mean from the 120-sample linear sweep.
- [x] **`test_moon_ha_tolerates_full_moon` pinned** — replaced
      `moon.score > 0.8` with `pytest.approx(0.8844, abs=0.001)`
      after recomputing the full Ha-impact aggregate (0.15 × 1.0
      × √sin(45°) × (1 − 5/60) ≈ 0.1156 impact × 1.0 overlap
      → 1 − 0.1156 ≈ 0.8844).
- [x] **`plannerStore.ts` migrate function added** — v3 → v4
      bump now explicitly carries forward `selectedLocationId`,
      `selectedHorizonId`, `selectedRigId`, and `sortBy`, and
      defaults the new `filterIntent` to `[]`. Without an explicit
      `migrate`, Zustand's default behaviour is to discard all v3
      state on mismatch — which would wipe the user's saved rig /
      location / horizon / sort preferences on the v0.21.0 → v0.21.1
      upgrade.
- [x] **`DimensionBreakdownOut.key` typed as `DimensionKey`
      Literal** — replaced the loose `key: str` + enumerating
      comment with the already-defined `Literal["observability",
      "meridian", "moon", "frame_fit"]` imported from
      `planner_scoring.py`. The Pydantic response now enforces the
      allowed values at the API boundary AND publishes the enum in
      the OpenAPI schema.
- [x] **`api/planner.py` module docstring updated** — version
      range bumped to `v0.16.0–v0.21.0`, the route inventory now
      includes the new `GET /api/planner/targets/{dso_id}/score`
      endpoint + the pre-existing
      `/targets/{dso_id}/annual-hours` and `/dsos/in-region`
      entries that the previous docstring also missed.

### New fix — startup health-check race

- [x] **`App.tsx` no longer treats "backend unreachable" the same
      as "db_configured=false".** Adds
      `retry: Infinity` + exponential-backoff `retryDelay` capped
      at 3 s on the `useQuery(["health"])` call, and gates the
      `SetupWizard` render on `healthQuery.isSuccess` instead of
      `data === undefined`. Under `make dev`, Vite is ready in
      <200 ms but uvicorn takes ~5 s to boot (catalog loader
      integrity checks + astropy imports + redshift backfill);
      before this fix, the frontend burned through TanStack
      Query's default 3 retries during the first second and then
      permanently rendered the SetupWizard until the user
      manually hard-reloaded the tab. Race was pre-existing but
      v0.21.0's slightly-expanded startup path (scoring settings
      loaded via `get_settings()` on first health response)
      happened to make it noticeable.

### Nav drag-to-reorder

- [x] **`AppShell` splits nav into a pinned Home row + a drag-
      reorderable stack** (11 remaining items). Uses `@dnd-kit` with
      a `PointerSensor` distance-activation constraint (8 px) so
      clicks still navigate via `NavLink` while a pointer move ≥ 8 px
      starts a drag.
- [x] **Subtle `DragIndicatorIcon` in a 20-px leading slot** on every
      reorderable row (opacity 0.25 at rest, 0.6 on hover). Home
      renders an empty slot of the same width so its nav icon stays
      horizontally aligned with the draggable rows.
- [x] **`settings.nav_order: list[str]`** added to the Pydantic model
      (no migration — KV settings absorb new fields). Same forward-
      compat contract as `calculators_clock_order`: unknown routes
      filtered, missing-from-list routes appended at the end.
- [x] **Not surfaced on the Settings page** per user request — the
      reorder UI is the left-nav itself, no separate control needed.

### Planner card layout polish

- [x] **Score chip + Wikipedia link inline on Line 4** with a 20 px
      gap. Score chip moved from the card's upper-right corner (too
      crowded next to the thumbnails) and from Line 1 (was pulling
      attention off the primary designation).
- [x] **Wikipedia chip → Link + `OpenInNewIcon`** on the card (same
      pattern already in use on the detail panel). `stopPropagation`
      on the link click keeps the CardActionArea's detail-panel open
      from firing when the user clicks through to Wikipedia.

### Score breakdown visualisation

- [x] **Dimension bars capped at `width: 33%`** (min 160 px, max
      320 px) in `ScoreBreakdownSection`. Full-width bars read as
      progress indicators, which is misleading for a dimensional
      score gauge.
- [x] **Label row's `space-between` right edge aligns with the
      `NN%` readout** — both share a single container width, so
      "weight / contribution" caption right-aligns with the bar's
      percent column.

### Collapsible planner filter panel

- [x] **Filter / sort / rig Paper gets a chevron toggle** at the top
      (`TuneIcon` + "Filters, sort, rig" label on the left, expand /
      collapse chevron on the right). Body wrapped in `Collapse` with
      `unmountOnExit` so hidden controls don't consume layout.
- [x] **Session-only state** via a `useState<boolean>` — no
      localStorage, no server round-trip; a tab reload reopens the
      bar. Default open so first-run users see the full UI.

### External references extension (SIMBAD + NED)

- [x] **Migration 0023 `dso_external_refs_simbad_ned.sql`** — widens
      the `dso_external_ref.provider` CHECK from
      `('wikidata', 'wikipedia')` to
      `('wikidata', 'wikipedia', 'simbad', 'ned')` via the SQLite
      table-rewrite pattern (`PRAGMA legacy_alter_table = ON` so
      child FKs don't follow the parent rename). Indexes + trigger +
      partial `WHERE language IS NULL` unique index recreated on the
      new table.
- [x] **Wikidata SPARQL + parser + loader extended** — `P3083`
      (SIMBAD) is pulled as an additional `OPTIONAL` clause.
      `QUERY_VERSION` bumped to `v3`. `WikidataRecord.simbad_id` +
      whitespace-trimming parser logic land; loader pre-fetches
      `{dso_id: (primary_designation, obj_type)}` once per load to
      drive the per-match SIMBAD + NED inserts.
- [x] **SIMBAD chips — broad coverage.** Inserted for every matched
      DSO using P3083 when Wikidata has it, else fallback to
      primary_designation (SIMBAD's name resolver is tolerant). URL
      builder uses `urllib.parse.quote_plus`.
- [x] **NED chips — extragalactic-only.** The spec claimed Wikidata
      P2528 was NED — it's actually the Richter earthquake-magnitude
      scale. Wikidata has no reliable NED property at all. Fixed by
      synthesising NED URLs from primary_designation via NED's
      tolerant `byname` resolver, gated by
      `GALAXY_TYPES = {G, GPair, GTrpl, GGroup}`. Same fallback shape
      as SIMBAD, filter narrows it to galaxies.
- [x] **CSV override handles both new providers** —
      `_VALID_PROVIDERS` extended; CSV rows with `provider=simbad`
      or `provider=ned` upsert / suppress the same way
      `wikidata` / `wikipedia` do. `_LANGUAGE_AWARE_PROVIDERS` stays
      `{wikipedia}` only — both new providers require `language=NULL`.
- [x] **Attribution** — `WIKIDATA_CITATION` extended with CDS /
      Université de Strasbourg (SIMBAD) and NASA/IPAC/Caltech (NED)
      credits; surfaces automatically in Admin → Catalogs via the
      existing data-driven panel.
- [x] **API + types** — `ExternalRef.provider` Literal widened;
      `_EXTERNAL_REF_PROVIDER_ORDER = ("wikipedia", "simbad", "ned",
      "wikidata")`. Wikidata stays in the tuple for stable server-
      side sort but is filtered out at render time per the
      user decision.
- [x] **Frontend `DsoExternalRefs` generalised** — renders any
      provider in `{wikipedia, simbad, ned}` via a small
      `PROVIDER_LABEL` map. Wikidata filter stays (not surfaced).
      `PlannerDetailPanel` replaces its inline duplicated Wikipedia
      block with the shared component.

### Admin Catalogs — Update-available indicator

- [x] **`SourceRow` gains `updateAvailable` + `updateTooltip`
      props** — when truthy, renders a small primary-outlined
      "Update available" chip next to the row's display name. Every
      downloadable catalog wires the flag through:
        - **OpenNGC** — tag-name diff (e.g., v2.0.3 → v2.0.4).
        - **VizieR (Sharpless / Barnard) + 50 MGC** — first-run
          "hasn't been fetched yet."
        - **Wikidata** — first-run OR `installed_query_version !=
          current_query_version` (v3 flagged the SIMBAD + NED
          extension for users still on v1/v2 TSVs).
- [x] **Backend unchanged** — every `/remote-version` endpoint
      already reported `has_update`; only the UI plumbing was
      missing.

### v0.21.1 Completion Criteria

- [x] Every deferred PR #26 code-review finding addressed (2
      ≥80 + 4 sub-80).
- [x] Backend lint / format / bandit clean.
- [x] Frontend `tsc --noEmit` + `npm run build` clean.
- [x] Full backend suite green (1862 passed / 3 skipped), no
      coverage regression on `services/planner_scoring.py` (still
      ≥ 96%).
- [x] Version headers bumped across the four tracked docs.

---

## v0.22.0 — PHD2 Guide-Log Analyzer Pass A (Parser + Viewer Skeleton)

**Status:** Done
**Branch:** `v0.22.0/phd2-analyzer-pass-a`

First pass of a multi-version PHD2 guide-log analyzer (v0.22.0 →
v0.30.0, functional spec at
`docs/nightcrate-phd2-analyzer-spec-v2.md`). v0.22.0 delivers the
parser, a D3 time-series chart, a five-phase calibration plot,
per-section summary metrics (RMS / peak / duration / SNR / frame
count), and a warnings drawer — enough for "open a PHD2 log, see the
guiding graph" as a standalone feature. Every later pass extends this
foundation without rework.

### Goals

- Anchor the multi-version arc on a correct, format-tolerant parser.
- Prove the data-model shape against a single high-confidence chart
  before the UI surface widens.
- Ship as a standalone feature (spec §4.1) — no catalog dependency.

### Parser (§3 of the spec)

- [x] File identification via content sniff (first non-blank line
      starts with `PHD2 version`); debug logs raise
      `Phd2DebugLogRejected` → HTTP 422.
- [x] Log-version capture when the PHD2 app version is blank (ASIAIR
      bundles).
- [x] Section splitting — Calibration + Guiding sections kept in file
      order (not timestamp order, per spec §3.8).
- [x] Section-header block parsing — regex-by-name for 35+ known keys;
      unrecognized keys retained verbatim in `freeform_keys` so future
      PHD2 versions don't lose information.
- [x] Guiding CSV parsing — by-name mapping, 18-vs-19-column arity
      tolerance (ErrorDescription trailing field), empty fields resolve
      to `None` (never `0.0`), DROP frames preserve `None` in
      positional fields.
- [x] ErrorDescription captured verbatim from the log — no hardcoded
      code→string table (spec §11.2 documents why the prior table was
      wrong).
- [x] Calibration CSV parsing — five named phases
      (West/East/Backlash/North/South) with derived angle + rate +
      parity extracted from the `<Axis> calibration complete` prose
      lines.
- [x] INFO event classification — closed vocabulary + raw-message
      retention for fallthrough: `settle_begin`, `settle_end`,
      `lock_position_set`, `dither`, `server_pause`, `server_resume`,
      `star_selected`, `alert`, `guiding_enabled`, `guiding_disabled`,
      generic `info`.
- [x] Locale-decimal recovery — detect via token-count heuristic
      (`T > C × 1.3`), rebuild float fields (integer columns like
      Frame and RADuration stay as a single token).
- [x] Backward-timestamp tolerance — sections in file order with a
      warning when start times go backward.
- [x] Parse-warning collection across the file (locale, backward
      timestamp, missing pixel scale, short row, error-count summary).

### Data model

- [x] Pydantic v2 models: `ParsedLog`, `LogSection`, `SectionHeader`,
      `GuidingSample`, `CalibrationSample`, `CalibrationPhase`,
      `LogEvent`, `ParseWarning`. All distances in pixels;
      `arcsec_scale` surfaced alongside metrics so the UI renders
      dual-unit labels without re-reading the header.
- [x] `Phd2DebugLogRejected` exception (ValueError subclass).

### Metrics (v0.22.0 scope only)

- [x] `compute_section_metrics`: RMS RA / Dec / total, peak RA / Dec,
      frame count + error count, duration, mean SNR, median SNR, mean
      star mass. Pixel-only compute; arcsec conversion at display time.
- [x] DROP frames excluded from RMS (positional fields are `None`).
- [x] Calibration sections route through `compute_section_metrics`
      returning `None` for guiding metrics — uniform API shape across
      section kinds.

Drift + oscillation + settle-aware filtering → Pass B (v0.23.0).

### API

- [x] `POST /api/phd2/parse` — body `{path: str}`, returns
      `ParseResponse` (ParsedLog + per-section metrics).
- [x] In-process TTL cache keyed by `(path, mtime_ns, size)` with
      per-key locking (mirrors `api/images.py`). 120 s TTL, 8-entry
      cap.
- [x] `GET /api/phd2/cache/stats`, `POST /api/phd2/cache/clear`.
- [x] 404 on missing file, 400 on directory, 422 on debug log /
      non-PHD2 content.

### Frontend

- [x] New `/guide-logs` route + nav entry in `AppShell.tsx`
      (`ShowChartIcon`, auto-appends via the v0.21.1 nav-reorder
      machinery for users with saved orders).
- [x] `pages/GuideLogsPage.tsx` — path input + Open button + parse
      status + summary strip + warnings drawer.
- [x] `components/guidelogs/TimeSeriesChart.tsx` — D3 time-series:
      RA blue + Dec orange traces, correction bars below the traces,
      SNR + StarMass sub-panels, crosshair cursor with all-trace
      readouts, D3 zoom/pan + reset. **Null values break the line**
      (never interpolate across DROP frames — the quiet correctness
      win that justifies the parser discipline).
- [x] `components/guidelogs/CalibrationPlot.tsx` — five-phase
      stepped path in dx/dy pixel space, origin-preserving square
      layout, phase legend with derived angle + rate + parity +
      axis-separation readout.
- [x] `components/guidelogs/StatsPanel.tsx` — dual-unit
      ("0.42 px / 1.66″") rendering when `Pixel scale` is declared,
      pixels-only otherwise.
- [x] `components/guidelogs/WarningsDrawer.tsx` — chip in header
      expanding to a short list.
- [x] `components/guidelogs/SectionNavigator.tsx` — left-column list
      with type chip, start time, duration, and a top-line stat.
- [x] `api/guideLogs.ts` — TypeScript types mirroring Pydantic
      models, `parseGuideLog`, cache endpoints.

Interaction polish (manual range selection, lock-scale, copy-stats,
recently-analyzed list, reveal-in-finder, drag-and-drop ingestion) is
deferred to Pass C (v0.24.0) per the approved plan.

### Tests

- [x] 47 initial PHD2 tests (parser §3 correctness + metrics pinned
      regressions + API endpoints). Plus 8 `TestSettleExclusion`
      tests added during the post-landing polish round below. Total
      suite: **1928 passed, 3 skipped** (up from 1862 at v0.21.1).
- [x] Fixtures: trimmed ASIAIR sample + 5 synthetic edge-case
      fixtures (locale-corrupted, backward-timestamp, missing pixel
      scale, debug-log, mixed arity).
- [x] Pinned RMS regression tests with hand-computed expected values.
- [x] DROP-frame handling verified: `None` in positional fields,
      never `0.0`.

### Pass-A polish round (post-initial-landing)

Significant work on top of the initial landing, some brought forward
from Pass B scope because the affected behaviour was actively
misleading users.

- [x] **Settle-window exclusion in guide-quality metrics** (PHD2 /
      convention — brought forward from Pass B). Peak /
      RMS / SNR / Mass no longer count samples bracketed by
      `settle_begin` / `settle_end` events, so the numbers reflect
      actual guiding instead of dither-excursion amplitudes. New
      `_settle_intervals` state-machine helper (tolerant of None-
      anchored, lone-end, unclosed-begin, duplicate-begin), new
      `frame_count_in_settle` / `frame_count_in_stats` fields on
      `SectionMetrics`, chart settle-region shading, page-level
      "Include settle frames in stats" toggle. Backend filters at
      source; frontend `lib/phd2GuidingMetrics.ts` mirrors the math
      client-side so the toggle flips without a round-trip.
- [x] **Viewport Summary panel** — second `StatsPanel` above the
      Section Summary that recomputes every metric over just the
      chart's visible X-domain samples. Page owns a `viewport` state,
      chart exposes `onViewportChange`. Both panels are collapsible.
- [x] **Event vertical-line markers with row-packed labels** —
      replaces the earlier event-dot indicator. Non-dither events get
      a thin dashed vertical line spanning every panel plus a short
      text label in one of three stacked rows (greedy-packed so
      labels don't overlap). Dither keeps its triangle marker.
- [x] **Chart polish** — clip paths per panel data area; rotated
      y-axis labels; axis extreme ticks (`withDomainExtremes`);
      clipped-pulse caret indicators; pulse/SNR/mass tick rounding
      to drop float-precision artifacts; Guide-axis unit toggle
      (px / ″); SNR/Mass Auto/Fixed scale toggles; legend-aware
      auto-fit (hiding a series narrows the axis); sentinel filter
      for non-physical SNR/Mass values; per-section zoom reset;
      uniform panel background tint; main-panel vertical axes
      removed for parity with the sub-panels' look; +50 px gap
      between legend and chart so the hover tooltip has room.
- [x] **Left-column axis controls** — Guide unit / Guide axis /
      Pulse axis / SNR scale / Mass scale absolutely-positioned and
      each vertically centred on its target panel inside the SVG.
      Toggle wrapper uses `translateY(-50%)` so centring stays
      robust against MUI rendering-height surprises; label floats
      above via `position: absolute, bottom: 100%`.
- [x] **Tooltip restructured** — RA / Dec error + pulse grid with
      blanks (not em-dashes) for null cells; event info removed
      from the tooltip now that the chart's line+label markers
      convey it; tooltip anchored at the toolbar's top and extends
      downward so the chart area isn't reserved when hover is idle
      and the tooltip never escapes the Tabs panel.
- [x] **Navigator + warnings** — Section navigator is collapsible
      to a thin rail; warnings chip converted to a hover tooltip
      with friendly event titles instead of raw codes.
- [x] **Moonrise in Tonight calculator** — `_moon_rise_set` widened
      from the sun's 24 h noon-to-noon grid to a dedicated 48 h
      window anchored at local midnight, so daytime moonrises are
      captured instead of returning `None`. Applies beyond PHD2 —
      the Tonight at-a-glance calculator now reports actual
      moonrise times even when the moon rose earlier in the day.

### Docs

- [x] Spec at `docs/nightcrate-phd2-analyzer-spec-v2.md`.
- [x] CLAUDE.md — new "PHD2 Guide-Log Analyzer" section describing
      the architecture + the shared architectural principles that
      apply across the multi-version arc.
- [x] `nightcrate-current-state.md` — new feature entry, v0.22.0
      version bump.
- [x] New "Appendix: PHD2 Analyzer Roadmap" (below) — one-line
      descriptions of v0.22.0 → v0.30.0.

### Verification

- [x] Backend: `ruff check`, `ruff format --check`, `bandit -r src/`,
      `pytest -n auto` — **all green, 1909 tests pass**.
- [x] Frontend: `npm run build` — TypeScript clean.
- [ ] Manual UI rundown via `make dev` — user task, see PR body.

### Out of scope (deferred to later passes)

See the PHD2 Analyzer Roadmap appendix for the full arc. Highlights:

- Scatter plot, unit toggle, drift/oscillation metrics, settle
  detection → Pass B (v0.23.0).
- Manual range selection, lock scale, copy stats, recent-files
  → Pass C (v0.24.0).
- FFT + unguided reconstruction + rig picker + worm markers
  → Pass D (v0.25.0).
- GA handling + AO toggle → Pass E (v0.26.0).
- Diagnostic engine → Pass F (v0.27.0) + Pass G (v0.28.0).
- Multi-log comparison + persistence → Pass H (v0.29.0).
- HTML report + catalog integration → Pass I (v0.30.0).

---

## v0.23.0 — PHD2 Pass B (Drift + Oscillation + Scatter + Event List)

**Status:** Done
**Branch:** `v0.23.0/phd2-pass-b`

Second pass of the nine-version PHD2 arc. Most of the original Pass B
appendix scope (settle detection, settle exclusion, unit toggle,
event markers, warnings polish) actually landed during the v0.22.0
Pass A post-landing polish round; v0.23.0 finishes off the remaining
Pass B items per spec §5.2 / §5.3 / §5.6:

### Metrics (spec §5.2 rest)

- [x] `drift_ra_px_per_min`, `drift_dec_px_per_min` — least-squares
      slope of `ra_raw_px` / `dec_raw_px` vs time, sign-preserving.
      Pure-Python closed-form regression; no scipy.
- [x] `oscillation_ra`, `oscillation_dec` — fraction [0, 1] of
      consecutive-pair sign flips over the stats-sample subset;
      zero-valued samples skipped (no sign).
- [x] Both compute over the same settle-filtered `stats_samples` as
      RMS/peak.
- [x] StatsPanel renders two new rows per metric per panel (Section
      Summary + Viewport Summary). Drift dual-unit when pixel scale
      is declared; oscillation as a percentage.

### Scatter plot (spec §5.3)

- [x] New `components/phd2/ScatterPlot.tsx` — D3 SVG scatter of
      `(dx, dy)`, one point per non-null sample.
- [x] 1σ + 2σ dispersion ellipses from a closed-form 2×2 covariance
      eigen-decomposition; orange centroid marker (filled + ring) so
      an off-origin offset — indicating calibration drift — is easy
      to read at a glance.
- [x] Square data area; axes symmetric around zero; dual-unit tick
      axis labels when pixel scale is known.
- [x] Collapsible, right-hand info strip with centroid coordinates,
      1σ axis lengths, and principal angle.
- [x] Settle-filtered by default (matches the Section Summary
      behaviour); the include-settle toggle flips both.

### INFO event list (spec §5.6)

- [x] New `components/phd2/EventList.tsx` — collapsible list of
      anchored events with a friendly kind chip, wall-clock time
      (falls back to elapsed seconds when the section lacks a start
      ISO), and the raw message / parsed Δx/Δy for dither.
- [x] Click a row → `scrollToTime(time_seconds)` imperative handle
      on the time-series chart. Preserves the chart's current zoom
      when already zoomed in; applies a ~60 s window otherwise so
      the event is visually distinct.
- [x] TimeSeriesChart switched to `forwardRef` + `useImperativeHandle`
      to expose the handle without drilling d3 through props.

### Tests

- [x] 11 new PHD2 metrics tests (`TestDrift`, `TestOscillation`):
      pinned slope values, flat-data zero case, settle exclusion,
      single-sample `None` guard, identical-timestamps `None`,
      zero-value skipping, all-zero-axis `None`. Total suite:
      **1939 passed, 3 skipped** (up from 1928 at v0.22.0).

### Out of scope (→ v0.24.0 Pass C)

- Manual range selection on the chart (drag-to-select + exclude-drag).
- Lock-scale across sections.
- Copy stats to clipboard.
- Reveal-in-finder.
- Recent-files history.

These are interaction-polish items (spec §5.5) that would double
this pass's scope.

---

## v0.24.0 — PHD2 Pass C (Range Selection + Copy Stats + Recent Files)

**Status:** Done
**Branch:** `v0.24.0/phd2-pass-c`

Third pass of the nine-version PHD2 arc. Completes the spec §5.5
interaction-polish bundle that was deferred from Pass A + B.

### Manual range selection + exclusion (spec §5.5)

- [x] **Multi-additive selections** — Shift+drag appends a teal
      band to the selections list; successive drags accumulate.
- [x] **Multi-additive exclusions** — Shift+Alt+drag appends a
      hatched-grey band to the exclusions list. Distinct hatch-
      pattern `<defs>` fill separates them from solid-grey settle
      shading.
- [x] Net sample set = **union(selections) − union(exclusions)**.
      Empty selections falls back to the zoom-driven viewport, then
      to the full section.
- [x] d3.zoom's `.filter` excludes shift-keyed mousedowns so the
      new gestures don't fight with existing pan. Cross-drag
      ``xScaleRef`` captures the live scale so shift-drag + scroll-
      zoom simultaneously doesn't drift the inversion.
- [x] **Live preview** — a brighter ``pendingSelection`` /
      ``pendingExclusion`` rect follows the cursor during drag;
      committed on mouseup (or discarded if < 0.25 s drag).
- [x] **Per-zone × close buttons** — rendered OUTSIDE the main-
      panel clipPath so they stay clickable even when the band is
      clipped by zoom. Teal × for selections, neutral × for
      exclusions; offset vertically so ×s on overlapping right
      edges don't collide.
- [x] **Toolbar actions** — **Include in view**, **Exclude in
      view** (disabled when not zoomed), **Clear all (N)** (count
      badge when zones present), and the existing **Reset X zoom**.
- [x] All zones reset on section change.
- [x] Viewport Summary panel folds into **Selection Summary** when
      any selection exists; subtitle shows the wall-clock range
      (1 selection) / "N selections" (multi), plus any exclusion
      detail.

### Copy stats to clipboard (spec §5.5)

- [x] StatsPanel header (guiding kind only) gains a
      `ContentCopyIcon` button. Click → TSV-formatted stats
      (title + subtitle header, then one label/value row per
      metric) write to `navigator.clipboard`.
- [x] Transient MUI Snackbar ("Stats copied to clipboard")
      confirms the write.

### Recent files history (spec §5.5)

- [x] New `lib/phd2RecentFiles.ts` — localStorage-backed store
      with a 10-entry cap. `getRecentFiles` / `addRecentFile` /
      `removeRecentFile` / `clearRecentFiles` helpers + a tiny
      `formatRelativeTime` formatter (no date-fns dep).
- [x] Added to history only on **successful parse** (prevents a
      typo path from polluting the list).
- [x] Empty-state landing page shows "Recent logs" when entries
      exist: filename (monospace, clickable to reopen), full path
      (secondary, title-hover for full text), relative timestamp,
      × icon per entry, "Clear all" button.

### Out of scope

- Lock-scale across sections — **already shipped** via the Guide
  / Pulse axis Fixed dropdown modes which persist per-chart and
  survive section switches.
- Reveal-in-finder — user-vetoed.

### Verification

- Frontend `npm run build` clean.
- Backend `uv run pytest` stays at **1939 passed / 3 skipped**
  (no backend changes).
- Manual flows cover: shift-drag select → stats recompute;
  shift+alt-drag exclude → stats drop samples; clear buttons
  wipe each band; section switch resets both; copy icon writes
  TSV + shows Snackbar; empty state shows recent-logs list;
  click to reopen; × removes; Clear all wipes.

---

## v0.25.0 — PHD2 Pass D-1 (Metric Foundation)

**Status:** ✅ Done
**Branch:** `v0.25.0/phd2-metric-foundation`
**Spec ref:** `docs/nightcrate-phd2-analyzer-spec-v4.md` §5.2.1 – §5.2.8

### Goal

Replace v0.22.0's metric formulas with exact formulas so NightCrate's reported numbers (RMS, drift, PA error, scatter ellipse rotation, peak, oscillation, frame counts) match for the same log. Foundational: every subsequent version (FFT, diagnostics, trends) consumes these metrics, so getting them aligned to the reference tool first avoids re-justifying differences later.

### Why it stands on its own

Corrected metrics are immediately user-visible — the Section Summary panel's RMS, drift, and oscillation rows all update. PA error becomes a new visible metric. Users who cross-reference NightCrate against will see matching numbers post-merge.

### Scope

#### §5.2.1 — RMS as standard deviation

`LFit::varx` is the **population variance** (West-incremental form). RMS is therefore standard deviation:

$$\text{RMS}_{\text{RA}} = \sqrt{\frac{1}{N}\sum_{i=1}^{N}(x_i - \bar{x})^2}$$

NOT RMS-from-zero `sqrt(mean(x²))`. The two differ when there's a systematic offset — sustained Dec drift, calibration centroid offset.

#### §5.2.3 — RA drift via corrections-subtraction

algorithm (`AnalysisWin.cpp` lines ~135-160):

```
ra0, t0 = first included frame's (raraw, dt)
ra1, t1 = last included frame's (raraw, dt)
sum = Σ e.raguide for e where e.included ∧ e.radur ≠ 0  (signed)
RaDrift_px_per_sec = (ra1 − ra0 − sum) / (t1 − t0)
drift_ra_px_per_min = RaDrift_px_per_sec × 60
```

Total raw position change = total mount drift + total guide correction. Least-squares slope (current code) undershoots the true mount drift when the algorithm successfully damped the drift. Note `e.included` (not the stricter `Include(e)`) when summing corrections — DROP frames with valid RAGuideDistance values still contribute.

#### §5.2.4 — Dec drift via unguided-frames-only accumulation

Dec is typically guided in only one direction. accumulates Dec position changes only across frames where the previous frame was unguided (`decdur == 0`):

```
y_accum = 0
prev_y = first_included.decraw
prev_guided = (first_included.decdur != 0)
LFit fit ; fit.data(first_included.dt, 0)

for each subsequent included frame:
    if not prev_guided:
        y_accum += (decraw − prev_y)
        fit.data(this.dt, y_accum)
    prev_y = decraw
    prev_guided = (decdur != 0)

DecDrift_px_per_sec = fit.B()
drift_dec_px_per_min = DecDrift × 60
```

#### §5.2.6 — PA error as per-section metric

Formula per `AnalysisWin.cpp` line ~166:

$$\alpha_{\text{arcmin}} = \frac{3.8197 \cdot |drift_{dec\_px/min}| \cdot pixel\_scale}{\cos(\delta)}$$

Pre-conditions: section is guiding, `declination_deg` known, `drift_dec_px_per_min` computable, `pixel_scale` known. When any pre-condition fails, PA error = `None`; UI shows "PA error: not available" rather than coercing to a number.

#### §5.2.7 — Scatter ellipse rotation (Theta = atan2(covxy, varx))

`LFit::Theta` (line ~95) uses:

$$\theta = \text{atan2}(\text{cov}_{xy}, \text{var}_x)$$

NOT the textbook PCA rotation `θ = ½ × atan2(2·covxy, varx − vary)`. After computing θ, axes are computed by re-iterating samples (`AnalysisWin.cpp` lines ~210-240):

```cpp
double cost = cos(theta), sint = sin(theta);
LFit fitxy;
for each included frame:
    double dr = e.raraw − avg_ra;
    double dd = e.decraw − avg_dec;
    fitxy.data(dr * cost + dd * sint, dd * cost − dr * sint);
lx = sqrt(fitxy.varx);   // sigma along major axis
ly = sqrt(fitxy.vary);   // sigma along minor axis
elongation = (lx + ly > 1e-6) ? abs(lx − ly) / (lx + ly) : 1.0
```

NightCrate adopts this form for cross-tool consistency even though it's not textbook PCA.

#### §5.2.2 — Peak (sign-preserving max-by-abs)

Per `AnalysisWin.cpp` line ~196: `if (fabs(e.raraw) > fabs(peak_r)) peak_r = e.raraw;`. Current code uses `max((abs(v) for v in ra_raw), default=None)` — drops the sign. Fix:

```python
def _signed_peak(values: list[float]) -> float | None:
    if not values:
        return None
    return max(values, key=abs)
```

#### §5.2.5 — Oscillation (count zero values as positive)

Spec §11.14: *"Frames where x_i = 0 (which is rare) are conventionally treated as positive for this calculation."* Current code skips zeros; spec says treat as positive. Fix:

```python
def _oscillation_rate(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    signs = [1 if v >= 0 else -1 for v in values]
    flips = sum(1 for a, b in zip(signs, signs[1:], strict=False) if a != b)
    return flips / (len(values) - 1)
```

#### §5.2.8 — Frame counts and duration breakdown

Add `duration_total_seconds` and `duration_included_seconds` fields to `SectionMetrics`. Backend computes both at parse time (using the in_settle filter for `included`); user-exclusions are layered on top client-side via the existing `phd2GuidingMetrics.ts` helper.

### Math derivations

#### §M1 — RMS as population variance via West-incremental update

`LFit::data` method computes streaming population mean and variance:

```
n_new = n + 1
delta = x − μ_old
μ_new = μ_old + delta / n_new
var_new = (n × var_old + delta × (x − μ_new)) / n_new
```

Population variance (1/N denominator), NOT sample variance (1/(N-1)). `RMS = sqrt(var)` is therefore standard deviation.

For series `[1, 2, 3]`: RMS-from-zero ≈ 2.16; standard deviation ≈ 0.82. reports the smaller; NightCrate currently reports the larger. This is the difference users will see post-v0.25.0.

#### §M2 — Polar alignment formula reconciliation

The 3.8197 constant comes from converting Barrett's arcsec/min-form derivation to px/min input.

**Source distinction.** Two independent sources arrive at the same relationship:

- **Barrett** (celestialwonders.com) — cited directly in `AnalysisWin.cpp` line 166. Small-angle geometry of a polar-misaligned mount tracking through a sidereal day.
- **Starry Nights** (starrynights.us) — derives the same relationship empirically with a 0.262 arcsec/min/arcmin coefficient at the celestial equator.

Both produce the same number to within rounding: `3.8197 = 60 / 15.71 ≈ 1 / 0.262`. NightCrate uses exact 3.8197 constant for cross-tool consistency, citing Barrett's derivation per source-code attribution.

Form (px/min): `α_arcmin = 3.8197 × drift_px_per_min × pixel_scale / cos(δ)`

#### §M3 — Dec-drift unguided-frames-only accumulation

`y_accum` accumulates Dec position changes only when the previous frame was unguided (decdur == 0). Those frames reflect actual sky drift over the inter-frame interval. Frames where the previous frame was guided are skipped because the inter-frame change is dominated by the guide pulse.

Edge cases:
- First included frame: `y_accum = 0`, `fit.data(first.dt, 0)`.
- Single included frame OR all-guided frames: `fit.B()` returns 0 (matches ).
- Sections with no Dec guiding at all: every frame has `decdur == 0`, so every change is accumulated — equivalent to a least-squares slope of `decraw` vs `t`.

### Files to modify

**Backend:**

- [x] `backend/src/nightcrate/services/phd2_metrics.py` — replaced `_rms` with `_stddev`, added `_ra_drift_corrections_subtracted`, `_dec_drift_unguided_only`, `_polar_alignment_error_arcmin`, `_signed_peak`, `_elongation`. `_oscillation_rate` rewritten to treat zeros as positive per spec §11.14.
- [x] `backend/src/nightcrate/api/phd2_models.py` — `SectionMetrics` gained `polar_alignment_error_arcmin`, `elongation`, `duration_total_seconds`, `duration_included_seconds`; legacy `duration_seconds` removed.

**Frontend:**

- [x] `frontend/src/lib/phd2GuidingMetrics.ts` — full TS port of the formulas (stddev RMS, RA corrections-subtraction drift, Dec unguided-frames-only drift, signed peak, oscillation incl. zeros, PA error, elongation).
- [x] `frontend/src/api/phd2.ts` — `SectionMetrics` interface updated with the new fields.
- [x] `frontend/src/components/phd2/StatsPanel.tsx` — added "PA error" row (`1.23′`) + "Elongation" row. Frames row split onto multiple lines via `whiteSpace: pre-line`.
- [x] `frontend/src/components/phd2/ScatterPlot.tsx` — switched to `θ = atan2(covxy, varx)` form with re-iteration for `lx` / `ly`.

### Tests (~30 new + regression updates)

- [x] `tests/services/test_phd2_metrics.py` — every pinned-value test for RMS / drift / oscillation re-derived by hand. Six new test classes: `TestRmsAsStandardDeviation`, `TestSignedPeak`, `TestRaDriftCorrectionsSubtraction`, `TestDecDriftUnguidedFramesOnly`, `TestPolarAlignmentError` (incl. high-declination regression anchor at δ=69° pinned at 18.34′ — see parser-bug callout below), `TestElongation`, `TestOscillationZerosTreatedAsPositive`. Final tally: **57 metric tests** (up from ~22 in v0.24.0).
- [x] PA-error coverage: 9 cases — celestial equator, mid-declination, negative declination, missing declination / pixel scale / drift, near-pole guard, **regression anchor at δ=69° pinned at 18.34′** (locks in the discrepancy with broken parser).
- [x] Dec-drift coverage: 5 cases — pure unguided collapses to least-squares slope, all-guided returns 0 (matches `LFit::B()`), alternating guided/unguided uses only the unguided deltas, single-sample undefined, all-zero stays at 0.
- [x] Elongation coverage: 6 cases — circular dispersion → 0, axis-aligned line → 1, zero dispersion → 1.0 defensive, single-sample → null, one-axis-null skipped, settle-window respected.

### Verification

- [x] Targeted: `uv run pytest tests/services/test_phd2_metrics.py tests/services/test_phd2_parser.py tests/test_phd2_api.py -n auto` → all pass.
- [x] Full backend suite (`uv run pytest -n auto`) green at finalize-session.
- [x] Manual cross-tool check on ASIAir sample log: NightCrate RMS RA / RMS Dec match 's. PA error row renders for δ=69° guiding section with the 18.34′ value (6.5′ is wrong on this log — see below).

### Beyond-plan UI work shipped on this branch

The original v0.25.0 plan was backend-only. UI iteration during the
session added:

- [x] **`SectionInfoPanel`** (new component) — collapsible "Session info" panel under the Section list in the left nav. Surfaces parsed `SectionHeader` fields grouped into Optics / Camera / Mount / Sky position / Star + lock / Algorithms / Dither / Profile / Other (freeform passthrough). Group titles render in `primary.main` with bold + uppercase + letter spacing for emphasis.
- [x] **Section + Viewport summaries moved into the left nav** below the Session info panel. Both default-collapsed; selection-aware via the existing `viewportMetrics` / `sectionMetrics` recompute. Right pane simplified to chart + scatter + events only.
- [x] **Tab restructure** — "Graph" renamed to "Guiding"; new **Dispersion** tab between Guiding and Data hosting the `ScatterPlot`. Data tab moved to index 2.
- [x] **Vertical scale sliders flank the chart** — replaced the four dropdowns / toggles (Guide axis, Pulse axis, SNR scale, Mass scale) with vertical MUI sliders on a 40 px rail each side of the SVG. Logarithmic mapping; UP = zoom in convention; per-slider reset button at the panel bottom; value-label tooltip flips to whichever side faces the chart so it never clips the left nav. Slider track aligns exactly with each panel's top / bottom horizontal axis line via `py: 0` override of MUI's default thumb padding.
- [x] **Toolbar reorg** — Guide unit (`px / ″`) toggle moved to the top of the legend row; "Include settle frames in stats" moved into the action-button row beside Reset X zoom; selection-action buttons (Include in view / Exclude in view / Clear all) split onto their own row with tooltips. `toolbarHeight` is measured via `ResizeObserver` so the slider rails track the actual rendered toolbar height rather than a stale constant.
- [x] **Panel-divider hairlines** at the midpoint of each gap between Guide / SNR / Mass. Default chart height bumped 440 → 650 px so SNR + Mass now render at the **same absolute height** (~110 px each).
- [x] **SNR / Mass median-anchored zoom** — axis lo locked at `autoLo` so the data minimum is always visible at the bottom; axis hi controlled by the slider. Slider min clamps above the median (`median + max(floor, 0.2 × (autoHi − median))`) so the bulk can never get pushed off the top. Y-axis is computed from full-section samples (not visible window) so X-zoom doesn't jiggle the SNR / Mass scale.
- [x] **Path field UX** — replaced plain TextField with `Autocomplete freeSolo` populated from `recentFiles`; dropdown shows filename / full path / relative time with a × per entry. Empty-state body copy rewritten. Field width capped (`flexBasis: 50%, maxWidth: 720, minWidth: 240`) so wide windows don't stretch it pointlessly.
- [x] **Slider tooltip auto-dismiss** — `onChangeCommitted` blurs the focused element so the value label disappears the moment the user releases the slider (was sticking visible while the thumb retained focus).

### parser-bug callout (worth flagging downstream)

`logparser.cpp` only reads declination from a line
that starts with `"RA = "` followed by `" hr, Dec = "`. Modern PHD2
logs (specifically ASIAir-bundled) emit a standalone `"Dec = N deg"`
line that parser doesn't match — `session.declination`
stays at the constructor default 0.0, so `cos(δ) = 1` and the PA-error
formula effectively drops the cos correction. reported
`6.5′` for the ASIAir sample log is wrong; NightCrate's `18.34′` at
δ=69° is the mathematically correct value. The new
`test_pa_pinned_at_high_declination_69` regression anchor pins the
correct number so a future refactor can't quietly drift back to the
no-cos form.

When v0.31.0 ships the diagnostic engine, the
`polar_alignment_from_dec_drift` rule should NOT be expected to match
reported number on ASIAir-bundled logs.

### Out of scope

- Spectrum tab work → v0.26.0
- Unguided RA → v0.27.0
- Strain wave markers → v0.28.0
- Per-instance schema → v0.29.0

---

## v0.26.0 — PHD2 Pass D-2 (Spectrum Conformance + Worm Markers)

**Status:** Done
**Branch:** `v0.26.0/phd2-spectrum-conformance`
**Spec ref:** `docs/nightcrate-phd2-analyzer-spec-v4.md` §6.1 (full FFT pipeline), §6.6 (worm markers)

**Note:** The Spectrum tab, FFT pipeline, worm markers, and rig picker shipped in this version were subsequently removed in v0.27.0.

### Goal

Implement the Spectrum tab strictly per spec v4 §6.1, with worm-period markers per §6.6. After this version, NightCrate's spectrum view matches spectrum view's reported values for the same log: same Hamming window, same `4/N` normalization, same Akima interpolation, same MAD-3 threshold, same snap-to-peak hover, same Period/Amplitude/P-P/RMS readouts.

### Why it stands on its own

The Spectrum tab is a self-contained view. Worm markers add diagnostic value when a rig is selected, fall back to a heuristic otherwise. Users with worm-mount rigs immediately benefit. Strain-wave-mount users see the heuristic fallback; better support ships in v0.28.0.

### Scope

#### §6.1 — Full FFT pipeline (verified port)

Pre-FFT pipeline (12 steps):

1. **Filter** to `included == true ∧ StarWasFound(err) ∧ ¬in_settle ∧ ¬user_excluded`. Selection-aware: FFT recomputes on shift-drag selection / shift+alt-drag exclusion changes.
2. **Minimum 12 entries** (`MIN_ENTRIES` per `AnalysisWin.cpp` line ~258). Skip + warn if fewer.
3. **Cadence check.** `IQR(dt) / median(dt) > 0.20` → skip + warn ("frequency analysis disabled — sample cadence varies > 20%"). IQR-over-median is robust against DROP-frame gaps.
4. **Drift subtraction** via least-squares linear fit. Drift slope `b` is preserved separately; FFT input is `x_i − (a + b·t_i)`.
5. **Akima spline interpolation** to uniform cadence via `scipy.interpolate.Akima1DInterpolator`. Adds scipy as a backend dependency.
6. **Hamming window** (NOT Hann). `w_i = 0.54 − 0.46 · cos(2π·i / (N − 1))`. NumPy: `np.hamming(n_uniform)`.
7. **FFT** via `numpy.fft.rfft` on the windowed series.
8. **Bin → period** mapping. `f_k = k / (N · Δt)`, `p_k = N · Δt / k`. Skip DC (k=0) and the symmetric upper half. keeps `nfft = N/2 − 1` bins.
9. **Amplitude normalization** `4/N` (per `AnalysisWin.cpp` line ~395 `double scale = 4. / (double) n;`). Then `amp_arcsec = amp_pixels × pixel_scale`.
10. **Display Y axis: log scale.** Lower bound: `max(amp_max / 10000, 0.001 arcsec)`. Upper: `amp_max × 1.1`.
11. **Display X axis: log scale, period in seconds.** Range: 5 s to roughly half the section duration.
12. **Seeing-band shading** at < 5 s with "atmospheric seeing" label.

Peak detection (§6.1.6):

- Threshold: `median(amp) + 3 × 1.4826 × MAD(amp)`. The 1.4826 factor scales MAD to be sigma-equivalent for normal data.
- Find local maxima above threshold.
- Deduplicate within ±5 % period (keep higher amplitude).
- Cap at top 5 by amplitude across all visible traces (NOT per-trace).
- Display: dot markers only, **no on-chart text labels**.

Hover tooltip (§6.1.7):

- Snap-to-peak within ±8 pixels of cursor (matches `OnMove` handler at `AnalysisWin.cpp` lines ~860-890).
- Tooltip readouts (per `AnalysisWin.cpp` line ~895):
  - **Period**: formatted naturally — "23.4 s", "1m 17s", "11m 28s"
  - **Amplitude**: `a` arcsec
  - **Peak-to-peak**: `2 · a` arcsec
  - **RMS**: `(√2 / 2) · a` ≈ `0.7071 · a` arcsec
- All four readouts visible; per-visible-trace.

#### §6.6 — Worm-period markers

Per-rig worm period via `mount.worm_period_seconds`. Re-add migration if v0.25.0 didn't carry it forward.

When `mount.drive_type == 'worm'` AND `worm_period_seconds` is set:
- Vertical dashed line at the worm period.
- If a detected peak falls within ±5% of the worm period: callout chip "Worm-period peak: 0.42″ amp @ 479 s (mount: <name>)".

Heuristic fallback (no rig OR no worm period known):
- Largest peak in [300, 800] s with amplitude > **0.5 arcsec** (NOT 2.0 — v3.1 corrected this).
- Labeled "likely worm-period peak (uncertain without mount identification)".

Worm-period seed values per spec v4 §6.6 table.

### Math derivations

#### §M1 — Hamming amplitude normalization 4/N

For a discrete sinusoid `x_i = A · cos(2π · k₀ · i / N)` windowed by Hamming `w_i = 0.54 − 0.46 · cos(2π·i / (N−1))`:

Hamming coherent gain `G_c = mean(w_i) ≈ 0.54`. Windowed FFT magnitude at the tone's bin: `|X_{k_0}| ≈ A · N · G_c / 2`. Solving for A: `A ≈ 2 · |X| / (N · G_c) ≈ 3.7 · |X| / N`.

rounds to **4** for compatibility: `a_arcsec = 4 · |X_k| / N · pixel_scale`. Over-estimates true peak amplitude by ~8% but **NightCrate must match value** so cross-tool comparisons line up.

#### §M2 — MAD-based peak threshold

`MAD(x) = median(|x_i − median(x)|)`. For normal data, `σ ≈ 1.4826 · MAD`. 3-sigma-equivalent threshold: `median(a) + 3 · 1.4826 · MAD(a)`. Robust against outliers; produces zero false peaks on a flat noise spectrum.

### Files to modify

**Backend:**

- [x] `backend/src/nightcrate/services/phd2_fft.py` — pure service implementing the §6.1 pipeline. `compute_section_fft(samples, *, pixel_scale, trace="ra")`. Uses `scipy.interpolate.Akima1DInterpolator`, `np.hamming`, `4/N`, MAD with 1.4826 factor. Three skip reasons: `too_short` / `non_uniform_cadence` / `constant_data`.
- [x] `backend/src/nightcrate/api/phd2_models.py` — `FftPeak`, `FftResult`, `WormMarker`, `SectionAnalysis` Pydantic models. `WormMarker.source: Literal["mount", "heuristic"]`. `SectionWithMetrics.analysis: SectionAnalysis = SectionAnalysis()`. `ParseRequest.rig_id: int | None = None`.
- [x] `backend/src/nightcrate/api/phd2.py` — `_RigInfo` (rig_id + mount drive_type + worm_period), `_load_rig_info` reads from `rig_summary` view, `_build_section_analysis` runs FFT for RA + Dec and builds the worm marker, `_build_worm_marker` (mount-with-worm-period / heuristic / none branches), `_is_worm_drive` (case-insensitive substring on free-form drive_type), `_match_peak` (highest amp within ±5%), `_heuristic_worm_peak` (largest in [300, 800] s above 0.5″). Cache key extended with `rig_id`.
- [x] `backend/src/nightcrate/db/migrations/0024.mount_worm_period.sql` — adds `mount.worm_period_seconds REAL` and rebuilds `rig_summary` to expose `mount_drive_type` and `mount_worm_period_seconds`.
- [x] `backend/src/nightcrate/data/seed/mount.csv` — `worm_period_seconds` column populated for worm mounts (EQ6-R Pro 479, AVX 480, GEM28/CEM70 600, CEM26 287, etc.). Strain-wave + direct-drive rows blank.
- [x] `backend/src/nightcrate/seed_loader/registry.py` — `worm_period_seconds` added to mount's `seeded_fields`.

**Backend new dep:**

- [x] `scipy>=1.11` added to `backend/pyproject.toml` (BSD-3-Clause).

**Frontend:**

- [x] `frontend/src/components/phd2/FftChart.tsx` — D3 SVG chart. Log-log axes, top-5 peak dots, always-on hover hairline + tooltip (snap-to-peak within ±8 px on horizontal distance, full Period/Amplitude/P-P/RMS readout when snapped, nearest-bin per-trace amplitudes when free), worm-marker overlay, seeing-band shading, X-axis tick rotation -30°, clipPath so log-scale values below the Y floor stay inside the panel.
- [x] `frontend/src/components/phd2/RigSelectBar.tsx` — MUI Select-based rig picker with first-class "No rig" option.
- [x] `frontend/src/lib/phd2RecentFiles.ts` — `RecentFile.selectedRigId?: number | null` + `setRecentFileRig` helper for per-log rig persistence.
- [x] `frontend/src/api/phd2.ts` — `FftPeak`, `FftResult`, `WormMarker`, `SectionAnalysis` interfaces; `parseGuideLog(path, rigId?)`.
- [x] `frontend/src/pages/Phd2AnalyzerPage.tsx` — Spectrum tab inserted at index 1 (Data shifted to 3); `RigSelectBar` in toolbar; `parseMutation.mutate({ path, rigId })`.

### Tests (39 new)

- [x] 19 FFT service tests (`tests/services/test_phd2_fft.py`) — scipy import sanity, all guard branches (too-short, non-uniform cadence, constant data), single-tone amplitude recovery within Hamming 8% bias band, two-tone separation, peak top-5 cap, ±5% dedup, MAD-3 noise-floor zero-peak, pixel-scale propagation.
- [x] 20 new API tests (`tests/test_phd2_api.py`) — `TestFftAttachment` (FFT result shape on parse responses, attaches to both RA and Dec sections, rig persistence across cache hits), `TestRigContext` (404 on bad rig_id, cache key separates rig variants), `TestWormMarkerHelpers` (`_is_worm_drive` substring matching, `_match_peak` ±5% window, `_heuristic_worm_peak` [300,800] s gate at 0.5″, `_build_worm_marker` mount-match / mount-no-peak / harmonic-falls-through / fft-skipped / no-rig branches).

### Verification

- [x] Backend pytest passes (52 PHD2 tests including the 39 new).
- [x] Frontend build passes (`tsc --noEmit` + vite build).
- [x] Manual: opened ASIAir sample log → Spectrum tab → hairline + snap-to-peak hover work end-to-end, peak amplitudes within Hamming 8% of reported values. Both Fred's mounts (WD-20 + AM5) are Harmonic so the rig-specific marker doesn't fire on his data; the heuristic fallback runs as expected.

---

## v0.27.0 — PHD2 Analyzer Polish + Cleanup

**Status:** Complete
**Branch:** `v0.27.0/phd2-unguided-ra`

### What happened

v0.26.0 shipped a Spectrum tab (FFT pipeline, worm markers, rig picker) and v0.27.0 initially added unguided RA reconstruction. Both proved unreliable and were **fully removed** in this version. The advanced analysis features (FFT, spectrum, unguided RA, worm markers, rig picker) are all gone. All references to the GPL-licensed PHDLogViewer were also scrubbed from the codebase.

### What v0.27.0 delivers

- Removed Spectrum tab, FftChart, RigSelectBar, phd2_fft.py, phd2_unguided.py, and all associated tests
- Removed all PHDLogViewer references from the codebase
- Removed unguided RA overlay and FFT unguided trace from TimeSeriesChart
- Removed TabHelpPanel component; replaced with per-tab info icon + popover
- Dispersion ellipses: switched from RIG_ORANGE to bright teal (#4db6ac) for colorblind visibility
- Added Section Info as first tab (equipment/sky/algorithm metadata in 3-column grid layout)
- Dispersion tab: added px/arcsec toggle, fixed axis extent math (centroid offset), axis labels now show single unit
- Section navigator: shows date + time, removed RMS from summary line
- Left nav: sections pinned at top, stats scroll independently below divider; stats hidden for calibration sections
- Dispersion tab hidden for calibration sections
- Calibration plot legend items now clickable to toggle phase visibility
- Stats panel: fixed 7-row layout (Duration/Frames, PA error/Elongation, RMS Total/RA/Dec, Peak RA/Dec, Drift RA/Dec, Osc RA/Dec, Mean SNR/Star mass)
- Toolbar: removed "Include in view" / "Exclude in view" buttons; kept "Clear all selections"; moved "Reset X zoom" before it
- D3 zoom constrained to chart interior (axes/labels excluded)
- Default app nav order reordered by workflow
- Updated main.py PHD2 feature description

---

## v0.28.0 — Plate Solving (ASTAP Integration)

**Status:** Done
**Branch:** `v0.28.0/plate-solving`

### What it does

Integrates ASTAP as an external plate solver invoked via subprocess. Users configure the ASTAP executable path in Settings (with macOS `.app` bundle auto-resolution), then plate solve any image from the Image Viewer toolbar. Results (RA, Dec, pixel scale, rotation, FOV) display in a dialog. No database persistence — one-shot tool.

### Delivered

- [x] `astap_executable_path` setting (no migration — KV pattern)
- [x] Settings page: Plate Solving accordion with Browse + live validation
- [x] File browser `accept=*` mode for selecting executables (extensionless Unix binaries)
- [x] macOS `.app` bundle resolution (navigates `Contents/MacOS/` to find the binary)
- [x] `services/plate_solve.py` — ASTAP subprocess invocation, `.ini` output parsing, result computation
- [x] `services/plate_solve_models.py` — `PlateSolveRequest` / `PlateSolveResult` Pydantic models
- [x] `api/plate_solve.py` — `POST /solve`, `POST /validate-path` endpoints
- [x] Temp file pipeline: archive and pxiproject images extracted to temp FITS for ASTAP
- [x] XISF images converted to temp FITS (ASTAP only supports uncompressed XISF)
- [x] Auto/Near/Blind solve modes — auto-detects from FITS header RA/Dec hints
- [x] `services/coordinate_format.py` — added `format_ra_hms()`, `format_dec_dms()`
- [x] Image Viewer: Plate Solve button in toolbar + `PlateSolveDialog` component
- [x] Dialog: mode selector, header hint display, results table, copy-to-clipboard, solve timer
- [x] Concurrency guard (`asyncio.Semaphore(1)`) — one solve at a time
- [x] ASTAP exit code mapping to user-friendly error messages
- [x] 35 backend tests (service unit + API integration)

### Not in scope

- No WCS overlay or annotation on images (future version)
- No database persistence of solve results
- No star database path setting (ASTAP finds its own)
- No astrometry.net support (ASTAP only)

---

## FITS Equipment Resolver Spec

This spec defines the **equipment resolver**: the component that takes values from FITS headers (`INSTRUME`, `TELESCOP`, `FILTER`, etc.) and resolves them to rows in the equipment database (`camera`, `telescope`, `filter`). It's the bridge between messy real-world header strings and the clean normalized equipment schema.

Target: Python 3.12+, SQLite. Assumes the schema from `nightcrate-schema-revision-spec.md` is in place (specifically: `camera_alias`, `telescope_alias`, `filter_alias` tables exist).

**Out of scope for this change:** the FITS file reader itself (astropy handles that), the full sub frame ingest pipeline, UI for reviewing unresolved aliases, any automatic fuzzy matching beyond the specific rules in §5.

---

### Table of contents

1. Goals and non-goals
2. Terminology
3. High-level design
4. Normalization rules
5. Resolution algorithm
6. Line-name canonicalization (for `FILTER` headers)
7. The two-camera-same-model problem
8. Public API
9. Unresolved alias handling
10. Logging and diagnostics
11. Deliverables

---

### 1. Goals and non-goals

#### Goals

- Given a FITS header value for a camera, telescope, or filter, return the corresponding equipment row — or `None` if no confident match exists.
- Record new alias observations automatically so the first encounter bootstraps the alias table.
- Treat any alias promotion to `confirmed=1` as a user-only action (the resolver never auto-confirms).
- Provide a clear "needs review" list for the UI (out of scope for this change) to act on later.
- Be fast: resolution should be O(1) for aliases already in the table.

#### Non-goals

- No fuzzy string matching, Levenshtein, embeddings, or ML. The resolver is deterministic: exact match against the normalized alias table, nothing else. If that fails, the caller handles the unresolved case.
- No UI for confirming aliases. The resolver returns structured results; the UI is separate.
- No FITS file reading. This component receives already-parsed header values as strings.
- No handling of date ranges, equipment retirement timelines, or "which camera was this two years ago." The resolver operates on the current state of the equipment DB.
- No automatic promotion of unconfirmed aliases. `confirmed=0` stays `confirmed=0` until a human decides otherwise.

---

### 2. Terminology

- **Header value** — the raw string from a FITS header, e.g. `"ZWO ASI2600MM Pro"`.
- **Alias** — the normalized form of a header value, stored in the alias tables, e.g. `"zwo asi2600mm pro"`.
- **Resolution** — the act of mapping a header value to an equipment row via the alias tables.
- **Confirmed alias** — `confirmed=1`; the user has explicitly told the app "this header value means this equipment row." Authoritative.
- **Unconfirmed alias** — `confirmed=0`; the resolver observed this header value and either seeded it or the system auto-inserted it pending user review.
- **Unresolved** — the normalized alias is not in the alias table at all. The caller must decide what to do (typically: surface it to the user for mapping).

---

### 3. High-level design

The resolver is a single module, `nightcrate.equipment_resolver`, with a class:

```python
class EquipmentResolver:
    def __init__(self, conn: sqlite3.Connection): ...

    def resolve_camera(self, header_value: str, source: AliasSource) -> ResolveResult[Camera]: ...
    def resolve_telescope(self, header_value: str, source: AliasSource) -> ResolveResult[Telescope]: ...
    def resolve_filter(self, header_value: str, source: AliasSource) -> ResolveResult[Filter]: ...
```

Each resolve method:

1. Normalizes the header value (§4).
2. Looks it up in the corresponding alias table.
3. If found and the equipment row is active, returns a `ResolveResult` containing the resolved row.
4. If found but the equipment row is `active=0`, still returns it but flags it with a warning.
5. If not found, inserts a new unconfirmed alias row with the given `source`, returns an `Unresolved` result, and the caller decides what to do.
6. Updates `last_seen_at` on the alias row whether or not it's newly inserted.

The resolver is **stateless** beyond the DB connection. Safe to instantiate per-ingest-run.

#### ResolveResult shape

```python
@dataclass
class ResolveResult(Generic[T]):
    status: Literal['resolved', 'resolved_retired', 'unresolved', 'ambiguous']
    equipment: T | None
    alias_row_id: int | None
    normalized_alias: str
    was_newly_observed: bool
    message: str | None = None
```

`status` values:

- **`resolved`** — matched an alias pointing to an active equipment row. Happy path.
- **`resolved_retired`** — matched an alias pointing to an `active=0` equipment row. Still returns the row (the header is probably from an old session before retirement), but the caller should display a warning in the UI.
- **`unresolved`** — normalized alias not in the table. A new unconfirmed alias row was inserted. Caller should queue for review.
- **`ambiguous`** — reserved for the two-camera-same-model problem (§7). Not emitted in the base implementation; placeholder for a future extension.

---

### 4. Normalization rules

Normalization must be deterministic and reversible enough that the same header value always produces the same normalized form. Apply these steps in order:

1. **Unicode normalize** to NFKC. Handles stray compatibility characters.
2. **Strip leading and trailing whitespace.**
3. **Collapse internal whitespace runs** to a single space. `"ZWO   ASI2600MM   Pro"` → `"ZWO ASI2600MM Pro"`.
4. **Remove zero-width and control characters.** Some capture software emits weird invisible bytes.
5. **Lowercase.** `"ZWO ASI2600MM Pro"` → `"zwo asi2600mm pro"`.
6. **Do NOT** remove punctuation, hyphens, slashes, or parentheses. `"7nm Ha"` and `"7 nm Ha"` are different aliases as far as the resolver is concerned; if a user wants them to resolve to the same filter, they add both as aliases.

**What normalization does not do:**

- No stemming, no tokenization, no reordering of words.
- No "smart" handling of brand prefixes (`"ZWO ASI2600MM Pro"` vs `"ASI2600MM Pro"` are different aliases until a human says otherwise).
- No removal of version numbers, firmware strings, or trailing whitespace variants beyond the steps above.

The rule of thumb: **normalization handles pure string-formatting differences. Everything else is the user's call.**

#### Implementation

```python
import re
import unicodedata

_WHITESPACE_RUN = re.compile(r'\s+')
_INVISIBLE = re.compile(r'[\u0000-\u001f\u007f-\u009f\u200b-\u200f\ufeff]')

def normalize_alias(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"alias must be str, got {type(value).__name__}")
    v = unicodedata.normalize('NFKC', value)
    v = _INVISIBLE.sub('', v)
    v = v.strip()
    v = _WHITESPACE_RUN.sub(' ', v)
    v = v.lower()
    return v
```

The resolver stores normalized aliases in the alias tables — never the raw header value. If you want to preserve the raw form for display (e.g., show the user "we saw `ZWO ASI2600MM Pro` in your header"), add an `original_observation TEXT` column to the alias tables in a follow-up schema change. Not doing that in this change; normalization is lossy and we accept that.

---

### 5. Resolution algorithm

For each equipment type, the algorithm is the same shape. Here it is for cameras; telescopes and filters are structurally identical, swapping table and FK names.

```python
def resolve_camera(
    self,
    header_value: str,
    source: AliasSource,
) -> ResolveResult[Camera]:
    if not header_value or not header_value.strip():
        return ResolveResult(
            status='unresolved',
            equipment=None,
            alias_row_id=None,
            normalized_alias='',
            was_newly_observed=False,
            message='empty header value',
        )

    normalized = normalize_alias(header_value)

    # Look up existing alias
    row = self.conn.execute("""
        SELECT ca.id AS alias_id, ca.confirmed, c.id AS camera_id, c.active
        FROM camera_alias ca
        JOIN camera c ON c.id = ca.camera_id
        WHERE ca.alias = ?
    """, (normalized,)).fetchone()

    if row is not None:
        # Update last_seen_at
        self.conn.execute(
            "UPDATE camera_alias SET last_seen_at = datetime('now') WHERE id = ?",
            (row['alias_id'],),
        )
        camera = self._load_camera(row['camera_id'])
        if row['active'] == 0:
            return ResolveResult(
                status='resolved_retired',
                equipment=camera,
                alias_row_id=row['alias_id'],
                normalized_alias=normalized,
                was_newly_observed=False,
                message='camera is retired (active=0)',
            )
        return ResolveResult(
            status='resolved',
            equipment=camera,
            alias_row_id=row['alias_id'],
            normalized_alias=normalized,
            was_newly_observed=False,
        )

    # Alias not in table — record the observation as unconfirmed.
    # We insert with camera_id = NULL? NO — the schema requires camera_id NOT NULL.
    # So we can't auto-insert an unresolved alias. See below.
    return ResolveResult(
        status='unresolved',
        equipment=None,
        alias_row_id=None,
        normalized_alias=normalized,
        was_newly_observed=False,
    )
```

#### The "unresolved observation" problem

The schema from the revision spec has `camera_alias.camera_id INTEGER NOT NULL`. That means you **cannot** insert an alias row without already knowing which camera it maps to. This is intentional — it prevents orphaned alias rows.

But it creates a gap: when the resolver sees a brand-new header value, it has nowhere to record the observation. The caller has to handle this via a separate "unresolved observations" table:

```sql
-- Add in a follow-up migration (NOT part of the schema revision spec — new here):
CREATE TABLE unresolved_equipment_observation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_kind TEXT NOT NULL CHECK (equipment_kind IN ('camera', 'telescope', 'filter')),
    normalized_alias TEXT NOT NULL,
    original_observation TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    seen_count INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL CHECK (source IN ('nina', 'asiair', 'user', 'manual')),
    resolved_to_equipment_id INTEGER,
    resolved_at TEXT,
    UNIQUE (equipment_kind, normalized_alias)
);

CREATE INDEX idx_unresolved_equipment_observation_kind
    ON unresolved_equipment_observation(equipment_kind, resolved_at);
```

When the resolver returns `status='unresolved'`, it also inserts (or updates via `ON CONFLICT`) a row in `unresolved_equipment_observation`. The UI will later query this table to present a "needs review" screen where the user picks the correct equipment row. When the user confirms, the app:

1. Inserts a row into the appropriate alias table with `confirmed=1` and `source='user'`.
2. Sets `resolved_to_equipment_id` and `resolved_at` on the unresolved observation row (keeping it for history, not deleting it).

**This schema addition is part of this spec's deliverables** (it's a small migration). The resolver code depends on the table existing.

#### Updated resolve_camera ending

```python
    # Alias not in table — record as unresolved observation
    self.conn.execute("""
        INSERT INTO unresolved_equipment_observation
            (equipment_kind, normalized_alias, original_observation, source)
        VALUES ('camera', ?, ?, ?)
        ON CONFLICT (equipment_kind, normalized_alias) DO UPDATE SET
            last_seen_at = datetime('now'),
            seen_count = seen_count + 1
    """, (normalized, header_value, source))

    return ResolveResult(
        status='unresolved',
        equipment=None,
        alias_row_id=None,
        normalized_alias=normalized,
        was_newly_observed=True,
    )
```

---

### 6. Line-name canonicalization (for `FILTER` headers)

The `FILTER` header is special. Users see it as both a physical filter reference *and* as a line-name reference. N.I.N.A. commonly writes `FILTER = "Ha"` or `FILTER = "Lum"` — which is **not** the model name of any filter the user owns; it's the slot label in the filter wheel config.

This means `resolve_filter` has to do two things:

1. **Canonicalize the line name** — normalize `"H-alpha"`, `"Hydrogen Alpha"`, `"H-a"`, `"Ha"`, etc. to the canonical `line_name` vocabulary from the schema (`'Ha'`, `'Hb'`, `'Oiii'`, `'Sii'`, etc.).
2. **Resolve to a physical filter** — match the canonicalized line name against the user's filter_passband rows, scoped to the current rig or session context (because the same `"Ha"` header maps to Fred's 7nm Optolong or 3nm Antlia depending on which rig captured the sub).

#### Line name canonicalization table

This is a hard-coded table in the resolver module, not in the database. Closed vocabulary, grows only via code change:

```python
LINE_NAME_CANONICAL: dict[str, str] = {
    # Ha and variants
    'ha': 'Ha',
    'h-a': 'Ha',
    'h alpha': 'Ha',
    'h-alpha': 'Ha',
    'halpha': 'Ha',
    'hydrogen alpha': 'Ha',
    'hydrogen-alpha': 'Ha',
    # Hb
    'hb': 'Hb',
    'h-b': 'Hb',
    'h beta': 'Hb',
    'h-beta': 'Hb',
    'hbeta': 'Hb',
    'hydrogen beta': 'Hb',
    # Oiii
    'oiii': 'Oiii',
    'o3': 'Oiii',
    'o-iii': 'Oiii',
    'o iii': 'Oiii',
    'oxygen iii': 'Oiii',
    'oxygen-iii': 'Oiii',
    'oxygeniii': 'Oiii',
    # Sii
    'sii': 'Sii',
    's2': 'Sii',
    's-ii': 'Sii',
    's ii': 'Sii',
    'sulfur ii': 'Sii',
    'sulphur ii': 'Sii',
    'sulfur-ii': 'Sii',
    # Broadband
    'l': 'Lum',
    'lum': 'Lum',
    'luminance': 'Lum',
    'clear': 'Lum',
    'r': 'R',
    'red': 'R',
    'g': 'G',
    'green': 'G',
    'b': 'B',
    'blue': 'B',
    # Utility
    'uvir': 'UVIR',
    'uv/ir': 'UVIR',
    'uv-ir': 'UVIR',
    'uv ir cut': 'UVIR',
}

def canonicalize_line_name(value: str) -> str | None:
    normalized = normalize_alias(value)
    return LINE_NAME_CANONICAL.get(normalized)
```

If `canonicalize_line_name` returns `None`, the header value is not a recognized line name — it might be a physical filter model name instead (`"Optolong L-Pro"`), in which case the regular alias lookup applies.

#### Filter resolution, full algorithm

```python
def resolve_filter(
    self,
    header_value: str,
    source: AliasSource,
    rig_context: RigContext | None = None,
) -> ResolveResult[Filter]:
    normalized = normalize_alias(header_value)

    # 1. Try exact alias lookup first (handles "Optolong L-Pro" style headers)
    row = self.conn.execute("""
        SELECT fa.id AS alias_id, fa.confirmed, f.id AS filter_id, f.active
        FROM filter_alias fa
        JOIN filter f ON f.id = fa.filter_id
        WHERE fa.alias = ?
    """, (normalized,)).fetchone()
    if row:
        # ... same handling as resolve_camera ...
        return ResolveResult(...)

    # 2. Try line name canonicalization (handles "Ha", "H-alpha" style headers)
    canonical_line = canonicalize_line_name(header_value)
    if canonical_line is not None and rig_context is not None:
        # Scope filter lookup to the rig's filter wheel
        candidate_filters = self.conn.execute("""
            SELECT DISTINCT f.id, f.active
            FROM filter f
            JOIN filter_passband fp ON fp.filter_id = f.id
            JOIN filter_wheel_filter fwf ON fwf.filter_id = f.id
            WHERE fp.line_name = ?
              AND fwf.filter_wheel_id = ?
        """, (canonical_line, rig_context.filter_wheel_id)).fetchall()

        if len(candidate_filters) == 1:
            filter_row = self._load_filter(candidate_filters[0]['id'])
            return ResolveResult(
                status='resolved',
                equipment=filter_row,
                alias_row_id=None,
                normalized_alias=normalized,
                was_newly_observed=False,
                message=f'resolved via line name canonicalization: {canonical_line}',
            )
        elif len(candidate_filters) > 1:
            return ResolveResult(
                status='ambiguous',
                equipment=None,
                alias_row_id=None,
                normalized_alias=normalized,
                was_newly_observed=False,
                message=f'multiple filters match line {canonical_line} in this rig',
            )
        # len == 0 falls through to unresolved

    # 3. Unresolved — record observation
    self.conn.execute("""
        INSERT INTO unresolved_equipment_observation
            (equipment_kind, normalized_alias, original_observation, source)
        VALUES ('filter', ?, ?, ?)
        ON CONFLICT (equipment_kind, normalized_alias) DO UPDATE SET
            last_seen_at = datetime('now'),
            seen_count = seen_count + 1
    """, (normalized, header_value, source))
    return ResolveResult(status='unresolved', ...)
```

#### `RigContext` and `filter_wheel_filter`

`RigContext` is a simple dataclass carrying the rig identity resolved earlier in the same ingest pipeline (typically via camera + telescope resolution). It has `rig_id`, `filter_wheel_id`, and optionally `session_id`.

`filter_wheel_filter` is a junction table that **does not yet exist** in the schema revision spec. It belongs to the rig/session layer that will be built later. For this spec, **mark the rig_context path as a forward-compatible stub:** the resolver accepts the `rig_context` parameter and its signature is ready, but if the schema doesn't have `filter_wheel_filter` yet, the code catches the missing-table error at query time and falls through to unresolved, logging a warning. Document this clearly.

Once the rig/session schema lands, the line-name-to-filter resolution starts working automatically.

---

### 7. The two-camera-same-model problem

Fred owns two physically distinct ASI 2600MM Pro cameras. Both produce `INSTRUME = "ZWO ASI2600MM Pro"` in their FITS headers. The `UNIQUE(alias)` constraint on `camera_alias` means the string `"zwo asi2600mm pro"` can map to exactly one camera row in the DB.

This is a known limitation and **is not solved by this spec**. The resolver returns whichever camera the alias points to. Disambiguation happens at the rig level via other context: which mount, which telescope, which filter wheel, which computer hostname captured the frame. That's a job for the ingest pipeline, not the alias resolver.

**For this spec**, document the limitation and flag it in the module docstring. When the rig-aware ingest code lands, it will do disambiguation by:

1. Resolving the obvious equipment from FITS headers.
2. Matching the resolved equipment against known rig configurations.
3. If exactly one rig matches, using that rig's specific camera instance.
4. If multiple rigs match, flagging the sub frame for manual rig assignment.

The alias tables will need a schema change later to support this (likely: replace `UNIQUE(alias)` with `UNIQUE(alias, rig_hint)` or similar). Do not implement that now.

---

### 8. Public API

```python
# nightcrate/equipment_resolver/__init__.py

from .resolver import EquipmentResolver, ResolveResult, RigContext
from .normalize import normalize_alias
from .line_names import canonicalize_line_name, LINE_NAME_CANONICAL

__all__ = [
    'EquipmentResolver',
    'ResolveResult',
    'RigContext',
    'normalize_alias',
    'canonicalize_line_name',
    'LINE_NAME_CANONICAL',
]

AliasSource = Literal['nina', 'asiair', 'user', 'manual']
```

#### Usage pattern

```python
import sqlite3
from nightcrate.equipment_resolver import EquipmentResolver

conn = sqlite3.connect('nightcrate.sqlite')
conn.row_factory = sqlite3.Row

resolver = EquipmentResolver(conn)

camera_result = resolver.resolve_camera('ZWO ASI2600MM Pro', source='nina')
if camera_result.status == 'resolved':
    print(f'Resolved to camera #{camera_result.equipment.id}: {camera_result.equipment.model_name}')
elif camera_result.status == 'unresolved':
    print(f'Unknown camera: {camera_result.normalized_alias} — flagged for review')

conn.commit()  # resolver writes to the DB (unresolved observations, last_seen_at updates)
```

The resolver writes to the DB during normal operation (updating `last_seen_at`, inserting unresolved observations). **The caller is responsible for committing** — the resolver never commits or rolls back on its own. This lets the caller wrap the entire ingest operation in a single transaction.

---

### 9. Unresolved alias handling

#### From the resolver's side

When a header value doesn't resolve:

1. Insert or update `unresolved_equipment_observation` via `ON CONFLICT`.
2. Return `ResolveResult(status='unresolved', ...)`.
3. Do **not** raise an exception. Unresolved is a normal outcome, not an error.

#### From the caller's side (documentation only — not implemented in this change)

The ingest pipeline should:

1. Continue processing the sub frame, recording whatever equipment *did* resolve.
2. Leave the unresolved equipment FK as NULL on the sub frame row, or store the unresolved observation ID for later resolution.
3. At the end of the ingest run, produce a count of how many unresolved observations were recorded.
4. The UI (later) surfaces the `unresolved_equipment_observation` table as a "map these to equipment" screen.

#### Promotion to confirmed aliases

When the user resolves an unresolved observation via UI (future):

```python
def confirm_unresolved_observation(
    conn: sqlite3.Connection,
    observation_id: int,
    equipment_id: int,
) -> None:
    """
    Map an unresolved observation to an equipment row.
    Creates a confirmed alias and marks the observation resolved.
    """
    obs = conn.execute(
        "SELECT equipment_kind, normalized_alias FROM unresolved_equipment_observation WHERE id = ?",
        (observation_id,),
    ).fetchone()

    table = f"{obs['equipment_kind']}_alias"
    fk = f"{obs['equipment_kind']}_id"

    conn.execute(
        f"INSERT INTO {table} ({fk}, alias, source, confirmed) VALUES (?, ?, 'user', 1)",
        (equipment_id, obs['normalized_alias']),
    )
    conn.execute(
        "UPDATE unresolved_equipment_observation "
        "SET resolved_to_equipment_id = ?, resolved_at = datetime('now') "
        "WHERE id = ?",
        (equipment_id, observation_id),
    )
```

Include this as a utility function in the resolver module for completeness, but **do not wire it to any UI** in this change.

---

### 10. Logging and diagnostics

The resolver uses Python's `logging` module with the logger name `nightcrate.equipment_resolver`. Log levels:

- **DEBUG** — every resolve call with input, normalized form, and result.
- **INFO** — first-time observations of a new unresolved alias.
- **WARNING** — resolved to a retired (`active=0`) equipment row; schema version mismatches; the `filter_wheel_filter` table being missing (forward-compat fallback).
- **ERROR** — unexpected DB errors, integrity violations, type errors on input.

Provide a `ResolverStats` accumulator that the caller can optionally pass in:

```python
@dataclass
class ResolverStats:
    resolved: int = 0
    resolved_retired: int = 0
    unresolved: int = 0
    ambiguous: int = 0
    newly_observed: int = 0
```

If passed to the `EquipmentResolver` constructor, it's updated in place on every resolve call. Useful for ingest summary reporting.

---

### 11. Deliverables

1. **Schema migration** adding `unresolved_equipment_observation` table (see §5). Include `CREATE TABLE` and the index. This is a small follow-up migration, not a modification of the main schema revision spec.

2. **`nightcrate/equipment_resolver/__init__.py`** — public API exports.

3. **`nightcrate/equipment_resolver/normalize.py`** — `normalize_alias` function with the rules from §4.

4. **`nightcrate/equipment_resolver/line_names.py`** — `LINE_NAME_CANONICAL` dict and `canonicalize_line_name` function.

5. **`nightcrate/equipment_resolver/resolver.py`** — `EquipmentResolver` class with `resolve_camera`, `resolve_telescope`, `resolve_filter` methods. `ResolveResult`, `RigContext`, `ResolverStats` dataclasses.

6. **`nightcrate/equipment_resolver/promotion.py`** — `confirm_unresolved_observation` utility.

7. **Tests** — pytest-based, using in-memory SQLite with the full schema:
   - `test_normalize.py` — normalization rules, NFKC, whitespace, invisibles, lowercase, non-removal of punctuation.
   - `test_line_names.py` — every entry in `LINE_NAME_CANONICAL`, plus `None` returns for unknown values.
   - `test_resolve_camera_happy_path.py` — seed a camera + alias, resolve header → expect `resolved` with correct camera.
   - `test_resolve_camera_retired.py` — camera with `active=0`, resolve → expect `resolved_retired`.
   - `test_resolve_camera_unresolved.py` — unknown header → expect `unresolved`, row created in `unresolved_equipment_observation`, `seen_count=1`. Second call increments `seen_count` and updates `last_seen_at`.
   - `test_resolve_telescope.py` — equivalent coverage.
   - `test_resolve_filter_via_alias.py` — filter resolved via exact alias match.
   - `test_resolve_filter_via_line_name.py` — filter resolved via line name canonicalization with a `RigContext` and a single matching filter in the rig.
   - `test_resolve_filter_ambiguous.py` — two filters in the same rig's wheel both match the line → `ambiguous`.
   - `test_resolve_filter_no_rig_context.py` — line name header without rig context → unresolved.
   - `test_resolve_filter_missing_fwf_table.py` — `filter_wheel_filter` table doesn't exist → warning logged, falls through to unresolved.
   - `test_promotion.py` — `confirm_unresolved_observation` creates the alias row and marks the observation resolved.
   - `test_resolver_stats.py` — ResolverStats accumulator correctly tracks counts.
   - `test_no_auto_commit.py` — verify the resolver never calls `conn.commit()` on its own.

8. **README section** covering:
   - The public API with a minimal example.
   - The normalization rules (so users understand why `"Ha"` and `"H-alpha"` work but `"7nm Ha"` and `"7 nm Ha"` don't).
   - The two-camera-same-model limitation (§7).
   - The forward-compatible stub for rig-scoped filter resolution (§6) and what will change once the rig/session schema lands.
   - The recommendation to wrap ingest operations in a single transaction and commit at the end.

---

### What NOT to build in this change

- FITS file reading — astropy handles that. The resolver takes strings.
- The sub frame ingest pipeline that calls the resolver.
- The "unresolved observations review" UI.
- Any fuzzy matching — the resolver is strictly exact-match after normalization.
- Rig disambiguation for the two-cameras-same-model case.
- The `filter_wheel_filter` table — that belongs to the rig/session schema, built later. The resolver handles its absence gracefully.
- Automatic promotion of unconfirmed aliases to confirmed. Only humans confirm aliases.
- Historical "which equipment was this two years ago" logic.

---
## Imaging Core Schema — Rigs, Projects, Sessions, Sub Frames

This spec defines the imaging-core schema layer: the tables that model *what you imaged*, *when you imaged it*, *what gear captured it*, and *what individual exposures resulted*. It sits on top of the equipment schema from `nightcrate-schema-revision-spec.md` and assumes the FITS equipment resolver from `nightcrate-fits-resolver-spec.md` exists (or is being built in parallel).

Target: SQLite. Stack: Python/FastAPI backend. Raw SQL migration, no ORM assumptions.

**Out of scope for this change:** the FITS file parser itself (astropy handles that), the ingest pipeline that drives this schema (separate spec), any UI, the AI analyzer feature (post-MVP — but the schema must enable it).

---

### Table of contents

1. Goals and design principles
2. Design decisions (what's in, what's deferred, why)
3. Targets and projects
4. Rigs and filter wheel contents
5. Sessions and session events
6. Sub frames (the core atom)
7. Calibration frame handling
8. PHD2 guiding data
9. Autofocus runs
10. File locations and content hashing
11. Ingestion provenance
12. Views and aggregates
13. AI context bundle (serialization contract)
14. Indices
15. Deliverables

---

### 1. Goals and design principles

#### Goals

- Model the full lifecycle of an imaging project: from the target being selected, through multi-night sessions on one or more rigs, down to the individual sub frames and associated telemetry.
- Handle the realities of Fred's dual-rig setup: two physical ASI 2600MM Pro cameras, a modular Askar V that changes focal length with different reducer configurations, filters whose name-per-rig mapping matters, and multi-night accumulation of integration time across projects.
- Support calibration frame matching (darks, flats, bias) via straightforward queries, not bespoke matching code.
- Associate PHD2 guiding data with sub frames by timestamp, with enough fidelity to support the guiding graph feature and per-sub RMS lookups.
- Be re-ingestable: running the ingest twice on the same data must be idempotent. No duplicate sub frames, no corrupted state.
- **Serialize cleanly into AI context windows.** See §13 — this is a hard design constraint, not an afterthought.

#### Design principles

- **Sub frames are the source of truth.** A sub frame records what actually captured it: which camera, which telescope + configuration, which filter, which gain, which temperature, at what time. Rigs and sessions are groupings for query convenience; they do not override what the FITS header says.
- **Content hash identity.** Every sub frame has a SHA-256 of its file contents. That's the stable identity. File paths move around; hashes don't. Re-ingest is an UPSERT keyed on content hash.
- **Timestamps are UTC ISO 8601 strings in the database** (SQLite `TEXT` with `datetime()` functions), with UTC as the only timezone stored. Display-time conversion to local is a UI concern.
- **Nullable equipment FKs on sub_frame.** If the resolver can only figure out some of the equipment from a header, the sub frame still ingests with partial equipment attribution. Historical imports from before you had proper equipment records are a real scenario and they must not fail.
- **Calibration frames are sub frames** (`frame_type != 'light'`), not a separate table. Same columns, same resolution pipeline. Matching is a query problem, not a data model problem.
- **Raw blobs for forensics.** Where a source has rich structured data we can't fully parse yet (N.I.N.A. session logs, autofocus JSON, PHD2 log sections), store the raw payload in a `*_raw_json` or `*_raw_text` column alongside parsed fields. This lets us improve parsing later without re-ingesting.

---

### 2. Design decisions

#### 2.1 Rig is a label, not a source of truth

Two approaches to "what rig captured this sub?" were considered:

- **Approach A:** Rig is a stable snapshot of equipment. Each sub frame references `rig_id`. Equipment details are looked up through the rig.
- **Approach B:** Each sub frame records its equipment directly (camera, telescope, filter, etc.). Rig is an optional label/grouping that may or may not match.

**Decision: Approach B.** Rigs are useful for saying "capture new data with the C11 rig" (forward-looking) and for grouping historical data in the UI. But the authoritative record of what captured a sub frame is the sub frame itself, inferred from FITS headers at ingest time. This avoids the slowly-changing-dimension nightmare of versioning rigs every time Fred swaps a filter, and it handles data imported from before a rig was defined.

`sub_frame.rig_id` is nullable. It's populated by the ingest pipeline as a best-guess based on which rig's current equipment matches the sub frame's recorded equipment.

#### 2.2 filter_wheel_filter is keyed to rig, not filter wheel

When the FITS resolver needs to map `FILTER = "Ha"` to a physical filter, it needs rig context: Fred's "Ha" is Optolong 7nm on the C11 rig and Antlia 3nm on the Askar V rig. The `filter_wheel_filter` table links rig → filter wheel position → filter. It represents the *current* loadout of the rig. When Fred swaps filters, he updates this table, but historical sub frames are unaffected because they already captured `filter_id` directly.

#### 2.3 Project → project_target → sub frame, not project → sub frame

A project is a logical imaging effort. For non-mosaic projects, it has one target. For mosaics, it has many panels. The `project_target` table is the join between a project and its target(s), carrying panel-specific center coordinates, rotation, and per-panel goals.

Sub frames reference `project_target_id` (nullable). This way:
- Non-mosaic queries ("integration on M101") work via a single join.
- Mosaic queries ("panel 3 of the M31 mosaic needs more Ha") work via the panel.
- Subs that haven't been assigned to a project yet have NULL and can be bulk-assigned later.

#### 2.4 Calibration frames live in the sub_frame table

Lights, darks, flats, and bias frames all have the same shape: they're FITS files with headers. Putting them in one table means one ingest pipeline, one resolution layer, one set of indices. Matching lights to calibration frames is a view (§12), not a separate data structure. If matching performance becomes a problem on large libraries, introduce a materialized match table later.

`sub_frame.session_id` is nullable. Library darks and bias frames taken outside any specific session (stored calibration library reused across months of imaging) exist as sub frames with no session.

#### 2.5 PHD2 data is stored per-sample, not just per-log

PHD2 logs contain thousands of samples per night. Storing them in their own table (`guiding_sample`) lets the app do per-sub RMS calculations, show guiding graphs for arbitrary time ranges, and analyze guiding quality over time. This is more rows than any other table, but they're small rows and SQLite handles millions of them without issue. Indexing is the only real concern (§14).

#### 2.6 Session events are a separate table

N.I.N.A. and ASIAIR session logs are timelines of events: filter change at 03:14, autofocus at 03:22, plate solve at 03:23, exposure start at 03:24, and so on. Parsing these into a `session_event` table enables the Gantt timeline visualization Fred wants. The raw log files are also retained (`session_log_file`) so reparsing can recover any event types we missed.

#### 2.7 No plate_solve table — plate solve results live on sub_frame

Plate solving happens per sub frame. Its output is RA, Dec, rotation, pixel scale — which are inline columns on `sub_frame`. A separate `plate_solve` table would add a join for no benefit. If plate solve metadata (solver name, version, runtime) matters later, add columns to `sub_frame` or a sibling `sub_frame_platesolve` 1:1 table.

#### 2.8 File content hash is sub frame identity

Every ingested sub frame has a SHA-256 of its file contents stored as `content_hash`. This is `UNIQUE` — re-ingesting the same file (even after it's been moved) is idempotent. File paths live in a separate `file_location` table so one sub frame can exist in multiple places (original acquisition PC, Mac working copy, NAS archive).

#### 2.9 Deferred: equipment versioning, rig snapshots, calibration sets

Not in this spec:

- **Rig versioning.** If you swap a camera, create a new rig or leave the old one as-is. No timeline tracking yet.
- **Named calibration libraries.** Darks are just `frame_type='dark'` sub frames with `session_id=NULL`. Grouping them into "Dark Library Winter 2025" is a future feature.
- **Processing outputs** (stacked masters, processed images). A later `processed_image` table will handle these; this spec is raw-capture-only.

---

### 3. Targets and projects

#### target

Cache of astronomical objects. Populated by plate solves, name lookups, and user entry.

```sql
CREATE TABLE target (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_name TEXT NOT NULL UNIQUE,       -- "M101", "NGC 7000", "Sh2-155"
    object_type TEXT,                         -- "galaxy", "emission_nebula", "planetary_nebula", "cluster", "other"
    constellation TEXT,
    ra_deg REAL,                              -- J2000
    dec_deg REAL,                             -- J2000
    catalog_designations_json TEXT,           -- JSON array: ["NGC 5457", "UGC 8981", "Arp 26"]
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user', 'simbad', 'ned', 'plate_solve', 'nina', 'asiair')),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);

CREATE INDEX idx_target_primary_name ON target(primary_name);
```

#### project

```sql
CREATE TABLE project (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'complete', 'abandoned')),
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    goal_total_integration_minutes REAL,
    cover_sub_frame_id INTEGER,               -- FK added later via ALTER after sub_frame exists
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

#### project_target

Join between project and target, with panel-specific data for mosaics.

```sql
CREATE TABLE project_target (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    target_id INTEGER NOT NULL REFERENCES target(id),
    panel_name TEXT,                          -- NULL for non-mosaic; "Panel 1" for mosaics
    panel_index INTEGER NOT NULL DEFAULT 0,   -- 0 for non-mosaic; 1..N for mosaic panels
    center_ra_deg REAL,                       -- may differ from target.ra_deg for mosaic panels
    center_dec_deg REAL,
    rotation_deg REAL,
    goal_integration_minutes REAL,            -- per-panel goal; rolls up to project.goal_total
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, panel_index)
);

CREATE INDEX idx_project_target_project ON project_target(project_id);
CREATE INDEX idx_project_target_target ON project_target(target_id);
```

#### project_filter_goal

Per-filter integration goals for a project target. "4 hours of Ha on the Elephant Trunk."

```sql
CREATE TABLE project_filter_goal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_target_id INTEGER NOT NULL REFERENCES project_target(id) ON DELETE CASCADE,
    line_name TEXT NOT NULL,                  -- same controlled vocabulary as filter_passband.line_name
    goal_minutes REAL NOT NULL CHECK (goal_minutes > 0),
    notes TEXT,
    CHECK (line_name IN (
        'Ha', 'Hb', 'Oiii', 'Sii', 'Nii', 'OI',
        'Lum', 'R', 'G', 'B',
        'UVIR', 'LP', 'ND', 'other'
    )),
    UNIQUE (project_target_id, line_name)
);

CREATE INDEX idx_project_filter_goal_target ON project_filter_goal(project_target_id);
```

Note: goals are per `line_name`, not per physical filter. A goal of "240 minutes of Ha" is satisfied by any sub frame whose filter has an `Ha` passband, regardless of which physical Ha filter.

---

### 4. Rigs and filter wheel contents

#### rig

A rig is a labeled grouping of equipment. It's the "template" used for new captures and the "best-guess grouping" applied to historical sub frames at ingest time.

```sql
CREATE TABLE rig (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    telescope_id INTEGER REFERENCES telescope(id),
    telescope_configuration_id INTEGER REFERENCES telescope_configuration(id),
    camera_id INTEGER REFERENCES camera(id),
    mount_id INTEGER REFERENCES mount(id),
    filter_wheel_id INTEGER REFERENCES filter_wheel(id),
    focuser_id INTEGER REFERENCES focuser(id),
    oag_id INTEGER REFERENCES oag(id),
    guide_scope_id INTEGER REFERENCES guide_scope(id),
    guide_camera_id INTEGER REFERENCES camera(id),
    capture_computer_id INTEGER REFERENCES computer(id),
    capture_software_id INTEGER REFERENCES software(id),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    -- active, source, seed_key, seed_hash omitted: rigs are user-defined, not seed-tracked
);

CREATE INDEX idx_rig_telescope ON rig(telescope_id);
CREATE INDEX idx_rig_camera ON rig(camera_id);
```

**Constraint:** all component FKs are nullable because rigs vary — a Seestar smart scope has no separate focuser or filter wheel, for example. Validation of "is this rig usable?" is an application concern, not a schema constraint.

#### filter_wheel_filter

Which filters are currently loaded in which position of a rig's filter wheel. This is the table the FITS resolver's line-name path needs.

```sql
CREATE TABLE filter_wheel_filter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rig_id INTEGER NOT NULL REFERENCES rig(id) ON DELETE CASCADE,
    filter_wheel_id INTEGER NOT NULL REFERENCES filter_wheel(id),
    position INTEGER NOT NULL CHECK (position > 0),
    filter_id INTEGER NOT NULL REFERENCES filter(id),
    installed_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT,
    UNIQUE (rig_id, position),
    UNIQUE (rig_id, filter_id)                -- a physical filter can only be in one slot at a time per rig
);

CREATE INDEX idx_filter_wheel_filter_rig ON filter_wheel_filter(rig_id);
CREATE INDEX idx_filter_wheel_filter_filter ON filter_wheel_filter(filter_id);
```

When Fred swaps filters between rigs or reorders his wheel, this table gets updated. Historical sub frames already have `filter_id` recorded inline (see §6), so past captures are unaffected by current loadout changes.

---

### 5. Sessions and session events

#### session

A session is a contiguous period of rig activity — typically one night of imaging on one rig. A single night with two rigs running simultaneously is two sessions (one per rig).

Session boundaries are determined by the ingest pipeline, not by the schema. The spec here only describes the storage.

```sql
CREATE TABLE session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rig_id INTEGER REFERENCES rig(id),
    session_name TEXT,                        -- optional user label
    start_utc TEXT NOT NULL,
    end_utc TEXT,                             -- NULL if session is open or unknown end
    site_name TEXT,
    site_latitude_deg REAL,
    site_longitude_deg REAL,
    site_elevation_m REAL,
    bortle_class INTEGER CHECK (bortle_class IS NULL OR bortle_class BETWEEN 1 AND 9),
    conditions_notes TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_session_rig ON session(rig_id);
CREATE INDEX idx_session_start_utc ON session(start_utc);
```

#### session_log_file

Raw log files ingested for the session. Retain the originals (or hashed references to them) so reparsing can recover any events we missed on the first pass.

```sql
CREATE TABLE session_log_file (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (source IN ('nina', 'asiair', 'phd2', 'other')),
    original_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,                  -- SHA-256 of contents
    file_size_bytes INTEGER NOT NULL,
    covered_start_utc TEXT,                   -- first timestamp in file
    covered_end_utc TEXT,                     -- last timestamp in file
    parse_status TEXT NOT NULL DEFAULT 'pending' CHECK (parse_status IN ('pending', 'parsed', 'failed', 'partial')),
    parse_error TEXT,
    raw_text BLOB,                            -- optional: store the raw log for reparse; may be large
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (file_hash)
);

CREATE INDEX idx_session_log_file_session ON session_log_file(session_id);
```

#### session_event

Parsed events from session logs. This is the source for the Gantt timeline visualization.

```sql
CREATE TABLE session_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    session_log_file_id INTEGER REFERENCES session_log_file(id),
    event_utc TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'session_start', 'session_end',
        'slew_start', 'slew_end',
        'plate_solve_start', 'plate_solve_end', 'plate_solve_failed',
        'filter_change',
        'exposure_start', 'exposure_end',
        'autofocus_start', 'autofocus_end',
        'dither',
        'meridian_flip_start', 'meridian_flip_end',
        'guiding_start', 'guiding_stop', 'guiding_lost',
        'cooling_target_reached',
        'error', 'warning', 'info',
        'other'
    )),
    event_data_json TEXT,                     -- structured per-type payload
    related_sub_frame_id INTEGER,             -- FK added after sub_frame exists
    related_filter_id INTEGER REFERENCES filter(id),
    notes TEXT
);

CREATE INDEX idx_session_event_session_time ON session_event(session_id, event_utc);
CREATE INDEX idx_session_event_type ON session_event(event_type);
```

`event_data_json` payloads per event type (documented in the README, not enforced):

- `plate_solve_end`: `{"ra_deg": ..., "dec_deg": ..., "rotation_deg": ..., "pixel_scale_arcsec": ...}`
- `filter_change`: `{"from_filter_id": ..., "to_filter_id": ..., "position": ...}`
- `autofocus_end`: `{"initial_hfr": ..., "final_hfr": ..., "steps_moved": ..., "temperature_c": ...}`
- `dither`: `{"ra_offset_arcsec": ..., "dec_offset_arcsec": ..., "settled_after_seconds": ...}`
- `error`: `{"message": "...", "source": "..."}`

---

### 6. Sub frames

The core atom. One row per captured exposure.

#### sub_frame

```sql
CREATE TABLE sub_frame (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity (stable across re-ingest and file movement)
    content_hash TEXT NOT NULL UNIQUE,        -- SHA-256 of full file contents, hex encoded

    -- Grouping (all nullable — ingested subs may not have all context)
    session_id INTEGER REFERENCES session(id),
    rig_id INTEGER REFERENCES rig(id),
    project_target_id INTEGER REFERENCES project_target(id),

    -- Frame classification
    frame_type TEXT NOT NULL CHECK (frame_type IN ('light', 'dark', 'flat', 'bias', 'dark_flat', 'unknown')),
    accepted INTEGER NOT NULL DEFAULT 1 CHECK (accepted IN (0,1)),
    rejection_reason TEXT,
    rejection_source TEXT CHECK (rejection_source IS NULL OR rejection_source IN ('user', 'automated', 'ingest')),

    -- Equipment (nullable; resolver fills what it can)
    camera_id INTEGER REFERENCES camera(id),
    telescope_id INTEGER REFERENCES telescope(id),
    telescope_configuration_id INTEGER REFERENCES telescope_configuration(id),
    filter_id INTEGER REFERENCES filter(id),
    mount_id INTEGER REFERENCES mount(id),
    filter_wheel_id INTEGER REFERENCES filter_wheel(id),
    focuser_id INTEGER REFERENCES focuser(id),

    -- Capture settings (from FITS header)
    exposure_seconds REAL NOT NULL CHECK (exposure_seconds > 0),
    gain INTEGER,
    offset_adu INTEGER,
    sensor_temp_c REAL,
    set_temp_c REAL,
    binning_x INTEGER NOT NULL DEFAULT 1,
    binning_y INTEGER NOT NULL DEFAULT 1,
    bit_depth INTEGER,
    image_width_px INTEGER,
    image_height_px INTEGER,

    -- Timing
    date_obs_utc TEXT NOT NULL,               -- ISO 8601, from DATE-OBS header
    obs_mjd REAL,                             -- Modified Julian Date, for precise ordering

    -- Pointing (from plate solve or headers)
    ra_deg REAL,                              -- J2000, plate-solved if available
    dec_deg REAL,
    rotation_deg REAL,
    pixel_scale_arcsec REAL,
    airmass REAL,

    -- Quality metrics (computed at ingest or later)
    hfr REAL,                                 -- half-flux radius, median
    star_count INTEGER,
    median_adu REAL,
    background_adu REAL,
    snr_estimate REAL,

    -- Site (redundant with session but denormalized for standalone queries)
    site_latitude_deg REAL,
    site_longitude_deg REAL,
    site_elevation_m REAL,

    -- Raw FITS header for forensics / reparse
    fits_header_json TEXT,                    -- optional: full header as JSON

    -- Provenance
    ingestion_run_id INTEGER,                 -- FK added later
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    notes TEXT,

    CHECK (
        -- Light frames must have a filter; calibration frames have frame-type-specific rules
        (frame_type = 'light' AND filter_id IS NOT NULL)
        OR (frame_type != 'light')
    )
);

CREATE INDEX idx_sub_frame_session ON sub_frame(session_id);
CREATE INDEX idx_sub_frame_project_target ON sub_frame(project_target_id);
CREATE INDEX idx_sub_frame_rig ON sub_frame(rig_id);
CREATE INDEX idx_sub_frame_camera ON sub_frame(camera_id);
CREATE INDEX idx_sub_frame_filter ON sub_frame(filter_id);
CREATE INDEX idx_sub_frame_frame_type ON sub_frame(frame_type);
CREATE INDEX idx_sub_frame_date_obs ON sub_frame(date_obs_utc);

-- Composite index for the most common calibration-match query
CREATE INDEX idx_sub_frame_dark_match
    ON sub_frame(camera_id, gain, set_temp_c, exposure_seconds, binning_x, binning_y)
    WHERE frame_type = 'dark';

CREATE INDEX idx_sub_frame_flat_match
    ON sub_frame(camera_id, gain, filter_id, binning_x, binning_y, telescope_configuration_id)
    WHERE frame_type = 'flat';

CREATE INDEX idx_sub_frame_bias_match
    ON sub_frame(camera_id, gain, binning_x, binning_y)
    WHERE frame_type = 'bias';
```

**Updated_at trigger** (same pattern as equipment tables):

```sql
CREATE TRIGGER trg_sub_frame_updated_at
AFTER UPDATE ON sub_frame
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE sub_frame SET updated_at = datetime('now') WHERE id = NEW.id;
END;
```

Once `sub_frame` exists, add the deferred FKs:

```sql
-- project.cover_sub_frame_id
ALTER TABLE project ADD COLUMN cover_sub_frame_id INTEGER REFERENCES sub_frame(id);

-- session_event.related_sub_frame_id
ALTER TABLE session_event ADD COLUMN related_sub_frame_id INTEGER REFERENCES sub_frame(id);
```

(Actually declare both FKs in the original CREATE and drop the forward-reference comment. SQLite is fine with forward references inside a single migration script; just create `sub_frame` before the tables that reference it, or use deferred FKs. Pick the cleaner approach at implementation time.)

---

### 7. Calibration frame handling

No separate table. Calibration frames are `sub_frame` rows with:

- `frame_type IN ('dark', 'flat', 'bias', 'dark_flat')`
- `session_id` nullable (library frames have NULL)
- `project_target_id` always NULL
- `filter_id` required only for flats (and dark_flats, if distinguished)

#### Calibration matching views

```sql
-- For each light frame, the matching dark frames
CREATE VIEW matching_darks AS
SELECT
    light.id AS light_id,
    dark.id AS dark_id,
    dark.date_obs_utc AS dark_date_obs_utc
FROM sub_frame light
JOIN sub_frame dark
  ON dark.frame_type = 'dark'
  AND dark.camera_id = light.camera_id
  AND dark.gain = light.gain
  AND dark.exposure_seconds = light.exposure_seconds
  AND dark.binning_x = light.binning_x
  AND dark.binning_y = light.binning_y
  AND ABS(COALESCE(dark.set_temp_c, -999) - COALESCE(light.set_temp_c, -999)) < 1.0
WHERE light.frame_type = 'light'
  AND light.accepted = 1
  AND dark.accepted = 1;

-- For each light frame, matching flats
CREATE VIEW matching_flats AS
SELECT
    light.id AS light_id,
    flat.id AS flat_id,
    flat.date_obs_utc AS flat_date_obs_utc
FROM sub_frame light
JOIN sub_frame flat
  ON flat.frame_type = 'flat'
  AND flat.camera_id = light.camera_id
  AND flat.gain = light.gain
  AND flat.filter_id = light.filter_id
  AND flat.binning_x = light.binning_x
  AND flat.binning_y = light.binning_y
  AND flat.telescope_configuration_id = light.telescope_configuration_id
WHERE light.frame_type = 'light'
  AND light.accepted = 1
  AND flat.accepted = 1;

-- For each light frame, matching bias
CREATE VIEW matching_bias AS
SELECT
    light.id AS light_id,
    bias.id AS bias_id,
    bias.date_obs_utc AS bias_date_obs_utc
FROM sub_frame light
JOIN sub_frame bias
  ON bias.frame_type = 'bias'
  AND bias.camera_id = light.camera_id
  AND bias.gain = light.gain
  AND bias.binning_x = light.binning_x
  AND bias.binning_y = light.binning_y
WHERE light.frame_type = 'light'
  AND light.accepted = 1
  AND bias.accepted = 1;

-- Summary: does each light have at least one of each calibration type?
CREATE VIEW calibration_coverage AS
SELECT
    light.id AS light_id,
    light.session_id,
    light.project_target_id,
    light.filter_id,
    EXISTS (SELECT 1 FROM matching_darks md WHERE md.light_id = light.id) AS has_dark,
    EXISTS (SELECT 1 FROM matching_flats mf WHERE mf.light_id = light.id) AS has_flat,
    EXISTS (SELECT 1 FROM matching_bias mb WHERE mb.light_id = light.id) AS has_bias
FROM sub_frame light
WHERE light.frame_type = 'light';
```

These are views, not materialized tables. On very large libraries they may get slow; if that happens, the fix is to precompute a `calibration_match` table maintained by triggers. Out of scope for this change.

Flat matching includes `telescope_configuration_id` because flats capture optical train state (rotator angle, dust, vignetting), which differs per configuration. A flat taken with the C11 at native focal length does not correctly calibrate a light taken with the 0.7x corrector.

---

### 8. PHD2 guiding data

#### guiding_log_file

Metadata about a PHD2 log file ingested for a session. A single PHD2 log typically spans an entire night and covers all targets imaged that night, so it maps one-to-one with a session (or one-to-many if there are log rotations).

```sql
CREATE TABLE guiding_log_file (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    original_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    start_utc TEXT NOT NULL,
    end_utc TEXT NOT NULL,
    guide_camera_id INTEGER REFERENCES camera(id),
    guide_scope_id INTEGER REFERENCES guide_scope(id),
    oag_id INTEGER REFERENCES oag(id),
    guide_pixel_scale_arcsec REAL,
    parse_status TEXT NOT NULL DEFAULT 'pending' CHECK (parse_status IN ('pending', 'parsed', 'failed', 'partial')),
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (file_hash)
);

CREATE INDEX idx_guiding_log_file_session ON guiding_log_file(session_id);
```

#### guiding_sample

Individual PHD2 samples. One row per guide exposure (typically every 1–3 seconds during a session).

```sql
CREATE TABLE guiding_sample (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guiding_log_file_id INTEGER NOT NULL REFERENCES guiding_log_file(id) ON DELETE CASCADE,
    sample_utc TEXT NOT NULL,
    ra_error_arcsec REAL,
    dec_error_arcsec REAL,
    ra_correction REAL,                       -- in PHD2's native units
    dec_correction REAL,
    snr REAL,
    star_mass REAL,
    frame_number INTEGER
);

-- This index is critical for the per-sub guiding lookup
CREATE INDEX idx_guiding_sample_log_time
    ON guiding_sample(guiding_log_file_id, sample_utc);

CREATE INDEX idx_guiding_sample_time ON guiding_sample(sample_utc);
```

#### dither_event

Distinct dither events from the guiding log. Useful for overlaying on the guiding graph and for splitting RMS calculations around dither settles.

```sql
CREATE TABLE dither_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guiding_log_file_id INTEGER NOT NULL REFERENCES guiding_log_file(id) ON DELETE CASCADE,
    dither_utc TEXT NOT NULL,
    ra_offset_arcsec REAL,
    dec_offset_arcsec REAL,
    settle_completed_utc TEXT,
    settle_failed INTEGER NOT NULL DEFAULT 0 CHECK (settle_failed IN (0,1))
);

CREATE INDEX idx_dither_event_log_time ON dither_event(guiding_log_file_id, dither_utc);
```

#### Per-sub guiding lookup

Guiding stats for a specific sub frame are computed on demand from `guiding_sample` filtered by the sub frame's time range:

```sql
-- Example: RMS during a specific sub frame
SELECT
    SQRT(AVG(ra_error_arcsec * ra_error_arcsec + dec_error_arcsec * dec_error_arcsec)) AS rms_total,
    SQRT(AVG(ra_error_arcsec * ra_error_arcsec)) AS rms_ra,
    SQRT(AVG(dec_error_arcsec * dec_error_arcsec)) AS rms_dec,
    MAX(ABS(ra_error_arcsec)) AS peak_ra,
    MAX(ABS(dec_error_arcsec)) AS peak_dec,
    COUNT(*) AS sample_count
FROM guiding_sample gs
JOIN guiding_log_file glf ON glf.id = gs.guiding_log_file_id
JOIN sub_frame sf ON sf.id = ?
WHERE glf.session_id = sf.session_id
  AND gs.sample_utc >= sf.date_obs_utc
  AND gs.sample_utc < datetime(sf.date_obs_utc, '+' || sf.exposure_seconds || ' seconds');
```

This is a per-query pattern, not a stored view — parameterized on the sub frame ID.

---

### 9. Autofocus runs

```sql
CREATE TABLE autofocus_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    triggered_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    filter_id INTEGER REFERENCES filter(id),
    focuser_id INTEGER REFERENCES focuser(id),
    temperature_c REAL,
    initial_position INTEGER,
    final_position INTEGER,
    initial_hfr REAL,
    final_hfr REAL,
    success INTEGER NOT NULL DEFAULT 1 CHECK (success IN (0,1)),
    trigger_reason TEXT,                      -- "scheduled", "temperature_delta", "hfr_drift", "filter_change", "manual"
    source TEXT CHECK (source IN ('nina', 'asiair', 'manual', 'other')),
    raw_json TEXT,                            -- full autofocus JSON from N.I.N.A., preserved for reparse
    notes TEXT
);

CREATE INDEX idx_autofocus_run_session ON autofocus_run(session_id);
CREATE INDEX idx_autofocus_run_triggered_at ON autofocus_run(triggered_at_utc);
```

---

### 10. File locations and content hashing

A single sub frame may exist in multiple filesystem locations (original on acquisition PC, working copy on Mac, archive on NAS). The `file_location` table tracks all known copies.

```sql
CREATE TABLE file_location (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sub_frame_id INTEGER NOT NULL REFERENCES sub_frame(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    path_type TEXT NOT NULL CHECK (path_type IN ('original', 'working_copy', 'archive', 'reorganized', 'other')),
    volume_label TEXT,                        -- "MacSSD", "Synology-NAS", "AX8Max-C"
    file_size_bytes INTEGER,
    file_hash TEXT,                           -- should match sub_frame.content_hash when verified
    file_mtime TEXT,
    last_verified_at TEXT,
    last_verified_status TEXT CHECK (last_verified_status IS NULL OR last_verified_status IN ('ok', 'missing', 'hash_mismatch', 'unreadable')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (path)
);

CREATE INDEX idx_file_location_sub_frame ON file_location(sub_frame_id);
CREATE INDEX idx_file_location_path_type ON file_location(path_type);
```

**Verification is a background task.** The app periodically re-hashes files (or checks mtime + size as a fast path) and updates `last_verified_status`. If a file is missing from its original location but present on the NAS, the app can still open it — it just picks the best available location.

---

### 11. Ingestion provenance

```sql
CREATE TABLE ingestion_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    source_path TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('catalog_in_place', 'copy_and_organize', 'reparse')),
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    files_scanned INTEGER NOT NULL DEFAULT 0,
    sub_frames_inserted INTEGER NOT NULL DEFAULT 0,
    sub_frames_updated INTEGER NOT NULL DEFAULT 0,
    sub_frames_skipped INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0,
    errors_json TEXT,
    notes TEXT
);

CREATE INDEX idx_ingestion_run_started_at ON ingestion_run(started_at);
```

Add to `sub_frame` (referenced above):

```sql
-- Already declared in §6 as sub_frame.ingestion_run_id INTEGER
-- Wire up the FK now that ingestion_run exists:
-- In the migration, declare sub_frame AFTER ingestion_run and include:
--   ingestion_run_id INTEGER REFERENCES ingestion_run(id)
```

---

### 12. Views and aggregates

#### integration_time_per_project_filter

The dashboard Fred wants: "how much Ha do I have on M101?"

```sql
CREATE VIEW integration_time_per_project_filter AS
SELECT
    pt.project_id,
    pt.id AS project_target_id,
    pt.panel_name,
    fp.line_name,
    COUNT(sf.id) AS accepted_sub_count,
    SUM(sf.exposure_seconds) AS total_seconds,
    SUM(sf.exposure_seconds) / 60.0 AS total_minutes,
    SUM(sf.exposure_seconds) / 3600.0 AS total_hours
FROM sub_frame sf
JOIN project_target pt ON pt.id = sf.project_target_id
JOIN filter f ON f.id = sf.filter_id
JOIN filter_passband fp ON fp.filter_id = f.id
WHERE sf.frame_type = 'light'
  AND sf.accepted = 1
GROUP BY pt.project_id, pt.id, pt.panel_name, fp.line_name;
```

For a single-band filter ("Ha 7nm"), this produces one row per sub with `line_name = 'Ha'`. For a duoband filter (e.g. Ha+Oiii), **this view will double-count** — one row for Ha, one for Oiii — which is actually what you want for "how much Ha have I captured?" since the sub contributes to both line budgets. Document this behavior explicitly in the README.

#### project_filter_goal_progress

Join goal and actual for dashboard display:

```sql
CREATE VIEW project_filter_goal_progress AS
SELECT
    pt.project_id,
    pt.id AS project_target_id,
    pt.panel_name,
    pfg.line_name,
    pfg.goal_minutes,
    COALESCE(itpf.total_minutes, 0) AS actual_minutes,
    COALESCE(itpf.total_minutes, 0) / pfg.goal_minutes AS completion_ratio
FROM project_target pt
JOIN project_filter_goal pfg ON pfg.project_target_id = pt.id
LEFT JOIN integration_time_per_project_filter itpf
    ON itpf.project_target_id = pt.id
   AND itpf.line_name = pfg.line_name;
```

#### session_summary

Quick "what happened during this session" rollup:

```sql
CREATE VIEW session_summary AS
SELECT
    s.id AS session_id,
    s.rig_id,
    s.start_utc,
    s.end_utc,
    (julianday(s.end_utc) - julianday(s.start_utc)) * 24.0 AS duration_hours,
    COUNT(DISTINCT sf.id) AS total_subs,
    SUM(CASE WHEN sf.frame_type = 'light' AND sf.accepted = 1 THEN 1 ELSE 0 END) AS accepted_lights,
    SUM(CASE WHEN sf.frame_type = 'light' AND sf.accepted = 0 THEN 1 ELSE 0 END) AS rejected_lights,
    SUM(CASE WHEN sf.frame_type = 'light' AND sf.accepted = 1 THEN sf.exposure_seconds ELSE 0 END) / 60.0 AS accepted_minutes,
    COUNT(DISTINCT sf.project_target_id) AS distinct_targets,
    COUNT(DISTINCT sf.filter_id) AS distinct_filters
FROM session s
LEFT JOIN sub_frame sf ON sf.session_id = s.id
GROUP BY s.id;
```

---

### 13. AI context bundle (serialization contract)

**This is the load-bearing AI-readiness requirement.** The post-MVP AI analyzer feature will take a session (or a project, or a sub frame) and feed a structured summary of its data into a Claude context window. The schema must support assembling this summary with straightforward queries.

This spec does **not** implement the bundle assembler. It declares the contract the schema supports, so that when the assembler is built it's a matter of writing queries against existing tables rather than reshaping data.

#### Bundle shape — session level

A session bundle is a single JSON document combining: session metadata, equipment details, target breakdown, sub frame statistics, guiding telemetry, focus telemetry, and event timeline.

```python
def build_session_context(session_id: int) -> dict:
    """
    Assemble a session into an AI-context-ready dict.
    All timestamps are UTC ISO 8601. All units are explicit in field names.
    """
```

Example output shape (for documentation; not something to implement now):

```json
{
  "schema_version": 1,
  "session": {
    "id": 123,
    "start_utc": "2025-03-15T03:14:00Z",
    "end_utc": "2025-03-15T10:47:00Z",
    "duration_hours": 7.55,
    "site": {
      "latitude_deg": 33.45,
      "longitude_deg": -112.07,
      "elevation_m": 340,
      "bortle_class": 7
    }
  },
  "equipment": {
    "rig_name": "C11 Primary",
    "telescope": {
      "model": "Celestron C11 SCT",
      "aperture_mm": 280,
      "optical_design": "SCT",
      "configuration": "Starizona LF 0.7x",
      "effective_focal_length_mm": 1960,
      "effective_focal_ratio": 7.0
    },
    "camera": {
      "model": "ZWO ASI 2600MM Pro",
      "sensor": "Sony IMX571",
      "pixel_size_um": 3.76,
      "resolution_px": [6248, 4176]
    },
    "mount": {"model": "WarpAstron WD-20", "type": "Harmonic Equatorial"},
    "guiding": {"scope_or_oag": "OAG", "camera": "ZWO ASI 178MM", "software": "PHD2"}
  },
  "targets": [
    {
      "project_name": "M101 Deep",
      "panel_name": null,
      "target_primary_name": "M101",
      "ra_deg": 210.80,
      "dec_deg": 54.35,
      "sub_count_this_session": 45,
      "integration_minutes_this_session": 93.5
    }
  ],
  "subs_summary": {
    "total": 45,
    "accepted": 43,
    "rejected": 2,
    "rejection_reasons": ["clouds (2)"],
    "by_filter": [
      {
        "filter_model": "Optolong 7nm Ha",
        "line_name": "Ha",
        "count": 28,
        "exposure_seconds_each": 300,
        "total_minutes": 140,
        "median_hfr": 1.87,
        "hfr_range": [1.71, 2.34],
        "median_star_count": 1847
      }
    ]
  },
  "guiding": {
    "total_rms_arcsec": 0.89,
    "ra_rms_arcsec": 0.62,
    "dec_rms_arcsec": 0.64,
    "peak_total_error_arcsec": 2.31,
    "dither_count": 22,
    "sample_count": 13500,
    "notable_spikes": [
      {"utc": "2025-03-15T05:22:00Z", "peak_arcsec": 4.8, "duration_seconds": 12}
    ]
  },
  "focus": {
    "autofocus_run_count": 4,
    "median_final_hfr": 1.82,
    "temperature_range_c": [8.2, 14.1],
    "focus_position_drift": 87
  },
  "events_timeline": [
    {"utc": "2025-03-15T03:14:00Z", "type": "session_start"},
    {"utc": "2025-03-15T03:16:22Z", "type": "plate_solve_end", "ra_deg": 210.81, "dec_deg": 54.34},
    {"utc": "2025-03-15T03:18:00Z", "type": "autofocus_end", "final_hfr": 1.79},
    {"utc": "2025-03-15T03:24:15Z", "type": "exposure_start", "filter": "Lum", "exposure_seconds": 120}
  ],
  "issues_detected": [
    {"type": "guiding_spike", "severity": "warning", "utc": "2025-03-15T05:22:00Z", "description": "4.8 arcsec spike, 12s duration"}
  ]
}
```

#### Schema implications of this bundle

The bundle drives these design choices in the schema above:

- **Equipment details are joinable in one hop from sub_frame** (camera, telescope, filter, etc.) because sub_frame has direct FKs. No need to walk through rig → camera.
- **Per-filter aggregates come from a simple `GROUP BY sf.filter_id`** joined with `filter_passband.line_name`. No custom aggregation tables needed.
- **Guiding stats come from a time-range query on `guiding_sample`** indexed by (guiding_log_file_id, sample_utc). No denormalized per-sub guiding columns.
- **Events timeline is `session_event` ordered by `event_utc`** — already a first-class table.
- **Issues detection is a separate layer** that runs queries against the schema. It is not stored. That layer doesn't exist yet; the schema just has to support the queries it will want to run.

#### The `schema_version` field is a real contract

Any future change to the bundle shape bumps `schema_version`. The AI analyzer code must be able to handle multiple versions gracefully. This is documented here even though the assembler isn't built yet, because it affects how the queries are structured. Assume version 1 from day one.

---

### 14. Indices

Already declared inline above. Summary of the critical ones:

- `sub_frame.content_hash` — `UNIQUE`, the identity of the frame.
- `sub_frame(session_id)`, `sub_frame(project_target_id)`, `sub_frame(rig_id)`, `sub_frame(camera_id)`, `sub_frame(filter_id)`, `sub_frame(date_obs_utc)` — standard lookups.
- `sub_frame(camera_id, gain, set_temp_c, exposure_seconds, binning_x, binning_y) WHERE frame_type = 'dark'` — partial index for dark matching.
- `sub_frame(camera_id, gain, filter_id, binning_x, binning_y, telescope_configuration_id) WHERE frame_type = 'flat'` — partial index for flat matching.
- `guiding_sample(guiding_log_file_id, sample_utc)` — the per-sub guiding lookup.
- `session_event(session_id, event_utc)` — the Gantt timeline query.

Performance is expected to be fine for libraries up to ~100k sub frames without further tuning. Beyond that, some views may need to become materialized tables maintained by triggers.

---

### 15. Deliverables

1. **A SQLite migration script** that creates all tables, indices, views, and triggers defined above. Idempotent (`IF NOT EXISTS`). Handle the forward-FK situation (`project.cover_sub_frame_id`, `session_event.related_sub_frame_id`, `sub_frame.ingestion_run_id`) cleanly by ordering CREATE statements so targets exist before references, or by using `ALTER TABLE ADD COLUMN` post-hoc.

2. **Seeded controlled-vocabulary CHECK values** — no data seeding required for this layer. Targets, projects, rigs are all user-created.

3. **README section** covering:
   - The design decisions from §2 (short version).
   - The "sub frame is source of truth" principle and why equipment FKs are duplicated on sub_frame rather than being inferred from rig.
   - The calibration matching view behavior and its limitations.
   - The `schema_version: 1` contract for AI context bundles.
   - The duoband double-counting behavior in `integration_time_per_project_filter`.
   - Which views are expected to become materialized tables if the library grows past ~100k frames.

4. **Tests** — pytest-based, using in-memory SQLite with the full schema:
   - `test_sub_frame_content_hash_unique.py` — re-ingesting the same content hash is idempotent.
   - `test_matching_darks_view.py` — dark matching correctly finds matches on gain/temp/exposure/binning and rejects mismatches.
   - `test_matching_flats_view.py` — flat matching includes telescope_configuration_id in the join.
   - `test_integration_time_per_project_filter.py` — single-band and duoband filter contribution.
   - `test_guiding_per_sub_query.py` — per-sub RMS calculation from guiding_sample.
   - `test_session_summary_view.py` — rollup counts and durations.
   - `test_project_filter_goal_progress.py` — goal vs actual with NULL-safe LEFT JOIN.
   - `test_calibration_library_nullable_session.py` — a dark with `session_id = NULL` is valid and matches lights from any session.
   - `test_sub_frame_partial_equipment.py` — sub frame with some equipment FKs NULL ingests and queries correctly.

---

### What NOT to build in this change

- The ingest pipeline that parses FITS files and populates sub frames. Separate spec.
- The N.I.N.A. / ASIAIR session log parser. Separate spec.
- The PHD2 log parser. Separate spec.
- The plate solver integration (ASTAP, astrometry.net). Separate spec.
- The AI context bundle assembler. Schema supports it; code comes later.
- The issue detection layer (guiding spikes, suspected clouds, focus drift alerts). Schema supports it; logic comes later.
- Any UI.
- A `processed_image` table for stacked masters and finished images. Later.
- Rig versioning / slowly-changing-dimension support. Later if needed.
- Materialized calibration match tables. Start with views; optimize if needed.
- Named calibration libraries / dark library management. Later.
- Target auto-resolution from external catalogs (SIMBAD, NED). Later.
- Bortle class auto-detection from coordinates. Later.

---
## Future Features to Consider

Features that depend on cross-frame infrastructure or are beyond the current scope. Captured here for future planning.

### Aberration Inspector — Heatmap & Vector Field Views

- **Heatmap view:** Full frame with semi-transparent color overlay (viridis) showing per-sample-square median of selected metric. Adjustable opacity slider, color legend, tooltip on hover.
- **Vector field view:** Full frame with arrow/line overlay per sample square — direction = median elongation angle, length = median eccentricity. Squares with eccentricity < 0.1 shown as small circles (round stars). Arrow scale legend.
- **View mode toggle:** Crop Grid | Heatmap | Vector Field in toolbar.

### Aberration Inspector — Diagnosis Engine & Export

- **Automated diagnosis:** Pattern matching on sample square metrics to identify tilt, coma, astigmatism, field curvature, backspacing error, tracking/guiding error. Per diagnosis: type, confidence (0-100%), plain-English description, fix suggestion. "Ruled out" entries explaining why certain aberrations were excluded.
- **Diagnosis logic:** Std of elongation angles < 15° → tilt or tracking. Eccentricity gradient across field → tilt. Eccentricity correlates with distance from center → field curvature or coma. Radial elongation directions → coma; tangential → field curvature. Uniform direction aligned with RA axis → tracking error.
- **Export:** PNG screenshot, CSV per-star, CSV per-sample-square.

### Multi-Frame Comparison (Aberration Inspector)

- **Frame-to-frame comparison:** Side-by-side vector fields or heatmaps from two frames (before/after tilt adjustment). Includes a difference view showing improvement vs. degradation per zone.
- **Filter comparison:** Aberration patterns across different filters from the same session to diagnose chromatic focus shift or filter-dependent tilt.
- **Session trend tracking:** Plot average corner eccentricity over time across sessions to catch slowly drifting mirrors or loosening tilt adapters.

### Interactive Tools (Aberration Inspector)

- **User annotations:** Pin notes to specific zones and persist them across sessions.
- **Interactive zone drawing:** Drag/resize custom zones instead of a fixed rectangular grid for fine-grained investigation of specific field regions.

### Equipment Links

Add a `manufacturer_link` child table (manufacturer_id, label, url — unique on manufacturer_id + label) for associating multiple named URLs with each manufacturer (user forum, downloads, ASCOM drivers, spec sheets, etc.). Follows the same parent/child pattern as telescope_configuration and filter_passband. Seed loader gets a `manufacturer_link.csv`.

Extend the same pattern to other equipment types — allow one or more URLs on cameras, telescopes, mounts, etc. for direct links to manufacturer spec pages, manuals, firmware downloads. Could be a generic `equipment_link` table (table_name, item_id, label, url) or per-type child tables.

### Session & Catalog Features

- **Frame quality indicators on filmstrip thumbnails:** When browsing a night's subs, show SNR or FWHM badges on each thumbnail for quick quality assessment without opening each frame.
- **Background sample region stats:** User-selectable region on the image canvas for targeted statistics (background level, noise).
- **Session ingestion pipeline:** Ingest N.I.N.A./ASIAIR session logs, PHD2 guiding logs, FITS headers into a searchable catalog with integration-time dashboards.

### AI Analysis (Post-MVP)

- **AI session analyzer:** Claude-based analysis of session telemetry, guiding logs, and final images to provide improvement feedback. Monetized via [redacted] or subscription.
- **Data model designed for AI-readiness:** MVP data model serializable into coherent context windows for AI analysis.

### FITS Header Database Storage (Ingestion Pipeline)

- **Canonical metadata in typed columns:** Store normalized values (object_name, exposure_time, filter_name, gain, sensor_temp, etc.) in dedicated database columns for fast queries and calibration frame matching.
- **Raw FITS header as JSON:** Store the full raw header as a JSON column — escape hatch for re-extraction when new keywords are added to the alias map.
- **PixInsight quality metrics:** Dedicated nullable columns for pi_ssweight, pi_psf_fwhm, pi_psf_eccen, pi_noise_layer0, etc. — populated only for files processed through PixInsight.
- **Calibration key indexes:** Index on (camera_name, gain, sensor_temp, exposure_time, binning_x, binning_y, filter_name, frame_type) for fast calibration frame matching (darks, flats, bias).
- **Unrecognized keyword frequency table:** Track keyword frequency across all ingested files. When a new keyword appears frequently, it signals a new alias to add to the map.
- **Coordinate validation:** Parse and validate RA/DEC values (ASIAIR writes nonsensical coordinates in dark frame headers). Use astropy.coordinates.Angle for format handling.
- **IMAGETYP filename fallback:** When IMAGETYP is missing (some SharpCap versions), fall back to filename pattern matching (e.g., `Dark_10.0s_...` or path containing `/darks/`).

---

---

## Appendix: PHD2 Analyzer Roadmap

The PHD2 analyzer shipped across versions v0.22.0 through v0.27.0. Advanced analysis features (FFT spectrum, unguided RA reconstruction, worm markers, diagnostic engine) were explored in v0.26.0-v0.27.0 but removed as unreliable. The analyzer's final feature set covers: log parsing with format-irregularity recovery, per-section metrics (RMS, drift, PA error, oscillation, elongation), time-series chart with guide pulses + SNR + star mass panels, dispersion scatter plot with 1-sigma / 2-sigma ellipses, per-frame data table, and calibration geometry plotting.

---

## Appendix: Library Reference

Evaluated libraries for potential use across NightCrate. Every library must pass a license review before inclusion. NightCrate is licensed under **MIT**. Only permissive licenses (MIT, BSD, Apache, ISC, HPND, PSF) are freely compatible. LGPL is acceptable for Python runtime imports but requires discussion. GPL is not allowed.

### Already in Use

| Library | License | Role |
|---|---|---|
| numpy | BSD 3-Clause | Array math (via `core/compute.py` abstraction) |
| astropy | BSD 3-Clause | FITS I/O, WCS, coordinate transforms, units |
| Pillow | HPND (PIL License) | PNG encoding for image endpoints |
| aiosqlite | MIT | Async SQLite access |
| FastAPI / uvicorn | MIT | Web framework / ASGI server |
| Pydantic | MIT | Data models, API shapes, settings |
| yoyo-migrations | Apache 2.0 | Database schema migrations |
| React | MIT | Frontend UI framework |
| MUI (core + X Community) | MIT | UI component library |
| Zustand | MIT | Frontend state management |
| TanStack Query | MIT | Frontend data fetching |
| react-router-dom | MIT | Frontend routing |
| @dnd-kit/core, @dnd-kit/sortable, @dnd-kit/utilities | MIT | Accessible drag-and-drop primitives (Calculators clock reorder; candidate for other reorderable UI) |
| Vite | MIT | Frontend build tooling |
| TypeScript | Apache 2.0 | Frontend type system |

### Approved for Future Use

All licenses verified as commercial-compatible. Add via `uv add` (backend) or `npm install` (frontend) when needed.

| Library | License | Potential Role |
|---|---|---|
| scipy | BSD 3-Clause | Signal processing (PHD2 RMS stats, autofocus curve fitting) |
| pandas | BSD 3-Clause | PHD2 log parsing (CSV-like), session statistics tabulation |
| astroquery | BSD 3-Clause | Simbad/MAST queries for object info, catalog cross-matching. Note: library is BSD-3, but data from each service has its own terms of use (e.g., SIMBAD requires "This research made use of the SIMBAD database" attribution in published work). Check per-service terms when adding queries. |
| photutils | BSD 3-Clause | Source detection, background estimation, FWHM/HFR measurement for sub quality. Note: overlaps with `sep` (currently used in Aberration Inspector). If added, consider migrating Aberration Inspector for consistency, or keep both if sep's speed advantage matters for single-image analysis. |
| astroalign | MIT | Image registration/alignment for stacking prep |
| sep | LGPL-3.0 | Source extraction, star detection, quality metrics. ⚠ LGPL — fine as Python import (dynamic linking). At distribution time (Tauri/PyInstaller), bundle LICENSE file per LGPL §6. No runtime attribution required. |
| reproject | BSD 3-Clause | WCS reprojection for overlaying images from different rigs/orientations |
| psutil | BSD 3-Clause | System resource monitoring (CPU cores, memory for worker management) |
| lz4 | BSD 3-Clause | Fast compression for caching processed image data |
| zstandard | BSD 3-Clause | Higher-ratio compression for archiving/caching |
| pywavelets (pywt) | MIT | Wavelet-based noise reduction/sharpening |
| opencv-python-headless | Apache 2.0 | Image processing, quality analysis. Use `-headless` variant (avoids Qt/GUI deps). `opencv-contrib-python` is **not allowed** without case-by-case review (contrib modules have mixed GPL/patent licensing). |
| numba | BSD 2-Clause | JIT compilation for CPU-bound array operations (alternative to mlx on non-Apple-Silicon). Note: pulls in LLVM via llvmlite (~50-100MB install size). |
| bottleneck | BSD 2-Clause | Fast median/nanmedian via introselect algorithm — 2-3x faster than numpy for large arrays |
| mlx | MIT | Apple Metal GPU acceleration for array operations (Apple Silicon only). Used for stats and stretch computation |
| tifffile | BSD 3-Clause | TIFF reading/writing if DSLR or other TIFF sources are needed |
| imagecodecs | BSD 3-Clause | Codec extensions for tifffile — required for LZW, JPEG, and other compressed TIFF formats |
| requests | Apache 2.0 | HTTP client (astroquery dependency; useful for external APIs) |
| D3.js | ISC | Complex interactive charts (PHD2 guiding graph, session timeline) |
| py7zr | LGPL-2.1+ | 7z archive extraction. Pure Python, no external binaries. ⚠ LGPL — fine as Python import. At distribution time, bundle LICENSE file per LGPL §6. No runtime attribution required. |
| rawpy | MIT (wrapper) / LibRaw: LGPL-2.1 or CDDL-1.0 | Camera RAW file support. ⚠ rawpy wraps LibRaw (dual-licensed LGPL-2.1 or CDDL-1.0; we use LGPL option via pip-installed pre-built wheels, which exclude GPL demosaic packs). **Building rawpy or LibRaw from source with demosaic pack support is not permitted** under MIT. At distribution time, bundle LibRaw's LICENSE.LGPL. |

### Not Recommended

| Library | License | Reason |
|---|---|---|
| **xisf** (Python, by sergio-dr) | **GPL-3.0** | **Incompatible with MIT license.** We have a clean-room parser (`services/xisf_io.py`) instead. Do not adopt. |
| plotly | MIT | Redundant — already using D3.js for complex charts and MUI X Charts for simple ones. |
| matplotlib | BSD-compat | Not needed — all charts are frontend-rendered via D3.js / MUI X Charts. |
