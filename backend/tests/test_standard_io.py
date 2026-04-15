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
    load_image_as_array,
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
def tmp_uint16_tiff(tmp_path: Path) -> Path:
    """Create a 16-bit grayscale TIFF."""
    arr = np.random.default_rng(11).integers(0, 65535, size=(30, 40), dtype=np.uint16)
    path = tmp_path / "uint16.tiff"
    tifffile.imwrite(str(path), arr)
    return path


@pytest.fixture
def tmp_png(tmp_path: Path) -> Path:
    """Create a standard PNG."""
    img = Image.fromarray(np.zeros((20, 30, 3), dtype=np.uint8), "RGB")
    path = tmp_path / "test.png"
    img.save(path)
    return path


@pytest.fixture
def tmp_gray_png(tmp_path: Path) -> Path:
    """Create a grayscale PNG."""
    arr = np.random.default_rng(3).integers(0, 255, size=(20, 30), dtype=np.uint8)
    img = Image.fromarray(arr, "L")
    path = tmp_path / "gray.png"
    img.save(path)
    return path


@pytest.fixture
def tmp_rgba_png(tmp_path: Path) -> Path:
    """Create an RGBA PNG."""
    arr = np.random.default_rng(5).integers(0, 255, size=(20, 30, 4), dtype=np.uint8)
    img = Image.fromarray(arr, "RGBA")
    path = tmp_path / "rgba.png"
    img.save(path)
    return path


@pytest.fixture
def tmp_jpeg(tmp_path: Path) -> Path:
    """Create a standard JPEG."""
    arr = np.random.default_rng(8).integers(0, 255, size=(20, 30, 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")
    path = tmp_path / "test.jpg"
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

    def test_binaryio_float_tiff(self, tmp_float_tiff_mono):
        """BinaryIO wrapping a float TIFF should return True."""
        with open(tmp_float_tiff_mono, "rb") as f:
            buf = io.BytesIO(f.read())
        assert is_float_tiff(buf) is True
        # Should also reset seek position
        assert buf.tell() == 0

    def test_binaryio_non_tiff_data(self):
        """BinaryIO with non-TIFF data should return False."""
        img = Image.new("RGB", (10, 10), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        assert is_float_tiff(buf) is False

    def test_binaryio_uint8_tiff(self, tmp_uint8_tiff):
        """BinaryIO wrapping a uint8 TIFF should return False."""
        with open(tmp_uint8_tiff, "rb") as f:
            buf = io.BytesIO(f.read())
        assert is_float_tiff(buf) is False


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


# ── load_image_as_array ────────────────────────────────────────────────────


class TestLoadImageAsArray:
    def test_rgb_png(self, tmp_png):
        arr = load_image_as_array(tmp_png)
        assert arr.shape == (3, 20, 30)
        assert arr.dtype == np.float64
        assert 0.0 <= arr.min()
        assert arr.max() <= 1.0

    def test_gray_png(self, tmp_gray_png):
        arr = load_image_as_array(tmp_gray_png)
        assert arr.shape == (20, 30)
        assert arr.dtype == np.float64

    def test_rgba_converts_to_rgb(self, tmp_rgba_png):
        arr = load_image_as_array(tmp_rgba_png)
        # Alpha dropped, result is (3, H, W)
        assert arr.shape == (3, 20, 30)

    def test_jpeg(self, tmp_jpeg):
        arr = load_image_as_array(tmp_jpeg)
        assert arr.shape == (3, 20, 30)
        assert 0.0 <= arr.min()
        assert arr.max() <= 1.0

    def test_16bit_tiff(self, tmp_uint16_tiff):
        """16-bit TIFFs should be normalized to [0,1] via Pillow I;16 mode."""
        arr = load_image_as_array(tmp_uint16_tiff)
        assert arr.shape == (30, 40)
        assert 0.0 <= arr.min()
        assert arr.max() <= 1.0

    def test_float_tiff_delegates(self, tmp_float_tiff_mono):
        """Float TIFFs should route through load_image_data."""
        arr = load_image_as_array(tmp_float_tiff_mono)
        assert arr.shape == (60, 80)
        assert 0.0 <= arr.min()
        assert arr.max() <= 1.0

    def test_float_rgb_tiff(self, tmp_float_tiff_rgb):
        arr = load_image_as_array(tmp_float_tiff_rgb)
        assert arr.shape == (3, 40, 60)

    def test_8bit_tiff(self, tmp_uint8_tiff):
        arr = load_image_as_array(tmp_uint8_tiff)
        assert arr.shape == (30, 40)
        assert 0.0 <= arr.min()
        assert arr.max() <= 1.0


# ── read_header additional tests ────────────────────────────────────────────


class TestReadHeaderExtra:
    def test_header_cards_have_description(self, tmp_png):
        cards = read_header(tmp_png)
        for card in cards:
            assert "description" in card

    def test_png_text_chunks(self, tmp_path):
        """PNG text metadata should appear in header."""
        from PIL import PngImagePlugin

        img = Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8), "RGB")
        info = PngImagePlugin.PngInfo()
        info.add_text("Author", "TestAuthor")
        path = tmp_path / "text.png"
        img.save(path, pnginfo=info)

        cards = read_header(path)
        by_key = {c["key"]: c for c in cards}
        assert "Author" in by_key
        assert by_key["Author"]["value"] == "TestAuthor"
        assert by_key["Author"]["comment"] == "PNG text"

    def test_float_tiff_header_fields(self, tmp_float_tiff_mono):
        """Float TIFF header should at least have Format, Width, Height."""
        cards = read_header(tmp_float_tiff_mono)
        keys = {c["key"] for c in cards}
        assert "Format" in keys
        assert "Width" in keys
        assert "Height" in keys

        by_key = {c["key"]: c["value"] for c in cards}
        assert by_key["Width"] == "80"
        assert by_key["Height"] == "60"

    def test_jpeg_header(self, tmp_jpeg):
        cards = read_header(tmp_jpeg)
        by_key = {c["key"]: c["value"] for c in cards}
        assert by_key["Format"] == "JPEG"
        assert by_key["Width"] == "30"
        assert by_key["Height"] == "20"


# ── list_extensions additional tests ─────────────────────────────────────────


class TestListExtensionsExtra:
    def test_jpeg_extension(self, tmp_jpeg):
        exts = list_extensions(tmp_jpeg)
        assert len(exts) == 1
        assert exts[0]["name"] == "JPEG"
        assert exts[0]["has_image"] is True
        assert "30x20" in exts[0]["type"]

    def test_png_extension_details(self, tmp_png):
        exts = list_extensions(tmp_png)
        assert exts[0]["index"] == 0
        assert exts[0]["name"] == "PNG"
        assert "30x20" in exts[0]["type"]

    def test_float_tiff_extension_has_dtype(self, tmp_float_tiff_mono):
        exts = list_extensions(tmp_float_tiff_mono)
        assert exts[0]["name"] == "TIFF"
        assert "80x60" in exts[0]["type"]


# ── load_image_bytes additional tests ────────────────────────────────────────


class TestLoadImageBytesExtra:
    def test_float_rgb_tiff(self, tmp_float_tiff_rgb):
        """Float RGB TIFF should produce valid PNG bytes."""
        png_bytes = load_image_bytes(tmp_float_tiff_rgb)
        img = Image.open(io.BytesIO(png_bytes))
        assert img.format == "PNG"

    def test_jpeg_produces_png(self, tmp_jpeg):
        png_bytes = load_image_bytes(tmp_jpeg)
        assert png_bytes[:4] == b"\x89PNG"

    def test_gray_png_produces_png(self, tmp_gray_png):
        png_bytes = load_image_bytes(tmp_gray_png)
        assert png_bytes[:4] == b"\x89PNG"


# ── EXIF metadata parsing ──────────────────────────────────────────────────


class TestExifParsing:
    def test_jpeg_with_exif(self, tmp_path):
        """JPEG with EXIF data should surface tags in header."""
        from PIL.ExifTags import Base

        arr = np.random.default_rng(42).integers(0, 255, (20, 30, 3), dtype=np.uint8)
        img = Image.fromarray(arr, "RGB")

        exif = img.getexif()
        exif[Base.Make] = "TestCamera"
        exif[Base.Model] = "TestModel"
        path = tmp_path / "exif.jpg"
        img.save(path, exif=exif.tobytes())

        cards = read_header(path)
        keys = {c["key"] for c in cards}
        assert "Make" in keys
        by_key = {c["key"]: c["value"] for c in cards}
        assert by_key["Make"] == "TestCamera"


# ── Palette/P mode image conversion ────────────────────────────────────────


class TestPaletteModeConversion:
    def test_palette_mode_converts_to_rgb(self, tmp_path):
        """P (palette) mode should be converted to RGB."""
        img = Image.new("P", (20, 15))
        path = tmp_path / "palette.png"
        img.save(path)

        arr = load_image_as_array(path)
        # Converted to RGB: (3, H, W)
        assert arr.shape == (3, 15, 20)


# ── BinaryIO edge cases for is_float_tiff ─────────────────────────────────


class TestIsFloatTiffBinaryIOEdges:
    def test_binaryio_broken_seek(self):
        """BinaryIO where seek fails after exception should still return False."""

        # Provide garbage data that will fail tifffile, and a broken seek
        class BrokenSeekIO(io.BytesIO):
            _seek_count = 0

            def seek(self, *args, **kwargs):
                self._seek_count += 1
                if self._seek_count > 1:
                    raise OSError("seek failed")
                return super().seek(*args, **kwargs)

        buf = BrokenSeekIO(b"not a tiff at all")
        result = is_float_tiff(buf)
        assert result is False


# ── load_image_bytes fallback paths ───────────────────────────────────────


class TestLoadImageBytesFallback:
    def test_float_tiff_binaryio_fallback(self, tmp_float_tiff_mono):
        """Float TIFF via BinaryIO should work through the fallback path."""
        with open(tmp_float_tiff_mono, "rb") as f:
            buf = io.BytesIO(f.read())
        png_bytes = load_image_bytes(buf)
        img = Image.open(io.BytesIO(png_bytes))
        assert img.format == "PNG"

    def test_non_tiff_raises(self):
        """Non-TIFF, non-image data should raise when load_image_bytes fails."""
        buf = io.BytesIO(b"this is not an image at all")
        with pytest.raises(Exception):
            load_image_bytes(buf)

    def test_non_tiff_path_raises(self, tmp_path):
        """A non-image file with non-TIFF extension should raise."""
        bad_file = tmp_path / "bad.png"
        bad_file.write_bytes(b"not a valid image")
        with pytest.raises(Exception):
            load_image_bytes(bad_file)


# ── read_header fallback / EXIF edge cases ──────────────────────────────────


class TestReadHeaderFallback:
    def test_float_tiff_binaryio_header(self, tmp_float_tiff_mono):
        """Float TIFF via BinaryIO should fall back to tifffile for header."""
        with open(tmp_float_tiff_mono, "rb") as f:
            buf = io.BytesIO(f.read())
        cards = read_header(buf)
        keys = {c["key"] for c in cards}
        assert "Format" in keys
        assert "Width" in keys
        assert "Height" in keys

    def test_non_tiff_binaryio_raises(self):
        """Non-TIFF BinaryIO that Pillow can't open should raise."""
        buf = io.BytesIO(b"not a valid image")
        with pytest.raises(Exception):
            read_header(buf)

    def test_exif_bytes_value_skipped(self, tmp_path):
        """EXIF tags with long bytes values should be skipped."""
        from PIL.ExifTags import Base

        arr = np.random.default_rng(42).integers(0, 255, (20, 30, 3), dtype=np.uint8)
        img = Image.fromarray(arr, "RGB")
        exif = img.getexif()
        exif[Base.Make] = "TestMake"
        # MakerNote is typically a large bytes value
        exif[Base.MakerNote] = b"\x00" * 100
        path = tmp_path / "exif_bytes.jpg"
        img.save(path, exif=exif.tobytes())

        cards = read_header(path)
        keys = {c["key"] for c in cards}
        assert "Make" in keys
        # MakerNote (large bytes) should be skipped
        assert "MakerNote" not in keys

    def test_exif_short_tuple_value(self, tmp_path):
        """EXIF tags with short tuple values should be stringified."""
        from PIL.ExifTags import Base

        arr = np.random.default_rng(42).integers(0, 255, (20, 30, 3), dtype=np.uint8)
        img = Image.fromarray(arr, "RGB")
        exif = img.getexif()
        exif[Base.Make] = "TupleMake"
        # Some EXIF tags can be tuples
        exif[Base.XResolution] = 72
        path = tmp_path / "exif_tuple.jpg"
        img.save(path, exif=exif.tobytes())

        cards = read_header(path)
        keys = {c["key"] for c in cards}
        assert "Make" in keys


# ── list_extensions fallback path ──────────────────────────────────────────


class TestListExtensionsFallback:
    def test_float_tiff_binaryio_extensions(self, tmp_float_tiff_mono):
        """Float TIFF via BinaryIO should fall back to tifffile for extensions."""
        with open(tmp_float_tiff_mono, "rb") as f:
            buf = io.BytesIO(f.read())
        exts = list_extensions(buf)
        assert len(exts) == 1
        assert exts[0]["name"] == "TIFF"
        assert exts[0]["has_image"] is True

    def test_non_tiff_binaryio_raises(self):
        """Non-TIFF BinaryIO should raise when Pillow fails."""
        buf = io.BytesIO(b"not a valid image")
        with pytest.raises(Exception):
            list_extensions(buf)
