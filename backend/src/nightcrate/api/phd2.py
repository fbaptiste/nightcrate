"""PHD2 guide-log analyzer API endpoints.

Exposes the parser + metrics behind a small set of HTTP endpoints with an
in-process TTL cache so reopen-the-same-log is a fast path. Mirrors the
cache + per-key lock pattern used by `api/images.py`.

Endpoints:
- ``POST /api/phd2/parse`` — parse a log file, return parsed data + metrics
- ``GET  /api/phd2/cache/stats``
- ``POST /api/phd2/cache/clear``
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from nightcrate.api.phd2_models import (
    CacheStatsResponse,
    ParseRequest,
    ParseResponse,
    SectionWithMetrics,
)
from nightcrate.services.phd2_metrics import compute_section_metrics
from nightcrate.services.phd2_parser import parse_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/phd2", tags=["PHD2 Guide-Log Analyzer"])


# ── TTL cache with per-key locks (mirrors api/images.py) ──────────────────────

_CACHE_MAX_ENTRIES = 8
_CACHE_TTL_SECONDS = 120

_cache: dict[tuple[str, int, int], tuple[ParseResponse, float]] = {}
_key_locks: dict[tuple[str, int, int], threading.Lock] = {}
_cache_lock = threading.Lock()


def _cache_key(path: Path) -> tuple[str, int, int]:
    """Key by path + mtime_ns + size so a file edit invalidates the cache."""
    stat = path.stat()
    return (str(path), stat.st_mtime_ns, stat.st_size)


def _get_cached_parse(path: Path) -> ParseResponse:
    """Parse the log, caching the result; concurrent requests for the same file share one parse."""
    key = _cache_key(path)

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

        result = _parse_and_build_response(path)

        with _cache_lock:
            while len(_cache) >= _CACHE_MAX_ENTRIES:
                oldest = next(iter(_cache))
                del _cache[oldest]
                _key_locks.pop(oldest, None)
            _cache[key] = (result, time.monotonic())

    return result


def _parse_and_build_response(path: Path) -> ParseResponse:
    """Parse + compute metrics. Called from inside the per-key lock."""
    parsed = parse_log(path)
    bundled = [
        SectionWithMetrics(section=section, metrics=compute_section_metrics(section))
        for section in parsed.sections
    ]
    return ParseResponse(log=parsed, sections=bundled)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/parse", response_model=ParseResponse)
async def parse(request: ParseRequest) -> ParseResponse:
    """Parse a PHD2 guide log at ``request.path`` and return structured data.

    Not a file upload — the backend reads the file directly from the user's
    filesystem (same pattern as the image viewer). Parsing runs in a worker
    thread because the parser is synchronous / CPU-bound.
    """
    path = Path(request.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.path}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {request.path}")

    try:
        return await asyncio.to_thread(_get_cached_parse, path)
    except ValueError as exc:
        # Covers Phd2DebugLogRejected (ValueError subclass) and bare ValueError
        # raised by the parser when the file isn't a PHD2 guide log at all.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def cache_stats() -> CacheStatsResponse:
    """Report the number of cached log parses."""
    with _cache_lock:
        entries = len(_cache)
    return CacheStatsResponse(
        entries=entries,
        max_entries=_CACHE_MAX_ENTRIES,
        ttl_seconds=_CACHE_TTL_SECONDS,
    )


@router.post("/cache/clear")
async def cache_clear() -> dict[str, int]:
    """Drop all cached parses."""
    with _cache_lock:
        cleared = len(_cache)
        _cache.clear()
        _key_locks.clear()
    return {"cleared": cleared}
