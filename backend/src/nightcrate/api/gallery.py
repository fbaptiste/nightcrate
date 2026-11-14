"""Project gallery endpoint and batched database loading."""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from nightcrate.api._common import load_designations
from nightcrate.api.dso import dso_search_clause
from nightcrate.api.object_facts_db import load_other_distances, load_target_facts
from nightcrate.api.object_search_db import load_solves
from nightcrate.catalog_loader.designations import (
    designation_search_prefixes,
    normalize_designation,
)
from nightcrate.core.app_config import get_projects_root
from nightcrate.db.session import get_db, workspace_key
from nightcrate.services.dso_sorting import designation_sort_key
from nightcrate.services.dso_type_groups import group_for_raw_type
from nightcrate.services.gallery import (
    GalleryCrop,
    GalleryMark,
    GalleryQuery,
    GalleryResult,
    GalleryRig,
    GallerySolveMarks,
    ProjectRecord,
    SearchObject,
    build_gallery,
    valid_session_date,
)
from nightcrate.services.object_search import SolveGeometry, marks_in_solve
from nightcrate.services.project_images import crop_path

router = APIRouter(prefix="/api/gallery", tags=["Projects"])


class GalleryResponse(GalleryResult):
    workspace_key: str
    search_object: SearchObject | None = None


class GallerySuggestion(BaseModel):
    dso_id: int
    designation: str
    detail: str | None = None
    project_count: int


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


_ID_QUERY_BATCH_SIZE = 500


def _project_batches(project_ids: list[int] | None) -> list[list[int] | None]:
    if project_ids is None:
        return [None]
    unique_ids = list(dict.fromkeys(project_ids))
    return [
        unique_ids[start : start + _ID_QUERY_BATCH_SIZE]
        for start in range(0, len(unique_ids), _ID_QUERY_BATCH_SIZE)
    ]


def _project_where(column: str, batch: list[int] | None) -> tuple[str, list[int]]:
    if batch is None:
        return "", []
    placeholders = ",".join("?" * len(batch))
    return f"WHERE {column} IN ({placeholders})", batch


async def load_project_records(
    conn,
    *,
    project_ids: list[int] | None = None,
    with_object_facts: bool = False,
) -> list[ProjectRecord]:
    """Load project Gallery inputs, optionally including solve-object facts."""
    if project_ids == []:
        return []
    batches = _project_batches(project_ids)

    project_rows = []
    for batch in batches:
        where, params = _project_where("p.id", batch)
        cursor = await conn.execute(
            f"""
            SELECT p.id, p.name, p.status, p.active, p.created_at,
                   pi.id AS main_image_id,
                   EXISTS (
                       SELECT 1 FROM project_solve ps WHERE ps.project_id = p.id
                   ) AS has_solve
            FROM project p
            LEFT JOIN project_image pi
              ON pi.project_id = p.id AND pi.is_main = 1
            {where}
            ORDER BY p.id
            """,  # noqa: S608  # nosec B608 - placeholders built only from ?
            params,
        )
        project_rows.extend(await cursor.fetchall())
    project_rows.sort(key=lambda row: int(row["id"]))

    crops_by_project: dict[int, dict[Literal["small", "medium", "large"], GalleryCrop]] = (
        defaultdict(dict)
    )
    projects_root = get_projects_root()
    for batch in batches:
        where, params = _project_where("pt.project_id", batch)
        cursor = await conn.execute(
            f"""
            SELECT pt.id, pt.project_id, pt.size,
                   COALESCE(pt.source_image_id, main.id) AS image_id
            FROM project_thumbnail pt
            LEFT JOIN project_image main
              ON main.project_id = pt.project_id AND main.is_main = 1
            {where}
            ORDER BY pt.project_id, pt.id
            """,  # noqa: S608  # nosec B608 - placeholders built only from ?
            params,
        )
        for row in await cursor.fetchall():
            image_id = row["image_id"]
            if image_id is None or projects_root is None:
                continue
            project_id = int(row["project_id"])
            size = row["size"]
            if not crop_path(projects_root / str(project_id), size, int(row["id"])).is_file():
                continue
            crops_by_project[project_id][size] = GalleryCrop(
                id=int(row["id"]), image_id=int(image_id)
            )

    loaded_targets = await load_target_facts(
        conn,
        project_ids,
        with_facts=with_object_facts,
    )

    rigs_by_project: dict[int, list[GalleryRig]] = defaultdict(list)
    for batch in batches:
        where, params = _project_where("project_id", batch)
        cursor = await conn.execute(
            f"""
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
            {where}
            ORDER BY project_id, sort_order, name COLLATE NOCASE, id
            """,  # noqa: S608  # nosec B608 - placeholders built only from ?
            params,
        )
        for row in await cursor.fetchall():
            rigs_by_project[int(row["project_id"])].append(
                GalleryRig(id=int(row["id"]), name=row["name"])
            )

    dates_by_project: dict[int, set[date]] = defaultdict(set)
    for batch in batches:
        where, params = _project_where("project_id", batch)
        cursor = await conn.execute(
            f"""
            SELECT project_id, session_date
            FROM project_session
            {where}
            ORDER BY project_id, id
            """,  # noqa: S608  # nosec B608 - placeholders built only from ?
            params,
        )
        for row in await cursor.fetchall():
            parsed = valid_session_date(row["session_date"])
            if parsed is not None:
                dates_by_project[int(row["project_id"])].add(parsed)

    integrations: dict[int, float] = {}
    for batch in batches:
        where, params = _project_where("project_id", batch)
        cursor = await conn.execute(
            f"""
            SELECT project_id, SUM(exposure_seconds * num_subs) / 60.0 AS minutes
            FROM project_session
            {where}
            GROUP BY project_id
            """,  # noqa: S608  # nosec B608 - placeholders built only from ?
            params,
        )
        for row in await cursor.fetchall():
            integrations[int(row["project_id"])] = float(row["minutes"])

    other_distances = await load_other_distances(conn, project_ids) if with_object_facts else {}
    return [
        ProjectRecord(
            id=int(row["id"]),
            name=row["name"],
            status=row["status"],
            created_at=row["created_at"],
            retired=not bool(row["active"]),
            main_image_id=row["main_image_id"],
            crops=crops_by_project.get(int(row["id"]), {}),
            targets=loaded_targets.get(int(row["id"]), []),
            dates=sorted(dates_by_project.get(int(row["id"]), set())),
            rigs=rigs_by_project.get(int(row["id"]), []),
            integration_minutes=integrations.get(int(row["id"]), 0.0),
            has_solve=bool(row["has_solve"]),
            other_distances=other_distances.get(int(row["id"]), []),
        )
        for row in project_rows
    ]


async def _search_targets(conn, q: str | None) -> set[int] | None:
    if q is None:
        return None
    clause, params = dso_search_clause(q, exact_designations=True)
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


async def _matching_dsos(conn, q: str, *, exact_designations: bool) -> list[dict]:
    clause, params = dso_search_clause(q, exact_designations=exact_designations)
    cursor = await conn.execute(
        f"""
        SELECT DISTINCT d.id, d.primary_designation, d.obj_type,
               d.ra_deg, d.dec_deg, d.maj_axis_arcmin, d.min_axis_arcmin,
               d.position_angle_deg, d.common_name, d.constellation,
               d.distance_pc, d.distance_method, d.mag_b, d.active
        FROM dso d
        WHERE {clause}
        """,  # noqa: S608  # nosec B608 - shared static SQL fragment
        params,
    )
    rows = []
    for row in await cursor.fetchall():
        value = dict(row)
        value["type_group"] = group_for_raw_type(value["obj_type"])
        rows.append(value)
    return rows


def _solve_marks(
    solve: SolveGeometry,
    dsos: list[dict],
    target_ids: set[int],
) -> GallerySolveMarks | None:
    annotated = marks_in_solve(solve, dsos)
    if not annotated:
        return None
    pixel_scale = math.hypot(solve.wcs.cd2_1, solve.wcs.cd2_2) * 3600.0
    minimum_inset = 75.0 / pixel_scale if pixel_scale > 0 else 0.0
    marks = [
        GalleryMark(
            dso_id=item.id,
            designation=item.primary_designation,
            common_name=item.common_name,
            pixel_x=item.pixel_x,
            pixel_y=item.pixel_y,
            semi_major_px=item.ellipse_semi_major_px,
            semi_minor_px=item.ellipse_semi_minor_px,
            angle_deg=item.ellipse_angle_deg,
            inset_radius_px=max(
                minimum_inset,
                5.0 * item.ellipse_semi_major_px
                if item.ellipse_semi_major_px is not None
                else minimum_inset,
            ),
            main_target=item.id in target_ids,
        )
        for item in annotated
    ]
    return GallerySolveMarks(
        solve_id=solve.solve_id,
        width=solve.image_width,
        height=solve.image_height,
        pixel_scale_arcsec=pixel_scale,
        marks=marks,
    )


def _project_gallery_solves(
    solves: list[SolveGeometry],
    dsos: list[dict],
    target_ids: dict[int, set[int]],
) -> list[GallerySolveMarks | None]:
    return [_solve_marks(solve, dsos, target_ids.get(solve.project_id, set())) for solve in solves]


def _project_solves(solves: list[SolveGeometry], dsos: list[dict]):
    return [marks_in_solve(solve, dsos) for solve in solves]


async def _search_images(
    conn,
    matched_dsos: list[dict],
    records: list[ProjectRecord],
    *,
    enabled: bool,
    include_retired: bool,
) -> dict[int, GallerySolveMarks] | None:
    if not enabled or not matched_dsos:
        return None
    active_dsos = [
        dso
        for dso in matched_dsos
        if dso["active"] and dso["ra_deg"] is not None and dso["dec_deg"] is not None
    ]
    if not active_dsos:
        return None
    eligible = [record for record in records if include_retired or not record.retired]
    solves = await load_solves(conn, (record.id for record in eligible))
    target_ids = {
        record.id: {facts.target.dso_id for facts in record.targets} for record in records
    }
    projected = await asyncio.to_thread(
        _project_gallery_solves,
        solves,
        active_dsos,
        target_ids,
    )
    return {
        solve.project_id: marks
        for solve, marks in zip(solves, projected, strict=True)
        if marks is not None
    }


async def _is_designation(conn, q: str) -> bool:
    key = normalize_designation(q)
    cursor = await conn.execute(
        """
        SELECT 1 FROM dso_designation WHERE search_key = ?
        UNION ALL
        SELECT 1 FROM dso_group WHERE search_key = ?
        LIMIT 1
        """,
        (key, key),
    )
    return await cursor.fetchone() is not None


async def _search_object(conn, q: str, dsos: list[dict]) -> SearchObject | None:
    if len(dsos) != 1:
        return None
    dso = dsos[0]
    dso_id = int(dso["id"])
    designations = (await load_designations(conn, [dso_id])).get(dso_id, [])
    query_key = normalize_designation(q)
    matched = next(
        (
            item.display_form
            for item in designations
            if normalize_designation(item.display_form) == query_key
        ),
        None,
    )
    alias = matched if matched and matched != dso["primary_designation"] else None
    if alias is None and dso["common_name"] is None:
        alias = next(
            (
                item.display_form
                for item in designations
                if item.display_form != dso["primary_designation"]
            ),
            None,
        )
    return SearchObject(
        dso_id=dso_id,
        designation=dso["primary_designation"],
        common_name=dso["common_name"],
        alias=alias,
    )


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
        records = await load_project_records(conn, with_object_facts=True)
        target_hits = await _search_targets(conn, normalized_q)
        matched_dsos = (
            await _matching_dsos(conn, normalized_q, exact_designations=True)
            if normalized_q is not None
            else []
        )
        image_hits = await _search_images(
            conn,
            matched_dsos,
            records,
            enabled=search_images,
            include_retired=include_retired,
        )
        designation_query = (
            await _is_designation(conn, normalized_q) if normalized_q is not None else False
        )
        search_object = (
            await _search_object(conn, normalized_q, matched_dsos)
            if normalized_q is not None
            else None
        )
    query.search_project_names = not designation_query
    result = build_gallery(
        records,
        query,
        target_search_hits=target_hits,
        image_search_hits=image_hits,
    )
    return GalleryResponse(
        **result.model_dump(),
        workspace_key=workspace_key(),
        search_object=search_object,
    )


@router.get("/suggest", response_model=list[GallerySuggestion])
async def suggest_gallery_objects(
    q: str,
    search_images: bool = Query(False),
    include_retired: bool = Query(False),
) -> list[GallerySuggestion]:
    query = q.strip()
    if len(query) < 2:
        return []
    async with get_db() as conn:
        candidates = await _matching_dsos(conn, query, exact_designations=False)
        if not candidates:
            return []
        designations = await load_designations(conn, [int(dso["id"]) for dso in candidates])
        clause, params = dso_search_clause(query)
        project_cursor = await conn.execute(
            f"""
            SELECT DISTINCT pt.dso_id, pt.project_id
            FROM project_target pt
            JOIN project p ON p.id = pt.project_id
            JOIN dso d ON d.id = pt.dso_id
            WHERE {clause} AND (? OR p.active = 1)
            """,  # noqa: S608  # nosec B608 - shared static SQL fragment
            [*params, include_retired],
        )
        projects_by_dso: dict[int, set[int]] = defaultdict(set)
        for row in await project_cursor.fetchall():
            projects_by_dso[int(row["dso_id"])].add(int(row["project_id"]))

        if search_images:
            records = [
                record
                for record in await load_project_records(conn)
                if include_retired or not record.retired
            ]
            solves = await load_solves(conn, (record.id for record in records))
            active_candidates = [
                dso
                for dso in candidates
                if dso["active"] and dso["ra_deg"] is not None and dso["dec_deg"] is not None
            ]
            projected = await asyncio.to_thread(_project_solves, solves, active_candidates)
            for solve, marks in zip(solves, projected, strict=True):
                for mark in marks:
                    projects_by_dso[mark.id].add(solve.project_id)

    prefixes = designation_search_prefixes(query)
    suggestions: list[GallerySuggestion] = []
    for dso in candidates:
        dso_id = int(dso["id"])
        if not dso["active"] and not projects_by_dso.get(dso_id):
            continue
        choices = designations.get(dso_id, [])
        matched = next(
            (
                item.display_form
                for item in choices
                if any(
                    normalize_designation(item.display_form).startswith(prefix)
                    for prefix in prefixes
                )
            ),
            dso["primary_designation"],
        )
        detail = dso["common_name"]
        if detail is None:
            detail = next(
                (item.display_form for item in choices if item.display_form != matched),
                None,
            )
        suggestions.append(
            GallerySuggestion(
                dso_id=dso_id,
                designation=matched,
                detail=detail,
                project_count=len(projects_by_dso.get(dso_id, set())),
            )
        )
    suggestions.sort(
        key=lambda item: (
            item.project_count == 0,
            -item.project_count,
            designation_sort_key(item.designation),
            item.dso_id,
        )
    )
    return suggestions[:8]
