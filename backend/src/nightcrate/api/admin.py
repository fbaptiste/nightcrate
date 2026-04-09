"""Admin API endpoints — database management, status, and app info."""

import importlib.resources
import sqlite3
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from nightcrate.core.app_config import (
    APP_DIR,
    CONFIG_PATH,
    DatabaseEntry,
    load_config,
    save_config,
)
from nightcrate.db.migrations import apply_migrations
from nightcrate.db.session import set_db_path
from nightcrate.seed_loader import load_all

_VERSION_FILE = Path(__file__).resolve().parents[3] / "VERSION"
_APP_VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateDatabaseRequest(BaseModel):
    path: str
    name: str


class ActivateDatabaseRequest(BaseModel):
    path: str


class RemoveDatabaseRequest(BaseModel):
    path: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db_size(path: str) -> int | None:
    """Return file size in bytes, or None if the file doesn't exist."""
    p = Path(path)
    if p.is_file():
        return p.stat().st_size
    return None


def _initialize_database(db_path: Path) -> None:
    """Run migrations and seed loader on a database."""
    apply_migrations(db_path=db_path)

    csv_root = importlib.resources.files("nightcrate") / "data" / "seed"
    sync_conn = sqlite3.connect(str(db_path))
    sync_conn.row_factory = sqlite3.Row
    sync_conn.execute("PRAGMA foreign_keys = ON")
    load_all(sync_conn, csv_root, "auto")
    sync_conn.commit()
    sync_conn.close()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/info")
async def admin_info() -> dict:
    """Return read-only application info."""
    return {
        "config_file": str(CONFIG_PATH),
        "app_data_dir": str(APP_DIR),
        "backend_root": str(Path(__file__).resolve().parents[1]),
        "seed_data_dir": str(importlib.resources.files("nightcrate") / "data" / "seed"),
        "python_version": sys.version.split()[0],
        "app_version": _APP_VERSION,
    }


@router.get("/status")
async def admin_status() -> dict:
    """Return database configuration status."""
    config = load_config()

    active_db_info = None
    if config.active_db is not None:
        size = _db_size(config.active_db)
        available = size is not None
        active_db_info = {
            "path": config.active_db,
            "name": config.databases.get(config.active_db, DatabaseEntry(name="")).name,
            "available": available,
            "size_bytes": size,
        }

    known_databases = []
    for path, entry in config.databases.items():
        size = _db_size(path)
        known_databases.append(
            {
                "path": path,
                "name": entry.name,
                "available": size is not None,
                "size_bytes": size,
            }
        )

    return {
        "db_configured": config.db_configured,
        "active_db": active_db_info,
        "known_databases": known_databases,
    }


@router.post("/database/create")
async def create_database(req: CreateDatabaseRequest) -> dict:
    """Create a new database at the given path without activating it."""
    db_path = Path(req.path)

    if db_path.exists():
        raise HTTPException(status_code=400, detail=f"Path already exists: {req.path}")

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _initialize_database(db_path)

    config = load_config()
    config.databases[req.path] = DatabaseEntry(name=req.name)
    save_config(config)

    return {
        "path": req.path,
        "name": req.name,
        "size_bytes": _db_size(req.path),
        "available": True,
    }


@router.post("/database/activate")
async def activate_database(req: ActivateDatabaseRequest) -> dict:
    """Activate a known database, running migrations and seed loader first."""
    config = load_config()

    if req.path not in config.databases:
        raise HTTPException(status_code=400, detail=f"Path not in known databases: {req.path}")

    db_path = Path(req.path)
    if not db_path.is_file():
        raise HTTPException(status_code=400, detail=f"Database file does not exist: {req.path}")

    _initialize_database(db_path)

    config.active_db = req.path
    save_config(config)

    # Hot-swap the runtime database path
    set_db_path(db_path)

    entry = config.databases[req.path]
    size = _db_size(req.path)
    return {
        "path": req.path,
        "name": entry.name,
        "available": True,
        "size_bytes": size,
    }


@router.post("/database/setup")
async def setup_database(req: CreateDatabaseRequest) -> dict:
    """First-run setup: create, migrate, seed, and activate a new database.

    Returns 409 if a database is already configured.
    """
    config = load_config()
    if config.db_configured:
        raise HTTPException(
            status_code=409, detail="A database is already configured. Use activate instead."
        )

    db_path = Path(req.path)

    if db_path.exists():
        raise HTTPException(status_code=400, detail=f"Path already exists: {req.path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    _initialize_database(db_path)

    config = load_config()
    config.databases[req.path] = DatabaseEntry(name=req.name)
    config.active_db = req.path
    save_config(config)

    # Hot-swap the runtime database path
    set_db_path(db_path)

    return {
        "path": req.path,
        "name": req.name,
        "size_bytes": _db_size(req.path),
        "available": True,
    }


@router.delete("/database")
async def remove_database(req: RemoveDatabaseRequest) -> dict:
    """Remove a database from the known list. Does not delete the file."""
    config = load_config()

    if config.active_db == req.path:
        raise HTTPException(
            status_code=400, detail="Cannot remove the active database. Activate another first."
        )

    if req.path not in config.databases:
        raise HTTPException(status_code=400, detail=f"Path not in known databases: {req.path}")

    del config.databases[req.path]
    save_config(config)

    return {"ok": True}


@router.get("/browse")
async def browse_filesystem(path: str = Query(default="~")) -> dict:
    """List directories and .db files at the given filesystem path."""
    resolved = Path(path).expanduser().resolve()

    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    dirs = []
    files = []

    try:
        for entry in sorted(resolved.iterdir(), key=lambda e: e.name.lower()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                dirs.append({"name": entry.name, "path": str(entry)})
            elif entry.is_file() and entry.suffix.lower() == ".db":
                files.append(
                    {
                        "name": entry.name,
                        "path": str(entry),
                        "size": entry.stat().st_size,
                    }
                )
    except PermissionError:
        pass  # Return whatever we managed to collect

    return {"path": str(resolved), "dirs": dirs, "files": files}
