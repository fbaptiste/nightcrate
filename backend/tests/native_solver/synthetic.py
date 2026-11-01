from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nightcrate.services.native_solver.geometry import angular_separation_deg, pixel_to_world
from nightcrate.services.native_solver.models import DetectedStars, StarCatalog, TanWCS


@dataclass(frozen=True)
class SyntheticCase:
    image: np.ndarray
    catalog: StarCatalog
    truth: TanWCS
    ideal_detections: DetectedStars
    bayer_mosaic: bool


def make_wcs(
    ra: float,
    dec: float,
    width: int,
    height: int,
    scale_arcsec: float,
    rotation_deg: float,
    parity: int,
) -> TanWCS:
    angle = np.radians(rotation_deg)
    scale = scale_arcsec / 3600.0
    cd = scale * np.array(
        [
            [np.cos(angle), -np.sin(angle)],
            [parity * np.sin(angle), parity * np.cos(angle)],
        ]
    )
    return TanWCS(ra % 360.0, dec, cd, width, height)


def _spaced_pixels(rng: np.random.Generator, count: int, width: int, height: int) -> np.ndarray:
    points: list[tuple[float, float]] = []
    attempts = 0
    while len(points) < count and attempts < count * 100:
        attempts += 1
        candidate = (rng.uniform(14, width - 14), rng.uniform(14, height - 14))
        if all(np.hypot(candidate[0] - x, candidate[1] - y) > 7.0 for x, y in points):
            points.append(candidate)
    if len(points) < count:
        raise RuntimeError("could not place requested synthetic stars")
    return np.asarray(points)


def _render(
    rng: np.random.Generator,
    width: int,
    height: int,
    pixels: np.ndarray,
    flux: np.ndarray,
    *,
    hot_pixels: int,
) -> np.ndarray:
    image = rng.normal(0.025, 0.003, (height, width))
    sigma = 1.35
    radius = 5
    for (x, y), amplitude in zip(pixels, flux, strict=True):
        x0, y0 = int(np.floor(x)), int(np.floor(y))
        xs = np.arange(max(0, x0 - radius), min(width, x0 + radius + 1))
        ys = np.arange(max(0, y0 - radius), min(height, y0 + radius + 1))
        xx, yy = np.meshgrid(xs, ys)
        image[np.ix_(ys, xs)] += amplitude * np.exp(
            -((xx - x) ** 2 + (yy - y) ** 2) / (2.0 * sigma**2)
        )
    if hot_pixels:
        hot_x = rng.integers(5, width - 5, hot_pixels)
        hot_y = rng.integers(5, height - 5, hot_pixels)
        image[hot_y, hot_x] = 1.0
    return np.clip(image, 0.0, 1.0)


def make_case(
    seed: int,
    *,
    ra: float | None = None,
    dec: float | None = None,
    scale_arcsec: float | None = None,
    rotation_deg: float | None = None,
    parity: int | None = None,
    bayer_mosaic: bool = False,
    width: int = 384,
    height: int = 320,
    star_count: int = 65,
    extra_catalog_factor: float = 1.0,
    missing_fraction: float = 0.0,
    spurious_count: int = 0,
    scramble_brightness: bool = False,
    distortion_corner_px: float = 0.0,
    render_image: bool = True,
) -> SyntheticCase:
    rng = np.random.default_rng(seed)
    ra = float(rng.uniform(0, 360) if ra is None else ra)
    dec = float(rng.uniform(-75, 75) if dec is None else dec)
    scale_arcsec = float(
        10 ** rng.uniform(np.log10(0.5), np.log10(10.0)) if scale_arcsec is None else scale_arcsec
    )
    rotation_deg = float(rng.uniform(0, 360) if rotation_deg is None else rotation_deg)
    parity = int(rng.choice([-1, 1]) if parity is None else parity)
    truth = make_wcs(ra, dec, width, height, scale_arcsec, rotation_deg, parity)
    if extra_catalog_factor < 1.0 or not 0.0 <= missing_fraction < 1.0:
        raise ValueError("invalid synthetic catalog factor or missing fraction")
    catalog_count = max(star_count, int(np.ceil(star_count * extra_catalog_factor)))
    all_pixels = _spaced_pixels(rng, catalog_count + spurious_count, width, height)
    catalog_pixels = all_pixels[:catalog_count]
    spurious_pixels = all_pixels[catalog_count:]
    sky_ra, sky_dec = pixel_to_world(truth, catalog_pixels)
    magnitudes = np.sort(rng.uniform(8.0, 15.0, catalog_count)).astype(np.float32)
    if scramble_brightness:
        rendered_indices = np.sort(rng.choice(catalog_count, size=star_count, replace=False))
    else:
        rendered_indices = np.arange(star_count)
    missing_count = int(round(missing_fraction * len(rendered_indices)))
    if missing_count:
        keep = np.ones(len(rendered_indices), dtype=bool)
        keep[rng.choice(len(rendered_indices), size=missing_count, replace=False)] = False
        rendered_indices = rendered_indices[keep]
    rendered_pixels = catalog_pixels[rendered_indices].copy()
    if distortion_corner_px:
        center = np.array([(width - 1.0) / 2.0, (height - 1.0) / 2.0])
        delta = rendered_pixels - center
        corner_radius = np.hypot(center[0], center[1])
        radius2 = np.sum(delta**2, axis=1) / corner_radius**2
        rendered_pixels += delta * (distortion_corner_px / corner_radius * radius2)[:, None]
    amplitudes = np.clip(
        0.8 * 10 ** (-0.18 * (magnitudes[rendered_indices] - magnitudes.min())),
        0.09,
        0.8,
    )
    # Match the measured corpus brightness uncertainty: Gaussian scatter in
    # magnitudes, converted back to a multiplicative flux ratio.
    amplitudes *= 10 ** (-0.4 * rng.normal(0.0, 0.25, len(rendered_indices)))
    if scramble_brightness:
        rng.shuffle(amplitudes)
    spurious_flux = rng.uniform(
        float(amplitudes.min()),
        float(amplitudes.max()),
        spurious_count,
    )
    image_pixels = np.vstack((rendered_pixels, spurious_pixels))
    image_flux = np.concatenate((amplitudes, spurious_flux))
    image = (
        _render(rng, width, height, image_pixels, image_flux, hot_pixels=12)
        if render_image
        else np.empty((0, 0), dtype=np.float32)
    )
    catalog = StarCatalog(np.asarray(sky_ra), np.asarray(sky_dec), magnitudes)
    jitter = rng.normal(0.0, 0.08, image_pixels.shape)
    measured = image_pixels + jitter
    ideal = DetectedStars(
        measured[:, 0],
        measured[:, 1],
        image_flux.astype(np.float64),
        np.full(len(image_pixels), 2.35482 * 1.35),
        width,
        height,
    )
    return SyntheticCase(image, catalog, truth, ideal, bayer_mosaic)


def solution_errors(truth: TanWCS, solved: TanWCS) -> dict[str, float | bool]:
    center_arcsec = 3600.0 * angular_separation_deg(
        truth.crval_ra, truth.crval_dec, solved.crval_ra, solved.crval_dec
    )
    rotation = abs((solved.rotation_deg - truth.rotation_deg + 180.0) % 360.0 - 180.0)
    return {
        "center_arcsec": center_arcsec,
        "scale_relative": abs(solved.scale_arcsec / truth.scale_arcsec - 1.0),
        "rotation_deg": rotation,
        "parity_equal": solved.parity == truth.parity,
    }
