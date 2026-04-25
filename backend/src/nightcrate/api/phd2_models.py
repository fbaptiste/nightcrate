"""PHD2 guide-log analyzer — API response / request wrappers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from nightcrate.services.phd2_metrics import SectionMetrics
from nightcrate.services.phd2_models import FftPeak, FftResult, LogSection, ParsedLog

__all__ = [
    "CacheStatsResponse",
    "FftPeak",
    "FftResult",
    "ParseRequest",
    "ParseResponse",
    "SectionAnalysis",
    "SectionWithMetrics",
    "WormMarker",
    "WormMarkerSource",
]


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    rig_id: int | None = None


WormMarkerSource = Literal["mount", "heuristic"]


class WormMarker(BaseModel):
    """Spectrum-overlay annotation pointing at the worm-gear period."""

    model_config = ConfigDict(extra="forbid")

    period_s: float
    source: WormMarkerSource
    label: str
    mount_name: str | None = None
    matched_peak: FftPeak | None = None


class SectionAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fft_ra: FftResult | None = None
    fft_dec: FftResult | None = None
    worm_marker: WormMarker | None = None


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
