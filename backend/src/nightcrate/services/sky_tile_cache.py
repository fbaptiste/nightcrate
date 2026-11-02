"""Sky-tile cache — v0.18.0 / Pass C.

Maintains an LRU disk cache of HEALPix-regional TAN tiles that back the
FOV simulator (and, later, the DSO catalog's auto-zoom preview). Each
cell is identified by
``(hips_survey, healpix_nside, healpix_ipix, tier, cell_size_deg_x100,
cell_width_px, cell_height_px, cell_i, cell_j)`` — no ``dso_id``, so
neighbouring DSOs in the same region share cells naturally.

Request lifecycle mirrors ``services/thumbnails.py`` — lookup, background
fetch via ``asyncio.create_task`` with an in-flight dedup map, optional
long-poll under ``asyncio.shield``, 10-minute failure backoff, and a
HiPS-tile render using the shared regional WCS so every cell in a region
lands on the same tangent plane.

Files live under ``APP_DIR/sky_tiles/`` (separate from
``APP_DIR/thumbnails/`` so the orphan-file sweeps don't mix the two
caches).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import aiosqlite

from nightcrate.services import hips_tiles, image_cache
from nightcrate.services.sky_tiles import (
    TIERS,
    Tier,
    TierSpec,
    cell_wcs,
)

logger = logging.getLogger("nightcrate.sky_tile_cache")


# 1×1 transparent PNG — tiny, valid, doubles as the placeholder while
# the background fetch runs. Matches ``services/thumbnails.py`` so the
# frontend's placeholder detection (``naturalWidth <= 1``) works
# uniformly across both caches.
_PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154785e63faffff3f0305000602020069b7c3c50000000049454e"
    "44ae426082"
)

_FETCH_ERROR_BACKOFF = timedelta(minutes=10)

# Cap how many cache-miss tasks can queue renders at once. The shared HiPS
# service applies the tighter CPU and upstream-request limits across both
# rendered-image caches.
_MAX_CONCURRENT_FETCHES = 8
_fetch_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)


# ── Value objects ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CellKey:
    """Fully-qualified sky-tile cache key.

    Field order mirrors the unique index in migration 0020. Two cells
    with equal keys share a cache row; two with any field different get
    their own rows. ``cell_size_deg_x100`` + the pixel dimensions sit in
    the key so a future change to any tier's spec doesn't collide with
    existing rows — they simply age out via LRU.
    """

    hips_survey: str
    healpix_nside: int
    healpix_ipix: int
    tier: Tier
    cell_size_deg_x100: int
    cell_width_px: int
    cell_height_px: int
    cell_i: int
    cell_j: int


@dataclass(frozen=True, slots=True)
class CellResult:
    body: bytes
    content_type: str
    status: Literal["hit", "placeholder", "error"]


def make_cell_key(
    *,
    hips_survey: str,
    healpix_nside: int,
    healpix_ipix: int,
    tier: TierSpec,
    cell_i: int,
    cell_j: int,
) -> CellKey:
    return CellKey(
        hips_survey=hips_survey,
        healpix_nside=healpix_nside,
        healpix_ipix=healpix_ipix,
        tier=tier.name,
        cell_size_deg_x100=tier.cell_size_deg_x100,
        cell_width_px=tier.cell_width_px,
        cell_height_px=tier.cell_height_px,
        cell_i=cell_i,
        cell_j=cell_j,
    )


# ── Disk layout ──────────────────────────────────────────────────────────────


def cell_dir(*, create: bool = True) -> Path:
    """User-writable directory. Created on first access."""
    return image_cache.cache_dir("sky_tile", create=create)


def _hips_slug(hips_survey: str) -> str:
    # ``CDS/P/DSS2/color`` → ``CDS_P_DSS2_color`` so the string is safe
    # on every filesystem.
    return re.sub(r"[^A-Za-z0-9_]", "_", hips_survey)


def _cell_path(key: CellKey) -> Path:
    return cell_dir() / (
        f"{_hips_slug(key.hips_survey)}_"
        f"n{key.healpix_nside}_p{key.healpix_ipix}_"
        f"{key.tier}_{key.cell_size_deg_x100}_"
        f"{key.cell_width_px}x{key.cell_height_px}_"
        f"{key.cell_i}_{key.cell_j}.jpg"
    )


# Filename pattern — kept loose enough to evolve without breaking the
# orphan sweep. The sweep only deletes files that BOTH match this regex
# AND are absent from the cache table, so a stricter match is preferred.
_CELL_FILENAME_RE = image_cache.SKY_TILE_FILENAME_RE


# ── Cache lookup + mutation ──────────────────────────────────────────────────


async def _lookup_cache_row(conn: aiosqlite.Connection, key: CellKey) -> aiosqlite.Row | None:
    cursor = await conn.execute(
        """
        SELECT id, file_path, source, bytes, fetched_at, fetch_error
        FROM sky_tile_cache
        WHERE hips_survey = ? AND healpix_nside = ? AND healpix_ipix = ?
          AND tier = ? AND cell_size_deg_x100 = ?
          AND cell_width_px = ? AND cell_height_px = ?
          AND cell_i = ? AND cell_j = ?
        """,
        (
            key.hips_survey,
            key.healpix_nside,
            key.healpix_ipix,
            key.tier,
            key.cell_size_deg_x100,
            key.cell_width_px,
            key.cell_height_px,
            key.cell_i,
            key.cell_j,
        ),
    )
    return await cursor.fetchone()


async def _touch_last_access(conn: aiosqlite.Connection, row_id: int) -> None:
    await conn.execute(
        "UPDATE sky_tile_cache SET last_access_at = datetime('now') WHERE id = ?",
        (row_id,),
    )
    await conn.commit()


async def _delete_cache_row(conn: aiosqlite.Connection, row_id: int) -> None:
    await conn.execute("DELETE FROM sky_tile_cache WHERE id = ?", (row_id,))
    await conn.commit()


async def _insert_cache_row(
    conn: aiosqlite.Connection,
    key: CellKey,
    *,
    file_path: str,
    source: str,
    bytes_size: int,
    fetch_error: str | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO sky_tile_cache (
            hips_survey, healpix_nside, healpix_ipix, tier,
            cell_size_deg_x100, cell_width_px, cell_height_px,
            cell_i, cell_j,
            file_path, source, bytes, fetch_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key.hips_survey,
            key.healpix_nside,
            key.healpix_ipix,
            key.tier,
            key.cell_size_deg_x100,
            key.cell_width_px,
            key.cell_height_px,
            key.cell_i,
            key.cell_j,
            file_path,
            source,
            bytes_size,
            fetch_error,
        ),
    )
    await conn.commit()


async def _evict_lru(conn: aiosqlite.Connection, max_bytes: int) -> int:
    """Evict against the budget shared with DSO thumbnails."""
    async with image_cache.lock:
        return await image_cache.evict_lru_locked(conn, max_bytes)


# ── Background fetch ─────────────────────────────────────────────────────────

_in_flight: dict[CellKey, asyncio.Task] = {}
_failure_backoff: dict[CellKey, float] = {}


def _clock() -> float:
    return time.monotonic()


def _failure_backoff_active(key: CellKey) -> bool:
    deadline = _failure_backoff.get(key)
    if deadline is None:
        return False
    if deadline > _clock():
        return True
    _failure_backoff.pop(key, None)
    return False


async def _record_fetch_failure(
    conn: aiosqlite.Connection,
    key: CellKey,
    *,
    file_path: str,
    error: Exception,
    expected_generation: int | None = None,
) -> None:
    """Persist a failure sentinel, falling back to a process-local backoff."""
    async with image_cache.lock:
        if expected_generation is not None and expected_generation != image_cache.generation():
            return
        try:
            await conn.rollback()
        except Exception:  # noqa: BLE001 — recovery is best effort
            logger.debug("[sky_tiles] rollback before failure sentinel failed", exc_info=True)
        try:
            await _insert_cache_row(
                conn,
                key,
                file_path=file_path,
                source="placeholder",
                bytes_size=0,
                fetch_error=str(error),
            )
        except Exception:  # noqa: BLE001 — the in-memory backoff is the final guard
            try:
                await conn.rollback()
            except Exception:  # noqa: BLE001 — recovery is best effort
                logger.debug("[sky_tiles] rollback after failure sentinel failed", exc_info=True)
            _failure_backoff[key] = _clock() + _FETCH_ERROR_BACKOFF.total_seconds()
            logger.exception(
                "[sky_tiles] could not persist failure sentinel for cell=%s; using memory backoff",
                key,
            )
        else:
            _failure_backoff.pop(key, None)


async def _fetch_and_store(
    conn: aiosqlite.Connection,
    key: CellKey,
    *,
    region_ra_deg: float,
    region_dec_deg: float,
    max_cache_bytes: int,
) -> None:
    """Render a DSS2 colour cell from HiPS tiles and persist it.

    Atomic-replace-then-insert ordering means a crash between the two can
    leave a complete orphan file for the startup sweep; it cannot expose a
    partial final JPEG or leave metadata pointing at missing bytes.
    """
    render_generation = image_cache.generation()
    tier = TIERS[key.tier]
    wcs = cell_wcs(region_ra_deg, region_dec_deg, tier, key.cell_i, key.cell_j)

    async with _fetch_semaphore:
        try:
            rendered = await hips_tiles.render(wcs, tier.cell_width_px, tier.cell_height_px)
        except Exception as exc:  # noqa: BLE001 — record + backoff
            logger.warning("[sky_tiles] cell=%s render failed: %s", key, exc)
            await _record_fetch_failure(
                conn,
                key,
                file_path=_cell_path(key).name,
                error=exc,
                expected_generation=render_generation,
            )
            return

    path = _cell_path(key)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        async with image_cache.lock:
            if render_generation != image_cache.generation():
                return
            try:
                temporary.write_bytes(rendered.jpeg)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            await _insert_cache_row(
                conn,
                key,
                file_path=path.name,
                source="dss2_color",
                bytes_size=len(rendered.jpeg),
            )
            await image_cache.evict_lru_locked(conn, max_cache_bytes)
    except Exception as exc:  # noqa: BLE001 — persist failure and enforce backoff
        logger.warning("[sky_tiles] cell=%s persistence failed: %s", key, exc)
        await _record_fetch_failure(
            conn,
            key,
            file_path=path.name,
            error=exc,
            expected_generation=render_generation,
        )
        return
    _failure_backoff.pop(key, None)


async def _background_wrapper(
    conn_factory,
    key: CellKey,
    *,
    region_ra_deg: float,
    region_dec_deg: float,
    max_cache_bytes: int,
) -> None:
    """Run ``_fetch_and_store`` against a fresh aiosqlite connection."""
    try:
        async with conn_factory() as conn:
            conn.row_factory = aiosqlite.Row
            await _fetch_and_store(
                conn,
                key,
                region_ra_deg=region_ra_deg,
                region_dec_deg=region_dec_deg,
                max_cache_bytes=max_cache_bytes,
            )
    except Exception:  # noqa: BLE001 — background tasks mustn't crash the server
        logger.exception("[sky_tiles] background fetch crashed for cell=%s", key)
    finally:
        _in_flight.pop(key, None)


# ── Public API ───────────────────────────────────────────────────────────────


async def get_cell(
    conn: aiosqlite.Connection,
    *,
    key: CellKey,
    region_ra_deg: float,
    region_dec_deg: float,
    max_cache_bytes: int,
    conn_factory,
    wait_timeout_s: float = 0.0,
) -> CellResult:
    """Serve one sky-tile cell, enqueuing a CDS fetch on cache miss.

    Mirrors ``services/thumbnails.get_thumbnail`` — cache hits return
    the JPEG bytes directly, misses schedule a background fetch and
    (optionally) hold the request open via ``asyncio.shield`` so the
    real image lands in the same HTTP round trip.
    """
    row = await _lookup_cache_row(conn, key)

    # Cache hit — serve and refresh LRU.
    if row is not None and row["fetch_error"] is None and row["source"] != "placeholder":
        try:
            path = image_cache.resolve_path(str(row["file_path"]), "sky_tile")
            if path is None:
                raise FileNotFoundError
            body = path.read_bytes()
            await _touch_last_access(conn, row["id"])
            _failure_backoff.pop(key, None)
            return CellResult(body=body, content_type="image/jpeg", status="hit")
        except FileNotFoundError:
            logger.warning(
                "[sky_tiles] orphan metadata for cell=%s — refetching",
                key,
            )
            await _delete_cache_row(conn, row["id"])
            row = None

    # Permanent-failure short-circuit during the backoff window.
    if row is not None and row["fetch_error"] is not None:
        fetched_at = datetime.fromisoformat(row["fetched_at"]).replace(tzinfo=UTC)
        if datetime.now(UTC) - fetched_at < _FETCH_ERROR_BACKOFF:
            return CellResult(body=b"", content_type="image/png", status="error")
        await _delete_cache_row(conn, row["id"])

    if _failure_backoff_active(key):
        return CellResult(body=b"", content_type="image/png", status="error")

    # Miss — schedule (or reuse) the background fetch.
    task = _in_flight.get(key)
    if task is None:
        task = asyncio.create_task(
            _background_wrapper(
                conn_factory,
                key,
                region_ra_deg=region_ra_deg,
                region_dec_deg=region_dec_deg,
                max_cache_bytes=max_cache_bytes,
            )
        )
        _in_flight[key] = task
        logger.debug("[sky_tiles] miss cell=%s — enqueued fetch", key)
    else:
        logger.debug("[sky_tiles] miss cell=%s — fetch already in flight", key)

    # Long-poll path. ``asyncio.shield`` keeps the background task alive
    # if the browser disconnects mid-wait — a cancellation from our side
    # must not abort a half-finished CDS request.
    if wait_timeout_s > 0:
        try:
            await asyncio.wait_for(asyncio.shield(task), wait_timeout_s)
        except TimeoutError:
            pass
        else:
            row = await _lookup_cache_row(conn, key)
            if row is not None and row["fetch_error"] is None and row["source"] != "placeholder":
                try:
                    path = image_cache.resolve_path(str(row["file_path"]), "sky_tile")
                    if path is None:
                        raise FileNotFoundError
                    body = path.read_bytes()
                    await _touch_last_access(conn, row["id"])
                    return CellResult(body=body, content_type="image/jpeg", status="hit")
                except FileNotFoundError:
                    pass
            if row is not None and row["fetch_error"] is not None:
                return CellResult(body=b"", content_type="image/png", status="error")
            if _failure_backoff_active(key):
                return CellResult(body=b"", content_type="image/png", status="error")

    return CellResult(body=_PLACEHOLDER_PNG, content_type="image/png", status="placeholder")


async def clear_cache(conn: aiosqlite.Connection) -> int:
    """Wipe the metadata table and every file on disk. Returns files deleted."""
    async with image_cache.lock:
        cursor = await conn.execute("SELECT file_path FROM sky_tile_cache")
        rows = await cursor.fetchall()
        deleted = 0
        for row in rows:
            path = image_cache.resolve_path(str(row["file_path"]), "sky_tile")
            if path is None:
                continue
            existed = path.exists()
            path.unlink(missing_ok=True)
            deleted += int(existed)
        await conn.execute("DELETE FROM sky_tile_cache")
        await conn.commit()
        _failure_backoff.clear()
        image_cache.advance_generation()
        return deleted


def reset_failure_backoff() -> None:
    _failure_backoff.clear()


_REHYDRATE_FILENAME_RE = re.compile(
    r"^(?P<slug>[A-Za-z0-9_]+?)_n(?P<nside>\d+)_p(?P<ipix>\d+)_"
    r"(?P<tier>narrow|med|wide)_(?P<csize>\d+)_"
    r"(?P<w>\d+)x(?P<h>\d+)_(?P<i>-?\d+)_(?P<j>-?\d+)\.jpg$"
)

# Slugs we accept for rehydration. One-way slug mapping
# (``CDS/P/DSS2/color`` → ``CDS_P_DSS2_color``) loses path structure,
# so rehydration is limited to surveys we know about.
_SLUG_TO_HIPS: dict[str, str] = {
    "CDS_P_DSS2_color": "CDS/P/DSS2/color",
}


async def rehydrate_from_disk(conn: aiosqlite.Connection) -> int:
    """Re-index on-disk tile files that are missing from the cache table.

    Fires on app startup before the orphan sweep so a user who wipes
    the database (e.g. via Admin → Database switch) doesn't lose their
    tile cache — the JPEGs live in ``APP_DIR/sky_tiles`` independently
    of the SQLite index. Each filename encodes the full ``CellKey``
    plus cell dimensions, so we can rebuild the DB row without a CDS
    round-trip. Fetch timestamps get reset to "now" since we don't
    know when the file was originally written.

    Returns the number of rows inserted.
    """
    async with image_cache.lock:
        d = cell_dir(create=False)
        if not d.is_dir():
            return 0

        inserted = 0
        changed = False
        for entry in d.iterdir():
            if not entry.is_file() or entry.suffix != ".jpg":
                continue
            if image_cache.resolve_path(entry.name, "sky_tile") is None:
                continue
            match = _REHYDRATE_FILENAME_RE.match(entry.name)
            if match is None:
                continue
            hips = _SLUG_TO_HIPS.get(match.group("slug"))
            if hips is None:
                continue
            size_bytes = entry.stat().st_size
            if size_bytes < 100:
                continue
            values = (
                hips,
                int(match.group("nside")),
                int(match.group("ipix")),
                match.group("tier"),
                int(match.group("csize")),
                int(match.group("w")),
                int(match.group("h")),
                int(match.group("i")),
                int(match.group("j")),
            )
            cursor = await conn.execute(
                """
                SELECT id, file_path, bytes FROM sky_tile_cache
                WHERE hips_survey = ? AND healpix_nside = ? AND healpix_ipix = ?
                  AND tier = ? AND cell_size_deg_x100 = ?
                  AND cell_width_px = ? AND cell_height_px = ?
                  AND cell_i = ? AND cell_j = ?
                """,
                values,
            )
            existing = await cursor.fetchone()
            if existing is not None:
                if existing["file_path"] != entry.name or int(existing["bytes"]) != size_bytes:
                    await conn.execute(
                        "UPDATE sky_tile_cache SET file_path = ?, bytes = ? WHERE id = ?",
                        (entry.name, size_bytes, existing["id"]),
                    )
                    changed = True
                continue
            await conn.execute(
                """
                INSERT INTO sky_tile_cache (
                    hips_survey, healpix_nside, healpix_ipix, tier,
                    cell_size_deg_x100, cell_width_px, cell_height_px,
                    cell_i, cell_j, file_path, source, bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'dss2_color', ?)
                """,
                (*values, entry.name, size_bytes),
            )
            inserted += 1
            changed = True
        if changed:
            await conn.commit()
        if inserted:
            logger.info("[sky_tiles] rehydrated %d on-disk file(s) into the cache index", inserted)
        return inserted


async def sync_orphan_files(conn: aiosqlite.Connection) -> int:
    """Delete on-disk files not referenced by any cache row.

    Called on app startup AFTER ``rehydrate_from_disk``, so any file
    that could be reattached to the index has already been. Anything
    left is either corrupt, from an unrecognised hips survey, or has
    been removed from the cache table explicitly.
    """
    async with image_cache.lock:
        d = cell_dir(create=False)
        if not d.is_dir():
            return 0

        cursor = await conn.execute("SELECT file_path FROM sky_tile_cache")
        known = {
            path.name
            for row in await cursor.fetchall()
            if (path := image_cache.resolve_path(str(row["file_path"]), "sky_tile")) is not None
        }

        removed = 0
        for entry in d.iterdir():
            if not entry.is_file():
                continue
            if image_cache.resolve_path(entry.name, "sky_tile") is None:
                continue
            if entry.name.startswith(".") and entry.suffix == ".tmp":
                entry.unlink(missing_ok=True)
                removed += 1
                continue
            if entry.suffix != ".jpg" or not _CELL_FILENAME_RE.match(entry.name):
                continue
            if entry.name not in known:
                entry.unlink(missing_ok=True)
                removed += 1
        if removed:
            logger.info("[sky_tiles] startup sweep removed %d orphan file(s)", removed)
        return removed


async def cache_stats(conn: aiosqlite.Connection, *, max_bytes: int) -> dict[str, int]:
    """Cache-usage metrics for a future Settings-page integration."""
    cursor = await conn.execute(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(bytes), 0) AS total FROM sky_tile_cache"
    )
    row = await cursor.fetchone()
    return {
        "total_bytes": int(row["total"]) if row else 0,
        "row_count": int(row["cnt"]) if row else 0,
        "max_bytes": max_bytes,
    }
