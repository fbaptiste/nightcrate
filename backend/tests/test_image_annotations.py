"""Tests for the image annotation service — WCS detection, projection, ellipse math."""

import math

import pytest

from nightcrate.services.image_annotation_models import WcsParams
from nightcrate.services.image_annotations import (
    build_wcs,
    compute_fov,
    compute_rotation,
    detect_wcs_from_cards,
    project_dsos,
)


def _make_cards(**kwargs: str) -> list[dict]:
    return [{"key": k, "value": v} for k, v in kwargs.items()]


ORION_WCS = WcsParams(
    crval1=83.633,
    crval2=-5.375,
    cd1_1=-0.000278,
    cd1_2=0.0,
    cd2_1=0.0,
    cd2_2=0.000278,
    crpix1=600.0,
    crpix2=500.0,
    naxis1=1200,
    naxis2=1000,
)


class TestDetectWcsFromCards:
    def test_complete_cd_matrix(self):
        cards = _make_cards(
            CRVAL1="83.633",
            CRVAL2="-5.375",
            CD1_1="-0.000278",
            CD1_2="0.0",
            CD2_1="0.0",
            CD2_2="0.000278",
            CRPIX1="600.0",
            CRPIX2="500.0",
            NAXIS1="1200",
            NAXIS2="1000",
            CTYPE1="RA---TAN",
            CTYPE2="DEC--TAN",
        )
        result = detect_wcs_from_cards(cards)
        assert result is not None
        assert result.crval1 == pytest.approx(83.633)
        assert result.crval2 == pytest.approx(-5.375)
        assert result.cd1_1 == pytest.approx(-0.000278)
        assert result.naxis1 == 1200

    def test_cdelt_crota_form(self):
        cards = _make_cards(
            CRVAL1="83.633",
            CRVAL2="-5.375",
            CDELT1="-0.000278",
            CDELT2="0.000278",
            CROTA2="45.0",
            CRPIX1="600.0",
            CRPIX2="500.0",
            NAXIS1="1200",
            NAXIS2="1000",
        )
        result = detect_wcs_from_cards(cards)
        assert result is not None
        cos_r = math.cos(math.radians(45.0))
        assert result.cd1_1 == pytest.approx(-0.000278 * cos_r)

    def test_missing_crval_returns_none(self):
        cards = _make_cards(
            CD1_1="-0.000278",
            CD1_2="0.0",
            CD2_1="0.0",
            CD2_2="0.000278",
            CRPIX1="600.0",
            CRPIX2="500.0",
            NAXIS1="1200",
            NAXIS2="1000",
        )
        assert detect_wcs_from_cards(cards) is None

    def test_missing_cd_and_cdelt_returns_none(self):
        cards = _make_cards(
            CRVAL1="83.633",
            CRVAL2="-5.375",
            CRPIX1="600.0",
            CRPIX2="500.0",
            NAXIS1="1200",
            NAXIS2="1000",
        )
        assert detect_wcs_from_cards(cards) is None

    def test_empty_cards_returns_none(self):
        assert detect_wcs_from_cards([]) is None


class TestBuildWcs:
    def test_round_trip(self):
        wcs = build_wcs(ORION_WCS)
        coord = wcs.pixel_to_world(600, 500)
        assert coord.ra.deg == pytest.approx(83.633, abs=0.001)
        assert coord.dec.deg == pytest.approx(-5.375, abs=0.001)

    def test_pixel_to_world_to_pixel(self):
        wcs = build_wcs(ORION_WCS)
        test_x, test_y = 300.0, 200.0
        sky = wcs.pixel_to_world(test_x, test_y)
        px, py = wcs.world_to_pixel(sky)
        assert float(px) == pytest.approx(test_x, abs=0.1)
        assert float(py) == pytest.approx(test_y, abs=0.1)


class TestComputeFov:
    def test_fov_dimensions(self):
        center_ra, center_dec, diag, fov_w, fov_h, scale = compute_fov(ORION_WCS)
        assert center_ra == pytest.approx(83.633, abs=0.01)
        assert center_dec == pytest.approx(-5.375, abs=0.01)
        expected_w = 0.000278 * 1200 * 3600 / 60
        expected_h = 0.000278 * 1000 * 3600 / 60
        assert fov_w == pytest.approx(expected_w, rel=0.05)
        assert fov_h == pytest.approx(expected_h, rel=0.05)
        assert scale == pytest.approx(0.000278 * 3600, rel=0.01)
        half_diag_arcmin = math.sqrt(fov_w**2 + fov_h**2) / 2.0
        assert diag == pytest.approx(half_diag_arcmin / 60.0, rel=0.05)


class TestComputeRotation:
    def test_no_rotation(self):
        assert compute_rotation(ORION_WCS) == pytest.approx(0.0, abs=0.01)

    def test_rotated(self):
        rotated = ORION_WCS.model_copy(
            update={"cd2_1": 0.000278, "cd2_2": 0.0},
        )
        assert compute_rotation(rotated) == pytest.approx(90.0, abs=0.01)


class TestProjectDsos:
    def test_dso_at_center_projects_to_crpix(self):
        dsos = [
            {
                "id": 1,
                "primary_designation": "TestDSO",
                "obj_type": "HII",
                "type_group": "Emission Nebula",
                "ra_deg": 83.633,
                "dec_deg": -5.375,
                "maj_axis_arcmin": 10.0,
                "min_axis_arcmin": 5.0,
                "position_angle_deg": 0.0,
                "common_name": "Test",
                "constellation": "Ori",
                "distance_pc": None,
                "distance_method": None,
                "mag_b": None,
            }
        ]
        results = project_dsos(ORION_WCS, dsos)
        assert len(results) == 1
        r = results[0]
        assert r.pixel_x == pytest.approx(600, abs=1)
        assert r.pixel_y == pytest.approx(500, abs=1)
        assert r.ellipse_semi_major_px is not None
        assert r.ellipse_semi_major_px > 0

    def test_dso_outside_fov_excluded(self):
        dsos = [
            {
                "id": 2,
                "primary_designation": "FarAway",
                "obj_type": "G",
                "type_group": "Galaxy",
                "ra_deg": 180.0,
                "dec_deg": 45.0,
                "maj_axis_arcmin": None,
                "min_axis_arcmin": None,
                "position_angle_deg": None,
                "common_name": None,
                "constellation": None,
                "distance_pc": None,
                "distance_method": None,
                "mag_b": None,
            }
        ]
        results = project_dsos(ORION_WCS, dsos)
        assert len(results) == 0

    def test_dso_without_angular_size(self):
        dsos = [
            {
                "id": 3,
                "primary_designation": "SmallDSO",
                "obj_type": "PN",
                "type_group": "Planetary Nebula",
                "ra_deg": 83.633,
                "dec_deg": -5.375,
                "maj_axis_arcmin": None,
                "min_axis_arcmin": None,
                "position_angle_deg": None,
                "common_name": None,
                "constellation": "Ori",
                "distance_pc": 500.0,
                "distance_method": "curated",
                "mag_b": 12.0,
            }
        ]
        results = project_dsos(ORION_WCS, dsos)
        assert len(results) == 1
        assert results[0].ellipse_semi_major_px is None

    def test_ellipse_dimensions_scale_with_angular_size(self):
        small = {
            "id": 10,
            "primary_designation": "Small",
            "obj_type": "G",
            "type_group": "Galaxy",
            "ra_deg": 83.633,
            "dec_deg": -5.375,
            "maj_axis_arcmin": 5.0,
            "min_axis_arcmin": 3.0,
            "position_angle_deg": 0.0,
            "common_name": None,
            "constellation": None,
            "distance_pc": None,
            "distance_method": None,
            "mag_b": None,
        }
        large = {
            **small,
            "id": 11,
            "primary_designation": "Large",
            "maj_axis_arcmin": 20.0,
            "min_axis_arcmin": 12.0,
        }
        results = project_dsos(ORION_WCS, [small, large])
        assert len(results) == 2
        small_r = next(r for r in results if r.id == 10)
        large_r = next(r for r in results if r.id == 11)
        assert large_r.ellipse_semi_major_px > small_r.ellipse_semi_major_px

    def test_empty_dso_list(self):
        assert project_dsos(ORION_WCS, []) == []
