"""Directory-scan ingest pipeline + catalog endpoints (v0.40.0, v0.41.1).

The HTTP/DB boundary for cataloging a folder. Orchestrates:

    scan (fast walk) -> ProcessPool header parse
    -> content-hash UPSERT into sub_frame / processed_image / file_location
    -> session formation -> light-to-target assignment
    -> ingestion_run counters

Frames are cataloged from their FITS headers alone. There is deliberately no
automatic equipment identification (v0.41.1 removed the header-to-equipment
resolver and the rig-attribution pass): a project carries its rigs via
project_rig, and that is the equipment context. ``sub_frame.filter_name_hint``
holds the header's filter name and is the only filter fact.

Ingest also never writes ``project_session`` — building the user-facing session
list from these frames is an explicit action on the Sessions tab
(``services/session_derivation.py``).

This module owns the transaction; the pure services (ingest_scanner,
ingest_classify, ingest_sessions) never commit. One ingest runs at a time per
process (global single-flight, 409 if busy).

Catalog endpoints are read-only except for the frame-classification corrections
(frame type + target, single and bulk).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import get_args

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

from nightcrate.api._common import bool_fields, get_or_404, row_to_dict
from nightcrate.core import app_config
from nightcrate.core.compute import effective_worker_count
from nightcrate.core.config import get_settings
from nightcrate.db.session import get_db
from nightcrate.services.catalog_thumbnail import DEFAULT_MAX_PX, render_thumbnail_bytes
from nightcrate.services.fits_header_map import extract_metadata
from nightcrate.services.frame_quality import analyze_frame_file, wants_stars
from nightcrate.services.ingest_classify import (
    CATEGORY_LOG,
    CATEGORY_OTHER,
    CATEGORY_PROCESSED,
    CATEGORY_PXIPROJECT,
    classify_frame,
)
from nightcrate.services.ingest_models import (
    BulkCorrectionResult,
    BulkFrameCorrection,
    CatalogDeleteRequest,
    CatalogDeleteResult,
    CatalogFilterStat,
    CatalogFrame,
    CatalogFramesPage,
    CatalogMaster,
    CatalogMastersPage,
    CatalogOther,
    CatalogOthersPage,
    CatalogSummary,
    CorrectableField,
    FrameCorrection,
    FrameTypeName,
    IngestStatus,
    QualityAnalyzeRequest,
    QualityAnalyzeResult,
    QualityCounts,
    QualityPending,
    SourceFolder,
    SourceFolderCreate,
    SourceFolderUpdate,
)
from nightcrate.services.ingest_scanner import (
    header_bearing,
    make_pool,
    parse_image_file,
    scan_directory,
)
from nightcrate.services.ingest_sessions import (
    assign_rigs_and_sessions,
    folder_prefix,
    project_geo_timezone,
)
from nightcrate.services.line_names import canonicalize_line_name

logger = logging.getLogger("nightcrate.ingest")
_LOG_PREFIX = "[ingest]"
_QUALITY_PREFIX = "[frame-quality]"

# Module-level tuple: ruff format strips parens from inline ``except (A, B):`` on
# py3.14, producing invalid Py2 syntax. Referencing a constant sidesteps it.
_COERCE_ERRORS = (TypeError, ValueError)

# Arcsec per pixel for a frame, as a SQL expression over the joins in
# _FRAME_SELECT. 206.265 converts (micron / millimetre) to arcseconds.
#
# HFR is measured and stored in PIXELS, which is only comparable within one rig —
# the same seeing reads 6 px at 1960 mm and 2 px at 600 mm. Multiplying by this
# gives the angular figure, which IS comparable, and is what an astrophotographer
# actually means by "how good was the seeing".
#
# Precedence: a plate-solved / header pixel scale on the frame wins, because it
# was measured on the sky. Otherwise derive it from the rig the user tagged.
# Binning multiplies the effective pixel pitch. NULL when the rig is untagged or
# its optics/camera are incomplete — the UI then shows pixels, never a guess.
_PIXEL_SCALE_SQL = (
    "COALESCE(sf.pixel_scale_arcsec, "
    "206.265 * sen.pixel_size_um * COALESCE(sf.binning_x, 1) "
    "/ NULLIF(tc.effective_focal_length_mm, 0))"
)

# Allow-list of catalog sort orders (v0.41.3). The values are interpolated into
# SQL, so this dict is the only thing that may ever reach an ORDER BY — a caller's
# string is looked up here, never used. ``x IS NULL`` first in every key sorts
# unanalyzed frames last regardless of direction, matching the app-wide rule that
# blanks sort last.
_FRAME_SORTS = {
    "path": "ORDER BY fl.path, sf.date_obs_utc, sf.id",
    "date": "ORDER BY sf.date_obs_utc, sf.id",
    # Worst focus/seeing first — the point of the quality pass.
    # Pixels: right within one rig, misleading across two — a long focal length
    # inflates every frame's figure. The arcsec orders below are the honest ones
    # for a multi-rig project, and fall back to pixels when the scale is unknown.
    "hfr_desc": "ORDER BY sf.hfr IS NULL, sf.hfr DESC, fl.path, sf.id",
    "hfr_asc": "ORDER BY sf.hfr IS NULL, sf.hfr ASC, fl.path, sf.id",
    "hfr_arcsec_desc": (
        f"ORDER BY sf.hfr IS NULL, sf.hfr * COALESCE({_PIXEL_SCALE_SQL}, 1) DESC, fl.path, sf.id"
    ),
    "hfr_arcsec_asc": (
        f"ORDER BY sf.hfr IS NULL, sf.hfr * COALESCE({_PIXEL_SCALE_SQL}, 1) ASC, fl.path, sf.id"
    ),
    # Fewest stars first — clouds, dew, or a frame that lost the target.
    "stars_asc": "ORDER BY sf.star_count IS NULL, sf.star_count ASC, fl.path, sf.id",
    "stars_desc": "ORDER BY sf.star_count IS NULL, sf.star_count DESC, fl.path, sf.id",
    # Brightest sky first — moon, twilight, or light pollution creeping in.
    "background_desc": (
        "ORDER BY sf.background_adu IS NULL, sf.background_adu DESC, fl.path, sf.id"
    ),
}

router = APIRouter(prefix="/api/projects", tags=["Projects"])

# Single-flight guard: at most one ingest run in flight per process.
_INGEST_LOCK = asyncio.Lock()

# Separate from _INGEST_LOCK: the quality pass reads files and writes only the
# quality columns, so it need not queue behind a folder re-scan (and vice versa).
# Each is still single-flight against itself.
_ANALYZE_LOCK = asyncio.Lock()

# Bound concurrent thumbnail renders so a grid drawing many cells can't stampede
# the loader (each render still reads a file). Renders run in a thread; results
# are cached on disk by content hash, so this only gates first-time renders.
_THUMB_SEM = asyncio.Semaphore(3)


def _thumb_cache_dir() -> Path:
    # Read APP_DIR at call time so the test harness's monkeypatch is honored.
    return app_config.APP_DIR / "catalog_thumbnails"


# ── Source-folder binding ─────────────────────────────────────────────────────


_FOLDER_SELECT = (
    "SELECT psf.*, r.name AS rig_name, "
    "COALESCE(d.common_name, d.primary_designation) AS target_name "
    "FROM project_source_folder psf "
    "LEFT JOIN rig r ON r.id = psf.rig_id "
    "LEFT JOIN project_target pt ON pt.id = psf.project_target_id "
    "LEFT JOIN dso d ON d.id = pt.dso_id "
)


async def _validate_folder_target(conn, project_id: int, target_id: int | None) -> None:
    """422 unless *target_id* is one of this project's own targets.

    Scoped, not just existence-checked: project_target ids are global, so a bare
    FK check would happily let one project's folder point at another's target.
    """
    if target_id is None:
        return
    cursor = await conn.execute(
        "SELECT 1 FROM project_target WHERE id = ? AND project_id = ?",
        (target_id, project_id),
    )
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=422, detail="Target does not belong to this project")


def _folder_response(d: dict) -> SourceFolder:
    bool_fields(d, "is_primary")
    return SourceFolder(**d)


async def _fetch_folder(conn, folder_id: int) -> SourceFolder:
    cursor = await conn.execute(
        f"{_FOLDER_SELECT} WHERE psf.id = ?",  # nosec B608 - constant SELECT
        (folder_id,),
    )
    return _folder_response(row_to_dict(await cursor.fetchone()))


@router.get("/{project_id}/folders", response_model=list[SourceFolder])
async def list_folders(project_id: int) -> list[SourceFolder]:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        cursor = await conn.execute(
            f"{_FOLDER_SELECT} WHERE psf.project_id = ? "  # nosec B608 - constant SELECT
            "ORDER BY psf.is_primary DESC, psf.added_at",
            (project_id,),
        )
        return [_folder_response(row_to_dict(r)) for r in await cursor.fetchall()]


@router.post("/{project_id}/folders", response_model=SourceFolder, status_code=201)
async def add_folder(project_id: int, body: SourceFolderCreate) -> SourceFolder:
    path = body.path.strip()
    if not path:
        raise HTTPException(status_code=422, detail="Folder path is required")
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        # First folder for a project is implicitly primary.
        cursor = await conn.execute(
            "SELECT COUNT(*) AS n FROM project_source_folder WHERE project_id = ?",
            (project_id,),
        )
        is_first = (await cursor.fetchone())["n"] == 0
        make_primary = body.is_primary or is_first
        if make_primary:
            await conn.execute(
                "UPDATE project_source_folder SET is_primary = 0 WHERE project_id = ?",
                (project_id,),
            )
        if body.rig_id is not None:
            await get_or_404(conn, "rig", body.rig_id, "Rig")
        await _validate_folder_target(conn, project_id, body.project_target_id)
        try:
            cursor = await conn.execute(
                "INSERT INTO project_source_folder "
                "(project_id, path, is_primary, rig_id, project_target_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    project_id,
                    path,
                    1 if make_primary else 0,
                    body.rig_id,
                    body.project_target_id,
                ),
            )
            folder_id = cursor.lastrowid
        except Exception as exc:  # noqa: BLE001 - translate UNIQUE(project_id, path)
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="Folder already added") from exc
            raise
        # A folder can be bound over files another folder already cataloged (or
        # re-bound after removal), so let the single owner settle rig + session.
        await assign_rigs_and_sessions(
            conn, project_id, await project_geo_timezone(conn, project_id)
        )
        await conn.commit()
        return await _fetch_folder(conn, folder_id)


@router.put("/{project_id}/folders/{folder_id}/primary", response_model=SourceFolder)
async def set_primary_folder(project_id: int, folder_id: int) -> SourceFolder:
    async with get_db() as conn:
        await _get_folder_or_404(conn, project_id, folder_id)
        await conn.execute(
            "UPDATE project_source_folder SET is_primary = 0 WHERE project_id = ?", (project_id,)
        )
        await conn.execute(
            "UPDATE project_source_folder SET is_primary = 1 WHERE id = ?", (folder_id,)
        )
        await conn.commit()
        return await _fetch_folder(conn, folder_id)


@router.patch("/{project_id}/folders/{folder_id}", response_model=SourceFolder)
async def update_folder(project_id: int, folder_id: int, body: SourceFolderUpdate) -> SourceFolder:
    """Tag a source folder with the rig that shot it and/or the target it holds
    (explicit null clears either).

    The user declares both; nothing infers them from a header. **Only the fields
    actually sent are written** (read off ``model_fields_set``), so tagging a rig
    cannot silently clear a target set separately. Frames already cataloged are
    re-tagged in place and their sessions re-keyed, so the change takes effect
    without a re-scan. Nested bindings resolve innermost-first, so tagging a parent
    folder never steals a nested folder's frames. Target differs from rig in two
    ways: it applies to lights only, and a hand-corrected frame
    (``project_target_source = 'user'``) is never overwritten.
    """
    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        await _get_folder_or_404(conn, project_id, folder_id)
        sent = body.model_fields_set
        if not ({"rig_id", "project_target_id"} & sent):
            return await _fetch_folder(conn, folder_id)
        if "rig_id" in sent and body.rig_id is not None:
            await get_or_404(conn, "rig", body.rig_id, "Rig")
        if "project_target_id" in sent:
            await _validate_folder_target(conn, project_id, body.project_target_id)
        # Only the fields actually sent are written, so tagging a rig can't clear
        # a target that was set separately.
        sets = [f"{f} = ?" for f in ("rig_id", "project_target_id") if f in sent]
        params = [getattr(body, f) for f in ("rig_id", "project_target_id") if f in sent]
        await conn.execute(
            # column names come from a fixed tuple; values are bound
            f"UPDATE project_source_folder SET {', '.join(sets)} WHERE id = ?",  # nosec B608
            (*params, folder_id),
        )
        await assign_rigs_and_sessions(
            conn, project_id, await project_geo_timezone(conn, project_id)
        )
        await conn.commit()
        return await _fetch_folder(conn, folder_id)


@router.delete("/{project_id}/folders/{folder_id}", status_code=204)
async def remove_folder(project_id: int, folder_id: int) -> None:
    """Unbind a source folder AND drop everything cataloged from under it.

    Cataloged files are matched by path prefix within this project (each project
    owns its own file rows). A sub/master that also has a file_location under
    another still-bound folder survives the orphan sweep; only items left with no
    file_location are deleted. Auto-sessions emptied by the removal are dropped too.
    """
    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        folder = await _get_folder_or_404(conn, project_id, folder_id)
        # Exact prefix match (folder + separator) so underscores/percent in real
        # paths can't act as LIKE wildcards. folder_prefix picks the separator the
        # folder's children actually carry: `/` for a plain directory or one
        # inside an archive, `::` for an archive bound at its root. Building it
        # here with a hardcoded `/` got both the archive-root case and Windows
        # wrong, and in both the DELETE simply matched nothing — the folder went
        # away and its frames stayed behind, invisible to the orphan sweep.
        prefix = folder_prefix(folder["path"])

        await conn.execute(
            "DELETE FROM file_location WHERE project_id = ? AND substr(path, 1, length(?)) = ?",
            (project_id, prefix, prefix),
        )
        # Orphan sweep: drop this project's subs/masters now lacking any file.
        await conn.execute(
            "DELETE FROM sub_frame WHERE project_id = ? "
            "AND NOT EXISTS (SELECT 1 FROM file_location fl WHERE fl.sub_frame_id = sub_frame.id)",
            (project_id,),
        )
        await conn.execute(
            "DELETE FROM processed_image WHERE project_id = ? "
            # Qualify the column — see the note in catalog_delete: a bare `id`
            # binds to file_location.id and sweeps away every master.
            "AND NOT EXISTS (SELECT 1 FROM file_location fl "
            "WHERE fl.processed_image_id = processed_image.id)",
            (project_id,),
        )
        await conn.execute("DELETE FROM project_source_folder WHERE id = ?", (folder_id,))
        # A sub that survived via a file_location under another still-bound folder
        # may have been getting its rig from the folder just removed, so re-pick
        # rig + session rather than only sweeping. This also drops emptied sessions.
        await assign_rigs_and_sessions(
            conn, project_id, await project_geo_timezone(conn, project_id)
        )
        await conn.commit()


async def _get_folder_or_404(conn, project_id: int, folder_id: int) -> dict:
    cursor = await conn.execute(
        "SELECT * FROM project_source_folder WHERE id = ? AND project_id = ?",
        (folder_id, project_id),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Source folder not found: {folder_id}")
    return row_to_dict(row)


# ── Ingest run ────────────────────────────────────────────────────────────────


@router.post("/{project_id}/ingest", response_model=IngestStatus)
async def start_ingest(
    project_id: int,
    folder_id: int | None = Query(default=None, description="Scan only this source folder"),
) -> IngestStatus:
    """Scan bound folders and catalog their contents (idempotent re-ingest).

    With ``folder_id`` only that folder is (re-)scanned; without it, every bound
    folder is scanned. Project-wide post-processing (dark-flat reclassification)
    runs either way, so a single-folder scan still settles cross-folder matches.
    """
    if _INGEST_LOCK.locked():
        raise HTTPException(status_code=409, detail="An ingest is already running")

    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        if folder_id is not None:
            folder = await _get_folder_or_404(conn, project_id, folder_id)
            folders = [folder["path"]]
        else:
            cursor = await conn.execute(
                "SELECT path FROM project_source_folder WHERE project_id = ? ORDER BY added_at",
                (project_id,),
            )
            folders = [r["path"] for r in await cursor.fetchall()]
        if not folders:
            raise HTTPException(status_code=422, detail="Project has no source folders")

    # Hold the lock for the whole synchronous-within-request run. Ingest is fast
    # enough (parse fan-out is parallel) to run inline; status is queryable after.
    async with _INGEST_LOCK:
        return await _run_ingest(project_id, folders)


async def _run_ingest(project_id: int, folders: list[str]) -> IngestStatus:
    settings = await get_settings()
    configured = settings.max_worker_cores
    n_workers = max(1, int(configured)) if configured else max(1, (os.cpu_count() or 2) - 1)

    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        cursor = await conn.execute(
            "INSERT INTO ingestion_run (project_id, source_path, status) VALUES (?, ?, 'running')",
            (project_id, os.pathsep.join(folders)),
        )
        run_id = cursor.lastrowid
        await conn.commit()

        tz_name = await project_geo_timezone(conn, project_id)
        errors: list[dict] = []
        counters = {"scanned": 0, "inserted": 0, "updated": 0, "skipped": 0}

        # One spawn pool for the whole run, shut down via the context manager so no
        # worker processes linger (which would wedge `uvicorn --reload` restarts).
        # n_workers == 1 → parse inline, no pool at all.
        pool = make_pool(n_workers) if n_workers > 1 else None
        try:
            for folder in folders:
                await _ingest_folder(conn, project_id, run_id, folder, pool, errors, counters)
            await _reclassify_dark_flats(conn, project_id)
            # Rig + session are assigned in one post-pass rather than per file: a
            # frame's rig depends on which bound folder *innermost* contains it,
            # which isn't known until every folder is on the table. The pass also
            # sweeps sessions a re-scan emptied. The user-facing project_session
            # rows are never touched by ingest — deriving those is an explicit
            # action on the Sessions tab.
            await assign_rigs_and_sessions(conn, project_id, tz_name)
            status = "completed"
        except Exception as exc:  # noqa: BLE001 - record failure on the run, re-raise after commit
            logger.exception("%s run %d failed", _LOG_PREFIX, run_id)
            errors.append({"path": None, "error": f"{type(exc).__name__}: {exc}"})
            status = "failed"
        finally:
            if pool is not None:
                pool.shutdown(wait=True, cancel_futures=True)

        await conn.execute(
            "UPDATE ingestion_run SET status = ?, files_scanned = ?, subs_inserted = ?, "
            "subs_updated = ?, subs_skipped = ?, errors_count = ?, errors_json = ?, "
            "finished_at = datetime('now') WHERE id = ?",
            (
                status,
                counters["scanned"],
                counters["inserted"],
                counters["updated"],
                counters["skipped"],
                len(errors),
                json.dumps(errors) if errors else None,
                run_id,
            ),
        )
        await conn.commit()

        logger.info(
            "%s run %d %s: scanned=%d inserted=%d updated=%d skipped=%d errors=%d",
            _LOG_PREFIX,
            run_id,
            status,
            counters["scanned"],
            counters["inserted"],
            counters["updated"],
            counters["skipped"],
            len(errors),
        )
        return IngestStatus(
            run_id=run_id,
            project_id=project_id,
            status=status,
            files_scanned=counters["scanned"],
            subs_inserted=counters["inserted"],
            subs_updated=counters["updated"],
            subs_skipped=counters["skipped"],
            errors_count=len(errors),
        )


async def _ingest_folder(conn, project_id, run_id, folder, pool, errors, counters) -> None:
    entries = scan_directory(folder)
    counters["scanned"] += len(entries)

    # Non-image categories: park a file_location row (no entity link).
    for entry in entries:
        if entry.category in (CATEGORY_PXIPROJECT, CATEGORY_LOG, CATEGORY_OTHER):
            await _upsert_plain_location(conn, project_id, entry)

    # Header-bearing files: parse in parallel, then persist on the main process.
    to_parse = header_bearing(entries)
    parsed = await _parse_in_pool(to_parse, pool)

    for result in parsed:
        if result.get("error"):
            errors.append({"path": result["path"], "error": result["error"]})
            continue
        try:
            await _persist_parsed(conn, project_id, run_id, result, counters)
        except Exception as exc:  # noqa: BLE001 - one bad file shouldn't abort the run
            errors.append({"path": result["path"], "error": f"{type(exc).__name__}: {exc}"})


async def _parse_in_pool(entries, pool) -> list[dict]:
    if not entries:
        return []
    paths = [e.path for e in entries]
    # No pool (single-core) or a single file → parse inline, no IPC overhead.
    if pool is None or len(paths) == 1:
        return [parse_image_file(p) for p in paths]
    loop = asyncio.get_running_loop()
    futures = [loop.run_in_executor(pool, parse_image_file, p) for p in paths]
    return list(await asyncio.gather(*futures))


async def _persist_parsed(conn, project_id, run_id, result, counters) -> None:
    meta = result["meta"]
    raw_header = result["raw_header"]
    route, frame_type = classify_frame(meta, raw_header, filename=Path(result["path"]).name)

    date_obs = _coerce_date_obs(meta.get("date_obs"), result["mtime"])

    if route == CATEGORY_PROCESSED:
        await _upsert_processed(
            conn,
            project_id,
            run_id,
            result,
            meta,
            raw_header,
            frame_type,
            date_obs,
            counters,
        )
        return

    # Sub frame.
    sub_id, was_insert = await _upsert_sub_frame(
        conn,
        project_id,
        run_id,
        result,
        meta,
        raw_header,
        frame_type,
        date_obs,
    )
    counters["inserted" if was_insert else "updated"] += 1

    # Session, rig AND target are assigned project-wide after every folder is
    # walked (assign_rigs_and_sessions) — all three depend on which bound folder
    # innermost contains the file, which isn't knowable here. Target moved there
    # in v0.41.3 when folders gained a target tag; writing it per-file could not
    # see folder nesting and got a tag-after-scan wrong.
    await _link_file_location(conn, project_id, result, "sub_frame", sub_id)


async def _upsert_sub_frame(
    conn,
    project_id,
    run_id,
    result,
    meta,
    raw_header,
    frame_type,
    date_obs,
) -> tuple[int, bool]:
    content_hash = result["content_hash"]
    cursor = await conn.execute(
        "SELECT id FROM sub_frame WHERE project_id = ? AND content_hash = ?",
        (project_id, content_hash),
    )
    existing = await cursor.fetchone()

    # Filters only matter for lights and flats. Darks / dark-flats / bias are
    # filterless by definition (calibration darks are never matched on filter),
    # so drop any FILTER the header happened to carry.
    keeps_filter = frame_type in ("light", "flat")

    cols = {
        "frame_type": frame_type,
        "filter_name_hint": _as_str(meta.get("filter_name")) if keeps_filter else None,
        "exposure_seconds": _as_float(meta.get("exposure_time")) or 0.0,
        "gain": _as_float(meta.get("gain")),
        "offset_adu": _as_float(meta.get("offset")),
        "sensor_temp_c": _as_float(meta.get("sensor_temp")),
        "set_temp_c": _as_float(meta.get("sensor_temp_target")),
        "binning_x": _as_int(meta.get("binning_x")),
        "binning_y": _as_int(meta.get("binning_y")),
        "bit_depth": _as_int(meta.get("bit_depth")),
        "image_width": _as_int(meta.get("image_width")),
        "image_height": _as_int(meta.get("image_height")),
        "date_obs_utc": date_obs,
        "airmass": _as_float(meta.get("airmass")),
        "object_hint": _as_str(meta.get("object_name")),
        "fits_header_json": json.dumps(raw_header),
        "ingestion_run_id": run_id,
    }

    if existing is None:
        cols["project_id"] = project_id
        cols["content_hash"] = content_hash
        names = ", ".join(cols)
        placeholders = ", ".join("?" for _ in cols)
        cursor = await conn.execute(
            f"INSERT INTO sub_frame ({names}) VALUES ({placeholders})",  # nosec B608 - column names from fixed internal dict, not user input
            tuple(cols.values()),
        )
        return cursor.lastrowid, True

    # Re-scan must never clobber a hand correction (migration 0043): frame_type
    # keeps its stored value while frame_type_source = 'user'.
    #
    # filter_name_hint is DERIVED, not user-owned — it is a function of (header
    # FILTER, effective frame type), where "effective" means the corrected type
    # when one was set. Recomputing it here rather than freezing it means a frame
    # corrected *to* light or flat gets its filter name back, which a one-way
    # freeze would have withheld forever (and matching_flats joins on it).
    cols.pop("filter_name_hint")  # rebuilt below from the effective frame type
    raw_hint = _as_str(meta.get("filter_name"))
    set_clause = ", ".join(
        "frame_type = CASE WHEN frame_type_source = 'user' THEN frame_type ELSE ? END"
        if k == "frame_type"
        else f"{k} = ?"
        for k in cols
    )
    await conn.execute(
        f"UPDATE sub_frame SET {set_clause}, filter_name_hint = CASE WHEN "  # nosec B608 - set_clause is built from a fixed internal column dict; every value is parameterized
        "(CASE WHEN frame_type_source = 'user' THEN frame_type ELSE ? END) "
        "IN ('light', 'flat') THEN ? ELSE NULL END WHERE id = ?",
        (*cols.values(), frame_type, raw_hint, existing["id"]),
    )
    return existing["id"], False


async def _upsert_processed(
    conn,
    project_id,
    run_id,
    result,
    meta,
    raw_header,
    frame_type,
    date_obs,
    counters,
) -> None:
    content_hash = result["content_hash"]
    cursor = await conn.execute(
        "SELECT id FROM processed_image WHERE project_id = ? AND content_hash = ?",
        (project_id, content_hash),
    )
    existing = await cursor.fetchone()
    # Masters carry no equipment identification, so the bandpass parsed from the
    # FILTER keyword (e.g. "Ha") is the filter the Masters tab shows. Only
    # lights/flats carry a filter; darks/bias stay NULL.
    line_name = None
    if frame_type in ("light", "flat"):
        line_name = canonicalize_line_name(raw_header.get("FILTER") or "")
    ncombine = (
        _as_int(meta.get("pi_ncombine"))
        or _as_int(raw_header.get("STACKCNT"))
        or _as_int(raw_header.get("NIMAGES"))
    )
    cols = {
        "image_kind": "master",
        "frame_type": frame_type,
        "line_name": line_name,
        "ncombine": ncombine,
        "total_exposure_seconds": _total_exposure(raw_header, ncombine),
        "date_obs_utc": date_obs,
        "image_width": _as_int(meta.get("image_width")),
        "image_height": _as_int(meta.get("image_height")),
        "fits_header_json": json.dumps(raw_header),
        "ingestion_run_id": run_id,
    }
    if existing is None:
        # project_id + content_hash are identity (per-project); set on INSERT only,
        # never re-assigned on UPDATE — mirrors _upsert_sub_frame.
        cols["project_id"] = project_id
        cols["content_hash"] = content_hash
        names = ", ".join(cols)
        placeholders = ", ".join("?" for _ in cols)
        cursor = await conn.execute(
            f"INSERT INTO processed_image ({names}) VALUES ({placeholders})",  # nosec B608 - column names from fixed internal dict, not user input
            tuple(cols.values()),
        )
        pid = cursor.lastrowid
        counters["inserted"] += 1
    else:
        set_clause = ", ".join(f"{k} = ?" for k in cols)
        await conn.execute(
            f"UPDATE processed_image SET {set_clause} WHERE id = ?",  # nosec B608 - column names from fixed internal dict, not user input
            (*cols.values(), existing["id"]),
        )
        pid = existing["id"]
        counters["updated"] += 1
    await _link_file_location(conn, project_id, result, "processed", pid)


async def _link_file_location(conn, project_id, result, category, entity_id) -> None:
    # col is one of two literals chosen above — never user input.
    col = "sub_frame_id" if category == "sub_frame" else "processed_image_id"
    await conn.execute(
        "INSERT INTO file_location "  # nosec B608 - col is a fixed literal, not user input
        f"(project_id, path, category, {col}, file_hash, size_bytes, mtime) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(project_id, path) DO UPDATE SET category = excluded.category, "
        f"{col} = excluded.{col}, file_hash = excluded.file_hash, "
        "size_bytes = excluded.size_bytes, mtime = excluded.mtime",
        (
            project_id,
            result["path"],
            category,
            entity_id,
            result["content_hash"],
            result.get("size_bytes"),
            result.get("mtime"),
        ),
    )


async def _upsert_plain_location(conn, project_id, entry) -> None:
    await conn.execute(
        "INSERT INTO file_location (project_id, path, category, size_bytes, mtime) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(project_id, path) DO UPDATE SET category = excluded.category, "
        "size_bytes = excluded.size_bytes, mtime = excluded.mtime",
        (project_id, entry.path, entry.category, entry.size_bytes or None, entry.mtime),
    )


async def _reclassify_dark_flats(conn, project_id: int) -> None:
    """Promote ``dark`` frames that are actually dark-flats to ``dark_flat``.

    Capture software (notably ASIAir) labels dark-flats just ``IMAGETYP=DARK`` —
    indistinguishable from real darks by header alone. The distinguishing signal is
    exposure: a dark-flat is shot at the *flats'* exposure, not the lights'. So a
    dark is reclassified ``dark_flat`` when some flat's exposure is within ±20 %
    (0.8–1.25×) of it AND no light is within that range.

    The tolerance matters: ASIAir flats are *auto-exposed* (e.g. 2.208 s) while the
    matching dark-flats use the nominal setting (2.2 s), so exact equality misses
    them — but flats (seconds) and lights (minutes) are ~100× apart, so a loose
    ratio never confuses the two. Project-scoped and idempotent. Real darks (which
    match the lights' exposure) and master darks (``processed_image``) are untouched.

    Frames whose ``frame_type_source`` is ``'user'`` are skipped (migration 0043):
    this pass runs on every scan, so without the guard it would silently revert a
    manual correction.
    """
    await conn.execute(
        "UPDATE sub_frame SET frame_type = 'dark_flat' WHERE id IN ("
        "  SELECT sf.id FROM sub_frame sf "
        "  WHERE sf.project_id = ? AND sf.frame_type = 'dark' AND sf.exposure_seconds > 0 "
        "    AND sf.frame_type_source = 'auto' "
        "    AND EXISTS ("
        "      SELECT 1 FROM sub_frame f "
        "      WHERE f.project_id = ? AND f.frame_type = 'flat' "
        "        AND f.exposure_seconds BETWEEN sf.exposure_seconds * 0.8 "
        "                                   AND sf.exposure_seconds * 1.25) "
        "    AND NOT EXISTS ("
        "      SELECT 1 FROM sub_frame l "
        "      WHERE l.project_id = ? AND l.frame_type = 'light' "
        "        AND l.exposure_seconds BETWEEN sf.exposure_seconds * 0.8 "
        "                                   AND sf.exposure_seconds * 1.25)"
        ")",
        (project_id, project_id, project_id),
    )


async def _project_display_tz(conn, project_id: int) -> str:
    """The IANA timezone for displaying dates: the project location's *display*
    timezone (``location.timezone``), or UTC if the project has no location."""
    cursor = await conn.execute(
        "SELECT l.timezone FROM project p LEFT JOIN location l ON l.id = p.location_id "
        "WHERE p.id = ?",
        (project_id,),
    )
    row = await cursor.fetchone()
    return (row["timezone"] if row and row["timezone"] else None) or "UTC"


# ── Catalog (read-only) ───────────────────────────────────────────────────────


@router.get("/{project_id}/catalog/summary", response_model=CatalogSummary)
async def catalog_summary(project_id: int) -> CatalogSummary:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        s = CatalogSummary()
        cursor = await conn.execute(
            "SELECT frame_type, COUNT(*) AS n FROM sub_frame "
            "WHERE project_id = ? GROUP BY frame_type",
            (project_id,),
        )
        by_type = {row["frame_type"]: row["n"] for row in await cursor.fetchall()}
        s.lights = by_type.get("light", 0)
        s.darks = by_type.get("dark", 0)
        s.flats = by_type.get("flat", 0)
        s.bias = by_type.get("bias", 0)
        s.dark_flats = by_type.get("dark_flat", 0)
        s.unknown_frames = by_type.get("unknown", 0)

        s.processed = await _count(
            conn, "SELECT COUNT(*) FROM processed_image WHERE project_id = ?", (project_id,)
        )
        s.sessions = await _count(
            conn, "SELECT COUNT(*) FROM session WHERE project_id = ?", (project_id,)
        )
        # Non-frame file counts (pxiproject/log/other) — each project owns its
        # file_location rows, so scope is a plain project_id match.
        cursor = await conn.execute(
            "SELECT category, COUNT(*) AS n FROM file_location "
            "WHERE project_id = ? GROUP BY category",
            (project_id,),
        )
        cat = {row["category"]: row["n"] for row in await cursor.fetchall()}
        s.pxiprojects = cat.get("pxiproject", 0)
        s.logs = cat.get("log", 0)
        s.other = cat.get("other", 0)
        s.total_files = (
            s.lights
            + s.darks
            + s.flats
            + s.bias
            + s.dark_flats
            + s.unknown_frames
            + s.processed
            + s.pxiprojects
            + s.logs
            + s.other
        )
        return s


@router.get("/{project_id}/catalog/frames", response_model=CatalogFramesPage)
async def catalog_frames(
    project_id: int,
    limit: int = Query(default=500, ge=1, le=100000),
    offset: int = Query(default=0, ge=0),
    frame_type: str | None = Query(default=None, description="Filter by frame_type"),
    filter_name: str | None = Query(default=None, description="Filter by filter name (pill)"),
    sort: str | None = Query(default=None, description=f"One of {sorted(_FRAME_SORTS)}"),
) -> CatalogFramesPage:
    # Optional frame_type filter (drives the count-pill filtering in the UI) and
    # filter-name scope (clicking a Lights/Flats filter pill, matching the same
    # filter_name_hint the pills are grouped by).
    scope, scope_params = _frame_scope(frame_type, filter_name)
    # An explicit sort wins; otherwise keep the per-tab default. Flats are
    # organised per-filter (you match flats to lights by filter), so sort by filter
    # first. Lights/calibration sort by path so raw vs per-stage outputs bunch
    # together; date_obs is the within-group tiebreak.
    if sort and sort in _FRAME_SORTS:
        order_clause = _FRAME_SORTS[sort]
    elif frame_type == "flat":
        order_clause = "ORDER BY sf.filter_name_hint, fl.path, sf.date_obs_utc, sf.id"
    else:
        order_clause = "ORDER BY fl.path, sf.date_obs_utc, sf.id"
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        total = await _count(
            conn,
            "SELECT COUNT(*) FROM sub_frame sf "
            # nosec B608 - clauses are fixed literals; values are parameterized
            f"WHERE sf.project_id = ?{scope}",
            (project_id, *scope_params),
        )
        cursor = await conn.execute(
            _FRAME_SELECT
            # nosec B608 - clauses are fixed literals; values are parameterized
            + f"WHERE sf.project_id = ?{scope} "
            f"GROUP BY sf.id {order_clause} LIMIT ? OFFSET ?",
            (project_id, *scope_params, limit, offset),
        )
        rows = [_catalog_frame(row_to_dict(r)) for r in await cursor.fetchall()]
        tz = await _project_display_tz(conn, project_id)
        return CatalogFramesPage(rows=rows, total=total, timezone=tz)


@router.post("/{project_id}/catalog/delete", response_model=CatalogDeleteResult)
async def catalog_delete(project_id: int, body: CatalogDeleteRequest) -> CatalogDeleteResult:
    """Remove items from this project's catalog. Files on disk are never touched.

    **A re-scan of a still-bound source folder will catalog these again** — the
    catalog is a view of what is under the bound folders, and nothing records
    that you removed something. That is the deliberate, documented behaviour, not
    an oversight: the UI says so before you confirm. To keep files out for good,
    unbind the folder or move them out of it.

    Deleting a sub frame or a processed image takes its file locations with it.
    Deleting a plain file removes only that row; if it was the last location of a
    sub or master, the orphan sweep drops that too.
    """
    if not (body.sub_frame_ids or body.processed_image_ids or body.file_ids):
        raise HTTPException(status_code=422, detail="Nothing to delete")

    result = CatalogDeleteResult()
    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        await get_or_404(conn, "project", project_id, "Project")

        for ids, table, field in (
            (body.sub_frame_ids, "sub_frame", "sub_frames"),
            (body.processed_image_ids, "processed_image", "processed_images"),
        ):
            if not ids:
                continue
            marks = ",".join("?" * len(ids))
            # Scoped to the project on both statements: an id from another
            # project must not be deletable by sending it here.
            await conn.execute(
                # only the placeholder count is interpolated; ids are parameterized
                f"DELETE FROM file_location WHERE project_id = ? AND {table}_id IN ({marks})",  # nosec B608
                (project_id, *ids),
            )
            cursor = await conn.execute(
                # only the placeholder count is interpolated; ids are parameterized
                f"DELETE FROM {table} WHERE project_id = ? AND id IN ({marks})",  # nosec B608
                (project_id, *ids),
            )
            setattr(result, field, cursor.rowcount)

        if body.file_ids:
            marks = ",".join("?" * len(body.file_ids))
            cursor = await conn.execute(
                # only the placeholder count is interpolated; ids are parameterized
                f"DELETE FROM file_location WHERE project_id = ? AND id IN ({marks})",  # nosec B608
                (project_id, *body.file_ids),
            )
            result.files = cursor.rowcount
            # A plain-file delete can strand the sub/master it belonged to.
            await conn.execute(
                "DELETE FROM sub_frame WHERE project_id = ? AND NOT EXISTS "
                "(SELECT 1 FROM file_location fl WHERE fl.sub_frame_id = sub_frame.id)",
                (project_id,),
            )
            await conn.execute(
                "DELETE FROM processed_image WHERE project_id = ? AND NOT EXISTS "
                # Qualify the column: a bare `id` binds to file_location.id, which
                # makes the subquery uncorrelated and deletes EVERY master.
                "(SELECT 1 FROM file_location fl "
                "WHERE fl.processed_image_id = processed_image.id)",
                (project_id,),
            )

        # Removing frames can empty a session and can change which folder a
        # surviving frame's rig comes from, so let the single owner settle all three.
        await assign_rigs_and_sessions(
            conn, project_id, await project_geo_timezone(conn, project_id)
        )
        await conn.commit()

    logger.info(
        "%s project %d deleted: subs=%d masters=%d files=%d",
        _LOG_PREFIX,
        project_id,
        result.sub_frames,
        result.processed_images,
        result.files,
    )
    return result


# ── Frame quality analysis (v0.41.3) ──────────────────────────────────────────
#
# A full pass over a real library is 210 GB and several minutes, so the run is
# driven by the client: it fetches the pending ids once, then POSTs them back in
# batches. Each batch is an ordinary short request. Progress, cancel and
# resume-where-it-stopped all fall out of that for free, and the app keeps its
# "all work is request-driven, no background tasks" property.


def _frame_scope(frame_type: str | None, filter_name: str | None) -> tuple[str, tuple]:
    """Build the WHERE fragment + params selecting the frames in scope.

    Shared by the listing, the quality-pending count and the quality summary so
    the three can never disagree about what "this tab, this filter pill" means.
    The frame-type vocabulary comes from ``FrameTypeName`` rather than a literal,
    so adding a frame type reaches every caller.
    """
    clause = ""
    params: tuple = ()
    if frame_type in get_args(FrameTypeName):
        clause += " AND sf.frame_type = ?"
        params += (frame_type,)
    if filter_name:
        clause += " AND sf.filter_name_hint = ?"
        params += (filter_name,)
    return clause, params


@router.get("/{project_id}/catalog/analyze/pending", response_model=QualityPending)
async def catalog_analyze_pending(
    project_id: int,
    frame_type: str | None = Query(default=None, description="Scope to one frame_type"),
    filter_name: str | None = Query(default=None, description="Scope to one filter pill"),
    force: bool = Query(default=False, description="Include already-analyzed frames"),
) -> QualityPending:
    """The frames awaiting quality analysis, as one ordered id list.

    Returns the whole list rather than a page — the client batches it locally, so
    progress is exact and there is no re-querying a target that moves as rows are
    analyzed underneath it.
    """
    scope, scope_params = _frame_scope(frame_type, filter_name)
    pending_clause = "" if force else " AND sf.quality_analyzed_at IS NULL"
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        total = await _count(
            conn,
            # clauses are fixed literals; values are parameterized
            f"SELECT COUNT(*) FROM sub_frame sf WHERE sf.project_id = ?{scope}",  # nosec B608
            (project_id, *scope_params),
        )
        cursor = await conn.execute(
            "SELECT sf.id FROM sub_frame sf "
            "LEFT JOIN file_location fl ON fl.sub_frame_id = sf.id "
            # nosec B608 - clauses are fixed literals; values are parameterized
            f"WHERE sf.project_id = ?{scope}{pending_clause} "
            "GROUP BY sf.id ORDER BY fl.path, sf.date_obs_utc, sf.id",
            (project_id, *scope_params),
        )
        ids = [int(r[0]) for r in await cursor.fetchall()]
        return QualityPending(frame_ids=ids, total=total)


@router.get("/{project_id}/catalog/analyze/summary", response_model=QualityCounts)
async def catalog_analyze_summary(
    project_id: int,
    frame_type: str | None = Query(default=None, description="Scope to one frame_type"),
    filter_name: str | None = Query(default=None, description="Scope to one filter pill"),
) -> QualityCounts:
    """How much of this scope has been analyzed, for the Analyze button's label.

    Counts only — the button needs to distinguish "nothing measured yet" from
    "12 new frames since last time" from "all done, offer a re-run", and pulling
    the full pending id list on every tab switch just to length it would ship
    ~20 KB of ints for a number.
    """
    scope, scope_params = _frame_scope(frame_type, filter_name)
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        cursor = await conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN sf.quality_analyzed_at IS NOT NULL THEN 1 ELSE 0 END) AS analyzed, "
            "SUM(CASE WHEN sf.quality_status = 'unreadable' THEN 1 ELSE 0 END) AS unreadable "
            # nosec B608 - clauses are fixed literals; values are parameterized
            f"FROM sub_frame sf WHERE sf.project_id = ?{scope}",
            (project_id, *scope_params),
        )
        row = row_to_dict(await cursor.fetchone())
    total = int(row["total"] or 0)
    analyzed = int(row["analyzed"] or 0)
    return QualityCounts(
        total=total,
        analyzed=analyzed,
        pending=total - analyzed,
        unreadable=int(row["unreadable"] or 0),
    )


@router.post("/{project_id}/catalog/analyze", response_model=QualityAnalyzeResult)
async def catalog_analyze(
    project_id: int,
    body: QualityAnalyzeRequest,
) -> QualityAnalyzeResult:
    """Compute quality metrics for one batch of frames.

    Star metrics are computed for lights only; ADU stats for every frame type.
    Every frame touched gets ``quality_analyzed_at`` set — including one that
    could not be read — so a file on an unmounted volume is reported once rather
    than retried on every subsequent run.
    """
    if _ANALYZE_LOCK.locked():
        raise HTTPException(status_code=409, detail="A frame analysis is already running")
    async with _ANALYZE_LOCK:
        return await _run_analyze(project_id, body)


async def _run_analyze(project_id: int, body: QualityAnalyzeRequest) -> QualityAnalyzeResult:
    settings = await get_settings()
    n_workers = effective_worker_count(settings.max_worker_cores)
    result = QualityAnalyzeResult()

    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        placeholders = ",".join("?" * len(body.frame_ids))
        cursor = await conn.execute(
            "SELECT sf.id, sf.frame_type, sf.quality_analyzed_at, MIN(fl.path) AS path "
            "FROM sub_frame sf "
            "LEFT JOIN file_location fl ON fl.sub_frame_id = sf.id "
            # nosec B608 - only the id placeholder count is interpolated
            f"WHERE sf.project_id = ? AND sf.id IN ({placeholders}) "
            "GROUP BY sf.id",
            (project_id, *body.frame_ids),
        )
        rows = [row_to_dict(r) for r in await cursor.fetchall()]

        todo: list[dict] = []
        for row in rows:
            if row["quality_analyzed_at"] and not body.force:
                result.skipped += 1
                continue
            if not row["path"]:
                # Cataloged with no file_location row — nothing to open. Mark it so
                # it leaves the queue instead of coming back every run.
                await _write_quality(conn, row["id"], None, "unreadable", "No file path on record")
                result.unreadable += 1
                continue
            todo.append(row)

        if todo:
            parsed = await _analyze_in_pool(todo, n_workers)
            for row, out in zip(todo, parsed, strict=True):
                if out.get("error"):
                    await _write_quality(conn, row["id"], None, "unreadable", out["error"])
                    result.unreadable += 1
                    if len(result.errors) < 20:
                        result.errors.append(f"{row['path']}: {out['error']}")
                    continue
                await _write_quality(conn, row["id"], out, out["status"], None)
                if out["status"] == "no_stars":
                    result.no_stars += 1
                result.analyzed += 1

        await conn.commit()

    logger.info(
        "%s project %d: analyzed=%d no_stars=%d unreadable=%d skipped=%d",
        _QUALITY_PREFIX,
        project_id,
        result.analyzed,
        result.no_stars,
        result.unreadable,
        result.skipped,
    )
    return result


async def _analyze_in_pool(todo: list[dict], n_workers: int) -> list[dict]:
    """Fan the batch out across a per-run ProcessPool.

    Per-run, never a module global: a long-lived spawn pool leaves worker
    processes alive that wedge ``uvicorn --reload`` (CLAUDE.md). A single frame
    or a single-core setting parses inline, skipping the IPC entirely.
    """
    args = [(row["path"], wants_stars(row["frame_type"])) for row in todo]
    if n_workers <= 1 or len(args) == 1:
        return [analyze_frame_file(p, s) for p, s in args]
    pool = make_pool(n_workers)
    try:
        loop = asyncio.get_running_loop()
        futures = [loop.run_in_executor(pool, analyze_frame_file, p, s) for p, s in args]
        return list(await asyncio.gather(*futures))
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


async def _write_quality(
    conn,
    frame_id: int,
    out: dict | None,
    status: str,
    error: str | None,
) -> None:
    """Persist one frame's outcome. A failure clears any stale metric values.

    ``updated_at`` is set explicitly on purpose. ``trg_sub_frame_updated_at`` fires
    only ``WHEN NEW.updated_at = OLD.updated_at``, so writing it here suppresses the
    trigger's second, recursive UPDATE — one statement per frame instead of two,
    over a pass that touches thousands of rows. Don't "simplify" it away.
    """
    await conn.execute(
        "UPDATE sub_frame SET hfr = ?, star_count = ?, median_adu = ?, "
        "background_adu = ?, snr_estimate = ?, quality_status = ?, "
        "quality_error = ?, quality_analyzed_at = datetime('now'), "
        "updated_at = datetime('now') WHERE id = ?",
        (
            out["hfr"] if out else None,
            out["star_count"] if out else None,
            out["median_adu"] if out else None,
            out["background_adu"] if out else None,
            out["snr_estimate"] if out else None,
            status,
            error,
            frame_id,
        ),
    )


def _require_correction(body: FrameCorrection) -> None:
    """422 unless the body actually asks for something.

    Stated as "did you send a correctable field?" rather than "is anything left
    after removing the non-correctable ones?" — the subtractive form silently
    stops guarding the moment a new bulk-only field is added.
    """
    if not (body.model_fields_set & set(get_args(CorrectableField))) and not body.reset_to_auto:
        raise HTTPException(status_code=422, detail="No correction fields provided")


def _header_filter_name(fits_header_json: str | None) -> str | None:
    """The FILTER value a frame would get from a fresh scan.

    Reads the stored header rather than the file on disk, so a correction works on
    a frame whose source volume is offline, and routes through the same
    ``extract_metadata`` normalization the ingest uses so the two can't disagree.
    """
    if not fits_header_json:
        return None
    try:
        header = json.loads(fits_header_json)
    except _COERCE_ERRORS:  # JSONDecodeError subclasses ValueError
        return None
    return _as_str(extract_metadata(header).get("filter_name"))


async def _apply_correction(conn, project_id: int, frame_id: int, body: FrameCorrection) -> None:
    """Apply one classification correction. Caller owns the transaction.

    Shared by the single-frame and bulk endpoints so the two can never drift.
    """
    cursor = await conn.execute(
        "SELECT id, frame_type, fits_header_json FROM sub_frame WHERE id = ? AND project_id = ?",
        (frame_id, project_id),
    )
    frame = await cursor.fetchone()
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Frame {frame_id} not found")

    sent = body.model_fields_set
    updates: dict[str, object] = {}

    if "frame_type" in sent:
        if body.frame_type is None:
            raise HTTPException(status_code=422, detail="frame_type cannot be null")
        updates["frame_type"] = body.frame_type
        updates["frame_type_source"] = "user"
        # filter_name_hint follows the corrected type in BOTH directions: a frame
        # corrected to a calibration type loses it (only lights and flats carry a
        # filter), and one corrected back to light/flat gets the header's FILTER
        # again. A one-way null would strand the frame with no filter forever, and
        # matching_flats joins on this column.
        updates["filter_name_hint"] = (
            _header_filter_name(frame["fits_header_json"])
            if body.frame_type in ("light", "flat")
            else None
        )

    if "project_target_id" in sent:
        if body.project_target_id is not None:
            # Only lights have a target — the automatic path enforces this
            # (`_persist_parsed` assigns one only when frame_type == 'light'), so
            # the manual path has to as well or the two disagree. Checked against
            # the *effective* type, which may be corrected in this same request.
            effective_type = updates.get("frame_type", frame["frame_type"])
            if effective_type != "light":
                raise HTTPException(
                    status_code=422,
                    detail=f"Only lights carry a target (frame is {effective_type})",
                )
            cursor = await conn.execute(
                "SELECT id FROM project_target WHERE id = ? AND project_id = ?",
                (body.project_target_id, project_id),
            )
            if await cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Target not found in this project")
        updates["project_target_id"] = body.project_target_id
        updates["project_target_source"] = "user"

    for f in body.reset_to_auto:
        updates[f"{f.removesuffix('_id')}_source"] = "auto"

    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    await conn.execute(
        f"UPDATE sub_frame SET {set_clause} WHERE id = ?",  # nosec B608 - column names from a fixed internal allow-list, not user input
        (*updates.values(), frame_id),
    )


@router.patch("/{project_id}/catalog/frames/{frame_id}/classification", response_model=CatalogFrame)
async def correct_frame_classification(
    project_id: int, frame_id: int, body: FrameCorrection
) -> CatalogFrame:
    """Manually correct a frame's type / target.

    Both are re-derived by the ingest pipeline on every scan, so a correction
    marks ``*_source = 'user'`` and the passes skip it (migration 0043).
    """
    _require_correction(body)

    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        await get_or_404(conn, "project", project_id, "Project")
        await _apply_correction(conn, project_id, frame_id, body)
        await conn.commit()
        cursor = await conn.execute(
            _FRAME_SELECT + "WHERE sf.id = ? GROUP BY sf.id",  # nosec B608 - fixed literal
            (frame_id,),
        )
        return _catalog_frame(row_to_dict(await cursor.fetchone()))


@router.post(
    "/{project_id}/catalog/frames/bulk-classification", response_model=BulkCorrectionResult
)
async def bulk_correct_frames(project_id: int, body: BulkFrameCorrection) -> BulkCorrectionResult:
    """Apply one classification correction to several frames in a single transaction.

    All-or-nothing: an unknown or out-of-project frame id 404s and nothing commits.
    """
    _require_correction(body)

    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        await get_or_404(conn, "project", project_id, "Project")
        for frame_id in body.frame_ids:
            await _apply_correction(conn, project_id, frame_id, body)
        await conn.commit()
        return BulkCorrectionResult(updated=len(body.frame_ids))


@router.get("/{project_id}/catalog/filter-summary", response_model=list[CatalogFilterStat])
async def catalog_filter_summary(
    project_id: int,
    frame_type: str = Query(..., description="light | flat"),
) -> list[CatalogFilterStat]:
    """Per-filter count + total exposure for a frame type (the Lights/Flats pills)."""
    if frame_type not in ("light", "flat"):
        raise HTTPException(status_code=422, detail="frame_type must be 'light' or 'flat'")
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        cursor = await conn.execute(
            "SELECT sf.filter_name_hint AS filter_name, "
            "COUNT(*) AS n, COALESCE(SUM(sf.exposure_seconds), 0) AS total "
            "FROM sub_frame sf "
            "WHERE sf.project_id = ? AND sf.frame_type = ? "
            "GROUP BY filter_name ORDER BY filter_name",
            (project_id, frame_type),
        )
        return [
            CatalogFilterStat(
                filter_name=row["filter_name"], count=row["n"], total_seconds=row["total"]
            )
            for row in await cursor.fetchall()
        ]


@router.get("/{project_id}/catalog/masters", response_model=CatalogMastersPage)
async def catalog_masters(
    project_id: int,
    limit: int = Query(default=500, ge=1, le=100000),
    offset: int = Query(default=0, ge=0),
) -> CatalogMastersPage:
    """Processed / stacked images (masters) for the project."""
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        total = await _count(
            conn,
            "SELECT COUNT(*) FROM processed_image WHERE project_id = ?",
            (project_id,),
        )
        cursor = await conn.execute(
            "SELECT pi.id, pi.image_kind, pi.frame_type, pi.line_name, "
            "pi.ncombine, pi.total_exposure_seconds, "
            "pi.image_width, pi.image_height, pi.date_obs_utc, "
            "fl.path AS path, fl.size_bytes AS file_size_bytes "
            "FROM processed_image pi "
            "LEFT JOIN file_location fl ON fl.processed_image_id = pi.id "
            "WHERE pi.project_id = ? "
            "GROUP BY pi.id ORDER BY fl.path, pi.id LIMIT ? OFFSET ?",
            (project_id, limit, offset),
        )
        rows = [_catalog_master(row_to_dict(r)) for r in await cursor.fetchall()]
        tz = await _project_display_tz(conn, project_id)
        return CatalogMastersPage(rows=rows, total=total, timezone=tz)


@router.get("/{project_id}/catalog/others", response_model=CatalogOthersPage)
async def catalog_others(
    project_id: int,
    limit: int = Query(default=500, ge=1, le=100000),
    offset: int = Query(default=0, ge=0),
    unclassified_only: bool = Query(
        default=False,
        description="Only unknown-type sub frames — the ones a correction can act on",
    ),
) -> CatalogOthersPage:
    """Catch-all: PixInsight projects, logs, other files, and unknown-type subs.

    ``unclassified_only`` drops the non-frame files. They dominate the tab on a
    PixInsight-processed project — WBPP writes an ``.xnml`` and an ``.xdrz``
    beside every registered sub, so a few hundred subs become a couple of
    thousand rows here — and none of them can be given a frame type, because
    they aren't frames. The "N frames could not be classified" alert links
    straight to this filtered view; without it the user is told to find 2 rows
    among 1,256.
    """
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        # Non-frame files owned by this project + this project's unknown-type subs.
        file_rows = (
            []
            if unclassified_only
            else await (
                await conn.execute(
                    "SELECT id, category, path, size_bytes, mtime FROM file_location "
                    "WHERE project_id = ? AND category IN ('pxiproject', 'log', 'other') "
                    "ORDER BY category, path",
                    (project_id,),
                )
            ).fetchall()
        )
        unknown_rows = await (
            await conn.execute(
                "SELECT sf.id, sf.date_obs_utc, fl.path AS path "
                "FROM sub_frame sf "
                "LEFT JOIN file_location fl ON fl.sub_frame_id = sf.id "
                "WHERE sf.project_id = ? AND sf.frame_type = 'unknown' "
                "GROUP BY sf.id ORDER BY sf.id",
                (project_id,),
            )
        ).fetchall()
        tz = await _project_display_tz(conn, project_id)

    items = [_catalog_other_file(row_to_dict(r)) for r in file_rows]
    items += [
        CatalogOther(
            id=d["id"],
            kind="sub_frame",
            type_label="Unknown frame",
            path=d.get("path"),
            date=d.get("date_obs_utc"),
        )
        for d in (row_to_dict(r) for r in unknown_rows)
    ]
    total = len(items)
    return CatalogOthersPage(rows=items[offset : offset + limit], total=total, timezone=tz)


_OTHER_TYPE_LABELS = {"pxiproject": "PixInsight Project", "log": "Log", "other": "Other"}


def _catalog_master(d: dict) -> CatalogMaster:
    ft = d.get("frame_type")
    kind = (d.get("image_kind") or "master").capitalize()
    type_label = f"{kind}: {ft.replace('_', ' ').title()}" if ft else kind
    dims = None
    if d.get("image_width") and d.get("image_height"):
        dims = f"{d['image_width']}x{d['image_height']}"
    return CatalogMaster(
        id=d["id"],
        type_label=type_label,
        frame_type=ft,
        filter_name=d.get("line_name"),
        ncombine=d.get("ncombine"),
        total_exposure_seconds=d.get("total_exposure_seconds"),
        dimensions=dims,
        file_size_bytes=d.get("file_size_bytes"),
        date_obs_utc=d.get("date_obs_utc"),
        path=d.get("path"),
    )


def _catalog_other_file(d: dict) -> CatalogOther:
    return CatalogOther(
        id=d["id"],
        kind="file",
        type_label=_OTHER_TYPE_LABELS.get(d.get("category", ""), "Other"),
        path=d.get("path"),
        size_bytes=d.get("size_bytes"),
        date=d.get("mtime"),
    )


@router.get("/{project_id}/catalog/frames/{frame_id}/thumbnail")
async def catalog_frame_thumbnail(project_id: int, frame_id: int):
    """Small auto-stretched JPEG preview for one cataloged sub frame."""
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT sf.content_hash, fl.path AS path "
            "FROM sub_frame sf "
            "LEFT JOIN file_location fl ON fl.sub_frame_id = sf.id "
            "WHERE sf.id = ? AND sf.project_id = ? "
            "ORDER BY fl.id LIMIT 1",
            (frame_id, project_id),
        )
        row = await cursor.fetchone()
    return await _serve_thumbnail(row)


@router.get("/{project_id}/catalog/masters/{master_id}/thumbnail")
async def catalog_master_thumbnail(project_id: int, master_id: int):
    """Small auto-stretched JPEG preview for one processed/master image."""
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT pi.content_hash, fl.path AS path "
            "FROM processed_image pi "
            "LEFT JOIN file_location fl ON fl.processed_image_id = pi.id "
            "WHERE pi.id = ? AND pi.project_id = ? "
            "ORDER BY fl.id LIMIT 1",
            (master_id, project_id),
        )
        row = await cursor.fetchone()
    return await _serve_thumbnail(row)


async def _serve_thumbnail(row):
    """Serve (cached or freshly-rendered) thumbnail bytes for a {content_hash, path} row.

    Decimates the raw array before rendering (cheap even for ~26 MP images), caches
    on disk by content hash (stable across DB recreation), and bounds concurrent
    first-time renders. Unreadable / missing → 404 (the grid shows no preview, never
    a 500). Render is pure-numpy (mlx is not thread-safe — see catalog_thumbnail).
    """
    if row is None or not row["path"]:
        raise HTTPException(status_code=404, detail="No file for this item")

    cache_path = _thumb_cache_dir() / f"{row['content_hash']}_{DEFAULT_MAX_PX}.jpg"
    if cache_path.is_file():
        return FileResponse(cache_path, media_type="image/jpeg")

    async with _THUMB_SEM:
        if cache_path.is_file():  # another request rendered it while we waited
            return FileResponse(cache_path, media_type="image/jpeg")
        try:
            data = await asyncio.to_thread(render_thumbnail_bytes, row["path"], DEFAULT_MAX_PX)
        except Exception as exc:  # noqa: BLE001 - unreadable source → no preview, not a 500
            logger.info("%s thumbnail render failed for %s: %s", _LOG_PREFIX, row["path"], exc)
            raise HTTPException(status_code=404, detail="Could not render thumbnail") from exc
        _write_cache_atomic(cache_path, data)
    return Response(content=data, media_type="image/jpeg")


def _write_cache_atomic(cache_path: Path, data: bytes) -> None:
    """Write thumbnail bytes to the cache via a temp file + rename."""
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(data)
        tmp.replace(cache_path)
    except OSError as exc:  # caching is best-effort — serve the bytes regardless
        logger.warning("%s could not cache thumbnail %s: %s", _LOG_PREFIX, cache_path.name, exc)


# Shared frame projection: the list endpoint and the single-frame refetch (after
# a correction) must return identical shapes.
#
# nosec B608 - the only interpolation is _PIXEL_SCALE_SQL, a module constant;
# every caller-supplied value is parameterized.
# Full-scale ADU for the frame's camera: 2^ADC - 1. NOT a constant 65535 — the
# ADC depth is a property of the camera, and a 12-bit body writes 0..4095 into a
# 16-bit file, so the container says nothing. Across one user's kit that can be
# 65535 (16-bit), 16383 (14-bit) and 4095 (12-bit) at once, which is why a bare
# ADU number can't be judged without it. NULL when the rig is untagged.
_FULL_SCALE_SQL = "CASE WHEN sen.adc_bit_depth > 0 THEN (1 << sen.adc_bit_depth) - 1 END"

_FRAME_SELECT = (
    "SELECT sf.id, sf.frame_type, sf.filter_name_hint, "
    "sf.object_hint, sf.exposure_seconds, sf.gain, sf.set_temp_c, sf.binning_x, "
    "sf.binning_y, sf.image_width, sf.image_height, sf.date_obs_utc, sf.accepted, "
    "sf.project_target_id, sf.frame_type_source, sf.project_target_source, "
    "sf.hfr, sf.star_count, sf.median_adu, sf.background_adu, sf.snr_estimate, "
    "sf.quality_status, sf.quality_analyzed_at, "
    "COALESCE(d.common_name, d.primary_designation) AS target_name, "
    "r.name AS rig_name, "
    f"{_PIXEL_SCALE_SQL} AS pixel_scale_arcsec, "  # nosec B608
    f"{_FULL_SCALE_SQL} AS full_scale_adu, "  # nosec B608
    "fl.path AS path, fl.size_bytes AS file_size_bytes "
    "FROM sub_frame sf "
    "LEFT JOIN project_target pt ON pt.id = sf.project_target_id "
    "LEFT JOIN dso d ON d.id = pt.dso_id "
    "LEFT JOIN rig r ON r.id = sf.rig_id "
    # Optics + sensor of the tagged rig, for the pixel scale above. All LEFT:
    # an untagged rig or an incomplete equipment record must not drop the frame.
    "LEFT JOIN telescope_configuration tc ON tc.id = r.telescope_configuration_id "
    "LEFT JOIN camera cam ON cam.id = r.camera_id "
    "LEFT JOIN sensor sen ON sen.id = cam.sensor_id "
    "LEFT JOIN file_location fl ON fl.sub_frame_id = sf.id "
)


def _catalog_frame(d: dict) -> CatalogFrame:
    scale = d.get("pixel_scale_arcsec")
    binning = None
    if d.get("binning_x") and d.get("binning_y"):
        binning = f"{d['binning_x']}x{d['binning_y']}"
    return CatalogFrame(
        id=d["id"],
        kind="sub_frame",
        frame_type=d.get("frame_type"),
        path=d.get("path"),
        filter_name=d.get("filter_name_hint"),
        object_hint=d.get("object_hint"),
        exposure_seconds=d.get("exposure_seconds"),
        gain=d.get("gain"),
        set_temp_c=d.get("set_temp_c"),
        binning=binning,
        image_width=d.get("image_width"),
        image_height=d.get("image_height"),
        file_size_bytes=d.get("file_size_bytes"),
        date_obs_utc=d.get("date_obs_utc"),
        accepted=bool(d["accepted"]) if d.get("accepted") is not None else None,
        rig_name=d.get("rig_name"),
        project_target_id=d.get("project_target_id"),
        target_name=d.get("target_name"),
        frame_type_source=d.get("frame_type_source"),
        project_target_source=d.get("project_target_source"),
        hfr=d.get("hfr"),
        star_count=d.get("star_count"),
        median_adu=d.get("median_adu"),
        background_adu=d.get("background_adu"),
        snr_estimate=d.get("snr_estimate"),
        quality_status=d.get("quality_status"),
        quality_analyzed_at=d.get("quality_analyzed_at"),
        pixel_scale_arcsec=scale,
        full_scale_adu=d.get("full_scale_adu"),
        # Derived on read, never stored: re-tagging a folder's rig must change
        # this without re-measuring anything.
        hfr_arcsec=round(d["hfr"] * scale, 3) if d.get("hfr") and scale else None,
    )


# ── small coercion helpers ────────────────────────────────────────────────────


async def _count(conn, sql: str, params: tuple) -> int:
    cursor = await conn.execute(sql, params)
    row = await cursor.fetchone()
    return row[0] if row else 0


def _coerce_date_obs(value, fallback_mtime: str) -> str:
    text = _as_str(value)
    return text if text else fallback_mtime


def _as_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except _COERCE_ERRORS:
        return None


def _as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except _COERCE_ERRORS:
        return None


def _total_exposure(raw_header: dict, ncombine: int | None) -> float | None:
    """Total integration time for a master (seconds).

    PixInsight writes the summed exposure as PCL:TotalExposureTime; otherwise fall
    back to single-frame EXPTIME × frames-combined when both are known.
    """
    direct = _as_float(raw_header.get("PCL:TotalExposureTime"))
    if direct:
        return direct
    exp = _as_float(raw_header.get("EXPTIME"))
    if exp and ncombine:
        return exp * ncombine
    return None
