"""HEALPix region + WCS cell math for the v0.18.0 sky-tile cache.

The WCS construction is the subtle part: every off-by-0.5-pixel or
sign mistake shows up as a visible seam between adjacent cells. The
seam-equality test is the hard gate — if two cells that share a
boundary don't report the same world coord at that boundary, the
formula is wrong.
"""

from __future__ import annotations

import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord

from nightcrate.services.sky_tiles import (
    HEALPIX_NSIDE,
    TIERS,
    cell_wcs,
    cell_wcs_dict,
    compute_grid_layout,
    ipix_for_coord,
    tangent_for_ipix,
    tier_for_fov,
)

# ─────────────────────────────────────────────────────────────────────
# Tier selection + HEALPix round-trip
# ─────────────────────────────────────────────────────────────────────


def test_nside_matches_plan():
    assert HEALPIX_NSIDE == 8  # 768 regions, ~7.3° each


@pytest.mark.parametrize(
    "fov,expected",
    [
        (0.3, "narrow"),
        (1.0, "narrow"),
        (1.0001, "med"),
        (1.5, "med"),
        (3.0, "med"),
        (3.0001, "wide"),
        (10.0, "wide"),
        (180.0, "wide"),
    ],
)
def test_tier_for_fov(fov: float, expected: str):
    assert tier_for_fov(fov).name == expected


@pytest.mark.parametrize(
    "ra,dec",
    [
        (0.0, 0.0),
        (180.0, 0.0),
        (359.99, -10.0),
        (150.0, 69.0),  # M81 neighbourhood
        (90.0, -89.5),  # near south pole — HEALPix must not degenerate
        (45.0, 85.0),  # near north pole
    ],
)
def test_ipix_contains_its_own_tangent(ra: float, dec: float):
    """Coord → ipix → tangent must fall inside the same HEALPix region."""
    ipix = ipix_for_coord(ra, dec)
    t_ra, t_dec = tangent_for_ipix(ipix)
    assert ipix_for_coord(t_ra, t_dec) == ipix


def test_ipix_range():
    """HEALPix NSIDE=8 has exactly 12·NSIDE² = 768 tiles."""
    # Sample a few coords; ipix should always land in [0, 768).
    for ra in (0.0, 45.0, 135.0, 225.0, 300.0):
        for dec in (-80.0, -40.0, 0.0, 40.0, 80.0):
            ipix = ipix_for_coord(ra, dec)
            assert 0 <= ipix < 12 * HEALPIX_NSIDE * HEALPIX_NSIDE


# ─────────────────────────────────────────────────────────────────────
# WCS sanity per cell
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tier_name", ["narrow", "med", "wide"])
def test_cell_zero_zero_puts_tangent_at_image_centre(tier_name: str):
    """Cell (0, 0) is the "centred" cell — tangent at pixel centre."""
    tier = TIERS[tier_name]
    ra0, dec0 = 150.0, 40.0
    w = cell_wcs(ra0, dec0, tier, 0, 0)
    # wcs_world2pix uses 1-based pixel origin when origin=1.
    x, y = w.wcs_world2pix([[ra0, dec0]], 1)[0]
    assert x == pytest.approx((tier.cell_width_px + 1) / 2, abs=1e-9)
    assert y == pytest.approx((tier.cell_height_px + 1) / 2, abs=1e-9)


@pytest.mark.parametrize("tier_name", ["narrow", "med", "wide"])
def test_pixel_scale_matches_tier_spec(tier_name: str):
    """One pixel step produces a great-circle separation of ``scale_deg_per_px``."""
    tier = TIERS[tier_name]
    ra0, dec0 = 150.0, 40.0
    w = cell_wcs(ra0, dec0, tier, 0, 0)
    cx = (tier.cell_width_px + 1) / 2
    cy = (tier.cell_height_px + 1) / 2
    (ra_a, dec_a), (ra_b, dec_b) = w.wcs_pix2world([[cx, cy], [cx + 1, cy]], 1)
    (ra_c, dec_c), (ra_d, dec_d) = w.wcs_pix2world([[cx, cy], [cx, cy + 1]], 1)
    ax_x = SkyCoord(ra_a * u.deg, dec_a * u.deg).separation(SkyCoord(ra_b * u.deg, dec_b * u.deg))
    ax_y = SkyCoord(ra_c * u.deg, dec_c * u.deg).separation(SkyCoord(ra_d * u.deg, dec_d * u.deg))
    assert ax_x.deg == pytest.approx(tier.scale_deg_per_px, rel=1e-6)
    assert ax_y.deg == pytest.approx(tier.scale_deg_per_px, rel=1e-6)


def test_east_left_orientation():
    """Pixel X increasing must correspond to decreasing RA (east at the left edge)."""
    tier = TIERS["narrow"]
    w = cell_wcs(150.0, 0.0, tier, 0, 0)  # equator avoids pole wrap
    cx = (tier.cell_width_px + 1) / 2
    cy = (tier.cell_height_px + 1) / 2
    (ra_a, _), (ra_b, _) = w.wcs_pix2world([[cx, cy], [cx + 1, cy]], 1)
    assert ra_b < ra_a


def test_north_up_orientation():
    """Pixel Y increasing (FITS native) must correspond to increasing Dec."""
    tier = TIERS["narrow"]
    w = cell_wcs(150.0, 0.0, tier, 0, 0)
    cx = (tier.cell_width_px + 1) / 2
    cy = (tier.cell_height_px + 1) / 2
    (_, dec_a), (_, dec_b) = w.wcs_pix2world([[cx, cy], [cx, cy + 1]], 1)
    assert dec_b > dec_a


def test_cell_i_positive_is_west():
    """``cell_i=+1`` must place the cell west of the tangent (lower RA)."""
    tier = TIERS["narrow"]
    ra0, dec0 = 150.0, 0.0
    w = cell_wcs(ra0, dec0, tier, +1, 0)
    # Cell (+1, 0)'s own image centre maps to its cell's sky centre.
    cx = (tier.cell_width_px + 1) / 2
    cy = (tier.cell_height_px + 1) / 2
    sky_ra, _ = w.wcs_pix2world([[cx, cy]], 1)[0]
    assert sky_ra < ra0


def test_cell_j_positive_is_south():
    """``cell_j=+1`` must place the cell south of the tangent (lower Dec)."""
    tier = TIERS["narrow"]
    ra0, dec0 = 150.0, 20.0
    w = cell_wcs(ra0, dec0, tier, 0, +1)
    cx = (tier.cell_width_px + 1) / 2
    cy = (tier.cell_height_px + 1) / 2
    _, sky_dec = w.wcs_pix2world([[cx, cy]], 1)[0]
    assert sky_dec < dec0


# ─────────────────────────────────────────────────────────────────────
# Seam equality — the gate that guarantees pixel-perfect tiling.
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "tier_name,ra0,dec0",
    [
        # Equator — gnomonic math is simplest.
        ("narrow", 150.0, 0.0),
        ("med", 150.0, 0.0),
        # Mid-northern latitude — matches real target zones.
        ("narrow", 150.0, 40.0),
        # High dec — where the old per-tile-tangent approach fell apart.
        ("narrow", 150.0, 69.0),
        # Near south pole — HEALPix must still generate sensible tangents.
        ("narrow", 150.0, -75.0),
    ],
)
def test_horizontal_seam_world_coords_match(tier_name: str, ra0: float, dec0: float):
    """Right edge of cell (i,j) must match left edge of cell (i-1,j) in sky."""
    tier = TIERS[tier_name]
    a = cell_wcs(ra0, dec0, tier, 0, 0)
    # cell_i increases west; the cell directly west of (0,0) is (+1, 0).
    # The shared seam is at cell (0,0)'s western edge = cell (+1, 0)'s eastern edge.
    # In FITS pixel terms: (0,0)'s right edge X = NAXIS1 + 0.5, (+1,0)'s left edge X = 0.5.
    b = cell_wcs(ra0, dec0, tier, +1, 0)
    cy = (tier.cell_height_px + 1) / 2
    world_a_right = a.wcs_pix2world([[tier.cell_width_px + 0.5, cy]], 1)[0]
    world_b_left = b.wcs_pix2world([[0.5, cy]], 1)[0]
    assert world_a_right[0] == pytest.approx(world_b_left[0], abs=1e-10)
    assert world_a_right[1] == pytest.approx(world_b_left[1], abs=1e-10)


@pytest.mark.parametrize(
    "tier_name,ra0,dec0",
    [
        ("narrow", 150.0, 0.0),
        ("med", 150.0, 0.0),
        ("narrow", 150.0, 40.0),
        ("narrow", 150.0, 69.0),
    ],
)
def test_vertical_seam_world_coords_match(tier_name: str, ra0: float, dec0: float):
    """Bottom edge of cell (i,j) must match top edge of cell (i,j+1) in sky.

    ``cell_j=+1`` is south; its northern edge (high pixel Y) meets (0,0)'s
    southern edge (low pixel Y = 0.5 in FITS native).
    """
    tier = TIERS[tier_name]
    a = cell_wcs(ra0, dec0, tier, 0, 0)
    b = cell_wcs(ra0, dec0, tier, 0, +1)
    cx = (tier.cell_width_px + 1) / 2
    world_a_south = a.wcs_pix2world([[cx, 0.5]], 1)[0]
    world_b_north = b.wcs_pix2world([[cx, tier.cell_height_px + 0.5]], 1)[0]
    assert world_a_south[0] == pytest.approx(world_b_north[0], abs=1e-10)
    assert world_a_south[1] == pytest.approx(world_b_north[1], abs=1e-10)


def test_diagonal_corner_shared_across_four_cells():
    """Corner where cells (0,0), (+1,0), (0,+1), (+1,+1) meet must be one sky point."""
    tier = TIERS["narrow"]
    ra0, dec0 = 150.0, 40.0
    c00 = cell_wcs(ra0, dec0, tier, 0, 0)
    c10 = cell_wcs(ra0, dec0, tier, +1, 0)
    c01 = cell_wcs(ra0, dec0, tier, 0, +1)
    c11 = cell_wcs(ra0, dec0, tier, +1, +1)

    # (0,0)'s south-west corner — high X, low Y in FITS native.
    sw00 = c00.wcs_pix2world([[tier.cell_width_px + 0.5, 0.5]], 1)[0]
    # (+1,0)'s south-east corner — low X, low Y.
    se10 = c10.wcs_pix2world([[0.5, 0.5]], 1)[0]
    # (0,+1)'s north-west corner — high X, high Y.
    nw01 = c01.wcs_pix2world([[tier.cell_width_px + 0.5, tier.cell_height_px + 0.5]], 1)[0]
    # (+1,+1)'s north-east corner — low X, high Y.
    ne11 = c11.wcs_pix2world([[0.5, tier.cell_height_px + 0.5]], 1)[0]

    for other in (se10, nw01, ne11):
        assert other[0] == pytest.approx(sw00[0], abs=1e-10)
        assert other[1] == pytest.approx(sw00[1], abs=1e-10)


# ─────────────────────────────────────────────────────────────────────
# hips2fits WCS-dict serialisation
# ─────────────────────────────────────────────────────────────────────


def test_cell_wcs_dict_has_required_keys():
    """hips2fits requires NAXIS*, CTYPE*, CRVAL*, CRPIX*, CDELT* at minimum."""
    tier = TIERS["narrow"]
    d = cell_wcs_dict(150.0, 40.0, tier, 0, 0)
    required = {
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
    }
    assert required.issubset(set(d.keys()))
    assert d["NAXIS1"] == tier.cell_width_px
    assert d["NAXIS2"] == tier.cell_height_px
    assert d["CTYPE1"] == "RA---TAN"
    assert d["CTYPE2"] == "DEC--TAN"
    assert d["CRVAL1"] == pytest.approx(150.0)
    assert d["CRVAL2"] == pytest.approx(40.0)


def test_cell_wcs_dict_is_json_serialisable():
    """hips2fits takes ``wcs=<JSON>`` — every value must round-trip through json."""
    import json

    tier = TIERS["narrow"]
    d = cell_wcs_dict(150.0, 40.0, tier, +2, -1)
    s = json.dumps(d)
    parsed = json.loads(s)
    # Values that matter for cell identity must survive the trip unchanged.
    for key in ("NAXIS1", "NAXIS2", "CTYPE1", "CTYPE2"):
        assert parsed[key] == d[key]
    for key in ("CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "CDELT1", "CDELT2"):
        assert float(parsed[key]) == pytest.approx(float(d[key]))


# ─────────────────────────────────────────────────────────────────────
# Grid layout — used by the sky-tile-grid endpoint
# ─────────────────────────────────────────────────────────────────────


def test_grid_layout_has_at_least_one_cell():
    layout = compute_grid_layout(
        center_ra_deg=150.0,
        center_dec_deg=40.0,
        tier_name="narrow",
        extent_deg=1.0,
    )
    assert len(layout.cells) >= 1
    assert layout.tier == "narrow"
    assert layout.cell_size_deg == TIERS["narrow"].cell_size_deg


def test_grid_layout_cell_count_scales_with_extent():
    a = compute_grid_layout(
        center_ra_deg=150.0, center_dec_deg=40.0, tier_name="narrow", extent_deg=1.0
    )
    b = compute_grid_layout(
        center_ra_deg=150.0, center_dec_deg=40.0, tier_name="narrow", extent_deg=3.0
    )
    assert len(b.cells) > len(a.cells)


def test_grid_layout_adjacent_cells_are_cell_size_apart():
    """Core invariant: neighbouring cells differ by exactly
    ``cell_width_px`` / ``cell_height_px`` in their pixel_x / pixel_y.

    If this fails, seams between cells show gaps or overlaps when
    composited.
    """
    tier = TIERS["narrow"]
    layout = compute_grid_layout(
        center_ra_deg=150.0,
        center_dec_deg=40.0,
        tier_name="narrow",
        extent_deg=2.0,
    )
    by_coord = {(c.cell_i, c.cell_j): c for c in layout.cells}
    for (ci, cj), c in by_coord.items():
        right = by_coord.get((ci + 1, cj))
        if right is not None:
            assert right.pixel_x - c.pixel_x == tier.cell_width_px
            assert right.pixel_y == c.pixel_y
        below = by_coord.get((ci, cj + 1))
        if below is not None:
            assert below.pixel_y - c.pixel_y == tier.cell_height_px
            assert below.pixel_x == c.pixel_x


def test_grid_layout_composite_exactly_bounds_cells():
    layout = compute_grid_layout(
        center_ra_deg=150.0,
        center_dec_deg=40.0,
        tier_name="narrow",
        extent_deg=2.5,
    )
    max_right = max(c.pixel_x + layout.cell_width_px for c in layout.cells)
    max_bottom = max(c.pixel_y + layout.cell_height_px for c in layout.cells)
    min_left = min(c.pixel_x for c in layout.cells)
    min_top = min(c.pixel_y for c in layout.cells)
    assert min_left == 0
    assert min_top == 0
    assert layout.composite_width_px == max_right
    assert layout.composite_height_px == max_bottom


def test_grid_layout_view_center_is_inside_composite():
    layout = compute_grid_layout(
        center_ra_deg=150.0,
        center_dec_deg=40.0,
        tier_name="narrow",
        extent_deg=1.0,
    )
    assert 0 <= layout.view_center_pixel_x <= layout.composite_width_px
    assert 0 <= layout.view_center_pixel_y <= layout.composite_height_px


@pytest.mark.parametrize(
    "tier_name,extent",
    [
        ("narrow", 0.5),
        ("narrow", 2.0),
        ("med", 3.0),
        ("med", 10.0),
        ("wide", 20.0),
    ],
)
def test_grid_layout_view_center_aligns_with_projected_coord(tier_name: str, extent: float):
    """view_center_pixel_* must match astropy's projection of
    (center_ra, center_dec) through any cell's WCS, after translating
    the cell-local pixel to the composite's screen-coords frame.
    End-to-end sign / Y-flip sanity check.
    """
    import math as _math

    tier = TIERS[tier_name]
    ra0, dec0 = 150.0, 40.0
    layout = compute_grid_layout(
        center_ra_deg=ra0, center_dec_deg=dec0, tier_name=tier_name, extent_deg=extent
    )
    cell = layout.cells[0]
    w = cell_wcs(
        layout.tangent_ra_deg,
        layout.tangent_dec_deg,
        tier,
        cell.cell_i,
        cell.cell_j,
    )
    px = w.wcs_world2pix([[ra0, dec0]], 1)[0]
    # FITS 1-based pixel → 0-based screen X (east-left matches FITS X).
    cell_local_screen_x = float(px[0]) - 0.5
    # FITS Y-up → screen Y-down.
    cell_local_screen_y = (tier.cell_height_px + 0.5) - float(px[1])
    composite_x = cell.pixel_x + cell_local_screen_x
    composite_y = cell.pixel_y + cell_local_screen_y
    assert _math.isclose(composite_x, layout.view_center_pixel_x, abs_tol=1.0)
    assert _math.isclose(composite_y, layout.view_center_pixel_y, abs_tol=1.0)
