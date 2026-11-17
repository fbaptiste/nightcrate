-- Remove the unused per-folder and per-frame target labels (v0.54.1).
-- depends: 0073.project_ready_to_process

PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;

CREATE TEMP TABLE _sub_frame_sequence_0074 (seq INTEGER);
INSERT INTO _sub_frame_sequence_0074
SELECT seq FROM sqlite_sequence WHERE name = 'sub_frame';

CREATE TEMP TABLE _source_folder_sequence_0074 (seq INTEGER);
INSERT INTO _source_folder_sequence_0074
SELECT seq FROM sqlite_sequence WHERE name = 'project_source_folder';

DROP VIEW session_summary;

ALTER TABLE project_source_folder RENAME TO _project_source_folder_legacy_0074;

CREATE TABLE project_source_folder (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    path       TEXT    NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    added_at   TEXT    NOT NULL DEFAULT (datetime('now')), rig_id INTEGER REFERENCES rig(id),
    UNIQUE (project_id, path)
);

INSERT INTO project_source_folder (id, project_id, path, is_primary, added_at, rig_id)
SELECT id, project_id, path, is_primary, added_at, rig_id
FROM _project_source_folder_legacy_0074;

DROP TABLE _project_source_folder_legacy_0074;

ALTER TABLE sub_frame RENAME TO _sub_frame_legacy_0074;

CREATE TABLE sub_frame (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Ownership: the project that cataloged this file (v0.40.0). One row per
    -- (project, content); the same file in another project is a separate row.
    project_id               INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,

    -- Identity (§2.8): SHA-256 of file contents; re-ingest is idempotent per project.
    content_hash             TEXT    NOT NULL,

    -- Grouping (all nullable; a sub can ingest with partial/no context).
    session_id               INTEGER REFERENCES session(id) ON DELETE SET NULL,
    rig_id                   INTEGER REFERENCES rig(id),
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
    -- is the raw FILTER header (e.g. 'Ha') — kept so a light catalogs with its
    -- filter name even before filter_id resolves (v0.41.0 maps + back-fills).
    object_hint              TEXT,
    filter_name_hint         TEXT,
    fits_header_json         TEXT,

    created_at               TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT    NOT NULL DEFAULT (datetime('now')), frame_type_source TEXT NOT NULL DEFAULT 'auto'
    CHECK (frame_type_source IN ('auto', 'user')), quality_analyzed_at TEXT, quality_status TEXT
    CHECK (quality_status IS NULL OR quality_status IN ('ok', 'no_stars', 'unreadable')), quality_error TEXT,

    -- Per-project content identity: re-ingesting the same file into the same
    -- project updates its row; the same file in another project is its own row.
    UNIQUE (project_id, content_hash)
);

INSERT INTO sub_frame (
    id, project_id, content_hash, session_id, rig_id, ingestion_run_id,
    frame_type, accepted, rejection_reason, rejection_source,
    exposure_seconds, gain, offset_adu, sensor_temp_c, set_temp_c,
    binning_x, binning_y, bit_depth, image_width, image_height,
    date_obs_utc, obs_mjd, ra_deg, dec_deg, rotation_deg, pixel_scale_arcsec,
    airmass, hfr, star_count, median_adu, background_adu, snr_estimate,
    latitude, longitude, elevation_m, object_hint, filter_name_hint,
    fits_header_json, created_at, updated_at, frame_type_source,
    quality_analyzed_at, quality_status, quality_error
)
SELECT
    id, project_id, content_hash, session_id, rig_id, ingestion_run_id,
    frame_type, accepted, rejection_reason, rejection_source,
    exposure_seconds, gain, offset_adu, sensor_temp_c, set_temp_c,
    binning_x, binning_y, bit_depth, image_width, image_height,
    date_obs_utc, obs_mjd, ra_deg, dec_deg, rotation_deg, pixel_scale_arcsec,
    airmass, hfr, star_count, median_adu, background_adu, snr_estimate,
    latitude, longitude, elevation_m, object_hint, filter_name_hint,
    fits_header_json, created_at, updated_at, frame_type_source,
    quality_analyzed_at, quality_status, quality_error
FROM _sub_frame_legacy_0074;

DROP TABLE _sub_frame_legacy_0074;

CREATE INDEX idx_project_source_folder_project ON project_source_folder(project_id);
CREATE UNIQUE INDEX idx_project_source_folder_one_primary
    ON project_source_folder(project_id) WHERE is_primary = 1;

CREATE INDEX idx_sub_frame_project ON sub_frame(project_id);
CREATE INDEX idx_sub_frame_session ON sub_frame(session_id);
CREATE INDEX idx_sub_frame_rig ON sub_frame(rig_id);
CREATE INDEX idx_sub_frame_run ON sub_frame(ingestion_run_id);
CREATE INDEX idx_sub_frame_frame_type ON sub_frame(frame_type);
CREATE INDEX idx_sub_frame_date_obs ON sub_frame(date_obs_utc);

CREATE INDEX idx_sub_frame_match_light
    ON sub_frame(project_id, rig_id, gain, exposure_seconds, binning_x, binning_y)
    WHERE frame_type = 'light' AND accepted = 1;
CREATE INDEX idx_sub_frame_match_dark
    ON sub_frame(project_id, rig_id, gain, exposure_seconds, binning_x, binning_y, set_temp_c)
    WHERE frame_type = 'dark' AND accepted = 1;
CREATE INDEX idx_sub_frame_match_flat
    ON sub_frame(project_id, rig_id, gain, filter_name_hint, binning_x, binning_y)
    WHERE frame_type = 'flat' AND accepted = 1;
CREATE INDEX idx_sub_frame_match_bias
    ON sub_frame(project_id, rig_id, gain, binning_x, binning_y)
    WHERE frame_type = 'bias' AND accepted = 1;
CREATE INDEX idx_sub_frame_quality_todo ON sub_frame(project_id, frame_type)
    WHERE quality_analyzed_at IS NULL;

CREATE TRIGGER trg_sub_frame_updated_at
AFTER UPDATE ON sub_frame
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE sub_frame SET updated_at = datetime('now') WHERE id = NEW.id;
END;

UPDATE sqlite_sequence
SET seq = (SELECT seq FROM _source_folder_sequence_0074)
WHERE name = 'project_source_folder'
  AND EXISTS (SELECT 1 FROM _source_folder_sequence_0074);
INSERT INTO sqlite_sequence (name, seq)
SELECT 'project_source_folder', seq FROM _source_folder_sequence_0074
WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'project_source_folder');

UPDATE sqlite_sequence
SET seq = (SELECT seq FROM _sub_frame_sequence_0074)
WHERE name = 'sub_frame' AND EXISTS (SELECT 1 FROM _sub_frame_sequence_0074);
INSERT INTO sqlite_sequence (name, seq)
SELECT 'sub_frame', seq FROM _sub_frame_sequence_0074
WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'sub_frame');

DROP TABLE _source_folder_sequence_0074;
DROP TABLE _sub_frame_sequence_0074;

CREATE VIEW session_summary AS
SELECT
    s.id         AS session_id,
    s.project_id AS project_id,
    s.rig_id     AS rig_id,
    s.start_utc  AS start_utc,
    s.end_utc    AS end_utc,
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
    COUNT(DISTINCT sf.filter_name_hint)   AS distinct_filters
FROM session s
LEFT JOIN sub_frame sf ON sf.session_id = s.id
GROUP BY s.id;

PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
