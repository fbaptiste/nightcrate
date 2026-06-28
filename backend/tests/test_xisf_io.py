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
    extra_xml: str = "",
) -> bytes:
    """Build a minimal valid XISF file in memory.

    ``extra_xml`` is injected verbatim inside the <Image> element (for Property
    elements whose payload lives in element text, e.g. base64 vectors/matrices).
    """
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
    prop_xml += extra_xml

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

    def test_single_stream_zstd(self):
        """Raw zstd stream (no sub-block headers) should decompress correctly."""
        original = b"\x01\x02\x03\x04" * 100
        cctx = zstandard.ZstdCompressor()
        raw = cctx.compress(original)
        result = _decompress_blocks(raw, "zstd", len(original), 1)
        assert result == original

    def test_single_stream_lz4(self):
        """Raw lz4 block (no sub-block headers) should decompress correctly."""
        original = b"\x01\x02\x03\x04" * 100
        raw = lz4.block.compress(original, store_size=False)
        # Ensure the sub-block header parse gives invalid sizes (triggering single-stream)
        result = _decompress_blocks(raw, "lz4", len(original), 1)
        assert result == original

    def test_single_stream_zlib(self):
        """Raw zlib stream (no sub-block headers) should decompress correctly."""
        original = b"\x01\x02\x03\x04" * 100
        raw = zlib.compress(original)
        result = _decompress_blocks(raw, "zlib", len(original), 1)
        assert result == original

    def test_lz4hc_codec_normalization(self):
        """lz4hc codec name (without hyphen) should be normalized to lz4-hc."""
        original = b"\x01\x02\x03\x04" * 100
        compressed = lz4.block.compress(original, store_size=False)
        sub_block = struct.pack("<QQ", len(compressed), len(original)) + compressed
        result = _decompress_blocks(sub_block, "lz4hc", len(original), 1)
        assert result == original

    def test_single_stream_with_shuffle(self):
        """Single-stream + byte shuffle should work correctly."""
        original = np.array([1000, 2000, 3000, 4000], dtype=np.uint16).tobytes()
        arr = np.frombuffer(original, dtype=np.uint8)
        item_size = 2
        group_size = len(arr) // item_size
        shuffled = arr.reshape(group_size, item_size).T.ravel().tobytes()
        cctx = zstandard.ZstdCompressor()
        raw = cctx.compress(shuffled)
        result = _decompress_blocks(raw, "zstd+sh", len(original), item_size)
        assert result == original


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

    def test_geometry_surfaced_as_naxis(self, tmp_path):
        # XISF keeps dimensions in the geometry attribute, not as FITS keywords;
        # read_header should derive NAXIS1/NAXIS2 from it.
        data = np.zeros((48, 64), dtype=np.uint16)  # H=48, W=64
        xisf_bytes = _make_xisf(64, 48, 1, "UInt16", data.tobytes())
        path = tmp_path / "geom.xisf"
        path.write_bytes(xisf_bytes)

        cards = {c["key"]: c["value"] for c in read_header(path)}
        assert cards["NAXIS1"] == "64"
        assert cards["NAXIS2"] == "48"

    def test_naxis_fits_keyword_wins_over_geometry(self, tmp_path):
        # A real NAXIS1 FITSKeyword must not be overwritten by the geometry value.
        data = np.zeros((48, 64), dtype=np.uint16)
        xisf_bytes = _make_xisf(
            64,
            48,
            1,
            "UInt16",
            data.tobytes(),
            fits_keywords=[("NAXIS1", "64", "Width")],
        )
        path = tmp_path / "geom2.xisf"
        path.write_bytes(xisf_bytes)
        naxis1 = [c for c in read_header(path) if c["key"] == "NAXIS1"]
        assert len(naxis1) == 1  # not duplicated

    def test_fits_keyword_values_have_quotes_stripped(self, tmp_path):
        """XISF FITSKeyword values with embedded quotes should be stripped."""
        data = np.zeros((4, 4), dtype=np.uint16)
        xisf_bytes = _make_xisf(
            4,
            4,
            1,
            "UInt16",
            data.tobytes(),
            fits_keywords=[
                ("FILTER", "'Ha'", "Filter name"),
                ("INSTRUME", "'ZWO ASI2600MM Pro'", "Camera"),
            ],
        )
        path = tmp_path / "quoted.xisf"
        path.write_bytes(xisf_bytes)

        cards = read_header(path)
        filter_card = next(c for c in cards if c["key"] == "FILTER")
        instrume_card = next(c for c in cards if c["key"] == "INSTRUME")
        assert filter_card["value"] == "Ha"
        assert instrume_card["value"] == "ZWO ASI2600MM Pro"


class TestAstrometricWcs:
    """PixInsight AstrometricSolution → synthetic FITS WCS cards."""

    @staticmethod
    def _astro_xml(crval, crpix, cd, projection="Gnomonic"):
        import base64

        def b(vals):
            return base64.b64encode(struct.pack(f"<{len(vals)}d", *vals)).decode()

        return (
            f'<Property id="PCL:AstrometricSolution:ProjectionSystem" type="String">'
            f"{projection}</Property>"
            '<Property id="PCL:AstrometricSolution:ReferenceCelestialCoordinates"'
            f' type="F64Vector" length="2" location="inline:base64">{b(crval)}</Property>'
            '<Property id="PCL:AstrometricSolution:ReferenceImageCoordinates"'
            f' type="F64Vector" length="2" location="inline:base64">{b(crpix)}</Property>'
            '<Property id="PCL:AstrometricSolution:LinearTransformationMatrix"'
            f' type="F64Matrix" rows="2" columns="2" location="inline:base64">{b(cd)}</Property>'
        )

    def test_reconstructs_wcs(self, tmp_path):
        from nightcrate.services.image_annotations import build_wcs, detect_wcs_from_cards

        data = np.zeros((800, 1000), dtype=np.uint16)
        crval = [300.0, 35.0]
        crpix = [499.0, 399.0]  # PI 0-based reference pixel
        cd = [1e-5, -3e-4, 3e-4, 1e-5]  # row-major CD1_1, CD1_2, CD2_1, CD2_2
        xisf = _make_xisf(
            1000, 800, 1, "UInt16", data.tobytes(), extra_xml=self._astro_xml(crval, crpix, cd)
        )
        path = tmp_path / "astro.xisf"
        path.write_bytes(xisf)

        wp = detect_wcs_from_cards(read_header(path))
        assert wp is not None
        assert wp.crval1 == pytest.approx(300.0)
        assert wp.crval2 == pytest.approx(35.0)
        assert wp.crpix1 == pytest.approx(500.0)  # PI 0-based + 1 → FITS 1-based
        assert wp.crpix2 == pytest.approx(400.0)
        assert wp.cd1_1 == pytest.approx(1e-5)
        assert wp.cd1_2 == pytest.approx(-3e-4)
        assert wp.cd2_1 == pytest.approx(3e-4)
        assert wp.cd2_2 == pytest.approx(1e-5)
        # Round trip: the 0-based reference pixel maps back to CRVAL.
        center = build_wcs(wp).pixel_to_world(crpix[0], crpix[1])
        assert center.ra.deg == pytest.approx(300.0, abs=1e-3)
        assert center.dec.deg == pytest.approx(35.0, abs=1e-3)

    def test_real_fits_wcs_keyword_wins(self, tmp_path):
        # A genuine FITSKeyword WCS value is not overwritten by the synthesized one.
        data = np.zeros((800, 1000), dtype=np.uint16)
        xisf = _make_xisf(
            1000,
            800,
            1,
            "UInt16",
            data.tobytes(),
            fits_keywords=[("CRVAL1", "42.0", "")],
            extra_xml=self._astro_xml([300.0, 35.0], [499.0, 399.0], [1e-5, -3e-4, 3e-4, 1e-5]),
        )
        path = tmp_path / "astro_realwcs.xisf"
        path.write_bytes(xisf)
        crval1 = [c for c in read_header(path) if c["key"] == "CRVAL1"]
        assert len(crval1) == 1
        assert crval1[0]["value"] == "42.0"

    def test_non_gnomonic_skipped(self, tmp_path):
        from nightcrate.services.image_annotations import detect_wcs_from_cards

        data = np.zeros((800, 1000), dtype=np.uint16)
        xisf = _make_xisf(
            1000,
            800,
            1,
            "UInt16",
            data.tobytes(),
            extra_xml=self._astro_xml(
                [300.0, 35.0], [499.0, 399.0], [1e-5, -3e-4, 3e-4, 1e-5], projection="Orthographic"
            ),
        )
        path = tmp_path / "astro_ortho.xisf"
        path.write_bytes(xisf)
        assert detect_wcs_from_cards(read_header(path)) is None

    def test_plain_xisf_has_no_wcs(self, tmp_path):
        from nightcrate.services.image_annotations import detect_wcs_from_cards

        data = np.zeros((4, 4), dtype=np.uint16)
        xisf = _make_xisf(4, 4, 1, "UInt16", data.tobytes())
        path = tmp_path / "plain.xisf"
        path.write_bytes(xisf)
        assert detect_wcs_from_cards(read_header(path)) is None


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
