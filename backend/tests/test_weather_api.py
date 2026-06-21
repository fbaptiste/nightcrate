"""Tests for the weather API endpoints."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

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


@pytest.mark.anyio
async def test_hourly_moon_aligned_by_utc_across_timezones(client):
    """Astro is joined to weather by absolute UTC, not a wall-clock string.

    A remote-observatory location whose display ``timezone`` differs from its
    ``geo_timezone`` must still get correctly aligned per-hour moon/darkness
    data. Before the fix the join matched ``"HH:MM"`` strings labelled in two
    different zones, so the moon columns were silently shifted by the offset.
    """
    from nightcrate.services.astronomy import compute_hourly_astro

    # Tokyo coordinates, but the user displays times in Los Angeles.
    lat, lon, elev = 35.6762, 139.6503, 40.0
    display_tz = "America/Los_Angeles"
    geo_tz = "Asia/Tokyo"
    resp = await client.post(
        "/api/locations",
        json={
            "name": "Remote Rig",
            "latitude": lat,
            "longitude": lon,
            "elevation_m": elev,
            "timezone": display_tz,
            "geo_timezone": geo_tz,
        },
    )
    assert resp.status_code == 201
    loc_id = resp.json()["id"]
    assert resp.json()["geo_timezone"] == geo_tz

    # Expected astro, indexed by absolute UTC instant (what the endpoint joins on).
    astro = compute_hourly_astro(
        latitude=lat,
        longitude=lon,
        elevation_m=elev,
        night_date=date(2026, 4, 13),
        timezone_str=geo_tz,
    )
    assert astro  # the night must resolve for the assertion to mean anything
    astro_sorted = sorted(astro, key=lambda a: a.time_utc)

    def nearest(utc_dt):
        best, best_gap = None, timedelta(minutes=31)
        for a in astro_sorted:
            gap = abs(a.time_utc - utc_dt)
            if gap < best_gap:
                best, best_gap = a, gap
        return best

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
    ):
        resp = await client.get(
            "/api/weather/hourly",
            params={"location_id": loc_id, "date": "2026-04-13"},
        )

    assert resp.status_code == 200
    hours = resp.json()["hours"]
    assert hours

    display = ZoneInfo(display_tz)
    checked = 0
    for hour in hours:
        if hour["moon_altitude_deg"] is None:
            continue
        # Weather time is naive local in the display tz; resolve to UTC.
        utc_dt = datetime.fromisoformat(hour["time"]).replace(tzinfo=display).astimezone(UTC)
        expected = nearest(utc_dt)
        assert expected is not None, f"no astro within 31 min of {utc_dt}"
        assert hour["moon_altitude_deg"] == pytest.approx(expected.moon_altitude_deg, abs=0.01)
        assert hour["darkness_category"] == expected.darkness_category
        checked += 1
    assert checked > 0


# ---------------------------------------------------------------------------
# Invalid date format on /hourly
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_hourly_invalid_date_format(client):
    """Calling /hourly with a non-date string should return 422."""
    loc_id = await _create_test_location(client)
    resp = await client.get(
        "/api/weather/hourly",
        params={"location_id": loc_id, "date": "not-a-date"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Missing required params on /forecast
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_forecast_missing_location_id(client):
    """Calling /forecast without location_id should return 422 (FastAPI validation)."""
    resp = await client.get("/api/weather/forecast")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Strict response schema validation on /forecast
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_forecast_strict_schema_validation(client):
    """Validate types, ranges, and enum values in the forecast response."""
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

    # Top-level fields
    assert isinstance(data["location_id"], int)
    assert isinstance(data["location_name"], str)
    assert isinstance(data["latitude"], float)
    assert isinstance(data["longitude"], float)
    assert isinstance(data["timezone"], str)
    assert isinstance(data["moon_included"], bool)
    assert isinstance(data["days"], list)

    for day in data["days"]:
        # Integer scores in valid ranges
        assert isinstance(day["imaging_quality"], int)
        assert 0 <= day["imaging_quality"] <= 100

        assert isinstance(day["sky_clarity"], int)
        assert 0 <= day["sky_clarity"] <= 100

        assert isinstance(day["transparency_score"], int)
        assert 0 <= day["transparency_score"] <= 100

        assert isinstance(day["seeing_score"], int)
        assert 0 <= day["seeing_score"] <= 100

        assert isinstance(day["wind_calm"], int)
        assert 0 <= day["wind_calm"] <= 100

        assert isinstance(day["moon_score"], int)
        assert 0 <= day["moon_score"] <= 100

        # Quality label must be one of the defined labels
        assert day["imaging_quality_label"] in ("Excellent", "Good", "Marginal", "Poor")

        # Deepest darkness reached must be one of the defined values
        assert day["deepest_darkness_reached"] in ("astro", "nautical", "civil", "none")

        # Float fields
        assert isinstance(day["darkness_hours"], (int, float))
        assert day["darkness_hours"] >= 0

        assert isinstance(day["moonless_dark_hours"], (int, float))
        assert day["moonless_dark_hours"] >= 0

        assert isinstance(day["moon_illumination_pct"], (int, float))
        assert 0 <= day["moon_illumination_pct"] <= 100

        assert isinstance(day["moon_phase_name"], str)

        # Boolean field
        assert isinstance(day["no_imaging_window"], bool)

        # Dew safe window structure
        dew = day["dew_safe_window"]
        assert dew["label"] in ("all_night", "until", "after", "none")

        # Cloud/temp/precip fields
        assert isinstance(day["avg_cloud_cover_pct"], (int, float))
        assert 0 <= day["avg_cloud_cover_pct"] <= 100
        assert isinstance(day["temp_min_c"], (int, float))
        assert isinstance(day["temp_max_c"], (int, float))
        assert isinstance(day["max_precipitation_probability_pct"], (int, float))
        assert 0 <= day["max_precipitation_probability_pct"] <= 100

        # Date format (ISO)
        assert isinstance(day["date"], str)
        assert len(day["date"]) == 10  # YYYY-MM-DD


# ---------------------------------------------------------------------------
# Methodology text validation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_methodology_text_current_weights(client):
    """Verify methodology text reflects current factors and weights."""
    resp = await client.get("/api/weather/methodology")
    assert resp.status_code == 200
    text = resp.json()["text"]

    # Current factors and weights must be present
    assert "Transparency" in text
    assert "35%" in text
    assert "Sky Clarity" in text
    assert "25%" in text  # Seeing weight

    # Old factors/weights must NOT be present
    assert "Dryness" not in text
    # Note: "40%" IS present in the "No Moon" column (Sky Clarity = 40% when
    # moon excluded) — that's the current design, not a stale weight.
    assert "| 40%" in text  # No-Moon column for Sky Clarity


# ---------------------------------------------------------------------------
# Polar location tests — Tromsø (69.65°N)
# ---------------------------------------------------------------------------


def _make_fake_weather_polar(n_hours: int = 168) -> WeatherData:
    """Build fake WeatherData for a polar location spanning 7 days.

    Uses June dates (summer) when Tromsø has midnight sun — no sunset.
    """
    hours = []
    for i in range(n_hours):
        day = 21 + i // 24
        hour = i % 24
        hours.append(
            HourlyWeather(
                time=f"2026-06-{day:02d}T{hour:02d}:00",
                temperature_c=10.0 + i * 0.02,
                dew_point_c=4.0,
                humidity_pct=70.0,
                cloud_cover_pct=30.0,
                cloud_cover_low_pct=15.0,
                cloud_cover_mid_pct=10.0,
                cloud_cover_high_pct=5.0,
                wind_speed_kmh=12.0,
                wind_direction_deg=200.0,
                wind_gusts_kmh=20.0,
                visibility_m=15000.0,
                precipitation_mm=0.0,
                precipitation_probability_pct=5.0,
                wind_speed_200hpa_kmh=45.0,
                wind_speed_300hpa_kmh=35.0,
                wind_speed_500hpa_kmh=18.0,
                geopotential_200hpa_m=11800.0,
                geopotential_300hpa_m=9200.0,
                geopotential_500hpa_m=5500.0,
            )
        )
    return WeatherData(
        latitude=69.65,
        longitude=18.96,
        source="forecast",
        hourly=hours,
        raw_json="{}",
    )


async def _create_polar_location(client: AsyncClient) -> int:
    """Create a Tromsø test location and return its ID."""
    resp = await client.post(
        "/api/locations",
        json={
            "name": "Tromsø Observatory",
            "latitude": 69.65,
            "longitude": 18.96,
            "elevation_m": 100.0,
            "timezone": "Europe/Oslo",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.anyio
async def test_polar_forecast_structure(client):
    """Forecast for Tromsø in summer should produce valid days, some with no_imaging_window.

    Mocks weather fetch but lets astronomy compute real twilight so polar
    conditions (midnight sun) are exercised. We patch datetime.now in the
    weather module to return a June date, matching our fake weather data.
    """
    loc_id = await _create_polar_location(client)
    fake_weather = _make_fake_weather_polar()
    fake_supplementary = _make_fake_supplementary()

    # The forecast endpoint calls datetime.now(tz) to determine start_date.
    # Patch it to return June 21 so our fake weather data aligns and the
    # astronomy module computes midnight-sun conditions.
    fake_now = datetime(2026, 6, 21, 14, 0, 0, tzinfo=ZoneInfo("Europe/Oslo"))

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
            params={"location_id": loc_id},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["location_id"] == loc_id
    assert data["location_name"] == "Tromsø Observatory"
    assert isinstance(data["days"], list)

    # In Arctic summer, most or all days should have no_imaging_window = True
    no_imaging_days = [d for d in data["days"] if d["no_imaging_window"]]
    assert len(no_imaging_days) > 0, "Tromsø in June should have polar day (no imaging window)"

    # Validate structure of no-imaging days
    for day in no_imaging_days:
        assert day["imaging_quality"] == 0
        assert day["imaging_quality_label"] == "Poor"
        assert day["darkness_hours"] == 0
        assert day["deepest_darkness_reached"] in ("astro", "nautical", "civil", "none")
        assert isinstance(day["no_imaging_window"], bool)
        assert isinstance(day["moon_illumination_pct"], (int, float))
        assert isinstance(day["moon_phase_name"], str)
        assert day["date"] is not None

    # All days (imaging or not) should have valid schema
    for day in data["days"]:
        assert 0 <= day["imaging_quality"] <= 100
        assert day["imaging_quality_label"] in ("Excellent", "Good", "Marginal", "Poor")
        assert day["deepest_darkness_reached"] in ("astro", "nautical", "civil", "none")


@pytest.mark.anyio
async def test_polar_hourly_summer(client):
    """Hourly for Tromsø on 2026-06-21 (midsummer) should return empty hours or valid no-imaging."""
    loc_id = await _create_polar_location(client)
    fake_weather = _make_fake_weather_polar()
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
            params={"location_id": loc_id, "date": "2026-06-21"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == "2026-06-21"
    assert data["location_id"] == loc_id

    # In midnight sun, expect no sunset → empty hours, None sunset/sunrise
    assert isinstance(data["hours"], list)
    # Moon polyline may be empty or populated depending on implementation
    assert isinstance(data["moon_polyline"], list)
    # Twilight times should all be None or valid strings
    twilight = data["twilight"]
    for key in ("civil_end", "nautical_end", "astro_start", "astro_end"):
        assert twilight[key] is None or isinstance(twilight[key], str)

    # If no sunset, hours should be empty (no imaging data to show)
    if data["sunset"] is None:
        assert len(data["hours"]) == 0


# ---------------------------------------------------------------------------
# Supplementary data fallback
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_supplementary_fallback_on_error(client):
    """If supplementary data fetch fails, forecast should still return successfully.

    PWV and AOD should fall back to empty dicts (hourly pwv_mm and aod will be None).
    """
    loc_id = await _create_test_location(client)
    fake_weather = _make_fake_weather()

    with (
        patch(
            "nightcrate.api.weather._fetch_or_cached",
            new_callable=AsyncMock,
            return_value=fake_weather,
        ),
        patch(
            "nightcrate.api.weather._fetch_or_cached_supplementary",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Supplementary API down"),
        ),
    ):
        resp = await client.get(
            "/api/weather/forecast",
            params={"location_id": loc_id},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["location_id"] == loc_id
    assert isinstance(data["days"], list)
    # Should still return valid days despite supplementary failure
    if len(data["days"]) > 0:
        day = data["days"][0]
        assert 0 <= day["imaging_quality"] <= 100
        assert day["imaging_quality_label"] in ("Excellent", "Good", "Marginal", "Poor")


# ---------------------------------------------------------------------------
# _compute_seeing surface fallback (no pressure-level data)
# ---------------------------------------------------------------------------


def _make_fake_weather_surface_only(n_hours: int = 48) -> WeatherData:
    """Build fake WeatherData with NO upper-atmosphere wind data.

    This exercises the _compute_seeing fallback to estimate_seeing_surface
    (line 291 of weather.py).
    """
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
                # No upper-atmosphere data
                wind_speed_200hpa_kmh=None,
                wind_speed_300hpa_kmh=None,
                wind_speed_500hpa_kmh=None,
                geopotential_200hpa_m=None,
                geopotential_300hpa_m=None,
                geopotential_500hpa_m=None,
            )
        )
    return WeatherData(
        latitude=34.05,
        longitude=-118.25,
        source="forecast",
        hourly=hours,
        raw_json="{}",
    )


@pytest.mark.anyio
async def test_forecast_surface_only_seeing(client):
    """Forecast with no upper-atmosphere data should still compute seeing via surface model."""
    loc_id = await _create_test_location(client)
    fake_weather = _make_fake_weather_surface_only()
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
    assert isinstance(data["days"], list)
    # Should produce valid results with surface-only seeing
    for day in data["days"]:
        assert 0 <= day["seeing_score"] <= 100
        assert 0 <= day["imaging_quality"] <= 100


@pytest.mark.anyio
async def test_hourly_surface_only_seeing(client):
    """Hourly with no upper-atmosphere data exercises surface seeing fallback."""
    loc_id = await _create_test_location(client)
    fake_weather = _make_fake_weather_surface_only()
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
    for hour in data["hours"]:
        assert 0 <= hour["seeing_score"] <= 100


# ---------------------------------------------------------------------------
# _compute_night_data exception path (astronomy failure)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_forecast_survives_astronomy_exception(client):
    """If compute_night_summary raises for one date, that date is skipped."""
    loc_id = await _create_test_location(client)
    fake_weather = _make_fake_weather()
    fake_supplementary = _make_fake_supplementary()

    call_count = 0
    original_compute = __import__(
        "nightcrate.services.astronomy", fromlist=["compute_night_summary"]
    ).compute_night_summary

    def flaky_compute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Simulated astronomy failure")
        return original_compute(*args, **kwargs)

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
        patch(
            "nightcrate.api.weather.compute_night_summary",
            side_effect=flaky_compute,
        ),
    ):
        resp = await client.get(
            "/api/weather/forecast",
            params={"location_id": loc_id},
        )

    assert resp.status_code == 200
    data = resp.json()
    # Should still return a response even though one night failed
    assert isinstance(data["days"], list)


# ---------------------------------------------------------------------------
# _fetch_or_cached — direct testing with weather_cache table
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_fetch_or_cached_stores_and_retrieves(client):
    """_fetch_or_cached should store fetched data and return cache on second call."""
    import json

    from nightcrate.api.weather import _fetch_or_cached

    loc_id = await _create_test_location(client)

    # Build a minimal raw JSON that parse_hourly can handle
    raw_hourly = {
        "time": ["2026-04-13T00:00"],
        "temperature_2m": [10.0],
        "dew_point_2m": [5.0],
        "relative_humidity_2m": [60.0],
        "cloud_cover": [20.0],
        "cloud_cover_low": [10.0],
        "cloud_cover_mid": [5.0],
        "cloud_cover_high": [5.0],
        "wind_speed_10m": [8.0],
        "wind_direction_10m": [180.0],
        "wind_gusts_10m": [15.0],
        "visibility": [20000.0],
        "precipitation": [0.0],
        "precipitation_probability": [10.0],
    }
    raw_json_str = json.dumps(
        {
            "latitude": 34.05,
            "longitude": -118.25,
            "hourly": raw_hourly,
        }
    )

    fake_data = WeatherData(
        latitude=34.05,
        longitude=-118.25,
        source="forecast",
        hourly=[
            HourlyWeather(
                time="2026-04-13T00:00",
                temperature_c=10.0,
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
                wind_speed_200hpa_kmh=None,
                wind_speed_300hpa_kmh=None,
                wind_speed_500hpa_kmh=None,
                geopotential_200hpa_m=None,
                geopotential_300hpa_m=None,
                geopotential_500hpa_m=None,
            )
        ],
        raw_json=raw_json_str,
    )

    # First call — should call fetch_weather and cache
    with patch(
        "nightcrate.api.weather.fetch_weather",
        new_callable=AsyncMock,
        return_value=fake_data,
    ) as mock_fetch:
        result = await _fetch_or_cached(
            location_id=loc_id,
            latitude=34.05,
            longitude=-118.25,
            timezone_str="America/Los_Angeles",
            source="forecast",
        )
        assert mock_fetch.call_count == 1
        assert result.source == "forecast"

    # Second call — should hit the cache
    with patch(
        "nightcrate.api.weather.fetch_weather",
        new_callable=AsyncMock,
    ) as mock_fetch2:
        result2 = await _fetch_or_cached(
            location_id=loc_id,
            latitude=34.05,
            longitude=-118.25,
            timezone_str="America/Los_Angeles",
            source="forecast",
        )
        assert mock_fetch2.call_count == 0  # cache hit, no fetch
        assert result2.latitude == 34.05


# ---------------------------------------------------------------------------
# _fetch_or_cached_supplementary — direct testing
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_fetch_or_cached_supplementary_stores_and_retrieves(client):
    """_fetch_or_cached_supplementary should store and retrieve from cache."""
    import json

    from nightcrate.api.weather import _fetch_or_cached_supplementary
    from nightcrate.services.weather import SupplementaryData

    loc_id = await _create_test_location(client)

    raw_json_str = json.dumps(
        {
            "hourly": {
                "time": ["2026-04-13T00:00", "2026-04-13T01:00"],
                "pwv": [3.5, 3.6],
            }
        }
    )

    fake_supp = SupplementaryData(
        latitude=34.05,
        longitude=-118.25,
        values_by_time={
            "2026-04-13T00:00": 3.5,
            "2026-04-13T01:00": 3.6,
        },
        raw_json=raw_json_str,
    )

    async def mock_fetch(**kwargs):
        return fake_supp

    # First call — should fetch and cache
    result = await _fetch_or_cached_supplementary(
        location_id=loc_id,
        latitude=34.05,
        longitude=-118.25,
        timezone_str="America/Los_Angeles",
        source_key="ecmwf_pwv",
        fetch_fn=mock_fetch,
    )
    assert result["2026-04-13T00:00"] == 3.5
    assert result["2026-04-13T01:00"] == 3.6

    # Second call — should hit cache
    call_count = 0

    async def counting_fetch(**kwargs):
        nonlocal call_count
        call_count += 1
        return fake_supp

    result2 = await _fetch_or_cached_supplementary(
        location_id=loc_id,
        latitude=34.05,
        longitude=-118.25,
        timezone_str="America/Los_Angeles",
        source_key="ecmwf_pwv",
        fetch_fn=counting_fetch,
    )
    assert call_count == 0  # cache hit
    assert result2["2026-04-13T00:00"] == 3.5


# ---------------------------------------------------------------------------
# _compute_seeing unit test — surface fallback
# ---------------------------------------------------------------------------


def test_compute_seeing_surface_fallback():
    """_compute_seeing falls back to surface model when no pressure-level data."""
    from nightcrate.api.weather import _compute_seeing

    h = HourlyWeather(
        time="2026-04-13T22:00",
        temperature_c=10.0,
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
        wind_speed_200hpa_kmh=None,
        wind_speed_300hpa_kmh=None,
        wind_speed_500hpa_kmh=None,
        geopotential_200hpa_m=None,
        geopotential_300hpa_m=None,
        geopotential_500hpa_m=None,
    )

    score = _compute_seeing(h, None)
    assert isinstance(score, int)
    assert 0 <= score <= 100


def test_compute_seeing_with_pressure_data():
    """_compute_seeing uses wind shear model when pressure-level data is present."""
    from nightcrate.api.weather import _compute_seeing

    h = HourlyWeather(
        time="2026-04-13T22:00",
        temperature_c=10.0,
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

    score = _compute_seeing(h, None)
    assert isinstance(score, int)
    assert 0 <= score <= 100
