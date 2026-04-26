"""PHD2 guide-log analyzer — API response / request wrappers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from nightcrate.services.phd2_metrics import SectionMetrics
from nightcrate.services.phd2_models import LogSection, ParsedLog

__all__ = [
    "CacheStatsResponse",
    "ParseRequest",
    "ParseResponse",
    "SectionAnalysis",
    "SectionWithMetrics",
]


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str


class SectionAnalysis(BaseModel):
    """Per-section derived data attached to ``SectionWithMetrics``.

    Reserved for future per-section analytics; currently empty after the
    v0.27.0 cleanup. Kept as a model so the response shape is forward-
    compatible without breaking older clients.
    """

    model_config = ConfigDict(extra="forbid")


class SectionWithMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: LogSection
    metrics: SectionMetrics
    analysis: SectionAnalysis = SectionAnalysis()


class ParseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    log: ParsedLog
    sections: list[SectionWithMetrics]


class CacheStatsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: int
    max_entries: int
    ttl_seconds: int
