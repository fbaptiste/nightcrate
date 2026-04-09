"""Application config — persisted in config.json, independent of the database.

The config file lives in the platformdirs app data directory. It stores the
list of known databases and which one is currently active.
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
    databases: dict[str, DatabaseEntry] = field(default_factory=dict)  # path str → entry
    active_db: str | None = None  # path str of active DB

    @property
    def db_configured(self) -> bool:
        """True if active_db is set AND the file exists on disk."""
        if self.active_db is None:
            return False
        return Path(self.active_db).is_file()


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
    """Return the active database path, or None if not configured/available."""
    config = load_config()
    if config.active_db is None:
        return None
    path = Path(config.active_db)
    if not path.is_file():
        return None
    return path


def get_default_db_path() -> Path:
    """Return the default database path (for setup wizard default)."""
    return APP_DIR / "nightcrate.db"
