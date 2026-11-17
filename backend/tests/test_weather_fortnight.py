"""Contracts for the compact per-location fortnight forecast."""

import asyncio
import threading
import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app
from nightcrate.services.astronomy import compute_night_summary
from nightcrate.services.imaging_rules import PRESETS
from nightcrate.services.weather import CloudModelData
from tests.test_weather_api import (
    NOW,
    _cached_night_summary,
    _data,
    _location,
    _model_series,
    _weather,
)


@pytest.fixture(autouse=True)
def _reuse_deterministic_astronomy(monkeypatch):
    monkeypatch.setattr("nightcrate.api.weather.compute_night_summary", _cached_night_summary)


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
    nights = fortnight.json()["nights"]
    assert [(n["date"], n["verdict"], n["moonless_dark_hours"]) for n in nights] == [
        (n["date"], n["verdict"], n["moonless_dark_hours"]) for n in forecast.json()["nights"]
    ]
    for night, source in zip(nights, forecast.json()["nights"], strict=True):
        astronomical = source["darkness_intervals"]["astronomical"]
        assert night["darkness"] == "astronomical"
        assert night["dark_hours"] == pytest.approx(_hours(astronomical), abs=0.01)
        assert night["runs"][0]["start_utc"] == astronomical[0]["start_utc"]
        assert night["runs"][-1]["end_utc"] == astronomical[-1]["end_utc"]
    assert fortnight.json()["evaluated_at"] == forecast.json()["evaluated_at"]
    assert fortnight.json()["stale_since"] is None


def _hours(intervals: list[dict]) -> float:
    seconds = 0.0
    for interval in intervals:
        start = datetime.fromisoformat(interval["start_utc"])
        seconds += (datetime.fromisoformat(interval["end_utc"]) - start).total_seconds()
    return round(seconds / 3600.0, 2)


def _moon_down_hours(runs: list[dict]) -> float:
    return _hours([run for run in runs if not run["moon_up"]])


async def test_astronomical_night_runs_cover_the_darkness_and_split_by_the_moon(
    client: AsyncClient,
):
    """Los Angeles, 17 October 2026: about 10 h of astronomical darkness."""
    location_id = await _location(client)
    _, fortnight = await _requests(client, location_id)
    first = fortnight.json()["nights"][0]
    assert first["date"] == "2026-10-17"
    summary = compute_night_summary(34.05, -118.25, None, date(2026, 10, 17), "America/Los_Angeles")
    assert first["darkness"] == "astronomical"
    assert first["dark_hours"] == summary.darkness_hours == pytest.approx(9.96, abs=0.01)
    # Local midnight (PDT, UTC−7) for the line's tick.
    assert first["midnight_utc"] == "2026-10-18T07:00:00Z"
    runs = first["runs"]
    assert [run["end_utc"] for run in runs[:-1]] == [run["start_utc"] for run in runs[1:]]
    assert _hours(runs) == pytest.approx(first["dark_hours"], abs=0.01)
    assert _moon_down_hours(runs) == pytest.approx(first["moonless_dark_hours"], abs=0.011)
    assert all(len(run["start"]) == len(run["end"]) == 5 for run in runs)


async def test_midnight_tick_uses_the_display_time_zone(client: AsyncClient):
    """An Auckland site shown in Honolulu time: its darkness begins the evening
    before in Honolulu, so the tick is that midnight, not the next one."""
    location_id = await _location(
        client,
        name="Display Zone Test",
        latitude=-36.85,
        longitude=174.76,
        timezone="Pacific/Honolulu",
        geo_timezone="Pacific/Auckland",
    )
    _, fortnight = await _requests(client, location_id)
    assert fortnight.status_code == 200, fortnight.text
    nights = fortnight.json()["nights"]
    assert (nights[0]["date"], nights[0]["midnight_utc"]) == ("2026-10-16", "2026-10-16T10:00:00Z")
    honolulu = ZoneInfo("Pacific/Honolulu")
    for night in nights:
        midnight = datetime.fromisoformat(night["midnight_utc"])
        assert midnight.astimezone(honolulu).time() == datetime.min.time()
        assert datetime.fromisoformat(night["runs"][0]["start_utc"]) < midnight
        assert midnight < datetime.fromisoformat(night["runs"][-1]["end_utc"])


async def test_nights_without_astronomical_darkness_use_nautical_then_civil(
    client: AsyncClient,
):
    """At 65° S from 17 October the Sun stops reaching −18°, then −12°."""
    location_id = await _location(
        client,
        name="Polar Test",
        latitude=-65.0,
        longitude=-64.0,
        timezone="America/Argentina/Ushuaia",
    )
    _, fortnight = await _requests(client, location_id)
    assert fortnight.status_code == 200
    nights = fortnight.json()["nights"]
    assert nights
    assert {night["darkness"] for night in nights} <= {"nautical", "civil"}
    assert nights[0]["darkness"] == "nautical"
    for night in nights:
        assert night["dark_hours"] > 0.0
        assert _hours(night["runs"]) == pytest.approx(night["dark_hours"], abs=0.01)
        assert _moon_down_hours(night["runs"]) == pytest.approx(
            night["moonless_dark_hours"], abs=0.011
        )


async def test_a_night_without_darkness_has_no_runs(client: AsyncClient):
    """At 78° S in late October the Sun stays within 6° of the horizon."""
    location_id = await _location(
        client,
        name="No Darkness Test",
        latitude=-78.0,
        longitude=166.7,
        timezone="Antarctica/McMurdo",
    )
    _, fortnight = await _requests(client, location_id)
    assert fortnight.status_code == 200, fortnight.text
    nights = fortnight.json()["nights"]
    assert nights
    for night in nights:
        assert night["darkness"] == "none"
        assert night["dark_hours"] == 0.0
        assert night["moonless_dark_hours"] == 0.0
        assert night["runs"] == []


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
    assert [function.__name__ for function in calls] == ["_run_fortnight"]

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
