"""Directory-scan ingest pipeline + read-only catalog endpoints (v0.40.0).

The HTTP/DB boundary for cataloging a folder. Orchestrates:

    scan (fast walk) -> ProcessPool header parse -> equipment resolution
    -> content-hash UPSERT into sub_frame / processed_image / file_location
    -> session formation -> light-to-target assignment -> ingestion_run counters

This module owns the transaction; the pure services (ingest_scanner,
ingest_classify, ingest_sessions, equipment_resolver) never commit. One ingest
runs at a time per process (global single-flight, 409 if busy).

Catalog read endpoints are deliberately read-only — editing/curation is v0.41.0.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

from nightcrate.api._common import bool_fields, get_or_404, row_to_dict
from nightcrate.core import app_config
from nightcrate.core.config import get_settings
from nightcrate.db.session import get_db
from nightcrate.services.catalog_thumbnail import DEFAULT_MAX_PX, render_thumbnail_bytes
from nightcrate.services.equipment_resolver import (
    EquipmentResolver,
    ResolverStats,
    canonicalize_line_name,
)
from nightcrate.services.ingest_classify import (
    CATEGORY_LOG,
    CATEGORY_OTHER,
    CATEGORY_PROCESSED,
    CATEGORY_PXIPROJECT,
    classify_frame,
)
from nightcrate.services.ingest_models import (
    CatalogFilterStat,
    CatalogFrame,
    CatalogFramesPage,
    CatalogMaster,
    CatalogMastersPage,
    CatalogOther,
    CatalogOthersPage,
    CatalogSummary,
    IngestStatus,
    SourceFolder,
    SourceFolderCreate,
)
from nightcrate.services.ingest_scanner import (
    header_bearing,
    make_pool,
    parse_image_file,
    scan_directory,
)
from nightcrate.services.ingest_sessions import session_key

logger = logging.getLogger("nightcrate.ingest")
_LOG_PREFIX = "[ingest]"

# Module-level tuple: ruff format strips parens from inline ``except (A, B):`` on
# py3.14, producing invalid Py2 syntax. Referencing a constant sidesteps it.
_COERCE_ERRORS = (TypeError, ValueError)
_BAD_ZONE = (ZoneInfoNotFoundError, ValueError)

router = APIRouter(prefix="/api/projects", tags=["Projects"])

# Single-flight guard: at most one ingest run in flight per process.
_INGEST_LOCK = asyncio.Lock()

# Bound concurrent thumbnail renders so a grid drawing many cells can't stampede
# the loader (each render still reads a file). Renders run in a thread; results
# are cached on disk by content hash, so this only gates first-time renders.
_THUMB_SEM = asyncio.Semaphore(3)


def _thumb_cache_dir() -> Path:
    # Read APP_DIR at call time so the test harness's monkeypatch is honored.
    return app_config.APP_DIR / "catalog_thumbnails"


# ── Source-folder binding ─────────────────────────────────────────────────────


def _folder_response(d: dict) -> SourceFolder:
    bool_fields(d, "is_primary")
    return SourceFolder(**d)


@router.get("/{project_id}/folders", response_model=list[SourceFolder])
async def list_folders(project_id: int) -> list[SourceFolder]:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        cursor = await conn.execute(
            "SELECT * FROM project_source_folder WHERE project_id = ? "
            "ORDER BY is_primary DESC, added_at",
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
        try:
            cursor = await conn.execute(
                "INSERT INTO project_source_folder (project_id, path, is_primary) VALUES (?, ?, ?)",
                (project_id, path, 1 if make_primary else 0),
            )
        except Exception as exc:  # noqa: BLE001 - translate UNIQUE(project_id, path)
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="Folder already added") from exc
            raise
        await conn.commit()
        fid = cursor.lastrowid
        cursor = await conn.execute("SELECT * FROM project_source_folder WHERE id = ?", (fid,))
        return _folder_response(row_to_dict(await cursor.fetchone()))


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
        cursor = await conn.execute(
            "SELECT * FROM project_source_folder WHERE id = ?", (folder_id,)
        )
        return _folder_response(row_to_dict(await cursor.fetchone()))


@router.delete("/{project_id}/folders/{folder_id}", status_code=204)
async def remove_folder(project_id: int, folder_id: int) -> None:
    """Unbind a source folder AND drop everything cataloged from under it.

    Cataloged files are matched by path prefix (no DB-level folder FK exists).
    A sub/master that also has a file_location under another still-bound folder
    survives the orphan sweep; only items left with no file_location are deleted.
    Auto-sessions emptied by the removal are dropped too.
    """
    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        folder = await _get_folder_or_404(conn, project_id, folder_id)
        # Exact prefix match (folder + separator) so underscores/percent in real
        # paths can't act as LIKE wildcards. Covers archive/pxiproject virtual
        # paths too — they start with the on-disk folder path.
        prefix = folder["path"].rstrip("/") + "/"

        await conn.execute(
            "DELETE FROM file_location WHERE substr(path, 1, length(?)) = ?",
            (prefix, prefix),
        )
        # Orphan sweep: drop this project's subs/masters now lacking any file.
        await conn.execute(
            "DELETE FROM sub_frame WHERE id IN ("
            "  SELECT sf.id FROM sub_frame sf "
            "  JOIN ingestion_run r ON r.id = sf.ingestion_run_id "
            "  WHERE r.project_id = ? "
            "    AND NOT EXISTS (SELECT 1 FROM file_location fl WHERE fl.sub_frame_id = sf.id))",
            (project_id,),
        )
        await conn.execute(
            "DELETE FROM processed_image WHERE project_id = ? "
            "AND NOT EXISTS (SELECT 1 FROM file_location fl WHERE fl.processed_image_id = id)",
            (project_id,),
        )
        # Drop auto-sessions emptied by the removal (manual project_session is a
        # different table and untouched).
        await conn.execute(
            "DELETE FROM session WHERE project_id = ? "
            "AND NOT EXISTS (SELECT 1 FROM sub_frame sf WHERE sf.session_id = session.id)",
            (project_id,),
        )
        await conn.execute("DELETE FROM project_source_folder WHERE id = ?", (folder_id,))
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

        tz_name = await _project_geo_timezone(conn, project_id)
        target_id = await _project_single_target(conn, project_id)
        stats = ResolverStats()
        errors: list[dict] = []
        counters = {"scanned": 0, "inserted": 0, "updated": 0, "skipped": 0}

        # One spawn pool for the whole run, shut down via the context manager so no
        # worker processes linger (which would wedge `uvicorn --reload` restarts).
        # n_workers == 1 → parse inline, no pool at all.
        pool = make_pool(n_workers) if n_workers > 1 else None
        try:
            for folder in folders:
                await _ingest_folder(
                    conn,
                    project_id,
                    run_id,
                    folder,
                    pool,
                    tz_name,
                    target_id,
                    stats,
                    errors,
                    counters,
                )
            await _reclassify_dark_flats(conn, project_id)
            # Drop auto-sessions left with no sub_frames (e.g. orphaned when a
            # re-scan recomputes start_utc, or a folder's frames were removed).
            await conn.execute(
                "DELETE FROM session WHERE project_id = ? AND NOT EXISTS "
                "(SELECT 1 FROM sub_frame sf WHERE sf.session_id = session.id)",
                (project_id,),
            )
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
            "%s run %d %s: scanned=%d inserted=%d updated=%d skipped=%d errors=%d (resolver: %s)",
            _LOG_PREFIX,
            run_id,
            status,
            counters["scanned"],
            counters["inserted"],
            counters["updated"],
            counters["skipped"],
            len(errors),
            stats,
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


async def _ingest_folder(
    conn, project_id, run_id, folder, pool, tz_name, target_id, stats, errors, counters
) -> None:
    entries = scan_directory(folder)
    counters["scanned"] += len(entries)

    # Non-image categories: park a file_location row (no entity link).
    for entry in entries:
        if entry.category in (CATEGORY_PXIPROJECT, CATEGORY_LOG, CATEGORY_OTHER):
            await _upsert_plain_location(conn, entry)

    # Header-bearing files: parse in parallel, then persist on the main process.
    to_parse = header_bearing(entries)
    parsed = await _parse_in_pool(to_parse, pool)

    resolver = EquipmentResolver(conn)
    for result in parsed:
        if result.get("error"):
            errors.append({"path": result["path"], "error": result["error"]})
            continue
        try:
            await _persist_parsed(
                conn, project_id, run_id, result, resolver, tz_name, target_id, stats, counters
            )
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


async def _persist_parsed(
    conn, project_id, run_id, result, resolver, tz_name, target_id, stats, counters
) -> None:
    meta = result["meta"]
    raw_header = result["raw_header"]
    route, frame_type = classify_frame(meta, raw_header)

    camera = await resolver.resolve_camera(meta.get("camera_name"), source="nina", stats=stats)
    telescope = await resolver.resolve_telescope(
        meta.get("telescope_name"), source="nina", stats=stats
    )
    # No rig context yet (rig assignment is v0.41.0); filter line-name scoping is
    # skipped, so lights routinely resolve to NULL — kept as filter_name_hint.
    filt = await resolver.resolve_filter(meta.get("filter_name"), source="nina", stats=stats)

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
            camera.equipment_id,
            telescope.equipment_id,
            filt.equipment_id,
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
        camera.equipment_id,
        telescope.equipment_id,
        filt.equipment_id,
        date_obs,
    )
    counters["inserted" if was_insert else "updated"] += 1

    # Session formation: (rig_id, observing night). rig is NULL at v0.40.0.
    key = session_key(None, date_obs, tz_name)
    session_id = await _ensure_session(conn, project_id, key, tz_name)
    assigned_target = target_id if frame_type == "light" else None
    await conn.execute(
        "UPDATE sub_frame SET session_id = ?, project_target_id = ? WHERE id = ?",
        (session_id, assigned_target, sub_id),
    )
    await _link_file_location(conn, result, "sub_frame", sub_id)


async def _upsert_sub_frame(
    conn,
    project_id,
    run_id,
    result,
    meta,
    raw_header,
    frame_type,
    camera_id,
    telescope_id,
    filter_id,
    date_obs,
) -> tuple[int, bool]:
    content_hash = result["content_hash"]
    cursor = await conn.execute("SELECT id FROM sub_frame WHERE content_hash = ?", (content_hash,))
    existing = await cursor.fetchone()

    # Filters only matter for lights and flats. Darks / dark-flats / bias are
    # filterless by definition (calibration darks are never matched on filter),
    # so drop any FILTER the header happened to carry.
    keeps_filter = frame_type in ("light", "flat")

    cols = {
        "frame_type": frame_type,
        "camera_id": camera_id,
        "telescope_id": telescope_id,
        "filter_id": filter_id if keeps_filter else None,
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
        cols["content_hash"] = content_hash
        names = ", ".join(cols)
        placeholders = ", ".join("?" for _ in cols)
        cursor = await conn.execute(
            f"INSERT INTO sub_frame ({names}) VALUES ({placeholders})",  # nosec B608 - column names from fixed internal dict, not user input
            tuple(cols.values()),
        )
        return cursor.lastrowid, True

    set_clause = ", ".join(f"{k} = ?" for k in cols)
    await conn.execute(
        f"UPDATE sub_frame SET {set_clause} WHERE id = ?",  # nosec B608 - column names from fixed internal dict, not user input
        (*cols.values(), existing["id"]),
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
    camera_id,
    telescope_id,
    filter_id,
    date_obs,
    counters,
) -> None:
    content_hash = result["content_hash"]
    cursor = await conn.execute(
        "SELECT id FROM processed_image WHERE content_hash = ?", (content_hash,)
    )
    existing = await cursor.fetchone()
    # No rig context for masters → filter_id rarely resolves. Fall back to the
    # bandpass parsed from the FILTER keyword (e.g. "Ha") so the Masters tab can
    # show a filter. Only lights/flats carry a filter; darks/bias stay NULL.
    line_name = None
    if frame_type in ("light", "flat") and not filter_id:
        line_name = canonicalize_line_name(raw_header.get("FILTER") or "")
    ncombine = (
        _as_int(meta.get("pi_ncombine"))
        or _as_int(raw_header.get("STACKCNT"))
        or _as_int(raw_header.get("NIMAGES"))
    )
    cols = {
        "project_id": project_id,
        "image_kind": "master",
        "frame_type": frame_type,
        "filter_id": filter_id,
        "line_name": line_name,
        "camera_id": camera_id,
        "telescope_id": telescope_id,
        "ncombine": ncombine,
        "total_exposure_seconds": _total_exposure(raw_header, ncombine),
        "date_obs_utc": date_obs,
        "image_width": _as_int(meta.get("image_width")),
        "image_height": _as_int(meta.get("image_height")),
        "fits_header_json": json.dumps(raw_header),
        "ingestion_run_id": run_id,
    }
    if existing is None:
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
    await _link_file_location(conn, result, "processed", pid)


async def _link_file_location(conn, result, category, entity_id) -> None:
    # col is one of two literals chosen above — never user input.
    col = "sub_frame_id" if category == "sub_frame" else "processed_image_id"
    await conn.execute(
        f"INSERT INTO file_location (path, category, {col}, file_hash, size_bytes, mtime) "  # nosec B608 - col is a fixed literal, not user input
        f"VALUES (?, ?, ?, ?, ?, ?) "
        f"ON CONFLICT(path) DO UPDATE SET category = excluded.category, "
        f"{col} = excluded.{col}, file_hash = excluded.file_hash, "
        f"size_bytes = excluded.size_bytes, mtime = excluded.mtime",
        (
            result["path"],
            category,
            entity_id,
            result["content_hash"],
            result.get("size_bytes"),
            result.get("mtime"),
        ),
    )


async def _upsert_plain_location(conn, entry) -> None:
    await conn.execute(
        "INSERT INTO file_location (path, category, size_bytes, mtime) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET category = excluded.category, "
        "size_bytes = excluded.size_bytes, mtime = excluded.mtime",
        (entry.path, entry.category, entry.size_bytes or None, entry.mtime),
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
    """
    await conn.execute(
        "UPDATE sub_frame SET frame_type = 'dark_flat' WHERE id IN ("
        "  SELECT sf.id FROM sub_frame sf "
        "  JOIN ingestion_run r ON r.id = sf.ingestion_run_id "
        "  WHERE r.project_id = ? AND sf.frame_type = 'dark' AND sf.exposure_seconds > 0 "
        "    AND EXISTS ("
        "      SELECT 1 FROM sub_frame f "
        "      JOIN ingestion_run rf ON rf.id = f.ingestion_run_id "
        "      WHERE rf.project_id = ? AND f.frame_type = 'flat' "
        "        AND f.exposure_seconds BETWEEN sf.exposure_seconds * 0.8 "
        "                                   AND sf.exposure_seconds * 1.25) "
        "    AND NOT EXISTS ("
        "      SELECT 1 FROM sub_frame l "
        "      JOIN ingestion_run rl ON rl.id = l.ingestion_run_id "
        "      WHERE rl.project_id = ? AND l.frame_type = 'light' "
        "        AND l.exposure_seconds BETWEEN sf.exposure_seconds * 0.8 "
        "                                   AND sf.exposure_seconds * 1.25)"
        ")",
        (project_id, project_id, project_id),
    )


def _observing_window_utc(night: str, tz_name: str | None) -> tuple[str, str]:
    """UTC bounds of the noon-to-noon observing night `night` (local date in the
    site's geo timezone). The previous code stamped a literal noon-UTC, which is
    wrong for any non-UTC site (e.g. UTC-7 → real window start is 19:00 UTC);
    v0.43's PHD2 time-range association needs the true UTC window."""
    try:
        tz = ZoneInfo(tz_name) if tz_name else UTC
    except _BAD_ZONE:
        tz = UTC
    d = date.fromisoformat(night)
    start = datetime(d.year, d.month, d.day, 12, 0, tzinfo=tz)
    nxt = d + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, 12, 0, tzinfo=tz)
    return start.astimezone(UTC).isoformat(), end.astimezone(UTC).isoformat()


async def _ensure_session(conn, project_id, key, tz_name: str | None) -> int:
    rig_id, night = key
    start_utc, end_utc = _observing_window_utc(night, tz_name)
    # Identity is (project, observing-night start, rig); start_utc is deterministic
    # per (night, geo-tz) so re-ingest dedupes to the same row.
    cursor = await conn.execute(
        "SELECT id FROM session WHERE project_id = ? AND start_utc = ? AND rig_id IS ?",
        (project_id, start_utc, rig_id),
    )
    row = await cursor.fetchone()
    if row is not None:
        return row["id"]
    cursor = await conn.execute(
        "INSERT INTO session (project_id, rig_id, start_utc, end_utc) VALUES (?, ?, ?, ?)",
        (project_id, rig_id, start_utc, end_utc),
    )
    return cursor.lastrowid


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


async def _project_geo_timezone(conn, project_id) -> str | None:
    cursor = await conn.execute(
        "SELECT l.geo_timezone, l.timezone FROM project p "
        "LEFT JOIN location l ON l.id = p.location_id WHERE p.id = ?",
        (project_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return row["geo_timezone"] or row["timezone"]


async def _project_single_target(conn, project_id) -> int | None:
    cursor = await conn.execute(
        "SELECT id FROM project_target WHERE project_id = ? ORDER BY id LIMIT 2",
        (project_id,),
    )
    rows = await cursor.fetchall()
    return rows[0]["id"] if len(rows) == 1 else None


async def _project_file_scope(conn, project_id: int) -> tuple[str, list]:
    """SQL predicate + params limiting `file_location` rows to files under the
    project's source folders. `file_location` has no project link (it's global —
    standalone non-frame files carry no FK), so non-frame counts/listings are
    scoped by path prefix against the project's bound folders. Exact-prefix match
    (`substr`) so underscores/percent in real paths can't act as LIKE wildcards.
    Returns a clause that matches NOTHING when the project has no folders."""
    cursor = await conn.execute(
        "SELECT path FROM project_source_folder WHERE project_id = ?", (project_id,)
    )
    prefixes = [r["path"].rstrip("/") + "/" for r in await cursor.fetchall()]
    if not prefixes:
        return "0", []
    clause = "(" + " OR ".join("substr(path, 1, length(?)) = ?" for _ in prefixes) + ")"
    params: list = []
    for p in prefixes:
        params.extend([p, p])
    return clause, params


# ── Catalog (read-only) ───────────────────────────────────────────────────────


@router.get("/{project_id}/catalog/summary", response_model=CatalogSummary)
async def catalog_summary(project_id: int) -> CatalogSummary:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        s = CatalogSummary()
        cursor = await conn.execute(
            "SELECT frame_type, COUNT(*) AS n FROM sub_frame sf "
            "JOIN ingestion_run r ON r.id = sf.ingestion_run_id "
            "WHERE r.project_id = ? GROUP BY frame_type",
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
        # Non-frame file counts (pxiproject/log/other) scoped to files under the
        # project's source folders (file_location has no project FK — see
        # _project_file_scope). file_clause is a generated literal; values bound.
        file_clause, file_params = await _project_file_scope(conn, project_id)
        cursor = await conn.execute(
            "SELECT category, COUNT(*) AS n FROM file_location "  # nosec B608
            f"WHERE {file_clause} GROUP BY category",
            file_params,
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
) -> CatalogFramesPage:
    # Optional frame_type filter (drives the count-pill filtering in the UI).
    type_clause = ""
    type_params: tuple = ()
    if frame_type in ("light", "dark", "flat", "bias", "dark_flat", "unknown"):
        type_clause = " AND sf.frame_type = ?"
        type_params = (frame_type,)
    # Optional filter-name scope (clicking a Lights/Flats filter pill). Matches the
    # same COALESCE(model, hint) the pills are grouped by.
    filter_clause = ""
    filter_params: tuple = ()
    if filter_name:
        filter_clause = " AND COALESCE(f.model_name, sf.filter_name_hint) = ?"
        filter_params = (filter_name,)
    # Flats are organised per-filter (you match flats to lights by filter), so sort
    # by filter first. Lights/calibration sort by path so raw vs per-stage outputs
    # bunch together; date_obs is the within-group tiebreak.
    if frame_type == "flat":
        order_clause = (
            "ORDER BY COALESCE(f.model_name, sf.filter_name_hint), fl.path, sf.date_obs_utc, sf.id"
        )
    else:
        order_clause = "ORDER BY fl.path, sf.date_obs_utc, sf.id"
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        total = await _count(
            conn,
            "SELECT COUNT(*) FROM sub_frame sf JOIN ingestion_run r ON r.id = sf.ingestion_run_id "
            "LEFT JOIN filter f ON f.id = sf.filter_id "
            # nosec B608 - clauses are fixed literals; values are parameterized
            f"WHERE r.project_id = ?{type_clause}{filter_clause}",
            (project_id, *type_params, *filter_params),
        )
        cursor = await conn.execute(
            "SELECT sf.id, sf.frame_type, sf.filter_name_hint, f.model_name AS filter_model, "
            "sf.object_hint, sf.exposure_seconds, sf.gain, sf.set_temp_c, sf.binning_x, "
            "sf.binning_y, sf.image_width, sf.image_height, sf.date_obs_utc, sf.camera_id, "
            "sf.telescope_id, sf.accepted, fl.path AS path, fl.size_bytes AS file_size_bytes "
            "FROM sub_frame sf "
            "JOIN ingestion_run r ON r.id = sf.ingestion_run_id "
            "LEFT JOIN filter f ON f.id = sf.filter_id "
            "LEFT JOIN file_location fl ON fl.sub_frame_id = sf.id "
            # nosec B608 - clauses are fixed literals; values are parameterized
            f"WHERE r.project_id = ?{type_clause}{filter_clause} "
            f"GROUP BY sf.id {order_clause} LIMIT ? OFFSET ?",
            (project_id, *type_params, *filter_params, limit, offset),
        )
        rows = [_catalog_frame(row_to_dict(r)) for r in await cursor.fetchall()]
        tz = await _project_display_tz(conn, project_id)
        return CatalogFramesPage(rows=rows, total=total, timezone=tz)


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
            "SELECT COALESCE(f.model_name, sf.filter_name_hint) AS filter_name, "
            "COUNT(*) AS n, COALESCE(SUM(sf.exposure_seconds), 0) AS total "
            "FROM sub_frame sf "
            "JOIN ingestion_run r ON r.id = sf.ingestion_run_id "
            "LEFT JOIN filter f ON f.id = sf.filter_id "
            "WHERE r.project_id = ? AND sf.frame_type = ? "
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
            "f.model_name AS filter_model, pi.ncombine, pi.total_exposure_seconds, "
            "pi.image_width, pi.image_height, pi.date_obs_utc, "
            "fl.path AS path, fl.size_bytes AS file_size_bytes "
            "FROM processed_image pi "
            "LEFT JOIN filter f ON f.id = pi.filter_id "
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
) -> CatalogOthersPage:
    """Catch-all: PixInsight projects, logs, other files, and unknown-type subs."""
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        # Non-frame files under the project's source folders (file_location has no
        # project FK — scoped by path prefix, see _project_file_scope) + this
        # project's unknown-type subs. file_clause is a generated literal; values bound.
        file_clause, file_params = await _project_file_scope(conn, project_id)
        file_rows = await (
            await conn.execute(
                "SELECT id, category, path, size_bytes, mtime FROM file_location "  # nosec B608
                f"WHERE category IN ('pxiproject', 'log', 'other') AND {file_clause} "
                "ORDER BY category, path",
                file_params,
            )
        ).fetchall()
        unknown_rows = await (
            await conn.execute(
                "SELECT sf.id, sf.date_obs_utc, fl.path AS path "
                "FROM sub_frame sf "
                "JOIN ingestion_run r ON r.id = sf.ingestion_run_id "
                "LEFT JOIN file_location fl ON fl.sub_frame_id = sf.id "
                "WHERE r.project_id = ? AND sf.frame_type = 'unknown' "
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
        filter_name=d.get("filter_model") or d.get("line_name"),
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
            "JOIN ingestion_run r ON r.id = sf.ingestion_run_id "
            "LEFT JOIN file_location fl ON fl.sub_frame_id = sf.id "
            "WHERE sf.id = ? AND r.project_id = ? "
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


def _catalog_frame(d: dict) -> CatalogFrame:
    binning = None
    if d.get("binning_x") and d.get("binning_y"):
        binning = f"{d['binning_x']}x{d['binning_y']}"
    return CatalogFrame(
        id=d["id"],
        kind="sub_frame",
        frame_type=d.get("frame_type"),
        path=d.get("path"),
        filter_name=d.get("filter_model") or d.get("filter_name_hint"),
        object_hint=d.get("object_hint"),
        exposure_seconds=d.get("exposure_seconds"),
        gain=d.get("gain"),
        set_temp_c=d.get("set_temp_c"),
        binning=binning,
        image_width=d.get("image_width"),
        image_height=d.get("image_height"),
        file_size_bytes=d.get("file_size_bytes"),
        date_obs_utc=d.get("date_obs_utc"),
        camera_id=d.get("camera_id"),
        telescope_id=d.get("telescope_id"),
        accepted=bool(d["accepted"]) if d.get("accepted") is not None else None,
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
