"""Models for project-resolved rig setups and project-only changes."""

from pydantic import BaseModel

from nightcrate.api.rig_models import RigPartsIn, RigPartsOut


class ProjectRigPartsOut(RigPartsOut):
    effective_focal_length_mm: float
    effective_focal_ratio: float
    pixel_size_um: float
    sensor_resolution_x: int
    sensor_resolution_y: int
    image_scale_arcsec_per_pixel: float
    field_of_view_deg: tuple[float, float]


class ProjectSetupOut(BaseModel):
    rig_setup_id: int | None
    until_at: str | None
    since_at: str | None
    night_count: int
    parts: ProjectRigPartsOut


class ProjectSetupOptionOut(BaseModel):
    rig_setup_id: int | None
    until_at: str | None
    camera_name: str
    image_scale_arcsec_per_pixel: float


class ProjectRigSetupsOut(BaseModel):
    rig_id: int
    rig_name: str
    declared: bool
    setups: list[ProjectSetupOut]
    setup_options: list[ProjectSetupOptionOut]
    base_parts: RigPartsIn
    change: RigPartsIn | None
    changed_groups: list[str]
