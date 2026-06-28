"""Pydantic shapes for the directory-scan ingest pipeline + read-only catalog."""

from __future__ import annotations

from pydantic import BaseModel


class SourceFolder(BaseModel):
    id: int
    project_id: int
    path: str
    is_primary: bool
    added_at: str


class SourceFolderCreate(BaseModel):
    path: str
    is_primary: bool = False


class IngestStatus(BaseModel):
    """Live + durable status of an ingestion run."""

    run_id: int
    project_id: int
    status: str  # running | completed | failed | cancelled
    files_scanned: int = 0
    subs_inserted: int = 0
    subs_updated: int = 0
    subs_skipped: int = 0
    errors_count: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None


class CatalogSummary(BaseModel):
    """Bucketed counts for the read-only catalog view."""

    lights: int = 0
    darks: int = 0
    flats: int = 0
    bias: int = 0
    dark_flats: int = 0
    unknown_frames: int = 0
    processed: int = 0
    pxiprojects: int = 0
    logs: int = 0
    other: int = 0
    sessions: int = 0
    total_files: int = 0


class CatalogFrame(BaseModel):
    """One row in the catalog DataGrid (a sub_frame or processed_image)."""

    id: int
    kind: str  # "sub_frame" | "processed_image"
    frame_type: str | None = None
    path: str | None = None
    filter_name: str | None = None
    object_hint: str | None = None
    exposure_seconds: float | None = None
    gain: float | None = None
    set_temp_c: float | None = None
    binning: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    file_size_bytes: int | None = None
    date_obs_utc: str | None = None
    camera_id: int | None = None
    telescope_id: int | None = None
    accepted: bool | None = None


class CatalogFramesPage(BaseModel):
    rows: list[CatalogFrame]
    total: int
    timezone: str = "UTC"  # IANA tz for displaying date_obs (project location or UTC)


class CatalogMaster(BaseModel):
    """A processed / stacked image (master) row for the Masters tab."""

    id: int
    type_label: str  # e.g. "Master: Dark", "Master"
    frame_type: str | None = None
    filter_name: str | None = None
    ncombine: int | None = None
    total_exposure_seconds: float | None = None
    dimensions: str | None = None  # "6248x4176"
    file_size_bytes: int | None = None
    date_obs_utc: str | None = None
    path: str | None = None


class CatalogMastersPage(BaseModel):
    rows: list[CatalogMaster]
    total: int
    timezone: str = "UTC"


class CatalogOther(BaseModel):
    """A non-frame catalog item for the Others tab (log / pxiproject / other /
    unknown-type sub)."""

    id: int
    kind: str  # "file" | "sub_frame"
    type_label: str  # "PixInsight Project" | "Log" | "Other" | "Unknown frame"
    path: str | None = None
    size_bytes: int | None = None
    date: str | None = None


class CatalogOthersPage(BaseModel):
    rows: list[CatalogOther]
    total: int
    timezone: str = "UTC"


class CatalogFilterStat(BaseModel):
    """Per-filter count + total exposure for the Lights/Flats filter pills."""

    filter_name: str | None = None
    count: int
    total_seconds: float
