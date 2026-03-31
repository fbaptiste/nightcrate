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
  - **No Tailwind CSS** — MUI uses its own styling system (`sx` prop + `styled`).
  - **State:** Zustand
  - **Data fetching:** TanStack Query
  - **Charts:** D3.js for complex interactive charts (PHD2 guiding graph, session timeline); MUI X Charts (free) for simpler dashboards (integration time bars, altitude).
- **Database:** SQLite accessed directly via `aiosqlite` (raw SQL, no ORM). Migrations managed with `yoyo-migrations` (SQL files in `db/migrations/`). **No SQLAlchemy.**
- **Data models:** Pydantic only — for API shapes, domain objects, and settings. No ORM models.
- **Desktop:** Phase 1 = local web app (FastAPI serves React, accessed via browser or pywebview); Phase 2 = Tauri wrapper if needed
- **Key Python libs:** `astropy`, `fitsio`, `astroquery`, ASTAP/astrometry.net for plate solving
- **Async ingestion:** asyncio task queue + `ProcessPoolExecutor` for CPU-bound FITS parsing (parallelizes across cores; SQLite writes stay on main process)
- **GPU acceleration:** `mlx` (Apple Metal, primary target for Mac/Apple Silicon) with numpy as CPU fallback. All array operations go through a thin `compute` backend module — callers never reference mlx/numpy directly. CuPy (NVIDIA CUDA) can be added later for cross-platform.
- **User settings:** `gpu_acceleration` (bool) and `max_worker_cores` (int, `null` = `cpu_count - 1`) are user-configurable at runtime. Settings stored in a `settings.json` in the app data directory.

Desktop packaging rationale: Qt rejected (PixInsight experience was buggy on Mac); Electron rejected (100MB+ bundle size); Tauri is the future native wrapper option using OS-native webview.

## Architecture

The app is a **local-first desktop application** for Mac (inherently cross-platform via web approach). The backend handles all computation — FITS parsing, log ingestion, plate solving, file management. The frontend is a React UI.

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

## FITS Image Display

FITS pixel data is normalized to [0, 1] at load time based on data type (uint16 ÷ 65535, matching PixInsight convention). Three stretch modes are supported:

- **Auto (STF):** Default. PixInsight-compatible Screen Transfer Function. Auto-computes shadow clip and midtones balance from median + MAD statistics. For linked color: uses dimmest channel's params across all channels.
- **Linear:** Percentile-based black/white point clipping + gamma.
- **Asinh:** Arcsinh stretch for lifting faint detail.

Both mono and color (RGB) FITS files are supported. Color images offer linked (single set of params for all channels) and unlinked (per-channel) stretch.

Stretch is applied server-side — the frontend sends stretch params as query parameters and receives a rendered PNG. The `core/compute.py` (`get_array_module()`) abstraction exists for future GPU acceleration but stretch currently uses numpy directly in `services/fits.py`.

## Dependency & License Policy

NightCrate is a **commercial closed-source product**. Before adding any new dependency (Python or JS/TS):

1. **Check the license.** Only permissive licenses are allowed: MIT, BSD (2/3-Clause), Apache 2.0, ISC, HPND, SIL OFL (fonts). LGPL is acceptable for Python packages imported at runtime (dynamic linking) but **requires attribution** in `README.md`.
2. **GPL is never allowed** — no GPL-2.0, GPL-3.0, or AGPL. If a critical feature needs a GPL library, write a clean-room implementation or find an alternative.
3. **MUI X Pro/Premium is never allowed** — paid commercial license required. Only MUI X Community tier.
4. **Update `README.md`** — add the library to the Open Source Acknowledgments table with its license and copyright.
5. **Update `PLAN.md`** — if it's a new category of library, add it to the Library Reference appendix.

The full evaluated library list is in `PLAN.md` under "Appendix: Library Reference."
