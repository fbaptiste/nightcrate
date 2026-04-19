-- depends: 0011.settings_kv
--
-- Add soft-delete column to `location` so deletes are reversible, matching
-- the pattern used by every equipment table. Pre-empts the v0.13+ session
-- ingestion pipeline: once sessions reference location_id, hard-deleting a
-- location would cascade into data loss. Soft-delete is the safer contract.

ALTER TABLE location
    ADD COLUMN active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1));

CREATE INDEX IF NOT EXISTS idx_location_active ON location(active);
