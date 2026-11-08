"""Regression tests for project thumbnail crop geometry and rendering."""

from __future__ import annotations

import math

import numpy as np
import pytest
from PIL import Image

from nightcrate.services.project_images import (
    CROP_SIZES,
    CropFrameError,
    check_crop_frame,
    fit_box,
    generate_cropped_thumbnail,
    render_crop,
)


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (2000, 1000, (0, -0.25, 1, 1.5)),
        (1000, 2000, (-5 / 6, 0, 8 / 3, 1)),
        (1000, 1000, (-1 / 6, 0, 4 / 3, 1)),
        (1200, 900, (0, 0, 1, 1)),
        (120, 100, (-1 / 18, 0, 10 / 9, 1)),
    ],
)
def test_fit_box(width: int, height: int, expected: tuple[float, float, float, float]):
    assert fit_box(width, height) == pytest.approx(expected)


@pytest.mark.parametrize(
    "frame",
    [
        fit_box(2000, 1000),
        (0.25, 0.125, 0.5, 0.75),
        (0.25, 0.125, 0.5, 0.75 * 1.004),
        (0.505, 0.12625, 0.5, 0.75),
    ],
)
def test_check_crop_frame_accepts_valid_frames(frame: tuple[float, float, float, float]):
    check_crop_frame(2000, 1000, *frame)


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        ((0, 0, 0.5, 0.5), "The frame must be 4:3."),
        ((0.6, 0.125, 0.5, 0.75), "The frame must stay within the picture and its mat."),
        ((0.25, 0.125, 0.5, 0.75 * 1.02), "The frame must be 4:3."),
        ((0.25, 0.125, 0.0004, 0.0006), "The frame is too small."),
    ],
)
def test_check_crop_frame_rejects_invalid_frames(
    frame: tuple[float, float, float, float], message: str
):
    with pytest.raises(CropFrameError, match=rf"^{message}$"):
        check_crop_frame(2000, 1000, *frame)


def test_render_landscape_fit_box_has_horizontal_mat():
    source = Image.new("RGB", (40, 20), "white")

    rendered = render_crop(source, *fit_box(*source.size), (480, 360))

    assert rendered.getpixel((240, 30)) == (0, 0, 0)
    assert rendered.getpixel((240, 180)) == (255, 255, 255)
    assert rendered.getpixel((240, 330)) == (0, 0, 0)
    pixels = np.asarray(rendered)
    filled_rows = np.flatnonzero(np.any(pixels != 0, axis=(1, 2)))
    assert filled_rows[0] == 60
    assert filled_rows[-1] == 299


def test_render_portrait_fit_box_has_vertical_mat():
    source = Image.new("RGB", (20, 40), "white")

    rendered = render_crop(source, *fit_box(*source.size), (480, 360))

    assert rendered.getpixel((60, 180)) == (0, 0, 0)
    assert rendered.getpixel((240, 180)) == (255, 255, 255)
    assert rendered.getpixel((420, 180)) == (0, 0, 0)
    pixels = np.asarray(rendered)
    filled_columns = np.flatnonzero(np.any(pixels != 0, axis=(0, 2)))
    assert filled_columns[0] == 150
    assert filled_columns[-1] == 329


def test_render_maps_frame_without_recomputing_it():
    pixels = np.empty((20, 40, 3), dtype=np.uint8)
    pixels[:, :20] = (220, 40, 20)
    pixels[:, 20:] = (20, 80, 220)
    source = Image.fromarray(pixels, mode="RGB")

    rendered = render_crop(source, 0.25, 0.125, 0.5, 0.75, (480, 360))

    assert rendered.getpixel((120, 180)) == (220, 40, 20)
    assert rendered.getpixel((360, 180)) == (20, 80, 220)


def test_render_preserves_mono_mode_and_adds_black_mat():
    source = Image.new("L", (40, 20), 255)

    rendered = render_crop(source, *fit_box(*source.size), (480, 360))

    assert rendered.mode == "L"
    assert rendered.getpixel((240, 30)) == 0
    assert rendered.getpixel((240, 180)) == 255


def test_render_odd_asymmetric_source_keeps_quadrants_and_mat():
    pixels = np.empty((19, 41, 3), dtype=np.uint8)
    pixels[:9, :20] = (220, 20, 20)
    pixels[:9, 20:] = (20, 220, 20)
    pixels[9:, :20] = (20, 20, 220)
    pixels[9:, 20:] = (220, 220, 20)
    source = Image.fromarray(pixels, mode="RGB")
    frame = (0.2, -0.15, 0.5, 0.75 * (41 / 19) * 0.5)

    rendered = render_crop(source, *frame, (480, 360))

    assert rendered.getpixel((240, 30)) == (0, 0, 0)
    assert rendered.getpixel((150, 150)) == (220, 20, 20)
    assert rendered.getpixel((380, 150)) == (20, 220, 20)
    assert rendered.getpixel((150, 330)) == pytest.approx((20, 20, 220), abs=2)
    assert rendered.getpixel((380, 330)) == pytest.approx((220, 220, 20), abs=2)


def test_render_preserves_known_square_proportions():
    pixels = np.zeros((20, 40, 3), dtype=np.uint8)
    pixels[6:14, 12:20] = 255
    source = Image.fromarray(pixels, mode="RGB")

    rendered = render_crop(source, *fit_box(*source.size), (480, 360))

    mask = np.all(np.asarray(rendered) > 128, axis=2)
    ys, xs = np.nonzero(mask)
    assert math.isclose(xs.max() - xs.min() + 1, 96, abs_tol=2)
    assert math.isclose(ys.max() - ys.min() + 1, 96, abs_tol=2)


@pytest.mark.parametrize(("size", "target"), CROP_SIZES.items())
def test_generate_cropped_thumbnail_writes_exact_size(tmp_path, size: str, target: tuple[int, int]):
    source_path = tmp_path / "source.png"
    output_path = tmp_path / f"{size}.jpg"
    Image.new("RGBA", (32, 24), (20, 80, 160, 128)).save(source_path)

    generate_cropped_thumbnail(str(source_path), 0, 0, 1, 1, output_path, size)

    with Image.open(output_path) as rendered:
        assert rendered.format == "JPEG"
        assert rendered.mode == "RGB"
        assert rendered.size == target
