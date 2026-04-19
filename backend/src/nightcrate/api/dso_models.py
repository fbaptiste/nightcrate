"""Pydantic models for the DSO catalog API."""

from __future__ import annotations

from pydantic import BaseModel


class DsoDesignation(BaseModel):
    catalog: str
    identifier: str
    display_form: str
    is_primary: bool


class CatalogSource(BaseModel):
    id: int
    source_id: str
    category: str
    display_name: str
    version: str | None
    source_url: str | None
    license: str | None
    attribution: str | None
    loaded_at: str
    row_count: int


class DsoListItem(BaseModel):
    id: int
    primary_designation: str
    obj_type: str
    ra_deg: float | None
    dec_deg: float | None
    constellation: str | None
    maj_axis_arcmin: float | None
    min_axis_arcmin: float | None
    mag_v: float | None
    mag_b: float | None
    common_name: str | None
    # Shortlist: primary + messier + caldwell (see api/dso.py).
    designations: list[DsoDesignation]


class DsoListResponse(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[DsoListItem]


class DsoDetail(BaseModel):
    id: int
    primary_designation: str
    obj_type: str
    raw_obj_type: str | None
    ra_deg: float | None
    dec_deg: float | None
    constellation: str | None
    maj_axis_arcmin: float | None
    min_axis_arcmin: float | None
    position_angle_deg: float | None
    mag_b: float | None
    mag_v: float | None
    mag_j: float | None
    mag_h: float | None
    mag_k: float | None
    surface_brightness: float | None
    hubble_type: str | None
    pm_ra: float | None
    pm_dec: float | None
    redshift: float | None
    radial_velocity: float | None
    cstar_mag_u: float | None
    cstar_mag_b: float | None
    cstar_mag_v: float | None
    cstar_id: str | None
    common_name: str | None
    ned_notes: str | None
    openngc_notes: str | None
    raw_other_id: str | None
    designations: list[DsoDesignation]
    source: CatalogSource
