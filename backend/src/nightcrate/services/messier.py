"""Pure helpers for the Messier checklist."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from nightcrate.services.thumbnails import compute_angular_extent_deg

MESSIER_NUMBERS: tuple[int, ...] = tuple(range(1, 111))


class Candidate(BaseModel):
    project_id: int
    name: str
    status: str
    created_at: str
    main_image_id: int | None
    dates: list[date]

    @field_validator("dates")
    @classmethod
    def _sort_dates(cls, value: list[date]) -> list[date]:
        return sorted(value)


class PictureField(BaseModel):
    width_deg: float
    height_deg: float


class SolveFacts(BaseModel):
    image_path: str
    image_width: int
    image_height: int
    fov_width_arcmin: float | None
    fov_height_arcmin: float | None


SlotState = Literal["imaged", "project", "none", "missing"]


def never_rises(latitude_deg: float, dec_deg: float | None) -> bool:
    """Return whether a target stays more than one degree below the horizon."""
    return dec_deg is not None and 90 - abs(latitude_deg - dec_deg) < -1


def order_candidates(items: list[Candidate], *, image_first: bool) -> list[Candidate]:
    """Order projects by image, latest session, creation time, then id."""
    ordered = sorted(items, key=lambda item: item.project_id, reverse=True)

    def created_at_key(item: Candidate) -> tuple[bool, float]:
        try:
            parsed = datetime.fromisoformat(item.created_at)
        except OverflowError, ValueError:
            return False, 0
        return True, parsed.timestamp()

    ordered.sort(key=created_at_key, reverse=True)
    ordered.sort(
        key=lambda item: (bool(item.dates), item.dates[-1] if item.dates else date.min),
        reverse=True,
    )
    if image_first:
        ordered.sort(key=lambda item: item.main_image_id is not None, reverse=True)
    return ordered


def main_image_field(
    solve: SolveFacts | None,
    main_path: str | None,
    main_size_px: tuple[int, int] | None,
) -> PictureField | None:
    """Return the solved field when it safely describes the displayed image."""
    if (
        solve is None
        or solve.fov_width_arcmin is None
        or solve.fov_height_arcmin is None
        or solve.image_width <= 0
        or solve.image_height <= 0
    ):
        return None
    if main_path != solve.image_path:
        if main_size_px is None or main_size_px[0] <= 0 or main_size_px[1] <= 0:
            return None
        main_ratio = main_size_px[0] / main_size_px[1]
        solve_ratio = solve.image_width / solve.image_height
        if abs(main_ratio / solve_ratio - 1) > 0.005:
            return None
    return PictureField(
        width_deg=solve.fov_width_arcmin / 60,
        height_deg=solve.fov_height_arcmin / 60,
    )


def crop_field(main: PictureField, crop_w: float, crop_h: float) -> PictureField:
    return PictureField(
        width_deg=main.width_deg * crop_w,
        height_deg=main.height_deg * crop_h,
    )


def survey_field_deg(maj_axis_arcmin: float | None) -> float:
    return compute_angular_extent_deg(
        "checklist",
        dso_maj_axis_arcmin=maj_axis_arcmin,
    )


def slot_state(has_object: bool, ordered: list[Candidate]) -> SlotState:
    if not has_object:
        return "missing"
    if not ordered:
        return "none"
    if ordered[0].main_image_id is not None:
        return "imaged"
    return "project"
