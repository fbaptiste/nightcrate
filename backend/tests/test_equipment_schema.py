"""Comprehensive tests for the equipment schema migration (0005)."""

import importlib.resources
import sqlite3
import time

import pytest


@pytest.fixture
def db_with_equipment_schema(tmp_path):
    """Apply all migrations up through 0005 to a fresh SQLite database."""
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


# -- helpers ----------------------------------------------------------


def _insert_manufacturer(conn, name="TestMfg"):
    """Insert a manufacturer and return its id."""
    conn.execute("INSERT INTO manufacturer (name) VALUES (?)", (name,))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_sensor(conn, manufacturer_id, *, model="TestSensor", mono=True):
    """Insert a sensor and return its id."""
    conn.execute(
        """
        INSERT INTO sensor
            (manufacturer_id, model_name, sensor_type,
             pixel_size_um, resolution_x, resolution_y, bayer_pattern)
        VALUES (?, ?, ?, 3.76, 6248, 4176, ?)
        """,
        (
            manufacturer_id,
            model,
            "mono" if mono else "color",
            None if mono else "RGGB",
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_camera(conn, manufacturer_id, sensor_id, *, model="TestCam"):
    """Insert a camera and return its id."""
    conn.execute(
        "INSERT INTO camera (manufacturer_id, sensor_id, model_name) VALUES (?, ?, ?)",
        (manufacturer_id, sensor_id, model),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_telescope(conn, manufacturer_id, *, model="TestScope"):
    """Insert a telescope and return its id."""
    conn.execute(
        "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) VALUES (?, ?, 280)",
        (manufacturer_id, model),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _get_filter_type_id(conn, name="narrowband_single"):
    """Get a seeded filter_type id by name."""
    row = conn.execute("SELECT id FROM filter_type WHERE name = ?", (name,)).fetchone()
    return row[0]


def _insert_filter(conn, manufacturer_id, filter_type_id, *, model="TestFilter"):
    """Insert a filter and return its id."""
    conn.execute(
        "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) VALUES (?, ?, ?)",
        (manufacturer_id, filter_type_id, model),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_connection_interface(conn, name="USB 3.0", category="data"):
    """Insert a connection_interface and return its id."""
    conn.execute(
        "INSERT INTO connection_interface (name, category) VALUES (?, ?)",
        (name, category),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_connector_size(conn, name="M42"):
    """Insert a connector_size and return its id."""
    conn.execute("INSERT INTO connector_size (name) VALUES (?)", (name,))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# -- test classes -----------------------------------------------------


class TestMigrationApplies:
    """Verify all expected tables and views exist after migration."""

    EXPECTED_TABLES = sorted(
        [
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
        ]
    )

    def test_all_31_tables_exist(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_yoyo%' "
            "ORDER BY name"
        ).fetchall()
        table_names = sorted(r["name"] for r in rows)
        # Filter to only equipment-schema tables (exclude earlier migrations)
        equipment_tables = [t for t in table_names if t in self.EXPECTED_TABLES]
        assert equipment_tables == self.EXPECTED_TABLES
        assert len(equipment_tables) == 31

    def test_filter_summary_view_exists(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view' AND name='filter_summary'"
        ).fetchall()
        assert len(rows) == 1


class TestFilterTypeSeedData:
    """Verify filter_type seed data is correctly inserted."""

    def test_nine_filter_type_rows(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        count = conn.execute("SELECT COUNT(*) FROM filter_type").fetchone()[0]
        assert count == 9

    def test_all_source_seed(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        non_seed = conn.execute(
            "SELECT COUNT(*) FROM filter_type WHERE source != 'seed'"
        ).fetchone()[0]
        assert non_seed == 0

    def test_all_seed_keys_prefixed(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        rows = conn.execute("SELECT seed_key FROM filter_type").fetchall()
        for row in rows:
            assert row["seed_key"].startswith("filter_type.")


class TestCheckConstraints:
    """Verify CHECK constraints on various tables."""

    def test_sensor_type_rejects_invalid(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sensor "
                "(manufacturer_id, model_name, sensor_type, "
                "pixel_size_um, resolution_x, resolution_y) "
                "VALUES (?, 'Bad', 'invalid', 3.76, 100, 100)",
                (mfg_id,),
            )

    def test_mono_sensor_rejects_bayer_pattern(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sensor "
                "(manufacturer_id, model_name, sensor_type, "
                "pixel_size_um, resolution_x, resolution_y, bayer_pattern) "
                "VALUES (?, 'MonoBayer', 'mono', 3.76, 100, 100, 'RGGB')",
                (mfg_id,),
            )

    def test_color_sensor_requires_bayer_pattern(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sensor "
                "(manufacturer_id, model_name, sensor_type, "
                "pixel_size_um, resolution_x, resolution_y) "
                "VALUES (?, 'ColorNoBayer', 'color', 3.76, 100, 100)",
                (mfg_id,),
            )

    def test_color_sensor_accepts_valid_bayer(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        conn.execute(
            "INSERT INTO sensor "
            "(manufacturer_id, model_name, sensor_type, "
            "pixel_size_um, resolution_x, resolution_y, bayer_pattern) "
            "VALUES (?, 'ColorOK', 'color', 3.76, 100, 100, 'RGGB')",
            (mfg_id,),
        )
        row = conn.execute("SELECT bayer_pattern FROM sensor WHERE model_name='ColorOK'").fetchone()
        assert row["bayer_pattern"] == "RGGB"

    def test_filter_type_rejects_invalid_name(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO filter_type (name, source, seed_key) "
                "VALUES ('bogus_type', 'user', NULL)"
            )

    def test_filter_passband_rejects_invalid_line_name(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        ft_id = _get_filter_type_id(conn, "narrowband_single")
        f_id = _insert_filter(conn, mfg_id, ft_id)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO filter_passband "
                "(filter_id, line_name, central_wavelength_nm, bandwidth_nm) "
                "VALUES (?, 'INVALID', 656.3, 7.0)",
                (f_id,),
            )

    def test_software_category_check(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO software (manufacturer_id, name, category) "
                "VALUES (?, 'BadSW', 'hacking')",
                (mfg_id,),
            )

    def test_connection_interface_category_check(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO connection_interface (name, category) VALUES ('BadIface', 'quantum')"
            )


class TestCascadeDeletes:
    """Verify ON DELETE CASCADE behavior."""

    def test_delete_telescope_cascades_to_configuration(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        scope_id = _insert_telescope(conn, mfg_id)
        conn.execute(
            "INSERT INTO telescope_configuration "
            "(telescope_id, config_name, effective_focal_length_mm, "
            "effective_focal_ratio) "
            "VALUES (?, 'Native', 2800, 10)",
            (scope_id,),
        )
        assert conn.execute("SELECT COUNT(*) FROM telescope_configuration").fetchone()[0] == 1
        conn.execute("DELETE FROM telescope WHERE id = ?", (scope_id,))
        assert conn.execute("SELECT COUNT(*) FROM telescope_configuration").fetchone()[0] == 0

    def test_delete_telescope_cascades_to_connector(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        scope_id = _insert_telescope(conn, mfg_id)
        cs_id = _insert_connector_size(conn)
        conn.execute(
            "INSERT INTO telescope_connector (telescope_id, connector_size_id) VALUES (?, ?)",
            (scope_id, cs_id),
        )
        assert conn.execute("SELECT COUNT(*) FROM telescope_connector").fetchone()[0] == 1
        conn.execute("DELETE FROM telescope WHERE id = ?", (scope_id,))
        assert conn.execute("SELECT COUNT(*) FROM telescope_connector").fetchone()[0] == 0

    def test_delete_filter_cascades_to_passband(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        ft_id = _get_filter_type_id(conn, "narrowband_single")
        f_id = _insert_filter(conn, mfg_id, ft_id)
        conn.execute(
            "INSERT INTO filter_passband "
            "(filter_id, line_name, central_wavelength_nm, bandwidth_nm) "
            "VALUES (?, 'Ha', 656.3, 7.0)",
            (f_id,),
        )
        assert conn.execute("SELECT COUNT(*) FROM filter_passband").fetchone()[0] == 1
        conn.execute("DELETE FROM filter WHERE id = ?", (f_id,))
        assert conn.execute("SELECT COUNT(*) FROM filter_passband").fetchone()[0] == 0


class TestUpdatedAtTrigger:
    """Verify updated_at auto-updates on UPDATE via triggers."""

    def test_manufacturer_updated_at_auto_updates(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        original = conn.execute(
            "SELECT updated_at FROM manufacturer WHERE id = ?", (mfg_id,)
        ).fetchone()["updated_at"]

        # Ensure time difference (SQLite datetime resolution is 1 second)
        time.sleep(1.1)

        conn.execute(
            "UPDATE manufacturer SET website = 'https://example.com' WHERE id = ?",
            (mfg_id,),
        )
        updated = conn.execute(
            "SELECT updated_at FROM manufacturer WHERE id = ?", (mfg_id,)
        ).fetchone()["updated_at"]

        assert updated > original


class TestPartialUniqueIndexes:
    """Verify partial unique indexes work correctly."""

    def test_seed_key_unique_among_non_null(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name, seed_key) VALUES ('A', 'mfg.a')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO manufacturer (name, seed_key) VALUES ('B', 'mfg.a')")

    def test_null_seed_keys_dont_conflict(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        conn.execute("INSERT INTO manufacturer (name, seed_key) VALUES ('NullA', NULL)")
        conn.execute("INSERT INTO manufacturer (name, seed_key) VALUES ('NullB', NULL)")
        count = conn.execute("SELECT COUNT(*) FROM manufacturer WHERE seed_key IS NULL").fetchone()[
            0
        ]
        assert count == 2

    def test_only_one_native_per_telescope(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        scope_id = _insert_telescope(conn, mfg_id)
        conn.execute(
            "INSERT INTO telescope_configuration "
            "(telescope_id, config_name, effective_focal_length_mm, "
            "effective_focal_ratio, is_native) "
            "VALUES (?, 'Native', 2800, 10, 1)",
            (scope_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO telescope_configuration "
                "(telescope_id, config_name, effective_focal_length_mm, "
                "effective_focal_ratio, is_native) "
                "VALUES (?, 'Also Native', 2800, 10, 1)",
                (scope_id,),
            )

    def test_multiple_non_native_configs_allowed(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        scope_id = _insert_telescope(conn, mfg_id)
        conn.execute(
            "INSERT INTO telescope_configuration "
            "(telescope_id, config_name, effective_focal_length_mm, "
            "effective_focal_ratio, is_native) "
            "VALUES (?, 'Reducer', 1960, 7, 0)",
            (scope_id,),
        )
        conn.execute(
            "INSERT INTO telescope_configuration "
            "(telescope_id, config_name, effective_focal_length_mm, "
            "effective_focal_ratio, is_native) "
            "VALUES (?, 'Barlow', 5600, 20, 0)",
            (scope_id,),
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM telescope_configuration WHERE telescope_id = ? AND is_native = 0",
            (scope_id,),
        ).fetchone()[0]
        assert count == 2


class TestFilterSummaryView:
    """Verify the filter_summary view aggregates correctly."""

    def test_single_band_filter(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        ft_id = _get_filter_type_id(conn, "narrowband_single")
        f_id = _insert_filter(conn, mfg_id, ft_id, model="Ha 7nm")
        conn.execute(
            "INSERT INTO filter_passband "
            "(filter_id, line_name, central_wavelength_nm, bandwidth_nm) "
            "VALUES (?, 'Ha', 656.3, 7.0)",
            (f_id,),
        )
        row = conn.execute("SELECT * FROM filter_summary WHERE filter_id = ?", (f_id,)).fetchone()
        assert row["passband_count"] == 1
        assert row["passband_lines"] == "Ha"
        assert row["filter_type_name"] == "narrowband_single"

    def test_dual_band_filter(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        ft_id = _get_filter_type_id(conn, "narrowband_dual")
        f_id = _insert_filter(conn, mfg_id, ft_id, model="HaOiii Dual")
        conn.execute(
            "INSERT INTO filter_passband "
            "(filter_id, line_name, central_wavelength_nm, bandwidth_nm) "
            "VALUES (?, 'Ha', 656.3, 7.0)",
            (f_id,),
        )
        conn.execute(
            "INSERT INTO filter_passband "
            "(filter_id, line_name, central_wavelength_nm, bandwidth_nm) "
            "VALUES (?, 'Oiii', 500.7, 7.0)",
            (f_id,),
        )
        row = conn.execute("SELECT * FROM filter_summary WHERE filter_id = ?", (f_id,)).fetchone()
        assert row["passband_count"] == 2
        # GROUP_CONCAT order may vary; check both lines present
        lines = set(row["passband_lines"].split("+"))
        assert lines == {"Ha", "Oiii"}

    def test_inactive_filter_excluded(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        ft_id = _get_filter_type_id(conn, "broadband_luminance")
        f_id = _insert_filter(conn, mfg_id, ft_id, model="OldFilter")
        conn.execute("UPDATE filter SET active = 0 WHERE id = ?", (f_id,))
        row = conn.execute("SELECT * FROM filter_summary WHERE filter_id = ?", (f_id,)).fetchone()
        assert row is None


class TestFullRoundTrip:
    """Insert a complete equipment set and verify counts."""

    def test_full_equipment_set(self, db_with_equipment_schema):
        conn = db_with_equipment_schema

        # Manufacturer
        mfg_id = _insert_manufacturer(conn, "ZWO")
        mfg2_id = _insert_manufacturer(conn, "Celestron")
        mfg3_id = _insert_manufacturer(conn, "Optolong")
        mfg4_id = _insert_manufacturer(conn, "iOptron")
        mfg5_id = _insert_manufacturer(conn, "ZWO-Software")
        mfg6_id = _insert_manufacturer(conn, "Intel")

        # Connection interface
        usb_id = _insert_connection_interface(conn, "USB 3.0", "data")

        # Connector size
        cs_id = _insert_connector_size(conn, "M42")

        # Sensor
        sensor_id = _insert_sensor(conn, mfg_id, model="IMX571")

        # Camera with interface
        cam_id = _insert_camera(conn, mfg_id, sensor_id, model="ASI 2600MM Pro")
        conn.execute(
            "INSERT INTO camera_interface (camera_id, interface_id) VALUES (?, ?)",
            (cam_id, usb_id),
        )

        # Telescope with connector and configuration
        scope_id = _insert_telescope(conn, mfg2_id, model="C11 EdgeHD")
        conn.execute(
            "INSERT INTO telescope_connector (telescope_id, connector_size_id) VALUES (?, ?)",
            (scope_id, cs_id),
        )
        conn.execute(
            "INSERT INTO telescope_configuration "
            "(telescope_id, config_name, effective_focal_length_mm, "
            "effective_focal_ratio, is_native) "
            "VALUES (?, 'Native', 2800, 10, 1)",
            (scope_id,),
        )

        # Filter with passband
        ft_id = _get_filter_type_id(conn, "narrowband_single")
        f_id = _insert_filter(conn, mfg3_id, ft_id, model="Ha 7nm")
        conn.execute(
            "INSERT INTO filter_passband "
            "(filter_id, line_name, central_wavelength_nm, bandwidth_nm) "
            "VALUES (?, 'Ha', 656.3, 7.0)",
            (f_id,),
        )

        # Mount with interface
        conn.execute("INSERT INTO mount_type (name) VALUES ('GEM')")
        mt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO mount (manufacturer_id, mount_type_id, model_name) "
            "VALUES (?, ?, 'CEM70G')",
            (mfg4_id, mt_id),
        )
        mount_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO mount_interface (mount_id, interface_id) VALUES (?, ?)",
            (mount_id, usb_id),
        )

        # Focuser
        conn.execute(
            "INSERT INTO focuser (manufacturer_id, model_name) VALUES (?, 'EAF')",
            (mfg_id,),
        )

        # Filter wheel
        conn.execute(
            "INSERT INTO filter_wheel "
            "(manufacturer_id, model_name, num_positions) "
            "VALUES (?, 'EFW', 7)",
            (mfg_id,),
        )

        # OAG
        conn.execute(
            "INSERT INTO oag (manufacturer_id, model_name) VALUES (?, 'OAG-L')",
            (mfg_id,),
        )

        # Guide scope
        conn.execute(
            "INSERT INTO guide_scope (manufacturer_id, model_name) VALUES (?, 'Mini Guide Scope')",
            (mfg_id,),
        )

        # Computer
        conn.execute("INSERT INTO computer_type (name) VALUES ('Mini PC')")
        ct_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO computer "
            "(manufacturer_id, computer_type_id, model_name) "
            "VALUES (?, ?, 'NUC')",
            (mfg6_id, ct_id),
        )

        # Software
        conn.execute(
            "INSERT INTO software (manufacturer_id, name, category) "
            "VALUES (?, 'ASIAIR', 'capture')",
            (mfg5_id,),
        )

        # Verify counts
        assert conn.execute("SELECT COUNT(*) FROM manufacturer").fetchone()[0] == 6
        assert conn.execute("SELECT COUNT(*) FROM sensor").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM camera").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM camera_interface").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM telescope").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM telescope_connector").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM telescope_configuration").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM filter").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM filter_passband").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM mount").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM mount_interface").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM focuser").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM filter_wheel").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM oag").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM guide_scope").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM computer").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM software").fetchone()[0] == 1


class TestAliasTables:
    """Verify alias and unresolved observation tables."""

    def test_camera_alias_insert_and_lookup(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        sensor_id = _insert_sensor(conn, mfg_id)
        cam_id = _insert_camera(conn, mfg_id, sensor_id)
        conn.execute(
            "INSERT INTO camera_alias (camera_id, alias, source) "
            "VALUES (?, 'ZWO ASI2600MM Pro', 'nina')",
            (cam_id,),
        )
        row = conn.execute(
            "SELECT * FROM camera_alias WHERE alias = 'ZWO ASI2600MM Pro'"
        ).fetchone()
        assert row["camera_id"] == cam_id
        assert row["source"] == "nina"
        assert row["confirmed"] == 0

    def test_alias_unique_constraint(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        sensor_id = _insert_sensor(conn, mfg_id)
        cam_id = _insert_camera(conn, mfg_id, sensor_id)
        conn.execute(
            "INSERT INTO camera_alias (camera_id, alias, source) VALUES (?, 'DupeAlias', 'nina')",
            (cam_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO camera_alias (camera_id, alias, source) "
                "VALUES (?, 'DupeAlias', 'user')",
                (cam_id,),
            )

    def test_delete_camera_cascades_to_aliases(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        mfg_id = _insert_manufacturer(conn)
        sensor_id = _insert_sensor(conn, mfg_id)
        cam_id = _insert_camera(conn, mfg_id, sensor_id)
        conn.execute(
            "INSERT INTO camera_alias (camera_id, alias, source) VALUES (?, 'CascadeTest', 'nina')",
            (cam_id,),
        )
        assert conn.execute("SELECT COUNT(*) FROM camera_alias").fetchone()[0] == 1
        conn.execute("DELETE FROM camera WHERE id = ?", (cam_id,))
        assert conn.execute("SELECT COUNT(*) FROM camera_alias").fetchone()[0] == 0

    def test_unresolved_observation_upsert(self, db_with_equipment_schema):
        conn = db_with_equipment_schema
        # First observation
        conn.execute(
            "INSERT INTO unresolved_equipment_observation "
            "(equipment_kind, normalized_alias, original_observation, source) "
            "VALUES ('camera', 'zwo asi2600mm pro', "
            "'ZWO ASI2600MM Pro', 'nina')"
        )
        row = conn.execute(
            "SELECT seen_count FROM unresolved_equipment_observation "
            "WHERE normalized_alias = 'zwo asi2600mm pro'"
        ).fetchone()
        assert row["seen_count"] == 1

        # Upsert — increment seen_count
        conn.execute(
            "INSERT INTO unresolved_equipment_observation "
            "(equipment_kind, normalized_alias, original_observation, source) "
            "VALUES ('camera', 'zwo asi2600mm pro', "
            "'ZWO ASI2600MM Pro', 'nina') "
            "ON CONFLICT(equipment_kind, normalized_alias) DO UPDATE "
            "SET seen_count = seen_count + 1, "
            "last_seen_at = datetime('now')"
        )
        row = conn.execute(
            "SELECT seen_count FROM unresolved_equipment_observation "
            "WHERE normalized_alias = 'zwo asi2600mm pro'"
        ).fetchone()
        assert row["seen_count"] == 2
