-- Project ↔ DSO main-target associations (v0.38.0)
-- depends: 0035.project_sessions
--
-- Single source of truth for a project's "main targets". Rows are created
-- either manually (Overview "+ Add target") or by plate-solve auto-flagging
-- its best-guess main object. The `is_main` flag on the solve response is
-- derived from this table — toggling main on the Plate Solve tab and adding
-- via the Overview edit the same record. The FK is to `project`, not to
-- `project_solve`, so rows survive `DELETE /solve`.

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
