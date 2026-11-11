"""Batched Messier checklist endpoint."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Query

from nightcrate.api._common import load_other_names
from nightcrate.api.gallery import load_project_records
from nightcrate.api.messier_models import (
    MessierCounts,
    MessierLocation,
    MessierObject,
    MessierResponse,
    MessierRig,
    MessierSlot,
    SlotProject,
    SolvedPicture,
    SurveyImage,
)
from nightcrate.api.object_search_db import load_solves
from nightcrate.catalog_loader import registry
from nightcrate.db.session import get_db, workspace_key
from nightcrate.services.dso_type_groups import group_for_raw_type
from nightcrate.services.gallery import ProjectRecord, imaging_runs
from nightcrate.services.messier import (
    MESSIER_NUMBERS,
    Candidate,
    never_rises,
    order_candidates,
    rig_view_field_deg,
    slot_state,
)
from nightcrate.services.object_search import marks_in_solve
from nightcrate.services.rig_calculators import compute_coverage_pct, rig_fov_from_summary
from nightcrate.services.thumbnails import ChecklistRender

router = APIRouter(prefix="/api/messier", tags=["Projects"])


def _project_solves(solves, dsos):
    return [marks_in_solve(solve, dsos) for solve in solves]


def _slot_project(record: ProjectRecord) -> SlotProject:
    return SlotProject(
        project_id=record.id,
        name=record.name,
        status=record.status,
        main_image_id=record.main_image_id,
        crops=record.crops,
        first_date=record.dates[0].isoformat() if record.dates else None,
        last_date=record.dates[-1].isoformat() if record.dates else None,
        nights=len(record.dates),
        imaging_runs=imaging_runs(record.dates),
    )


async def _load_location(
    conn,
    requested: Literal["default", "none"] | int,
) -> MessierLocation | None:
    if requested == "none":
        return None
    row = None
    if isinstance(requested, int):
        cursor = await conn.execute(
            "SELECT id, name, latitude FROM location WHERE id = ? AND active = 1",
            (requested,),
        )
        row = await cursor.fetchone()
    if row is None:
        cursor = await conn.execute(
            """
            SELECT id, name, latitude
            FROM location
            WHERE is_default = 1 AND active = 1
            ORDER BY id
            LIMIT 1
            """
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return MessierLocation(
        id=int(row["id"]),
        name=row["name"],
        latitude_deg=float(row["latitude"]),
    )


async def _load_rig(conn, rig_id: int | None) -> MessierRig | None:
    if rig_id is None:
        return None
    cursor = await conn.execute(
        "SELECT * FROM rig_summary WHERE id = ? AND active = 1",
        (rig_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    field = rig_fov_from_summary(row)
    view_field = rig_view_field_deg(*field) if field is not None else None
    return MessierRig(
        id=int(row["id"]),
        name=row["name"],
        fov_major_deg=field[0] if field is not None else None,
        fov_minor_deg=field[1] if field is not None else None,
        view_field_deg=view_field,
    )


@router.get("", response_model=MessierResponse)
async def get_messier(
    location: Literal["default", "none"] | int = Query("default"),
    rig_id: int | None = None,
) -> MessierResponse:
    async with get_db() as conn:
        object_cursor = await conn.execute(
            """
            SELECT CAST(dd.identifier AS INTEGER) AS messier_number,
                   d.id, d.common_name, d.obj_type, d.constellation, d.mag_v,
                   d.maj_axis_arcmin, d.min_axis_arcmin, d.active,
                   d.ra_deg, d.dec_deg
            FROM dso_designation dd
            JOIN dso d ON d.id = dd.dso_id
            WHERE dd.catalog = 'messier'
            ORDER BY CAST(dd.identifier AS INTEGER), d.id
            """
        )
        object_rows = {
            int(row["messier_number"]): row
            for row in await object_cursor.fetchall()
            if int(row["messier_number"]) in MESSIER_NUMBERS
        }

        catalogs_root = registry.user_catalogs_root() / "openngc"
        if not object_rows and not any(
            (catalogs_root / name).is_file() for name in ("NGC.csv", "addendum.csv")
        ):
            return MessierResponse(
                catalog_status="not_downloaded",
                location=await _load_location(conn, location),
                rig=await _load_rig(conn, rig_id),
                counts=MessierCounts(
                    imaged=0,
                    project=0,
                    never_rises=0,
                    missing=0,
                    in_solved=0,
                ),
                slots=[],
                workspace_key=workspace_key(),
            )

        dso_ids = [int(row["id"]) for row in object_rows.values()]
        other_names = await load_other_names(conn, dso_ids)
        location_model = await _load_location(conn, location)
        rig_model = await _load_rig(conn, rig_id)
        rig_field = (
            (rig_model.fov_major_deg, rig_model.fov_minor_deg)
            if rig_model is not None
            and rig_model.fov_major_deg is not None
            and rig_model.fov_minor_deg is not None
            else None
        )
        survey_field = rig_model.view_field_deg if rig_model is not None else None
        records = [record for record in await load_project_records(conn) if not record.retired]

        records_by_id = {record.id: record for record in records}
        candidates_by_dso: dict[int, list[Candidate]] = defaultdict(list)
        messier_dso_ids = set(dso_ids)
        for record in records:
            candidate = Candidate(
                project_id=record.id,
                name=record.name,
                status=record.status,
                created_at=record.created_at,
                main_image_id=record.main_image_id,
                dates=record.dates,
            )
            for target in record.targets:
                if target.target.dso_id in messier_dso_ids:
                    candidates_by_dso[target.target.dso_id].append(candidate)

        ordered_by_dso = {
            dso_id: order_candidates(items, image_first=True)
            for dso_id, items in candidates_by_dso.items()
        }
        solves = await load_solves(conn, (record.id for record in records))
        searchable_dsos = [
            {
                **dict(row),
                "id": int(row["id"]),
                "primary_designation": f"M {number}",
                "type_group": group_for_raw_type(row["obj_type"]),
            }
            for number, row in object_rows.items()
            if row["active"] and row["ra_deg"] is not None and row["dec_deg"] is not None
        ]
        projected = await asyncio.to_thread(_project_solves, solves, searchable_dsos)
        solved_by_dso: dict[int, list[SolvedPicture]] = defaultdict(list)
        for solve, marks in zip(solves, projected, strict=True):
            record = records_by_id[solve.project_id]
            for mark in marks:
                solved_by_dso[mark.id].append(SolvedPicture(project_id=record.id, name=record.name))
        for pictures in solved_by_dso.values():
            pictures.sort(key=lambda picture: (picture.name.casefold(), picture.project_id))

    slots: list[MessierSlot] = []
    imaged_count = 0
    project_count = 0
    never_count = 0
    missing_count = 0
    in_solved_count = 0
    for number in MESSIER_NUMBERS:
        row = object_rows.get(number)
        dso_id = int(row["id"]) if row is not None else None
        ordered = ordered_by_dso.get(dso_id, []) if dso_id is not None else []
        state = slot_state(row is not None, ordered)
        if state == "imaged":
            imaged_count += 1
        elif state == "project":
            project_count += 1
        elif state == "missing":
            missing_count += 1

        object_model = None
        survey = None
        if row is not None:
            object_model = MessierObject(
                dso_id=int(row["id"]),
                designation=f"M {number}",
                common_name=row["common_name"],
                other_names=other_names.get(int(row["id"]), []),
                obj_type=row["obj_type"],
                constellation=row["constellation"],
                mag_v=row["mag_v"],
                maj_axis_arcmin=row["maj_axis_arcmin"],
                min_axis_arcmin=row["min_axis_arcmin"],
                active=bool(row["active"]),
            )
            if row["ra_deg"] is not None and row["dec_deg"] is not None:
                descriptor = (
                    ChecklistRender.for_field(
                        float(row["ra_deg"]),
                        float(row["dec_deg"]),
                        survey_field,
                    )
                    if survey_field is not None
                    else ChecklistRender.for_object(
                        float(row["ra_deg"]),
                        float(row["dec_deg"]),
                        row["maj_axis_arcmin"],
                    )
                )
                survey = SurveyImage(
                    field_deg=descriptor.field_mdeg / 1000,
                    render_key=descriptor.render_key,
                )

        does_not_rise = bool(
            state != "imaged"
            and location_model is not None
            and row is not None
            and never_rises(location_model.latitude_deg, row["dec_deg"])
        )
        never_count += int(does_not_rise)
        in_solved_pictures = (
            solved_by_dso.get(dso_id, []) if state == "none" and dso_id is not None else []
        )
        in_solved_count += int(bool(in_solved_pictures))
        slots.append(
            MessierSlot(
                number=number,
                object=object_model,
                state=state,
                never_rises=does_not_rise,
                projects=[_slot_project(records_by_id[item.project_id]) for item in ordered],
                survey=survey,
                coverage_pct=(
                    compute_coverage_pct(
                        *rig_field,
                        row["maj_axis_arcmin"],
                        row["min_axis_arcmin"],
                    )
                    if rig_field is not None and row is not None
                    else None
                ),
                in_solved_pictures=in_solved_pictures,
            )
        )

    return MessierResponse(
        catalog_status="ready",
        location=location_model,
        rig=rig_model,
        counts=MessierCounts(
            imaged=imaged_count,
            project=project_count,
            never_rises=never_count,
            missing=missing_count,
            in_solved=in_solved_count,
        ),
        slots=slots,
        workspace_key=workspace_key(),
    )
