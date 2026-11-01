from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import sep
from scipy.ndimage import uniform_filter

from .models import DetectedStars


@dataclass(frozen=True)
class ExtractionConfig:
    threshold_sigma: float = 3.5
    min_area: int = 5
    max_elongation: float = 2.5
    edge_margin: int = 8
    max_sources: int = 250
    grid_size: int = 5
    max_working_pixels_unknown_scale: int = 8_000_000
    max_working_pixels_known_scale: int = 5_000_000
    max_working_scale_arcsec: float = 4.1
    background_mesh_full_resolution_px: int = 128
    scale_limited_filter_size: int = 5
    centroid_on_unsmoothed: bool = True
    saturation: Literal["exclude", "include"] = "include"


def _block_mean_2x2(data: np.ndarray) -> np.ndarray:
    height = data.shape[0] // 2 * 2
    width = data.shape[1] // 2 * 2
    trimmed = data[:height, :width]
    return trimmed.reshape(height // 2, 2, width // 2, 2).mean(axis=(1, 3), dtype=np.float32)


def _working_bin_factor(
    height: int,
    width: int,
    *,
    bayer_mosaic: bool,
    pixel_scale_arcsec: float | None,
    config: ExtractionConfig,
) -> int:
    factor = 2 if bayer_mosaic else 1
    working_pixels = (height // factor) * (width // factor)
    if pixel_scale_arcsec is None:
        while working_pixels > config.max_working_pixels_unknown_scale:
            factor *= 2
            working_pixels = (height // factor) * (width // factor)
    else:
        while (
            working_pixels > config.max_working_pixels_known_scale
            and pixel_scale_arcsec * factor * 2.0 <= config.max_working_scale_arcsec
        ):
            factor *= 2
            working_pixels = (height // factor) * (width // factor)
    return factor


def _mono_float32(data: np.ndarray) -> np.ndarray:
    source = np.asarray(data)
    if source.ndim == 3:
        # Average channels into one float32 buffer. This keeps stars that are
        # weak in any one filter without a full-size float64 luminance array.
        if source.shape[-1] <= 4:
            channel_count = source.shape[-1]
            mono = np.asarray(source[..., 0], dtype=np.float32).copy()
            for channel in range(1, channel_count):
                np.add(mono, source[..., channel], out=mono, casting="unsafe")
        elif source.shape[0] <= 4:
            channel_count = source.shape[0]
            mono = np.asarray(source[0], dtype=np.float32).copy()
            for channel in range(1, channel_count):
                np.add(mono, source[channel], out=mono, casting="unsafe")
        else:
            raise ValueError("cannot identify the channel axis")
        mono /= channel_count
        source = mono
    if source.ndim != 2:
        raise ValueError("star extraction requires a two-dimensional mono array")
    return np.ascontiguousarray(source, dtype=np.float32)


def _spatial_brightest(
    x: np.ndarray,
    y: np.ndarray,
    flux: np.ndarray,
    width: int,
    height: int,
    maximum: int,
    grid_size: int,
) -> np.ndarray:
    cells: list[list[int]] = [[] for _ in range(grid_size * grid_size)]
    cell_x = np.clip((x / max(width, 1) * grid_size).astype(int), 0, grid_size - 1)
    cell_y = np.clip((y / max(height, 1) * grid_size).astype(int), 0, grid_size - 1)
    for index in np.argsort(-flux, kind="stable"):
        cells[int(cell_y[index] * grid_size + cell_x[index])].append(int(index))
    chosen: list[int] = []
    rank = 0
    while len(chosen) < maximum:
        added = False
        for cell in cells:
            if rank < len(cell):
                chosen.append(cell[rank])
                added = True
                if len(chosen) == maximum:
                    break
        if not added:
            break
        rank += 1
    return np.asarray(chosen, dtype=int)


def extract_array(
    data: np.ndarray,
    *,
    bayer_mosaic: bool = False,
    pixel_scale_arcsec: float | None = None,
    config: ExtractionConfig | None = None,
) -> DetectedStars:
    """Extract solver stars, returning coordinates in the input array."""
    config = config or ExtractionConfig()
    source = _mono_float32(data)
    original_height, original_width = source.shape
    working = source
    coordinate_scale = 1.0
    desired_factor = _working_bin_factor(
        original_height,
        original_width,
        bayer_mosaic=bayer_mosaic,
        pixel_scale_arcsec=pixel_scale_arcsec,
        config=config,
    )
    if bayer_mosaic and coordinate_scale < desired_factor:
        working = _block_mean_2x2(working)
        coordinate_scale *= 2.0
    while coordinate_scale < desired_factor:
        working = _block_mean_2x2(working)
        coordinate_scale *= 2.0
    detection_working = working
    if (
        working.size > config.max_working_pixels_known_scale
        and config.scale_limited_filter_size > 1
    ):
        # When the scale cap prevents one more decimation, retain the spatial
        # samples but recover part of the 2x2 bin's faint-star S/N benefit.
        detection_working = uniform_filter(
            working,
            size=config.scale_limited_filter_size,
            mode="nearest",
            output=np.float32,
        )
    if not config.centroid_on_unsmoothed:
        working = detection_working
    working = np.ascontiguousarray(working, dtype=np.float32)
    detection_working = np.ascontiguousarray(detection_working, dtype=np.float32)
    mesh = int(round(config.background_mesh_full_resolution_px / coordinate_scale))
    mesh = int(np.clip(mesh, 32, 128))
    background = sep.Background(working, bw=mesh, bh=mesh, fw=3, fh=3)
    subtracted = np.ascontiguousarray(working - background.back(), dtype=np.float32)
    detection_subtracted = (
        np.ascontiguousarray(
            detection_working
            - uniform_filter(
                background.back(),
                size=config.scale_limited_filter_size,
                mode="nearest",
                output=np.float32,
            ),
            dtype=np.float32,
        )
        if detection_working is not working
        else subtracted
    )
    objects = sep.extract(
        detection_subtracted,
        config.threshold_sigma,
        err=background.rms(),
        minarea=config.min_area,
        deblend_nthresh=32,
        deblend_cont=0.01,
        clean=True,
    )
    if not len(objects):
        empty = np.empty(0, dtype=np.float64)
        return DetectedStars(empty, empty, empty, empty, original_width, original_height)

    a = np.asarray(objects["a"], dtype=np.float64)
    b = np.asarray(objects["b"], dtype=np.float64)
    fwhm_working = 2.35482 * np.sqrt(np.maximum(a * b, 0.0))
    x0 = np.asarray(objects["x"], dtype=np.float64)
    y0 = np.asarray(objects["y"], dtype=np.float64)
    flux = np.asarray(objects["flux"], dtype=np.float64)
    margin = config.edge_margin
    keep = (
        (objects["npix"] >= config.min_area)
        & (b > 0.45)
        & (a / np.maximum(b, 1e-6) <= config.max_elongation)
        & (fwhm_working >= 1.2)
        & (x0 >= margin)
        & (x0 < working.shape[1] - margin)
        & (y0 >= margin)
        & (y0 < working.shape[0] - margin)
        & np.isfinite(flux)
        & (flux > 0)
    )
    candidate_indices = np.flatnonzero(keep)
    # A convolved single-pixel defect can satisfy SEP's isophotal area cut.
    # Real PSFs illuminate several native/working pixels around their peak.
    psf_like: list[bool] = []
    for index in candidate_indices:
        xx, yy = int(round(x0[index])), int(round(y0[index]))
        patch = subtracted[max(0, yy - 2) : yy + 3, max(0, xx - 2) : xx + 3]
        peak = float(patch.max(initial=0.0))
        psf_like.append(peak > 0 and np.count_nonzero(patch >= 0.15 * peak) >= 4)
    candidate_indices = candidate_indices[np.asarray(psf_like, dtype=bool)]
    # Reject visibly flat-topped cores. A lone maximum is retained because a
    # normalized linear image often has one legitimately clipped pixel.
    saturation_level = 0.995
    if config.saturation == "exclude" and working.max(initial=0.0) >= saturation_level:
        saturated: list[int] = []
        for index in candidate_indices:
            xx, yy = int(round(x0[index])), int(round(y0[index]))
            patch = working[max(0, yy - 2) : yy + 3, max(0, xx - 2) : xx + 3]
            saturated.append(int(np.count_nonzero(patch >= saturation_level) >= 3))
        candidate_indices = candidate_indices[~np.asarray(saturated, dtype=bool)]
    if not len(candidate_indices):
        empty = np.empty(0, dtype=np.float64)
        return DetectedStars(empty, empty, empty, empty, original_width, original_height)

    sigma = np.clip(fwhm_working[candidate_indices] / 2.35482, 0.6, 6.0)
    x_window, y_window, flags = sep.winpos(
        subtracted, x0[candidate_indices], y0[candidate_indices], sigma
    )
    good = flags == 0
    candidate_indices = candidate_indices[good]
    x_window = np.asarray(x_window)[good]
    y_window = np.asarray(y_window)[good]
    x = (x_window + 0.5) * coordinate_scale - 0.5
    y = (y_window + 0.5) * coordinate_scale - 0.5
    selected = _spatial_brightest(
        x,
        y,
        flux[candidate_indices],
        original_width,
        original_height,
        config.max_sources,
        config.grid_size,
    )
    return DetectedStars(
        x[selected].astype(np.float64),
        y[selected].astype(np.float64),
        flux[candidate_indices][selected].astype(np.float64),
        (fwhm_working[candidate_indices][selected] * coordinate_scale).astype(np.float64),
        original_width,
        original_height,
    )


def _has_bayer_header(cards: list[dict]) -> bool:
    values = {
        str(card.get("key", "")).upper(): str(card.get("value", "")).strip() for card in cards
    }
    return any(values.get(key) for key in ("BAYERPAT", "BAYERPATTERN"))


def extract_near(
    data: np.ndarray,
    *,
    bayer_mosaic: bool,
    pixel_scale_arcsec: float | None = None,
) -> DetectedStars:
    """Extract stars with the prototype's catalogue-only profile."""
    return extract_array(
        data,
        bayer_mosaic=bayer_mosaic,
        pixel_scale_arcsec=pixel_scale_arcsec,
        config=ExtractionConfig(centroid_on_unsmoothed=False),
    )


def extract_for_index(
    data: np.ndarray,
    *,
    bayer_mosaic: bool,
    pixel_scale_arcsec: float | None = None,
) -> tuple[DetectedStars, DetectedStars]:
    """Extract one saturation-inclusive population for verification and quads."""
    config = ExtractionConfig()
    detections = extract_array(
        data,
        bayer_mosaic=bayer_mosaic,
        pixel_scale_arcsec=pixel_scale_arcsec,
        config=config,
    )
    return detections, detections
