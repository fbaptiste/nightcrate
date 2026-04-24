"""PHD2 guide-log metrics.

Pure functions over the parsed data model. Computes the top-line summary
metrics (RMS, peak, drift, oscillation, frame count, duration, SNR, star
mass) **with settle-window exclusion** — samples inside
``settle_begin``/``settle_end`` windows drop out of every quality
metric so dither excursions don't inflate the numbers (matches PHD2 /
PHDLogViewer convention).

- RMS + peak — v0.22.0 Pass A.
- Settle-window exclusion — v0.22.0 Pass A polish round.
- Drift + oscillation — v0.23.0 Pass B.

All distances are in guide-camera pixels. `arcsec_scale` is surfaced so
the display layer can render dual-unit labels without re-reading the
section header.
"""

from __future__ import annotations

import math
from statistics import median

from pydantic import BaseModel, ConfigDict

from nightcrate.services.phd2_models import GuidingSample, LogEvent, LogSection


class SectionMetrics(BaseModel):
    """Top-line per-section metrics — attached to each guiding section in the API response."""

    model_config = ConfigDict(extra="forbid")

    rms_ra_px: float | None
    rms_dec_px: float | None
    rms_total_px: float | None
    peak_ra_px: float | None
    peak_dec_px: float | None
    # Drift: least-squares slope of ``ra_raw_px`` / ``dec_raw_px`` vs
    # time, reported in px per minute. Sign-preserving — positive Dec
    # drift means the star is drifting north on the camera. ``None``
    # when fewer than two non-null values contributed.
    drift_ra_px_per_min: float | None
    drift_dec_px_per_min: float | None
    # Oscillation: fraction [0, 1] of consecutive stats-sample pairs
    # whose raw-distance sign flipped (zero-valued samples are skipped
    # — zero has no sign). Rates near 0.5 suggest chasing seeing, near
    # 0.3 are typical of good guiding. ``None`` when fewer than two
    # non-null values contributed.
    oscillation_ra: float | None
    oscillation_dec: float | None
    frame_count_total: int
    frame_count_error: int
    # Samples that fell inside a settle window (bracketed by
    # ``settle_begin`` / ``settle_end`` INFO events) — excluded from
    # every quality metric above per PHD2 / PHDLogViewer convention.
    # Includes DROP rows that happened to land in the window.
    frame_count_in_settle: int
    # Samples that actually contributed to the filtered metrics above:
    # has positional data AND outside every settle window. Surfaces
    # as the "active" denominator in the UI frames row.
    frame_count_in_stats: int
    duration_seconds: float
    mean_snr: float | None
    median_snr: float | None
    mean_star_mass: float | None
    # arcsec conversion factor from the section header, surfaced so the UI
    # can render "0.42 px / 1.66″" without re-reading the header. `None` when
    # `Pixel scale` was absent.
    arcsec_scale: float | None


def compute_section_metrics(section: LogSection) -> SectionMetrics:
    """Compute summary metrics for one guiding section.

    Samples inside settle windows (bracketed by ``settle_begin`` /
    ``settle_end`` INFO events) are excluded from every quality metric —
    RMS, peak, SNR, star mass, and even the error count — per PHD2 and
    PHDLogViewer convention. The raw totals (``frame_count_total``,
    ``duration_seconds``) remain unfiltered so the UI can display the
    decomposition "N total · M in stats · K in settle".

    Calibration sections also route through this (returning mostly `None` +
    zero counts) so the API response shape stays uniform across kinds.
    """
    if section.kind == "calibration" or not section.samples:
        return SectionMetrics(
            rms_ra_px=None,
            rms_dec_px=None,
            rms_total_px=None,
            peak_ra_px=None,
            peak_dec_px=None,
            drift_ra_px_per_min=None,
            drift_dec_px_per_min=None,
            oscillation_ra=None,
            oscillation_dec=None,
            frame_count_total=len(section.samples),
            frame_count_error=sum(1 for s in section.samples if s.error_code != 0),
            frame_count_in_settle=0,
            frame_count_in_stats=0,
            duration_seconds=_duration_seconds(section),
            mean_snr=None,
            median_snr=None,
            mean_star_mass=None,
            arcsec_scale=section.header.pixel_scale_arcsec_per_px,
        )

    fallback_end = section.samples[-1].time_seconds
    intervals = _settle_intervals(section.events, fallback_end)

    # Partition: in_settle vs in_stats. A sample only contributes to
    # in_stats when it's outside every settle window AND has positional
    # data (the existing DROP-exclusion rule).
    in_settle_count = 0
    stats_samples: list[GuidingSample] = []
    for s in section.samples:
        if _in_any_interval(s.time_seconds, intervals):
            in_settle_count += 1
            continue
        stats_samples.append(s)

    ra_raw = [s.ra_raw_px for s in stats_samples if s.ra_raw_px is not None]
    dec_raw = [s.dec_raw_px for s in stats_samples if s.dec_raw_px is not None]
    snrs = [s.snr for s in stats_samples if s.snr is not None]
    masses = [s.star_mass for s in stats_samples if s.star_mass is not None]

    rms_ra = _rms(ra_raw)
    rms_dec = _rms(dec_raw)
    rms_total = (
        math.sqrt(rms_ra**2 + rms_dec**2) if rms_ra is not None and rms_dec is not None else None
    )
    peak_ra = max((abs(v) for v in ra_raw), default=None)
    peak_dec = max((abs(v) for v in dec_raw), default=None)
    # Samples that actually contributed to RMS/peak — both axes use the
    # same null-filter shape so counting either gives the stats-active
    # denominator. Uses ra_raw length; samples with one-axis-null are
    # rare and would be a parser anomaly.
    in_stats_count = len(ra_raw)

    # Drift + oscillation over the same stats_samples subset. Computed
    # as (time_seconds, value) pairs so both axes can share the same
    # regression helper — skips rows where either time or value is
    # null / missing.
    ra_pairs = [(s.time_seconds, s.ra_raw_px) for s in stats_samples if s.ra_raw_px is not None]
    dec_pairs = [(s.time_seconds, s.dec_raw_px) for s in stats_samples if s.dec_raw_px is not None]
    drift_ra = _slope_per_minute(ra_pairs)
    drift_dec = _slope_per_minute(dec_pairs)
    oscillation_ra = _oscillation_rate(ra_raw)
    oscillation_dec = _oscillation_rate(dec_raw)

    return SectionMetrics(
        rms_ra_px=rms_ra,
        rms_dec_px=rms_dec,
        rms_total_px=rms_total,
        peak_ra_px=peak_ra,
        peak_dec_px=peak_dec,
        drift_ra_px_per_min=drift_ra,
        drift_dec_px_per_min=drift_dec,
        oscillation_ra=oscillation_ra,
        oscillation_dec=oscillation_dec,
        frame_count_total=len(section.samples),
        frame_count_error=sum(1 for s in stats_samples if s.error_code != 0),
        frame_count_in_settle=in_settle_count,
        frame_count_in_stats=in_stats_count,
        duration_seconds=_duration_seconds(section),
        mean_snr=sum(snrs) / len(snrs) if snrs else None,
        median_snr=median(snrs) if snrs else None,
        mean_star_mass=sum(masses) / len(masses) if masses else None,
        arcsec_scale=section.header.pixel_scale_arcsec_per_px,
    )


def _settle_intervals(events: list[LogEvent], fallback_end_t: float) -> list[tuple[float, float]]:
    """Derive closed settle intervals from a section's INFO events.

    State-machine over sorted ``settle_begin`` / ``settle_end`` events.
    Handles every parser-realistic edge case:

    - ``time_seconds is None`` on a begin → anchor at ``0.0``
      (the event precedes any sample, so "from section start").
    - ``time_seconds is None`` on an end → skip (can't anchor a close).
    - Duplicate begin while open → ignore.
    - Unmatched end (section began mid-settle) → emit ``[0.0, t]``.
    - Unclosed begin at end of walk → close at ``fallback_end_t``.
    """
    relevant: list[tuple[float, str]] = []
    for e in events:
        if e.kind not in ("settle_begin", "settle_end"):
            continue
        if e.time_seconds is None:
            if e.kind == "settle_begin":
                relevant.append((0.0, "settle_begin"))
            # A None-anchored end has nothing to anchor against; skip.
            continue
        relevant.append((e.time_seconds, e.kind))
    relevant.sort(key=lambda p: p[0])

    intervals: list[tuple[float, float]] = []
    open_start: float | None = None
    for t, kind in relevant:
        if kind == "settle_begin":
            if open_start is None:
                open_start = t
            # Duplicate begin while open — ignore.
            continue
        # kind == "settle_end"
        if open_start is not None:
            intervals.append((open_start, t))
            open_start = None
        else:
            # Section opened mid-settle — interval from section start
            # up through this end marker.
            intervals.append((0.0, t))
    if open_start is not None:
        intervals.append((open_start, fallback_end_t))
    return intervals


def _in_any_interval(t: float, intervals: list[tuple[float, float]]) -> bool:
    """Closed-interval membership across a (small) list of windows.

    A sample exactly on a boundary is treated as in-settle — it's a
    transition sample and excluding it matches PHDLogViewer's behaviour.
    """
    for t0, t1 in intervals:
        if t0 <= t <= t1:
            return True
    return False


def _rms(values: list[float]) -> float | None:
    if not values:
        return None
    return math.sqrt(sum(v * v for v in values) / len(values))


def _slope_per_minute(pairs: list[tuple[float, float]]) -> float | None:
    """Least-squares slope of ``value`` against ``time_seconds``,
    returned in **units per minute** (raw slope × 60).

    Requires at least two pairs with differing x values; otherwise
    returns ``None``. No scipy dependency — the closed-form
    ``Σ(x−x̄)(y−ȳ) / Σ(x−x̄)²`` is sufficient and numerically
    stable enough for the sample counts we see in practice.
    """
    if len(pairs) < 2:
        return None
    n = len(pairs)
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    num = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    den = sum((p[0] - mx) ** 2 for p in pairs)
    if den == 0:
        # All x values identical — regression undefined.
        return None
    slope_per_sec = num / den
    return slope_per_sec * 60.0


def _oscillation_rate(values: list[float]) -> float | None:
    """Fraction of consecutive value pairs whose signs differ.

    Zero-valued samples are skipped (a zero has no sign, so counting
    it as a flip would inflate the rate on low-SNR sections). Returns
    ``None`` when fewer than two non-zero values are present.
    """
    nonzero = [v for v in values if v != 0]
    if len(nonzero) < 2:
        return None
    flips = 0
    for a, b in zip(nonzero, nonzero[1:], strict=False):
        if (a > 0) != (b > 0):
            flips += 1
    return flips / (len(nonzero) - 1)


def _duration_seconds(section: LogSection) -> float:
    """Wall-clock duration from first to last sample's ``Time`` column.

    Uses per-frame elapsed seconds rather than section end - section start —
    section end may be ``None`` (EOF-terminated sections), and the sample
    series gives exact duration anyway.
    """
    if not section.samples:
        return 0.0
    return section.samples[-1].time_seconds - section.samples[0].time_seconds
