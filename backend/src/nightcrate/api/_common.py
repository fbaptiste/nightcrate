"""Shared router helpers — row serialisation, boolean normalisation,
seed-field stripping, and structured integrity-error handling.

Historically these helpers were copy-pasted into each of ``api/equipment.py``,
``api/rigs.py``, and ``api/locations.py`` — three subtly different copies.
The common ones now live here; routers import from a single source.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import aiosqlite
from fastapi import HTTPException

# Columns stripped from API responses for every seed-tracked equipment row.
# Kept in sync with the seed loader contract (services/seed_loader/registry.py).
_SEED_KEYS: tuple[str, ...] = ("source", "seed_key", "seed_hash")


def row_to_dict(
    row: Any,
    *,
    extra_fn: Callable[[dict], None] | None = None,
) -> dict:
    """Turn an ``aiosqlite.Row`` into a plain ``dict``.

    ``extra_fn`` is an optional post-processing hook — for example, locations
    use it to derive ``latitude_display`` / ``longitude_display``. It runs in
    place and may add/overwrite keys but should not raise on missing columns.
    """
    d = dict(row)
    if extra_fn is not None:
        extra_fn(d)
    return d


def bool_fields(d: dict, *keys: str) -> dict:
    """Coerce the given INTEGER(0/1) columns to Python booleans, in place."""
    for k in keys:
        if k in d and d[k] is not None:
            d[k] = bool(d[k])
    return d


def strip_seed(d: dict) -> dict:
    """Drop seed-tracking columns (source/seed_key/seed_hash) from a row
    dict so they never leak into API responses."""
    for k in _SEED_KEYS:
        d.pop(k, None)
    return d


@contextmanager
def integrity_guard(
    *,
    conflict_detail: str,
) -> Iterator[None]:
    """Translate SQLite UNIQUE-constraint violations into HTTP 409.

    Wraps an INSERT/UPDATE block. On ``aiosqlite.IntegrityError`` with
    ``sqlite_errorname == 'SQLITE_CONSTRAINT_UNIQUE'``, raises
    ``HTTPException(409, conflict_detail)`` instead of the string-matching
    anti-pattern (``if "UNIQUE" in str(exc): ...``) that was scattered
    across routers before. Non-UNIQUE integrity errors propagate unchanged.

    Usage::

        with integrity_guard(conflict_detail="Camera already exists"):
            await conn.execute("INSERT INTO camera ...")
    """
    try:
        yield
    except aiosqlite.IntegrityError as exc:
        errname = getattr(exc, "sqlite_errorname", "") or ""
        if errname == "SQLITE_CONSTRAINT_UNIQUE":
            raise HTTPException(status_code=409, detail=conflict_detail) from exc
        raise
