-- v0.40.0 — total integration time for masters/stacks.
-- PixInsight masters carry no NCOMBINE but do carry the summed exposure
-- (PCL:TotalExposureTime); store it so the catalog can show integration time
-- instead of a (usually absent) frame count. Backfilled on the next re-scan.
ALTER TABLE processed_image ADD COLUMN total_exposure_seconds REAL;
