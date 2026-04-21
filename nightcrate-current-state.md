# NightCrate — Current State

**Purpose:** A living inventory of what's actually built in NightCrate, intended to give an architecture-conversation Claude (or any future reader) a current picture of the system without having to read the codebase. This complements the spec documents — specs describe what's planned; this document describes what exists.

**Maintenance model:** Updated incrementally as features land. Not exhaustive — a one-paragraph-per-feature summary is enough. The goal is "good enough that an architecture discussion doesn't miss obvious existing functionality," not "complete API documentation."

**NightCrate version:** 0.18.0

**Last updated:** 2026-04-20

**Last full repo snapshot:** 2026-04-19

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
- **Key backend libraries:** astropy ≥7.0 (astronomy), **astropy-healpix** (BSD-3, HEALPix partitioning for the sky-tile cache — not GPL `healpy`), aiosqlite (async DB), yoyo-migrations (schema), Pillow + tifffile (standard images), numpy ≥2.0, sep (star extraction), lz4 + zstandard (XISF compression), defusedxml (XML parsing), py7zr (7z archives), httpx (HTTP client — via shared `services/http_client.py` wrapper with uniform timeout + 1-retry), bottleneck (fast median), imagecodecs, mlx (Apple Silicon GPU, darwin-only), platformdirs (cross-platform paths), timezonefinder (coords → IANA tz).
- **Frontend:** React 19 + TypeScript 5.9, built with Vite 8. MUI 7 (Material + X Community: DataGrid, Charts, DatePickers, TreeView — free tier only, no MUI X Pro/Premium). D3 7 for complex charts. Zustand for state, TanStack Query for data fetching, react-router-dom 7 for routing. **@dnd-kit** (core + sortable + utilities, MIT) for drag-to-reorder (Clocks view). Geist font via @fontsource-variable.
- **Database:** SQLite via aiosqlite (raw SQL, no ORM). Current migration: `0020.sky_tile_cache.sql`. Pydantic for all data models.
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
- **Key backend:** `api/equipment.py`, `api/equipment_factory.py` (v0.12.2 — `build_lookup_router` + `build_equipment_router` consolidate duplicated CRUD for 9 lookup tables + 8 mid-complexity equipment tables; `sensor`, `telescope`, and `filter` stay hand-written because of unique children/junctions), `api/equipment_models.py`, `seed_loader/`

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

### Custom Horizons

**Status:** `[shipped]`

Per-location custom horizon profiles (azimuth/altitude polylines) for session planning visibility analysis. Import from N.I.N.A. `.hrz`, Theodolite iPhone CSV (14-column sniff), Telescopius, APCC, or generic two-column text. Export to N.I.N.A. `.hrz`, Stellarium zip, or CSV. Interactive SVG editor with D3 renders a N-centered panorama (-180° to +180° around North), drag-to-move points, right-click popover for azimuth/altitude numeric entry + delete, Douglas-Peucker point reduction with vertical-altitude error metric, centripetal Catmull-Rom (α=0.5) smoothing for display, compare-to-original overlay (blue dotted, always linear), and trace-mode reference overlay (orange dashed) from imported data. Staged-save UX: horizon edits stage inside the Location editor dialog; the outer dialog's Save is the single persistence action that writes both location fields and horizon together. Detail panel shows a read-only horizon chart with a Raw/Smoothed switch.

- **Route:** rendered inside `/locations` (editor dialog + detail panel)
- **API:** `/api/locations/{id}/horizon` (GET/PUT/DELETE/import), `/api/locations/{id}/horizon/export/{format}`, `POST /api/horizons/parse` (stateless)
- **Key backend:** `services/horizon.py`, `api/horizons.py` (two routers: `/api/locations/{id}/horizon/*` and `/api/horizons/parse`), `api/horizon_models.py`
- **Key frontend:** `components/locations/HorizonEditor.tsx`, `HorizonChart.tsx`, `HorizonEditorToolbar.tsx`, `HorizonPointEditPopover.tsx`, `lib/horizonReduce.ts`
- **Schema:** migration `0014.location_horizon.sql` (`location_horizon`, `location_horizon_point`)

### Target Planner (v0.16.0 Pass A + v0.17.0 Pass B + v0.18.0 Pass C)

**Status:** `[shipped]`

Location-driven "what's up tonight" page at `/planner`. Lists every active DSO geometrically visible during astronomical darkness, scored by hours-visible; optional rig selection adds FOV coverage %, a "frames well" filter, an "In my rig" thumbnail column showing the object framed by the rig's sensor, and a rotatable FOV Simulator in the detail panel. Custom horizons (v0.13.0) are used automatically when present; locations without a horizon fall back to a flat `planner_min_altitude_deg` floor from Settings.

**Tonight / Anytime (v0.18.0):** prominent header-level mode toggle switches the page between "Tonight from {location}" (the location-aware planner) and "Browse the full catalog" (Anytime — same data source, no location / visibility / moon context, catalog-style filters matching the DSO Catalog page: constellation dropdown, has-distance checkbox, type-group chips with counts, raw-type chips under an "Advanced filters" disclosure, clear-filters button). Location selector, imaging-focused sliders (Min hours / Brighter than / Min size / Frames well), visibility columns, and the "no astro-dark" alert are all hidden in Anytime. Backend deliberately does NOT fall back to saved imaging defaults in Anytime.

Backend: vectorized astropy alt/az over 14 k DSOs runs in well under a second per night with a process-wide 4-entry LRU. Sky-track service produces a 5-minute resolution per-DSO altitude/azimuth + moon-altitude + horizon-reference track for the detail panel's D3 graph.

Thumbnails: DSS2 Color JPEGs (falling back to DSS2 red) fetched from CDS Aladin's hips2fits, cached on disk under `APP_DIR/thumbnails/`. Variants: `list` (180×180), `detail` (800×800), `rig_framed` (180×180). The old `fov_simulator` variant is retired — the simulator now pulls cells from the DSO-agnostic `sky_tile_cache` below. Misses return a 1×1 PNG with HTTP 202 OR — when the client passes `wait_ms=N` — hold the request open for up to 10 s awaiting the background fetch task under `asyncio.shield`, returning the real image in the same round trip. Per-process `_fetch_semaphore=8` caps concurrency against CDS. App-startup orphan sweep deletes on-disk files not referenced by the cache table.

**Sky-tile cache (v0.18.0, migration 0020):** DSO-agnostic HEALPix-regional tile cache. Cells keyed by `(hips_survey, nside, ipix, tier, cell_size, cell_w, cell_h, cell_i, cell_j)` — no FK to `dso`. NSIDE=8 (via `astropy-healpix`, BSD-3) partitions the sphere into 768 equal-area regions. Every cell inside a region shares the region's tangent plane and tiles pixel-perfectly at shared edges (hips2fits with custom `wcs=<JSON>` header). Three tiers selected by rig major FOV: `narrow` (≤1°, 0.5° cells @ 800×800), `med` (1–3°, 2° cells @ 800×800), `wide` (>3°, 8° cells @ 1024×1024). Two DSOs whose composites overlap inside a region share every cell in the overlap — the defining performance win over the DSO-keyed `thumbnail_cache`. Same long-poll + 1-hour error-backoff contract. `SkyPreview` on the DSO Catalog detail panel reuses the same tiles with an auto-tier zoom-to-fit driven by `previewSpecForDsoSize`.

FOV Simulator (v0.18.0 rewrite): drag-to-rotate orange sensor rectangle overlaid on a pannable `SkyTileComposite`. Staged mount — centre cell first with `waitMs=4000`, then distance-sorted remainder. Grid promotes 1 → 3 → 5 cells wide as the centre renders so the backend's 8-slot semaphore focuses on the target. Scroll-wheel zoom (native wheel listener — React's `onWheel` is passive). Default zoom: rig rect fills 75% of the viewport. Annotation click takes precedence over pan (JSX z-order). Re-centre button preserves zoom + rotation; R resets everything. Annotation overlay uses `projectRaDecInRegion` (single region tangent shared with the cells) — no per-tile candidate selection needed, alignment is pixel-exact across all cells. Labels counter-scale by `1/zoom` to stay constant CSS size during zoom.

- **Route:** `/planner`
- **API:** `GET /api/planner/targets` (+ `q`, `restrict_tonight`, `type`, `constellation`, `has_distance`), `GET /api/planner/targets/{dso_id}/sky-track`, `GET /api/planner/thumbnails/{dso_id}` (optional `wait_ms` long-poll), `GET /api/planner/sky-tile-grid` (layout math), `GET /api/planner/sky-tile` (cell bytes, optional `wait_ms`), `POST /api/planner/thumbnails/cache/clear`, `GET /api/planner/thumbnails/cache/stats`, `POST /api/planner/sky-tile/cache/clear`, `GET /api/planner/sky-tile/cache/stats`, `GET /api/planner/dsos/in-region`
- **Key backend:** `services/planner_visibility.py`, `services/planner_sky_track.py`, `services/thumbnails.py` + `services/hips_client.py`, `services/sky_tiles.py` + `services/sky_tile_cache.py` (v0.18.0), `services/rig_calculators.py:compute_coverage_pct`, `services/horizon.py:interpolate_horizon_altitude`
- **Key frontend:** `pages/PlannerPage.tsx`, `components/planner/{ThumbnailCell,SkyPositionGraph,PlannerDetailPanel,FovSimulator,SkyTileCell,SkyTileComposite,DsoAnnotationOverlay,DsoAnnotationPopover}.tsx`, `components/dso/SkyPreview.tsx`, `lib/{dsoAnnotations,skyPreviewExtent}.ts`, `stores/thumbnailCacheStore.ts`, `api/planner.ts`
- **Schema:** migrations 0017–0019 (`thumbnail_cache`), 0020 (`sky_tile_cache`, v0.18.0)
- **Settings:** `planner_min_altitude_deg` (30°), `planner_min_visibility_hours` (2h), `planner_max_magnitude` (12), `planner_min_size_arcmin` (5'), `thumbnail_cache_max_mb` (500, v0.18.0 bump from 20; slider max 5 GB)
- **Deliberate deviations from spec:** moon distance is **closest approach during the visibility window**, not at-peak — the at-peak value can be misleading when the moon is below horizon at transit but rises during the visible window.

### DSO catalog

**Status:** `[shipped]` (v0.14.0 MVP + v0.15.0 augmentation)

Deep-sky object catalog. Data is **not shipped** in the repo — on first run the tables are empty and the DSO page shows a CTA pointing to Admin → Catalogs. v0.15.0 expands from OpenNGC-only to a multi-source layered model:

- **OpenNGC** (GitHub) — base rows. ~13,371 DSOs + designations across 29 cross-reference catalogs.
- **Sharpless 2** (VizieR VII/20) — HII regions. Merged onto existing OpenNGC DSOs via `sharpless_crossref.csv` where a known identity exists (e.g., Sh2-281 → NGC 1976); standalone otherwise.
- **Barnard** (VizieR VII/220A) — dark nebulae. Always standalone — never merged with backing emission regions.
- **50 MGC** (Ohlson+ 2024, J/AJ/167/31) — galaxy distance augmenter, not a DSO source. Fetched from the author's **GitHub mirror** (`github.com/davidohlson/50MGC`, default branch `master`) rather than VizieR because CDS has been intermittently flaky. The GitHub mirror ships the catalog as a FITS binary table at `data/catalog.fits`; parsed via astropy, using the lowercase column names `pgc`, `bestdist`, `bestdist_error`, `bestdist_method`. Fills `distance_pc` on existing galaxy DSOs via PGC cross-reference, honoring curated distances via `WHERE distance_pc IS NULL`. About 83% of 50 MGC values are themselves flow-corrected redshift distances; the remainder are Cepheid, TRGB, or SBF measurements.
- **NightCrate augmentation** (bundled MIT) — common-name overrides, non-galaxy surface brightness, curated distances. Applied before 50 MGC so curated wins.
- **Redshift-derived Hubble-law distances** — post-load computation. Galaxies that still have no distance after the four fetched sources but carry a non-zero `redshift` get `d = z·c/H₀` with H₀ = 70 km/s/Mpc, tagged `distance_method='redshift'`. Not a fetched source and not represented in `dso_catalog_source` — purely a final pass inside `load_catalogs`.

VizieR fetches (Sharpless, Barnard) rotate through three CDS mirrors (Strasbourg → India → South Africa) on retry exhaustion. GitHub fetches (OpenNGC, 50 MGC) use `raw.githubusercontent.com` exclusively. All fetchers use the same atomic pattern (`.download/` → rename, sha256, `version.json` commit marker). Constellation codes for Sharpless/Barnard rows come from `astropy.SkyCoord.get_constellation()` (cached). Shared loader primitives live in `catalog_loader/_common.py`.

**UI additions:** type-group filter chips (Galaxy / Emission Nebula / Planetary Nebula / etc.) via the backend's `services/dso_type_groups.py` dispatch — raw OpenNGC codes moved to an "Advanced filters" expander. Distance column in the grid + detail panel with pc/ly dual-unit auto-scaling (`lib/distanceFormat.ts`). B-Mag tooltip clarifying Johnson B ≈ photographic magnitude. Subtle "augmented" star icon next to common_name / surface_brightness when the value came from the NightCrate editorial layer.

- **Route:** `/catalog/dso`
- **API:** `/api/dso` (list + `type_group` / `has_distance` filters + `distance_pc` sortable), `/api/dso/{id}` (detail, now with distance + augmentation flags), `/api/dso/lookup`, `/api/dso/facets` (now returns `type_groups` + `raw_types` + `constellations`), `/api/dso/catalog-sources`, + `POST /api/admin/catalogs/reload`, `GET/POST /api/admin/catalogs/vizier/{source_id}/{remote-version,fetch}` (per-source VizieR endpoints for Sharpless / Barnard), `GET/POST /api/admin/catalogs/50mgc/{remote-version,fetch}` (50 MGC GitHub fetch — not VizieR), `POST /api/admin/catalogs/nightcrate/reload`.
- **Key backend:** `catalog_loader/` module: `remote.py` (OpenNGC GitHub fetch), `vizier.py` + `vizier_tsv.py` (CDS, 3-mirror fallback), `mgc50_fetch.py` + `mgc50_parser.py` (50 MGC GitHub FITS binary table via astropy), `sharpless_loader.py` + `barnard_loader.py` (standalone DSO creation), `mgc50_augmenter.py` (distance augmenter), `redshift_distance.py` (Hubble-law post-load backfill), `augment_loader.py` (editorial overrides), `_common.py` (shared loader primitives + `retry_with_backoff`). `services/dso_type_groups.py` type-group dispatch. `services/astronomy.py` exposes `redshift_to_parsecs`, `distance_modulus_to_parsecs`, and the `SPEED_OF_LIGHT_KM_S` / `HUBBLE_CONSTANT_KM_S_MPC` constants.
- **Key frontend:** `pages/DsoCatalogPage.tsx` (type-group chips + Advanced expander + distance column), `components/dso/DsoDetailPanel.tsx` (distance row with "~" prefix on redshift-derived values + help-icon opening the distance dialog, B-Mag tooltip, AugmentedBadge), `components/dso/DsoDistanceHelpDialog.tsx` (KaTeX-rendered explanation of the three distance methods), `components/dso/DsoAttributionPanel.tsx` (CDS acknowledgment + per-catalog citations + redshift-derived section), `components/dso/CatalogsAdminSection.tsx` (per-source rows in Admin — OpenNGC + Sharpless + Barnard + 50 MGC GitHub + NightCrate bundled), `lib/distanceFormat.ts`, `lib/dsoTypeGroups.ts`.
- **Schema:** migrations `0015.dso_catalog.sql` + `0016.dso_augmentation.sql` (adds `distance_pc`, `distance_method` with CHECK vocabulary `{'50mgc', 'curated', 'redshift'}`, `common_name_augmented`, `surface_brightness_augmented` on `dso`).
- **Data:** not in repo; downloaded to `APP_DIR/catalogs/{openngc,vizier,github/50mgc}/`. NightCrate editorial CSVs bundled at `backend/src/nightcrate/data/catalogs/nightcrate/` (`dso_augment.csv`, `sharpless_crossref.csv`, `barnard_crossref.csv`).

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
- **Shared primitives:** `CalculatorLocationBar` (location picker for the aware calculators), `CalculatorSidebar` (Equipment-style TreeView), `CalculatorAboutSection` (reused from rigs), `RigPickerMenu` (auto-populate from a rig — Pixel Scale / Field of View / File Size; loads focal length, pixel size, sensor dims, ADC bit depth from the selected rig and leaves fields editable)
- **Math rendering:** KaTeX via `react-katex`. `components/calculators/Math.tsx` exposes `<Inline>` / `<Block>` wrappers used in the About sections of Pixel Scale, Field of View, File Size, Airmass, SQM/Bortle/NELM, Temperature, and the Weather methodology accordion
- **Deps:** `@dnd-kit/{core,sortable,utilities}` for drag-to-reorder (MIT); `katex` + `react-katex` + `@types/react-katex` for math rendering (MIT)

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

Current migration: **0016** (DSO augmentation columns). 16 migrations total (`0001`–`0016`).

- **Core app:** `settings` (key-value table as of migration 0011 — one row per preference), `recent_files` — app preferences and state
- **Equipment (migrations 0005–0006, plus inline edits in v0.12.0):** 12 equipment tables, 10 lookup/reference tables, 5 junction tables, 2 child tables, 4 FITS alias tables, 1 view, `seed_loader_meta` — fully normalized equipment catalog. `is_mine` column + partial index added to 10 owned equipment tables in v0.12.0. `idx_camera_guide_sensor` added inline to 0006 in v0.12.1.
- **Locations (migrations 0007, 0012, inline-edited in v0.12.0):** `location` — user imaging sites with coordinates, light pollution (Bortle + SQM), `typical_seeing_low/high_arcsec` for rig calculator sampling assessment. Migration 0012 adds `active` soft-delete column.
- **Horizons (migration 0014):** `location_horizon` (one row per location, UNIQUE on `location_id`, source ∈ {imported, drawn}), `location_horizon_point` (composite PK on horizon_id + azimuth_deg, CHECK az ∈ [0,360), alt ∈ [-5,90]) — custom per-location horizon profiles.
- **DSO catalog (migrations 0015 + 0016):** `dso_catalog_source` (loader registry + file sha256), `dso` (canonical DSO with closed `obj_type` CHECK vocabulary, + `distance_pc` / `distance_method` / `common_name_augmented` / `surface_brightness_augmented` added in 0016; `distance_method` CHECK ∈ `{'50mgc', 'curated', 'redshift'}`), `dso_designation` (many-per-dso with closed 29-catalog CHECK vocabulary, `UNIQUE(catalog, identifier)`, partial unique index enforcing one primary per dso). Populated via fetch-on-demand from GitHub (OpenNGC + 50 MGC FITS) + VizieR (Sharpless, Barnard). NightCrate augmentation CSV (common names, non-galaxy surface brightness, curated distances) bundled in-repo under `data/catalogs/nightcrate/`.
- **Target Planner thumbnails (migration 0017, extended by migrations 0018 + 0019):** `thumbnail_cache` — metadata for the LRU disk cache under `APP_DIR/thumbnails/` that serves DSS2 Color JPEG thumbnails fetched from CDS Aladin's hips2fits. FK cascade-deletes when a DSO disappears. `fetch_error` rows record failed attempts for a 1-hour backoff window. Files live on disk, not in the DB. v0.17.0 migration 0018 widens the variant CHECK to include `rig_framed` + `fov_simulator`, adds nullable `fov_major_deg_x1000` / `fov_minor_deg_x1000` columns, and rebuilds the unique index over `COALESCE(-1)`-wrapped FOV columns. Migration 0019 ALTER-adds `center_ra_deg_x1000` / `center_dec_deg_x1000` for panned FOV-simulator tiles at arbitrary sky centres, using a distinct `COALESCE(-999999)` sentinel so legitimate 0.0 RA (celestial equator) can't collide with NULL.
- **Aberration (migration 0004):** `aberration_analysis`, `aberration_stars` — cached star detection results with TTL
- **Weather (migration 0008):** `weather_cache` — forecast/archive/openmeteo_aq/ecmwf_pwv source-keyed cache
- **Rigs (migrations 0009–0010, 0013):** `rig`, `rig_filter_slot`, `rig_software` junction, `rig_summary` view — user-composed imaging templates. Migration 0010 recreates the view to expose `telescope_id` for the Equipment tab's detail pane. Migration 0013 recreates the view again to expose `sensor_adc_bit_depth` for the File Size calculator's auto-populate flow.

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
