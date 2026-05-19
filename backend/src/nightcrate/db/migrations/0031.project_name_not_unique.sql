-- Drop UNIQUE constraint on project.name — duplicate names allowed (v0.35.0)
-- depends: 0030.project_image_staged

PRAGMA foreign_keys = OFF;

CREATE TABLE project_new (
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

INSERT INTO project_new SELECT * FROM project;
DROP TABLE project;
ALTER TABLE project_new RENAME TO project;

CREATE INDEX IF NOT EXISTS idx_project_active ON project(active);

CREATE TRIGGER IF NOT EXISTS trg_project_updated_at
AFTER UPDATE ON project
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project SET updated_at = datetime('now') WHERE id = NEW.id;
END;

PRAGMA foreign_keys = ON;
