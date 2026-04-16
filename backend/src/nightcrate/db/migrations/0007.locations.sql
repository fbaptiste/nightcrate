-- depends: 0006.camera_guide_sensor

-- User-defined imaging locations for weather, session planning, and moon phase.

CREATE TABLE IF NOT EXISTS location (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    elevation_m REAL,
    timezone TEXT NOT NULL,
    geo_timezone TEXT,
    bortle_class INTEGER CHECK (bortle_class BETWEEN 1 AND 9),
    sqm_reading REAL CHECK (sqm_reading BETWEEN 10 AND 25),
    city TEXT,
    state_province TEXT,
    country TEXT,
    postal_code TEXT,
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS trg_location_updated_at
AFTER UPDATE ON location
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE location SET updated_at = datetime('now') WHERE id = NEW.id;
END;
