"""Weather forecast API — integrates weather, astronomy, seeing, and imaging quality."""

import asyncio
import bisect
import json
import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from nightcrate.api.weather_models import (
    DailySummaryResponse,
    DewSafeWindowResponse,
    FactorResponse,
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
    moon_altitudes_at,
)
from nightcrate.services.dew import (
    classify_dew_risk,
    compute_dew_safe_window,
)
from nightcrate.services.imaging_quality import (
    UNUSABLE_LABEL,
    Flag,
    ImagingQuality,
    Mode,
    darkness_fraction,
    expected_useful_hours,
    label_for_score,
    moon_score,
    score_hour,
    wind_calm_score,
)
from nightcrate.services.seeing import estimate_seeing_surface, estimate_seeing_wind_shear
from nightcrate.services.transparency import estimate_transparency
from nightcrate.services.weather import (
    CLOUD_PRIMARY_MODEL,
    CLOUD_SPREAD_MODELS,
    FORECAST_UNCERTAIN_MIN_SPREAD,
    CloudModelData,
    NearestMatchIndex,
    SupplementaryData,
    WeatherData,
    fetch_air_quality,
    fetch_cloud_models,
    fetch_pwv,
    fetch_weather,
    parse_cloud_models,
    parse_hourly,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/weather", tags=["Weather"])

# ── Help text (verbatim from spec) ─────────────────────────────────────────

METHODOLOGY = """\
The imaging quality score (0\u2013100) rates each forecast hour's suitability for \
deep-sky imaging. Higher is always better. It reads as **expected useful data as a \
fraction of a perfect hour**, so summing it across a night gives equivalent hours \
of good data.

### Two questions, two numbers

    score = availability \u00d7 quality

**Availability** is the fraction of the hour that yields keepable sub-frames. It \
is a *product* of hard gates and the cloud curve, so any closed gate zeroes it \
and nothing downstream can rescue it. **Quality** is how good those frames will \
be, and is a weighted mean \u2014 seeing, transparency and wind each degrade data, \
but none alone makes a night unimageable. Both are shown, so a cirrus night can \
read "0, though quality would have been 67".

### Gates and the cloud curve (availability)

| Factor | Behaviour |
|--------|-----------|
| Darkness | Fraction of the hour inside astronomical darkness (sun below \u221218\u00b0). \
Narrowband mode uses sun below \u221212\u00b0, keeping the astronomical-twilight hours \
a 3nm filter can shoot through. No darkness at all \u2192 0. |
| Precipitation | Any forecast precipitation *amount* closes the hour outright. \
Probability ramps the gate from 1 to 0 across 40\u201370%. |
| Wind | Sustained wind ramps the gate from 1 to 0 across 40\u201360 km/h \u2014 above \
that a tall OTA is unsafe and guiding is hopeless regardless of sky. |
| Cloud | Yield is (1 \u2212 cover)^1.5 on the **maximum** of total and per-layer \
cover. Exactly 0 at 100% cover, for any layer. |

**Cloud counts fully, whatever its altitude.** The forecast reports high cloud as \
*coverage* inferred from relative humidity, not opacity, so it cannot tell \
subvisual cirrus from an opaque deck. Giving high cloud partial credit is what \
made an overcast cirrus night score 46 in the previous model. Layer composition \
now drives only an advisory: when obscuration is almost all above 8 km, the hour \
is flagged so you can check satellite IR before writing the night off.

### Quality factors

| Factor       | Weight | Description |
|--------------|--------|-------------|
| Seeing       | 45%    | Atmospheric turbulence. Upper-atmosphere wind shear at \
200/300/500 hPa when available, surface wind/humidity/stability as fallback. |
| Transparency | 40%    | Total-column water vapour (PWV), aerosol optical depth \
(smoke, dust, pollution), surface humidity and visibility. |
| Wind Calm    | 15%    | Surface wind. Calm (< 5 km/h) is ideal; 40 km/h scores zero. |

The **Moon** multiplies quality rather than adding to it, from 1.0 at no moon down \
to a floor of 0.35 under a full moon high in the sky \u2014 a floor, not a gate, \
because bright targets survive moonlight. The per-hour penalty scales with \
illumination and with the sine of the moon's altitude, so a full moon at 5\u00b0 costs \
far less than one overhead. Disabled entirely in narrowband mode.

### Quality Labels

| Score   | Label     |
|---------|-----------|
| 75\u2013100  | Excellent |
| 50\u201374   | Good      |
| 25\u201349   | Marginal  |
| 0\u201324    | Poor      |

**Unusable** overrides all of these when availability falls below 0.10 \
(\u2248 78% cloud, or any closed gate) \u2014 it is a statement about whether you can \
image at all, not the bottom bucket of the scale.

### Dew Risk

Classified from temperature minus dew point spread. Advisory only: it never \
affects the score, because dew heaters make it a preparation issue rather than a \
go/no-go one.
- **Low:** spread > 5 \u00b0C
- **Moderate:** spread 3\u20135 \u00b0C
- **High:** spread 1\u20133 \u00b0C (dew heaters recommended)
- **Critical:** spread < 1 \u00b0C (active dew formation likely)

### Forecast Uncertainty

Cloud cover comes from **ECMWF**, chosen by measurement: against reanalysis over \
126 night hours, its day-ahead mean absolute error was 18 points against GFS's 32, \
and it called a clear night cloudy 8 times against GFS's 25. Everything else still \
comes from Open-Meteo's default blend.

Two further models (GFS and ICON) are fetched in the same request, and the score is \
re-run on each. When their verdicts differ \u2014 different quality labels, and far \
enough apart to change the evening's plan \u2014 the night is marked as uncertain and \
the range is shown. On the nights the models agree, nothing is shown, because a \
range of "0\u20130" is noise. A wide range is a reason to look again closer to the \
night rather than to trust the headline number.

### Data Sources

- **Weather:** Open-Meteo forecast API (free); cloud from ECMWF IFS 0.25, with \
GFS and ICON fetched alongside for the uncertainty range
- **PWV:** Open-Meteo ECMWF IFS 0.25\u00b0 model
- **Air quality (AOD):** Open-Meteo Air Quality API, CAMS Global
- **Astronomy:** astropy (moon, twilight, elongation)
- **Seeing model:** Trinquet & Vernin 2006, Cherubini & Businger 2013
- **Cloud treatment:** ESO and Gemini observing-condition definitions; Sassen & \
Cho (1992) cirrus optical-depth classes; mid-latitude cirrus climatology, \
Atmos. Chem. Phys. 20, 4427\u20134444 (2020)\
"""


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _get_location(location_id: int) -> dict:
    """Fetch a location row from the DB or raise 404."""
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT * FROM location WHERE id = ? AND active = 1", (location_id,)
        )
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
    ttl_hours: int | None = None,
) -> WeatherData:
    """Return cached weather data if fresh, otherwise fetch and cache."""
    if ttl_hours is None:
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
            logger.debug(
                "[weather-cache] HIT weather[%s] location=%s",
                source,
                location_id,
            )
            raw = json.loads(row["response_json"])
            hourly = parse_hourly(raw["hourly"], row["source"])
            return WeatherData(
                latitude=raw["latitude"],
                longitude=raw["longitude"],
                source=row["source"],
                hourly=hourly,
                raw_json=row["response_json"],
            )

    logger.info(
        "[weather-cache] MISS weather[%s] location=%s → fetching",
        source,
        location_id,
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


async def _fetch_or_cached_cloud_models(
    location_id: int,
    latitude: float,
    longitude: float,
    timezone_str: str,
    ttl_hours: int | None = None,
) -> CloudModelData | None:
    """Multi-model cloud cover with cache. None when unavailable.

    A failure here must never fail the forecast: the primary cloud series falls
    back to the main `best_match` response and the spread is simply not shown.
    """
    if ttl_hours is None:
        settings = await get_settings()
        ttl_hours = settings.weather_cache_ttl_hours

    try:
        async with get_db() as conn:
            cursor = await conn.execute(
                """SELECT response_json FROM weather_cache
                   WHERE location_id = ? AND source = 'cloud_models'
                     AND fetched_at > datetime('now', ?)
                   ORDER BY fetched_at DESC LIMIT 1""",
                (location_id, f"-{ttl_hours} hours"),
            )
            row = await cursor.fetchone()
            if row is not None:
                logger.debug("[weather-cache] HIT cloud_models location=%s", location_id)
                raw = json.loads(row["response_json"])
                return CloudModelData(
                    models=parse_cloud_models(raw.get("hourly", {}), CLOUD_SPREAD_MODELS),
                    raw_json=row["response_json"],
                )
    except Exception:
        logger.warning("[weather-cache] cloud_models cache read failed (non-fatal)")

    logger.info("[weather-cache] MISS cloud_models location=%s -> fetching", location_id)
    try:
        data = await fetch_cloud_models(latitude, longitude, timezone_str)
    except Exception:
        logger.warning("[weather] cloud-model fetch failed; falling back to the primary forecast")
        return None

    try:
        async with get_db() as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO weather_cache
                   (location_id, source, start_date, end_date, response_json, fetched_at)
                   VALUES (?, 'cloud_models', '', '', ?, datetime('now'))""",
                (location_id, data.raw_json),
            )
            await conn.commit()
    except Exception:
        logger.warning("Failed to cache cloud-model data (non-fatal)")

    return data


async def _fetch_or_cached_supplementary(
    location_id: int,
    latitude: float,
    longitude: float,
    timezone_str: str,
    source_key: str,
    fetch_fn,
    ttl_hours: int | None = None,
) -> dict[str, float | None]:
    """Fetch supplementary time-series data (PWV or AOD) with cache.

    Returns a time→value map. Cache failures are non-fatal — the fetched
    data is always returned even if caching fails.
    """
    if ttl_hours is None:
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
                logger.debug(
                    "[weather-cache] HIT %s location=%s",
                    source_key,
                    location_id,
                )
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

    logger.info(
        "[weather-cache] MISS %s location=%s → fetching",
        source_key,
        location_id,
    )
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
    ttl_hours: int | None = None,
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
                ttl_hours=ttl_hours,
            )
        except Exception:
            logger.warning("Supplementary fetch %s failed for location %s", source_key, loc["id"])
            return {}

    pwv_by_time, aod_by_time = await asyncio.gather(
        _safe_fetch("ecmwf_pwv", fetch_pwv),
        _safe_fetch("openmeteo_aq", fetch_air_quality),
    )
    return pwv_by_time, aod_by_time


def _transparency_score(h, pwv_mm: float | None, aod_value: float | None) -> int:
    """Compute transparency score for an hourly weather record."""
    return estimate_transparency(
        pwv_mm=pwv_mm,
        aod=aod_value,
        humidity_pct=h.humidity_pct,
        visibility_m=h.visibility_m,
    ).score


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


def _mode_for(moon_included: bool) -> Mode:
    """Narrowband mode ignores the moon and widens the darkness gate to sun <= -12."""
    return Mode.NORMAL if moon_included else Mode.NARROWBAND


def _hour_utc(h, tz: ZoneInfo) -> datetime:
    """Absolute UTC instant for a weather hour.

    Weather rows are labelled in the *display* timezone while astronomy is
    computed in the site timezone, so everything that joins the two must go
    through the absolute instant rather than a wall-clock string.
    """
    return datetime.fromisoformat(h.time).replace(tzinfo=tz).astimezone(UTC)


def _cloud_for(h, cloud_models: CloudModelData | None, time_key: str) -> tuple:
    """Cloud figures to score this hour with.

    The primary model (ECMWF, chosen on measured skill — see
    `services/weather.py:CLOUD_PRIMARY_MODEL`) when it covers the hour, else the
    main `best_match` forecast. Falling back rather than skipping matters at the
    8-day edge, where a model's horizon can end mid-window.
    """
    if cloud_models is not None:
        primary = cloud_models.at(CLOUD_PRIMARY_MODEL, time_key)
        if primary is not None:
            return primary
    return (
        h.cloud_cover_pct,
        h.cloud_cover_low_pct,
        h.cloud_cover_mid_pct,
        h.cloud_cover_high_pct,
    )


def _score_one_hour(
    h,
    *,
    cloud: tuple,
    seeing: float,
    transparency: float,
    darkness: float,
    moon_altitude_deg: float | None,
    moon_illumination_pct: float,
    mode: Mode,
) -> ImagingQuality | None:
    """Score a single forecast hour, or None when it carries no cloud data.

    The scorer refuses to guess at missing cloud cover, which is right — but one
    bad hour must not fail the whole request, so it is caught and reported here.
    """
    try:
        total, low, mid, high = cloud
        return score_hour(
            cloud_cover=total,
            cloud_cover_low=low,
            cloud_cover_mid=mid,
            cloud_cover_high=high,
            seeing=seeing,
            transparency=transparency,
            wind_calm=wind_calm_score(h.wind_speed_kmh),
            moon=moon_score(moon_altitude_deg, moon_illumination_pct),
            darkness=darkness,
            precipitation_mm=h.precipitation_mm,
            precipitation_probability=h.precipitation_probability_pct,
            wind_speed_kmh=h.wind_speed_kmh,
            temperature_c=h.temperature_c,
            dew_point_c=h.dew_point_c,
            mode=mode,
        )
    except ValueError:
        logger.warning("[weather] hour %s has no cloud data - left unscored", h.time)
        return None


def _score_spread(
    h, cloud_models: CloudModelData | None, time_key: str, **score_kw
) -> tuple[ImagingQuality, ImagingQuality] | None:
    """The lowest- and highest-scoring forecast model for one hour.

    Only cloud varies between the runs; everything else is held at the values the
    primary score used, so the range isolates forecast disagreement rather than
    mixing in other differences.

    Returns the full results rather than two numbers so a night can aggregate the
    extremes the same way it aggregates the headline, and label them with the same
    rule — ``Unusable`` depends on availability, not on the score, so it cannot be
    recovered from a bare pair of integers. None with fewer than two models
    covering the hour (ICON's horizon ends before the 8-day window does).
    """
    if cloud_models is None:
        return None
    variants = cloud_models.spread_at(time_key)
    if len(variants) < 2:
        return None
    scored = [q for c in variants if (q := _score_one_hour(h, cloud=c, **score_kw)) is not None]
    if len(scored) < 2:
        return None
    return min(scored, key=lambda q: q.score), max(scored, key=lambda q: q.score)


def _factor_rows(quality: ImagingQuality) -> list[FactorResponse]:
    return [
        FactorResponse(
            key=f.key, role=f.role.value, value=f.value, effect=f.effect, applied=f.applied
        )
        for f in quality.factors
    ]


def _aggregate_factors(scored: list[ImagingQuality]) -> list[FactorResponse]:
    """Mean of each factor across the night, in the model's own row order.

    A factor counts as applied for the night if it applied in any hour, and its
    displayed value averages only the hours where it had one.
    """
    if not scored:
        return []
    rows: list[FactorResponse] = []
    for idx, template in enumerate(scored[0].factors):
        same = [q.factors[idx] for q in scored if idx < len(q.factors)]
        values = [f.value for f in same if f.value is not None]
        rows.append(
            FactorResponse(
                key=template.key,
                role=template.role.value,
                value=round(sum(values) / len(values), 1) if values else None,
                effect=round(sum(f.effect for f in same) / len(same), 4),
                applied=any(f.applied for f in same),
            )
        )
    return rows


def _aggregate_flags(scored: list[ImagingQuality]) -> list[str]:
    """Union of the night's flags, in first-seen order."""
    seen: list[str] = []
    for q in scored:
        for flag in q.flags:
            if flag.value not in seen:
                seen.append(flag.value)
    return seen


def _compute_night_data(
    loc: dict,
    night_date: date,
    tz: ZoneInfo,
    weather: WeatherData,
    pwv_index: NearestMatchIndex,
    aod_index: NearestMatchIndex,
    moon_included: bool,
    cloud_models: CloudModelData | None = None,
) -> DailySummaryResponse | None:
    """Compute a daily summary for one night, driven by actual sunset/sunrise."""
    # Use geographic timezone for astronomy (noon-to-noon search window must
    # align with physical location), fall back to display timezone if unavailable.
    astro_tz = loc.get("geo_timezone") or loc["timezone"]
    try:
        night = compute_night_summary(
            latitude=loc["latitude"],
            longitude=loc["longitude"],
            elevation_m=loc.get("elevation_m"),
            night_date=night_date,
            timezone_str=astro_tz,
        )
    except Exception:
        logger.warning("Skipping %s — astronomy computation failed", night_date)
        return None

    # If no imaging window, return a minimal response
    if night.no_imaging_window:
        return DailySummaryResponse(
            date=night_date.isoformat(),
            imaging_quality=0,
            imaging_quality_label=UNUSABLE_LABEL,
            availability=0.0,
            quality=0.0,
            expected_useful_hours=0.0,
            factors=[],
            flags=[Flag.NO_DARKNESS.value],
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
    # Average the cloud series that is actually scored (the primary model), not
    # the main forecast's — otherwise the card's "avg cloud" contradicts its own
    # Clear Sky factor.
    night_clouds = [_cloud_for(h, cloud_models, h.time) for _, h in hours_data]
    avg_cloud = sum(c[0] for c in night_clouds) / n
    avg_cloud_low = sum(c[1] for c in night_clouds) / n
    avg_cloud_mid = sum(c[2] for c in night_clouds) / n
    avg_cloud_high = sum(c[3] for c in night_clouds) / n
    max_precip_prob = max(
        (h.precipitation_probability_pct or 0 for _, h in hours_data),
        default=0,
    )
    temp_min = min(h.temperature_c for _, h in hours_data)
    temp_max = max(h.temperature_c for _, h in hours_data)

    # Per-hour seeing and transparency: the scorer consumes these hour by hour,
    # so there is deliberately no average taken here any more.
    seeing_scores = []
    for idx, (i, h) in enumerate(hours_data):
        prev_h = hours_data[idx - 1][1] if idx > 0 else None
        seeing_scores.append(_compute_seeing(h, prev_h))

    # Transparency scores (O(log n) per lookup via the prebuilt indexes)
    transparency_scores = []
    for _, h in hours_data:
        pwv_val = pwv_index.lookup(h.time)
        aod_val = aod_index.lookup(h.time)
        transparency_scores.append(_transparency_score(h, pwv_val, aod_val))

    # Score every hour, then aggregate. Scoring the *averaged* inputs once is
    # structurally wrong for a gate product: averaging cloud across the night and
    # then applying (1-f)^k is not the same as aggregating the per-hour yields,
    # and it discards which hours were the good ones — the thing the user is
    # actually deciding about.
    mode = _mode_for(moon_included)
    hour_utcs = [_hour_utc(h, tz) for _, h in hours_data]
    moon_alts = moon_altitudes_at(
        hour_utcs, loc["latitude"], loc["longitude"], loc.get("elevation_m")
    )
    scored: list[ImagingQuality] = []
    in_window: list[ImagingQuality] = []
    spreads: list[tuple[int, int, bool]] = []
    for idx, (_, h) in enumerate(hours_data):
        dark = darkness_fraction(hour_utcs[idx], night.darkness, mode=mode)
        score_kw = dict(
            seeing=seeing_scores[idx],
            transparency=transparency_scores[idx],
            darkness=dark,
            moon_altitude_deg=moon_alts[idx] if idx < len(moon_alts) else None,
            moon_illumination_pct=night.moon.illumination_pct,
            mode=mode,
        )
        hour_quality = _score_one_hour(h, cloud=_cloud_for(h, cloud_models, h.time), **score_kw)
        if hour_quality is None:
            continue
        scored.append(hour_quality)
        if dark > 0.0:
            in_window.append(hour_quality)
            spread = _score_spread(h, cloud_models, h.time, **score_kw)
            if spread is not None:
                spreads.append(spread)

    # The night's headline averages only the hours inside the darkness window —
    # padding a clear twilight hour into the mean would flatter a cloudy night.
    # A fully clouded dark hour still counts, at 0.
    rated = in_window or scored
    if rated:
        night_score = int(round(sum(q.score for q in rated) / len(rated)))
        night_availability = sum(q.availability for q in rated) / len(rated)
        night_quality = sum(q.quality for q in rated) / len(rated)
    else:
        night_score, night_availability, night_quality = 0, 0.0, 0.0
    useful_hours = expected_useful_hours(scored)
    # Aggregate the extremes exactly as the headline is aggregated, then label
    # them with the same rule. The night counts as uncertain only when those two
    # labels differ — i.e. the models disagree about the *verdict*, not merely
    # about the number. Flagging any hour whose extremes cross a boundary marks
    # essentially every night, since a ten-hour night with three models almost
    # always has one such hour, and a flag that is always on says nothing.
    if spreads:
        lows = [lo for lo, _ in spreads]
        highs = [hi for _, hi in spreads]
        night_min = int(round(sum(q.score for q in lows) / len(lows)))
        night_max = int(round(sum(q.score for q in highs) / len(highs)))
        min_label = label_for_score(night_min, sum(q.availability for q in lows) / len(lows))
        max_label = label_for_score(night_max, sum(q.availability for q in highs) / len(highs))
        night_uncertain = (
            min_label != max_label and night_max - night_min >= FORECAST_UNCERTAIN_MIN_SPREAD
        )
    else:
        night_min = night_max = None
        night_uncertain = False

    # Dew safe window — compute from hourly data during darkness
    dew_hourly: list[tuple[str, float, float]] = []
    for _, h in hours_data:
        weather_dt = datetime.fromisoformat(h.time)
        hhmm = weather_dt.strftime("%H:%M")
        dew_hourly.append((hhmm, h.temperature_c, h.dew_point_c))

    dew_window = compute_dew_safe_window(dew_hourly)

    return DailySummaryResponse(
        date=night_date.isoformat(),
        imaging_quality=night_score,
        imaging_quality_label=label_for_score(night_score, night_availability),
        availability=round(night_availability, 4),
        quality=round(night_quality, 1),
        expected_useful_hours=round(useful_hours, 2),
        factors=_aggregate_factors(rated),
        flags=_aggregate_flags(rated),
        score_min=night_min,
        score_max=night_max,
        forecast_uncertain=night_uncertain,
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
    ttl = settings.weather_cache_ttl_hours

    # Fire all three outbound sources concurrently on cache miss: main
    # forecast, PWV, and AOD. _fetch_supplementary_pair already gathers its
    # PWV/AOD pair; nesting that inside the outer gather means all three
    # requests are in flight at the same time.
    weather, (pwv_by_time, aod_by_time), cloud_models = await asyncio.gather(
        _fetch_or_cached(
            location_id=loc["id"],
            latitude=loc["latitude"],
            longitude=loc["longitude"],
            timezone_str=loc["timezone"],
            source="forecast",
            ttl_hours=ttl,
        ),
        _fetch_supplementary_pair(loc, ttl_hours=ttl),
        _fetch_or_cached_cloud_models(
            location_id=loc["id"],
            latitude=loc["latitude"],
            longitude=loc["longitude"],
            timezone_str=loc["timezone"],
            ttl_hours=ttl,
        ),
    )

    tz = ZoneInfo(loc["timezone"])

    now_local = datetime.now(tz)
    start_date = now_local.date()

    # Build nearest-match indexes once; 7 night-computations reuse them.
    pwv_index = NearestMatchIndex(pwv_by_time)
    aod_index = NearestMatchIndex(aod_by_time)

    days: list[DailySummaryResponse] = []
    for offset in range(8):  # try up to 8 days to get 7 valid nights
        d = start_date + timedelta(days=offset)
        result = _compute_night_data(
            loc,
            d,
            tz,
            weather,
            pwv_index,
            aod_index,
            moon_included,
            cloud_models,
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
        geo_timezone=loc.get("geo_timezone"),
        moon_included=moon_included,
        days=days,
    )


@router.get("/hourly", response_model=HourlyDetailResponse)
async def get_hourly(
    location_id: int = Query(..., description="Location ID"),
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    include_moon: bool | None = Query(None, description="Include moon penalty in quality score"),
):
    """Hourly weather detail for a specific night."""
    loc = await _get_location(location_id)
    settings = await get_settings()
    moon_included = include_moon if include_moon is not None else settings.weather_moon_penalty
    ttl = settings.weather_cache_ttl_hours
    try:
        night_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format, expected YYYY-MM-DD")

    # All three sources fetched concurrently on cache miss.
    weather, (pwv_by_time, aod_by_time), cloud_models = await asyncio.gather(
        _fetch_or_cached(
            location_id=loc["id"],
            latitude=loc["latitude"],
            longitude=loc["longitude"],
            timezone_str=loc["timezone"],
            source="forecast",
            ttl_hours=ttl,
        ),
        _fetch_supplementary_pair(loc, ttl_hours=ttl),
        _fetch_or_cached_cloud_models(
            location_id=loc["id"],
            latitude=loc["latitude"],
            longitude=loc["longitude"],
            timezone_str=loc["timezone"],
            ttl_hours=ttl,
        ),
    )

    tz = ZoneInfo(loc["timezone"])
    astro_tz = loc.get("geo_timezone") or loc["timezone"]

    astro_hours = compute_hourly_astro(
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        elevation_m=loc.get("elevation_m"),
        night_date=night_date,
        timezone_str=astro_tz,
    )
    night = compute_night_summary(
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        elevation_m=loc.get("elevation_m"),
        night_date=night_date,
        timezone_str=astro_tz,
    )

    # If no imaging window (polar conditions), return minimal response
    if night.no_imaging_window or night.sunset is None or night.sunrise is None:
        return HourlyDetailResponse(
            date=date,
            location_id=loc["id"],
            location_name=loc["name"],
            timezone=loc["timezone"],
            geo_timezone=loc.get("geo_timezone"),
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

    # Index astro data by absolute UTC instant. Weather hours are labelled in the
    # display timezone while astro is computed in the site (geo) timezone, so a
    # wall-clock "HH:MM" join would misalign whenever the two zones differ (the
    # supported remote-observatory setup). Match on the absolute moment instead.
    astro_sorted = sorted(astro_hours, key=lambda a: a.time_utc)
    astro_utc_dts = [a.time_utc for a in astro_sorted]

    def _astro_at(utc_dt: datetime):
        """Nearest astro entry to an absolute UTC instant, within ~half an hour.

        With the padded hourly grids the match is exact when display and geo
        timezones share whole-hour offsets, and at most ~30 min apart for the
        rare fractional-offset zones.
        """
        if not astro_utc_dts:
            return None
        idx = bisect.bisect_left(astro_utc_dts, utc_dt)
        best = None
        best_gap = timedelta(minutes=31)
        for i in (idx - 1, idx):
            if 0 <= i < len(astro_utc_dts):
                gap = abs(astro_utc_dts[i] - utc_dt)
                if gap < best_gap:
                    best_gap = gap
                    best = astro_sorted[i]
        return best

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

    # Build nearest-match indexes once; reused for every hour below.
    pwv_index = NearestMatchIndex(pwv_by_time)
    aod_index = NearestMatchIndex(aod_by_time)

    mode = _mode_for(moon_included)
    hours: list[HourlyWeatherResponse] = []
    for idx, (i, h) in enumerate(matched):
        prev_h = matched[idx - 1][1] if idx > 0 else None
        seeing = _compute_seeing(h, prev_h)

        # Weather timestamps are naive local time in the display timezone;
        # resolve to UTC before matching against the astro series.
        weather_dt = datetime.fromisoformat(h.time).replace(tzinfo=tz)
        astro = _astro_at(weather_dt.astimezone(UTC))

        # Transparency (PWV and AOD via O(log n) lookup on prebuilt indexes)
        pwv_val = pwv_index.lookup(h.time)
        aod_val = aod_index.lookup(h.time)
        transparency = _transparency_score(h, pwv_val, aod_val)

        # Dew risk
        dew_risk = classify_dew_risk(h.temperature_c, h.dew_point_c)

        # Moon illumination comes from the same astro entry as the altitude —
        # the nightly figure was previously used here while the hourly one was
        # emitted in the response, i.e. two sources for one quantity.
        moon_alt = astro.moon_altitude_deg if astro else None
        moon_illum = astro.moon_illumination_pct if astro else night.moon.illumination_pct
        score_kw = dict(
            seeing=seeing,
            transparency=transparency,
            darkness=darkness_fraction(weather_dt.astimezone(UTC), night.darkness, mode=mode),
            moon_altitude_deg=moon_alt,
            moon_illumination_pct=moon_illum,
            mode=mode,
        )
        hour_cloud = _cloud_for(h, cloud_models, h.time)
        quality = _score_one_hour(h, cloud=hour_cloud, **score_kw)
        if quality is None:
            continue
        spread = _score_spread(h, cloud_models, h.time, **score_kw)

        hours.append(
            HourlyWeatherResponse(
                time=h.time,
                temperature_c=h.temperature_c,
                dew_point_c=h.dew_point_c,
                humidity_pct=h.humidity_pct,
                # The cloud series that was scored, which is the primary model
                # rather than the main forecast. Emitting `h`'s values here made
                # the panel contradict itself: a "Clear Sky 30" factor sitting
                # above a "Cloud (total) 0%" raw row.
                cloud_cover_pct=hour_cloud[0],
                cloud_cover_low_pct=hour_cloud[1],
                cloud_cover_mid_pct=hour_cloud[2],
                cloud_cover_high_pct=hour_cloud[3],
                wind_speed_kmh=h.wind_speed_kmh,
                wind_direction_deg=h.wind_direction_deg,
                wind_gusts_kmh=h.wind_gusts_kmh,
                visibility_m=h.visibility_m,
                precipitation_mm=h.precipitation_mm,
                precipitation_probability_pct=h.precipitation_probability_pct,
                pwv_mm=pwv_val,
                aod=aod_val,
                dew_risk=dew_risk,
                imaging_quality=quality.score,
                imaging_quality_label=quality.label,
                availability=round(quality.availability, 4),
                quality=round(quality.quality, 1),
                factors=_factor_rows(quality),
                flags=[f.value for f in quality.flags],
                score_min=spread[0].score if spread else None,
                score_max=spread[1].score if spread else None,
                forecast_uncertain=bool(
                    spread
                    and spread[0].label != spread[1].label
                    and spread[1].score - spread[0].score >= FORECAST_UNCERTAIN_MIN_SPREAD
                ),
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
        timezone=loc["timezone"],
        geo_timezone=loc.get("geo_timezone"),
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


@router.get("/cache/stats")
async def weather_cache_stats() -> dict:
    """Return row count and approximate byte size of the weather_cache table."""
    async with get_db() as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM weather_cache")
        rows = (await cursor.fetchone())[0]

        try:
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(pgsize), 0) FROM dbstat WHERE name = 'weather_cache'"
            )
            bytes_used = (await cursor.fetchone())[0]
        except Exception:
            # dbstat not available — estimate from stored JSON
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(LENGTH(response_json)), 0) FROM weather_cache"
            )
            bytes_used = (await cursor.fetchone())[0]

    return {"rows": rows, "bytes": bytes_used}


@router.delete("/cache")
async def clear_weather_cache() -> dict:
    """Delete all cached weather, PWV, and AOD data. Next forecast request will re-fetch."""
    async with get_db() as conn:
        cursor = await conn.execute("DELETE FROM weather_cache")
        deleted = cursor.rowcount
        await conn.commit()
    logger.info("[weather-cache] CLEAR — deleted %s rows", deleted)
    return {"ok": True, "deleted": deleted}
