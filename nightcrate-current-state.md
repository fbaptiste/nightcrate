# NightCrate — Current State

**Purpose:** A living inventory of what's actually built in NightCrate, intended to give an architecture-conversation Claude (or any future reader) a current picture of the system without having to read the codebase. This complements the spec documents — specs describe what's planned; this document describes what exists.

**Maintenance model:** Updated incrementally as features land. Not exhaustive — a one-paragraph-per-feature summary is enough. The goal is "good enough that an architecture discussion doesn't miss obvious existing functionality," not "complete API documentation."

**Last updated:** 2026-04-15

**Last full repo snapshot:** 2026-04-15

---

## How to use this document

- **Reading it:** Sections are organized by feature area, not by code structure. Each entry is short. Status tags indicate maturity.
- **Updating it:** When you finish a feature or make a significant architectural change, add or update the relevant entry. Don't worry about polish — bullet-point notes are fine. The maintenance cost should be low or this document will go stale.
- **Status tags:**
  - `[shipped]` — built, working, used in real workflows
  - `[in progress]` — actively being built; partial functionality exists
  - `[stub]` — placeholder or skeleton exists, no real functionality yet
  - `[planned]` — described in a spec but not started

---

## Stack and runtime

- **Backend:** Python 3.14 + FastAPI ≥0.115, served by Uvicorn. Version 0.11.0.
- **Key backend libraries:** astropy ≥7.0 (astronomy), aiosqlite (async DB), yoyo-migrations (schema), Pillow + tifffile (standard images), numpy ≥2.0, sep (star extraction), lz4 + zstandard (XISF compression), defusedxml (XML parsing), py7zr (7z archives), httpx (HTTP client for weather APIs), bottleneck (fast median), imagecodecs, mlx (Apple Silicon GPU, darwin-only), platformdirs (cross-platform paths).
- **Frontend:** React 19 + TypeScript 5.9, built with Vite 8. MUI 7 (Material + X Community: DataGrid, Charts, DatePickers, TreeView). D3 7 for complex charts. Zustand for state, TanStack Query for data fetching, react-router-dom 7 for routing. Geist font via @fontsource-variable.
- **Database:** SQLite via aiosqlite (raw SQL, no ORM). Current migration: `0008.weather_cache.sql`. Pydantic for all data models.
- **Packaging:** Local web app — `make dev` runs backend (uvicorn port 8000) + frontend (Vite port 5173) concurrently. `nightcrate` CLI entry point defined in pyproject.toml. No Tauri/Electron wrapper yet.
- **Platform support:** Mac, Windows, Linux. Platform-specific app data dirs via platformdirs. GPU auto-detects mlx (Mac) or CuPy (Windows/Linux) with numpy CPU fallback.

---

## Repository layout

```
nightcrate/
  backend/                  # Python backend (FastAPI app)
    src/nightcrate/
      api/                  # FastAPI routers (files, images, aberration, equipment,
                            #   locations, weather, settings, admin, diagnostics)
      core/                 # App config, GPU compute abstraction, settings model
      db/                   # Session management, migrations (0001–0008 .sql files)
      seed_loader/          # CSV-driven equipment seed loader (hash, registry, loader, CLI)
      services/             # Domain logic (imaging, fits_io, xisf_io, pxiproject_io,
                            #   standard_io, archive_io, aberration, weather, astronomy,
                            #   seeing, transparency, dew, imaging_quality, fits_header_map)
      data/seed/            # 31 CSV seed files for equipment reference data
      main.py               # App entry point, lifespan, router registration
    tests/                  # pytest test suite (~936 tests, 92% coverage)
  frontend/                 # React + TypeScript frontend (Vite)
    src/
      api/                  # Typed fetch clients per backend domain
      components/           # UI components (aberration/, equipment/, fits/, weather/,
                            #   AppShell, SetupWizard, ThemeProvider, ActivityConsole, etc.)
      lib/                  # Shared utilities (channelColors, colorName, namedColors,
                            #   formUtils, unitConversion, useDebounce)
      pages/                # Route pages: Home, ImageViewer, Equipment, Locations,
                            #   Weather, Settings, Admin, ApiDocs
      stores/               # Zustand stores (settingsStore)
      theme/                # MUI theme configuration
  docs/                     # Reference documents (XISF spec, weather algorithms)
  DB_SCHEMA.md              # Mermaid ER diagrams
  DB_SCHEMA_DDL.sql         # Authoritative CREATE TABLE statements
  CLAUDE.md                 # AI assistant instructions
  PLAN.md                   # Version roadmap and changelog
  Makefile                  # dev, backend, frontend, install, lint, format, test
  VERSION                   # Current version (0.11.0)
```

---

## Implemented features

### Catalog and project management

**Status:** `[planned]`

No catalog, project, session, or sub-frame management exists yet. The file browser and image viewer operate directly on the filesystem — there's no database-backed catalog of imaging sessions or targets. The ingestion pipeline is not built.

### Equipment

**Status:** `[shipped]`

Full CRUD for 12 equipment types (camera, sensor, telescope/OTA, filter, mount, focuser, filter wheel, OAG, guide scope, computer, software) plus 10 lookup/reference tables. Fully normalized schema with junction tables for interfaces, child tables for filter passbands and size options, and telescope configurations. Equipment seed loader populates reference data from 31 CSV files on first run with hash-based change detection for re-seeding. FITS alias tables exist for future FITS-to-equipment resolution. UI: two-panel layout with TreeView sidebar + DataGrid content area, per-type form dialogs, inline CRUD for lookup tables. Soft delete with optional restore. All seed-tracking columns stripped from API responses.

- **Routes:** `/equipment`, `/equipment/:category`
- **API:** `/api/equipment/*` (5+ endpoints per type), `/api/equipment/lookups/*`
- **Key backend:** `api/equipment.py`, `api/equipment_models.py`, `seed_loader/`

### Locations

**Status:** `[shipped]`

CRUD for imaging locations with coordinates, timezone, elevation, Bortle class, SQM reading, and address fields. Supports multiple locations with a single default (used by weather forecasting). Validation on lat/lon ranges.

- **Route:** `/locations`
- **API:** `/api/locations/*`
- **Schema:** migration `0007.locations.sql`

### Image viewer

**Status:** `[shipped]`

Multi-format viewer: FITS, XISF (clean-room parser, no GPL dependency), PixInsight projects (.pxiproject), PNG, JPEG, TIFF (including float32). Archive browsing (zip, tar, tar.gz, tar.bz2, tar.zst, 7z) with in-memory extraction. PixInsight-compatible auto-stretch (STF with avgDev). Per-channel statistics (median, MAD, avgDev, SNR, CIE L*a*b* a*). Canvas-based histogram with R/G/B/Luminosity channels, log/linear scale. Client-side pixel inspector with magnifier, hex color, XKCD named color. FITS header viewing and editing (batch update/add/delete with structural keyword protection). Recent files tracking. GPU-accelerated stretch and stats via mlx/cupy with numpy fallback.

**Aberration Inspector** tab: star detection via sep, configurable sample grid with per-square metrics, draggable grid squares, tile preview with ellipse overlays. Results cached in SQLite with TTL-based cleanup.

- **Route:** `/image-viewer`
- **API:** `/api/images/*`, `/api/files/*`, `/api/aberration/*`
- **Key backend:** `services/imaging.py`, `services/fits_io.py`, `services/xisf_io.py`, `services/pxiproject_io.py`, `services/standard_io.py`, `services/archive_io.py`, `services/aberration.py`

### Weather

**Status:** `[shipped]`

7-day imaging quality forecast with hourly detail. Composite 0–100 quality scores per night with weighted factors: sky clarity (35–40%), seeing (25%), transparency (15–25%), moon (0–15%), wind calm (10%). Broadband/narrowband weight sets toggle via moon penalty setting. Cloud gating multiplies non-sky factors by √(sky_clarity/100). Seeing estimated via blended surface (JAG Lab) + wind-shear (Trinquet/Cherubini) models. Transparency scored from PWV + AOD + humidity + visibility with graceful fallback tiers. Dew risk classification from temperature–dew point spread with safe window computation.

**UI:** Daily card view with quality badge (Excellent/Good/Marginal/Poor, sequential blue palette). Hourly timeline with D3 SVG: darkness gradient, moon polyline, score factor grid, weather details. Location selector from saved locations. Moon phase icon with terminator rendering. Methodology help accordion. Metric/imperial unit toggle.

- **Route:** `/weather`
- **API:** `/api/weather/forecast`, `/api/weather/hourly/{date}`, `/api/weather/methodology`
- **Data sources:** Open-Meteo (standard + ECMWF for PWV + Air Quality for AOD)
- **Key backend:** `services/weather.py`, `services/astronomy.py`, `services/seeing.py`, `services/transparency.py`, `services/dew.py`, `services/imaging_quality.py`
- **Reference:** `docs/weather-algorithms.md`

### Settings and admin

**Status:** `[shipped]`

**Settings:** theme (light/dark/browser), GPU acceleration toggle, max worker cores, file browser favorites and last path, aberration cache TTL, weather cache TTL, weather moon penalty toggle, weather units (metric/imperial). Stored as single JSON row in SQLite `settings` table.

**Admin:** Multi-database support with first-run setup wizard (three scenarios: fresh, available DBs, all unavailable). Create, register, activate, remove databases. DB hot-swap via `set_db_path()` + page reload. Filesystem browser with shortcuts (Home, Documents, App Data) and directory creation. App info display. Equipment re-seed trigger.

- **Routes:** `/settings`, `/admin`
- **API:** `/api/settings`, `/api/admin/*`, `/api/health`

### API documentation

**Status:** `[shipped]`

Auto-generated OpenAPI/Swagger docs from FastAPI with organized tag groups (File Browser, Image Viewer, Aberration Inspector, Equipment, Lookup Tables, Locations, Weather, Settings, Administration, Diagnostics). Accessible via in-app API Docs page.

- **Route:** `/api-docs` (in-app page), plus standard FastAPI `/docs` and `/redoc`

### Diagnostics / Activity Console

**Status:** `[shipped]`

ASGI middleware records every request with start timestamp, duration, status, and activity label. Frontend dialog shows requests grouped by activity with expandable detail tables. Activity labels propagated via `X-Activity` header or `_activity` query param. Diagnostics requests excluded from tracking.

- **API:** `/api/diagnostics/*`
- **Frontend:** `components/ActivityConsole.tsx`

---

## Schema state

Current migration: **0008** (weather_cache). 8 migrations total (`0001`–`0008`).

- **Core app:** `settings` (single JSON row), `recent_files` — app preferences and state
- **Equipment (migrations 0005–0006):** 12 equipment tables, 10 lookup/reference tables, 5 junction tables, 2 child tables, 4 FITS alias tables, 1 view, `seed_loader_meta` — fully normalized equipment catalog
- **Locations (migration 0007):** `location` — user imaging sites with coordinates and light pollution data
- **Aberration (migration 0004):** `aberration_analysis`, `aberration_stars` — cached star detection results with TTL
- **Weather (migration 0008):** `weather_cache` — forecast/archive/openmeteo_aq/ecmwf_pwv source-keyed cache

Authoritative DDL in `DB_SCHEMA_DDL.sql`. ER diagrams in `DB_SCHEMA.md`.

---

## Background processes and jobs

- **Startup (lifespan):** Migrations applied, seed loader runs (first-run populate / hash-based re-seed), stale aberration cache purged (TTL-based), stale weather cache purged (2× TTL)
- **No recurring background tasks** — no Celery, APScheduler, or asyncio task loops. All work is request-driven.
- **Caching:**
  - Image data + stats: in-memory with per-key locking (prevents redundant computation from concurrent requests)
  - Aberration analysis: SQLite cache keyed by (file_path, hdu, settings_json), TTL configurable (default 30 days)
  - Weather forecasts: SQLite cache keyed by source type, TTL configurable (default 6 hours, purged at 2× TTL)
  - Supplementary weather data (PWV/AOD): cached alongside forecast with non-fatal writes

---

## External dependencies

- **Open-Meteo** — weather forecast data (standard API for main weather, ECMWF endpoint for PWV, Air Quality API for AOD). Free, no auth required.
- No other external services called at runtime. Astronomy computations (moon, twilight, seeing) are all local via astropy + custom models.

---

## Notable architectural decisions already made

[Decisions baked into the codebase that future architecture discussions should not relitigate without good reason. Capture the decision and a one-sentence rationale.]

- [Decision 1] — [why]
- [Decision 2] — [why]

---

## Known limitations and rough edges

[Things that exist but have known gaps, performance issues, or planned overhauls. Not bug tracking — high-level "you should know this isn't great yet" notes.]

---

## What's NOT built yet

[Quick pointers to the spec documents that describe planned-but-not-built features, so a reader knows where to find more.]

- DSO catalogs — see `nightcrate-dso-catalog-plan.md`
- Schema revision — see `nightcrate-schema-revision-spec.md`
- Seed loader — see `nightcrate-seed-loader-spec.md`
- FITS resolver — see `nightcrate-fits-resolver-spec.md`
- Imaging core — see `nightcrate-ingest-pipeline-spec.md`
- Aberration Inspector — see `nightcrate-aberration-inspector-spec.md`
- [add as relevant]

---
