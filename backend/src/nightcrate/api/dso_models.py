"""Pydantic models for the DSO catalog API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DsoDesignation(BaseModel):
    catalog: str
    identifier: str
    display_form: str
    is_primary: bool


class ExternalRef(BaseModel):
    """Link from a DSO to an external knowledge-base or reference entry.

    Wikidata + Wikipedia arrived in v0.20.0; SIMBAD + NED in v0.21.1.
    Wikidata is language-agnostic and stays client-hidden (structured
    data, not a human-readable page). SIMBAD and NED are also
    language-agnostic reference databases.
    """

    provider: Literal["wikidata", "wikipedia", "simbad", "ned"]
    language: str | None = None
    identifier: str
    url: str | None = None
    label: str | None = None


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
    distance_pc: float | None
    distance_method: str | None
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
    distance_pc: float | None
    distance_method: str | None
    common_name: str | None
    common_name_augmented: bool
    surface_brightness_augmented: bool
    ned_notes: str | None
    openngc_notes: str | None
    raw_other_id: str | None
    designations: list[DsoDesignation]
    external_refs: list[ExternalRef]
    source: CatalogSource


class TypeGroupFacet(BaseModel):
    name: str
    display_order: int
    count: int
    raw_types: list[str]


class RawTypeFacet(BaseModel):
    code: str
    count: int


class ConstellationFacet(BaseModel):
    code: str
    count: int


class CatalogFacet(BaseModel):
    code: str
    count: int


class DsoFacetsResponse(BaseModel):
    type_groups: list[TypeGroupFacet]
    raw_types: list[RawTypeFacet]
    constellations: list[ConstellationFacet]
    catalogs: list[CatalogFacet]
