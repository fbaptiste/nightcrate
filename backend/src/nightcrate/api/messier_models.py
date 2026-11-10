"""Wire models for the Messier checklist endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from nightcrate.services.gallery import GalleryCrop, ImagingRun
from nightcrate.services.messier import PictureField

CropSize = Literal["small", "medium", "large"]


class MessierLocation(BaseModel):
    id: int
    name: str
    latitude_deg: float


class MessierRig(BaseModel):
    id: int
    name: str
    fov_major_deg: float | None
    fov_minor_deg: float | None


class MessierObject(BaseModel):
    dso_id: int
    designation: str
    common_name: str | None
    other_names: list[str]
    obj_type: str
    constellation: str | None
    mag_v: float | None
    maj_axis_arcmin: float | None
    min_axis_arcmin: float | None
    active: bool


class SlotProject(BaseModel):
    project_id: int
    name: str
    status: str
    main_image_id: int | None
    crops: dict[CropSize, GalleryCrop]
    first_date: str | None
    last_date: str | None
    nights: int
    imaging_runs: list[ImagingRun]
    picture_fields: dict[CropSize, PictureField | None] | None


class SurveyImage(BaseModel):
    field_deg: float
    render_key: str


class MessierSlot(BaseModel):
    number: int
    object: MessierObject | None
    state: Literal["imaged", "project", "none", "missing"]
    never_rises: bool
    projects: list[SlotProject]
    survey: SurveyImage | None


class MessierCounts(BaseModel):
    imaged: int
    project: int
    never_rises: int
    missing: int


class MessierResponse(BaseModel):
    catalog_status: Literal["ready", "not_downloaded"]
    location: MessierLocation | None
    rig: MessierRig | None
    counts: MessierCounts
    slots: list[MessierSlot]
    workspace_key: str
