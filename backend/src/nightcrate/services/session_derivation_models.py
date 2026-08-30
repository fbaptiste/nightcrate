"""Pydantic shapes for session derivation (v0.41.1)."""

from __future__ import annotations

from pydantic import BaseModel


class DerivedSession(BaseModel):
    """One row the derivation will write into ``project_session``."""

    night: str
    rig_id: int | None
    line_name: str
    filter_label: str | None
    exposure_seconds: float
    gain: int | None
    binning: int | None
    num_subs: int


class DerivationSummary(BaseModel):
    """Result of a derive pass, surfaced to the user as a toast."""

    project_id: int
    lights_considered: int = 0
    lights_skipped: int = 0
    """Lights that could not become part of a session — a non-positive exposure,
    which ``project_session.exposure_seconds CHECK (> 0)`` would reject."""
    sessions_replaced: int = 0
    """``source='auto'`` rows deleted before the rebuild."""
    sessions_created: int = 0
    manual_sessions_kept: int = 0
