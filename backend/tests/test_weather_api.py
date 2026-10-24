"""End-to-end contracts for the personal weather verdict endpoint."""

import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from nightcrate.api.weather import ForecastData, _is_single_model, _write_cache, _write_cloud_cache
from nightcrate.api.weather import (
    _fetch_or_cached_cloud_models as REAL_FETCH_OR_CACHED_CLOUD_MODELS,
)
from nightcrate.api.weather_methodology import METHODOLOGY_DETAILS, METHODOLOGY_SUMMARY
from nightcrate.main import app
from nightcrate.services import astronomy
from nightcrate.services.astronomy import compute_night_summary
from nightcrate.services.imaging_rules import PRESETS
from nightcrate.services.weather import (
    CloudModelData,
    HourlyWeather,
    ModelSeries,
    WeatherData,
    parse_hourly,
)

NOW = datetime(2026, 10, 17, 19, tzinfo=UTC)  # local noon in Los Angeles


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _location(
    client: AsyncClient,
    *,
    name: str = "Verdict Test",
    latitude: float = 34.05,
    longitude: float = -118.25,
    timezone: str = "America/Los_Angeles",
    geo_timezone: str | None = None,
) -> int:
    body = {
        "name": name,
        "latitude": latitude,
        "longitude": longitude,
        "elevation_m": 300,
        "timezone": timezone,
    }
    if geo_timezone is not None:
        body["geo_timezone"] = geo_timezone
    response = await client.post("/api/locations", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _weather(
    *,
    start: datetime = datetime(2026, 10, 16, tzinfo=UTC),
    hours: int = 240,
    rain_at: datetime | None = None,
    rain_probability_pct: float = 10.0,
    null_at: datetime | None = None,
) -> WeatherData:
    rows = []
    for index in range(hours):
        time = start + timedelta(hours=index)
        rows.append(
            HourlyWeather(
                time_utc=time,
                temperature_c=None if time == null_at else 12.0,
                dew_point_c=4.0,
                humidity_pct=None if time == null_at else 40.0,
                cloud_cover_pct=0.0,
                cloud_cover_low_pct=0.0,
                cloud_cover_mid_pct=0.0,
                cloud_cover_high_pct=0.0,
                wind_speed_kmh=None if time == null_at else 5.0,
                wind_direction_deg=180.0,
                wind_gusts_kmh=10.0,
                visibility_m=None if time == null_at else 25000.0,
                precipitation_mm=0.0,
                precipitation_probability_pct=rain_probability_pct if time == rain_at else 0.0,
            )
        )
    return WeatherData(34.05, -118.25, "forecast", rows, "{}")


def _data(
    *,
    weather: WeatherData | None = None,
    cloud_models: CloudModelData | None = None,
    fetched_at: datetime = NOW,
    meta_raw: str | None = None,
    forecast_stale_minutes: int | None = None,
    cloud_stale_minutes: int | None = None,
) -> ForecastData:
    weather = weather or _weather()
    if cloud_models is None:
        values = {row.time_utc: (0.0, 0.0, 0.0, 0.0) for row in weather.hourly}
        cloud_models = CloudModelData(
            models={
                model: _model_series(values)
                for model in ("ecmwf_ifs025", "gfs_seamless", "icon_seamless")
            },
            raw_json="{}",
        )
    return ForecastData(
        weather=weather,
        cloud_models=cloud_models,
        pwv_by_time={},
        aod_by_time={},
        fetched_at=fetched_at,
        forecast_attempted_at=fetched_at,
        cloud_fetched_at=fetched_at if cloud_models is not None else None,
        cloud_attempted_at=fetched_at,
        meta_raw=meta_raw,
        forecast_stale_minutes=forecast_stale_minutes,
        cloud_stale_minutes=cloud_stale_minutes,
    )


def _model_series(
    values: dict[datetime, tuple[float | None, float | None, float | None, float | None]],
) -> ModelSeries:
    return ModelSeries(
        cloud_total_pct={stamp: figures[0] for stamp, figures in values.items()},
        cloud_low_pct={stamp: figures[1] for stamp, figures in values.items()},
        cloud_mid_pct={stamp: figures[2] for stamp, figures in values.items()},
        cloud_high_pct={stamp: figures[3] for stamp, figures in values.items()},
        precipitation_mm={stamp: 0.0 for stamp in values},
        fields_present=frozenset(
            {
                "cloud_cover",
                "cloud_cover_low",
                "cloud_cover_mid",
                "cloud_cover_high",
                "precipitation",
            }
        ),
    )


def _metadata_raw(initialisations: dict[str, datetime]) -> str:
    return json.dumps(
        {
            domain: {
                "last_run_initialisation_time": initialisation.timestamp(),
                "last_run_availability_time": (initialisation + timedelta(hours=1)).timestamp(),
                "temporal_resolution_seconds": 3600,
                "update_interval_seconds": 3600,
            }
            for domain, initialisation in initialisations.items()
        }
    )


def _raw_times(*, before: datetime | None = None) -> list[datetime]:
    start = datetime(2026, 10, 16, tzinfo=UTC)
    # One past day plus the 16-day forecast request.
    values = [start + timedelta(hours=index) for index in range(17 * 24)]
    return [value for value in values if before is None or value < before]


def _weather_json(*, before: datetime | None = None) -> str:
    times = _raw_times(before=before)
    count = len(times)
    return json.dumps(
        {
            "latitude": 34.05,
            "longitude": -118.25,
            "utc_offset_seconds": 0,
            "hourly": {
                "time": [int(value.timestamp()) for value in times],
                "temperature_2m": [12.0] * count,
                "dew_point_2m": [4.0] * count,
                "relative_humidity_2m": [40.0] * count,
                "cloud_cover": [0.0] * count,
                "cloud_cover_low": [0.0] * count,
                "cloud_cover_mid": [0.0] * count,
                "cloud_cover_high": [0.0] * count,
                "wind_speed_10m": [5.0] * count,
                "wind_direction_10m": [180.0] * count,
                "wind_gusts_10m": [10.0] * count,
                "visibility": [25000.0] * count,
                "precipitation": [0.0] * count,
                "precipitation_probability": [0.0] * count,
            },
        }
    )


def _cloud_json(*, before: datetime | None = None) -> str:
    times = _raw_times(before=before)
    count = len(times)
    hourly: dict[str, list[int] | list[float]] = {
        "time": [int(value.timestamp()) for value in times]
    }
    for model in ("ecmwf_ifs025", "gfs_seamless", "icon_seamless"):
        for variable in (
            "cloud_cover",
            "cloud_cover_low",
            "cloud_cover_mid",
            "cloud_cover_high",
            "precipitation",
            "precipitation_probability",
        ):
            hourly[f"{variable}_{model}"] = [0.0] * count
    return json.dumps({"utc_offset_seconds": 0, "hourly": hourly})


async def _seed_real_cache(
    location_id: int,
    *,
    forecast_age: timedelta = timedelta(hours=1),
    cloud_age: timedelta = timedelta(hours=1),
    cloud_json: str | None = None,
    weather_json: str | None = None,
) -> None:
    empty_supplementary = json.dumps({"utc_offset_seconds": 0, "hourly": {"time": []}})
    await _write_cache(location_id, "forecast", weather_json or _weather_json(), NOW - forecast_age)
    await _write_cloud_cache(
        location_id,
        cloud_json or _cloud_json(),
        "{}",
        NOW - cloud_age,
    )
    await _write_cache(location_id, "ecmwf_pwv", empty_supplementary, NOW - timedelta(hours=1))
    await _write_cache(location_id, "openmeteo_aq", empty_supplementary, NOW - timedelta(hours=1))


async def _forecast(
    client: AsyncClient,
    body: dict,
    data: ForecastData | None = None,
    *,
    now: datetime = NOW,
):
    with (
        patch("nightcrate.api.weather._now", return_value=now),
        patch(
            "nightcrate.api.weather._load_forecast_data",
            new=AsyncMock(return_value=data or _data()),
        ),
    ):
        return await client.post("/api/weather/forecast", json=body)


def _compact_duration(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    rounded = Decimal.from_float(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return str(rounded).removesuffix(".0")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.25, "1.3"),
        (1.249999999, "1.2"),
        (10.05, "10.1"),
        (0.35, "0.3"),
        (10.0, "10"),
        (2.96, "3"),
    ],
)
def test_compact_duration_matches_ui_rounding(value: float, expected: str):
    assert _compact_duration(value) == expected


def _assert_forecast_json_equivalent(exact, fast, path: str = "response") -> None:
    if path.endswith(".missing_hours") and isinstance(exact, int | float):
        assert isinstance(fast, int | float), path
        assert abs(exact - fast) <= 2 / 3600, path
        assert _compact_duration(float(exact)) == _compact_duration(float(fast)), path
        return
    if (
        isinstance(exact, str)
        and isinstance(fast, str)
        and re.match(r"^\d{4}-\d{2}-\d{2}T", exact)
        and re.match(r"^\d{4}-\d{2}-\d{2}T", fast)
    ):
        exact_datetime = datetime.fromisoformat(exact.replace("Z", "+00:00"))
        fast_datetime = datetime.fromisoformat(fast.replace("Z", "+00:00"))
        assert abs(exact_datetime - fast_datetime) <= timedelta(seconds=1), path
        return
    if isinstance(exact, dict):
        assert isinstance(fast, dict), path
        assert fast.keys() == exact.keys(), path
        for key in exact:
            _assert_forecast_json_equivalent(exact[key], fast[key], f"{path}.{key}")
        return
    if isinstance(exact, list):
        assert isinstance(fast, list), path
        assert len(fast) == len(exact), path
        for index, (exact_item, fast_item) in enumerate(zip(exact, fast, strict=True)):
            _assert_forecast_json_equivalent(exact_item, fast_item, f"{path}[{index}]")
        return
    assert fast == exact, path


async def test_forecast_response_equivalent_to_exact_astronomy(
    client: AsyncClient,
    monkeypatch,
):
    from nightcrate.api.weather import _night_summary_cached

    location_id = await _location(client)
    body = {
        "location_id": location_id,
        "rules": PRESETS["attended_session"][1].model_dump(),
    }

    with monkeypatch.context() as exact_patch:
        exact_patch.setattr(
            astronomy,
            "_spline_altitudes",
            lambda fn, times, location, node_every=10: fn(times, location),
        )
        _night_summary_cached.cache_clear()
        exact_response = await _forecast(client, body)

    _night_summary_cached.cache_clear()
    fast_response = await _forecast(client, body)

    assert exact_response.status_code == 200, exact_response.text
    assert fast_response.status_code == 200, fast_response.text
    _assert_forecast_json_equivalent(exact_response.json(), fast_response.json())


async def test_forecast_returns_fourteen_nights(client: AsyncClient):
    location_id = await _location(client)
    response = await _forecast(client, {"location_id": location_id})
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["nights"]) == 14
    assert data["rules_saved"] is False
    assert data["rules"] == PRESETS["attended_session"][1].model_dump()
    assert data["nights"][0]["cloud_source"] == "ecmwf"
    assert data["nights"][0]["verdict"] == "go"
    assert data["nights"][0]["single_model"] is False
    assert data["evaluated_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert data["ignored_controls"] == []
    assert data["run_age_minutes"]["ecmwf_ifs025"] is None
    first = data["nights"][0]
    assert first["controls"] == {
        "gear_out": None,
        "gear_in": None,
        "imaging_from": None,
        "imaging_until": None,
    }
    assert first["model_statuses"]["ecmwf_ifs025"] == "go"
    assert first["primary_model"] == "ecmwf_ifs025"
    assert first["cloud_combination"] == "majority"
    assert first["differing_hours"] == 0
    assert first["compared_hours"] > 0
    assert first["cloud_models"] == ["ecmwf_ifs025", "gfs_seamless", "icon_seamless"]
    assert first["cloud_models_used"] == first["cloud_models"]
    assert first["default_cloud_used"] is False
    assert first["layer_model"] == "ecmwf_ifs025"
    assert {item["model"] for item in first["coverage"]} == set(first["model_statuses"])
    assert first["exposure"] is None
    assert first["imaging"] is not None
    assert isinstance(first["other_reasons"], list)
    assert first["advisory"] is None
    assert {"start_utc", "end_utc", "model", "models", "missing_hours"} <= first["reason"].keys()
    assert "period" not in first["reason"]
    hour = first["hours"][0]
    assert "gear_out_minutes" not in hour
    assert "effective_cloud_pct" not in hour
    assert set(("exposure_minutes", "session_state", "disagrees", "cloud_pct")) <= hour.keys()
    assert set(("expected", "model_precip_mm")) <= hour.keys()
    assert "chance_period" not in hour
    assert "chance_limit_pct" not in hour
    assert "transparency_tier" in hour


async def test_forecast_without_system_tz_database(client: AsyncClient, no_system_tz_database):
    """Issue #16: on Windows the forecast failed with ZoneInfoNotFoundError."""
    location_id = await _location(
        client, name="Rome", latitude=41.9, longitude=12.5, timezone="Europe/Rome"
    )
    response = await _forecast(client, {"location_id": location_id})
    assert response.status_code == 200, response.text
    assert len(response.json()["nights"]) == 14


async def test_evaluated_at_is_now(client: AsyncClient):
    location_id = await _location(client)
    response = await _forecast(client, {"location_id": location_id})

    assert response.status_code == 200, response.text
    assert datetime.fromisoformat(response.json()["evaluated_at"]) == NOW


async def test_resolution_indicator_fields_and_run_ages(client: AsyncClient):
    location_id = await _location(client)
    ecmwf_init = datetime(2026, 10, 12, 18, tzinfo=UTC)
    meta_raw = _metadata_raw(
        {
            "ecmwf_ifs025": ecmwf_init,
            "ncep_gfs013": datetime(2026, 10, 17, 12, tzinfo=UTC),
        }
    )
    response = await _forecast(
        client,
        {"location_id": location_id},
        _data(meta_raw=meta_raw),
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["run_age_minutes"] == {
        "ecmwf_ifs025": 7260,
        "gfs_seamless": 420,
        "icon_seamless": None,
    }
    first = data["nights"][0]
    assert first["cloud_coarse_from"] == "05:00"
    assert first["cloud_coarse_from_utc"] == "2026-10-18T12:00:00Z"


async def test_coverage_line_fields(client: AsyncClient):
    location_id = await _location(client)
    fetched_at = datetime(2026, 10, 11, 8, tzinfo=UTC)
    response = await _forecast(
        client,
        {"location_id": location_id},
        _data(fetched_at=fetched_at),
    )

    assert response.status_code == 200, response.text
    icon = next(
        item
        for item in response.json()["nights"][0]["coverage"]
        if item["model"] == "icon_seamless"
    )
    assert icon["status"] == "not_expected"
    assert icon["expected_until"] == "15:00"
    assert icon["expected_until_utc"] == "2026-10-17T22:00:00Z"


def test_single_model_ignores_comparisons_beyond_coverage():
    assert _is_single_model("uncertain", ("ecmwf_ifs025",))
    assert _is_single_model("single", ("gfs_seamless",))
    assert not _is_single_model("majority", ("ecmwf_ifs025", "gfs_seamless"))


async def test_layer_model_tracks_gfs_preference(client: AsyncClient):
    location_id = await _location(client)
    rules = PRESETS["attended_session"][1].model_copy(
        update={
            "cloud_use_ecmwf": False,
            "cloud_use_icon": False,
            "cloud_preferred_model": "gfs_seamless",
        }
    )

    response = await _forecast(
        client,
        {"location_id": location_id, "rules": rules.model_dump()},
    )

    assert response.status_code == 200, response.text
    assert response.json()["nights"][0]["layer_model"] == "gfs_seamless"


async def test_forecast_reports_all_darkness_levels(client: AsyncClient):
    """The darkness band needs the exact −6°/−12°/−18° crossings, nested in order."""
    location_id = await _location(client)
    response = await _forecast(client, {"location_id": location_id})
    assert response.status_code == 200, response.text
    night = response.json()["nights"][0]
    summary = compute_night_summary(34.05, -118.25, 300, date(2026, 10, 17), "America/Los_Angeles")
    zone = ZoneInfo("America/Los_Angeles")
    for level in ("civil", "nautical", "astronomical"):
        assert night["darkness_intervals"][level] == [
            {
                "start": start.astimezone(zone).strftime("%H:%M"),
                "end": end.astimezone(zone).strftime("%H:%M"),
                "start_utc": start.isoformat().replace("+00:00", "Z"),
                "end_utc": end.isoformat().replace("+00:00", "Z"),
            }
            for start, end in summary.dark_intervals[level]
        ]
    (civil,) = night["darkness_intervals"]["civil"]
    (nautical,) = night["darkness_intervals"]["nautical"]
    (astro,) = night["darkness_intervals"]["astronomical"]
    # Evening times rise toward deeper darkness; morning times fall back.
    assert civil["start"] < nautical["start"] < astro["start"]
    assert astro["end"] < nautical["end"] < civil["end"]


async def test_night_summaries_are_memoized(client: AsyncClient):
    location_id = await _location(client)
    with patch(
        "nightcrate.api.weather.compute_night_summary",
        wraps=compute_night_summary,
    ) as compute:
        first = await _forecast(client, {"location_id": location_id})
        second = await _forecast(client, {"location_id": location_id})

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert compute.call_count == 14


async def test_forecast_uses_saved_rules(client: AsyncClient):
    location_id = await _location(client)
    rules = PRESETS["left_out_all_night"][1].model_dump()
    saved = await client.put(f"/api/locations/{location_id}/imaging-rules", json=rules)
    assert saved.status_code == 200
    response = await _forecast(client, {"location_id": location_id})
    assert response.status_code == 200
    assert response.json()["rules_saved"] is True
    assert response.json()["rules"]["rain_policy"] == "night_off"


async def test_cloud_rule_fields_round_trip_and_reject_empty_selection(client: AsyncClient):
    location_id = await _location(client)
    rules = PRESETS["attended_session"][1].model_dump()
    rules.update(
        cloud_use_ecmwf=False,
        cloud_use_gfs=True,
        cloud_use_icon=True,
        cloud_preferred_model="icon_seamless",
        cloud_combination="uncertain",
    )
    saved = await client.put(f"/api/locations/{location_id}/imaging-rules", json=rules)
    assert saved.status_code == 200, saved.text
    assert saved.json()["rules"] == rules

    invalid = {**rules, "cloud_use_gfs": False, "cloud_use_icon": False}
    rejected = await client.put(
        f"/api/locations/{location_id}/imaging-rules",
        json=invalid,
    )
    assert rejected.status_code == 422
    assert "Choose at least one cloud forecast" in rejected.text


async def test_forecast_draft_rules_preview_does_not_save(client: AsyncClient):
    location_id = await _location(client)
    # Preceding-hour semantics: 10:00 UTC is rain over 02:00–03:00 PDT.
    weather = _weather(
        rain_at=datetime(2026, 10, 18, 10, tzinfo=UTC),
        rain_probability_pct=11.0,
    )
    default = await _forecast(client, {"location_id": location_id}, _data(weather=weather))
    assert default.status_code == 200
    assert default.json()["nights"][0]["verdict"] == "go"

    draft = PRESETS["left_out_all_night"][1].model_dump()
    preview = await _forecast(
        client,
        {"location_id": location_id, "rules": draft},
        _data(weather=weather),
    )
    first = preview.json()["nights"][0]
    assert first["verdict"] == "no"
    assert first["reason"]["code"] == "rain"
    assert first["reason"]["start"] == "02:00"
    assert first["reason"]["end"] == "03:00"
    stored = await client.get(f"/api/locations/{location_id}/imaging-rules")
    assert stored.json()["saved"] is False


async def test_forecast_imaging_until_control(client: AsyncClient):
    location_id = await _location(client)
    baseline = await _forecast(client, {"location_id": location_id})
    first_date = baseline.json()["nights"][0]["date"]
    cap = "2026-10-17T21:30:00-07:00"
    response = await _forecast(
        client,
        {
            "location_id": location_id,
            "night_controls": {first_date: {"imaging_until": cap}},
        },
    )
    assert response.status_code == 200, response.text
    first = response.json()["nights"][0]
    assert first["verdict"] == "no"
    assert first["reason"]["code"] == "no_window"
    assert first["evaluated_end"] == "21:30"
    assert first["evaluated_end_utc"] == "2026-10-18T04:30:00Z"
    assert first["controls"]["imaging_until"] == "2026-10-18T04:30:00Z"
    assert first["hours"][-1]["time"] > "2026-10-17T21:30"
    assert response.json()["nights"][1] == baseline.json()["nights"][1]

    naive = await _forecast(
        client,
        {
            "location_id": location_id,
            "night_controls": {first_date: {"imaging_until": "2026-10-17T21:30"}},
        },
    )
    assert naive.status_code == 422

    outside = await _forecast(
        client,
        {
            "location_id": location_id,
            "night_controls": {first_date: {"imaging_until": "2026-10-18T13:00:00-07:00"}},
        },
    )
    assert outside.status_code == 422


async def test_gear_control_keeps_natural_hour_range(client: AsyncClient):
    location_id = await _location(client)
    rules = PRESETS["left_out_all_night"][1].model_dump()
    baseline = await _forecast(client, {"location_id": location_id, "rules": rules})
    response = await _forecast(
        client,
        {
            "location_id": location_id,
            "rules": rules,
            "night_controls": {"2026-10-17": {"gear_out": "2026-10-17T23:00:00-07:00"}},
        },
    )

    assert baseline.status_code == 200, baseline.text
    assert response.status_code == 200, response.text
    baseline_hours = baseline.json()["nights"][0]["hours"]
    hours = response.json()["nights"][0]["hours"]
    assert hours[0]["start_utc"] == baseline_hours[0]["start_utc"]

    gear_out_utc = datetime(2026, 10, 18, 6, tzinfo=UTC)
    context_hours = [
        hour for hour in hours if datetime.fromisoformat(hour["start_utc"]) < gear_out_utc
    ]
    assert context_hours
    assert all(hour["exposure_minutes"] == 0 for hour in context_hours)
    assert all(
        set(hour["conditions"]) == {"cloud", "rain", "wind", "dew", "moon"}
        for hour in context_hours
    )


async def test_controls_validation_422(client: AsyncClient):
    location_id = await _location(client)
    rules = PRESETS["left_out_all_night"][1].model_dump()
    requests = [
        # A timestamp outside the selected date's noon-to-noon night.
        {"gear_out": "2026-10-17T11:59:00-07:00"},
        # Effective gear-out must precede effective gear-in.
        {
            "gear_out": "2026-10-17T23:00:00-07:00",
            "gear_in": "2026-10-17T22:00:00-07:00",
        },
        # Effective imaging start must precede effective imaging stop.
        {
            "imaging_from": "2026-10-18T01:00:00-07:00",
            "imaging_until": "2026-10-18T00:00:00-07:00",
        },
        # Under night_off, an imaging bound must remain inside exposure.
        {
            "gear_out": "2026-10-17T18:00:00-07:00",
            "gear_in": "2026-10-18T06:00:00-07:00",
            "imaging_from": "2026-10-17T17:00:00-07:00",
        },
    ]
    for controls in requests:
        response = await _forecast(
            client,
            {
                "location_id": location_id,
                "rules": rules,
                "night_controls": {"2026-10-17": controls},
            },
        )
        assert response.status_code == 422, response.text


async def test_inapplicable_controls_ignored_and_reported(client: AsyncClient):
    location_id = await _location(client)
    controls = {
        # Gear controls are intentionally invalid for the date and relative order.
        # They must be ignored when a draft changes the policy to hours_lost.
        "gear_out": "2026-10-18T13:00:00-07:00",
        "gear_in": "2026-10-17T11:00:00-07:00",
        "imaging_until": "2026-10-17T23:30:00-07:00",
    }
    response = await _forecast(
        client,
        {
            "location_id": location_id,
            "rules": PRESETS["attended_session"][1].model_dump(),
            "night_controls": {"2026-10-17": controls},
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["ignored_controls"] == ["2026-10-17"]
    echoed = response.json()["nights"][0]["controls"]
    assert echoed["gear_out"] is None
    assert echoed["gear_in"] is None
    assert echoed["imaging_until"] == "2026-10-18T06:30:00Z"


async def test_forecast_ignores_expired_override(client: AsyncClient):
    location_id = await _location(client)
    response = await _forecast(
        client,
        {
            "location_id": location_id,
            "night_controls": {"2026-10-16": {"imaging_until": "2026-10-16T22:00:00-07:00"}},
        },
    )
    assert response.status_code == 200
    assert response.json()["ignored_controls"] == ["2026-10-16"]


async def test_forecast_override_survives_darkness_change(client: AsyncClient):
    location_id = await _location(client, longitude=-122.0)
    cap = "2026-10-17T19:45:00-07:00"
    nautical = PRESETS["attended_session"][1].model_copy(update={"darkness": "nautical"})
    astronomical = nautical.model_copy(update={"darkness": "astronomical"})
    for rules, expected_reason in (
        (nautical, "no_window"),
        (astronomical, "no_dark_time"),
    ):
        response = await _forecast(
            client,
            {
                "location_id": location_id,
                "rules": rules.model_dump(),
                "night_controls": {"2026-10-17": {"imaging_until": cap}},
            },
        )
        assert response.status_code == 200, response.text
        first = response.json()["nights"][0]
        assert first["evaluated_end"] == "19:45"
        assert first["reason"]["code"] == expected_reason
        assert response.json()["ignored_controls"] == []


async def test_forecast_models_disagree_and_stale(client: AsyncClient):
    location_id = await _location(client)
    times = [row.time_utc for row in _weather().hourly]
    models = CloudModelData(
        models={
            "ecmwf_ifs025": _model_series({time: (0.0, 0.0, 0.0, 0.0) for time in times}),
            "gfs_seamless": _model_series({time: (100.0, 100.0, 0.0, 0.0) for time in times}),
        },
        raw_json="{}",
    )
    rules = PRESETS["attended_session"][1].model_copy(
        update={"cloud_use_icon": False, "cloud_combination": "uncertain"}
    )
    disagreement = await _forecast(
        client,
        {"location_id": location_id, "rules": rules.model_dump()},
        _data(cloud_models=models),
    )
    first = disagreement.json()["nights"][0]
    assert first["verdict"] == "uncertain"
    assert first["reason"]["code"] == "no_shared_window"
    assert first["model_statuses"]["ecmwf_ifs025"] == "go"
    assert first["model_statuses"]["gfs_seamless"] == "no"

    stale = await _forecast(
        client,
        {"location_id": location_id},
        _data(forecast_stale_minutes=540),
    )
    first = stale.json()["nights"][0]
    assert first["stale_minutes"] == 540
    assert first["verdict"] == "not_enough_data"
    assert first["reason"]["code"] == "stale"


async def test_stale_cloud_affects_declared_ecmwf_nights(client: AsyncClient):
    location_id = await _location(client)
    weather = _weather()
    cutoff = datetime(2026, 10, 21, tzinfo=UTC)
    ecmwf_times = [row.time_utc for row in weather.hourly if row.time_utc < cutoff]
    models = CloudModelData(
        models={
            "ecmwf_ifs025": _model_series({time: (0.0, 0.0, 0.0, 0.0) for time in ecmwf_times})
        },
        raw_json="{}",
    )
    response = await _forecast(
        client,
        {"location_id": location_id},
        _data(weather=weather, cloud_models=models, cloud_stale_minutes=540),
    )
    assert response.status_code == 200, response.text
    nights = response.json()["nights"]
    assert nights[0]["cloud_source"] == "ecmwf"
    assert nights[0]["stale_minutes"] == 540
    assert nights[0]["verdict"] != "go"
    assert nights[4]["cloud_source"] == "ecmwf"
    assert nights[4]["stale_minutes"] == 540
    assert nights[4]["verdict"] == "not_enough_data"


async def test_primary_model_ignores_elapsed_gaps(client: AsyncClient):
    location_id = await _location(client)
    missing = datetime(2026, 10, 18, 2, tzinfo=UTC)  # 19:00 PDT
    model_times = [row.time_utc for row in _weather().hourly if row.time_utc != missing]
    models = CloudModelData(
        models={
            "ecmwf_ifs025": _model_series({time: (0.0, 0.0, 0.0, 0.0) for time in model_times}),
        },
        raw_json="{}",
    )
    now = datetime(2026, 10, 18, 6, tzinfo=UTC)  # 23:00 PDT

    with (
        patch("nightcrate.api.weather._now", return_value=now),
        patch(
            "nightcrate.api.weather._load_forecast_data",
            new=AsyncMock(return_value=_data(cloud_models=models)),
        ),
    ):
        response = await client.post("/api/weather/forecast", json={"location_id": location_id})

    assert response.status_code == 200, response.text
    assert response.json()["nights"][0]["cloud_source"] == "ecmwf"


async def test_primary_model_ignores_post_cap_gaps(client: AsyncClient):
    location_id = await _location(client)
    cutoff = datetime(2026, 10, 18, 8, tzinfo=UTC)  # 01:00 PDT
    model_times = [row.time_utc for row in _weather().hourly if row.time_utc < cutoff]
    models = CloudModelData(
        models={
            "ecmwf_ifs025": _model_series({time: (0.0, 0.0, 0.0, 0.0) for time in model_times}),
        },
        raw_json="{}",
    )

    response = await _forecast(
        client,
        {
            "location_id": location_id,
            "night_controls": {"2026-10-17": {"imaging_until": "2026-10-18T00:30:00-07:00"}},
        },
        _data(cloud_models=models),
    )

    assert response.status_code == 200, response.text
    assert response.json()["nights"][0]["cloud_source"] == "ecmwf"


@pytest.mark.parametrize(
    ("rain_policy", "expected"),
    [
        # Gear-out interval: the twilight shower at 00:00 counts.
        ("night_off", (40.0, "00:00", 0.7, "00:00")),
        # Dark hours only: the twilight shower is ignored.
        ("hours_lost", (10.0, "01:00", 0.2, "01:00")),
    ],
)
def test_rain_extremes_follow_rain_policy(rain_policy, expected):
    """The night-detail rain figures cover the hours the rain verdict judges."""
    from nightcrate.api.weather import _extremes
    from nightcrate.services.imaging_types import (
        HourInput,
        HourResult,
        ModelHour,
    )

    start = datetime(2026, 10, 18, 0, tzinfo=UTC)
    # (rain chance %, rain mm, dark minutes): twilight, then two dark hours.
    hours = [(40.0, 0.5, 0.0), (10.0, 0.0, 60.0), (5.0, 0.2, 60.0)]
    inputs = []
    results = []
    for offset, (probability, amount, dark_minutes) in enumerate(hours):
        hour_start = start + timedelta(hours=offset)
        inputs.append(
            HourInput(
                start_utc=hour_start,
                models={"ecmwf_ifs025": ModelHour(0.0, (0.0, 0.0, 0.0), amount, True, True)},
                precip_probability_pct=probability,
                precip_mm=amount,
                wind_kmh=5.0,
                gust_kmh=8.0,
                temperature_c=10.0,
                dew_point_c=2.0,
                moon_altitude_deg=-10.0,
            )
        )
        results.append(
            HourResult(
                start_utc=hour_start,
                elapsed=False,
                # This twilight hour is outside a narrower imaging interval,
                # but still inside exposure under night_off.
                excluded=dark_minutes == 0,
                dark_minutes=dark_minutes,
                exposure_minutes=60.0,
                checks={},
                conditions={},
                state="clear" if dark_minutes else "outside",
                session_state="clear" if dark_minutes else "outside",
                model_states={},
                disagrees=False,
                cloud_pct={},
                expected={},
                dew_spread_c=8.0,
            )
        )

    extremes = _extremes(inputs, results, rain_policy, ZoneInfo("UTC"))

    probability, at, total, sum_start = expected
    assert extremes.max_precip_probability_pct == probability
    assert extremes.max_precip_probability_at == at
    assert extremes.precip_mm_total == pytest.approx(total)
    assert extremes.precip_missing_hours == 0
    assert extremes.precip_sum_start == sum_start
    assert extremes.precip_sum_end == "03:00"


def _extreme_amount_rows(amounts: list[float | None]):
    from nightcrate.services.imaging_types import (
        HourInput,
        HourResult,
        ModelHour,
    )

    start = datetime(2026, 10, 18, tzinfo=UTC)
    inputs = []
    results = []
    for offset, amount in enumerate(amounts):
        hour_start = start + timedelta(hours=offset)
        inputs.append(
            HourInput(
                start_utc=hour_start,
                models={"ecmwf_ifs025": ModelHour(0.0, (0.0, 0.0, 0.0), amount, True, True)},
                precip_probability_pct=0.0,
                precip_mm=amount,
                wind_kmh=5.0,
                gust_kmh=8.0,
                temperature_c=10.0,
                dew_point_c=2.0,
                moon_altitude_deg=-10.0,
            )
        )
        results.append(
            HourResult(
                start_utc=hour_start,
                elapsed=False,
                excluded=False,
                dark_minutes=60.0,
                exposure_minutes=60.0,
                checks={},
                conditions={},
                state="clear",
                session_state="clear",
                model_states={},
                disagrees=False,
                cloud_pct={},
                expected={},
                dew_spread_c=8.0,
            )
        )
    return inputs, results


def test_totals_incomplete():
    from nightcrate.api.weather import _extremes

    inputs, results = _extreme_amount_rows([0.1, None, 0.2, None])
    extremes = _extremes(inputs, results, "hours_lost", ZoneInfo("UTC"))

    assert extremes.precip_mm_total == pytest.approx(0.3)
    assert extremes.precip_missing_hours == 2
    assert extremes.precip_sum_start == "00:00"
    assert extremes.precip_sum_end == "04:00"
    assert extremes.precip_sum_start_utc == datetime(2026, 10, 18, tzinfo=UTC)
    assert extremes.precip_sum_end_utc == datetime(2026, 10, 18, 4, tzinfo=UTC)


def test_trace_amount_not_zero_in_extremes():
    from nightcrate.api.weather import _extremes

    inputs, results = _extreme_amount_rows([0.05])
    extremes = _extremes(inputs, results, "hours_lost", ZoneInfo("UTC"))

    assert extremes.precip_mm_total == pytest.approx(0.05)


def test_reason_response_carries_structured_evidence_and_utc():
    from nightcrate.api.weather import _reason_response
    from nightcrate.services.imaging_types import Reason

    start = datetime(2026, 10, 18, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    response = _reason_response(
        Reason(
            code="rain",
            start_utc=start,
            end_utc=end,
            model="icon_seamless",
            models={"icon_seamless": "unresolved"},
            missing_hours=2.0,
        ),
        ZoneInfo("America/Los_Angeles"),
    )

    assert response.start == "18:00"
    assert response.end == "20:00"
    assert response.start_utc == start
    assert response.end_utc == end
    assert response.model == "icon_seamless"
    assert response.models == {"icon_seamless": "unresolved"}
    assert response.missing_hours == 2.0
    assert "period" not in response.model_dump()


async def test_forecast_stale_after_failed_fetch(client: AsyncClient, monkeypatch):
    location_id = await _location(client)
    await _seed_real_cache(location_id)
    monkeypatch.setattr(
        "nightcrate.api.weather._fetch_or_cached_cloud_models",
        REAL_FETCH_OR_CACHED_CLOUD_MODELS,
    )
    weather_fetch = AsyncMock(side_effect=RuntimeError("offline"))
    cloud_fetch = AsyncMock(side_effect=RuntimeError("offline"))

    with (
        patch("nightcrate.api.weather._now", return_value=NOW),
        patch("nightcrate.api.weather.fetch_weather", new=weather_fetch),
        patch("nightcrate.api.weather.fetch_cloud_models", new=cloud_fetch),
    ):
        fresh = await client.post("/api/weather/forecast", json={"location_id": location_id})
        assert fresh.status_code == 200, fresh.text
        assert fresh.json()["nights"][0]["verdict"] == "go"
        weather_fetch.assert_not_awaited()
        cloud_fetch.assert_not_awaited()

        await _write_cache(
            location_id,
            "forecast",
            _weather_json(),
            NOW - timedelta(hours=9),
        )
        stale = await client.post("/api/weather/forecast", json={"location_id": location_id})

    assert stale.status_code == 200, stale.text
    assert stale.json()["stale_sources"]["forecast"] in range(538, 543)
    first = stale.json()["nights"][0]
    assert first["verdict"] == "not_enough_data"
    assert first["reason"]["code"] == "stale"
    weather_fetch.assert_awaited_once()
    cloud_fetch.assert_not_awaited()


async def test_forecast_stale_cloud_row_only(client: AsyncClient, monkeypatch):
    location_id = await _location(client)
    await _seed_real_cache(
        location_id,
        cloud_age=timedelta(hours=9),
        cloud_json=_cloud_json(before=datetime(2026, 10, 21, tzinfo=UTC)),
    )
    monkeypatch.setattr(
        "nightcrate.api.weather._fetch_or_cached_cloud_models",
        REAL_FETCH_OR_CACHED_CLOUD_MODELS,
    )
    weather_fetch = AsyncMock(side_effect=RuntimeError("offline"))
    cloud_fetch = AsyncMock(side_effect=RuntimeError("offline"))

    with (
        patch("nightcrate.api.weather._now", return_value=NOW),
        patch("nightcrate.api.weather.fetch_weather", new=weather_fetch),
        patch("nightcrate.api.weather.fetch_cloud_models", new=cloud_fetch),
    ):
        response = await client.post("/api/weather/forecast", json={"location_id": location_id})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["stale_sources"]["cloud_models"] in range(538, 543)
    for night in data["nights"][:3]:
        assert night["stale_minutes"] in range(538, 543)
        assert night["verdict"] != "go"
    assert data["nights"][4]["cloud_source"] == "ecmwf"
    assert data["nights"][4]["stale_minutes"] in range(538, 543)
    assert data["nights"][4]["verdict"] == "not_enough_data"
    weather_fetch.assert_not_awaited()
    cloud_fetch.assert_awaited_once()


async def test_fetch_or_cached_fresh_hit_does_not_fetch(client: AsyncClient, monkeypatch):
    location_id = await _location(client)
    await _seed_real_cache(location_id)
    monkeypatch.setattr(
        "nightcrate.api.weather._fetch_or_cached_cloud_models",
        REAL_FETCH_OR_CACHED_CLOUD_MODELS,
    )
    weather_fetch = AsyncMock(side_effect=RuntimeError("must not fetch"))
    cloud_fetch = AsyncMock(side_effect=RuntimeError("must not fetch"))

    with (
        patch("nightcrate.api.weather._now", return_value=NOW),
        patch("nightcrate.api.weather.fetch_weather", new=weather_fetch),
        patch("nightcrate.api.weather.fetch_cloud_models", new=cloud_fetch),
    ):
        response = await client.post("/api/weather/forecast", json={"location_id": location_id})

    assert response.status_code == 200, response.text
    weather_fetch.assert_not_awaited()
    cloud_fetch.assert_not_awaited()


async def test_fresh_cache_short_of_horizon_is_refetched(client: AsyncClient, monkeypatch):
    """A row from the old 8-day horizon is within its TTL but must not be served."""
    location_id = await _location(client)
    short = NOW + timedelta(days=8)
    await _seed_real_cache(
        location_id,
        weather_json=_weather_json(before=short),
        cloud_json=_cloud_json(before=short),
    )
    monkeypatch.setattr(
        "nightcrate.api.weather._fetch_or_cached_cloud_models",
        REAL_FETCH_OR_CACHED_CLOUD_MODELS,
    )
    weather_fetch = AsyncMock(side_effect=RuntimeError("offline"))
    cloud_fetch = AsyncMock(side_effect=RuntimeError("offline"))

    with (
        patch("nightcrate.api.weather._now", return_value=NOW),
        patch("nightcrate.api.weather.fetch_weather", new=weather_fetch),
        patch("nightcrate.api.weather.fetch_cloud_models", new=cloud_fetch),
    ):
        response = await client.post("/api/weather/forecast", json={"location_id": location_id})

    # Both sources tried a repair; the within-TTL rows remain current while
    # the nights past their end have no data.
    assert response.status_code == 200, response.text
    weather_fetch.assert_awaited_once()
    cloud_fetch.assert_awaited_once()
    nights = response.json()["nights"]
    assert len(nights) == 14
    assert response.json()["stale_sources"] == {"forecast": None, "cloud_models": None}
    assert nights[0]["stale_minutes"] is None
    assert nights[-1]["verdict"] == "not_enough_data"


async def test_forecast_null_context_inputs(client: AsyncClient):
    location_id = await _location(client)
    null_time = datetime(2026, 10, 18, 5, tzinfo=UTC)  # 22:00 PDT
    rules = PRESETS["dome"][1].model_dump()
    response = await _forecast(
        client,
        {"location_id": location_id, "rules": rules},
        _data(weather=_weather(null_at=null_time)),
    )
    assert response.status_code == 200, response.text
    hour = next(
        item for item in response.json()["nights"][0]["hours"] if item["time"].endswith("T22:00")
    )
    assert hour["seeing"] is None
    assert hour["transparency"] is None
    assert hour["transparency_tier"] is None
    assert hour["wind_kmh"] is None
    assert hour["checks"]["wind"] == "not_counted"


async def test_forecast_anchor_noon_transition(client: AsyncClient):
    location_id = await _location(client)
    before = NOW - timedelta(minutes=1)
    after = NOW + timedelta(minutes=1)
    with (
        patch("nightcrate.api.weather._now", return_value=before),
        patch("nightcrate.api.weather._load_forecast_data", new=AsyncMock(return_value=_data())),
    ):
        first = await client.post("/api/weather/forecast", json={"location_id": location_id})
    with (
        patch("nightcrate.api.weather._now", return_value=after),
        patch("nightcrate.api.weather._load_forecast_data", new=AsyncMock(return_value=_data())),
    ):
        second = await client.post("/api/weather/forecast", json={"location_id": location_id})
    assert first.json()["nights"][0]["date"] == "2026-10-16"
    assert second.json()["nights"][0]["date"] == "2026-10-17"


async def test_forecast_night_under_way_stays_listed(client: AsyncClient):
    location_id = await _location(client)
    under_way = datetime(2026, 10, 18, 8, tzinfo=UTC)  # 01:00 PDT
    with (
        patch("nightcrate.api.weather._now", return_value=under_way),
        patch(
            "nightcrate.api.weather._load_forecast_data",
            new=AsyncMock(return_value=_data()),
        ),
    ):
        response = await client.post("/api/weather/forecast", json={"location_id": location_id})
    assert response.status_code == 200, response.text
    first = response.json()["nights"][0]
    assert first["date"] == "2026-10-17"
    assert first["evaluated_from"] == "01:00"
    assert first["evaluated_from_utc"] == "2026-10-18T08:00:00Z"
    at_19 = next(hour for hour in first["hours"] if hour["time"].endswith("T19:00"))
    assert at_19["elapsed"] is True


async def test_forecast_display_timezone_differs_from_site(client: AsyncClient):
    location_id = await _location(
        client,
        timezone="America/New_York",
        geo_timezone="America/Los_Angeles",
    )
    response = await _forecast(client, {"location_id": location_id})
    assert response.status_code == 200, response.text
    first = response.json()["nights"][0]
    for hour in first["hours"]:
        utc = datetime.fromisoformat(hour["start_utc"])
        expected = utc.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%dT%H:%M")
        assert hour["time"] == expected
    summary = compute_night_summary(
        34.05,
        -118.25,
        300,
        date.fromisoformat(first["date"]),
        "America/Los_Angeles",
    )
    assert summary.moon.moonset_utc is not None
    assert first["moonset"] == summary.moon.moonset_utc.astimezone(
        ZoneInfo("America/New_York")
    ).strftime("%H:%M")


@pytest.mark.parametrize(
    ("timezone", "suffix"),
    [("Asia/Kolkata", ":30"), ("Asia/Kathmandu", ":45")],
)
async def test_fractional_offset_alignment(
    client: AsyncClient,
    timezone: str,
    suffix: str,
):
    location_id = await _location(client, timezone=timezone)
    response = await _forecast(client, {"location_id": location_id})

    assert response.status_code == 200, response.text
    night = response.json()["nights"][1]
    assert night["hours"]
    assert all(hour["time"].endswith(suffix) for hour in night["hours"])
    assert all(datetime.fromisoformat(hour["start_utc"]).minute == 0 for hour in night["hours"])
    interval_hours = sum(
        (
            datetime.fromisoformat(interval["end_utc"])
            - datetime.fromisoformat(interval["start_utc"])
        ).total_seconds()
        / 3600
        for interval in night["dark_intervals"]
    )
    assert night["dark_hours"] == pytest.approx(interval_hours, abs=0.02)


async def test_fractional_dst_night(client: AsyncClient):
    timezone = "Australia/Lord_Howe"
    now = datetime(2026, 10, 3, 2, tzinfo=UTC)
    location_id = await _location(
        client,
        latitude=-31.55,
        longitude=159.08,
        timezone=timezone,
    )
    weather = _weather(start=datetime(2026, 10, 2, tzinfo=UTC), hours=17 * 24)
    response = await _forecast(
        client,
        {"location_id": location_id},
        _data(weather=weather, fetched_at=now),
        now=now,
    )

    assert response.status_code == 200, response.text
    night = response.json()["nights"][0]
    starts = [datetime.fromisoformat(hour["start_utc"]) for hour in night["hours"]]
    assert len(starts) == len(set(starts))
    assert all(later - earlier == timedelta(hours=1) for earlier, later in zip(starts, starts[1:]))
    interval_hours = sum(
        (
            datetime.fromisoformat(interval["end_utc"])
            - datetime.fromisoformat(interval["start_utc"])
        ).total_seconds()
        / 3600
        for interval in night["dark_intervals"]
    )
    assert night["dark_hours"] == pytest.approx(interval_hours, abs=0.02)


@pytest.mark.parametrize(
    ("night_date", "expected_hours"),
    [(date(2026, 3, 7), 23), (date(2026, 10, 31), 25)],
)
def test_dst_23_and_25_hour_nights(night_date: date, expected_hours: int):
    from nightcrate.api.weather import _night_bounds

    start, end = _night_bounds(night_date, ZoneInfo("America/New_York"))

    assert (end - start).total_seconds() / 3600 == expected_hours


async def test_forecast_dst_fallback_legacy_cache_labels_repeat(client: AsyncClient):
    location_id = await _location(
        client,
        latitude=40.71,
        longitude=-74.0,
        timezone="America/New_York",
    )
    times = [f"2026-11-{day:02d}T{hour:02d}:00" for day in range(1, 9) for hour in range(24)]
    raw = {
        "time": times,
        "temperature_2m": [10.0] * len(times),
        "dew_point_2m": [4.0] * len(times),
        "relative_humidity_2m": [50.0] * len(times),
        "cloud_cover": [0.0] * len(times),
        "cloud_cover_low": [0.0] * len(times),
        "cloud_cover_mid": [0.0] * len(times),
        "cloud_cover_high": [0.0] * len(times),
        "wind_speed_10m": [5.0] * len(times),
        "wind_direction_10m": [180.0] * len(times),
        "wind_gusts_10m": [10.0] * len(times),
        "visibility": [20000.0] * len(times),
        "precipitation": [0.0] * len(times),
        "precipitation_probability": [0.0] * len(times),
    }
    weather = WeatherData(
        40.71,
        -74.0,
        "forecast",
        parse_hourly(raw, "forecast", -14400),
        "{}",
    )
    now = datetime(2026, 10, 31, 19, tzinfo=UTC)
    with (
        patch("nightcrate.api.weather._now", return_value=now),
        patch(
            "nightcrate.api.weather._load_forecast_data",
            new=AsyncMock(return_value=_data(weather=weather)),
        ),
    ):
        response = await client.post("/api/weather/forecast", json={"location_id": location_id})
    assert response.status_code == 200, response.text
    hours = response.json()["nights"][0]["hours"]
    starts = [datetime.fromisoformat(hour["start_utc"]) for hour in hours]
    assert all(later - earlier == timedelta(hours=1) for earlier, later in zip(starts, starts[1:]))
    labels = [hour["time"] for hour in hours]
    assert labels.count("2026-11-01T01:00") == 2


@pytest.mark.parametrize(
    ("latitude", "longitude", "timezone", "now", "expected"),
    [
        (78.0, 0.0, "UTC", datetime(2026, 6, 21, 12, tzinfo=UTC), "summer"),
        (89.0, 0.0, "UTC", datetime(2026, 12, 21, 12, tzinfo=UTC), "night"),
        (
            69.65,
            18.96,
            "Europe/Oslo",
            datetime(2026, 12, 21, 11, tzinfo=UTC),
            "twilight",
        ),
        (
            -33.45,
            -70.66,
            "America/Santiago",
            datetime(2026, 6, 21, 16, tzinfo=UTC),
            "southern",
        ),
    ],
)
async def test_forecast_extreme_latitude_and_southern_cases(
    client: AsyncClient,
    latitude: float,
    longitude: float,
    timezone: str,
    now: datetime,
    expected: str,
):
    location_id = await _location(
        client,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
    )
    weather = _weather(start=now.replace(hour=0) - timedelta(days=1))
    with (
        patch("nightcrate.api.weather._now", return_value=now),
        patch(
            "nightcrate.api.weather._load_forecast_data",
            new=AsyncMock(return_value=_data(weather=weather)),
        ),
    ):
        response = await client.post("/api/weather/forecast", json={"location_id": location_id})
    assert response.status_code == 200, response.text
    first = response.json()["nights"][0]
    if expected == "summer":
        assert first["verdict"] == "no"
        assert first["reason"]["code"] == "never_dark"
        assert first["hours"]
    elif expected == "night":
        assert first["dark_hours"] == 24
        assert first["reason"]["code"] != "never_dark"
    elif expected == "twilight":
        assert first["dark_hours"] == pytest.approx(13.55, abs=0.1)
        assert first["sunset"] is None
        assert first["gear_out_start"] == "12:00"
        assert first["gear_out_end"] == "12:00"
    else:
        assert first["dark_hours"] > 9


async def test_forecast_503_when_nothing_cached(client: AsyncClient):
    location_id = await _location(client)
    unavailable = HTTPException(
        status_code=503,
        detail="Forecast unavailable — Open-Meteo could not be reached and nothing is cached",
    )
    with (
        patch("nightcrate.api.weather._now", return_value=NOW),
        patch(
            "nightcrate.api.weather._load_forecast_data",
            new=AsyncMock(side_effect=unavailable),
        ),
    ):
        response = await client.post("/api/weather/forecast", json={"location_id": location_id})
    assert response.status_code == 503


async def test_methodology_uses_plain_final_copy(client: AsyncClient):
    response = await client.get("/api/weather/methodology")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "summary": METHODOLOGY_SUMMARY,
        "details": METHODOLOGY_DETAILS,
    }
    assert all(
        keyword in payload["summary"]
        for keyword in ("Usable time", "Go", "Uncertain", "Not enough data", "majority")
    )
    banned = (
        "period",
        "coverage",
        "declared",
        "unresolved",
        "pessimistic",
        "primary",
        "comparison",
        "fallback",
        "interval",
        "veto",
        "regime",
    )
    for text in payload.values():
        assert not any(re.search(rf"\b{word}\b", text, re.IGNORECASE) for word in banned)
