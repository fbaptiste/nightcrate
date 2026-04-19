"""Tests for Open-Meteo weather client service.

Uses mocked HTTP responses — no real API calls in tests.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nightcrate.services.weather import (
    HourlyWeather,
    SupplementaryData,
    WeatherData,
    fetch_air_quality,
    fetch_pwv,
    fetch_weather,
    nearest_match,
    parse_hourly,
)

# Minimal Open-Meteo response structure (shared between forecast and archive)
MOCK_RESPONSE_JSON = {
    "latitude": 33.26,
    "longitude": -116.38,
    "utc_offset_seconds": -25200,
    "timezone": "America/Los_Angeles",
    "hourly_units": {"time": "iso8601", "temperature_2m": "°C"},
    "hourly": {
        "time": [
            "2026-03-15T00:00",
            "2026-03-15T01:00",
            "2026-03-15T02:00",
        ],
        "temperature_2m": [8.5, 7.2, 6.1],
        "dew_point_2m": [2.1, 1.8, 1.5],
        "relative_humidity_2m": [55, 58, 62],
        "cloud_cover": [10, 20, 15],
        "cloud_cover_low": [5, 10, 5],
        "cloud_cover_mid": [3, 5, 8],
        "cloud_cover_high": [2, 5, 2],
        "wind_speed_10m": [8.0, 6.5, 5.0],
        "wind_direction_10m": [180, 190, 200],
        "wind_gusts_10m": [15.0, 12.0, 10.0],
        "visibility": [20000, 18000, 22000],
        "precipitation": [0.0, 0.1, 0.0],
        "precipitation_probability": [10, 30, 5],
    },
}

MOCK_FORECAST_EXTRA = {
    "hourly": {
        **MOCK_RESPONSE_JSON["hourly"],
        "wind_speed_200hPa": [40.0, 35.0, 30.0],
        "wind_speed_300hPa": [30.0, 25.0, 22.0],
        "wind_speed_500hPa": [15.0, 12.0, 10.0],
        "geopotential_height_200hPa": [11800, 11800, 11800],
        "geopotential_height_300hPa": [9200, 9200, 9200],
        "geopotential_height_500hPa": [5500, 5500, 5500],
    },
}

MOCK_AQ_RESPONSE = {
    "latitude": 33.26,
    "longitude": -116.38,
    "hourly": {
        "time": [
            "2026-03-15T00:00",
            "2026-03-15T03:00",
            "2026-03-15T06:00",
        ],
        "aerosol_optical_depth": [0.05, 0.06, 0.04],
    },
}

MOCK_PWV_RESPONSE = {
    "latitude": 33.26,
    "longitude": -116.38,
    "hourly": {
        "time": [
            "2026-03-15T00:00",
            "2026-03-15T01:00",
            "2026-03-15T02:00",
        ],
        "total_column_integrated_water_vapour": [8.5, 9.0, 7.5],
    },
}


def _make_mock_response(json_data: dict) -> MagicMock:
    """Return a synchronous mock that matches httpx.Response's interface."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


class TestFetchWeather:
    @patch("nightcrate.services.http_client.httpx.AsyncClient")
    async def test_forecast_returns_weather_data(self, mock_client_cls):
        response_data = {**MOCK_RESPONSE_JSON, "hourly": MOCK_FORECAST_EXTRA["hourly"]}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_make_mock_response(response_data))
        mock_client_cls.return_value = mock_client

        result = await fetch_weather(
            latitude=33.26,
            longitude=-116.38,
            timezone_str="America/Los_Angeles",
            source="forecast",
        )

        assert isinstance(result, WeatherData)
        assert len(result.hourly) == 3
        assert result.source == "forecast"

    @patch("nightcrate.services.http_client.httpx.AsyncClient")
    async def test_archive_returns_weather_data(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_make_mock_response(MOCK_RESPONSE_JSON))
        mock_client_cls.return_value = mock_client

        result = await fetch_weather(
            latitude=33.26,
            longitude=-116.38,
            timezone_str="America/Los_Angeles",
            source="archive",
            start_date="2025-01-15",
            end_date="2025-01-15",
        )

        assert isinstance(result, WeatherData)
        assert result.source == "archive"

    @patch("nightcrate.services.http_client.httpx.AsyncClient")
    async def test_hourly_fields_parsed(self, mock_client_cls):
        response_data = {**MOCK_RESPONSE_JSON, "hourly": MOCK_FORECAST_EXTRA["hourly"]}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_make_mock_response(response_data))
        mock_client_cls.return_value = mock_client

        result = await fetch_weather(
            latitude=33.26,
            longitude=-116.38,
            timezone_str="America/Los_Angeles",
            source="forecast",
        )

        h = result.hourly[0]
        assert isinstance(h, HourlyWeather)
        assert h.temperature_c == 8.5
        assert h.dew_point_c == 2.1
        assert h.humidity_pct == 55
        assert h.cloud_cover_pct == 10
        assert h.cloud_cover_low_pct == 5
        assert h.cloud_cover_mid_pct == 3
        assert h.cloud_cover_high_pct == 2
        assert h.wind_speed_kmh == 8.0
        assert h.wind_direction_deg == 180
        assert h.wind_gusts_kmh == 15.0
        assert h.visibility_m == 20000

    @patch("nightcrate.services.http_client.httpx.AsyncClient")
    async def test_forecast_has_pressure_level_data(self, mock_client_cls):
        response_data = {**MOCK_RESPONSE_JSON, "hourly": MOCK_FORECAST_EXTRA["hourly"]}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_make_mock_response(response_data))
        mock_client_cls.return_value = mock_client

        result = await fetch_weather(
            latitude=33.26,
            longitude=-116.38,
            timezone_str="America/Los_Angeles",
            source="forecast",
        )

        h = result.hourly[0]
        assert h.wind_speed_200hpa_kmh == 40.0
        assert h.wind_speed_300hpa_kmh == 30.0
        assert h.wind_speed_500hpa_kmh == 15.0
        assert h.geopotential_200hpa_m == 11800
        assert h.geopotential_300hpa_m == 9200
        assert h.geopotential_500hpa_m == 5500

    @patch("nightcrate.services.http_client.httpx.AsyncClient")
    async def test_archive_no_pressure_level_data(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_make_mock_response(MOCK_RESPONSE_JSON))
        mock_client_cls.return_value = mock_client

        result = await fetch_weather(
            latitude=33.26,
            longitude=-116.38,
            timezone_str="America/Los_Angeles",
            source="archive",
            start_date="2025-01-15",
            end_date="2025-01-15",
        )

        h = result.hourly[0]
        assert h.wind_speed_200hpa_kmh is None
        assert h.wind_speed_300hpa_kmh is None
        assert h.wind_speed_500hpa_kmh is None


class TestFetchAirQuality:
    @patch("nightcrate.services.http_client.httpx.AsyncClient")
    async def test_air_quality_returns_data(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_make_mock_response(MOCK_AQ_RESPONSE))
        mock_client_cls.return_value = mock_client

        result = await fetch_air_quality(
            latitude=33.26,
            longitude=-116.38,
            timezone_str="America/Los_Angeles",
        )

        assert isinstance(result, SupplementaryData)
        assert len(result.values_by_time) == 3
        assert result.values_by_time["2026-03-15T00:00"] == 0.05
        assert result.values_by_time["2026-03-15T03:00"] == 0.06


class TestFetchPwv:
    @patch("nightcrate.services.http_client.httpx.AsyncClient")
    async def test_pwv_returns_data(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_make_mock_response(MOCK_PWV_RESPONSE))
        mock_client_cls.return_value = mock_client

        result = await fetch_pwv(
            latitude=33.26,
            longitude=-116.38,
            timezone_str="America/Los_Angeles",
        )

        assert isinstance(result, SupplementaryData)
        assert len(result.values_by_time) == 3
        assert result.values_by_time["2026-03-15T00:00"] == 8.5
        assert result.values_by_time["2026-03-15T01:00"] == 9.0


class TestNearestMatch:
    def test_exact_match(self):
        data = {"2026-03-15T00:00": 0.05, "2026-03-15T03:00": 0.06}
        assert nearest_match(data, "2026-03-15T00:00") == 0.05

    def test_nearest_within_gap(self):
        """3-hourly AOD data should match nearby hourly timestamps."""
        data = {"2026-03-15T00:00": 0.05, "2026-03-15T03:00": 0.06}
        # 01:00 is 1h from 00:00 — should match 00:00
        assert nearest_match(data, "2026-03-15T01:00") == 0.05
        # 02:00 is 2h from 03:00 and 2h from 00:00 — pick 00:00 (first encountered)
        result = nearest_match(data, "2026-03-15T02:00")
        assert result in (0.05, 0.06)  # either is acceptable

    def test_beyond_max_gap(self):
        data = {"2026-03-15T00:00": 0.05}
        # 04:00 is 4h away, beyond default max_gap_hours=3
        assert nearest_match(data, "2026-03-15T04:00") is None

    def test_empty_data(self):
        assert nearest_match({}, "2026-03-15T00:00") is None

    def test_custom_max_gap_rejects_distant_match(self):
        """A match 2 hours away should fail with max_gap_hours=1."""
        data = {"2026-03-15T00:00": 0.05}
        # 2h away, max_gap=1 — should return None
        assert nearest_match(data, "2026-03-15T02:00", max_gap_hours=1.0) is None

    def test_custom_max_gap_accepts_with_default(self):
        """The same 2-hour gap succeeds with default max_gap_hours=3."""
        data = {"2026-03-15T00:00": 0.05}
        # 2h away, max_gap=3 (default) — should match
        assert nearest_match(data, "2026-03-15T02:00", max_gap_hours=3.0) == 0.05

    def test_none_value_in_data(self):
        """nearest_match should return None when the matched entry has a None value."""
        data = {"2026-03-15T00:00": None}
        assert nearest_match(data, "2026-03-15T00:00") is None


class TestFetchWeatherErrors:
    @patch("nightcrate.services.http_client.httpx.AsyncClient")
    async def test_http_500_raises_status_error(self, mock_client_cls):
        """A 500 response from Open-Meteo should raise httpx.HTTPStatusError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("GET", "https://api.open-meteo.com/v1/forecast"),
            response=mock_response,
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_weather(
                latitude=33.26,
                longitude=-116.38,
                timezone_str="America/Los_Angeles",
                source="forecast",
            )

    async def test_archive_without_dates_raises_value_error(self):
        """fetch_weather with source='archive' but no dates should raise ValueError."""
        with pytest.raises(ValueError, match="start_date and end_date are required"):
            await fetch_weather(
                latitude=33.26,
                longitude=-116.38,
                timezone_str="America/Los_Angeles",
                source="archive",
            )

    async def test_archive_missing_end_date_raises_value_error(self):
        """fetch_weather with source='archive' and only start_date should raise ValueError."""
        with pytest.raises(ValueError, match="start_date and end_date are required"):
            await fetch_weather(
                latitude=33.26,
                longitude=-116.38,
                timezone_str="America/Los_Angeles",
                source="archive",
                start_date="2025-01-15",
            )


class TestParseHourly:
    def test_empty_hourly_arrays(self):
        """Empty time/data arrays should produce an empty list."""
        hourly_dict = {
            "time": [],
            "temperature_2m": [],
            "dew_point_2m": [],
            "relative_humidity_2m": [],
            "cloud_cover": [],
            "cloud_cover_low": [],
            "cloud_cover_mid": [],
            "cloud_cover_high": [],
            "wind_speed_10m": [],
            "wind_direction_10m": [],
            "wind_gusts_10m": [],
            "visibility": [],
            "precipitation": [],
            "precipitation_probability": [],
        }
        result = parse_hourly(hourly_dict, "forecast")
        assert result == []

    def test_missing_optional_fields_handled(self):
        """Missing visibility/precipitation/probability fields produce None values."""
        hourly_dict = {
            "time": ["2026-03-15T00:00"],
            "temperature_2m": [8.5],
            "dew_point_2m": [2.1],
            "relative_humidity_2m": [55],
            "cloud_cover": [10],
            "cloud_cover_low": [5],
            "cloud_cover_mid": [3],
            "cloud_cover_high": [2],
            "wind_speed_10m": [8.0],
            "wind_direction_10m": [180],
            "wind_gusts_10m": [15.0],
            # No visibility, precipitation, precipitation_probability keys
        }
        result = parse_hourly(hourly_dict, "archive")
        assert len(result) == 1
        h = result[0]
        assert h.visibility_m is None
        assert h.precipitation_mm is None
        assert h.precipitation_probability_pct is None


class TestGetAndLogException:
    """Exception path in the shared `_get_and_log` wrapper — exercised via
    `fetch_weather` since the helper is internal. Verifies the error is
    logged and then re-raised so callers still see the original exception."""

    @patch("nightcrate.services.http_client.httpx.AsyncClient")
    async def test_network_error_propagates(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("network down"))
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.ConnectError, match="network down"):
            await fetch_weather(
                latitude=33.26,
                longitude=-116.38,
                timezone_str="America/Los_Angeles",
                source="forecast",
            )

    @patch("nightcrate.services.http_client.httpx.AsyncClient")
    async def test_timeout_propagates(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.ReadTimeout):
            await fetch_weather(
                latitude=33.26,
                longitude=-116.38,
                timezone_str="America/Los_Angeles",
                source="forecast",
            )
