"""Format-agnostic image processing: normalization, stretch, stats, rendering.

All functions accept normalized [0, 1] float64 arrays — no knowledge of FITS, XISF, etc.
"""

import io
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

# ── STF constants (matches PixInsight defaults) ──────────────────────────────

STF_TARGET_BG = 0.25  # target median in the stretched image
STF_SHADOW_CLIP = -2.8  # scaled-MAD units below median for shadow clip


# ── Data normalization ───────────────────────────────────────────────────────


def normalize_to_01(raw_data: np.ndarray) -> np.ndarray:
    """Normalize raw pixel data to [0, 1] based on data type.

    Matches PixInsight behaviour: integer types are divided by their type max,
    float types are assumed to be already in [0, 1] (or normalized by actual max).
    """
    dtype = raw_data.dtype
    data = np.array(raw_data, dtype=np.float64)

    if dtype == np.uint16:
        data /= 65535.0
    elif dtype == np.uint32:
        data /= 4294967295.0
    elif dtype == np.int16:
        data = (data + 32768.0) / 65535.0
    elif dtype == np.int32:
        data = (data + 2147483648.0) / 4294967295.0
    elif np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        data = (data - info.min) / (info.max - info.min)
    else:
        # Float data: normalize by actual max if values exceed 1
        dmax = data.max()
        if dmax > 1.0:
            data /= dmax
        data = np.clip(data, 0.0, None)

    return data


def reshape_color(data: np.ndarray) -> np.ndarray:
    """Ensure a 3D array is shaped (3, H, W). Collapse extra dims for mono."""
    if data.ndim == 3:
        if data.shape[0] == 3:
            return data
        if data.shape[2] == 3:
            return np.moveaxis(data, 2, 0)

    while data.ndim > 2:
        data = data[0]
    return data


# ── Image statistics + STF auto-computation ──────────────────────────────────


@dataclass
class StfParams:
    """Auto-computed STF parameters for one channel."""

    shadow: float
    midtone: float
    highlight: float


@dataclass
class ChannelStats:
    min: float
    max: float
    median: float
    mad: float
    stf: StfParams


@dataclass
class ImageStats:
    color: bool
    channels: list[ChannelStats] = field(default_factory=list)
    linked_stf: StfParams | None = None


def _compute_stf(median: float, mad: float) -> StfParams:
    """Compute STF shadow clip and midtones balance from [0, 1] normalized stats."""
    sigma = mad * 1.4826

    c = median + STF_SHADOW_CLIP * sigma
    c = max(0.0, c)

    if c < median and (1.0 - c) > 0:
        med_clipped = (median - c) / (1.0 - c)
    else:
        med_clipped = 0.0

    t = STF_TARGET_BG
    if 0 < med_clipped < 1:
        m = (med_clipped * (1 - t)) / (med_clipped * (1 - 2 * t) + t)
    elif med_clipped <= 0:
        m = 0.0
    else:
        m = 0.5

    return StfParams(shadow=c, midtone=m, highlight=1.0)


def _channel_stats(plane: np.ndarray) -> ChannelStats:
    """Compute statistics for a single [0, 1]-normalized channel."""
    flat = plane.ravel()
    med = float(np.median(flat))
    mad = float(np.median(np.abs(flat - med)))
    stf = _compute_stf(med, mad)
    return ChannelStats(
        min=float(flat.min()),
        max=float(flat.max()),
        median=med,
        mad=mad,
        stf=stf,
    )


def compute_image_stats(data: np.ndarray) -> ImageStats:
    """Compute per-channel statistics and auto STF params for a normalized array.

    data: (H, W) for mono or (3, H, W) for color.
    """
    if data.ndim == 2:
        return ImageStats(color=False, channels=[_channel_stats(data)])

    channels = [_channel_stats(data[i]) for i in range(3)]
    ref_idx = min(range(3), key=lambda i: channels[i].median)
    return ImageStats(color=True, channels=channels, linked_stf=channels[ref_idx].stf)


# ── Stretch + render ─────────────────────────────────────────────────────────


@dataclass
class StretchParams:
    stretch: str = "stf"  # "stf" | "linear"
    shadow: float = 0.0
    midtone: float = 0.5
    highlight: float = 1.0


def _mtf(x: np.ndarray, m: float) -> np.ndarray:
    """Midtones Transfer Function: MTF(x, m) = (m-1)*x / ((2m-1)*x - m)."""
    if m <= 0.0:
        return np.zeros_like(x)
    if m >= 1.0:
        return np.ones_like(x)
    return ((m - 1.0) * x) / ((2.0 * m - 1.0) * x - m)


def stretch_plane(plane: np.ndarray, p: StretchParams) -> np.ndarray:
    """Apply stretch to a single 2D plane normalized to [0, 1]. Return uint8."""
    if p.stretch == "stf":
        c = p.shadow
        h = p.highlight
        if h <= c:
            return np.full(plane.shape, 128, dtype=np.uint8)

        clipped = np.clip(plane, c, h)
        rescaled = (clipped - c) / (h - c)
        stretched = _mtf(rescaled, p.midtone)
        return (np.clip(stretched, 0.0, 1.0) * 255).astype(np.uint8)

    # Linear: simple min/max scaling
    dmin = plane.min()
    dmax = plane.max()
    if dmax == dmin:
        return np.full(plane.shape, 128, dtype=np.uint8)
    normalized = (plane - dmin) / (dmax - dmin)
    return (normalized * 255).astype(np.uint8)


def render_image_png(
    data: np.ndarray,
    linked: StretchParams | None = None,
    per_channel: list[StretchParams] | None = None,
) -> bytes:
    """Render a normalized [0, 1] array to PNG bytes with stretch applied.

    data: (H, W) for mono or (3, H, W) for color.
    """
    default_params = StretchParams()

    if data.ndim == 2:
        params = linked if linked is not None else default_params
        scaled = stretch_plane(data, params)
        img = Image.fromarray(scaled, mode="L")
    else:
        if per_channel and len(per_channel) == 3:
            channel_params = per_channel
        else:
            p = linked if linked is not None else default_params
            channel_params = [p, p, p]

        planes = [stretch_plane(data[i], channel_params[i]) for i in range(3)]
        rgb = np.stack(planes, axis=2)
        img = Image.fromarray(rgb, mode="RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
