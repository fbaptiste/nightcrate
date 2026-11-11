"""Tests for the image annotation service — WCS detection, projection, ellipse math."""

import math

import pytest
from astropy.io import fits
from astropy.wcs import WCS

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
        sin_r = math.sin(math.radians(45.0))
        assert result.cd1_1 == pytest.approx(-0.000278 * cos_r)
        assert result.cd1_2 == pytest.approx(-0.000278 * sin_r)
        assert result.cd2_1 == pytest.approx(-0.000278 * sin_r)
        assert result.cd2_2 == pytest.approx(0.000278 * cos_r)

    def test_cdelt_crota_matches_astropy(self):
        values = {
            "CRVAL1": 83.633,
            "CRVAL2": -5.375,
            "CDELT1": -2.0e-4,
            "CDELT2": 3.0e-4,
            "CROTA2": 30.0,
            "CRPIX1": 600.0,
            "CRPIX2": 500.0,
            "NAXIS1": 1200,
            "NAXIS2": 1000,
            "CTYPE1": "RA---TAN",
            "CTYPE2": "DEC--TAN",
        }
        cards = _make_cards(**{key: str(value) for key, value in values.items()})
        result = detect_wcs_from_cards(cards)
        assert result is not None

        header = fits.Header()
        for key, value in values.items():
            header[key] = value
        expected_x, expected_y = WCS(header).world_to_pixel_values(83.733, -5.275)
        actual_x, actual_y = build_wcs(result).world_to_pixel_values(83.733, -5.275)

        assert actual_x == pytest.approx(expected_x, abs=1e-6)
        assert actual_y == pytest.approx(expected_y, abs=1e-6)

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
                "other_names": ["Test Nebula", "Example Nebula"],
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
        assert r.other_names == ["Test Nebula", "Example Nebula"]

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

    def test_offframe_point_excluded_but_extended_overlap_included(self):
        # An object whose center projects just outside the frame: a point object
        # is excluded (would be clipped by the overlay → must not be counted),
        # while a large object whose extent still overlaps the frame is kept.
        wcs = build_wcs(ORION_WCS)
        coord = wcs.pixel_to_world(ORION_WCS.naxis1 + 30, 500)  # 30 px past right edge
        ra, dec = float(coord.ra.deg), float(coord.dec.deg)
        base = {
            "obj_type": "G",
            "type_group": "Galaxy",
            "ra_deg": ra,
            "dec_deg": dec,
            "min_axis_arcmin": None,
            "position_angle_deg": None,
            "common_name": None,
            "constellation": None,
            "distance_pc": None,
            "distance_method": None,
            "mag_b": None,
        }
        point = {**base, "id": 10, "primary_designation": "Point", "maj_axis_arcmin": None}
        extended = {**base, "id": 11, "primary_designation": "BigNeb", "maj_axis_arcmin": 60.0}
        ids = {r.id for r in project_dsos(ORION_WCS, [point, extended])}
        assert 10 not in ids  # off-frame point: not drawable → excluded
        assert 11 in ids  # extent overlaps the frame → kept

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

    @pytest.mark.parametrize(
        ("position_angle", "expected_angle"),
        [(0.0, 90.0), (45.0, 45.0), (104.0, 166.0), (170.0, 100.0)],
    )
    def test_ellipse_angle_uses_projected_axes(self, position_angle, expected_angle):
        scale = 4.5 / 3600.0
        params = WcsParams(
            crval1=170.0,
            crval2=13.0,
            cd1_1=-scale,
            cd1_2=0,
            cd2_1=0,
            cd2_2=-scale,
            crpix1=601,
            crpix2=451,
            naxis1=1200,
            naxis2=900,
        )
        result = project_dsos(params, [_ellipse_dso(position_angle)])[0]
        assert result.pixel_x == pytest.approx(600.0, abs=0.1)
        assert result.pixel_y == pytest.approx(450.0, abs=0.1)
        assert result.ellipse_angle_deg == pytest.approx(expected_angle, abs=0.5)

    @pytest.mark.parametrize(
        ("rotation", "position_angle"),
        [(rotation, pa) for rotation in (30.0, 90.0, 180.0, 270.0) for pa in (0, 45, 104, 170)],
    )
    def test_rotated_solution_angles(self, rotation, position_angle):
        scale = 4.5 / 3600.0
        angle = math.radians(rotation)
        params = WcsParams(
            crval1=170.0,
            crval2=13.0,
            cd1_1=-scale * math.cos(angle),
            cd1_2=scale * math.sin(angle),
            cd2_1=-scale * math.sin(angle),
            cd2_2=-scale * math.cos(angle),
            crpix1=601,
            crpix2=451,
            naxis1=1200,
            naxis2=900,
        )
        # Inverting CD rotates the north-up answer by -rotation in pixel space.
        expected = (90.0 - position_angle - rotation) % 180.0
        result = project_dsos(params, [_ellipse_dso(position_angle)])[0]
        assert result.ellipse_angle_deg == pytest.approx(expected, abs=0.5)

    @pytest.mark.parametrize("position_angle", (0.0, 45.0, 104.0, 170.0))
    @pytest.mark.parametrize(
        "updates",
        [
            {"cd1_1": 4.5 / 3600.0},
            {"cd2_2": 4.5 / 3600.0},
        ],
    )
    def test_mirror_and_bottom_up_angles(self, updates, position_angle):
        scale = 4.5 / 3600.0
        params = WcsParams(
            crval1=170.0,
            crval2=13.0,
            cd1_1=-scale,
            cd1_2=0,
            cd2_1=0,
            cd2_2=-scale,
            crpix1=601,
            crpix2=451,
            naxis1=1200,
            naxis2=900,
        ).model_copy(update=updates)
        result = project_dsos(params, [_ellipse_dso(position_angle)])[0]
        expected_angle = (position_angle - 90.0) % 180.0
        assert result.ellipse_angle_deg == pytest.approx(expected_angle, abs=0.5)

    @pytest.mark.parametrize(
        ("matrix", "expected_major", "expected_minor", "expected_angle"),
        [
            ((-2.0, 0.0, 0.0, -1.0), 49.12, 14.48, 77.60),
            ((-1.0, 0.1, 0.0, -1.0), 55.80, 25.49, 55.20),
        ],
    )
    def test_unequal_scale_and_skew(self, matrix, expected_major, expected_minor, expected_angle):
        scale = 4.5 / 3600.0
        params = WcsParams(
            crval1=170.0,
            crval2=13.0,
            cd1_1=matrix[0] * scale,
            cd1_2=matrix[1] * scale,
            cd2_1=matrix[2] * scale,
            cd2_2=matrix[3] * scale,
            crpix1=601,
            crpix2=451,
            naxis1=1200,
            naxis2=900,
        )
        result = project_dsos(params, [_ellipse_dso(30.0)])[0]
        assert result.ellipse_semi_major_px == pytest.approx(expected_major, abs=0.1)
        assert result.ellipse_semi_minor_px == pytest.approx(expected_minor, abs=0.1)
        assert result.ellipse_angle_deg == pytest.approx(expected_angle, abs=0.2)


def _ellipse_dso(position_angle: float) -> dict:
    return {
        "id": 101,
        "primary_designation": "Test ellipse",
        "obj_type": "G",
        "type_group": "Galaxy",
        "ra_deg": 170.0,
        "dec_deg": 13.0,
        "maj_axis_arcmin": 8.0,
        "min_axis_arcmin": 4.0,
        "position_angle_deg": position_angle,
        "common_name": None,
        "constellation": "Leo",
    }
