"""Batched Messier checklist endpoint."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query
from PIL import Image, UnidentifiedImageError

from nightcrate.api._common import load_other_names
from nightcrate.api.gallery import load_project_records
from nightcrate.api.messier_models import (
    CropSize,
    MessierCounts,
    MessierLocation,
    MessierObject,
    MessierResponse,
    MessierRig,
    MessierSlot,
    SlotProject,
    SurveyImage,
)
from nightcrate.catalog_loader import registry
from nightcrate.core.app_config import get_projects_root
from nightcrate.db.session import get_db, workspace_key
from nightcrate.services.gallery import ProjectRecord, imaging_runs
from nightcrate.services.messier import (
    MESSIER_NUMBERS,
    Candidate,
    PictureField,
    SolveFacts,
    crop_field,
    main_image_field,
    never_rises,
    order_candidates,
    slot_state,
)
from nightcrate.services.rig_calculators import rig_fov_from_summary
from nightcrate.services.thumbnails import ChecklistRender

router = APIRouter(prefix="/api/messier", tags=["Projects"])

_CROP_SIZES: tuple[CropSize, ...] = ("small", "medium", "large")
_ID_BATCH_SIZE = 500


def _slot_project(
    record: ProjectRecord,
    picture_fields: dict[int, dict[CropSize, PictureField | None]],
) -> SlotProject:
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
        picture_fields=(
            picture_fields.get(record.id) if record.main_image_id is not None else None
        ),
    )


def _main_preview_size(
    projects_root: Path | None,
    project_id: int,
    image_id: int,
) -> tuple[int, int] | None:
    if projects_root is None:
        return None
    path = projects_root / str(project_id) / f"img_{image_id}" / "thumb_lg.jpg"
    try:
        with Image.open(path) as image:
            return image.size
    except FileNotFoundError, OSError, UnidentifiedImageError:
        return None


async def _load_picture_fields(
    conn,
    records: list[ProjectRecord],
) -> dict[int, dict[CropSize, PictureField | None]]:
    """Load solve and crop geometry for every candidate project with an image."""
    if not records:
        return {}
    project_ids = list(dict.fromkeys(record.id for record in records))
    facts_by_project: dict[int, dict] = {}
    crops_by_project: dict[int, dict[str, dict]] = defaultdict(dict)
    for start in range(0, len(project_ids), _ID_BATCH_SIZE):
        batch = project_ids[start : start + _ID_BATCH_SIZE]
        placeholders = ",".join("?" * len(batch))
        facts_cursor = await conn.execute(
            f"""
            SELECT p.id AS project_id,
                   pi.id AS main_image_id, pi.file_path AS main_path,
                   ps.image_path, ps.image_width, ps.image_height,
                   ps.fov_width_arcmin, ps.fov_height_arcmin
            FROM project p
            LEFT JOIN project_image pi
              ON pi.project_id = p.id AND pi.is_main = 1
            LEFT JOIN project_solve ps ON ps.project_id = p.id
            WHERE p.id IN ({placeholders})
            """,  # noqa: S608  # nosec B608 - bounded integer-id batch
            batch,
        )
        for row in await facts_cursor.fetchall():
            facts_by_project[int(row["project_id"])] = dict(row)

        crop_cursor = await conn.execute(
            f"""
            SELECT project_id, size, source_image_id, crop_w, crop_h
            FROM project_thumbnail
            WHERE project_id IN ({placeholders})
            """,  # noqa: S608  # nosec B608 - bounded integer-id batch
            batch,
        )
        for row in await crop_cursor.fetchall():
            crops_by_project[int(row["project_id"])][str(row["size"])] = dict(row)

    projects_root = get_projects_root()
    result: dict[int, dict[CropSize, PictureField | None]] = {}
    for record in records:
        facts = facts_by_project.get(record.id, {})
        solve = None
        if facts.get("image_path") is not None:
            solve = SolveFacts(
                image_path=facts["image_path"],
                image_width=int(facts["image_width"]),
                image_height=int(facts["image_height"]),
                fov_width_arcmin=facts["fov_width_arcmin"],
                fov_height_arcmin=facts["fov_height_arcmin"],
            )
        image_id = record.main_image_id
        preview_size = (
            _main_preview_size(projects_root, record.id, image_id) if image_id is not None else None
        )
        main = main_image_field(solve, facts.get("main_path"), preview_size)
        fields: dict[CropSize, PictureField | None] = {}
        for size in _CROP_SIZES:
            crop = crops_by_project.get(record.id, {}).get(size)
            visible_crop = record.crops.get(size)
            if crop is None or visible_crop is None:
                fields[size] = main
            elif image_id is not None and crop["source_image_id"] in (None, image_id):
                fields[size] = (
                    crop_field(main, float(crop["crop_w"]), float(crop["crop_h"]))
                    if main is not None
                    else None
                )
            else:
                fields[size] = None
        result[record.id] = fields
    return result


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
    return MessierRig(
        id=int(row["id"]),
        name=row["name"],
        fov_major_deg=field[0] if field is not None else None,
        fov_minor_deg=field[1] if field is not None else None,
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
                counts=MessierCounts(imaged=0, project=0, never_rises=0, missing=0),
                slots=[],
                workspace_key=workspace_key(),
            )

        dso_ids = [int(row["id"]) for row in object_rows.values()]
        other_names = await load_other_names(conn, dso_ids)
        location_model = await _load_location(conn, location)
        rig_model = await _load_rig(conn, rig_id)
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
        imaged_records = [
            record
            for record in records
            if record.main_image_id is not None
            and any(target.target.dso_id in messier_dso_ids for target in record.targets)
        ]
        picture_fields = await _load_picture_fields(conn, imaged_records)

    slots: list[MessierSlot] = []
    imaged_count = 0
    project_count = 0
    never_count = 0
    missing_count = 0
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
                descriptor = ChecklistRender.for_object(
                    float(row["ra_deg"]),
                    float(row["dec_deg"]),
                    row["maj_axis_arcmin"],
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
        slots.append(
            MessierSlot(
                number=number,
                object=object_model,
                state=state,
                never_rises=does_not_rise,
                projects=[
                    _slot_project(records_by_id[item.project_id], picture_fields)
                    for item in ordered
                ],
                survey=survey,
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
        ),
        slots=slots,
        workspace_key=workspace_key(),
    )
