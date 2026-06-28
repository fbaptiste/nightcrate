-- sub_frame: add filter_name_hint + drop the light-needs-filter CHECK (v0.40.0).
--
-- Why a separate migration instead of editing 0037: 0037 had already been applied
-- to a running dev database with the original shape (light-needs-filter CHECK
-- present, no filter_name_hint). yoyo never re-runs an applied migration, so the
-- corrected shape must arrive as a NEW forward migration that converges every DB
-- — fresh installs (which applied 0037's original shape) and the already-migrated
-- dev DB alike.
--
-- As-built rationale: at v0.40.0 ingest a light's filter_id is routinely NULL
-- (rig isn't resolved until v0.41.0, alias tables start empty), so the raw FILTER
-- header is kept in filter_name_hint and the light-needs-filter CHECK is dropped
-- — ingest must never fail on partial equipment (§1 design principle). v0.41.0
-- maps filter_name_hint -> filter_id and back-fills integration.
--
-- SQLite can't ALTER a CHECK in place, so this uses the standard table-rewrite
-- (rename → create → copy → drop), mirroring migration 0022.
--
-- depends: 0037.imaging_core

PRAGMA foreign_keys = OFF;
-- Children reference sub_frame(id) (file_location.sub_frame_id,
-- session_event.related_sub_frame_id, project.cover_sub_frame_id). legacy_alter_table
-- keeps their FK names pinned to "sub_frame" across the rename/drop so they re-bind
-- to the rebuilt table rather than dangling.
PRAGMA legacy_alter_table = ON;

ALTER TABLE sub_frame RENAME TO _sub_frame_legacy;

CREATE TABLE sub_frame (
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

    -- Forensics / hints. object_hint is the raw OBJECT header; filter_name_hint
    -- is the raw FILTER header (e.g. 'Ha') — kept so a light catalogs with its
    -- filter name even before filter_id resolves (v0.41.0 maps + back-fills).
    object_hint              TEXT,
    filter_name_hint         TEXT,
    fits_header_json         TEXT,

    created_at               TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT    NOT NULL DEFAULT (datetime('now'))
    -- No light-needs-filter CHECK (intentionally dropped — see header).
);

-- Copy existing rows. filter_name_hint is absent in the legacy table, so it is
-- omitted from both column lists and defaults to NULL in the rebuilt table.
INSERT INTO sub_frame (
    id, content_hash, session_id, rig_id, project_target_id, ingestion_run_id,
    frame_type, accepted, rejection_reason, rejection_source,
    camera_id, telescope_id, telescope_configuration_id, filter_id, mount_id,
    filter_wheel_id, focuser_id,
    exposure_seconds, gain, offset_adu, sensor_temp_c, set_temp_c,
    binning_x, binning_y, bit_depth, image_width, image_height,
    date_obs_utc, obs_mjd, ra_deg, dec_deg, rotation_deg, pixel_scale_arcsec, airmass,
    hfr, star_count, median_adu, background_adu, snr_estimate,
    latitude, longitude, elevation_m,
    object_hint, fits_header_json, created_at, updated_at
)
SELECT
    id, content_hash, session_id, rig_id, project_target_id, ingestion_run_id,
    frame_type, accepted, rejection_reason, rejection_source,
    camera_id, telescope_id, telescope_configuration_id, filter_id, mount_id,
    filter_wheel_id, focuser_id,
    exposure_seconds, gain, offset_adu, sensor_temp_c, set_temp_c,
    binning_x, binning_y, bit_depth, image_width, image_height,
    date_obs_utc, obs_mjd, ra_deg, dec_deg, rotation_deg, pixel_scale_arcsec, airmass,
    hfr, star_count, median_adu, background_adu, snr_estimate,
    latitude, longitude, elevation_m,
    object_hint, fits_header_json, created_at, updated_at
FROM _sub_frame_legacy;

DROP TABLE _sub_frame_legacy;

PRAGMA legacy_alter_table = OFF;

-- Recreate indexes (dropped with the legacy table).
CREATE INDEX IF NOT EXISTS idx_sub_frame_session ON sub_frame(session_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_rig ON sub_frame(rig_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_target ON sub_frame(project_target_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_run ON sub_frame(ingestion_run_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_camera ON sub_frame(camera_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_telescope ON sub_frame(telescope_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_filter ON sub_frame(filter_id);
CREATE INDEX IF NOT EXISTS idx_sub_frame_frame_type ON sub_frame(frame_type);
CREATE INDEX IF NOT EXISTS idx_sub_frame_date_obs ON sub_frame(date_obs_utc);

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

-- Recreate the updated_at trigger (dropped with the legacy table).
CREATE TRIGGER IF NOT EXISTS trg_sub_frame_updated_at
AFTER UPDATE ON sub_frame
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE sub_frame SET updated_at = datetime('now') WHERE id = NEW.id;
END;

PRAGMA foreign_keys = ON;
