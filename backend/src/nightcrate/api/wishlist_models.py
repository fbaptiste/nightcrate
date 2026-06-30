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


# ── Sections ─────────────────────────────────────────────────────────────────


class SectionResponse(BaseModel):
    id: int
    name: str
    sort_order: int


class CreateSectionRequest(BaseModel):
    name: str = "New Section"


class RenameSectionRequest(BaseModel):
    name: str


class ReorderSectionsRequest(BaseModel):
    section_ids: list[int]


class MoveFavoriteRequest(BaseModel):
    section_id: int | None = None
    sort_order: int = 0


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
    moon_filter_enabled: bool
    max_illumination_pct: int
    min_separation_deg: int
    moon_combine: str
    threshold_hours: float
    date_ranges: list[DateRangeOut]
    notes: str | None
    created_at: str
    updated_at: str


class FavoriteFullItem(BaseModel):
    dso: FavoriteDsoSummary
    sort_order: int
    section_id: int | None
    plan_count: int
    plans: list[PlanSummary]
    created_at: str


class FavoritesFullResponse(BaseModel):
    items: list[FavoriteFullItem]
    sections: list[SectionResponse]
    total: int


class ReorderItemIn(BaseModel):
    dso_id: int
    section_id: int | None = None
    sort_order: int = 0


class ReorderFavoritesRequest(BaseModel):
    items: list[ReorderItemIn]


# ── Plans ────────────────────────────────────────────────────────────────────


class CreatePlanRequest(BaseModel):
    dso_id: int
    location_id: int
    horizon_id: int
    rig_id: int
    moon_sep_deg: int = 0
    moon_filter_enabled: bool = False
    max_illumination_pct: int = 50
    min_separation_deg: int = 60
    moon_combine: str = "and"
    threshold_hours: float = 2.0
    date_ranges: list[DateRange] = []
    notes: str | None = None


class UpdatePlanRequest(BaseModel):
    location_id: int | None = None
    horizon_id: int | None = None
    rig_id: int | None = None
    moon_sep_deg: int | None = None
    moon_filter_enabled: bool | None = None
    max_illumination_pct: int | None = None
    min_separation_deg: int | None = None
    moon_combine: str | None = None
    threshold_hours: float | None = None
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
    moon_filter_enabled: bool
    max_illumination_pct: int
    min_separation_deg: int
    moon_combine: str
    threshold_hours: float
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
    section_id: int | None = None
    section_name: str | None = None


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
    # Location-tz "tonight" date (ISO) — the calendar's today marker anchors
    # to this so it lands on the right month/day in the evening.
    today: str
    months: list[str]
    targets: list[CalendarTargetRow]
    sections: list[SectionResponse]
    moon_phases: list[MoonPhaseMonth]
