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


async def test_thumbnail_fov_simulator_missing_fov_returns_400(client: TestClient, seed_db):
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = (await cursor.fetchone())["id"]
    response = client.get(
        f"/api/planner/thumbnails/{m42}",
        params={"variant": "fov_simulator", "fov_major_deg": 0.37},
    )
    assert response.status_code == 400


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


async def test_dsos_in_region_response_includes_type_group(client: TestClient, seed_dsos_in_region):
    response = client.get(
        "/api/planner/dsos/in-region",
        params={
            "ra_center_deg": 202.47,
            "dec_center_deg": 47.20,
            "extent_deg": 0.5,
        },
    )
    assert response.status_code == 200
    # All seeded objects are galaxies — type_group must be populated.
    for item in response.json()["items"]:
        if item["obj_type"] == "G":
            assert item["type_group"] == "Galaxy"


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


async def test_thumbnail_sky_center_rejected_on_non_simulator_variant(client: TestClient, seed_db):
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = (await cursor.fetchone())["id"]
    response = client.get(
        f"/api/planner/thumbnails/{m42}",
        params={"variant": "detail", "center_ra_deg": 100.0, "center_dec_deg": 10.0},
    )
    assert response.status_code == 400


async def test_thumbnail_sky_center_rejected_on_invalid_range(client: TestClient, seed_db):
    async with get_db() as conn:
        cursor = await conn.execute("SELECT id FROM dso WHERE primary_designation = 'M 42'")
        m42 = (await cursor.fetchone())["id"]
    # Dec out of range.
    response = client.get(
        f"/api/planner/thumbnails/{m42}",
        params={
            "variant": "fov_simulator",
            "fov_major_deg": 0.37,
            "fov_minor_deg": 0.28,
            "center_ra_deg": 50.0,
            "center_dec_deg": 100.0,
        },
    )
    assert response.status_code == 400
    # RA out of range (negative).
    response = client.get(
        f"/api/planner/thumbnails/{m42}",
        params={
            "variant": "fov_simulator",
            "fov_major_deg": 0.37,
            "fov_minor_deg": 0.28,
            "center_ra_deg": -1.0,
            "center_dec_deg": 10.0,
        },
    )
    assert response.status_code == 400


async def test_thumbnail_rig_framed_with_valid_fov_returns_202_placeholder(
    client: TestClient, seed_db, monkeypatch
):
    # Mock out the upstream fetcher so we don't touch the network; 202
    # path fires immediately and the fetch runs in the background.
    async def _fake_get(*args, **kwargs):
        # Tiny valid JPEG body passes the fetcher's magic-byte check.
        class R:
            status_code = 200
            content = b"\xff\xd8" + b"x" * 2048

        return R()

    monkeypatch.setattr("nightcrate.services.hips_client.http_client.get", _fake_get)
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


async def test_sky_tile_cache_clear_endpoint(client: TestClient):
    response = client.post("/api/planner/sky-tile/cache/clear")
    assert response.status_code == 200
    assert "deleted_files" in response.json()


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

    async def _fake_get(url, *args, **kwargs):
        # Never resolves (mimics a slow CDS); the client's wait_ms=0 means
        # we should see the placeholder path without waiting.
        import asyncio

        await asyncio.sleep(60)

        class R:
            status_code = 200
            content = b"\xff\xd8" + b"x" * 2048

        return R()

    monkeypatch.setattr("nightcrate.services.hips_client.http_client.get", _fake_get)
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

    async def _fake_get(url, *args, **kwargs):
        class R:
            status_code = 200
            content = fake_body

        return R()

    monkeypatch.setattr("nightcrate.services.hips_client.http_client.get", _fake_get)
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
