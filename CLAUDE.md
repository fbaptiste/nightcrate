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
  - **Styling:** Tailwind CSS (dark mode via `class` strategy) + shadcn/ui component library
  - **Theme:** Light / Dark / Browser (auto). Stored in settings.json, applied via `dark` class on `<html>`.
  - **State:** Zustand
  - **Data fetching:** TanStack Query
  - **Charts:** D3.js for complex interactive charts (PHD2 guiding graph, session timeline); Recharts for simpler dashboards (integration time, altitude). Recharts is D3-based — one ecosystem.
- **Database:** SQLite for MVP (PostgreSQL is Fred's area of expertise but SQLite is preferred for local desktop simplicity)
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
- **Migrations:** Alembic

## Commands

```bash
# Backend (from backend/)
uv run uvicorn nightcrate.main:app --reload --port 8000
uv run pytest
uv run ruff check .
uv run ruff check --fix .
uv run ruff format .
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "description"

# Frontend (from frontend/)
npm run dev        # Vite dev server → http://localhost:5173
npm run build
npm run lint
```

## FITS Image Display

Raw FITS data is 16-bit (0–65535). "No stretch" display means **linear min/max scaling**: map the actual pixel min→0, max→255. The image will look correctly exposed but not astronomically stretched. All pixel math goes through `core/compute.py` (`get_array_module()`), never directly importing mlx/numpy.
