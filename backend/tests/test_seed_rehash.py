"""Tests for the one-shot re-hash steps (seed_loader/rehash.py).

These cover the case the loader's ordinary "the row still matches the CSV" repair
cannot: a release that changes a table's seeded_fields *and* changes CSV values for
some of its rows. Without a step, an untouched-but-stale row is indistinguishable
from an edited one and is stranded permanently.
"""

import importlib.resources
import sqlite3

import pytest

from nightcrate.seed_loader.hash import compute_seed_hash
from nightcrate.seed_loader.loader import load_all
from nightcrate.seed_loader.rehash import REHASH_STEPS

SENSOR_HEADER = (
    "seed_key,manufacturer_seed_key,adc_bit_depth,bayer_pattern,dual_gain,"
    "full_well_capacity_ke,model_name,notes,peak_qe_pct,pixel_size_um,"
    "read_noise_low_gain_e,read_noise_high_gain_e,resolution_x,resolution_y,"
    "sensor_height_mm,sensor_type,sensor_width_mm,source_url"
)
MFR_HEADER = "seed_key,name,notes,website"


@pytest.fixture
def seed_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrations_dir = importlib.resources.files("nightcrate") / "db" / "migrations"
    for name in sorted(f.name for f in migrations_dir.iterdir() if f.name.endswith(".sql")):
        sql = (migrations_dir / name).read_text()
        conn.executescript(
            "\n".join(
                line for line in sql.split("\n") if not line.strip().startswith("-- depends:")
            )
        )
    yield conn
    conn.close()


@pytest.fixture
def csv_root(tmp_path):
    seed_dir = importlib.resources.files("nightcrate") / "data" / "seed"
    dest = tmp_path / "seed"
    dest.mkdir()
    for f in seed_dir.iterdir():
        if f.name.endswith(".csv"):
            (dest / f.name).write_text(
                f.read_text(encoding="utf-8").split("\n")[0] + "\n", encoding="utf-8"
            )
    return dest


def write(csv_root, filename, header, *rows):
    body = header + "\n" + ("\n".join(rows) + "\n" if rows else "")
    (csv_root / filename).write_text(body, encoding="utf-8")


def _sensor_row(read_noise_low: str = "", read_noise_high: str = "") -> str:
    return (
        f"sensor.imx571,manufacturer.zwo,16,,1,50.0,IMX571,,91.0,3.76,"
        f"{read_noise_low},{read_noise_high},6248,4176,15.7,mono,23.5,"
    )


def _make_pre_0052(conn, *, read_noise_e, **overrides):
    """Rewrite the sensor row's seed_hash as it would have been before 0052.

    Also clears the step markers, so the next load sees a database that has just
    had the migration applied.
    """
    row = conn.execute("SELECT * FROM sensor WHERE seed_key = 'sensor.imx571'").fetchone()
    fields = {
        "manufacturer_id": row["manufacturer_id"],
        "model_name": row["model_name"],
        "sensor_type": row["sensor_type"],
        "pixel_size_um": row["pixel_size_um"],
        "resolution_x": row["resolution_x"],
        "resolution_y": row["resolution_y"],
        "sensor_width_mm": row["sensor_width_mm"],
        "sensor_height_mm": row["sensor_height_mm"],
        "adc_bit_depth": row["adc_bit_depth"],
        "full_well_capacity_ke": row["full_well_capacity_ke"],
        "read_noise_e": read_noise_e,
        "peak_qe_pct": row["peak_qe_pct"],
        "bayer_pattern": row["bayer_pattern"],
        "dual_gain": row["dual_gain"],
        "notes": row["notes"],
        "source_url": row["source_url"],
    }
    fields.update(overrides)
    conn.execute(
        "UPDATE sensor SET seed_hash = ? WHERE seed_key = 'sensor.imx571'",
        (compute_seed_hash(fields),),
    )
    conn.execute("DELETE FROM seed_loader_meta WHERE key LIKE 'rehash.%'")
    conn.commit()


def test_recovers_a_row_whose_value_also_changed_this_release(seed_db, csv_root):
    """The case the CSV-comparison repair cannot reach.

    The row is untouched, but 0052 moved its value into a different column *and*
    the same release changed that value — so it matches neither the stored hash
    nor the CSV. Only reconstructing the pre-migration hash identifies it.
    """
    write(csv_root, "manufacturer.csv", MFR_HEADER, "manufacturer.zwo,ZWO,,")
    write(csv_root, "sensor.csv", SENSOR_HEADER, _sensor_row(read_noise_low="3.3"))
    load_all(seed_db, csv_root, mode="first_run")

    # As 0052 leaves it: the value has moved to the high-gain column, and the
    # stored hash is the one computed over the old single read_noise_e field.
    seed_db.execute(
        "UPDATE sensor SET read_noise_low_gain_e = NULL, read_noise_high_gain_e = 3.3 "
        "WHERE seed_key = 'sensor.imx571'"
    )
    _make_pre_0052(seed_db, read_noise_e=3.3)

    # ...and this release also corrects the figure.
    write(csv_root, "sensor.csv", SENSOR_HEADER, _sensor_row(read_noise_high="0.7"))

    report = load_all(seed_db, csv_root, mode="update")

    assert report.migration_rehashed.get("sensor") == 1
    assert report.per_table["sensor"].skipped_user_modified == []
    assert report.per_table["sensor"].updated == 1
    row = seed_db.execute(
        "SELECT read_noise_low_gain_e l, read_noise_high_gain_e h FROM sensor "
        "WHERE seed_key = 'sensor.imx571'"
    ).fetchone()
    assert row["l"] is None
    assert row["h"] == 0.7


def test_leaves_a_genuinely_edited_row_alone(seed_db, csv_root):
    """A pre-migration user edit is still a user edit after the migration."""
    write(csv_root, "manufacturer.csv", MFR_HEADER, "manufacturer.zwo,ZWO,,")
    write(csv_root, "sensor.csv", SENSOR_HEADER, _sensor_row(read_noise_low="3.3"))
    load_all(seed_db, csv_root, mode="first_run")

    seed_db.execute(
        "UPDATE sensor SET read_noise_low_gain_e = NULL, read_noise_high_gain_e = 3.3, "
        "notes = 'my own measurement' WHERE seed_key = 'sensor.imx571'"
    )
    # The stored hash reflects the row as seeded, not as edited.
    _make_pre_0052(seed_db, read_noise_e=3.3, notes=None)

    report = load_all(seed_db, csv_root, mode="update")

    assert report.migration_rehashed.get("sensor", 0) == 0
    assert "sensor.imx571" in report.per_table["sensor"].skipped_user_modified
    row = seed_db.execute("SELECT notes FROM sensor WHERE seed_key = 'sensor.imx571'").fetchone()
    assert row["notes"] == "my own measurement"


def test_steps_run_once_per_database(seed_db, csv_root):
    """Markers stop a step re-running and re-adopting a later user edit."""
    write(csv_root, "manufacturer.csv", MFR_HEADER, "manufacturer.zwo,ZWO,,")
    write(csv_root, "sensor.csv", SENSOR_HEADER, _sensor_row(read_noise_low="3.3"))
    load_all(seed_db, csv_root, mode="first_run")
    _make_pre_0052(seed_db, read_noise_e=3.3)

    first = load_all(seed_db, csv_root, mode="update")
    assert first.migration_rehashed.get("sensor") == 1

    second = load_all(seed_db, csv_root, mode="update")
    assert second.migration_rehashed == {}

    markers = {r["key"] for r in seed_db.execute("SELECT key FROM seed_loader_meta").fetchall()}
    assert {s.key for s in REHASH_STEPS} <= markers


def test_first_run_marks_steps_without_touching_anything(seed_db, csv_root):
    """A fresh database seeds correct hashes, so the steps have nothing to do."""
    write(csv_root, "manufacturer.csv", MFR_HEADER, "manufacturer.zwo,ZWO,,")
    write(csv_root, "sensor.csv", SENSOR_HEADER, _sensor_row(read_noise_low="3.3"))

    report = load_all(seed_db, csv_root, mode="first_run")

    assert report.migration_rehashed == {"sensor": 0, "camera": 0}
    markers = {r["key"] for r in seed_db.execute("SELECT key FROM seed_loader_meta").fetchall()}
    assert {s.key for s in REHASH_STEPS} <= markers
