"""Tests for the plate solve service — .ini parsing, result computation,
ASTAP binary resolution, hint extraction, header passthrough, and coordinate formatting."""

import asyncio
import io
import logging
import math
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest
from astropy.io import fits as astro_fits

from nightcrate.services import plate_solve, solve_operations
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
from nightcrate.services.plate_solve_models import PlateSolveResult


def _reset_solve_state():
    solve_operations._reset_for_tests()
    plate_solve._solve_process = None
    plate_solve._astap_stop = None
    plate_solve._astap_task = None
    plate_solve._native_cancel = None
    plate_solve._native_task = None


def _cancel_active_solve() -> bool:
    operation = solve_operations.active_operation()
    assert operation is not None
    return solve_operations.cancel(operation.operation_id).cancelled


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
            "CRPIX1": "2328.5",
            "CRPIX2": "1760.5",
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
            "CRPIX1": "50.5",
            "CRPIX2": "50.5",
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
        assert result.solved is False
        assert result.error_message == "ASTAP returned an incomplete solution."
        assert result.fov_width_arcmin is None
        assert result.fov_height_arcmin is None

    def test_solved_flag_without_crpix_is_rejected(self):
        result = _compute_results(
            {
                "PLTSOLVD": "T",
                "CRVAL1": "180.0",
                "CRVAL2": "0.0",
                "CD1_1": "-0.0003",
                "CD1_2": "0.0",
                "CD2_1": "0.0",
                "CD2_2": "0.0003",
            },
            100,
            100,
        )
        assert not result.solved
        assert result.error_message == "ASTAP returned an incomplete solution."

    @pytest.mark.parametrize("include_crota", [True, False])
    def test_compute_results_flip(self, include_crota):
        ini_data = {
            "PLTSOLVD": "T",
            "CRVAL1": "24.174044",
            "CRVAL2": "15.783461",
            "CD1_1": "3.1708226849663004e-4",
            "CD1_2": "1.6613319845650712e-4",
            "CD2_1": "1.6618754352258259e-4",
            "CD2_2": "-3.1700913753065986e-4",
            "CRPIX1": "1504.5",
            "CRPIX2": "1504.5",
        }
        if include_crota:
            ini_data["CROTA2"] = "-152.33486201188387"

        result = _compute_results(ini_data, 3008, 3008, flip_rows=True)

        assert result.crpix1 == pytest.approx(1504.5)
        assert result.crpix2 == pytest.approx(1504.5)
        assert result.cd1_1 == pytest.approx(3.1708226849663004e-4)
        assert result.cd1_2 == pytest.approx(-1.6613319845650712e-4)
        assert result.cd2_1 == pytest.approx(1.6618754352258259e-4)
        assert result.cd2_2 == pytest.approx(3.1700913753065986e-4)
        assert result.rotation_deg == pytest.approx(27.657, abs=0.001)

    def test_compute_results_fits_input_is_unchanged(self):
        ini_data = {
            "PLTSOLVD": "T",
            "CRVAL1": "24.174044",
            "CRVAL2": "15.783461",
            "CD1_1": "3.1708226849663004e-4",
            "CD1_2": "1.6613319845650712e-4",
            "CD2_1": "1.6618754352258259e-4",
            "CD2_2": "-3.1700913753065986e-4",
            "CRPIX1": "1504.5",
            "CRPIX2": "1504.5",
            "CROTA2": "-152.33486201188387",
        }

        result = _compute_results(ini_data, 3008, 3008)

        assert result.crpix2 == pytest.approx(1504.5)
        assert result.cd1_2 == pytest.approx(1.6613319845650712e-4)
        assert result.cd2_2 == pytest.approx(-3.1700913753065986e-4)
        assert result.rotation_deg == pytest.approx(-152.335, abs=0.001)


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

    def test_pixel_fallback_failure_logs_debug_and_returns_missing(self, caplog):
        image_path = "/fake/missing-dimensions.fits"

        with (
            patch.object(
                plate_solve,
                "_resolve_path",
                return_value=(Path(image_path), "fits", 0, None),
            ),
            patch.object(plate_solve, "read_header_cards", return_value=[]),
            patch.object(plate_solve, "cards_to_dict", return_value={}),
            patch.object(plate_solve, "_get_dimensions_from_file", return_value=(None, None)),
            patch.object(
                plate_solve.fits_io,
                "load_image_data",
                side_effect=RuntimeError("pixel read failed"),
            ),
            caplog.at_level(logging.DEBUG, logger="nightcrate"),
        ):
            dimensions = plate_solve.get_image_dimensions(image_path)

        assert dimensions == (None, None)
        debug_records = [record for record in caplog.records if record.levelno == logging.DEBUG]
        assert len(debug_records) == 1
        assert debug_records[0].message.startswith("[plate-solve]")
        assert image_path in debug_records[0].message
        assert debug_records[0].exc_info is not None


# ── _run_astap ─────────────────────────────────────────────────────────


class TestRunAstap:
    @pytest.mark.parametrize("missing_stream", ["stdout", "stderr"])
    async def test_missing_process_stream_kills_waits_and_clears_progress(
        self, tmp_path, missing_stream
    ):
        class FakeProcess:
            def __init__(self):
                self.stdout = None if missing_stream == "stdout" else object()
                self.stderr = None if missing_stream == "stderr" else object()
                self.killed = False
                self.waited = False

            def kill(self):
                self.killed = True

            async def wait(self):
                self.waited = True

        proc = FakeProcess()

        async def fake_create_subprocess_exec(*_args, **_kwargs):
            return proc

        with (
            patch.object(
                plate_solve.asyncio,
                "create_subprocess_exec",
                fake_create_subprocess_exec,
            ),
            patch.object(plate_solve, "_solve_process", None),
        ):
            with pytest.raises(OSError, match="process streams are unavailable"):
                await plate_solve._run_astap(
                    ["astap", "image.fits"],
                    tmp_path / "result",
                    60,
                    None,
                    None,
                )

            assert proc.killed is True
            assert proc.waited is True


# ── Archive / BytesIO source handling ───────────────────────────────────


class TestArchiveSourceSolve:
    async def test_bytesio_source_not_closed_during_solve(self, tmp_fits_mono):
        """Regression: an archive-extracted BytesIO source gets closed by
        header reading (astropy closes file objects passed to fits.open).
        _do_solve must read its bytes once and reuse them so preparing the
        ASTAP temp file doesn't fail with 'I/O operation on closed file'."""
        raw = tmp_fits_mono.read_bytes()

        def fake_resolve(_path):
            return io.BytesIO(raw), "fits", 0, ("archive.zip", 1.0, "sub.fits")

        async def fake_chain(_binary, image_file, **_kwargs):
            assert image_file.suffix == ".fits"
            return PlateSolveResult(solved=True, ra_deg=210.0, dec_deg=54.0)

        with (
            patch.object(plate_solve, "_resolve_path", fake_resolve),
            patch.object(plate_solve, "run_astap_chain", fake_chain),
        ):
            result = await plate_solve._do_solve(
                Path("/fake/astap"),
                "archive.zip::sub.fits",
                hdu=0,
                ra_hint=None,
                dec_hint=None,
                fov_hint=None,
                timeout=60,
            )

        assert result.solved is True

    @pytest.mark.parametrize(
        ("image_path", "prepared_path", "expected_flip"),
        [
            ("X.PNG", "/images/X.PNG", True),
            ("a.zip::b.png", "/tmp/solve_input.fits", False),
            ("c.fits", "/images/c.fits", False),
        ],
    )
    async def test_flip_decision_by_input(self, image_path, prepared_path, expected_flip):
        observed: list[bool] = []

        async def fake_chain(_binary, image_file, **_kwargs):
            observed.append(image_file.suffix.lower() in plate_solve.STANDARD_EXTENSIONS)
            return PlateSolveResult(solved=True, ra_deg=210.0, dec_deg=54.0)

        with (
            patch.object(
                plate_solve,
                "_resolve_path",
                return_value=(Path("/source/input"), "standard", 0, None),
            ),
            patch.object(
                plate_solve,
                "read_header_cards",
                return_value=[
                    {"key": "NAXIS1", "value": "3008"},
                    {"key": "NAXIS2", "value": "3008"},
                ],
            ),
            patch.object(
                plate_solve,
                "_prepare_image_file",
                return_value=Path(prepared_path),
            ),
            patch.object(plate_solve, "run_astap_chain", fake_chain),
        ):
            await plate_solve._do_solve(
                Path("/fake/astap"),
                image_path,
                hdu=0,
                ra_hint=None,
                dec_hint=None,
                fov_hint=None,
                timeout=60,
            )

        assert observed == [expected_flip]


# ── Native/ASTAP dispatcher ────────────────────────────────────────────


async def test_run_solve_astap_success(tmp_path):
    _reset_solve_state()
    expected = PlateSolveResult(solved=True, ra_deg=12.0, dec_deg=-3.0)
    astap = tmp_path / "astap"
    astap.write_text("#!/bin/sh")
    astap.chmod(0o755)
    with patch.object(plate_solve, "_do_solve", new=AsyncMock(return_value=expected)) as call:
        result = await plate_solve.run_solve(
            solver="astap",
            astap_path=str(astap),
            image_path="image.fits",
            hdu=0,
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
            timeout=60,
        )
    assert result is expected
    call.assert_awaited_once()
    assert solve_operations.active_operation() is None


def _sleeping_astap(tmp_path: Path) -> Path:
    astap = tmp_path / "astap"
    astap.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n")
    astap.chmod(0o755)
    return astap


async def _wait_for_astap_process() -> asyncio.subprocess.Process:
    for _ in range(200):
        if plate_solve._solve_process is not None:
            return plate_solve._solve_process
        await asyncio.sleep(0.01)
    raise AssertionError("ASTAP process did not start")


async def test_astap_task_cancellation_waits_for_process_exit(tmp_path):
    _reset_solve_state()
    astap = _sleeping_astap(tmp_path)
    image = tmp_path / "image.fits"
    astro_fits.PrimaryHDU(np.zeros((10, 10), dtype=np.float32)).writeto(image)
    task = asyncio.create_task(
        plate_solve.run_solve(
            solver="astap",
            astap_path=str(astap),
            image_path=str(image),
            hdu=0,
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
            timeout=60,
        )
    )
    proc = await _wait_for_astap_process()

    task.cancel()
    assert solve_operations.active_operation() is not None
    with pytest.raises(asyncio.CancelledError):
        await task

    assert proc.returncode is not None
    assert plate_solve._solve_process is None
    assert solve_operations.active_operation() is None


async def test_cancel_solve_during_astap_preparation_prevents_process_start(tmp_path, monkeypatch):
    _reset_solve_state()
    astap = _sleeping_astap(tmp_path)
    image = tmp_path / "image.fits"
    astro_fits.PrimaryHDU(np.zeros((10, 10), dtype=np.float32)).writeto(image)
    started = threading.Event()
    release = threading.Event()
    temporary_dirs: list[Path] = []

    def blocked_prepare(source, _file_type, _image_index, _hdu, tmp_dir, **_kwargs):
        temporary_dirs.append(tmp_dir)
        started.set()
        release.wait(2)
        assert tmp_dir.exists()
        return source

    start_process = AsyncMock(side_effect=AssertionError("ASTAP started"))
    monkeypatch.setattr(plate_solve, "_prepare_image_file", blocked_prepare)
    monkeypatch.setattr(plate_solve.asyncio, "create_subprocess_exec", start_process)
    task = asyncio.create_task(
        plate_solve.run_solve(
            solver="astap",
            astap_path=str(astap),
            image_path=str(image),
            hdu=0,
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
            timeout=60,
        )
    )
    assert await asyncio.to_thread(started.wait, 1)

    assert _cancel_active_solve() is True
    await asyncio.sleep(0)
    assert solve_operations.active_operation() is not None
    assert not task.done()
    assert temporary_dirs[0].exists()
    release.set()
    result = await task

    start_process.assert_not_awaited()
    assert not result.solved
    assert result.error_message == "Solve cancelled."
    assert not temporary_dirs[0].exists()
    assert solve_operations.active_operation() is None


async def test_astap_source_read_runs_off_loop_and_cancel_starts_no_process(tmp_path, monkeypatch):
    _reset_solve_state()
    astap = _sleeping_astap(tmp_path)
    image = tmp_path / "image.fits"
    astro_fits.PrimaryHDU(np.zeros((10, 10), dtype=np.float32)).writeto(image)
    read_started = threading.Event()
    release_read = threading.Event()

    def blocked_resolve(_path):
        read_started.set()
        release_read.wait(2)
        return image, "fits", 0, None

    start_process = AsyncMock(side_effect=AssertionError("ASTAP started"))
    monkeypatch.setattr(plate_solve, "_resolve_path", blocked_resolve)
    monkeypatch.setattr(plate_solve.asyncio, "create_subprocess_exec", start_process)
    task = asyncio.create_task(
        plate_solve.run_solve(
            solver="astap",
            astap_path=str(astap),
            image_path=str(image),
            hdu=0,
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
            timeout=60,
        )
    )
    assert await asyncio.to_thread(read_started.wait, 1)

    loop_tick = asyncio.create_task(asyncio.sleep(0))
    await asyncio.wait_for(loop_tick, 0.2)
    assert _cancel_active_solve() is True
    assert not task.done()
    release_read.set()
    result = await task

    start_process.assert_not_awaited()
    assert not result.solved
    assert result.failure_reason == "cancelled"
    assert solve_operations.active_operation() is None


async def test_shutdown_during_astap_preparation_prevents_process_start(tmp_path, monkeypatch):
    _reset_solve_state()
    astap = _sleeping_astap(tmp_path)
    image = tmp_path / "image.fits"
    astro_fits.PrimaryHDU(np.zeros((10, 10), dtype=np.float32)).writeto(image)
    started = threading.Event()
    release = threading.Event()

    def blocked_prepare(source, *_args, **_kwargs):
        started.set()
        release.wait(2)
        return source

    start_process = AsyncMock(side_effect=AssertionError("ASTAP started"))
    monkeypatch.setattr(plate_solve, "_prepare_image_file", blocked_prepare)
    monkeypatch.setattr(plate_solve.asyncio, "create_subprocess_exec", start_process)
    task = asyncio.create_task(
        plate_solve.run_solve(
            solver="astap",
            astap_path=str(astap),
            image_path=str(image),
            hdu=0,
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
            timeout=60,
        )
    )
    assert await asyncio.to_thread(started.wait, 1)

    stopping = asyncio.create_task(plate_solve.shutdown())
    await asyncio.sleep(0)
    assert not stopping.done()
    assert solve_operations.active_operation() is not None
    release.set()
    await stopping
    result = await task

    start_process.assert_not_awaited()
    assert not result.solved
    assert result.error_message == "Solve cancelled."
    assert solve_operations.active_operation() is None


async def test_cancel_solve_between_astap_steps_prevents_blind(tmp_path, monkeypatch):
    _reset_solve_state()
    astap = _sleeping_astap(tmp_path)
    image = tmp_path / "image.fits"
    astro_fits.PrimaryHDU(np.zeros((10, 10), dtype=np.float32)).writeto(image)
    first_attempt_done = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def fake_run_astap_step(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AssertionError("ASTAP blind step started")
        first_attempt_done.set()
        await release.wait()
        return plate_solve._AstapRun(
            PlateSolveResult(solved=False, error_message="No solution found"), "no_match"
        )

    monkeypatch.setattr(plate_solve, "_run_astap_step", fake_run_astap_step)
    task = asyncio.create_task(
        plate_solve.run_solve(
            solver="astap",
            astap_path=str(astap),
            image_path=str(image),
            hdu=0,
            ra_hint=10.0,
            dec_hint=20.0,
            fov_hint=None,
            timeout=60,
        )
    )
    await first_attempt_done.wait()

    assert _cancel_active_solve() is True
    await asyncio.sleep(0)
    release.set()
    result = await task

    assert calls == 1
    assert not result.solved
    assert result.error_message == "Solve cancelled."
    assert result.failure_reason == "cancelled"


async def test_cancel_solve_during_astap_launch_kills_new_process(tmp_path, monkeypatch):
    _reset_solve_state()
    astap = _sleeping_astap(tmp_path)
    image = tmp_path / "image.fits"
    astro_fits.PrimaryHDU(np.zeros((10, 10), dtype=np.float32)).writeto(image)
    real_start = asyncio.create_subprocess_exec
    launching = asyncio.Event()
    release = asyncio.Event()
    started: list[asyncio.subprocess.Process] = []

    async def held_start(*args, **kwargs):
        launching.set()
        await release.wait()
        proc = await real_start(*args, **kwargs)
        started.append(proc)
        return proc

    monkeypatch.setattr(plate_solve.asyncio, "create_subprocess_exec", held_start)
    task = asyncio.create_task(
        plate_solve.run_solve(
            solver="astap",
            astap_path=str(astap),
            image_path=str(image),
            hdu=0,
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
            timeout=60,
        )
    )
    await asyncio.wait_for(launching.wait(), 2)

    assert plate_solve._solve_process is None
    assert _cancel_active_solve() is True
    release.set()
    result = await asyncio.wait_for(task, 5)

    assert len(started) == 1
    assert started[0].returncode is not None
    assert not result.solved
    assert result.error_message == "Solve cancelled."
    assert plate_solve._solve_process is None
    assert solve_operations.active_operation() is None


async def test_shutdown_waits_for_astap_process_exit(tmp_path):
    _reset_solve_state()
    astap = _sleeping_astap(tmp_path)
    image = tmp_path / "image.fits"
    astro_fits.PrimaryHDU(np.zeros((10, 10), dtype=np.float32)).writeto(image)
    task = asyncio.create_task(
        plate_solve.run_solve(
            solver="astap",
            astap_path=str(astap),
            image_path=str(image),
            hdu=0,
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
            timeout=60,
        )
    )
    proc = await _wait_for_astap_process()

    await plate_solve.shutdown()
    assert proc.returncode is not None
    await task
    assert plate_solve._solve_process is None
    assert solve_operations.active_operation() is None


async def test_astap_path_unchanged(tmp_path):
    _reset_solve_state()
    expected = PlateSolveResult(solved=True, ra_deg=12.0, dec_deg=-3.0)
    astap = tmp_path / "astap"
    astap.write_text("#!/bin/sh")
    astap.chmod(0o755)
    with patch.object(plate_solve, "_do_solve", new=AsyncMock(return_value=expected)) as call:
        result = await plate_solve.run_plate_solve(
            str(astap),
            "image.fits",
            hdu=2,
            ra_hint=12.0,
            dec_hint=-3.0,
            fov_hint=1.5,
            timeout=42,
        )

    assert result is expected
    assert call.await_args.args == (astap, "image.fits", 2, 12.0, -3.0, 1.5, 42)
    assert call.await_args.kwargs["operation"].solver == "astap"


def _patch_native_worker(monkeypatch, worker):
    from nightcrate.services.native_solver import solve_image as solve_image_module

    monkeypatch.setattr(
        plate_solve,
        "_resolve_path",
        lambda _path: (Path("/fake/image.fits"), "fits", 0, None),
    )
    monkeypatch.setattr(plate_solve, "read_header_cards", lambda *_args: [])
    monkeypatch.setattr(plate_solve, "get_image_dimensions", lambda *_args: (10, 10))
    monkeypatch.setattr(solve_image_module, "solve_image", worker)


async def _run_native(operation=None):
    return await plate_solve.run_solve(
        solver="native",
        astap_path=None,
        image_path="image.fits",
        hdu=0,
        ra_hint=None,
        dec_hint=None,
        fov_hint=None,
        timeout=60,
        operation=operation,
    )


async def test_run_solve_409_when_busy(monkeypatch):
    _reset_solve_state()
    started = threading.Event()
    release = threading.Event()

    def worker(*_args, **_kwargs):
        started.set()
        release.wait(2)
        return PlateSolveResult(solved=False, solver="native")

    _patch_native_worker(monkeypatch, worker)
    task = asyncio.create_task(_run_native())
    assert await asyncio.to_thread(started.wait, 1)
    with pytest.raises(RuntimeError, match="already in progress"):
        await _run_native()
    release.set()
    await task


async def test_native_header_read_off_event_loop(monkeypatch):
    _reset_solve_state()
    from nightcrate.services.native_solver import solve_image as solve_image_module

    event_loop_thread = threading.current_thread()
    observed_threads: list[threading.Thread] = []
    detections = solve_image_module.DetectedStars(
        np.empty(0),
        np.empty(0),
        np.empty(0),
        np.empty(0),
        10,
        10,
    )

    def read_cards(*_args):
        observed_threads.append(threading.current_thread())
        return [
            {"key": "RA", "value": 83.82},
            {"key": "DEC", "value": -5.39},
        ]

    monkeypatch.setattr(solve_image_module, "installed", lambda: object())
    monkeypatch.setattr(solve_image_module, "built_ranges", lambda: set())
    monkeypatch.setattr(solve_image_module, "built_layers", lambda: [])
    monkeypatch.setattr(solve_image_module.handles, "get_catalog", lambda: object())
    monkeypatch.setattr(solve_image_module.handles, "get_layers", lambda _names: [])
    monkeypatch.setattr(
        solve_image_module.pixel_loader,
        "resolve",
        lambda _path: (object(), "fits", 0),
    )
    monkeypatch.setattr(
        solve_image_module.pixel_loader,
        "load_normalized_mono",
        lambda _path, _hdu: np.zeros((10, 10), dtype=np.float32),
    )
    monkeypatch.setattr(solve_image_module, "extract_near", lambda *_args, **_kwargs: detections)
    monkeypatch.setattr(plate_solve, "read_header_cards", read_cards)

    operation = solve_operations.claim(uuid4(), "native")
    try:
        result = await _run_native(operation)
    finally:
        solve_operations.release(operation)
    snapshot = solve_operations.snapshot(operation.operation_id)

    assert not result.solved
    assert observed_threads
    assert observed_threads[0] is not event_loop_thread
    assert result.attempts[0].step == "load"
    assert result.attempts[0].position_source == "header"
    assert snapshot is not None
    assert snapshot.attempts[0].step == "load"
    assert snapshot.attempts[0].position_source == "header"


async def test_cancel_route_releases_slot_after_worker_stops(monkeypatch):
    _reset_solve_state()
    started = threading.Event()
    cancel_seen = threading.Event()
    release = threading.Event()

    def worker(*_args, cancel, **_kwargs):
        started.set()
        cancel.wait(1)
        cancel_seen.set()
        release.wait(2)
        return PlateSolveResult(solved=False, solver="native", failure_reason="cancelled")

    _patch_native_worker(monkeypatch, worker)
    task = asyncio.create_task(_run_native())
    assert await asyncio.to_thread(started.wait, 1)
    assert _cancel_active_solve() is True
    assert await asyncio.to_thread(cancel_seen.wait, 1)
    with pytest.raises(plate_solve.SolveSlotBusy):
        async with plate_solve.solve_slot():
            pass
    release.set()
    await task
    async with plate_solve.solve_slot():
        pass


async def test_task_cancellation_waits_for_worker(monkeypatch):
    _reset_solve_state()
    started = threading.Event()
    cancel_seen = threading.Event()
    release = threading.Event()

    def worker(*_args, cancel, **_kwargs):
        started.set()
        cancel.wait(1)
        cancel_seen.set()
        release.wait(2)
        return PlateSolveResult(solved=False, solver="native", failure_reason="cancelled")

    _patch_native_worker(monkeypatch, worker)
    task = asyncio.create_task(_run_native())
    assert await asyncio.to_thread(started.wait, 1)
    task.cancel()
    assert await asyncio.to_thread(cancel_seen.wait, 1)
    await asyncio.sleep(0)
    assert solve_operations.active_operation() is not None
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert solve_operations.active_operation() is None


async def test_double_cancellation_waits_for_worker(monkeypatch):
    _reset_solve_state()
    started = threading.Event()
    cancel_seen = threading.Event()
    release = threading.Event()

    def worker(*_args, cancel, **_kwargs):
        started.set()
        cancel.wait(1)
        cancel_seen.set()
        release.wait(2)
        return PlateSolveResult(solved=False, solver="native", failure_reason="cancelled")

    _patch_native_worker(monkeypatch, worker)
    task = asyncio.create_task(_run_native())
    assert await asyncio.to_thread(started.wait, 1)
    task.cancel()
    assert await asyncio.to_thread(cancel_seen.wait, 1)
    task.cancel()
    await asyncio.sleep(0)
    assert solve_operations.active_operation() is not None
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert solve_operations.active_operation() is None


async def test_shutdown_waits_for_worker_and_closes_handles(monkeypatch):
    _reset_solve_state()
    started = threading.Event()

    def worker(*_args, cancel, **_kwargs):
        started.set()
        cancel.wait(2)
        return PlateSolveResult(solved=False, solver="native", failure_reason="cancelled")

    _patch_native_worker(monkeypatch, worker)
    close_all = MagicMock()
    monkeypatch.setattr(plate_solve.handles, "close_all", close_all)
    task = asyncio.create_task(_run_native())
    assert await asyncio.to_thread(started.wait, 1)
    await plate_solve.shutdown()
    await task
    close_all.assert_called_once_with()


async def test_shutdown_leaves_mappings_when_worker_outlives_timeout(monkeypatch):
    _reset_solve_state()
    started = threading.Event()
    release = threading.Event()

    def worker(*_args, **_kwargs):
        started.set()
        release.wait(2)
        return PlateSolveResult(solved=False, solver="native")

    _patch_native_worker(monkeypatch, worker)
    close_all = MagicMock()
    monkeypatch.setattr(plate_solve.handles, "close_all", close_all)

    async def immediate_timeout(_awaitable, timeout):
        assert timeout == 10.0
        raise TimeoutError

    monkeypatch.setattr(plate_solve.asyncio, "wait_for", immediate_timeout)
    task = asyncio.create_task(_run_native())
    assert await asyncio.to_thread(started.wait, 1)
    await plate_solve.shutdown()
    close_all.assert_not_called()
    assert solve_operations.active_operation() is not None
    release.set()
    await task


async def test_no_gpu_during_solve(monkeypatch):
    _reset_solve_state()
    from nightcrate.core import compute
    from nightcrate.services import imaging

    before = compute._gpu_enabled
    fail = MagicMock(side_effect=AssertionError("GPU backend called"))
    monkeypatch.setattr(compute, "get_array_module", fail)
    monkeypatch.setattr(compute, "set_gpu_enabled", fail)
    monkeypatch.setattr(imaging, "get_array_module", fail)

    def worker(*_args, **_kwargs):
        return PlateSolveResult(solved=False, solver="native")

    _patch_native_worker(monkeypatch, worker)
    await _run_native()
    fail.assert_not_called()
    assert compute._gpu_enabled == before


# ── Structured ASTAP chain ─────────────────────────────────────────────


_VALID_ASTAP_INI = """PLTSOLVD=T
CRVAL1=120.0
CRVAL2=30.0
CRPIX1=50.5
CRPIX2=40.5
CD1_1=-0.0003
CD1_2=0.0
CD2_1=0.0
CD2_2=0.0003
"""


def _scripted_astap(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "astap"
    script.write_text("#!/usr/bin/env python3\n" + body)
    script.chmod(0o755)
    return script


async def _run_chain(
    binary: Path,
    image: Path,
    *,
    position=(120.0, 30.0),
    scale=1.5,
    timeout=2.0,
):
    operation = solve_operations.claim(uuid4(), "astap")
    try:
        result = await plate_solve.run_astap_chain(
            binary,
            image,
            position=position,
            scale_arcsec=scale,
            image_width=100,
            image_height=80,
            deadline=time.monotonic() + timeout,
            stop=operation.stop,
            reporter=operation,
            operation=operation,
        )
        return result, operation.attempts()
    finally:
        solve_operations.release(operation)


async def test_astap_near_miss_advances_to_blind(tmp_path):
    _reset_solve_state()
    calls = tmp_path / "calls"
    astap = _scripted_astap(
        tmp_path,
        f"""import pathlib, sys
calls = pathlib.Path({str(calls)!r})
count = int(calls.read_text()) + 1 if calls.exists() else 1
calls.write_text(str(count))
if count == 1:
    raise SystemExit(1)
out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1] + '.ini')
out.write_text({_VALID_ASTAP_INI!r})
""",
    )
    image = tmp_path / "image.fits"
    image.write_bytes(b"input")

    result, attempts = await _run_chain(astap, image)

    assert result.solved
    assert calls.read_text() == "2"
    assert [attempt.step for attempt in attempts] == ["astap_near", "astap_blind"]
    assert [attempt.outcome for attempt in attempts] == ["no_match", "solved"]


async def test_astap_near_timeout_advances_to_blind(tmp_path, monkeypatch):
    _reset_solve_state()
    calls = tmp_path / "calls"
    astap = _scripted_astap(
        tmp_path,
        f"""import pathlib, sys, time
calls = pathlib.Path({str(calls)!r})
count = int(calls.read_text()) + 1 if calls.exists() else 1
calls.write_text(str(count))
radius = sys.argv[sys.argv.index('-r') + 1]
if radius == '30':
    time.sleep(0.2)
else:
    pathlib.Path(sys.argv[sys.argv.index('-o') + 1] + '.ini').write_text({_VALID_ASTAP_INI!r})
""",
    )
    image = tmp_path / "image.fits"
    image.write_bytes(b"input")
    monkeypatch.setattr(plate_solve, "_ASTAP_NEAR_SECONDS", 0.05)

    result, attempts = await _run_chain(astap, image)

    assert result.solved
    assert [attempt.outcome for attempt in attempts] == ["step_timeout", "solved"]


async def test_astap_database_error_stops_chain(tmp_path):
    _reset_solve_state()
    calls = tmp_path / "calls"
    astap = _scripted_astap(
        tmp_path,
        f"""import pathlib
calls = pathlib.Path({str(calls)!r})
calls.write_text(str(int(calls.read_text()) + 1 if calls.exists() else 1))
raise SystemExit(32)
""",
    )
    image = tmp_path / "image.fits"
    image.write_bytes(b"input")

    result, attempts = await _run_chain(astap, image)

    assert not result.solved
    assert "database" in result.error_message.lower()
    assert result.failure_reason == "error"
    assert calls.read_text() == "1"
    assert attempts[0].outcome == "error"


async def test_astap_too_few_stars_has_shared_failure_reason(tmp_path):
    _reset_solve_state()
    astap = _scripted_astap(tmp_path, "raise SystemExit(2)\n")
    image = tmp_path / "image.fits"
    image.write_bytes(b"input")

    result, attempts = await _run_chain(astap, image, position=None)

    assert not result.solved
    assert result.failure_reason == "too_few_stars"
    assert attempts[0].outcome == "too_few_stars"


async def test_astap_stale_ini_is_not_reused_by_blind_step(tmp_path):
    _reset_solve_state()
    calls = tmp_path / "calls"
    astap = _scripted_astap(
        tmp_path,
        f"""import pathlib, sys
calls = pathlib.Path({str(calls)!r})
count = int(calls.read_text()) + 1 if calls.exists() else 1
calls.write_text(str(count))
if count == 1:
    pathlib.Path(sys.argv[sys.argv.index('-o') + 1] + '.ini').write_text({_VALID_ASTAP_INI!r})
    raise SystemExit(1)
""",
    )
    image = tmp_path / "image.fits"
    image.write_bytes(b"input")

    result, attempts = await _run_chain(astap, image)

    assert not result.solved
    assert result.failure_reason == "error"
    assert calls.read_text() == "2"
    assert [attempt.outcome for attempt in attempts] == ["no_match", "error"]


async def test_astap_without_position_runs_blind_with_explicit_zero_fov(tmp_path):
    _reset_solve_state()
    recorded = tmp_path / "args"
    astap = _scripted_astap(
        tmp_path,
        f"""import pathlib, sys
pathlib.Path({str(recorded)!r}).write_text(' '.join(sys.argv[1:]))
raise SystemExit(1)
""",
    )
    image = tmp_path / "image.fits"
    image.write_bytes(b"input")

    result, attempts = await _run_chain(astap, image, position=None, scale=None)

    args = recorded.read_text().split()
    assert args[args.index("-r") + 1] == "180"
    assert args[args.index("-fov") + 1] == "0.0"
    assert len(attempts) == 1
    assert attempts[0].step == "astap_blind"
    assert result.failure_reason == "no_match"


async def test_astap_expired_preparation_deadline_starts_no_process(tmp_path, monkeypatch):
    _reset_solve_state()
    image = tmp_path / "image.fits"
    image.write_bytes(b"input")
    operation = solve_operations.claim(uuid4(), "astap")
    start = AsyncMock(side_effect=AssertionError("ASTAP started"))
    monkeypatch.setattr(plate_solve, "_run_astap_step", start)
    try:
        result = await plate_solve.run_astap_chain(
            tmp_path / "astap",
            image,
            position=None,
            scale_arcsec=None,
            image_width=100,
            image_height=80,
            deadline=time.monotonic() - 0.1,
            stop=operation.stop,
            reporter=operation,
            operation=operation,
        )
        attempts = operation.attempts()
    finally:
        solve_operations.release(operation)

    assert not result.solved
    assert result.failure_reason == "time_limit"
    assert attempts[0].outcome == "overall_timeout"
    start.assert_not_awaited()


async def test_astap_private_home_preserves_user_config(tmp_path, monkeypatch):
    _reset_solve_state()
    user_home = tmp_path / "user"
    config = user_home / ".config" / "astap" / "astap.cfg"
    config.parent.mkdir(parents=True)
    config.write_text("user-settings")
    copied = tmp_path / "copied"
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("ASTAP_COPIED", str(copied))
    astap = _scripted_astap(
        tmp_path,
        """import os, pathlib
cfg = pathlib.Path(os.environ['HOME']) / '.config' / 'astap' / 'astap.cfg'
pathlib.Path(os.environ['ASTAP_COPIED']).write_text(cfg.read_text())
cfg.write_text('changed-by-astap')
raise SystemExit(1)
""",
    )
    image = tmp_path / "image.fits"
    image.write_bytes(b"input")

    await _run_chain(astap, image, position=None, scale=None)

    assert copied.read_text() == "user-settings"
    assert config.read_text() == "user-settings"


def test_astap_windows_config_path_is_exact(tmp_path):
    config = tmp_path / "astap" / "astap.cfg"
    decoy = tmp_path / "other" / "astap.cfg"
    config.parent.mkdir(parents=True)
    decoy.parent.mkdir(parents=True)
    config.write_text("settings")
    decoy.write_text("decoy")

    paths = plate_solve._astap_config_paths({"LOCALAPPDATA": str(tmp_path)}, platform="win32")

    assert paths == [config]


def test_astap_private_home_uses_xdg_config(tmp_path):
    xdg_config = tmp_path / "xdg"
    config = xdg_config / "astap" / "astap.cfg"
    config.parent.mkdir(parents=True)
    config.write_text("user-settings")
    temp_home = tmp_path / "private"

    env = plate_solve._private_astap_environment(
        temp_home,
        environ={"HOME": str(tmp_path / "home"), "XDG_CONFIG_HOME": str(xdg_config)},
        platform="linux",
    )

    assert env["XDG_CONFIG_HOME"] == str(temp_home / ".config")
    assert (temp_home / ".config" / "astap" / "astap.cfg").read_text() == "user-settings"


def test_astap_windows_guard_restores_changed_config(tmp_path, caplog):
    config = tmp_path / "astap" / "astap.cfg"
    config.parent.mkdir(parents=True)
    config.write_bytes(b"original")

    with caplog.at_level(logging.WARNING, logger="nightcrate"):
        with plate_solve._guard_astap_settings(
            environ={"LOCALAPPDATA": str(tmp_path)}, platform="win32"
        ):
            config.write_bytes(b"changed")

    assert config.read_bytes() == b"original"
    assert f"[plate_solve] Restored ASTAP settings changed by a solve: {config}" in caplog.messages


def test_astap_windows_guard_does_not_rewrite_unchanged_config(tmp_path):
    config = tmp_path / "astap" / "astap.cfg"
    config.parent.mkdir(parents=True)
    config.write_bytes(b"original")
    mtime = config.stat().st_mtime_ns

    with plate_solve._guard_astap_settings(
        environ={"LOCALAPPDATA": str(tmp_path)}, platform="win32"
    ):
        pass

    assert config.stat().st_mtime_ns == mtime


def test_astap_windows_guard_restores_when_step_raises(tmp_path):
    config = tmp_path / "astap" / "astap.cfg"
    config.parent.mkdir(parents=True)
    config.write_bytes(b"original")

    with pytest.raises(RuntimeError, match="fake step failed"):
        with plate_solve._guard_astap_settings(
            environ={"LOCALAPPDATA": str(tmp_path)}, platform="win32"
        ):
            config.write_bytes(b"changed")
            raise RuntimeError("fake step failed")

    assert config.read_bytes() == b"original"


def test_astap_private_home_without_config_does_not_copy(tmp_path):
    temp_home = tmp_path / "private"

    env = plate_solve._private_astap_environment(
        temp_home,
        environ={"HOME": str(tmp_path / "missing"), "XDG_CONFIG_HOME": ""},
        platform="darwin",
    )

    assert env["XDG_CONFIG_HOME"] == str(temp_home / ".config")
    assert not (temp_home / ".config" / "astap" / "astap.cfg").exists()


def test_prepare_hdu_one_writes_selected_extension(tmp_path):
    path = tmp_path / "multi.fits"
    astro_fits.HDUList(
        [
            astro_fits.PrimaryHDU(np.zeros((2, 3), dtype=np.uint16)),
            astro_fits.ImageHDU(np.full((4, 5), 7, dtype=np.uint16)),
        ]
    ).writeto(path)

    prepared_dir = tmp_path / "prepared"
    prepared_dir.mkdir()
    prepared = plate_solve._prepare_image_file(path, "fits", 0, 1, prepared_dir)

    with astro_fits.open(prepared) as hdul:
        assert hdul[0].data.shape == (4, 5)
        assert np.all(hdul[0].data == 7)


async def test_astap_field_uses_prepared_height_and_shared_header_scale(tmp_path):
    prepared = tmp_path / "prepared.fits"
    astro_fits.PrimaryHDU(np.zeros((40, 100), dtype=np.float32)).writeto(prepared)
    observed = {}

    async def fake_chain(_binary, _image_file, **kwargs):
        observed.update(kwargs)
        return PlateSolveResult(solved=False)

    cards = [
        {"key": "NAXIS1", "value": "100"},
        {"key": "NAXIS2", "value": "999"},
        {"key": "FOCALLEN", "value": "500"},
        {"key": "YPIXSZ", "value": "4"},
        {"key": "XPIXSZ", "value": "9"},
    ]
    with (
        patch.object(
            plate_solve,
            "_resolve_path",
            return_value=(tmp_path / "source.xisf", "xisf", 0, None),
        ),
        patch.object(plate_solve, "read_header_cards", return_value=cards),
        patch.object(plate_solve, "_prepare_image_file", return_value=prepared),
        patch.object(plate_solve, "run_astap_chain", fake_chain),
    ):
        await plate_solve._do_solve(
            tmp_path / "astap",
            "source.xisf",
            hdu=0,
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
            timeout=180,
        )

    assert observed["image_height"] == 40
    assert observed["scale_arcsec"] == pytest.approx(206.265 * 4 / 500)


@pytest.mark.parametrize(
    ("cd1_2", "cd2_2", "expected"),
    [
        (0.0, 1e-4, 0.0),
        (-1e-4 * math.sin(math.radians(30)), 1e-4 * math.cos(math.radians(30)), 30.0),
        (1e-4 * math.sin(math.radians(30)), 1e-4 * math.cos(math.radians(30)), -30.0),
    ],
)
def test_rotation_from_cd(cd1_2, cd2_2, expected):
    assert plate_solve.rotation_from_cd(cd1_2, cd2_2) == pytest.approx(expected)
