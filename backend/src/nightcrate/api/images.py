"""Unified image API endpoints — dispatches by file type (FITS, XISF, PNG/JPEG/TIFF)."""

import asyncio
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import BinaryIO, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from nightcrate.db.session import get_db
from nightcrate.services import archive_io, fits_io, pxiproject_io, standard_io, xisf_io
from nightcrate.services.fits_header_map import (
    FITS_KEYWORD_ALIASES,
    extract_metadata,
)
from nightcrate.services.imaging import (
    LUM_B,
    LUM_G,
    LUM_R,
    ImageStats,
    StretchParams,
    compute_image_stats,
    is_color_image,
    render_image_png,
    resolve_auto_stretch,
)

router = APIRouter(prefix="/api/images", tags=["Image Viewer"])

FITS_EXTENSIONS = {".fits", ".fit", ".fts"}
XISF_EXTENSIONS = {".xisf"}
STANDARD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
ALL_EXTENSIONS = FITS_EXTENSIONS | XISF_EXTENSIONS | STANDARD_EXTENSIONS

# ---------------------------------------------------------------------------
# In-memory image data cache — avoids redundant file loads when multiple
# endpoints hit the same file within a short window (e.g. opening a file).
# ---------------------------------------------------------------------------

_CACHE_MAX_ENTRIES = 5
_CACHE_TTL_SECONDS = 120

_cache: dict[tuple, tuple[np.ndarray, float]] = {}
_stats_cache: dict[tuple, tuple[ImageStats, float]] = {}
_key_locks: dict[tuple, threading.Lock] = {}
_cache_lock = threading.Lock()


def _cached_compute(key: tuple, store: dict, compute_fn):
    """Get a value from a TTL cache, or compute it exactly once.

    Uses per-key locking so concurrent requests for the same key share a
    single computation — the first thread computes and caches, others wait.
    """
    with _cache_lock:
        entry = store.get(key)
        if entry is not None:
            val, ts = entry
            if time.monotonic() - ts < _CACHE_TTL_SECONDS:
                return val
            del store[key]
        if key not in _key_locks:
            _key_locks[key] = threading.Lock()
        lock = _key_locks[key]

    with lock:
        with _cache_lock:
            entry = store.get(key)
            if entry is not None:
                val, ts = entry
                if time.monotonic() - ts < _CACHE_TTL_SECONDS:
                    return val

        val = compute_fn()

        with _cache_lock:
            while len(store) >= _CACHE_MAX_ENTRIES:
                oldest = next(iter(store))
                del store[oldest]
                _key_locks.pop(oldest, None)
            store[key] = (val, time.monotonic())

    return val


def _get_cached_image_data(
    p: Path | BinaryIO,
    ft: str,
    idx: int,
    hdu: int,
    cache_key: tuple | None = None,
) -> np.ndarray:
    """Load image data with TTL cache and per-key locking.

    cache_key is used for archive entries (BytesIO) so concurrent requests
    share cached data instead of loading independently.
    """
    if isinstance(p, Path):
        key = (str(p), p.stat().st_mtime, idx, hdu)
    elif cache_key is not None:
        key = (*cache_key, hdu)
    else:
        return _load_image_data(p, ft, idx, hdu)
    return _cached_compute(key, _cache, lambda: _load_image_data(p, ft, idx, hdu))


def _get_or_compute_stats(
    data: np.ndarray,
    p: Path | BinaryIO,
    idx: int,
    hdu: int,
    cache_key: tuple | None = None,
) -> ImageStats:
    """Return stats from cache or compute once with per-key locking."""
    if isinstance(p, Path):
        key = (str(p), p.stat().st_mtime, idx, hdu)
    elif cache_key is not None:
        key = (*cache_key, hdu)
    else:
        return compute_image_stats(data)
    return _cached_compute(key, _stats_cache, lambda: compute_image_stats(data))


STRUCTURAL_KEYWORDS = fits_io.STRUCTURAL_KEYWORDS


def _file_type(p: Path) -> str:
    """Return 'fits', 'xisf', 'float_tiff', or 'standard' based on extension and content."""
    ext = p.suffix.lower()
    if ext in FITS_EXTENSIONS:
        return "fits"
    if ext in XISF_EXTENSIONS:
        return "xisf"
    if ext in STANDARD_EXTENSIONS:
        if ext in (".tif", ".tiff") and standard_io.is_float_tiff(p):
            return "float_tiff"
        return "standard"
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type: {ext}. Supported: {', '.join(sorted(ALL_EXTENSIONS))}",
    )


def _file_type_from_ext(entry_name: str) -> str:
    """Determine file type from extension only (no disk check)."""
    suffix = Path(entry_name).suffix.lower()
    if suffix in FITS_EXTENSIONS:
        return "fits"
    if suffix in XISF_EXTENSIONS:
        return "xisf"
    if suffix in STANDARD_EXTENSIONS:
        if suffix in {".tif", ".tiff"}:
            return "tiff_unknown"
        return "standard"
    raise HTTPException(status_code=422, detail=f"Unsupported format: {entry_name}")


def _detect_tiff_type_from_buf(buf: BinaryIO) -> str:
    import tifffile

    try:
        with tifffile.TiffFile(buf) as tif:
            is_float = tif.pages[0].dtype.kind == "f"
        buf.seek(0)
        return "float_tiff" if is_float else "standard"
    except Exception:
        buf.seek(0)
        return "standard"


def _resolve_path(path: str) -> tuple[Path | BinaryIO, str, int, tuple | None]:
    """Validate and resolve a file path.

    Returns (resolved_path, file_type, image_index, cache_key).
    image_index is only meaningful for pxiproject virtual paths; 0 otherwise.
    cache_key is set for archive entries so they can share the data/stats caches
    (and per-key locks) that prevent redundant computation and concurrent GPU access.
    For regular Path files, cache_key is None — those use path + mtime directly.
    """
    if "::" in path:
        left, right = path.rsplit("::", 1)
        left_path = Path(left).resolve()

        # pxiproject: right side is an integer index
        try:
            idx = int(right)
            if not left_path.is_dir():
                raise HTTPException(status_code=404, detail=f"Project not found: {left_path}")
            return left_path, "pxiproject", idx, None
        except ValueError:
            pass

        # Archive handling
        if archive_io.is_archive(left_path):
            if not left_path.is_file():
                raise HTTPException(status_code=404, detail=f"Archive not found: {left}")
            try:
                buf = archive_io.extract_entry(left_path, right)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail=f"Entry not found: {right}")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            ft = _file_type_from_ext(right)
            if ft == "tiff_unknown":
                ft = _detect_tiff_type_from_buf(buf)
            # Cache key uses archive path + mtime + entry so concurrent
            # requests for the same entry share cached data and locks.
            cache_key = (str(left_path), left_path.stat().st_mtime, right)
            return buf, ft, 0, cache_key

        raise HTTPException(status_code=400, detail=f"Invalid virtual path: {path}")

    p = Path(path)
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be absolute")
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    return p, _file_type(p), 0, None


def _load_image_data(p: Path | BinaryIO, ft: str, idx: int, hdu: int):
    """Load normalized image data for any supported file type."""
    if ft == "pxiproject":
        return pxiproject_io.load_image_data(p, idx)
    if ft == "fits":
        return fits_io.load_image_data(p, hdu)
    if ft == "float_tiff":
        return standard_io.load_image_data(p)
    if ft == "standard":
        return standard_io.load_image_as_array(p)
    return xisf_io.load_image_data(p, hdu)


@router.get("/extensions")
async def get_extensions(
    path: str = Query(..., description="Absolute path to image file"),
) -> list[dict]:
    """List extensions/layers in the file, with stretch capability flag."""
    p, ft, idx, _ck = _resolve_path(path)
    stretch = ft in ("fits", "xisf", "float_tiff", "pxiproject")
    try:
        if ft == "pxiproject":
            exts = pxiproject_io.list_extensions(p, idx)
        elif ft == "fits":
            exts = fits_io.list_extensions(p)
        elif ft == "xisf":
            exts = xisf_io.list_extensions(p)
        else:
            exts = standard_io.list_extensions(p)
        for ext in exts:
            ext["supports_stretch"] = stretch
        return exts
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/header")
async def get_header(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
) -> list[dict]:
    """Return metadata cards for the specified extension."""
    p, ft, idx, _ck = _resolve_path(path)
    try:
        if ft == "pxiproject":
            return pxiproject_io.read_header(p, idx)
        if ft == "fits":
            return fits_io.read_header(p, hdu)
        if ft == "xisf":
            return xisf_io.read_header(p, hdu)
        return standard_io.read_header(p)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


# ── Header editing ──────────────────────────────────────────────────────────


class HeaderOperation(BaseModel):
    op: Literal["update", "add", "delete"]
    key: str
    value: str | None = None
    comment: str | None = None


class HeaderEditRequest(BaseModel):
    path: str
    hdu: int = 0
    operations: list[HeaderOperation]


@router.patch("/header")
async def edit_header(request: HeaderEditRequest) -> list[dict]:
    """Apply edit operations to a FITS header and return the updated cards."""
    if "::" in request.path:
        raise HTTPException(
            status_code=400,
            detail="Header editing is not supported for archive or project virtual paths",
        )

    p = Path(request.path)
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be absolute")
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.path}")
    if p.suffix.lower() not in FITS_EXTENSIONS:
        raise HTTPException(
            status_code=422, detail="Header editing is only supported for FITS files"
        )

    ops = [op.model_dump() for op in request.operations]
    try:
        return await asyncio.to_thread(fits_io.update_header, p, request.hdu, ops)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


@router.get("/metadata")
async def get_metadata(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
) -> dict:
    """Return canonical metadata and unrecognized keywords for a file."""
    p, ft, idx, _ck = _resolve_path(path)
    try:
        if ft == "pxiproject":
            cards = pxiproject_io.read_header(p, idx)
        elif ft == "fits":
            cards = fits_io.read_header(p, hdu)
        elif ft == "xisf":
            cards = xisf_io.read_header(p, hdu)
        else:
            cards = standard_io.read_header(p)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal processing error") from exc

    # Build a raw header dict from cards (first occurrence wins for dupes)
    raw_header: dict[str, str] = {}
    for card in cards:
        if card["key"] and card["key"] not in raw_header:
            raw_header[card["key"]] = card["value"]

    canonical = extract_metadata(raw_header)

    recognized = set(FITS_KEYWORD_ALIASES.keys())
    unrecognized = [
        k
        for k in raw_header
        if k.upper() not in recognized
        and k.upper() not in STRUCTURAL_KEYWORDS
        and not k.upper().startswith("NAXIS")
    ]

    return {
        "canonical": canonical,
        "unrecognized_keywords": unrecognized,
    }


def _compute_stats(
    p: Path | BinaryIO, ft: str, idx: int, hdu: int, cache_key: tuple | None = None
) -> dict:
    """Load image and compute stats (runs in thread pool). Uses stats cache."""
    data = _get_cached_image_data(p, ft, idx, hdu, cache_key=cache_key)
    return asdict(_get_or_compute_stats(data, p, idx, hdu, cache_key=cache_key))


@router.get("/stats")
async def get_stats(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
) -> dict:
    """Return per-channel statistics and auto-computed stretch defaults.

    Only applicable to FITS, XISF, float TIFF, and pxiproject. Returns 404 for standard images.
    """
    p, ft, idx, ck = _resolve_path(path)
    if ft == "standard":
        raise HTTPException(
            status_code=404, detail="Stats not available for standard image formats"
        )
    try:
        return await asyncio.to_thread(_compute_stats, p, ft, idx, hdu, ck)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


def _read_pixel(
    p: Path | BinaryIO,
    ft: str,
    idx: int,
    hdu: int,
    x: int,
    y: int,
    cache_key: tuple | None = None,
) -> dict:
    """Load image and read a single pixel (runs in thread pool)."""
    data = _get_cached_image_data(p, ft, idx, hdu, cache_key=cache_key)
    color = is_color_image(data)
    h, w = (data.shape[1], data.shape[2]) if color else (data.shape[0], data.shape[1])

    if x < 0 or x >= w or y < 0 or y >= h:
        raise HTTPException(
            status_code=400, detail=f"Coordinates ({x}, {y}) out of bounds ({w}x{h})"
        )

    if color:
        r, g, b = float(data[0, y, x]), float(data[1, y, x]), float(data[2, y, x])
        k = LUM_R * r + LUM_G * g + LUM_B * b
        return {"x": x, "y": y, "color": True, "R": r, "G": g, "B": b, "K": k}
    val = float(data[y, x])
    return {"x": x, "y": y, "color": False, "K": val}


@router.get("/pixel")
async def get_pixel(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    x: int = Query(..., description="X coordinate (column)"),
    y: int = Query(..., description="Y coordinate (row)"),
) -> dict:
    """Return raw pixel values at the given (x, y) coordinate."""
    p, ft, idx, ck = _resolve_path(path)
    try:
        return await asyncio.to_thread(_read_pixel, p, ft, idx, hdu, x, y, ck)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


_HISTOGRAM_MAX_PIXELS = 2_000_000


def _compute_histogram(data: np.ndarray, bins: int = 256) -> dict:
    """Compute histogram from loaded image data.

    For large images, subsamples to ~2M pixels per channel for performance.
    A 256-bin histogram is statistically identical at this sample size.
    """
    color = is_color_image(data)
    bin_edges = np.linspace(0.0, 1.0, bins + 1)

    # Subsample large images for histogram performance
    h, w = (data.shape[1], data.shape[2]) if color else (data.shape[0], data.shape[1])
    pixel_count = h * w
    stride = max(1, int(np.sqrt(pixel_count / _HISTOGRAM_MAX_PIXELS)))

    channels = []
    if color:
        for i, name in enumerate(["R", "G", "B"]):
            plane = data[i, ::stride, ::stride] if stride > 1 else data[i]
            counts, _ = np.histogram(plane, bins=bin_edges)
            channels.append({"name": name, "bins": counts.tolist()})
        # Luminance from subsampled channels
        r = data[0, ::stride, ::stride] if stride > 1 else data[0]
        g = data[1, ::stride, ::stride] if stride > 1 else data[1]
        b = data[2, ::stride, ::stride] if stride > 1 else data[2]
        lum = LUM_R * r + LUM_G * g + LUM_B * b
        lum_counts, _ = np.histogram(lum, bins=bin_edges)
        luminosity = lum_counts.tolist()
    else:
        plane = data[::stride, ::stride] if stride > 1 else data
        counts, _ = np.histogram(plane, bins=bin_edges)
        channels.append({"name": "L", "bins": counts.tolist()})
        luminosity = None

    return {
        "color": color,
        "channels": channels,
        "luminosity": luminosity,
        "bin_edges": bin_edges.tolist(),
    }


def _load_and_histogram(
    p: Path | BinaryIO,
    ft: str,
    idx: int,
    hdu: int,
    bins: int,
    cache_key: tuple | None = None,
) -> dict:
    """Load image and compute histogram (runs in thread pool)."""
    data = _get_cached_image_data(p, ft, idx, hdu, cache_key=cache_key)
    return _compute_histogram(data, bins)


@router.get("/histogram")
async def get_histogram(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    bins: int = Query(256, description="Number of histogram bins"),
) -> dict:
    """Return per-channel histogram data for the image."""
    p, ft, idx, ck = _resolve_path(path)
    try:
        return await asyncio.to_thread(_load_and_histogram, p, ft, idx, hdu, bins, ck)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


def _compute_stats_and_histogram(
    p: Path | BinaryIO,
    ft: str,
    idx: int,
    hdu: int,
    bins: int,
    cache_key: tuple | None = None,
) -> dict:
    """Load image once, compute both stats and histogram (runs in thread pool)."""
    data = _get_cached_image_data(p, ft, idx, hdu, cache_key=cache_key)
    stats = _get_or_compute_stats(data, p, idx, hdu, cache_key=cache_key)
    return {
        "stats": asdict(stats),
        "histogram": _compute_histogram(data, bins),
    }


@router.get("/stats-histogram")
async def get_stats_and_histogram(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    bins: int = Query(256, description="Number of histogram bins"),
) -> dict:
    """Return stats and histogram in a single response (one data load)."""
    p, ft, idx, ck = _resolve_path(path)
    if ft == "standard":
        raise HTTPException(
            status_code=404,
            detail="Stats/histogram not available for standard image formats",
        )
    try:
        return await asyncio.to_thread(_compute_stats_and_histogram, p, ft, idx, hdu, bins, ck)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


def _render_image(
    p: Path | BinaryIO,
    ft: str,
    idx: int,
    hdu: int,
    linked: StretchParams,
    per_channel: list[StretchParams] | None,
    cache_key: tuple | None = None,
) -> bytes:
    """Load image and render to PNG (runs in thread pool).

    For stretch=auto, passes cached stats to avoid redundant computation.
    """
    if ft == "standard":
        return standard_io.load_image_bytes(p)
    data = _get_cached_image_data(p, ft, idx, hdu, cache_key=cache_key)
    # For auto-stretch, compute stats (with per-key locking to avoid
    # redundant computation with concurrent stats-histogram request)
    if linked and linked.stretch == "auto":
        stats = _get_or_compute_stats(data, p, idx, hdu, cache_key=cache_key)
        linked, per_channel, _ = resolve_auto_stretch(data, stats=stats)
        return render_image_png(data, linked=linked, per_channel=per_channel)
    return render_image_png(data, linked=linked, per_channel=per_channel)


@router.get("/image")
async def get_image(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    stretch: str = Query("stf", description="Stretch type: auto | stf | linear"),
    shadow: float = Query(0.0, description="Shadow clip, normalized 0–1"),
    midtone: float = Query(0.5, description="Midtones balance 0–1"),
    highlight: float = Query(1.0, description="Highlight clip, normalized 0–1"),
    r_shadow: float | None = Query(None),
    r_midtone: float | None = Query(None),
    r_highlight: float | None = Query(None),
    g_shadow: float | None = Query(None),
    g_midtone: float | None = Query(None),
    g_highlight: float | None = Query(None),
    b_shadow: float | None = Query(None),
    b_midtone: float | None = Query(None),
    b_highlight: float | None = Query(None),
) -> Response:
    """Return the image as a PNG. Stretch is applied for scientific formats."""
    p, ft, idx, ck = _resolve_path(path)

    linked = StretchParams(stretch=stretch, shadow=shadow, midtone=midtone, highlight=highlight)

    channel_overrides = [
        r_shadow,
        r_midtone,
        r_highlight,
        g_shadow,
        g_midtone,
        g_highlight,
        b_shadow,
        b_midtone,
        b_highlight,
    ]
    per_channel = None
    if any(v is not None for v in channel_overrides):

        def _ch(sh: float | None, mt: float | None, hl: float | None) -> StretchParams:
            return StretchParams(
                stretch=stretch,
                shadow=sh if sh is not None else shadow,
                midtone=mt if mt is not None else midtone,
                highlight=hl if hl is not None else highlight,
            )

        per_channel = [
            _ch(r_shadow, r_midtone, r_highlight),
            _ch(g_shadow, g_midtone, g_highlight),
            _ch(b_shadow, b_midtone, b_highlight),
        ]

    try:
        png_bytes = await asyncio.to_thread(_render_image, p, ft, idx, hdu, linked, per_channel, ck)
        return Response(content=png_bytes, media_type="image/png")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


# ── Recent files ─────────────────────────────────────────────────────────────

MAX_RECENT = 100


@router.post("/recent")
async def add_recent(path: str = Query(..., description="Path to record")) -> dict:
    """Record a file open. Upserts the path and prunes beyond MAX_RECENT."""
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO recent_files (path, opened_at) VALUES (?, datetime('now'))
               ON CONFLICT(path) DO UPDATE SET opened_at = datetime('now')""",
            (path,),
        )
        await conn.execute(
            """DELETE FROM recent_files WHERE id NOT IN (
                   SELECT id FROM recent_files ORDER BY opened_at DESC LIMIT ?
               )""",
            (MAX_RECENT,),
        )
        await conn.commit()
    return {"ok": True}


def _resolve_recent_name(raw_path: str, project_cache: dict[str, list[dict]]) -> str | None:
    """Resolve display name for a recent file path. Returns None if stale."""
    if "::" not in raw_path:
        p = Path(raw_path)
        return p.name if p.exists() else None

    left_str, right = raw_path.rsplit("::", 1)
    left_path = Path(left_str)

    # Archive virtual path: archive.zip::subdir/file.fits
    if archive_io.is_archive(left_path):
        if not left_path.is_file():
            return None
        entry_name = right.rsplit("/", 1)[-1]
        return f"{left_path.name} / {entry_name}"

    # Pxiproject virtual path: project.pxiproject::index
    project_dir = left_path
    if not project_dir.is_dir():
        return None

    if left_str not in project_cache:
        try:
            project_cache[left_str] = pxiproject_io.list_project_images(project_dir)
        except Exception:
            project_cache[left_str] = []

    images = project_cache[left_str]
    idx = int(right) if right.isdigit() else -1
    img_name = images[idx]["name"] if 0 <= idx < len(images) else right
    return f"{project_dir.name} / {img_name}"


@router.get("/recent")
async def get_recent() -> list[dict]:
    """Return recent files ordered most recent first. Excludes files that no longer exist."""
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT path, opened_at FROM recent_files ORDER BY opened_at DESC LIMIT ?",
            (MAX_RECENT,),
        )
        rows = await cursor.fetchall()

    result = []
    stale_paths = []
    project_cache: dict[str, list[dict]] = {}

    for row in rows:
        raw_path = row[0]
        name = _resolve_recent_name(raw_path, project_cache)
        if name is not None:
            result.append({"path": raw_path, "name": name, "opened_at": row[1]})
        else:
            stale_paths.append(raw_path)

    if stale_paths:
        async with get_db() as conn:
            await conn.executemany(
                "DELETE FROM recent_files WHERE path = ?",
                [(p,) for p in stale_paths],
            )
            await conn.commit()

    return result
