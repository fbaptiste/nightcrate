"""Tests for the multi-model cloud forecast and the score spread (v0.41.5).

The app's cloud series comes from ECMWF rather than Open-Meteo's `best_match`,
which resolves to GFS. That was measured, not assumed: over 126 night hours,
day-ahead mean absolute error against ERA5 was ECMWF 18.2 pts vs GFS 32.4, and
GFS called a clear night cloudy 25 times against ECMWF's 8. The spread across
three models is surfaced so a night the models disagree about does not read as
settled fact.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.api.weather import _cloud_for, _score_spread
from nightcrate.main import app
from nightcrate.services.imaging_quality import Mode
from nightcrate.services.weather import (
    CLOUD_PRIMARY_MODEL,
    CLOUD_SPREAD_MODELS,
    CloudModelData,
    HourlyWeather,
    WeatherData,
    parse_cloud_models,
)

from .test_weather_api import _make_fake_supplementary, _make_fake_weather


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _hour(**kw) -> HourlyWeather:
    base = dict(
        time="2026-04-13T22:00",
        temperature_c=12.0,
        dew_point_c=5.0,
        humidity_pct=60.0,
        cloud_cover_pct=50.0,
        cloud_cover_low_pct=50.0,
        cloud_cover_mid_pct=0.0,
        cloud_cover_high_pct=0.0,
        wind_speed_kmh=8.0,
        wind_direction_deg=180.0,
        wind_gusts_kmh=15.0,
        visibility_m=20000.0,
        precipitation_mm=0.0,
        precipitation_probability_pct=10.0,
    )
    return HourlyWeather(**{**base, **kw})


SCORE_KW = dict(
    seeing=88.0,
    transparency=41.0,
    darkness=1.0,
    moon_altitude_deg=None,
    moon_illumination_pct=0.0,
    mode=Mode.NORMAL,
)


def _models(**per_model) -> CloudModelData:
    """CloudModelData for one hour: model -> total cloud (layers zeroed)."""
    return CloudModelData(
        models={m: {"2026-04-13T22:00": (t, 0.0, 0.0, 0.0)} for m, t in per_model.items()},
        raw_json="{}",
    )


# ---------------------------------------------------------------------------
# Parsing the multi-model response
# ---------------------------------------------------------------------------


class TestParseCloudModels:
    def test_splits_suffixed_series_per_model(self):
        hourly = {
            "time": ["2026-04-13T22:00", "2026-04-13T23:00"],
            "cloud_cover_ecmwf_ifs025": [10, 20],
            "cloud_cover_low_ecmwf_ifs025": [1, 2],
            "cloud_cover_mid_ecmwf_ifs025": [3, 4],
            "cloud_cover_high_ecmwf_ifs025": [5, 6],
            "cloud_cover_gfs_seamless": [90, 80],
            "cloud_cover_low_gfs_seamless": [0, 0],
            "cloud_cover_mid_gfs_seamless": [0, 0],
            "cloud_cover_high_gfs_seamless": [90, 80],
        }
        out = parse_cloud_models(hourly, ("ecmwf_ifs025", "gfs_seamless"))
        assert set(out) == {"ecmwf_ifs025", "gfs_seamless"}
        assert out["ecmwf_ifs025"]["2026-04-13T22:00"] == (10.0, 1.0, 3.0, 5.0)
        assert out["gfs_seamless"]["2026-04-13T23:00"] == (80.0, 0.0, 0.0, 80.0)

    def test_skips_a_model_that_is_absent(self):
        hourly = {
            "time": ["2026-04-13T22:00"],
            "cloud_cover_ecmwf_ifs025": [10],
            "cloud_cover_low_ecmwf_ifs025": [0],
            "cloud_cover_mid_ecmwf_ifs025": [0],
            "cloud_cover_high_ecmwf_ifs025": [0],
        }
        out = parse_cloud_models(hourly, CLOUD_SPREAD_MODELS)
        assert set(out) == {"ecmwf_ifs025"}

    def test_drops_hours_past_a_model_horizon(self):
        """ICON's horizon ends before the 8-day window, leaving trailing nulls."""
        hourly = {
            "time": ["2026-04-13T22:00", "2026-04-13T23:00"],
            "cloud_cover_icon_seamless": [10, None],
            "cloud_cover_low_icon_seamless": [0, None],
            "cloud_cover_mid_icon_seamless": [0, None],
            "cloud_cover_high_icon_seamless": [0, None],
        }
        out = parse_cloud_models(hourly, ("icon_seamless",))
        assert list(out["icon_seamless"]) == ["2026-04-13T22:00"]


# ---------------------------------------------------------------------------
# Which cloud series gets scored
# ---------------------------------------------------------------------------


class TestPrimaryCloudSelection:
    def test_prefers_the_primary_model(self):
        h = _hour(cloud_cover_pct=90.0, cloud_cover_low_pct=90.0)
        cm = _models(**{CLOUD_PRIMARY_MODEL: 12.0, "gfs_seamless": 90.0})
        assert _cloud_for(h, cm, h.time) == (12.0, 0.0, 0.0, 0.0)

    def test_falls_back_to_the_main_forecast_when_the_hour_is_missing(self):
        h = _hour(cloud_cover_pct=90.0, cloud_cover_low_pct=90.0)
        cm = CloudModelData(models={CLOUD_PRIMARY_MODEL: {}}, raw_json="{}")
        assert _cloud_for(h, cm, h.time) == (90.0, 90.0, 0.0, 0.0)

    def test_falls_back_when_there_are_no_models_at_all(self):
        """A failed cloud-model fetch must not change the score."""
        h = _hour(cloud_cover_pct=35.0, cloud_cover_low_pct=35.0)
        assert _cloud_for(h, None, h.time) == (35.0, 35.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# The spread
# ---------------------------------------------------------------------------


class TestScoreSpread:
    def test_returns_the_extreme_results_not_bare_numbers(self):
        """Full results, so a night can aggregate and label them like the headline."""
        h = _hour()
        cm = _models(ecmwf_ifs025=0.0, gfs_seamless=100.0, icon_seamless=50.0)
        low, high = _score_spread(h, cm, h.time, **SCORE_KW)
        assert low.score == 0  # the 100%-cloud model
        assert high.score > 50  # the clear one
        assert low.availability < high.availability
        assert low.label != high.label

    def test_agreeing_models_give_an_empty_range(self):
        h = _hour()
        cm = _models(ecmwf_ifs025=100.0, gfs_seamless=100.0, icon_seamless=100.0)
        low, high = _score_spread(h, cm, h.time, **SCORE_KW)
        assert low.score == high.score == 0
        assert low.label == high.label

    def test_needs_two_models(self):
        h = _hour()
        assert _score_spread(h, _models(ecmwf_ifs025=10.0), h.time, **SCORE_KW) is None

    def test_none_without_model_data(self):
        h = _hour()
        assert _score_spread(h, None, h.time, **SCORE_KW) is None

    def test_numeric_difference_without_a_verdict_difference(self):
        """Two heavily-clouded models differ numerically but agree on the verdict,
        which is what the uncertainty flag is about."""
        h = _hour()
        cm = _models(ecmwf_ifs025=97.0, gfs_seamless=100.0)
        low, high = _score_spread(h, cm, h.time, **SCORE_KW)
        assert low.label == high.label, (low.score, high.score)

    def test_only_cloud_varies_between_the_runs(self):
        """The range must isolate forecast disagreement, not mix in other factors."""
        h = _hour()
        cm = _models(ecmwf_ifs025=0.0, gfs_seamless=0.0)
        low, high = _score_spread(h, cm, h.time, **SCORE_KW)
        assert low.score == high.score
        assert low.quality == pytest.approx(high.quality)


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------


async def _location(client: AsyncClient) -> int:
    resp = await client.post(
        "/api/locations",
        json={
            "name": "Spread Test",
            "latitude": 34.05,
            "longitude": -118.25,
            "elevation_m": 300.0,
            "timezone": "America/Los_Angeles",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _wide_spread_models() -> CloudModelData:
    """Clear vs overcast for every hour of the fake forecast."""
    models = {}
    for name, total in ((CLOUD_PRIMARY_MODEL, 0.0), ("gfs_seamless", 100.0)):
        series = {}
        for i in range(48):
            t = f"2026-04-{13 + i // 24:02d}T{i % 24:02d}:00"
            series[t] = (total, 0.0, 0.0, total)
        models[name] = series
    return CloudModelData(models=models, raw_json="{}")


@pytest.mark.anyio
async def test_hourly_reports_the_spread(client):
    loc = await _location(client)
    with (
        patch(
            "nightcrate.api.weather._fetch_or_cached",
            new_callable=AsyncMock,
            return_value=_make_fake_weather(),
        ),
        patch(
            "nightcrate.api.weather._fetch_or_cached_supplementary",
            new_callable=AsyncMock,
            return_value=_make_fake_supplementary(),
        ),
        patch(
            "nightcrate.api.weather._fetch_or_cached_cloud_models",
            new_callable=AsyncMock,
            return_value=_wide_spread_models(),
        ),
    ):
        resp = await client.get(
            "/api/weather/hourly", params={"location_id": loc, "date": "2026-04-13"}
        )
    assert resp.status_code == 200
    hours = resp.json()["hours"]
    assert hours, "expected hourly rows"
    for h in hours:
        assert h["score_min"] is not None and h["score_max"] is not None
        assert h["score_min"] <= h["imaging_quality"] <= h["score_max"]
    # A clear-vs-overcast disagreement must be flagged on at least the dark hours.
    assert any(h["forecast_uncertain"] for h in hours)


@pytest.mark.anyio
async def test_spread_absent_when_the_fetch_fails(client):
    """The documented fallback: no models, no range, and the score still works."""
    loc = await _location(client)
    with (
        patch(
            "nightcrate.api.weather._fetch_or_cached",
            new_callable=AsyncMock,
            return_value=_make_fake_weather(),
        ),
        patch(
            "nightcrate.api.weather._fetch_or_cached_supplementary",
            new_callable=AsyncMock,
            return_value=_make_fake_supplementary(),
        ),
        patch(
            "nightcrate.api.weather._fetch_or_cached_cloud_models",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        resp = await client.get(
            "/api/weather/hourly", params={"location_id": loc, "date": "2026-04-13"}
        )
    assert resp.status_code == 200
    for h in resp.json()["hours"]:
        assert h["score_min"] is None
        assert h["score_max"] is None
        assert h["forecast_uncertain"] is False
        assert isinstance(h["imaging_quality"], int)


@pytest.mark.anyio
async def test_cloud_models_cache_source_is_accepted(client):
    """Migration 0057 widened the weather_cache CHECK vocabulary."""
    from nightcrate.db.session import get_db

    loc = await _location(client)
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO weather_cache (location_id, source, start_date, end_date, response_json)
               VALUES (?, 'cloud_models', '', '', '{}')""",
            (loc,),
        )
        await conn.commit()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM weather_cache WHERE source = 'cloud_models'"
        )
        assert (await cursor.fetchone())[0] == 1


def _today_hours(n_days: int = 9) -> list[str]:
    """Hour labels starting today.

    `get_forecast` iterates forward from *today*, so weather fixed to a date in
    the past yields zero nights — which is why the older forecast tests guard on
    `if days`. These tests need real nights, so the fixture tracks the clock.
    """
    start = date.today()
    return [
        f"{start + timedelta(days=i):%Y-%m-%d}T{h:02d}:00" for i in range(n_days) for h in range(24)
    ]


def _weather_from_today(cloud: float = 20.0) -> WeatherData:
    hours = [
        HourlyWeather(
            time=t,
            temperature_c=12.0,
            dew_point_c=5.0,
            humidity_pct=60.0,
            cloud_cover_pct=cloud,
            cloud_cover_low_pct=0.0,
            cloud_cover_mid_pct=0.0,
            cloud_cover_high_pct=cloud,
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
        for t in _today_hours()
    ]
    return WeatherData(
        latitude=34.05, longitude=-118.25, source="forecast", hourly=hours, raw_json="{}"
    )


def _uniform_models(**per_model) -> CloudModelData:
    """One constant cloud cover per model, across the whole fixture window."""
    times = _today_hours()
    return CloudModelData(
        models={n: {t: (c, 0.0, 0.0, c) for t in times} for n, c in per_model.items()},
        raw_json="{}",
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "clouds,expect_flag",
    [
        ({"ecmwf_ifs025": 100.0, "gfs_seamless": 97.0}, False),  # both hopeless
        ({"ecmwf_ifs025": 0.0, "gfs_seamless": 3.0}, False),  # both excellent
        ({"ecmwf_ifs025": 0.0, "gfs_seamless": 100.0}, True),  # clear vs overcast
    ],
)
async def test_night_is_flagged_only_when_the_verdict_differs(client, clouds, expect_flag):
    """Regression: the flag must not be on for every night.

    It was, briefly — the night flag was `any()` over the hourly flags, and with
    three models a ten-hour night almost always has one hour whose extremes
    straddle a label boundary. A flag that is always on carries no information.
    The night is judged on its own aggregated extremes instead.
    """
    loc = await _location(client)
    with (
        patch(
            "nightcrate.api.weather._fetch_or_cached",
            new_callable=AsyncMock,
            return_value=_weather_from_today(),
        ),
        patch(
            "nightcrate.api.weather._fetch_or_cached_supplementary",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "nightcrate.api.weather._fetch_or_cached_cloud_models",
            new_callable=AsyncMock,
            return_value=_uniform_models(**clouds),
        ),
    ):
        resp = await client.get("/api/weather/forecast", params={"location_id": loc})
    assert resp.status_code == 200
    days = resp.json()["days"]
    assert days, "expected at least one night"
    for day in days:
        assert day["forecast_uncertain"] is expect_flag, (
            day["date"],
            day["score_min"],
            day["score_max"],
            day["imaging_quality_label"],
        )
        if day["score_min"] is not None:
            assert day["score_min"] <= day["imaging_quality"] <= day["score_max"]
