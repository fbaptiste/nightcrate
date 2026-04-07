-- depends: 0005.equipment_schema

ALTER TABLE camera ADD COLUMN guide_sensor_id INTEGER REFERENCES sensor(id);
