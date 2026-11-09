"""Correction endpoint for an earlier rig setup."""

import logging

from fastapi import APIRouter, HTTPException

from nightcrate.api.rig_models import RigPartsIn, RigSetupOut
from nightcrate.api.rigs import _setup_response, _validate_rig_parts
from nightcrate.db.session import get_db
from nightcrate.services.rig_setups import RigParts, list_rig_setups, write_setup_parts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rig-setups", tags=["Rigs"])


@router.put("/{setup_id}", response_model=RigSetupOut)
async def update_rig_setup(setup_id: int, body: RigPartsIn):
    async with get_db() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = await conn.execute("SELECT rig_id FROM rig_setup WHERE id = ?", (setup_id,))
            setup = await cursor.fetchone()
            if setup is None:
                raise HTTPException(status_code=404, detail="Rig setup not found")
            await _validate_rig_parts(conn, body)
            parts = RigParts(
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
                filter_slots=frozenset(
                    (slot.slot_number, slot.filter_id) for slot in body.filter_slots
                ),
                software_ids=frozenset(body.software_ids),
            )
            await write_setup_parts(conn, setup_id, parts)
            summaries = await list_rig_setups(conn, setup["rig_id"])
            summary = next(item for item in summaries if item.id == setup_id)
            response = await _setup_response(conn, summary)
            await conn.commit()
            return response
        except HTTPException:
            await conn.rollback()
            raise
        except ValueError as exc:
            await conn.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            await conn.rollback()
            logger.exception("[rig-setups] failed to update setup %d", setup_id)
            raise HTTPException(status_code=500, detail="Failed to update rig setup") from exc
        except BaseException:
            await conn.rollback()
            raise
