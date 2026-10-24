"""Open-Meteo weather client service.

Fetches hourly weather data from Open-Meteo's forecast and archive APIs,
precipitable water vapor from the ECMWF model, and aerosol optical depth
from the Air Quality API.

Forecast API: https://api.open-meteo.com/v1/forecast
ECMWF API:    https://api.open-meteo.com/v1/ecmwf
Archive API:  https://archive-api.open-meteo.com/v1/archive
Air Quality:  https://air-quality-api.open-meteo.com/v1/air-quality
"""

import asyncio
import bisect
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from nightcrate.services.http_client import get as http_get

logger = logging.getLogger(__name__)

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ECMWF_URL = "https://api.open-meteo.com/v1/ecmwf"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


_COMMON_HOURLY = [
    "temperature_2m",
    "dew_point_2m",
    "relative_humidity_2m",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "visibility",
    "precipitation",
    "precipitation_probability",
]

# Cloud-forecast models requested alongside the main forecast.
#
# ECMWF is the default preferred cloud forecast (see `imaging_rules._preset`).
# Over 126 night hours at one test location, day-ahead
# mean absolute error against ERA5 reanalysis was ECMWF 18.2 pts, ICON 23.0,
# GFS 32.4, and GFS called a clear night cloudy 25 times against ECMWF's 8.
# `best_match` resolves to GFS at that location, which is why a genuinely
# 43%-cloud night was being reported as 100%. ERA5 is itself an IFS product,
# the sample was one site over two weeks, and the scored cloud field was not
# recorded, so this is a pragmatic choice rather than a proven ranking.
# See docs/archive/imaging-quality-model.md §7.
#
# **Only cloud moves to ECMWF.** Everything else still comes from `best_match`,
# because that is all the measurement covered — and because ECMWF IFS 0.25
# serves no `visibility` at all, which the transparency score needs.
# Nights in the forecast. ECMWF IFS 0.25 cloud reaches about 14.5 days ahead
# (measured 2026-10-17), so 14 nights generally stay on the primary cloud model;
# at the edge, declared coverage and the labelled fallback decide. Nights 8–14
# are shown as an outlook. The request contract keeps two days
# beyond the night count so coverage is derived consistently from its parameters.
FORECAST_NIGHTS = 14
FORECAST_DAYS = FORECAST_NIGHTS + 2
CLOUD_SPREAD_MODELS = ("ecmwf_ifs025", "gfs_seamless", "icon_seamless")
CLOUD_REQUEST_MODELS = CLOUD_SPREAD_MODELS
META_DOMAINS = {
    "ecmwf_ifs025": "ecmwf_ifs025",
    "gfs_seamless": "ncep_gfs013",
    "icon_seamless": "dwd_icon",
}

_CLOUD_HOURLY = [
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "precipitation",
]

_PRESSURE_LEVEL_HOURLY = [
    "wind_speed_200hPa",
    "wind_speed_300hPa",
    "wind_speed_500hPa",
    "geopotential_height_200hPa",
    "geopotential_height_300hPa",
    "geopotential_height_500hPa",
]


@dataclass(frozen=True)
class HourlyWeather:
    """Weather data for a single hour."""

    time_utc: datetime
    temperature_c: float | None
    dew_point_c: float | None
    humidity_pct: float | None
    cloud_cover_pct: float | None
    cloud_cover_low_pct: float | None
    cloud_cover_mid_pct: float | None
    cloud_cover_high_pct: float | None
    wind_speed_kmh: float | None
    wind_direction_deg: float | None
    wind_gusts_kmh: float | None
    visibility_m: float | None
    precipitation_mm: float | None
    precipitation_probability_pct: float | None
    # Pressure-level fields — forecast only, None for archive
    wind_speed_200hpa_kmh: float | None = None
    wind_speed_300hpa_kmh: float | None = None
    wind_speed_500hpa_kmh: float | None = None
    geopotential_200hpa_m: float | None = None
    geopotential_300hpa_m: float | None = None
    geopotential_500hpa_m: float | None = None


@dataclass(frozen=True)
class WeatherData:
    """Complete weather response for a location."""

    latitude: float
    longitude: float
    source: Literal["forecast", "archive"]
    hourly: list[HourlyWeather]
    raw_json: str


@dataclass(frozen=True)
class SupplementaryData:
    """Supplementary time-series data from a separate API (PWV or AOD).

    Stores a UTC time→value map.
    """

    latitude: float
    longitude: float
    values_by_time: dict[datetime, float | None]
    raw_json: str


def _parse_time(value: int | float | str, utc_offset_seconds: int) -> datetime:
    """Decode an Open-Meteo timestamp to aware UTC.

    New responses use Unix seconds. Legacy cached responses contain local ISO
    labels paired with one fixed response offset; Open-Meteo explicitly does
    not apply DST transitions within such a response.
    """
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC)
    local_naive = datetime.fromisoformat(value)
    if local_naive.tzinfo is not None:
        return local_naive.astimezone(UTC)
    return (local_naive - timedelta(seconds=utc_offset_seconds)).replace(tzinfo=UTC)


def parse_hourly(
    hourly_dict: dict,
    source: Literal["forecast", "archive"],
    utc_offset_seconds: int = 0,
) -> list[HourlyWeather]:
    """Parse the Open-Meteo hourly block into a list of HourlyWeather records.

    This function is intentionally public (not underscore-prefixed) because
    the weather API router uses it for cache deserialization.
    """
    times = hourly_dict["time"]
    n = len(times)

    def _get(key: str, idx: int) -> float | None:
        values = hourly_dict.get(key)
        if values is None:
            return None
        if idx >= len(values):
            return None
        v = values[idx]
        return float(v) if v is not None else None

    result = []
    for i in range(n):
        if source == "forecast":
            wind_200 = _get("wind_speed_200hPa", i)
            wind_300 = _get("wind_speed_300hPa", i)
            wind_500 = _get("wind_speed_500hPa", i)
            geo_200 = _get("geopotential_height_200hPa", i)
            geo_300 = _get("geopotential_height_300hPa", i)
            geo_500 = _get("geopotential_height_500hPa", i)
        else:
            wind_200 = None
            wind_300 = None
            wind_500 = None
            geo_200 = None
            geo_300 = None
            geo_500 = None

        result.append(
            HourlyWeather(
                time_utc=_parse_time(times[i], utc_offset_seconds),
                temperature_c=_get("temperature_2m", i),
                dew_point_c=_get("dew_point_2m", i),
                humidity_pct=_get("relative_humidity_2m", i),
                cloud_cover_pct=_get("cloud_cover", i),
                cloud_cover_low_pct=_get("cloud_cover_low", i),
                cloud_cover_mid_pct=_get("cloud_cover_mid", i),
                cloud_cover_high_pct=_get("cloud_cover_high", i),
                wind_speed_kmh=_get("wind_speed_10m", i),
                wind_direction_deg=_get("wind_direction_10m", i),
                wind_gusts_kmh=_get("wind_gusts_10m", i),
                visibility_m=_get("visibility", i),
                precipitation_mm=_get("precipitation", i),
                precipitation_probability_pct=_get("precipitation_probability", i),
                wind_speed_200hpa_kmh=wind_200,
                wind_speed_300hpa_kmh=wind_300,
                wind_speed_500hpa_kmh=wind_500,
                geopotential_200hpa_m=geo_200,
                geopotential_300hpa_m=geo_300,
                geopotential_500hpa_m=geo_500,
            )
        )

    return result


def _parse_supplementary(data: dict, variable: str) -> dict[datetime, float | None]:
    """Parse a single-variable hourly response into a time→value map."""
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    values = hourly.get(variable, [])

    offset = int(data.get("utc_offset_seconds", 0))
    result: dict[datetime, float | None] = {}
    for i, t in enumerate(times):
        val = values[i] if i < len(values) else None
        result[_parse_time(t, offset)] = float(val) if val is not None else None
    return result


class NearestMatchIndex:
    """Prebuilt index for repeated nearest-match lookups against the same data.

    Building this once outside a loop is O(n log n); each lookup is O(log n).
    Previously `nearest_match` did the sort + `datetime.fromisoformat` work
    on every call, which added up to tens of thousands of parses per forecast.
    """

    __slots__ = ("_data", "_sorted_dts", "_sorted_vals")

    def __init__(self, data: dict[datetime, float | None]):
        self._data = data
        pairs = sorted(data.items(), key=lambda p: p[0])
        self._sorted_dts = [p[0] for p in pairs]
        self._sorted_vals = [p[1] for p in pairs]

    def lookup(self, target_utc: datetime, max_gap_hours: float = 3.0) -> float | None:
        if not self._sorted_dts:
            return None
        # Exact-hit fast path — avoids the datetime parse on aligned hourlies.
        if target_utc in self._data:
            return self._data[target_utc]

        idx = bisect.bisect_left(self._sorted_dts, target_utc)
        best_val: float | None = None
        best_gap = float("inf")
        for i in (idx - 1, idx):
            if 0 <= i < len(self._sorted_dts):
                gap = abs((self._sorted_dts[i] - target_utc).total_seconds()) / 3600
                if gap < best_gap and gap <= max_gap_hours:
                    best_gap = gap
                    best_val = self._sorted_vals[i]
        return best_val


def nearest_match(
    data: dict[datetime, float | None],
    target_utc: datetime,
    max_gap_hours: float = 3.0,
) -> float | None:
    """Find the value for the closest timestamp within max_gap_hours.

    Convenience wrapper over `NearestMatchIndex` for one-off lookups. In a
    tight loop, build the index once and call `.lookup()` directly.
    """
    if not data:
        return None
    return NearestMatchIndex(data).lookup(target_utc, max_gap_hours)


@dataclass(frozen=True)
class ModelSeries:
    """One provider model, with every requested field parsed independently."""

    cloud_total_pct: dict[datetime, float | None]
    cloud_low_pct: dict[datetime, float | None]
    cloud_mid_pct: dict[datetime, float | None]
    cloud_high_pct: dict[datetime, float | None]
    precipitation_mm: dict[datetime, float | None]
    fields_present: frozenset[str]


@dataclass(frozen=True)
class CloudModelData:
    """Per-model forecast series for one location."""

    models: dict[str, ModelSeries]
    raw_json: str


def parse_cloud_models(
    hourly: dict,
    models: tuple[str, ...],
    utc_offset_seconds: int = 0,
) -> dict[str, ModelSeries]:
    """Split a multi-model Open-Meteo response into per-model series.

    With more than one ``models=`` value every variable comes back suffixed
    (``cloud_cover_ecmwf_ifs025``); with exactly one it does not. Only the
    multi-model shape is parsed here.
    """
    if any(variable in hourly for variable in _CLOUD_HOURLY):
        raise ValueError("multi-model response contains unsuffixed forecast fields")

    times = hourly.get("time", [])
    parsed_times = [_parse_time(value, utc_offset_seconds) for value in times]
    out: dict[str, ModelSeries] = {}
    for model in models:
        keys = {variable: f"{variable}_{model}" for variable in _CLOUD_HOURLY}
        present = frozenset(variable for variable, key in keys.items() if key in hourly)
        if not present:
            continue

        def field(variable: str) -> dict[datetime, float | None]:
            if variable not in present:
                return {}
            values = hourly[keys[variable]]
            return {
                stamp: (
                    float(values[index])
                    if index < len(values) and values[index] is not None
                    else None
                )
                for index, stamp in enumerate(parsed_times)
            }

        out[model] = ModelSeries(
            cloud_total_pct=field("cloud_cover"),
            cloud_low_pct=field("cloud_cover_low"),
            cloud_mid_pct=field("cloud_cover_mid"),
            cloud_high_pct=field("cloud_cover_high"),
            precipitation_mm=field("precipitation"),
            fields_present=present,
        )
    return out


async def fetch_cloud_models(
    latitude: float,
    longitude: float,
    timezone_str: str,
) -> CloudModelData:
    """Fetch cloud cover from several forecast models in one request.

    Supplies the selectable cloud series used to compare and combine forecasts.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "GMT",
        "timeformat": "unixtime",
        "hourly": ",".join(_CLOUD_HOURLY),
        "forecast_days": FORECAST_DAYS,
        "past_days": 1,
        "models": ",".join(CLOUD_REQUEST_MODELS),
    }
    response = await http_get(_FORECAST_URL, params=params, label="weather[cloud_models]")
    response.raise_for_status()
    data = response.json()
    return CloudModelData(
        models=parse_cloud_models(
            data.get("hourly", {}),
            CLOUD_REQUEST_MODELS,
            int(data.get("utc_offset_seconds", 0)),
        ),
        raw_json=json.dumps(data),
    )


async def fetch_model_meta() -> str:
    """Fetch raw model metadata used for run ages and cloud resolution."""

    async def fetch_domain(domain: str) -> dict:
        url = f"https://api.open-meteo.com/data/{domain}/static/meta.json"
        response = await http_get(url, label=f"weather[model_meta:{domain}]")
        response.raise_for_status()
        return response.json()

    domain_names = tuple(META_DOMAINS.values())
    bodies = await asyncio.gather(*(fetch_domain(domain) for domain in domain_names))
    return json.dumps(dict(zip(domain_names, bodies, strict=True)))


async def fetch_weather(
    latitude: float,
    longitude: float,
    timezone_str: str,
    source: Literal["forecast", "archive"] = "forecast",
    start_date: str | None = None,
    end_date: str | None = None,
) -> WeatherData:
    """Fetch hourly weather data from Open-Meteo.

    Args:
        latitude: Location latitude in decimal degrees.
        longitude: Location longitude in decimal degrees.
        timezone_str: IANA timezone string (e.g. "America/Los_Angeles").
        source: "forecast" uses the forecast API; "archive" uses the archive API.
        start_date: ISO date string (YYYY-MM-DD). Required for archive source.
        end_date: ISO date string (YYYY-MM-DD). Required for archive source.

    Returns:
        WeatherData with parsed hourly records and the raw JSON for caching.

    Raises:
        ValueError: If archive source is used without start_date/end_date.
        httpx.HTTPStatusError: On non-2xx HTTP response.
    """
    if source == "archive" and (start_date is None or end_date is None):
        raise ValueError("start_date and end_date are required for archive source")

    url = _FORECAST_URL if source == "forecast" else _ARCHIVE_URL

    hourly_vars = list(_COMMON_HOURLY)
    if source == "forecast":
        hourly_vars.extend(_PRESSURE_LEVEL_HOURLY)

    params: dict = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "GMT",
        "timeformat": "unixtime",
        "hourly": ",".join(hourly_vars),
        "wind_speed_unit": "kmh",
    }

    if source == "forecast":
        # One day past the last night so its sunrise window has data.
        params["forecast_days"] = FORECAST_DAYS
        params["past_days"] = 1
    else:
        params["start_date"] = start_date
        params["end_date"] = end_date

    response = await http_get(url, params=params, label=f"weather[{source}]")
    response.raise_for_status()
    data = response.json()

    hourly = parse_hourly(data["hourly"], source, int(data.get("utc_offset_seconds", 0)))

    return WeatherData(
        latitude=data["latitude"],
        longitude=data["longitude"],
        source=source,
        hourly=hourly,
        raw_json=json.dumps(data),
    )


async def fetch_pwv(
    latitude: float,
    longitude: float,
    timezone_str: str,
) -> SupplementaryData:
    """Fetch precipitable water vapor from the ECMWF model.

    The standard Open-Meteo forecast API does not include
    total_column_integrated_water_vapour. The ECMWF IFS 0.25° model does.
    """
    params: dict = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "GMT",
        "timeformat": "unixtime",
        "hourly": "total_column_integrated_water_vapour",
        "forecast_days": FORECAST_DAYS,
    }

    response = await http_get(_ECMWF_URL, params=params, label="ecmwf_pwv")
    response.raise_for_status()
    data = response.json()

    values = _parse_supplementary(data, "total_column_integrated_water_vapour")

    return SupplementaryData(
        latitude=data.get("latitude", latitude),
        longitude=data.get("longitude", longitude),
        values_by_time=values,
        raw_json=json.dumps(data),
    )


async def fetch_air_quality(
    latitude: float,
    longitude: float,
    timezone_str: str,
) -> SupplementaryData:
    """Fetch aerosol optical depth from Open-Meteo Air Quality API.

    Returns up to 7 days of hourly AOD data. The air-quality endpoint
    is separate from the forecast endpoint (different domain, different model).

    Global domain: 45 km spatial, 3-hourly temporal, updated every 12 hours.
    AOD values will effectively step across 3-hour blocks.
    """
    params: dict = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "GMT",
        "timeformat": "unixtime",
        "hourly": "aerosol_optical_depth",
        "forecast_days": 7,
    }

    response = await http_get(_AIR_QUALITY_URL, params=params, label="air_quality_aod")
    response.raise_for_status()
    data = response.json()

    values = _parse_supplementary(data, "aerosol_optical_depth")

    return SupplementaryData(
        latitude=data.get("latitude", latitude),
        longitude=data.get("longitude", longitude),
        values_by_time=values,
        raw_json=json.dumps(data),
    )
