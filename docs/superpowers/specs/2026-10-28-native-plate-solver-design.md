# v0.43.0 design: native plate solver

**Status:** approved by Fred on 2026-10-28. Written after a brainstorm with
Fred. His
product decisions are marked **Fred**. The roadmap decisions of 2026-10-26 and
2026-10-27 are summarized in §2 and are not reopened here. Engineering choices
Claude made are marked **Claude's call** and are listed in §14 for Fred to
check.

Prototype evidence comes from the throwaway prototype, a separate local
repository that is not published, and from its review records
in `.superpowers/codex/solver-prototype/` (ignored, local). Both were measured
on Fred's local corpus, which never enters the repository.

## 1. Why

NightCrate solves images only through ASTAP, a separate program each user
must install along with a star database. Without it, a project cannot find the
objects in its image, and the Image Analyzer cannot draw object overlays for an
image whose header has no solution.

The prototype showed that NightCrate can solve images itself. On Fred's
corpus, a fully blind solve (no position, no scale) solved 104 of 106 subs and
masters, with a median of 0.75 s and 95% within 3.9 s. ASTAP solved all 106
only with the header position, and 96 without it. Across all 143 images that
should solve,
native blind solved 128 and ASTAP 123, and neither gave a wrong answer. Fred
accepted the prototype on 2026-10-27.

The aim is that a new user can solve any image after a one-time star
download, with no other program to install. ASTAP stays available for
anyone who prefers it.

## 2. Settled before this spec

These come from the roadmap (PLAN.md, v0.43.0 → Scope) and the product
decisions note. They change only by Fred's decision.

- Stars: the Siril Astrometry Catalogue extracted from Gaia DR3 (Zenodo record
  14692304, version 1.0.0, CC BY 4.0, derived from Gaia DR3 under
  CC BY-NC 3.0 IGO). It is read from its published format specification
  (Zenodo 14697486), never from Siril's code. Each user downloads it directly
  from Zenodo or imports a copy. NightCrate hosts and bundles no star files.
- The star pattern index is built locally.
- Fully blind for fields of 0.2–10°: position and scale both unknown. Hints
  only make a solve faster.
- TAN output, so existing overlays, the field of view and object search work
  unchanged. SIP distortion comes later.
- Each solve records its solver, catalog version, stars detected and matched,
  RMS and confidence.
- ASTAP stays user-installed. A setting picks the default solver. A failed
  native solve offers "Solve with ASTAP" and never retries automatically.
- No new Python dependencies: numpy, scipy, astropy, sep and astropy-healpix
  are already declared in `backend/pyproject.toml`. healpy is not used (GPL).
- Method from published work: 4-star geometric hashing and Bayesian
  verification (Lang et al. 2010, AJ 139, 1782) and TAN WCS (Calabretta &
  Greisen 2002). The source of open-source solvers may be read for concepts
  (SASpro, astrometry.net, ASTAP, tetra3, twirl). NightCrate writes its own
  code, copies none, and credits the projects that informed it.
- Test images stay local. Only the benchmark script and synthetic tests that
  generate their star fields in memory enter the repository.
- The bar for native as the default (§11.2).

## 3. Goals, non-goals and anti-goals

### 3.1 Goals

- **Fred:** the native solver replaces ASTAP in the two places that solve
  today: the Image Analyzer (results shown, not saved) and a project's Plate
  Solve tab (results saved). Both flows keep their current behavior apart from
  the changes below.
- Getting the stars is a one-time step in Admin, and it survives
  interruptions.
- A solve is fast enough that a user doesn't think about choosing between a
  solve near a known position and a blind solve.
- A wrong solution is never saved or shown as solved.

### 3.2 Non-goals

- **Fred:** nothing new that fast solving makes possible, such as solving
  every sub during cataloging. That can return when an imaging decision needs
  it.
- SIP or other distortion terms.
- Reusing an installed ASTAP star database.
- Following newer versions of the Siril file automatically (§4.3).
- A GPU path for the solver.

### 3.3 Anti-goals (failure even if it works)

- A solve that reports success with the wrong sky position, scale or parity.
- A star download or index build that leaves a half-written file looking
  installed.
- Anything in the solver that writes to the user's image files.
- A solve that blocks the server, so other pages stop responding.
- Star data duplicated per database.

## 4. Star data in Admin

**Fred:** star data is managed in Admin, in a new **Plate-solving stars**
section directly below the existing Catalogs section, following the approved
mockup (the local file `.superpowers/brainstorm/43189-1793279244/content/admin-stars-v2.html`,
three states: before download, downloading, installed).

### 4.1 Storage

**Fred:** the star file and indexes live in NightCrate's app data folder and
are shared by every database. Solve results and settings stay per database.

```
APP_DIR/star_catalogs/
  siril-astro-gaia-dr3-1.0.0/
    siril_cat_healpix8_astro.dat      1.52 GB, memory-mapped
    version.json                      written last; presence = installed
  indexes/
    range-0.2-0.4.ncidx               one file per field range (§4.4)
    range-0.4-0.8.ncidx
    ...
  .staging/                           partial downloads and builds
```

- `version.json` records the source (Zenodo record, version, DOI, file name),
  both published SHA-256 checksums, the fetch or import time, the licence and
  the attribution text. It follows the DSO catalog pattern: files go into a
  staging folder and are moved into place by an atomic rename, and
  `version.json` is written last.
- Each index file carries its own header recording the star file's checksum,
  the index format version, the range and its build parameters. An index whose
  star file or format version doesn't match is shown as needing a rebuild and
  is never used.
- `APP_DIR` is read at call time (`app_config.APP_DIR`), never copied at
  import, as `tests/test_app_dir_isolation.py` enforces.
- Nothing about the star data is stored in a database. Which ranges are built
  is read from the files on disk.

### 4.2 Download and import

- **Pinned source (Claude's call).** The record id, file name, size
  (1,142,276,749 bytes) and both checksums are constants in the code:
  - compressed `siril_cat_healpix8_astro.dat.bz2`:
    `846ad4b12c50865df0cb8c5b23453f22eec78bbe9969e17d669ae19eb49d421f`;
  - uncompressed `siril_cat_healpix8_astro.dat`:
    `2fa40c93fe115235d35c5050757f2ef60a326a6f3030f87be1598c016fcb2388`.

  These are the published `.sha256sum` files from the record, downloaded
  2026-10-26 and verified against the file by the prototype. The record has
  one version (1.0.0, 2025-01-20; Zenodo API checked 2026-10-28).
- **Resumable streaming download.** Zenodo serves byte ranges (checked
  2026-10-28: `206 Partial Content`, `accept-ranges: bytes`). The download
  streams to `.staging/` and is never held in memory. If it is interrupted
  (network, Cancel, server restart), the partial file stays, and the next
  Download continues from its current size. A partial file larger than the
  published size, or a checksum mismatch at the end, is deleted, and the user
  is told to start again.
- **One stream** (revised after the Codex plan review). Parallel byte ranges are left out of this version;
  they would only speed up a one-time download, and single-stream recovery
  matters more. A partial file that is already complete is verified without
  a new request; a range response with the wrong `Content-Range` is
  rejected; writes never go past the published size; and a verified
  compressed file survives a failed unpack, so the next attempt only
  unpacks.
  - **Superseded 2026-11-01 by v0.43.1:** the download now uses four parallel
    byte-range pieces with verified assembly and retains this single stream as
    the fallback when a server does not honour ranges.
- **Only when not installed.** Download and import run only when the stars
  aren't installed; to replace them, the user removes them first.
- After the compressed checksum passes, the file is decompressed (about 40 s)
  while the uncompressed checksum is computed. The result is renamed into
  place, `version.json` is written, and the `.bz2` is deleted.
- **Disk check:** before starting, at least 2.8 GB must be free in the app
  data folder (download plus unpacked file); otherwise the section says how
  much is needed and doesn't start.
- **Import:** "Import file…" opens the existing server-side file browser. It
  accepts the `.bz2` or the unpacked `.dat`, verifies the matching checksum,
  and copies (never moves) the file into place by the same staging path. The
  user's file is never modified.
- **Running it.** A request starts the download as an app-owned asyncio task;
  the section polls a status route for bytes done, speed and time left. This
  is the same request-driven pattern as the thumbnail and sky-tile fetches,
  not a job system. Nothing starts or resumes at server startup.
- Outbound HTTP goes through a new streaming helper in
  `services/http_client.py`, with the same logging style and the same retry
  rule for transient failures. A failed range request is retried once, and
  the user can always resume.

### 4.3 No automatic updates (Claude's call)

The pinned version is the only one NightCrate accepts. Adopting a newer Siril
version needs a NightCrate release that verifies its format and pins its
checksums. Admin does not check Zenodo for new versions. There is one version
so far, and accepting an unverified file would undermine the "never wrong"
goal.

### 4.4 Field ranges and the index

**Revised by Fred (2026-10-29), after the range-boundary check in §11:**
Admin offers two choices instead of six ranges, following Seti Astro Suite
Pro's approach:
- **Standard:** the 8′ to 256′ layers. It covers fields of 0.4° to 10°,
  takes 529 MB, and needs about 3.2 GB of memory to build. It is ticked by
  default (recommended), whatever the user's rigs.
- **Narrow fields:** the 4′ layer. It adds fields of 0.2° to 0.4°, takes
  1.39 GB, and needs about 5.4 GB of memory to build. It is ticked by default
  when one of the user's rigs has a field under 0.4°.

Why:
- **The finding.** A field near the bottom of one of the six ranges needed
  the next smaller layer. Neighbouring layers overlap, and a field near a
  boundary is solved by both (SASpro's help page says the same).
- **The cost of the alternative.** Pairing each range with the layer below
  would have made a lone 0.4–0.8° rig cost 1.77 GB. The two choices cost any
  user at most about 0.5 GB more than the old minimum, apart from narrow-field
  users, who need the 4′ layer anyway.
- **Simpler for users.** Two choices are easier to explain than six.

Every solve searches all built layers. The rest of this section is unchanged
where it doesn't conflict: each choice is a "range" in the manifest, layers
are shared and stored once, and Remove keeps layers that another built
range still uses. The original text and table below are kept as the record.

**Fred (original):** users choose which field ranges to index. Each range shows its size,
whether it covers one of their rigs, its status and a Remove button. Ranges
that cover their rigs start ticked. Each range builds and is removed on its
own.

The prototype built seven layers of star patterns, each for patterns of one
size. A range maps to the layer whose patterns fit its fields (prototype rule:
field width ≈ 4.5 × pattern size).

| Range (field width) | Prototype layer | Size (measured) |
|---|---|---:|
| 0.2° – 0.4° | q = 4′ | 1.39 GB |
| 0.4° – 0.8° | q = 8′ | 383 MB |
| 0.8° – 1.6° | q = 16′ | 106 MB |
| 1.6° – 3.2° | q = 32′ | 29 MB |
| 3.2° – 6.4° | q = 64′ | 8 MB |
| 6.4° – 10° | q = 128′ and q = 256′ | 3 MB |

- **To verify before the boundaries are final:** whether a field near a
  boundary needs its neighbouring layer. The prototype always had every layer
  from 8′ up. The plan includes a corpus run with one range built at a time.
  If neighbours matter, a range also builds its neighbouring layer, and the
  table's sizes change.
- **A rig's field** is the longer side of its sensor's field, from the rig's
  telescope, reducer and camera, computed the same way the solve dialog's
  equipment hints do today. Rigs come from the current database; the ticks are
  only a starting suggestion.
- **Building** (revised after the Codex plan review):
  - The prototype's whole-sky builder runs unchanged, one layer at a time, in
    its own child process. Its threads are sized by the existing
    `max_worker_cores` setting.
  - Its memory never sits in the server process, and the child is joined in
    `finally`.
  - Progress is polled like the download. Cancel terminates the child and
    deletes its whole temporary folder. A build first checks for free space
    of 3 × the range's size, because the builder holds several temporary
    files at once.
  - A finished layer moves into place by atomic rename.
- **Memory** (revised after the Codex plan review). The prototype's builds peaked at 3.2 GB (8′) and 5.4 GB
  (4′).
  - Building in portions of the sky to stay under 2 GB was dropped. Proving
    that a portioned build gives exactly the same index needs ordering, tie
    and boundary rules the prototype never had, for a one-time build the
    user opts into.
  - Admin instead shows "Building needs about N GB of memory." under any
    range above 2 GB, with the figure measured on the product build.
- **Which ranges are built** (revised after the Codex plan review) is recorded in a small manifest beside the
  index files, written atomically. Layer files alone can't say which ranges
  the user chose once two ranges share a layer.
- **Remove.** Takes the range out of the manifest, then deletes the layers no
  remaining manifest entry lists, whether or not that range is ready. Memory-mapped files are closed first, because
  Windows cannot delete a mapped file. Remove is refused (409) while a solve
  is running.
- **Builds and solves** (revised after the Codex plan review). A build may start while a solve runs. Only its
  last step, swapping the finished file into place, waits for the solve to
  finish. A solve requested during that brief swap gets the usual
  "already in progress" message. This replaces "build is
  refused while a solve runs", which would have blocked solving for the
  minutes a build takes.
- **Removing the stars** removes every index too, after a confirmation that
  states the space freed.
- **Status shown:** not built, building with a percentage, built, or needs
  rebuilding (§4.1). The total space used appears below the table.

### 4.5 Admin routes

New routes under `/api/admin/star-catalog/`, following `api/admin.py`'s
existing catalog routes:

- `GET status`: installed version, file sizes, download or build progress,
  each range's state and size, rigs covered per range, free disk space.
- `POST download`, `POST download/cancel`, `POST import` (path).
- `POST ranges/build` (list of ranges), `POST ranges/cancel`,
  `DELETE ranges/{range_id}`, `DELETE` (remove everything).

One star-data operation runs at a time (download, import, build or remove);
another request gets 409.

## 5. Solving

### 5.1 One flow, no mode choice

**Fred:** the dialog no longer offers a choice between a solve near a
position and a blind solve. Following the approved mockup
(`solve-dialog.html`, states A, C and D; §6.3 replaces state B):

1. Load the image through `services/pixel_loader` (plain, archive, XISF and
   `.pxiproject` paths; worker-safe; rows top-down). No temporary FITS is
   written for the native solver.
2. Detect stars with sep, following the prototype's extraction settings,
   including its binning rules for large frames.
3. **Near a position** (revised after the Codex plan review). This uses only modes the prototype measured.
   - **With a position and a scale** (from the header, a chosen target, or
     the equipment hints): if the field's range is built, search the index
     around the position with that scale (`native-header-index`). If not, use
     the catalogue-only solver around the position (`native-header`), which
     needs no index, is slower, and tries 0.5× and 2× of the scale itself.
   - **With a position but no scale:** a blind solve first, then the
     catalogue-only solver around the position (`native-target`) if blind
     didn't solve or couldn't run. The catalogue step doesn't depend on
     which ranges are installed, so building an unrelated range never stops
     an image that used to solve.
4. **Blind** (with a position and a scale, after near; with no position, on
   its own; always only when at least one range is built): scale-known first
   when a scale is known
   (`native-blind-scale`), then unknown scale (`native-blind`). A wrong
   header scale, such as a binned master carrying the unbinned value, is
   recovered by the unknown-scale step. The prototype measured both binned
   M33 masters solving this way.
5. Accept only a solution that passes verification (§5.2), then refine the
   TAN fit against the Siril stars in the field.

The result records which path solved it: near a position, near a position
without the index, or blind, and the scale stage.

### 5.2 Never wrong

- Verification follows the prototype: an image-centred likelihood ratio over
  every detection (Lang et al. 2010), with an acceptance bar of odds of 10¹⁸
  for every path, and three-quadrant coverage.
- **Every search through the index** (near a position or blind) uses the
  blind settings: at least 12 matches and at most 0.2° axis
  non-orthogonality, plus the blind extraction profile and code tolerance.
  These are the settings the prototype's index search ran with when it was
  measured, near a position (`native-header-index`, 0.48 s median,
  106 of 106) as well as blind. The 0.2° limit rejected the sheared
  wide-field false fits in the real-index trials; the largest accepted corpus
  shear was 0.108°.
- **The catalogue-only solver** keeps its own measured settings: 10 matches
  and 3°. It is used only near a position, when the index can't be used
  (§5.1).
- After the first accepted candidate, the remaining candidates in that pass
  are checked. A second accepted answer at a different sky position (more
  than 1% of the image diagonal away) or with the other parity makes the
  result **ambiguous**. An ambiguous result is reported as not solved and is
  never saved.
- **A check cut short is not a solve** (revised after the Codex plan review). If the time budget or a cancel
  arrives before that ambiguity check has finished, the result is not solved.
  The prototype's catalogue-only solver already did this; its blind solver
  did not, and the port fixes it.
- These thresholds are not loosened to raise the solve rate without Fred's
  decision.

### 5.3 Output conventions

- TAN WCS in NightCrate's stored convention: rows counted from the top,
  1-based `CRPIX`, CD matrix in degrees per pixel, the same convention as
  ASTAP results after v0.42.0's row fix. Both parities are supported.
- Rotation uses the corrected-solution rule in
  `docs/development-decisions.md` (Plate solving):
  `degrees(atan2(-CD1_2, CD2_2))`.
- Pixel scale and field of view are computed as for ASTAP results, so
  overlays, the field of view and object search need no change.
- Star positions use the prototype's fixed epoch, J2026.0 (Claude's call).
  For nearly all stars, the error from the observing date is under 0.1″ over
  a decade, far below a pixel at any supported scale.

### 5.4 Running a solve

- **One solve at a time**, native or ASTAP, under the existing semaphore and
  409 rule.
- **A worker thread, not a process (Claude's call).** A process pool would add
  the cost of starting a Python process and importing numpy, scipy and
  astropy to every solve, roughly a second. The median target is under one
  second. The solve therefore runs in a thread through `asyncio.to_thread`,
  so the server keeps responding, and the star file and indexes are
  memory-mapped once and reused. The plan measures both options on Fred's Mac
  before committing to this.
  - The solver is numpy-only. It never touches the GPU backend, which must not
    be used from worker threads.
  - Cancel is cooperative. The solver checks a cancel flag and its time
    budget between candidates. The existing cancel route sets the flag for a
    native solve and keeps killing the process for ASTAP.
  - **The worker owns the solve slot until it has actually stopped**
    (revised after the Codex plan review). A cancelled request signals the worker and waits for it before the
    slot is released. Server shutdown signals it too, and closes the
    memory-mapped files only once it has stopped.
- **Time budgets** (revised after the Codex plan review):
  - a near or catalogue-only step has 20 s, the prototype's own budget;
  - the blind scale-known step has 10 s (its measured P95 was 3.1 s);
  - the blind unknown-scale step has 30 s, the prototype's blind budget;
  - the whole solve, including loading, has 60 s;
  - a step that runs out of its own time hands over to the next one;
  - When nothing solves:
    - "field not built" wins when the field is known and its range isn't
      built;
    - otherwise "ran out of time" when any search was cut short;
    - "no match" only when every search finished.
- **Minimum stars** (revised after the Codex plan review): 12 detections for an index search and 10 for the
  catalogue-only solver, the prototype's match minimums. "Too few stars" is
  reported only when no possible step has enough.
- **Progress:** the existing progress route reports plain steps, such as
  "Loading image", "312 stars detected", "Searching near M42", "Blind solve:
  fields 0.4°–0.8°" and "Checking a match".
- **Failure reasons** (shown in state C or D): stars not installed; no range
  built; too few stars detected (with the count); no match (with the count
  and the ranges searched); a field outside the built ranges (when the field
  is known, naming the range to build); ambiguous; time limit; image
  unreadable.

### 5.5 Choosing the solver

- **New setting `default_solver`:** `"native"` (default) or `"astap"`, in
  `core/config.py:Settings`, stored per database like every setting. No
  migration is needed for settings.
- The solve requests (`PlateSolveRequest`, `ProjectSolveRequest`) gain an
  optional `solver` field. Omitted, it means the default; the dialog sends
  `"astap"` for "Solve with ASTAP".
- `mode` stays on `PlateSolveRequest` for ASTAP only; the dialog sends
  `"auto"`. The native solver ignores it.
- **If native is the default but the stars aren't installed,** the dialog shows
  state D: "Open Admin", plus "Solve with ASTAP" when ASTAP is set up.
- **If ASTAP is the default,** solving behaves as today. A failed ASTAP solve
  does not offer the native solver (Claude's call: the roadmap names only the
  native → ASTAP direction).

## 6. Results and records

### 6.1 Result fields

`PlateSolveResult` and `ProjectSolveResponse` gain:

| Field | Native | ASTAP |
|---|---|---|
| `solver` | `"native"` | `"astap"` |
| `star_catalog` | `"Siril Gaia DR3 astrometry 1.0.0"` | null |
| `stars_detected` | count | null |
| `stars_matched` | count | null |
| `rms_px`, `rms_arcsec` | fit residual | null |
| `log_odds` | verification score | null |
| `solve_path` | §5.1 path and scale stage | null |

ASTAP values stay null because NightCrate does not get them from ASTAP; a
missing value is not invented.

### 6.2 Migration 0065

`project_solve` gains columns by `ALTER TABLE ... ADD COLUMN`, so no table is
rebuilt and no child table is touched:

- `solver TEXT NOT NULL DEFAULT 'astap' CHECK (solver IN ('native', 'astap'))`.
  Every existing row was solved by ASTAP, so the default is correct for them.
- `star_catalog TEXT`, `stars_detected INTEGER`, `stars_matched INTEGER`,
  `rms_px REAL`, `log_odds REAL`, `solve_path TEXT`, `scale_stage TEXT`, all
  nullable. (`scale_stage` was added after the Codex plan review, so a saved
  solve can report it.)

`rms_arcsec` is derived from `rms_px` and the scale, so it is not stored. The
Image Analyzer's solves are still not saved. `DB_SCHEMA_DDL.sql` and
`DB_SCHEMA.md` are updated.

### 6.3 Display

**Fred:** three rows are added wherever a solution is shown: Solver
("Built-in · Gaia DR3 (Siril 1.0.0)" or "ASTAP"), Stars ("248 matched of 312
detected") and Fit error ("0.41 px RMS (0.80″)").

- **Fred (after the builder check):** the dialog keeps closing itself on a
  successful solve, as it has since April 2026 (commit 8c14a32). The rows
  therefore go where results already appear: the Image Analyzer's
  "Astrometric Solution" sidebar section (`PlateSolveDetailPanel.tsx`), and
  the saved solve's summary on a project's Plate Solve tab
  (`ProjectPlateSolveTab.tsx`). The mockup's state B, an open "Solved"
  dialog, is not built.
- The Image Analyzer currently keeps only the WCS from a solve. It now keeps
  the whole result, so the sidebar can show the rows. A solution read from
  the image header has no solver rows.
- Older project solves show "Solver: ASTAP" and omit the other two rows. **Claude's
call (accepted with the mockup):** confidence is saved but not shown, because
every accepted solve clears the same very high bar.

## 7. Screens

All screens follow the two approved mockups. Colours are theme tokens, and the
UI uses no red/green or purple/amber pairs.

- **Admin → Plate-solving stars:** §4. The attribution line names ESA/Gaia
  (DPAC) and the Siril team, with both licences.
- **Solve dialog** (`PlateSolveDialog.tsx`, shared by the Image Analyzer and
  `ProjectPlateSolveTab.tsx`):
  - state A: the "Blind solve" chip shows when no position is known, and a
    line names the solver;
  - a successful solve closes the dialog, as today (§6.3);
  - state C: the failure reason with Retry, plus "Solve with ASTAP" when ASTAP
    is set up;
  - state D: stars not installed.

  The near/blind choice and the 300 s blind timeout go. The "From Reference
  Image" tab and the equipment hints stay as they are.
- **Settings → Plate Solving** (`AstapPathSection` in `SettingsPage.tsx`): a
  "Default solver" choice (Built-in / ASTAP) above the ASTAP path. The path's
  help text says ASTAP is optional.
- **Image Analyzer sidebar and project Plate Solve tab:** the new rows
  (§6.3).

## 8. Credits and terms

- README acknowledgments:
  - the Siril Astrometry Catalogue (Siril team, CC BY 4.0, with its DOI);
  - ESA/Gaia DPAC with ESA's standard acknowledgement text;
  - Lang et al. (2010);
  - the solvers whose source informed the design: SASpro (GPL-3.0) and
    astrometry.net (GPL-3), plus any of ASTAP, tetra3 or twirl that the
    implementation actually consults.

  A log of the files read is kept in the local records.
- NightCrate makes no claim that the star data may be used commercially. The
  Admin section and README state that Gaia's CC BY-NC 3.0 IGO terms also
  apply.
- No code is copied from any solver. The prototype is NightCrate's own code,
  written under the same rules.

## 9. Code layout (Claude's call)

The prototype's solver modules are ported, not rewritten. They are the code
whose measured behavior Fred accepted, and a rewrite would have to be proved
again on the corpus. The port cleans them up to product standards (typed
models, `[plate_solve]` log prefixes, no benchmark-only branches), and the
benchmark checks that the port matches the prototype's results.

- `services/star_catalog/`: the Siril reader (memory-mapped cone queries),
  download and import, the index format and builder, and status. No FastAPI
  imports.
- `services/native_solver/`: extraction, geometry, the solve paths,
  verification and refinement, plus the result model. Pure functions that
  take loaded arrays and catalog handles.
- `services/plate_solve.py`: dispatches between native and ASTAP and keeps
  the existing ASTAP code unchanged.
- `api/admin.py` (or a new `api/star_catalog.py` router), `api/plate_solve.py`
  and `api/project_solve.py`: HTTP, the semaphore, saving.
- **Not ported:** the ESA cell fetcher (superseded), memory probes, coverage
  diagnostics and trial generators. Trial generation needed by tests moves into
  the test suite.
- **Benchmark script:** `backend/scripts/plate_solve_benchmark.py` (path set in
  the plan). It takes the corpus folder and an output folder on the command
  line, writes results outside the repository, and runs native and ASTAP
  through the product code paths.

## 10. Tests

Unit and API tests, run without network or the real star file:

- **A synthetic star file in Siril format,** written by the tests for a few
  sky patches, so reading and cone queries run against known values. Header
  validation rejects a wrong magic number, version or size.
- **Index build and lookup** on that synthetic catalog. A built range finds a
  known pattern; a mismatched source checksum is reported as needing a
  rebuild.
- **Solves of synthetic images rendered in memory:** each solve path, both
  parities, a 2× wrong header scale recovered by the scale stages, and a field
  outside the built ranges. Each checks an off-centre star's pixel position
  against the known answer, in the top-down convention.
- **Never wrong:**
  - random-dot images are never solved;
  - an ambiguous case (two equally good answers) is reported as ambiguous;
  - trials with brightness scatter and spurious stars calibrated to the
    corpus (spurious fluxes drawn from the star range; scatter σ ≈ 0.25 mag,
    P90 0.4) give no wrong answers.
- **Download** against a local HTTP test server:
  - resume after an interrupted stream;
  - a partial file larger than published is deleted;
  - a checksum mismatch is rejected, and nothing is marked installed;
  - the disk-space check;
  - cancel;
  - `version.json` is written last.
- **Import** of `.bz2` and `.dat`, plus a wrong file, and the user's file left
  unmodified.
- **Remove order:** maps are closed before a file is deleted; remove and build
  are refused during a solve.
- **Migration 0065** on a database at 0064 with existing solves: rows get
  `solver = 'astap'`, the other new columns are null, and integrity and
  foreign-key checks are clean. A fresh database builds too.
- **API contracts:** the new fields, the `solver` request field, the
  default-solver setting, 409s, and each failure reason's message.
- **App data isolation:** star data follows the redirected `APP_DIR` in tests.

## 11. Verification beyond tests (high-stakes)

### 11.1 Checks

- **Corpus benchmark** (Fred's local corpus, product code, one image at a time
  on an idle machine): native and ASTAP, in the same modes as phase 2c, with
  one range built at a time for the boundary question (§4.4).
- **Calibrated synthetic trials,** thousands across the sky, including south
  of −30° and fields over 5°, which the corpus lacks.
- **The real download** from Zenodo once, including an interrupted resume.
- **Index builds of every range** on Fred's Mac, recording time and peak
  memory.
- **Migration gate:** a copy of Fred's database at 0064 upgraded through the
  app's runner, plus a fresh database.
- **Rendered checks** of the Admin section and every dialog state, in light
  and dark at 1500 and 820 px.
- **A fresh independent Codex review** (dependency-free, but high-stakes:
  migration, external data and its terms, outbound HTTP, concurrency,
  scientific results).

### 11.2 The bar for native as the default

Unchanged from the roadmap:

- a solve rate at least ASTAP's on the corpus;
- no wrong solutions on the corpus or in thousands of synthetic trials;
- a median time no worse than ASTAP's;
- fully blind solves with a median of 3 s or less and 95% within 10 s on the
  corpus, including image loading.

**How it is measured** (Claude's call, fixed in the plan before any run):

- Each solver runs its product flow:
  - native uses the header or target position when there is one, then falls
    back to a blind solve;
  - ASTAP runs as today: near the header position, otherwise blind with the
    field given.
- **Solve rate:** over all corpus images that should solve (143 in the
  prototype's corpus), native at least ASTAP.
- **Median time:** over the images both solve, including image loading,
  native no slower than ASTAP. Failures are excluded here, because ASTAP's
  run up to 180 s and native's up to 60 s.
- **Fully blind target:** native with position and scale removed, on the
  subs and masters (106 in the prototype's corpus). Failures count at their
  elapsed time in the median and P95.
- **No wrong answer:** in any mode, or in the synthetic trials.

If the product misses the bar, `default_solver` defaults to ASTAP and the
result goes to Fred before release.

**Fred (2026-10-29):** the corpus benchmark missed only the median time
(native 0.53 s against ASTAP's 0.39 s, one new process per image). Timed the
server's way, native took 0.35 s against ASTAP's 0.37 s. Fred kept native as
the default, because some users won't have ASTAP set up at all.

## 12. Process

Staged as `docs/agent-collaboration.md` describes:
- this spec, then Fred's approval;
- an implementation plan;
- an independent Codex plan review;
- Fred's approval of the final plan;
- Codex implementation by phase, with Claude's review;
- the checks in §11;
- candidate preparation;
- Fred's acceptance test.

**Fred (2026-10-28):** he stopped his `make dev` server, so the work happens
in the main checkout on the version branch, with no worktree. The server stays
stopped until the migration gate has passed, because migration 0065 must not
reach his real database before it has been checked on a copy.

Migrations run at startup against the database the app config marks active.
So any server running this version's code before the migration gate (rendered
checks, trying the download or index builds) runs with a temporary home
folder holding a copy of Fred's database and config, as the v0.42.0 checks
did. The real star file is imported into that temporary app data folder;
Fred's own app data is never written.

## 13. Out of scope

- Solving subs during cataloging, SIP distortion, ASTAP database reuse, GPU
  acceleration, following new Siril versions.
- **A lighter image loader.** A float32, single-channel, binned loader would
  cut the loader's memory peak (3.8 GB on the largest mosaic); this affects
  ASTAP solves too.
- **The two rotation formulas noted in the 2026-10-26 research.**
  `image_annotations.compute_rotation` uses `atan2(cd2_1, cd2_2)`. Only native
  results use the plate-solving rule; the other formula is unchanged and
  stays in the deferred list.
- Windows runtime testing. The code is written for Windows (memory-map
  closing, paths), but no Windows machine is in the loop.

## 14. Calls Claude made for Fred to check

1. Pin Siril version 1.0.0 and its checksums; no update check (§4.2, §4.3).
2. *Revised:* one download stream; parallel byte ranges are left out of this
   version (§4.2).
3. *Revised:* the prototype's whole-sky index builder in a child process,
   with its memory shown in Admin, instead of building in portions of the
   sky (§4.4).
4. A range maps to one prototype layer, pending the boundary check (§4.4).
   *Added:* a manifest records which ranges the user built.
5. Solves run in a worker thread with cooperative cancel, not a process,
   pending a measurement (§5.4). *Added:* the worker holds the solve slot
   until it has stopped.
6. *Revised:* 20 s near, 30 s blind, 60 s overall (§5.4).
7. Fixed star epoch J2026.0 (§5.3).
8. A failed ASTAP solve doesn't offer the native solver (§5.5).
9. ASTAP's stars, RMS and confidence stay empty rather than estimated (§6.1).
10. Confidence saved but not shown (§6.3).
11. Port the prototype's code rather than rewrite it (§9).
12. If native misses the bar, ASTAP stays the default and Fred decides (§11.2).
13. How the bar is measured: product flow against product flow, solve rate
    over every image that should solve, and median time over images both
    solve (§11.2).
14. *Added:* the solve order uses only the prototype's measured modes; the
    index search near a position has no 0.5×/2× scale retries (§5.1).
15. *Added:* a build may run during a solve; only its file swap waits (§4.4).
16. *Added:* download and import only when the stars aren't installed
    (§4.2).
