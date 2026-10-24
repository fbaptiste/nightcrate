"""Weather settings after retirement of the Moon score toggle."""

import aiosqlite
from httpx import ASGITransport, AsyncClient

from nightcrate.core.config import Settings, get_settings
from nightcrate.db.session import get_db_path
from nightcrate.main import app

RETIRED_MOON_KEY = "weather_moon" + "_penalty"


async def test_default_weather_cache_ttl():
    assert Settings().weather_cache_ttl_hours == 6
    assert RETIRED_MOON_KEY not in Settings.model_fields


async def test_settings_ignore_retired_moon_key():
    async with aiosqlite.connect(get_db_path()) as conn:
        await conn.execute(
            "INSERT INTO settings (key, value_json) VALUES (?, 'false')",
            (RETIRED_MOON_KEY,),
        )
        await conn.commit()
    settings = await get_settings()
    assert settings.weather_cache_ttl_hours == 6


async def test_settings_api_omits_retired_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/settings")
    assert response.status_code == 200
    assert RETIRED_MOON_KEY not in response.json()
