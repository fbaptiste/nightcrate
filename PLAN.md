# NightCrate — Implementation Plan

Living document tracking implementation status. Check off items as they are completed.

## Table of Contents

- [v0.1.0 — Foundation + FITS Viewer](#v010--foundation--fits-viewer) ✅
- [v0.2.0 — Enhanced FITS Viewer](#v020--enhanced-fits-viewer) ✅
- [v0.3.0 — XISF Support + Image I/O Refactor](#v030--xisf-support--image-io-refactor) (in progress)
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
- [x] Identified GPL blockers: `xisf` (Python) and `PyQt6` — documented alternatives

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

**Status:** In progress

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

### 5. Refactor Image I/O Layer (planned)

Currently all image loading, stretching, stats, and rendering live in `services/fits.py`. Before adding XISF, split this into a clean architecture:

```
services/
├── imaging.py       # Shared: normalize, stretch, stats, render_image_png
├── fits_io.py       # FITS-specific: load data, read headers, list extensions
└── xisf_io.py       # XISF-specific: parse format, load data, read metadata
```

#### 1.1 Create `services/imaging.py`

Move format-agnostic code out of `services/fits.py`:

- [ ] `_normalize_to_01()` — data-type-based normalization
- [ ] `_mtf()`, `_stretch_plane()`, `_compute_stf()` — stretch engine
- [ ] `StretchParams`, `StfParams`, `ChannelStats`, `ImageStats` — data classes
- [ ] `get_image_stats()` — compute per-channel stats from a normalized array
- [ ] `render_image_png()` — apply stretch and encode PNG from a normalized array

All functions in `imaging.py` accept normalized [0, 1] float64 arrays — they have no knowledge of FITS or XISF.

#### 1.2 Create `services/fits_io.py`

Move FITS-specific code from `services/fits.py`:

- [ ] `load_image_data(path, hdu) → np.ndarray` — returns normalized [0, 1] array, shape (H, W) or (3, H, W)
- [ ] `read_header(path, hdu) → list[dict]` — returns `{key, value, comment}` dicts
- [ ] `list_extensions(path) → list[dict]` — returns extension summary (index, name, type, has_image)

#### 1.3 Delete `services/fits.py`

- [ ] Remove after all code has been migrated to `imaging.py` and `fits_io.py`
- [ ] Update imports in `api/fits.py`

### 6. XISF Clean-Room Parser

Write a read-only XISF parser based on the open XISF 1.0 specification. No dependency on the GPL `xisf` Python package.

#### 6.1 Add Dependencies

- [ ] `lz4` (BSD 3-Clause) — for LZ4/LZ4-HC decompression
- [ ] `zstandard` (BSD 3-Clause) — for Zstandard decompression
- [ ] Both already on the approved library list in this document
- [ ] Update `README.md` Open Source Acknowledgments

#### 6.2 Create `services/xisf_io.py`

##### File header parsing

- [ ] Validate magic bytes (`XISF0100` at offset 0)
- [ ] Read XML header length (uint32 LE at offset 8)
- [ ] Parse XML header block (UTF-8, namespace `http://www.pixinsight.com/xisf`)

##### Image data loading

- [ ] Parse `<Image>` element: `geometry` (W:H:C), `sampleFormat`, `colorSpace`, `location`, `compression`
- [ ] Support sample formats: `UInt16`, `Float32` (covers >95% of astrophotography files)
- [ ] Support color spaces: `Gray` (mono), `RGB` (planar channel layout: RRR...GGG...BBB)
- [ ] Read attachment data at absolute file offset
- [ ] Decompression: uncompressed, `zlib`, `lz4`, `lz4-hc`, `zstd` (with and without `+sh` byte shuffling)
- [ ] Sub-block reading: 16-byte headers (compressed_size uint64 LE, uncompressed_size uint64 LE) per chunk
- [ ] Byte unshuffle via numpy reshape/transpose
- [ ] Normalize to [0, 1]: UInt16 ÷ 65535, Float32 assumed already [0, 1] (or ÷ max if > 1)
- [ ] Return normalized array shaped (H, W) for Gray or (3, H, W) for RGB

##### Metadata extraction

- [ ] Parse `<FITSKeyword>` elements → `{key, value, comment}` dicts (same format as FITS headers)
- [ ] Parse `<Property>` elements → extract key properties (scalar `value` attributes + inline base64 `String` type)
- [ ] Map XISF properties to display fields: `Instrument:Filter:Name` → filter, `Instrument:ExposureTime` → exposure, `Observation:Time:Start` → capture date

##### Extension listing

- [ ] `list_extensions(path) → list[dict]` — list all `<Image>` elements with id, geometry, sampleFormat, colorSpace, has_image
- [ ] Most files have one primary image + optional thumbnail; show only image-bearing extensions

##### Deferred (not in v0.3.0)

- Complex32/Complex64, UInt8, UInt32, Float64 sample formats
- Inline base64 image data, external URL locations
- Writing XISF files
- Vector/Matrix property types

### 7. Unified API Layer

#### 7.1 Update `api/fits.py` → dispatch by file type

- [ ] Rename to `api/images.py` (or keep as `api/fits.py` and add XISF routing)
- [ ] Accept both `.fits/.fit/.fts` and `.xisf` extensions in path validation
- [ ] Dispatch to `fits_io` or `xisf_io` based on file extension
- [ ] All endpoints (`/image`, `/stats`, `/header`, `/hdus`) work identically for both formats

#### 7.2 Update file browser

- [ ] Show `.xisf` files alongside FITS files in the browse dialog
- [ ] Update backend `FITS_EXTENSIONS` set to include `.xisf`

#### 7.3 Update info bar

- [ ] XISF files that contain `<FITSKeyword>` elements work automatically (same key names)
- [ ] For XISF files without FITS keywords, fall back to XISF properties: `Observation:Time:Start` → date, `Instrument:ExposureTime` → exposure, `Instrument:Filter:Name` → filter

#### 7.4 Update help text and labels

- [ ] File path placeholder: "Absolute path to .fits or .xisf file…"
- [ ] Browse dialog title: "Open Image File"

### 8. Recent Files

- [ ] Track the last 100 opened files in the SQLite database (path, timestamp)
- [ ] Add a dropdown to the file path input in the FITS Viewer toolbar — shows recent files ordered most recent first
- [ ] Selecting a recent file opens it immediately
- [ ] Prune entries beyond 100; remove entries for files that no longer exist on disk

### 9. Standard Image Format Support (PNG, JPEG, TIFF)

- [ ] Backend: load PNG, JPEG, and TIFF files via Pillow (already a dependency)
- [ ] Serve the image directly as PNG to the frontend (no stretch applied — these are already display-ready)
- [ ] Extract and display any available metadata (EXIF for JPEG/TIFF, PNG text chunks) in the header table
- [ ] Display metadata in the info bar where applicable (filename always shown; date/exposure/filter if present in EXIF)
- [ ] Zoom/pan works identically to FITS/XISF
- [ ] Stretch controls panel is hidden when viewing PNG/JPEG/TIFF (not applicable)
- [ ] File browser shows `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff` alongside FITS and XISF files
- [ ] Update `IMAGE_EXTENSIONS` set in backend and file path validation

### v0.3.0 Completion Criteria

- [x] Settings stored in SQLite (single-file app state)
- [x] Cross-platform: app data directory, file browser volumes, GPU detection
- [x] Asinh stretch removed; Linear is simple min/max with no controls
- [x] 59 unit tests passing; bandit security scanning added
- [x] Pre-commit checklist enforced: ruff lint → ruff format → bandit → pytest
- [ ] Existing FITS functionality works identically after I/O refactor (no regressions)
- [ ] XISF files (uncompressed, zlib, lz4, zstd — with and without shuffling) open and display correctly
- [ ] Auto-stretch (STF) works on XISF files
- [ ] Mono and color XISF files both supported
- [ ] XISF metadata (FITS keywords and/or XISF properties) displayed in header table and info bar
- [ ] File browser shows both FITS and XISF files
- [ ] Recent files dropdown shows last 100 opened files
- [ ] PNG, JPEG, TIFF files open with zoom/pan and metadata but no stretch controls
- [ ] `uv run ruff check .` passes
- [ ] `uv run ruff format --check .` passes
- [ ] `uv run bandit -r src/` passes
- [ ] `uv run pytest` passes (add tests for XISF parser)
- [ ] `npm run build` succeeds

---

## Appendix: Library Reference

Evaluated libraries for potential use across NightCrate. Every library must pass a license review before inclusion — NightCrate is a **commercial closed-source product**, so GPL-licensed code is not permitted.

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

### Not Recommended / Blocked

| Library | License | Reason |
|---|---|---|
| **PyQt6** | **GPL-3.0** | Requires paid Riverbank Computing commercial license for closed-source distribution. Not needed — NightCrate uses pywebview/Tauri. |
| **xisf** (Python, by sergio-dr) | **GPL-3.0** | Cannot use in closed-source commercial product. XISF format support is important (PixInsight native format) — will need a custom parser based on the open XISF specification instead. |
| pyqtgraph | MIT | License is fine, but depends on PyQt6 which is GPL. Also moot — not using Qt. |
| plotly | MIT | License is fine, but redundant — already using D3.js for complex charts and MUI X Charts for simple ones. |
| matplotlib | BSD-compat | License is fine, but not needed — all charts are frontend-rendered via D3.js / MUI X Charts. |
