-- Project thumbnail crop definitions (v0.36.0)
-- depends: 0031.project_name_not_unique

CREATE TABLE IF NOT EXISTS project_thumbnail (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    size            TEXT    NOT NULL CHECK (size IN ('small', 'medium', 'large')),
    source_image_id INTEGER REFERENCES project_image(id) ON DELETE SET NULL,
    crop_x          REAL    NOT NULL DEFAULT 0,
    crop_y          REAL    NOT NULL DEFAULT 0,
    crop_w          REAL    NOT NULL DEFAULT 1,
    crop_h          REAL    NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, size)
);

CREATE INDEX IF NOT EXISTS idx_project_thumbnail_project
    ON project_thumbnail(project_id);

CREATE TRIGGER IF NOT EXISTS trg_project_thumbnail_updated_at
AFTER UPDATE ON project_thumbnail
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project_thumbnail SET updated_at = datetime('now') WHERE id = NEW.id;
END;
