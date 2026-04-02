# NightCrate — Implementation Plan

Living document tracking implementation status. Check off items as they are completed.

## Table of Contents

- [v0.1.0 — Foundation + FITS Viewer](#v010--foundation--fits-viewer) ✅
- [v0.2.0 — Enhanced FITS Viewer](#v020--enhanced-fits-viewer) ✅
- [v0.3.0 — XISF Support + Image I/O Refactor](#v030--xisf-support--image-io-refactor) ✅
- [v0.3.0a — UI Polish + Frontend Redesign](#v030a--ui-polish--frontend-redesign) ✅
- [v0.4.0 — PixInsight Project Browsing](#v040--pixinsight-project-browsing) ✅
- [v0.4.1 — Image Histogram](#v041--image-histogram)
- [v0.5.0 — Aberration Inspector](#v050--aberration-inspector)
- [Future Features to Consider](#future-features-to-consider)
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

## v0.5.0 — Aberration Inspector: Star Detection & Crop Grid

**Goal:** Detect and measure star shapes across a single astronomical image, display results in a zoned crop grid. The core feature that directly replaces N.I.N.A.'s basic 3x3 aberration inspector with a configurable, quantitative alternative.

**Status:** Planned

---

### New Dependencies

- `sep` (LGPL-3.0, already approved) — Source Extractor for star detection and shape measurement. Fast, gives eccentricity + position angle directly. **Requires attribution in README.**
- `photutils` (BSD 3-Clause, already approved) — fallback for 2D Gaussian/Moffat fitting if needed

### 1. Backend — Star Detection & Measurement

New service: `services/aberration.py`

- [ ] `detect_stars(fits_path, settings)` — detect stars using `sep`, measure per-star metrics
- [ ] Per-star output: x, y, FWHM, HFR, eccentricity, elongation_angle_deg, peak_adu, flux, SNR, semi_major, semi_minor
- [ ] Configurable filters: min_star_snr, max_star_peak_adu, min/max_star_fwhm_px, exclude_saturated
- [ ] Background subtraction via `sep.Background`
- [ ] Edge-of-frame exclusion

### 2. Backend — Zone Aggregation

- [ ] Group stars into configurable rectangular grid (3x3 through 9x9)
- [ ] Per-zone: median + mean + std of selected metric, median elongation angle, representative star selection
- [ ] Cheap re-gridding — no re-analysis needed when grid density changes

### 3. Backend — API Endpoints

New router: `api/aberration.py`

- [ ] `POST /api/aberration/analyze` — trigger analysis of a FITS frame, return star list + global stats
- [ ] `POST /api/aberration/zones` — compute zone-aggregated stats from prior analysis (re-gridding without re-analysis)
- [ ] `GET /api/aberration/crop` — return auto-stretched PNG crop around a specific star

### 4. Database — Analysis Storage

Migration: `aberration_analysis` and `aberration_stars` tables

- [ ] `aberration_analysis`: id, frame_id, created_at, image_width/height, settings_json, global stats, star_count
- [ ] `aberration_stars`: id, analysis_id, x, y, fwhm, hfr, eccentricity, elongation_angle_deg, peak_adu, flux, snr, semi_major, semi_minor
- [ ] Index on `(analysis_id)` for fast zone queries
- [ ] Results cached — re-opening previously analyzed frame is instant
- [ ] Cache TTL: configurable expiration (default 30 days), stored in settings table
- [ ] Startup cleanup: purge expired cache entries on app launch
- [ ] Settings UI: display cache size in MB + "Clear All" button to purge entire aberration cache
- [ ] API: `GET /api/aberration/cache/size` (returns bytes), `DELETE /api/aberration/cache` (purge all)

### 5. Frontend — Aberration Inspector Tab

New tab in the Image Viewer (alongside Image and Header tabs).

- [ ] "Aberration" tab in the image viewer tab bar
- [ ] Tab reuses the currently loaded file — no separate file selection
- [ ] Right sidebar becomes context-dependent: switches between image viewer controls (histogram, stats, pixel inspector) and aberration inspector controls depending on active tab

### 6. Frontend — Toolbar

- [ ] Grid density selector: 3x3, 4x4, 5x5, 7x7, 9x9 (default 5x5)
- [ ] Metric selector: eccentricity (default), FWHM, HFR, peak ADU, elongation angle

### 7. Frontend — Crop Grid View

- [ ] Grid of square tiles, one per zone
- [ ] Each tile: auto-stretched star crop (from `/crop`), metric value overlay, background color tint (viridis scale)
- [ ] Star count per zone in corner
- [ ] Click zone → expand in sidebar with full stats, star list, mini-histogram

### 8. Frontend — Right Sidebar (Aberration Context)

Replaces the image viewer's right sidebar content when the Aberration tab is active.

- [ ] Global stats: star count, median FWHM, median eccentricity, median HFR
- [ ] Zone detail (on hover/click): larger crop, full stats, star list, mini-histogram

### 9. Tests

- [ ] Star detection on synthetic test image
- [ ] Zone aggregation with known star positions
- [ ] API endpoint tests (analyze, zones, crop)

### v0.5.0 Completion Criteria

- [ ] Star detection produces correct metrics on real FITS sub frame
- [ ] Crop Grid view matches/exceeds N.I.N.A.'s aberration inspector
- [ ] Re-gridding is instant (no re-analysis)
- [ ] Previously analyzed frames load instantly from cache
- [ ] All visualizations use colorblind-safe palette (viridis)
- [ ] `uv run pytest` passes
- [ ] `npm run build` succeeds

---

## v0.5.1 — Aberration Inspector: Heatmap & Vector Field Views

**Goal:** Add spatial visualization modes to the aberration inspector — a color heatmap overlay and a vector field showing elongation direction/magnitude. These make optical aberration patterns immediately visible at a glance. No new backend logic — purely frontend views consuming existing v0.5.0 API data.

**Status:** Planned

---

### 1. Frontend — Toolbar Additions

- [ ] View mode toggle: Crop Grid | Heatmap | Vector Field
- [ ] Star filter controls (expandable): min/max SNR, max peak ADU, min/max FWHM, min stars per zone

### 2. Frontend — Heatmap View

- [ ] Full FITS frame (auto-stretched grayscale, downscaled for viewport)
- [ ] Semi-transparent color grid overlay (viridis colormap, per zone median of selected metric)
- [ ] Adjustable opacity slider (default ~40%)
- [ ] Color legend/scale bar
- [ ] Zone tooltip on hover

### 3. Frontend — Vector Field View

- [ ] Full frame background with arrow overlay
- [ ] One arrow per zone: direction = median elongation angle, length = median eccentricity
- [ ] Arrow color = eccentricity magnitude (viridis)
- [ ] Zones with eccentricity < 0.1 → small circles (round stars)
- [ ] Arrow scale legend

### 4. Tests

- [ ] Heatmap renders with correct zone colors for known metric values
- [ ] Vector field arrows match expected directions for synthetic star data

### v0.5.1 Completion Criteria

- [ ] Heatmap shows clear spatial pattern for tilted optics
- [ ] Vector Field shows parallel arrows for tilt, radial for coma
- [ ] View mode toggle switches cleanly between all three views
- [ ] Star filters update all views in real time
- [ ] All visualizations use colorblind-safe palette (viridis)
- [ ] `uv run pytest` passes
- [ ] `npm run build` succeeds

---

## v0.5.2 — Aberration Inspector: Diagnosis Engine & Export

**Goal:** Automated pattern-matching diagnosis that names the aberration (tilt, coma, field curvature, etc.) with confidence levels, plain-English explanations, and fix suggestions. Plus data export for offline analysis.

**Status:** Planned

---

### 1. Backend — Diagnosis Engine

- [ ] Pattern matching on the zone-aggregated vector field (eccentricity + elongation angle per zone)
- [ ] Diagnose: tilt, coma, astigmatism, field curvature, backspacing error, tracking/guiding error
- [ ] Per diagnosis: type, confidence (0-100%), plain-English description, fix suggestion
- [ ] "Ruled out" entries explaining why certain aberrations were excluded
- [ ] Logic:
  - Std of elongation angles < 15° → tilt or tracking
  - Eccentricity gradient across field → tilt
  - Eccentricity correlates with distance from center → field curvature or coma
  - Radial elongation directions → coma; tangential → field curvature
  - Uniform direction aligned with RA axis → tracking error

### 2. Backend — API Endpoint

- [ ] `POST /api/aberration/diagnose` — run pattern-matching diagnosis on zone data

### 3. Frontend — Right Sidebar Additions

- [ ] Diagnosis panel: cards with type, confidence bar, description, suggestion
- [ ] "Ruled out" section (collapsible)
- [ ] "How to read this" help tooltip

### 4. Frontend — Export

- [ ] Export: PNG screenshot, CSV per-star, CSV per-zone

### 5. Tests

- [ ] Diagnosis pattern matching (synthetic patterns for each aberration type)
- [ ] API endpoint test (diagnose)

### v0.5.2 Completion Criteria

- [ ] Diagnosis correctly identifies tilt in a known-tilted frame
- [ ] "Ruled out" explanations are coherent and helpful
- [ ] Export produces valid CSV with all expected columns
- [ ] PNG export captures current view accurately
- [ ] `uv run pytest` passes
- [ ] `npm run build` succeeds

---

---

## Future Features to Consider

Features that depend on cross-frame infrastructure or are beyond the current scope. Captured here for future planning.

### Multi-Frame Comparison (Aberration Inspector)

- **Frame-to-frame comparison:** Side-by-side vector fields or heatmaps from two frames (before/after tilt adjustment). Includes a difference view showing improvement vs. degradation per zone.
- **Filter comparison:** Aberration patterns across different filters from the same session to diagnose chromatic focus shift or filter-dependent tilt.
- **Session trend tracking:** Plot average corner eccentricity over time across sessions to catch slowly drifting mirrors or loosening tilt adapters.

### Interactive Tools (Aberration Inspector)

- **User annotations:** Pin notes to specific zones and persist them across sessions.
- **Interactive zone drawing:** Drag/resize custom zones instead of a fixed rectangular grid for fine-grained investigation of specific field regions.

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
