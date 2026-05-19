-- NightCrate version: 0.36.0
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
    staged        INTEGER NOT NULL DEFAULT 0 CHECK (staged IN (0, 1)),
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
