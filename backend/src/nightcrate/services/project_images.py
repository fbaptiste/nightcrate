"""Pre-calculated image generation for projects.

Two entry points:

- ``generate_rendered_images(file_path, output_dir)`` — produces
  ``full.jpg``, ``thumb_lg.jpg``, ``thumb_md.jpg``, ``thumb_sm.jpg``
  in the given directory (per-image previews).
- ``generate_cropped_thumbnail(file_path, crop, output_path, size)`` —
  produces a single cropped thumbnail at the target size written to
  *output_path* (project-level display thumbnails).

Pure service — no FastAPI, no DB access.
"""

from __future__ import annotations

import io
import logging
import threading
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from nightcrate.services import fits_io, pxiproject_io, standard_io, xisf_io
from nightcrate.services.imaging import (
    compute_image_stats,
    resolve_auto_stretch,
    stretch_plane,
)
from nightcrate.services.path_resolver import resolve_path

logger = logging.getLogger(__name__)

VARIANT_SIZES: dict[str, int] = {
    "full": 4000,
    "thumb_lg": 800,
    "thumb_md": 400,
    "thumb_sm": 180,
}

_RENDER_LOCK = threading.Lock()


def _downsample(data: np.ndarray, max_dim: int) -> np.ndarray:
    """Stride-subsample so the largest spatial dimension <= max_dim."""
    h, w = data.shape[-2], data.shape[-1]
    step = max(1, max(h, w) // max_dim)
    if step <= 1:
        return data
    if data.ndim == 2:
        return data[::step, ::step]
    return data[:, ::step, ::step]


def _load_raw(file_path: str) -> tuple[str, object]:
    """Load raw image data and return (file_type, data_or_path).

    For standard images returns ("standard", PILImage).
    For scientific formats returns (ft, np.ndarray).
    """
    p, ft, idx, _ck = resolve_path(file_path)

    if ft == "standard":
        raw = standard_io.load_image_bytes(p)
        return "standard", PILImage.open(io.BytesIO(raw))

    if ft == "pxiproject":
        data = pxiproject_io.load_image_data(p, idx)
    elif ft == "fits":
        data = fits_io.load_image_data(p, 0)
    elif ft == "xisf":
        data = xisf_io.load_image_data(p, 0)
    elif ft == "float_tiff":
        data = standard_io.load_image_data(p)
    else:
        data = standard_io.load_image_as_array(p)

    return ft, data


def _render_scientific(data: np.ndarray, max_size: int) -> PILImage.Image:
    """Downsample, auto-stretch, and return a Pillow Image."""
    small = _downsample(data, max_size * 2)
    stats = compute_image_stats(small)
    linked, per_channel, _ = resolve_auto_stretch(small, stats=stats)

    if small.ndim == 2:
        params = linked if linked is not None else (per_channel[0] if per_channel else linked)
        scaled = stretch_plane(small, params)
        img = PILImage.fromarray(scaled, mode="L")
    else:
        ch_params = (
            per_channel if per_channel and len(per_channel) == 3 else [linked, linked, linked]
        )
        planes = [stretch_plane(small[i], ch_params[i]) for i in range(3)]
        rgb = np.stack(planes, axis=2)
        img = PILImage.fromarray(rgb, mode="RGB")

    img.thumbnail((max_size, max_size), PILImage.LANCZOS)
    return img


def _save_jpeg(img: PILImage.Image, path: Path) -> None:
    if img.mode == "RGBA":
        img = img.convert("RGB")
    img.save(path, format="JPEG", quality=85)


def generate_rendered_images(file_path: str, output_dir: Path) -> None:
    """Generate all pre-calculated image variants and write to *output_dir*.

    Creates ``full.jpg``, ``thumb_lg.jpg``, ``thumb_md.jpg``,
    ``thumb_sm.jpg``.  Serialised via a module-level lock so only one
    render runs at a time (MLX Metal is not thread-safe).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    with _RENDER_LOCK:
        ft, raw = _load_raw(file_path)

        if ft == "standard":
            pil_img: PILImage.Image = raw  # type: ignore[assignment]
            if pil_img.mode == "RGBA":
                pil_img = pil_img.convert("RGB")
            for variant, size in VARIANT_SIZES.items():
                copy = pil_img.copy()
                copy.thumbnail((size, size), PILImage.LANCZOS)
                _save_jpeg(copy, output_dir / f"{variant}.jpg")
        else:
            data: np.ndarray = raw  # type: ignore[assignment]
            for variant, size in VARIANT_SIZES.items():
                img = _render_scientific(data, size)
                _save_jpeg(img, output_dir / f"{variant}.jpg")

    logger.info("[project-images] rendered %s → %s", file_path, output_dir)


CROP_SIZES: dict[str, tuple[int, int]] = {
    "small": (480, 360),
    "medium": (800, 600),
    "large": (1200, 900),
}


class CropFrameError(ValueError):
    """The requested thumbnail frame is invalid for its source image."""


def crop_path(project_folder: Path, size: str, row_id: int) -> Path:
    """Return the generation-specific crop path inside a project folder."""
    return project_folder / f"thumb_crop_{size}_{row_id}.jpg"


def fit_box(width: int, height: int) -> tuple[float, float, float, float]:
    """Return the smallest centred 4:3 fractional box containing an image."""
    aspect = width / height
    if aspect >= 4 / 3:
        box_height = 0.75 * aspect
        return 0, (1 - box_height) / 2, 1, box_height
    box_width = 4 / (3 * aspect)
    return (1 - box_width) / 2, 0, box_width, 1


def check_crop_frame(
    width: int,
    height: int,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    """Validate a fractional 4:3 crop frame against the image's fit box."""
    tolerance = 0.01
    aspect_error = abs((w * width) / (h * height) / (4 / 3) - 1)
    if aspect_error > tolerance:
        raise CropFrameError("The frame must be 4:3.")

    fit_x, fit_y, fit_w, fit_h = fit_box(width, height)
    if (
        x < fit_x - tolerance * fit_w
        or x + w > fit_x + fit_w + tolerance * fit_w
        or y < fit_y - tolerance * fit_h
        or y + h > fit_y + fit_h + tolerance * fit_h
    ):
        raise CropFrameError("The frame must stay within the picture and its mat.")

    if w * width < 1 or h * height < 1:
        raise CropFrameError("The frame is too small.")


def render_crop(
    img: PILImage.Image,
    x: float,
    y: float,
    w: float,
    h: float,
    target: tuple[int, int],
) -> PILImage.Image:
    """Render a fractional frame onto a black target-sized canvas."""
    if img.mode == "RGBA":
        img = img.convert("RGB")

    width, height = img.size
    target_width, target_height = target
    left = x * width
    top = y * height
    right = (x + w) * width
    bottom = (y + h) * height
    scale_x = target_width / (right - left)
    scale_y = target_height / (bottom - top)

    intersection_left = max(0, left)
    intersection_top = max(0, top)
    intersection_right = min(width, right)
    intersection_bottom = min(height, bottom)

    paste_left = round((intersection_left - left) * scale_x)
    paste_right = round((intersection_right - left) * scale_x)
    paste_top = round((intersection_top - top) * scale_y)
    paste_bottom = round((intersection_bottom - top) * scale_y)
    paste_left = max(0, min(paste_left, target_width - 1))
    paste_right = max(paste_left + 1, min(paste_right, target_width))
    paste_top = max(0, min(paste_top, target_height - 1))
    paste_bottom = max(paste_top + 1, min(paste_bottom, target_height))

    piece = img.resize(
        (paste_right - paste_left, paste_bottom - paste_top),
        PILImage.LANCZOS,
        box=(intersection_left, intersection_top, intersection_right, intersection_bottom),
    )
    canvas = PILImage.new(img.mode, target, 0)
    canvas.paste(piece, (paste_left, paste_top))
    return canvas


def generate_cropped_thumbnail(
    file_path: str,
    crop_x: float,
    crop_y: float,
    crop_w: float,
    crop_h: float,
    output_path: Path,
    size: str,
) -> None:
    """Generate a cropped thumbnail from *file_path* and write to *output_path*.

    Crop coordinates are fractions relative to the source image and may extend onto its mat.
    Serialised via the module-level render lock.
    """
    target = CROP_SIZES[size]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with _RENDER_LOCK:
        ft, raw = _load_raw(file_path)

        if ft == "standard":
            pil_img: PILImage.Image = raw  # type: ignore[assignment]
        else:
            data: np.ndarray = raw  # type: ignore[assignment]
            max_dim = max(data.shape[-2], data.shape[-1])
            render_size = min(max_dim, max(target) * 4)
            pil_img = _render_scientific(data, render_size)

        check_crop_frame(*pil_img.size, crop_x, crop_y, crop_w, crop_h)
        cropped = render_crop(pil_img, crop_x, crop_y, crop_w, crop_h, target)
        _save_jpeg(cropped, output_path)

    logger.info("[project-images] cropped %s → %s", file_path, output_path)
