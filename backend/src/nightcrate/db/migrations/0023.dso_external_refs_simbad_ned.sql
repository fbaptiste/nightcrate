-- Widen dso_external_ref.provider CHECK to admit two new providers:
--   * 'simbad' — CDS SIMBAD reference database (full sky)
--   * 'ned'    — NASA/IPAC Extragalactic Database (galaxies only)
--
-- Both are language-agnostic (like wikidata) — loaders insert with
-- language=NULL. The partial unique index on (dso_id, provider) WHERE
-- language IS NULL (created in 0022) already covers them without
-- change.
--
-- SQLite can't ALTER a CHECK in place — same table-rewrite pattern as
-- 0022. No data changes, just widens the domain.

-- depends: 0022.dso_external_refs

PRAGMA foreign_keys = OFF;
-- SQLite 3.25+ rewrites foreign-key references in CHILD tables when you
-- rename the parent — so any FK pointing at dso_external_ref would
-- follow this rename to _dso_external_ref_legacy and dangle after DROP.
-- No FK currently references dso_external_ref, but setting this pragma
-- keeps the migration safe against future children + matches 0022's
-- precedent.
PRAGMA legacy_alter_table = ON;

ALTER TABLE dso_external_ref RENAME TO _dso_external_ref_legacy;

CREATE TABLE dso_external_ref (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    dso_id            INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    provider          TEXT NOT NULL CHECK (provider IN ('wikidata', 'wikipedia', 'simbad', 'ned')),
    language          TEXT,
    identifier        TEXT NOT NULL,
    url               TEXT,
    label             TEXT,
    source_catalog_id INTEGER REFERENCES dso_catalog_source(id),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (dso_id, provider, language)
);

INSERT INTO dso_external_ref (
    id, dso_id, provider, language, identifier, url, label,
    source_catalog_id, created_at, updated_at
)
SELECT
    id, dso_id, provider, language, identifier, url, label,
    source_catalog_id, created_at, updated_at
FROM _dso_external_ref_legacy;

DROP TABLE _dso_external_ref_legacy;

PRAGMA legacy_alter_table = OFF;

-- Indexes + trigger recreated on the new table (the DROP of the legacy
-- table takes its dependent objects with it).

CREATE INDEX idx_dso_external_ref_dso
    ON dso_external_ref(dso_id);

CREATE INDEX idx_dso_external_ref_provider
    ON dso_external_ref(provider, identifier);

CREATE UNIQUE INDEX idx_dso_external_ref_langless_unique
    ON dso_external_ref(dso_id, provider)
    WHERE language IS NULL;

CREATE TRIGGER trg_dso_external_ref_updated_at
AFTER UPDATE ON dso_external_ref
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE dso_external_ref SET updated_at = datetime('now') WHERE id = NEW.id;
END;

PRAGMA foreign_keys = ON;
