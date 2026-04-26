"""Pydantic models for the image annotation service."""

from pydantic import BaseModel


class WcsParams(BaseModel):
    crval1: float
    crval2: float
    cd1_1: float
    cd1_2: float
    cd2_1: float
    cd2_2: float
    crpix1: float
    crpix2: float
    naxis1: int
    naxis2: int


class AnnotatedDso(BaseModel):
    id: int
    primary_designation: str
    obj_type: str
    type_group: str
    common_name: str | None = None
    constellation: str | None = None
    ra_deg: float
    dec_deg: float
    pixel_x: float
    pixel_y: float
    ellipse_semi_major_px: float | None = None
    ellipse_semi_minor_px: float | None = None
    ellipse_angle_deg: float | None = None
    maj_axis_arcmin: float | None = None
    min_axis_arcmin: float | None = None
    distance_pc: float | None = None
    distance_method: str | None = None
    mag_b: float | None = None


class ImageAnnotationResult(BaseModel):
    wcs: WcsParams
    center_ra_deg: float
    center_dec_deg: float
    fov_width_arcmin: float
    fov_height_arcmin: float
    pixel_scale_arcsec: float
    rotation_deg: float
    dsos: list[AnnotatedDso]
