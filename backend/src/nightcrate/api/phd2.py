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
    FftPeak,
    FftResult,
    ParseRequest,
    ParseResponse,
    SectionAnalysis,
    SectionWithMetrics,
    WormMarker,
)
from nightcrate.db.session import get_db
from nightcrate.services import archive_io
from nightcrate.services.phd2_fft import compute_section_fft, compute_unguided_fft
from nightcrate.services.phd2_metrics import (
    _in_any_interval,
    _settle_intervals,
    compute_section_metrics,
)
from nightcrate.services.phd2_models import LogSection
from nightcrate.services.phd2_parser import parse_log
from nightcrate.services.phd2_unguided import reconstruct_unguided_ra

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/phd2", tags=["PHD2 Guide-Log Analyzer"])


_CACHE_MAX_ENTRIES = 8
_CACHE_TTL_SECONDS = 120

# Cache key includes rig_id so changing the selected rig re-runs
# worm-marker logic without re-parsing the (immutable) log.
_CacheKey = tuple[str, int, int, int | None]
_cache: dict[_CacheKey, tuple[ParseResponse, float]] = {}
_key_locks: dict[_CacheKey, threading.Lock] = {}
_cache_lock = threading.Lock()


# Spec v4 §6.6 — heuristic worm-marker constraints when rig context
# is absent. Below 0.5″ the low-frequency end is dominated by
# polar-alignment / algorithm behaviour, not the worm gear. Worm
# gears across the imaging market sit in [4, 13] minutes.
_HEURISTIC_AMP_MIN_ARCSEC = 0.5
_HEURISTIC_PERIOD_MIN_S = 300.0
_HEURISTIC_PERIOD_MAX_S = 800.0

# ±5 % absorbs manufacturing variance in published worm periods but
# keeps a 600 s GEM peak from accidentally matching a 287 s CEM
# marker.
_WORM_MATCH_FRAC = 0.05


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
            # parse_log reads source.name as the log file_path.
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
    key: _CacheKey,
    loader,
    rig_info: _RigInfo | None,
) -> ParseResponse:
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
        result = _parse_and_build_response(source, rig_info)

        with _cache_lock:
            while len(_cache) >= _CACHE_MAX_ENTRIES:
                oldest = next(iter(_cache))
                del _cache[oldest]
                _key_locks.pop(oldest, None)
            _cache[key] = (result, time.monotonic())

    return result


class _RigInfo:
    """Subset of `rig_summary` columns the FFT path needs."""

    __slots__ = ("rig_id", "mount_name", "mount_drive_type", "mount_worm_period_seconds")

    def __init__(
        self,
        rig_id: int,
        mount_name: str | None,
        mount_drive_type: str | None,
        mount_worm_period_seconds: float | None,
    ) -> None:
        self.rig_id = rig_id
        self.mount_name = mount_name
        self.mount_drive_type = mount_drive_type
        self.mount_worm_period_seconds = mount_worm_period_seconds


def _parse_and_build_response(source, rig_info: _RigInfo | None) -> ParseResponse:
    parsed = parse_log(source)
    bundled: list[SectionWithMetrics] = []
    for section in parsed.sections:
        metrics = compute_section_metrics(section)
        analysis = _build_section_analysis(section, rig_info)
        bundled.append(SectionWithMetrics(section=section, metrics=metrics, analysis=analysis))
    return ParseResponse(log=parsed, sections=bundled)


def _build_section_analysis(section: LogSection, rig_info: _RigInfo | None) -> SectionAnalysis:
    if section.kind != "guiding":
        return SectionAnalysis()
    stats_samples = _stats_samples(section)
    pixel_scale = section.header.pixel_scale_arcsec_per_px
    fft_ra = compute_section_fft(stats_samples, pixel_scale=pixel_scale, trace="ra")
    fft_dec = compute_section_fft(stats_samples, pixel_scale=pixel_scale, trace="dec")
    # Unguided trace runs over the FULL section (chart overlay shows the raw
    # cumulative drift); the spectrum filters to settle-excluded samples.
    unguided_ra_px = reconstruct_unguided_ra(section)
    fft_unguided = compute_unguided_fft(
        stats_samples,
        _filter_unguided_to_stats(section, stats_samples, unguided_ra_px),
        pixel_scale=pixel_scale,
    )
    # Dec rarely shows clean worm signatures because of asymmetric
    # Dec correction patterns — RA drives the worm marker.
    worm_marker = _build_worm_marker(rig_info, fft_ra)
    return SectionAnalysis(
        fft_ra=fft_ra,
        fft_dec=fft_dec,
        unguided_ra_px=unguided_ra_px,
        fft_unguided=fft_unguided,
        worm_marker=worm_marker,
    )


def _filter_unguided_to_stats(
    section: LogSection,
    stats_samples,
    unguided_ra_px: list[float | None],
) -> list[float | None]:
    """Project unguided values onto the settle-excluded sample subset (O(N))."""
    stats_ids = {id(s) for s in stats_samples}
    return [unguided_ra_px[i] for i, s in enumerate(section.samples) if id(s) in stats_ids]


def _stats_samples(section: LogSection):
    """Mirror the metrics layer's settle-excluded subset."""
    if not section.samples:
        return []
    fallback_end = section.samples[-1].time_seconds
    intervals = _settle_intervals(section.events, fallback_end)
    return [s for s in section.samples if not _in_any_interval(s.time_seconds, intervals)]


def _build_worm_marker(rig_info: _RigInfo | None, fft_ra: FftResult | None) -> WormMarker | None:
    if fft_ra is None or fft_ra.skip_reason is not None:
        return None

    if rig_info is not None and _is_worm_drive(rig_info.mount_drive_type):
        period = rig_info.mount_worm_period_seconds
        if period is not None and period > 0:
            matched = _match_peak(fft_ra.peaks, period)
            if matched is not None and rig_info.mount_name:
                label = (
                    f"Worm-period peak: {matched.amplitude_arcsec:.2f}″ "
                    f"amp @ {matched.period_s:.0f} s (mount: {rig_info.mount_name})"
                )
            elif rig_info.mount_name:
                label = f"Worm period: {period:.0f} s (mount: {rig_info.mount_name})"
            else:
                label = f"Worm period: {period:.0f} s"
            return WormMarker(
                period_s=period,
                source="mount",
                label=label,
                mount_name=rig_info.mount_name,
                matched_peak=matched,
            )

    candidate = _heuristic_worm_peak(fft_ra.peaks)
    if candidate is None:
        return None
    return WormMarker(
        period_s=candidate.period_s,
        source="heuristic",
        label=(
            f"Likely worm-period peak: {candidate.amplitude_arcsec:.2f}″ "
            f"amp @ {candidate.period_s:.0f} s (uncertain — identify the "
            f"mount in the rig for a confident reading)"
        ),
        matched_peak=candidate,
    )


def _is_worm_drive(drive_type: str | None) -> bool:
    # Case-insensitive substring on the free-form drive_type so
    # "Worm gear", "worm-driven", etc. all match. Controlled
    # vocabulary lands in v0.28.0.
    if drive_type is None:
        return False
    return "worm" in drive_type.lower()


def _match_peak(peaks: list[FftPeak], target_period: float) -> FftPeak | None:
    candidates = [
        p for p in peaks if abs(p.period_s - target_period) / target_period <= _WORM_MATCH_FRAC
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.amplitude_arcsec)


def _heuristic_worm_peak(peaks: list[FftPeak]) -> FftPeak | None:
    candidates = [
        p
        for p in peaks
        if _HEURISTIC_PERIOD_MIN_S <= p.period_s <= _HEURISTIC_PERIOD_MAX_S
        and p.amplitude_arcsec > _HEURISTIC_AMP_MIN_ARCSEC
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.amplitude_arcsec)


async def _load_rig_info(rig_id: int) -> _RigInfo:
    async with get_db() as db:
        async with db.execute(
            "SELECT mount_name, mount_drive_type, mount_worm_period_seconds "
            "FROM rig_summary WHERE id = ? AND active = 1",
            (rig_id,),
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Rig not found: {rig_id}")
    mount_name, drive_type, worm_period = row
    return _RigInfo(
        rig_id=rig_id,
        mount_name=mount_name,
        mount_drive_type=drive_type,
        mount_worm_period_seconds=worm_period,
    )


@router.post("/parse", response_model=ParseResponse)
async def parse(request: ParseRequest) -> ParseResponse:
    """Parse a PHD2 guide log at ``request.path`` and return structured data."""
    display, mtime_ns, size, loader = _resolve_request_path(request.path)
    rig_info = await _load_rig_info(request.rig_id) if request.rig_id is not None else None
    key: _CacheKey = (display, mtime_ns, size, request.rig_id)

    try:
        return await asyncio.to_thread(_get_cached_parse, key, loader, rig_info)
    except HTTPException:
        raise
    except ValueError as exc:
        # Phd2DebugLogRejected (ValueError subclass) and bare ValueError
        # raised when the file isn't a PHD2 guide log.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def cache_stats() -> CacheStatsResponse:
    with _cache_lock:
        entries = len(_cache)
    return CacheStatsResponse(
        entries=entries,
        max_entries=_CACHE_MAX_ENTRIES,
        ttl_seconds=_CACHE_TTL_SECONDS,
    )


@router.post("/cache/clear")
async def cache_clear() -> dict[str, int]:
    with _cache_lock:
        cleared = len(_cache)
        _cache.clear()
        _key_locks.clear()
    return {"cleared": cleared}
