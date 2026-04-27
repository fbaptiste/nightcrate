"""Pydantic request/response models for /api/planner/wishlist/* endpoints."""

from __future__ import annotations

from pydantic import BaseModel

# ── Shared ───────────────────────────────────────────────────────────────────


class DateRange(BaseModel):
    start_date: str
    end_date: str


class DateRangeOut(BaseModel):
    id: int
    start_date: str
    end_date: str


# ── Favorites ────────────────────────────────────────────────────────────────


class AddFavoriteRequest(BaseModel):
    dso_id: int


class FavoriteIdsResponse(BaseModel):
    dso_ids: list[int]


class FavoriteDsoSummary(BaseModel):
    dso_id: int
    primary_designation: str
    common_name: str | None
    obj_type: str
    constellation: str | None
    ra_deg: float | None
    dec_deg: float | None
    mag_v: float | None
    maj_axis_arcmin: float | None


class PlanSummary(BaseModel):
    id: int
    location_id: int
    location_name: str
    horizon_id: int
    horizon_name: str
    rig_id: int
    rig_name: str
    moon_sep_deg: int
    date_ranges: list[DateRangeOut]
    notes: str | None
    created_at: str
    updated_at: str


class FavoriteFullItem(BaseModel):
    dso: FavoriteDsoSummary
    sort_order: int
    plan_count: int
    plans: list[PlanSummary]
    created_at: str


class FavoritesFullResponse(BaseModel):
    items: list[FavoriteFullItem]
    total: int


class ReorderFavoritesRequest(BaseModel):
    dso_ids: list[int]


# ── Plans ────────────────────────────────────────────────────────────────────


class CreatePlanRequest(BaseModel):
    dso_id: int
    location_id: int
    horizon_id: int
    rig_id: int
    moon_sep_deg: int = 0
    date_ranges: list[DateRange] = []
    notes: str | None = None


class UpdatePlanRequest(BaseModel):
    location_id: int | None = None
    horizon_id: int | None = None
    rig_id: int | None = None
    moon_sep_deg: int | None = None
    date_ranges: list[DateRange] | None = None
    notes: str | None = None
    clear_notes: bool = False


class PlanResponse(BaseModel):
    id: int
    dso_id: int
    primary_designation: str
    common_name: str | None
    location_id: int
    location_name: str
    horizon_id: int
    horizon_name: str
    rig_id: int
    rig_name: str
    moon_sep_deg: int
    date_ranges: list[DateRangeOut]
    notes: str | None
    created_at: str
    updated_at: str


class PlanListResponse(BaseModel):
    items: list[PlanResponse]
    total: int


# ── Calendar ─────────────────────────────────────────────────────────────────


class CalendarTargetRow(BaseModel):
    dso_id: int
    primary_designation: str
    common_name: str | None
    plan_id: int
    date_ranges: list[DateRangeOut]
    notes: str | None
    monthly_hours: list[float]


class MoonPhaseMonth(BaseModel):
    month: str
    new_moon_date: str
    full_moon_date: str


class CalendarResponse(BaseModel):
    location_id: int
    location_name: str
    rig_id: int
    rig_name: str
    horizon_id: int
    horizon_name: str
    months: list[str]
    targets: list[CalendarTargetRow]
    moon_phases: list[MoonPhaseMonth]
