"""API tests for project object and imaging information."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services.astronomy import midnight_meridian_date
from tests.gallery_library import make_library_dsos
from tests.test_gallery_api import _project, _solve, _target


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def test_info_solved_project_has_wcs_and_date(client: AsyncClient):
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        project_id = await _project(conn, "Cygnus field")
        await _target(conn, project_id, dsos.ids["m31"])
        await _solve(
            conn,
            project_id,
            [dsos.ids["m31"], dsos.ids["m42"], dsos.ids["m32"]],
            center_ra_deg=315.11,
            center_dec_deg=43.61,
        )
        await conn.execute(
            """
            UPDATE project_solve
            SET ra_hms = '21:00:26', dec_dms = '+43:36:36',
                fov_width_arcmin = 125.4, fov_height_arcmin = 63.0,
                rotation_deg = 17.5,
                image_width = 6016, image_height = 4016,
                cd1_1 = -0.00021, cd1_2 = 0.00003,
                cd2_1 = 0.00004, cd2_2 = 0.00022,
                crpix1 = 3008.5, crpix2 = 2008.5
            WHERE project_id = ?
            """,
            (project_id,),
        )
        solve = await (
            await conn.execute(
                "SELECT id FROM project_solve WHERE project_id = ?",
                (project_id,),
            )
        ).fetchone()
        assert solve is not None
        solve_id = int(solve["id"])
        await conn.execute(
            "UPDATE dso SET distance_pc = 10000000, distance_method = 'curated' WHERE id = ?",
            (dsos.ids["m32"],),
        )
        await conn.commit()

    response = await client.get(f"/api/projects/{project_id}/info")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["solved"] is True
    assert body["field"]["constellation"] == "Cyg"
    assert body["field"]["fov_width_deg"] == pytest.approx(125.4 / 60)
    assert body["field"]["solve_id"] == solve_id
    assert body["field"]["wcs"] == {
        "crval1": 315.11,
        "crval2": 43.61,
        "crpix1": 3008.5,
        "crpix2": 2008.5,
        "cd1_1": -0.00021,
        "cd1_2": 0.00003,
        "cd2_1": 0.00004,
        "cd2_2": 0.00022,
        "width": 6016,
        "height": 4016,
    }
    midnight_month, midnight_day = midnight_meridian_date(315.11, datetime.now(UTC).year)
    assert body["field"]["midnight_meridian_month"] == midnight_month
    assert body["field"]["midnight_meridian_day"] == midnight_day
    assert [item["designation"] for item in body["other_objects"]] == ["M 32", "M 42"]


async def test_info_unsolved_project(client: AsyncClient):
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        project_id = await _project(conn, "Not solved")
        await _target(conn, project_id, dsos.ids["m31"])
        await conn.commit()

    body = (await client.get(f"/api/projects/{project_id}/info")).json()

    assert body["solved"] is False
    assert body["field"] is None
    assert [target["dso_id"] for target in body["targets"]] == [dsos.ids["m31"]]
    assert body["other_objects"] == []


async def test_info_matches_gallery(client: AsyncClient):
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        project_id = await _project(conn, "Same facts")
        await _target(conn, project_id, dsos.ids["m31"])
        await _solve(conn, project_id, [dsos.ids["m31"], dsos.ids["m32"]])
        await conn.execute(
            "UPDATE dso SET distance_pc = 10000000, distance_method = 'redshift' WHERE id = ?",
            (dsos.ids["m32"],),
        )
        rig = await conn.execute(
            """
            INSERT INTO rig (name, telescope_configuration_id, camera_id, active, sort_order)
            VALUES ('Info rig', 1, 1, 1, 0)
            """
        )
        await conn.execute(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            (project_id, rig.lastrowid),
        )
        await conn.execute(
            """
            INSERT INTO project_session (
                project_id, rig_id, line_name, exposure_seconds, num_subs, session_date
            ) VALUES (?, ?, 'Lum', 300, 12, '2026-11-10')
            """,
            (project_id, rig.lastrowid),
        )
        await conn.commit()

    info = (await client.get(f"/api/projects/{project_id}/info")).json()
    gallery = (await client.get("/api/gallery")).json()
    item = next(item for item in gallery["items"] if item["project_id"] == project_id)

    for key in (
        "targets",
        "other_distances",
        "nights",
        "imaging_runs",
        "integration_minutes",
        "rigs",
    ):
        assert info[key] == item[key]


async def test_info_missing_project_404(client: AsyncClient):
    response = await client.get("/api/projects/999999/info")
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
