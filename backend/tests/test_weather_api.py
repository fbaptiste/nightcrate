"""Tests for the weather API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app
from nightcrate.services.weather import HourlyWeather, WeatherData


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _make_fake_weather(n_hours: int = 48) -> WeatherData:
    """Build a fake WeatherData spanning 2 days of hourly data."""
    hours = []
    for i in range(n_hours):
        day = 13 + i // 24
        hour = i % 24
        hours.append(
            HourlyWeather(
                time=f"2026-04-{day:02d}T{hour:02d}:00",
                temperature_c=12.0 + i * 0.1,
                dew_point_c=5.0,
                humidity_pct=60.0,
                cloud_cover_pct=20.0,
                cloud_cover_low_pct=10.0,
                cloud_cover_mid_pct=5.0,
                cloud_cover_high_pct=5.0,
                wind_speed_kmh=8.0,
                wind_direction_deg=180.0,
                wind_gusts_kmh=15.0,
                visibility_m=20000.0,
                precipitation_mm=0.0,
                precipitation_probability_pct=10.0,
                wind_speed_200hpa_kmh=50.0,
                wind_speed_300hpa_kmh=40.0,
                wind_speed_500hpa_kmh=20.0,
                geopotential_200hpa_m=11800.0,
                geopotential_300hpa_m=9200.0,
                geopotential_500hpa_m=5500.0,
            )
        )
    return WeatherData(
        latitude=34.05,
        longitude=-118.25,
        source="forecast",
        hourly=hours,
        raw_json="{}",
    )


def _make_fake_supplementary() -> dict[str, float | None]:
    """Build a fake supplementary data map (used for both PWV and AOD)."""
    result = {}
    for i in range(48):
        day = 13 + i // 24
        hour = i % 24
        result[f"2026-04-{day:02d}T{hour:02d}:00"] = 0.05
    return result


async def _create_test_location(client: AsyncClient) -> int:
    """Create a test location and return its ID."""
    resp = await client.post(
        "/api/locations",
        json={
            "name": "Test Observatory",
            "latitude": 34.05,
            "longitude": -118.25,
            "elevation_m": 300.0,
            "timezone": "America/Los_Angeles",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# GET /api/weather/methodology
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_methodology_returns_text(client):
    resp = await client.get("/api/weather/methodology")
    assert resp.status_code == 200
    data = resp.json()
    assert "text" in data
    assert "Sky Clarity" in data["text"]
    assert "Transparency" in data["text"]
    assert "35%" in data["text"]


# ---------------------------------------------------------------------------
# GET /api/weather/forecast
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_forecast_404_for_missing_location(client):
    resp = await client.get("/api/weather/forecast", params={"location_id": 9999})
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_forecast_returns_days(client):
    loc_id = await _create_test_location(client)
    fake_weather = _make_fake_weather()
    fake_supplementary = _make_fake_supplementary()

    with (
        patch(
            "nightcrate.api.weather._fetch_or_cached",
            new_callable=AsyncMock,
            return_value=fake_weather,
        ),
        patch(
            "nightcrate.api.weather._fetch_or_cached_supplementary",
            new_callable=AsyncMock,
            return_value=fake_supplementary,
        ),
    ):
        resp = await client.get(
            "/api/weather/forecast",
            params={"location_id": loc_id},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["location_id"] == loc_id
    assert data["location_name"] == "Test Observatory"
    assert data["moon_included"] is True  # default from settings
    assert isinstance(data["days"], list)

    if len(data["days"]) > 0:
        day = data["days"][0]
        assert "date" in day
        assert "imaging_quality" in day
        assert "imaging_quality_label" in day
        assert "sky_clarity" in day
        assert "transparency_score" in day
        assert "seeing_score" in day
        assert "wind_calm" in day
        assert "moon_score" in day
        assert "sunset" in day
        assert "sunrise" in day
        assert "darkness_hours" in day
        assert "moonless_dark_hours" in day
        assert "moon_illumination_pct" in day
        assert "moon_phase_name" in day
        assert "dew_safe_window" in day
        assert "no_imaging_window" in day
        assert "deepest_darkness_reached" in day
        assert "avg_cloud_cover_pct" in day
        assert 0 <= day["imaging_quality"] <= 100
        # Verify dryness is gone
        assert "dryness" not in day


@pytest.mark.anyio
async def test_forecast_moon_toggle(client):
    loc_id = await _create_test_location(client)
    fake_weather = _make_fake_weather()
    fake_supplementary = _make_fake_supplementary()

    with (
        patch(
            "nightcrate.api.weather._fetch_or_cached",
            new_callable=AsyncMock,
            return_value=fake_weather,
        ),
        patch(
            "nightcrate.api.weather._fetch_or_cached_supplementary",
            new_callable=AsyncMock,
            return_value=fake_supplementary,
        ),
    ):
        resp = await client.get(
            "/api/weather/forecast",
            params={"location_id": loc_id, "include_moon": False},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["moon_included"] is False


# ---------------------------------------------------------------------------
# GET /api/weather/hourly
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_hourly_404_for_missing_location(client):
    resp = await client.get(
        "/api/weather/hourly",
        params={"location_id": 9999, "date": "2026-04-13"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_hourly_returns_hours(client):
    loc_id = await _create_test_location(client)
    fake_weather = _make_fake_weather()
    fake_supplementary = _make_fake_supplementary()

    with (
        patch(
            "nightcrate.api.weather._fetch_or_cached",
            new_callable=AsyncMock,
            return_value=fake_weather,
        ),
        patch(
            "nightcrate.api.weather._fetch_or_cached_supplementary",
            new_callable=AsyncMock,
            return_value=fake_supplementary,
        ),
    ):
        resp = await client.get(
            "/api/weather/hourly",
            params={"location_id": loc_id, "date": "2026-04-13"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == "2026-04-13"
    assert data["location_id"] == loc_id
    assert "sunset" in data
    assert "sunrise" in data
    assert "moon_polyline" in data
    assert isinstance(data["hours"], list)

    if len(data["hours"]) > 0:
        hour = data["hours"][0]
        assert "time" in hour
        assert "temperature_c" in hour
        assert "sky_clarity" in hour
        assert "transparency_score" in hour
        assert "seeing_score" in hour
        assert "wind_calm" in hour
        assert "dew_risk" in hour
        assert "pwv_mm" in hour
        assert "aod" in hour
        # Verify dryness is gone
        assert "dryness" not in hour
