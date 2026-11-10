"""Pure filtering, facet counting, and sorting for the project gallery."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from functools import cmp_to_key
from typing import Literal

from pydantic import BaseModel, Field

from nightcrate.services.dso_sorting import catalog_rank
from nightcrate.services.dso_type_groups import TYPE_GROUPS

_SESSION_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STATUS_ORDER = ("active", "paused", "complete", "abandoned")


def valid_session_date(text: str | None) -> date | None:
    """Return the leading ISO calendar date, ignoring invalid free text."""
    if text is None or len(text) < 10 or _SESSION_DATE_RE.fullmatch(text[:10]) is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


class ImagingRun(BaseModel):
    start: str
    end: str


def imaging_runs(dates: list[date]) -> list[ImagingRun]:
    """Merge the represented calendar months into consecutive runs."""
    months = sorted({(value.year, value.month) for value in dates})
    if not months:
        return []

    runs: list[ImagingRun] = []
    start = previous = months[0]
    for current in months[1:]:
        previous_index = previous[0] * 12 + previous[1]
        current_index = current[0] * 12 + current[1]
        if current_index != previous_index + 1:
            runs.append(ImagingRun(start=_month_text(start), end=_month_text(previous)))
            start = current
        previous = current
    runs.append(ImagingRun(start=_month_text(start), end=_month_text(previous)))
    return runs


def _month_text(month: tuple[int, int]) -> str:
    return f"{month[0]:04d}-{month[1]:02d}"


class GalleryTarget(BaseModel):
    dso_id: int
    name: str
    also_known_as: list[str] = Field(default_factory=list)


class GalleryRig(BaseModel):
    id: int
    name: str


class GalleryCrop(BaseModel):
    id: int
    image_id: int


class TargetFacts(BaseModel):
    target: GalleryTarget
    catalogs: frozenset[str] = Field(default_factory=frozenset)
    type_group: str
    constellation: str | None = None


class ProjectRecord(BaseModel):
    id: int
    name: str
    status: str
    created_at: str = ""
    retired: bool = False
    main_image_id: int | None = None
    crops: dict[Literal["small", "medium", "large"], GalleryCrop] = Field(default_factory=dict)
    targets: list[TargetFacts] = Field(default_factory=list)
    dates: list[date] = Field(default_factory=list)
    rigs: list[GalleryRig] = Field(default_factory=list)
    integration_minutes: float = 0.0


class GalleryQuery(BaseModel):
    q: str | None = None
    catalogs: list[str] = Field(default_factory=list)
    type_groups: list[str] = Field(default_factory=list)
    constellations: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    rig_ids: list[int] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    include_undated: bool = False
    include_retired: bool = False
    search_images: bool = False
    sort: Literal["latest", "first", "name"] = "latest"
    desc: bool = True


class GalleryItem(BaseModel):
    project_id: int
    name: str
    status: str
    retired: bool
    main_image_id: int | None
    crops: dict[Literal["small", "medium", "large"], GalleryCrop] = Field(default_factory=dict)
    targets: list[GalleryTarget]
    first_date: str | None
    last_date: str | None
    nights: int
    imaging_runs: list[ImagingRun]
    integration_minutes: float
    rigs: list[GalleryRig]
    found_in_image: list[str]


class FacetCount(BaseModel):
    code: str
    count: int


class RigFacetCount(BaseModel):
    id: int
    name: str
    count: int


class GalleryFacets(BaseModel):
    catalogs: list[FacetCount]
    type_groups: list[FacetCount]
    constellations: list[FacetCount]
    statuses: list[FacetCount]
    rigs: list[RigFacetCount]


class GalleryResult(BaseModel):
    items: list[GalleryItem]
    facets: GalleryFacets
    library_total: int


def _matches_search(
    record: ProjectRecord,
    query: GalleryQuery,
    target_search_hits: set[int] | None,
    image_search_hits: dict[int, list[str]] | None,
) -> bool:
    if not query.q or not query.q.strip():
        return True
    needle = query.q.strip().casefold()
    return (
        needle in record.name.casefold()
        or record.id in (target_search_hits or set())
        or (query.search_images and record.id in (image_search_hits or {}))
    )


def _matches_filters(record: ProjectRecord, query: GalleryQuery, *, exclude: str | None) -> bool:
    if not query.include_retired and record.retired:
        return False
    if exclude != "catalogs" and query.catalogs:
        selected = set(query.catalogs)
        if not any(facts.catalogs & selected for facts in record.targets):
            return False
    if exclude != "type_groups" and query.type_groups:
        selected = set(query.type_groups)
        if not any(facts.type_group in selected for facts in record.targets):
            return False
    if exclude != "constellations" and query.constellations:
        selected = set(query.constellations)
        if not any(facts.constellation in selected for facts in record.targets):
            return False
    if exclude != "statuses" and query.statuses and record.status not in query.statuses:
        return False
    if exclude != "rigs" and query.rig_ids:
        selected_rigs = set(query.rig_ids)
        if not any(rig.id in selected_rigs for rig in record.rigs):
            return False
    if query.date_from is not None or query.date_to is not None:
        if not record.dates:
            if not query.include_undated:
                return False
        elif not any(
            (query.date_from is None or value >= query.date_from)
            and (query.date_to is None or value <= query.date_to)
            for value in record.dates
        ):
            return False
    return True


def _facet_counts(
    records: list[ProjectRecord],
    query: GalleryQuery,
    *,
    exclude: str,
    values: Callable[[ProjectRecord], set[str]],
    selected: list[str],
    order: Callable[[str], object],
) -> list[FacetCount]:
    counts: dict[str, int] = {}
    for record in records:
        if not _matches_filters(record, query, exclude=exclude):
            continue
        for value in values(record):
            counts[value] = counts.get(value, 0) + 1
    codes = set(counts) | set(selected)
    return [FacetCount(code=code, count=counts.get(code, 0)) for code in sorted(codes, key=order)]


def _rig_facets(records: list[ProjectRecord], query: GalleryQuery) -> list[RigFacetCount]:
    known: dict[int, tuple[str, int]] = {}
    for record in records:
        for position, rig in enumerate(record.rigs):
            known.setdefault(rig.id, (rig.name, position))

    counts: dict[int, int] = {}
    for record in records:
        if not _matches_filters(record, query, exclude="rigs"):
            continue
        for rig_id in {rig.id for rig in record.rigs}:
            counts[rig_id] = counts.get(rig_id, 0) + 1

    ids = set(counts) | (set(query.rig_ids) & set(known))
    ordered = sorted(
        ids,
        key=lambda rig_id: (known[rig_id][1], known[rig_id][0].casefold(), rig_id),
    )
    return [
        RigFacetCount(id=rig_id, name=known[rig_id][0], count=counts.get(rig_id, 0))
        for rig_id in ordered
    ]


def _compare_records(left: ProjectRecord, right: ProjectRecord, query: GalleryQuery) -> int:
    if query.sort == "name":
        left_primary: object = left.name.casefold()
        right_primary: object = right.name.casefold()
    else:
        left_primary = (
            (left.dates[-1] if query.sort == "latest" else left.dates[0]) if left.dates else None
        )
        right_primary = (
            (right.dates[-1] if query.sort == "latest" else right.dates[0]) if right.dates else None
        )
        if left_primary is None or right_primary is None:
            if left_primary is None and right_primary is not None:
                return 1
            if right_primary is None and left_primary is not None:
                return -1

    if left_primary != right_primary:
        comparison = -1 if left_primary < right_primary else 1
        return -comparison if query.desc else comparison
    left_name = left.name.casefold()
    right_name = right.name.casefold()
    if left_name != right_name:
        return -1 if left_name < right_name else 1
    return (left.id > right.id) - (left.id < right.id)


def build_gallery(
    records: list[ProjectRecord],
    query: GalleryQuery,
    *,
    target_search_hits: set[int] | None,
    image_search_hits: dict[int, list[str]] | None,
) -> GalleryResult:
    """Filter records, compute disjunctive facets, and build gallery cards."""
    searched = [
        record
        for record in records
        if _matches_search(record, query, target_search_hits, image_search_hits)
    ]
    matching = [record for record in searched if _matches_filters(record, query, exclude=None)]
    matching.sort(key=cmp_to_key(lambda left, right: _compare_records(left, right, query)))

    target_hits = target_search_hits or set()
    needle = query.q.strip().casefold() if query.q and query.q.strip() else None
    items = []
    for record in matching:
        dates = sorted(set(record.dates))
        direct_match = needle is not None and (
            needle in record.name.casefold() or record.id in target_hits
        )
        found_in_image = []
        if needle is not None and query.search_images and not direct_match:
            found_in_image = list((image_search_hits or {}).get(record.id, []))
        items.append(
            GalleryItem(
                project_id=record.id,
                name=record.name,
                status=record.status,
                retired=record.retired,
                main_image_id=record.main_image_id,
                crops=record.crops,
                targets=[facts.target for facts in record.targets],
                first_date=dates[0].isoformat() if dates else None,
                last_date=dates[-1].isoformat() if dates else None,
                nights=len(dates),
                imaging_runs=imaging_runs(dates),
                integration_minutes=record.integration_minutes,
                rigs=record.rigs,
                found_in_image=found_in_image,
            )
        )

    catalogs = _facet_counts(
        searched,
        query,
        exclude="catalogs",
        values=lambda record: {code for facts in record.targets for code in facts.catalogs},
        selected=query.catalogs,
        order=lambda code: (catalog_rank(code), code),
    )
    type_order = {group.name: group.display_order for group in TYPE_GROUPS}
    type_groups = _facet_counts(
        searched,
        query,
        exclude="type_groups",
        values=lambda record: {facts.type_group for facts in record.targets},
        selected=query.type_groups,
        order=lambda code: (type_order.get(code, len(TYPE_GROUPS) + 1), code),
    )
    constellations = _facet_counts(
        searched,
        query,
        exclude="constellations",
        values=lambda record: {
            facts.constellation for facts in record.targets if facts.constellation is not None
        },
        selected=query.constellations,
        order=lambda code: code,
    )
    status_order = {status: index for index, status in enumerate(_STATUS_ORDER)}
    statuses = _facet_counts(
        searched,
        query,
        exclude="statuses",
        values=lambda record: {record.status},
        selected=query.statuses,
        order=lambda code: (status_order.get(code, len(_STATUS_ORDER)), code),
    )
    return GalleryResult(
        items=items,
        facets=GalleryFacets(
            catalogs=catalogs,
            type_groups=type_groups,
            constellations=constellations,
            statuses=statuses,
            rigs=_rig_facets(searched, query),
        ),
        library_total=len(records),
    )
