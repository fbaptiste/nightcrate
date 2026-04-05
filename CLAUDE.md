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

## Dependency & License Policy

NightCrate is licensed under **GPL-3.0**. Before adding any new dependency (Python or JS/TS):

1. **Check the license.** Compatible licenses: MIT, BSD (2/3-Clause), Apache 2.0, ISC, HPND, SIL OFL (fonts), LGPL, GPL-3.0. **Always verify compatibility and get approval before adding GPL-licensed dependencies** — even though NightCrate is GPL-3.0, we prefer permissive dependencies where possible and want to evaluate GPL libraries case by case.
2. **MUI X Pro/Premium is never allowed** — paid commercial license. Only MUI X Community tier.
3. **Update `README.md`** — add the library to the Open Source Acknowledgments table with its license and copyright.
4. **Update `PLAN.md`** — if it's a new category of library, add it to the Library Reference appendix.

The full evaluated library list is in `PLAN.md` under "Appendix: Library Reference."
