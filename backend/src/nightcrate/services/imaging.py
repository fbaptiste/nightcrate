"""Format-agnostic image processing: normalization, stretch, stats, rendering.

All functions accept normalized [0, 1] float64 arrays — no knowledge of FITS, XISF, etc.
"""

import io
from dataclasses import dataclass, field

import bottleneck as bn
import numpy as np
from PIL import Image

from nightcrate.core.compute import get_array_module

# ── STF constants (matches PixInsight AutoSTF defaults) ──────────────────────

STF_TARGET_BG = 0.25  # target background brightness in output
STF_SHADOWS_CLIP = -1.25  # avgDev units below median for shadow clip

# ── Luminance weights (ITU-R BT.709) ───────────────────────────────────────
LUM_R, LUM_G, LUM_B = 0.2126, 0.7152, 0.0722


# ── Data normalization ───────────────────────────────────────────────────────


def is_color_image(data: np.ndarray) -> bool:
    """Return True if the array represents a color (3-channel) image."""
    return data.ndim == 3 and data.shape[0] == 3


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
    avg_dev: float
    snr: float
    stf: StfParams


@dataclass
class ImageStats:
    color: bool
    channels: list[ChannelStats] = field(default_factory=list)
    linked_stf: StfParams | None = None
    background_delta: list[float] | None = None  # per-channel deviation from mean median
    lab_a_median: float | None = None  # CIE L*a*b* a* median (color balance diagnostic)


def _mtf_scalar(x: float, m: float) -> float:
    """Scalar MTF for parameter computation (not pixel processing)."""
    if m <= 0.0:
        return 0.0
    if m >= 1.0:
        return 1.0
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return ((m - 1.0) * x) / ((2.0 * m - 1.0) * x - m)


def _compute_stf(median: float, avg_dev: float) -> StfParams:
    """Compute STF shadow clip and midtones balance.

    Uses the PixInsight AutoSTF algorithm:
    - Shadow clip: median + SHADOWS_CLIP * avgDev
    - Midtones balance: MTF(TARGET_BKG, median - shadow_clip)
      (exploits the MTF self-inverse property)
    """
    c0 = median + STF_SHADOWS_CLIP * avg_dev
    c0 = max(0.0, min(c0, 1.0))

    # Midtones balance via MTF self-inverse property:
    # We want MTF(b0, m) = TARGET_BG, so m = MTF(b0, TARGET_BG)
    b0 = median - c0
    if b0 <= 0.0:
        m = 0.0
    elif b0 >= 1.0:
        m = 0.5
    else:
        m = _mtf_scalar(b0, STF_TARGET_BG)

    return StfParams(shadow=c0, midtone=m, highlight=1.0)


def _channel_stats(plane: np.ndarray) -> ChannelStats:
    """Compute statistics for a single [0, 1]-normalized channel.

    Uses GPU (mlx/cupy) when available for median and deviation computation.
    """
    xp = get_array_module()
    if xp is not np:
        # GPU path: convert to GPU array, compute stats, extract scalars
        gpu = xp.array(plane)
        med = float(xp.median(gpu).item())
        deviations = xp.abs(gpu - med)
        mad = float(xp.median(deviations).item())
        avg_dev = float(xp.mean(deviations).item())
        vmin = float(xp.min(gpu).item())
        vmax = float(xp.max(gpu).item())
    else:
        # CPU path: bottleneck for fast median
        flat = plane.ravel()
        med = float(bn.nanmedian(flat))
        deviations = np.abs(flat - med)
        mad = float(bn.nanmedian(deviations))
        avg_dev = float(np.mean(deviations))
        vmin = float(flat.min())
        vmax = float(flat.max())
    sigma = mad * 1.4826
    snr = med / sigma if sigma > 0 else 0.0
    stf = _compute_stf(med, avg_dev)
    return ChannelStats(
        min=vmin,
        max=vmax,
        median=med,
        mad=mad,
        avg_dev=avg_dev,
        snr=snr,
        stf=stf,
    )


def compute_image_stats(data: np.ndarray) -> ImageStats:
    """Compute per-channel statistics and auto STF params for a normalized array.

    data: (H, W) for mono or (3, H, W) for color.

    For color images, the linked STF averages c0 and median across all channels
    before computing a single set of parameters (matching PixInsight's linked mode).
    """
    if data.ndim == 2:
        return ImageStats(color=False, channels=[_channel_stats(data)])

    n = data.shape[0]
    channels = [_channel_stats(data[i]) for i in range(n)]

    # Linked mode: average shadow clip and median across channels
    avg_c0 = 0.0
    avg_median = 0.0
    for ch in channels:
        avg_c0 += ch.median + STF_SHADOWS_CLIP * ch.avg_dev
        avg_median += ch.median
    avg_c0 = max(0.0, min(avg_c0 / n, 1.0))
    avg_median /= n

    b0 = avg_median - avg_c0
    if b0 <= 0.0:
        m = 0.0
    elif b0 >= 1.0:
        m = 0.5
    else:
        m = _mtf_scalar(b0, STF_TARGET_BG)

    linked_stf = StfParams(shadow=avg_c0, midtone=m, highlight=1.0)

    # Per-channel background deviation from mean median
    background_delta = [(ch.median - avg_median) for ch in channels]

    # CIE L*a*b* a* median — color balance diagnostic
    lab_a_median = _compute_lab_a_median(data) if n == 3 else None

    return ImageStats(
        color=True,
        channels=channels,
        linked_stf=linked_stf,
        background_delta=background_delta,
        lab_a_median=lab_a_median,
    )


def _compute_lab_a_median(rgb_data: np.ndarray) -> float:
    """Compute median CIE L*a*b* a* value from linear RGB [0,1] data.

    Positive a* = red/magenta excess, negative a* = green excess.
    Uses sRGB→XYZ→Lab conversion with D65 illuminant.
    """
    r, g, b = rgb_data[0], rgb_data[1], rgb_data[2]
    # Subsample for performance (~500K pixels is statistically sufficient)
    stride = max(1, int(np.sqrt(r.size / 500_000)))
    if stride > 1:
        r, g, b = r[::stride, ::stride], g[::stride, ::stride], b[::stride, ::stride]

    # Linear sRGB → XYZ (D65) — only X and Y needed for a*
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b

    # D65 reference white
    xn, yn = 0.95047, 1.0

    def f(t: np.ndarray) -> np.ndarray:
        delta = 6.0 / 29.0
        mask = t > delta**3
        result = np.empty_like(t)
        result[mask] = np.cbrt(t[mask])
        result[~mask] = t[~mask] / (3.0 * delta**2) + 4.0 / 29.0
        return result

    fx = f(x / xn)
    fy = f(y / yn)

    # a* = 500 * (f(X/Xn) - f(Y/Yn))
    a_star = 500.0 * (fx - fy)

    return float(bn.nanmedian(a_star))


# ── Stretch + render ─────────────────────────────────────────────────────────


@dataclass
class StretchParams:
    stretch: str = "stf"  # "stf" | "linear" | "auto"
    shadow: float = 0.0
    midtone: float = 0.5
    highlight: float = 1.0


def _mtf(x, m: float):
    """Midtones Transfer Function: MTF(x, m) = (m-1)*x / ((2m-1)*x - m).

    Works with numpy, mlx, and cupy arrays (uses only arithmetic operators).
    """
    if m <= 0.0:
        return x * 0.0
    if m >= 1.0:
        return x * 0.0 + 1.0
    return ((m - 1.0) * x) / ((2.0 * m - 1.0) * x - m)


def stretch_plane(plane: np.ndarray, p: StretchParams) -> np.ndarray:
    """Apply stretch to a single 2D plane normalized to [0, 1]. Return uint8.

    Uses GPU (mlx/cupy) when available for the heavy element-wise operations.
    """
    xp = get_array_module()
    use_gpu = xp is not np

    if p.stretch == "stf":
        c = p.shadow
        h = p.highlight
        if h <= c:
            return np.full(plane.shape, 128, dtype=np.uint8)

        src = xp.array(plane) if use_gpu else plane
        clipped = xp.clip(src, c, h)
        rescaled = (clipped - c) / (h - c)
        stretched = _mtf(rescaled, p.midtone)
        result = xp.clip(stretched, 0.0, 1.0) * 255
        if use_gpu:
            return np.asarray(result.astype(xp.uint8))
        return result.astype(np.uint8)

    # Linear: simple min/max scaling
    src = xp.array(plane) if use_gpu else plane
    dmin = float(xp.min(src))
    dmax = float(xp.max(src))
    if dmax == dmin:
        return np.full(plane.shape, 128, dtype=np.uint8)
    normalized = (src - dmin) / (dmax - dmin)
    result = normalized * 255
    if use_gpu:
        return np.asarray(result.astype(xp.uint8))
    return result.astype(np.uint8)


def resolve_auto_stretch(
    data: np.ndarray,
    stats: ImageStats | None = None,
) -> tuple[StretchParams, list[StretchParams] | None, ImageStats]:
    """Compute stretch params automatically from image data.

    Determines whether the image is linear or non-linear by checking the STF
    midtone value.  Linear images get STF stretch; non-linear images get a
    simple linear passthrough.

    Returns (linked_params, per_channel_params_or_None, computed_stats).
    """
    if stats is None:
        stats = compute_image_stats(data)

    # Non-linear detection: if the STF midtone is >= 0.1, the image is already
    # stretched — use linear passthrough.
    stf = stats.linked_stf or (stats.channels[0].stf if stats.channels else None)
    if stf and stf.midtone >= 0.1:
        return StretchParams(stretch="linear"), None, stats

    # Linear image — apply STF auto-stretch
    if stats.color and stats.linked_stf:
        linked = StretchParams(
            stretch="stf",
            shadow=stats.linked_stf.shadow,
            midtone=stats.linked_stf.midtone,
            highlight=stats.linked_stf.highlight,
        )
    elif stats.channels:
        ch_stf = stats.channels[0].stf
        linked = StretchParams(
            stretch="stf", shadow=ch_stf.shadow, midtone=ch_stf.midtone, highlight=ch_stf.highlight
        )
    else:
        linked = StretchParams(stretch="linear")

    per_channel = None
    if stats.color and len(stats.channels) == 3:
        per_channel = [
            StretchParams(
                stretch="stf",
                shadow=ch.stf.shadow,
                midtone=ch.stf.midtone,
                highlight=ch.stf.highlight,
            )
            for ch in stats.channels
        ]

    return linked, per_channel, stats


def render_image_png(
    data: np.ndarray,
    linked: StretchParams | None = None,
    per_channel: list[StretchParams] | None = None,
) -> bytes:
    """Render a normalized [0, 1] array to PNG bytes with stretch applied.

    data: (H, W) for mono or (3, H, W) for color.
    If linked.stretch == "auto", computes stats and determines the best stretch.
    """
    default_params = StretchParams()

    # Resolve auto-stretch: compute stats and pick the right params
    if linked and linked.stretch == "auto":
        linked, per_channel, _ = resolve_auto_stretch(data)

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
    # Level 1: fastest compression. Local app — file size doesn't matter,
    # but encoding speed directly impacts image load time.
    img.save(buf, format="PNG", compress_level=1)
    return buf.getvalue()
