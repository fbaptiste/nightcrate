"""Tests for settings configuration — key-value schema."""

import json

import pytest

from nightcrate.core.config import (
    BrowserFavorite,
    Settings,
    get_settings,
    update_settings,
)


class TestSettingsModel:
    def test_defaults(self):
        s = Settings()
        assert s.theme == "browser"
        assert s.gpu_acceleration is True
        assert s.max_worker_cores is None
        assert s.last_browse_path is None
        assert s.browser_favorites == []
        assert s.calculators_clock_order == []

    def test_custom_values(self):
        s = Settings(
            theme="dark",
            gpu_acceleration=False,
            max_worker_cores=4,
            last_browse_path="/tmp",
            browser_favorites=[BrowserFavorite(name="data", path="/data")],
            calculators_clock_order=["utc", "local"],
        )
        assert s.theme == "dark"
        assert s.max_worker_cores == 4
        assert len(s.browser_favorites) == 1
        assert s.calculators_clock_order == ["utc", "local"]

    def test_invalid_theme_rejected(self):
        with pytest.raises(Exception):
            Settings(theme="invalid")


class TestSettingsPersistence:
    async def test_get_returns_defaults(self):
        s = await get_settings()
        assert s.theme == "browser"
        assert s.gpu_acceleration is True
        assert s.calculators_clock_order == []

    async def test_round_trip(self):
        original = Settings(
            theme="dark",
            gpu_acceleration=False,
            last_browse_path="/Volumes/Data",
            browser_favorites=[BrowserFavorite(name="Astro", path="/Volumes/Astro")],
            calculators_clock_order=["mjd", "jd", "local"],
        )
        await update_settings(original)
        loaded = await get_settings()
        assert loaded.theme == "dark"
        assert loaded.gpu_acceleration is False
        assert loaded.last_browse_path == "/Volumes/Data"
        assert len(loaded.browser_favorites) == 1
        assert loaded.browser_favorites[0].name == "Astro"
        assert loaded.calculators_clock_order == ["mjd", "jd", "local"]

    async def test_corrupt_single_row_falls_back_to_default_for_that_field(self):
        """A single corrupt value_json row shouldn't poison the whole load —
        other fields load normally; the bad one falls back to its default."""
        from nightcrate.db.session import get_db

        # Seed a known-good set first, then corrupt just the theme row.
        await update_settings(Settings(theme="dark", gpu_acceleration=False))
        async with get_db() as conn:
            await conn.execute(
                "UPDATE settings SET value_json = 'not valid json{{{' WHERE key = ?",
                ("theme",),
            )
            await conn.commit()
        loaded = await get_settings()
        # `theme` fell back to default; `gpu_acceleration` is still the dark-mode value.
        assert loaded.theme == "browser"
        assert loaded.gpu_acceleration is False

    async def test_unknown_key_is_ignored(self):
        """Legacy or forward-compat rows in the table must not break load."""
        from nightcrate.db.session import get_db

        async with get_db() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO settings (key, value_json) VALUES (?, ?)",
                ("a_future_setting_we_dont_know_about", '"hello"'),
            )
            await conn.commit()
        # Load succeeds — unknown key silently ignored.
        s = await get_settings()
        assert isinstance(s, Settings)

    async def test_type_drift_returns_defaults(self):
        """If a persisted value has the wrong type for its field (e.g. a DB
        edited by hand), Pydantic validation fails and we hand back a pristine
        defaults Settings rather than a half-initialised one."""
        from nightcrate.db.session import get_db

        async with get_db() as conn:
            # `gpu_acceleration` must be a bool; shove an int list in there.
            await conn.execute(
                "INSERT OR REPLACE INTO settings (key, value_json) VALUES (?, ?)",
                ("gpu_acceleration", "[1,2,3]"),
            )
            await conn.commit()
        s = await get_settings()
        assert s == Settings()

    async def test_update_is_upsert_not_duplicating_rows(self):
        """Calling update_settings repeatedly must not create duplicate rows;
        the PRIMARY KEY on `key` + ON CONFLICT handles it."""
        from nightcrate.db.session import get_db

        await update_settings(Settings(theme="dark"))
        await update_settings(Settings(theme="light"))
        await update_settings(Settings(theme="browser"))
        async with get_db() as conn:
            cursor = await conn.execute("SELECT COUNT(*) AS n FROM settings WHERE key = 'theme'")
            row = await cursor.fetchone()
        assert row["n"] == 1

    async def test_update_refreshes_updated_at(self):
        """Every upsert bumps updated_at for the affected rows."""
        from nightcrate.db.session import get_db

        await update_settings(Settings(theme="dark"))
        async with get_db() as conn:
            cursor = await conn.execute("SELECT updated_at FROM settings WHERE key = 'theme'")
            first = (await cursor.fetchone())["updated_at"]
        # Bump via another update.
        await update_settings(Settings(theme="light"))
        async with get_db() as conn:
            cursor = await conn.execute("SELECT updated_at FROM settings WHERE key = 'theme'")
            second = (await cursor.fetchone())["updated_at"]
        # Timestamps are strings; `second >= first` lexicographically works
        # because they share the ISO8601-ish format CURRENT_TIMESTAMP emits.
        assert second >= first

    async def test_empty_table_returns_all_defaults(self):
        """A freshly migrated DB with zero rows must load cleanly as defaults."""
        from nightcrate.db.session import get_db

        async with get_db() as conn:
            await conn.execute("DELETE FROM settings")
            await conn.commit()
        s = await get_settings()
        assert s == Settings()

    async def test_composite_values_roundtrip(self):
        """List/object fields (browser_favorites, calculators_clock_order)
        serialise as JSON and round-trip structurally."""
        payload = Settings(
            browser_favorites=[
                BrowserFavorite(name="A", path="/a"),
                BrowserFavorite(name="B", path="/b with spaces"),
            ],
            calculators_clock_order=["utc", "local", "jd"],
        )
        await update_settings(payload)
        loaded = await get_settings()
        assert [f.name for f in loaded.browser_favorites] == ["A", "B"]
        assert loaded.browser_favorites[1].path == "/b with spaces"
        assert loaded.calculators_clock_order == ["utc", "local", "jd"]

    async def test_null_values_roundtrip(self):
        """Nullable fields (max_worker_cores, last_browse_path) must persist
        a JSON `null` and come back as Python `None`."""
        from nightcrate.db.session import get_db

        await update_settings(Settings(max_worker_cores=None, last_browse_path=None))
        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT value_json FROM settings WHERE key = 'max_worker_cores'"
            )
            row = await cursor.fetchone()
        assert row["value_json"] == "null"
        loaded = await get_settings()
        assert loaded.max_worker_cores is None
        assert loaded.last_browse_path is None

    async def test_value_json_is_well_formed_for_each_row(self):
        """Every row written by update_settings must itself be parseable JSON
        (not SQL-ese, not python-repr). Catches double-quoting regressions."""
        from nightcrate.db.session import get_db

        await update_settings(
            Settings(
                theme="dark",
                max_worker_cores=8,
                calculators_clock_order=["utc"],
            )
        )
        async with get_db() as conn:
            cursor = await conn.execute("SELECT key, value_json FROM settings")
            for row in await cursor.fetchall():
                # Must not raise.
                json.loads(row["value_json"])
