"""Project CRUD + image management endpoints (save-as-you-go)."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
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
    ProjectSoftwareRef,
    ProjectSoftwareSet,
    ProjectUpdate,
    ReorderImagesRequest,
    ThumbnailCropDef,
    ThumbnailCropResponse,
    ThumbnailCropsRequest,
)
from nightcrate.core.app_config import get_projects_root
from nightcrate.db.session import get_db, workspace_key
from nightcrate.services import archive_io, pixel_loader, pxiproject_io, xisf_io
from nightcrate.services.project_images import (
    VARIANT_SIZES,
    CropFrameError,
    crop_path,
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
        "SELECT r.id, r.name, r.active FROM project_rig pr JOIN rig r ON r.id = pr.rig_id"
        " WHERE pr.project_id = ? ORDER BY r.sort_order, r.name",
        (project_id,),
    )
    rigs = []
    for row in await cursor.fetchall():
        value = row_to_dict(row)
        bool_fields(value, "active")
        rigs.append(ProjectRigRef(**value))

    cursor = await conn.execute(
        """
        SELECT ps.id, ps.software_id, s.name, s.category,
               m.name AS manufacturer_name, ps.software_version_id,
               sv.version, s.active
        FROM project_software ps
        JOIN software s ON s.id = ps.software_id
        LEFT JOIN manufacturer m ON m.id = s.manufacturer_id
        LEFT JOIN software_version sv ON sv.id = ps.software_version_id
        WHERE ps.project_id = ?
        ORDER BY ps.sort_order, ps.id
        """,
        (project_id,),
    )
    software = []
    for row in await cursor.fetchall():
        value = row_to_dict(row)
        bool_fields(value, "active")
        software.append(ProjectSoftwareRef(**value))

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

    cursor = await conn.execute(
        "SELECT solved_at FROM project_solve WHERE project_id = ?", (project_id,)
    )
    solve_row = await cursor.fetchone()

    return ProjectResponse(
        **proj,
        location_name=location_name,
        rigs=rigs,
        software=software,
        images=images,
        thumbnail_crops=crops,
        solved_at=solve_row["solved_at"] if solve_row is not None else None,
        workspace_key=workspace_key(),
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


async def _generate_crop_file(source_path: str, size_name: str, crop_def, out_path: Path) -> None:
    """Generate one crop off the event loop, propagating failures to the caller."""
    await asyncio.to_thread(
        generate_cropped_thumbnail,
        source_path,
        crop_def.crop_x,
        crop_def.crop_y,
        crop_def.crop_w,
        crop_def.crop_h,
        out_path,
        size_name,
    )


def _delete_crop_files(project_id: int, crops: list[tuple[int, str]]) -> None:
    """Best-effort cleanup after the corresponding database change commits."""
    project_folder = _permanent_dir(project_id)
    for row_id, size in crops:
        current = crop_path(project_folder, size, row_id)
        legacy = project_folder / f"thumb_crop_{size}.jpg"
        for path in (current, legacy):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Couldn't remove obsolete project crop %s", path, exc_info=True)


def _delete_paths(paths: list[Path]) -> None:
    """Best-effort removal that preserves the error which triggered cleanup."""
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Couldn't remove temporary project crop %s", path, exc_info=True)


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


def _verify_project_image(path: str) -> None:
    """Verify XISF pixels behind a project-image path before DB insertion."""
    lower_path = path.lower()
    if not lower_path.endswith(".xisf") and ".pxiproject::" not in lower_path:
        return
    try:
        source, file_type, image_index = pixel_loader.resolve(path)
    except xisf_io.XISFError as exc:
        name = Path(path.rsplit("::", 1)[-1]).name
        raise _ProjectImageXISFError(name, str(exc)) from exc
    except Exception:
        # Verification is additive validation. Preserve the prior save-and-render
        # behavior when a path is missing or a virtual reference cannot resolve.
        return
    if file_type == "xisf":
        try:
            xisf_io.verify_image(source)
        except xisf_io.XISFError as exc:
            raise _ProjectImageXISFError(Path(path.rsplit("::", 1)[-1]).name, str(exc)) from exc
        return
    if file_type != "pxiproject":
        return
    try:
        entry = pxiproject_io.list_project_images(source)[image_index]
    except xisf_io.XISFError as exc:
        raise _ProjectImageXISFError(Path(path).name, str(exc)) from exc
    except Exception:
        return
    if entry["source"] != "referenced" or not entry["file_path"]:
        return
    referenced = Path(entry["file_path"])
    if referenced.suffix.lower() == ".xisf":
        try:
            xisf_io.verify_image(referenced)
        except xisf_io.XISFError as exc:
            raise _ProjectImageXISFError(referenced.name, str(exc)) from exc


class _ProjectImageXISFError(ValueError):
    def __init__(self, name: str, message: str) -> None:
        super().__init__(message)
        self.name = name


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
               MAX(CASE WHEN pi.is_main = 1 THEN pi.file_path END) AS main_image_path,
               MAX(CASE WHEN pi.is_main = 1 THEN pi.id END) AS _main_image_id,
               (SELECT pt.id FROM project_thumbnail pt
                WHERE pt.project_id = p.id AND pt.size = 'small') AS _crop_small_id,
               (SELECT pt.id FROM project_thumbnail pt
                WHERE pt.project_id = p.id AND pt.size = 'medium') AS _crop_medium_id,
               (SELECT pt.id FROM project_thumbnail pt
                WHERE pt.project_id = p.id AND pt.size = 'large') AS _crop_large_id
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
        main_id = d.pop("_main_image_id")
        small_id = d.pop("_crop_small_id")
        medium_id = d.pop("_crop_medium_id")
        large_id = d.pop("_crop_large_id")
        d["thumbnail_version"] = (
            f"{main_id if main_id is not None else '-'}"
            f".s{small_id if small_id is not None else '-'}"
            f".m{medium_id if medium_id is not None else '-'}"
            f".l{large_id if large_id is not None else '-'}"
        )
        d["workspace_key"] = workspace_key()
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


@router.put("/{project_id}/software")
async def set_project_software(project_id: int, body: ProjectSoftwareSet) -> ProjectResponse:
    """Replace a project's ordered software/version list."""
    pairs = [(entry.software_id, entry.software_version_id) for entry in body.entries]
    if len(pairs) != len(set(pairs)):
        raise HTTPException(
            status_code=422, detail="The same software and version may appear only once"
        )

    async with get_db() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await get_or_404(conn, "project", project_id, "Project")
            for entry in body.entries:
                cursor = await conn.execute(
                    "SELECT id FROM software WHERE id = ?", (entry.software_id,)
                )
                if await cursor.fetchone() is None:
                    raise HTTPException(status_code=422, detail="Software not found")
                if entry.software_version_id is not None:
                    cursor = await conn.execute(
                        "SELECT id FROM software_version WHERE id = ? AND software_id = ?",
                        (entry.software_version_id, entry.software_id),
                    )
                    if await cursor.fetchone() is None:
                        raise HTTPException(
                            status_code=422,
                            detail="Software version does not belong to this program",
                        )
            await conn.execute("DELETE FROM project_software WHERE project_id = ?", (project_id,))
            await conn.executemany(
                "INSERT INTO project_software "
                "(project_id, software_id, software_version_id, sort_order) "
                "VALUES (?, ?, ?, ?)",
                [
                    (project_id, entry.software_id, entry.software_version_id, index)
                    for index, entry in enumerate(body.entries)
                ],
            )
            await conn.commit()
            return await _fetch_project_with_images(conn, project_id)
        except HTTPException:
            await conn.rollback()
            raise
        except Exception as exc:
            await conn.rollback()
            logger.exception("[software] failed to save project %d software", project_id)
            raise HTTPException(status_code=500, detail="Failed to save project software") from exc
        except BaseException:
            await conn.rollback()
            raise


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

        for vpath in all_paths:
            try:
                await asyncio.to_thread(_verify_project_image, vpath)
            except _ProjectImageXISFError as exc:
                raise HTTPException(status_code=422, detail=f"{exc.name}: {exc}") from exc

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
        await conn.execute("BEGIN IMMEDIATE")
        cursor = await conn.execute(
            "SELECT id, is_main FROM project_image WHERE id = ? AND project_id = ?",
            (image_id, project_id),
        )
        image_row = await cursor.fetchone()
        if image_row is None:
            raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")

        # Delete named crops before the image so ON DELETE SET NULL cannot turn
        # them into follow-main crops. If the main changes, its follow-main
        # crops are invalid too because their fractions belong to this picture.
        cursor = await conn.execute(
            "SELECT id, size FROM project_thumbnail"
            " WHERE project_id = ? AND (source_image_id = ?"
            " OR (? = 1 AND source_image_id IS NULL))",
            (project_id, image_id, image_row["is_main"]),
        )
        stale_crops = [(r["id"], r["size"]) for r in await cursor.fetchall()]
        if stale_crops:
            placeholders = ",".join("?" * len(stale_crops))
            await conn.execute(
                f"DELETE FROM project_thumbnail WHERE id IN ({placeholders})",  # nosec B608
                [row_id for row_id, _ in stale_crops],
            )

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
    _delete_crop_files(project_id, stale_crops)


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
        await conn.execute("BEGIN IMMEDIATE")
        cursor = await conn.execute(
            "SELECT id FROM project_image WHERE id = ? AND project_id = ?",
            (image_id, project_id),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")

        cursor = await conn.execute(
            "SELECT id FROM project_image WHERE project_id = ? AND is_main = 1",
            (project_id,),
        )
        current_main = await cursor.fetchone()
        main_changes = current_main is None or current_main["id"] != image_id
        stale_crops: list[tuple[int, str]] = []
        if main_changes:
            cursor = await conn.execute(
                "SELECT id, size FROM project_thumbnail"
                " WHERE project_id = ? AND source_image_id IS NULL",
                (project_id,),
            )
            stale_crops = [(r["id"], r["size"]) for r in await cursor.fetchall()]
            await conn.execute(
                "DELETE FROM project_thumbnail WHERE project_id = ? AND source_image_id IS NULL",
                (project_id,),
            )

        await conn.execute(
            "UPDATE project_image SET is_main = 0 WHERE project_id = ?",
            (project_id,),
        )
        await conn.execute(
            "UPDATE project_image SET is_main = 1 WHERE id = ?",
            (image_id,),
        )
        await conn.commit()
        project = await _fetch_project_with_images(conn, project_id)

    _delete_crop_files(project_id, stale_crops)
    return project


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
    """Generate and publish a complete set of requested crop generations."""
    requested = [
        (size_name, crop_def)
        for size_name, crop_def in body.crops.items()
        if size_name in _VALID_THUMB_SIZES
    ]

    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")

        if not requested:
            return await _fetch_project_with_images(conn, project_id)

        cursor = await conn.execute(
            "SELECT id FROM project_image WHERE project_id = ? AND is_main = 1",
            (project_id,),
        )
        main_row = await cursor.fetchone()
        if main_row is None:
            raise HTTPException(status_code=422, detail="This project has no main image to crop.")
        initial_main_id = main_row["id"]

        resolved: list[tuple[str, ThumbnailCropDef, str]] = []
        for size_name, crop_def in requested:
            source_id = (
                initial_main_id if crop_def.source_image_id is None else crop_def.source_image_id
            )
            cursor = await conn.execute(
                "SELECT file_path FROM project_image WHERE id = ? AND project_id = ?",
                (source_id, project_id),
            )
            source_row = await cursor.fetchone()
            if source_row is None:
                raise HTTPException(
                    status_code=422, detail=f"Image {source_id} isn't in this project."
                )
            resolved.append((size_name, crop_def, source_row["file_path"]))

        permanent_dir = _permanent_dir(project_id)
        permanent_dir.mkdir(parents=True, exist_ok=True)
        temporary: dict[str, Path] = {}
        try:
            for size_name, crop_def, source_path in resolved:
                with tempfile.NamedTemporaryFile(
                    prefix=f".thumb_crop_{size_name}_",
                    suffix=".tmp",
                    dir=permanent_dir,
                    delete=False,
                ) as temp_file:
                    temp_path = Path(temp_file.name)
                    temporary[size_name] = temp_path
                try:
                    await _generate_crop_file(source_path, size_name, crop_def, temp_path)
                except CropFrameError as exc:
                    source_name = Path(source_path).name
                    raise HTTPException(
                        status_code=422,
                        detail=f"The {size_name} frame doesn't fit {source_name}: {exc}",
                    ) from exc
                except Exception as exc:
                    source_name = Path(source_path).name
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"Couldn't make the {size_name} thumbnail from {source_name}: {exc}"
                        ),
                    ) from exc
        except HTTPException:
            _delete_paths(list(temporary.values()))
            raise
        except Exception as exc:
            _delete_paths(list(temporary.values()))
            logger.exception("Couldn't stage thumbnails for project %d", project_id)
            raise HTTPException(
                status_code=500, detail=f"Couldn't save the thumbnails: {exc}"
            ) from exc

        new_files: list[Path] = []
        orphan_files: list[Path] = []
        try:
            await conn.execute("BEGIN IMMEDIATE")

            if any(crop_def.source_image_id is None for _, crop_def, _ in resolved):
                cursor = await conn.execute(
                    "SELECT id FROM project_image WHERE project_id = ? AND is_main = 1",
                    (project_id,),
                )
                current_main = await cursor.fetchone()
                if current_main is None or current_main["id"] != initial_main_id:
                    raise HTTPException(
                        status_code=409,
                        detail="The main image changed while saving. Try again.",
                    )

            for size_name, crop_def, _ in resolved:
                cursor = await conn.execute(
                    "SELECT id FROM project_thumbnail WHERE project_id = ? AND size = ?",
                    (project_id, size_name),
                )
                old_row = await cursor.fetchone()
                if old_row is not None:
                    await conn.execute(
                        "DELETE FROM project_thumbnail WHERE id = ?", (old_row["id"],)
                    )

                cursor = await conn.execute(
                    """INSERT INTO project_thumbnail
                       (project_id, size, source_image_id, crop_x, crop_y, crop_w, crop_h)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
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
                row_id = cursor.lastrowid
                if row_id is None:
                    raise RuntimeError("No thumbnail generation id was returned")
                new_path = crop_path(permanent_dir, size_name, row_id)
                temporary[size_name].rename(new_path)
                new_files.append(new_path)

            cursor = await conn.execute(
                "SELECT id, size FROM project_thumbnail WHERE project_id = ?", (project_id,)
            )
            owned_files = {
                crop_path(permanent_dir, row["size"], row["id"]).name
                for row in await cursor.fetchall()
            }
            orphan_files = [
                path
                for path in permanent_dir.glob("thumb_crop_*.jpg")
                if path.name not in owned_files
            ]
            await conn.commit()
        except HTTPException:
            try:
                await conn.rollback()
            except Exception:
                logger.exception("Couldn't roll back rejected project crop save")
            _delete_paths([*temporary.values(), *new_files])
            raise
        except Exception as exc:
            try:
                await conn.rollback()
            except Exception:
                logger.exception("Couldn't roll back failed project crop save")
            _delete_paths([*temporary.values(), *new_files])
            logger.exception("Couldn't save thumbnails for project %d", project_id)
            raise HTTPException(
                status_code=500, detail=f"Couldn't save the thumbnails: {exc}"
            ) from exc

        _delete_paths(orphan_files)
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
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


# ── Project list thumbnail ─────────────────────────────────────────────────


@router.get("/{project_id}/thumbnail")
async def get_thumbnail(
    project_id: int,
    size: str = Query("small", description="Thumbnail size: small, medium, large"),
) -> Response:
    if size not in _VALID_THUMB_SIZES:
        size = "small"

    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT id FROM project_thumbnail WHERE project_id = ? AND size = ?",
            (project_id, size),
        )
        crop_row = await cursor.fetchone()
        if crop_row is not None:
            cropped = crop_path(_permanent_dir(project_id), size, crop_row["id"])
            if cropped.is_file():
                return FileResponse(
                    cropped,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"},
                )

        cursor = await conn.execute(
            "SELECT id FROM project_image WHERE project_id = ? AND is_main = 1",
            (project_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    fallback_variant = _THUMB_FALLBACK.get(size, "thumb_sm")
    path = _find_rendered(project_id, row["id"], fallback_variant)
    if path is None:
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )
