"""Target Planner thumbnail cache.

Serves DSS2 Color JPEG thumbnails for DSOs from an LRU disk cache under
``APP_DIR/thumbnails/``. Misses return a lightweight placeholder and
enqueue a background fetch from CDS Aladin's ``hips2fits``; the frontend
re-requests after a short delay and serves the cached image on the
retry.

Failures record a ``fetch_error`` row so repeated client polls don't
restart fetch storms against CDS. Errors expire after a 1-hour backoff.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import aiosqlite

from nightcrate.core.app_config import APP_DIR
from nightcrate.services.hips_client import (
    HIPS_DSS2_COLOR,
    HIPS_DSS2_RED,
    build_hips2fits_url,
    fetch_hips_image,
)

logger = logging.getLogger("nightcrate.thumbnails")

Variant = Literal["list", "detail"]

# 1×1 transparent PNG — small, valid, renders cleanly as a placeholder
# while the background fetch runs.
_PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154785e63faffff3f0305000602020069b7c3c50000000049454e"
    "44ae426082"
)

_FETCH_ERROR_BACKOFF = timedelta(hours=1)

# Cap how many concurrent background fetches run against CDS so a
# first-time user listing 100 rows doesn't hammer the service.
_MAX_CONCURRENT_FETCHES = 4
_fetch_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)

# Dedupe in-flight fetches keyed on (dso_id, variant). Concurrent polls
# for the same thumbnail wait on the same task rather than enqueuing
# duplicates.
_in_flight: dict[tuple[int, Variant], asyncio.Task] = {}


@dataclass(frozen=True, slots=True)
class ThumbnailDimensions:
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class ThumbnailResult:
    """What ``get_thumbnail`` returns to the API layer."""

    body: bytes
    content_type: str
    # "hit" → 200 with cached image; "placeholder" → 202 with a tiny PNG
    # while a fetch runs; "error" → 204 after the fetch-error backoff.
    status: Literal["hit", "placeholder", "error"]


# ── Variant sizing ───────────────────────────────────────────────────────────

_DIMENSIONS: dict[Variant, ThumbnailDimensions] = {
    "list": ThumbnailDimensions(180, 180),
    "detail": ThumbnailDimensions(600, 600),
}

# Angular extent multipliers / minimums (deg). Converted from the
# DSO's major axis (arcmin).
_EXTENT: dict[Variant, tuple[float, float]] = {
    # (multiplier on maj_axis_deg, minimum_deg)
    "list": (1.5, 0.1),
    "detail": (2.5, 0.5),
}


def compute_fov_deg(variant: Variant, maj_axis_arcmin: float | None) -> float:
    """Return the angular extent to request from hips2fits in degrees."""
    multiplier, minimum = _EXTENT[variant]
    if maj_axis_arcmin is None or maj_axis_arcmin <= 0:
        return minimum
    maj_deg = maj_axis_arcmin / 60.0
    return max(maj_deg * multiplier, minimum)


def dimensions_for(variant: Variant) -> ThumbnailDimensions:
    return _DIMENSIONS[variant]


# ── Filesystem helpers ───────────────────────────────────────────────────────


def thumb_dir() -> Path:
    """User-writable directory under APP_DIR. Created on first access."""
    d = APP_DIR / "thumbnails"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _thumb_path(dso_id: int, variant: Variant, width: int, height: int) -> Path:
    return thumb_dir() / f"{dso_id}_{variant}_{width}x{height}.jpg"


# ── Cache lookup and insertion ───────────────────────────────────────────────


async def _lookup_cache_row(
    conn: aiosqlite.Connection,
    dso_id: int,
    variant: Variant,
    width: int,
    height: int,
) -> aiosqlite.Row | None:
    cursor = await conn.execute(
        """
        SELECT id, file_path, source, bytes, fetched_at, fetch_error
        FROM thumbnail_cache
        WHERE dso_id = ? AND variant = ? AND width = ? AND height = ?
        """,
        (dso_id, variant, width, height),
    )
    return await cursor.fetchone()


async def _touch_last_access(conn: aiosqlite.Connection, row_id: int) -> None:
    await conn.execute(
        "UPDATE thumbnail_cache SET last_access_at = datetime('now') WHERE id = ?",
        (row_id,),
    )
    await conn.commit()


async def _delete_cache_row(conn: aiosqlite.Connection, row_id: int) -> None:
    await conn.execute("DELETE FROM thumbnail_cache WHERE id = ?", (row_id,))
    await conn.commit()


async def _evict_lru(conn: aiosqlite.Connection, max_bytes: int) -> int:
    """Evict least-recently-used rows until total size ≤ ``max_bytes``.

    Deletes the file on disk before the metadata row so an orphan file
    can't outlast its metadata. Returns the count of rows evicted.
    """
    cursor = await conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM thumbnail_cache")
    total_row = await cursor.fetchone()
    total = int(total_row[0]) if total_row else 0
    if total <= max_bytes:
        return 0

    evicted = 0
    while total > max_bytes:
        cursor = await conn.execute(
            "SELECT id, file_path, bytes FROM thumbnail_cache ORDER BY last_access_at ASC LIMIT 1"
        )
        oldest = await cursor.fetchone()
        if oldest is None:
            break
        path = Path(oldest["file_path"])
        path.unlink(missing_ok=True)
        await conn.execute("DELETE FROM thumbnail_cache WHERE id = ?", (oldest["id"],))
        total -= int(oldest["bytes"])
        evicted += 1
    await conn.commit()
    return evicted


async def _insert_cache_row(
    conn: aiosqlite.Connection,
    *,
    dso_id: int,
    variant: Variant,
    width: int,
    height: int,
    file_path: str,
    source: str,
    bytes_size: int,
    fetch_error: str | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO thumbnail_cache (
            dso_id, variant, width, height, file_path, source, bytes, fetch_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (dso_id, variant, width, height, file_path, source, bytes_size, fetch_error),
    )
    await conn.commit()


# ── Background fetch ─────────────────────────────────────────────────────────


async def _fetch_and_store(
    conn: aiosqlite.Connection,
    *,
    dso_id: int,
    variant: Variant,
    ra_deg: float,
    dec_deg: float,
    maj_axis_arcmin: float | None,
    max_cache_bytes: int,
) -> None:
    """Fetch DSS2 Color (with DSS2 red fallback) and persist the result.

    Writes the JPEG to disk before inserting the DB row so a crash
    between the two steps leaves an orphan file — rerunning the fetch
    overwrites it cleanly. A persistent-failure branch inserts a
    ``fetch_error`` sentinel row so subsequent polls short-circuit.
    """
    dim = dimensions_for(variant)
    fov = compute_fov_deg(variant, maj_axis_arcmin)

    color_url = build_hips2fits_url(
        HIPS_DSS2_COLOR,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        width=dim.width,
        height=dim.height,
        fov_deg=fov,
    )
    red_url = build_hips2fits_url(
        HIPS_DSS2_RED,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        width=dim.width,
        height=dim.height,
        fov_deg=fov,
    )

    async with _fetch_semaphore:
        body: bytes | None = None
        source: str | None = None
        try:
            body = await fetch_hips_image(color_url)
            source = "dss2_color"
        except Exception as color_exc:  # noqa: BLE001 — fallback on any failure
            logger.info(
                "[thumbnails] dso=%s color fetch failed (%s); trying DSS2 red",
                dso_id,
                color_exc,
            )
            try:
                body = await fetch_hips_image(red_url)
                source = "dss2_red"
            except Exception as red_exc:  # noqa: BLE001 — record failure, backoff
                logger.warning(
                    "[thumbnails] dso=%s both color and red fetches failed: %s / %s",
                    dso_id,
                    color_exc,
                    red_exc,
                )
                await _insert_cache_row(
                    conn,
                    dso_id=dso_id,
                    variant=variant,
                    width=dim.width,
                    height=dim.height,
                    file_path=str(_thumb_path(dso_id, variant, dim.width, dim.height)),
                    source="placeholder",
                    bytes_size=0,
                    fetch_error=f"color: {color_exc}; red: {red_exc}",
                )
                return

    if body is None or source is None:
        # Belt-and-braces — the try/except above covers both branches.
        return

    path = _thumb_path(dso_id, variant, dim.width, dim.height)
    path.write_bytes(body)
    await _insert_cache_row(
        conn,
        dso_id=dso_id,
        variant=variant,
        width=dim.width,
        height=dim.height,
        file_path=str(path),
        source=source,
        bytes_size=len(body),
    )
    await _evict_lru(conn, max_cache_bytes)


async def _background_wrapper(
    conn_factory,
    *,
    dso_id: int,
    variant: Variant,
    ra_deg: float,
    dec_deg: float,
    maj_axis_arcmin: float | None,
    max_cache_bytes: int,
) -> None:
    """Run a fetch against a fresh aiosqlite connection.

    FastAPI's ``BackgroundTasks`` runs after the response — the original
    request's connection context is already closed, so we open our own.
    """
    try:
        async with conn_factory() as conn:
            conn.row_factory = aiosqlite.Row
            await _fetch_and_store(
                conn,
                dso_id=dso_id,
                variant=variant,
                ra_deg=ra_deg,
                dec_deg=dec_deg,
                maj_axis_arcmin=maj_axis_arcmin,
                max_cache_bytes=max_cache_bytes,
            )
    except Exception:  # noqa: BLE001 — background task mustn't crash the server
        logger.exception("[thumbnails] background fetch crashed for dso=%s", dso_id)
    finally:
        _in_flight.pop((dso_id, variant), None)


# ── Public API ───────────────────────────────────────────────────────────────


async def get_thumbnail(
    conn: aiosqlite.Connection,
    *,
    dso_id: int,
    variant: Variant,
    ra_deg: float,
    dec_deg: float,
    maj_axis_arcmin: float | None,
    max_cache_bytes: int,
    conn_factory,
) -> ThumbnailResult:
    """Serve a thumbnail by variant, enqueuing a fetch on cache miss.

    ``conn`` is the current request's aiosqlite connection (used for the
    lookup + touch). ``conn_factory`` is an async context-manager
    factory (typically ``nightcrate.db.session.get_db``) used by the
    background task to open its own connection after the response is
    sent.
    """
    dim = dimensions_for(variant)
    row = await _lookup_cache_row(conn, dso_id, variant, dim.width, dim.height)

    if row is not None and row["fetch_error"] is None and row["source"] != "placeholder":
        # Cache hit. Serve bytes from disk, refresh LRU timestamp.
        try:
            body = Path(row["file_path"]).read_bytes()
            await _touch_last_access(conn, row["id"])
            return ThumbnailResult(body=body, content_type="image/jpeg", status="hit")
        except FileNotFoundError:
            # Metadata orphan — the file was deleted out-of-band. Drop the
            # row and fall through to a fresh fetch.
            logger.warning(
                "[thumbnails] orphan metadata for dso=%s variant=%s — refetching",
                dso_id,
                variant,
            )
            await _delete_cache_row(conn, row["id"])
            row = None

    # Permanent-failure short-circuit during the backoff window.
    if row is not None and row["fetch_error"] is not None:
        fetched_at = datetime.fromisoformat(row["fetched_at"]).replace(tzinfo=UTC)
        if datetime.now(UTC) - fetched_at < _FETCH_ERROR_BACKOFF:
            return ThumbnailResult(body=b"", content_type="image/png", status="error")
        # Backoff expired — drop the row and try again.
        await _delete_cache_row(conn, row["id"])

    # Miss: schedule the background fetch (dedup via in-flight map).
    key = (dso_id, variant)
    if key not in _in_flight:
        task = asyncio.create_task(
            _background_wrapper(
                conn_factory,
                dso_id=dso_id,
                variant=variant,
                ra_deg=ra_deg,
                dec_deg=dec_deg,
                maj_axis_arcmin=maj_axis_arcmin,
                max_cache_bytes=max_cache_bytes,
            )
        )
        _in_flight[key] = task

    return ThumbnailResult(body=_PLACEHOLDER_PNG, content_type="image/png", status="placeholder")


async def clear_cache(conn: aiosqlite.Connection) -> int:
    """Wipe every cached thumbnail (metadata + files). Returns files deleted."""
    cursor = await conn.execute("SELECT file_path FROM thumbnail_cache")
    rows = await cursor.fetchall()
    deleted = 0
    for row in rows:
        Path(row["file_path"]).unlink(missing_ok=True)
        deleted += 1
    await conn.execute("DELETE FROM thumbnail_cache")
    await conn.commit()
    return deleted


async def cache_stats(conn: aiosqlite.Connection, *, max_bytes: int) -> dict[str, int]:
    """Return cache-usage metrics for the Settings page."""
    cursor = await conn.execute(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(bytes), 0) AS total FROM thumbnail_cache"
    )
    row = await cursor.fetchone()
    return {
        "total_bytes": int(row["total"]) if row else 0,
        "row_count": int(row["cnt"]) if row else 0,
        "max_bytes": max_bytes,
    }
