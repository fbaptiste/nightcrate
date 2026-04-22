"""Pydantic models for the horizon API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class HorizonPointModel(BaseModel):
    azimuth_deg: float = Field(ge=0.0, lt=360.0)
    altitude_deg: float = Field(ge=-5.0, le=90.0)


class HorizonCreate(BaseModel):
    """Body for ``POST /api/locations/{id}/horizons``.

    ``type='artificial'`` requires ``flat_altitude_deg``; ``type='custom'``
    requires ``points`` (≥2). ``source`` defaults to ``'drawn'`` for
    custom horizons created in the editor. Set ``is_default=true`` to
    promote the new row to the location's default (demoting whatever
    was default before).
    """

    name: str = Field(min_length=1, max_length=80)
    type: Literal["artificial", "custom"]
    flat_altitude_deg: float | None = Field(default=None, ge=-5.0, le=90.0)
    points: list[HorizonPointModel] | None = None
    source: Literal["imported", "drawn"] | None = None
    source_filename: str | None = None
    notes: str | None = None
    is_default: bool = False

    @model_validator(mode="after")
    def _validate_shape(self) -> HorizonCreate:
        if self.type == "artificial":
            if self.flat_altitude_deg is None:
                raise ValueError("Artificial horizons require flat_altitude_deg.")
            if self.points:
                raise ValueError("Artificial horizons must not have points.")
            if self.source is not None:
                raise ValueError("Artificial horizons must not have a source.")
        else:  # custom
            if not self.points or len(self.points) < 2:
                raise ValueError("Custom horizons require at least 2 points.")
            if self.flat_altitude_deg is not None:
                raise ValueError("Custom horizons must not set flat_altitude_deg.")
        return self


class HorizonUpdate(BaseModel):
    """Body for ``PATCH /api/locations/{id}/horizons/{hid}``.

    All fields optional — standard PATCH shape. ``points`` replacing
    wholesale is fine for custom horizons; the editor always sends the
    full current polyline. Promoting to default is idempotent (setting
    ``is_default=true`` on an already-default row is a no-op).
    """

    name: str | None = Field(default=None, min_length=1, max_length=80)
    flat_altitude_deg: float | None = Field(default=None, ge=-5.0, le=90.0)
    points: list[HorizonPointModel] | None = None
    notes: str | None = None
    is_default: bool | None = None

    @field_validator("points")
    @classmethod
    def _at_least_two_points(
        cls, v: list[HorizonPointModel] | None
    ) -> list[HorizonPointModel] | None:
        if v is not None and len(v) < 2:
            raise ValueError("A horizon needs at least 2 points.")
        return v


class HorizonResponse(BaseModel):
    """Full horizon representation returned by every CRUD endpoint."""

    id: int
    location_id: int
    name: str
    type: Literal["artificial", "custom"]
    flat_altitude_deg: float | None
    source: Literal["imported", "drawn"] | None
    source_filename: str | None
    notes: str | None
    points: list[HorizonPointModel]
    is_default: bool
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
