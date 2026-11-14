"""Response models for project object information."""

from __future__ import annotations

from pydantic import BaseModel

from nightcrate.services.gallery import GalleryRig, GalleryTarget, ImagingRun
from nightcrate.services.object_facts import OtherObject, OtherObjectDistance


class SolveField(BaseModel):
    constellation: str
    centre_ra_hms: str | None
    centre_dec_dms: str | None
    centre_ra_deg: float
    centre_dec_deg: float
    fov_width_deg: float | None
    fov_height_deg: float | None
    rotation_deg: float | None


class ProjectInfo(BaseModel):
    project_id: int
    name: str
    status: str
    retired: bool
    solved: bool
    targets: list[GalleryTarget]
    other_objects: list[OtherObject]
    other_distances: list[OtherObjectDistance]
    field: SolveField | None
    first_date: str | None
    last_date: str | None
    nights: int
    imaging_runs: list[ImagingRun]
    integration_minutes: float
    rigs: list[GalleryRig]
