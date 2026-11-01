from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy_healpix import HEALPix

from nightcrate.services.star_catalog.siril import (
    ANGLE_SCALE_DEG,
    EXPECTED_TITLE,
    HEADER_SIZE,
    RECORD_DTYPE,
)


@dataclass(frozen=True)
class SyntheticStar:
    ra: float
    dec: float
    pmra: float = 0.0
    pmdec: float = 0.0
    g: float = 10.0


def write_siril_catalog(path: Path, stars: list[SyntheticStar], level: int = 8) -> Path:
    hp = HEALPix(nside=2**level, order="nested", frame="icrs")
    cells = np.asarray(
        hp.lonlat_to_healpix(
            np.array([star.ra for star in stars]) * u.deg,
            np.array([star.dec for star in stars]) * u.deg,
        ),
        dtype=np.int64,
    )
    order = np.argsort(cells, kind="stable")
    cells = cells[order]
    rows = np.zeros(len(stars), dtype=RECORD_DTYPE)
    for output_index, source_index in enumerate(order):
        star = stars[int(source_index)]
        rows[output_index]["ra"] = round((star.ra % 360) / ANGLE_SCALE_DEG)
        rows[output_index]["dec"] = round(star.dec / ANGLE_SCALE_DEG)
        rows[output_index]["pmra"] = round(star.pmra)
        rows[output_index]["pmdec"] = round(star.pmdec)
        rows[output_index]["g"] = round(star.g * 1000)
    counts = np.bincount(cells, minlength=12 * 4**level)
    cumulative = np.cumsum(counts, dtype=np.uint32)
    header = bytearray(HEADER_SIZE)
    title = EXPECTED_TITLE.encode("ascii")
    header[: len(title)] = title
    header[48:53] = bytes((3, level, 1, 0, 0))
    struct.pack_into("<III", header, 53, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(header)
        cumulative.tofile(stream)
        rows.tofile(stream)
    return path
