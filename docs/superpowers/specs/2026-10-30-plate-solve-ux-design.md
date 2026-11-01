# Plate solving: solver fixes and a simpler solve UI (v0.43.0 addendum)

Addendum to [the native plate solver spec](2026-10-28-native-plate-solver-design.md).
Where the two differ, this one wins.

## 1. Why

Fred's acceptance test of the v0.43.0 candidate failed on a real image, a
stretched and cropped stack from a small smart telescope. Neither solver
solved it from the project Plate Solve tab. Fred also found the solve UI
confusing:

- options weren't clear;
- "From Reference Image" meant nothing to him;
- the chosen image wasn't shown before solving;
- a failure meant choosing the image again.

## 2. Fred's decisions (2026-10-30)

1. Fix the solvers and redesign the whole plate-solve UI in v0.43.0, before
   release. Fred re-tests the new candidate.
2. The UI follows the approved clickable mockup (§9). Fred: "I like this UX
   much better."
3. **Remove "From Reference Image"** (the stars-only copy), with its
   `validate-reference-image` route. A failure instead points to the
   stacked image from before processing.
4. **No telescope-and-camera picker** for the pixel scale. A rig already
   pairs them.
5. **ASTAP searches the whole sky by itself** after a miss near the
   position, within its 3-minute limit, with the steps shown and Cancel
   available.

Unchanged from the main spec:

- built-in is the default;
- "A failed native solve offers 'Solve with ASTAP' and never retries
  automatically";
- the acceptance thresholds (§5.2) are never loosened without Fred.

## 3. Root causes (each reproduced)

1. **Built-in, stretched images.**
   - The verification detections drop any star with three or more pixels at
     or above 0.995 in its 5×5 patch (`native_solver/extract.py`).
   - In a stretched image that is every bright star. Verification compares
     the detections with the brightest catalog stars in the frame, so the
     true pose scored a log-odds of about −208.
   - Verifying with the saturation-inclusive set solved the image in
     0.35 s, with 180 of 250 matched and a centre within 0.3″ of ASTAP's.
2. **ASTAP, wrong field.** Rig and Equipment hints sent a field height of
   pixel scale × the sensor's full height. That is 14% too large for a
   948-row crop of a 1080-row sensor, and ASTAP's position search failed
   with it, normal and slow. A whole-sky ASTAP search with the same wrong
   field solved in 1 s.
3. **Other defects:**
   - manual hints were never sent;
   - header binning was counted twice;
   - the project tab never prefilled header equipment, because the header
     arrived after the dialog's reset;
   - ASTAP had no blind step, and its message suggested one;
   - an ASTAP "solved" result wasn't checked for a complete WCS;
   - an ASTAP failure could hide behind the star-setup screen;
   - "Retry" repeated an identical search;
   - dismissing the dialog didn't cancel, so a late result could attach to
     another image;
   - cancel wasn't tied to one solve;
   - plain FITS with HDU > 0 went to ASTAP unconverted;
   - the success screen was never shown;
   - the Analyzer offered solving only when the file had no header WCS.

## 4. Built-in solver

- **One saturation-inclusive detection population** for verification, the
  index search and catalog-only solving. It comes from an explicit
  extraction policy; scaling intensities to dodge the saturation test is
  not used.
  - The acceptance thresholds and the ambiguity checks are unchanged.
  - If the corpus or the false-match trials regress, the fallback is to
    choose the population per image (inclusive only when the brightest
    stars are clipped). Either way, Codex reviews it before Fred decides.
- **The 10 corpus finals the built-in solver still fails** (galaxy and
  nebula PNG, JPEG and XISF) get a time-boxed diagnosis against independent
  WCS truth.
  - Truth comes from a blind ASTAP solve where one exists (the Heart Nebula
    final), or from the project's solved stack.
  - Instrument: true-star coverage among the top 80, the candidate caps, the
    cheap check and full verification.
  - Fix only a clear root cause that passes the corpus and the trials;
    otherwise record the finding and report it to Fred.
- The solve sequence (near → blind with scale → blind without scale), the
  budgets (20/10/30 s, 60 s overall) and the thresholds are unchanged.

## 5. ASTAP

- **A step chain with typed outcomes:** `solved`, `no_solution`,
  `too_few_stars`, `step_timeout`, `overall_timeout`, `cancelled`, `error`.
  - **Step 1, near:** the position and the field from the scale hint (when
    there is a position), capped at 60 s, so the whole-sky step always has
    at least 120 s minus preparation.
  - **Step 2, whole sky:** `-r 180`, with the field from the scale hint, or
    `-fov 0` when no scale is known.
  - The chain advances after `no_solution` or `step_timeout` while time
    remains. It stops on `solved`, `cancelled`, `error`, `overall_timeout`
    and `too_few_stars`. With no position, step 1 is skipped.
  - The unchanged-hint `-speed slow` retry is dropped unless the corpus run
    shows it rescues an image that step 2 doesn't.
- **One monotonic 180 s deadline**, including image preparation. Each step
  gets the time remaining.
- **A complete WCS before `solved`:**
  - finite `CRVAL1` in [0, 360) and `CRVAL2` in [−90, 90];
  - finite `CRPIX1/2` and all four CD elements;
  - a non-singular CD matrix;
  - a finite positive scale;
  - positive dimensions.

  Otherwise the result is "ASTAP returned an incomplete solution".
- **The FITS file ASTAP reads:** an HDU > 0 is written to a temporary FITS
  first. The field passed to ASTAP is scale × the height of the file ASTAP
  actually reads.
- **Messages state what was tried** and never suggest an action the UI
  lacks.

## 6. Hints and request contracts

- **Pixel scale, not field height.** `scale_hint_arcsec` (″/px) on
  `PlateSolveRequest` and `ProjectSolveRequest`.
  - Precedence: request scale, then the legacy `fov_hint` (kept as a
    deprecated adapter), then the header.
  - Values must be finite and > 0. RA/Dec are accepted only as a finite pair
    in range.
  - `mode` and the reference route are removed.
- **The header rule has one home, the backend:** `YPIXSZ`, falling back to
  `XPIXSZ`, with `FOCALLEN`.
  - While the user hasn't changed the scale, the client sends none.
  - The panel's display mirrors that rule.
  - "Search without a scale" or "Search without a position" sends an
    explicit ignore, so it's distinguishable from "use the header".
- **The calculated scale** uses the *physical* pixel size × binning ÷ focal
  length × 206.265. Rigs supply the physical pixel size.
- **Attempts.** Every result, and the project 422, carries `attempts`. Each
  `SolveAttempt` has:
  - `solver`;
  - `step` (`near_index`, `near_catalog`, `blind_known_scale`,
    `blind_unknown_scale`, `astap_near`, `astap_blind`);
  - `position_source` and `scale_source` (`request` / `header` / `none`);
  - `ranges` and `layers` searched;
  - `outcome` (`solved`, `no_match`, `skipped`, `step_timeout`,
    `overall_timeout`, `cancelled`, `ambiguous`, `too_few_stars`, `error`);
  - `seconds`.
- **Operations.**
  - The client sends an `operation_id` (UUID) with each solve.
  - `POST /plate-solve/cancel {operation_id}` cancels only that operation.
    A cancel for an operation that hasn't claimed the slot yet is recorded
    (at most 64 entries, each kept for 10 minutes). It is checked when the
    slot is claimed, and again just before the project INSERT, so a pending
    cancel stops the solve or the save.
  - `GET /plate-solve/progress?operation_id=` returns the operation's
    snapshot:
    - completed `attempts`;
    - `active_step` (with its sources and ranges);
    - `planned` (the steps still to come, shown as "Waiting");
    - `elapsed_seconds`.

    The UI never infers steps from time or text.
  - An operation lasts until the endpoint has finished *everything* it does,
    including a project's render and save, not only the solver. A cancel
    during rendering stops the save. Reusing an ID returns 409.
  - An attempt's `ranges` and `layers` are the ones actually searched,
    recorded inside the search loop, not the ones that were available.
    ASTAP's "no solution" is recorded as `no_match`.
- **Project replace after success.** `ProjectSolveRequest.replace: bool`.
  - Without it, an existing solve still returns 409.
  - With it, the rendered images are an immutable *generation* per solve
    row, in `solve/<solve id>/<variant>.jpg`:
    1. solve, and render into a staging folder;
    2. in one transaction, re-check cancellation, delete the old
       `project_solve` (its `project_dso` rows cascade), insert the new row
       and its objects, rename staging to `solve/<new id>/`, then commit;
    3. a failed rename rolls the transaction back;
    4. a failed commit removes the new folder;
    5. after commit, the old generation is deleted on a best-effort basis.
  - The image route serves the current row's generation, falling back to
    the legacy `solve/<variant>.jpg` for solves saved before this change.
    Any crash leaves either the old row and old images, or the new row and
    new images. A stray folder is never served and is cleared on the next
    delete or replace.
  - `project_target` (main targets) is untouched, and the best guess is
    added with `INSERT OR IGNORE`, as today. No migration.
  - Image URLs are versioned by solve ID. A leftover folder for a reused row
    ID is removed before the rename. A project solve takes HDU 0 only.
  - Replace, delete and solve publication for one project are serialized.
- **Preview route:** `GET /api/images/preview?path=&hdu=&max_px=`.
  - Returns a sized, auto-stretched JPEG for any path that `path_resolver`
    handles.
  - **Memory:**
    - FITS reads a strided section from the memory map before converting to
      float32;
    - standard images use PIL's reduced decoding;
    - XISF and `.pxiproject` images decode and then decimate, one at a time;
    - only encoded JPEGs are cached, within a 32 MB budget;
    - a concurrency permit is held until the worker thread actually ends.
  - **Cache identity**, from a stat taken before decoding:
    - plain files: real path, size and mtime;
    - archive entries: the archive's identity plus the member name;
    - project images: the manifest's identity, the image index and the
      backing file's identity.
  - Responses carry an ETag with `Cache-Control: no-cache`, so the browser
    revalidates.
  - Cold latency and peak RSS are measured on a full-size sub.

## 7. The plate-solve panel

One component, `PlateSolvePanel`, replaces `PlateSolveDialog`. It sits beside
the image, and below it on a tablet. File choosing and the remove
confirmation stay modal; solving never is.

- **Summary**, three rows, each with its source and a "Change" button
  (accessible names "Change starting position", "Change pixel scale",
  "Change solver"):
  - Starting position: "From the image header" + the coordinates, "From a
    target", or "None".
  - Pixel scale: "From the image header" + ″/px (focal length, pixel size),
    "From a rig", "Entered", "Calculated", or "None".
  - Solver: "Built-in" (Gaia DR3 star data) or "ASTAP".

  Below them: "These guide the first search. If it finds nothing, the solver
  widens the search by itself."
- **The editor** replaces the summary in the panel, with "Apply", "Cancel"
  (which discards unapplied edits) and "Reset to image header". Only the
  fields of the selected choice show.
  - Starting position: "Use the image header", "Choose a target", or
    "Search without a position".
  - Pixel scale:
    - "Use the image header";
    - "Use a rig", with binning;
    - "Enter the pixel scale";
    - "Calculate from focal length and pixel size", with binning;
    - "Search without a scale".

    Plus the note: "The scale must match this image, including any resizing
    or drizzle."
  - Solver: Built-in or ASTAP, each with its availability. "This changes the
    solver for this image only. The default is in Settings."
- **The primary action:** "Solve and save to project" (project), "Solve and
  replace saved solution" (project, replacing), or "Solve" (Analyzer).
- **Solving:**
  - "Solving with <solver> · N s";
  - a live step list from the progress snapshot, one row per step, with an
    icon and the words "Done", "No match", "Searching" or "Waiting" (never
    colour alone);
  - "Cancel solve".

  For ASTAP: "A search without a position can take up to 3 minutes. You can
  cancel at any time."
- **Failure:**
  - "No solution found" (or the precise outcome) and "Your image and hints
    are still selected.";
  - the step list stays;
  - "Change hints" and "Solve with <the other solver>" (when it's set up);
  - the help: "Heavily processed or cropped images can have too few usable
    stars. The stacked image from before processing usually solves.", with
    "Choose another image".
  - "Try again" appears only after a cancel, a time limit, a server or read
    error, or a change to the star data or configuration.
- **Setup needed:** an inline note, not a whole-panel screen. For example:
  "The built-in solver needs its star data, a one-time 1.14 GB download."
  with "Set up plate-solving stars" (a deep link to that Admin section) and
  "Use ASTAP instead". The image and hints stay.
- **Applied hints, the solver choice and the chosen image** survive a trip
  to setup and back:
  - a session snapshot keyed by surface, project and image;
  - the project page reads `?tab=plate-solve&solve=<path>&hdu=<n>`.
- **Requests:** each request has a client token bound to its image and HDU.
  - Late results, progress and callbacks are ignored.
  - Leaving or unmounting cancels the request, including the Analyzer
    staying mounted when hidden.
  - A stale project response refetches the saved solve instead of trusting
    the response.

## 8. Surfaces

- **Project Plate Solve tab:**
  - **Empty state:** "Place an image on the sky and identify its objects",
    with "Choose image" and this text (Fred asked for it, 2026-10-30; Codex
    drafted it and Claude checked it against the code):

    > Plate solving identifies catalog objects in this image. Choose one or
    > more main targets to organize the project's folders and frames in the
    > Catalog tab. Later, search will find projects and frames by their
    > main targets or by any object identified in them.

    In the solved view, above "Objects in image": "Choose one or more main
    targets for cataloging. Later, search will find projects by main target
    or any identified object."
    - Search by object isn't built yet; the text says "Later" and must not
      be shown as working.
    - Its two scopes (main targets only, or every identified object) are
      Fred's direction, in PLAN.md → Roadmap → Object search.
    - Several main targets are already supported (one `project_target` row
      per object).
  - **After choosing:** the file name and size, the preview ("Loading
    preview…", or "Retry preview" on failure), and the panel.
  - **Solved:**
    - the overlays on the same image;
    - "Solved and saved to project", with centre, pixel scale, rotation,
      field and solver;
    - "View solution details" (stars matched, fit error, the step that
      found it);
    - "Objects in image" with "Main target" checkboxes;
    - "Solve again" and "Choose another image", which both replace only
      after success, with "Not saved yet" and "Keep the saved solution";
    - a secondary "Remove saved solution".
  - The project tab solves and saves a file's primary image (HDU 0), as
    today (Fred, 2026-10-30: "first picture is fine"). Saved solves store no extension, and project images are
    single-image stacks. The Analyzer keeps its extension choice.
- **Image Analyzer:**
  - A "Plate solve" action is always on the Image and Identify tabs.
  - The Identify sidebar shows "Sky position" with its source: "From the
    image header", "From a built-in solve" or "From an ASTAP solve".
  - It offers "Solve again", and "Use the image-header solution" after a
    solve. "Shown here only. The file isn't changed."
  - A new solve overrides the header WCS in annotations (fixing the current
    precedence).
- **Settings:** the default solver and the ASTAP path, unchanged.
- **Admin:** "Set up plate-solving stars" links to that section.
- **Removed:**
  - the Solve/Reference tabs and the reference route;
  - the "Blind solve" chip;
  - the read-only RA/Dec boxes;
  - the Equipment picker;
  - the field-height display;
  - the dead success screen;
  - "Retry";
  - whole-dialog setup screens.

## 9. Approved mockup

The clickable mockup Fred approved is kept locally at
`.superpowers/mockups/v0.43.0/plate-solve-redesign.html` (ignored). The built
UI must match it. Records `88–92` hold the UI discussion with Codex, and
`78–87` the solver and contract discussion.

## 10. Verification

- **Backend tests** (in-memory synthetic):
  - hint precedence and validation, including X/Y pixel sizes and Y-only
    headers;
  - a rendered-pixel image with clipped stars through extraction, which
    fails today;
  - rendered negative and adversarial images through extraction and both
    verification profiles;
  - the ASTAP chain with a fake ASTAP: a near miss or timeout goes to the
    whole sky; cancel between steps; an error doesn't advance; stale
    sidecars; incomplete WCS including CRPIX; preparation using up the
    deadline;
  - operation races: a late cancel of A leaves B running; a pending cancel
    before the slot is claimed; a cancel before the project INSERT;
  - replace-after-success, including failure paths;
  - attempts through the project 422;
  - the preview route.
- **Corpus benchmark,** both solvers, against the §11.2 bar of the main spec.
  - Solves without an independent reference are reported as **unverified**,
    never counted toward "zero wrong", and get a target-in-field check.
  - Blind ASTAP has already confirmed three of the 18 previously unverified
    native solves to within 0.4″.
- **Synthetic false-match trials:** zero wrong.
- **The original failing image** solves with both solvers through the real
  endpoints on a temporary-HOME server.
- **Rendered checks** (headless, temporary HOME) at desktop and tablet widths,
  for both surfaces:
  - the preview, then the solve;
  - failure keeps the image;
  - the other-solver offer;
  - hint editing, with the request payload's scale for a rig and for a
    typed scale;
  - the header prefill;
  - setup round trips;
  - dismiss → reopen → the stale response is ignored;
  - replace and keep.
- **Release checks,** a fresh independent Codex review, `sync-docs`, a new
  candidate, and Fred's re-test.
