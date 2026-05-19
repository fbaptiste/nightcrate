"""Application config — persisted in config.json, independent of the database.

The config file lives in the platformdirs app data directory. It stores the
list of known workspaces and which one is currently active.

A **workspace** is a user-named directory containing ``nightcrate.db`` plus a
``project_data/`` folder for rendered images. The entire workspace is
self-contained and portable.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_data_dir

APP_DIR = Path(user_data_dir("NightCrate", appauthor=False))
CONFIG_PATH = APP_DIR / "config.json"

DB_FILENAME = "nightcrate.db"


@dataclass
class DatabaseEntry:
    name: str


@dataclass
class AppConfig:
    databases: dict[str, DatabaseEntry] = field(default_factory=dict)  # workspace path str → entry
    active_db: str | None = None  # workspace folder path str

    @property
    def db_configured(self) -> bool:
        """True if active_db is set AND the database file exists inside the workspace."""
        if self.active_db is None:
            return False
        return workspace_db_path(Path(self.active_db)).is_file()


def workspace_db_path(workspace: Path) -> Path:
    """Return the database file path for a workspace folder."""
    return workspace / DB_FILENAME


def load_config() -> AppConfig:
    """Load config from disk. Returns empty config if file doesn't exist or is corrupt."""
    if not CONFIG_PATH.is_file():
        return AppConfig()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        databases = {
            path: DatabaseEntry(name=entry["name"])
            for path, entry in data.get("databases", {}).items()
        }
        active_db = data.get("active_db", None)
        return AppConfig(databases=databases, active_db=active_db)
    except Exception:
        return AppConfig()


def save_config(config: AppConfig) -> None:
    """Write config to disk. Creates the directory if needed."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "databases": {path: asdict(entry) for path, entry in config.databases.items()},
        "active_db": config.active_db,
    }
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_active_db_path() -> Path | None:
    """Return the active database file path, or None if not configured."""
    config = load_config()
    if config.active_db is None:
        return None
    db = workspace_db_path(Path(config.active_db))
    if not db.is_file():
        return None
    return db


def get_active_workspace() -> Path | None:
    """Return the active workspace folder path, or None if not configured."""
    config = load_config()
    if config.active_db is None:
        return None
    ws = Path(config.active_db)
    if not workspace_db_path(ws).is_file():
        return None
    return ws


def get_default_db_path() -> Path:
    """Return the default database path (for setup wizard default)."""
    return workspace_db_path(APP_DIR / "Default")


def get_default_workspace() -> Path:
    """Return the default workspace folder (for setup wizard default)."""
    return APP_DIR / "Default"


def get_projects_root() -> Path | None:
    """Return the project storage root inside the active workspace.

    Returns ``{workspace}/project_data/``, or ``None`` when no workspace
    is configured. The directory is not auto-created — callers create it
    on demand.

    Uses the runtime DB path from ``db.session`` (which tests can
    monkeypatch) to derive the workspace, rather than reading the config
    file directly.
    """
    from nightcrate.db.session import get_db_path

    try:
        db_path = get_db_path()
    except Exception:
        return None
    if db_path is None:
        return None
    return db_path.parent / "project_data"
