"""Pydantic response models for /api/planner/* endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class PlannerLocationSummary(BaseModel):
    id: int
    name: str
    has_custom_horizon: bool


class PlannerRigSummary(BaseModel):
    id: int
    name: str
    fov_major_deg: float
    fov_minor_deg: float


class DarkWindowOut(BaseModel):
    start_utc: str
    end_utc: str
    hours: float


class PlannerTargetItem(BaseModel):
    dso_id: int
    primary_designation: str
    common_name: str | None
    obj_type: str
    type_group: str | None
    ra_deg: float | None
    dec_deg: float | None
    constellation: str | None
    maj_axis_arcmin: float | None
    min_axis_arcmin: float | None
    mag_v: float | None
    distance_pc: float | None
    hours_visible: float
    max_altitude_deg: float
    peak_time_utc: str
    transit_time_utc: str | None
    altitude_at_transit_deg: float | None
    min_moon_separation_deg: float | None
    coverage_pct: float | None = None


class PlannerTargetsResponse(BaseModel):
    location: PlannerLocationSummary
    rig: PlannerRigSummary | None
    date: str
    dark_window: DarkWindowOut | None
    moon_phase_pct: float
    total: int
    offset: int
    limit: int
    items: list[PlannerTargetItem]


class TwilightBandsOut(BaseModel):
    sunset_utc: str | None
    civil_end_utc: str | None
    nautical_end_utc: str | None
    astro_start_utc: str | None
    astro_end_utc: str | None
    nautical_start_utc: str | None
    civil_start_utc: str | None
    sunrise_utc: str | None


class SkyTrackResponse(BaseModel):
    dso_id: int
    times_utc: list[str]
    object_altitude_deg: list[float]
    object_azimuth_deg: list[float]
    moon_altitude_deg: list[float]
    horizon_altitude_at_object_az: list[float]
    twilight: TwilightBandsOut
    moon_phase_pct: float
    peak_time_utc: str
    peak_altitude_deg: float
    transit_time_utc: str | None


class ThumbnailCacheStats(BaseModel):
    total_bytes: int
    row_count: int
    max_bytes: int


class CacheClearResponse(BaseModel):
    deleted_files: int
