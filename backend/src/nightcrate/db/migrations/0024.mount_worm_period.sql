-- Add ``mount.worm_period_seconds`` (REAL, nullable). Worm-driven
-- mounts have a published or measured worm-gear period that drives
-- the dominant peak in the PHD2 spectrum. v0.26.0's spectrum view
-- renders a vertical marker at this period and matches detected
-- peaks against it (per spec v4 §6.6).
--
-- Strain-wave and direct-drive mounts leave the field NULL — the
-- v0.28.0 drive-type-aware marker model handles those cases.
--
-- The ``rig_summary`` view is rebuilt to surface the new field plus
-- the existing ``mount.drive_type`` so the FFT endpoint can read
-- both via a single rig lookup.

-- depends: 0023.dso_external_refs_simbad_ned

ALTER TABLE mount ADD COLUMN worm_period_seconds REAL;

-- Backfill known worm-period values for existing seed-tracked rows so they
-- aren't stuck at NULL on already-running databases. Adding a new column
-- to mount's ``seeded_fields`` (registry.py) means the seed loader's
-- "user-modified" hash check would otherwise refuse to update rows that
-- predate the field — every existing seed row's stored ``seed_hash`` was
-- computed before this column existed, so ``current_hash != seed_hash``
-- on the next run and the loader skips the row. Patching the values
-- directly in this migration sidesteps that path and brings existing
-- worm-drive rows in line with the CSV in lockstep with the schema
-- change. Strain-wave + direct-drive rows stay NULL (rig-aware support
-- ships in v0.28.0).
UPDATE mount SET worm_period_seconds = 638 WHERE seed_key = 'mount.skywatcher.heq5_pro';
UPDATE mount SET worm_period_seconds = 479 WHERE seed_key = 'mount.skywatcher.eq6_r_pro';
UPDATE mount SET worm_period_seconds = 479 WHERE seed_key = 'mount.skywatcher.cq350_pro';
UPDATE mount SET worm_period_seconds = 479 WHERE seed_key = 'mount.skywatcher.eq8_r_pro';
UPDATE mount SET worm_period_seconds = 479 WHERE seed_key = 'mount.skywatcher.eq8_rh_pro';
UPDATE mount SET worm_period_seconds = 479 WHERE seed_key = 'mount.skywatcher.az_eq6';
UPDATE mount SET worm_period_seconds = 478 WHERE seed_key = 'mount.skywatcher.star_adventurer_2i';
UPDATE mount SET worm_period_seconds = 478 WHERE seed_key = 'mount.skywatcher.star_adventurer_gti';
UPDATE mount SET worm_period_seconds = 287 WHERE seed_key = 'mount.ioptron.cem26';
UPDATE mount SET worm_period_seconds = 287 WHERE seed_key = 'mount.ioptron.cem40';
UPDATE mount SET worm_period_seconds = 600 WHERE seed_key = 'mount.ioptron.cem70';
UPDATE mount SET worm_period_seconds = 600 WHERE seed_key = 'mount.ioptron.gem28';
UPDATE mount SET worm_period_seconds = 600 WHERE seed_key = 'mount.ioptron.gem45';
UPDATE mount SET worm_period_seconds = 478 WHERE seed_key = 'mount.ioptron.skyguider_pro';
UPDATE mount SET worm_period_seconds = 480 WHERE seed_key = 'mount.celestron.avx';
UPDATE mount SET worm_period_seconds = 480 WHERE seed_key = 'mount.celestron.cgem_ii';
UPDATE mount SET worm_period_seconds = 540 WHERE seed_key = 'mount.celestron.cgx';
UPDATE mount SET worm_period_seconds = 540 WHERE seed_key = 'mount.celestron.cgx_l';
UPDATE mount SET worm_period_seconds = 570 WHERE seed_key = 'mount.takahashi.em200_temma3';
UPDATE mount SET worm_period_seconds = 570 WHERE seed_key = 'mount.takahashi.em11_temma2z';
UPDATE mount SET worm_period_seconds = 240 WHERE seed_key = 'mount.losmandy.g11';
UPDATE mount SET worm_period_seconds = 240 WHERE seed_key = 'mount.losmandy.gm8';
UPDATE mount SET worm_period_seconds = 480 WHERE seed_key = 'mount.vixen.sxd2';
UPDATE mount SET worm_period_seconds = 480 WHERE seed_key = 'mount.vixen.sxp2';

-- The seed loader's "user-modified" check will continue to skip these
-- rows on subsequent runs (existing ``seed_hash`` predates the new
-- field, so it can't match the recomputed hash). That's acceptable
-- pre-release: future CSV edits on these specific mounts won't
-- propagate via the loader, but a fresh DB rebuild picks up the right
-- values via the normal seed path. After first release, schema-evolving
-- the seed contract will need a versioned-hash strategy in the loader
-- itself.

DROP VIEW IF EXISTS rig_summary;

CREATE VIEW rig_summary AS
SELECT
    r.id,
    r.name,
    r.description,
    r.is_default,
    r.active,
    r.notes,
    r.created_at,
    r.updated_at,
    -- OTA
    r.telescope_configuration_id,
    t.id AS telescope_id,
    t.model_name AS telescope_name,
    tc.config_name AS telescope_config_name,
    tc.effective_focal_length_mm,
    tc.effective_focal_ratio,
    tc.effective_image_circle_mm,
    t.aperture_mm,
    -- Camera
    r.camera_id,
    c.model_name AS camera_name,
    s.pixel_size_um,
    s.resolution_x AS sensor_resolution_x,
    s.resolution_y AS sensor_resolution_y,
    s.sensor_width_mm,
    s.sensor_height_mm,
    s.sensor_type,
    s.adc_bit_depth AS sensor_adc_bit_depth,
    -- Mount
    r.mount_id,
    m.model_name AS mount_name,
    m.drive_type AS mount_drive_type,
    m.worm_period_seconds AS mount_worm_period_seconds,
    -- Filter wheel
    r.filter_wheel_id,
    fw.model_name AS filter_wheel_name,
    fw.num_positions AS filter_wheel_positions,
    -- Focuser
    r.focuser_id,
    foc.model_name AS focuser_name,
    -- Guide
    r.guide_camera_id,
    gc.model_name AS guide_camera_name,
    r.guide_scope_id,
    gs.model_name AS guide_scope_name,
    gs.focal_length_mm AS guide_scope_focal_length_mm,
    r.oag_id,
    o.model_name AS oag_name,
    -- Guide camera sensor (for guide calculator)
    gs2.pixel_size_um AS guide_pixel_size_um,
    gs2.resolution_x AS guide_resolution_x,
    gs2.resolution_y AS guide_resolution_y,
    -- Peripherals
    r.computer_id,
    comp.model_name AS computer_name,
    -- Single filter
    r.single_filter_id,
    sf.model_name AS single_filter_name
FROM rig r
JOIN telescope_configuration tc ON tc.id = r.telescope_configuration_id
JOIN telescope t ON t.id = tc.telescope_id
JOIN camera c ON c.id = r.camera_id
JOIN sensor s ON s.id = c.sensor_id
LEFT JOIN mount m ON m.id = r.mount_id
LEFT JOIN filter_wheel fw ON fw.id = r.filter_wheel_id
LEFT JOIN focuser foc ON foc.id = r.focuser_id
LEFT JOIN camera gc ON gc.id = r.guide_camera_id
LEFT JOIN sensor gs2 ON gs2.id = gc.sensor_id
LEFT JOIN guide_scope gs ON gs.id = r.guide_scope_id
LEFT JOIN oag o ON o.id = r.oag_id
LEFT JOIN computer comp ON comp.id = r.computer_id
LEFT JOIN filter sf ON sf.id = r.single_filter_id;
