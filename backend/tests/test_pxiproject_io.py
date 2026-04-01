"""Tests for the PixInsight .pxiproject parser."""

import struct
import zlib

import lz4.block
import numpy as np
import pytest
import zstandard

from nightcrate.services.pxiproject_io import (
    PxiProjectError,
    RAWIMAGE_HEADER_SIZE,
    RAWIMAGE_MAGIC,
    _decompress_blob,
    _decompress_channel_section,
    _parse_rawimage_header,
    list_extensions,
    list_project_images,
    load_image_data,
    read_header,
)


# ── Helpers to build test .pxiproject bundles ────────────────────────────────


def _make_rawimage_header(
    width: int, height: int, channels: int = 1, bps: int = 32
) -> bytes:
    """Build a 128-byte rawimage swap header."""
    header = bytearray(RAWIMAGE_HEADER_SIZE)
    header[0:8] = RAWIMAGE_MAGIC
    header[15] = bps
    struct.pack_into("<I", header, 16, 1)  # channels_in_blob = 1
    struct.pack_into("<I", header, 28, width)
    struct.pack_into("<I", header, 32, height)
    struct.pack_into("<I", header, 36, channels)  # total_channels
    return bytes(header)


def _make_compressed_channel(data: bytes, codec: str) -> bytes:
    """Compress a single channel's data into the block format used by pxiproject blobs.

    Format: num_blocks(uint32) + per block: comp_size(uint64) + uncomp_size(uint64) + 16-byte prefix + compressed_data
    """
    if codec == "zlib":
        compressed = zlib.compress(data)
    elif codec in ("lz4", "lz4hc"):
        compressed = lz4.block.compress(data, store_size=False)
    elif codec == "zstd":
        compressed = zstandard.ZstdCompressor().compress(data)
    else:
        raise ValueError(f"Unknown codec: {codec}")

    prefix = b"\x00" * 16  # 16-byte block prefix
    block = struct.pack("<QQ", len(compressed), len(data)) + prefix + compressed
    return struct.pack("<I", 1) + block  # 1 block


def _make_uncompressed_channel(data: bytes) -> bytes:
    """Build an uncompressed channel section (comp_size == uncomp_size)."""
    prefix = b"\x00" * 16
    block = struct.pack("<QQ", len(data), len(data)) + prefix + data
    return struct.pack("<I", 1) + block


def _make_xosm(
    images: list[dict],
    compression: str = "none",
) -> str:
    """Build a minimal XOSM XML string."""
    ns = "http://www.pixinsight.com/xosm"
    image_windows = ""
    for img in images:
        view = img["name"]
        file_path_attr = f' filePath="{img["file_path"]}" copy="true" format="XISF"' if img.get("file_path") else ""
        stf_enabled = img.get("stf_enabled", "1")
        stf_midtone = img.get("stf_midtone")
        data_src = img.get("data_src", "")

        stf_xml = ""
        if stf_midtone is not None:
            stf_xml = f'<stf xmlns="{ns}" m="{stf_midtone}" c0="0" c1="1" r0="0" r1="1"/>'

        keywords_xml = ""
        for kw_name, kw_val, kw_comment in img.get("keywords", []):
            keywords_xml += f'<keyword xmlns="{ns}" name="{kw_name}" value="{kw_val}" comment="{kw_comment}"/>'
        fk_xml = f'<fitsKeywords xmlns="{ns}">{keywords_xml}</fitsKeywords>' if keywords_xml else ""

        image_xml = f'<image xmlns="{ns}" src="@project_data_dir/{data_src}"/>' if data_src else ""

        image_windows += f"""
        <ImageWindow xmlns="{ns}" currentView="{view}"{file_path_attr}>
            {fk_xml}
            <geometry xmlns="{ns}" visible="false" left="0" top="0" width="100" height="100"/>
            <MainView xmlns="{ns}" id="{view}" stfEnabled="{stf_enabled}">
                {stf_xml}
                {image_xml}
            </MainView>
        </ImageWindow>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<xosm version="1.2" xmlns="{ns}">
    <Project xmlns="{ns}">
        <features xmlns="{ns}" compression="{compression}"/>
    </Project>
    {image_windows}
</xosm>"""


def _make_project(tmp_path, images, compression="none", blobs=None):
    """Build a complete .pxiproject directory bundle for testing."""
    project_dir = tmp_path / "test.pxiproject"
    project_dir.mkdir()
    data_dir = project_dir / "project.data"
    data_dir.mkdir()

    xosm = _make_xosm(images, compression)
    (project_dir / "project.xosm").write_text(xosm)

    if blobs:
        for name, data in blobs.items():
            (data_dir / name).write_bytes(data)

    return project_dir


# ── Header parsing tests ────────────────────────────────────────────────────


class TestParseRawimageHeader:
    def test_basic_mono(self):
        header = _make_rawimage_header(100, 80, channels=1, bps=32)
        w, h, ch, bps = _parse_rawimage_header(header)
        assert (w, h, ch, bps) == (100, 80, 1, 32)

    def test_rgb(self):
        header = _make_rawimage_header(200, 150, channels=3, bps=32)
        w, h, ch, bps = _parse_rawimage_header(header)
        assert (w, h, ch, bps) == (200, 150, 3, 32)

    def test_uint16(self):
        header = _make_rawimage_header(50, 40, channels=1, bps=16)
        _, _, _, bps = _parse_rawimage_header(header)
        assert bps == 16

    def test_fallback_to_channels_in_blob(self):
        """When total_channels (offset 36) is 0, falls back to channels_in_blob (offset 16)."""
        header = bytearray(_make_rawimage_header(10, 10, channels=1, bps=32))
        struct.pack_into("<I", header, 36, 0)  # zero out total_channels
        struct.pack_into("<I", header, 16, 1)  # channels_in_blob = 1
        _, _, ch, _ = _parse_rawimage_header(bytes(header))
        assert ch == 1

    def test_bad_magic(self):
        header = b"\x00" * RAWIMAGE_HEADER_SIZE
        with pytest.raises(PxiProjectError, match="Bad rawimage magic"):
            _parse_rawimage_header(header)

    def test_too_small(self):
        with pytest.raises(PxiProjectError, match="too small"):
            _parse_rawimage_header(b"egamiwar" + b"\x00" * 10)


# ── Decompression tests ────────────────────────────────────────────────────


class TestDecompressBlob:
    def _make_mono_pixel_data(self, width, height):
        rng = np.random.default_rng(42)
        return rng.uniform(0.0, 1.0, size=(height, width)).astype(np.float32).tobytes()

    def test_uncompressed(self):
        pixels = self._make_mono_pixel_data(10, 8)
        result = _decompress_blob(pixels, "none", 1)
        assert result == pixels

    def test_zlib(self):
        pixels = self._make_mono_pixel_data(10, 8)
        blob = _make_compressed_channel(pixels, "zlib")
        result = _decompress_blob(blob, "zlib", 1)
        assert result == pixels

    def test_lz4(self):
        pixels = self._make_mono_pixel_data(10, 8)
        blob = _make_compressed_channel(pixels, "lz4")
        result = _decompress_blob(blob, "lz4", 1)
        assert result == pixels

    def test_zstd(self):
        pixels = self._make_mono_pixel_data(10, 8)
        blob = _make_compressed_channel(pixels, "zstd")
        result = _decompress_blob(blob, "zstd", 1)
        assert result == pixels

    def test_zstd_plus_sh_strips_shuffle_flag(self):
        """zstd+sh should decompress using zstd (shuffle is not applied to pixel data)."""
        pixels = self._make_mono_pixel_data(10, 8)
        blob = _make_compressed_channel(pixels, "zstd")
        result = _decompress_blob(blob, "zstd+sh", 1)
        assert result == pixels

    def test_multi_channel(self):
        """RGB blob contains 3 separate channel sections."""
        rng = np.random.default_rng(7)
        ch_size = 10 * 8 * 4  # 10x8 float32
        channels = [rng.bytes(ch_size) for _ in range(3)]
        blob = b"".join(_make_compressed_channel(ch, "zlib") for ch in channels)
        result = _decompress_blob(blob, "zlib", 3)
        assert result == b"".join(channels)

    def test_uncompressed_block(self):
        """Block with comp_size == uncomp_size is stored uncompressed."""
        pixels = b"\x01\x02\x03\x04" * 10
        blob = _make_uncompressed_channel(pixels)
        result = _decompress_blob(blob, "zlib", 1)
        assert result == pixels

    def test_unsupported_codec(self):
        pixels = self._make_mono_pixel_data(4, 4)
        blob = _make_compressed_channel(pixels, "zlib")
        with pytest.raises(PxiProjectError, match="Unsupported compression"):
            _decompress_blob(blob, "brotli", 1)


# ── XOSM parsing tests ─────────────────────────────────────────────────────


class TestListProjectImages:
    def test_basic_listing(self, tmp_path):
        project = _make_project(tmp_path, [
            {"name": "L_raw", "file_path": "/data/L.xisf", "data_src": "blob-001",
             "keywords": [("FILTER", "'LUM'", "Filter"), ("EXPTIME", "120", "Exposure")]},
            {"name": "RGB_starless", "data_src": "blob-002",
             "keywords": [("OBJECT", "'M42'", "Target")]},
        ])
        images = list_project_images(project)
        assert len(images) == 2

        assert images[0]["name"] == "L_raw"
        assert images[0]["source"] == "referenced"
        assert images[0]["file_path"] == "/data/L.xisf"
        assert images[0]["filter"] == "LUM"
        assert images[0]["exposure"] == 120.0

        assert images[1]["name"] == "RGB_starless"
        assert images[1]["source"] == "embedded"
        assert images[1]["file_path"] is None
        assert images[1]["object"] == "M42"

    def test_linearity_stf_small_midtone(self, tmp_path):
        project = _make_project(tmp_path, [
            {"name": "Linear", "data_src": "b1", "stf_midtone": "0.0005"},
        ])
        images = list_project_images(project)
        assert images[0]["linear"] is True

    def test_linearity_stf_identity(self, tmp_path):
        project = _make_project(tmp_path, [
            {"name": "Stretched", "data_src": "b1", "stf_midtone": "0.5"},
        ])
        images = list_project_images(project)
        assert images[0]["linear"] is False

    def test_linearity_stf_enabled_no_elements(self, tmp_path):
        """STF enabled but no stf elements → linear (PixInsight auto-computes)."""
        project = _make_project(tmp_path, [
            {"name": "AutoSTF", "data_src": "b1", "stf_enabled": "1"},
        ])
        images = list_project_images(project)
        assert images[0]["linear"] is True

    def test_linearity_stf_disabled(self, tmp_path):
        project = _make_project(tmp_path, [
            {"name": "NoSTF", "data_src": "b1", "stf_enabled": "0"},
        ])
        images = list_project_images(project)
        assert images[0]["linear"] is False

    def test_missing_xosm(self, tmp_path):
        project = tmp_path / "bad.pxiproject"
        project.mkdir()
        with pytest.raises(PxiProjectError, match="project.xosm not found"):
            list_project_images(project)


class TestReadHeader:
    def test_reads_fits_keywords(self, tmp_path):
        project = _make_project(tmp_path, [
            {"name": "Img", "data_src": "b1",
             "keywords": [("OBJECT", "'M31'", "Target"), ("FILTER", "'Ha'", "Filter")]},
        ])
        cards = read_header(project, 0)
        keys = {c["key"] for c in cards}
        assert "OBJECT" in keys
        assert "FILTER" in keys

    def test_index_out_of_range(self, tmp_path):
        project = _make_project(tmp_path, [
            {"name": "Only", "data_src": "b1"},
        ])
        with pytest.raises(ValueError, match="out of range"):
            read_header(project, 5)


class TestListExtensions:
    def test_returns_single_entry(self, tmp_path):
        project = _make_project(tmp_path, [
            {"name": "TestImg", "data_src": "b1"},
        ])
        exts = list_extensions(project, 0)
        assert len(exts) == 1
        assert exts[0]["name"] == "TestImg"
        assert exts[0]["has_image"] is True
        assert "linear" in exts[0]

    def test_index_out_of_range(self, tmp_path):
        project = _make_project(tmp_path, [
            {"name": "Only", "data_src": "b1"},
        ])
        with pytest.raises(ValueError, match="out of range"):
            list_extensions(project, 3)


# ── End-to-end image loading tests ──────────────────────────────────────────


class TestLoadImageData:
    def test_embedded_mono_uncompressed(self, tmp_path):
        width, height = 10, 8
        rng = np.random.default_rng(42)
        pixels = rng.uniform(0.01, 0.9, size=(height, width)).astype(np.float32)

        header = _make_rawimage_header(width, height, channels=1, bps=32)
        blob = header + pixels.tobytes()

        project = _make_project(
            tmp_path,
            [{"name": "Mono", "data_src": "blob-001"}],
            compression="none",
            blobs={"blob-001": blob},
        )
        data = load_image_data(project, 0)
        assert data.shape == (height, width)
        assert data.dtype == np.float64
        assert data.min() >= 0.0
        assert data.max() <= 1.0

    def test_embedded_mono_zlib(self, tmp_path):
        width, height = 10, 8
        rng = np.random.default_rng(42)
        pixels = rng.uniform(0.01, 0.9, size=(height, width)).astype(np.float32)

        header = _make_rawimage_header(width, height, channels=1, bps=32)
        compressed_section = _make_compressed_channel(pixels.tobytes(), "zlib")
        blob = header + compressed_section

        project = _make_project(
            tmp_path,
            [{"name": "Mono", "data_src": "blob-001"}],
            compression="zlib",
            blobs={"blob-001": blob},
        )
        data = load_image_data(project, 0)
        assert data.shape == (height, width)
        np.testing.assert_allclose(data, pixels.astype(np.float64), atol=1e-6)

    def test_embedded_rgb_zstd(self, tmp_path):
        width, height = 8, 6
        rng = np.random.default_rng(99)
        channels = []
        for _ in range(3):
            ch = rng.uniform(0.01, 0.9, size=(height, width)).astype(np.float32)
            channels.append(ch)

        header = _make_rawimage_header(width, height, channels=3, bps=32)
        compressed = b"".join(
            _make_compressed_channel(ch.tobytes(), "zstd") for ch in channels
        )
        blob = header + compressed

        project = _make_project(
            tmp_path,
            [{"name": "RGB", "data_src": "blob-001"}],
            compression="zstd+sh",
            blobs={"blob-001": blob},
        )
        data = load_image_data(project, 0)
        assert data.shape == (3, height, width)
        assert data.dtype == np.float64

    def test_referenced_xisf(self, tmp_path):
        """Referenced images delegate to xisf_io — test with a real XISF file."""
        from nightcrate.services.xisf_io import XISF_NS

        width, height = 10, 8
        pixels = np.random.default_rng(42).uniform(0, 0.5, size=(height, width)).astype(np.float32)
        pixel_bytes = pixels.tobytes()

        # Build a minimal XISF file
        data_offset = 4096
        xml_str = f"""<?xml version="1.0" encoding="UTF-8"?>
<xisf version="1.0" xmlns="{XISF_NS}">
<Image geometry="{width}:{height}:1" sampleFormat="Float32" colorSpace="Gray"
       location="attachment:{data_offset}:{len(pixel_bytes)}" />
</xisf>"""
        xml_bytes = xml_str.encode("utf-8")
        header_len = len(xml_bytes)
        xisf_header = b"XISF0100" + struct.pack("<I", header_len) + b"\x00" * 4
        padding = b"\x00" * (data_offset - len(xisf_header) - len(xml_bytes))
        xisf_file = xisf_header + xml_bytes + padding + pixel_bytes

        xisf_path = tmp_path / "ref_image.xisf"
        xisf_path.write_bytes(xisf_file)

        project = _make_project(
            tmp_path,
            [{"name": "RefImg", "file_path": str(xisf_path), "data_src": "blob-001"}],
            blobs={"blob-001": b"\x00" * 128},  # dummy blob, not used for referenced
        )
        data = load_image_data(project, 0)
        assert data.shape == (height, width)

    def test_referenced_file_not_found(self, tmp_path):
        project = _make_project(
            tmp_path,
            [{"name": "Missing", "file_path": "/nonexistent/file.xisf", "data_src": "b1"}],
        )
        with pytest.raises(FileNotFoundError, match="Referenced file not found"):
            load_image_data(project, 0)

    def test_embedded_blob_not_found(self, tmp_path):
        project = _make_project(
            tmp_path,
            [{"name": "NoBlobFile", "data_src": "nonexistent-blob"}],
        )
        with pytest.raises(FileNotFoundError, match="Blob not found"):
            load_image_data(project, 0)

    def test_index_out_of_range(self, tmp_path):
        project = _make_project(
            tmp_path,
            [{"name": "Only", "data_src": "b1"}],
        )
        with pytest.raises(ValueError, match="out of range"):
            load_image_data(project, 5)

    def test_path_traversal_blocked(self, tmp_path):
        """data_src with ../ should be rejected."""
        secret = tmp_path / "secret.txt"
        secret.write_text("sensitive data")

        project = _make_project(
            tmp_path,
            [{"name": "Evil", "data_src": "../../secret.txt"}],
        )
        with pytest.raises(PxiProjectError, match="Invalid data source path"):
            load_image_data(project, 0)
