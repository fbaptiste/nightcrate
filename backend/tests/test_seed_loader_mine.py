"""Regression test: is_mine flag survives re-seed without triggering an update.

The seed hash is computed exclusively from the CSV seeded_fields columns.
is_mine is NOT a seeded_field, so marking a row as is_mine=1 must NOT cause
a hash mismatch on re-seed, and a re-seed must NOT stomp the flag.
"""

import importlib.resources
import sqlite3
from pathlib import Path

import pytest

from nightcrate.seed_loader.loader import load_all

# ---------------------------------------------------------------------------
# Fixtures (mirrors test_seed_loader.py conventions)
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_db():
    """In-memory SQLite DB with all equipment migrations applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    migrations_dir = importlib.resources.files("nightcrate") / "db" / "migrations"
    for name in sorted(f.name for f in migrations_dir.iterdir() if f.name.endswith(".sql")):
        sql = (migrations_dir / name).read_text()
        body = "\n".join(
            line for line in sql.split("\n") if not line.strip().startswith("-- depends:")
        )
        conn.executescript(body)

    yield conn
    conn.close()


@pytest.fixture
def csv_root(tmp_path):
    """Temp dir with header-only CSV stubs for all seed tables."""
    seed_dir = importlib.resources.files("nightcrate") / "data" / "seed"
    dest = tmp_path / "seed"
    dest.mkdir()
    for f in seed_dir.iterdir():
        if f.name.endswith(".csv"):
            header = f.read_text(encoding="utf-8").split("\n")[0]
            (dest / f.name).write_text(header + "\n", encoding="utf-8")
    return dest


def write_csv(csv_root: Path, filename: str, header: str, *rows: str) -> None:
    if rows:
        content = header + "\n" + "\n".join(rows) + "\n"
    else:
        content = header + "\n"
    (csv_root / filename).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Test: is_mine preserved across re-seed
# ---------------------------------------------------------------------------


def test_is_mine_preserved_across_reseed(seed_db, csv_root):
    """Marking is_mine=1 on a seed row does NOT trigger re-seed, and the flag
    is preserved when the seed loader re-runs in update mode.

    Rationale: is_mine is not in seeded_fields for camera, so it is excluded
    from the seed hash computation. The re-seed logic computes current_hash
    only over seeded_fields — a change to is_mine must not produce a hash
    mismatch (which would classify the row as user-modified and skip it, or
    worse, overwrite it). Instead, the row should remain 'unchanged' from the
    seed loader's perspective, and the is_mine=1 flag must survive intact.
    """
    # Seed a minimal camera row (plus its required dependencies)
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,",
    )
    write_csv(
        csv_root,
        "sensor.csv",
        "seed_key,manufacturer_seed_key,adc_bit_depth,bayer_pattern,dual_gain,"
        "full_well_capacity_ke,model_name,notes,peak_qe_pct,pixel_size_um,"
        "read_noise_e,resolution_x,resolution_y,sensor_height_mm,sensor_type,"
        "sensor_width_mm,source_url",
        "sensor.imx571,manufacturer.zwo,,,0,,IMX571,,,3.76,,6248,4176,,mono,,",
    )
    write_csv(
        csv_root,
        "camera.csv",
        "seed_key,connector_size_seed_key,guide_sensor_seed_key,manufacturer_seed_key,"
        "sensor_seed_key,usb_hub_interface_seed_key,back_focus_mm,cooled,cooling_delta_c,"
        "has_usb_hub,model_name,notes,source_url,tilt_adapter,unity_gain,"
        "effective_full_well_ke,effective_read_noise_lcg_e,effective_read_noise_hcg_e,"
        "effective_peak_qe_pct,hcg_threshold_gain,weight_g",
        "camera.asi2600mm,,,manufacturer.zwo,sensor.imx571,,,1,,0,ASI2600MM Pro,,,0,100,,,,,,",
    )

    # --- Step a: first_run seed load ---
    report1 = load_all(seed_db, csv_root, mode="first_run")
    assert report1.ok
    assert report1.per_table["camera"].inserted == 1

    # --- Step b: capture seed_hash of the freshly-inserted row ---
    row_before = seed_db.execute(
        "SELECT id, seed_hash, is_mine FROM camera WHERE seed_key = 'camera.asi2600mm'"
    ).fetchone()
    assert row_before is not None
    seed_hash_before = row_before["seed_hash"]
    assert seed_hash_before and len(seed_hash_before) == 64  # valid SHA-256 hex
    assert row_before["is_mine"] == 0  # default — not yet marked as mine

    # --- Step c: mark is_mine = 1 ---
    seed_db.execute("UPDATE camera SET is_mine = 1 WHERE seed_key = 'camera.asi2600mm'")
    seed_db.commit()

    # Verify the flag is set before re-seed
    is_mine_set = seed_db.execute(
        "SELECT is_mine FROM camera WHERE seed_key = 'camera.asi2600mm'"
    ).fetchone()["is_mine"]
    assert is_mine_set == 1

    # --- Step d: re-run seed loader in update mode ---
    report2 = load_all(seed_db, csv_root, mode="update")

    # --- Step e: is_mine=1 must still be set ---
    row_after = seed_db.execute(
        "SELECT seed_hash, is_mine FROM camera WHERE seed_key = 'camera.asi2600mm'"
    ).fetchone()
    assert row_after["is_mine"] == 1, (
        "is_mine flag was stomped by re-seed — this is a bug in the seed loader"
    )

    # --- Step f: seed_hash must be unchanged (row was treated as 'unchanged', not re-written) ---
    assert row_after["seed_hash"] == seed_hash_before, (
        "seed_hash changed after re-seed even though CSV was identical — "
        "is_mine change incorrectly triggered a hash mismatch"
    )

    # The loader must report the camera as unchanged (not updated, not skipped)
    camera_report = report2.per_table.get("camera")
    assert camera_report is not None
    assert camera_report.unchanged == 1, (
        f"Expected camera row to be 'unchanged' on re-seed, "
        f"got: updated={camera_report.updated}, "
        f"skipped_user_modified={camera_report.skipped_user_modified}"
    )
    assert camera_report.updated == 0
    assert camera_report.skipped_user_modified == []
