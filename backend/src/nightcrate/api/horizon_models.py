"""Pydantic models for the horizon API."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class HorizonPointModel(BaseModel):
    azimuth_deg: float = Field(ge=0.0, lt=360.0)
    altitude_deg: float = Field(ge=-5.0, le=90.0)


class HorizonPut(BaseModel):
    """Body for ``PUT /api/locations/{id}/horizon``. Editor-driven, so
    ``source`` is pinned to ``'drawn'``."""

    source: Literal["drawn"] = "drawn"
    points: list[HorizonPointModel]
    notes: str | None = None

    @field_validator("points")
    @classmethod
    def _at_least_two_points(cls, v: list[HorizonPointModel]) -> list[HorizonPointModel]:
        if len(v) < 2:
            raise ValueError("A horizon needs at least 2 points.")
        return v


class HorizonResponse(BaseModel):
    location_id: int
    source: Literal["imported", "drawn"]
    source_filename: str | None
    notes: str | None
    points: list[HorizonPointModel]
    created_at: str
    updated_at: str


class HorizonImportResponse(BaseModel):
    horizon: HorizonResponse
    warnings: list[str]


class HorizonParseResponse(BaseModel):
    """Body returned by ``POST /api/horizons/parse``. Parses a horizon file
    without persisting anything — used by the Location editor's staged-save
    flow."""

    points: list[HorizonPointModel]
    warnings: list[str]
    source_filename: str | None
