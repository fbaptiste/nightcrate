# NightCrate — Current State

**Purpose:** A living inventory of what's actually built in NightCrate, intended to give an architecture-conversation Claude (or any future reader) a current picture of the system without having to read the codebase. This complements the spec documents — specs describe what's planned; this document describes what exists.

**Maintenance model:** Updated incrementally as features land. Not exhaustive — a one-paragraph-per-feature summary is enough. The goal is "good enough that an architecture discussion doesn't miss obvious existing functionality," not "complete API documentation."

**NightCrate version:** 0.12.1

**Last updated:** 2026-04-18

**Last full repo snapshot:** 2026-04-17

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

- **Backend:** Python 3.14 + FastAPI ≥0.115, served by Uvicorn. Version 0.12.1.
- **Key backend libraries:** astropy ≥7.0 (astronomy), aiosqlite (async DB), yoyo-migrations (schema), Pillow + tifffile (standard images), numpy ≥2.0, sep (star extraction), lz4 + zstandard (XISF compression), defusedxml (XML parsing), py7zr (7z archives), httpx (HTTP client — now via shared `services/http_client.py` wrapper with uniform timeout + 1-retry), bottleneck (fast median), imagecodecs, mlx (Apple Silicon GPU, darwin-only), platformdirs (cross-platform paths), timezonefinder (coords → IANA tz).
- **Frontend:** React 19 + TypeScript 5.9, built with Vite 8. MUI 7 (Material + X Community: DataGrid, Charts, DatePickers, TreeView — free tier only, no MUI X Pro/Premium). D3 7 for complex charts. Zustand for state, TanStack Query for data fetching, react-router-dom 7 for routing. **@dnd-kit** (core + sortable + utilities, MIT) for drag-to-reorder (Clocks view). Geist font via @fontsource-variable.
- **Database:** SQLite via aiosqlite (raw SQL, no ORM). Current migration: `0012.location_soft_delete.sql`. Pydantic for all data models.
- **Packaging:** Local web app — `make dev` runs backend (uvicorn port 8000) + frontend (Vite port 5173) concurrently. `nightcrate` CLI entry point defined in pyproject.toml. No Tauri/Electron wrapper yet.
- **Platform support:** Mac, Windows, Linux. Platform-specific app data dirs via platformdirs. GPU auto-detects mlx (Mac) or CuPy (Windows/Linux) with numpy CPU fallback.

---

## Repository layout

```
nightcrate/
  backend/                  # Python backend (FastAPI app)
    src/nightcrate/
      api/                  # FastAPI routers (files, images, aberration, equipment,
                            #   locations, weather, rigs, settings, admin, diagnostics)
      core/                 # App config, GPU compute abstraction, settings model
      db/                   # Session management, migrations (0001–0010 .sql files)
      seed_loader/          # CSV-driven equipment seed loader (hash, registry, loader, CLI)
      services/             # Domain logic (imaging, fits_io, xisf_io, pxiproject_io,
                            #   standard_io, archive_io, aberration, weather, astronomy,
                            #   seeing, transparency, dew, imaging_quality, fits_header_map,
                            #   rig_calculators)
      data/seed/            # 31 CSV seed files for equipment reference data
      main.py               # App entry point, lifespan, router registration
    tests/                  # pytest test suite (~1124 tests, ~94% coverage on new code)
  frontend/                 # React + TypeScript frontend (Vite)
    src/
      api/                  # Typed fetch clients per backend domain
      components/           # UI components (aberration/, equipment/, fits/, rigs/, weather/,
                            #   AppShell, SetupWizard, ThemeProvider, ActivityConsole, etc.)
      lib/                  # Shared utilities (channelColors, colorName, namedColors,
                            #   formUtils, unitConversion, useDebounce, rigColors,
                            #   weatherColors)
      pages/                # Route pages: Home, ImageViewer, Equipment, Locations,
                            #   Weather, Rigs, Settings, Admin, ApiDocs
      stores/               # Zustand stores (settingsStore)
      theme/                # MUI theme configuration
  docs/                     # Reference documents (XISF spec, weather algorithms,
                            #   superpowers specs & plans for rigs / my-equipment /
                            #   guide suitability)
  DB_SCHEMA.md              # Mermaid ER diagrams
  DB_SCHEMA_DDL.sql         # Authoritative CREATE TABLE statements
  CLAUDE.md                 # AI assistant instructions
  PLAN.md                   # Version roadmap and changelog
  Makefile                  # dev, backend, frontend, install, lint, format, test
  VERSION                   # Current version (0.12.0)
```

---

## Implemented features

### Catalog and project management

**Status:** `[planned]`

No catalog, project, session, or sub-frame management exists yet. The file browser and image viewer operate directly on the filesystem — there's no database-backed catalog of imaging sessions or targets. The ingestion pipeline is not built. Rigs (v0.12.0) are the foundation — they model the user's imaging configurations and will feed the future FITS resolver + session/sub_frame layer.

### Equipment

**Status:** `[shipped]`

Full CRUD for 12 equipment types (camera, sensor, telescope/OTA, filter, mount, focuser, filter wheel, OAG, guide scope, computer, software) plus 10 lookup/reference tables. Fully normalized schema with junction tables for interfaces, child tables for filter passbands and size options, and telescope configurations. Equipment seed loader populates reference data from 31 CSV files on first run with hash-based change detection for re-seeding. FITS alias tables exist for future FITS-to-equipment resolution. UI: two-panel layout with TreeView sidebar + DataGrid content area, per-type form dialogs, inline CRUD for lookup tables. Soft delete with optional restore. All seed-tracking columns stripped from API responses.

**My Equipment (v0.12.0):** per-row `is_mine` boolean on 10 owned equipment types with partial indexes, `?mine=true` filter + is_mine-first ordering on list endpoints, `POST /api/equipment/<type>/{id}/mine` toggle, `GET /api/equipment/mine-counts`. UI: clickable star column in lists (optimistic toggle + Snackbar rollback), MineCheckbox in all 10 form dialogs, "MY EQUIPMENT" sidebar group with reactive sub-items, star indicator in rig-builder dropdowns with owned items surfaced at the top.

- **Routes:** `/equipment`, `/equipment/:category` (including `my-cameras`, `my-telescopes`, etc.)
- **API:** `/api/equipment/*` (5+ endpoints per type), `/api/equipment/lookups/*`, `/api/equipment/<type>/{id}/mine`, `/api/equipment/mine-counts`
- **Key backend:** `api/equipment.py`, `api/equipment_models.py`, `seed_loader/`

### Rigs and rig calculators

**Status:** `[shipped]`

User-composed imaging rig templates (one telescope configuration + one camera + optional mount / focuser / filter wheel / filter slots / OAG / guide scope / guide camera / computer / software). Full CRUD with clone, restore, and default-rig enforcement. `rig_summary` view drives list rendering with joined equipment names and guide-camera sensor data for calculators.

**Calculators:** Image scale, FOV (arctan formula with sensor-dim fallback), Dawes/Rayleigh limits, sensor coverage, sampling assessment (3-tier: oversampled/well_sampled/undersampled with per-binning recommendations). **Guide suitability:** mode-aware (guide-scope vs OAG), 4-tier rating on `effective_error_main_pixels` (0.6/1.0/1.2 thresholds), 6″/pixel hard cap, binning + centroid accuracy as query params. **Guiding tolerance:** 0.5× / 1.0× / 1.5× main-scale thresholds with plain-language comparison to current guide precision.

**UI:** Card-grid rig list with detail panel that opens on click. Detail panel has three tabs — **Equipment** (tree + detail pane fetching full equipment objects in parallel; shows every field including sensor photometrics, passbands, interfaces), **Imaging** (metrics + sampling chart with seeing slider), **Guiding** (two sub-tabs: Guide System and Guiding Tolerance, each with its own binning selector). Pure D3 charts (SamplingChart, GuideSuitabilityChart). "About this calculator" disclosures with attribution links.

- **Route:** `/rigs`
- **API:** `/api/rigs/*` (CRUD + `clone`, `restore`, `calculators`, `equipment-options`)
- **Key backend:** `api/rigs.py`, `api/rig_models.py`, `services/rig_calculators.py`
- **Specs:** `docs/superpowers/specs/2026-04-15-rig-builder-design.md`, `2026-04-16-my-equipment-design.md`, `2026-04-16-guide-suitability-design.md`

### Locations

**Status:** `[shipped]`

CRUD for imaging locations with coordinates, timezone, elevation, Bortle class, SQM reading, and address fields. Supports multiple locations with a single default (used by weather forecasting). Validation on lat/lon ranges.

**v0.12.1 additions:** sexagesimal lat/lon display (in edit form + detail panel), elevation shown in user's preferred unit with the other parenthesised, Clear Outside Bortle/SQM scraper endpoint, Display vs Location Timezone separation (with warning-dialog unlock on the coordinate-derived tz), detail slide-up panel with embedded OSM map, soft-delete via `active` column (migration 0012) — pre-empts v0.13 session-ingestion references.

- **Route:** `/locations`
- **API:** `/api/locations/*`
- **Schema:** migrations `0007.locations.sql`, `0012.location_soft_delete.sql`

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

**Settings:** theme (light/dark/browser), GPU acceleration toggle, max worker cores, file browser favorites and last path, aberration cache TTL, weather cache TTL, weather moon penalty toggle, weather units (metric/imperial), calculators clock order. As of v0.12.1, stored as one row per preference in the `settings(key, value_json, updated_at)` key-value table (migration 0011 — reshaped from the previous singleton JSON blob). `core/config.py:Settings` remains the Pydantic source of truth; adding a new field still requires no schema migration.

**Admin:** Multi-database support with first-run setup wizard (three scenarios: fresh, available DBs, all unavailable). Create, register, activate, remove databases — Create now auto-activates + reloads. Database list alphabetical with the active row inlined. DB hot-swap via `set_db_path()` + page reload. Filesystem browser with shortcuts (Home, Documents, App Data) and directory creation. App info display. Equipment re-seed trigger.

- **Routes:** `/settings`, `/admin`
- **API:** `/api/settings`, `/api/admin/*`, `/api/health`, `/api/weather/cache/{stats,clear}`

### Calculators

**Status:** `[shipped]`

Standalone mini-app with 12 astronomer/astrophotographer utilities grouped into four categories. Each calculator is backed by its own API endpoint so the math is equally usable from any external client — the frontend does no math beyond live-tick display.

**Calculators:** Lat/Long Converter (sexagesimal ↔ decimal), RA/Dec ↔ Alt/Az (location-aware, astropy-backed), Clocks (Local / UTC / LST / JD / MJD + Location's Display Timezone + Location Timezone; drag-to-reorder), Tonight at a Glance, Angular Units, Linear Units, Pixel Scale, Field of View, File Size, Airmass (Kasten-Young), SQM / Bortle / NELM, Temperature.

- **Route:** `/calculators[/:calcId]`
- **API:** `/api/calculators/*` (13 endpoints)
- **Key backend:** `services/calculators.py`, `services/coordinate_format.py`
- **Frontend:** `pages/CalculatorsPage.tsx`, `components/calculators/*`, `api/calculators.ts`, `stores/calculatorsStore.ts`
- **Shared primitives:** `CalculatorLocationBar` (location picker for the aware calculators), `CalculatorSidebar` (Equipment-style TreeView), `CalculatorAboutSection` (reused from rigs)
- **Deps:** `@dnd-kit/{core,sortable,utilities}` for drag-to-reorder (MIT)

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

Current migration: **0012** (location soft-delete). 12 migrations total (`0001`–`0012`).

- **Core app:** `settings` (key-value table as of migration 0011 — one row per preference), `recent_files` — app preferences and state
- **Equipment (migrations 0005–0006, plus inline edits in v0.12.0):** 12 equipment tables, 10 lookup/reference tables, 5 junction tables, 2 child tables, 4 FITS alias tables, 1 view, `seed_loader_meta` — fully normalized equipment catalog. `is_mine` column + partial index added to 10 owned equipment tables in v0.12.0. `idx_camera_guide_sensor` added inline to 0006 in v0.12.1.
- **Locations (migrations 0007, 0012, inline-edited in v0.12.0):** `location` — user imaging sites with coordinates, light pollution (Bortle + SQM), `typical_seeing_low/high_arcsec` for rig calculator sampling assessment. Migration 0012 adds `active` soft-delete column.
- **Aberration (migration 0004):** `aberration_analysis`, `aberration_stars` — cached star detection results with TTL
- **Weather (migration 0008):** `weather_cache` — forecast/archive/openmeteo_aq/ecmwf_pwv source-keyed cache
- **Rigs (migrations 0009–0010):** `rig`, `rig_filter_slot`, `rig_software` junction, `rig_summary` view — user-composed imaging templates. Migration 0010 recreates the view to expose `telescope_id` for the Equipment tab's detail pane

Authoritative DDL in `DB_SCHEMA_DDL.sql`. ER diagrams in `DB_SCHEMA.md`. LLM-facing seed-data + abbreviated-schema reference (for CSV authoring in Claude Desktop) in `LLM_DB_SPECS.md` at the repo root.

---

## Background processes and jobs

- **Startup (lifespan):** Migrations applied, seed loader runs (first-run populate / hash-based re-seed), stale aberration cache purged (TTL-based), stale weather cache purged (2× TTL)
- **No recurring background tasks** — no Celery, APScheduler, or asyncio task loops. All work is request-driven.
- **Caching:**
  - Image data + stats: in-memory with per-key locking (prevents redundant computation from concurrent requests)
  - Aberration analysis: SQLite cache keyed by (file_path, hdu, settings_json), TTL configurable (default 30 days)
  - Weather forecasts: SQLite cache keyed by source type, TTL configurable (default 6 hours, purged at 2× TTL)
  - Supplementary weather data (PWV/AOD): cached alongside forecast with non-fatal writes
  - Frontend: TanStack Query caches rig calculator + per-equipment detail fetches; `["mine-counts"]` invalidated on any star toggle

---

## External dependencies

- **Open-Meteo** — weather forecast data (standard API for main weather, ECMWF endpoint for PWV, Air Quality API for AOD). Free, no auth required.
- No other external services called at runtime. Astronomy computations (moon, twilight, seeing) are all local via astropy + custom models. Rig calculators (image scale, FOV, guide suitability, guiding tolerance, sampling) are pure local math — no external calls.

---

## Notable architectural decisions already made

- **sep over photutils for star detection** — photutils is GPL; sep (LGPL) is license-compatible and faster for the extraction-only use case (aberration inspector).
- **Catalog in place (reference, don't move files)** — default behavior is to index files where they live on disk. File reorganization/copy is optional, never forced. Avoids breaking PixInsight project paths or user directory structures.
- **Clean-room XISF parser** — the only existing XISF library (PixInsight's) is GPL. `xisf_io.py` is a from-scratch implementation covering sub-block and single-stream compression (zlib, lz4, lz4-hc, zstd with byte shuffle).
- **No ORM, raw SQL via aiosqlite** — deliberate choice for SQLite. Pydantic handles data shapes; SQL handles queries. No SQLAlchemy, no Tortoise, no Peewee.
- **No fuzzy matching in FITS resolver** — the planned resolver uses exact alias lookup, not string similarity. Unresolved headers go to an `unresolved_equipment_observation` table for manual review. This avoids silent mismatches across similar equipment names.
- **avgDev not MAD for auto-stretch** — PixInsight's Screen Transfer Function uses average deviation, not median absolute deviation. This was validated against PixInsight's actual output.
- **Seed data in CSV, not migrations** — equipment reference data lives in `data/seed/*.csv` loaded by the seed loader, not in SQL migration INSERT statements. Keeps migrations structural-only and allows Fred to prepare seed data in Claude Desktop.
- **Single JSON row for settings** — `settings` table has one row with a JSON blob. No column-per-setting. Simplifies adding new settings without migrations.
- **GPU abstraction via `core/compute.py`** — callers never import mlx/numpy/cupy directly. `get_array_module()` returns the right backend. Setting toggle applies immediately.
- **`::` virtual path separator** — used for both archive entries (`archive.zip::image.fits`) and pxiproject images (`project.pxiproject::0`). Consistent convention across all multi-image containers.

---

## Known limitations and rough edges

- **No catalog/ingestion pipeline** — the app can view and inspect images, but doesn't catalog them into projects/sessions/targets. This is the biggest missing piece for real workflow use.
- **No plate solving integration** — ASTAP and astrometry.net are planned but not wired up. No WCS overlay or object annotation on images.
- **Equipment exists but isn't connected to images** — FITS alias tables (`camera_alias`, `telescope_alias`, `filter_alias`) exist in the schema but the resolver that matches FITS headers to equipment rows is not built yet.
- **Weather seeing model is surface-level** — the wind-shear model improves accuracy when pressure-level data is available, but Open-Meteo's pressure-level coverage is limited. Seeing estimates should be treated as rough guidance, not observatory-grade predictions.
- **Single-chunk frontend bundle** — Vite warns about >500KB bundle. No code splitting yet. Acceptable for a local app but worth addressing if load times become noticeable.
- **`color="error"` uses MUI red** — a few error text instances use MUI's default red, which isn't ideal for red-green colorblind users. Should use the project's blue/orange palette instead.

---

## What's NOT built yet

Specs for future work live inline in `PLAN.md` (not as separate files).

- **FITS equipment resolver** — matches FITS header strings (`INSTRUME`, `TELESCOP`, `FILTER`) to equipment DB rows via alias tables. Schema support exists (alias tables, `unresolved_equipment_observation`); the resolver logic and UI are not built. See PLAN.md "FITS Equipment Resolver Spec" section.
- **Imaging core schema (rigs, projects, sessions, sub frames)** — the entire catalog/ingestion side. Equipment schema landed in v0.8.0–v0.10.0; what remains is the imaging-side schema (`rig`, `project`, `session`, `sub_frame`, calibration matching) and the ingestion pipeline (FITS parsing, N.I.N.A./ASIAIR/PHD2 log import). See PLAN.md "Imaging Core Schema" section.
- **DSO catalogs** — deep-sky object database for target planning and identification.
- **Plate solving** — ASTAP/astrometry.net integration for WCS coordinates and image annotation.
- **Desktop packaging** — Tauri wrapper for native app distribution (currently runs as local web app in browser).

Note: the seed loader (v0.10.0) and aberration inspector (v0.5.0) are shipped — they were listed here in an earlier version of this doc but are now implemented.

---
