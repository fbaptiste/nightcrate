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


async def test_targets_response_includes_filter_aware_facet_counts(client: TestClient, seed_db):
    # The chip labels on the frontend read "Galaxy (N)" where N is the
    # count under the current filters. Back-end must return those
    # tallies alongside the filtered items.
    _ = seed_db
    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "limit": 5},
    )
    assert response.status_code == 200
    body = response.json()
    # Both dictionaries exist and are non-empty for a seeded DB.
    assert isinstance(body["type_group_counts"], dict)
    assert isinstance(body["raw_type_counts"], dict)
    assert sum(body["type_group_counts"].values()) > 0
    # Selecting a specific group via ``type_group`` does NOT reduce
    # that group's own facet count (faceted-search invariant: a
    # chip's count reflects the state with its own dimension
    # excluded).
    first_group = next(iter(body["type_group_counts"].keys()))
    filtered = client.get(
        "/api/planner/targets",
        params={
            "restrict_tonight": "false",
            "type_group": first_group,
            "limit": 5,
        },
    ).json()
    assert filtered["type_group_counts"][first_group] == body["type_group_counts"][first_group]


async def test_targets_sort_by_size_descending(client: TestClient, seed_db):
    # ``sort=size`` maps to ``maj_axis_arcmin`` in the in-memory sort
    # helper. In Anytime mode (no visibility filter) the largest
    # object in the seed fixture must sort first on ``desc``.
    _ = seed_db
    response = client.get(
        "/api/planner/targets",
        params={"restrict_tonight": "false", "sort": "size", "sort_dir": "desc"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    # First few rows must be the largest (descending major axis).
    sizes = [i["maj_axis_arcmin"] for i in items[:5] if i["maj_axis_arcmin"] is not None]
    assert sizes == sorted(sizes, reverse=True)


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
