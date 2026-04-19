"""Tests for weather cache stats, clear, and polar no-imaging branch.

Focuses on coverage gaps introduced by the latest additions to
`nightcrate.api.weather`:

- `GET /api/weather/cache/stats` — row count + byte size (with dbstat fallback).
- `DELETE /api/weather/cache` — clears the cache.
- `_compute_night_data` polar branch — `no_imaging_window == True`.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db_path
from nightcrate.main import app
from nightcrate.services.weather import HourlyWeather, WeatherData


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _create_location(
    client: AsyncClient,
    *,
    name: str = "Cache Test Observatory",
    latitude: float = 34.05,
    longitude: float = -118.25,
    elevation_m: float = 300.0,
    timezone: str = "America/Los_Angeles",
) -> int:
    resp = await client.post(
        "/api/locations",
        json={
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "elevation_m": elevation_m,
            "timezone": timezone,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _insert_cache_row(
    location_id: int,
    source: str,
    *,
    start_date: str = "",
    end_date: str = "",
    payload: dict | None = None,
) -> None:
    """Directly insert a valid JSON row into weather_cache for the current test DB."""
    if payload is None:
        payload = {
            "latitude": 34.05,
            "longitude": -118.25,
            "hourly": {
                "time": ["2026-04-13T00:00"],
                "temperature_2m": [10.0],
            },
        }
    async with aiosqlite.connect(str(get_db_path())) as conn:
        await conn.execute(
            """INSERT INTO weather_cache
               (location_id, source, start_date, end_date, response_json, fetched_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (location_id, source, start_date, end_date, json.dumps(payload)),
        )
        await conn.commit()


# ---------------------------------------------------------------------------
# GET /api/weather/cache/stats
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cache_stats_empty(client):
    """Fresh DB → cache is empty → rows=0."""
    resp = await client.get("/api/weather/cache/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rows"] == 0
    # bytes may be 0 (no rows). dbstat might return 0 or a small non-zero table
    # overhead depending on whether the table has been populated previously.
    assert isinstance(data["bytes"], int)
    assert data["bytes"] >= 0


@pytest.mark.anyio
async def test_cache_stats_populated(client):
    """After inserting rows of various sources, stats should reflect them."""
    loc_id = await _create_location(client)

    await _insert_cache_row(loc_id, "forecast")
    await _insert_cache_row(loc_id, "ecmwf_pwv")
    await _insert_cache_row(loc_id, "openmeteo_aq")

    resp = await client.get("/api/weather/cache/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rows"] == 3
    # Either dbstat (pgsize) or the LENGTH(response_json) fallback should
    # report a non-zero byte count since the rows store real JSON.
    assert data["bytes"] > 0


# ---------------------------------------------------------------------------
# DELETE /api/weather/cache
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cache_clear_empty(client):
    """Clearing an empty cache returns deleted=0 and ok=true."""
    resp = await client.delete("/api/weather/cache")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"ok": True, "deleted": 0}


@pytest.mark.anyio
async def test_cache_clear_populated(client):
    """Clearing a populated cache deletes all rows."""
    loc_id = await _create_location(client)

    await _insert_cache_row(loc_id, "forecast")
    await _insert_cache_row(loc_id, "ecmwf_pwv")
    await _insert_cache_row(loc_id, "openmeteo_aq")

    resp = await client.delete("/api/weather/cache")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["deleted"] == 3

    # Verify the table is actually empty.
    async with aiosqlite.connect(str(get_db_path())) as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM weather_cache")
        remaining = (await cursor.fetchone())[0]
    assert remaining == 0

    # A follow-up stats call agrees.
    stats = await client.get("/api/weather/cache/stats")
    assert stats.status_code == 200
    assert stats.json()["rows"] == 0


# ---------------------------------------------------------------------------
# Polar no-imaging-window branch of _compute_night_data
# ---------------------------------------------------------------------------


def _make_fake_weather_polar_june(n_hours: int = 192) -> WeatherData:
    """Fake hourly weather for an 85°N location spanning 8 June days."""
    hours = []
    for i in range(n_hours):
        day = 15 + i // 24  # starts 2026-06-15, covers 8 days
        hour = i % 24
        hours.append(
            HourlyWeather(
                time=f"2026-06-{day:02d}T{hour:02d}:00",
                temperature_c=2.0,
                dew_point_c=0.0,
                humidity_pct=80.0,
                cloud_cover_pct=40.0,
                cloud_cover_low_pct=20.0,
                cloud_cover_mid_pct=10.0,
                cloud_cover_high_pct=10.0,
                wind_speed_kmh=15.0,
                wind_direction_deg=180.0,
                wind_gusts_kmh=25.0,
                visibility_m=15000.0,
                precipitation_mm=0.0,
                precipitation_probability_pct=10.0,
                wind_speed_200hpa_kmh=None,
                wind_speed_300hpa_kmh=None,
                wind_speed_500hpa_kmh=None,
                geopotential_200hpa_m=None,
                geopotential_300hpa_m=None,
                geopotential_500hpa_m=None,
            )
        )
    return WeatherData(
        latitude=85.0,
        longitude=0.0,
        source="forecast",
        hourly=hours,
        raw_json="{}",
    )


def _make_fake_supp_empty() -> dict[str, float | None]:
    return {}


@pytest.mark.anyio
async def test_forecast_polar_no_imaging_window(client):
    """85°N in June → midnight sun → no_imaging_window=True on returned days."""
    loc_id = await _create_location(
        client,
        name="Extreme Polar Observatory",
        latitude=85.0,
        longitude=0.0,
        elevation_m=10.0,
        timezone="UTC",
    )
    fake_weather = _make_fake_weather_polar_june()
    fake_supplementary = _make_fake_supp_empty()

    fake_now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=ZoneInfo("UTC"))

    class MockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return fake_now.astimezone(tz)
            return fake_now

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
        patch("nightcrate.api.weather.datetime", MockDatetime),
    ):
        resp = await client.get(
            "/api/weather/forecast",
            params={"location_id": loc_id, "include_moon": True},
        )

    assert resp.status_code == 200
    data = resp.json()

    no_imaging_days = [d for d in data["days"] if d["no_imaging_window"]]
    assert len(no_imaging_days) > 0, "85°N in June should yield at least one no-imaging-window day"

    # Every no-imaging-window day must match the shape produced by the polar
    # branch in _compute_night_data: all scores zero except moon (100), zero
    # darkness, dew_safe_window="none", and a valid deepest_darkness_reached.
    for day in no_imaging_days:
        assert day["imaging_quality"] == 0
        assert day["imaging_quality_label"] == "Poor"
        assert day["sky_clarity"] == 0
        assert day["transparency_score"] == 0
        assert day["seeing_score"] == 0
        assert day["wind_calm"] == 0
        assert day["moon_score"] == 100
        assert day["darkness_hours"] == 0
        assert day["moonless_dark_hours"] == 0
        assert day["dew_safe_window"]["label"] == "none"
        assert day["deepest_darkness_reached"] in ("astro", "nautical", "civil", "none")
        assert day["avg_cloud_cover_pct"] == 0
        assert day["avg_cloud_low_pct"] == 0
        assert day["avg_cloud_mid_pct"] == 0
        assert day["avg_cloud_high_pct"] == 0
        assert day["temp_min_c"] == 0
        assert day["temp_max_c"] == 0
        assert day["max_precipitation_probability_pct"] == 0
