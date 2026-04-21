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
    # Visibility fields — populated when the planner is in
    # "tonight only" mode. In the "anytime" mode (restrict_tonight=False)
    # these are ``None`` because no visibility computation runs — the
    # planner just surfaces the full catalog so users can search by
    # name / type / magnitude without being gated on "is it up
    # tonight?".
    hours_visible: float | None
    max_altitude_deg: float | None
    peak_time_utc: str | None
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
    # Monotonic counter the frontend appends to thumbnail URLs as a
    # cache-buster so clearing the backend cache also evicts whatever
    # copies the user's browser HTTP cache is holding.
    generation: int = 0


class CacheClearResponse(BaseModel):
    deleted_files: int


# ─── v0.18.0 sky-tile grid layout ────────────────────────────────────────────


class SkyTileCellLayout(BaseModel):
    """One cell's identity + top-left position in the composite image."""

    nside: int
    ipix: int
    tier: str
    cell_i: int
    cell_j: int
    pixel_x: int
    pixel_y: int


class SkyTileGridLayout(BaseModel):
    """Layout returned by ``GET /api/planner/sky-tile-grid``.

    Gives the frontend everything it needs to compose the view: the
    region + tangent (informational; cells carry the full cache key),
    the source-pixel composite size, where the requested centre lands
    inside the composite, and the list of cells with their top-left
    source-pixel positions. ``pixel_x`` / ``pixel_y`` values align with
    the screen's east-left / north-up convention.
    """

    nside: int
    ipix: int
    tangent_ra_deg: float
    tangent_dec_deg: float
    tier: str
    cell_size_deg: float
    cell_width_px: int
    cell_height_px: int
    composite_width_px: int
    composite_height_px: int
    view_center_pixel_x: int
    view_center_pixel_y: int
    cells: list[SkyTileCellLayout]


class NearbyDsoItem(BaseModel):
    id: int
    primary_designation: str
    ra_deg: float
    dec_deg: float
    maj_axis_arcmin: float | None
    min_axis_arcmin: float | None
    obj_type: str
    type_group: str | None


class NearbyDsosResponse(BaseModel):
    items: list[NearbyDsoItem]
