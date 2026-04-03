-- depends: 0003.recent_files

CREATE TABLE IF NOT EXISTS aberration_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    hdu INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    image_width INTEGER NOT NULL,
    image_height INTEGER NOT NULL,
    settings_json TEXT NOT NULL,
    star_count INTEGER NOT NULL,
    median_fwhm REAL,
    median_hfr REAL,
    median_eccentricity REAL,
    UNIQUE(file_path, hdu, settings_json)
);

CREATE TABLE IF NOT EXISTS aberration_stars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL REFERENCES aberration_analysis(id) ON DELETE CASCADE,
    x REAL NOT NULL,
    y REAL NOT NULL,
    fwhm REAL NOT NULL,
    hfr REAL NOT NULL,
    eccentricity REAL NOT NULL,
    elongation_angle_deg REAL NOT NULL,
    peak_adu REAL NOT NULL,
    flux REAL NOT NULL,
    snr REAL NOT NULL,
    semi_major REAL NOT NULL,
    semi_minor REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_aberration_stars_analysis
    ON aberration_stars(analysis_id);

CREATE INDEX IF NOT EXISTS idx_aberration_analysis_path
    ON aberration_analysis(file_path, hdu);
