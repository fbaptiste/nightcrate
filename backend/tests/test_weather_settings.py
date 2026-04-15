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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
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
