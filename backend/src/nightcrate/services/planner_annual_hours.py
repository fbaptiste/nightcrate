"""Annual "best time of year" track for the planner detail panel.

For each night of a calendar year, returns the number of hours the
target spends above a given altitude threshold **during astronomical
darkness**, optionally with moon avoidance (``moon_sep_deg > 0``) or
without (``moon_sep_deg == 0``, the old "narrowband" mode).

A "night" is the continuous interval from astronomical dusk on
evening date ``D`` to astronomical dawn on day ``D+1``. The bucket the
point belongs to is always labelled by the *evening* date ``D`` — so
hours observed at 02:00 local time on Jan 2 count toward the Jan 1
bucket. We implement that by shifting the sample's local timestamp
back 12 hours before taking its date: a noon-to-noon window anchored
on the local noon of each evening.

Per-night algorithm:
    Sample every quantity (sun alt, obj alt, moon alt, moon–target
    separation) on a 5-minute grid. For each adjacent pair of samples
    forming a 5-minute segment, treat every per-sample quantity as a
    linear function of time across the segment and integrate the
    seconds within the segment where ALL predicates hold
    simultaneously:
      - sun_alt < −18°                           (astronomical darkness)
      - obj_alt > threshold                      (fixed deg, or horizon)
      - moon_alt < 0 OR moon_sep > moon_sep_deg  (only when > 0)

    A predicate that crosses its threshold inside a segment produces a
    sub-interval boundary. The segment's contribution is the sum of
    lengths of the sub-intervals where every predicate holds. This
    replaces the old "count samples × 5 min" approach which suffered
    from ±5-minute quantisation (jagged month-to-month visuals).

Performance: two-pass astropy was redundant now that the integrator
needs all quantities on the full grid — we compute sun / obj / moon
on the full 5-minute year (~105 k samples). When ``moon_sep_deg == 0``
we skip the moon transform entirely (~30% faster). Process-level
parallelism via ``ProcessPoolExecutor`` splits the year into equal
date-range chunks aligned on local-noon boundaries.
"""

from __future__ import annotations

import atexit
import multiprocessing as mp
import threading
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import astropy.units as u
import numpy as np
from astropy.coordinates import AltAz, SkyCoord, get_body
from astropy.time import Time, TimeDelta

from nightcrate.services.horizon import resolve_horizon_altitude
from nightcrate.services.planner_visibility import (
    PlannerHorizon,
    PlannerLocation,
    _make_earth_location,
)

_SAMPLE_MINUTES = 5
_SAMPLE_SECONDS = _SAMPLE_MINUTES * 60
_ASTRO_DARK_DEG = -18.0


@dataclass(frozen=True, slots=True)
class AnnualHoursPoint:
    """One night's bucket — evening date D and hours above threshold."""

    date: date
    hours: float


@dataclass(frozen=True, slots=True)
class MoonDataPoint:
    date: date
    illumination_pct: float
    min_separation_deg: float | None
    max_altitude_deg: float | None


@dataclass(frozen=True, slots=True)
class AnnualHoursTrack:
    dso_id: int
    year: int
    horizon_id: int
    horizon_type: str
    horizon_name: str
    flat_altitude_deg: float | None
    moon_sep_deg: float
    points: list[AnnualHoursPoint]
    filtered_points: list[AnnualHoursPoint]
    moon_data: list[MoonDataPoint]


def _integrate_segment(
    obj_alt1: float,
    obj_alt2: float,
    horizon1: float,
    horizon2: float,
    sun_alt1: float,
    sun_alt2: float,
    moon_alt1: float | None,
    moon_alt2: float | None,
    moon_sep1: float | None,
    moon_sep2: float | None,
    moon_sep_threshold: float,
) -> float:
    """Return the valid seconds within a single 5-minute sample pair.

    Every per-sample quantity is treated as linear in ``u ∈ [0, 1]``
    across the segment. For each predicate we find the crossing of its
    sign-defining linear function (e.g. ``obj_alt − horizon`` for the
    altitude test). The segment is subdivided at every such crossing,
    and each sub-interval's midpoint is tested against every
    predicate; sub-intervals where all predicates pass contribute
    their length to the total.

    ``moon_sep_threshold`` = 0 disables the moon check entirely; the
    moon-alt / moon-sep arguments may be ``None`` in that case.
    """
    apply_moon = moon_sep_threshold > 0.0
    crossings = [0.0, 1.0]

    def root(f1: float, f2: float) -> float | None:
        # Return u ∈ (0, 1) where linear interp crosses zero, or None.
        # Requires a strict sign change between the endpoints.
        if f1 * f2 >= 0:
            return None
        denom = f1 - f2
        # Paranoia guard: tangent-grazing samples with f1 ≈ −f2 ≈ ε
        # can make ``denom`` tiny and flirt with inf/nan. In practice
        # our per-sample quantities move 0.1°–1° per 5-min step, so
        # this path is essentially unreachable — but one free line of
        # defence costs nothing.
        if abs(denom) < 1e-12:
            return None
        uu = f1 / denom
        return uu if 0.0 < uu < 1.0 else None

    u = root(obj_alt1 - horizon1, obj_alt2 - horizon2)
    if u is not None:
        crossings.append(u)
    u = root(_ASTRO_DARK_DEG - sun_alt1, _ASTRO_DARK_DEG - sun_alt2)
    if u is not None:
        crossings.append(u)
    if apply_moon:
        assert moon_alt1 is not None and moon_alt2 is not None  # nosec B101
        assert moon_sep1 is not None and moon_sep2 is not None  # nosec B101
        u = root(-moon_alt1, -moon_alt2)
        if u is not None:
            crossings.append(u)
        u = root(moon_sep1 - moon_sep_threshold, moon_sep2 - moon_sep_threshold)
        if u is not None:
            crossings.append(u)

    crossings.sort()

    total_u = 0.0
    for i in range(len(crossings) - 1):
        u_lo = crossings[i]
        u_hi = crossings[i + 1]
        u_mid = 0.5 * (u_lo + u_hi)

        obj_m = obj_alt1 + u_mid * (obj_alt2 - obj_alt1)
        horiz_m = horizon1 + u_mid * (horizon2 - horizon1)
        if obj_m <= horiz_m:
            continue
        sun_m = sun_alt1 + u_mid * (sun_alt2 - sun_alt1)
        if sun_m >= _ASTRO_DARK_DEG:
            continue
        if apply_moon:
            assert moon_alt1 is not None and moon_alt2 is not None  # nosec B101
            assert moon_sep1 is not None and moon_sep2 is not None  # nosec B101
            moon_m = moon_alt1 + u_mid * (moon_alt2 - moon_alt1)
            sep_m = moon_sep1 + u_mid * (moon_sep2 - moon_sep1)
            if not (moon_m < 0.0 or sep_m > moon_sep_threshold):
                continue

        total_u += u_hi - u_lo

    return total_u * _SAMPLE_SECONDS


def _integrate_filtered_segment(
    obj_alt1: float,
    obj_alt2: float,
    horizon1: float,
    horizon2: float,
    sun_alt1: float,
    sun_alt2: float,
    moon_alt1: float,
    moon_alt2: float,
    illum1: float,
    illum2: float,
    sep1: float,
    sep2: float,
    max_illumination_pct: float | None,
    min_separation_deg: float | None,
    moon_combine: str,
) -> float:
    """Return valid seconds within a segment for the moon filter predicates.

    Same linear-interpolation-and-root approach as ``_integrate_segment``
    but checks the illumination/separation filter instead of the old
    binary moon_sep_threshold.
    """
    crossings = [0.0, 1.0]

    def root(f1: float, f2: float) -> float | None:
        if f1 * f2 >= 0:
            return None
        denom = f1 - f2
        if abs(denom) < 1e-12:
            return None
        uu = f1 / denom
        return uu if 0.0 < uu < 1.0 else None

    u = root(obj_alt1 - horizon1, obj_alt2 - horizon2)
    if u is not None:
        crossings.append(u)
    u = root(_ASTRO_DARK_DEG - sun_alt1, _ASTRO_DARK_DEG - sun_alt2)
    if u is not None:
        crossings.append(u)
    u = root(-moon_alt1, -moon_alt2)
    if u is not None:
        crossings.append(u)
    if max_illumination_pct is not None:
        u = root(max_illumination_pct - illum1, max_illumination_pct - illum2)
        if u is not None:
            crossings.append(u)
    if min_separation_deg is not None:
        u = root(sep1 - min_separation_deg, sep2 - min_separation_deg)
        if u is not None:
            crossings.append(u)

    crossings.sort()

    total_u = 0.0
    for i in range(len(crossings) - 1):
        u_lo = crossings[i]
        u_hi = crossings[i + 1]
        u_mid = 0.5 * (u_lo + u_hi)

        obj_m = obj_alt1 + u_mid * (obj_alt2 - obj_alt1)
        horiz_m = horizon1 + u_mid * (horizon2 - horizon1)
        if obj_m <= horiz_m:
            continue
        sun_m = sun_alt1 + u_mid * (sun_alt2 - sun_alt1)
        if sun_m >= _ASTRO_DARK_DEG:
            continue

        moon_m = moon_alt1 + u_mid * (moon_alt2 - moon_alt1)
        if moon_m < 0.0:
            total_u += u_hi - u_lo
            continue

        illum_m = illum1 + u_mid * (illum2 - illum1)
        sep_m = sep1 + u_mid * (sep2 - sep1)
        illum_pass = max_illumination_pct is None or illum_m <= max_illumination_pct
        sep_pass = min_separation_deg is None or sep_m >= min_separation_deg
        if moon_combine == "or":
            if not (illum_pass or sep_pass):
                continue
        else:
            if not (illum_pass and sep_pass):
                continue

        total_u += u_hi - u_lo

    return total_u * _SAMPLE_SECONDS


def _compute_subrange(
    location: PlannerLocation,
    horizon: PlannerHorizon,
    ra_deg: float,
    dec_deg: float,
    moon_sep_deg: float,
    start_date: date,
    end_date: date,
    max_illumination_pct: float | None = None,
    min_separation_deg: float | None = None,
    moon_combine: str = "and",
) -> list[tuple[date, float, float, float, float | None, float | None]]:
    """Compute per-night raw hours, filtered hours, and moon illumination.

    Raw hours: target above horizon during astro dark (existing logic
    using ``moon_sep_deg`` for backward compat with the old binary filter).

    Filtered hours: applies a second moon filter using
    ``max_illumination_pct`` and/or ``min_separation_deg`` combined
    with ``moon_combine`` ("and" or "or"). When moon is below horizon,
    both predicates pass automatically.

    ``moon_sep_deg == 0`` AND no illumination/separation filters
    disables the moon transform entirely (~30% perf win).
    """
    apply_moon = moon_sep_deg > 0.0
    apply_filter = max_illumination_pct is not None or min_separation_deg is not None
    need_moon = apply_moon or apply_filter
    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    earth_loc = _make_earth_location(location)
    tz = ZoneInfo(location.timezone)

    local_start = datetime(start_date.year, start_date.month, start_date.day, 12, 0, 0, tzinfo=tz)
    local_end = datetime(end_date.year, end_date.month, end_date.day, 12, 0, 0, tzinfo=tz)
    total_seconds = (local_end - local_start).total_seconds()
    n_samples = int(total_seconds / 60.0 / _SAMPLE_MINUTES)
    n_days = (end_date - start_date).days

    t0 = Time(local_start.astimezone(UTC))
    offsets = TimeDelta(np.arange(n_samples, dtype=float) * _SAMPLE_SECONDS, format="sec")
    times = t0 + offsets

    # Full-grid astropy transforms. The integrator needs every
    # quantity at every sample (not just on the dark subset) because
    # a segment straddling dusk / dawn is split at the darkness
    # crossing, and the object / moon values at the crossing are
    # interpolated from the surrounding samples.
    altaz_frame = AltAz(obstime=times, location=earth_loc)
    sun_body = get_body("sun", times, earth_loc)
    sun_alt = np.asarray(sun_body.transform_to(altaz_frame).alt.deg)

    obj_altaz = coord.transform_to(altaz_frame)
    obj_alt = np.asarray(obj_altaz.alt.deg)

    if horizon.type == "artificial":
        # Flat horizon — skip the azimuth extraction entirely.
        horizon_alt = np.full(
            n_samples,
            float(horizon.flat_altitude_deg if horizon.flat_altitude_deg is not None else 0.0),
        )
    else:
        obj_az = np.asarray(obj_altaz.az.deg)
        horizon_alt = resolve_horizon_altitude(
            horizon.type, horizon.flat_altitude_deg, horizon.points, obj_az
        )

    if need_moon:
        moon_body = get_body("moon", times, earth_loc)
        moon_altaz = moon_body.transform_to(altaz_frame)
        moon_alt = np.asarray(moon_altaz.alt.deg)
        moon_sep = np.asarray(coord.separation(moon_body).deg)
        elongation = np.asarray(sun_body.separation(moon_body).deg)
        illum_pct = (1.0 - np.cos(np.radians(elongation))) / 2.0 * 100.0
    else:
        moon_body = None
        moon_alt = None
        moon_sep = None
        illum_pct = None

    # Per-sample predicate values. ``above_h`` / ``dark`` / ``moon_ok``
    # are pointwise booleans used for the vectorised fast-path
    # (stable segments — no predicate sign change within the segment).
    above_h = obj_alt > horizon_alt
    dark = sun_alt < _ASTRO_DARK_DEG
    if apply_moon:
        assert moon_alt is not None and moon_sep is not None  # nosec B101
        moon_ok = (moon_alt < 0.0) | (moon_sep > moon_sep_deg)
    else:
        moon_ok = np.ones(n_samples, dtype=bool)
    sample_valid = above_h & dark & moon_ok

    # Sign-change detection per predicate per segment — linear
    # functions whose roots we'd need to find inside the segment.
    f_h = obj_alt - horizon_alt
    f_d = _ASTRO_DARK_DEG - sun_alt  # >0 ⇔ dark

    def has_sign_change(f: np.ndarray) -> np.ndarray:
        return f[:-1] * f[1:] < 0  # strict — exact zero-touch doesn't flip state

    has_cross = has_sign_change(f_h) | has_sign_change(f_d)
    if apply_moon:
        assert moon_alt is not None and moon_sep is not None  # nosec B101
        has_cross = (
            has_cross | has_sign_change(-moon_alt) | has_sign_change(moon_sep - moon_sep_deg)
        )

    # Fast path: segment has no sign changes in any predicate AND
    # both endpoints are fully valid → whole 300-s segment counts.
    # No sign changes AND endpoints invalid → 0 seconds.
    # Either way we skip the Python-loop integrator.
    stable = ~has_cross
    # If no predicate crosses zero between i and i+1, each individual
    # boolean that feeds ``sample_valid`` is constant across the
    # segment — so ``sample_valid[i+1]`` equals ``sample_valid[i]`` by
    # construction. Checking only the left endpoint is enough.
    stable_full = stable & sample_valid[:-1]
    seconds_per_segment = np.zeros(n_samples - 1, dtype=float)
    seconds_per_segment[stable_full] = _SAMPLE_SECONDS

    # Slow path: only segments with at least one predicate crossing.
    # Typically a handful per day at mid-latitudes (target rise/set,
    # dusk, dawn, moon rise/set, moon separation crossing the threshold).
    crossing_idx = np.where(has_cross)[0]
    if crossing_idx.size > 0:
        for i in crossing_idx:
            seconds_per_segment[i] = _integrate_segment(
                float(obj_alt[i]),
                float(obj_alt[i + 1]),
                float(horizon_alt[i]),
                float(horizon_alt[i + 1]),
                float(sun_alt[i]),
                float(sun_alt[i + 1]),
                float(moon_alt[i]) if moon_alt is not None else None,
                float(moon_alt[i + 1]) if moon_alt is not None else None,
                float(moon_sep[i]) if moon_sep is not None else None,
                float(moon_sep[i + 1]) if moon_sep is not None else None,
                moon_sep_deg,
            )

    # Bucket segments by the evening date of their left endpoint. A
    # segment straddling local noon (once per day) attributes to the
    # bucket of the left endpoint — acceptable because that segment
    # is entirely daylight on the receiving bucket's date anyway, so
    # its contribution is already zero.
    utc_datetimes = times.to_datetime(timezone=UTC)
    day_index = np.fromiter(
        (
            ((dt.astimezone(tz) - timedelta(hours=12)).date() - start_date).days
            for dt in utc_datetimes
        ),
        dtype=np.int32,
        count=len(utc_datetimes),
    )
    seg_day_index = day_index[:-1]
    in_range = (seg_day_index >= 0) & (seg_day_index < n_days)

    seconds_per_day = np.zeros(n_days, dtype=float)
    np.add.at(seconds_per_day, seg_day_index[in_range], seconds_per_segment[in_range])
    hours = seconds_per_day / 3600.0

    # Moon-filtered hours: apply illumination/separation predicates.
    # Uses its own sign-change detection (has_cross_filtered) so that
    # moon rise/set, illumination, and separation crossings are properly
    # handled even when the raw path's moon_sep_deg == 0.
    can_filter = (
        apply_filter
        and need_moon
        and moon_alt is not None
        and moon_sep is not None
        and illum_pct is not None
    )
    if can_filter:
        moon_below = moon_alt < 0.0
        if max_illumination_pct is not None:
            illum_ok = moon_below | (illum_pct <= max_illumination_pct)
        else:
            illum_ok = np.ones(n_samples, dtype=bool)
        if min_separation_deg is not None:
            sep_ok = moon_below | (moon_sep >= min_separation_deg)
        else:
            sep_ok = np.ones(n_samples, dtype=bool)

        if moon_combine == "or":
            moon_filter_ok = illum_ok | sep_ok
        else:
            moon_filter_ok = illum_ok & sep_ok

        filtered_valid = above_h & dark & moon_filter_ok

        has_cross_filtered = (
            has_sign_change(f_h) | has_sign_change(f_d) | has_sign_change(-moon_alt)
        )
        if max_illumination_pct is not None:
            has_cross_filtered = has_cross_filtered | has_sign_change(
                max_illumination_pct - illum_pct
            )
        if min_separation_deg is not None:
            has_cross_filtered = has_cross_filtered | has_sign_change(moon_sep - min_separation_deg)

        filtered_seg = np.zeros(n_samples - 1, dtype=float)
        stable_filtered = ~has_cross_filtered & filtered_valid[:-1]
        filtered_seg[stable_filtered] = _SAMPLE_SECONDS

        crossing_idx_filtered = np.where(has_cross_filtered)[0]
        if crossing_idx_filtered.size > 0:
            for i in crossing_idx_filtered:
                filtered_seg[i] = _integrate_filtered_segment(
                    float(obj_alt[i]),
                    float(obj_alt[i + 1]),
                    float(horizon_alt[i]),
                    float(horizon_alt[i + 1]),
                    float(sun_alt[i]),
                    float(sun_alt[i + 1]),
                    float(moon_alt[i]),
                    float(moon_alt[i + 1]),
                    float(illum_pct[i]),
                    float(illum_pct[i + 1]),
                    float(moon_sep[i]),
                    float(moon_sep[i + 1]),
                    max_illumination_pct,
                    min_separation_deg,
                    moon_combine,
                )

        filtered_per_day = np.zeros(n_days, dtype=float)
        np.add.at(filtered_per_day, seg_day_index[in_range], filtered_seg[in_range])
        filtered_hours = filtered_per_day / 3600.0
    else:
        filtered_hours = hours.copy()

    # Midnight illumination for the response (one value per night).
    midnight_illum = np.zeros(n_days, dtype=float)
    if illum_pct is not None:
        samples_per_day = 24 * 60 // _SAMPLE_MINUTES
        midnight_offset = 12 * 60 // _SAMPLE_MINUTES
        midnight_indices = np.arange(n_days) * samples_per_day + midnight_offset
        valid_mid = midnight_indices < len(illum_pct)
        midnight_illum[valid_mid] = illum_pct[midnight_indices[valid_mid]]

    min_sep_per_day = np.full(n_days, np.inf)
    max_moon_alt_per_day = np.full(n_days, -np.inf)
    if moon_sep is not None:
        valid_mask = (above_h & dark)[:-1] & in_range
        np.minimum.at(min_sep_per_day, seg_day_index[valid_mask], moon_sep[:-1][valid_mask])
    if moon_alt is not None:
        dark_mask = dark[:-1] & in_range
        np.maximum.at(max_moon_alt_per_day, seg_day_index[dark_mask], moon_alt[:-1][dark_mask])
    min_sep_per_day[min_sep_per_day == np.inf] = np.nan
    max_moon_alt_per_day[max_moon_alt_per_day == -np.inf] = np.nan

    return [
        (
            start_date + timedelta(days=i),
            round(float(hours[i]), 2),
            round(float(filtered_hours[i]), 2),
            round(float(midnight_illum[i]), 1),
            round(float(min_sep_per_day[i]), 1) if not np.isnan(min_sep_per_day[i]) else None,
            round(float(max_moon_alt_per_day[i]), 1)
            if not np.isnan(max_moon_alt_per_day[i])
            else None,
        )
        for i in range(n_days)
    ]


# ── Long-lived worker pool ─────────────────────────────────────────────────
#
# Creating a ``ProcessPoolExecutor`` costs ~1 s per worker (spawn context
# + astropy import). For a FastAPI server serving per-request year
# computes, re-creating the pool on every call burns 6–12 s of overhead
# before the real work starts. Caching a module-level pool keyed on
# worker count lets the first request pay the cost; every subsequent
# request reuses the warm workers (astropy already imported).
#
# Thread-safe lazy init via ``threading.Lock``. The pool is closed on
# interpreter shutdown via ``atexit``; uvicorn --reload leaks processes
# between reloads but production deployments don't reload, so that's
# acceptable.
_POOL_LOCK = threading.Lock()
_POOL: ProcessPoolExecutor | None = None
_POOL_WORKERS: int = 0


def _get_pool(n_workers: int) -> ProcessPoolExecutor:
    global _POOL, _POOL_WORKERS
    with _POOL_LOCK:
        if _POOL is None or _POOL_WORKERS != n_workers:
            if _POOL is not None:
                _POOL.shutdown(wait=False, cancel_futures=True)
            ctx = mp.get_context("spawn")
            _POOL = ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx)
            _POOL_WORKERS = n_workers
        return _POOL


def _shutdown_pool() -> None:
    global _POOL
    with _POOL_LOCK:
        if _POOL is not None:
            _POOL.shutdown(wait=False, cancel_futures=True)
            _POOL = None


atexit.register(_shutdown_pool)


def compute_annual_hours(
    location: PlannerLocation,
    horizon: PlannerHorizon,
    year: int,
    dso: SkyCoord | tuple[int, float, float],
    *,
    moon_sep_deg: float,
    max_illumination_pct: float | None = None,
    min_separation_deg: float | None = None,
    moon_combine: str = "and",
    max_workers: int | None = None,
) -> AnnualHoursTrack:
    if not (0.0 <= moon_sep_deg <= 180.0):
        raise ValueError(f"moon_sep_deg must be in [0, 180], got {moon_sep_deg!r}")
    if horizon.type == "custom" and not horizon.points:
        raise ValueError("Custom horizon has no points.")

    if isinstance(dso, tuple):
        dso_id, ra_deg, dec_deg = dso
    else:
        dso_id = 0
        ra_deg = float(dso.ra.deg)  # type: ignore[attr-defined]
        dec_deg = float(dso.dec.deg)  # type: ignore[attr-defined]

    year_start = date(year, 1, 1)
    year_end = date(year + 1, 1, 1)
    n_days = (year_end - year_start).days

    n_workers = max(1, max_workers or 1)
    if n_workers == 1:
        pairs = _compute_subrange(
            location,
            horizon,
            ra_deg,
            dec_deg,
            moon_sep_deg,
            year_start,
            year_end,
            max_illumination_pct,
            min_separation_deg,
            moon_combine,
        )
    else:
        n_workers = min(n_workers, n_days)
        bounds = [
            year_start + timedelta(days=(n_days * i) // n_workers) for i in range(n_workers + 1)
        ]
        chunks = list(zip(bounds[:-1], bounds[1:], strict=True))
        pool = _get_pool(n_workers)
        futures = [
            pool.submit(
                _compute_subrange,
                location,
                horizon,
                ra_deg,
                dec_deg,
                moon_sep_deg,
                start_d,
                end_d,
                max_illumination_pct,
                min_separation_deg,
                moon_combine,
            )
            for start_d, end_d in chunks
        ]
        pairs = []
        for f in futures:
            pairs.extend(f.result())

    pairs.sort(key=lambda p: p[0])
    return AnnualHoursTrack(
        dso_id=dso_id,
        year=year,
        horizon_id=horizon.id,
        horizon_type=horizon.type,
        horizon_name=horizon.name,
        flat_altitude_deg=horizon.flat_altitude_deg,
        moon_sep_deg=moon_sep_deg,
        points=[AnnualHoursPoint(date=d, hours=h) for d, h, _, _, _, _ in pairs],
        filtered_points=[AnnualHoursPoint(date=d, hours=fh) for d, _, fh, _, _, _ in pairs],
        moon_data=[
            MoonDataPoint(
                date=d,
                illumination_pct=il,
                min_separation_deg=sep,
                max_altitude_deg=alt,
            )
            for d, _, _, il, sep, alt in pairs
        ],
    )
