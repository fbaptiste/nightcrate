"""Tests for STF auto-stretch computation and MTF."""

import numpy as np
import pytest

from nightcrate.services.fits import (
    StretchParams,
    _compute_stf,
    _mtf,
    _stretch_plane,
)


class TestMTF:
    def test_identity_at_half(self):
        """m=0.5 should be the identity function."""
        x = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        result = _mtf(x, 0.5)
        np.testing.assert_allclose(result, x, atol=1e-10)

    def test_endpoints(self):
        """MTF(0, m) = 0 and MTF(1, m) = 1 for any valid m."""
        for m in [0.01, 0.1, 0.25, 0.5, 0.75, 0.99]:
            x = np.array([0.0, 1.0])
            result = _mtf(x, m)
            assert result[0] == pytest.approx(0.0, abs=1e-10)
            assert result[1] == pytest.approx(1.0, abs=1e-10)

    def test_brightens_when_m_low(self):
        """Low m values should push midtones up (brighten)."""
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
        """MTF should be monotonically increasing for any valid m."""
        x = np.linspace(0, 1, 100)
        for m in [0.01, 0.1, 0.5, 0.9]:
            result = _mtf(x, m)
            assert np.all(np.diff(result) >= -1e-10)


class TestComputeStf:
    def test_typical_astro_background(self):
        """Typical uint16 sub: median ~0.023 (1500/65535), small MAD."""
        median = 1500 / 65535  # ~0.0229
        mad = 50 / 65535  # ~0.000763
        stf = _compute_stf(median, mad)

        assert stf.highlight == 1.0
        assert 0.0 <= stf.shadow < median
        assert 0.0 < stf.midtone < 0.5  # should be aggressive stretch

    def test_zero_mad(self):
        """Uniform image (MAD=0) should still produce valid params."""
        stf = _compute_stf(0.5, 0.0)
        assert stf.shadow == pytest.approx(0.5)  # median - 0 = median
        assert stf.midtone == 0.0  # med_clipped becomes 0
        assert stf.highlight == 1.0

    def test_very_bright_median(self):
        """Already bright image should get less aggressive stretch."""
        stf = _compute_stf(0.8, 0.01)
        assert stf.midtone > 0.3  # close to identity

    def test_shadow_clamped_to_zero(self):
        """Shadow clip should never go below 0."""
        stf = _compute_stf(0.001, 0.01)  # MAD >> median
        assert stf.shadow == 0.0


class TestStretchPlane:
    def test_stf_returns_uint8(self):
        plane = np.random.default_rng(1).uniform(0, 0.1, (10, 10))
        params = StretchParams(stretch="stf", shadow=0.01, midtone=0.05, highlight=1.0)
        result = _stretch_plane(plane, params)
        assert result.dtype == np.uint8
        assert result.shape == (10, 10)

    def test_linear_full_range(self):
        plane = np.linspace(0, 1, 100).reshape(10, 10)
        params = StretchParams(stretch="linear", black_pct=0, white_pct=100, gamma=1.0)
        result = _stretch_plane(plane, params)
        assert result.min() == 0
        assert result.max() == 255

    def test_linear_gamma_brightens(self):
        # Need a range of values so lo != hi
        plane = np.linspace(0, 1, 25).reshape(5, 5)
        no_gamma = _stretch_plane(plane, StretchParams(stretch="linear", gamma=1.0))
        with_gamma = _stretch_plane(plane, StretchParams(stretch="linear", gamma=2.0))
        # gamma > 1 should brighten midtones (higher output for mid-range input)
        mid = 2  # a row in the middle range
        assert with_gamma[mid, mid] > no_gamma[mid, mid]

    def test_asinh_returns_uint8(self):
        plane = np.random.default_rng(2).uniform(0, 0.1, (10, 10))
        params = StretchParams(stretch="asinh", black_pct=0, white_pct=100, asinh_beta=0.1)
        result = _stretch_plane(plane, params)
        assert result.dtype == np.uint8

    def test_stf_highlight_lte_shadow_returns_gray(self):
        plane = np.ones((5, 5)) * 0.5
        params = StretchParams(stretch="stf", shadow=0.6, midtone=0.5, highlight=0.3)
        result = _stretch_plane(plane, params)
        np.testing.assert_array_equal(result, 128)

    def test_uniform_plane_linear(self):
        plane = np.full((5, 5), 0.5)
        params = StretchParams(stretch="linear", black_pct=0, white_pct=100, gamma=1.0)
        result = _stretch_plane(plane, params)
        # All pixels identical — lo == hi, should return gray
        np.testing.assert_array_equal(result, 128)
