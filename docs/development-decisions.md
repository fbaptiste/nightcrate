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
- The analyzer starts star detection (`/api/images/quality`) only after the
  displayed image has loaded. On a 95 MP master, detection takes about 6 s.
  Started alongside the full-size render, it slowed the picture from about
  1.3 s to about 7 s (v0.50.0). The Image Info panel's last row, File size,
  comes from `/api/images/metadata` (`file_size_bytes`). The size is taken
  before the header read, because FITS header reads close a passed buffer.
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
- The XISF reader follows the published *XISF Version 1.0 Specification*,
  revision 2 (1.02, October 2026). It covers the §7.2 baseline decoder plus the
  stored solution's first layer. Data blocks are read through
  `xisf_blocks.read_block` (`verify_block` checks one without decompressing):
  - locate it (inline base64/hex, embedded `Data`, or attachment);
  - verify its checksum over the stored bytes;
  - decompress its subblocks from the `subblocks` attribute. `c == u` pieces
    are stored as-is; output is bounded, and input must be fully consumed;
  - unshuffle the whole block, leaving a trailing partial item as is.
  There are no in-data subblock size headers.
  - **Errors:** `XISFError` is a `ValueError`, so routers return its plain
    message as a 422. A checksum failure in an image's pixel block
    (`XISFChecksumError`) means damaged: that image is refused everywhere. A
    damaged or unsupported property block makes only that property
    unavailable; the header and the solution still read.
    `XISFUnavailableError` means an unsupported feature, and the rest of the
    file stays readable.
  - **Header reads** (`read_header`, ingest, the Header tab) never read attached
    blocks; they show summaries. Canonical metadata comes only from decoded
    values.
  - **String properties** are element text, never base64-decoded unless their
    `location` says so.
- XISF stored solutions are looked up in this order:
  1. `AstrometricSolution:*`, written by PixInsight 1.9.5 and later;
  2. the legacy `PCL:AstrometricSolution:*`;
  3. the FITS keyword WCS.

  Only layer 1 is used: **CD = matrix as-is, CRVAL = reference sky coordinates,
  CRPIX = reference image coordinates + 0.5.** XISF pixel (i, j) covers
  [i, i+1) × [j, j+1), while FITS pixel centres are whole numbers from 1. There
  is no transpose or y-flip.
  - **Evidence for +0.5** (v0.50.0, 36 files: 4 with the new names, 32 legacy):
    against native solves, the median offset was 0.00 px; with +1 it was
    −0.5 px.
  - **Rules for the new namespace:** `Version` major 1; gnomonic only; default
    native coordinates only; finite values and a non-singular matrix.
  - **An unusable new-style solution** returns a reason and never falls back to
    the legacy names or FITS keywords.
  - **FITS keyword WCS:** convert CDELT/CROTA to CD, then flip to displayed
    top-down rows (`CRPIX2 = H + 1 - CRPIX2`; negate the second CD column).
  - The XISF `geometry` dimensions are authoritative over stale FITS `NAXIS`
    cards. Nonlinear spline distortion is not modeled for annotations.
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
- **An object's ellipse** comes from the solution's local geometry at the
  object (`services/image_annotations.py`): map 1′ east and north offsets to
  pixels, then take the SVD of that Jacobian times the object's axes. That
  gives the semi-axes and angle in displayed (y-down) pixels, so rotation,
  mirroring and unequal scales come out right. Before v0.49.0 the position
  angle minus the picture's rotation was used, as if every ellipse started
  north–south, and most rings were drawn at the wrong tilt.
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

- Users run the app through the Vite development server (`make dev`); the
  backend does not serve a built frontend. Vite's development-server advisories
  therefore reach users. For example, Vite 8.0.3's open-in-editor route could
  leak a Windows password hash to any web page visited while NightCrate ran.
  So `vite`, `@vitejs/plugin-react`, and `@vitejs/plugin-basic-ssl` are listed
  under `dependencies`, which means `npm audit --omit=dev` covers them.
  `make install` uses `npm ci` so that installs never rewrite the lockfile.
- `AppShell` keeps the Image Analyzer, Planner, PHD2 Analyzer, DSO Catalog,
  Weather, Gallery and Messier pages mounted after their first visit, hidden with `display: none`, so
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
- **A new seed row named like a user's own row** links to it instead of
  stopping startup (v0.47.0): `SeedableTable.natural_key` is set only for
  `manufacturer` (`name`) and `software` (`manufacturer_id`, `name`). On that
  UNIQUE failure the seed key maps to the user's row in `fk_map`; nothing is
  written to it and it stays out of `inserted_or_updated`, so its junctions are
  never replaced. Other tables still fail loudly: linking a user's telescope
  would collide with its configurations (child path and native-configuration
  index), which needs its own design.
- **Software versions** (`software_version`) are user data, unique per
  program, listed newest first (`id DESC`). They save in the equipment
  factory's `before_commit` hook, in the same transaction as the program;
  `versions` omitted or `null` leaves them, `[]` removes them all, and a
  version a project uses can't be removed (409 `version_in_use`).
  `project_software`'s composite foreign key keeps a version on its own
  program; a program may appear twice with different versions, never twice
  with the same one or with none.
- Software pickers group by category in a fixed order: the rig form lists
  capture, guiding, plate solving, planetarium, utility, other, processing;
  the project field lists processing first (`orderSoftwareOptions`).

## Rig history and project setups

Since v0.47.0. Spec: [v0.47.0 design](superpowers/specs/2026-11-07-v0.47.0-design.md).

- **A rig keeps one identity.** Never copy rig rows for history or project
  changes: calibration matching, the gallery rig filter, every picker and the
  UNIQUE rig name assume one row per rig. History is `rig_setup` rows attached
  to the rig; a project's own changes are one `project_rig_change` row per
  project and rig.
- **In use** means any `project_rig`, `project_session`, `session`,
  `sub_frame` or `project_source_folder` row. Wishlist plans and planner
  settings look forward and always use the current setup.
- **Equipment changes on a rig in use need `apply_mode`.** Without it,
  `PUT /api/rigs/{id}` returns 409 `rig_change_needs_choice` (counts and the
  changed parts) and writes nothing. Name, description, notes, default and
  order never ask. The whole update is one `BEGIN IMMEDIATE` transaction from
  the first read of the old state, with slot validation before any write.
  - `from_now_on`: `save_earlier_setup` copies the current parts into a
    `rig_setup` and stamps every frame whose setup rig is this rig, and every
    batch of the rig; frames cataloged later have no stamp and use the
    current setup.
  - `existing`: the edit applies to the rig, and in each earlier setup a
    part group changes only where it still has the rig's old value.
- **Part groups:** telescope, camera, filters (wheel, single filter and slots
  together, because slots depend on the wheel), mount, focuser, guider (OAG
  or guide scope), guide camera, computer, software. Swapping the guider
  leaves the guide camera following the rig.
- **Stamps:** one `sub_frame_rig_setup` row per frame and rig, so a frame
  keeps its earlier setup for each rig it has been on. A stamp applies only
  while the frame is on that rig; `assign_rigs_and_sessions` never clears
  stamps, so re-tagging a folder away and back restores them. A batch has one
  `project_session.rig_setup_id`, kept a setup of its own rig (a rig-only
  PATCH clears a foreign one).
- **A frame's setup rig** is its `rig_id`, else the project's single rig (the
  derive fallback). Frame computations use `rig_id` only, so untagged frames
  still have no pixel scale; batches use the setup rig. When the project gains
  a second rig, untagged frames' batches lose their rig and setup, as the
  fallback refuses to guess; the stamps remain and tagging the folder restores
  both.
- **Effective equipment for records** comes from `sub_frame_equipment`:
  the project's change, else the applying stamp, else the rig. It feeds pixel
  scale, star sizes in arcseconds, the arcsec HFR sorts, full-scale ADU and
  the calibration views. Focal estimates and the project setup panel use
  `project_setups`. Rig calculators, the planner, star-catalog coverage and
  the wishlist use the rig's current setup.
- **Moving a night** (`PUT /api/projects/{id}/sessions/{session_id}/setup`)
  re-stamps every frame of that observing night on that setup rig,
  calibration frames included, and that night's derived batches; a manual
  batch's setup is its own column. This is how old files cataloged after a
  change are put right. Its menu offers every setup of the rig
  (`setup_options`), not only those the project used.
- **The project Overview** (Fred, 2026-11-08) puts the plate-solve line under
  the main targets and the processing software, description and integration
  in the side column; equipment is its own section below the picture, one
  row per rig with its camera, image scale, field of view and nights, and a
  row's setup panel opens directly under the rig list (scrolled into view),
  not at the foot of the page.
- **Project changes** store only swapped groups; a group set back to the
  rig's value is dropped, and no groups left deletes the row. They apply to
  all of the project's nights on that rig, whatever the setup, are never
  touched by rig edits, and go with the project.
- **Night counts** are distinct (project, observing night) over frames (by
  setup rig) and all batches, derived and manual; a stale derived batch with
  no frames left still counts, because the Sessions tab shows it.
- **Equipment usage** (`GET /api/equipment/{kind}/{id}/usage`) counts rigs
  whose current setup, earlier setups or project changes use the record, and
  projects whose resolved setups do (plus manual batches' filters). It uses
  grouped queries over all projects: calling `project_setups` per project
  took about 0.9 s on a 500-project library.

## Projects, catalog, and sessions

- Projects persist edits immediately: text on blur/Enter; gallery/order/main/crop
  actions on click. No staging area or global Save/Cancel. Abandoning a new
  project means deleting it.
- Gallery images are finished display images. The plate-solve image is separate,
  normally linear FITS/XISF. One solve per project today; mosaics are deferred.
- `project_solve` stores WCS; `project_dso` stores the in-frame objects found
  at solve time, from the 500 largest in the cone
  (`api/plate_solve.py:query_dsos_in_cone`). Searches compute membership from
  the WCS instead (see Gallery and project images).
  Pick the automatic main by nearest center, then largest on a tie. Reproject
  overlay coordinates from stored WCS on read, off the event loop.
  The stored solve is view-only; delete it with confirmation before re-solving.
- `project_target` is the single source for main targets (overview chips and
  solve-tab stars). Main targets survive deletion of a solve; derived solve
  objects and its rendered image do not. Reuse `DsoAnnotationOverlay` in both
  analyzers; main objects are teal and others blue.
- Catalog objects keep their row identity by `(source_catalog_id, source_key)`,
  such as the exact OpenNGC `Name` or a normalized catalog number (each
  source's key is in the [catalog architecture](dso-catalog-architecture.md)).
  Reconciliation runs each matching pass across the complete object set;
  shared or former designations never prove identity. When an object's owner
  changes, its id follows its contributing entries (`dso_source_entry`), so
  removing and re-adding a catalog keeps ids and links. The one-time legacy
  pass is guarded by `dso_catalog_source.keys_assigned`. A loaded object source
  of a catalog that is on, with a missing file or an unfinished download,
  defers the whole object step rather than guessing; a removed catalog never
  defers.
- Only explicit OpenNGC duplicate rows, Sharpless cross-references, an
  unambiguous full Barnard identifier matching an OpenNGC object's parsed own
  name, and rule R for the catalogs added in v0.44.0 merge catalog objects.
  Rule R takes a reviewed override, then an own name already owned, then a
  catalog column naming an owned designation; position alone never merges.
  Alternate names never prove a Barnard merge, and an object's parsed own
  designation outranks another object's alternate claim. A merged entry adds
  names and provenance, never columns or notes. Known user links move to the
  survivor. Other unclaimed rows become inactive and retain their names,
  enrichment, and user relationships.
  Any new table with a foreign key to `dso` must be classified in
  `catalog_loader.user_links` as user-linked or catalog-derived; the fresh-DB
  foreign-key guard test must fail until that classification is made.
- **Removing a catalog** is the only path that deletes catalog objects. It
  needs positive evidence that removed catalogs alone provided the object:
  every `dso_source_entry` row of the object belongs to one, or, for a row with
  no entries, every catalog of its own source is removed. An empty set never
  counts. Unlinked objects are deleted. Objects referenced by
  `favorite_target`, `project_target` or an unclassified table stay inactive,
  with their names.
  - **A solve's in-frame list is not a link.** `project_dso` is computed when
    the solve is made; counting it would keep thousands of inactive MCG
    galaxies from galaxy-field solves after MCG is removed. Its rows go with
    the object. Merges still move them.
  - Existing solves are not recomputed when a catalog is added.
- **Never infer a catalog choice.** The choice is app-wide
  (`catalogs/choice.json`, beside the shared downloads); each database records
  what it applied in `dso_catalog_applied`. A missing or corrupt choice file,
  missing files or missing `version.json` entries keep what the database
  applied, and nothing is removed. Upgraded databases keep Sharpless and
  Barnard on with no choice file written. A database opened later applies a
  recorded removal once, without asking again. Rules:
  [optional catalogs](dso-catalog-architecture.md#optional-catalogs).
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
- Scans verify each XISF image's pixel checksum (`xisf_io.verify_image`) without
  decompressing it. A file a scan can't catalog becomes a row in
  `uncataloged_file`, one per (project, path), with reason `damaged`,
  `unsupported` or `unreadable`. The project's Files tab lists them under
  "Not cataloged".
  - **Coverage:** a directory scan covers paths without `::` under its prefix.
    An archive folder covers its `folder_prefix`.
  - **Rows kept:** directories a scan couldn't list, and subtrees it
    deliberately skips (hidden folders, `.pxiproject` bundles), keep their rows.
  - **Unreadable folder:** an offline or unreadable folder changes nothing and
    reports a folder-level error.
  - **Transactions:** each folder is one transaction, with a savepoint per file.
    The post-pass doesn't change which files are cataloged.
  - **Folder removal** deletes the rows no other bound folder can retry.
- Adding project images verifies the XISF behind every path before inserting,
  including `.pxiproject::index` references to an XISF. The request is all or
  nothing: 422 `"{file}: {message}"`. Other resolution failures keep the earlier
  insert-then-render behaviour.
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
- **Night notes** (`project_night_note`, v0.47.0) hold one note per project
  and observing night, keyed by the civil night date (`YYYY-MM-DD`; the API
  rejects anything that doesn't round-trip, such as week dates). They live
  apart from capture batches so a rebuild never touches them, and a note
  whose night has no batches left keeps its block on the Sessions tab. The
  rig is not part of the key: a note records the night's conditions.
- The **Sessions tab** groups batches by night (newest first), then rig. Its
  totals use wall-clock minutes and physical subs (sessions' `num_subs`),
  never the passband lines, which credit a duoband batch twice. The
  per-night setup picker calls the batch setup endpoint once; the backend
  moves that night's derived batches and leaves hand-entered ones, which
  show their own setup when it differs.
- **Filter colours** (v0.47.0) live in `components/projects/filterColors.ts`
  and are used by the Sessions tab, the Overview's Integration bars and the
  Files tab. Colour follows wavelength, from the Okabe-Ito palette: B blue,
  OIII sky blue, G green, R orange, Hα vermillion, SII reddish purple; L
  black (near-white in dark mode). Hβ, OI and NII take their neighbour's
  colour with stripes; no filter, UV/IR cut and light-pollution filters take
  L's with stripes; unknown names get a grey outline. An equipment filter
  with several lines is split between their colours, red first. Don't use a
  mid grey for L: for green-weak vision it matches G. Check any palette
  change with a colour-vision validator (Machado 2009, deutan and protan);
  the filter's name always sits beside its colour. Order: L and the other
  whole-spectrum filters, then R, G, B, then narrowband from red to blue
  (SII, NII, Hα, OI, OIII, Hβ); a multi-line filter sits with its reddest
  line.
- Derived grain: **night, rig, canonical filter, exposure, gain, binning**.
  Fall back to the project's rig only when it has exactly one. Round REAL gain
  to INTEGER; asymmetric binning becomes NULL; skip/report zero-exposure lights.
  `filter_label` preserves unrecognized names while `line_name='other'` satisfies
  the existing CHECK. Unknown labels stay distinct in integration totals.
  Order canonical lines by `LINE_NAMES`, then unknown labels alphabetically.
- Integration is derived from exposure × sub count. Equipment-filter sessions
  expand into their passband lines, so duoband contributes to both line totals
  while wall-clock exposure counts once. Per-filter goals were removed.
  The sub-count breakdown (`exposures`) instead labels the filter as shot: an
  equipment filter by model name, so a duoband filter is one row and its subs
  count once. It merges nights, rigs, gains, and binnings; exposures are keyed
  to three decimals as the derive groups them. A filter with no recorded
  passband (UV/IR cut, L-Pro) adds to the total and the breakdown but to no
  bar, so "no integration" means a zero total, not empty `lines`. Minutes are
  returned unrounded; the UI rounds them and shows nonzero time under 30 s as
  "<1m".
  A capture batch must provide an equipment `filter_id` or generic `line_name`.
  Manual/derived overlap and stale derived rows after catalog changes remain
  explicit limitations; nothing silently re-derives.
- Calibration matching stays **per project and rig**, not a global calibration
  library. Darks match exposure/gain/binning/set-temp ±1°C; flats match
  gain/binning/filter hint, not exposure; bias matches gain/binning. Both sides
  require `accepted=1`. Compare nullable matching keys with `IS`. Since
  v0.47.0, darks and bias also compare the effective camera and flats the
  effective camera and telescope configuration (`sub_frame_equipment`), so a
  "from now on" camera change never pairs old darks with new lights on a
  tagged rig. Known limit: frames from untagged folders have no rig, so
  their effective camera is NULL on both sides and they still match by
  settings alone, as before v0.47.0 (v0.47.0-R2; revisit with the
  calibration coverage UI).
- Removing a folder purges its file locations and orphaned subs/masters/sessions.
  In correlated orphan queries, qualify outer columns (`processed_image.id`):
  bare `id` can bind to `file_location.id` and delete the entire project's table.
- Deleting catalog entries does not exclude them from later scans. The source
  files remain; a rescan catalogs them again. Do not add silent exclusions.
- Reuse `FileBrowser` in `directoryMode` for folder/archive selection. The
  project's **Files** tab (named Catalog before v0.47.0; the side menu's DSO
  Catalog is something else) uses category tabs and an infinite-scroll table,
  with a thumbnail sheet for lights; MUI Community DataGrid's 100-row page cap
  is not a substitute. Sort/filter on the server, blanks last. Capture-time
  sorts order by `julianday(date_obs_utc)`, not text: stored timestamps mix
  `T`/space and zone suffixes, and text order can split a night. Night
  headings come from `CatalogFrame.observing_night` (the derivation's
  geographic zone and noon rule) and appear only between consecutive loaded
  rows, so a page boundary never repeats one. The pixel-only HFR sorts left
  the UI in v0.47.0; the arcsec order falls back to pixels when a frame's
  scale is unknown. The table keeps the cards' quality meanings: empty
  cells before analysis, "unreadable" and "no stars" in words, ADU against
  the camera's full scale.
- Catalog cells use their dedicated thumbnail endpoint, never the full-image
  endpoint: decimate raw data first, cache JPEGs by content hash/size, bound
  concurrency (3), and fetch lazily. Ingest is single-flight (409 if busy), with
  per-run process pools and database writes in the main process.

## Gallery and project images

Design: [v0.46.0 spec](superpowers/specs/2026-11-04-v0.46.0-design.md) and its
2026-11-07 amendment.
- **Terminology (Fred):** a project is *plate solved* when it has a
  `project_solve` row: a plate-solved image from its Plate Solve tab.
- **Imaging dates** come only from `project_session.session_date`, manual and
  derived alike. A value counts only when its first ten characters match
  `YYYY-MM-DD` and parse (`services/gallery.py:valid_session_date`).
  - Edit, creation and file dates never stand in.
  - Dates show as runs of consecutive months ("Jan–Feb 2025, Jan 2026"),
    or as exact dates when every night is in one month. Runs are built by
    `imaging_runs`, which the integration summary reuses.
- **Integration** on cards is the project page's total. Each session counts
  once, and manual and derived rows that overlap still count twice. No
  gallery filter or sort uses integration until that overlap is resolved.
- **The gallery endpoint** loads every project, retired included, in a few
  batched queries. It filters, counts facets and sorts in the pure
  `build_gallery`, without paging.
  - Facets exclude their own filter and count a project once per option.
  - Targets on inactive (removed-catalog) objects still match.
  - Rigs are one list: rigs declared on the project, plus rigs its sessions
    name.
- **Search** (object search, [v0.49.0 spec](superpowers/specs/2026-11-10-v0.49.0-design.md)):
  - **Submitted searches:** designations match exactly
    (`dso_search_clause(..., exact_designations=True)`), so "M1" finds M 1
    and never M 10–M 19. Names and aliases match anywhere. Main targets on
    inactive (removed-catalog) objects still match.
  - **Project names** match anywhere, except when the query is a
    designation.
  - **Suggestions while typing** (`GET /api/gallery/suggest`, two
    characters or more) match designations from the start.
  - **"Also search plate-solved projects"** adds projects whose solve
    contains a matching active object. Membership is computed at search
    time from the stored solution (`services/object_search.py`), never
    from `project_dso`: those rows were computed once at solve time, from a
    capped list and the catalogs present then.
    - `objects_near` is a provable superset: an object's distance from the
      sky position of the image's centre pixel is at most (half diagonal +
      √2 × its half-size in pixels) × the larger singular value of CD.
    - The shared `project_dsos` then decides membership, as the Plate Solve
      tab does. Nothing is capped.
  - **Results** say "Main target", "In the plate-solved image", or both.
    In-image results show the solve image with the object marked
    (`SolveMarkedImage.tsx`). The solve image route takes `solve_id` and
    answers 204 when the project's solve has changed, so an old mark is
    never drawn on a new picture.
- **Images (Fred, 2026-11-07):** each view shows the user's framing for its
  size, otherwise the whole main image.
  - **Sizes and views:**
    - small: the Gallery list, Gallery small and Projects Compact;
    - medium: Gallery medium and Projects List;
    - large: Gallery large and Projects Pictures
      (`lib/galleryRendition.ts:cropSizeForView`).
  - **Every image box is 4:3** with `object-fit: contain` on black (only
    when there is an image). A framing file is exactly 4:3, so it fills its
    box.
  - **An unframed image** uses `thumb_sm/md/lg`, picked from the measured
    tile width and the pixel density (`pickRendition`). Renditions bound the
    long side, so `srcset` widths would be false for portraits.
  - **The full-size viewer** shows the image the view's framing was made
    from (`viewerImageId`), otherwise the main image.
  - **Images load as they come near the viewport,** on both pages
    (`components/common/NearViewportImage.tsx`, 400 px margin).
    - Its wrapper must stay a plain block box. As a grid, the image's
      `height: 100%` stopped resolving, and portraits overflowed their
      boxes.
- **Browser caching:**
  - project images are served `no-store`, because `FileResponse` sends no
    304s;
  - URLs carry `ws` (a token renewed by every `set_db_path`) and, for
    thumbnails, `v`. They exist only so an open page notices a change; the
    server ignores both.
  - Caching forever was considered during plan review and dropped: it
    needed version checks, workspace lifetimes and per-request workspace
    pinning.
- **Crops (framings):**
  - **Shape:**
    - every frame is 4:3 in real pixels, stored as fractions of the source
      image's width and height;
    - a frame may extend onto the mat, so a fraction can be negative or
      above 1.
  - **Limits:**
    - the frame stays inside the *fit box*, the smallest 4:3 box holding
      the whole image, centred (`services/project_images.py:fit_box`);
    - it must include part of the picture;
    - the server checks shape and fit box against the loaded image within
      1%, because the editor measures the aspect from `thumb_lg`.
  - **Output:**
    - `render_crop` maps the frame as sent and never recomputes its height;
    - it pastes the image's overlap with the frame onto a black canvas of
      the output size, never one the size of the frame;
    - output sizes are 480×360, 800×600 and 1200×900.
  - **Saving:**
    - each save creates a new row and file,
      `thumb_crop_{size}_{row_id}.jpg`;
    - temporary files are generated first. Rows are then replaced and files
      renamed in one transaction, which rechecks the main image; any
      failure changes nothing, and cleanup covers allocating temporary
      files;
    - after commit, the save deletes every `thumb_crop_*.jpg` in the
      project folder that no current row owns, never `.tmp` files.
  - **`remove_image` and `set_main_image`** take the write lock (`BEGIN
    IMMEDIATE`) before reading. A crop saved in between could otherwise
    survive its image's deletion as a follow-the-main crop (Codex
    reproduced this).
    - Removing an image deletes the crops that name it.
    - A new main image deletes the follow-the-main crops.
  - **A crop counts only when its file exists.** The gallery omits it, and
    `/thumbnail` serves the main rendition. There is no old-name fallback.
  - **Migration 0068** deleted every crop made before v0.46.0. They
    couldn't be trusted: the old editor kept each shape in image
    proportions, not pixels, so most were squashed. It uses DELETE, not a table rebuild, so crop ids, and so
    thumbnail versions, never repeat.
- **The thumbnail editor** (`ThumbnailCropEditor.tsx`,
  `lib/thumbnailFrame.ts`):
  - **The canvas:** the fit box, drawn black with the image inside it. The
    frame is a square in canvas units (u, v, s).
  - **Input:** pointer events with capture and `touch-action: none`. The
    frame must never remount mid-drag. Arrow keys move it, and + and −
    resize it.
  - **State:** one reducer for frames, unsaved sizes and the error. Each
    input event is one transition, and no-ops return the same state.
  - **Updaters stay pure.** A ref mutated inside an updater lost the
    restored frame under StrictMode's double call.
  - **No `FormControl` around the image `Select`.** In development its
    context changes every render, and `InputBase` re-ran an update after
    each one. Fast key repeat then hit React's nested-update limit.
  - **Saving:** only changed sizes are sent. The dialog stays open until
    the save succeeds, and shows the server's message if it fails.
- **View pickers** (`components/common/ViewToggle.tsx`), used by the Gallery
  and Projects pages: joined icon buttons, the selected one filled with the
  primary colour, each with a tooltip and an accessible name. Clicking the
  selected button again does nothing. The Projects page's views are
  Compact, List and Pictures.
- **Plate-solve focal length:**
  - **Formula:** 206.265 × pixel size (µm) ÷ solved scale (″/px)
    (`rig_calculators.py:estimate_focal_length_mm`).
  - **Which rigs:** one estimate per rig on the project, declared or named
    by a session, retired and not-mine included, in the gallery's order.
    It is built in the solve response.
  - **Freshness:** rig, session and project edits invalidate
    `project-solve`.
  - **Label:** an estimate. It assumes the image's pixels are the
    camera's; binning, drizzling or resizing changes it.
- **The page** is persistent, and keeps its own scroll position.
  - It records `scrollTop` while visible. A hidden page reads 0, so it must
    never save on hide.
  - Turned cards survive a refetch; the viewer closes when the page hides.
  - No window-level key listeners: the viewer handles ← and → in its own
    `onKeyDown`.
  - The viewer's arrows are pinned to the window, so repeated clicks need no
    pointer movement.
- **Line fitting** (`components/gallery/LineFitList.tsx`) shows as many items
  as fit in two lines, then a "+N" pill: first items for targets, latest
  runs ("+N earlier") for dates.
  - The ", " separator must sit outside each item's no-wrap span. Inside
    it, the list can't wrap: it measures as one line, is never shortened
    and overflows, clipped.
  - A line counts as the larger of the text's line height and 19 px,
    because the 18 px pill makes small-text lines taller.
- **Missing renditions** show "No preview" everywhere: gallery tiles, the
  project page's main image and its thumbnail strip. A 204 never leaves a
  spinner running.
- **The scratch workspace script** copies the source database with SQLite's
  backup API from a read-only connection. A live database's WAL is
  included, and the source is never written.
  - It gives about a third of the projects framings, made with the real
    renderer.
  - The source must already be at the current schema. A copy at 0067 lost
    its framings to 0068 on the first server start.
- **The nav order:** a route missing from a saved `nav_order` is inserted
  after its nearest default predecessor (`AppShell.tsx:normalizeNavOrder`),
  so new pages don't land at the bottom.
- **The project page:**
  - the status chip beside the title is the status choice;
  - a "Plate solved" pill (filled teal, or a dashed grey outline) opens the
    Plate Solve tab;
  - `MarkdownEditor` puts its edit toggle right after its label, as in
    "Main targets +".

## Messier checklist

Design: [v0.48.0 spec](superpowers/specs/2026-11-09-v0.48.0-design.md).
- **Slots:** 110, from `services/messier.py:MESSIER_NUMBERS`, matched to
  objects through their Messier designations; M 102 is NGC 5866 (v0.45.0).
- **Which project fills a slot:** only active projects with the object
  among their main targets. Projects with a main image come first, then
  the latest valid session date (dated before undated), creation time,
  and id (`order_candidates`).
- **Never rises:** `90 − |latitude − Dec| < −1`, a conservative test with
  a one-degree margin, for the location chosen on the page. It ignores
  the horizon profile.
- **Without a rig,** survey images span `max(1.5 × major axis, 0.15°)`,
  5′ when the size is unknown.
- **Rig view** (v0.49.0, [spec](superpowers/specs/2026-11-10-v0.49.0-design.md),
  "Rig view and the not-imaged ribbon"): with a rig whose field is known,
  survey pictures show the rig's whole view with the sky filled in, the
  frame drawn on it (`RigFieldBox`, `lib/messierFov.ts`).
  - The picture spans `rig_view_field_deg` = max(major, minor × 4/3) / 0.92
    across its 4:3 width. Only 0.05°–30° is supported; outside it, the
    close-up survey picture is shown with the frame drawn to scale
    (`fovGeometry`).
  - "{n}% of the field" is the Planner's `compute_coverage_pct`, shown
    when the object has a size, own pictures included.
  - **Own pictures never get the rig view** (Fred): with "Imaged as: Own
    image" they look as they do without a rig. Their tile has a teal
    border, 4 px (3 px small), round with the tile, around the whole tile
    rather than a letterboxed picture.
  - **The server owns the field.** The thumbnail route takes `rig_id`
    (checklist variant only) and derives the field from the active rig.
    With `render_key`, a mismatch (an equipment edit between loading the
    page and loading a picture) answers 204 `no-store`, never another
    field's pixels.
- **Not imaged:** a corner ribbon on survey pictures of slots not imaged,
  top-left, so it never covers a small central object.
- **In a solved picture:** a slot not imaged whose object lies in one of
  the user's plate-solved pictures (`marks_in_solve`, as in the Gallery's
  search) gets a pill on its tile, a teal outlined box with a dot on the
  map, and a count in the progress line.
- **The progress map** jumps to a box's tile: instant scroll (a smooth one
  used up the highlight), focus, and a 1.5 s ring. It never changes
  "Show"; a box whose tile the filter hides does nothing and keeps the
  default cursor.
- **Survey images** are the `checklist` thumbnail variant: 800 × 600,
  identified by `ChecklistRender` (centre and field quantised, plus a
  render revision). The same `render_key` names the cache row
  (migration 0071), the file and the browser URL, with the workspace key.
  Change the framing rule by bumping `CHECKLIST_FRAMING_REVISION`, never
  by reusing a key.
- **Loading survey images** (`lib/surveyRequestQueue.ts`,
  `MessierSkyImage`):
  - at most three requests in flight for the whole page, nearest the
    visible part first. Browsers allow six connections per server; in
    v0.48.0's first look about 100 long-polled requests from tiles
    scrolled past held all six, and the full-size viewer waited about a
    minute;
  - a tile's first request asks without waiting (`wait_ms=0`), so every
    tile near the view tells the server about its picture at once; while
    the answer is 202 it long-polls (`wait_ms=4000`) at least 1 s apart,
    for 75 s at most. First requests go ahead of polls in the queue;
  - every poll goes through the queue; a 202 releases its place;
  - a tile leaving the 400 px look-ahead cancels its request, and asks
    again with a fresh 75 s budget when it returns;
  - the `IntersectionObserver` root is the page's own scroll box.
    `rootMargin` only grows an explicit root; with the default root the
    scroll box still clips;
  - the browser keeps finished pictures: requests use the default cache
    mode, and the server sends `public, max-age=86400` on 200 and
    `no-store` on 202 and 204. The thumbnail cache's generation (`_g`) is
    in the URL, so clearing the cache in Admin replaces them;
  - a loaded image survives hiding and showing the page and the
    checklist's refetch on each visit. Its identity is the object, the
    render key, the workspace and the cache generation. On a changed
    identity the tile drops its picture at once, and the object URL is
    revoked after the `<img>` is gone, never before: v0.49.0 found a
    revoked URL shown again after a quick rig switch back, which left
    tiles blank for good. A refetch never repeats an in-flight request;
    it only retries tiles that failed. Readiness comes from the image's
    own `onLoad` and resets before paint when the image goes.
- **The server renders the most recently requested picture first**
  (`services/thumbnails.py`, `_MostRecentRequestGate`, all thumbnail
  variants, eight at a time). A request for a picture already waiting
  moves it up; nothing is dropped. A page abandons requests when tiles
  scroll away or the rig changes, but the server can't tell, and in
  arrival order the tiles on screen waited behind that work (Fred's
  report, v0.49.0). Each render's clean-up releases only the slot it
  reserved, never a newer render of the same picture.
- **The header is pinned** inside the page's scroll box. The scroll box's
  `scroll-padding-top` follows the header's measured height, so keyboard
  focus and the viewer's return never leave a tile under it.
  - Container queries on the header choose the layout: three areas from
    1,100 px, a compact form with a smaller map from 950 px, two rows
    below. The map column is fixed to the boxes' width; the legend wraps
    inside it.
  - The header's content is at most 1,552 px, the tile grid's width.
- **Shared pieces with the Gallery:** `FlipTile` and the viewer. Viewer
  entries have their own key, so two slots showing one project image
  stay distinct.
- **The Planner's project pill** reads `GET /api/project-target-links`
  (active projects' main targets, with names, status and imaging dates).
  Every change to those calls `invalidateProjectLinks`: targets
  (`ProjectDetailPage`, `ProjectPlateSolveTab`), sessions
  (`ProjectSessionsTab`), name or status, retiring and restoring
  (`ProjectDetailPage`), and creating a project (`ProjectsPage`). The
  Planner also refreshes the links each time its card tabs show.
  - Its `select` must be a module-level function. An inline one returned
    a new Map every render and looped the Planner ("Maximum update depth
    exceeded").
- **"Open in Planner"** navigates to `/planner?object=<dso id>`. The
  persistent Planner opens that object's details once its settings have
  loaded, then removes the parameter.

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
  on demand to `APP_DIR/catalogs/`. The Melotte list is NightCrate's own
  transcription of Melotte's 1915 catalogue: no downloadable Melotte table
  exists, and Wikipedia's list is CC BY-SA.
- **VizieR catalogs publish as one commit.** Stage every table of the catalog,
  write its `vizier/publishing/{catalog_id}.json` marker, move the files into
  place, then write `vizier/version.json` atomically and delete the marker.
  The `version.json` write is the commit point. The loader consumes only
  catalogs whose files match their `version.json` sha256 and have no marker,
  so an interrupted publication stays unavailable instead of half-loaded.
  Sharpless and Barnard alone also accept files from before v0.44.0 with no
  entry. GitHub downloads still write `version.json` last.
- **Screen before applying.** Run `catalog_loader.match_review` on every new
  catalog's full download before its first application to any database, and
  turn each confirmed error into a `dso_match_overrides.csv` row. Overrides
  take precedence over matches a catalog or OpenNGC states and reserve their
  designation: LBN 191 is the whole Cygnus Loop, never NGC 6960.
- Distance precedence is curated, then 50 MGC, then redshift; augmenters fill
  only NULL distances. Object types and designation catalogs are closed CHECK
  vocabularies: update migrations and loader maps together (0066 added `hh`,
  `aco`, `png` and `wr`, and the types `HH`, `ClG` and `WR*`).
- **One "Emission nebula" type choice** (Fred, 2026-11-03). OpenNGC types
  nearly every emission nebula imagers target as `HII`, and uses `EmN` only
  for 8 nebulae in the Large Magellanic Cloud. The type lists therefore merge
  them: `dso_type_groups.FILTER_TYPE_MERGES` maps `HII` to `EmN` for the
  facets, filters and planner counts (mirrored by `filterTypeCode` in
  `dsoTypeNames.ts`), and a filter naming either code matches both, so saved
  planner filters keep working. Stored types are unchanged; an `HII` object's
  label reads "Emission nebula (HII region)".
- Keep values that aren't an object's own V magnitude or visual size out of
  `mag_v` and `maj_axis_arcmin`: the Wolf-Rayet narrow-band v, ACO's `m10` and
  the LDN area go in the notes. The LDN equivalent diameter is used only for
  the match size gate and never stored.
- Render external-reference chips for `wikipedia`, `simbad`, `ned`, then
  `google` and `google_images`, in server order. Store Wikidata QIDs without
  showing them as user-facing links. Verify Wikidata property IDs against the
  provider rather than trusting old specs.
- **Common names** (v0.45.0).
  - `dso.common_name` is the preferred name only and never holds a comma;
    the object's other names are in `dso_other_name`, in order.
  - **Every catalog name is kept:** the entry's names and those of every
    entry merged into it, in collector order. NightCrate's reviewed list
    (`common_names.csv`) adds names and orders them, its rank 1 being
    preferred, and removes a wrong name only through a `remove` row with
    evidence.
  - `common_name_augmented` is 1 exactly for listed objects. The augment
    file no longer touches names, and it is not an object input.
  - Group rows (`target=group`) name groups with no object of their own and
    never fall back to a member: with Arp off, "Arp 244" is one galaxy's
    designation, which must not take "Antennae Galaxies".
  - `dso_other_name` is catalog-derived (`user_links.CATALOG_DERIVED_TABLES`).
    Any new table referencing `dso` must be classified there, or an alias
    would protect an object from removal like a project link.
  - **Each name needs two independent sources:**
    - SIMBAD;
    - NED;
    - Wikidata or Wikipedia (counted as one);
    - agency, observatory or university pages, astronomical societies,
      published papers and magazines.
    - One organisation counts once, and Fred's decision is recorded as
      `Fred:<date>`. Forums, image-sharing sites and vendors don't count.
    - Names are checked one at a time, as facts; nothing is copied from
      another site's list. Rejected and single-source names are recorded in
      the [names review](superpowers/plans/2026-11-03-v0.45.0-names-review.md).
  - **M 102 is NGC 5866** (Fred, 2026-11-03), through a reviewed `assign`
    override. OpenNGC follows Méchain's 1783 note that M 102 repeated
    M 101.
  - An override on an OpenNGC duplicate row decides where the duplicate goes:
    `assign` moves it to the target; `separate`, or an `assign` whose target
    isn't loaded, drops it. A duplicate row has no data of its own, so it
    never becomes a standalone object.
  - The catalog table's designation and Common name cells show the names on
    hover only. Names inside the grid, a button or an option have no tab
    stop of their own, so Enter keeps opening the row; keyboard users reach
    the other names through the detail panel.
  - Results show other names on hover (`NameWithAlternates`) wherever a
    result's name appears, and as a line in the detail panels. List
    endpoints load `other_names` for the returned page only.
- **Google links are computed per request** (`api/dso.py:_search_refs`) and
  never stored, so `dso_external_ref`'s provider CHECK is unchanged. The query
  is the primary designation plus the preferred common name.
- **One search-key function.** Designation search keys come only from
  `designations.normalize_designation`, used by the loaders
  (`_build_search_key`) and every API search; don't add another normaliser.
  - Structured names keep their signs: `PN G000.0+02.0` and `PN G000.0-02.0`,
    or `MCG+02-05-050` and `MCG-02-05-050`, stay distinct, while padding
    differences (`PN G0.0+2.0`, `MCG-02-05-50`) match.
  - An unsigned MCG zone means `+`, the written convention. Only the repair of
    identifiers stored before 0066 reads it as `-`
    (`canonical_legacy_identifier`), because the old parser dropped the minus
    of tight `MCG-…` tokens.
  - Long names map to the stored prefix: "Melotte 25" finds `Mel 25`, and
    likewise "Collinder", "Herbig-Haro" and "Wolf-Rayet".
  - Partial MCG and PN G queries also try the zero-padded forms the typed
    digits could mean (`designation_search_prefixes`, at most four
    prefixes, built on `normalize_designation`): "MCG-1-2" finds
    MCG -01-02-003 and "PN G 10.8" finds PN G010.8-01.8. Until 2026-11-03
    such partial queries matched nothing.
  - `designations.py` imports nothing from `nightcrate`; `_common` imports
    `loader`, so a normal import from there would loop.
- **Compute constellations in batches.** Collectors leave `constellation`
  empty, and `reconcile.build_object_set` fills them all with one
  `astronomy.constellations_for_coords` call. A per-row astropy call made the
  object build take about 150 s with every catalog on, against 1.2 s batched
  (measured 2026-11-02).
- **Repair checks must settle.** Each `_…_due` check in `loader.py` forces
  the whole object step, so one that stays true rebuilds every catalog
  object on every start. From v0.44.0 until its PR review fixes,
  `_designation_canon_due` did: OpenNGC lists Pease 1's PN G065.0-27.3 on
  M 15, the reviewed `separate` override keeps it off, and with HASH not
  loaded no object claims it. A start with nothing changed took 4.1 s
  instead of 0.27 s (real database, 2026-11-03). The check now skips
  identifiers a match override names.
  - `_primary_designation_due` holds every stored primary name equal to
    its primary designation's display form. MCG primaries were stored as
    "MCG+07-02-016" until 2026-11-03; the first load after the fix renames
    them (22,914 in a real database). A retained inactive object gets the
    same name when its designations are rebuilt.
  - After changing a collector or a check, confirm that a second
    `load_catalogs(force=False)` runs no object step
    (`test_separate_png_override_does_not_repeat_repair`).
- **A bad downloaded row never stops the object step.** An Arp member name
  the parser can't read loads as an anonymous "Arp N" member with a
  warning, and a duplicate row is skipped. Errors in NightCrate's own lists
  still raise; tests guard the shipped files. A `dso_parts.csv` whole whose
  designation already names a collector group (`ldn`, `arp`) is skipped
  with a warning, and the collector's group stays.
- `hash.file_sha256` caches digests in process by resolved path, size,
  mtime, ctime and inode. A file that changes during three reads in a row
  returns its last digest uncached.
- One article/entity may describe several objects; do not enforce cross-DSO
  uniqueness. A partial index on `(dso_id, provider) WHERE language IS NULL`
  supplies the deduplication SQLite's nullable UNIQUE constraint does not.
- **VizieR mirrors.** Six hosts, in order: Strasbourg, Harvard and IDIA
  South Africa over HTTPS, then Tokyo, Beijing and India (Pune) over plain
  HTTP. Fred accepted plain HTTP on 2026-11-03 as a fallback, knowing a
  download could be altered in transit. Mirror availability changes, so
  recheck the list with real downloads before editing `VIZIER_HOSTS`.
  - **Checked 2026-11-01**, during the CDS outage that began about
    2026-10-21: Harvard and IDIA work; Tokyo and Beijing serve plain HTTP
    only; Pune and Moscow time out; `vizieridia.saao.ac.za` fails HTTPS on
    its certificate.
  - **Checked 2026-11-03:** Strasbourg unreachable and Harvard HTTP 502.
    Tokyo and Beijing serve every table NightCrate uses except HASH (V/163),
    and their Sharpless table matches IDIA's byte for byte. Only Strasbourg
    and Harvard carry V/163. Pune times out over both schemes; it uses HTTP,
    which also reaches a host that redirects to HTTPS. `vizier.ast.cam.ac.uk`
    and `vizier.hia.nrc.ca` no longer serve VizieR.
  - **Check every mirror at once first** (Fred, 2026-11-03). Before a table,
    if no check has run in the last hour (`MIRROR_DOWN_S`) or every host is
    marked down, request one Sharpless row (`-out=Sh2,Diam`) from all six
    hosts concurrently: one attempt each, 10 s limit. Hosts that don't
    answer with a valid VizieR TSV are skipped until the hour is up. If none
    answers, nothing is recorded, since the user's own connection is the
    likely cause. A transport error or HTTP 5xx during a download also marks
    that host down. VizieR's "Table or Catalog not found" reply (IDIA,
    Tokyo and Beijing for HASH), a 4xx or a bad body only moves on to the
    next host. This replaced the same day's "try failed mirrors last" rule.
  - **Fail fast.** Make one pass over the available hosts; each gets only the
    shared HTTP client's single retry, with a 10 s connect limit. Stacked
    retries on a dead host once cost about 7 minutes per host.
  - **Plain failure messages.** The Catalogs page names the catalog, the
    failed part of a multi-table catalog, and each mirror's outcome grouped
    by reason ("Strasbourg, Harvard and India are down and South Africa,
    Tokyo and Beijing don't have this table"); the technical text goes to the
    log. Measured live on 2026-11-03: the HASH failure took 15 s, against
    about 45 s trying hosts one by one.
  - **Name the failed mirror's own time** when moving on ("Strasbourg timed
    out after 21 s. Trying the Harvard mirror…"), measured around the host's
    whole download; the progress counter restarts with each message, so it
    always counts the attempt in progress. Harvard has been seen holding a
    connection silent for about 60 s; the 180 s silence limit is kept for
    slow large downloads.
- **Sky images.** Render DSS2 colour images directly from 512 px HiPS tiles.
  Try `HIPS_TILE_SOURCES` in order: CDS alasky, then ESA ESASky. Split each
  nested index at order `k+9`; in the decoded JPEG, `column = iy` and
  `row = ix`, then flip the completed FITS-order output vertically for JPEG.
  Coarsen until a render needs at most 32 tiles, mark timed-out sources down
  for 10 minutes, and keep validated compressed tiles in memory only. Do not
  add a disk tile cache. A render holds its permit until its worker thread
  exits, even after repeated cancellation (see the star-data operation rule).
- **Catalog actions** (fetches, reloads, and adding or removing an optional
  catalog on the Catalogs page) run one at a time; a second returns 409, and
  database create/add/activate/setup are refused while one runs. The page
  polls `GET /api/admin/catalogs/fetch-status` for the step, seconds and bytes
  (`services/catalog_progress.py`); fetchers report through
  `http_client.get`'s opt-in event callback. The catalog load
  stays on the event loop by design (0.1–3.1 s measured on a real-size
  database; the object step took 4.5 s with every optional catalog on,
  2026-11-02); moving it to a thread needs a database-contention policy first.
  The app's connections use SQLite's rollback journal with a 5 s lock wait,
  so a load in a thread could turn a waiting save into an error.
- **Removing a catalog** first prepares the object step with the removal
  (`prepare_removal_step`) and returns 409 if it is blocked, before the
  choice file or any download changes; it runs no dry run. The separate
  removal-preview endpoint keeps its dry run for the dialog's counts.
  Measured 2026-11-03 with every catalog on: preview 3.1 s, removal
  5.1–5.5 s (7.0 s with the earlier second dry run).
- **Sharpless and Barnard on a fresh install** load whenever their files
  appear (the legacy default), but `GET /catalogs/optional` reports them
  `off` until they are chosen, applied or installed, so the page offers Add
  rather than "Files missing". An applied or chosen catalog whose files are
  gone still shows "Files missing".
- **Designation order** uses one natural key (`services/dso_sorting.py`,
  registered as a SQLite function and mirrored in
  `frontend/src/lib/designationSort.ts`): display prefix case-insensitively,
  then each number numerically (M 2 before M 10; ESO 107-2 before 107-010),
  then `id`. With catalogs selected, the list shows and sorts by each
  object's name from those catalogs (`display_designation`), chosen by
  `catalog_rank` (Messier, NGC, IC, Caldwell, then other codes
  alphabetically), then its lowest number; rank only chooses the name and
  never orders rows. A group member with no name of its own in those
  catalogs shows the group's name ("Arp 244"); the planner's catalog filter
  chooses its displayed name the same way. With none selected, the primary
  name. Type and Constellation sort by the labels shown
  (`services/dso_display.py`, kept in step with the frontend maps by a parity
  test).
- The list response carries every designation of each row, in rank then
  natural order, and the groups it belongs to (`part_of`); the table shows
  "Part of" pills, then the other names, beside Designation. Keep the table's
  `sortModel` identity stable (memoized): MUI DataGrid treats a new array as a
  sort change and returns to page 1.
- **Groups ("part of")** are catalog-derived (`dso_group`,
  `dso_group_member`) and rebuilt in each object step. Searching a group's
  name, or its whole's designation or common name, returns its members, and
  catalog filters and facets count members. See the
  [catalog architecture](dso-catalog-architecture.md#groups-part-of).
- OpenNGC names whose catalog has no NightCrate code display their own prefix
  and number ("H 5", "MWSC 3561"), never a synthetic "OTHER"; HCG names map to
  `hickson`. A PGC number fused to the next name by a missing upstream comma
  ("PGC 056771SDSS J…", two OpenNGC rows) is split into both names.
- See [catalog architecture](dso-catalog-architecture.md) for source layering.

## Locations, horizons, and target planning

- `geo_timezone` is coordinate-derived and controls observing nights/astronomy;
  `timezone` is the user's display choice. Remote sites may legitimately differ.
- Keep `tzdata` as a backend dependency. Windows has no system time-zone
  database, so `ZoneInfo` fails without it. In issue #16, the weather forecast
  and the planner both returned 500 for `Europe/Rome`. Tests using the
  `no_system_tz_database` fixture (in `tests/conftest.py`) hide the system copy
  to simulate Windows. They cover `ZoneInfo`, `tonight_date`, the forecast
  route, and the time-zone list.
- Each location has at least one horizon and exactly one default; at most one
  custom polyline, any number of artificial flat horizons. Last-horizon deletion
  is 422. Location edits **stage horizons**; Save applies atomically, Cancel
  discards. This intentionally differs from immediate project saves.
- Store raw horizon points in `[0,360)`, never 360. Smoothing is derived, not
  persisted. Display wraps to `[-180,+180]` with virtual south-seam points.
- Visibility samples all active DSOs every five minutes during astronomical
  darkness, then filters in memory. Cache by location/date/horizon and both
  location/horizon update timestamps, for 6 hours; catalog and database
  changes clear the cache (`api/admin.py:_clear_planner_visibility_cache`).
  Empty and NULL sort values always go last.
- **Apparent coordinates, transformed once.** Transit times and altitudes,
  and the five-minute altitude/azimuth grid, use each object's apparent
  (TETE) position at one instant and the apparent sidereal time at each
  sample, with the standard hour-angle formulas. The sky track's transit
  uses the same apparent RA.
  - Until 2026-11-03 the hour angle used the J2000 RA, so transits came out
    56–131 s early (439 s at Dec +85°) and transit altitudes near the
    zenith up to 0.37° low.
  - Checked against a dense astropy AltAz search: transits within 1 s,
    transit altitudes within 0.0002°, grid altitudes within 0.63″.
  - With 45,436 objects, the first Tonight request went from 3.9 s to 1.2 s.
- **Score every item, detail only the page.** The list scores every
  filtered item with `score_values`, sorts and paginates, then runs
  `score_targets` (breakdowns) and `compute_now_status` for the page only.
  Now status covers every item only when it is a sort key. Candidates are
  slotted dataclasses, and only page items become validated
  `PlannerTargetItem`s: in Pydantic 2, `model_construct` measured slower
  than validation. With 45,436 objects (2026-11-03), Tonight went from
  1.43 s to 0.29 s and Anytime from 0.39 s to 0.24 s. See
  [planner scoring](planner-scoring.md#4-combination--weighted-geometric-mean).
- **Filter counts are tonight's.** Once a planner response has loaded, the
  type, catalog and constellation lists count from it, and a value with
  nothing passing counts 0; the catalog-wide `/api/dso/facets` totals are
  only a placeholder before the first response. `PillFilter` hides zero
  counts but keeps a selected value, shown as "(0)". Until 2026-11-03 a
  missing count fell back to the catalog total, so "Emission nebula (8)"
  appeared although all 8 are in the Large Magellanic Cloud.
- **Planner limits show what is applied.** The server never falls back to the
  Settings magnitude and size limits: a missing `max_magnitude` or
  `min_size_arcmin` means no limit, in both modes. Only the visibility-hours
  minimum keeps its Tonight default.
  - Tonight opens with both boxes ticked at the saved slider values (last
    used, else Settings); Anytime opens with both unticked. Each mode keeps its
    own ticks.
  - A magnitude limit passes objects with no magnitude; a size limit drops
    objects with no size. The captions under the ticked boxes say so.
  - Picking or clearing a catalog never changes the limits.
- **No unbounded id lists in planner queries.** With every catalog on, the
  active objects exceed SQLite's variable limit (32,766 in the build tested),
  and a query binding one `?` per object fails with "too many SQL variables".
  Query by the same `active = 1` and coordinate conditions instead, or bind
  only a bounded page of ids. `test_anytime_with_40000_objects` guards this.
  The list reads coordinates and metadata in one such query; chunked id
  lists measured no faster (2026-11-03).
- Moon separation is closest approach during target visibility, not at transit.
  Before comparing a distance-bearing astropy Sun/Moon coordinate with an ICRS
  target, use `astronomy.direction_only`; frame-origin translation otherwise
  corrupts the sky direction. Same-frame Sun–Moon separations are safe.
- Moon rise/set needs a **48 h midnight-anchored grid** (the lunar day is longer
  than 24 h). Now-status calculations need both darkness boundaries.
- **Dense crossing grids are splined** (v0.41.9).
  - **Where:** the 24 h Sun grid in `compute_night_summary` and the 48 h Moon
    grid in `_moon_rise_set`.
  - **How:** exact astropy altitudes at every 10th sample plus the last; a
    `CubicSpline` in elapsed seconds fills the samples between
    (`_spline_altitudes`, called explicitly at those two sites).
  - **Stays exact:** moonless sampling, `moon_altitudes_at`, the Moon polyline,
    the Moon phase and `compute_hourly_astro`.
  - **Before changing the node rule or extending the spline,** keep these
    passing:
    - `tests/test_astronomy_spline.py`: equivalence with exact sampling and
      exact-evaluation counts;
    - the forecast and Tonight equivalence tests in `test_weather_api.py` and
      `test_calculators.py`.
  - **Tolerances:** datetimes within 1 s; unrounded API durations within 2 s;
    everything shown identical.
  - [Spec](superpowers/specs/2026-10-23-forecast-astronomy-speed-design.md).
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

**ASTAP**

- Run ASTAP through `asyncio.create_subprocess_exec`; **never pass `-update`**.
  Direct outputs to a temporary directory with `-o` and read the `.ini` sidecar.
  Resolve macOS `.app` executables under `Contents/MacOS/`.
- Convert archive/project images, XISF, and FITS whose image is in an
  extension (HDU > 0) to temporary FITS, retaining focal length, pixel size and
  coordinate hints. Ordinary supported files pass directly. Use a fresh buffer
  for each header/dimension/image consumer. Resolve, read and prepare the file
  in worker threads, never on the event loop.
- ASTAP returns bottom-up FITS row order when PNG, JPG/JPEG, or TIF/TIFF files
  are passed through unchanged. Flip `CRPIX2` and the second CD column before
  returning or storing those solves. Archive entries, XISF, and `.pxiproject`
  inputs are converted to temporary FITS and must not be flipped again.
- Corrected solutions, and all ASTAP results without CROTA2, use
  `degrees(atan2(-CD1_2, CD2_2))` for rotation. Unflipped results with CROTA2
  retain ASTAP's value. Migration 0064 applies the same correction and rotation
  rule to existing standard-image project solves.
- ASTAP runs as a step chain under one 180-second deadline that includes file
  preparation:
  - **Near step:** used only when a position is known; `-r 30` and a
    timeout of the smaller of 60 seconds and the remaining time.
  - **Whole-sky step:** `-r 180`. It runs after `no_match` or a step
    timeout, and directly when there is no position.
  - **Field (`-fov`):** the pixel scale × the height of the file ASTAP reads,
    not the sensor's. With no scale, `-fov 0`.
  - **Stopping:** `too_few_stars`, `cancelled`, `error` and the overall time
    limit end the chain.
  - **Retries:** the old `-speed slow` retry is gone; the chain solved 130 of
    143 corpus images against 123.
  - **Results:** the result's `failure_reason` uses the built-in solver's
    vocabulary (`no_match`, `time_limit`, `cancelled`, `too_few_stars`,
    `error`). A result counts as solved only when its WCS is complete:
    CRVAL, CRPIX and all four CD values.
- An ASTAP command-line run with `-fov 0` rewrites the user's `astap.cfg`
  (search field, radius, position, last file), and later runs and the user's
  ASTAP GUI then use those values.
  - Every ASTAP subprocess runs with `HOME` and `XDG_CONFIG_HOME` pointing at a
    fresh temporary folder that holds a copy of the user's `astap.cfg`, so
    their settings apply and are never written. This is verified on macOS.
  - On Windows (`%LOCALAPPDATA%\astap\astap.cfg`, unverified), ASTAP may
    ignore the redirected variables. A guard restores the user's file if a
    solve changed it.
  - Run hand experiments the same way, with a private `HOME`.

**Built-in star data and field ranges**

- The source is the pinned Siril Astrometry Catalogue extracted from Gaia DR3,
  including its sizes and SHA-256 checksums; keep the authority in
  `services/star_catalog/store.py`. Under `APP_DIR/star_catalogs/`, the catalog
  and `version.json` live in `siril-astro-gaia-dr3-1.0.0/`, layer files live at
  `indexes/<layer>.ncidx`, the range manifest is `indexes/ranges.json`, and
  in-progress work lives in `.staging/`.
- Download and import only when the catalog is not installed. Downloads use
  four fixed byte-range pieces, resume each piece only from a validated range,
  then assemble and SHA-256-check a hidden temporary archive before publishing
  it. If a server does not honour ranges, keep piece 1 as the prefix and fall
  back to the resumable single stream. Claiming the single star-data operation
  removes stale staging left by a crashed operation while retaining resumable
  pieces.
  Publish the catalog first and write `version.json` last; its presence is the
  installed marker. An import never reads from inside `star_root()`: check
  containment by filesystem identity, not path spelling (macOS is
  case-insensitive), and reject hard links to the staging destinations. The
  import opens its destination for writing, so an alias would truncate the
  source.
- The star-data operation keeps ownership until its worker threads and network
  tasks have finished, however many times it is cancelled. Wait with
  `core/tasks.py:settle`, which re-raises the cancellation only afterwards.
  - A plain `await` after the first cancellation lets a second one release
    ownership while a thread still writes to staging.
  - Shielding the worker itself is not enough: in Python 3.14 each abandoned
    shield logs "exception in shielded future" when the worker later raises.
    `settle` shields a waiter that never raises (found in v0.43.1). The plate
    solver's ASTAP, native and project-save waits use it too; a project save
    runs its commit, `committed = True` and cleanup as one settled step, so a
    cancel never deletes committed images.
- Store one index file per layer, not per user-facing range. `ranges.json`
  records the ranges the user owns; a layer remains while any remaining
  manifest entry names it. Each layer build runs in one fresh child process and
  keeps all temporary files in its parent-owned staging directory. Never hold
  a file per partition open: a process started from a macOS terminal may open
  only 256 files, while agent shells often allow far more, so a limit failure
  shows only on users' machines. Tests that guard this lower the limit
  themselves. Publish
  layers and the manifest under the solve slot, after `handles.close_all()`, so
  no mapped file is replaced under a reader.
- Build requested ranges one at a time in `FIELD_RANGES` order (Standard
  first), and publish each as soon as its layers are ready, so Standard is
  usable while Narrow fields builds. Weight a range's progress by its layers'
  `estimated_bytes`; build time tracks size (about 16 MB/s per layer). A
  cancel or failure keeps ranges already published. A build request drops
  ranges already built, but a ready range missing from the manifest takes the
  publish-only path. `/status` reports a ready range as `built` before
  considering the operation's current range; remaining requested ranges are
  `building` or `waiting`, each with its own progress.
- Offer two user-facing index choices: recommended **Standard** covers 0.4°–10°
  with q008 through q256, while optional **Narrow fields** covers 0.2°–0.4°
  with q004. Neighbouring layers overlap, and a field near a layer's lower edge
  needs the next smaller layer, so exposing each layer as a separate field range
  would leave gaps near the boundaries.

**Built-in solve**

- Before brightness and spatial selection, reject extraction candidates wider
  than six times the median width of candidates that passed the existing shape,
  PSF and saturation checks. This applies to every extraction profile.
- Quads and verification use one saturation-inclusive detection population.
  - Rejecting stars with clipped cores removed every bright star from
    stretched finals. Verification compares detections with the brightest
    catalog stars, so the true pose of the NA Nebula final scored log-odds
    −208.
  - With the clipped stars kept, it solves in 0.35 s.
  - The corpus and the false-match trials were unchanged.
- Acceptance settings are fixed. Every index search uses `BlindSolverConfig`:
  at least 12 matches, at most 0.2° axis non-orthogonality, and code tolerance
  0.010. The catalog-only position search uses `SolverConfig`: 10 matches and
  3° axis non-orthogonality. Both require `log_odds_threshold = ln(1e18)` and
  three quadrants. Do not loosen any of these values without Fred's decision.
- An early-stopped ambiguity scan is never a solve. If deadline or cancellation
  arrives after a first acceptance but before ambiguity checking finishes,
  return `time_limit` or `cancelled` with no WCS.
- Keep the measured solve order:
  - position and scale: search the index near the position when that field range
    is built, otherwise use the catalog-only position search; if it misses, run
    blind scale-known and then blind unknown-scale;
  - position without scale: run blind unknown-scale, then the catalog-only
    position search if blind misses or cannot run;
  - no position: run blind only, scale-known first when a scale is available,
    then unknown-scale.

  Blind steps require at least one built layer. `ambiguous` and `cancelled` stop
  the sequence.
- Budgets are 20 seconds for a near/catalog step, 10 seconds for blind
  scale-known, 30 seconds for blind unknown-scale, and 60 seconds overall
  including image loading. A step receives the smaller of its budget and the
  remaining overall time. Index steps need 12 detections; catalog-only needs 10.
  Report `too_few_stars` only when the image is below every step that could run.
- When all attempted steps miss, outcome precedence is `field_not_built`, then
  `time_limit` if any search hit its deadline, then `no_match` when all searches
  exhausted their candidates.
- The native solve runs in a worker thread, but that thread retains the single
  solve slot until it actually stops, including after cancellation or request
  teardown. An ASTAP solve is owned the same way:
  - it runs as a task;
  - a cancel or shutdown sets its stop flag and kills the process;
  - no new step starts after the stop, and the flag is checked again
    once a new process exists, since a cancel during the launch has no
    process to kill;
  - the slot is released only when the task has ended, so the temporary
    directory outlives the worker.

  Native solving and star-catalog work are numpy-only and never use the GPU
  backend.
- Solver output uses top-down rows exactly as `pixel_loader` returns them,
  1-based `CRPIX` at `((width + 1) / 2, (height + 1) / 2)`, and CD in degrees
  per pixel. Compute rotation through the shared `rotation_from_cd` rule,
  `degrees(atan2(-CD1_2, CD2_2))`, without normalizing it.

**Results and display**

- Migration 0065 adds `solver` and the native metrics to `project_solve`:
  catalog, detected/matched stars, pixel RMS, log odds, solve path and scale
  stage. Existing rows are `solver = 'astap'`; ASTAP leaves the native metrics
  null.
- Image Analyzer solves are shown without persistence ("Shown here only. The
  file isn't changed."). A solved WCS always overrides the header's in
  annotations, and the annotation query key fingerprints the complete WCS.
  Project solves persist the WCS and object links. Keep these flows distinct.

**Hints**

- The scale hint is a pixel scale, `scale_hint_arcsec` (″/px), never a field
  height. A field computed from the full sensor was 14% wrong for a cropped
  final, and ASTAP's position search failed with it.
- **Precedence:** the request's scale, then the deprecated `fov_hint`, then
  the header (`YPIXSZ`, falling back to `XPIXSZ`, with `FOCALLEN`). Header
  pixel sizes already include binning.
- **Sending hints:**
  - while the user keeps the header choice, the client sends no scale or
    position, so the backend's header rule is the only one;
  - `position: "none"` and `scale: "none"` ignore the header explicitly;
  - rig and manual entries compute physical pixel × binning ÷ focal length.
- **Validation:** RA/Dec only as a finite, in-range pair; scales finite and
  > 0.

**Solve operations**

- **Identity.** Each solve has a client-generated `operation_id` (UUID),
  required on solve, cancel and progress requests. A request without one,
  and a request with an unknown field such as the removed `mode`, gets 422.
- **Cancel** touches only its own ID.
  - A cancel for an ID that hasn't started yet is kept (at most 64, for
    10 minutes). It is checked when the solve claims the slot and again
    before a project commit.
  - Used IDs can't be reused; the last 1,024 are remembered.
- **Progress** returns the finished attempts, the active step, the planned
  steps and the elapsed time. The UI never infers steps from time or text.
- **Lifetime.** The endpoint owns the operation through rendering and
  saving, not just the solver.
  - `begin_commit()` checks for a cancel and closes the cancel window in one
    locked step. A cancel after that returns `cancelled: false`, and the save
    completes.
  - The solve slot is shared with star-data publication.
- **Error detail.** Every error from either solve endpoint (Image Analyzer
  or project) has the detail `{message, failure_reason, attempts}`, never a
  bare string. FastAPI's own request-validation 422s are the exception.
  - **Reasons and statuses:**
    - `invalid_configuration` (422): ASTAP isn't set up, its path is
      invalid, or it can't be started;
    - `read_error` (422): the image can't be resolved, read or converted;
      a missing file adds the hint about a disconnected drive;
    - `busy` (409);
    - `solve_exists` (409);
    - `time_limit` (408);
    - `error` (500), for anything else, including internal invariants.

    Project solves add `invalid_image`, `invalid_wcs` and `render_failed`.
  - **Reading errors.** The solvers wrap failures at their read sites in
    `ImageReadError`, and an ASTAP launch failure in `AstapLaunchError`.
    A plain `ValueError` from a solve is therefore an internal error, not
    a reading error.
  - **Attempts.** An error never carries an attempt with a null outcome. A
    step still open is reported as `cancelled`, `overall_timeout` or
    `error`.

**Project solves**

- **Replace after success.** A replacement (`replace: true`) and a first
  solve both render into `solve/.staging-<operation id>/`. Then, under the
  per-project lock, in one transaction:
  - re-check for a cancel;
  - delete the old row (its objects cascade);
  - insert the new row and its objects;
  - remove any leftover folder for a reused row ID;
  - rename the staging folder to `solve/<new id>/`;
  - commit.
- **Failures and cleanup.**
  - Any failure before the commit, including a failed commit, removes the
    new folders and leaves the old row and images untouched.
  - **After the commit,** while the lock and slot are still held, every
    other entry in `solve/` is removed: older generations, legacy
    top-level images, and staging folders left by a crash. No render can
    be running then, because the solve slot is global.
  - **Delete** removes the row, the generations and legacy images, but
    leaves `.staging-*` folders: a replacement may be rendering into one
    outside the lock.
  - **A render failure saves nothing,** and neither does a failure to
    move the staging folder into place (`render_failed`).
- **Images.** The image route serves the current row's generation, falling
  back to the legacy `solve/<variant>.jpg`. Image URLs carry `?_v=<solve id>`;
  `solved_at` has one-second precision.
- **Main targets** live in `project_target` and survive a replacement.
- **HDU.** A project solve takes HDU 0 only. A FITS whose image is in an
  extension gets a 422 that points to the Image Analyzer.

**Preview route**

- `GET /api/images/preview?path=&hdu=&max_px=` returns a JPEG of the chosen
  image before any solve, for any path `path_resolver` handles.
- **It must look like the project's rendered image.**
  - PNG, JPEG and 8- or 16-bit TIFF are shown as they are.
  - FITS, XISF, float TIFF and project images are normalized by data type
    (`normalize_to_01`; FITS uses the type implied by `BITPIX`/`BSCALE`/`BZERO`).
    They are then stretched only when `resolve_auto_stretch`'s linear test
    says so.
  - This is mirrored in numpy, because the preview runs in concurrent
    threads. A single always-on stretch over-brightened processed finals.
- **Memory.** FITS samples a stride of the memory map before scaling;
  standard images use PIL's reduced decoding; full-decode formats run one at
  a time. A 540 MB XISF final peaked at 2.7 GB, against 5 GB for the
  project render.
- **Caching.** Only encoded JPEGs are cached, within 32 MB, keyed by a stat
  identity taken before decoding:
  - plain files: path, size and mtime;
  - archive entries: the archive's identity plus the member name;
  - project images: the manifest's identity, the image index and the backing
    file's identity.

  Responses carry an ETag with `Cache-Control: no-cache`.

**Solve UI**

- **The panel.** One inline `PlateSolvePanel` sits beside the image: in the
  project tab, and in the Image Analyzer's Identify sidebar.
  - Solving is never modal.
  - The old dialog was removed (Fred, 2026-10-30), together with "From
    Reference Image" and the equipment scale picker.
- **Requests.**
  - Each request's token is bound to its image and HDU; late results,
    progress and callbacks are dropped.
  - Leaving a page, changing the image or hiding the Analyzer route cancels
    the solve. Persistent routes stay mounted with `display: none`.
  - A stale project response refetches the saved solve rather than trusting
    the response.
- **Mount guards under StrictMode.** A hook that clears a mounted flag in an
  effect cleanup must set it again in the effect's setup. Otherwise
  StrictMode's mount → cleanup → mount leaves it false, and every result is
  treated as stale.
- **Setup round trip.** Applied hints and the solver survive a trip to setup
  through a session snapshot and `?tab=plate-solve&solve=&hdu=`. Setup links
  carry `?returnTo=`, which is accepted only as a same-origin app path (no
  `//`, no scheme, no backslash). Admin scrolls to `#plate-solving-stars`.
- **Failure reasons.** Both solvers share one list, and every reason has its
  own title.
  - **"Try again"** follows a cancel, a time limit, an error, a read error,
    a busy slot, a render failure, or a response without a reason. It also
    follows missing stars or ranges once the built-in solver is available.
  - **Every failure** also offers "Change hints", and the other solver when
    it is set up.
  - **Unfinished steps.** A finished step list never shows an unfinished
    step as "Done"; it reads "Stopped".

## Weather: personal imaging verdict

v0.41.9 replaced the 0–100 imaging score with a per-night verdict. The design
and its reasons are in the
[spec](superpowers/specs/2026-10-17-weather-redesign-design.md) and the
[plan](superpowers/plans/2026-10-17-weather-verdict.md). They were revised by the
[forecaster revisions spec](superpowers/specs/2026-10-17-forecaster-revisions-design.md)
(its §11 holds the agreed clarifications) and its
[plan](superpowers/plans/2026-10-17-forecaster-revisions.md). The previous model is
archived in [imaging-quality-model.md](archive/imaging-quality-model.md).

**Verdict and rules**

- **Verdicts:** Go / Uncertain / No / Not enough data, plus Night over. Every
  non-Go verdict has a reason. There is **no blended score anywhere**: not in
  an API field, not as a sort key, not in the UI.
- **Evaluation** is server-side only, in `services/imaging_verdict.py`. The
  frontend never derives a verdict.
- **Rules** live per location in `location_imaging_rules` (1:1, typed, CHECK
  vocabularies).
  - No row means the `attended_session` default preset, and the UI shows
    presets only then.
  - Thresholds are user settings; do not hard-code them into the evaluator.
- **Usable time** (called "clear time" in the code) counts the exact dark
  minutes, for the rules' darkness threshold, that pass every counted check.
  User-facing text says "usable", never "clear", because wind, dew, the Moon
  and precipitation also remove time (2026-10-18).
  - All-night rules apply the fraction ("at least", 1–100%), minimum-hours
    and "longest interruption" tests.
  - Short sessions need one contiguous run.
  - Runs and gaps never bridge non-dark time.
- **Cloud is each model's reported total.** Layers never count, and a missing
  total is unknown, never rebuilt from layers. For ECMWF on Open-Meteo, the
  layers are humidity estimates; they are shown under "For information".
- **Precipitation.**
  - **Chance comes only from the main forecast,** with **one limit** applied
    to every hourly value as reported (Fred, 2026-10-18).
    - Further ahead, the US forecast gives one chance per 6-hour stretch and
      repeats it in each hour.
    - A second "per-period" limit, with hour-or-block classification, was
      built and then removed (spec §11 F3). It couldn't be explained in plain
      words. Do not reintroduce it without a new decision.
  - **The amount** fails only above `rain_amount_threshold_mm`.
  - **"Any model"** (`rain_forecasts`) adds ECMWF's, GFS's and ICON's own
    amounts inside their coverage.
  - **Under `night_off`,** precipitation is judged over the exposure interval
    and acts as a night-level veto. Session states used for the cloud verdict
    exclude it, and displayed states include it.
- **Saved rules were reset by 0059** (Fred, 2026-10-18). The table had never
  shipped, so the new schema starts empty.
- **Missing data.**
  - A known fail beats unknown.
  - Unknowns are evaluated twice: pessimistic passes → Go; optimistic fails →
    No (with an `at_most` or `at_least` bound); otherwise Not enough data.
  - Checks that cannot affect the verdict (cloud/wind/dew/moon outside the
    imaging interval, precipitation outside its interval) are `not_counted`,
    never unknown.
  - **The verdict guarantee:** with rules, intervals and declared coverage
    fixed, replacing a known value with unknown never turns a non-Go into Go.
    `tests/test_imaging_guarantee.py` enforces it. Any new branch must keep
    it, and every Go condition must be a pessimistic pass.
- **Display conditions.** Each hour also carries `conditions`: every enabled
  rule judged regardless of darkness. The hour strip draws its icons from it so
  twilight and outside-imaging hours show the full forecast (Fred, 2026-10-17);
  elapsed hours stay blank. The verdict uses only `checks`.
- **The hour strip is frozen** (Fred, 2026-10-18): its icons, sizing, geometry
  and colours. Data may change what it shows: `disagrees`, which is set only on
  Uncertain nights and only where an expected comparison model's known state
  differs from the primary's, and positions from UTC timestamps for
  fractional-offset zones. Its look may not change. The rendered check
  compares pixels with reference screenshots.
- **Horizon: 14 nights** (Fred, 2026-10-17), the reach of ECMWF cloud. The
  Weather page has a "7-day forecast" tab (default) and an "Outlook" tab for
  nights 8–14, whose far-range hourly cloud changes between runs; a date link
  opens the tab holding that night. The rules editor's "this week" counts cover
  nights 1–7. With more than one forecast ticked, night details show a cloud
  row for each of ECMWF, GFS and ICON, unticked ones marked "Not used for the
  cloud decision"; with one ticked, only that row, plus a "Show each model's
  cloud" toggle.
- **Darkness band.** The Tonight card and the night-detail grid draw darkness
  from each night's `darkness_intervals` (exact −6°/−12°/−18° crossings), not
  from the per-hour `darkness_category`: one label per hour hides the half-hour
  twilight stretches (Fred, 2026-10-17).
- **Rest of the night.** A night under way is judged from now on. It shows
  Night over once darkness or the imaging interval has ended (Fred,
  2026-10-17), and stays listed until local noon. The exposure tail after
  darkness is not evaluated, and no wording may imply that exposure has ended.
- **Per-night controls** (session state, never saved) are aware timestamps:
  - "Gear out at" and "Gear in at" bound the exposure (`night_off`);
  - "Imaging from" and "Imaging until" narrow imaging, inside the exposure
    under `night_off`.

  The UI offers only valid combinations. The API returns 422 for invalid ones,
  and the UI resets them. Controls that don't apply (gear under `hours_lost`,
  or nights no longer listed) are ignored and reported back. The night's hours
  always cover the natural span plus any control times.
- **The night anchor** is the display-timezone wall clock: before local noon it
  is the previous date (`tonight_date`, and the frontend `tonightDate`).
- **The darkness setting is independent of the Moon.** The Moon only counts
  when "Moon must be down" is set.

**Data and time**

- **UTC everywhere.** Open-Meteo uses one fixed offset per response and ignores
  DST, so every request uses `timezone=GMT` and `timeformat=unixtime`, and
  series are parsed to aware UTC.
  - Legacy cache rows are decoded with their own `utc_offset_seconds`.
  - Rows off the whole-UTC-hour grid are ignored.
  - Display labels come from `ZoneInfo`.
- **Preceding-hour fields.** `precipitation`, `precipitation_probability` and
  `wind_gusts_10m` describe the preceding hour: the value at `T+1h` covers
  `[T, T+1h)`. The other fields are instantaneous at `T`.
- **Complete inputs.** `services/forecast_inputs.py` builds one input per whole
  UTC hour of the night. Each field is resolved from its own timestamp and
  source; a missing source row leaves only that row's fields `None`.
- **Darkness.**
  - `NightSummary.dark_intervals` are the maximal runs at or below
    −18 / −12 / −6°, found from the sampled sun altitude **independently of
    sunset**. This covers polar twilight without a sunset, continuous polar
    night, and two intervals in one night.
  - `darkness_hours`, `moonless_dark_hours`, `deepest_darkness_reached` and
    `no_imaging_window` derive from the intervals.
  - The `DarknessWindow` boundary fields are still chained from sunset; use
    the intervals for any duration.
- **Cloud sources and coverage.**
  - **Declared coverage** (`services/forecast_coverage.py`) decides which
    models are expected for each hour: fetch time + a fixed per-model value,
    capped by the request's own range. It is never derived from which values
    arrived. Missing values inside it are unknown; values outside it are
    informational. It applies to model cloud and to "Any model" amounts. The
    main forecast's own fields always count: missing is unknown.
  - **The rules choose the cloud forecasts** (Fred, 2026-10-18, spec §11
    F4).
    - Users tick one to three of ECMWF, GFS and ICON, with a preferred one.
    - **"Majority for each hour"** (the default) decides each hour's cloud
      check by the ticked models expected at that hour. A tie goes to the
      preferred model, or, beyond its reach, to the first expected ticked
      model in the order ECMWF, GFS, ICON. Unknown votes are bracketed. The
      night is then judged on that one sequence and is never Uncertain from
      disagreement.
    - **A per-night vote was rejected:** two models can each allow a session
      at different hours with no hour most models support. So was a "follow
      the preferred forecast" mode: ticking only that model does the same.
    - **"Show Uncertain"** keeps the comparison rules. All night: a Go/No
      split is Uncertain. Short session: all expected models must share one
      usable window, or the night is Uncertain.
    - **Default forecast and missing values, by mode:**
      - **Majority:** `best_match` decides an hour, labelled, only where no
        ticked model is *expected* at that hour.
      - **Show Uncertain:** `best_match` replaces the whole night's primary
        only when no ticked model is *expected* for the night.
      - **In both modes,** a missing expected value is an unknown vote, never
        a substitution. It gives Not enough data only when it could change
        the outcome; under the majority, two known agreeing votes still
        decide the hour.
    - The cloud choice never changes the "Any model" precipitation check.
    - Unticked models still show in night details, marked "Not used for the
      cloud decision".
  - **Sources** follow Fred's decision not to pursue accuracy work. Do not add
    sources, medians or benchmarks without a new decision.
- **Freshness** is tracked per source.
  - "Stale" means past its TTL **and** the refresh failed. A row within its
    TTL is never stale, even when incomplete; its gaps are unknown hours.
  - Rows that are incomplete or from an older contract are refetched at most
    once an hour per location and source, and concurrent requests share the
    refetch. Polling once a minute cannot flood Open-Meteo.
  - A night's staleness counts the main forecast, and the cloud row when it
    was used (a ticked model's cloud, or "Any model" amounts). Model
    metadata never makes a verdict stale.
  - Stale data turns Go, Uncertain and Not enough data into Not enough data;
    a No stays No and shows the forecast's age.
  - The cloud row and its `model_meta` row are written in one transaction
    with the same full-precision `fetched_at`, and are read in one statement.
  - The startup purge keeps 8 days of rows. No main-forecast row at all →
    503.
- **Re-evaluation.** Verdicts are not cached: every request evaluates against
  now.
  - Weather and Tonight poll every 60 s, only while their route is active.
    Persistent routes stay mounted while hidden.
  - On the browser's clock, a result older than 3 minutes, or one whose
    refresh failed, is shown as "Last result: … — not current". The frontend
    never computes a verdict.
- **Context estimates.** Seeing and transparency are labels only
  (good/fair/poor). Their required inputs are explicit, and missing stays
  missing: never a neutral 50.
- **Dew** has one definition: the temperature − dew-point spread, compared
  with the rules' `dew_min_spread_c` whether counted or advisory.
- **"How the verdict works"** comes only from
  `api/weather_methodology.py`: `METHODOLOGY_SUMMARY` ("In one minute") and
  `METHODOLOGY_DETAILS` (Fred, 2026-10-18).
  - The summary stays readable in about a minute.
  - Both use bullets, short tables and `>` callouts, not paragraphs.
  - Both use plain words. The API test bans internal terms such as "period",
    "coverage", "primary" and "fallback".
- **Rules editor hover notes.** Every setting's label carries a one- or
  two-sentence hover note on the label text: no icons, no underline. The
  wording was agreed by Claude and Codex (2026-10-18).

## Calculators, settings, and diagnostics

- Calculator math runs server-side. The sidereal clock ticks locally between
  60 s refreshes. Backend `HH:MM` strings are already display-local; pass them
  through without interpreting them as UTC. Render formulas with
  `components/calculators/Math.tsx` (`Inline`/`Block`), which calls KaTeX
  directly. `react-katex` was removed because it pinned KaTeX 0.16. Formulas
  are hard-coded TeX; keep KaTeX's default `trust: false`.
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
- **Rendered-image caches** (`services/image_cache.py`): rows store the file's
  name, resolved inside today's `APP_DIR` cache folder; legacy absolute paths
  resolve by their name, never at the old location, so a moved app-data folder
  keeps its images. Thumbnails and planner cells share one budget, one lock
  (publication, eviction, clearing, reconciliation and the sweep) and one
  "Clear All", which also deletes recognized cache files without a row and
  leaves unknown files alone. The startup sweep runs only after a
  reconciliation with no unresolved errors. A render that started before a
  clear never publishes after it.
- Diagnostics middleware records requests. Use `X-Activity` for fetch and
  `_activity` for image URLs; keep an image's activity label stable from file
  open so cache busting does not split request groups.
