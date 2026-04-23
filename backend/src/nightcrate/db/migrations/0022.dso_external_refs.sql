-- External references for DSOs: Wikidata QIDs, Wikipedia article links,
-- and future NED/SIMBAD/Astrobin/etc. One row per (dso, provider, language).
--
-- Populated by two loaders:
--   * catalog_loader/wikidata_loader.py   — bulk SPARQL fetch
--   * catalog_loader/external_refs_loader.py — editorial CSV overrides
--
-- Migration also widens the dso_catalog_source.category CHECK to include
-- 'wikidata'. The existing values ('openngc', 'vizier', 'nightcrate') stay
-- valid; widening a CHECK on SQLite requires the standard table-rewrite
-- pattern (copy → drop → rename).

-- depends: 0021.location_horizon_multi

PRAGMA foreign_keys = OFF;
-- SQLite 3.25+ rewrites foreign-key references in CHILD tables when you
-- rename the parent — so ``dso.source_catalog_id`` would follow this
-- rename to ``_dso_catalog_source_legacy`` and dangle after DROP. The
-- ``legacy_alter_table`` pragma restores pre-3.25 behaviour (rename
-- leaves child FKs untouched) for the duration of this migration.
PRAGMA legacy_alter_table = ON;

-- ── Widen dso_catalog_source.category CHECK ─────────────────────────────
--
-- 0015's CHECK admitted only openngc | vizier | nightcrate. Widen to
-- include 'wikidata'. SQLite can't ALTER a CHECK in place; table-rewrite
-- is the only path.

ALTER TABLE dso_catalog_source RENAME TO _dso_catalog_source_legacy;

CREATE TABLE dso_catalog_source (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     TEXT NOT NULL UNIQUE,
    category      TEXT NOT NULL CHECK (category IN ('openngc', 'vizier', 'nightcrate', 'wikidata')),
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

INSERT INTO dso_catalog_source (
    id, source_id, category, display_name, version, source_url, file_path,
    file_hash, license, attribution, loaded_at, row_count
)
SELECT
    id, source_id, category, display_name, version, source_url, file_path,
    file_hash, license, attribution, loaded_at, row_count
FROM _dso_catalog_source_legacy;

DROP TABLE _dso_catalog_source_legacy;

PRAGMA legacy_alter_table = OFF;

-- ── New table: dso_external_ref ─────────────────────────────────────────

CREATE TABLE dso_external_ref (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    dso_id            INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
    provider          TEXT NOT NULL CHECK (provider IN ('wikidata', 'wikipedia')),
    -- NULL for language-agnostic providers (wikidata, future NED/SIMBAD/etc.).
    -- Required for wikipedia. Loader enforces; CHECK does not express the
    -- coupling to avoid an unwieldy expression.
    language          TEXT,
    identifier        TEXT NOT NULL,
    url               TEXT,
    label             TEXT,
    source_catalog_id INTEGER REFERENCES dso_catalog_source(id),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    -- One row per DSO per provider per language. Prevents accidental
    -- duplicates (e.g., two Wikidata QIDs on one DSO).
    UNIQUE (dso_id, provider, language)
);

CREATE INDEX idx_dso_external_ref_dso
    ON dso_external_ref(dso_id);

CREATE INDEX idx_dso_external_ref_provider
    ON dso_external_ref(provider, identifier);

-- ``UNIQUE(dso_id, provider, language)`` above does NOT enforce
-- uniqueness when ``language IS NULL`` because SQLite treats all NULLs
-- as distinct inside a unique index. This partial unique index covers
-- the language-agnostic providers (wikidata today; future NED / SIMBAD
-- / etc.), ensuring at most one row per ``(dso_id, provider)`` when
-- language is NULL.
CREATE UNIQUE INDEX idx_dso_external_ref_langless_unique
    ON dso_external_ref(dso_id, provider)
    WHERE language IS NULL;

-- NOTE: No global uniqueness constraint on (provider, language,
-- identifier). A single external resource may legitimately point at
-- multiple NightCrate DSOs:
--   * Wikipedia: multi-object articles (Stephan's Quintet → 5 galaxies).
--   * Wikidata: per-catalog splits in OpenNGC (NGC 1316 + PGC 12769 are
--     the same physical galaxy in two DSO rows; Crab Nebula has NGC 1952
--     and Sh2-244 entries; California Nebula has NGC 1499 and Sh2-220).
-- The loader duplicates the ref onto every matching DSO so a user
-- viewing any of them sees the Wikipedia / Wikidata chip.

CREATE TRIGGER trg_dso_external_ref_updated_at
AFTER UPDATE ON dso_external_ref
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE dso_external_ref SET updated_at = datetime('now') WHERE id = NEW.id;
END;

PRAGMA foreign_keys = ON;
