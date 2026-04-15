# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Active development. See `PLAN.md` for the current version plan and task checklist.

Reference documents:
- `nightcrate-brief.md` — product vision, MVP features, architecture decisions
- `NightCrate_Equipment_and_Technical_Context.md` — Fred's imaging setup, file formats, FITS headers, PHD2 log structure, known edge cases

## Planned Stack

- **Backend:** Python + FastAPI
- **Frontend:** React + TypeScript (Vite); Claude Code handles most React/JS work — Fred is not a React developer
  - **UI library:** MUI (`@mui/material`) — free MIT core. MUI X Community tier only (`@mui/x-data-grid`, `@mui/x-date-pickers`, `@mui/x-charts`, `@mui/x-tree-view`) — all free MIT. **Never use MUI X Pro or Premium** (paid commercial license).
  - **Theme:** MUI `ThemeProvider` with light/dark/browser (system) modes. Stored in SQLite settings table via backend.
  - **No Tailwind CSS, shadcn, or related packages** — MUI uses its own styling system (`sx` prop + `styled`). Do not add `tailwind-merge`, `class-variance-authority`, `clsx`, `lucide-react`, or `@base-ui/react`.
  - **State:** Zustand
  - **Data fetching:** TanStack Query
  - **Charts:** D3.js for complex interactive charts (PHD2 guiding graph, session timeline); MUI X Charts (free) for simpler dashboards (integration time bars, altitude).
- **Database:** SQLite accessed directly via `aiosqlite` (raw SQL, no ORM). Migrations managed with `yoyo-migrations` (SQL files in `db/migrations/`). **No SQLAlchemy.**
- **Data models:** Pydantic only — for API shapes, domain objects, and settings. No ORM models.
- **Desktop:** Phase 1 = local web app (FastAPI serves React, accessed via browser or pywebview); Phase 2 = Tauri wrapper if needed
- **Key Python libs:** `astropy`, `astroquery`, `lz4`, `zstandard`, `defusedxml`, ASTAP/astrometry.net for plate solving
- **Async ingestion:** asyncio task queue + `ProcessPoolExecutor` for CPU-bound FITS parsing (parallelizes across cores; SQLite writes stay on main process)
- **GPU acceleration:** `mlx` (Apple Metal, Apple Silicon) or `cupy` (NVIDIA CUDA, Windows/Linux) with numpy as CPU fallback. All array operations go through a thin `compute` backend module — callers never reference mlx/numpy/cupy directly.
- **User settings:** `gpu_acceleration` (bool) and `max_worker_cores` (int, `null` = `cpu_count - 1`) are user-configurable at runtime. Settings stored in the SQLite database (`settings` table, single JSON row).

Desktop packaging rationale: Electron rejected (100MB+ bundle size); Tauri is the future native wrapper option using OS-native webview.

## Architecture

The app is a **cross-platform local-first desktop application** (Mac, Windows, Linux). The backend handles all computation — FITS parsing, log ingestion, plate solving, file management. The frontend is a React UI.

**Cross-platform:** App data directory via `platformdirs` (Mac: `~/Library/Application Support/NightCrate`, Windows: `AppData/Local/NightCrate`, Linux: `~/.local/share/NightCrate`). File browser detects volumes per platform. GPU backend auto-detects mlx (Mac) or CuPy (Windows/Linux).

**Core data flow:** Imaging data captured on Windows PCs → transferred to Mac → NightCrate ingests and catalogs → PixInsight for processing.

**Key domain hierarchy:** Equipment Profile → Project → Session (single night) → Sub Frame

**Calibration frame matching keys:**
- Darks: camera + gain + sensor temperature + exposure + binning
- Flats: camera + gain + filter + binning (+ rotator angle ideally)
- Bias: camera + gain + binning

## Domain Knowledge

**Two imaging rigs run simultaneously:**
- Rig 1 (C11): N.I.N.A. + PHD2 on Windows mini-PC, ZWO ASI 2600MM Pro, Optolong 7nm narrowband + ZWO LRGB
- Rig 2 (Askar V): ASIAIR controller + PHD2, ZWO ASI 2600MM Pro, Antlia 3nm narrowband + Optolong LRGB

**Ingestion sources with different formats:**
- N.I.N.A. session logs (text) + autofocus JSON files
- ASIAIR logs (format TBD — needs research)
- PHD2 guiding logs (CSV-like, timestamped, single file spanning full night)
- FITS headers (standard keywords + N.I.N.A.-specific `NINA-` prefixed extensions)

**FITS header parsing priority keywords:** `OBJECT`, `FILTER`, `EXPTIME`, `GAIN`, `CCD-TEMP`, `INSTRUME`, `TELESCOP`, `DATE-OBS`, `IMAGETYP`, `RA`/`OBJCTRA`, `DEC`/`OBJCTDEC`

**PHD2 association:** Match guiding data to subs by timestamp. One PHD2 log file may cover multiple targets across a full night.

**Known edge cases to handle:**
- Multi-night projects are the norm (same target imaged across weeks/months)
- Dual-rig simultaneous imaging of same or different targets — never conflate rigs
- Filter name inconsistency across software: normalize "Lum"/"L"/"Luminance", "Ha"/"H-alpha", etc.
- Partial/interrupted sessions due to weather are normal, not errors
- Data may live on local SSD, NAS (Synology), or mounted volumes — handle paths flexibly
- Calibration frames (darks/bias) often reused across many sessions

## UI/UX Requirements

- **Color-blind-friendly palette required** — Fred is red-green color blind. Use blue/orange instead of red/green; add pattern/shape differentiation where color alone would be used.
- Catalog by reference (don't move files) is the default. File reorganization/copy is optional.

## Python Tooling

- **Python version:** 3.14
- **Package manager / venv:** `uv` — use `uv add <pkg>` to add deps, `uv run <cmd>` to run inside venv, `uv sync` after pulling changes
- **Linter/formatter:** `ruff` (replaces flake8, black, isort — single tool, configured in pyproject.toml)
- **Testing:** `pytest`
- **Migrations:** `yoyo-migrations` — SQL files in `backend/src/nightcrate/db/migrations/`, applied automatically on startup via `db/migrations.py`

## Commands

From the repo root, use `make`:

```bash
make dev       # Start backend + frontend together; browser opens automatically; Ctrl+C stops both
make backend   # Backend only (http://127.0.0.1:8000)
make frontend  # Frontend only (http://localhost:5173)
make install   # Sync all deps after pulling changes
make lint      # ruff check
make format    # ruff format
make test      # pytest
```

Direct commands when needed:
```bash
# Backend (from backend/)
uv run uvicorn nightcrate.main:app --reload --port 8000
uv run pytest                          # Run tests
uv run ruff check src/ tests/          # Lint
uv run ruff format src/ tests/         # Format
uv run bandit -r src/                  # Security scan

# Migrations: applied automatically on startup.
# To add a new migration: create backend/src/nightcrate/db/migrations/NNNN.description.sql
```

## Pre-Commit Checklist

Before committing, all applicable checks must pass:

**Backend (from `backend/`):**
1. `uv run ruff check src/ tests/` — lint
2. `uv run ruff format --check src/ tests/` — formatting
3. `uv run bandit -r src/` — security
4. `uv run pytest` — tests

**Frontend (from `frontend/`):**
5. `npm run build` — TypeScript compilation + production build

## Gotchas

- **Python 3.14 + ruff format:** ruff format may strip parentheses from `except (ValueError, IndexError):` turning it into the Python 2 syntax `except ValueError, IndexError:`. This is a known ruff issue with `target-version = "py314"`. Avoid multi-exception `except` clauses, or rewrite to avoid the pattern (e.g., use a single base exception or restructure the logic).

## Image Viewer

Supported formats: FITS (`.fits/.fit/.fts`), XISF (`.xisf`), PixInsight projects (`.pxiproject`), PNG, JPEG, TIFF (including float32 TIFF).

**Architecture:**
- `services/imaging.py` — format-agnostic: normalization, stretch, stats, histogram, Lab a*, PNG rendering
- `services/fits_io.py` — FITS loading via astropy
- `services/xisf_io.py` — clean-room XISF parser (no GPL dependency). Supports sub-block and single-stream compression (zlib, lz4, lz4-hc, zstd ± byte shuffle)
- `services/pxiproject_io.py` — PixInsight project parser (XOSM manifest + rawimage swap format)
- `services/standard_io.py` — PNG/JPEG/TIFF via Pillow + tifffile for float32 TIFFs
- `api/images.py` — unified API at `/api/images/*`, dispatches by file type. Virtual paths (`project::index`) for pxiproject images.

**Auto Stretch** (PixInsight-compatible Screen Transfer Function):
- Uses **avgDev** (average deviation), NOT MAD, for shadow clip computation
- Shadow clip: `median + (-1.25) * avgDev`
- Midtones balance via MTF self-inverse: `m = MTF(b0, TARGET_BG)` where `b0 = median - shadow_clip`
- Linked color mode: averages shadow clip and median across all channels
- Target background: 0.25 (standard PixInsight default)
- Non-linear images auto-detected (STF midtone >= 0.1) and shown without stretch
- Backend-driven `supports_stretch` flag on `/extensions` endpoint
- `stretch=auto` mode: backend computes stats, determines linearity, and applies STF in a single request — frontend sends one request on file open instead of sequential round trips
- Frontend uses `stretch: "auto"` as default; sliders populated from stats when they arrive; user slider interaction switches to explicit `stretch: "stf"` params

**Histogram:**
- Canvas-based rendering below image (filled area curves, not SVG bars)
- R/G/B/Luminosity channels with channel checkboxes
- Log/linear scale (auto-defaults based on image linearity)
- Stretch indicator lines on slider interaction (auto-hide after 3s)
- Channel intensity bars for color images (normalized to max channel)

**Pixel Inspector:**
- Client-side sampling via offscreen canvas (zero API calls on hover)
- R/G/B/K values, hex color, XKCD named color (949 colors, CC0)
- Magnified patch preview with adjustable zoom
- Amber reticle cursor with black outline for contrast

**Statistics:**
- Per-channel: median, MAD, avgDev, SNR (median/σ), background delta
- CIE L*a*b* a* median for color balance (neutral/warm excess/cool excess)
- Image Info section with curated FITS keywords

**Important implementation notes:**
- All hex color constants must be 6-digit (#888888, never #888) — canvas gradient code appends alpha suffixes
- Channel colors defined in `lib/channelColors.ts` (single source of truth)
- Luminance weights (`LUM_R/G/B`) defined in `services/imaging.py`
- Stretch is applied server-side — frontend sends stretch params as query parameters and receives a rendered PNG
- `core/compute.py` (`get_array_module()`) provides GPU abstraction — used in `_channel_stats()` and `stretch_plane()` for mlx/cupy acceleration. Settings toggle applies immediately via `set_gpu_enabled()`
- `bottleneck.nanmedian()` used as CPU fallback for faster median computation (2-3x vs numpy)
- Histogram subsampled to ~2M pixels for large images (statistically identical for 256 bins)
- PNG encoding uses `compress_level=1` (fastest) — local app, speed over file size
- Per-key locking on image data and stats caches prevents redundant computation from concurrent requests
- Archive (BytesIO) paths use a cache key `(archive_path, mtime, entry_path)` to share the same caching and locking as regular files

**Header Editing:**
- FITS files only (not XISF, standard, archive, or pxiproject virtual paths)
- `PATCH /api/images/header` — batch operations (update, add, delete) validated and applied atomically
- `fits_io.update_header()` uses `mode="update"` + `flush()` for efficient in-place writes (no full file rewrite)
- Structural keywords (`SIMPLE`, `BITPIX`, `NAXIS*`, `EXTEND`, `BZERO`, `BSCALE`, `COMMENT`, `HISTORY`, `END`) are protected — cannot be edited or deleted
- `STRUCTURAL_KEYWORDS` canonical definition in `fits_io.py`, imported by `images.py`
- Frontend: toggle edit mode in `FitsHeaderTable`, inline cell editing, add/delete with undo, save/discard

## Activity Console

In-app request timing viewer for performance analysis.

**Architecture:**
- `api/diagnostics.py` — ASGI middleware (`RequestTrackingMiddleware`) records every request with start timestamp, duration, status, and activity label
- `components/ActivityConsole.tsx` — dialog showing requests grouped by activity, with expandable detail tables
- `api/diagnostics.ts` — frontend API client

**Key details:**
- Activity label propagated via `X-Activity` header (for `fetch()` calls) or `_activity` query param (for `<img src>` calls)
- Image requests use a stable `_activity` label set once on file open (doesn't change on tab switch) to avoid URL cache-busting
- Timestamps show request START time (not completion time)
- `total_duration_ms` is sum of individual request durations, not wall-clock elapsed time
- Diagnostics requests (`/api/diagnostics/*`) are excluded from tracking

## Aberration Inspector

Analyses star shapes across the field to diagnose optical aberrations (tilt, coma, field curvature). Tab in the image viewer.

**Architecture:**
- `services/aberration.py` — star detection via `sep`, sample grid computation, isolated star filtering
- `api/aberration.py` — REST endpoints for analyze, samples, crop, cache management
- `db/migrations/0004.aberration_cache.sql` — SQLite cache for analysis results (TTL-based)
- Frontend: `components/aberration/` — CropGrid, AberrationToolbar, AberrationSidebar, ZoneOverlayMap
- `components/SidebarSection.tsx` — shared collapsible section component (used by both image viewer and aberration sidebar)

**Star Detection:**
- Uses `sep` (Source Extractor) for extraction + `sep.flux_radius` for HFR
- Filters: min SNR, min/max FWHM, max semi-major (extended object rejection), sep blending flag, min neighbor separation
- All filters user-adjustable via toolbar sliders, debounced 500ms
- Different filter settings = different cache key

**Sample Grid:**
- Evenly-spaced squares (not full-coverage tiling) — `image_width / (samples_across * 1.5)` square size
- Per-square metrics aggregated from all isolated stars within the region
- Squares draggable in reference thumbnail with client-side re-aggregation (no backend call)
- Drag constrained to row/column lane via midpoint boundaries

**Tile Preview:**
- Centered popup with auto-stretched region crop
- SVG overlay: rotated ellipses (eccentricity), dotted direction lines (elongation angle), eccentricity labels
- Star hover tooltip with zoomed crop + per-star metrics

**Caching:**
- Analysis results stored in `aberration_analysis` + `aberration_stars` tables
- Cache key: (file_path, hdu, settings_json)
- TTL: `aberration_cache_ttl_days` setting (default 30), cleanup on startup
- Settings page: cache size display + Clear All button

## Archive Browser

Supports browsing into archive files as if they were folders. Selecting an image inside an archive extracts it in-memory and loads it through the standard image pipeline.

**Supported formats:** zip, tar, tar.gz, tar.bz2, tar.zst, 7z

**Architecture:**
- `services/archive_io.py` — format dispatch (zip/tar/7z), TOC listing, in-memory extraction to BytesIO
- `api/files.py` — `browse-archive` endpoint, archive detection in directory browse
- `api/images.py` — archive branch in `_resolve_path()` for `::` virtual paths
- I/O services (`fits_io`, `xisf_io`, `standard_io`) accept `Path | BinaryIO`

**Virtual paths:** `{archive_path}::{entry_path}` (same `::` separator as pxiproject)

**In-memory extraction:** No temp files for zip/tar. 7z uses a temporary directory (py7zr API limitation) but cleans up immediately.

## Equipment Database

Fully normalized equipment schema (migrations `0005.equipment_schema.sql` + `0006.camera_guide_sensor.sql`).

**Reference docs:**
- `DB_SCHEMA.md` — Mermaid ER diagrams broken into logical groups
- `DB_SCHEMA_DDL.sql` — authoritative CREATE TABLE statements

**Architecture:**
- 10 lookup/reference tables: `manufacturer`, `optical_design`, `mount_type`, `connection_interface`, `connector_size`, `filter_size`, `form_factor`, `focuser_type`, `filter_type`, `seed_loader_meta`
- 12 equipment tables: `sensor`, `camera`, `telescope`, `telescope_configuration`, `filter`, `mount`, `focuser`, `filter_wheel`, `oag`, `guide_scope`, `computer`, `software`
- 5 junction tables: `camera_interface`, `telescope_connector`, `mount_interface`, `focuser_interface`, `filter_wheel_interface`
- 2 child tables: `filter_passband`, `filter_size_option`
- 4 FITS alias tables: `camera_alias`, `telescope_alias`, `filter_alias`, `unresolved_equipment_observation`
- 1 view: `filter_summary`
- 1 domain table: `location` (migration 0007 — user imaging locations, not seed-tracked)

**Key design decisions:**
- No custom_fields JSON — add real columns via migration when needed
- `filter_type` is a user-extensible vocabulary of roles (narrowband_single, broadband_color, etc.) with `display_name` for UI; wavelengths live in `filter_passband` on the physical filter
- `filter` represents an abstract product; physical sizes live in the `filter_size_option` child table (one row per available size with `mounted_thickness_mm`)
- `telescope` carries identity only (aperture, design) — all focal length/ratio/back_focus on `telescope_configuration`. Every telescope must have one config with `is_native=1`
- `camera` has `effective_full_well_ke`, `effective_read_noise_lcg_e`, `effective_read_noise_hcg_e`, `effective_peak_qe_pct`, `hcg_threshold_gain` for vendor-tuned specs that override sensor baseline values
- Every equipment table has seed tracking columns: `created_at`, `updated_at`, `active`, `source`, `seed_key`, `seed_hash`
- `updated_at` triggers auto-fire on every equipment table
- Partial unique index on `seed_key WHERE NOT NULL` for seed loader support
- Closed vocabularies enforced by CHECK constraints: `filter_passband.line_name`, `software.category`, `connection_interface.category`, `sensor.sensor_type`, `sensor.bayer_pattern`

## Equipment Management API

Full CRUD API for all equipment types under `/api/equipment/`.

**Architecture:**
- `api/equipment_models.py` — Pydantic Create/Update/Response models for all types
- `api/equipment.py` — single router with all CRUD endpoints
- Helpers: `_row_to_dict`, `_bool_fields`, `_get_or_404`, `_strip_seed`, `_build_*_response` per complex type
- Soft delete: DELETE sets `active=0`, list endpoints accept `?include_retired=true`
- Seed tracking columns stripped from all responses via `_SEED_KEYS` constant

**Endpoints per type:**
- 10 lookup tables: 5 endpoints each (list, get, create, update, soft-delete)
- `sensor`, `camera`, `mount`, `focuser`, `filter_wheel`, `oag`, `guide_scope`, `computer`, `software`: 5 endpoints each
- `telescope`: 5 endpoints + 3 child endpoints for configurations (create, update, delete)
- `filter`: 5 endpoints + 3 child endpoints for passbands + 3 child endpoints for size options (create, update, delete)

**Frontend Equipment page:**
- `pages/EquipmentPage.tsx` — two-panel layout with TreeView sidebar + content area
- `components/equipment/EquipmentSidebar.tsx` — grouped categories (Imaging, Optics, Tracking, Accessories, Computing, Reference)
- `components/equipment/EquipmentList.tsx` — generic list component handling DataGrid, state, delete confirmation for all types
- Per-type thin list wrappers (`CameraList`, `SensorList`, `MountList`, etc.) define columns and wire EquipmentList to their form dialog
- Per-type form dialogs (`CameraFormDialog`, `SensorFormDialog`, etc.) — each uses the generic `{ open, item, onClose, onSaved }` interface
- `components/equipment/LookupTablesPanel.tsx` — accordion UI with inline CRUD for all lookup tables
- `components/equipment/shared/` — ManufacturerPicker, SensorPicker, LookupPicker, InterfaceMultiSelect, ConfirmDeleteDialog, DetailField, ExternalLink, SensorLink
- `lib/formUtils.ts` — shared `parseOptionalFloat`, `parseOptionalInt`, `formatFilterType`, `formatSnakeCase`
- `api/equipment.ts` — TypeScript interfaces + fetch functions for all equipment types
- All form dialogs show error feedback via Snackbar on save failure

## Equipment Seed Loader

Populates the equipment database from CSV seed files on first run, with hash-based change detection on re-seed.

**Architecture:**
- `seed_loader/hash.py` — deterministic SHA-256 hash (contract v1, versioned — never change without migration)
- `seed_loader/registry.py` — `SeedableTable` dataclass registry, 31 tables in dependency load order
- `seed_loader/csv_reader.py` — CSV parsing with header validation, comment support, FK seed_key resolution
- `seed_loader/loader.py` — core: first_run/update modes, FK resolution via in-memory map, re-seed decision logic, junction/child handling, orphan detection, single-transaction
- `seed_loader/__main__.py` — CLI: `python -m nightcrate.seed_loader --db <path> --csv-root <path> [--dry-run] [--json]`
- `seed_loader/models.py` — SeedReport, TableReport, SeedError dataclasses
- `data/seed/*.csv` — 31 CSV files (one per seedable table)
- Runs automatically on app startup after migrations (sync sqlite3 connection, non-fatal)
- filter_type rows loaded from CSV, NOT from migration (no equipment data in migrations)

**Re-seed rules:** never overwrites `source='user'` rows or user-modified seed rows (detected by hash mismatch). Junction tables delete-and-reinsert only for parents that were inserted/updated.

## Admin Page — Database Management

Multi-database support with first-run setup wizard and hot-swap.

**Architecture:**
- `core/app_config.py` — reads/writes `config.json` in platformdirs app dir. Tracks known databases (path → name) + active DB path.
- `db/session.py` — dynamic `DB_PATH` via `get_db_path()` / `set_db_path()`. `get_db()` resolves path on each call.
- `db/migrations.py` — `apply_migrations(db_path=None)` accepts optional path for initializing new DBs.
- `api/admin.py` — endpoints: `/api/admin/info`, `/api/admin/status`, `/api/admin/database/create`, `/api/admin/database/add`, `/api/admin/database/activate`, `/api/admin/database/setup`, `DELETE /api/admin/database` (with `?delete_file=true` option), `/api/admin/browse`, `/api/admin/shortcuts`, `/api/admin/mkdir`
- `/api/health` returns `db_configured: bool` — frontend uses this to decide wizard vs normal app
- Frontend: `SetupWizard.tsx` (three scenarios: fresh, available DBs, all unavailable), `AdminPage.tsx` (app info + DB management), folder browser with Home/Documents/App Data shortcuts + new folder

**Key behaviors:**
- First startup with no config → setup wizard
- Active DB unavailable but others available → wizard offers activation
- DB switch: `set_db_path()` + `window.location.reload()` — no backend restart needed
- Remove can optionally delete the file (irreversible)

## Weather Forecast

7-day imaging quality forecast with hourly detail for imaging session planning.

**Architecture:**
- `services/weather.py` — Open-Meteo forecast client (standard API + ECMWF for PWV + Air Quality for AOD). `SupplementaryData` dataclass for PWV/AOD time-series. `nearest_match()` for aligning 3-hourly AOD to hourly weather timestamps.
- `services/astronomy.py` — astropy-based moon, twilight, darkness. All event fields `Optional` for polar latitude safety. `compute_moon_polyline()` for 10-min altitude sampling.
- `services/seeing.py` — surface model (JAG Lab) + wind-shear model (Trinquet/Cherubini). Blended 60/40 when pressure-level data available.
- `services/transparency.py` — three-tier scoring (PWV+AOD+humidity+visibility → fallback → degraded)
- `services/dew.py` — temperature-dew point spread classification + safe window computation
- `services/imaging_quality.py` — composite score with weighted sky clarity (cloud layers), cloud gating factor, transparency, seeing, moon, wind calm
- `api/weather.py` — forecast/hourly/methodology endpoints, supplementary data cache with non-fatal writes
- `api/weather_models.py` — Pydantic response models
- `db/migrations/0008.weather_cache.sql` — cache table (forecast/archive/openmeteo_aq/ecmwf_pwv sources)

**Imaging Quality Weights:**
- Broadband (moon included): Sky 35% / Seeing 25% / Transparency 15% / Moon 15% / Wind 10%
- Narrowband (no moon): Sky 40% / Transparency 25% / Seeing 25% / Wind 10%
- Cloud gating: all non-sky factors multiplied by √(sky_clarity/100)
- Quality labels: Excellent (80+), Good (55+), Marginal (30+), Poor (0+)

**Frontend:**
- `pages/WeatherPage.tsx` — location selector, moon toggle, 7-day cards, hourly detail
- `components/weather/DailyCard.tsx` — quality badge, factor bars, moon info, dew-safe line
- `components/weather/HourlyTimeline.tsx` — D3 SVG: darkness gradient bar, moon polyline, score factor grid (daylight hours grayed), weather details grid
- `components/weather/MethodologyInfo.tsx` — help accordion with factor table, cloud gating, dew risk
- `components/weather/MoonPhaseIcon.tsx` — terminator ellipse rendering from illumination %
- `components/weather/QualityBadge.tsx` — sequential blue palette (darker = better)
- `components/weather/LocationSelector.tsx` — dropdown from saved locations
- `api/weather.ts` — TypeScript interfaces and fetch functions

**Key implementation details:**
- PWV from ECMWF endpoint (standard forecast API doesn't include `total_column_integrated_water_vapour`)
- AOD from Air Quality API (3-hourly global, matched via `nearest_match`)
- Supplementary data cache writes wrapped in try/except (non-fatal — data returned even if caching fails)
- `forecast_days=8` to cover the last night's sunrise window
- Polar latitude handling: no HTTP 422, returns `no_imaging_window: true` with valid moon/darkness info
- Dew risk uses colorblind-safe sequential blue palette (not red/green)

## Dependency & License Policy

NightCrate is licensed under **MIT**. Before adding any new dependency (Python or JS/TS):

1. **Check the license.** Permissive licenses are always OK: MIT, BSD (2/3-Clause), Apache 2.0, ISC, HPND, SIL OFL (fonts), PSF. **LGPL is acceptable** for Python packages imported at runtime (dynamic linking) but requires attribution. **GPL is not allowed** — it would force the entire project to GPL. If a critical feature needs a GPL library, write a clean-room implementation or find an alternative. **Always discuss copyleft dependencies (LGPL, GPL) with Fred before adding** so we can weigh pros and cons together.
2. **MUI X Pro/Premium is never allowed** — paid commercial license. Only MUI X Community tier.
3. **Update `README.md`** — add the library to the Open Source Acknowledgments table with its license and copyright.
4. **Update `PLAN.md`** — if it's a new category of library, add it to the Library Reference appendix.

The full evaluated library list is in `PLAN.md` under "Appendix: Library Reference."
