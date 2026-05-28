-- Drop the project_image.staged column (v0.37.0)
-- depends: 0032.project_thumbnail
--
-- The project detail page moved from a stage + Save/Cancel model to
-- save-as-you-go: edits (including added images) persist immediately, so
-- the provisional "staged" marker is obsolete. No index references it.

ALTER TABLE project_image DROP COLUMN staged;
