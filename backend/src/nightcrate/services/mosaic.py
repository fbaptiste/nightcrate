"""Pure conversions from recorded colour mosaics to consumer-specific forms."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from nightcrate.services.cfa import CfaPattern, PatternInfo


@dataclass(frozen=True)
class Mosaic:
    recorded: np.ndarray
    normalised: np.ndarray
    pattern: PatternInfo

    def __post_init__(self) -> None:
        if self.recorded.ndim != 2 or self.normalised.shape != self.recorded.shape:
            raise ValueError("A mosaic needs matching two-dimensional sample arrays")


def _mask(shape: tuple[int, int], pattern: CfaPattern, colour: str) -> np.ndarray:
    rows = np.arange(shape[0])[:, None] % pattern.height
    columns = np.arange(shape[1])[None, :] % pattern.width
    tile = np.array([list(row) for row in pattern.rows])
    return tile[rows, columns] == colour


def display_rgb(mosaic: Mosaic) -> np.ndarray:
    """Interpolate each colour by normalized convolution, for display only."""
    kernel = np.ones((5, 5), dtype=np.float32)
    planes: list[np.ndarray] = []
    data = np.asarray(mosaic.normalised, dtype=np.float32)
    for colour in "RGB":
        mask = _mask(data.shape, mosaic.pattern.pattern, colour).astype(np.float32)
        numerator = ndimage.convolve(data * mask, kernel, mode="nearest")
        denominator = ndimage.convolve(mask, kernel, mode="nearest")
        plane = np.divide(
            numerator,
            denominator,
            out=np.zeros_like(numerator, dtype=np.float32),
            where=denominator > 0,
        )
        planes.append(plane)
    return np.stack(planes).astype(np.float32, copy=False)


def channel_samples(mosaic: Mosaic) -> dict[str, np.ndarray]:
    return {
        colour: mosaic.recorded[_mask(mosaic.recorded.shape, mosaic.pattern.pattern, colour)]
        for colour in "RGB"
    }


def block_size(pattern: CfaPattern) -> int:
    if (pattern.height, pattern.width) == (2, 2):
        return 2
    if (pattern.height, pattern.width) == (6, 6):
        return 3
    raise ValueError(f"Unsupported CFA repeat size: {pattern.width}x{pattern.height}")


def _block_colour_means(data: np.ndarray, pattern: CfaPattern) -> np.ndarray:
    size = block_size(pattern)
    height = data.shape[0] // size
    width = data.shape[1] // size
    cropped = np.asarray(data[: height * size, : width * size], dtype=np.float32)
    blocks = cropped.reshape(height, size, width, size).transpose(0, 2, 1, 3)
    colour_planes: list[np.ndarray] = []
    for colour in "RGB":
        mask = _mask(cropped.shape, pattern, colour)
        block_mask = mask.reshape(height, size, width, size).transpose(0, 2, 1, 3)
        count = block_mask.sum(axis=(2, 3))
        total = np.where(block_mask, blocks, 0.0).sum(axis=(2, 3))
        if np.any(count == 0):
            raise ValueError(f"A {size}x{size} CFA block contains no {colour} samples")
        colour_planes.append((total / count).astype(np.float32))
    return np.stack(colour_planes)


def measurement_grey(mosaic: Mosaic) -> tuple[np.ndarray, int]:
    size = block_size(mosaic.pattern.pattern)
    channels = _block_colour_means(mosaic.normalised, mosaic.pattern.pattern)
    return channels.mean(axis=0, dtype=np.float32), size


def colour_superpixels(mosaic: Mosaic) -> np.ndarray:
    return _block_colour_means(mosaic.normalised, mosaic.pattern.pattern)
