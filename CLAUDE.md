# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Active development. See `PLAN.md` for the current version plan and task checklist.

Reference documents:
- `nightcrate-brief.md` — product vision, MVP features, architecture decisions
- `nightcrate-current-state.md` — living inventory of what's actually built (per-feature snapshots, statuses, file pointers). Use this when you need to know what exists today; use `PLAN.md` when you need version history; use this CLAUDE.md when you need architectural decisions, conventions, and gotchas.
- `NightCrate_Equipment_and_Technical_Context.md` — Fred's imaging setup, file formats, FITS headers, PHD2 log structure, known edge cases
- `DB_SCHEMA.md` / `DB_SCHEMA_DDL.sql` — authoritative schema docs
- `LLM_DB_SPECS.md` — LLM-facing seed-data reference (CSV columns, abbreviated schema)

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
- **Key Python libs:** `astropy`, `astroquery`, `lz4`, `zstandard`, `defusedxml`, `timezonefinder` (geo tz from coordinates), `scipy` (FFT pipeline). ASTAP integrated as external plate solver (subprocess, not a Python dependency).
- **Async ingestion:** asyncio task queue + `ProcessPoolExecutor` for CPU-bound FITS parsing (parallelizes across cores; SQLite writes stay on main process)
- **GPU acceleration:** `mlx` (Apple Metal, Apple Silicon) or `cupy` (NVIDIA CUDA, Windows/Linux) with numpy as CPU fallback. All array operations go through a thin `compute` backend module — callers never reference mlx/numpy/cupy directly.
- **User settings:** `gpu_acceleration` (bool) and `max_worker_cores` (int, `null` = `cpu_count - 1`) are user-configurable at runtime. Settings stored in the SQLite database (`settings` table, key-value rows).

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

**Layer separation (enforced):**
- `services/` — pure business logic. **No FastAPI, no DB session, no API-layer imports.** Service modules return Pydantic shapes that live alongside them in `services/*_models.py`.
- `api/` — HTTP boundary. Owns DB access via `get_db()`, request/response Pydantic wrappers, and orchestration. May import from `services/` but never the reverse.
- Reference pattern: `services/aberration.py` ↔ `api/aberration.py`. New PHD2 / planner / weather code follows the same shape.

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

- **Color-blind-friendly palette required** — Fred is red-green color blind. Use blue/orange instead of red/green; add pattern/shape differentiation where color alone would be used. Approved trio: blue / orange / teal. Reject purple + amber as too similar.
- **No question-mark icons** for help affordances; **no underlines on tooltips**; theme-aware D3 colors (don't hardcode `#fff` / `#000`).
- **Catalog by reference (don't move files)** is the default. File reorganization/copy is optional.
- **Hex colors must be 6-digit** (`#888888`, never `#888`) — gradient code appends alpha suffixes that break with 3-digit hex.

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
make test      # pytest (serial — full output, consistent ordering)
make test-fast # pytest -n auto (parallel via pytest-xdist, typically 2-3x faster)
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

- **Python 3.14 + ruff format:** ruff format may strip parentheses from `except (ValueError, IndexError):` turning it into Python 2 syntax. Avoid multi-exception `except` clauses; if needed, define a module-level tuple constant and reference it.
- **JSX Unicode escapes** are not interpreted in attribute strings: `label="°C"` passes 8 literal characters. Wrap in an expression: `label={"°C"}`. HTML entities like `&approx;` / `&asymp;` aren't in React's named-entity table — use `{"≈"}` instead.
- **MUI `<Typography variant=...>` overrides parent font styles.** A parent Box's `sx={{ fontSize, lineHeight }}` does NOT cascade — the variant brings its own (caption is 12px / 1.66, not the parent's 11 / 1.35). When sizing a fixed-height container by parent font math, force inheritance: `'& .MuiTypography-root': { fontSize: 'inherit', lineHeight: 'inherit' }`.
- **Migration policy** — never edit existing migration files. Always create new forward migrations (next sequential number in `db/migrations/`). Existing user data (locations, horizons, rigs, plans) must be preserved across upgrades.

## Cross-cutting patterns

### Settings (key-value schema)

Settings live in `settings(key TEXT PRIMARY KEY, value_json TEXT, updated_at TEXT)` (migration 0011). Each Pydantic field on `core/config.py:Settings` maps to one row. **Adding a new setting requires no migration** — add the Pydantic field with a default, and the KV path handles the rest. `get_settings()` merges rows, silently drops un-parseable JSON, falls back to defaults on `ValidationError`.

### Outbound HTTP

All outbound HTTP goes through `services/http_client.py:get()`. Uniform 30 s timeout, one 500 ms-backoff retry on transient failures (`TimeoutException`, `ConnectError`, 5xx), structured `[http] …` log lines. Callers still catch `httpx.HTTPError` and translate to their domain-appropriate HTTP status (typically 502).

### Logging

- `NIGHTCRATE_LOG_LEVEL` env var drives the `nightcrate` namespace logger level (INFO default; `DEBUG` for traces).
- Use structured prefixes on hot paths: `[weather-cache]`, `[http]`, `[open-meteo]`, etc.
- Router 500s (bare `except Exception`) MUST log via `logger.exception(...)` so server bugs leave a traceback.

### Shared router helpers (`api/_common.py`)

- `row_to_dict(row, *, extra_fn=None)` — aiosqlite.Row → dict with optional post-processor.
- `bool_fields(d, *keys)` — INTEGER(0/1) → Python bool, in place.
- `strip_seed(d)` — drops `source` / `seed_key` / `seed_hash` from response dicts.
- `integrity_guard(...)` — context manager translating `aiosqlite.IntegrityError.sqlite_errorname` into HTTP 409 (UNIQUE) or 422 (CHECK), with optional partial-index dispatch.

**Use these in every new CRUD router instead of reimplementing the pattern.** New equipment/lookup routes should also reach for the factories in `api/equipment_factory.py` (`build_lookup_router`, `build_equipment_router`).

### Path resolution

`services/path_resolver.py:resolve_path(path)` handles plain filesystem paths, pxiproject virtual paths (`project_dir::index`), and archive virtual paths (`archive.zip::entry`). Returns `(resolved_path_or_BytesIO, file_type, image_index, cache_key)`. Used by both `api/images.py` and `api/aberration.py`. **All new code that accepts user-supplied paths should go through this.**

## Feature areas — architectural notes

For full feature inventory and per-version history see `nightcrate-current-state.md` (living snapshot) and `PLAN.md`. This section captures only the **architectural invariants and gotchas worth knowing when modifying these areas**.

### Image Analyzer
- Format-agnostic core in `services/imaging.py`; per-format I/O in `services/{fits,xisf,pxiproject,standard}_io.py`. The XISF parser is **clean-room** — the GPL-licensed reference lib is off-limits per the dependency policy.
- **Auto-stretch uses PixInsight AutoSTF** (avgDev, NOT MAD). Constants: shadow clip = `median + (-1.25)·avgDev`, midtone target = 0.25, MTF self-inverse for midtones balance.
- Stretch is **server-side**; frontend sends params as query string and receives a rendered PNG. Default mode is `stretch=auto` (one round-trip computes stats + linearity + STF); user slider interaction switches to explicit `stretch=stf`.
- **Per-key locks** on image-data and stats caches prevent redundant computation under concurrent requests. Archive cache key is `(archive_path, mtime, entry_path)` so archive-extracted images share with regular files.
- **FITS header editing only** — XISF, standard images, archive paths, and pxiproject virtuals can't be edited. Structural keywords (`SIMPLE`, `BITPIX`, `NAXIS*`, `EXTEND`, `BZERO`, `BSCALE`, `COMMENT`, `HISTORY`, `END`) are protected.
- Performance patterns: histograms subsample to ~2M pixels for large images; PNG encoding uses `compress_level=1` (local app, speed > size); `bottleneck.nanmedian` over numpy median.
- **Pixel inspector — small sampling canvas (iOS WebKit constraint).** Never allocate a full-image offscreen canvas — iOS silently fails to allocate the backing store for canvases backing >~70 MB images and `getImageData` returns all zeros without throwing. Use a single 301×301 canvas allocated once, and 9-arg `drawImage(img, sx, sy, sw, sh, dx, dy, sw, sh)` to copy just the requested patch region per sample. Pattern lives in `frontend/src/components/fits/FitsImage.tsx`.
- **Touch viewport hardening (iPad).** The page sets `<meta name="viewport" content="...maximum-scale=1.0, user-scalable=no">` and the FitsImage container preventDefaults Apple's proprietary `gesturestart`/`gesturechange`/`gestureend` events. Without those, iPadOS engages its own pinch-zoom alongside our touch handler and the user sees the "freeze then jump" stutter. **Do not regress** — if you ever see touch-zoom go janky on iPad, check the viewport meta first.

### Tablet / LAN access (`make dev-lan`)
- Vite binds to `0.0.0.0:5173` and serves HTTPS. Cert resolution: prefers `frontend/.certs/{cert,key}.pem` (mkcert-issued, trusted on iPad after profile install) and falls back to `@vitejs/plugin-basic-ssl` (untrusted, browser warning) if those files are absent. See `frontend/vite.config.ts`.
- Backend stays HTTP on `127.0.0.1:8000`; Vite proxies `/api` → backend, so the iPad never talks to the backend directly.
- iPad pixel inspector and clipboard buttons require a trusted cert. Self-signed → canvas tainting + `navigator.clipboard` rejection.
- Touch interactions are added to chart SVGs as native `addEventListener` with `{ passive: false }` so `preventDefault` works. The shared loupe-suppression CSS bundle is `WebkitTouchCallout: "none"` + `WebkitUserSelect: "none"` + `userSelect: "none"` + `touch-action: "none"` on the chart's SVG element.

### Aberration Inspector
- Cache key is `(file_path, hdu, settings_json)`. Different filter settings = different cache row. TTL via `aberration_cache_ttl_days` setting.
- Star detection via `sep` + `sep.flux_radius` for HFR. Filters are user-tunable, debounced 500 ms.

### Archive Browser
- Virtual paths: `{archive_path}::{entry_path}` (same `::` separator as pxiproject). All I/O services accept `Path | BinaryIO`.
- In-memory extraction for zip/tar; 7z uses a temp dir then cleans up (py7zr API limitation).

### Equipment + Rigs
- **Schema is fully normalized.** No `custom_fields` JSON; add a real column via migration when needed. See `DB_SCHEMA.md` / `DB_SCHEMA_DDL.sql`.
- **Closed CHECK vocabularies** on key fields (`drive_type`, `filter_passband.line_name`, `software.category`, `connection_interface.category`, `sensor.sensor_type`, `sensor.bayer_pattern`). Adding a value = migration.
- Every telescope has ≥ 1 `telescope_configuration` with exactly one `is_native = 1`.
- `camera` table carries `effective_*` overrides that win over the underlying sensor's baseline values.
- Soft-delete via `active = 0`; list endpoints accept `?include_retired=true`.
- Default-rig enforcement: setting `is_default = 1` clears it on all others in one transaction (`_ensure_single_default`).
- `is_mine` flag on the 10 owned-equipment tables is **NOT** in `seeded_fields` — toggling does NOT trigger a re-seed.
- Filter slots (`rig_filter_slot`) require `filter_wheel_id`; clearing the wheel deletes all slots in the same transaction.

### Seed Loader
- **Hash contract is versioned.** Never expand a table's `seeded_fields` after first seed without a migration that backfills affected rows directly — the loader's user-modified check (`current_hash != stored_hash`) will skip every existing row otherwise. v0.26.0's migration 0024 backfilled `worm_period_seconds` via direct UPDATE statements for this reason.
- Never overwrites `source = 'user'` rows.
- Junction tables delete-and-reinsert only for parents that were inserted/updated.
- First-run vs update modes; missing CSV files fail loud at startup.

### DSO Catalog
- **No vendored DSO data.** Repo ships only NightCrate editorial CSVs (CC0). OpenNGC, Sharpless, Barnard, 50 MGC, Wikidata data downloads to `APP_DIR/catalogs/` on user demand from Admin → Catalogs.
- **Source layering precedence is structural, not enforced**: `curated > 50 MGC > redshift`. Each augmenter writes only `WHERE distance_pc IS NULL`, so earlier stages never get clobbered.
- Canonical `dso.obj_type` and `dso_designation.catalog` are **closed CHECK vocabularies** — adding a new prefix needs both a migration AND a loader-map update.
- All catalog fetchers use **atomic staging-dir-rename** and write `version.json` LAST so a crash mid-rename leaves the source as "Not loaded".
- See `docs/dso-catalog-architecture.md`.

### DSO External References
- **Provider allowlist for chip rendering: `wikipedia | simbad | ned`.** Wikidata QIDs are stored but never rendered as user-facing chips — they're for future automated enrichment (Commons images, etc.).
- Provider order is server-fixed (`api/dso.py: _EXTERNAL_REF_PROVIDER_ORDER`).
- **SQLite NULL-uniqueness quirk**: the main `UNIQUE(dso_id, provider, language)` doesn't dedupe when language is NULL; a partial unique index `(dso_id, provider) WHERE language IS NULL` covers wikidata/simbad/ned rows.
- One Wikipedia article / Wikidata QID may correctly cover multiple DSOs (Stephan's Quintet → 5 galaxies). Don't add cross-DSO uniqueness.
- **Verify Wikidata property IDs against live Wikidata before trusting a spec** — specs sometimes claim wrong properties (P2528 = earthquake magnitude, not NED).

### Horizons (per-location, multi)
- Each location has ≥ 1 horizon. Deleting the last one is 422.
- Exactly one horizon per location has `is_default = 1` (partial unique index). At most one custom (polyline) horizon per location; any number of artificial (flat-altitude) horizons.
- **Horizons in the Location editor STAGE — they do NOT persist immediately.** Save commits everything atomically (location fields + horizons); Cancel discards everything. **Do NOT regress** to immediate-persistence — the editor's dirty-state contract requires staging. The atomic-create + diff-apply paths live in `api/locations.py` (`LocationCreate.horizons`) and `api/horizons.py` (`PUT /api/locations/{id}/horizons`).
- Smoothing is **never persisted**; raw points are canonical, consumers re-run D3 smoothing.
- Points stored `[0, 360)`, never 360; display rolls to `[-180, +180]` with virtual seam points at the S boundary.

### Target Planner
- Visibility snapshot computes alt/az at 5-min sampling over **all active DSOs** in the astro-dark window, then filters in memory. Cache key = location + date + location.updated_at + horizon_id + horizon.updated_at.
- Tonight mode applies imaging-focused defaults (min size, max magnitude); **Anytime mode does NOT fall back to those defaults** — a missing param means "don't filter" (otherwise small + faint object types silently collapse).
- `compute_now_status` needs **both** `astro_dark_start_utc` and `astro_dark_end_utc` and uses a **48 h midnight-anchored grid** for moon rise/set (24 h noon-to-noon misses the lunar period of 24h50m).
- Moon separation is computed at **closest approach during the visibility window**, not at peak (peak is misleading when moon is below horizon at transit).
- Sort null-handling: blanks (None AND empty/whitespace strings) always sort last regardless of per-key direction.
- **Persistent UI state lives in the `settings` KV table** (planner_* fields), bridged by `frontend/src/lib/usePlannerSettingsSync.ts`. Free-text search is the only ephemeral field. The sync hook hydrates the in-memory Zustand store on mount, then rAF-coalesces multi-setter ticks into a single PUT and skips no-op writes via a `lastPushedRef` JSON diff. Adding a new persisted field = add it to the Pydantic model, the TS Settings interface, the planner store, and the `buildPayload` map.
- **WishlistCalendarView snap precision.** Snap entries carry their underlying `Date`; never round-trip pixel→date through `d3.scaleTime().invert()` — its linear interpolation can return a date 1 ms before the intended one, which will fail the strict `hoverDate >= rs` check that gates the bar tooltip's range label.

### Target Planner Scoring
- Score is **backend-only** and **Tonight-only** (no Anytime score).
- **Moon impact** uses a two-component model: sky glow (global brightness, default 60% weight) + proximity penalty (local gradient near moon, default 40%). This replaced a proximity-only formula that dropped to zero impact beyond `min_sep`. Both weights are configurable.
- **Meridian timing** uses the true astronomical transit time (not clamped to the dark window) with a configurable buffer (default 2h) that extends the zero point beyond the dark boundary.
- **Observability** min-altitude setting must be ≥ 10° (validation enforced) — below that the `1/sin(alt)` airmass formula produces degenerate values.
- Cluster modifier vocab is closed: `OCl | GCl | *Ass`. `Cl+N` is intentionally NOT a cluster (users image those for the nebula).
- Detail-panel rig/horizon overrides trigger a refetch via `fetchSingleTargetScore` — the list-fetch score is frozen on the page-level rig.

### Caches that survive DB recreation
On-disk caches that outlive the SQLite DB (thumbnails, sky tiles) **must encode stable identity (RA/Dec + variant + size + FOV) in filenames**, NOT internal `dso_id` (unstable across catalog reloads). On startup, `rehydrate_from_disk()` parses filenames back into cache keys and re-indexes BEFORE the orphan sweep deletes anything.

### PHD2 Guide-Log Analyzer
- **Pure-service architecture**: `services/phd2_*.py` produce data; `api/phd2.py` is the only DB/HTTP boundary. Service modules **must not import from `api/`**.
- **Pixel-canonical representation**: all distances stored and computed in pixels; arcsec derived at display time from `SectionHeader.pixel_scale_arcsec_per_px`. Missing pixel scale → UI shows pixels-only; never fabricate arcsec.
- **Parse-by-name, never-by-position.** Column order read per-section from the actual CSV header. Future PHD2 versions reordering columns must not break the parser.
- **Never silently coerce missing data.** Empty fields → `None`, never `0.0`. DROP frames have `None` in positional fields (coercing to zero silently corrupts RMS and creates phantom ideal-guiding periods on charts).
- **No hardcoded ErrorCode → string table.** The log's own ErrorDescription is authoritative.
- **Three tabs**: Guiding (RA/Dec time-series + pulses + SNR + Mass sub-panels), Dispersion (2-D scatter + 1σ / 2σ ellipses), Data (per-frame table). No spectrum / no unguided RA — both stripped in v0.27.0 cleanup.
- **Recent files in DB.** `phd2_recent_files(id, path UNIQUE, opened_at)` (migration 0028). Endpoints `POST/GET/DELETE /api/phd2/recent` mirror the image-analyzer's recent-files pattern. Frontend client lives in `api/phd2.ts` (not the lib file — that one only owns the legacy localStorage migration + the `formatRelativeTime` display helper).
- **Viewport export.** `POST /api/phd2/export` returns the visible window (filtered by section + time range) as a PHD2-format text log file.
- Sample log for local testing: `sample_data/session_logs/ASIAir/PHD2_GuideLog_2026-03-07_193345.txt`.

### Plate Solving
- **ASTAP via subprocess** — invoked via `asyncio.create_subprocess_exec()`. **Never pass `-update`** (would modify the input file). Output directed to temp dir via `-o`, parsed from the `.ini` sidecar.
- **macOS `.app` bundle resolution**: `resolve_astap_binary()` navigates `Contents/MacOS/` to find the executable by name (`astap`, `ASTAP`).
- **Temp file pipeline**: archive/pxiproject images extracted to temp FITS for ASTAP. XISF also converted (ASTAP only handles uncompressed XISF). Regular FITS/TIFF/PNG/JPG passed directly. Header keywords (focal length, pixel size, coordinates) are passed through to temp FITS so ASTAP can determine correct binning and FOV.
- **Concurrency**: `asyncio.Semaphore(1)` — one solve at a time. Second request gets 409.
- **Display-only results** — no DB persistence. RA/Dec/pixel scale/rotation/FOV shown in a dialog.
- **Two-tab UI**: "Solve" (solve the current image directly) and "From Reference Image" (solve a pre-processed stars-only image with matching dimensions). Both support coordinate hints (from header or target search) and equipment hints (from rig, individual equipment, or manual focal length/pixel size).
- **Equipment hints**: Rig, Equipment (OTA config + camera), or Manual mode. Computes pixel scale and FOV from the selected equipment + binning, passed to ASTAP as `-fov` for faster solving.
- **Key backend:** `services/plate_solve.py` (ASTAP invocation + `.ini` parsing), `services/plate_solve_models.py` (Pydantic shapes), `api/plate_solve.py` (`POST /solve`, `POST /validate-reference-image`).
- **Key frontend:** `components/plate-solve/PlateSolveDialog.tsx`, Settings page `AstapPathSection`.

### Weather Forecast
- Two timezones per location: `geo_timezone` (auto-derived from coords via `timezonefinder`, used for noon-to-noon astro windows and the lunar 48 h grid) and `timezone` (user's display preference, used for Open-Meteo API + display formatting). **Don't conflate them** — remote-observatory operators legitimately want display in their home timezone while astro computes against site coordinates.
- Quality scoring uses a **colorblind-safe sequential blue palette** (darker = better). Cloud gating: all non-sky factors multiplied by `√(sky_clarity / 100)`.
- Supplementary data writes (PWV, AOD) are **non-fatal** — wrap in try/except and serve stale data rather than 5xx.
- Forecast covers 8 days (`forecast_days=8`) so the last night's sunrise window is included.

### Calculators
- Math runs server-side (one endpoint per calculator). Frontend ticks at the sidereal rate between 60 s server refreshes for the sidereal clock.
- Backend returns `HH:MM` strings already rendered in the display timezone — frontend must pass them through verbatim, not re-parse as ISO-UTC.
- Formula rendering via **KaTeX** (MIT). Clock order persists in `settings.calculators_clock_order` (server-side), not localStorage. Drag-to-reorder via `@dnd-kit` (single-container `SortableContext` + click-to-add — cross-container drag was attempted and abandoned).
- **Native form-control theming**: `MuiCssBaseline` sets `body.colorScheme = "dark"/"light"` so the native date-input popup, scrollbars, and other browser-rendered form elements match the current theme.

### Admin → Caches
Cache management UI (thumbnail / sky-tile / aberration / weather budgets + Clear All) lives on the Admin page, **NOT Settings**. Settings is for user preferences only (theme, units, planner defaults, GPU, worker cores).

### Activity Console
ASGI middleware (`api/diagnostics.py:RequestTrackingMiddleware`) records every request. Activity label propagates via `X-Activity` header (for `fetch()`) or `_activity` query param (for `<img>` calls — header isn't accessible). Image requests use a **stable `_activity` label** set once on file open so URL-cache-busting doesn't fragment grouping.

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
