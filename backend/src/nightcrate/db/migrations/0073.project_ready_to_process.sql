-- Add the hand-set Ready to process project status (v0.53.0).
-- depends: 0072.uncataloged_file

PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;

-- A plain table copy would lower AUTOINCREMENT after the highest project had
-- been deleted. Keep the user's counter independently of the surviving rows.
CREATE TEMP TABLE _project_sequence_0073 (seq INTEGER);
INSERT INTO _project_sequence_0073
SELECT seq FROM sqlite_sequence WHERE name = 'project';

ALTER TABLE project RENAME TO _project_legacy_0073;

CREATE TABLE project (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT    NOT NULL,
    description          TEXT,
    notes                TEXT,
    status               TEXT    NOT NULL DEFAULT 'active'
                         CHECK (status IN (
                             'active', 'ready_to_process', 'paused',
                             'complete', 'abandoned'
                         )),
    active               INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    location_id          INTEGER REFERENCES location(id),
    cover_sub_frame_id   INTEGER REFERENCES sub_frame(id)
);

INSERT INTO project (
    id, name, description, notes, status, active, created_at, updated_at,
    location_id, cover_sub_frame_id
)
SELECT
    id, name, description, notes, status, active, created_at, updated_at,
    location_id, cover_sub_frame_id
FROM _project_legacy_0073;

DROP TABLE _project_legacy_0073;

CREATE INDEX idx_project_active ON project(active);

CREATE TRIGGER trg_project_updated_at
AFTER UPDATE ON project
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE project SET updated_at = datetime('now') WHERE id = NEW.id;
END;

UPDATE sqlite_sequence
SET seq = (SELECT seq FROM _project_sequence_0073)
WHERE name = 'project' AND EXISTS (SELECT 1 FROM _project_sequence_0073);

INSERT INTO sqlite_sequence (name, seq)
SELECT 'project', seq
FROM _project_sequence_0073
WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'project');

DROP TABLE _project_sequence_0073;

PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
