# v0.43.0 — native plate solver: implementation plan

> **For agentic workers:** this plan follows `docs/agent-collaboration.md`.
> Codex implements Tasks 1–10 one phase at a time in the main checkout on
> `v0.43.0/native-plate-solver`, and leaves the work unstaged. Claude reviews
> each phase, re-runs the checks, stages accepted work and owns Task 11.
> Nobody commits without Fred's authorization. Steps use checkbox (`- [ ]`)
> syntax.

**Goal:** NightCrate solves images itself, by default, in the Image Analyzer
and on a project's Plate Solve tab, from a one-time star download managed in
Admin. ASTAP stays available on request.

**Architecture:**
- **`services/star_catalog/`** owns the star data:
  - the Siril file reader;
  - the pinned download and import;
  - the star pattern index, its field ranges, the manifest of built ranges
    and the builder;
  - a cache of open memory-mapped files.
- **`services/native_solver/`** is the solver, ported from the prototype:
  extraction, geometry, verification, a search through the index (near a
  position or blind) and the catalogue-only search near a position.
  `solve_image` runs the prototype's measured modes in a fixed order.
- **`services/plate_solve.py`** dispatches between native and ASTAP under its
  single-solve semaphore. A native solve runs in a worker thread that owns
  the slot until it has actually stopped.
- **Index builds** run the prototype's whole-sky builder in one child process
  per layer, so their memory never sits in the server process.
- **Routes:** `api/star_catalog.py` serves the Admin section, and the two
  existing solve routes gain a `solver` choice and the new result fields.
  Migration 0065 adds the solve record's columns.
- **Frontend:** a new Admin section; the solve dialog's states A, C and D;
  the default-solver setting; and the new rows in the Image Analyzer sidebar
  and the project's saved solve.

**Tech stack:** Python 3.14, FastAPI, Pydantic, numpy, scipy, astropy,
astropy-healpix, sep, httpx, raw SQLite (`aiosqlite`), yoyo;
React/TypeScript/MUI/TanStack Query.

**Approval:** Fred approved this plan on 2026-10-28, after the Codex plan
review, and accepted the build memory shown in Admin (about 5.4 GB for the
0.2–0.4° range).

**Spec:**
[2026-10-28-native-plate-solver-design.md](../specs/2026-10-28-native-plate-solver-design.md),
approved by Fred on 2026-10-28. Claude's calls are listed in its §14; those
revised after the Codex plan review are marked there.

**Prototype (read-only reference):** a separate local repository that is
not published. Its `README.md` and `solver_proto/`
modules are what this plan ports. The phase 2c report is
`37-codex-p2c.md`. Nothing is copied from SASpro, astrometry.net, ASTAP,
tetra3 or twirl.

**Baseline:** `923db06` (main after PR #20). The checkout also holds
uncommitted edits that Codex never touches: `PLAN.md`, the spec,
`.claude/skills/start-version/SKILL.md`, and this plan.

## Global Constraints

- **No new dependency**, Python or npm. healpy is never used.
- **Migration:** `0065.project_solve_solver.sql` (Task 7). Never edit an
  existing migration.
- **Fred's database:** his `make dev` server is stopped and stays stopped
  until Task 11's migration gate. Any server running this branch before then
  uses a temporary `HOME` holding copies of his config and database. No test
  or command writes to his real app data folder.
- **Layering:**
  - `services/` never imports `api/` or FastAPI;
  - `api/` owns HTTP, the 409s and saving;
  - `services/native_solver` may import `services/star_catalog`, never the
    reverse.
- **`APP_DIR`** is read at call time through `app_config.APP_DIR`.
  `tests/test_app_dir_isolation.py` must keep passing.
- **No GPU.** Nothing under `services/native_solver` or
  `services/star_catalog` calls `core.compute.get_array_module` or
  `set_gpu_enabled`. `pixel_loader` imports `core.compute` indirectly but
  never calls it (its module docstring), and that stays true.
- **Pinned source** (`star_catalog/store.py`, exact):
  - Zenodo record 14692304, version `1.0.0`, DOI `10.5281/zenodo.14692304`;
    format specification DOI `10.5281/zenodo.14697486`.
  - URL
    `https://zenodo.org/records/14692304/files/siril_cat_healpix8_astro.dat.bz2?download=1`.
  - Compressed file `siril_cat_healpix8_astro.dat.bz2`, 1,142,276,749 bytes,
    SHA-256
    `846ad4b12c50865df0cb8c5b23453f22eec78bbe9969e17d669ae19eb49d421f`.
  - Uncompressed file `siril_cat_healpix8_astro.dat`, 1,521,132,640 bytes,
    SHA-256
    `2fa40c93fe115235d35c5050757f2ef60a326a6f3030f87be1598c016fcb2388`.
- **Star data layout:**
  - `star_root()` is `APP_DIR / "star_catalogs"`;
  - the catalog lives in `star_root() / "siril-astro-gaia-dr3-1.0.0"`, beside
    its `version.json`;
  - layers live in `star_root() / "indexes" / "<layer>.ncidx"`;
  - the manifest of built ranges is
    `star_root() / "indexes" / "ranges.json"`;
  - work in progress goes to `star_root() / ".staging"`.

  `version.json` is written last; its presence means installed. The manifest
  is written atomically (temporary file, then `os.replace`).
- **Star epoch** `STAR_EPOCH = 2026.0` for the index and for verification.
- **Acceptance settings, copied verbatim from the prototype's
  `solver_proto/models.py`:**
  - every search through the index uses `BlindSolverConfig`, at least 12
    matches and at most 0.2° axis non-orthogonality, code tolerance 0.010;
  - the catalogue-only search near a position uses `SolverConfig`, 10 matches
    and 3°;
  - both use `log_odds_threshold = ln(1e18)` and 3 quadrants.

  Not one value changes without Fred's decision.
- **A search that stops early is never solved.** If the deadline or cancel
  arrives after a first acceptance but before the ambiguity scan has
  finished, the outcome is `time_limit` or `cancelled`, with no WCS. The
  catalogue solver already does this (`solve.py:662`); the blind solver does
  not (`blind_solve.py:655`), and the port fixes it.
- **Solve order: the prototype's measured modes only** (spec §5.1):
  - **With a position and a scale:**
    1. **Near:** search the index near the position with that scale, if the
       field's range is built (prototype `native-header-index`). Otherwise
       use the catalogue-only search near the position, with its own scale
       stages (prototype `native-header`).
    2. **Blind,** if near didn't solve: scale-known (prototype
       `native-blind-scale`), then unknown scale (prototype `native-blind`).
  - **With a position but no scale:**
    1. **Blind,** unknown scale.
    2. **The catalogue-only search near the position** (prototype
       `native-target`), if blind didn't solve or couldn't run.

    The catalogue step doesn't depend on which layers are installed, so
    installing an unrelated range never stops an image that used to solve.
  - **With no position:** blind only, scale-known first when a scale is
    given.
  - Blind steps run only when at least one layer is built. An `ambiguous` or
    `cancelled` result stops the sequence.
- **Extraction per step.** Each step extracts from the already-loaded array
  with its own profile and scale argument: near profile for the catalogue
  step; index profile otherwise.
  - Unknown-scale steps pass no scale, which changes the binning, as the
    prototype's `native-blind` did (`benchmark.py:282`, `extract.py:49`).
  - Results are cached per (profile, scale).
- **Time budgets** (each step gets the smaller of its own budget and the
  time left overall):
  - near or catalogue step: 20 s (the prototype's `max_solve_seconds`);
  - blind scale-known: 10 s (its measured P95 was 3.1 s);
  - blind unknown scale: 30 s (the prototype's blind budget);
  - the whole solve, including loading: 60 s.

  A step that runs out hands over to the next.
- **Unsolved outcomes,** when no step solved. `ambiguous` and `cancelled` have
  already stopped the sequence. Otherwise, the first rule that applies wins:
  1. `field_not_built`, when the field is known and its range isn't built;
  2. `time_limit`, when any search that ran was cut short by its own budget
     or the overall one;
  3. `no_match`, when every search that ran finished its candidates.
- **Detection minimums:** 12 for an index search and 10 for the
  catalogue-only search. `too_few_stars` only when the image has fewer than
  the minimum of every step that could run.
- **Output convention:** rows counted from the top, exactly as
  `pixel_loader` returns them; 1-based `CRPIX` at the image centre
  `((w + 1) / 2, (h + 1) / 2)`; CD in degrees per pixel.
- **Rotation** comes from the existing rule for corrected solutions,
  `degrees(atan2(-CD1_2, CD2_2))`, unnormalized, through one shared helper
  (Task 6). The prototype's `TanWCS.rotation_deg` is not used.
- **Concurrency:**
  - one solve at a time;
  - one star-data operation at a time (download, import, build or remove),
    claimed before its route returns;
  - **publication** of a catalog or layer (rename, `version.json`, manifest)
    and every deletion first calls `handles.close_all()`. Each holds the
    solve slot while it runs:
    - publication waits for a running solve to finish;
    - remove routes answer 409 immediately while a solve runs;
  - a build may start while a solve runs; only its publication waits. A
    solve requested during a publication gets the existing "already in
    progress" 409;
  - download and import run only when the stars are not installed;
  - **ownership ends only when work has stopped:**
    - neither the solve slot nor the star-data operation is released until
      its thread or child process has actually finished;
    - on shutdown, both are signalled and awaited for up to 10 s;
    - mapped files are closed only if no worker is still running. Otherwise
      they are left for process exit, never closed under a live reader;
  - **build temporary files:** each build gets a parent-owned folder,
    `.staging/build-<layer>-<uuid>/`, and every temporary file the child
    makes goes inside it.
    - After joining the child on error or cancel, the parent deletes the
      whole folder.
    - On success, the output survives until it is published, and the folder
      is deleted after publication (or after a failed publication);
  - **build disk check:** free space of at least 3.0 × the layer's estimate.
    The unchanged builder holds its selected stars, raw partitions, sorted
    spool and output at once, about 3.8 GB for `q004`; Task 11 measures the
    real peak;
  - **removal ownership:** a layer is kept while any remaining manifest
    entry lists it, ready or not.
- **Log prefixes:** `[star_catalog]` and `[plate_solve]`. Router 500 handlers
  use `logger.exception`.
- **Sources read.** Codex lists, in each task report, every file it read
  outside this repository and the prototype, for the credits log (spec §8).
  No code is copied from another solver.
- **Field ranges (ids and layers, exact):**

  | Range id | Field width | Layers | Estimated bytes |
  |---|---|---|---:|
  | `0.2-0.4` | 0.2° to < 0.4° | `q004` | 1,387,419,120 |
  | `0.4-0.8` | 0.4° to < 0.8° | `q008` | 383,025,280 |
  | `0.8-1.6` | 0.8° to < 1.6° | `q016` | 106,247,728 |
  | `1.6-3.2` | 1.6° to < 3.2° | `q032` | 28,957,176 |
  | `3.2-6.4` | 3.2° to < 6.4° | `q064` | 7,757,912 |
  | `6.4-10` | 6.4° to ≤ 10° | `q128`, `q256` | 3,139,584 |

  - Layer parameters are the prototype's `BandSpec` table (`q004-v5` …
    `q256-v5`), renamed without `-v5`.
  - Task 11 may add a neighbouring layer to a range (spec §4.4). The table
    and the manifest make that a data change.
  - **One file per layer, not per range** (this refines spec §4.1). A range
    is built when it is in the manifest and every one of its layers is
    `ready`.
- **Build memory per layer,** shown in Admin when above 2 GB:
  - `q004`: 5.4 GB;
  - `q008`: 3.2 GB.

  These are the prototype's peak RSS; Task 11 replaces them with measured
  product figures.
- **User-facing text, exact:**
  - **failure messages** (in `native_solver/messages.py`):
    - `stars_not_installed`: "The built-in solver needs the plate-solving
      stars, a one-time 1.14 GB download."
    - `no_ranges`: "No field ranges are built yet. Build one in Admin →
      Plate-solving stars."
    - `too_few_stars`: "Only {n} stars were detected; at least {m} are
      needed. Check focus, clouds or the exposure."
    - `no_match`: "No match found. {n} stars were detected, but none of the
      built field ranges matched them."
    - `field_not_built`: "This image's field ({field:.2f}°) is in the
      {range} range, which isn't built. Build it in Admin → Plate-solving
      stars to blind solve it."
    - `ambiguous`: "Two different solutions fit this image, so neither is
      used."
    - `time_limit`: "The search ran out of time before finding a
      solution."
    - `cancelled`: "Solve cancelled."
  - **409s:**
    - "Another star-data task is running."
    - "A plate solve is running. Try again when it finishes."
    - the existing "A plate solve is already in progress."
  - **422s:**
    - "The plate-solving stars are already installed. Remove them first to
      download or import again."
  - **Admin build-memory note:** "Building needs about {n} GB of memory."

## Review Focus

1. **A memory-mapped file deleted or replaced while mapped,** in the server or
   in a build. Windows refuses, and a mapped file that changes under a reader
   corrupts reads.
   - Every publication and deletion closes the cache first, under the solve
     slot.
   - The builder closes its own temporary mappings before removing its
     temporary folder, on success and on error.

   Tasks 2 and 3 test the order, actual closure, and reopening after a
   replacement.
2. **A partial or foreign file mistaken for the catalog or a layer.**
   - The catalog counts only if `version.json` exists and the size matches.
   - A layer whose header names another catalog checksum or format version
     is `stale` and never used.
   - A range counts only if it is in the manifest.

   Tasks 2 and 3 test all three.
3. **A resumed download in an unusual state:**
   - the server ignores Range;
   - the partial file is already complete;
   - a `206` arrives with the wrong `Content-Range`;
   - the body is short;
   - the disk fills up;
   - an interruption comes during verification or unpacking.

   Task 2 tests each.
4. **A header with a wrong scale or position.**
   - Binned masters carry the unbinned scale, and the blind unknown-scale
     step must recover them.
   - A position more than 2.0° off must fall back to a blind solve.

   Neither may loosen acceptance. Tasks 5 and 6 test both.
5. **A solve cancelled, timed out or abandoned mid-candidate.**
   - The worker must stop within one candidate check.
   - The slot is released only after it has stopped.
   - No row is saved.
   - Shutdown waits for it.

   Tasks 6 and 7 test cancel, request cancellation, timeout, shutdown and the
   saved state.

---

## Phase A: star data (backend, high-stakes)

High-stakes because of external data and its terms, outbound HTTP, writes to
the app data folder and concurrency.

### Task 1: The Siril catalog reader

**Files:**
- Create `backend/src/nightcrate/services/star_catalog/__init__.py`,
  `models.py` and `siril.py`.
- Test `backend/tests/star_catalog/__init__.py`, `conftest.py` and
  `test_siril.py`.

**Interfaces:**
- Produces:
  - `models.StarCatalog(ra: NDArray[float64], dec: NDArray[float64], g: NDArray[float32])`,
    a frozen dataclass with `__len__` and `take(indices)`. It is moved from
    the prototype's `models.py`.
  - `models.STAR_EPOCH = 2026.0`.
  - `siril.SirilCatalog(path: Path)`, a context manager with:
    - `header: SirilHeader`;
    - `query_cone(ra_deg: float, dec_deg: float, radius_deg: float, *, epoch: float = STAR_EPOCH) -> StarCatalog`;
    - `close() -> None` and `closed: bool`.
  - `siril.SirilFormatError(ValueError)`, raised for a bad header.
  - `siril.ChecksumMismatch(ValueError)`.
  - `siril.decompress_and_verify(compressed: Path, output: Path, *, compressed_sha256: str, uncompressed_sha256: str, cancel: threading.Event | None = None, on_bytes: Callable[[int], None] | None = None) -> Path`.
    It writes `output` only after both checksums pass, and otherwise raises
    `ChecksumMismatch`, leaving no output. It never deletes `compressed`.
  - Test fixture `write_siril_catalog(path: Path, stars: list[SyntheticStar]) -> Path`
    in `tests/star_catalog/conftest.py`. It writes a valid level-8 Siril file
    following the reader's format. `SyntheticStar` holds ra and dec (deg,
    J2016.0), pmra and pmdec (mas/yr) and G.

- [ ] **Step 1: Write the failing tests** in `test_siril.py`:
  - `test_header_rejects_bad_magic` and `test_header_rejects_truncated_file`
    raise `SirilFormatError`.
  - `test_cone_returns_only_stars_inside`: 5 stars at 0.5°, 0.9°, 1.1°, 2° and
    10° from (180, 0), queried at radius 1.0°, return exactly the first two.
  - `test_cone_spans_cell_boundaries`: stars on both sides of a level-8 cell
    edge are both returned.
  - `test_epoch_propagation`: a star at (0, 0) with pmra 1000 mas/yr and
    pmdec 0, queried at epoch 2026.0, has
    `ra == pytest.approx(10 / 3600, abs=1e-8)`.
  - `test_decompress_and_verify_ok`, plus
    `test_decompress_and_verify_mismatch_leaves_no_output`, which also checks
    that the compressed file is untouched.
  - `test_close_releases_mapping`: after `close()`, `closed` is true and the
    file can be renamed over (`os.replace` of another file onto it succeeds).
- [ ] **Step 2:** `uv run pytest tests/star_catalog/test_siril.py -v`. Expected:
  fail on import.
- [ ] **Step 3: Port** the prototype's `siril_catalog.py` into `siril.py`. It
  takes the checksums as arguments, not checksum files, and adds
  `cancel`/`on_bytes`. The ESA fetcher in `catalog.py` is not ported.
- [ ] **Step 4:** run Step 2's command. Expected: PASS. Then `uv run ruff check`
  and `uv run ruff format --check` on the new files.

### Task 2: The star store: download, import, status and removal

**Files:**
- Create `services/star_catalog/store.py` (layout, pinned source,
  `version.json`, installed state), `services/star_catalog/handles.py` and
  `services/star_catalog/fetch.py` (operation state, download, import).
- Modify `services/http_client.py` (add `stream_to_file`).
- Test `tests/star_catalog/test_store.py`, `test_handles.py`,
  `test_fetch.py` and `tests/test_http_client.py` (create the file if it is
  missing).

**Interfaces:**
- Consumes `siril.SirilCatalog` and `siril.decompress_and_verify` (Task 1).
- Produces:
  - **From `store`:**
    - `SIRIL_SOURCE`, a frozen dataclass of the pinned constants above, plus
      licence `"CC BY 4.0"`, Gaia licence `"CC BY-NC 3.0 IGO"` and the
      attribution text in spec §8;
    - `star_root() -> Path`, `catalog_dir() -> Path` and
      `catalog_path() -> Path`;
    - `installed() -> InstalledCatalog | None`. It is `None` unless
      `version.json` parses and the `.dat` size equals the pinned size.
      `InstalledCatalog` has `version`, `size_bytes`, `installed_at`,
      `source: Literal["download", "import"]` and `uncompressed_sha256`;
    - `required_free_bytes(already_downloaded: int) -> int`, the remaining
      compressed bytes plus the uncompressed size plus 100 MiB;
    - `InsufficientSpace(needed: int, free: int)`;
    - `AlreadyInstalled`.
  - **From `handles`:** `get_catalog() -> SirilCatalog`,
    `get_layers(names: Iterable[str]) -> list[IndexLayer]` (Task 3 supplies
    `IndexLayer`) and `close_all() -> None`. They are guarded by one
    `threading.Lock`, open lazily, and stay cached until `close_all`.
  - **From `fetch`:**
    - `StarOperation`, a Pydantic model:
      - `kind: Literal["download", "import", "build", "remove"]`;
      - `state: Literal["running", "done", "failed", "cancelled"]`;
      - `phase: Literal["downloading", "verifying", "unpacking", "copying", "building", "publishing", "removing"]`;
      - `bytes_done: int`, `bytes_total: int`;
      - `speed_bytes_per_s: float | None`, over a rolling 10 s window;
      - `ranges: list[str]`, `progress: float | None` and `message: str | None`.
    - `current_operation() -> StarOperation | None`.
    - `start_download() -> StarOperation` and
      `start_import(path: Path) -> StarOperation` raise
      `StarOperationBusy` or `AlreadyInstalled`. The operation is claimed
      synchronously before they return.
    - `cancel_operation() -> bool`.
    - `shutdown() -> Awaitable[None]`, called from the lifespan after
      `yield`. It cancels the running operation and awaits its thread or
      child for up to 10 s, under the ownership rule in Global Constraints.
    - The publish step takes a `publish_lock: Callable[[], AsyncContextManager[None]]`.
      Task 4 passes `plate_solve.solve_slot_wait`, so `fetch` never imports
      `plate_solve`.

    The operation runs as one app-owned `asyncio` task holding a module-level
    reference, like `sky_tile_cache`'s in-flight fetches. Blocking work
    (hashing, bz2, copying) runs through `asyncio.to_thread`.
  - **From `http_client`:**
    `stream_to_file(url: str, dest: Path, *, expected_size: int, on_bytes: Callable[[int], None], cancel: asyncio.Event, label: str) -> None`.
    - If `dest` already has `expected_size` bytes, it returns without a
      request.
    - Otherwise it requests from `dest`'s current size with
      `Range: bytes=<size>-`.
      - A `206` must carry `Content-Range: bytes <size>-<expected_size - 1>/<expected_size>`.
        Anything else is a malformed-range error: the partial file is kept
        and the request is not retried.
      - On `200` it truncates and restarts from zero.
    - It never writes beyond `expected_size`. A `dest` larger than that is
      deleted, raising `ValueError`.
    - A body that ends early raises `ShortTransfer` and keeps the bytes
      written. One retry for a transient failure resumes from the new size.
    - It logs like `get`.
  - **Download sequence:**
    1. The disk check.
    2. Stream to `.staging/<compressed name>.part`.
    3. Rename to `.staging/<compressed name>` and verify its checksum. A
       mismatch deletes it.
    4. Unpack and verify into `.staging/<uncompressed name>`. An unpack
       failure keeps the verified compressed file for the next attempt.
    5. Under the publish lock, `handles.close_all()`, rename into
       `catalog_dir()`, then write `version.json`.
    6. Delete the compressed file.

    On a restart, a verified compressed file in `.staging` skips straight to
    step 4.

- [ ] **Step 1: Write the failing tests.** HTTP uses `httpx.MockTransport`;
  nothing touches the network or the real app data folder.
  - `test_stream_resumes_with_range`: an attempt interrupted after 1,000 bytes
    leaves a 1,000-byte `.part`. The next call sends `Range: bytes=1000-`, and
    the file equals the full body.
  - `test_stream_restarts_when_range_ignored`: the server answers `200`, and
    the result is the body exactly, not 1,000 + body.
  - `test_stream_complete_part_makes_no_request`: the mock fails the test if
    called.
  - `test_stream_wrong_content_range_rejected`: a wrong start or a wrong
    total keeps the partial file unchanged.
  - `test_stream_short_body_then_retry_resumes`: the retry's `Range` uses the
    new size.
  - `test_stream_never_exceeds_expected_size`, with a server sending extra
    bytes.
  - `test_stream_oversized_part_deleted`.
  - `test_stream_disk_full_keeps_partial`: an `OSError(ENOSPC)` on write
    leaves the operation failed with the partial file intact.
  - `test_download_installs_atomically`: with a small fake source (pinned
    constants monkeypatched to the fake's sizes and checksums), the end state
    is the `.dat` and `version.json`, with no compressed file and an empty
    `.staging`. A spy confirms the order: `close_all`, rename, then
    `version.json`.
  - `test_download_checksum_mismatch`: the operation fails with "The
    downloaded file didn't match its published checksum. Download it again.",
    nothing is installed, and the compressed file is deleted.
  - `test_unpack_failure_keeps_verified_compressed`, and
    `test_restart_after_verified_compressed_skips_download`.
  - `test_download_insufficient_space` (`shutil.disk_usage` monkeypatched):
    `InsufficientSpace` names the needed bytes.
  - `test_download_cancel_keeps_part_for_resume`.
  - `test_download_refused_when_installed`: `AlreadyInstalled`.
  - `test_import_bz2_and_dat`: both install; the source file's size and
    mtime are unchanged.
  - `test_import_wrong_file`: fails with "This file isn't the Siril Gaia DR3
    astrometry catalogue, version 1.0.0."
  - `test_busy`: a second start raises `StarOperationBusy`.
  - `test_shutdown_waits_for_operation`: with a blocked copy thread, the
    operation stays claimed until the thread returns.
  - `test_installed_requires_version_json_and_size`.
  - `test_handles_close_all_closes_and_reopens`: after `close_all`, every
    previously returned object reports `closed`, and the next `get_catalog`
    returns a new open one.
  - `test_star_root_follows_app_dir_redirect`.
- [ ] **Step 2:** `uv run pytest tests/star_catalog tests/test_http_client.py -v`.
  Expected: fail.
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4:** run Step 2's command. Expected: PASS. Then
  `uv run pytest tests/test_app_dir_isolation.py -v`. Expected: PASS.

### Task 3: The index: format, field ranges, building and removal

**Files:**
- Create the following under `services/star_catalog/`:
  - `ranges.py`: layer specs, `FIELD_RANGES`, the manifest, and coverage
    helpers;
  - `index.py`: the `.ncidx` format and the `IndexLayer` reader;
  - `index_build.py`: the builder and its child process.
- Modify `fetch.py` (build and remove operations).
- Test `tests/star_catalog/test_ranges.py`, `test_index.py` and
  `test_index_build.py`.

**Interfaces:**
- Consumes `SirilCatalog`, `store.star_root()`, `handles` and
  `fetch.StarOperation`.
- Produces:
  - **From `ranges`:**
    - `LayerSpec`, the prototype's `BandSpec`;
    - `LAYERS: dict[str, LayerSpec]`;
    - `FieldRange(id: str, min_deg: float, max_deg: float, layers: tuple[str, ...], estimated_bytes: int, build_memory_bytes: int)`;
    - `FIELD_RANGES: tuple[FieldRange, ...]`;
    - `range_for_field(field_deg: float) -> FieldRange | None`;
    - `layer_path(name: str) -> Path`;
    - `read_manifest() -> set[str]` and `write_manifest(ids: set[str]) -> None`
      (atomic);
    - `built_ranges() -> set[str]`: manifest ids whose layers are all
      `ready`;
    - `built_layers() -> list[str]`, the union of the built ranges' layers.
  - **From `index`:**
    - `INDEX_FORMAT = "nightcrate-star-index"`, `INDEX_FORMAT_VERSION = 1`;
    - `IndexLayer(path: Path)`, the prototype's `IndexBand`, with
      `query_codes`, `query_stars`, `baseline_radec`, `quad_radec`, `close`
      and `closed`;
    - `layer_state(name: str) -> Literal["missing", "ready", "stale"]`.
      `stale` means the header's `source.uncompressed_sha256` differs from
      the pinned value, or the format or version differs.
  - **From `index_build`:**
    `build_layer(name: str, *, threads: int, cancel: threading.Event, on_progress: Callable[[float], None]) -> Path`.
    - It runs the prototype's whole-sky `build_siril_band` unchanged in
      behavior, in one child process (the `multiprocessing` spawn context),
      with cKDTree's `workers=threads`.
    - It creates the build folder `.staging/build-<layer>-<uuid>/`. The
      child writes every temporary file and the output inside it (the
      prototype's `tempfile` calls get `dir=` that folder).
    - It returns the staged output path.
    - Cancel terminates the child. The child is joined in `finally`, and the
      parent then deletes the whole build folder on cancel or error, or
      everything except the output on success.
    - Inside the child, the selected-star and tile memmaps are closed
      explicitly before their temporary folder is removed, on success and on
      error.
    - `threads` comes from
      `compute.effective_worker_count(settings.max_worker_cores)`.
  - **From `fetch`:**
    - `start_build(range_ids: list[str]) -> StarOperation`. It builds the
      missing or stale layers of those ranges. Then, under the publish lock,
      it calls `close_all`, renames each layer into place, and adds the ids
      to the manifest.
      - Before each layer, there must be free space of at least 3.0 × its
        estimate; otherwise `InsufficientSpace`.
    - `start_remove(range_ids: list[str] | Literal["all"]) -> StarOperation`.
      - Under the solve slot (the caller already holds it), it removes the
        ids from the manifest first, then calls `close_all`.
      - It deletes the layers that no remaining manifest entry lists, ready
        or not, then any orphan layer file not referenced by the manifest.
        "all" also deletes the catalog.

- [ ] **Step 1: Write the failing tests:**
  - `test_range_for_field_boundaries`: 0.19 → None; 0.2 → `0.2-0.4`;
    0.3999 → `0.2-0.4`; 0.4 → `0.4-0.8`; 10.0 → `6.4-10`; 10.01 → None.
  - `test_layer_specs_match_prototype`: each layer's diameters, HEALPix
    level, stars per cell, quads per star and magnitude limit equal the
    prototype's table.
  - **`test_build_layer_matches_prototype_format`:** on a synthetic Siril
    catalog of about 20,000 stars covering the whole sky, `q256` builds. Its
    reader finds a quad planted from known stars, and its header records the
    pinned checksum, format version 1 and `STAR_EPOCH`.
  - `test_layer_state_stale_on_checksum_or_version`.
  - **`test_build_cancel_terminates_child_and_cleans_staging`:** cancel
    arrives while the child holds partition and spool files. Afterwards the
    child's `exitcode` is not None, and the whole build folder is gone.
  - `test_build_child_error_cleans_up`: a child that raises leaves no build
    folder and a failed operation with the message.
  - `test_build_disk_check`: free space below 3.0 × the estimate refuses with
    `InsufficientSpace`.
  - **`test_publish_closes_handles_and_reopens`:** with a layer open through
    `handles`, rebuilding it calls `close_all` before `os.replace`. The old
    object reports `closed`, and `get_layers` then opens the new file.
  - `test_manifest_atomic_and_restart`: a manifest written, then read back in
    a fresh module state, gives the same ids. A layer file present but not
    in the manifest is not reported built.
  - **`test_remove_with_shared_layers`,** with a temporary range table:
    - two ranges with identical layer sets: removing one leaves the other
      built, and both layer files remain;
    - a subset range: removing the smaller range reports it not built and
      keeps the shared layer;
    - removing the larger one deletes only its own layers;
    - range A owns `q004`, range B owns `q004` and `q008`, and `q008` is
      stale: removing A keeps `q004`, because B still lists it.
  - `test_remove_all_deletes_catalog_and_indexes`.
- [ ] **Step 2:** `uv run pytest tests/star_catalog -v`. Expected: the new tests
  fail.
- [ ] **Step 3: Implement.** Port the format, the reader and
  `build_siril_band` with `write_band` from the prototype's `blind_index.py`,
  keeping their selection, ranking, `k = 24` neighbour limits, partitioning
  and stable key sort unchanged. Version 3/4 reading and the `--region`
  option are not ported.
- [ ] **Step 4:** run Step 2's command. Expected: PASS.

### Task 4: Admin routes

**Files:**
- Create `api/star_catalog.py` and `api/star_catalog_models.py`.
- Modify `main.py` (include the router; add an OpenAPI tag "Star catalog").
- Test `tests/test_star_catalog_api.py`.

**Interfaces:**
- Consumes Tasks 1–3, and from Task 6 `plate_solve.solve_slot()` (immediate:
  raises `RuntimeError` with "A plate solve is running. Try again when it
  finishes." when taken) and `plate_solve.solve_slot_wait()` (waits). If
  Task 4 lands before Task 6, it adds these two helpers to `plate_solve.py`
  around the existing semaphore, and Task 6 keeps them.
- Produces routes under `/api/admin/star-catalog`:
  - `GET /status` returns `StarCatalogStatus`:
    - `installed: InstalledCatalog | None`;
    - `source`: version, download bytes, unpacked bytes, DOI, licence,
      Gaia licence and attribution;
    - `operation: StarOperation | None`;
    - `ranges: list[RangeStatus]`, where `RangeStatus` has:
      - `id`, `min_deg`, `max_deg`;
      - `state: Literal["not_built", "building", "built", "needs_rebuild"]`;
      - `size_bytes`, the actual size when built and the estimate otherwise,
        with `size_is_estimate: bool`;
      - `build_memory_bytes`;
      - `rigs: list[RigCoverage(id, name, field_deg)]`;
    - `total_bytes_used`, `free_bytes`.
  - `POST /download`, `POST /import` (`{path}`), `POST /cancel` and
    `POST /ranges/build` (`{range_ids}`) each return `StarOperation` (202).
    - 409 while another star-data operation runs.
    - 422 for `AlreadyInstalled`, `InsufficientSpace`, unknown range ids, or
      an import path that doesn't exist.
  - `DELETE /ranges/{range_id}` and `DELETE /` hold `solve_slot()` for the
    synchronous part of `start_remove`. They return `StarOperation`, or 409.

  `RigCoverage` comes from `rig_summary` rows that are not retired. Each
  rig's field is the larger of `services/rig_calculators.compute_fov`'s
  width and height. Rigs without focal length or sensor data are skipped.

- [ ] **Step 1: Write the failing tests:**
  - `test_status_not_installed`: every range is `not_built` with its
    estimate, and `0.2-0.4` carries its build memory.
  - `test_rig_coverage`: a rig with a 400 mm focal length, 3.76 µm pixels and
    a 6248 × 4176 sensor (field 3.36°) appears under `3.2-6.4` only.
  - `test_download_returns_operation_and_busy_409`.
  - `test_download_when_installed_422`, with the exact message.
  - `test_build_unknown_range_422`.
  - `test_build_allowed_while_solving_publication_waits`: with the solve
    slot held by the test, a build starts (202). Its layer is not published
    until the slot is released.
  - `test_delete_range_409_while_solving`.
  - `test_delete_all_reports_operation`.
- [ ] **Step 2:** `uv run pytest tests/test_star_catalog_api.py -v`. Expected:
  fail.
- [ ] **Step 3: Implement.** Follow `api/admin.py`'s catalog routes for style
  and error translation.
- [ ] **Step 4:** run Step 2's command and the whole `tests/star_catalog`.
  Expected: PASS. Then ruff, format and bandit on the touched files.

---

## Phase B: the solver (backend, high-stakes)

High-stakes because it produces a scientific result that changes overlays and
object search, and because of concurrency, API contracts and a migration.

### Task 5: Solver core

**Files:**
- Create the following under `services/native_solver/`:
  - `__init__.py`;
  - `models.py`: `DetectedStars`, `TanWCS`, `SolverConfig`,
    `BlindSolverConfig`, `SolveOutcome`;
  - `geometry.py`;
  - `extract.py`: array in, detections out;
  - `verify.py`: verification, the TAN fit and refinement;
  - `index_search.py`: from `blind_solve.py`;
  - `near_catalog.py`: from `solve.py`'s `solve_hinted`;
  - `messages.py`.
- Test `tests/native_solver/__init__.py`, `synthetic.py` (generator),
  `test_geometry.py`, `test_extract.py`, `test_index_search.py`,
  `test_near_catalog.py` and `test_safety.py`.

**Interfaces:**
- Consumes `StarCatalog`, `SirilCatalog`, `IndexLayer` and `STAR_EPOCH`.
- Produces:
  - **`extract_near`:**
    `extract_near(data: NDArray, *, bayer_mosaic: bool, pixel_scale_arcsec: float | None) -> DetectedStars`
    uses the prototype's hinted extraction settings.
  - **`extract_for_index`:**
    `extract_for_index(data: NDArray, *, bayer_mosaic: bool, pixel_scale_arcsec: float | None) -> tuple[DetectedStars, DetectedStars]`
    returns `(detections, quad_detections)` with the prototype's blind
    settings. The second set is saturation-inclusive, for forming patterns
    only.
  - **`search_index`:**
    `search_index(detections: DetectedStars, quad_detections: DetectedStars, layers: list[IndexLayer], catalog: SirilCatalog, *, pixel_scale_arcsec: float | None, near: tuple[float, float] | None, deadline: float, cancel: threading.Event) -> SolveOutcome`.
    - A given scale means one scale-known search; `None` means unknown. There
      are no 0.5× or 2× stages here.
    - `near` restricts candidates to 2.0° around (ra, dec).
    - It uses `BlindSolverConfig`.
  - **`search_near_catalog`:**
    `search_near_catalog(detections: DetectedStars, catalog: SirilCatalog, *, ra: float, dec: float, pixel_scale_arcsec: float | None, deadline: float, cancel: threading.Event) -> SolveOutcome`
    keeps the prototype's scale stages (header, 0.5×, 2×, unknown) and
    `SolverConfig`.
  - **`SolveOutcome`:**
    - `status: Literal["solved", "not_solved", "ambiguous", "time_limit", "cancelled"]`;
    - `reason: str`, a code from `messages`;
    - `wcs: TanWCS | None`;
    - `log_odds`, `matched_count`, `detected_count`, `rms_px`, `rms_arcsec`;
    - `scale_stage: str | None`;
    - `timings: dict[str, float]`.
  - `messages.MESSAGES: dict[str, str]` holds the exact strings in Global
    Constraints.
- **Test generator.** `tests/native_solver/synthetic.py` makes a sky field
  from a synthetic Siril catalog and a known `TanWCS`. Its noise is
  calibrated to the corpus: spurious-detection fluxes are drawn from the
  catalog stars' flux range, brightness scatter σ is 0.25 mag, and a given
  fraction of stars is dropped.

- [ ] **Step 1: Write the failing tests:**
  - **`test_index_search_blind_solves`:** a 1.0° × 0.67° field at 1.5″/px
    (2400 × 1600) centred on (83.82, −5.39), rotated 30°, in both parities,
    is solved. In each case:
    - the off-centre pixel (200.0, 300.0), 0-based and top-down, maps back
      within 0.3 px;
    - the centre is within 1″;
    - the scale is within 0.1%;
    - the parity matches.
  - `test_index_search_wrong_scale_fails_then_unknown_solves`: a 2× scale
    gives `not_solved`; the same field with the scale unknown solves.
  - `test_index_search_near_restricts_to_radius`: `near` 1.5° off solves;
    `near` 3° off gives `not_solved`.
  - `test_near_catalog_recovers_2x_scale`: `scale_stage == "half"`.
  - **`test_random_dots_never_solve`:** 50 seeded random-dot fields give
    `not_solved` on both search paths, and none reaches the threshold.
  - **`test_ambiguous_pattern_refused`:** a catalog containing the same star
    pattern at two sky positions 30° apart gives `ambiguous`, with
    `wcs is None`.
  - **`test_deadline_after_first_acceptance_not_solved`:** the clock is
    patched to expire after the first accepted candidate, before a second
    conflicting one is checked. The result is `time_limit` with
    `wcs is None`, on both search paths.
  - `test_cancel_during_ambiguity_scan_not_solved`: the same with cancel;
    `cancelled` with no WCS.
  - `test_cancel_stops_quickly`: the event set from another thread returns
    `cancelled` within 0.5 s.
  - **`test_configs_match_prototype`:** every field of both configs equals
    the prototype's values, listed literally in the test.
- [ ] **Step 2:** `uv run pytest tests/native_solver -v`. Expected: fail.
- [ ] **Step 3: Port** from the prototype:
  - `geometry.py`;
  - `extract.py` (array functions only; loading moves to Task 6; no
    `set_gpu_enabled`);
  - `solve.py`'s verification, fit, refinement and `solve_hinted`;
  - `blind_solve.py`'s `solve_blind`.

  Behavior is unchanged except for the early-stop rule in Global
  Constraints. Rename to the product names above, add the `cancel` checks
  between candidates, and pass `deadline` in. The benchmark-only branches go:
  `wrong_candidate`, memory probes and timing-only fields.
- [ ] **Step 4:** run Step 2's command. Expected: PASS.

### Task 6: Solving an image, and the dispatcher

**Files:**
- Create `services/native_solver/solve_image.py` and `hints.py`.
- Modify:
  - `services/plate_solve.py`: add `run_solve`, `solve_slot`,
    `solve_slot_wait`, `rotation_from_cd` and `shutdown`; make progress and
    cancel native-aware. The existing unguarded `_do_solve` (ASTAP
    preprocessing, row correction, retries and `_run_astap`) is reused
    unchanged;
  - `main.py`: call `plate_solve.shutdown()` and `fetch.shutdown()` after
    the lifespan's `yield`.
- Test `tests/native_solver/test_solve_image.py` and `test_hints.py`, and
  additions to `tests/test_plate_solve.py`.

**Interfaces:**
- Consumes Tasks 1–5, `pixel_loader.load_normalized_mono` and
  `plate_solve.read_header_cards`.
- Produces:
  - **`SolveHints`:**
    `hints.SolveHints(ra_deg: float | None, dec_deg: float | None, scale_arcsec: float | None)`.
  - **`hints_for`:**
    `hints.hints_for(cards, *, image_height: int, ra_hint, dec_hint, fov_hint) -> SolveHints`.
    Request hints win over the header.
    - The position comes from `RA`/`OBJCTRA`/`CRVAL1` and
      `DEC`/`OBJCTDEC`/`CRVAL2`, through the existing parsers.
    - The scale is `206.265 * XPIXSZ / FOCALLEN`, or
      `fov_hint * 3600 / image_height`.
  - **`solve_image`:**
    `solve_image(image_path: str, hdu: int, hints: SolveHints, *, cancel: threading.Event, progress: Callable[[str], None]) -> PlateSolveResult`.
    It is synchronous. It runs the solve order, budgets and minimums in
    Global Constraints exactly.
    - Its prerequisite results:
      - `stars_not_installed` when no catalog is installed;
      - `no_ranges` when no layer is built and there is no position.
    - After all steps miss, the unsolved-outcome rule in Global Constraints
      applies.
  - **`plate_solve.run_solve`:**
    `run_solve(*, solver: Literal["native", "astap"], astap_path: str | None, image_path: str, hdu: int, mode: str, ra_hint, dec_hint, fov_hint, timeout: int) -> PlateSolveResult`.
    - It claims `_solve_semaphore` once, the same race-free way the current
      code does.
    - `astap` resolves the binary and calls the existing unguarded
      `_do_solve`. The old `run_plate_solve` stays as the guarded wrapper for
      existing callers and tests.
    - `native` starts `asyncio.to_thread(solve_image, ...)` as a stored task
      with a fresh `threading.Event`, and awaits it through
      `asyncio.shield`. If the awaiting coroutine is cancelled, it sets the
      event and awaits the task's completion before releasing the slot,
      then re-raises.
  - **`plate_solve.solve_slot()` and `solve_slot_wait()`:** async context
    managers on the same semaphore. The first raises immediately when taken;
    the second waits.
  - `plate_solve.cancel_solve()` also sets the native event.
    `get_solve_progress()` shows native progress.
  - **`plate_solve.shutdown()`:** sets the native event and waits up to 10 s
    for the worker. It calls `handles.close_all()` only if the worker has
    finished; otherwise it leaves the mappings for process exit.
  - **`rotation_from_cd`:**
    `plate_solve.rotation_from_cd(cd1_2: float, cd2_2: float) -> float`
    holds the current corrected-solution rule, moved out of
    `_compute_results` and used by both solvers.
  - **Result:** native results fill `PlateSolveResult`'s existing fields the
    same way `_compute_results` does: RA/Dec strings, scale, field of view
    and CD/CRPIX. They also set the Task 7 fields.

- [ ] **Step 1: Write the failing tests:**
  - **`test_solve_fits_end_to_end`:** a synthetic FITS in `tmp_path` with
    `RA`, `DEC`, `FOCALLEN` and `XPIXSZ` solves against synthetic star data
    under the redirected `APP_DIR`, with:
    - `solver == "native"`;
    - `solve_path == "near_index"`;
    - `crpix1 == (w + 1) / 2`;
    - Task 5's pixel check passing.
  - `test_headerless_png_solves_blind`: `solve_path == "blind"`,
    `scale_stage == "unknown"`.
  - `test_binned_header_scale_recovered_by_blind`: a header scale 2× the
    true one gives `solve_path == "blind"` and `scale_stage == "unknown"`. A
    spy shows the unknown-scale step extracted with no scale.
  - `test_position_3_degrees_off_falls_back_to_blind`: `solve_path == "blind"`.
  - **`test_position_no_scale_unaffected_by_unrelated_range`:** a header
    position, no scale and 11 detections. It solves with
    `solve_path == "near_catalog"` with no layers built, and again after an
    unrelated range is built.
  - `test_near_budget_leaves_time_for_blind`: a near step patched to use its
    whole 20 s budget is followed by the blind step.
  - `test_scale_known_exhaustion_leaves_time_for_unknown`: a scale-known
    blind step patched to use its 10 s is followed by the unknown-scale
    step.
  - `test_catalogue_timeout_reports_time_limit`: no layers built, a header
    position and **no scale** (so the field is unknown and `field_not_built`
    cannot apply). A catalogue step that exhausts its 20 s gives
    `time_limit`, not `no_match`. (Corrected during Phase B: with a scale,
    the field is known, and `field_not_built` correctly wins under the
    outcome precedence.)
  - `test_blind_timeout_then_catalogue_miss_reports_time_limit`: a position
    and no scale; the blind step exhausts its 30 s and the catalogue step
    finishes without a match. The result is `time_limit`.
  - `test_field_not_built_wins_over_time_limit`.
  - `test_field_not_built_message`: the exact text, with the field and the
    range.
  - `test_stars_not_installed` and `test_no_ranges_without_position`.
  - **`test_no_gpu_during_solve`:** the end-to-end solve succeeds with
    three functions patched to raise:
    - `nightcrate.core.compute.get_array_module`;
    - the alias `nightcrate.services.imaging.get_array_module`;
    - `nightcrate.core.compute.set_gpu_enabled`.

    `compute._gpu_enabled` is unchanged.
  - **`test_rotation_from_cd`:** each pair maps to its expected value, with
    s = 1e-4:

    | (CD1_2, CD2_2) | Expected rotation |
    |---|---:|
    | (0, s) | 0.0 |
    | (−s·sin 30°, s·cos 30°) | 30.0 |
    | (s·sin 30°, s·cos 30°) | −30.0 |
  - `test_run_solve_astap_success`: ASTAP through `run_solve`, with the
    subprocess mocked as in the existing tests. It succeeds, proving there
    is no self-conflict.
  - `test_run_solve_409_when_busy`.
  - **Slot tests,** each with `solve_image` patched to block on an event:
    - `test_cancel_route_releases_slot_after_worker_stops`: the slot stays
      taken until the worker returns, and a delete-range in between gets
      409;
    - `test_task_cancellation_waits_for_worker`: cancelling the awaiting
      task leaves the slot taken until the worker returns;
    - `test_shutdown_waits_for_worker_and_closes_handles`;
    - `test_shutdown_leaves_mappings_when_worker_outlives_timeout`: with the
      timeout patched short and the worker still blocked, `close_all` is not
      called.
  - `test_astap_path_unchanged`: existing ASTAP tests pass unmodified.
  - `test_progress_messages`: the sequence includes "Loading image",
    "N stars detected" and "Blind solve: fields …".
- [ ] **Step 2:** `uv run pytest tests/native_solver tests/test_plate_solve.py -v`.
  Expected: the new tests fail.
- [ ] **Step 3: Implement.** Load images with `load_normalized_mono`. Detect a
  Bayer mosaic with the prototype's `_has_bayer_header` rule.
- [ ] **Step 4:** run Step 2's command. Expected: PASS.

### Task 7: Migration 0065, the setting and the API contracts

**Files:**
- Create `db/migrations/0065.project_solve_solver.sql`.
- Modify:
  - `core/config.py` (`default_solver`);
  - `services/plate_solve_models.py`;
  - `api/plate_solve.py`;
  - `api/project_solve.py` and `api/project_solve_models.py`;
  - `DB_SCHEMA_DDL.sql` and `DB_SCHEMA.md`.
- Test `tests/test_migration_0065.py`, and additions to
  `tests/test_project_solve_api.py`, `tests/test_config.py` and the plate
  solve API tests.

**Interfaces:**
- **Migration** (`depends` on 0064):
  - `ALTER TABLE project_solve ADD COLUMN solver TEXT NOT NULL DEFAULT 'astap' CHECK (solver IN ('native', 'astap'))`;
  - then nullable `star_catalog TEXT`, `stars_detected INTEGER`,
    `stars_matched INTEGER`, `rms_px REAL`, `log_odds REAL`,
    `solve_path TEXT` and `scale_stage TEXT`.
- **Setting:** `Settings.default_solver: Literal["native", "astap"] = "native"`.
- **`PlateSolveRequest`** gains `solver: Literal["native", "astap"] | None = None`.
  `ProjectSolveRequest` gains the same.
- **`PlateSolveResult` and `ProjectSolveResponse`** gain:
  - `solver: Literal["native", "astap"]`;
  - `star_catalog: str | None`, `"Siril Gaia DR3 astrometry 1.0.0"` for
    native;
  - `stars_detected`, `stars_matched`, `rms_px`, `rms_arcsec`, `log_odds`;
  - `solve_path: Literal["near_index", "near_catalog", "blind"] | None`;
  - `scale_stage: str | None`.

  `PlateSolveResult` alone also gains `failure_reason: str | None`, a key of
  `MESSAGES`.
- **Routes:**
  - Both call `run_solve` with `request.solver or settings.default_solver`.
  - The ASTAP path check and its 422 apply only when the choice is `astap`.
  - A native solve that runs and doesn't solve:
    - `/plate-solve/solve` returns 200 with `solved: false`, `error_message`
      set to the message text, and `failure_reason`;
    - the project route returns 422 with
      `detail = {"message": ..., "failure_reason": ...}`.

    Its other 422s keep string details.
  - The project route saves the new columns, and `GET` returns them.
    `rms_arcsec` is `rms_px * pixel_scale_arcsec`.

- [ ] **Step 1: Write the failing tests:**
  - **`test_migration_0065`:** a database at 0064 with two existing solves
    and their `project_dso` rows upgrades. Then:
    - both rows have `solver = 'astap'`, and the new columns are NULL;
    - every original `project_solve` column value (WCS, CRPIX, sizes,
      `solved_at`) is unchanged;
    - `project_dso` ids and their `solve_id` and `dso_id` are unchanged;
    - `PRAGMA integrity_check` returns `ok`, and `foreign_key_check` is
      empty;
    - an insert with `solver = 'x'` fails the CHECK;
    - a fresh database migrates to 0065.
  - `test_default_solver_setting`: the default is `"native"`, an invalid
    stored value falls back to it, and the round trip works.
  - **`test_solve_route_native_default_without_astap`:** no ASTAP path and
    synthetic stars installed give 200 `solved: true` and
    `solver == "native"`.
  - `test_solve_route_astap_requires_path`: `solver="astap"` with no path
    gives 422.
  - **`test_project_solve_saves_native_fields`:** the `POST` then `GET`
    round trip returns every new field, including `scale_stage`, and
    `rms_arcsec` is computed.
  - `test_project_solve_unsolved_detail_object`.
  - `test_project_solve_forwards_solver_astap`.
  - `test_project_solve_cancelled_saves_nothing`: a cancelled native project
    solve leaves no `project_solve` or `project_dso` row.
  - `test_existing_astap_project_solve_reads_back_as_astap`.
- [ ] **Step 2:** run those tests. Expected: fail.
- [ ] **Step 3: Implement.** Update the DDL and the schema diagram.
- [ ] **Step 4:** run them, then the full `tests/test_plate_solve*.py`,
  `tests/test_project_solve_api.py`, `tests/test_migration_0064.py` and
  `tests/test_config.py`. Expected: PASS.

---

## Phase C: frontend

UI follows the approved mockups:
`.superpowers/brainstorm/43189-1793279244/content/admin-stars-v2.html`, and
`solve-dialog.html` states A, C, D and E. State B is replaced by the sidebar
rows.

**Colours.** The theme tokens and colours used by `CatalogsAdminSection.tsx`
apply: amber primary and slate blue secondary. "Built" uses the secondary
colour with a check mark, never green. No red/green or purple/amber pairs.

### Task 8: Admin "Plate-solving stars" section

**Files:**
- Create `frontend/src/api/starCatalog.ts` (types matching Task 4 and the
  TanStack hooks) and
  `frontend/src/components/admin/StarCatalogAdminSection.tsx`.
- Modify `frontend/src/pages/AdminPage.tsx` to render the section directly
  below `CatalogsAdminSection`.

**Interfaces:**
- `useStarCatalogStatus()` polls `GET /api/admin/star-catalog/status` every
  1 s while `operation?.state === "running"`, and otherwise doesn't poll.
- There are also mutations for download, import, cancel, build, delete-range
  and delete-all, each invalidating the status.

- [ ] **Step 1: Build the three states.** Text, sizes and buttons are as in
  the mockup:
  - **Before download:** the intro text, the catalog row with "Import file…"
    and "Download", and the note "Field ranges can be chosen once the stars
    are installed."
  - **Downloading:** a progress bar, then
    "Downloading · {done} of {total} · about {n} min left · resumes if
    interrupted", and Cancel. While unpacking, "Verifying" and "Unpacking"
    replace "Downloading".
  - **Installed:**
    - the catalog row ("Version 1.0.0 · 1.52 GB · checksum verified ·
      CC BY 4.0 · zenodo.org") with Remove;
    - "Field ranges" with the explanation ending "can't be blind solved.";
    - the table: tick box, "Field width", "Your rigs" chips (name and
      field), "Size" (prefixed "about" when an estimate), "Status", and a
      Remove button per built range;
    - under a range whose `build_memory_bytes` exceeds 2 GB, the caption
      "Building needs about {n} GB of memory.";
    - a "Needs rebuilding" status that offers Build;
    - "Build selected" (disabled when nothing new is ticked);
    - the space-used line.
  - **Ticks start** on unbuilt ranges that cover a rig and on built ranges.
  - **"Import file…"** opens the existing `FileBrowser`
    (`components/fits/FileBrowser`).
  - **Remove-all** asks for confirmation in an MUI `Dialog` (never a browser
    `confirm`), stating the space freed.
  - **Errors** show in an `Alert` with the server's message, parsed by the
    Task 9 helper.
  - **The attribution line** under the table: "Stars from ESA's Gaia DR3
    (ESA/Gaia/DPAC), prepared by the Siril team. Catalogue CC BY 4.0; Gaia
    data also under CC BY-NC 3.0 IGO."
- [ ] **Step 2:** run `npm run build` in `frontend/`. Expected: it succeeds,
  with only the existing bundle-size warning.

### Task 9: The solve dialog, the setting and the result rows

**Files:**
- Modify:
  - `frontend/src/api/plateSolve.ts` and `projectSolve.ts` (new fields,
    `solver` request field, `failure_reason`, the error helper);
  - `frontend/src/api/settings.ts` (`default_solver`);
  - `frontend/src/components/plate-solve/PlateSolveDialog.tsx`;
  - `frontend/src/pages/SettingsPage.tsx` (`AstapPathSection`);
  - `frontend/src/components/plate-solve/PlateSolveDetailPanel.tsx`;
  - `frontend/src/components/analyzer/ImageAnalyzerView.tsx`;
  - `frontend/src/components/projects/ProjectPlateSolveTab.tsx`.

**Interfaces:**
- **The error helper:**
  `parseApiError(err: unknown): { message: string; failureReason: string | null }`
  in `api/plateSolve.ts`.
  - `apiFetch` throws `Error(rawResponseText)`
    (`frontend/src/api/client.ts:41-44`).
  - The helper parses the text as JSON. A string `detail` becomes the
    message. An object `detail` gives `message` and `failure_reason`.
  - Anything else becomes the raw text, or "Plate solve failed." when it is
    empty.
  - It never returns an object to render.

**Steps:**

- [ ] **Step 1: Dialog.**
  - **Removed:** the near/blind mode request (always send `mode: "auto"`)
    and the 300 s blind timeout.
  - **Kept:** "Blind solve" chip, shown when no position is known.
  - **State A:** a caption under the hints, "Solver: built-in (Gaia DR3
    stars). Change the default in Settings." or "Solver: ASTAP. Change the
    default in Settings."
  - **Ready check.** `configured` becomes:
    - for native, the stars installed, and at least one range built or a
      position known (status fetched on open);
    - for ASTAP, the path is set.
  - **State D,** when native is the default and the stars aren't installed,
    or no range is built and no position is known:
    - the message;
    - "Open Admin", which navigates to `/admin`;
    - "Solve with ASTAP", only when the ASTAP path is set.
  - **State C,** after a native failure:
    - the message, with the sentence "A target or a position in the image
      header lets it solve near that position." when `no_match`;
    - Retry;
    - "Solve with ASTAP", only when the ASTAP path is set. It re-runs with
      `solver: "astap"`.
  - **Errors:** every catch uses `parseApiError`. `solveViaProject` forwards
    `solver`, and turns a 422 with an object `detail` into
    `{solved: false, error_message, failure_reason}`.
  - A successful solve still closes the dialog.
- [ ] **Step 2: Settings.** A "Default solver" radio (Built-in / ASTAP) above
  the ASTAP path. The path's help text reads: "Optional. Used when ASTAP is
  the default, or when you choose "Solve with ASTAP"."
- [ ] **Step 3: Sidebar and project rows.**
  - `ImageAnalyzerView` keeps the whole `PlateSolveResult` from `onSolved`,
    beside the WCS it already keeps.
  - `PlateSolveDetailPanel`'s "Astrometric Solution" section and
    `ProjectPlateSolveTab`'s summary show:
    - Solver: "Built-in · Gaia DR3 (Siril 1.0.0)" or "ASTAP";
    - Stars: "{matched} matched of {detected} detected";
    - Fit error: "{rms_px:.2f} px RMS ({rms_arcsec:.2f}″)".
  - The rows are omitted when a value is null.
  - A header-read solution in the Image Analyzer shows no solver rows.
- [ ] **Step 4:** run `npm run build`. Expected: it succeeds.

---

## Phase D: benchmark, trials and docs

### Task 10: Benchmark script, real-star trials and documentation

**Files:**
- Create:
  - `backend/scripts/plate_solve_benchmark.py`;
  - `backend/tests/native_solver/test_real_sky_trials.py`, skipped unless
    `NIGHTCRATE_STAR_DATA` points at a folder holding the real `.dat` and
    built layers.
- Modify:
  - `README.md` (features, prerequisites: ASTAP optional, and
    acknowledgments per spec §8);
  - `docs/development-decisions.md` ("Plate solving": native solver, star
    data, ranges and manifest, acceptance settings, early-stop rule, solve
    order and budgets, worker and slot, output convention);
  - `docs/README.md` (code map).

**Interfaces:**
- **Benchmark command:**

  ```
  uv run python scripts/plate_solve_benchmark.py --corpus <dir> --targets <json> --star-data <dir> --output <dir> [--astap <path>] [--modes ...] [--images token ...] [--limit N] [--ranges id ...]
  ```

  - It runs one image at a time through `solve_image` and `run_plate_solve`.
  - It writes `results.jsonl` and `summary.md` to `--output`, which must be
    outside the repository; the script refuses a path inside it.
  - **Modes:**
    - `native` is the product flow;
    - `native-blind` has position and scale removed;
    - `astap` is today's auto mode.
  - `--ranges` limits the layers used to those ranges, for the boundary
    check.
  - **Summary:**
    - the bar of spec §11.2, computed exactly as written there;
    - wrong solutions against an independent reference (ASTAP's solution or
      a stored header WCS), by the prototype's rule: parity mismatch, or a
      grid median beyond 1% of the diagonal;
    - counts by input format (FITS, XISF, PNG, JPEG, TIFF);
    - the rotation difference against ASTAP;
    - per-image peak memory.
- **Trials:** `test_real_sky_trials.py` runs `N` (default 2,000) seeded
  positives across the whole sky, with fields of 0.2–10° and the calibrated
  generator, plus 1,000 random-dot negatives.
  - It asserts zero wrong solutions and zero solved negatives.
  - It first writes the generated inputs (detections, quad detections,
    image size, scale given or not, and the true WCS) to a fixture file, at
    `NIGHTCRATE_TRIALS_FIXTURE`.
  - It writes recovery by field range and declination band to
    `NIGHTCRATE_TRIALS_OUTPUT`.
  - The fixture file lets Task 11 feed the prototype exactly the same inputs,
    with the same layers and budgets.

- [ ] **Step 1:** write the script and the trials test. Run the trials test
  without the environment variable. Expected: skipped.
- [ ] **Step 2:** `uv run ruff check src tests scripts` and
  `uv run ruff format --check src tests scripts`. Expected: clean.
- [ ] **Step 3:** documentation edits. Then check links with the
  repository's usual link check, and run `git diff --check`.

---

### Task 10b: Two index choices (revision, Fred 2026-10-29)

Task 11's range check found that a field near the bottom of a range needs the
next smaller layer. Fred replaced the six ranges with two choices, following
SASpro (spec §4.4, revised).

**Files:**
- **Modify:**
  - `backend/src/nightcrate/services/star_catalog/ranges.py`
  - `backend/src/nightcrate/services/native_solver/messages.py` and
    `solve_image.py` (`field_not_built` wording only)
  - `backend/src/nightcrate/api/star_catalog.py` and
    `star_catalog_models.py`
  - `frontend/src/api/starCatalog.ts` and
    `frontend/src/components/admin/StarCatalogAdminSection.tsx`
  - the matching tests
  - `docs/development-decisions.md` (Plate solving)
  - `README.md`, only if a stated size changes

**Contract:**
- `FIELD_RANGES` has two entries:
  - `("0.4-10", 0.4, 10.0, ("q008", "q016", "q032", "q064", "q128", "q256"))`,
    named "Standard", recommended, build memory 3_200_000_000;
  - `("0.2-0.4", 0.2, 0.4, ("q004",))`, named "Narrow fields", not
    recommended, build memory 5_400_000_000.
- `FieldRange` gains `name: str` and `recommended: bool`, and `RangeStatus`
  exposes both.
- Admin:
  - ticks a not-built range by default when it is recommended or covers a
    rig;
  - shows the name with the field span;
  - lists Standard first.
- `field_not_built` names the choice to build.
- Layers, the build, removal and the manifest mechanics are unchanged.
  Manifests holding old range ids need no migration (the version is
  unreleased); unknown ids are ignored.

**Tests:**
- The table: ids, spans, layers, estimated bytes 529_127_680 and
  1_387_419_120.
- `range_for_field` at 0.2, 0.3999, 0.4, 9.99 and 10.0, plus out-of-range
  values.
- The status route returns `name` and `recommended`.
- The `field_not_built` message for a 0.30° field names Narrow fields.

## Task 11 (Claude): measurements, verification and integration

Each item records its result in PLAN.md. A miss on the bar or a safety
result goes to Fred before anything else.

- [ ] **Thread against process** (spec §5.4). On Fred's Mac, measure a solve
  run with `asyncio.to_thread` and with a per-run spawn process, 20 corpus
  subs each. Keep the thread unless the process is within 0.1 s at the
  median.
- [ ] **The real download** from Zenodo through the Admin route, against a
  temporary `HOME`, including one interruption and a resume, and an
  interruption during unpacking. Record the time.
- [ ] **Build every layer** on Fred's Mac with the default thread count.
  Record:
  - the time;
  - the peak resident memory of the parent and the child together, which
    updates `build_memory_bytes`;
  - the peak temporary disk use, which confirms or updates the 3.0 ×
    preflight;
  - the combined memory of a `q004` build and a concurrent solve.
- [ ] **Range boundaries** (spec §4.4). Run the corpus with each range built
  alone (`--ranges`), plus seeded synthetic fields at each range's edges.
  If fields near a boundary need the neighbouring layer, add it to the range
  table and update the estimates.
- [ ] **Port check.** On 20 corpus images, the product's solutions match the
  prototype's phase 2c results within 0.1 px median grid distance.
- [ ] **Corpus benchmark** against the bar (spec §11.2), with the
  per-format counts and the rotation agreement with ASTAP (within 0.1° on
  images both solve).
- [ ] **Real-star trials** with `NIGHTCRATE_STAR_DATA` set. Feed the same
  fixture file to the prototype's `solve_blind`, with the same layers and
  budgets, through a local script outside the repository. The product's
  recovery in each field range and declination band must be no more than 2
  points below the prototype's, with zero wrong answers and zero solved
  negatives.
- [ ] **Migration gate.** Upgrade a copy of Fred's database at 0064 through
  the app's runner. Check:
  - row counts in every table;
  - existing solves' WCS values and `project_dso` ids;
  - `integrity_check` and `foreign_key_check`;
  - that existing solves read back as ASTAP;
  - that a re-run is a no-op;
  - and a fresh database.
- [ ] **Rendered checks** (headless Playwright, temporary `HOME`):
  - every Admin state and every dialog state, in light and dark, at 1500
    and 820 px;
  - the failure transports: `no_match` (a noise image), `field_not_built`,
    `stars_not_installed`, a string-detail 422 (an invalid ASTAP path) and a
    non-JSON error, in both the Image Analyzer and the project tab;
  - "Solve with ASTAP" from the project tab saving `solver = 'astap'`;
  - the sidebar and project rows;
  - the Settings radio and keyboard focus order;
  - that a successful solve closes the dialog.
- [ ] **Full checks.**
  - Backend: `uv run ruff check src/ tests/ scripts/`,
    `uv run ruff format --check src/ tests/ scripts/`,
    `uv run bandit -r src/`, `uv lock --check`, and the full
    `uv run pytest` run outside the Codex sandbox.
  - Frontend: `npm run build`.
- [ ] **A fresh independent Codex review** of the whole change (`gpt-5.6-sol`,
  high, read-only).

## Codex review

- **Builder check (Claude subagent) of the spec, before the plan.** Four
  questions.
  - Two were settled from the prototype's evidence:
    - index searches use the blind acceptance settings they were measured
      with;
    - the bar's measurement method is fixed before any run.
  - Fred answered the other two:
    - the dialog keeps closing on success, with the new rows in the sidebar
      and the saved solve;
    - his dev server stays stopped.
- **Mode:** independent plan review. Rounds: 4/5. Records:
  `.superpowers/codex/v0.43.0/` (local).
- **Adopted changes.** Every finding was accepted; none was rejected.
  - **Never wrong.** A search stopped by its deadline or a cancel before its
    ambiguity check has finished is not a solve. The prototype's blind
    search returned such a result as solved.
  - **Solve slot.** The native worker owns the solve slot until it has
    actually stopped, on cancel, request cancellation and shutdown. Shutdown
    never closes mapped files under a live worker.
  - **ASTAP dispatch** reuses the existing unguarded `_do_solve`, so the slot
    is claimed once.
  - **Mapped files.**
    - Every publication and deletion closes the cached handles first, under
      the solve slot.
    - Download and import run only when the stars aren't installed.
    - A build may run during a solve; only its publication waits.
  - **Download recovery:**
    - a complete partial file is verified without a request;
    - a wrong `Content-Range` is rejected;
    - writes are bounded;
    - a short transfer resumes from the new size;
    - a verified compressed file survives a failed unpack.
  - **Index build.** Building in sky portions was dropped: proving
    equivalence needed rules the prototype never had. The prototype's
    whole-sky builder runs unchanged in one child process per layer.
    - Its temporary files live in a parent-owned folder, removed after the
      child is joined.
    - Disk preflight is 3 × the layer size.
    - Its memory need is shown in Admin.
  - **Ranges.** A manifest records the user's ranges. Shared layers are kept
    while any remaining manifest entry lists them.
  - **Solve order.**
    - Only the prototype's measured modes are used, and the index search has
      no 0.5×/2× retries.
    - With a position and no scale: blind first, then catalogue, regardless
      of installed ranges.
    - Each step has its own budget (20 s, 10 s, 30 s) under a 60 s total,
      and its own extraction.
    - Minimums: 12 detections for an index search, 10 for the catalogue
      search.
  - **Outcome precedence** when nothing solves: field not built, then
    ran out of time, then no match.
  - **Records and tests.**
    - `scale_stage` is saved.
    - The migration test checks original values and child ids.
    - The GPU test patches every lookup site.
    - A frontend error helper handles object, string and non-JSON details.
    - The trials feed identical inputs to the prototype for the recovery
      comparison.
- **Tracked items:** none. No material finding was rejected, and no
  disagreement remains.
- **Implementation reviews (2026-10-29).** Records are in
  `.superpowers/codex/v0.43.0/` (local).
  - **First independent review of the whole change (`47`):** four major
    and two minor findings.
    - **Five accepted and fixed (`48–51`):**
      - ASTAP outliving the solve slot on cancellation;
      - an import aliasing NightCrate's own staged file;
      - no cancel or deadline check between load, extraction and search;
      - the native pixel scale not using ASTAP's rule;
      - Admin's rig field not using the dialog's formula.
    - Claude added a sixth fix, found during rendered checks: a plain
      message for a non-JSON error body.
    - **Rejected:** "the Siril catalogue's CC BY 4.0 licence is
      unconfirmed". Zenodo's API record 14692304 has
      `license.id = "cc-by-4.0"`.
  - **Phase E (Task 10b)** followed Fred's decision on the two index
    choices.
  - **Second independent review, of the fixes and Phase E (`57`):** three
    findings, accepted as minor and fixed (`58–61`):
    - ASTAP's ownership began only once its process existed;
    - no stop check before a new extraction;
    - the import guard was case-sensitive.
  - **Re-review of round 2 (`63`):** two findings.
    - **Accepted:** `/cancel` did not set ASTAP's stop flag during
      preparation or before a retry. Sent to the writer as cycle 3
      (`64–66`).
    - **Rejected, minor:** a deadline during the header read reports
      `time_limit` rather than `field_not_built`. The field isn't known
      until the pixels load, a header read can't realistically use up the
      60 s budget, and `time_limit` is a true outcome.
  - **Tracked items:** none open. The two rejections above are closed with
    their evidence.
  - **Closing re-review of cycle 3 (`69`):** one major finding, accepted.
    A cancel while ASTAP's process was being created found no process to
    kill, so the solve ran on. With the cycle limit reached it went to
    Fred, who approved Claude's fix on 2026-10-29 with no fourth review
    cycle: a stop check right after the process starts, and a test that
    holds the launch while Cancel arrives.
  - **Tracked items:** none open.
- **Fixes during Fred's acceptance test (2026-10-30).**
  - **Too many open files:** Claude's fix; the index builder opens one
    partition file at a time.
  - **Build progress and the range table:** Codex implemented it (`70–73`).
    Claude's review sent back one defect, rig chips truncated with "…"
    (`74–75`).
  - **Independent review of both (`77`, fresh read-only session):** no
    blocker or major findings. One minor finding, accepted: a build
    request naming an already-built range reports it as building at 100%
    until it publishes. The Admin page never sends one.
  - **Tracked item:** that finding. **Fred (2026-10-30):** fix it in
    v0.43.1 rather than change the candidate during acceptance. Status:
    pending, owned by v0.43.1 (PLAN.md roadmap, "Faster star download").
  - **Status (2026-11-02, v0.44.0 start sweep):** fixed in v0.43.1 (Task
    B1, merged in PR #22). A build request skips ranges already built and
    `/status` reports a ready range as built; covered by
    `test_build_filters_built_range_while_solve_holds_publication`,
    `test_status_reports_ready_current_range_as_built` and
    `test_ready_but_unlisted_range_is_published_without_rebuild`. Closed.
