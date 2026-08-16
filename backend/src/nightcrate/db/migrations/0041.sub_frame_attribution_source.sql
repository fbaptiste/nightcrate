-- v0.41.0 — per-field attribution source on sub_frame.
-- 'auto' = set by the resolver / rig-attribution pass (a re-run may overwrite);
-- 'user' = set by a manual override (automated passes must never clobber it).
-- Only the three user-overridable attributions carry a source column; telescope
-- stays purely automated. Existing rows default to 'auto' (everything so far
-- was resolver-written).
ALTER TABLE sub_frame ADD COLUMN rig_source TEXT NOT NULL DEFAULT 'auto'
    CHECK (rig_source IN ('auto', 'user'));
ALTER TABLE sub_frame ADD COLUMN camera_source TEXT NOT NULL DEFAULT 'auto'
    CHECK (camera_source IN ('auto', 'user'));
ALTER TABLE sub_frame ADD COLUMN filter_source TEXT NOT NULL DEFAULT 'auto'
    CHECK (filter_source IN ('auto', 'user'));
