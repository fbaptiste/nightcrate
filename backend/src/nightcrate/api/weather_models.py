"""Pydantic request and response models for the weather verdict API."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from nightcrate.services.imaging_rules import ImagingRules
from nightcrate.services.imaging_types import ModelStatus
from nightcrate.services.imaging_verdict import CheckState, HourState, Verdict


class NightControlsRequest(BaseModel):
    gear_out: AwareDatetime | None = None
    gear_in: AwareDatetime | None = None
    imaging_from: AwareDatetime | None = None
    imaging_until: AwareDatetime | None = None


class ForecastRequest(BaseModel):
    location_id: int
    rules: ImagingRules | None = None
    night_controls: dict[str, NightControlsRequest] = Field(default_factory=dict)


class ReasonResponse(BaseModel):
    code: str
    start: str | None = None
    end: str | None = None
    start_utc: datetime | None = None
    end_utc: datetime | None = None
    value: float | None = None
    limit: float | None = None
    requirement: str | None = None
    models: dict[str, ModelStatus] | None = None
    bound: Literal["at_most", "at_least"] | None = None
    model: str | None = None
    missing_hours: float | None = None


class CoverageResponse(BaseModel):
    model: str
    status: Literal["go", "no", "unresolved", "not_expected", "not_used"]
    expected_until: str | None = None
    expected_until_utc: datetime | None = None


class IntervalResponse(BaseModel):
    start: str
    end: str
    start_utc: datetime
    end_utc: datetime


class ExtremesResponse(BaseModel):
    max_precip_probability_pct: float | None = None
    max_precip_probability_at: str | None = None
    max_precip_probability_at_utc: datetime | None = None
    precip_mm_total: float | None = None
    precip_missing_hours: int
    precip_sum_start: str | None = None
    precip_sum_end: str | None = None
    precip_sum_start_utc: datetime | None = None
    precip_sum_end_utc: datetime | None = None
    max_gust_kmh: float | None = None
    max_gust_at: str | None = None
    max_gust_at_utc: datetime | None = None
    min_dew_spread_c: float | None = None
    min_dew_spread_at: str | None = None
    min_dew_spread_at_utc: datetime | None = None


class ExpectedFieldsResponse(BaseModel):
    cloud: bool
    amount: bool


class HourResponse(BaseModel):
    time: str
    start_utc: datetime
    elapsed: bool
    excluded: bool
    dark_minutes: float
    exposure_minutes: float
    darkness_category: Literal["day", "civil", "nautical", "astro"]
    state: HourState
    session_state: HourState
    model_states: dict[str, HourState]
    disagrees: bool
    checks: dict[str, CheckState]
    conditions: dict[str, CheckState]
    cloud_total_pct: float | None
    cloud_low_pct: float | None
    cloud_mid_pct: float | None
    cloud_high_pct: float | None
    cloud_pct: dict[str, float | None]
    expected: dict[str, ExpectedFieldsResponse]
    precip_probability_pct: float | None
    precip_mm: float | None
    model_precip_mm: dict[str, float | None]
    gust_kmh: float | None
    wind_kmh: float | None
    temperature_c: float | None
    dew_point_c: float | None
    dew_spread_c: float | None
    visibility_m: float | None
    moon_altitude_deg: float | None
    seeing: Literal["good", "fair", "poor"] | None
    transparency: Literal["good", "fair", "poor"] | None
    transparency_tier: Literal["primary", "fallback", "degraded"] | None


class NightResponse(BaseModel):
    date: str
    verdict: Verdict
    reason: ReasonResponse
    other_reasons: list[ReasonResponse]
    advisory: ReasonResponse | None
    clear_hours: float
    dark_hours: float
    unknown_hours: float
    clear_pct: float | None
    longest_gap_start: str | None
    longest_gap_end: str | None
    longest_gap_start_utc: datetime | None
    longest_gap_end_utc: datetime | None
    window_start: str | None
    window_end: str | None
    window_start_utc: datetime | None
    window_end_utc: datetime | None
    gear_out_start: str
    gear_out_end: str
    gear_out_start_utc: datetime
    gear_out_end_utc: datetime
    evaluated_from: str | None
    evaluated_end: str | None
    evaluated_from_utc: datetime | None
    evaluated_end_utc: datetime | None
    dark_intervals: list[IntervalResponse]
    # Sun below −6° / −12° / −18°, for the darkness band; display times.
    darkness_intervals: dict[Literal["civil", "nautical", "astronomical"], list[IntervalResponse]]
    exposure: IntervalResponse | None
    imaging: IntervalResponse | None
    controls: NightControlsRequest
    model_statuses: dict[str, ModelStatus]
    primary_model: str
    cloud_combination: Literal["majority", "uncertain", "single"]
    differing_hours: int
    compared_hours: int
    cloud_models: tuple[str, ...]
    cloud_models_used: tuple[str, ...]
    default_cloud_used: bool
    coverage: list[CoverageResponse]
    single_model: bool
    cloud_source: Literal["ecmwf", "best_match_fallback"]
    layer_model: str
    cloud_coarse_from: str | None
    cloud_coarse_from_utc: datetime | None
    stale_minutes: int | None
    requirements: dict[
        str,
        Literal["pass", "fail", "unknown", "not_counted", "info"],
    ]
    extremes: ExtremesResponse
    sunset: str | None
    sunset_utc: datetime | None
    sunrise: str | None
    sunrise_utc: datetime | None
    moon_illumination_pct: float
    moon_phase_name: str
    moonrise: str | None
    moonrise_utc: datetime | None
    moonset: str | None
    moonset_utc: datetime | None
    hours: list[HourResponse]


class StaleSourcesResponse(BaseModel):
    forecast: int | None
    cloud_models: int | None


class ForecastResponse(BaseModel):
    location_id: int
    location_name: str
    timezone: str
    geo_timezone: str | None
    rules: ImagingRules
    rules_saved: bool
    fetched_at: str
    evaluated_at: datetime
    stale_sources: StaleSourcesResponse
    run_age_minutes: dict[str, int | None]
    ignored_controls: list[str]
    nights: list[NightResponse]


class MethodologyResponse(BaseModel):
    summary: str
    details: str
