"""Shared input contracts for the revised imaging evaluator."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

CheckState = Literal["pass", "fail", "unknown", "not_counted"]
HourState = Literal["clear", "not_clear", "unknown", "outside"]
Verdict = Literal["go", "uncertain", "no", "not_enough_data", "night_over"]
ModelStatus = Literal["go", "no", "unresolved", "not_expected"]
WindowStatus = Literal["established", "impossible", "unresolved"]
ReasonCode = Literal[
    "clear_all_night",
    "clear_with_gaps",
    "short_window",
    "rain",
    "rain_amount",
    "rain_model_amount",
    "rain_missing",
    "clear_fraction",
    "min_hours",
    "gap",
    "no_window",
    "no_shared_window",
    "never_dark",
    "no_dark_time",
    "models_disagree",
    "forecasts_differ",
    "model_incomplete",
    "model_not_used",
    "fallback",
    "layer_advisory",
    "missing_data",
    "stale",
    "night_over",
]


@dataclass(frozen=True)
class ModelHour:
    cloud_total_pct: float | None
    cloud_layers_pct: tuple[float | None, float | None, float | None]
    precip_mm: float | None
    cloud_expected: bool
    amount_expected: bool


@dataclass(frozen=True)
class HourInput:
    start_utc: datetime
    models: Mapping[str, ModelHour]
    precip_probability_pct: float | None
    precip_mm: float | None
    wind_kmh: float | None
    gust_kmh: float | None
    temperature_c: float | None
    dew_point_c: float | None
    moon_altitude_deg: float | None


@dataclass(frozen=True)
class NightControls:
    gear_out_utc: datetime | None = None
    gear_in_utc: datetime | None = None
    imaging_from_utc: datetime | None = None
    imaging_until_utc: datetime | None = None


@dataclass(frozen=True)
class NightInput:
    sunset_utc: datetime | None
    sunrise_utc: datetime | None
    noon_start_utc: datetime
    noon_end_utc: datetime
    dark_intervals: list[tuple[datetime, datetime]]
    hours: list[HourInput]
    now_utc: datetime
    controls: NightControls
    cloud_models: tuple[str, ...]
    preferred_model: str
    combination: Literal["majority", "uncertain"]
    fallback_model: str
    stale_minutes: Mapping[str, int | None]


@dataclass(frozen=True)
class Reason:
    code: ReasonCode
    start_utc: datetime | None = None
    end_utc: datetime | None = None
    value: float | None = None
    limit: float | None = None
    requirement: str | None = None
    models: dict[str, ModelStatus] | None = None
    bound: Literal["at_most", "at_least"] | None = None
    model: str | None = None
    missing_hours: float | None = None


@dataclass(frozen=True)
class CoverageNote:
    model: str
    expected_until_utc: datetime | None
    status: ModelStatus | Literal["not_used"]


@dataclass(frozen=True)
class HourResult:
    start_utc: datetime
    elapsed: bool
    excluded: bool
    dark_minutes: float
    exposure_minutes: float
    checks: dict[str, CheckState]
    conditions: dict[str, CheckState]
    state: HourState
    session_state: HourState
    model_states: dict[str, HourState]
    disagrees: bool
    cloud_pct: dict[str, float | None]
    expected: dict[str, tuple[bool, bool]]
    dew_spread_c: float | None


@dataclass(frozen=True)
class NightResult:
    verdict: Verdict
    reasons: list[Reason]
    advisory: Reason | None
    clear_minutes: float
    dark_minutes: float
    unknown_minutes: float
    longest_gap: tuple[datetime, datetime] | None
    longest_clear_run: tuple[datetime, datetime] | None
    window: tuple[datetime, datetime] | None
    exposure: tuple[datetime, datetime] | None
    imaging: tuple[datetime, datetime] | None
    evaluated_from_utc: datetime | None
    primary_model: str
    fallback: bool
    cloud_combination: Literal["majority", "uncertain", "single"]
    differing_hours: int
    compared_hours: int
    cloud_models: tuple[str, ...]
    cloud_models_used: tuple[str, ...]
    default_cloud_used: bool
    model_statuses: dict[str, ModelStatus]
    coverage: list[CoverageNote]
    requirements: dict[str, CheckState | Literal["info"]]
    hours: list[HourResult]
