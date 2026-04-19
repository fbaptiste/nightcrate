-- depends: 0005.equipment_schema

ALTER TABLE camera ADD COLUMN guide_sensor_id INTEGER REFERENCES sensor(id);
CREATE INDEX IF NOT EXISTS idx_camera_guide_sensor ON camera(guide_sensor_id);
