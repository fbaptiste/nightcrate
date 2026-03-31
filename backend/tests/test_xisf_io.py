"""Tests for the XISF clean-room parser."""

import struct
import zlib

import lz4.block
import numpy as np
import pytest
import zstandard

from nightcrate.services.xisf_io import (
    XISFError,
    _byte_unshuffle,
    _decompress_blocks,
    _extract_property_value,
    list_extensions,
    load_image_data,
    read_header,
)

# ── Helpers to build test XISF files ─────────────────────────────────────────


def _make_xisf(
    width: int,
    height: int,
    channels: int,
    sample_format: str,
    pixel_data: bytes,
    compression: str = "",
    fits_keywords: list[tuple[str, str, str]] | None = None,
    properties: list[tuple[str, str, str]] | None = None,
) -> bytes:
    """Build a minimal valid XISF file in memory."""
    geom = f"{width}:{height}:{channels}" if channels > 1 else f"{width}:{height}:1"
    color_space = "RGB" if channels == 3 else "Gray"

    # XML header
    kw_xml = ""
    if fits_keywords:
        for name, value, comment in fits_keywords:
            kw_xml += f'<FITSKeyword name="{name}" value="{value}" comment="{comment}" />\n'

    prop_xml = ""
    if properties:
        for pid, ptype, pval in properties:
            prop_xml += f'<Property id="{pid}" type="{ptype}" value="{pval}" />\n'

    # Data will be placed at offset = 16 + header_len (aligned to 4096 for realism)
    # We'll compute the actual offset after knowing header size
    placeholder_offset = 4096
    data_size = len(pixel_data)

    comp_attr = f' compression="{compression}"' if compression else ""
    location = f"attachment:{placeholder_offset}:{data_size}"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<xisf version="1.0" xmlns="http://www.pixinsight.com/xisf">
<Image geometry="{geom}" sampleFormat="{sample_format}" colorSpace="{color_space}"
       location="{location}"{comp_attr}>
{kw_xml}{prop_xml}</Image>
</xisf>"""

    xml_bytes = xml.encode("utf-8")
    header_len = len(xml_bytes)

    # Pad to align data at placeholder_offset
    total_header = 16 + header_len
    if total_header < placeholder_offset:
        padding = b"\x00" * (placeholder_offset - total_header)
    else:
        # Header too big for 4096 alignment, recalculate
        placeholder_offset = total_header
        # Re-generate XML with correct offset
        location = f"attachment:{placeholder_offset}:{data_size}"
        xml = xml.replace(f"attachment:4096:{data_size}", location)
        xml_bytes = xml.encode("utf-8")
        header_len = len(xml_bytes)
        padding = b""

    # Assemble file
    magic = b"XISF0100"
    header_len_le = struct.pack("<I", header_len)
    reserved = struct.pack("<I", 0)

    return magic + header_len_le + reserved + xml_bytes + padding + pixel_data


def _make_sub_blocks(data: bytes, compress_fn) -> bytes:
    """Wrap data in XISF sub-block format: [compressed_size:u64][uncompressed_size:u64][data]."""
    compressed = compress_fn(data)
    header = struct.pack("<QQ", len(compressed), len(data))
    return header + compressed


class TestByteUnshuffle:
    def test_uint16_round_trip(self):
        """Shuffled → unshuffled should restore original byte order for uint16."""
        original = np.array([1000, 2000, 3000, 4000], dtype=np.uint16)
        raw = original.tobytes()
        # Simulate shuffle: group by byte position
        arr = np.frombuffer(raw, dtype=np.uint8)
        item_size = 2
        group_size = len(arr) // item_size
        shuffled = arr.reshape(group_size, item_size).T.ravel().tobytes()
        # Unshuffle
        restored = _byte_unshuffle(shuffled, item_size)
        assert restored == raw

    def test_float32_round_trip(self):
        original = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        raw = original.tobytes()
        arr = np.frombuffer(raw, dtype=np.uint8)
        item_size = 4
        group_size = len(arr) // item_size
        shuffled = arr.reshape(group_size, item_size).T.ravel().tobytes()
        restored = _byte_unshuffle(shuffled, item_size)
        assert restored == raw

    def test_invalid_length_raises(self):
        with pytest.raises(XISFError, match="not divisible"):
            _byte_unshuffle(b"\x00\x01\x02", 2)


class TestDecompressBlocks:
    def test_zlib(self):
        original = b"\x01\x02\x03\x04" * 100
        compressed = zlib.compress(original)
        sub_block = struct.pack("<QQ", len(compressed), len(original)) + compressed
        result = _decompress_blocks(sub_block, "zlib", len(original), 1)
        assert result == original

    def test_lz4(self):
        original = b"\x01\x02\x03\x04" * 100
        compressed = lz4.block.compress(original, store_size=False)
        sub_block = struct.pack("<QQ", len(compressed), len(original)) + compressed
        result = _decompress_blocks(sub_block, "lz4", len(original), 1)
        assert result == original

    def test_zstd(self):
        original = b"\x01\x02\x03\x04" * 100
        cctx = zstandard.ZstdCompressor()
        compressed = cctx.compress(original)
        sub_block = struct.pack("<QQ", len(compressed), len(original)) + compressed
        result = _decompress_blocks(sub_block, "zstd", len(original), 1)
        assert result == original

    def test_uncompressed_passthrough(self):
        original = b"\x01\x02\x03\x04"
        sub_block = struct.pack("<QQ", len(original), len(original)) + original
        result = _decompress_blocks(sub_block, "zlib", len(original), 1)
        assert result == original

    def test_unsupported_codec(self):
        # comp_size < uncomp_size forces actual decompression (not passthrough)
        sub_block = struct.pack("<QQ", 3, 4) + b"\x00" * 3
        with pytest.raises(XISFError, match="Unsupported"):
            _decompress_blocks(sub_block, "brotli", 4, 1)


class TestLoadImageData:
    def test_mono_uint16_uncompressed(self, tmp_path):
        data = np.arange(0, 100, dtype=np.uint16).reshape(10, 10)
        xisf_bytes = _make_xisf(10, 10, 1, "UInt16", data.tobytes())
        path = tmp_path / "mono.xisf"
        path.write_bytes(xisf_bytes)

        result = load_image_data(path)
        assert result.shape == (10, 10)
        assert result.dtype == np.float64
        assert result.min() >= 0.0
        assert result.max() <= 1.0

    def test_rgb_float32_uncompressed(self, tmp_path):
        data = np.random.default_rng(42).uniform(0, 1, (3, 8, 10)).astype(np.float32)
        xisf_bytes = _make_xisf(10, 8, 3, "Float32", data.tobytes())
        path = tmp_path / "color.xisf"
        path.write_bytes(xisf_bytes)

        result = load_image_data(path)
        assert result.shape == (3, 8, 10)
        assert result.min() >= 0.0
        assert result.max() <= 1.0

    def test_mono_zlib_compressed(self, tmp_path):
        data = np.arange(0, 100, dtype=np.uint16).reshape(10, 10)
        raw = data.tobytes()
        compressed = zlib.compress(raw)
        sub_block = struct.pack("<QQ", len(compressed), len(raw)) + compressed

        xisf_bytes = _make_xisf(
            10,
            10,
            1,
            "UInt16",
            sub_block,
            compression=f"zlib:{len(raw)}",
        )
        path = tmp_path / "compressed.xisf"
        path.write_bytes(xisf_bytes)

        result = load_image_data(path)
        assert result.shape == (10, 10)

    def test_bad_magic_raises(self, tmp_path):
        path = tmp_path / "bad.xisf"
        path.write_bytes(b"NOT_XISF" + b"\x00" * 100)
        with pytest.raises(XISFError, match="Not an XISF"):
            load_image_data(path)

    def test_hdu_out_of_range(self, tmp_path):
        data = np.zeros((4, 4), dtype=np.uint16)
        xisf_bytes = _make_xisf(4, 4, 1, "UInt16", data.tobytes())
        path = tmp_path / "single.xisf"
        path.write_bytes(xisf_bytes)

        with pytest.raises(ValueError, match="out of range"):
            load_image_data(path, hdu=5)


class TestReadHeader:
    def test_fits_keywords(self, tmp_path):
        data = np.zeros((4, 4), dtype=np.uint16)
        xisf_bytes = _make_xisf(
            4,
            4,
            1,
            "UInt16",
            data.tobytes(),
            fits_keywords=[
                ("OBJECT", "M31", "Target name"),
                ("EXPTIME", "300.0", "Exposure"),
                ("FILTER", "Ha", "Filter"),
            ],
        )
        path = tmp_path / "header.xisf"
        path.write_bytes(xisf_bytes)

        cards = read_header(path)
        keys = {c["key"] for c in cards}
        assert "OBJECT" in keys
        assert "EXPTIME" in keys
        assert "FILTER" in keys

    def test_xisf_properties_mapped(self, tmp_path):
        data = np.zeros((4, 4), dtype=np.uint16)
        xisf_bytes = _make_xisf(
            4,
            4,
            1,
            "UInt16",
            data.tobytes(),
            properties=[
                ("Instrument:Filter:Name", "String", "Ha"),
                ("Instrument:ExposureTime", "Float64", "300.0"),
            ],
        )
        path = tmp_path / "props.xisf"
        path.write_bytes(xisf_bytes)

        cards = read_header(path)
        keys = {c["key"] for c in cards}
        assert "FILTER" in keys
        assert "EXPTIME" in keys


class TestListExtensions:
    def test_single_image(self, tmp_path):
        data = np.zeros((4, 4), dtype=np.uint16)
        xisf_bytes = _make_xisf(4, 4, 1, "UInt16", data.tobytes())
        path = tmp_path / "single.xisf"
        path.write_bytes(xisf_bytes)

        exts = list_extensions(path)
        assert len(exts) == 1
        assert exts[0]["has_image"] is True
        assert exts[0]["index"] == 0


class TestExtractPropertyValue:
    def test_inline_value(self):
        from xml.etree.ElementTree import Element

        elem = Element("Property", attrib={"value": "hello"})
        assert _extract_property_value(elem) == "hello"

    def test_empty_returns_empty(self):
        from xml.etree.ElementTree import Element

        elem = Element("Property")
        assert _extract_property_value(elem) == ""

    def test_plain_text(self):
        from xml.etree.ElementTree import Element

        elem = Element("Property", attrib={"type": "Int32"})
        elem.text = "42"
        assert _extract_property_value(elem) == "42"
