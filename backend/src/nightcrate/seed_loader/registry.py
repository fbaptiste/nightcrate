"""
Seedable table registry.

Declares every table the seed loader knows about: its CSV filename,
which fields go into the hash, FK column mappings, and the correct
load order (parents before children, referenced tables before referencing ones).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SeedableTable:
    table_name: str
    csv_filename: str
    seeded_fields: tuple[str, ...]  # DB column names included in the seed hash
    fk_columns: dict[str, str] = field(default_factory=dict)  # csv_col → referenced table
    # for child tables: the CSV FK column that resolves to the parent id
    parent_key_column: str | None = None
    is_junction: bool = False
    junction_parent: str | None = None
    junction_key_columns: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# LOAD ORDER — 29 entries, parents always precede children
# ---------------------------------------------------------------------------

LOAD_ORDER: list[SeedableTable] = [
    # ------------------------------------------------------------------
    # 1-7: Lookup / reference tables (no FK dependencies)
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="manufacturer",
        csv_filename="manufacturer.csv",
        seeded_fields=("name", "website", "notes"),
    ),
    SeedableTable(
        table_name="optical_design",
        csv_filename="optical_design.csv",
        seeded_fields=("name", "description"),
    ),
    SeedableTable(
        table_name="mount_type",
        csv_filename="mount_type.csv",
        seeded_fields=("name", "description"),
    ),
    SeedableTable(
        table_name="connection_interface",
        csv_filename="connection_interface.csv",
        seeded_fields=("name", "category", "notes"),
    ),
    SeedableTable(
        table_name="connector_size",
        csv_filename="connector_size.csv",
        seeded_fields=("name", "diameter_mm", "notes"),
    ),
    SeedableTable(
        table_name="filter_size",
        csv_filename="filter_size.csv",
        seeded_fields=("name", "description"),
    ),
    SeedableTable(
        table_name="computer_type",
        csv_filename="computer_type.csv",
        seeded_fields=("name", "description"),
    ),
    SeedableTable(
        table_name="filter_type",
        csv_filename="filter_type.csv",
        seeded_fields=("name", "description"),
    ),
    # ------------------------------------------------------------------
    # 9: sensor — FK: manufacturer_id → manufacturer
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="sensor",
        csv_filename="sensor.csv",
        seeded_fields=(
            "manufacturer_id",
            "model_name",
            "sensor_type",
            "pixel_size_um",
            "resolution_x",
            "resolution_y",
            "sensor_width_mm",
            "sensor_height_mm",
            "adc_bit_depth",
            "full_well_capacity_ke",
            "read_noise_e",
            "peak_qe_pct",
            "bayer_pattern",
            "dual_gain",
            "hcg_threshold_gain",
            "notes",
        ),
        fk_columns={
            "manufacturer_seed_key": "manufacturer",
        },
    ),
    # ------------------------------------------------------------------
    # 9: camera — FKs: manufacturer, sensor (×2), connector_size,
    #             connection_interface
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="camera",
        csv_filename="camera.csv",
        seeded_fields=(
            "manufacturer_id",
            "sensor_id",
            "guide_sensor_id",
            "connector_size_id",
            "model_name",
            "cooled",
            "cooling_delta_c",
            "back_focus_mm",
            "weight_g",
            "tilt_adapter",
            "has_usb_hub",
            "usb_hub_interface_id",
            "unity_gain",
            "notes",
        ),
        fk_columns={
            "manufacturer_seed_key": "manufacturer",
            "sensor_seed_key": "sensor",
            "guide_sensor_seed_key": "sensor",
            "connector_size_seed_key": "connector_size",
            "usb_hub_interface_seed_key": "connection_interface",
        },
    ),
    # ------------------------------------------------------------------
    # 10: camera_interface — junction (camera × connection_interface)
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="camera_interface",
        csv_filename="camera_interface.csv",
        seeded_fields=("camera_id", "interface_id"),
        fk_columns={
            "camera_seed_key": "camera",
            "interface_seed_key": "connection_interface",
        },
        is_junction=True,
        junction_parent="camera",
        junction_key_columns=("camera_id", "interface_id"),
    ),
    # ------------------------------------------------------------------
    # 11: telescope — FKs: manufacturer, optical_design
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="telescope",
        csv_filename="telescope.csv",
        seeded_fields=(
            "manufacturer_id",
            "optical_design_id",
            "model_name",
            "aperture_mm",
            "image_circle_mm",
            "weight_kg",
            "obstruction_pct",
            "notes",
        ),
        fk_columns={
            "manufacturer_seed_key": "manufacturer",
            "optical_design_seed_key": "optical_design",
        },
    ),
    # ------------------------------------------------------------------
    # 12: telescope_connector — junction (telescope × connector_size)
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="telescope_connector",
        csv_filename="telescope_connector.csv",
        seeded_fields=("telescope_id", "connector_size_id"),
        fk_columns={
            "telescope_seed_key": "telescope",
            "connector_size_seed_key": "connector_size",
        },
        is_junction=True,
        junction_parent="telescope",
        junction_key_columns=("telescope_id", "connector_size_id"),
    ),
    # ------------------------------------------------------------------
    # 13: telescope_configuration — child of telescope
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="telescope_configuration",
        csv_filename="telescope_configuration.csv",
        seeded_fields=(
            "telescope_id",
            "config_name",
            "accessory_name",
            "reduction_factor",
            "effective_focal_length_mm",
            "effective_focal_ratio",
            "effective_image_circle_mm",
            "effective_back_focus_mm",
            "is_native",
            "notes",
        ),
        fk_columns={
            "telescope_seed_key": "telescope",
        },
        parent_key_column="telescope_seed_key",
    ),
    # ------------------------------------------------------------------
    # 14: filter — FKs: manufacturer, filter_type, filter_size
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="filter",
        csv_filename="filter.csv",
        seeded_fields=(
            "manufacturer_id",
            "filter_type_id",
            "filter_size_id",
            "model_name",
            "peak_transmission_pct",
            "mounted_thickness_mm",
            "notes",
        ),
        fk_columns={
            "manufacturer_seed_key": "manufacturer",
            "filter_type_seed_key": "filter_type",
            "filter_size_seed_key": "filter_size",
        },
    ),
    # ------------------------------------------------------------------
    # 15: filter_passband — child of filter
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="filter_passband",
        csv_filename="filter_passband.csv",
        seeded_fields=(
            "filter_id",
            "line_name",
            "central_wavelength_nm",
            "bandwidth_nm",
            "peak_transmission_pct",
        ),
        fk_columns={
            "filter_seed_key": "filter",
        },
        parent_key_column="filter_seed_key",
    ),
    # ------------------------------------------------------------------
    # 16: mount — FKs: manufacturer, mount_type
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="mount",
        csv_filename="mount.csv",
        seeded_fields=(
            "manufacturer_id",
            "mount_type_id",
            "model_name",
            "payload_capacity_kg",
            "mount_weight_kg",
            "counterweight_required",
            "goto_capable",
            "periodic_error_arcsec",
            "drive_type",
            "notes",
        ),
        fk_columns={
            "manufacturer_seed_key": "manufacturer",
            "mount_type_seed_key": "mount_type",
        },
    ),
    # ------------------------------------------------------------------
    # 17: mount_interface — junction (mount × connection_interface)
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="mount_interface",
        csv_filename="mount_interface.csv",
        seeded_fields=("mount_id", "interface_id"),
        fk_columns={
            "mount_seed_key": "mount",
            "interface_seed_key": "connection_interface",
        },
        is_junction=True,
        junction_parent="mount",
        junction_key_columns=("mount_id", "interface_id"),
    ),
    # ------------------------------------------------------------------
    # 18: focuser — FK: manufacturer
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="focuser",
        csv_filename="focuser.csv",
        seeded_fields=(
            "manufacturer_id",
            "model_name",
            "motorized",
            "travel_range_mm",
            "step_size_um",
            "total_steps",
            "temperature_compensation",
            "backlash_steps",
            "notes",
        ),
        fk_columns={
            "manufacturer_seed_key": "manufacturer",
        },
    ),
    # ------------------------------------------------------------------
    # 19: focuser_interface — junction (focuser × connection_interface)
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="focuser_interface",
        csv_filename="focuser_interface.csv",
        seeded_fields=("focuser_id", "interface_id"),
        fk_columns={
            "focuser_seed_key": "focuser",
            "interface_seed_key": "connection_interface",
        },
        is_junction=True,
        junction_parent="focuser",
        junction_key_columns=("focuser_id", "interface_id"),
    ),
    # ------------------------------------------------------------------
    # 20: filter_wheel — FKs: manufacturer, filter_size, connector_size (×2)
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="filter_wheel",
        csv_filename="filter_wheel.csv",
        seeded_fields=(
            "manufacturer_id",
            "filter_size_id",
            "camera_side_connector_id",
            "telescope_side_connector_id",
            "model_name",
            "num_positions",
            "back_focus_contribution_mm",
            "notes",
        ),
        fk_columns={
            "manufacturer_seed_key": "manufacturer",
            "filter_size_seed_key": "filter_size",
            "camera_side_connector_seed_key": "connector_size",
            "telescope_side_connector_seed_key": "connector_size",
        },
    ),
    # ------------------------------------------------------------------
    # 21: filter_wheel_interface — junction (filter_wheel × connection_interface)
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="filter_wheel_interface",
        csv_filename="filter_wheel_interface.csv",
        seeded_fields=("filter_wheel_id", "interface_id"),
        fk_columns={
            "filter_wheel_seed_key": "filter_wheel",
            "interface_seed_key": "connection_interface",
        },
        is_junction=True,
        junction_parent="filter_wheel",
        junction_key_columns=("filter_wheel_id", "interface_id"),
    ),
    # ------------------------------------------------------------------
    # 22: oag — FKs: manufacturer, connector_size (imaging side + guide camera)
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="oag",
        csv_filename="oag.csv",
        seeded_fields=(
            "manufacturer_id",
            "imaging_side_connector_id",
            "guide_camera_connector_id",
            "model_name",
            "prism_size_mm",
            "back_focus_contribution_mm",
            "weight_g",
            "notes",
        ),
        fk_columns={
            "manufacturer_seed_key": "manufacturer",
            "imaging_side_connector_seed_key": "connector_size",
            "guide_camera_connector_seed_key": "connector_size",
        },
    ),
    # ------------------------------------------------------------------
    # 23: guide_scope — FKs: manufacturer, connector_size
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="guide_scope",
        csv_filename="guide_scope.csv",
        seeded_fields=(
            "manufacturer_id",
            "guide_camera_connector_id",
            "model_name",
            "aperture_mm",
            "focal_length_mm",
            "weight_g",
            "notes",
        ),
        fk_columns={
            "manufacturer_seed_key": "manufacturer",
            "guide_camera_connector_seed_key": "connector_size",
        },
    ),
    # ------------------------------------------------------------------
    # 24: computer — FKs: manufacturer, computer_type
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="computer",
        csv_filename="computer.csv",
        seeded_fields=(
            "manufacturer_id",
            "computer_type_id",
            "model_name",
            "notes",
        ),
        fk_columns={
            "manufacturer_seed_key": "manufacturer",
            "computer_type_seed_key": "computer_type",
        },
    ),
    # ------------------------------------------------------------------
    # 25: software — FK: manufacturer
    # ------------------------------------------------------------------
    SeedableTable(
        table_name="software",
        csv_filename="software.csv",
        seeded_fields=(
            "manufacturer_id",
            "name",
            "category",
            "website",
            "notes",
        ),
        fk_columns={
            "manufacturer_seed_key": "manufacturer",
        },
    ),
    # ------------------------------------------------------------------
    # 26-28: Alias tables
    #
    # Alias tables have a different structure from standard seeded tables:
    #   - No seed_key / seed_hash columns — identified by the alias text
    #     (UNIQUE constraint on alias).
    #   - No active column; have first_seen_at / last_seen_at instead.
    #   - The loader uses `alias` as the natural key for upserts.
    #   - source is included as a seeded field (value: 'seed').
    # ------------------------------------------------------------------
    # 26: camera_alias
    SeedableTable(
        table_name="camera_alias",
        csv_filename="camera_alias.csv",
        seeded_fields=("camera_id", "alias", "source", "confirmed"),
        fk_columns={
            "camera_seed_key": "camera",
        },
    ),
    # 27: telescope_alias
    SeedableTable(
        table_name="telescope_alias",
        csv_filename="telescope_alias.csv",
        seeded_fields=("telescope_id", "alias", "source", "confirmed"),
        fk_columns={
            "telescope_seed_key": "telescope",
        },
    ),
    # 28: filter_alias
    SeedableTable(
        table_name="filter_alias",
        csv_filename="filter_alias.csv",
        seeded_fields=("filter_id", "alias", "source", "confirmed"),
        fk_columns={
            "filter_seed_key": "filter",
        },
    ),
]

# ---------------------------------------------------------------------------
# Registry dict — table_name → SeedableTable, for O(1) lookups
# ---------------------------------------------------------------------------

REGISTRY: dict[str, SeedableTable] = {t.table_name: t for t in LOAD_ORDER}
