from __future__ import annotations

import numpy as np
import pytest

from nightcrate.services.cfa import (
    CfaPattern,
    parse_bayer,
    pattern_from_fits,
    pattern_from_raw,
    pattern_from_xisf,
)


@pytest.mark.parametrize(
    ("header", "height", "rows"),
    [
        ({"BAYERPAT": "RGGB", "XBAYROFF": 1, "ROWORDER": "TOP-DOWN"}, 4, ("GR", "BG")),
        ({"BAYERPAT": "RGGB", "YBAYROFF": 1, "ROWORDER": "TOP-DOWN"}, 4, ("GB", "RG")),
        ({"BAYERPAT": "RGGB", "ROWORDER": "BOTTOM-UP"}, 4, ("GB", "RG")),
        ({"BAYERPAT": "RGGB", "ROWORDER": "BOTTOM-UP"}, 5, ("RG", "GB")),
    ],
)
def test_fits_offsets_and_row_order(header, height, rows):
    assert pattern_from_fits(header, height).pattern.rows == rows


def test_colortyp_fallback_and_bayerpat_wins():
    fallback = pattern_from_fits({"COLORTYP": " bggr ", "ROWORDER": "TOP-DOWN"}, 10)
    assert fallback.pattern.rows == ("BG", "GR")
    assert fallback.source == "fits_colortyp"

    preferred = pattern_from_fits(
        {"BAYERPAT": "GRBG", "COLORTYP": "BGGR", "ROWORDER": "TOP-DOWN"}, 10
    )
    assert preferred.pattern.rows == ("GR", "BG")
    assert preferred.source == "fits_bayerpat"


def test_sharpcap_offsets_are_ignored_and_recorded():
    info = pattern_from_fits(
        {
            "BAYERPAT": "RGGB",
            "XBAYROFF": 1,
            "YBAYROFF": 1,
            "ROWORDER": "TOP-DOWN",
            "SWCREATE": "SharpCap 4.1",
        },
        20,
    )
    assert info.pattern.rows == ("RG", "GB")
    assert any("SharpCap offsets ignored" in value for value in info.assumptions)


def test_missing_roworder_assumption():
    info = pattern_from_fits({"BAYERPAT": "RGGB"}, 20)
    assert info.assumptions == ("ROWORDER missing; assumed TOP-DOWN",)


def test_xisf_bayer_and_xtrans():
    bayer = pattern_from_xisf({"pattern": "RGGB", "width": "2", "height": "2"})
    assert bayer.pattern.rows == ("RG", "GB")

    text = "GRGGBGBGBRGRGRGGBGGBGGRGRGRBGBGBGGRG"
    xtrans = pattern_from_xisf({"pattern": text, "width": "6", "height": "6"})
    assert xtrans.pattern.width == 6
    assert xtrans.pattern.height == 6
    assert "".join(xtrans.pattern.rows) == text


@pytest.mark.parametrize(
    "attributes",
    [
        {"pattern": "RGGX", "width": "2", "height": "2"},
        {"pattern": "RGG", "width": "2", "height": "2"},
        {"pattern": "RGGB", "width": "bad", "height": "2"},
    ],
)
def test_xisf_unsupported_pattern_is_none(attributes):
    assert pattern_from_xisf(attributes) is None


def test_raw_colour_indices_use_colour_description():
    info = pattern_from_raw(np.array([[0, 1], [3, 2]], dtype=np.uint8), b"RGBG")
    assert info.pattern.rows == ("RG", "GB")


def test_parse_bayer_is_strict_but_case_insensitive():
    assert parse_bayer(" rGgB ") == CfaPattern(("RG", "GB"))
    assert parse_bayer("RGBG") is None


def test_colour_at_wraps():
    pattern = CfaPattern(("RG", "GB"))
    assert pattern.colour_at(3, 4) == "G"
