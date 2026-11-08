# Plate-solve fixes and solve UI — implementation plan

> **For agentic workers:** Codex implements one phase at a time under
> `docs/agent-collaboration.md` §4. Claude reviews, re-runs checks and stages.
> Steps use checkbox syntax.

**Goal:** make both solvers solve stretched or cropped images, give the user
an honest record of what was tried, and replace the solve dialog with one
inline panel beside the image, in v0.43.0.

**Architecture:**
- The built-in solver verifies with one saturation-inclusive population and
  reports structured attempts.
- ASTAP becomes a step chain (near, then the whole sky) under one deadline.
- Each solve is an operation with an ID that owns cancel and progress.
- The frontend's `PlateSolvePanel`, with its hint model and operation hook,
  serves both the project tab and the Image Analyzer.

**Tech stack:** Python 3.14 / FastAPI / Pydantic / aiosqlite; React /
TypeScript / MUI / TanStack Query.

**Spec:** [2026-10-30-plate-solve-ux-design.md](../specs/2026-10-30-plate-solve-ux-design.md),
an addendum to [2026-10-28-native-plate-solver-design.md](../specs/2026-10-28-native-plate-solver-design.md).
**Base:** branch `v0.43.0/native-plate-solver`, HEAD `923db06`, staged tree
`c969a35` (the previous candidate). The approved mockup is
`.superpowers/mockups/v0.43.0/plate-solve-redesign.html` (local).

## Global constraints

- **Acceptance thresholds unchanged:** `log_odds_threshold = ln(1e18)`;
  three quadrants; 12 matches and 0.2° (index); 10 matches and 3°
  (catalog-only); the ambiguity rules. Never loosened without Fred.
- **Budgets:** built-in 20/10/30 s and 60 s overall, unchanged; ASTAP 180 s
  overall, including preparation.
- **No automatic native→ASTAP retry.** ASTAP's own near→whole-sky chain is
  automatic (Fred, 2026-10-30).
- **One solve slot,** check-and-acquire with no `await` in between. Workers
  keep the slot until they actually stop.
- **No new dependencies. No migration.** Never edit 0065.
- Services don't import `api/` or FastAPI. Read `app_config.APP_DIR` at call
  time. Outbound HTTP is not involved.
- **UI rules:**
  - MUI `sx` and theme tokens;
  - blue/orange/teal for meaning, always with an icon or text;
  - no question-mark icons;
  - tablet-safe touch targets;
  - plain copy exactly as in spec §7–8.
- **Test data:** in-memory synthetic only. Real images stay local.
- **Codex never stages, commits or pushes.** Fred's `make dev` (port 8000,
  `--reload`) and Vite run from this checkout. Edits reload his server, which
  Claude tells him before each phase.
- **Every phase leaves the running app working.**
  - A2 updates the dispatcher in the same task.
  - B1 keeps the old body-less `POST /plate-solve/cancel` and the old
    `{message}` progress as deprecated adapters until C5 removes them.
  - The comparative corpus gate for ASTAP waits for B3.

## Review focus

Each item names the condition, what the user expects, and the task that
pins it with a test.

1. **A file with several images, or HDU > 0.** The preview, the built-in
   solve and ASTAP all use the chosen extension (B2, B5).
2. **Archive and `.pxiproject` virtual paths.** The preview and both solvers
   work through `path_resolver`, or fail with a clear message, never a 500
   (B2, B5).
3. **Two solves at once** (Analyzer and project tab). The second gets 409,
   and cancelling either touches only its own operation (B1).
4. **A header with only `XPIXSZ` and `XBINNING` > 1, or only `YPIXSZ`.** The
   panel's displayed scale equals the backend's (A3, C1).
5. **A missing ASTAP star database or binary.** The typed `error` stops the
   chain with ASTAP's own message, and the image and hints stay (B3, C2).

---

## Phase A — built-in solver

### Task A1: saturation-inclusive extraction policy

**Files:**
- `backend/src/nightcrate/services/native_solver/extract.py`;
- `solve_image.py`;
- `near_catalog.py` (caller);
- tests in `backend/tests/native_solver/test_extract.py` and a new
  `test_rendered_trials.py`.

**Interfaces:**
- `ExtractionConfig.saturation: Literal["exclude", "include"] = "include"`.
- `extract_for_index(...) -> tuple[DetectedStars, DetectedStars]` keeps its
  signature. Under `include`, both elements are the same population.
- `extract_near` uses the same policy.
- Remove the `mono * (0.9 / peak)` rescale.

- [ ] **Write failing tests:**
  - `test_clipped_bright_stars_are_kept_for_verification`: render a
    star field from a seeded catalog with a TAN WCS, PSF σ 1.5 px, then
    stretch and clip it so the 30 brightest stars have flat tops at 1.0.
    `extract_for_index` must return those 30 among the first set.
  - `test_stretched_clipped_field_solves`: the same image through
    `solve_image` with a monkeypatched star source and index built from
    the same synthetic catalog. It is solved, with the centre within 2″ of
    truth.
- [ ] Run them; they fail on the current code.
- [ ] Implement the policy.
- [ ] **Rendered trials** in `test_rendered_trials.py`, through extraction
  and both verification profiles:
  - **Negative cases**, each `solved is False`:
    - random dots;
    - a nebula-only image with blobs;
    - a *displaced catalog*: real star positions near the hint with
      shuffled brightness and 20–60 px random offsets;
    - a clipped decoy.
  - Each negative must reach full verification (`rejection_counts
    ["full_verified"] > 0`), so it can't pass by finding too few stars.
    Pure noise is kept separately as the too-few-stars case.
  - **Positive controls** from the same renderer: the true field, its
    mirrored version (both parities are valid), and the clipped version.
    All solve within 2″ of truth.
  - **Recovery floor:** at least 9 of 10 seeded true fields solve.
- [ ] Add the same recovery floor to `test_real_sky_trials.py`, which today
  asserts only zero wrong.
- [ ] Run `uv run pytest tests/native_solver -q`: all pass.

### Task A2: attempts and structured progress

**Files:**
- `native_solver/models.py` or `services/plate_solve_models.py` (the shared
  `SolveAttempt`);
- `solve_image.py`;
- tests in `test_solve_image.py`.

**Interfaces** (the solver reports to a `SolveReporter`, which Phase B
stores in the operation):

```python
SolveStep = Literal["load", "near_index", "near_catalog", "blind_known_scale",
                    "blind_unknown_scale", "astap_near", "astap_blind"]
AttemptOutcome = Literal["solved", "no_match", "skipped", "step_timeout",
                         "overall_timeout", "cancelled", "ambiguous",
                         "too_few_stars", "error"]
class SolveAttempt(BaseModel):
    solver: Literal["native", "astap"]
    step: SolveStep
    position_source: Literal["request", "header", "none"]
    scale_source: Literal["request", "header", "none"]
    ranges: list[str] = []
    layers: list[str] = []
    outcome: AttemptOutcome | None = None   # None while active
    seconds: float | None = None
    detail: str | None = None               # e.g. "250 stars found"
class SolveReporter(Protocol):
    def start(self, attempt: SolveAttempt) -> None: ...
    def finish(self, outcome: AttemptOutcome, *, detail: str | None = None) -> None: ...
```

- `solve_image(..., reporter: SolveReporter)` replaces `progress`. In the
  same task, `run_solve` passes an adapter that turns reporter events into
  the existing progress text, so the app keeps working until B1. Every step
  that runs, or is skipped for a stated reason, appears once, in order.
  `PlateSolveResult.attempts: list[SolveAttempt]`.
- `SolveReporter.plan(steps: list[SolveStep])` announces the steps still to
  come, from the decision tree in `solve_image.py:282-345`, and is updated
  as steps finish.
- `ranges` and `layers` are recorded **inside** `search_index`/`solve_blind`
  as each band is actually searched (`index_search.py:335-360`), not from
  `built_ranges()`.

- [ ] **Tests:**
  - with a position and a scale, a miss records `near_index`,
    `blind_known_scale` and `blind_unknown_scale`, each `no_match`. Each
    attempt's `layers` equals the bands the search actually visited (with a
    known scale, a subset of the built layers, filtered by
    `1.5 ≤ field / diameter ≤ 12`);
  - the planned list shrinks as steps finish, and is empty after a solve;
  - with no position, `near_*` is absent;
  - a cancel mid-step records `cancelled` and stops;
  - with the field's range not built, the result is `field_not_built` and
    the attempt says which range was missing.
- [ ] Implement, then run `uv run pytest tests/native_solver tests/test_plate_solve.py -q`.

### Task A3: hints contract (built-in side)

**Files:** `native_solver/hints.py`, tests.
**Interface:** `hints_for(cards, *, image_height, ra_hint, dec_hint,
scale_hint_arcsec, fov_hint, ignore_position, ignore_scale) -> SolveHints`,
where `SolveHints` gains `position_source` and `scale_source`.
- Precedence: `scale_hint_arcsec` > `fov_hint` (legacy) > header (`YPIXSZ`
  ?? `XPIXSZ`, `FOCALLEN`).
- `ignore_*` forces `none`.
- [ ] Tests:
  - the precedence order;
  - Y-only headers;
  - X/Y differing (Y is used);
  - an ignore beats the header.

  Request-model validation is tested in B1.

### Task A4: benchmark honesty and corpus diagnosis (Claude runs; Codex edits the script)

- [ ] **`backend/scripts/plate_solve_benchmark.py`:**
  - a solved row with no reference gets `verified: false`, never counts
    toward "zero wrong", and gets a target-in-field check (the target's
    position inside the image rectangle via the solution's WCS);
  - the summary lists the unverified solves;
  - the ASTAP mode runs the new chain (after B3).
- [ ] **Claude:** a full corpus run, native and native-blind, after A1–A3.
  Zero wrong and no native regression. The comparative §11.2 bar against
  ASTAP is checked after B3, with ASTAP's new chain.
- [ ] **Claude:** synthetic false-match trials (the existing real-sky trial
  test plus the A1 rendered trials). Zero wrong.
- [ ] **Claude: a time-boxed diagnosis of the 10 failing finals.**
  - Truth comes from a blind ASTAP WCS (Heart Nebula) or from the project's
    solved stack.
  - Record the stage each fails at.
  - A fix goes back to Codex only with a clear cause, and must pass the
    corpus and the trials.

**Phase A gate:**
- targeted tests;
- the corpus bar;
- zero wrong in the trials;
- the original failing image solved by `solve_image` on the scratch star
  data.

---

## Phase B — backend contracts and ASTAP chain

### Task B1: operations, cancel and progress

**Files:**
- new `backend/src/nightcrate/services/solve_operations.py`;
- `services/plate_solve.py` (`run_solve`, `cancel_solve`, remove
  `_solve_progress` and `get_solve_progress`);
- `api/plate_solve.py`;
- `api/project_solve.py`;
- models;
- tests in a new `backend/tests/test_solve_operations.py` and the existing
  API tests.

**Interfaces:**
- `PlateSolveRequest` and `ProjectSolveRequest` gain:
  - `operation_id: UUID | None` (the server generates one if absent);
  - `scale_hint_arcsec: float | None` (gt=0, finite);
  - `position: Literal["auto", "none"] = "auto"`;
  - `scale: Literal["auto", "none"] = "auto"`.
- Validators:
  - `ra_hint` and `dec_hint` both or neither, finite, RA in [0, 360) and
    Dec in [−90, 90];
  - `position == "none"` with an RA/Dec → 422;
  - `scale == "none"` with a scale → 422;
  - `fov_hint` stays deprecated, finite and > 0.
  - `mode` is removed. Unknown fields are ignored, as Pydantic does by
    default.
- `solve_operations`:
  - `claim(operation_id, solver) -> SolveOperation` raises `SolveBusy` (409)
    if the slot is taken, or `SolveCancelled` if the ID is pending-cancelled;
  - `release(op)`;
  - `cancel(operation_id) -> CancelResult(cancelled: bool, pending: bool)`;
  - `snapshot(operation_id) -> ProgressSnapshot | None`;
  - pending cancels live in an `OrderedDict` capped at 64 entries, each kept
    for 600 s;
  - `SolveOperation` implements `SolveReporter`.
- `ProgressSnapshot(operation_id, solver, attempts, active_step,
  elapsed_seconds, state: Literal["running", "finished"])`.
- `POST /plate-solve/cancel` takes the body `{operation_id}`.
  `GET /plate-solve/progress?operation_id=` returns 200 with the snapshot,
  or 404 for an unknown ID.
- A finished operation's snapshot stays readable for 60 s, so the client
  reconciles. At most 16 finished snapshots are kept; the oldest goes first.
  The worker's task and thread references are dropped at finish.
- **Lifetime:**
  - The *endpoint* owns the operation, not `run_solve`. `POST /solve` and
    `POST /projects/{id}/solve` claim it, run the solver, and, for a
    project, render and save, and only then release it.
  - Cancel checkpoints sit before the solver, before rendering, and
    immediately before the INSERT or commit. A cancel after commit returns
    `cancelled: false` (the save stands).
  - A reused `operation_id` gives 409.
- **Locking:**
  - Reporter writes come from the worker thread and snapshot reads from the
    event loop, so they share a `threading.Lock`.
  - A per-project `asyncio.Lock` serializes publication by solve, replace
    and delete.
- **The slot stays shared.** `solve_slot()` and `solve_slot_wait()`, which
  star-data publication uses (`api/star_catalog.py:39`, `:220`, `:234`),
  keep their exclusion with solves.
- **Request validation moves here from A3:**
  - a non-finite or ≤ 0 scale or FOV → 422;
  - a lone RA or Dec → 422;
  - an RA/Dec out of range → 422.

- [ ] **Failing tests:**
  - `test_late_cancel_of_finished_operation_leaves_next_running`: A
    finishes, B starts, then A's cancel arrives. B solves, and the cancel
    returns `cancelled: false` (native and fake ASTAP);
  - `test_cancel_before_claim_stops_solve`: pause before the slot is
    claimed, cancel, resume. No solver runs, and the result is `cancelled`.
    For both endpoints;
  - `test_cancel_before_project_insert_saves_nothing`: pause after the solve
    returns and before the INSERT, cancel. No row is written and the
    response is `cancelled`;
  - `test_pending_cancels_are_bounded`: 65 IDs, the oldest drops; an ID
    older than 600 s expires;
  - `test_progress_snapshot_lists_attempts`;
  - `test_concurrent_solve_returns_409`;
  - `test_cancel_during_project_render_saves_nothing`;
  - `test_reused_operation_id_returns_409`;
  - `test_star_publication_still_waits_for_an_active_solve`;
  - `test_deprecated_cancel_and_progress_still_work` (removed in C5).
- [ ] Implement, keeping the existing worker ownership (`_astap_task`, the
  native task and shield loops) and the launch-window stop check.
- [ ] Run `uv run pytest tests/test_solve_operations.py tests/test_plate_solve.py tests/test_plate_solve_api.py tests/test_project_solve_api.py -q`.

### Task B2: scale contract on both endpoints, and the FITS extension

- `run_solve` receives `scale_hint_arcsec`, `ignore_position`,
  `ignore_scale` and `hdu`, and passes them to the native hints (A3) and to
  ASTAP (B3).
- For ASTAP, an HDU > 0 FITS is written to a temporary FITS through the
  existing `_write_temp_fits`, keeping the header pass-through.
- [ ] Tests:
  - an HDU 1 FITS reaches ASTAP as a temporary file containing that HDU's
    data;
  - an XISF's field uses the prepared file's height, not a stale `NAXIS2`.

### Task B3: ASTAP step chain

**Files:**
- `services/plate_solve.py`, with the chain extracted into a new
  `services/astap_chain.py` if `plate_solve.py` grows;
- tests in `test_plate_solve.py` with a fake ASTAP executable script that
  writes scripted `.ini` sidecars.

**Interface:** `run_astap_chain(binary, image_file, *, position, scale_arcsec,
image_height, deadline, stop, reporter) -> PlateSolveResult`.
- Steps:
  - `astap_near`: `-r 30 -ra -spd -fov <scale × height>`, only with a
    position. Its subprocess timeout is `min(60 s, remaining)`;
  - `astap_blind`: `-r 180 -fov <scale × height>`, or `-fov 0` with no
    scale. It gets all the remaining time.
- Outcome names: ASTAP's "no solution" is recorded as `no_match`, the
  shared attempt outcome.
- Advance on `no_solution` or `step_timeout` while time remains. Stop on
  `solved`, `too_few_stars`, `cancelled`, `error` and `overall_timeout`.
- Remove the old outcomes and message: the `-speed slow` retry (kept only if
  A4's corpus run shows a rescue) and "Try blind solve".
- Typed outcomes come from the exit code and the `.ini`:
  - 1 → `no_solution`;
  - 2 → `too_few_stars`;
  - 16 / 32 / 33 / 34 → `error` with ASTAP's text;
  - the subprocess timeout → `step_timeout`, or `overall_timeout` at the
    deadline.
- `_compute_results` gains `validate_wcs()`, applied before any
  `solved=True`, per spec §5.
- [ ] **Failing tests:**
  - a near miss goes to blind, which solves;
  - a near timeout goes to blind. This uses a fake ASTAP that really
    sleeps past the near cap, and an injected monotonic clock through the
    real timeout wrapper. Blind must start with at least 120 s, minus
    preparation, remaining;
  - a cancel between the steps stops it, and blind never starts;
  - exit 32 (no database) stops with an `error` outcome;
  - a stale `.ini` from step 1 isn't read by step 2;
  - `PLTSOLVD=T` without `CRPIX1` is not solved;
  - preparation consuming the deadline gives `overall_timeout` with no
    ASTAP run;
  - with no position, only `astap_blind` runs, with `-fov 0` when there is
    no scale.
- [ ] Implement and run the targeted tests.

### Task B4: project replace after success

**Files:** `api/project_solve.py`, `project_solve_models.py`, tests.
- `ProjectSolveRequest.replace: bool = False`.
- With an existing solve: `replace=False` → 409, as today. With `True`, and
  for every new solve, the images are an immutable generation per row, in
  `solve/<solve id>/` (spec §6):
  1. solve;
  2. render the variants into `solve/.staging-<operation id>/`;
  3. under the per-project lock, one transaction: re-check the cancel,
     delete the old `project_solve`, insert the new solve and its
     `project_dso` rows, `INSERT OR IGNORE` the best-guess
     `project_target`, and rename staging to `solve/<new id>/`;
  4. commit.
- **Failures:**
  - a failed rename rolls back;
  - a failed commit removes `solve/<new id>/`;
  - after commit, remove the old generation and any stray `.staging-*` or
    unreferenced generation folders on a best-effort basis.
- **A reused ID.** SQLite can hand out a rolled-back row ID again, so a
  crash between the rename and the commit can leave a folder with that
  number. Under the per-project lock and inside the transaction, before the
  rename: if `solve/<new id>/` exists, it can't belong to any committed row
  (the row is new in this transaction), so remove it first.
- **Image URLs** are versioned by solve ID (`?_v=<solve id>`), not
  `solved_at`, which has second precision (`projectSolve.ts:94-101`). Two
  replacements within one second must still show the new pixels.
- **HDU:** `ProjectSolveRequest.hdu` must be 0; anything else returns 422.
  If the primary HDU holds no image, the 422 says: "This file's image isn't
  in its primary extension. Open it in the Image Analyzer to solve it."
- `GET …/solve/image/{variant}` serves `solve/<current id>/<variant>.jpg`,
  falling back to the legacy `solve/<variant>.jpg`. Delete removes the
  whole `solve/` folder, as today.
- **Response models:**
  - the POST success response gains `attempts`, which are not persisted.
    "View solution details" uses the persisted `solve_path` and
    `scale_stage` after a reload;
  - the 422 detail for both solvers becomes `{message, failure_reason,
    attempts}`.
- [ ] **Tests:**
  - a replace success swaps the row and the images and keeps the mains;
  - a replace with a failed solve keeps the old row and images;
  - a replace with a render failure keeps the old;
  - a replace with a rename failure (monkeypatched) rolls back and keeps
    the old;
  - a replace with a commit failure (monkeypatched) keeps the old and
    leaves no served new folder;
  - an interrupted publication (exception after the rename and before the
    commit) keeps the old;
  - crash residue: a leftover `solve/<id>/` for an ID SQLite then reuses,
    followed by a **successful** replace, gives the new images;
  - two replaces with an identical `solved_at` give different image URLs;
  - `hdu=1` → 422; a primary HDU with no image → 422 with the message;
  - a legacy-layout solve is still served and replaced;
  - `replace=False` still gives 409;
  - an ASTAP 422 carries the attempts.

### Task B5: preview route

**Files:**
- `api/images.py`;
- `services/catalog_thumbnail.py`, or a new `services/image_preview.py`
  sharing its stretch;
- tests.

The reference route is removed in C5, together with the UI that calls it.

**Interface:** `GET /api/images/preview?path=&hdu=0&max_px=1600` →
`image/jpeg`.
- `max_px` is clamped to [256, 2400].
- `path_resolver` handles plain, archive and pxiproject paths.
- **Loaders** (new `services/image_preview.py`, reusing
  `catalog_thumbnail`'s STF stretch):
  - FITS opens with `memmap=True, do_not_scale_image_data=True` and samples
    the raw mapped array with a stride on the spatial axes only. For
    `(C, H, W)` that is `[:, ::s, ::s]`; for `(H, W)`, `[::s, ::s]`. It then
    applies BSCALE, BZERO and BLANK itself before converting to float32.
    Astropy refuses scaled data through a strict memory map;
  - PNG, JPEG and TIFF use PIL `draft`/`reduce`;
  - XISF, float TIFF and `.pxiproject` decode fully and then decimate.
- **Cache:** only the encoded JPEG bytes, in an LRU bounded at 32 MB.
- **Identity**, from `os.stat` before decoding. Every key includes `hdu` and
  `max_px`:
  - plain: `(realpath, st_size, st_mtime_ns)`;
  - archive: `(archive realpath, size, mtime_ns, member)`;
  - pxiproject: `(manifest realpath, size, mtime_ns, image index, backing
    file stat)`.
- **Caching headers:** `ETag` = a hash of the identity, with
  `Cache-Control: no-cache`; a matching `If-None-Match` gets 304.
- **Concurrency:** `Semaphore(1)` for full-decode formats and `Semaphore(2)`
  for strided and reduced ones. The permit is released when the worker
  thread finishes, not when the request is cancelled.
- **Errors:** a missing file → 404; unreadable → 422 with the message.

- [ ] **Tests:**
  - FITS HDU 0 and HDU 1 give distinguishable images, also for one FITS
    inside an archive (different keys and ETags);
  - unsigned 16-bit FITS (BZERO 32768), scaled FITS (BSCALE ≠ 1, with
    BLANK) and a 3-plane colour FITS all render with the right orientation
    and no error;
  - XISF;
  - PNG;
  - two members of one zip give different images and keys;
  - two images of one `.pxiproject` give different keys;
  - overwriting a source changes the ETag;
  - 304 on a matching ETag;
  - a missing file → 404;
  - a cache hit doesn't reload;
  - the longest side ≤ `max_px`;
  - the cache stays under its byte budget.
- [ ] **Claude** measures cold latency and peak RSS on a 26 MP FITS sub and
  a large XISF (target < 2 s cold for FITS), and records both.

**Phase B gate:**
- `uv run ruff check src/ tests/` and `ruff format --check`;
- `bandit -r src/`;
- the targeted pytest above.

---

## Phase C — frontend

### Task C1: API and pure hint model

**Files:**
- `frontend/src/api/plateSolve.ts`, `api/projectSolve.ts`;
- a new `frontend/src/components/plate-solve/hintModel.ts`.

**Changes:**
- New types: `SolveAttempt`, `ProgressSnapshot`, the request fields
  (`operation_id`, `scale_hint_arcsec`, `position`, `scale`, `replace`).
- `cancelSolve(operationId)`, `fetchSolveProgress(operationId)`,
  `previewUrl(path, hdu, maxPx)`.
- Remove `validateReferenceImage` and `mode`.

**`hintModel.ts`** (pure, no React):
- `headerHints(cards)` returns the position, a scale computed exactly as the
  backend does (Y ?? X pixel, `FOCALLEN`), and the physical pixel and
  binning for prefill (`YBINNING` ?? `XBINNING`);
- `scaleFrom({ kind: "rig" | "calc" | "enter", ... })`;
- `buildRequest(state)`: no scale while the scale is "header"; explicit
  `position`/`scale: "none"` for the searches without them.

No unit-test runner exists, so the backend tests cover the rule and Claude's
rendered checks assert the request payloads.

### Task C2: `PlateSolvePanel` and `useSolveOperation`

**Files:** new `components/plate-solve/PlateSolvePanel.tsx`,
`useSolveOperation.ts` and `SolveSteps.tsx`.

- **The panel** has the states summary / editor / solving / failure /
  setup-note. The copy and layout are exactly as in spec §7 and the mockup.
  Props:

  ```ts
  interface PlateSolvePanelProps {
    image: { path: string; hdu: number; cards: HeaderCard[] };
    scope: { surface: "project"; projectId: number } | { surface: "analyzer" };
    solve: (req: PlateSolveRequest) => Promise<SolveOutcome>; // adapter: project POST or /plate-solve/solve
    primaryLabel: string;
    replacing?: boolean;
    active: boolean;             // false when hidden or unmounting → cancel
    onSolved: (result: PlateSolveResult) => void;
    onStale: () => void;         // project: invalidate + refetch saved solve
    onChooseImage: () => void;
  }
  type SolveOutcome =
    | { kind: "solved"; result: PlateSolveResult }
    | { kind: "failed"; message: string; failureReason: string | null; attempts: SolveAttempt[] };
  ```

- `parseApiError` keeps `attempts` from the 422 detail.
- **The hook:**
  - a token per request, bound to `{path, hdu}`;
  - polls the progress by operation ID every 1 s;
  - cancels on unmount, on dismiss and on image change;
  - ignores stale responses and progress;
  - `solve(solverOverride?)` keeps the last chosen solver for the image.
- **The return-state snapshot:** `sessionStorage` keyed by
  `surface:project:path:hdu`, holding the applied hints and the solver. It
  is restored when the URL brings the image back.

### Task C3: project tab

**Files:**
- `components/projects/ProjectPlateSolveTab.tsx`;
- `pages/ProjectDetailPage.tsx` (`?tab=plate-solve&solve=&hdu=`, selecting
  the tab);
- a new `components/plate-solve/ImagePreview.tsx` (the preview with the
  optional `DsoAnnotationOverlay`).

**States, per spec §8:**
- the empty state, with the explanation text quoted in spec §8, word for
  word, plus its one-line version above "Objects in image";
- the chosen image (preview + panel);
- solved (overlay, "Solved and saved to project", "View solution details",
  "Objects in image" with "Main target" checkboxes, "Solve again", "Choose
  another image", the secondary "Remove saved solution");
- replacing ("Not saved yet", "Keep the saved solution", "Solve and replace
  saved solution").

A stale project response invalidates and refetches `["project-solve", id]`
and `["project-targets", id]`. The project tab uses HDU 0, as today; there
is no extension selector (spec §8).

### Task C4: Image Analyzer

**Files:** `components/analyzer/ImageAnalyzerView.tsx`, and
`PlateSolveDetailPanel.tsx` (reusing `AstrometricSolutionSection`).
- A "Plate solve" action on the Image and Identify tabs. The Identify
  sidebar shows "Sky position", with the panel when solving or solving
  again.
- After a solve: "Shown here only. The file isn't changed.", plus "Use the
  image-header solution" when one exists.
- **Fix the annotation precedence:** a solved WCS is always sent to
  `/annotate` and overrides the header (currently `:376`).
- The annotation query key fingerprints the **complete** WCS (CRVAL,
  CRPIX, all four CD elements and NAXIS), not the centre alone (`:366-375`).
- Leaving the route cancels the operation, because the Analyzer stays
  mounted when hidden (`AppShell.tsx:487`).

### Task C5: deep links and removal

- `StarCatalogAdminSection` gets `id="plate-solving-stars"`; `AdminPage`
  scrolls to `location.hash`. The setup links carry `?returnTo=<encoded app
  URL>`.
  - Admin and Settings show a "Back to plate solve" button while
    `returnTo` is present. It navigates to that URL, which restores the tab,
    the image and the session snapshot.
  - Only same-origin app paths are accepted.
- Delete `PlateSolveDialog.tsx`, including `SolveResults`, and its imports.
- Remove B1's deprecated cancel/progress adapters and their test.
- Remove `POST /plate-solve/validate-reference-image`
  (`api/plate_solve.py:39-70`), its frontend wrapper
  (`plateSolve.ts:100-113`) and `mode`, in the same task as the UI that used
  them.
- `npm run build` must be clean.

**Phase C gate:** `npm run build`. Then Claude's rendered checks, spec §10,
headless, with a temporary HOME, at 1280 and 820 px, through every mockup
state on both surfaces.
- The check script is kept as a record at
  `.superpowers/codex/v0.43.0/checks/plate-solve-ui.mjs`.
- It uses Playwright route interception to hold responses behind barriers,
  so stale-response and cancel ordering are executed and asserted, not
  inferred from screenshots.
- It asserts that "Cancel" discards unapplied editor changes.
- Claude also solves the original failing image through **both real
  endpoints** (`/plate-solve/solve` and the project POST), with both
  solvers, on that server.

The checks cover:
- request-payload assertions (a rig on a cropped image sends
  `scale_hint_arcsec`; manual entry sends it; untouched header sends none);
- the header prefill;
- the setup round trip;
- dismiss/reopen staleness;
- replace and keep;
- a side-by-side comparison with the mockup.

---

## After the phases

1. A fresh independent Codex review: high-stakes (scientific, subprocess,
   concurrency, API contracts, persistence, paths).
2. `sync-docs`:
   - `docs/development-decisions.md` "Plate solving" (the new rules: one
     detection population, the ASTAP chain, operations, replace, preview,
     the removed reference);
   - README.
3. The full release checks, including the full backend suite once.
4. A new candidate: PLAN.md set to "Candidate ready", the staged tree
   recorded.
5. Fred's re-test.

## Stop conditions (escalate to Fred)

- Any wrong solve in the corpus or the trials, or a need to touch a
  threshold.
- A need for a migration or a new dependency.
- The corpus bar regresses.
- The 10-finals diagnosis points to a change in the search design.
- Three review cycles on a phase without convergence.

## Codex review

- **Mode:** independent plan review. Converged in 3 of 5 rounds. Records:
  `.superpowers/codex/v0.43.0/` (local), `94–99`. The backend design (`78–87`)
  and the UI design (`88–92`) converged in separate discussions before this
  plan.
- **Adopted from the plan review:**
  - replacement publishes immutable image generations before the database
    commit, with tests for every failure boundary;
  - the shared contracts and compatibility adapters land first, so each
    phase leaves the app working, and the comparative ASTAP gate waits for
    the chain;
  - the operation lasts through the project render and commit, IDs can't be
    reused, and same-project publication is serialized;
  - the ranges and layers actually searched are recorded inside the loop,
    and the backend sends the planned steps for "Waiting";
  - ASTAP's near step is capped, so the whole-sky step keeps its time;
  - the preview cache identity covers archive members and project images,
    with ETag revalidation, an encoded-byte budget and held concurrency
    permits;
  - the panel's adapter, scope and stale-response props, and attempts
    carried through project responses and parsed errors;
  - an explicit `returnTo` round trip, and the complete WCS in the
    annotation fingerprint.
- **Implementation reviews.**
  - Claude reviewed each phase (records `100–143`), with rendered checks for
    Phase C.
  - A fresh independent Codex review of `c969a35 → 465875c` (record `145`)
    found no blockers, 7 major findings and 1 minor. All were verified and
    fixed (record `147`), with one Claude finding added:
    - post-commit cleanup could outlive the lock and delete a newer solve's
      folder;
    - ASTAP results carried no `failure_reason`;
    - stale "Searching" rows stayed on failure screens;
    - ASTAP preparation blocked the event loop;
    - `operation_id` wasn't required;
    - the project route accepted `mode`;
    - the project 422 shapes were mixed;
    - channel-last colour FITS previews were sampled on the wrong axes;
    - (Claude) the built-in `time_limit` was neither titled nor retryable.
- **Contract tightened after the old dialog was removed (Claude, within the
  plan):** Task B1 kept `operation_id` optional and ignored unknown fields
  only so the old dialog kept working. Once C5 removed that dialog, both
  solve endpoints require the ID and reject unknown fields such as `mode`.
- **PR review of #21 (2026-11-01).**
  - **Scope:** Claude's code-review agent read the changes made after the
    independent review (`465875c → 9428a6e`).
  - **Findings:** seven, none high, all verified by Claude:
    - an unfinished step shown as "Done";
    - "Try again" lost for errors without a reason;
    - contract tests that passed with the contract reverted;
    - missing failure titles;
    - a delete racing a replacement's render;
    - crash leftovers kept;
    - wrong error labels.
  - **Fred's decision:** fix all seven before merging.
  - **Fixed** in records `150–156`: one structured error shape with typed
    reasons on both endpoints, read and launch error types, open steps
    closed, titles and retry rules, and the folder rules.

### v0.43.0-D1 — Extension (HDU) support for project solves

- **Kind:** disagreement (plan review)
- **Claude:** project images are single-image stacks, and saved solves
  store no extension. Rendering a chosen extension needs durable selection
  metadata, which the plan's no-migration constraint rules out.
- **Codex:** "Add extension-aware rendering and durable source-selection
  metadata compatible with the no-migration constraint."
- **Fred's decision:** project solves use a file's first image (HDU 0) —
  "first picture is fine" (2026-10-30). The Image Analyzer keeps its
  extension choice.
- **Disposition:** HDU 0 only for project solves.
- **Implementation:** done. `ProjectSolveRequest.hdu` must be 0, and a FITS
  whose primary HDU has no image gets a 422 that points to the Image
  Analyzer.
- **Outcome:** pending — no project image with its picture outside the
  first extension has been solved yet. Next check: the first such file in a
  project, which should get the 422 pointing to the Image Analyzer.
- **Log:**
  - 2026-10-30 — decided and implemented.
  - 2026-11-01 — Fred accepted the candidate as feature complete; he raised
    no extension problem. Shipped in v0.43.0.
  - 2026-11-04 — v0.46.0 start sweep: no new evidence. Fred's active
    database has six project images and one FITS, whose picture is in
    the first HDU; the others are PNG, JPEG, XISF and PixInsight virtual
    paths. The 422 is covered by `test_project_solve_api.py`. Four
    releases have completed since the entry was created, so it goes to
    Fred to close as inconclusive or keep with an owner.
  - 2026-11-04 — **Closed as inconclusive** (Fred: "yes, close it as
    inconclusive"). No project file has put its picture outside the
    first HDU; the 422 path stays covered by its test.
