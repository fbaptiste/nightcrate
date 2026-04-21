-- Target Planner Pass C — DSO-agnostic sky-tile cache.
--
-- The existing ``thumbnail_cache`` table keys every cache entry on a
-- DSO id, which means two DSOs that share a sky region can't share
-- cached bytes. Pass C reworks the FOV simulator around a HEALPix-
-- regional TAN projection where every cell in a region lives on the
-- same tangent plane — cells tile pixel-perfectly and, because their
-- identity is a pure function of sky coordinates, neighbouring DSOs
-- hit the same cached cells.
--
-- Schema design:
--   - Regions partition the sphere via HEALPix NSIDE=8 (768 tiles at
--     ~7.3° per side, roughly equal area, no pole singularity).
--     ``healpix_ipix`` is the canonical region identifier.
--   - Within a region, ``tier`` selects one of three resolution steps
--     (``narrow`` / ``med`` / ``wide``) chosen per rig from the rig's
--     major FOV. See services/sky_tiles.py for the tier → cell-size
--     mapping. Cache rows at different tiers never collide.
--   - ``cell_i`` / ``cell_j`` are integer offsets from the region's
--     tangent point on the TAN plane, in units of cells. Together
--     with the tier, they pick out one rectangular sub-region of the
--     region's tangent plane.
--   - ``cell_size_deg_x100`` stores the cell's angular extent (deg ×
--     100, so 50 / 200 / 800 for the three tiers). ``cell_width_px``
--     / ``cell_height_px`` store the image's pixel dimensions. All
--     three are part of the unique key so a future change to any
--     tier's sizing lives alongside the old entries until they age
--     out via LRU.
--
-- Coexists with ``thumbnail_cache`` (which continues to serve the
-- ``list`` / ``detail`` / ``rig_framed`` variants). The
-- ``fov_simulator`` variant on ``thumbnail_cache`` ages out through
-- ordinary LRU eviction — no data migration is needed.
--
-- Depends: 0019.thumbnail_sky_region

CREATE TABLE IF NOT EXISTS sky_tile_cache (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    hips_survey          TEXT    NOT NULL,
    healpix_nside        INTEGER NOT NULL,
    healpix_ipix         INTEGER NOT NULL,
    tier                 TEXT    NOT NULL CHECK (tier IN ('narrow', 'med', 'wide')),
    cell_size_deg_x100   INTEGER NOT NULL,
    cell_width_px        INTEGER NOT NULL,
    cell_height_px       INTEGER NOT NULL,
    cell_i               INTEGER NOT NULL,
    cell_j               INTEGER NOT NULL,
    file_path            TEXT    NOT NULL UNIQUE,
    source               TEXT    NOT NULL CHECK (source IN (
        'dss2_color', 'dss2_red', 'dss2_blue', 'placeholder'
    )),
    bytes                INTEGER NOT NULL,
    fetched_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    last_access_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    fetch_error          TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sky_tile_cache_unique
    ON sky_tile_cache(
        hips_survey,
        healpix_nside,
        healpix_ipix,
        tier,
        cell_size_deg_x100,
        cell_width_px,
        cell_height_px,
        cell_i,
        cell_j
    );

CREATE INDEX IF NOT EXISTS idx_sky_tile_cache_last_access
    ON sky_tile_cache(last_access_at);
CREATE INDEX IF NOT EXISTS idx_sky_tile_cache_region
    ON sky_tile_cache(healpix_nside, healpix_ipix);
