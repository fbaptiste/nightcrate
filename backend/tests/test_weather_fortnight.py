"""Contracts for the compact per-location fortnight forecast."""

import asyncio
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app
from nightcrate.services.imaging_rules import PRESETS
from nightcrate.services.weather import CloudModelData
from tests.test_weather_api import NOW, _data, _location, _model_series, _weather


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _requests(client: AsyncClient, location_id: int, data=None):
    with (
        patch("nightcrate.api.weather._now", return_value=NOW),
        patch(
            "nightcrate.api.weather._load_forecast_data",
            new=AsyncMock(return_value=data or _data()),
        ),
    ):
        forecast = await client.post("/api/weather/forecast", json={"location_id": location_id})
        fortnight = await client.get("/api/weather/fortnight", params={"location_id": location_id})
    return forecast, fortnight


async def test_fortnight_matches_forecast_nights_and_moonless_hours(client: AsyncClient):
    location_id = await _location(client)
    forecast, fortnight = await _requests(client, location_id)
    assert forecast.status_code == fortnight.status_code == 200
    expected = [
        {
            "date": night["date"],
            "verdict": night["verdict"],
            "moonless_dark_hours": night["moonless_dark_hours"],
        }
        for night in forecast.json()["nights"]
    ]
    assert fortnight.json()["nights"] == expected
    assert fortnight.json()["evaluated_at"] == forecast.json()["evaluated_at"]
    assert fortnight.json()["stale_since"] is None


async def test_fortnight_uses_saved_rules_to_change_verdict(client: AsyncClient):
    location_id = await _location(client)
    weather = _weather()
    cloudy = {row.time_utc: (50.0, 50.0, 0.0, 0.0) for row in weather.hourly}
    data = _data(
        weather=weather,
        cloud_models=CloudModelData(
            models={
                model: _model_series(cloudy)
                for model in ("ecmwf_ifs025", "gfs_seamless", "icon_seamless")
            },
            raw_json="{}",
        ),
    )
    strict = await client.put(
        f"/api/locations/{location_id}/imaging-rules",
        json=PRESETS["attended_session"][1].model_copy(update={"cloud_max_pct": 20}).model_dump(),
    )
    assert strict.status_code == 200
    _, strict_response = await _requests(client, location_id, data)

    relaxed = await client.put(
        f"/api/locations/{location_id}/imaging-rules",
        json=PRESETS["attended_session"][1].model_copy(update={"cloud_max_pct": 80}).model_dump(),
    )
    assert relaxed.status_code == 200
    _, relaxed_response = await _requests(client, location_id, data)
    assert (
        strict_response.json()["nights"][0]["verdict"]
        != relaxed_response.json()["nights"][0]["verdict"]
    )


@pytest.mark.parametrize(
    ("forecast_stale", "cloud_stale", "expected"),
    [
        (None, 30, datetime(2026, 10, 17, 17, tzinfo=UTC)),
        (30, None, datetime(2026, 10, 17, 16, tzinfo=UTC)),
    ],
)
async def test_stale_since_identifies_the_stale_source(
    client: AsyncClient,
    forecast_stale: int | None,
    cloud_stale: int | None,
    expected: datetime,
):
    location_id = await _location(client)
    data = replace(
        _data(
            fetched_at=datetime(2026, 10, 17, 16, tzinfo=UTC),
            forecast_stale_minutes=forecast_stale,
            cloud_stale_minutes=cloud_stale,
        ),
        cloud_fetched_at=datetime(2026, 10, 17, 17, tzinfo=UTC),
        cloud_attempted_at=NOW - timedelta(minutes=1),
    )
    _, fortnight = await _requests(client, location_id, data)
    assert fortnight.status_code == 200, fortnight.text
    assert fortnight.json()["stale_since"] == expected.isoformat().replace("+00:00", "Z")


async def test_fortnight_uses_to_thread_and_unknown_location_is_404(client: AsyncClient):
    location_id = await _location(client)
    calls = []

    async def run_in_place(function, *args):
        calls.append(function)
        return function(*args)

    with (
        patch("nightcrate.api.weather._now", return_value=NOW),
        patch("nightcrate.api.weather._load_forecast_data", new=AsyncMock(return_value=_data())),
        patch("nightcrate.api.weather.asyncio.to_thread", side_effect=run_in_place),
    ):
        response = await client.get("/api/weather/fortnight", params={"location_id": location_id})
    assert response.status_code == 200, response.text
    assert [function.__name__ for function in calls] == ["_run_build"]

    missing = await client.get("/api/weather/fortnight", params={"location_id": 999999})
    assert missing.status_code == 404


async def test_concurrent_fortnight_builds_do_not_overlap(client: AsyncClient):
    location_id = await _location(client)
    counter_lock = threading.Lock()
    active = 0
    max_active = 0

    def tracked_build(*_args):
        nonlocal active, max_active
        with counter_lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with counter_lock:
            active -= 1
        return SimpleNamespace(
            evaluated_at=NOW,
            stale_sources=SimpleNamespace(forecast=None, cloud_models=None),
            nights=[],
        )

    with (
        patch("nightcrate.api.weather._now", return_value=NOW),
        patch("nightcrate.api.weather._load_forecast_data", new=AsyncMock(return_value=_data())),
        patch("nightcrate.api.weather._build_forecast", side_effect=tracked_build),
    ):
        responses = await asyncio.gather(
            *(
                client.get("/api/weather/fortnight", params={"location_id": location_id})
                for _ in range(3)
            )
        )

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert max_active == 1


async def test_provider_failure_matches_forecast(client: AsyncClient):
    location_id = await _location(client)
    failure = HTTPException(status_code=503, detail="Weather forecast is unavailable")
    with patch("nightcrate.api.weather._load_forecast_data", new=AsyncMock(side_effect=failure)):
        forecast = await client.post("/api/weather/forecast", json={"location_id": location_id})
        fortnight = await client.get("/api/weather/fortnight", params={"location_id": location_id})
    assert forecast.status_code == fortnight.status_code == 503
    assert forecast.json() == fortnight.json()
