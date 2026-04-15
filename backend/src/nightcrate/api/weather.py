"""Weather forecast API — integrates weather, astronomy, seeing, and imaging quality."""

import asyncio
import json
import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from nightcrate.api.weather_models import (
    DailySummaryResponse,
    DewSafeWindowResponse,
    ForecastResponse,
    HourlyDetailResponse,
    HourlyWeatherResponse,
    MethodologyResponse,
    MoonPolylinePointResponse,
    TwilightTimesResponse,
)
from nightcrate.core.config import get_settings
from nightcrate.db.session import get_db
from nightcrate.services.astronomy import (
    compute_hourly_astro,
    compute_moon_polyline,
    compute_night_summary,
)
from nightcrate.services.dew import (
    classify_dew_risk,
    compute_dew_safe_window,
)
from nightcrate.services.imaging_quality import (
    compute_imaging_quality,
    compute_sky_clarity,
)
from nightcrate.services.seeing import estimate_seeing_surface, estimate_seeing_wind_shear
from nightcrate.services.transparency import estimate_transparency
from nightcrate.services.weather import (
    SupplementaryData,
    WeatherData,
    fetch_air_quality,
    fetch_pwv,
    fetch_weather,
    nearest_match,
    parse_hourly,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/weather", tags=["Weather"])

# ── Help text (verbatim from spec) ─────────────────────────────────────────

METHODOLOGY = """\
The imaging quality score (0\u2013100) rates each night\u2019s suitability for deep-sky \
imaging. Higher is always better. Sky clarity acts as a cloud gating factor \u2014 \
heavy clouds suppress the contribution of all other factors.

### Factors & Weights

| Factor       | Weight | No Moon | Description |
|--------------|--------|---------|-------------|
| Sky Clarity  | 35%    | 40%     | Cloud-weighted sky openness. Low, mid, and \
high clouds are weighted 1.0 / 0.9 / 0.6 \u2014 thin cirrus hurts less than thick \
stratus. Also acts as a gating multiplier on all other factors. |
| Seeing       | 25%    | 25%     | Atmospheric turbulence estimate. Uses \
upper-atmosphere wind shear at 200/300/500 hPa when available, surface \
wind/humidity/stability as fallback. |
| Transparency | 15%    | 25%     | Total-column water vapor (PWV), aerosol \
optical depth (wildfire smoke, dust, pollution), surface humidity, and \
visibility combined. Lower PWV and AOD = better narrowband and broadband \
transparency. |
| Moon         | 15%    | n/a     | Penalty based on how long the moon is above \
the horizon during darkness and how bright it is. Disable for narrowband \
imaging. |
| Wind Calm    | 10%    | 10%     | Surface wind penalty. Calm (< 5 km/h) is \
ideal; strong wind (> 25 km/h) scores poorly. |

### Cloud Gating

Other factors are multiplied by \u221a(sky_clarity / 100). At 50% cloud cover, \
other factors contribute 71% of their normal weight. At 90% cloud cover, 32%. \
At 100% cloud, 0. Perfect seeing can\u2019t save a cloudy night.

### Quality Labels

| Score   | Label     |
|---------|-----------|
| 80\u2013100  | Excellent |
| 55\u201379   | Good      |
| 30\u201354   | Marginal  |
| 0\u201329    | Poor      |

### Dew Risk

Classified from temperature minus dew point spread:
- **Low:** spread > 5 \u00b0C
- **Moderate:** spread 3\u20135 \u00b0C
- **High:** spread 1\u20133 \u00b0C (dew heaters recommended)
- **Critical:** spread < 1 \u00b0C (active dew formation likely)

The \u201cDew-safe\u201d line on daily cards reports when the spread stays above 3 \u00b0C \
during darkness.

### Data Sources

- **Weather:** Open-Meteo forecast API (free)
- **PWV:** Open-Meteo ECMWF IFS 0.25\u00b0 model
- **Air quality (AOD):** Open-Meteo Air Quality API, CAMS Global
- **Astronomy:** astropy (moon, twilight, elongation)
- **Seeing model:** Trinquet & Vernin 2006, Cherubini & Businger 2013\
"""


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _get_location(location_id: int) -> dict:
    """Fetch a location row from the DB or raise 404."""
    async with get_db() as conn:
        cursor = await conn.execute("SELECT * FROM location WHERE id = ?", (location_id,))
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Location not found")
        return dict(row)


async def _fetch_or_cached(
    location_id: int,
    latitude: float,
    longitude: float,
    timezone_str: str,
    source: str = "forecast",
    start_date: str | None = None,
    end_date: str | None = None,
) -> WeatherData:
    """Return cached weather data if fresh, otherwise fetch and cache."""
    settings = await get_settings()
    ttl_hours = settings.weather_cache_ttl_hours

    async with get_db() as conn:
        if source == "forecast":
            cursor = await conn.execute(
                """SELECT response_json, source FROM weather_cache
                   WHERE location_id = ? AND source = 'forecast'
                     AND fetched_at > datetime('now', ?)
                   ORDER BY fetched_at DESC LIMIT 1""",
                (location_id, f"-{ttl_hours} hours"),
            )
        else:
            cursor = await conn.execute(
                """SELECT response_json, source FROM weather_cache
                   WHERE location_id = ? AND source = 'archive'
                     AND start_date = ? AND end_date = ?
                     AND fetched_at > datetime('now', ?)
                   ORDER BY fetched_at DESC LIMIT 1""",
                (location_id, start_date, end_date, f"-{ttl_hours} hours"),
            )

        row = await cursor.fetchone()
        if row is not None:
            raw = json.loads(row["response_json"])
            hourly = parse_hourly(raw["hourly"], row["source"])
            return WeatherData(
                latitude=raw["latitude"],
                longitude=raw["longitude"],
                source=row["source"],
                hourly=hourly,
                raw_json=row["response_json"],
            )

    data = await fetch_weather(
        latitude=latitude,
        longitude=longitude,
        timezone_str=timezone_str,
        source=source,
        start_date=start_date,
        end_date=end_date,
    )

    try:
        async with get_db() as conn:
            if source == "forecast":
                await conn.execute(
                    """INSERT OR REPLACE INTO weather_cache
                       (location_id, source, start_date, end_date, response_json, fetched_at)
                       VALUES (?, 'forecast', '', '', ?, datetime('now'))""",
                    (location_id, data.raw_json),
                )
            else:
                await conn.execute(
                    """INSERT OR REPLACE INTO weather_cache
                       (location_id, source, start_date, end_date, response_json, fetched_at)
                       VALUES (?, 'archive', ?, ?, ?, datetime('now'))""",
                    (location_id, start_date, end_date, data.raw_json),
                )
            await conn.commit()
    except Exception:
        logger.warning("Failed to cache weather data (non-fatal)")

    return data


async def _fetch_or_cached_supplementary(
    location_id: int,
    latitude: float,
    longitude: float,
    timezone_str: str,
    source_key: str,
    fetch_fn,
) -> dict[str, float | None]:
    """Fetch supplementary time-series data (PWV or AOD) with cache.

    Returns a time→value map. Cache failures are non-fatal — the fetched
    data is always returned even if caching fails.
    """
    settings = await get_settings()
    ttl_hours = settings.weather_cache_ttl_hours

    # Try cache first
    try:
        async with get_db() as conn:
            cursor = await conn.execute(
                """SELECT response_json FROM weather_cache
                   WHERE location_id = ? AND source = ?
                     AND fetched_at > datetime('now', ?)
                   ORDER BY fetched_at DESC LIMIT 1""",
                (location_id, source_key, f"-{ttl_hours} hours"),
            )
            row = await cursor.fetchone()
            if row is not None:
                raw = json.loads(row["response_json"])
                # Re-parse from raw JSON
                hourly = raw.get("hourly", {})
                times = hourly.get("time", [])
                # Find the first non-"time" key for the values
                val_key = next(
                    (k for k in hourly if k != "time"),
                    None,
                )
                values = hourly.get(val_key, []) if val_key else []
                result = {}
                for i, t in enumerate(times):
                    val = values[i] if i < len(values) else None
                    result[t] = float(val) if val is not None else None
                return result
    except Exception:
        logger.debug("Cache read failed for %s (non-fatal)", source_key)

    # Fetch fresh
    data: SupplementaryData = await fetch_fn(
        latitude=latitude,
        longitude=longitude,
        timezone_str=timezone_str,
    )

    # Try to cache (non-fatal)
    try:
        async with get_db() as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO weather_cache
                   (location_id, source, start_date, end_date, response_json, fetched_at)
                   VALUES (?, ?, '', '', ?, datetime('now'))""",
                (location_id, source_key, data.raw_json),
            )
            await conn.commit()
    except Exception:
        logger.warning("Failed to cache %s data (non-fatal)", source_key)

    return data.values_by_time


def _compute_seeing(h, prev_h) -> int:
    """Compute seeing score for an hourly weather record, choosing the best model."""
    prev_temp = prev_h.temperature_c if prev_h is not None else None

    if h.wind_speed_200hpa_kmh is not None:
        return estimate_seeing_wind_shear(
            wind_speed_200hpa_kmh=h.wind_speed_200hpa_kmh,
            wind_speed_300hpa_kmh=h.wind_speed_300hpa_kmh,
            wind_speed_500hpa_kmh=h.wind_speed_500hpa_kmh,
            geopotential_200hpa_m=h.geopotential_200hpa_m,
            geopotential_300hpa_m=h.geopotential_300hpa_m,
            geopotential_500hpa_m=h.geopotential_500hpa_m,
            temperature_c=h.temperature_c,
            dew_point_c=h.dew_point_c,
            humidity_pct=h.humidity_pct,
            wind_speed_surface_kmh=h.wind_speed_kmh,
            prev_temperature_c=prev_temp,
        )
    return estimate_seeing_surface(
        temperature_c=h.temperature_c,
        dew_point_c=h.dew_point_c,
        humidity_pct=h.humidity_pct,
        wind_speed_kmh=h.wind_speed_kmh,
        prev_temperature_c=prev_temp,
    )


async def _fetch_supplementary_pair(
    loc: dict,
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    """Fetch PWV and AOD supplementary data concurrently. Returns (pwv, aod) dicts."""

    async def _safe_fetch(source_key: str, fetch_fn) -> dict[str, float | None]:
        try:
            return await _fetch_or_cached_supplementary(
                loc["id"],
                loc["latitude"],
                loc["longitude"],
                loc["timezone"],
                source_key,
                fetch_fn,
            )
        except Exception:
            logger.warning("Supplementary fetch %s failed for location %s", source_key, loc["id"])
            return {}

    pwv_by_time, aod_by_time = await asyncio.gather(
        _safe_fetch("ecmwf_pwv", fetch_pwv),
        _safe_fetch("openmeteo_aq", fetch_air_quality),
    )
    return pwv_by_time, aod_by_time


def _compute_transparency(
    h,
    pwv_mm: float | None,
    aod_value: float | None,
) -> int:
    """Compute transparency score for an hourly weather record."""
    result = estimate_transparency(
        pwv_mm=pwv_mm,
        aod=aod_value,
        humidity_pct=h.humidity_pct,
        visibility_m=h.visibility_m,
    )
    return result.score


def _hours_in_window(
    weather_hours: list,
    start_str: str,
    end_str: str,
) -> list[tuple[int, object]]:
    """Return (index, hour) tuples for weather hours within a time window."""
    result = []
    for i, h in enumerate(weather_hours):
        if start_str <= h.time <= end_str:
            result.append((i, h))
    return result


def _fmt_time(dt: datetime | None, tz: ZoneInfo) -> str | None:
    """Format a datetime as HH:MM in local time, or return None."""
    if dt is None:
        return None
    return dt.astimezone(tz).strftime("%H:%M")


def _compute_night_data(
    loc: dict,
    night_date: date,
    tz: ZoneInfo,
    weather: WeatherData,
    pwv_by_time: dict[str, float | None],
    aod_by_time: dict[str, float | None],
    moon_included: bool,
) -> DailySummaryResponse | None:
    """Compute a daily summary for one night, driven by actual sunset/sunrise."""
    try:
        night = compute_night_summary(
            latitude=loc["latitude"],
            longitude=loc["longitude"],
            elevation_m=loc.get("elevation_m"),
            night_date=night_date,
            timezone_str=loc["timezone"],
        )
    except Exception:
        logger.warning("Skipping %s — astronomy computation failed", night_date)
        return None

    # If no imaging window, return a minimal response
    if night.no_imaging_window:
        return DailySummaryResponse(
            date=night_date.isoformat(),
            imaging_quality=0,
            imaging_quality_label="Poor",
            sky_clarity=0,
            transparency_score=0,
            seeing_score=0,
            wind_calm=0,
            moon_score=100,
            sunset=_fmt_time(night.sunset, tz),
            sunrise=_fmt_time(night.sunrise, tz),
            astro_dark_start=_fmt_time(night.darkness.astro_start, tz),
            astro_dark_end=_fmt_time(night.darkness.astro_end, tz),
            darkness_hours=night.darkness_hours,
            moonless_dark_hours=night.moonless_dark_hours,
            moon_illumination_pct=night.moon.illumination_pct,
            moon_phase_name=night.moon.phase_name,
            dew_safe_window=DewSafeWindowResponse(label="none"),
            no_imaging_window=True,
            deepest_darkness_reached=night.deepest_darkness_reached,
            temp_min_c=0,
            temp_max_c=0,
            max_precipitation_probability_pct=0,
            avg_cloud_cover_pct=0,
            avg_cloud_low_pct=0,
            avg_cloud_mid_pct=0,
            avg_cloud_high_pct=0,
        )

    # Window: sunset to sunrise (actual imaging window).
    sunset_local = night.sunset.astimezone(tz)
    sunrise_local = night.sunrise.astimezone(tz)
    sunset_str = sunset_local.strftime("%Y-%m-%dT%H:%M")
    sunrise_str = sunrise_local.strftime("%Y-%m-%dT%H:%M")

    hours_data = _hours_in_window(weather.hourly, sunset_str, sunrise_str)
    if not hours_data:
        return None

    n = len(hours_data)
    avg_cloud = sum(h.cloud_cover_pct for _, h in hours_data) / n
    avg_cloud_low = sum(h.cloud_cover_low_pct for _, h in hours_data) / n
    avg_cloud_mid = sum(h.cloud_cover_mid_pct for _, h in hours_data) / n
    avg_cloud_high = sum(h.cloud_cover_high_pct for _, h in hours_data) / n
    avg_wind = sum(h.wind_speed_kmh for _, h in hours_data) / n
    max_precip_prob = max(
        (h.precipitation_probability_pct or 0 for _, h in hours_data),
        default=0,
    )
    temp_min = min(h.temperature_c for _, h in hours_data)
    temp_max = max(h.temperature_c for _, h in hours_data)

    # Seeing scores
    seeing_scores = []
    for idx, (i, h) in enumerate(hours_data):
        prev_h = hours_data[idx - 1][1] if idx > 0 else None
        seeing_scores.append(_compute_seeing(h, prev_h))
    avg_seeing = sum(seeing_scores) / len(seeing_scores)

    # Transparency scores (use nearest_match for PWV and AOD)
    transparency_scores = []
    for _, h in hours_data:
        pwv_val = nearest_match(pwv_by_time, h.time)
        aod_val = nearest_match(aod_by_time, h.time)
        transparency_scores.append(_compute_transparency(h, pwv_val, aod_val))
    avg_transparency = sum(transparency_scores) / len(transparency_scores)

    # Sky clarity (weighted)
    sky_clarity = compute_sky_clarity(
        cloud_cover_pct=avg_cloud,
        cloud_cover_low_pct=avg_cloud_low,
        cloud_cover_mid_pct=avg_cloud_mid,
        cloud_cover_high_pct=avg_cloud_high,
    )

    quality = compute_imaging_quality(
        sky_clarity=sky_clarity,
        seeing_score=int(round(avg_seeing)),
        transparency_score=int(round(avg_transparency)),
        wind_speed_kmh=avg_wind,
        moonless_dark_hours=night.moonless_dark_hours,
        darkness_hours=night.darkness_hours,
        moon_illumination_pct=night.moon.illumination_pct,
        include_moon=moon_included,
    )

    # Dew safe window — compute from hourly data during darkness
    dew_hourly: list[tuple[str, float, float]] = []
    for _, h in hours_data:
        weather_dt = datetime.fromisoformat(h.time)
        hhmm = weather_dt.strftime("%H:%M")
        dew_hourly.append((hhmm, h.temperature_c, h.dew_point_c))

    dew_window = compute_dew_safe_window(dew_hourly)

    return DailySummaryResponse(
        date=night_date.isoformat(),
        imaging_quality=quality.overall,
        imaging_quality_label=quality.label,
        sky_clarity=quality.sky_clarity,
        transparency_score=quality.transparency,
        seeing_score=int(round(avg_seeing)),
        wind_calm=quality.wind_calm,
        moon_score=quality.moon_score,
        sunset=sunset_local.strftime("%H:%M"),
        sunrise=sunrise_local.strftime("%H:%M"),
        astro_dark_start=_fmt_time(night.darkness.astro_start, tz),
        astro_dark_end=_fmt_time(night.darkness.astro_end, tz),
        darkness_hours=night.darkness_hours,
        moonless_dark_hours=night.moonless_dark_hours,
        moon_illumination_pct=night.moon.illumination_pct,
        moon_phase_name=night.moon.phase_name,
        dew_safe_window=DewSafeWindowResponse(
            label=dew_window.label,
            until_time=dew_window.until_time,
            after_time=dew_window.after_time,
        ),
        no_imaging_window=night.no_imaging_window,
        deepest_darkness_reached=night.deepest_darkness_reached,
        temp_min_c=round(temp_min, 1),
        temp_max_c=round(temp_max, 1),
        max_precipitation_probability_pct=round(max_precip_prob, 1),
        avg_cloud_cover_pct=round(avg_cloud, 1),
        avg_cloud_low_pct=round(avg_cloud_low, 1),
        avg_cloud_mid_pct=round(avg_cloud_mid, 1),
        avg_cloud_high_pct=round(avg_cloud_high, 1),
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/forecast", response_model=ForecastResponse)
async def get_forecast(
    location_id: int = Query(..., description="Location ID"),
    include_moon: bool | None = Query(None, description="Include moon penalty in quality score"),
):
    """7-day imaging quality forecast for a location."""
    loc = await _get_location(location_id)
    settings = await get_settings()
    moon_included = include_moon if include_moon is not None else settings.weather_moon_penalty

    weather = await _fetch_or_cached(
        location_id=loc["id"],
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        timezone_str=loc["timezone"],
        source="forecast",
    )

    pwv_by_time, aod_by_time = await _fetch_supplementary_pair(loc)

    tz = ZoneInfo(loc["timezone"])

    now_local = datetime.now(tz)
    start_date = now_local.date()

    days: list[DailySummaryResponse] = []
    for offset in range(8):  # try up to 8 days to get 7 valid nights
        d = start_date + timedelta(days=offset)
        result = _compute_night_data(
            loc,
            d,
            tz,
            weather,
            pwv_by_time,
            aod_by_time,
            moon_included,
        )
        if result is not None:
            days.append(result)
        if len(days) >= 7:
            break

    return ForecastResponse(
        location_id=loc["id"],
        location_name=loc["name"],
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        timezone=loc["timezone"],
        moon_included=moon_included,
        days=days,
    )


@router.get("/hourly", response_model=HourlyDetailResponse)
async def get_hourly(
    location_id: int = Query(..., description="Location ID"),
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
):
    """Hourly weather detail for a specific night."""
    loc = await _get_location(location_id)
    night_date = datetime.strptime(date, "%Y-%m-%d").date()

    weather = await _fetch_or_cached(
        location_id=loc["id"],
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        timezone_str=loc["timezone"],
        source="forecast",
    )

    pwv_by_time, aod_by_time = await _fetch_supplementary_pair(loc)

    tz = ZoneInfo(loc["timezone"])

    astro_hours = compute_hourly_astro(
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        elevation_m=loc.get("elevation_m"),
        night_date=night_date,
        timezone_str=loc["timezone"],
    )
    night = compute_night_summary(
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        elevation_m=loc.get("elevation_m"),
        night_date=night_date,
        timezone_str=loc["timezone"],
    )

    # If no imaging window (polar conditions), return minimal response
    if night.no_imaging_window or night.sunset is None or night.sunrise is None:
        return HourlyDetailResponse(
            date=date,
            location_id=loc["id"],
            location_name=loc["name"],
            sunset=_fmt_time(night.sunset, tz),
            sunrise=_fmt_time(night.sunrise, tz),
            twilight=TwilightTimesResponse(
                civil_end=_fmt_time(night.darkness.civil_end, tz),
                nautical_end=_fmt_time(night.darkness.nautical_end, tz),
                astro_start=_fmt_time(night.darkness.astro_start, tz),
                astro_end=_fmt_time(night.darkness.astro_end, tz),
                nautical_start=_fmt_time(night.darkness.nautical_start, tz),
                civil_start=_fmt_time(night.darkness.civil_start, tz),
            ),
            moon_polyline=[],
            hours=[],
        )

    # Lookup astro data by HH:MM local time
    astro_by_time: dict[str, object] = {}
    for a in astro_hours:
        astro_by_time[a.time_local] = a

    # Window: sunset - 1h through sunrise + 1h for pre/post context
    sunset_local = night.sunset.astimezone(tz)
    sunrise_local = night.sunrise.astimezone(tz)
    window_start = sunset_local - timedelta(hours=1)
    window_end = sunrise_local + timedelta(hours=1)
    start_str = window_start.strftime("%Y-%m-%dT%H:%M")
    end_str = window_end.strftime("%Y-%m-%dT%H:%M")

    matched = _hours_in_window(weather.hourly, start_str, end_str)

    # Compute moon polyline for the window
    moon_polyline_data = compute_moon_polyline(
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        elevation_m=loc.get("elevation_m"),
        start_utc=window_start.astimezone(UTC),
        end_utc=window_end.astimezone(UTC),
    )
    moon_polyline = [
        MoonPolylinePointResponse(
            time_utc=p.time_utc,
            altitude_deg=p.altitude_deg,
        )
        for p in moon_polyline_data
    ]

    hours: list[HourlyWeatherResponse] = []
    for idx, (i, h) in enumerate(matched):
        prev_h = matched[idx - 1][1] if idx > 0 else None
        seeing = _compute_seeing(h, prev_h)

        weather_dt = datetime.fromisoformat(h.time)
        hhmm = weather_dt.strftime("%H:%M")
        astro = astro_by_time.get(hhmm)

        # Sky clarity (weighted by cloud layers)
        sky_clarity_val = compute_sky_clarity(
            cloud_cover_pct=h.cloud_cover_pct,
            cloud_cover_low_pct=h.cloud_cover_low_pct,
            cloud_cover_mid_pct=h.cloud_cover_mid_pct,
            cloud_cover_high_pct=h.cloud_cover_high_pct,
        )

        # Transparency (PWV and AOD via nearest-match)
        pwv_val = nearest_match(pwv_by_time, h.time)
        aod_val = nearest_match(aod_by_time, h.time)
        transparency = _compute_transparency(h, pwv_val, aod_val)

        # Dew risk
        dew_risk = classify_dew_risk(h.temperature_c, h.dew_point_c)

        moon_alt = astro.moon_altitude_deg if astro else None
        moon_up = moon_alt is not None and moon_alt > 0
        quality = compute_imaging_quality(
            sky_clarity=sky_clarity_val,
            seeing_score=seeing,
            transparency_score=transparency,
            wind_speed_kmh=h.wind_speed_kmh,
            moonless_dark_hours=0.0 if moon_up else 1.0,
            darkness_hours=1.0,
            moon_illumination_pct=night.moon.illumination_pct,
            include_moon=True,
        )

        hours.append(
            HourlyWeatherResponse(
                time=h.time,
                temperature_c=h.temperature_c,
                dew_point_c=h.dew_point_c,
                humidity_pct=h.humidity_pct,
                cloud_cover_pct=h.cloud_cover_pct,
                cloud_cover_low_pct=h.cloud_cover_low_pct,
                cloud_cover_mid_pct=h.cloud_cover_mid_pct,
                cloud_cover_high_pct=h.cloud_cover_high_pct,
                wind_speed_kmh=h.wind_speed_kmh,
                wind_direction_deg=h.wind_direction_deg,
                wind_gusts_kmh=h.wind_gusts_kmh,
                visibility_m=h.visibility_m,
                precipitation_mm=h.precipitation_mm,
                precipitation_probability_pct=h.precipitation_probability_pct,
                pwv_mm=pwv_val,
                aod=aod_val,
                sky_clarity=sky_clarity_val,
                transparency_score=transparency,
                seeing_score=seeing,
                wind_calm=quality.wind_calm,
                dew_risk=dew_risk,
                imaging_quality=quality.overall,
                imaging_quality_label=quality.label,
                moon_altitude_deg=astro.moon_altitude_deg if astro else None,
                moon_illumination_pct=(astro.moon_illumination_pct if astro else None),
                darkness_category=(astro.darkness_category if astro else None),
            )
        )

    twilight = TwilightTimesResponse(
        civil_end=_fmt_time(night.darkness.civil_end, tz),
        nautical_end=_fmt_time(night.darkness.nautical_end, tz),
        astro_start=_fmt_time(night.darkness.astro_start, tz),
        astro_end=_fmt_time(night.darkness.astro_end, tz),
        nautical_start=_fmt_time(night.darkness.nautical_start, tz),
        civil_start=_fmt_time(night.darkness.civil_start, tz),
    )

    return HourlyDetailResponse(
        date=date,
        location_id=loc["id"],
        location_name=loc["name"],
        sunset=sunset_local.strftime("%H:%M"),
        sunrise=sunrise_local.strftime("%H:%M"),
        twilight=twilight,
        moon_polyline=moon_polyline,
        hours=hours,
    )


@router.get("/methodology", response_model=MethodologyResponse)
async def get_methodology():
    """Return the imaging quality score methodology description."""
    return MethodologyResponse(text=METHODOLOGY)
