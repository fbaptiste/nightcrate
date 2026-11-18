"""Shared loading of existing project-thumbnail framing files."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

from nightcrate.core.app_config import get_projects_root
from nightcrate.services.gallery import GalleryCrop
from nightcrate.services.project_images import crop_candidates

_BATCH_SIZE = 500


async def load_project_crops(
    conn, project_ids: Sequence[int]
) -> dict[int, dict[Literal["small", "medium", "large"], GalleryCrop]]:
    """Load saved framings whose generated files still exist, batched by project."""
    unique_ids = list(dict.fromkeys(project_ids))
    if not unique_ids:
        return {}
    projects_root = get_projects_root()
    if projects_root is None:
        return {}

    result: dict[int, dict[Literal["small", "medium", "large"], GalleryCrop]] = defaultdict(dict)
    for start in range(0, len(unique_ids), _BATCH_SIZE):
        batch = unique_ids[start : start + _BATCH_SIZE]
        placeholders = ",".join("?" * len(batch))
        cursor = await conn.execute(
            f"""
            SELECT pt.id, pt.project_id, pt.size,
                   COALESCE(pt.source_image_id, main.id) AS image_id
            FROM project_thumbnail pt
            LEFT JOIN project_image main
              ON main.project_id = pt.project_id AND main.is_main = 1
            WHERE pt.project_id IN ({placeholders})
            ORDER BY pt.project_id, pt.id
            """,  # noqa: S608  # nosec B608 - placeholders built only from ?
            batch,
        )
        for row in await cursor.fetchall():
            image_id = row["image_id"]
            if image_id is None:
                continue
            project_id = int(row["project_id"])
            size = row["size"]
            if not any(
                path.is_file()
                for path in crop_candidates(projects_root / str(project_id), size, int(row["id"]))
            ):
                continue
            result[project_id][size] = GalleryCrop(id=int(row["id"]), image_id=int(image_id))
    return dict(result)
