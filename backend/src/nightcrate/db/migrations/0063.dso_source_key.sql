-- Stable source identity for in-place DSO catalog reconciliation.
-- depends: 0062.imaging_rules_cloud_models

ALTER TABLE dso ADD COLUMN source_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_dso_source_key
    ON dso(source_catalog_id, source_key)
    WHERE source_key IS NOT NULL;

ALTER TABLE dso_catalog_source
    ADD COLUMN keys_assigned INTEGER NOT NULL DEFAULT 0
    CHECK (keys_assigned IN (0, 1));
