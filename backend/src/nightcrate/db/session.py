"""Async SQLite connection factory."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

APP_DIR = Path(os.path.expanduser("~/Library/Application Support/NightCrate"))
DB_PATH = APP_DIR / "nightcrate.db"


def _ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """Yield an aiosqlite connection with row_factory set to return dicts."""
    _ensure_app_dir()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn
