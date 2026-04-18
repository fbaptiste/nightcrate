"""Calculators API — astronomy, optical, and unit conversion helpers.

Thin FastAPI wrapper over `services/calculators.py`. Reuses `services/astronomy.py`
for sunset/twilight/moon and `services/coordinate_format.py` for sexagesimal
display.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from nightcrate.db.session import get_db
from nightcrate.services.astronomy import compute_night_summary
from nightcrate.services.calculators import (
    AIRMASS_REFERENCE_ALTITUDES,
    ANGULAR_UNITS,
    LINEAR_UNITS,
    altaz_to_radec,
    angular_all_units,
    bortle_to_sqm,
    convert_angular,
    convert_linear,
    field_of_view,
    format_bytes,
    kasten_young_airmass,
    linear_all_units,
    local_sidereal_time,
    nelm_to_sqm,
    parse_latlon_components,
    parse_latlon_string,
    pixel_scale,
    radec_to_altaz,
    sensor_from_pixels,
    sqm_to_bortle,
    sqm_to_nelm,
    temperature_all,
)
from nightcrate.services.coordinate_format import format_latitude, format_longitude

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calculators", tags=["Calculators"])


AngularUnit = Literal["rad", "deg", "arcmin", "arcsec", "mas"]
LinearUnit = Literal[
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
]
TempUnit = Literal["C", "F", "K"]


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _load_location(location_id: int) -> dict:
    async with get_db() as conn:
        row = await conn.execute("SELECT * FROM location WHERE id = ?", (location_id,))
        result = await row.fetchone()
    if result is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return dict(result)


def _fmt_hhmm(dt: datetime | None, tz: ZoneInfo) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(tz).strftime("%H:%M")


# ── 1. Lat/Lon → Sexagesimal ─────────────────────────────────────────────────


class LatLonDisplayResponse(BaseModel):
    latitude_display: str
    longitude_display: str


@router.get("/lat-long/to-sexagesimal", response_model=LatLonDisplayResponse)
async def lat_long_to_sexagesimal(
    latitude: float = Query(...),
    longitude: float = Query(...),
):
    """Format decimal lat/lon as sexagesimal display strings."""
    try:
        return LatLonDisplayResponse(
            latitude_display=format_latitude(latitude),
            longitude_display=format_longitude(longitude),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── 2. Lat/Lon → Decimal ─────────────────────────────────────────────────────


class LatLonToDecimalRequest(BaseModel):
    latitude: str | None = None
    longitude: str | None = None
    latitude_deg: float | None = None
    latitude_min: float | None = None
    latitude_sec: float | None = None
    latitude_direction: str | None = None
    longitude_deg: float | None = None
    longitude_min: float | None = None
    longitude_sec: float | None = None
    longitude_direction: str | None = None


class LatLonToDecimalResponse(BaseModel):
    latitude: float | None
    longitude: float | None
    latitude_error: str | None
    longitude_error: str | None


def _resolve_latlon_side(
    kind: str,
    string_value: str | None,
    deg: float | None,
    minute: float | None,
    second: float | None,
    direction: str | None,
) -> tuple[float | None, str | None]:
    """Return (value, error). `error` is None on success. Empty inputs → (None, None)."""
    # Component path wins if any numeric component is provided.
    has_components = any(v is not None for v in (deg, minute, second)) or direction is not None
    if has_components:
        try:
            value = parse_latlon_components(deg, minute, second, direction, kind)
        except ValueError as exc:
            return None, str(exc)
        return value, None
    if string_value is None or not string_value.strip():
        return None, None
    try:
        value = parse_latlon_string(string_value, kind)
    except ValueError as exc:
        return None, str(exc)
    return value, None


@router.post("/lat-long/to-decimal", response_model=LatLonToDecimalResponse)
async def lat_long_to_decimal(body: LatLonToDecimalRequest):
    """Parse free-form or component lat/lon input into decimal degrees."""
    lat_value, lat_err = _resolve_latlon_side(
        "lat",
        body.latitude,
        body.latitude_deg,
        body.latitude_min,
        body.latitude_sec,
        body.latitude_direction,
    )
    lon_value, lon_err = _resolve_latlon_side(
        "lon",
        body.longitude,
        body.longitude_deg,
        body.longitude_min,
        body.longitude_sec,
        body.longitude_direction,
    )
    return LatLonToDecimalResponse(
        latitude=lat_value,
        longitude=lon_value,
        latitude_error=lat_err,
        longitude_error=lon_err,
    )


# ── 3. RA/Dec ⇄ Alt/Az ───────────────────────────────────────────────────────


class RaDecAltAzRequest(BaseModel):
    direction: Literal["forward", "reverse"]
    ra_deg: float | None = None
    dec_deg: float | None = None
    alt_deg: float | None = None
    az_deg: float | None = None
    timestamp_iso: str | None = None
    location_id: int


class RaDecAltAzResponse(BaseModel):
    ra_deg: float
    dec_deg: float
    alt_deg: float
    az_deg: float
    airmass: float | None
    below_horizon: bool


@router.post("/radec-altaz", response_model=RaDecAltAzResponse)
async def radec_altaz(body: RaDecAltAzRequest):
    """Forward (RA/Dec→Alt/Az) or reverse transform at a stored location."""
    loc = await _load_location(body.location_id)
    lat = loc["latitude"]
    lon = loc["longitude"]
    elev = loc.get("elevation_m")

    try:
        if body.direction == "forward":
            if body.ra_deg is None or body.dec_deg is None:
                raise HTTPException(
                    status_code=422,
                    detail="ra_deg and dec_deg required for forward transform",
                )
            result = radec_to_altaz(body.ra_deg, body.dec_deg, lat, lon, elev, body.timestamp_iso)
        else:
            if body.alt_deg is None or body.az_deg is None:
                raise HTTPException(
                    status_code=422,
                    detail="alt_deg and az_deg required for reverse transform",
                )
            result = altaz_to_radec(body.alt_deg, body.az_deg, lat, lon, elev, body.timestamp_iso)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RaDecAltAzResponse(
        ra_deg=result.ra_deg,
        dec_deg=result.dec_deg,
        alt_deg=result.alt_deg,
        az_deg=result.az_deg,
        airmass=result.airmass,
        below_horizon=result.below_horizon,
    )


# ── 4. Sidereal time ─────────────────────────────────────────────────────────


class SiderealTimeResponse(BaseModel):
    lst_hours: float
    lst_hms: str
    utc_iso: str


@router.get("/sidereal-time", response_model=SiderealTimeResponse)
async def sidereal_time(
    location_id: int = Query(...),
    timestamp: str | None = Query(None),
):
    """Compute apparent local sidereal time for a stored location."""
    loc = await _load_location(location_id)
    try:
        hours, hms, utc_iso = local_sidereal_time(loc["longitude"], timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SiderealTimeResponse(lst_hours=hours, lst_hms=hms, utc_iso=utc_iso)


# ── 5. Tonight ───────────────────────────────────────────────────────────────


class TonightResponse(BaseModel):
    date: str
    timezone: str
    sunset: str | None
    civil_twilight_end: str | None
    nautical_twilight_end: str | None
    astronomical_twilight_end: str | None
    astronomical_twilight_start: str | None
    nautical_twilight_start: str | None
    civil_twilight_start: str | None
    sunrise: str | None
    moonrise: str | None
    moonset: str | None
    moon_illumination_pct: float
    moon_phase_name: str
    astronomical_dark_hours: float
    moonless_dark_hours: float


@router.get("/tonight", response_model=TonightResponse)
async def tonight(
    location_id: int = Query(...),
    date_: str | None = Query(None, alias="date"),
):
    """Sunset, twilight, moonrise, and darkness summary for a night."""
    loc = await _load_location(location_id)
    astro_tz = loc.get("geo_timezone") or loc["timezone"]
    display_tz_name = loc["timezone"]
    display_tz = ZoneInfo(display_tz_name)

    if date_ is None:
        today = datetime.now(tz=ZoneInfo(astro_tz)).date()
        night_date = today
    else:
        try:
            night_date = date.fromisoformat(date_)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid date: {date_}") from exc

    try:
        night = compute_night_summary(
            latitude=loc["latitude"],
            longitude=loc["longitude"],
            elevation_m=loc.get("elevation_m"),
            night_date=night_date,
            timezone_str=astro_tz,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return TonightResponse(
        date=night_date.isoformat(),
        timezone=display_tz_name,
        sunset=_fmt_hhmm(night.sunset, display_tz),
        civil_twilight_end=_fmt_hhmm(night.darkness.civil_end, display_tz),
        nautical_twilight_end=_fmt_hhmm(night.darkness.nautical_end, display_tz),
        astronomical_twilight_end=_fmt_hhmm(night.darkness.astro_start, display_tz),
        astronomical_twilight_start=_fmt_hhmm(night.darkness.astro_end, display_tz),
        nautical_twilight_start=_fmt_hhmm(night.darkness.nautical_start, display_tz),
        civil_twilight_start=_fmt_hhmm(night.darkness.civil_start, display_tz),
        sunrise=_fmt_hhmm(night.sunrise, display_tz),
        moonrise=night.moon.moonrise,
        moonset=night.moon.moonset,
        moon_illumination_pct=night.moon.illumination_pct,
        moon_phase_name=night.moon.phase_name,
        astronomical_dark_hours=night.darkness_hours,
        moonless_dark_hours=night.moonless_dark_hours,
    )


# ── 6. Angular unit conversion ───────────────────────────────────────────────


class UnitConvertResponse(BaseModel):
    value: float
    from_unit: str
    to_unit: str
    result: float
    all_units: dict[str, float]


@router.get("/angular-units/convert", response_model=UnitConvertResponse)
async def angular_units_convert(
    value: float = Query(...),
    from_: AngularUnit = Query(..., alias="from"),
    to: AngularUnit = Query(...),
):
    """Convert an angle between rad, deg, arcmin, arcsec, and mas."""
    if from_ not in ANGULAR_UNITS or to not in ANGULAR_UNITS:
        raise HTTPException(status_code=422, detail="Unknown angular unit")
    result = convert_angular(value, from_, to)
    return UnitConvertResponse(
        value=value,
        from_unit=from_,
        to_unit=to,
        result=result,
        all_units=angular_all_units(value, from_),
    )


# ── 7. Linear unit conversion ────────────────────────────────────────────────


@router.get("/linear-units/convert", response_model=UnitConvertResponse)
async def linear_units_convert(
    value: float = Query(...),
    from_: LinearUnit = Query(..., alias="from"),
    to: LinearUnit = Query(...),
):
    """Convert a length between metric, imperial, and astronomical units."""
    if from_ not in LINEAR_UNITS or to not in LINEAR_UNITS:
        raise HTTPException(status_code=422, detail="Unknown linear unit")
    result = convert_linear(value, from_, to)
    return UnitConvertResponse(
        value=value,
        from_unit=from_,
        to_unit=to,
        result=result,
        all_units=linear_all_units(value, from_),
    )


# ── 8. Pixel scale ───────────────────────────────────────────────────────────


class PixelScaleResponse(BaseModel):
    arcsec_per_pixel: float
    effective_focal_length_mm: float


@router.get("/pixel-scale", response_model=PixelScaleResponse)
async def pixel_scale_endpoint(
    focal_length_mm: float = Query(..., gt=0),
    pixel_size_um: float = Query(..., gt=0),
    reducer: float = Query(1.0, gt=0),
):
    """Arc-seconds per pixel for a given focal length + pixel size (+ reducer)."""
    try:
        arcsec, eff = pixel_scale(focal_length_mm, pixel_size_um, reducer)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PixelScaleResponse(arcsec_per_pixel=arcsec, effective_focal_length_mm=eff)


# ── 9. Field of view ─────────────────────────────────────────────────────────


class FovResponse(BaseModel):
    width_deg: float
    height_deg: float
    width_arcmin: float
    height_arcmin: float
    diagonal_deg: float
    diagonal_arcmin: float


@router.get("/fov", response_model=FovResponse)
async def fov_endpoint(
    focal_length_mm: float = Query(..., gt=0),
    sensor_width_mm: float | None = Query(None, gt=0),
    sensor_height_mm: float | None = Query(None, gt=0),
    pixel_count_x: int | None = Query(None, gt=0),
    pixel_count_y: int | None = Query(None, gt=0),
    pixel_size_um: float | None = Query(None, gt=0),
):
    """Field of view from a focal length and either sensor dimensions or pixel grid."""
    if sensor_width_mm is not None and sensor_height_mm is not None:
        width_mm = sensor_width_mm
        height_mm = sensor_height_mm
    elif pixel_count_x is not None and pixel_count_y is not None and pixel_size_um is not None:
        try:
            width_mm, height_mm = sensor_from_pixels(pixel_count_x, pixel_count_y, pixel_size_um)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        raise HTTPException(
            status_code=422,
            detail=(
                "Provide either sensor_width_mm + sensor_height_mm, "
                "or pixel_count_x + pixel_count_y + pixel_size_um."
            ),
        )

    try:
        fov = field_of_view(focal_length_mm, width_mm, height_mm)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FovResponse(
        width_deg=fov.width_deg,
        height_deg=fov.height_deg,
        width_arcmin=fov.width_arcmin,
        height_arcmin=fov.height_arcmin,
        diagonal_deg=fov.diagonal_deg,
        diagonal_arcmin=fov.diagonal_arcmin,
    )


# ── 10. File size ────────────────────────────────────────────────────────────


class FileSizeResponse(BaseModel):
    bytes_per_frame: int
    total_bytes: int
    megapixels: float
    per_frame_display: str
    total_display: str


@router.get("/file-size", response_model=FileSizeResponse)
async def file_size_endpoint(
    width: int = Query(..., gt=0),
    height: int = Query(..., gt=0),
    bit_depth: int = Query(16, ge=1),
    frames: int = Query(1, ge=1),
    compression: float = Query(1.0, gt=0),
):
    """Estimate raw pixel footprint for a single frame and a whole session."""
    bytes_per_frame = int(width * height * (bit_depth / 8.0) * compression)
    total_bytes = int(bytes_per_frame * frames)
    megapixels = (width * height) / 1_000_000.0
    return FileSizeResponse(
        bytes_per_frame=bytes_per_frame,
        total_bytes=total_bytes,
        megapixels=megapixels,
        per_frame_display=format_bytes(bytes_per_frame),
        total_display=format_bytes(total_bytes),
    )


# ── 11. Airmass ──────────────────────────────────────────────────────────────


class AirmassReferenceEntry(BaseModel):
    altitude_deg: float
    airmass: float


class AirmassResponse(BaseModel):
    altitude_deg: float
    airmass: float | None
    below_horizon: bool
    reference_table: list[AirmassReferenceEntry]


@router.get("/airmass", response_model=AirmassResponse)
async def airmass_endpoint(
    altitude_deg: float = Query(..., ge=-90, le=90),
):
    """Kasten-Young airmass for a given altitude + a reference table."""
    airmass = kasten_young_airmass(altitude_deg)
    reference = []
    for alt in AIRMASS_REFERENCE_ALTITUDES:
        X = kasten_young_airmass(alt)
        reference.append(
            AirmassReferenceEntry(altitude_deg=alt, airmass=X if X is not None else float("nan"))
        )
    return AirmassResponse(
        altitude_deg=altitude_deg,
        airmass=airmass,
        below_horizon=altitude_deg <= 0.0,
        reference_table=reference,
    )


# ── 12. SQM / Bortle / NELM ──────────────────────────────────────────────────


class SqmBortleResponse(BaseModel):
    sqm: float
    bortle: int
    nelm: float
    note: str | None


@router.get("/sqm-bortle", response_model=SqmBortleResponse)
async def sqm_bortle_endpoint(
    sqm: float | None = Query(None),
    bortle: int | None = Query(None, ge=1, le=9),
    nelm: float | None = Query(None),
):
    """Convert between SQM, Bortle class, and NELM. Provide exactly one."""
    if sqm is None and bortle is None and nelm is None:
        raise HTTPException(
            status_code=422,
            detail="Provide one of: sqm, bortle, or nelm",
        )

    note: str | None = None

    # Precedence: sqm > nelm > bortle
    if sqm is not None:
        if sqm < 14.0 or sqm > 23.0:
            note = "clamped"
            sqm = max(14.0, min(23.0, sqm))
        resolved_sqm = float(sqm)
    elif nelm is not None:
        if nelm < 0.0 or nelm > 8.0:
            note = "clamped"
            nelm = max(0.0, min(8.0, nelm))
        resolved_sqm = nelm_to_sqm(float(nelm))
    else:
        # bortle is not None
        resolved_sqm = bortle_to_sqm(int(bortle))

    resolved_bortle = sqm_to_bortle(resolved_sqm)
    resolved_nelm = sqm_to_nelm(resolved_sqm)

    return SqmBortleResponse(
        sqm=resolved_sqm,
        bortle=resolved_bortle,
        nelm=resolved_nelm,
        note=note,
    )


# ── 13. Temperature ──────────────────────────────────────────────────────────


class TemperatureResponse(BaseModel):
    celsius: float
    fahrenheit: float
    kelvin: float


@router.get("/temperature", response_model=TemperatureResponse)
async def temperature_endpoint(
    value: float = Query(...),
    from_: TempUnit = Query(..., alias="from"),
):
    """Convert a temperature between Celsius, Fahrenheit, and Kelvin."""
    try:
        c, f, k = temperature_all(value, from_)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TemperatureResponse(celsius=c, fahrenheit=f, kelvin=k)
