"""Pydantic models for the plate solving service."""

import math
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

SolveStep = Literal[
    "load",
    "near_index",
    "near_catalog",
    "blind_known_scale",
    "blind_unknown_scale",
    "astap_near",
    "astap_blind",
]
AttemptOutcome = Literal[
    "solved",
    "no_match",
    "skipped",
    "step_timeout",
    "overall_timeout",
    "cancelled",
    "ambiguous",
    "too_few_stars",
    "error",
]


def check_solve_hints(
    *,
    ra_hint: float | None,
    dec_hint: float | None,
    fov_hint: float | None,
    scale_hint_arcsec: float | None,
    position: Literal["auto", "none"],
    scale: Literal["auto", "none"],
) -> None:
    if (ra_hint is None) != (dec_hint is None):
        raise ValueError("RA and Dec hints must be provided together.")
    if ra_hint is not None:
        if not math.isfinite(ra_hint) or not 0 <= ra_hint < 360:
            raise ValueError("RA hint must be finite and in [0, 360).")
        if dec_hint is None or not math.isfinite(dec_hint) or not -90 <= dec_hint <= 90:
            raise ValueError("Dec hint must be finite and in [-90, 90].")
        if position == "none":
            raise ValueError("Position hints cannot be used when position is 'none'.")
    if scale == "none" and (scale_hint_arcsec is not None or fov_hint is not None):
        raise ValueError("Scale hints cannot be used when scale is 'none'.")


class SolveAttempt(BaseModel):
    solver: Literal["native", "astap"]
    step: SolveStep
    position_source: Literal["request", "header", "none"]
    scale_source: Literal["request", "header", "none"]
    ranges: list[str] = []
    layers: list[str] = []
    outcome: AttemptOutcome | None = None
    seconds: float | None = None
    detail: str | None = None


class PlateSolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_path: str
    hdu: int = Field(default=0, ge=0)
    operation_id: UUID
    ra_hint: float | None = None
    dec_hint: float | None = None
    fov_hint: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    scale_hint_arcsec: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    position: Literal["auto", "none"] = "auto"
    scale: Literal["auto", "none"] = "auto"
    timeout: int = 180
    solver: Literal["native", "astap"] | None = None

    @model_validator(mode="after")
    def validate_hints(self) -> PlateSolveRequest:
        check_solve_hints(
            ra_hint=self.ra_hint,
            dec_hint=self.dec_hint,
            fov_hint=self.fov_hint,
            scale_hint_arcsec=self.scale_hint_arcsec,
            position=self.position,
            scale=self.scale,
        )
        return self


class PlateSolveResult(BaseModel):
    solved: bool
    solver: Literal["native", "astap"] = "astap"
    star_catalog: str | None = None
    stars_detected: int | None = None
    stars_matched: int | None = None
    rms_px: float | None = None
    rms_arcsec: float | None = None
    log_odds: float | None = None
    solve_path: Literal["near_index", "near_catalog", "blind"] | None = None
    scale_stage: str | None = None
    failure_reason: str | None = None
    ra_deg: float | None = None
    dec_deg: float | None = None
    ra_hms: str | None = None
    dec_dms: str | None = None
    pixel_scale_arcsec: float | None = None
    rotation_deg: float | None = None
    fov_width_arcmin: float | None = None
    fov_height_arcmin: float | None = None
    image_width: int | None = None
    image_height: int | None = None
    cd1_1: float | None = None
    cd1_2: float | None = None
    cd2_1: float | None = None
    cd2_2: float | None = None
    crpix1: float | None = None
    crpix2: float | None = None
    error_message: str | None = None
    warning: str | None = None
    solve_time_seconds: float | None = None
    attempts: list[SolveAttempt] = []
