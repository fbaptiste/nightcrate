"""Integration tests for /api/planner/* endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nightcrate.db.session import get_db
from nightcrate.main import app


@pytest.fixture
def client():
    return TestClient(app)


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
        await conn.execute(
            """
            INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg,
                constellation, maj_axis_arcmin, min_axis_arcmin, mag_v,
                source_catalog_id, source_row_hash)
            VALUES ('M 42', 'HII', 83.8221, -5.3911, 'Ori', 65.0, 60.0, 4.0, ?, 'h1')
            """,
            (source_id,),
        )
        # A dim galaxy that should be filtered out by magnitude.
        await conn.execute(
            """
            INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg,
                constellation, maj_axis_arcmin, min_axis_arcmin, mag_v,
                source_catalog_id, source_row_hash)
            VALUES ('FAINT-1', 'G', 200.0, 30.0, 'CVn', 3.0, 2.0, 18.0, ?, 'h2')
            """,
            (source_id,),
        )
        await conn.commit()

    return location_id


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
    assert data["location"]["has_custom_horizon"] is False
    assert data["rig"] is None
    assert data["dark_window"] is not None
    assert data["total"] >= 0
    # FAINT-1 (z=18) should be filterable out via max_magnitude.
    designations = {item["primary_designation"] for item in data["items"]}
    assert designations.issubset({"M 42", "FAINT-1"})


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


async def test_targets_endpoint_404s_missing_location(client: TestClient):
    response = client.get(
        "/api/planner/targets",
        params={"location_id": 99999, "date": "2026-04-19"},
    )
    assert response.status_code == 404


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
    assert len(data["horizon_altitude_at_object_az"]) == len(data["times_utc"])
    assert data["twilight"]["sunset_utc"] is not None


async def test_thumbnail_cache_stats_endpoint(client: TestClient):
    response = client.get("/api/planner/thumbnails/cache/stats")
    assert response.status_code == 200
    data = response.json()
    assert {"total_bytes", "row_count", "max_bytes"} <= data.keys()


async def test_thumbnail_cache_clear_endpoint(client: TestClient):
    response = client.post("/api/planner/thumbnails/cache/clear")
    assert response.status_code == 200
    assert "deleted_files" in response.json()
