"""Tests for settings configuration."""

import pytest

from nightcrate.core.config import BrowserFavorite, Settings, get_settings, update_settings


class TestSettingsModel:
    def test_defaults(self):
        s = Settings()
        assert s.theme == "browser"
        assert s.gpu_acceleration is True
        assert s.max_worker_cores is None
        assert s.last_browse_path is None
        assert s.browser_favorites == []

    def test_custom_values(self):
        s = Settings(
            theme="dark",
            gpu_acceleration=False,
            max_worker_cores=4,
            last_browse_path="/tmp",
            browser_favorites=[BrowserFavorite(name="data", path="/data")],
        )
        assert s.theme == "dark"
        assert s.max_worker_cores == 4
        assert len(s.browser_favorites) == 1

    def test_invalid_theme_rejected(self):
        with pytest.raises(Exception):
            Settings(theme="invalid")


class TestSettingsPersistence:
    async def test_get_returns_defaults(self):
        s = await get_settings()
        assert s.theme == "browser"
        assert s.gpu_acceleration is True

    async def test_round_trip(self):
        original = Settings(
            theme="dark",
            gpu_acceleration=False,
            last_browse_path="/Volumes/Data",
            browser_favorites=[BrowserFavorite(name="Astro", path="/Volumes/Astro")],
        )
        await update_settings(original)
        loaded = await get_settings()
        assert loaded.theme == "dark"
        assert loaded.gpu_acceleration is False
        assert loaded.last_browse_path == "/Volumes/Data"
        assert len(loaded.browser_favorites) == 1
        assert loaded.browser_favorites[0].name == "Astro"

    async def test_corrupt_data_returns_defaults(self):
        """If the JSON in the DB is invalid, get_settings returns defaults."""
        from nightcrate.db.session import get_db

        async with get_db() as conn:
            await conn.execute("UPDATE settings SET data = 'not valid json{{{' WHERE id = 1")
            await conn.commit()
        s = await get_settings()
        assert s.theme == "browser"
