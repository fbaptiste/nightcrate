"""Tests for FITS file I/O — loading, headers, extension listing, stats, rendering."""

import io
from pathlib import Path

import pytest
from PIL import Image

from nightcrate.services.fits_io import list_extensions, load_image_data, read_header
from nightcrate.services.imaging import StretchParams, compute_image_stats, render_image_png


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

    def test_cards_have_description(self, tmp_fits_mono: Path):
        cards = read_header(tmp_fits_mono)
        exptime = next(c for c in cards if c["key"] == "EXPTIME")
        assert exptime["description"] == "Exposure time (sec)"

    def test_unknown_keyword_description_is_none(self, tmp_fits_mono: Path):
        cards = read_header(tmp_fits_mono)
        simple = next(c for c in cards if c["key"] == "SIMPLE")
        assert simple["description"] is None

    def test_invalid_hdu_raises(self, tmp_fits_mono: Path):
        with pytest.raises(ValueError, match="out of range"):
            read_header(tmp_fits_mono, hdu=99)


class TestListExtensions:
    def test_mono_file(self, tmp_fits_mono: Path):
        exts = list_extensions(tmp_fits_mono)
        assert len(exts) >= 1
        assert exts[0]["has_image"] is True
        assert exts[0]["index"] == 0

    def test_empty_hdu(self, tmp_fits_no_image: Path):
        exts = list_extensions(tmp_fits_no_image)
        assert exts[0]["has_image"] is False


class TestLoadImageData:
    def test_mono_shape(self, tmp_fits_mono: Path):
        data = load_image_data(tmp_fits_mono)
        assert data.ndim == 2
        assert data.shape == (100, 120)

    def test_color_shape(self, tmp_fits_color: Path):
        data = load_image_data(tmp_fits_color)
        assert data.ndim == 3
        assert data.shape == (3, 80, 100)

    def test_normalized_range(self, tmp_fits_mono: Path):
        data = load_image_data(tmp_fits_mono)
        assert data.min() >= 0.0
        assert data.max() <= 1.0


class TestImageStats:
    def test_mono_stats(self, tmp_fits_mono: Path):
        data = load_image_data(tmp_fits_mono)
        stats = compute_image_stats(data)
        assert stats.color is False
        assert len(stats.channels) == 1
        ch = stats.channels[0]
        assert 0.0 <= ch.min <= ch.median <= ch.max <= 1.0
        assert ch.mad >= 0.0

    def test_color_stats(self, tmp_fits_color: Path):
        data = load_image_data(tmp_fits_color)
        stats = compute_image_stats(data)
        assert stats.color is True
        assert len(stats.channels) == 3
        assert stats.linked_stf is not None

    def test_float32_stats(self, tmp_fits_float32: Path):
        data = load_image_data(tmp_fits_float32)
        stats = compute_image_stats(data)
        assert stats.color is False
        ch = stats.channels[0]
        assert ch.min >= 0.0
        assert ch.max <= 1.0


class TestRenderImagePng:
    def test_mono_default_stretch(self, tmp_fits_mono: Path):
        data = load_image_data(tmp_fits_mono)
        png = render_image_png(data)
        assert len(png) > 0
        img = Image.open(io.BytesIO(png))
        assert img.mode == "L"
        assert img.size == (120, 100)

    def test_color_default_stretch(self, tmp_fits_color: Path):
        data = load_image_data(tmp_fits_color)
        png = render_image_png(data)
        img = Image.open(io.BytesIO(png))
        assert img.mode == "RGB"
        assert img.size == (100, 80)

    def test_stf_stretch(self, tmp_fits_mono: Path):
        data = load_image_data(tmp_fits_mono)
        params = StretchParams(stretch="stf", shadow=0.01, midtone=0.05, highlight=1.0)
        png = render_image_png(data, linked=params)
        img = Image.open(io.BytesIO(png))
        assert img.mode == "L"

    def test_linear_stretch(self, tmp_fits_mono: Path):
        data = load_image_data(tmp_fits_mono)
        params = StretchParams(stretch="linear")
        png = render_image_png(data, linked=params)
        assert len(png) > 0

    def test_per_channel_color(self, tmp_fits_color: Path):
        data = load_image_data(tmp_fits_color)
        ch_params = [
            StretchParams(stretch="stf", shadow=0.01, midtone=0.1, highlight=1.0),
            StretchParams(stretch="stf", shadow=0.02, midtone=0.15, highlight=1.0),
            StretchParams(stretch="stf", shadow=0.01, midtone=0.12, highlight=1.0),
        ]
        png = render_image_png(data, per_channel=ch_params)
        img = Image.open(io.BytesIO(png))
        assert img.mode == "RGB"

    def test_no_image_data_raises(self, tmp_fits_no_image: Path):
        with pytest.raises(ValueError, match="no image data"):
            load_image_data(tmp_fits_no_image)
