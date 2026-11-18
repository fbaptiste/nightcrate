"""Colour measurement units, block coordinates, and solver restoration."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.api import aberration as aberration_api
from nightcrate.main import app
from nightcrate.services import plate_solve
from nightcrate.services.aberration import DetectionSettings, detect_stars
from nightcrate.services.cfa import CfaPattern, PatternInfo
from nightcrate.services.frame_quality import analyze_array, analyze_frame_file
from nightcrate.services.native_solver.models import TanWCS
from nightcrate.services.native_solver.solve_image import _sensor_wcs
from nightcrate.services.pixel_loader import LoadedImage, grey_of
from nightcrate.services.plate_solve import _restore_sensor_result
from nightcrate.services.plate_solve_models import PlateSolveResult
from tests.fixtures.raw_fixtures import write_cfa_dng


def _mosaic(recorded: np.ndarray, *, source="fits_bayerpat") -> LoadedImage:
    return LoadedImage(
        kind="mosaic",
        recorded=recorded,
        units="adu",
        pattern=PatternInfo(CfaPattern(("RG", "GB")), source, "test"),
        width=recorded.shape[1],
        height=recorded.shape[0],
        full_scale=65535.0,
        _normalise_mode="bounds",
        _normalise_max=65535.0,
    )


def test_frame_levels_use_recorded_sites_not_measurement_grey():
    image = _mosaic(np.array([[0, 0], [0, 120]], dtype=np.uint16))

    result = analyze_array(image, False)

    assert result["median_adu"] == 0.0
    assert result["quality_units"] == "adu"


def test_block_detection_returns_sensor_coordinates_and_settings():
    y, x = np.mgrid[:80, :80]
    data = 0.01 + 0.8 * np.exp(-((x - 30) ** 2 + (y - 20) ** 2) / 8.0)
    settings = DetectionSettings(
        min_star_snr=1,
        min_star_fwhm_px=1,
        min_separation_px=0,
        edge_margin_px=2,
    )

    result = detect_stars(data, settings, block_size=2, original_shape=(160, 160))

    assert result.image_width == result.image_height == 160
    assert result.settings == settings
    assert result.star_count == 1
    assert result.stars[0].x == pytest.approx(60.5, abs=0.2)
    assert result.stars[0].y == pytest.approx(40.5, abs=0.2)


def test_star_field_through_mosaic_matches_mono():
    y, x = np.mgrid[:160, :160]
    field = np.random.default_rng(42).normal(600.0, 20.0, size=(160, 160))
    for cx, cy in ((40, 40), (80, 55), (55, 110), (120, 120)):
        field += 30000 * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * 1.7**2))
    recorded = np.asarray(np.clip(field, 0, 65535), dtype=np.uint16)
    mono = LoadedImage(
        "mono",
        recorded,
        "adu",
        None,
        160,
        160,
        full_scale=65535.0,
        _normalise_mode="bounds",
        _normalise_max=65535.0,
    )
    mosaic = _mosaic(recorded)
    settings = DetectionSettings(min_star_fwhm_px=1, min_separation_px=20)

    mono_grey, mono_block = grey_of(mono)
    mosaic_grey, mosaic_block = grey_of(mosaic)
    mono_result = detect_stars(
        mono_grey, settings, block_size=mono_block, original_shape=(160, 160)
    )
    mosaic_result = detect_stars(
        mosaic_grey, settings, block_size=mosaic_block, original_shape=(160, 160)
    )

    assert mosaic_result.star_count == mono_result.star_count == 4
    assert mosaic_result.median_hfr == pytest.approx(mono_result.median_hfr, rel=0.1)
    assert mosaic_result.median_fwhm == pytest.approx(mono_result.median_fwhm, rel=0.1)
    for mosaic_star, mono_star in zip(mosaic_result.stars, mono_result.stars, strict=True):
        assert mosaic_star.x == pytest.approx(mono_star.x, abs=0.5)
        assert mosaic_star.y == pytest.approx(mono_star.y, abs=0.5)


@pytest.mark.anyio
async def test_view_pattern_choice_never_changes_quality(tmp_path: Path):
    path = tmp_path / "mono.fits"
    fits.PrimaryHDU(np.full((32, 32), 2000, dtype=np.uint16)).writeto(path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        plain = await client.get("/api/images/quality", params={"path": str(path)})
        chosen = await client.get(
            "/api/images/quality", params={"path": str(path), "pattern": "RGGB"}
        )

    assert plain.status_code == chosen.status_code == 200
    assert plain.json() == chosen.json()


def test_aberration_loader_honours_project_index(monkeypatch: pytest.MonkeyPatch):
    captured = None
    image = LoadedImage("mono", np.zeros((2, 3)), "float", None, 3, 2)

    def load(source, file_type, index, hdu):
        nonlocal captured
        captured = (source, file_type, index, hdu)
        return image

    monkeypatch.setattr(aberration_api, "load_resolved", load)
    mono, block, shape = aberration_api._load_mono_data(Path("project"), "pxiproject", 0, 7)

    assert captured == (Path("project"), "pxiproject", 7, 0)
    assert mono.shape == (2, 3)
    assert block == 1
    assert shape == (2, 3)


def test_aberration_cache_key_has_measurement_version():
    key = json.loads(aberration_api._settings_key(DetectionSettings()))
    assert key["measurement_version"] == 2


def test_native_and_astap_wcs_are_restored_to_sensor_pixels():
    working = TanWCS(
        crval_ra=10,
        crval_dec=20,
        cd=np.array([[0.0, -0.001], [0.001, 0.0]]),
        width=100,
        height=50,
    )
    restored = _sensor_wcs(working, 2, 200, 100)
    assert restored.width == 200
    assert restored.height == 100
    assert restored.cd == pytest.approx(working.cd / 2)
    assert restored.crpix == pytest.approx((100.5, 50.5))

    result = PlateSolveResult(
        solved=True,
        image_width=100,
        image_height=50,
        pixel_scale_arcsec=2.0,
        cd1_1=0.001,
        cd1_2=0.0,
        cd2_1=0.0,
        cd2_2=0.001,
        crpix1=50.5,
        crpix2=25.5,
        rms_px=0.4,
    )
    _restore_sensor_result(result, 2, 200, 100)
    assert result.pixel_scale_arcsec == 1.0
    assert (result.crpix1, result.crpix2) == pytest.approx((100.5, 50.5))
    assert result.rms_px == 0.8


def test_fourteen_bit_raw_quality_median_is_recorded_value(tmp_path: Path):
    pytest.importorskip("rawpy")
    pytest.importorskip("exiv2")
    samples = np.full((32, 32), 4096, dtype=np.uint16)
    path = write_cfa_dng(tmp_path / "constant.dng", samples, white=16383)

    result = analyze_frame_file(str(path), False)

    assert result["error"] is None
    assert result["median_adu"] == 4096.0
    assert result["quality_units"] == "adu"


@pytest.mark.anyio
async def test_astap_temp_raw_solution_full_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pytest.importorskip("rawpy")
    pytest.importorskip("exiv2")
    samples = np.arange(32 * 34, dtype=np.uint16).reshape(32, 34) + 512
    path = write_cfa_dng(tmp_path / "solve.dng", samples, white=16383)
    observed = {}

    async def fake_chain(_binary, image_file, **kwargs):
        observed["shape"] = fits.getdata(image_file).shape
        observed["scale"] = kwargs["scale_arcsec"]
        return PlateSolveResult(
            solved=True,
            image_width=17,
            image_height=16,
            pixel_scale_arcsec=3.0,
            cd1_1=0.001,
            cd1_2=0.0,
            cd2_1=0.0,
            cd2_2=0.001,
            crpix1=9.0,
            crpix2=8.5,
        )

    monkeypatch.setattr(plate_solve, "run_astap_chain", fake_chain)
    result = await plate_solve._do_solve(
        Path("/unused/astap"),
        str(path),
        0,
        None,
        None,
        None,
        30,
        scale_hint_arcsec=1.5,
    )

    assert observed == {"shape": (16, 17), "scale": 3.0}
    assert (result.image_width, result.image_height) == (34, 32)
    assert result.pixel_scale_arcsec == 1.5
    assert (result.crpix1, result.crpix2) == pytest.approx((17.5, 16.5))
