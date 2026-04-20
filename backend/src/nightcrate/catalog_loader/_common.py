"""Shared helpers used by the per-source DSO loaders.

v0.14.0 had a single OpenNGC-specific loader. v0.15.0 added four more
parser strategies (Sharpless, Barnard, 50 MGC, augment CSV) that all
share the same low-level patterns — file-hash check, source-registry
upsert, DSO/designation inserts, string normalisation. This module
holds those primitives so the per-strategy loaders stay focused on
their parser-specific logic.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from nightcrate.catalog_loader.loader import SourceResult
from nightcrate.catalog_loader.registry import CatalogSource

# ── Small value parsers ─────────────────────────────────────────────────────


def maybe_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def maybe_str(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


# ── Designation search-key normalisation (mirrors api/dso.py) ───────────────

_SEARCH_STRIP_RE = re.compile(r"[\s\-_]+")

# Long catalog names users may type get rewritten to the short display-form
# prefix used by stored ``dso_designation.search_key`` values.
_LONG_TO_SHORT_PREFIX: dict[str, str] = {
    "messier": "m",
    "caldwell": "c",
    "sharpless2": "sh2",
    "barnard": "b",
    "hickson": "hcg",
}


def normalize_designation(query: str) -> str:
    """Return the ``search_key``-compatible form of *query*.

    e.g. ``"M 42"`` → ``"m42"``, ``"messier 42"`` → ``"m42"``,
    ``"NGC 1976"`` → ``"ngc1976"``, ``"Sh2-281"`` → ``"sh2281"``.
    """
    normalized = _SEARCH_STRIP_RE.sub("", query).lower()
    for long, short in _LONG_TO_SHORT_PREFIX.items():
        if normalized.startswith(long):
            return short + normalized[len(long) :]
    return normalized


# ── dso_catalog_source upsert ───────────────────────────────────────────────


def upsert_catalog_source(
    cur: sqlite3.Cursor,
    source: CatalogSource,
    file_hash: str,
    row_count: int,
) -> int:
    """Insert or update the ``dso_catalog_source`` row for *source*.

    Returns the row's integer id. Any follow-up DSO inserts use this as
    their ``source_catalog_id`` FK so a future wipe-and-reload can
    ``DELETE FROM dso WHERE source_catalog_id = ?`` cleanly.
    """
    cur.execute(
        "SELECT id FROM dso_catalog_source WHERE source_id = ?",
        (source.source_id,),
    )
    existing = cur.fetchone()
    if existing is None:
        cur.execute(
            """
            INSERT INTO dso_catalog_source (
                source_id, category, display_name, version, source_url,
                file_path, file_hash, license, attribution, row_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.source_id,
                source.category,
                source.display_name,
                source.version,
                source.source_url,
                str(source.file_path),
                file_hash,
                source.license,
                source.attribution,
                row_count,
            ),
        )
        new_id = cur.lastrowid
        if new_id is None:
            raise RuntimeError("dso_catalog_source INSERT returned no row id")
        return new_id

    cur.execute(
        """
        UPDATE dso_catalog_source SET
            category = ?, display_name = ?, version = ?, source_url = ?,
            file_path = ?, file_hash = ?, license = ?, attribution = ?,
            loaded_at = datetime('now'), row_count = ?
        WHERE id = ?
        """,
        (
            source.category,
            source.display_name,
            source.version,
            source.source_url,
            str(source.file_path),
            file_hash,
            source.license,
            source.attribution,
            row_count,
            existing[0],
        ),
    )
    return existing[0]


def clear_previous_source_rows(
    cur: sqlite3.Cursor,
    source: CatalogSource,
    *,
    logger: logging.Logger,
) -> None:
    """Delete DSOs previously inserted by *source*, if any.

    Scoped via the ``source_catalog_id`` FK; the ``ON DELETE CASCADE`` on
    ``dso_designation`` cleans up the children. No-op when the source
    has never been loaded before. Logs the deleted-row count at INFO.
    """
    cur.execute(
        "SELECT id FROM dso_catalog_source WHERE source_id = ?",
        (source.source_id,),
    )
    existing = cur.fetchone()
    if existing is None:
        return
    cur.execute("DELETE FROM dso WHERE source_catalog_id = ?", (existing[0],))
    label = logger.name.rsplit(".", 1)[-1]
    logger.info("[%s] %s: cleared %d previous rows", label, source.source_id, cur.rowcount)


# ── DSO + designation inserts ───────────────────────────────────────────────


def insert_dso(
    cur: sqlite3.Cursor,
    *,
    primary_designation: str,
    obj_type: str,
    ra_deg: float | None,
    dec_deg: float | None,
    constellation: str | None,
    maj_axis_arcmin: float | None,
    min_axis_arcmin: float | None,
    common_name: str | None,
    openngc_notes: str | None,
    source_catalog_id: int,
    source_row_hash: str,
) -> int:
    """Insert a minimal DSO row used by Sharpless/Barnard loaders.

    OpenNGC has its own richer insert in ``loader.py:_insert_dso`` — this
    helper covers the simpler case where only coordinates + geometry +
    common_name are known.
    """
    cur.execute(
        """
        INSERT INTO dso (
            primary_designation, obj_type, ra_deg, dec_deg, constellation,
            maj_axis_arcmin, min_axis_arcmin, common_name, openngc_notes,
            source_catalog_id, source_row_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            primary_designation,
            obj_type,
            ra_deg,
            dec_deg,
            constellation,
            maj_axis_arcmin,
            min_axis_arcmin,
            common_name,
            openngc_notes,
            source_catalog_id,
            source_row_hash,
        ),
    )
    dso_id = cur.lastrowid
    if dso_id is None:
        raise RuntimeError("dso INSERT returned no row id")
    return dso_id


def insert_designation(
    cur: sqlite3.Cursor,
    *,
    dso_id: int,
    catalog: str,
    identifier: str,
    display_form: str,
    search_key: str,
    is_primary: bool,
    logger: logging.Logger | None = None,
) -> bool:
    """Insert a designation; return True if inserted, False on UNIQUE collision.

    A collision means another DSO already claims this (catalog, identifier)
    pair — the existing owner wins and the incoming row loses that
    cross-reference. Caller gets False so it can keep its own counters
    accurate.
    """
    try:
        cur.execute(
            """
            INSERT INTO dso_designation
                (dso_id, catalog, identifier, display_form, search_key, is_primary)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (dso_id, catalog, identifier, display_form, search_key, 1 if is_primary else 0),
        )
        return True
    except sqlite3.IntegrityError:
        if logger is not None:
            logger.debug(
                "[%s] designation collision: %s %s already claimed",
                logger.name.rsplit(".", 1)[-1],
                catalog,
                identifier,
            )
        return False


# ── Hash-check preamble used by every loader ────────────────────────────────


@dataclass(frozen=True, slots=True)
class LoaderPreflight:
    """Outcome of the pre-load hash check.

    When ``status`` is ``missing`` / ``unchanged``, the loader returns
    the ``preset_result`` immediately. Otherwise it proceeds with the
    heavy load and uses the caller's own per-source logic.
    """

    preset_result: SourceResult | None


def check_source_state(
    conn: sqlite3.Connection,
    source: CatalogSource,
    effective_hash: str,
    *,
    force: bool,
) -> LoaderPreflight:
    """Handle the missing / hash-match short-circuit shared by all loaders.

    Returns a ``LoaderPreflight`` whose ``preset_result`` is non-None when
    the caller should early-return (file missing or hash unchanged).
    A ``None`` return signals "proceed with the full load"; the caller is
    responsible for ``BEGIN``, clearing prior rows, calling
    :func:`upsert_catalog_source`, parsing, inserting, and committing.
    """
    if not source.file_path.exists():
        return LoaderPreflight(
            SourceResult(
                source_id=source.source_id,
                status="missing",
                error=f"file not found: {source.file_path}",
            )
        )

    cur = conn.cursor()
    cur.execute(
        "SELECT id, file_hash FROM dso_catalog_source WHERE source_id = ?",
        (source.source_id,),
    )
    existing = cur.fetchone()
    if existing and existing[1] == effective_hash and not force:
        cur.execute("SELECT row_count FROM dso_catalog_source WHERE id = ?", (existing[0],))
        row = cur.fetchone()
        dso_count = int(row[0]) if row else 0
        return LoaderPreflight(
            SourceResult(
                source_id=source.source_id,
                status="unchanged",
                dso_count=dso_count,
            )
        )
    return LoaderPreflight(preset_result=None)


# ── Retry layer shared between GitHub (remote.py) + VizieR (vizier.py) ──────

_DEFAULT_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_MIN_S = 0.6
_RETRY_BACKOFF_MAX_S = 1.4


async def retry_with_backoff[T](
    coro_factory: Callable[[], Awaitable[T]],
    *,
    label: str,
    logger: logging.Logger,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
) -> T:
    """Run *coro_factory* up to *max_attempts* times with jittered backoff.

    Sits on top of ``services/http_client.get``'s own single-retry-per-call,
    so the worst case is ~2 × max_attempts underlying HTTP attempts per
    URL. Used by the GitHub and VizieR fetchers.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_factory()
        except Exception as exc:  # noqa: BLE001 — diagnostic-only retry layer
            last_exc = exc
            logger.warning(
                "[%s] %s attempt %d/%d failed: %s",
                logger.name.rsplit(".", 1)[-1],
                label,
                attempt,
                max_attempts,
                exc,
            )
            if attempt == max_attempts:
                raise
            await asyncio.sleep(
                random.uniform(_RETRY_BACKOFF_MIN_S, _RETRY_BACKOFF_MAX_S)  # nosec B311
            )
    raise last_exc if last_exc is not None else RuntimeError("retry loop exhausted")
