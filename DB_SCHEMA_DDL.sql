-- NightCrate version: 0.40.2
-- NightCrate Database Schema
-- SQLite DDL for the full current schema. Originally authored at v0.8.0;
-- extended through v0.15.0 (rig builder, My Equipment flag, location seeing,
-- location soft-delete, settings key-value schema, rig_summary ADC bit depth,
-- custom horizons, DSO catalog, DSO augmentation).
-- Incorporates revision spec: no custom_fields, seed tracking, alias tables,
-- closed-vocabulary CHECK constraints, updated_at triggers.
--
-- Infrastructure tables (settings, recent_file, aberration_analysis,
-- aberration_star, weather_cache) live in their own migrations; only the
-- weather_cache and location tables from those groups are mirrored here.

-- ============================================================
-- SEED LOADER META
-- ============================================================

CREATE TABLE IF NOT EXISTS seed_loader_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ============================================================
-- LOOKUP / REFERENCE TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS manufacturer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    website TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_manufacturer_seed_key
    ON manufacturer(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_manufacturer_updated_at
AFTER UPDATE ON manufacturer
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE manufacturer SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS optical_design (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_optical_design_seed_key
    ON optical_design(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_optical_design_updated_at
AFTER UPDATE ON optical_design
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE optical_design SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS mount_type (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mount_type_seed_key
    ON mount_type(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_mount_type_updated_at
AFTER UPDATE ON mount_type
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE mount_type SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS connection_interface (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL CHECK (category IN ('data', 'control', 'power', 'wireless')),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_connection_interface_seed_key
    ON connection_interface(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_connection_interface_updated_at
AFTER UPDATE ON connection_interface
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE connection_interface SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS connector_size (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    diameter_mm REAL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_connector_size_seed_key
    ON connector_size(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_connector_size_updated_at
AFTER UPDATE ON connector_size
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE connector_size SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS filter_size (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_filter_size_seed_key
    ON filter_size(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_filter_size_updated_at
AFTER UPDATE ON filter_size
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE filter_size SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS form_factor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_form_factor_seed_key
    ON form_factor(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_form_factor_updated_at
AFTER UPDATE ON form_factor
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE form_factor SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS filter_type (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_filter_type_seed_key
    ON filter_type(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_filter_type_updated_at
AFTER UPDATE ON filter_type
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE filter_type SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- filter_type rows are loaded by the seed loader from filter_type.csv

-- ============================================================
-- SENSOR
-- ============================================================

CREATE TABLE IF NOT EXISTS sensor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturer(id),
    model_name TEXT NOT NULL,
    sensor_type TEXT NOT NULL CHECK (sensor_type IN ('mono', 'color')),
    pixel_size_um REAL NOT NULL CHECK (pixel_size_um > 0),
    resolution_x INTEGER NOT NULL CHECK (resolution_x > 0),
    resolution_y INTEGER NOT NULL CHECK (resolution_y > 0),
    sensor_width_mm REAL,
    sensor_height_mm REAL,
    adc_bit_depth INTEGER,
    full_well_capacity_ke REAL,
    read_noise_e REAL,
    peak_qe_pct REAL,
    bayer_pattern TEXT CHECK (bayer_pattern IS NULL OR bayer_pattern IN ('RGGB', 'GRBG', 'GBRG', 'BGGR')),
    dual_gain INTEGER NOT NULL DEFAULT 0 CHECK (dual_gain IN (0, 1)),
    notes TEXT,
    source_url TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name),
    CHECK (
        (sensor_type = 'mono' AND bayer_pattern IS NULL)
        OR (sensor_type = 'color' AND bayer_pattern IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_sensor_manufacturer ON sensor(manufacturer_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sensor_seed_key
    ON sensor(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_sensor_updated_at
AFTER UPDATE ON sensor
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE sensor SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================
-- CAMERA
-- ============================================================

CREATE TABLE IF NOT EXISTS camera (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturer(id),
    sensor_id INTEGER NOT NULL REFERENCES sensor(id),
    guide_sensor_id INTEGER REFERENCES sensor(id),
    connector_size_id INTEGER REFERENCES connector_size(id),
    model_name TEXT NOT NULL,
    cooled INTEGER NOT NULL DEFAULT 0 CHECK (cooled IN (0, 1)),
    cooling_delta_c REAL,
    back_focus_mm REAL,
    weight_g REAL,
    tilt_adapter INTEGER NOT NULL DEFAULT 0 CHECK (tilt_adapter IN (0, 1)),
    has_usb_hub INTEGER NOT NULL DEFAULT 0 CHECK (has_usb_hub IN (0, 1)),
    usb_hub_interface_id INTEGER REFERENCES connection_interface(id),
    unity_gain INTEGER,
    effective_full_well_ke REAL,
    effective_read_noise_lcg_e REAL,
    effective_read_noise_hcg_e REAL,
    effective_peak_qe_pct REAL,
    hcg_threshold_gain INTEGER,
    notes TEXT,
    source_url TEXT,
    is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_camera_mine ON camera(is_mine) WHERE is_mine = 1;

CREATE INDEX IF NOT EXISTS idx_camera_manufacturer ON camera(manufacturer_id);
CREATE INDEX IF NOT EXISTS idx_camera_sensor ON camera(sensor_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_camera_seed_key
    ON camera(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_camera_updated_at
AFTER UPDATE ON camera
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE camera SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS camera_interface (
    camera_id INTEGER NOT NULL REFERENCES camera(id) ON DELETE CASCADE,
    interface_id INTEGER NOT NULL REFERENCES connection_interface(id),
    PRIMARY KEY (camera_id, interface_id)
);

-- ============================================================
-- TELESCOPE
-- ============================================================

CREATE TABLE IF NOT EXISTS telescope (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturer(id),
    optical_design_id INTEGER REFERENCES optical_design(id),
    model_name TEXT NOT NULL,
    aperture_mm REAL NOT NULL CHECK (aperture_mm > 0),
    image_circle_mm REAL,
    weight_kg REAL,
    obstruction_pct REAL,
    notes TEXT,
    source_url TEXT,
    is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_telescope_mine ON telescope(is_mine) WHERE is_mine = 1;

CREATE INDEX IF NOT EXISTS idx_telescope_manufacturer ON telescope(manufacturer_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_telescope_seed_key
    ON telescope(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_telescope_updated_at
AFTER UPDATE ON telescope
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE telescope SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS telescope_connector (
    telescope_id INTEGER NOT NULL REFERENCES telescope(id) ON DELETE CASCADE,
    connector_size_id INTEGER NOT NULL REFERENCES connector_size(id),
    PRIMARY KEY (telescope_id, connector_size_id)
);

CREATE TABLE IF NOT EXISTS telescope_configuration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telescope_id INTEGER NOT NULL REFERENCES telescope(id) ON DELETE CASCADE,
    config_name TEXT NOT NULL,
    accessory_name TEXT,
    reduction_factor REAL NOT NULL DEFAULT 1.0 CHECK (reduction_factor > 0),
    effective_focal_length_mm REAL NOT NULL CHECK (effective_focal_length_mm > 0),
    effective_focal_ratio REAL NOT NULL CHECK (effective_focal_ratio > 0),
    effective_image_circle_mm REAL,
    effective_back_focus_mm REAL,
    is_native INTEGER NOT NULL DEFAULT 0 CHECK (is_native IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (telescope_id, config_name)
);

CREATE INDEX IF NOT EXISTS idx_telescope_configuration_telescope
    ON telescope_configuration(telescope_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_telescope_configuration_one_native
    ON telescope_configuration(telescope_id) WHERE is_native = 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_telescope_configuration_seed_key
    ON telescope_configuration(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_telescope_configuration_updated_at
AFTER UPDATE ON telescope_configuration
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE telescope_configuration SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================
-- FILTER
-- ============================================================

CREATE TABLE IF NOT EXISTS filter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturer(id),
    filter_type_id INTEGER NOT NULL REFERENCES filter_type(id),
    model_name TEXT NOT NULL,
    peak_transmission_pct REAL,
    notes TEXT,
    source_url TEXT,
    is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_filter_mine ON filter(is_mine) WHERE is_mine = 1;

CREATE INDEX IF NOT EXISTS idx_filter_manufacturer ON filter(manufacturer_id);
CREATE INDEX IF NOT EXISTS idx_filter_type ON filter(filter_type_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_filter_seed_key
    ON filter(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_filter_updated_at
AFTER UPDATE ON filter
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE filter SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS filter_passband (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filter_id INTEGER NOT NULL REFERENCES filter(id) ON DELETE CASCADE,
    line_name TEXT NOT NULL CHECK (line_name IN (
        'Ha', 'Hb', 'Oiii', 'Sii', 'Nii', 'OI',
        'Lum', 'R', 'G', 'B', 'R+',
        'UVIR', 'LP', 'ND', 'other'
    )),
    central_wavelength_nm REAL NOT NULL CHECK (central_wavelength_nm > 0),
    bandwidth_nm REAL NOT NULL CHECK (bandwidth_nm > 0),
    peak_transmission_pct REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_filter_passband_filter ON filter_passband(filter_id);
CREATE INDEX IF NOT EXISTS idx_filter_passband_line ON filter_passband(line_name);

CREATE UNIQUE INDEX IF NOT EXISTS idx_filter_passband_seed_key
    ON filter_passband(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_filter_passband_updated_at
AFTER UPDATE ON filter_passband
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE filter_passband SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS filter_size_option (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filter_id INTEGER NOT NULL REFERENCES filter(id) ON DELETE CASCADE,
    filter_size_id INTEGER NOT NULL REFERENCES filter_size(id),
    mounted_thickness_mm REAL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (filter_id, filter_size_id)
);

CREATE INDEX IF NOT EXISTS idx_filter_size_option_filter ON filter_size_option(filter_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_filter_size_option_seed_key
    ON filter_size_option(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_filter_size_option_updated_at
AFTER UPDATE ON filter_size_option
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE filter_size_option SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================
-- MOUNT
-- ============================================================

CREATE TABLE IF NOT EXISTS mount (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturer(id),
    mount_type_id INTEGER REFERENCES mount_type(id),
    model_name TEXT NOT NULL,
    payload_capacity_kg REAL,
    mount_weight_kg REAL,
    counterweight_required INTEGER NOT NULL DEFAULT 0 CHECK (counterweight_required IN (0, 1)),
    goto_capable INTEGER NOT NULL DEFAULT 1 CHECK (goto_capable IN (0, 1)),
    periodic_error_arcsec REAL,
    drive_type TEXT,
    worm_period_seconds REAL,
    notes TEXT,
    source_url TEXT,
    is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_mount_mine ON mount(is_mine) WHERE is_mine = 1;

CREATE INDEX IF NOT EXISTS idx_mount_manufacturer ON mount(manufacturer_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mount_seed_key
    ON mount(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_mount_updated_at
AFTER UPDATE ON mount
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE mount SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS mount_interface (
    mount_id INTEGER NOT NULL REFERENCES mount(id) ON DELETE CASCADE,
    interface_id INTEGER NOT NULL REFERENCES connection_interface(id),
    PRIMARY KEY (mount_id, interface_id)
);

-- ============================================================
-- FOCUSER TYPE (lookup)
-- ============================================================

CREATE TABLE IF NOT EXISTS focuser_type (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_focuser_type_seed_key
    ON focuser_type(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_focuser_type_updated_at
AFTER UPDATE ON focuser_type
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE focuser_type SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================
-- FOCUSER
-- ============================================================

CREATE TABLE IF NOT EXISTS focuser (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturer(id),
    focuser_type_id INTEGER REFERENCES focuser_type(id),
    model_name TEXT NOT NULL,
    motorized INTEGER NOT NULL DEFAULT 1 CHECK (motorized IN (0, 1)),
    travel_range_mm REAL,
    step_size_um REAL,
    total_steps INTEGER,
    temperature_compensation INTEGER NOT NULL DEFAULT 0 CHECK (temperature_compensation IN (0, 1)),
    backlash_steps INTEGER,
    notes TEXT,
    source_url TEXT,
    is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_focuser_mine ON focuser(is_mine) WHERE is_mine = 1;

CREATE INDEX IF NOT EXISTS idx_focuser_manufacturer ON focuser(manufacturer_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_focuser_seed_key
    ON focuser(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_focuser_updated_at
AFTER UPDATE ON focuser
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE focuser SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS focuser_interface (
    focuser_id INTEGER NOT NULL REFERENCES focuser(id) ON DELETE CASCADE,
    interface_id INTEGER NOT NULL REFERENCES connection_interface(id),
    PRIMARY KEY (focuser_id, interface_id)
);

-- ============================================================
-- FILTER WHEEL
-- ============================================================

CREATE TABLE IF NOT EXISTS filter_wheel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturer(id),
    filter_size_id INTEGER REFERENCES filter_size(id),
    camera_side_connector_id INTEGER REFERENCES connector_size(id),
    telescope_side_connector_id INTEGER REFERENCES connector_size(id),
    model_name TEXT NOT NULL,
    num_positions INTEGER NOT NULL CHECK (num_positions > 0),
    back_focus_contribution_mm REAL,
    notes TEXT,
    source_url TEXT,
    is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_filter_wheel_mine ON filter_wheel(is_mine) WHERE is_mine = 1;

CREATE INDEX IF NOT EXISTS idx_filter_wheel_manufacturer ON filter_wheel(manufacturer_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_filter_wheel_seed_key
    ON filter_wheel(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_filter_wheel_updated_at
AFTER UPDATE ON filter_wheel
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE filter_wheel SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS filter_wheel_interface (
    filter_wheel_id INTEGER NOT NULL REFERENCES filter_wheel(id) ON DELETE CASCADE,
    interface_id INTEGER NOT NULL REFERENCES connection_interface(id),
    PRIMARY KEY (filter_wheel_id, interface_id)
);

-- ============================================================
-- GUIDING EQUIPMENT
-- ============================================================

CREATE TABLE IF NOT EXISTS oag (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturer(id),
    imaging_side_connector_id INTEGER REFERENCES connector_size(id),
    guide_camera_connector_id INTEGER REFERENCES connector_size(id),
    model_name TEXT NOT NULL,
    prism_size_mm REAL,
    back_focus_contribution_mm REAL,
    weight_g REAL,
    notes TEXT,
    source_url TEXT,
    is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_oag_mine ON oag(is_mine) WHERE is_mine = 1;

CREATE INDEX IF NOT EXISTS idx_oag_manufacturer ON oag(manufacturer_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_oag_seed_key
    ON oag(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_oag_updated_at
AFTER UPDATE ON oag
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE oag SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS guide_scope (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturer(id),
    guide_camera_connector_id INTEGER REFERENCES connector_size(id),
    model_name TEXT NOT NULL,
    aperture_mm REAL,
    focal_length_mm REAL,
    weight_g REAL,
    notes TEXT,
    source_url TEXT,
    is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_guide_scope_mine ON guide_scope(is_mine) WHERE is_mine = 1;

CREATE INDEX IF NOT EXISTS idx_guide_scope_manufacturer ON guide_scope(manufacturer_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_guide_scope_seed_key
    ON guide_scope(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_guide_scope_updated_at
AFTER UPDATE ON guide_scope
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE guide_scope SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================
-- COMPUTING AND SOFTWARE
-- ============================================================

CREATE TABLE IF NOT EXISTS computer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturer(id),
    form_factor_id INTEGER REFERENCES form_factor(id),
    model_name TEXT NOT NULL,
    notes TEXT,
    source_url TEXT,
    is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_computer_mine ON computer(is_mine) WHERE is_mine = 1;

CREATE INDEX IF NOT EXISTS idx_computer_manufacturer ON computer(manufacturer_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_computer_seed_key
    ON computer(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_computer_updated_at
AFTER UPDATE ON computer
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE computer SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS software (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturer(id),
    name TEXT NOT NULL,
    category TEXT CHECK (category IN (
        'capture', 'guiding', 'processing', 'planetarium',
        'plate_solving', 'utility', 'other'
    )),
    website TEXT,
    notes TEXT,
    is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, name)
);

CREATE INDEX IF NOT EXISTS idx_software_mine ON software(is_mine) WHERE is_mine = 1;

CREATE INDEX IF NOT EXISTS idx_software_manufacturer ON software(manufacturer_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_software_seed_key
    ON software(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_software_updated_at
AFTER UPDATE ON software
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE software SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================
-- FITS INGEST ALIAS TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS camera_alias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL REFERENCES camera(id) ON DELETE CASCADE,
    alias TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL CHECK (source IN ('seed', 'nina', 'asiair', 'user', 'manual')),
    confirmed INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_camera_alias_camera ON camera_alias(camera_id);

CREATE TABLE IF NOT EXISTS telescope_alias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telescope_id INTEGER NOT NULL REFERENCES telescope(id) ON DELETE CASCADE,
    alias TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL CHECK (source IN ('seed', 'nina', 'asiair', 'user', 'manual')),
    confirmed INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_telescope_alias_telescope ON telescope_alias(telescope_id);

CREATE TABLE IF NOT EXISTS filter_alias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filter_id INTEGER NOT NULL REFERENCES filter(id) ON DELETE CASCADE,
    alias TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL CHECK (source IN ('seed', 'nina', 'asiair', 'user', 'manual')),
    confirmed INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_filter_alias_filter ON filter_alias(filter_id);

CREATE TABLE IF NOT EXISTS unresolved_equipment_observation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_kind TEXT NOT NULL CHECK (equipment_kind IN ('camera', 'telescope', 'filter')),
    normalized_alias TEXT NOT NULL,
    original_observation TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    seen_count INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL CHECK (source IN ('nina', 'asiair', 'user', 'manual')),
    resolved_to_equipment_id INTEGER,
    resolved_at TEXT,
    UNIQUE (equipment_kind, normalized_alias)
);

CREATE INDEX IF NOT EXISTS idx_unresolved_equipment_observation_kind
    ON unresolved_equipment_observation(equipment_kind, resolved_at);

-- ============================================================
-- VIEWS
-- ============================================================

CREATE VIEW IF NOT EXISTS filter_summary AS
SELECT
    f.id AS filter_id,
    f.model_name,
    f.manufacturer_id,
    f.filter_type_id,
    ft.name AS filter_type_name,
    COUNT(fp.id) AS passband_count,
    MIN(fp.central_wavelength_nm) AS min_wavelength_nm,
    MAX(fp.central_wavelength_nm) AS max_wavelength_nm,
    MIN(fp.bandwidth_nm) AS min_bandwidth_nm,
    MAX(fp.bandwidth_nm) AS max_bandwidth_nm,
    GROUP_CONCAT(fp.line_name, '+') AS passband_lines
FROM filter f
JOIN filter_type ft ON ft.id = f.filter_type_id
LEFT JOIN filter_passband fp ON fp.filter_id = f.id
WHERE f.active = 1
GROUP BY f.id;

-- ============================================================
-- LOCATION (migration 0007)
-- ============================================================

CREATE TABLE IF NOT EXISTS location (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    elevation_m REAL,
    timezone TEXT NOT NULL,
    geo_timezone TEXT,
    bortle_class INTEGER CHECK (bortle_class BETWEEN 1 AND 9),
    sqm_reading REAL CHECK (sqm_reading BETWEEN 10 AND 25),
    typical_seeing_low_arcsec REAL CHECK (typical_seeing_low_arcsec > 0),
    typical_seeing_high_arcsec REAL CHECK (typical_seeing_high_arcsec > 0),
    city TEXT,
    state_province TEXT,
    country TEXT,
    postal_code TEXT,
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    -- Soft-delete flag (migration 0012). List endpoints hide active=0 rows
    -- unless ?include_retired=true; restore endpoint flips back to 1.
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_location_active ON location(active);

CREATE TRIGGER IF NOT EXISTS trg_location_updated_at
AFTER UPDATE ON location
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE location SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ─── Weather Cache ─────────────────────────────────────────────────────────

-- Cache for Open-Meteo API responses (weather forecast, ECMWF PWV, air quality AOD).
-- One row per (location, data source) combination. TTL-based cleanup on startup.

CREATE TABLE IF NOT EXISTS weather_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES location(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (source IN ('forecast', 'archive', 'openmeteo_aq', 'ecmwf_pwv')),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    response_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(location_id, source, start_date, end_date)
);

-- ============================================================
-- RIGS (v0.12.0)
-- ============================================================

-- A rig is a named user-composed imaging template: one telescope configuration,
-- one camera, and optional slots for mount / focuser / filter wheel / filters /
-- guide scope / OAG / guide camera / computer / software. Powers the optical
-- calculators (image scale, FOV, sampling assessment, guide suitability,
-- guiding tolerance).

CREATE TABLE IF NOT EXISTS rig (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    telescope_configuration_id INTEGER NOT NULL
        REFERENCES telescope_configuration(id),
    camera_id INTEGER NOT NULL REFERENCES camera(id),
    filter_wheel_id INTEGER REFERENCES filter_wheel(id),
    single_filter_id INTEGER REFERENCES filter(id),
    mount_id INTEGER REFERENCES mount(id),
    focuser_id INTEGER REFERENCES focuser(id),
    oag_id INTEGER REFERENCES oag(id),
    guide_scope_id INTEGER REFERENCES guide_scope(id),
    guide_camera_id INTEGER REFERENCES camera(id),
    computer_id INTEGER REFERENCES computer(id),
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_rig_active ON rig(active);
CREATE INDEX IF NOT EXISTS idx_rig_default ON rig(is_default) WHERE is_default = 1;

CREATE TRIGGER IF NOT EXISTS trg_rig_updated_at
AFTER UPDATE ON rig
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE rig SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Filter wheel slot assignments for a rig. slot_number is 1-based and unique
-- within a rig. Validated against filter_wheel.num_positions at the API layer.
CREATE TABLE IF NOT EXISTS rig_filter_slot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rig_id INTEGER NOT NULL REFERENCES rig(id) ON DELETE CASCADE,
    slot_number INTEGER NOT NULL CHECK (slot_number >= 1),
    filter_id INTEGER NOT NULL REFERENCES filter(id),
    UNIQUE (rig_id, slot_number),
    UNIQUE (rig_id, filter_id)
);

CREATE INDEX IF NOT EXISTS idx_rig_filter_slot_rig ON rig_filter_slot(rig_id);

-- Junction table: multiple software packages per rig (e.g. NINA + PHD2 + ASIAIR).
CREATE TABLE IF NOT EXISTS rig_software (
    rig_id INTEGER NOT NULL REFERENCES rig(id) ON DELETE CASCADE,
    software_id INTEGER NOT NULL REFERENCES software(id),
    PRIMARY KEY (rig_id, software_id)
);

-- Convenience view resolving equipment names + headline specs for rig listing.
-- Includes guide camera sensor data for guide calculator computations,
-- telescope_id for the Equipment tab's detail view, and sensor_adc_bit_depth
-- (from the imaging camera's sensor) for the File Size calculator's
-- auto-populate-from-rig flow.
CREATE VIEW IF NOT EXISTS rig_summary AS
SELECT
    r.id,
    r.name,
    r.description,
    r.is_default,
    r.active,
    r.notes,
    r.created_at,
    r.updated_at,
    -- OTA
    r.telescope_configuration_id,
    t.id AS telescope_id,
    t.model_name AS telescope_name,
    tc.config_name AS telescope_config_name,
    tc.effective_focal_length_mm,
    tc.effective_focal_ratio,
    tc.effective_image_circle_mm,
    t.aperture_mm,
    -- Camera
    r.camera_id,
    c.model_name AS camera_name,
    s.pixel_size_um,
    s.resolution_x AS sensor_resolution_x,
    s.resolution_y AS sensor_resolution_y,
    s.sensor_width_mm,
    s.sensor_height_mm,
    s.sensor_type,
    s.adc_bit_depth AS sensor_adc_bit_depth,
    -- Mount
    r.mount_id,
    m.model_name AS mount_name,
    m.drive_type AS mount_drive_type,
    m.worm_period_seconds AS mount_worm_period_seconds,
    -- Filter wheel
    r.filter_wheel_id,
    fw.model_name AS filter_wheel_name,
    fw.num_positions AS filter_wheel_positions,
    -- Focuser
    r.focuser_id,
    foc.model_name AS focuser_name,
    -- Guide
    r.guide_camera_id,
    gc.model_name AS guide_camera_name,
    r.guide_scope_id,
    gs.model_name AS guide_scope_name,
    gs.focal_length_mm AS guide_scope_focal_length_mm,
    r.oag_id,
    o.model_name AS oag_name,
    gs2.pixel_size_um AS guide_pixel_size_um,
    gs2.resolution_x AS guide_resolution_x,
    gs2.resolution_y AS guide_resolution_y,
    -- Peripherals
    r.computer_id,
    comp.model_name AS computer_name,
    -- Single filter
    r.single_filter_id,
    sf.model_name AS single_filter_name
FROM rig r
JOIN telescope_configuration tc ON tc.id = r.telescope_configuration_id
JOIN telescope t ON t.id = tc.telescope_id
JOIN camera c ON c.id = r.camera_id
JOIN sensor s ON s.id = c.sensor_id
LEFT JOIN mount m ON m.id = r.mount_id
LEFT JOIN filter_wheel fw ON fw.id = r.filter_wheel_id
LEFT JOIN focuser foc ON foc.id = r.focuser_id
LEFT JOIN camera gc ON gc.id = r.guide_camera_id
LEFT JOIN sensor gs2 ON gs2.id = gc.sensor_id
LEFT JOIN guide_scope gs ON gs.id = r.guide_scope_id
LEFT JOIN oag o ON o.id = r.oag_id
LEFT JOIN computer comp ON comp.id = r.computer_id
LEFT JOIN filter sf ON sf.id = r.single_filter_id;


-- ── Horizons (multi per location, migrations 0014 + 0021) ──────────────────
-- Each location owns ≥1 horizon: at most one custom polyline ('custom' with
-- points in location_horizon_point), plus any number of named artificial
-- flat-altitude rows ('artificial' with flat_altitude_deg). Partial unique
-- indexes enforce exactly-one-default per location AND at-most-one-custom
-- per location. Migration 0021 reshaped the original 1:1 shape (created
-- in 0014) to 1:N and backfilled a '0° flat' artificial default for every
-- location that had no horizon. Points cascade-delete with the horizon.

CREATE TABLE location_horizon (
    id                  INTEGER PRIMARY KEY,
    location_id         INTEGER NOT NULL REFERENCES location(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    type                TEXT NOT NULL CHECK (type IN ('custom', 'artificial')),
    flat_altitude_deg   REAL,
    source              TEXT CHECK (source IS NULL OR source IN ('imported', 'drawn')),
    source_filename     TEXT,
    notes               TEXT,
    is_default          INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    created_at          TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at          TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    CHECK (
        (type = 'custom' AND flat_altitude_deg IS NULL) OR
        (type = 'artificial' AND flat_altitude_deg >= -5 AND flat_altitude_deg <= 90 AND source IS NULL)
    ),
    UNIQUE (location_id, name)
);

CREATE UNIQUE INDEX idx_location_horizon_default
    ON location_horizon (location_id) WHERE is_default = 1;

CREATE UNIQUE INDEX idx_location_horizon_one_custom
    ON location_horizon (location_id) WHERE type = 'custom';

CREATE TABLE location_horizon_point (
    horizon_id      INTEGER NOT NULL REFERENCES location_horizon(id) ON DELETE CASCADE,
    azimuth_deg     REAL NOT NULL CHECK (azimuth_deg >= 0 AND azimuth_deg < 360),
    altitude_deg    REAL NOT NULL CHECK (altitude_deg >= -5 AND altitude_deg <= 90),
    PRIMARY KEY (horizon_id, azimuth_deg)
);

CREATE INDEX idx_location_horizon_point_azimuth
    ON location_horizon_point (horizon_id, azimuth_deg);


-- ── DSO Catalog (migration 0015) ───────────────────────────────────────────
-- Deep-sky object catalog (v0.14.0 MVP). Canonical `dso` row per physical
-- object; `dso_designation` attaches catalog-specific identifiers to it
-- (same shape as camera ↔ camera_alias). `dso_catalog_source` registers
-- which file each row came from and stores the file's sha256 for
-- hash-based change detection on reload.
--
-- All three tables are loader-populated (no INSERTs in this migration).
-- CHECK vocabularies are deliberately closed: unknown `obj_type` values
-- fall through to `'Other'` + preserve the original in `raw_obj_type`;
-- unknown catalog prefixes are dropped from designations but kept on
-- `dso.raw_other_id` for future re-parsing.

CREATE TABLE dso_catalog_source (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     TEXT NOT NULL UNIQUE,
    category      TEXT NOT NULL CHECK (category IN ('openngc', 'vizier', 'nightcrate')),
    display_name  TEXT NOT NULL,
    version       TEXT,
    source_url    TEXT,
    file_path     TEXT NOT NULL,
    file_hash     TEXT NOT NULL,
    license       TEXT,
    attribution   TEXT,
    loaded_at     TEXT NOT NULL DEFAULT (datetime('now')),
    row_count     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE dso (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,

    primary_designation     TEXT NOT NULL,

    obj_type                TEXT NOT NULL CHECK (obj_type IN (
        'G', 'GPair', 'GTrpl', 'GGroup',
        'HII', 'EmN', 'RfN', 'PN', 'OCl', 'GCl', 'Cl+N', 'SNR', 'DrkN', 'Neb',
        '*Ass', 'Nova', '*', '**', 'Other'
    )),
    raw_obj_type            TEXT,

    ra_deg                  REAL,
    dec_deg                 REAL,
    constellation           TEXT,

    maj_axis_arcmin         REAL,
    min_axis_arcmin         REAL,
    position_angle_deg      REAL,

    mag_b                   REAL,
    mag_v                   REAL,
    mag_j                   REAL,
    mag_h                   REAL,
    mag_k                   REAL,
    surface_brightness      REAL,

    hubble_type             TEXT,
    pm_ra                   REAL,
    pm_dec                  REAL,
    redshift                REAL,
    radial_velocity         REAL,

    cstar_mag_u             REAL,
    cstar_mag_b             REAL,
    cstar_mag_v             REAL,
    cstar_id                TEXT,

    common_name             TEXT,
    ned_notes               TEXT,
    openngc_notes           TEXT,
    raw_other_id            TEXT,

    -- Editorial fields reserved for v0.15+ augmentation CSV; unused now.
    popularity_rank         INTEGER,
    difficulty              TEXT CHECK (
        difficulty IS NULL
        OR difficulty IN ('easy', 'moderate', 'challenging', 'extreme')
    ),
    recommended_filter_id   INTEGER REFERENCES filter(id),

    source_catalog_id       INTEGER NOT NULL REFERENCES dso_catalog_source(id),
    source_row_hash         TEXT NOT NULL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now')),
    active                  INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE INDEX idx_dso_obj_type            ON dso(obj_type);
CREATE INDEX idx_dso_constellation       ON dso(constellation);
CREATE INDEX idx_dso_primary_designation ON dso(primary_designation);
CREATE INDEX idx_dso_source_catalog      ON dso(source_catalog_id);

CREATE TRIGGER trg_dso_updated_at
AFTER UPDATE ON dso
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE dso SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE dso_designation (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dso_id        INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    catalog       TEXT NOT NULL CHECK (catalog IN (
        'ngc', 'ic', 'messier', 'caldwell', 'ugc', 'pgc', 'mcg', 'eso',
        'arp', 'hickson', 'sharpless2', 'barnard', 'ldn', 'lbn', 'vdb',
        'cederblad', 'pk', 'rcw', 'gum', 'mrk', 'terzan', 'pal', 'mel',
        'cr', 'stock', 'ruprecht', 'abell', 'dolidze', 'dwb'
    )),
    identifier    TEXT NOT NULL,
    display_form  TEXT NOT NULL,
    search_key    TEXT NOT NULL,
    is_primary    INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    UNIQUE (catalog, identifier)
);

CREATE INDEX idx_dso_designation_dso         ON dso_designation(dso_id);
CREATE INDEX idx_dso_designation_search_key  ON dso_designation(search_key);
CREATE UNIQUE INDEX idx_dso_designation_primary_per_dso
    ON dso_designation(dso_id) WHERE is_primary = 1;



-- ── DSO Augmentation (migration 0016) ──────────────────────────────────────
-- distance_pc / distance_method carry galaxy distances from three sources
-- layered by precedence: curated (NightCrate editorial) > 50mgc (Ohlson+
-- 2024) > redshift (post-load Hubble-law backfill). common_name_augmented
-- and surface_brightness_augmented flag rows with editorial overrides so
-- the detail panel can show a subtle "augmented" indicator. See
-- docs/dso-catalog-architecture.md for precedence rules.

ALTER TABLE dso ADD COLUMN distance_pc REAL;
ALTER TABLE dso ADD COLUMN distance_method TEXT
    CHECK (distance_method IS NULL OR distance_method IN ('50mgc', 'curated', 'redshift'));
ALTER TABLE dso ADD COLUMN surface_brightness_augmented INTEGER NOT NULL DEFAULT 0
    CHECK (surface_brightness_augmented IN (0, 1));
ALTER TABLE dso ADD COLUMN common_name_augmented INTEGER NOT NULL DEFAULT 0
    CHECK (common_name_augmented IN (0, 1));


-- ── Target Planner thumbnail cache (migration 0017) ────────────────────────
-- Metadata-only table (files live on disk under APP_DIR/thumbnails/). LRU
-- eviction is driven by last_access_at; fetch_error rows record failed
-- attempts so repeated polls don't re-fire a broken CDS fetch.

-- v0.17.0 / migration 0018 widens the variant CHECK to include
-- 'rig_framed' + 'fov_simulator' and adds nullable FOV descriptor
-- columns (deg × 1000, as ints, to avoid float-equality pitfalls in
-- the unique index). The unique index uses COALESCE so rig-independent
-- entries (NULL FOV) don't collide with rig-dependent ones at the same
-- dso_id.
CREATE TABLE IF NOT EXISTS thumbnail_cache (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    dso_id               INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    variant              TEXT    NOT NULL CHECK (variant IN (
        'list', 'detail', 'rig_framed', 'fov_simulator'
    )),
    width                INTEGER NOT NULL,
    height               INTEGER NOT NULL,
    fov_major_deg_x1000  INTEGER,
    fov_minor_deg_x1000  INTEGER,
    center_ra_deg_x1000  INTEGER,
    center_dec_deg_x1000 INTEGER,
    file_path            TEXT    NOT NULL UNIQUE,
    source               TEXT    NOT NULL CHECK (source IN (
        'dss2_color', 'dss2_red', 'dss2_blue', 'placeholder'
    )),
    bytes                INTEGER NOT NULL,
    fetched_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    last_access_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    fetch_error          TEXT
);

-- Unique index wraps FOV columns in COALESCE(-1) and centre-coord
-- columns in COALESCE(-999999). Distinct sentinels keep a legitimate
-- 0.0 RA (celestial equator) from colliding with NULL, and rig-
-- independent entries (NULL FOV) from colliding with rig-dependent
-- ones at the same dso_id.
CREATE UNIQUE INDEX IF NOT EXISTS idx_thumbnail_cache_unique
    ON thumbnail_cache(
        dso_id,
        variant,
        width,
        height,
        COALESCE(fov_major_deg_x1000, -1),
        COALESCE(fov_minor_deg_x1000, -1),
        COALESCE(center_ra_deg_x1000, -999999),
        COALESCE(center_dec_deg_x1000, -999999)
    );

CREATE INDEX IF NOT EXISTS idx_thumbnail_cache_last_access
    ON thumbnail_cache(last_access_at);
CREATE INDEX IF NOT EXISTS idx_thumbnail_cache_dso
    ON thumbnail_cache(dso_id);

CREATE INDEX IF NOT EXISTS idx_dso_distance_method
    ON dso(distance_method)
    WHERE distance_method IS NOT NULL;

-- ─── v0.18.0 — Target Planner Pass C sky-tile cache (migration 0020) ─────────
--
-- DSO-agnostic cell cache for the FOV Simulator and DSO-catalog auto-
-- zoom previews. Cells are keyed by sky region (HEALPix NSIDE=8, 768
-- regions) + tier + cell offset — no FK to dso. Two DSOs whose
-- composites overlap in the same region share every cell in the
-- overlap. See ``services/sky_tiles.py`` for the tier → cell-size
-- mapping.

CREATE TABLE IF NOT EXISTS sky_tile_cache (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    hips_survey          TEXT    NOT NULL,
    healpix_nside        INTEGER NOT NULL,
    healpix_ipix         INTEGER NOT NULL,
    tier                 TEXT    NOT NULL CHECK (tier IN ('narrow', 'med', 'wide')),
    cell_size_deg_x100   INTEGER NOT NULL,
    cell_width_px        INTEGER NOT NULL,
    cell_height_px       INTEGER NOT NULL,
    cell_i               INTEGER NOT NULL,
    cell_j               INTEGER NOT NULL,
    file_path            TEXT    NOT NULL UNIQUE,
    source               TEXT    NOT NULL CHECK (source IN (
        'dss2_color', 'dss2_red', 'dss2_blue', 'placeholder'
    )),
    bytes                INTEGER NOT NULL,
    fetched_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    last_access_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    fetch_error          TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sky_tile_cache_unique
    ON sky_tile_cache(
        hips_survey,
        healpix_nside,
        healpix_ipix,
        tier,
        cell_size_deg_x100,
        cell_width_px,
        cell_height_px,
        cell_i,
        cell_j
    );

CREATE INDEX IF NOT EXISTS idx_sky_tile_cache_last_access
    ON sky_tile_cache(last_access_at);
CREATE INDEX IF NOT EXISTS idx_sky_tile_cache_region
    ON sky_tile_cache(healpix_nside, healpix_ipix);


-- ── DSO external refs (migrations 0022 + 0023) ────────────────────────────
-- Associates Wikidata QIDs, Wikipedia article URLs, SIMBAD cross-
-- references, and NED galaxy-DB links with canonical DSO rows. Populated
-- by two loaders — `catalog_loader/wikidata_loader.py` (bulk SPARQL fetch
-- + synthesised SIMBAD/NED URLs) and `catalog_loader/external_refs_loader.py`
-- (editorial CSV overrides). One row per (dso_id, provider, language);
-- `language` is NULL for language-agnostic providers (wikidata / simbad
-- / ned) and required for wikipedia.
--
-- Migration 0022 introduces the table with provider CHECK = {wikidata,
-- wikipedia} and also widens `dso_catalog_source.category` to include
-- `'wikidata'`.
-- Migration 0023 widens the provider CHECK to {wikidata, wikipedia,
-- simbad, ned} via the SQLite table-rewrite pattern (PRAGMA
-- legacy_alter_table = ON) so existing rows survive and indexes +
-- trigger + partial unique index get recreated on the new table.
CREATE TABLE dso_external_ref (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    dso_id            INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    provider          TEXT NOT NULL CHECK (provider IN ('wikidata', 'wikipedia', 'simbad', 'ned')),
    language          TEXT,
    identifier        TEXT NOT NULL,
    url               TEXT,
    label             TEXT,
    source_catalog_id INTEGER REFERENCES dso_catalog_source(id),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (dso_id, provider, language)
);

CREATE INDEX idx_dso_external_ref_dso
    ON dso_external_ref(dso_id);
CREATE INDEX idx_dso_external_ref_provider
    ON dso_external_ref(provider, identifier);
-- UNIQUE(dso_id, provider, language) above doesn't enforce uniqueness
-- when language IS NULL (SQLite unique-index semantics treat NULL as
-- always distinct). Partial index covers the language-agnostic providers
-- (wikidata today, future NED/SIMBAD/etc.).
CREATE UNIQUE INDEX idx_dso_external_ref_langless_unique
    ON dso_external_ref(dso_id, provider)
    WHERE language IS NULL;
-- No global uniqueness on (provider, language, identifier) — a single
-- external resource may legitimately cover multiple NightCrate DSOs
-- (Wikipedia's Stephan's Quintet article = 5 galaxies; Wikidata's
-- Crab Nebula entity = NGC 1952 + Sh2-244; etc.). The loader duplicates
-- the ref onto every matching DSO so users viewing any of them see the
-- chip.

-- ============================================================
-- Projects (v0.35.0)
-- ============================================================

CREATE TABLE project (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT,
    notes       TEXT,
    status      TEXT    NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'complete', 'abandoned')),
    active      INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_project_active ON project(active);

CREATE TRIGGER trg_project_updated_at
AFTER UPDATE ON project
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE project_image (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    file_path     TEXT    NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_main       INTEGER NOT NULL DEFAULT 0 CHECK (is_main IN (0, 1)),
    notes         TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_project_image_project
    ON project_image(project_id);
-- At most one main image per project.
CREATE UNIQUE INDEX idx_project_image_main
    ON project_image(project_id) WHERE is_main = 1;

CREATE TRIGGER trg_project_image_updated_at
AFTER UPDATE ON project_image
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project_image SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE project_thumbnail (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    size            TEXT    NOT NULL CHECK (size IN ('small', 'medium', 'large')),
    source_image_id INTEGER REFERENCES project_image(id) ON DELETE SET NULL,
    crop_x          REAL    NOT NULL DEFAULT 0,
    crop_y          REAL    NOT NULL DEFAULT 0,
    crop_w          REAL    NOT NULL DEFAULT 1,
    crop_h          REAL    NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, size)
);

CREATE INDEX idx_project_thumbnail_project
    ON project_thumbnail(project_id);

CREATE TRIGGER trg_project_thumbnail_updated_at
AFTER UPDATE ON project_thumbnail
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project_thumbnail SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Project plate solve + identified DSO objects (v0.37.0, migration 0034).
-- One solve per project of a standalone (non-gallery) image; deleting the
-- solve cascades its identified objects.
CREATE TABLE project_solve (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id         INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    image_path         TEXT    NOT NULL,
    image_width        INTEGER NOT NULL,
    image_height       INTEGER NOT NULL,
    center_ra_deg      REAL    NOT NULL,   -- ASTAP CRVAL = field centre
    center_dec_deg     REAL    NOT NULL,
    ra_hms             TEXT,
    dec_dms            TEXT,
    pixel_scale_arcsec REAL,
    rotation_deg       REAL,
    fov_width_arcmin   REAL,
    fov_height_arcmin  REAL,
    cd1_1              REAL    NOT NULL,
    cd1_2              REAL    NOT NULL,
    cd2_1              REAL    NOT NULL,
    cd2_2              REAL    NOT NULL,
    crpix1             REAL    NOT NULL,
    crpix2             REAL    NOT NULL,
    solved_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id)
);

CREATE INDEX idx_project_solve_project ON project_solve(project_id);

CREATE TABLE project_dso (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    solve_id   INTEGER NOT NULL REFERENCES project_solve(id) ON DELETE CASCADE,
    dso_id     INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    is_main    INTEGER NOT NULL DEFAULT 0 CHECK (is_main IN (0, 1)),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (solve_id, dso_id)
);

CREATE INDEX idx_project_dso_solve ON project_dso(solve_id);
CREATE INDEX idx_project_dso_dso ON project_dso(dso_id);

-- v0.38.0: project metadata + manual imaging sessions ------------------------

ALTER TABLE project ADD COLUMN location_id INTEGER REFERENCES location(id);

CREATE TABLE project_rig (
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    rig_id     INTEGER NOT NULL REFERENCES rig(id),
    PRIMARY KEY (project_id, rig_id)
);
CREATE INDEX idx_project_rig_project ON project_rig(project_id);
CREATE INDEX idx_project_rig_rig ON project_rig(rig_id);

-- Manual capture batch: N identical light subs of one filter. The v0.39.0
-- ingest will also write to this table (source = 'auto') with user override.
CREATE TABLE project_session (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    rig_id           INTEGER REFERENCES rig(id),
    filter_id        INTEGER REFERENCES filter(id),
    line_name        TEXT CHECK (line_name IS NULL OR line_name IN (
                         'Ha', 'Hb', 'Oiii', 'Sii', 'Nii', 'OI',
                         'Lum', 'R', 'G', 'B', 'R+',
                         'UVIR', 'LP', 'ND', 'other'
                     )),
    exposure_seconds REAL    NOT NULL CHECK (exposure_seconds > 0),
    gain             INTEGER CHECK (gain IS NULL OR gain >= 0),
    num_subs         INTEGER NOT NULL CHECK (num_subs > 0),
    binning          INTEGER CHECK (binning IS NULL OR binning >= 1),
    session_date     TEXT,    -- ISO date or full ISO datetime; NULL when unknown
    notes            TEXT,
    source           TEXT    NOT NULL DEFAULT 'manual'
                         CHECK (source IN ('manual', 'auto')),
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    CHECK (filter_id IS NOT NULL OR line_name IS NOT NULL)
);
CREATE INDEX idx_project_session_project ON project_session(project_id);

CREATE TRIGGER trg_project_session_updated_at
AFTER UPDATE ON project_session
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project_session SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Per-filter integration goals.
CREATE TABLE project_filter_goal (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    line_name    TEXT    NOT NULL CHECK (line_name IN (
                     'Ha', 'Hb', 'Oiii', 'Sii', 'Nii', 'OI',
                     'Lum', 'R', 'G', 'B', 'R+',
                     'UVIR', 'LP', 'ND', 'other'
                 )),
    goal_minutes REAL    NOT NULL CHECK (goal_minutes > 0),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, line_name)
);
CREATE INDEX idx_project_filter_goal_project ON project_filter_goal(project_id);

CREATE TRIGGER trg_project_filter_goal_updated_at
AFTER UPDATE ON project_filter_goal
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project_filter_goal SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Persistent project ↔ DSO link (migration 0036). Single source of truth for
-- "main targets" — solve auto-flag and manual Overview "+" both write here,
-- and rows survive solve deletion (FK cascades on project, not solve).
CREATE TABLE project_target (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    dso_id     INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, dso_id)
);
CREATE INDEX idx_project_target_project ON project_target(project_id);
CREATE INDEX idx_project_target_dso ON project_target(dso_id);

-- ============================================================
-- Imaging Core (v0.40.0, migration 0037)
-- ============================================================
-- Sessions, sub frames, processed images, file locations, ingestion provenance,
-- project source folders, plus the calibration-matching and integration VIEWS.
-- The guiding / session-event / session-log / autofocus tables are created EMPTY
-- here so their forward FKs resolve cleanly; they are populated in later versions
-- (v0.43/0.44). `session` is the AUTO/ingest rig-night grouping of sub frames and
-- is distinct from `project_session` (manual capture batch, migration 0035).

-- Ingestion provenance (§11).
CREATE TABLE ingestion_run (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id        INTEGER REFERENCES project(id) ON DELETE CASCADE,
    source_path       TEXT    NOT NULL,
    mode              TEXT    NOT NULL DEFAULT 'catalog_in_place'
                          CHECK (mode IN ('catalog_in_place', 'copy_and_organize', 'reparse')),
    status            TEXT    NOT NULL DEFAULT 'running'
                          CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    files_scanned     INTEGER NOT NULL DEFAULT 0,
    subs_inserted     INTEGER NOT NULL DEFAULT 0,
    subs_updated      INTEGER NOT NULL DEFAULT 0,
    subs_skipped      INTEGER NOT NULL DEFAULT 0,
    errors_count      INTEGER NOT NULL DEFAULT 0,
    errors_json       TEXT,
    started_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at       TEXT
);
CREATE INDEX idx_ingestion_run_project ON ingestion_run(project_id);

-- Sessions (§5) — auto/ingest rig-night grouping of sub frames.
CREATE TABLE session (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER REFERENCES project(id) ON DELETE CASCADE,
    rig_id           INTEGER REFERENCES rig(id),
    start_utc        TEXT    NOT NULL,
    end_utc          TEXT,
    site_name        TEXT,
    latitude         REAL    CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    longitude        REAL    CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180),
    elevation_m      REAL,
    bortle_class     INTEGER CHECK (bortle_class IS NULL OR bortle_class BETWEEN 1 AND 9),
    conditions_notes TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_session_project ON session(project_id);
CREATE INDEX idx_session_rig ON session(rig_id);
CREATE INDEX idx_session_start ON session(start_utc);

-- Processed images (§2.9 promoted to first-class) — stacks / masters / finals.
CREATE TABLE processed_image (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Ownership (migration 0040): each project owns its own row for a file.
    project_id       INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    content_hash     TEXT    NOT NULL,
    image_kind       TEXT    NOT NULL DEFAULT 'master'
                         CHECK (image_kind IN ('master', 'stack', 'processed', 'other')),
    frame_type       TEXT    CHECK (frame_type IS NULL OR frame_type IN
                         ('light', 'dark', 'flat', 'bias', 'dark_flat', 'unknown')),
    filter_id        INTEGER REFERENCES filter(id),
    line_name        TEXT    CHECK (line_name IS NULL OR line_name IN (
                         'Ha', 'Hb', 'Oiii', 'Sii', 'Nii', 'OI',
                         'Lum', 'R', 'G', 'B', 'R+',
                         'UVIR', 'LP', 'ND', 'other'
                     )),
    camera_id        INTEGER REFERENCES camera(id),
    telescope_id     INTEGER REFERENCES telescope(id),
    ncombine         INTEGER,
    total_exposure_seconds REAL,  -- migration 0039: integration time for masters
    date_obs_utc     TEXT,
    image_width      INTEGER,
    image_height     INTEGER,
    fits_header_json TEXT,
    ingestion_run_id INTEGER REFERENCES ingestion_run(id) ON DELETE SET NULL,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, content_hash)  -- migration 0040: per-project identity
);
CREATE INDEX idx_processed_image_project ON processed_image(project_id);
CREATE INDEX idx_processed_image_filter ON processed_image(filter_id);

-- Sub frames (§6) — the core atom; lights + darks + flats + bias share this table.
CREATE TABLE sub_frame (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Ownership (migration 0040): each project owns its own row for a file.
    project_id               INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,

    -- Identity (§2.8): SHA-256 of file contents; re-ingest is idempotent per project.
    content_hash             TEXT    NOT NULL,

    -- Grouping (all nullable; a sub can ingest with partial/no context).
    session_id               INTEGER REFERENCES session(id) ON DELETE SET NULL,
    rig_id                   INTEGER REFERENCES rig(id),
    project_target_id        INTEGER REFERENCES project_target(id) ON DELETE SET NULL,
    ingestion_run_id         INTEGER REFERENCES ingestion_run(id) ON DELETE SET NULL,

    -- Classification.
    frame_type               TEXT    NOT NULL DEFAULT 'unknown'
                                 CHECK (frame_type IN
                                     ('light', 'dark', 'flat', 'bias', 'dark_flat', 'unknown')),
    accepted                 INTEGER NOT NULL DEFAULT 1 CHECK (accepted IN (0, 1)),
    rejection_reason         TEXT,
    rejection_source         TEXT    CHECK (rejection_source IS NULL OR
                                     rejection_source IN ('user', 'automated', 'ingest')),

    -- Equipment (all nullable; the resolver fills what it can).
    camera_id                INTEGER REFERENCES camera(id),
    telescope_id             INTEGER REFERENCES telescope(id),
    telescope_configuration_id INTEGER REFERENCES telescope_configuration(id),
    filter_id                INTEGER REFERENCES filter(id),
    mount_id                 INTEGER REFERENCES mount(id),
    filter_wheel_id          INTEGER REFERENCES filter_wheel(id),
    focuser_id               INTEGER REFERENCES focuser(id),

    -- Capture settings (from FITS header). Bias frames legitimately have ~0
    -- exposure, so the constraint is >= 0 (the spec's >0 was light-centric).
    exposure_seconds         REAL    NOT NULL DEFAULT 0 CHECK (exposure_seconds >= 0),
    gain                     REAL,
    offset_adu               REAL,
    sensor_temp_c            REAL,
    set_temp_c               REAL,
    binning_x                INTEGER,
    binning_y                INTEGER,
    bit_depth                INTEGER,
    image_width              INTEGER,
    image_height             INTEGER,

    -- Timing (§6). date_obs_utc is required; the pipeline falls back to file
    -- mtime when a header lacks DATE-OBS so ingest never fails on it.
    date_obs_utc             TEXT    NOT NULL,
    obs_mjd                  REAL,

    -- Pointing (plate-solved or header).
    ra_deg                   REAL,
    dec_deg                  REAL,
    rotation_deg             REAL,
    pixel_scale_arcsec       REAL,
    airmass                  REAL,

    -- Quality metrics (computed at/after ingest; NULL in v0.40.0).
    hfr                      REAL,
    star_count               INTEGER,
    median_adu               REAL,
    background_adu           REAL,
    snr_estimate             REAL,

    -- Site (denormalized from session for standalone queryability).
    latitude                 REAL,
    longitude                REAL,
    elevation_m              REAL,

    -- Forensics / hints. object_hint is the raw OBJECT header; filter_name_hint
    -- is the raw FILTER header, kept so a light catalogs with its filter name
    -- even before the physical filter_id resolves (rig assignment is v0.41.0).
    object_hint              TEXT,
    filter_name_hint         TEXT,
    fits_header_json         TEXT,

    created_at               TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT    NOT NULL DEFAULT (datetime('now')),

    UNIQUE (project_id, content_hash)  -- migration 0040: per-project identity
);

CREATE INDEX idx_sub_frame_project ON sub_frame(project_id);
CREATE INDEX idx_sub_frame_session ON sub_frame(session_id);
CREATE INDEX idx_sub_frame_rig ON sub_frame(rig_id);
CREATE INDEX idx_sub_frame_target ON sub_frame(project_target_id);
CREATE INDEX idx_sub_frame_run ON sub_frame(ingestion_run_id);
CREATE INDEX idx_sub_frame_camera ON sub_frame(camera_id);
CREATE INDEX idx_sub_frame_telescope ON sub_frame(telescope_id);
CREATE INDEX idx_sub_frame_filter ON sub_frame(filter_id);
CREATE INDEX idx_sub_frame_frame_type ON sub_frame(frame_type);
CREATE INDEX idx_sub_frame_date_obs ON sub_frame(date_obs_utc);

-- Partial composite indices keyed to the calibration-match queries (§6/§7).
CREATE INDEX idx_sub_frame_match_light
    ON sub_frame(camera_id, gain, exposure_seconds, binning_x, binning_y)
    WHERE frame_type = 'light' AND accepted = 1;
CREATE INDEX idx_sub_frame_match_dark
    ON sub_frame(camera_id, gain, exposure_seconds, binning_x, binning_y, set_temp_c)
    WHERE frame_type = 'dark' AND accepted = 1;
CREATE INDEX idx_sub_frame_match_flat
    ON sub_frame(camera_id, gain, filter_id, binning_x, binning_y, telescope_configuration_id)
    WHERE frame_type = 'flat' AND accepted = 1;
CREATE INDEX idx_sub_frame_match_bias
    ON sub_frame(camera_id, gain, binning_x, binning_y)
    WHERE frame_type = 'bias' AND accepted = 1;

-- File locations (§10, generalized) — one row per cataloged file (any category),
-- with optional links to the sub_frame / processed_image it represents. Multiple
-- rows may share a sub_frame_id (same sub in several places).
CREATE TABLE file_location (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Ownership (migration 0040): each project owns its own row for a path.
    project_id           INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    path                 TEXT    NOT NULL,
    category             TEXT    NOT NULL DEFAULT 'other'
                             CHECK (category IN
                                 ('sub_frame', 'processed', 'pxiproject', 'log', 'other')),
    sub_frame_id         INTEGER REFERENCES sub_frame(id) ON DELETE CASCADE,
    processed_image_id   INTEGER REFERENCES processed_image(id) ON DELETE CASCADE,
    path_type            TEXT    NOT NULL DEFAULT 'original'
                             CHECK (path_type IN
                                 ('original', 'working_copy', 'archive', 'reorganized', 'other')),
    volume_label         TEXT,
    size_bytes           INTEGER,
    file_hash            TEXT,
    mtime                TEXT,
    last_verified_at     TEXT,
    last_verified_status TEXT    CHECK (last_verified_status IS NULL OR last_verified_status IN
                             ('ok', 'missing', 'hash_mismatch', 'unreadable')),
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, path)  -- migration 0040: per-project identity
);
CREATE INDEX idx_file_location_project ON file_location(project_id);
CREATE INDEX idx_file_location_sub_frame ON file_location(sub_frame_id);
CREATE INDEX idx_file_location_processed ON file_location(processed_image_id);
CREATE INDEX idx_file_location_hash ON file_location(file_hash);
CREATE INDEX idx_file_location_category ON file_location(category);

-- Session logs + events (§5) — created empty; parsed in v0.44.0.
CREATE TABLE session_log_file (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER REFERENCES session(id) ON DELETE CASCADE,
    file_hash        TEXT    NOT NULL UNIQUE,
    path             TEXT,
    source           TEXT    NOT NULL DEFAULT 'other'
                         CHECK (source IN ('nina', 'asiair', 'phd2', 'other')),
    covered_start_utc TEXT,
    covered_end_utc  TEXT,
    parse_status     TEXT    NOT NULL DEFAULT 'pending'
                         CHECK (parse_status IN ('pending', 'parsed', 'failed', 'partial')),
    parse_error      TEXT,
    raw_text         BLOB,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_session_log_file_session ON session_log_file(session_id);

CREATE TABLE session_event (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           INTEGER REFERENCES session(id) ON DELETE CASCADE,
    event_utc            TEXT    NOT NULL,
    event_type           TEXT    NOT NULL CHECK (event_type IN (
                             'session_start', 'session_end', 'slew_start', 'slew_end',
                             'plate_solve_start', 'plate_solve_end', 'plate_solve_failed',
                             'filter_change', 'exposure_start', 'exposure_end',
                             'autofocus_start', 'autofocus_end', 'dither',
                             'meridian_flip_start', 'meridian_flip_end',
                             'guiding_start', 'guiding_stop', 'guiding_lost',
                             'cooling_target_reached', 'error', 'warning', 'info', 'other'
                         )),
    event_data_json      TEXT,
    related_sub_frame_id INTEGER REFERENCES sub_frame(id) ON DELETE SET NULL,
    related_filter_id    INTEGER REFERENCES filter(id),
    created_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_session_event_session ON session_event(session_id, event_utc);
CREATE INDEX idx_session_event_type ON session_event(event_type);

-- Autofocus runs (§9) — created empty; populated in v0.44.0.
CREATE TABLE autofocus_run (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER REFERENCES session(id) ON DELETE CASCADE,
    filter_id         INTEGER REFERENCES filter(id),
    focuser_id        INTEGER REFERENCES focuser(id),
    triggered_at_utc  TEXT,
    completed_at_utc  TEXT,
    temperature_c     REAL,
    initial_position  INTEGER,
    final_position    INTEGER,
    initial_hfr       REAL,
    final_hfr         REAL,
    success           INTEGER CHECK (success IS NULL OR success IN (0, 1)),
    trigger_reason    TEXT    CHECK (trigger_reason IS NULL OR trigger_reason IN
                          ('scheduled', 'temperature_delta', 'hfr_drift', 'filter_change', 'manual')),
    source            TEXT    NOT NULL DEFAULT 'other'
                          CHECK (source IN ('nina', 'asiair', 'manual', 'other')),
    raw_json          TEXT,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_autofocus_run_session ON autofocus_run(session_id);

-- PHD2 guiding (§8) — created empty; populated in v0.43.0.
CREATE TABLE guiding_log_file (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id               INTEGER REFERENCES session(id) ON DELETE CASCADE,
    file_hash                TEXT    NOT NULL UNIQUE,
    path                     TEXT,
    start_utc                TEXT,
    end_utc                  TEXT,
    guide_camera_id          INTEGER REFERENCES camera(id),
    guide_scope_id           INTEGER REFERENCES guide_scope(id),
    oag_id                   INTEGER REFERENCES oag(id),
    guide_pixel_scale_arcsec REAL,
    parse_status             TEXT    NOT NULL DEFAULT 'pending'
                                 CHECK (parse_status IN ('pending', 'parsed', 'failed', 'partial')),
    created_at               TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_guiding_log_file_session ON guiding_log_file(session_id);

CREATE TABLE guiding_sample (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    guiding_log_file_id  INTEGER NOT NULL REFERENCES guiding_log_file(id) ON DELETE CASCADE,
    sample_utc           TEXT    NOT NULL,
    ra_error_arcsec      REAL,
    dec_error_arcsec     REAL,
    ra_correction        REAL,
    dec_correction       REAL,
    snr                  REAL,
    star_mass            REAL,
    frame_number         INTEGER
);
-- The critical index for per-sub time-range RMS lookups (§8/§14).
CREATE INDEX idx_guiding_sample_log_time
    ON guiding_sample(guiding_log_file_id, sample_utc);

CREATE TABLE dither_event (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    guiding_log_file_id  INTEGER NOT NULL REFERENCES guiding_log_file(id) ON DELETE CASCADE,
    dither_utc           TEXT    NOT NULL,
    ra_offset_arcsec     REAL,
    dec_offset_arcsec    REAL,
    settle_completed_utc TEXT,
    settle_failed        INTEGER NOT NULL DEFAULT 0 CHECK (settle_failed IN (0, 1))
);
CREATE INDEX idx_dither_event_log ON dither_event(guiding_log_file_id);

-- Project ↔ source-folder binding (v0.40.0).
CREATE TABLE project_source_folder (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    path       TEXT    NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    added_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, path)
);
CREATE INDEX idx_project_source_folder_project ON project_source_folder(project_id);
-- At most one primary folder per project.
CREATE UNIQUE INDEX idx_project_source_folder_one_primary
    ON project_source_folder(project_id) WHERE is_primary = 1;

-- Deferred back-reference resolved now that sub_frame exists.
ALTER TABLE project ADD COLUMN cover_sub_frame_id INTEGER REFERENCES sub_frame(id);

-- updated_at triggers (equipment-table convention: only fire when the caller
-- didn't already bump updated_at, so manual updates don't double-fire).
CREATE TRIGGER trg_session_updated_at
AFTER UPDATE ON session
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE session SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_sub_frame_updated_at
AFTER UPDATE ON sub_frame
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE sub_frame SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_processed_image_updated_at
AFTER UPDATE ON processed_image
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE processed_image SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Calibration-matching views (§7). All consider only accepted = 1 frames on both
-- sides. These are views, not materialized tables.

-- Darks match on camera + gain + exposure + binning, with set temperature within
-- ±1.0 °C (never matched on filter).
CREATE VIEW matching_darks AS
SELECT l.id AS light_id, d.id AS dark_id
FROM sub_frame l
JOIN sub_frame d
    ON  d.frame_type = 'dark' AND d.accepted = 1
    AND d.camera_id = l.camera_id
    AND d.gain IS l.gain
    AND d.exposure_seconds = l.exposure_seconds
    AND d.binning_x IS l.binning_x
    AND d.binning_y IS l.binning_y
    AND (
        (d.set_temp_c IS NULL AND l.set_temp_c IS NULL)
        OR ABS(d.set_temp_c - l.set_temp_c) <= 1.0
    )
WHERE l.frame_type = 'light' AND l.accepted = 1;

-- Flats match on camera + gain + filter + binning + telescope configuration
-- (optical-train state matters; a flat at native FL doesn't calibrate a 0.7x light).
CREATE VIEW matching_flats AS
SELECT l.id AS light_id, f.id AS flat_id
FROM sub_frame l
JOIN sub_frame f
    ON  f.frame_type = 'flat' AND f.accepted = 1
    AND f.camera_id = l.camera_id
    AND f.gain IS l.gain
    AND f.filter_id = l.filter_id
    AND f.binning_x IS l.binning_x
    AND f.binning_y IS l.binning_y
    AND f.telescope_configuration_id IS l.telescope_configuration_id
WHERE l.frame_type = 'light' AND l.accepted = 1;

-- Bias match on camera + gain + binning.
CREATE VIEW matching_bias AS
SELECT l.id AS light_id, b.id AS bias_id
FROM sub_frame l
JOIN sub_frame b
    ON  b.frame_type = 'bias' AND b.accepted = 1
    AND b.camera_id = l.camera_id
    AND b.gain IS l.gain
    AND b.binning_x IS l.binning_x
    AND b.binning_y IS l.binning_y
WHERE l.frame_type = 'light' AND l.accepted = 1;

-- Per accepted light frame: does it have at least one matching dark / flat / bias?
CREATE VIEW calibration_coverage AS
SELECT
    l.id AS light_id,
    CASE WHEN EXISTS (SELECT 1 FROM matching_darks md WHERE md.light_id = l.id)
         THEN 1 ELSE 0 END AS has_dark,
    CASE WHEN EXISTS (SELECT 1 FROM matching_flats mf WHERE mf.light_id = l.id)
         THEN 1 ELSE 0 END AS has_flat,
    CASE WHEN EXISTS (SELECT 1 FROM matching_bias mb WHERE mb.light_id = l.id)
         THEN 1 ELSE 0 END AS has_bias
FROM sub_frame l
WHERE l.frame_type = 'light' AND l.accepted = 1;

-- Integration time grouped by project / target / line_name. A duoband filter
-- (two passband rows) INTENTIONALLY double-counts — one row per line — which is
-- correct for "how much Ha have I captured?".
CREATE VIEW integration_time_per_project_filter AS
SELECT
    pt.project_id          AS project_id,
    sf.project_target_id   AS project_target_id,
    fp.line_name           AS line_name,
    SUM(sf.exposure_seconds)          AS total_seconds,
    SUM(sf.exposure_seconds) / 60.0   AS total_minutes,
    SUM(sf.exposure_seconds) / 3600.0 AS total_hours,
    COUNT(*)                          AS sub_count
FROM sub_frame sf
JOIN filter_passband fp ON fp.filter_id = sf.filter_id AND fp.active = 1
LEFT JOIN project_target pt ON pt.id = sf.project_target_id
WHERE sf.frame_type = 'light' AND sf.accepted = 1
GROUP BY pt.project_id, sf.project_target_id, fp.line_name;

-- Per-project per-line goal vs actual (NULL-safe). Goals are keyed (project_id,
-- line_name) per the shipped project_filter_goal shape; actuals sum across targets.
CREATE VIEW project_filter_goal_progress AS
SELECT
    g.id           AS goal_id,
    g.project_id   AS project_id,
    g.line_name    AS line_name,
    g.goal_minutes AS goal_minutes,
    COALESCE(SUM(i.total_minutes), 0) AS actual_minutes,
    CASE WHEN g.goal_minutes > 0
         THEN COALESCE(SUM(i.total_minutes), 0) / g.goal_minutes
         ELSE NULL END AS completion_ratio
FROM project_filter_goal g
LEFT JOIN integration_time_per_project_filter i
    ON i.project_id = g.project_id AND i.line_name = g.line_name
GROUP BY g.id;

-- "What happened during this session" rollup.
CREATE VIEW session_summary AS
SELECT
    s.id        AS session_id,
    s.project_id AS project_id,
    s.rig_id    AS rig_id,
    s.start_utc AS start_utc,
    s.end_utc   AS end_utc,
    CASE WHEN s.end_utc IS NOT NULL
         THEN (julianday(s.end_utc) - julianday(s.start_utc)) * 24.0
         ELSE NULL END AS duration_hours,
    COUNT(sf.id) AS total_subs,
    SUM(CASE WHEN sf.frame_type = 'light' AND sf.accepted = 1 THEN 1 ELSE 0 END)
        AS accepted_lights,
    SUM(CASE WHEN sf.frame_type = 'light' AND sf.accepted = 0 THEN 1 ELSE 0 END)
        AS rejected_lights,
    SUM(CASE WHEN sf.frame_type = 'light' AND sf.accepted = 1
             THEN sf.exposure_seconds ELSE 0 END) / 60.0 AS accepted_light_minutes,
    COUNT(DISTINCT sf.project_target_id) AS distinct_targets,
    COUNT(DISTINCT sf.filter_id)         AS distinct_filters
FROM session s
LEFT JOIN sub_frame sf ON sf.session_id = s.id
GROUP BY s.id;
