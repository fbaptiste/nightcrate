from __future__ import annotations

import io

import numpy as np
from astropy.io import fits
from PIL import Image

from nightcrate.services.catalog_thumbnail import render_array_jpeg
from nightcrate.services.cfa import CfaPattern
from nightcrate.services.pixel_loader import display_of, grey_of, load_image, samples_of
from tests.fixtures.raw_fixtures import write_cfa_dng
from tests.test_pxiproject_io import _make_project
from tests.test_xisf_io import _make_xisf


def test_fits_bayer_is_mosaic(tmp_path):
    path = tmp_path / "bayer.fits"
    hdu = fits.PrimaryHDU(np.arange(48, dtype=np.uint16).reshape(6, 8))
    hdu.header["BAYERPAT"] = "RGGB"
    hdu.header["ROWORDER"] = "TOP-DOWN"
    hdu.writeto(path)
    image = load_image(str(path))
    assert image.kind == "mosaic"
    assert image.pattern.pattern.rows == ("RG", "GB")


def test_three_planes_with_bayerpat_is_colour(tmp_path):
    path = tmp_path / "colour.fits"
    hdu = fits.PrimaryHDU(np.arange(3 * 6 * 8, dtype=np.uint16).reshape(3, 6, 8))
    hdu.header["BAYERPAT"] = "RGGB"
    hdu.writeto(path)
    image = load_image(str(path))
    assert image.kind == "colour"
    assert image.pattern is None


def _write_xisf(path, pixels: np.ndarray, *, bounds=None, cfa=True):
    extra = (
        '<ColorFilterArray pattern="RGGB" width="2" height="2" name="Bayer RGGB" />' if cfa else ""
    )
    path.write_bytes(
        _make_xisf(
            pixels.shape[1],
            pixels.shape[0],
            1,
            "UInt16",
            pixels.astype(np.uint16).tobytes(),
            bounds=bounds,
            extra_children=extra,
        )
    )
    return path


def test_xisf_cfa_is_mosaic(tmp_path):
    path = _write_xisf(tmp_path / "mosaic.xisf", np.arange(48).reshape(6, 8))
    image = load_image(str(path))
    assert image.kind == "mosaic"
    assert image.pattern.source == "xisf_cfa"
    assert image.pattern.pattern.rows == ("RG", "GB")


def test_xisf_fits_keyword_pattern_is_fallback(tmp_path):
    pixels = np.arange(48, dtype=np.uint16).reshape(6, 8)
    path = tmp_path / "fits-pattern.xisf"
    path.write_bytes(
        _make_xisf(
            8,
            6,
            1,
            "UInt16",
            pixels.tobytes(),
            fits_keywords=[("BAYERPAT", "'BGGR'", ""), ("ROWORDER", "'TOP-DOWN'", "")],
        )
    )
    image = load_image(str(path))
    assert image.kind == "mosaic"
    assert image.pattern.source == "fits_bayerpat"
    assert image.pattern.pattern.rows == ("BG", "GR")


def test_pxiproject_reference_carries_pattern(tmp_path):
    xisf = _write_xisf(tmp_path / "referenced.xisf", np.arange(48).reshape(6, 8))
    project = _make_project(
        tmp_path,
        [{"name": "Reference", "file_path": str(xisf), "data_src": "unused"}],
    )
    image = load_image(f"{project}::0")
    assert image.kind == "mosaic"
    assert image.pattern.pattern.rows == ("RG", "GB")


def test_override_only_without_recorded_pattern(tmp_path):
    plain = tmp_path / "plain.fits"
    fits.PrimaryHDU(np.arange(48, dtype=np.uint16).reshape(6, 8)).writeto(plain)
    override = CfaPattern(("BG", "GR"))
    image = load_image(str(plain), pattern_override=override)
    assert image.kind == "mosaic"
    assert image.pattern.source == "user_choice"

    recorded = tmp_path / "recorded.fits"
    hdu = fits.PrimaryHDU(np.arange(48, dtype=np.uint16).reshape(6, 8))
    hdu.header["BAYERPAT"] = "RGGB"
    hdu.header["ROWORDER"] = "TOP-DOWN"
    hdu.writeto(recorded)
    image = load_image(str(recorded), pattern_override=override)
    assert image.pattern.source == "fits_bayerpat"
    assert image.pattern.pattern.rows == ("RG", "GB")


def test_grey_ignores_user_choice(tmp_path):
    values = np.arange(48, dtype=np.uint16).reshape(6, 8)
    path = tmp_path / "plain.fits"
    fits.PrimaryHDU(values).writeto(path)
    plain = load_image(str(path))
    override = load_image(str(path), pattern_override=CfaPattern(("RG", "GB")))
    np.testing.assert_array_equal(grey_of(override)[0], grey_of(plain)[0])
    assert grey_of(override)[1] == 1


def test_recorded_int16_fits_with_bzero(tmp_path):
    values = np.array([[0, 32768, 65535]], dtype=np.uint16)
    path = tmp_path / "unsigned.fits"
    fits.PrimaryHDU(values).writeto(path)
    image = load_image(str(path))
    np.testing.assert_array_equal(image.recorded, values)
    np.testing.assert_array_equal(samples_of(image)["L"], values)
    assert image.units == "adu"
    assert image.full_scale == 65535


def test_recorded_float_fits_above_one(tmp_path):
    values = np.array([[0.5, 2.0, 4.0]], dtype=np.float32)
    path = tmp_path / "float.fits"
    fits.PrimaryHDU(values).writeto(path)
    image = load_image(str(path))
    np.testing.assert_array_equal(image.recorded, values)
    np.testing.assert_allclose(image.normalised(), values / 4.0)
    assert image.units == "float"
    assert image.full_scale == 4.0


def test_recorded_xisf_with_bounds(tmp_path):
    values = np.array([[0, 2048, 4095]], dtype=np.uint16)
    path = _write_xisf(tmp_path / "bounded.xisf", values, bounds="0:4095", cfa=False)
    image = load_image(str(path))
    np.testing.assert_array_equal(image.recorded, values)
    np.testing.assert_allclose(image.normalised(), values / 4095.0, atol=1e-6)
    assert image.full_scale == 4095


def test_xisf_measurement_normalisation_keeps_samples_outside_bounds(tmp_path):
    values = np.array([[50, 100, 200, 250]], dtype=np.uint16)
    path = _write_xisf(tmp_path / "outside-bounds.xisf", values, bounds="100:200", cfa=False)

    image = load_image(str(path))

    np.testing.assert_allclose(image.normalised(), [[-0.5, 0.0, 1.0, 1.5]])
    np.testing.assert_allclose(image.denormalise(image.normalised()), values)
    np.testing.assert_allclose(display_of(image), [[0.0, 0.0, 1.0, 1.0]])
    with Image.open(io.BytesIO(render_array_jpeg(display_of(image), 32))) as output:
        rendered = np.asarray(output).copy()
    assert rendered.dtype == np.uint8
    assert int(rendered.min()) >= 0
    assert int(rendered.max()) <= 255


def test_recorded_uint16_raw_and_white_level_normalisation(tmp_path):
    values = np.full((32, 34), 512, dtype=np.uint16)
    values[0, 0] = 16383
    path = write_cfa_dng(tmp_path / "white.dng", values, white=16383)
    image = load_image(str(path))
    np.testing.assert_array_equal(image.recorded, values)
    assert samples_of(image)[image.pattern.pattern.colour_at(0, 0)].max() == 16383
    assert image.normalised()[0, 0] == 1.0
    assert image.recorded[0, 0] == 16383
    assert image.white_level == 16383
    assert image.full_scale == 16383
