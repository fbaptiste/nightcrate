"""Tests for auto-stretch resolution and stretch=auto in render_image_png."""

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from nightcrate.services.imaging import (
    StretchParams,
    _resolve_auto_stretch,
    compute_image_stats,
    render_image_png,
)


class TestResolveAutoStretch:
    def test_linear_mono_returns_stf(self):
        """Linear mono image should return STF stretch params."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.001, 0.01, size=(50, 60))
        linked, per_ch = _resolve_auto_stretch(data)
        assert linked.stretch == "stf"
        assert linked.shadow > 0
        assert linked.midtone < 0.1  # low midtone = linear data
        assert per_ch is None  # mono → no per-channel

    def test_nonlinear_mono_returns_linear(self):
        """Non-linear mono image (already stretched) should get linear passthrough."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.2, 0.8, size=(50, 60))  # high median → non-linear
        linked, per_ch = _resolve_auto_stretch(data)
        assert linked.stretch == "linear"
        assert per_ch is None

    def test_linear_color_returns_stf_with_per_channel(self):
        """Linear color image should return linked STF + per-channel STF."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.001, 0.01, size=(3, 50, 60))
        linked, per_ch = _resolve_auto_stretch(data)
        assert linked.stretch == "stf"
        assert per_ch is not None
        assert len(per_ch) == 3
        for ch in per_ch:
            assert ch.stretch == "stf"

    def test_nonlinear_color_returns_linear(self):
        """Non-linear color image should get linear passthrough, no per-channel."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0.2, 0.8, size=(3, 50, 60))
        linked, per_ch = _resolve_auto_stretch(data)
        assert linked.stretch == "linear"
        assert per_ch is None


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
