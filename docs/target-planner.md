# Target Planner (v0.16.0, Pass A)

One-page overview for developers extending the planner later. User
documentation lives elsewhere.

## What it does

`/planner` answers "what's up tonight?" for a user-selected location.
The list is populated by a vectorized astropy alt/az computation over
every active DSO, reduced to per-DSO summary fields (hours-visible,
peak altitude, moon min-separation, rise/set/transit) and filtered +
sorted in memory. An optional rig selection adds a FOV coverage column
and unlocks a "frames well" filter.

## Architecture

```
api/planner.py              → route handlers + filter/sort/paginate
api/planner_models.py       → Pydantic response shapes

services/planner_visibility.py
  PlannerLocation            value object decoupled from the DB model
  DsoCoord                   {id, ra, dec, maj_axis_arcmin}
  VisibilitySnapshot         {dark_window, moon_phase, per_dso: dict}
  compute_visibility_snapshot()
  VisibilityCache            in-process LRU, keyed on
                             (location_id, date, updated_at, horizon_updated_at)

services/planner_sky_track.py
  compute_sky_track()        per-DSO high-res track for the detail graph

services/thumbnails.py       DSS2 Color JPEGs under APP_DIR/thumbnails/
services/hips_client.py      thin wrapper over CDS hips2fits
services/rig_calculators.py  + compute_coverage_pct / frames_well

frontend/
  pages/PlannerPage.tsx
  components/planner/{PlannerFilters, PlannerDetailPanel, SkyPositionGraph, ThumbnailCell}.tsx
  api/planner.ts
```

## Visibility model

- Window = astro-dark on the selected date (sun ≤ −18°). No civil or
  nautical imaging window — deferred.
- Sampling = 5 minutes. ~100 samples per DSO per night for a typical
  mid-latitude site. Full snapshot over 14 k DSOs runs in <1 s
  vectorized.
- A DSO is visible at time *t* when `alt(t) > horizon(az(t))`. Horizon
  is the location's custom polyline (via `services/horizon.py`'s
  interpolator) or a flat `planner_min_altitude_deg` floor.
- `min_moon_separation_deg` is the **closest approach during the
  visibility window**, not at-peak — the original spec called for
  at-peak but at-peak is misleading (moon may be below horizon at
  transit but rise during the visible window). Spec deviation noted in
  the visibility-engine module docstring.

## Thumbnail cache

- Misses return a 1×1 transparent PNG with HTTP 202 and enqueue a
  background fetch. The frontend detects the placeholder via
  `img.naturalWidth <= 1` and retries every 2 seconds (cache-buster
  query param) until the real image lands.
- Primary source: `CDS/P/DSS2/color`. Fallback: `CDS/P/DSS2/red`. Both
  via `hips2fits` with a 20-second timeout.
- Double-failure inserts a `fetch_error` sentinel row so follow-up
  polls don't restart fetch storms. Errors expire after 1 hour.
- LRU eviction runs after every successful fetch — deterministic, no
  background sweeper.

## Extending — where to hook the next pieces

- **Weather integration (Pass B):** surface `imaging_quality` + cloud
  gating per-target in the list. The weather snapshot is already
  keyed by location + date; a small join at API time would do it.
- **Rig-framed thumbnails (Pass B):** switch the thumbnail `fov_deg`
  from max(major × 1.5, 0.1°) to the rig's actual FOV. Cache key
  grows an extra variant for rig-framed.
- **Date picker:** the API already accepts `date` — just surface it in
  the UI and add a note that visibility-snapshot caching keys on the
  date so different picks don't collide.
- **Moon distance filter:** add a numeric slider and a `min_moon_distance_deg`
  query param; trivial in-memory filter since separation is already
  computed.
