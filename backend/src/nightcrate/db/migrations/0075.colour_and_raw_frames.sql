-- Colour mosaics, camera-raw metadata and versioned quality measurements (v0.55.0).
-- depends: 0074.drop_folder_and_frame_target

ALTER TABLE sub_frame ADD COLUMN iso INTEGER CHECK (iso IS NULL OR iso > 0);
ALTER TABLE sub_frame ADD COLUMN camera_temp_c REAL;
ALTER TABLE sub_frame ADD COLUMN filter_name_source TEXT NOT NULL DEFAULT 'auto'
    CHECK (filter_name_source IN ('auto', 'user'));
ALTER TABLE sub_frame ADD COLUMN date_obs_source TEXT NOT NULL DEFAULT 'header'
    CHECK (date_obs_source IN (
        'header', 'exif_offset', 'maker_note', 'estimated_project_zone',
        'estimated_computer_zone', 'file_time'
    ));
ALTER TABLE sub_frame ADD COLUMN frame_type_basis TEXT
    CHECK (frame_type_basis IS NULL OR frame_type_basis IN (
        'header', 'sky', 'file_name', 'folder_name'
    ));
ALTER TABLE sub_frame ADD COLUMN file_metadata_json TEXT;
ALTER TABLE sub_frame ADD COLUMN quality_method INTEGER;
ALTER TABLE sub_frame ADD COLUMN quality_units TEXT
    CHECK (quality_units IS NULL OR quality_units IN ('adu', 'float'));

ALTER TABLE project_session ADD COLUMN iso INTEGER CHECK (iso IS NULL OR iso > 0);

-- Only the old FITS path whose recorded values and measurement-grey calculation
-- are provably unchanged keeps its result. Legacy XISF headers did not retain
-- sampleFormat/bounds, so no XISF result is provable and all are cleared.
UPDATE sub_frame
SET quality_units = 'adu'
WHERE (
      hfr IS NOT NULL OR star_count IS NOT NULL OR median_adu IS NOT NULL
      OR background_adu IS NOT NULL OR snr_estimate IS NOT NULL
      OR quality_analyzed_at IS NOT NULL OR quality_status IS NOT NULL
      OR quality_error IS NOT NULL
  )
  AND EXISTS (
      SELECT 1 FROM file_location fl
      WHERE fl.sub_frame_id = sub_frame.id
        AND (
            lower(fl.path) LIKE '%.fit'
            OR lower(fl.path) LIKE '%.fits'
            OR lower(fl.path) LIKE '%.fts'
        )
  )
  AND CAST(json_extract(fits_header_json, '$.BITPIX') AS INTEGER) = 16
  AND CAST(json_extract(fits_header_json, '$.BZERO') AS REAL) = 32768
  AND COALESCE(CAST(json_extract(fits_header_json, '$.BSCALE') AS REAL), 1) = 1
  AND CAST(json_extract(fits_header_json, '$.NAXIS') AS INTEGER) = 2
  AND NULLIF(trim(CAST(json_extract(fits_header_json, '$.BAYERPAT') AS TEXT)), '') IS NULL
  AND NULLIF(trim(CAST(json_extract(fits_header_json, '$.COLORTYP') AS TEXT)), '') IS NULL;

UPDATE sub_frame
SET hfr = NULL,
    star_count = NULL,
    median_adu = NULL,
    background_adu = NULL,
    snr_estimate = NULL,
    quality_analyzed_at = NULL,
    quality_status = NULL,
    quality_error = NULL,
    quality_units = NULL
WHERE quality_units IS NULL
  AND (
      hfr IS NOT NULL OR star_count IS NOT NULL OR median_adu IS NOT NULL
      OR background_adu IS NOT NULL OR snr_estimate IS NOT NULL
      OR quality_analyzed_at IS NOT NULL OR quality_status IS NOT NULL
      OR quality_error IS NOT NULL
  );

DROP VIEW calibration_coverage;
DROP VIEW matching_darks;
DROP VIEW matching_flats;
DROP VIEW matching_bias;

CREATE VIEW matching_darks AS
SELECT l.id AS light_id, d.id AS dark_id
FROM sub_frame l
JOIN sub_frame_equipment le ON le.sub_frame_id = l.id
JOIN sub_frame d
    ON  d.frame_type = 'dark' AND d.accepted = 1
    AND d.project_id = l.project_id
    AND d.rig_id IS l.rig_id
    AND d.gain IS l.gain
    AND d.iso IS l.iso
    AND d.exposure_seconds = l.exposure_seconds
    AND d.binning_x IS l.binning_x
    AND d.binning_y IS l.binning_y
    AND (
        l.file_metadata_json IS NOT NULL
        OR (d.set_temp_c IS NULL AND l.set_temp_c IS NULL)
        OR ABS(d.set_temp_c - l.set_temp_c) <= 1.0
    )
JOIN sub_frame_equipment de
    ON de.sub_frame_id = d.id AND de.camera_id IS le.camera_id
WHERE l.frame_type = 'light' AND l.accepted = 1;

CREATE VIEW matching_flats AS
SELECT l.id AS light_id, f.id AS flat_id
FROM sub_frame l
JOIN sub_frame_equipment le ON le.sub_frame_id = l.id
JOIN sub_frame f
    ON  f.frame_type = 'flat' AND f.accepted = 1
    AND f.project_id = l.project_id
    AND f.rig_id IS l.rig_id
    AND f.gain IS l.gain
    AND f.iso IS l.iso
    AND f.filter_name_hint IS l.filter_name_hint
    AND f.binning_x IS l.binning_x
    AND f.binning_y IS l.binning_y
JOIN sub_frame_equipment fe
    ON fe.sub_frame_id = f.id
    AND fe.camera_id IS le.camera_id
    AND fe.telescope_configuration_id IS le.telescope_configuration_id
WHERE l.frame_type = 'light' AND l.accepted = 1;

CREATE VIEW matching_bias AS
SELECT l.id AS light_id, b.id AS bias_id
FROM sub_frame l
JOIN sub_frame_equipment le ON le.sub_frame_id = l.id
JOIN sub_frame b
    ON  b.frame_type = 'bias' AND b.accepted = 1
    AND b.project_id = l.project_id
    AND b.rig_id IS l.rig_id
    AND b.gain IS l.gain
    AND b.iso IS l.iso
    AND b.binning_x IS l.binning_x
    AND b.binning_y IS l.binning_y
JOIN sub_frame_equipment be
    ON be.sub_frame_id = b.id AND be.camera_id IS le.camera_id
WHERE l.frame_type = 'light' AND l.accepted = 1;

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
