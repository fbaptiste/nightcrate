-- depends: 0026.rig_sort_order
-- Persist moon filter settings and threshold bar position on plan
-- assignments so they survive navigation and restarts.

ALTER TABLE target_plan ADD COLUMN moon_filter_enabled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE target_plan ADD COLUMN max_illumination_pct INTEGER NOT NULL DEFAULT 50;
ALTER TABLE target_plan ADD COLUMN min_separation_deg INTEGER NOT NULL DEFAULT 60;
ALTER TABLE target_plan ADD COLUMN moon_combine TEXT NOT NULL DEFAULT 'and';
ALTER TABLE target_plan ADD COLUMN threshold_hours REAL NOT NULL DEFAULT 2.0;
