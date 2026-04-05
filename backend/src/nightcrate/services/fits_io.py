"""FITS file I/O — loading image data, reading headers, listing extensions."""

from pathlib import Path
from typing import BinaryIO

import numpy as np
from astropy.io import fits

from nightcrate.services.fits_header_map import get_keyword_description
from nightcrate.services.imaging import normalize_to_01, reshape_color


def _hdu_index(hdul: fits.HDUList, hdu: int) -> fits.ImageHDU | fits.PrimaryHDU:
    if hdu < 0 or hdu >= len(hdul):
        raise ValueError(f"HDU index {hdu} out of range (file has {len(hdul)} HDUs)")
    return hdul[hdu]


def load_image_data(source: Path | BinaryIO, hdu: int = 0) -> np.ndarray:
    """Load image data as float64 array normalized to [0, 1].

    Returns shape (H, W) for mono or (3, H, W) for color.
    """
    with fits.open(source, memmap=False) as hdul:
        target = _hdu_index(hdul, hdu)
        if target.data is None:
            raise ValueError(f"HDU {hdu} contains no image data")
        data = normalize_to_01(target.data)
    return reshape_color(data)


def read_header(source: Path | BinaryIO, hdu: int = 0) -> list[dict]:
    """Return all header cards for the given HDU as {key, value, comment, description} dicts."""
    with fits.open(source, memmap=False) as hdul:
        target = _hdu_index(hdul, hdu)
        return [
            {
                "key": card.keyword,
                "value": str(card.value).strip("'\""),
                "comment": card.comment,
                "description": get_keyword_description(card.keyword),
            }
            for card in target.header.cards
        ]


STRUCTURAL_KEYWORDS = frozenset(
    {
        "SIMPLE",
        "NAXIS",
        "NAXIS1",
        "NAXIS2",
        "NAXIS3",
        "EXTEND",
        "BZERO",
        "BSCALE",
        "COMMENT",
        "HISTORY",
        "END",
        "",
        "BITPIX",
    }
)


def update_header(
    path: Path,
    hdu: int,
    operations: list[dict],
) -> list[dict]:
    """Apply edit operations to a FITS header and write in place.

    Each operation is a dict with:
      - op: "update" | "add" | "delete"
      - key: FITS keyword
      - value: new value (for update/add)
      - comment: optional comment (for update/add)

    Validates all operations before applying any. Returns the updated
    header cards in the same format as read_header().
    """
    with fits.open(path, mode="update", memmap=False) as hdul:
        target = _hdu_index(hdul, hdu)
        header = target.header

        # Validate all operations first (fail-fast)
        for op_dict in operations:
            op = op_dict["op"]
            key = op_dict["key"].upper()

            if key in STRUCTURAL_KEYWORDS or key.startswith("NAXIS"):
                raise ValueError(f"Cannot modify structural keyword: {key}")

            if op == "update":
                if key not in header:
                    raise ValueError(f"Keyword not found: {key}")
            elif op == "add":
                if key in header:
                    raise ValueError(f"Keyword already exists: {key}")
            elif op == "delete":
                if key not in header:
                    raise ValueError(f"Keyword not found: {key}")
            else:
                raise ValueError(f"Unknown operation: {op}")

        # Apply all operations
        for op_dict in operations:
            op = op_dict["op"]
            key = op_dict["key"].upper()

            if op == "update":
                value = op_dict.get("value", "")
                comment = op_dict.get("comment")
                if comment is not None:
                    header[key] = (value, comment)
                else:
                    header[key] = value
            elif op == "add":
                value = op_dict.get("value", "")
                comment = op_dict.get("comment", "")
                header.append((key, value, comment))
            elif op == "delete":
                del header[key]

        hdul.flush()

        # Return updated cards from the already-open HDU (avoids re-reading file)
        return [
            {
                "key": card.keyword,
                "value": str(card.value).strip("'\""),
                "comment": card.comment,
                "description": get_keyword_description(card.keyword),
            }
            for card in header.cards
        ]


def list_extensions(source: Path | BinaryIO) -> list[dict]:
    """Return a summary of all HDUs: index, name, type, has_image."""
    with fits.open(source, memmap=False) as hdul:
        result = []
        for i, hdu_obj in enumerate(hdul):
            has_image = (
                isinstance(hdu_obj, (fits.PrimaryHDU, fits.ImageHDU))
                and hdu_obj.data is not None
                and hdu_obj.data.ndim >= 2
            )
            result.append(
                {
                    "index": i,
                    "name": hdu_obj.name or f"HDU {i}",
                    "type": type(hdu_obj).__name__,
                    "has_image": has_image,
                }
            )
        return result
