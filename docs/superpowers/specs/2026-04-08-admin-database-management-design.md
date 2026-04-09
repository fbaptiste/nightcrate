# Admin Page — Database Management Design Spec

## Goal

First-run setup wizard for choosing database location + name. Admin page for viewing current database info, switching between known databases, and creating new ones. Hot-swap without restart.

## First-Run Flow

1. App starts, backend reads `config.json` from platformdirs app dir
2. If no config or no `active_db` → `/api/health` returns `db_configured: false`
3. Frontend detects this on load, shows setup wizard instead of normal UI
4. Wizard presents: database name (text field, e.g., "Fred's Imaging Rig") + file path (with browse button, defaults to `{app_dir}/nightcrate.db`)
5. User confirms → `POST /api/admin/database/create` creates the DB, runs migrations + seed loader
6. Backend writes `config.json` with the new entry as `active_db`
7. Frontend transitions to the normal app

## Config File

Location: `{platformdirs app_dir}/config.json` (e.g., `~/Library/Application Support/NightCrate/config.json`)

```json
{
  "databases": {
    "/Users/fred/Library/Application Support/NightCrate/nightcrate.db": {
      "name": "Fred's Imaging Rig"
    },
    "/Users/fred/Desktop/test.db": {
      "name": "Test Database"
    }
  },
  "active_db": "/Users/fred/Library/Application Support/NightCrate/nightcrate.db"
}
```

- `databases` — dict of known databases, keyed by absolute file path, value has `name`
- `active_db` — absolute path to the currently active database (must be a key in `databases`)
- File is read before any DB connection is opened
- Written by backend only (never by frontend directly)

## Backend

### `core/app_config.py`

Reads/writes `config.json`. No DB dependency.

```python
@dataclass
class DatabaseEntry:
    path: str
    name: str

@dataclass  
class AppConfig:
    databases: dict[str, DatabaseEntry]  # path → entry
    active_db: str | None  # path of active DB, None if not configured

def get_config_path() -> Path
def load_config() -> AppConfig
def save_config(config: AppConfig) -> None
def get_active_db_path() -> Path | None  # returns None if not configured
```

### Modify `db/session.py`

`DB_PATH` becomes dynamic — reads from `get_active_db_path()` on each `get_db()` call. If None (not configured), `get_db()` raises an error.

Add `set_db_path(path: Path)` for hot-swap — updates a module-level variable that `get_db()` reads. On switch, `app_config.save_config()` persists it, and `set_db_path()` updates the runtime state.

### `api/admin.py` — new router

**`GET /api/admin/status`**
Returns: `{ db_configured: bool, active_db: { path, name, size_bytes } | null, known_databases: [{ path, name, size_bytes }] }`

**`POST /api/admin/database/create`**
Body: `{ path: string, name: string }`
- Creates SQLite file at `path`
- Runs migrations
- Runs seed loader
- Adds to config.databases
- Does NOT switch to it (separate action)
- Returns: `{ path, name, size_bytes }`

**`POST /api/admin/database/activate`**
Body: `{ path: string }`
- Validates path exists and is a key in config.databases
- Runs migrations (in case schema is behind)
- Runs seed loader
- Updates config.active_db
- Hot-swaps DB_PATH in session.py
- Returns: `{ path, name, size_bytes }`

**`POST /api/admin/database/setup`** (first-run only)
Body: `{ path: string, name: string }`
- Creates DB + runs migrations + seed loader
- Sets as active_db in config
- Hot-swaps DB_PATH
- Returns: `{ path, name, size_bytes }`
- Rejects if active_db is already configured (not a re-setup endpoint)

**`DELETE /api/admin/database`**
Body: `{ path: string }`
- Removes from config.databases (does NOT delete the file)
- Cannot remove the active_db
- Returns: `{ ok: true }`

**`GET /api/admin/browse`**
Query: `path` (directory to browse)
- Returns directory listing filtered to show directories + `.db` files
- Reuse pattern from existing `api/files.py` browse endpoint

### Modify `main.py`

- On startup: load config, if `active_db` is set → use it as DB_PATH, run migrations + seed loader as before
- If `active_db` is not set → skip DB initialization (no migrations, no seed loader). The app starts but most endpoints will fail until setup is complete. The `/api/health` and `/api/admin/*` endpoints must still work.

### Modify `/api/health`

Add `db_configured: bool` to the health response. Frontend uses this to decide whether to show the setup wizard.

## Frontend

### Setup Wizard (`components/SetupWizard.tsx`)

Shown instead of the normal app when `db_configured: false`. Full-screen centered card with:
- "Welcome to NightCrate" heading
- Database name field (default: "My Equipment Database")
- Database path field (default: `{default_app_dir}/nightcrate.db`) with Browse button
- "Create & Start" button
- On success: reload the page (or re-query health to transition to normal app)

### Admin Page (`pages/AdminPage.tsx`)

Accessible from nav sidebar. Shows:
- **Current database** section: name, path, file size
- **Known databases** list: each entry shows name, path, size, "Activate" button (grayed if already active), "Remove" button (grayed if active)
- **Add database** section: two options:
  - "Create New" — opens dialog with name + path fields
  - "Add Existing" — opens file browser dialog to pick a `.db` file, then prompts for name
- After activating a different DB: invalidate all TanStack Query caches

### App.tsx changes

- Query `/api/health` on load
- If `db_configured: false` → render `<SetupWizard />` instead of `<AppShell />`
- If `db_configured: true` → render normal app

### AppShell.tsx changes

- Add "Admin" nav item with appropriate icon (e.g., `AdminPanelSettingsIcon`)

## Tests

### `tests/test_app_config.py`
- Config file creation/loading/saving
- Default path when no config exists
- Adding/removing database entries
- Active DB switching

### `tests/test_admin_api.py`
- `GET /api/admin/status` — configured and unconfigured states
- `POST /api/admin/database/create` — creates DB, runs migrations
- `POST /api/admin/database/activate` — switches active DB
- `POST /api/admin/database/setup` — first-run setup
- `DELETE /api/admin/database` — removes from known list
- Edge cases: activate non-existent path, remove active DB (rejected), create at invalid path

## Out of Scope

- Database deletion (only "forget" — never delete user's files)
- Database backup/restore
- Database migration between versions
- Remote database access
