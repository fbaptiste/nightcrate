-- Imaging-core schema (v0.40.0): sessions, sub frames, processed images, file
-- locations, ingestion provenance, project source folders, plus the calibration-
-- matching and integration VIEWS.
--
-- This is the schema the Sessions/Sub-Frames/Ingest arc is built on (see PLAN.md
-- "Imaging Core Schema spec" §1-§15). The guiding / session-event / session-log /
-- autofocus tables are created EMPTY here so their forward FKs
-- (sub_frame.ingestion_run_id, project.cover_sub_frame_id,
-- session_event.related_sub_frame_id) resolve cleanly now; they are populated in
-- later versions (v0.43/0.44).
--
-- Forward-only and non-destructive: this migration only ADDS tables, views,
-- indices, triggers, and one nullable column on `project`. No existing table is
-- reshaped, so all existing user data (projects, locations, rigs, equipment,
-- plans) is preserved untouched.
--
-- Notes on shipped-shape fidelity:
--   * The new `session` table is the AUTO/ingest rig-night grouping of sub frames.
--     It is NOT `project_session` (migration 0035), which stays the MANUAL
--     capture-batch table. v0.42.0 reconciles manual vs derived integration.
--   * `project_filter_goal` (0035) is keyed (project_id, line_name); the goal-
--     progress view joins that shape, not the spec's project_target_id form.
--   * `project_target` (0036) has no mosaic panel columns yet (deferred).
--
-- depends: 0036.project_target


-- ─────────────────────────────────────────────────────────────────────────────
-- Ingestion provenance (§11)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ingestion_run (
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
CREATE INDEX IF NOT EXISTS idx_ingestion_run_project ON ingestion_run(project_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Sessions (§5) — auto/ingest rig-night grouping of sub frames
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS session (
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
CREATE INDEX IF NOT EXISTS idx_session_project ON session(project_id);
CREATE INDEX IF NOT EXISTS idx_session_rig ON session(rig_id);
CREATE INDEX IF NOT EXISTS idx_session_start ON session(start_utc);


-- ─────────────────────────────────────────────────────────────────────────────
-- Processed images (§2.9 promoted to first-class) — stacks / masters / finals
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS processed_image (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER REFERENCES project(id) ON DELETE CASCADE,
    content_hash     TEXT    NOT NULL UNIQUE,
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
    date_obs_utc     TEXT,
    image_width      INTEGER,
    image_height     INTEGER,
    fits_header_json TEXT,
    ingestion_run_id INTEGER REFERENCES ingestion_run(id) ON DELETE SET NULL,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_processed_image_project ON processed_image(project_id);
CREATE INDEX IF NOT EXISTS idx_processed_image_filter ON processed_image(filter_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Sub frames (§6) — the core atom; lights + darks + flats + bias share this table
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sub_frame (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity (§2.8): SHA-256 of file contents; re-ingest is idempotent.
    content_hash             TEXT    NOT NULL UNIQUE,

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

    -- Forensics / hints.
    object_hint              TEXT,
    fits_header_json         TEXT,

    created_at               TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT    NOT NULL DEFAULT (datetime('now')),

    -- Light frames must carry a filter; calibration frames need not.
    -- NOTE: superseded by migration 0038, which drops this CHECK and adds
    -- filter_name_hint — at v0.40.0 a light's filter_id is routinely NULL
    -- (rig not resolved until v0.41.0), and ingest must never fail on partial
    -- equipment. Kept here as-applied; do not edit an applied migration.
    CHECK (frame_type != 'light' OR filter_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_sub_frame_session ON sub_frame(session_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_rig ON sub_frame(rig_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_target ON sub_frame(project_target_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_run ON sub_frame(ingestion_run_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_camera ON sub_frame(camera_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_telescope ON sub_frame(telescope_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_filter ON sub_frame(filter_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_frame_type ON sub_frame(frame_type);
CREATE INDEX IF NOT EXISTS idx_sub_frame_date_obs ON sub_frame(date_obs_utc);

-- Partial composite indices keyed to the calibration-match queries (§6/§7).
CREATE INDEX IF NOT EXISTS idx_sub_frame_match_light
    ON sub_frame(camera_id, gain, exposure_seconds, binning_x, binning_y)
    WHERE frame_type = 'light' AND accepted = 1;
CREATE INDEX IF NOT EXISTS idx_sub_frame_match_dark
    ON sub_frame(camera_id, gain, exposure_seconds, binning_x, binning_y, set_temp_c)
    WHERE frame_type = 'dark' AND accepted = 1;
CREATE INDEX IF NOT EXISTS idx_sub_frame_match_flat
    ON sub_frame(camera_id, gain, filter_id, binning_x, binning_y, telescope_configuration_id)
    WHERE frame_type = 'flat' AND accepted = 1;
CREATE INDEX IF NOT EXISTS idx_sub_frame_match_bias
    ON sub_frame(camera_id, gain, binning_x, binning_y)
    WHERE frame_type = 'bias' AND accepted = 1;


-- ─────────────────────────────────────────────────────────────────────────────
-- File locations (§10, generalized) — one row per cataloged file (any category),
-- with optional links to the sub_frame / processed_image it represents. Multiple
-- rows may share a sub_frame_id (same sub in several places).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS file_location (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    path                 TEXT    NOT NULL UNIQUE,
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
    created_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_file_location_sub_frame ON file_location(sub_frame_id);
CREATE INDEX IF NOT EXISTS idx_file_location_processed ON file_location(processed_image_id);
CREATE INDEX IF NOT EXISTS idx_file_location_hash ON file_location(file_hash);
CREATE INDEX IF NOT EXISTS idx_file_location_category ON file_location(category);


-- ─────────────────────────────────────────────────────────────────────────────
-- Session logs + events (§5) — created empty; parsed in v0.44.0
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS session_log_file (
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
CREATE INDEX IF NOT EXISTS idx_session_log_file_session ON session_log_file(session_id);

CREATE TABLE IF NOT EXISTS session_event (
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
CREATE INDEX IF NOT EXISTS idx_session_event_session ON session_event(session_id, event_utc);
CREATE INDEX IF NOT EXISTS idx_session_event_type ON session_event(event_type);


-- ─────────────────────────────────────────────────────────────────────────────
-- Autofocus runs (§9) — created empty; populated in v0.44.0
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS autofocus_run (
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
CREATE INDEX IF NOT EXISTS idx_autofocus_run_session ON autofocus_run(session_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- PHD2 guiding (§8) — created empty; populated in v0.43.0
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS guiding_log_file (
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
CREATE INDEX IF NOT EXISTS idx_guiding_log_file_session ON guiding_log_file(session_id);

CREATE TABLE IF NOT EXISTS guiding_sample (
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
CREATE INDEX IF NOT EXISTS idx_guiding_sample_log_time
    ON guiding_sample(guiding_log_file_id, sample_utc);

CREATE TABLE IF NOT EXISTS dither_event (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    guiding_log_file_id  INTEGER NOT NULL REFERENCES guiding_log_file(id) ON DELETE CASCADE,
    dither_utc           TEXT    NOT NULL,
    ra_offset_arcsec     REAL,
    dec_offset_arcsec    REAL,
    settle_completed_utc TEXT,
    settle_failed        INTEGER NOT NULL DEFAULT 0 CHECK (settle_failed IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_dither_event_log ON dither_event(guiding_log_file_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Project ↔ source-folder binding (v0.40.0)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS project_source_folder (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    path       TEXT    NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    added_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, path)
);
CREATE INDEX IF NOT EXISTS idx_project_source_folder_project ON project_source_folder(project_id);
-- At most one primary folder per project.
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_source_folder_one_primary
    ON project_source_folder(project_id) WHERE is_primary = 1;


-- ─────────────────────────────────────────────────────────────────────────────
-- Deferred back-reference resolved now that sub_frame exists.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE project ADD COLUMN cover_sub_frame_id INTEGER REFERENCES sub_frame(id);


-- ─────────────────────────────────────────────────────────────────────────────
-- updated_at triggers (equipment-table convention: only fire when the caller
-- didn't already bump updated_at, so manual updates don't double-fire).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TRIGGER IF NOT EXISTS trg_session_updated_at
AFTER UPDATE ON session
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE session SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_sub_frame_updated_at
AFTER UPDATE ON sub_frame
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE sub_frame SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_processed_image_updated_at
AFTER UPDATE ON processed_image
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE processed_image SET updated_at = datetime('now') WHERE id = NEW.id;
END;


-- ─────────────────────────────────────────────────────────────────────────────
-- Calibration-matching views (§7). All consider only accepted = 1 frames on both
-- sides. These are views, not materialized tables.
-- ─────────────────────────────────────────────────────────────────────────────

-- Darks match on camera + gain + exposure + binning, with set temperature within
-- ±1.0 °C (never matched on filter).
CREATE VIEW IF NOT EXISTS matching_darks AS
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
CREATE VIEW IF NOT EXISTS matching_flats AS
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
CREATE VIEW IF NOT EXISTS matching_bias AS
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
CREATE VIEW IF NOT EXISTS calibration_coverage AS
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


-- ─────────────────────────────────────────────────────────────────────────────
-- Integration + goal-progress views (§12)
-- ─────────────────────────────────────────────────────────────────────────────

-- Integration time grouped by project / target / line_name. A duoband filter
-- (two passband rows) INTENTIONALLY double-counts — one row per line — which is
-- correct for "how much Ha have I captured?".
CREATE VIEW IF NOT EXISTS integration_time_per_project_filter AS
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
CREATE VIEW IF NOT EXISTS project_filter_goal_progress AS
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
CREATE VIEW IF NOT EXISTS session_summary AS
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
