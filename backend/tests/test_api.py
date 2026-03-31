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


class TestImageEndpoints:
    async def test_extensions(self, client: AsyncClient, tmp_fits_mono: Path):
        resp = await client.get("/api/images/extensions", params={"path": str(tmp_fits_mono)})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["has_image"] is True

    async def test_header(self, client: AsyncClient, tmp_fits_mono: Path):
        resp = await client.get("/api/images/header", params={"path": str(tmp_fits_mono), "hdu": 0})
        assert resp.status_code == 200
        cards = resp.json()
        keys = {c["key"] for c in cards}
        assert "OBJECT" in keys

    async def test_stats_fits(self, client: AsyncClient, tmp_fits_mono: Path):
        resp = await client.get("/api/images/stats", params={"path": str(tmp_fits_mono), "hdu": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["color"] is False
        assert len(data["channels"]) == 1
        assert "stf" in data["channels"][0]

    async def test_image_default(self, client: AsyncClient, tmp_fits_mono: Path):
        resp = await client.get("/api/images/image", params={"path": str(tmp_fits_mono), "hdu": 0})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert len(resp.content) > 0

    async def test_image_with_stf_params(self, client: AsyncClient, tmp_fits_mono: Path):
        resp = await client.get(
            "/api/images/image",
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
        resp = await client.get("/api/images/extensions", params={"path": "/nonexistent/file.fits"})
        assert resp.status_code == 404

    async def test_relative_path_rejected(self, client: AsyncClient):
        resp = await client.get("/api/images/extensions", params={"path": "relative/file.fits"})
        assert resp.status_code == 400

    async def test_non_image_extension_rejected(self, client: AsyncClient, tmp_path: Path):
        txt = tmp_path / "file.txt"
        txt.write_text("not an image")
        resp = await client.get("/api/images/extensions", params={"path": str(txt)})
        assert resp.status_code == 400

    async def test_standard_image(self, client: AsyncClient, tmp_path: Path):
        """PNG files should be served without stretch."""
        from PIL import Image

        img = Image.new("RGB", (10, 10), color="red")
        png_path = tmp_path / "test.png"
        img.save(png_path)

        resp = await client.get("/api/images/image", params={"path": str(png_path), "hdu": 0})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    async def test_standard_image_stats_not_available(self, client: AsyncClient, tmp_path: Path):
        from PIL import Image

        img = Image.new("RGB", (10, 10), color="blue")
        png_path = tmp_path / "test.png"
        img.save(png_path)

        resp = await client.get("/api/images/stats", params={"path": str(png_path), "hdu": 0})
        assert resp.status_code == 404


class TestRecentFiles:
    async def test_record_and_fetch(self, client: AsyncClient, tmp_fits_mono: Path):
        # Record a file
        resp = await client.post("/api/images/recent", params={"path": str(tmp_fits_mono)})
        assert resp.status_code == 200

        # Fetch recent
        resp = await client.get("/api/images/recent")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["path"] == str(tmp_fits_mono)
        assert data[0]["name"] == tmp_fits_mono.name

    async def test_stale_entries_pruned(self, client: AsyncClient):
        # Record a file that doesn't exist
        resp = await client.post("/api/images/recent", params={"path": "/nonexistent/ghost.fits"})
        assert resp.status_code == 200

        # Fetch — should not include the non-existent file
        resp = await client.get("/api/images/recent")
        paths = [r["path"] for r in resp.json()]
        assert "/nonexistent/ghost.fits" not in paths


class TestFilesEndpoints:
    async def test_volumes(self, client: AsyncClient):
        resp = await client.get("/api/files/volumes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["name"].startswith("~")

    async def test_browse_home(self, client: AsyncClient):
        resp = await client.get("/api/files/browse", params={"path": "~"})
        assert resp.status_code == 200
        data = resp.json()
        assert "path" in data
        assert "dirs" in data
        assert "files" in data
        assert "parent" in data

    async def test_browse_lists_image_files(self, client: AsyncClient, tmp_dir_with_fits: Path):
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
