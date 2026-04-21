"""Target Planner thumbnail cache.

Serves DSS2 Color JPEG thumbnails for DSOs from an LRU disk cache under
``APP_DIR/thumbnails/``. Misses return a lightweight placeholder and
enqueue a background fetch from CDS Aladin's ``hips2fits``; the frontend
re-requests after a short delay and serves the cached image on the
retry.

Three variants share the cache:

    ``list``          180×180, object-framed
    ``detail``        800×800, object-framed, wide extent
    ``rig_framed``    180×180, fetched at the rig's FOV major axis; the
                      browser crops to the rig's aspect via ``object-fit``

(The old ``fov_simulator`` variant was retired in v0.18.0 — the
simulator pulls from the DSO-agnostic ``sky_tile_cache`` now.)

Failures record a ``fetch_error`` row so repeated client polls don't
restart fetch storms against CDS. Errors expire after a 1-hour backoff.
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
    build_hips2fits_url,
    fetch_hips_image,
)

logger = logging.getLogger("nightcrate.thumbnails")

Variant = Literal["list", "detail", "rig_framed"]

# ``rig_framed`` requires fov_major_deg + fov_minor_deg query params;
# the other variants reject those params as unused input.
_RIG_DEPENDENT: frozenset[Variant] = frozenset({"rig_framed"})

# 1×1 transparent PNG — small, valid, renders cleanly as a placeholder
# while the background fetch runs.
_PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154785e63faffff3f0305000602020069b7c3c50000000049454e"
    "44ae426082"
)

_FETCH_ERROR_BACKOFF = timedelta(hours=1)

# Cap how many concurrent background fetches run against CDS so a
# first-time user listing 100 rows doesn't hammer the service. 8
# matches the sky-tile cache's slot count + the browser's
# per-origin connection limit — the backend stops being the
# bottleneck below what the frontend already fires in parallel.
_MAX_CONCURRENT_FETCHES = 8
_fetch_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)


# ── Dataclasses ──────────────────────────────────────────────────────────────


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


@dataclass(frozen=True, slots=True)
class ThumbnailKey:
    """Composite cache key — dso + variant + dimensions + rig FOV.

    FOV values are stored / compared as (deg × 1000) integers so two
    rigs that round to the same 0.001° share a cache entry. NULL
    fields use ``-1`` under COALESCE in the DB so a list/detail entry
    doesn't collide with a rig-framed one at the same dso_id.

    ``center_ra_deg_x1000`` / ``center_dec_deg_x1000`` are retained
    on the cache schema (migration 0019) but unused now that the
    old panned ``fov_simulator`` variant is gone; they're always
    ``None`` here.
    """

    dso_id: int
    variant: Variant
    width: int
    height: int
    fov_major_deg_x1000: int | None = None
    fov_minor_deg_x1000: int | None = None
    center_ra_deg_x1000: int | None = None
    center_dec_deg_x1000: int | None = None


# Dedupe in-flight fetches keyed on the full ThumbnailKey. Concurrent
# polls for the same thumbnail wait on the same task rather than
# enqueuing duplicates.
_in_flight: dict[ThumbnailKey, asyncio.Task] = {}


# ── Variant sizing ───────────────────────────────────────────────────────────

_DIMENSIONS: dict[Variant, ThumbnailDimensions] = {
    "list": ThumbnailDimensions(180, 180),
    "detail": ThumbnailDimensions(800, 800),
    "rig_framed": ThumbnailDimensions(180, 180),
}


def dimensions_for(variant: Variant) -> ThumbnailDimensions:
    return _DIMENSIONS[variant]


def compute_angular_extent_deg(
    variant: Variant,
    *,
    dso_maj_axis_arcmin: float | None,
    fov_major_deg: float | None = None,
    fov_minor_deg: float | None = None,
) -> float:
    """Angular extent (deg) to request from ``hips2fits`` for *variant*.

    ``list`` and ``detail`` scale with the DSO's major axis;
    ``rig_framed`` matches the rig's major-axis FOV exactly. Small /
    missing DSO sizes fall back to a minimum so the image is always
    readable.
    """
    # ``fov_minor_deg`` is retained in the signature for API
    # compatibility but unused now that the panned ``fov_simulator``
    # variant is gone.
    _ = fov_minor_deg
    if variant == "list":
        maj_deg = (dso_maj_axis_arcmin or 5.0) / 60.0
        return max(maj_deg * 1.5, 0.1)
    if variant == "detail":
        maj_deg = (dso_maj_axis_arcmin or 10.0) / 60.0
        return max(maj_deg * 3.5, 1.0)
    if variant == "rig_framed":
        if fov_major_deg is None or fov_major_deg <= 0:
            raise ValueError("rig_framed variant requires a positive fov_major_deg")
        return fov_major_deg
    raise ValueError(f"Unknown variant: {variant}")


def _to_x1000(value: float | None) -> int | None:
    """Round deg float → int × 1000. ``None`` passes through."""
    if value is None:
        return None
    return round(value * 1000)


def make_key(
    dso_id: int,
    variant: Variant,
    *,
    fov_major_deg: float | None = None,
    fov_minor_deg: float | None = None,
    center_ra_deg: float | None = None,
    center_dec_deg: float | None = None,
) -> ThumbnailKey:
    """Build the cache key — rig-dependent variants require FOV params.

    ``center_ra_deg`` / ``center_dec_deg`` are retained for API
    compatibility with the old panned ``fov_simulator`` code path and
    are silently discarded — they never make it into the key now.
    """
    _ = center_ra_deg, center_dec_deg  # retired v0.18.0
    if variant in _RIG_DEPENDENT and (fov_major_deg is None or fov_minor_deg is None):
        raise ValueError(f"variant {variant!r} requires fov_major_deg + fov_minor_deg")
    dim = dimensions_for(variant)
    # Rig-independent variants deliberately ignore passed-in FOV values so
    # a stray param can never fork the cache.
    if variant not in _RIG_DEPENDENT:
        fov_major_deg = None
        fov_minor_deg = None
    return ThumbnailKey(
        dso_id=dso_id,
        variant=variant,
        width=dim.width,
        height=dim.height,
        fov_major_deg_x1000=_to_x1000(fov_major_deg),
        fov_minor_deg_x1000=_to_x1000(fov_minor_deg),
    )


# ── Filesystem helpers ───────────────────────────────────────────────────────


def thumb_dir() -> Path:
    """User-writable directory under APP_DIR. Created on first access."""
    d = APP_DIR / "thumbnails"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _thumb_path(key: ThumbnailKey) -> Path:
    """Disk location for *key*. Suffix carries the rounded FOV on
    rig-dependent variants (so two rigs don't clobber each other's
    JPEGs).
    """
    base = f"{key.dso_id}_{key.variant}_{key.width}x{key.height}"
    if key.fov_major_deg_x1000 is not None and key.fov_minor_deg_x1000 is not None:
        base += f"_{key.fov_major_deg_x1000}_{key.fov_minor_deg_x1000}"
    return thumb_dir() / f"{base}.jpg"


# File-name pattern — must parse any stem produced by ``_thumb_path``.
# Groups: dso_id, variant, width, height, fov_major_x1000?, fov_minor_x1000?,
# center_ra_x1000?, center_dec_x1000?
_THUMB_FILENAME_RE = re.compile(
    r"^(?P<dso_id>\d+)_"
    # ``fov_simulator`` retired in v0.18.0 but kept in the regex so
    # orphan sweeps still parse + delete its leftover on-disk JPEGs.
    r"(?P<variant>list|detail|rig_framed|fov_simulator)_"
    r"(?P<width>\d+)x(?P<height>\d+)"
    r"(?:_(?P<fmaj>-?\d+)_(?P<fmin>-?\d+))?"
    r"(?:_c(?P<cra>-?\d+)_(?P<cdec>-?\d+))?"
    r"\.jpg$"
)


# ── Cache lookup and insertion ───────────────────────────────────────────────


def _coalesce_fov(v: int | None) -> int:
    """Match the DB's ``COALESCE(.., -1)`` wrapping for FOV columns."""
    return v if v is not None else -1


def _coalesce_center(v: int | None) -> int:
    """Match the DB's ``COALESCE(.., -999999)`` wrapping for sky-centre columns.

    Uses a distinct sentinel from the FOV columns so a legitimate 0.0
    centre (valid RA on the celestial equator) can't collide with the
    NULL sentinel.
    """
    return v if v is not None else -999999


async def _lookup_cache_row(conn: aiosqlite.Connection, key: ThumbnailKey) -> aiosqlite.Row | None:
    cursor = await conn.execute(
        """
        SELECT id, file_path, source, bytes, fetched_at, fetch_error
        FROM thumbnail_cache
        WHERE dso_id = ? AND variant = ? AND width = ? AND height = ?
          AND COALESCE(fov_major_deg_x1000, -1) = ?
          AND COALESCE(fov_minor_deg_x1000, -1) = ?
          AND COALESCE(center_ra_deg_x1000, -999999) = ?
          AND COALESCE(center_dec_deg_x1000, -999999) = ?
        """,
        (
            key.dso_id,
            key.variant,
            key.width,
            key.height,
            _coalesce_fov(key.fov_major_deg_x1000),
            _coalesce_fov(key.fov_minor_deg_x1000),
            _coalesce_center(key.center_ra_deg_x1000),
            _coalesce_center(key.center_dec_deg_x1000),
        ),
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
    key: ThumbnailKey,
    *,
    file_path: str,
    source: str,
    bytes_size: int,
    fetch_error: str | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO thumbnail_cache (
            dso_id, variant, width, height,
            fov_major_deg_x1000, fov_minor_deg_x1000,
            center_ra_deg_x1000, center_dec_deg_x1000,
            file_path, source, bytes, fetch_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key.dso_id,
            key.variant,
            key.width,
            key.height,
            key.fov_major_deg_x1000,
            key.fov_minor_deg_x1000,
            key.center_ra_deg_x1000,
            key.center_dec_deg_x1000,
            file_path,
            source,
            bytes_size,
            fetch_error,
        ),
    )
    await conn.commit()


# ── Background fetch ─────────────────────────────────────────────────────────


async def _fetch_and_store(
    conn: aiosqlite.Connection,
    key: ThumbnailKey,
    *,
    ra_deg: float,
    dec_deg: float,
    extent_deg: float,
    max_cache_bytes: int,
) -> None:
    """Fetch DSS2 Color (with DSS2 red fallback) and persist the result.

    Writes the JPEG to disk before inserting the DB row so a crash
    between the two steps leaves an orphan file — rerunning the fetch
    overwrites it cleanly. A persistent-failure branch inserts a
    ``fetch_error`` sentinel row so subsequent polls short-circuit.
    """
    color_url = build_hips2fits_url(
        HIPS_DSS2_COLOR,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        width=key.width,
        height=key.height,
        fov_deg=extent_deg,
    )
    red_url = build_hips2fits_url(
        HIPS_DSS2_RED,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        width=key.width,
        height=key.height,
        fov_deg=extent_deg,
    )

    async with _fetch_semaphore:
        try:
            body = await fetch_hips_image(color_url)
            source = "dss2_color"
        except Exception as color_exc:  # noqa: BLE001 — fallback on any failure
            logger.info(
                "[thumbnails] dso=%s color fetch failed (%s); trying DSS2 red",
                key.dso_id,
                color_exc,
            )
            try:
                body = await fetch_hips_image(red_url)
                source = "dss2_red"
            except Exception as red_exc:  # noqa: BLE001 — record failure, backoff
                logger.warning(
                    "[thumbnails] dso=%s both color and red fetches failed: %s / %s",
                    key.dso_id,
                    color_exc,
                    red_exc,
                )
                await _insert_cache_row(
                    conn,
                    key,
                    file_path=str(_thumb_path(key)),
                    source="placeholder",
                    bytes_size=0,
                    fetch_error=f"color: {color_exc}; red: {red_exc}",
                )
                return

    path = _thumb_path(key)
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
    key: ThumbnailKey,
    *,
    ra_deg: float,
    dec_deg: float,
    extent_deg: float,
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
                key,
                ra_deg=ra_deg,
                dec_deg=dec_deg,
                extent_deg=extent_deg,
                max_cache_bytes=max_cache_bytes,
            )
    except Exception:  # noqa: BLE001 — background task mustn't crash the server
        logger.exception("[thumbnails] background fetch crashed for dso=%s", key.dso_id)
    finally:
        _in_flight.pop(key, None)


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
    fov_major_deg: float | None = None,
    fov_minor_deg: float | None = None,
    wait_timeout_s: float = 0.0,
) -> ThumbnailResult:
    """Serve a thumbnail by variant, enqueuing a fetch on cache miss.

    ``conn`` is the current request's aiosqlite connection (used for the
    lookup + touch). ``conn_factory`` is an async context-manager
    factory (typically ``nightcrate.db.session.get_db``) used by the
    background task to open its own connection after the response is
    sent. ``fov_major_deg`` / ``fov_minor_deg`` are required for the
    ``rig_framed`` variant and rejected with a ``ValueError`` when
    missing.

    ``wait_timeout_s`` > 0 turns the endpoint into a long-poll: on a
    cache miss the request holds open, awaiting the background fetch
    task, and returns the real image in the same HTTP round trip. If
    the fetch doesn't complete within the window the call falls through
    to the placeholder path so the client can retry. Defaults to 0 for
    backwards compatibility with pollers.
    """
    key = make_key(
        dso_id,
        variant,
        fov_major_deg=fov_major_deg,
        fov_minor_deg=fov_minor_deg,
    )
    effective_ra = ra_deg
    effective_dec = dec_deg
    logger.debug(
        "[thumb] req dso=%d variant=%s fov=(%s,%s) -> sky=(%.5f,%.5f)",
        dso_id,
        variant,
        f"{fov_major_deg:.4f}" if fov_major_deg is not None else "—",
        f"{fov_minor_deg:.4f}" if fov_minor_deg is not None else "—",
        effective_ra,
        effective_dec,
    )
    row = await _lookup_cache_row(conn, key)

    if row is not None and row["fetch_error"] is None and row["source"] != "placeholder":
        # Cache hit. Serve bytes from disk, refresh LRU timestamp.
        try:
            body = Path(row["file_path"]).read_bytes()
            await _touch_last_access(conn, row["id"])
            logger.debug("[thumb] hit dso=%d variant=%s bytes=%d", dso_id, variant, len(body))
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
    task = _in_flight.get(key)
    if task is None:
        extent_deg = compute_angular_extent_deg(
            variant,
            dso_maj_axis_arcmin=maj_axis_arcmin,
            fov_major_deg=fov_major_deg,
            fov_minor_deg=fov_minor_deg,
        )
        logger.debug(
            "[thumb] miss dso=%d variant=%s extent=%.4f° — enqueueing fetch",
            dso_id,
            variant,
            extent_deg,
        )
        task = asyncio.create_task(
            _background_wrapper(
                conn_factory,
                key,
                ra_deg=effective_ra,
                dec_deg=effective_dec,
                extent_deg=extent_deg,
                max_cache_bytes=max_cache_bytes,
            )
        )
        _in_flight[key] = task
    else:
        logger.debug(
            "[thumb] miss dso=%d variant=%s — fetch already in flight",
            dso_id,
            variant,
        )

    # Long-poll path: wait up to ``wait_timeout_s`` for the background
    # fetch to land the real image, then re-read the cache row and
    # serve it in the same HTTP round trip. ``asyncio.shield`` is
    # required — if the browser disconnects while we're waiting the
    # FastAPI handler gets cancelled, and without the shield that
    # cancellation would propagate into the CDS fetch and abort a
    # half-completed download. With the shield we just exit the wait,
    # leaving the background task to finish on its own.
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
                    logger.debug(
                        "[thumb] long-poll hit dso=%d variant=%s bytes=%d",
                        dso_id,
                        variant,
                        len(body),
                    )
                    return ThumbnailResult(body=body, content_type="image/jpeg", status="hit")
                except FileNotFoundError:
                    # Extremely unlikely — fetch just wrote the file —
                    # but if it happens, fall through to placeholder so
                    # the client retries and hits the orphan-metadata
                    # branch on the next pass.
                    pass
            if row is not None and row["fetch_error"] is not None:
                return ThumbnailResult(body=b"", content_type="image/png", status="error")

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


async def sync_orphan_files(conn: aiosqlite.Connection) -> int:
    """Delete on-disk thumbnail files not referenced by ``thumbnail_cache``.

    Called once on app startup (after migrations run) to clean up the
    stale Pass A ``detail`` JPEGs left behind when migration 0018 wiped
    the table. Also guards against manual tampering on subsequent boots.

    Returns the count of files removed.
    """
    d = APP_DIR / "thumbnails"
    if not d.is_dir():
        return 0

    cursor = await conn.execute("SELECT file_path FROM thumbnail_cache")
    known = {str(Path(row["file_path"]).resolve()) for row in await cursor.fetchall()}

    removed = 0
    for entry in d.iterdir():
        if not entry.is_file() or entry.suffix != ".jpg":
            continue
        if not _THUMB_FILENAME_RE.match(entry.name):
            continue
        if str(entry.resolve()) not in known:
            entry.unlink(missing_ok=True)
            removed += 1
    if removed:
        logger.info("[thumbnails] startup sweep removed %d orphan file(s)", removed)
    return removed


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
