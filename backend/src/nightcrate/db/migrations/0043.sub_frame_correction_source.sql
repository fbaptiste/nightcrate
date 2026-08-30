-- v0.41.1 — per-field source for the two hand-correctable classification fields.
--
-- Same contract as migration 0041's rig/camera/filter source columns: 'auto' =
-- derived by the ingest pipeline (a later pass may overwrite it), 'user' = set
-- by a manual correction, which no automated pass may clobber.
--
-- Both are needed because two passes re-derive these values on EVERY scan:
--   * frame_type      -- api/ingest.py:_reclassify_dark_flats re-runs the
--                        dark -> dark_flat promotion project-wide.
--   * project_target_id -- api/ingest.py:_persist_parsed assigns the project's
--                        single target to each light, and assigns NULL when the
--                        project has zero or several targets, which would wipe a
--                        manual assignment on a multi-target project.
--
-- Existing rows default to 'auto': everything written before v0.41.1 was
-- pipeline-derived.
ALTER TABLE sub_frame ADD COLUMN frame_type_source TEXT NOT NULL DEFAULT 'auto'
    CHECK (frame_type_source IN ('auto', 'user'));
ALTER TABLE sub_frame ADD COLUMN project_target_source TEXT NOT NULL DEFAULT 'auto'
    CHECK (project_target_source IN ('auto', 'user'));
