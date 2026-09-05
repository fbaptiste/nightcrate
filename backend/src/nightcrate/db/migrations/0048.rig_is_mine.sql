-- v0.41.1 — mark which rigs the user actually owns.
--
-- Mark which rigs the user actually owns, so seeded smart-telescope rigs do
-- not clutter a list whose whole purpose is "my rigs".
--
-- Same flag, same semantics and the same NOT-in-seeded_fields treatment as the
-- ten owned-equipment tables: toggling it is a user action that must never
-- count as a seed modification, so the loader keeps updating a seeded rig's
-- specs even after the user has claimed it.
--
-- Default 0 matches the equipment tables (a catalog row is not yours until you
-- say so). Every rig that exists today was hand-built by the user, so those are
-- backfilled to 1; rigs created through the API set it explicitly.

ALTER TABLE rig ADD COLUMN is_mine INTEGER NOT NULL DEFAULT 0
    CHECK (is_mine IN (0, 1));

UPDATE rig SET is_mine = 1 WHERE source = 'user';

-- Rebuild rig_summary to expose is_mine. SQLite freezes a view's column list
-- at creation, so adding a column to the base table is not enough.
DROP VIEW IF EXISTS rig_summary;

CREATE VIEW rig_summary AS
SELECT
    r.id,
    r.name,
    r.description,
    r.is_default,
    r.is_mine,
    r.active,
    r.sort_order,
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
