"""Project CRUD + staged image management endpoints."""

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
    ProjectCreate,
    ProjectImageResponse,
    ProjectListItem,
    ProjectResponse,
    ProjectSaveRequest,
    ThumbnailCropResponse,
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


def _staging_dir(project_id: int) -> Path:
    return _projects_root() / ".staging" / str(project_id)


def _permanent_dir(project_id: int) -> Path:
    return _projects_root() / str(project_id)


def _image_dir(base: Path, image_id: int) -> Path:
    return base / f"img_{image_id}"


def _find_rendered(project_id: int, image_id: int, variant: str) -> Path | None:
    """Find a rendered variant on disk — permanent first, staging fallback."""
    fname = f"{variant}.jpg"
    perm = _image_dir(_permanent_dir(project_id), image_id) / fname
    if perm.is_file():
        return perm
    staged = _image_dir(_staging_dir(project_id), image_id) / fname
    if staged.is_file():
        return staged
    return None


# ── row helpers ────────────────────────────────────────────────────────────


def _image_row(d: dict) -> dict:
    bool_fields(d, "is_main", "staged")
    return d


async def _fetch_project_with_images(conn, project_id: int) -> ProjectResponse:
    proj = await get_or_404(conn, "project", project_id, "Project")
    bool_fields(proj, "active")
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

    return ProjectResponse(**proj, images=images, thumbnail_crops=crops)


async def _auto_promote_main(conn, project_id: int) -> None:
    cursor = await conn.execute(
        "SELECT id FROM project_image WHERE project_id = ? AND is_main = 1 AND staged = 0",
        (project_id,),
    )
    if await cursor.fetchone() is not None:
        return
    cursor = await conn.execute(
        "SELECT id FROM project_image WHERE project_id = ? AND staged = 0"
        " ORDER BY display_order, id LIMIT 1",
        (project_id,),
    )
    first = await cursor.fetchone()
    if first is not None:
        await conn.execute(
            "UPDATE project_image SET is_main = 1 WHERE id = ?",
            (first["id"],),
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
               COUNT(CASE WHEN pi.staged = 0 THEN pi.id END) AS image_count,
               MAX(CASE WHEN pi.is_main = 1 AND pi.staged = 0
                        THEN pi.file_path END) AS main_image_path
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
    staging = _staging_dir(project_id)
    if staging.is_dir():
        shutil.rmtree(staging, ignore_errors=True)


# ── Stage images ───────────────────────────────────────────────────────────


@router.post("/{project_id}/images/stage", status_code=201)
async def stage_images(
    project_id: int,
    body: AddImagesRequest,
) -> list[ProjectImageResponse]:
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
                   (project_id, file_path, display_order, is_main, staged)
                   VALUES (?, ?, ?, ?, 1)""",
                (project_id, vpath, next_order + i, is_main),
            )
            created_ids.append(cursor.lastrowid)

        await conn.commit()

        if not created_ids:
            return []

        # Generate pre-calculated images in the staging folder.
        staging = _staging_dir(project_id)
        for img_id, vpath in zip(created_ids, all_paths):
            out_dir = _image_dir(staging, img_id)
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


@router.delete("/{project_id}/images/{image_id}/stage", status_code=204)
async def unstage_image(project_id: int, image_id: int) -> None:
    """Remove a staged image (before Save)."""
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT id, staged FROM project_image WHERE id = ? AND project_id = ?",
            (image_id, project_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")
        if not row["staged"]:
            raise HTTPException(status_code=409, detail="Image is already committed")

        await conn.execute("DELETE FROM project_image WHERE id = ?", (image_id,))
        await conn.commit()

    img_dir = _image_dir(_staging_dir(project_id), image_id)
    if img_dir.is_dir():
        shutil.rmtree(img_dir, ignore_errors=True)


# ── Save (commit) ──────────────────────────────────────────────────────────


@router.post("/{project_id}/save")
async def save_project(project_id: int, body: ProjectSaveRequest) -> ProjectResponse:
    async with get_db() as conn:
        existing = await get_or_404(conn, "project", project_id, "Project")

        name = body.name if body.name is not None else existing["name"]
        description = (
            None
            if body.clear_description
            else (body.description if body.description is not None else existing["description"])
        )
        notes = (
            None
            if body.clear_notes
            else (body.notes if body.notes is not None else existing["notes"])
        )
        status = body.status if body.status is not None else existing["status"]

        if status not in _VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status: {status}")

        await conn.execute(
            """UPDATE project
               SET name = ?, description = ?, notes = ?, status = ?
               WHERE id = ?""",
            (name, description, notes, status, project_id),
        )

        # Remove images marked for deletion.
        perm_dir = _permanent_dir(project_id)
        for rid in body.remove_image_ids or []:
            await conn.execute(
                "DELETE FROM project_image WHERE id = ? AND project_id = ?",
                (rid, project_id),
            )
            img_dir = _image_dir(perm_dir, rid)
            if img_dir.is_dir():
                shutil.rmtree(img_dir, ignore_errors=True)
            staged_dir = _image_dir(_staging_dir(project_id), rid)
            if staged_dir.is_dir():
                shutil.rmtree(staged_dir, ignore_errors=True)

        # Reorder images.
        if body.image_order is not None:
            for idx, img_id in enumerate(body.image_order):
                await conn.execute(
                    "UPDATE project_image SET display_order = ? WHERE id = ? AND project_id = ?",
                    (idx, img_id, project_id),
                )

        # Update main image.
        if body.main_image_id is not None:
            await conn.execute(
                "UPDATE project_image SET is_main = 0 WHERE project_id = ?",
                (project_id,),
            )
            await conn.execute(
                "UPDATE project_image SET is_main = 1 WHERE id = ? AND project_id = ?",
                (body.main_image_id, project_id),
            )

        # Update per-image notes.
        if body.image_notes is not None:
            for img_id, img_notes in body.image_notes.items():
                await conn.execute(
                    "UPDATE project_image SET notes = ? WHERE id = ? AND project_id = ?",
                    (img_notes, int(img_id), project_id),
                )

        # Commit staged images: move files from staging → permanent.
        cursor = await conn.execute(
            "SELECT id FROM project_image WHERE project_id = ? AND staged = 1",
            (project_id,),
        )
        staged_rows = await cursor.fetchall()
        perm_dir.mkdir(parents=True, exist_ok=True)
        for srow in staged_rows:
            src = _image_dir(_staging_dir(project_id), srow["id"])
            dst = _image_dir(perm_dir, srow["id"])
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.move(str(src), str(dst))

        await conn.execute(
            "UPDATE project_image SET staged = 0 WHERE project_id = ? AND staged = 1",
            (project_id,),
        )

        # Save thumbnail crop definitions and generate cropped thumbnails.
        if body.thumbnail_crops:
            for size_name, crop_def in body.thumbnail_crops.items():
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

                source_id = crop_def.source_image_id
                if source_id is None:
                    cursor = await conn.execute(
                        "SELECT id FROM project_image"
                        " WHERE project_id = ? AND is_main = 1 AND staged = 0"
                        " LIMIT 1",
                        (project_id,),
                    )
                    main_row = await cursor.fetchone()
                    if main_row:
                        source_id = main_row["id"]

                if source_id is not None:
                    cursor = await conn.execute(
                        "SELECT file_path FROM project_image WHERE id = ?",
                        (source_id,),
                    )
                    src_row = await cursor.fetchone()
                    if src_row:
                        out_path = perm_dir / f"thumb_crop_{size_name}.jpg"
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

        await _auto_promote_main(conn, project_id)
        await conn.commit()

        # Clean up empty staging dir.
        staging = _staging_dir(project_id)
        if staging.is_dir():
            shutil.rmtree(staging, ignore_errors=True)

        return await _fetch_project_with_images(conn, project_id)


# ── Discard staged changes ─────────────────────────────────────────────────


@router.post("/{project_id}/discard")
async def discard_staging(project_id: int) -> ProjectResponse:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        await conn.execute(
            "DELETE FROM project_image WHERE project_id = ? AND staged = 1",
            (project_id,),
        )
        await conn.commit()

        staging = _staging_dir(project_id)
        if staging.is_dir():
            shutil.rmtree(staging, ignore_errors=True)

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
            "SELECT id FROM project_image WHERE project_id = ? AND is_main = 1 AND staged = 0",
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


# ── Startup cleanup ───────────────────────────────────────────────────────


async def cleanup_orphaned_staging() -> None:
    """Delete staged image rows and staging folders left by interrupted sessions."""
    try:
        async with get_db() as conn:
            await conn.execute("DELETE FROM project_image WHERE staged = 1")
            await conn.commit()
    except Exception:
        logger.warning("Failed to clean staged image rows", exc_info=True)

    root = get_projects_root()
    if root is None:
        return
    staging_root = root / ".staging"
    if staging_root.is_dir():
        shutil.rmtree(staging_root, ignore_errors=True)
        logger.info("[projects] cleaned up orphaned staging folder")
