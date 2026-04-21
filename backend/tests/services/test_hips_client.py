"""Unit tests for the hips2fits URL builders."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

from nightcrate.services.hips_client import (
    build_hips2fits_url,
    build_hips2fits_wcs_url,
)
from nightcrate.services.sky_tiles import TIERS, cell_wcs_dict


def test_build_hips2fits_url_basic():
    url = build_hips2fits_url(
        "CDS/P/DSS2/color",
        ra_deg=150.0,
        dec_deg=40.0,
        width=800,
        height=800,
        fov_deg=1.0,
    )
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert qs["hips"] == ["CDS/P/DSS2/color"]
    assert qs["width"] == ["800"]
    assert qs["height"] == ["800"]
    assert qs["ra"] == ["150.000000"]
    assert qs["dec"] == ["40.000000"]
    assert qs["fov"] == ["1.000000"]
    assert qs["format"] == ["jpg"]


def test_build_hips2fits_wcs_url_round_trip_via_query_string():
    """URL-decode must produce a JSON dict that round-trips through json.loads."""
    tier = TIERS["narrow"]
    wcs = cell_wcs_dict(150.0, 40.0, tier, 0, 0)
    url = build_hips2fits_wcs_url("CDS/P/DSS2/color", wcs)
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert qs["hips"] == ["CDS/P/DSS2/color"]
    assert qs["format"] == ["jpg"]
    # ``wcs`` must decode back to a JSON dict with all the keys we sent.
    decoded = json.loads(qs["wcs"][0])
    for key in (
        "NAXIS",
        "NAXIS1",
        "NAXIS2",
        "CTYPE1",
        "CTYPE2",
        "CRVAL1",
        "CRVAL2",
        "CRPIX1",
        "CRPIX2",
        "CDELT1",
        "CDELT2",
    ):
        assert key in decoded
    assert decoded["NAXIS1"] == tier.cell_width_px
    assert decoded["CTYPE1"] == "RA---TAN"


@pytest.mark.parametrize("cell_i,cell_j", [(0, 0), (+1, 0), (0, +1), (-2, +3)])
def test_wcs_url_encodes_every_tier_and_cell(cell_i: int, cell_j: int):
    for tier_name in ("narrow", "med", "wide"):
        tier = TIERS[tier_name]
        wcs = cell_wcs_dict(10.0, -30.0, tier, cell_i, cell_j)
        url = build_hips2fits_wcs_url("CDS/P/DSS2/color", wcs)
        # Must be a valid URL with a parseable wcs= param.
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        decoded = json.loads(qs["wcs"][0])
        # CRPIX values must round-trip exactly through JSON.
        assert float(decoded["CRPIX1"]) == pytest.approx(wcs["CRPIX1"])
        assert float(decoded["CRPIX2"]) == pytest.approx(wcs["CRPIX2"])
