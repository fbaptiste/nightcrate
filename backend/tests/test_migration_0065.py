"""Preservation tests for migration 0065's solver provenance columns."""

import sqlite3
from pathlib import Path

import pytest
from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR, apply_migrations


def _apply_through_0064(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        through_0064 = backend.to_apply(migrations).filter(
            lambda migration: migration.id != "0065.project_solve_solver"
        )
        backend.apply_migrations(through_0064)


def _insert_solve(conn: sqlite3.Connection, number: int) -> tuple[int, int, int]:
    project_id = int(
        conn.execute("INSERT INTO project (name) VALUES (?)", (f"Project {number}",)).lastrowid
    )
    solve_id = int(
        conn.execute(
            """
            INSERT INTO project_solve (
                project_id, image_path, image_width, image_height,
                center_ra_deg, center_dec_deg, ra_hms, dec_dms,
                pixel_scale_arcsec, rotation_deg, fov_width_arcmin, fov_height_arcmin,
                cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2, solved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                f"image-{number}.fits",
                1000 + number,
                800 + number,
                80.0 + number,
                -5.0 - number,
                f"0{number}h",
                f"-0{number}d",
                1.5 + number,
                30.0 + number,
                40.0 + number,
                30.0 + number,
                -0.001,
                0.0002,
                0.0002,
                0.001,
                500.5,
                400.5,
                f"2026-01-0{number} 01:02:03",
            ),
        ).lastrowid
    )
    source_id = int(
        conn.execute(
            """
            INSERT INTO dso_catalog_source
                (source_id, category, display_name, file_path, file_hash, row_count)
            VALUES (?, 'openngc', ?, '/tmp/test', ?, 1)
            """,
            (f"test-{number}", f"Test {number}", f"hash-{number}"),
        ).lastrowid
    )
    dso_id = int(
        conn.execute(
            """
            INSERT INTO dso
                (primary_designation, obj_type, source_catalog_id, source_row_hash)
            VALUES (?, 'G', ?, ?)
            """,
            (f"TEST {number}", source_id, f"row-{number}"),
        ).lastrowid
    )
    link_id = int(
        conn.execute(
            "INSERT INTO project_dso (solve_id, dso_id, is_main) VALUES (?, ?, ?)",
            (solve_id, dso_id, number % 2),
        ).lastrowid
    )
    return solve_id, link_id, dso_id


def test_migration_0065(tmp_path):
    db_path = tmp_path / "before_0065.db"
    _apply_through_0064(db_path)
    with sqlite3.connect(db_path) as conn:
        first = _insert_solve(conn, 1)
        second = _insert_solve(conn, 2)
        conn.row_factory = sqlite3.Row
        original_solves = [dict(row) for row in conn.execute("SELECT * FROM project_solve")]
        original_links = [dict(row) for row in conn.execute("SELECT * FROM project_dso")]
        conn.commit()

    apply_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute("SELECT * FROM project_solve ORDER BY id")]
        links = [dict(row) for row in conn.execute("SELECT * FROM project_dso ORDER BY id")]
        assert [row["id"] for row in rows] == [first[0], second[0]]
        for before, after in zip(original_solves, rows, strict=True):
            assert {key: after[key] for key in before} == before
            assert after["solver"] == "astap"
            for key in (
                "star_catalog",
                "stars_detected",
                "stars_matched",
                "rms_px",
                "log_odds",
                "solve_path",
                "scale_stage",
            ):
                assert after[key] is None
        assert links == original_links
        assert [(row["id"], row["solve_id"], row["dso_id"]) for row in links] == [
            (first[1], first[0], first[2]),
            (second[1], second[0], second[2]),
        ]
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO project_solve (
                    project_id, image_path, image_width, image_height,
                    center_ra_deg, center_dec_deg, cd1_1, cd1_2, cd2_1, cd2_2,
                    crpix1, crpix2, solver
                ) VALUES (999, 'x', 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 'x')
                """
            )

    fresh = tmp_path / "fresh.db"
    apply_migrations(fresh)
    with sqlite3.connect(fresh) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(project_solve)")}
    assert "solver" in columns
    assert "scale_stage" in columns
