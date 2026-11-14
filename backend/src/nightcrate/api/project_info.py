"""Project object-information endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from nightcrate.api.gallery import load_project_records
from nightcrate.api.object_facts_db import load_other_objects
from nightcrate.api.project_info_models import ProjectInfo, SolveField
from nightcrate.db.session import get_db
from nightcrate.services.astronomy import constellation_for_coords
from nightcrate.services.gallery import GalleryQuery, build_gallery

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.get("/{project_id}/info", response_model=ProjectInfo)
async def get_project_info(project_id: int) -> ProjectInfo:
    async with get_db() as conn:
        records = await load_project_records(
            conn,
            project_ids=[project_id],
            with_object_facts=True,
        )
        if not records:
            raise HTTPException(status_code=404, detail="Project not found")
        record = records[0]
        other_objects = (await load_other_objects(conn, [project_id])).get(project_id, [])
        solve_cursor = await conn.execute(
            """
            SELECT center_ra_deg, center_dec_deg, ra_hms, dec_dms,
                   fov_width_arcmin, fov_height_arcmin, rotation_deg
            FROM project_solve
            WHERE project_id = ?
            """,
            (project_id,),
        )
        solve = await solve_cursor.fetchone()

    item = build_gallery(
        [record],
        GalleryQuery(include_retired=True),
        target_search_hits=None,
        image_search_hits=None,
    ).items[0]
    field = None
    if solve is not None:
        centre_ra_deg = float(solve["center_ra_deg"])
        centre_dec_deg = float(solve["center_dec_deg"])
        field = SolveField(
            constellation=constellation_for_coords(centre_ra_deg, centre_dec_deg),
            centre_ra_hms=solve["ra_hms"],
            centre_dec_dms=solve["dec_dms"],
            centre_ra_deg=centre_ra_deg,
            centre_dec_deg=centre_dec_deg,
            fov_width_deg=(
                float(solve["fov_width_arcmin"]) / 60
                if solve["fov_width_arcmin"] is not None
                else None
            ),
            fov_height_deg=(
                float(solve["fov_height_arcmin"]) / 60
                if solve["fov_height_arcmin"] is not None
                else None
            ),
            rotation_deg=(
                float(solve["rotation_deg"]) if solve["rotation_deg"] is not None else None
            ),
        )

    return ProjectInfo(
        project_id=item.project_id,
        name=item.name,
        status=item.status,
        retired=item.retired,
        solved=record.has_solve,
        targets=item.targets,
        other_objects=other_objects,
        other_distances=item.other_distances,
        field=field,
        first_date=item.first_date,
        last_date=item.last_date,
        nights=item.nights,
        imaging_runs=item.imaging_runs,
        integration_minutes=item.integration_minutes,
        rigs=item.rigs,
    )
