-- Project metadata + manual imaging sessions (v0.38.0)
-- depends: 0034.project_solve
--
-- Adds: rig association (multi), a location reference, manually-entered
-- capture sessions (one row = a batch of N identical light subs), and
-- per-filter integration goals. Per-filter ACTUAL integration is derived
-- from sessions (exposure x sub count); the v0.39.0 ingest pipeline will
-- store individual file-backed sub_frames separately and COALESCE over the
-- manual value. Calibration frames are deferred to v0.38.1.

-- Many-to-many: a project can use multiple rigs (dual-rig setup).
CREATE TABLE IF NOT EXISTS project_rig (
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    rig_id     INTEGER NOT NULL REFERENCES rig(id),
    PRIMARY KEY (project_id, rig_id)
);

CREATE INDEX IF NOT EXISTS idx_project_rig_project ON project_rig(project_id);
CREATE INDEX IF NOT EXISTS idx_project_rig_rig ON project_rig(rig_id);

-- Single optional location. No CASCADE: locations soft-delete (active = 0),
-- so the reference stays valid when a location is retired.
ALTER TABLE project ADD COLUMN location_id INTEGER REFERENCES location(id);

-- A manually-entered capture batch: N identical light subs of one filter.
-- `filter_id` (a specific equipment filter) OR `line_name` (a generic
-- bandpass) identifies the filter; at least one is required. `line_name`
-- uses the same closed vocabulary as filter_passband.line_name.
CREATE TABLE IF NOT EXISTS project_session (
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
    -- ISO date ('YYYY-MM-DD') or full ISO datetime; NULL when unknown.
    session_date     TEXT,
    notes            TEXT,
    source           TEXT    NOT NULL DEFAULT 'manual'
                         CHECK (source IN ('manual', 'auto')),
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    CHECK (filter_id IS NOT NULL OR line_name IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_project_session_project ON project_session(project_id);

CREATE TRIGGER IF NOT EXISTS trg_project_session_updated_at
AFTER UPDATE ON project_session
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project_session SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Per-filter integration goal for a project ("4 hours of Ha").
CREATE TABLE IF NOT EXISTS project_filter_goal (
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

CREATE INDEX IF NOT EXISTS idx_project_filter_goal_project ON project_filter_goal(project_id);

CREATE TRIGGER IF NOT EXISTS trg_project_filter_goal_updated_at
AFTER UPDATE ON project_filter_goal
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project_filter_goal SET updated_at = datetime('now') WHERE id = NEW.id;
END;
