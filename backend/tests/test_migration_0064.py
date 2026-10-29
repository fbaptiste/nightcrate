"""Regression tests for migration 0064's saved-solve row correction."""

import math
import sqlite3
from pathlib import Path

import pytest
from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR, apply_migrations
from nightcrate.db.session import get_db
from nightcrate.services.plate_solve import _compute_results


def _apply_through_0063(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        through_0063 = backend.to_apply(migrations).filter(
            lambda migration: migration.id != "0064.project_solve_row_order"
        )
        backend.apply_migrations(through_0063)


def _insert_solve(
    conn: sqlite3.Connection,
    image_path: str,
    *,
    image_height: int = 1000,
    crpix2: float = 200.0,
    cd1_1: float = 1.0,
    cd1_2: float = 2.0,
    cd2_1: float = 3.0,
    cd2_2: float = -4.0,
    rotation_deg: float = 30.0,
) -> int:
    project_id = conn.execute(
        "INSERT INTO project (name) VALUES (?)", (f"Project {image_path}",)
    ).lastrowid
    cursor = conn.execute(
        """
        INSERT INTO project_solve (
            project_id, image_path, image_width, image_height,
            center_ra_deg, center_dec_deg, rotation_deg,
            cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2
        ) VALUES (?, ?, 1200, ?, 83.633, -5.375, ?, ?, ?, ?, ?, 600.0, ?)
        """,
        (
            project_id,
            image_path,
            image_height,
            rotation_deg,
            cd1_1,
            cd1_2,
            cd2_1,
            cd2_2,
            crpix2,
        ),
    )
    return int(cursor.lastrowid)


async def test_conftest_applies_python_migrations():
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT 1 FROM _yoyo_migration WHERE migration_id = ?",
            ("0064.project_solve_row_order",),
        )
        assert await cursor.fetchone() is not None


def test_migration_0064_flips_only_standard_files(tmp_path):
    db_path = tmp_path / "before_0064.db"
    _apply_through_0063(db_path)
    with sqlite3.connect(db_path) as conn:
        png_id = _insert_solve(conn, "a.PNG")
        archive_id = _insert_solve(conn, "b.zip::c.png")
        fits_id = _insert_solve(conn, "d.fits")
        conn.commit()

    apply_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        rows = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT id, crpix2, cd1_2, cd2_2, rotation_deg FROM project_solve"
            )
        }
    assert rows[png_id] == pytest.approx((801.0, -2.0, 4.0, math.degrees(math.atan2(2, 4))))
    assert rows[archive_id] == pytest.approx((200.0, 2.0, -4.0, 30.0))
    assert rows[fits_id] == pytest.approx((200.0, 2.0, -4.0, 30.0))


def test_migration_0064_rotation_cases(tmp_path):
    db_path = tmp_path / "rotation_before_0064.db"
    _apply_through_0063(db_path)
    m74 = {
        "image_height": 3008,
        "crpix2": 1504.5,
        "cd1_1": 3.1708226849663004e-4,
        "cd1_2": 1.6613319845650712e-4,
        "cd2_1": 1.6618754352258259e-4,
        "cd2_2": -3.1700913753065986e-4,
    }
    unequal = {
        "cd1_1": 0.8660254e-4,
        "cd1_2": -0.5075384e-4,
        "cd2_1": 0.5e-4,
        "cd2_2": 0.8616292e-4,
    }
    with sqlite3.connect(db_path) as conn:
        crota_id = _insert_solve(conn, "crota.png", rotation_deg=-152.335, **m74)
        fallback_id = _insert_solve(conn, "fallback.jpeg", rotation_deg=27.660, **m74)
        unequal_id = _insert_solve(conn, "unequal.tif", rotation_deg=30.0, **unequal)
        conn.commit()

    apply_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        rotations = dict(conn.execute("SELECT id, rotation_deg FROM project_solve"))
    assert rotations[crota_id] == pytest.approx(27.657, abs=0.001)
    assert rotations[fallback_id] == pytest.approx(27.657, abs=0.001)

    runtime = _compute_results(
        {
            "PLTSOLVD": "T",
            "CD1_1": str(unequal["cd1_1"]),
            "CD1_2": str(unequal["cd1_2"]),
            "CD2_1": str(unequal["cd2_1"]),
            "CD2_2": str(unequal["cd2_2"]),
            "CRPIX2": "200.0",
        },
        1200,
        1000,
        flip_rows=True,
    )
    assert rotations[unequal_id] == pytest.approx(runtime.rotation_deg, abs=0.0005)
