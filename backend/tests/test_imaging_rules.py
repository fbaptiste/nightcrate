"""Tests for per-location imaging rules and their schema migrations."""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR, apply_migrations
from nightcrate.db.session import get_db_path
from nightcrate.main import app
from nightcrate.services.imaging_rules import DEFAULT_PRESET, PRESETS, ImagingRules

CLOUD_RULE_FIELDS = {
    "cloud_use_ecmwf",
    "cloud_use_gfs",
    "cloud_use_icon",
    "cloud_preferred_model",
    "cloud_combination",
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _location(client: AsyncClient, name: str = "Rules Test Site") -> int:
    response = await client.post(
        "/api/locations",
        json={
            "name": name,
            "latitude": 33.4484,
            "longitude": -112.0740,
            "timezone": "America/Phoenix",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _rules_row(location_id: int, **overrides) -> dict:
    values = PRESETS["attended_session"][1].model_dump()
    values.update(overrides)
    return {"location_id": location_id, **values}


def _insert_rules(conn: sqlite3.Connection, values: dict) -> None:
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    conn.execute(
        f"INSERT INTO location_imaging_rules ({columns}) VALUES ({placeholders})",  # nosec B608 - test-only fixed keys
        tuple(values.values()),
    )


def test_presets_match_spec():
    common = {
        "min_clear_fraction_pct": 50,
        "min_clear_hours": 2.0,
        "max_cloudy_gap_hours": None,
        "short_session_hours": 2.0,
        "darkness": "astronomical",
        "cloud_max_pct": 20,
        "cloud_use_ecmwf": True,
        "cloud_use_gfs": True,
        "cloud_use_icon": True,
        "cloud_preferred_model": "ecmwf_ifs025",
        "cloud_combination": "majority",
        "gear_out_before_sunset_min": 30,
        "gear_out_after_sunrise_min": 30,
        "rain_amount_threshold_mm": 0,
        "wind_max_kmh": 30,
        "gust_max_kmh": 45,
        "dew_counted": False,
        "dew_min_spread_c": 3.0,
        "moon_must_be_down": False,
    }
    expected = {
        "left_out_all_night": {
            **common,
            "session_style": "all_night",
            "rain_max_probability_pct": 10,
            "rain_policy": "night_off",
            "rain_forecasts": "any_model",
            "wind_counted": True,
        },
        "attended_session": {
            **common,
            "session_style": "short_session",
            "rain_max_probability_pct": 20,
            "rain_policy": "hours_lost",
            "rain_forecasts": "main",
            "wind_counted": True,
        },
        "dome": {
            **common,
            "session_style": "all_night",
            "rain_max_probability_pct": 20,
            "rain_policy": "hours_lost",
            "rain_forecasts": "main",
            "wind_counted": False,
        },
    }
    assert {key: rules.model_dump() for key, (_, rules) in PRESETS.items()} == expected
    assert DEFAULT_PRESET == "attended_session"


def test_rules_accept_fraction_100():
    values = PRESETS[DEFAULT_PRESET][1].model_dump()
    values["min_clear_fraction_pct"] = 100
    assert ImagingRules(**values).min_clear_fraction_pct == 100


def test_rules_reject_fraction_below_1():
    values = PRESETS[DEFAULT_PRESET][1].model_dump()
    values["min_clear_fraction_pct"] = 0.5
    with pytest.raises(ValidationError):
        ImagingRules(**values)


def test_rules_threshold_bounds():
    values = PRESETS[DEFAULT_PRESET][1].model_dump()
    values["rain_amount_threshold_mm"] = 0
    assert ImagingRules(**values).rain_amount_threshold_mm == 0
    values["rain_amount_threshold_mm"] = 5
    assert ImagingRules(**values).rain_amount_threshold_mm == 5
    values["rain_amount_threshold_mm"] = -0.1
    with pytest.raises(ValidationError):
        ImagingRules(**values)


def test_rules_require_a_selected_cloud_model_and_selected_preference():
    values = PRESETS[DEFAULT_PRESET][1].model_dump()
    values.update(cloud_use_ecmwf=False, cloud_use_gfs=False, cloud_use_icon=False)
    with pytest.raises(ValidationError, match="Choose at least one cloud forecast"):
        ImagingRules(**values)

    values["cloud_use_gfs"] = True
    with pytest.raises(
        ValidationError,
        match="The preferred cloud forecast must be one of the ticked forecasts",
    ):
        ImagingRules(**values)

    assert all(ImagingRules.model_validate(rules) for _, rules in PRESETS.values())


def test_rules_forbid_extra_fields():
    values = PRESETS[DEFAULT_PRESET][1].model_dump()
    values["surprise"] = True
    with pytest.raises(ValidationError):
        ImagingRules(**values)


@pytest.mark.anyio
async def test_get_rules_unsaved_returns_default(client):
    location_id = await _location(client)
    response = await client.get(f"/api/locations/{location_id}/imaging-rules")
    assert response.status_code == 200
    assert response.json() == {
        "location_id": location_id,
        "saved": False,
        "rules": PRESETS[DEFAULT_PRESET][1].model_dump(),
    }


@pytest.mark.anyio
async def test_put_get_roundtrip_new_fields(client):
    location_id = await _location(client)
    values = PRESETS["left_out_all_night"][1].model_dump()
    values["max_cloudy_gap_hours"] = 1.5
    values["rain_amount_threshold_mm"] = 0.1
    values["rain_forecasts"] = "any_model"
    response = await client.put(f"/api/locations/{location_id}/imaging-rules", json=values)
    assert response.status_code == 200, response.text
    assert response.json() == {"location_id": location_id, "saved": True, "rules": values}
    response = await client.get(f"/api/locations/{location_id}/imaging-rules")
    assert response.status_code == 200
    assert response.json()["rules"] == values
    assert response.json()["rules"]["wind_counted"] is True


@pytest.mark.anyio
async def test_put_rejects_no_selected_cloud_forecast(client):
    location_id = await _location(client)
    values = PRESETS[DEFAULT_PRESET][1].model_dump()
    values.update(cloud_use_ecmwf=False, cloud_use_gfs=False, cloud_use_icon=False)
    response = await client.put(f"/api/locations/{location_id}/imaging-rules", json=values)
    assert response.status_code == 422
    assert "Choose at least one cloud forecast" in response.text


@pytest.mark.anyio
async def test_put_overwrites(client):
    location_id = await _location(client)
    first = PRESETS["left_out_all_night"][1].model_dump()
    second = PRESETS["dome"][1].model_dump()
    assert (
        await client.put(f"/api/locations/{location_id}/imaging-rules", json=first)
    ).status_code == 200
    assert (
        await client.put(f"/api/locations/{location_id}/imaging-rules", json=second)
    ).status_code == 200
    with closing(sqlite3.connect(get_db_path())) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM location_imaging_rules WHERE location_id = ?",
            (location_id,),
        ).fetchone()[0]
        policy = conn.execute(
            "SELECT rain_policy FROM location_imaging_rules WHERE location_id = ?",
            (location_id,),
        ).fetchone()[0]
    assert count == 1
    assert policy == second["rain_policy"]


@pytest.mark.anyio
async def test_rules_404_inactive_location(client):
    location_id = await _location(client)
    assert (await client.delete(f"/api/locations/{location_id}")).status_code == 200
    path = f"/api/locations/{location_id}/imaging-rules"
    assert (await client.get(path)).status_code == 404
    assert (await client.put(path, json=PRESETS[DEFAULT_PRESET][1].model_dump())).status_code == 404


@pytest.mark.anyio
async def test_presets_endpoint_order(client):
    response = await client.get("/api/imaging-rules/presets")
    assert response.status_code == 200
    assert [preset["key"] for preset in response.json()] == [
        "left_out_all_night",
        "attended_session",
        "dome",
    ]


def test_migration_0061_fresh_via_yoyo(tmp_path):
    path = tmp_path / "fresh.db"
    apply_migrations(path)
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='location_imaging_rules'"
        ).fetchone() == (1,)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(location_imaging_rules)")}
        assert {
            "rain_max_probability_pct",
            "rain_amount_threshold_mm",
            "rain_forecasts",
        } <= columns
        assert "rain_max_period_probability_pct" not in columns
        assert conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='trigger' AND name='trg_location_imaging_rules_updated_at'"
        ).fetchone() == (1,)
        rows_before = conn.execute(
            "SELECT COUNT(*) FROM _yoyo_migration WHERE migration_id = ?",
            ("0061.imaging_rules_single_chance",),
        ).fetchone()[0]
        total_before = conn.execute("SELECT COUNT(*) FROM _yoyo_migration").fetchone()[0]
    assert rows_before == 1
    apply_migrations(path)
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _yoyo_migration").fetchone()[0] == total_before


def test_migration_0061_preserves_rules(tmp_path):
    path = tmp_path / "upgrade-from-0060.db"
    with get_backend(f"sqlite:///{path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        through_0060 = backend.to_apply(migrations).filter(
            lambda migration: migration.id <= "0060.weather_cache_model_meta"
        )
        with backend.lock():
            backend.apply_migrations(through_0060)

    with closing(sqlite3.connect(path)) as conn:
        location_ids = [
            conn.execute(
                "INSERT INTO location (name, latitude, longitude, timezone) VALUES (?, ?, ?, ?)",
                (name, 33.4484, -112.0740, "America/Phoenix"),
            ).lastrowid
            for name in ("Saved Rules One", "Saved Rules Two")
        ]
        for index, location_id in enumerate(location_ids):
            rules = {
                key: value
                for key, value in PRESETS[("left_out_all_night", "dome")[index]][1]
                .model_dump()
                .items()
                if key not in CLOUD_RULE_FIELDS
            }
            rules["rain_max_period_probability_pct"] = 77 + index
            _insert_rules(
                conn,
                {
                    "location_id": location_id,
                    **rules,
                    "created_at": f"2000-01-0{index + 1} 01:02:03",
                    "updated_at": f"2001-02-0{index + 1} 04:05:06",
                },
            )
        conn.commit()
        preserved_columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(location_imaging_rules)")
            if row[1] != "rain_max_period_probability_pct"
        ]
        column_list = ", ".join(preserved_columns)
        before = conn.execute(
            f"SELECT {column_list} FROM location_imaging_rules ORDER BY location_id"  # nosec B608 - schema-derived test columns
        ).fetchall()

    apply_migrations(path)

    with closing(sqlite3.connect(path)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(location_imaging_rules)")}
        assert "rain_max_period_probability_pct" not in columns
        after = conn.execute(
            f"SELECT {column_list} FROM location_imaging_rules ORDER BY location_id"  # nosec B608 - schema-derived test columns
        ).fetchall()
        assert after == before
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

        old_updated_at = after[0][preserved_columns.index("updated_at")]
        conn.execute(
            "UPDATE location_imaging_rules SET cloud_max_pct = cloud_max_pct + 1 "
            "WHERE location_id = ?",
            (location_ids[0],),
        )
        conn.commit()
        updated_at = conn.execute(
            "SELECT updated_at FROM location_imaging_rules WHERE location_id = ?",
            (location_ids[0],),
        ).fetchone()[0]
        assert updated_at != old_updated_at


def test_migration_0062_adds_cloud_columns_preserving_rows(tmp_path):
    path = tmp_path / "upgrade-from-0061.db"
    with get_backend(f"sqlite:///{path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        through_0061 = backend.to_apply(migrations).filter(
            lambda migration: migration.id <= "0061.imaging_rules_single_chance"
        )
        with backend.lock():
            backend.apply_migrations(through_0061)

    with closing(sqlite3.connect(path)) as conn:
        location_ids = [
            conn.execute(
                "INSERT INTO location (name, latitude, longitude, timezone) VALUES (?, ?, ?, ?)",
                (name, 33.4484, -112.0740, "America/Phoenix"),
            ).lastrowid
            for name in ("Cloud Rules One", "Cloud Rules Two")
        ]
        for index, location_id in enumerate(location_ids):
            rules = {
                key: value
                for key, value in PRESETS[("left_out_all_night", "dome")[index]][1]
                .model_dump()
                .items()
                if key not in CLOUD_RULE_FIELDS
            }
            _insert_rules(
                conn,
                {
                    "location_id": location_id,
                    **rules,
                    "created_at": f"2000-01-0{index + 1} 01:02:03",
                    "updated_at": f"2001-02-0{index + 1} 04:05:06",
                },
            )
        conn.commit()
        columns_before = [
            row[1] for row in conn.execute("PRAGMA table_info(location_imaging_rules)")
        ]
        before = conn.execute(
            f"SELECT {', '.join(columns_before)} FROM location_imaging_rules "  # nosec B608 - schema-derived test columns
            "ORDER BY location_id"
        ).fetchall()

    apply_migrations(path)

    with closing(sqlite3.connect(path)) as conn:
        after = conn.execute(
            f"SELECT {', '.join(columns_before)} FROM location_imaging_rules "  # nosec B608 - schema-derived test columns
            "ORDER BY location_id"
        ).fetchall()
        assert after == before
        assert (
            conn.execute(
                "SELECT cloud_use_ecmwf, cloud_use_gfs, cloud_use_icon, "
                "cloud_preferred_model, cloud_combination "
                "FROM location_imaging_rules ORDER BY location_id"
            ).fetchall()
            == [(1, 1, 1, "ecmwf_ifs025", "majority")] * 2
        )
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE location_imaging_rules SET cloud_use_ecmwf = 0, "
                "cloud_use_gfs = 0, cloud_use_icon = 0 WHERE location_id = ?",
                (location_ids[0],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE location_imaging_rules SET cloud_use_ecmwf = 0 WHERE location_id = ?",
                (location_ids[0],),
            )

        old_updated_at = after[0][columns_before.index("updated_at")]
        conn.execute(
            "UPDATE location_imaging_rules SET cloud_max_pct = cloud_max_pct + 1 "
            "WHERE location_id = ?",
            (location_ids[0],),
        )
        conn.commit()
        updated_at = conn.execute(
            "SELECT updated_at FROM location_imaging_rules WHERE location_id = ?",
            (location_ids[0],),
        ).fetchone()[0]
        assert updated_at != old_updated_at


@pytest.mark.anyio
async def test_migration_0059_discards_rules_only(tmp_path, monkeypatch, client):
    path = tmp_path / "upgrade.db"
    with get_backend(f"sqlite:///{path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        through_0058 = backend.to_apply(migrations).filter(
            lambda migration: migration.id <= "0058.location_imaging_rules"
        )
        with backend.lock():
            backend.apply_migrations(through_0058)

    with closing(sqlite3.connect(path)) as conn:
        location_ids = [
            conn.execute(
                "INSERT INTO location (name, latitude, longitude, timezone) VALUES (?, ?, ?, ?)",
                (name, 33.4484, -112.0740, "America/Phoenix"),
            ).lastrowid
            for name in ("Preserved Site One", "Preserved Site Two")
        ]
        old_rules = {
            key: value
            for key, value in PRESETS["attended_session"][1].model_dump().items()
            if key
            not in {
                "rain_amount_threshold_mm",
                "rain_forecasts",
                *CLOUD_RULE_FIELDS,
            }
        }
        for location_id in location_ids:
            _insert_rules(conn, {"location_id": location_id, **old_rules})
        conn.execute(
            """INSERT INTO weather_cache
               (location_id, source, start_date, end_date, response_json)
               VALUES (?, 'forecast', '2026-10-17', '2026-10-18', '{\"hourly\": {}}')""",
            (location_ids[0],),
        )
        conn.commit()
        application_tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "AND name NOT LIKE '_yoyo%' AND name != 'location_imaging_rules' "
                "ORDER BY name"
            )
        ]
        counts_before = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in application_tables
        }
        locations_before = conn.execute("SELECT * FROM location ORDER BY id").fetchall()

    apply_migrations(path)
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT * FROM location ORDER BY id").fetchall() == locations_before
        assert {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in application_tables
        } == counts_before
        assert conn.execute("SELECT COUNT(*) FROM location_imaging_rules").fetchone() == (0,)
        table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'location_imaging_rules'"
        ).fetchone()[0]
        normalized_sql = " ".join(table_sql.split())
        assert (
            "CHECK (min_clear_fraction_pct >= 1 AND min_clear_fraction_pct <= 100)"
            in normalized_sql
        )
        assert "rain_max_period_probability_pct" not in normalized_sql
        assert "CHECK (rain_amount_threshold_mm >= 0)" in normalized_sql
        assert "CHECK (rain_forecasts IN ('main', 'any_model'))" in normalized_sql
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    monkeypatch.setattr("nightcrate.db.session._db_path", path)
    location_id = location_ids[0]
    response = await client.get(f"/api/locations/{location_id}/imaging-rules")
    assert response.status_code == 200
    assert response.json() == {
        "location_id": location_id,
        "saved": False,
        "rules": PRESETS[DEFAULT_PRESET][1].model_dump(),
    }

    values = PRESETS["left_out_all_night"][1].model_dump()
    response = await client.put(f"/api/locations/{location_id}/imaging-rules", json=values)
    assert response.status_code == 200, response.text
    response = await client.get(f"/api/locations/{location_id}/imaging-rules")
    assert response.json() == {"location_id": location_id, "saved": True, "rules": values}

    with closing(sqlite3.connect(path)) as conn:
        conn.execute(
            "UPDATE location_imaging_rules SET updated_at = '2000-01-01 00:00:00' "
            "WHERE location_id = ?",
            (location_id,),
        )
        conn.commit()
    values["cloud_max_pct"] = 25
    response = await client.put(f"/api/locations/{location_id}/imaging-rules", json=values)
    assert response.status_code == 200, response.text
    with closing(sqlite3.connect(path)) as conn:
        assert (
            conn.execute(
                "SELECT updated_at FROM location_imaging_rules WHERE location_id = ?",
                (location_id,),
            ).fetchone()[0]
            != "2000-01-01 00:00:00"
        )
        conn.execute("PRAGMA foreign_keys = ON")
        assert conn.execute(
            "SELECT COUNT(*) FROM location_imaging_rules WHERE location_id = ?",
            (location_id,),
        ).fetchone() == (1,)
        conn.execute("DELETE FROM location WHERE id = ?", (location_id,))
        assert conn.execute(
            "SELECT COUNT(*) FROM location_imaging_rules WHERE location_id = ?",
            (location_id,),
        ).fetchone() == (0,)


def test_rules_check_constraints():
    with closing(sqlite3.connect(get_db_path())) as conn:
        location_id = conn.execute(
            "INSERT INTO location (name, latitude, longitude, timezone) VALUES (?, ?, ?, ?)",
            ("Constraint Site", 33.4484, -112.0740, "America/Phoenix"),
        ).lastrowid
        with pytest.raises(sqlite3.IntegrityError):
            _insert_rules(conn, _rules_row(location_id, rain_policy="sometimes"))
        with pytest.raises(sqlite3.IntegrityError):
            _insert_rules(conn, _rules_row(location_id, wind_counted=2))
