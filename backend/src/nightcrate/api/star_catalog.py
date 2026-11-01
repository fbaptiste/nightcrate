from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from nightcrate.db.session import get_db
from nightcrate.services import plate_solve
from nightcrate.services.star_catalog import fetch
from nightcrate.services.star_catalog.ranges import (
    FIELD_RANGES,
    built_ranges,
    layer_path,
    range_for_field,
    read_manifest,
)
from nightcrate.services.star_catalog.store import (
    SIRIL_SOURCE,
    AlreadyInstalled,
    InsufficientSpace,
    installed,
    star_root,
)

from .star_catalog_models import (
    BuildRequest,
    ImportRequest,
    RangeStatus,
    RigCoverage,
    SourceStatus,
    StarCatalogStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/star-catalog", tags=["Star catalog"])
fetch.publish_lock = plate_solve.solve_slot_wait


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, fetch.StarOperationBusy):
        return HTTPException(status_code=409, detail="Another star-data task is running.")
    if isinstance(exc, AlreadyInstalled):
        return HTTPException(
            status_code=422,
            detail=(
                "The plate-solving stars are already installed. Remove them first "
                "to download or import again."
            ),
        )
    if isinstance(exc, InsufficientSpace):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


async def _rig_coverage() -> list[RigCoverage]:
    result: list[RigCoverage] = []
    try:
        async with get_db() as conn:
            rows = await conn.execute_fetchall(
                "SELECT * FROM rig_summary WHERE active = 1 AND is_mine = 1 "
                "ORDER BY sort_order, name"
            )
    except sqlite3.Error, OSError:
        logger.warning("[star_catalog] failed to load rig coverage", exc_info=True)
        return result
    for row in rows:
        try:
            focal = row["effective_focal_length_mm"]
            px = row["pixel_size_um"]
            rx = row["sensor_resolution_x"]
            ry = row["sensor_resolution_y"]
            if focal is None or px is None or rx is None or ry is None:
                continue
            pixel_scale = px / focal * 206.265
            field_deg = pixel_scale * max(rx, ry) / 3600.0
            result.append(RigCoverage(id=row["id"], name=row["name"], field_deg=field_deg))
        except KeyError, TypeError, ValueError, ZeroDivisionError:
            continue
    return result


def _bytes_used() -> int:
    root = star_root()
    if not root.exists():
        return 0
    return sum(
        path.stat().st_size
        for path in root.rglob("*")
        if path.is_file() and ".staging" not in path.parts
    )


@router.get("/status", response_model=StarCatalogStatus)
async def get_status() -> StarCatalogStatus:
    rigs = await _rig_coverage()
    manifest = read_manifest()
    ready = built_ranges()
    operation = fetch.current_operation()
    range_rows: list[RangeStatus] = []
    for item in FIELD_RANGES:
        requested = (
            operation is not None
            and operation.state == "running"
            and operation.kind == "build"
            and item.id in operation.ranges
        )
        if requested and item.id == operation.current_range:
            state = "building"
        elif item.id in ready:
            state = "built"
        elif requested:
            state = "waiting"
        elif item.id in manifest:
            state = "needs_rebuild"
        else:
            state = "not_built"
        actual = sum(
            layer_path(name).stat().st_size for name in item.layers if layer_path(name).is_file()
        )
        size_is_estimate = state not in {"built", "needs_rebuild"} or not actual
        covered_rigs = [rig for rig in rigs if range_for_field(rig.field_deg) == item]
        range_rows.append(
            RangeStatus(
                id=item.id,
                name=item.name,
                recommended=item.recommended,
                min_deg=item.min_deg,
                max_deg=item.max_deg,
                state=state,
                progress=(
                    operation.range_progress.get(item.id)
                    if state == "building" and operation is not None
                    else None
                ),
                size_bytes=item.estimated_bytes if size_is_estimate else actual,
                size_is_estimate=size_is_estimate,
                build_memory_bytes=item.build_memory_bytes,
                rigs=covered_rigs,
            )
        )
    root = star_root()
    root.mkdir(parents=True, exist_ok=True)
    return StarCatalogStatus(
        installed=installed(),
        source=SourceStatus(
            version=SIRIL_SOURCE.version,
            download_bytes=SIRIL_SOURCE.compressed_size,
            unpacked_bytes=SIRIL_SOURCE.uncompressed_size,
            doi=SIRIL_SOURCE.doi,
            licence=SIRIL_SOURCE.licence,
            gaia_licence=SIRIL_SOURCE.gaia_licence,
            attribution=SIRIL_SOURCE.attribution,
        ),
        operation=operation,
        ranges=range_rows,
        total_bytes_used=_bytes_used(),
        free_bytes=shutil.disk_usage(root).free,
    )


@router.post("/download", response_model=fetch.StarOperation, status_code=status.HTTP_202_ACCEPTED)
async def download() -> fetch.StarOperation:
    try:
        return fetch.start_download()
    except (fetch.StarOperationBusy, AlreadyInstalled, InsufficientSpace) as exc:
        raise _translate_error(exc) from exc
    except Exception as exc:
        logger.exception("[star_catalog] failed to start download")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/import", response_model=fetch.StarOperation, status_code=status.HTTP_202_ACCEPTED)
async def import_file(request: ImportRequest) -> fetch.StarOperation:
    path = Path(request.path)
    if not path.is_file():
        raise HTTPException(status_code=422, detail="Import path does not exist.")
    try:
        return fetch.start_import(path)
    except (fetch.StarOperationBusy, AlreadyInstalled, InsufficientSpace, ValueError) as exc:
        raise _translate_error(exc) from exc
    except Exception as exc:
        logger.exception("[star_catalog] failed to start import")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/cancel", response_model=fetch.StarOperation, status_code=status.HTTP_202_ACCEPTED)
async def cancel() -> fetch.StarOperation:
    fetch.cancel_operation()
    operation = fetch.current_operation()
    if operation is None:
        raise HTTPException(status_code=422, detail="No star-data task is running.")
    return operation


@router.post(
    "/ranges/build", response_model=fetch.StarOperation, status_code=status.HTTP_202_ACCEPTED
)
async def build_ranges(request: BuildRequest) -> fetch.StarOperation:
    valid = {item.id for item in FIELD_RANGES}
    unknown = sorted(set(request.range_ids) - valid)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown field range: {', '.join(unknown)}")
    try:
        return fetch.start_build(request.range_ids)
    except (fetch.StarOperationBusy, InsufficientSpace) as exc:
        raise _translate_error(exc) from exc
    except Exception as exc:
        logger.exception("[star_catalog] failed to start index build")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/ranges/{range_id}", response_model=fetch.StarOperation)
async def remove_range(range_id: str) -> fetch.StarOperation:
    if range_id not in {item.id for item in FIELD_RANGES}:
        raise HTTPException(status_code=422, detail=f"Unknown field range: {range_id}")
    try:
        async with plate_solve.solve_slot():
            return fetch.start_remove([range_id])
    except plate_solve.SolveSlotBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except fetch.StarOperationBusy as exc:
        raise _translate_error(exc) from exc
    except Exception as exc:
        logger.exception("[star_catalog] failed to remove index range")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/", response_model=fetch.StarOperation)
async def remove_all() -> fetch.StarOperation:
    try:
        async with plate_solve.solve_slot():
            return fetch.start_remove("all")
    except plate_solve.SolveSlotBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except fetch.StarOperationBusy as exc:
        raise _translate_error(exc) from exc
    except Exception as exc:
        logger.exception("[star_catalog] failed to remove star catalog")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
