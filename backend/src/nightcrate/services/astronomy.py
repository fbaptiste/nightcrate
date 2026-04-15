"""Astronomy service — moon, twilight, darkness computations.

Pure computation module using astropy. No DB, no HTTP, no FastAPI imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import astropy.units as u
import numpy as np
from astropy.coordinates import AltAz, EarthLocation, get_body
from astropy.time import Time, TimeDelta

# ── Sun altitude thresholds (degrees) ────────────────────────────────────────

_HORIZON = -0.833  # geometric horizon with refraction correction
_CIVIL = -6.0
_NAUTICAL = -12.0
_ASTRONOMICAL = -18.0

# ── Sampling resolution ─────────────────────────────────────────────────────

_DENSE_SAMPLES = 1440  # 1-minute resolution over 24h for horizon crossings
_MOONLESS_INTERVAL_MIN = 5  # minutes between moon altitude samples
_MOON_POLYLINE_INTERVAL_MIN = 2  # minutes between moon polyline samples


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MoonInfo:
    """Moon phase and rise/set information for a given night."""

    illumination_pct: float  # 0–100
    elongation_deg: float  # sun-moon angular separation as seen from Earth
    phase_name: str  # one of 8 standard names
    moonrise: str | None  # HH:MM local or None
    moonset: str | None  # HH:MM local or None


@dataclass(frozen=True)
class DarknessWindow:
    """Twilight boundary times (all UTC datetimes). All fields optional for polar latitudes."""

    civil_end: datetime | None  # evening: sun crosses -6°
    nautical_end: datetime | None  # evening: sun crosses -12°
    astro_start: datetime | None  # evening: sun crosses -18° (darkness begins)
    astro_end: datetime | None  # morning: sun crosses -18° (darkness ends)
    nautical_start: datetime | None  # morning: sun crosses -12°
    civil_start: datetime | None  # morning: sun crosses -6°


@dataclass(frozen=True)
class NightSummary:
    """Complete summary of astronomical conditions for one night."""

    sunset: datetime | None  # UTC
    sunrise: datetime | None  # UTC
    darkness: DarknessWindow
    darkness_hours: float  # hours of deepest available darkness
    moonless_dark_hours: float  # hours of darkness with moon below horizon
    moon: MoonInfo
    deepest_darkness_reached: str  # "astro" | "nautical" | "civil" | "none"
    no_imaging_window: bool  # True when no sunset or no darkness at all


@dataclass(frozen=True)
class HourlyAstro:
    """Astronomical data for one hour of the night."""

    time_utc: datetime
    time_local: str  # HH:MM
    moon_altitude_deg: float
    moon_illumination_pct: float
    darkness_category: str


@dataclass(frozen=True)
class MoonPolylinePoint:
    """One point in the moon altitude polyline."""

    time_utc: str  # ISO format
    altitude_deg: float


# ── Internal helpers ─────────────────────────────────────────────────────────


def _make_location(latitude: float, longitude: float, elevation_m: float | None) -> EarthLocation:
    """Create an EarthLocation, defaulting elevation to 0 if None."""
    elev = elevation_m if elevation_m is not None else 0.0
    return EarthLocation(lat=latitude * u.deg, lon=longitude * u.deg, height=elev * u.m)


def _make_time_grid(start_utc: datetime, end_utc: datetime, n_samples: int) -> Time:
    """Create an evenly-spaced astropy Time array between two UTC datetimes."""
    t_start = Time(start_utc)
    total_sec = (end_utc - start_utc).total_seconds()
    offsets = TimeDelta(np.linspace(0, total_sec, n_samples), format="sec")
    return t_start + offsets


def _sun_altitudes(times: Time, location: EarthLocation) -> np.ndarray:
    """Compute sun altitude in degrees for an array of times."""
    altaz_frame = AltAz(obstime=times, location=location)
    sun = get_body("sun", times, location)
    sun_altaz = sun.transform_to(altaz_frame)
    return np.asarray(sun_altaz.alt.deg)


def _moon_altitudes(times: Time, location: EarthLocation) -> np.ndarray:
    """Compute moon altitude in degrees for an array of times."""
    altaz_frame = AltAz(obstime=times, location=location)
    moon = get_body("moon", times, location)
    moon_altaz = moon.transform_to(altaz_frame)
    return np.asarray(moon_altaz.alt.deg)


def _time_to_utc_datetime(t: Time) -> datetime:
    """Convert an astropy Time scalar to a timezone-aware UTC datetime."""
    return t.to_datetime(timezone=UTC)


def _find_crossing(
    times: Time,
    altitudes: np.ndarray,
    threshold: float,
    direction: str,
    start_idx: int = 0,
) -> datetime | None:
    """Find the first time the altitude crosses the threshold.

    direction: 'down' for descending crossing, 'up' for ascending crossing.
    start_idx: only consider crossings at index >= start_idx.
    Returns UTC datetime or None if no crossing found.
    """
    if direction == "down":
        above = altitudes > threshold
        crossings = np.where(above[:-1] & ~above[1:])[0]
    else:
        below = altitudes < threshold
        crossings = np.where(below[:-1] & ~below[1:])[0]

    # Filter to crossings at or after start_idx
    crossings = crossings[crossings >= start_idx]

    if len(crossings) == 0:
        return None

    idx = int(crossings[0])
    # Linear interpolation between adjacent samples
    alt0 = float(altitudes[idx])
    alt1 = float(altitudes[idx + 1])
    frac = (threshold - alt0) / (alt1 - alt0)

    t0 = times[idx]
    dt = (times[idx + 1] - times[idx]).sec  # seconds between samples
    crossing_time = t0 + TimeDelta(frac * dt, format="sec")
    return _time_to_utc_datetime(crossing_time)


def _find_crossing_after(
    times: Time,
    altitudes: np.ndarray,
    threshold: float,
    direction: str,
    after: datetime | None,
) -> datetime | None:
    """Find the first crossing after a given datetime. Returns None if after is None."""
    if after is None:
        return None
    after_time = Time(after)
    # Find the first index where time > after
    dt_array = (times - after_time).sec
    valid = np.where(np.asarray(dt_array) > 0)[0]
    if len(valid) == 0:
        return None
    start_idx = int(valid[0])
    return _find_crossing(times, altitudes, threshold, direction, start_idx=start_idx)


def _find_crossing_independent(
    times: Time,
    altitudes: np.ndarray,
    threshold: float,
    direction: str,
) -> datetime | None:
    """Find a crossing independently (not relative to another event)."""
    return _find_crossing(times, altitudes, threshold, direction, start_idx=0)


def _moon_phase_info(time: Time, location: EarthLocation) -> MoonInfo:
    """Compute moon phase information at a given time.

    Uses the Meeus method: compute the phase angle i (Sun-Moon-Earth angle)
    from 3D geocentric positions, then illumination = (1 + cos(i)) / 2.
    """
    from astropy.coordinates import get_body_barycentric

    sun = get_body("sun", time, location)
    moon = get_body("moon", time, location)

    # Phase angle (i): the angle at the Moon between Sun and Earth.
    sun_pos = get_body_barycentric("sun", time).get_xyz().to(u.km).value
    moon_pos = get_body_barycentric("moon", time).get_xyz().to(u.km).value
    earth_pos = get_body_barycentric("earth", time).get_xyz().to(u.km).value

    # Vectors from the Moon's perspective
    moon_to_sun = sun_pos - moon_pos
    moon_to_earth = earth_pos - moon_pos

    # Phase angle via dot product
    cos_i = np.dot(moon_to_sun, moon_to_earth) / (
        np.linalg.norm(moon_to_sun) * np.linalg.norm(moon_to_earth)
    )
    cos_i = np.clip(cos_i, -1.0, 1.0)

    # Illumination fraction (Meeus formula)
    illumination_pct = float((1.0 + cos_i) / 2.0 * 100.0)

    # Elongation (angular separation as seen from Earth)
    elongation_deg = float(sun.separation(moon).deg)

    # Waxing vs waning from ecliptic longitude difference
    sun_ecl = sun.geocentricmeanecliptic
    moon_ecl = moon.geocentricmeanecliptic
    delta_lon = (moon_ecl.lon - sun_ecl.lon).deg % 360

    phase_name = _phase_name_from_delta_lon(delta_lon)

    return MoonInfo(
        illumination_pct=round(illumination_pct, 1),
        elongation_deg=round(elongation_deg, 1),
        phase_name=phase_name,
        moonrise=None,  # filled in by caller
        moonset=None,  # filled in by caller
    )


def _phase_name_from_delta_lon(delta_lon: float) -> str:
    """Map ecliptic longitude difference to one of 8 standard phase names."""
    if delta_lon < 22.5:
        return "New Moon"
    if delta_lon < 67.5:
        return "Waxing Crescent"
    if delta_lon < 112.5:
        return "First Quarter"
    if delta_lon < 157.5:
        return "Waxing Gibbous"
    if delta_lon < 202.5:
        return "Full Moon"
    if delta_lon < 247.5:
        return "Waning Gibbous"
    if delta_lon < 292.5:
        return "Last Quarter"
    if delta_lon < 337.5:
        return "Waning Crescent"
    return "New Moon"


def _moon_rise_set(
    times: Time,
    location: EarthLocation,
    tz: ZoneInfo,
) -> tuple[str | None, str | None]:
    """Find moonrise and moonset times within the time window."""
    moon_alts = _moon_altitudes(times, location)

    rise_dt = _find_crossing(times, moon_alts, _HORIZON, direction="up")
    set_dt = _find_crossing(times, moon_alts, _HORIZON, direction="down")

    rise_str = rise_dt.astimezone(tz).strftime("%H:%M") if rise_dt else None
    set_str = set_dt.astimezone(tz).strftime("%H:%M") if set_dt else None

    return rise_str, set_str


def _compute_moonless_dark_hours(
    dark_start: datetime,
    dark_end: datetime,
    location: EarthLocation,
) -> float:
    """Count hours of darkness with moon below horizon.

    Samples moon altitude every _MOONLESS_INTERVAL_MIN minutes.
    """
    total_minutes = (dark_end - dark_start).total_seconds() / 60.0
    n_samples = max(1, int(total_minutes / _MOONLESS_INTERVAL_MIN) + 1)

    sample_times = _make_time_grid(dark_start, dark_end, n_samples)
    moon_alts = _moon_altitudes(sample_times, location)
    below_horizon = np.sum(moon_alts < _HORIZON)

    return float(below_horizon / n_samples * total_minutes / 60.0)


def _classify_darkness(sun_alt: float) -> str:
    """Classify the darkness category from sun altitude."""
    if sun_alt > _HORIZON:
        return "daylight"
    if sun_alt > _CIVIL:
        return "civil_twilight"
    if sun_alt > _NAUTICAL:
        return "nautical_twilight"
    if sun_alt > _ASTRONOMICAL:
        return "astronomical_twilight"
    return "night"


def _determine_deepest_darkness(darkness: DarknessWindow) -> str:
    """Determine the deepest darkness level reached."""
    if darkness.astro_start is not None and darkness.astro_end is not None:
        return "astro"
    if darkness.nautical_end is not None and darkness.nautical_start is not None:
        return "nautical"
    if darkness.civil_end is not None and darkness.civil_start is not None:
        return "civil"
    return "none"


def _get_darkness_window_times(
    darkness: DarknessWindow,
    deepest: str,
) -> tuple[datetime | None, datetime | None]:
    """Get the start/end times for the deepest available darkness level."""
    if deepest == "astro":
        return darkness.astro_start, darkness.astro_end
    if deepest == "nautical":
        return darkness.nautical_end, darkness.nautical_start
    if deepest == "civil":
        return darkness.civil_end, darkness.civil_start
    return None, None


# ── Public API ───────────────────────────────────────────────────────────────


def compute_night_summary(
    latitude: float,
    longitude: float,
    elevation_m: float | None,
    night_date: date,
    timezone_str: str,
) -> NightSummary:
    """Compute a full night summary: sunset/sunrise, twilight, moon, darkness.

    The "night" spans from evening of night_date to morning of night_date + 1.
    Search window is local noon to local noon.

    Handles polar latitudes gracefully — if certain twilight crossings don't
    occur, those fields are None instead of raising.
    """
    tz = ZoneInfo(timezone_str)
    location = _make_location(latitude, longitude, elevation_m)

    # Search window: local noon on night_date to local noon on night_date + 1
    noon_local = datetime(night_date.year, night_date.month, night_date.day, 12, 0, 0, tzinfo=tz)
    noon_next = noon_local + timedelta(hours=24)

    noon_utc = noon_local.astimezone(UTC)
    noon_next_utc = noon_next.astimezone(UTC)

    # Dense time samples for crossing detection
    times = _make_time_grid(noon_utc, noon_next_utc, _DENSE_SAMPLES)
    sun_alts = _sun_altitudes(times, location)

    # Find sunset and sunrise independently
    sunset = _find_crossing_independent(times, sun_alts, _HORIZON, direction="down")
    sunrise = _find_crossing_after(times, sun_alts, _HORIZON, direction="up", after=sunset)

    # Evening twilight boundaries (descending, each independently after sunset)
    civil_end = _find_crossing_after(times, sun_alts, _CIVIL, direction="down", after=sunset)
    nautical_end = _find_crossing_after(
        times,
        sun_alts,
        _NAUTICAL,
        direction="down",
        after=civil_end,
    )
    astro_start = _find_crossing_after(
        times,
        sun_alts,
        _ASTRONOMICAL,
        direction="down",
        after=nautical_end,
    )

    # Morning twilight boundaries (ascending)
    # For astro_end, search after astro_start if available, else after nautical_end
    astro_end = _find_crossing_after(
        times,
        sun_alts,
        _ASTRONOMICAL,
        direction="up",
        after=astro_start,
    )
    nautical_start = _find_crossing_after(
        times,
        sun_alts,
        _NAUTICAL,
        direction="up",
        after=astro_end if astro_end is not None else nautical_end,
    )
    civil_start = _find_crossing_after(
        times,
        sun_alts,
        _CIVIL,
        direction="up",
        after=nautical_start if nautical_start is not None else civil_end,
    )

    darkness = DarknessWindow(
        civil_end=civil_end,
        nautical_end=nautical_end,
        astro_start=astro_start,
        astro_end=astro_end,
        nautical_start=nautical_start,
        civil_start=civil_start,
    )

    # Determine deepest darkness and compute hours
    deepest = _determine_deepest_darkness(darkness)
    dark_start, dark_end = _get_darkness_window_times(darkness, deepest)

    if dark_start is not None and dark_end is not None:
        darkness_hours = (dark_end - dark_start).total_seconds() / 3600.0
    else:
        darkness_hours = 0.0

    # No imaging window: no sunset or no darkness at all
    no_imaging_window = sunset is None or deepest == "none"

    # Moon info at midnight local
    midnight_local = datetime(
        night_date.year,
        night_date.month,
        night_date.day,
        0,
        0,
        0,
        tzinfo=tz,
    ) + timedelta(hours=24)
    midnight_utc = midnight_local.astimezone(UTC)
    midnight_time = Time(midnight_utc)

    moon_info = _moon_phase_info(midnight_time, location)

    # Moon rise/set during the night window
    moonrise_str, moonset_str = _moon_rise_set(times, location, tz)
    moon_info = MoonInfo(
        illumination_pct=moon_info.illumination_pct,
        elongation_deg=moon_info.elongation_deg,
        phase_name=moon_info.phase_name,
        moonrise=moonrise_str,
        moonset=moonset_str,
    )

    # Moonless dark hours
    if dark_start is not None and dark_end is not None:
        moonless_dark_hours = _compute_moonless_dark_hours(dark_start, dark_end, location)
    else:
        moonless_dark_hours = 0.0

    return NightSummary(
        sunset=sunset,
        sunrise=sunrise,
        darkness=darkness,
        darkness_hours=round(darkness_hours, 2),
        moonless_dark_hours=round(moonless_dark_hours, 2),
        moon=moon_info,
        deepest_darkness_reached=deepest,
        no_imaging_window=no_imaging_window,
    )


def compute_hourly_astro(
    latitude: float,
    longitude: float,
    elevation_m: float | None,
    night_date: date,
    timezone_str: str,
) -> list[HourlyAstro]:
    """Compute hourly astronomical data from sunset to sunrise.

    Returns one entry per hour covering the full night.
    Returns empty list if no sunset/sunrise occurs (polar conditions).
    """
    tz = ZoneInfo(timezone_str)
    location = _make_location(latitude, longitude, elevation_m)

    # Find sunset and sunrise using dense sampling
    noon_local = datetime(night_date.year, night_date.month, night_date.day, 12, 0, 0, tzinfo=tz)
    noon_next = noon_local + timedelta(hours=24)
    noon_utc = noon_local.astimezone(UTC)
    noon_next_utc = noon_next.astimezone(UTC)

    times_dense = _make_time_grid(noon_utc, noon_next_utc, _DENSE_SAMPLES)
    sun_alts_dense = _sun_altitudes(times_dense, location)

    sunset = _find_crossing_independent(times_dense, sun_alts_dense, _HORIZON, direction="down")
    if sunset is None:
        return []

    sunrise = _find_crossing_after(
        times_dense,
        sun_alts_dense,
        _HORIZON,
        direction="up",
        after=sunset,
    )
    if sunrise is None:
        return []

    # Generate hourly samples from sunset to sunrise
    sunset_local = sunset.astimezone(tz)
    sunrise_local = sunrise.astimezone(tz)

    # Start at the next full hour after sunset
    start_hour = sunset_local.replace(minute=0, second=0, microsecond=0)
    if start_hour < sunset_local:
        start_hour += timedelta(hours=1)

    # End at the hour of sunrise (inclusive)
    end_hour = sunrise_local.replace(minute=0, second=0, microsecond=0)

    hourly_times_local = []
    current = start_hour
    while current <= end_hour:
        hourly_times_local.append(current)
        current += timedelta(hours=1)

    if not hourly_times_local:
        return []

    # Convert to UTC for astropy
    hourly_utc = [t.astimezone(UTC) for t in hourly_times_local]
    astropy_times = Time(hourly_utc)

    # Compute sun and moon positions for all hours at once
    sun_alts = _sun_altitudes(astropy_times, location)
    moon_alts = _moon_altitudes(astropy_times, location)

    # Moon illumination at midnight (constant enough for hourly display)
    midnight_local = datetime(
        night_date.year,
        night_date.month,
        night_date.day,
        0,
        0,
        0,
        tzinfo=tz,
    ) + timedelta(hours=24)
    midnight_utc = midnight_local.astimezone(UTC)
    moon_info = _moon_phase_info(Time(midnight_utc), location)

    results = []
    for i, t_local in enumerate(hourly_times_local):
        results.append(
            HourlyAstro(
                time_utc=hourly_utc[i],
                time_local=t_local.strftime("%H:%M"),
                moon_altitude_deg=round(float(moon_alts[i]), 2),
                moon_illumination_pct=moon_info.illumination_pct,
                darkness_category=_classify_darkness(float(sun_alts[i])),
            )
        )

    return results


def compute_moon_polyline(
    latitude: float,
    longitude: float,
    elevation_m: float | None,
    start_utc: datetime,
    end_utc: datetime,
) -> list[MoonPolylinePoint]:
    """Compute moon altitude at regular intervals for polyline rendering.

    Samples every _MOON_POLYLINE_INTERVAL_MIN minutes between start and end.
    Returns list of (ISO timestamp, altitude_deg) points.
    """
    location = _make_location(latitude, longitude, elevation_m)

    total_minutes = (end_utc - start_utc).total_seconds() / 60.0
    n_samples = max(2, int(total_minutes / _MOON_POLYLINE_INTERVAL_MIN) + 1)

    sample_times = _make_time_grid(start_utc, end_utc, n_samples)
    moon_alts = _moon_altitudes(sample_times, location)

    points = []
    for i in range(n_samples):
        t_dt = _time_to_utc_datetime(sample_times[i])
        points.append(
            MoonPolylinePoint(
                time_utc=t_dt.isoformat(),
                altitude_deg=round(float(moon_alts[i]), 2),
            )
        )

    return points
