-- v0.47.0 — rig setup history, project-specific rig changes, and project software.
-- depends: 0068.clear_thumbnail_crops

CREATE TABLE rig_setup (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rig_id INTEGER NOT NULL REFERENCES rig(id) ON DELETE CASCADE,
    until_at TEXT NOT NULL,
    telescope_configuration_id INTEGER NOT NULL REFERENCES telescope_configuration(id),
    camera_id INTEGER NOT NULL REFERENCES camera(id),
    filter_wheel_id INTEGER REFERENCES filter_wheel(id),
    single_filter_id INTEGER REFERENCES filter(id),
    mount_id INTEGER REFERENCES mount(id),
    focuser_id INTEGER REFERENCES focuser(id),
    oag_id INTEGER REFERENCES oag(id),
    guide_scope_id INTEGER REFERENCES guide_scope(id),
    guide_camera_id INTEGER REFERENCES camera(id),
    computer_id INTEGER REFERENCES computer(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (id, rig_id)
);
CREATE INDEX idx_rig_setup_rig ON rig_setup(rig_id);

CREATE TABLE rig_setup_filter_slot (
    rig_setup_id INTEGER NOT NULL REFERENCES rig_setup(id) ON DELETE CASCADE,
    slot_number INTEGER NOT NULL CHECK (slot_number >= 1),
    filter_id INTEGER NOT NULL REFERENCES filter(id),
    PRIMARY KEY (rig_setup_id, slot_number),
    UNIQUE (rig_setup_id, filter_id)
);

CREATE TABLE rig_setup_software (
    rig_setup_id INTEGER NOT NULL REFERENCES rig_setup(id) ON DELETE CASCADE,
    software_id INTEGER NOT NULL REFERENCES software(id),
    PRIMARY KEY (rig_setup_id, software_id)
);

CREATE TABLE sub_frame_rig_setup (
    sub_frame_id INTEGER NOT NULL REFERENCES sub_frame(id) ON DELETE CASCADE,
    rig_id INTEGER NOT NULL,
    rig_setup_id INTEGER NOT NULL,
    PRIMARY KEY (sub_frame_id, rig_id),
    FOREIGN KEY (rig_setup_id, rig_id)
        REFERENCES rig_setup(id, rig_id) ON DELETE CASCADE
);
CREATE INDEX idx_sub_frame_rig_setup_setup ON sub_frame_rig_setup(rig_setup_id);

ALTER TABLE project_session ADD COLUMN rig_setup_id INTEGER
    REFERENCES rig_setup(id) ON DELETE SET NULL;
CREATE INDEX idx_project_session_rig_setup ON project_session(rig_setup_id);

CREATE TABLE project_rig_change (
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    rig_id INTEGER NOT NULL REFERENCES rig(id),
    telescope_configuration_id INTEGER REFERENCES telescope_configuration(id),
    camera_id INTEGER REFERENCES camera(id),
    filters_changed INTEGER NOT NULL DEFAULT 0 CHECK (filters_changed IN (0, 1)),
    filter_wheel_id INTEGER REFERENCES filter_wheel(id),
    single_filter_id INTEGER REFERENCES filter(id),
    mount_changed INTEGER NOT NULL DEFAULT 0 CHECK (mount_changed IN (0, 1)),
    mount_id INTEGER REFERENCES mount(id),
    focuser_changed INTEGER NOT NULL DEFAULT 0 CHECK (focuser_changed IN (0, 1)),
    focuser_id INTEGER REFERENCES focuser(id),
    guider_changed INTEGER NOT NULL DEFAULT 0 CHECK (guider_changed IN (0, 1)),
    oag_id INTEGER REFERENCES oag(id),
    guide_scope_id INTEGER REFERENCES guide_scope(id),
    guide_camera_changed INTEGER NOT NULL DEFAULT 0
        CHECK (guide_camera_changed IN (0, 1)),
    guide_camera_id INTEGER REFERENCES camera(id),
    computer_changed INTEGER NOT NULL DEFAULT 0 CHECK (computer_changed IN (0, 1)),
    computer_id INTEGER REFERENCES computer(id),
    software_changed INTEGER NOT NULL DEFAULT 0 CHECK (software_changed IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (project_id, rig_id)
);

CREATE TRIGGER trg_project_rig_change_updated_at
AFTER UPDATE ON project_rig_change
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project_rig_change SET updated_at = datetime('now')
    WHERE project_id = NEW.project_id AND rig_id = NEW.rig_id;
END;

CREATE TABLE project_rig_change_filter_slot (
    project_id INTEGER NOT NULL,
    rig_id INTEGER NOT NULL,
    slot_number INTEGER NOT NULL CHECK (slot_number >= 1),
    filter_id INTEGER NOT NULL REFERENCES filter(id),
    PRIMARY KEY (project_id, rig_id, slot_number),
    UNIQUE (project_id, rig_id, filter_id),
    FOREIGN KEY (project_id, rig_id)
        REFERENCES project_rig_change(project_id, rig_id) ON DELETE CASCADE
);

CREATE TABLE project_rig_change_software (
    project_id INTEGER NOT NULL,
    rig_id INTEGER NOT NULL,
    software_id INTEGER NOT NULL REFERENCES software(id),
    PRIMARY KEY (project_id, rig_id, software_id),
    FOREIGN KEY (project_id, rig_id)
        REFERENCES project_rig_change(project_id, rig_id) ON DELETE CASCADE
);

CREATE TABLE software_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    software_id INTEGER NOT NULL REFERENCES software(id) ON DELETE CASCADE,
    version TEXT NOT NULL CHECK (length(trim(version)) BETWEEN 1 AND 50),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (software_id, version),
    UNIQUE (id, software_id)
);

CREATE TABLE project_software (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    software_id INTEGER NOT NULL REFERENCES software(id),
    software_version_id INTEGER,
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (software_version_id, software_id)
        REFERENCES software_version(id, software_id),
    UNIQUE (project_id, software_id, software_version_id)
);
CREATE UNIQUE INDEX idx_project_software_no_version
    ON project_software(project_id, software_id)
    WHERE software_version_id IS NULL;

CREATE VIEW sub_frame_equipment AS
SELECT
    sf.id AS sub_frame_id,
    sf.project_id,
    sf.rig_id,
    rs.id AS rig_setup_id,
    COALESCE(prc.telescope_configuration_id,
             rs.telescope_configuration_id,
             r.telescope_configuration_id) AS telescope_configuration_id,
    COALESCE(prc.camera_id, rs.camera_id, r.camera_id) AS camera_id
FROM sub_frame sf
LEFT JOIN rig r ON r.id = sf.rig_id
LEFT JOIN sub_frame_rig_setup sfs
    ON sfs.sub_frame_id = sf.id AND sfs.rig_id = sf.rig_id
LEFT JOIN rig_setup rs ON rs.id = sfs.rig_setup_id
LEFT JOIN project_rig_change prc
    ON prc.project_id = sf.project_id AND prc.rig_id = sf.rig_id;

DROP VIEW calibration_coverage;
DROP VIEW matching_darks;
DROP VIEW matching_flats;
DROP VIEW matching_bias;

CREATE VIEW matching_darks AS
SELECT l.id AS light_id, d.id AS dark_id
FROM sub_frame l
JOIN sub_frame_equipment le ON le.sub_frame_id = l.id
JOIN sub_frame d
    ON  d.frame_type = 'dark' AND d.accepted = 1
    AND d.project_id = l.project_id
    AND d.rig_id IS l.rig_id
    AND d.gain IS l.gain
    AND d.exposure_seconds = l.exposure_seconds
    AND d.binning_x IS l.binning_x
    AND d.binning_y IS l.binning_y
    AND (
        (d.set_temp_c IS NULL AND l.set_temp_c IS NULL)
        OR ABS(d.set_temp_c - l.set_temp_c) <= 1.0
    )
JOIN sub_frame_equipment de
    ON de.sub_frame_id = d.id AND de.camera_id IS le.camera_id
WHERE l.frame_type = 'light' AND l.accepted = 1;

CREATE VIEW matching_flats AS
SELECT l.id AS light_id, f.id AS flat_id
FROM sub_frame l
JOIN sub_frame_equipment le ON le.sub_frame_id = l.id
JOIN sub_frame f
    ON  f.frame_type = 'flat' AND f.accepted = 1
    AND f.project_id = l.project_id
    AND f.rig_id IS l.rig_id
    AND f.gain IS l.gain
    AND f.filter_name_hint IS l.filter_name_hint
    AND f.binning_x IS l.binning_x
    AND f.binning_y IS l.binning_y
JOIN sub_frame_equipment fe
    ON fe.sub_frame_id = f.id
    AND fe.camera_id IS le.camera_id
    AND fe.telescope_configuration_id IS le.telescope_configuration_id
WHERE l.frame_type = 'light' AND l.accepted = 1;

CREATE VIEW matching_bias AS
SELECT l.id AS light_id, b.id AS bias_id
FROM sub_frame l
JOIN sub_frame_equipment le ON le.sub_frame_id = l.id
JOIN sub_frame b
    ON  b.frame_type = 'bias' AND b.accepted = 1
    AND b.project_id = l.project_id
    AND b.rig_id IS l.rig_id
    AND b.gain IS l.gain
    AND b.binning_x IS l.binning_x
    AND b.binning_y IS l.binning_y
JOIN sub_frame_equipment be
    ON be.sub_frame_id = b.id AND be.camera_id IS le.camera_id
WHERE l.frame_type = 'light' AND l.accepted = 1;

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
