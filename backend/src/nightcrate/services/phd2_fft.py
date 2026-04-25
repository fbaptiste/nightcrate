"""PHD2 spectrum (FFT) pipeline — PHDLogViewer-aligned (spec v4 §6.1)."""

from __future__ import annotations

from typing import Literal

import numpy as np
from scipy.interpolate import Akima1DInterpolator  # type: ignore[import-untyped]

from nightcrate.services.phd2_models import FftPeak, FftResult, GuidingSample

# PHDLogViewer's `AnalysisWin.cpp` line ~258 — refuses to run on
# sections shorter than 12 frames. Below that the FFT bins are
# uselessly wide.
MIN_ENTRIES = 12

# IQR(dt) / median(dt) above this threshold means the cadence is
# bimodal enough that interpolation can't paper over it. IQR-over-
# median is robust against DROP-frame gaps that would blow up plain
# std/mean.
CADENCE_IQR_RATIO_LIMIT = 0.20

# PHDLogViewer caps at 8; spec v4 §6.1.6 tightens to 5 (peaks above
# that are noise-floor-adjacent).
MAX_PEAKS = 5

# Two peaks within ±5 % period collapse to the higher-amplitude one.
PEAK_DEDUP_FRAC = 0.05

# 1 / Φ⁻¹(3/4) — converts MAD to a normal-σ equivalent.
MAD_SIGMA_FACTOR = 1.4826

# Conservative threshold; matches PHDLogViewer.
PEAK_SIGMA_THRESHOLD = 3.0

# Hamming amplitude scale: a = (4 / N) · |X_k|. The factor 4 ≈ 2
# (single-sided) × 1/0.54 (Hamming coherent gain reciprocal). Over-
# estimates true peak amplitude by ~8 % but matches PHDLogViewer's
# numbers exactly. See spec §M5.
HAMMING_AMP_SCALE = 4.0

# Below 5 s the spectrum is dominated by atmospheric seeing; the
# chart greys out that band.
SEEING_BAND_S = 5.0


SkipReason = Literal[
    "too_short",
    "non_uniform_cadence",
    "constant_data",
]


def compute_section_fft(
    samples: list[GuidingSample],
    *,
    pixel_scale: float | None,
    trace: Literal["ra", "dec"] = "ra",
) -> FftResult | None:
    """Compute the FFT spectrum for one trace of one guiding section."""
    if not samples:
        return None

    times: list[float] = []
    values: list[float] = []
    for s in samples:
        v = s.ra_raw_px if trace == "ra" else s.dec_raw_px
        if v is None:
            continue
        times.append(s.time_seconds)
        values.append(v)

    if len(times) < MIN_ENTRIES:
        return _skip("too_short")

    t_arr = np.asarray(times, dtype=np.float64)
    x_arr = np.asarray(values, dtype=np.float64)

    dt_arr = np.diff(t_arr)
    if dt_arr.size == 0:
        return _skip("too_short")
    dt_median = float(np.median(dt_arr))
    if dt_median <= 0:
        return _skip("non_uniform_cadence")
    iqr = float(np.percentile(dt_arr, 75) - np.percentile(dt_arr, 25))
    if iqr / dt_median > CADENCE_IQR_RATIO_LIMIT:
        return _skip("non_uniform_cadence")

    # Drift subtraction so the spectrum's low-frequency end isn't
    # dominated by polar-alignment-driven drift.
    a, b = _linear_fit(t_arr, x_arr)
    x_detrended = x_arr - (a + b * t_arr)

    # Resample to a uniform grid at the median dt; clamp the right
    # edge to within the original extent so Akima doesn't extrapolate.
    t_uniform = t_arr[0] + np.arange(len(t_arr)) * dt_median
    t_uniform = t_uniform[t_uniform <= t_arr[-1]]
    n_uniform = len(t_uniform)
    if n_uniform < MIN_ENTRIES:
        return _skip("too_short")
    x_uniform = Akima1DInterpolator(t_arr, x_detrended)(t_uniform)

    x_windowed = x_uniform * np.hamming(n_uniform)

    fft = np.fft.rfft(x_windowed)
    if fft.size <= 1:
        return _skip("too_short")
    fft_mag = np.abs(fft[1:])
    bin_indices = np.arange(1, fft.size)

    # f_k = k / (N · Δt) → p_k = N · Δt / k.
    period_s = (n_uniform * dt_median) / bin_indices

    amplitude_arcsec = fft_mag * (HAMMING_AMP_SCALE / n_uniform)
    if pixel_scale is not None and pixel_scale > 0:
        amplitude_arcsec = amplitude_arcsec * pixel_scale

    # Without this, a constant detrended series collapses the MAD
    # threshold to zero and numeric noise surfaces as "peaks".
    if float(np.max(amplitude_arcsec)) <= 0:
        return _skip("constant_data")

    peaks = _detect_peaks(period_s, amplitude_arcsec)

    return FftResult(
        period_s=[float(p) for p in period_s],
        amplitude_arcsec=[float(a) for a in amplitude_arcsec],
        peaks=peaks,
    )


def _skip(reason: SkipReason) -> FftResult:
    return FftResult(period_s=[], amplitude_arcsec=[], peaks=[], skip_reason=reason)


def _linear_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """OLS slope + intercept for y ≈ a + b·x."""
    n = len(x)
    if n < 2:
        return float(y.mean()) if n == 1 else 0.0, 0.0
    mx = float(x.mean())
    my = float(y.mean())
    cov = float(((x - mx) * (y - my)).sum())
    var = float(((x - mx) ** 2).sum())
    if var == 0:
        return my, 0.0
    b = cov / var
    return my - b * mx, b


def _detect_peaks(period_s: np.ndarray, amplitude: np.ndarray) -> list[FftPeak]:
    if amplitude.size < 3:
        return []
    median = float(np.median(amplitude))
    mad = float(np.median(np.abs(amplitude - median)))
    threshold = median + PEAK_SIGMA_THRESHOLD * MAD_SIGMA_FACTOR * mad

    candidates: list[tuple[float, float]] = []
    for i in range(1, amplitude.size - 1):
        a = float(amplitude[i])
        if a <= threshold:
            continue
        if a <= float(amplitude[i - 1]) or a <= float(amplitude[i + 1]):
            continue
        candidates.append((float(period_s[i]), a))

    if not candidates:
        return []

    # Dedup: highest-amplitude wins within a ±5 % period band.
    candidates.sort(key=lambda p: p[1], reverse=True)
    accepted: list[tuple[float, float]] = []
    for period, amp in candidates:
        too_close = any(
            abs(period - acc_period) / max(period, acc_period) <= PEAK_DEDUP_FRAC
            for acc_period, _ in accepted
        )
        if too_close:
            continue
        accepted.append((period, amp))
        if len(accepted) >= MAX_PEAKS:
            break

    accepted.sort(key=lambda p: p[0])
    sqrt2 = float(np.sqrt(2))
    return [
        FftPeak(
            period_s=period,
            amplitude_arcsec=amp,
            peak_to_peak_arcsec=2.0 * amp,
            rms_arcsec=amp / sqrt2,
        )
        for period, amp in accepted
    ]
