"""XISF file I/O — clean-room parser for PixInsight's native format.

Based on the open XISF 1.0 specification. No dependency on the GPL xisf package.
Supports: UInt16/Float32, Gray/RGB, uncompressed/zlib/lz4/lz4-hc/zstd (±shuffle).
"""

import base64
import struct
import zlib
from pathlib import Path
from xml.etree.ElementTree import Element  # nosec B405 — type only, parsing via defusedxml

import defusedxml.ElementTree as ET
import lz4.block
import numpy as np
import zstandard

from nightcrate.services.fits_header_map import get_keyword_description
from nightcrate.services.imaging import normalize_to_01, reshape_color

XISF_MAGIC = b"XISF0100"
XISF_NS = "http://www.pixinsight.com/xisf"

# Map XISF sampleFormat to numpy dtype and normalization divisor
SAMPLE_FORMATS: dict[str, np.dtype] = {
    "UInt8": np.dtype(np.uint8),
    "UInt16": np.dtype(np.uint16),
    "UInt32": np.dtype(np.uint32),
    "Float32": np.dtype(np.float32),
    "Float64": np.dtype(np.float64),
}


class XISFError(Exception):
    """Raised when an XISF file cannot be parsed."""


def _tag(local: str) -> str:
    """Return a namespace-qualified tag name."""
    return f"{{{XISF_NS}}}{local}"


def _byte_unshuffle(data: bytes, item_size: int) -> bytes:
    """Reverse XISF byte shuffling using numpy."""
    arr = np.frombuffer(data, dtype=np.uint8)
    n = len(arr)
    if n % item_size != 0:
        raise XISFError(f"Byte unshuffle: data length {n} not divisible by item size {item_size}")
    group_size = n // item_size
    return arr.reshape(item_size, group_size).T.ravel().tobytes()


def _decompress_blocks(raw: bytes, codec: str, uncompressed_size: int, item_size: int) -> bytes:
    """Read sub-blocks from raw data, decompress, and optionally unshuffle."""
    # Determine if byte-shuffling is needed
    shuffle = "+sh" in codec
    base_codec = codec.replace("+sh", "").replace("+sc", "")

    result = bytearray()
    offset = 0

    while len(result) < uncompressed_size:
        if offset + 16 > len(raw):
            raise XISFError("Unexpected end of compressed data (sub-block header truncated)")
        comp_size, uncomp_size = struct.unpack_from("<QQ", raw, offset)
        offset += 16

        if offset + comp_size > len(raw):
            raise XISFError("Unexpected end of compressed data (sub-block data truncated)")
        chunk = raw[offset : offset + comp_size]
        offset += comp_size

        if comp_size == uncomp_size:
            # Stored uncompressed
            result.extend(chunk)
        elif base_codec == "zlib":
            result.extend(zlib.decompress(chunk))
        elif base_codec in ("lz4", "lz4-hc"):
            result.extend(lz4.block.decompress(chunk, uncompressed_size=uncomp_size))
        elif base_codec == "zstd":
            dctx = zstandard.ZstdDecompressor()
            result.extend(dctx.decompress(chunk))
        else:
            raise XISFError(f"Unsupported compression codec: {codec}")

    data = bytes(result[:uncompressed_size])

    if shuffle:
        data = _byte_unshuffle(data, item_size)

    return data


def _parse_xml_header(file_path: Path) -> tuple[Element, int]:
    """Read and parse the XISF XML header. Returns (root_element, header_end_offset)."""
    with open(file_path, "rb") as f:
        magic = f.read(8)
        if magic != XISF_MAGIC:
            raise XISFError(f"Not an XISF file (bad magic: {magic!r})")

        header_len_bytes = f.read(4)
        _reserved = f.read(4)
        header_len = struct.unpack("<I", header_len_bytes)[0]

        xml_bytes = f.read(header_len)

    # Strip null padding
    xml_text = xml_bytes.decode("utf-8").rstrip("\x00")
    root = ET.fromstring(xml_text)
    return root, 16 + header_len


def _find_primary_image(root: Element) -> Element:
    """Find the first (primary) Image element."""
    for img in root.iter(_tag("Image")):
        return img
    raise XISFError("No <Image> element found in XISF header")


def load_image_data(file_path: Path, hdu: int = 0) -> np.ndarray:
    """Load image data as float64 array normalized to [0, 1].

    Returns shape (H, W) for Gray or (3, H, W) for RGB.
    The hdu parameter selects among multiple Image elements (0-indexed).
    """
    root, _ = _parse_xml_header(file_path)

    images = list(root.iter(_tag("Image")))
    if hdu < 0 or hdu >= len(images):
        raise ValueError(f"Image index {hdu} out of range (file has {len(images)} images)")
    img_elem = images[hdu]

    # Parse geometry: "W:H:C"
    geom_str = img_elem.get("geometry", "")
    geom_parts = geom_str.split(":")
    if len(geom_parts) < 2:
        raise XISFError(f"Invalid geometry: {geom_str}")
    width, height = int(geom_parts[0]), int(geom_parts[1])
    channels = int(geom_parts[2]) if len(geom_parts) > 2 else 1

    # Sample format
    fmt = img_elem.get("sampleFormat", "")
    if fmt not in SAMPLE_FORMATS:
        raise XISFError(f"Unsupported sampleFormat: {fmt}")
    dtype = SAMPLE_FORMATS[fmt]
    item_size = dtype.itemsize

    # Location
    location = img_elem.get("location", "")
    if not location.startswith("attachment:"):
        raise XISFError(f"Unsupported location type: {location}")
    loc_parts = location.split(":")
    data_offset = int(loc_parts[1])
    data_size = int(loc_parts[2])

    # Compression (optional)
    compression = img_elem.get("compression", "")

    # Read raw data from file
    with open(file_path, "rb") as f:
        f.seek(data_offset)
        raw = f.read(data_size)

    if len(raw) != data_size:
        raise XISFError(f"Expected {data_size} bytes at offset {data_offset}, got {len(raw)}")

    # Decompress if needed
    if compression:
        parts = compression.split(":")
        codec = parts[0]
        uncompressed_size = (
            int(parts[1]) if len(parts) > 1 else width * height * channels * item_size
        )
        pixel_bytes = _decompress_blocks(raw, codec, uncompressed_size, item_size)
    else:
        pixel_bytes = raw

    # Convert to numpy array
    arr = np.frombuffer(pixel_bytes, dtype=dtype)

    if channels == 1:
        arr = arr.reshape(height, width)
    else:
        # XISF uses planar layout: RRR...GGG...BBB
        arr = arr.reshape(channels, height, width)

    # Normalize to [0, 1]
    normalized = normalize_to_01(arr)
    return reshape_color(normalized)


def _extract_property_value(prop: Element) -> str:
    """Extract the scalar value from an XISF <Property> element.

    Handles both inline attributes and base64-encoded text content.
    """
    value = prop.get("value", "")
    if value:
        return value
    if not prop.text:
        return ""
    prop_type = prop.get("type", "")
    if prop_type == "String":
        try:
            return base64.b64decode(prop.text).decode("utf-8")
        except Exception:
            return prop.text
    return prop.text


def read_header(file_path: Path, hdu: int = 0) -> list[dict]:
    """Read metadata as {key, value, comment} dicts.

    First extracts <FITSKeyword> elements (same format as FITS headers).
    Then extracts <Property> elements with scalar values, mapping XISF property IDs
    to equivalent FITS-style keywords for display.
    """
    root, _ = _parse_xml_header(file_path)

    images = list(root.iter(_tag("Image")))
    if hdu < 0 or hdu >= len(images):
        raise ValueError(f"Image index {hdu} out of range (file has {len(images)} images)")
    img_elem = images[hdu]

    cards: list[dict] = []

    # FITS keywords (preferred — most XISF files from PixInsight include these)
    for kw in img_elem.iter(_tag("FITSKeyword")):
        name = kw.get("name", "")
        cards.append(
            {
                "key": name,
                "value": kw.get("value", ""),
                "comment": kw.get("comment", ""),
                "description": get_keyword_description(name),
            }
        )

    # XISF properties (supplement with mapped names if not already in FITS keywords)
    existing_keys = {c["key"] for c in cards}
    prop_map = {
        "Instrument:Camera:Name": "INSTRUME",
        "Instrument:Filter:Name": "FILTER",
        "Instrument:ExposureTime": "EXPTIME",
        "Instrument:Sensor:Temperature": "CCD-TEMP",
        "Instrument:Telescope:Name": "TELESCOP",
        "Observation:Object:Name": "OBJECT",
        "Observation:Time:Start": "DATE-OBS",
        "Observation:Object:RA": "RA",
        "Observation:Object:Dec": "DEC",
    }

    for prop in img_elem.iter(_tag("Property")):
        prop_id = prop.get("id", "")
        value = _extract_property_value(prop)
        if not value:
            continue

        mapped_key = prop_map.get(prop_id)
        if mapped_key and mapped_key not in existing_keys:
            cards.append(
                {
                    "key": mapped_key,
                    "value": str(value),
                    "comment": f"XISF: {prop_id}",
                    "description": get_keyword_description(mapped_key),
                }
            )
            existing_keys.add(mapped_key)
        elif not mapped_key:
            cards.append(
                {
                    "key": prop_id,
                    "value": str(value),
                    "comment": "",
                    "description": get_keyword_description(prop_id),
                }
            )

    return cards


def list_extensions(file_path: Path) -> list[dict]:
    """List all Image elements in the XISF file."""
    root, _ = _parse_xml_header(file_path)

    result = []
    for i, img in enumerate(root.iter(_tag("Image"))):
        geom = img.get("geometry", "?")
        fmt = img.get("sampleFormat", "?")
        color_space = img.get("colorSpace", "?")
        img_id = img.get("id", f"Image {i}")

        result.append(
            {
                "index": i,
                "name": img_id,
                "type": f"{fmt} {color_space} ({geom})",
                "has_image": True,
            }
        )

    return result
