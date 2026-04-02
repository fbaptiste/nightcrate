"""Tests for nightcrate.services.fits_header_map."""

import pytest

from nightcrate.services.fits_header_map import (
    FITS_KEYWORD_ALIASES,
    FITS_KEYWORD_MAP,
    KEYWORD_PRIORITY,
    extract_metadata,
    get_keyword_description,
    normalize_filter_name,
    normalize_frame_type,
    resolve_header,
)

# ── resolve_header ───────────────────────────────────────────────────────────


class TestResolveHeader:
    def test_standard_keyword(self):
        assert resolve_header("EXPTIME") == "exposure_time"

    def test_case_insensitive(self):
        assert resolve_header("exptime") == "exposure_time"
        assert resolve_header("Exptime") == "exposure_time"

    def test_unknown_keyword(self):
        assert resolve_header("XYZZY") is None

    def test_vendor_keyword_nina(self):
        assert resolve_header("SSWEIGHT") == "pi_ssweight"

    def test_vendor_keyword_sgpro(self):
        assert resolve_header("CCDXBIN") == "binning_x"

    def test_vendor_keyword_zwo(self):
        assert resolve_header("GAINRAW") == "gain"


# ── get_keyword_description ──────────────────────────────────────────────────


class TestGetKeywordDescription:
    def test_exptime(self):
        assert get_keyword_description("EXPTIME") == "Exposure time (sec)"

    def test_ccd_temp(self):
        assert get_keyword_description("CCD-TEMP") == "Sensor temp (C)"

    def test_ssweight(self):
        assert get_keyword_description("SSWEIGHT") == "PI: SubframeSel weight"

    def test_unknown(self):
        assert get_keyword_description("BOGUS") is None

    def test_case_insensitive(self):
        assert get_keyword_description("exptime") == "Exposure time (sec)"


# ── normalize_frame_type ─────────────────────────────────────────────────────


class TestNormalizeFrameType:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("LIGHT", "light"),
            ("DARK", "dark"),
            ("FLAT", "flat"),
            ("BIAS", "bias"),
        ],
    )
    def test_iraf_short_form(self, raw, expected):
        assert normalize_frame_type(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Light Frame", "light"),
            ("Dark Frame", "dark"),
            ("Flat Field", "flat"),
            ("Bias Frame", "bias"),
        ],
    )
    def test_sbfitsext_long_form(self, raw, expected):
        assert normalize_frame_type(raw) == expected

    def test_object_convention(self):
        assert normalize_frame_type("OBJECT") == "light"

    def test_science_convention(self):
        assert normalize_frame_type("SCIENCE") == "light"

    def test_zero_convention(self):
        assert normalize_frame_type("ZERO") == "bias"

    def test_whitespace_handling(self):
        assert normalize_frame_type("  LIGHT  ") == "light"
        assert normalize_frame_type("  Dark Frame  ") == "dark"

    def test_case_insensitive(self):
        assert normalize_frame_type("light") == "light"
        assert normalize_frame_type("dark frame") == "dark"

    def test_unknown_type(self):
        assert normalize_frame_type("MYSTERY") is None


# ── normalize_filter_name ────────────────────────────────────────────────────


class TestNormalizeFilterName:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Luminance", "Lum"),
            ("L", "Lum"),
            ("LUM", "Lum"),
        ],
    )
    def test_luminance_variants(self, raw, expected):
        assert normalize_filter_name(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("H-Alpha", "Ha"),
            ("HA", "Ha"),
            ("OIII", "Oiii"),
            ("O-III", "Oiii"),
            ("Sulfur-II", "Sii"),
            ("SII", "Sii"),
        ],
    )
    def test_narrowband(self, raw, expected):
        assert normalize_filter_name(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Red", "Red"),
            ("R", "Red"),
            ("Green", "Green"),
            ("G", "Green"),
            ("Blue", "Blue"),
            ("B", "Blue"),
        ],
    )
    def test_rgb(self, raw, expected):
        assert normalize_filter_name(raw) == expected

    def test_passthrough_l_extreme(self):
        assert normalize_filter_name("L-eXtreme") == "L-eXtreme"

    def test_passthrough_nbz(self):
        assert normalize_filter_name("NBZ") == "NBZ"

    def test_whitespace(self):
        assert normalize_filter_name("  L  ") == "Lum"
        assert normalize_filter_name("  L-eXtreme  ") == "L-eXtreme"


# ── extract_metadata ─────────────────────────────────────────────────────────


class TestExtractMetadata:
    def test_full_nina_header(self):
        header = {
            "EXPTIME": 300.0,
            "IMAGETYP": "LIGHT",
            "FILTER": "Ha",
            "GAIN": 100,
            "CCD-TEMP": -10.0,
            "INSTRUME": "ZWO ASI2600MM Pro",
            "TELESCOP": "Celestron C11",
            "DATE-OBS": "2025-03-15T02:30:00",
            "OBJECT": "NGC 6992",
            "XBINNING": 1,
            "YBINNING": 1,
            "FOCALLEN": 2800,
        }
        result = extract_metadata(header)
        assert result["exposure_time"] == 300.0
        assert result["frame_type"] == "light"
        assert result["filter_name"] == "Ha"
        assert result["gain"] == 100
        assert result["sensor_temp"] == -10.0
        assert result["camera_name"] == "ZWO ASI2600MM Pro"
        assert result["telescope_name"] == "Celestron C11"
        assert result["object_name"] == "NGC 6992"
        assert result["binning_x"] == 1
        assert result["focal_length"] == 2800

    def test_asiair_header_missing_telescop(self):
        header = {
            "EXPTIME": 180.0,
            "IMAGETYP": "Light",
            "FILTER": "OIII",
            "GAINRAW": 120,
            "INSTRUME": "ZWO ASI2600MM Pro",
            "DATE-OBS": "2025-03-15T03:00:00",
        }
        result = extract_metadata(header)
        assert result["exposure_time"] == 180.0
        assert result["filter_name"] == "Oiii"
        assert result["gain"] == 120
        assert "telescope_name" not in result

    def test_maxim_dl_long_frame_type(self):
        header = {
            "IMAGETYP": "Dark Frame",
            "EXPTIME": 300.0,
            "CCD-TEMP": -20.0,
        }
        result = extract_metadata(header)
        assert result["frame_type"] == "dark"

    def test_sgpro_keywords(self):
        header = {
            "CREATOR": "Sequence Generator Pro",
            "EXPOSURE": 120.0,
            "TEMPERAT": -15.0,
            "CCDXBIN": 2,
        }
        result = extract_metadata(header)
        assert result["software_creator"] == "Sequence Generator Pro"
        assert result["exposure_time"] == 120.0
        assert result["sensor_temp"] == -15.0
        assert result["binning_x"] == 2

    def test_pixinsight_quality_keywords(self):
        header = {
            "SSWEIGHT": 0.85,
            "PSFSIGNAL": 12.5,
            "PSFFWHM": 2.1,
            "PSFECCENTR": 0.45,
            "PSFSTARS": 312,
            "PSFSNR": 55.0,
            "PSFFLUX": 1200.0,
        }
        result = extract_metadata(header)
        assert result["pi_ssweight"] == 0.85
        assert result["pi_psf_signal"] == 12.5
        assert result["pi_psf_fwhm"] == 2.1
        assert result["pi_psf_eccen"] == 0.45
        assert result["pi_psf_stars"] == 312
        assert result["pi_psf_snr"] == 55.0
        assert result["pi_psf_flux"] == 1200.0

    def test_exptime_wins_over_exposure(self):
        header = {
            "EXPTIME": 300.0,
            "EXPOSURE": 299.9,
        }
        result = extract_metadata(header)
        assert result["exposure_time"] == 300.0

    def test_ccd_temp_wins_over_temperat(self):
        header = {
            "CCD-TEMP": -10.0,
            "TEMPERAT": -9.8,
        }
        result = extract_metadata(header)
        assert result["sensor_temp"] == -10.0

    def test_empty_values_skipped(self):
        header = {
            "EXPTIME": 300.0,
            "OBJECT": "",
            "FILTER": "   ",
            "TELESCOP": None,
        }
        result = extract_metadata(header)
        assert result["exposure_time"] == 300.0
        assert "object_name" not in result
        assert "filter_name" not in result
        assert "telescope_name" not in result

    def test_insflnam_used_when_filter_absent(self):
        header = {
            "INSFLNAM": "H-Alpha",
        }
        result = extract_metadata(header)
        assert result["filter_name"] == "Ha"

    def test_filter_wins_over_insflnam(self):
        header = {
            "FILTER": "Ha",
            "INSFLNAM": "Hydrogen-Alpha",
        }
        result = extract_metadata(header)
        assert result["filter_name"] == "Ha"


# ── Map consistency ──────────────────────────────────────────────────────────


class TestMapConsistency:
    def test_priority_keywords_exist_in_aliases(self):
        """Every keyword listed in KEYWORD_PRIORITY must exist in FITS_KEYWORD_ALIASES."""
        for canonical, keywords in KEYWORD_PRIORITY.items():
            for kw in keywords:
                assert kw in FITS_KEYWORD_ALIASES, (
                    f"Keyword {kw!r} in KEYWORD_PRIORITY[{canonical!r}] "
                    f"is missing from FITS_KEYWORD_ALIASES"
                )

    def test_priority_keywords_map_to_declared_canonical(self):
        """Each keyword in KEYWORD_PRIORITY must map to the canonical field it's declared under."""
        for canonical, keywords in KEYWORD_PRIORITY.items():
            for kw in keywords:
                actual = FITS_KEYWORD_ALIASES[kw]
                assert actual == canonical, (
                    f"Keyword {kw!r} under KEYWORD_PRIORITY[{canonical!r}] "
                    f"maps to {actual!r} instead"
                )

    def test_keyword_map_and_aliases_agree(self):
        """FITS_KEYWORD_ALIASES must be derived from FITS_KEYWORD_MAP."""
        for kw, canonical in FITS_KEYWORD_ALIASES.items():
            assert kw in FITS_KEYWORD_MAP
            assert FITS_KEYWORD_MAP[kw][0] == canonical
