-- v0.48.0 — add the Messier checklist thumbnail variant and render identity.
-- depends: 0070.project_night_notes

ALTER TABLE thumbnail_cache RENAME TO thumbnail_cache_old;

CREATE TABLE thumbnail_cache (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    dso_id               INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    variant              TEXT    NOT NULL CHECK (variant IN (
        'list', 'detail', 'rig_framed', 'fov_simulator', 'checklist'
    )),
    width                INTEGER NOT NULL,
    height               INTEGER NOT NULL,
    fov_major_deg_x1000  INTEGER,
    fov_minor_deg_x1000  INTEGER,
    center_ra_deg_x1000  INTEGER,
    center_dec_deg_x1000 INTEGER,
    render_key           TEXT,
    file_path            TEXT    NOT NULL UNIQUE,
    source               TEXT    NOT NULL CHECK (source IN (
        'dss2_color', 'dss2_red', 'dss2_blue', 'placeholder'
    )),
    bytes                INTEGER NOT NULL,
    fetched_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    last_access_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    fetch_error          TEXT
);

INSERT INTO thumbnail_cache (
    id, dso_id, variant, width, height,
    fov_major_deg_x1000, fov_minor_deg_x1000,
    center_ra_deg_x1000, center_dec_deg_x1000, render_key,
    file_path, source, bytes, fetched_at, last_access_at, fetch_error
)
SELECT
    id, dso_id, variant, width, height,
    fov_major_deg_x1000, fov_minor_deg_x1000,
    center_ra_deg_x1000, center_dec_deg_x1000, NULL,
    file_path, source, bytes, fetched_at, last_access_at, fetch_error
FROM thumbnail_cache_old;

DROP TABLE thumbnail_cache_old;

CREATE UNIQUE INDEX idx_thumbnail_cache_unique
    ON thumbnail_cache(
        dso_id,
        variant,
        width,
        height,
        COALESCE(fov_major_deg_x1000, -1),
        COALESCE(fov_minor_deg_x1000, -1),
        COALESCE(center_ra_deg_x1000, -999999),
        COALESCE(center_dec_deg_x1000, -999999),
        COALESCE(render_key, '')
    );
CREATE INDEX idx_thumbnail_cache_last_access
    ON thumbnail_cache(last_access_at);
CREATE INDEX idx_thumbnail_cache_dso
    ON thumbnail_cache(dso_id);
