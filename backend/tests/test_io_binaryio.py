"""Tests for BinaryIO support in I/O services."""

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

from nightcrate.services import fits_io, standard_io, xisf_io


@pytest.fixture
def fits_bytes() -> bytes:
    data = np.zeros((20, 30), dtype=np.uint16)
    data[10, 15] = 10000
    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "TestStar"
    buf = BytesIO()
    hdu.writeto(buf)
    return buf.getvalue()


class TestFitsIOBinaryIO:
    def test_load_image_data(self, fits_bytes: bytes):
        buf = BytesIO(fits_bytes)
        data = fits_io.load_image_data(buf)
        assert data.shape == (20, 30)
        assert data.dtype == np.float64

    def test_read_header(self, fits_bytes: bytes):
        buf = BytesIO(fits_bytes)
        cards = fits_io.read_header(buf)
        keys = [c["key"] for c in cards]
        assert "OBJECT" in keys

    def test_list_extensions(self, fits_bytes: bytes):
        buf = BytesIO(fits_bytes)
        exts = fits_io.list_extensions(buf)
        assert len(exts) >= 1
        assert exts[0]["has_image"] is True


@pytest.fixture
def png_bytes() -> bytes:
    img = Image.new("RGB", (40, 30), color=(128, 64, 32))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestStandardIOBinaryIO:
    def test_load_image_as_array(self, png_bytes: bytes):
        buf = BytesIO(png_bytes)
        data = standard_io.load_image_as_array(buf)
        assert data.ndim >= 2
        assert data.dtype == np.float64

    def test_list_extensions(self, png_bytes: bytes):
        buf = BytesIO(png_bytes)
        exts = standard_io.list_extensions(buf)
        assert len(exts) == 1
        assert exts[0]["has_image"] is True

    def test_read_header(self, png_bytes: bytes):
        buf = BytesIO(png_bytes)
        cards = standard_io.read_header(buf)
        assert isinstance(cards, list)


@pytest.fixture
def xisf_bytes() -> bytes | None:
    xisf_path = Path(__file__).parent / "fixtures" / "test_mono_uncompressed.xisf"
    if not xisf_path.exists():
        return None
    return xisf_path.read_bytes()


class TestXisfIOBinaryIO:
    def test_load_image_data(self, xisf_bytes):
        if xisf_bytes is None:
            pytest.skip("XISF fixture not available")
        buf = BytesIO(xisf_bytes)
        data = xisf_io.load_image_data(buf)
        assert data.ndim >= 2
        assert data.dtype == np.float64

    def test_read_header(self, xisf_bytes):
        if xisf_bytes is None:
            pytest.skip("XISF fixture not available")
        buf = BytesIO(xisf_bytes)
        cards = xisf_io.read_header(buf)
        assert isinstance(cards, list)

    def test_list_extensions(self, xisf_bytes):
        if xisf_bytes is None:
            pytest.skip("XISF fixture not available")
        buf = BytesIO(xisf_bytes)
        exts = xisf_io.list_extensions(buf)
        assert len(exts) >= 1
