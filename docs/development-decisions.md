# Development decisions

Read the relevant section before changing a feature. These are current constraints;
release history belongs in [the archived plan](archive/plan-through-v0.41.5.md).
Shared architecture, checks, and privacy rules live in [CLAUDE.md](../CLAUDE.md).

## Image analyzer and file I/O

- `imaging.py` owns format-independent math; `fits_io`, `xisf_io`,
  `pxiproject_io`, `standard_io`, and `archive_io` own input formats. Keep the
  XISF reader clean-room; do not copy the GPL reference library.
- AutoSTF uses **avgDev, not MAD**: shadow clip `median − 1.25 × avgDev`, target
  median 0.25, self-inverse MTF for midtones. Stretch runs server-side:
  `stretch=auto` computes stats/linearity/STF together; slider edits use `stf`.
- GPU stretch/statistics are safe only on their serialized path. Thumbnail
  renderers use numpy, decimate before stretching, and never call the GPU-backed
  stretch helpers from `asyncio.to_thread`. Concurrent mlx calls can segfault.
- Use per-key locks for image/stat caches. Archive identity includes archive
  path, mtime, and entry; histogram sampling is about 2M pixels; PNG compression
  level 1 favors local rendering speed.
- Only ordinary FITS files support header editing. Protect `SIMPLE`, `BITPIX`,
  `NAXIS*`, `EXTEND`, `BZERO`, `BSCALE`, `COMMENT`, `HISTORY`, and `END`.
- Virtual paths use `archive.zip::entry` or `project.pxiproject::index`. An
  integer suffix identifies a project image; merely finding `::` does not.
  Python `path_resolver` and TypeScript `parsePath` must agree.
- I/O accepts `Path | BinaryIO`. zip/tar entries extract in memory; 7z uses a
  cleaned-up temporary directory. Header reads can close a passed buffer:
  read bytes once and give each consumer a fresh `BytesIO`, not a re-seek.
- XISF WCS comes from `PCL:AstrometricSolution`: decode its base64 properties
  to TAN/FITS cards. **CD = matrix as-is, CRVAL = reference sky coordinates,
  CRPIX = reference image coordinates + 1.** No transpose or y-flip. Real FITS
  WCS wins; nonlinear spline distortion is not modeled for annotations.
- `astropy.wcs.WCS.world_to_pixel` returns 0-based coordinates that match numpy
  indexing and the displayed image (row 0 at the top). Use them directly for
  annotations; a y-flip misaligns every overlay.
- `.pxiproject` referenced images load from the path the project stores. A
  missing file raises "Referenced file not found", usually because a drive is
  not mounted. Do not add a fallback to paths relative to the project: projects
  legitimately reference subs, masters, and outputs on different drives, and a
  same-named file elsewhere could load silently. Improve the message instead.
  The loader does not yet reject a relative stored path, which would resolve
  against the server's working directory (see `PLAN.md` deferred work).
- Annotation counts must match drawn objects: keep any object whose extent
  intersects the frame, clip the overlay, and clamp labels into the image.
- `pixel_loader` is the shared path-to-normalized-array entry point for new
  code. `api/images.py:_load_image_data` and `api/aberration.py:_load_mono_data`
  still dispatch pre-resolved sources separately; a new format affects all three.
- Aberration detection uses `sep` and `sep.flux_radius` for HFR. Cache by
  `(file_path, hdu, settings_json)` with configurable TTL; debounce edits 500 ms.
- File browser: a single click opens a folder or selects a file; a double click
  opens the file. Stretch sliders change local state and render only on
  **Apply**; the Auto/None and Linked/Unlinked toggles and Reset apply at once.
  Show the Extension selector (not "HDU") only when a file has more than one
  image extension. The analyzer sidebar never scrolls horizontally: inner
  containers use `minWidth: 0` and `overflowX: hidden`.

## App shell

- `AppShell` keeps the Image Analyzer, Planner, PHD2 Analyzer, DSO Catalog, and
  Weather pages mounted after their first visit, hidden with `display: none`, so
  nested state such as chart zoom survives navigation. To add a page, register
  it in `PERSISTENT_ROUTES` (`components/AppShell.tsx`) and give its route
  `element: null` in `App.tsx` to avoid a second render.

## Tablet and LAN behavior

- `make dev-lan` exposes **both** backend and frontend on the LAN. The backend
  has no authentication and widens CORS; this is opt-in for a trusted network.
- Vite prefers `frontend/.certs/{cert,key}.pem` (mkcert), otherwise uses
  `@vitejs/plugin-basic-ssl`. Trusted HTTPS is needed for tablet clipboard and
  pixel-inspection behavior. Proxy `/api`, `/docs`, `/openapi.json` to the backend.
- Pixel inspection samples a reusable **301×301 canvas** with nine-argument
  `drawImage`. A full-image canvas can silently fail to allocate on iOS and
  return zero pixels.
- Preserve the viewport's `maximum-scale=1.0,user-scalable=no` and image
  container `gesturestart/change/end` suppression: Safari otherwise adds its own
  zoom to the app's pinch handler. Touch zoom/pan updates transforms during the
  gesture and synchronizes state on completion.
- Chart touch listeners need `{ passive: false }` for `preventDefault`.
  Suppress touch callouts/text selection and set `touch-action: none` on SVGs
  where the chart owns the gesture.
- Detect touch tablets with `navigator.maxTouchPoints > 1`. iPadOS Safari sends
  a desktop Mac user agent by default, so user-agent tests miss iPads.
- Chip-style Autocomplete filters set `readOnly` on the input
  (`inputProps={{ ...params.inputProps, readOnly: true }}`): a tap opens the
  options without raising the iOS keyboard. See `PillFilter` and
  `FilterIntentSelect`.

## Equipment and seed data

- Normalize equipment; no generic `custom_fields` JSON. Vocabularies such as
  drive type, passband line, software/interface categories and sensor/Bayer type
  are CHECK-constrained. A telescope has exactly one native configuration and
  at least one configuration. Camera `effective_*` values override its sensor.
  Use measured optical-configuration focal lengths when available rather than
  assuming the nominal marketed focal length.
- Retire equipment with `active=0`; support restore/include-retired. Selecting a
  default rig clears the other defaults in the same transaction. Removing a
  rig's filter wheel removes its slots in the same transaction.
- A filter's name alone cannot identify equipment. Different rigs can use
  different filters with the same band label. Equipment comes from user-declared
  rigs, not an automatic FITS resolver.
- Sensor read noise is split into **low/high gain**, not conversion mode:
  some sensors publish two values without a discrete HCG switch. `dual_gain` and
  `hcg_threshold_gain` describe that switch. Full-well capacity is the low-gain
  figure; use low-gain noise for dynamic range.
- Mount payload excludes counterweights; use photographic capacity where it is
  distinguished from visual. Harmonic mounts' with-counterweight rating has its
  own column. Peak QE is within **400–700 nm**, with wavelength stored separately.
- A `filter_passband` row represents an emission line usefully passed, not one
  physical window. Lines may share a bandwidth; **never sum bandwidth across rows**.
- Seed `rig` only for inseparable smart telescopes; ordinary rigs are user
  records. Load rigs last, after their components. `is_default`, `sort_order`,
  and `is_mine` are user-managed, not seeded. Renaming a seeded rig marks it edited.
- Seed hashes include field names. Self-heal a stale hash only when current data
  already equals incoming CSV data. A seeded-field rename also needs a step in
  `seed_loader/rehash.py`: reconstruct the old hash and update only untouched rows.
  Do not write CSV values into a migration to bypass edit protection.
- Never overwrite `source='user'` rows. Replace junction rows only for updated
  or inserted parents. Missing expected CSV files fail loudly. Test rehashes on
  a pre-migration DB copy; fresh databases cannot expose stranded seed records.

## Projects, catalog, and sessions

- Projects persist edits immediately: text on blur/Enter; gallery/order/main/crop
  actions on click. No staging area or global Save/Cancel. Abandoning a new
  project means deleting it.
- Gallery images are finished display images. The plate-solve image is separate,
  normally linear FITS/XISF. One solve per project today; mosaics are deferred.
- `project_solve` stores WCS; `project_dso` stores **every** in-frame object.
  Pick the automatic main by nearest center, then largest on a tie. Reproject
  overlay coordinates from stored WCS on read, off the event loop.
  The stored solve is view-only; delete it with confirmation before re-solving.
- `project_target` is the single source for main targets (overview chips and
  solve-tab stars). Main targets survive deletion of a solve; derived solve
  objects and its rendered image do not. Reuse `DsoAnnotationOverlay` in both
  analyzers; main objects are teal and others blue.
- `MarkdownEditor` defaults to rendered Markdown, enters editing explicitly,
  and saves only changed text. Reuse it for descriptions and notes.
- A project owns every `sub_frame`, `processed_image`, and `file_location` row.
  Identity is **(project, content hash)** for images and **(project, path)** for
  locations. The same physical file in two projects has independent rows.
  Re-ingest is idempotent within a project; tests need distinct pixels when they
  intend distinct files. Scope catalog queries directly by `project_id`.
- Ingest commits then lets users correct facts. Classify from headers, never
  directory names. `NCOMBINE`, `STACKCNT`, master image types and PixInsight
  history route masters/stacks to `processed_image`, outside exposure totals.
  Keep logs and `.pxiproject` assets; skip generated `.xnml`, `.xdrz`, `.xpsm` sidecars.
- Infer dark-flats from a dark exposure matching a flat within **±20%** but not
  a light. Reclassification is project-scoped and idempotent; leave master darks
  and darks matching lights alone. Darks/dark-flats/bias have no filter.
- Ingest must accept incomplete equipment/filter metadata; do not restore a
  light-needs-filter CHECK. Keep unrecognized header values as hints.
- **No automatic equipment identification.** The old resolver, alias queue,
  per-frame equipment overrides, and most equipment FKs were removed. A project's
  rig assignments and each folder's declared `rig_id` supply equipment context.
- Source folders declare `rig_id` and `project_target_id`. The target must belong
  to the same project. PATCH changes only supplied fields (`model_fields_set`).
  `assign_rigs_and_sessions` is the single owner of frame rig/session/target;
  run after the full walk and when folder tags change, never per file during scan.
- **Longest matching folder prefix wins**, regardless of scan/tag order. Use
  `ingest_sessions.folder_prefix` for platform and archive boundaries: a bound
  archive root ends in `.zip`, while entries start `.zip::`. Archive entries
  inherit archive mtime when a header date is absent.
- Form sessions by **(project, observing night, rig)**, with the night running
  noon-to-noon in the site's geographic timezone. Never conflate simultaneous
  rigs. NULL rig is a valid group (`IS`, not `=`); choose a stable existing row
  and sweep legacy empty duplicate sessions.
- Targets apply only to lights. Use the folder's target, else a project's sole
  target. `OBJECT` is a hint, never an automatic target lookup.
- User corrections to `frame_type` and target survive rescans via their source
  guards. `filter_name_hint` remains **derived** from header FILTER plus effective
  frame type in both directions, even for corrected frames. Read stored header
  JSON so corrections work offline; never freeze the hint behind a type guard.
- `fits_header_map.FILTER_NAME_ALIASES` supplies display labels. The separate
  `line_names` service supplies canonical bandpasses. Keep its 15-value vocabulary,
  the TypeScript copy, and the database CHECK synchronized (including `R+`).
- `session` is the ingest rig/night group; `project_session` is a capture batch.
  Derive capture batches **only on request**, never during ingest. Replace auto
  rows and preserve manual rows. Derived rows are read-only (409 on edit/delete).
- Derived grain: **night, rig, canonical filter, exposure, gain, binning**.
  Fall back to the project's rig only when it has exactly one. Round REAL gain
  to INTEGER; asymmetric binning becomes NULL; skip/report zero-exposure lights.
  `filter_label` preserves unrecognized names while `line_name='other'` satisfies
  the existing CHECK. Unknown labels stay distinct in integration totals.
  Order canonical lines by `LINE_NAMES`, then unknown labels alphabetically.
- Integration is derived from exposure × sub count. Equipment-filter sessions
  expand into their passband lines, so duoband contributes to both line totals
  while wall-clock exposure counts once. Per-filter goals were removed.
  A capture batch must provide an equipment `filter_id` or generic `line_name`.
  Manual/derived overlap and stale derived rows after catalog changes remain
  explicit limitations; nothing silently re-derives.
- Calibration matching stays **per project and rig**, not a global calibration
  library. Darks match exposure/gain/binning/set-temp ±1°C; flats match
  gain/binning/filter hint, not exposure; bias matches gain/binning. Both sides
  require `accepted=1`. Compare nullable matching keys with `IS`.
- Removing a folder purges its file locations and orphaned subs/masters/sessions.
  In correlated orphan queries, qualify outer columns (`processed_image.id`):
  bare `id` can bind to `file_location.id` and delete the entire project's table.
- Deleting catalog entries does not exclude them from later scans. The source
  files remain; a rescan catalogs them again. Do not add silent exclusions.
- Reuse `FileBrowser` in `directoryMode` for folder/archive selection. The
  catalog uses category tabs and an infinite card list; MUI Community DataGrid's
  100-row page cap is not a substitute. Sort/filter on the server, blanks last.
- Catalog cells use their dedicated thumbnail endpoint, never the full-image
  endpoint: decimate raw data first, cache JPEGs by content hash/size, bound
  concurrency (3), and fetch lazily. Ingest is single-flight (409 if busy), with
  per-run process pools and database writes in the main process.

## Frame quality

- Analyze requested catalog subsets in **client-driven batches of 60**. Pending
  IDs, progress/ETA, cancellation between batches and resume are already supported.
  The analysis lock is independent of ingest. Do not introduce a background job
  system without a concrete need.
- `quality_analyzed_at`, not `hfr IS NULL`, marks completion. Star metrics apply
  to lights; median/background apply to every frame type. `ok`, `no_stars`, and
  `unreadable` are distinct outcomes; stamp failures so offline files do not
  retry forever.
- Keep `QUALITY_SETTINGS` frozen; changing detection settings makes stored
  measurements incomparable and requires invalidation. `analyze_array` is shared
  with the analyzer. Workers disable GPU and must not call `compute_image_stats`.
- HFR is stored in **pixels**. Convert on read using solved pixel scale, else
  `206.265 × pixel_size_um × binning / focal_length_mm` from the tagged rig;
  leave arcseconds absent if unknown. Multi-rig sorting uses arcseconds.
- Star count varies with PixInsight processing stage/noise floor; do not compare
  it as if raw and registered/calibrated data were equivalent.
- ADU metrics are on a 16-bit-equivalent scale: integer normalization recovers
  counts, while floating XISF values scaled by 65535 are equivalents. Display
  camera full scale from `2^adc_bit_depth − 1`, not the file container's bit depth.
  Source floats do not establish real camera ADU.

## DSO catalog and references

- Vendor only NightCrate editorial CSVs, not external catalogs. Download sources
  on demand to `APP_DIR/catalogs/`. Use staging-directory atomic renames and
  write `version.json` last so interrupted downloads remain visibly incomplete.
- Distance precedence is curated, then 50 MGC, then redshift; augmenters fill
  only NULL distances. Object types and designation catalogs are closed CHECK
  vocabularies: update migrations and loader maps together.
- Render external-reference chips only for `wikipedia`, `simbad`, `ned`, in server
  order. Store Wikidata QIDs without showing them as user-facing links. Verify
  Wikidata property IDs against the provider rather than trusting old specs.
- One article/entity may describe several objects; do not enforce cross-DSO
  uniqueness. A partial index on `(dso_id, provider) WHERE language IS NULL`
  supplies the deduplication SQLite's nullable UNIQUE constraint does not.
- See [catalog architecture](dso-catalog-architecture.md) for source layering.

## Locations, horizons, and target planning

- `geo_timezone` is coordinate-derived and controls observing nights/astronomy;
  `timezone` is the user's display choice. Remote sites may legitimately differ.
- Each location has at least one horizon and exactly one default; at most one
  custom polyline, any number of artificial flat horizons. Last-horizon deletion
  is 422. Location edits **stage horizons**; Save applies atomically, Cancel
  discards. This intentionally differs from immediate project saves.
- Store raw horizon points in `[0,360)`, never 360. Smoothing is derived, not
  persisted. Display wraps to `[-180,+180]` with virtual south-seam points.
- Visibility samples all active DSOs every five minutes during astronomical
  darkness, then filters in memory. Cache by location/date/horizon and both
  location/horizon update timestamps. Anytime/full-catalog mode must not inherit
  Tonight's magnitude/size defaults. Empty and NULL sort values always go last.
- Moon separation is closest approach during target visibility, not at transit.
  Before comparing a distance-bearing astropy Sun/Moon coordinate with an ICRS
  target, use `astronomy.direction_only`; frame-origin translation otherwise
  corrupts the sky direction. Same-frame Sun–Moon separations are safe.
- Moon rise/set needs a **48 h midnight-anchored grid** (the lunar day is longer
  than 24 h). Now-status calculations need both darkness boundaries.
- `astronomy.tonight_date` rolls site-local time back 12 h. Use its frontend
  mirror `tonightDate` for planner dates/now markers; `todayInTimezone` is an
  ordinary calendar date. Backend annual charts stamp their location-local
  `today`; format UTC-anchored date points with `timeZone: 'UTC'`.
- Planner settings persist through the DB KV store and `usePlannerSettingsSync`.
  Search text and Plan-a-Night date are ephemeral. New persisted fields need
  Python Settings, TS Settings, store, and `buildPayload` entries. Coalesce writes
  and skip no-ops; do not restore browser-only persistence for these fields.
- Wishlist chart snaps retain the original `Date`; a pixel→date round trip can
  land 1 ms before a boundary and break range tooltips.
- Planner thumbnails use IntersectionObserver (`rootMargin: '400px'`) to mount
  images near the nested scroll viewport. Native image lazy loading stalled
  below the first viewport here. Keep eager callers eager.
- Score in the backend for Plan-a-Night only. Moon impact combines global sky
  glow and target proximity (default 60/40), with filter-specific sensitivities.
  Meridian timing uses true transit plus a default 2 h boundary buffer.
- Observability minimum altitude must be at least 10° for the airmass formula.
  Cluster modifiers apply to `OCl`, `GCl`, `*Ass`, not `Cl+N`. Detail-panel
  rig/horizon overrides require a new single-target score; list scores are frozen
  to the list's context. See [planner scoring](planner-scoring.md).

## PHD2 analyzer

- Services parse/measure; `api/phd2.py` owns HTTP/DB. Parse CSV columns by name
  for each section, not position. Use the log's ErrorDescription, not a
  hardcoded ErrorCode map. Empty/DROP positions stay `None`, never zero.
- Pixels are canonical; derive arcseconds from each section's pixel scale.
  When scale is absent, show pixels only. Exclude dither settle intervals from
  quality statistics; retain source timestamps and section boundaries.
- Preserve PHD2 metric conventions: population-standard-deviation RMS,
  corrections-subtracted RA drift, unguided-frame Dec drift, sign-preserving
  peak, and declination-aware polar-alignment error. Backend/viewport math agree.
- Tabs are Section Info, Guiding, Dispersion (guiding sections only), and Data.
  Spectrum/FFT and unguided RA reconstruction were removed as unreliable; do not
  restore them from historical plans.
- Recent files persist in `phd2_recent_files`; the API client owns requests,
  while the lib helper handles legacy localStorage migration/display utilities.
  Export returns the visible section/time range as a PHD2-format log.

## Plate solving

- Run ASTAP through `asyncio.create_subprocess_exec`; **never pass `-update`**.
  Direct outputs to a temporary directory with `-o` and read the `.ini` sidecar.
  Resolve macOS `.app` executables under `Contents/MacOS/`.
- Convert archive/project images and XISF to temporary FITS, retaining focal
  length, pixel size and coordinate hints. Ordinary supported files pass
  directly. Use a fresh buffer for each header/dimension/image consumer.
- Allow one solve (`Semaphore(1)`); check/acquire without an intervening await,
  return 409 for concurrent requests, cancel only through the explicit endpoint.
- Image Analyzer solves display results without persistence; project solves
  persist WCS/object links. Keep these flows distinct. Reference-image mode
  requires matching dimensions; rig/equipment/manual hints supply scale/FOV.

## Weather: existing contract

This records the shipped behavior, not validation of its scientific assumptions.
Forecast redesign is deferred; sources and judgment calls are documented in
[imaging-quality-model.md](imaging-quality-model.md).

- Join hourly astronomy and weather by **absolute UTC**, not displayed HH:MM.
  Pad the astronomy grid ±1 h for context columns. Missing astronomy is not a
  below-horizon Moon. Fetch eight days to include the final night's sunrise.
- `score = 100 × availability × quality`. Availability multiplies darkness,
  precipitation, wind, and `(1 − effective_cover)^1.5`. Cloud must remain a gate:
  100% cover yields zero. Effective cover is the max of total and every layer;
  adding cloud must never improve the score.
- Score each hour, then aggregate; never score averaged nightly inputs.
  `expected_useful_hours` sums availability × quality. Darkness uses exact
  hourly overlap with twilight (−18°, or −12° in narrowband mode); Moon inputs
  are hourly, with score `100 × (1 − illumination × sin(altitude))`.
- `Unusable` follows availability below 0.10, not a numerical score bucket.
  Prefer the server label; frontend `scoreToLabel` cannot recover it. Use a
  sequential blue palette, darker for better scores, and hatch unusable hours.
- Primary cloud comes from ECMWF; other weather still uses Open-Meteo
  `best_match` for visibility. The source choice rests on one location/two weeks
  of comparisons, not a universal ranking. Do not switch to a model median
  without new evidence. Emit the cloud series actually scored in raw rows and
  nightly averages, leaving source inconsistencies visible.
- Model disagreement requires both a label difference and material score spread
  (`FORECAST_UNCERTAIN_MIN_SPREAD`). Judge nights from aggregated extremes,
  never `any()` over hourly flags.
- Scoring constants remain fixed. `api/weather.py:METHODOLOGY` is the UI's single
  methodology source. Supplementary PWV/AOD cache writes are non-fatal; serve
  available stale data instead of failing the forecast.

## Calculators, settings, and diagnostics

- Calculator math runs server-side. The sidereal clock ticks locally between
  60 s refreshes. Backend `HH:MM` strings are already display-local; pass them
  through without interpreting them as UTC. Use KaTeX for formulas.
- Clock order persists in DB settings; use single-container dnd-kit sorting
  plus click-to-add. Location-aware calculators declare `aware: true` and share
  `CalculatorLocationBar` / the session-only calculators location store.
- Moon Altitude (Year) reuses `planner_annual_hours.compute_moon_year` and
  `/api/planner/moon-year`; phase dates come from illumination extrema.
- Tonight links to Moon Altitude with a year and Weather with location/date.
  Read and clear URL params. Weather is persistent and loads asynchronously:
  retain `pendingDate` in state until the matching forecast arrives, then apply
  only dates in its range. Declare this effect after default-location selection.
- Cache budgets/clear controls belong in **Admin → Caches**, not Settings.
- Diagnostics middleware records requests. Use `X-Activity` for fetch and
  `_activity` for image URLs; keep an image's activity label stable from file
  open so cache busting does not split request groups.
