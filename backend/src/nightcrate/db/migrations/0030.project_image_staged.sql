-- Add staging flag to project_image (v0.35.0)
-- depends: 0029.project

ALTER TABLE project_image ADD COLUMN staged INTEGER NOT NULL DEFAULT 0 CHECK (staged IN (0, 1));
