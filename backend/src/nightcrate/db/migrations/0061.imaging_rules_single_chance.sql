-- depends: 0060.weather_cache_model_meta

-- v0.41.9: use one precipitation-chance limit for every forecast hour.
-- Preserve saved rules and timestamps while dropping the superseded second limit.

DROP TRIGGER trg_location_imaging_rules_updated_at;

CREATE TABLE location_imaging_rules_new (
    location_id INTEGER PRIMARY KEY REFERENCES location(id) ON DELETE CASCADE,
    session_style TEXT NOT NULL CHECK (session_style IN ('all_night', 'short_session')),
    min_clear_fraction_pct REAL NOT NULL
        CHECK (min_clear_fraction_pct >= 1 AND min_clear_fraction_pct <= 100),
    min_clear_hours REAL NOT NULL CHECK (min_clear_hours >= 0),
    max_cloudy_gap_hours REAL CHECK (max_cloudy_gap_hours > 0),
    short_session_hours REAL NOT NULL
        CHECK (short_session_hours > 0 AND short_session_hours <= 24),
    darkness TEXT NOT NULL CHECK (darkness IN ('astronomical', 'nautical', 'civil')),
    cloud_max_pct REAL NOT NULL CHECK (cloud_max_pct >= 0 AND cloud_max_pct <= 100),
    gear_out_before_sunset_min INTEGER NOT NULL
        CHECK (gear_out_before_sunset_min >= 0 AND gear_out_before_sunset_min <= 240),
    gear_out_after_sunrise_min INTEGER NOT NULL
        CHECK (gear_out_after_sunrise_min >= 0 AND gear_out_after_sunrise_min <= 240),
    rain_max_probability_pct REAL NOT NULL
        CHECK (rain_max_probability_pct >= 0 AND rain_max_probability_pct <= 100),
    rain_amount_threshold_mm REAL NOT NULL CHECK (rain_amount_threshold_mm >= 0),
    rain_forecasts TEXT NOT NULL CHECK (rain_forecasts IN ('main', 'any_model')),
    rain_policy TEXT NOT NULL CHECK (rain_policy IN ('night_off', 'hours_lost')),
    wind_counted INTEGER NOT NULL CHECK (wind_counted IN (0, 1)),
    wind_max_kmh REAL NOT NULL CHECK (wind_max_kmh > 0),
    gust_max_kmh REAL NOT NULL CHECK (gust_max_kmh > 0),
    dew_counted INTEGER NOT NULL CHECK (dew_counted IN (0, 1)),
    dew_min_spread_c REAL NOT NULL CHECK (dew_min_spread_c >= 0),
    moon_must_be_down INTEGER NOT NULL CHECK (moon_must_be_down IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO location_imaging_rules_new (
    location_id,
    session_style,
    min_clear_fraction_pct,
    min_clear_hours,
    max_cloudy_gap_hours,
    short_session_hours,
    darkness,
    cloud_max_pct,
    gear_out_before_sunset_min,
    gear_out_after_sunrise_min,
    rain_max_probability_pct,
    rain_amount_threshold_mm,
    rain_forecasts,
    rain_policy,
    wind_counted,
    wind_max_kmh,
    gust_max_kmh,
    dew_counted,
    dew_min_spread_c,
    moon_must_be_down,
    created_at,
    updated_at
)
SELECT
    location_id,
    session_style,
    min_clear_fraction_pct,
    min_clear_hours,
    max_cloudy_gap_hours,
    short_session_hours,
    darkness,
    cloud_max_pct,
    gear_out_before_sunset_min,
    gear_out_after_sunrise_min,
    rain_max_probability_pct,
    rain_amount_threshold_mm,
    rain_forecasts,
    rain_policy,
    wind_counted,
    wind_max_kmh,
    gust_max_kmh,
    dew_counted,
    dew_min_spread_c,
    moon_must_be_down,
    created_at,
    updated_at
FROM location_imaging_rules;

DROP TABLE location_imaging_rules;
ALTER TABLE location_imaging_rules_new RENAME TO location_imaging_rules;

CREATE TRIGGER trg_location_imaging_rules_updated_at
AFTER UPDATE ON location_imaging_rules
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE location_imaging_rules
    SET updated_at = datetime('now')
    WHERE location_id = NEW.location_id;
END;
