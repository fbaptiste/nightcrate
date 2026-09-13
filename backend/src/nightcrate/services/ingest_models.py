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
    project_target_id: int | None = None
    """Which target this folder holds. **User-declared, never inferred** (v0.41.3).
    NULL falls back to the project's single target, which is what every frame got
    before folders could say. The OBJECT header stays a hint and is not used."""
    target_name: str | None = None
    added_at: str


class SourceFolderCreate(BaseModel):
    path: str
    is_primary: bool = False
    rig_id: int | None = None
    project_target_id: int | None = None


class SourceFolderUpdate(BaseModel):
    """Partial update of the folder's declared facts.

    ``rig_id`` and ``project_target_id`` are the editable ones; a field absent
    from the body is left alone, an explicit null clears it. That distinction is
    read off ``model_fields_set``, not off the value.
    """

    rig_id: int | None = None
    project_target_id: int | None = None


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
    # Quality metrics (v0.41.3). All NULL until the analyze pass has run over this
    # frame. hfr / star_count / snr_estimate stay NULL on calibration frames even
    # after a successful run — only lights carry stars. See services/frame_quality.py
    # for the definitions; hfr is in PIXELS and only comparable within a rig.
    hfr: float | None = None
    star_count: int | None = None
    median_adu: float | None = None
    background_adu: float | None = None
    snr_estimate: float | None = None
    quality_status: str | None = None  # ok | no_stars | unreadable
    quality_analyzed_at: str | None = None
    # Derived on read, never stored (v0.41.3). The frame's plate-solved scale if
    # it has one, else computed from the tagged rig's focal length and sensor
    # pitch (times binning). NULL when the rig is untagged or its equipment record
    # is incomplete — the UI then shows HFR in pixels rather than guessing.
    pixel_scale_arcsec: float | None = None
    # hfr x pixel_scale_arcsec. The angular figure is the comparable one: the same
    # seeing reads ~6 px at 1960 mm and ~2 px at 600 mm.
    hfr_arcsec: float | None = None
    # Saturation point of the frame's camera (2^ADC - 1), from the tagged rig.
    # An ADU reading can't be judged without it: 30,000 is about half scale on a
    # 16-bit body and impossible on a 12-bit one. NULL when the rig is untagged.
    full_scale_adu: int | None = None


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


class QualityPending(BaseModel):
    """The frames still awaiting quality analysis, in the requested scope.

    The whole ordered id list, not a page: the client slices it into batches
    itself, which makes progress exact and avoids re-querying a moving target
    between batches. 2,664 ints is about 20 KB of JSON.
    """

    frame_ids: list[int]
    total: int  # frames in scope overall (analyzed + pending), for the progress bar


class QualityCounts(BaseModel):
    """Analyze-state of the frames in one catalog scope, for the button labels."""

    total: int = 0
    analyzed: int = 0  # includes unreadable — they were attempted
    pending: int = 0  # never attempted
    unreadable: int = 0


class QualityAnalyzeRequest(BaseModel):
    """One batch of the client-driven analyze run."""

    frame_ids: list[int] = Field(min_length=1, max_length=500)
    force: bool = False  # recompute even if already analyzed


class QualityAnalyzeResult(BaseModel):
    analyzed: int = 0
    no_stars: int = 0
    unreadable: int = 0
    skipped: int = 0  # already analyzed and force was not set
    errors: list[str] = []


class CatalogDeleteRequest(BaseModel):
    """Items to drop from the catalog. At least one list must be non-empty.

    Three typed lists rather than one id list plus a discriminator, because the
    three tables are genuinely different rows — a sub frame owns its file
    locations, a plain file IS a file location.
    """

    sub_frame_ids: list[int] = []
    processed_image_ids: list[int] = []
    file_ids: list[int] = []


class CatalogDeleteResult(BaseModel):
    sub_frames: int = 0
    processed_images: int = 0
    files: int = 0


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
