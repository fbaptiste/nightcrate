-- DSO augmentation columns (v0.15.0).
--
-- Adds distance_pc + distance_method (with a closed CHECK vocabulary) and two
-- provenance booleans used by the frontend detail panel to show a subtle
-- "augmented" indicator next to common_name and surface_brightness values
-- that were populated from NightCrate's editorial augmentation CSV.
--
-- Distances are stored in parsecs (astronomy-canonical); the frontend
-- formatter auto-scales and shows both parsecs and light-years.
--
-- `distance_method` is NULL when no distance is known. New methods
-- (gaia_parallax, hubble_law, etc.) are added by future migrations.

-- depends: 0015.dso_catalog

ALTER TABLE dso ADD COLUMN distance_pc REAL;
ALTER TABLE dso ADD COLUMN distance_method TEXT
    CHECK (distance_method IS NULL OR distance_method IN ('50mgc', 'curated', 'redshift'));
ALTER TABLE dso ADD COLUMN surface_brightness_augmented INTEGER NOT NULL DEFAULT 0
    CHECK (surface_brightness_augmented IN (0, 1));
ALTER TABLE dso ADD COLUMN common_name_augmented INTEGER NOT NULL DEFAULT 0
    CHECK (common_name_augmented IN (0, 1));

CREATE INDEX IF NOT EXISTS idx_dso_distance_method
    ON dso(distance_method)
    WHERE distance_method IS NOT NULL;
