"""FITS file reading and rendering logic."""

import io
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image


def _hdu_index(hdul: fits.HDUList, hdu: int) -> fits.ImageHDU | fits.PrimaryHDU:
    if hdu < 0 or hdu >= len(hdul):
        raise ValueError(f"HDU index {hdu} out of range (file has {len(hdul)} HDUs)")
    return hdul[hdu]


def read_header(file_path: Path, hdu: int = 0) -> list[dict]:
    """Return all header cards for the given HDU as a list of dicts."""
    with fits.open(file_path, memmap=False) as hdul:
        target = _hdu_index(hdul, hdu)
        cards = []
        for card in target.header.cards:
            cards.append({
                "key": card.keyword,
                "value": str(card.value),
                "comment": card.comment,
            })
        return cards


def list_hdus(file_path: Path) -> list[dict]:
    """Return a summary of all HDUs: index, name, type, and whether it has image data."""
    with fits.open(file_path, memmap=False) as hdul:
        result = []
        for i, hdu_obj in enumerate(hdul):
            has_image = (
                isinstance(hdu_obj, (fits.PrimaryHDU, fits.ImageHDU))
                and hdu_obj.data is not None
                and hdu_obj.data.ndim >= 2
            )
            result.append({
                "index": i,
                "name": hdu_obj.name or f"HDU {i}",
                "type": type(hdu_obj).__name__,
                "has_image": has_image,
            })
        return result


def render_image_png(file_path: Path, hdu: int = 0) -> bytes:
    """Read image data from the given HDU and return a PNG as bytes.

    Applies linear min/max scaling: maps the actual pixel range to [0, 255].
    No astronomical stretch is applied — this is the simplest possible display.
    """
    with fits.open(file_path, memmap=False) as hdul:
        target = _hdu_index(hdul, hdu)

        if target.data is None:
            raise ValueError(f"HDU {hdu} contains no image data")

        data = np.array(target.data, dtype=np.float64)

        # Collapse to 2D if needed (e.g. RGB cube: take first plane)
        while data.ndim > 2:
            data = data[0]

        data_min = data.min()
        data_max = data.max()

        if data_max == data_min:
            # Uniform image — render as mid-grey
            scaled = np.full(data.shape, 128, dtype=np.uint8)
        else:
            scaled = ((data - data_min) / (data_max - data_min) * 255).astype(np.uint8)

        img = Image.fromarray(scaled, mode="L")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
