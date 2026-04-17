"""Tests verifying the is_mine column and partial index on owned equipment tables."""

import importlib.resources
import sqlite3

import pytest

OWNED_TABLES = [
    "camera",
    "telescope",
    "filter",
    "mount",
    "focuser",
    "filter_wheel",
    "oag",
    "guide_scope",
    "computer",
    "software",
]

NON_OWNED_TABLES = [
    "sensor",
    "telescope_configuration",
    "manufacturer",
    "optical_design",
    "filter_type",
]


@pytest.fixture
def db_with_equipment_schema(tmp_path):
    """Apply all migrations to a fresh SQLite database."""
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    migrations_dir = importlib.resources.files("nightcrate") / "db" / "migrations"
    for migration_name in sorted(
        f.name for f in migrations_dir.iterdir() if f.name.endswith(".sql")
    ):
        sql = (migrations_dir / migration_name).read_text()
        lines = sql.split("\n")
        body = "\n".join(line for line in lines if not line.strip().startswith("-- depends:"))
        conn.executescript(body)

    yield conn
    conn.close()


class TestIsMineColumnPresent:
    """Verify is_mine exists on all 10 owned tables with correct definition."""

    @pytest.mark.parametrize("table", OWNED_TABLES)
    def test_is_mine_column_exists(self, db_with_equipment_schema, table):
        conn = db_with_equipment_schema
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608
        col_names = [r["name"] for r in rows]
        assert "is_mine" in col_names, f"is_mine column missing from {table}"

    @pytest.mark.parametrize("table", OWNED_TABLES)
    def test_is_mine_column_type_and_constraints(self, db_with_equipment_schema, table):
        conn = db_with_equipment_schema
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608
        col = next((r for r in rows if r["name"] == "is_mine"), None)
        assert col is not None, f"is_mine column missing from {table}"
        assert col["type"].upper() == "INTEGER", f"is_mine type wrong in {table}: {col['type']}"
        assert col["notnull"] == 1, f"is_mine should be NOT NULL in {table}"
        assert str(col["dflt_value"]) == "0", f"is_mine default should be 0 in {table}"


class TestIsMineColumnAbsent:
    """Verify is_mine is NOT present on non-owned tables."""

    @pytest.mark.parametrize("table", NON_OWNED_TABLES)
    def test_is_mine_absent(self, db_with_equipment_schema, table):
        conn = db_with_equipment_schema
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608
        col_names = [r["name"] for r in rows]
        assert "is_mine" not in col_names, f"is_mine should NOT exist in {table}"


class TestIsMinePartialIndex:
    """Verify partial indexes on is_mine exist for all 10 owned tables."""

    @pytest.mark.parametrize("table", OWNED_TABLES)
    def test_partial_index_exists(self, db_with_equipment_schema, table):
        conn = db_with_equipment_schema
        index_name = f"idx_{table}_mine"
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,),
        ).fetchone()
        assert row is not None, f"Partial index {index_name} missing for table {table}"


class TestIsMineDefaultAndConstraint:
    """Verify is_mine defaults to 0 and enforces the CHECK constraint."""

    def test_is_mine_defaults_to_zero_on_camera(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestMfg')")
        mfg_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO sensor "
            "(manufacturer_id, model_name, sensor_type, pixel_size_um, "
            "resolution_x, resolution_y) "
            "VALUES (?, 'S1', 'mono', 3.76, 100, 100)",
            (mfg_id,),
        )
        sensor_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO camera (manufacturer_id, sensor_id, model_name) VALUES (?, ?, 'Cam1')",
            (mfg_id, sensor_id),
        )
        row = conn.execute("SELECT is_mine FROM camera WHERE model_name='Cam1'").fetchone()
        assert row["is_mine"] == 0

    def test_is_mine_can_be_set_to_one_on_camera(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestMfg2')")
        mfg_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO sensor "
            "(manufacturer_id, model_name, sensor_type, pixel_size_um, "
            "resolution_x, resolution_y) "
            "VALUES (?, 'S2', 'mono', 3.76, 100, 100)",
            (mfg_id,),
        )
        sensor_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO camera (manufacturer_id, sensor_id, model_name, is_mine) "
            "VALUES (?, ?, 'MyCam', 1)",
            (mfg_id, sensor_id),
        )
        row = conn.execute("SELECT is_mine FROM camera WHERE model_name='MyCam'").fetchone()
        assert row["is_mine"] == 1

    def test_is_mine_rejects_invalid_value_on_camera(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestMfg3')")
        mfg_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO sensor "
            "(manufacturer_id, model_name, sensor_type, pixel_size_um, "
            "resolution_x, resolution_y) "
            "VALUES (?, 'S3', 'mono', 3.76, 100, 100)",
            (mfg_id,),
        )
        sensor_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO camera (manufacturer_id, sensor_id, model_name, is_mine) "
                "VALUES (?, ?, 'BadCam', 2)",
                (mfg_id, sensor_id),
            )
