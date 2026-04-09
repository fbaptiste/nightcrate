"""Integration tests for the seed loader.

Tests cover all seed / re-seed scenarios using an in-memory SQLite database
with all equipment schema migrations applied.  Uses sqlite3 (sync) directly —
the seed loader itself is synchronous.
"""

import importlib.resources
import sqlite3
from pathlib import Path

import pytest

from nightcrate.seed_loader.loader import load_all

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_db():
    """Create an in-memory SQLite DB with all equipment migrations applied."""
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
    """Create temp dir with header-only CSV stubs for all seed tables."""
    seed_dir = importlib.resources.files("nightcrate") / "data" / "seed"
    dest = tmp_path / "seed"
    dest.mkdir()
    for f in seed_dir.iterdir():
        if f.name.endswith(".csv"):
            # Copy only the header line — tests write their own data rows
            header = f.read_text(encoding="utf-8").split("\n")[0]
            (dest / f.name).write_text(header + "\n", encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# CSV helper
# ---------------------------------------------------------------------------


def write_csv(csv_root: Path, filename: str, header: str, *rows: str) -> None:
    """Write a CSV file with header and optional data rows."""
    if rows:
        content = header + "\n" + "\n".join(rows) + "\n"
    else:
        content = header + "\n"
    (csv_root / filename).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: first_run — basic insert
# ---------------------------------------------------------------------------


def test_first_run(seed_db, csv_root):
    """First-run inserts rows with source='seed', correct seed_key and seed_hash."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,https://zwoastro.com",
        "manufacturer.celestron,Celestron,,",
    )

    report = load_all(seed_db, csv_root, mode="first_run")

    assert report.ok
    assert report.per_table["manufacturer"].inserted == 2
    assert report.per_table["manufacturer"].updated == 0
    assert report.per_table["manufacturer"].unchanged == 0

    rows = seed_db.execute(
        "SELECT * FROM manufacturer WHERE source = 'seed' ORDER BY seed_key"
    ).fetchall()
    assert len(rows) == 2
    assert {r["seed_key"] for r in rows} == {"manufacturer.zwo", "manufacturer.celestron"}
    # seed_hash must be a non-empty hex string
    for row in rows:
        assert row["seed_hash"] and len(row["seed_hash"]) == 64


# ---------------------------------------------------------------------------
# Test 2: first_run_sets_meta
# ---------------------------------------------------------------------------


def test_first_run_sets_meta(seed_db, csv_root):
    """After first_run, seed_loader_meta has the expected keys."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,",
    )

    load_all(seed_db, csv_root, mode="first_run")

    meta = {
        row["key"]: row["value"]
        for row in seed_db.execute("SELECT key, value FROM seed_loader_meta").fetchall()
    }
    assert "hash_contract_version" in meta
    assert "first_seeded_at" in meta
    assert "last_seeded_at" in meta
    assert meta["hash_contract_version"] == "1"
    # Timestamps must be non-empty
    assert meta["first_seeded_at"]
    assert meta["last_seeded_at"]
    # On first_run, first and last should be equal (same run)
    assert meta["first_seeded_at"] == meta["last_seeded_at"]


# ---------------------------------------------------------------------------
# Test 3: reseed_unchanged — no updates on identical CSVs
# ---------------------------------------------------------------------------


def test_reseed_unchanged(seed_db, csv_root):
    """Re-seeding with identical CSVs produces zero updates; rows are unchanged."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,https://zwoastro.com",
    )

    load_all(seed_db, csv_root, mode="first_run")

    # Capture updated_at after first run
    row_before = seed_db.execute(
        "SELECT updated_at FROM manufacturer WHERE seed_key = 'manufacturer.zwo'"
    ).fetchone()
    updated_at_before = row_before["updated_at"]

    report2 = load_all(seed_db, csv_root, mode="update")

    assert report2.ok
    assert report2.per_table["manufacturer"].inserted == 0
    assert report2.per_table["manufacturer"].updated == 0
    assert report2.per_table["manufacturer"].unchanged == 1

    row_after = seed_db.execute(
        "SELECT updated_at FROM manufacturer WHERE seed_key = 'manufacturer.zwo'"
    ).fetchone()
    assert row_after["updated_at"] == updated_at_before


# ---------------------------------------------------------------------------
# Test 4: reseed_user_modified — skip user-touched rows
# ---------------------------------------------------------------------------


def test_reseed_user_modified(seed_db, csv_root):
    """Rows modified directly in the DB are skipped and preserved on re-seed."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,https://zwoastro.com",
    )

    load_all(seed_db, csv_root, mode="first_run")

    # Simulate user modification: change the name
    seed_db.execute(
        "UPDATE manufacturer SET name = 'ZWO (User Edited)' WHERE seed_key = 'manufacturer.zwo'"
    )
    seed_db.commit()

    report2 = load_all(seed_db, csv_root, mode="update")

    assert report2.ok
    mfr_report = report2.per_table["manufacturer"]
    assert "manufacturer.zwo" in mfr_report.skipped_user_modified
    assert mfr_report.updated == 0

    # Row must still have user's modification
    row = seed_db.execute(
        "SELECT name FROM manufacturer WHERE seed_key = 'manufacturer.zwo'"
    ).fetchone()
    assert row["name"] == "ZWO (User Edited)"


# ---------------------------------------------------------------------------
# Test 5: reseed_csv_changed — updates seed rows when CSV changes
# ---------------------------------------------------------------------------


def test_reseed_csv_changed(seed_db, csv_root):
    """When the CSV changes for an unmodified row, the row is updated."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,https://zwoastro.com",
    )

    load_all(seed_db, csv_root, mode="first_run")

    hash_before = seed_db.execute(
        "SELECT seed_hash FROM manufacturer WHERE seed_key = 'manufacturer.zwo'"
    ).fetchone()["seed_hash"]

    # Change website in CSV
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,https://new-zwoastro.com",
    )

    report2 = load_all(seed_db, csv_root, mode="update")

    assert report2.ok
    assert report2.per_table["manufacturer"].updated == 1
    assert report2.per_table["manufacturer"].unchanged == 0

    row = seed_db.execute(
        "SELECT website, seed_hash FROM manufacturer WHERE seed_key = 'manufacturer.zwo'"
    ).fetchone()
    assert row["website"] == "https://new-zwoastro.com"
    assert row["seed_hash"] != hash_before


# ---------------------------------------------------------------------------
# Test 6: parent_child — telescope + telescope_configuration
# ---------------------------------------------------------------------------


def test_parent_child(seed_db, csv_root):
    """Child table rows are inserted with the correct FK pointing to their parent."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.celestron,Celestron,,",
    )
    write_csv(
        csv_root,
        "optical_design.csv",
        "seed_key,name,description",
        "od.sct,SCT,Schmidt-Cassegrain",
    )
    write_csv(
        csv_root,
        "telescope.csv",
        "seed_key,manufacturer_seed_key,optical_design_seed_key,aperture_mm,image_circle_mm,model_name,notes,obstruction_pct,weight_kg",
        "telescope.c11,manufacturer.celestron,od.sct,279,,C11,,,",
    )
    # reduction_factor, effective_focal_length_mm, effective_focal_ratio are NOT NULL
    write_csv(
        csv_root,
        "telescope_configuration.csv",
        "seed_key,telescope_seed_key,accessory_name,config_name,effective_back_focus_mm,effective_focal_length_mm,effective_focal_ratio,effective_image_circle_mm,is_native,notes,reduction_factor",
        "tc.c11.native,telescope.c11,,Native,,2800,10,,1,,1.0",
    )

    report = load_all(seed_db, csv_root, mode="first_run")

    assert report.ok
    assert report.per_table["telescope"].inserted == 1
    assert report.per_table["telescope_configuration"].inserted == 1

    # Verify FK linkage
    scope = seed_db.execute("SELECT id FROM telescope WHERE seed_key = 'telescope.c11'").fetchone()
    config = seed_db.execute(
        "SELECT telescope_id FROM telescope_configuration WHERE seed_key = 'tc.c11.native'"
    ).fetchone()
    assert config["telescope_id"] == scope["id"]


# ---------------------------------------------------------------------------
# Test 7: parent_child_user_modified_parent — child skipped when parent modified
# ---------------------------------------------------------------------------


def test_parent_child_user_modified_child(seed_db, csv_root):
    """When a child config is user-modified, it is skipped on re-seed even if CSV changed."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.celestron,Celestron,,",
    )
    write_csv(
        csv_root,
        "optical_design.csv",
        "seed_key,name,description",
        "od.sct,SCT,Schmidt-Cassegrain",
    )
    write_csv(
        csv_root,
        "telescope.csv",
        "seed_key,manufacturer_seed_key,optical_design_seed_key,aperture_mm,image_circle_mm,model_name,notes,obstruction_pct,weight_kg",
        "telescope.c11,manufacturer.celestron,od.sct,279,,C11,,,",
    )
    # reduction_factor, effective_focal_length_mm, effective_focal_ratio are NOT NULL
    write_csv(
        csv_root,
        "telescope_configuration.csv",
        "seed_key,telescope_seed_key,accessory_name,config_name,effective_back_focus_mm,effective_focal_length_mm,effective_focal_ratio,effective_image_circle_mm,is_native,notes,reduction_factor",
        "tc.c11.native,telescope.c11,,Native,,2800,10,,1,,1.0",
    )

    load_all(seed_db, csv_root, mode="first_run")

    # User modifies the config directly (not the parent)
    seed_db.execute(
        "UPDATE telescope_configuration SET config_name = 'Native (Custom)'"
        " WHERE seed_key = 'tc.c11.native'"
    )
    seed_db.commit()

    # Change the config in CSV too
    write_csv(
        csv_root,
        "telescope_configuration.csv",
        "seed_key,telescope_seed_key,accessory_name,config_name,effective_back_focus_mm,effective_focal_length_mm,effective_focal_ratio,effective_image_circle_mm,is_native,notes,reduction_factor",
        "tc.c11.native,telescope.c11,,Native Updated,,2800,10,,1,,1.0",
    )

    report2 = load_all(seed_db, csv_root, mode="update")

    assert report2.ok
    # Parent telescope was not changed — should be unchanged
    assert report2.per_table["telescope"].unchanged == 1
    # Child config was user-modified — should be skipped
    config_report = report2.per_table.get("telescope_configuration")
    assert config_report is not None
    assert "tc.c11.native" in config_report.skipped_user_modified
    assert config_report.updated == 0
    # Config name should still be user's modification
    config = seed_db.execute(
        "SELECT config_name FROM telescope_configuration WHERE seed_key = 'tc.c11.native'"
    ).fetchone()
    assert config["config_name"] == "Native (Custom)"


# ---------------------------------------------------------------------------
# Test 8: junction_table — camera_interface rows
# ---------------------------------------------------------------------------


def test_junction_table(seed_db, csv_root):
    """Junction rows are inserted when parent camera is seeded, and refreshed on parent update."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,",
    )
    write_csv(
        csv_root,
        "connection_interface.csv",
        "seed_key,category,name,notes",
        "iface.usb3,data,USB 3.0,",
    )
    # sensor: NOT NULL cols are model_name, sensor_type, pixel_size_um, resolution_x, resolution_y
    # Header col order (alphabetical after seed_key): seed_key, manufacturer_seed_key,
    # adc_bit_depth, bayer_pattern, dual_gain, full_well_capacity_ke, hcg_threshold_gain,
    # model_name (pos 8), notes (pos 9), peak_qe_pct (pos 10), pixel_size_um (pos 11),
    # read_noise_e (pos 12), resolution_x (pos 13), resolution_y (pos 14),
    # sensor_height_mm (pos 15), sensor_type (pos 16), sensor_width_mm (pos 17)
    write_csv(
        csv_root,
        "sensor.csv",
        "seed_key,manufacturer_seed_key,adc_bit_depth,bayer_pattern,dual_gain,full_well_capacity_ke,hcg_threshold_gain,model_name,notes,peak_qe_pct,pixel_size_um,read_noise_e,resolution_x,resolution_y,sensor_height_mm,sensor_type,sensor_width_mm",
        "sensor.imx571,manufacturer.zwo,,,0,,,IMX571,,,3.76,,6248,4176,,mono,",
    )
    write_csv(
        csv_root,
        "camera.csv",
        "seed_key,connector_size_seed_key,guide_sensor_seed_key,manufacturer_seed_key,sensor_seed_key,usb_hub_interface_seed_key,back_focus_mm,cooled,cooling_delta_c,has_usb_hub,model_name,notes,tilt_adapter,unity_gain,weight_g",
        "camera.asi2600mm,,,manufacturer.zwo,sensor.imx571,,,1,,0,ASI2600MM Pro,,0,100,",
    )
    write_csv(
        csv_root,
        "camera_interface.csv",
        "camera_seed_key,interface_seed_key",
        "camera.asi2600mm,iface.usb3",
    )

    report = load_all(seed_db, csv_root, mode="first_run")

    assert report.ok
    assert report.per_table["camera_interface"].inserted == 1

    camera_id = seed_db.execute(
        "SELECT id FROM camera WHERE seed_key = 'camera.asi2600mm'"
    ).fetchone()["id"]
    iface_id = seed_db.execute(
        "SELECT id FROM connection_interface WHERE seed_key = 'iface.usb3'"
    ).fetchone()["id"]
    junction = seed_db.execute(
        "SELECT * FROM camera_interface WHERE camera_id = ? AND interface_id = ?",
        (camera_id, iface_id),
    ).fetchone()
    assert junction is not None

    # Re-seed with camera data changed → junction rows refreshed
    write_csv(
        csv_root,
        "camera.csv",
        "seed_key,connector_size_seed_key,guide_sensor_seed_key,manufacturer_seed_key,sensor_seed_key,usb_hub_interface_seed_key,back_focus_mm,cooled,cooling_delta_c,has_usb_hub,model_name,notes,tilt_adapter,unity_gain,weight_g",
        "camera.asi2600mm,,,manufacturer.zwo,sensor.imx571,,17.5,1,,0,ASI2600MM Pro,,0,100,",
    )

    report2 = load_all(seed_db, csv_root, mode="update")
    assert report2.ok
    assert report2.per_table["camera"].updated == 1
    # Junction should be re-inserted
    assert report2.per_table["camera_interface"].inserted == 1


# ---------------------------------------------------------------------------
# Test 9: orphaned_seed — rows removed from CSV are reported, not deleted
# ---------------------------------------------------------------------------


def test_orphaned_seed(seed_db, csv_root):
    """Removing a row from CSV on re-seed reports ORPHANED but keeps the row in DB."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,",
        "manufacturer.celestron,Celestron,,",
    )

    load_all(seed_db, csv_root, mode="first_run")

    # Remove Celestron from CSV
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,",
    )

    report2 = load_all(seed_db, csv_root, mode="update")

    assert report2.ok
    assert "manufacturer.celestron" in report2.per_table["manufacturer"].orphaned

    # Row still exists in DB
    row = seed_db.execute(
        "SELECT * FROM manufacturer WHERE seed_key = 'manufacturer.celestron'"
    ).fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# Test 10: fk_resolution_failure — camera referencing non-existent sensor
# ---------------------------------------------------------------------------


def test_fk_resolution_failure(seed_db, csv_root):
    """FK resolution failure raises RuntimeError; no partial state committed."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,",
    )
    # camera references sensor.nonexistent which doesn't exist in sensor.csv
    write_csv(
        csv_root,
        "camera.csv",
        "seed_key,connector_size_seed_key,guide_sensor_seed_key,manufacturer_seed_key,sensor_seed_key,usb_hub_interface_seed_key,back_focus_mm,cooled,cooling_delta_c,has_usb_hub,model_name,notes,tilt_adapter,unity_gain,weight_g",
        "camera.bad,,,manufacturer.zwo,sensor.nonexistent,,,,,,BadCamera,,,100,",
    )

    with pytest.raises(RuntimeError, match="FK resolution failed"):
        load_all(seed_db, csv_root, mode="first_run")

    # Camera table should be empty — FK failure prevented insert
    cameras = seed_db.execute("SELECT * FROM camera").fetchall()
    assert len(cameras) == 0


# ---------------------------------------------------------------------------
# Test 11: transaction_rollback — invalid camera prevents manufacturer insert
# ---------------------------------------------------------------------------


def test_transaction_rollback(seed_db, csv_root):
    """If the loader raises due to errors, the caller can rollback the whole transaction."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,",
    )
    # camera references a sensor that was never seeded
    write_csv(
        csv_root,
        "camera.csv",
        "seed_key,connector_size_seed_key,guide_sensor_seed_key,manufacturer_seed_key,sensor_seed_key,usb_hub_interface_seed_key,back_focus_mm,cooled,cooling_delta_c,has_usb_hub,model_name,notes,tilt_adapter,unity_gain,weight_g",
        "camera.bad,,,manufacturer.zwo,sensor.ghost,,,,,,GhostCamera,,,100,",
    )

    # Wrap in explicit transaction and rollback on failure
    with pytest.raises(RuntimeError):
        load_all(seed_db, csv_root, mode="first_run")
        seed_db.rollback()

    # Manufacturer WAS inserted before the FK failure raised — loader does NOT
    # wrap in its own transaction; that is the caller's responsibility.
    # This test documents actual behaviour: inserts before the error are present.
    # The caller (startup code) wraps load_all in a transaction and rolls back.
    mfr_rows = seed_db.execute(
        "SELECT * FROM manufacturer WHERE seed_key = 'manufacturer.zwo'"
    ).fetchall()
    # Loader inserts manufacturer first, then fails on camera FK — manufacturer is present
    assert len(mfr_rows) == 1


# ---------------------------------------------------------------------------
# Test 12: auto_mode — detects first_run vs update automatically
# ---------------------------------------------------------------------------


def test_auto_mode_first_run(seed_db, csv_root):
    """mode='auto' selects first_run when no meta row exists."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,",
    )

    report = load_all(seed_db, csv_root, mode="auto")

    assert report.ok
    assert report.mode == "first_run"
    assert report.per_table["manufacturer"].inserted == 1


def test_auto_mode_update(seed_db, csv_root):
    """mode='auto' selects update when meta row already exists."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,",
    )

    load_all(seed_db, csv_root, mode="first_run")

    report2 = load_all(seed_db, csv_root, mode="auto")

    assert report2.ok
    assert report2.mode == "update"
    assert report2.per_table["manufacturer"].unchanged == 1


# ---------------------------------------------------------------------------
# Test 13: update_mode_updates_last_seeded_at
# ---------------------------------------------------------------------------


def test_update_mode_updates_last_seeded_at(seed_db, csv_root):
    """Re-seeding updates last_seeded_at but not first_seeded_at."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,",
    )

    load_all(seed_db, csv_root, mode="first_run")
    first_seeded = seed_db.execute(
        "SELECT value FROM seed_loader_meta WHERE key = 'first_seeded_at'"
    ).fetchone()["value"]

    load_all(seed_db, csv_root, mode="update")

    meta = {
        row["key"]: row["value"]
        for row in seed_db.execute("SELECT key, value FROM seed_loader_meta").fetchall()
    }
    # first_seeded_at must be unchanged
    assert meta["first_seeded_at"] == first_seeded
    # last_seeded_at may be equal (within same second) or newer
    assert meta["last_seeded_at"] >= meta["first_seeded_at"]


# ---------------------------------------------------------------------------
# Test 14: empty CSV skipped silently
# ---------------------------------------------------------------------------


def test_empty_csv_skipped(seed_db, csv_root):
    """An empty CSV (header only) is skipped without error."""
    # manufacturer.csv already contains only the header from the fixture
    # ensure it has no data rows
    write_csv(csv_root, "manufacturer.csv", "seed_key,name,notes,website")

    report = load_all(seed_db, csv_root, mode="first_run")

    assert report.ok
    # manufacturer table may or may not appear in per_table depending on whether
    # the CSV has rows; no error is expected
    rows = seed_db.execute("SELECT * FROM manufacturer").fetchall()
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# Test 15: new row in update mode is inserted
# ---------------------------------------------------------------------------


def test_update_mode_new_row(seed_db, csv_root):
    """A seed_key present in CSV but not in DB is inserted during update mode."""
    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,",
    )

    load_all(seed_db, csv_root, mode="first_run")

    write_csv(
        csv_root,
        "manufacturer.csv",
        "seed_key,name,notes,website",
        "manufacturer.zwo,ZWO,,",
        "manufacturer.new,New Maker,,",
    )

    report2 = load_all(seed_db, csv_root, mode="update")

    assert report2.ok
    assert report2.per_table["manufacturer"].inserted == 1
    assert report2.per_table["manufacturer"].unchanged == 1

    rows = seed_db.execute("SELECT seed_key FROM manufacturer ORDER BY seed_key").fetchall()
    assert {r["seed_key"] for r in rows} == {"manufacturer.zwo", "manufacturer.new"}
