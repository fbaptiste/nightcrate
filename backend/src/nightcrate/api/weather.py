"""Weather forecast API — personal imaging verdicts from traceable rules."""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from nightcrate.api.imaging_rules import load_rules
from nightcrate.api.weather_methodology import METHODOLOGY_DETAILS, METHODOLOGY_SUMMARY
from nightcrate.api.weather_models import (
    CoverageResponse,
    ExpectedFieldsResponse,
    ExtremesResponse,
    ForecastRequest,
    ForecastResponse,
    HourResponse,
    IntervalResponse,
    MethodologyResponse,
    NightControlsRequest,
    NightResponse,
    ReasonResponse,
    StaleSourcesResponse,
)
from nightcrate.core.config import get_settings
from nightcrate.db.session import get_db
from nightcrate.services.astronomy import (
    NightSummary,
    compute_night_summary,
    dark_intervals_for,
    moon_altitudes_at,
)
from nightcrate.services.forecast_coverage import (
    coarse_cloud_from,
    last_expected_stamp,
    parse_model_meta,
    requested_range,
)
from nightcrate.services.forecast_inputs import build_hours
from nightcrate.services.imaging_rules import (
    ImagingRules,
    RainPolicy,
    selected_cloud_models,
)
from nightcrate.services.imaging_types import (
    HourInput,
    HourResult,
    NightControls,
    NightInput,
    Reason,
)
from nightcrate.services.imaging_verdict import evaluate_night
from nightcrate.services.seeing import (
    estimate_seeing_surface,
    estimate_seeing_wind_shear,
    score_label,
)
from nightcrate.services.transparency import estimate_transparency
from nightcrate.services.weather import (
    CLOUD_REQUEST_MODELS,
    CLOUD_SPREAD_MODELS,
    FORECAST_DAYS,
    FORECAST_NIGHTS,
    META_DOMAINS,
    CloudModelData,
    HourlyWeather,
    NearestMatchIndex,
    SupplementaryData,
    WeatherData,
    fetch_air_quality,
    fetch_cloud_models,
    fetch_model_meta,
    fetch_pwv,
    fetch_weather,
    parse_cloud_models,
    parse_hourly,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/weather", tags=["Weather"])


@dataclass(frozen=True)
class ForecastData:
    weather: WeatherData
    cloud_models: CloudModelData | None
    pwv_by_time: dict[datetime, float | None]
    aod_by_time: dict[datetime, float | None]
    fetched_at: datetime
    forecast_attempted_at: datetime
    cloud_fetched_at: datetime | None
    cloud_attempted_at: datetime
    meta_raw: str | None
    forecast_stale_minutes: int | None
    cloud_stale_minutes: int | None


@dataclass(frozen=True)
class _CachedWeather:
    data: WeatherData
    fetched_at: datetime
    stale_minutes: int | None
    attempted_at: datetime


@dataclass(frozen=True)
class _CachedCloud:
    data: CloudModelData | None
    fetched_at: datetime | None
    stale_minutes: int | None
    meta_raw: str | None
    attempted_at: datetime


_repair_attempts: dict[tuple[int, str], datetime] = {}
_refresh_failures: dict[tuple[int, str], datetime] = {}
_cache_locks: dict[tuple[int, str], asyncio.Lock] = {}
_REPAIR_INTERVAL = timedelta(hours=1)
_REFRESH_FAILURE_COOLDOWN = timedelta(minutes=10)


def _now() -> datetime:
    """The sole wall clock for forecast evaluation and cache freshness."""
    return datetime.now(UTC)


def _db_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _stale_minutes(fetched_at: datetime, now: datetime) -> int:
    return max(0, int(round((now - fetched_at).total_seconds() / 60.0)))


def _on_hour_grid(times: list[datetime]) -> bool:
    return all(
        value.tzinfo is not None
        and value.utcoffset() is not None
        and value.minute == 0
        and value.second == 0
        and value.microsecond == 0
        for value in times
    )


def _weather_from_raw(raw_json: str, source: str) -> WeatherData:
    raw = json.loads(raw_json)
    hourly = parse_hourly(
        raw.get("hourly", {}),
        source,
        int(raw.get("utc_offset_seconds", 0)),
    )
    if not _on_hour_grid([hour.time_utc for hour in hourly]):
        raise ValueError("cached weather timestamps are off the whole-UTC-hour grid")
    return WeatherData(
        latitude=float(raw.get("latitude", 0.0)),
        longitude=float(raw.get("longitude", 0.0)),
        source=source,
        hourly=hourly,
        raw_json=raw_json,
    )


def _cloud_from_raw(raw_json: str) -> CloudModelData:
    raw = json.loads(raw_json)
    models = parse_cloud_models(
        raw.get("hourly", {}),
        CLOUD_REQUEST_MODELS,
        int(raw.get("utc_offset_seconds", 0)),
    )
    times = [
        stamp
        for series in models.values()
        for field in (
            series.cloud_total_pct,
            series.cloud_low_pct,
            series.cloud_mid_pct,
            series.cloud_high_pct,
            series.precipitation_mm,
        )
        for stamp in field
    ]
    if not _on_hour_grid(times):
        raise ValueError("cached cloud timestamps are off the whole-UTC-hour grid")
    return CloudModelData(models=models, raw_json=raw_json)


def _supplementary_from_raw(raw_json: str) -> dict[datetime, float | None]:
    raw = json.loads(raw_json)
    hourly = raw.get("hourly", {})
    key = next((name for name in hourly if name != "time"), None)
    if key is None:
        return {}
    offset = int(raw.get("utc_offset_seconds", 0))
    synthetic = {
        "time": hourly.get("time", []),
        "temperature_2m": hourly.get(key, []),
    }
    parsed = parse_hourly(synthetic, "archive", offset)
    result = {hour.time_utc: hour.temperature_c for hour in parsed}
    if not _on_hour_grid(list(result)):
        raise ValueError("cached supplementary timestamps are off the whole-UTC-hour grid")
    return result


async def _cache_row(location_id: int, source: str) -> Any | None:
    async with get_db() as conn:
        cursor = await conn.execute(
            """SELECT response_json, fetched_at, source FROM weather_cache
               WHERE location_id = ? AND source = ?
               ORDER BY fetched_at DESC LIMIT 1""",
            (location_id, source),
        )
        return await cursor.fetchone()


async def _cloud_cache_rows(location_id: int) -> dict[str, Any]:
    """Read the cloud payload and its metadata candidate in one statement."""
    async with get_db() as conn:
        cursor = await conn.execute(
            """SELECT response_json, fetched_at, source FROM weather_cache
               WHERE location_id = ? AND source IN ('cloud_models', 'model_meta')""",
            (location_id,),
        )
        return {row["source"]: row for row in await cursor.fetchall()}


def _cache_timestamp(fetched_at: datetime) -> str:
    return fetched_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


async def _write_cache(location_id: int, source: str, raw_json: str, fetched_at: datetime) -> None:
    try:
        async with get_db() as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO weather_cache
                   (location_id, source, start_date, end_date, response_json, fetched_at)
                   VALUES (?, ?, '', '', ?, ?)""",
                (
                    location_id,
                    source,
                    raw_json,
                    _cache_timestamp(fetched_at),
                ),
            )
            await conn.commit()
    except Exception:
        logger.warning("[weather-cache] write failed source=%s location=%s", source, location_id)


async def _write_cloud_cache(
    location_id: int,
    cloud_raw: str,
    meta_domains_raw: str | None,
    fetched_at: datetime,
) -> None:
    """Atomically replace the cloud row and its generation-bound metadata row."""
    meta_payload: str | None = None
    if meta_domains_raw is not None:
        try:
            domains = json.loads(meta_domains_raw)
            if not isinstance(domains, dict):
                raise ValueError("model metadata must be a JSON object")
            meta_payload = json.dumps(
                {
                    "cloud_sha256": hashlib.sha256(cloud_raw.encode()).hexdigest(),
                    "domains": domains,
                }
            )
        except TypeError, ValueError, json.JSONDecodeError:
            logger.warning("[weather-cache] invalid model metadata location=%s", location_id)

    stamp = _cache_timestamp(fetched_at)
    try:
        async with get_db() as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO weather_cache
                   (location_id, source, start_date, end_date, response_json, fetched_at)
                   VALUES (?, 'cloud_models', '', '', ?, ?)""",
                (location_id, cloud_raw, stamp),
            )
            if meta_payload is None:
                await conn.execute(
                    "DELETE FROM weather_cache WHERE location_id = ? AND source = 'model_meta'",
                    (location_id,),
                )
            else:
                await conn.execute(
                    """INSERT OR REPLACE INTO weather_cache
                       (location_id, source, start_date, end_date, response_json, fetched_at)
                       VALUES (?, 'model_meta', '', '', ?, ?)""",
                    (location_id, meta_payload, stamp),
                )
            await conn.commit()
    except Exception:
        logger.warning("[weather-cache] cloud pair write failed location=%s", location_id)


def _paired_meta_raw(cloud_row: Any, meta_row: Any | None) -> str | None:
    if meta_row is None or _db_datetime(meta_row["fetched_at"]) != _db_datetime(
        cloud_row["fetched_at"]
    ):
        return None
    try:
        payload = json.loads(meta_row["response_json"])
        domains = payload["domains"]
        if not isinstance(domains, dict):
            return None
        expected_hash = hashlib.sha256(cloud_row["response_json"].encode()).hexdigest()
        if payload["cloud_sha256"] != expected_hash:
            return None
        return json.dumps(domains)
    except KeyError, TypeError, ValueError, json.JSONDecodeError:
        return None


def _last_requested(fetched_at: datetime) -> datetime:
    return requested_range(fetched_at, forecast_days=FORECAST_DAYS, past_days=1)[1]


def _last_non_null_weather(data: WeatherData, attribute: str) -> datetime | None:
    return max(
        (row.time_utc for row in data.hourly if getattr(row, attribute) is not None),
        default=None,
    )


def _weather_complete(data: WeatherData, fetched_at: datetime) -> bool:
    expected = last_expected_stamp("best_match", fetched_at, _last_requested(fetched_at))
    fields = (
        "cloud_cover_pct",
        "precipitation_mm",
        "precipitation_probability_pct",
        "wind_speed_kmh",
        "wind_gusts_kmh",
        "temperature_c",
        "dew_point_c",
    )
    return all(
        (last := _last_non_null_weather(data, field)) is not None and last >= expected
        for field in fields
    )


def _last_non_null(series: dict[datetime, float | None]) -> datetime | None:
    return max((stamp for stamp, value in series.items() if value is not None), default=None)


def _cloud_modern(data: CloudModelData) -> bool:
    return all(
        model in data.models
        and {"cloud_cover", "precipitation"} <= data.models[model].fields_present
        for model in CLOUD_SPREAD_MODELS
    )


def _cloud_complete(data: CloudModelData, fetched_at: datetime) -> bool:
    last_requested = _last_requested(fetched_at)
    for model in CLOUD_SPREAD_MODELS:
        series = data.models.get(model)
        if series is None:
            return False
        expected = last_expected_stamp(model, fetched_at, last_requested)
        for field in (series.cloud_total_pct, series.precipitation_mm):
            last = _last_non_null(field)
            if last is None or last < expected:
                return False
    return True


def _repair_allowed(key: tuple[int, str], now: datetime) -> bool:
    previous = _repair_attempts.get(key)
    return previous is None or now - previous >= _REPAIR_INTERVAL


def _refresh_allowed_after_failure(key: tuple[int, str], now: datetime) -> bool:
    previous = _refresh_failures.get(key)
    return previous is None or now - previous >= _REFRESH_FAILURE_COOLDOWN


def _cache_lock(key: tuple[int, str]) -> asyncio.Lock:
    return _cache_locks.setdefault(key, asyncio.Lock())


async def _fetch_or_cached(
    location_id: int,
    latitude: float,
    longitude: float,
    timezone_str: str,
    source: str = "forecast",
    start_date: str | None = None,
    end_date: str | None = None,
    ttl_hours: int | None = None,
) -> _CachedWeather:
    """Load fresh weather, or serve the newest valid stale row after fetch failure."""
    del start_date, end_date
    if ttl_hours is None:
        ttl_hours = (await get_settings()).weather_cache_ttl_hours
    now = _now()

    def decode(row: Any | None) -> tuple[WeatherData | None, datetime | None]:
        if row is None:
            return None, None
        fetched_at: datetime | None = None
        try:
            fetched_at = _db_datetime(row["fetched_at"])
            return _weather_from_raw(row["response_json"], row["source"]), fetched_at
        except KeyError, TypeError, ValueError, json.JSONDecodeError:
            logger.info("[weather-cache] IGNORE invalid %s location=%s", source, location_id)
            return None, fetched_at

    def current(cached: WeatherData | None, fetched_at: datetime | None) -> bool:
        return (
            cached is not None
            and fetched_at is not None
            and _stale_minutes(fetched_at, now) <= ttl_hours * 60
            and _weather_complete(cached, fetched_at)
        )

    def fallback(
        cached: WeatherData | None,
        fetched_at: datetime | None,
        *,
        stale: bool,
        exc: Exception | None = None,
    ) -> _CachedWeather:
        if cached is None or fetched_at is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Forecast unavailable — Open-Meteo could not be reached and nothing is cached"
                ),
            ) from exc
        stale_minutes = _stale_minutes(fetched_at, now) if stale else None
        return _CachedWeather(cached, fetched_at, stale_minutes, now)

    async def refresh(*, stale_fallback: bool) -> _CachedWeather:
        _repair_attempts[key] = now
        logger.info("[weather-cache] MISS %s location=%s", source, location_id)
        try:
            data = await fetch_weather(latitude, longitude, timezone_str, source="forecast")
        except Exception as exc:
            _refresh_failures[key] = now
            return fallback(cached, fetched_at, stale=stale_fallback, exc=exc)
        _refresh_failures.pop(key, None)
        await _write_cache(location_id, source, data.raw_json, now)
        return _CachedWeather(data, now, None, now)

    key = (location_id, source)
    row = await _cache_row(location_id, source)
    cached, fetched_at = decode(row)
    if current(cached, fetched_at):
        logger.debug("[weather-cache] HIT %s location=%s", source, location_id)
        return _CachedWeather(cached, fetched_at, None, now)  # type: ignore[arg-type]

    async with _cache_lock(key):
        row = await _cache_row(location_id, source)
        cached, fetched_at = decode(row)
        if current(cached, fetched_at):
            return _CachedWeather(cached, fetched_at, None, now)  # type: ignore[arg-type]
        within_ttl = fetched_at is not None and _stale_minutes(fetched_at, now) <= ttl_hours * 60
        if not _refresh_allowed_after_failure(key, now):
            return fallback(cached, fetched_at, stale=not within_ttl)
        if within_ttl and not _repair_allowed(key, now):
            return fallback(cached, fetched_at, stale=False)
        return await refresh(stale_fallback=not within_ttl)


async def _fetch_or_cached_cloud_models(
    location_id: int,
    latitude: float,
    longitude: float,
    timezone_str: str,
    ttl_hours: int | None = None,
) -> _CachedCloud:
    """Load cloud models with an independent stale fallback."""
    if ttl_hours is None:
        ttl_hours = (await get_settings()).weather_cache_ttl_hours
    now = _now()

    def decode(
        rows: dict[str, Any],
    ) -> tuple[CloudModelData | None, datetime | None, str | None, bool, bool]:
        cloud_row = rows.get("cloud_models")
        if cloud_row is None:
            return None, None, None, False, False
        fetched_at: datetime | None = None
        try:
            fetched_at = _db_datetime(cloud_row["fetched_at"])
            cached = _cloud_from_raw(cloud_row["response_json"])
            modern = _cloud_modern(cached)
            complete = modern and _cloud_complete(cached, fetched_at)
            return (
                cached,
                fetched_at,
                _paired_meta_raw(cloud_row, rows.get("model_meta")),
                modern,
                complete,
            )
        except KeyError, TypeError, ValueError, json.JSONDecodeError:
            logger.info("[weather-cache] IGNORE invalid cloud_models location=%s", location_id)
            return None, fetched_at, None, False, False

    def current(
        fetched_at: datetime | None, meta_raw: str | None, modern: bool, complete: bool
    ) -> bool:
        return (
            fetched_at is not None
            and _stale_minutes(fetched_at, now) <= ttl_hours * 60
            and meta_raw is not None
            and modern
            and complete
        )

    def fallback(*, stale: bool) -> _CachedCloud:
        if not modern or cached is None or fetched_at is None:
            return _CachedCloud(None, None, None, None, now)
        stale_minutes = _stale_minutes(fetched_at, now) if stale else None
        return _CachedCloud(
            cached,
            fetched_at,
            stale_minutes,
            meta_raw,
            now,
        )

    async def refresh(*, stale_fallback: bool) -> _CachedCloud:
        _repair_attempts[key] = now
        cloud_result, meta_result = await asyncio.gather(
            fetch_cloud_models(latitude, longitude, timezone_str),
            fetch_model_meta(),
            return_exceptions=True,
        )
        if isinstance(cloud_result, asyncio.CancelledError):
            raise cloud_result
        if isinstance(cloud_result, Exception):
            logger.warning("[weather] cloud-model refresh failed location=%s", location_id)
            _refresh_failures[key] = now
            return fallback(stale=stale_fallback)
        _refresh_failures.pop(key, None)
        if isinstance(meta_result, asyncio.CancelledError):
            raise meta_result
        meta_domains_raw = None if isinstance(meta_result, Exception) else meta_result
        if meta_domains_raw is None:
            logger.warning("[weather] model-metadata refresh failed location=%s", location_id)
        await _write_cloud_cache(location_id, cloud_result.raw_json, meta_domains_raw, now)
        return _CachedCloud(cloud_result, now, None, meta_domains_raw, now)

    key = (location_id, "cloud_models")
    rows = await _cloud_cache_rows(location_id)
    cached, fetched_at, meta_raw, modern, complete = decode(rows)
    if current(fetched_at, meta_raw, modern, complete):
        return _CachedCloud(cached, fetched_at, None, meta_raw, now)

    async with _cache_lock(key):
        rows = await _cloud_cache_rows(location_id)
        cached, fetched_at, meta_raw, modern, complete = decode(rows)
        if current(fetched_at, meta_raw, modern, complete):
            return _CachedCloud(cached, fetched_at, None, meta_raw, now)
        within_ttl = fetched_at is not None and _stale_minutes(fetched_at, now) <= ttl_hours * 60
        if not _refresh_allowed_after_failure(key, now):
            return fallback(stale=not within_ttl)
        if within_ttl and not _repair_allowed(key, now):
            return fallback(stale=False)
        return await refresh(stale_fallback=not within_ttl)


async def _fetch_or_cached_supplementary(
    location_id: int,
    latitude: float,
    longitude: float,
    timezone_str: str,
    source_key: str,
    fetch_fn,
    ttl_hours: int | None = None,
) -> dict[datetime, float | None]:
    """Load context-only supplementary data; stale rows remain usable."""
    if ttl_hours is None:
        ttl_hours = (await get_settings()).weather_cache_ttl_hours
    now = _now()

    def decode(row: Any | None) -> tuple[dict[datetime, float | None] | None, datetime | None]:
        if row is None:
            return None, None
        try:
            return _supplementary_from_raw(row["response_json"]), _db_datetime(row["fetched_at"])
        except KeyError, TypeError, ValueError, json.JSONDecodeError:
            return None, None

    def current(cached: dict[datetime, float | None] | None, fetched_at: datetime | None) -> bool:
        return (
            cached is not None
            and fetched_at is not None
            and _stale_minutes(fetched_at, now) <= ttl_hours * 60
        )

    key = (location_id, source_key)
    row = await _cache_row(location_id, source_key)
    cached, fetched_at = decode(row)
    if current(cached, fetched_at):
        return cached  # type: ignore[return-value]

    async with _cache_lock(key):
        row = await _cache_row(location_id, source_key)
        cached, fetched_at = decode(row)
        if current(cached, fetched_at):
            return cached  # type: ignore[return-value]
        if not _refresh_allowed_after_failure(key, now):
            return cached or {}
        try:
            data: SupplementaryData = await fetch_fn(latitude, longitude, timezone_str)
        except Exception:
            logger.warning("[weather] supplementary refresh failed source=%s", source_key)
            _refresh_failures[key] = now
            return cached or {}
        _refresh_failures.pop(key, None)
        await _write_cache(location_id, source_key, data.raw_json, now)
        return data.values_by_time


async def _fetch_supplementary_pair(
    loc: dict,
    ttl_hours: int,
) -> tuple[dict[datetime, float | None], dict[datetime, float | None]]:
    return await asyncio.gather(
        _fetch_or_cached_supplementary(
            loc["id"],
            loc["latitude"],
            loc["longitude"],
            loc["timezone"],
            "ecmwf_pwv",
            fetch_pwv,
            ttl_hours,
        ),
        _fetch_or_cached_supplementary(
            loc["id"],
            loc["latitude"],
            loc["longitude"],
            loc["timezone"],
            "openmeteo_aq",
            fetch_air_quality,
            ttl_hours,
        ),
    )


async def _load_forecast_data(loc: dict, ttl: int) -> ForecastData:
    """Load all forecast sources, retaining freshness independently."""
    weather_result, cloud_result, supplementary = await asyncio.gather(
        _fetch_or_cached(
            loc["id"], loc["latitude"], loc["longitude"], loc["timezone"], ttl_hours=ttl
        ),
        _fetch_or_cached_cloud_models(
            loc["id"], loc["latitude"], loc["longitude"], loc["timezone"], ttl
        ),
        _fetch_supplementary_pair(loc, ttl),
    )
    if cloud_result is None:  # the test-suite network guard uses this documented fallback
        cloud_result = _CachedCloud(None, None, None, None, _now())
    pwv, aod = supplementary
    return ForecastData(
        weather=weather_result.data,
        cloud_models=cloud_result.data,
        pwv_by_time=pwv,
        aod_by_time=aod,
        fetched_at=weather_result.fetched_at,
        forecast_attempted_at=weather_result.attempted_at,
        cloud_fetched_at=cloud_result.fetched_at,
        cloud_attempted_at=cloud_result.attempted_at,
        meta_raw=cloud_result.meta_raw,
        forecast_stale_minutes=weather_result.stale_minutes,
        cloud_stale_minutes=cloud_result.stale_minutes,
    )


def _floor_hour(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _ceil_hour(value: datetime) -> datetime:
    floor = _floor_hour(value)
    return floor if value.astimezone(UTC) == floor else floor + timedelta(hours=1)


def _fmt_time(value: datetime | None, timezone: ZoneInfo) -> str | None:
    return value.astimezone(timezone).strftime("%H:%M") if value is not None else None


def _is_single_model(
    cloud_combination: str,
    cloud_models_used: tuple[str, ...],
) -> bool:
    """Whether at most one selected forecast participated in the decision."""
    return cloud_combination == "single" or len(cloud_models_used) <= 1


def _night_bounds(night_date: date, timezone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime(
        night_date.year,
        night_date.month,
        night_date.day,
        12,
        tzinfo=timezone,
    )
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def _contains(intervals: list[tuple[datetime, datetime]], value: datetime) -> bool:
    return any(start <= value < end for start, end in intervals)


def _darkness_category(summary: NightSummary, midpoint: datetime) -> str:
    if _contains(summary.dark_intervals["astronomical"], midpoint):
        return "astro"
    if _contains(summary.dark_intervals["nautical"], midpoint):
        return "nautical"
    if _contains(summary.dark_intervals["civil"], midpoint):
        return "civil"
    return "day"


def _compute_seeing(hour: HourlyWeather | None, previous: HourlyWeather | None) -> int | None:
    if hour is None:
        return None
    previous_temperature = previous.temperature_c if previous is not None else None
    shear = estimate_seeing_wind_shear(
        wind_speed_200hpa_kmh=hour.wind_speed_200hpa_kmh,
        wind_speed_300hpa_kmh=hour.wind_speed_300hpa_kmh,
        wind_speed_500hpa_kmh=hour.wind_speed_500hpa_kmh,
        geopotential_200hpa_m=hour.geopotential_200hpa_m,
        geopotential_300hpa_m=hour.geopotential_300hpa_m,
        geopotential_500hpa_m=hour.geopotential_500hpa_m,
        temperature_c=hour.temperature_c,
        dew_point_c=hour.dew_point_c,
        humidity_pct=hour.humidity_pct,
        wind_speed_surface_kmh=hour.wind_speed_kmh,
        prev_temperature_c=previous_temperature,
    )
    if shear is not None:
        return shear
    return estimate_seeing_surface(
        temperature_c=hour.temperature_c,
        dew_point_c=hour.dew_point_c,
        humidity_pct=hour.humidity_pct,
        wind_speed_kmh=hour.wind_speed_kmh,
        prev_temperature_c=previous_temperature,
    )


def _interval_response(
    interval: tuple[datetime, datetime] | None, timezone: ZoneInfo
) -> IntervalResponse | None:
    if interval is None:
        return None
    start, end = interval
    return IntervalResponse(
        start=_fmt_time(start, timezone) or "",
        end=_fmt_time(end, timezone) or "",
        start_utc=start,
        end_utc=end,
    )


def _reason_response(reason: Reason, timezone: ZoneInfo) -> ReasonResponse:
    return ReasonResponse(
        code=reason.code,
        start=_fmt_time(reason.start_utc, timezone),
        end=_fmt_time(reason.end_utc, timezone),
        start_utc=reason.start_utc,
        end_utc=reason.end_utc,
        value=reason.value,
        limit=reason.limit,
        requirement=reason.requirement,
        models=reason.models,
        bound=reason.bound,
        model=reason.model,
        missing_hours=reason.missing_hours,
    )


def _maximum(
    pairs: list[tuple[datetime, float | None]],
) -> tuple[float | None, datetime | None]:
    known = [(time, value) for time, value in pairs if value is not None]
    if not known:
        return None, None
    time, value = max(known, key=lambda item: item[1])
    return value, time


def _minimum(
    pairs: list[tuple[datetime, float | None]],
) -> tuple[float | None, datetime | None]:
    known = [(time, value) for time, value in pairs if value is not None]
    if not known:
        return None, None
    time, value = min(known, key=lambda item: item[1])
    return value, time


def _extremes(
    inputs: list[HourInput],
    results: list[HourResult],
    rain_policy: RainPolicy,
    timezone: ZoneInfo,
) -> ExtremesResponse:
    # Rain is judged over the gear-out interval under "night off" and over
    # dark hours under "hours lost", matching the evaluator's rain requirement.
    rain = [
        (source.start_utc, source)
        for source, result in zip(inputs, results, strict=True)
        if (result.exposure_minutes > 0 if rain_policy == "night_off" else result.dark_minutes > 0)
        and not result.elapsed
    ]
    dark = [
        (source.start_utc, source, result)
        for source, result in zip(inputs, results, strict=True)
        if result.dark_minutes > 0 and not result.elapsed and not result.excluded
    ]
    probability, probability_at = _maximum(
        [(time, source.precip_probability_pct) for time, source in rain]
    )
    gust, gust_at = _maximum([(time, source.gust_kmh) for time, source, _ in dark])
    dew, dew_at = _minimum([(time, result.dew_spread_c) for time, _, result in dark])
    amounts = [source.precip_mm for _, source in rain if source.precip_mm is not None]
    missing_amounts = sum(source.precip_mm is None for _, source in rain)
    sum_start = rain[0][0] if rain else None
    sum_end = rain[-1][0] + timedelta(hours=1) if rain else None
    return ExtremesResponse(
        max_precip_probability_pct=probability,
        max_precip_probability_at=_fmt_time(probability_at, timezone),
        max_precip_probability_at_utc=probability_at,
        precip_mm_total=sum(amounts) if amounts else None,
        precip_missing_hours=missing_amounts,
        precip_sum_start=_fmt_time(sum_start, timezone),
        precip_sum_end=_fmt_time(sum_end, timezone),
        precip_sum_start_utc=sum_start,
        precip_sum_end_utc=sum_end,
        max_gust_kmh=gust,
        max_gust_at=_fmt_time(gust_at, timezone),
        max_gust_at_utc=gust_at,
        min_dew_spread_c=dew,
        min_dew_spread_at=_fmt_time(dew_at, timezone),
        min_dew_spread_at_utc=dew_at,
    )


def _hour_responses(
    inputs: list[HourInput],
    results: list[HourResult],
    summary: NightSummary,
    primary_model: str,
    weather_by_time: dict[datetime, HourlyWeather],
    pwv_index: NearestMatchIndex,
    aod_index: NearestMatchIndex,
    display_timezone: ZoneInfo,
) -> list[HourResponse]:
    responses: list[HourResponse] = []
    for source, result in zip(inputs, results, strict=True):
        row = weather_by_time.get(source.start_utc)
        previous = weather_by_time.get(source.start_utc - timedelta(hours=1))
        model = source.models[primary_model]
        figures = (model.cloud_total_pct, *model.cloud_layers_pct)
        transparency = estimate_transparency(
            pwv_mm=pwv_index.lookup(source.start_utc),
            aod=aod_index.lookup(source.start_utc),
            humidity_pct=row.humidity_pct if row is not None else None,
            visibility_m=row.visibility_m if row is not None else None,
        )
        responses.append(
            HourResponse(
                time=source.start_utc.astimezone(display_timezone).strftime("%Y-%m-%dT%H:%M"),
                start_utc=source.start_utc,
                elapsed=result.elapsed,
                excluded=result.excluded,
                dark_minutes=round(result.dark_minutes, 2),
                exposure_minutes=round(result.exposure_minutes, 2),
                darkness_category=_darkness_category(
                    summary, source.start_utc + timedelta(minutes=30)
                ),
                state=result.state,
                session_state=result.session_state,
                model_states=result.model_states,
                disagrees=result.disagrees,
                checks=result.checks,
                conditions=result.conditions,
                cloud_total_pct=figures[0],
                cloud_low_pct=figures[1],
                cloud_mid_pct=figures[2],
                cloud_high_pct=figures[3],
                cloud_pct=result.cloud_pct,
                expected={
                    name: ExpectedFieldsResponse(cloud=expected[0], amount=expected[1])
                    for name, expected in result.expected.items()
                },
                precip_probability_pct=source.precip_probability_pct,
                precip_mm=source.precip_mm,
                model_precip_mm={name: value.precip_mm for name, value in source.models.items()},
                gust_kmh=source.gust_kmh,
                wind_kmh=source.wind_kmh,
                temperature_c=source.temperature_c,
                dew_point_c=source.dew_point_c,
                dew_spread_c=result.dew_spread_c,
                visibility_m=row.visibility_m if row is not None else None,
                moon_altitude_deg=source.moon_altitude_deg,
                seeing=score_label(_compute_seeing(row, previous)),
                transparency=score_label(transparency.score),
                transparency_tier=transparency.tier,
            )
        )
    return responses


async def _get_location_and_rules(
    location_id: int,
) -> tuple[dict, ImagingRules, bool]:
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT * FROM location WHERE id = ? AND active = 1",
            (location_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Location not found")
        rules, saved = await load_rules(conn, location_id)
        return dict(row), rules, saved


def _astronomy_nights(
    loc: dict,
    anchor: date,
) -> list[tuple[date, NightSummary]]:
    site_timezone = loc.get("geo_timezone") or loc["timezone"]
    nights: list[tuple[date, NightSummary]] = []
    for offset in range(FORECAST_NIGHTS + 1):
        night_date = anchor + timedelta(days=offset)
        try:
            summary = _night_summary_cached(
                loc["latitude"],
                loc["longitude"],
                loc.get("elevation_m"),
                night_date,
                site_timezone,
            )
        except Exception:
            logger.exception("[weather] astronomy failed date=%s", night_date)
            continue
        nights.append((night_date, summary))
        if len(nights) == FORECAST_NIGHTS:
            break
    return nights


@lru_cache(maxsize=256)
def _night_summary_cached(
    latitude: float,
    longitude: float,
    elevation_m: float | None,
    night_date: date,
    site_timezone: str,
) -> NightSummary:
    """Reuse rule-independent astronomy across forecast evaluations."""
    return compute_night_summary(
        latitude,
        longitude,
        elevation_m,
        night_date,
        site_timezone,
    )


def _validated_controls(
    key: str,
    requested: NightControlsRequest,
    rules: ImagingRules,
    noon_start: datetime,
    noon_end: datetime,
    natural_gear_start: datetime,
    natural_gear_end: datetime,
) -> tuple[NightControlsRequest, NightControls, bool]:
    """Return applicable UTC controls, evaluator controls and whether any were ignored."""

    def utc(value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    ignored = rules.rain_policy == "hours_lost" and (
        requested.gear_out is not None or requested.gear_in is not None
    )
    controls = NightControlsRequest(
        gear_out=(utc(requested.gear_out) if rules.rain_policy == "night_off" else None),
        gear_in=(utc(requested.gear_in) if rules.rain_policy == "night_off" else None),
        imaging_from=utc(requested.imaging_from),
        imaging_until=utc(requested.imaging_until),
    )
    for field, value in controls:
        if value is not None and not noon_start <= value <= noon_end:
            raise HTTPException(
                status_code=422,
                detail=f"{field} for {key} must lie within that noon-to-noon night",
            )

    if rules.rain_policy == "night_off":
        exposure_start = controls.gear_out or natural_gear_start
        exposure_end = controls.gear_in or natural_gear_end
        if exposure_start >= exposure_end:
            raise HTTPException(status_code=422, detail=f"gear_out must precede gear_in for {key}")
        imaging_start = controls.imaging_from or exposure_start
        imaging_end = controls.imaging_until or exposure_end
        if (
            controls.imaging_from is not None
            and not exposure_start <= controls.imaging_from <= exposure_end
        ) or (
            controls.imaging_until is not None
            and not exposure_start <= controls.imaging_until <= exposure_end
        ):
            raise HTTPException(
                status_code=422,
                detail=f"imaging controls for {key} must lie within the exposure interval",
            )
    else:
        imaging_start = controls.imaging_from or noon_start
        imaging_end = controls.imaging_until or noon_end

    if imaging_start >= imaging_end:
        raise HTTPException(
            status_code=422,
            detail=f"imaging_from must precede imaging_until for {key}",
        )

    return (
        controls,
        NightControls(
            gear_out_utc=controls.gear_out,
            gear_in_utc=controls.gear_in,
            imaging_from_utc=controls.imaging_from,
            imaging_until_utc=controls.imaging_until,
        ),
        ignored,
    )


def _run_age_minutes(metadata: dict[str, Any], now: datetime) -> dict[str, int | None]:
    return {
        model: (
            max(0, int((now - metadata[domain].init_utc).total_seconds() // 60))
            if domain in metadata
            else None
        )
        for model, domain in META_DOMAINS.items()
    }


@router.post("/forecast", response_model=ForecastResponse)
async def forecast(request: ForecastRequest) -> ForecastResponse:
    """Evaluate the forecast's noon-to-noon nights against saved or draft rules."""
    try:
        loc, saved_rules, rules_saved = await _get_location_and_rules(request.location_id)
        rules = request.rules or saved_rules
        settings = await get_settings()
        now = _now()
        display_timezone = ZoneInfo(loc["timezone"])
        site_timezone = ZoneInfo(loc.get("geo_timezone") or loc["timezone"])
        local_now = now.astimezone(display_timezone)
        anchor = local_now.date() - timedelta(days=1) if local_now.hour < 12 else local_now.date()
        astronomy_nights = _astronomy_nights(loc, anchor)
        forecast_data = await _load_forecast_data(loc, settings.weather_cache_ttl_hours)
        returned_dates = {night_date.isoformat() for night_date, _ in astronomy_nights}
        ignored = {key for key in request.night_controls if key not in returned_dates}
        weather_by_time = {row.time_utc: row for row in forecast_data.weather.hourly}
        pwv_index = NearestMatchIndex(forecast_data.pwv_by_time)
        aod_index = NearestMatchIndex(forecast_data.aod_by_time)
        forecast_last_requested = _last_requested(forecast_data.fetched_at)
        cloud_anchor = forecast_data.cloud_fetched_at or forecast_data.cloud_attempted_at
        cloud_last_requested = _last_requested(cloud_anchor)
        expected_until = {
            "best_match": last_expected_stamp(
                "best_match", forecast_data.fetched_at, forecast_last_requested
            ),
            **{
                model: last_expected_stamp(model, cloud_anchor, cloud_last_requested)
                for model in CLOUD_SPREAD_MODELS
            },
        }
        metadata = parse_model_meta(forecast_data.meta_raw)
        run_age_minutes = _run_age_minutes(metadata, now)
        coarse_from = coarse_cloud_from(metadata.get("ecmwf_ifs025"), cloud_anchor)
        nights: list[NightResponse] = []

        for night_date, summary in astronomy_nights:
            key = night_date.isoformat()
            noon_start, noon_end = _night_bounds(night_date, site_timezone)
            gear_start = (summary.sunset or noon_start) - timedelta(
                minutes=rules.gear_out_before_sunset_min if summary.sunset is not None else 0
            )
            gear_end = (summary.sunrise or noon_end) + timedelta(
                minutes=rules.gear_out_after_sunrise_min if summary.sunrise is not None else 0
            )
            controls, evaluator_controls, controls_ignored = _validated_controls(
                key,
                request.night_controls.get(key, NightControlsRequest()),
                rules,
                noon_start,
                noon_end,
                gear_start,
                gear_end,
            )
            if controls_ignored:
                ignored.add(key)
            control_times = tuple(
                value
                for value in (
                    controls.gear_out,
                    controls.gear_in,
                    controls.imaging_from,
                    controls.imaging_until,
                )
                if value is not None
            )
            hour_start = _floor_hour(max(noon_start, min((gear_start, *control_times))))
            hour_end = _ceil_hour(min(noon_end, max((gear_end, *control_times))))
            hour_times = []
            cursor = hour_start
            while cursor < hour_end:
                hour_times.append(cursor)
                cursor += timedelta(hours=1)
            moon_values = moon_altitudes_at(
                hour_times,
                loc["latitude"],
                loc["longitude"],
                loc.get("elevation_m"),
            )
            moon_by_time = dict(zip(hour_times, moon_values, strict=True))
            inputs = build_hours(
                forecast_data.weather.hourly,
                forecast_data.cloud_models,
                moon_by_time,
                hour_start,
                hour_end,
                expected=expected_until,
            )
            selected_darkness = dark_intervals_for(summary, rules.darkness)
            result = evaluate_night(
                NightInput(
                    sunset_utc=summary.sunset,
                    sunrise_utc=summary.sunrise,
                    noon_start_utc=noon_start,
                    noon_end_utc=noon_end,
                    dark_intervals=selected_darkness,
                    hours=inputs,
                    now_utc=now,
                    controls=evaluator_controls,
                    cloud_models=selected_cloud_models(rules),
                    preferred_model=rules.cloud_preferred_model,
                    combination=rules.cloud_combination,
                    fallback_model="best_match",
                    stale_minutes={
                        "forecast": forecast_data.forecast_stale_minutes,
                        "cloud_models": forecast_data.cloud_stale_minutes,
                    },
                ),
                rules,
            )
            stale_minutes = next(
                (
                    int(reason.value)
                    for reason in result.reasons
                    if reason.code == "stale" and reason.value is not None
                ),
                None,
            )
            gear_interval = result.exposure or (gear_start, gear_end)
            evaluated_end_utc = controls.imaging_until
            coarse_for_night = (
                coarse_from if any(end > coarse_from for _, end in selected_darkness) else None
            )
            coverage_statuses = dict(result.model_statuses)
            coverage_statuses.update(
                {
                    note.model: note.status
                    for note in result.coverage
                    if note.model not in coverage_statuses
                }
            )
            coverage = []
            for model, status in coverage_statuses.items():
                coverage_end = expected_until.get(model)
                coverage_end_in_night = (
                    coverage_end
                    if coverage_end is not None and noon_start < coverage_end < noon_end
                    else None
                )
                coverage.append(
                    CoverageResponse(
                        model=model,
                        status=status,
                        expected_until=_fmt_time(coverage_end_in_night, display_timezone),
                        expected_until_utc=coverage_end_in_night,
                    )
                )
            clear_pct = (
                result.clear_minutes / result.dark_minutes * 100.0
                if result.dark_minutes > 0
                else None
            )
            nights.append(
                NightResponse(
                    date=key,
                    verdict=result.verdict,
                    reason=_reason_response(result.reasons[0], display_timezone),
                    other_reasons=[
                        _reason_response(reason, display_timezone) for reason in result.reasons[1:]
                    ],
                    advisory=(
                        _reason_response(result.advisory, display_timezone)
                        if result.advisory is not None
                        else None
                    ),
                    clear_hours=round(result.clear_minutes / 60.0, 2),
                    dark_hours=round(result.dark_minutes / 60.0, 2),
                    unknown_hours=round(result.unknown_minutes / 60.0, 2),
                    clear_pct=round(clear_pct, 1) if clear_pct is not None else None,
                    longest_gap_start=(
                        _fmt_time(result.longest_gap[0], display_timezone)
                        if result.longest_gap
                        else None
                    ),
                    longest_gap_end=(
                        _fmt_time(result.longest_gap[1], display_timezone)
                        if result.longest_gap
                        else None
                    ),
                    longest_gap_start_utc=(result.longest_gap[0] if result.longest_gap else None),
                    longest_gap_end_utc=(result.longest_gap[1] if result.longest_gap else None),
                    window_start=(
                        _fmt_time(result.window[0], display_timezone) if result.window else None
                    ),
                    window_end=(
                        _fmt_time(result.window[1], display_timezone) if result.window else None
                    ),
                    window_start_utc=result.window[0] if result.window else None,
                    window_end_utc=result.window[1] if result.window else None,
                    gear_out_start=_fmt_time(gear_interval[0], display_timezone) or "",
                    gear_out_end=_fmt_time(gear_interval[1], display_timezone) or "",
                    gear_out_start_utc=gear_interval[0],
                    gear_out_end_utc=gear_interval[1],
                    evaluated_from=_fmt_time(result.evaluated_from_utc, display_timezone),
                    evaluated_end=_fmt_time(evaluated_end_utc, display_timezone),
                    evaluated_from_utc=result.evaluated_from_utc,
                    evaluated_end_utc=evaluated_end_utc,
                    dark_intervals=[
                        IntervalResponse(
                            start=_fmt_time(start, display_timezone) or "",
                            end=_fmt_time(end, display_timezone) or "",
                            start_utc=start,
                            end_utc=end,
                        )
                        for start, end in selected_darkness
                    ],
                    darkness_intervals={
                        level: [
                            IntervalResponse(
                                start=_fmt_time(start, display_timezone) or "",
                                end=_fmt_time(end, display_timezone) or "",
                                start_utc=start,
                                end_utc=end,
                            )
                            for start, end in summary.dark_intervals[level]
                        ]
                        for level in ("civil", "nautical", "astronomical")
                    },
                    exposure=_interval_response(result.exposure, display_timezone),
                    imaging=_interval_response(result.imaging, display_timezone),
                    controls=controls,
                    model_statuses=result.model_statuses,
                    primary_model=result.primary_model,
                    cloud_combination=result.cloud_combination,
                    differing_hours=result.differing_hours,
                    compared_hours=result.compared_hours,
                    cloud_models=result.cloud_models,
                    cloud_models_used=result.cloud_models_used,
                    default_cloud_used=result.default_cloud_used,
                    coverage=coverage,
                    single_model=_is_single_model(
                        result.cloud_combination,
                        result.cloud_models_used,
                    ),
                    cloud_source=("best_match_fallback" if result.default_cloud_used else "ecmwf"),
                    layer_model=result.primary_model,
                    cloud_coarse_from=_fmt_time(coarse_for_night, display_timezone),
                    cloud_coarse_from_utc=coarse_for_night,
                    stale_minutes=stale_minutes,
                    requirements=result.requirements,
                    extremes=_extremes(inputs, result.hours, rules.rain_policy, display_timezone),
                    sunset=_fmt_time(summary.sunset, display_timezone),
                    sunset_utc=summary.sunset,
                    sunrise=_fmt_time(summary.sunrise, display_timezone),
                    sunrise_utc=summary.sunrise,
                    moon_illumination_pct=summary.moon.illumination_pct,
                    moon_phase_name=summary.moon.phase_name,
                    moonrise=_fmt_time(summary.moon.moonrise_utc, display_timezone),
                    moonrise_utc=summary.moon.moonrise_utc,
                    moonset=_fmt_time(summary.moon.moonset_utc, display_timezone),
                    moonset_utc=summary.moon.moonset_utc,
                    hours=_hour_responses(
                        inputs,
                        result.hours,
                        summary,
                        result.primary_model,
                        weather_by_time,
                        pwv_index,
                        aod_index,
                        display_timezone,
                    ),
                )
            )

        return ForecastResponse(
            location_id=loc["id"],
            location_name=loc["name"],
            timezone=loc["timezone"],
            geo_timezone=loc.get("geo_timezone"),
            rules=rules,
            rules_saved=rules_saved,
            fetched_at=forecast_data.fetched_at.astimezone(UTC).isoformat(),
            evaluated_at=now,
            stale_sources=StaleSourcesResponse(
                forecast=forecast_data.forecast_stale_minutes,
                cloud_models=forecast_data.cloud_stale_minutes,
            ),
            run_age_minutes=run_age_minutes,
            ignored_controls=sorted(ignored),
            nights=nights,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[weather] forecast failed location=%s", request.location_id)
        raise HTTPException(status_code=500, detail="Failed to build weather forecast") from exc


@router.get("/methodology", response_model=MethodologyResponse)
async def get_methodology() -> MethodologyResponse:
    return MethodologyResponse(summary=METHODOLOGY_SUMMARY, details=METHODOLOGY_DETAILS)


@router.get("/cache/stats")
async def weather_cache_stats() -> dict:
    async with get_db() as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM weather_cache")
        rows = (await cursor.fetchone())[0]
        try:
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(pgsize), 0) FROM dbstat WHERE name = 'weather_cache'"
            )
            size = (await cursor.fetchone())[0]
        except Exception:
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(LENGTH(response_json)), 0) FROM weather_cache"
            )
            size = (await cursor.fetchone())[0]
    return {"rows": rows, "bytes": size}


@router.delete("/cache")
async def clear_weather_cache() -> dict:
    async with get_db() as conn:
        cursor = await conn.execute("DELETE FROM weather_cache")
        await conn.commit()
        deleted = cursor.rowcount
    logger.info("[weather-cache] CLEAR deleted=%s", deleted)
    return {"ok": True, "deleted": deleted}
