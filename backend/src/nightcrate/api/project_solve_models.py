"""Pydantic models for project plate-solve + identified-DSO endpoints."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nightcrate.services.image_annotation_models import WcsParams
from nightcrate.services.plate_solve_models import SolveAttempt, check_solve_hints


class ProjectSolveRequest(BaseModel):
    """Solve a standalone image for a project. Header coordinate hints are
    used automatically; ra/dec/fov hints are optional manual overrides."""

    model_config = ConfigDict(extra="forbid")

    image_path: str
    hdu: int = Field(default=0, ge=0, le=0)
    operation_id: UUID
    replace: bool = False
    ra_hint: float | None = None
    dec_hint: float | None = None
    fov_hint: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    scale_hint_arcsec: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    position: Literal["auto", "none"] = "auto"
    scale: Literal["auto", "none"] = "auto"
    solver: Literal["native", "astap"] | None = None

    @model_validator(mode="after")
    def validate_hints(self) -> ProjectSolveRequest:
        check_solve_hints(
            ra_hint=self.ra_hint,
            dec_hint=self.dec_hint,
            fov_hint=self.fov_hint,
            scale_hint_arcsec=self.scale_hint_arcsec,
            position=self.position,
            scale=self.scale,
        )
        return self


class SetMainRequest(BaseModel):
    is_main: bool


class IdentifiedDso(BaseModel):
    """A catalog object found in the solved frame, with its projected pixel
    position for the overlay and whether it's flagged as a main subject."""

    dso_id: int
    active: bool
    primary_designation: str
    common_name: str | None = None
    other_names: list[str]
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
    solver: Literal["native", "astap"]
    star_catalog: str | None = None
    stars_detected: int | None = None
    stars_matched: int | None = None
    rms_px: float | None = None
    rms_arcsec: float | None = None
    log_odds: float | None = None
    solve_path: Literal["near_index", "near_catalog", "blind"] | None = None
    scale_stage: str | None = None
    attempts: list[SolveAttempt] = Field(default_factory=list)
    wcs: WcsParams
    objects: list[IdentifiedDso]
