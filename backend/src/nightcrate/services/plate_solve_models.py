"""Pydantic models for the plate solving service."""

from typing import Literal

from pydantic import BaseModel


class PlateSolveRequest(BaseModel):
    image_path: str
    hdu: int = 0
    mode: Literal["auto", "near", "blind", "extract"] = "auto"
    ra_hint: float | None = None
    dec_hint: float | None = None
    fov_hint: float | None = None
    timeout: int = 180


class PlateSolveResult(BaseModel):
    solved: bool
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
