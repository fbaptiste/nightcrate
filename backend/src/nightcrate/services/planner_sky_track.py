"""High-resolution sky-track for the planner detail panel graph.

Produces per-(DSO, time) altitude + azimuth over a wider window than the
visibility snapshot: from 30 minutes before civil dusk to 30 minutes
after civil dawn, at 5-minute sampling. The detail-panel D3 graph needs
full-twilight context (astro-dark alone wouldn't show the twilight
bands), plus a moon-altitude line and a horizon reference curve.

Cheap enough (~180 samples, one DSO) to compute per-request; no cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import astropy.units as u
import numpy as np
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body
from astropy.time import Time, TimeDelta

from nightcrate.services.astronomy import compute_illumination_pct
from nightcrate.services.horizon import interpolate_horizon_altitude
from nightcrate.services.planner_visibility import (
    PlannerLocation,
    _make_earth_location,
)

_SAMPLE_MINUTES = 5
_SUN_SAMPLES_PER_DAY = 1440

# Sun-altitude thresholds — same as services.astronomy.
_HORIZON = -0.833
_CIVIL = -6.0
_NAUTICAL = -12.0
_ASTRONOMICAL = -18.0


@dataclass(frozen=True, slots=True)
class TwilightBands:
    """UTC start/end times for the three twilight phases + horizon.

    All fields may be None at polar latitudes or when the requested
    night doesn't span a particular twilight phase.
    """

    sunset_utc: datetime | None
    civil_end_utc: datetime | None
    nautical_end_utc: datetime | None
    astro_start_utc: datetime | None
    astro_end_utc: datetime | None
    nautical_start_utc: datetime | None
    civil_start_utc: datetime | None
    sunrise_utc: datetime | None


@dataclass(frozen=True, slots=True)
class SkyTrack:
    """Per-time altitude/azimuth series for a single DSO.

    All list fields share the same length and ``times_utc`` index.
    Used by the planner detail panel's D3 sky-position graph.
    """

    dso_id: int
    times_utc: list[datetime]
    object_altitude_deg: list[float]
    object_azimuth_deg: list[float]
    moon_altitude_deg: list[float]
    horizon_altitude_at_object_az: list[float]
    twilight: TwilightBands
    moon_phase_pct: float
    # Highest-altitude sample within the display window — always defined
    # (even if the object's true transit falls outside the window).
    peak_time_utc: datetime
    peak_altitude_deg: float
    # Meridian crossing (upper culmination); ``None`` when the object's
    # transit falls outside the display window.
    transit_time_utc: datetime | None


def _find_sun_crossings(
    sun_alt_deg: np.ndarray, times: Time
) -> tuple[
    datetime | None,
    datetime | None,
    datetime | None,
    datetime | None,
    datetime | None,
    datetime | None,
    datetime | None,
    datetime | None,
]:
    """Find the 8 twilight crossings inside a 24h noon-to-noon window.

    Returns (sunset, civil_end, nautical_end, astro_start, astro_end,
    nautical_start, civil_start, sunrise) as UTC datetimes or None.
    """

    def _first_crossing(threshold: float, direction: str, start_idx: int = 0) -> datetime | None:
        alt = sun_alt_deg
        if direction == "down":
            mask = alt[:-1] > threshold
            crossings = np.where(mask & (alt[1:] <= threshold))[0]
        else:
            mask = alt[:-1] < threshold
            crossings = np.where(mask & (alt[1:] >= threshold))[0]
        crossings = crossings[crossings >= start_idx]
        if len(crossings) == 0:
            return None
        idx = int(crossings[0])
        # Linear interpolation between samples.
        a0 = float(alt[idx])
        a1 = float(alt[idx + 1])
        # The mask guarantees a0 and a1 bracket the threshold, so a1 != a0.
        frac = (threshold - a0) / (a1 - a0)
        dt_sec = (times[idx + 1] - times[idx]).sec
        return (times[idx] + TimeDelta(frac * dt_sec, format="sec")).to_datetime(timezone=UTC)

    sunset = _first_crossing(_HORIZON, "down")
    civil_end = _first_crossing(_CIVIL, "down")
    nautical_end = _first_crossing(_NAUTICAL, "down")
    astro_start = _first_crossing(_ASTRONOMICAL, "down")
    astro_end = _first_crossing(_ASTRONOMICAL, "up")
    nautical_start = _first_crossing(_NAUTICAL, "up")
    civil_start = _first_crossing(_CIVIL, "up")
    sunrise = _first_crossing(_HORIZON, "up")
    return (
        sunset,
        civil_end,
        nautical_end,
        astro_start,
        astro_end,
        nautical_start,
        civil_start,
        sunrise,
    )


def _twilight_bands(
    location: PlannerLocation,
    night_date: date,
    earth_loc: EarthLocation,
) -> tuple[TwilightBands, datetime, datetime]:
    """Compute twilight boundaries + the display window bounds.

    Display window is 30 minutes before civil dusk to 30 minutes after
    civil dawn, or — when twilight doesn't fully resolve — falls back to
    civil dusk/dawn from whichever endpoints exist. Returns
    ``(bands, window_start, window_end)``.
    """
    tz = ZoneInfo(location.timezone)
    noon_local = datetime(night_date.year, night_date.month, night_date.day, 12, 0, 0, tzinfo=tz)
    noon_next = noon_local + timedelta(hours=24)
    t0 = Time(noon_local.astimezone(UTC))
    total_sec = (noon_next - noon_local).total_seconds()
    offsets = TimeDelta(np.linspace(0.0, total_sec, _SUN_SAMPLES_PER_DAY), format="sec")
    sun_times = t0 + offsets
    sun = get_body("sun", sun_times, earth_loc)
    sun_alt = np.asarray(sun.transform_to(AltAz(obstime=sun_times, location=earth_loc)).alt.deg)

    (
        sunset,
        civil_end,
        nautical_end,
        astro_start,
        astro_end,
        nautical_start,
        civil_start,
        sunrise,
    ) = _find_sun_crossings(sun_alt, sun_times)

    bands = TwilightBands(
        sunset_utc=sunset,
        civil_end_utc=civil_end,
        nautical_end_utc=nautical_end,
        astro_start_utc=astro_start,
        astro_end_utc=astro_end,
        nautical_start_utc=nautical_start,
        civil_start_utc=civil_start,
        sunrise_utc=sunrise,
    )

    # Display window — pad by 30 minutes around civil dusk/dawn so the
    # graph shows a little context before and after full twilight.
    start_candidate = civil_end or sunset or noon_local.astimezone(UTC)
    end_candidate = civil_start or sunrise or noon_next.astimezone(UTC)
    window_start = start_candidate - timedelta(minutes=30)
    window_end = end_candidate + timedelta(minutes=30)
    return bands, window_start, window_end


def compute_sky_track(
    location: PlannerLocation,
    night_date: date,
    dso: SkyCoord | tuple[int, float, float],
    *,
    flat_min_altitude_deg: float,
) -> SkyTrack:
    """Compute a high-resolution sky track for one DSO.

    ``dso`` may be a pre-built ``SkyCoord`` (tests) or a
    ``(dso_id, ra_deg, dec_deg)`` tuple (API callers). Returns a single
    ``SkyTrack`` suitable for plotting in the detail panel.
    """
    if isinstance(dso, tuple):
        dso_id, ra_deg, dec_deg = dso
        coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    else:
        # Tests can pass a prebuilt SkyCoord; dso_id defaults to 0.
        dso_id = 0
        coord = dso

    earth_loc = _make_earth_location(location)
    bands, window_start, window_end = _twilight_bands(location, night_date, earth_loc)

    # Time grid across the display window.
    total_sec = (window_end - window_start).total_seconds()
    n_samples = max(2, int(total_sec / 60.0 / _SAMPLE_MINUTES) + 1)
    t0 = Time(window_start)
    offsets = TimeDelta(np.linspace(0.0, total_sec, n_samples), format="sec")
    times = t0 + offsets

    altaz_frame = AltAz(obstime=times, location=earth_loc)
    obj_altaz = coord.transform_to(altaz_frame)
    obj_alt = np.asarray(obj_altaz.alt.deg)
    obj_az = np.asarray(obj_altaz.az.deg)

    moon = get_body("moon", times, earth_loc)
    moon_altaz = moon.transform_to(altaz_frame)
    moon_alt = np.asarray(moon_altaz.alt.deg)

    if location.horizon_points:
        horizon_alt = interpolate_horizon_altitude(location.horizon_points, obj_az)
    else:
        horizon_alt = np.full_like(obj_alt, flat_min_altitude_deg)

    tz = ZoneInfo(location.timezone)
    midnight_local = datetime(
        night_date.year, night_date.month, night_date.day, 0, 0, 0, tzinfo=tz
    ) + timedelta(hours=24)
    moon_phase = compute_illumination_pct(Time(midnight_local.astimezone(UTC)))

    times_utc = [t.to_datetime(timezone=UTC) for t in times]

    # Transit = meridian crossing. Compute Hour Angle from Local Apparent
    # Sidereal Time at each sample: HA = LST − RA, wrapped to (−180, 180].
    # Transit is the first ascending sign change of HA; None when HA never
    # crosses zero in the window (object transits during daylight).
    lst_hours = np.asarray(
        times.sidereal_time("apparent", longitude=location.longitude_deg * u.deg).hour
    )
    lst_deg = lst_hours * 15.0
    ra_deg_val = float(coord.ra.deg)
    ha = (lst_deg - ra_deg_val + 180.0) % 360.0 - 180.0

    transit_time_utc: datetime | None = None
    transit_alt_interp: float | None = None
    for i in range(len(ha) - 1):
        a, b = float(ha[i]), float(ha[i + 1])
        # Positive-going crossing from east (HA<0) to west (HA>0).
        # Reject ±180° wrap-arounds via a step-size bound — adjacent
        # 5-minute samples advance HA by ~1.25°.
        if a <= 0 < b and (b - a) < 90.0:
            # The `a <= 0 < b` guard guarantees (b - a) > 0.
            frac = -a / (b - a)
            dt = (times_utc[i + 1] - times_utc[i]).total_seconds()
            transit_time_utc = times_utc[i] + timedelta(seconds=frac * dt)
            # Interpolate altitude at the crossing too — same fraction.
            transit_alt_interp = float(obj_alt[i]) + frac * (
                float(obj_alt[i + 1]) - float(obj_alt[i])
            )
            break

    # Peak is the highest altitude the object reaches inside the window.
    # When transit falls in-window the two are the same physical point,
    # so reuse the interpolated transit values — otherwise the dot
    # snaps to a 5-minute sample while the meridian line is sub-minute
    # precise, and they'll visibly drift.
    if transit_time_utc is not None and transit_alt_interp is not None:
        peak_time = transit_time_utc
        peak_altitude = transit_alt_interp
    else:
        peak_idx = int(np.argmax(obj_alt))
        peak_time = times_utc[peak_idx]
        peak_altitude = float(obj_alt[peak_idx])

    return SkyTrack(
        dso_id=dso_id,
        times_utc=times_utc,
        object_altitude_deg=[round(float(v), 2) for v in obj_alt],
        object_azimuth_deg=[round(float(v), 2) for v in obj_az],
        moon_altitude_deg=[round(float(v), 2) for v in moon_alt],
        horizon_altitude_at_object_az=[round(float(v), 2) for v in horizon_alt],
        twilight=bands,
        moon_phase_pct=moon_phase,
        peak_time_utc=peak_time,
        peak_altitude_deg=round(peak_altitude, 2),
        transit_time_utc=transit_time_utc,
    )
