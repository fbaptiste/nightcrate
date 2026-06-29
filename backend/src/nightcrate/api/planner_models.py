"""Pydantic response models for /api/planner/* endpoints."""

from __future__ import annotations

from pydantic import BaseModel

from nightcrate.services.planner_scoring import DimensionKey


class PlannerLocationSummary(BaseModel):
    id: int
    name: str


class PlannerHorizonSummary(BaseModel):
    """Echo of the horizon used to compute the snapshot — mirrors the
    location + rig summaries so the UI header can render "{horizon name}
    · {flat altitude}°" without a second fetch."""

    id: int
    name: str
    type: str  # 'custom' | 'artificial'
    flat_altitude_deg: float | None


class PlannerRigSummary(BaseModel):
    id: int
    name: str
    fov_major_deg: float
    fov_minor_deg: float


class DarkWindowOut(BaseModel):
    start_utc: str
    end_utc: str
    hours: float


class PlannerDesignation(BaseModel):
    catalog: str
    identifier: str
    display_form: str
    is_primary: bool


class DimensionBreakdownOut(BaseModel):
    """One dimension's per-target contribution to the score."""

    key: DimensionKey
    label: str
    score: float  # 0-1
    weight: float
    contribution: float  # score ** weight, the factor in the geometric mean
    inputs: list[str]


class ScoreBreakdownOut(BaseModel):
    """Score breakdown attached to each scored target.

    Gated targets (``score_pct=null``): ``gate_failures`` populated,
    ``dimensions`` empty. Scored targets: the reverse. Dropped
    dimensions (e.g., frame_fit without a rig) are omitted from
    ``dimensions``.
    """

    dimensions: list[DimensionBreakdownOut]
    gate_failures: list[str]


class PlannerTargetItem(BaseModel):
    dso_id: int
    primary_designation: str
    common_name: str | None
    obj_type: str
    ra_deg: float | None
    dec_deg: float | None
    constellation: str | None
    maj_axis_arcmin: float | None
    min_axis_arcmin: float | None
    mag_v: float | None
    distance_pc: float | None
    # Full catalog cross-references surfaced on the planner card. The
    # primary is already in ``primary_designation`` but carried here
    # too so the frontend doesn't have to reason about the gap. Sorted
    # primary-first, then alphabetically by ``display_form``.
    designations: list[PlannerDesignation] = []
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
    # "up" / "rising" / "set" relative to the request time. ``None``
    # in Anytime mode (no location, no now-anchored question).
    now_status: str | None = None
    # Wikipedia article surfaced from ``dso_external_ref`` for chip
    # rendering on the planner card. Full external-ref list (incl.
    # Wikidata QID) stays on the DSO-detail endpoint — this is the
    # minimal list-payload carve-out for the one chip the card shows.
    wikipedia_url: str | None = None
    wikipedia_label: str | None = None
    # ─── Scoring (v0.21.0) ────────────────────────────────────────
    # Populated only in Tonight mode. ``score_pct=null`` means a
    # hard gate tripped — the breakdown's ``gate_failures`` lists
    # the reasons. In Anytime mode all three fields are ``null``.
    score_pct: int | None = None
    quality_label: str | None = None  # "Excellent" / "Good" / "Fair" / "Poor"
    score_breakdown: ScoreBreakdownOut | None = None


class PlannerTargetsResponse(BaseModel):
    # ``None`` in Anytime mode when the caller didn't supply a location
    # — catalog browsing is location-independent.
    location: PlannerLocationSummary | None
    # Echo of the effective horizon used for tonight-mode compute.
    # ``None`` in Anytime mode (no location → no horizon either).
    horizon: PlannerHorizonSummary | None = None
    rig: PlannerRigSummary | None
    date: str
    dark_window: DarkWindowOut | None
    moon_phase_pct: float
    # One of the eight standard moon-phase names ("New Moon",
    # "Waxing Crescent", "First Quarter", …). ``null`` in Anytime
    # mode when no date / location anchor is available.
    moon_phase_name: str | None
    total: int
    offset: int
    limit: int
    items: list[PlannerTargetItem]
    # Facet counts computed alongside the filtered items so the
    # frontend's pill filters can render labels like "Galaxy (234)"
    # that reflect the current filter state instead of the full
    # catalog total. Each dict is keyed by its dimension's value
    # (raw obj_type codes, catalog codes, 3-letter constellation
    # codes); values are the number of DSOs that would survive if
    # only that dimension's value were selected, with all OTHER
    # filters held constant (faceted-search convention).
    raw_type_counts: dict[str, int]
    catalog_counts: dict[str, int]
    constellation_counts: dict[str, int]


class SingleTargetScoreResponse(BaseModel):
    """Response of ``GET /api/planner/targets/{dso_id}/score`` — used by
    the detail panel to refresh scoring when its rig / horizon /
    location differs from the list page's choice."""

    dso_id: int
    score_pct: int | None
    quality_label: str | None
    score_breakdown: ScoreBreakdownOut | None
    # Visibility summary for the same (dso, location, horizon, date) — lets the
    # detail panel populate its fact grid for an object that isn't in the
    # currently-loaded list page (e.g. switched to via the FOV annotation).
    hours_visible: float | None = None
    max_altitude_deg: float | None = None
    peak_time_utc: str | None = None
    transit_time_utc: str | None = None
    altitude_at_transit_deg: float | None = None
    min_moon_separation_deg: float | None = None


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
    moon_azimuth_deg: list[float]
    moon_separation_deg: list[float]
    horizon_altitude_at_object_az: list[float]
    twilight: TwilightBandsOut
    moon_phase_pct: float
    peak_time_utc: str
    peak_altitude_deg: float
    transit_time_utc: str | None


class AnnualHoursPoint(BaseModel):
    date: str
    hours: float


class MoonDataPoint(BaseModel):
    date: str
    illumination_pct: float
    min_separation_deg: float | None
    max_altitude_deg: float | None


class AnnualHoursResponse(BaseModel):
    dso_id: int
    year: int
    horizon_id: int
    horizon_type: str
    horizon_name: str
    flat_altitude_deg: float | None
    moon_sep_deg: float
    # Location-tz "tonight" date (ISO), or None when not in the plotted year.
    # Lets the chart anchor its "today" marker to the matching night instead
    # of the current UTC instant (which mis-snaps to the next day in the
    # evening, since each point is anchored at noon UTC).
    today: str | None
    points: list[AnnualHoursPoint]
    filtered_points: list[AnnualHoursPoint]
    moon_data: list[MoonDataPoint]


class MoonYearPoint(BaseModel):
    date: str
    max_altitude_deg: float | None  # peak Moon altitude during astro darkness
    illumination_pct: float


class MoonYearResponse(BaseModel):
    year: int
    location_id: int
    location_name: str
    timezone: str
    points: list[MoonYearPoint]
    new_moons: list[str]  # ISO dates — dark-sky imaging windows
    full_moons: list[str]


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


class NearbyDsosResponse(BaseModel):
    items: list[NearbyDsoItem]
