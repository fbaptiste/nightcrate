"""Pre-calculated image generation for projects.

Produces auto-stretched JPEGs at multiple sizes from any supported
image format.  The caller provides an output directory; this module
writes ``full.jpg``, ``thumb_lg.jpg``, ``thumb_md.jpg``, and
``thumb_sm.jpg`` into it.

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
    "small": (180, 180),
    "medium": (400, 400),
    "large": (280, 210),
}


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

    Crop coordinates are fractions 0–1 relative to the source image.
    Serialised via the module-level render lock.
    """
    target = CROP_SIZES.get(size, (180, 180))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with _RENDER_LOCK:
        ft, raw = _load_raw(file_path)

        if ft == "standard":
            pil_img: PILImage.Image = raw  # type: ignore[assignment]
            if pil_img.mode == "RGBA":
                pil_img = pil_img.convert("RGB")
        else:
            data: np.ndarray = raw  # type: ignore[assignment]
            max_dim = max(data.shape[-2], data.shape[-1])
            render_size = min(max_dim, max(target) * 4)
            pil_img = _render_scientific(data, render_size)

        w, h = pil_img.size
        left = int(crop_x * w)
        upper = int(crop_y * h)
        right = int((crop_x + crop_w) * w)
        lower = int((crop_y + crop_h) * h)
        left = max(0, min(left, w - 1))
        upper = max(0, min(upper, h - 1))
        right = max(left + 1, min(right, w))
        lower = max(upper + 1, min(lower, h))

        cropped = pil_img.crop((left, upper, right, lower))
        cropped = cropped.resize(target, PILImage.LANCZOS)
        _save_jpeg(cropped, output_path)

    logger.info("[project-images] cropped %s → %s", file_path, output_path)
