"""Colour-filter-array patterns and file-format pattern rules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

PatternSource = Literal[
    "fits_bayerpat",
    "fits_colortyp",
    "xisf_cfa",
    "raw_file",
    "user_choice",
]


@dataclass(frozen=True)
class CfaPattern:
    rows: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.rows or not self.rows[0]:
            raise ValueError("A CFA pattern must not be empty")
        width = len(self.rows[0])
        if any(len(row) != width for row in self.rows):
            raise ValueError("Every CFA pattern row must have the same width")
        if any(colour not in "RGB" for row in self.rows for colour in row):
            raise ValueError("CFA patterns may contain only R, G and B")

    @property
    def width(self) -> int:
        return len(self.rows[0])

    @property
    def height(self) -> int:
        return len(self.rows)

    def colour_at(self, y: int, x: int) -> str:
        return self.rows[y % self.height][x % self.width]


@dataclass(frozen=True)
class PatternInfo:
    pattern: CfaPattern
    source: PatternSource
    detail: str
    assumptions: tuple[str, ...] = ()


def parse_bayer(text: str) -> CfaPattern | None:
    value = text.strip().upper()
    if value not in {"RGGB", "GRBG", "GBRG", "BGGR"}:
        return None
    return CfaPattern((value[:2], value[2:]))


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip().strip("'\""))
    except TypeError, ValueError:
        return default


def pattern_from_fits(header: Mapping[str, Any], height: int) -> PatternInfo | None:
    """Resolve a FITS CFA into the same top-down row order as its numpy data."""
    values = {str(key).upper(): value for key, value in header.items()}
    source: PatternSource
    key: str
    if parse_bayer(str(values.get("BAYERPAT", ""))) is not None:
        key = "BAYERPAT"
        source = "fits_bayerpat"
    elif parse_bayer(str(values.get("COLORTYP", ""))) is not None:
        key = "COLORTYP"
        source = "fits_colortyp"
    else:
        return None
    base = parse_bayer(str(values[key]))
    if base is None:  # guarded by the source selection above
        return None

    assumptions: list[str] = []
    dx = _integer(values.get("XBAYROFF"))
    dy = _integer(values.get("YBAYROFF"))
    software = str(values.get("SWCREATE", ""))
    if "sharpcap" in software.lower() and (dx or dy):
        dx = dy = 0
        assumptions.append("SharpCap offsets ignored; BAYERPAT is already corrected")

    raw_row_order = values.get("ROWORDER")
    if raw_row_order is None or not str(raw_row_order).strip():
        row_order = "TOP-DOWN"
        assumptions.append("ROWORDER missing; assumed TOP-DOWN")
    else:
        row_order = str(raw_row_order).strip().strip("'\"").upper()
        if row_order not in {"TOP-DOWN", "BOTTOM-UP"}:
            row_order = "TOP-DOWN"
            assumptions.append("ROWORDER unrecognised; assumed TOP-DOWN")

    def colour(row: int, column: int) -> str:
        source_row = row if row_order == "TOP-DOWN" else height - 1 - row
        return base.colour_at(source_row + dy, column + dx)

    pattern = CfaPattern(
        tuple(
            "".join(colour(row, column) for column in range(base.width))
            for row in range(base.height)
        )
    )
    return PatternInfo(pattern, source, key, tuple(assumptions))


def pattern_from_xisf(cfa: Mapping[str, str] | None) -> PatternInfo | None:
    if not cfa:
        return None
    try:
        width = int(cfa["width"])
        height = int(cfa["height"])
    except KeyError, TypeError, ValueError:
        return None
    text = cfa.get("pattern", "").strip().upper()
    if width <= 0 or height <= 0 or len(text) != width * height:
        return None
    if any(colour not in "RGB" for colour in text):
        return None
    rows = tuple(text[offset : offset + width] for offset in range(0, len(text), width))
    return PatternInfo(CfaPattern(rows), "xisf_cfa", cfa.get("name", "ColorFilterArray"))


def pattern_from_raw(raw_colors_visible: np.ndarray, color_desc: bytes) -> PatternInfo:
    colours = bytes(color_desc).decode("ascii", errors="ignore").rstrip("\x00")
    if not colours:
        raise ValueError("The raw file has no colour descriptions")
    indices = np.asarray(raw_colors_visible)
    if indices.ndim != 2 or indices.size == 0:
        raise ValueError("The raw file has no colour pattern")

    # Raw formats in scope use Bayer (2x2) or X-Trans (6x6). Compare strided
    # views instead of walking every sensor pixel in Python on a 50 MP frame.
    period_h, period_w = indices.shape
    for candidate_h in (1, 2, 6):
        if candidate_h <= indices.shape[0] and all(
            np.all(indices[offset::candidate_h] == indices[offset]) for offset in range(candidate_h)
        ):
            period_h = candidate_h
            break
    for candidate_w in (1, 2, 6):
        if candidate_w <= indices.shape[1] and all(
            np.all(indices[:, offset::candidate_w] == indices[:, offset : offset + 1])
            for offset in range(candidate_w)
        ):
            period_w = candidate_w
            break
    rows: list[str] = []
    for row in indices[:period_h, :period_w]:
        try:
            rows.append("".join(colours[int(index)] for index in row))
        except (IndexError, ValueError) as exc:
            raise ValueError("The raw file has an invalid colour pattern") from exc
    return PatternInfo(CfaPattern(tuple(rows)), "raw_file", "the raw file")
