"""Camera-raw pixel and metadata readers."""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Literal

import numpy as np

from nightcrate.services.cfa import PatternInfo, pattern_from_raw
from nightcrate.services.raw_support import require

RAW_EXTENSIONS = frozenset(
    {".cr2", ".cr3", ".nef", ".nrw", ".arw", ".raf", ".orf", ".rw2", ".pef", ".dng"}
)


class RawUnsupported(ValueError):
    """A camera-raw file that the installed LibRaw cannot decode."""


@dataclass(frozen=True)
class RawSamples:
    samples: np.ndarray | None
    rgb: np.ndarray | None
    pattern: PatternInfo | None
    black_levels: tuple[float, ...]
    white_level: int
    visible: tuple[int, int, int, int]


@dataclass(frozen=True)
class RawLayout:
    pattern: PatternInfo | None
    black_levels: tuple[float, ...]
    white_level: int
    visible: tuple[int, int, int, int]


TimeSource = Literal["exif_offset", "maker_note", "none"]


@dataclass(frozen=True)
class RawMetadata:
    captured_local: datetime | None
    utc_offset: timedelta | None
    time_source: TimeSource
    exposure_s: float | None
    iso: int | None
    make: str | None
    model: str | None
    body_serial: str | None
    lens: str | None
    lens_serial: str | None
    focal_length_mm: float | None
    orientation: int | None
    camera_temp_c: float | None
    sensor_temp_c: float | None
    compression: str | None
    cards: list[dict]


def _rewind(source: Path | BinaryIO) -> Path | BinaryIO:
    if not isinstance(source, Path):
        source.seek(0)
    return source


def _plain_unsupported(exc: Exception) -> RawUnsupported:
    message = str(exc).strip()
    if not message or len(message) > 180:
        message = "This camera raw file isn't supported."
    return RawUnsupported(message)


def _layout_from_raw(raw) -> RawLayout:
    sizes = raw.sizes
    visible = (
        int(sizes.left_margin),
        int(sizes.top_margin),
        int(sizes.width),
        int(sizes.height),
    )
    raw_pattern = raw.raw_pattern
    pattern = None
    if raw_pattern is not None:
        indices = np.asarray(raw_pattern)
        if indices.ndim != 2 or indices.size == 0:
            raise RawUnsupported("This camera raw file has an unsupported colour pattern.")
        rows = (np.arange(indices.shape[0]) + visible[1]) % indices.shape[0]
        columns = (np.arange(indices.shape[1]) + visible[0]) % indices.shape[1]
        pattern = pattern_from_raw(indices[np.ix_(rows, columns)], bytes(raw.color_desc))
    return RawLayout(
        pattern=pattern,
        black_levels=tuple(float(value) for value in raw.black_level_per_channel),
        white_level=int(raw.white_level),
        visible=visible,
    )


def read_raw_layout(source: Path | BinaryIO) -> RawLayout:
    """Read levels, visible bounds and CFA phase without copying full image arrays."""
    require()
    import rawpy

    try:
        raw_source = str(source) if isinstance(source, Path) else _rewind(source)
        with rawpy.imread(raw_source) as raw:
            return _layout_from_raw(raw)
    except RawUnsupported:
        raise
    except rawpy.LibRawError as exc:
        raise _plain_unsupported(exc) from None
    except (OSError, ValueError) as exc:
        raise _plain_unsupported(exc) from None


def read_raw_samples(source: Path | BinaryIO) -> RawSamples:
    """Read visible recorded samples and their CFA without processing them."""
    require()
    import rawpy

    try:
        raw_source = str(source) if isinstance(source, Path) else _rewind(source)
        with rawpy.imread(raw_source) as raw:
            data = np.array(raw.raw_image_visible, copy=True)
            black = tuple(float(value) for value in raw.black_level_per_channel)
            white = int(raw.white_level)
            sizes = raw.sizes
            visible = (
                int(sizes.left_margin),
                int(sizes.top_margin),
                int(sizes.width),
                int(sizes.height),
            )
            if data.ndim == 3 and data.shape[-1] >= 3:
                rgb = np.moveaxis(data[..., :3], -1, 0)
                return RawSamples(None, rgb, None, black, white, visible)
            if data.ndim != 2:
                raise RawUnsupported("This camera raw file has an unsupported pixel layout.")
            colours = np.array(raw.raw_colors_visible, copy=True)
            pattern = pattern_from_raw(colours, bytes(raw.color_desc))
            return RawSamples(data, None, pattern, black, white, visible)
    except RawUnsupported:
        raise
    except rawpy.LibRawError as exc:
        raise _plain_unsupported(exc) from None
    except (OSError, ValueError) as exc:
        raise _plain_unsupported(exc) from None


def _exiv2_image(source: Path | BinaryIO):
    import exiv2

    if isinstance(source, Path):
        return exiv2.ImageFactory.open(str(source))
    source.seek(0)
    return exiv2.ImageFactory.open(source.read())


def _datum_map(exif_data) -> dict[str, object]:
    return {datum.key(): datum for datum in exif_data}


def _text(data: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        datum = data.get(key)
        if datum is not None:
            value = datum.toString().strip()
            if value:
                return value
    return None


def _float(data: dict[str, object], *keys: str) -> float | None:
    for key in keys:
        datum = data.get(key)
        if datum is not None:
            try:
                return float(datum.toFloat())
            except TypeError, ValueError, OverflowError:
                continue
    return None


def _exif_exposure(data: dict[str, object]) -> float | None:
    """Read ExposureTime's rational text before using its lossy float view."""
    datum = data.get("Exif.Photo.ExposureTime")
    if datum is None:
        return None
    text = datum.toString().strip()
    match = re.fullmatch(r"([+-]?\d+)\s*/\s*(\d+)", text)
    if match is not None and int(match.group(2)) != 0:
        return int(match.group(1)) / int(match.group(2))
    try:
        return float(datum.toFloat())
    except TypeError, ValueError, OverflowError:
        return None


def _libraw_exposure(source: Path | BinaryIO) -> float | None:
    """Return LibRaw's shutter value, rounded past its float32 noise."""
    import rawpy

    try:
        raw_source = str(source) if isinstance(source, Path) else _rewind(source)
        with rawpy.imread(raw_source) as raw:
            value = float(raw.other.shutter_speed)
    except rawpy.LibRawError, AttributeError, OSError, TypeError, ValueError, OverflowError:
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return _six_significant_digits(value)


def _six_significant_digits(value: float) -> float:
    return float(f"{value:.6g}")


def _exposure_seconds(data: dict[str, object], source: Path | BinaryIO) -> float | None:
    exposure = _exif_exposure(data)
    return exposure if exposure is not None else _libraw_exposure(source)


def _printed(exif_data, data: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        datum = data.get(key)
        if datum is None:
            continue
        try:
            value = datum.print(exif_data).strip()
        except Exception:  # noqa: BLE001 - fall back for unusual maker-note types
            value = datum.toString().strip()
        if value:
            return value
    return None


def _integer(data: dict[str, object], *keys: str) -> int | None:
    value = _float(data, *keys)
    return int(value) if value is not None else None


def _parse_offset(value: str | None) -> timedelta | None:
    if not value:
        return None
    match = re.fullmatch(r"\s*([+-])(\d{2}):?(\d{2})\s*", value)
    if match is None:
        return None
    minutes = int(match.group(2)) * 60 + int(match.group(3))
    return timedelta(minutes=minutes if match.group(1) == "+" else -minutes)


def _parse_datetime(value: str | None, subsecond: str | None) -> datetime | None:
    if not value:
        return None
    try:
        captured = datetime.strptime(value.strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    if subsecond:
        digits = "".join(character for character in subsecond if character.isdigit())[:6]
        if digits:
            captured = captured.replace(microsecond=int(digits.ljust(6, "0")))
    return captured


def _maker_offset(data: dict[str, object]) -> timedelta | None:
    canon = _integer(data, "Exif.CanonTi.TimeZone")
    if canon is not None and -24 * 60 <= canon <= 24 * 60:
        return timedelta(minutes=canon)
    nikon_minutes = _integer(
        data,
        "Exif.NikonWt.Timezone",
        "Exif.NikonWt.TimeZone",
        "Exif.Nikon3.TimeZone",
    )
    if nikon_minutes is not None and -24 * 60 <= nikon_minutes <= 24 * 60:
        return timedelta(minutes=nikon_minutes)
    return None


def _temperature(exif_data, data: dict[str, object], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        datum = data.get(key)
        if datum is None:
            continue
        try:
            interpreted = datum.print(exif_data)
        except Exception:  # noqa: BLE001 - fall back to Exiv2's plain representation
            interpreted = datum.toString()
        match = re.search(r"[-+]?\d+(?:\.\d+)?", interpreted)
        if match:
            return float(match.group())
    return None


def _is_maker_note(key: str) -> bool:
    group = key.split(".", 2)[1] if key.count(".") >= 2 else ""
    return group not in {"Image", "Photo", "GPSInfo", "Iop", "Thumbnail", "SubImage1"}


_BYTE_TYPES = frozenset({"Undefined", "Byte", "SByte"})
_NUMERIC_TYPES = frozenset(
    {"Short", "SShort", "Long", "SLong", "Rational", "SRational", "Float", "Double"}
)


def _card_value(exif_data, datum) -> str | None:
    plain = datum.toString()
    try:
        value = datum.print(exif_data)
        interpreted = value != plain
    except Exception:  # noqa: BLE001 - a failed interpretation is raw data
        value = plain
        interpreted = False
    if interpreted:
        return value
    type_name = datum.typeName()
    count = datum.count()
    if type_name in _BYTE_TYPES and count > 16:
        return None
    if type_name in _NUMERIC_TYPES and count > 64:
        return None
    return value


def _cards(exif_data) -> list[dict]:
    cards: list[dict] = []
    for datum in exif_data:
        key = datum.key()
        value = _card_value(exif_data, datum)
        if value is None:
            continue
        cards.append(
            {
                "group": "Maker notes" if _is_maker_note(key) else "EXIF",
                "key": key,
                "value": value,
                "comment": datum.tagLabel() or datum.tagDesc() or "",
            }
        )
    order = {"EXIF": 0, "Maker notes": 1}
    return sorted(cards, key=lambda card: order[card["group"]])


def read_raw_metadata(source: Path | BinaryIO) -> RawMetadata:
    """Read EXIF and maker-note facts without changing the source file."""
    require()
    try:
        image = _exiv2_image(source)
        image.readMetadata()
        exif_data = image.exifData()
    except Exception as exc:  # exiv2 exposes several native exception subclasses
        raise _plain_unsupported(exc) from None
    data = _datum_map(exif_data)

    captured = _parse_datetime(
        _text(data, "Exif.Photo.DateTimeOriginal", "Exif.Image.DateTime"),
        _text(data, "Exif.Photo.SubSecTimeOriginal"),
    )
    offset = _parse_offset(_text(data, "Exif.Photo.OffsetTimeOriginal", "Exif.Photo.OffsetTime"))
    time_source: TimeSource = "exif_offset" if offset is not None else "none"
    if offset is None:
        offset = _maker_offset(data)
        if offset is not None:
            time_source = "maker_note"

    camera_temp = _temperature(
        exif_data,
        data,
        (
            "Exif.CanonSi.CameraTemperature",
            "Exif.PentaxDng.CameraTemperature",
            "Exif.PentaxDng.Temperature",
            "Exif.Pentax.Temperature",
            "Exif.Sony1.CameraTemperature",
            "Exif.Sony2Fp.CameraTemperature",
            "Exif.SonyMisc1.CameraTemperature",
        ),
    )
    sensor_temp = _temperature(
        exif_data,
        data,
        (
            "Exif.OlympusEq.SensorTemperature",
            "Exif.OlympusFi.SensorTemperature",
            "Exif.PentaxDng.SensorTemperature",
        ),
    )
    compression_values = [
        _printed(exif_data, data, "Exif.Nikon3.NEFCompression"),
        _printed(
            exif_data,
            data,
            "Exif.Sony1.RAWFileType",
            "Exif.Sony2.RAWFileType",
        ),
    ]
    if not any(compression_values):
        compression_values.append(_printed(exif_data, data, "Exif.Image.Compression"))
    compression = "; ".join(dict.fromkeys(value for value in compression_values if value)) or None

    return RawMetadata(
        captured_local=captured,
        utc_offset=offset,
        time_source=time_source,
        exposure_s=_exposure_seconds(data, source),
        iso=_integer(
            data,
            "Exif.Photo.ISOSpeedRatings",
            "Exif.Photo.PhotographicSensitivity",
            "Exif.Photo.RecommendedExposureIndex",
        ),
        make=_text(data, "Exif.Image.Make"),
        model=_text(data, "Exif.Image.Model"),
        body_serial=_text(
            data,
            "Exif.Photo.BodySerialNumber",
            "Exif.Canon.SerialNumber",
            "Exif.Nikon3.SerialNumber",
        ),
        lens=_text(data, "Exif.Photo.LensModel", "Exif.CanonCs.LensType"),
        lens_serial=_text(data, "Exif.Photo.LensSerialNumber"),
        focal_length_mm=_float(data, "Exif.Photo.FocalLength"),
        orientation=_integer(data, "Exif.Image.Orientation"),
        camera_temp_c=camera_temp,
        sensor_temp_c=sensor_temp,
        compression=compression,
        cards=_cards(exif_data),
    )


def _reusable_sources(source: Path | BinaryIO) -> tuple[Path | BinaryIO, Path | BinaryIO]:
    if isinstance(source, Path):
        return source, source
    source.seek(0)
    payload = source.read()
    return io.BytesIO(payload), io.BytesIO(payload)


def read_header(source: Path | BinaryIO) -> list[dict]:
    """Return raw metadata cards in stable, user-facing group order."""
    metadata_source, samples_source = _reusable_sources(source)
    metadata = read_raw_metadata(metadata_source)
    samples = read_raw_samples(samples_source)
    summary: list[dict] = []

    def add(group: str, key: str, value, comment: str = "") -> None:
        if value is not None:
            summary.append({"group": group, "key": key, "value": str(value), "comment": comment})

    add("Capture", "Capture time", metadata.captured_local)
    add("Capture", "UTC offset", _format_utc_offset(metadata.utc_offset))
    add("Capture", "Exposure", metadata.exposure_s, "seconds")
    add("Capture", "ISO", metadata.iso)
    add("Camera and lens", "Make", metadata.make)
    add("Camera and lens", "Model", metadata.model)
    add("Camera and lens", "Body serial", metadata.body_serial)
    add("Camera and lens", "Lens", metadata.lens)
    add("Camera and lens", "Lens serial", metadata.lens_serial)
    add("Camera and lens", "Focal length", metadata.focal_length_mm, "millimetres")
    add("Camera and lens", "Orientation", metadata.orientation, "listed, not applied")
    if samples.pattern is not None:
        add("Colour data", "Pattern", "/".join(samples.pattern.pattern.rows))
        add("Colour data", "Pattern source", samples.pattern.detail)
    add("Colour data", "Black levels", ", ".join(f"{value:g}" for value in samples.black_levels))
    add("Colour data", "White level", samples.white_level)
    add("Colour data", "Visible area", samples.visible, "left, top, width, height")
    return summary + metadata.cards


def _format_utc_offset(offset: timedelta | None) -> str | None:
    if offset is None:
        return None
    total_minutes = round(offset.total_seconds() / 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"{sign}{hours:02d}:{minutes:02d}"
