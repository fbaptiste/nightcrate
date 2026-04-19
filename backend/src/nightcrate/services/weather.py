"""Open-Meteo weather client service.

Fetches hourly weather data from Open-Meteo's forecast and archive APIs,
precipitable water vapor from the ECMWF model, and aerosol optical depth
from the Air Quality API.

Forecast API: https://api.open-meteo.com/v1/forecast
ECMWF API:    https://api.open-meteo.com/v1/ecmwf
Archive API:  https://archive-api.open-meteo.com/v1/archive
Air Quality:  https://air-quality-api.open-meteo.com/v1/air-quality
"""

import bisect
import json
import logging
from dataclasses import dataclass
from datetime import datetime
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

    time: str
    temperature_c: float
    dew_point_c: float
    humidity_pct: float
    cloud_cover_pct: float
    cloud_cover_low_pct: float
    cloud_cover_mid_pct: float
    cloud_cover_high_pct: float
    wind_speed_kmh: float
    wind_direction_deg: float
    wind_gusts_kmh: float
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

    Stores a time→value map. Timestamps are ISO local time strings
    matching the weather data format.
    """

    latitude: float
    longitude: float
    values_by_time: dict[str, float | None]
    raw_json: str


def parse_hourly(hourly_dict: dict, source: Literal["forecast", "archive"]) -> list[HourlyWeather]:
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
                time=times[i],
                temperature_c=float(hourly_dict["temperature_2m"][i]),
                dew_point_c=float(hourly_dict["dew_point_2m"][i]),
                humidity_pct=float(hourly_dict["relative_humidity_2m"][i]),
                cloud_cover_pct=float(hourly_dict["cloud_cover"][i]),
                cloud_cover_low_pct=float(hourly_dict["cloud_cover_low"][i]),
                cloud_cover_mid_pct=float(hourly_dict["cloud_cover_mid"][i]),
                cloud_cover_high_pct=float(hourly_dict["cloud_cover_high"][i]),
                wind_speed_kmh=float(hourly_dict["wind_speed_10m"][i]),
                wind_direction_deg=float(hourly_dict["wind_direction_10m"][i]),
                wind_gusts_kmh=float(hourly_dict["wind_gusts_10m"][i]),
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


def _parse_supplementary(data: dict, variable: str) -> dict[str, float | None]:
    """Parse a single-variable hourly response into a time→value map."""
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    values = hourly.get(variable, [])

    result = {}
    for i, t in enumerate(times):
        val = values[i] if i < len(values) else None
        result[t] = float(val) if val is not None else None
    return result


class NearestMatchIndex:
    """Prebuilt index for repeated nearest-match lookups against the same data.

    Building this once outside a loop is O(n log n); each lookup is O(log n).
    Previously `nearest_match` did the sort + `datetime.fromisoformat` work
    on every call, which added up to tens of thousands of parses per forecast.
    """

    __slots__ = ("_data", "_sorted_dts", "_sorted_vals")

    def __init__(self, data: dict[str, float | None]):
        self._data = data
        pairs = sorted(
            ((datetime.fromisoformat(ts), v) for ts, v in data.items()),
            key=lambda p: p[0],
        )
        self._sorted_dts = [p[0] for p in pairs]
        self._sorted_vals = [p[1] for p in pairs]

    def lookup(self, target_time: str, max_gap_hours: float = 3.0) -> float | None:
        if not self._sorted_dts:
            return None
        # Exact-hit fast path — avoids the datetime parse on aligned hourlies.
        if target_time in self._data:
            return self._data[target_time]

        target_dt = datetime.fromisoformat(target_time)
        idx = bisect.bisect_left(self._sorted_dts, target_dt)
        best_val: float | None = None
        best_gap = float("inf")
        for i in (idx - 1, idx):
            if 0 <= i < len(self._sorted_dts):
                gap = abs((self._sorted_dts[i] - target_dt).total_seconds()) / 3600
                if gap < best_gap and gap <= max_gap_hours:
                    best_gap = gap
                    best_val = self._sorted_vals[i]
        return best_val


def nearest_match(
    data: dict[str, float | None],
    target_time: str,
    max_gap_hours: float = 3.0,
) -> float | None:
    """Find the value for the closest timestamp within max_gap_hours.

    Convenience wrapper over `NearestMatchIndex` for one-off lookups. In a
    tight loop, build the index once and call `.lookup()` directly.
    """
    if not data:
        return None
    return NearestMatchIndex(data).lookup(target_time, max_gap_hours)


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
        "timezone": timezone_str,
        "hourly": ",".join(hourly_vars),
        "wind_speed_unit": "kmh",
    }

    if source == "forecast":
        # Request 8 days so the last night's sunrise window (which extends
        # into the morning of day 8) has weather data coverage.
        params["forecast_days"] = 8
    else:
        params["start_date"] = start_date
        params["end_date"] = end_date

    response = await http_get(url, params=params, label=f"weather[{source}]")
    response.raise_for_status()
    data = response.json()

    hourly = parse_hourly(data["hourly"], source)

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
        "timezone": timezone_str,
        "hourly": "total_column_integrated_water_vapour",
        "forecast_days": 8,
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
        "timezone": timezone_str,
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
