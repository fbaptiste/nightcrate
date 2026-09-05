-- v0.41.1 — populate the internal filter changers on already-seeded
-- smart-telescope rigs.
--
-- rig_filter_slot is a junction table, and the loader only delete-and-reinserts
-- junction rows for parents it inserted or updated in that run. The five rigs
-- were seeded by 0047 and are unchanged, so their slots would never appear on a
-- database that already exists — only on a fresh one. Same shape as 0024
-- backfilling worm_period_seconds directly for the same reason.
--
-- INSERT OR IGNORE rather than a plain INSERT: both UNIQUE constraints on
-- rig_filter_slot (rig+slot, rig+filter) then make this a no-op wherever the
-- slot is already filled, so a user who assigned their own glass to a claimed
-- rig keeps it.

INSERT OR IGNORE INTO rig_filter_slot (rig_id, filter_id, slot_number)
SELECT r.id, f.id, 1 FROM rig r, filter f
 WHERE r.seed_key = 'rig.zwo.seestar_s50' AND f.seed_key = 'filter.zwo.seestar_uv_ir_cut';

INSERT OR IGNORE INTO rig_filter_slot (rig_id, filter_id, slot_number)
SELECT r.id, f.id, 2 FROM rig r, filter f
 WHERE r.seed_key = 'rig.zwo.seestar_s50' AND f.seed_key = 'filter.zwo.seestar_duo_band';

INSERT OR IGNORE INTO rig_filter_slot (rig_id, filter_id, slot_number)
SELECT r.id, f.id, 3 FROM rig r, filter f
 WHERE r.seed_key = 'rig.zwo.seestar_s50' AND f.seed_key = 'filter.zwo.seestar_dark';

INSERT OR IGNORE INTO rig_filter_slot (rig_id, filter_id, slot_number)
SELECT r.id, f.id, 1 FROM rig r, filter f
 WHERE r.seed_key = 'rig.zwo.seestar_s30' AND f.seed_key = 'filter.zwo.seestar_uv_ir_cut';

INSERT OR IGNORE INTO rig_filter_slot (rig_id, filter_id, slot_number)
SELECT r.id, f.id, 2 FROM rig r, filter f
 WHERE r.seed_key = 'rig.zwo.seestar_s30' AND f.seed_key = 'filter.zwo.seestar_duo_band';

INSERT OR IGNORE INTO rig_filter_slot (rig_id, filter_id, slot_number)
SELECT r.id, f.id, 3 FROM rig r, filter f
 WHERE r.seed_key = 'rig.zwo.seestar_s30' AND f.seed_key = 'filter.zwo.seestar_dark';

INSERT OR IGNORE INTO rig_filter_slot (rig_id, filter_id, slot_number)
SELECT r.id, f.id, 1 FROM rig r, filter f
 WHERE r.seed_key = 'rig.zwo.seestar_s30_pro' AND f.seed_key = 'filter.zwo.seestar_uv_ir_cut';

INSERT OR IGNORE INTO rig_filter_slot (rig_id, filter_id, slot_number)
SELECT r.id, f.id, 2 FROM rig r, filter f
 WHERE r.seed_key = 'rig.zwo.seestar_s30_pro' AND f.seed_key = 'filter.zwo.seestar_duo_band';

INSERT OR IGNORE INTO rig_filter_slot (rig_id, filter_id, slot_number)
SELECT r.id, f.id, 3 FROM rig r, filter f
 WHERE r.seed_key = 'rig.zwo.seestar_s30_pro' AND f.seed_key = 'filter.zwo.seestar_dark';

INSERT OR IGNORE INTO rig_filter_slot (rig_id, filter_id, slot_number)
SELECT r.id, f.id, 1 FROM rig r, filter f
 WHERE r.seed_key = 'rig.dwarflab.dwarf_mini' AND f.seed_key = 'filter.dwarflab.cls';

INSERT OR IGNORE INTO rig_filter_slot (rig_id, filter_id, slot_number)
SELECT r.id, f.id, 2 FROM rig r, filter f
 WHERE r.seed_key = 'rig.dwarflab.dwarf_mini' AND f.seed_key = 'filter.dwarflab.duo_band';

INSERT OR IGNORE INTO rig_filter_slot (rig_id, filter_id, slot_number)
SELECT r.id, f.id, 3 FROM rig r, filter f
 WHERE r.seed_key = 'rig.dwarflab.dwarf_mini' AND f.seed_key = 'filter.dwarflab.dark';
