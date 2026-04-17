-- depends: 0008.weather_cache

-- Rig: user-composed equipment template for imaging configurations.

CREATE TABLE IF NOT EXISTS rig (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,

    -- Required slots
    telescope_configuration_id INTEGER NOT NULL
        REFERENCES telescope_configuration(id),
    camera_id INTEGER NOT NULL
        REFERENCES camera(id),

    -- Optional slots
    filter_wheel_id INTEGER REFERENCES filter_wheel(id),
    single_filter_id INTEGER REFERENCES filter(id),
    mount_id INTEGER REFERENCES mount(id),
    focuser_id INTEGER REFERENCES focuser(id),
    oag_id INTEGER REFERENCES oag(id),
    guide_scope_id INTEGER REFERENCES guide_scope(id),
    guide_camera_id INTEGER REFERENCES camera(id),
    computer_id INTEGER REFERENCES computer(id),
    -- Metadata
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rig_one_default
    ON rig(is_default)
    WHERE is_default = 1;

CREATE INDEX IF NOT EXISTS idx_rig_telescope_configuration ON rig(telescope_configuration_id);
CREATE INDEX IF NOT EXISTS idx_rig_camera ON rig(camera_id);

CREATE TRIGGER IF NOT EXISTS trg_rig_updated_at
AFTER UPDATE ON rig
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE rig SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Filter slot junction table (rig-scoped, not filter-wheel-scoped).
CREATE TABLE IF NOT EXISTS rig_filter_slot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rig_id INTEGER NOT NULL REFERENCES rig(id) ON DELETE CASCADE,
    slot_number INTEGER NOT NULL CHECK (slot_number >= 1),
    filter_id INTEGER NOT NULL REFERENCES filter(id),
    UNIQUE (rig_id, slot_number),
    UNIQUE (rig_id, filter_id)
);

CREATE INDEX IF NOT EXISTS idx_rig_filter_slot_rig ON rig_filter_slot(rig_id);

-- Software junction table (many-to-many: rig can have multiple software).
CREATE TABLE IF NOT EXISTS rig_software (
    rig_id INTEGER NOT NULL REFERENCES rig(id) ON DELETE CASCADE,
    software_id INTEGER NOT NULL REFERENCES software(id),
    PRIMARY KEY (rig_id, software_id)
);

-- Convenience view resolving all equipment names for rig listing.
-- Includes guide camera sensor data for guide calculator computations.
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
    -- Mount
    r.mount_id,
    m.model_name AS mount_name,
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
    oag.model_name AS oag_name,
    -- Guide camera sensor (for guide calculator)
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
LEFT JOIN oag ON oag.id = r.oag_id
LEFT JOIN computer comp ON comp.id = r.computer_id
LEFT JOIN filter sf ON sf.id = r.single_filter_id;
