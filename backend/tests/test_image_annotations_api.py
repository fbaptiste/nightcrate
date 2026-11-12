"""API-level tests for the image annotation endpoints."""

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app
from nightcrate.services.image_annotation_models import FileSolution, WcsParams


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


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["detect-wcs", "annotate"])
async def test_truncated_xisf_reader_error_returns_plain_422(client, tmp_path, endpoint):
    path = tmp_path / "truncated.xisf"
    path.write_bytes(b"XISF0100")

    response = await client.get(f"/api/plate-solve/{endpoint}", params={"path": str(path)})

    assert response.status_code == 422
    assert response.json() == {"detail": "This XISF file has an invalid header."}


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["detect-wcs", "annotate"])
async def test_unexpected_reader_failure_is_logged_500(
    client, fits_no_wcs, endpoint, monkeypatch, caplog
):
    """A failure that isn't a reader error stays a logged, generic 500."""
    from nightcrate.api import plate_solve as plate_solve_api

    def boom(*_args):
        raise RuntimeError("disk vanished")

    monkeypatch.setattr(plate_solve_api, "read_file_solution", boom)
    with caplog.at_level("ERROR"):
        response = await client.get(
            f"/api/plate-solve/{endpoint}", params={"path": str(fits_no_wcs)}
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal processing error"}
    assert "image read failed" in caplog.text


class TestDetectWcs:
    @pytest.mark.anyio
    async def test_xisf_solution_keeps_reason_and_half_pixel_conversion(self, client, tmp_path):
        from tests.test_xisf_io import TestAstrometricWcs, _make_xisf

        pixels = np.zeros((8, 10), dtype=np.uint16)
        xml = TestAstrometricWcs._astro_xml(
            [300.0, 35.0],
            [4.0, 3.0],
            [1e-5, -3e-4, 3e-4, 1e-5],
            prefix="AstrometricSolution:",
            version="1.0",
        )
        path = tmp_path / "solution.xisf"
        path.write_bytes(_make_xisf(10, 8, 1, "UInt16", pixels.tobytes(), extra_xml=xml))

        response = await client.get("/api/plate-solve/detect-wcs", params={"path": str(path)})

        assert response.status_code == 200
        assert response.json()["wcs"]["crpix1"] == 4.5
        assert response.json()["unavailable_reason"] is None

    @pytest.mark.anyio
    async def test_xisf_unsupported_projection_flows_to_annotate(self, client, tmp_path):
        from tests.test_xisf_io import TestAstrometricWcs, _make_xisf

        pixels = np.zeros((8, 10), dtype=np.uint16)
        xml = TestAstrometricWcs._astro_xml(
            [300.0, 35.0],
            [4.0, 3.0],
            [1e-5, -3e-4, 3e-4, 1e-5],
            "Stereographic",
            prefix="AstrometricSolution:",
            version="1.0",
        )
        path = tmp_path / "stereographic.xisf"
        path.write_bytes(_make_xisf(10, 8, 1, "UInt16", pixels.tobytes(), extra_xml=xml))

        detected = await client.get("/api/plate-solve/detect-wcs", params={"path": str(path)})
        annotated = await client.get("/api/plate-solve/annotate", params={"path": str(path)})

        reason = detected.json()["unavailable_reason"]
        assert detected.json()["wcs"] is None
        assert "Stereographic" in reason
        assert annotated.status_code == 422
        assert annotated.json()["detail"] == reason

    @pytest.mark.anyio
    async def test_with_wcs_headers(self, client, fits_with_wcs):
        resp = await client.get(
            "/api/plate-solve/detect-wcs",
            params={"path": str(fits_with_wcs)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["wcs"]["crval1"] == pytest.approx(83.633)
        assert data["wcs"]["naxis1"] == 1200
        assert data["unavailable_reason"] is None

    @pytest.mark.anyio
    async def test_without_wcs_headers(self, client, fits_no_wcs):
        resp = await client.get(
            "/api/plate-solve/detect-wcs",
            params={"path": str(fits_no_wcs)},
        )
        assert resp.status_code == 200
        assert resp.json() == {"wcs": None, "unavailable_reason": None}

    @pytest.mark.anyio
    async def test_uses_format_specific_wcs_reader(self, client, monkeypatch):
        expected = WcsParams(
            crval1=300.0,
            crval2=35.0,
            cd1_1=1e-5,
            cd1_2=-3e-4,
            cd2_1=3e-4,
            cd2_2=1e-5,
            crpix1=500.0,
            crpix2=400.0,
            naxis1=1000,
            naxis2=800,
        )
        monkeypatch.setattr(
            "nightcrate.api.plate_solve.resolve_path",
            lambda _path: (Path("test.xisf"), "xisf", 0, None),
        )
        monkeypatch.setattr(
            "nightcrate.api.plate_solve.read_file_solution",
            lambda *_args: FileSolution(wcs=expected),
        )

        resp = await client.get(
            "/api/plate-solve/detect-wcs",
            params={"path": "test.xisf"},
        )

        assert resp.status_code == 200
        assert resp.json() == {"wcs": expected.model_dump(), "unavailable_reason": None}


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
