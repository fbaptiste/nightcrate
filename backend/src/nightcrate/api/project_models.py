"""Pydantic request/response models for /api/projects/* endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── Requests ────────────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    notes: str | None = None
    status: str = "active"


class AddImagesRequest(BaseModel):
    file_paths: list[str]


class ThumbnailCropDef(BaseModel):
    source_image_id: int | None = None
    crop_x: float = Field(default=0, ge=0, le=1)
    crop_y: float = Field(default=0, ge=0, le=1)
    crop_w: float = Field(default=1, gt=0, le=1)
    crop_h: float = Field(default=1, gt=0, le=1)


class ProjectUpdate(BaseModel):
    """Partial metadata update (save-as-you-go). Only the fields present in
    the request body are changed; absent fields are left untouched. Empty
    strings for description/notes clear them."""

    name: str | None = None
    description: str | None = None
    notes: str | None = None
    status: str | None = None


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


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None
    notes: str | None
    status: str
    active: bool
    images: list[ProjectImageResponse]
    thumbnail_crops: list[ThumbnailCropResponse]
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
    created_at: str
    updated_at: str
