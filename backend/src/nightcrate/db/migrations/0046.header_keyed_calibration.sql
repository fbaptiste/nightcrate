-- v0.41.1 — re-key calibration matching on header facts; drop the dead equipment columns.
--
-- Migrations 0044/0045 removed automatic equipment identification but left the
-- equipment FK columns in place, on the theory that v0.42's calibration matching
-- wanted that shape. It doesn't. Calibration matches on capture settings the FITS
-- header already gives us — exposure, gain, binning, set temperature, filter name
-- — and within a project the camera is fixed by the project's rig anyway, so the
-- camera term was near-redundant even when it was populated.
--
-- The old views joined `d.camera_id = l.camera_id` with a plain `=`. Once every
-- camera_id went NULL that comparison is NULL, not TRUE, so the join failed before
-- it ever reached the exposure test and every view returned zero rows. This
-- migration replaces the equipment terms with `project_id` scoping (which the views
-- lacked entirely — flagged by migration 0040, never fixed) plus `filter_name_hint`
-- for flats, and then drops the columns the old shape needed.
--
-- Dropped with them: `integration_time_per_project_filter`. Integration now has a
-- single source of truth — `project_session` rows derived by
-- services/session_derivation.py. A parallel sub-frame-level view keyed on a header
-- string would be a second, subtly different answer to the same question. If v0.42
-- needs per-sub granularity for calibration-aware totals it can add one back
-- deliberately.
--
-- KEPT deliberately: `accepted` / `rejection_reason` / `rejection_source` stay
-- dormant (all frames accepted = 1) per the arc-wide "catalog and correlate, don't
-- curate for processing" decision — the views below still honor them, so an
-- accept/reject UI could return without a migration.
--
-- Dual-rig projects are handled by `project_source_folder.rig_id` (added below)
-- rather than by inference: the user tags each bound folder with the rig that shot
-- it, every frame under that folder inherits it, and the match views scope on it.
-- That restores per-rig session splitting and keeps one rig's darks away from the
-- other's lights — without the pipeline guessing anything from a header.

-- ── Views first: they block DROP COLUMN on any column they name ───────────────
DROP VIEW IF EXISTS calibration_coverage;
DROP VIEW IF EXISTS matching_darks;
DROP VIEW IF EXISTS matching_flats;
DROP VIEW IF EXISTS matching_bias;
DROP VIEW IF EXISTS integration_time_per_project_filter;
DROP VIEW IF EXISTS session_summary;

-- ── Then the indexes over the dead columns ───────────────────────────────────
DROP INDEX IF EXISTS idx_sub_frame_camera;
DROP INDEX IF EXISTS idx_sub_frame_telescope;
DROP INDEX IF EXISTS idx_sub_frame_filter;
DROP INDEX IF EXISTS idx_sub_frame_match_light;
DROP INDEX IF EXISTS idx_sub_frame_match_dark;
DROP INDEX IF EXISTS idx_sub_frame_match_flat;
DROP INDEX IF EXISTS idx_sub_frame_match_bias;
DROP INDEX IF EXISTS idx_processed_image_filter;

-- ── Now the columns themselves (all NULL since 0044; no data is lost) ────────
ALTER TABLE sub_frame DROP COLUMN camera_id;
ALTER TABLE sub_frame DROP COLUMN telescope_id;
ALTER TABLE sub_frame DROP COLUMN telescope_configuration_id;
ALTER TABLE sub_frame DROP COLUMN filter_id;
ALTER TABLE sub_frame DROP COLUMN mount_id;
ALTER TABLE sub_frame DROP COLUMN filter_wheel_id;
ALTER TABLE sub_frame DROP COLUMN focuser_id;

ALTER TABLE processed_image DROP COLUMN camera_id;
ALTER TABLE processed_image DROP COLUMN telescope_id;
ALTER TABLE processed_image DROP COLUMN filter_id;

-- project_source_folder.rig_id — the ONLY equipment fact the ingest records, and the
-- user declares it rather than the pipeline inferring it. Every frame found under a
-- tagged folder inherits it into sub_frame.rig_id, sessions key on (project, night,
-- rig) again so simultaneous dual-rig nights split, and the calibration views below
-- refuse to match a dark from one rig against a light from another.
ALTER TABLE project_source_folder ADD COLUMN rig_id INTEGER REFERENCES rig(id);

-- ── Indexes keyed to the new match predicates ────────────────────────────────
CREATE INDEX idx_sub_frame_match_light
    ON sub_frame(project_id, rig_id, gain, exposure_seconds, binning_x, binning_y)
    WHERE frame_type = 'light' AND accepted = 1;
CREATE INDEX idx_sub_frame_match_dark
    ON sub_frame(project_id, rig_id, gain, exposure_seconds, binning_x, binning_y, set_temp_c)
    WHERE frame_type = 'dark' AND accepted = 1;
CREATE INDEX idx_sub_frame_match_flat
    ON sub_frame(project_id, rig_id, gain, filter_name_hint, binning_x, binning_y)
    WHERE frame_type = 'flat' AND accepted = 1;
CREATE INDEX idx_sub_frame_match_bias
    ON sub_frame(project_id, rig_id, gain, binning_x, binning_y)
    WHERE frame_type = 'bias' AND accepted = 1;

-- ── Rebuilt views ────────────────────────────────────────────────────────────

-- Darks: same exposure, gain and binning, set temperature within ±1.0 °C. Never
-- matched on filter — calibration darks are filterless by definition.
CREATE VIEW matching_darks AS
SELECT l.id AS light_id, d.id AS dark_id
FROM sub_frame l
JOIN sub_frame d
    ON  d.frame_type = 'dark' AND d.accepted = 1
    AND d.project_id = l.project_id
    AND d.rig_id IS l.rig_id
    AND d.gain IS l.gain
    AND d.exposure_seconds = l.exposure_seconds
    AND d.binning_x IS l.binning_x
    AND d.binning_y IS l.binning_y
    AND (
        (d.set_temp_c IS NULL AND l.set_temp_c IS NULL)
        OR ABS(d.set_temp_c - l.set_temp_c) <= 1.0
    )
WHERE l.frame_type = 'light' AND l.accepted = 1;

-- Flats: same gain, binning and FILTER header. Not matched on exposure — a flat's
-- exposure is set by the panel, not the target.
CREATE VIEW matching_flats AS
SELECT l.id AS light_id, f.id AS flat_id
FROM sub_frame l
JOIN sub_frame f
    ON  f.frame_type = 'flat' AND f.accepted = 1
    AND f.project_id = l.project_id
    AND f.rig_id IS l.rig_id
    AND f.gain IS l.gain
    AND f.filter_name_hint IS l.filter_name_hint
    AND f.binning_x IS l.binning_x
    AND f.binning_y IS l.binning_y
WHERE l.frame_type = 'light' AND l.accepted = 1;

-- Bias: same gain and binning only (zero-length exposure, no filter).
CREATE VIEW matching_bias AS
SELECT l.id AS light_id, b.id AS bias_id
FROM sub_frame l
JOIN sub_frame b
    ON  b.frame_type = 'bias' AND b.accepted = 1
    AND b.project_id = l.project_id
    AND b.rig_id IS l.rig_id
    AND b.gain IS l.gain
    AND b.binning_x IS l.binning_x
    AND b.binning_y IS l.binning_y
WHERE l.frame_type = 'light' AND l.accepted = 1;

-- Per-light coverage flags over the three match views (unchanged shape).
CREATE VIEW calibration_coverage AS
SELECT
    l.id AS light_id,
    CASE WHEN EXISTS (SELECT 1 FROM matching_darks md WHERE md.light_id = l.id)
         THEN 1 ELSE 0 END AS has_dark,
    CASE WHEN EXISTS (SELECT 1 FROM matching_flats mf WHERE mf.light_id = l.id)
         THEN 1 ELSE 0 END AS has_flat,
    CASE WHEN EXISTS (SELECT 1 FROM matching_bias mb WHERE mb.light_id = l.id)
         THEN 1 ELSE 0 END AS has_bias
FROM sub_frame l
WHERE l.frame_type = 'light' AND l.accepted = 1;

-- "What happened during this session" rollup. distinct filters count the FILTER
-- header now that filter_id is gone.
CREATE VIEW session_summary AS
SELECT
    s.id         AS session_id,
    s.project_id AS project_id,
    s.rig_id     AS rig_id,
    s.start_utc  AS start_utc,
    s.end_utc    AS end_utc,
    CASE WHEN s.end_utc IS NOT NULL
         THEN (julianday(s.end_utc) - julianday(s.start_utc)) * 24.0
         ELSE NULL END AS duration_hours,
    COUNT(sf.id) AS total_subs,
    SUM(CASE WHEN sf.frame_type = 'light' AND sf.accepted = 1 THEN 1 ELSE 0 END)
        AS accepted_lights,
    SUM(CASE WHEN sf.frame_type = 'light' AND sf.accepted = 0 THEN 1 ELSE 0 END)
        AS rejected_lights,
    SUM(CASE WHEN sf.frame_type = 'light' AND sf.accepted = 1
             THEN sf.exposure_seconds ELSE 0 END) / 60.0 AS accepted_light_minutes,
    COUNT(DISTINCT sf.project_target_id)  AS distinct_targets,
    COUNT(DISTINCT sf.filter_name_hint)   AS distinct_filters
FROM session s
LEFT JOIN sub_frame sf ON sf.session_id = s.id
GROUP BY s.id;
