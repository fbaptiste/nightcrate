from __future__ import annotations

import gc
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import astropy.units as u
import numpy as np
from astropy_healpix import HEALPix
from scipy.spatial import cKDTree

from .models import STAR_EPOCH, StarCatalog
from .ranges import LayerSpec
from .siril import ANGLE_SCALE_DEG, CATALOG_EPOCH, SirilCatalog, _propagate
from .store import SIRIL_SOURCE

try:
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None  # type: ignore[assignment]

MAGIC = b"NCQIDX2\0"
INDEX_FORMAT = "nightcrate-star-index"
INDEX_FORMAT_VERSION = 1
VERSION = INDEX_FORMAT_VERSION
HEADER_SIZE = 16_384

STAR_DTYPE = np.dtype([("ra", "<f4"), ("dec", "<f4")])
BUILD_STAR_DTYPE = np.dtype([("ra", "<f4"), ("dec", "<f4"), ("g", "<f2")])
QUAD_DTYPE = np.dtype(
    [
        ("key", "<u4"),
        ("code", "<u2", (4,)),
        ("refs", "<u4", (2,)),
        ("tile", "<u4"),
    ]
)
TILE_ENTRY_DTYPE = np.dtype([("key", "<u4"), ("start", "<u8"), ("count", "<u4")])

CODE_MIN = -0.25
CODE_MAX = 1.25
CODE_SPAN = CODE_MAX - CODE_MIN
MAX_CODE_TOLERANCE = 0.010
CODE_BINS = int(math.ceil(CODE_SPAN / (2.0 * MAX_CODE_TOLERANCE)))
CODE_QUANTUM = CODE_SPAN / 65535.0
KEY_SPACE = CODE_BINS**4
PARTITIONS = 256


BandSpec = LayerSpec


def radec_to_unit(ra: np.ndarray, dec: np.ndarray) -> np.ndarray:
    ra_r = np.radians(ra)
    dec_r = np.radians(dec)
    cos_dec = np.cos(dec_r)
    return np.column_stack((cos_dec * np.cos(ra_r), cos_dec * np.sin(ra_r), np.sin(dec_r)))


def unit_to_radec(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    unit = vectors / np.linalg.norm(vectors, axis=1)[:, None]
    return np.degrees(np.arctan2(unit[:, 1], unit[:, 0])) % 360.0, np.degrees(np.arcsin(unit[:, 2]))


def allocated_memory_mb() -> None:
    return None


def _peak_rss_mb() -> float:
    if resource is None:
        return 0.0
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024**2 if sys.platform == "darwin" else 1024)


def _quantize(codes: np.ndarray) -> np.ndarray:
    scaled = np.clip((np.asarray(codes) - CODE_MIN) / CODE_SPAN, 0.0, 1.0)
    return np.rint(scaled * 65535.0).astype("<u2")


def _decode_codes(codes: np.ndarray) -> np.ndarray:
    return np.asarray(codes, dtype=np.float64) * CODE_QUANTUM + CODE_MIN


def _code_keys(codes: np.ndarray) -> np.ndarray:
    cells = np.floor((np.asarray(codes) - CODE_MIN) / (2 * MAX_CODE_TOLERANCE))
    cells = np.clip(cells, 0, CODE_BINS - 1).astype(np.uint32)
    key = cells[:, 0]
    for axis in range(1, 4):
        key = key * CODE_BINS + cells[:, axis]
    return key.astype(np.uint32)


def _probe_keys(codes: np.ndarray) -> np.ndarray:
    position = (np.asarray(codes) - CODE_MIN) / (2 * MAX_CODE_TOLERANCE)
    primary = np.floor(position).astype(np.int64)
    secondary = primary + np.where(position - primary < 0.5, -1, 1)
    primary = np.clip(primary, 0, CODE_BINS - 1)
    secondary = np.clip(secondary, 0, CODE_BINS - 1)
    result = np.empty((len(codes), 16), dtype=np.uint32)
    for mask in range(16):
        chosen = np.column_stack(
            [secondary[:, axis] if mask & (1 << axis) else primary[:, axis] for axis in range(4)]
        )
        key = chosen[:, 0]
        for axis in range(1, 4):
            key = key * CODE_BINS + chosen[:, axis]
        result[:, mask] = key.astype(np.uint32)
    return result


def _tile_rows_from_catalogs(
    catalogs: Iterable[tuple[int, StarCatalog]], spec: BandSpec
) -> tuple[np.ndarray, np.ndarray]:
    blocks: list[np.ndarray] = []
    entries: list[tuple[int, int, int]] = []
    offset = 0
    for tile, catalog in catalogs:
        if not len(catalog):
            continue
        keep = np.flatnonzero(catalog.g <= spec.magnitude_limit)
        if len(keep) > spec.stars_per_cell:
            keep = keep[np.argsort(catalog.g[keep], kind="stable")[: spec.stars_per_cell]]
        if not len(keep):
            continue
        rows = np.empty(len(keep), dtype=BUILD_STAR_DTYPE)
        rows["ra"] = catalog.ra[keep].astype(np.float32)
        rows["dec"] = catalog.dec[keep].astype(np.float32)
        rows["g"] = catalog.g[keep].astype(np.float16)
        blocks.append(rows)
        entries.append((int(tile), offset, len(rows)))
        offset += len(rows)
    stars = np.concatenate(blocks) if blocks else np.empty(0, dtype=BUILD_STAR_DTYPE)
    return stars, np.asarray(entries, dtype=TILE_ENTRY_DTYPE)


def _select_siril_stars(
    source: SirilCatalog,
    spec: BandSpec,
    epoch: float,
    region: tuple[float, float, float] | None,
    chunk: int = 500_000,
    on_progress: Callable[[float], None] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """One sequential catalogue pass followed by an exact per-cell top-k."""
    hp = HEALPix(nside=2**spec.healpix_level, order="nested", frame="icrs")
    allowed: np.ndarray | None = None
    if region is not None:
        allowed = np.sort(
            np.asarray(
                hp.cone_search_lonlat(region[0] * u.deg, region[1] * u.deg, region[2] * u.deg),
                dtype=np.int64,
            )
        )
    parts: list[np.ndarray] = []
    row_dtype = np.dtype([("tile", "<u4"), *BUILD_STAR_DTYPE.descr])
    for start in range(0, source.record_count, chunk):
        if on_progress is not None:
            on_progress(min(1.0, (start + chunk) / max(1, source.record_count)))
        records = np.asarray(source._records[start : start + chunk])  # noqa: SLF001
        records = records[records["g"].astype(np.float32) <= spec.magnitude_limit * 1000.0]
        if not len(records):
            continue
        ra = (records["ra"].astype(np.float64) * ANGLE_SCALE_DEG) % 360.0
        dec = records["dec"].astype(np.float64) * ANGLE_SCALE_DEG
        if epoch != CATALOG_EPOCH:
            ra, dec = _propagate(
                ra,
                dec,
                records["pmra"].astype(np.float64),
                records["pmdec"].astype(np.float64),
                epoch,
            )
        tile = np.asarray(hp.lonlat_to_healpix(ra * u.deg, dec * u.deg), dtype=np.uint32)
        if allowed is not None:
            chosen = np.isin(tile, allowed)
            tile, ra, dec, records = (
                tile[chosen],
                ra[chosen],
                dec[chosen],
                records[chosen],
            )
        if not len(tile):
            continue
        mag = records["g"].astype(np.float32) / 1000.0
        order = np.lexsort((mag, tile))
        ordered_tile = tile[order]
        starts = np.flatnonzero(np.r_[True, ordered_tile[1:] != ordered_tile[:-1]])
        counts = np.diff(np.r_[starts, len(order)])
        rank = np.arange(len(order)) - np.repeat(starts, counts)
        order = order[rank < spec.stars_per_cell]
        rows = np.empty(len(order), dtype=row_dtype)
        rows["tile"] = tile[order]
        rows["ra"] = ra[order].astype(np.float32)
        rows["dec"] = dec[order].astype(np.float32)
        rows["g"] = mag[order].astype(np.float16)
        parts.append(rows)
    if not parts:
        return np.empty(0, dtype=BUILD_STAR_DTYPE), np.empty(0, dtype=TILE_ENTRY_DTYPE)
    rows = np.concatenate(parts)
    rows = rows[np.lexsort((rows["g"], rows["tile"]))]
    starts = np.flatnonzero(np.r_[True, rows["tile"][1:] != rows["tile"][:-1]])
    counts = np.diff(np.r_[starts, len(rows)])
    rank = np.arange(len(rows)) - np.repeat(starts, counts)
    rows = rows[rank < spec.stars_per_cell]
    tile_keys, tile_starts, tile_counts = np.unique(
        rows["tile"], return_index=True, return_counts=True
    )
    entries = np.empty(len(tile_keys), dtype=TILE_ENTRY_DTYPE)
    entries["key"] = tile_keys
    entries["start"] = tile_starts
    entries["count"] = tile_counts
    stars = np.empty(len(rows), dtype=BUILD_STAR_DTYPE)
    for name in ("ra", "dec", "g"):
        stars[name] = rows[name]
    return stars, entries


def _brightest_columns(
    values: np.ndarray, valid: np.ndarray, count: int
) -> tuple[np.ndarray, np.ndarray]:
    sentinel = np.iinfo(np.uint32).max
    ranked = np.where(valid, values, sentinel)
    columns = np.argsort(ranked, axis=1, kind="stable")[:, :count]
    chosen = np.take_along_axis(ranked, columns, axis=1)
    return columns, chosen != sentinel


def _encode_fixed_baselines(points: np.ndarray, refs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a, b = points[:, 0], points[:, 1]
    direction = b - a
    diameter2 = np.einsum("ij,ij->i", direction, direction)
    delta = points[:, 2:] - a[:, None, :]
    along = np.einsum("qki,qi->qk", delta, direction) / diameter2[:, None]
    cross = (
        direction[:, None, 0] * delta[:, :, 1] - direction[:, None, 1] * delta[:, :, 0]
    ) / diameter2[:, None]
    values = np.stack((along + cross, along - cross), axis=2)
    swap_cd = (values[:, 1, 0] < values[:, 0, 0]) | (
        (values[:, 1, 0] == values[:, 0, 0]) & (values[:, 1, 1] < values[:, 0, 1])
    )
    values[swap_cd] = values[swap_cd, ::-1]
    reverse = values[:, 0, 0] + values[:, 1, 0] > 1.0
    values[reverse] = 1.0 - values[reverse]
    swap_after = (values[:, 1, 0] < values[:, 0, 0]) | (
        (values[:, 1, 0] == values[:, 0, 0]) & (values[:, 1, 1] < values[:, 0, 1])
    )
    values[swap_after] = values[swap_after, ::-1]
    refs = refs.copy()
    refs[reverse] = refs[reverse, ::-1]
    return values.reshape(-1, 4), refs


def _quad_chunks(
    stars: np.ndarray,
    spec: BandSpec,
    workers: int,
    anchor_chunk: int = 25_000,
    on_progress: Callable[[float], None] | None = None,
) -> Iterable[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Yield brightness-anchored, whole-sky quads."""
    if len(stars) < 4:
        return
    xyz = radec_to_unit(stars["ra"].astype(np.float64), stars["dec"].astype(np.float64))
    tree = cKDTree(xyz, compact_nodes=True, balanced_tree=True)
    brightness = np.argsort(stars["g"], kind="stable").astype(np.uint32, copy=False)
    rank = np.empty(len(stars), dtype=np.uint32)
    rank[brightness] = np.arange(len(stars), dtype=np.uint32)
    low = 2.0 * math.sin(math.radians(spec.min_diameter_deg) / 2.0)
    high = 2.0 * math.sin(math.radians(spec.max_diameter_deg) / 2.0)
    for begin in range(0, len(brightness), anchor_chunk):
        anchors = brightness[begin : begin + anchor_chunk]
        if on_progress is not None:
            on_progress((begin + len(anchors)) / len(brightness))
        distances, neighbours = tree.query(
            xyz[anchors],
            k=min(24, len(stars)),
            distance_upper_bound=high,
            workers=workers,
        )
        distances = np.asarray(distances).reshape(len(anchors), -1)
        neighbours = np.asarray(neighbours).reshape(len(anchors), -1)
        in_range = neighbours < len(stars)
        safe = np.minimum(neighbours, len(stars) - 1)
        in_range &= distances >= low
        in_range &= rank[safe] > rank[anchors, None]
        columns, present = _brightest_columns(rank[safe], in_range, spec.quads_per_star)
        chosen = np.take_along_axis(safe, columns, axis=1)
        a = np.repeat(anchors, spec.quads_per_star)[present.ravel()]
        b = chosen.ravel()[present.ravel()]
        if not len(a):
            continue
        midpoint = xyz[a] + xyz[b]
        midpoint /= np.linalg.norm(midpoint, axis=1)[:, None]
        half_radius = np.linalg.norm(xyz[a] - midpoint, axis=1)
        inner_dist, inner_ids = tree.query(
            midpoint,
            k=min(24, len(stars)),
            distance_upper_bound=float(half_radius.max()) + 1e-12,
            workers=workers,
        )
        inner_dist = np.asarray(inner_dist).reshape(len(a), -1)
        inner_ids = np.asarray(inner_ids).reshape(len(a), -1)
        inner_valid = inner_ids < len(stars)
        inner_safe = np.minimum(inner_ids, len(stars) - 1)
        inner_valid &= inner_dist <= half_radius[:, None] + 1e-12
        inner_valid &= (inner_safe != a[:, None]) & (inner_safe != b[:, None])
        inner_columns, inner_present = _brightest_columns(rank[inner_safe], inner_valid, 2)
        cd = np.take_along_axis(inner_safe, inner_columns, axis=1)
        complete = inner_present.all(axis=1)
        if not np.any(complete):
            continue
        a, b, cd, midpoint = (
            a[complete],
            b[complete],
            cd[complete],
            midpoint[complete],
        )
        ids = np.column_stack((a, b, cd)).astype(np.uint32)
        east = np.column_stack((-midpoint[:, 1], midpoint[:, 0], np.zeros(len(midpoint))))
        norm = np.linalg.norm(east, axis=1)
        pole = norm < 1e-12
        east[pole] = np.array([1.0, 0.0, 0.0])
        norm[pole] = 1.0
        east /= norm[:, None]
        north = np.cross(midpoint, east)
        directions = xyz[ids]
        denominator = np.einsum("qki,qi->qk", directions, midpoint)
        x = np.einsum("qki,qi->qk", directions, east) / denominator
        y = np.einsum("qki,qi->qk", directions, north) / denominator
        code, refs = _encode_fixed_baselines(np.stack((x, y), axis=2), ids[:, :2])
        valid_code = np.all((code >= CODE_MIN) & (code <= CODE_MAX), axis=1)
        if np.any(valid_code):
            center_ra, center_dec = unit_to_radec(midpoint[valid_code])
            hp = HEALPix(nside=2**spec.healpix_level, order="nested", frame="icrs")
            owners = np.asarray(
                hp.lonlat_to_healpix(center_ra * u.deg, center_dec * u.deg),
                dtype=np.uint32,
            )
            yield code[valid_code], refs[valid_code], owners


def write_band(
    path: Path,
    spec: BandSpec,
    tile_catalogs: Iterable[tuple[int, StarCatalog]] | None,
    *,
    source_identity: dict[str, object],
    epoch: float = 2026.0,
    workers: int = 1,
    region: tuple[float, float, float] | None = None,
    started: float | None = None,
    selected: tuple[np.ndarray, np.ndarray] | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> dict[str, object]:
    """Build one independently verifiable NightCrate v5 index layer."""
    started = time.perf_counter() if started is None else started
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if selected is None:
        if tile_catalogs is None:
            raise ValueError("tile catalogs or a selected star table is required")
        stars, tile_entries = _tile_rows_from_catalogs(tile_catalogs, spec)
    else:
        stars, tile_entries = selected
    if not len(stars):
        raise ValueError("no index stars selected")
    allocation_samples = [allocated_memory_mb()]
    with tempfile.TemporaryDirectory(dir=path.parent, prefix=f".{path.name}.build-") as temp_name:
        temp = Path(temp_name)
        partition_paths = [temp / f"part-{index:03d}.bin" for index in range(PARTITIONS)]
        for item in partition_paths:
            item.touch()
        quad_count = 0
        for codes, refs, owners in _quad_chunks(
            stars,
            spec,
            workers,
            on_progress=(None if on_progress is None else lambda value: on_progress(0.7 * value)),
        ):
            rows = np.empty(len(codes), dtype=QUAD_DTYPE)
            rows["code"] = _quantize(codes)
            rows["key"] = _code_keys(_decode_codes(rows["code"]))
            rows["refs"] = refs
            rows["tile"] = owners
            partition = np.minimum(
                PARTITIONS - 1,
                rows["key"].astype(np.uint64) * PARTITIONS // KEY_SPACE,
            )
            # One partition file open at a time: macOS allows a process 256.
            for value in np.unique(partition):
                with partition_paths[int(value)].open("ab") as stream:
                    rows[partition == value].tofile(stream)
            quad_count += len(rows)
            allocation_samples.append(allocated_memory_mb())
        quad_spool = temp / "quads.bin"
        with quad_spool.open("wb") as output:
            for partition_index, partition_path in enumerate(partition_paths):
                rows = np.fromfile(partition_path, dtype=QUAD_DTYPE)
                if len(rows):
                    rows = rows[np.argsort(rows["key"], kind="stable")]
                    rows.tofile(output)
                allocation_samples.append(allocated_memory_mb())
                if on_progress is not None:
                    on_progress(0.7 + 0.25 * (partition_index + 1) / PARTITIONS)
        tile_offset = HEADER_SIZE
        star_offset = tile_offset + len(tile_entries) * TILE_ENTRY_DTYPE.itemsize
        quad_offset = star_offset + len(stars) * STAR_DTYPE.itemsize
        elapsed = time.perf_counter() - started
        measured = [value for value in allocation_samples if value is not None]
        metadata: dict[str, object] = {
            "format": INDEX_FORMAT,
            "version": VERSION,
            "epoch": epoch,
            "source": source_identity,
            "band": asdict(spec),
            "counts": {
                "tiles": len(tile_entries),
                "stars": len(stars),
                "quads": quad_count,
            },
            "layout": {
                "header_size": HEADER_SIZE,
                "tile_offset": tile_offset,
                "tile_itemsize": TILE_ENTRY_DTYPE.itemsize,
                "star_offset": star_offset,
                "star_itemsize": STAR_DTYPE.itemsize,
                "quad_offset": quad_offset,
                "quad_itemsize": QUAD_DTYPE.itemsize,
                "code_range": [CODE_MIN, CODE_MAX],
                "code_bins": CODE_BINS,
                "max_code_tolerance": MAX_CODE_TOLERANCE,
            },
            "build": {
                "workers": workers,
                "region": list(region) if region else None,
                "seconds": elapsed,
                "peak_rss_mb": _peak_rss_mb(),
                "allocated_peak_sampled_mb": max(measured) if measured else None,
                "quad_scope": "whole selected sky",
            },
        }
        encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) + 12 > HEADER_SIZE:
            raise ValueError("index metadata exceeds fixed header")
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("wb") as output:
                output.write(MAGIC)
                output.write(struct.pack("<I", len(encoded)))
                output.write(encoded)
                output.write(b"\0" * (HEADER_SIZE - output.tell()))
                tile_entries.tofile(output)
                packed = np.empty(len(stars), dtype=STAR_DTYPE)
                packed["ra"], packed["dec"] = stars["ra"], stars["dec"]
                packed.tofile(output)
                with quad_spool.open("rb") as source:
                    shutil.copyfileobj(source, output, 8 * 1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        if on_progress is not None:
            on_progress(1.0)
    metadata["bytes"] = path.stat().st_size
    return metadata


def _entry_rows(entries: np.ndarray, keys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    positions = np.searchsorted(entries["key"], keys)
    valid = positions < len(entries)
    indices = np.flatnonzero(valid)
    if len(indices):
        valid[indices] &= entries["key"][positions[indices]] == keys[indices]
    return positions, valid


class IndexLayer:
    """Read-only memory-mapped NightCrate index layer."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        with self.path.open("rb") as stream:
            if stream.read(8) != MAGIC:
                raise ValueError(f"{self.path} is not a NightCrate quad index")
            length = struct.unpack("<I", stream.read(4))[0]
            if length > HEADER_SIZE - 12:
                raise ValueError("invalid index metadata length")
            self.metadata = json.loads(stream.read(length))
        self.version = int(self.metadata.get("version", -1))
        if self.metadata.get("format") != INDEX_FORMAT or self.version != INDEX_FORMAT_VERSION:
            raise ValueError(f"unsupported index version {self.version}")
        counts, layout = self.metadata["counts"], self.metadata["layout"]
        star_dtype, quad_dtype = STAR_DTYPE, QUAD_DTYPE
        expected = int(layout["quad_offset"]) + int(counts["quads"]) * quad_dtype.itemsize
        if self.path.stat().st_size != expected:
            raise ValueError("index file size does not match header counts")
        self.stars = np.memmap(
            self.path,
            mode="r",
            dtype=star_dtype,
            offset=int(layout["star_offset"]),
            shape=(int(counts["stars"]),),
        )
        self.quads = np.memmap(
            self.path,
            mode="r",
            dtype=quad_dtype,
            offset=int(layout["quad_offset"]),
            shape=(int(counts["quads"]),),
        )
        band = dict(self.metadata["band"])
        band.setdefault("magnitude_limit", 99.0)
        self.spec = BandSpec(**band)
        self.tile_entries: np.memmap | None = None
        self.tile_entries = np.memmap(
            self.path,
            mode="r",
            dtype=TILE_ENTRY_DTYPE,
            offset=int(layout["tile_offset"]),
            shape=(int(counts["tiles"]),),
        )
        self._closed = False
        self._healpix = HEALPix(nside=2**self.spec.healpix_level, order="nested", frame="icrs")

    def baseline_radec(self, indices: np.ndarray | list[int]) -> np.ndarray:
        rows = self.quads[np.asarray(indices, dtype=np.int64)]
        return self.stars[np.asarray(rows["refs"], dtype=np.int64)]

    def quad_radec(self, indices: np.ndarray | list[int]) -> np.ndarray:
        """Reconstruct A/B/C/D positions from the normalized code."""
        selected = np.asarray(indices, dtype=np.int64)
        rows = self.quads[selected]
        ab = self.stars[rows["refs"]]
        vectors = radec_to_unit(
            ab["ra"].astype(np.float64).reshape(-1),
            ab["dec"].astype(np.float64).reshape(-1),
        ).reshape(-1, 2, 3)
        midpoint = vectors.sum(axis=1)
        midpoint /= np.linalg.norm(midpoint, axis=1)[:, None]
        east = np.column_stack((-midpoint[:, 1], midpoint[:, 0], np.zeros(len(midpoint))))
        norm = np.linalg.norm(east, axis=1)
        pole = norm < 1e-12
        east[pole], norm[pole] = np.array([1.0, 0.0, 0.0]), 1.0
        east /= norm[:, None]
        north = np.cross(midpoint, east)
        denominator = np.einsum("qki,qi->qk", vectors, midpoint)
        ab_x = np.einsum("qki,qi->qk", vectors, east) / denominator
        ab_y = np.einsum("qki,qi->qk", vectors, north) / denominator
        ab_xy = np.stack((ab_x, ab_y), axis=2)
        code = _decode_codes(rows["code"]).reshape(-1, 2, 2)
        along = 0.5 * (code[:, :, 0] + code[:, :, 1])
        cross = 0.5 * (code[:, :, 0] - code[:, :, 1])
        direction = ab_xy[:, 1] - ab_xy[:, 0]
        perpendicular = np.column_stack((-direction[:, 1], direction[:, 0]))
        cd_xy = (
            ab_xy[:, :1]
            + along[:, :, None] * direction[:, None]
            + cross[:, :, None] * perpendicular[:, None]
        )
        xy = np.concatenate((ab_xy, cd_xy), axis=1)
        sky_vectors = (
            midpoint[:, None] + xy[:, :, :1] * east[:, None] + xy[:, :, 1:] * north[:, None]
        )
        ra, dec = unit_to_radec(sky_vectors.reshape(-1, 3))
        result = np.empty((len(rows), 4), dtype=STAR_DTYPE)
        result["ra"] = ra.reshape(-1, 4).astype(np.float32)
        result["dec"] = dec.reshape(-1, 4).astype(np.float32)
        return result

    def query_codes(
        self,
        codes: np.ndarray,
        tolerance: float | np.ndarray,
        maximum: int,
        tiles: set[int] | None = None,
    ) -> list[tuple[float, int, int]]:
        values = np.atleast_2d(np.asarray(codes, dtype=np.float64))
        if not len(values) or not len(self.quads):
            return []
        tolerances = np.broadcast_to(np.asarray(tolerance, dtype=np.float64), (len(values),))
        flat = _probe_keys(values).ravel()
        keys = self.quads["key"]
        lo = np.searchsorted(keys, flat, side="left")
        hi = np.searchsorted(keys, flat, side="right")
        counts = hi - lo
        total = int(counts.sum())
        if not total:
            return []
        query_ids = np.repeat(np.repeat(np.arange(len(values)), 16), counts)
        starts = np.repeat(lo, counts)
        offsets = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
        disk_ids = starts + offsets
        pair = query_ids.astype(np.int64) * (len(self.quads) + 1) + disk_ids
        _, unique = np.unique(pair, return_index=True)
        query_ids, disk_ids = query_ids[unique], disk_ids[unique]
        decoded = _decode_codes(self.quads["code"][disk_ids])
        distance = np.max(np.abs(decoded - values[query_ids]), axis=1)
        keep = distance <= tolerances[query_ids] + CODE_QUANTUM
        if tiles is not None:
            keep &= np.isin(self.quads["tile"][disk_ids], np.fromiter(tiles, dtype=np.uint32))
        result = [
            (float(d), int(q), int(i))
            for d, q, i in zip(distance[keep], query_ids[keep], disk_ids[keep], strict=True)
        ]
        result.sort(key=lambda item: item[0])
        return result[:maximum]

    def query_stars(self, ra: float, dec: float, radius_deg: float) -> np.ndarray:
        cells = np.asarray(
            self._healpix.cone_search_lonlat(ra * u.deg, dec * u.deg, radius_deg * u.deg),
            dtype=np.uint32,
        )
        positions, valid = _entry_rows(self.tile_entries, cells)
        parts = [
            self.stars[
                int(self.tile_entries[pos]["start"]) : int(
                    self.tile_entries[pos]["start"] + self.tile_entries[pos]["count"]
                )
            ]
            for pos in positions[valid]
        ]
        return np.concatenate(parts) if parts else np.empty(0, dtype=self.stars.dtype)

    def verify(self, *, deep: bool = False) -> dict[str, int]:
        if len(self.tile_entries) > 1 and np.any(
            self.tile_entries["key"][1:] <= self.tile_entries["key"][:-1]
        ):
            raise ValueError("tile keys are not strictly increasing")
        ends = self.tile_entries["start"] + self.tile_entries["count"]
        if len(ends) and int(ends.max()) > len(self.stars):
            raise ValueError("tile entry points outside the star section")
        if len(self.quads) > 1 and np.any(self.quads["key"][1:] < self.quads["key"][:-1]):
            raise ValueError("quad keys are not sorted")
        if deep:
            for start in range(0, len(self.quads), 500_000):
                rows = self.quads[start : start + 500_000]
                if len(rows) and int(rows["refs"].max()) >= len(self.stars):
                    raise ValueError("quad contains an out-of-range star reference")
                if np.any(_code_keys(_decode_codes(rows["code"])) != rows["key"]):
                    raise ValueError("quad is stored under the wrong key")
        return {
            "stars": len(self.stars),
            "quads": len(self.quads),
            "grid_cells": len(np.unique(self.quads["key"])),
        }

    def close(self) -> None:
        if self._closed:
            return
        for name in ("quads", "stars", "tile_entries"):
            value = getattr(self, name, None)
            mapping = getattr(value, "_mmap", None)
            if mapping is not None:
                mapping.close()
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def build_siril_band(
    catalog_path: Path,
    output: Path,
    spec: BandSpec,
    *,
    epoch: float = STAR_EPOCH,
    workers: int = 1,
    checksum: str | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    checksum = checksum or SIRIL_SOURCE.uncompressed_sha256
    with SirilCatalog(catalog_path) as source:
        selected_stars, selected_tiles = _select_siril_stars(
            source,
            spec,
            epoch,
            None,
            on_progress=(
                None if on_progress is None else lambda value: on_progress(0.02 + 0.23 * value)
            ),
        )
        # Large fine-scale layers retain tens of millions of selected stars.
        # Move that stable selection to file-backed arrays before constructing
        # the global spatial tree, so those two phases do not stack their heap
        # footprints.  The mappings are read-only inputs to write_band.
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=output.parent, prefix=f".{output.name}.selected-"
        ) as selected_temp:
            selected_dir = Path(selected_temp)
            stars_path = selected_dir / "stars.bin"
            tiles_path = selected_dir / "tiles.bin"
            star_count, tile_count = len(selected_stars), len(selected_tiles)
            selected_stars.tofile(stars_path)
            selected_tiles.tofile(tiles_path)
            del selected_stars, selected_tiles
            gc.collect()
            mapped_stars = np.memmap(
                stars_path,
                mode="r",
                dtype=BUILD_STAR_DTYPE,
                shape=(star_count,),
            )
            mapped_tiles = np.memmap(
                tiles_path,
                mode="r",
                dtype=TILE_ENTRY_DTYPE,
                shape=(tile_count,),
            )
            try:
                return write_band(
                    output,
                    spec,
                    None,
                    source_identity={
                        "kind": "Siril Gaia DR3 astrometric extract",
                        "filename": catalog_path.name,
                        "uncompressed_sha256": checksum,
                        "records": source.record_count,
                    },
                    epoch=epoch,
                    workers=workers,
                    region=None,
                    started=started,
                    selected=(mapped_stars, mapped_tiles),
                    on_progress=(
                        None
                        if on_progress is None
                        else lambda value: on_progress(0.25 + 0.74 * value)
                    ),
                )
            finally:
                mapped_stars._mmap.close()
                mapped_tiles._mmap.close()


def layer_state(name: str) -> Literal["missing", "ready", "stale"]:
    from .ranges import layer_path

    path = layer_path(name)
    if not path.is_file():
        return "missing"
    try:
        with IndexLayer(path) as layer:
            source = layer.metadata.get("source", {})
            if source.get("uncompressed_sha256") != SIRIL_SOURCE.uncompressed_sha256:
                return "stale"
            if (
                layer.metadata.get("format") != INDEX_FORMAT
                or layer.version != INDEX_FORMAT_VERSION
            ):
                return "stale"
        return "ready"
    except OSError, TypeError, ValueError, KeyError, json.JSONDecodeError:
        return "stale"
