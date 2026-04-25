"""Unit tests for PHD2 spectrum (FFT) pipeline — spec v4 §6.1."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.interpolate import Akima1DInterpolator  # type: ignore[import-untyped]

from nightcrate.services.phd2_fft import (
    HAMMING_AMP_SCALE,
    MAX_PEAKS,
    MIN_ENTRIES,
    compute_section_fft,
)
from nightcrate.services.phd2_models import GuidingSample


def _make_samples(
    times: list[float], values: list[float], *, axis: str = "ra"
) -> list[GuidingSample]:
    samples: list[GuidingSample] = []
    for i, (t, v) in enumerate(zip(times, values, strict=True)):
        samples.append(
            GuidingSample(
                frame=i + 1,
                time_seconds=t,
                mount_kind="Mount",
                ra_raw_px=v if axis == "ra" else 0.0,
                dec_raw_px=v if axis == "dec" else 0.0,
                snr=20.0,
                star_mass=1000.0,
                error_code=0,
            )
        )
    return samples


class TestScipyAvailable:
    def test_akima1d_interpolator_imports(self):
        from scipy.interpolate import Akima1DInterpolator  # noqa: F401

    def test_akima_handles_monotone_series(self):
        x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        y = x**2
        interp = Akima1DInterpolator(x, y)
        assert interp(2.5) == pytest.approx(6.25, abs=0.5)

    def test_akima_does_not_overshoot_step(self):
        # Akima's defining property: no overshoot on step-like data.
        x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        y = np.array([0.0, 0.0, 1.0, 1.0, 1.0])
        interp = Akima1DInterpolator(x, y)
        v = float(interp(1.5))
        assert 0.0 <= v <= 1.0


class TestPipelineGuards:
    def test_too_short_section_skips(self):
        n = MIN_ENTRIES - 1
        samples = _make_samples(list(range(n)), [0.1] * n)
        result = compute_section_fft(samples, pixel_scale=1.0)
        assert result is not None
        assert result.skip_reason == "too_short"
        assert result.peaks == []
        assert result.period_s == []

    def test_non_uniform_cadence_skips(self):
        # Mix 1 s and 5 s gaps; IQR/median > 0.20 → skip.
        times = [0, 1, 2, 7, 8, 13, 14, 19, 20, 25, 26, 31, 32, 37]
        samples = _make_samples(times, [0.1] * len(times))
        result = compute_section_fft(samples, pixel_scale=1.0)
        assert result is not None
        assert result.skip_reason == "non_uniform_cadence"

    def test_uniform_cadence_passes_guard(self):
        times = list(range(20))
        samples = _make_samples(times, [0.1 * (i % 2) for i in range(20)])
        result = compute_section_fft(samples, pixel_scale=1.0)
        assert result is not None
        assert result.skip_reason is None

    def test_constant_data_skips(self):
        times = list(range(20))
        samples = _make_samples(times, [0.0] * 20)
        result = compute_section_fft(samples, pixel_scale=1.0)
        assert result is not None
        assert result.skip_reason == "constant_data"

    def test_drop_frames_excluded(self):
        # 11 valid + 1 DROP (None values) = 11 valid → MIN_ENTRIES not met.
        n = 11
        valid = _make_samples(list(range(n)), [0.1 * (i % 2) for i in range(n)])
        drop = GuidingSample(
            frame=n + 1,
            time_seconds=float(n),
            mount_kind="DROP",
            ra_raw_px=None,
            dec_raw_px=None,
            snr=None,
            star_mass=None,
            error_code=6,
        )
        result = compute_section_fft(valid + [drop], pixel_scale=1.0)
        assert result is not None
        assert result.skip_reason == "too_short"


class TestAmplitudeRecovery:
    """The 4/N Hamming scale over-estimates true peak amplitude by ~8 %
    (spec §M5); assertions allow that bias band."""

    def test_pure_sine_recovers_period(self):
        n = 100
        times = list(range(n))
        period = 20.0
        amp_px = 1.0
        values = [amp_px * math.sin(2 * math.pi * t / period) for t in times]
        samples = _make_samples(times, values)
        result = compute_section_fft(samples, pixel_scale=1.0)
        assert result is not None
        assert result.skip_reason is None
        assert len(result.peaks) >= 1
        top = max(result.peaks, key=lambda p: p.amplitude_arcsec)
        assert abs(top.period_s - period) / period < 0.05

    def test_pure_sine_amplitude_within_hamming_bias(self):
        n = 200
        times = list(range(n))
        period = 25.0
        amp_px = 0.5
        values = [amp_px * math.sin(2 * math.pi * t / period) for t in times]
        samples = _make_samples(times, values)
        result = compute_section_fft(samples, pixel_scale=2.0)
        assert result is not None
        top = max(result.peaks, key=lambda p: p.amplitude_arcsec)
        true_amp = amp_px * 2.0
        assert true_amp * 0.95 < top.amplitude_arcsec < true_amp * 1.15

    def test_pure_sine_derived_readouts_consistent(self):
        n = 200
        times = list(range(n))
        values = [0.5 * math.sin(2 * math.pi * t / 25.0) for t in times]
        samples = _make_samples(times, values)
        result = compute_section_fft(samples, pixel_scale=1.0)
        assert result is not None
        for peak in result.peaks:
            assert peak.peak_to_peak_arcsec == pytest.approx(2.0 * peak.amplitude_arcsec)
            assert peak.rms_arcsec == pytest.approx(peak.amplitude_arcsec / math.sqrt(2))

    def test_two_tone_recovers_both_peaks(self):
        n = 400
        times = list(range(n))
        values = [
            0.6 * math.sin(2 * math.pi * t / 20.0) + 1.0 * math.sin(2 * math.pi * t / 50.0)
            for t in times
        ]
        samples = _make_samples(times, values)
        result = compute_section_fft(samples, pixel_scale=1.0)
        assert result is not None
        periods = sorted(p.period_s for p in result.peaks)
        assert any(abs(p - 20.0) / 20.0 < 0.05 for p in periods)
        assert any(abs(p - 50.0) / 50.0 < 0.05 for p in periods)


class TestPeakDetection:
    def test_top_n_cap_at_max_peaks(self):
        n = 800
        times = list(range(n))
        targets = [
            (20.0, 1.0),
            (30.0, 0.9),
            (45.0, 0.8),
            (60.0, 0.7),
            (90.0, 0.6),
            (120.0, 0.55),
            (180.0, 0.5),
        ]
        values = [
            sum(amp * math.sin(2 * math.pi * t / period) for period, amp in targets) for t in times
        ]
        samples = _make_samples(times, values)
        result = compute_section_fft(samples, pixel_scale=1.0)
        assert result is not None
        assert len(result.peaks) <= MAX_PEAKS

    def test_dedup_within_5_percent(self):
        n = 200
        times = list(range(n))
        values = [1.0 * math.sin(2 * math.pi * t / 30.0) for t in times]
        samples = _make_samples(times, values)
        result = compute_section_fft(samples, pixel_scale=1.0)
        assert result is not None
        within_band = [p for p in result.peaks if 28.5 < p.period_s < 31.5]
        assert len(within_band) == 1

    def test_noise_floor_produces_zero_peaks(self):
        rng = np.random.default_rng(seed=42)
        n = 200
        times = list(range(n))
        values = (rng.normal(0, 1e-6, n)).tolist()
        samples = _make_samples(times, values)
        result = compute_section_fft(samples, pixel_scale=1.0)
        assert result is not None
        if result.skip_reason is None:
            assert result.peaks == []


class TestPixelScale:
    def test_pixel_scale_multiplied_into_amplitude(self):
        n = 200
        times = list(range(n))
        values = [1.0 * math.sin(2 * math.pi * t / 25.0) for t in times]
        samples = _make_samples(times, values)
        a1 = compute_section_fft(samples, pixel_scale=1.0)
        a4 = compute_section_fft(samples, pixel_scale=4.0)
        assert a1 is not None and a4 is not None
        top1 = max(a1.peaks, key=lambda p: p.amplitude_arcsec)
        top4 = max(a4.peaks, key=lambda p: p.amplitude_arcsec)
        assert top4.amplitude_arcsec == pytest.approx(4.0 * top1.amplitude_arcsec)

    def test_pixel_scale_none_leaves_amplitudes_in_pixels(self):
        n = 200
        times = list(range(n))
        values = [1.0 * math.sin(2 * math.pi * t / 25.0) for t in times]
        samples = _make_samples(times, values)
        result = compute_section_fft(samples, pixel_scale=None)
        assert result is not None
        top = max(result.peaks, key=lambda p: p.amplitude_arcsec)
        assert 0.95 < top.amplitude_arcsec < 1.15


class TestEdgeCases:
    def test_empty_samples_returns_none(self):
        assert compute_section_fft([], pixel_scale=1.0) is None

    def test_hamming_constant_documented(self):
        assert HAMMING_AMP_SCALE == 4.0
