"""Pure-Python helpers for the Calculators feature.

No FastAPI / DB imports — only astropy and stdlib. Functions here are unit-tested
directly and are composed from the `api/calculators.py` router.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import astropy.units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time

# ── Angular units ────────────────────────────────────────────────────────────

ANGULAR_UNITS: tuple[str, ...] = ("rad", "deg", "arcmin", "arcsec", "mas")

# All stored internally as a multiplier that converts 1 <unit> -> <degrees>.
_ANGULAR_TO_DEG: dict[str, float] = {
    "deg": 1.0,
    "rad": 180.0 / math.pi,
    "arcmin": 1.0 / 60.0,
    "arcsec": 1.0 / 3600.0,
    "mas": 1.0 / 3_600_000.0,
}


# ── Linear units ─────────────────────────────────────────────────────────────

LINEAR_UNITS: tuple[str, ...] = (
    "nm",
    "um",
    "mm",
    "cm",
    "m",
    "in",
    "ft",
    "yd",
    "km",
    "mi",
    "nmi",
    "au",
    "ly",
    "pc",
    "kpc",
    "mpc",
)

_PC_M = 3.0856775814913673e16  # parsec in meters

# Multiplier that converts 1 <unit> -> <meters>.
_LINEAR_TO_M: dict[str, float] = {
    "nm": 1e-9,
    "um": 1e-6,
    "mm": 1e-3,
    "cm": 1e-2,
    "m": 1.0,
    "km": 1e3,
    "in": 0.0254,
    "ft": 0.3048,
    "yd": 0.9144,
    "mi": 1609.344,
    "nmi": 1852.0,
    "au": 1.495978707e11,
    "ly": 9.4607304725808e15,
    "pc": _PC_M,
    "kpc": 1e3 * _PC_M,
    "mpc": 1e6 * _PC_M,
}


def convert_angular(value: float, from_unit: str, to_unit: str) -> float:
    """Convert an angular value between units."""
    if from_unit not in _ANGULAR_TO_DEG:
        raise ValueError(f"Unknown angular unit: {from_unit}")
    if to_unit not in _ANGULAR_TO_DEG:
        raise ValueError(f"Unknown angular unit: {to_unit}")
    deg = value * _ANGULAR_TO_DEG[from_unit]
    return deg / _ANGULAR_TO_DEG[to_unit]


def angular_all_units(value: float, from_unit: str) -> dict[str, float]:
    """Convert value to every angular unit and return the dict."""
    return {unit: convert_angular(value, from_unit, unit) for unit in ANGULAR_UNITS}


def convert_linear(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a linear value between units."""
    if from_unit not in _LINEAR_TO_M:
        raise ValueError(f"Unknown linear unit: {from_unit}")
    if to_unit not in _LINEAR_TO_M:
        raise ValueError(f"Unknown linear unit: {to_unit}")
    meters = value * _LINEAR_TO_M[from_unit]
    return meters / _LINEAR_TO_M[to_unit]


def linear_all_units(value: float, from_unit: str) -> dict[str, float]:
    """Convert value to every linear unit and return the dict."""
    return {unit: convert_linear(value, from_unit, unit) for unit in LINEAR_UNITS}


# ── Lat/Lon parsing ──────────────────────────────────────────────────────────

# Accept ° (U+00B0), prime (U+2032), double-prime (U+2033), straight quotes.
_DEG_CHARS = "\u00b0d"
_MIN_CHARS = "\u2032'\u2019m"
_SEC_CHARS = '\u2033"\u201ds'
_DIRECTIONS = {"N", "S", "E", "W"}


def _strip_direction(text: str) -> tuple[str, str | None]:
    """Extract N/S/E/W if present at start or end; return (rest, direction)."""
    text = text.strip()
    if not text:
        return text, None
    last = text[-1].upper()
    if last in _DIRECTIONS:
        return text[:-1].strip(), last
    first = text[0].upper()
    if first in _DIRECTIONS and len(text) > 1 and not text[1].isalpha():
        return text[1:].strip(), first
    return text, None


def _tokenize_angle(body: str) -> list[float]:
    """Split an angle body (no direction) into numeric tokens.

    Tolerates `° ′ ″`, `d m s`, quotes, whitespace, and commas.
    """
    # Replace unit markers with spaces
    cleaned = body
    for ch in _DEG_CHARS + _MIN_CHARS + _SEC_CHARS:
        cleaned = cleaned.replace(ch, " ")
    # Split on whitespace / commas
    parts = re.split(r"[\s,]+", cleaned.strip())
    parts = [p for p in parts if p]
    out: list[float] = []
    for p in parts:
        out.append(float(p))
    return out


def parse_latlon_string(text: str, kind: str) -> float:
    """Parse a latitude or longitude string into decimal degrees.

    `kind` is "lat" or "lon" and only affects the allowed range.
    Raises ValueError if the string can't be parsed or is out of range.
    """
    if not text or not text.strip():
        raise ValueError("Empty value")

    body, direction = _strip_direction(text)
    if not body:
        raise ValueError("No numeric value")

    # A leading sign plus a direction is ambiguous.
    sign = 1.0
    if body.startswith("-"):
        sign = -1.0
        body = body[1:].strip()
    elif body.startswith("+"):
        body = body[1:].strip()

    tokens = _tokenize_angle(body)
    if not tokens:
        raise ValueError("No numeric components")
    if len(tokens) > 3:
        raise ValueError("Too many components (expected deg / min / sec)")

    degrees = tokens[0]
    minutes = tokens[1] if len(tokens) > 1 else 0.0
    seconds = tokens[2] if len(tokens) > 2 else 0.0

    if minutes < 0 or seconds < 0:
        raise ValueError("Minutes and seconds must be non-negative")
    if minutes >= 60 or seconds >= 60:
        raise ValueError("Minutes and seconds must be < 60")

    # Pure-decimal shortcut: if only one token and it has a fractional part,
    # tokens[0] already carries the full value. The minutes/seconds calculation
    # below correctly yields the same value when those are zero.
    magnitude = abs(degrees) + minutes / 60.0 + seconds / 3600.0
    # Preserve the explicit sign if the user wrote `-33 27 54`.
    if degrees < 0:
        magnitude = -magnitude
    else:
        magnitude = sign * magnitude

    if direction:
        if kind == "lat" and direction not in {"N", "S"}:
            raise ValueError(f"Invalid latitude direction: {direction}")
        if kind == "lon" and direction not in {"E", "W"}:
            raise ValueError(f"Invalid longitude direction: {direction}")
        # Direction overrides sign for a positive magnitude; if the user wrote
        # "-33 N" we treat that as a contradiction.
        if magnitude < 0 and direction in {"N", "E"}:
            raise ValueError("Negative value conflicts with direction")
        if magnitude < 0 and direction in {"S", "W"}:
            # "-33 S" is redundant but not wrong — keep the magnitude.
            pass
        else:
            magnitude = abs(magnitude)
            if direction in {"S", "W"}:
                magnitude = -magnitude

    if kind == "lat":
        if not -90.0 <= magnitude <= 90.0:
            raise ValueError(f"Latitude out of range: {magnitude}")
    else:
        if not -180.0 <= magnitude <= 180.0:
            raise ValueError(f"Longitude out of range: {magnitude}")

    return magnitude


def parse_latlon_components(
    deg: float | None,
    minute: float | None,
    second: float | None,
    direction: str | None,
    kind: str,
) -> float:
    """Assemble decimal degrees from explicit deg/min/sec + direction."""
    if deg is None:
        raise ValueError("Degrees required")
    degrees = float(deg)
    minutes = float(minute) if minute is not None else 0.0
    seconds = float(second) if second is not None else 0.0
    if minutes < 0 or seconds < 0:
        raise ValueError("Minutes and seconds must be non-negative")
    if minutes >= 60 or seconds >= 60:
        raise ValueError("Minutes and seconds must be < 60")

    magnitude = abs(degrees) + minutes / 60.0 + seconds / 3600.0
    if degrees < 0:
        magnitude = -magnitude

    if direction:
        direction = direction.upper()
        if kind == "lat" and direction not in {"N", "S"}:
            raise ValueError(f"Invalid latitude direction: {direction}")
        if kind == "lon" and direction not in {"E", "W"}:
            raise ValueError(f"Invalid longitude direction: {direction}")
        magnitude = abs(magnitude)
        if direction in {"S", "W"}:
            magnitude = -magnitude

    if kind == "lat" and not -90.0 <= magnitude <= 90.0:
        raise ValueError(f"Latitude out of range: {magnitude}")
    if kind == "lon" and not -180.0 <= magnitude <= 180.0:
        raise ValueError(f"Longitude out of range: {magnitude}")
    return magnitude


# ── Airmass ──────────────────────────────────────────────────────────────────

# Default reference altitudes in degrees for the airmass UI table.
AIRMASS_REFERENCE_ALTITUDES: tuple[float, ...] = (10.0, 20.0, 30.0, 45.0, 60.0, 90.0)


def kasten_young_airmass(altitude_deg: float) -> float | None:
    """Kasten-Young (1989) airmass. Returns None below the horizon."""
    if altitude_deg <= 0.0:
        return None
    z = 90.0 - altitude_deg
    z_rad = math.radians(z)
    denom = math.cos(z_rad) + 0.50572 * (6.07995 + 90.0 - z) ** -1.6364
    return 1.0 / denom


# ── RA/Dec ⇄ Alt/Az ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AltAzResult:
    ra_deg: float
    dec_deg: float
    alt_deg: float
    az_deg: float
    airmass: float | None
    below_horizon: bool


def _parse_timestamp(ts: str | None) -> Time:
    """Parse an ISO timestamp (or default to now UTC) into astropy Time."""
    if ts is None:
        return Time(datetime.now(tz=UTC))
    # datetime.fromisoformat handles "YYYY-MM-DDTHH:MM:SS[+-HH:MM|Z]" on 3.14
    iso = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return Time(dt)


def radec_to_altaz(
    ra_deg: float,
    dec_deg: float,
    latitude: float,
    longitude: float,
    elevation_m: float | None,
    timestamp_iso: str | None,
) -> AltAzResult:
    """Forward transform: RA/Dec (ICRS) → Alt/Az at location and time."""
    time = _parse_timestamp(timestamp_iso)
    loc = EarthLocation(
        lat=latitude * u.deg,
        lon=longitude * u.deg,
        height=(elevation_m or 0.0) * u.m,
    )
    sky = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    altaz = sky.transform_to(AltAz(obstime=time, location=loc))
    alt = float(altaz.alt.deg)
    az = float(altaz.az.deg)
    airmass = kasten_young_airmass(alt)
    return AltAzResult(
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        alt_deg=alt,
        az_deg=az,
        airmass=airmass,
        below_horizon=alt <= 0.0,
    )


def altaz_to_radec(
    alt_deg: float,
    az_deg: float,
    latitude: float,
    longitude: float,
    elevation_m: float | None,
    timestamp_iso: str | None,
) -> AltAzResult:
    """Reverse transform: Alt/Az → RA/Dec (ICRS) at location and time."""
    time = _parse_timestamp(timestamp_iso)
    loc = EarthLocation(
        lat=latitude * u.deg,
        lon=longitude * u.deg,
        height=(elevation_m or 0.0) * u.m,
    )
    altaz_frame = AltAz(obstime=time, location=loc)
    sky_altaz = SkyCoord(alt=alt_deg * u.deg, az=az_deg * u.deg, frame=altaz_frame)
    icrs = sky_altaz.transform_to("icrs")
    airmass = kasten_young_airmass(alt_deg)
    return AltAzResult(
        ra_deg=float(icrs.ra.deg),
        dec_deg=float(icrs.dec.deg),
        alt_deg=alt_deg,
        az_deg=az_deg,
        airmass=airmass,
        below_horizon=alt_deg <= 0.0,
    )


# ── Sidereal time ────────────────────────────────────────────────────────────


def local_sidereal_time(longitude: float, timestamp_iso: str | None) -> tuple[float, str, str]:
    """Compute apparent local sidereal time.

    Returns (lst_hours, lst_hms_string, utc_iso_string).
    """
    time = _parse_timestamp(timestamp_iso)
    lst = time.sidereal_time("apparent", longitude=longitude * u.deg)
    hours = float(lst.hour) % 24.0

    total_seconds = hours * 3600.0
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = int(round(total_seconds % 60))
    # Handle 60-second rollover from rounding
    if s == 60:
        s = 0
        m += 1
    if m == 60:
        m = 0
        h = (h + 1) % 24
    hms = f"{h:02d}:{m:02d}:{s:02d}"

    utc_dt = time.to_datetime(timezone=UTC)
    return hours, hms, utc_dt.isoformat()


# ── Optical calculators ──────────────────────────────────────────────────────


def pixel_scale(
    focal_length_mm: float,
    pixel_size_um: float,
    reducer: float = 1.0,
) -> tuple[float, float]:
    """Return (arcsec_per_pixel, effective_focal_length_mm)."""
    if focal_length_mm <= 0 or pixel_size_um <= 0 or reducer <= 0:
        raise ValueError("focal length, pixel size, and reducer must be positive")
    effective_focal = focal_length_mm * reducer
    arcsec_per_pixel = (pixel_size_um / effective_focal) * 206.265
    return arcsec_per_pixel, effective_focal


@dataclass(frozen=True)
class FovResult:
    width_deg: float
    height_deg: float
    width_arcmin: float
    height_arcmin: float
    diagonal_deg: float
    diagonal_arcmin: float


def field_of_view(
    focal_length_mm: float,
    sensor_width_mm: float,
    sensor_height_mm: float,
) -> FovResult:
    """Compute FOV from focal length and physical sensor dimensions."""
    if focal_length_mm <= 0 or sensor_width_mm <= 0 or sensor_height_mm <= 0:
        raise ValueError("focal length and sensor dimensions must be positive")
    w_rad = 2.0 * math.atan(sensor_width_mm / (2.0 * focal_length_mm))
    h_rad = 2.0 * math.atan(sensor_height_mm / (2.0 * focal_length_mm))
    w_deg = math.degrees(w_rad)
    h_deg = math.degrees(h_rad)
    diag_deg = math.sqrt(w_deg * w_deg + h_deg * h_deg)
    return FovResult(
        width_deg=w_deg,
        height_deg=h_deg,
        width_arcmin=w_deg * 60.0,
        height_arcmin=h_deg * 60.0,
        diagonal_deg=diag_deg,
        diagonal_arcmin=diag_deg * 60.0,
    )


def sensor_from_pixels(
    pixel_count_x: int,
    pixel_count_y: int,
    pixel_size_um: float,
) -> tuple[float, float]:
    """Sensor dimensions (mm) from pixel counts and pixel size in um."""
    if pixel_count_x <= 0 or pixel_count_y <= 0 or pixel_size_um <= 0:
        raise ValueError("pixel counts and pixel size must be positive")
    width_mm = pixel_count_x * pixel_size_um / 1000.0
    height_mm = pixel_count_y * pixel_size_um / 1000.0
    return width_mm, height_mm


# ── File size ────────────────────────────────────────────────────────────────


def format_bytes(num_bytes: float) -> str:
    """Format a byte count as a human-readable string with 2 decimal places."""
    if num_bytes < 0:
        return f"-{format_bytes(-num_bytes)}"
    suffixes = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(num_bytes)
    for suffix in suffixes:
        if value < 1024.0 or suffix == suffixes[-1]:
            return f"{value:.2f} {suffix}"
        value /= 1024.0
    return f"{value:.2f} PB"


# ── SQM / Bortle / NELM ──────────────────────────────────────────────────────

# (bortle_class, sqm_lower_inclusive, sqm_upper_exclusive, midpoint)
# Midpoints used for bortle→SQM direction.
_BORTLE_BANDS: tuple[tuple[int, float, float, float], ...] = (
    (1, 21.99, math.inf, 22.0),
    (2, 21.89, 21.99, 21.94),
    (3, 21.69, 21.89, 21.79),
    (4, 20.49, 21.69, 21.09),
    (5, 19.50, 20.49, 19.995),
    (6, 18.95, 19.50, 19.225),
    (7, 18.38, 18.95, 18.665),
    (8, 17.80, 18.38, 18.09),
    (9, -math.inf, 17.80, 17.0),
)


def sqm_to_bortle(sqm: float) -> int:
    """Map an SQM reading to a Bortle class (1–9)."""
    for bortle, lo, hi, _mid in _BORTLE_BANDS:
        if lo <= sqm < hi:
            return bortle
    # Should be unreachable; highest band has +inf upper, lowest has -inf lower.
    return 9 if sqm < 17.80 else 1


def bortle_to_sqm(bortle: int) -> float:
    """Map a Bortle class (1–9) to the midpoint SQM of the band."""
    for b, _lo, _hi, mid in _BORTLE_BANDS:
        if b == bortle:
            return mid
    raise ValueError(f"Bortle out of range: {bortle}")


def sqm_to_nelm(sqm: float) -> float:
    """NELM from SQM using the standard Schaefer-style empirical formula.

    NELM = 7.93 − 5 × log10(10^(4.316 − SQM/5) + 1)
    """
    return 7.93 - 5.0 * math.log10(10.0 ** (4.316 - sqm / 5.0) + 1.0)


def nelm_to_sqm(nelm: float) -> float:
    """Invert NELM→SQM by bisection on [16, 22]. Monotonic in that range."""
    lo, hi = 16.0, 22.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if sqm_to_nelm(mid) < nelm:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# ── Temperature ──────────────────────────────────────────────────────────────


def temperature_all(value: float, from_unit: str) -> tuple[float, float, float]:
    """Return (celsius, fahrenheit, kelvin) for the given input."""
    unit = from_unit.upper()
    if unit == "C":
        c = value
    elif unit == "F":
        c = (value - 32.0) * 5.0 / 9.0
    elif unit == "K":
        c = value - 273.15
    else:
        raise ValueError(f"Unknown temperature unit: {from_unit}")
    f = c * 9.0 / 5.0 + 32.0
    k = c + 273.15
    return c, f, k
