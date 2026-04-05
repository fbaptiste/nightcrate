"""Tests for FITS header editing — PATCH /api/images/header."""

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
def editable_fits(tmp_path: Path) -> Path:
    """Create a FITS file with known headers for editing tests."""
    rng = np.random.default_rng(42)
    data = rng.integers(1400, 1600, size=(50, 60), dtype=np.uint16)
    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = ("M42", "Target name")
    hdu.header["FILTER"] = ("Ha", "Filter used")
    hdu.header["EXPTIME"] = 300.0
    hdu.header["OBSERVER"] = "Fred"
    path = tmp_path / "editable.fits"
    hdu.writeto(path, overwrite=True)
    return path


class TestUpdateOperation:
    async def test_update_value(self, client: AsyncClient, editable_fits: Path):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [{"op": "update", "key": "OBJECT", "value": "NGC 1234"}],
            },
        )
        assert resp.status_code == 200
        cards = resp.json()
        obj = next(c for c in cards if c["key"] == "OBJECT")
        assert obj["value"] == "NGC 1234"

    async def test_update_value_and_comment(self, client: AsyncClient, editable_fits: Path):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [
                    {
                        "op": "update",
                        "key": "OBJECT",
                        "value": "IC 1396",
                        "comment": "Elephant Trunk",
                    }
                ],
            },
        )
        assert resp.status_code == 200
        cards = resp.json()
        obj = next(c for c in cards if c["key"] == "OBJECT")
        assert obj["value"] == "IC 1396"
        assert obj["comment"] == "Elephant Trunk"

    async def test_update_preserves_comment_when_omitted(
        self, client: AsyncClient, editable_fits: Path
    ):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [{"op": "update", "key": "OBJECT", "value": "NGC 7000"}],
            },
        )
        assert resp.status_code == 200
        cards = resp.json()
        obj = next(c for c in cards if c["key"] == "OBJECT")
        assert obj["comment"] == "Target name"

    async def test_update_nonexistent_key_400(self, client: AsyncClient, editable_fits: Path):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [{"op": "update", "key": "NOSUCHKEY", "value": "x"}],
            },
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()


class TestAddOperation:
    async def test_add_keyword(self, client: AsyncClient, editable_fits: Path):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [
                    {"op": "add", "key": "TELESCOP", "value": "C11", "comment": "Telescope"}
                ],
            },
        )
        assert resp.status_code == 200
        cards = resp.json()
        tel = next(c for c in cards if c["key"] == "TELESCOP")
        assert tel["value"] == "C11"
        assert tel["comment"] == "Telescope"

    async def test_add_duplicate_key_400(self, client: AsyncClient, editable_fits: Path):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [{"op": "add", "key": "OBJECT", "value": "duplicate"}],
            },
        )
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()


class TestDeleteOperation:
    async def test_delete_keyword(self, client: AsyncClient, editable_fits: Path):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [{"op": "delete", "key": "OBSERVER"}],
            },
        )
        assert resp.status_code == 200
        cards = resp.json()
        keys = {c["key"] for c in cards}
        assert "OBSERVER" not in keys

    async def test_delete_nonexistent_key_400(self, client: AsyncClient, editable_fits: Path):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [{"op": "delete", "key": "NOSUCHKEY"}],
            },
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()


class TestStructuralKeywordProtection:
    @pytest.mark.parametrize("key", ["SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2"])
    async def test_cannot_update_structural(self, client: AsyncClient, editable_fits: Path, key):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [{"op": "update", "key": key, "value": "bad"}],
            },
        )
        assert resp.status_code == 400
        assert "structural" in resp.json()["detail"].lower()

    async def test_cannot_delete_structural(self, client: AsyncClient, editable_fits: Path):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [{"op": "delete", "key": "BITPIX"}],
            },
        )
        assert resp.status_code == 400

    async def test_cannot_add_structural(self, client: AsyncClient, editable_fits: Path):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [{"op": "add", "key": "NAXIS3", "value": "1"}],
            },
        )
        assert resp.status_code == 400


class TestPathValidation:
    async def test_archive_path_rejected(self, client: AsyncClient, tmp_path: Path):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": f"{tmp_path}/archive.zip::entry.fits",
                "hdu": 0,
                "operations": [{"op": "update", "key": "OBJECT", "value": "x"}],
            },
        )
        assert resp.status_code == 400
        assert "virtual path" in resp.json()["detail"].lower()

    async def test_file_not_found_404(self, client: AsyncClient, tmp_path: Path):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(tmp_path / "nonexistent.fits"),
                "hdu": 0,
                "operations": [{"op": "update", "key": "OBJECT", "value": "x"}],
            },
        )
        assert resp.status_code == 404

    async def test_non_fits_rejected(self, client: AsyncClient, tmp_path: Path):
        png = tmp_path / "image.png"
        png.write_bytes(b"\x89PNG\r\n")
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(png),
                "hdu": 0,
                "operations": [{"op": "update", "key": "OBJECT", "value": "x"}],
            },
        )
        assert resp.status_code == 422


class TestBatchOperations:
    async def test_multiple_operations(self, client: AsyncClient, editable_fits: Path):
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [
                    {"op": "update", "key": "OBJECT", "value": "NGC 2024"},
                    {"op": "add", "key": "TELESCOP", "value": "C11"},
                    {"op": "delete", "key": "OBSERVER"},
                ],
            },
        )
        assert resp.status_code == 200
        cards = resp.json()
        keys = {c["key"] for c in cards}
        obj = next(c for c in cards if c["key"] == "OBJECT")
        assert obj["value"] == "NGC 2024"
        assert "TELESCOP" in keys
        assert "OBSERVER" not in keys

    async def test_file_actually_modified_on_disk(self, client: AsyncClient, editable_fits: Path):
        """Verify the FITS file on disk is actually modified after editing."""
        await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [{"op": "update", "key": "OBJECT", "value": "DiskCheck"}],
            },
        )
        # Re-read directly from disk
        with fits.open(editable_fits) as hdul:
            assert hdul[0].header["OBJECT"] == "DiskCheck"

    async def test_numeric_type_preserved_on_update(self, client: AsyncClient, editable_fits: Path):
        """Updating a numeric keyword preserves its FITS type (not converted to string)."""
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [{"op": "update", "key": "EXPTIME", "value": "600.0"}],
            },
        )
        assert resp.status_code == 200
        with fits.open(editable_fits) as hdul:
            val = hdul[0].header["EXPTIME"]
            assert isinstance(val, float)
            assert val == 600.0

    async def test_added_numeric_value_stored_as_number(
        self, client: AsyncClient, editable_fits: Path
    ):
        """Adding a keyword with a numeric string stores it as a number in FITS."""
        resp = await client.patch(
            "/api/images/header",
            json={
                "path": str(editable_fits),
                "hdu": 0,
                "operations": [{"op": "add", "key": "AIRMASS", "value": "1.23"}],
            },
        )
        assert resp.status_code == 200
        with fits.open(editable_fits) as hdul:
            val = hdul[0].header["AIRMASS"]
            assert isinstance(val, float)
            assert val == 1.23
