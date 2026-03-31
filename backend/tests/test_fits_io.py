"""Tests for FITS file I/O — loading, headers, HDU listing, stats, rendering."""

import io
from pathlib import Path

import pytest
from PIL import Image

from nightcrate.services.fits import (
    StretchParams,
    get_image_stats,
    is_color,
    list_hdus,
    read_header,
    render_image_png,
)


class TestReadHeader:
    def test_reads_standard_keywords(self, tmp_fits_mono: Path):
        cards = read_header(tmp_fits_mono)
        keys = {c["key"] for c in cards}
        assert "OBJECT" in keys
        assert "EXPTIME" in keys
        assert "FILTER" in keys

    def test_values_are_strings(self, tmp_fits_mono: Path):
        cards = read_header(tmp_fits_mono)
        for card in cards:
            assert isinstance(card["value"], str)

    def test_invalid_hdu_raises(self, tmp_fits_mono: Path):
        with pytest.raises(ValueError, match="out of range"):
            read_header(tmp_fits_mono, hdu=99)


class TestListHdus:
    def test_mono_file(self, tmp_fits_mono: Path):
        hdus = list_hdus(tmp_fits_mono)
        assert len(hdus) >= 1
        assert hdus[0]["has_image"] is True
        assert hdus[0]["index"] == 0

    def test_empty_hdu(self, tmp_fits_no_image: Path):
        hdus = list_hdus(tmp_fits_no_image)
        assert hdus[0]["has_image"] is False


class TestIsColor:
    def test_mono(self, tmp_fits_mono: Path):
        assert is_color(tmp_fits_mono) is False

    def test_color(self, tmp_fits_color: Path):
        assert is_color(tmp_fits_color) is True


class TestGetImageStats:
    def test_mono_stats(self, tmp_fits_mono: Path):
        stats = get_image_stats(tmp_fits_mono)
        assert stats.color is False
        assert len(stats.channels) == 1
        ch = stats.channels[0]
        assert 0.0 <= ch.min <= ch.median <= ch.max <= 1.0
        assert ch.mad >= 0.0
        assert 0.0 <= ch.stf.shadow <= 1.0
        assert 0.0 <= ch.stf.midtone <= 1.0

    def test_color_stats(self, tmp_fits_color: Path):
        stats = get_image_stats(tmp_fits_color)
        assert stats.color is True
        assert len(stats.channels) == 3
        assert stats.linked_stf is not None
        # Linked STF should come from the dimmest channel
        medians = [ch.median for ch in stats.channels]
        ref_idx = medians.index(min(medians))
        assert stats.linked_stf.shadow == stats.channels[ref_idx].stf.shadow

    def test_float32_stats(self, tmp_fits_float32: Path):
        stats = get_image_stats(tmp_fits_float32)
        assert stats.color is False
        ch = stats.channels[0]
        assert ch.min >= 0.0
        assert ch.max <= 1.0


class TestRenderImagePng:
    def test_mono_default_stretch(self, tmp_fits_mono: Path):
        png = render_image_png(tmp_fits_mono)
        assert len(png) > 0
        img = Image.open(io.BytesIO(png))
        assert img.mode == "L"
        assert img.size == (120, 100)  # (W, H) — matches our fixture

    def test_color_default_stretch(self, tmp_fits_color: Path):
        png = render_image_png(tmp_fits_color)
        img = Image.open(io.BytesIO(png))
        assert img.mode == "RGB"
        assert img.size == (100, 80)

    def test_stf_stretch(self, tmp_fits_mono: Path):
        params = StretchParams(stretch="stf", shadow=0.01, midtone=0.05, highlight=1.0)
        png = render_image_png(tmp_fits_mono, linked=params)
        img = Image.open(io.BytesIO(png))
        assert img.mode == "L"

    def test_linear_stretch(self, tmp_fits_mono: Path):
        params = StretchParams(stretch="linear")
        png = render_image_png(tmp_fits_mono, linked=params)
        assert len(png) > 0

    def test_per_channel_color(self, tmp_fits_color: Path):
        ch_params = [
            StretchParams(stretch="stf", shadow=0.01, midtone=0.1, highlight=1.0),
            StretchParams(stretch="stf", shadow=0.02, midtone=0.15, highlight=1.0),
            StretchParams(stretch="stf", shadow=0.01, midtone=0.12, highlight=1.0),
        ]
        png = render_image_png(tmp_fits_color, per_channel=ch_params)
        img = Image.open(io.BytesIO(png))
        assert img.mode == "RGB"

    def test_no_image_data_raises(self, tmp_fits_no_image: Path):
        with pytest.raises(ValueError, match="no image data"):
            render_image_png(tmp_fits_no_image)
