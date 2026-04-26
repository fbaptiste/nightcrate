"""PHD2 guide-log analyzer API endpoints."""

from __future__ import annotations

import asyncio
import io
import logging
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from nightcrate.api.phd2_models import (
    CacheStatsResponse,
    ParseRequest,
    ParseResponse,
    SectionAnalysis,
    SectionWithMetrics,
)
from nightcrate.services import archive_io
from nightcrate.services.phd2_metrics import compute_section_metrics
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
