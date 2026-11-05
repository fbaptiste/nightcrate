"""Integration tests for /api/planner/* endpoints."""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from nightcrate.api.planner import _sort_items
from nightcrate.api.planner_models import PlannerTargetItem
from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services import hips_tiles
from nightcrate.services.dso_sorting import designation_sort_key
from nightcrate.services.planner_visibility import (
    DarkWindow,
    DsoVisibility,
    VisibilitySnapshot,
    default_cache,
)


@pytest.fixture
def client():
    return TestClient(app)


def _make_every_dso_visible(monkeypatch) -> None:
    cached: VisibilitySnapshot | None = None

    def get_or_compute(location, _horizon, night_date, dsos):
        nonlocal cached
        if cached is not None and set(cached.per_dso) == {dso.dso_id for dso in dsos}:
            return cached
        start = datetime(2026, 4, 20, 3, 0, tzinfo=UTC)
        end = start + timedelta(hours=6)
        per_dso = {
            dso.dso_id: DsoVisibility(
                dso_id=dso.dso_id,
                hours_visible=6.0,
                max_altitude_deg=60.0,
                peak_time_utc=start + timedelta(hours=3),
                azimuth_at_peak_deg=180.0,
                min_moon_separation_deg=90.0,
                rise_time_utc=start,
                set_time_utc=end,
                transit_time_utc=start + timedelta(hours=3),
                altitude_at_transit_deg=60.0,
            )
            for dso in dsos
        }
        cached = VisibilitySnapshot(
            location_id=location.id,
            night_date=night_date,
            dark_window=DarkWindow(start, end),
            moon_phase_pct=0.0,
            per_dso=per_dso,
        )
        return cached

    monkeypatch.setattr(
        "nightcrate.api.planner.default_cache",
        SimpleNamespace(get_or_compute=get_or_compute),
    )
    monkeypatch.setattr("nightcrate.api.planner.score_targets", lambda *_args, **_kwargs: {})


async def _old_id_list_order(catalog: str | None = None) -> list[int]:
    async with get_db() as conn:
        rows = await (
            await conn.execute(
                """
                SELECT id
                FROM dso
                WHERE active = 1 AND ra_deg IS NOT NULL AND dec_deg IS NOT NULL
                """
            )
        ).fetchall()
        dso_ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in dso_ids)
        metadata_rows = await (
            await conn.execute(
                f"""
                SELECT id, primary_designation
                FROM dso
                WHERE id IN ({placeholders})
                """,  # noqa: S608  # nosec B608 - reproduces the replaced id-list query
                dso_ids,
            )
        ).fetchall()
        designation_rows = await (
            await conn.execute(
                f"""
                SELECT dso_id, catalog
                FROM dso_designation
                WHERE dso_id IN ({placeholders})
                """,  # noqa: S608  # nosec B608 - reproduces the replaced id-list query
                dso_ids,
            )
        ).fetchall()

    catalogs: dict[int, set[str]] = {dso_id: set() for dso_id in dso_ids}
    for row in designation_rows:
        catalogs[int(row["dso_id"])].add(str(row["catalog"]))
    metadata = {int(row["id"]): str(row["primary_designation"]) for row in metadata_rows}
    eligible = [dso_id for dso_id in dso_ids if catalog is None or catalog in catalogs[dso_id]]
    return sorted(eligible, key=lambda dso_id: (designation_sort_key(metadata[dso_id]), dso_id))


@pytest.fixture(autouse=True)
def _planner_cache_dirs(tmp_path, monkeypatch):
    """Keep planner disk-cache writes inside each test's temporary directory."""
    monkeypatch.setattr("nightcrate.core.app_config.APP_DIR", tmp_path)


@pytest.fixture
async def seed_db():
    """Seed a location + a handful of DSOs for the planner to operate on."""
    async with get_db() as conn:
        # Location: Phoenix.
        cursor = await conn.execute(
            """
            INSERT INTO location
                (name, latitude, longitude, elevation_m, timezone, geo_timezone,
                 bortle_class, typical_seeing_low_arcsec, typical_seeing_high_arcsec,
                 is_default, active)
            VALUES ('Phoenix', 33.4484, -112.074, 331, 'America/Phoenix',
                'America/Phoenix', 8, 2.0, 4.0, 1, 1)
            """
        )
        location_id = cursor.lastrowid

        # Default horizon — mirrors the auto-seed the POST /api/locations
        # endpoint does. Raw-SQL seeding has to own this itself.
        await conn.execute(
            """
            INSERT INTO location_horizon (location_id, name, type, flat_altitude_deg, is_default)
            VALUES (?, '0° flat', 'artificial', 0, 1)
            """,
            (location_id,),
        )

        # DSO source + rows.
        await conn.execute(
            """
            INSERT INTO dso_catalog_source
                (source_id, category, display_name, file_path, file_hash, row_count)
            VALUES ('test', 'openngc', 'Test', '/dev/null', 'abc', 0)
            """
        )
        cursor = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        source_id = int((await cursor.fetchone())["id"])

        # M42 — well-known bright HII region. Spring evening from Phoenix puts
        # it low in the west but probably above 30° for at least a short
        # astro-dark window.
        cursor = await conn.execute(
            """
            INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg,
                constellation, maj_axis_arcmin, min_axis_arcmin, mag_v,
                source_catalog_id, source_row_hash)
            VALUES ('M 42', 'HII', 83.8221, -5.3911, 'Ori', 65.0, 60.0, 4.0, ?, 'h1')
            """,
            (source_id,),
        )
        m42_id = cursor.lastrowid
        # A dim galaxy that should be filtered out by magnitude.
        cursor = await conn.execute(
            """
            INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg,
                constellation, maj_axis_arcmin, min_axis_arcmin, mag_v,
                source_catalog_id, source_row_hash)
            VALUES ('FAINT-1', 'G', 200.0, 30.0, 'CVn', 3.0, 2.0, 18.0, ?, 'h2')
            """,
            (source_id,),
        )
        faint_id = cursor.lastrowid
        # NGC 281 — Pacman nebula in Cas. Carries an ngc designation but
        # not a messier one; used by the catalog-OR filter test to
        # prove the OR expands to rows that only carry one of the two
        # selected catalogs.
        cursor = await conn.execute(
            """
            INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg,
                constellation, maj_axis_arcmin, min_axis_arcmin, mag_v,
                source_catalog_id, source_row_hash)
            VALUES ('NGC 281', 'HII', 13.0, 56.62, 'Cas', 35.0, 30.0, 7.4, ?, 'h3')
            """,
            (source_id,),
        )
        ngc281_id = cursor.lastrowid

        # Designations — catalog-filter and catalog-facet tests depend
        # on this table being populated.
        for dso_id, catalog, identifier, display, key, is_primary in (
            (m42_id, "ngc", "1976", "NGC 1976", "ngc1976", 0),
            (m42_id, "messier", "42", "M 42", "m42", 1),
            (faint_id, "ngc", "9999", "NGC 9999", "ngc9999", 1),
            (ngc281_id, "ngc", "281", "NGC 281", "ngc281", 1),
        ):
            await conn.execute(
                """
                INSERT INTO dso_designation
                    (dso_id, catalog, identifier, display_form, search_key, is_primary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (dso_id, catalog, identifier, display, key, is_primary),
            )

        await conn.commit()

    return location_id


@pytest.fixture
async def seed_emission_types(seed_db):
    async with get_db() as conn:
        source = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        source_id = int((await source.fetchone())["id"])
        await conn.execute(
            """
            INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg,
                constellation, maj_axis_arcmin, min_axis_arcmin, mag_v,
                source_catalog_id, source_row_hash)
            VALUES ('TEST EmN', 'EmN', 315.0, 44.0, 'Cyg', 45.0, 35.0, 8.0, ?, 'emn1')
            """,
            (source_id,),
        )
        await conn.commit()
    return seed_db


@pytest.fixture
async def seed_limit_edge_dsos(seed_db):
    """Add unknown-magnitude and unknown-size rows for limit semantics tests."""
    async with get_db() as conn:
        source = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        source_id = int((await source.fetchone())["id"])
        await conn.execute(
            """
            INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg,
                constellation, maj_axis_arcmin, min_axis_arcmin,
                source_catalog_id, source_row_hash)
            VALUES ('NOMAG', 'G', 201.0, 30.0, 'CVn', 20.0, 10.0, ?, 'limit-nomag')
            """,
            (source_id,),
        )
        await conn.execute(
            """
            INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg,
                constellation, mag_v, source_catalog_id, source_row_hash)
            VALUES ('NOSIZE', 'G', 202.0, 30.0, 'CVn', 8.0, ?, 'limit-nosize')
            """,
            (source_id,),
        )
        await conn.commit()
    return seed_db


@pytest.fixture
async def seed_grouped_dsos(seed_db):
    async with get_db() as conn:
        source = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id='test'")
        source_id = int((await source.fetchone())["id"])
        ids: dict[str, int] = {}
        for index, (name, catalog, identifier) in enumerate(
            (
                ("NGC 4038", "ngc", "4038"),
                ("NGC 4039", "ngc", "4039"),
                ("Arp 1", "arp", "1"),
            )
        ):
            cursor = await conn.execute(
                """
                INSERT INTO dso (
                    primary_designation, obj_type, ra_deg, dec_deg, constellation,
                    maj_axis_arcmin, source_catalog_id, source_row_hash, source_key
                ) VALUES (?, 'G', ?, -18.0, 'Crv', 5.0, ?, ?, ?)
                """,
                (name, 180.0 + index, source_id, f"group-{index}", f"group-{index}"),
            )
            assert cursor.lastrowid is not None
            dso_id = int(cursor.lastrowid)
            ids[name] = dso_id
            await conn.execute(
                """
                INSERT INTO dso_designation (
                    dso_id, catalog, identifier, display_form, search_key, is_primary
                ) VALUES (?, ?, ?, ?, ?, 1)
                """,
                (dso_id, catalog, identifier, name, name.replace(" ", "").lower()),
            )
        group = await conn.execute(
            """
            INSERT INTO dso_group (catalog, identifier, display_form, search_key, common_name)
            VALUES ('arp', '244', 'Arp 244', 'arp244', 'Antennae Galaxies')
            """
        )
        assert group.lastrowid is not None
        await conn.executemany(
            "INSERT INTO dso_group_member (group_id, dso_id) VALUES (?, ?)",
            (
                (int(group.lastrowid), ids["NGC 4038"]),
                (int(group.lastrowid), ids["NGC 4039"]),
            ),
        )
        await conn.commit()
    return seed_db, ids


@pytest.fixture
async def seed_other_names(seed_db):
    async with get_db() as conn:
        source = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        source_id = int((await source.fetchone())["id"])
        cursor = await conn.execute(
            """
            INSERT INTO dso (
                primary_designation, common_name, obj_type, ra_deg, dec_deg,
                constellation, maj_axis_arcmin, min_axis_arcmin, mag_v,
                source_catalog_id, source_row_hash
            ) VALUES (
                'M 76', 'Little Dumbbell Nebula', 'PN', 25.58, 51.58,
                'Per', 2.7, 1.8, 10.1, ?, 'other-names'
            )
            """,
            (source_id,),
        )
        m76_id = int(cursor.lastrowid)
        await conn.execute(
            """
            INSERT INTO dso_designation (
                dso_id, catalog, identifier, display_form, search_key, is_primary
            ) VALUES (?, 'messier', '76', 'M 76', 'm76', 1)
            """,
            (m76_id,),
        )
        await conn.executemany(
            "INSERT INTO dso_other_name (dso_id, name, position) VALUES (?, ?, ?)",
            ((m76_id, "Cork Nebula", 1), (m76_id, "Barbell Nebula", 2)),
        )
        await conn.commit()
    return seed_db, m76_id


async def test_lists_return_other_names(client: TestClient, seed_other_names):
    location_id, m76_id = seed_other_names
    requests = (
        {"restrict_tonight": "false", "limit": 100},
        {
            "location_id": location_id,
            "date": "2026-11-15",
            "restrict_tonight": "true",
            "min_hours": 0,
            "limit": 100,
        },
    )

    for params in requests:
        response = client.get("/api/planner/targets", params=params)
        assert response.status_code == 200
        by_id = {item["dso_id"]: item for item in response.json()["items"]}
        assert by_id[m76_id]["other_names"] == ["Cork Nebula", "Barbell Nebula"]
        m42 = next(item for item in by_id.values() if item["primary_designation"] == "M 42")
        assert m42["other_names"] == []


async def test_search_matches_other_name(client: TestClient, seed_other_names):
    _location_id, m76_id = seed_other_names

    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "q": "Cork"},
    )

    assert response.status_code == 200
    assert [item["dso_id"] for item in response.json()["items"]] == [m76_id]


async def test_search_matches_group_name(client: TestClient, seed_grouped_dsos):
    _location_id, ids = seed_grouped_dsos

    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "q": "Antennae"},
    )

    assert response.status_code == 200
    assert {item["dso_id"] for item in response.json()["items"]} == {
        ids["NGC 4038"],
        ids["NGC 4039"],
    }


async def test_targets_endpoint_returns_snapshot(client: TestClient, seed_db):
    location_id = seed_db
    # Date in April puts Orion low in the Phoenix evening; 2 hours minimum
    # may or may not include M42 — keep the filter lax to avoid flakiness.
    response = client.get(
        "/api/planner/targets",
        params={
            "location_id": location_id,
            "date": "2026-04-19",
            "min_hours": 0.0,
            "max_magnitude": 20.0,
            "min_size_arcmin": 0.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["location"]["name"] == "Phoenix"
    # Auto-seeded 0° artificial default horizon echoes back in the response.
    assert data["horizon"]["type"] == "artificial"
    assert data["horizon"]["flat_altitude_deg"] == 0.0
    assert data["rig"] is None
    assert data["dark_window"] is not None
    assert data["total"] >= 0
    # FAINT-1 (z=18) should be filterable out via max_magnitude.
    designations = {item["primary_designation"] for item in data["items"]}
    assert designations.issubset({"M 42", "FAINT-1", "NGC 281"})


async def test_now_status_suppressed_for_non_today_date(client: TestClient, seed_db, monkeypatch):
    """``now_status`` (up/rising/set *right now*) is only meaningful when the
    requested night is today; for any other date the backend must return it as
    ``None``.

    Determinism: ``now_status`` normally depends on the real wall clock relative
    to the night's dark window, so we pin "today" via ``_tonight_date`` and force
    ``compute_now_status`` to a sentinel. Both requests use mid-January nights one
    day apart, where M 42 is well-placed over Phoenix all night — so visibility is
    held constant and the ONLY variable is whether the date equals today.
    """
    location_id = seed_db
    fixed_today = date(2026, 1, 15)
    monkeypatch.setattr("nightcrate.api.planner._tonight_date", lambda _tz: fixed_today)

    def fake_now_status(_loc, _hor, coords, *, astro_dark_start_utc, astro_dark_end_utc):
        return {d.dso_id: "up" for d in coords}

    monkeypatch.setattr("nightcrate.api.planner.compute_now_status", fake_now_status)

    common = {
        "location_id": location_id,
        "min_hours": 0.0,
        "max_magnitude": 20.0,
        "min_size_arcmin": 0.0,
    }

    def m42(items):
        return next((i for i in items if i["primary_designation"] == "M 42"), None)

    # Requested date IS today → now_status computed (sentinel "up").
    today = client.get("/api/planner/targets", params={**common, "date": fixed_today.isoformat()})
    assert today.status_code == 200
    today_m42 = m42(today.json()["items"])
    assert today_m42 is not None, "M 42 should be visible over Phoenix in mid-January"
    assert today_m42["now_status"] == "up"

    # One night later (not today) → now_status suppressed to None, even though
    # M 42 is still visible.
    other = client.get("/api/planner/targets", params={**common, "date": "2026-01-16"})
    assert other.status_code == 200
    other_items = other.json()["items"]
    other_m42 = m42(other_items)
    assert other_m42 is not None, "M 42 should still be visible the next night"
    assert other_m42["now_status"] is None
    assert all(item["now_status"] is None for item in other_items)


async def test_now_status_computes_page_only_unless_used_for_sort(
    client: TestClient, seed_db, monkeypatch
):
    _make_every_dso_visible(monkeypatch)
    fixed_today = date(2026, 4, 19)
    monkeypatch.setattr("nightcrate.api.planner._tonight_date", lambda _tz: fixed_today)
    calls: list[list[int]] = []

    def fake_now_status(_loc, _hor, coords, *, astro_dark_start_utc, astro_dark_end_utc):
        ids = sorted(dso.dso_id for dso in coords)
        calls.append(ids)
        statuses = ("set", "up", "rising")
        return {dso_id: statuses[index % len(statuses)] for index, dso_id in enumerate(ids)}

    monkeypatch.setattr("nightcrate.api.planner.compute_now_status", fake_now_status)
    common = {
        "location_id": seed_db,
        "date": fixed_today.isoformat(),
        "min_hours": 0.0,
    }

    page_response = client.get(
        "/api/planner/targets",
        params={**common, "limit": 1, "sort": "primary_designation:asc"},
    )
    assert page_response.status_code == 200
    assert len(calls[-1]) == 1
    assert page_response.json()["items"][0]["now_status"] is not None

    sorted_response = client.get(
        "/api/planner/targets",
        params={**common, "limit": 100, "sort": "now_status:asc"},
    )
    assert sorted_response.status_code == 200
    assert len(calls[-1]) == sorted_response.json()["total"]
    assert [item["now_status"] for item in sorted_response.json()["items"]] == [
        "up",
        "rising",
        "set",
    ]


def test_key_sort_has_stable_ties_and_nulls_last_for_asc_and_desc():
    def item(
        dso_id: int,
        designation: str,
        common_name: str | None,
        score: int | None,
        status: str | None,
    ):
        return (
            PlannerTargetItem.model_construct(
                dso_id=dso_id,
                primary_designation=designation,
                common_name=common_name,
                score_pct=score,
                now_status=status,
            ),
            None,
        )

    rows = [
        item(1, "NGC 10", "Alpha", 50, "set"),
        item(2, "NGC 2", "alpha", 50, "up"),
        item(3, "M 1", None, 50, "rising"),
        item(4, "B 1", "Beta", None, None),
        item(5, "NGC 2", "alpha", 60, "set"),
    ]
    _sort_items(
        rows,
        [("score_pct", "desc"), ("common_name", "asc"), ("primary_designation", "desc")],
    )
    assert [row[0].dso_id for row in rows] == [5, 1, 2, 3, 4]

    _sort_items(rows, [("now_status", "asc"), ("score_pct", "desc")])
    assert [row[0].dso_id for row in rows] == [2, 3, 5, 1, 4]


def test_transit_datetime_sort_is_chronological_with_nulls_last():
    early = datetime(2026, 4, 20, 3, 0, tzinfo=UTC)
    late = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    rows = [
        (SimpleNamespace(dso_id=3, transit_time_utc=None), None),
        (SimpleNamespace(dso_id=2, transit_time_utc=late), None),
        (SimpleNamespace(dso_id=1, transit_time_utc=early), None),
    ]

    _sort_items(rows, [("transit_time_utc", "asc")])
    assert [row[0].dso_id for row in rows] == [1, 2, 3]

    _sort_items(rows, [("transit_time_utc", "desc")])
    assert [row[0].dso_id for row in rows] == [2, 1, 3]


async def test_targets_endpoint_applies_max_magnitude(client: TestClient, seed_db):
    location_id = seed_db
    response = client.get(
        "/api/planner/targets",
        params={
            "location_id": location_id,
            "date": "2026-04-19",
            "min_hours": 0.0,
            "max_magnitude": 10.0,  # excludes FAINT-1 at mag 18
            "min_size_arcmin": 0.0,
        },
    )
    data = response.json()
    designations = {item["primary_designation"] for item in data["items"]}
    assert "FAINT-1" not in designations


async def test_tonight_without_limit_params_filters_nothing(
    client: TestClient, seed_limit_edge_dsos, monkeypatch
):
    _make_every_dso_visible(monkeypatch)
    response = client.get(
        "/api/planner/targets",
        params={"location_id": seed_limit_edge_dsos, "date": "2026-04-19", "limit": 100},
    )

    assert response.status_code == 200
    designations = {item["primary_designation"] for item in response.json()["items"]}
    assert {"FAINT-1", "NOMAG", "NOSIZE"} <= designations


async def test_magnitude_limit_passes_unknown_magnitude(
    client: TestClient, seed_limit_edge_dsos, monkeypatch
):
    _make_every_dso_visible(monkeypatch)
    response = client.get(
        "/api/planner/targets",
        params={
            "location_id": seed_limit_edge_dsos,
            "date": "2026-04-19",
            "max_magnitude": 10.0,
            "limit": 100,
        },
    )

    assert response.status_code == 200
    designations = {item["primary_designation"] for item in response.json()["items"]}
    assert "NOMAG" in designations
    assert "FAINT-1" not in designations


async def test_size_limit_drops_unknown_size(client: TestClient, seed_limit_edge_dsos, monkeypatch):
    _make_every_dso_visible(monkeypatch)
    response = client.get(
        "/api/planner/targets",
        params={
            "location_id": seed_limit_edge_dsos,
            "date": "2026-04-19",
            "min_size_arcmin": 5.0,
            "limit": 100,
        },
    )

    assert response.status_code == 200
    designations = {item["primary_designation"] for item in response.json()["items"]}
    assert "NOSIZE" not in designations


async def test_anytime_unchanged(client: TestClient, seed_limit_edge_dsos):
    _ = seed_limit_edge_dsos
    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "limit": 100},
    )

    assert response.status_code == 200
    designations = {item["primary_designation"] for item in response.json()["items"]}
    assert {"FAINT-1", "NOMAG", "NOSIZE"} <= designations


async def test_targets_response_includes_filter_aware_facet_counts(client: TestClient, seed_db):
    # The pill filters on the frontend read "Galaxy (N)" where N is the
    # count under the current filters. Back-end returns one dict per
    # filter dimension (raw type, catalog, constellation); each chip's
    # count reflects the state with its own dimension held out.
    _ = seed_db
    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "limit": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["raw_type_counts"], dict)
    assert isinstance(body["catalog_counts"], dict)
    assert isinstance(body["constellation_counts"], dict)
    assert sum(body["raw_type_counts"].values()) > 0
    assert sum(body["catalog_counts"].values()) > 0


async def test_targets_merge_emission_nebula_raw_types(client: TestClient, seed_emission_types):
    _ = seed_emission_types
    baseline = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "limit": 100},
    )
    assert baseline.status_code == 200
    raw_counts = baseline.json()["raw_type_counts"]
    assert raw_counts["EmN"] == 3
    assert "HII" not in raw_counts

    results = {}
    for code in ("EmN", "HII"):
        response = client.get(
            "/api/planner/targets",
            params={"restrict_tonight": "false", "type": code, "limit": 100},
        )
        assert response.status_code == 200
        results[code] = {
            (item["primary_designation"], item["obj_type"]) for item in response.json()["items"]
        }
        assert {obj_type for _, obj_type in results[code]} == {"EmN", "HII"}

    assert results["EmN"] == results["HII"]
    assert len(results["EmN"]) == 3


async def test_targets_raw_type_count_excludes_own_dimension(client: TestClient, seed_db):
    # Faceted-search invariant: selecting one raw type doesn't collapse
    # the raw-type facet — every other raw type remains pickable, and
    # the selected type's own count remains unchanged.
    _ = seed_db
    # Re-fetch the baseline inside this test so the comparison below
    # uses a body scoped to this request.
    body = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "limit": 5},
    ).json()
    first_raw = next(iter(body["raw_type_counts"].keys()))
    filtered = client.get(
        "/api/planner/targets",
        params={
            "restrict_tonight": "false",
            "type": first_raw,
            "limit": 5,
        },
    ).json()
    assert set(filtered["raw_type_counts"].keys()) == set(body["raw_type_counts"].keys())
    assert filtered["raw_type_counts"][first_raw] == body["raw_type_counts"][first_raw]


async def test_targets_filter_by_catalog_is_or(client: TestClient, seed_db):
    # ``catalog=messier,ngc`` should return rows that carry EITHER
    # designation (OR semantics), not their intersection.
    _ = seed_db
    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "catalog": "messier,ngc", "limit": 100},
    )
    assert response.status_code == 200
    designations = {item["primary_designation"] for item in response.json()["items"]}
    # Mini fixture has M 42 (carries both messier and ngc) and NGC 281
    # (carries ngc but not messier). The union must include NGC 281.
    assert "NGC 281" in designations


async def test_targets_filter_by_multiple_constellations(client: TestClient, seed_db):
    _ = seed_db
    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "constellation": "Per,Ori", "limit": 100},
    )
    assert response.status_code == 200
    constellations = {i["constellation"] for i in response.json()["items"] if i["constellation"]}
    assert constellations <= {"Per", "Ori"}


async def test_targets_sort_by_size_descending(client: TestClient, seed_db):
    # Multi-sort ``field:dir`` syntax. In Anytime mode (no visibility
    # filter) the largest object in the seed fixture must sort first
    # on ``desc``.
    _ = seed_db
    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "sort": "maj_axis_arcmin:desc"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    # First few rows must be the largest (descending major axis).
    sizes = [i["maj_axis_arcmin"] for i in items[:5] if i["maj_axis_arcmin"] is not None]
    assert sizes == sorted(sizes, reverse=True)


async def test_targets_multi_sort(client: TestClient, seed_db):
    # Two-key sort: major axis ascending, then magnitude ascending as
    # the tie-breaker. Seed rows all have distinct sizes so the mag
    # tie-break doesn't fire, but the response shape + ordering proves
    # the multi-key parser + stable sort both work.
    _ = seed_db
    response = client.get(
        "/api/planner/targets",
        params={
            "restrict_tonight": "false",
            "sort": "maj_axis_arcmin:asc,mag_v:asc",
        },
    )
    assert response.status_code == 200
    items = response.json()["items"]
    sizes = [i["maj_axis_arcmin"] for i in items if i["maj_axis_arcmin"] is not None]
    assert sizes == sorted(sizes)


async def test_targets_sort_designations_naturally_in_both_directions(client: TestClient, seed_db):
    _ = seed_db
    async with get_db() as conn:
        source = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        source_id = int((await source.fetchone())["id"])
        for index, designation in enumerate(
            ("NGC 10", "NGC 2", "ESO 107-010", "ESO 107-2", "M 31", "Mel 1")
        ):
            await conn.execute(
                """
                INSERT INTO dso (
                    primary_designation, obj_type, ra_deg, dec_deg, common_name,
                    source_catalog_id, source_row_hash
                ) VALUES (?, 'G', ?, 10, 'Phase F planner', ?, ?)
                """,
                (designation, 20 + index, source_id, f"phase-f-planner-{index}"),
            )
        await conn.commit()

    common = {
        "restrict_tonight": "false",
        "q": "Phase F planner",
        "limit": 100,
    }
    ascending = client.get(
        "/api/planner/targets",
        params={**common, "sort": "primary_designation:asc"},
    )
    descending = client.get(
        "/api/planner/targets",
        params={**common, "sort": "primary_designation:desc"},
    )
    assert ascending.status_code == descending.status_code == 200
    expected = ["ESO 107-2", "ESO 107-010", "M 31", "Mel 1", "NGC 2", "NGC 10"]
    assert [item["primary_designation"] for item in ascending.json()["items"]] == expected
    assert [item["primary_designation"] for item in descending.json()["items"]] == list(
        reversed(expected)
    )


async def test_tied_designations_use_ascending_id_across_pages_in_both_directions(
    client: TestClient, seed_db
):
    _ = seed_db
    async with get_db() as conn:
        source = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        source_id = int((await source.fetchone())["id"])
        tied_ids: list[int] = []
        for index in range(3):
            cursor = await conn.execute(
                """
                INSERT INTO dso (
                    primary_designation, obj_type, ra_deg, dec_deg, common_name,
                    source_catalog_id, source_row_hash
                ) VALUES ('B 33', 'DrkN', ?, 10, 'Phase F tied designation', ?, ?)
                """,
                (20 + index, source_id, f"phase-f-tied-{index}"),
            )
            tied_ids.append(int(cursor.lastrowid))
        await conn.commit()

    for direction in ("asc", "desc"):
        pages: list[int] = []
        for offset in (0, 2):
            response = client.get(
                "/api/planner/targets",
                params={
                    "restrict_tonight": "false",
                    "q": "Phase F tied designation",
                    "sort": f"primary_designation:{direction}",
                    "limit": 2,
                    "offset": offset,
                },
            )
            assert response.status_code == 200
            pages.extend(item["dso_id"] for item in response.json()["items"])
        assert pages == sorted(tied_ids)


async def test_id_tiebreak_does_not_override_secondary_sort_precedence(client: TestClient, seed_db):
    _ = seed_db
    async with get_db() as conn:
        source = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        source_id = int((await source.fetchone())["id"])
        for index, (name, designation) in enumerate(
            (("Group A", "NGC 2"), ("Group B", "NGC 1"), ("Group A", "NGC 10"))
        ):
            await conn.execute(
                """
                INSERT INTO dso (
                    primary_designation, obj_type, ra_deg, dec_deg, common_name,
                    source_catalog_id, source_row_hash
                ) VALUES (?, 'G', ?, 10, ?, ?, ?)
                """,
                (designation, 20 + index, name, source_id, f"phase-f-secondary-{index}"),
            )
        await conn.commit()

    response = client.get(
        "/api/planner/targets",
        params={
            "restrict_tonight": "false",
            "q": "Group",
            "sort": "common_name:asc,primary_designation:desc",
        },
    )

    assert response.status_code == 200
    assert [
        (item["common_name"], item["primary_designation"]) for item in response.json()["items"]
    ] == [("Group A", "NGC 10"), ("Group A", "NGC 2"), ("Group B", "NGC 1")]


def test_plate_solve_typescript_comparator_keeps_id_ties_ascending():
    frontend = Path(__file__).parents[2] / "frontend"
    node = shutil.which("node")
    assert node is not None
    script = """
        import { createServer } from 'vite';
        const server = await createServer({ server: { middlewareMode: true } });
        try {
          const module = await server.ssrLoadModule(
            '/src/components/plate-solve/PlateSolveDsoGrid.tsx'
          );
          const compare = module.comparePlateSolveDsoRows;
          const low = { id: 10, primary_designation: 'B 33' };
          const high = { id: 20, primary_designation: 'B 33' };
          if (compare(low, high, 'primary_designation', 'asc') >= 0) process.exitCode = 1;
          if (compare(low, high, 'primary_designation', 'desc') >= 0) process.exitCode = 1;
          const before = { id: 30, primary_designation: 'NGC 2' };
          const after = { id: 5, primary_designation: 'NGC 10' };
          if (compare(before, after, 'primary_designation', 'asc') >= 0) process.exitCode = 1;
          if (compare(before, after, 'primary_designation', 'desc') <= 0) process.exitCode = 1;
        } finally {
          await server.close();
        }
    """
    result = subprocess.run(  # noqa: S603  # nosec B603 - fixed local Node probe
        [node, "--input-type=module", "-e", script],
        cwd=frontend,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


async def test_targets_sort_422_on_unknown_field(client: TestClient, seed_db):
    _ = seed_db
    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "sort": "bogus:asc"},
    )
    assert response.status_code == 422


async def test_targets_sort_422_on_missing_direction(client: TestClient, seed_db):
    _ = seed_db
    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "sort": "mag_v"},
    )
    assert response.status_code == 422


async def test_targets_endpoint_404s_missing_location(client: TestClient):
    response = client.get(
        "/api/planner/targets",
        params={"location_id": 99999, "date": "2026-04-19"},
    )
    assert response.status_code == 404


async def test_targets_anytime_mode_works_without_location(client: TestClient, seed_db):
    # Regression: a first-run user with no saved locations must still be
    # able to browse the catalog via Anytime mode — the endpoint can't
    # require ``location_id`` in that mode.
    _ = seed_db
    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "limit": 5},
    )
    assert response.status_code == 200
    body = response.json()
    # Location metadata is null in Anytime without a location.
    assert body["location"] is None
    assert body["dark_window"] is None
    # Visibility fields are null on every item.
    assert body["total"] > 0
    for item in body["items"]:
        assert item["hours_visible"] is None
        assert item["max_altitude_deg"] is None


async def test_scaled_queries_match_old_id_list_order(client: TestClient, seed_db, monkeypatch):
    location_id = seed_db
    _make_every_dso_visible(monkeypatch)
    expected = {
        None: await _old_id_list_order(),
        "messier": await _old_id_list_order("messier"),
    }

    for restrict_tonight in (False, True):
        for catalog, expected_ids in expected.items():
            params: dict[str, str | int | float | bool] = {
                "restrict_tonight": restrict_tonight,
                "sort": "primary_designation:asc",
                "limit": 500,
            }
            if restrict_tonight:
                params.update(
                    {
                        "location_id": location_id,
                        "date": "2026-04-19",
                        "min_hours": 0,
                        "max_magnitude": 100,
                        "min_size_arcmin": 0,
                    }
                )
            if catalog is not None:
                params["catalog"] = catalog

            response = client.get("/api/planner/targets", params=params)

            assert response.status_code == 200
            body = response.json()
            assert body["total"] == len(expected_ids)
            assert [item["dso_id"] for item in body["items"]] == expected_ids


async def test_anytime_with_40000_objects(client: TestClient, seed_db, monkeypatch):
    location_id = seed_db
    _make_every_dso_visible(monkeypatch)
    async with get_db() as conn:
        source = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        source_id = int((await source.fetchone())["id"])
        await conn.executemany(
            """
            INSERT INTO dso (
                primary_designation, obj_type, ra_deg, dec_deg, constellation,
                maj_axis_arcmin, mag_v, source_catalog_id, source_key, source_row_hash
            ) VALUES (?, 'Other', ?, ?, 'Ori', 10.0, 5.0, ?, ?, ?)
            """,
            (
                (
                    f"BULK {index:05d}",
                    float(index % 360),
                    float(index % 120 - 60),
                    source_id,
                    f"bulk-{index:05d}",
                    f"bulk-hash-{index:05d}",
                )
                for index in range(40_000)
            ),
        )
        await conn.execute(
            """
            INSERT INTO dso_designation (
                dso_id, catalog, identifier, display_form, search_key, is_primary
            )
            SELECT id, 'wr', source_key, primary_designation,
                   'bulk' || substr(source_key, 6), 1
            FROM dso
            WHERE source_key LIKE 'bulk-%'
            """
        )
        await conn.commit()
        expected_bulk_ids = [
            int(row["id"])
            for row in await (
                await conn.execute(
                    """
                    SELECT id FROM dso
                    WHERE source_key LIKE 'bulk-%'
                    ORDER BY source_key
                    LIMIT 25
                    """
                )
            ).fetchall()
        ]

    for restrict_tonight in (False, True):
        for catalog, expected_total in ((None, 40_003), ("wr", 40_000)):
            params: dict[str, str | int | float | bool] = {
                "restrict_tonight": restrict_tonight,
                "sort": "primary_designation:asc",
                "limit": 25,
            }
            if restrict_tonight:
                params.update(
                    {
                        "location_id": location_id,
                        "date": "2026-04-19",
                        "min_hours": 0,
                        "max_magnitude": 100,
                        "min_size_arcmin": 0,
                    }
                )
            if catalog is not None:
                params["catalog"] = catalog

            response = client.get("/api/planner/targets", params=params)

            assert response.status_code == 200
            body = response.json()
            assert body["total"] == expected_total
            assert [item["dso_id"] for item in body["items"]] == expected_bulk_ids


async def test_targets_tonight_mode_requires_location(client: TestClient):
    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "true"},
    )
    assert response.status_code == 400


async def test_sky_track_endpoint_returns_arrays(client: TestClient, seed_db):
    location_id = seed_db
    # Find M42's DSO id.
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = (await cursor.fetchone())["id"]

    response = client.get(
        f"/api/planner/targets/{m42}/sky-track",
        params={"location_id": location_id, "date": "2026-04-19"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["times_utc"]) > 0
    assert len(data["object_altitude_deg"]) == len(data["times_utc"])
    assert len(data["moon_altitude_deg"]) == len(data["times_utc"])
    assert len(data["moon_azimuth_deg"]) == len(data["times_utc"])
    assert all(0.0 <= az < 360.0 for az in data["moon_azimuth_deg"])
    assert len(data["horizon_altitude_at_object_az"]) == len(data["times_utc"])
    assert data["twilight"]["sunset_utc"] is not None


async def test_score_endpoint_includes_visibility_facts(client: TestClient, seed_db):
    # The detail panel reads its fact grid from this endpoint when the DSO
    # isn't in the loaded list page (switched via the FOV annotation), so the
    # score response must carry the visibility summary, not just the score.
    location_id = seed_db
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = (await cursor.fetchone())["id"]

    response = client.get(
        f"/api/planner/targets/{m42}/score",
        params={"location_id": location_id, "date": "2026-04-19"},
    )
    assert response.status_code == 200
    data = response.json()
    for key in (
        "hours_visible",
        "max_altitude_deg",
        "peak_time_utc",
        "transit_time_utc",
        "altitude_at_transit_deg",
        "min_moon_separation_deg",
    ):
        assert key in data
    # M42 transits at this date/location, so the meridian facts resolve.
    assert data["altitude_at_transit_deg"] is not None
    assert data["transit_time_utc"] is not None


async def test_inactive_object_is_hidden_from_warm_target_cache_but_scores_by_id(
    client: TestClient, seed_db
):
    location_id = seed_db
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = int((await cursor.fetchone())["id"])

    params = {
        "location_id": location_id,
        "date": "2026-04-19",
        "restrict_tonight": "true",
        "min_hours": 0,
        "limit": 100,
    }
    default_cache.clear()
    try:
        warm = client.get("/api/planner/targets", params=params)
        assert warm.status_code == 200
        assert m42 in {item["dso_id"] for item in warm.json()["items"]}

        baseline = client.get(
            f"/api/planner/targets/{m42}/score",
            params={"location_id": location_id, "date": "2026-04-19"},
        )
        assert baseline.status_code == 200

        async with get_db() as conn:
            await conn.execute("UPDATE dso SET active = 0 WHERE id = ?", (m42,))
            await conn.commit()

        cached = client.get("/api/planner/targets", params=params)
        assert cached.status_code == 200
        assert m42 not in {item["dso_id"] for item in cached.json()["items"]}

        default_cache.clear()
        without_object = client.get("/api/planner/targets", params=params)
        assert without_object.status_code == 200
        inactive = client.get(
            f"/api/planner/targets/{m42}/score",
            params={"location_id": location_id, "date": "2026-04-19"},
        )
        assert inactive.status_code == 200
        for key in (
            "score_pct",
            "quality_label",
            "score_breakdown",
            "hours_visible",
            "max_altitude_deg",
            "peak_time_utc",
            "transit_time_utc",
            "altitude_at_transit_deg",
            "min_moon_separation_deg",
        ):
            assert inactive.json()[key] == baseline.json()[key]
    finally:
        default_cache.clear()


async def test_annual_hours_endpoint_returns_one_point_per_night(client: TestClient, seed_db):
    location_id = seed_db
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = (await cursor.fetchone())["id"]

    response = client.get(
        f"/api/planner/targets/{m42}/annual-hours",
        params={
            "location_id": location_id,
            "year": 2026,
            "moon_sep_deg": 0.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["dso_id"] == m42
    assert data["year"] == 2026
    # Default horizon is the auto-seeded 0° artificial.
    assert data["horizon_type"] == "artificial"
    assert data["flat_altitude_deg"] == 0.0
    assert data["moon_sep_deg"] == 0.0
    # 2026 is not a leap year.
    assert len(data["points"]) == 365
    assert data["points"][0]["date"] == "2026-01-01"
    assert data["points"][-1]["date"] == "2026-12-31"
    assert all(0.0 <= p["hours"] <= 14.0 for p in data["points"])
    # The chart anchors its "today" marker to this location-tz date so it
    # lines up with the dome/sky-track. Null unless tonight is in this year.
    assert "today" in data
    if data["today"] is not None:
        assert data["today"].startswith("2026-")
        assert data["points"][0]["date"] <= data["today"] <= data["points"][-1]["date"]


async def test_inactive_object_sky_track_and_annual_hours_match_active(client: TestClient, seed_db):
    location_id = seed_db
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = int((await cursor.fetchone())["id"])

    sky_params = {"location_id": location_id, "date": "2026-04-19"}
    annual_params = {"location_id": location_id, "year": 2026, "moon_sep_deg": 0.0}
    active_sky = client.get(f"/api/planner/targets/{m42}/sky-track", params=sky_params)
    active_annual = client.get(f"/api/planner/targets/{m42}/annual-hours", params=annual_params)
    assert active_sky.status_code == 200
    assert active_annual.status_code == 200

    async with get_db() as conn:
        await conn.execute("UPDATE dso SET active = 0 WHERE id = ?", (m42,))
        await conn.commit()

    inactive_sky = client.get(f"/api/planner/targets/{m42}/sky-track", params=sky_params)
    inactive_annual = client.get(f"/api/planner/targets/{m42}/annual-hours", params=annual_params)
    assert inactive_sky.status_code == 200
    assert inactive_annual.status_code == 200
    assert inactive_sky.json() == active_sky.json()
    assert inactive_annual.json() == active_annual.json()


async def test_inactive_object_thumbnail_is_still_available(
    client: TestClient, seed_db, monkeypatch
):
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = int((await cursor.fetchone())["id"])
        await conn.execute("UPDATE dso SET active = 0 WHERE id = ?", (m42,))
        await conn.commit()

    async def _thumbnail(*args, **kwargs):
        return SimpleNamespace(status="hit", body=b"jpeg", content_type="image/jpeg")

    monkeypatch.setattr("nightcrate.api.planner.thumbnails.get_thumbnail", _thumbnail)
    response = client.get(f"/api/planner/thumbnails/{m42}")
    assert response.status_code == 200
    assert response.content == b"jpeg"


async def test_annual_hours_unknown_horizon_returns_404(client: TestClient, seed_db):
    location_id = seed_db
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = (await cursor.fetchone())["id"]

    response = client.get(
        f"/api/planner/targets/{m42}/annual-hours",
        params={
            "location_id": location_id,
            "horizon_id": 999999,
        },
    )
    assert response.status_code == 404


async def test_annual_hours_unknown_dso_returns_404(client: TestClient, seed_db):
    location_id = seed_db
    response = client.get(
        "/api/planner/targets/999999/annual-hours",
        params={"location_id": location_id},
    )
    assert response.status_code == 404


async def test_moon_year_endpoint_returns_points_and_phases(client: TestClient, seed_db):
    location_id = seed_db
    response = client.get(
        "/api/planner/moon-year",
        params={"location_id": location_id, "year": 2026},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2026
    assert data["location_id"] == location_id
    assert len(data["points"]) == 365
    assert data["points"][0]["date"] == "2026-01-01"
    # Illumination spans the full lunar cycle over the year.
    ills = [p["illumination_pct"] for p in data["points"]]
    assert min(ills) < 5.0 and max(ills) > 95.0
    # ~12-13 new/full moons a year, returned as ISO dates.
    assert 11 <= len(data["new_moons"]) <= 14
    assert 11 <= len(data["full_moons"]) <= 14
    assert all(len(d) == 10 for d in data["new_moons"])


async def test_moon_year_unknown_location_returns_404(client: TestClient):
    response = client.get("/api/planner/moon-year", params={"location_id": 999999})
    assert response.status_code == 404


async def test_thumbnail_cache_stats_endpoint(client: TestClient):
    response = client.get("/api/planner/thumbnails/cache/stats")
    assert response.status_code == 200
    data = response.json()
    assert {"total_bytes", "row_count", "max_bytes"} <= data.keys()


async def test_thumbnail_cache_clear_endpoint_covers_both_image_caches(
    client: TestClient, tmp_path
):
    tile_dir = tmp_path / "sky_tiles"
    tile_dir.mkdir()
    tile = tile_dir / "tile.jpg"
    tile.write_bytes(b"tile")
    async with get_db() as conn:
        await conn.execute(
            """
            INSERT INTO sky_tile_cache
                (hips_survey, healpix_nside, healpix_ipix, tier,
                 cell_size_deg_x100, cell_width_px, cell_height_px,
                 cell_i, cell_j, file_path, source, bytes)
            VALUES ('CDS/P/DSS2/color', 8, 1, 'narrow', 25, 512, 512,
                    0, 0, 'tile.jpg', 'dss2_color', 4)
            """
        )
        await conn.commit()

    stats = client.get("/api/planner/thumbnails/cache/stats").json()
    assert stats["row_count"] == 1
    assert stats["total_bytes"] == 4
    response = client.post("/api/planner/thumbnails/cache/clear")
    assert response.status_code == 200
    assert response.json()["deleted_files"] == 1
    assert not tile.exists()
    async with get_db() as conn:
        assert not await conn.execute_fetchall("SELECT id FROM sky_tile_cache")


async def test_thumbnail_rig_framed_missing_fov_returns_400(client: TestClient, seed_db):
    # Find an actual DSO ID so we get past the 404 check before the FOV one.
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = (await cursor.fetchone())["id"]
    response = client.get(
        f"/api/planner/thumbnails/{m42}",
        params={"variant": "rig_framed"},
    )
    assert response.status_code == 400
    assert "fov_major_deg" in response.json()["detail"]


async def test_thumbnail_rig_framed_negative_fov_returns_400(client: TestClient, seed_db):
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = (await cursor.fetchone())["id"]
    response = client.get(
        f"/api/planner/thumbnails/{m42}",
        params={
            "variant": "rig_framed",
            "fov_major_deg": -0.1,
            "fov_minor_deg": 0.28,
        },
    )
    assert response.status_code == 400


@pytest.fixture
async def seed_dsos_in_region(seed_db):
    """Add a clutch of DSOs around M 51 so the region query has something
    to return. Sizes span the range the overlay must handle."""
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        source_id = int((await cursor.fetchone())["id"])
        # M 51 centre: RA 202.47°, Dec +47.20°.
        await conn.executemany(
            """
            INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg,
                constellation, maj_axis_arcmin, min_axis_arcmin, mag_v,
                source_catalog_id, source_row_hash)
            VALUES (?, ?, ?, ?, 'CVn', ?, ?, ?, ?, ?)
            """,
            [
                # Primary target.
                ("M 51", "G", 202.47, 47.20, 11.2, 6.9, 8.4, source_id, "m51"),
                # NGC 5195 — just north of M 51, within a ~15' frame.
                ("NGC 5195", "G", 202.50, 47.27, 5.8, 4.6, 9.6, source_id, "n5195"),
                # IC 4263 — smaller nearby companion.
                ("IC 4263", "G", 202.60, 47.15, 1.2, 0.5, 15.0, source_id, "ic4263"),
                # IC 4277 — even smaller.
                ("IC 4277", "G", 202.53, 47.22, 0.8, 0.3, 16.0, source_id, "ic4277"),
                # IC 4278 — null-size test case.
                ("IC 4278", "G", 202.55, 47.24, None, None, 16.5, source_id, "ic4278"),
                # One object just outside the frame but within the buffer.
                ("BUFFERED-OBJ", "G", 203.20, 47.20, 3.0, 2.0, 14.0, source_id, "bufobj"),
                # An object well outside the region — should never come back.
                ("FAR-AWAY", "G", 250.00, 10.00, 5.0, 5.0, 12.0, source_id, "far"),
            ],
        )
        await conn.commit()
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 51'")
        m51_id = int((await cursor.fetchone())["id"])
    return m51_id


async def test_dsos_in_region_returns_expected_objects(client: TestClient, seed_dsos_in_region):
    response = client.get(
        "/api/planner/dsos/in-region",
        params={
            "ra_center_deg": 202.47,
            "dec_center_deg": 47.20,
            "extent_deg": 0.5,
            "exclude_id": seed_dsos_in_region,
        },
    )
    assert response.status_code == 200
    names = {i["primary_designation"] for i in response.json()["items"]}
    assert "NGC 5195" in names
    assert "IC 4263" in names
    assert "IC 4277" in names
    assert "IC 4278" in names
    assert "M 51" not in names  # excluded
    assert "FAR-AWAY" not in names


async def test_dsos_in_region_buffer_includes_just_outside_object(
    client: TestClient, seed_dsos_in_region
):
    # BUFFERED-OBJ sits at RA 203.20, ~0.73° east of M51's centre — just
    # past the raw half-extent of 0.5° but well inside the 10% buffered
    # window (0.55° halved). The exact bound depends on cos(Dec)
    # stretching of the RA half-width at dec +47°, so pick an extent
    # that is clearly large enough to capture it with the buffer.
    response = client.get(
        "/api/planner/dsos/in-region",
        params={
            "ra_center_deg": 202.47,
            "dec_center_deg": 47.20,
            "extent_deg": 2.0,
            "exclude_id": seed_dsos_in_region,
        },
    )
    assert response.status_code == 200
    names = {i["primary_designation"] for i in response.json()["items"]}
    assert "BUFFERED-OBJ" in names


async def test_dsos_in_region_response_includes_raw_obj_type(
    client: TestClient, seed_dsos_in_region
):
    response = client.get(
        "/api/planner/dsos/in-region",
        params={
            "ra_center_deg": 202.47,
            "dec_center_deg": 47.20,
            "extent_deg": 0.5,
        },
    )
    assert response.status_code == 200
    # Response surfaces the raw OpenNGC obj_type on each item — the
    # frontend translates to a friendly label via ``displayDsoType``.
    for item in response.json()["items"]:
        assert "obj_type" in item
        assert "type_group" not in item


async def test_dsos_in_region_rejects_out_of_range_params(client: TestClient):
    # Dec > 90 rejected.
    response = client.get(
        "/api/planner/dsos/in-region",
        params={"ra_center_deg": 10.0, "dec_center_deg": 91.0, "extent_deg": 1.0},
    )
    assert response.status_code == 422
    # extent_deg <= 0 rejected.
    response = client.get(
        "/api/planner/dsos/in-region",
        params={"ra_center_deg": 10.0, "dec_center_deg": 10.0, "extent_deg": 0.0},
    )
    assert response.status_code == 422


async def test_dsos_in_region_caps_limit(client: TestClient, seed_dsos_in_region):
    # Specifying a limit above 500 should be rejected (validation clamps).
    response = client.get(
        "/api/planner/dsos/in-region",
        params={
            "ra_center_deg": 202.47,
            "dec_center_deg": 47.20,
            "extent_deg": 0.5,
            "limit": 1000,
        },
    )
    assert response.status_code == 422


async def test_thumbnail_rig_framed_with_valid_fov_returns_202_placeholder(
    client: TestClient, seed_db, monkeypatch
):
    # Mock out the upstream fetcher so we don't touch the network; 202
    # path fires immediately and the fetch runs in the background.
    async def _fake_render(*args, **kwargs):
        return hips_tiles.RenderedImage(b"\xff\xd8" + b"x" * 2048, frozenset({"cds"}))

    monkeypatch.setattr(hips_tiles, "render", _fake_render)
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = (await cursor.fetchone())["id"]
    response = client.get(
        f"/api/planner/thumbnails/{m42}",
        params={
            "variant": "rig_framed",
            "fov_major_deg": 0.37,
            "fov_minor_deg": 0.28,
        },
    )
    # Placeholder (202) on miss, or a hit (200) if the fetch completed
    # during the short test window.
    assert response.status_code in {200, 202}


# ── Sky-tile endpoints (v0.18.0 / Pass C) ─────────────────────────────────────


async def test_sky_tile_cache_stats_endpoint(client: TestClient):
    response = client.get("/api/planner/sky-tile/cache/stats")
    assert response.status_code == 200
    data = response.json()
    assert {"total_bytes", "row_count", "max_bytes", "generation"} <= data.keys()


async def test_sky_tile_cache_clear_endpoint_keeps_thumbnails(
    client: TestClient, seed_db, tmp_path
):
    thumb_dir = tmp_path / "thumbnails"
    thumb_dir.mkdir()
    thumb = thumb_dir / "thumb.jpg"
    thumb.write_bytes(b"thumb")
    async with get_db() as conn:
        row = (
            await conn.execute_fetchall("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        )[0]
        await conn.execute(
            """
            INSERT INTO thumbnail_cache
                (dso_id, variant, width, height, file_path, source, bytes)
            VALUES (?, 'list', 180, 180, 'thumb.jpg', 'dss2_color', 5)
            """,
            (row["id"],),
        )
        await conn.commit()
    response = client.post("/api/planner/sky-tile/cache/clear")
    assert response.status_code == 200
    assert response.json()["deleted_files"] == 0
    assert thumb.is_file()
    async with get_db() as conn:
        assert await conn.execute_fetchall("SELECT id FROM thumbnail_cache")


async def test_sky_tile_rejects_unsupported_hips(client: TestClient):
    response = client.get(
        "/api/planner/sky-tile",
        params={
            "hips": "CDS/P/SomeOtherSurvey",
            "nside": 8,
            "ipix": 0,
            "tier": "narrow",
            "cell_i": 0,
            "cell_j": 0,
        },
    )
    assert response.status_code == 400
    assert "Unsupported HiPS survey" in response.json()["detail"]


async def test_sky_tile_rejects_ipix_over_region_count(client: TestClient):
    # nside=8 has 12*64 = 768 regions (valid ipix range 0..767).
    response = client.get(
        "/api/planner/sky-tile",
        params={
            "nside": 8,
            "ipix": 768,
            "tier": "narrow",
            "cell_i": 0,
            "cell_j": 0,
        },
    )
    assert response.status_code == 400
    assert "ipix" in response.json()["detail"]


async def test_sky_tile_rejects_unknown_tier(client: TestClient):
    response = client.get(
        "/api/planner/sky-tile",
        params={
            "nside": 8,
            "ipix": 0,
            "tier": "mediumish",
            "cell_i": 0,
            "cell_j": 0,
        },
    )
    # Literal validation happens at the pydantic layer → 422.
    assert response.status_code == 422


async def test_sky_tile_miss_returns_placeholder(client: TestClient, monkeypatch):
    """A cold cache returns the 1×1 PNG placeholder with status 202."""

    async def _fake_render(*args, **kwargs):
        # Never resolves (mimics a slow CDS); the client's wait_ms=0 means
        # we should see the placeholder path without waiting.
        import asyncio

        await asyncio.sleep(60)

        return hips_tiles.RenderedImage(b"\xff\xd8" + b"x" * 2048, frozenset({"cds"}))

    monkeypatch.setattr(hips_tiles, "render", _fake_render)
    response = client.get(
        "/api/planner/sky-tile",
        params={
            "nside": 8,
            "ipix": 100,
            "tier": "narrow",
            "cell_i": 0,
            "cell_j": 0,
        },
    )
    assert response.status_code == 202
    assert response.headers.get("cache-control", "").startswith("no-store")


async def test_sky_tile_hit_returns_jpeg(client: TestClient, monkeypatch):
    """A successful CDS response renders as a 200 with image/jpeg."""
    fake_body = b"\xff\xd8" + b"x" * 2048

    async def _fake_render(*args, **kwargs):
        return hips_tiles.RenderedImage(fake_body, frozenset({"cds"}))

    monkeypatch.setattr(hips_tiles, "render", _fake_render)
    # wait_ms=2000 lets the long-poll finish the fetch in one round trip.
    response = client.get(
        "/api/planner/sky-tile",
        params={
            "nside": 8,
            "ipix": 100,
            "tier": "narrow",
            "cell_i": 0,
            "cell_j": 0,
            "wait_ms": 2000,
        },
    )
    assert response.status_code == 200
    assert response.headers.get("content-type") == "image/jpeg"
    assert response.content == fake_body


# ── Sky-tile grid layout endpoint ─────────────────────────────────────────────


async def test_sky_tile_grid_returns_cells(client: TestClient):
    response = client.get(
        "/api/planner/sky-tile-grid",
        params={"ra_deg": 150.0, "dec_deg": 40.0, "tier": "narrow", "extent_deg": 2.0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tier"] == "narrow"
    assert data["nside"] == 8
    assert data["cell_width_px"] == 800
    assert data["cell_height_px"] == 800
    assert len(data["cells"]) >= 4
    assert data["composite_width_px"] > 0
    assert data["composite_height_px"] > 0
    # view_center_pixel_* must fall inside the composite.
    assert 0 <= data["view_center_pixel_x"] <= data["composite_width_px"]
    assert 0 <= data["view_center_pixel_y"] <= data["composite_height_px"]


async def test_sky_tile_grid_derives_tier_from_fov(client: TestClient):
    """A 0.5° FOV must land in the ``narrow`` tier without an explicit ``tier`` query."""
    response = client.get(
        "/api/planner/sky-tile-grid",
        params={"ra_deg": 150.0, "dec_deg": 40.0, "fov_major_deg": 0.5, "extent_deg": 1.0},
    )
    assert response.status_code == 200
    assert response.json()["tier"] == "narrow"


async def test_sky_tile_grid_adjacent_cells_are_cell_sized_apart(client: TestClient):
    """Endpoint preserves the core stitching invariant from the service layer."""
    response = client.get(
        "/api/planner/sky-tile-grid",
        params={"ra_deg": 150.0, "dec_deg": 40.0, "tier": "narrow", "extent_deg": 2.0},
    )
    data = response.json()
    by_coord = {(c["cell_i"], c["cell_j"]): c for c in data["cells"]}
    for (ci, cj), c in by_coord.items():
        right = by_coord.get((ci + 1, cj))
        if right is not None:
            assert right["pixel_x"] - c["pixel_x"] == data["cell_width_px"]
            assert right["pixel_y"] == c["pixel_y"]


async def test_sky_tile_grid_requires_tier_or_fov(client: TestClient):
    response = client.get(
        "/api/planner/sky-tile-grid",
        params={"ra_deg": 150.0, "dec_deg": 40.0, "extent_deg": 2.0},
    )
    assert response.status_code == 400
    assert "tier" in response.json()["detail"]


async def test_planner_group_search_returns_all_members(client: TestClient, seed_grouped_dsos):
    _location_id, ids = seed_grouped_dsos

    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "q": "Arp 244", "limit": 500},
    )

    assert response.status_code == 200
    assert {item["dso_id"] for item in response.json()["items"]} == {
        ids["NGC 4038"],
        ids["NGC 4039"],
    }


async def test_planner_search_pads_partial_mcg_and_png_designations(
    client: TestClient,
    seed_db,
):
    async with get_db() as conn:
        row = await (
            await conn.execute("SELECT id FROM dso WHERE primary_designation='M 42'")
        ).fetchone()
        dso_id = int(row["id"])
        await conn.executemany(
            """
            INSERT INTO dso_designation (
                dso_id, catalog, identifier, display_form, search_key, is_primary
            ) VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                (dso_id, "mcg", "-01-02-003", "MCG -01-02-003", "mcg-01-02-003"),
                (dso_id, "png", "010.8-01.8", "PN G010.8-01.8", "png010.8-01.8"),
            ),
        )
        await conn.commit()

    for query in ("MCG-1-2", "MCG-1", "PN G 10.8", "PN G 10"):
        response = client.get(
            "/api/planner/targets",
            params={"restrict_tonight": "false", "q": query, "limit": 500},
        )
        assert response.status_code == 200
        assert dso_id in {item["dso_id"] for item in response.json()["items"]}


async def test_planner_group_catalog_filter_and_facets(client: TestClient, seed_grouped_dsos):
    _location_id, ids = seed_grouped_dsos

    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "catalog": "arp", "limit": 500},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["catalog_counts"]["arp"] == 3
    assert {item["dso_id"] for item in body["items"]} == {
        ids["NGC 4038"],
        ids["NGC 4039"],
        ids["Arp 1"],
    }
    assert [item["primary_designation"] for item in body["items"]] == [
        "Arp 1",
        "Arp 244",
        "Arp 244",
    ]
