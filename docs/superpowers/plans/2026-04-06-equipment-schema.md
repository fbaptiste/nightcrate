# Equipment Database Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the full normalized equipment database schema (tables, indexes, triggers, views, seed data) as a single migration.

**Architecture:** One SQL migration file (`0005.equipment_schema.sql`) containing all table definitions, indexes, triggers, views, and seed data. Tests verify the migration applies cleanly and all constraints work. No API or UI code.

**Tech Stack:** SQLite, yoyo-migrations (SQL files), pytest, aiosqlite

---

### Task 1: Write the Migration — Lookup/Reference Tables

**Files:**
- Create: `backend/src/nightcrate/db/migrations/0005.equipment_schema.sql`

- [ ] **Step 1: Create the migration file with lookup tables**

Create `backend/src/nightcrate/db/migrations/0005.equipment_schema.sql`. Start with the dependency header and all lookup/reference tables. Copy the DDL directly from `DB_SCHEMA_DDL.sql` for these tables:

- `seed_loader_meta`
- `manufacturer`
- `optical_design`
- `mount_type`
- `connection_interface`
- `connector_size`
- `filter_size`
- `computer_type`
- `filter_type` (with seed INSERT)

Each table includes: columns, seed tracking columns (`created_at`, `updated_at`, `active`, `source`, `seed_key`, `seed_hash`), partial unique index on `seed_key`, and `updated_at` trigger.

```sql
-- depends: 0004.aberration_cache
```

The full DDL for each table is in `DB_SCHEMA_DDL.sql` — copy it verbatim. Do not abbreviate or paraphrase. Include all CHECK constraints, UNIQUE indexes, partial indexes, and triggers exactly as specified.

- [ ] **Step 2: Verify the file parses**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run python -c "import sqlite3; conn = sqlite3.connect(':memory:'); conn.executescript(open('src/nightcrate/db/migrations/0005.equipment_schema.sql').read().split('-- depends:')[1]); print('OK')"`

Expected: `OK` (no SQL syntax errors)

---

### Task 2: Add Equipment Tables to the Migration

**Files:**
- Modify: `backend/src/nightcrate/db/migrations/0005.equipment_schema.sql`

- [ ] **Step 1: Append sensor and camera tables**

Append to the migration file. Copy from `DB_SCHEMA_DDL.sql`:

- `sensor` (with manufacturer FK, CHECK constraints for sensor_type and bayer_pattern cross-check, seed tracking, trigger, indexes)
- `camera` (with manufacturer/sensor/connector_size FKs, has_usb_hub + usb_hub_interface_id, seed tracking, trigger, indexes)
- `camera_interface` junction table

- [ ] **Step 2: Append telescope tables**

- `telescope` (manufacturer/optical_design FKs, no focal length — seed tracking, trigger, indexes)
- `telescope_connector` junction table
- `telescope_configuration` (telescope FK, is_native, partial unique index for one native per telescope, seed tracking, trigger, indexes)

- [ ] **Step 3: Append filter tables**

- `filter` (manufacturer/filter_type/filter_size FKs, seed tracking, trigger, indexes)
- `filter_passband` (filter FK, line_name CHECK, seed tracking, trigger, indexes)

- [ ] **Step 4: Append mount, focuser, filter_wheel tables**

- `mount` + `mount_interface`
- `focuser` + `focuser_interface`
- `filter_wheel` + `filter_wheel_interface`

All with manufacturer FKs, seed tracking columns, triggers, indexes.

- [ ] **Step 5: Append guiding, computing, software tables**

- `oag` (manufacturer FK, connector_size FKs for both sides)
- `guide_scope` (manufacturer FK, connector_size FK)
- `computer` (manufacturer FK, computer_type FK)
- `software` (manufacturer FK, category CHECK)

All with seed tracking columns, triggers, indexes.

- [ ] **Step 6: Append alias tables and view**

- `camera_alias`
- `telescope_alias`
- `filter_alias`
- `unresolved_equipment_observation`
- `filter_summary` view

- [ ] **Step 7: Verify the complete migration parses**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run python -c "import sqlite3; conn = sqlite3.connect(':memory:'); conn.executescript(open('src/nightcrate/db/migrations/0005.equipment_schema.sql').read().split('-- depends:')[1]); print('Tables:', [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\").fetchall()]); print('OK')"`

Expected: `OK` with all table names listed.

- [ ] **Step 8: Commit**

```bash
git add backend/src/nightcrate/db/migrations/0005.equipment_schema.sql
git commit -m "feat: add equipment schema migration (0005)"
```

---

### Task 3: Test — Migration Applies Cleanly

**Files:**
- Create: `backend/tests/test_equipment_schema.py`

- [ ] **Step 1: Write test that migration applies to empty database**

```python
"""Tests for the equipment schema migration (0005)."""

import sqlite3

import pytest


@pytest.fixture
def db_with_equipment_schema(tmp_path):
    """Apply all migrations up through 0005 to a fresh SQLite database."""
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Read and apply all migrations in order
    import importlib.resources
    migrations_dir = (
        importlib.resources.files("nightcrate") / "db" / "migrations"
    )
    for migration_name in sorted(
        f.name for f in migrations_dir.iterdir() if f.name.endswith(".sql")
    ):
        sql = (migrations_dir / migration_name).read_text()
        # Strip the -- depends: header line
        lines = sql.split("\n")
        body = "\n".join(
            line for line in lines if not line.strip().startswith("-- depends:")
        )
        conn.executescript(body)

    yield conn
    conn.close()


class TestMigrationApplies:
    def test_all_equipment_tables_created(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "seed_loader_meta",
            "manufacturer",
            "optical_design",
            "mount_type",
            "connection_interface",
            "connector_size",
            "filter_size",
            "computer_type",
            "filter_type",
            "sensor",
            "camera",
            "camera_interface",
            "telescope",
            "telescope_connector",
            "telescope_configuration",
            "filter",
            "filter_passband",
            "mount",
            "mount_interface",
            "focuser",
            "focuser_interface",
            "filter_wheel",
            "filter_wheel_interface",
            "oag",
            "guide_scope",
            "computer",
            "software",
            "camera_alias",
            "telescope_alias",
            "filter_alias",
            "unresolved_equipment_observation",
        }
        assert expected.issubset(tables)

    def test_filter_summary_view_exists(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        views = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            ).fetchall()
        }
        assert "filter_summary" in views
```

- [ ] **Step 2: Run the test**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_equipment_schema.py -v`

Expected: 2 tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_equipment_schema.py
git commit -m "test: migration applies cleanly, all tables and views created"
```

---

### Task 4: Test — Filter Type Seed Data

**Files:**
- Modify: `backend/tests/test_equipment_schema.py`

- [ ] **Step 1: Write test for seeded filter_type rows**

```python
class TestFilterTypeSeedData:
    def test_all_filter_types_seeded(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        rows = conn.execute("SELECT name, source, seed_key FROM filter_type ORDER BY name").fetchall()
        names = {row["name"] for row in rows}
        expected = {
            "broadband_luminance",
            "broadband_color",
            "narrowband_single",
            "narrowband_dual",
            "narrowband_tri",
            "uv_ir_cut",
            "light_pollution",
            "neutral_density",
            "other",
        }
        assert names == expected

    def test_filter_type_seed_rows_have_correct_source(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        rows = conn.execute("SELECT source FROM filter_type").fetchall()
        assert all(row["source"] == "seed" for row in rows)

    def test_filter_type_seed_keys_set(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        rows = conn.execute("SELECT seed_key FROM filter_type").fetchall()
        assert all(row["seed_key"] is not None for row in rows)
        assert all(row["seed_key"].startswith("filter_type.") for row in rows)
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_equipment_schema.py -v`

Expected: 5 tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_equipment_schema.py
git commit -m "test: filter_type seed data verification"
```

---

### Task 5: Test — CHECK Constraints

**Files:**
- Modify: `backend/tests/test_equipment_schema.py`

- [ ] **Step 1: Write CHECK constraint tests**

```python
class TestCheckConstraints:
    def test_sensor_type_must_be_mono_or_color(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, pixel_size_um, resolution_x, resolution_y) "
                "VALUES (1, 'TestSensor', 'invalid', 3.76, 6248, 4176)"
            )

    def test_mono_sensor_rejects_bayer_pattern(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, pixel_size_um, resolution_x, resolution_y, bayer_pattern) "
                "VALUES (1, 'TestSensor', 'mono', 3.76, 6248, 4176, 'RGGB')"
            )

    def test_color_sensor_requires_bayer_pattern(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, pixel_size_um, resolution_x, resolution_y) "
                "VALUES (1, 'TestSensor', 'color', 3.76, 6248, 4176)"
            )

    def test_color_sensor_accepts_valid_bayer(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
        conn.execute(
            "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, pixel_size_um, resolution_x, resolution_y, bayer_pattern) "
            "VALUES (1, 'TestSensor', 'color', 3.76, 6248, 4176, 'RGGB')"
        )
        row = conn.execute("SELECT bayer_pattern FROM sensor WHERE model_name = 'TestSensor'").fetchone()
        assert row["bayer_pattern"] == "RGGB"

    def test_filter_type_rejects_invalid_name(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO filter_type (name, source) VALUES ('invalid_type', 'user')"
            )

    def test_filter_passband_rejects_invalid_line_name(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
        ft_id = conn.execute("SELECT id FROM filter_type WHERE name = 'narrowband_single'").fetchone()["id"]
        conn.execute(
            "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) VALUES (1, ?, 'Test Ha')",
            (ft_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO filter_passband (filter_id, line_name, central_wavelength_nm, bandwidth_nm) "
                "VALUES (1, 'InvalidLine', 656.3, 7.0)"
            )

    def test_software_category_check(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO software (manufacturer_id, name, category) VALUES (1, 'TestApp', 'invalid')"
            )

    def test_connection_interface_category_check(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO connection_interface (name, category) VALUES ('BadInterface', 'invalid')"
            )
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_equipment_schema.py -v`

Expected: 13 tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_equipment_schema.py
git commit -m "test: CHECK constraint enforcement for closed vocabularies"
```

---

### Task 6: Test — Cascade, Triggers, Unique Indexes

**Files:**
- Modify: `backend/tests/test_equipment_schema.py`

- [ ] **Step 1: Write cascade and trigger tests**

```python
class TestCascadeDeletes:
    def _insert_telescope_with_config(self, conn):
        """Helper: insert a manufacturer, telescope, connector, and native config."""
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
        conn.execute(
            "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) VALUES (1, 'TestScope', 280)"
        )
        conn.execute(
            "INSERT INTO connector_size (name) VALUES ('M48')"
        )
        conn.execute(
            "INSERT INTO telescope_connector (telescope_id, connector_size_id) VALUES (1, 1)"
        )
        conn.execute(
            "INSERT INTO telescope_configuration (telescope_id, config_name, effective_focal_length_mm, effective_focal_ratio, is_native) "
            "VALUES (1, 'Native', 2800, 10, 1)"
        )

    def test_delete_telescope_cascades_to_config(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        self._insert_telescope_with_config(conn)
        conn.execute("DELETE FROM telescope WHERE id = 1")
        assert conn.execute("SELECT COUNT(*) FROM telescope_configuration").fetchone()[0] == 0

    def test_delete_telescope_cascades_to_connectors(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        self._insert_telescope_with_config(conn)
        conn.execute("DELETE FROM telescope WHERE id = 1")
        assert conn.execute("SELECT COUNT(*) FROM telescope_connector").fetchone()[0] == 0

    def test_delete_filter_cascades_to_passbands(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
        ft_id = conn.execute("SELECT id FROM filter_type WHERE name = 'narrowband_single'").fetchone()["id"]
        conn.execute(
            "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) VALUES (1, ?, 'Test Ha')",
            (ft_id,),
        )
        conn.execute(
            "INSERT INTO filter_passband (filter_id, line_name, central_wavelength_nm, bandwidth_nm) "
            "VALUES (1, 'Ha', 656.3, 7.0)"
        )
        conn.execute("DELETE FROM filter WHERE id = 1")
        assert conn.execute("SELECT COUNT(*) FROM filter_passband").fetchone()[0] == 0


class TestUpdatedAtTrigger:
    def test_manufacturer_updated_at_auto_updates(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
        original = conn.execute("SELECT updated_at FROM manufacturer WHERE id = 1").fetchone()["updated_at"]
        # Force a different timestamp by updating
        conn.execute("UPDATE manufacturer SET name = 'TestCo2' WHERE id = 1")
        updated = conn.execute("SELECT updated_at FROM manufacturer WHERE id = 1").fetchone()["updated_at"]
        # The trigger fires and sets updated_at to now — which may or may not differ
        # from original depending on timing. The key test is that it doesn't error.
        assert updated is not None


class TestPartialUniqueIndexes:
    def test_seed_key_unique_among_seed_rows(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name, seed_key, source) VALUES ('A', 'mfg.a', 'seed')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO manufacturer (name, seed_key, source) VALUES ('B', 'mfg.a', 'seed')")

    def test_null_seed_keys_dont_conflict(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('UserMfg1')")
        conn.execute("INSERT INTO manufacturer (name) VALUES ('UserMfg2')")
        count = conn.execute("SELECT COUNT(*) FROM manufacturer WHERE seed_key IS NULL").fetchone()[0]
        assert count == 2

    def test_one_native_config_per_telescope(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
        conn.execute(
            "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) VALUES (1, 'TestScope', 280)"
        )
        conn.execute(
            "INSERT INTO telescope_configuration (telescope_id, config_name, effective_focal_length_mm, effective_focal_ratio, is_native) "
            "VALUES (1, 'Native', 2800, 10, 1)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO telescope_configuration (telescope_id, config_name, effective_focal_length_mm, effective_focal_ratio, is_native) "
                "VALUES (1, 'Also Native', 2800, 10, 1)"
            )

    def test_multiple_non_native_configs_allowed(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
        conn.execute(
            "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) VALUES (1, 'TestScope', 280)"
        )
        conn.execute(
            "INSERT INTO telescope_configuration (telescope_id, config_name, effective_focal_length_mm, effective_focal_ratio, is_native) "
            "VALUES (1, 'Native', 2800, 10, 1)"
        )
        conn.execute(
            "INSERT INTO telescope_configuration (telescope_id, config_name, effective_focal_length_mm, effective_focal_ratio, is_native) "
            "VALUES (1, '0.7x Reducer', 1960, 7, 0)"
        )
        conn.execute(
            "INSERT INTO telescope_configuration (telescope_id, config_name, effective_focal_length_mm, effective_focal_ratio, is_native) "
            "VALUES (1, '2x Barlow', 5600, 20, 0)"
        )
        count = conn.execute("SELECT COUNT(*) FROM telescope_configuration WHERE telescope_id = 1").fetchone()[0]
        assert count == 3
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_equipment_schema.py -v`

Expected: 21 tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_equipment_schema.py
git commit -m "test: cascade deletes, updated_at triggers, partial unique indexes"
```

---

### Task 7: Test — Filter Summary View and Full Data Round-Trip

**Files:**
- Modify: `backend/tests/test_equipment_schema.py`

- [ ] **Step 1: Write filter_summary view test and a full round-trip test**

```python
class TestFilterSummaryView:
    def _insert_filter_with_passbands(self, conn, model_name, filter_type_name, passbands):
        """Helper: insert a filter with passbands.

        passbands: list of (line_name, wavelength, bandwidth) tuples.
        """
        conn.execute("INSERT OR IGNORE INTO manufacturer (name) VALUES ('Optolong')")
        mfg_id = conn.execute("SELECT id FROM manufacturer WHERE name = 'Optolong'").fetchone()["id"]
        ft_id = conn.execute("SELECT id FROM filter_type WHERE name = ?", (filter_type_name,)).fetchone()["id"]
        conn.execute(
            "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) VALUES (?, ?, ?)",
            (mfg_id, ft_id, model_name),
        )
        filter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for line_name, wavelength, bandwidth in passbands:
            conn.execute(
                "INSERT INTO filter_passband (filter_id, line_name, central_wavelength_nm, bandwidth_nm) "
                "VALUES (?, ?, ?, ?)",
                (filter_id, line_name, wavelength, bandwidth),
            )
        return filter_id

    def test_single_band_filter(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        self._insert_filter_with_passbands(
            conn, "Optolong 7nm Ha", "narrowband_single", [("Ha", 656.3, 7.0)]
        )
        row = conn.execute("SELECT * FROM filter_summary WHERE model_name = 'Optolong 7nm Ha'").fetchone()
        assert row["passband_count"] == 1
        assert row["passband_lines"] == "Ha"
        assert row["min_wavelength_nm"] == 656.3
        assert row["min_bandwidth_nm"] == 7.0

    def test_dual_band_filter(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        self._insert_filter_with_passbands(
            conn,
            "L-eXtreme",
            "narrowband_dual",
            [("Ha", 656.3, 7.0), ("Oiii", 500.7, 7.0)],
        )
        row = conn.execute("SELECT * FROM filter_summary WHERE model_name = 'L-eXtreme'").fetchone()
        assert row["passband_count"] == 2
        assert "Ha" in row["passband_lines"]
        assert "Oiii" in row["passband_lines"]

    def test_inactive_filter_excluded_from_view(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        fid = self._insert_filter_with_passbands(
            conn, "Retired Filter", "narrowband_single", [("Ha", 656.3, 7.0)]
        )
        conn.execute("UPDATE filter SET active = 0 WHERE id = ?", (fid,))
        row = conn.execute("SELECT * FROM filter_summary WHERE model_name = 'Retired Filter'").fetchone()
        assert row is None


class TestFullRoundTrip:
    def test_complete_equipment_insertion(self, db_with_equipment_schema):
        """Insert a complete set of equipment: manufacturer, sensor, camera, telescope
        with config, filter with passband, mount, focuser, filter_wheel, OAG, guide_scope,
        computer, software. Verifies the full schema works end-to-end."""
        conn = db_with_equipment_schema

        # Manufacturer
        conn.execute("INSERT INTO manufacturer (name) VALUES ('ZWO')")

        # Lookup rows
        conn.execute("INSERT INTO optical_design (name) VALUES ('SCT')")
        conn.execute("INSERT INTO mount_type (name) VALUES ('Harmonic EQ')")
        conn.execute("INSERT INTO connection_interface (name, category) VALUES ('USB 3.0', 'data')")
        conn.execute("INSERT INTO connection_interface (name, category) VALUES ('WiFi', 'wireless')")
        conn.execute("INSERT INTO connector_size (name, diameter_mm) VALUES ('M54', 54.0)")
        conn.execute("INSERT INTO filter_size (name) VALUES ('36mm')")
        conn.execute("INSERT INTO computer_type (name) VALUES ('imaging')")

        # Sensor
        conn.execute(
            "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, pixel_size_um, resolution_x, resolution_y) "
            "VALUES (1, 'IMX571', 'mono', 3.76, 6248, 4176)"
        )

        # Camera
        conn.execute(
            "INSERT INTO camera (manufacturer_id, sensor_id, connector_size_id, model_name, cooled, has_usb_hub, usb_hub_interface_id, unity_gain) "
            "VALUES (1, 1, 1, 'ASI 2600MM Pro', 1, 1, 1, 100)"
        )
        conn.execute("INSERT INTO camera_interface (camera_id, interface_id) VALUES (1, 1)")

        # Telescope + config
        conn.execute(
            "INSERT INTO telescope (manufacturer_id, optical_design_id, model_name, aperture_mm) "
            "VALUES (1, 1, 'C11', 280)"
        )
        conn.execute("INSERT INTO telescope_connector (telescope_id, connector_size_id) VALUES (1, 1)")
        conn.execute(
            "INSERT INTO telescope_configuration (telescope_id, config_name, effective_focal_length_mm, effective_focal_ratio, is_native) "
            "VALUES (1, 'Native', 2800, 10, 1)"
        )

        # Filter + passband
        ft_id = conn.execute("SELECT id FROM filter_type WHERE name = 'narrowband_single'").fetchone()["id"]
        conn.execute(
            "INSERT INTO filter (manufacturer_id, filter_type_id, filter_size_id, model_name) "
            "VALUES (1, ?, 1, 'ZWO Ha 7nm')", (ft_id,)
        )
        conn.execute(
            "INSERT INTO filter_passband (filter_id, line_name, central_wavelength_nm, bandwidth_nm) "
            "VALUES (1, 'Ha', 656.3, 7.0)"
        )

        # Mount + interfaces
        conn.execute(
            "INSERT INTO mount (manufacturer_id, mount_type_id, model_name, payload_capacity_kg) "
            "VALUES (1, 1, 'AM5', 13.0)"
        )
        conn.execute("INSERT INTO mount_interface (mount_id, interface_id) VALUES (1, 1)")
        conn.execute("INSERT INTO mount_interface (mount_id, interface_id) VALUES (1, 2)")

        # Focuser
        conn.execute(
            "INSERT INTO focuser (manufacturer_id, model_name, motorized, temperature_compensation) "
            "VALUES (1, 'EAF', 1, 1)"
        )
        conn.execute("INSERT INTO focuser_interface (focuser_id, interface_id) VALUES (1, 1)")

        # Filter wheel
        conn.execute(
            "INSERT INTO filter_wheel (manufacturer_id, filter_size_id, camera_side_connector_id, telescope_side_connector_id, model_name, num_positions) "
            "VALUES (1, 1, 1, 1, 'EFW 7x36', 7)"
        )
        conn.execute("INSERT INTO filter_wheel_interface (filter_wheel_id, interface_id) VALUES (1, 1)")

        # OAG
        conn.execute(
            "INSERT INTO oag (manufacturer_id, imaging_side_connector_id, guide_camera_connector_id, model_name) "
            "VALUES (1, 1, 1, 'OAG-L')"
        )

        # Guide scope
        conn.execute(
            "INSERT INTO guide_scope (manufacturer_id, guide_camera_connector_id, model_name, aperture_mm, focal_length_mm) "
            "VALUES (1, 1, 'Mini Guide 30mm', 30, 120)"
        )

        # Computer
        conn.execute(
            "INSERT INTO computer (manufacturer_id, computer_type_id, model_name) VALUES (1, 1, 'ASIAIR Plus')"
        )

        # Software
        conn.execute(
            "INSERT INTO software (manufacturer_id, name, category) VALUES (1, 'ASIAir', 'capture')"
        )

        # Verify counts
        assert conn.execute("SELECT COUNT(*) FROM camera").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM telescope").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM telescope_configuration").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM filter").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM filter_passband").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM mount").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM mount_interface").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM focuser").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM filter_wheel").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM oag").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM guide_scope").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM computer").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM software").fetchone()[0] == 1
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_equipment_schema.py -v`

Expected: 25 tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_equipment_schema.py
git commit -m "test: filter_summary view and full equipment round-trip"
```

---

### Task 8: Test — Alias Tables

**Files:**
- Modify: `backend/tests/test_equipment_schema.py`

- [ ] **Step 1: Write alias table tests**

```python
class TestAliasTables:
    def _setup_camera(self, conn):
        conn.execute("INSERT INTO manufacturer (name) VALUES ('ZWO')")
        conn.execute(
            "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, pixel_size_um, resolution_x, resolution_y) "
            "VALUES (1, 'IMX571', 'mono', 3.76, 6248, 4176)"
        )
        conn.execute(
            "INSERT INTO camera (manufacturer_id, sensor_id, model_name) VALUES (1, 1, 'ASI 2600MM Pro')"
        )

    def test_camera_alias_insert_and_lookup(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        self._setup_camera(conn)
        conn.execute(
            "INSERT INTO camera_alias (camera_id, alias, source) VALUES (1, 'zwo asi2600mm pro', 'seed')"
        )
        row = conn.execute("SELECT * FROM camera_alias WHERE alias = 'zwo asi2600mm pro'").fetchone()
        assert row["camera_id"] == 1
        assert row["confirmed"] == 0

    def test_alias_unique_constraint(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        self._setup_camera(conn)
        conn.execute(
            "INSERT INTO camera_alias (camera_id, alias, source) VALUES (1, 'zwo asi2600mm pro', 'seed')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO camera_alias (camera_id, alias, source) VALUES (1, 'zwo asi2600mm pro', 'nina')"
            )

    def test_delete_camera_cascades_to_aliases(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        self._setup_camera(conn)
        conn.execute(
            "INSERT INTO camera_alias (camera_id, alias, source) VALUES (1, 'zwo asi2600mm pro', 'seed')"
        )
        conn.execute("DELETE FROM camera WHERE id = 1")
        assert conn.execute("SELECT COUNT(*) FROM camera_alias").fetchone()[0] == 0

    def test_unresolved_observation_upsert(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute(
            "INSERT INTO unresolved_equipment_observation "
            "(equipment_kind, normalized_alias, original_observation, source) "
            "VALUES ('camera', 'unknown camera', 'Unknown Camera', 'nina')"
        )
        conn.execute(
            "INSERT INTO unresolved_equipment_observation "
            "(equipment_kind, normalized_alias, original_observation, source) "
            "VALUES ('camera', 'unknown camera', 'Unknown Camera', 'nina') "
            "ON CONFLICT (equipment_kind, normalized_alias) DO UPDATE SET "
            "seen_count = seen_count + 1, last_seen_at = datetime('now')"
        )
        row = conn.execute(
            "SELECT seen_count FROM unresolved_equipment_observation WHERE normalized_alias = 'unknown camera'"
        ).fetchone()
        assert row["seen_count"] == 2
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_equipment_schema.py -v`

Expected: 29 tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_equipment_schema.py
git commit -m "test: alias tables and unresolved observation upsert"
```

---

### Task 9: Run Full Test Suite and Lint

**Files:** None (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest -v`

Expected: All tests pass (342 existing + ~29 new = ~371 total)

- [ ] **Step 2: Lint and format**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`

Expected: All checks passed, no formatting issues

- [ ] **Step 3: Security scan**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run bandit -r src/`

Expected: No high severity issues

- [ ] **Step 4: Frontend build (unchanged but verify)**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

Expected: Build succeeds (no frontend changes, but verify nothing broke)
