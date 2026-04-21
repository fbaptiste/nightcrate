"""Sky-tile partitioning + WCS construction for the v0.18.0 FOV-simulator
cache (Target Planner Pass C).

The sphere is partitioned into 768 HEALPix regions (``NSIDE=8``,
~7.3° per side, equal-area). Each region has a fixed tangent point —
the region's HEALPix pixel centre. Within a region, a tile is a
sub-region of the region's TAN plane whose pixels we render via
hips2fits using a custom WCS header that shares the region's tangent.

This arrangement has two useful properties:

1. **Pixel-perfect stitching** inside a region. Two adjacent cells
   share identical world coordinates at their common boundary because
   they live on the same tangent plane with a CRPIX offset between
   them. No projection mismatch, no per-tile-tangent drift.
2. **DSO-agnostic caching**. A cell's identity is
   ``(hips_survey, nside, ipix, tier, cell_i, cell_j)``. Neighbouring
   DSOs in the same region share cache entries — viewing DSO B after
   DSO A only fetches cells outside A's view, not cells A already
   populated.

This module is pure math and value objects — no I/O and no database
access. Fetching + caching live in ``sky_tile_cache.py``; the API
endpoint lives in ``api/planner.py``.

Resolution tiers
================

A single cell size can't span the real rig spectrum (from ~250 mm
focal length → ~5° FOV to ~2800 mm → ~0.5° FOV). Three tiers,
selected per rig by the backend from ``fov_major_deg``:

* ``narrow`` — cell 0.5° × 0.5° at 800 × 800 px (1600 px/°). Rigs
  with major FOV ≤ 1°.
* ``med`` — cell 2° × 2° at 800 × 800 px (400 px/°). Rigs with
  1° < FOV ≤ 3°.
* ``wide`` — cell 8° × 8° at 1024 × 1024 px (128 px/°). Rigs with
  FOV > 3°.

Cache rows at different tiers are distinct entries; same-tier rigs
share cells.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS
from astropy_healpix import HEALPix

Tier = Literal["narrow", "med", "wide"]


# 768 regions at ~7.3° per side. Equal-area, no pole singularity.
HEALPIX_NSIDE: int = 8

# ``nested`` ordering gives a stable, hierarchically-meaningful index
# that survives NSIDE changes if we ever want a multi-resolution
# regional grid later. For the current plan the index just needs to be
# deterministic for each (ra, dec).
_HP = HEALPix(nside=HEALPIX_NSIDE, order="nested", frame="icrs")


@dataclass(frozen=True, slots=True)
class TierSpec:
    """Resolution tier: angular extent of one cell + pixel dimensions."""

    name: Tier
    cell_size_deg: float
    cell_width_px: int
    cell_height_px: int
    # Upper bound (inclusive) of ``fov_major_deg`` that selects this tier.
    # Rigs with a larger FOV fall through to the next tier.
    max_fov_deg: float

    @property
    def scale_deg_per_px(self) -> float:
        return self.cell_size_deg / self.cell_width_px

    @property
    def cell_size_deg_x100(self) -> int:
        """Integer representation for cache-key stability (matches migration 0020)."""
        return round(self.cell_size_deg * 100)


# Tier lookup order matters — ``tier_for_fov`` walks narrow → med → wide.
_TIER_ORDER: tuple[Tier, ...] = ("narrow", "med", "wide")

TIERS: dict[Tier, TierSpec] = {
    "narrow": TierSpec("narrow", 0.5, 800, 800, 1.0),
    "med": TierSpec("med", 2.0, 800, 800, 3.0),
    # ``max_fov_deg`` on the wide tier is a catch-all — no real rig has
    # a single-axis FOV approaching 180°, so this acts as a sentinel.
    "wide": TierSpec("wide", 8.0, 1024, 1024, 180.0),
}


def tier_for_fov(fov_major_deg: float) -> TierSpec:
    """Pick the tier whose cell angular extent comfortably holds the rig FOV."""
    for name in _TIER_ORDER:
        spec = TIERS[name]
        if fov_major_deg <= spec.max_fov_deg:
            return spec
    return TIERS["wide"]


def ipix_for_coord(ra_deg: float, dec_deg: float) -> int:
    """HEALPix region (``ipix``) containing the given sky coordinate."""
    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    return int(_HP.skycoord_to_healpix(coord))


def tangent_for_ipix(ipix: int) -> tuple[float, float]:
    """Region's tangent point (ra_deg, dec_deg) — HEALPix pixel centre."""
    coord = _HP.healpix_to_skycoord(ipix)
    return float(coord.ra.deg), float(coord.dec.deg)


def cell_wcs(
    region_ra_deg: float,
    region_dec_deg: float,
    tier: TierSpec,
    cell_i: int,
    cell_j: int,
) -> WCS:
    """Build an ``astropy.wcs.WCS`` for one cell on the region's TAN plane.

    The region's tangent point is fixed at ``(region_ra_deg, region_dec_deg)``
    regardless of which cell we're building; the cell identity is encoded
    entirely in the ``CRPIX`` offset. That's what makes adjacent cells
    tile pixel-perfectly — they share the tangent and only disagree on
    the reference pixel's location relative to their image.

    Cell ``(0, 0)`` is the "centred" cell — its image centre lands on
    the region tangent. ``cell_i`` increases westward (toward lower
    RA, higher pixel X because ``CDELT1 < 0`` is east-left); ``cell_j``
    increases southward (toward lower Dec). The sign conventions line
    up with the existing simulator's ``(col, row)`` layout.

    WCS conventions applied:
    * ``CTYPE1 = RA---TAN``, ``CTYPE2 = DEC--TAN`` — standard gnomonic.
    * ``CDELT1 = -scale``, ``CDELT2 = +scale`` — east-left, north-up in FITS pixel space.
    * ``CRPIX`` uses 1-based FITS pixel indexing. Image centre for a
      ``NAXIS1 × NAXIS2`` image is ``((NAXIS1+1)/2, (NAXIS2+1)/2)``
      (400.5, 400.5 for 800×800) — not ``(NAXIS/2, NAXIS/2)``. Getting
      this wrong causes a half-pixel seam drift.
    * ``LONPOLE = 180``, ``LATPOLE = R_dec`` — explicit for robustness
      across WCS serialisation roundtrips.
    """
    scale = tier.scale_deg_per_px
    n1 = tier.cell_width_px
    n2 = tier.cell_height_px

    # Image-centre pixel coordinates (FITS 1-based, so centre is at
    # (NAXIS+1)/2 rather than NAXIS/2). Cell offsets shift CRPIX so that
    # the tangent lands OUTSIDE the cell's own image when cell_i/j ≠ 0.
    # Positive cell_i → west (higher pixel X under CDELT1<0); the
    # tangent sits to the east of the image → CRPIX1 decreases as cell_i
    # increases. Positive cell_j → south (lower pixel Y under
    # CDELT2>0); the tangent sits to the north of the image → CRPIX2
    # increases as cell_j increases.
    crpix1 = (n1 + 1) / 2 - cell_i * n1
    crpix2 = (n2 + 1) / 2 + cell_j * n2

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [region_ra_deg, region_dec_deg]
    w.wcs.cdelt = [-scale, +scale]
    w.wcs.crpix = [crpix1, crpix2]
    w.wcs.cunit = ["deg", "deg"]
    w.wcs.lonpole = 180.0
    w.wcs.latpole = region_dec_deg
    # array_shape drives serialisation of NAXIS* when we pass through
    # ``to_header(relax=True)``; set it for completeness.
    w.array_shape = (n2, n1)
    return w


def cell_wcs_dict(
    region_ra_deg: float,
    region_dec_deg: float,
    tier: TierSpec,
    cell_i: int,
    cell_j: int,
) -> dict[str, int | float | str]:
    """WCS header dict suitable for hips2fits's ``wcs=<JSON>`` parameter.

    Astropy's ``WCS.to_header()`` omits ``NAXIS*`` (those belong on the
    HDU, not the WCS) — add them back explicitly so hips2fits knows the
    output image dimensions.
    """
    w = cell_wcs(region_ra_deg, region_dec_deg, tier, cell_i, cell_j)
    header = w.to_header()
    out: dict[str, int | float | str] = {}
    for key in header.keys():
        out[key] = header[key]
    out["NAXIS"] = 2
    out["NAXIS1"] = tier.cell_width_px
    out["NAXIS2"] = tier.cell_height_px
    return out


# ─── Grid layout ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CellLayout:
    """One cell's identity + its top-left position in the composite image.

    All pixel coordinates are in the composite's *source-pixel* system —
    screen-aligned (X east-left, Y top-to-bottom) and measured in the
    JPEG's native pixel units. The frontend applies CSS transforms to
    fit the composite into whatever viewport size it wants.
    """

    nside: int
    ipix: int
    tier: Tier
    cell_i: int
    cell_j: int
    pixel_x: int
    pixel_y: int


@dataclass(frozen=True, slots=True)
class GridLayout:
    """Layout response returned by the planner's sky-tile-grid endpoint.

    ``view_center_pixel_x/y`` tells the frontend where the requested
    ``(center_ra_deg, center_dec_deg)`` lands in the composite — it
    won't be exactly at ``(composite/2, composite/2)`` because the
    composite extends beyond the view to include whole cells at the
    edges.
    """

    nside: int
    ipix: int
    tangent_ra_deg: float
    tangent_dec_deg: float
    tier: Tier
    cell_size_deg: float
    cell_width_px: int
    cell_height_px: int
    composite_width_px: int
    composite_height_px: int
    view_center_pixel_x: int
    view_center_pixel_y: int
    cells: list[CellLayout]


def compute_grid_layout(
    *,
    center_ra_deg: float,
    center_dec_deg: float,
    tier_name: Tier,
    extent_deg: float,
) -> GridLayout:
    """Compute the cell-grid layout for a simulator or preview view.

    The view is centred on ``(center_ra_deg, center_dec_deg)`` and spans
    ``extent_deg`` on a side. Every cell shares the DSO's home HEALPix
    region tangent, so seams within the region are pixel-perfect.

    Layout derivation:
    * Project the centre onto the region's tangent plane via
      ``cell_wcs(ci=0, cj=0)`` and ``wcs_world2pix`` — gives the DSO's
      ``tpx_x / tpx_y`` (tangent-relative FITS pixel coords, Y-up).
    * The view is a square in tangent-pixel space of ``extent_deg /
      scale_deg_per_px`` on a side, centred on the DSO.
    * Cell ``(ci, cj)``'s tangent-pixel centre is ``(ci·n1, -cj·n2)``
      with ranges ``[(ci-0.5)·n1, (ci+0.5)·n1]`` × ``[(-cj-0.5)·n2,
      (-cj+0.5)·n2]``. Any cell overlapping the view window is
      included.
    * Composite: bounding box of the selected cells. ``ci_min`` anchors
      the composite's left edge (east); ``cj_min`` anchors the top
      (north). East-left / north-up screen coordinates.
    """
    tier = TIERS[tier_name]
    ipix = ipix_for_coord(center_ra_deg, center_dec_deg)
    tangent_ra, tangent_dec = tangent_for_ipix(ipix)

    n1 = tier.cell_width_px
    n2 = tier.cell_height_px

    # DSO in tangent-relative FITS pixel coords (Y-up).
    w = cell_wcs(tangent_ra, tangent_dec, tier, 0, 0)
    dso_pix = w.wcs_world2pix([[center_ra_deg, center_dec_deg]], 1)[0]
    dso_tpx_x = float(dso_pix[0]) - (n1 + 1) / 2
    dso_tpx_y = float(dso_pix[1]) - (n2 + 1) / 2

    half_ext_px = (extent_deg / 2) / tier.scale_deg_per_px

    view_x_min = dso_tpx_x - half_ext_px
    view_x_max = dso_tpx_x + half_ext_px
    view_y_min = dso_tpx_y - half_ext_px
    view_y_max = dso_tpx_y + half_ext_px

    # Iterate a conservative bounding range of ``(ci, cj)`` and keep
    # anything that overlaps the view. The conservative range is cheap
    # (at most ~(half_ext/cell_size+2)² candidates — tens, not thousands)
    # and the overlap test is exact.
    import math as _math

    ci_lo = _math.floor(view_x_min / n1 - 0.5)
    ci_hi = _math.ceil(view_x_max / n1 + 0.5)
    cj_lo = _math.floor(-view_y_max / n2 - 0.5)
    cj_hi = _math.ceil(-view_y_min / n2 + 0.5)

    cells_in_view: list[tuple[int, int]] = []
    for ci in range(ci_lo, ci_hi + 1):
        for cj in range(cj_lo, cj_hi + 1):
            cx = ci * n1
            cy = -cj * n2
            # Overlap: cell's [cx-n1/2, cx+n1/2] × [cy-n2/2, cy+n2/2]
            # intersects the view window.
            if (
                cx + n1 / 2 >= view_x_min
                and cx - n1 / 2 <= view_x_max
                and cy + n2 / 2 >= view_y_min
                and cy - n2 / 2 <= view_y_max
            ):
                cells_in_view.append((ci, cj))

    if not cells_in_view:
        # Pathological — extent smaller than a single pixel, or caller
        # supplied garbage. Return a minimal one-cell layout so downstream
        # code doesn't have to handle empty responses.
        cells_in_view = [(0, 0)]

    ci_min = min(ci for ci, _ in cells_in_view)
    ci_max = max(ci for ci, _ in cells_in_view)
    cj_min = min(cj for _, cj in cells_in_view)
    cj_max = max(cj for _, cj in cells_in_view)

    composite_width = (ci_max - ci_min + 1) * n1
    composite_height = (cj_max - cj_min + 1) * n2

    # DSO in composite screen coords (X east-left ≡ tpx_x direction,
    # Y top-to-bottom inverts tpx_y).
    view_center_x = int(round(dso_tpx_x - (ci_min - 0.5) * n1))
    view_center_y = int(round((-cj_min + 0.5) * n2 - dso_tpx_y))

    cells: list[CellLayout] = [
        CellLayout(
            nside=HEALPIX_NSIDE,
            ipix=ipix,
            tier=tier.name,
            cell_i=ci,
            cell_j=cj,
            pixel_x=(ci - ci_min) * n1,
            pixel_y=(cj - cj_min) * n2,
        )
        for ci, cj in cells_in_view
    ]

    return GridLayout(
        nside=HEALPIX_NSIDE,
        ipix=ipix,
        tangent_ra_deg=tangent_ra,
        tangent_dec_deg=tangent_dec,
        tier=tier.name,
        cell_size_deg=tier.cell_size_deg,
        cell_width_px=n1,
        cell_height_px=n2,
        composite_width_px=composite_width,
        composite_height_px=composite_height,
        view_center_pixel_x=view_center_x,
        view_center_pixel_y=view_center_y,
        cells=cells,
    )
