"""Target Planner visibility engine.

Computes per-DSO alt/az over a night's astro-dark window and reduces to
the fields the planner UI needs (hours_visible, max_altitude, peak_time,
min_moon_separation, rise/set/transit). Vectorized over the full DSO set
via astropy SkyCoord + AltAz broadcasting so a full ~14 k-row snapshot
runs in under a second on typical hardware.

Moon separation is tracked as the closest approach during the
visibility window rather than at peak altitude — the at-peak value can
be misleading when the moon is below the horizon at the object's
transit but rises to approach during the still-visible portion of the
window.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

# Global astropy IERS configuration. Disabling auto-download avoids
# the noisy first-use attempt to fetch Bulletin-A from CDS on dark-site
# observatory boxes with no internet; setting auto_max_age=None makes
# astropy tolerate the bundled predictive table even when its
# predictions are older than 30 days (the ≲ 0.5-arc-sec Earth-orientation
# error is deep in our precision noise). These lines must run before
# any astropy sidereal-time / AltAz call — since this module is imported
# by every other planner module that touches astropy, configuring here
# catches both the FastAPI app path and the pytest path.
from astropy.utils import iers as _astropy_iers

_astropy_iers.conf.auto_download = False
_astropy_iers.conf.auto_max_age = None

import astropy.units as u  # noqa: E402
import numpy as np  # noqa: E402
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body  # noqa: E402
from astropy.time import Time, TimeDelta  # noqa: E402

from nightcrate.services.astronomy import compute_illumination_pct  # noqa: E402
from nightcrate.services.horizon import resolve_horizon_altitude  # noqa: E402

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
    """Minimal location value object decoupled from the Pydantic Location
    model.

    Horizon is now a separate ``PlannerHorizon`` passed alongside —
    every location has ≥1 horizon and the caller picks which one
    (default-for-location or user override). ``updated_at`` flows into
    the visibility cache key so a coordinate or timezone change
    invalidates the cached snapshot automatically.
    """

    id: int
    latitude_deg: float
    longitude_deg: float
    elevation_m: float | None
    timezone: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class PlannerHorizon:
    """One of a location's horizons — either a polyline (``type='custom'``)
    or a constant altitude (``type='artificial'``).

    ``updated_at`` flows into the visibility + annual-hours cache keys
    so any edit to the horizon invalidates derived results.
    """

    id: int
    location_id: int
    name: str
    type: str  # 'custom' | 'artificial'
    flat_altitude_deg: float | None
    # Polyline ordered ascending by azimuth; empty for artificial horizons.
    points: tuple[tuple[float, float], ...]
    updated_at: str


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
    """Per-DSO visibility summary over the astro-dark window.

    Peak and transit used to be two independent numbers that could
    disagree by up to the sample spacing (±2.5 min at 5-min sampling).
    That produced inconsistent UI rows like "peak 55° @ 08:39 / transit
    55° @ 08:36" for objects culminating during the window, where by
    geometric definition the two are the same instant. The reduction
    now collapses them: whenever the object's upper transit lands
    inside the astro-dark window, ``peak_time_utc`` IS the transit and
    ``max_altitude_deg`` is the analytical altitude at transit. When
    the transit falls outside the window, peak is the higher of the
    altitudes at the window's two endpoints.

    ``transit_time_utc`` and ``altitude_at_transit_deg`` are always
    populated — they're pure sidereal geometry, independent of what
    astro-dark does tonight. Callers that want to know whether the
    meridian crossing is imaging-actionable compare ``transit_time_utc``
    to whatever time window they care about.
    """

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
    # Meridian crossing (upper culmination). Altitude can be negative
    # for a target that never rises at this location.
    transit_time_utc: datetime
    altitude_at_transit_deg: float


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


def _reduce_per_dso(
    dsos: Sequence[DsoCoord],
    times: Time,
    alt_deg: np.ndarray,  # (N, T)
    az_deg: np.ndarray,  # (N, T)
    moon_separation_deg: np.ndarray,  # (N, T)
    visible_mask: np.ndarray,  # (N, T) boolean
    *,
    transit_times: Sequence[datetime],
    alt_at_transit: np.ndarray,  # (N,)
    dark_start_utc: datetime,
    dark_end_utc: datetime,
    lat_deg: float,
) -> dict[int, DsoVisibility]:
    """Collapse the (N, T) arrays into one ``DsoVisibility`` per DSO.

    - ``hours_visible``, ``rise``/``set``, ``min_moon_separation`` are
      still derived from the 5-min sampled mask (sub-minute precision
      on those isn't useful for planning).
    - ``peak_time_utc`` / ``max_altitude_deg`` are **analytical**: the
      transit instant if it falls inside the dark window, else the
      higher-altitude dark-window endpoint. No more sampled argmax —
      that was the source of ±2.5-min drift from the analytical
      transit time.
    - ``transit_time_utc`` / ``altitude_at_transit_deg`` always come
      from sidereal geometry (analytic, full datetime precision).
    """
    n_samples = alt_deg.shape[1]
    out: dict[int, DsoVisibility] = {}

    visible_counts = visible_mask.sum(axis=1)
    hours_visible = visible_counts * (_SAMPLE_MINUTES / 60.0)

    # First and last visible index per row (N,). -1 when never visible.
    first_visible = np.where(visible_mask.any(axis=1), visible_mask.argmax(axis=1), -1)
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
    # The 5-min sample grid is built from ``dark_start_utc`` to
    # ``dark_end_utc`` inclusive, so the first and last columns of
    # ``alt_deg`` / ``az_deg`` are the exact endpoint altitudes we need
    # for the fallback peak — no extra astropy call.
    alt_start = alt_deg[:, 0]
    alt_end = alt_deg[:, -1]
    az_start = az_deg[:, 0]
    az_end = az_deg[:, -1]

    for i, dso in enumerate(dsos):
        t_transit = transit_times[i]
        transit_in = dark_start_utc <= t_transit <= dark_end_utc

        if transit_in:
            # Peak IS the transit by geometric definition.
            peak_time = t_transit
            max_alt = float(round(float(alt_at_transit[i]), 2))
            # Azimuth at upper transit: 0° (north) if the object transits
            # north of zenith, else 180° (south). The exact value at
            # ``dec == lat`` (zenith transit) is undefined; 180° is a
            # harmless default for that measure-zero case.
            az_peak = 0.0 if float(dso.dec_deg) > lat_deg else 180.0
        elif alt_start[i] >= alt_end[i]:
            peak_time = dark_start_utc
            max_alt = float(round(float(alt_start[i]), 2))
            az_peak = float(round(float(az_start[i]), 2))
        else:
            peak_time = dark_end_utc
            max_alt = float(round(float(alt_end[i]), 2))
            az_peak = float(round(float(az_end[i]), 2))

        rise_time = times_utc[int(first_visible[i])] if first_visible[i] >= 0 else None
        set_time = times_utc[int(last_visible[i])] if last_visible[i] >= 0 else None

        out[dso.dso_id] = DsoVisibility(
            dso_id=dso.dso_id,
            hours_visible=float(round(hours_visible[i], 2)),
            max_altitude_deg=max_alt,
            peak_time_utc=peak_time,
            azimuth_at_peak_deg=az_peak,
            min_moon_separation_deg=None
            if not np.isfinite(min_sep[i])
            else float(round(min_sep[i], 1)),
            rise_time_utc=rise_time,
            set_time_utc=set_time,
            transit_time_utc=t_transit,
            altitude_at_transit_deg=float(round(float(alt_at_transit[i]), 2)),
        )
    return out


# Mean sidereal day length in hours (Earth rotation period).
_SIDEREAL_DAY_HOURS = 23.9344696


def _compute_upper_transits(
    earth_loc: EarthLocation,
    night_date: date,
    tz: str,
    coords: SkyCoord,
) -> tuple[list[datetime], np.ndarray]:
    """Upper-transit time + altitude for each ICRS coord, within the
    24-hour window centred on local midnight of ``night_date``.

    Two-step:

    1. Find the transit *time* analytically: solve LST = RA at a
       reference instant (local noon of ``night_date``) and advance by
       the wrapped hour angle. The RA drift from J2000-to-epoch
       precession is sub-arcsecond per year, i.e., a few seconds of
       wall-clock drift over a 25-year epoch — well below the 1-minute
       display resolution, so ICRS RA is fine here.

    2. Evaluate altitude through astropy's AltAz transform at that
       transit time, **in apparent coordinates**. Doing this keeps the
       transit-altitude number consistent with the sampled ``alt_deg``
       array used for hours-visible / endpoint-peak — both reflect
       ICRS → precession → nutation → aberration → topocentric AltAz.
       Using the raw formula ``90° − |lat − dec|`` on the catalog
       (J2000) declination would disagree with the sampled path by up
       to the precession shift (roughly 0.1° at dec ≈ +69° for a
       26-year epoch), producing "max alt 55° / transit alt 54°" type
       inconsistencies between the two columns.

    Returned altitude can be negative (object transits below the
    horizon, i.e., never visible). Callers decide how to display that.
    """
    ras_deg = np.asarray(coords.ra.deg)
    tzinfo = ZoneInfo(tz)
    # Reference point: local noon of the night's date (i.e., the day
    # whose evening begins the planning window). The transit we want
    # falls within the following 24 sidereal hours.
    noon_local = datetime(night_date.year, night_date.month, night_date.day, 12, 0, tzinfo=tzinfo)
    t_ref = Time(noon_local.astimezone(UTC))
    lst_deg = t_ref.sidereal_time("apparent", longitude=earth_loc.lon).hour * 15.0
    # Hour angle at the reference: HA = LST − RA, wrapped to [−180, 180].
    ha = (lst_deg - ras_deg + 180.0) % 360.0 - 180.0
    # Upper transit when HA = 0. If HA < 0 the object is east of the
    # meridian → transit is in the future. Convert to hours-from-ref,
    # wrapped to one sidereal day so we always land inside the window.
    sidereal_rate = 360.0 / _SIDEREAL_DAY_HOURS
    hours_to_transit = (-ha / sidereal_rate) % _SIDEREAL_DAY_HOURS
    transit_times_dt = [
        (noon_local + timedelta(hours=float(h))).astimezone(UTC) for h in hours_to_transit
    ]

    # Evaluate altitude at each transit time *through the same frame
    # stack the sampled altitudes use*. One vectorised transform: each
    # coord is paired with its own obstime (both shape N), astropy
    # broadcasts element-wise.
    transit_times_astropy = Time(transit_times_dt)
    altaz_frame = AltAz(obstime=transit_times_astropy, location=earth_loc)
    alt_at_transit = np.asarray(coords.transform_to(altaz_frame).alt.deg)
    return transit_times_dt, alt_at_transit


def compute_visibility_snapshot(
    location: PlannerLocation,
    horizon: PlannerHorizon,
    night_date: date,
    dsos: Sequence[DsoCoord],
) -> VisibilitySnapshot:
    """Compute the visibility snapshot for one night at one location + horizon."""
    earth_loc = _make_earth_location(location)
    dark = _astro_dark_window(location, night_date, earth_loc)

    # Moon phase reference — local midnight. Matches services.astronomy.
    tz = ZoneInfo(location.timezone)
    midnight_local = datetime(
        night_date.year, night_date.month, night_date.day, 0, 0, 0, tzinfo=tz
    ) + timedelta(hours=24)
    moon_phase = compute_illumination_pct(Time(midnight_local.astimezone(UTC)))

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

    # Horizon profile per-(DSO, time): a flat altitude for artificial
    # horizons, polyline interpolation for custom ones. Both return the
    # same (N, T) shape as ``alt_deg`` via ``resolve_horizon_altitude``.
    horizon_alt = resolve_horizon_altitude(
        horizon.type, horizon.flat_altitude_deg, horizon.points, az_deg
    )

    visible = alt_deg > horizon_alt

    # Analytical transit (always populated; outside-of-dark-hours fine)
    # — feeds the peak selection inside ``_reduce_per_dso``.
    transit_times, alt_at_transit = _compute_upper_transits(
        earth_loc, night_date, location.timezone, coords
    )
    per_dso = _reduce_per_dso(
        dsos,
        times,
        alt_deg,
        az_deg,
        moon_sep,
        visible,
        transit_times=transit_times,
        alt_at_transit=alt_at_transit,
        dark_start_utc=dark.start_utc,
        dark_end_utc=dark.end_utc,
        lat_deg=float(earth_loc.lat.deg),
    )
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

    Key includes both ``updated_at`` fields (location + horizon) and
    the horizon id so an edit to either invalidates the cached
    snapshot automatically AND swapping horizons in the planner
    recomputes rather than serving stale numbers. Size is bounded at
    ``max_entries`` with the oldest dropped on insert.
    """

    max_entries: int = 4
    ttl_seconds: int = 900  # 15 minutes
    _entries: dict[tuple[Any, ...], tuple[datetime, VisibilitySnapshot]] = field(
        default_factory=dict
    )

    def _key(
        self,
        location: PlannerLocation,
        horizon: PlannerHorizon,
        night_date: date,
    ) -> tuple[Any, ...]:
        return (
            location.id,
            night_date.isoformat(),
            location.updated_at,
            horizon.id,
            horizon.updated_at,
        )

    def get_or_compute(
        self,
        location: PlannerLocation,
        horizon: PlannerHorizon,
        night_date: date,
        dsos: Sequence[DsoCoord],
    ) -> VisibilitySnapshot:
        now = datetime.now(UTC)
        key = self._key(location, horizon, night_date)
        entry = self._entries.get(key)
        if entry is not None:
            fetched_at, snapshot = entry
            if (now - fetched_at).total_seconds() <= self.ttl_seconds:
                # LRU refresh — touch the entry.
                self._entries[key] = (fetched_at, snapshot)
                return snapshot

        snapshot = compute_visibility_snapshot(location, horizon, night_date, dsos)
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
