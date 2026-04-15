-- depends: 0007.locations

-- Cache for Open-Meteo API responses.
-- One row per (location, date range, data source) combination.
-- TTL-based cleanup on startup.

CREATE TABLE IF NOT EXISTS weather_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES location(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (source IN ('forecast', 'archive', 'openmeteo_aq', 'ecmwf_pwv')),
    start_date TEXT NOT NULL,       -- ISO date YYYY-MM-DD
    end_date TEXT NOT NULL,         -- ISO date YYYY-MM-DD
    response_json TEXT NOT NULL,    -- raw Open-Meteo JSON
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(location_id, source, start_date, end_date)
);
