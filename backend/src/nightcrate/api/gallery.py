"""Project gallery endpoint and batched database loading."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from nightcrate.api._common import load_designations, load_other_names
from nightcrate.api.dso import dso_search_clause
from nightcrate.core.app_config import get_projects_root
from nightcrate.db.session import get_db, workspace_key
from nightcrate.services.dso_sorting import designation_sort_key
from nightcrate.services.dso_type_groups import group_for_raw_type
from nightcrate.services.gallery import (
    GalleryCrop,
    GalleryQuery,
    GalleryResult,
    GalleryRig,
    GalleryTarget,
    ProjectRecord,
    TargetFacts,
    build_gallery,
    valid_session_date,
)
from nightcrate.services.project_images import crop_path

router = APIRouter(prefix="/api/gallery", tags=["Projects"])


class GalleryResponse(GalleryResult):
    workspace_key: str


def _csv_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return list(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))


def _parse_date(value: str | None, label: str) -> date | None:
    if value is None or not value.strip():
        return None
    parsed = valid_session_date(value)
    if parsed is None or len(value) != 10:
        raise HTTPException(status_code=422, detail=f"Invalid {label} date")
    return parsed


def _parse_rigs(value: str | None) -> list[int]:
    rigs: list[int] = []
    for part in _csv_values(value):
        try:
            rig_id = int(part)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid rig id: {part}") from exc
        if rig_id not in rigs:
            rigs.append(rig_id)
    return rigs


def _alternate_names(name: str, designations: list, other_names: list[str]) -> list[str]:
    result: list[str] = []
    seen = {name.casefold()}
    for value in [*(designation.display_form for designation in designations), *other_names]:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


async def load_project_records(conn) -> list[ProjectRecord]:
    project_cursor = await conn.execute(
        """
        SELECT p.id, p.name, p.status, p.active, p.created_at,
               pi.id AS main_image_id
        FROM project p
        LEFT JOIN project_image pi
          ON pi.project_id = p.id AND pi.is_main = 1
        ORDER BY p.id
        """
    )
    project_rows = await project_cursor.fetchall()
    crops_by_project: dict[int, dict[Literal["small", "medium", "large"], GalleryCrop]] = (
        defaultdict(dict)
    )
    crop_cursor = await conn.execute(
        """
        SELECT pt.id, pt.project_id, pt.size,
               COALESCE(pt.source_image_id, main.id) AS image_id
        FROM project_thumbnail pt
        LEFT JOIN project_image main
          ON main.project_id = pt.project_id AND main.is_main = 1
        ORDER BY pt.project_id, pt.id
        """
    )
    projects_root = get_projects_root()
    if projects_root is not None:
        for row in await crop_cursor.fetchall():
            image_id = row["image_id"]
            if image_id is None:
                continue
            project_id = int(row["project_id"])
            size = row["size"]
            if not crop_path(projects_root / str(project_id), size, int(row["id"])).is_file():
                continue
            crops_by_project[project_id][size] = GalleryCrop(
                id=int(row["id"]), image_id=int(image_id)
            )
    targets_by_project: dict[int, list] = defaultdict(list)
    target_cursor = await conn.execute(
        """
        SELECT pt.project_id, pt.dso_id, d.primary_designation, d.common_name,
               d.obj_type, d.constellation
        FROM project_target pt
        JOIN dso d ON d.id = pt.dso_id
        ORDER BY pt.project_id, pt.created_at, pt.id
        """
    )
    target_rows = await target_cursor.fetchall()
    dso_ids = list(dict.fromkeys(int(row["dso_id"]) for row in target_rows))
    designations = await load_designations(conn, dso_ids)
    other_names = await load_other_names(conn, dso_ids)

    group_catalogs: dict[int, set[str]] = defaultdict(set)
    group_cursor = await conn.execute(
        """
        SELECT DISTINCT pt.dso_id, g.catalog
        FROM project_target pt
        JOIN dso_group_member gm ON gm.dso_id = pt.dso_id
        JOIN dso_group g ON g.id = gm.group_id
        """
    )
    for row in await group_cursor.fetchall():
        group_catalogs[int(row["dso_id"])].add(str(row["catalog"]))

    for row in target_rows:
        dso_id = int(row["dso_id"])
        dso_designations = designations.get(dso_id, [])
        preferred_name = row["common_name"] or row["primary_designation"]
        catalogs = {designation.catalog for designation in dso_designations}
        catalogs.update(group_catalogs.get(dso_id, set()))
        targets_by_project[int(row["project_id"])].append(
            TargetFacts(
                target=GalleryTarget(
                    dso_id=dso_id,
                    name=preferred_name,
                    also_known_as=_alternate_names(
                        preferred_name,
                        dso_designations,
                        other_names.get(dso_id, []),
                    ),
                ),
                catalogs=frozenset(catalogs),
                type_group=group_for_raw_type(row["obj_type"]),
                constellation=row["constellation"],
            )
        )

    rigs_by_project: dict[int, list[GalleryRig]] = defaultdict(list)
    rig_cursor = await conn.execute(
        """
        SELECT project_id, id, name, sort_order
        FROM (
            SELECT pr.project_id, r.id, r.name, r.sort_order
            FROM project_rig pr
            JOIN rig r ON r.id = pr.rig_id
            UNION
            SELECT ps.project_id, r.id, r.name, r.sort_order
            FROM project_session ps
            JOIN rig r ON r.id = ps.rig_id
        )
        ORDER BY project_id, sort_order, name COLLATE NOCASE, id
        """
    )
    for row in await rig_cursor.fetchall():
        rigs_by_project[int(row["project_id"])].append(
            GalleryRig(id=int(row["id"]), name=row["name"])
        )

    dates_by_project: dict[int, set[date]] = defaultdict(set)
    date_cursor = await conn.execute(
        "SELECT project_id, session_date FROM project_session ORDER BY project_id, id"
    )
    for row in await date_cursor.fetchall():
        parsed = valid_session_date(row["session_date"])
        if parsed is not None:
            dates_by_project[int(row["project_id"])].add(parsed)

    integrations: dict[int, float] = {}
    integration_cursor = await conn.execute(
        """
        SELECT project_id, SUM(exposure_seconds * num_subs) / 60.0 AS minutes
        FROM project_session
        GROUP BY project_id
        """
    )
    for row in await integration_cursor.fetchall():
        integrations[int(row["project_id"])] = float(row["minutes"])

    return [
        ProjectRecord(
            id=int(row["id"]),
            name=row["name"],
            status=row["status"],
            created_at=row["created_at"],
            retired=not bool(row["active"]),
            main_image_id=row["main_image_id"],
            crops=crops_by_project.get(int(row["id"]), {}),
            targets=targets_by_project.get(int(row["id"]), []),
            dates=sorted(dates_by_project.get(int(row["id"]), set())),
            rigs=rigs_by_project.get(int(row["id"]), []),
            integration_minutes=integrations.get(int(row["id"]), 0.0),
        )
        for row in project_rows
    ]


async def _search_targets(conn, q: str | None) -> set[int] | None:
    if q is None:
        return None
    clause, params = dso_search_clause(q)
    cursor = await conn.execute(
        f"""
        SELECT DISTINCT pt.project_id
        FROM project_target pt
        JOIN dso d ON d.id = pt.dso_id
        WHERE {clause}
        """,  # noqa: S608  # nosec B608 - shared static SQL fragment
        params,
    )
    return {int(row["project_id"]) for row in await cursor.fetchall()}


async def _search_images(
    conn, q: str | None, records: list[ProjectRecord], enabled: bool
) -> dict[int, list[str]] | None:
    if q is None or not enabled:
        return None
    await conn.create_function("designation_key", 1, designation_sort_key, deterministic=True)
    clause, params = dso_search_clause(q)
    cursor = await conn.execute(
        f"""
        SELECT DISTINCT ps.project_id, d.id AS dso_id,
               d.primary_designation, d.common_name
        FROM project_solve ps
        JOIN project_dso pd ON pd.solve_id = ps.id
        JOIN dso d ON d.id = pd.dso_id
        WHERE {clause}
        ORDER BY ps.project_id, designation_key(d.primary_designation), d.id
        """,  # noqa: S608  # nosec B608 - shared static SQL fragment
        params,
    )
    target_ids = {
        record.id: {facts.target.dso_id for facts in record.targets} for record in records
    }
    hits: dict[int, list[str]] = defaultdict(list)
    seen: dict[int, set[str]] = defaultdict(set)
    for row in await cursor.fetchall():
        project_id = int(row["project_id"])
        if int(row["dso_id"]) in target_ids.get(project_id, set()):
            continue
        name = row["common_name"] or row["primary_designation"]
        key = name.casefold()
        if key not in seen[project_id]:
            seen[project_id].add(key)
            hits[project_id].append(name)
    return dict(hits)


@router.get("", response_model=GalleryResponse)
async def get_gallery(
    q: str | None = None,
    catalog: str | None = None,
    type_group: str | None = None,
    constellation: str | None = None,
    status: str | None = None,
    rig: str | None = None,
    imaged_from: str | None = None,
    imaged_to: str | None = None,
    include_undated: bool = False,
    include_retired: bool = False,
    sort: Literal["latest", "first", "name"] = "latest",
    desc: bool = True,
    search_images: bool = Query(False),
) -> GalleryResponse:
    date_from = _parse_date(imaged_from, "from")
    date_to = _parse_date(imaged_to, "to")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=422, detail="From is after To")

    normalized_q = q.strip() if q and q.strip() else None
    query = GalleryQuery(
        q=normalized_q,
        catalogs=_csv_values(catalog),
        type_groups=_csv_values(type_group),
        constellations=_csv_values(constellation),
        statuses=_csv_values(status),
        rig_ids=_parse_rigs(rig),
        date_from=date_from,
        date_to=date_to,
        include_undated=include_undated,
        include_retired=include_retired,
        search_images=search_images,
        sort=sort,
        desc=desc,
    )
    async with get_db() as conn:
        records = await load_project_records(conn)
        target_hits = await _search_targets(conn, normalized_q)
        image_hits = await _search_images(conn, normalized_q, records, search_images)
    result = build_gallery(
        records,
        query,
        target_search_hits=target_hits,
        image_search_hits=image_hits,
    )
    return GalleryResponse(**result.model_dump(), workspace_key=workspace_key())
