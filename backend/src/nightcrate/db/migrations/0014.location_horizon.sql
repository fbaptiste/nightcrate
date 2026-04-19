-- Custom horizon per location. One horizon per location, enforced by
-- UNIQUE on location_id. Points cascade-delete with the horizon and
-- the parent location. A soft-deleted location keeps its horizon
-- (the horizon becomes inaccessible until the location is restored).

-- depends: 0013.rig_summary_adc_depth

CREATE TABLE location_horizon (
    id              INTEGER PRIMARY KEY,
    location_id     INTEGER NOT NULL UNIQUE REFERENCES location(id) ON DELETE CASCADE,
    source          TEXT NOT NULL CHECK (source IN ('imported', 'drawn')),
    source_filename TEXT,
    notes           TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at      TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE location_horizon_point (
    horizon_id      INTEGER NOT NULL REFERENCES location_horizon(id) ON DELETE CASCADE,
    azimuth_deg     REAL NOT NULL CHECK (azimuth_deg >= 0 AND azimuth_deg < 360),
    altitude_deg    REAL NOT NULL CHECK (altitude_deg >= -5 AND altitude_deg <= 90),
    PRIMARY KEY (horizon_id, azimuth_deg)
);

CREATE INDEX idx_location_horizon_point_azimuth
    ON location_horizon_point (horizon_id, azimuth_deg);
