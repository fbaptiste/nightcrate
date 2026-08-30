-- v0.41.1 — derived imaging sessions; retire per-frame equipment attribution.
--
-- Additive half of the pair (0045 does the drops). Two things happen here:
--
-- 1. project_session.filter_label — the header filter name a derived session was
--    grouped on (the normalized short-form stored in sub_frame.filter_name_hint,
--    e.g. "Ha" / "Red" / "L-eXtreme"). A plain ADD COLUMN is enough because a
--    derived row ALSO sets line_name (canonical, or 'other' when the header name
--    isn't a recognized bandpass), so the existing table CHECK
--    "filter_id IS NOT NULL OR line_name IS NOT NULL" still holds and no table
--    rewrite is needed. filter_label carries the truth for display; line_name
--    keeps the integration bars grouping on a closed vocabulary.
--
-- 2. Clearing the equipment attribution that v0.39.0-v0.41.0 wrote. Automatic
--    equipment identification (the FITS header -> equipment-row resolver and the
--    rig-attribution pass) is removed in this version: a project carries its rigs
--    via project_rig, and that is the equipment context. The equipment FK columns
--    are left in place here and merely cleared, so the partially-populated values
--    they hold today aren't left as half-truths. This includes the handful of
--    manual per-frame overrides recorded under migration 0041 — an intentional,
--    one-way loss. NOTE (superseded by migration 0046): 0046 drops those columns
--    outright — calibration matches on header facts, not equipment rows, so
--    keeping their shape bought nothing.
--
--    session.rig_id is cleared here too. NOTE (superseded by migration 0046):
--    per-rig sessions came back, keyed on the rig the USER tags on a source
--    folder rather than one inferred from a header — so session.rig_id and
--    sub_frame.rig_id are live again. Everything else this UPDATE clears stays
--    cleared, and 0046 drops those columns outright.

ALTER TABLE project_session ADD COLUMN filter_label TEXT;

UPDATE session SET rig_id = NULL WHERE rig_id IS NOT NULL;

UPDATE sub_frame SET rig_id = NULL,
                     camera_id = NULL,
                     telescope_id = NULL,
                     telescope_configuration_id = NULL,
                     filter_id = NULL,
                     mount_id = NULL,
                     filter_wheel_id = NULL,
                     focuser_id = NULL;

UPDATE processed_image SET camera_id = NULL,
                           telescope_id = NULL,
                           filter_id = NULL;
