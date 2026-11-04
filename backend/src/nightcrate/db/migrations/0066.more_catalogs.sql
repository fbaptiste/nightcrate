-- Optional DSO catalogs, structured designation vocabularies, and group identity.
-- depends: 0065.project_solve_solver

PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;

ALTER TABLE dso RENAME TO _dso_legacy;

CREATE TABLE dso (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_designation     TEXT NOT NULL,
    obj_type                TEXT NOT NULL CHECK (obj_type IN (
        'G', 'GPair', 'GTrpl', 'GGroup',
        'HII', 'EmN', 'RfN', 'PN', 'OCl', 'GCl', 'Cl+N', 'SNR', 'DrkN', 'Neb',
        '*Ass', 'Nova', '*', '**', 'Other', 'HH', 'ClG', 'WR*'
    )),
    raw_obj_type            TEXT,
    ra_deg                  REAL,
    dec_deg                 REAL,
    constellation           TEXT,
    maj_axis_arcmin         REAL,
    min_axis_arcmin         REAL,
    position_angle_deg      REAL,
    mag_b                   REAL,
    mag_v                   REAL,
    mag_j                   REAL,
    mag_h                   REAL,
    mag_k                   REAL,
    surface_brightness      REAL,
    hubble_type             TEXT,
    pm_ra                   REAL,
    pm_dec                  REAL,
    redshift                REAL,
    radial_velocity         REAL,
    cstar_mag_u             REAL,
    cstar_mag_b             REAL,
    cstar_mag_v             REAL,
    cstar_id                TEXT,
    common_name             TEXT,
    ned_notes               TEXT,
    openngc_notes           TEXT,
    raw_other_id            TEXT,
    popularity_rank         INTEGER,
    difficulty              TEXT CHECK (
        difficulty IS NULL
        OR difficulty IN ('easy', 'moderate', 'challenging', 'extreme')
    ),
    recommended_filter_id   INTEGER REFERENCES filter(id),
    source_catalog_id       INTEGER NOT NULL REFERENCES dso_catalog_source(id),
    source_row_hash         TEXT NOT NULL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now')),
    active                  INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    distance_pc             REAL,
    distance_method         TEXT CHECK (
        distance_method IS NULL OR distance_method IN ('50mgc', 'curated', 'redshift')
    ),
    surface_brightness_augmented INTEGER NOT NULL DEFAULT 0
        CHECK (surface_brightness_augmented IN (0, 1)),
    common_name_augmented   INTEGER NOT NULL DEFAULT 0
        CHECK (common_name_augmented IN (0, 1)),
    source_key              TEXT
);

INSERT INTO dso (
    id, primary_designation, obj_type, raw_obj_type, ra_deg, dec_deg,
    constellation, maj_axis_arcmin, min_axis_arcmin, position_angle_deg,
    mag_b, mag_v, mag_j, mag_h, mag_k, surface_brightness, hubble_type,
    pm_ra, pm_dec, redshift, radial_velocity, cstar_mag_u, cstar_mag_b,
    cstar_mag_v, cstar_id, common_name, ned_notes, openngc_notes,
    raw_other_id, popularity_rank, difficulty, recommended_filter_id,
    source_catalog_id, source_row_hash, created_at, updated_at, active,
    distance_pc, distance_method, surface_brightness_augmented,
    common_name_augmented, source_key
)
SELECT
    id, primary_designation, obj_type, raw_obj_type, ra_deg, dec_deg,
    constellation, maj_axis_arcmin, min_axis_arcmin, position_angle_deg,
    mag_b, mag_v, mag_j, mag_h, mag_k, surface_brightness, hubble_type,
    pm_ra, pm_dec, redshift, radial_velocity, cstar_mag_u, cstar_mag_b,
    cstar_mag_v, cstar_id, common_name, ned_notes, openngc_notes,
    raw_other_id, popularity_rank, difficulty, recommended_filter_id,
    source_catalog_id, source_row_hash, created_at, updated_at, active,
    distance_pc, distance_method, surface_brightness_augmented,
    common_name_augmented, source_key
FROM _dso_legacy;

DROP TABLE _dso_legacy;

CREATE INDEX idx_dso_obj_type            ON dso(obj_type);
CREATE INDEX idx_dso_constellation       ON dso(constellation);
CREATE INDEX idx_dso_primary_designation ON dso(primary_designation);
CREATE INDEX idx_dso_source_catalog      ON dso(source_catalog_id);
CREATE INDEX idx_dso_distance_method
    ON dso(distance_method) WHERE distance_method IS NOT NULL;
CREATE UNIQUE INDEX idx_dso_source_key
    ON dso(source_catalog_id, source_key) WHERE source_key IS NOT NULL;

CREATE TRIGGER trg_dso_updated_at
AFTER UPDATE ON dso
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE dso SET updated_at = datetime('now') WHERE id = NEW.id;
END;

ALTER TABLE dso_designation RENAME TO _dso_designation_legacy;

CREATE TABLE dso_designation (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dso_id        INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    catalog       TEXT NOT NULL CHECK (catalog IN (
        'ngc', 'ic', 'messier', 'caldwell', 'ugc', 'pgc', 'mcg', 'eso',
        'arp', 'hickson', 'sharpless2', 'barnard', 'ldn', 'lbn', 'vdb',
        'cederblad', 'pk', 'rcw', 'gum', 'mrk', 'terzan', 'pal', 'mel',
        'cr', 'stock', 'ruprecht', 'abell', 'dolidze', 'dwb',
        'hh', 'aco', 'png', 'wr'
    )),
    identifier    TEXT NOT NULL,
    display_form  TEXT NOT NULL,
    search_key    TEXT NOT NULL,
    is_primary    INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    UNIQUE (catalog, identifier)
);

INSERT INTO dso_designation (
    id, dso_id, catalog, identifier, display_form, search_key, is_primary
)
SELECT id, dso_id, catalog, identifier, display_form, search_key, is_primary
FROM _dso_designation_legacy;

DROP TABLE _dso_designation_legacy;

CREATE INDEX idx_dso_designation_dso ON dso_designation(dso_id);
CREATE INDEX idx_dso_designation_search_key ON dso_designation(search_key);
CREATE UNIQUE INDEX idx_dso_designation_primary_per_dso
    ON dso_designation(dso_id) WHERE is_primary = 1;

PRAGMA legacy_alter_table = OFF;

CREATE TABLE dso_group (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog       TEXT NOT NULL CHECK (catalog IN (
        'ngc', 'ic', 'messier', 'caldwell', 'ugc', 'pgc', 'mcg', 'eso',
        'arp', 'hickson', 'sharpless2', 'barnard', 'ldn', 'lbn', 'vdb',
        'cederblad', 'pk', 'rcw', 'gum', 'mrk', 'terzan', 'pal', 'mel',
        'cr', 'stock', 'ruprecht', 'abell', 'dolidze', 'dwb',
        'hh', 'aco', 'png', 'wr'
    )),
    identifier    TEXT NOT NULL,
    display_form  TEXT NOT NULL,
    search_key    TEXT NOT NULL,
    whole_dso_id  INTEGER REFERENCES dso(id) ON DELETE CASCADE,
    UNIQUE (catalog, identifier)
);

CREATE TABLE dso_group_member (
    group_id INTEGER NOT NULL REFERENCES dso_group(id) ON DELETE CASCADE,
    dso_id   INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, dso_id)
);

CREATE INDEX idx_dso_group_search_key ON dso_group(search_key);
CREATE INDEX idx_dso_group_member_dso ON dso_group_member(dso_id);

CREATE TABLE dso_source_entry (
    source_catalog_id INTEGER NOT NULL REFERENCES dso_catalog_source(id),
    source_key        TEXT NOT NULL,
    catalog_id        TEXT NOT NULL,
    dso_id            INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    PRIMARY KEY (source_catalog_id, source_key, catalog_id)
);

CREATE INDEX idx_dso_source_entry_dso ON dso_source_entry(dso_id);

CREATE TABLE dso_catalog_applied (
    catalog_id TEXT PRIMARY KEY,
    state      TEXT NOT NULL CHECK (state IN ('on', 'removed')),
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

PRAGMA foreign_keys = ON;
