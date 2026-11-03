"""Response models for app-wide optional DSO catalogs."""

from typing import Literal

from pydantic import BaseModel


class OptionalCatalogStatus(BaseModel):
    catalog_id: str
    display_name: str
    credit: str
    kind: Literal["vizier", "nightcrate"]
    state: Literal["on", "off", "removed"]
    installed: bool
    version: str | None
    object_count: int


class RemovalPreview(BaseModel):
    objects_removed: int
    objects_kept: int
    blocked_reason: str | None
