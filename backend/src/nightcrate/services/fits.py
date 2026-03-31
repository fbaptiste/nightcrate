"""FITS file reading and rendering logic."""

import io
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image

# ── STF constants (matches PixInsight defaults) ──────────────────────────────

STF_TARGET_BG = 0.25        # target median in the stretched image
STF_SHADOW_CLIP = -2.8      # scaled-MAD units below median for shadow clip


def _hdu_index(hdul: fits.HDUList, hdu: int) -> fits.ImageHDU | fits.PrimaryHDU:
    if hdu < 0 or hdu >= len(hdul):
        raise ValueError(f"HDU index {hdu} out of range (file has {len(hdul)} HDUs)")
    return hdul[hdu]


def read_header(file_path: Path, hdu: int = 0) -> list[dict]:
    """Return all header cards for the given HDU as a list of dicts."""
    with fits.open(file_path, memmap=False) as hdul:
        target = _hdu_index(hdul, hdu)
        cards = []
        for card in target.header.cards:
            cards.append({
                "key": card.keyword,
                "value": str(card.value),
                "comment": card.comment,
            })
        return cards


def list_hdus(file_path: Path) -> list[dict]:
    """Return a summary of all HDUs: index, name, type, and whether it has image data."""
    with fits.open(file_path, memmap=False) as hdul:
        result = []
        for i, hdu_obj in enumerate(hdul):
            has_image = (
                isinstance(hdu_obj, (fits.PrimaryHDU, fits.ImageHDU))
                and hdu_obj.data is not None
                and hdu_obj.data.ndim >= 2
            )
            result.append({
                "index": i,
                "name": hdu_obj.name or f"HDU {i}",
                "type": type(hdu_obj).__name__,
                "has_image": has_image,
            })
        return result


def _normalize_to_01(raw_data: np.ndarray) -> np.ndarray:
    """Normalize raw FITS pixel data to [0, 1] based on data type.

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


def _load_image_data(file_path: Path, hdu: int) -> np.ndarray:
    """Load image data as float64 array normalized to [0, 1].

    Returns shape (H, W) for mono or (3, H, W) for color.
    """
    with fits.open(file_path, memmap=False) as hdul:
        target = _hdu_index(hdul, hdu)
        if target.data is None:
            raise ValueError(f"HDU {hdu} contains no image data")
        data = _normalize_to_01(target.data)

    # Detect color: 3D array where one axis == 3
    if data.ndim == 3:
        if data.shape[0] == 3:
            return data  # already (3, H, W)
        if data.shape[2] == 3:
            return np.moveaxis(data, 2, 0)  # (H, W, 3) → (3, H, W)

    # Collapse extra dims to 2D mono
    while data.ndim > 2:
        data = data[0]
    return data


def is_color(file_path: Path, hdu: int = 0) -> bool:
    """Return True if the HDU contains a 3-channel (color) image."""
    with fits.open(file_path, memmap=False) as hdul:
        target = _hdu_index(hdul, hdu)
        if target.data is None:
            return False
        d = target.data
        return d.ndim == 3 and (d.shape[0] == 3 or d.shape[2] == 3)


# ── Image statistics + STF auto-computation ──────────────────────────────────


@dataclass
class StfParams:
    """Auto-computed STF parameters for one channel."""

    shadow: float     # black clip point, normalized 0–1
    midtone: float    # midtones balance, 0–1 (lower = more aggressive stretch)
    highlight: float  # white point, normalized 0–1 (usually 1.0)


@dataclass
class ChannelStats:
    min: float
    max: float
    median: float
    mad: float        # median absolute deviation
    stf: StfParams    # auto-computed STF defaults


@dataclass
class ImageStats:
    color: bool
    channels: list[ChannelStats] = field(default_factory=list)
    linked_stf: StfParams | None = None  # for color: STF from dimmest channel


def _compute_stf(median: float, mad: float) -> StfParams:
    """Compute STF shadow clip and midtones balance.

    Input median and mad must already be in [0, 1] normalized space.
    """
    # Normalized MAD → estimated standard deviation
    sigma = mad * 1.4826

    # Shadow clipping: 2.8σ below median
    c = median + STF_SHADOW_CLIP * sigma
    c = max(0.0, c)

    # Normalized median after shadow clip
    if c < median and (1.0 - c) > 0:
        med_clipped = (median - c) / (1.0 - c)
    else:
        med_clipped = 0.0

    # Midtones balance: solve for m so MTF maps med_clipped → TARGET_BG
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


def get_image_stats(file_path: Path, hdu: int = 0) -> ImageStats:
    """Return per-channel statistics and auto-computed STF params."""
    data = _load_image_data(file_path, hdu)
    if data.ndim == 2:
        ch = _channel_stats(data)
        return ImageStats(color=False, channels=[ch])

    # Color: (3, H, W)
    channels = [_channel_stats(data[i]) for i in range(3)]

    # Linked STF: use the dimmest channel (lowest median)
    ref_idx = min(range(3), key=lambda i: channels[i].median)
    linked_stf = channels[ref_idx].stf

    return ImageStats(color=True, channels=channels, linked_stf=linked_stf)


# ── Stretch + render ─────────────────────────────────────────────────────────


@dataclass
class StretchParams:
    stretch: str = "stf"         # "stf" | "linear" | "asinh"
    # STF params (used when stretch == "stf")
    shadow: float = 0.0          # shadow clip, normalized 0–1
    midtone: float = 0.5         # midtones balance, 0–1
    highlight: float = 1.0       # highlight clip, normalized 0–1
    # Legacy params (used when stretch == "linear" or "asinh")
    black_pct: float = 0.0
    white_pct: float = 100.0
    gamma: float = 1.0
    asinh_beta: float = 0.1


def _mtf(x: np.ndarray, m: float) -> np.ndarray:
    """Midtones Transfer Function — vectorized for a numpy array.

    MTF(x, m) = (m - 1) * x / ((2m - 1) * x - m)
    """
    if m <= 0.0:
        return np.zeros_like(x)
    if m >= 1.0:
        return np.ones_like(x)
    return ((m - 1.0) * x) / ((2.0 * m - 1.0) * x - m)


def _stretch_plane(plane: np.ndarray, p: StretchParams) -> np.ndarray:
    """Apply stretch to a single 2D plane already normalized to [0, 1]. Return uint8."""
    if p.stretch == "stf":
        c = p.shadow
        h = p.highlight
        if h <= c:
            return np.full(plane.shape, 128, dtype=np.uint8)

        # Clip to shadow/highlight range and rescale to [0, 1]
        clipped = np.clip(plane, c, h)
        rescaled = (clipped - c) / (h - c)

        # Apply midtones transfer function
        stretched = _mtf(rescaled, p.midtone)
        return (np.clip(stretched, 0.0, 1.0) * 255).astype(np.uint8)

    elif p.stretch == "asinh":
        flat = plane.ravel()
        lo = float(np.percentile(flat, p.black_pct))
        hi = float(np.percentile(flat, p.white_pct))
        if hi <= lo:
            return np.full(plane.shape, 128, dtype=np.uint8)
        clipped = np.clip(plane, lo, hi)
        normalized = (clipped - lo) / (hi - lo)
        beta = max(p.asinh_beta, 1e-6)
        normalized = np.arcsinh(normalized / beta) / np.arcsinh(1.0 / beta)
        return (np.clip(normalized, 0.0, 1.0) * 255).astype(np.uint8)

    else:
        # Linear with percentile clip + gamma
        flat = plane.ravel()
        lo = float(np.percentile(flat, p.black_pct))
        hi = float(np.percentile(flat, p.white_pct))
        if hi <= lo:
            return np.full(plane.shape, 128, dtype=np.uint8)
        clipped = np.clip(plane, lo, hi)
        normalized = (clipped - lo) / (hi - lo)
        if p.gamma != 1.0:
            normalized = np.power(np.clip(normalized, 0.0, 1.0), 1.0 / p.gamma)
        return (normalized * 255).astype(np.uint8)


def render_image_png(
    file_path: Path,
    hdu: int = 0,
    linked: StretchParams | None = None,
    per_channel: list[StretchParams] | None = None,
) -> bytes:
    """Read image data from the given HDU and return a PNG as bytes.

    Data is normalized to [0, 1] at load time (matching PixInsight convention),
    then the stretch is applied in that space.
    """
    data = _load_image_data(file_path, hdu)
    default_params = StretchParams()

    if data.ndim == 2:
        # Mono
        params = linked if linked is not None else default_params
        scaled = _stretch_plane(data, params)
        img = Image.fromarray(scaled, mode="L")
    else:
        # Color (3, H, W)
        if per_channel and len(per_channel) == 3:
            channel_params = per_channel
        else:
            p = linked if linked is not None else default_params
            channel_params = [p, p, p]

        planes = [_stretch_plane(data[i], channel_params[i]) for i in range(3)]
        rgb = np.stack(planes, axis=2)  # (H, W, 3)
        img = Image.fromarray(rgb, mode="RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
