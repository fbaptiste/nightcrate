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


class HorizonReplaceItem(BaseModel):
    """One row in the atomic replace-horizons payload.

    Same shape as ``HorizonCreate`` but with an optional ``id`` field.
    ``id`` is populated for rows the caller wants to UPDATE (must be an
    existing horizon on this location); omitted / ``None`` for rows to
    INSERT. The server rejects any id that doesn't belong to the
    target location.
    """

    id: int | None = None
    name: str = Field(min_length=1, max_length=80)
    type: Literal["artificial", "custom"]
    flat_altitude_deg: float | None = Field(default=None, ge=-5.0, le=90.0)
    points: list[HorizonPointModel] | None = None
    source: Literal["imported", "drawn"] | None = None
    source_filename: str | None = None
    notes: str | None = None
    is_default: bool = False

    @model_validator(mode="after")
    def _validate_shape(self) -> HorizonReplaceItem:
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


class LocationHorizonsReplace(BaseModel):
    """Body for ``PUT /api/locations/{id}/horizons`` (atomic replace).

    The caller sends the full desired horizon set for the location; the
    server applies creates / updates / deletes in a single SQL
    transaction so partial failures can't leak. Invariants (exactly-one-
    default, ≤1 custom, unique names, ≥1 total) are validated both in
    Pydantic (422 on malformed) and on commit.

    Used by the Location editor's staged-save flow so "Cancel discards
    everything, Save commits everything" holds even across mid-flight
    network failures.
    """

    horizons: list[HorizonReplaceItem]

    @model_validator(mode="after")
    def _validate_set(self) -> LocationHorizonsReplace:
        if not self.horizons:
            raise ValueError(
                "horizons: at least one horizon is required — a location "
                "without a horizon violates the every-location-has-≥1 invariant"
            )
        default_count = sum(1 for h in self.horizons if h.is_default)
        if default_count != 1:
            raise ValueError(
                f"horizons: exactly one entry must have is_default=true (got {default_count})"
            )
        custom_count = sum(1 for h in self.horizons if h.type == "custom")
        if custom_count > 1:
            raise ValueError("horizons: at most one 'custom' horizon per location")
        names = [h.name for h in self.horizons]
        if len(names) != len(set(names)):
            raise ValueError("horizons: names must be unique within the list")
        # ids supplied must be unique across the payload (repeats would
        # mean the caller is trying to apply two different states to the
        # same row).
        ids = [h.id for h in self.horizons if h.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("horizons: ids must be unique within the list")
        return self
