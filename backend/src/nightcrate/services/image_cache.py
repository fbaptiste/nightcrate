"""Shared safety and budget controls for the rendered-image disk caches."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import aiosqlite

from nightcrate.core import app_config

# Publication, eviction, clearing, reconciliation, and orphan sweeping all
# mutate the same on-disk budget. Rendering deliberately happens outside this
# lock in the two cache services.
lock = asyncio.Lock()
_generation = 0


# These patterns define the files NightCrate owns in the two cache directories.
# Keep them here so clearing and each cache's reconciliation sweep use the same
# allow-list. Temporary publication files wrap an owned JPEG as
# ``.<filename>.tmp`` and are recognized by :func:`is_cache_owned_filename`.
THUMBNAIL_FILENAME_RE = re.compile(
    r"^ra(?P<ra>\d+)_dec(?P<dec>-?\d+)_"
    r"(?P<variant>list|detail|rig_framed|fov_simulator)_"
    r"(?P<width>\d+)x(?P<height>\d+)"
    r"(?:_(?P<fmaj>-?\d+)_(?P<fmin>-?\d+))?"
    r"\.jpg$"
)
LEGACY_THUMBNAIL_FILENAME_RE = re.compile(
    r"^\d+_"
    r"(?:list|detail|rig_framed|fov_simulator)_"
    r"\d+x\d+"
    r"(?:_-?\d+_-?\d+)?"
    r"(?:_c-?\d+_-?\d+)?"
    r"\.jpg$"
)
SKY_TILE_FILENAME_RE = re.compile(
    r"^[A-Za-z0-9_]+_n\d+_p\d+_(narrow|med|wide)_\d+_"
    r"\d+x\d+_-?\d+_-?\d+\.jpg$"
)


def generation() -> int:
    """Return the process-local cache generation used to reject stale renders."""
    return _generation


def advance_generation() -> int:
    """Invalidate renders that started before a cache clear."""
    global _generation
    _generation += 1
    return _generation


def cache_dir(kind: str, *, create: bool = False) -> Path:
    """Return a cache directory using the current ``APP_DIR`` value."""
    if kind == "thumbnail":
        directory = app_config.APP_DIR / "thumbnails"
    elif kind == "sky_tile":
        directory = app_config.APP_DIR / "sky_tiles"
    else:
        raise ValueError(f"Unknown image-cache kind: {kind}")
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


def resolve_path(stored: str, kind: str) -> Path | None:
    """Resolve a stored filename or legacy absolute path inside today's cache.

    Legacy rows may contain POSIX or Windows absolute paths from another app
    data folder. Only their basename is portable. Traversal, nested paths, NUL
    bytes, and symlinks escaping the current cache directory are rejected.
    """
    if not stored or "\x00" in stored:
        return None
    normalized = stored.replace("\\", "/")
    parts = normalized.split("/")
    if any(part == ".." for part in parts):
        return None
    legacy_absolute = normalized.startswith("/") or (
        len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/"
    )
    if "/" in normalized and not legacy_absolute:
        return None
    filename = parts[-1]
    if filename in {"", ".", ".."}:
        return None

    directory = cache_dir(kind)
    candidate = directory / filename
    try:
        root = directory.resolve(strict=False)
        resolved = candidate.resolve(strict=False)
    except OSError:
        return None
    if not resolved.is_relative_to(root):
        return None
    return candidate


def is_cache_owned_filename(filename: str, kind: str) -> bool:
    """Return whether *filename* is a recognized cache JPEG or its temp file."""
    candidate = filename
    if candidate.startswith(".") and candidate.endswith(".tmp"):
        candidate = candidate[1:-4]
    if kind == "thumbnail":
        return bool(
            THUMBNAIL_FILENAME_RE.fullmatch(candidate)
            or LEGACY_THUMBNAIL_FILENAME_RE.fullmatch(candidate)
        )
    if kind == "sky_tile":
        return bool(SKY_TILE_FILENAME_RE.fullmatch(candidate))
    raise ValueError(f"Unknown image-cache kind: {kind}")


async def evict_lru_locked(conn: aiosqlite.Connection, max_bytes: int) -> int:
    """Evict the combined LRU while the caller holds :data:`lock`."""
    cursor = await conn.execute(
        """
        SELECT cache_kind, id, file_path, bytes, last_access_at
        FROM (
            SELECT 'thumbnail' AS cache_kind, id, file_path, bytes, last_access_at
            FROM thumbnail_cache
            UNION ALL
            SELECT 'sky_tile' AS cache_kind, id, file_path, bytes, last_access_at
            FROM sky_tile_cache
        )
        ORDER BY last_access_at ASC, cache_kind ASC, id ASC
        """
    )
    rows = await cursor.fetchall()
    total = sum(int(row["bytes"]) for row in rows)
    evicted = 0
    for row in rows:
        if total <= max_bytes:
            break
        path = resolve_path(str(row["file_path"]), str(row["cache_kind"]))
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # Keep metadata when the corresponding file could not be
                # removed; another entry may still bring the budget down.
                continue
        table = "thumbnail_cache" if row["cache_kind"] == "thumbnail" else "sky_tile_cache"
        await conn.execute(f"DELETE FROM {table} WHERE id = ?", (row["id"],))  # nosec B608
        total -= int(row["bytes"])
        evicted += 1
    await conn.commit()
    return evicted


async def combined_stats(conn: aiosqlite.Connection, *, max_bytes: int) -> dict[str, int]:
    """Return indexed usage for both rendered-image caches."""
    cursor = await conn.execute(
        """
        SELECT COALESCE(SUM(cnt), 0) AS cnt, COALESCE(SUM(total), 0) AS total
        FROM (
            SELECT COUNT(*) AS cnt, COALESCE(SUM(bytes), 0) AS total
            FROM thumbnail_cache
            UNION ALL
            SELECT COUNT(*) AS cnt, COALESCE(SUM(bytes), 0) AS total
            FROM sky_tile_cache
        )
        """
    )
    row = await cursor.fetchone()
    return {
        "total_bytes": int(row["total"]) if row else 0,
        "row_count": int(row["cnt"]) if row else 0,
        "max_bytes": max_bytes,
    }


async def clear_all(conn: aiosqlite.Connection) -> int:
    """Clear both cache tables and files as one generation."""
    async with lock:
        paths: set[Path] = set()
        for kind, table in (("thumbnail", "thumbnail_cache"), ("sky_tile", "sky_tile_cache")):
            cursor = await conn.execute(f"SELECT file_path FROM {table}")  # nosec B608
            for row in await cursor.fetchall():
                if path := resolve_path(str(row["file_path"]), kind):
                    paths.add(path)

            directory = cache_dir(kind)
            if not directory.is_dir():
                continue
            for entry in directory.iterdir():
                if not entry.is_file() or not is_cache_owned_filename(entry.name, kind):
                    continue
                if path := resolve_path(entry.name, kind):
                    paths.add(path)

        deleted = 0
        for path in sorted(paths):
            existed = path.exists()
            path.unlink(missing_ok=True)
            deleted += int(existed)
        await conn.execute("DELETE FROM thumbnail_cache")
        await conn.execute("DELETE FROM sky_tile_cache")
        await conn.commit()
        advance_generation()
        return deleted
