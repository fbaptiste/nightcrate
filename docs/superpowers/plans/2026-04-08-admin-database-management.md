# Admin Page — Database Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** First-run setup wizard + Admin page for managing multiple NightCrate databases with hot-swap support.

**Architecture:** Config file (`config.json` in platformdirs app dir) stores known databases + active DB path. Backend `app_config.py` reads/writes it. `db/session.py` becomes dynamic (reads active path on each `get_db()` call). New `api/admin.py` router for status/create/activate/info endpoints. Frontend: setup wizard on first run, Admin page for ongoing management.

**Tech Stack:** Python/FastAPI, aiosqlite, React/TypeScript, MUI

---

## File Structure

### Backend (create)
- `backend/src/nightcrate/core/app_config.py` — config file read/write, AppConfig dataclass
- `backend/src/nightcrate/api/admin.py` — admin API endpoints
- `backend/tests/test_app_config.py` — config unit tests
- `backend/tests/test_admin_api.py` — admin API tests

### Backend (modify)
- `backend/src/nightcrate/db/session.py` — dynamic DB_PATH
- `backend/src/nightcrate/db/migrations.py` — use dynamic path
- `backend/src/nightcrate/main.py` — conditional startup, register admin router, update health endpoint
- `backend/tests/conftest.py` — adapt to dynamic DB_PATH

### Frontend (create)
- `frontend/src/api/admin.ts` — admin API client + types
- `frontend/src/components/SetupWizard.tsx` — first-run wizard
- `frontend/src/pages/AdminPage.tsx` — database management + app info

### Frontend (modify)
- `frontend/src/App.tsx` — conditional wizard vs normal app
- `frontend/src/components/AppShell.tsx` — Admin nav item

---

### Task 1: App Config Module

**Files:**
- Create: `backend/src/nightcrate/core/app_config.py`
- Create: `backend/tests/test_app_config.py`

- [ ] **Step 1: Create app_config module**

```python
"""Application config — persisted in config.json, independent of the database.

The config file lives in the platformdirs app data directory (same parent as
the default database location). It stores the list of known databases and
which one is currently active.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_data_dir

APP_DIR = Path(user_data_dir("NightCrate", appauthor=False))
CONFIG_PATH = APP_DIR / "config.json"


@dataclass
class DatabaseEntry:
    name: str


@dataclass
class AppConfig:
    databases: dict[str, DatabaseEntry] = field(default_factory=dict)  # path → entry
    active_db: str | None = None

    @property
    def db_configured(self) -> bool:
        """True if active_db is set AND the file exists on disk."""
        if self.active_db is None:
            return False
        return Path(self.active_db).is_file()


def load_config() -> AppConfig:
    """Load config from disk. Returns empty config if file doesn't exist."""
    if not CONFIG_PATH.exists():
        return AppConfig()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        databases = {
            path: DatabaseEntry(name=entry["name"])
            for path, entry in raw.get("databases", {}).items()
        }
        return AppConfig(
            databases=databases,
            active_db=raw.get("active_db"),
        )
    except (json.JSONDecodeError, KeyError):
        return AppConfig()


def save_config(config: AppConfig) -> None:
    """Write config to disk. Creates the directory if needed."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "databases": {path: asdict(entry) for path, entry in config.databases.items()},
        "active_db": config.active_db,
    }
    CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def get_active_db_path() -> Path | None:
    """Return the active database path, or None if not configured/available."""
    config = load_config()
    if config.active_db and Path(config.active_db).is_file():
        return Path(config.active_db)
    return None


def get_default_db_path() -> Path:
    """Return the default database path (for setup wizard default)."""
    return APP_DIR / "nightcrate.db"
```

- [ ] **Step 2: Write config tests**

Create `backend/tests/test_app_config.py`:

Tests:
1. `test_load_missing_config` — no file → empty AppConfig
2. `test_save_and_load_roundtrip` — save, load, verify databases + active_db preserved
3. `test_db_configured_true` — active_db points to existing file → True
4. `test_db_configured_false_no_active` — active_db is None → False
5. `test_db_configured_false_missing_file` — active_db points to non-existent file → False
6. `test_load_corrupt_json` — malformed JSON → empty AppConfig (graceful)
7. `test_add_and_remove_database` — modify databases dict, save, reload
8. `test_get_active_db_path_returns_none` — no config → None
9. `test_get_active_db_path_returns_path` — valid config with existing file → Path

Use `monkeypatch` to redirect `APP_DIR` and `CONFIG_PATH` to `tmp_path`.

- [ ] **Step 3: Run tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_app_config.py -v`

- [ ] **Step 4: Lint and commit**

```bash
git add backend/src/nightcrate/core/app_config.py backend/tests/test_app_config.py
git commit -m "feat: app config module for database management"
```

---

### Task 2: Dynamic DB_PATH in session.py and migrations.py

**Files:**
- Modify: `backend/src/nightcrate/db/session.py`
- Modify: `backend/src/nightcrate/db/migrations.py`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Make session.py use dynamic DB_PATH**

Currently `session.py` has:
```python
APP_DIR = Path(user_data_dir("NightCrate", appauthor=False))
DB_PATH = APP_DIR / "nightcrate.db"
```

Change to:
```python
from nightcrate.core.app_config import APP_DIR, get_active_db_path, get_default_db_path

# Module-level mutable path — set on startup, can be swapped at runtime
_active_db_path: Path | None = None


def get_db_path() -> Path:
    """Return the current active database path."""
    if _active_db_path is not None:
        return _active_db_path
    # Fallback: check config
    path = get_active_db_path()
    if path is not None:
        return path
    # Ultimate fallback: default location
    return get_default_db_path()


def set_db_path(path: Path) -> None:
    """Hot-swap the active database path (called by admin API)."""
    global _active_db_path
    _active_db_path = path


# Keep DB_PATH as a property-like accessor for backward compatibility
# with code that imports it directly (migrations.py, conftest.py)
DB_PATH = property(lambda self: get_db_path())  # This won't work as module-level
```

Actually, the cleanest approach: keep `DB_PATH` as a module-level variable but make `get_db()` use `get_db_path()` instead. Other code that imports `DB_PATH` (migrations.py, main.py, conftest.py) needs to be updated to call `get_db_path()`.

```python
"""Async SQLite connection factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from nightcrate.core.app_config import APP_DIR, get_active_db_path, get_default_db_path

# Runtime-mutable path — set during startup or hot-swapped by admin API
_db_path: Path | None = None


def get_db_path() -> Path:
    """Return the current database path."""
    if _db_path is not None:
        return _db_path
    path = get_active_db_path()
    if path is not None:
        return path
    return get_default_db_path()


def set_db_path(path: Path) -> None:
    """Set the active database path at runtime."""
    global _db_path
    _db_path = path


def _ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """Yield an aiosqlite connection with row_factory set to return dicts."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn
```

- [ ] **Step 2: Update migrations.py**

Change from importing `DB_PATH` to calling `get_db_path()`:

```python
"""Apply yoyo migrations on startup."""

from pathlib import Path

from yoyo import get_backend, read_migrations

from nightcrate.db.session import _ensure_app_dir, get_db_path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def apply_migrations(db_path: Path | None = None) -> None:
    """Run any pending migrations synchronously."""
    _ensure_app_dir()
    path = db_path or get_db_path()
    backend = get_backend(f"sqlite:///{path}")
    migrations = read_migrations(str(MIGRATIONS_DIR))
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))
```

The optional `db_path` parameter allows the admin API to run migrations on a newly created DB before it becomes the active one.

- [ ] **Step 3: Update conftest.py**

The test conftest monkeypatches `DB_PATH` — it now needs to monkeypatch `_db_path` or use `set_db_path()`:

```python
monkeypatch.setattr("nightcrate.db.session._db_path", test_db)
```

Also update the `APP_DIR` monkeypatch:
```python
monkeypatch.setattr("nightcrate.core.app_config.APP_DIR", tmp_path)
monkeypatch.setattr("nightcrate.core.app_config.CONFIG_PATH", tmp_path / "config.json")
```

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest -v`

All existing tests must pass — this is a refactor, no behavior changes.

- [ ] **Step 5: Lint and commit**

```bash
git add backend/src/nightcrate/db/session.py backend/src/nightcrate/db/migrations.py backend/tests/conftest.py
git commit -m "refactor: dynamic DB_PATH for database hot-swap support"
```

---

### Task 3: Admin API Endpoints

**Files:**
- Create: `backend/src/nightcrate/api/admin.py`
- Create: `backend/tests/test_admin_api.py`
- Modify: `backend/src/nightcrate/main.py`

- [ ] **Step 1: Create admin router**

Create `backend/src/nightcrate/api/admin.py` with these endpoints:

**`GET /api/admin/info`** — read-only app info:
```python
@router.get("/info")
async def admin_info() -> dict:
    return {
        "config_file": str(CONFIG_PATH),
        "app_data_dir": str(APP_DIR),
        "backend_root": str(Path(__file__).resolve().parents[1]),
        "seed_data_dir": str(importlib.resources.files("nightcrate") / "data" / "seed"),
        "python_version": sys.version.split()[0],
        "app_version": APP_VERSION,
    }
```

**`GET /api/admin/status`** — database configuration status:
```python
@router.get("/status")
async def admin_status() -> dict:
    config = load_config()
    known = []
    for path_str, entry in config.databases.items():
        p = Path(path_str)
        available = p.is_file()
        known.append({
            "path": path_str,
            "name": entry.name,
            "size_bytes": p.stat().st_size if available else None,
            "available": available,
        })
    active = None
    if config.active_db:
        p = Path(config.active_db)
        entry = config.databases.get(config.active_db)
        available = p.is_file()
        active = {
            "path": config.active_db,
            "name": entry.name if entry else "Unknown",
            "size_bytes": p.stat().st_size if available else None,
            "available": available,
        }
    return {
        "db_configured": config.db_configured,
        "active_db": active,
        "known_databases": known,
    }
```

**`POST /api/admin/database/create`** — create a new DB:
```python
@router.post("/database/create")
async def create_database(body: CreateDatabaseRequest) -> dict:
    # body has: path (str), name (str)
    # 1. Create parent directory if needed
    # 2. Create SQLite file
    # 3. Run migrations on it
    # 4. Run seed loader on it
    # 5. Add to config.databases (do NOT activate)
    # 6. Return DB info
```

**`POST /api/admin/database/activate`** — switch active DB:
```python
@router.post("/database/activate")
async def activate_database(body: ActivateDatabaseRequest) -> dict:
    # body has: path (str)
    # 1. Validate path is in config.databases and file exists
    # 2. Run migrations (in case schema is behind)
    # 3. Run seed loader
    # 4. Update config.active_db
    # 5. Hot-swap: set_db_path(Path(body.path))
    # 6. Return DB info
```

**`POST /api/admin/database/setup`** — first-run setup (create + activate):
```python
@router.post("/database/setup")
async def setup_database(body: CreateDatabaseRequest) -> dict:
    # 1. Reject if already configured
    # 2. Create DB (same as /create)
    # 3. Activate it (same as /activate)
    # 4. Return DB info
```

**`DELETE /api/admin/database`** — remove from known list:
```python
@router.delete("/database")
async def remove_database(body: RemoveDatabaseRequest) -> dict:
    # body has: path (str)
    # 1. Cannot remove active_db
    # 2. Remove from config.databases
    # 3. Save config
    # 4. Return {"ok": True}
```

**`GET /api/admin/browse`** — directory browser for DB file selection:
```python
@router.get("/browse")
async def browse_for_database(path: str = Query(default="~")) -> dict:
    # List directories + .db files in the given path
    # Similar to files.py browse but filtered to dirs + *.db
```

- [ ] **Step 2: Register admin router and update health endpoint in main.py**

Import and register admin router. Update health endpoint to include `db_configured`. Update startup to be conditional on `db_configured`.

The startup flow becomes:
1. Load config
2. If active_db available → `set_db_path()`, run migrations, run seed loader, purge aberration cache
3. If not → skip all DB operations, app starts in "unconfigured" mode

Health endpoint: `return {"status": "ok", "version": APP_VERSION, "db_configured": config.db_configured}`

- [ ] **Step 3: Write admin API tests**

Create `backend/tests/test_admin_api.py`:

Tests:
1. `test_admin_info` — returns valid paths and versions
2. `test_admin_status_unconfigured` — no config → db_configured=false, empty known_databases
3. `test_admin_status_configured` — with active DB → db_configured=true, correct active_db
4. `test_create_database` — creates DB file, runs migrations, adds to config
5. `test_setup_first_run` — creates + activates DB, sets db_configured=true
6. `test_setup_rejects_if_configured` — already configured → 409
7. `test_activate_database` — switches active DB
8. `test_activate_missing_file` — file doesn't exist → 400
9. `test_remove_database` — removes from known list
10. `test_remove_active_rejected` — cannot remove active DB → 400
11. `test_status_shows_unavailable` — DB in config but file deleted → available=false
12. `test_browse_directories` — returns dirs + .db files
13. `test_health_includes_db_configured` — health endpoint returns db_configured field

- [ ] **Step 4: Run tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_admin_api.py tests/test_app_config.py -v`

- [ ] **Step 5: Lint and commit**

```bash
git add backend/src/nightcrate/api/admin.py backend/src/nightcrate/main.py backend/tests/test_admin_api.py
git commit -m "feat: admin API — database status, create, activate, remove, browse, info"
```

---

### Task 4: Frontend — Admin API Client

**Files:**
- Create: `frontend/src/api/admin.ts`

- [ ] **Step 1: Create types and fetch functions**

```typescript
import { apiFetch } from "./client";

export interface AppInfo {
  config_file: string;
  app_data_dir: string;
  backend_root: string;
  seed_data_dir: string;
  python_version: string;
  app_version: string;
}

export interface DatabaseInfo {
  path: string;
  name: string;
  size_bytes: number | null;
  available: boolean;
}

export interface AdminStatus {
  db_configured: boolean;
  active_db: DatabaseInfo | null;
  known_databases: DatabaseInfo[];
}

export interface BrowseResult {
  path: string;
  dirs: { name: string; path: string }[];
  files: { name: string; path: string; size: number }[];
}

export const fetchAdminInfo = () => apiFetch<AppInfo>("/admin/info");

export const fetchAdminStatus = () => apiFetch<AdminStatus>("/admin/status");

export const createDatabase = (data: { path: string; name: string }) =>
  apiFetch<DatabaseInfo>("/admin/database/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const setupDatabase = (data: { path: string; name: string }) =>
  apiFetch<DatabaseInfo>("/admin/database/setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const activateDatabase = (path: string) =>
  apiFetch<DatabaseInfo>("/admin/database/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });

export const removeDatabase = (path: string) =>
  apiFetch<{ ok: boolean }>("/admin/database", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });

export const browseForDatabase = (path = "~") =>
  apiFetch<BrowseResult>(`/admin/browse?path=${encodeURIComponent(path)}`);

export const fetchHealth = () =>
  apiFetch<{ status: string; version: string; db_configured: boolean }>("/health");
```

Note: `fetchHealth` may already exist in another file — check `api/files.ts`. If so, update it there to include `db_configured` rather than duplicating.

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/admin.ts
git commit -m "feat: frontend admin API client"
```

---

### Task 5: Frontend — Setup Wizard

**Files:**
- Create: `frontend/src/components/SetupWizard.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create SetupWizard**

Full-screen centered card shown when `db_configured: false`.

Two scenarios determined by the `AdminStatus` response:
- **Scenario A** (fresh install): no known databases → "Welcome to NightCrate" + create form
- **Scenario B** (unavailable DBs): known databases exist but none available → warning listing unavailable DBs + create form

Fields:
- Database name (TextField, default "My Equipment Database")
- Database path (TextField, default from `/api/admin/info` → `app_data_dir + "/nightcrate.db"`)
- Browse button (opens a simple path picker — can use the `/api/admin/browse` endpoint)
- "Create & Start" button → calls `POST /api/admin/database/setup`
- On success: call `window.location.reload()` to restart the app with the new DB

Use `useQuery` with `fetchAdminStatus` to determine the scenario.

- [ ] **Step 2: Modify App.tsx for conditional rendering**

```typescript
// App.tsx now:
// 1. Fetches /api/health on mount
// 2. If db_configured === false → render SetupWizard
// 3. If db_configured === true → render normal RouterProvider

export default function App() {
  const { data: health, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  if (isLoading) return <LoadingScreen />;  // or null
  if (!health?.db_configured) return <SetupWizard />;

  return (
    <ThemeProvider>
      <RouterProvider router={router} />
    </ThemeProvider>
  );
}
```

Move the `useSettingsStore` load into `AppShell` instead of `App` (since it requires a configured DB).

- [ ] **Step 3: Verify build**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SetupWizard.tsx frontend/src/App.tsx
git commit -m "feat: first-run setup wizard"
```

---

### Task 6: Frontend — Admin Page

**Files:**
- Create: `frontend/src/pages/AdminPage.tsx`
- Modify: `frontend/src/App.tsx` — add route
- Modify: `frontend/src/components/AppShell.tsx` — add nav item

- [ ] **Step 1: Create AdminPage**

Two sections:

**App Info section:**
Read-only fields from `GET /api/admin/info`. Display each as a label + monospace value. Use MUI `TextField` with `InputProps={{ readOnly: true }}` or just `Typography` pairs.

**Database Management section:**
- Current database: name + path + size (highlighted)
- Known databases list: MUI List or simple table
  - Available DBs: normal text, Activate button (disabled if active), Remove button (disabled if active)
  - Unavailable DBs: dimmed/italic, "(not found)" label, Remove button enabled, Activate button disabled
- "Create New Database" button → opens dialog with name + path + Browse
- "Add Existing Database" button → opens file browser dialog, then name prompt

After activating a different DB: `queryClient.invalidateQueries()` to refetch everything, or `window.location.reload()` for simplicity.

- [ ] **Step 2: Add route and nav item**

In App.tsx: add `{ path: "admin", element: <AdminPage /> }` to children.

In AppShell.tsx: add nav item with `AdminPanelSettingsIcon`:
```typescript
{ to: "/admin", label: "Admin", icon: <AdminPanelSettingsIcon /> }
```

- [ ] **Step 3: Verify build**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/AdminPage.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx
git commit -m "feat: Admin page with database management + app info"
```

---

### Task 7: Full Checks

**Files:** None (verification only)

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest -v`

- [ ] **Step 2: Lint and format**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`

- [ ] **Step 3: Security scan**

Run: `uv run bandit -r src/`

- [ ] **Step 4: Frontend build**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

- [ ] **Step 5: Manual testing**

Delete the existing database and config to simulate first run:
```bash
rm -f "$HOME/Library/Application Support/NightCrate/nightcrate.db"
rm -f "$HOME/Library/Application Support/NightCrate/config.json"
```

Start `make dev`. Verify:
1. Setup wizard appears (not the normal app)
2. Default path is pre-filled
3. Create & Start works → transitions to normal app with seed data
4. Navigate to Admin page → shows app info + current database
5. Create a second database from Admin page
6. Activate the second database → app switches, equipment page shows seed data
7. Switch back to the first database
8. Verify the original data (including "ZWO Astronomy" user edit) is preserved
