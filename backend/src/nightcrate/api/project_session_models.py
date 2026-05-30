"""Pydantic models for project sessions, integration, and filter goals (v0.38.0).

A "session" here is a manually-entered capture batch: N identical light subs
of one filter. Per-filter ACTUAL integration is derived from these (exposure x
sub count); GOALS are entered separately. The v0.39.0 ingest pipeline will
auto-fill sessions from scanned sub-frames (user can override).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

# Closed bandpass vocabulary — mirrors filter_passband.line_name (migration 0005).
LINE_NAMES: tuple[str, ...] = (
    "Ha",
    "Hb",
    "Oiii",
    "Sii",
    "Nii",
    "OI",
    "Lum",
    "R",
    "G",
    "B",
    "R+",
    "UVIR",
    "LP",
    "ND",
    "other",
)


# ── Sessions ──────────────────────────────────────────────────────────────


class SessionCreate(BaseModel):
    rig_id: int | None = None
    filter_id: int | None = None
    line_name: str | None = None
    exposure_seconds: float = Field(gt=0)
    gain: int | None = Field(default=None, ge=0)
    num_subs: int = Field(gt=0)
    binning: int | None = Field(default=None, ge=1)
    session_date: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _require_filter_or_line(self) -> SessionCreate:
        if self.filter_id is None and self.line_name is None:
            raise ValueError("A specific filter or a bandpass line_name is required")
        if self.line_name is not None and self.line_name not in LINE_NAMES:
            raise ValueError(f"Invalid line_name: {self.line_name}")
        return self


class SessionUpdate(BaseModel):
    """Partial update; only fields present in the body are changed. Sending a
    field as null clears it (except exposure_seconds/num_subs, which are
    required — clearing them is rejected by the endpoint)."""

    rig_id: int | None = None
    filter_id: int | None = None
    line_name: str | None = None
    exposure_seconds: float | None = Field(default=None, gt=0)
    gain: int | None = Field(default=None, ge=0)
    num_subs: int | None = Field(default=None, gt=0)
    binning: int | None = Field(default=None, ge=1)
    session_date: str | None = None
    notes: str | None = None


class SessionResponse(BaseModel):
    id: int
    project_id: int
    rig_id: int | None
    rig_name: str | None
    filter_id: int | None
    filter_name: str | None
    line_name: str | None
    exposure_seconds: float
    gain: int | None
    num_subs: int
    binning: int | None
    session_date: str | None
    notes: str | None
    source: str
    integration_minutes: float
    created_at: str
    updated_at: str


# ── Integration goals + summary ─────────────────────────────────────────────


class FilterGoal(BaseModel):
    line_name: str
    goal_minutes: float = Field(gt=0)

    @model_validator(mode="after")
    def _check_line(self) -> FilterGoal:
        if self.line_name not in LINE_NAMES:
            raise ValueError(f"Invalid line_name: {self.line_name}")
        return self


class FilterGoalsSet(BaseModel):
    """Replace the full set of per-filter goals for a project."""

    goals: list[FilterGoal]


class IntegrationLine(BaseModel):
    line_name: str
    actual_minutes: float
    goal_minutes: float | None
    session_count: int
    sub_count: int


class IntegrationSummary(BaseModel):
    lines: list[IntegrationLine]
    total_actual_minutes: float
    first_session_date: str | None
    last_session_date: str | None
