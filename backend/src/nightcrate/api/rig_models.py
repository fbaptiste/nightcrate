"""Pydantic models for the rig API."""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── Request Models ───────────────────────────────────────────────────────────


class RigFilterSlotIn(BaseModel):
    slot_number: int = Field(ge=1)
    filter_id: int


class RigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    telescope_configuration_id: int
    camera_id: int
    filter_wheel_id: int | None = None
    single_filter_id: int | None = None
    mount_id: int | None = None
    focuser_id: int | None = None
    oag_id: int | None = None
    guide_scope_id: int | None = None
    guide_camera_id: int | None = None
    computer_id: int | None = None
    software_id: int | None = None
    is_default: bool = False
    notes: str | None = None
    filter_slots: list[RigFilterSlotIn] = []


class RigUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    telescope_configuration_id: int | None = None
    camera_id: int | None = None
    filter_wheel_id: int | None = None
    single_filter_id: int | None = None
    mount_id: int | None = None
    focuser_id: int | None = None
    oag_id: int | None = None
    guide_scope_id: int | None = None
    guide_camera_id: int | None = None
    computer_id: int | None = None
    software_id: int | None = None
    is_default: bool | None = None
    notes: str | None = None
    filter_slots: list[RigFilterSlotIn] | None = None


# ── Response Models ──────────────────────────────────────────────────────────


class RigFilterSlotOut(BaseModel):
    slot_number: int
    filter_id: int
    filter_name: str
    filter_type_name: str
    passbands: list[str]


class RigWarning(BaseModel):
    field: str
    message: str


class SamplingAssessment(BaseModel):
    image_scale: float
    ideal_range_low: float
    ideal_range_high: float
    seeing_fwhm_low: float
    seeing_fwhm_high: float
    seeing_source: str
    seeing_location_name: str | None
    assessment: str
    recommendation: str
    binning_recommendations: dict[int, str]


class RigCalculators(BaseModel):
    image_scale_arcsec_per_pixel: float
    image_scale_arcsec_per_pixel_binned: dict[int, float]
    field_of_view_arcmin: tuple[float, float]
    field_of_view_deg: tuple[float, float]
    focal_ratio: float
    dawes_limit_arcsec: float
    rayleigh_limit_arcsec: float
    max_useful_magnification: float
    sensor_diagonal_mm: float | None
    image_circle_mm: float | None
    sensor_coverage_pct: float | None
    sampling_assessment: SamplingAssessment
    guide_image_scale_arcsec_per_pixel: float | None = None
    guide_field_of_view_arcmin: tuple[float, float] | None = None


class RigOut(BaseModel):
    id: int
    name: str
    description: str | None
    telescope_configuration_id: int
    telescope_name: str
    telescope_config_name: str
    effective_focal_length_mm: float
    effective_focal_ratio: float
    aperture_mm: float
    camera_id: int
    camera_name: str
    pixel_size_um: float
    sensor_resolution_x: int
    sensor_resolution_y: int
    sensor_width_mm: float | None
    sensor_height_mm: float | None
    sensor_type: str
    filter_wheel_id: int | None
    filter_wheel_name: str | None
    filter_wheel_positions: int | None
    single_filter_id: int | None
    single_filter_name: str | None
    mount_id: int | None
    mount_name: str | None
    focuser_id: int | None
    focuser_name: str | None
    oag_id: int | None
    oag_name: str | None
    guide_scope_id: int | None
    guide_scope_name: str | None
    guide_scope_focal_length_mm: float | None
    guide_camera_id: int | None
    guide_camera_name: str | None
    computer_id: int | None
    computer_name: str | None
    software_id: int | None
    software_name: str | None
    filter_slots: list[RigFilterSlotOut]
    is_default: bool
    active: bool
    notes: str | None
    created_at: str
    updated_at: str
    calculators: RigCalculators
    warnings: list[RigWarning]


# ── Equipment Options ────────────────────────────────────────────────────────


class TelescopeConfigOption(BaseModel):
    id: int
    config_name: str
    effective_focal_length_mm: float
    effective_focal_ratio: float
    effective_image_circle_mm: float | None


class TelescopeWithConfigs(BaseModel):
    telescope_id: int
    telescope_name: str
    manufacturer_name: str
    aperture_mm: float
    configs: list[TelescopeConfigOption]


class CameraOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str
    pixel_size_um: float
    resolution_x: int
    resolution_y: int
    sensor_width_mm: float | None
    sensor_height_mm: float | None
    sensor_type: str


class FilterWheelOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str
    num_positions: int


class FilterOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str
    filter_type_name: str


class MountOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str


class FocuserOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str


class OagOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str


class GuideScopeOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str
    focal_length_mm: float | None


class ComputerOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str


class SoftwareOption(BaseModel):
    id: int
    name: str
    category: str


class EquipmentOptionsOut(BaseModel):
    telescopes: list[TelescopeWithConfigs]
    cameras: list[CameraOption]
    filter_wheels: list[FilterWheelOption]
    filters: list[FilterOption]
    mounts: list[MountOption]
    focusers: list[FocuserOption]
    oags: list[OagOption]
    guide_scopes: list[GuideScopeOption]
    computers: list[ComputerOption]
    software: list[SoftwareOption]
