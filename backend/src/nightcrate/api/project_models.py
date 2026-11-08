"""Pydantic request/response models for /api/projects/* endpoints."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ProjectStatus = Literal["active", "paused", "complete", "abandoned"]

# ── Requests ────────────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    notes: str | None = None
    status: ProjectStatus = "active"


class AddImagesRequest(BaseModel):
    file_paths: list[str]


class ThumbnailCropDef(BaseModel):
    source_image_id: int | None = Field(default=None, gt=0)
    crop_x: float = Field(allow_inf_nan=False)
    crop_y: float = Field(allow_inf_nan=False)
    crop_w: float = Field(gt=0, allow_inf_nan=False)
    crop_h: float = Field(gt=0, allow_inf_nan=False)

    @field_validator("crop_x", "crop_y", "crop_w", "crop_h", mode="before")
    @classmethod
    def make_nonfinite_input_json_safe(cls, value):
        if isinstance(value, float) and not math.isfinite(value):
            return "non-finite"
        return value

    @model_validator(mode="after")
    def frame_overlaps_picture(self) -> ThumbnailCropDef:
        if not (
            self.crop_x < 1
            and self.crop_x + self.crop_w > 0
            and self.crop_y < 1
            and self.crop_y + self.crop_h > 0
        ):
            raise ValueError("The frame must include part of the picture.")
        return self


class ProjectUpdate(BaseModel):
    """Partial metadata update (save-as-you-go). Only the fields present in
    the request body are changed; absent fields are left untouched. Empty
    strings for description/notes clear them; null location_id clears it."""

    name: str | None = None
    description: str | None = None
    notes: str | None = None
    status: ProjectStatus | None = None
    location_id: int | None = None


class ProjectRigsSet(BaseModel):
    """Replace the full set of rigs associated with a project."""

    rig_ids: list[int]


class ImageNotesUpdate(BaseModel):
    notes: str | None = None


class ReorderImagesRequest(BaseModel):
    image_ids: list[int]


class ThumbnailCropsRequest(BaseModel):
    crops: dict[str, ThumbnailCropDef]


# ── Responses ───────────────────────────────────────────────────────────────


class ProjectImageResponse(BaseModel):
    id: int
    project_id: int
    file_path: str
    display_order: int
    is_main: bool
    notes: str | None
    created_at: str
    updated_at: str


class ThumbnailCropResponse(BaseModel):
    size: str
    source_image_id: int | None
    crop_x: float
    crop_y: float
    crop_w: float
    crop_h: float


class ProjectRigRef(BaseModel):
    id: int
    name: str


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None
    notes: str | None
    status: str
    active: bool
    location_id: int | None
    location_name: str | None
    rigs: list[ProjectRigRef]
    images: list[ProjectImageResponse]
    thumbnail_crops: list[ThumbnailCropResponse]
    solved_at: str | None
    workspace_key: str
    created_at: str
    updated_at: str


class ProjectListItem(BaseModel):
    id: int
    name: str
    description: str | None
    status: str
    active: bool
    image_count: int
    main_image_path: str | None
    thumbnail_version: str
    workspace_key: str
    created_at: str
    updated_at: str
