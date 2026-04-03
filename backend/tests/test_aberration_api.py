"""Tests for aberration inspector API endpoints."""

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def tmp_fits_with_stars(tmp_path: Path) -> Path:
    """Create a FITS file with simulated star-like sources for detection tests."""
    rng = np.random.default_rng(1234)
    data = rng.integers(1000, 1200, size=(200, 200), dtype=np.uint16)

    for cx, cy in [(40, 40), (100, 60), (60, 140), (160, 100), (150, 150)]:
        for dy in range(-8, 9):
            for dx in range(-8, 9):
                r2 = dx**2 + dy**2
                val = int(50000 * np.exp(-r2 / 8.0))
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < 200 and 0 <= nx < 200:
                    data[ny, nx] = min(65535, data[ny, nx] + val)

    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "StarTest"
    path = tmp_path / "stars.fits"
    hdu.writeto(path, overwrite=True)
    return path


class TestAnalyzeEndpoint:
    async def test_analyze_basic(self, client: AsyncClient, tmp_fits_with_stars: Path):
        resp = await client.post(
            "/api/aberration/analyze",
            params={"path": str(tmp_fits_with_stars), "hdu": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "stars" in data
        assert "star_count" in data
        assert data["image_width"] == 200
        assert data["image_height"] == 200
        assert data["star_count"] == len(data["stars"])

    async def test_analyze_nonexistent_file(self, client: AsyncClient):
        resp = await client.post(
            "/api/aberration/analyze",
            params={"path": "/nonexistent/file.fits", "hdu": 0},
        )
        assert resp.status_code == 404

    async def test_analyze_relative_path_rejected(self, client: AsyncClient):
        resp = await client.post(
            "/api/aberration/analyze",
            params={"path": "relative/path/file.fits", "hdu": 0},
        )
        assert resp.status_code == 422

    async def test_analyze_caching(self, client: AsyncClient, tmp_fits_with_stars: Path):
        params = {"path": str(tmp_fits_with_stars), "hdu": 0}
        resp1 = await client.post("/api/aberration/analyze", params=params)
        resp2 = await client.post("/api/aberration/analyze", params=params)
        assert resp1.json()["star_count"] == resp2.json()["star_count"]


class TestSamplesEndpoint:
    async def test_samples_basic(self, client: AsyncClient, tmp_fits_with_stars: Path):
        resp = await client.post(
            "/api/aberration/samples",
            params={"path": str(tmp_fits_with_stars), "hdu": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "squares" in data
        assert data["samples_across"] == 5
        assert data["cols"] == 5
        assert data["rows"] >= 2
        assert len(data["squares"]) == data["rows"] * data["cols"]

    async def test_samples_custom_count(self, client: AsyncClient, tmp_fits_with_stars: Path):
        resp = await client.post(
            "/api/aberration/samples",
            params={"path": str(tmp_fits_with_stars), "hdu": 0, "samples_across": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["cols"] == 3

    async def test_samples_square_structure(self, client: AsyncClient, tmp_fits_with_stars: Path):
        resp = await client.post(
            "/api/aberration/samples",
            params={"path": str(tmp_fits_with_stars), "hdu": 0},
        )
        for sq in resp.json()["squares"]:
            assert "row" in sq
            assert "col" in sq
            assert "x0" in sq
            assert "y0" in sq
            assert "x1" in sq
            assert "y1" in sq
            assert "star_count" in sq
            assert "star_indices" in sq

    async def test_samples_nonexistent_file(self, client: AsyncClient):
        resp = await client.post(
            "/api/aberration/samples",
            params={"path": "/nonexistent/file.fits", "hdu": 0},
        )
        assert resp.status_code == 404


class TestCropEndpoint:
    async def test_crop_region(self, client: AsyncClient, tmp_fits_with_stars: Path):
        params = {
            "path": str(tmp_fits_with_stars),
            "hdu": 0,
            "x0": 20,
            "y0": 20,
            "x1": 80,
            "y1": 80,
        }
        resp = await client.get(
            "/api/aberration/crop",
            params=params,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert len(resp.content) > 0

    async def test_crop_edge_clamp(self, client: AsyncClient, tmp_fits_with_stars: Path):
        params = {
            "path": str(tmp_fits_with_stars),
            "hdu": 0,
            "x0": 0,
            "y0": 0,
            "x1": 64,
            "y1": 64,
        }
        resp = await client.get(
            "/api/aberration/crop",
            params=params,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    async def test_crop_nonexistent_file(self, client: AsyncClient):
        params = {
            "path": "/nonexistent/file.fits",
            "hdu": 0,
            "x0": 0,
            "y0": 0,
            "x1": 64,
            "y1": 64,
        }
        resp = await client.get(
            "/api/aberration/crop",
            params=params,
        )
        assert resp.status_code == 404


class TestCacheSizeEndpoint:
    async def test_cache_size_empty(self, client: AsyncClient):
        resp = await client.get("/api/aberration/cache/size")
        assert resp.status_code == 200
        data = resp.json()
        assert "bytes" in data
        assert data["bytes"] >= 0

    async def test_cache_size_after_analysis(self, client: AsyncClient, tmp_fits_with_stars: Path):
        params = {"path": str(tmp_fits_with_stars), "hdu": 0}
        await client.post("/api/aberration/analyze", params=params)
        resp = await client.get("/api/aberration/cache/size")
        assert resp.json()["bytes"] >= 0


class TestClearCacheEndpoint:
    async def test_clear_cache_empty(self, client: AsyncClient):
        resp = await client.delete("/api/aberration/cache")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    async def test_clear_cache_after_analysis(self, client: AsyncClient, tmp_fits_with_stars: Path):
        params = {"path": str(tmp_fits_with_stars), "hdu": 0}
        await client.post("/api/aberration/analyze", params=params)
        resp = await client.delete("/api/aberration/cache")
        assert resp.json()["deleted_analyses"] >= 1

    async def test_cache_repopulates_after_clear(
        self, client: AsyncClient, tmp_fits_with_stars: Path
    ):
        params = {"path": str(tmp_fits_with_stars), "hdu": 0}
        resp1 = await client.post("/api/aberration/analyze", params=params)
        await client.delete("/api/aberration/cache")
        resp2 = await client.post("/api/aberration/analyze", params=params)
        assert resp2.json()["star_count"] == resp1.json()["star_count"]
