-- Correct capture-time provenance for frames cataloged before v0.55.0.
-- depends: 0075.colour_and_raw_frames

UPDATE sub_frame
SET date_obs_source = 'file_time'
WHERE date_obs_source = 'header'
  AND file_metadata_json IS NULL
  AND CASE
      WHEN fits_header_json IS NULL OR NOT json_valid(fits_header_json) THEN 1
      ELSE
          NULLIF(trim(CAST(json_extract(fits_header_json, '$."DATE-OBS"') AS TEXT)), '') IS NULL
          AND NULLIF(trim(CAST(json_extract(fits_header_json, '$."DATE-UTC"') AS TEXT)), '') IS NULL
      END;
