-- 0047: make `rig` a seedable table so all-in-one smart telescopes can ship
-- ready to use.
--
-- Rigs have always been purely user records. An all-in-one smart telescope is
-- the one case where that is wrong: its optics, camera and filter changer are
-- fixed and inseparable, so there is nothing for the user to assemble — the
-- rig IS the product. Seeding those saves every owner of a Seestar or DWARF
-- from hand-building a rig whose every field is already known.
--
-- Same three columns and the same partial unique index every other seeded
-- table carries, so the loader's user-modified check (current_hash vs
-- stored_hash) works here exactly as it does elsewhere: a seeded rig the user
-- edits is never overwritten again, and `source = 'user'` rigs are never
-- touched at all.
--
-- ALTER TABLE ADD COLUMN is used rather than a table rebuild: rig is the
-- parent of rig_filter_slot and is referenced by sub_frame.rig_id and
-- project_rig, and a rename-rebuild would drag those FKs to the legacy table.

ALTER TABLE rig ADD COLUMN source TEXT NOT NULL DEFAULT 'user'
    CHECK (source IN ('seed', 'user'));
ALTER TABLE rig ADD COLUMN seed_key TEXT;
ALTER TABLE rig ADD COLUMN seed_hash TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_rig_seed_key
    ON rig(seed_key) WHERE seed_key IS NOT NULL;
