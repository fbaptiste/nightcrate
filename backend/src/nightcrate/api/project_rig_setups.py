"""Project setup history and project-specific rig changes."""

import logging
import math

import aiosqlite
from fastapi import APIRouter, HTTPException, Response

from nightcrate.api.project_rig_setup_models import (
    ProjectRigPartsOut,
    ProjectRigSetupsOut,
    ProjectSetupOptionOut,
    ProjectSetupOut,
)
from nightcrate.api.rig_models import RigPartsIn
from nightcrate.api.rigs import _parts_response, _validate_rig_parts
from nightcrate.db.session import get_db
from nightcrate.services.rig_setups import (
    ProjectRigSetups,
    RigParts,
    changed_groups,
    project_setups,
    read_rig_parts,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Projects"])


def _parts_from_body(body: RigPartsIn) -> RigParts:
    return RigParts(
        telescope_configuration_id=body.telescope_configuration_id,
        camera_id=body.camera_id,
        filter_wheel_id=body.filter_wheel_id,
        single_filter_id=body.single_filter_id,
        mount_id=body.mount_id,
        focuser_id=body.focuser_id,
        oag_id=body.oag_id,
        guide_scope_id=body.guide_scope_id,
        guide_camera_id=body.guide_camera_id,
        computer_id=body.computer_id,
        filter_slots=frozenset((slot.slot_number, slot.filter_id) for slot in body.filter_slots),
        software_ids=frozenset(body.software_ids),
    )


def _parts_ids(parts: RigParts) -> RigPartsIn:
    return RigPartsIn(
        **{
            column: getattr(parts, column)
            for column in (
                "telescope_configuration_id",
                "camera_id",
                "filter_wheel_id",
                "single_filter_id",
                "mount_id",
                "focuser_id",
                "oag_id",
                "guide_scope_id",
                "guide_camera_id",
                "computer_id",
            )
        },
        filter_slots=[
            {"slot_number": slot, "filter_id": filter_id}
            for slot, filter_id in sorted(parts.filter_slots)
        ],
        software_ids=sorted(parts.software_ids),
    )


async def _resolved_parts(conn, parts: RigParts) -> ProjectRigPartsOut:
    names = await _parts_response(conn, parts)
    cursor = await conn.execute(
        """
        SELECT tc.effective_focal_length_mm, tc.effective_focal_ratio,
               s.pixel_size_um, s.resolution_x, s.resolution_y
        FROM telescope_configuration tc
        JOIN camera c ON c.id = ?
        JOIN sensor s ON s.id = c.sensor_id
        WHERE tc.id = ?
        """,
        (parts.camera_id, parts.telescope_configuration_id),
    )
    row = await cursor.fetchone()
    if row is None:
        raise ValueError("rig parts refer to missing camera or telescope configuration")
    focal = float(row["effective_focal_length_mm"])
    pixel = float(row["pixel_size_um"])
    width_mm = row["resolution_x"] * pixel / 1000.0
    height_mm = row["resolution_y"] * pixel / 1000.0
    return ProjectRigPartsOut(
        **names.model_dump(),
        effective_focal_length_mm=focal,
        effective_focal_ratio=float(row["effective_focal_ratio"]),
        pixel_size_um=pixel,
        sensor_resolution_x=row["resolution_x"],
        sensor_resolution_y=row["resolution_y"],
        image_scale_arcsec_per_pixel=round(206.265 * pixel / focal, 2),
        field_of_view_deg=(
            round(math.degrees(2 * math.atan(width_mm / (2 * focal))), 2),
            round(math.degrees(2 * math.atan(height_mm / (2 * focal))), 2),
        ),
    )


async def _response(conn, item: ProjectRigSetups) -> ProjectRigSetupsOut:
    setup_options: list[ProjectSetupOptionOut] = []
    for setup in item.setup_options:
        parts = await _resolved_parts(conn, setup.parts)
        setup_options.append(
            ProjectSetupOptionOut(
                rig_setup_id=setup.rig_setup_id,
                until_at=setup.until_at,
                camera_name=parts.camera_name,
                image_scale_arcsec_per_pixel=parts.image_scale_arcsec_per_pixel,
            )
        )
    return ProjectRigSetupsOut(
        rig_id=item.rig_id,
        rig_name=item.rig_name,
        declared=item.declared,
        setups=[
            ProjectSetupOut(
                rig_setup_id=setup.rig_setup_id,
                until_at=setup.until_at,
                since_at=setup.since_at,
                night_count=setup.night_count,
                parts=await _resolved_parts(conn, setup.parts),
            )
            for setup in item.setups
        ],
        setup_options=setup_options,
        base_parts=_parts_ids(item.base_parts),
        change=_parts_ids(item.change) if item.change is not None else None,
        changed_groups=list(item.changed_groups),
    )


async def _one_response(conn, project_id: int, rig_id: int) -> ProjectRigSetupsOut:
    items = await project_setups(conn, project_id)
    try:
        item = next(value for value in items if value.rig_id == rig_id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Rig is not used by this project") from exc
    return await _response(conn, item)


@router.get("/{project_id}/rig-setups", response_model=list[ProjectRigSetupsOut])
async def get_project_rig_setups(project_id: int):
    async with get_db() as conn:
        try:
            return [await _response(conn, item) for item in await project_setups(conn, project_id)]
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc


async def _write_change(
    conn: aiosqlite.Connection,
    project_id: int,
    rig_id: int,
    base: RigParts,
    requested: RigParts,
) -> None:
    groups = changed_groups(base, requested)
    if not groups:
        await conn.execute(
            "DELETE FROM project_rig_change WHERE project_id = ? AND rig_id = ?",
            (project_id, rig_id),
        )
        return

    changed = set(groups)
    await conn.execute(
        """
        INSERT INTO project_rig_change (
            project_id, rig_id, telescope_configuration_id, camera_id,
            filters_changed, filter_wheel_id, single_filter_id,
            mount_changed, mount_id, focuser_changed, focuser_id,
            guider_changed, oag_id, guide_scope_id,
            guide_camera_changed, guide_camera_id,
            computer_changed, computer_id, software_changed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, rig_id) DO UPDATE SET
            telescope_configuration_id = excluded.telescope_configuration_id,
            camera_id = excluded.camera_id,
            filters_changed = excluded.filters_changed,
            filter_wheel_id = excluded.filter_wheel_id,
            single_filter_id = excluded.single_filter_id,
            mount_changed = excluded.mount_changed, mount_id = excluded.mount_id,
            focuser_changed = excluded.focuser_changed, focuser_id = excluded.focuser_id,
            guider_changed = excluded.guider_changed, oag_id = excluded.oag_id,
            guide_scope_id = excluded.guide_scope_id,
            guide_camera_changed = excluded.guide_camera_changed,
            guide_camera_id = excluded.guide_camera_id,
            computer_changed = excluded.computer_changed, computer_id = excluded.computer_id,
            software_changed = excluded.software_changed
        """,
        (
            project_id,
            rig_id,
            requested.telescope_configuration_id if "telescope" in changed else None,
            requested.camera_id if "camera" in changed else None,
            int("filters" in changed),
            requested.filter_wheel_id if "filters" in changed else None,
            requested.single_filter_id if "filters" in changed else None,
            int("mount" in changed),
            requested.mount_id if "mount" in changed else None,
            int("focuser" in changed),
            requested.focuser_id if "focuser" in changed else None,
            int("guider" in changed),
            requested.oag_id if "guider" in changed else None,
            requested.guide_scope_id if "guider" in changed else None,
            int("guide_camera" in changed),
            requested.guide_camera_id if "guide_camera" in changed else None,
            int("computer" in changed),
            requested.computer_id if "computer" in changed else None,
            int("software" in changed),
        ),
    )
    await conn.execute(
        "DELETE FROM project_rig_change_filter_slot WHERE project_id = ? AND rig_id = ?",
        (project_id, rig_id),
    )
    if "filters" in changed:
        await conn.executemany(
            "INSERT INTO project_rig_change_filter_slot "
            "(project_id, rig_id, slot_number, filter_id) VALUES (?, ?, ?, ?)",
            [
                (project_id, rig_id, slot, filter_id)
                for slot, filter_id in sorted(requested.filter_slots)
            ],
        )
    await conn.execute(
        "DELETE FROM project_rig_change_software WHERE project_id = ? AND rig_id = ?",
        (project_id, rig_id),
    )
    if "software" in changed:
        await conn.executemany(
            "INSERT INTO project_rig_change_software "
            "(project_id, rig_id, software_id) VALUES (?, ?, ?)",
            [(project_id, rig_id, software_id) for software_id in requested.software_ids],
        )


@router.put("/{project_id}/rigs/{rig_id}/change", response_model=ProjectRigSetupsOut)
async def put_project_rig_change(project_id: int, rig_id: int, body: RigPartsIn):
    async with get_db() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            items = await project_setups(conn, project_id)
            if not any(item.rig_id == rig_id for item in items):
                raise HTTPException(status_code=404, detail="Rig is not used by this project")
            await _validate_rig_parts(conn, body)
            base = await read_rig_parts(conn, rig_id)
            await _write_change(conn, project_id, rig_id, base, _parts_from_body(body))
            response = await _one_response(conn, project_id, rig_id)
            await conn.commit()
            return response
        except HTTPException:
            await conn.rollback()
            raise
        except (ValueError, aiosqlite.IntegrityError) as exc:
            await conn.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            await conn.rollback()
            logger.exception(
                "[rig-setups] failed to change rig %d for project %d", rig_id, project_id
            )
            raise HTTPException(
                status_code=500, detail="Failed to save project rig change"
            ) from exc
        except BaseException:
            await conn.rollback()
            raise


@router.delete("/{project_id}/rigs/{rig_id}/change", status_code=204)
async def delete_project_rig_change(project_id: int, rig_id: int):
    async with get_db() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = await conn.execute("SELECT id FROM project WHERE id = ?", (project_id,))
            if await cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Project not found")
            await conn.execute(
                "DELETE FROM project_rig_change WHERE project_id = ? AND rig_id = ?",
                (project_id, rig_id),
            )
            await conn.commit()
            return Response(status_code=204)
        except HTTPException:
            await conn.rollback()
            raise
        except Exception as exc:
            await conn.rollback()
            logger.exception(
                "[rig-setups] failed to remove rig %d change for project %d",
                rig_id,
                project_id,
            )
            raise HTTPException(
                status_code=500, detail="Failed to remove project rig change"
            ) from exc
        except BaseException:
            await conn.rollback()
            raise
