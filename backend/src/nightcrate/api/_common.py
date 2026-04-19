"""Shared router helpers — row serialisation, boolean normalisation,
seed-field stripping, and structured integrity-error handling."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import aiosqlite
from fastapi import HTTPException

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
    constraint_map: dict[str, str] | None = None,
    check_detail: str | None = None,
) -> Iterator[None]:
    """Translate SQLite integrity errors into HTTP responses.

    Wraps an INSERT/UPDATE block and converts structured SQLite error names
    (`sqlite_errorname`) into the appropriate HTTPException:

    - ``SQLITE_CONSTRAINT_UNIQUE`` → 409. If ``constraint_map`` is provided,
      the exception's ``str()`` is searched for each mapping key; the first
      match wins and its value becomes the 409 detail. ``conflict_detail``
      is the fallback when no mapping key matches (or when no map is given).
    - ``SQLITE_CONSTRAINT_CHECK`` → 422 with ``check_detail`` (if set).
      Covers closed-vocabulary CHECK constraints like `software.category`.

    Non-matching integrity errors propagate unchanged.

    Usage::

        with integrity_guard(conflict_detail="Camera already exists"):
            await conn.execute("INSERT INTO camera ...")

        with integrity_guard(
            conflict_detail="Name already exists",
            constraint_map={
                "idx_telescope_one_native": "A native config already exists",
            },
        ):
            ...
    """
    try:
        yield
    except aiosqlite.IntegrityError as exc:
        errname = getattr(exc, "sqlite_errorname", "") or ""
        if errname == "SQLITE_CONSTRAINT_UNIQUE":
            if constraint_map:
                msg = str(exc)
                for needle, detail in constraint_map.items():
                    if needle in msg:
                        raise HTTPException(status_code=409, detail=detail) from exc
            raise HTTPException(status_code=409, detail=conflict_detail) from exc
        if errname == "SQLITE_CONSTRAINT_CHECK" and check_detail is not None:
            raise HTTPException(status_code=422, detail=check_detail) from exc
        raise
