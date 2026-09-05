"""Pydantic shapes for the directory-scan ingest pipeline + catalog."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from nightcrate.services.ingest_classify import FRAME_TYPES

# Derived from the single vocabulary in services/ingest_classify.py rather than
# restated, so the two cannot drift. A test still pins both to the
# sub_frame.frame_type CHECK constraint (migration 0037).
FrameTypeName = Literal[*FRAME_TYPES]


class SourceFolder(BaseModel):
    id: int
    project_id: int
    path: str
    is_primary: bool
    rig_id: int | None = None
    """Which rig shot the frames under this folder. **User-declared, never inferred**
    — it is the one equipment fact the ingest records. Frames inherit it, sessions key
    on it so a simultaneous dual-rig night splits, and calibration matching scopes on
    it. NULL means "not stated", which is a valid answer."""
    rig_name: str | None = None
    added_at: str


class SourceFolderCreate(BaseModel):
    path: str
    is_primary: bool = False
    rig_id: int | None = None


class SourceFolderUpdate(BaseModel):
    """Partial update. Only ``rig_id`` is editable; an explicit null clears it."""

    rig_id: int | None = None


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
    """One row in the catalog card list (a sub_frame or processed_image)."""

    id: int
    kind: str  # "sub_frame" | "processed_image"
    frame_type: str | None = None
    path: str | None = None
    filter_name: str | None = None  # the FITS FILTER header value
    object_hint: str | None = None
    exposure_seconds: float | None = None
    gain: float | None = None
    set_temp_c: float | None = None
    binning: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    file_size_bytes: int | None = None
    date_obs_utc: str | None = None
    accepted: bool | None = None
    # The rig the user tagged on this frame's source folder (v0.41.1). NULL is a
    # valid answer — "not stated" — and renders as no chip rather than a blank one.
    rig_name: str | None = None
    # Classification (v0.41.1) — hand-correctable, guarded by a source flag.
    project_target_id: int | None = None
    target_name: str | None = None  # resolved DSO designation for display
    frame_type_source: str | None = None
    project_target_source: str | None = None


CorrectableField = Literal["frame_type", "project_target_id"]


class FrameCorrection(BaseModel):
    """Per-frame manual classification correction (v0.41.1).

    A field present in the body is applied verbatim (explicit ``null`` = "none")
    and its ``*_source`` flips to ``'user'``, so the ingest passes that re-derive
    these values on every scan leave them alone. ``reset_to_auto`` hands a field
    back to the pipeline.
    """

    frame_type: FrameTypeName | None = None
    project_target_id: int | None = None
    reset_to_auto: list[CorrectableField] = []


class BulkFrameCorrection(FrameCorrection):
    """A :class:`FrameCorrection` applied to several frames in one transaction."""

    frame_ids: list[int] = Field(min_length=1)


class BulkCorrectionResult(BaseModel):
    updated: int


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
