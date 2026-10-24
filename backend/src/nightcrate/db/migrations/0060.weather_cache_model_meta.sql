-- depends: 0059.imaging_rules_precipitation

-- v0.41.9: add 'model_meta' to weather_cache.source.
--
-- The row stores the four Open-Meteo model metadata documents paired with a
-- cloud_models payload. The source vocabulary is a closed CHECK, so SQLite
-- requires a table rebuild. Existing rows and their ids are preserved.

CREATE TABLE weather_cache_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES location(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (
        source IN (
            'forecast', 'archive', 'openmeteo_aq', 'ecmwf_pwv',
            'cloud_models', 'model_meta'
        )
    ),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    response_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(location_id, source, start_date, end_date)
);

INSERT INTO weather_cache_new (id, location_id, source, start_date, end_date, response_json, fetched_at)
SELECT id, location_id, source, start_date, end_date, response_json, fetched_at
FROM weather_cache;

DROP TABLE weather_cache;

ALTER TABLE weather_cache_new RENAME TO weather_cache;
