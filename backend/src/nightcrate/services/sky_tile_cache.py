"""Sky-tile cache — v0.18.0 / Pass C.

Maintains an LRU disk cache of HEALPix-regional TAN tiles that back the
FOV simulator (and, later, the DSO catalog's auto-zoom preview). Each
cell is identified by
``(hips_survey, healpix_nside, healpix_ipix, tier, cell_size_deg_x100,
cell_width_px, cell_height_px, cell_i, cell_j)`` — no ``dso_id``, so
neighbouring DSOs in the same region share cells naturally.

Request lifecycle mirrors ``services/thumbnails.py`` — lookup, background
fetch via ``asyncio.create_task`` with an in-flight dedup map, optional
long-poll under ``asyncio.shield``, 1-hour failure backoff,
``hips2fits`` render via the WCS URL builder so every cell in a region
lands on the same tangent plane.

Files live under ``APP_DIR/sky_tiles/`` (separate from
``APP_DIR/thumbnails/`` so the orphan-file sweeps don't mix the two
caches).
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import aiosqlite

from nightcrate.core.app_config import APP_DIR
from nightcrate.services.hips_client import (
    HIPS_DSS2_COLOR,
    HIPS_DSS2_RED,
    build_hips2fits_wcs_url,
    fetch_hips_image,
)
from nightcrate.services.sky_tiles import (
    TIERS,
    Tier,
    TierSpec,
    cell_wcs_dict,
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

_FETCH_ERROR_BACKOFF = timedelta(hours=1)

_MAX_CONCURRENT_FETCHES = 4
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


def cell_dir() -> Path:
    """User-writable directory. Created on first access."""
    d = APP_DIR / "sky_tiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


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
_CELL_FILENAME_RE = re.compile(
    r"^[A-Za-z0-9_]+_n\d+_p\d+_(narrow|med|wide)_\d+_"
    r"\d+x\d+_-?\d+_-?\d+\.jpg$"
)


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
    """Evict LRU rows until the cache's total size is under ``max_bytes``.

    Deletes the on-disk file before the DB row so a crash in the middle
    doesn't leave an orphan file outliving its metadata.
    """
    cursor = await conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM sky_tile_cache")
    total_row = await cursor.fetchone()
    total = int(total_row[0]) if total_row else 0
    if total <= max_bytes:
        return 0

    evicted = 0
    while total > max_bytes:
        cursor = await conn.execute(
            "SELECT id, file_path, bytes FROM sky_tile_cache ORDER BY last_access_at ASC LIMIT 1"
        )
        oldest = await cursor.fetchone()
        if oldest is None:
            break
        Path(oldest["file_path"]).unlink(missing_ok=True)
        await conn.execute("DELETE FROM sky_tile_cache WHERE id = ?", (oldest["id"],))
        total -= int(oldest["bytes"])
        evicted += 1
    await conn.commit()
    return evicted


# ── Background fetch ─────────────────────────────────────────────────────────

_in_flight: dict[CellKey, asyncio.Task] = {}


async def _fetch_and_store(
    conn: aiosqlite.Connection,
    key: CellKey,
    *,
    region_ra_deg: float,
    region_dec_deg: float,
    max_cache_bytes: int,
) -> None:
    """Fetch a cell from hips2fits (DSS2 Color → DSS2 Red fallback) and persist.

    Write-then-insert ordering means a crash between the two leaves an
    orphan file the startup sweep will clean up; it never leaves a
    dangling metadata row pointing at missing bytes.
    """
    tier = TIERS[key.tier]
    wcs = cell_wcs_dict(region_ra_deg, region_dec_deg, tier, key.cell_i, key.cell_j)
    color_url = build_hips2fits_wcs_url(HIPS_DSS2_COLOR, wcs)
    red_url = build_hips2fits_wcs_url(HIPS_DSS2_RED, wcs)

    async with _fetch_semaphore:
        try:
            body = await fetch_hips_image(color_url)
            source = "dss2_color"
        except Exception as color_exc:  # noqa: BLE001 — fallback on any failure
            logger.info(
                "[sky_tiles] cell=%s color fetch failed (%s); trying DSS2 red",
                key,
                color_exc,
            )
            try:
                body = await fetch_hips_image(red_url)
                source = "dss2_red"
            except Exception as red_exc:  # noqa: BLE001 — record + backoff
                logger.warning(
                    "[sky_tiles] cell=%s both color and red fetches failed: %s / %s",
                    key,
                    color_exc,
                    red_exc,
                )
                await _insert_cache_row(
                    conn,
                    key,
                    file_path=str(_cell_path(key)),
                    source="placeholder",
                    bytes_size=0,
                    fetch_error=f"color: {color_exc}; red: {red_exc}",
                )
                return

    path = _cell_path(key)
    path.write_bytes(body)
    await _insert_cache_row(
        conn,
        key,
        file_path=str(path),
        source=source,
        bytes_size=len(body),
    )
    await _evict_lru(conn, max_cache_bytes)


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
            body = Path(row["file_path"]).read_bytes()
            await _touch_last_access(conn, row["id"])
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
                    body = Path(row["file_path"]).read_bytes()
                    await _touch_last_access(conn, row["id"])
                    return CellResult(body=body, content_type="image/jpeg", status="hit")
                except FileNotFoundError:
                    pass
            if row is not None and row["fetch_error"] is not None:
                return CellResult(body=b"", content_type="image/png", status="error")

    return CellResult(body=_PLACEHOLDER_PNG, content_type="image/png", status="placeholder")


async def clear_cache(conn: aiosqlite.Connection) -> int:
    """Wipe the metadata table and every file on disk. Returns files deleted."""
    cursor = await conn.execute("SELECT file_path FROM sky_tile_cache")
    rows = await cursor.fetchall()
    deleted = 0
    for row in rows:
        Path(row["file_path"]).unlink(missing_ok=True)
        deleted += 1
    await conn.execute("DELETE FROM sky_tile_cache")
    await conn.commit()
    return deleted


async def sync_orphan_files(conn: aiosqlite.Connection) -> int:
    """Delete on-disk files not referenced by any cache row.

    Called on app startup to clean up files left behind by crashes
    mid-write or by manual tampering.
    """
    d = APP_DIR / "sky_tiles"
    if not d.is_dir():
        return 0

    cursor = await conn.execute("SELECT file_path FROM sky_tile_cache")
    known = {str(Path(row["file_path"]).resolve()) for row in await cursor.fetchall()}

    removed = 0
    for entry in d.iterdir():
        if not entry.is_file() or entry.suffix != ".jpg":
            continue
        if not _CELL_FILENAME_RE.match(entry.name):
            continue
        if str(entry.resolve()) not in known:
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
