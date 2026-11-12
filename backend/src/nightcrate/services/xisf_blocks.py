"""Read XISF data blocks from inline, embedded, or attached storage."""

import base64
import binascii
import hashlib
import hmac
import io
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal, cast
from xml.etree.ElementTree import Element  # nosec B405 - parsed by the caller with defusedxml

import lz4.block
import numpy as np
import zstandard

XISF_NS = "http://www.pixinsight.com/xisf"
BlockData = bytes | bytearray | memoryview

# DEFLATE's maximum expansion is 1,032 output bytes per compressed byte.
ZLIB_MAX_EXPANSION_RATIO = 1_032
# An LZ4 sequence can expand to at most 255 output bytes per compressed byte.
LZ4_MAX_EXPANSION_RATIO = 255
# Keep Zstandard's broad window bounded without rejecting valid sparse image data.
ZSTD_MAX_EXPANSION_RATIO = 65_536
# Tiny compressed pieces need room for framing that dominates their payload size.
DECOMPRESSION_SIZE_ALLOWANCE = 64 * 1024
# Unshaped values such as String properties may not claim unbounded output.
MAX_UNBOUNDED_BLOCK_SIZE = 256 * 1024 * 1024
# Zstandard output is consumed in bounded pieces regardless of declared size.
ZSTD_READ_CHUNK_SIZE = 4 * 1024 * 1024

CHECKSUM_MISMATCH_MESSAGE = (
    "This XISF file is damaged. Its contents don't match the check saved with it. "
    "Re-save it from PixInsight or restore a backup."
)
INVALID_BLOCK_MESSAGE = "This XISF file contains invalid stored data."
INVALID_COMPRESSED_BLOCK_MESSAGE = "This XISF file contains invalid compressed data."
UNSUPPORTED_CODEC_MESSAGE = "This XISF file uses unsupported compression: {codec}."
UNSUPPORTED_LOCATION_MESSAGE = "This XISF file stores data in an unsupported place: {location}."
UNSUPPORTED_CHECKSUM_MESSAGE = "This XISF file uses an unsupported check: {algorithm}."
UNSUPPORTED_BYTE_ORDER_MESSAGE = (
    "This XISF file stores numbers in an unsupported order: {byte_order}."
)
UNSUPPORTED_BLOCK_SIZE_MESSAGE = "This XISF file contains a stored value larger than 256 MiB."


class XISFError(ValueError):
    """Raised when an XISF file cannot be parsed."""


class XISFChecksumError(XISFError):
    """Raised when an XISF data-block checksum does not match."""


class XISFUnavailableError(XISFError):
    """Raised when an XISF data block uses an unsupported feature."""


@dataclass(frozen=True)
class BlockSpec:
    """Attributes needed to locate and decode one XISF data block."""

    location: str
    compression: str | None
    subblocks: str | None
    checksum: str | None
    byte_order: Literal["little", "big"]
    encoded_text: str | None
    encoding: Literal["base64", "hex"] | None


@dataclass(frozen=True)
class _CompressionSpec:
    codec: str
    uncompressed_size: int
    item_size: int | None
    shuffled: bool


def _tag(local: str) -> str:
    return f"{{{XISF_NS}}}{local}"


def _direct_child(elem: Element, local: str) -> Element | None:
    tag = _tag(local)
    return next((child for child in elem if child.tag == tag), None)


def block_spec(elem: Element) -> BlockSpec:
    """Build a block description from an XISF element."""
    location = elem.get("location", "")
    byte_order_value = elem.get("byteOrder", "little")
    if byte_order_value not in {"little", "big"}:
        raise XISFUnavailableError(
            UNSUPPORTED_BYTE_ORDER_MESSAGE.format(byte_order=byte_order_value or "(missing)")
        )
    byte_order = cast(Literal["little", "big"], byte_order_value)

    compression = elem.get("compression")
    subblocks = elem.get("subblocks")
    checksum = elem.get("checksum")
    encoded_text: str | None = None
    encoding_value: str | None = None

    if location == "embedded":
        data = _direct_child(elem, "Data")
        if data is None:
            raise XISFError(INVALID_BLOCK_MESSAGE)
        encoding_value = data.get("encoding")
        compression = data.get("compression")
        # Compatibility extension: accept these attributes on the parent when
        # an embedded Data element does not provide them.
        subblocks = data.get("subblocks") or subblocks
        checksum = data.get("checksum") or checksum
        encoded_text = data.text or ""
    elif location.startswith("inline:"):
        encoding_value = location.partition(":")[2]
        encoded_text = elem.text or ""

    encoding = cast(Literal["base64", "hex"] | None, encoding_value)
    return BlockSpec(
        location=location,
        compression=compression,
        subblocks=subblocks,
        checksum=checksum,
        byte_order=byte_order,
        encoded_text=encoded_text,
        encoding=encoding,
    )


def is_attached(spec: BlockSpec) -> bool:
    """Return whether a block uses attached storage."""
    return spec.location.startswith("attachment:")


def _nonnegative_int(value: str, *, compressed: bool = False) -> int:
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError) as exc:
        message = INVALID_COMPRESSED_BLOCK_MESSAGE if compressed else INVALID_BLOCK_MESSAGE
        raise XISFError(message) from exc
    if parsed < 0:
        message = INVALID_COMPRESSED_BLOCK_MESSAGE if compressed else INVALID_BLOCK_MESSAGE
        raise XISFError(message)
    return parsed


def _attachment_parts(location: str) -> tuple[int, int]:
    parts = location.split(":")
    if len(parts) != 3 or parts[0] != "attachment":
        raise XISFError(INVALID_BLOCK_MESSAGE)
    return _nonnegative_int(parts[1]), _nonnegative_int(parts[2])


def _parse_compression(
    compression: str | None, fallback_item_size: int | None
) -> _CompressionSpec | None:
    if compression is None:
        return None

    parts = compression.split(":")
    if len(parts) not in {2, 3}:
        raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)

    codec_value = parts[0]
    shuffled = codec_value.endswith("+sh")
    codec = codec_value.removesuffix("+sh")
    if codec == "lz4-hc":
        codec = "lz4hc"
    if codec not in {"zlib", "lz4", "lz4hc", "zstd"}:
        raise XISFUnavailableError(
            UNSUPPORTED_CODEC_MESSAGE.format(codec=codec_value or "(missing)")
        )

    uncompressed_size = _nonnegative_int(parts[1], compressed=True)
    shuffle_item_size: int | None = None
    if len(parts) == 3:
        shuffle_item_size = _nonnegative_int(parts[2], compressed=True)
        if shuffle_item_size == 0:
            raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
    elif shuffled:
        # Compatibility extension: older writers omitted the shuffle item size.
        if fallback_item_size is not None and fallback_item_size <= 0:
            raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
        shuffle_item_size = fallback_item_size

    return _CompressionSpec(codec, uncompressed_size, shuffle_item_size, shuffled)


def _parse_subblocks(value: str | None) -> list[tuple[int, int]] | None:
    if value is None:
        return None
    if not value:
        raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)

    result: list[tuple[int, int]] = []
    for part in value.split(":"):
        lengths = part.split(",")
        if len(lengths) != 2:
            raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
        result.append(
            (
                _nonnegative_int(lengths[0], compressed=True),
                _nonnegative_int(lengths[1], compressed=True),
            )
        )
    return result


def _validate_declared_sizes(
    spec: BlockSpec,
    compression: _CompressionSpec | None,
    subblocks: list[tuple[int, int]] | None,
    expected_size: int | None,
) -> None:
    if expected_size is not None and expected_size < 0:
        raise XISFError(INVALID_BLOCK_MESSAGE)
    if subblocks is not None and compression is None:
        raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
    if compression is not None:
        if expected_size is not None and compression.uncompressed_size != expected_size:
            raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
        if subblocks is not None and sum(u for _, u in subblocks) != compression.uncompressed_size:
            raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
    elif expected_size is not None and is_attached(spec):
        _, stored_size = _attachment_parts(spec.location)
        if stored_size != expected_size:
            raise XISFError(INVALID_BLOCK_MESSAGE)


def _decode_text(spec: BlockSpec, max_decoded_size: int | None = None) -> bytes:
    text = "".join((spec.encoded_text or "").split())
    try:
        if spec.encoding == "base64":
            padding = len(text) - len(text.rstrip("="))
            decoded_size = len(text) * 3 // 4 - min(padding, 2)
            if max_decoded_size is not None and decoded_size > max_decoded_size:
                raise XISFUnavailableError(UNSUPPORTED_BLOCK_SIZE_MESSAGE)
            return base64.b64decode(text, validate=True)
        if spec.encoding == "hex":
            if len(text) % 2:
                raise XISFError(INVALID_BLOCK_MESSAGE)
            if max_decoded_size is not None and len(text) // 2 > max_decoded_size:
                raise XISFUnavailableError(UNSUPPORTED_BLOCK_SIZE_MESSAGE)
            return bytes.fromhex(text)
    except XISFError:
        raise
    except (binascii.Error, ValueError) as exc:
        raise XISFError(INVALID_BLOCK_MESSAGE) from exc
    raise XISFUnavailableError(
        UNSUPPORTED_LOCATION_MESSAGE.format(
            location=f"encoded data ({spec.encoding or 'missing encoding'})"
        )
    )


def _read_attachment(spec: BlockSpec, source: Path | BinaryIO | None) -> bytes:
    if source is None:
        raise XISFError(INVALID_BLOCK_MESSAGE)
    position, size = _attachment_parts(spec.location)

    owns_file = isinstance(source, Path)
    try:
        if owns_file:
            path = cast(Path, source)
            file_size = path.stat().st_size
            stream: BinaryIO = path.open("rb")
        else:
            stream = cast(BinaryIO, source)
            stream.seek(0, io.SEEK_END)
            file_size = stream.tell()

        if position > file_size or size > file_size - position:
            raise XISFError(INVALID_BLOCK_MESSAGE)
        stream.seek(position)
        data = stream.read(size)
        if len(data) != size:
            raise XISFError(INVALID_BLOCK_MESSAGE)
        return data
    except XISFError:
        raise
    except (OSError, ValueError) as exc:
        raise XISFError(INVALID_BLOCK_MESSAGE) from exc
    finally:
        if owns_file and "stream" in locals():
            stream.close()


def _stored_bytes(
    spec: BlockSpec,
    source: Path | BinaryIO | None,
    max_decoded_size: int | None = None,
) -> bytes:
    if is_attached(spec):
        return _read_attachment(spec, source)
    if spec.location == "embedded" or spec.location.startswith("inline:"):
        return _decode_text(spec, max_decoded_size)
    raise XISFUnavailableError(
        UNSUPPORTED_LOCATION_MESSAGE.format(location=spec.location or "(missing)")
    )


def _verify_checksum(checksum: str | None, data: bytes) -> None:
    if checksum is None:
        return
    algorithm, separator, digest = checksum.partition(":")
    if not separator or not digest:
        raise XISFError(INVALID_BLOCK_MESSAGE)
    algorithms = {
        "sha-1": "sha1",
        "sha1": "sha1",
        "sha-256": "sha256",
        "sha256": "sha256",
        "sha-512": "sha512",
        "sha512": "sha512",
        "sha3-256": "sha3_256",
        "sha3-512": "sha3_512",
    }
    name = algorithms.get(algorithm.lower())
    if name is None:
        raise XISFUnavailableError(UNSUPPORTED_CHECKSUM_MESSAGE.format(algorithm=algorithm))
    actual = hashlib.new(name, data).hexdigest()
    if not hmac.compare_digest(actual.lower(), digest.lower()):
        raise XISFChecksumError(CHECKSUM_MISMATCH_MESSAGE)


def _validate_stored_size(
    raw: bytes,
    compression: _CompressionSpec | None,
    subblocks: list[tuple[int, int]] | None,
    expected_size: int | None,
) -> None:
    if compression is None:
        if expected_size is not None and len(raw) != expected_size:
            raise XISFError(INVALID_BLOCK_MESSAGE)
        return
    if subblocks is not None and sum(c for c, _ in subblocks) != len(raw):
        raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)


def _validate_unbounded_size(spec: BlockSpec, compression: _CompressionSpec | None) -> None:
    if compression is not None:
        declared_size = compression.uncompressed_size
    elif is_attached(spec):
        _, declared_size = _attachment_parts(spec.location)
    else:
        return
    if declared_size > MAX_UNBOUNDED_BLOCK_SIZE:
        raise XISFUnavailableError(UNSUPPORTED_BLOCK_SIZE_MESSAGE)


def _validate_expansion_ratios(
    raw: bytes,
    compression: _CompressionSpec,
    subblocks: list[tuple[int, int]] | None,
) -> None:
    ratio = {
        "zlib": ZLIB_MAX_EXPANSION_RATIO,
        "lz4": LZ4_MAX_EXPANSION_RATIO,
        "lz4hc": LZ4_MAX_EXPANSION_RATIO,
        "zstd": ZSTD_MAX_EXPANSION_RATIO,
    }[compression.codec]
    pieces = subblocks or [(len(raw), compression.uncompressed_size)]
    total_compressed = sum(compressed for compressed, _ in pieces)
    total_uncompressed = sum(uncompressed for _, uncompressed in pieces)
    if (
        total_compressed != total_uncompressed
        and total_uncompressed > total_compressed * ratio + DECOMPRESSION_SIZE_ALLOWANCE
    ):
        raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
    for compressed_size, uncompressed_size in pieces:
        if compressed_size == uncompressed_size:
            continue
        maximum = compressed_size * ratio + DECOMPRESSION_SIZE_ALLOWANCE
        if uncompressed_size > maximum:
            raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)


def _decompress_zlib(chunk: bytes, uncompressed_size: int) -> bytes:
    decompressor = zlib.decompressobj()
    data = decompressor.decompress(chunk, uncompressed_size + 1)
    if (
        len(data) != uncompressed_size
        or not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
    ):
        raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
    return data


def _read_zstd_output(reader, size: int) -> bytes:
    return reader.read(size)


def _decompress_zstd(
    chunk: bytes | memoryview,
    uncompressed_size: int,
    decompressor: zstandard.ZstdDecompressor,
) -> bytes:
    source = io.BytesIO(chunk)
    output: list[bytes] = []
    total = 0
    with decompressor.stream_reader(source, read_across_frames=False, closefd=False) as reader:
        while True:
            piece = _read_zstd_output(reader, ZSTD_READ_CHUNK_SIZE)
            if not piece:
                break
            total += len(piece)
            if total > uncompressed_size:
                raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
            output.append(piece)
    if total != uncompressed_size or source.tell() != len(chunk):
        raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
    return output[0] if len(output) == 1 else b"".join(output)


def _decompress_chunk(
    chunk: bytes | memoryview,
    codec: str,
    uncompressed_size: int,
    zstd_decompressor: zstandard.ZstdDecompressor,
) -> bytes:
    try:
        if codec == "zlib":
            return _decompress_zlib(chunk, uncompressed_size)
        if codec in {"lz4", "lz4hc"}:
            data = lz4.block.decompress(chunk, uncompressed_size=uncompressed_size)
            if len(data) != uncompressed_size:
                raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
            return data
        if codec == "zstd":
            return _decompress_zstd(chunk, uncompressed_size, zstd_decompressor)
    except XISFError:
        raise
    except Exception as exc:  # codec libraries expose implementation-specific errors
        raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE) from exc
    raise XISFUnavailableError(UNSUPPORTED_CODEC_MESSAGE.format(codec=codec))


def _decompress(
    raw: bytes,
    compression: _CompressionSpec,
    subblocks: list[tuple[int, int]] | None,
) -> BlockData:
    pieces = subblocks or [(len(raw), compression.uncompressed_size)]
    _validate_expansion_ratios(raw, compression, subblocks)
    raw_view = memoryview(raw)
    decoded_pieces: list[BlockData] = []
    input_offset = 0
    zstd_decompressor = zstandard.ZstdDecompressor()

    for compressed_size, uncompressed_size in pieces:
        chunk = raw_view[input_offset : input_offset + compressed_size]
        input_offset += compressed_size
        if compressed_size == uncompressed_size:
            decoded = chunk
        else:
            decoded = _decompress_chunk(
                chunk, compression.codec, uncompressed_size, zstd_decompressor
            )
        if len(decoded) != uncompressed_size:
            raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
        decoded_pieces.append(decoded)

    decoded_size = sum(len(piece) for piece in decoded_pieces)
    if input_offset != len(raw) or decoded_size != compression.uncompressed_size:
        raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
    if len(decoded_pieces) == 1:
        return decoded_pieces[0]

    output = bytearray(decoded_size)
    output_view = memoryview(output)
    output_offset = 0
    for piece in decoded_pieces:
        piece_size = len(piece)
        output_view[output_offset : output_offset + piece_size] = piece
        output_offset += piece_size
    return output


def unshuffle(data: BlockData, item_size: int) -> memoryview:
    """Reverse XISF byte shuffling, preserving a trailing partial item."""
    if item_size <= 0:
        raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
    if item_size == 1 or not data:
        return memoryview(data)
    source = np.frombuffer(data, dtype=np.uint8)
    output = np.empty(len(source), dtype=np.uint8)

    complete_size = len(source) - len(source) % item_size
    item_count = complete_size // item_size
    output[:complete_size].reshape(item_count, item_size)[:] = (
        source[:complete_size].reshape(item_size, item_count).T
    )
    output[complete_size:] = source[complete_size:]
    return memoryview(output)


def verify_block(spec: BlockSpec, source: Path | BinaryIO | None) -> None:
    """Verify a block's location, codec, stored size, and checksum."""
    compression = _parse_compression(spec.compression, None)
    subblocks = _parse_subblocks(spec.subblocks)
    _validate_declared_sizes(spec, compression, subblocks, None)
    raw = _stored_bytes(spec, source)
    _validate_stored_size(raw, compression, subblocks, None)
    _verify_checksum(spec.checksum, raw)


def read_block(
    spec: BlockSpec,
    source: Path | BinaryIO | None,
    *,
    item_size: int | None = None,
    expected_size: int | None = None,
) -> BlockData:
    """Read, verify, decompress, and unshuffle one XISF data block."""
    try:
        compression = _parse_compression(spec.compression, item_size)
        subblocks = _parse_subblocks(spec.subblocks)
        _validate_declared_sizes(spec, compression, subblocks, expected_size)
        if expected_size is None:
            _validate_unbounded_size(spec, compression)
        if compression is not None and compression.shuffled and compression.item_size is None:
            raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)

        max_decoded_size = MAX_UNBOUNDED_BLOCK_SIZE if expected_size is None else None
        raw = _stored_bytes(spec, source, max_decoded_size)
        if expected_size is None and len(raw) > MAX_UNBOUNDED_BLOCK_SIZE:
            raise XISFUnavailableError(UNSUPPORTED_BLOCK_SIZE_MESSAGE)
        _validate_stored_size(raw, compression, subblocks, expected_size)
        _verify_checksum(spec.checksum, raw)

        if compression is None:
            return raw
        data = _decompress(raw, compression, subblocks)
        if compression.shuffled:
            if compression.item_size is None:
                raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
            data = unshuffle(data, compression.item_size)
        return data
    except XISFError:
        raise
    except (MemoryError, OverflowError) as exc:
        raise XISFError(INVALID_BLOCK_MESSAGE) from exc
