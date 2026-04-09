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
