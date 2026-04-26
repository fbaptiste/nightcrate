"""PHD2 guide-log metrics.

Pure functions over the parsed data model. Top-line summary metrics —
RMS, peak, drift, polar-alignment error, oscillation, frame counts,
duration, SNR, star mass — computed with settle-window exclusion
(samples bracketed by ``settle_begin`` / ``settle_end`` events drop
out of every quality metric).

Formulas:
  - RMS = population standard deviation (NOT RMS-from-zero).
  - RA drift = ``(ra_last − ra_first − Σ ra_guide) / Δt``.
  - Dec drift = least-squares slope of unguided-frames-only y_accum.
  - PA error = ``3.8197 · |drift_dec| · pixel_scale / cos(δ)`` (Barrett).
  - Peak = sign-preserving max-by-abs.
  - Oscillation = sign-flip rate, zero values treated as positive.

All distances are in guide-camera pixels. ``arcsec_scale`` is surfaced
on the response so the display layer can render dual-unit labels
without re-reading the section header.
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
    # Peak is sign-preserving (max-by-abs) — for
    # ``[+0.3, -0.5, +0.4]``, peak_ra is ``-0.5``, not ``0.5``.
    peak_ra_px: float | None
    peak_dec_px: float | None
    # RA drift via the corrections-subtraction algorithm. Total raw
    # position change minus total guide correction over the section
    # duration, in px / minute. NOT a least-squares slope of raw
    # position vs time — that systematically undershoots the true
    # mount drift when the algorithm successfully damped it.
    drift_ra_px_per_min: float | None
    # Dec drift via the unguided-frames-only accumulation algorithm.
    # Position changes are accumulated only when the previous frame
    # was unguided (``decdur == 0``); the slope of ``y_accum vs t``
    # is the drift rate. Bypasses the asymmetric-Dec-correction
    # problem that breaks the RA algorithm for Dec.
    drift_dec_px_per_min: float | None
    # Polar alignment error in arcminutes, derived from the Dec drift
    # via Barrett's formula: ``α = 3.8197 · |drift| · pixel_scale /
    # cos(δ)``. ``None`` when declination, drift, or pixel scale are
    # unavailable, or near the celestial pole where the formula
    # diverges.
    polar_alignment_error_arcmin: float | None
    # Oscillation: fraction [0, 1] of consecutive stats-sample pairs
    # whose raw-distance sign flipped. Zero-valued samples are
    # treated as positive. ``None`` when fewer than two samples.
    oscillation_ra: float | None
    oscillation_dec: float | None
    # Scatter-ellipse elongation: ``|lx − ly| / (lx + ly)`` over the
    # rotated mount-axis frame (raraw/decraw, centred on per-axis
    # means; rotation ``θ = atan2(cov_xy, var_x)``). Range [0, 1]:
    # 0 = circular, 1 = degenerate line (or near-zero dispersion).
    # ``None`` when fewer than two samples have both axes populated.
    elongation: float | None
    frame_count_total: int
    frame_count_error: int
    # Samples that fell inside a settle window (bracketed by
    # ``settle_begin`` / ``settle_end`` INFO events) — excluded from
    # every quality metric above. Includes DROP rows that happened
    # to land in the window.
    frame_count_in_settle: int
    # Samples that actually contributed to the filtered metrics above:
    # has positional data AND outside every settle window.
    frame_count_in_stats: int
    # Wall-clock duration first → last sample (§5.2.8). Always
    # present even when only one sample exists (in which case 0.0).
    duration_total_seconds: float
    # Sum of inter-frame intervals where both endpoints are settle-
    # excluded (§5.2.8). The "active" denominator a user looks at when
    # asking "how long was I actually guiding?"
    duration_included_seconds: float
    mean_snr: float | None
    median_snr: float | None
    mean_star_mass: float | None
    # arcsec conversion factor from the section header, surfaced so the UI
    # can render "0.42 px / 1.66″" without re-reading the header. ``None``
    # when ``Pixel scale`` was absent.
    arcsec_scale: float | None


def compute_section_metrics(section: LogSection) -> SectionMetrics:
    """Compute summary metrics for one guiding section.

    Samples inside settle windows (bracketed by ``settle_begin`` /
    ``settle_end`` INFO events) are excluded from every quality
    metric — RMS, peak, drift, oscillation, SNR, star mass, and the
    error count. The raw totals (``frame_count_total``,
    ``duration_total_seconds``) remain unfiltered so the UI can
    display the decomposition "N total · M in stats · K in settle".

    Calibration sections route through this too (returning mostly
    ``None`` + zero counts) so the API response shape stays uniform
    across kinds.
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
            polar_alignment_error_arcmin=None,
            oscillation_ra=None,
            oscillation_dec=None,
            elongation=None,
            frame_count_total=len(section.samples),
            frame_count_error=sum(1 for s in section.samples if s.error_code != 0),
            frame_count_in_settle=0,
            frame_count_in_stats=0,
            duration_total_seconds=_duration_total(section),
            duration_included_seconds=0.0,
            mean_snr=None,
            median_snr=None,
            mean_star_mass=None,
            arcsec_scale=section.header.pixel_scale_arcsec_per_px,
        )

    fallback_end = section.samples[-1].time_seconds
    intervals = _settle_intervals(section.events, fallback_end)

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

    rms_ra = _stddev(ra_raw)
    rms_dec = _stddev(dec_raw)
    rms_total = (
        math.sqrt(rms_ra**2 + rms_dec**2) if rms_ra is not None and rms_dec is not None else None
    )

    peak_ra = _signed_peak(ra_raw)
    peak_dec = _signed_peak(dec_raw)

    in_stats_count = len(ra_raw)

    drift_ra = _ra_drift_corrections_subtracted(stats_samples)
    drift_dec = _dec_drift_unguided_only(stats_samples)
    pa_arcmin = _polar_alignment_error_arcmin(
        drift_dec_px_per_min=drift_dec,
        declination_deg=section.header.declination_deg,
        pixel_scale=section.header.pixel_scale_arcsec_per_px,
    )

    oscillation_ra = _oscillation_rate(ra_raw)
    oscillation_dec = _oscillation_rate(dec_raw)
    elongation = _elongation(stats_samples)

    return SectionMetrics(
        rms_ra_px=rms_ra,
        rms_dec_px=rms_dec,
        rms_total_px=rms_total,
        peak_ra_px=peak_ra,
        peak_dec_px=peak_dec,
        drift_ra_px_per_min=drift_ra,
        drift_dec_px_per_min=drift_dec,
        polar_alignment_error_arcmin=pa_arcmin,
        oscillation_ra=oscillation_ra,
        oscillation_dec=oscillation_dec,
        elongation=elongation,
        frame_count_total=len(section.samples),
        frame_count_error=sum(1 for s in stats_samples if s.error_code != 0),
        frame_count_in_settle=in_settle_count,
        frame_count_in_stats=in_stats_count,
        duration_total_seconds=_duration_total(section),
        duration_included_seconds=_duration_included(section.samples, intervals),
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
            continue
        relevant.append((e.time_seconds, e.kind))
    relevant.sort(key=lambda p: p[0])

    intervals: list[tuple[float, float]] = []
    open_start: float | None = None
    for t, kind in relevant:
        if kind == "settle_begin":
            if open_start is None:
                open_start = t
            continue
        if open_start is not None:
            intervals.append((open_start, t))
            open_start = None
        else:
            intervals.append((0.0, t))
    if open_start is not None:
        intervals.append((open_start, fallback_end_t))
    return intervals


def _in_any_interval(t: float, intervals: list[tuple[float, float]]) -> bool:
    """Closed-interval membership across a (small) list of windows.

    A sample exactly on a boundary is treated as in-settle — it's a
    transition sample and excluding it keeps post-dither corrective
    excursions out of the stats.
    """
    for t0, t1 in intervals:
        if t0 <= t <= t1:
            return True
    return False


def _stddev(values: list[float]) -> float | None:
    """Population standard deviation: ``sqrt(mean((x − x̄)²))``,
    NOT ``sqrt(mean(x²))``.

    Returns ``None`` for empty input. For a single value, returns 0.0
    (the variance is zero — sole sample equals the mean).
    """
    if not values:
        return None
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(var)


def _signed_peak(values: list[float]) -> float | None:
    """Sign-preserving max-by-absolute-value.

    For ``[+0.3, -0.5, +0.4]``, returns ``-0.5``. ``None`` when the
    input is empty.
    """
    if not values:
        return None
    return max(values, key=abs)


def _oscillation_rate(values: list[float]) -> float | None:
    """Fraction of consecutive value pairs whose signs differ.

    Zero values are treated as positive for this calculation.
    Returns ``None`` when fewer than two values are present.
    """
    if len(values) < 2:
        return None
    signs = [1 if v >= 0 else -1 for v in values]
    flips = sum(1 for a, b in zip(signs, signs[1:], strict=False) if a != b)
    return flips / (len(values) - 1)


def _ra_drift_corrections_subtracted(stats_samples: list[GuidingSample]) -> float | None:
    """RA drift in px / minute via the corrections-subtraction
    algorithm.

    Total raw RA change minus total RA guide correction over the
    section duration:

    .. code-block:: text

        drift_per_sec = (ra_last − ra_first − Σ ra_guide) / Δt

    The Σ runs over all settle-filtered samples with
    ``ra_duration_ms != 0`` and a non-null ``ra_guide_px``. DROP
    frames with valid ``RAGuideDistance`` values still contribute to
    the sum (the guide pulse went out even if the next-frame
    measurement was rejected).

    Returns ``None`` when fewer than two samples have valid
    ``ra_raw_px`` or when the duration is non-positive.
    """
    valid = [s for s in stats_samples if s.ra_raw_px is not None]
    if len(valid) < 2:
        return None
    first = valid[0]
    last = valid[-1]
    dt = last.time_seconds - first.time_seconds
    if dt <= 0:
        return None
    sum_raguide = 0.0
    for s in stats_samples:
        if s.ra_duration_ms is None or s.ra_duration_ms == 0:
            continue
        if s.ra_guide_px is None:
            continue
        sum_raguide += s.ra_guide_px
    # mypy: valid[*].ra_raw_px is not None by construction.
    drift_per_sec = (last.ra_raw_px - first.ra_raw_px - sum_raguide) / dt  # type: ignore[operator]
    return drift_per_sec * 60.0


def _dec_drift_unguided_only(stats_samples: list[GuidingSample]) -> float | None:
    """Dec drift in px / minute via the unguided-frames-only
    accumulation algorithm.

    Accumulates Dec position changes only when the *previous* frame
    was unguided (``dec_duration_ms == 0``); the slope of ``y_accum
    vs time`` (linear regression ``B = cov(t, y_accum) / var(t)``) is
    the drift rate. Bypasses the asymmetric-Dec-correction problem
    that breaks the RA algorithm for Dec.

    Edge cases:

    - Fewer than two samples with valid ``dec_raw_px`` → ``None``.
    - All-guided section (every prev had a Dec pulse): only the seed
      ``(first.t, 0)`` is in the regression; returns ``0`` in this
      degenerate case.
    - All-unguided section (no Dec pulses ever): every change is
      accumulated, equivalent to the simple least-squares slope of
      ``decraw`` vs ``t``.
    """
    valid = [s for s in stats_samples if s.dec_raw_px is not None]
    if len(valid) < 2:
        return None

    first = valid[0]
    n = 1
    sum_x = first.time_seconds
    sum_y = 0.0
    sum_xx = first.time_seconds**2
    sum_xy = 0.0

    y_accum = 0.0
    prev_y = first.dec_raw_px
    prev_guided = first.dec_duration_ms is not None and first.dec_duration_ms != 0

    for s in valid[1:]:
        # ``s.dec_raw_px`` is non-None by the ``valid`` filter; ``prev_y``
        # carries forward from the previous iteration's ``s.dec_raw_px``
        # (or the initial seed), also non-None.
        if not prev_guided:
            y_accum += s.dec_raw_px - prev_y  # type: ignore[operator]
            n += 1
            sum_x += s.time_seconds
            sum_y += y_accum
            sum_xx += s.time_seconds**2
            sum_xy += s.time_seconds * y_accum
        prev_y = s.dec_raw_px
        prev_guided = s.dec_duration_ms is not None and s.dec_duration_ms != 0

    if n < 2:
        # All-guided section — no unguided drift to estimate.
        return 0.0
    mean_x = sum_x / n
    denom = sum_xx - n * mean_x * mean_x
    if denom == 0:
        return 0.0
    mean_y = sum_y / n
    numer = sum_xy - n * mean_x * mean_y
    return (numer / denom) * 60.0


def _elongation(stats_samples: list[GuidingSample]) -> float | None:
    """Scatter-ellipse elongation.

    Computes ``|lx − ly| / (lx + ly)`` where ``lx`` and ``ly`` are the
    sigmas along the principal axes of the (raraw, decraw) dispersion,
    after rotation by ``θ = atan2(cov_xy, var_x)`` (close to but not
    exactly the textbook PCA form).

    Range ``[0, 1]``: 0 = circular dispersion, 1 = a degenerate line
    (or near-zero dispersion — defensive 1.0).

    Returns ``None`` when fewer than two samples have both ``ra_raw_px``
    and ``dec_raw_px`` populated.
    """
    pairs: list[tuple[float, float]] = []
    for s in stats_samples:
        if s.ra_raw_px is None or s.dec_raw_px is None:
            continue
        pairs.append((s.ra_raw_px, s.dec_raw_px))
    if len(pairs) < 2:
        return None
    n = len(pairs)
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    vxx = 0.0
    vyy = 0.0
    vxy = 0.0
    for x, y in pairs:
        dx = x - mx
        dy = y - my
        vxx += dx * dx
        vyy += dy * dy
        vxy += dx * dy
    vxx /= n
    vyy /= n
    vxy /= n
    theta = math.atan2(vxy, vxx)
    cost = math.cos(theta)
    sint = math.sin(theta)
    rot_vx = 0.0
    rot_vy = 0.0
    for x, y in pairs:
        dx = x - mx
        dy = y - my
        xr = dx * cost + dy * sint
        yr = dy * cost - dx * sint
        rot_vx += xr * xr
        rot_vy += yr * yr
    rot_vx /= n
    rot_vy /= n
    lx = math.sqrt(max(0.0, rot_vx))
    ly = math.sqrt(max(0.0, rot_vy))
    if lx + ly < 1e-6:
        return 1.0
    return abs(lx - ly) / (lx + ly)


def _polar_alignment_error_arcmin(
    *,
    drift_dec_px_per_min: float | None,
    declination_deg: float | None,
    pixel_scale: float | None,
) -> float | None:
    """Polar alignment error in arcminutes — Barrett's formula:

    .. code-block:: text

        α_arcmin = 3.8197 · |drift_dec_px_per_min| · pixel_scale / cos(δ)

    The constant 3.8197 ≈ 60 / 15.71 reproduces Barrett's
    arcsec/min-form derivation for px/min input.

    Returns ``None`` when any input is missing or when ``cos(δ) ≈ 0``
    (near the celestial pole, where the formula diverges).
    """
    if drift_dec_px_per_min is None or declination_deg is None or pixel_scale is None:
        return None
    cos_dec = math.cos(math.radians(declination_deg))
    if abs(cos_dec) < 1e-6:
        return None
    return 3.8197 * abs(drift_dec_px_per_min) * pixel_scale / cos_dec


def _duration_total(section: LogSection) -> float:
    """Wall-clock duration first → last sample (§5.2.8 ``duration_total``).

    Uses per-frame elapsed seconds rather than section end - section
    start — section end may be ``None`` (EOF-terminated sections), and
    the sample series gives exact duration anyway.
    """
    if not section.samples:
        return 0.0
    return section.samples[-1].time_seconds - section.samples[0].time_seconds


def _duration_included(
    samples: list[GuidingSample],
    intervals: list[tuple[float, float]],
) -> float:
    """Sum of inter-frame intervals where both endpoints are outside
    every settle window (§5.2.8 ``duration_included``).

    The "active" duration a user looks at when asking "how long was I
    actually guiding?" — the gaps swallowed by dither-settles drop out.
    """
    if len(samples) < 2:
        return 0.0
    total = 0.0
    prev = samples[0]
    prev_in_stats = not _in_any_interval(prev.time_seconds, intervals)
    for s in samples[1:]:
        in_stats = not _in_any_interval(s.time_seconds, intervals)
        if prev_in_stats and in_stats:
            total += s.time_seconds - prev.time_seconds
        prev = s
        prev_in_stats = in_stats
    return total
