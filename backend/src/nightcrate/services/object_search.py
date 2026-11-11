"""Pure plate-solve geometry used by object search and checklist features."""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel

from nightcrate.services.image_annotation_models import AnnotatedDso, WcsParams
from nightcrate.services.image_annotations import project_dsos


class SolveGeometry(BaseModel):
    project_id: int
    solve_id: int
    wcs: WcsParams
    image_width: int
    image_height: int


def _tan_pixel_to_sky(
    wcs: WcsParams, x: np.ndarray, y: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """TAN deprojection matching FITS' one-based CRPIX convention."""
    dx = x + 1.0 - wcs.crpix1
    dy = y + 1.0 - wcs.crpix2
    xi = np.deg2rad(wcs.cd1_1 * dx + wcs.cd1_2 * dy)
    eta = np.deg2rad(wcs.cd2_1 * dx + wcs.cd2_2 * dy)
    ra0 = math.radians(wcs.crval1)
    dec0 = math.radians(wcs.crval2)
    sin_dec0 = math.sin(dec0)
    cos_dec0 = math.cos(dec0)
    denominator = cos_dec0 - eta * sin_dec0
    ra = ra0 + np.arctan2(xi, denominator)
    dec = np.arctan2(
        sin_dec0 + eta * cos_dec0,
        np.sqrt(denominator * denominator + xi * xi),
    )
    return np.mod(np.rad2deg(ra), 360.0), np.rad2deg(dec)


def _separation_deg(
    ra1_deg: float,
    dec1_deg: float,
    ra2_deg: np.ndarray,
    dec2_deg: np.ndarray,
) -> np.ndarray:
    ra_delta = np.deg2rad(ra2_deg - ra1_deg)
    dec1 = math.radians(dec1_deg)
    dec2 = np.deg2rad(dec2_deg)
    cosine = math.sin(dec1) * np.sin(dec2) + math.cos(dec1) * np.cos(dec2) * np.cos(ra_delta)
    return np.rad2deg(np.arccos(np.clip(cosine, -1.0, 1.0)))


def _centre_and_scale(solve: SolveGeometry) -> tuple[float, float, float]:
    wcs = solve.wcs
    centre_ra, centre_dec = _tan_pixel_to_sky(
        wcs,
        np.array([solve.image_width / 2.0]),
        np.array([solve.image_height / 2.0]),
    )
    sigma_max = float(
        np.linalg.svd(
            np.array([[wcs.cd1_1, wcs.cd1_2], [wcs.cd2_1, wcs.cd2_2]]),
            compute_uv=False,
        )[0]
    )
    return float(centre_ra[0]), float(centre_dec[0]), sigma_max


def solve_reach(solve: SolveGeometry) -> tuple[float, float, float]:
    """Return the displayed image centre and a sky circle containing its corners."""
    centre_ra, centre_dec, _ = _centre_and_scale(solve)
    xs = np.array([0.0, solve.image_width, solve.image_width, 0.0])
    ys = np.array([0.0, 0.0, solve.image_height, solve.image_height])
    corner_ra, corner_dec = _tan_pixel_to_sky(solve.wcs, xs, ys)
    radius = float(np.max(_separation_deg(centre_ra, centre_dec, corner_ra, corner_dec)))
    return centre_ra, centre_dec, radius


def objects_near(solve: SolveGeometry, dsos: list[dict]) -> list[dict]:
    """Return a vectorised, provable superset of objects overlapping the image."""
    if not dsos:
        return []
    centre_ra, centre_dec, sigma_max = _centre_and_scale(solve)
    ra = np.fromiter((float(dso["ra_deg"]) for dso in dsos), dtype=float, count=len(dsos))
    dec = np.fromiter((float(dso["dec_deg"]) for dso in dsos), dtype=float, count=len(dsos))
    sizes = np.fromiter(
        (float(dso.get("maj_axis_arcmin") or 0.0) for dso in dsos),
        dtype=float,
        count=len(dsos),
    )
    pixel_scale_deg = math.hypot(solve.wcs.cd2_1, solve.wcs.cd2_2)
    if pixel_scale_deg > 0:
        margins = sizes / 60.0 / pixel_scale_deg / 2.0
    else:
        margins = np.zeros(len(dsos), dtype=float)
    half_diagonal = math.hypot(solve.image_width / 2.0, solve.image_height / 2.0)
    bounds = (half_diagonal + math.sqrt(2.0) * margins) * sigma_max
    keep = _separation_deg(centre_ra, centre_dec, ra, dec) <= bounds
    return [dso for dso, included in zip(dsos, keep, strict=True) if bool(included)]


def marks_in_solve(solve: SolveGeometry, dsos: list[dict]) -> list[AnnotatedDso]:
    """Project the narrowed object set through the shared annotation function."""
    return project_dsos(solve.wcs, objects_near(solve, dsos))
