# Target Planner (v0.16.0 Pass A + v0.17.0 Pass B)

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

## Pass B additions (v0.17.0)

### Thumbnail variants

Two new cache variants extend the Pass A set (with their backend-
computed angular extent):

- `rig_framed` — 180×180, extent = rig major-axis FOV exactly. The list
  renders it in a box sized by the rig's sensor aspect ratio and lets
  `object-fit: cover` crop the stored square image to the right
  proportions.
- `fov_simulator` — 800×800, extent = `max(rig_diagonal × 1.5, object × 2)`
  so the rig rectangle has room to rotate with comfortable margin
  regardless of rig or target scale.

The Pass A `detail` variant grew from 600×600 → 800×800 with the
extent formula tightened from `×2.5 / 0.5°` to `×3.5 / 1.0°`. Migration
0018 wipes the old cache (rows + files, via the startup orphan sweep)
so stale Pass A `detail` JPEGs don't briefly show before their LRU
eviction.

### Cache key with FOV

Rig-dependent variants add two columns to the key: `fov_major_deg_x1000`
and `fov_minor_deg_x1000` (rounded deg × 1000 as an int to sidestep
float-equality pitfalls). Two rigs that differ by < 0.001° share a
cache entry; rigs that differ by ≥ 0.01° get separate entries. Edit
a rig's focal reducer and the cache picks up the new shape without
orphaning anything.

The `UNIQUE` index wraps the nullable FOV columns in `COALESCE(..,-1)`
so a `list` or `detail` entry (FOV = NULL) doesn't collide with a
`rig_framed` one at the same `dso_id`.

### Orphan sweep

`services.thumbnails.sync_orphan_files()` runs once on app startup
(from `main.py` lifespan). It scans `APP_DIR/thumbnails/`, parses each
file with `_THUMB_FILENAME_RE`, and deletes any file whose name
doesn't correspond to a live row. Non-thumbnail files (README, etc.)
are left alone. Needed because migration 0018 wipes the DB rows but
SQL migrations can't `unlink()`.

### Frontend — FOV simulator

`components/planner/FovSimulator.tsx` — the detail-panel hero when a
rig is selected. Wide-view DSS2 background + CSS-rotated orange
rectangle sized to the rig's angular FOV scaled to the image's pixel
extent. Drag the edge, use ← → keys (±5°), Shift+arrow (±1°), the
numeric input, or the reset button. Rotation is session-only — closing
the detail panel resets to 0° (Pass C will own persistence).

North-up east-left convention throughout. A "what does this mean?"
tooltip explains that the rotation shown is relative to sky north, not
the user's actual rotator angle (mount orientation + rotator position
produce the real captured-image rotation).

### Frontend — second list column

`PlannerPage.tsx` renders an "In my rig" column right after the Pass A
thumbnail column when a rig is selected. Column width + image CSS use
the rig's major/minor ratio so the cell reads like a viewfinder.

## Extending — where to hook the next pieces

- **Saved rotation per (rig, dso):** clean bolt-on — one new table
  (`user_fov_preference`) and two new routes (GET/PUT). Add
  a "Save rotation" button next to the simulator's input field.
- **Mosaic planning:** extend the simulator to support multi-panel
  layout; `FovSimulator` becomes a single panel with a sibling
  "add panel" action.
- **Weather integration:** surface `imaging_quality` + cloud gating
  per-target in the list. The weather snapshot is already keyed by
  location + date.
- **Date picker:** the API already accepts `date` — just surface it in
  the UI and the visibility cache keys already handle separate dates
  cleanly.
- **Moon distance filter:** trivial in-memory filter since separation
  is already computed.
