-- Target Planner Pass B — panned fov_simulator views.
--
-- Adds sky-region columns to thumbnail_cache so the FOV simulator can
-- cache images fetched at arbitrary (RA, Dec), not just the DSO's
-- native coordinates. Two rows for the same DSO + rig at different
-- panned centres get distinct cache entries under the widened unique
-- index.
--
-- 0018 rebuilt the table on its way to adding FOV descriptor columns;
-- by the time pan landed, 0018 had already applied to dev databases,
-- so this follow-up migration uses ALTER TABLE ADD COLUMN +
-- index-rebuild instead of rebuilding the table again.
--
-- When both center_*_deg_x1000 columns are NULL, the entry behaves
-- exactly like the pre-pan behaviour — the simulator's initial view
-- still hits the same cache row as before, so users don't lose any
-- already-cached images.
--
-- Depends: 0018.thumbnail_rig_framed

ALTER TABLE thumbnail_cache ADD COLUMN center_ra_deg_x1000 INTEGER;
ALTER TABLE thumbnail_cache ADD COLUMN center_dec_deg_x1000 INTEGER;

-- Rebuild the unique key: COALESCE wraps the new columns with a
-- distinct sentinel (-999999) so a legitimate 0.0 RA/Dec can't
-- collide with NULL, and so the sentinel for the FOV columns (-1)
-- stays unambiguous.
DROP INDEX IF EXISTS idx_thumbnail_cache_unique;
CREATE UNIQUE INDEX idx_thumbnail_cache_unique
    ON thumbnail_cache(
        dso_id,
        variant,
        width,
        height,
        COALESCE(fov_major_deg_x1000, -1),
        COALESCE(fov_minor_deg_x1000, -1),
        COALESCE(center_ra_deg_x1000, -999999),
        COALESCE(center_dec_deg_x1000, -999999)
    );
