-- Project-owned files: every cataloged row belongs to exactly the project that
-- cataloged it (v0.40.0).
--
-- Why: the 0037 imaging-core schema was global — sub_frame.content_hash and
-- file_location.path were globally UNIQUE, so one physical file was one row
-- regardless of project, a frame's project was reached only indirectly
-- (sub_frame -> ingestion_run.project_id / session.project_id), and non-frame
-- files (logs, .pxiproject, other) had no project link at all (they were scoped
-- to a project by path-prefix matching at query time). That global model leaked
-- across projects (the "Others" tab forgot the prefix scope) and, worse, the
-- global content_hash silently REASSIGNED a file to whichever project scanned it
-- last instead of letting each project own its own copy.
--
-- New model: each project has its own files, plain and simple. A given physical
-- file may be cataloged in more than one project; when it is, each project gets
-- its OWN independent row (no shared row, no global identity). Re-scan stays
-- idempotent PER PROJECT via UNIQUE(project_id, content_hash) / UNIQUE(project_id,
-- path). "Have I imaged this object before?" is answered by the plate-solve /
-- project_dso layer, not by frame identity, so nothing is lost.
--
-- This rebuilds three tables to add project_id + per-project uniqueness, following
-- the table-rewrite pattern from migration 0038 (rename -> create -> copy -> drop)
-- because SQLite can't drop a column-level UNIQUE in place. legacy_alter_table
-- keeps child FK names (file_location.sub_frame_id / .processed_image_id,
-- session_event.related_sub_frame_id, project.cover_sub_frame_id) pinned across
-- the rename/drop. The calibration/integration/session_summary VIEWS reference
-- sub_frame by name and only use columns that survive, so they auto-rebind and are
-- intentionally left untouched (calibration-match scoping is a v0.41.0 concern).
--
-- Backfill drops rows that resolve to no project (unreachable in any catalog
-- today): sub_frames with neither an ingestion_run nor a session carrying a
-- project, processed_images with a NULL project_id, and file_location rows that
-- link to nothing and sit under no bound project folder.
--
-- depends: 0039.processed_image_total_exposure

PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. sub_frame — add project_id NOT NULL + UNIQUE(project_id, content_hash)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE sub_frame RENAME TO _sub_frame_legacy;

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
    updated_at               TEXT    NOT NULL DEFAULT (datetime('now')),

    -- Per-project content identity: re-ingesting the same file into the same
    -- project updates its row; the same file in another project is its own row.
    UNIQUE (project_id, content_hash)
);

-- Copy rows, resolving project_id from the ingestion run (preferred) or the
-- session. Rows that resolve to no project are unreachable in any catalog today
-- and are dropped by the WHERE filter (the NOT NULL column rejects them anyway).
INSERT INTO sub_frame (
    id, project_id, content_hash, session_id, rig_id, project_target_id, ingestion_run_id,
    frame_type, accepted, rejection_reason, rejection_source,
    camera_id, telescope_id, telescope_configuration_id, filter_id, mount_id,
    filter_wheel_id, focuser_id,
    exposure_seconds, gain, offset_adu, sensor_temp_c, set_temp_c,
    binning_x, binning_y, bit_depth, image_width, image_height,
    date_obs_utc, obs_mjd, ra_deg, dec_deg, rotation_deg, pixel_scale_arcsec, airmass,
    hfr, star_count, median_adu, background_adu, snr_estimate,
    latitude, longitude, elevation_m,
    object_hint, filter_name_hint, fits_header_json, created_at, updated_at
)
SELECT
    s.id,
    COALESCE(
        (SELECT r.project_id FROM ingestion_run r WHERE r.id = s.ingestion_run_id),
        (SELECT ss.project_id FROM session ss WHERE ss.id = s.session_id)
    ) AS project_id,
    s.content_hash, s.session_id, s.rig_id, s.project_target_id, s.ingestion_run_id,
    s.frame_type, s.accepted, s.rejection_reason, s.rejection_source,
    s.camera_id, s.telescope_id, s.telescope_configuration_id, s.filter_id, s.mount_id,
    s.filter_wheel_id, s.focuser_id,
    s.exposure_seconds, s.gain, s.offset_adu, s.sensor_temp_c, s.set_temp_c,
    s.binning_x, s.binning_y, s.bit_depth, s.image_width, s.image_height,
    s.date_obs_utc, s.obs_mjd, s.ra_deg, s.dec_deg, s.rotation_deg, s.pixel_scale_arcsec, s.airmass,
    s.hfr, s.star_count, s.median_adu, s.background_adu, s.snr_estimate,
    s.latitude, s.longitude, s.elevation_m,
    s.object_hint, s.filter_name_hint, s.fits_header_json, s.created_at, s.updated_at
FROM _sub_frame_legacy s
WHERE COALESCE(
        (SELECT r.project_id FROM ingestion_run r WHERE r.id = s.ingestion_run_id),
        (SELECT ss.project_id FROM session ss WHERE ss.id = s.session_id)
    ) IS NOT NULL;

DROP TABLE _sub_frame_legacy;

CREATE INDEX IF NOT EXISTS idx_sub_frame_project ON sub_frame(project_id);
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

CREATE TRIGGER IF NOT EXISTS trg_sub_frame_updated_at
AFTER UPDATE ON sub_frame
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE sub_frame SET updated_at = datetime('now') WHERE id = NEW.id;
END;


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. processed_image — project_id becomes NOT NULL + UNIQUE(project_id, content_hash)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE processed_image RENAME TO _processed_image_legacy;

CREATE TABLE processed_image (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id             INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    content_hash           TEXT    NOT NULL,
    image_kind             TEXT    NOT NULL DEFAULT 'master'
                               CHECK (image_kind IN ('master', 'stack', 'processed', 'other')),
    frame_type             TEXT    CHECK (frame_type IS NULL OR frame_type IN
                               ('light', 'dark', 'flat', 'bias', 'dark_flat', 'unknown')),
    filter_id              INTEGER REFERENCES filter(id),
    line_name              TEXT    CHECK (line_name IS NULL OR line_name IN (
                               'Ha', 'Hb', 'Oiii', 'Sii', 'Nii', 'OI',
                               'Lum', 'R', 'G', 'B', 'R+',
                               'UVIR', 'LP', 'ND', 'other'
                           )),
    camera_id              INTEGER REFERENCES camera(id),
    telescope_id           INTEGER REFERENCES telescope(id),
    ncombine               INTEGER,
    total_exposure_seconds REAL,
    date_obs_utc           TEXT,
    image_width            INTEGER,
    image_height           INTEGER,
    fits_header_json       TEXT,
    ingestion_run_id       INTEGER REFERENCES ingestion_run(id) ON DELETE SET NULL,
    created_at             TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, content_hash)
);

INSERT INTO processed_image (
    id, project_id, content_hash, image_kind, frame_type, filter_id, line_name,
    camera_id, telescope_id, ncombine, total_exposure_seconds, date_obs_utc,
    image_width, image_height, fits_header_json, ingestion_run_id, created_at, updated_at
)
SELECT
    id, project_id, content_hash, image_kind, frame_type, filter_id, line_name,
    camera_id, telescope_id, ncombine, total_exposure_seconds, date_obs_utc,
    image_width, image_height, fits_header_json, ingestion_run_id, created_at, updated_at
FROM _processed_image_legacy
WHERE project_id IS NOT NULL;

DROP TABLE _processed_image_legacy;

CREATE INDEX IF NOT EXISTS idx_processed_image_project ON processed_image(project_id);
CREATE INDEX IF NOT EXISTS idx_processed_image_filter ON processed_image(filter_id);

CREATE TRIGGER IF NOT EXISTS trg_processed_image_updated_at
AFTER UPDATE ON processed_image
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE processed_image SET updated_at = datetime('now') WHERE id = NEW.id;
END;


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. file_location — add project_id NOT NULL + UNIQUE(project_id, path)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE file_location RENAME TO _file_location_legacy;

CREATE TABLE file_location (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
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
    -- A project owns one row per path; the same path in another project is its
    -- own row.
    UNIQUE (project_id, path)
);

-- Resolve project_id: image rows inherit it from the sub_frame / processed_image
-- they link to; standalone non-frame rows (logs / .pxiproject / other) resolve via
-- the project source folder they sit under (the path-prefix mapping, used one last
-- time). Rows that resolve to no project are dropped.
INSERT INTO file_location (
    id, project_id, path, category, sub_frame_id, processed_image_id, path_type,
    volume_label, size_bytes, file_hash, mtime, last_verified_at, last_verified_status,
    created_at
)
SELECT
    fl.id,
    COALESCE(
        (SELECT sf.project_id FROM sub_frame sf WHERE sf.id = fl.sub_frame_id),
        (SELECT pi.project_id FROM processed_image pi WHERE pi.id = fl.processed_image_id),
        -- Only TRULY standalone rows resolve by folder. A linked-but-dropped row
        -- (its sub/processed resolved to no project) stays NULL and is filtered out,
        -- rather than surviving with a dangling FK. The prefix is matched WITH a
        -- trailing separator so a sibling folder sharing a name prefix (e.g. a file
        -- under /data/M31_old can't be claimed by a folder bound as /data/M31) —
        -- mirrors remove_folder's runtime rstrip('/')+'/' prefix.
        (CASE WHEN fl.sub_frame_id IS NULL AND fl.processed_image_id IS NULL THEN
            (SELECT p.project_id FROM project_source_folder p
                 WHERE substr(fl.path, 1, length(rtrim(p.path, '/')) + 1)
                       = rtrim(p.path, '/') || '/' LIMIT 1)
         END)
    ) AS project_id,
    fl.path, fl.category, fl.sub_frame_id, fl.processed_image_id, fl.path_type,
    fl.volume_label, fl.size_bytes, fl.file_hash, fl.mtime, fl.last_verified_at,
    fl.last_verified_status, fl.created_at
FROM _file_location_legacy fl
WHERE COALESCE(
        (SELECT sf.project_id FROM sub_frame sf WHERE sf.id = fl.sub_frame_id),
        (SELECT pi.project_id FROM processed_image pi WHERE pi.id = fl.processed_image_id),
        (CASE WHEN fl.sub_frame_id IS NULL AND fl.processed_image_id IS NULL THEN
            (SELECT p.project_id FROM project_source_folder p
                 WHERE substr(fl.path, 1, length(rtrim(p.path, '/')) + 1)
                       = rtrim(p.path, '/') || '/' LIMIT 1)
         END)
    ) IS NOT NULL;

DROP TABLE _file_location_legacy;

CREATE INDEX IF NOT EXISTS idx_file_location_project ON file_location(project_id);
CREATE INDEX IF NOT EXISTS idx_file_location_sub_frame ON file_location(sub_frame_id);
CREATE INDEX IF NOT EXISTS idx_file_location_processed ON file_location(processed_image_id);
CREATE INDEX IF NOT EXISTS idx_file_location_hash ON file_location(file_hash);
CREATE INDEX IF NOT EXISTS idx_file_location_category ON file_location(category);

PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
