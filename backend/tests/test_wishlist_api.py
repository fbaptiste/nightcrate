"""Integration tests for /api/planner/wishlist/* endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nightcrate.db.session import get_db
from nightcrate.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
async def seed_dso_and_location():
    """Seed minimal DSO + location + horizon + rig data for wishlist tests."""
    async with get_db() as conn:
        await conn.execute(
            """
            INSERT INTO dso_catalog_source
                (source_id, category, display_name, file_path, file_hash, row_count)
            VALUES ('test', 'openngc', 'Test', '/dev/null', 'abc', 0)
            """
        )
        cursor = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        source_id = int((await cursor.fetchone())["id"])

        cursor = await conn.execute(
            """
            INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg,
                constellation, maj_axis_arcmin, mag_v,
                source_catalog_id, source_row_hash)
            VALUES ('M 42', 'HII', 83.8221, -5.3911, 'Ori', 65.0, 4.0, ?, 'h1')
            """,
            (source_id,),
        )
        m42_id = cursor.lastrowid

        cursor = await conn.execute(
            """
            INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg,
                constellation, maj_axis_arcmin, mag_v,
                source_catalog_id, source_row_hash)
            VALUES ('NGC 7000', 'HII', 314.7, 44.53, 'Cyg', 120.0, 4.0, ?, 'h2')
            """,
            (source_id,),
        )
        ngc7000_id = cursor.lastrowid

        cursor = await conn.execute(
            """
            INSERT INTO location
                (name, latitude, longitude, elevation_m, timezone, geo_timezone,
                 bortle_class, is_default, active)
            VALUES ('Phoenix', 33.4484, -112.074, 331, 'America/Phoenix',
                'America/Phoenix', 8, 1, 1)
            """
        )
        location_id = cursor.lastrowid

        cursor = await conn.execute(
            """
            INSERT INTO location_horizon (location_id, name, type, flat_altitude_deg, is_default)
            VALUES (?, '0° flat', 'artificial', 0, 1)
            """,
            (location_id,),
        )
        horizon_id = cursor.lastrowid

        cursor = await conn.execute(
            """
            INSERT INTO location
                (name, latitude, longitude, elevation_m, timezone, geo_timezone,
                 bortle_class, is_default, active)
            VALUES ('Remote', 31.68, -110.88, 1500, 'America/Phoenix',
                'America/Phoenix', 3, 0, 1)
            """
        )
        remote_id = cursor.lastrowid

        cursor = await conn.execute(
            """
            INSERT INTO location_horizon (location_id, name, type, flat_altitude_deg, is_default)
            VALUES (?, '5° flat', 'artificial', 5, 1)
            """,
            (remote_id,),
        )
        remote_hz_id = cursor.lastrowid

        mfr_cursor = await conn.execute("SELECT id FROM manufacturer LIMIT 1")
        mfr_row = await mfr_cursor.fetchone()
        mfr_id = int(mfr_row["id"])

        cursor = await conn.execute(
            """
            INSERT INTO sensor
                (manufacturer_id, model_name, sensor_type, pixel_size_um,
                 resolution_x, resolution_y, sensor_width_mm, sensor_height_mm)
            VALUES (?, 'Test Sensor', 'mono', 3.76, 6248, 4176, 23.5, 15.7)
            """,
            (mfr_id,),
        )
        sensor_id = cursor.lastrowid

        cursor = await conn.execute(
            """
            INSERT INTO camera
                (manufacturer_id, sensor_id, model_name, cooled)
            VALUES (?, ?, 'Test Camera', 1)
            """,
            (mfr_id, sensor_id),
        )
        camera_id = cursor.lastrowid

        cursor = await conn.execute(
            """
            INSERT INTO telescope
                (manufacturer_id, model_name, aperture_mm)
            VALUES (?, 'Test OTA', 280)
            """,
            (mfr_id,),
        )
        telescope_id = cursor.lastrowid

        cursor = await conn.execute(
            """
            INSERT INTO telescope_configuration
                (telescope_id, config_name, effective_focal_length_mm,
                 effective_focal_ratio, is_native)
            VALUES (?, 'Native', 2800, 10.0, 1)
            """,
            (telescope_id,),
        )
        config_id = cursor.lastrowid

        cursor = await conn.execute(
            """
            INSERT INTO rig (name, telescope_configuration_id, camera_id, is_default, active)
            VALUES ('C11 Rig', ?, ?, 1, 1)
            """,
            (config_id, camera_id),
        )
        rig_id = cursor.lastrowid

        cursor = await conn.execute(
            """
            INSERT INTO rig (name, telescope_configuration_id, camera_id, is_default, active)
            VALUES ('Askar V Rig', ?, ?, 0, 1)
            """,
            (config_id, camera_id),
        )
        rig2_id = cursor.lastrowid

        await conn.commit()

    return {
        "m42_id": m42_id,
        "ngc7000_id": ngc7000_id,
        "location_id": location_id,
        "horizon_id": horizon_id,
        "remote_id": remote_id,
        "remote_hz_id": remote_hz_id,
        "rig_id": rig_id,
        "rig2_id": rig2_id,
    }


def test_calendar_today_is_location_tz_date(client, seed_dso_and_location):
    # The calendar's "today" marker must anchor to the location-tz date (the
    # same `tonight_date` the planner/annual chart uses), NOT the raw UTC
    # instant — otherwise the marker lands a day ahead in the evening.
    from nightcrate.services.astronomy import tonight_date

    ids = seed_dso_and_location
    resp = client.get(
        "/api/planner/wishlist/calendar",
        params={
            "location_id": ids["location_id"],
            "horizon_id": ids["horizon_id"],
            "rig_id": ids["rig_id"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["today"] == tonight_date("America/Phoenix").isoformat()


# ── Favorites CRUD ───────────────────────────────────────────────────────────


class TestFavorites:
    def test_list_empty(self, client):
        resp = client.get("/api/planner/wishlist/favorites")
        assert resp.status_code == 200
        assert resp.json() == {"dso_ids": []}

    def test_add_favorite(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        resp = client.post(
            "/api/planner/wishlist/favorites",
            json={"dso_id": ids["m42_id"]},
        )
        assert resp.status_code == 200
        assert ids["m42_id"] in resp.json()["dso_ids"]

    def test_add_favorite_idempotent(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        client.post(
            "/api/planner/wishlist/favorites",
            json={"dso_id": ids["m42_id"]},
        )
        resp = client.post(
            "/api/planner/wishlist/favorites",
            json={"dso_id": ids["m42_id"]},
        )
        assert resp.status_code == 200
        assert resp.json()["dso_ids"].count(ids["m42_id"]) == 1

    def test_add_favorite_nonexistent_dso(self, client):
        resp = client.post(
            "/api/planner/wishlist/favorites",
            json={"dso_id": 99999},
        )
        assert resp.status_code == 404

    def test_remove_favorite(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        client.post(
            "/api/planner/wishlist/favorites",
            json={"dso_id": ids["m42_id"]},
        )
        resp = client.delete(f"/api/planner/wishlist/favorites/{ids['m42_id']}")
        assert resp.status_code == 204

        resp = client.get("/api/planner/wishlist/favorites")
        assert ids["m42_id"] not in resp.json()["dso_ids"]

    def test_remove_nonexistent_is_idempotent(self, client):
        resp = client.delete("/api/planner/wishlist/favorites/99999")
        assert resp.status_code == 204

    def test_favorites_ordering(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        client.post(
            "/api/planner/wishlist/favorites",
            json={"dso_id": ids["m42_id"]},
        )
        client.post(
            "/api/planner/wishlist/favorites",
            json={"dso_id": ids["ngc7000_id"]},
        )
        resp = client.get("/api/planner/wishlist/favorites")
        dso_ids = resp.json()["dso_ids"]
        assert dso_ids == [ids["m42_id"], ids["ngc7000_id"]]

    def test_reorder_favorites(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        client.post(
            "/api/planner/wishlist/favorites",
            json={"dso_id": ids["m42_id"]},
        )
        client.post(
            "/api/planner/wishlist/favorites",
            json={"dso_id": ids["ngc7000_id"]},
        )
        resp = client.put(
            "/api/planner/wishlist/favorites/reorder",
            json={
                "items": [
                    {"dso_id": ids["ngc7000_id"], "sort_order": 0},
                    {"dso_id": ids["m42_id"], "sort_order": 1},
                ],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["dso_ids"] == [ids["ngc7000_id"], ids["m42_id"]]

    def test_favorites_full_empty(self, client):
        resp = client.get("/api/planner/wishlist/favorites/full")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_favorites_full_with_data(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        client.post(
            "/api/planner/wishlist/favorites",
            json={"dso_id": ids["m42_id"]},
        )
        resp = client.get("/api/planner/wishlist/favorites/full")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["dso"]["dso_id"] == ids["m42_id"]
        assert item["dso"]["primary_designation"] == "M 42"
        assert item["plan_count"] == 0
        assert item["plans"] == []


# ── Plans CRUD ───────────────────────────────────────────────────────────────


class TestPlans:
    def test_create_plan_with_date_ranges(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        client.post("/api/planner/wishlist/favorites", json={"dso_id": ids["m42_id"]})
        resp = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
                "date_ranges": [
                    {"start_date": "2026-06-01", "end_date": "2026-07-15"},
                    {"start_date": "2026-08-01", "end_date": "2026-09-30"},
                ],
                "notes": "Need 20h Ha+OIII",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["dso_id"] == ids["m42_id"]
        assert data["location_name"] == "Phoenix"
        assert len(data["date_ranges"]) == 2
        assert data["date_ranges"][0]["start_date"] == "2026-06-01"
        assert data["date_ranges"][1]["start_date"] == "2026-08-01"
        assert data["notes"] == "Need 20h Ha+OIII"

    def test_create_plan_no_date_ranges(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        resp = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
            },
        )
        assert resp.status_code == 201
        assert resp.json()["date_ranges"] == []

    def test_create_plan_auto_favorites(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        resp = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
            },
        )
        assert resp.status_code == 201
        fav_resp = client.get("/api/planner/wishlist/favorites")
        assert ids["m42_id"] in fav_resp.json()["dso_ids"]

    def test_create_plan_duplicate_409(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        plan_body = {
            "dso_id": ids["m42_id"],
            "location_id": ids["location_id"],
            "horizon_id": ids["horizon_id"],
            "rig_id": ids["rig_id"],
        }
        client.post("/api/planner/wishlist/plans", json=plan_body)
        resp = client.post("/api/planner/wishlist/plans", json=plan_body)
        assert resp.status_code == 409

    def test_create_plan_overlapping_ranges_422(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        resp = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
                "date_ranges": [
                    {"start_date": "2026-06-01", "end_date": "2026-07-15"},
                    {"start_date": "2026-07-10", "end_date": "2026-08-30"},
                ],
            },
        )
        assert resp.status_code == 422
        assert "overlap" in resp.json()["detail"].lower()

    def test_create_plan_invalid_location(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        resp = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": 99999,
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
            },
        )
        assert resp.status_code == 404

    def test_create_plan_horizon_wrong_location(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        resp = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["remote_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
            },
        )
        assert resp.status_code == 404
        assert "Horizon" in resp.json()["detail"]

    def test_update_plan_date_ranges(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        create_resp = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
            },
        )
        plan_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/planner/wishlist/plans/{plan_id}",
            json={
                "date_ranges": [
                    {"start_date": "2026-07-01", "end_date": "2026-09-30"},
                ],
                "notes": "Broadband only",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["date_ranges"]) == 1
        assert data["date_ranges"][0]["start_date"] == "2026-07-01"
        assert data["notes"] == "Broadband only"

    def test_update_plan_replace_date_ranges(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        create_resp = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
                "date_ranges": [
                    {"start_date": "2026-06-01", "end_date": "2026-07-15"},
                ],
            },
        )
        plan_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/planner/wishlist/plans/{plan_id}",
            json={
                "date_ranges": [
                    {"start_date": "2026-08-01", "end_date": "2026-09-30"},
                    {"start_date": "2026-10-15", "end_date": "2026-11-30"},
                ],
            },
        )
        assert resp.status_code == 200
        assert len(resp.json()["date_ranges"]) == 2

    def test_update_plan_clear_date_ranges(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        create_resp = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
                "date_ranges": [
                    {"start_date": "2026-06-01", "end_date": "2026-07-15"},
                ],
            },
        )
        plan_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/planner/wishlist/plans/{plan_id}",
            json={"date_ranges": []},
        )
        assert resp.status_code == 200
        assert resp.json()["date_ranges"] == []

    def test_update_plan_not_found(self, client):
        resp = client.put(
            "/api/planner/wishlist/plans/99999",
            json={"notes": "nope"},
        )
        assert resp.status_code == 404

    def test_delete_plan(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        create_resp = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
            },
        )
        plan_id = create_resp.json()["id"]

        resp = client.delete(f"/api/planner/wishlist/plans/{plan_id}")
        assert resp.status_code == 204

        list_resp = client.get("/api/planner/wishlist/plans")
        assert list_resp.json()["total"] == 0

    def test_list_plans_with_filter(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
            },
        )
        client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["ngc7000_id"],
                "location_id": ids["remote_id"],
                "horizon_id": ids["remote_hz_id"],
                "rig_id": ids["rig2_id"],
            },
        )

        all_resp = client.get("/api/planner/wishlist/plans")
        assert all_resp.json()["total"] == 2

        filtered_resp = client.get(
            "/api/planner/wishlist/plans",
            params={"location_id": ids["location_id"], "rig_id": ids["rig_id"]},
        )
        assert filtered_resp.json()["total"] == 1
        assert filtered_resp.json()["items"][0]["location_name"] == "Phoenix"

    def test_multiple_plans_per_target(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        resp1 = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
            },
        )
        assert resp1.status_code == 201

        resp2 = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["remote_id"],
                "horizon_id": ids["remote_hz_id"],
                "rig_id": ids["rig2_id"],
            },
        )
        assert resp2.status_code == 201

        all_resp = client.get("/api/planner/wishlist/plans")
        assert all_resp.json()["total"] == 2


# ── Cascade behavior ────────────────────────────────────────────────────────


class TestCascade:
    def test_unfavorite_cascades_plans(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
            },
        )
        plans_before = client.get("/api/planner/wishlist/plans")
        assert plans_before.json()["total"] == 1

        client.delete(f"/api/planner/wishlist/favorites/{ids['m42_id']}")

        plans_after = client.get("/api/planner/wishlist/plans")
        assert plans_after.json()["total"] == 0

    def test_favorites_full_includes_plans_with_ranges(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
                "date_ranges": [
                    {"start_date": "2026-06-01", "end_date": "2026-08-31"},
                ],
                "notes": "Test plan",
            },
        )
        resp = client.get("/api/planner/wishlist/favorites/full")
        data = resp.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["plan_count"] == 1
        plan = item["plans"][0]
        assert plan["location_name"] == "Phoenix"
        assert plan["notes"] == "Test plan"
        assert len(plan["date_ranges"]) == 1
        assert plan["date_ranges"][0]["start_date"] == "2026-06-01"

    def test_date_range_check_constraint(self, client, seed_dso_and_location):
        ids = seed_dso_and_location
        resp = client.post(
            "/api/planner/wishlist/plans",
            json={
                "dso_id": ids["m42_id"],
                "location_id": ids["location_id"],
                "horizon_id": ids["horizon_id"],
                "rig_id": ids["rig_id"],
                "date_ranges": [
                    {"start_date": "2026-09-01", "end_date": "2026-06-01"},
                ],
            },
        )
        assert resp.status_code == 422
