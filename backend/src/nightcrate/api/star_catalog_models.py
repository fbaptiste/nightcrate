from typing import Literal

from pydantic import BaseModel

from nightcrate.services.star_catalog.fetch import StarOperation
from nightcrate.services.star_catalog.store import InstalledCatalog


class SourceStatus(BaseModel):
    version: str
    download_bytes: int
    unpacked_bytes: int
    doi: str
    licence: str
    gaia_licence: str
    attribution: str


class RigCoverage(BaseModel):
    id: int
    name: str
    field_deg: float


class RangeStatus(BaseModel):
    id: str
    name: str
    recommended: bool
    min_deg: float
    max_deg: float
    state: Literal["not_built", "waiting", "building", "built", "needs_rebuild"]
    progress: float | None = None
    size_bytes: int
    size_is_estimate: bool
    build_memory_bytes: int
    rigs: list[RigCoverage]


class StarCatalogStatus(BaseModel):
    installed: InstalledCatalog | None
    source: SourceStatus
    operation: StarOperation | None
    ranges: list[RangeStatus]
    total_bytes_used: int
    free_bytes: int


class ImportRequest(BaseModel):
    path: str


class BuildRequest(BaseModel):
    range_ids: list[str]
