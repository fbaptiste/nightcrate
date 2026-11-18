"""Tests for aberration inspector API endpoints."""

import json
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.api import aberration as aberration_api
from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services.aberration import AnalysisResult, DetectionSettings


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


async def _seed_legacy_analysis(file_path: Path) -> str:
    settings_json = json.dumps(DetectionSettings().model_dump(), sort_keys=True)
    async with get_db() as conn:
        cursor = await conn.execute(
            """INSERT INTO aberration_analysis
               (file_path, hdu, settings_json, image_width, image_height,
                star_count, median_fwhm, median_hfr, median_eccentricity)
               VALUES (?, 0, ?, 300, 200, 23, 6.75, 3.25, 0.2)""",
            (str(file_path), settings_json),
        )
        await conn.execute(
            """INSERT INTO aberration_stars
               (analysis_id, x, y, fwhm, hfr, eccentricity, elongation_angle_deg,
                peak_adu, flux, snr, semi_major, semi_minor)
               VALUES (?, 0, 0, 6.75, 3.25, 0.2, 12, 0.8, 100, 20, 3, 2)""",
            (cursor.lastrowid,),
        )
        await conn.commit()
    return settings_json


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

    async def test_analyze_nonexistent_file(self, client: AsyncClient, tmp_path: Path):
        missing = tmp_path / "nonexistent.fits"
        resp = await client.post(
            "/api/aberration/analyze",
            params={"path": str(missing), "hdu": 0},
        )
        assert resp.status_code == 404
        assert resp.json() == {"detail": f"File not found: {missing}"}

    async def test_missing_file_uses_legacy_cached_analysis(
        self, client: AsyncClient, tmp_path: Path
    ):
        missing = tmp_path / "offline.fits"
        await _seed_legacy_analysis(missing)

        resp = await client.post(
            "/api/aberration/analyze",
            params={"path": str(missing), "hdu": 0},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["star_count"] == 23
        assert body["stars"][0]["fwhm"] == 6.75
        assert body["stars"][0]["flag"] == 0
        assert body["median_snr"] is None
        assert body["background_level"] is None

    async def test_readable_file_is_reanalysed_and_keeps_legacy_row(
        self,
        client: AsyncClient,
        tmp_fits_with_stars: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        legacy_key = await _seed_legacy_analysis(tmp_fits_with_stars)
        fresh = AnalysisResult(
            stars=[],
            star_count=0,
            image_width=200,
            image_height=200,
            median_fwhm=None,
            median_hfr=None,
            median_eccentricity=None,
            settings=DetectionSettings(),
        )
        monkeypatch.setattr(aberration_api, "detect_stars", lambda *_args, **_kwargs: fresh)

        resp = await client.post(
            "/api/aberration/analyze",
            params={"path": str(tmp_fits_with_stars), "hdu": 0},
        )

        assert resp.status_code == 200
        assert resp.json()["star_count"] == 0
        current_key = aberration_api._settings_key(DetectionSettings())
        async with get_db() as conn:
            rows = await (
                await conn.execute(
                    "SELECT settings_json, star_count FROM aberration_analysis "
                    "WHERE file_path = ? ORDER BY settings_json",
                    (str(tmp_fits_with_stars),),
                )
            ).fetchall()
        assert {(row["settings_json"], row["star_count"]) for row in rows} == {
            (legacy_key, 23),
            (current_key, 0),
        }

    async def test_analyze_relative_path_rejected(self, client: AsyncClient):
        resp = await client.post(
            "/api/aberration/analyze",
            params={"path": "relative/path/file.fits", "hdu": 0},
        )
        assert resp.status_code in (400, 422)

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

    async def test_samples_nonexistent_file(self, client: AsyncClient, tmp_path: Path):
        resp = await client.post(
            "/api/aberration/samples",
            params={"path": str(tmp_path / "nonexistent.fits"), "hdu": 0},
        )
        assert resp.status_code == 404

    async def test_samples_use_legacy_cache_when_file_is_missing(
        self, client: AsyncClient, tmp_path: Path
    ):
        missing = tmp_path / "offline-samples.fits"
        await _seed_legacy_analysis(missing)

        resp = await client.post(
            "/api/aberration/samples",
            params={"path": str(missing), "hdu": 0, "samples_across": 5},
        )

        assert resp.status_code == 200
        squares = resp.json()["squares"]
        assert sum(square["star_count"] for square in squares) == 1
        assert (
            next(square["median_fwhm"] for square in squares if square["star_count"] == 1) == 6.75
        )


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

    async def test_crop_nonexistent_file(self, client: AsyncClient, tmp_path: Path):
        params = {
            "path": str(tmp_path / "nonexistent.fits"),
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
