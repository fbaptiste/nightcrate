"""API-level tests for the plate solve endpoints."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app
from nightcrate.services import solve_operations
from nightcrate.services.plate_solve_models import SolveAttempt
from nightcrate.services.star_catalog import handles
from tests.native_solver.test_solve_image import _install_real_assets


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def reset_solve_operations():
    solve_operations._reset_for_tests()
    yield
    solve_operations._reset_for_tests()


class TestValidatePath:
    @pytest.mark.anyio
    async def test_valid_executable(self, client, tmp_path):
        exe = tmp_path / "astap"
        exe.write_text("#!/bin/sh")
        exe.chmod(0o755)
        resp = await client.post(
            "/api/plate-solve/validate-path",
            params={"path": str(exe)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["resolved_path"] == str(exe)

    @pytest.mark.anyio
    async def test_nonexistent_path(self, client):
        resp = await client.post(
            "/api/plate-solve/validate-path",
            params={"path": "/nonexistent/astap"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] is not None

    @pytest.mark.anyio
    async def test_macos_app_bundle(self, client, tmp_path):
        app_dir = tmp_path / "ASTAP.app"
        macos = app_dir / "Contents" / "MacOS"
        macos.mkdir(parents=True)
        exe = macos / "astap"
        exe.write_text("#!/bin/sh")
        exe.chmod(0o755)
        resp = await client.post(
            "/api/plate-solve/validate-path",
            params={"path": str(app_dir)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["resolved_path"] == str(exe)


class TestSolveEndpoint:
    @pytest.mark.anyio
    async def test_solve_route_astap_requires_path(self, client, tmp_path):
        resp = await client.post(
            "/api/plate-solve/solve",
            json={
                "image_path": str(tmp_path / "test.fits"),
                "operation_id": str(uuid4()),
                "solver": "astap",
            },
        )
        assert resp.status_code == 422
        assert "not configured" in resp.json()["detail"].lower()

    @pytest.mark.anyio
    async def test_solve_route_native_default_without_astap(self, client, tmp_path, monkeypatch):
        case = _install_real_assets(tmp_path, monkeypatch, seed=812)
        path = tmp_path / "native-default.fits"
        hdu = fits.PrimaryHDU(np.asarray(case.image, dtype=np.float32))
        hdu.header["RA"] = case.truth.crval_ra
        hdu.header["DEC"] = case.truth.crval_dec
        hdu.header["XPIXSZ"] = 3.76
        hdu.header["FOCALLEN"] = 206.265 * 3.76 / case.truth.scale_arcsec
        hdu.writeto(path)
        try:
            response = await client.post(
                "/api/plate-solve/solve",
                json={"image_path": str(path), "operation_id": str(uuid4())},
            )
        finally:
            handles.close_all()
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["solved"] is True
        assert payload["solver"] == "native"
        assert payload["solve_path"] == "near_index"

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "payload",
        [
            {"ra_hint": 10.0},
            {"ra_hint": 360.0, "dec_hint": 0.0},
            {"ra_hint": 10.0, "dec_hint": 91.0},
            {"scale_hint_arcsec": 0.0},
            {"fov_hint": -1.0},
            {"hdu": -1},
            {"position": "none", "ra_hint": 10.0, "dec_hint": 20.0},
            {"scale": "none", "scale_hint_arcsec": 1.0},
        ],
    )
    async def test_invalid_hint_contract_returns_422(self, client, payload):
        response = await client.post(
            "/api/plate-solve/solve",
            json={"image_path": "/fake/image.fits", "operation_id": str(uuid4()), **payload},
        )
        assert response.status_code == 422

    @pytest.mark.anyio
    async def test_removed_mode_returns_422(self, client):
        response = await client.post(
            "/api/plate-solve/solve",
            json={
                "image_path": "/fake/image.fits",
                "operation_id": str(uuid4()),
                "mode": "blind",
            },
        )
        assert response.status_code == 422

    @pytest.mark.anyio
    async def test_solve_requires_operation_id(self, client):
        response = await client.post(
            "/api/plate-solve/solve",
            json={"image_path": "/fake/image.fits"},
        )

        assert response.status_code == 422


class TestSolveOperationsApi:
    @pytest.mark.anyio
    async def test_structured_progress(self, client):
        operation_id = uuid4()
        operation = solve_operations.claim(operation_id, "native")
        operation.plan(["near_index", "blind_known_scale"])
        operation.start(
            SolveAttempt(
                solver="native",
                step="near_index",
                position_source="request",
                scale_source="header",
            )
        )

        structured = await client.get(
            "/api/plate-solve/progress", params={"operation_id": str(operation_id)}
        )

        assert structured.status_code == 200
        assert structured.json()["active_step"]["step"] == "near_index"
        assert structured.json()["planned"] == ["blind_known_scale"]
        solve_operations.release(operation)

    @pytest.mark.anyio
    async def test_progress_and_cancel_require_operation_id(self, client):
        progress = await client.get("/api/plate-solve/progress")
        cancel = await client.post("/api/plate-solve/cancel")

        assert progress.status_code == 422
        assert cancel.status_code == 422

    @pytest.mark.anyio
    async def test_unknown_progress_returns_404(self, client):
        response = await client.get(
            "/api/plate-solve/progress", params={"operation_id": str(uuid4())}
        )
        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_cancel_before_claim_stops_endpoint_before_solver(self, client):
        operation_id = uuid4()
        cancelled = await client.post(
            "/api/plate-solve/cancel", json={"operation_id": str(operation_id)}
        )
        runner = AsyncMock(side_effect=AssertionError("solver ran"))
        with patch("nightcrate.api.plate_solve.run_solve", new=runner):
            response = await client.post(
                "/api/plate-solve/solve",
                json={"image_path": "/fake/image.fits", "operation_id": str(operation_id)},
            )
        assert cancelled.json() == {"cancelled": False, "pending": True}
        assert response.status_code == 200
        assert response.json()["failure_reason"] == "cancelled"
        runner.assert_not_awaited()

    @pytest.mark.anyio
    async def test_concurrent_solve_returns_409(self, client):
        operation = solve_operations.claim(uuid4(), "native")
        try:
            response = await client.post(
                "/api/plate-solve/solve",
                json={"image_path": "/fake/image.fits", "operation_id": str(uuid4())},
            )
        finally:
            solve_operations.release(operation)
        assert response.status_code == 409

    @pytest.mark.anyio
    async def test_late_cancel_does_not_stop_next_operation(self, client):
        old_id = uuid4()
        old = solve_operations.claim(old_id, "native")
        solve_operations.release(old)
        current = solve_operations.claim(uuid4(), "native")
        try:
            response = await client.post(
                "/api/plate-solve/cancel", json={"operation_id": str(old_id)}
            )
            assert response.json() == {"cancelled": False, "pending": False}
            assert not current.stop.is_set()
        finally:
            solve_operations.release(current)
