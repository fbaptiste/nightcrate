"""Database loading helpers for plate-solve object search."""

from __future__ import annotations

from collections.abc import Iterable

from nightcrate.services.image_annotation_models import WcsParams
from nightcrate.services.object_search import SolveGeometry

_ID_BATCH_SIZE = 500


def _geometry(row) -> SolveGeometry:
    width = int(row["image_width"])
    height = int(row["image_height"])
    return SolveGeometry(
        project_id=int(row["project_id"]),
        solve_id=int(row["id"]),
        image_width=width,
        image_height=height,
        wcs=WcsParams(
            crval1=row["center_ra_deg"],
            crval2=row["center_dec_deg"],
            cd1_1=row["cd1_1"],
            cd1_2=row["cd1_2"],
            cd2_1=row["cd2_1"],
            cd2_2=row["cd2_2"],
            crpix1=row["crpix1"],
            crpix2=row["crpix2"],
            naxis1=width,
            naxis2=height,
        ),
    )


async def load_solves(conn, project_ids: Iterable[int] | None = None) -> list[SolveGeometry]:
    """Load all solve geometry, or geometry for a bounded set of projects."""
    if project_ids is None:
        cursor = await conn.execute("SELECT * FROM project_solve ORDER BY project_id")
        return [_geometry(row) for row in await cursor.fetchall()]

    ids = list(dict.fromkeys(int(value) for value in project_ids))
    result: list[SolveGeometry] = []
    for start in range(0, len(ids), _ID_BATCH_SIZE):
        batch = ids[start : start + _ID_BATCH_SIZE]
        placeholders = ",".join("?" * len(batch))
        cursor = await conn.execute(
            f"SELECT * FROM project_solve WHERE project_id IN ({placeholders}) ORDER BY project_id",  # noqa: S608  # nosec B608 - bounded integer ids
            batch,
        )
        result.extend(_geometry(row) for row in await cursor.fetchall())
    return result
