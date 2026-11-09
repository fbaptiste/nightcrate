-- v0.47.0 — notes attached to a project's civil observing night.
-- depends: 0069.rig_setups_and_project_software

CREATE TABLE project_night_note (
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    night_date TEXT NOT NULL
        CHECK (night_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    notes TEXT NOT NULL CHECK (length(trim(notes)) > 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (project_id, night_date)
);
