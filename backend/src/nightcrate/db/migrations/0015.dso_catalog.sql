-- Deep-sky object catalog (v0.14.0 MVP).
--
-- One canonical `dso` row per physical object. `dso_designation` attaches
-- catalog-specific identifiers (NGC/IC/Messier/Caldwell/etc.) to the DSO
-- it names — same shape as camera ↔ camera_alias. `dso_catalog_source`
-- registers which file each row came from and carries the content hash
-- used for change detection on reload.
--
-- All three tables are loader-populated (no INSERTs in this migration).
-- The CHECK vocabularies are deliberately closed: unknown obj_types fall
-- through to 'Other' + raw_obj_type, unknown catalog prefixes are dropped
-- from designations but preserved on dso.raw_other_id for future re-parsing.

-- depends: 0014.location_horizon

CREATE TABLE dso_catalog_source (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     TEXT NOT NULL UNIQUE,
    category      TEXT NOT NULL CHECK (category IN ('openngc', 'vizier', 'nightcrate')),
    display_name  TEXT NOT NULL,
    version       TEXT,
    source_url    TEXT,
    file_path     TEXT NOT NULL,
    file_hash     TEXT NOT NULL,
    license       TEXT,
    attribution   TEXT,
    loaded_at     TEXT NOT NULL DEFAULT (datetime('now')),
    row_count     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE dso (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,

    primary_designation     TEXT NOT NULL,

    obj_type                TEXT NOT NULL CHECK (obj_type IN (
        'G', 'GPair', 'GTrpl', 'GGroup',
        'HII', 'EmN', 'RfN', 'PN', 'OCl', 'GCl', 'Cl+N', 'SNR', 'DrkN', 'Neb',
        '*Ass', 'Nova', '*', '**', 'Other'
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

    -- Editorial fields reserved for v0.15+ augmentation CSV; unused now.
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
    active                  INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE INDEX idx_dso_obj_type            ON dso(obj_type);
CREATE INDEX idx_dso_constellation       ON dso(constellation);
CREATE INDEX idx_dso_primary_designation ON dso(primary_designation);
CREATE INDEX idx_dso_source_catalog      ON dso(source_catalog_id);

CREATE TRIGGER trg_dso_updated_at
AFTER UPDATE ON dso
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE dso SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE dso_designation (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dso_id        INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    catalog       TEXT NOT NULL CHECK (catalog IN (
        'ngc', 'ic', 'messier', 'caldwell', 'ugc', 'pgc', 'mcg', 'eso',
        'arp', 'hickson', 'sharpless2', 'barnard', 'ldn', 'lbn', 'vdb',
        'cederblad', 'pk', 'rcw', 'gum', 'mrk', 'terzan', 'pal', 'mel',
        'cr', 'stock', 'ruprecht', 'abell', 'dolidze', 'dwb'
    )),
    identifier    TEXT NOT NULL,
    display_form  TEXT NOT NULL,
    search_key    TEXT NOT NULL,
    is_primary    INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    UNIQUE (catalog, identifier)
);

CREATE INDEX idx_dso_designation_dso         ON dso_designation(dso_id);
CREATE INDEX idx_dso_designation_search_key  ON dso_designation(search_key);
CREATE UNIQUE INDEX idx_dso_designation_primary_per_dso
    ON dso_designation(dso_id) WHERE is_primary = 1;
