"""Tests for STF auto-stretch computation and MTF."""

import numpy as np
import pytest

from nightcrate.services.imaging import (
    StretchParams,
    _compute_stf,
    _mtf,
    stretch_plane,
)


class TestMTF:
    def test_identity_at_half(self):
        x = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        result = _mtf(x, 0.5)
        np.testing.assert_allclose(result, x, atol=1e-10)

    def test_endpoints(self):
        for m in [0.01, 0.1, 0.25, 0.5, 0.75, 0.99]:
            x = np.array([0.0, 1.0])
            result = _mtf(x, m)
            assert result[0] == pytest.approx(0.0, abs=1e-10)
            assert result[1] == pytest.approx(1.0, abs=1e-10)

    def test_brightens_when_m_low(self):
        x = np.array([0.5])
        result_low = _mtf(x, 0.1)
        result_high = _mtf(x, 0.9)
        assert result_low[0] > result_high[0]

    def test_m_zero_returns_zeros(self):
        x = np.array([0.0, 0.5, 1.0])
        result = _mtf(x, 0.0)
        np.testing.assert_array_equal(result, np.zeros(3))

    def test_m_one_returns_ones(self):
        x = np.array([0.0, 0.5, 1.0])
        result = _mtf(x, 1.0)
        np.testing.assert_array_equal(result, np.ones(3))

    def test_monotonic(self):
        x = np.linspace(0, 1, 100)
        for m in [0.01, 0.1, 0.5, 0.9]:
            result = _mtf(x, m)
            assert np.all(np.diff(result) >= -1e-10)


class TestComputeStf:
    """Tests use avg_dev (average deviation), not MAD."""

    def test_typical_astro_background(self):
        median = 1500 / 65535  # ~0.023
        avg_dev = 50 / 65535  # ~0.00076
        stf = _compute_stf(median, avg_dev)
        assert stf.highlight == 1.0
        assert 0.0 <= stf.shadow < median
        # Low midtone = aggressive stretch for faint data
        assert 0.0 < stf.midtone < 0.05

    def test_zero_avg_dev(self):
        stf = _compute_stf(0.5, 0.0)
        assert stf.shadow == pytest.approx(0.5)
        assert stf.midtone == 0.0
        assert stf.highlight == 1.0

    def test_very_bright_median(self):
        # Bright image with small avg_dev: shadow clip is close to median,
        # b0 is small, so midtone is still aggressive (low value).
        # With large avg_dev, b0 grows and midtone approaches 0.5.
        stf_small_dev = _compute_stf(0.8, 0.01)
        stf_large_dev = _compute_stf(0.8, 0.3)
        assert stf_large_dev.midtone > stf_small_dev.midtone

    def test_shadow_clamped_to_zero(self):
        stf = _compute_stf(0.001, 0.01)
        assert stf.shadow == 0.0

    def test_mtf_self_inverse(self):
        """Verify: if m = MTF(b0, TARGET), then MTF(b0, m) ≈ TARGET."""
        from nightcrate.services.imaging import STF_TARGET_BG, _mtf_scalar

        median = 0.023
        avg_dev = 0.00076
        c0 = max(0, median + (-1.25) * avg_dev)
        b0 = median - c0
        m = _mtf_scalar(b0, STF_TARGET_BG)
        # Applying MTF with the computed midtone should give TARGET_BG
        result = _mtf_scalar(b0, m)
        assert result == pytest.approx(STF_TARGET_BG, abs=1e-6)


class TestStretchPlane:
    def test_stf_returns_uint8(self):
        plane = np.random.default_rng(1).uniform(0, 0.1, (10, 10))
        params = StretchParams(stretch="stf", shadow=0.01, midtone=0.05, highlight=1.0)
        result = stretch_plane(plane, params)
        assert result.dtype == np.uint8
        assert result.shape == (10, 10)

    def test_linear_full_range(self):
        plane = np.linspace(0, 1, 100).reshape(10, 10)
        params = StretchParams(stretch="linear")
        result = stretch_plane(plane, params)
        assert result.min() == 0
        assert result.max() == 255

    def test_linear_no_stretch(self):
        plane = np.linspace(0, 1, 25).reshape(5, 5)
        result = stretch_plane(plane, StretchParams(stretch="linear"))
        assert 126 <= result[2, 2] <= 130

    def test_stf_highlight_lte_shadow_returns_gray(self):
        plane = np.ones((5, 5)) * 0.5
        params = StretchParams(stretch="stf", shadow=0.6, midtone=0.5, highlight=0.3)
        result = stretch_plane(plane, params)
        np.testing.assert_array_equal(result, 128)

    def test_uniform_plane_linear(self):
        plane = np.full((5, 5), 0.5)
        params = StretchParams(stretch="linear")
        result = stretch_plane(plane, params)
        np.testing.assert_array_equal(result, 128)
