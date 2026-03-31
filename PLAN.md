# NightCrate — Implementation Plan

Living document tracking implementation status. Check off items as they are completed.

---

## Version 1 — Foundation + FITS Viewer

**Goal:** Working skeleton with a functional backend and frontend, theme switching, and the ability to open a FITS file, display its image and header.

**Status:** 🔲 Not started

---

### 1. Environment Setup

Steps you'll need to follow (once) before development begins.

#### 1.1 Install uv

- [ ] Install uv (Mac):
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
  Then restart your terminal so `uv` is on your PATH. Verify with `uv --version`.

#### 1.2 Install Python 3.14

- [ ] Install Python 3.14 via uv:
  ```bash
  uv python install 3.14
  ```
  uv manages its own Python installs — this does not affect any system Python.

#### 1.3 Node.js

- [ ] Verify Node.js is installed: `node --version` (need v20+). Install via `brew install node` if needed.

---

### 2. Project Structure

- [ ] Create the top-level directory layout:
  ```
  nightcrate/
  ├── backend/      ← Python/FastAPI
  ├── frontend/     ← React/TypeScript
  ├── CLAUDE.md
  └── PLAN.md
  ```

---

### 3. Backend — Project Initialization

#### 3.1 uv Project Setup

- [ ] Initialize the backend project:
  ```bash
  cd backend
  uv init --python 3.14
  ```
  This creates `pyproject.toml` and a `.venv` automatically.

- [ ] Add core dependencies:
  ```bash
  uv add fastapi "uvicorn[standard]" sqlalchemy alembic astropy pillow numpy
  ```

- [ ] Add dev dependencies:
  ```bash
  uv add --dev ruff pytest pytest-asyncio httpx
  ```

  **Key uv commands you'll use daily:**
  | Command | What it does |
  |---------|-------------|
  | `uv add <pkg>` | Add a dependency (like `pip install` + saves to pyproject.toml) |
  | `uv add --dev <pkg>` | Add a dev-only dependency |
  | `uv run <cmd>` | Run a command inside the venv without activating it |
  | `uv sync` | Sync venv to match pyproject.toml (run after pulling changes) |
  | `uv python pin 3.14` | Pin this project to Python 3.14 |

#### 3.2 Ruff Configuration

- [ ] Add ruff config to `backend/pyproject.toml`:
  ```toml
  [tool.ruff]
  target-version = "py314"
  line-length = 100

  [tool.ruff.lint]
  select = ["E", "F", "I", "UP"]   # pycodestyle, pyflakes, isort, pyupgrade

  [tool.ruff.format]
  quote-style = "double"
  ```

  **Key ruff commands:**
  | Command | What it does |
  |---------|-------------|
  | `uv run ruff check .` | Lint — shows issues |
  | `uv run ruff check --fix .` | Lint + auto-fix what it can |
  | `uv run ruff format .` | Format (replaces black) |
  | `uv run ruff format --check .` | Check formatting without changing files |

#### 3.3 Directory Structure

- [ ] Create backend source layout:
  ```
  backend/
  ├── pyproject.toml
  ├── src/
  │   └── nightcrate/
  │       ├── __init__.py
  │       ├── main.py          # FastAPI app entry point
  │       ├── api/
  │       │   ├── __init__.py
  │       │   ├── fits.py      # FITS endpoints
  │       │   └── settings.py  # Settings endpoints
  │       ├── core/
  │       │   ├── __init__.py
  │       │   ├── config.py    # App settings (load/save settings.json)
  │       │   └── compute.py   # GPU/CPU compute backend abstraction
  │       ├── db/
  │       │   ├── __init__.py
  │       │   ├── base.py      # SQLAlchemy base
  │       │   └── session.py   # DB session factory
  │       └── services/
  │           ├── __init__.py
  │           └── fits.py      # FITS reading/rendering logic
  └── tests/
      └── __init__.py
  ```

#### 3.4 FastAPI App Shell

- [ ] `main.py` — FastAPI instance with CORS configured for localhost, routers registered, startup/shutdown lifecycle
- [ ] Health check endpoint: `GET /api/health` → `{"status": "ok"}`
- [ ] Configure FastAPI to serve the built React frontend as static files (for production mode)

#### 3.5 Settings System

- [ ] `core/config.py` — Pydantic `Settings` model with fields:
  - `theme`: `"light" | "dark" | "browser"` (default: `"browser"`)
  - `gpu_acceleration`: `bool` (default: `true`)
  - `max_worker_cores`: `int | None` (default: `null` → uses `cpu_count - 1`)
- [ ] Load from / save to `~/Library/Application Support/NightCrate/settings.json`
- [ ] `GET /api/settings` — return current settings
- [ ] `PUT /api/settings` — update and persist settings

#### 3.6 Compute Backend Stub

- [ ] `core/compute.py` — thin module that detects available backends at startup (mlx if on Apple Silicon, else numpy) and respects the `gpu_acceleration` setting. Expose `get_array_module()` that returns the right backend. Rest of codebase always calls this, never imports mlx/numpy directly.

#### 3.7 Database Initialization

- [ ] `db/base.py` — SQLAlchemy `DeclarativeBase`
- [ ] `db/session.py` — async engine + session factory pointing to `~/Library/Application Support/NightCrate/nightcrate.db`
- [ ] Initialize Alembic: `uv run alembic init alembic`
- [ ] Configure `alembic.ini` and `alembic/env.py` to use the app's DB URL and import all models
- [ ] Create and apply initial (empty) migration: `uv run alembic revision --autogenerate -m "initial"` then `uv run alembic upgrade head`

---

### 4. Backend — FITS Functionality

#### 4.1 FITS Header Endpoint

- [ ] `GET /api/fits/header?path=<encoded_path>` — reads the FITS file at the given path using `astropy.io.fits`, returns all header cards as a JSON array of `{key, value, comment}` objects. Handles multi-HDU files (returns headers per HDU).

#### 4.2 FITS Image Endpoint

- [ ] `GET /api/fits/image?path=<encoded_path>&hdu=0` — reads image data from the specified HDU, applies **linear min/max scaling** (maps actual data min→0, max→255 with no stretch curve), returns a PNG via `StreamingResponse`.
  - Note: this is the simplest possible display — the image will look correctly exposed but not stretched. Astronomical stretching (arcsinh, histogram equalization, etc.) comes in a later version.
  - Use the compute backend (`get_array_module()`) for the scaling operation.
  - Use `Pillow` for PNG encoding.

---

### 5. Frontend — Project Initialization

#### 5.1 Vite + React + TypeScript

- [ ] Scaffold the project:
  ```bash
  cd frontend
  npm create vite@latest . -- --template react-ts
  npm install
  ```

- [ ] Add dependencies:
  ```bash
  npm install zustand react-router-dom @tanstack/react-query
  npm install -D tailwindcss @tailwindcss/vite
  ```

- [ ] Initialize Tailwind CSS:
  ```bash
  npx tailwindcss init
  ```
  Configure `vite.config.ts` to use the Tailwind Vite plugin. Set Tailwind dark mode to `class` strategy.

#### 5.2 shadcn/ui

- [ ] Initialize shadcn/ui:
  ```bash
  npx shadcn@latest init
  ```
  Choose: TypeScript, default style, CSS variables for theming.

- [ ] Add initial components:
  ```bash
  npx shadcn@latest add button select separator scroll-area table
  ```

#### 5.3 Directory Structure

- [ ] Establish frontend source layout:
  ```
  frontend/src/
  ├── api/             # Typed API client functions (calls backend)
  ├── components/      # Shared UI components
  ├── pages/           # Top-level route pages
  ├── stores/          # Zustand stores
  └── lib/             # Utilities
  ```

---

### 6. Frontend — Foundation

#### 6.1 API Client

- [ ] `api/client.ts` — base fetch wrapper pointing to `http://localhost:8000`
- [ ] `api/settings.ts` — `getSettings()`, `updateSettings()`
- [ ] `api/fits.ts` — `getFitsHeader(path)`, `getFitsImageUrl(path, hdu)`

#### 6.2 Theme System

- [ ] `stores/settingsStore.ts` — Zustand store holding `theme`, `gpuAcceleration`, `maxWorkerCores`; hydrates from `GET /api/settings` on app load; `updateSettings()` action calls `PUT /api/settings`
- [ ] `components/ThemeProvider.tsx` — reads `theme` from store; applies `dark` class to `<html>` for dark mode, removes it for light, and uses `window.matchMedia('prefers-color-scheme: dark')` listener for browser/auto mode
- [ ] Theme persists across sessions (stored in `settings.json` via backend)

#### 6.3 App Shell + Routing

- [ ] `main.tsx` — mount `ThemeProvider`, `QueryClientProvider`, `RouterProvider`
- [ ] Basic layout: sidebar/nav + main content area
- [ ] Routes:
  - `/` — home/welcome page (placeholder)
  - `/fits-viewer` — FITS file viewer
  - `/settings` — settings page

#### 6.4 Settings Page

- [ ] Theme selector: radio/select with options Light / Dark / Browser
- [ ] GPU acceleration toggle
- [ ] Max worker cores input (number, blank = auto)
- [ ] Changes call `PUT /api/settings` and update the Zustand store immediately (optimistic update)

---

### 7. Frontend — FITS Viewer

#### 7.1 File Selection

- [ ] File path input — a text input where the user types or pastes an absolute file path (native file picker `<input type="file">` cannot return absolute paths in browsers; pywebview can bridge this later)
- [ ] "Open" button triggers load

#### 7.2 FITS Header Panel

- [ ] Fetches `GET /api/fits/header?path=...` on file open
- [ ] Displays a scrollable table: Keyword | Value | Comment
- [ ] Multi-HDU support: tab or dropdown to switch between HDUs

#### 7.3 FITS Image Panel

- [ ] Loads image from `GET /api/fits/image?path=...&hdu=...`
- [ ] Displays the PNG returned by the backend
- [ ] Shows HDU selector if multiple image HDUs exist
- [ ] Basic zoom: fit-to-window toggle and 1:1 pixel view

---

### 8. Running the App

- [ ] Document the dev workflow in CLAUDE.md:
  ```bash
  # Terminal 1 — backend
  cd backend
  uv run uvicorn nightcrate.main:app --reload --port 8000

  # Terminal 2 — frontend
  cd frontend
  npm run dev          # Vite dev server on http://localhost:5173
  ```

---

### Version 1 Completion Criteria

- [ ] Backend starts cleanly with `uv run uvicorn ...`
- [ ] Frontend starts cleanly with `npm run dev`
- [ ] `GET /api/health` returns 200
- [ ] Settings load/save round-trip works
- [ ] Theme switching (light/dark/browser) works and persists across app restarts
- [ ] A FITS file can be opened and its header viewed
- [ ] A FITS file's image data is displayed (linear-scaled, no stretch)
- [ ] `uv run ruff check .` passes with no errors

---

*Next version will be defined once Version 1 is complete.*
