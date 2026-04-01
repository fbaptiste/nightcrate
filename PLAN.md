# NightCrate — Implementation Plan

Living document tracking implementation status. Check off items as they are completed.

## Table of Contents

- [v0.1.0 — Foundation + FITS Viewer](#v010--foundation--fits-viewer) ✅
- [v0.2.0 — Enhanced FITS Viewer](#v020--enhanced-fits-viewer) ✅
- [v0.3.0 — XISF Support + Image I/O Refactor](#v030--xisf-support--image-io-refactor) ✅
- [v0.3.0a — UI Polish + Frontend Redesign](#v030a--ui-polish--frontend-redesign) ✅
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
- [x] License changed to GPL-3.0: added LICENSE file, updated dependency policy in CLAUDE.md and PLAN.md

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

*v0.4.0 scope to be defined.*

---

## Appendix: Library Reference

Evaluated libraries for potential use across NightCrate. Every library must pass a license review before inclusion. NightCrate is licensed under **GPL-3.0**. GPL dependencies are now technically compatible but should still be evaluated case by case — we prefer permissive dependencies where possible.

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
| Vite | MIT | Frontend build tooling |
| TypeScript | Apache 2.0 | Frontend type system |

### Approved for Future Use

All licenses verified as commercial-compatible. Add via `uv add` (backend) or `npm install` (frontend) when needed.

| Library | License | Potential Role |
|---|---|---|
| scipy | BSD 3-Clause | Signal processing (PHD2 RMS stats, autofocus curve fitting) |
| pandas | BSD 3-Clause | PHD2 log parsing (CSV-like), session statistics tabulation |
| astroquery | BSD 3-Clause | Simbad/MAST queries for object info, catalog cross-matching |
| photutils | BSD 3-Clause | Source detection, background estimation, FWHM/HFR measurement for sub quality |
| astroalign | MIT | Image registration/alignment for stacking prep |
| sep | LGPL-3.0 | Source extraction, star detection, quality metrics. ⚠ LGPL — OK as Python import (dynamic linking), **requires attribution** |
| reproject | BSD 3-Clause | WCS reprojection for overlaying images from different rigs/orientations |
| psutil | BSD 3-Clause | System resource monitoring (CPU cores, memory for worker management) |
| lz4 | BSD 3-Clause | Fast compression for caching processed image data |
| zstandard | BSD 3-Clause | Higher-ratio compression for archiving/caching |
| pywavelets (pywt) | MIT | Wavelet-based noise reduction/sharpening |
| opencv-python | Apache 2.0 | Image processing, quality analysis |
| numba | BSD 2-Clause | JIT compilation for CPU-bound array operations (alternative to mlx on non-Apple-Silicon) |
| tifffile | BSD 3-Clause | TIFF reading/writing if DSLR or other TIFF sources are needed |
| requests | Apache 2.0 | HTTP client (astroquery dependency; useful for external APIs) |
| D3.js | ISC | Complex interactive charts (PHD2 guiding graph, session timeline) |
| rawpy | MIT (wrapper) / LibRaw: LGPL-2.1 or CDDL-1.0 | Camera RAW file support. ⚠ LibRaw LGPL — OK via dynamic linking in Python wheels. **Requires attribution.** Note: GPL demosaic packs excluded from standard builds. |

### Not Recommended

| Library | License | Reason |
|---|---|---|
| **xisf** (Python, by sergio-dr) | **GPL-3.0** | License is now compatible, but we already have a clean-room parser (`services/xisf_io.py`). Evaluate before adopting — needs case-by-case approval for GPL deps. |
| plotly | MIT | Redundant — already using D3.js for complex charts and MUI X Charts for simple ones. |
| matplotlib | BSD-compat | Not needed — all charts are frontend-rendered via D3.js / MUI X Charts. |
