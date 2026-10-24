-- depends: 0058.location_imaging_rules

DROP TRIGGER trg_location_imaging_rules_updated_at;
DROP TABLE location_imaging_rules;

CREATE TABLE location_imaging_rules (
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
    rain_max_period_probability_pct REAL NOT NULL
        CHECK (
            rain_max_period_probability_pct >= 0
            AND rain_max_period_probability_pct <= 100
        ),
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

CREATE TRIGGER trg_location_imaging_rules_updated_at
AFTER UPDATE ON location_imaging_rules
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE location_imaging_rules
    SET updated_at = datetime('now')
    WHERE location_id = NEW.location_id;
END;
