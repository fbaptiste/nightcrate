from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _source(conn) -> int:
    cursor = await conn.execute(
        """
        INSERT INTO dso_catalog_source
            (source_id, category, display_name, file_path, file_hash)
        VALUES ('messier-api', 'nightcrate', 'Messier API', '/synthetic', 'hash')
        """
    )
    return int(cursor.lastrowid)


async def _messier(
    conn,
    source_id: int,
    number: int,
    *,
    primary: str | None = None,
    dec: float = 20,
    active: int = 1,
    maj: float | None = 10,
    min_axis: float | None = 5,
) -> int:
    cursor = await conn.execute(
        """
        INSERT INTO dso (
            primary_designation, obj_type, ra_deg, dec_deg, constellation,
            common_name, mag_v, maj_axis_arcmin, min_axis_arcmin,
            source_catalog_id, source_row_hash, source_key, active
        ) VALUES (?, 'G', ?, ?, 'And', ?, 8.5, ?, ?, ?, ?, ?, ?)
        """,
        (
            primary or f"M {number}",
            float(number),
            dec,
            f"Object {number}",
            maj,
            min_axis,
            source_id,
            f"row-{number}",
            f"m-{number}",
            active,
        ),
    )
    dso_id = int(cursor.lastrowid)
    await conn.execute(
        """
        INSERT INTO dso_designation
            (dso_id, catalog, identifier, display_form, search_key, is_primary)
        VALUES (?, 'messier', ?, ?, ?, 1)
        """,
        (dso_id, str(number), f"M {number}", f"m{number}"),
    )
    return dso_id


async def _project(
    conn,
    name: str,
    targets: list[int],
    *,
    active: int = 1,
    image: bool = False,
    created_at: str = "2026-01-01",
    dates: tuple[str, ...] = (),
) -> tuple[int, int | None]:
    cursor = await conn.execute(
        "INSERT INTO project (name, active, created_at) VALUES (?, ?, ?)",
        (name, active, created_at),
    )
    project_id = int(cursor.lastrowid)
    for dso_id in targets:
        await conn.execute(
            "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
            (project_id, dso_id),
        )
    image_id = None
    if image:
        image_cursor = await conn.execute(
            """
            INSERT INTO project_image (project_id, file_path, is_main)
            VALUES (?, ?, 1)
            """,
            (project_id, f"/synthetic/{name}.jpg"),
        )
        image_id = int(image_cursor.lastrowid)
    for session_date in dates:
        await conn.execute(
            """
            INSERT INTO project_session
                (project_id, line_name, exposure_seconds, num_subs, session_date)
            VALUES (?, 'Ha', 300, 1, ?)
            """,
            (project_id, session_date),
        )
    return project_id, image_id


async def test_110_slots_m102_states_counts_retired_and_one_project_three_slots(
    client: AsyncClient,
):
    async with get_db() as conn:
        source = await _source(conn)
        m1 = await _messier(conn, source, 1)
        m31 = await _messier(conn, source, 31)
        m32 = await _messier(conn, source, 32)
        m101 = await _messier(conn, source, 101, primary="NGC 5457", active=0)
        m102 = await _messier(conn, source, 102, primary="NGC 5866")
        m110 = await _messier(conn, source, 110)
        await conn.execute(
            "INSERT INTO dso_other_name (dso_id, name, position) VALUES (?, 'Spindle Galaxy', 1)",
            (m102,),
        )
        imaged_id, image_id = await _project(conn, "Imaged", [m1], image=True)
        await _project(conn, "Three slots", [m31, m32, m110])
        retired_id, _ = await _project(conn, "Retired", [m101], active=0, image=True)
        await conn.commit()

    response = await client.get("/api/messier", params={"location": "none"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["catalog_status"] == "ready"
    assert [slot["number"] for slot in body["slots"]] == list(range(1, 111))
    slots = {slot["number"]: slot for slot in body["slots"]}
    assert slots[1]["state"] == "imaged"
    assert slots[1]["projects"][0]["project_id"] == imaged_id
    assert slots[1]["projects"][0]["main_image_id"] == image_id
    assert [slots[number]["state"] for number in (31, 32, 110)] == [
        "project",
        "project",
        "project",
    ]
    assert slots[101]["object"]["active"] is False
    assert slots[101]["state"] == "none"
    assert slots[102]["object"]["designation"] == "M 102"
    assert slots[102]["object"]["dso_id"] == m102
    assert slots[102]["object"]["other_names"] == ["Spindle Galaxy"]
    assert slots[2]["state"] == "missing"
    assert body["counts"] == {
        "imaged": 1,
        "project": 3,
        "never_rises": 0,
        "missing": 104,
        "in_solved": 0,
    }
    assert all(
        project["project_id"] != retired_id
        for slot in body["slots"]
        for project in slot["projects"]
    )

    async with get_db() as conn:
        await conn.execute("UPDATE project SET active = 1 WHERE id = ?", (retired_id,))
        await conn.commit()
    restored = (await client.get("/api/messier", params={"location": "none"})).json()
    assert restored["slots"][100]["state"] == "imaged"


async def test_ordering_ties_through_api(client: AsyncClient):
    async with get_db() as conn:
        source = await _source(conn)
        dso_id = await _messier(conn, source, 1)
        a, _ = await _project(conn, "A", [dso_id], image=True, dates=("2025-03-01",))
        b, _ = await _project(conn, "B", [dso_id], dates=("2026-01-01",))
        c, _ = await _project(conn, "C", [dso_id], image=True, created_at="2026-02-01")
        d, _ = await _project(conn, "D", [dso_id], image=True, created_at="2026-02-01")
        await conn.commit()
    body = (await client.get("/api/messier", params={"location": "none"})).json()
    assert [item["project_id"] for item in body["slots"][0]["projects"]] == [a, d, c, b]


async def test_not_downloaded_only_without_files_and_designations(
    client: AsyncClient,
    tmp_path: Path,
):
    empty = (await client.get("/api/messier")).json()
    assert empty["catalog_status"] == "not_downloaded"
    assert empty["slots"] == []

    openngc = tmp_path / "catalogs" / "openngc"
    openngc.mkdir(parents=True)
    (openngc / "NGC.csv").write_text("synthetic")
    with_file = (await client.get("/api/messier")).json()
    assert with_file["catalog_status"] == "ready"
    assert len(with_file["slots"]) == 110


async def test_location_default_none_id_deleted_invalid_and_never_rises(client: AsyncClient):
    async with get_db() as conn:
        source = await _source(conn)
        m40 = await _messier(conn, source, 40, dec=58.0844)
        await _messier(conn, source, 102, primary="NGC 5866", dec=55.7632)
        imaged = await _messier(conn, source, 101, dec=58.5)
        await _project(conn, "Image", [imaged], image=True)
        default = await conn.execute(
            """
            INSERT INTO location
                (name, latitude, longitude, timezone, is_default)
            VALUES ('South', -35, 20, 'UTC', 1)
            """
        )
        other = await conn.execute(
            """
            INSERT INTO location (name, latitude, longitude, timezone)
            VALUES ('North', 35, 20, 'UTC')
            """
        )
        deleted = await conn.execute(
            """
            INSERT INTO location (name, latitude, longitude, timezone, active)
            VALUES ('Deleted', 0, 20, 'UTC', 0)
            """
        )
        await conn.commit()

    default_body = (await client.get("/api/messier")).json()
    assert default_body["location"]["id"] == default.lastrowid
    assert default_body["slots"][39]["object"]["dso_id"] == m40
    assert default_body["slots"][39]["never_rises"] is True
    assert default_body["slots"][101]["never_rises"] is False
    assert default_body["slots"][100]["never_rises"] is False
    assert default_body["counts"]["never_rises"] == 1

    none = (await client.get("/api/messier", params={"location": "none"})).json()
    assert none["location"] is None
    by_id = (await client.get("/api/messier", params={"location": other.lastrowid})).json()
    assert by_id["location"]["id"] == other.lastrowid
    fallback = (await client.get("/api/messier", params={"location": deleted.lastrowid})).json()
    assert fallback["location"]["id"] == default.lastrowid
    assert (await client.get("/api/messier", params={"location": "abc"})).status_code == 422


async def test_project_omits_picture_fields_and_includes_survey_render_key(
    client: AsyncClient,
):
    async with get_db() as conn:
        source = await _source(conn)
        dso_id = await _messier(conn, source, 31, maj=190)
        project_id, _ = await _project(conn, "Fields", [dso_id], image=True)
        await conn.commit()

    body = (await client.get("/api/messier", params={"location": "none"})).json()
    slot = body["slots"][30]
    assert "picture_fields" not in slot
    assert slot["projects"][0]["project_id"] == project_id
    assert "picture_fields" not in slot["projects"][0]
    assert slot["survey"] == {
        "field_deg": 4.75,
        "render_key": "r1_ra310000_dec200000_f4750_800x600",
    }
    assert slot["coverage_pct"] is None


async def test_object_only_in_active_solved_picture_is_reported_without_becoming_imaged(
    client: AsyncClient,
):
    async with get_db() as conn:
        source = await _source(conn)
        m84 = await _messier(conn, source, 84)
        m86 = await _messier(conn, source, 86)
        m87 = await _messier(conn, source, 87, dec=12.391123)
        for dso_id, ra_deg, dec_deg, major, minor, angle in (
            (m84, 186.265597, 12.886983, 7.41, 6.44, 133),
            (m86, 186.549225, 12.945969, 11.53, 8.43, 128),
            (m87, 187.70593, 12.391123, 7.11, 6.67, 153),
        ):
            await conn.execute(
                """
                UPDATE dso
                SET ra_deg = ?, dec_deg = ?, maj_axis_arcmin = ?,
                    min_axis_arcmin = ?, position_angle_deg = ?
                WHERE id = ?
                """,
                (ra_deg, dec_deg, major, minor, angle, dso_id),
            )
        project_id, _ = await _project(conn, "Markarian's Chain", [m84, m86], image=True)
        scale = 2.3 / 1200.0
        await conn.execute(
            """
            INSERT INTO project_solve (
                project_id, image_path, image_width, image_height,
                center_ra_deg, center_dec_deg, pixel_scale_arcsec,
                fov_width_arcmin, fov_height_arcmin,
                cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2
            ) VALUES (?, '/markarian.fits', 1200, 900, 186.78, 13.06, ?,
                      138, 103.5, ?, 0, 0, ?, 601, 451)
            """,
            (project_id, scale * 3600, -scale, -scale),
        )
        retired_id, _ = await _project(conn, "Retired Markarian", [], active=0)
        await conn.execute(
            """
            INSERT INTO project_solve (
                project_id, image_path, image_width, image_height,
                center_ra_deg, center_dec_deg, cd1_1, cd1_2, cd2_1, cd2_2,
                crpix1, crpix2
            ) VALUES (?, '/retired.fits', 1200, 900, 186.78, 13.06,
                      ?, 0, 0, ?, 601, 451)
            """,
            (retired_id, -scale, -scale),
        )
        await conn.commit()

    body = (await client.get("/api/messier", params={"location": "none"})).json()
    slots = {slot["number"]: slot for slot in body["slots"]}
    assert slots[84]["state"] == "imaged"
    assert slots[84]["in_solved_pictures"] == []
    assert slots[87]["state"] == "none"
    assert slots[87]["in_solved_pictures"] == [
        {"project_id": project_id, "name": "Markarian's Chain"}
    ]
    assert body["counts"]["in_solved"] == 1


async def test_rig_fov_missing_retired_incomplete_and_planner_unchanged(
    client: AsyncClient,
    monkeypatch,
):
    from nightcrate.api.planner import _load_rig_fov
    from nightcrate.services.rig_calculators import rig_fov_from_summary

    async with get_db() as conn:
        source = await _source(conn)
        await _messier(conn, source, 1, maj=8.0, min_axis=4.0)
        await _messier(conn, source, 31, maj=177.83, min_axis=69.66)
        equipment = await (
            await conn.execute(
                """
                SELECT tc.id AS configuration_id, c.id AS camera_id
                FROM telescope_configuration tc
                CROSS JOIN camera c
                JOIN sensor s ON s.id = c.sensor_id
                WHERE tc.effective_focal_length_mm IS NOT NULL
                ORDER BY tc.id, c.id
                LIMIT 1
                """
            )
        ).fetchone()
        rig = await conn.execute(
            """
            INSERT INTO rig (name, telescope_configuration_id, camera_id)
            VALUES ('Messier rig', ?, ?)
            """,
            (equipment["configuration_id"], equipment["camera_id"]),
        )
        rig_id = int(rig.lastrowid)
        await conn.commit()
        summary = await (
            await conn.execute("SELECT * FROM rig_summary WHERE id = ?", (rig_id,))
        ).fetchone()
        expected = rig_fov_from_summary(summary)
        planner_summary, planner_major, planner_minor = await _load_rig_fov(conn, rig_id)
        assert expected is not None
        assert (planner_major, planner_minor) == expected
        assert planner_summary.fov_major_deg == round(expected[0], 4)
        assert planner_summary.fov_minor_deg == round(expected[1], 4)

    ready = (await client.get("/api/messier", params={"rig_id": rig_id})).json()
    assert ready["rig"]["id"] == rig_id
    assert ready["rig"]["fov_major_deg"] == pytest.approx(expected[0])
    assert ready["rig"]["fov_minor_deg"] == pytest.approx(expected[1])
    assert ready["rig"]["view_field_deg"] is not None

    monkeypatch.setattr(
        "nightcrate.api.messier.rig_fov_from_summary",
        lambda _row: (2.80, 1.86),
    )
    rig_view = (await client.get("/api/messier", params={"rig_id": rig_id})).json()
    slots = {slot["number"]: slot for slot in rig_view["slots"]}
    assert rig_view["rig"]["view_field_deg"] == pytest.approx(3.043478)
    assert slots[1]["survey"] == {
        "field_deg": 3.043,
        "render_key": "r1_ra10000_dec200000_f3043_800x600",
    }
    assert slots[1]["coverage_pct"] == 4.8
    assert slots[31]["coverage_pct"] == 105.9

    for major, expected_view in (
        (0.0276, None),
        (0.046, 0.05),
        (27.6, 30.0),
        (36.8, None),
    ):
        monkeypatch.setattr(
            "nightcrate.api.messier.rig_fov_from_summary",
            lambda _row, major=major: (major, 0.01),
        )
        bounded = (await client.get("/api/messier", params={"rig_id": rig_id})).json()
        assert bounded["rig"]["view_field_deg"] == expected_view
        bounded_m1 = bounded["slots"][0]
        assert bounded_m1["coverage_pct"] is not None
        if expected_view is None:
            assert bounded_m1["survey"] == {
                "field_deg": 0.2,
                "render_key": "r1_ra10000_dec200000_f200_800x600",
            }
        else:
            assert bounded_m1["survey"]["field_deg"] == expected_view

    missing = (await client.get("/api/messier", params={"rig_id": 999999})).json()
    assert missing["rig"] is None

    async with get_db() as conn:
        await conn.execute("UPDATE rig SET active = 0 WHERE id = ?", (rig_id,))
        await conn.commit()
    retired = (await client.get("/api/messier", params={"rig_id": rig_id})).json()
    assert retired["rig"] is None

    async with get_db() as conn:
        await conn.execute("UPDATE rig SET active = 1 WHERE id = ?", (rig_id,))
        await conn.commit()
    monkeypatch.setattr("nightcrate.api.messier.rig_fov_from_summary", lambda _row: None)
    incomplete = (await client.get("/api/messier", params={"rig_id": rig_id})).json()
    assert incomplete["rig"] == {
        "id": rig_id,
        "name": "Messier rig",
        "fov_major_deg": None,
        "fov_minor_deg": None,
        "view_field_deg": None,
    }
    incomplete_slots = {slot["number"]: slot for slot in incomplete["slots"]}
    assert incomplete_slots[1]["survey"] == {
        "field_deg": 0.2,
        "render_key": "r1_ra10000_dec200000_f200_800x600",
    }
    assert incomplete_slots[1]["coverage_pct"] is None
