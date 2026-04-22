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
class AnnualHoursTrack:
    """Per-night hours-above-threshold series for a single DSO + location
    + horizon."""

    dso_id: int
    year: int
    horizon_id: int
    # 'custom' or 'artificial' — echoes the input horizon's type so the
    # response body stays self-describing without needing a separate
    # horizon fetch.
    horizon_type: str
    horizon_name: str
    # Flat altitude for artificial horizons; ``None`` for custom.
    flat_altitude_deg: float | None
    # Minimum moon–target separation (deg) required for a night-sample
    # to count. ``0`` disables the moon check entirely (all samples
    # pass the moon predicate), matching the old "ignore moon" mode.
    moon_sep_deg: float
    points: list[AnnualHoursPoint]


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


def _compute_subrange(
    location: PlannerLocation,
    horizon: PlannerHorizon,
    ra_deg: float,
    dec_deg: float,
    moon_sep_deg: float,
    start_date: date,
    end_date: date,
) -> list[tuple[date, float]]:
    """Compute per-night hours for nights with evening dates in
    ``[start_date, end_date)``.

    ``moon_sep_deg == 0`` disables the moon check and skips the moon
    astropy transform entirely (~30% perf win).

    Picklable, stateless; fans out cleanly across ``ProcessPoolExecutor``
    workers.
    """
    apply_moon = moon_sep_deg > 0.0
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
    sun_alt = np.asarray(get_body("sun", times, earth_loc).transform_to(altaz_frame).alt.deg)

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

    if apply_moon:
        moon_body = get_body("moon", times, earth_loc)
        moon_altaz = moon_body.transform_to(altaz_frame)
        moon_alt = np.asarray(moon_altaz.alt.deg)
        moon_sep = np.asarray(coord.separation(moon_body).deg)
    else:
        moon_alt = None
        moon_sep = None

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

    return [(start_date + timedelta(days=i), round(float(hours[i]), 2)) for i in range(n_days)]


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
    max_workers: int | None = None,
) -> AnnualHoursTrack:
    """Compute per-night hours above the given horizon.

    ``moon_sep_deg`` sets the minimum moon–target separation (deg)
    required during a sample for the sample to count. ``0`` disables
    the moon check entirely and skips the moon transform; values in
    ``[0, 180]`` are valid.

    ``max_workers`` controls process-level parallelism:
    - ``None`` or ``1`` runs single-process in the caller's thread.
    - ``>= 2`` spawns a ``ProcessPoolExecutor`` with that many workers
      and splits the year into equal date-range chunks. Spawn
      overhead is ~1–2 s on mid-range hardware, so the break-even
      point vs single-process is around 3–4 workers for a full year.
    """
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
            location, horizon, ra_deg, dec_deg, moon_sep_deg, year_start, year_end
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
        points=[AnnualHoursPoint(date=d, hours=h) for d, h in pairs],
    )
