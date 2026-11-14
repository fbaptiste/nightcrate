"""Pure models and display rules for deep-sky object facts."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel


def catalog_numbers(
    name: str,
    primary: str,
    designations: Sequence[tuple[str, str]],
) -> list[str]:
    """Return Messier and NGC names, or the primary designation as fallback."""
    preferred = [
        display_form
        for catalog in ("messier", "ngc")
        for designation_catalog, display_form in designations
        if designation_catalog == catalog
    ]
    candidates = preferred or [primary]
    result: list[str] = []
    seen = {name.casefold()}
    for value in candidates:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


class OtherObjectDistance(BaseModel):
    dso_id: int
    distance_pc: float
    distance_estimated: bool


class OtherObject(BaseModel):
    dso_id: int
    name: str
    designation: str
    obj_type: str
    constellation: str | None
    distance_pc: float | None
    distance_estimated: bool
    wikipedia_url: str | None
