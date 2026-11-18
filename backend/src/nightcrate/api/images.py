"""Unified image API endpoints — dispatches by file type (FITS, XISF, PNG/JPEG/TIFF)."""

import asyncio
import io
import logging
import math
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import BinaryIO, Literal

import numpy as np
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from nightcrate.db.session import get_db
from nightcrate.services import (
    archive_io,
    fits_io,
    image_preview,
    pxiproject_io,
    raw_io,
    raw_support,
    standard_io,
    xisf_io,
)
from nightcrate.services.cfa import (
    CfaPattern,
    PatternInfo,
    parse_bayer,
    pattern_from_fits,
    pattern_from_xisf,
)
from nightcrate.services.fits_header_map import (
    FITS_KEYWORD_ALIASES,
    extract_metadata,
)
from nightcrate.services.frame_quality import analyze_array
from nightcrate.services.imaging import (
    LUM_B,
    LUM_G,
    LUM_R,
    ImageStats,
    StretchParams,
    compute_channel_stats,
    render_image_png,
    resolve_auto_stretch,
)
from nightcrate.services.path_resolver import (
    FITS_EXTENSIONS,
    resolve_path,
)
from nightcrate.services.pixel_loader import (
    LoadedImage,
    display_of,
    load_resolved,
    samples_of,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/images", tags=["Image Analyzer"])

# ---------------------------------------------------------------------------
# In-memory image data cache — avoids redundant file loads when multiple
# endpoints hit the same file within a short window (e.g. opening a file).
# ---------------------------------------------------------------------------

_CACHE_MAX_ENTRIES = 5
_CACHE_TTL_SECONDS = 120

_cache: dict[tuple, tuple[LoadedImage, float]] = {}
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


PatternName = Literal["RGGB", "GRBG", "GBRG", "BGGR"]


def _pattern(value: PatternName | None) -> CfaPattern | None:
    return parse_bayer(value) if value is not None else None


def _get_cached_image(
    p: Path | BinaryIO,
    ft: str,
    idx: int,
    hdu: int,
    cache_key: tuple | None = None,
    pattern: PatternName | None = None,
) -> LoadedImage:
    """Load a :class:`LoadedImage` with TTL cache and per-key locking.

    cache_key is used for archive entries (BytesIO) so concurrent requests
    share cached data instead of loading independently.
    """
    if isinstance(p, Path):
        key = (str(p), p.stat().st_mtime, idx, hdu, pattern)
    elif cache_key is not None:
        key = (*cache_key, hdu, pattern)
    else:
        return load_resolved(
            p,
            ft,
            idx,
            hdu,
            pattern_override=_pattern(pattern),
            reject_recorded_pattern=True,
        )
    return _cached_compute(
        key,
        _cache,
        lambda: load_resolved(
            p,
            ft,
            idx,
            hdu,
            pattern_override=_pattern(pattern),
            reject_recorded_pattern=True,
        ),
    )


def _get_or_compute_stats(
    image: LoadedImage,
    p: Path | BinaryIO,
    idx: int,
    hdu: int,
    cache_key: tuple | None = None,
    pattern: PatternName | None = None,
) -> ImageStats:
    """Return stats from cache or compute once with per-key locking."""
    if isinstance(p, Path):
        key = (str(p), p.stat().st_mtime, idx, hdu, pattern)
    elif cache_key is not None:
        key = (*cache_key, hdu, pattern)
    else:
        return compute_channel_stats(samples_of(image), image)
    return _cached_compute(
        key,
        _stats_cache,
        lambda: compute_channel_stats(samples_of(image), image),
    )


STRUCTURAL_KEYWORDS = fits_io.STRUCTURAL_KEYWORDS


def _colour_info_values(kind: str, info: PatternInfo | None) -> dict:
    return {
        "kind": kind,
        "pattern": "".join(info.pattern.rows) if info is not None else None,
        "source": info.source if info is not None else None,
        "detail": info.detail if info is not None else None,
        "assumptions": list(info.assumptions) if info is not None else [],
    }


def _colour_info(image: LoadedImage) -> dict:
    return _colour_info_values(image.kind, image.pattern)


_IMAGE_READ_ERRORS = (ValueError, OSError, raw_support.RawUnavailable)


def _image_http_error(exc: ValueError | OSError | raw_support.RawUnavailable) -> HTTPException:
    status = 400 if str(exc) == "A colour pattern is already recorded for this image" else 422
    return HTTPException(status_code=status, detail=str(exc))


def _cards_map(cards: list[dict]) -> dict[str, str]:
    return {card["key"]: card["value"] for card in cards if card.get("key")}


def _header_colour(cards: list[dict], *, kind_hint: str | None = None) -> dict:
    header = _cards_map(cards)
    height = int(header.get("NAXIS2", 0) or 0)
    axes = int(header.get("NAXIS", 0) or 0)
    axis1 = int(header.get("NAXIS1", 0) or 0)
    axis3 = int(header.get("NAXIS3", 0) or 0)
    kind = kind_hint or ("colour" if axes == 3 and 3 in {axis1, axis3} else "mono")
    pattern = pattern_from_fits(header, height) if kind == "mono" and height > 0 else None
    if pattern is not None:
        kind = "mosaic"
    return _colour_info_values(kind, pattern)


def _source_factory(source: Path | BinaryIO):
    if isinstance(source, Path):
        return lambda: source
    source.seek(0)
    payload = source.read()
    return lambda: io.BytesIO(payload)


def _list_extensions(path: str) -> list[dict]:
    """List image metadata without decoding or populating the pixel cache."""
    p, ft, idx, _cache_key = resolve_path(path)
    fresh_source = _source_factory(p)
    stretch = ft in ("fits", "xisf", "float_tiff", "pxiproject", "raw")
    if ft == "raw":
        layout = raw_io.read_raw_layout(fresh_source())
        width, height = layout.visible[2:]
        exts = [
            {
                "index": 0,
                "name": Path(path.rsplit("::", 1)[-1]).name,
                "type": f"Camera raw ({width}x{height})",
                "has_image": True,
                "colour": _colour_info_values(
                    "mosaic" if layout.pattern is not None else "mono", layout.pattern
                ),
            }
        ]
    elif ft == "pxiproject":
        exts = pxiproject_io.list_extensions(p, idx)
        cards = pxiproject_io.read_header(p, idx)
        exts[0]["colour"] = _header_colour(cards)
    elif ft == "fits":
        exts = fits_io.list_extensions(fresh_source())
        for ext in exts:
            ext["colour"] = (
                _header_colour(fits_io.read_header(fresh_source(), ext["index"]))
                if ext.get("has_image")
                else None
            )
    elif ft == "xisf":
        exts = xisf_io.list_extensions(fresh_source())
        for ext in exts:
            pattern = pattern_from_xisf(xisf_io.cfa_attributes(fresh_source(), ext["index"]))
            kind = (
                "mosaic"
                if pattern is not None
                else ("colour" if " RGB " in f" {ext['type']} " else "mono")
            )
            if pattern is None:
                cards = xisf_io.read_header(fresh_source(), ext["index"])
                colour = _header_colour(cards, kind_hint=kind)
            else:
                colour = _colour_info_values(kind, pattern)
            ext["colour"] = colour
    else:
        exts = standard_io.list_extensions(fresh_source())
        for ext in exts:
            mode = str(ext["type"]).split(" ", 1)[0].upper()
            if mode in {"1", "L", "I", "F", "I;16"}:
                kind = "mono"
            elif ft == "float_tiff":
                cards = _cards_map(standard_io.read_header(fresh_source()))
                kind = "colour" if int(cards.get("SamplesPerPixel", 1)) >= 3 else "mono"
            else:
                kind = "colour"
            ext["colour"] = _colour_info_values(kind, None)
    for ext in exts:
        ext["supports_stretch"] = stretch
        if not ext.get("has_image"):
            ext["colour"] = None
    return exts


def _read_header(path: str, hdu: int) -> list[dict]:
    p, ft, idx, _cache_key = resolve_path(path)
    if ft == "raw":
        return raw_io.read_header(p)
    if ft == "pxiproject":
        return pxiproject_io.read_header(p, idx)
    if ft == "fits":
        return fits_io.read_header(p, hdu)
    if ft == "xisf":
        return xisf_io.read_header(p, hdu)
    return standard_io.read_header(p)


@router.get("/extensions")
async def get_extensions(
    path: str = Query(..., description="Absolute path to image file"),
) -> list[dict]:
    """List extensions/layers in the file, with stretch capability flag."""
    try:
        return await asyncio.to_thread(_list_extensions, path)
    except HTTPException:
        raise
    except _IMAGE_READ_ERRORS as exc:
        raise _image_http_error(exc) from exc
    except Exception as exc:
        logger.exception("extension listing failed for %s", path)
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


@router.get("/header")
async def get_header(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
) -> list[dict]:
    """Return metadata cards for the specified extension."""
    try:
        return await asyncio.to_thread(_read_header, path, hdu)
    except HTTPException:
        raise
    except _IMAGE_READ_ERRORS as exc:
        raise _image_http_error(exc) from exc
    except Exception as exc:
        logger.exception("read_header failed for %s (hdu=%s)", path, hdu)
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
        logger.exception("update_header failed for %s (hdu=%s, ops=%d)", p, request.hdu, len(ops))
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


@router.get("/metadata")
async def get_metadata(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
) -> dict:
    """Return canonical metadata and unrecognized keywords for a file."""
    p, ft, idx, _ck = resolve_path(path)
    # Before the header read: FITS header reads close a passed buffer.
    file_size_bytes = _file_size_bytes(p, ft, idx)
    try:
        if ft == "raw":
            metadata = await asyncio.to_thread(raw_io.read_raw_metadata, p)
            canonical = {
                "captured_local": (
                    metadata.captured_local.isoformat() if metadata.captured_local else None
                ),
                "utc_offset_minutes": (
                    int(metadata.utc_offset.total_seconds() // 60)
                    if metadata.utc_offset is not None
                    else None
                ),
                "time_source": metadata.time_source,
                "exposure_time": metadata.exposure_s,
                "iso": metadata.iso,
                "make": metadata.make,
                "model": metadata.model,
                "body_serial": metadata.body_serial,
                "lens": metadata.lens,
                "lens_serial": metadata.lens_serial,
                "focal_length_mm": metadata.focal_length_mm,
                "orientation": metadata.orientation,
                "camera_temp": metadata.camera_temp_c,
                "sensor_temp": metadata.sensor_temp_c,
                "compression": metadata.compression,
            }
            return {
                "canonical": canonical,
                "unrecognized_keywords": [],
                "file_size_bytes": file_size_bytes,
            }
        if ft == "pxiproject":
            cards = await asyncio.to_thread(pxiproject_io.read_header, p, idx)
        elif ft == "fits":
            cards = await asyncio.to_thread(fits_io.read_header, p, hdu)
        elif ft == "xisf":
            cards = await asyncio.to_thread(xisf_io.read_header, p, hdu)
        else:
            cards = await asyncio.to_thread(standard_io.read_header, p)
    except _IMAGE_READ_ERRORS as exc:
        raise _image_http_error(exc) from exc
    except Exception as exc:
        logger.exception("fits_keywords failed for %s (ft=%s, hdu=%s)", p, ft, hdu)
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
        "file_size_bytes": file_size_bytes,
    }


def _file_size_bytes(p: Path | BinaryIO, ft: str, idx: int) -> int | None:
    """Size of the stored image, for the analyzer's size pill; None when unknown.

    A plain file is its size on disk. An archive entry is the extracted entry's
    size (``resolve_path`` already holds it in memory). A PixInsight project
    image is its referenced file, or its stored blob inside ``project.data``.
    """
    try:
        if ft == "pxiproject" and isinstance(p, Path):
            entry = pxiproject_io.list_project_images(p)[idx]
            if entry["source"] == "referenced" and entry["file_path"]:
                referenced = pxiproject_io.referenced_image_path(entry["file_path"])
                return referenced.stat().st_size if referenced.is_file() else None
            if entry["data_src"]:
                # The same containment rule as pxiproject_io.load_image_data:
                # a blob path must stay inside project.data.
                data_dir = (p / "project.data").resolve()
                blob = (data_dir / entry["data_src"]).resolve()
                if not blob.is_relative_to(data_dir) or not blob.is_file():
                    return None
                return blob.stat().st_size
            return None
        if isinstance(p, Path):
            return p.stat().st_size
        if hasattr(p, "getbuffer"):
            return p.getbuffer().nbytes
    except OSError, ValueError, IndexError, pxiproject_io.PxiProjectError:
        return None
    return None


def _compute_stats(
    p: Path | BinaryIO,
    ft: str,
    idx: int,
    hdu: int,
    cache_key: tuple | None = None,
    pattern: PatternName | None = None,
) -> dict:
    """Load image and compute stats (runs in thread pool). Uses stats cache."""
    image = _get_cached_image(p, ft, idx, hdu, cache_key=cache_key, pattern=pattern)
    return asdict(_get_or_compute_stats(image, p, idx, hdu, cache_key=cache_key, pattern=pattern))


@router.get("/stats")
async def get_stats(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    pattern: PatternName | None = Query(None, description="View-only Bayer pattern"),
) -> dict:
    """Return per-channel statistics and auto-computed stretch defaults.

    Only applicable to FITS, XISF, float TIFF, and pxiproject. Returns 404 for standard images.
    """
    p, ft, idx, ck = resolve_path(path)
    if ft == "standard":
        raise HTTPException(
            status_code=404, detail="Stats not available for standard image formats"
        )
    try:
        return await asyncio.to_thread(_compute_stats, p, ft, idx, hdu, ck, pattern)
    except _IMAGE_READ_ERRORS as exc:
        raise _image_http_error(exc) from exc
    except Exception as exc:
        logger.exception("stats failed for %s (ft=%s, hdu=%s)", p, ft, hdu)
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


def _compute_quality(
    p: Path | BinaryIO, ft: str, idx: int, hdu: int, cache_key: tuple | None = None
) -> dict:
    """Load image (cached) and measure star + level quality (runs in a thread)."""
    image = _get_cached_image(p, ft, idx, hdu, cache_key=cache_key)
    return analyze_array(image, True)


# Star detection loads the frame at full resolution and peaks around 3x its size
# in memory. Stepping prev/next in the analyzer overlay fires one per step and
# nothing cancels the in-flight ones, so bound the concurrency the same way the
# catalog thumbnail render does (api/ingest.py:_THUMB_SEM).
_QUALITY_SEM = asyncio.Semaphore(3)


@router.get("/quality")
async def get_quality(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
) -> dict:
    """Star count, HFR, star SNR and levels in ADU for the loaded image.

    Deliberately a **separate endpoint from /stats**, not folded into it: star
    detection costs ~0.36 s on a 26 MP frame against ~0.07 s for the whole of
    /stats, so bundling would make an instant panel sluggish on every image —
    including masters and snapshots with no stars worth finding. The analyzer
    fetches the two in parallel and fills the star block in when it lands.

    Shares ``services/frame_quality.analyze_array`` with the catalog's batch
    pass, so what you read here is the same number the catalog stores.
    """
    p, ft, idx, ck = resolve_path(path)
    if ft == "standard":
        raise HTTPException(
            status_code=404, detail="Quality metrics not available for standard image formats"
        )
    try:
        async with _QUALITY_SEM:
            return await asyncio.to_thread(_compute_quality, p, ft, idx, hdu, ck)
    except _IMAGE_READ_ERRORS as exc:
        raise _image_http_error(exc) from exc
    except Exception as exc:
        logger.exception("quality failed for %s (ft=%s, hdu=%s)", p, ft, hdu)
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


def _read_pixel(
    p: Path | BinaryIO,
    ft: str,
    idx: int,
    hdu: int,
    x: int,
    y: int,
    cache_key: tuple | None = None,
    pattern: PatternName | None = None,
) -> dict:
    """Load image and read a single pixel (runs in thread pool)."""
    image = _get_cached_image(p, ft, idx, hdu, cache_key=cache_key, pattern=pattern)
    data = image.recorded
    color = image.kind == "colour"
    h, w = image.height, image.width

    if x < 0 or x >= w or y < 0 or y >= h:
        raise HTTPException(
            status_code=400, detail=f"Coordinates ({x}, {y}) out of bounds ({w}x{h})"
        )

    if color:
        r, g, b = float(data[0, y, x]), float(data[1, y, x]), float(data[2, y, x])
        k = LUM_R * r + LUM_G * g + LUM_B * b
        return {
            "x": x,
            "y": y,
            "color": True,
            "R": r,
            "G": g,
            "B": b,
            "K": k,
            "units": image.units,
            "site_colour": None,
        }
    val = float(data[y, x])
    site_colour = (
        image.pattern.pattern.colour_at(y, x)
        if image.kind == "mosaic" and image.pattern is not None
        else None
    )
    return {
        "x": x,
        "y": y,
        "color": False,
        "K": val,
        "units": image.units,
        "site_colour": site_colour,
    }


@router.get("/pixel")
async def get_pixel(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    x: int = Query(..., description="X coordinate (column)"),
    y: int = Query(..., description="Y coordinate (row)"),
    pattern: PatternName | None = Query(None, description="View-only Bayer pattern"),
) -> dict:
    """Return raw pixel values at the given (x, y) coordinate."""
    p, ft, idx, ck = resolve_path(path)
    try:
        return await asyncio.to_thread(_read_pixel, p, ft, idx, hdu, x, y, ck, pattern)
    except HTTPException:
        raise
    except _IMAGE_READ_ERRORS as exc:
        raise _image_http_error(exc) from exc
    except Exception as exc:
        logger.exception("pixel read failed for %s (x=%s, y=%s, hdu=%s)", p, x, y, hdu)
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


_HISTOGRAM_MAX_PIXELS = 2_000_000


def _histogram_stride(pixel_count: int) -> int:
    """Return a flat stride whose sample count does not exceed the histogram budget."""
    return max(1, math.ceil(max(0, pixel_count) / _HISTOGRAM_MAX_PIXELS))


def _compute_histogram(image: LoadedImage, bins: int = 256) -> dict:
    """Compute a histogram from real channel sites in normalized bin space.

    For large images, subsamples to ~2M pixels per channel for performance.
    A 256-bin histogram is statistically identical at this sample size.
    """
    bin_edges = np.linspace(0.0, 1.0, bins + 1)
    samples = samples_of(image)
    normalised = {name: image.display_normalise(values) for name, values in samples.items()}
    color = len(normalised) == 3
    pixel_count = max((values.size for values in normalised.values()), default=0)
    stride = _histogram_stride(pixel_count)

    channels = []
    for name, values in normalised.items():
        plane = values.ravel()[::stride]
        counts, _ = np.histogram(plane, bins=bin_edges)
        channels.append({"name": name, "bins": counts.tolist()})

    if image.kind == "colour":
        r = normalised["R"].ravel()[::stride]
        g = normalised["G"].ravel()[::stride]
        b = normalised["B"].ravel()[::stride]
        lum = LUM_R * r + LUM_G * g + LUM_B * b
        lum_counts, _ = np.histogram(lum, bins=bin_edges)
        luminosity = lum_counts.tolist()
    else:
        luminosity = None

    return {
        "color": color,
        "channels": channels,
        "luminosity": luminosity,
        "bin_edges": bin_edges.tolist(),
        "units": image.units,
        "full_scale": image.full_scale,
    }


def _load_and_histogram(
    p: Path | BinaryIO,
    ft: str,
    idx: int,
    hdu: int,
    bins: int,
    cache_key: tuple | None = None,
    pattern: PatternName | None = None,
) -> dict:
    """Load image and compute histogram (runs in thread pool)."""
    image = _get_cached_image(p, ft, idx, hdu, cache_key=cache_key, pattern=pattern)
    return _compute_histogram(image, bins)


@router.get("/histogram")
async def get_histogram(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    bins: int = Query(256, description="Number of histogram bins"),
    pattern: PatternName | None = Query(None, description="View-only Bayer pattern"),
) -> dict:
    """Return per-channel histogram data for the image."""
    p, ft, idx, ck = resolve_path(path)
    try:
        return await asyncio.to_thread(_load_and_histogram, p, ft, idx, hdu, bins, ck, pattern)
    except _IMAGE_READ_ERRORS as exc:
        raise _image_http_error(exc) from exc
    except Exception as exc:
        logger.exception("histogram failed for %s (ft=%s, hdu=%s, bins=%s)", p, ft, hdu, bins)
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


def _compute_stats_and_histogram(
    p: Path | BinaryIO,
    ft: str,
    idx: int,
    hdu: int,
    bins: int,
    cache_key: tuple | None = None,
    pattern: PatternName | None = None,
) -> dict:
    """Load image once, compute both stats and histogram (runs in thread pool)."""
    image = _get_cached_image(p, ft, idx, hdu, cache_key=cache_key, pattern=pattern)
    stats = _get_or_compute_stats(image, p, idx, hdu, cache_key=cache_key, pattern=pattern)
    return {
        "stats": asdict(stats),
        "histogram": _compute_histogram(image, bins),
    }


@router.get("/stats-histogram")
async def get_stats_and_histogram(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    bins: int = Query(256, description="Number of histogram bins"),
    pattern: PatternName | None = Query(None, description="View-only Bayer pattern"),
) -> dict:
    """Return stats and histogram in a single response (one data load)."""
    p, ft, idx, ck = resolve_path(path)
    if ft == "standard":
        raise HTTPException(
            status_code=404,
            detail="Stats/histogram not available for standard image formats",
        )
    try:
        return await asyncio.to_thread(
            _compute_stats_and_histogram, p, ft, idx, hdu, bins, ck, pattern
        )
    except _IMAGE_READ_ERRORS as exc:
        raise _image_http_error(exc) from exc
    except Exception as exc:
        logger.exception("stats+histogram failed for %s (ft=%s, hdu=%s)", p, ft, hdu)
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


def _render_image(
    p: Path | BinaryIO,
    ft: str,
    idx: int,
    hdu: int,
    linked: StretchParams,
    per_channel: list[StretchParams] | None,
    cache_key: tuple | None = None,
    pattern: PatternName | None = None,
) -> bytes:
    """Load image and render to PNG (runs in thread pool).

    For stretch=auto, passes cached stats to avoid redundant computation.
    """
    if ft == "standard":
        return standard_io.load_image_bytes(p)
    image = _get_cached_image(p, ft, idx, hdu, cache_key=cache_key, pattern=pattern)
    data = display_of(image)
    # For auto-stretch, compute stats (with per-key locking to avoid
    # redundant computation with concurrent stats-histogram request)
    if linked and linked.stretch == "auto":
        stats = _get_or_compute_stats(image, p, idx, hdu, cache_key=cache_key, pattern=pattern)
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
    pattern: PatternName | None = Query(None, description="View-only Bayer pattern"),
) -> Response:
    """Return the image as a PNG. Stretch is applied for scientific formats."""
    p, ft, idx, ck = resolve_path(path)

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
        png_bytes = await asyncio.to_thread(
            _render_image, p, ft, idx, hdu, linked, per_channel, ck, pattern
        )
        return Response(content=png_bytes, media_type="image/png")
    except _IMAGE_READ_ERRORS as exc:
        raise _image_http_error(exc) from exc
    except Exception as exc:
        logger.exception("image render failed for %s (ft=%s, hdu=%s)", p, ft, hdu)
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


@router.get("/preview")
async def get_preview(
    path: str = Query(..., description="Absolute or virtual image path"),
    hdu: int = Query(0, ge=0, description="Extension index"),
    max_px: int = Query(image_preview.DEFAULT_MAX_PX, description="Maximum long-side pixels"),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
) -> Response:
    """Return a bounded, auto-stretched JPEG preview with revalidation headers."""
    try:
        preview = await asyncio.to_thread(
            image_preview.get_preview,
            path,
            hdu=hdu,
            max_px=max_px,
            if_none_match=if_none_match,
        )
    except image_preview.PreviewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except image_preview.PreviewUnreadable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    headers = {"ETag": preview.etag, "Cache-Control": "no-cache"}
    if preview.not_modified:
        return Response(status_code=304, headers=headers)
    return Response(content=preview.content, media_type="image/jpeg", headers=headers)


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
