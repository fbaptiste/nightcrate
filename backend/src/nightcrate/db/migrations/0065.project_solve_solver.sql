-- Record which solver produced each saved project solution and its native metrics.
-- depends: 0064.project_solve_row_order

ALTER TABLE project_solve
    ADD COLUMN solver TEXT NOT NULL DEFAULT 'astap'
    CHECK (solver IN ('native', 'astap'));
ALTER TABLE project_solve ADD COLUMN star_catalog TEXT;
ALTER TABLE project_solve ADD COLUMN stars_detected INTEGER;
ALTER TABLE project_solve ADD COLUMN stars_matched INTEGER;
ALTER TABLE project_solve ADD COLUMN rms_px REAL;
ALTER TABLE project_solve ADD COLUMN log_odds REAL;
ALTER TABLE project_solve ADD COLUMN solve_path TEXT;
ALTER TABLE project_solve ADD COLUMN scale_stage TEXT;

