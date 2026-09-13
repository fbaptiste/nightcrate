-- v0.41.3 — track whether a frame's quality metrics have been computed.
--
-- Migration 0037 created hfr / star_count / median_adu / background_adu /
-- snr_estimate and left them empty. v0.41.3 fills them from a batch pass over
-- the cataloged files, which needs to know which frames are still outstanding.
--
-- Why a marker column rather than "hfr IS NULL": the pass computes ADU stats for
-- EVERY frame type but star metrics only for lights, so a successfully analyzed
-- dark legitimately ends up with hfr NULL. Keying "not analyzed" off hfr would
-- put every calibration frame back in the queue on every run, forever.
--
--   quality_analyzed_at  NULL = never analyzed. Set on every outcome, including
--                        failures, so an unreadable file is not retried endlessly.
--   quality_status       'ok'         metrics computed
--                        'no_stars'   read fine, detection found nothing (clouds,
--                                     a closed shutter) — a real result, not an error
--                        'unreadable' the file could not be read or decoded
--   quality_error        the reason, for the 'unreadable' case only.
--
-- Re-analyzing with force clears all three and recomputes.
ALTER TABLE sub_frame ADD COLUMN quality_analyzed_at TEXT;
ALTER TABLE sub_frame ADD COLUMN quality_status TEXT
    CHECK (quality_status IS NULL OR quality_status IN ('ok', 'no_stars', 'unreadable'));
ALTER TABLE sub_frame ADD COLUMN quality_error TEXT;

-- The pending-work query is "this project's frames of this type that have never
-- been analyzed" — a partial index keeps it off a full scan as the catalog grows.
CREATE INDEX idx_sub_frame_quality_todo ON sub_frame(project_id, frame_type)
    WHERE quality_analyzed_at IS NULL;
