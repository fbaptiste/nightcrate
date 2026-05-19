-- Projects + project images (v0.35.0)
-- depends: 0028.phd2_recent_files

CREATE TABLE IF NOT EXISTS project (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT,
    notes       TEXT,
    status      TEXT    NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'complete', 'abandoned')),
    active      INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_project_active ON project(active);

CREATE TRIGGER IF NOT EXISTS trg_project_updated_at
AFTER UPDATE ON project
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS project_image (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    file_path     TEXT    NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_main       INTEGER NOT NULL DEFAULT 0 CHECK (is_main IN (0, 1)),
    notes         TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_project_image_project
    ON project_image(project_id);

-- At most one main image per project.
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_image_main
    ON project_image(project_id) WHERE is_main = 1;

CREATE TRIGGER IF NOT EXISTS trg_project_image_updated_at
AFTER UPDATE ON project_image
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project_image SET updated_at = datetime('now') WHERE id = NEW.id;
END;
