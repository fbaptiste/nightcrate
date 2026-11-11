"""Safety tests for the synthetic gallery workspace script."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite
import pytest
from PIL import Image

from nightcrate.db.session import get_db_path
from nightcrate.services.project_images import CROP_SIZES, crop_path
from scripts.make_gallery_workspace import _backup_database, _build
from tests.gallery_library import make_library_dsos


def test_backup_database_includes_uncheckpointed_wal_without_touching_source(
    tmp_path: Path,
):
    source = tmp_path / "source.db"
    destination = tmp_path / "copy.db"
    writer = sqlite3.connect(source)
    try:
        assert writer.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute("CREATE TABLE example (value TEXT NOT NULL)")
        writer.commit()
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        writer.execute("INSERT INTO example VALUES ('committed in WAL')")
        writer.commit()

        wal = source.with_name(f"{source.name}-wal")
        assert wal.is_file()
        assert wal.stat().st_size > 0
        source_bytes = source.read_bytes()
        source_mtime_ns = source.stat().st_mtime_ns

        _backup_database(source, destination)

        with sqlite3.connect(destination) as copied:
            assert copied.execute("SELECT value FROM example").fetchall() == [("committed in WAL",)]
        assert source.read_bytes() == source_bytes
        assert source.stat().st_mtime_ns == source_mtime_ns
    finally:
        writer.close()


@pytest.mark.asyncio
async def test_build_writes_deterministic_framed_thumbnail_rows_and_files(tmp_path: Path):
    source = get_db_path()
    async with aiosqlite.connect(source) as conn:
        await make_library_dsos(conn)

    destination = tmp_path / "gallery-workspace"
    destination.mkdir()
    await _build(source, destination, projects=12, seed=46)

    destination_db = destination / "nightcrate.db"
    with sqlite3.connect(destination_db) as conn:
        rows = conn.execute(
            """
            SELECT id, project_id, size, source_image_id,
                   crop_x, crop_y, crop_w, crop_h
            FROM project_thumbnail
            ORDER BY project_id, size
            """
        ).fetchall()
        solved_with_images = conn.execute(
            """
            SELECT COUNT(*)
            FROM project p
            JOIN project_image pi ON pi.project_id = p.id AND pi.is_main = 1
            JOIN project_solve ps ON ps.project_id = p.id
            """
        ).fetchone()[0]
        main_images = conn.execute(
            "SELECT COUNT(*) FROM project_image WHERE is_main = 1"
        ).fetchone()[0]
        known = conn.execute(
            """
            SELECT p.id, p.name, ps.id, ps.center_ra_deg, ps.center_dec_deg,
                   ps.image_width, ps.image_height
            FROM project p
            JOIN project_solve ps ON ps.project_id = p.id
            WHERE p.name IN ('Leo Triplet', 'Hamburger Galaxy', 'Markarian''s Chain')
            ORDER BY p.name
            """
        ).fetchall()

    assert len(rows) == 6
    assert {row[2] for row in rows} == set(CROP_SIZES)
    assert {row[3] for row in rows} == {None}
    assert len({row[1] for row in rows}) == 2
    assert len({tuple(row[4:]) for row in rows}) == 2
    assert solved_with_images == main_images
    assert len(known) == 3
    assert {(row[5], row[6]) for row in known} == {(1200, 900)}

    for row_id, project_id, size, *_ in rows:
        path = crop_path(destination / "project_data" / str(project_id), size, row_id)
        assert path.is_file()
        with Image.open(path) as image:
            assert image.size == CROP_SIZES[size]

    for project_id, _name, solve_id, *_ in known:
        solve_dir = destination / "project_data" / str(project_id) / "solve" / str(solve_id)
        assert {path.name for path in solve_dir.glob("*.jpg")} == {
            "full.jpg",
            "thumb_lg.jpg",
            "thumb_md.jpg",
            "thumb_sm.jpg",
        }
