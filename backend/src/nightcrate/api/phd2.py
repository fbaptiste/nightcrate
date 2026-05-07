"""PHD2 guide-log analyzer API endpoints."""

from __future__ import annotations

import asyncio
import io
import logging
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from nightcrate.api.phd2_models import (
    CacheStatsResponse,
    ParseRequest,
    ParseResponse,
    SectionAnalysis,
    SectionWithMetrics,
)
from nightcrate.db.session import get_db
from nightcrate.services import archive_io
from nightcrate.services.phd2_metrics import compute_section_metrics
from nightcrate.services.phd2_models import LogSection, ParsedLog
from nightcrate.services.phd2_parser import parse_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/phd2", tags=["PHD2 Guide-Log Analyzer"])


_CACHE_MAX_ENTRIES = 8
_CACHE_TTL_SECONDS = 120

_CacheKey = tuple[str, int, int]
_cache: dict[_CacheKey, tuple[ParseResponse, float]] = {}
_key_locks: dict[_CacheKey, threading.Lock] = {}
_cache_lock = threading.Lock()


def _resolve_request_path(raw: str) -> tuple[str, int, int, object]:
    """Validate the request path and return (display_path, mtime_ns, size, loader)."""
    if "::" in raw:
        archive_str, entry = raw.split("::", 1)
        archive_path = Path(archive_str).expanduser().resolve()
        if not archive_path.exists():
            raise HTTPException(status_code=404, detail=f"Archive not found: {archive_str}")
        if not archive_path.is_file():
            raise HTTPException(status_code=400, detail=f"Not a file: {archive_str}")
        if not archive_io.is_archive(archive_path):
            raise HTTPException(status_code=400, detail=f"Not a recognized archive: {archive_str}")
        stat = archive_path.stat()
        display = f"{archive_path}::{entry}"

        def _load_archive_entry() -> io.StringIO:
            try:
                buf = archive_io.extract_entry(archive_path, entry)
            except FileNotFoundError as exc:
                raise HTTPException(
                    status_code=404,
                    detail=f"Entry not found in archive: {entry}",
                ) from exc
            stream = io.StringIO(buf.getvalue().decode("utf-8", errors="replace"))
            stream.name = display  # type: ignore[attr-defined]
            return stream

        return display, stat.st_mtime_ns, stat.st_size, _load_archive_entry

    path = Path(raw).expanduser().resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {raw}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {raw}")
    stat = path.stat()
    return str(path), stat.st_mtime_ns, stat.st_size, lambda: path


def _get_cached_parse(key: _CacheKey, loader) -> ParseResponse:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is not None:
            val, ts = entry
            if time.monotonic() - ts < _CACHE_TTL_SECONDS:
                return val
            del _cache[key]
        if key not in _key_locks:
            _key_locks[key] = threading.Lock()
        lock = _key_locks[key]

    with lock:
        with _cache_lock:
            entry = _cache.get(key)
            if entry is not None:
                val, ts = entry
                if time.monotonic() - ts < _CACHE_TTL_SECONDS:
                    return val

        source = loader()
        result = _parse_and_build_response(source)

        with _cache_lock:
            while len(_cache) >= _CACHE_MAX_ENTRIES:
                oldest = next(iter(_cache))
                del _cache[oldest]
                _key_locks.pop(oldest, None)
            _cache[key] = (result, time.monotonic())

    return result


def _parse_and_build_response(source) -> ParseResponse:
    parsed = parse_log(source)
    bundled: list[SectionWithMetrics] = []
    for section in parsed.sections:
        metrics = compute_section_metrics(section)
        bundled.append(
            SectionWithMetrics(section=section, metrics=metrics, analysis=SectionAnalysis())
        )
    return ParseResponse(log=parsed, sections=bundled)


@router.post("/parse", response_model=ParseResponse)
async def parse(request: ParseRequest) -> ParseResponse:
    """Parse a PHD2 guide log at ``request.path`` and return structured data."""
    display, mtime_ns, size, loader = _resolve_request_path(request.path)
    key: _CacheKey = (display, mtime_ns, size)

    try:
        return await asyncio.to_thread(_get_cached_parse, key, loader)
    except HTTPException:
        raise
    except ValueError as exc:
        # Phd2DebugLogRejected (ValueError subclass) and bare ValueError
        # raised when the file isn't a PHD2 guide log.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def cache_stats() -> CacheStatsResponse:
    """Return cache size + configuration for the Admin → Caches view."""
    with _cache_lock:
        return CacheStatsResponse(
            entries=len(_cache),
            max_entries=_CACHE_MAX_ENTRIES,
            ttl_seconds=_CACHE_TTL_SECONDS,
        )


@router.post("/cache/clear", response_model=dict[str, int])
async def cache_clear() -> dict[str, int]:
    """Drop every cached parse — used by the Admin → Caches "Clear" button."""
    with _cache_lock:
        cleared = len(_cache)
        _cache.clear()
        _key_locks.clear()
    return {"cleared": cleared}


@router.post("/export")
async def export_section(
    path: str = Query(...),
    section_index: int = Query(0),
    time_start: float | None = Query(None),
    time_end: float | None = Query(None),
) -> Response:
    """Export a PHD2 guiding section as a valid PHD2 log file.

    Reconstructs the log format with the original header, filtering
    guiding rows to those within [time_start, time_end] (elapsed seconds).
    If time_start/time_end are omitted, exports the full section.
    """
    display, mtime_ns, size, loader = _resolve_request_path(path)
    key: _CacheKey = (display, mtime_ns, size)

    try:
        parsed_response = await asyncio.to_thread(_get_cached_parse, key, loader)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    parsed = parsed_response.log
    if section_index < 0 or section_index >= len(parsed.sections):
        raise HTTPException(status_code=400, detail=f"Section index {section_index} out of range")

    section = parsed.sections[section_index]
    if section.kind != "guiding":
        raise HTTPException(status_code=400, detail="Export is only supported for guiding sections")

    output = await asyncio.to_thread(
        _build_export,
        parsed,
        section,
        time_start,
        time_end,
    )

    filename = f"PHD2_Export_{section.start_time.strftime('%Y-%m-%d_%H%M%S')}.txt"
    return Response(
        content=output,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_export(
    parsed: ParsedLog,
    section: LogSection,
    time_start: float | None,
    time_end: float | None,
) -> str:
    """Reconstruct a PHD2 log file for the given section and time range."""
    lines: list[str] = []

    version_str = (
        f"PHD2 version {parsed.phd2_version}, " if parsed.phd2_version else "PHD2 version, "
    )
    lines.append(
        f"{version_str}Log version {parsed.log_version}. "
        f"Log enabled at {parsed.log_enabled_at.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    lines.append("")

    lines.append(f"Guiding Begins at {section.start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    header = section.header
    if header.dither_description:
        parts = [f"Dither = {header.dither_description}"]
        if header.dither_scale is not None:
            parts.append(f"Dither scale = {header.dither_scale:.3f}")
        if header.image_noise_reduction:
            parts.append(f"Image noise reduction = {header.image_noise_reduction}")
        lines.append(", ".join(parts))
    if header.pixel_scale_arcsec_per_px is not None:
        parts = [f"Pixel scale = {header.pixel_scale_arcsec_per_px:.2f} arc-sec/px"]
        if header.binning is not None:
            parts.append(f"Binning = {header.binning}")
        if header.focal_length_mm is not None:
            parts.append(f"Focal length = {int(header.focal_length_mm)} mm")
        lines.append(", ".join(parts))
    if header.search_region_px is not None:
        line = f"Search region = {header.search_region_px} px"
        if header.star_mass_tolerance_pct is not None:
            line += f", Star mass tolerance = {header.star_mass_tolerance_pct:.1f}%"
        lines.append(line)
    if header.equipment_profile is not None:
        lines.append(f"Equipment Profile = {header.equipment_profile}")
    if header.camera:
        lines.append(f"Camera = {header.camera}")
    if header.exposure_ms is not None:
        lines.append(f"Exposure = {header.exposure_ms} ms")
    for k, v in header.freeform_keys.items():
        lines.append(f"{k} = {v}")

    columns = [
        "Frame",
        "Time",
        "mount",
        "dx",
        "dy",
        "RARawDistance",
        "DECRawDistance",
        "RAGuideDistance",
        "DECGuideDistance",
        "RADuration",
        "RADirection",
        "DECDuration",
        "DECDirection",
        "XStep",
        "YStep",
        "StarMass",
        "SNR",
        "ErrorCode",
    ]
    lines.append(",".join(columns))

    def fmt(v, decimals=3):
        if v is None:
            return ""
        if isinstance(v, int):
            return str(v)
        return f"{v:.{decimals}f}"

    def in_range(t: float | None) -> bool:
        if t is None:
            return time_start is None or time_start <= 0
        if time_start is not None and t < time_start:
            return False
        if time_end is not None and t > time_end:
            return False
        return True

    events_by_time: list[tuple[float | None, str]] = [
        (ev.time_seconds, f"INFO: {ev.raw_message}")
        for ev in section.events
        if in_range(ev.time_seconds)
    ]

    event_idx = 0
    for sample in section.samples:
        if not in_range(sample.time_seconds):
            continue

        while event_idx < len(events_by_time):
            ev_time, ev_line = events_by_time[event_idx]
            if ev_time is None or ev_time <= sample.time_seconds:
                lines.append(ev_line)
                event_idx += 1
            else:
                break

        row = [
            str(sample.frame),
            f"{sample.time_seconds:.3f}",
            f'"{sample.mount_kind}"',
            fmt(sample.dx_px),
            fmt(sample.dy_px),
            fmt(sample.ra_raw_px),
            fmt(sample.dec_raw_px),
            fmt(sample.ra_guide_px),
            fmt(sample.dec_guide_px),
            fmt(sample.ra_duration_ms, 0) if sample.ra_duration_ms is not None else "",
            sample.ra_direction or "",
            fmt(sample.dec_duration_ms, 0) if sample.dec_duration_ms is not None else "",
            sample.dec_direction or "",
            fmt(sample.x_step),
            fmt(sample.y_step),
            fmt(sample.star_mass, 0) if sample.star_mass is not None else "",
            fmt(sample.snr, 2) if sample.snr is not None else "",
            str(sample.error_code),
        ]
        if sample.error_description:
            row.append(f'"{sample.error_description}"')
        lines.append(",".join(row))

    while event_idx < len(events_by_time):
        lines.append(events_by_time[event_idx][1])
        event_idx += 1

    if section.end_time:
        lines.append(f"Guiding Ends at {section.end_time.strftime('%Y-%m-%d %H:%M:%S')}")

    lines.append("")
    return "\n".join(lines)


# ── Recent files ─────────────────────────────────────────────────────────────
# Mirrors the image-analyzer recent-files pattern (api/images.py): same
# upsert + prune-on-cap behavior, but in its own table so the two histories
# stay independent.

MAX_RECENT_PHD2 = 50


@router.post("/recent")
async def add_recent_phd2(path: str = Query(..., description="Path to record")) -> dict:
    """Record a PHD2 log open. Upserts the path and prunes beyond MAX_RECENT_PHD2."""
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO phd2_recent_files (path, opened_at) VALUES (?, datetime('now'))
               ON CONFLICT(path) DO UPDATE SET opened_at = datetime('now')""",
            (path,),
        )
        await conn.execute(
            """DELETE FROM phd2_recent_files WHERE id NOT IN (
                   SELECT id FROM phd2_recent_files ORDER BY opened_at DESC LIMIT ?
               )""",
            (MAX_RECENT_PHD2,),
        )
        await conn.commit()
    return {"ok": True}


@router.get("/recent")
async def get_recent_phd2() -> list[dict]:
    """Return recent PHD2 logs ordered most recent first."""
    async with get_db() as conn:
        cursor = await conn.execute(
            # id DESC as tie-breaker so back-to-back inserts (sub-second
            # apart) still order by insertion sequence.
            "SELECT path, opened_at FROM phd2_recent_files"
            " ORDER BY opened_at DESC, id DESC LIMIT ?",
            (MAX_RECENT_PHD2,),
        )
        rows = await cursor.fetchall()
    return [{"path": row[0], "opened_at": row[1]} for row in rows]


@router.delete("/recent")
async def delete_recent_phd2(path: str = Query(..., description="Path to remove")) -> dict:
    """Remove a single PHD2 log from the recent-files history."""
    async with get_db() as conn:
        await conn.execute(
            "DELETE FROM phd2_recent_files WHERE path = ?",
            (path,),
        )
        await conn.commit()
    return {"ok": True}
