"""Pre-calculated image generation for projects.

Two entry points:

- ``generate_rendered_images(file_path, output_dir)`` — produces
  current ``full_v2.jpg``, ``thumb_lg_v2.jpg``, ``thumb_md_v2.jpg`` and
  ``thumb_sm_v2.jpg`` renditions. Older ``_v1`` and unversioned files remain
  usable until a current rendition replaces them.
- ``generate_cropped_thumbnail(file_path, crop, output_path, size)`` —
  produces one current ``thumb_crop_{size}_v2_{row_id}.jpg`` file. Older
  ``_v1_`` and unversioned crop generations remain usable until replacement.

Pure service — no FastAPI, no DB access.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
import re
import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from nightcrate.core.tasks import drain_task_map
from nightcrate.services import standard_io
from nightcrate.services.catalog_thumbnail import render_array_jpeg
from nightcrate.services.imaging import area_reduce
from nightcrate.services.path_resolver import resolve_path
from nightcrate.services.pixel_loader import load_image, superpixels_of

logger = logging.getLogger(__name__)

VARIANT_SIZES: dict[str, int] = {
    "full": 4000,
    "thumb_lg": 800,
    "thumb_md": 400,
    "thumb_sm": 180,
}
RENDER_VERSION = 2

_RENDER_LOCK = threading.Lock()
_REFRESH_SEM = asyncio.Semaphore(1)
_in_flight: dict[Path, asyncio.Task[None]] = {}
_running_refreshes: set[asyncio.Task[None]] = set()


def _downsample(data: np.ndarray, max_dim: int) -> np.ndarray:
    """Area-reduce so the largest spatial dimension is at most *max_dim*."""
    h, w = data.shape[-2], data.shape[-1]
    step = max(1, math.ceil(max(h, w) / max_dim))
    return area_reduce(data, step)


def _load_raw(file_path: str) -> tuple[str, object]:
    """Load raw image data and return (file_type, data_or_path).

    For standard images returns ("standard", PILImage).
    For scientific formats returns (ft, np.ndarray).
    """
    p, ft, _idx, _ck = resolve_path(file_path)

    if ft == "standard":
        raw = standard_io.load_image_bytes(p)
        return "standard", PILImage.open(io.BytesIO(raw))

    return ft, superpixels_of(load_image(file_path))


def rendition_path(output_dir: Path, variant: str) -> Path:
    return output_dir / f"{variant}_v{RENDER_VERSION}.jpg"


def rendition_candidates(output_dir: Path, variant: str) -> list[Path]:
    """Return rendition generations newest first."""
    paths = [rendition_path(output_dir, variant)]
    paths.extend(
        output_dir / f"{variant}_v{version}.jpg" for version in range(RENDER_VERSION - 1, 0, -1)
    )
    paths.append(output_dir / f"{variant}.jpg")
    return paths


def _render_scientific(data: np.ndarray, max_size: int) -> PILImage.Image:
    """Area-reduce and render through the worker-safe NumPy stretch."""
    small = _downsample(data, max_size * 2)
    payload = render_array_jpeg(small, max_size, quality=85, stretch="auto")
    with PILImage.open(io.BytesIO(payload)) as image:
        return image.copy()


def _save_jpeg(img: PILImage.Image, path: Path) -> None:
    if img.mode == "RGBA":
        img = img.convert("RGB")
    img.save(path, format="JPEG", quality=85)


def _delete_exact_obsolete(paths: list[Path], identity: str) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "[project-images] couldn't remove obsolete %s file %s",
                identity,
                path,
                exc_info=True,
            )


def _delete_older_renditions(output_dir: Path, variant: str) -> None:
    _delete_exact_obsolete(rendition_candidates(output_dir, variant)[1:], "rendition")


def _delete_older_crops(output_path: Path, size: str) -> None:
    match = re.fullmatch(
        rf"thumb_crop_{re.escape(size)}_v{RENDER_VERSION}_(\d+)\.jpg",
        output_path.name,
    )
    if match is None:
        return
    row_id = match.group(1)
    _delete_exact_obsolete(crop_candidates(output_path.parent, size, int(row_id))[1:], "crop")


def generate_rendered_images(file_path: str, output_dir: Path) -> None:
    """Generate all pre-calculated image variants and write to *output_dir*.

    Creates versioned ``full``, ``thumb_lg``, ``thumb_md`` and ``thumb_sm``
    JPEG renditions. Serialised via a module-level lock so only one
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
                _save_jpeg(copy, rendition_path(output_dir, variant))
                _delete_older_renditions(output_dir, variant)
        else:
            data: np.ndarray = raw  # type: ignore[assignment]
            for variant, size in VARIANT_SIZES.items():
                img = _render_scientific(data, size)
                _save_jpeg(img, rendition_path(output_dir, variant))
                _delete_older_renditions(output_dir, variant)

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
    return project_folder / f"thumb_crop_{size}_v{RENDER_VERSION}_{row_id}.jpg"


def crop_candidates(project_folder: Path, size: str, row_id: int) -> list[Path]:
    """Return crop generations newest first."""
    paths = [crop_path(project_folder, size, row_id)]
    paths.extend(
        project_folder / f"thumb_crop_{size}_v{version}_{row_id}.jpg"
        for version in range(RENDER_VERSION - 1, 0, -1)
    )
    paths.append(project_folder / f"thumb_crop_{size}_{row_id}.jpg")
    return paths


async def _background_wrapper(
    target: Path,
    operation: Callable[..., None],
    args: tuple[object, ...],
) -> None:
    try:
        async with _REFRESH_SEM:
            task = asyncio.current_task()
            if task is not None:
                _running_refreshes.add(task)
            try:
                await asyncio.to_thread(operation, *args)
            finally:
                if task is not None:
                    _running_refreshes.discard(task)
    except Exception as exc:  # noqa: BLE001 - refresh failures keep the older file usable
        logger.info("[project-images] background refresh failed for %s: %s", target, exc)
    finally:
        if _in_flight.get(target) is asyncio.current_task():
            _in_flight.pop(target, None)


def refresh_in_background(
    target: Path,
    operation: Callable[..., None],
    *args: object,
) -> None:
    """Start at most one background refresh for *target*."""
    if target in _in_flight:
        return
    task = asyncio.create_task(_background_wrapper(target, operation, args))
    _in_flight[target] = task


async def drain_background_refreshes(*, cancel_pending: bool = False) -> None:
    """Drain current refreshes, optionally cancelling work not yet rendering."""
    await drain_task_map(
        _in_flight,
        cancel_pending=cancel_pending,
        running=_running_refreshes.copy(),
    )


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
        _delete_older_crops(output_path, size)

    logger.info("[project-images] cropped %s → %s", file_path, output_path)
