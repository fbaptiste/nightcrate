"""Tests for settings configuration — key-value schema."""

import json
import logging

import pytest

from nightcrate.core.config import (
    BrowserFavorite,
    Settings,
    get_settings,
    settings_from_rows,
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
        assert s.gallery_slideshow_seconds == 5

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
    async def test_repeated_damaged_load_logs_once(self, caplog, monkeypatch):
        from nightcrate.core import config
        from nightcrate.db.session import get_db

        monkeypatch.setattr(config, "_last_logged_dropped_fields", frozenset())
        async with get_db() as conn:
            await conn.execute(
                "INSERT INTO settings (key, value_json) VALUES (?, ?)",
                ("gallery_view", '"huge"'),
            )
            await conn.commit()

        with caplog.at_level(logging.WARNING, logger="nightcrate.core.config"):
            await get_settings()
            await get_settings()

        warnings = [
            record
            for record in caplog.records
            if record.message.startswith("[settings] ignored invalid stored fields")
        ]
        assert len(warnings) == 1

    async def test_damage_returning_after_clean_load_logs_again(self, caplog, monkeypatch):
        """damaged → repaired → damaged again gives two warnings, not one."""
        from nightcrate.core import config
        from nightcrate.db.session import get_db

        monkeypatch.setattr(config, "_last_logged_dropped_fields", frozenset())

        async def set_view(value_json: str) -> None:
            async with get_db() as conn:
                await conn.execute(
                    "INSERT INTO settings (key, value_json) VALUES ('gallery_view', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                    (value_json,),
                )
                await conn.commit()

        with caplog.at_level(logging.WARNING, logger="nightcrate.core.config"):
            await set_view('"huge"')
            await get_settings()
            await set_view('"large"')
            assert (await get_settings()).gallery_view == "large"
            await set_view('"huge"')
            await get_settings()

        warnings = [
            record
            for record in caplog.records
            if record.message.startswith("[settings] ignored invalid stored fields")
        ]
        assert len(warnings) == 2

    async def test_invalid_field_falls_back_alone_and_nothing_is_written(self):
        from nightcrate.db.session import get_db

        async with get_db() as conn:
            await conn.executemany(
                "INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                [
                    ("gallery_view", '"huge"', "2000-01-01 00:00:00"),
                    ("theme", '"dark"', "2000-01-01 00:00:00"),
                    ("gallery_slideshow_seconds", "7", "2000-01-01 00:00:00"),
                ],
            )
            await conn.commit()
            before = await (await conn.execute("SELECT * FROM settings ORDER BY key")).fetchall()

        loaded = await get_settings()

        async with get_db() as conn:
            after = await (await conn.execute("SELECT * FROM settings ORDER BY key")).fetchall()
        assert loaded.gallery_view == "medium"
        assert loaded.gallery_slideshow_seconds == 5
        assert loaded.theme == "dark"
        assert [tuple(row) for row in after] == [tuple(row) for row in before]

    async def test_threshold_order_failure_resets_only_thresholds(self):
        from nightcrate.db.session import get_db

        values = {
            "scoring_threshold_excellent": 50,
            "scoring_threshold_good": 60,
            "scoring_weight_moon": 4.0,
            "theme": "dark",
        }
        async with get_db() as conn:
            await conn.executemany(
                "INSERT INTO settings (key, value_json) VALUES (?, ?)",
                [(key, json.dumps(value)) for key, value in values.items()],
            )
            await conn.commit()

        loaded = await get_settings()
        assert (
            loaded.scoring_threshold_excellent,
            loaded.scoring_threshold_good,
            loaded.scoring_threshold_fair,
        ) == (80, 60, 40)
        assert loaded.scoring_weight_moon == 4.0
        assert loaded.theme == "dark"

    async def test_negative_weight_resets_only_that_weight(self):
        from nightcrate.db.session import get_db

        async with get_db() as conn:
            await conn.executemany(
                "INSERT INTO settings (key, value_json) VALUES (?, ?)",
                [
                    ("scoring_weight_moon", "-1"),
                    ("scoring_weight_meridian", "3"),
                    ("theme", '"dark"'),
                ],
            )
            await conn.commit()

        loaded = await get_settings()
        assert loaded.scoring_weight_moon == 1.5
        assert loaded.scoring_weight_meridian == 3
        assert loaded.theme == "dark"

    async def test_string_stored_numbers_judged_as_parsed(self):
        from nightcrate.db.session import get_db

        async with get_db() as conn:
            await conn.executemany(
                "INSERT INTO settings (key, value_json) VALUES (?, ?)",
                [
                    ("scoring_threshold_excellent", '"50"'),
                    ("scoring_threshold_good", "60"),
                ],
            )
            await conn.commit()
        loaded = await get_settings()
        assert (
            loaded.scoring_threshold_excellent,
            loaded.scoring_threshold_good,
            loaded.scoring_threshold_fair,
        ) == (80, 60, 40)

        async with get_db() as conn:
            await conn.execute("DELETE FROM settings")
            await conn.executemany(
                "INSERT INTO settings (key, value_json) VALUES (?, ?)",
                [
                    ("scoring_threshold_excellent", '"100"'),
                    ("scoring_threshold_good", '"90"'),
                    ("scoring_threshold_fair", '"80"'),
                    ("scoring_weight_moon", "-1"),
                ],
            )
            await conn.commit()
        loaded = await get_settings()
        assert (
            loaded.scoring_threshold_excellent,
            loaded.scoring_threshold_good,
            loaded.scoring_threshold_fair,
        ) == (100, 90, 80)
        assert loaded.scoring_weight_moon == 1.5

    def test_settings_from_rows_valid_passthrough(self):
        loaded, dropped = settings_from_rows({"gallery_slideshow_seconds": 8})
        assert loaded.gallery_slideshow_seconds == 8
        assert dropped == frozenset()

    def test_composite_and_scoring_failures_together(self):
        loaded, dropped = settings_from_rows(
            {
                "browser_favorites": [{"name": "missing path"}],
                "planner_coverage_range": [15],
                "scoring_threshold_excellent": 50,
                "scoring_threshold_good": 60,
                "scoring_threshold_fair": 40,
                "theme": "dark",
            }
        )
        assert loaded.browser_favorites == []
        assert loaded.planner_coverage_range is None
        assert (
            loaded.scoring_threshold_excellent,
            loaded.scoring_threshold_good,
            loaded.scoring_threshold_fair,
        ) == (80, 60, 40)
        assert loaded.theme == "dark"
        assert dropped == frozenset(
            {
                "browser_favorites",
                "planner_coverage_range",
                "scoring_threshold_excellent",
                "scoring_threshold_good",
                "scoring_threshold_fair",
            }
        )

    def test_low_min_altitude_resets_only_altitude(self):
        loaded, dropped = settings_from_rows(
            {"scoring_observability_min_altitude_deg": 5.0, "theme": "dark"}
        )
        assert loaded.scoring_observability_min_altitude_deg == 30.0
        assert loaded.theme == "dark"
        assert dropped == frozenset({"scoring_observability_min_altitude_deg"})

    def test_low_min_altitude_error_names_its_field(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            Settings(scoring_observability_min_altitude_deg=5.0)
        (error,) = exc_info.value.errors()
        assert error["type"] == "cross_field"
        assert error["ctx"]["fields"] == ["scoring_observability_min_altitude_deg"]
        assert "must be >= 10" in error["msg"]

    def test_unplaceable_validation_error_falls_back_to_defaults(self, monkeypatch):
        """Defensive path: an error naming no stored key can't be fixed by
        dropping one, so every stored key is dropped and defaults load."""
        from nightcrate.core import config

        calls = {"n": 0}

        def flaky_violations(_settings):
            calls["n"] += 1
            return frozenset({"scoring_threshold_good"}) if calls["n"] == 1 else frozenset()

        monkeypatch.setattr(config, "_cross_field_violations", flaky_violations)
        loaded, dropped = settings_from_rows({"theme": "dark"})
        assert loaded == Settings()
        assert dropped == frozenset({"theme"})

    async def test_messier_settings_round_trip_and_invalid_location_fallback(self):
        values = Settings(
            messier_view="large",
            messier_imaged_style="sky",
            messier_unimaged_style="blank",
            messier_show_projects=True,
            messier_location=7,
            messier_rig_id=12,
        )
        await update_settings(values)
        loaded = await get_settings()
        assert loaded.messier_view == "large"
        assert loaded.messier_imaged_style == "sky"
        assert loaded.messier_unimaged_style == "blank"
        assert loaded.messier_show_projects is True
        assert loaded.messier_location == 7
        assert loaded.messier_rig_id == 12

        from nightcrate.db.session import get_db

        for invalid in (True, 1.0, 0, -3, "abc"):
            async with get_db() as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value_json) VALUES (?, ?)",
                    ("messier_location", json.dumps(invalid)),
                )
                await conn.commit()
            assert (await get_settings()).messier_location == "default"

        for valid in ("none", "default", 7):
            async with get_db() as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value_json) VALUES (?, ?)",
                    ("messier_location", json.dumps(valid)),
                )
                await conn.commit()
            assert (await get_settings()).messier_location == valid

        async with get_db() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO settings (key, value_json) VALUES (?, ?)",
                ("messier_imaged_style", '"invalid"'),
            )
            await conn.commit()
        assert (await get_settings()).messier_imaged_style == "own"

    async def test_default_solver_setting(self):
        from nightcrate.db.session import get_db

        assert Settings().default_solver == "native"
        async with get_db() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO settings (key, value_json) VALUES (?, ?)",
                ("default_solver", '"invalid"'),
            )
            await conn.commit()
        assert (await get_settings()).default_solver == "native"
        await update_settings(Settings(default_solver="astap"))
        assert (await get_settings()).default_solver == "astap"

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
