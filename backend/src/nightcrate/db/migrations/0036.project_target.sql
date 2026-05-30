-- Manual project ↔ DSO associations (v0.38.0)
-- depends: 0035.project_sessions
--
-- Lets a user manually add target objects to a project without requiring a
-- plate solve. The Overview surfaces these alongside the solve-identified
-- mains (project_dso.is_main = 1), deduped by dso_id at the display layer.

CREATE TABLE IF NOT EXISTS project_target (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    dso_id     INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, dso_id)
);

CREATE INDEX IF NOT EXISTS idx_project_target_project ON project_target(project_id);
CREATE INDEX IF NOT EXISTS idx_project_target_dso ON project_target(dso_id);

-- Backfill from existing solve-flagged mains (v0.37 data) so the Overview's
-- main-target list survives a future solve deletion.
INSERT OR IGNORE INTO project_target (project_id, dso_id, created_at)
SELECT ps.project_id, pd.dso_id, pd.created_at
FROM project_dso pd
JOIN project_solve ps ON ps.id = pd.solve_id
WHERE pd.is_main = 1;
