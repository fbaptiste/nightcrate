"""PHD2 guide-log analyzer API endpoints.

Exposes the parser + metrics behind a small set of HTTP endpoints with an
in-process TTL cache so reopen-the-same-log is a fast path. Mirrors the
cache + per-key lock pattern used by `api/images.py`.

Accepts two path shapes on ``POST /parse``:

- Plain filesystem path — e.g. ``/path/to/PHD2_GuideLog_…txt``
- Archive virtual path — e.g. ``/path/to/logs.zip::PHD2_GuideLog_…txt``.
  The ``::`` separator mirrors the image-viewer convention and is handled
  by extracting the entry via ``archive_io`` and parsing it from a
  ``StringIO`` (the parser already supports ``Path | TextIO``).

Endpoints:
- ``POST /api/phd2/parse`` — parse a log file, return parsed data + metrics
- ``GET  /api/phd2/cache/stats``
- ``POST /api/phd2/cache/clear``
"""

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
    SectionWithMetrics,
)
from nightcrate.services import archive_io
from nightcrate.services.phd2_metrics import compute_section_metrics
from nightcrate.services.phd2_parser import parse_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/phd2", tags=["PHD2 Guide-Log Analyzer"])


# ── TTL cache with per-key locks (mirrors api/images.py) ──────────────────────

_CACHE_MAX_ENTRIES = 8
_CACHE_TTL_SECONDS = 120

# Cache keys are (display_path, mtime_ns, size_bytes). For plain paths that's
# the file's own stat; for archive virtual paths it's the containing
# archive's stat so editing the archive invalidates the cache.
_cache: dict[tuple[str, int, int], tuple[ParseResponse, float]] = {}
_key_locks: dict[tuple[str, int, int], threading.Lock] = {}
_cache_lock = threading.Lock()


def _resolve_request_path(raw: str) -> tuple[str, int, int, object]:
    """Validate the request path and return (display_path, mtime_ns, size, loader).

    ``loader`` is a zero-arg callable that returns a ``Path | TextIO`` ready
    to hand to ``parse_log``. Separating validation from loading lets us
    surface errors with consistent HTTP status codes without duplicating the
    archive-vs-filesystem branch logic.
    """
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
            # parse_log reads ``source.name`` as the log's file_path. Stamp
            # the virtual path so downstream consumers see a sensible label.
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


def _get_cached_parse(
    key: tuple[str, int, int],
    loader,
) -> ParseResponse:
    """Parse the log, caching the result; concurrent requests for the same
    key share one parse."""
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
    """Parse + compute metrics. Called from inside the per-key lock."""
    parsed = parse_log(source)
    bundled = [
        SectionWithMetrics(section=section, metrics=compute_section_metrics(section))
        for section in parsed.sections
    ]
    return ParseResponse(log=parsed, sections=bundled)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/parse", response_model=ParseResponse)
async def parse(request: ParseRequest) -> ParseResponse:
    """Parse a PHD2 guide log at ``request.path`` and return structured data.

    Accepts either a plain filesystem path or an archive virtual path in the
    form ``archive.zip::path/inside/archive.txt``. Parsing runs in a worker
    thread because the parser is synchronous / CPU-bound.
    """
    display, mtime_ns, size, loader = _resolve_request_path(request.path)
    key = (display, mtime_ns, size)

    try:
        return await asyncio.to_thread(_get_cached_parse, key, loader)
    except HTTPException:
        raise
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
