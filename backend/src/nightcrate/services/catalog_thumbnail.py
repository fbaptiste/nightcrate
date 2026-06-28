"""Cheap, cached thumbnails for cataloged frames (v0.40.0).

The catalog grid needs a small per-row preview, but the full image-render endpoint
loads + stretches the entire frame (real subs are ~26 MP) — far too heavy for a
48 px cell. This renders a small JPEG by **decimating the array before any heavy
work**, applying the same PixInsight AutoSTF auto-stretch, and encoding at low
quality. Callers cache the bytes on disk keyed by content hash.

**Pure NumPy — never the GPU backend.** mlx (Apple Metal) is NOT safe to call
concurrently from multiple threads: the catalog grid renders several thumbnails at
once (via ``asyncio.to_thread``), and routing those through `imaging.stretch_plane`
/ `resolve_auto_stretch` (which use `get_array_module()` → mlx) segfaults the
process (reproduced: 9 concurrent XISF renders → SIGSEGV with mlx, clean with
numpy). The STF math is replicated here in numpy so the thumbnail path never
touches the GPU. Decimated arrays are tiny, so there is no perf cost.

Pure service: takes a path, returns bytes. No DB, no FastAPI, no caching policy.
"""

from __future__ import annotations

import io
import logging

import numpy as np
from PIL import Image

from nightcrate.services import fits_io, pxiproject_io, standard_io, xisf_io
from nightcrate.services.imaging import (
    STF_SHADOWS_CLIP,
    STF_TARGET_BG,
    _mtf_scalar,
    reshape_color,
)
from nightcrate.services.path_resolver import resolve_path

logger = logging.getLogger("nightcrate.catalog_thumbnail")

DEFAULT_MAX_PX = 96
# Decimate so the longest axis is ~this many source pixels before the stretch —
# enough detail for a small thumbnail at a fraction of the cost.
_DECIMATE_TARGET_FACTOR = 3


def _load_normalized(path: str) -> np.ndarray:
    """Load image data normalized to [0, 1], shape (H, W) or (3, H, W).

    The format loaders already normalize + reshape, so this is just a dispatch.
    """
    resolved, ft, idx, _ = resolve_path(path)
    if ft == "pxiproject":
        return reshape_color(pxiproject_io.load_image_data(resolved, idx))
    if ft == "fits":
        return fits_io.load_image_data(resolved)
    if ft == "float_tiff":
        return reshape_color(standard_io.load_image_data(resolved))
    if ft == "standard":
        return reshape_color(standard_io.load_image_as_array(resolved))
    return xisf_io.load_image_data(resolved)


def _decimate_step(long_axis: int, max_px: int) -> int:
    return max(1, long_axis // (max_px * _DECIMATE_TARGET_FACTOR))


def _stf_params(plane01: np.ndarray) -> tuple[float, float]:
    """PixInsight AutoSTF (shadow, midtone) for a [0, 1] plane — numpy, no GPU.

    Mirrors ``imaging._channel_stats`` + ``imaging._compute_stf``.
    """
    flat = plane01.ravel()
    median = float(np.median(flat))
    avg_dev = float(np.mean(np.abs(flat - median)))
    shadow = min(max(median + STF_SHADOWS_CLIP * avg_dev, 0.0), 1.0)
    b0 = median - shadow
    if b0 <= 0.0:
        midtone = 0.0
    elif b0 >= 1.0:
        midtone = 0.5
    else:
        midtone = _mtf_scalar(b0, STF_TARGET_BG)
    return shadow, midtone


def _stretch_u8(
    plane01: np.ndarray, shadow: float, midtone: float, highlight: float = 1.0
) -> np.ndarray:
    """Apply the STF (clip → rescale → MTF) to a [0, 1] plane → uint8. Numpy MTF
    mirrors ``imaging.stretch_plane`` (STF branch)."""
    if highlight <= shadow:
        return np.full(plane01.shape, 128, dtype=np.uint8)
    rescaled = (np.clip(plane01, shadow, highlight) - shadow) / (highlight - shadow)
    if midtone <= 0.0:
        out = np.zeros_like(rescaled)
    elif midtone >= 1.0:
        out = np.ones_like(rescaled)
    else:
        out = ((midtone - 1.0) * rescaled) / ((2.0 * midtone - 1.0) * rescaled - midtone)
    return (np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8)


def render_thumbnail_bytes(path: str, max_px: int = DEFAULT_MAX_PX) -> bytes:
    """Render *path* to a small auto-stretched JPEG (<= max_px on the long side).

    Raises on unreadable / unsupported sources — the caller maps that to a 404 and
    simply shows no thumbnail (a missing preview is never fatal).
    """
    data = _load_normalized(path)

    if data.ndim == 2:
        step = _decimate_step(max(data.shape), max_px)
        small = np.ascontiguousarray(data[::step, ::step])
        shadow, midtone = _stf_params(small)
        img = Image.fromarray(_stretch_u8(small, shadow, midtone), mode="L")
    elif data.ndim == 3 and data.shape[0] == 3:
        _, h, w = data.shape
        step = _decimate_step(max(h, w), max_px)
        planes = []
        for i in range(3):
            plane = np.ascontiguousarray(data[i, ::step, ::step])
            shadow, midtone = _stf_params(plane)
            planes.append(_stretch_u8(plane, shadow, midtone))
        img = Image.fromarray(np.stack(planes, axis=-1), mode="RGB")
    else:
        raise ValueError(f"unsupported thumbnail array shape: {data.shape}")

    img.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()
