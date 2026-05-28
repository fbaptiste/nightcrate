"""Pydantic models for project plate-solve + identified-DSO endpoints."""

from __future__ import annotations

from pydantic import BaseModel

from nightcrate.services.image_annotation_models import WcsParams


class ProjectSolveRequest(BaseModel):
    """Solve a standalone image for a project. Header coordinate hints are
    used automatically; ra/dec/fov hints are optional manual overrides."""

    image_path: str
    hdu: int = 0
    ra_hint: float | None = None
    dec_hint: float | None = None
    fov_hint: float | None = None


class SetMainRequest(BaseModel):
    is_main: bool


class IdentifiedDso(BaseModel):
    """A catalog object found in the solved frame, with its projected pixel
    position for the overlay and whether it's flagged as a main subject."""

    dso_id: int
    primary_designation: str
    common_name: str | None = None
    obj_type: str
    type_group: str
    constellation: str | None = None
    ra_deg: float
    dec_deg: float
    maj_axis_arcmin: float | None = None
    min_axis_arcmin: float | None = None
    distance_pc: float | None = None
    mag_b: float | None = None
    is_main: bool
    pixel_x: float
    pixel_y: float
    ellipse_semi_major_px: float | None = None
    ellipse_semi_minor_px: float | None = None
    ellipse_angle_deg: float | None = None


class ProjectSolveResponse(BaseModel):
    id: int
    project_id: int
    image_path: str
    image_width: int
    image_height: int
    center_ra_deg: float
    center_dec_deg: float
    ra_hms: str | None
    dec_dms: str | None
    pixel_scale_arcsec: float | None
    rotation_deg: float | None
    fov_width_arcmin: float | None
    fov_height_arcmin: float | None
    solved_at: str
    wcs: WcsParams
    objects: list[IdentifiedDso]
