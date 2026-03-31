"""Tests for FastAPI endpoints."""

from pathlib import Path

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


class TestHealthEndpoint:
    async def test_health(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestFitsEndpoints:
    async def test_hdus(self, client: AsyncClient, tmp_fits_mono: Path):
        resp = await client.get("/api/fits/hdus", params={"path": str(tmp_fits_mono)})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["has_image"] is True

    async def test_header(self, client: AsyncClient, tmp_fits_mono: Path):
        resp = await client.get("/api/fits/header", params={"path": str(tmp_fits_mono), "hdu": 0})
        assert resp.status_code == 200
        cards = resp.json()
        keys = {c["key"] for c in cards}
        assert "OBJECT" in keys

    async def test_stats(self, client: AsyncClient, tmp_fits_mono: Path):
        resp = await client.get("/api/fits/stats", params={"path": str(tmp_fits_mono), "hdu": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["color"] is False
        assert len(data["channels"]) == 1
        assert "stf" in data["channels"][0]

    async def test_image_default(self, client: AsyncClient, tmp_fits_mono: Path):
        resp = await client.get("/api/fits/image", params={"path": str(tmp_fits_mono), "hdu": 0})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert len(resp.content) > 0

    async def test_image_with_stf_params(self, client: AsyncClient, tmp_fits_mono: Path):
        resp = await client.get(
            "/api/fits/image",
            params={
                "path": str(tmp_fits_mono),
                "hdu": 0,
                "stretch": "stf",
                "shadow": 0.01,
                "midtone": 0.05,
                "highlight": 1.0,
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    async def test_nonexistent_file(self, client: AsyncClient):
        resp = await client.get("/api/fits/hdus", params={"path": "/nonexistent/file.fits"})
        assert resp.status_code == 404

    async def test_relative_path_rejected(self, client: AsyncClient):
        resp = await client.get("/api/fits/hdus", params={"path": "relative/file.fits"})
        assert resp.status_code == 400

    async def test_non_fits_extension_rejected(self, client: AsyncClient, tmp_path: Path):
        txt = tmp_path / "file.txt"
        txt.write_text("not a fits file")
        resp = await client.get("/api/fits/hdus", params={"path": str(txt)})
        assert resp.status_code == 400


class TestFilesEndpoints:
    async def test_volumes(self, client: AsyncClient):
        resp = await client.get("/api/files/volumes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        # Home should always be first
        assert data[0]["name"].startswith("~")

    async def test_browse_home(self, client: AsyncClient):
        resp = await client.get("/api/files/browse", params={"path": "~"})
        assert resp.status_code == 200
        data = resp.json()
        assert "path" in data
        assert "dirs" in data
        assert "files" in data
        assert "parent" in data

    async def test_browse_lists_fits_only(self, client: AsyncClient, tmp_dir_with_fits: Path):
        resp = await client.get("/api/files/browse", params={"path": str(tmp_dir_with_fits)})
        assert resp.status_code == 200
        data = resp.json()
        file_names = {f["name"] for f in data["files"]}
        assert "image1.fits" in file_names
        assert "image2.fit" in file_names
        assert "readme.txt" not in file_names

    async def test_browse_excludes_hidden(self, client: AsyncClient, tmp_dir_with_fits: Path):
        resp = await client.get("/api/files/browse", params={"path": str(tmp_dir_with_fits)})
        data = resp.json()
        dir_names = {d["name"] for d in data["dirs"]}
        file_names = {f["name"] for f in data["files"]}
        assert ".hidden" not in dir_names
        assert ".secret.fits" not in file_names

    async def test_browse_not_a_directory(self, client: AsyncClient, tmp_fits_mono: Path):
        resp = await client.get("/api/files/browse", params={"path": str(tmp_fits_mono)})
        assert resp.status_code == 400

    async def test_browse_has_parent(self, client: AsyncClient, tmp_dir_with_fits: Path):
        resp = await client.get("/api/files/browse", params={"path": str(tmp_dir_with_fits)})
        data = resp.json()
        assert data["parent"] is not None
