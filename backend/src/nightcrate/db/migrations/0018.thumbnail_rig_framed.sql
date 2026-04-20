-- Target Planner Pass B — rig-framed + FOV-simulator thumbnail variants.
--
-- Two changes to thumbnail_cache:
--   1. Widen the variant CHECK vocabulary to include 'rig_framed' and
--      'fov_simulator'.
--   2. Add FOV descriptor columns (fov_major_deg_x1000, fov_minor_deg_x1000)
--      so that two different rigs with different sensor FOVs get separate
--      cache entries. Storing as int-deg × 1000 keeps the unique key safe
--      from floating-point equality pitfalls and gives ~0.001° precision.
--
-- SQLite doesn't support ALTER TABLE MODIFY CONSTRAINT, so we rebuild the
-- table via the standard rename-then-copy pattern. We also take this
-- opportunity to start the cache clean — Pass A's detail variant is being
-- resized to a wider angular extent (Pass B §3.3), so any cached 600×600
-- entries are stale. Dropping the table wipes both the rows and leaves
-- every on-disk file orphaned; the planner_cache_sync helper invoked at
-- app startup sweeps the orphans on the next boot.
--
-- (Pan/sky-region columns ship in 0019 — this migration was already
-- applied to dev databases when pan arrived, so the extension had to
-- be additive rather than in-place editing.)
--
-- Depends: 0017.target_planner

DROP TABLE IF EXISTS thumbnail_cache;

CREATE TABLE thumbnail_cache (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    dso_id               INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    variant              TEXT    NOT NULL CHECK (variant IN (
        'list', 'detail', 'rig_framed', 'fov_simulator'
    )),
    width                INTEGER NOT NULL,
    height               INTEGER NOT NULL,
    -- Rounded deg × 1000 for rig-dependent variants; NULL otherwise.
    fov_major_deg_x1000  INTEGER,
    fov_minor_deg_x1000  INTEGER,
    file_path            TEXT    NOT NULL UNIQUE,
    source               TEXT    NOT NULL CHECK (source IN (
        'dss2_color', 'dss2_red', 'dss2_blue', 'placeholder'
    )),
    bytes                INTEGER NOT NULL,
    fetched_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    last_access_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    fetch_error          TEXT
);

-- Unique key spans the FOV descriptor via COALESCE so rig-independent
-- variants (list, detail) don't collide on NULL.
CREATE UNIQUE INDEX idx_thumbnail_cache_unique
    ON thumbnail_cache(
        dso_id,
        variant,
        width,
        height,
        COALESCE(fov_major_deg_x1000, -1),
        COALESCE(fov_minor_deg_x1000, -1)
    );

CREATE INDEX idx_thumbnail_cache_last_access
    ON thumbnail_cache(last_access_at);
CREATE INDEX idx_thumbnail_cache_dso
    ON thumbnail_cache(dso_id);
