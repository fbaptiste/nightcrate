-- depends: 0056.source_folder_target

-- v0.41.5: add 'cloud_models' to weather_cache.source.
--
-- The multi-model cloud request (ECMWF + GFS + ICON in one call) is a second,
-- separate Open-Meteo response and so needs its own cache row. `source` is a
-- closed CHECK vocabulary, and SQLite cannot alter a CHECK in place, so the
-- table is rebuilt.
--
-- Existing rows are carried over rather than dropped. They would re-fetch
-- harmlessly on the next request, but a forecast refetch for every location on
-- upgrade is a needless burst of API calls.

CREATE TABLE weather_cache_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES location(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (
        source IN ('forecast', 'archive', 'openmeteo_aq', 'ecmwf_pwv', 'cloud_models')
    ),
    start_date TEXT NOT NULL,       -- ISO date YYYY-MM-DD
    end_date TEXT NOT NULL,         -- ISO date YYYY-MM-DD
    response_json TEXT NOT NULL,    -- raw Open-Meteo JSON
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(location_id, source, start_date, end_date)
);

INSERT INTO weather_cache_new (id, location_id, source, start_date, end_date, response_json, fetched_at)
SELECT id, location_id, source, start_date, end_date, response_json, fetched_at
FROM weather_cache;

DROP TABLE weather_cache;

ALTER TABLE weather_cache_new RENAME TO weather_cache;
