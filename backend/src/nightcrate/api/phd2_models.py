"""PHD2 guide-log analyzer — API response / request wrappers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from nightcrate.services.phd2_metrics import SectionMetrics
from nightcrate.services.phd2_models import LogSection, ParsedLog


class ParseRequest(BaseModel):
    """Request body for ``POST /api/phd2/parse``."""

    model_config = ConfigDict(extra="forbid")

    path: str


class SectionWithMetrics(BaseModel):
    """Per-section bundle: raw parsed section + computed top-line metrics.

    Kept as a wrapper (rather than merging metrics onto `LogSection`) so the
    service layer's data model stays purely parser-shaped — v3+ diagnostics
    will wrap similarly without muddying the parse output.
    """

    model_config = ConfigDict(extra="forbid")

    section: LogSection
    metrics: SectionMetrics


class ParseResponse(BaseModel):
    """Response body for ``POST /api/phd2/parse``."""

    model_config = ConfigDict(extra="forbid")

    log: ParsedLog
    sections: list[SectionWithMetrics]


class CacheStatsResponse(BaseModel):
    """Response body for ``GET /api/phd2/cache/stats``."""

    model_config = ConfigDict(extra="forbid")

    entries: int
    max_entries: int
    ttl_seconds: int
