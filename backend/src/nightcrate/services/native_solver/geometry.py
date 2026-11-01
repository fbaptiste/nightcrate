from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from .models import FloatArray, TanWCS


def radec_to_unit(ra_deg: FloatArray, dec_deg: FloatArray) -> FloatArray:
    ra = np.radians(np.asarray(ra_deg, dtype=np.float64))
    dec = np.radians(np.asarray(dec_deg, dtype=np.float64))
    cos_dec = np.cos(dec)
    return np.column_stack((cos_dec * np.cos(ra), cos_dec * np.sin(ra), np.sin(dec)))


def unit_to_radec(vectors: FloatArray) -> tuple[FloatArray, FloatArray]:
    vec = np.asarray(vectors, dtype=np.float64)
    vec = vec / np.linalg.norm(vec, axis=-1, keepdims=True)
    ra = np.degrees(np.arctan2(vec[..., 1], vec[..., 0])) % 360.0
    dec = np.degrees(np.arcsin(np.clip(vec[..., 2], -1.0, 1.0)))
    return np.asarray(ra), np.asarray(dec)


def tangent_basis(ra_deg: float, dec_deg: float) -> tuple[FloatArray, FloatArray, FloatArray]:
    ra = np.radians(ra_deg)
    dec = np.radians(dec_deg)
    center = np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)])
    east = np.array([-np.sin(ra), np.cos(ra), 0.0])
    north = np.array([-np.sin(dec) * np.cos(ra), -np.sin(dec) * np.sin(ra), np.cos(dec)])
    return center, east, north


def gnomonic_project(
    ra_deg: FloatArray, dec_deg: FloatArray, center_ra: float, center_dec: float
) -> tuple[FloatArray, NDArray[np.bool_]]:
    """Project sky vectors to a TAN plane; output coordinates are degrees."""
    vectors = radec_to_unit(np.asarray(ra_deg), np.asarray(dec_deg))
    center, east, north = tangent_basis(center_ra, center_dec)
    denominator = vectors @ center
    valid = denominator > 1e-12
    xy = np.full((len(vectors), 2), np.nan, dtype=np.float64)
    xy[valid, 0] = np.degrees((vectors[valid] @ east) / denominator[valid])
    xy[valid, 1] = np.degrees((vectors[valid] @ north) / denominator[valid])
    return xy, valid


def gnomonic_inverse(
    xy_deg: FloatArray, center_ra: float, center_dec: float
) -> tuple[FloatArray, FloatArray]:
    xy = np.asarray(xy_deg, dtype=np.float64)
    scalar = xy.ndim == 1
    xy = np.atleast_2d(xy)
    center, east, north = tangent_basis(center_ra, center_dec)
    vectors = center + np.radians(xy[:, :1]) * east + np.radians(xy[:, 1:2]) * north
    ra, dec = unit_to_radec(vectors)
    if scalar:
        return ra[0], dec[0]
    return ra, dec


def angular_separation_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    v1 = radec_to_unit(np.array([ra1]), np.array([dec1]))[0]
    v2 = radec_to_unit(np.array([ra2]), np.array([dec2]))[0]
    return float(np.degrees(np.arccos(np.clip(v1 @ v2, -1.0, 1.0))))


@dataclass(frozen=True)
class QuadSet:
    codes: FloatArray
    indices: NDArray[np.int32]
    diameters: FloatArray
    capped: bool = False

    def __len__(self) -> int:
        return len(self.codes)


def _canonical_quad(
    points: FloatArray, indices: tuple[int, int, int, int]
) -> tuple[FloatArray, tuple[int, int, int, int], float] | None:
    distances = np.sum((points[:, None, :] - points[None, :, :]) ** 2, axis=2)
    a, b = np.unravel_index(np.argmax(distances), distances.shape)
    diameter2 = distances[a, b]
    if diameter2 <= 1e-12:
        return None
    others = [i for i in range(4) if i not in (a, b)]
    midpoint = (points[a] + points[b]) / 2.0
    if any(np.sum((points[i] - midpoint) ** 2) > diameter2 / 4.0 + 1e-10 for i in others):
        return None

    def encode(aa: int, bb: int) -> tuple[FloatArray, list[int]]:
        d = points[bb] - points[aa]
        vals = []
        for i in others:
            delta = points[i] - points[aa]
            along = float(delta @ d / diameter2)
            cross = float((d[0] * delta[1] - d[1] * delta[0]) / diameter2)
            vals.append((along + cross, along - cross, i))
        vals.sort(key=lambda value: (value[0], value[1]))
        return np.array([vals[0][0], vals[0][1], vals[1][0], vals[1][1]]), [
            vals[0][2],
            vals[1][2],
        ]

    code, cd = encode(a, b)
    if code[0] + code[2] > 1.0:
        a, b = b, a
        code, cd = encode(a, b)
    order = (indices[a], indices[b], indices[cd[0]], indices[cd[1]])
    return code, order, float(np.sqrt(diameter2))


def build_quads(
    points: FloatArray,
    *,
    neighbour_count: int = 7,
    min_diameter: float = 0.0,
    max_diameter: float = float("inf"),
    max_quads: int = 10_000,
    max_interior_stars: int = 12,
    quads_per_diameter: int = 8,
) -> QuadSet:
    """Build similarity-invariant quads from diameter pairs.

    A and B are selected by a fixed separation band. C and D lie inside the
    circle having AB as its diameter. Unlike a k-nearest-neighbour graph, this
    construction does not change its scale when unrelated faint stars are
    added. Interior stars are sampled from fixed AB-coordinate bins and all
    quad codes are computed in vectorized batches.
    """
    del neighbour_count  # Kept as a compatibility-only keyword for phase 1 callers.
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 4:
        return QuadSet(np.empty((0, 4)), np.empty((0, 4), dtype=np.int32), np.empty(0))
    tree = cKDTree(points)
    pairs = tree.query_pairs(max_diameter, output_type="ndarray")
    if not len(pairs):
        return QuadSet(np.empty((0, 4)), np.empty((0, 4), dtype=np.int32), np.empty(0))
    pair_delta = points[pairs[:, 1]] - points[pairs[:, 0]]
    pair_distance2 = np.einsum("ij,ij->i", pair_delta, pair_delta)
    keep = pair_distance2 >= min_diameter**2
    pairs = pairs[keep]
    pair_distance2 = pair_distance2[keep]
    if not len(pairs):
        return QuadSet(np.empty((0, 4)), np.empty((0, 4), dtype=np.int32), np.empty(0))
    # Interleave short and long diameters so a cap cannot select only one end
    # of the requested scale band.
    order = np.argsort(pair_distance2, kind="stable")
    if len(order) > 1:
        positions: list[int] = []
        low, high = 0, len(order) - 1
        while low <= high:
            positions.append(low)
            if low != high:
                positions.append(high)
            low += 1
            high -= 1
        order = order[np.asarray(positions)]
    pairs = pairs[order]
    pair_distance2 = pair_distance2[order]

    quad_rows: list[np.ndarray] = []
    seen: set[tuple[int, int, int, int]] = set()
    capped = False
    for (a, b), diameter2 in zip(pairs, pair_distance2, strict=True):
        direction = points[b] - points[a]
        relative = points - points[a]
        along = (relative @ direction) / diameter2
        cross = (direction[0] * relative[:, 1] - direction[1] * relative[:, 0]) / diameter2
        inside = (along - 0.5) ** 2 + cross**2 <= 0.25 + 1e-12
        inside[[a, b]] = False
        candidates = np.flatnonzero(inside)
        if len(candidates) < 2:
            continue
        # Fixed bins in the normalized diameter circle are insensitive to
        # stars appearing elsewhere. Input order is brightness order, so the
        # representative in a populated bin is deterministic at each depth.
        bx = np.clip((along[candidates] * 4).astype(int), 0, 3)
        by = np.clip(((cross[candidates] + 0.5) * 4).astype(int), 0, 3)
        bin_id = by * 4 + bx
        representatives: list[int] = []
        per_bin = max(1, math.ceil(max_interior_stars / 16))
        for value in range(16):
            members = candidates[bin_id == value]
            representatives.extend(int(v) for v in members[:per_bin])
        representatives = representatives[:max_interior_stars]
        if len(representatives) < 2:
            continue
        cd = np.asarray(list(combinations(representatives, 2)), dtype=np.int32)
        if len(cd) > quads_per_diameter:
            separation2 = np.sum((points[cd[:, 0]] - points[cd[:, 1]]) ** 2, axis=1)
            cd = cd[np.argsort(-separation2, kind="stable")[:quads_per_diameter]]
        for c, d in cd:
            key = tuple(sorted((int(a), int(b), int(c), int(d))))
            if key in seen:
                continue
            seen.add(key)
            quad_rows.append(np.array([a, b, c, d], dtype=np.int32))
            if len(quad_rows) >= max_quads:
                capped = True
                break
        if capped:
            break
    if not quad_rows:
        return QuadSet(np.empty((0, 4)), np.empty((0, 4), dtype=np.int32), np.empty(0))
    raw_indices = np.stack(quad_rows)
    a = raw_indices[:, 0].copy()
    b = raw_indices[:, 1].copy()

    def encode(aa: np.ndarray, bb: np.ndarray, other: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        direction = points[bb] - points[aa]
        diameter2 = np.einsum("ij,ij->i", direction, direction)
        delta = points[other] - points[aa, None, :]
        along = np.einsum("qki,qi->qk", delta, direction) / diameter2[:, None]
        cross = (
            direction[:, None, 0] * delta[:, :, 1] - direction[:, None, 1] * delta[:, :, 0]
        ) / diameter2[:, None]
        values = np.stack((along + cross, along - cross), axis=2)
        swap = (values[:, 1, 0] < values[:, 0, 0]) | (
            (values[:, 1, 0] == values[:, 0, 0]) & (values[:, 1, 1] < values[:, 0, 1])
        )
        ordered = other.copy()
        ordered[swap] = ordered[swap, ::-1]
        values[swap] = values[swap, ::-1]
        return values.reshape(-1, 4), ordered

    other = raw_indices[:, 2:4].copy()
    codes, other = encode(a, b, other)
    reverse = codes[:, 0] + codes[:, 2] > 1.0
    if np.any(reverse):
        reversed_codes, reversed_other = encode(b[reverse], a[reverse], raw_indices[reverse, 2:4])
        codes[reverse] = reversed_codes
        other[reverse] = reversed_other
        a[reverse], b[reverse] = b[reverse], a[reverse]
    indices = np.column_stack((a, b, other)).astype(np.int32, copy=False)
    diameters = np.linalg.norm(points[a] - points[b], axis=1)
    return QuadSet(codes, indices, diameters, capped)


def build_ranked_quads(
    points: FloatArray,
    *,
    min_diameter: float,
    max_diameter: float,
    max_b_per_a: int = 2,
    max_quads: int = 10_000,
) -> QuadSet:
    """Form brightness-anchored quads from globally ranked points.

    ``points`` must be brightest first.  For each anchor, the first fainter
    neighbours in the requested separation interval are tried as baselines;
    the two brightest remaining points in the diameter circle complete the
    quad.  The index builder implements the same rule in batches on the
    sphere, while this small-image version deliberately stays straightforward.
    """
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 4 or max_diameter <= min_diameter:
        return QuadSet(np.empty((0, 4)), np.empty((0, 4), dtype=np.int32), np.empty(0))
    tree = cKDTree(points)
    rows: list[tuple[FloatArray, tuple[int, int, int, int], float]] = []
    capped = False
    for a, point in enumerate(points):
        neighbours = np.asarray(tree.query_ball_point(point, max_diameter), dtype=int)
        neighbours = neighbours[neighbours > a]
        if not len(neighbours):
            continue
        distances = np.linalg.norm(points[neighbours] - point, axis=1)
        neighbours = np.sort(neighbours[distances >= min_diameter])[:max_b_per_a]
        for b in neighbours:
            midpoint = 0.5 * (point + points[b])
            radius = 0.5 * float(np.linalg.norm(points[b] - point))
            interior = np.asarray(tree.query_ball_point(midpoint, radius + 1e-10), dtype=int)
            interior = np.sort(interior[(interior != a) & (interior != b)])
            if len(interior) < 2:
                continue
            encoded = _canonical_quad(
                points[[a, b, interior[0], interior[1]]],
                (a, int(b), int(interior[0]), int(interior[1])),
            )
            if encoded is not None:
                rows.append(encoded)
            if len(rows) >= max_quads:
                capped = True
                break
        if capped:
            break
    if not rows:
        return QuadSet(np.empty((0, 4)), np.empty((0, 4), dtype=np.int32), np.empty(0))
    return QuadSet(
        np.stack([row[0] for row in rows]),
        np.asarray([row[1] for row in rows], dtype=np.int32),
        np.asarray([row[2] for row in rows]),
        capped,
    )


def build_neighbour_quads(
    points: FloatArray,
    *,
    neighbour_count: int = 7,
    min_diameter: float = 0.0,
    max_diameter: float = float("inf"),
    max_quads: int = 10_000,
    **_: object,
) -> QuadSet:
    """Phase-1b nearest-neighbour builder, retained as a trial baseline."""
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 4:
        return QuadSet(np.empty((0, 4)), np.empty((0, 4), dtype=np.int32), np.empty(0))
    tree = cKDTree(points)
    k = min(neighbour_count + 1, len(points))
    seen: set[tuple[int, int, int, int]] = set()
    rows: list[tuple[FloatArray, tuple[int, int, int, int], float]] = []
    capped = False
    for anchor in range(len(points)):
        neighbours = np.atleast_1d(tree.query(points[anchor], k=k)[1]).tolist()
        neighbours = [int(index) for index in neighbours if int(index) != anchor]
        for trio in combinations(neighbours, 3):
            key = tuple(sorted((anchor, *trio)))
            if key in seen:
                continue
            seen.add(key)
            result = _canonical_quad(points[list(key)], key)
            if result is None or not min_diameter <= result[2] <= max_diameter:
                continue
            rows.append(result)
            if len(rows) >= max_quads:
                capped = True
                break
        if capped:
            break
    if not rows:
        return QuadSet(np.empty((0, 4)), np.empty((0, 4), dtype=np.int32), np.empty(0))
    return QuadSet(
        np.stack([row[0] for row in rows]),
        np.asarray([row[1] for row in rows], dtype=np.int32),
        np.asarray([row[2] for row in rows]),
        capped,
    )


def fit_similarity(source: FloatArray, target: FloatArray) -> tuple[FloatArray, FloatArray, float]:
    """Return target = source @ matrix.T + offset, permitting either parity."""
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    src = source - source_mean
    dst = target - target_mean
    u, singular, vt = np.linalg.svd(src.T @ dst)
    rotation = u @ vt
    scale = float(singular.sum() / np.sum(src**2))
    matrix = (scale * rotation).T
    offset = target_mean - source_mean @ matrix.T
    residual = target - (source @ matrix.T + offset)
    return matrix, offset, float(np.sqrt(np.mean(np.sum(residual**2, axis=1))))


def world_to_pixel(
    wcs: TanWCS, ra: FloatArray, dec: FloatArray
) -> tuple[FloatArray, NDArray[np.bool_]]:
    if not isinstance(wcs, TanWCS):
        raise TypeError("wcs must be TanWCS")
    tangent, valid = gnomonic_project(ra, dec, wcs.crval_ra, wcs.crval_dec)
    pixels = tangent @ np.linalg.inv(wcs.cd).T + wcs.center_pixel
    return pixels, valid


def pixel_to_world(wcs: TanWCS, pixels: FloatArray) -> tuple[FloatArray, FloatArray]:
    delta = np.asarray(pixels) - wcs.center_pixel
    tangent = delta @ wcs.cd.T
    return gnomonic_inverse(tangent, wcs.crval_ra, wcs.crval_dec)
