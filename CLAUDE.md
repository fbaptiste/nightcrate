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
- **Key Python libs:** `astropy`, `astroquery`, `lz4`, `zstandard`, `defusedxml`, `timezonefinder` (geo tz from coordinates), ASTAP/astrometry.net for plate solving
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

**Test quality expectations:**
- New code must include tests covering happy paths, edge cases, and error conditions
- Tests must assert specific expected values (not just ranges like `0 <= x <= 100`)
- When modifying scoring formulas or algorithms, add pinned regression tests with hand-computed expected values
- When removing guards, assertions, or defensive checks, verify the downstream code still handles all cases
- Run `uv run coverage report --include="src/nightcrate/*"` periodically — no module should regress below its current coverage level

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
- `api/equipment.py` — hand-written routes for the unique-shape types (`sensor`, `telescope` + configurations + connectors, `filter` + passbands + size options) plus thin factory calls for the rest
- `api/equipment_factory.py` — `build_lookup_router` (9 lookup tables, 5 endpoints each) and `build_equipment_router` (8 mid-complexity equipment tables: 6 endpoints each, optional interface-junction rebuild, optional CHECK-constraint hook, caller-supplied `response_builder` for nested shapes)
- Helpers: `_common.row_to_dict`, `_common.bool_fields`, `_common.get_or_404`, `_common.strip_seed`, `_common.integrity_guard`; per-type `_build_X_response` helpers in `equipment.py` for the nested manufacturer + interface + per-type lookups
- Soft delete: DELETE sets `active=0`, list endpoints accept `?include_retired=true`
- Seed tracking columns stripped from all responses via `_SEED_KEYS` constant

**Endpoints per type:**
- 9 lookup tables (factory-built): 5 endpoints each (list, get, create, update, soft-delete)
- `camera`, `mount`, `focuser`, `filter_wheel`, `computer`, `oag`, `guide_scope`, `software` (factory-built): 6 endpoints each (list / get / create / update / soft-delete / mine-toggle); the first four rebuild an interface junction on create/update; `software` adds a 422 response on `category` CHECK violations
- `sensor` (hand-written): 5 endpoints; no `is_mine`, no junction, no children
- `telescope` (hand-written): 5 endpoints + 3 child endpoints for configurations (create/update/delete) + connector junction rebuild
- `filter` (hand-written): 5 endpoints + 3 child endpoints for passbands + 3 child endpoints for size options (create/update/delete)

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
- **Geographic vs display timezone:** each location has `geo_timezone` (auto-derived from coordinates via `timezonefinder`) and `timezone` (user's display preference). Astronomy computations (`compute_night_summary`, `compute_hourly_astro`) use `geo_timezone` for noon-to-noon search windows. Open-Meteo API and all display formatting use the user's `timezone`. This allows remote observatory operators to see times in their home timezone.
- `GET /api/locations/timezones` — backend-provided IANA timezone list for dropdown (filtered, Region/City format)
- `GET /api/locations/geo-timezone` — real-time coordinate-to-timezone lookup
- `lib/weatherColors.ts` — shared score-to-color helpers (scoreToBackground, scoreToTextColor, scoreToLabel)
- `HourlyTimeline.tsx` uses `localTimeToMinutes()` (string parsing, no Date) and `utcToLocalMinutes()` (Intl.DateTimeFormat) for timezone-correct rendering
- Weather page reads settings from Zustand store (shared with Settings page) for instant unit/preference sync

## Rig Builder

User-composed imaging rig templates that assemble equipment into a named configuration. Powers optical calculators and will feed the future FITS resolver and ingest pipeline.

**Architecture:**
- `db/migrations/0009.rig.sql` — `rig`, `rig_filter_slot`, `rig_software` (junction) tables, plus `rig_summary` view that joins equipment names for list rendering. Migration 0010 drops/recreates the view to expose `telescope_id` (edit-in-place of 0009 doesn't re-run on existing DBs).
- `services/rig_calculators.py` — pure math module (no DB / API deps). `compute_image_scale`, `compute_fov`, `compute_resolution_limits`, `compute_sensor_coverage`, `assess_sampling` (3-band: oversampled / well_sampled / undersampled with per-binning recommendations), `compute_guide_suitability`, `compute_guiding_tolerance`, `compute_rig_calculators` aggregator. Pinned regression tests against Fred's actual C11 and Askar V configurations.
- `api/rigs.py` — full CRUD + clone/restore/calculators/equipment-options endpoints. `rig_summary` view drives list responses; separate queries fetch filter slots + software. `_check_warnings` produces advisory warnings (retired equipment, guide-camera = imaging-camera, guide-scope missing focal length, orphan guide camera).
- `api/rig_models.py` — Pydantic: `RigCreate`, `RigUpdate`, `RigOut`, `RigCalculators` (nests `SamplingAssessment`, `GuideSuitability | None`, `GuidingTolerance | None`), `RigWarning` (with `severity: "error"|"info"`).
- `pages/RigsPage.tsx` — card grid + inline expansion detail panel. `RigCard` summarises rig contents and calculator highlights. `RigFormDialog` is the create/edit dialog.
- `components/rigs/CalculatorPanel.tsx` — **tabbed** detail layout: header row with rig name + Location selector + close; tabs **Equipment / Imaging / Guiding**; each tab owns its own body. Default tab is Equipment. Owns shared state (`selectedLocationId`, `guideBinning`, `centroidAccuracy`, `guidingImageBinning`) that becomes query params on `fetchRigCalculators`.
- `components/rigs/RigFormDialog.tsx` — equipment Autocompletes grouped by manufacturer (software grouped by category). `FilterSlotGrid` renders one slot per wheel position.
- `components/rigs/SamplingChart.tsx` — pure D3 horizontal-bar chart showing all four binning levels against the ideal zone. Theme-aware. Blue (well sampled) / orange (oversampled) / teal (undersampled).

**Key invariants:**
- Each rig has exactly one `telescope_configuration_id` (which implies one `telescope`, always present). Camera is required. Everything else is optional.
- Filter slots (`rig_filter_slot`) require a `filter_wheel_id`; if the wheel is cleared on update, all slots are deleted. Single-filter rigs set `single_filter_id` instead.
- Multi-software support via `rig_software` junction — ordered by software name in responses.
- Default rig enforcement: setting `is_default=1` on one rig clears it on all others in a single transaction (`_ensure_single_default`).
- Soft delete via `active=0`; `?include_retired=true` or restore endpoint brings them back.

## My Equipment

Per-row `is_mine` boolean on 10 equipment tables (camera, telescope, filter, mount, focuser, filter_wheel, oag, guide_scope, computer, software) lets users mark gear they personally own. Owned items surface first in rig-builder dropdowns and in a dedicated "MY EQUIPMENT" sidebar group.

**Schema:**
- `is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0,1))` on each of the 10 tables (inline edit of migration 0005).
- Partial index `idx_<table>_mine ON <table>(is_mine) WHERE is_mine = 1` per table.
- Sensor, telescope_configuration, junction tables, child tables, lookup tables, and alias tables are **not** touched.
- Seed loader hash contract is unaffected — `is_mine` is not in `SeedableTable.seeded_fields`, so marking an item as mine does not trigger re-seed.

**API:**
- `is_mine` on every `<Type>Create` (default `False`) / `<Type>Update` (nullable) / `<Type>Response` for the 10 types.
- List endpoints accept `?mine=true` and default to `ORDER BY is_mine DESC, <existing sort>` so owned gear floats to the top in every list.
- `POST /api/equipment/<type>/{id}/mine` — dedicated idempotent toggle per type; body `{is_mine: bool}`; returns the full response.
- `GET /api/equipment/mine-counts` — single round trip returning per-type counts used by the sidebar to decide which sub-items to render.
- Create endpoints persist `is_mine` explicitly in their INSERTs (don't rely on column default).

**Frontend:**
- `components/equipment/EquipmentList.tsx` — clickable star column (leftmost, `StarIcon`/`StarOutlineIcon`, blue primary), optimistic toggle via `toggleEquipmentMine`, rollback with Snackbar on failure, invalidates list + `["mine-counts"]` queries. Accepts `mineOnly` prop to filter the list to owned items.
- `components/equipment/shared/MineCheckbox.tsx` — shared control wired into all 10 equipment form dialogs.
- `components/equipment/EquipmentSidebar.tsx` — new "MY EQUIPMENT" group at top. Reactive: sub-items only render for types with count > 0 per `fetchMineCounts`. Empty state shows italic "Click the star on any equipment row to add it here."
- `pages/EquipmentPage.tsx` — routes `my-cameras`, `my-telescopes`, etc. to the same per-type list wrappers with `mineOnly={true}`.
- Rig builder Autocompletes (`RigFormDialog`, `FilterSlotGrid`) use `withMineGroup` helper in `components/rigs/mineGroup.ts` — duplicates owned items into a virtual "My Equipment" group at the top with a blue `StarIcon` indicator; owned items also appear in their manufacturer group with the same star.

## Rig Calculators — Guide System & Guiding Tolerance

Two complementary guiding calculators rendered in the Guiding tab of the rig detail panel. Guide System answers "is my guide rig precise enough for my imaging rig?" up-front; Guiding Tolerance answers the inverse "given my imaging rig, what PHD2 RMS should I aim for?"

**Architecture:**
- `services/rig_calculators.py` — `compute_guide_suitability(guide_scope_id, oag_id, …, guide_binning, centroid_accuracy_pixels)` returns `GuideSuitability | None`. `compute_guiding_tolerance(unbinned_main_scale, image_binning, guide_suitability)` always returns a `GuidingTolerance`.
- `api/rig_models.py` — Pydantic `GuideSuitability` and `GuidingTolerance`. `RigCalculators` nests them (replaced the older top-level `guide_image_scale_*`/`guide_field_of_view_*` fields).
- `api/rigs.py` — `GET /api/rigs/{id}/calculators` accepts `guide_binning` (1–4), `centroid_accuracy_pixels` (0.05–0.5), `image_binning` (1–4) query params. 422 on out-of-range values. Emits two new warnings: guide scope missing focal length; guide camera assigned with no OAG/guide-scope path.
- `components/rigs/GuideSuitabilityPanel.tsx` — metrics table, rating `Chip` (excellent/good/marginal/poor), mode-aware subtitle (guide-scope vs OAG), advanced disclosure with centroid accuracy slider.
- `components/rigs/GuideSuitabilityChart.tsx` — pure D3 horizontal bar chart (main pixel vs guide error), threshold markers at 0.6 / 1.0 / 1.2 px, scale-cap annotation when triggered.
- `components/rigs/GuidingTolerancePanel.tsx` — "Image Scale" row in Imaging-tab style; thresholds table (Tight / Acceptable / Over budget); shaded-zone visualization with current-precision marker (bars at 0.7 opacity for dark-mode readability); interpretation line generated server-side.
- `components/rigs/GuidingTab.tsx` — **two sub-tabs** (Guide System / Guiding Tolerance) with **two independent binning selectors** above them: "Imaging camera binning" drives Guiding Tolerance; "Guide camera binning" drives Guide System. Imaging tab's binning is separate and purely display-side.
- `components/rigs/CalculatorAboutSection.tsx` — shared collapsed disclosure for attribution + methodology text (astronomy.tools, Open PHD Guiding, Stan Moore for Guide System; Cloudy Nights community rule of thumb for Guiding Tolerance).
- `lib/rigColors.ts` — shared palette (`RIG_BLUE`, `RIG_ORANGE`, `RIG_TEAL`, light variants), `samplingColor()`, `ratingColor()`, `ratingTextColor()`, `ratingLabel()` helpers.

**Guide System math:**
- Mode resolution: `guide_scope_id` set → guide-scope mode (focal length from guide scope); else `oag_id` set → OAG mode (focal length from telescope configuration's `effective_focal_length_mm`); else None.
- `guide_scale_arcsec_per_pixel = (guide_pixel_size_um × guide_binning / guide_focal_length_mm) × 206.265`
- `effective_guide_precision_arcsec = guide_scale × centroid_accuracy_pixels` (default 0.2 px)
- `g_ratio = guide_scale / main_scale`; `effective_error_main_pixels = g_ratio × centroid_accuracy_pixels`
- Four rating bands on `effective_error_main_pixels`: Excellent ≤0.6, Good ≤1.0, Marginal ≤1.2, Poor >1.2.
- **Absolute scale cap:** `guide_scale_arcsec_per_pixel > 6.0` forces Poor with `rating_reason='scale_cap'` (PHD2 community limit). Cap wins when both fail.
- FOV uses the **unbinned** resolution (binning doesn't change physical sensor area).

**Guiding Tolerance math:**
- `tight_rms_arcsec = 0.5 × main_scale × image_binning`
- `acceptable_rms_arcsec = 1.0 × main_scale × image_binning`
- `noticeable_rms_arcsec = 1.5 × main_scale × image_binning`
- When `guide_suitability` is present, its `effective_guide_precision_arcsec` is compared to the thresholds; `guide_system_within_tight` / `_within_acceptable` / `headroom_arcsec` are populated; `interpretation` string generated server-side.

**Equipment tab (tree + detail):**
- Left: SimpleTreeView grouped Imaging / Optics / Tracking / Accessories / Computing (same order as the main Equipment sidebar). Multi-item categories (filters, software, cameras when both imaging + guide present) expand to per-item leaves; singletons are leaves under their group.
- Right: selected item's full detail. Fetches complete equipment objects via `/api/equipment/<type>/{id}` in parallel (`useQueries` for filters). TanStack Query caches across opens.
- Includes every available field: cooling deltas, back focus, weight, connectors, interfaces as outlined chips, vendor-tuned camera specs, full sensor photometrics (pixel size, ADC depth, full well, read noise, peak QE, Bayer pattern, dual gain) for both imaging and guide cameras, telescope optical design / image circle / obstruction, all other configurations on the OTA, filter passband lines with wavelength/bandwidth/peak transmission plus filter size options, mount payload / PE / drive type, focuser step size / backlash / temp compensation.
- Responsive: side-by-side on md+, stacked on smaller screens. Both panes scroll at 70vh.
- Default initial selection: "Summary" when description or notes present; otherwise the imaging camera.

## Calculators

Standalone astronomy + imaging-math utilities at `/calculators[/:calcId]`. Each calculator has a backend endpoint so the math is equally usable from any external client — frontend does no math beyond live-tick display.

**Architecture:**
- `backend/src/nightcrate/api/calculators.py` — 13 endpoints under `/api/calculators/*` (lat/long sexagesimal both ways, RA/Dec ↔ Alt/Az, sidereal time, tonight, angular units, linear units, pixel scale, FOV, file size, airmass, SQM/Bortle/NELM, temperature).
- `backend/src/nightcrate/services/calculators.py` — pure-Python service layer (no DB/FastAPI deps).
- `backend/src/nightcrate/services/coordinate_format.py` — `format_latitude` / `format_longitude` for sexagesimal display (astropy `Angle`, `°` `′` `″` glyphs, padded DMS). Used by Locations too.
- `frontend/src/pages/CalculatorsPage.tsx` — Equipment-style sidebar + content pane.
- `frontend/src/components/calculators/` — 12 per-calculator components; shared `CalculatorSidebar`, `CalculatorLocationBar` (dropdown wired to default-location logic), `RigPickerMenu` (auto-populate for Pixel Scale / Field of View / File Size), `Math.tsx` (thin `InlineMath` / `BlockMath` wrappers over react-katex).
- `frontend/src/api/calculators.ts` — TypeScript client + response types.
- `frontend/src/stores/calculatorsStore.ts` — session-only `selectedLocationId`. Clock order persists via the server-side `settings` table (not localStorage).

**Key details:**
- RA/Dec ↔ Alt/Az uses `astropy.coordinates.SkyCoord` + `EarthLocation` + `AltAz` frame; airmass via Kasten-Young (1989).
- Sidereal time: server computes via `Time(...).sidereal_time('apparent', longitude=...)`; client ticks at the sidereal rate (1.00273790935) between 60-second server refreshes.
- Tonight: reuses `services/astronomy.py:compute_night_summary`; returns sunset/sunrise, three twilight pairs, moonrise/moonset, moon illumination + phase, astronomical dark hours, moonless dark hours. Backend returns `HH:MM` strings already rendered in the display timezone — the frontend must pass them through verbatim, not re-parse as ISO-UTC.
- SQM ↔ Bortle band mapping; SQM → NELM via Schaefer approximation; NELM → SQM via bisection.
- Clocks drag-to-reorder via **@dnd-kit** (MIT — `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`). Chosen order persists in `settings.calculators_clock_order` (server-side, not localStorage).
- FOV uses the full arctan form (not small-angle approximation).
- Rig auto-populate: Pixel Scale / Field of View / File Size each render `<RigPickerMenu onApply={...} />` above their inputs. `onApply` receives the full `Rig` object and copies focal length, pixel size, sensor width/height (mm + px), and ADC bit depth into local state. Fields remain editable after a rig is applied. `sensor_adc_bit_depth` is sourced from migration 0013's extension of the `rig_summary` view.
- Formula rendering via **KaTeX** (MIT — `katex`, `react-katex`, `@types/react-katex`). CSS imported once in `main.tsx`. Used in About sections of Pixel Scale, Field of View, File Size, Airmass, SQM/Bortle/NELM, Temperature, and the Weather methodology accordion.
- **JSX Unicode gotcha:** JSX does NOT interpret backslash escapes in attribute-string form (`label="\u00B0C"` passes 8 literal characters). Wrap the string in a JS expression: `label={"\u00B0C"}`. Similarly, `&approx;` is not in React's named-entity table; use `{"\u2248"}` instead.
- **Native form-control theming:** `MuiCssBaseline` sets `body.colorScheme = "dark"/"light"` per theme so the native date-input popup, scrollbars, and other browser-rendered form elements match the current theme.

## Custom Horizons

Per-location horizon profile (trees, hills, buildings). Imported from N.I.N.A. `.hrz` / Telescopius / APCC / Theodolite iPhone CSV / generic 2-col text, edited in a dedicated dialog, exported to N.I.N.A., Stellarium, or CSV. Shipped in v0.13.0 — data is stored and displayed but not yet consumed by planner, altitude overlays, or session scoring.

**Architecture:**
- `backend/src/nightcrate/db/migrations/0014.location_horizon.sql` — `location_horizon` (1:1 with location, UNIQUE on `location_id`, source ∈ `{'imported','drawn'}`) + `location_horizon_point` (composite PK on `(horizon_id, azimuth_deg)`, CHECK on az `[0,360)` and alt `[-5,90]`). `ON DELETE CASCADE` from location → horizon → points.
- `services/horizon.py` — forgiving parser: sniffs Theodolite CSV (by `HDG_DEG`/`VERT` header columns), else falls through to 2-col text. Normalizes az to `[0,360)`, validates alt, sorts, offsets exact duplicates by +0.01° (N.I.N.A. vertical-obstruction convention), rejects <2 points. Three exporters — `.hrz`, Stellarium polygonal zip, CSV — plus a filename sanitizer.
- `api/horizons.py` — 7 endpoints under `/api/locations/{id}/horizon` (GET / PUT / DELETE / POST `/import` / GET `/export/{nina.hrz,stellarium.zip,csv}`), plus a sibling `parse_router` exposing stateless `POST /api/horizons/parse` (no DB write) for the frontend's staged-save flow. Export allows soft-deleted locations for recovery. INSERT wrapped in `integrity_guard` for concurrent-save safety. Shared `_parse_upload_file` helper (read + UTF-8 decode + parse, 400 on failure) used by both `/import` and `/parse`.
- `api/horizon_models.py` — `HorizonPut` (≥2-point validator), `HorizonResponse`, `HorizonImportResponse`, `HorizonParseResponse`.

**Frontend:**
- `components/locations/HorizonChart.tsx` — SVG + D3 panorama. N-centered x-axis (S on both edges), auto-fit y with a single-pass reduce over all visible layers. Three stacked layers: solid-orange editable line + teal fill; dashed-orange **trace reference**; dotted-blue **original comparison**. Editable mode: double-click to add, drag to move (0.1° snap), right-click for precision popover. Readonly mode: smooth Catmull-Rom (raw-points toggle flips to linear + measurement dots). Implicit dashed 0° baseline when <2 points.
- `components/locations/HorizonEditor.tsx` — MUI modal dialog (`maxWidth="lg"`, not fullScreen) with toolbar + point-edit popover + reduce preview dialog + clear-trace confirm + too-few-points guard + ⌘Z/⌘⇧Z undo/redo. Buttons are **Keep changes** / **Discard changes** — "Keep" stages the result in the parent via `onSave`, does NOT persist directly.
- `components/locations/HorizonEditorToolbar.tsx` — import / export dropdown / reduce / clear / undo / redo / altitude-range toggle / trace chip / compare toggle / smooth toggle / point counter.
- `components/locations/HorizonPointEditPopover.tsx` — right-click popover with az/alt numeric inputs + Delete.
- `lib/horizonReduce.ts` — Douglas-Peucker using **vertical altitude distance** as the error metric (preserves peak obstructions). Iterative (stack-based, safe on long point lists).
- `api/horizons.ts` — typed fetch clients. `fetchHorizon` returns `null` on 404 (no horizon defined); `parseHorizonFile` is the stateless parse path; `downloadHorizonExport` triggers a browser anchor-click download so the frontend never buffers the bytes.

**Staged-save flow (key UX decision):**
- Horizon persistence is owned by the outer Location editor, not the horizon dialog. `LocationHorizonEditSection` in `LocationsPage.tsx` holds tri-state `{kind: "none" | "set" | "delete"}` staged data.
- Horizon editor's **Keep changes** updates the parent's staged state via `onSave(points)` — no network I/O inside the callback.
- Import routes through `parseHorizonFile` (no DB write) so the imported points land in staged state.
- Delete in the horizon section marks `{kind: "delete"}` — preview goes blank with a "Pending deletion — Save to apply" chip and Undo link.
- Location editor's Save persists staged horizon (PUT or DELETE) **before** updating location fields (horizon validation is stricter; fail fast).
- Location editor's Cancel/X/Escape runs a dirty check against both the form and the staged horizon; shows a Discard-changes prompt when anything is unsaved.
- Export menu is disabled (`exportsDisabled={staged.kind !== "none"}`) while staged changes exist, to avoid serving stale server data.

**Chart layering:**
- Editable orange + teal fill sits on top.
- Trace reference is a dashed centripetal-Catmull-Rom curve (smooth shape guide, user traces over it).
- Original comparison is a dotted **linear** curve in `RIG_BLUE` (shows exactly what was stored; never smoothed).
- Reduce dialog reuses the same chart in readonly mode with the pre-reduce snapshot as `referencePoints` and the live reduced-preview as `points` — the before/after visualization pattern.

**Key invariants:**
- ≥2 points required to save a horizon (enforced Pydantic-side and in the editor via the too-few-points dialog; <2 falls back to empty dashed 0° baseline).
- Smoothing is **never persisted**. Raw points are the canonical shape. Consumers that want a smooth curve re-run the same D3 path generation.
- Azimuth stored as `[0, 360)`, never 360; display rolls to `[-180, +180]` with virtual seam points at the S boundary for continuous rendering.

## Settings (key-value schema)

Application settings stored in a `settings(key TEXT PRIMARY KEY, value_json TEXT, updated_at TEXT)` table (migration 0011, reshaped from the previous `settings(id, data JSON)` singleton). Each Pydantic field on `core/config.py:Settings` maps to one row; `get_settings()` merges rows, silently drops rows with un-parseable JSON, and falls back to defaults on `ValidationError`. `update_settings()` upserts every field in a single loop — each update bumps `updated_at`.

Adding a new setting still requires no schema migration: add the Pydantic field with a default, and the KV path handles the rest.

## Outbound HTTP

All outbound HTTP (Open-Meteo forecast/PWV/AOD, Clear Outside scraper) goes through `backend/src/nightcrate/services/http_client.py:get()`. Uniform 30s timeout, one 500ms-backoff retry on transient failures (`TimeoutException`, `ConnectError`, 5xx), structured `[http] …` log lines. Callers still catch `httpx.HTTPError` and translate to their domain-appropriate HTTP status (typically 502 for upstream failures).

## Logging

- `NIGHTCRATE_LOG_LEVEL` env var drives the `nightcrate` namespace logger level (INFO default; set to `DEBUG` for verbose traces).
- `[weather-cache]` / `[http]` / `[open-meteo]` structured log lines on hot paths.
- Router 500s (bare `except Exception`) log via `logger.exception(...)` so server bugs leave a traceback in the log.

## Shared router helpers

`backend/src/nightcrate/api/_common.py`:
- `row_to_dict(row, *, extra_fn=None)` — aiosqlite.Row → dict, with an optional post-processor (locations uses it to derive sexagesimal display strings).
- `bool_fields(d, *keys)` — INTEGER(0/1) → Python bool, in place.
- `strip_seed(d)` — drops `source`/`seed_key`/`seed_hash` from response dicts.
- `integrity_guard(conflict_detail, *, constraint_map=None, check_detail=None)` — context manager that translates `aiosqlite.IntegrityError.sqlite_errorname` into HTTP 409 (UNIQUE) or 422 (CHECK). Optional `constraint_map` dispatches on partial-index name substring.

Use these in every new CRUD router instead of reimplementing the pattern.

## Path resolution

`backend/src/nightcrate/services/path_resolver.py` — `resolve_path(path)` handles plain filesystem paths, pxiproject virtual paths (`project_dir::index`), and archive virtual paths (`archive.zip::entry`). Returns `(resolved_path_or_BytesIO, file_type, image_index, cache_key)`. Used by both `api/images.py` and `api/aberration.py`.

## Dependency & License Policy

NightCrate is licensed under **MIT**. Before adding any new dependency (Python or JS/TS):

1. **Check the license:.** **Always discuss copyleft dependencies (LGPL, GPL) with Fred before adding** so we can weigh pros and cons together. Always use attributions where necessary. Discuss possibility of clean room implementation options if that becomes necessary.

NightCrate is licensed under MIT. Dependency licenses must be reviewed
before inclusion. The acceptable licenses, in order of preference:

Freely compatible (always fine):
  MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, HPND, PSF-2.0,
  CC0, Unlicense, 0BSD

Font licenses (always fine for bundled fonts):
  SIL OFL 1.1 — permits embedding and redistribution with software
  under any license, including proprietary.

Compatible with attribution obligations (fine, note the requirements):
  BSD-4-Clause — advertising clause imposes attribution on derivative
  works. Prefer BSD-2/3-Clause alternatives where available.
  MPL-2.0 — file-level copyleft. Modifications to MPL files must stay
  MPL; combining MPL libraries with MIT code is fine.

Compatible for normal Python imports (fine, no discussion needed):
  LGPL-2.1, LGPL-2.1+, LGPL-3.0, LGPL-3.0+ — Python `import` is
  dynamic linking, which LGPL permits. Currently in use: sep (LGPL-3.0),
  py7zr (LGPL-2.1+). Discussion is required only if NightCrate modifies
  the library source, static-links it, or bundles it into a redistributed
  artifact (e.g., a PyInstaller/Tauri build) — in those cases the LGPL
  library's source must be made available alongside the distribution,
  per LGPL requirements.

Not allowed (incompatible copyleft):
  GPL-2.0, GPL-2.0+, GPL-3.0, GPL-3.0+, AGPL-3.0, AGPL-3.0+
  — the copyleft terms would force NightCrate to relicense.

Not allowed (not open source):
  SSPL, BUSL (Business Source License), Commons Clause, Elastic
  License 2.0, Confluent Community License, Redis Source Available
  License, any "source-available" license that restricts commercial
  use, hosting, or competition.

Dual-licensed libraries:
  Fine — take the permissive option. Many libraries offer MIT-or-GPL,
  MPL-or-LGPL-or-GPL, etc. Use under the most permissive option.

Commercial tier caveats:
  MUI X packages (@mui/x-charts, @mui/x-data-grid, @mui/x-date-pickers,
  @mui/x-tree-view) ship a Community tier (MIT) and Pro/Premium tiers
  (commercial). NightCrate uses only Community features. Features marked
  with a "Pro" or "Premium" badge in MUI X documentation are off-limits
  regardless of whether they appear to work without a license key.

Exception — external programs invoked across a process boundary:
  External programs invoked via subprocess, IPC, CLI, or HTTP are not
  "dependencies" for license propagation purposes — they are separate
  works. GPL-licensed external tools (e.g., plate solvers, Source
  Extractor, ASTAP) may be invoked via the process-boundary pattern.
  The license of an external program does not propagate to code that
  calls it across a process boundary, provided NightCrate does not
  bundle the program into a combined distribution. If such a program
  is bundled with a redistributed NightCrate build, its license terms
  apply to that distribution and must be reviewed separately.

Transitive and bundled licensing considerations:
  - LGPL obligations only kick in at distribution/packaging time (Tauri/PyInstaller),
    not at pip-install time. At distribution time, the LGPL library's LICENSE file
    and notices must be bundled alongside the build (LGPL §6). No runtime attribution
    or "credits screen" is required.
  - Pre-built wheels from PyPI are the expected distribution path. Building from
    source may pull in different license terms (e.g., rawpy's LibRaw demosaic packs
    are GPL-2.0 — only the standard pip-installed wheels, which exclude these packs,
    are compatible with MIT).
  - Some libraries have optional features or tiers that are separately licensed and
    off-limits even if the main library is fine: rawpy demosaic packs (GPL-2.0),
    opencv-contrib modules (mixed GPL/patent), MUI X Pro/Premium (commercial).
  - `opencv-python-headless` is preferred over `opencv-python` (avoids Qt/GUI deps).
    `opencv-contrib-python` is not allowed without case-by-case review.
  - Data retrieved from astronomical databases (via astroquery or similar) may have
    attribution requirements independent of the library's software license. Check
    the terms of use for each specific service queried (e.g., SIMBAD, MAST).
  - If Claude Code audits transitive deps and flags the GCC Runtime Library, that is
    covered by the GCC Runtime Library Exception and is explicitly designed for use
    in non-GPL code.

2. **MUI X Pro/Premium is never allowed** — paid commercial license. Only MUI X Community tier.
3. **Update `README.md`** — add the library to the Open Source Acknowledgments table with its license and copyright.
4. **Update `PLAN.md`** — if it's a new category of library, add it to the Library Reference appendix.

The full evaluated library list is in `PLAN.md` under "Appendix: Library Reference."
