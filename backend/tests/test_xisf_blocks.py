"""Tests for the shared XISF data-block reader."""

import base64
import hashlib
import io
import zlib
from xml.etree import ElementTree as ET

import lz4.block
import numpy as np
import pytest
import zstandard

from nightcrate.services import xisf_blocks
from nightcrate.services.xisf_blocks import (
    BlockSpec,
    XISFChecksumError,
    XISFError,
    XISFUnavailableError,
    block_spec,
    is_attached,
    read_block,
    unshuffle,
    verify_block,
)

NS = "http://www.pixinsight.com/xisf"


def _spec(
    data: bytes,
    *,
    compression: str | None = None,
    subblocks: str | None = None,
    checksum: str | None = None,
    encoding: str = "base64",
) -> BlockSpec:
    if encoding == "base64":
        text = base64.b64encode(data).decode()
    else:
        text = data.hex()
    return BlockSpec(
        location=f"inline:{encoding}",
        compression=compression,
        subblocks=subblocks,
        checksum=checksum,
        byte_order="little",
        encoded_text=text,
        encoding=encoding,
    )


def _shuffle(data: bytes, item_size: int) -> bytes:
    complete_size = len(data) - len(data) % item_size
    values = np.frombuffer(data, dtype=np.uint8, count=complete_size)
    shuffled = values.reshape(complete_size // item_size, item_size).T.ravel().tobytes()
    return shuffled + data[complete_size:]


def _compress(codec: str, data: bytes, *, write_content_size: bool = True) -> bytes:
    if codec == "zlib":
        return zlib.compress(data)
    if codec in {"lz4", "lz4hc", "lz4-hc"}:
        mode = "high_compression" if codec != "lz4" else "default"
        return lz4.block.compress(data, mode=mode, store_size=False)
    if codec == "zstd":
        return zstandard.ZstdCompressor(write_content_size=write_content_size).compress(data)
    raise AssertionError(codec)


@pytest.mark.parametrize("codec", ["zlib", "lz4", "lz4hc", "zstd"])
@pytest.mark.parametrize("shuffled", [False, True], ids=["plain", "shuffled"])
@pytest.mark.parametrize("with_subblocks", [False, True], ids=["single", "subblocks"])
def test_all_codecs_and_subblock_forms(codec, shuffled, with_subblocks):
    original = (b"\x01\x00\x02\x00" * 768) + b"end!"
    encoded = _shuffle(original, 2) if shuffled else original
    codec_name = f"{codec}+sh" if shuffled else codec
    compression = f"{codec_name}:{len(original)}" + (":2" if shuffled else "")

    if with_subblocks:
        boundaries = (0, 1024, 2048, len(encoded))
        pieces = [encoded[a:b] for a, b in zip(boundaries, boundaries[1:])]
        stored = [_compress(codec, pieces[0]), pieces[1], _compress(codec, pieces[2])]
        payload = b"".join(stored)
        subblocks = ":".join(
            f"{len(chunk)},{len(piece)}" for chunk, piece in zip(stored, pieces, strict=True)
        )
    else:
        payload = _compress(codec, encoded)
        subblocks = None

    assert (
        read_block(
            _spec(payload, compression=compression, subblocks=subblocks),
            None,
            item_size=2,
            expected_size=len(original),
        )
        == original
    )


def test_unshuffle_preserves_trailing_partial_item():
    original = bytes(range(256)) * 16 + b"xyz"
    shuffled = _shuffle(original, 4)

    assert shuffled[-3:] == original[-3:]
    assert unshuffle(shuffled, 4) == original
    assert unshuffle(original, 1) == original


@pytest.mark.parametrize("trailing", [0, 3], ids=["complete-items", "trailing-bytes"])
def test_large_shuffled_round_trip_uses_bytes_like_output(trailing):
    size = 1_000_003 if trailing else 1_000_000
    original = np.random.default_rng(42).integers(0, 256, size=size, dtype=np.uint8).tobytes()
    shuffled = _shuffle(original, 4)
    compressed = zlib.compress(shuffled)

    result = read_block(
        _spec(compressed, compression=f"zlib+sh:{len(original)}:4"),
        None,
        item_size=4,
        expected_size=len(original),
    )

    assert isinstance(result, (bytearray, memoryview))
    assert result == original


@pytest.mark.parametrize(
    ("encoding", "uppercase"),
    [("base64", False), ("hex", False), ("hex", True)],
)
def test_inline_ignores_whitespace(encoding, uppercase):
    data = b"NightCrate XISF block"
    encoded = base64.b64encode(data).decode() if encoding == "base64" else data.hex()
    if uppercase:
        encoded = encoded.upper()
    encoded = f"\n {encoded[:8]} \t{encoded[8:]}\n"
    spec = BlockSpec(
        location=f"inline:{encoding}",
        compression=None,
        subblocks=None,
        checksum=None,
        byte_order="little",
        encoded_text=encoded,
        encoding=encoding,
    )

    assert read_block(spec, None) == data


def test_odd_length_hex_is_invalid():
    spec = _spec(b"", encoding="hex")
    spec = BlockSpec(**{**spec.__dict__, "encoded_text": "abc"})
    with pytest.raises(XISFError):
        read_block(spec, None)


@pytest.mark.parametrize("checksum_on_data", [True, False])
def test_embedded_data_attributes_and_parent_checksum(checksum_on_data):
    original = b"embedded data" * 30
    compressed = zlib.compress(original)
    digest = hashlib.sha256(compressed).hexdigest()
    parent_checksum = "" if checksum_on_data else f' checksum="sha256:{digest}"'
    data_checksum = f' checksum="sha256:{digest}"' if checksum_on_data else ""
    elem = ET.fromstring(
        f'<Image xmlns="{NS}" location="embedded"{parent_checksum}>'
        f'<Data encoding="base64" compression="zlib:{len(original)}"{data_checksum}>'
        f"{base64.b64encode(compressed).decode()}</Data></Image>"
    )

    spec = block_spec(elem)

    assert spec.compression == f"zlib:{len(original)}"
    assert spec.checksum == f"sha256:{digest}"
    assert read_block(spec, None) == original


def test_embedded_subblocks_fall_back_to_parent():
    original = b"parent subblocks" * 40
    compressed = zlib.compress(original)
    elem = ET.fromstring(
        f'<Image xmlns="{NS}" location="embedded" '
        f'subblocks="{len(compressed)},{len(original)}">'
        f'<Data encoding="base64" compression="zlib:{len(original)}">'
        f"{base64.b64encode(compressed).decode()}</Data></Image>"
    )

    assert read_block(block_spec(elem), None) == original


def test_shuffle_item_size_compatibility_fallback():
    original = np.arange(100, dtype=np.uint16).tobytes()
    compressed = zlib.compress(_shuffle(original, 2))
    spec = _spec(compressed, compression=f"zlib+sh:{len(original)}")

    assert verify_block(spec, None) is None
    assert read_block(spec, None, item_size=2) == original


@pytest.mark.parametrize("algorithm", ["sha1", "sha-256", "sha512", "sha3-256", "sha3-512"])
def test_supported_checksums_accept_uppercase_digest(algorithm):
    data = b"checksummed"
    name = (
        algorithm.replace("-", "") if algorithm.startswith("sha-") else algorithm.replace("-", "_")
    )
    digest = hashlib.new(name, data).hexdigest().upper()

    assert read_block(_spec(data, checksum=f"{algorithm}:{digest}"), None) == data


def test_checksum_failure_happens_before_decompression(monkeypatch):
    original = b"compress me" * 100
    compressed = bytearray(zlib.compress(original))
    digest = hashlib.sha256(compressed).hexdigest()
    compressed[-1] ^= 1
    monkeypatch.setattr(
        xisf_blocks,
        "_decompress",
        lambda *args, **kwargs: pytest.fail("decompressor was called"),
    )

    with pytest.raises(XISFChecksumError):
        read_block(
            _spec(
                bytes(compressed),
                compression=f"zlib:{len(original)}",
                checksum=f"sha256:{digest}",
            ),
            None,
        )


def test_unknown_checksum_is_unavailable():
    with pytest.raises(XISFUnavailableError):
        read_block(_spec(b"data", checksum="md5:00"), None)


@pytest.mark.parametrize("codec", ["zlib", "lz4", "lz4hc", "zstd"])
def test_malformed_codec_data_is_normalized(codec):
    with pytest.raises(XISFError):
        read_block(_spec(b"not compressed", compression=f"{codec}:100"), None)


def test_wrong_decompressed_length_and_subblock_totals_are_invalid():
    compressed = zlib.compress(b"abc")
    with pytest.raises(XISFError):
        read_block(_spec(compressed, compression="zlib:4", subblocks=f"{len(compressed)},4"), None)
    with pytest.raises(XISFError):
        read_block(
            _spec(compressed, compression="zlib:3", subblocks=f"{len(compressed) + 1},3"),
            None,
        )
    with pytest.raises(XISFError):
        read_block(_spec(compressed, compression="zlib:4", subblocks=f"{len(compressed)},3"), None)


@pytest.mark.parametrize("codec", ["zlib", "zstd"])
def test_trailing_bytes_are_rejected(codec):
    original = b"stream contents" * 20
    with pytest.raises(XISFError):
        read_block(
            _spec(_compress(codec, original) + b"junk", compression=f"{codec}:{len(original)}"),
            None,
        )


def test_two_zstandard_frames_are_rejected():
    first = b"first" * 100
    second = b"second"
    payload = _compress("zstd", first) + _compress("zstd", second)
    with pytest.raises(XISFError):
        read_block(_spec(payload, compression=f"zstd:{len(first)}"), None)


def test_lz4_trailing_bytes_are_rejected_by_installed_binding():
    original = b"lz4 contents" * 100
    with pytest.raises(XISFError):
        read_block(
            _spec(_compress("lz4", original) + b"junk", compression=f"lz4:{len(original)}"),
            None,
        )


@pytest.mark.parametrize("codec", ["zlib", "lz4", "lz4hc", "zstd"])
def test_no_subblocks_equal_length_is_raw_and_larger_length_is_decompressed(codec):
    raw = b"raw!"
    assert read_block(_spec(raw, compression=f"{codec}:4"), None) == raw

    original = b"x"
    compressed = _compress(codec, original)
    assert len(compressed) > len(original)
    assert read_block(_spec(compressed, compression=f"{codec}:1"), None) == original


def test_zlib_oversized_output_is_bounded(monkeypatch):
    original_factory = zlib.decompressobj
    produced = []

    class RecordingDecompressor:
        def __init__(self):
            self._inner = original_factory()

        def decompress(self, data, max_length=0):
            result = self._inner.decompress(data, max_length)
            produced.append(len(result))
            return result

        def __getattr__(self, name):
            return getattr(self._inner, name)

    monkeypatch.setattr(xisf_blocks.zlib, "decompressobj", RecordingDecompressor)
    with pytest.raises(XISFError):
        read_block(_spec(zlib.compress(b"x" * 65536), compression="zlib:100"), None)
    assert max(produced) <= 101


@pytest.mark.parametrize("write_content_size", [True, False], ids=["known-size", "unknown-size"])
def test_zstandard_oversized_output_is_rejected(write_content_size):
    compressed = _compress("zstd", b"x" * 65536, write_content_size=write_content_size)
    with pytest.raises(XISFError):
        read_block(_spec(compressed, compression="zstd:100"), None)


@pytest.mark.parametrize("codec", ["zlib", "lz4", "zstd"])
def test_impossible_declared_size_is_rejected_before_allocation(codec, monkeypatch):
    declared_size = 500_000_000_000

    def fail_allocation(_size):
        pytest.fail("output allocation was attempted")

    monkeypatch.setattr(xisf_blocks, "bytearray", fail_allocation, raising=False)

    with pytest.raises(XISFError):
        read_block(
            _spec(b"x" * 20, compression=f"{codec}:{declared_size}"),
            None,
            expected_size=declared_size,
        )


def test_read_block_normalizes_memory_error(monkeypatch):
    def fail_allocation(_size):
        raise MemoryError

    monkeypatch.setattr(xisf_blocks, "bytearray", fail_allocation, raising=False)

    with pytest.raises(XISFError):
        read_block(
            _spec(b"ab", compression="zlib:2", subblocks="1,1:1,1"),
            None,
            expected_size=2,
        )


def test_high_ratio_zstandard_block_still_decodes():
    original = bytes(4 * 1024 * 1024)
    compressed = _compress("zstd", original)

    result = read_block(
        _spec(compressed, compression=f"zstd:{len(original)}"),
        None,
        expected_size=len(original),
    )

    assert result == original


def test_malformed_zstandard_huge_claim_uses_only_bounded_reads(monkeypatch):
    declared_size = 10 * 1024 * 1024 * 1024
    payload = b"x" * (160 * 1024)
    read_sizes = []
    allocation_sizes = []
    original_read = xisf_blocks._read_zstd_output
    original_bytearray = bytearray

    def recording_read(reader, size):
        read_sizes.append(size)
        return original_read(reader, size)

    def recording_bytearray(size):
        allocation_sizes.append(size)
        return original_bytearray(size)

    monkeypatch.setattr(xisf_blocks, "_read_zstd_output", recording_read)
    monkeypatch.setattr(xisf_blocks, "bytearray", recording_bytearray, raising=False)

    with pytest.raises(XISFError):
        read_block(
            _spec(payload, compression=f"zstd:{declared_size}"),
            None,
            expected_size=declared_size,
        )

    assert read_sizes
    assert max(read_sizes) <= 4 * 1024 * 1024
    assert allocation_sizes == []


def test_many_tiny_subblocks_reject_aggregate_claim_without_large_allocation(monkeypatch):
    subblock_count = 16_384
    declared_size = subblock_count * 65_536
    allocation_sizes = []
    original_bytearray = bytearray

    def recording_bytearray(size):
        allocation_sizes.append(size)
        return original_bytearray(size)

    monkeypatch.setattr(xisf_blocks, "bytearray", recording_bytearray, raising=False)

    with pytest.raises(XISFError):
        read_block(
            _spec(
                b"x" * subblock_count,
                compression=f"lz4:{declared_size}",
                subblocks=":".join(["1,65536"] * subblock_count),
            ),
            None,
            expected_size=declared_size,
        )

    assert allocation_sizes == []


class RecordingBytesIO(io.BytesIO):
    def __init__(self, value):
        super().__init__(value)
        self.read_offsets = []

    def read(self, size=-1):
        self.read_offsets.append((self.tell(), size))
        return super().read(size)


def test_expected_size_mismatch_precedes_attachment_read():
    source = RecordingBytesIO(b"0123456789")
    spec = BlockSpec("attachment:2:4", None, None, None, "little", None, None)
    with pytest.raises(XISFError):
        read_block(spec, source, expected_size=5)
    assert source.read_offsets == []


@pytest.mark.parametrize(
    ("location", "compression", "subblocks"),
    [
        ("attachment:-1:4", None, None),
        ("attachment:x:4", None, None),
        ("inline:base64", "zlib:-1", None),
        ("inline:base64", "zlib:x", None),
        ("inline:base64", "zlib:4", "-1,4"),
        ("inline:base64", "zlib:4", "x,4"),
    ],
)
def test_invalid_sizes_are_normalized(location, compression, subblocks):
    spec = BlockSpec(location, compression, subblocks, None, "little", "", "base64")
    with pytest.raises(XISFError):
        read_block(spec, io.BytesIO(b"data"))


def test_verify_block_checks_checksum_without_decompressing(monkeypatch):
    original = b"verified" * 100
    compressed = zlib.compress(original)
    good = _spec(
        compressed,
        compression=f"zlib:{len(original)}",
        checksum=f"sha256:{hashlib.sha256(compressed).hexdigest()}",
    )
    monkeypatch.setattr(
        xisf_blocks,
        "_decompress",
        lambda *args, **kwargs: pytest.fail("decompressor was called"),
    )

    assert verify_block(good, None) is None
    damaged = BlockSpec(**{**good.__dict__, "checksum": f"sha256:{'0' * 64}"})
    with pytest.raises(XISFChecksumError):
        verify_block(damaged, None)


def test_attachment_must_lie_within_source():
    spec = BlockSpec("attachment:2:10", None, None, None, "little", None, None)
    with pytest.raises(XISFError):
        read_block(spec, io.BytesIO(b"short"))


@pytest.mark.parametrize("location", ["url(file:///x.xisb)", "path(@header_dir/x)"])
def test_external_locations_are_unavailable(location):
    spec = BlockSpec(location, None, None, None, "little", None, None)
    with pytest.raises(XISFUnavailableError):
        read_block(spec, None)


def test_unknown_codec_is_unavailable_and_error_is_value_error():
    with pytest.raises(XISFUnavailableError):
        read_block(_spec(b"data", compression="brotli:100"), None)
    assert issubclass(XISFError, ValueError)
    assert is_attached(BlockSpec("attachment:0:0", None, None, None, "little", None, None))
