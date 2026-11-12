"""Tests for the XISF clean-room parser."""

import base64
import hashlib
import io
import struct
import zlib

import numpy as np
import pytest
import zstandard

from nightcrate.services.xisf_io import (
    PropertyValue,
    XISFChecksumError,
    XISFError,
    XISFUnavailableError,
    _display_value,
    _read_property,
    list_extensions,
    load_image_data,
    read_header,
    read_solution,
    read_wcs_params,
    verify_image,
)

# ── Helpers to build test XISF files ─────────────────────────────────────────


def _make_xisf(
    width: int,
    height: int,
    channels: int,
    sample_format: str,
    pixel_data: bytes,
    compression: str = "",
    subblocks: str | None = None,
    checksum: str | None = None,
    byte_order: str = "little",
    pixel_storage: str | None = None,
    location_override: str | None = None,
    fits_keywords: list[tuple[str, str, str]] | None = None,
    properties: list[tuple[str, str, str]] | None = None,
    extra_xml: str = "",
    extra_children: str = "",
    geometry: str | None = None,
    color_space: str | None = None,
    bounds: str | None = None,
    include_geometry: bool = True,
) -> bytes:
    """Build a minimal valid XISF file in memory.

    ``extra_xml`` is injected verbatim inside the <Image> element (for Property
    elements whose payload lives in element text, e.g. base64 vectors/matrices).
    """
    geom = geometry or (f"{width}:{height}:{channels}" if channels > 1 else f"{width}:{height}:1")
    geometry_attr = f' geometry="{geom}"' if include_geometry else ""
    image_color_space = color_space or ("RGB" if channels == 3 else "Gray")

    # XML header
    kw_xml = ""
    if fits_keywords:
        for name, value, comment in fits_keywords:
            kw_xml += f'<FITSKeyword name="{name}" value="{value}" comment="{comment}" />\n'

    prop_xml = ""
    if properties:
        for pid, ptype, pval in properties:
            prop_xml += f'<Property id="{pid}" type="{ptype}" value="{pval}" />\n'
    prop_xml += extra_xml + extra_children

    # Data will be placed at offset = 16 + header_len (aligned to 4096 for realism)
    # We'll compute the actual offset after knowing header size
    placeholder_offset = 4096
    data_size = len(pixel_data)

    block_attrs = ""
    if compression and location_override != "embedded":
        block_attrs += f' compression="{compression}"'
    if subblocks and location_override != "embedded":
        block_attrs += f' subblocks="{subblocks}"'
    if checksum and location_override != "embedded":
        block_attrs += f' checksum="{checksum}"'
    if byte_order != "little":
        block_attrs += f' byteOrder="{byte_order}"'
    if pixel_storage is not None:
        block_attrs += f' pixelStorage="{pixel_storage}"'
    if bounds is not None:
        block_attrs += f' bounds="{bounds}"'

    location = location_override or f"attachment:{placeholder_offset}:{data_size}"
    block_text = ""
    attached_data = pixel_data
    if location == "inline:base64":
        block_text = base64.b64encode(pixel_data).decode()
        attached_data = b""
    elif location == "inline:hex":
        block_text = pixel_data.hex()
        attached_data = b""
    elif location == "embedded":
        data_attrs = ' encoding="hex"'
        if compression:
            data_attrs += f' compression="{compression}"'
        if subblocks:
            data_attrs += f' subblocks="{subblocks}"'
        if checksum:
            data_attrs += f' checksum="{checksum}"'
        block_text = f"<Data{data_attrs}>{pixel_data.hex()}</Data>"
        attached_data = b""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<xisf version="1.0" xmlns="http://www.pixinsight.com/xisf">
<Image{geometry_attr} sampleFormat="{sample_format}" colorSpace="{image_color_space}"
       location="{location}"{block_attrs}>
{block_text}{kw_xml}{prop_xml}</Image>
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

    return magic + header_len_le + reserved + xml_bytes + padding + attached_data


class TestLoadImageData:
    def test_verify_image_checks_stored_pixels_without_decompressing(self, tmp_path, monkeypatch):
        raw = np.arange(16, dtype=np.uint16).tobytes()
        checksum = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        good = tmp_path / "good.xisf"
        good.write_bytes(_make_xisf(4, 4, 1, "UInt16", raw, checksum=checksum))
        monkeypatch.setattr(
            "nightcrate.services.xisf_blocks._decompress",
            lambda *_args: pytest.fail("verification must not decompress"),
        )

        assert verify_image(good) is None
        damaged = bytearray(good.read_bytes())
        damaged[-1] ^= 1
        bad = tmp_path / "damaged.xisf"
        bad.write_bytes(damaged)
        with pytest.raises(XISFChecksumError):
            verify_image(bad)

    def test_verify_image_without_checksum_does_not_read_attached_pixels(self):
        class RecordingSource(io.BytesIO):
            def __init__(self, data):
                super().__init__(data)
                self.reads = []

            def read(self, size=-1):
                self.reads.append((self.tell(), size))
                return super().read(size)

        raw = np.arange(16, dtype=np.uint16).tobytes()
        source = RecordingSource(_make_xisf(4, 4, 1, "UInt16", raw))

        verify_image(source)

        assert not any(position >= 4096 for position, _size in source.reads)

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

    @pytest.mark.parametrize("geometry", ["0:10:1", "10:10:0"])
    def test_nonpositive_geometry_is_invalid_but_still_listed(self, tmp_path, geometry):
        path = tmp_path / f"invalid-{geometry.replace(':', '-')}.xisf"
        path.write_bytes(_make_xisf(1, 1, 1, "UInt16", b"", geometry=geometry))

        assert len(list_extensions(path)) == 1
        with pytest.raises(XISFError):
            load_image_data(path)

    @pytest.mark.parametrize("geometry", ["10", "x:4:4:1"])
    def test_corrupt_geometry_is_invalid(self, tmp_path, geometry):
        path = tmp_path / f"corrupt-{geometry.replace(':', '-')}.xisf"
        path.write_bytes(_make_xisf(1, 1, 1, "UInt16", b"", geometry=geometry))

        with pytest.raises(XISFError):
            load_image_data(path)

    def test_missing_geometry_is_invalid(self, tmp_path):
        path = tmp_path / "missing-geometry.xisf"
        path.write_bytes(
            _make_xisf(
                1,
                1,
                1,
                "UInt16",
                b"",
                include_geometry=False,
            )
        )

        with pytest.raises(XISFError):
            load_image_data(path)

    @pytest.mark.parametrize("geometry", ["10:10", "4:4:4:1"])
    def test_non_2d_geometry_is_unavailable_but_still_listed(self, tmp_path, geometry):
        path = tmp_path / f"unsupported-{geometry.replace(':', '-')}.xisf"
        path.write_bytes(_make_xisf(1, 1, 1, "UInt16", b"", geometry=geometry))

        assert len(list_extensions(path)) == 1
        with pytest.raises(XISFUnavailableError, match="only two-dimensional"):
            load_image_data(path)

    def test_float_bounds_rescale_to_unit_interval(self, tmp_path):
        values = np.array([-1.0, 0.0, 1.0, 2.0], dtype=np.float32)
        path = tmp_path / "float-bounds.xisf"
        path.write_bytes(_make_xisf(4, 1, 1, "Float32", values.tobytes(), bounds="-1:1"))

        np.testing.assert_allclose(load_image_data(path), [[0.0, 0.5, 1.0, 1.0]])

    def test_integer_bounds_override_type_range(self, tmp_path):
        values = np.array([0, 4095, 8190], dtype=np.uint16)
        path = tmp_path / "integer-bounds.xisf"
        path.write_bytes(_make_xisf(3, 1, 1, "UInt16", values.tobytes(), bounds="0:4095"))

        np.testing.assert_array_equal(load_image_data(path), [[0.0, 1.0, 1.0]])

    def test_integer_zero_one_bounds_use_declared_range(self, tmp_path):
        values = np.array([0, 1], dtype=np.uint16)
        path = tmp_path / "integer-zero-one.xisf"
        path.write_bytes(_make_xisf(2, 1, 1, "UInt16", values.tobytes(), bounds="0:1"))

        np.testing.assert_array_equal(load_image_data(path), [[0.0, 1.0]])

    def test_zero_one_bounds_leave_float_path_unchanged(self, tmp_path):
        values = np.array([0.0, 0.25, 1.0], dtype=np.float32)
        plain = tmp_path / "plain-float.xisf"
        bounded = tmp_path / "bounded-float.xisf"
        plain.write_bytes(_make_xisf(3, 1, 1, "Float32", values.tobytes()))
        bounded.write_bytes(_make_xisf(3, 1, 1, "Float32", values.tobytes(), bounds="0:1"))

        np.testing.assert_array_equal(load_image_data(bounded), load_image_data(plain))

    @pytest.mark.parametrize("bounds", ["0", "low:high", "1:0", "nan:1"])
    def test_malformed_bounds_are_invalid(self, tmp_path, bounds):
        values = np.zeros((2, 2), dtype=np.float32)
        path = tmp_path / "bad-bounds.xisf"
        path.write_bytes(_make_xisf(2, 2, 1, "Float32", values.tobytes(), bounds=bounds))

        with pytest.raises(XISFError, match="invalid sample bounds"):
            load_image_data(path)

    def test_rgb_drops_alpha_channel(self, tmp_path):
        values = np.arange(16, dtype=np.uint16).reshape(4, 2, 2)
        path = tmp_path / "rgba.xisf"
        path.write_bytes(
            _make_xisf(
                2,
                2,
                4,
                "UInt16",
                values.tobytes(),
                color_space="RGB",
            )
        )

        result = load_image_data(path)
        assert result.shape == (3, 2, 2)
        np.testing.assert_array_equal(result, values[:3].astype(np.float64) / 65535.0)

    def test_gray_drops_extra_channel(self, tmp_path):
        values = np.arange(8, dtype=np.uint16).reshape(2, 2, 2)
        path = tmp_path / "gray-alpha.xisf"
        path.write_bytes(
            _make_xisf(
                2,
                2,
                2,
                "UInt16",
                values.tobytes(),
                color_space="Gray",
            )
        )

        result = load_image_data(path)
        assert result.shape == (2, 2)
        np.testing.assert_array_equal(result, values[0].astype(np.float64) / 65535.0)

    def test_cielab_color_space_is_unavailable(self, tmp_path):
        values = np.zeros((3, 2, 2), dtype=np.float32)
        path = tmp_path / "lab.xisf"
        path.write_bytes(
            _make_xisf(
                2,
                2,
                3,
                "Float32",
                values.tobytes(),
                color_space="CIELab",
            )
        )

        with pytest.raises(XISFUnavailableError, match="unsupported color space"):
            load_image_data(path)

    def test_mono_zlib_compressed(self, tmp_path):
        data = np.arange(0, 100, dtype=np.uint16).reshape(10, 10)
        raw = data.tobytes()
        compressed = zlib.compress(raw)

        xisf_bytes = _make_xisf(
            10,
            10,
            1,
            "UInt16",
            compressed,
            compression=f"zlib:{len(raw)}",
        )
        path = tmp_path / "compressed.xisf"
        path.write_bytes(xisf_bytes)

        result = load_image_data(path)
        assert result.shape == (10, 10)

    def test_normal_rgb_storage_becomes_planar(self, tmp_path):
        expected = np.empty((3, 2, 3), dtype=np.float32)
        for row in range(2):
            for col in range(3):
                expected[:, row, col] = (0.1 * (row + 1), 0.2 + 0.1 * col, 0.9)
        normal = np.moveaxis(expected, 0, 2)
        path = tmp_path / "normal.xisf"
        path.write_bytes(_make_xisf(3, 2, 3, "Float32", normal.tobytes(), pixel_storage="Normal"))

        result = load_image_data(path)

        assert result.shape == (3, 2, 3)
        np.testing.assert_allclose(result, expected)

    def test_big_endian_matches_little_endian(self, tmp_path):
        values = np.array([[1, 256], [65535, 4660]], dtype=np.uint16)
        little = tmp_path / "little.xisf"
        big = tmp_path / "big.xisf"
        little.write_bytes(_make_xisf(2, 2, 1, "UInt16", values.astype("<u2").tobytes()))
        big.write_bytes(
            _make_xisf(
                2,
                2,
                1,
                "UInt16",
                values.astype(">u2").tobytes(),
                byte_order="big",
            )
        )

        np.testing.assert_array_equal(load_image_data(big), load_image_data(little))

    @pytest.mark.parametrize("location", ["inline:base64", "embedded"])
    def test_inline_and_embedded_pixels(self, tmp_path, location):
        values = np.array([[1, 256], [65535, 4660]], dtype=np.uint16)
        attached = tmp_path / "attached.xisf"
        alternate = tmp_path / "alternate.xisf"
        attached.write_bytes(_make_xisf(2, 2, 1, "UInt16", values.tobytes()))
        alternate.write_bytes(
            _make_xisf(
                2,
                2,
                1,
                "UInt16",
                values.tobytes(),
                location_override=location,
            )
        )

        np.testing.assert_array_equal(load_image_data(alternate), load_image_data(attached))

    def test_zstd_shuffled_subblocks_include_stored_piece(self, tmp_path):
        values = np.arange(600, dtype=np.uint16).reshape(20, 30)
        raw = values.tobytes()
        bytes_view = np.frombuffer(raw, dtype=np.uint8)
        shuffled = bytes_view.reshape(len(raw) // 2, 2).T.ravel().tobytes()
        pieces = [shuffled[:400], shuffled[400:800], shuffled[800:]]
        first = zstandard.ZstdCompressor().compress(pieces[0])
        third = zstandard.ZstdCompressor().compress(pieces[2])
        stored = first + pieces[1] + third
        subblocks = f"{len(first)},400:400,400:{len(third)},400"
        compressed_path = tmp_path / "subblocks.xisf"
        plain_path = tmp_path / "plain.xisf"
        compressed_path.write_bytes(
            _make_xisf(
                30,
                20,
                1,
                "UInt16",
                stored,
                compression=f"zstd+sh:{len(raw)}:2",
                subblocks=subblocks,
            )
        )
        plain_path.write_bytes(_make_xisf(30, 20, 1, "UInt16", raw))

        np.testing.assert_array_equal(load_image_data(compressed_path), load_image_data(plain_path))

    def test_checksum_failure_does_not_break_header_reads(self, tmp_path):
        values = np.arange(16, dtype=np.uint16).reshape(4, 4)
        path = tmp_path / "damaged.xisf"
        path.write_bytes(
            _make_xisf(
                4,
                4,
                1,
                "UInt16",
                values.tobytes(),
                checksum=f"sha256:{'0' * 64}",
            )
        )

        with pytest.raises(XISFChecksumError):
            load_image_data(path)
        assert read_header(path)
        assert len(list_extensions(path)) == 1

    def test_unsupported_compression_does_not_break_header_read(self, tmp_path):
        raw = np.zeros((4, 4), dtype=np.uint16).tobytes()
        path = tmp_path / "unsupported.xisf"
        path.write_bytes(_make_xisf(4, 4, 1, "UInt16", raw, compression="brotli:32"))

        with pytest.raises(XISFUnavailableError):
            load_image_data(path)
        assert read_header(path)

    @pytest.mark.parametrize(
        "payload",
        [
            b"XISF0100\x01\x00",
            b"XISF0100" + struct.pack("<I", 100) + b"\x00" * 4 + b"<xisf/>",
            b"XISF0100" + struct.pack("<I", 7) + b"\x00" * 4 + b"<xisf>>",
        ],
        ids=["short-preamble", "header-past-end", "malformed-xml"],
    )
    @pytest.mark.parametrize("reader", [read_header, list_extensions, load_image_data])
    def test_invalid_headers_are_normalized(self, payload, reader):
        with pytest.raises(XISFError):
            reader(io.BytesIO(payload))

    def test_pixel_load_does_not_read_attached_property(self):
        class RecordingBytesIO(io.BytesIO):
            def __init__(self, value):
                super().__init__(value)
                self.reads = []

            def read(self, size=-1):
                start = self.tell()
                result = super().read(size)
                self.reads.append((start, len(result)))
                return result

        pixels = np.arange(16, dtype=np.uint16).reshape(4, 4)
        property_data = struct.pack("<4d", 1, 2, 3, 4)
        property_offset = 4096 + pixels.nbytes
        child = (
            '<Property id="Damaged" type="F64Matrix" rows="2" columns="2" '
            f'location="attachment:{property_offset}:{len(property_data)}" '
            f'checksum="sha256:{"0" * 64}" />'
        )
        source = RecordingBytesIO(
            _make_xisf(4, 4, 1, "UInt16", pixels.tobytes(), extra_children=child) + property_data
        )

        result = load_image_data(source)

        assert result.shape == (4, 4)
        assert all(
            start + size <= property_offset or start >= property_offset + len(property_data)
            for start, size in source.reads
        )

    def test_bad_magic_raises(self, tmp_path):
        path = tmp_path / "bad.xisf"
        path.write_bytes(b"NOT_XISF" + b"\x00" * 100)
        with pytest.raises(XISFError, match="not a valid XISF"):
            load_image_data(path)

    def test_hdu_out_of_range(self, tmp_path):
        data = np.zeros((4, 4), dtype=np.uint16)
        xisf_bytes = _make_xisf(4, 4, 1, "UInt16", data.tobytes())
        path = tmp_path / "single.xisf"
        path.write_bytes(xisf_bytes)

        with pytest.raises(ValueError, match="out of range"):
            load_image_data(path, hdu=5)


class TestReadHeader:
    def test_oversized_uncompressed_inline_string_is_rejected_before_decode(
        self, tmp_path, monkeypatch
    ):
        from nightcrate.services import xisf_blocks

        encoded = base64.b64encode(b"x" * 2048).decode()
        child = (
            f'<Property id="HugeInline" type="String" location="inline:base64">{encoded}</Property>'
        )
        path = tmp_path / "oversized-inline-property.xisf"
        path.write_bytes(
            _make_xisf(
                1,
                1,
                1,
                "UInt16",
                np.zeros((1, 1), dtype=np.uint16).tobytes(),
                extra_children=child,
            )
        )
        monkeypatch.setattr(xisf_blocks, "MAX_UNBOUNDED_BLOCK_SIZE", 1024)

        def fail_decode(*_args, **_kwargs):
            pytest.fail("base64 decoding was attempted")

        monkeypatch.setattr(xisf_blocks.base64, "b64decode", fail_decode)

        cards = read_header(path)

        value = next(card["value"] for card in cards if card["key"] == "HugeInline")
        assert "unavailable" in value

    def test_oversized_string_property_is_unavailable_without_breaking_header(self, tmp_path):
        compressed = zlib.compress(b"small string")
        encoded = base64.b64encode(compressed).decode()
        child = (
            '<Property id="HugeString" type="String" location="inline:base64" '
            f'compression="zlib:{300 * 1024 * 1024}">{encoded}</Property>'
        )
        path = tmp_path / "oversized-property.xisf"
        path.write_bytes(
            _make_xisf(
                1,
                1,
                1,
                "UInt16",
                np.zeros((1, 1), dtype=np.uint16).tobytes(),
                extra_children=child,
            )
        )

        cards = read_header(path)

        value = next(card["value"] for card in cards if card["key"] == "HugeString")
        assert "unavailable" in value
        assert "larger than 256 MiB" in value

    def test_nested_thumbnail_metadata_is_ignored(self, tmp_path):
        data = np.zeros((4, 4), dtype=np.uint16)
        thumbnail = (
            '<Thumbnail geometry="1:1:1" sampleFormat="UInt8" colorSpace="Gray" '
            'location="inline:hex">00'
            '<Property id="Observation:Object:Name" type="String" value="Wrong" />'
            "</Thumbnail>"
        )
        path = tmp_path / "thumbnail.xisf"
        path.write_bytes(_make_xisf(4, 4, 1, "UInt16", data.tobytes(), extra_children=thumbnail))

        assert "OBJECT" not in {card["key"] for card in read_header(path)}
        assert len(list_extensions(path)) == 1

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
    def _astro_xml(
        crval,
        crpix,
        cd,
        projection="Gnomonic",
        *,
        prefix="PCL:AstrometricSolution:",
        version=None,
        vector_type="F64Vector",
        matrix_type="F64Matrix",
        extra="",
    ):
        import base64

        def b(vals):
            return base64.b64encode(struct.pack(f"<{len(vals)}d", *vals)).decode()

        version_xml = (
            f'<Property id="{prefix}Version" type="String">{version}</Property>'
            if version is not None
            else ""
        )
        return (
            version_xml + f'<Property id="{prefix}ProjectionSystem" type="String">'
            f"{projection}</Property>"
            f'<Property id="{prefix}ReferenceCelestialCoordinates"'
            f' type="{vector_type}" length="2" location="inline:base64">{b(crval)}</Property>'
            f'<Property id="{prefix}ReferenceImageCoordinates"'
            f' type="{vector_type}" length="2" location="inline:base64">{b(crpix)}</Property>'
            f'<Property id="{prefix}LinearTransformationMatrix"'
            f' type="{matrix_type}" rows="2" columns="2" location="inline:base64">'
            f"{b(cd)}</Property>" + extra
        )

    def test_new_namespace_version_and_aliases(self, tmp_path):
        data = np.zeros((80, 100), dtype=np.uint16)
        native = base64.b64encode(struct.pack("<2d", 0.0, 90.0)).decode()
        pole = base64.b64encode(struct.pack("<2d", 180.0, 90.0)).decode()
        extra = (
            '<Property id="AstrometricSolution:CelestialReferenceSystem" '
            'type="String">FK5</Property>'
            '<Property id="AstrometricSolution:ReferenceNativeCoordinates" '
            f'type="F64Vector" length="2" location="inline:base64">{native}</Property>'
            '<Property id="AstrometricSolution:CelestialPoleNativeCoordinates" '
            f'type="F64Vector" length="2" location="inline:base64">{pole}</Property>'
        )
        xml = self._astro_xml(
            [300.0, 35.0],
            [49.0, 39.0],
            [1e-5, -3e-4, 3e-4, 1e-5],
            prefix="AstrometricSolution:",
            version="1.3",
            vector_type="Vector",
            matrix_type="Matrix",
            extra=extra,
        )
        # A complete legacy solution is present too; the new namespace wins.
        xml += self._astro_xml([42.0, -10.0], [12.0, 15.0], [-0.001, 0.0, 0.0, 0.001])
        path = tmp_path / "new-solution.xisf"
        path.write_bytes(_make_xisf(100, 80, 1, "UInt16", data.tobytes(), extra_xml=xml))

        result = read_solution(path)

        assert result.unavailable_reason is None
        assert result.wcs is not None
        assert result.wcs.crval1 == 300.0
        assert result.wcs.crpix1 == 49.5
        assert result.wcs.crpix2 == 39.5

    @pytest.mark.parametrize(
        ("version", "projection"),
        [
            (None, "Gnomonic"),
            ("2.0", "Gnomonic"),
            ("one", "Gnomonic"),
            ("1.0", "Stereographic"),
            ("1.0", "MysteryProjection"),
        ],
    )
    def test_new_namespace_unavailable_does_not_fall_back(self, tmp_path, version, projection):
        data = np.zeros((80, 100), dtype=np.uint16)
        new_xml = self._astro_xml(
            [300.0, 35.0],
            [49.0, 39.0],
            [1e-5, -3e-4, 3e-4, 1e-5],
            projection,
            prefix="AstrometricSolution:",
            version=version,
        )
        old_xml = self._astro_xml([42.0, -10.0], [12.0, 15.0], [-0.001, 0.0, 0.0, 0.001])
        fits = [
            ("CRVAL1", "83.0", ""),
            ("CRVAL2", "-5.0", ""),
            ("CRPIX1", "50.0", ""),
            ("CRPIX2", "30.0", ""),
            ("CD1_1", "-0.0002", ""),
            ("CD1_2", "0", ""),
            ("CD2_1", "0", ""),
            ("CD2_2", "0.0002", ""),
        ]
        path = tmp_path / "unavailable-new-solution.xisf"
        path.write_bytes(
            _make_xisf(
                100,
                80,
                1,
                "UInt16",
                data.tobytes(),
                fits_keywords=fits,
                extra_xml=new_xml + old_xml,
            )
        )

        result = read_solution(path)

        assert result.wcs is None
        assert result.unavailable_reason
        if projection != "Gnomonic":
            assert projection in result.unavailable_reason

    @pytest.mark.parametrize(
        "native_xml",
        [
            ("ReferenceNativeCoordinates", [0.0, 80.0]),
            ("CelestialPoleNativeCoordinates", [170.0, 90.0]),
        ],
    )
    def test_rotated_native_coordinates_are_unavailable(self, tmp_path, native_xml):
        name, values = native_xml
        encoded = base64.b64encode(struct.pack("<2d", *values)).decode()
        extra = (
            f'<Property id="AstrometricSolution:{name}" type="F64Vector" '
            f'length="2" location="inline:base64">{encoded}</Property>'
        )
        xml = self._astro_xml(
            [300.0, 35.0],
            [49.0, 39.0],
            [1e-5, -3e-4, 3e-4, 1e-5],
            prefix="AstrometricSolution:",
            version="1.0",
            extra=extra,
        )
        path = tmp_path / "rotated.xisf"
        path.write_bytes(
            _make_xisf(
                100, 80, 1, "UInt16", np.zeros((80, 100), dtype=np.uint16).tobytes(), extra_xml=xml
            )
        )

        result = read_solution(path)
        assert result.wcs is None
        assert result.unavailable_reason
        assert "unsupported coordinate layout" in result.unavailable_reason

    @pytest.mark.parametrize(
        ("crval", "cd"),
        [
            ([float("nan"), 35.0], [1e-5, -3e-4, 3e-4, 1e-5]),
            ([300.0, 35.0], [1e-4, 2e-4, 5e-5, 1e-4]),
        ],
        ids=["non-finite", "singular"],
    )
    def test_invalid_layer_one_values_are_unavailable(self, tmp_path, crval, cd):
        xml = self._astro_xml(
            crval,
            [49.0, 39.0],
            cd,
            prefix="AstrometricSolution:",
            version="1.0",
        )
        path = tmp_path / "invalid-layer-one.xisf"
        path.write_bytes(
            _make_xisf(
                100,
                80,
                1,
                "UInt16",
                np.zeros((80, 100), dtype=np.uint16).tobytes(),
                extra_xml=xml,
            )
        )

        result = read_solution(path)
        assert result.wcs is None
        assert result.unavailable_reason

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
        assert wp.crpix1 == pytest.approx(499.5)  # XISF half-integer convention
        assert wp.crpix2 == pytest.approx(399.5)
        assert wp.cd1_1 == pytest.approx(1e-5)
        assert wp.cd1_2 == pytest.approx(-3e-4)
        assert wp.cd2_1 == pytest.approx(3e-4)
        assert wp.cd2_2 == pytest.approx(1e-5)
        # Round trip: the 0-based reference pixel maps back to CRVAL.
        center = build_wcs(wp).pixel_to_world(crpix[0] - 0.5, crpix[1] - 0.5)
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

    def test_xisf_properties_win_whole(self, tmp_path):
        data = np.zeros((80, 100), dtype=np.uint16)
        properties = self._astro_xml(
            [300.0, 35.0],
            [49.0, 39.0],
            [1e-5, -3e-4, 3e-4, 1e-5],
        )
        keywords = [
            ("CRVAL1", "42.0", ""),
            ("CRVAL2", "-10.0", ""),
            ("CRPIX1", "12.0", ""),
            ("CRPIX2", "15.0", ""),
            ("CD1_1", "-0.001", ""),
            ("CD1_2", "0.0", ""),
            ("CD2_1", "0.0", ""),
            ("CD2_2", "0.001", ""),
        ]
        path = tmp_path / "properties_win.xisf"
        path.write_bytes(
            _make_xisf(
                100,
                80,
                1,
                "UInt16",
                data.tobytes(),
                fits_keywords=keywords,
                extra_xml=properties,
            )
        )

        result = read_wcs_params(path, 0)

        assert result is not None
        assert result.crval1 == pytest.approx(300.0)
        assert result.crval2 == pytest.approx(35.0)
        assert result.crpix1 == pytest.approx(49.5)
        assert result.crpix2 == pytest.approx(39.5)
        assert result.cd1_1 == pytest.approx(1e-5)
        assert result.cd1_2 == pytest.approx(-3e-4)
        assert result.cd2_1 == pytest.approx(3e-4)
        assert result.cd2_2 == pytest.approx(1e-5)

    def test_incomplete_astrometric_properties_fall_back_to_fits_keywords(self, tmp_path):
        data = np.zeros((80, 100), dtype=np.uint16)
        keywords = [
            ("CRVAL1", "83.633", ""),
            ("CRVAL2", "-5.375", ""),
            ("CRPIX1", "50.0", ""),
            ("CRPIX2", "30.0", ""),
            ("CD1_1", "-0.0002", ""),
            ("CD1_2", "-0.00015", ""),
            ("CD2_1", "-0.0001", ""),
            ("CD2_2", "0.00025", ""),
        ]
        path = tmp_path / "information_only.xisf"
        path.write_bytes(
            _make_xisf(
                100,
                80,
                1,
                "UInt16",
                data.tobytes(),
                fits_keywords=keywords,
                properties=[
                    (
                        "PCL:AstrometricSolution:Information",
                        "String",
                        "metadata but no solution",
                    )
                ],
            )
        )

        result = read_wcs_params(path, 0)

        assert result is not None
        assert result.crval1 == pytest.approx(83.633)
        assert result.crpix2 == pytest.approx(51.0)
        assert result.cd1_2 == pytest.approx(0.00015)
        assert result.cd2_2 == pytest.approx(-0.00025)

    def test_xisf_keyword_flip_uses_geometry_dimensions(self, tmp_path):
        width, height = 100, 3000
        data = np.zeros((height, width), dtype=np.uint16)
        keywords = [
            ("NAXIS1", "5000", "stale pre-crop width"),
            ("NAXIS2", "4000", "stale pre-crop height"),
            ("CRVAL1", "83.633", ""),
            ("CRVAL2", "-5.375", ""),
            ("CRPIX1", "50.0", ""),
            ("CRPIX2", "100.0", ""),
            ("CD1_1", "-0.0002", ""),
            ("CD1_2", "-0.00015", ""),
            ("CD2_1", "-0.0001", ""),
            ("CD2_2", "0.00025", ""),
        ]
        path = tmp_path / "cropped_keywords.xisf"
        path.write_bytes(
            _make_xisf(
                width,
                height,
                1,
                "UInt16",
                data.tobytes(),
                fits_keywords=keywords,
            )
        )

        result = read_wcs_params(path, 0)

        assert result is not None
        assert result.naxis1 == width
        assert result.naxis2 == height
        assert result.crpix2 == pytest.approx(2901.0)

    @pytest.mark.parametrize("matrix_form", ["cd", "cdelt"])
    def test_xisf_fits_keywords_are_flipped(self, tmp_path, matrix_form):
        from nightcrate.services.image_annotations import build_wcs, detect_wcs_from_cards

        width, height = 100, 80
        data = np.zeros((height, width), dtype=np.uint16)
        common = [
            ("CRVAL1", "83.633", ""),
            ("CRVAL2", "-5.375", ""),
            ("CRPIX1", "50.0", ""),
            ("CRPIX2", "30.0", ""),
        ]
        if matrix_form == "cd":
            matrix = [
                ("CD1_1", "-0.0002", ""),
                ("CD1_2", "-0.00015", ""),
                ("CD2_1", "-0.0001", ""),
                ("CD2_2", "0.000259807621135", ""),
            ]
        else:
            matrix = [
                ("CDELT1", "-0.0002", ""),
                ("CDELT2", "0.0003", ""),
                ("CROTA2", "30.0", ""),
            ]
        path = tmp_path / f"keywords_{matrix_form}.xisf"
        path.write_bytes(
            _make_xisf(
                width,
                height,
                1,
                "UInt16",
                data.tobytes(),
                fits_keywords=[*common, *matrix],
            )
        )

        unflipped = detect_wcs_from_cards(read_header(path))
        flipped = read_wcs_params(path, 0)
        assert unflipped is not None
        assert flipped is not None
        sky = build_wcs(unflipped).pixel_to_world(31.0, 17.0)
        x, y = build_wcs(flipped).world_to_pixel(sky)

        assert float(x) == pytest.approx(31.0, abs=1e-6)
        assert float(y) == pytest.approx(height - 1 - 17.0, abs=1e-6)

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


class TestPropertyValue:
    def test_inline_value(self):
        from xml.etree.ElementTree import Element

        elem = Element("Property", attrib={"type": "String", "value": "hello"})
        assert _read_property(elem, None).text == "hello"

    def test_empty_returns_empty(self):
        from xml.etree.ElementTree import Element

        elem = Element("Property", attrib={"type": "String"})
        assert _read_property(elem, None).text == ""

    def test_plain_text(self):
        from xml.etree.ElementTree import Element

        elem = Element("Property", attrib={"type": "Int32"})
        elem.text = "42"
        assert _read_property(elem, None).text == "42"

    def test_string_block_and_significant_spaces(self):
        from xml.etree.ElementTree import Element

        plain = Element("Property", attrib={"type": "String"})
        plain.text = "  two spaces  "
        encoded = Element("Property", attrib={"type": "String", "location": "inline:base64"})
        encoded.text = "VGhlIHF1aWNrIGJyb3duIGZveA=="

        assert _read_property(plain, None).text == "  two spaces  "
        assert _read_property(encoded, None).text == "The quick brown fox"

    def test_uint64_vector_remains_exact_and_alias_is_canonical(self):
        from xml.etree.ElementTree import Element

        maximum = 18_446_744_073_709_551_615
        vector = Element(
            "Property",
            attrib={"type": "UI64Vector", "length": "2", "location": "inline:base64"},
        )
        vector.text = base64.b64encode(struct.pack("<2Q", maximum, 0)).decode()
        alias = Element(
            "Property",
            attrib={"type": "Vector", "length": "2", "location": "inline:base64"},
        )
        alias.text = base64.b64encode(struct.pack("<2d", 12.5, -3.25)).decode()

        exact = _read_property(vector, None)
        canonical = _read_property(alias, None)
        assert exact.values == (maximum, 0)
        assert _display_value(exact) == f"{maximum}, 0"
        assert canonical.type == "F64Vector"
        assert canonical.values == (12.5, -3.25)

    def test_attached_matrix_is_not_read_without_source(self):
        from xml.etree.ElementTree import Element

        matrix = Element(
            "Property",
            attrib={
                "type": "F64Matrix",
                "rows": "412",
                "columns": "2",
                "location": "attachment:100:6592",
            },
        )
        value = _read_property(matrix, None)
        assert value.status == "attached"
        assert _display_value(value) == "F64Matrix 412×2 (stored in the file, not shown)"

    def test_compressed_string_checksum_and_failed_vector_are_structured(self):
        from xml.etree.ElementTree import Element

        raw = b"compressed property"
        compressed = zstandard.ZstdCompressor().compress(raw)
        string = Element(
            "Property",
            attrib={
                "type": "String",
                "location": "inline:base64",
                "compression": f"zstd:{len(raw)}",
                "checksum": f"sha256:{hashlib.sha256(compressed).hexdigest()}",
            },
        )
        string.text = base64.b64encode(compressed).decode()
        damaged = Element(
            "Property",
            attrib={
                "type": "F64Vector",
                "length": "3",
                "location": "inline:base64",
            },
        )
        damaged.text = base64.b64encode(struct.pack("<2d", 1.0, 2.0)).decode()

        assert _read_property(string, None).text == "compressed property"
        unavailable = _read_property(damaged, None)
        assert unavailable.status == "unavailable"
        assert "unavailable" in _display_value(unavailable)

    def test_complex_and_unknown_types_display_as_summaries(self):
        from xml.etree.ElementTree import Element

        complex_value = Element(
            "Property",
            attrib={"type": "C64Vector", "length": "2", "location": "inline:base64"},
        )
        complex_value.text = base64.b64encode(bytes(32)).decode()
        unknown = Element("Property", attrib={"type": "FutureType", "value": "ignored"})

        assert _display_value(_read_property(complex_value, None)) == "C64Vector 2"
        assert _display_value(_read_property(unknown, None)) == "FutureType"

    def test_display_contract(self):
        assert _display_value(PropertyValue("ok", None, (12.5, -3.25), (2,), "F64Vector")) == (
            "12.5, -3.25"
        )
        assert _display_value(PropertyValue("ok", None, tuple(range(12)), (12,), "F64Vector")) == (
            "F64Vector 12"
        )
        assert _display_value(PropertyValue("attached", None, None, (412, 2), "F64Matrix")) == (
            "F64Matrix 412×2 (stored in the file, not shown)"
        )
