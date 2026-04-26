"""Image annotation service — WCS detection, DSO projection onto images.

Pure service module — no FastAPI, no DB access. Takes header cards and
DSO catalog rows as input; returns projected annotations with pixel
coordinates. WCS math via astropy.wcs.
"""

import math

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS

from nightcrate.services.image_annotation_models import AnnotatedDso, WcsParams

_WCS_REQUIRED_KEYS = {"CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "NAXIS1", "NAXIS2"}
_CD_KEYS = {"CD1_1", "CD1_2", "CD2_1", "CD2_2"}
_CDELT_KEYS = {"CDELT1", "CDELT2"}


def detect_wcs_from_cards(cards: list[dict]) -> WcsParams | None:
    """Extract WCS parameters from FITS header cards.

    Supports both CD matrix form and CDELT+CROTA form. Returns None
    if the headers don't contain a complete WCS solution.
    """
    raw: dict[str, str] = {}
    for card in cards:
        if card["key"]:
            raw[card["key"].upper()] = card["value"]

    for key in _WCS_REQUIRED_KEYS:
        if key not in raw:
            return None

    has_cd = all(k in raw for k in _CD_KEYS)
    has_cdelt = all(k in raw for k in _CDELT_KEYS)

    if has_cd:
        cd1_1 = _float(raw["CD1_1"])
        cd1_2 = _float(raw["CD1_2"])
        cd2_1 = _float(raw["CD2_1"])
        cd2_2 = _float(raw["CD2_2"])
    elif has_cdelt:
        cdelt1 = _float(raw["CDELT1"])
        cdelt2 = _float(raw["CDELT2"])
        crota2 = _float(raw.get("CROTA2", "0"))
        cos_r = math.cos(math.radians(crota2))
        sin_r = math.sin(math.radians(crota2))
        cd1_1 = cdelt1 * cos_r
        cd1_2 = -cdelt1 * sin_r
        cd2_1 = cdelt2 * sin_r
        cd2_2 = cdelt2 * cos_r
    else:
        return None

    if any(v is None for v in (cd1_1, cd1_2, cd2_1, cd2_2)):
        return None

    crval1 = _float(raw["CRVAL1"])
    crval2 = _float(raw["CRVAL2"])
    crpix1 = _float(raw["CRPIX1"])
    crpix2 = _float(raw["CRPIX2"])
    naxis1 = _int(raw["NAXIS1"])
    naxis2 = _int(raw["NAXIS2"])

    if any(v is None for v in (crval1, crval2, crpix1, crpix2, naxis1, naxis2)):
        return None

    return WcsParams(
        crval1=crval1,
        crval2=crval2,
        cd1_1=cd1_1,
        cd1_2=cd1_2,
        cd2_1=cd2_1,
        cd2_2=cd2_2,
        crpix1=crpix1,
        crpix2=crpix2,
        naxis1=naxis1,
        naxis2=naxis2,
    )


def build_wcs(params: WcsParams) -> WCS:
    """Construct an astropy WCS from parameters."""
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [params.crval1, params.crval2]
    w.wcs.crpix = [params.crpix1, params.crpix2]
    w.wcs.cd = [
        [params.cd1_1, params.cd1_2],
        [params.cd2_1, params.cd2_2],
    ]
    w.wcs.cunit = ["deg", "deg"]
    w.array_shape = (params.naxis2, params.naxis1)
    return w


def compute_fov(
    params: WcsParams,
) -> tuple[float, float, float, float, float, float]:
    """Compute FOV properties from WCS parameters.

    Returns (center_ra, center_dec, diagonal_radius_deg,
             fov_width_arcmin, fov_height_arcmin, pixel_scale_arcsec).
    """
    wcs = build_wcs(params)
    cx, cy = params.naxis1 / 2.0, params.naxis2 / 2.0
    center = wcs.pixel_to_world(cx, cy)
    center_ra = center.ra.deg
    center_dec = center.dec.deg

    corners_x = [0, params.naxis1, params.naxis1, 0]
    corners_y = [0, 0, params.naxis2, params.naxis2]
    corner_coords = wcs.pixel_to_world(corners_x, corners_y)

    max_sep = max(center.separation(c).deg for c in corner_coords)

    mid_top = wcs.pixel_to_world(cx, 0)
    mid_bottom = wcs.pixel_to_world(cx, params.naxis2)
    mid_left = wcs.pixel_to_world(0, cy)
    mid_right = wcs.pixel_to_world(params.naxis1, cy)

    fov_h_deg = mid_top.separation(mid_bottom).deg
    fov_w_deg = mid_left.separation(mid_right).deg

    pixel_scale = math.sqrt(params.cd2_1**2 + params.cd2_2**2) * 3600.0

    return (
        center_ra,
        center_dec,
        max_sep,
        fov_w_deg * 60.0,
        fov_h_deg * 60.0,
        pixel_scale,
    )


def compute_rotation(params: WcsParams) -> float:
    """Image rotation in degrees (north through east)."""
    return math.degrees(math.atan2(params.cd2_1, params.cd2_2))


def project_dsos(
    params: WcsParams,
    dsos: list[dict],
) -> list[AnnotatedDso]:
    """Project DSO catalog rows onto image pixel coordinates.

    *dsos* is a list of dicts from the DB query with keys: id,
    primary_designation, obj_type, type_group, ra_deg, dec_deg,
    maj_axis_arcmin, min_axis_arcmin, position_angle_deg,
    common_name, constellation, distance_pc, distance_method, b_mag.

    Returns only DSOs whose projected center falls within the image
    (with margin for extended objects).
    """
    wcs = build_wcs(params)
    image_rotation = compute_rotation(params)
    pixel_scale_deg = math.sqrt(params.cd2_1**2 + params.cd2_2**2)

    if not dsos:
        return []

    ra_arr = np.array([d["ra_deg"] for d in dsos])
    dec_arr = np.array([d["dec_deg"] for d in dsos])
    coords = SkyCoord(ra=ra_arr, dec=dec_arr, unit="deg")
    px_x, px_y = wcs.world_to_pixel(coords)

    results: list[AnnotatedDso] = []
    for i, dso in enumerate(dsos):
        x, y = float(px_x[i]), float(px_y[i])

        if np.isnan(x) or np.isnan(y):
            continue

        maj_arcmin = dso.get("maj_axis_arcmin")
        margin = 50.0
        if maj_arcmin is not None and pixel_scale_deg > 0:
            margin = max(margin, (maj_arcmin / 60.0) / pixel_scale_deg)

        if x < -margin or x > params.naxis1 + margin:
            continue
        if y < -margin or y > params.naxis2 + margin:
            continue

        semi_major_px = None
        semi_minor_px = None
        ellipse_angle = None

        if maj_arcmin is not None and pixel_scale_deg > 0:
            semi_major_px = (maj_arcmin / 60.0) / pixel_scale_deg / 2.0
            min_arcmin = dso.get("min_axis_arcmin") or maj_arcmin
            semi_minor_px = (min_arcmin / 60.0) / pixel_scale_deg / 2.0

            pa = dso.get("position_angle_deg") or 0.0
            ellipse_angle = pa - image_rotation

        results.append(
            AnnotatedDso(
                id=dso["id"],
                primary_designation=dso["primary_designation"],
                obj_type=dso["obj_type"],
                type_group=dso["type_group"],
                common_name=dso.get("common_name"),
                constellation=dso.get("constellation"),
                ra_deg=dso["ra_deg"],
                dec_deg=dso["dec_deg"],
                pixel_x=round(x, 1),
                pixel_y=round(y, 1),
                ellipse_semi_major_px=round(semi_major_px, 1) if semi_major_px else None,
                ellipse_semi_minor_px=round(semi_minor_px, 1) if semi_minor_px else None,
                ellipse_angle_deg=round(ellipse_angle, 1) if ellipse_angle is not None else None,
                maj_axis_arcmin=maj_arcmin,
                min_axis_arcmin=dso.get("min_axis_arcmin"),
                distance_pc=dso.get("distance_pc"),
                distance_method=dso.get("distance_method"),
                mag_b=dso.get("mag_b"),
            )
        )

    return results


def _float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _int(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))
    except ValueError:
        return None
