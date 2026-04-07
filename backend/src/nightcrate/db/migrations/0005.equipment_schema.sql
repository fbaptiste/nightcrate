-- depends: 0004.aberration_cache

-- NightCrate Equipment Database Schema — v0.8.0 (Revised)
-- SQLite DDL for all proposed equipment tables.
-- Incorporates revision spec: no custom_fields, seed tracking, alias tables,
-- closed-vocabulary CHECK constraints, updated_at triggers.
--
-- Existing tables (setting, recent_file, aberration_analysis, aberration_star)
-- are not included.

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

CREATE TABLE IF NOT EXISTS computer_type (
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_computer_type_seed_key
    ON computer_type(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_computer_type_updated_at
AFTER UPDATE ON computer_type
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE computer_type SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS filter_type (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE CHECK (name IN (
        'broadband_luminance',
        'broadband_color',
        'narrowband_single',
        'narrowband_dual',
        'narrowband_tri',
        'uv_ir_cut',
        'light_pollution',
        'neutral_density',
        'other'
    )),
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

-- Seed filter_type rows
INSERT OR IGNORE INTO filter_type (name, description, source, seed_key) VALUES
    ('broadband_luminance', 'Broadband luminance / clear filter covering the full visible spectrum', 'seed', 'filter_type.broadband_luminance'),
    ('broadband_color', 'Broadband R, G, or B filter for LRGB imaging', 'seed', 'filter_type.broadband_color'),
    ('narrowband_single', 'Narrowband filter isolating a single emission line (e.g. Ha, Oiii, Sii)', 'seed', 'filter_type.narrowband_single'),
    ('narrowband_dual', 'Dual-narrowband filter combining two emission lines in one piece of glass', 'seed', 'filter_type.narrowband_dual'),
    ('narrowband_tri', 'Tri-narrowband filter combining three emission lines', 'seed', 'filter_type.narrowband_tri'),
    ('uv_ir_cut', 'UV/IR blocking filter', 'seed', 'filter_type.uv_ir_cut'),
    ('light_pollution', 'Broadband light pollution rejection filter', 'seed', 'filter_type.light_pollution'),
    ('neutral_density', 'Neutral density filter', 'seed', 'filter_type.neutral_density'),
    ('other', 'Filter that does not fit standard categories', 'seed', 'filter_type.other');

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
    hcg_threshold_gain INTEGER,
    notes TEXT,
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
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

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
    filter_size_id INTEGER REFERENCES filter_size(id),
    model_name TEXT NOT NULL,
    peak_transmission_pct REAL,
    mounted_thickness_mm REAL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name, filter_size_id)
);

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
        'Lum', 'R', 'G', 'B',
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
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

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
-- FOCUSER
-- ============================================================

CREATE TABLE IF NOT EXISTS focuser (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturer(id),
    model_name TEXT NOT NULL,
    motorized INTEGER NOT NULL DEFAULT 1 CHECK (motorized IN (0, 1)),
    travel_range_mm REAL,
    step_size_um REAL,
    total_steps INTEGER,
    temperature_compensation INTEGER NOT NULL DEFAULT 0 CHECK (temperature_compensation IN (0, 1)),
    backlash_steps INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

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
    computer_type_id INTEGER REFERENCES computer_type(id),
    model_name TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, model_name)
);

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT,
    UNIQUE (manufacturer_id, name)
);

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
