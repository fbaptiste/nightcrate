"""Async SQLite connection factory."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

from nightcrate.core import app_config
from nightcrate.core.app_config import (
    get_active_db_path,
    get_default_db_path,
    load_config,
    workspace_db_path,
)

if TYPE_CHECKING:
    from nightcrate.db.workspace_upgrade import WorkspaceProblem

# Runtime-mutable path — set during startup or hot-swapped by admin API
_db_path: Path | None = None
_workspace_key: str | None = None
_workspace_problem: WorkspaceProblem | None = None


class WorkspaceUnavailable(RuntimeError):
    """The configured workspace was refused during guarded activation."""


def set_workspace_problem(problem: WorkspaceProblem | None) -> None:
    global _workspace_problem
    _workspace_problem = problem


def workspace_problem() -> WorkspaceProblem | None:
    return _workspace_problem


def active_db_path_or_none() -> Path | None:
    """Return the configured active database unless activation is blocked."""
    if _workspace_problem is not None:
        return None
    if _db_path is not None:
        return _db_path
    config = load_config()
    return workspace_db_path(Path(config.active_db)) if config.active_db is not None else None


def get_db_path() -> Path:
    """Return the current database path."""
    if _workspace_problem is not None:
        raise WorkspaceUnavailable("The active workspace is unavailable")
    if _db_path is not None:
        return _db_path
    path = get_active_db_path()
    if path is not None:
        return path
    return get_default_db_path()


def set_db_path(path: Path) -> None:
    """Set the active database path at runtime."""
    global _db_path, _workspace_key
    _db_path = path
    _workspace_key = secrets.token_hex(6)


def workspace_key() -> str:
    """Return the per-activation token used to distinguish image URLs."""
    global _workspace_key
    if _workspace_key is None:
        _workspace_key = secrets.token_hex(6)
    return _workspace_key


def _ensure_app_dir() -> None:
    app_config.APP_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """Yield an aiosqlite connection with row_factory set to return dicts."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn
