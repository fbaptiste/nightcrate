"""One worker-safe loader for every image path NightCrate accepts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Literal

import numpy as np
from astropy.io import fits

from nightcrate.services import pxiproject_io, raw_io, standard_io, xisf_io
from nightcrate.services.cfa import CfaPattern, PatternInfo, pattern_from_fits, pattern_from_xisf
from nightcrate.services.imaging import LUM_B, LUM_G, LUM_R, reshape_color
from nightcrate.services.mosaic import (
    Mosaic,
    channel_samples,
    colour_superpixels,
    display_rgb,
    measurement_grey,
)
from nightcrate.services.path_resolver import resolve_path as _resolve_path_raw

ImageKind = Literal["mono", "colour", "mosaic"]
ImageUnits = Literal["adu", "float"]


@dataclass
class LoadedImage:
    kind: ImageKind
    recorded: np.ndarray
    units: ImageUnits
    pattern: PatternInfo | None
    width: int
    height: int
    white_level: float | None = None
    full_scale: float | None = None
    _normalise_mode: Literal["integer", "float", "bounds", "raw", "identity"] = field(
        default="identity", repr=False
    )
    _normalise_min: float = field(default=0.0, repr=False)
    _normalise_max: float = field(default=1.0, repr=False)
    _normalised_cache: np.ndarray | None = field(default=None, init=False, repr=False)
    _display_cache: np.ndarray | None = field(default=None, init=False, repr=False, compare=False)
    _display_lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)

    def normalise(self, values: np.ndarray) -> np.ndarray:
        """Map recorded samples into working units without losing excursions.

        This affine map is used for measurements, so it must remain the exact
        inverse of :meth:`denormalise`. Display consumers clip explicitly.
        """
        data = np.asarray(values, dtype=np.float32)
        if self._normalise_mode in {"integer", "bounds"}:
            span = self._normalise_max - self._normalise_min
            result = (data - self._normalise_min) / span if span > 0 else np.zeros_like(data)
        elif self._normalise_mode in {"float", "raw"}:
            result = data / self._normalise_max if self._normalise_max > 0 else np.zeros_like(data)
        else:
            result = data
        return result.astype(np.float32, copy=False)

    def normalised(self) -> np.ndarray:
        if self._normalised_cache is None:
            self._normalised_cache = self.normalise(self.recorded)
        return self._normalised_cache

    def display_normalise(self, values: np.ndarray) -> np.ndarray:
        """Normalize samples and clip them to the display gamut."""
        return np.clip(self.normalise(values), 0.0, 1.0).astype(np.float32, copy=False)

    def display_normalised(self) -> np.ndarray:
        """Return the loaded samples clipped to the display gamut."""
        return np.clip(self.normalised(), 0.0, 1.0).astype(np.float32, copy=False)

    def denormalise(self, values: np.ndarray | float) -> np.ndarray:
        """Map normalized values back onto this image's recorded scale."""
        data = np.asarray(values, dtype=np.float64)
        if self._normalise_mode in {"integer", "bounds"}:
            data = data * (self._normalise_max - self._normalise_min) + self._normalise_min
        elif self._normalise_mode in {"float", "raw"}:
            data = data * self._normalise_max
        return data


def resolve(path: str) -> tuple[object, str, int]:
    """Resolve a path while keeping FastAPI exceptions out of service workers."""
    try:
        resolved, file_type, index, _cache_key = _resolve_path_raw(path)
    except Exception as exc:
        if type(exc).__name__ == "HTTPException":
            detail = getattr(exc, "detail", str(exc))
            if getattr(exc, "status_code", None) == 404:
                raise FileNotFoundError(detail) from None
            raise ValueError(detail) from None
        raise
    return resolved, file_type, index


def _array_kind(array: np.ndarray) -> ImageKind:
    return "colour" if array.ndim == 3 and array.shape[0] == 3 else "mono"


def _normalisation_for(
    array: np.ndarray, bounds: tuple[float, float] | None = None
) -> tuple[ImageUnits, str, float, float, float | None]:
    if bounds is not None and (np.issubdtype(array.dtype, np.integer) or bounds != (0.0, 1.0)):
        lower, upper = bounds
        units: ImageUnits = "adu" if np.issubdtype(array.dtype, np.integer) else "float"
        return units, "bounds", lower, upper, upper
    if np.issubdtype(array.dtype, np.integer):
        info = np.iinfo(array.dtype)
        return "adu", "integer", float(info.min), float(info.max), float(info.max)
    maximum = float(np.nanmax(array)) if array.size else 1.0
    divisor = maximum if maximum > 1.0 else 1.0
    return "float", "float", 0.0, divisor, divisor


def _loaded(
    array: np.ndarray,
    *,
    pattern: PatternInfo | None = None,
    bounds: tuple[float, float] | None = None,
    white_level: float | None = None,
) -> LoadedImage:
    recorded = reshape_color(np.asarray(array))
    kind: ImageKind = (
        "mosaic" if pattern is not None and recorded.ndim == 2 else _array_kind(recorded)
    )
    if white_level is not None:
        units: ImageUnits = "adu"
        mode, lower, upper, full_scale = "raw", 0.0, float(white_level), float(white_level)
    else:
        units, mode, lower, upper, full_scale = _normalisation_for(recorded, bounds)
    return LoadedImage(
        kind=kind,
        recorded=recorded,
        units=units,
        pattern=pattern if kind == "mosaic" else None,
        width=int(recorded.shape[-1]),
        height=int(recorded.shape[-2]),
        white_level=white_level,
        full_scale=full_scale,
        _normalise_mode=mode,
        _normalise_min=lower,
        _normalise_max=upper,
    )


def _load_fits(source, hdu: int) -> LoadedImage:
    with fits.open(source, memmap=False) as hdul:
        if hdu < 0 or hdu >= len(hdul):
            raise ValueError(f"HDU index {hdu} out of range (file has {len(hdul)} HDUs)")
        target = hdul[hdu]
        if target.data is None:
            raise ValueError(f"HDU {hdu} contains no image data")
        recorded = reshape_color(np.array(target.data, copy=True))
        header = dict(target.header)
    pattern = pattern_from_fits(header, recorded.shape[-2]) if recorded.ndim == 2 else None
    return _loaded(recorded, pattern=pattern)


def _load_xisf(source, hdu: int) -> LoadedImage:
    recorded, bounds = xisf_io.load_image_samples(source, hdu)
    pattern = pattern_from_xisf(xisf_io.cfa_attributes(source, hdu)) if recorded.ndim == 2 else None
    if pattern is None and recorded.ndim == 2:
        header = {card["key"]: card["value"] for card in xisf_io.read_header(source, hdu)}
        pattern = pattern_from_fits(header, recorded.shape[-2])
    return _loaded(recorded, pattern=pattern, bounds=bounds)


def _load_pxiproject(source: Path, index: int) -> LoadedImage:
    recorded, bounds, cfa = pxiproject_io.load_image_samples(source, index)
    pattern = pattern_from_xisf(cfa) if recorded.ndim == 2 else None
    if pattern is None and recorded.ndim == 2:
        header = {card["key"]: card["value"] for card in pxiproject_io.read_header(source, index)}
        pattern = pattern_from_fits(header, recorded.shape[-2])
    return _loaded(recorded, pattern=pattern, bounds=bounds)


def _load_raw(source) -> LoadedImage:
    result = raw_io.read_raw_samples(source)
    recorded = result.rgb if result.rgb is not None else result.samples
    if recorded is None:
        raise raw_io.RawUnsupported("This camera raw file has no visible samples.")
    return _loaded(recorded, pattern=result.pattern, white_level=float(result.white_level))


def load_resolved(
    source,
    file_type: str,
    index: int = 0,
    hdu: int = 0,
    *,
    pattern_override: CfaPattern | None = None,
    reject_recorded_pattern: bool = False,
) -> LoadedImage:
    """Decode an already-resolved source and preserve recorded values."""
    if file_type == "pxiproject":
        image = _load_pxiproject(source, index)
    elif file_type == "fits":
        image = _load_fits(source, hdu)
    elif file_type == "xisf":
        image = _load_xisf(source, hdu)
    elif file_type == "raw":
        image = _load_raw(source)
    elif file_type == "float_tiff":
        image = _loaded(standard_io.load_image_data(source))
    elif file_type == "standard":
        image = _loaded(standard_io.load_image_as_array(source))
    else:
        raise ValueError(f"Unsupported file type: {file_type}")

    if pattern_override is not None:
        if image.kind != "mono" or image.pattern is not None:
            if reject_recorded_pattern:
                raise ValueError("A colour pattern is already recorded for this image")
        else:
            image.kind = "mosaic"
            image.pattern = PatternInfo(
                pattern_override,
                "user_choice",
                "Pattern selected for this view",
                ("Pattern selected for this view only",),
            )
    return image


def load_image(
    path: str, hdu: int = 0, *, pattern_override: CfaPattern | None = None
) -> LoadedImage:
    """Decode *path* once and preserve its recorded values and units."""
    source, file_type, index = resolve(path)
    return load_resolved(
        source,
        file_type,
        index,
        hdu,
        pattern_override=pattern_override,
    )


def _mosaic(image: LoadedImage, *, display: bool = False) -> Mosaic:
    if image.kind != "mosaic" or image.pattern is None:
        raise ValueError("The loaded image is not a mosaic")
    normalised = image.display_normalised() if display else image.normalised()
    return Mosaic(image.recorded, normalised, image.pattern)


def display_of(image: LoadedImage) -> np.ndarray:
    if image._display_cache is None:
        with image._display_lock:
            if image._display_cache is None:
                image._display_cache = (
                    display_rgb(_mosaic(image, display=True))
                    if image.kind == "mosaic"
                    else image.display_normalised()
                )
    return image._display_cache


def samples_of(image: LoadedImage) -> dict[str, np.ndarray]:
    if image.kind == "mosaic":
        return channel_samples(_mosaic(image))
    if image.kind == "colour":
        return {colour: image.recorded[index] for index, colour in enumerate("RGB")}
    return {"L": image.recorded}


def grey_of(image: LoadedImage) -> tuple[np.ndarray, int]:
    if image.kind == "mosaic":
        if image.pattern is not None and image.pattern.source == "user_choice":
            return image.normalised(), 1
        return measurement_grey(_mosaic(image))
    normalised = image.normalised()
    if image.kind == "colour":
        grey = LUM_R * normalised[0] + LUM_G * normalised[1] + LUM_B * normalised[2]
        return grey.astype(np.float64), 1
    return normalised.astype(np.float64), 1


def superpixels_of(image: LoadedImage) -> np.ndarray:
    return (
        colour_superpixels(_mosaic(image, display=True))
        if image.kind == "mosaic"
        else image.display_normalised()
    )
