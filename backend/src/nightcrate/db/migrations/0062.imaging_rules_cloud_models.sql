-- depends: 0061.imaging_rules_single_chance

-- v0.41.9: let each location choose how cloud forecasts decide an hour.

ALTER TABLE location_imaging_rules
ADD COLUMN cloud_use_ecmwf INTEGER NOT NULL DEFAULT 1
CHECK (cloud_use_ecmwf IN (0, 1));

ALTER TABLE location_imaging_rules
ADD COLUMN cloud_use_gfs INTEGER NOT NULL DEFAULT 1
CHECK (cloud_use_gfs IN (0, 1));

ALTER TABLE location_imaging_rules
ADD COLUMN cloud_use_icon INTEGER NOT NULL DEFAULT 1
CHECK (cloud_use_icon IN (0, 1));

ALTER TABLE location_imaging_rules
ADD COLUMN cloud_combination TEXT NOT NULL DEFAULT 'majority'
CHECK (cloud_combination IN ('majority', 'uncertain'));

ALTER TABLE location_imaging_rules
ADD COLUMN cloud_preferred_model TEXT NOT NULL DEFAULT 'ecmwf_ifs025'
CHECK (
    cloud_preferred_model IN ('ecmwf_ifs025', 'gfs_seamless', 'icon_seamless')
    AND (cloud_use_ecmwf = 1 OR cloud_use_gfs = 1 OR cloud_use_icon = 1)
    AND (
        (cloud_preferred_model = 'ecmwf_ifs025' AND cloud_use_ecmwf = 1)
        OR (cloud_preferred_model = 'gfs_seamless' AND cloud_use_gfs = 1)
        OR (cloud_preferred_model = 'icon_seamless' AND cloud_use_icon = 1)
    )
);
