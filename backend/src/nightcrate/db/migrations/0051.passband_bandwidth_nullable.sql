-- v0.41.1 — allow a passband with no bandwidth.
--
-- A filter's emission line is public knowledge; its bandwidth often isn't.
-- DwarfLab publishes the DWARF dual-band's lines (Ha 656.3, OIII 500.7) and
-- not their widths, and a user entering their own filter may well know it
-- passes Ha without knowing to how many nanometres. Requiring the number meant
-- the choice was to invent one or record nothing, and an invented width feeds
-- the per-line moon-sensitivity model and is wrong quietly.
--
-- central_wavelength_nm stays NOT NULL: it is what identifies the passband, and
-- for an emission line it follows from line_name.
--
-- SQLite can't relax NOT NULL in place, so this is the standard rebuild. Same
-- shape as 0031, with one addition it didn't need: the filter_summary view
-- reads filter_passband, and a view is NOT just resolved by name at query time
-- here — ALTER TABLE ... RENAME rewrites references inside existing views, and
-- doing that while the original table is already dropped leaves filter_summary
-- pointing at nothing ("no such table: main.filter_passband"). So the view is
-- dropped up front and recreated afterwards, per SQLite's own ALTER procedure.

PRAGMA foreign_keys = OFF;

DROP VIEW IF EXISTS filter_summary;

CREATE TABLE filter_passband_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filter_id INTEGER NOT NULL REFERENCES filter(id) ON DELETE CASCADE,
    line_name TEXT NOT NULL CHECK (line_name IN (
        'Ha', 'Hb', 'Oiii', 'Sii', 'Nii', 'OI',
        'Lum', 'R', 'G', 'B', 'R+',
        'UVIR', 'LP', 'ND', 'other'
    )),
    central_wavelength_nm REAL NOT NULL CHECK (central_wavelength_nm > 0),
    -- Nullable, but still positive when given.
    bandwidth_nm REAL CHECK (bandwidth_nm IS NULL OR bandwidth_nm > 0),
    peak_transmission_pct REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed', 'user')),
    seed_key TEXT,
    seed_hash TEXT
);

INSERT INTO filter_passband_new SELECT * FROM filter_passband;
DROP TABLE filter_passband;
ALTER TABLE filter_passband_new RENAME TO filter_passband;

CREATE INDEX IF NOT EXISTS idx_filter_passband_filter ON filter_passband(filter_id);
CREATE INDEX IF NOT EXISTS idx_filter_passband_line ON filter_passband(line_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_filter_passband_seed_key
    ON filter_passband(seed_key) WHERE seed_key IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_filter_passband_updated_at
AFTER UPDATE ON filter_passband
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE filter_passband SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE VIEW filter_summary AS
SELECT
    f.id AS filter_id,
    f.model_name,
    f.manufacturer_id,
    f.filter_type_id,
    ft.name AS filter_type_name,
    COUNT(fp.id) AS passband_count,
    MIN(fp.central_wavelength_nm) AS min_wavelength_nm,
    MAX(fp.central_wavelength_nm) AS max_wavelength_nm,
    MIN(fp.bandwidth_nm) AS min_bandwidth_nm,
    MAX(fp.bandwidth_nm) AS max_bandwidth_nm,
    GROUP_CONCAT(fp.line_name, '+') AS passband_lines
FROM filter f
JOIN filter_type ft ON ft.id = f.filter_type_id
LEFT JOIN filter_passband fp ON fp.filter_id = f.id
WHERE f.active = 1
GROUP BY f.id;

PRAGMA foreign_keys = ON;
