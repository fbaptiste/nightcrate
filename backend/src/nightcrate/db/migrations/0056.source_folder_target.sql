-- v0.41.3 — a source folder can declare which target it holds.
--
-- The rig is already a declared per-folder fact (migration 0046). The target was
-- not: ingest assigned the project's single target to every light and gave up
-- entirely when a project had more than one. On a project holding two targets
-- that meant nothing got a target at all, and on a single-target project it
-- meant frames of a DIFFERENT object were linked to it regardless — a folder of
-- M 42 subs scanned into a project whose one target is M 101 came out linked to
-- M 101, with the real name sitting unused in object_hint.
--
-- Declaring it per folder follows the same principle as the rig: the user states
-- the fact, nothing is inferred from a header. The OBJECT header stays a hint
-- only, per the arc-wide decision — 'Barnard 144' under a Tulip Nebula project
-- is the standing counter-example to trusting it.
--
-- NULL keeps today's behaviour: fall back to the project's single target.
--
-- ON DELETE SET NULL rather than CASCADE: removing a target from the project
-- must not silently unbind the source folder along with it.
ALTER TABLE project_source_folder
    ADD COLUMN project_target_id INTEGER REFERENCES project_target(id) ON DELETE SET NULL;

CREATE INDEX idx_source_folder_target ON project_source_folder(project_target_id);
