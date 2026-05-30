"""Project CRUD + image management endpoints (save-as-you-go)."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

from nightcrate.api._common import bool_fields, get_or_404, row_to_dict
from nightcrate.api.project_models import (
    AddImagesRequest,
    ImageNotesUpdate,
    ProjectCreate,
    ProjectImageResponse,
    ProjectListItem,
    ProjectResponse,
    ProjectRigRef,
    ProjectRigsSet,
    ProjectUpdate,
    ReorderImagesRequest,
    ThumbnailCropResponse,
    ThumbnailCropsRequest,
)
from nightcrate.core.app_config import get_projects_root
from nightcrate.db.session import get_db
from nightcrate.services import archive_io, pxiproject_io
from nightcrate.services.project_images import (
    VARIANT_SIZES,
    generate_cropped_thumbnail,
    generate_rendered_images,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Projects"])

_VALID_STATUSES = {"active", "paused", "complete", "abandoned"}
_VALID_SORTS = {"name", "created_at", "updated_at"}
_IMAGE_SUFFIXES = {".fits", ".fit", ".fts", ".xisf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
_VALID_VARIANTS = set(VARIANT_SIZES.keys())
_VALID_THUMB_SIZES = {"small", "medium", "large"}
_THUMB_FALLBACK = {"small": "thumb_sm", "medium": "thumb_md", "large": "thumb_lg"}


# ── path helpers ───────────────────────────────────────────────────────────


def _projects_root() -> Path:
    root = get_projects_root()
    if root is None:
        raise HTTPException(status_code=503, detail="No database configured")
    return root


def _permanent_dir(project_id: int) -> Path:
    return _projects_root() / str(project_id)


def _image_dir(base: Path, image_id: int) -> Path:
    return base / f"img_{image_id}"


def _find_rendered(project_id: int, image_id: int, variant: str) -> Path | None:
    """Find a rendered variant on disk."""
    path = _image_dir(_permanent_dir(project_id), image_id) / f"{variant}.jpg"
    return path if path.is_file() else None


# ── row helpers ────────────────────────────────────────────────────────────


def _image_row(d: dict) -> dict:
    bool_fields(d, "is_main")
    return d


async def _fetch_project_with_images(conn, project_id: int) -> ProjectResponse:
    proj = await get_or_404(conn, "project", project_id, "Project")
    bool_fields(proj, "active")

    location_name: str | None = None
    if proj.get("location_id") is not None:
        cursor = await conn.execute(
            "SELECT name FROM location WHERE id = ?", (proj["location_id"],)
        )
        loc_row = await cursor.fetchone()
        location_name = loc_row["name"] if loc_row else None

    cursor = await conn.execute(
        "SELECT r.id, r.name FROM project_rig pr JOIN rig r ON r.id = pr.rig_id"
        " WHERE pr.project_id = ? ORDER BY r.sort_order, r.name",
        (project_id,),
    )
    rigs = [ProjectRigRef(**row_to_dict(r)) for r in await cursor.fetchall()]

    cursor = await conn.execute(
        "SELECT * FROM project_image WHERE project_id = ? ORDER BY display_order, id",
        (project_id,),
    )
    image_rows = await cursor.fetchall()
    images = [_image_row(row_to_dict(r)) for r in image_rows]

    cursor = await conn.execute(
        "SELECT size, source_image_id, crop_x, crop_y, crop_w, crop_h"
        " FROM project_thumbnail WHERE project_id = ?",
        (project_id,),
    )
    crop_rows = await cursor.fetchall()
    crops = [ThumbnailCropResponse(**row_to_dict(r)) for r in crop_rows]

    return ProjectResponse(
        **proj, location_name=location_name, rigs=rigs, images=images, thumbnail_crops=crops
    )


async def _auto_promote_main(conn, project_id: int) -> None:
    cursor = await conn.execute(
        "SELECT id FROM project_image WHERE project_id = ? AND is_main = 1",
        (project_id,),
    )
    if await cursor.fetchone() is not None:
        return
    cursor = await conn.execute(
        "SELECT id FROM project_image WHERE project_id = ? ORDER BY display_order, id LIMIT 1",
        (project_id,),
    )
    first = await cursor.fetchone()
    if first is not None:
        await conn.execute(
            "UPDATE project_image SET is_main = 1 WHERE id = ?",
            (first["id"],),
        )


async def _generate_crop_file(conn, project_id: int, size_name: str, crop_def) -> None:
    """(Re)generate the cropped thumbnail file for one size. Resolves a NULL
    source image to the project's current main image."""
    source_id = crop_def.source_image_id
    if source_id is None:
        cursor = await conn.execute(
            "SELECT id FROM project_image WHERE project_id = ? AND is_main = 1 LIMIT 1",
            (project_id,),
        )
        main_row = await cursor.fetchone()
        if main_row:
            source_id = main_row["id"]

    if source_id is None:
        return

    cursor = await conn.execute(
        "SELECT file_path FROM project_image WHERE id = ? AND project_id = ?",
        (source_id, project_id),
    )
    src_row = await cursor.fetchone()
    if not src_row:
        return

    out_path = _permanent_dir(project_id) / f"thumb_crop_{size_name}.jpg"
    try:
        await asyncio.to_thread(
            generate_cropped_thumbnail,
            src_row["file_path"],
            crop_def.crop_x,
            crop_def.crop_y,
            crop_def.crop_w,
            crop_def.crop_h,
            out_path,
            size_name,
        )
    except Exception:
        logger.warning(
            "Cropped thumbnail generation failed for project %d size %s",
            project_id,
            size_name,
            exc_info=True,
        )


# ── enumerate helper ───────────────────────────────────────────────────────


def _enumerate_paths(file_path: str) -> list[str]:
    p = Path(file_path)

    if p.suffix.lower() == ".pxiproject" or (p.is_dir() and (p / "project.xosm").exists()):
        try:
            imgs = pxiproject_io.list_project_images(p)
            return [f"{file_path}::{img['index']}" for img in imgs]
        except Exception:
            logger.warning("Failed to enumerate pxiproject: %s", file_path)
            return [file_path]

    if archive_io.is_archive(p):
        try:
            entries = archive_io.list_contents(p)
            paths = []
            for entry in entries:
                if entry["type"] != "file":
                    continue
                ext = Path(entry["name"]).suffix.lower()
                if ext in _IMAGE_SUFFIXES:
                    paths.append(f"{file_path}::{entry['name']}")
            return paths if paths else [file_path]
        except Exception:
            logger.warning("Failed to enumerate archive: %s", file_path)
            return [file_path]

    return [file_path]


# ── Project CRUD ────────────────────────────────────────────────────────────


@router.get("")
async def list_projects(
    q: str | None = Query(None, description="Search name and description"),
    sort: str = Query("updated_at", description="Sort field: name, created_at, updated_at"),
    desc: bool = Query(True, description="Sort descending"),
    include_retired: bool = Query(False),
) -> list[ProjectListItem]:
    if sort not in _VALID_SORTS:
        sort = "updated_at"
    direction = "DESC" if desc else "ASC"

    conditions: list[str] = []
    params: list[str | int] = []

    if not include_retired:
        conditions.append("p.active = 1")

    if q:
        conditions.append("(p.name LIKE ? OR p.description LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = f"""
        SELECT p.*,
               COUNT(pi.id) AS image_count,
               MAX(CASE WHEN pi.is_main = 1 THEN pi.file_path END) AS main_image_path
        FROM project p
        LEFT JOIN project_image pi ON pi.project_id = p.id
        {where}
        GROUP BY p.id
        ORDER BY p.{sort} {direction}
    """  # nosec B608

    async with get_db() as conn:
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()

    items = []
    for r in rows:
        d = row_to_dict(r)
        bool_fields(d, "active")
        items.append(ProjectListItem(**d))
    return items


@router.post("", status_code=201)
async def create_project(body: ProjectCreate) -> ProjectResponse:
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status: {body.status}")

    async with get_db() as conn:
        cursor = await conn.execute(
            "INSERT INTO project (name, description, notes, status) VALUES (?, ?, ?, ?)",
            (body.name, body.description, body.notes, body.status),
        )
        project_id = cursor.lastrowid
        await conn.commit()
        return await _fetch_project_with_images(conn, project_id)


@router.get("/{project_id}")
async def get_project(project_id: int) -> ProjectResponse:
    async with get_db() as conn:
        return await _fetch_project_with_images(conn, project_id)


@router.patch("/{project_id}")
async def update_project(project_id: int, body: ProjectUpdate) -> ProjectResponse:
    """Partial metadata update. Only fields present in the body are changed;
    empty description/notes clear them."""
    fields = body.model_dump(exclude_unset=True)

    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")

        sets: list[str] = []
        params: list[str | None] = []

        if "name" in fields:
            name = (fields["name"] or "").strip()
            if not name:
                raise HTTPException(status_code=422, detail="Name cannot be empty")
            sets.append("name = ?")
            params.append(name)
        if "description" in fields:
            sets.append("description = ?")
            params.append(fields["description"] or None)
        if "notes" in fields:
            sets.append("notes = ?")
            params.append(fields["notes"] or None)
        if "status" in fields:
            status = fields["status"]
            if status not in _VALID_STATUSES:
                raise HTTPException(status_code=422, detail=f"Invalid status: {status}")
            sets.append("status = ?")
            params.append(status)
        if "location_id" in fields:
            location_id = fields["location_id"]
            if location_id is not None:
                await get_or_404(conn, "location", location_id, "Location")
            sets.append("location_id = ?")
            params.append(location_id)

        if sets:
            params.append(project_id)
            await conn.execute(
                f"UPDATE project SET {', '.join(sets)} WHERE id = ?",  # nosec B608 - column names internal
                params,
            )
            await conn.commit()

        return await _fetch_project_with_images(conn, project_id)


@router.put("/{project_id}/rigs")
async def set_project_rigs(project_id: int, body: ProjectRigsSet) -> ProjectResponse:
    """Replace the full set of rigs associated with a project."""
    rig_ids = list(dict.fromkeys(body.rig_ids))  # dedupe, preserve order

    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        for rig_id in rig_ids:
            await get_or_404(conn, "rig", rig_id, "Rig")

        await conn.execute("DELETE FROM project_rig WHERE project_id = ?", (project_id,))
        for rig_id in rig_ids:
            await conn.execute(
                "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
                (project_id, rig_id),
            )
        await conn.commit()
        return await _fetch_project_with_images(conn, project_id)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int) -> None:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        await conn.execute("UPDATE project SET active = 0 WHERE id = ?", (project_id,))
        await conn.commit()


@router.post("/{project_id}/restore")
async def restore_project(project_id: int) -> ProjectResponse:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        await conn.execute("UPDATE project SET active = 1 WHERE id = ?", (project_id,))
        await conn.commit()
        return await _fetch_project_with_images(conn, project_id)


@router.delete("/{project_id}/permanent", status_code=204)
async def permanently_delete_project(project_id: int) -> None:
    """Hard-delete a project, its images, and all on-disk files."""
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        await conn.execute("DELETE FROM project WHERE id = ?", (project_id,))
        await conn.commit()

    perm = _permanent_dir(project_id)
    if perm.is_dir():
        shutil.rmtree(perm, ignore_errors=True)


# ── Images ─────────────────────────────────────────────────────────────────


@router.post("/{project_id}/images", status_code=201)
async def add_images(
    project_id: int,
    body: AddImagesRequest,
) -> list[ProjectImageResponse]:
    """Add image(s) to a project. Images persist immediately; their preview
    variants are pre-rendered before the response returns."""
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")

        cursor = await conn.execute(
            "SELECT COALESCE(MAX(display_order), -1) FROM project_image WHERE project_id = ?",
            (project_id,),
        )
        row = await cursor.fetchone()
        next_order = (row[0] if row else -1) + 1

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM project_image WHERE project_id = ?",
            (project_id,),
        )
        existing_count = (await cursor.fetchone())[0]

        all_paths: list[str] = []
        for fp in body.file_paths:
            all_paths.extend(await asyncio.to_thread(_enumerate_paths, fp))

        created_ids: list[int] = []
        for i, vpath in enumerate(all_paths):
            is_main = 1 if (existing_count == 0 and i == 0) else 0
            cursor = await conn.execute(
                """INSERT INTO project_image
                   (project_id, file_path, display_order, is_main)
                   VALUES (?, ?, ?, ?)""",
                (project_id, vpath, next_order + i, is_main),
            )
            created_ids.append(cursor.lastrowid)

        await conn.commit()

        if not created_ids:
            return []

        # Pre-render preview variants straight into the permanent folder.
        perm = _permanent_dir(project_id)
        for img_id, vpath in zip(created_ids, all_paths):
            out_dir = _image_dir(perm, img_id)
            try:
                await asyncio.to_thread(generate_rendered_images, vpath, out_dir)
            except Exception:
                logger.warning("Pre-calc failed for %s", vpath, exc_info=True)

        placeholders = ",".join("?" * len(created_ids))
        cursor = await conn.execute(
            f"SELECT * FROM project_image WHERE id IN ({placeholders}) ORDER BY display_order",  # nosec B608
            created_ids,
        )
        rows = await cursor.fetchall()
        return [ProjectImageResponse(**_image_row(row_to_dict(r))) for r in rows]


@router.delete("/{project_id}/images/{image_id}", status_code=204)
async def remove_image(project_id: int, image_id: int) -> None:
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT id FROM project_image WHERE id = ? AND project_id = ?",
            (image_id, project_id),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")

        # Capture which cropped thumbnails this image sourced (their files
        # become stale once it's gone; the FK nulls source_image_id).
        cursor = await conn.execute(
            "SELECT size FROM project_thumbnail WHERE project_id = ? AND source_image_id = ?",
            (project_id, image_id),
        )
        stale_sizes = [r["size"] for r in await cursor.fetchall()]

        await conn.execute(
            "DELETE FROM project_image WHERE id = ? AND project_id = ?",
            (image_id, project_id),
        )
        await _auto_promote_main(conn, project_id)
        await conn.commit()

    perm = _permanent_dir(project_id)
    img_dir = _image_dir(perm, image_id)
    if img_dir.is_dir():
        shutil.rmtree(img_dir, ignore_errors=True)
    for size in stale_sizes:
        (perm / f"thumb_crop_{size}.jpg").unlink(missing_ok=True)


@router.put("/{project_id}/images/order")
async def reorder_images(project_id: int, body: ReorderImagesRequest) -> ProjectResponse:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        for idx, img_id in enumerate(body.image_ids):
            await conn.execute(
                "UPDATE project_image SET display_order = ? WHERE id = ? AND project_id = ?",
                (idx, img_id, project_id),
            )
        await conn.commit()
        return await _fetch_project_with_images(conn, project_id)


@router.post("/{project_id}/images/{image_id}/main")
async def set_main_image(project_id: int, image_id: int) -> ProjectResponse:
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT id FROM project_image WHERE id = ? AND project_id = ?",
            (image_id, project_id),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")

        await conn.execute(
            "UPDATE project_image SET is_main = 0 WHERE project_id = ?",
            (project_id,),
        )
        await conn.execute(
            "UPDATE project_image SET is_main = 1 WHERE id = ?",
            (image_id,),
        )
        await conn.commit()
        return await _fetch_project_with_images(conn, project_id)


@router.patch("/{project_id}/images/{image_id}")
async def update_image_notes(
    project_id: int, image_id: int, body: ImageNotesUpdate
) -> ProjectImageResponse:
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT id FROM project_image WHERE id = ? AND project_id = ?",
            (image_id, project_id),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")

        await conn.execute(
            "UPDATE project_image SET notes = ? WHERE id = ?",
            (body.notes or None, image_id),
        )
        await conn.commit()

        cursor = await conn.execute("SELECT * FROM project_image WHERE id = ?", (image_id,))
        row = await cursor.fetchone()
        return ProjectImageResponse(**_image_row(row_to_dict(row)))


# ── Thumbnail crops ────────────────────────────────────────────────────────


@router.put("/{project_id}/thumbnails")
async def save_thumbnail_crops(project_id: int, body: ThumbnailCropsRequest) -> ProjectResponse:
    """Save thumbnail crop definitions and regenerate the cropped files."""
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")

        for size_name, crop_def in body.crops.items():
            if size_name not in _VALID_THUMB_SIZES:
                continue
            await conn.execute(
                """INSERT INTO project_thumbnail
                   (project_id, size, source_image_id, crop_x, crop_y, crop_w, crop_h)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (project_id, size) DO UPDATE SET
                       source_image_id = excluded.source_image_id,
                       crop_x = excluded.crop_x,
                       crop_y = excluded.crop_y,
                       crop_w = excluded.crop_w,
                       crop_h = excluded.crop_h""",
                (
                    project_id,
                    size_name,
                    crop_def.source_image_id,
                    crop_def.crop_x,
                    crop_def.crop_y,
                    crop_def.crop_w,
                    crop_def.crop_h,
                ),
            )
            await _generate_crop_file(conn, project_id, size_name, crop_def)

        await conn.commit()
        return await _fetch_project_with_images(conn, project_id)


# ── Rendered image serving ─────────────────────────────────────────────────


@router.get("/{project_id}/images/{image_id}/rendered/{variant}")
async def get_rendered_image(project_id: int, image_id: int, variant: str) -> Response:
    if variant not in _VALID_VARIANTS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid variant: {variant}. Must be one of {sorted(_VALID_VARIANTS)}",
        )

    path = _find_rendered(project_id, image_id, variant)
    if path is None:
        return Response(status_code=204)

    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ── Project list thumbnail ─────────────────────────────────────────────────


@router.get("/{project_id}/thumbnail")
async def get_thumbnail(
    project_id: int,
    size: str = Query("small", description="Thumbnail size: small, medium, large"),
) -> Response:
    if size not in _VALID_THUMB_SIZES:
        size = "small"

    cropped = _permanent_dir(project_id) / f"thumb_crop_{size}.jpg"
    if cropped.is_file():
        return FileResponse(
            cropped,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT id FROM project_image WHERE project_id = ? AND is_main = 1",
            (project_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        return Response(status_code=204)

    fallback_variant = _THUMB_FALLBACK.get(size, "thumb_sm")
    path = _find_rendered(project_id, row["id"], fallback_variant)
    if path is None:
        return Response(status_code=204)

    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )
