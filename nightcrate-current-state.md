# NightCrate — Current State

**Purpose:** A living inventory of what's actually built in NightCrate, intended to give an architecture-conversation Claude (or any future reader) a current picture of the system without having to read the codebase. This complements the spec documents — specs describe what's planned; this document describes what exists.

**Maintenance model:** Updated incrementally as features land. Not exhaustive — a one-paragraph-per-feature summary is enough. The goal is "good enough that an architecture discussion doesn't miss obvious existing functionality," not "complete API documentation."

**NightCrate version:** 0.39.0

**Last updated:** 2026-06-25

**Last full repo snapshot:** 2026-05-19

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

- **Backend:** Python 3.14 + FastAPI ≥0.115, served by Uvicorn.
- **Key backend libraries:** astropy ≥7.0 (astronomy), **astropy-healpix** (BSD-3, HEALPix partitioning for the sky-tile cache — not GPL `healpy`), aiosqlite (async DB), yoyo-migrations (schema), Pillow + tifffile (standard images), numpy ≥2.0, scipy (FFT pipeline, Akima interpolation), sep (star extraction), lz4 + zstandard (XISF compression), defusedxml (XML parsing), py7zr (7z archives), httpx (HTTP client — via shared `services/http_client.py` wrapper with uniform timeout + 1-retry), bottleneck (fast median), imagecodecs, mlx (Apple Silicon GPU, darwin-only), platformdirs (cross-platform paths), timezonefinder (coords → IANA tz).
- **Frontend:** React 19 + TypeScript 5.9, built with Vite 8. MUI Material 7 + MUI X Community v8 (DataGrid, Charts, DatePickers, TreeView — free tier only, no MUI X Pro/Premium). D3 7 for complex charts. Zustand 5 for state, TanStack Query 5 for data fetching, react-router-dom 7 for routing. **@dnd-kit** (core + sortable + utilities, MIT) for drag-to-reorder. KaTeX + react-katex for math rendering. Geist font via @fontsource-variable.
- **Database:** SQLite via aiosqlite (raw SQL, no ORM). Current migration: `0034.project_solve.sql`. Pydantic for all data models.
- **Packaging:** Local web app — `make dev` runs backend (uvicorn port 8000) + frontend (Vite port 5173) concurrently. `make dev-lan` binds to `0.0.0.0` + serves Vite over HTTPS (auto-picks `frontend/.certs/{cert,key}.pem` if present, else `@vitejs/plugin-basic-ssl` self-signed) so iPad/Android tablets can reach NightCrate over the LAN. `nightcrate` CLI entry point defined in pyproject.toml. No Tauri/Electron wrapper yet.
- **Platform support:** Mac, Windows, Linux. Platform-specific app data dirs via platformdirs. GPU auto-detects mlx (Mac) or CuPy (Windows/Linux) with numpy CPU fallback.

---

## Repository layout

```
nightcrate/
  backend/                  # Python backend (FastAPI app)
    src/nightcrate/
      api/                  # FastAPI routers (~18 modules: files, images, aberration,
                            #   equipment, locations, horizons, weather, rigs, planner,
                            #   wishlist, dso, phd2, plate_solve, calculators, settings,
                            #   admin, diagnostics + _common helpers + equipment_factory)
      catalog_loader/       # DSO catalog fetchers (OpenNGC, VizieR, 50MGC, Wikidata,
                            #   Sharpless/Barnard loaders, augmenters, shared primitives)
      core/                 # App config, GPU compute abstraction, settings model
      db/                   # Session management, migrations (0001–0034 .sql files)
      seed_loader/          # CSV-driven equipment seed loader (hash, registry, loader, CLI)
      services/             # Domain logic (~40 modules: imaging, fits/xisf/pxiproject/
                            #   standard/archive I/O, aberration, weather, astronomy,
                            #   seeing, transparency, dew, imaging_quality, planner_*,
                            #   thumbnails, sky_tiles, horizon, phd2_*, plate_solve,
                            #   image_annotations, rig_calculators, calculators,
                            #   coordinate_format, http_client, path_resolver)
      data/seed/            # 31 CSV seed files for equipment reference data
      data/catalogs/        # Bundled NightCrate editorial CSVs (augmentation, crossrefs)
      main.py               # App entry point, lifespan, router registration
    tests/                  # pytest test suite (~2087 tests)
  frontend/                 # React + TypeScript frontend (Vite)
    src/
      api/                  # Typed fetch clients (18 modules, one per backend domain)
      components/           # UI components (14 directories: aberration, admin, calculators,
                            #   common, dso, equipment, fits, locations, phd2, planner,
                            #   plate-solve, rigs, settings, weather + root-level AppShell,
                            #   SetupWizard, ThemeProvider, ActivityConsole, SidebarSection,
                            #   EasterEggWand)
      lib/                  # Shared utilities (23 modules: formatting, colors, debounce,
                            #   type groups, sort fields, guiding metrics, settings sync)
      pages/                # 14 route pages: Home, ImageAnalyzer, Equipment, Locations,
                            #   Weather, Rigs, Settings, Admin, ApiDocs, Planner,
                            #   DsoCatalog, Phd2Analyzer, Calculators, Tonight
      stores/               # 7 Zustand stores (settings, planner, imageAnalyzer, phd2,
                            #   dsoCatalog, calculators, thumbnailCache)
      theme/                # MUI theme configuration
  docs/                     # Reference documents, specs, algorithm docs
  sample_data/              # Sample logs for testing (PHD2, ASIAIR)
  DB_SCHEMA.md              # Mermaid ER diagrams
  DB_SCHEMA_DDL.sql         # Authoritative CREATE TABLE statements
  LLM_DB_SPECS.md           # LLM-facing seed-data + schema reference
  CLAUDE.md                 # AI assistant instructions
  PLAN.md                   # Version roadmap and changelog
  Makefile                  # dev, dev-lan, backend, frontend, install, lint, format, test
  VERSION                   # Current version (0.36.0)
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

User-composed imaging rig templates (one telescope configuration + one camera + optional mount / focuser / filter wheel / filter slots / OAG / guide scope / guide camera / computer / software). Full CRUD with clone, restore, and default-rig enforcement. `rig_summary` view drives list rendering with joined equipment names and guide-camera sensor data for calculators. **v0.32.0:** drag-to-reorder on the Rigs page via `sort_order` column (migration 0026); `PUT /api/rigs/reorder` endpoint; all rig dropdowns honour user order.

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

### Horizons (v0.19.0 multi-horizon + v0.20.0 staged-save restoration)

**Status:** `[shipped]`

Each location owns ≥1 horizon: at most one **custom** polyline shape (imported from N.I.N.A. `.hrz`, Theodolite iPhone CSV, Telescopius, APCC, or generic 2-col text; or drawn in the editor), plus any number of named **artificial** flat-altitude rows. One row per location is marked `is_default=1` — the planner uses it when no explicit horizon is selected. Custom horizon editor unchanged from v0.13.0 (N-centered D3 panorama, Douglas-Peucker reduction, compare-to-original overlay, trace mode). `POST /api/locations` auto-seeds a `0° flat` artificial default for every new location that doesn't supply its own horizons, and migration 0021 back-seeds the same row for locations that had no horizon pre-upgrade.

**v0.20.0 — staged-save restoration.** v0.19.0's LocationHorizonsSection rewrite accidentally dropped v0.13.0's staged-save contract. v0.20.0 restores it: horizon CRUD inside the Location editor dialog now writes to in-memory staged state only; the outer Save button commits everything atomically (new locations via `LocationCreate.horizons` — one transaction; existing locations via an ordered `planSaveOps` diff-apply — creates → updates → promote-default → deletes). Cancel discards every staged change. Per-row `new`/`modified`/`deleted` chips surface what will commit. See CLAUDE.md's "⚠ DO NOT regress" guardrail in the Horizons section for the invariant.

**Compute integration (v0.19.0):** `services/horizon.resolve_horizon_altitude(type, flat_altitude_deg, points, az)` dispatches artificial vs custom at a single call-site; every planner compute path (`planner_visibility`, `planner_sky_track`, `planner_annual_hours`, `planner_now_status`) takes a `PlannerHorizon` value object. The old `planner_min_altitude_deg` setting is gone — altitude floor lives per-horizon on the location.

- **Route:** rendered inside `/locations` (editor dialog). Also a header dropdown on `/planner` (between Location and Rig).
- **API:** `GET/POST/PATCH/DELETE /api/locations/{id}/horizons[/{hid}]` — full CRUD. Plus `POST /horizons/import` (imports a file as a new custom horizon, replacing any existing custom), `GET /horizons/{hid}/export/{format}`, and stateless `POST /api/horizons/parse`. Auto-promote on default delete, 422 on last-horizon delete, 422 on demoting a default without promoting another, 409 on duplicate name or second custom.
- **Key backend:** `services/horizon.py`, `api/horizons.py`, `api/horizon_models.py` (`HorizonCreate` / `HorizonUpdate` with `type`-discriminated validation).
- **Key frontend:** `components/locations/LocationHorizonsSection.tsx` (v0.20.0 rewrite — operates on staged state owned by `LocationsPage`), `components/locations/horizonStaging.ts` (v0.20.0 — StagedHorizon + lifecycle helpers + save-dispatch planner), plus the unchanged editor dialog components (`HorizonEditor`, `HorizonChart`, etc.). Shared `components/planner/horizonMenuItems.tsx` renders the Custom/Artificial grouped dropdown for both the planner main page and the detail panel.
- **Schema:** migrations `0014.location_horizon.sql` (original 1:1) + `0021.location_horizon_multi.sql` (reshapes to 1:N with partial unique indexes on `is_default` and `type='custom'`). v0.20.0 extends `LocationCreate` with optional `horizons: list[HorizonCreate] | None` for atomic create.

### Target Planner (v0.16.0–v0.21.0 + v0.30.0 wishlist + v0.31.0 moon quality)

**Status:** `[shipped]`

Location-driven "what's up tonight" page at `/planner`. Lists every active DSO geometrically visible during astronomical darkness, scored by a transparent 0–100 quality algorithm (v0.21.0); optional rig selection adds FOV coverage, a "Size in frame" coverage-range filter (dual-thumb slider), an "In my rig" thumbnail showing the object framed by the rig's sensor, and a rotatable FOV Simulator in the detail panel.

**v0.21.0 scoring algorithm.** Per-target 0–100 score with an `Excellent / Good / Fair / Poor` colored chip on every Tonight-mode card + detail header, plus a "Score breakdown" section at the bottom of the detail panel showing per-dimension bars + human-readable inputs (or gate-failure reasons for unscored targets). Pipeline is two hard gates → four quality dimensions (**observability** altitude-weighted hours; **meridian timing** peak-vs-dark-midpoint; **moon impact** phase × proximity × filter-sensitivity with a limiting-filter rule; **frame fit** Gaussian on coverage) → weighted geometric mean. 25 new user-tunable settings (weights, 7 moon sensitivities, 7 moon min-separations, cluster modifier, frame-fit ideal+spread, 3 chip thresholds, 2 hard-gate caps) in a collapsible Settings accordion with tooltips. A new filter-intent multi-select (Ha/SII/OIII/L/R/G/B) on the planner page drives the moon dimension — empty selection neutralizes it. Filter intent persists via Zustand (imaging habits are stable). Scoring is backend-only, pure-function over the visibility snapshot's retained time-series arrays; a single-target `GET /api/planner/targets/{dso_id}/score` endpoint refetches when the detail panel's panel-local rig / horizon / location differ from the page's. Anytime mode has no score (the algorithm is tonight-scoped by construction). Full algorithm reference in `docs/planner-scoring.md`.

**v0.19.0 rewrite.** Three big reshapes shipped together. (1) Locations gained **multi-horizon** (one optional custom polyline + any number of artificial flat-altitude rows, with exactly one `is_default`). Every compute path takes a `PlannerHorizon` value object; the old `planner_min_altitude_deg` fallback setting is gone. Third dropdown (Location · **Horizon** · Rig) in both the main page and the detail panel; changing location resets the horizon to that location's default. (2) **Multi-sort panel** replaces the DataGrid's single-column header sort — collapsible accordion with a `SortableContext` "Sort by" area (drag to reorder) and an "Available" chip list (click to add). 14 sort fields via `PLANNER_SORT_FIELDS`; backend stable Timsort per key, nulls + empty strings always last. `sortBy` persists in `plannerStore` (Zustand persist v3). (3) **Card-based list** replaces the DataGrid row layout — one card per DSO with thumbnail + rig-framed thumbnail + info block + tonight-line visibility stats; the whole card is clickable (opens detail panel). Opaque custom loading overlay on the Paper wrapper sidesteps MUI X's linear-progress-in-column-header artifact during refetches.

**Now-status fix (v0.19.0).** `compute_now_status` takes both `astro_dark_start_utc` and `astro_dark_end_utc`. Decision tree: post-dawn returns empty; daytime-before-tonight samples only the dark-window interval (with "up" never firing); inside astro-dark samples `now → dark_end`. Earlier bug sampled `now → dark_end` unconditionally, surfacing "set" for objects that had set in the morning but would re-rise during tonight's session.

**Tonight / Anytime (v0.18.0):** prominent header-level mode toggle switches the page between "Tonight from {location}" (the location-aware planner) and "Browse the full catalog" (Anytime — same data source, no location / visibility / moon context, catalog-style filters matching the DSO Catalog page: constellation dropdown, has-distance checkbox, type-group chips with counts, raw-type chips under an "Advanced filters" disclosure, clear-filters button). Horizon dropdown, imaging-focused sliders (Min hours / Brighter than / Min size / Size in frame), tonight-only card row, and the "no astro-dark" alert are all hidden in Anytime. Backend deliberately does NOT fall back to saved imaging defaults in Anytime.

Backend: vectorized astropy alt/az over 14 k DSOs runs in well under a second per night with a process-wide 4-entry LRU. Sky-track service produces a 5-minute resolution per-DSO altitude/azimuth + moon-altitude + horizon-reference track for the detail panel's D3 graph.

Thumbnails: DSS2 Color JPEGs (falling back to DSS2 red) fetched from CDS Aladin's hips2fits, cached on disk under `APP_DIR/thumbnails/`. Variants: `list` (180×180), `detail` (800×800), `rig_framed` (180×180). The old `fov_simulator` variant is retired — the simulator now pulls cells from the DSO-agnostic `sky_tile_cache` below. Misses return a 1×1 PNG with HTTP 202 OR — when the client passes `wait_ms=N` — hold the request open for up to 10 s awaiting the background fetch task under `asyncio.shield`, returning the real image in the same round trip. Per-process `_fetch_semaphore=8` caps concurrency against CDS. App-startup orphan sweep deletes on-disk files not referenced by the cache table.

**Sky-tile cache (v0.18.0, migration 0020):** DSO-agnostic HEALPix-regional tile cache. Cells keyed by `(hips_survey, nside, ipix, tier, cell_size, cell_w, cell_h, cell_i, cell_j)` — no FK to `dso`. NSIDE=8 (via `astropy-healpix`, BSD-3) partitions the sphere into 768 equal-area regions. Every cell inside a region shares the region's tangent plane and tiles pixel-perfectly at shared edges (hips2fits with custom `wcs=<JSON>` header). Three tiers selected by rig major FOV: `narrow` (≤1°, 0.5° cells @ 800×800), `med` (1–3°, 2° cells @ 800×800), `wide` (>3°, 8° cells @ 1024×1024). Two DSOs whose composites overlap inside a region share every cell in the overlap — the defining performance win over the DSO-keyed `thumbnail_cache`. Same long-poll + 1-hour error-backoff contract. `SkyPreview` on the DSO Catalog detail panel reuses the same tiles with an auto-tier zoom-to-fit driven by `previewSpecForDsoSize`.

FOV Simulator (v0.18.0 rewrite): drag-to-rotate orange sensor rectangle overlaid on a pannable `SkyTileComposite`. Staged mount — centre cell first with `waitMs=4000`, then distance-sorted remainder. Grid promotes 1 → 3 → 5 cells wide as the centre renders so the backend's 8-slot semaphore focuses on the target. Scroll-wheel zoom (native wheel listener — React's `onWheel` is passive). Default zoom: rig rect fills 75% of the viewport. Annotation click takes precedence over pan (JSX z-order). Re-centre button preserves zoom + rotation; R resets everything. Annotation overlay uses `projectRaDecInRegion` (single region tangent shared with the cells) — no per-tile candidate selection needed, alignment is pixel-exact across all cells. Labels counter-scale by `1/zoom` to stay constant CSS size during zoom.

- **Route:** `/planner`
- **API:** `GET /api/planner/targets` (+ `q`, `restrict_tonight`, `type`, `constellation`, `has_distance`, `horizon_id`, `coverage_min_pct` / `coverage_max_pct`, `filter_intent`, multi-`sort`), `GET /api/planner/targets/{dso_id}/score` (v0.21.0 — single-target scoring for the detail panel), `GET /api/planner/targets/{dso_id}/sky-track` (+ `horizon_id`), `GET /api/planner/targets/{dso_id}/annual-hours` (+ `horizon_id`, `moon_sep_deg`), `GET /api/planner/thumbnails/{dso_id}` (optional `wait_ms` long-poll), `GET /api/planner/sky-tile-grid` (layout math), `GET /api/planner/sky-tile` (cell bytes, optional `wait_ms`), `POST /api/planner/thumbnails/cache/clear`, `GET /api/planner/thumbnails/cache/stats`, `POST /api/planner/sky-tile/cache/clear`, `GET /api/planner/sky-tile/cache/stats`, `GET /api/planner/dsos/in-region`
- **Key backend:** `services/planner_visibility.py` (`PlannerLocation` + `PlannerHorizon` + `VisibilityTimeSeries` v0.21.0), `services/planner_scoring.py` + `services/planner_scoring_constants.py` (v0.21.0), `services/planner_sky_track.py`, `services/planner_annual_hours.py`, `services/planner_now_status.py` (v0.19.0 day/night fix), `services/thumbnails.py` + `services/hips_client.py`, `services/sky_tiles.py` + `services/sky_tile_cache.py` (v0.18.0), `services/rig_calculators.py:compute_coverage_pct`, `services/horizon.py:resolve_horizon_altitude`. `api/planner.py` catalog `PLANNER_SORT_FIELDS` (15 fields incl. `score_pct`) + stable-Timsort `_sort_items` helper.
- **Key frontend:** `pages/PlannerPage.tsx` (v0.19.0 card list + multi-sort panel + v0.21.0 filter-intent select), `components/planner/{ThumbnailCell,PlannerTargetCard,PlannerSortPanel,SkyPositionGraph,PlannerDetailPanel,FovSimulator,SkyTileCell,SkyTileComposite,DsoAnnotationOverlay,DsoAnnotationPopover,BestTimeOfYearChart,horizonMenuItems,ScoreChip,ScoreBreakdownSection,FilterIntentSelect}.tsx`, `components/settings/PlannerScoringSection.tsx`, `components/dso/SkyPreview.tsx`, `lib/{plannerSortFields,dsoAnnotations,skyPreviewExtent,plannerScoreColors}.ts`, `stores/{plannerStore,thumbnailCacheStore}.ts`, `api/planner.ts`, `api/horizons.ts`.
- **Schema:** migrations 0017–0019 (`thumbnail_cache`), 0020 (`sky_tile_cache`, v0.18.0), 0021 (multi-horizon reshape, v0.19.0), 0022 (`dso_external_ref` + `dso_catalog_source.category` widen, v0.20.0). v0.21.0 scoring adds no migration — new settings absorbed by the KV `settings` table via Pydantic defaults.
- **Settings (v0.19.0 + v0.21.0):** `planner_min_visibility_hours` (2h), `planner_max_magnitude` (12), `planner_min_size_arcmin` (5'), `planner_frames_well_min_pct` (15), `planner_frames_well_max_pct` (90), `planner_moon_sep_deg` (0 — "Ignore moon"; default for the Best time of year chart), `thumbnail_cache_max_mb` (500; slider max 5 GB). **Plus 25 `scoring_*` fields (v0.21.0):** 4 weights, 7 moon sensitivities, 7 moon min-separations, cluster modifier, observability altitude, frame-fit ideal + spread, 3 chip thresholds, 2 hard-gate caps — all configurable in Settings → Planner Scoring with tooltips. **Removed (v0.19.0):** `planner_min_altitude_deg` (altitude floor now lives per-horizon on the location).
- **Deliberate deviations from spec:** moon distance is **closest approach during the visibility window**, not at-peak — the at-peak value can be misleading when the moon is below horizon at transit but rises during the visible window. Meridian + Max altitude are always rendered as two separate card lines (no collapse-when-equal) for consistent vertical rhythm in the card list.

**v0.30.0 Target Wishlist & Planning.** Wishlist tab for bookmarking DSOs, organizing into named sections (drag-and-drop with dnd-kit Multiple Containers), and creating plan assignments (location + horizon + rig + date ranges + notes). Interactive annual chart with shift-drag date selection, draggable hours threshold, and auto-generate. Calendar view shows a year-agnostic Gantt chart of planned imaging windows with section-colored bars.

**v0.31.0 Moon Quality Weighted Visibility.** Moon illumination/separation filter with checkbox + `Illumination ≤ / AND|OR / Separation ≥` controls (shared `MoonFilterControls` component). Best Time of Year chart shows dual curves (raw blue + effective orange), moon phase backdrop, and a moon max-altitude line on the right y-axis — all toggleable via clickable legend. Moon impact scoring reworked to a two-component model (sky glow 60% + proximity 40%) so a bright moon far from the target still penalises broadband. Meridian timing now uses the true transit time with a 2h buffer. Illumination formula fixed from `(1+cos)` to `(1-cos)` (elongation vs phase angle). Detail panel sections (Score, Sky Position, Best Time of Year) are collapsible; sky position chart widened to match.

**v0.34.0 DB-backed UI state + UX cleanup.** All planner UI state (location, horizon, rig, sort, filter intent, type/catalog/constellation chips, sliders, tab, detail panel, calendar pickers — everything except free-text search) moved from the Zustand `persist` middleware (browser localStorage, per-origin) to the `settings` KV table. Bridged by `frontend/src/lib/usePlannerSettingsSync.ts`: hydrates the in-memory store on mount, rAF-coalesces multi-setter ticks into one PUT, skips no-op writes via a `lastPushedRef` JSON diff. One-time legacy `nightcrate-planner` localStorage migration carries existing entries forward. UX: "Clear filters" moved inside the Filters panel; "Reset sorting" button added inside the Sort panel; CatalogFilter / TypeFilter / ConstellationFilter / FilterIntentSelect inner inputs are `readOnly` so the iPad soft keyboard never appears. Planner thumbnails now retry hard fetch errors (5xx, 204, network blip) under the same backoff budget as the 1×1 placeholder. WishlistCalendarView snap entries carry their underlying `Date` (round-tripping through `d3.scaleTime().invert` was returning ~1 ms before the snap target due to float interpolation, dropping the bar tooltip's range label near the today line).

### DSO catalog

**Status:** `[shipped]` (v0.14.0 MVP + v0.15.0 augmentation + v0.20.0 external references)

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
- **Data:** not in repo; downloaded to `APP_DIR/catalogs/{openngc,vizier,github/50mgc,wikidata}/`. NightCrate editorial CSVs bundled at `backend/src/nightcrate/data/catalogs/nightcrate/` (`dso_augment.csv`, `sharpless_crossref.csv`, `barnard_crossref.csv`, `dso_external_refs.csv`).

**v0.20.0 — external references (Wikidata + Wikipedia); v0.21.1 — SIMBAD + NED extension:** provider-agnostic `dso_external_ref` child table populated by two loaders. Wikidata SPARQL fetch pulls catalog-cross-referenced entities (NGC / Messier / Sharpless / Barnard / PGC / UGC via P528/P972 + P3208/P4095/P6340 shortcuts) + their English Wikipedia sitelinks + SIMBAD IDs (P3083); matching runs in-DB against `dso_designation.search_key`. Editorial CSV override (`dso_external_refs.csv`, ships empty) runs last and always wins — supports upsert and suppression rows across all four providers. **Chips on the detail panels:** Wikipedia (always when present) + SIMBAD (always, fallback from primary_designation when Wikidata has no P3083) + NED (extragalactic-only, always synthesised from primary_designation via NED's tolerant `byname` resolver — Wikidata's P2528 turned out to be earthquake magnitude, not NED). Wikidata QIDs are stored silently, filtered at render time. Admin endpoints: `GET /api/admin/catalogs/wikidata/remote-version` (now reports `installed_query_version` vs `current_query_version` so the admin UI's "Update available" chip flags SPARQL-shape changes), `POST /api/admin/catalogs/wikidata/fetch`. Schema: migration 0022 creates the table with `{wikidata, wikipedia}` CHECK; migration 0023 widens to `{wikidata, wikipedia, simbad, ned}` via the SQLite table-rewrite pattern.

### Image Analyzer (renamed from Image Viewer in v0.33.0)

**Status:** `[shipped]`

Multi-format viewer: FITS, XISF (clean-room parser, no GPL dependency), PixInsight projects (.pxiproject), PNG, JPEG, TIFF (including float32). Archive browsing (zip, tar, tar.gz, tar.bz2, tar.zst, 7z) with in-memory extraction. PixInsight-compatible auto-stretch (STF with avgDev). Per-channel statistics (median, MAD, avgDev, SNR, CIE L*a*b* a*). Canvas-based histogram with R/G/B/Luminosity channels, log/linear scale. Client-side pixel inspector with magnifier, hex color, XKCD named color. FITS header viewing and editing (batch update/add/delete with structural keyword protection). Recent files tracking. GPU-accelerated stretch and stats via mlx/cupy with numpy fallback. **v0.33.0:** clickable Stretched/Linear pill override, improved linearity detection (header keyword search + mid-range fraction check).

**Aberration Inspector** tab: star detection via sep, configurable sample grid with per-square metrics, draggable grid squares, tile preview with ellipse overlays. Results cached in SQLite with TTL-based cleanup.

**Identify tab (v0.29.0).** Detects WCS from FITS headers (CD matrix + CDELT/CROTA forms) or plate solves via ASTAP, then overlays DSO annotations on the image using astropy WCS pixel projection. SVG annotation overlay with ellipses + labels, colorblind-safe palette. Right detail panel shows astrometric solution + selected object info (designations, distance, external links). Bottom DSO grid is sortable with bi-directional selection sync (click grid ↔ highlight marker). Type group filter chips + min-size slider. ASTAP `-speed slow` retry on failure; progress streaming via `GET /progress` + `POST /cancel`.

**Tablet support (v0.34.0).** Pinch-to-zoom + one-finger pan via native touch handlers + direct DOM transform during gesture (state syncs on touchend). Long-press enters pixel-inspect mode with a floating crosshair. iPad pixel inspector uses a single 301×301 sampling canvas + 9-arg `drawImage` to copy just the patch region per sample — full-image canvases silently fail to allocate on iOS WebKit. Pre-warm at 1:1 behind a black cover on tablet to avoid WebKit's lazy GPU-layer cascade on first pinch. Viewport meta sets `maximum-scale=1.0, user-scalable=no` and the container preventDefaults Apple's proprietary `gesturestart`/`change`/`end` events to keep iPadOS from running its own pinch-zoom in parallel.

- **Route:** `/image-analyzer`
- **API:** `/api/images/*`, `/api/files/*`, `/api/aberration/*`, `/api/plate-solve/detect-wcs`, `/api/plate-solve/annotate`, `/api/plate-solve/progress`, `/api/plate-solve/cancel`
- **Key backend:** `services/imaging.py`, `services/fits_io.py`, `services/xisf_io.py`, `services/pxiproject_io.py`, `services/standard_io.py`, `services/archive_io.py`, `services/aberration.py`, `services/image_annotations.py`, `services/image_annotation_models.py`

### Weather

**Status:** `[shipped]`

7-day imaging quality forecast with hourly detail. Composite 0–100 quality scores per night with weighted factors: sky clarity (35–40%), seeing (25%), transparency (15–25%), moon (0–15%), wind calm (10%). Broadband/narrowband weight sets toggle via moon penalty setting. Cloud gating multiplies non-sky factors by √(sky_clarity/100). Seeing estimated via blended surface (JAG Lab) + wind-shear (Trinquet/Cherubini) models. Transparency scored from PWV + AOD + humidity + visibility with graceful fallback tiers. Dew risk classification from temperature–dew point spread with safe window computation.

**UI:** Daily card view with quality badge (Excellent/Good/Marginal/Poor, sequential blue palette). Hourly timeline with D3 SVG: darkness gradient, moon polyline, score factor grid, weather details. Location selector from saved locations. Moon phase icon with terminator rendering. Methodology help accordion. Metric/imperial unit toggle.

- **Route:** `/weather`
- **API:** `/api/weather/forecast`, `/api/weather/hourly/{date}`, `/api/weather/methodology`
- **Data sources:** Open-Meteo (standard + ECMWF for PWV + Air Quality for AOD)
- **Key backend:** `services/weather.py`, `services/astronomy.py`, `services/seeing.py`, `services/transparency.py`, `services/dew.py`, `services/imaging_quality.py`
- **Hourly astro↔weather join is by absolute UTC** (nearest-match), not wall-clock `HH:MM`, so the per-hour moon/darkness columns stay correct when a location's display `timezone` differs from its `geo_timezone` (remote-observatory setups). `compute_hourly_astro` pads its grid ±1h so the table's pre-sunset / post-sunrise context columns have real astro data (v0.38.1).
- **Reference:** `docs/weather-algorithms.md`

### Settings and admin

**Status:** `[shipped]`

**Settings:** theme (light/dark/browser), GPU acceleration toggle, max worker cores, file browser favorites and last path, aberration cache TTL, weather cache TTL, weather moon penalty toggle, weather units (metric/imperial), calculators clock order, ASTAP executable path, thumbnail/sky-tile cache budgets, 25 `scoring_*` fields (planner scoring weights and thresholds), `planner_*` fields (min visibility hours, max magnitude, min size, size-in-frame range, moon separation, filter intent, sort order, selected location/horizon/rig, active tab, detail panel state, calendar pickers — everything except free-text search). As of v0.12.1, stored as one row per preference in the `settings(key, value_json, updated_at)` key-value table (migration 0011 — reshaped from the previous singleton JSON blob). `core/config.py:Settings` remains the Pydantic source of truth; adding a new field still requires no schema migration.

**Admin:** Multi-database support with first-run setup wizard (three scenarios: fresh, available DBs, all unavailable). Create, register, activate, remove databases — Create now auto-activates + reloads. Database list alphabetical with the active row inlined. DB hot-swap via `set_db_path()` + page reload. Filesystem browser with shortcuts (Home, Documents, App Data) and directory creation. App info display. Equipment re-seed trigger.

- **Routes:** `/settings`, `/admin`
- **API:** `/api/settings`, `/api/admin/*`, `/api/health`, `/api/weather/cache/{stats,clear}`

### Calculators

**Status:** `[shipped]`

Standalone mini-app with 12 astronomer/astrophotographer utilities grouped into four categories. Each calculator is backed by its own API endpoint so the math is equally usable from any external client — the frontend does no math beyond live-tick display.

**Calculators:** Lat/Long Converter (sexagesimal ↔ decimal), RA/Dec ↔ Alt/Az (location-aware, astropy-backed), Clocks (Local / UTC / LST / JD / MJD + Location's Display Timezone + Location Timezone; drag-to-reorder), Tonight at a Glance, Angular Units, Linear Units, Pixel Scale, Field of View, File Size, Airmass (Kasten-Young), SQM / Bortle / NELM, Temperature. **Tonight at a Glance** was promoted to its own top-level nav entry in v0.27.0 (`/tonight` route, `TonightPage.tsx`).

- **Route:** `/calculators[/:calcId]`
- **API:** `/api/calculators/*` (13 endpoints)
- **Key backend:** `services/calculators.py`, `services/coordinate_format.py`
- **Frontend:** `pages/CalculatorsPage.tsx`, `components/calculators/*`, `api/calculators.ts`, `stores/calculatorsStore.ts`
- **Shared primitives:** `CalculatorLocationBar` (location picker for the aware calculators), `CalculatorSidebar` (Equipment-style TreeView), `CalculatorAboutSection` (reused from rigs), `RigPickerMenu` (auto-populate from a rig — Pixel Scale / Field of View / File Size; loads focal length, pixel size, sensor dims, ADC bit depth from the selected rig and leaves fields editable)
- **Math rendering:** KaTeX via `react-katex`. `components/calculators/Math.tsx` exposes `<Inline>` / `<Block>` wrappers used in the About sections of Pixel Scale, Field of View, File Size, Airmass, SQM/Bortle/NELM, Temperature, and the Weather methodology accordion
- **Deps:** `@dnd-kit/{core,sortable,utilities}` for drag-to-reorder (MIT); `katex` + `react-katex` + `@types/react-katex` for math rendering (MIT)

### API documentation

**Status:** `[shipped]`

Auto-generated OpenAPI/Swagger docs from FastAPI with organized tag groups (File Browser, Image Analyzer, Aberration Inspector, Equipment, Lookup Tables, Locations, Weather, Settings, Administration, Diagnostics). Accessible via in-app API Docs page.

- **Route:** `/api-docs` (in-app page), plus standard FastAPI `/docs` and `/redoc`

### Diagnostics / Activity Console

**Status:** `[shipped]`

ASGI middleware records every request with start timestamp, duration, status, and activity label. Frontend dialog shows requests grouped by activity with expandable detail tables. Activity labels propagated via `X-Activity` header or `_activity` query param. Diagnostics requests excluded from tracking.

- **API:** `/api/diagnostics/*`
- **Frontend:** `components/ActivityConsole.tsx`

---

### PHD2 Guide-Log Analyzer (Passes A + B + C + D-1 + D-2 + D-3)

**Status:** `[shipped]` (Passes A–D-3 shipped; the FFT/spectrum and unguided-RA passes from D-2/D-3 were removed in subsequent cleanup as unreliable. v0.34.0 adds tablet touch + DB-backed recent files + viewport export.)

First pass of a ten-version arc that delivers a PHD2 guide-log analyzer, aiming to replace the community's "post log to the PHD2 Google Group and wait for expert" workflow with an in-app parser + charts + (eventually, in v0.31.0) an automated diagnostic engine. Functional spec: `docs/nightcrate-phd2-analyzer-spec-v4.md`. v0.22.0 delivers a format-tolerant parser (handles ASIAIR's blank app-version field, irregular header key separators, 18-vs-19-column row arity, DROP frames, locale-decimal recovery, backward timestamp jumps), a D3 time-series chart with RA/Dec traces + correction bars + SNR/mass sub-panels + crosshair cursor + row-packed vertical-line event markers, a five-phase calibration plot with derived angle/rate/parity, per-section + viewport summary panels (collapsible), and a warnings hover-tooltip. Settle-window exclusion in the quality metrics (originally Pass B scope) was pulled forward during the polish round because inflated Peak/RMS numbers from dither excursions were actively misleading. Standalone-first (spec §4.1) — no persistence yet (in-process TTL cache only); catalog integration lands in v0.34.0.

- **API:** `/api/phd2/parse` (POST), `/api/phd2/cache/stats` (GET), `/api/phd2/cache/clear` (POST), `/api/phd2/export` (POST — viewport export to PHD2-format text), `/api/phd2/recent` (GET/POST/DELETE — DB-backed recent-files history)
- **Backend services:** `services/phd2_parser.py`, `services/phd2_metrics.py` (with `_settle_intervals` state-machine), `services/phd2_models.py`
- **Frontend:** `pages/Phd2AnalyzerPage.tsx`, `components/phd2/{TimeSeriesChart,CalibrationPlot,ScatterPlot,FftChart,RigSelectBar,StatsPanel,EventList,WarningsDrawer,SectionNavigator,SectionInfoPanel,SectionDataTab}.tsx`, `lib/phd2GuidingMetrics.ts` (client-side metrics helper for Viewport / Selection Summary + toggle-aware recompute), `lib/phd2RecentFiles.ts` (per-log rig persistence), `api/phd2.ts`

v0.23.0 Pass B added: drift + oscillation metrics on both Section + Viewport Summary panels; a ScatterPlot component (dx vs dy with 1σ / 2σ dispersion ellipse + centroid); a collapsible EventList that pans the chart to a clicked event via a new `scrollToTime` imperative handle on TimeSeriesChart.

v0.24.0 Pass C added: multi-additive range zones on the chart — Shift-drag accumulates selection bands (teal), Shift+Alt-drag accumulates exclusion bands (hatched grey); the viewport metric panel shows union(selections) − union(exclusions) and its title folds to "Selection Summary" when any selection exists. Per-zone × close buttons render outside the main-panel clipPath at the top-right of each band. Toolbar actions: Include in view / Exclude in view (adopt the current X-zoom domain as a new zone) and Clear all (wipe both zone sets). Plus: copy-stats-to-clipboard icon on the StatsPanel header (TSV via `navigator.clipboard` + transient Snackbar); recent-files history (`lib/phd2RecentFiles.ts`) localStorage-backed, 10-entry cap.

v0.25.0 Pass D-1 — **Metric Foundation** (-aligned). Backend `phd2_metrics.py` rewritten so every metric reproduces from `AnalysisWin.cpp` per spec v4 §5.2: RMS = population standard deviation (not RMS-from-zero); RA drift = corrections-subtraction `(ra_last − ra_first − Σ ra_guide) / Δt × 60`; Dec drift = unguided-frames-only `y_accum` slope × 60; PA error in arcmin via Barrett's `3.8197 · |drift| · pixel_scale / cos(δ)`; sign-preserving peak; oscillation counts zeros as positive; elongation `|lx − ly| / (lx + ly)` over the rotated mount-axis frame; duration split into `total` + `included`. The TS port in `phd2GuidingMetrics.ts` mirrors all formulas exactly. ScatterPlot rotation switched from PCA to `θ = atan2(cov_xy, var_x)` form. Discovered that **parser silently misses declination on modern PHD2 (incl. ASIAir-bundled) logs** — its PA-error reading is wrong on those logs; NightCrate's is correct. Test `test_pa_pinned_at_high_declination_69` pins this regression anchor at δ=69° / 18.34′. UI rework: vertical scale sliders flank the chart (replaced four dropdowns / toggles); three-tab structure (**Guiding** / **Dispersion** / **Data**); Section / Viewport / Selection summary panels moved into the left nav; new **SectionInfoPanel** surfaces parsed `SectionHeader` fields grouped into Optics / Camera / Mount / Sky / Star+lock / Algorithms / Dither / Profile / Other; recent-files Autocomplete dropdown on the path field. SNR / Mass median-anchored zoom (axis lo locked at data min, axis hi via slider, slider clamps above the median so the bulk can never get pushed off the top).
- **Route:** `/phd2-analyzer` (top-level, nav entry auto-appended for users with saved nav orders)
- **Sample log:** `sample_data/session_logs/ASIAir/PHD2_GuideLog_2026-03-07_193345.txt`

v0.26.0 Pass D-2 — **Spectrum Conformance + Worm Markers** (spec v4 §6.1, §6.6). New backend service `services/phd2_fft.py` ports `AnalysisWin.cpp` FFT pipeline end-to-end: filter → MIN_ENTRIES=12 + IQR/median > 0.20 cadence guard + constant-data guard (each surfaces as a structured `skip_reason`) → least-squares drift subtraction → Akima spline resample (`scipy.interpolate.Akima1DInterpolator`, scipy added as a backend dep) → Hamming window → `numpy.fft.rfft` → 4/N amplitude scale → MAD-σ peak detection (`median + 3·1.4826·MAD`) with ±5% dedup, top-5 cap. Worm-period markers via `_build_worm_marker`: rig with worm-drive mount + `worm_period_seconds` set → vertical marker + matching-peak chip; otherwise heuristic fallback (largest peak in [300, 800] s above 0.5″) labelled "uncertain". Migration `0024.mount_worm_period.sql` adds `mount.worm_period_seconds REAL` and rebuilds `rig_summary` to expose `mount_drive_type` + `mount_worm_period_seconds`. New `RigSelectBar` toolbar component persists per-log via `phd2RecentFiles.selectedRigId`. New **Spectrum** tab (now index 1, between Guiding and Dispersion; Data shifted to index 3) renders the `FftChart`: log-log axes, top-5 peak dots (subtle white outline), seeing-band shading at < 5 s, X-axis -30° tick rotation, panel clipPath so log-scale values below the Y floor stay contained, always-on hover hairline that snaps horizontally to peaks within ±8 px (snap is X-only — the user's mental model is "the line is near the peak"), tooltip with full Period / Amplitude / Peak-to-peak / RMS readout when snapped + nearest-bin per-trace amplitudes when free, fixed vertical anchor so the tooltip doesn't bounce on snap, content-aware auto-resize. Cache key extended with `rig_id` so rig variants don't pollute each other.

v0.27.0 Pass D-3 — **Unguided RA Reconstruction** (spec v4 §6.2 + §6.1.8). New backend service `services/phd2_unguided.py:reconstruct_unguided_ra(section, *, undo_corrections=True)` ports recurrence `move = raraw − prev_raraw − prev_raguide` cumulative-summed; mount-kind-agnostic so AO frames with valid star data accumulate alongside Mount frames (the AO's correction lives in `ra_guide_px` exactly like a Mount pulse). DROP frames (`ra_raw_px is None` OR `error_code != 0`) emit `None` without advancing `prev_*` — the next valid frame's `move` correctly spans the gap. Output is 1:1 with `section.samples`. `services/phd2_fft.py` refactored to expose `compute_unguided_fft(samples, unguided_ra_px, *, pixel_scale)` that runs the v4 §6.1 pipeline (drift subtraction, Hamming, Akima, MAD-σ peaks) on the unguided trace; the new private `_compute_fft_for_series` helper is the shared core for RA / Dec / Unguided. `_build_section_analysis` runs the recurrence over the FULL section (chart overlay) and the FFT over the settle-excluded subset (spectrum), filtering in lockstep via a small `_filter_unguided_to_stats` helper. `SectionAnalysis` Pydantic shape gains `unguided_ra_px: list[float | None] | None` and `fft_unguided: FftResult | None`. Frontend wiring: `TimeSeriesChart` adds an `unguidedRa` prop, a `raUnguided` visibility key (off by default), a teal dashed third path inside the main panel using `xScale` + `yDistScale` and a `.defined()` predicate that breaks the line on `null`, a legend chip with `disabled` support when prop is null, and a conditional tooltip row showing the unguided value in the toolbar's selected unit. `FftChart` adds an `fftUnguided` prop, a `showUnguided` toggle, a teal dashed trace + peak dots, a three-state `TraceKind` union with `TRACE_COLOR` / `TRACE_PEAK_LABEL` lookup tables, a free-cursor tooltip third row, and a snapped-peak tooltip with three colour variants. 12 new tests (10 unguided + 2 API).

Incidental fix with broader reach: `_moon_rise_set` in `services/astronomy.py` was widened from the sun's 24 h noon-to-noon grid to a dedicated 48 h midnight-anchored window. The **Tonight at-a-glance calculator** now reports actual moonrise times even when the moon rose earlier in the day.

### Projects (v0.35.0)

**Status:** `[shipped]`

Imaging project management with **save-as-you-go** editing and pre-calculated images. Projects are first-class entities supporting both manual/incremental use (start with a name + finished image) and full ingest (future — v0.39.0+). Each project has a multi-image gallery with drag-to-reorder, main image designation (star), and per-image notes. **v0.37.0 replaced the original stage-then-Save model: every edit persists immediately** (text fields on blur/Enter; image add/remove/reorder/main/crop on the click) — no Save/Cancel, no staging. Pre-calculated images (full ~4000px + 3 thumbnails at 800/400/180px) are generated eagerly when images are added, downsampled before stretching for speed, serialised through a render lock to avoid MLX Metal concurrency crashes. Workspace folder structure: user-named folder containing `nightcrate.db` + `project_data/` — self-contained and portable.

- **Route:** `/projects` (list), `/projects/:id` (detail — Overview + Plate Solve tabs)
- **API (projects):** `GET/POST /api/projects`, `GET/PATCH/DELETE /api/projects/{id}` (get / metadata update / soft-delete), `POST /restore`, `DELETE /permanent`, `POST/DELETE /api/projects/{id}/images`, `PUT /images/order`, `POST /images/{id}/main`, `PATCH /images/{id}` (notes), `PUT /api/projects/{id}/thumbnails` (crops), `GET /images/{id}/rendered/{variant}`, `GET /thumbnail?size=…`
- **API (plate solve, v0.37.0):** `POST/GET/DELETE /api/projects/{id}/solve`, `PUT /api/projects/{id}/solve/objects/{dso_id}` (toggle main), `GET /api/projects/{id}/solve/image/{variant}`
- **Key backend:** `api/projects.py`, `api/project_models.py`, `api/project_solve.py` + `project_solve_models.py` (v0.37.0), `services/project_images.py` (pre-calc), `core/app_config.py` (workspace model)
- **Key frontend:** `pages/ProjectsPage.tsx`, `pages/ProjectDetailPage.tsx`, `components/projects/{ProjectCard,ProjectGalleryCard,ProjectFormDialog,ImageGalleryStrip,ThumbnailCropEditor,ProjectPlateSolveTab}.tsx`, `components/plate-solve/DsoAnnotationOverlay.tsx` (shared with Image Analyzer), `api/{projects,projectSolve}.ts`
- **Schema:** migrations 0029 (`project` + `project_image`), 0031 (drop UNIQUE on name), 0032 (`project_thumbnail`), 0033 (drop `staged` column — save-as-you-go), 0034 (`project_solve` + `project_dso`), 0035 (`project_rig` + `project.location_id` + `project_session` + `project_filter_goal` — v0.38.0), 0036 (`project_target` — persistent main targets; backfills from existing solve mains)

**v0.36.0 — Thumbnail Crops + Gallery View.** User-defined crop rectangles per thumbnail size (small 1:1, medium 1:1, large 4:3) stored in `project_thumbnail` table. Crop editor dialog with three tabs, draggable/resizable rectangle with aspect-ratio constraint, source image selector. Cropped thumbnails generated server-side and cached on disk at `{project_dir}/thumb_crop_{size}.jpg`. Projects page has three view modes: Gallery (4:3 cards), List (120px medium thumbnail + description), Compact (56px small thumbnail). "Show retired" toggle to view/restore/delete soft-deleted projects.

**v0.37.0 — Target Identification + DSO Linking.** Two parts. (1) **Save-as-you-go refactor** — dropped the stage + Save/Cancel model for immediate persistence (migration 0033 drops `project_image.staged`); rationale: staging doesn't scale to the v0.39.0+ sessions/sub-frames ingest. (2) **Plate-solve DSO linking** — a project gets one standalone (non-gallery) plate-solve image; solving stores the WCS solution (view-only — delete to re-solve) plus **every** in-FOV catalog object in `project_dso` (one auto-flagged main, nearest centre + largest; multi-main via star toggle). Deleting the solve cascades its objects + the rendered image behind a confirm dialog. A "Plate Solve" tab shows the image with a catalog-annotation overlay (shared `DsoAnnotationOverlay` — mains teal / others blue, colorblind-safe), a read-only solution summary, and the object list; mains surface as chips on the Overview. Storing all objects (not just mains) is deliberate — powers a future cross-project DSO search (search/completion UI deferred). Also fixed a pre-existing bug: solving an archive entry failed with "I/O operation on closed file" (header reading closes the BytesIO) — the solver now reads bytes once and hands fresh buffers to each consumer.

**v0.38.0 — Project Metadata + Manual Imaging Sessions.** Substantial expansion of the project domain. New entities: `project_rig` (multi-rig junction), `project.location_id` FK, **`project_session`** (manual capture batches — filter, exposure, gain, sub count, optional date+rig; derived integration), `project_filter_goal` (per-line goals), **`project_target`** (persistent project↔dso link; backfilled from existing solve mains in migration 0036). The detail page is now four tabs (Overview / Sessions / Plate Solve / Notes); the Overview switched to a magazine-style float layout (520-px image left, scrollable description right; full-width thumbnails below; left-aligned integration chart; capped-width sections). **Main targets unified** — `project_target` is the single source of truth; toggling a main on the Plate Solve tab and adding one via "+" on the Overview edit the same row, and `is_main` in the solve response is derived from `project_target` so **main targets survive `DELETE /solve`**. New manual session entry includes a grouped filter picker (My Rig group → Bandpass → other equipment by manufacturer), Binning select (1x1/2x2/3x3/4x4 default 1x1), rig defaults to the project's rig, and a duo-band filter (e.g. Optolong L-eNhance Ha+Oiii) double-counts into both line budgets via `filter_passband` (spec §12) while wall-clock total counts each session once. **Markdown editor** (`components/common/MarkdownEditor.tsx`) — reusable, default rendered view (react-markdown + remark-gfm, MUI-themed sx overrides), edit-icon toggles to a raw TextField. Used by Notes (full-tab) and Overview Description. Also tightened the moon phase namer in `services/astronomy.py` — principal phases (New, First/Last Quarter, Full) now span ~1 day each (±7°) instead of ~3.7 days (±22.5°), so the daily weather forecast no longer shows "Full Moon" for four consecutive days.

### Plate Solving (ASTAP)

Plate solving via ASTAP subprocess invocation. User configures the ASTAP executable path in Settings (with macOS `.app` bundle auto-resolution via `Contents/MacOS/`), then plate solves any image from the Image Analyzer toolbar. Two-tab UI: "Solve" (current image) and "From Reference Image" (pre-processed stars-only image with dimension validation). Automatically detects near vs blind mode from available coordinate hints (FITS header or target search). Equipment hints (Rig, Equipment, or Manual) provide FOV to ASTAP for faster solving. Results (RA, Dec, pixel scale, rotation, FOV) displayed in a dialog — no database persistence.

Handles all NightCrate image sources: filesystem files passed directly to ASTAP; archive and pxiproject images extracted to temp FITS with header keyword passthrough (focal length, pixel size, coordinates); XISF converted to temp FITS. File browser enhanced with `accept=*` mode for selecting extensionless Unix executables.

- **Route:** Image Analyzer toolbar button (no dedicated page)
- **API:** `POST /api/plate-solve/solve` (accepts image path, mode, optional RA/Dec/FOV hints), `POST /api/plate-solve/validate-reference-image` (validates reference image dimensions match), `POST /api/plate-solve/validate-path` (validates ASTAP executable, resolves `.app` bundles)
- **Key backend:** `services/plate_solve.py` (ASTAP invocation + `.ini` parsing + temp file pipeline + header passthrough), `services/plate_solve_models.py` (Pydantic shapes), `api/plate_solve.py` (endpoints), `services/coordinate_format.py` (`format_ra_hms`, `format_dec_dms`)
- **Key frontend:** `components/plate-solve/PlateSolveDialog.tsx` (tab UI + equipment hints + results table + copy), `pages/SettingsPage.tsx` (`AstapPathSection` with browse + validation), `api/plateSolve.ts`
- **Settings:** `astap_executable_path` (KV table, no migration)

### FITS Equipment Resolver (v0.39.0) — first ingest-arc component

**Status:** `[shipped]` (backend service only — no API/UI surface yet)

Deterministic string→equipment-row resolver: the foundation the v0.40.0+ folder-ingest pipeline sits on. Takes raw FITS header values (`INSTRUME` / `TELESCOP` / `FILTER`), normalizes them (NFKC → strip → collapse whitespace → drop control/zero-width chars → lowercase, punctuation preserved), and exact-matches against the FITS alias tables (no fuzzy matching). Four outcomes: `resolved`, `resolved_retired` (alias points at an `active=0` row), `unresolved` (records into `unresolved_equipment_observation` with a `seen_count`), `ambiguous` (a filter line name matched more than one filter in the rig). `FILTER` headers additionally canonicalize through a closed code-level line-name map (`Ha`/`Oiii`/…) and scope to the capturing rig's loaded filters via the existing `rig_filter_slot` table. Promotion of an observation to a confirmed alias is human-only (`confirm_unresolved_observation`); the resolver never auto-confirms. Caller owns the transaction. No migration and no seed — the alias + observation tables exist since migration 0005 and bootstrap empty.

- **Route / API:** none yet — pure service consumed by the ingest pipeline (v0.40.0+)
- **Key backend:** `services/equipment_resolver.py` (`normalize_alias`, `canonicalize_line_name`, `EquipmentResolver`, `RigContext`, `ResolverStats`, `confirm_unresolved_observation`)
- **Tests:** `tests/test_equipment_resolver.py` — 72 tests, 100% module coverage
- **Known limitation:** two physically distinct same-model cameras share one alias → resolves to whichever camera the alias points at; rig-level disambiguation deferred to v0.41.0

---

## Schema state

Current migration: **0036** (`project_target`). 36 migrations total (`0001`–`0036`).

**Recent migrations not detailed elsewhere:** 0025 (`target_wishlist` — `target_wishlist`, `wishlist_section`, `target_plan`, `target_plan_date_range` tables for the wishlist + planning system), 0026 (`rig_sort_order` — `sort_order` column on `rig` + `rig_summary` view rebuild), 0027 (`plan_filter_settings` — moon filter + threshold columns on `target_plan`), 0028 (`phd2_recent_files` — `id, path UNIQUE, opened_at` for DB-backed PHD2 recent-files history mirroring the image-analyzer pattern).

- **Core app:** `settings` (key-value table as of migration 0011 — one row per preference), `recent_files` — app preferences and state
- **Equipment (migrations 0005–0006, plus inline edits in v0.12.0):** 12 equipment tables, 10 lookup/reference tables, 5 junction tables, 2 child tables, 4 FITS alias tables, 1 view, `seed_loader_meta` — fully normalized equipment catalog. `is_mine` column + partial index added to 10 owned equipment tables in v0.12.0. `idx_camera_guide_sensor` added inline to 0006 in v0.12.1.
- **Locations (migrations 0007, 0012, inline-edited in v0.12.0):** `location` — user imaging sites with coordinates, light pollution (Bortle + SQM), `typical_seeing_low/high_arcsec` for rig calculator sampling assessment. Migration 0012 adds `active` soft-delete column.
- **Horizons (migrations 0014 + 0021):** `location_horizon` + `location_horizon_point` — per-location horizon profiles. Migration 0014 was the original 1:1 shape (one polyline per location); migration 0021 reshaped to **1:N** with `type ∈ {custom, artificial}`, `flat_altitude_deg` for artificial rows, partial unique indexes enforcing exactly-one-default-per-location and at-most-one-custom-per-location. Migration also seeded a `0° flat` artificial default for every pre-existing location that had no horizon.
- **DSO catalog (migrations 0015 + 0016):** `dso_catalog_source` (loader registry + file sha256), `dso` (canonical DSO with closed `obj_type` CHECK vocabulary, + `distance_pc` / `distance_method` / `common_name_augmented` / `surface_brightness_augmented` added in 0016; `distance_method` CHECK ∈ `{'50mgc', 'curated', 'redshift'}`), `dso_designation` (many-per-dso with closed 29-catalog CHECK vocabulary, `UNIQUE(catalog, identifier)`, partial unique index enforcing one primary per dso). Populated via fetch-on-demand from GitHub (OpenNGC + 50 MGC FITS) + VizieR (Sharpless, Barnard). NightCrate augmentation CSV (common names, non-galaxy surface brightness, curated distances) bundled in-repo under `data/catalogs/nightcrate/`.
- **DSO external references (migrations 0022 + 0023):** `dso_external_ref` table associating Wikidata QIDs / Wikipedia URLs / SIMBAD / NED links with canonical DSOs. `provider` CHECK enum widened from `{wikidata, wikipedia}` (0022) to `{wikidata, wikipedia, simbad, ned}` (0023). `UNIQUE(dso_id, provider, language)` plus a partial unique index `(dso_id, provider) WHERE language IS NULL` to handle the SQLite NULL-uniqueness quirk. Loaded from a Wikidata SPARQL pull + bundled editorial CSV; one Wikipedia article / Wikidata QID legitimately maps to multiple DSOs.
- **Target Planner thumbnails (migration 0017, extended by migrations 0018 + 0019):** `thumbnail_cache` — metadata for the LRU disk cache under `APP_DIR/thumbnails/` that serves DSS2 Color JPEG thumbnails fetched from CDS Aladin's hips2fits. FK cascade-deletes when a DSO disappears. `fetch_error` rows record failed attempts for a 1-hour backoff window. Files live on disk, not in the DB. v0.17.0 migration 0018 widens the variant CHECK to include `rig_framed` + `fov_simulator`, adds nullable `fov_major_deg_x1000` / `fov_minor_deg_x1000` columns, and rebuilds the unique index over `COALESCE(-1)`-wrapped FOV columns. Migration 0019 ALTER-adds `center_ra_deg_x1000` / `center_dec_deg_x1000` for panned FOV-simulator tiles at arbitrary sky centres, using a distinct `COALESCE(-999999)` sentinel so legitimate 0.0 RA (celestial equator) can't collide with NULL. Filenames are keyed on sky coordinates (NOT internal `dso_id`) so the cache survives DB recreation; `rehydrate_from_disk()` re-indexes JPEGs at startup before the orphan sweep.
- **Sky-tile cache (migration 0020):** `sky_tile_cache` — DSO-agnostic cell-keyed cache `(hips_survey, healpix_nside, healpix_ipix, tier, cell_size, cell_w/h, cell_i, cell_j)` that lets two DSOs whose views overlap share every cell in the overlap. Three tiers selected by rig major FOV (narrow ≤1°, med 1–3°, wide >3°). Same long-poll + error-backoff semantics as the thumbnail cache. Filenames also encode stable identity for cross-DB survival.
- **Aberration (migration 0004):** `aberration_analysis`, `aberration_stars` — cached star detection results with TTL
- **Weather (migration 0008):** `weather_cache` — forecast/archive/openmeteo_aq/ecmwf_pwv source-keyed cache
- **Rigs (migrations 0009–0010, 0013, 0024, 0026):** `rig`, `rig_filter_slot`, `rig_software` junction, `rig_summary` view — user-composed imaging templates. `rig_summary` view has been rebuilt four times: 0010 (expose `telescope_id`), 0013 (expose `sensor_adc_bit_depth`), 0024 (expose `mount_drive_type` + `mount_worm_period_seconds`), 0026 (expose `sort_order`).
- **Mount worm period (migration 0024, v0.26.0):** ALTER adds `mount.worm_period_seconds REAL`. Rebuilds `rig_summary` to expose `mount_drive_type` + `mount_worm_period_seconds`. Backfills 24 worm-drive seed mounts via direct UPDATE statements (sidesteps the seed loader's user-modified hash check, which would otherwise refuse to update existing rows after `worm_period_seconds` was added to mount's `seeded_fields`).

Authoritative DDL in `DB_SCHEMA_DDL.sql`. ER diagrams in `DB_SCHEMA.md`. LLM-facing seed-data + abbreviated-schema reference (for CSV authoring in Claude Desktop) in `LLM_DB_SPECS.md` at the repo root.

---

## Background processes and jobs

- **Startup (lifespan):** Migrations applied, seed loader runs (first-run populate / hash-based re-seed), stale aberration cache purged (TTL-based), stale weather cache purged (2× TTL), thumbnail + sky-tile on-disk caches rehydrated (filename → cache-key re-index, then orphan sweep)
- **No recurring background tasks** — no Celery, APScheduler, or asyncio task loops. All work is request-driven.
- **Caching:**
  - Image data + stats: in-memory with per-key locking (prevents redundant computation from concurrent requests)
  - Aberration analysis: SQLite cache keyed by (file_path, hdu, settings_json), TTL configurable (default 30 days)
  - Weather forecasts: SQLite cache keyed by source type, TTL configurable (default 6 hours, purged at 2× TTL)
  - Supplementary weather data (PWV/AOD): cached alongside forecast with non-fatal writes
  - Planner thumbnails: SQLite metadata + on-disk JPEGs under `APP_DIR/thumbnails/`. Keyed by sky coordinates (not DB ID) so cache survives DB recreation. LRU with configurable budget (default 500 MB). Background fetch via `asyncio.shield` with 8-slot semaphore against CDS. 1-hour error backoff.
  - Sky-tile cache: SQLite metadata + on-disk JPEGs. DSO-agnostic HEALPix cells; two DSOs whose views overlap share every cell. Same long-poll + error-backoff semantics as thumbnails.
  - Planner visibility: process-wide 4-entry LRU keyed on location + date + horizon; holds the vectorized alt/az snapshot for ~14 k DSOs.
  - Annual hours: 8-entry in-memory LRU with 15-min TTL.
  - PHD2 parse results: in-process TTL cache (no DB persistence).
  - Frontend: TanStack Query caches rig calculator + per-equipment detail fetches; `["mine-counts"]` invalidated on any star toggle. Zustand `persist` middleware for page-level state (image analyzer, PHD2, DSO catalog, calculators). Planner state persisted to backend `settings` KV table via `usePlannerSettingsSync`.

---

## External dependencies

- **Open-Meteo** — weather forecast data (standard API for main weather, ECMWF endpoint for PWV, Air Quality API for AOD). Free, no auth required. Called on weather page load (cached 6 h).
- **CDS Aladin hips2fits** (`alasky.cds.unistra.fr`) — DSS2 colour/red JPEG tiles for planner thumbnails and sky-tile cache. Free, no auth required. Called at runtime when a user views a planner target and the tile is not cached.
- **GitHub raw.githubusercontent.com** — OpenNGC catalog data + 50 MGC galaxy distance catalog (FITS binary table). Free, no auth. User-triggered via Admin → Catalogs (one-time fetch, cached on disk).
- **CDS VizieR** (`vizier.cds.unistra.fr` + India/South Africa mirrors) — Sharpless 2 + Barnard dark-nebula catalog data (TSV). Free, no auth. User-triggered via Admin → Catalogs.
- **Wikidata SPARQL** (`query.wikidata.org`) — DSO external references (QIDs, Wikipedia sitelinks, SIMBAD IDs). Free, CC0, no auth. User-triggered via Admin → Catalogs.
- Astronomy computations (moon, twilight, seeing) are all local via astropy + custom models. Rig calculators (image scale, FOV, guide suitability, guiding tolerance, sampling) are pure local math — no external calls.

---

## Notable architectural decisions already made

- **sep over photutils for star detection** — photutils is GPL; sep (LGPL) is license-compatible and faster for the extraction-only use case (aberration inspector).
- **Catalog in place (reference, don't move files)** — default behavior is to index files where they live on disk. File reorganization/copy is optional, never forced. Avoids breaking PixInsight project paths or user directory structures.
- **Clean-room XISF parser** — the only existing XISF library (PixInsight's) is GPL. `xisf_io.py` is a from-scratch implementation covering sub-block and single-stream compression (zlib, lz4, lz4-hc, zstd with byte shuffle).
- **No ORM, raw SQL via aiosqlite** — deliberate choice for SQLite. Pydantic handles data shapes; SQL handles queries. No SQLAlchemy, no Tortoise, no Peewee.
- **No fuzzy matching in FITS resolver** — the planned resolver uses exact alias lookup, not string similarity. Unresolved headers go to an `unresolved_equipment_observation` table for manual review. This avoids silent mismatches across similar equipment names.
- **avgDev not MAD for auto-stretch** — PixInsight's Screen Transfer Function uses average deviation, not median absolute deviation. This was validated against PixInsight's actual output.
- **Seed data in CSV, not migrations** — equipment reference data lives in `data/seed/*.csv` loaded by the seed loader, not in SQL migration INSERT statements. Keeps migrations structural-only and allows Fred to prepare seed data in Claude Desktop.
- **Key-value `settings` table (migration 0011 reshape)** — one row per Pydantic field on `core/config.py:Settings`. Adding a new setting still requires no schema migration: add the field with a default and the KV path absorbs it. (Replaced the original single-JSON-blob-row design.)
- **GPU abstraction via `core/compute.py`** — callers never import mlx/numpy/cupy directly. `get_array_module()` returns the right backend. Setting toggle applies immediately.
- **`::` virtual path separator** — used for both archive entries (`archive.zip::image.fits`) and pxiproject images (`project.pxiproject::0`). Consistent convention across all multi-image containers.

---

## Known limitations and rough edges

- **No catalog/ingestion pipeline** — the app can view and inspect images, but doesn't catalog them into projects/sessions/targets. This is the biggest missing piece for real workflow use.
- **Equipment exists but isn't connected to images** — FITS alias tables (`camera_alias`, `telescope_alias`, `filter_alias`) exist in the schema but the resolver that matches FITS headers to equipment rows is not built yet.
- **Weather seeing model is surface-level** — the wind-shear model improves accuracy when pressure-level data is available, but Open-Meteo's pressure-level coverage is limited. Seeing estimates should be treated as rough guidance, not observatory-grade predictions.
- **Single-chunk frontend bundle** — Vite warns about >500KB bundle. No code splitting yet. Acceptable for a local app but worth addressing if load times become noticeable.
- **`color="error"` uses MUI red** — a few error text instances use MUI's default red, which isn't ideal for red-green colorblind users. Should use the project's blue/orange palette instead.

---

## What's NOT built yet

Specs for future work live inline in `PLAN.md` (not as separate files).

- **FITS equipment resolver** — matches FITS header strings (`INSTRUME`, `TELESCOP`, `FILTER`) to equipment DB rows via alias tables. Schema support exists (alias tables, `unresolved_equipment_observation`); the resolver logic and UI are not built. See PLAN.md "FITS Equipment Resolver Spec" section.
- **Imaging core schema (rigs, projects, sessions, sub frames)** — the entire catalog/ingestion side. Equipment schema landed in v0.8.0–v0.10.0; what remains is the imaging-side schema (`rig`, `project`, `session`, `sub_frame`, calibration matching) and the ingestion pipeline (FITS parsing, N.I.N.A./ASIAIR/PHD2 log import). See PLAN.md "Imaging Core Schema" section.
- **WCS overlay / image annotation** — plate solving via ASTAP is implemented (v0.29.1) but the solved coordinates are display-only. No overlay of WCS grid, DSO labels, or star catalogs on the image viewer.
- **Desktop packaging** — Tauri wrapper for native app distribution (currently runs as local web app in browser).

Note: the seed loader (v0.10.0) and aberration inspector (v0.5.0) are shipped — they were listed here in an earlier version of this doc but are now implemented.

---
