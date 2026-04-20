"""Tests for the Hubble-law redshift distance backfill.

Exercises the final pass in ``load_catalogs`` that assigns
``distance_method='redshift'`` to galaxies with a known redshift but no
curated or 50 MGC distance. Verifies the precedence chain
``curated > 50 MGC > redshift`` and the galaxy-only, positive-z gating.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader.redshift_distance import apply_redshift_distances
from nightcrate.services.astronomy import (
    HUBBLE_CONSTANT_KM_S_MPC,
    SPEED_OF_LIGHT_KM_S,
    redshift_to_parsecs,
)


def _apply_full_schema(db: sqlite3.Connection) -> None:
    """Run every migration from 0005 onward — same pattern as conftest.py."""
    import importlib.resources

    # Migration 0011 reshapes an existing settings table; create a placeholder
    # so the migration's ALTER/INSERT statements resolve.
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data TEXT NOT NULL DEFAULT '{}'
        );
        INSERT OR IGNORE INTO settings (id, data) VALUES (1, '{}');
        """
    )

    migrations_dir = importlib.resources.files("nightcrate") / "db" / "migrations"
    for name in sorted(f.name for f in migrations_dir.iterdir() if f.name.endswith(".sql")):
        if name >= "0005":
            body = "\n".join(
                line
                for line in (migrations_dir / name).read_text().split("\n")
                if not line.strip().startswith("-- depends:")
            )
            db.executescript(body)
    db.commit()


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(tmp_path / "redshift.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _apply_full_schema(conn)
    # A catalog source row is required by dso.source_catalog_id FK.
    conn.execute(
        """
        INSERT INTO dso_catalog_source (
            source_id, category, display_name, file_path, file_hash
        ) VALUES ('test', 'openngc', 'Test source', '/dev/null', 'abc')
        """
    )
    conn.commit()
    return conn


def _insert_dso(
    db: sqlite3.Connection,
    *,
    name: str,
    obj_type: str,
    redshift: float | None,
    distance_pc: float | None = None,
    distance_method: str | None = None,
) -> int:
    """Insert a minimal DSO row and return its id."""
    cur = db.execute(
        """
        INSERT INTO dso (
            primary_designation, obj_type, redshift,
            distance_pc, distance_method,
            source_catalog_id, source_row_hash
        ) VALUES (?, ?, ?, ?, ?, 1, 'r')
        """,
        (name, obj_type, redshift, distance_pc, distance_method),
    )
    db.commit()
    dso_id = cur.lastrowid
    assert dso_id is not None
    return dso_id


def test_galaxy_with_positive_redshift_gets_hubble_distance(db):
    dso_id = _insert_dso(db, name="TEST G1", obj_type="G", redshift=0.02)

    summary = apply_redshift_distances(db)

    row = db.execute(
        "SELECT distance_pc, distance_method FROM dso WHERE id = ?", (dso_id,)
    ).fetchone()
    assert row["distance_method"] == "redshift"
    # z=0.02 → d = 0.02 * 299792.458 / 70 Mpc ≈ 85.655 Mpc ≈ 8.565e7 pc
    expected = (0.02 * SPEED_OF_LIGHT_KM_S / HUBBLE_CONSTANT_KM_S_MPC) * 1_000_000.0
    assert row["distance_pc"] == pytest.approx(expected, rel=1e-9)
    assert summary.distances_applied == 1
    assert summary.galaxies_considered == 1


def test_curated_distance_is_preserved(db):
    """Rule: redshift never wins over a curated distance."""
    dso_id = _insert_dso(
        db,
        name="TEST G2",
        obj_type="G",
        redshift=0.02,
        distance_pc=10_000_000.0,
        distance_method="curated",
    )

    apply_redshift_distances(db)

    row = db.execute(
        "SELECT distance_pc, distance_method FROM dso WHERE id = ?", (dso_id,)
    ).fetchone()
    assert row["distance_method"] == "curated"
    assert row["distance_pc"] == pytest.approx(10_000_000.0)


def test_50mgc_distance_is_preserved(db):
    """Rule: redshift never wins over a 50 MGC distance."""
    dso_id = _insert_dso(
        db,
        name="TEST G3",
        obj_type="G",
        redshift=0.02,
        distance_pc=5_000_000.0,
        distance_method="50mgc",
    )

    apply_redshift_distances(db)

    row = db.execute(
        "SELECT distance_pc, distance_method FROM dso WHERE id = ?", (dso_id,)
    ).fetchone()
    assert row["distance_method"] == "50mgc"
    assert row["distance_pc"] == pytest.approx(5_000_000.0)


def test_non_galaxy_is_skipped_even_with_redshift(db):
    """Redshift-based Hubble distances only make sense for galaxies — a
    planetary nebula with a redshift value should be left alone."""
    dso_id = _insert_dso(db, name="TEST PN", obj_type="PN", redshift=0.01)

    summary = apply_redshift_distances(db)

    row = db.execute(
        "SELECT distance_pc, distance_method FROM dso WHERE id = ?", (dso_id,)
    ).fetchone()
    assert row["distance_method"] is None
    assert row["distance_pc"] is None
    assert summary.distances_applied == 0


def test_zero_or_negative_redshift_is_skipped(db):
    """Blueshifted (Local Group) and zero-redshift rows must be skipped —
    the Hubble formula is meaningless for them."""
    dso_zero = _insert_dso(db, name="TEST Z0", obj_type="G", redshift=0.0)
    dso_neg = _insert_dso(db, name="TEST NEG", obj_type="G", redshift=-0.001)

    summary = apply_redshift_distances(db)

    for dso_id in (dso_zero, dso_neg):
        row = db.execute(
            "SELECT distance_pc, distance_method FROM dso WHERE id = ?", (dso_id,)
        ).fetchone()
        assert row["distance_method"] is None
        assert row["distance_pc"] is None
    assert summary.skipped_non_positive_z == 2
    assert summary.distances_applied == 0


def test_galaxy_pair_and_group_types_are_included(db):
    """``GPair``, ``GTrpl``, ``GGroup`` share the galaxy-type vocabulary."""
    ids = [
        _insert_dso(db, name="TEST GP", obj_type="GPair", redshift=0.01),
        _insert_dso(db, name="TEST GT", obj_type="GTrpl", redshift=0.01),
        _insert_dso(db, name="TEST GG", obj_type="GGroup", redshift=0.01),
    ]

    summary = apply_redshift_distances(db)

    for dso_id in ids:
        row = db.execute("SELECT distance_method FROM dso WHERE id = ?", (dso_id,)).fetchone()
        assert row["distance_method"] == "redshift"
    assert summary.distances_applied == 3


def test_rerun_is_idempotent(db):
    """Calling the backfill twice produces the same state — prior
    redshift-derived distances are cleared and reapplied."""
    dso_id = _insert_dso(db, name="TEST GI", obj_type="G", redshift=0.015)

    apply_redshift_distances(db)
    first = db.execute(
        "SELECT distance_pc, distance_method FROM dso WHERE id = ?", (dso_id,)
    ).fetchone()

    apply_redshift_distances(db)
    second = db.execute(
        "SELECT distance_pc, distance_method FROM dso WHERE id = ?", (dso_id,)
    ).fetchone()

    assert first["distance_method"] == "redshift"
    assert second["distance_method"] == "redshift"
    assert first["distance_pc"] == pytest.approx(second["distance_pc"])


def test_redshift_to_parsecs_sanity():
    """Pinned formula regression: z=0.02 → ~85.655 Mpc."""
    d_pc = redshift_to_parsecs(0.02)
    assert d_pc is not None
    # d = 0.02 * 299792.458 / 70 Mpc ≈ 85.65499 Mpc
    assert d_pc == pytest.approx(85_654_987.99, abs=1.0)


def test_redshift_to_parsecs_rejects_non_positive():
    """Helper must reject z <= 0 rather than returning negative distances."""
    assert redshift_to_parsecs(0.0) is None
    assert redshift_to_parsecs(-0.001) is None
