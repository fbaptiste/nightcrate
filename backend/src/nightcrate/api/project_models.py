"""Pydantic request/response models for /api/projects/* endpoints."""

from __future__ import annotations

from pydantic import BaseModel

# ── Requests ────────────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    notes: str | None = None
    status: str = "active"


class AddImagesRequest(BaseModel):
    file_paths: list[str]


class ProjectSaveRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    notes: str | None = None
    status: str | None = None
    clear_description: bool = False
    clear_notes: bool = False
    remove_image_ids: list[int] | None = None
    image_order: list[int] | None = None
    main_image_id: int | None = None
    image_notes: dict[str, str | None] | None = None


# ── Responses ───────────────────────────────────────────────────────────────


class ProjectImageResponse(BaseModel):
    id: int
    project_id: int
    file_path: str
    display_order: int
    is_main: bool
    staged: bool
    notes: str | None
    created_at: str
    updated_at: str


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None
    notes: str | None
    status: str
    active: bool
    images: list[ProjectImageResponse]
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
