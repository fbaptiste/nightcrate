"""Pydantic models for project sessions and integration (v0.38.0).

A "session" is a capture batch: N identical light subs of one filter. It is
either hand-entered (``source='manual'``) or rebuilt from the project's cataloged
light frames by the v0.41.1 derive pass (``source='auto'``). Per-filter
integration is derived from these (exposure x sub count); per-filter goals were
removed in v0.41.1.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from nightcrate.services.line_names import LINE_NAMES

__all__ = [
    "LINE_NAMES",
    "IntegrationLine",
    "IntegrationSummary",
    "SessionCreate",
    "SessionResponse",
    "SessionUpdate",
]


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
    filter_label: str | None
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


# ── Integration summary ─────────────────────────────────────────────────────


class IntegrationLine(BaseModel):
    """One bar in the integration read-out.

    ``label`` is a free string, not the closed bandpass vocabulary: a derived
    session for a filter whose header name isn't a recognized line (``L-eXtreme``)
    is labelled by that name rather than collapsed into ``other``. Canonical
    bandpasses sort first, then raw names alphabetically.
    """

    label: str
    actual_minutes: float
    session_count: int
    """Distinct observing nights, not rows — a night split across exposures is one."""
    sub_count: int


class IntegrationSummary(BaseModel):
    lines: list[IntegrationLine]
    total_actual_minutes: float
    first_session_date: str | None
    last_session_date: str | None
