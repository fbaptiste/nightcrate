"""API-level tests for the image annotation endpoints."""

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
def fits_with_wcs(tmp_path: Path) -> Path:
    data = np.zeros((1000, 1200), dtype=np.uint16)
    hdu = fits.PrimaryHDU(data)
    hdu.header["CTYPE1"] = "RA---TAN"
    hdu.header["CTYPE2"] = "DEC--TAN"
    hdu.header["CRVAL1"] = 83.633
    hdu.header["CRVAL2"] = -5.375
    hdu.header["CRPIX1"] = 600.0
    hdu.header["CRPIX2"] = 500.0
    hdu.header["CD1_1"] = -0.000278
    hdu.header["CD1_2"] = 0.0
    hdu.header["CD2_1"] = 0.0
    hdu.header["CD2_2"] = 0.000278
    path = tmp_path / "wcs_test.fits"
    hdu.writeto(path, overwrite=True)
    return path


@pytest.fixture
def fits_no_wcs(tmp_path: Path) -> Path:
    data = np.zeros((1000, 1200), dtype=np.uint16)
    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "M42"
    path = tmp_path / "no_wcs.fits"
    hdu.writeto(path, overwrite=True)
    return path


class TestDetectWcs:
    @pytest.mark.anyio
    async def test_with_wcs_headers(self, client, fits_with_wcs):
        resp = await client.get(
            "/api/plate-solve/detect-wcs",
            params={"path": str(fits_with_wcs)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data is not None
        assert data["crval1"] == pytest.approx(83.633)
        assert data["naxis1"] == 1200

    @pytest.mark.anyio
    async def test_without_wcs_headers(self, client, fits_no_wcs):
        resp = await client.get(
            "/api/plate-solve/detect-wcs",
            params={"path": str(fits_no_wcs)},
        )
        assert resp.status_code == 200
        assert resp.json() is None


class TestAnnotate:
    @pytest.mark.anyio
    async def test_with_wcs_in_headers(self, client, fits_with_wcs):
        resp = await client.get(
            "/api/plate-solve/annotate",
            params={"path": str(fits_with_wcs)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "wcs" in data
        assert "dsos" in data
        assert data["center_ra_deg"] == pytest.approx(83.633, abs=0.01)

    @pytest.mark.anyio
    async def test_no_wcs_returns_422(self, client, fits_no_wcs):
        resp = await client.get(
            "/api/plate-solve/annotate",
            params={"path": str(fits_no_wcs)},
        )
        assert resp.status_code == 422
        assert "No WCS" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_with_wcs_override(self, client, fits_no_wcs):
        resp = await client.get(
            "/api/plate-solve/annotate",
            params={
                "path": str(fits_no_wcs),
                "crval1": 83.633,
                "crval2": -5.375,
                "cd1_1": -0.000278,
                "cd1_2": 0.0,
                "cd2_1": 0.0,
                "cd2_2": 0.000278,
                "crpix1": 600.0,
                "crpix2": 500.0,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["wcs"]["crval1"] == pytest.approx(83.633)

    @pytest.mark.anyio
    async def test_partial_wcs_override_returns_422(self, client, fits_no_wcs):
        resp = await client.get(
            "/api/plate-solve/annotate",
            params={
                "path": str(fits_no_wcs),
                "crval1": 83.633,
            },
        )
        assert resp.status_code == 422
        assert "Partial WCS" in resp.json()["detail"]
