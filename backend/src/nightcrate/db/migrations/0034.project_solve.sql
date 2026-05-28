-- Project plate-solve + identified DSO objects (v0.37.0)
-- depends: 0033.project_image_drop_staged
--
-- A project has at most one plate solve for now (mosaics will relax this).
-- The solve image is standalone — NOT a gallery project_image. Deleting the
-- solve cascades its identified objects (project_dso).

CREATE TABLE IF NOT EXISTS project_solve (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id         INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    image_path         TEXT    NOT NULL,
    image_width        INTEGER NOT NULL,
    image_height       INTEGER NOT NULL,
    -- WCS reference point (ASTAP CRVAL = field centre); also used for display.
    center_ra_deg      REAL    NOT NULL,
    center_dec_deg     REAL    NOT NULL,
    ra_hms             TEXT,
    dec_dms            TEXT,
    pixel_scale_arcsec REAL,
    rotation_deg       REAL,
    fov_width_arcmin   REAL,
    fov_height_arcmin  REAL,
    -- CD matrix + reference pixel, needed to re-project the catalog overlay.
    cd1_1              REAL    NOT NULL,
    cd1_2              REAL    NOT NULL,
    cd2_1              REAL    NOT NULL,
    cd2_2              REAL    NOT NULL,
    crpix1             REAL    NOT NULL,
    crpix2             REAL    NOT NULL,
    solved_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id)
);

CREATE INDEX IF NOT EXISTS idx_project_solve_project ON project_solve(project_id);

CREATE TABLE IF NOT EXISTS project_dso (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    solve_id   INTEGER NOT NULL REFERENCES project_solve(id) ON DELETE CASCADE,
    dso_id     INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    is_main    INTEGER NOT NULL DEFAULT 0 CHECK (is_main IN (0, 1)),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (solve_id, dso_id)
);

CREATE INDEX IF NOT EXISTS idx_project_dso_solve ON project_dso(solve_id);
CREATE INDEX IF NOT EXISTS idx_project_dso_dso ON project_dso(dso_id);
