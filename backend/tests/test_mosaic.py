from __future__ import annotations

import numpy as np
import pytest

from nightcrate.services.cfa import CfaPattern, PatternInfo
from nightcrate.services.mosaic import (
    Mosaic,
    channel_samples,
    colour_superpixels,
    display_rgb,
    measurement_grey,
)

BAYER = ("RGGB", "GRBG", "GBRG", "BGGR")
XTRANS = (
    "GRGGBG",
    "BGBRGR",
    "GRGGBG",
    "GBGGRG",
    "RGRBGB",
    "GBGGRG",
)


def _shift(pattern: CfaPattern, dy: int, dx: int) -> CfaPattern:
    return CfaPattern(
        tuple(
            "".join(pattern.colour_at(row + dy, column + dx) for column in range(pattern.width))
            for row in range(pattern.height)
        )
    )


def _mosaic(scene: np.ndarray, pattern: CfaPattern) -> Mosaic:
    indices = {"R": 0, "G": 1, "B": 2}
    recorded = np.empty(scene.shape[1:], dtype=np.float32)
    for row in range(recorded.shape[0]):
        for column in range(recorded.shape[1]):
            recorded[row, column] = scene[indices[pattern.colour_at(row, column)], row, column]
    return Mosaic(recorded, recorded.copy(), PatternInfo(pattern, "raw_file", "test"))


def _patch_scene(height: int = 64, width: int = 64) -> np.ndarray:
    scene = np.empty((3, height, width), dtype=np.float32)
    colours = ((1, 0, 0), (0, 1, 0), (0, 0, 1), (0.5, 0.5, 0.5))
    for index, colour in enumerate(colours):
        y = (index // 2) * (height // 2)
        x = (index % 2) * (width // 2)
        scene[:, y : y + height // 2, x : x + width // 2] = np.array(colour)[:, None, None]
    return scene


@pytest.mark.parametrize("text", BAYER)
def test_display_rgb_interior_exact_bayer(text):
    pattern = CfaPattern((text[:2], text[2:]))
    scene = _patch_scene()
    actual = display_rgb(_mosaic(scene, pattern))
    np.testing.assert_allclose(actual[:, 4:28, 4:28], scene[:, 4:28, 4:28], atol=1e-6)
    np.testing.assert_allclose(actual[:, 36:60, 36:60], scene[:, 36:60, 36:60], atol=1e-6)


@pytest.mark.parametrize("phase_y", range(6))
@pytest.mark.parametrize("phase_x", range(6))
def test_display_rgb_interior_exact_xtrans_every_phase(phase_y, phase_x):
    pattern = _shift(CfaPattern(XTRANS), phase_y, phase_x)
    scene = _patch_scene(72, 72)
    actual = display_rgb(_mosaic(scene, pattern))
    np.testing.assert_allclose(actual[:, 5:31, 5:31], scene[:, 5:31, 5:31], atol=1e-6)


@pytest.mark.parametrize("text", BAYER)
def test_channel_samples_exact(text):
    pattern = CfaPattern((text[:2], text[2:]))
    scene = np.stack([np.full((12, 14), value, dtype=np.float32) for value in (10, 20, 30)])
    channels = channel_samples(_mosaic(scene, pattern))
    assert channels["R"].size == 42
    assert channels["G"].size == 84
    assert channels["B"].size == 42
    np.testing.assert_array_equal(channels["R"], 10)
    np.testing.assert_array_equal(channels["G"], 20)
    np.testing.assert_array_equal(channels["B"], 30)


@pytest.mark.parametrize("rgb", [(1, 0, 0), (0, 1, 0), (0.5, 0.5, 0.5)])
@pytest.mark.parametrize("text", BAYER)
@pytest.mark.parametrize("phase_y", range(2))
@pytest.mark.parametrize("phase_x", range(2))
def test_grey_uniform_scene_every_bayer_phase(rgb, text, phase_y, phase_x):
    pattern = _shift(CfaPattern((text[:2], text[2:])), phase_y, phase_x)
    scene = np.stack([np.full((33, 35), value, dtype=np.float32) for value in rgb])
    grey, size = measurement_grey(_mosaic(scene, pattern))
    assert size == 2
    np.testing.assert_allclose(grey, np.mean(rgb), atol=1e-6)


@pytest.mark.parametrize("rgb", [(1, 0, 0), (0, 1, 0), (0.5, 0.5, 0.5)])
@pytest.mark.parametrize("phase_y", range(6))
@pytest.mark.parametrize("phase_x", range(6))
def test_grey_uniform_scene_every_xtrans_phase(rgb, phase_y, phase_x):
    pattern = _shift(CfaPattern(XTRANS), phase_y, phase_x)
    scene = np.stack([np.full((33, 35), value, dtype=np.float32) for value in rgb])
    grey, size = measurement_grey(_mosaic(scene, pattern))
    assert size == 3
    np.testing.assert_allclose(grey, np.mean(rgb), atol=1e-6)


def test_odd_dimensions_leave_incomplete_edge_out():
    pattern = CfaPattern(("RG", "GB"))
    scene = np.ones((3, 33, 35), dtype=np.float32)
    mosaic = _mosaic(scene, pattern)
    grey, size = measurement_grey(mosaic)
    superpixels = colour_superpixels(mosaic)
    assert size == 2
    assert grey.shape == (16, 17)
    assert superpixels.shape == (3, 16, 17)


def test_colour_superpixels_bayer():
    pattern = PatternInfo(CfaPattern(("RG", "GB")), "raw_file", "test")
    values = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    actual = colour_superpixels(Mosaic(values, values, pattern))
    np.testing.assert_allclose(actual[:, 0, 0], (0.1, 0.25, 0.4), atol=1e-6)


def test_measurement_grey_uses_normalised_samples_not_recorded_values():
    pattern = PatternInfo(CfaPattern(("RG", "GB")), "raw_file", "test")
    recorded = np.full((2, 2), 5000, dtype=np.uint16)
    normalised = np.array([[-0.2, 0.2], [0.6, 1.4]], dtype=np.float32)

    grey, size = measurement_grey(Mosaic(recorded, normalised, pattern))

    assert size == 2
    expected = (-0.2 + (0.2 + 0.6) / 2 + 1.4) / 3
    np.testing.assert_allclose(grey, [[expected]])
