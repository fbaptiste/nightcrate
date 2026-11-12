"""XISF file I/O — clean-room parser for PixInsight's native format.

Based on the open XISF 1.0 specification. No dependency on the GPL xisf package.
Supports: UInt16/Float32, Gray/RGB, uncompressed/zlib/lz4/lz4-hc/zstd (±shuffle).
"""

import logging
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal
from xml.etree.ElementTree import Element  # nosec B405 — type only, parsing via defusedxml

import defusedxml.ElementTree as ET
import numpy as np
from defusedxml.common import DefusedXmlException

from nightcrate.services.fits_header_map import get_keyword_description
from nightcrate.services.image_annotation_models import FileSolution, WcsParams
from nightcrate.services.image_annotations import detect_wcs_from_cards, flip_wcs_rows
from nightcrate.services.imaging import normalize_to_01, reshape_color
from nightcrate.services.xisf_blocks import (
    INVALID_BLOCK_MESSAGE,
    INVALID_COMPRESSED_BLOCK_MESSAGE,
    XISFChecksumError,
    XISFError,
    XISFUnavailableError,
    _attachment_parts,
    _parse_compression,
    _parse_subblocks,
    _validate_declared_sizes,
    block_spec,
    is_attached,
    read_block,
    verify_block,
)

__all__ = ["XISFChecksumError", "XISFError", "XISFUnavailableError"]

logger = logging.getLogger("nightcrate")

XISF_MAGIC = b"XISF0100"
XISF_NS = "http://www.pixinsight.com/xisf"

INVALID_HEADER_MESSAGE = "This XISF file has an invalid header."
BAD_SIGNATURE_MESSAGE = "This file is not a valid XISF file."
INVALID_GEOMETRY_MESSAGE = "This XISF image has invalid geometry: {geometry}."
UNSUPPORTED_GEOMETRY_MESSAGE = (
    "This XISF file uses an unsupported image shape; only two-dimensional images are supported."
)
INVALID_BOUNDS_MESSAGE = "This XISF image has invalid sample bounds: {bounds}."
IMAGE_INDEX_MESSAGE = "Image {index} is out of range; this file has {count} images."
UNSUPPORTED_SAMPLE_FORMAT_MESSAGE = "This XISF file uses an unsupported sample format: {format}."
UNSUPPORTED_PIXEL_STORAGE_MESSAGE = (
    "This XISF file uses an unsupported pixel layout: {pixel_storage}."
)
UNSUPPORTED_COLOR_SPACE_MESSAGE = "This XISF file uses an unsupported color space: {color_space}."
UNSUPPORTED_SOLUTION_VERSION_MESSAGE = (
    "This XISF file uses unsupported plate solution version {version}. "
    "Solve the image in NightCrate instead."
)
UNSUPPORTED_SOLUTION_PROJECTION_MESSAGE = (
    "This XISF file uses the {projection} projection for its plate solution. "
    "NightCrate supports only gnomonic solutions; solve the image in NightCrate instead."
)
ROTATED_SOLUTION_MESSAGE = (
    "This XISF file uses an unsupported coordinate layout for its plate solution. "
    "Solve the image in NightCrate instead."
)
MALFORMED_SOLUTION_MESSAGE = (
    "This XISF file has an incomplete or malformed plate solution. "
    "Solve the image in NightCrate instead."
)

# Map XISF sampleFormat to numpy dtype and normalization divisor
SAMPLE_FORMATS: dict[str, np.dtype] = {
    "UInt8": np.dtype(np.uint8),
    "UInt16": np.dtype(np.uint16),
    "UInt32": np.dtype(np.uint32),
    "Float32": np.dtype(np.float32),
    "Float64": np.dtype(np.float64),
}

# XISF 1.0 §8.4.4.1–§8.4.4.6 alternate property type names.
_CANONICAL_TYPES = {
    "Byte": "UInt8",
    "Short": "Int16",
    "UShort": "UInt16",
    "Int": "Int32",
    "UInt": "UInt32",
    "Float": "Float32",
    "Double": "Float64",
    "Quad": "Float128",
    "Complex": "Complex64",
    "ByteArray": "UI8Vector",
    "IVector": "I32Vector",
    "UIVector": "UI32Vector",
    "Vector": "F64Vector",
    "ByteMatrix": "UI8Matrix",
    "IMatrix": "I32Matrix",
    "UIMatrix": "UI32Matrix",
    "Matrix": "F64Matrix",
}

_NUMERIC_DTYPES: dict[str, np.dtype] = {
    "I8Vector": np.dtype(np.int8),
    "UI8Vector": np.dtype(np.uint8),
    "I16Vector": np.dtype(np.int16),
    "UI16Vector": np.dtype(np.uint16),
    "I32Vector": np.dtype(np.int32),
    "UI32Vector": np.dtype(np.uint32),
    "I64Vector": np.dtype(np.int64),
    "UI64Vector": np.dtype(np.uint64),
    "F32Vector": np.dtype(np.float32),
    "F64Vector": np.dtype(np.float64),
    "I8Matrix": np.dtype(np.int8),
    "UI8Matrix": np.dtype(np.uint8),
    "I16Matrix": np.dtype(np.int16),
    "UI16Matrix": np.dtype(np.uint16),
    "I32Matrix": np.dtype(np.int32),
    "UI32Matrix": np.dtype(np.uint32),
    "I64Matrix": np.dtype(np.int64),
    "UI64Matrix": np.dtype(np.uint64),
    "F32Matrix": np.dtype(np.float32),
    "F64Matrix": np.dtype(np.float64),
}
_COMPLEX_ITEM_SIZES = {
    "C32Vector": 8,
    "C64Vector": 16,
    "C128Vector": 32,
    "C32Matrix": 8,
    "C64Matrix": 16,
    "C128Matrix": 32,
}
_KNOWN_TYPES = {
    "Boolean",
    "Int8",
    "UInt8",
    "Int16",
    "UInt16",
    "Int32",
    "UInt32",
    "Int64",
    "UInt64",
    "Int128",
    "UInt128",
    "Float32",
    "Float64",
    "Float128",
    "Complex32",
    "Complex64",
    "Complex128",
    "String",
    "TimePoint",
    *_NUMERIC_DTYPES,
    *_COMPLEX_ITEM_SIZES,
    "I128Vector",
    "UI128Vector",
    "F128Vector",
    "I128Matrix",
    "UI128Matrix",
    "F128Matrix",
}


@dataclass(frozen=True)
class PropertyValue:
    status: Literal["ok", "attached", "unavailable"]
    text: str | None
    values: tuple[int | float, ...] | None
    shape: tuple[int, ...] | None
    type: str
    message: str | None = None


def _tag(local: str) -> str:
    """Return a namespace-qualified tag name."""
    return f"{{{XISF_NS}}}{local}"


def _children(elem: Element, local: str) -> list[Element]:
    """Return direct children with the requested XISF tag."""
    tag = _tag(local)
    return [child for child in elem if child.tag == tag]


def _images(root: Element) -> list[Element]:
    """Return the root element's direct Image children."""
    return _children(root, "Image")


def _parse_xml_header(source: Path | BinaryIO) -> tuple[Element, int]:
    """Read and parse the XISF XML header. Returns (root_element, header_end_offset)."""
    if isinstance(source, Path):
        f = open(source, "rb")  # noqa: SIM115
        owns_file = True
    else:
        f = source
        owns_file = False
    try:
        f.seek(0)
        preamble = f.read(16)
        if len(preamble) != 16:
            raise XISFError(INVALID_HEADER_MESSAGE)
        magic = preamble[:8]
        if magic != XISF_MAGIC:
            raise XISFError(BAD_SIGNATURE_MESSAGE)

        header_len = struct.unpack("<I", preamble[8:12])[0]
        f.seek(0, 2)
        file_size = f.tell()
        if header_len > file_size - 16:
            raise XISFError(INVALID_HEADER_MESSAGE)
        f.seek(16)
        xml_bytes = f.read(header_len)
        if len(xml_bytes) != header_len:
            raise XISFError(INVALID_HEADER_MESSAGE)
        xml_text = xml_bytes.decode("utf-8").rstrip("\x00")
        root = ET.fromstring(xml_text)
    except XISFError:
        raise
    except (
        OSError,
        struct.error,
        UnicodeDecodeError,
        ET.ParseError,
        DefusedXmlException,
    ) as exc:
        raise XISFError(INVALID_HEADER_MESSAGE) from exc
    finally:
        if owns_file:
            f.close()

    return root, 16 + header_len


def load_image_data(source: Path | BinaryIO, hdu: int = 0) -> np.ndarray:
    """Load image data as float64 array normalized to [0, 1].

    Returns shape (H, W) for Gray or (3, H, W) for RGB.
    The hdu parameter selects among multiple Image elements (0-indexed).
    """
    root, _ = _parse_xml_header(source)

    images = _images(root)
    if hdu < 0 or hdu >= len(images):
        raise XISFError(IMAGE_INDEX_MESSAGE.format(index=hdu, count=len(images)))
    img_elem = images[hdu]

    # Parse geometry: "W:H:C"
    geometry_value = img_elem.get("geometry")
    if geometry_value is None:
        raise XISFError(INVALID_GEOMETRY_MESSAGE.format(geometry="(missing)"))
    geom_str = geometry_value
    geom_parts = geom_str.split(":")
    if not geom_str or any(not value for value in geom_parts):
        raise XISFError(INVALID_GEOMETRY_MESSAGE.format(geometry=geom_str))
    try:
        geometry = tuple(int(value) for value in geom_parts)
    except ValueError as exc:
        raise XISFError(INVALID_GEOMETRY_MESSAGE.format(geometry=geom_str)) from exc
    if any(value <= 0 for value in geometry):
        raise XISFError(INVALID_GEOMETRY_MESSAGE.format(geometry=geom_str))
    if len(geometry) == 1:
        raise XISFError(INVALID_GEOMETRY_MESSAGE.format(geometry=geom_str))
    if len(geometry) != 3:
        raise XISFUnavailableError(UNSUPPORTED_GEOMETRY_MESSAGE)
    width, height, channels = geometry

    # Sample format
    fmt = img_elem.get("sampleFormat", "")
    if fmt not in SAMPLE_FORMATS:
        raise XISFUnavailableError(UNSUPPORTED_SAMPLE_FORMAT_MESSAGE.format(format=fmt))
    dtype = SAMPLE_FORMATS[fmt]
    item_size = dtype.itemsize

    pixel_storage = img_elem.get("pixelStorage", "Planar")
    if pixel_storage not in {"Planar", "Normal"}:
        raise XISFUnavailableError(
            UNSUPPORTED_PIXEL_STORAGE_MESSAGE.format(pixel_storage=pixel_storage)
        )

    color_space = img_elem.get("colorSpace", "Gray")
    if color_space not in {"Gray", "RGB"}:
        raise XISFUnavailableError(
            UNSUPPORTED_COLOR_SPACE_MESSAGE.format(color_space=color_space or "(missing)")
        )

    bounds_value = img_elem.get("bounds")
    bounds: tuple[float, float] | None = None
    if bounds_value is not None:
        parts = bounds_value.split(":")
        try:
            if len(parts) != 2:
                raise ValueError
            lower, upper = (float(value) for value in parts)
        except ValueError as exc:
            raise XISFError(INVALID_BOUNDS_MESSAGE.format(bounds=bounds_value)) from exc
        if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
            raise XISFError(INVALID_BOUNDS_MESSAGE.format(bounds=bounds_value))
        bounds = (lower, upper)

    spec = block_spec(img_elem)
    expected_size = width * height * channels * item_size
    pixel_bytes = read_block(spec, source, item_size=item_size, expected_size=expected_size)

    # Convert to numpy array
    stored_dtype = dtype.newbyteorder(">" if spec.byte_order == "big" else "<")
    arr = np.frombuffer(pixel_bytes, dtype=stored_dtype).astype(dtype, copy=False)

    if channels == 1:
        arr = arr.reshape(height, width)
    elif pixel_storage == "Normal":
        arr = np.moveaxis(arr.reshape(height, width, channels), 2, 0)
    else:
        # XISF uses planar layout: RRR...GGG...BBB
        arr = arr.reshape(channels, height, width)

    if color_space == "Gray":
        if arr.ndim == 3:
            arr = arr[0]
    else:
        if arr.ndim != 3 or channels < 3:
            raise XISFError(INVALID_GEOMETRY_MESSAGE.format(geometry=geom_str))
        arr = arr[:3]

    bounded_integer = bounds is not None and np.issubdtype(arr.dtype, np.integer)
    bounded_float = bounds is not None and bounds != (0.0, 1.0)
    if bounded_integer or bounded_float:
        lower, upper = bounds
        arr = (arr.astype(np.float64) - lower) / (upper - lower)
        normalized = np.clip(arr, 0.0, 1.0)
    else:
        # Preserve the established type-range and unbounded-float paths.
        normalized = normalize_to_01(arr)

    return reshape_color(normalized)


def verify_image(source: Path | BinaryIO, hdu: int = 0) -> None:
    """Verify one image's stored pixels without decompressing them."""
    root, _ = _parse_xml_header(source)
    images = _images(root)
    if hdu < 0 or hdu >= len(images):
        raise XISFError(IMAGE_INDEX_MESSAGE.format(index=hdu, count=len(images)))
    spec = block_spec(images[hdu])
    if spec.checksum is None and is_attached(spec):
        compression = _parse_compression(spec.compression, None)
        subblocks = _parse_subblocks(spec.subblocks)
        _validate_declared_sizes(spec, compression, subblocks, None)
        position, stored_size = _attachment_parts(spec.location)
        try:
            if isinstance(source, Path):
                file_size = source.stat().st_size
            else:
                source.seek(0, 2)
                file_size = source.tell()
        except (OSError, ValueError) as exc:
            raise XISFError(INVALID_BLOCK_MESSAGE) from exc
        if position > file_size or stored_size > file_size - position:
            raise XISFError(INVALID_BLOCK_MESSAGE)
        if subblocks is not None and sum(size for size, _ in subblocks) != stored_size:
            raise XISFError(INVALID_COMPRESSED_BLOCK_MESSAGE)
        return
    verify_block(spec, source)


def _canonical_type(value: str) -> str:
    return _CANONICAL_TYPES.get(value, value)


def _property_shape(prop: Element, prop_type: str) -> tuple[int, ...] | None:
    try:
        if prop_type.endswith("Vector"):
            shape = (int(prop.get("length", "")),)
        elif prop_type.endswith("Matrix"):
            shape = (int(prop.get("rows", "")), int(prop.get("columns", "")))
        else:
            return None
    except ValueError:
        return None
    return shape if all(size >= 0 for size in shape) else None


def _unavailable(prop_type: str, shape: tuple[int, ...] | None, message: str) -> PropertyValue:
    return PropertyValue("unavailable", None, None, shape, prop_type, message)


def _read_property(prop: Element, source: Path | BinaryIO | None) -> PropertyValue:
    """Read one XISF property without accessing attachments when source is None."""
    prop_type = _canonical_type(prop.get("type", ""))
    shape = _property_shape(prop, prop_type)

    if prop_type == "String" and not prop.get("location"):
        # XISF strings live in element text. Keep accepting the old scalar
        # attribute form emitted by some writers when there is no text.
        text = prop.text if prop.text is not None else prop.get("value", "")
        return PropertyValue("ok", text, None, None, prop_type)
    if prop_type not in _KNOWN_TYPES:
        return PropertyValue("ok", None, None, shape, prop_type)
    if "value" in prop.attrib:
        return PropertyValue("ok", prop.get("value", ""), None, shape, prop_type)
    if prop_type in {
        "Boolean",
        "Int8",
        "UInt8",
        "Int16",
        "UInt16",
        "Int32",
        "UInt32",
        "Int64",
        "UInt64",
        "Int128",
        "UInt128",
        "Float32",
        "Float64",
        "Float128",
        "Complex32",
        "Complex64",
        "Complex128",
        "TimePoint",
    }:
        # Compatibility extension: lenient writers put scalar and TimePoint
        # values in element text when the required value attribute is absent.
        return PropertyValue("ok", prop.text or "", None, None, prop_type)
    if not prop.get("location"):
        return _unavailable(prop_type, shape, "missing stored value")
    if (prop_type.endswith("Vector") or prop_type.endswith("Matrix")) and shape is None:
        return _unavailable(prop_type, None, "invalid or missing dimensions")

    try:
        spec = block_spec(prop)
        if source is None and is_attached(spec):
            return PropertyValue("attached", None, None, shape, prop_type)
        if prop_type == "String":
            data = read_block(spec, source)
            try:
                text = bytes(data).decode("utf-8")
            except UnicodeDecodeError:
                return _unavailable(prop_type, None, "invalid UTF-8 string")
            return PropertyValue("ok", text, None, None, prop_type)
        if shape is None:
            return _unavailable(prop_type, None, "invalid or missing dimensions")

        count = math.prod(shape)
        if prop_type in _COMPLEX_ITEM_SIZES:
            read_block(
                spec,
                source,
                item_size=_COMPLEX_ITEM_SIZES[prop_type],
                expected_size=count * _COMPLEX_ITEM_SIZES[prop_type],
            )
            return PropertyValue("ok", None, None, shape, prop_type)
        dtype = _NUMERIC_DTYPES.get(prop_type)
        if dtype is None:
            return _unavailable(prop_type, shape, "numeric type is not supported")
        stored_dtype = dtype.newbyteorder(">" if spec.byte_order == "big" else "<")
        data = read_block(
            spec,
            source,
            item_size=dtype.itemsize,
            expected_size=count * dtype.itemsize,
        )
        values = tuple(np.frombuffer(data, dtype=stored_dtype).tolist())
        return PropertyValue("ok", None, values, shape, prop_type)
    except XISFError as exc:
        return _unavailable(prop_type, shape, str(exc))


def _shape_text(value: PropertyValue) -> str:
    if value.shape is None:
        return ""
    if len(value.shape) == 1:
        return str(value.shape[0])
    return f"{value.shape[0]}×{value.shape[1]}"


def _display_value(value: PropertyValue) -> str:
    """Format a structured property value for the Header tab."""
    if value.status == "attached":
        result = f"{value.type} {_shape_text(value)} (stored in the file, not shown)"
        return result.replace("  ", " ")
    if value.status == "unavailable":
        return f"{value.type} (unavailable: {value.message})"
    if value.text is not None:
        return value.text
    if value.values is not None and len(value.values) <= 9:
        return ", ".join(str(item) for item in value.values)
    if value.shape is not None:
        return f"{value.type} {_shape_text(value)}"
    return value.type


def _solution_properties(img_elem: Element, prefix: str) -> dict[str, Element]:
    return {
        prop.get("id", "").removeprefix(prefix): prop
        for prop in _children(img_elem, "Property")
        if prop.get("id", "").startswith(prefix)
    }


def _geometry(img_elem: Element) -> tuple[int, int] | None:
    parts = img_elem.get("geometry", "").split(":")
    try:
        width, height = int(parts[0]), int(parts[1])
    except IndexError, ValueError:
        return None
    return (width, height) if width >= 0 and height >= 0 else None


def _typed_values(
    props: dict[str, Element], key: str, prop_type: str, shape: tuple[int, ...], source
) -> tuple[int | float, ...] | None:
    prop = props.get(key)
    if prop is None:
        return None
    value = _read_property(prop, source)
    if value.status != "ok" or value.type != prop_type or value.shape != shape:
        return None
    return value.values


def _wcs_from_values(
    crval: tuple[int | float, ...] | None,
    crpix: tuple[int | float, ...] | None,
    cd: tuple[int | float, ...] | None,
    geometry: tuple[int, int] | None,
) -> WcsParams | None:
    if crval is None or crpix is None or cd is None or geometry is None:
        return None
    numbers = tuple(float(value) for value in (*crval, *crpix, *cd))
    if not all(math.isfinite(value) for value in numbers):
        return None
    if float(cd[0]) * float(cd[3]) - float(cd[1]) * float(cd[2]) == 0:
        return None
    return WcsParams(
        crval1=float(crval[0]),
        crval2=float(crval[1]),
        crpix1=float(crpix[0]) + 0.5,
        crpix2=float(crpix[1]) + 0.5,
        cd1_1=float(cd[0]),
        cd1_2=float(cd[1]),
        cd2_1=float(cd[2]),
        cd2_2=float(cd[3]),
        naxis1=geometry[0],
        naxis2=geometry[1],
    )


def _new_solution(props: dict[str, Element], source, geometry) -> FileSolution:
    version_prop = props.get("Version")
    version = _read_property(version_prop, source) if version_prop is not None else None
    version_text = (
        version.text
        if version is not None and version.status == "ok" and version.type == "String"
        else None
    )
    if version_text is None:
        return FileSolution(unavailable_reason=MALFORMED_SOLUTION_MESSAGE)
    if re.fullmatch(r"\d+\.\d+", version_text) is None or version_text.split(".")[0] != "1":
        return FileSolution(
            unavailable_reason=UNSUPPORTED_SOLUTION_VERSION_MESSAGE.format(version=version_text)
        )

    projection_prop = props.get("ProjectionSystem")
    projection = _read_property(projection_prop, source) if projection_prop is not None else None
    projection_text = (
        projection.text
        if projection is not None and projection.status == "ok" and projection.type == "String"
        else None
    )
    if projection_text is None:
        return FileSolution(unavailable_reason=MALFORMED_SOLUTION_MESSAGE)
    if projection_text != "Gnomonic":
        return FileSolution(
            unavailable_reason=UNSUPPORTED_SOLUTION_PROJECTION_MESSAGE.format(
                projection=projection_text
            )
        )

    crval = _typed_values(props, "ReferenceCelestialCoordinates", "F64Vector", (2,), source)
    crpix = _typed_values(props, "ReferenceImageCoordinates", "F64Vector", (2,), source)
    cd = _typed_values(props, "LinearTransformationMatrix", "F64Matrix", (2, 2), source)
    if crval is None or crpix is None or cd is None:
        return FileSolution(unavailable_reason=MALFORMED_SOLUTION_MESSAGE)

    reference_native = props.get("ReferenceNativeCoordinates")
    if reference_native is not None:
        native = _typed_values(props, "ReferenceNativeCoordinates", "F64Vector", (2,), source)
        if native is None or not (
            math.isclose(float(native[0]), 0.0, rel_tol=0.0, abs_tol=1e-9)
            and math.isclose(float(native[1]), 90.0, rel_tol=0.0, abs_tol=1e-9)
        ):
            return FileSolution(unavailable_reason=ROTATED_SOLUTION_MESSAGE)
    pole_prop = props.get("CelestialPoleNativeCoordinates")
    if pole_prop is not None:
        pole = _typed_values(props, "CelestialPoleNativeCoordinates", "F64Vector", (2,), source)
        pole_at_zenith = math.isclose(float(crval[1]), 90.0, rel_tol=0.0, abs_tol=1e-9)
        default_phi = 0.0 if pole_at_zenith else 180.0
        if pole is None or not (
            math.isclose(float(pole[0]), default_phi, rel_tol=0.0, abs_tol=1e-9)
            and math.isclose(float(pole[1]), 90.0, rel_tol=0.0, abs_tol=1e-9)
        ):
            return FileSolution(unavailable_reason=ROTATED_SOLUTION_MESSAGE)

    wcs = _wcs_from_values(crval, crpix, cd, geometry)
    if wcs is None:
        return FileSolution(unavailable_reason=MALFORMED_SOLUTION_MESSAGE)
    return FileSolution(wcs=wcs)


def _legacy_solution(props: dict[str, Element], source, geometry) -> WcsParams | None:
    projection_prop = props.get("ProjectionSystem")
    if projection_prop is None:
        return None
    projection = _read_property(projection_prop, source)
    if projection.status != "ok" or (projection.text or "").strip().lower() != "gnomonic":
        return None
    return _wcs_from_values(
        _typed_values(props, "ReferenceCelestialCoordinates", "F64Vector", (2,), source),
        _typed_values(props, "ReferenceImageCoordinates", "F64Vector", (2,), source),
        _typed_values(props, "LinearTransformationMatrix", "F64Matrix", (2, 2), source),
        geometry,
    )


def _property_solution(img_elem: Element, source) -> FileSolution | None:
    new_props = _solution_properties(img_elem, "AstrometricSolution:")
    if new_props:
        return _new_solution(new_props, source, _geometry(img_elem))
    legacy_props = _solution_properties(img_elem, "PCL:AstrometricSolution:")
    legacy = _legacy_solution(legacy_props, source, _geometry(img_elem))
    return FileSolution(wcs=legacy) if legacy is not None else None


def _wcs_cards(wcs: WcsParams, existing_keys: set[str]) -> list[dict]:
    derived = {
        "CTYPE1": "RA---TAN",
        "CTYPE2": "DEC--TAN",
        "CRVAL1": repr(wcs.crval1),
        "CRVAL2": repr(wcs.crval2),
        "CRPIX1": repr(wcs.crpix1),
        "CRPIX2": repr(wcs.crpix2),
        "CD1_1": repr(wcs.cd1_1),
        "CD1_2": repr(wcs.cd1_2),
        "CD2_1": repr(wcs.cd2_1),
        "CD2_2": repr(wcs.cd2_2),
    }
    return [
        {"key": key, "value": value, "comment": "XISF: AstrometricSolution", "description": ""}
        for key, value in derived.items()
        if key not in existing_keys
    ]


def read_header(source: Path | BinaryIO, hdu: int = 0) -> list[dict]:
    """Read metadata as {key, value, comment} dicts.

    1. <FITSKeyword> elements (same format as FITS headers).
    2. NAXIS1/NAXIS2 derived from the Image `geometry` attribute (when absent).
    3. <Property> elements, mapping scalar XISF property IDs to equivalent
       FITS-style keywords and summarizing other values for display.
    4. Synthetic FITS WCS cards reconstructed from a usable stored solution.
    Steps 2-4 only add keys that aren't already present (real FITSKeyword wins).
    """
    root, _ = _parse_xml_header(source)

    images = _images(root)
    if hdu < 0 or hdu >= len(images):
        raise XISFError(IMAGE_INDEX_MESSAGE.format(index=hdu, count=len(images)))
    img_elem = images[hdu]

    cards: list[dict] = []

    # FITS keywords (preferred — most XISF files from PixInsight include these)
    for kw in _children(img_elem, "FITSKeyword"):
        name = kw.get("name", "")
        cards.append(
            {
                "key": name,
                "value": kw.get("value", "").strip("'\""),
                "comment": kw.get("comment", ""),
                "description": get_keyword_description(name),
            }
        )

    # Geometry → NAXIS keywords. XISF keeps image dimensions in the Image
    # `geometry="W:H:C"` attribute, not as FITS keywords; surface them so any
    # FITS-oriented consumer (ingest dimensions, header view) sees the size.
    # Only added when absent — real FITSKeyword NAXIS cards always win.
    existing_keys = {c["key"] for c in cards}
    geom_parts = img_elem.get("geometry", "").split(":")
    if len(geom_parts) >= 2:
        for axis_key, raw in (("NAXIS1", geom_parts[0]), ("NAXIS2", geom_parts[1])):
            if axis_key in existing_keys or not raw.isdigit():
                continue
            cards.append(
                {
                    "key": axis_key,
                    "value": raw,
                    "comment": "XISF: geometry",
                    "description": get_keyword_description(axis_key),
                }
            )
            existing_keys.add(axis_key)

    # XISF properties (supplement with mapped names if not already in FITS keywords)
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

    for prop in _children(img_elem, "Property"):
        prop_id = prop.get("id", "")
        value = _read_property(prop, None)

        mapped_key = prop_map.get(prop_id)
        if mapped_key and mapped_key not in existing_keys and value.status == "ok" and value.text:
            cards.append(
                {
                    "key": mapped_key,
                    "value": value.text,
                    "comment": f"XISF: {prop_id}",
                    "description": get_keyword_description(mapped_key),
                }
            )
            existing_keys.add(mapped_key)
        elif not mapped_key:
            display = _display_value(value)
            if not display:
                continue
            cards.append(
                {
                    "key": prop_id,
                    "value": display,
                    "comment": "",
                    "description": get_keyword_description(prop_id),
                }
            )

    # Header reads deliberately do not touch attached property blocks.
    stored = _property_solution(img_elem, None)
    if stored is not None and stored.wcs is not None:
        cards.extend(_wcs_cards(stored.wcs, existing_keys))

    return cards


def read_solution(source: Path | BinaryIO, hdu: int = 0) -> FileSolution:
    """Read the stored XISF solution in displayed, top-down row order.

    Property solutions use the XISF half-integer pixel convention, so their
    reference image coordinates gain 0.5 in the FITS-compatible WCS model.
    FITS-keyword WCS uses FITS row order and is flipped only when no complete
    property solution is present.
    """
    root, _ = _parse_xml_header(source)
    images = _images(root)
    if hdu < 0 or hdu >= len(images):
        raise XISFError(IMAGE_INDEX_MESSAGE.format(index=hdu, count=len(images)))
    img_elem = images[hdu]

    geometry_cards: list[dict] = []
    geom_parts = img_elem.get("geometry", "").split(":")
    if len(geom_parts) >= 2:
        geometry_cards = [
            {"key": "NAXIS1", "value": geom_parts[0]},
            {"key": "NAXIS2", "value": geom_parts[1]},
        ]

    stored = _property_solution(img_elem, source)
    if stored is not None:
        return stored

    fits_cards = [
        {
            "key": kw.get("name", ""),
            "value": kw.get("value", "").strip("'\""),
        }
        for kw in _children(img_elem, "FITSKeyword")
    ]
    # XISF geometry is the image's authoritative post-crop size. Appending it
    # makes it win over stale FITS NAXIS cards when cards become a key/value map.
    fits_cards.extend(geometry_cards)
    params = detect_wcs_from_cards(fits_cards)
    return FileSolution(wcs=flip_wcs_rows(params) if params is not None else None)


def read_wcs_params(source: Path | BinaryIO, hdu: int = 0) -> WcsParams | None:
    """Return the usable WCS from :func:`read_solution`, if one exists."""
    return read_solution(source, hdu).wcs


def list_extensions(source: Path | BinaryIO) -> list[dict]:
    """List all Image elements in the XISF file."""
    root, _ = _parse_xml_header(source)

    result = []
    for i, img in enumerate(_images(root)):
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
