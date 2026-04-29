"""Tests for the plate solve service — .ini parsing, result computation,
ASTAP binary resolution, hint extraction, header passthrough, and coordinate formatting."""

import math

import numpy as np
import pytest
from astropy.io import fits as astro_fits

from nightcrate.services.coordinate_format import format_dec_dms, format_ra_hms
from nightcrate.services.plate_solve import (
    _build_astap_args,
    _coerce_header_value,
    _compute_results,
    _extract_hints,
    _parse_astap_ini,
    _write_temp_fits,
    resolve_astap_binary,
    validate_astap_path,
)

# ── resolve_astap_binary ────────────────────────────────────────────────


class TestResolveAstapBinary:
    def test_direct_executable(self, tmp_path):
        exe = tmp_path / "astap"
        exe.write_text("#!/bin/sh\nexit 0")
        exe.chmod(0o755)
        assert resolve_astap_binary(str(exe)) == exe

    def test_macos_app_bundle(self, tmp_path):
        app = tmp_path / "ASTAP.app"
        macos = app / "Contents" / "MacOS"
        macos.mkdir(parents=True)
        exe = macos / "astap"
        exe.write_text("#!/bin/sh")
        exe.chmod(0o755)
        assert resolve_astap_binary(str(app)) == exe

    def test_macos_app_bundle_uppercase(self, tmp_path):
        app = tmp_path / "ASTAP.app"
        macos = app / "Contents" / "MacOS"
        macos.mkdir(parents=True)
        exe = macos / "ASTAP"
        exe.write_text("#!/bin/sh")
        exe.chmod(0o755)
        result = resolve_astap_binary(str(app))
        assert result.parent == macos
        assert result.name.lower() == "astap"

    def test_macos_app_bundle_multiple_executables(self, tmp_path):
        """When multiple executables exist, prefer the one named 'astap'."""
        app = tmp_path / "ASTAP.app"
        macos = app / "Contents" / "MacOS"
        macos.mkdir(parents=True)
        for name in ("astap", "fpack", "funpack"):
            f = macos / name
            f.write_text("#!/bin/sh")
            f.chmod(0o755)
        assert resolve_astap_binary(str(app)).name == "astap"

    def test_nonexistent_path_raises(self):
        with pytest.raises(ValueError, match="not found"):
            resolve_astap_binary("/nonexistent/astap")

    def test_non_executable_raises(self, tmp_path):
        f = tmp_path / "astap"
        f.write_text("not executable")
        f.chmod(0o644)
        with pytest.raises(ValueError, match="not executable"):
            resolve_astap_binary(str(f))

    def test_app_bundle_no_contents_macos_raises(self, tmp_path):
        app = tmp_path / "Bad.app"
        app.mkdir()
        with pytest.raises(ValueError, match="no Contents/MacOS"):
            resolve_astap_binary(str(app))

    def test_app_bundle_empty_macos_raises(self, tmp_path):
        app = tmp_path / "Empty.app"
        macos = app / "Contents" / "MacOS"
        macos.mkdir(parents=True)
        with pytest.raises(ValueError, match="Could not locate"):
            resolve_astap_binary(str(app))


# ── validate_astap_path ─────────────────────────────────────────────────


class TestValidateAstapPath:
    def test_valid_path(self, tmp_path):
        exe = tmp_path / "astap"
        exe.write_text("#!/bin/sh")
        exe.chmod(0o755)
        result = validate_astap_path(str(exe))
        assert result["valid"] is True
        assert result["resolved_path"] == str(exe)
        assert result["error"] is None

    def test_invalid_path(self):
        result = validate_astap_path("/nonexistent/astap")
        assert result["valid"] is False
        assert result["resolved_path"] is None
        assert "not found" in result["error"]


# ── _parse_astap_ini ────────────────────────────────────────────────────


class TestParseAstapIni:
    def test_successful_solve(self, tmp_path):
        ini = tmp_path / "result.ini"
        ini.write_text(
            "PLTSOLVD=T                                     // T=true, F=false\n"
            "CRPIX1= 1.1645000000000000E+003                // X of reference pixel\n"
            "CRPIX2= 8.8050000000000000E+002                // Y of reference pixel\n"
            "CRVAL1= 1.5463033992314939E+002                // RA of reference pixel\n"
            "CRVAL2= 2.2039358425145043E+001                // Dec of reference pixel\n"
            "CDELT1=-7.4798001762187193E-004                // X pixel size\n"
            "CDELT2= 7.4845252983311850E-004                // Y pixel size\n"
            "CROTA1=-1.1668387329628058E+000                // twist X\n"
            "CROTA2=-1.1900321176194073E+000                // twist Y\n"
            "CD1_1=-7.4781868711882519E-004                 // CD matrix\n"
            "CD1_2= 1.5241315209850368E-005                 // CD matrix\n"
            "CD2_1= 1.5534412042060001E-005                 // CD matrix\n"
            "CD2_2= 7.4829732842251226E-004                 // CD matrix\n"
        )
        data = _parse_astap_ini(ini)
        assert data["PLTSOLVD"] == "T"
        assert float(data["CRVAL1"]) == pytest.approx(154.63, rel=1e-3)
        assert float(data["CRVAL2"]) == pytest.approx(22.039, rel=1e-3)
        assert float(data["CD2_2"]) == pytest.approx(7.483e-4, rel=1e-3)

    def test_failed_solve(self, tmp_path):
        ini = tmp_path / "result.ini"
        ini.write_text(
            "PLTSOLVD=F                                     // T=true, F=false\n"
            "ERROR=Not enough stars detected\n"
            "WARNING=Image may be out of focus\n"
        )
        data = _parse_astap_ini(ini)
        assert data["PLTSOLVD"] == "F"
        assert data["ERROR"] == "Not enough stars detected"
        assert data["WARNING"] == "Image may be out of focus"

    def test_strips_inline_comments(self, tmp_path):
        ini = tmp_path / "result.ini"
        ini.write_text("CRVAL1= 180.0                // RA in degrees\n")
        data = _parse_astap_ini(ini)
        assert float(data["CRVAL1"]) == pytest.approx(180.0)


# ── _compute_results ────────────────────────────────────────────────────


class TestComputeResults:
    def test_successful_solve_full(self):
        ini_data = {
            "PLTSOLVD": "T",
            "CRVAL1": "154.630340",
            "CRVAL2": "22.039358",
            "CD1_1": "-7.4781868711882519E-004",
            "CD1_2": "1.5241315209850368E-005",
            "CD2_1": "1.5534412042060001E-005",
            "CD2_2": "7.4829732842251226E-004",
            "CROTA2": "-1.1900321176194073",
        }
        result = _compute_results(ini_data, 4656, 3520)
        assert result.solved is True
        assert result.ra_deg == pytest.approx(154.63034, rel=1e-5)
        assert result.dec_deg == pytest.approx(22.039358, rel=1e-5)
        expected_scale = math.sqrt(1.5534412042060001e-5**2 + 7.4829732842251226e-4**2) * 3600.0
        assert result.pixel_scale_arcsec == pytest.approx(expected_scale, rel=1e-3)
        assert result.rotation_deg == pytest.approx(-1.19, rel=0.02)
        assert result.fov_width_arcmin is not None
        assert result.fov_height_arcmin is not None
        assert result.fov_width_arcmin == pytest.approx(expected_scale * 4656 / 60.0, rel=1e-3)
        assert result.fov_height_arcmin == pytest.approx(expected_scale * 3520 / 60.0, rel=1e-3)
        assert result.ra_hms is not None
        assert result.dec_dms is not None

    def test_failed_solve(self):
        ini_data = {
            "PLTSOLVD": "F",
            "ERROR": "No solution found",
            "WARNING": "Low star count",
        }
        result = _compute_results(ini_data, 4656, 3520)
        assert result.solved is False
        assert result.error_message == "No solution found"
        assert result.warning == "Low star count"
        assert result.ra_deg is None

    def test_pixel_scale_from_cd_matrix(self):
        ini_data = {
            "PLTSOLVD": "T",
            "CRVAL1": "180.0",
            "CRVAL2": "-30.0",
            "CD1_1": "-0.000278",
            "CD1_2": "0.0",
            "CD2_1": "0.0",
            "CD2_2": "0.000278",
            "CROTA2": "0.0",
        }
        result = _compute_results(ini_data, 100, 100)
        assert result.pixel_scale_arcsec == pytest.approx(0.000278 * 3600.0, rel=1e-3)

    def test_missing_image_dimensions(self):
        ini_data = {
            "PLTSOLVD": "T",
            "CRVAL1": "0.0",
            "CRVAL2": "0.0",
            "CD2_1": "0.0",
            "CD2_2": "0.000278",
            "CROTA2": "0.0",
        }
        result = _compute_results(ini_data, None, None)
        assert result.solved is True
        assert result.fov_width_arcmin is None
        assert result.fov_height_arcmin is None


# ── _extract_hints ──────────────────────────────────────────────────────


class TestExtractHints:
    def test_extracts_ra_dec_from_numeric_keywords(self):
        cards = [
            {"key": "RA", "value": "180.0"},
            {"key": "DEC", "value": "-30.0"},
        ]
        hints = _extract_hints(cards)
        assert hints["ra_hours"] == pytest.approx(12.0)
        assert hints["spd"] == pytest.approx(60.0)

    def test_extracts_ra_dec_from_hms_dms(self):
        cards = [
            {"key": "OBJCTRA", "value": "05 34 31.94"},
            {"key": "OBJCTDEC", "value": "+22 00 52.0"},
        ]
        hints = _extract_hints(cards)
        assert "ra_hours" in hints
        assert hints["ra_hours"] == pytest.approx(5.575539, rel=1e-3)
        assert hints["spd"] == pytest.approx(112.0144, rel=1e-3)

    def test_missing_coordinates_returns_no_position_hints(self):
        cards = [{"key": "OBJECT", "value": "M31"}]
        hints = _extract_hints(cards)
        assert "ra_hours" not in hints
        assert "spd" not in hints

    def test_estimates_fov_from_focal_length(self):
        cards = [
            {"key": "FOCALLEN", "value": "2800"},
            {"key": "XPIXSZ", "value": "3.76"},
            {"key": "NAXIS2", "value": "3520"},
        ]
        hints = _extract_hints(cards)
        assert "fov_deg" in hints
        plate_scale_arcsec = (3.76 / 2800.0) * 206.265
        expected_fov = plate_scale_arcsec * 3520 / 3600.0
        assert hints["fov_deg"] == pytest.approx(expected_fov, rel=1e-3)


# ── _build_astap_args ───────────────────────────────────────────────────


class TestBuildAstapArgs:
    def test_blind_solve(self, tmp_path):
        args = _build_astap_args(
            tmp_path / "astap",
            tmp_path / "image.fits",
            tmp_path / "out",
            mode="blind",
            hints={},
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
        )
        assert "-r" in args
        assert args[args.index("-r") + 1] == "180"
        assert "-update" not in args

    def test_near_solve_with_explicit_hints(self, tmp_path):
        args = _build_astap_args(
            tmp_path / "astap",
            tmp_path / "image.fits",
            tmp_path / "out",
            mode="near",
            hints={},
            ra_hint=180.0,
            dec_hint=-30.0,
            fov_hint=1.5,
        )
        assert args[args.index("-r") + 1] == "30"
        assert "-ra" in args
        assert args[args.index("-ra") + 1] == str(180.0 / 15.0)
        assert "-spd" in args
        assert args[args.index("-spd") + 1] == str(-30.0 + 90.0)
        assert "-fov" in args
        assert args[args.index("-fov") + 1] == "1.5"

    def test_auto_mode_with_header_hints_uses_near(self, tmp_path):
        hints = {"ra_hours": 12.0, "spd": 60.0}
        args = _build_astap_args(
            tmp_path / "astap",
            tmp_path / "image.fits",
            tmp_path / "out",
            mode="auto",
            hints=hints,
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
        )
        assert args[args.index("-r") + 1] == "30"
        assert "-ra" in args
        assert args[args.index("-ra") + 1] == "12.0"

    def test_auto_mode_without_hints_uses_blind(self, tmp_path):
        args = _build_astap_args(
            tmp_path / "astap",
            tmp_path / "image.fits",
            tmp_path / "out",
            mode="auto",
            hints={},
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
        )
        assert args[args.index("-r") + 1] == "180"

    def test_never_passes_update_flag(self, tmp_path):
        for mode in ("auto", "near", "blind"):
            args = _build_astap_args(
                tmp_path / "astap",
                tmp_path / "image.fits",
                tmp_path / "out",
                mode=mode,
                hints={},
                ra_hint=None,
                dec_hint=None,
                fov_hint=None,
            )
            assert "-update" not in args


# ── Coordinate formatting ───────────────────────────────────────────────


class TestCoordinateFormatting:
    def test_format_ra_hms(self):
        result = format_ra_hms(83.633)
        assert "h" in result
        assert "m" in result
        assert "s" in result

    def test_format_ra_zero(self):
        result = format_ra_hms(0.0)
        assert result.startswith("00h")

    def test_format_dec_positive(self):
        result = format_dec_dms(22.014)
        assert result.startswith("+")

    def test_format_dec_negative(self):
        result = format_dec_dms(-30.0)
        assert result.startswith("-")

    def test_format_dec_zero(self):
        result = format_dec_dms(0.0)
        assert result.startswith("+")


# ── _coerce_header_value ───────────────────────────────────────────────


class TestCoerceHeaderValue:
    def test_integer_string_returns_int(self):
        assert _coerce_header_value("42") == 42
        assert isinstance(_coerce_header_value("42"), int)

    def test_negative_integer(self):
        assert _coerce_header_value("-10") == -10
        assert isinstance(_coerce_header_value("-10"), int)

    def test_float_string_returns_float(self):
        assert _coerce_header_value("3.76") == pytest.approx(3.76)
        assert isinstance(_coerce_header_value("3.76"), float)

    def test_scientific_notation_returns_float(self):
        result = _coerce_header_value("2.69E-004")
        assert result == pytest.approx(2.69e-4)
        assert isinstance(result, float)

    def test_plain_string_returns_string(self):
        assert _coerce_header_value("ZWO ASI2600MM Pro") == "ZWO ASI2600MM Pro"
        assert isinstance(_coerce_header_value("ZWO ASI2600MM Pro"), str)

    def test_empty_string_returns_string(self):
        assert _coerce_header_value("") == ""

    def test_hms_coordinate_returns_string(self):
        assert _coerce_header_value("05 34 31.94") == "05 34 31.94"


# ── _write_temp_fits ───────────────────────────────────────────────────


class TestWriteTempFits:
    def test_uint16_data_written_directly(self, tmp_path):
        data = np.array([[100, 200], [300, 400]], dtype=np.uint16)
        path = _write_temp_fits(data, tmp_path)
        assert path.exists()
        with astro_fits.open(path) as hdul:
            assert hdul[0].data.dtype == np.uint16
            np.testing.assert_array_equal(hdul[0].data, data)

    def test_float_data_scaled_to_uint16(self, tmp_path):
        data = np.array([[0.0, 0.5], [0.75, 1.0]], dtype=np.float32)
        path = _write_temp_fits(data, tmp_path)
        with astro_fits.open(path) as hdul:
            assert hdul[0].data.dtype == np.uint16
            assert hdul[0].data[0, 0] == 0
            assert hdul[0].data[0, 1] == 32767
            assert hdul[0].data[1, 1] == 65535

    def test_no_header_keywords(self, tmp_path):
        data = np.zeros((10, 10), dtype=np.uint16)
        path = _write_temp_fits(data, tmp_path)
        with astro_fits.open(path) as hdul:
            assert "FOCALLEN" not in hdul[0].header

    def test_header_keywords_passthrough(self, tmp_path):
        data = np.zeros((10, 10), dtype=np.uint16)
        keywords = {
            "FOCALLEN": "2800",
            "XPIXSZ": "3.76",
            "INSTRUME": "ZWO ASI2600MM Pro",
            "RA": "180.0",
            "XBINNING": "2",
        }
        path = _write_temp_fits(data, tmp_path, header_keywords=keywords)
        with astro_fits.open(path) as hdul:
            h = hdul[0].header
            assert h["FOCALLEN"] == 2800
            assert h["XPIXSZ"] == pytest.approx(3.76)
            assert h["INSTRUME"] == "ZWO ASI2600MM Pro"
            assert h["RA"] == pytest.approx(180.0)
            assert h["XBINNING"] == 2

    def test_non_passthrough_keys_ignored(self, tmp_path):
        data = np.zeros((10, 10), dtype=np.uint16)
        keywords = {"OBJECT": "M31", "FOCALLEN": "500"}
        path = _write_temp_fits(data, tmp_path, header_keywords=keywords)
        with astro_fits.open(path) as hdul:
            assert "OBJECT" not in hdul[0].header
            assert hdul[0].header["FOCALLEN"] == 500

    def test_none_values_in_keywords_skipped(self, tmp_path):
        data = np.zeros((10, 10), dtype=np.uint16)
        keywords = {"FOCALLEN": "700", "XPIXSZ": None}
        path = _write_temp_fits(data, tmp_path, header_keywords=keywords)
        with astro_fits.open(path) as hdul:
            assert hdul[0].header["FOCALLEN"] == 700
            assert "XPIXSZ" not in hdul[0].header


# ── get_image_dimensions ───────────────────────────────────────────────


class TestGetImageDimensions:
    def test_fits_dimensions_from_header(self, tmp_path):
        from nightcrate.services.plate_solve import get_image_dimensions

        fits_path = tmp_path / "test.fits"
        data = np.zeros((100, 200), dtype=np.uint16)
        hdu = astro_fits.PrimaryHDU(data)
        hdu.writeto(fits_path)
        w, h = get_image_dimensions(str(fits_path))
        assert w == 200
        assert h == 100

    def test_fits_3d_dimensions(self, tmp_path):
        from nightcrate.services.plate_solve import get_image_dimensions

        fits_path = tmp_path / "color.fits"
        data = np.zeros((3, 80, 120), dtype=np.uint16)
        hdu = astro_fits.PrimaryHDU(data)
        hdu.writeto(fits_path)
        w, h = get_image_dimensions(str(fits_path))
        assert w == 120
        assert h == 80
