"""Small generated camera-raw fixtures used by the raw-file tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile


def write_cfa_dng(
    path: Path,
    samples: np.ndarray,
    pattern: str = "RGGB",
    *,
    black: int = 512,
    white: int = 16383,
    exif: dict[str, str] | None = None,
    makernote: dict[str, str] | None = None,
) -> Path:
    """Write a minimal, LibRaw-readable CFA DNG and optional EXIF metadata."""
    import exiv2

    pattern = pattern.strip().upper()
    if pattern not in {"RGGB", "GRBG", "GBRG", "BGGR"}:
        raise ValueError(f"Unsupported generated Bayer pattern: {pattern}")
    colour_indices = {"R": 0, "G": 1, "B": 2}
    cfa = tuple(colour_indices[colour] for colour in pattern)
    data = np.asarray(samples, dtype=np.uint16)
    if data.ndim != 2:
        raise ValueError("Generated CFA samples must be two-dimensional")
    extratags = [
        (50706, "B", 4, (1, 4, 0, 0), False),  # DNGVersion
        (50707, "B", 4, (1, 3, 0, 0), False),  # DNGBackwardVersion
        (50708, "s", 0, "NightCrate Generated Camera", False),
        (33421, "H", 2, (2, 2), False),
        (33422, "B", 4, cfa, False),
        (50714, "H", 1, black, False),
        (50717, "I", 1, white, False),
        (271, "s", 0, "NightCrate", False),
        (272, "s", 0, "Generated DNG", False),
    ]
    tifffile.imwrite(path, data, photometric=32803, metadata=None, extratags=extratags)

    values = {**(exif or {}), **(makernote or {})}
    if values:
        image = exiv2.ImageFactory.open(str(path))
        image.readMetadata()
        metadata = image.exifData()
        for key, value in values.items():
            metadata[key] = value
        image.setExifData(metadata)
        image.writeMetadata()
    return path
