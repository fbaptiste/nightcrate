# Astronomy Weather Forecast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a weather forecast dashboard for imaging session planning, showing cloud cover, seeing estimates, moon phase, darkness hours, and an overall imaging quality score — all tied to saved observer locations.

**Architecture:** Backend service fetches weather data from Open-Meteo (forecast + historical APIs) and computes astronomical data via astropy (moon, twilight, darkness). A separate seeing estimation service uses upper-atmosphere wind shear (Trinquet/Cherubini methodology) for forecasts and surface-only fallback for historical data. Frontend renders a 7-day overview with daily cards and a detailed hourly timeline for a selected day. All metrics use a consistent 0–100 "goodness" scale (high = better for imaging). Single blue hue with brightness/opacity for quality encoding (bright = good, dark = bad) — never color-only encoding.

**Tech Stack:** Python (FastAPI, astropy, httpx), React + TypeScript (MUI, D3.js for timeline chart), SQLite (weather cache), Open-Meteo API (free, no key)

**Key references:**
- Trinquet & Vernin (2006), "A Model to Forecast Seeing and Estimate Cn² Profiles from Meteorological Data," PASP 118(843), 756–764
- Cherubini & Businger (2013), "Another Look at the Refractive Index Structure Function," J. Applied Meteorology & Climatology 52(2), 498–506
- Open-Meteo Forecast API: https://open-meteo.com/en/docs
- Open-Meteo Historical API: https://archive-api.open-meteo.com/v1/archive

---

## File Structure

### Backend — new files

| File | Responsibility |
|------|---------------|
| `services/weather.py` | Open-Meteo API client — fetches forecast + historical weather data via httpx. Parses JSON into typed dataclasses. Handles both base URLs with shared parsing. |
| `services/astronomy.py` | Astropy computations — moon phase/illumination/altitude, twilight times (civil/nautical/astronomical), sunrise/sunset, darkness hours, moonless dark hours. All pure functions taking (lat, lon, elevation, date). |
| `services/seeing.py` | Seeing estimation — two models: (1) wind-shear model using pressure-level data (forecast), (2) surface-only model (historical fallback). Outputs 0–100 score. |
| `services/imaging_quality.py` | Composite imaging quality score — combines sky clarity, seeing, wind, humidity, moon. Configurable moon toggle. Documents methodology in module docstring. |
| `api/weather.py` | FastAPI router — forecast endpoint, hourly detail endpoint, methodology info endpoint. Reads location from DB, delegates to services. |
| `api/weather_models.py` | Pydantic models — request params, daily summary, hourly detail, methodology description. |
| `db/migrations/0008.weather_cache.sql` | SQLite table for caching Open-Meteo responses (location + date range → JSON, with TTL). |
| `tests/test_seeing.py` | Unit tests for seeing estimation (both models). |
| `tests/test_astronomy.py` | Unit tests for astropy computations (moon, twilight, darkness). |
| `tests/test_imaging_quality.py` | Unit tests for composite score calculation. |
| `tests/test_weather_service.py` | Unit tests for Open-Meteo client (mocked HTTP). |
| `tests/test_weather_api.py` | Integration tests for weather API endpoints. |

### Frontend — new files

| File | Responsibility |
|------|---------------|
| `api/weather.ts` | TypeScript interfaces + fetch functions for weather endpoints. |
| `pages/WeatherPage.tsx` | Main page — location selector, 7-day cards, hourly detail panel. |
| `components/weather/DailyCard.tsx` | Single day card — imaging quality score, sky clarity, seeing, moonless hours, darkness hours, moon phase icon, sunset/sunrise. |
| `components/weather/HourlyTimeline.tsx` | D3-rendered timeline chart — darkness bands, cloud cover layers, moon altitude curve, seeing score, wind. |
| `components/weather/LocationSelector.tsx` | Dropdown to pick from saved locations (default pre-selected). |
| `components/weather/MoonPhaseIcon.tsx` | SVG moon phase icon component (new → full, 8 phases). |
| `components/weather/MethodologyInfo.tsx` | Expandable info panel explaining score calculation, weights, and data sources. |
| `components/weather/QualityBadge.tsx` | Reusable badge showing 0–100 score with blue-hue brightness, text label (Excellent/Good/Marginal/Poor), and optional metric name. |

### Existing files to modify

| File | Change |
|------|--------|
| `backend/src/nightcrate/main.py` | Register weather router, add openapi_tags entry, add weather cache purge to lifespan. |
| `backend/src/nightcrate/core/config.py` | Add `weather_cache_ttl_hours: int = 6` and `weather_moon_penalty: bool = True` to Settings model. |
| `backend/tests/conftest.py` | Add weather_cache table creation. |
| `frontend/src/App.tsx` | Add `/weather` route. |
| `frontend/src/components/AppShell.tsx` | Add Weather nav item (between Locations and Settings). |

---

## Task 1: Database Migration — Weather Cache Table

**Files:**
- Create: `backend/src/nightcrate/db/migrations/0008.weather_cache.sql`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Write the migration SQL**

```sql
-- depends: 0007.locations

-- Cache for Open-Meteo API responses.
-- One row per (location, date range, data source) combination.
-- TTL-based cleanup on startup.

CREATE TABLE IF NOT EXISTS weather_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES location(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (source IN ('forecast', 'archive')),
    start_date TEXT NOT NULL,       -- ISO date YYYY-MM-DD
    end_date TEXT NOT NULL,         -- ISO date YYYY-MM-DD
    response_json TEXT NOT NULL,    -- raw Open-Meteo JSON
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(location_id, source, start_date, end_date)
);
```

Create file `backend/src/nightcrate/db/migrations/0008.weather_cache.sql` with the above content.

- [ ] **Step 2: Update conftest.py to include the new migration**

The existing conftest.py already applies all migrations >= `0005` via sorted filename iteration, so the new `0008.weather_cache.sql` file will be picked up automatically. Verify by checking the loop in `conftest.py` lines 70–79 — it iterates all `.sql` files with name >= `"0005"`.

No code change needed here, but verify the migration applies cleanly:

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_equipment_schema.py -v -x`
Expected: PASS (confirms migration applies without errors)

- [ ] **Step 3: Commit**

```bash
git add backend/src/nightcrate/db/migrations/0008.weather_cache.sql
git commit -m "feat: add weather_cache table migration (0008)"
```

---

## Task 2: Settings — Weather Configuration

**Files:**
- Modify: `backend/src/nightcrate/core/config.py`
- Modify: `frontend/src/stores/settingsStore.ts` (no change needed — Settings model is dynamic JSON)

- [ ] **Step 1: Write the failing test**

Create file `backend/tests/test_weather_settings.py`:

```python
"""Test weather-related settings fields."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.core.config import Settings, get_settings, update_settings
from nightcrate.main import app


class TestWeatherSettings:
    async def test_default_weather_cache_ttl(self):
        settings = Settings()
        assert settings.weather_cache_ttl_hours == 6

    async def test_default_moon_penalty(self):
        settings = Settings()
        assert settings.weather_moon_penalty is True

    async def test_persist_weather_settings(self):
        updated = Settings(weather_cache_ttl_hours=3, weather_moon_penalty=False)
        saved = await update_settings(updated)
        assert saved.weather_cache_ttl_hours == 3
        assert saved.weather_moon_penalty is False

        reloaded = await get_settings()
        assert reloaded.weather_cache_ttl_hours == 3
        assert reloaded.weather_moon_penalty is False


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


class TestWeatherSettingsAPI:
    async def test_settings_roundtrip(self, client: AsyncClient):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["weather_cache_ttl_hours"] == 6
        assert data["weather_moon_penalty"] is True

        resp = await client.put(
            "/api/settings",
            json={**data, "weather_cache_ttl_hours": 2, "weather_moon_penalty": False},
        )
        assert resp.status_code == 200
        assert resp.json()["weather_cache_ttl_hours"] == 2
        assert resp.json()["weather_moon_penalty"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_weather_settings.py -v -x`
Expected: FAIL — `Settings` has no field `weather_cache_ttl_hours`

- [ ] **Step 3: Add settings fields**

In `backend/src/nightcrate/core/config.py`, add two fields to the `Settings` class after `aberration_cache_ttl_days`:

```python
class Settings(BaseModel):
    theme: Literal["light", "dark", "browser"] = "browser"
    gpu_acceleration: bool = True
    max_worker_cores: int | None = None  # None → cpu_count - 1
    last_browse_path: str | None = None
    browser_favorites: list[BrowserFavorite] = []
    aberration_cache_ttl_days: int = 30
    weather_cache_ttl_hours: int = 6
    weather_moon_penalty: bool = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_weather_settings.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/nightcrate/core/config.py backend/tests/test_weather_settings.py
git commit -m "feat: add weather_cache_ttl_hours and weather_moon_penalty settings"
```

---

## Task 3: Astronomy Service — Moon, Twilight, Darkness

**Files:**
- Create: `backend/src/nightcrate/services/astronomy.py`
- Create: `backend/tests/test_astronomy.py`

This is a pure computation module using astropy. No DB, no HTTP, no FastAPI imports.

- [ ] **Step 1: Write the failing tests**

Create file `backend/tests/test_astronomy.py`:

```python
"""Tests for astronomy service — moon, twilight, darkness computations."""

from datetime import date, datetime, timezone

import pytest

from nightcrate.services.astronomy import (
    DarknessWindow,
    HourlyAstro,
    MoonInfo,
    NightSummary,
    compute_hourly_astro,
    compute_night_summary,
)


class TestNightSummary:
    """Test the nightly summary computation for a known location and date."""

    @pytest.fixture
    def summary(self) -> NightSummary:
        # Borrego Springs, CA — dark site, well-characterized
        return compute_night_summary(
            latitude=33.2558,
            longitude=-116.3753,
            elevation_m=236.0,
            night_date=date(2026, 3, 15),
            timezone_str="America/Los_Angeles",
        )

    def test_sunset_before_sunrise(self, summary: NightSummary):
        assert summary.sunset < summary.sunrise

    def test_astronomical_darkness(self, summary: NightSummary):
        assert summary.darkness.astro_start < summary.darkness.astro_end
        assert summary.darkness.astro_start > summary.sunset
        assert summary.darkness.astro_end < summary.sunrise

    def test_darkness_hours_positive(self, summary: NightSummary):
        assert summary.darkness_hours > 0
        assert summary.darkness_hours < 14  # sanity — never more than ~14h

    def test_moonless_hours_lte_darkness(self, summary: NightSummary):
        assert summary.moonless_dark_hours <= summary.darkness_hours
        assert summary.moonless_dark_hours >= 0

    def test_moon_info(self, summary: NightSummary):
        assert 0 <= summary.moon.illumination_pct <= 100
        assert summary.moon.phase_name in (
            "New Moon",
            "Waxing Crescent",
            "First Quarter",
            "Waxing Gibbous",
            "Full Moon",
            "Waning Gibbous",
            "Last Quarter",
            "Waning Crescent",
        )

    def test_twilight_order(self, summary: NightSummary):
        # Evening: sunset < civil_end < nautical_end < astro_start
        assert summary.sunset < summary.darkness.civil_end
        assert summary.darkness.civil_end < summary.darkness.nautical_end
        assert summary.darkness.nautical_end < summary.darkness.astro_start


class TestHourlyAstro:
    """Test hourly astronomical data (moon altitude for each hour of the night)."""

    def test_hourly_returns_entries(self):
        hours = compute_hourly_astro(
            latitude=33.2558,
            longitude=-116.3753,
            elevation_m=236.0,
            night_date=date(2026, 3, 15),
            timezone_str="America/Los_Angeles",
        )
        # Should cover roughly sunset to sunrise — at least 10 hours
        assert len(hours) >= 10

    def test_hourly_has_moon_altitude(self):
        hours = compute_hourly_astro(
            latitude=33.2558,
            longitude=-116.3753,
            elevation_m=236.0,
            night_date=date(2026, 3, 15),
            timezone_str="America/Los_Angeles",
        )
        for h in hours:
            assert isinstance(h.moon_altitude_deg, float)
            assert -90 <= h.moon_altitude_deg <= 90

    def test_hourly_has_timestamps(self):
        hours = compute_hourly_astro(
            latitude=33.2558,
            longitude=-116.3753,
            elevation_m=236.0,
            night_date=date(2026, 3, 15),
            timezone_str="America/Los_Angeles",
        )
        for h in hours:
            assert isinstance(h.time_utc, datetime)
            assert isinstance(h.time_local, str)  # formatted HH:MM
            assert isinstance(h.darkness_category, str)
            assert h.darkness_category in (
                "daylight",
                "civil_twilight",
                "nautical_twilight",
                "astronomical_twilight",
                "night",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_astronomy.py -v -x`
Expected: FAIL — `nightcrate.services.astronomy` does not exist

- [ ] **Step 3: Implement the astronomy service**

Create file `backend/src/nightcrate/services/astronomy.py`:

```python
"""Astronomical computations for imaging session planning.

Uses astropy to compute moon phase/illumination/altitude, twilight times,
sunrise/sunset, darkness windows, and moonless dark hours for a given
observer location and date.

All functions are pure — no DB, no HTTP, no side effects.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone

import numpy as np
from astropy.coordinates import AltAz, EarthLocation, get_body
from astropy.time import Time, TimeDelta
import astropy.units as u


@dataclass(frozen=True)
class MoonInfo:
    illumination_pct: float  # 0–100
    phase_angle_deg: float  # 0–360
    phase_name: str  # e.g. "Waxing Crescent"
    moonrise: str | None  # local time HH:MM or None if no rise
    moonset: str | None  # local time HH:MM or None if no set


@dataclass(frozen=True)
class DarknessWindow:
    civil_end: datetime  # evening civil twilight end
    nautical_end: datetime  # evening nautical twilight end
    astro_start: datetime  # astronomical darkness begins
    astro_end: datetime  # astronomical darkness ends (morning)
    nautical_start: datetime  # morning nautical twilight starts
    civil_start: datetime  # morning civil twilight starts


@dataclass(frozen=True)
class NightSummary:
    sunset: datetime
    sunrise: datetime
    darkness: DarknessWindow
    darkness_hours: float  # hours of astronomical darkness
    moonless_dark_hours: float  # darkness hours with moon below horizon
    moon: MoonInfo


@dataclass(frozen=True)
class HourlyAstro:
    time_utc: datetime
    time_local: str  # HH:MM in observer timezone
    moon_altitude_deg: float
    moon_illumination_pct: float
    darkness_category: str  # daylight/civil_twilight/nautical_twilight/astronomical_twilight/night


def _make_location(latitude: float, longitude: float, elevation_m: float) -> EarthLocation:
    return EarthLocation(lat=latitude * u.deg, lon=longitude * u.deg, height=(elevation_m or 0) * u.m)


def _find_horizon_crossing(
    location: EarthLocation,
    body_name: str,
    t_start: Time,
    t_end: Time,
    altitude_deg: float,
    rising: bool,
    steps: int = 200,
) -> Time | None:
    """Find when a body crosses a given altitude between t_start and t_end.

    Uses dense sampling + linear interpolation. Returns the first crossing
    matching the direction (rising=True for upward crossing, False for downward).
    Returns None if no crossing found.
    """
    times = t_start + (t_end - t_start) * np.linspace(0, 1, steps)
    altaz = AltAz(obstime=times, location=location)
    alts = get_body(body_name, times).transform_to(altaz).alt.deg

    for i in range(len(alts) - 1):
        crossed_up = alts[i] < altitude_deg <= alts[i + 1]
        crossed_down = alts[i] > altitude_deg >= alts[i + 1]
        if (rising and crossed_up) or (not rising and crossed_down):
            # Linear interpolation for sub-step accuracy
            frac = (altitude_deg - alts[i]) / (alts[i + 1] - alts[i])
            dt = (times[i + 1] - times[i]) * frac
            return times[i] + dt

    return None


def _time_to_datetime(t: Time) -> datetime:
    return t.to_datetime(timezone=timezone.utc)


def _time_to_local_str(t: Time, tz_str: str) -> str:
    import zoneinfo

    tz = zoneinfo.ZoneInfo(tz_str)
    dt = t.to_datetime(timezone=timezone.utc).astimezone(tz)
    return dt.strftime("%H:%M")


def _moon_phase_name(phase_angle_deg: float) -> str:
    """Map phase angle (0=new, 180=full) to standard 8-phase name."""
    a = phase_angle_deg % 360
    if a < 22.5:
        return "New Moon"
    elif a < 67.5:
        return "Waxing Crescent"
    elif a < 112.5:
        return "First Quarter"
    elif a < 157.5:
        return "Waxing Gibbous"
    elif a < 202.5:
        return "Full Moon"
    elif a < 247.5:
        return "Waning Gibbous"
    elif a < 292.5:
        return "Last Quarter"
    elif a < 337.5:
        return "Waning Crescent"
    else:
        return "New Moon"


def _moon_illumination(time: Time) -> float:
    """Compute moon illumination percentage (0–100) at a given time."""
    sun = get_body("sun", time)
    moon = get_body("moon", time)
    elongation = sun.separation(moon)
    phase_angle = np.arctan2(
        sun.distance * np.sin(elongation),
        moon.distance - sun.distance * np.cos(elongation),
    )
    return float((1 + np.cos(phase_angle)) / 2 * 100)


def _moon_phase_angle(time: Time) -> float:
    """Compute moon phase angle in degrees (0=new, 180=full)."""
    sun = get_body("sun", time)
    moon = get_body("moon", time)
    elongation = sun.separation(moon).deg
    # Simple approximation: elongation ≈ phase angle for our purposes
    return float(elongation)


def compute_night_summary(
    latitude: float,
    longitude: float,
    elevation_m: float | None,
    night_date: date,
    timezone_str: str,
) -> NightSummary:
    """Compute a full night summary for the evening of the given date.

    The "night" spans from the evening of night_date to the morning of night_date + 1.
    All times are returned as UTC datetimes.
    """
    import zoneinfo

    tz = zoneinfo.ZoneInfo(timezone_str)
    location = _make_location(latitude, longitude, elevation_m or 0)

    # Noon on the given date in local time — guaranteed to be before sunset
    local_noon = datetime(night_date.year, night_date.month, night_date.day, 12, 0, tzinfo=tz)
    t_noon = Time(local_noon)
    # Search window: noon to noon next day
    t_next_noon = t_noon + TimeDelta(1, format="jd")

    # Sun crossings
    sunset_t = _find_horizon_crossing(location, "sun", t_noon, t_next_noon, -0.833, rising=False)
    sunrise_t = _find_horizon_crossing(location, "sun", t_noon, t_next_noon, -0.833, rising=True)
    civil_end = _find_horizon_crossing(location, "sun", t_noon, t_next_noon, -6.0, rising=False)
    nautical_end = _find_horizon_crossing(location, "sun", t_noon, t_next_noon, -12.0, rising=False)
    astro_start = _find_horizon_crossing(location, "sun", t_noon, t_next_noon, -18.0, rising=False)
    astro_end = _find_horizon_crossing(location, "sun", t_noon, t_next_noon, -18.0, rising=True)
    nautical_start = _find_horizon_crossing(location, "sun", t_noon, t_next_noon, -12.0, rising=True)
    civil_start = _find_horizon_crossing(location, "sun", t_noon, t_next_noon, -6.0, rising=True)

    # All crossings should exist for non-polar locations
    assert sunset_t is not None, "No sunset found (polar conditions?)"
    assert sunrise_t is not None, "No sunrise found (polar conditions?)"
    assert astro_start is not None, "No astronomical darkness (high latitude summer?)"
    assert astro_end is not None, "No astronomical darkness end"

    # Darkness hours
    darkness_hours = (astro_end - astro_start).to_value("hr")

    # Moon info at midnight local
    local_midnight = datetime(
        night_date.year, night_date.month, night_date.day, 0, 0, tzinfo=tz
    ) + __import__("datetime").timedelta(days=1)
    t_midnight = Time(local_midnight)
    illum = _moon_illumination(t_midnight)
    phase_angle = _moon_phase_angle(t_midnight)

    # Moon rise/set during the night
    moonrise_t = _find_horizon_crossing(location, "moon", sunset_t, sunrise_t, 0.0, rising=True)
    moonset_t = _find_horizon_crossing(location, "moon", sunset_t, sunrise_t, 0.0, rising=False)

    # Moonless dark hours: time during astronomical darkness when moon is below horizon
    # Sample at 5-minute intervals during astronomical darkness
    n_samples = max(1, int(darkness_hours * 12))  # 12 samples per hour = 5 min
    dark_times = astro_start + (astro_end - astro_start) * np.linspace(0, 1, n_samples)
    altaz = AltAz(obstime=dark_times, location=location)
    moon_alts = get_body("moon", dark_times).transform_to(altaz).alt.deg
    moonless_fraction = float(np.sum(moon_alts < 0) / len(moon_alts))
    moonless_dark_hours = darkness_hours * moonless_fraction

    moon = MoonInfo(
        illumination_pct=round(illum, 1),
        phase_angle_deg=round(phase_angle, 1),
        phase_name=_moon_phase_name(phase_angle),
        moonrise=_time_to_local_str(moonrise_t, timezone_str) if moonrise_t else None,
        moonset=_time_to_local_str(moonset_t, timezone_str) if moonset_t else None,
    )

    darkness = DarknessWindow(
        civil_end=_time_to_datetime(civil_end),
        nautical_end=_time_to_datetime(nautical_end),
        astro_start=_time_to_datetime(astro_start),
        astro_end=_time_to_datetime(astro_end),
        nautical_start=_time_to_datetime(nautical_start),
        civil_start=_time_to_datetime(civil_start),
    )

    return NightSummary(
        sunset=_time_to_datetime(sunset_t),
        sunrise=_time_to_datetime(sunrise_t),
        darkness=darkness,
        darkness_hours=round(darkness_hours, 2),
        moonless_dark_hours=round(moonless_dark_hours, 2),
        moon=moon,
    )


def compute_hourly_astro(
    latitude: float,
    longitude: float,
    elevation_m: float | None,
    night_date: date,
    timezone_str: str,
) -> list[HourlyAstro]:
    """Compute hourly moon altitude and darkness category from sunset to sunrise.

    Returns one entry per hour. Used by the hourly timeline chart.
    """
    import zoneinfo

    tz = zoneinfo.ZoneInfo(timezone_str)
    location = _make_location(latitude, longitude, elevation_m or 0)

    # Get sunset/sunrise to define the range
    local_noon = datetime(night_date.year, night_date.month, night_date.day, 12, 0, tzinfo=tz)
    t_noon = Time(local_noon)
    t_next_noon = t_noon + TimeDelta(1, format="jd")

    sunset_t = _find_horizon_crossing(location, "sun", t_noon, t_next_noon, -0.833, rising=False)
    sunrise_t = _find_horizon_crossing(location, "sun", t_noon, t_next_noon, -0.833, rising=True)

    if sunset_t is None or sunrise_t is None:
        return []

    # Generate hourly timestamps from one hour before sunset to one hour after sunrise
    t_start = sunset_t - TimeDelta(1 / 24, format="jd")
    t_end = sunrise_t + TimeDelta(1 / 24, format="jd")
    n_hours = int(np.ceil((t_end - t_start).to_value("hr")))

    results = []
    for i in range(n_hours + 1):
        t = t_start + TimeDelta(i / 24, format="jd")
        altaz = AltAz(obstime=t, location=location)

        sun_alt = get_body("sun", t).transform_to(altaz).alt.deg
        moon_pos = get_body("moon", t).transform_to(altaz)
        moon_alt = float(moon_pos.alt.deg)
        illum = _moon_illumination(t)

        if sun_alt > -0.833:
            category = "daylight"
        elif sun_alt > -6.0:
            category = "civil_twilight"
        elif sun_alt > -12.0:
            category = "nautical_twilight"
        elif sun_alt > -18.0:
            category = "astronomical_twilight"
        else:
            category = "night"

        results.append(
            HourlyAstro(
                time_utc=_time_to_datetime(t),
                time_local=_time_to_local_str(t, timezone_str),
                moon_altitude_deg=round(moon_alt, 1),
                moon_illumination_pct=round(illum, 1),
                darkness_category=category,
            )
        )

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_astronomy.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/nightcrate/services/astronomy.py backend/tests/test_astronomy.py
git commit -m "feat: add astronomy service — moon, twilight, darkness computations"
```

---

## Task 4: Seeing Estimation Service

**Files:**
- Create: `backend/src/nightcrate/services/seeing.py`
- Create: `backend/tests/test_seeing.py`

Two models: (1) wind-shear model using pressure-level data for forecasts, (2) surface-only model for historical fallback. Both output a 0–100 goodness score.

- [ ] **Step 1: Write the failing tests**

Create file `backend/tests/test_seeing.py`:

```python
"""Tests for seeing estimation service."""

import pytest

from nightcrate.services.seeing import (
    estimate_seeing_surface,
    estimate_seeing_wind_shear,
)


class TestSurfaceModel:
    """JAG-Lab-style surface-only seeing estimate."""

    def test_perfect_conditions(self):
        # Low humidity, moderate wind, large temp-dew spread, stable temp
        score = estimate_seeing_surface(
            temperature_c=10.0,
            dew_point_c=-5.0,
            humidity_pct=20.0,
            wind_speed_kmh=7.0,
            prev_temperature_c=10.5,
        )
        assert 70 <= score <= 100

    def test_terrible_conditions(self):
        # High humidity, strong wind, zero spread, unstable temp
        score = estimate_seeing_surface(
            temperature_c=15.0,
            dew_point_c=15.0,
            humidity_pct=95.0,
            wind_speed_kmh=40.0,
            prev_temperature_c=10.0,
        )
        assert 0 <= score <= 30

    def test_score_range(self):
        for temp in (0, 10, 25):
            for hum in (10, 50, 90):
                for wind in (0, 10, 30):
                    score = estimate_seeing_surface(
                        temperature_c=temp,
                        dew_point_c=temp - 5,
                        humidity_pct=hum,
                        wind_speed_kmh=wind,
                    )
                    assert 0 <= score <= 100

    def test_no_prev_temperature(self):
        score = estimate_seeing_surface(
            temperature_c=10.0,
            dew_point_c=2.0,
            humidity_pct=50.0,
            wind_speed_kmh=10.0,
            prev_temperature_c=None,
        )
        assert 0 <= score <= 100


class TestWindShearModel:
    """Trinquet/Cherubini wind-shear seeing estimate for forecast data."""

    def test_calm_jet_stream(self):
        # Light winds at all levels = good seeing
        score = estimate_seeing_wind_shear(
            wind_speed_200hpa_kmh=20.0,
            wind_speed_300hpa_kmh=15.0,
            wind_speed_500hpa_kmh=10.0,
            geopotential_200hpa_m=11800.0,
            geopotential_300hpa_m=9200.0,
            geopotential_500hpa_m=5500.0,
            temperature_c=10.0,
            dew_point_c=2.0,
            humidity_pct=40.0,
            wind_speed_surface_kmh=5.0,
            prev_temperature_c=10.0,
        )
        assert 60 <= score <= 100

    def test_strong_jet_stream(self):
        # Strong upper winds = bad seeing
        score = estimate_seeing_wind_shear(
            wind_speed_200hpa_kmh=150.0,
            wind_speed_300hpa_kmh=120.0,
            wind_speed_500hpa_kmh=60.0,
            geopotential_200hpa_m=11800.0,
            geopotential_300hpa_m=9200.0,
            geopotential_500hpa_m=5500.0,
            temperature_c=10.0,
            dew_point_c=2.0,
            humidity_pct=40.0,
            wind_speed_surface_kmh=5.0,
            prev_temperature_c=10.0,
        )
        assert 0 <= score <= 40

    def test_score_always_0_to_100(self):
        for upper_wind in (10, 50, 100, 200):
            score = estimate_seeing_wind_shear(
                wind_speed_200hpa_kmh=float(upper_wind),
                wind_speed_300hpa_kmh=float(upper_wind * 0.8),
                wind_speed_500hpa_kmh=float(upper_wind * 0.5),
                geopotential_200hpa_m=11800.0,
                geopotential_300hpa_m=9200.0,
                geopotential_500hpa_m=5500.0,
                temperature_c=10.0,
                dew_point_c=2.0,
                humidity_pct=50.0,
                wind_speed_surface_kmh=10.0,
            )
            assert 0 <= score <= 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_seeing.py -v -x`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the seeing service**

Create file `backend/src/nightcrate/services/seeing.py`:

```python
"""Astronomical seeing estimation from weather data.

Two models:

1. **Surface-only model** — uses ground-level weather variables only.
   Based on the JAG Lab methodology. Suitable for historical data where
   upper-atmosphere observations are unavailable.

2. **Wind-shear model** — incorporates upper-atmosphere wind speed at
   200/300/500 hPa pressure levels. Based on Trinquet & Vernin (2006) and
   Cherubini & Businger (2013). Used for forecast data where Open-Meteo
   provides pressure-level variables.

Both models output a 0–100 score where **higher = better seeing**.

References:
- Trinquet, H. & Vernin, J. (2006). PASP 118(843), 756–764.
- Cherubini, T. & Businger, S. (2013). J. Appl. Meteorol. Climatol. 52(2), 498–506.
"""


def estimate_seeing_surface(
    temperature_c: float,
    dew_point_c: float,
    humidity_pct: float,
    wind_speed_kmh: float,
    prev_temperature_c: float | None = None,
) -> int:
    """Surface-only seeing estimate (JAG Lab methodology).

    Components (weighted sum):
    - Temperature–dew point spread (30%): larger spread → less moisture → better
    - Wind at surface (30%): 5–10 km/h optimal, degrades above 10
    - Humidity (20%): lower → better
    - Temperature stability (20%): smaller hour-to-hour change → better

    Returns: 0–100 integer, higher = better seeing.
    """
    # Component 1: temp–dew point spread (30%)
    spread = abs(temperature_c - dew_point_c)
    temp_dew_score = min(100, max(0, 60 + spread * 2))

    # Component 2: surface wind (30%)
    if wind_speed_kmh < 5:
        wind_score = max(60, wind_speed_kmh * 12)
    elif wind_speed_kmh <= 10:
        wind_score = 100
    else:
        wind_score = max(0, 100 - (wind_speed_kmh - 10) * 5)

    # Component 3: humidity (20%)
    humidity_score = max(0, 100 - humidity_pct * 0.8)

    # Component 4: temperature stability (20%)
    if prev_temperature_c is not None:
        temp_change = abs(temperature_c - prev_temperature_c)
        stability_score = max(0, 100 - temp_change * 10)
    else:
        stability_score = 70  # neutral assumption when no prior data

    score = (
        temp_dew_score * 0.30
        + wind_score * 0.30
        + humidity_score * 0.20
        + stability_score * 0.20
    )
    return round(min(100, max(0, score)))


def estimate_seeing_wind_shear(
    wind_speed_200hpa_kmh: float,
    wind_speed_300hpa_kmh: float,
    wind_speed_500hpa_kmh: float,
    geopotential_200hpa_m: float,
    geopotential_300hpa_m: float,
    geopotential_500hpa_m: float,
    temperature_c: float,
    dew_point_c: float,
    humidity_pct: float,
    wind_speed_surface_kmh: float,
    prev_temperature_c: float | None = None,
) -> int:
    """Wind-shear seeing estimate using upper-atmosphere data.

    Combines two contributions:

    1. **Upper-atmosphere turbulence (60% weight):** Wind shear between
       pressure levels as a proxy for optical turbulence (Cn²). Based on
       Cherubini & Businger (2013): shear = |ΔV| / Δz between adjacent
       pressure levels. Higher shear → worse seeing.

    2. **Surface conditions (40% weight):** Same components as the
       surface-only model, re-weighted.

    The upper-atmosphere component uses 200 hPa wind speed as the primary
    jet stream indicator (per Sarazin & Tokovinin 2002, ESO methodology)
    plus inter-layer shear for finer discrimination.

    Returns: 0–100 integer, higher = better seeing.
    """
    # --- Upper atmosphere (60%) ---

    # Layer shear: wind speed difference / geopotential height difference
    # Convert km/h to m/s for shear calculation
    v200 = wind_speed_200hpa_kmh / 3.6
    v300 = wind_speed_300hpa_kmh / 3.6
    v500 = wind_speed_500hpa_kmh / 3.6

    dz_200_300 = abs(geopotential_200hpa_m - geopotential_300hpa_m)
    dz_300_500 = abs(geopotential_300hpa_m - geopotential_500hpa_m)

    # Avoid division by zero (shouldn't happen with real data)
    dz_200_300 = max(dz_200_300, 100)
    dz_300_500 = max(dz_300_500, 100)

    shear_200_300 = abs(v200 - v300) / dz_200_300  # s⁻¹
    shear_300_500 = abs(v300 - v500) / dz_300_500  # s⁻¹

    # Jet stream indicator: 200 hPa wind speed
    # ESO correlation: < 15 m/s → good, > 30 m/s → poor
    jet_speed = v200
    if jet_speed < 10:
        jet_score = 100
    elif jet_speed < 20:
        jet_score = 100 - (jet_speed - 10) * 3  # 100 → 70
    elif jet_speed < 35:
        jet_score = 70 - (jet_speed - 20) * 4  # 70 → 10
    else:
        jet_score = max(0, 10 - (jet_speed - 35) * 1)

    # Shear penalty: high shear between layers indicates turbulence
    # Typical good seeing: shear < 0.002 s⁻¹; bad: > 0.005 s⁻¹
    avg_shear = (shear_200_300 + shear_300_500) / 2
    if avg_shear < 0.001:
        shear_score = 100
    elif avg_shear < 0.003:
        shear_score = 100 - (avg_shear - 0.001) * 25000  # 100 → 50
    else:
        shear_score = max(0, 50 - (avg_shear - 0.003) * 15000)

    upper_score = jet_score * 0.6 + shear_score * 0.4

    # --- Surface conditions (40%) ---
    surface_score = estimate_seeing_surface(
        temperature_c=temperature_c,
        dew_point_c=dew_point_c,
        humidity_pct=humidity_pct,
        wind_speed_kmh=wind_speed_surface_kmh,
        prev_temperature_c=prev_temperature_c,
    )

    score = upper_score * 0.60 + surface_score * 0.40
    return round(min(100, max(0, score)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_seeing.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/nightcrate/services/seeing.py backend/tests/test_seeing.py
git commit -m "feat: add seeing estimation service — surface + wind-shear models"
```

---

## Task 5: Imaging Quality Score Service

**Files:**
- Create: `backend/src/nightcrate/services/imaging_quality.py`
- Create: `backend/tests/test_imaging_quality.py`

Composite 0–100 score combining sky clarity, seeing, wind, humidity, and optional moon penalty. Documents its own methodology.

- [ ] **Step 1: Write the failing tests**

Create file `backend/tests/test_imaging_quality.py`:

```python
"""Tests for composite imaging quality score."""

import pytest

from nightcrate.services.imaging_quality import (
    METHODOLOGY,
    ImagingQualityInput,
    compute_imaging_quality,
)


class TestImagingQuality:
    def test_perfect_night(self):
        result = compute_imaging_quality(
            ImagingQualityInput(
                cloud_cover_pct=0,
                seeing_score=95,
                wind_speed_kmh=3,
                humidity_pct=20,
                moonless_dark_hours=8,
                darkness_hours=8,
                moon_illumination_pct=0,
            ),
            include_moon=True,
        )
        assert result.overall >= 80

    def test_cloudy_night(self):
        result = compute_imaging_quality(
            ImagingQualityInput(
                cloud_cover_pct=90,
                seeing_score=80,
                wind_speed_kmh=5,
                humidity_pct=30,
                moonless_dark_hours=6,
                darkness_hours=8,
                moon_illumination_pct=10,
            ),
            include_moon=True,
        )
        assert result.overall <= 30

    def test_moon_toggle_difference(self):
        inp = ImagingQualityInput(
            cloud_cover_pct=10,
            seeing_score=70,
            wind_speed_kmh=5,
            humidity_pct=30,
            moonless_dark_hours=2,
            darkness_hours=8,
            moon_illumination_pct=95,
        )
        with_moon = compute_imaging_quality(inp, include_moon=True)
        without_moon = compute_imaging_quality(inp, include_moon=False)
        assert without_moon.overall > with_moon.overall

    def test_new_moon_no_penalty(self):
        inp = ImagingQualityInput(
            cloud_cover_pct=10,
            seeing_score=70,
            wind_speed_kmh=5,
            humidity_pct=30,
            moonless_dark_hours=8,
            darkness_hours=8,
            moon_illumination_pct=0,
        )
        with_moon = compute_imaging_quality(inp, include_moon=True)
        without_moon = compute_imaging_quality(inp, include_moon=False)
        # With new moon, scores should be very close (moon_penalty ≈ 0)
        assert abs(with_moon.overall - without_moon.overall) <= 2

    def test_score_range(self):
        for cloud in (0, 50, 100):
            for seeing in (0, 50, 100):
                result = compute_imaging_quality(
                    ImagingQualityInput(
                        cloud_cover_pct=cloud,
                        seeing_score=seeing,
                        wind_speed_kmh=10,
                        humidity_pct=50,
                        moonless_dark_hours=4,
                        darkness_hours=8,
                        moon_illumination_pct=50,
                    ),
                    include_moon=True,
                )
                assert 0 <= result.overall <= 100

    def test_breakdown_present(self):
        result = compute_imaging_quality(
            ImagingQualityInput(
                cloud_cover_pct=20,
                seeing_score=75,
                wind_speed_kmh=8,
                humidity_pct=40,
                moonless_dark_hours=6,
                darkness_hours=8,
                moon_illumination_pct=30,
            ),
            include_moon=True,
        )
        assert 0 <= result.sky_clarity <= 100
        assert 0 <= result.seeing <= 100
        assert 0 <= result.wind_calm <= 100
        assert 0 <= result.dryness <= 100
        assert 0 <= result.moon_score <= 100

    def test_methodology_documented(self):
        assert len(METHODOLOGY) > 100  # not empty
        assert "Sky clarity" in METHODOLOGY
        assert "40%" in METHODOLOGY


class TestLabel:
    def test_excellent(self):
        result = compute_imaging_quality(
            ImagingQualityInput(
                cloud_cover_pct=0,
                seeing_score=95,
                wind_speed_kmh=3,
                humidity_pct=20,
                moonless_dark_hours=8,
                darkness_hours=8,
                moon_illumination_pct=0,
            ),
            include_moon=False,
        )
        assert result.label == "Excellent"

    def test_poor(self):
        result = compute_imaging_quality(
            ImagingQualityInput(
                cloud_cover_pct=95,
                seeing_score=10,
                wind_speed_kmh=40,
                humidity_pct=90,
                moonless_dark_hours=0,
                darkness_hours=8,
                moon_illumination_pct=100,
            ),
            include_moon=True,
        )
        assert result.label == "Poor"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_imaging_quality.py -v -x`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the imaging quality service**

Create file `backend/src/nightcrate/services/imaging_quality.py`:

```python
"""Composite imaging quality score for astronomical imaging sessions.

Combines multiple weather and astronomical factors into a single 0–100
score where **higher = better conditions for imaging**.

Factors and weights:
- Sky clarity (40%): 100 - cloud_cover_pct. Clouds are the #1 session killer.
- Seeing quality (25%): Direct pass-through of seeing score (0–100).
- Moon penalty (20%, optional): Based on moon-up fraction of darkness × illumination.
  Disabled for narrowband shooters who image regardless of moon.
- Wind calm (10%): Inverted + scaled surface wind. Mostly matters for long FL.
- Dryness (5%): Inverted humidity. Dew risk + transparency loss.

When moon penalty is disabled, the 20% weight is redistributed:
sky clarity gets 50%, seeing 30%, wind 12%, dryness 8%.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ImagingQualityInput:
    cloud_cover_pct: float  # 0–100
    seeing_score: int  # 0–100, higher = better
    wind_speed_kmh: float
    humidity_pct: float  # 0–100
    moonless_dark_hours: float
    darkness_hours: float
    moon_illumination_pct: float  # 0–100


@dataclass(frozen=True)
class ImagingQualityResult:
    overall: int  # 0–100
    label: str  # Excellent / Good / Marginal / Poor
    sky_clarity: int  # 0–100
    seeing: int  # 0–100 (pass-through)
    wind_calm: int  # 0–100
    dryness: int  # 0–100
    moon_score: int  # 0–100 (100 = no moon impact)
    moon_included: bool


METHODOLOGY = """\
Imaging Quality Score (0–100) — higher is better.

**Factors and weights (with moon penalty enabled):**
- **Sky clarity (40%):** 100 minus total cloud cover percentage. \
Clouds are the primary session killer — even partial cover disrupts long exposures.
- **Seeing quality (25%):** Atmospheric turbulence estimate. For forecasts, \
this uses upper-atmosphere wind shear at 200/300/500 hPa pressure levels \
(Trinquet & Vernin 2006, Cherubini & Businger 2013). For historical data, \
a surface-only estimate is used.
- **Moon penalty (20%):** Proportional to moon-up time during darkness × \
illumination. A full moon up all night scores 0; a new moon scores 100. \
Disable this toggle if you shoot narrowband (Ha/OIII/SII) where moonlight \
has minimal impact.
- **Wind calm (10%):** Surface wind penalty. Calm (< 5 km/h) to moderate \
(< 15 km/h) scores well; strong wind (> 25 km/h) scores poorly. Matters \
most for long focal length setups susceptible to vibration.
- **Dryness (5%):** Inverse of relative humidity. High humidity risks dew \
on optics and reduces atmospheric transparency.

**When moon penalty is disabled,** weights redistribute to: \
Sky clarity 50%, Seeing 30%, Wind 12%, Dryness 8%.

**Labels:** Excellent (80–100), Good (55–79), Marginal (30–54), Poor (0–29).

**Data sources:** Open-Meteo (weather), astropy (moon/twilight).\
"""


def _wind_calm_score(wind_speed_kmh: float) -> int:
    """Convert wind speed to 0–100 calm score."""
    if wind_speed_kmh <= 5:
        return 100
    elif wind_speed_kmh <= 15:
        return round(100 - (wind_speed_kmh - 5) * 4)  # 100 → 60
    elif wind_speed_kmh <= 30:
        return round(60 - (wind_speed_kmh - 15) * 3.5)  # 60 → 7.5
    else:
        return 0


def _dryness_score(humidity_pct: float) -> int:
    """Convert humidity to 0–100 dryness score."""
    return round(max(0, min(100, 100 - humidity_pct)))


def _moon_penalty_score(
    moonless_dark_hours: float,
    darkness_hours: float,
    moon_illumination_pct: float,
) -> int:
    """Compute moon impact score (100 = no moon impact, 0 = worst case).

    Combines moon-up fraction during darkness with illumination level.
    New moon always scores ~100 regardless of position.
    """
    if darkness_hours <= 0:
        return 100  # no darkness at all — moon is irrelevant

    moonless_fraction = moonless_dark_hours / darkness_hours
    moon_up_fraction = 1.0 - moonless_fraction
    illumination_factor = moon_illumination_pct / 100.0

    # Penalty is proportional to both how long the moon is up AND how bright it is
    penalty = moon_up_fraction * illumination_factor
    return round(max(0, min(100, (1.0 - penalty) * 100)))


def _label(score: int) -> str:
    if score >= 80:
        return "Excellent"
    elif score >= 55:
        return "Good"
    elif score >= 30:
        return "Marginal"
    else:
        return "Poor"


def compute_imaging_quality(
    inp: ImagingQualityInput,
    include_moon: bool = True,
) -> ImagingQualityResult:
    """Compute composite imaging quality score.

    Args:
        inp: All input metrics for the scoring period.
        include_moon: Whether to include moon penalty. Disable for
            narrowband shooters who image regardless of moonlight.

    Returns:
        ImagingQualityResult with overall score, label, and per-factor breakdown.
    """
    sky_clarity = round(max(0, min(100, 100 - inp.cloud_cover_pct)))
    seeing = round(max(0, min(100, inp.seeing_score)))
    wind_calm = _wind_calm_score(inp.wind_speed_kmh)
    dryness = _dryness_score(inp.humidity_pct)
    moon_score = _moon_penalty_score(
        inp.moonless_dark_hours, inp.darkness_hours, inp.moon_illumination_pct
    )

    if include_moon:
        overall = (
            sky_clarity * 0.40
            + seeing * 0.25
            + moon_score * 0.20
            + wind_calm * 0.10
            + dryness * 0.05
        )
    else:
        overall = (
            sky_clarity * 0.50
            + seeing * 0.30
            + wind_calm * 0.12
            + dryness * 0.08
        )

    overall_int = round(max(0, min(100, overall)))

    return ImagingQualityResult(
        overall=overall_int,
        label=_label(overall_int),
        sky_clarity=sky_clarity,
        seeing=seeing,
        wind_calm=wind_calm,
        dryness=dryness,
        moon_score=moon_score,
        moon_included=include_moon,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_imaging_quality.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/nightcrate/services/imaging_quality.py backend/tests/test_imaging_quality.py
git commit -m "feat: add imaging quality composite score service"
```

---

## Task 6: Open-Meteo Weather Client Service

**Files:**
- Create: `backend/src/nightcrate/services/weather.py`
- Create: `backend/tests/test_weather_service.py`

Fetches forecast and historical weather data from Open-Meteo. Parses into typed dataclasses. Handles both APIs with shared parsing code.

- [ ] **Step 1: Write the failing tests**

Create file `backend/tests/test_weather_service.py`:

```python
"""Tests for Open-Meteo weather client service.

Uses mocked HTTP responses — no real API calls in tests.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from nightcrate.services.weather import (
    HourlyWeather,
    WeatherData,
    fetch_weather,
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


def _make_mock_response(json_data: dict) -> AsyncMock:
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = AsyncMock()
    return mock_resp


class TestFetchWeather:
    @patch("nightcrate.services.weather.httpx.AsyncClient")
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

    @patch("nightcrate.services.weather.httpx.AsyncClient")
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

    @patch("nightcrate.services.weather.httpx.AsyncClient")
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

    @patch("nightcrate.services.weather.httpx.AsyncClient")
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

    @patch("nightcrate.services.weather.httpx.AsyncClient")
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_weather_service.py -v -x`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the weather service**

Create file `backend/src/nightcrate/services/weather.py`:

```python
"""Open-Meteo weather data client.

Fetches hourly weather data from two Open-Meteo APIs:
- Forecast: https://api.open-meteo.com/v1/forecast (up to 16 days ahead)
- Archive: https://archive-api.open-meteo.com/v1/archive (back to 1940)

Both APIs share the same parameter format and response structure.
The forecast API additionally provides pressure-level wind data for
seeing estimation.

No API key required for non-commercial use.
"""

from dataclasses import dataclass
from typing import Literal

import httpx

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Hourly variables requested from both APIs
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
]

# Additional pressure-level variables (forecast API only)
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
    time: str  # ISO datetime string
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
    # Pressure-level data (forecast only — None for archive)
    wind_speed_200hpa_kmh: float | None = None
    wind_speed_300hpa_kmh: float | None = None
    wind_speed_500hpa_kmh: float | None = None
    geopotential_200hpa_m: float | None = None
    geopotential_300hpa_m: float | None = None
    geopotential_500hpa_m: float | None = None


@dataclass(frozen=True)
class WeatherData:
    latitude: float
    longitude: float
    source: Literal["forecast", "archive"]
    hourly: list[HourlyWeather]
    raw_json: str  # original response for caching


def _parse_hourly(hourly: dict, source: str) -> list[HourlyWeather]:
    """Parse the hourly block from an Open-Meteo response."""
    times = hourly["time"]
    n = len(times)
    result = []

    for i in range(n):
        pressure_kwargs = {}
        if source == "forecast":
            pressure_kwargs = {
                "wind_speed_200hpa_kmh": hourly.get("wind_speed_200hPa", [None] * n)[i],
                "wind_speed_300hpa_kmh": hourly.get("wind_speed_300hPa", [None] * n)[i],
                "wind_speed_500hpa_kmh": hourly.get("wind_speed_500hPa", [None] * n)[i],
                "geopotential_200hpa_m": hourly.get("geopotential_height_200hPa", [None] * n)[i],
                "geopotential_300hpa_m": hourly.get("geopotential_height_300hPa", [None] * n)[i],
                "geopotential_500hpa_m": hourly.get("geopotential_height_500hPa", [None] * n)[i],
            }

        result.append(
            HourlyWeather(
                time=times[i],
                temperature_c=hourly["temperature_2m"][i],
                dew_point_c=hourly["dew_point_2m"][i],
                humidity_pct=hourly["relative_humidity_2m"][i],
                cloud_cover_pct=hourly["cloud_cover"][i],
                cloud_cover_low_pct=hourly["cloud_cover_low"][i],
                cloud_cover_mid_pct=hourly["cloud_cover_mid"][i],
                cloud_cover_high_pct=hourly["cloud_cover_high"][i],
                wind_speed_kmh=hourly["wind_speed_10m"][i],
                wind_direction_deg=hourly["wind_direction_10m"][i],
                wind_gusts_kmh=hourly["wind_gusts_10m"][i],
                visibility_m=hourly.get("visibility", [None] * n)[i],
                **pressure_kwargs,
            )
        )

    return result


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
        latitude: Observer latitude.
        longitude: Observer longitude.
        timezone_str: IANA timezone (e.g. "America/Los_Angeles").
        source: "forecast" for future data, "archive" for historical.
        start_date: Required for archive. ISO date YYYY-MM-DD.
        end_date: Required for archive. ISO date YYYY-MM-DD.

    Returns:
        WeatherData with parsed hourly entries and raw JSON for caching.
    """
    base_url = _FORECAST_URL if source == "forecast" else _ARCHIVE_URL

    hourly_vars = list(_COMMON_HOURLY)
    if source == "forecast":
        hourly_vars.extend(_PRESSURE_LEVEL_HOURLY)

    params: dict = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(hourly_vars),
        "timezone": timezone_str,
        "wind_speed_unit": "kmh",
    }

    if source == "archive":
        if not start_date or not end_date:
            raise ValueError("start_date and end_date required for archive source")
        params["start_date"] = start_date
        params["end_date"] = end_date

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(base_url, params=params)
        resp.raise_for_status()
        data = resp.json()

    import json

    raw_json = json.dumps(data)

    hourly = _parse_hourly(data["hourly"], source)

    return WeatherData(
        latitude=data["latitude"],
        longitude=data["longitude"],
        source=source,
        hourly=hourly,
        raw_json=raw_json,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_weather_service.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/nightcrate/services/weather.py backend/tests/test_weather_service.py
git commit -m "feat: add Open-Meteo weather client service (forecast + archive)"
```

---

## Task 7: Weather API Router + Pydantic Models

**Files:**
- Create: `backend/src/nightcrate/api/weather_models.py`
- Create: `backend/src/nightcrate/api/weather.py`
- Modify: `backend/src/nightcrate/main.py`
- Create: `backend/tests/test_weather_api.py`

- [ ] **Step 1: Write the Pydantic models**

Create file `backend/src/nightcrate/api/weather_models.py`:

```python
"""Pydantic models for the weather forecast API."""

from pydantic import BaseModel


class HourlyWeatherResponse(BaseModel):
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
    # Computed scores (0–100, higher = better)
    sky_clarity: int
    seeing_score: int
    wind_calm: int
    dryness: int
    # Astronomy
    moon_altitude_deg: float | None
    darkness_category: str | None


class DailySummaryResponse(BaseModel):
    date: str  # YYYY-MM-DD
    # Scores (0–100, higher = better)
    imaging_quality: int
    imaging_quality_label: str  # Excellent / Good / Marginal / Poor
    sky_clarity: int
    seeing_score: int
    wind_calm: int
    dryness: int
    moon_score: int
    # Astronomy
    sunset: str  # HH:MM local
    sunrise: str  # HH:MM local
    darkness_hours: float
    moonless_dark_hours: float
    moon_illumination_pct: float
    moon_phase_name: str
    # Cloud layer breakdown
    avg_cloud_cover_pct: float
    avg_cloud_low_pct: float
    avg_cloud_mid_pct: float
    avg_cloud_high_pct: float


class ForecastResponse(BaseModel):
    location_id: int
    location_name: str
    latitude: float
    longitude: float
    timezone: str
    moon_included: bool
    days: list[DailySummaryResponse]


class HourlyDetailResponse(BaseModel):
    date: str
    location_id: int
    location_name: str
    sunset: str
    sunrise: str
    hours: list[HourlyWeatherResponse]


class MethodologyResponse(BaseModel):
    text: str
```

- [ ] **Step 2: Write the failing API tests**

Create file `backend/tests/test_weather_api.py`:

```python
"""Integration tests for weather API endpoints.

Uses mocked Open-Meteo responses to avoid real HTTP calls.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
async def location_id(client: AsyncClient) -> int:
    """Create a test location and return its ID."""
    resp = await client.post(
        "/api/locations",
        json={
            "name": "Borrego Springs",
            "latitude": 33.2558,
            "longitude": -116.3753,
            "elevation_m": 236,
            "timezone": "America/Los_Angeles",
            "bortle_class": 2,
        },
    )
    assert resp.status_code == 201 or resp.status_code == 200
    return resp.json()["id"]


class TestForecastEndpoint:
    @patch("nightcrate.api.weather._fetch_or_cached")
    async def test_forecast_returns_days(self, mock_fetch, client, location_id):
        # Build a minimal mock WeatherData
        from nightcrate.services.weather import HourlyWeather, WeatherData

        hours = []
        for h in range(24 * 7):  # 7 days of hourly data
            hours.append(
                HourlyWeather(
                    time=f"2026-04-14T{h % 24:02d}:00",
                    temperature_c=10.0,
                    dew_point_c=2.0,
                    humidity_pct=40.0,
                    cloud_cover_pct=15.0,
                    cloud_cover_low_pct=5.0,
                    cloud_cover_mid_pct=5.0,
                    cloud_cover_high_pct=5.0,
                    wind_speed_kmh=8.0,
                    wind_direction_deg=180.0,
                    wind_gusts_kmh=12.0,
                    visibility_m=20000.0,
                    wind_speed_200hpa_kmh=30.0,
                    wind_speed_300hpa_kmh=22.0,
                    wind_speed_500hpa_kmh=12.0,
                    geopotential_200hpa_m=11800.0,
                    geopotential_300hpa_m=9200.0,
                    geopotential_500hpa_m=5500.0,
                )
            )

        mock_fetch.return_value = WeatherData(
            latitude=33.26,
            longitude=-116.38,
            source="forecast",
            hourly=hours,
            raw_json="{}",
        )

        resp = await client.get(f"/api/weather/forecast?location_id={location_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "days" in data
        assert data["location_id"] == location_id
        assert data["moon_included"] is True

    @patch("nightcrate.api.weather._fetch_or_cached")
    async def test_forecast_moon_toggle(self, mock_fetch, client, location_id):
        from nightcrate.services.weather import HourlyWeather, WeatherData

        hours = [
            HourlyWeather(
                time="2026-04-14T22:00",
                temperature_c=10.0,
                dew_point_c=2.0,
                humidity_pct=40.0,
                cloud_cover_pct=15.0,
                cloud_cover_low_pct=5.0,
                cloud_cover_mid_pct=5.0,
                cloud_cover_high_pct=5.0,
                wind_speed_kmh=8.0,
                wind_direction_deg=180.0,
                wind_gusts_kmh=12.0,
                visibility_m=20000.0,
                wind_speed_200hpa_kmh=30.0,
                wind_speed_300hpa_kmh=22.0,
                wind_speed_500hpa_kmh=12.0,
                geopotential_200hpa_m=11800.0,
                geopotential_300hpa_m=9200.0,
                geopotential_500hpa_m=5500.0,
            )
        ] * 168

        mock_fetch.return_value = WeatherData(
            latitude=33.26, longitude=-116.38, source="forecast",
            hourly=hours, raw_json="{}",
        )

        resp = await client.get(
            f"/api/weather/forecast?location_id={location_id}&include_moon=false"
        )
        assert resp.status_code == 200
        assert resp.json()["moon_included"] is False

    async def test_forecast_no_location(self, client):
        resp = await client.get("/api/weather/forecast?location_id=9999")
        assert resp.status_code == 404


class TestMethodologyEndpoint:
    async def test_methodology_returns_text(self, client):
        resp = await client.get("/api/weather/methodology")
        assert resp.status_code == 200
        data = resp.json()
        assert "Sky clarity" in data["text"]
        assert "40%" in data["text"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_weather_api.py -v -x`
Expected: FAIL — module not found

- [ ] **Step 4: Implement the weather API router**

Create file `backend/src/nightcrate/api/weather.py`:

```python
"""Weather forecast API endpoints."""

import json
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from nightcrate.api.weather_models import (
    DailySummaryResponse,
    ForecastResponse,
    HourlyDetailResponse,
    HourlyWeatherResponse,
    MethodologyResponse,
)
from nightcrate.core.config import get_settings
from nightcrate.db.session import get_db
from nightcrate.services.astronomy import compute_hourly_astro, compute_night_summary
from nightcrate.services.imaging_quality import (
    METHODOLOGY,
    ImagingQualityInput,
    compute_imaging_quality,
)
from nightcrate.services.seeing import estimate_seeing_surface, estimate_seeing_wind_shear
from nightcrate.services.weather import WeatherData, fetch_weather

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/weather", tags=["Weather"])


async def _get_location(location_id: int) -> dict:
    """Fetch a location by ID or raise 404."""
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT * FROM location WHERE id = ?", (location_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Location not found")
        return dict(row)


async def _fetch_or_cached(
    location_id: int,
    latitude: float,
    longitude: float,
    timezone_str: str,
    source: str = "forecast",
    start_date: str | None = None,
    end_date: str | None = None,
) -> WeatherData:
    """Fetch weather data, using cache if available and fresh."""
    settings = await get_settings()
    ttl_hours = settings.weather_cache_ttl_hours

    # Check cache
    async with get_db() as conn:
        if source == "forecast":
            cursor = await conn.execute(
                """SELECT response_json, fetched_at FROM weather_cache
                   WHERE location_id = ? AND source = 'forecast'
                   ORDER BY fetched_at DESC LIMIT 1""",
                (location_id,),
            )
        else:
            cursor = await conn.execute(
                """SELECT response_json, fetched_at FROM weather_cache
                   WHERE location_id = ? AND source = 'archive'
                   AND start_date = ? AND end_date = ?
                   ORDER BY fetched_at DESC LIMIT 1""",
                (location_id, start_date, end_date),
            )

        row = await cursor.fetchone()
        if row:
            fetched_at = datetime.fromisoformat(row["fetched_at"]).replace(
                tzinfo=timezone.utc
            )
            age_hours = (
                datetime.now(timezone.utc) - fetched_at
            ).total_seconds() / 3600
            if age_hours < ttl_hours:
                from nightcrate.services.weather import WeatherData, _parse_hourly

                data = json.loads(row["response_json"])
                hourly = _parse_hourly(data["hourly"], source)
                return WeatherData(
                    latitude=data["latitude"],
                    longitude=data["longitude"],
                    source=source,
                    hourly=hourly,
                    raw_json=row["response_json"],
                )

    # Cache miss — fetch from API
    result = await fetch_weather(
        latitude=latitude,
        longitude=longitude,
        timezone_str=timezone_str,
        source=source,
        start_date=start_date,
        end_date=end_date,
    )

    # Store in cache
    async with get_db() as conn:
        await conn.execute(
            """INSERT OR REPLACE INTO weather_cache
               (location_id, source, start_date, end_date, response_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                location_id,
                source,
                start_date or "",
                end_date or "",
                result.raw_json,
            ),
        )
        await conn.commit()

    return result


def _compute_hourly_seeing(hours: list, idx: int) -> int:
    """Compute seeing score for a single hour. Uses wind-shear model if
    pressure data is available, otherwise falls back to surface model."""
    h = hours[idx]
    prev_temp = hours[idx - 1].temperature_c if idx > 0 else None

    if h.wind_speed_200hpa_kmh is not None:
        return estimate_seeing_wind_shear(
            wind_speed_200hpa_kmh=h.wind_speed_200hpa_kmh,
            wind_speed_300hpa_kmh=h.wind_speed_300hpa_kmh,
            wind_speed_500hpa_kmh=h.wind_speed_500hpa_kmh,
            geopotential_200hpa_m=h.geopotential_200hpa_m,
            geopotential_300hpa_m=h.geopotential_300hpa_m,
            geopotential_500hpa_m=h.geopotential_500hpa_m,
            temperature_c=h.temperature_c,
            dew_point_c=h.dew_point_c,
            humidity_pct=h.humidity_pct,
            wind_speed_surface_kmh=h.wind_speed_kmh,
            prev_temperature_c=prev_temp,
        )
    else:
        return estimate_seeing_surface(
            temperature_c=h.temperature_c,
            dew_point_c=h.dew_point_c,
            humidity_pct=h.humidity_pct,
            wind_speed_kmh=h.wind_speed_kmh,
            prev_temperature_c=prev_temp,
        )


def _group_hours_by_date(hours: list) -> dict[str, list]:
    """Group hourly weather data by date string."""
    groups: dict[str, list] = {}
    for h in hours:
        day = h.time[:10]  # YYYY-MM-DD
        groups.setdefault(day, []).append(h)
    return groups


@router.get("/forecast", response_model=ForecastResponse)
async def get_forecast(
    location_id: int = Query(..., description="Location ID"),
    include_moon: bool = Query(True, description="Include moon penalty in quality score"),
):
    """Get 7-day weather forecast with imaging quality scores for a location."""
    loc = await _get_location(location_id)
    settings = await get_settings()

    # Use setting as default, but allow query param override
    moon_enabled = include_moon and settings.weather_moon_penalty

    weather = await _fetch_or_cached(
        location_id=loc["id"],
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        timezone_str=loc["timezone"],
        source="forecast",
    )

    grouped = _group_hours_by_date(weather.hourly)
    days = []

    for day_str in sorted(grouped.keys())[:7]:
        day_hours = grouped[day_str]
        day_date = date.fromisoformat(day_str)

        # Night summary (astronomy)
        try:
            night = compute_night_summary(
                latitude=loc["latitude"],
                longitude=loc["longitude"],
                elevation_m=loc["elevation_m"],
                night_date=day_date,
                timezone_str=loc["timezone"],
            )
        except (AssertionError, Exception):
            # Polar conditions or computation failure — skip this day
            continue

        # Average weather during darkness hours
        # Filter hours to nighttime (rough: after 18:00 or before 06:00 local)
        hour_ints = [int(h.time[11:13]) for h in day_hours]
        night_hours = [
            h for h, hr in zip(day_hours, hour_ints) if hr >= 18 or hr <= 6
        ]
        if not night_hours:
            night_hours = day_hours  # fallback to full day

        avg_cloud = sum(h.cloud_cover_pct for h in night_hours) / len(night_hours)
        avg_cloud_low = sum(h.cloud_cover_low_pct for h in night_hours) / len(night_hours)
        avg_cloud_mid = sum(h.cloud_cover_mid_pct for h in night_hours) / len(night_hours)
        avg_cloud_high = sum(h.cloud_cover_high_pct for h in night_hours) / len(night_hours)
        avg_wind = sum(h.wind_speed_kmh for h in night_hours) / len(night_hours)
        avg_humidity = sum(h.humidity_pct for h in night_hours) / len(night_hours)

        # Average seeing for the night
        all_hours = weather.hourly
        seeing_scores = []
        for i, h in enumerate(all_hours):
            if h in night_hours:
                seeing_scores.append(_compute_hourly_seeing(all_hours, i))
        avg_seeing = sum(seeing_scores) / len(seeing_scores) if seeing_scores else 50

        # Imaging quality composite
        quality = compute_imaging_quality(
            ImagingQualityInput(
                cloud_cover_pct=avg_cloud,
                seeing_score=round(avg_seeing),
                wind_speed_kmh=avg_wind,
                humidity_pct=avg_humidity,
                moonless_dark_hours=night.moonless_dark_hours,
                darkness_hours=night.darkness_hours,
                moon_illumination_pct=night.moon.illumination_pct,
            ),
            include_moon=moon_enabled,
        )

        import zoneinfo

        tz = zoneinfo.ZoneInfo(loc["timezone"])
        sunset_local = night.sunset.astimezone(tz).strftime("%H:%M")
        sunrise_local = night.sunrise.astimezone(tz).strftime("%H:%M")

        days.append(
            DailySummaryResponse(
                date=day_str,
                imaging_quality=quality.overall,
                imaging_quality_label=quality.label,
                sky_clarity=quality.sky_clarity,
                seeing_score=quality.seeing,
                wind_calm=quality.wind_calm,
                dryness=quality.dryness,
                moon_score=quality.moon_score,
                sunset=sunset_local,
                sunrise=sunrise_local,
                darkness_hours=night.darkness_hours,
                moonless_dark_hours=night.moonless_dark_hours,
                moon_illumination_pct=night.moon.illumination_pct,
                moon_phase_name=night.moon.phase_name,
                avg_cloud_cover_pct=round(avg_cloud, 1),
                avg_cloud_low_pct=round(avg_cloud_low, 1),
                avg_cloud_mid_pct=round(avg_cloud_mid, 1),
                avg_cloud_high_pct=round(avg_cloud_high, 1),
            )
        )

    return ForecastResponse(
        location_id=loc["id"],
        location_name=loc["name"],
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        timezone=loc["timezone"],
        moon_included=moon_enabled,
        days=days,
    )


@router.get("/hourly", response_model=HourlyDetailResponse)
async def get_hourly_detail(
    location_id: int = Query(..., description="Location ID"),
    date: str = Query(..., description="Date YYYY-MM-DD"),
):
    """Get detailed hourly weather + astronomy data for a specific night."""
    loc = await _get_location(location_id)
    day_date = __import__("datetime").date.fromisoformat(date)

    weather = await _fetch_or_cached(
        location_id=loc["id"],
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        timezone_str=loc["timezone"],
        source="forecast",
    )

    # Get astronomy data for each hour
    astro_hours = compute_hourly_astro(
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        elevation_m=loc["elevation_m"],
        night_date=day_date,
        timezone_str=loc["timezone"],
    )

    # Build a lookup of astronomy data by hour
    astro_by_hour = {}
    for ah in astro_hours:
        key = ah.time_local  # HH:MM
        astro_by_hour[key] = ah

    # Filter weather hours for the requested date (evening) and next day (morning)
    grouped = _group_hours_by_date(weather.hourly)
    day_hours = grouped.get(date, [])

    all_hours = weather.hourly
    result_hours = []

    for i, h in enumerate(all_hours):
        if h not in day_hours:
            continue

        seeing = _compute_hourly_seeing(all_hours, i)
        hour_str = h.time[11:16]  # HH:MM
        astro = astro_by_hour.get(hour_str)

        result_hours.append(
            HourlyWeatherResponse(
                time=h.time,
                temperature_c=h.temperature_c,
                dew_point_c=h.dew_point_c,
                humidity_pct=h.humidity_pct,
                cloud_cover_pct=h.cloud_cover_pct,
                cloud_cover_low_pct=h.cloud_cover_low_pct,
                cloud_cover_mid_pct=h.cloud_cover_mid_pct,
                cloud_cover_high_pct=h.cloud_cover_high_pct,
                wind_speed_kmh=h.wind_speed_kmh,
                wind_direction_deg=h.wind_direction_deg,
                wind_gusts_kmh=h.wind_gusts_kmh,
                visibility_m=h.visibility_m,
                sky_clarity=round(max(0, 100 - h.cloud_cover_pct)),
                seeing_score=seeing,
                wind_calm=round(max(0, min(100, 100 - h.wind_speed_kmh * 3))),
                dryness=round(max(0, 100 - h.humidity_pct)),
                moon_altitude_deg=astro.moon_altitude_deg if astro else None,
                darkness_category=astro.darkness_category if astro else None,
            )
        )

    try:
        night = compute_night_summary(
            latitude=loc["latitude"],
            longitude=loc["longitude"],
            elevation_m=loc["elevation_m"],
            night_date=day_date,
            timezone_str=loc["timezone"],
        )
        import zoneinfo

        tz = zoneinfo.ZoneInfo(loc["timezone"])
        sunset_local = night.sunset.astimezone(tz).strftime("%H:%M")
        sunrise_local = night.sunrise.astimezone(tz).strftime("%H:%M")
    except Exception:
        sunset_local = ""
        sunrise_local = ""

    return HourlyDetailResponse(
        date=date,
        location_id=loc["id"],
        location_name=loc["name"],
        sunset=sunset_local,
        sunrise=sunrise_local,
        hours=result_hours,
    )


@router.get("/methodology", response_model=MethodologyResponse)
async def get_methodology():
    """Get a human-readable description of how imaging quality scores are calculated."""
    return MethodologyResponse(text=METHODOLOGY)
```

- [ ] **Step 5: Register the router in main.py**

In `backend/src/nightcrate/main.py`, add the import and router registration:

Add to imports (after the locations import):
```python
from nightcrate.api import (
    aberration,
    admin,
    diagnostics,
    equipment,
    files,
    images,
    locations,
    settings,
    weather,
)
```

Add the openapi_tags entry (after "Locations" and before "Settings"):
```python
    {
        "name": "Weather",
        "description": (
            "Astronomy weather forecast for imaging session planning. "
            "Provides 7-day overview with imaging quality scores, detailed "
            "hourly breakdowns, cloud layer analysis, seeing estimates, "
            "and moon/twilight data. Powered by Open-Meteo (weather) "
            "and astropy (astronomy)."
        ),
    },
```

Add router registration (after `locations.router`):
```python
app.include_router(weather.router)
```

Add weather cache purge to the lifespan (after aberration cache purge):
```python
        # Purge stale weather cache entries
        try:
            async with get_db() as conn:
                await conn.execute(
                    "DELETE FROM weather_cache WHERE fetched_at < datetime('now', ?)",
                    (f"-{ttl_hours * 2} hours",),  # Keep slightly longer than TTL
                )
                await conn.commit()
        except Exception:
            pass  # Non-fatal
```

Note: `ttl_hours` uses `app_settings.weather_cache_ttl_hours` — read it from the settings that were already loaded above.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_weather_api.py -v -x`
Expected: PASS

- [ ] **Step 7: Run full test suite**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest -v -x`
Expected: PASS (all existing tests still green)

- [ ] **Step 8: Commit**

```bash
git add backend/src/nightcrate/api/weather_models.py backend/src/nightcrate/api/weather.py backend/src/nightcrate/main.py backend/tests/test_weather_api.py
git commit -m "feat: add weather forecast API with caching and quality scores"
```

---

## Task 8: Frontend — API Client + TypeScript Types

**Files:**
- Create: `frontend/src/api/weather.ts`

- [ ] **Step 1: Create the weather API client**

Create file `frontend/src/api/weather.ts`:

```typescript
import { apiFetch } from "./client";

export interface HourlyWeather {
  time: string;
  temperature_c: number;
  dew_point_c: number;
  humidity_pct: number;
  cloud_cover_pct: number;
  cloud_cover_low_pct: number;
  cloud_cover_mid_pct: number;
  cloud_cover_high_pct: number;
  wind_speed_kmh: number;
  wind_direction_deg: number;
  wind_gusts_kmh: number;
  visibility_m: number | null;
  sky_clarity: number;
  seeing_score: number;
  wind_calm: number;
  dryness: number;
  moon_altitude_deg: number | null;
  darkness_category: string | null;
}

export interface DailySummary {
  date: string;
  imaging_quality: number;
  imaging_quality_label: string;
  sky_clarity: number;
  seeing_score: number;
  wind_calm: number;
  dryness: number;
  moon_score: number;
  sunset: string;
  sunrise: string;
  darkness_hours: number;
  moonless_dark_hours: number;
  moon_illumination_pct: number;
  moon_phase_name: string;
  avg_cloud_cover_pct: number;
  avg_cloud_low_pct: number;
  avg_cloud_mid_pct: number;
  avg_cloud_high_pct: number;
}

export interface ForecastResponse {
  location_id: number;
  location_name: string;
  latitude: number;
  longitude: number;
  timezone: string;
  moon_included: boolean;
  days: DailySummary[];
}

export interface HourlyDetailResponse {
  date: string;
  location_id: number;
  location_name: string;
  sunset: string;
  sunrise: string;
  hours: HourlyWeather[];
}

export interface Methodology {
  text: string;
}

export const fetchForecast = (locationId: number, includeMoon = true) =>
  apiFetch<ForecastResponse>(
    `/weather/forecast?location_id=${locationId}&include_moon=${includeMoon}`
  );

export const fetchHourlyDetail = (locationId: number, date: string) =>
  apiFetch<HourlyDetailResponse>(
    `/weather/hourly?location_id=${locationId}&date=${date}`
  );

export const fetchMethodology = () =>
  apiFetch<Methodology>("/weather/methodology");
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/weather.ts
git commit -m "feat: add weather forecast TypeScript API client"
```

---

## Task 9: Frontend — QualityBadge + MoonPhaseIcon Components

**Files:**
- Create: `frontend/src/components/weather/QualityBadge.tsx`
- Create: `frontend/src/components/weather/MoonPhaseIcon.tsx`

- [ ] **Step 1: Create the QualityBadge component**

Create file `frontend/src/components/weather/QualityBadge.tsx`:

```tsx
import { Box, Tooltip, Typography } from "@mui/material";

/**
 * Displays a 0–100 quality score as a badge with:
 * - Single blue hue, brightness = quality (bright = good, dark = bad)
 * - Text label (Excellent / Good / Marginal / Poor)
 * - Numeric score
 * - Optional metric name
 */

interface QualityBadgeProps {
  score: number; // 0–100
  label?: string; // Excellent / Good / Marginal / Poor
  metricName?: string; // e.g. "Sky Clarity"
  size?: "small" | "medium" | "large";
  showLabel?: boolean;
  tooltip?: string;
}

function scoreToLabel(score: number): string {
  if (score >= 80) return "Excellent";
  if (score >= 55) return "Good";
  if (score >= 30) return "Marginal";
  return "Poor";
}

/**
 * Map a 0–100 score to a blue hue with brightness variation.
 * 100 = bright, saturated blue; 0 = dark, desaturated blue-gray.
 *
 * Uses HSL: hue fixed at 215 (slate blue matching theme),
 * saturation 20–70%, lightness 25–65%.
 */
function scoreToBackground(score: number): string {
  const t = score / 100; // 0–1
  const saturation = 20 + t * 50; // 20% → 70%
  const lightness = 25 + t * 40; // 25% → 65%
  return `hsl(215, ${saturation}%, ${lightness}%)`;
}

function scoreToTextColor(score: number): string {
  // Light text for dark backgrounds, dark text for light backgrounds
  return score >= 60 ? "#1a1c20" : "#e2e0dd";
}

const sizes = {
  small: { width: 40, height: 40, fontSize: "0.85rem", labelSize: "0.6rem" },
  medium: { width: 56, height: 56, fontSize: "1.1rem", labelSize: "0.65rem" },
  large: { width: 72, height: 72, fontSize: "1.4rem", labelSize: "0.7rem" },
};

export default function QualityBadge({
  score,
  label,
  metricName,
  size = "medium",
  showLabel = true,
  tooltip,
}: QualityBadgeProps) {
  const displayLabel = label || scoreToLabel(score);
  const s = sizes[size];
  const bg = scoreToBackground(score);
  const textColor = scoreToTextColor(score);

  const badge = (
    <Box sx={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: 0.25 }}>
      {metricName && (
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: s.labelSize }}>
          {metricName}
        </Typography>
      )}
      <Box
        sx={{
          width: s.width,
          height: s.height,
          borderRadius: "50%",
          backgroundColor: bg,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transition: "background-color 0.3s",
        }}
      >
        <Typography sx={{ fontSize: s.fontSize, fontWeight: 600, color: textColor }}>
          {score}
        </Typography>
      </Box>
      {showLabel && (
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: s.labelSize }}>
          {displayLabel}
        </Typography>
      )}
    </Box>
  );

  if (tooltip) {
    return <Tooltip title={tooltip}>{badge}</Tooltip>;
  }
  return badge;
}
```

- [ ] **Step 2: Create the MoonPhaseIcon component**

Create file `frontend/src/components/weather/MoonPhaseIcon.tsx`:

```tsx
import { SvgIcon, type SvgIconProps } from "@mui/material";

/**
 * SVG moon phase icon. Maps phase name to a visual representation.
 * Uses a simple circle + shadow overlay approach.
 */

interface MoonPhaseIconProps extends SvgIconProps {
  phaseName: string;
  illuminationPct?: number;
}

/**
 * Draw a moon phase using a circle (lit side) with an overlay ellipse (shadow).
 * The ellipse x-radius controls how much is shadowed.
 */
export default function MoonPhaseIcon({
  phaseName,
  illuminationPct,
  ...props
}: MoonPhaseIconProps) {
  // Map phase name to shadow parameters
  // cx=12, cy=12, r=10 for the moon circle
  const phase = phaseName.toLowerCase();

  // Determine shadow ellipse rx (0 = full moon, 10 = new moon)
  // and which side is lit
  let shadowRx: number;
  let shadowOnRight: boolean;

  if (phase.includes("new")) {
    shadowRx = 10;
    shadowOnRight = false;
  } else if (phase.includes("full")) {
    shadowRx = 0;
    shadowOnRight = false;
  } else if (phase.includes("first quarter")) {
    shadowRx = 0;
    shadowOnRight = true; // left half dark
  } else if (phase.includes("last quarter")) {
    shadowRx = 0;
    shadowOnRight = false; // right half dark
  } else if (phase.includes("waxing crescent")) {
    shadowRx = 7;
    shadowOnRight = true;
  } else if (phase.includes("waxing gibbous")) {
    shadowRx = 5;
    shadowOnRight = false;
  } else if (phase.includes("waning gibbous")) {
    shadowRx = 5;
    shadowOnRight = true;
  } else if (phase.includes("waning crescent")) {
    shadowRx = 7;
    shadowOnRight = false;
  } else {
    // Fallback: use illumination if available
    shadowRx = illuminationPct != null ? 10 - (illuminationPct / 100) * 10 : 5;
    shadowOnRight = false;
  }

  return (
    <SvgIcon {...props} viewBox="0 0 24 24">
      {/* Moon circle */}
      <circle cx="12" cy="12" r="10" fill="#c8ccd0" />
      {/* Shadow overlay — uses clip path to keep within circle */}
      <clipPath id="moon-clip">
        <circle cx="12" cy="12" r="10" />
      </clipPath>
      {phase.includes("first quarter") ? (
        <rect
          x="2"
          y="2"
          width="10"
          height="20"
          fill="#2a2d32"
          clipPath="url(#moon-clip)"
        />
      ) : phase.includes("last quarter") ? (
        <rect
          x="12"
          y="2"
          width="10"
          height="20"
          fill="#2a2d32"
          clipPath="url(#moon-clip)"
        />
      ) : shadowRx > 0 ? (
        <ellipse
          cx={shadowOnRight ? 12 + (10 - shadowRx) : 12 - (10 - shadowRx)}
          cy="12"
          rx={shadowRx}
          ry="10"
          fill="#2a2d32"
          clipPath="url(#moon-clip)"
        />
      ) : null}
    </SvgIcon>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/weather/QualityBadge.tsx frontend/src/components/weather/MoonPhaseIcon.tsx
git commit -m "feat: add QualityBadge and MoonPhaseIcon components"
```

---

## Task 10: Frontend — LocationSelector + MethodologyInfo Components

**Files:**
- Create: `frontend/src/components/weather/LocationSelector.tsx`
- Create: `frontend/src/components/weather/MethodologyInfo.tsx`

- [ ] **Step 1: Create the LocationSelector component**

Create file `frontend/src/components/weather/LocationSelector.tsx`:

```tsx
import {
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  type SelectChangeEvent,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { fetchLocations, type Location } from "../../api/locations";

interface LocationSelectorProps {
  selectedId: number | null;
  onChange: (locationId: number) => void;
}

export default function LocationSelector({
  selectedId,
  onChange,
}: LocationSelectorProps) {
  const { data: locations = [] } = useQuery({
    queryKey: ["locations"],
    queryFn: fetchLocations,
  });

  const handleChange = (event: SelectChangeEvent<number>) => {
    onChange(event.target.value as number);
  };

  // Auto-select default location if none selected
  const defaultLoc = locations.find((l) => l.is_default);
  const effectiveId = selectedId ?? defaultLoc?.id ?? locations[0]?.id ?? "";

  return (
    <FormControl size="small" sx={{ minWidth: 220 }}>
      <InputLabel>Location</InputLabel>
      <Select
        value={effectiveId as number}
        onChange={handleChange}
        label="Location"
      >
        {locations.map((loc) => (
          <MenuItem key={loc.id} value={loc.id}>
            {loc.name}
            {loc.is_default ? " (default)" : ""}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
```

- [ ] **Step 2: Create the MethodologyInfo component**

Create file `frontend/src/components/weather/MethodologyInfo.tsx`:

```tsx
import { ExpandMore as ExpandMoreIcon, Info as InfoIcon } from "@mui/icons-material";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { fetchMethodology } from "../../api/weather";

/**
 * Expandable panel explaining how imaging quality scores are calculated.
 * Fetches methodology text from the backend so it stays in sync with
 * the actual algorithm.
 */
export default function MethodologyInfo() {
  const { data } = useQuery({
    queryKey: ["weather-methodology"],
    queryFn: fetchMethodology,
    staleTime: Infinity, // methodology doesn't change at runtime
  });

  if (!data) return null;

  // Parse the markdown-like text into simple paragraphs
  const paragraphs = data.text.split("\n").filter((line) => line.trim());

  return (
    <Accordion
      disableGutters
      elevation={0}
      sx={{
        backgroundColor: "transparent",
        "&::before": { display: "none" },
      }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <InfoIcon fontSize="small" color="action" />
          <Typography variant="body2" color="text.secondary">
            How are scores calculated?
          </Typography>
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Box sx={{ maxWidth: 600 }}>
          {paragraphs.map((para, i) => (
            <Typography
              key={i}
              variant="body2"
              color="text.secondary"
              sx={{ mb: 1 }}
            >
              {para}
            </Typography>
          ))}
        </Box>
      </AccordionDetails>
    </Accordion>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/weather/LocationSelector.tsx frontend/src/components/weather/MethodologyInfo.tsx
git commit -m "feat: add LocationSelector and MethodologyInfo components"
```

---

## Task 11: Frontend — DailyCard Component

**Files:**
- Create: `frontend/src/components/weather/DailyCard.tsx`

- [ ] **Step 1: Create the DailyCard component**

Create file `frontend/src/components/weather/DailyCard.tsx`:

```tsx
import {
  Box,
  Card,
  CardActionArea,
  CardContent,
  Divider,
  Typography,
} from "@mui/material";

import type { DailySummary } from "../../api/weather";
import MoonPhaseIcon from "./MoonPhaseIcon";
import QualityBadge from "./QualityBadge";

interface DailyCardProps {
  day: DailySummary;
  selected: boolean;
  onClick: () => void;
}

function formatDate(dateStr: string): { dayName: string; monthDay: string } {
  const d = new Date(dateStr + "T12:00:00"); // noon to avoid timezone shift
  const dayName = d.toLocaleDateString("en-US", { weekday: "short" });
  const monthDay = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return { dayName, monthDay };
}

export default function DailyCard({ day, selected, onClick }: DailyCardProps) {
  const { dayName, monthDay } = formatDate(day.date);

  return (
    <Card
      elevation={selected ? 4 : 1}
      sx={{
        minWidth: 140,
        maxWidth: 160,
        border: selected ? 2 : 1,
        borderColor: selected ? "primary.main" : "divider",
        transition: "all 0.2s",
      }}
    >
      <CardActionArea onClick={onClick}>
        <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
          {/* Date header */}
          <Typography variant="body2" fontWeight={600} textAlign="center">
            {dayName}
          </Typography>
          <Typography variant="caption" color="text.secondary" textAlign="center" display="block">
            {monthDay}
          </Typography>

          <Box sx={{ display: "flex", justifyContent: "center", my: 1 }}>
            <QualityBadge
              score={day.imaging_quality}
              label={day.imaging_quality_label}
              size="large"
            />
          </Box>

          <Divider sx={{ my: 1 }} />

          {/* Metric rows */}
          <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
            <MetricRow label="Sky Clarity" value={day.sky_clarity} />
            <MetricRow label="Seeing" value={day.seeing_score} />
            <MetricRow label="Wind Calm" value={day.wind_calm} />
          </Box>

          <Divider sx={{ my: 1 }} />

          {/* Moon + darkness */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.5 }}>
            <MoonPhaseIcon
              phaseName={day.moon_phase_name}
              illuminationPct={day.moon_illumination_pct}
              sx={{ fontSize: 18 }}
            />
            <Typography variant="caption" color="text.secondary">
              {Math.round(day.moon_illumination_pct)}%
            </Typography>
          </Box>

          <Typography variant="caption" color="text.secondary" display="block">
            Moonless: {day.moonless_dark_hours.toFixed(1)}h
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block">
            Dark: {day.darkness_hours.toFixed(1)}h
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block">
            Sunset {day.sunset} / Rise {day.sunrise}
          </Typography>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}

function MetricRow({ label, value }: { label: string; value: number }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <QualityBadge score={value} size="small" showLabel={false} />
    </Box>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/weather/DailyCard.tsx
git commit -m "feat: add DailyCard component for 7-day weather overview"
```

---

## Task 12: Frontend — HourlyTimeline Component

**Files:**
- Create: `frontend/src/components/weather/HourlyTimeline.tsx`

This is the most complex frontend component — a D3-rendered timeline chart showing darkness bands, cloud cover layers, moon altitude, seeing score, and wind.

- [ ] **Step 1: Create the HourlyTimeline component**

Create file `frontend/src/components/weather/HourlyTimeline.tsx`:

```tsx
import { Box, Typography } from "@mui/material";
import { useEffect, useRef } from "react";
import * as d3 from "d3";

import type { HourlyWeather } from "../../api/weather";

interface HourlyTimelineProps {
  hours: HourlyWeather[];
  sunset: string;
  sunrise: string;
}

const MARGIN = { top: 20, right: 40, bottom: 30, left: 50 };
const ROW_HEIGHT = 32;
const LABEL_WIDTH = 100;

// Darkness category → background opacity (within blue hue)
const DARKNESS_OPACITY: Record<string, number> = {
  daylight: 0.0,
  civil_twilight: 0.15,
  nautical_twilight: 0.3,
  astronomical_twilight: 0.5,
  night: 0.7,
};

/**
 * Map a 0–100 goodness score to a blue brightness.
 * Returns an HSL color string.
 */
function scoreToCellColor(score: number): string {
  const t = score / 100;
  const lightness = 20 + t * 50; // 20% (dark/bad) → 70% (bright/good)
  const saturation = 15 + t * 45; // 15% → 60%
  return `hsl(215, ${saturation}%, ${lightness}%)`;
}

function scoreToTextColor(score: number): string {
  return score >= 55 ? "#1a1c20" : "#e2e0dd";
}

export default function HourlyTimeline({
  hours,
  sunset,
  sunrise,
}: HourlyTimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || hours.length === 0) return;

    const container = containerRef.current;
    // Clear previous render
    d3.select(container).selectAll("*").remove();

    const timeLabels = hours.map((h) => h.time.slice(11, 16)); // HH:MM
    const cellWidth = Math.max(36, Math.min(50, (container.clientWidth - LABEL_WIDTH) / hours.length));
    const totalWidth = LABEL_WIDTH + cellWidth * hours.length + MARGIN.right;

    const rows = [
      { label: "Darkness", key: "darkness" },
      { label: "Sky Clarity", key: "sky_clarity" },
      { label: "Seeing", key: "seeing_score" },
      { label: "Wind Calm", key: "wind_calm" },
      { label: "Cloud (total)", key: "cloud_total" },
      { label: "Cloud (high)", key: "cloud_high" },
      { label: "Cloud (mid)", key: "cloud_mid" },
      { label: "Cloud (low)", key: "cloud_low" },
      { label: "Moon Alt.", key: "moon_alt" },
    ];

    const totalHeight = MARGIN.top + rows.length * ROW_HEIGHT + MARGIN.bottom;

    const svg = d3
      .select(container)
      .append("svg")
      .attr("width", totalWidth)
      .attr("height", totalHeight);

    // Row labels
    rows.forEach((row, ri) => {
      svg
        .append("text")
        .attr("x", LABEL_WIDTH - 8)
        .attr("y", MARGIN.top + ri * ROW_HEIGHT + ROW_HEIGHT / 2)
        .attr("text-anchor", "end")
        .attr("dominant-baseline", "middle")
        .attr("font-size", "11px")
        .attr("fill", "currentColor")
        .text(row.label);
    });

    // Time labels (top)
    timeLabels.forEach((label, ci) => {
      if (ci % 2 === 0) {
        svg
          .append("text")
          .attr("x", LABEL_WIDTH + ci * cellWidth + cellWidth / 2)
          .attr("y", MARGIN.top - 6)
          .attr("text-anchor", "middle")
          .attr("font-size", "10px")
          .attr("fill", "currentColor")
          .text(label);
      }
    });

    // Data cells
    hours.forEach((h, ci) => {
      const x = LABEL_WIDTH + ci * cellWidth;

      rows.forEach((row, ri) => {
        const y = MARGIN.top + ri * ROW_HEIGHT;
        let score: number;
        let displayText: string;

        switch (row.key) {
          case "darkness": {
            const cat = h.darkness_category || "daylight";
            const opacity = DARKNESS_OPACITY[cat] ?? 0;
            svg
              .append("rect")
              .attr("x", x)
              .attr("y", y)
              .attr("width", cellWidth)
              .attr("height", ROW_HEIGHT)
              .attr("fill", `hsla(215, 50%, 30%, ${opacity})`)
              .attr("stroke", "rgba(128,128,128,0.15)")
              .attr("stroke-width", 0.5);
            // Label for night
            if (cat === "night") {
              svg
                .append("text")
                .attr("x", x + cellWidth / 2)
                .attr("y", y + ROW_HEIGHT / 2)
                .attr("text-anchor", "middle")
                .attr("dominant-baseline", "middle")
                .attr("font-size", "9px")
                .attr("fill", "#8eb0d8")
                .text("N");
            }
            return;
          }
          case "sky_clarity":
            score = h.sky_clarity;
            displayText = `${score}`;
            break;
          case "seeing_score":
            score = h.seeing_score;
            displayText = `${score}`;
            break;
          case "wind_calm":
            score = h.wind_calm;
            displayText = `${score}`;
            break;
          case "cloud_total":
            score = Math.round(100 - h.cloud_cover_pct);
            displayText = `${Math.round(h.cloud_cover_pct)}%`;
            break;
          case "cloud_high":
            score = Math.round(100 - h.cloud_cover_high_pct);
            displayText = `${Math.round(h.cloud_cover_high_pct)}%`;
            break;
          case "cloud_mid":
            score = Math.round(100 - h.cloud_cover_mid_pct);
            displayText = `${Math.round(h.cloud_cover_mid_pct)}%`;
            break;
          case "cloud_low":
            score = Math.round(100 - h.cloud_cover_low_pct);
            displayText = `${Math.round(h.cloud_cover_low_pct)}%`;
            break;
          case "moon_alt": {
            const alt = h.moon_altitude_deg;
            if (alt == null) {
              score = 50;
              displayText = "?";
            } else {
              // Moon below horizon = good (score 100), above = worse
              score = alt <= 0 ? 100 : Math.max(0, Math.round(100 - alt * 1.5));
              displayText = `${Math.round(alt)}°`;
            }
            break;
          }
          default:
            score = 50;
            displayText = "";
        }

        // Cell background
        svg
          .append("rect")
          .attr("x", x)
          .attr("y", y)
          .attr("width", cellWidth)
          .attr("height", ROW_HEIGHT)
          .attr("fill", scoreToCellColor(score))
          .attr("stroke", "rgba(128,128,128,0.15)")
          .attr("stroke-width", 0.5);

        // Cell text
        svg
          .append("text")
          .attr("x", x + cellWidth / 2)
          .attr("y", y + ROW_HEIGHT / 2)
          .attr("text-anchor", "middle")
          .attr("dominant-baseline", "middle")
          .attr("font-size", "10px")
          .attr("font-weight", 500)
          .attr("fill", scoreToTextColor(score))
          .text(displayText);
      });
    });
  }, [hours, sunset, sunrise]);

  if (hours.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
        Select a day to see hourly details.
      </Typography>
    );
  }

  return (
    <Box
      ref={containerRef}
      sx={{
        overflowX: "auto",
        overflowY: "hidden",
        width: "100%",
        "& svg": { display: "block", color: "text.primary" },
      }}
    />
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/weather/HourlyTimeline.tsx
git commit -m "feat: add HourlyTimeline D3 chart for hourly weather detail"
```

---

## Task 13: Frontend — WeatherPage + Routing + Navigation

**Files:**
- Create: `frontend/src/pages/WeatherPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`

- [ ] **Step 1: Create the WeatherPage**

Create file `frontend/src/pages/WeatherPage.tsx`:

```tsx
import { Box, Checkbox, FormControlLabel, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { fetchDefaultLocation } from "../api/locations";
import { fetchForecast, fetchHourlyDetail } from "../api/weather";
import DailyCard from "../components/weather/DailyCard";
import HourlyTimeline from "../components/weather/HourlyTimeline";
import LocationSelector from "../components/weather/LocationSelector";
import MethodologyInfo from "../components/weather/MethodologyInfo";
import { EasterEggWand } from "../components/EasterEggWand";

export default function WeatherPage() {
  const [locationId, setLocationId] = useState<number | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [includeMoon, setIncludeMoon] = useState(true);

  // Auto-select default location
  const { data: defaultLoc } = useQuery({
    queryKey: ["locations", "default"],
    queryFn: fetchDefaultLocation,
  });

  useEffect(() => {
    if (defaultLoc && locationId === null) {
      setLocationId(defaultLoc.id);
    }
  }, [defaultLoc, locationId]);

  const handleLocationChange = useCallback((id: number) => {
    setLocationId(id);
    setSelectedDate(null); // reset detail view on location change
  }, []);

  // Forecast query
  const {
    data: forecast,
    isLoading: forecastLoading,
    error: forecastError,
  } = useQuery({
    queryKey: ["weather-forecast", locationId, includeMoon],
    queryFn: () => fetchForecast(locationId!, includeMoon),
    enabled: locationId !== null,
  });

  // Auto-select first day
  useEffect(() => {
    if (forecast && forecast.days.length > 0 && selectedDate === null) {
      setSelectedDate(forecast.days[0].date);
    }
  }, [forecast, selectedDate]);

  // Hourly detail query
  const { data: hourlyDetail, isLoading: hourlyLoading } = useQuery({
    queryKey: ["weather-hourly", locationId, selectedDate],
    queryFn: () => fetchHourlyDetail(locationId!, selectedDate!),
    enabled: locationId !== null && selectedDate !== null,
  });

  return (
    <Box sx={{ p: 3, maxWidth: 1200 }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          mb: 3,
        }}
      >
        <Typography variant="h5">Weather Forecast</Typography>
        <EasterEggWand category="weather" />
      </Box>

      {/* Controls bar */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 3, flexWrap: "wrap" }}>
        <LocationSelector selectedId={locationId} onChange={handleLocationChange} />
        <FormControlLabel
          control={
            <Checkbox
              checked={includeMoon}
              onChange={(e) => setIncludeMoon(e.target.checked)}
              size="small"
            />
          }
          label={
            <Typography variant="body2">Include moon in quality score</Typography>
          }
        />
      </Box>

      {/* Error state */}
      {forecastError && (
        <Typography color="error" sx={{ mb: 2 }}>
          Failed to load forecast. Make sure you have at least one location configured.
        </Typography>
      )}

      {/* Loading state */}
      {forecastLoading && (
        <Typography color="text.secondary">Loading forecast...</Typography>
      )}

      {/* 7-day cards */}
      {forecast && (
        <Box sx={{ display: "flex", gap: 1.5, overflowX: "auto", pb: 2, mb: 3 }}>
          {forecast.days.map((day) => (
            <DailyCard
              key={day.date}
              day={day}
              selected={day.date === selectedDate}
              onClick={() => setSelectedDate(day.date)}
            />
          ))}
        </Box>
      )}

      {/* Hourly detail */}
      {selectedDate && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            Hourly Detail — {selectedDate}
          </Typography>
          {hourlyLoading ? (
            <Typography color="text.secondary">Loading hourly data...</Typography>
          ) : hourlyDetail ? (
            <HourlyTimeline
              hours={hourlyDetail.hours}
              sunset={hourlyDetail.sunset}
              sunrise={hourlyDetail.sunrise}
            />
          ) : null}
        </Box>
      )}

      {/* Methodology */}
      <MethodologyInfo />
    </Box>
  );
}
```

- [ ] **Step 2: Add the route in App.tsx**

In `frontend/src/App.tsx`, add the import and route:

Import (add with other page imports):
```tsx
import WeatherPage from "./pages/WeatherPage";
```

Route (add after the `/locations` route, before `/settings`):
```tsx
{ path: "weather", element: <WeatherPage /> },
```

- [ ] **Step 3: Add nav item in AppShell.tsx**

In `frontend/src/components/AppShell.tsx`, add the weather nav item.

Add the icon import:
```tsx
import WbSunnyIcon from "@mui/icons-material/WbSunny";
```

Add to the `navItems` array (after the Locations entry):
```tsx
{ to: "/weather", label: "Weather", icon: <WbSunnyIcon /> },
```

- [ ] **Step 4: Verify TypeScript compiles and build succeeds**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/WeatherPage.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx
git commit -m "feat: add WeatherPage with routing and navigation"
```

---

## Task 14: Integration Testing — Full Stack Verification

**Files:** No new files — this task verifies everything works together.

- [ ] **Step 1: Run backend linting**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run ruff check src/ tests/`
Expected: No errors. Fix any issues found.

- [ ] **Step 2: Run backend formatting check**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run ruff format --check src/ tests/`
Expected: No changes needed. If changes needed, run `uv run ruff format src/ tests/` and commit.

- [ ] **Step 3: Run security scan**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run bandit -r src/`
Expected: No high-severity issues.

- [ ] **Step 4: Run full backend test suite**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest -v`
Expected: All tests pass.

- [ ] **Step 5: Run frontend build**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 6: Manual smoke test**

Run: `cd /Users/fbaptiste/dev/nightcrate && make dev`

Test:
1. Navigate to Weather page via sidebar
2. Verify location selector shows saved locations (default pre-selected)
3. Verify 7-day cards load with scores
4. Click a day card — verify hourly timeline renders
5. Toggle moon checkbox — verify scores update
6. Expand "How are scores calculated?" — verify methodology text
7. Test light/dark theme — verify blue hue cells remain readable

- [ ] **Step 7: Commit any fixes**

```bash
git add -A
git commit -m "fix: integration testing fixes for weather feature"
```

---

## Task 15: Settings Page — Weather Configuration UI

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Read the current SettingsPage**

Read the file to understand the current structure before modifying.

- [ ] **Step 2: Add weather settings section**

Add a "Weather" section to the Settings page with:
- Weather cache TTL slider (1–24 hours, default 6)
- Moon penalty toggle (default on)

Follow the exact same pattern as existing settings controls (GPU acceleration toggle, aberration cache TTL, etc.).

- [ ] **Step 3: Verify build**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx
git commit -m "feat: add weather cache TTL and moon penalty settings to Settings page"
```
