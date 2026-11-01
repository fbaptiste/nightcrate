from __future__ import annotations

import bz2
import hashlib
import math
import os
import struct
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy_healpix import HEALPix

from .models import STAR_EPOCH, StarCatalog

HEADER_SIZE = 128
TITLE_SIZE = 48
EXPECTED_TITLE = "Siril Gaia DR3 astrometric extract"
RECORD_DTYPE = np.dtype(
    [
        ("ra", "<i4"),
        ("dec", "<i4"),
        ("pmra", "<i2"),
        ("pmdec", "<i2"),
        ("teff", "<u2"),
        ("g", "<i2"),
    ]
)
ANGLE_SCALE_DEG = 360.0 / (2**31 - 1)
CATALOG_EPOCH = 2016.0


class SirilFormatError(ValueError):
    pass


class ChecksumMismatch(ValueError):
    pass


@dataclass(frozen=True)
class SirilHeader:
    title: str
    release: int
    level: int
    catalog_type: int
    chunked: bool
    chunk_level: int
    chunk_pixel: int
    first_pixel: int
    last_pixel: int

    @property
    def cell_count(self) -> int:
        return 12 * 4**self.level


def _read_header(path: Path) -> SirilHeader:
    with path.open("rb") as stream:
        raw = stream.read(HEADER_SIZE)
    if len(raw) != HEADER_SIZE:
        raise SirilFormatError(f"Siril catalog header is {len(raw)} bytes; expected {HEADER_SIZE}")
    try:
        title = raw[:TITLE_SIZE].split(b"\0", 1)[0].decode("ascii")
    except UnicodeDecodeError as exc:
        raise SirilFormatError("Siril catalog title is not ASCII") from exc
    release, level, catalog_type, chunked, chunk_level = raw[48:53]
    chunk_pixel, first_pixel, last_pixel = struct.unpack_from("<III", raw, 53)
    header = SirilHeader(
        title,
        release,
        level,
        catalog_type,
        bool(chunked),
        chunk_level,
        chunk_pixel,
        first_pixel,
        last_pixel,
    )
    if header.title != EXPECTED_TITLE:
        raise SirilFormatError(
            f"unexpected Siril catalog title {header.title!r}; expected {EXPECTED_TITLE!r}"
        )
    if header.release != 3:
        raise SirilFormatError(f"unsupported Gaia release {header.release}; expected DR3 (3)")
    if not 0 <= header.level <= 12:
        raise SirilFormatError(f"invalid HEALPix level {header.level}")
    if header.catalog_type != 1:
        raise SirilFormatError("unsupported Siril catalog type; expected astrometric (1)")
    if header.chunked or any(
        (header.chunk_level, header.chunk_pixel, header.first_pixel, header.last_pixel)
    ):
        raise SirilFormatError(
            "chunked Siril catalogs are not supported; expected a monolithic file"
        )
    return header


def _radec_to_unit(ra: np.ndarray, dec: np.ndarray) -> np.ndarray:
    ra_r = np.radians(ra)
    dec_r = np.radians(dec)
    cos_dec = np.cos(dec_r)
    return np.column_stack((cos_dec * np.cos(ra_r), cos_dec * np.sin(ra_r), np.sin(dec_r)))


def _unit_to_radec(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    unit = vectors / np.linalg.norm(vectors, axis=1)[:, None]
    return np.degrees(np.arctan2(unit[:, 1], unit[:, 0])) % 360.0, np.degrees(np.arcsin(unit[:, 2]))


def _propagate(
    ra: np.ndarray, dec: np.ndarray, pmra: np.ndarray, pmdec: np.ndarray, epoch: float
) -> tuple[np.ndarray, np.ndarray]:
    vectors = _radec_to_unit(ra, dec)
    ra_r, dec_r = np.radians(ra), np.radians(dec)
    east = np.column_stack((-np.sin(ra_r), np.cos(ra_r), np.zeros(len(ra))))
    north = np.column_stack(
        (-np.sin(dec_r) * np.cos(ra_r), -np.sin(dec_r) * np.sin(ra_r), np.cos(dec_r))
    )
    scale = (epoch - CATALOG_EPOCH) * np.radians(1.0 / 3_600_000.0)
    moved = vectors + scale * (
        np.nan_to_num(pmra)[:, None] * east + np.nan_to_num(pmdec)[:, None] * north
    )
    return _unit_to_radec(moved)


def _consecutive_ranges(values: Iterable[int]) -> list[tuple[int, int]]:
    ordered = sorted({int(value) for value in values})
    if not ordered:
        return []
    result: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value != previous + 1:
            result.append((start, previous))
            start = value
        previous = value
    result.append((start, previous))
    return result


class SirilCatalog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.header = _read_header(self.path)
        self._index = np.memmap(
            self.path, mode="r", dtype="<u4", offset=HEADER_SIZE, shape=(self.header.cell_count,)
        )
        if len(self._index) > 1 and np.any(self._index[1:] < self._index[:-1]):
            self.close()
            raise SirilFormatError("Siril catalog index is not cumulative")
        self.record_count = int(self._index[-1]) if len(self._index) else 0
        data_offset = HEADER_SIZE + self.header.cell_count * 4
        expected = data_offset + self.record_count * RECORD_DTYPE.itemsize
        if self.path.stat().st_size != expected:
            self.close()
            raise SirilFormatError(f"Siril catalog size mismatch: expected {expected} bytes")
        self._records = np.memmap(
            self.path, mode="r", dtype=RECORD_DTYPE, offset=data_offset, shape=(self.record_count,)
        )
        self._healpix = HEALPix(nside=2**self.header.level, order="nested", frame="icrs")
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def cell_bounds(self, cell: int) -> tuple[int, int]:
        if not 0 <= cell < self.header.cell_count:
            raise IndexError(f"HEALPix cell {cell} is outside this catalog")
        return (0 if cell == 0 else int(self._index[cell - 1]), int(self._index[cell]))

    def query_cone(
        self, ra_deg: float, dec_deg: float, radius_deg: float, *, epoch: float = STAR_EPOCH
    ) -> StarCatalog:
        if self.closed:
            raise ValueError("Siril catalog is closed")
        if not 0 <= radius_deg <= 180:
            raise ValueError("cone radius must be between 0 and 180 degrees")
        cells = self._healpix.cone_search_lonlat(
            ra_deg * u.deg, dec_deg * u.deg, radius_deg * u.deg
        )
        blocks: list[np.ndarray] = []
        for first, last in _consecutive_ranges(cells):
            start, _ = self.cell_bounds(first)
            _, end = self.cell_bounds(last)
            if end > start:
                blocks.append(np.asarray(self._records[start:end]))
        if not blocks:
            return StarCatalog(np.empty(0), np.empty(0), np.empty(0, dtype=np.float32))
        records = np.concatenate(blocks) if len(blocks) > 1 else blocks[0]
        ra = records["ra"].astype(np.float64) * ANGLE_SCALE_DEG % 360.0
        dec = records["dec"].astype(np.float64) * ANGLE_SCALE_DEG
        if epoch != CATALOG_EPOCH:
            ra, dec = _propagate(
                ra,
                dec,
                records["pmra"].astype(np.float64),
                records["pmdec"].astype(np.float64),
                epoch,
            )
        center = _radec_to_unit(np.array([ra_deg]), np.array([dec_deg]))[0]
        keep = _radec_to_unit(ra, dec) @ center >= math.cos(math.radians(radius_deg))
        return StarCatalog(ra[keep], dec[keep], records["g"][keep].astype(np.float32) / 1000.0)

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        for name in ("_records", "_index"):
            mapping = getattr(getattr(self, name, None), "_mmap", None)
            if mapping is not None:
                mapping.close()
        self._closed = True

    def __enter__(self) -> SirilCatalog:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _sha256(path: Path, *, cancel: threading.Event | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            if cancel is not None and cancel.is_set():
                raise InterruptedError("operation cancelled")
            digest.update(chunk)
    return digest.hexdigest()


def decompress_and_verify(
    compressed: Path,
    output: Path,
    *,
    compressed_sha256: str,
    uncompressed_sha256: str,
    cancel: threading.Event | None = None,
    on_bytes: Callable[[int], None] | None = None,
) -> Path:
    compressed = Path(compressed)
    output = Path(output)
    output.unlink(missing_ok=True)
    if _sha256(compressed, cancel=cancel) != compressed_sha256:
        raise ChecksumMismatch("compressed SHA-256 mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    digest = hashlib.sha256()
    done = 0
    try:
        with bz2.open(compressed, "rb") as source, temporary.open("wb") as destination:
            while chunk := source.read(1024 * 1024):
                if cancel is not None and cancel.is_set():
                    raise InterruptedError("operation cancelled")
                destination.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if on_bytes is not None:
                    on_bytes(done)
        if digest.hexdigest() != uncompressed_sha256:
            raise ChecksumMismatch("uncompressed SHA-256 mismatch")
        os.replace(temporary, output)
        return output
    finally:
        temporary.unlink(missing_ok=True)
