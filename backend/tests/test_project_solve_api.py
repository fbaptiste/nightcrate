"""Tests for project plate-solve + identified-DSO endpoints.

ASTAP and real image rendering are mocked; the WCS projection (astropy) and
DB layer run for real, so the best-match / store-all / cascade logic is
exercised end to end.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services.plate_solve_models import PlateSolveResult

_SCALE = 3.0 / 3600.0  # 3 arcsec/px in degrees

# A self-consistent solve: centre 210/+54, 3"/px, 4000×4000, no rotation.
_SOLVE = dict(
    solved=True,
    ra_deg=210.0,
    dec_deg=54.0,
    ra_hms="14 00 00.0",
    dec_dms="+54 00 00",
    pixel_scale_arcsec=3.0,
    rotation_deg=0.0,
    fov_width_arcmin=200.0,
    fov_height_arcmin=200.0,
    image_width=4000,
    image_height=4000,
    cd1_1=-_SCALE,
    cd1_2=0.0,
    cd2_1=0.0,
    cd2_2=_SCALE,
    crpix1=2000.0,
    crpix2=2000.0,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _dso_dict(dso_id: int, designation: str, ra: float, dec: float, maj: float) -> dict:
    return {
        "id": dso_id,
        "primary_designation": designation,
        "obj_type": "G",
        "type_group": "Galaxy",
        "ra_deg": ra,
        "dec_deg": dec,
        "maj_axis_arcmin": maj,
        "min_axis_arcmin": maj * 0.9,
        "position_angle_deg": 0.0,
        "common_name": None,
        "constellation": "UMa",
        "distance_pc": None,
        "distance_method": None,
        "mag_b": 9.0,
    }


async def _seed_two_dsos() -> tuple[int, int]:
    """Insert a big central DSO + a smaller offset one; return their ids."""
    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO dso_catalog_source"
            " (source_id, category, display_name, file_path, file_hash, row_count)"
            " VALUES ('test', 'openngc', 'Test', '/dev/null', 'abc', 0)"
        )
        cur = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        sid = int((await cur.fetchone())["id"])

        cur = await conn.execute(
            "INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg, constellation,"
            " maj_axis_arcmin, min_axis_arcmin, position_angle_deg, mag_b,"
            " source_catalog_id, source_row_hash)"
            " VALUES ('M 101', 'G', 210.0, 54.0, 'UMa', 28.0, 27.0, 0.0, 8.0, ?, 'h1')",
            (sid,),
        )
        big = cur.lastrowid
        cur = await conn.execute(
            "INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg, constellation,"
            " maj_axis_arcmin, min_axis_arcmin, position_angle_deg, mag_b,"
            " source_catalog_id, source_row_hash)"
            " VALUES ('NGC 5474', 'G', 210.1, 54.05, 'UMa', 4.8, 4.3, 0.0, 11.0, ?, 'h2')",
            (sid,),
        )
        small = cur.lastrowid
        await conn.commit()
    return big, small


@contextlib.contextmanager
def _mock_solve(dso_dicts: list[dict], result_kwargs: dict | None = None):
    """Patch ASTAP + cone query + render so the solve runs without external deps."""
    result = PlateSolveResult(**(result_kwargs or _SOLVE))
    with (
        patch(
            "nightcrate.api.project_solve.get_settings",
            new=AsyncMock(return_value=SimpleNamespace(astap_executable_path="/fake/astap")),
        ),
        patch(
            "nightcrate.api.project_solve.validate_astap_path",
            new=MagicMock(return_value={"valid": True, "error": None}),
        ),
        patch(
            "nightcrate.api.project_solve.run_plate_solve",
            new=AsyncMock(return_value=result),
        ),
        patch(
            "nightcrate.api.project_solve.query_dsos_in_cone",
            new=AsyncMock(return_value=dso_dicts),
        ),
        patch("nightcrate.api.project_solve.generate_rendered_images", new=MagicMock()),
    ):
        yield


async def _make_project(client: AsyncClient, name: str) -> int:
    r = await client.post("/api/projects", json={"name": name})
    return r.json()["id"]


class TestCreateSolve:
    async def test_stores_all_objects_and_flags_main(self, client: AsyncClient):
        big, small = await _seed_two_dsos()
        pid = await _make_project(client, "Solve Create")
        dsos = [
            _dso_dict(big, "M 101", 210.0, 54.0, 28.0),
            _dso_dict(small, "NGC 5474", 210.1, 54.05, 4.8),
        ]
        with _mock_solve(dsos):
            resp = await client.post(
                f"/api/projects/{pid}/solve", json={"image_path": "/fake/light.fits"}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["center_ra_deg"] == 210.0
        assert data["image_width"] == 4000
        # All identified objects stored (not just the main).
        assert {o["dso_id"] for o in data["objects"]} == {big, small}
        mains = [o for o in data["objects"] if o["is_main"]]
        assert len(mains) == 1
        assert mains[0]["dso_id"] == big  # central + largest
        # Overlay data present.
        assert data["wcs"]["naxis1"] == 4000
        assert all("pixel_x" in o for o in data["objects"])

    async def test_conflict_when_solve_exists(self, client: AsyncClient):
        big, small = await _seed_two_dsos()
        pid = await _make_project(client, "Solve Conflict")
        dsos = [_dso_dict(big, "M 101", 210.0, 54.0, 28.0)]
        with _mock_solve(dsos):
            await client.post(f"/api/projects/{pid}/solve", json={"image_path": "/fake/a.fits"})
            second = await client.post(
                f"/api/projects/{pid}/solve", json={"image_path": "/fake/b.fits"}
            )
        assert second.status_code == 409

    async def test_failed_solve_422(self, client: AsyncClient):
        pid = await _make_project(client, "Solve Fail")
        with _mock_solve([], result_kwargs={"solved": False, "error_message": "No stars"}):
            resp = await client.post(
                f"/api/projects/{pid}/solve", json={"image_path": "/fake/blank.fits"}
            )
        assert resp.status_code == 422
        assert "No stars" in resp.json()["detail"]

    async def test_no_astap_path_422(self, client: AsyncClient):
        pid = await _make_project(client, "No ASTAP")
        with patch(
            "nightcrate.api.project_solve.get_settings",
            new=AsyncMock(return_value=SimpleNamespace(astap_executable_path="")),
        ):
            resp = await client.post(
                f"/api/projects/{pid}/solve", json={"image_path": "/fake/x.fits"}
            )
        assert resp.status_code == 422

    async def test_solve_empty_field_stores_no_objects(self, client: AsyncClient):
        pid = await _make_project(client, "Empty Field")
        with _mock_solve([]):
            resp = await client.post(
                f"/api/projects/{pid}/solve", json={"image_path": "/fake/sparse.fits"}
            )
        assert resp.status_code == 200
        assert resp.json()["objects"] == []


class TestGetSolve:
    async def test_get_after_create(self, client: AsyncClient):
        big, _ = await _seed_two_dsos()
        pid = await _make_project(client, "Solve Get")
        with _mock_solve([_dso_dict(big, "M 101", 210.0, 54.0, 28.0)]):
            await client.post(f"/api/projects/{pid}/solve", json={"image_path": "/fake/a.fits"})
        resp = await client.get(f"/api/projects/{pid}/solve")
        assert resp.status_code == 200
        assert resp.json()["objects"][0]["dso_id"] == big

    async def test_get_204_when_no_solve(self, client: AsyncClient):
        pid = await _make_project(client, "No Solve")
        resp = await client.get(f"/api/projects/{pid}/solve")
        assert resp.status_code == 204


class TestSetMain:
    async def test_toggle_main_on(self, client: AsyncClient):
        big, small = await _seed_two_dsos()
        pid = await _make_project(client, "Set Main On")
        dsos = [
            _dso_dict(big, "M 101", 210.0, 54.0, 28.0),
            _dso_dict(small, "NGC 5474", 210.1, 54.05, 4.8),
        ]
        with _mock_solve(dsos):
            await client.post(f"/api/projects/{pid}/solve", json={"image_path": "/fake/a.fits"})
        # Add the small one as a second main (multi-main allowed).
        resp = await client.put(
            f"/api/projects/{pid}/solve/objects/{small}", json={"is_main": True}
        )
        assert resp.status_code == 200
        mains = {o["dso_id"] for o in resp.json()["objects"] if o["is_main"]}
        assert mains == {big, small}

    async def test_toggle_main_off(self, client: AsyncClient):
        big, _ = await _seed_two_dsos()
        pid = await _make_project(client, "Set Main Off")
        with _mock_solve([_dso_dict(big, "M 101", 210.0, 54.0, 28.0)]):
            await client.post(f"/api/projects/{pid}/solve", json={"image_path": "/fake/a.fits"})
        resp = await client.put(f"/api/projects/{pid}/solve/objects/{big}", json={"is_main": False})
        assert resp.status_code == 200
        assert all(not o["is_main"] for o in resp.json()["objects"])

    async def test_unknown_dso_404(self, client: AsyncClient):
        big, _ = await _seed_two_dsos()
        pid = await _make_project(client, "Set Main 404")
        with _mock_solve([_dso_dict(big, "M 101", 210.0, 54.0, 28.0)]):
            await client.post(f"/api/projects/{pid}/solve", json={"image_path": "/fake/a.fits"})
        resp = await client.put(f"/api/projects/{pid}/solve/objects/999999", json={"is_main": True})
        assert resp.status_code == 404

    async def test_set_main_no_solve_404(self, client: AsyncClient):
        pid = await _make_project(client, "Set Main No Solve")
        resp = await client.put(f"/api/projects/{pid}/solve/objects/1", json={"is_main": True})
        assert resp.status_code == 404


class TestDeleteSolve:
    async def test_delete_cascades_objects(self, client: AsyncClient):
        big, small = await _seed_two_dsos()
        pid = await _make_project(client, "Solve Delete")
        dsos = [
            _dso_dict(big, "M 101", 210.0, 54.0, 28.0),
            _dso_dict(small, "NGC 5474", 210.1, 54.05, 4.8),
        ]
        with _mock_solve(dsos):
            await client.post(f"/api/projects/{pid}/solve", json={"image_path": "/fake/a.fits"})

        assert (await client.delete(f"/api/projects/{pid}/solve")).status_code == 204
        assert (await client.get(f"/api/projects/{pid}/solve")).status_code == 204

        async with get_db() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM project_dso pd"
                " JOIN project_solve ps ON ps.id = pd.solve_id WHERE ps.project_id = ?",
                (pid,),
            )
            assert (await cur.fetchone())[0] == 0

    async def test_delete_no_solve_is_noop(self, client: AsyncClient):
        pid = await _make_project(client, "Delete No Solve")
        assert (await client.delete(f"/api/projects/{pid}/solve")).status_code == 204


class TestSolveImage:
    async def test_invalid_variant_422(self, client: AsyncClient):
        pid = await _make_project(client, "Solve Img Variant")
        resp = await client.get(f"/api/projects/{pid}/solve/image/bogus")
        assert resp.status_code == 422

    async def test_missing_image_204(self, client: AsyncClient):
        pid = await _make_project(client, "Solve Img Missing")
        resp = await client.get(f"/api/projects/{pid}/solve/image/full")
        assert resp.status_code == 204
