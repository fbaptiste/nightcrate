"""Home endpoint integration tests with hand-computed figures."""

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def test_empty_home_returns_every_empty_shape(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("nightcrate.api.home._today", lambda: date(2026, 11, 14))
    response = await client.get("/api/home")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["today"] == "2026-11-14"
    assert body["stages"] == {
        "not_started": 0,
        "capturing": 0,
        "ready_to_process": 0,
        "complete": 0,
        "paused": 0,
        "abandoned": 0,
    }
    assert body["total_projects"] == 0
    assert body["recent"] == body["rigs"] == body["locations"] == []
    assert body["forecast_locations"] == []
    assert body["latest_picture"] is None
    assert body["year"]["best_night"] is None
    assert len(body["year"]["months"]) == 12
    assert all(month["minutes"] == 0 for month in body["year"]["months"])


async def test_home_figures_reuse_integration_and_exclude_retired(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("nightcrate.api.home._today", lambda: date(2026, 11, 14))
    async with get_db() as conn:
        maker = (
            await conn.execute("INSERT INTO manufacturer (name) VALUES ('Home maker')")
        ).lastrowid
        filter_type = (
            await conn.execute(
                "INSERT INTO filter_type (name, display_name) VALUES ('home', 'Home')"
            )
        ).lastrowid
        dual = (
            await conn.execute(
                "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) "
                "VALUES (?, ?, 'Dual')",
                (maker, filter_type),
            )
        ).lastrowid
        await conn.executemany(
            "INSERT INTO filter_passband (filter_id, line_name, central_wavelength_nm) "
            "VALUES (?, ?, ?)",
            [(dual, "Ha", 656.3), (dual, "Oiii", 500.7)],
        )

        project_ids = {}
        for name, status in (
            ("Dual project", "active"),
            ("Ready project", "ready_to_process"),
            ("Complete project", "complete"),
            ("Paused project", "paused"),
            ("Abandoned project", "abandoned"),
            ("Retired project", "active"),
        ):
            cursor = await conn.execute(
                "INSERT INTO project (name, status) VALUES (?, ?)", (name, status)
            )
            project_ids[name] = cursor.lastrowid
        await conn.execute(
            "UPDATE project SET active = 0 WHERE id = ?", (project_ids["Retired project"],)
        )
        await conn.executemany(
            """
            INSERT INTO project_session
                (project_id, filter_id, line_name, filter_label,
                 exposure_seconds, num_subs, session_date, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (project_ids["Dual project"], dual, None, None, 300, 12, "2026-11-10", "manual"),
                (
                    project_ids["Dual project"],
                    None,
                    "other",
                    "Mystery",
                    60,
                    30,
                    None,
                    "auto",
                ),
                (
                    project_ids["Complete project"],
                    None,
                    "Lum",
                    None,
                    60,
                    10,
                    "2025-12-01",
                    "manual",
                ),
                (project_ids["Complete project"], None, "Lum", None, 60, 5, "2025-11-30", "manual"),
                (
                    project_ids["Retired project"],
                    None,
                    "Lum",
                    None,
                    600,
                    60,
                    "2026-11-12",
                    "manual",
                ),
            ],
        )
        await conn.executemany(
            "INSERT INTO project_image (project_id, file_path, is_main, created_at) "
            "VALUES (?, ?, 1, ?)",
            [
                (project_ids["Dual project"], "/synthetic/dual.jpg", "2026-11-10 23:30:00"),
                (project_ids["Retired project"], "/synthetic/retired.jpg", "2026-11-13 12:00:00"),
            ],
        )
        await conn.commit()

    response = await client.get("/api/home")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_projects"] == 5
    assert body["stages"] == {
        "not_started": 0,
        "capturing": 1,
        "ready_to_process": 1,
        "complete": 1,
        "paused": 1,
        "abandoned": 1,
    }
    assert [item["name"] for item in body["recent"]] == ["Dual project", "Complete project"]
    dual_home = body["recent"][0]
    assert dual_home["total_minutes"] == 90
    assert dual_home["nights"] == 1
    assert dual_home["last_date"] == "2026-11-10"
    assert dual_home["has_image"] is True
    assert [(line["label"], line["minutes"]) for line in dual_home["lines"]] == [
        ("Ha", 60),
        ("Oiii", 60),
        ("Mystery", 30),
    ]
    integration = (
        await client.get(f"/api/projects/{project_ids['Dual project']}/integration")
    ).json()
    assert dual_home["total_minutes"] == integration["total_actual_minutes"]
    assert [line["label"] for line in dual_home["lines"]] == [
        line["label"] for line in integration["lines"]
    ]
    assert body["latest_picture"]["project_id"] == project_ids["Dual project"]
    assert body["year"]["minutes"] == 70
    assert body["year"]["nights"] == 2
    assert body["year"]["new_pictures"] == 1


async def test_home_rig_location_ordering_retirement_and_caps(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("nightcrate.api.home._today", lambda: date(2026, 11, 14))
    async with get_db() as conn:
        maker = (
            await conn.execute("INSERT INTO manufacturer (name) VALUES ('Panel maker')")
        ).lastrowid
        telescope = (
            await conn.execute(
                "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) "
                "VALUES (?, 'Panel scope', 100)",
                (maker,),
            )
        ).lastrowid
        configuration = (
            await conn.execute(
                """
                INSERT INTO telescope_configuration
                    (telescope_id, config_name, effective_focal_length_mm,
                     effective_focal_ratio, is_native)
                VALUES (?, 'Native', 500, 5, 1)
                """,
                (telescope,),
            )
        ).lastrowid
        sensor = (
            await conn.execute(
                """
                INSERT INTO sensor
                    (manufacturer_id, model_name, sensor_type, pixel_size_um,
                     resolution_x, resolution_y, adc_bit_depth)
                VALUES (?, 'Panel sensor', 'mono', 3.76, 1000, 800, 16)
                """,
                (maker,),
            )
        ).lastrowid
        camera = (
            await conn.execute(
                "INSERT INTO camera (manufacturer_id, sensor_id, model_name) "
                "VALUES (?, ?, 'Panel camera')",
                (maker, sensor),
            )
        ).lastrowid

        rig_ids = []
        for index in range(7):
            cursor = await conn.execute(
                """
                INSERT INTO rig
                    (name, telescope_configuration_id, camera_id, is_mine, sort_order)
                VALUES (?, ?, ?, 1, ?)
                """,
                (f"Rig {index}", configuration, camera, index),
            )
            rig_ids.append(cursor.lastrowid)
        retired_rig = (
            await conn.execute(
                """
                INSERT INTO rig
                    (name, telescope_configuration_id, camera_id, is_mine, active)
                VALUES ('Retired rig', ?, ?, 1, 0)
                """,
                (configuration, camera),
            )
        ).lastrowid
        other_rig = (
            await conn.execute(
                """
                INSERT INTO rig
                    (name, telescope_configuration_id, camera_id, is_mine)
                VALUES ('Not my rig', ?, ?, 0)
                """,
                (configuration, camera),
            )
        ).lastrowid

        location_ids = []
        for index in range(7):
            cursor = await conn.execute(
                """
                INSERT INTO location
                    (name, latitude, longitude, timezone, is_default)
                VALUES (?, 33.4484, -112.0740, 'America/Phoenix', ?)
                """,
                (f"Location {index}", index == 0),
            )
            location_ids.append(cursor.lastrowid)
        retired_location = (
            await conn.execute(
                """
                INSERT INTO location
                    (name, latitude, longitude, timezone, active)
                VALUES ('Retired location', 33.4484, -112.0740, 'America/Phoenix', 0)
                """
            )
        ).lastrowid

        project_id = (
            await conn.execute(
                "INSERT INTO project (name, location_id) VALUES ('Panel project', ?)",
                (location_ids[0],),
            )
        ).lastrowid
        old_project = (
            await conn.execute(
                "INSERT INTO project (name, location_id) VALUES ('Old project', ?)",
                (location_ids[1],),
            )
        ).lastrowid
        hidden_location_project = (
            await conn.execute(
                "INSERT INTO project (name, location_id) VALUES ('Hidden location', ?)",
                (retired_location,),
            )
        ).lastrowid
        await conn.execute(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            (project_id, rig_ids[0]),
        )
        await conn.executemany(
            """
            INSERT INTO project_session
                (project_id, rig_id, line_name, exposure_seconds, num_subs, session_date)
            VALUES (?, ?, 'Lum', ?, 1, ?)
            """,
            [
                (project_id, rig_ids[0], 7200, "2026-11-10"),
                (project_id, retired_rig, 1800, "2026-11-10"),
                (project_id, other_rig, 600, "2026-11-10"),
                (old_project, rig_ids[1], 3600, "2025-11-30"),
                (hidden_location_project, rig_ids[2], 1200, "2026-11-09"),
            ],
        )
        await conn.commit()

    response = await client.get("/api/home")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["rigs"]) == 5
    assert body["rigs"][0] == {
        "rig_id": rig_ids[0],
        "name": "Rig 0",
        "minutes": 120,
        "nights": 1,
        "last_used": "2026-11-10",
        "active_projects": 1,
    }
    assert all(item["name"] not in {"Retired rig", "Not my rig"} for item in body["rigs"])
    old_rig = next(item for item in body["rigs"] if item["rig_id"] == rig_ids[1])
    assert old_rig["minutes"] == old_rig["nights"] == 0
    assert old_rig["last_used"] == "2025-11-30"

    assert len(body["locations"]) == 5
    assert body["locations"][0]["location_id"] == location_ids[0]
    assert body["locations"][0]["minutes"] == 160
    assert all(item["location_id"] != retired_location for item in body["locations"])
    # The default, the location an active project uses, then spare rows by name.
    assert [item["location_id"] for item in body["forecast_locations"]] == [
        location_ids[0],
        location_ids[1],
        location_ids[2],
        location_ids[3],
    ]
    assert [item["note"] for item in body["forecast_locations"]] == [
        "default",
        "used",
        None,
        None,
    ]
    assert all(item["location_id"] != retired_location for item in body["forecast_locations"])
