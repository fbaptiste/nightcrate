"""Response models for the Home summary endpoint."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from nightcrate.api.project_models import ProjectStatus
from nightcrate.services.gallery import GalleryCrop

ProjectStage = Literal[
    "not_started",
    "capturing",
    "ready_to_process",
    "complete",
    "paused",
    "abandoned",
]


class StageCounts(BaseModel):
    not_started: int = 0
    capturing: int = 0
    ready_to_process: int = 0
    complete: int = 0
    paused: int = 0
    abandoned: int = 0


class HomeIntegrationLine(BaseModel):
    label: str
    minutes: float
    not_recorded: bool = False


class RecentProject(BaseModel):
    project_id: int
    name: str
    status: ProjectStatus
    stage: ProjectStage
    target_label: str | None
    constellation: str | None
    thumbnail_version: str
    has_image: bool
    crops: dict[Literal["small", "medium", "large"], GalleryCrop]
    total_minutes: float
    lines: list[HomeIntegrationLine]
    last_date: date
    nights: int


class LatestPicture(BaseModel):
    project_id: int
    project_name: str
    image_id: int
    added: date
    status: ProjectStatus
    target_label: str | None
    constellation: str | None
    crops: dict[Literal["small", "medium", "large"], GalleryCrop]


class MonthSummary(BaseModel):
    month: str
    minutes: float


class BestNight(BaseModel):
    date: date
    minutes: float
    project_id: int
    project_name: str
    other_projects: int


class YearSummary(BaseModel):
    since: date
    minutes: float
    nights: int
    new_pictures: int
    best_night: BestNight | None
    months: list[MonthSummary]


class RigSummary(BaseModel):
    rig_id: int
    name: str
    minutes: float
    nights: int
    last_used: date | None
    active_projects: int


class LocationSummary(BaseModel):
    location_id: int
    name: str
    is_default: bool
    minutes: float
    nights: int
    last_used: date | None
    active_projects: int


class ForecastLocation(BaseModel):
    location_id: int
    name: str
    note: Literal["default", "used"] | None
    active_projects: int


class HomeSummary(BaseModel):
    today: date
    stages: StageCounts
    total_projects: int
    recent: list[RecentProject]
    latest_picture: LatestPicture | None
    year: YearSummary
    rigs: list[RigSummary]
    locations: list[LocationSummary]
    forecast_locations: list[ForecastLocation]
    workspace_key: str
