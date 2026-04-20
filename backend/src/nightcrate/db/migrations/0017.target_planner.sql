-- Target Planner thumbnail cache (v0.16.0).
--
-- Thumbnails are fetched from CDS Aladin's hips2fits service for the
-- DSO catalog's rows (DSS2 Color primary, DSS2 red fallback) and stored
-- as JPEGs under APP_DIR/thumbnails/. This table is the metadata side of
-- the cache — one row per cached thumbnail.
--
-- Eviction is LRU over last_access_at; the thumbnail service enforces a
-- total-size budget on every successful fetch. fetch_error rows record
-- a failed attempt so the same DSO doesn't restart a refetch storm; the
-- service treats them as "don't retry for ~1 hour from fetched_at".

-- depends: 0016.dso_augmentation

CREATE TABLE IF NOT EXISTS thumbnail_cache (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    dso_id         INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    variant        TEXT    NOT NULL CHECK (variant IN ('list', 'detail')),
    width          INTEGER NOT NULL,
    height         INTEGER NOT NULL,
    file_path      TEXT    NOT NULL UNIQUE,
    source         TEXT    NOT NULL CHECK (source IN (
        'dss2_color', 'dss2_red', 'dss2_blue', 'placeholder'
    )),
    bytes          INTEGER NOT NULL,
    fetched_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    last_access_at TEXT    NOT NULL DEFAULT (datetime('now')),
    fetch_error    TEXT,
    UNIQUE (dso_id, variant, width, height)
);

CREATE INDEX IF NOT EXISTS idx_thumbnail_cache_last_access
    ON thumbnail_cache(last_access_at);

CREATE INDEX IF NOT EXISTS idx_thumbnail_cache_dso
    ON thumbnail_cache(dso_id);
