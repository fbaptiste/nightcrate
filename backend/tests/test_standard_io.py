"""Tests for standard image I/O — PNG, JPEG, TIFF (including float32 TIFFs)."""

import io
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import Image

from nightcrate.services.standard_io import (
    is_float_tiff,
    list_extensions,
    load_image_bytes,
    load_image_data,
    read_header,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_float_tiff_mono(tmp_path: Path) -> Path:
    """Create a float32 grayscale TIFF."""
    arr = np.random.default_rng(42).uniform(0.01, 0.9, size=(60, 80)).astype(np.float32)
    path = tmp_path / "float_mono.tif"
    tifffile.imwrite(str(path), arr)
    return path


@pytest.fixture
def tmp_float_tiff_rgb(tmp_path: Path) -> Path:
    """Create a float32 RGB TIFF (H, W, 3)."""
    arr = np.random.default_rng(99).uniform(0.01, 0.9, size=(40, 60, 3)).astype(np.float32)
    path = tmp_path / "float_rgb.tif"
    tifffile.imwrite(str(path), arr, photometric="rgb")
    return path


@pytest.fixture
def tmp_uint8_tiff(tmp_path: Path) -> Path:
    """Create a standard 8-bit TIFF."""
    arr = np.random.default_rng(7).integers(0, 255, size=(30, 40), dtype=np.uint8)
    path = tmp_path / "uint8.tiff"
    tifffile.imwrite(str(path), arr)
    return path


@pytest.fixture
def tmp_png(tmp_path: Path) -> Path:
    """Create a standard PNG."""
    img = Image.fromarray(np.zeros((20, 30, 3), dtype=np.uint8), "RGB")
    path = tmp_path / "test.png"
    img.save(path)
    return path


# ── is_float_tiff ────────────────────────────────────────────────────────────


class TestIsFloatTiff:
    def test_float32_tiff(self, tmp_float_tiff_mono):
        assert is_float_tiff(tmp_float_tiff_mono) is True

    def test_uint8_tiff(self, tmp_uint8_tiff):
        assert is_float_tiff(tmp_uint8_tiff) is False

    def test_png_returns_false(self, tmp_png):
        assert is_float_tiff(tmp_png) is False

    def test_nonexistent_returns_false(self, tmp_path):
        assert is_float_tiff(tmp_path / "nope.tif") is False


# ── load_image_data (float TIFF) ────────────────────────────────────────────


class TestLoadImageData:
    def test_mono_float_tiff(self, tmp_float_tiff_mono):
        data = load_image_data(tmp_float_tiff_mono)
        assert data.shape == (60, 80)
        assert data.dtype == np.float64
        assert 0.0 <= data.min()
        assert data.max() <= 1.0

    def test_rgb_float_tiff(self, tmp_float_tiff_rgb):
        data = load_image_data(tmp_float_tiff_rgb)
        assert data.shape == (3, 40, 60)
        assert data.dtype == np.float64

    def test_unsupported_shape(self, tmp_path):
        """4D arrays should raise."""
        import warnings

        arr = np.zeros((2, 3, 4, 5), dtype=np.float32)
        path = tmp_path / "4d.tif"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            tifffile.imwrite(str(path), arr)
        with pytest.raises(ValueError, match="Unsupported TIFF array shape"):
            load_image_data(path)


# ── load_image_bytes ─────────────────────────────────────────────────────────


class TestLoadImageBytes:
    def test_png_passthrough(self, tmp_png):
        png_bytes = load_image_bytes(tmp_png)
        img = Image.open(io.BytesIO(png_bytes))
        assert img.format == "PNG"

    def test_uint8_tiff(self, tmp_uint8_tiff):
        png_bytes = load_image_bytes(tmp_uint8_tiff)
        img = Image.open(io.BytesIO(png_bytes))
        assert img.format == "PNG"

    def test_float_tiff_fallback(self, tmp_float_tiff_mono):
        """Float TIFFs that Pillow can't open should fall back to tifffile."""
        png_bytes = load_image_bytes(tmp_float_tiff_mono)
        img = Image.open(io.BytesIO(png_bytes))
        assert img.format == "PNG"


# ── read_header ──────────────────────────────────────────────────────────────


class TestReadHeader:
    def test_png_header(self, tmp_png):
        cards = read_header(tmp_png)
        keys = {c["key"] for c in cards}
        assert "Format" in keys
        assert "Width" in keys
        assert "Height" in keys

    def test_float_tiff_header(self, tmp_float_tiff_mono):
        cards = read_header(tmp_float_tiff_mono)
        keys = {c["key"] for c in cards}
        assert "Format" in keys
        assert "Width" in keys
        assert "Height" in keys


# ── list_extensions ──────────────────────────────────────────────────────────


class TestListExtensions:
    def test_png(self, tmp_png):
        exts = list_extensions(tmp_png)
        assert len(exts) == 1
        assert exts[0]["has_image"] is True

    def test_float_tiff(self, tmp_float_tiff_mono):
        exts = list_extensions(tmp_float_tiff_mono)
        assert len(exts) == 1
        assert exts[0]["has_image"] is True
