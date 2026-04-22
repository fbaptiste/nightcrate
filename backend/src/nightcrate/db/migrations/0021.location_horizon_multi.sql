-- Multiple horizons per location: one optional custom polyline horizon
-- plus zero or more named "artificial" flat-altitude horizons. Exactly
-- one row per location carries ``is_default=1`` (enforced by the
-- partial unique index). A 0° artificial default is auto-seeded for
-- every location that has no horizons after the reshape.

-- depends: 0020.sky_tile_cache

-- SQLite 3.26+ rewrites foreign-key references when you ALTER TABLE
-- RENAME, which we do NOT want here: we're dropping the old parent
-- table entirely and replacing it with a new shape. Turn FK
-- enforcement off for the reshape, then rebuild everything with
-- fresh FKs that point at the new location_horizon.
PRAGMA foreign_keys = OFF;

-- Snapshot the old single-horizon shape under a temporary name.
ALTER TABLE location_horizon RENAME TO _location_horizon_legacy;
ALTER TABLE location_horizon_point RENAME TO _location_horizon_point_legacy;

CREATE TABLE location_horizon (
    id                  INTEGER PRIMARY KEY,
    location_id         INTEGER NOT NULL REFERENCES location(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    -- 'custom'     → polyline points live in location_horizon_point
    -- 'artificial' → flat floor, flat_altitude_deg required
    type                TEXT NOT NULL CHECK (type IN ('custom', 'artificial')),
    flat_altitude_deg   REAL,
    -- Provenance for custom horizons: 'imported' from a file, 'drawn' in
    -- the editor. NULL for artificial horizons.
    source              TEXT CHECK (source IS NULL OR source IN ('imported', 'drawn')),
    source_filename     TEXT,
    notes               TEXT,
    is_default          INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    created_at          TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at          TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    CHECK (
        (type = 'custom' AND flat_altitude_deg IS NULL) OR
        (type = 'artificial' AND flat_altitude_deg >= -5 AND flat_altitude_deg <= 90 AND source IS NULL)
    ),
    UNIQUE (location_id, name)
);

-- Exactly one default per location.
CREATE UNIQUE INDEX idx_location_horizon_default
    ON location_horizon (location_id) WHERE is_default = 1;

-- One custom horizon per location — matches the editor UX.
CREATE UNIQUE INDEX idx_location_horizon_one_custom
    ON location_horizon (location_id) WHERE type = 'custom';

-- Drop the legacy index name before recreating it on the new table
-- (the ALTER TABLE RENAME above keeps the index attached to the now-
-- renamed legacy table, but its name is still taken in the DB-wide
-- index namespace).
DROP INDEX IF EXISTS idx_location_horizon_point_azimuth;

-- Recreate location_horizon_point with an FK that points at the NEW
-- location_horizon. Copy the old rows across unchanged.
CREATE TABLE location_horizon_point (
    horizon_id      INTEGER NOT NULL REFERENCES location_horizon(id) ON DELETE CASCADE,
    azimuth_deg     REAL NOT NULL CHECK (azimuth_deg >= 0 AND azimuth_deg < 360),
    altitude_deg    REAL NOT NULL CHECK (altitude_deg >= -5 AND altitude_deg <= 90),
    PRIMARY KEY (horizon_id, azimuth_deg)
);
CREATE INDEX idx_location_horizon_point_azimuth
    ON location_horizon_point (horizon_id, azimuth_deg);

-- Carry existing custom horizons forward. Each legacy row keeps its
-- id so the point rows we copy over still reference a valid parent.
INSERT INTO location_horizon (
    id, location_id, name, type, flat_altitude_deg,
    source, source_filename, notes, is_default, created_at, updated_at
)
SELECT
    id,
    location_id,
    'Custom horizon',
    'custom',
    NULL,
    source,
    source_filename,
    notes,
    1,
    created_at,
    updated_at
FROM _location_horizon_legacy;

INSERT INTO location_horizon_point (horizon_id, azimuth_deg, altitude_deg)
SELECT horizon_id, azimuth_deg, altitude_deg
FROM _location_horizon_point_legacy;

-- Seed a 0° artificial default for every location that had no horizon.
INSERT INTO location_horizon (
    location_id, name, type, flat_altitude_deg, is_default
)
SELECT
    l.id,
    '0° flat',
    'artificial',
    0,
    1
FROM location l
WHERE l.id NOT IN (SELECT location_id FROM location_horizon);

DROP TABLE _location_horizon_point_legacy;
DROP TABLE _location_horizon_legacy;

PRAGMA foreign_keys = ON;
