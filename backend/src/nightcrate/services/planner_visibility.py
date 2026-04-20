"""Target Planner visibility engine.

Computes per-DSO alt/az over a night's astro-dark window and reduces to
the fields the planner UI needs (hours_visible, max_altitude, peak_time,
min_moon_separation, rise/set/transit). Vectorized over the full DSO set
via astropy SkyCoord + AltAz broadcasting so a full ~14 k-row snapshot
runs in under a second on typical hardware.

Spec deviation from §7.2: the original spec proposed
``moon_separation_at_peak_deg`` — swapped to
``min_moon_separation_deg`` (closest approach during the visibility
window) because the at-peak value can be wildly misleading when the
moon is below the horizon at the object's transit but approaches
during the visible window.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import astropy.units as u
import numpy as np
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body
from astropy.time import Time, TimeDelta

from nightcrate.services.astronomy import compute_illumination_pct
from nightcrate.services.horizon import interpolate_horizon_altitude

# 5-minute sampling for the planner visibility snapshot. Precision on
# hours-visible is ±2.5 min, which is plenty for planning.
_SAMPLE_MINUTES = 5

# 1-minute sampling for finding sun-altitude crossings (twilight
# boundaries). Same as services/astronomy.py's _DENSE_SAMPLES.
_SUN_SAMPLES_PER_DAY = 1440

_ASTRO_DARK_DEG = -18.0


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PlannerLocation:
    """Minimal value object decoupled from the Pydantic Location model.

    ``updated_at`` fields (location + horizon) flow into the visibility
    cache key so an edit to either invalidates the cached snapshot
    automatically.
    """

    id: int
    latitude_deg: float
    longitude_deg: float
    elevation_m: float | None
    timezone: str
    updated_at: str
    # None or empty list → flat-horizon fallback at ``min_altitude_deg``.
    horizon_points: tuple[tuple[float, float], ...] = ()
    horizon_updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class DsoCoord:
    """Minimal DSO payload for visibility. Pulled by SELECT at snapshot time."""

    dso_id: int
    ra_deg: float
    dec_deg: float
    # Major axis is optional in OpenNGC; None → angular-size filters treat
    # it as zero (the "missing-size" case).
    maj_axis_arcmin: float | None = None


@dataclass(frozen=True, slots=True)
class DarkWindow:
    """Astro-dark window for the snapshot's night.

    ``None`` fields mean astro-dark does not occur tonight (polar
    summer). The snapshot's per-DSO visibility arrays will be empty in
    that case.
    """

    start_utc: datetime | None
    end_utc: datetime | None

    @property
    def hours(self) -> float:
        if self.start_utc is None or self.end_utc is None:
            return 0.0
        return (self.end_utc - self.start_utc).total_seconds() / 3600.0


@dataclass(frozen=True, slots=True)
class DsoVisibility:
    """Per-DSO visibility summary over the astro-dark window."""

    dso_id: int
    hours_visible: float
    max_altitude_deg: float
    peak_time_utc: datetime
    azimuth_at_peak_deg: float
    # Minimum separation to the moon across the visibility window. ``None``
    # when the DSO never rises above horizon during astro-dark.
    min_moon_separation_deg: float | None
    rise_time_utc: datetime | None
    set_time_utc: datetime | None
    # Meridian crossing (upper culmination) within the astro-dark window.
    # ``None`` when the object's true transit falls outside astro-dark
    # — the sampled peak in that case is at a window edge, which means
    # the altitude function is still monotonic across the sample grid.
    transit_time_utc: datetime | None
    altitude_at_transit_deg: float | None


@dataclass(frozen=True, slots=True)
class VisibilitySnapshot:
    """Container returned by ``compute_visibility_snapshot``."""

    location_id: int
    night_date: date
    dark_window: DarkWindow
    moon_phase_pct: float
    per_dso: dict[int, DsoVisibility] = field(default_factory=dict)


# ── Sun-altitude helpers ─────────────────────────────────────────────────────


def _make_earth_location(loc: PlannerLocation) -> EarthLocation:
    elev = loc.elevation_m if loc.elevation_m is not None else 0.0
    return EarthLocation(
        lat=loc.latitude_deg * u.deg, lon=loc.longitude_deg * u.deg, height=elev * u.m
    )


def _astro_dark_window(
    loc: PlannerLocation,
    night_date: date,
    earth_loc: EarthLocation,
) -> DarkWindow:
    """Find the contiguous interval during which sun altitude ≤ −18°.

    Search window is local noon on ``night_date`` to local noon on
    ``night_date + 1``. Polar-summer nights without any astro-dark
    interval return ``DarkWindow(None, None)``.
    """
    tz = ZoneInfo(loc.timezone)
    noon_local = datetime(night_date.year, night_date.month, night_date.day, 12, 0, 0, tzinfo=tz)
    noon_next = noon_local + timedelta(hours=24)

    t_start = Time(noon_local.astimezone(UTC))
    total_sec = (noon_next - noon_local).total_seconds()
    offsets = TimeDelta(np.linspace(0.0, total_sec, _SUN_SAMPLES_PER_DAY), format="sec")
    times = t_start + offsets

    sun = get_body("sun", times, earth_loc)
    sun_alt = sun.transform_to(AltAz(obstime=times, location=earth_loc)).alt.deg
    mask = np.asarray(sun_alt) <= _ASTRO_DARK_DEG
    if not mask.any():
        return DarkWindow(None, None)

    # Longest contiguous run of True — in theory there's only one run per
    # day at temperate latitudes, but extreme polar geometry or daylight
    # saving wraparound can produce more. Pick the longest to be safe.
    idx = np.where(mask)[0]
    splits = np.where(np.diff(idx) > 1)[0]
    runs: list[tuple[int, int]] = []
    start = idx[0]
    for s in splits:
        runs.append((int(start), int(idx[s])))
        start = idx[s + 1]
    runs.append((int(start), int(idx[-1])))
    longest = max(runs, key=lambda r: r[1] - r[0])

    dark_start = times[longest[0]].to_datetime(timezone=UTC)
    dark_end = times[longest[1]].to_datetime(timezone=UTC)
    return DarkWindow(start_utc=dark_start, end_utc=dark_end)


# ── Snapshot computation ─────────────────────────────────────────────────────


def _sample_grid(start: datetime, end: datetime) -> Time:
    """Build a Time grid from ``start`` to ``end`` at ``_SAMPLE_MINUTES`` spacing."""
    total_minutes = max(1, int((end - start).total_seconds() / 60.0))
    n_samples = max(2, total_minutes // _SAMPLE_MINUTES + 1)
    t0 = Time(start)
    offsets = TimeDelta(np.linspace(0.0, (end - start).total_seconds(), n_samples), format="sec")
    return t0 + offsets


def _moon_phase_pct(earth_loc: EarthLocation, reference_time: Time) -> float:
    """Moon illumination fraction (%) at ``reference_time``.

    Thin alias so existing call sites keep their location-passing
    signature; the underlying Meeus calculation lives in
    ``services.astronomy.compute_illumination_pct``.
    """
    # earth_loc is unused — the Meeus computation is geocentric. Kept in
    # the signature for call-site symmetry with compute_visibility_snapshot.
    del earth_loc
    return compute_illumination_pct(reference_time)


def _reduce_per_dso(
    dsos: Sequence[DsoCoord],
    times: Time,
    alt_deg: np.ndarray,  # (N, T)
    az_deg: np.ndarray,  # (N, T)
    moon_separation_deg: np.ndarray,  # (N, T)
    visible_mask: np.ndarray,  # (N, T) boolean
) -> dict[int, DsoVisibility]:
    """Reduce the (N, T) arrays into one DsoVisibility per DSO.

    ``peak_time`` is the time of max altitude across the whole astro-dark
    window regardless of visibility; ``rise``/``set`` are the first/last
    visible samples. ``transit`` matches ``peak`` when the peak sample
    also happens to be visible.
    """
    n_samples = alt_deg.shape[1]
    out: dict[int, DsoVisibility] = {}

    peak_idx = alt_deg.argmax(axis=1)
    rows = np.arange(alt_deg.shape[0])
    max_alt = alt_deg[rows, peak_idx]
    az_peak = az_deg[rows, peak_idx]

    visible_counts = visible_mask.sum(axis=1)
    hours_visible = visible_counts * (_SAMPLE_MINUTES / 60.0)

    # First and last visible index per row (N,). -1 when never visible.
    first_visible = np.where(visible_mask.any(axis=1), visible_mask.argmax(axis=1), -1)
    # reverse-argmax via reversed columns
    last_visible = np.where(
        visible_mask.any(axis=1),
        n_samples - 1 - visible_mask[:, ::-1].argmax(axis=1),
        -1,
    )

    # Minimum moon separation across the visibility window per DSO. inf when
    # never visible — converted to None on output.
    sep_visible = np.where(visible_mask, moon_separation_deg, np.inf)
    min_sep = sep_visible.min(axis=1)

    times_utc = [t.to_datetime(timezone=UTC) for t in times]

    for i, dso in enumerate(dsos):
        peak_i = int(peak_idx[i])
        peak_time = times_utc[peak_i]
        rise_time = times_utc[int(first_visible[i])] if first_visible[i] >= 0 else None
        set_time = times_utc[int(last_visible[i])] if last_visible[i] >= 0 else None
        # Transit = strictly interior local max. The altitude function
        # has exactly one maximum per sidereal day — if the sampled
        # argmax is an edge sample, the object is still climbing or
        # descending and the real transit falls outside astro-dark.
        interior = 0 < peak_i < n_samples - 1
        transit_time = peak_time if interior else None
        transit_alt = float(round(max_alt[i], 2)) if interior else None
        out[dso.dso_id] = DsoVisibility(
            dso_id=dso.dso_id,
            hours_visible=float(round(hours_visible[i], 2)),
            max_altitude_deg=float(round(max_alt[i], 2)),
            peak_time_utc=peak_time,
            azimuth_at_peak_deg=float(round(az_peak[i], 2)),
            min_moon_separation_deg=None
            if not np.isfinite(min_sep[i])
            else float(round(min_sep[i], 1)),
            rise_time_utc=rise_time,
            set_time_utc=set_time,
            transit_time_utc=transit_time,
            altitude_at_transit_deg=transit_alt,
        )
    return out


def compute_visibility_snapshot(
    location: PlannerLocation,
    night_date: date,
    dsos: Sequence[DsoCoord],
    *,
    flat_min_altitude_deg: float,
) -> VisibilitySnapshot:
    """Compute the visibility snapshot for one night at one location.

    ``flat_min_altitude_deg`` is used as the horizon when the location
    has no custom horizon.
    """
    earth_loc = _make_earth_location(location)
    dark = _astro_dark_window(location, night_date, earth_loc)

    # Moon phase reference — local midnight. Matches services.astronomy.
    tz = ZoneInfo(location.timezone)
    midnight_local = datetime(
        night_date.year, night_date.month, night_date.day, 0, 0, 0, tzinfo=tz
    ) + timedelta(hours=24)
    moon_phase = _moon_phase_pct(earth_loc, Time(midnight_local.astimezone(UTC)))

    if dark.start_utc is None or dark.end_utc is None or not dsos:
        return VisibilitySnapshot(
            location_id=location.id,
            night_date=night_date,
            dark_window=dark,
            moon_phase_pct=moon_phase,
            per_dso={},
        )

    times = _sample_grid(dark.start_utc, dark.end_utc)
    altaz_frame = AltAz(obstime=times, location=earth_loc)

    ra = np.asarray([d.ra_deg for d in dsos])
    dec = np.asarray([d.dec_deg for d in dsos])
    coords = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")

    # Broadcast to (N_dsos, N_times).
    altaz = coords[:, None].transform_to(altaz_frame[None, :])
    alt_deg = np.asarray(altaz.alt.deg)
    az_deg = np.asarray(altaz.az.deg)

    # Moon is a single (T,) path shared across DSOs.
    moon_coord = get_body("moon", times, earth_loc)
    # SkyCoord.separation returns an Angle — convert to deg. Broadcasting
    # coords[:, None] against moon_coord[None, :] yields (N, T).
    sep = coords[:, None].separation(moon_coord[None, :]).deg
    moon_sep = np.asarray(sep)

    # Horizon profile per-(DSO, time): interpolate along azimuth when a
    # custom horizon exists; otherwise a scalar flat minimum.
    if location.horizon_points:
        horizon_alt = interpolate_horizon_altitude(location.horizon_points, az_deg)
    else:
        horizon_alt = np.full_like(alt_deg, flat_min_altitude_deg)

    visible = alt_deg > horizon_alt

    per_dso = _reduce_per_dso(dsos, times, alt_deg, az_deg, moon_sep, visible)
    return VisibilitySnapshot(
        location_id=location.id,
        night_date=night_date,
        dark_window=dark,
        moon_phase_pct=moon_phase,
        per_dso=per_dso,
    )


# ── In-process LRU cache ─────────────────────────────────────────────────────


@dataclass
class VisibilityCache:
    """In-process LRU cache for visibility snapshots.

    Key includes both ``updated_at`` fields (location + horizon) so an
    edit to either invalidates the cached snapshot automatically. Size
    is bounded at ``max_entries`` with the oldest dropped on insert.
    """

    max_entries: int = 4
    ttl_seconds: int = 900  # 15 minutes
    _entries: dict[tuple[Any, ...], tuple[datetime, VisibilitySnapshot]] = field(
        default_factory=dict
    )

    def _key(
        self,
        location: PlannerLocation,
        night_date: date,
        flat_min_altitude_deg: float,
    ) -> tuple[Any, ...]:
        return (
            location.id,
            night_date.isoformat(),
            location.updated_at,
            location.horizon_updated_at,
            round(flat_min_altitude_deg, 2),
        )

    def get_or_compute(
        self,
        location: PlannerLocation,
        night_date: date,
        dsos: Sequence[DsoCoord],
        *,
        flat_min_altitude_deg: float,
    ) -> VisibilitySnapshot:
        now = datetime.now(UTC)
        key = self._key(location, night_date, flat_min_altitude_deg)
        entry = self._entries.get(key)
        if entry is not None:
            fetched_at, snapshot = entry
            if (now - fetched_at).total_seconds() <= self.ttl_seconds:
                # LRU refresh — touch the entry.
                self._entries[key] = (fetched_at, snapshot)
                return snapshot

        snapshot = compute_visibility_snapshot(
            location, night_date, dsos, flat_min_altitude_deg=flat_min_altitude_deg
        )
        self._entries[key] = (now, snapshot)
        # Drop oldest entries while over budget.
        while len(self._entries) > self.max_entries:
            oldest_key = next(iter(self._entries))
            del self._entries[oldest_key]
        return snapshot

    def clear(self) -> None:
        self._entries.clear()


# Module-level default cache — one instance shared by the API layer.
default_cache = VisibilityCache()
