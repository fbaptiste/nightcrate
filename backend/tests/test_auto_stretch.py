"""Tests for auto-stretch resolution, mid-range linearity detection,
and stretch=auto in render_image_png."""

import io

import numpy as np
import pytest
from PIL import Image

from nightcrate.services.imaging import (
    StretchParams,
    compute_image_stats,
    render_image_png,
    resolve_auto_stretch,
)


class TestResolveAutoStretch:
    def test_linear_mono_returns_stf(self):
        """Linear mono image should return STF stretch params."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.001, 0.01, size=(50, 60))
        linked, per_ch, _ = resolve_auto_stretch(data)
        assert linked.stretch == "stf"
        assert linked.shadow > 0
        assert linked.midtone < 0.1  # low midtone = linear data
        assert per_ch is None  # mono → no per-channel

    def test_nonlinear_mono_returns_linear(self):
        """Non-linear mono image (already stretched) should get linear passthrough."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.2, 0.8, size=(50, 60))  # high median → non-linear
        linked, per_ch, _ = resolve_auto_stretch(data)
        assert linked.stretch == "linear"
        assert per_ch is None

    def test_linear_color_returns_stf_with_per_channel(self):
        """Linear color image should return linked STF + per-channel STF."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.001, 0.01, size=(3, 50, 60))
        linked, per_ch, _ = resolve_auto_stretch(data)
        assert linked.stretch == "stf"
        assert per_ch is not None
        assert len(per_ch) == 3
        for ch in per_ch:
            assert ch.stretch == "stf"

    def test_nonlinear_color_returns_linear(self):
        """Non-linear color image should get linear passthrough, no per-channel."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.2, 0.8, size=(3, 50, 60))
        linked, per_ch, _ = resolve_auto_stretch(data)
        assert linked.stretch == "linear"
        assert per_ch is None


class TestMidRangeFraction:
    def test_mono_linear_has_zero_mid_range(self):
        """Linear mono data (low pixel values) should have ~0 mid-range fraction."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.001, 0.01, size=(50, 60))
        stats = compute_image_stats(data)
        assert stats.mid_range_fraction == pytest.approx(0.0, abs=1e-6)

    def test_mono_nonlinear_has_high_mid_range(self):
        """Non-linear mono data (spread across range) should have high mid-range fraction."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.2, 0.8, size=(50, 60))
        stats = compute_image_stats(data)
        assert stats.mid_range_fraction > 0.9

    def test_color_linear_has_zero_mid_range(self):
        """Linear color data should have ~0 mid-range fraction (luminance-weighted)."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.001, 0.01, size=(3, 50, 60))
        stats = compute_image_stats(data)
        assert stats.mid_range_fraction == pytest.approx(0.0, abs=1e-6)

    def test_color_nonlinear_has_high_mid_range(self):
        """Non-linear color data should have high mid-range fraction."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.2, 0.8, size=(3, 50, 60))
        stats = compute_image_stats(data)
        assert stats.mid_range_fraction > 0.9

    def test_threshold_boundary_below(self):
        """Data with mid-range fraction just below 0.001 should be treated as linear."""
        data = np.full((1000, 1), 0.05, dtype=np.float64)
        stats = compute_image_stats(data)
        assert stats.mid_range_fraction == 0.0
        linked, _, _ = resolve_auto_stretch(data, stats)
        assert linked.stretch == "stf"

    def test_threshold_boundary_above(self):
        """Data with mid-range fraction above 0.001 should be treated as non-linear."""
        data = np.full((1000, 1), 0.5, dtype=np.float64)
        stats = compute_image_stats(data)
        assert stats.mid_range_fraction == 1.0
        linked, _, _ = resolve_auto_stretch(data, stats)
        assert linked.stretch == "linear"

    def test_exact_boundary_values(self):
        """Pixels at exactly 0.1 and 0.9 should be counted in mid-range."""
        data = np.array([[0.1, 0.9, 0.05, 0.95]], dtype=np.float64)
        stats = compute_image_stats(data)
        assert stats.mid_range_fraction == pytest.approx(0.5)


class TestRenderAutoStretch:
    def test_auto_stretch_mono_produces_png(self):
        """stretch=auto on mono data should produce a valid PNG."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.001, 0.01, size=(50, 60))
        params = StretchParams(stretch="auto")
        png = render_image_png(data, linked=params)
        img = Image.open(io.BytesIO(png))
        assert img.mode == "L"
        assert img.size == (60, 50)

    def test_auto_stretch_color_produces_png(self):
        """stretch=auto on color data should produce a valid RGB PNG."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.001, 0.01, size=(3, 50, 60))
        params = StretchParams(stretch="auto")
        png = render_image_png(data, linked=params)
        img = Image.open(io.BytesIO(png))
        assert img.mode == "RGB"
        assert img.size == (60, 50)

    def test_auto_stretch_matches_manual_stf(self):
        """stretch=auto should produce the same result as manually applying STF params."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.001, 0.01, size=(50, 60))

        # Auto
        auto_png = render_image_png(data, linked=StretchParams(stretch="auto"))

        # Manual: compute stats, then apply STF
        stats = compute_image_stats(data)
        stf = stats.channels[0].stf
        manual_params = StretchParams(
            stretch="stf", shadow=stf.shadow, midtone=stf.midtone, highlight=stf.highlight
        )
        manual_png = render_image_png(data, linked=manual_params)

        assert auto_png == manual_png

    def test_auto_stretch_nonlinear_matches_linear(self):
        """stretch=auto on non-linear data should match stretch=linear."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.2, 0.8, size=(50, 60))

        auto_png = render_image_png(data, linked=StretchParams(stretch="auto"))
        linear_png = render_image_png(data, linked=StretchParams(stretch="linear"))

        assert auto_png == linear_png
