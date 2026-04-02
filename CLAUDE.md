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
  - **UI library:** MUI (`@mui/material`) — free MIT core. MUI X Community tier only (`@mui/x-data-grid`, `@mui/x-date-pickers`, `@mui/x-charts`, `@mui/x-tree-view`) — all free MIT. **Never use MUI X Pro or Premium** (paid, commercial license required; NightCrate is a commercial product so the open-source exception does not apply).
  - **Theme:** MUI `ThemeProvider` with light/dark/browser (system) modes. Stored in `settings.json` via backend.
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

Before committing any Python code changes, all of these must pass:

1. `uv run ruff check src/ tests/` — lint
2. `uv run ruff format --check src/ tests/` — formatting
3. `uv run bandit -r src/` — security
4. `uv run pytest` — tests

## Image Viewer

Supported formats: FITS (`.fits/.fit/.fts`), XISF (`.xisf`), PixInsight projects (`.pxiproject`), PNG, JPEG, TIFF (including float32 TIFF).

**Architecture:**
- `services/imaging.py` — format-agnostic: normalization, stretch, stats, histogram, Lab a*, PNG rendering
- `services/fits_io.py` — FITS loading via astropy
- `services/xisf_io.py` — clean-room XISF parser (no GPL dependency)
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
- The `core/compute.py` (`get_array_module()`) abstraction exists for future GPU acceleration

## Dependency & License Policy

NightCrate is licensed under **GPL-3.0**. Before adding any new dependency (Python or JS/TS):

1. **Check the license.** Compatible licenses: MIT, BSD (2/3-Clause), Apache 2.0, ISC, HPND, SIL OFL (fonts), LGPL, GPL-3.0. **Always verify compatibility and get approval before adding GPL-licensed dependencies** — even though NightCrate is GPL-3.0, we prefer permissive dependencies where possible and want to evaluate GPL libraries case by case.
2. **MUI X Pro/Premium is never allowed** — paid commercial license. Only MUI X Community tier.
3. **Update `README.md`** — add the library to the Open Source Acknowledgments table with its license and copyright.
4. **Update `PLAN.md`** — if it's a new category of library, add it to the Library Reference appendix.

The full evaluated library list is in `PLAN.md` under "Appendix: Library Reference."
