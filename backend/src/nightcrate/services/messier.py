"""Pure helpers for the Messier checklist."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, field_validator

MESSIER_NUMBERS: tuple[int, ...] = tuple(range(1, 111))
MIN_RIG_VIEW_FIELD_DEG = 0.05
MAX_RIG_VIEW_FIELD_DEG = 30.0


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


def rig_view_field_deg(major_deg: float, minor_deg: float) -> float | None:
    """Return a supported 4:3 survey width that fits the rig within 92%."""
    field_deg = max(major_deg, minor_deg * 4 / 3) / 0.92
    tolerance = 1e-12
    if (
        field_deg < MIN_RIG_VIEW_FIELD_DEG - tolerance
        or field_deg > MAX_RIG_VIEW_FIELD_DEG + tolerance
    ):
        return None
    return min(MAX_RIG_VIEW_FIELD_DEG, max(MIN_RIG_VIEW_FIELD_DEG, field_deg))


def slot_state(has_object: bool, ordered: list[Candidate]) -> SlotState:
    if not has_object:
        return "missing"
    if not ordered:
        return "none"
    if ordered[0].main_image_id is not None:
        return "imaged"
    return "project"
