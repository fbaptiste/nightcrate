"""API-level tests for the plate solve endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


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
    async def test_returns_422_when_not_configured(self, client, tmp_path):
        resp = await client.post(
            "/api/plate-solve/solve",
            json={"image_path": str(tmp_path / "test.fits")},
        )
        assert resp.status_code == 422
        assert "not configured" in resp.json()["detail"].lower()
