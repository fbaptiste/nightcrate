-- v0.41.1 — drop the equipment-alias queue and the per-filter integration goals.
--
-- Destructive half of the pair (0044 is the additive one). Removes two features:
--
-- 1. Integration GOALS. project_filter_goal held a per-project target of N minutes
--    per bandpass and the UI tracked sessions against it. The integration bars
--    stay, showing per-filter totals only. project_filter_goal_progress must be
--    dropped BEFORE its table.
--
-- 2. The equipment ALIAS machinery. camera_alias / telescope_alias / filter_alias
--    mapped FITS header strings to equipment rows, and
--    unresolved_equipment_observation was the Admin review queue for strings that
--    didn't match. All three alias CSVs shipped empty and the queue bootstrapped
--    on first ingest, so the only data lost is aliases a user confirmed by hand.
--    None of the four tables is referenced by a foreign key (they point AT
--    camera/telescope/filter, never the reverse), so the drops are unconstrained.
--
-- The three sub_frame *_source columns go with the per-frame equipment override
-- they guarded. DROP COLUMN is safe for all three: SQLite refuses it only when the
-- column is a PK/UNIQUE, indexed, or named in a view or trigger, and none of them
-- is any of those. Their column-level CHECK is folded into the column definition
-- and removed with it. (Requires SQLite >= 3.35; the repo already requires 3.25+.)
-- The classification source columns from 0043 (frame_type_source,
-- project_target_source) are NOT affected — hand-correcting a frame's type or
-- target stays.
--
-- TEMPORARILY DEAD after this migration, fixed by 0046: matching_darks,
-- matching_flats, matching_bias, calibration_coverage and
-- integration_time_per_project_filter all join on sub_frame.camera_id / filter_id,
-- which 0044 cleared, so they return no rows between this migration and the next.
-- 0046 re-keys them on header facts (exposure, gain, binning, set temp,
-- filter_name_hint) scoped to project + rig, and drops the integration view.

DROP VIEW IF EXISTS project_filter_goal_progress;
DROP TABLE IF EXISTS project_filter_goal;

DROP TABLE IF EXISTS unresolved_equipment_observation;
DROP TABLE IF EXISTS camera_alias;
DROP TABLE IF EXISTS telescope_alias;
DROP TABLE IF EXISTS filter_alias;

ALTER TABLE sub_frame DROP COLUMN rig_source;
ALTER TABLE sub_frame DROP COLUMN camera_source;
ALTER TABLE sub_frame DROP COLUMN filter_source;
