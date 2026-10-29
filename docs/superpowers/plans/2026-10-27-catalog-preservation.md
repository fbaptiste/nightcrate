# v0.42.0 — catalog preservation, mirrored overlays, planner star: implementation plan

> **For agentic workers:** this plan follows `docs/agent-collaboration.md`.
> Codex implements Tasks 1–7 one phase at a time **in the worktree
> `../nightcrate-v042-wt`** (detached at 115f18f), never in
> the main checkout, and leaves the work unstaged. Claude reviews each phase,
> re-runs the checks and owns Task 8. Nobody commits without Fred's
> authorization. Steps use checkbox (`- [ ]`) syntax.

**Goal:**
- Catalog reloads keep every object's `dso.id` and every user record.
- Merged objects carry their records over to the survivor; removed objects are
  kept and shown as "not listed".
- XISF FITS-keyword WCS and ASTAP solves of PNG, JPEG and TIFF files stop
  appearing mirrored.
- The planner detail panel gets the wishlist star.

**Architecture:**
- **Object step.**
  - The object inputs (OpenNGC main and addendum, Sharpless, Barnard, the
    Sharpless crossref, the augment CSV) are parsed into one complete new
    object set. Designations and merge signals are resolved purely in memory.
  - That set is matched to existing rows by stored source keys (or, once, by
    legacy display text) and applied in one transaction: in-place updates,
    designations rebuilt, and unclaimed rows merged (records moved) or removed
    (`active = 0`).
- **Enrichment** re-runs after it. Invalidation is recorded by clearing stored
  file hashes.
- **API.** Read routes reached through user records return `active`; routes
  that create new links refuse inactive objects.
- **WCS.** XISF gets a WCS reader that fixes row order. ASTAP results for
  standard-format files are flipped, and migration 0064 repairs saved solves.

**Tech stack:** Python 3.14, FastAPI, Pydantic, raw SQLite (sync `sqlite3` in
the catalog loader, `aiosqlite` in the API), yoyo migrations, astropy;
React/TypeScript/MUI/TanStack Query.

**Spec:**
[2026-10-27-catalog-preservation-design.md](../specs/2026-10-27-catalog-preservation-design.md).
Fred waived his spec and plan approvals for the night of 2026-10-27 ("just
build everything"). Claude's calls are listed in spec §6.

**Baseline:** main checkout and worktree both at `115f18f`. The main checkout
also holds Fred's uncommitted licence and doc edits: `CLAUDE.md`, `LICENSE`,
`PLAN.md`, `README.md` and `frontend/src/components/dso/DsoAttributionPanel.tsx`.
The worktree never changes those five files.

## Global Constraints

- **Migrations:** `0063.dso_source_key.sql` (Task 1) and
  `0064.project_solve_row_order.py` (Task 6, a yoyo Python migration). Never edit an existing
  migration.
- **No new dependency**, Python or npm.
- **Where to work:** code changes go only in the worktree; never touch the five
  files listed under Baseline.
- **Source keys:**
  - OpenNGC: `Name` exactly as written (`NGC0224`).
  - Sharpless: the Sh2 number as the loader normalizes it (leading zeros
    stripped, `"0"` if empty).
  - Barnard: `_normalise_barn_id` of the `Barn`/`B` column.
- **Object inputs:** `openngc`, `openngc_addendum`, `vizier_sharpless`,
  `vizier_barnard`, `nightcrate_sharpless_crossref` and `nightcrate_augment`.
  `nightcrate_barnard_crossref` is read by nothing and stays outside.
- **Enrichment order:** `github_50mgc`, `wikidata_external_refs`,
  `nightcrate_external_refs`, then the redshift pass. The augment loader runs
  as the first step after the object step, whenever the object step ran.
- **Matching passes (spec §1.4).** Each pass runs over *all* new objects of
  *all* sources before the next pass. Matching uses the pre-step snapshot only,
  and each existing row is claimed at most once.
  1. Same source and key.
  2. Same source, NULL key.
     - **Unchanged file** (current effective hash equals the stored
       `file_hash`, Sharpless in its `file:crossref` form): pair each
       same-`primary_designation` group in file order with rows in ascending
       id.
     - **Otherwise:** a row pairs only with the single new object whose
       `source_row_hash` equals its stored one. Everything else stays
       unclaimed.
  3. Same `Name` key in the other OpenNGC source (main ↔ addendum).
  4. New row.

  No designation-based matching.
- **Merge signals only:** an OpenNGC `Dup` row whose own `Name` equals an
  unclaimed row's source key, or a Sharpless crossref whose Sh2 number equals
  an unclaimed Sharpless row's key. Each resolves to the survivor. Rows with a
  NULL key are never merged.
- **Colliding plans:**
  - the survivor's settings win;
  - notes are `survivor_notes`, then `From {old}: {old_notes}`, then
    `From {old}, settings not kept: {name}={value}, …` (only differing
    settings). Non-empty parts are joined by `"\n\n"`;
  - date ranges are unioned, and ranges with `start_date <= previous end_date`
    are merged.
- **Table classes:** catalog-derived tables are `dso_designation`,
  `dso_external_ref` and `thumbnail_cache`. User-link tables are
  `favorite_target`, `project_target` and `project_dso`.
- **Invalidation sentinel:** a stored `file_hash` of `''` means "due again",
  not changed content.
  - An augment hash of `''` runs augment and later enrichment, not the object
    step; a different non-empty augment hash runs the object step.
  - The object step stores `''` for augment and every enrichment source.
  - An enrichment change stores `''` for every later enrichment source before
    running them.
  - Loaders store their real hash only on success.
- **Enrichment clears:** augment, 50 MGC and redshift clear only their own
  values (50 MGC also redshift), only `WHERE active = 1`, and inside their own
  transaction. The object step never touches distances, and touches inactive
  rows only to set `active = 0`.
- **WCS:**
  - **Row flip:** `CRPIX2' = H + 1 − CRPIX2`, `CD1_2' = −CD1_2`,
    `CD2_2' = −CD2_2`.
  - **Rotation:** for flipped results, and for any result without CROTA2,
    `degrees(atan2(−CD1_2, CD2_2))` on the final matrix. Non-flipped results
    with CROTA2 keep it.
  - **CDELT/CROTA:** `CD1_1 = CDELT1·cos ρ`, `CD1_2 = −CDELT2·sin ρ`,
    `CD2_1 = CDELT1·sin ρ`, `CD2_2 = CDELT2·cos ρ`.
- **Standard extensions:** `.png .jpg .jpeg .tif .tiff`, case-insensitive
  (`path_resolver.STANDARD_EXTENSIONS`).
- **Contracts:**
  - new `active: bool` on `DsoDetail`, `FavoriteDsoSummary`,
    `CalendarTargetRow`, project `TargetResponse` and `IdentifiedDso`;
  - 409 responses where Task 4 says;
  - TypeScript types match. No other contract change.
- **Wording:** "No longer listed in {catalog}" in detail views, where {catalog}
  is the source `display_name` without its trailing " (…)". Rows get a text tag
  "Not listed". Codex may propose better wording in its report; Claude decides.
- **UI:**
  - theme tokens; no colour-only meaning;
  - no question-mark icons or tooltip underlines;
  - the star uses `RIG_ORANGE` (on) and `text.disabled` (off).
- **Codex:**
  - never stages, commits, pushes or edits vault notes;
  - runs only the named test modules (`uv run pytest <files>`), never the whole
    suite or GPU tests;
  - for frontend work, runs `npm run build` and ESLint on changed files.

## Review Focus

- **First startup after the upgrade.** Real databases have NULL keys,
  `OTHER …` display text for prefix-less addendum rows, Barnard rows whose
  designation lost to OpenNGC, and Sharpless designations merged onto NGC rows.
  Every row must pair, none may become inactive, and the step must not repeat.
  Pinned by Task 2 (`test_one_time_step_on_legacy_fixture`) and Task 3
  (`test_keys_assigned_stops_repeat`), and checked on Fred's database copy in
  Task 8.
- **Names shared or freed between objects.** Real OpenNGC lists IC 1459 under
  NGC 7368 and NGC 7418, and NGC 764's name belongs to NGC 755. A removal must
  not move records along a shared name. A former duplicate listed again must not
  take its old host's row. Pinned by Task 2.
- **A loaded catalog's file missing on this machine.** Nothing may change.
  Pinned by Task 3 (`test_missing_loaded_source_defers_object_step`).
- **Failures between and inside steps.** Faults injected inside the object
  transaction, and loaders that raise or return `failed` afterwards, must leave
  records intact and the failed source due again at the next load. Pinned by
  Tasks 2 and 3.
- **Which ASTAP inputs to flip.** A `zip::x.png` entry (sent to ASTAP as a
  temporary FITS) must not be flipped; `X.PNG` on disk must be. Pinned by
  Task 6.

---

## Phase A: catalog object step (backend, high-stakes)

### Task 1: Migration 0063 and moving user records

**Files:**
- Create:
  - `backend/src/nightcrate/db/migrations/0063.dso_source_key.sql`;
  - `backend/src/nightcrate/catalog_loader/user_links.py`.
- Test: `backend/tests/catalog_loader/test_user_links.py`.
- Modify: `DB_SCHEMA_DDL.sql` and `DB_SCHEMA.md` (`dso`, `dso_catalog_source`).

**Interfaces:**
- **Produces:**
  - `CATALOG_DERIVED_TABLES` and `USER_LINK_TABLES`, both
    `frozenset[str]` (Global Constraints);
  - `move_user_links(cur: sqlite3.Cursor, old_id: int, new_id: int,
    old_label: str) -> None`. It never commits. `old_label` is the old
    object's display designation, used in merged plan notes;
  - `count_references(cur: sqlite3.Cursor, dso_id: int) -> int`. It counts
    rows in every table with a foreign key to `dso(id)`, discovered at call
    time from `sqlite_master` plus `PRAGMA foreign_key_list`, excluding
    `CATALOG_DERIVED_TABLES`.

- [ ] **Step 1: Migration.**
  - `-- depends: 0062.imaging_rules_cloud_models`;
  - `ALTER TABLE dso ADD COLUMN source_key TEXT;`
  - `CREATE UNIQUE INDEX IF NOT EXISTS idx_dso_source_key ON
    dso(source_catalog_id, source_key) WHERE source_key IS NOT NULL;`
  - `ALTER TABLE dso_catalog_source ADD COLUMN keys_assigned INTEGER NOT NULL
    DEFAULT 0 CHECK (keys_assigned IN (0, 1));`
- [ ] **Step 2: Failing tests.** They use a migrated temp database, with A
  (old) and B (new) as hand-inserted `dso` rows.
  - `test_fk_tables_are_all_classified`: tables with an FK to `dso` equal
    `CATALOG_DERIVED_TABLES | USER_LINK_TABLES` exactly.
  - `test_moves_favorite_with_plans_and_ranges`:
    - **Setup:** A is on the wishlist (sort 3, section S) with one plan and two
      ranges; B is not.
    - **Expect:** B's favorite has sort 3 and section S, the plan has
      `dso_id = B` with both ranges, and no row for A remains.
  - `test_favorite_collision_merges_plans`:
    - **Setup:** A (label "NGC 3") has plans (L, H, R1) with notes "a",
      moon_sep 10, and ranges 2026-11-01..11-10 and 2026-12-01..12-05, and
      (L, H, R2) with notes NULL. B has (L, H, R1) with notes "b", moon_sep 30,
      and range 2026-11-08..11-20.
    - **Expect:**
      - B's (L, H, R1) plan keeps moon_sep 30;
      - its notes are exactly `"b\n\nFrom NGC 3: a\n\nFrom NGC 3, settings not
        kept: moon_sep_deg=10"`;
      - its ranges are 2026-11-01..11-20 and 2026-12-01..12-05;
      - A's (L, H, R2) plan belongs to B;
      - A's favorite is gone.
  - `test_moves_project_target`: A is the target of P, with two sub-frames and
    one `project_source_folder` pointing at it. Afterwards the same
    `project_target.id` has `dso_id = B`.
  - `test_project_target_collision_repoints_children`:
    - **Setup:** P has tA (for A) and tB (for B). Sub-frames, a source folder,
      and rows of a synthetic test table `zz_future_child(project_target_id
      REFERENCES project_target(id))` point at tA.
    - **Expect:** all of them point at tB, and tA is gone.
  - `test_project_dso_collision_keeps_main_flag`: S lists A (`is_main = 1`) and
    B (`is_main = 0`). Afterwards one row for B with `is_main = 1`.
  - `test_count_references_discovers_real_fk_tables`: A with designations and a
    thumbnail row gives 0. A synthetic `zz_future_link(dso_id REFERENCES
    dso(id))` row gives 1.
- [ ] **Step 3: Implement `user_links.py`.**
  - **Favorites:** insert B's favorite (copy `sort_order`, `section_id` and
    `created_at`), then re-point or merge plans, then delete A's favorite. This
    order is required because `target_plan.dso_id` references
    `favorite_target(dso_id)`.
  - **Plan collisions:** resolve them before re-pointing.
  - **Discovery:** `project_target` children and `count_references` find their
    tables through PRAGMA. Table names come only from `sqlite_master`; mark
    those f-strings `# nosec B608`.
- [ ] **Step 4:** `uv run pytest tests/catalog_loader/test_user_links.py`
  passes; ruff and format are clean.

### Task 2: The object step

**Files:**
- Create:
  - `backend/src/nightcrate/catalog_loader/reconcile.py`;
  - `backend/tests/fixtures/catalogs/legacy/`, which holds the mini catalog
    files and `legacy_dso.sql`, a dump of `dso`, `dso_designation` and
    `dso_catalog_source` produced by **today's** loader. Generate it in Step 0,
    before changing any loader.
- Modify:
  - `catalog_loader/loader.py`: `_load_source` is replaced by
    `collect_openngc`; the designation and display helpers stay;
  - `sharpless_loader.py`: adds `collect_sharpless`; `load_sharpless` is
    removed;
  - `barnard_loader.py`: adds `collect_barnard`; `load_barnard` is removed;
  - `_common.py`: `clear_previous_source_rows` is removed.
- Test:
  - `backend/tests/catalog_loader/test_reconcile.py` (new);
  - update `test_loader.py`, `test_sharpless_loader.py` and
    `test_barnard_loader.py` where they assert row replacement.

**Interfaces:**
- **Consumes:** Task 1.
- **Produces (in `reconcile.py`):**
  ```python
  @dataclass(frozen=True, slots=True)
  class NewObject:
      source_id: str
      source_key: str
      columns: dict[str, object]     # dso columns this source owns, incl. primary_designation, source_row_hash
      designations: tuple[tuple[str, str, bool], ...]  # (catalog, identifier, is_primary) as finally owned
      file_order: int

  @dataclass(frozen=True, slots=True)
  class ObjectSet:                   # pure result of collect + resolve, no DB access
      objects: tuple[NewObject, ...]
      merges: dict[tuple[str, str], int]   # (source_id, source_key of a folded object) -> index into objects
      hashes: dict[str, str]               # source_id -> effective hash
      unresolved: int

  def build_object_set(sources: dict[str, CatalogSource], crossref_path: Path | None) -> ObjectSet
  def apply_object_set(conn: sqlite3.Connection, new: ObjectSet,
                       enrichment_source_ids: tuple[str, ...]) -> ReconcileReport
  ```
  - `ReconcileReport` holds per-source counts plus `inserted`, `updated`,
    `reactivated`, `merged`, `removed` and `kept_inactive_merge`.
  - `build_object_set` does what today's loaders do, in today's order, with
    first-owner-wins on designations:
    1. OpenNGC main: for each canonical row in file order, its canonical
       designations and **then immediately** its other-id designations; then
       main Dups;
    2. the addendum the same way;
    3. a retry of all unresolved OpenNGC Dups until no progress;
    4. Sharpless, with crossref targets resolved against the new designation
       set by search key as `_resolve_target` does, and unresolved ones
       falling back to standalone;
    5. Barnard.

    Primary text matches today exactly, including `OTHER <raw name>`.
  - `apply_object_set` does all of the following in one `BEGIN`…`COMMIT`, and
    rolls back on any exception:
    1. snapshot;
    2. match (Global Constraints passes);
    3. INSERT or UPDATE changed columns, including `common_name` and
       `surface_brightness`, and set `source_key` and `active = 1`;
    4. reset both augment flags on claimed rows whose `common_name` or
       `surface_brightness` it rewrote. No distance change; nothing else
       changes on unclaimed rows;
    5. delete and re-insert all designations;
    6. merge unclaimed rows through `merges` only (`move_user_links`, then
       delete if `count_references == 0`, else inactive); others become
       `active = 0`, with former designations no row holds re-attached;
    7. update each object source's `file_hash`, `row_count`, `loaded_at` and
       `keys_assigned = 1`, except `nightcrate_augment`;
    8. set `file_hash = ''` for `nightcrate_augment` and every
       `enrichment_source_ids` row.

- [ ] **Step 0:** with today's code (before any edit), load the mini fixtures
  plus small Sharpless and Barnard TSVs and a crossref, and write
  `legacy_dso.sql`. The fixture must include:
  - a prefix-less addendum row;
  - a Barnard row whose designation collides with an addendum `B` row;
  - a crossref-merged Sh2 number;
  - an NGC row listing another object's IC number (like NGC 7368/IC 1459).

  Also record the generator script in the fixture folder's README.
- [ ] **Step 1: Failing tests** in `test_reconcile.py`, each asserting concrete
  ids, designations and record rows:
  - `test_bootstrap_with_changed_file_pairs_only_unambiguous`, parametrized:
    - the legacy fixture has two `M 7` rows and the new file drops the first;
    - legacy `NGC0001 → M 7` and `NGC0002 → M 8`; the new file removes
      `NGC0001` and gives `NGC0002` the M 7 cross-reference.

    In each case no record moves to a different catalog row: the changed
    rows' old rows become inactive with their records, and unchanged rows
    pair by `source_row_hash`.
  - `test_alternate_name_beats_later_canonical`: an earlier row's other-id
    `B 33` owns that designation over a later canonical `B033`, as today.
  - `test_dup_via_addendum_resolves_before_sharpless`: a main-file Dup of an
    addendum object, with that object also a Sharpless crossref target. The
    Sh2 designation lands on the addendum object; no standalone is created.
  - `test_removed_object_keeps_enrichment`: an augmented, 50 MGC-distanced
    object is removed. Its name, flags and distance remain after the full
    chain.
  - `test_one_time_step_on_legacy_fixture`:
    - **Setup:** load `legacy_dso.sql`, plus a favorite, a target, a solve
      object and sub-frames.
    - **Expect:** `apply_object_set` (from `build_object_set` on the same files)
      keeps every id, with `inserted == removed == merged == 0`. Every row gets
      its key, every record is unchanged, and designations equal the legacy
      ones.
  - `test_second_run_changes_only_updated_at`
  - `test_changed_values_update_in_place`
  - `test_removed_and_nonexistent_become_inactive` (records kept, designations
    re-attached)
  - `test_reappearing_object_reactivates`
  - `test_duplicate_merge_moves_records` (old row deleted; `ngc3` resolves to
    the survivor)
  - `test_merge_kept_inactive_when_referenced_by_unknown_table`: a real
    `zz_future_link` FK row keeps the merged row, with `active = 0`.
  - `test_shared_name_is_not_a_merge`: `IC0009` (wishlisted) is removed while
    `NGC0005` lists IC 9. Expect `IC0009` inactive with its favorite, and none
    on `NGC0005`.
  - `test_former_duplicate_listed_again_gets_new_row` (`NGC0007` was a Dup of
    `NGC0008`).
  - `test_forward_and_chained_duplicates_resolve`: a main-file Dup of an
    addendum object, and a two-step chain.
  - `test_sharpless_crossref_added_and_removed`
  - `test_addendum_to_main_move_keeps_id`
  - `test_null_key_unclaimed_row_is_removed_not_merged`
  - `test_rollback_at_each_stage`: parametrized to raise after designation
    deletion, after the first object update, and after the first
    `move_user_links`. All tables are identical to before.
  - `test_surface_brightness_reset_when_object_becomes_galaxy`
- [ ] **Step 2: Implement** collectors, `build_object_set` and
  `apply_object_set`.
- [ ] **Step 3:** `uv run pytest tests/catalog_loader/` passes.

### Task 3: Load orchestration and Admin routes

**Files:**
- Modify:
  - `catalog_loader/loader.py` (`load_catalogs`, `_dispatch_source`) and
    `augment_loader.py` (clear curated distances when it runs);
  - `api/admin.py`: the four fetch routes call `_run_loader(force=False)`;
    `POST /catalogs/reload` and `/catalogs/nightcrate/reload` keep force;
  - `docs/dso-catalog-architecture.md`: the reload model and object identity.
- Test: `backend/tests/catalog_loader/test_load_orchestration.py` (new) and
  `backend/tests/test_admin_api.py`.

**Interfaces:**
- **Consumes:** Task 2.
- **Produces:** `load_catalogs(conn, catalogs_root, *, force=False) ->
  LoadSummary`, signature and result shape unchanged.
- **Behavior:**
  - **Skip the object step** while any object source that has a
    `dso_catalog_source` row has no file. Each object source then reports
    `skipped`, with `error` naming the missing file. No code path may create a
    source row for a missing file, so a source never loaded and absent never
    blocks.
  - **Otherwise run it** when:
    - any object input's effective hash differs from the stored one;
    - `force` is set;
    - any present, loaded object source has `keys_assigned = 0`.
  - **After an object step:** augment, then all enrichment, forced.
  - **Otherwise:** start from augment if its stored hash is `''`, else from the
    earliest enrichment source whose stored hash is `''` or differs (here and
    everywhere, a stored `''` never counts as an object-input change). Store `''` for every
    later enrichment source first.
  - **Loader changes:**
    - `augment_loader`, `mgc50_augmenter` and `redshift_distance` restrict
      their resets to `active = 1`;
    - `mgc50_augmenter` also clears `redshift` distances inside its own
      transaction before filling.
  - **Redshift** always runs last, as today.
  - **Planner cache:** `_run_loader` in `api/admin.py` clears
    `planner_visibility.default_cache` in a `finally` after every load, so
    the cache is cleared even when a load raises.

- [ ] **Step 1: Failing tests:**
  - `test_wikidata_change_runs_only_wikidata_and_later`
  - `test_barnard_change_runs_object_step_and_all_enrichment`
  - `test_augment_change_runs_object_step`
  - `test_nothing_changed_runs_only_redshift`
  - `test_keys_assigned_stops_repeat`: a keyless unmatched row remains, but
    the next load doesn't run the object step.
  - `test_missing_loaded_source_defers_object_step`: Barnard is loaded, then
    its file is deleted, then OpenNGC changes. Nothing in `dso` or
    `dso_designation` changes, and the summary names the file.
  - `test_failed_enrichment_reruns_next_load`, parametrized:
    - the loader raises;
    - the loader returns `failed`;
    - the editorial pass fails after a Wikidata change;
    - the augment loader fails after a Barnard-triggered object step, with the
      augment file unchanged;
    - interruption after the object commit, simulated by raising in
      orchestration right after `apply_object_set`.

    In each case the next load runs the failed source, and for augment it does
    not run the object step.
  - `test_never_loaded_missing_source_never_blocks`: two runs with no Barnard
    file ever; the object step runs on OpenNGC changes both times.
  - `test_all_merged_sharpless_missing_blocks`: a Sharpless file whose every
    row is crossref-merged loads with `row_count = 0`. After it is removed, an
    OpenNGC change does not run the object step.
  - `test_reactivated_object_loses_dropped_curated_distance`
  - `test_admin_reload_clears_planner_cache`
  - `test_new_50mgc_distance_replaces_stale_redshift`
  - `test_fetch_routes_do_not_force` and `test_reload_route_still_forces`
- [ ] **Step 2: Implement.**
- [ ] **Step 3:** `uv run pytest tests/catalog_loader/ tests/test_admin_api.py`
  passes.

## Phase B: removed objects in the API and UI, and the planner star

### Task 4: API

**Files:**
- Modify:
  - `api/dso.py`: `_fetch_detail` drops `AND active = 1`;
  - `api/dso_models.py`: `DsoDetail.active: bool`;
  - `api/planner.py`:
    - `_load_dso_metadata` adds `AND active = 1`;
    - sky-track, annual-hours and thumbnail drop their `active = 1` filter;
    - `score_single_target` looks up its own object's metadata without the
      active filter. When the object is missing from the cached snapshot (an
      inactive object, or one added after caching), it builds a one-object
      snapshot (`planner_visibility.py:440`, time series included) and scores
      from that;
  - `api/wishlist.py` and `api/wishlist_models.py`:
    `FavoriteDsoSummary.active` and `CalendarTargetRow.active`.
    `add_favorite` returns 409 for an inactive object, with detail "This object
    is no longer listed in its catalog.", and 404 for a missing one.
    `create_plan` accepts an inactive object only when it is already a
    favorite, otherwise 409;
  - `api/project_targets.py`: `TargetResponse.active`; `add_target` returns
    409 for an inactive object;
  - `api/project_solve.py` and `api/project_solve_models.py`:
    `IdentifiedDso.active`. `PUT /projects/{id}/solve/objects/{dso_id}`
    returns 409 when it would create a main target for an inactive object.
    Removing one, or a no-op on an existing target, still succeeds.
- Test: `test_dso_api.py`, `test_planner_api.py`, `test_wishlist_api.py`,
  `test_project_targets_api.py` and `test_project_solve_api.py`. Each sets one
  object `active = 0` with SQL.

- [ ] **Step 1: Failing tests:**
  - **Object detail:** returns 200 with `active: false`.
  - **Wishlist:**
    - the list and calendar show the object with `active: false`;
    - adding it → 409;
    - a plan for an existing inactive favorite → 201;
    - a plan for a non-favorite inactive object → 409.
  - **Projects:**
    - targets show `active: false`; adding the object → 409;
    - solve objects show `active: false`;
    - marking it main → 409, while unmarking an existing main succeeds.
  - **Planner:**
    - with a warm visibility cache computed while the object was active,
      `/targets` no longer returns it after it is set inactive;
    - annual-hours, sky-track and thumbnail return 200 with the same numbers as
      while it was active;
    - with a warm cache that never contained the object, its score, breakdown
      and hours equal a cold computation;
    - catalog list and search still exclude it.
- [ ] **Step 2: Implement.**
- [ ] **Step 3:** the five modules pass.

### Task 5: Frontend

**Files:**
- Create: `frontend/src/components/dso/NotListedTag.tsx`. It is the "Not
  listed" text tag (caption `Typography`, outlined in `text.secondary`) and
  exports `catalogShortName(displayName: string): string`.
- Modify:
  - types in `api/dsos.ts`, `api/wishlist.ts`, `api/projectTargets.ts` and
    `api/projectSolve.ts`;
  - `components/planner/WishlistTab.tsx`: the tag next to the designation in
    rows;
  - `components/planner/WishlistCalendarView.tsx`: the label gets " · not
    listed";
  - `pages/ProjectDetailPage.tsx`: the target chip gets the tag;
  - `components/projects/ProjectPlateSolveTab.tsx`: the identified-object row
    gets the tag; the main toggle is disabled for an inactive object that
    isn't already main;
  - `components/dso/DsoDetailPanel.tsx`: "No longer listed in {catalog}" when
    `active === false`;
  - `components/planner/PlannerDetailPanel.tsx`: optional props `isFavorite?:
    boolean` and `onToggleFavorite?: (dsoId: number) => void`. The star sits in
    the title row before the close button and renders only when
    `onToggleFavorite` is passed. Its icons and aria labels match
    `PlannerTargetCard`. The close button gets `aria-label="Close"`;
  - `pages/PlannerPage.tsx`: passes `isFavorite={favoriteIds?.has(dsoId)}`
    and `onToggleFavorite={handleToggleFavorite}`.

- [ ] **Step 1: Implement.**
- [ ] **Step 2:** `npm run build` passes; `npx eslint` on the changed files
  is clean.
- [ ] **Step 3 (Claude):** rendered check with Playwright on the disposable
  app, light and dark, at 1500 px and 820 px.
  - The tags appear on a copy where a wishlisted, targeted, solved object is
    inactive, and that object is absent from catalog search.
  - The star toggles in the panel and on the card, and the two stay in sync.

## Phase C: mirrored overlays (backend, high-stakes)

### Task 6: WCS row order and the CDELT conversion

**Files:**
- Modify:
  - `services/image_annotations.py`: fix the CDELT/CROTA conversion in
    `detect_wcs_from_cards`; add `flip_wcs_rows(params: WcsParams) ->
    WcsParams`;
  - `services/xisf_io.py`: add `read_wcs_params(source: Path | BinaryIO,
    hdu: int) -> WcsParams | None`. With properties present, the
    property-derived cards are used as one set. With FITS keywords only, it
    runs `detect_wcs_from_cards` and then `flip_wcs_rows`. `read_header` is
    unchanged;
  - `services/plate_solve.py`:
    - `read_wcs_params(source, file_type, image_index, hdu) -> WcsParams |
      None` next to `read_header_cards`; XISF goes through
      `xisf_io.read_wcs_params`, everything else as today;
    - `_compute_results(…, flip_rows: bool = False)` applies the flip and the
      rotation rule;
    - `run_plate_solve` sets `flip_rows` when the file handed to ASTAP has a
      standard extension;
  - `api/plate_solve.py`: `/detect-wcs` and `/annotate` use
    `read_wcs_params`;
  - `docs/development-decisions.md`: the XISF WCS rule, the plate-solving
    row-order fact, and the rotation convention.
- Modify: `backend/tests/conftest.py`. A plain import of a yoyo `.py`
  migration fails, because `step()` needs yoyo's loading context. The
  bootstrap therefore applies `.py` migrations through yoyo:
  - commit the aiosqlite connection;
  - `get_backend(f"sqlite:///{db_path}")` and `read_migrations(<migrations
    dir>)`;
  - `backend.mark_migrations(...)` for the `.sql` migrations the fixture
    already ran;
  - `backend.apply_migrations(backend.to_apply(...))` for the rest;
  - release the backend before the test continues.
- Test: `test_conftest_applies_python_migrations`, a smoke test that the
  fixture database lists 0064 as applied in `_yoyo_migration` and that a
  PNG solve inserted before 0064 runs on a copy is flipped.
- Create: `db/migrations/0064.project_solve_row_order.py`, a yoyo Python
  migration and the repository's first.
  - **Header:** `from yoyo import step`, `__depends__ =
    {"0063.dso_source_key"}`, `steps = [step(_apply)]`.
  - **Rows:** `_apply(conn)` selects rows whose `lower(image_path)` ends with
    a standard extension, with no `::`, and with `image_height`, `crpix2`,
    `cd1_2` and `cd2_2` not NULL. It applies the flip to each.
  - **Rotation:** set to `degrees(atan2(−cd1_2_new, cd2_2_new))` for every
    flipped row.
- Test: `test_image_annotations.py`, `test_xisf_io.py`, `test_plate_solve.py`,
  `test_image_annotations_api.py`, and `test_migration_0064.py` (new).

- [ ] **Step 1: Failing tests:**
  - `test_cdelt_crota_matches_astropy`: CDELT1 = −2.0e-4, CDELT2 = 3.0e-4,
    CROTA2 = 30°, an object 0.1° from CRVAL. Both pixel coordinates equal
    astropy's `WCS(header).world_to_pixel` to 1e-6 px.
  - `test_xisf_fits_keywords_are_flipped`: an XISF with keyword WCS only. The
    object's y equals `H − 1 − y_unflipped`, and x is unchanged.
  - `test_xisf_properties_win_whole`: properties plus contradictory keywords.
    The result equals the properties' solution exactly.
  - `test_compute_results_flip`:
    - **Input:** the raw `.ini` values recorded in the evidence (CD1_1
      3.1708226849663004e-4, CD1_2 1.6613319845650712e-4, CD2_1
      1.6618754352258259e-4, CD2_2 −3.1700913753065986e-4, CROTA2
      −152.33486201188387, CRPIX1 = CRPIX2 = 1504.5), H = 3008. The `.ini` is
      kept at `.superpowers/codex/v0.42.0/01b-astap-png-raw.ini`.
    - **Expect:** CD1_2 and CD2_2 negated, CRPIX2 = 1504.5 (3009 − 1504.5),
      CRPIX1 unchanged, rotation `degrees(atan2(−CD1_2', CD2_2'))` = 27.657
      (to 3 decimals), with or without CROTA2.
    - **Expect for a FITS input** with the same values and no flip: unchanged,
      with the rotation equal to CROTA2.
  - `test_flip_decision_by_input`: `X.PNG` on disk is flipped; `a.zip::b.png`
    and `c.fits` are not. Monkeypatch the ASTAP subprocess as the existing
    tests do.
  - `test_migration_0064_flips_only_standard_files`: three solves (`a.png`,
    `b.zip::c.png`, `d.fits`). Only `a.png` changes, to exact values.
  - `test_migration_0064_rotation_cases`:
    - a row from CROTA2 (stored −152.335) and a legacy-fallback row (stored
      27.660), both with the M74 PNG matrix → 27.657 (to 3 decimals);
    - Codex's positive-determinant, unequal-axis matrix `[[0.8660254,
      −0.5075384], [0.5, 0.8616292]] × 1e-4` with stored 30.0 → the
      corrected-matrix value, matching the runtime fallback.
- [ ] **Step 2: Implement.**
- [ ] **Step 3:** the named modules pass.

### Task 7: Docs

**Files:**
- `docs/development-decisions.md`, catalog section: identity and keys, merge
  and removal rules, the guard test, and the rule that a new table with a
  foreign key to `dso` must be classified.
- `docs/dso-catalog-architecture.md`, if Task 3 has not finished it.
- `DB_SCHEMA.md`.

- [ ] **Step 1:** make the updates; `git diff --check` is clean.

## Task 8 (Claude): verification and integration

- [ ] **Per phase:**
  - inventory before and after;
  - read the full diff;
  - re-run the named tests plus ruff, format and bandit;
  - one batch of findings.
- [ ] **Migration gate:** a copy of Fred's database at 0062, upgraded through a
  disposable backend run from the worktree, and a fresh database.
  - `PRAGMA integrity_check` and `foreign_key_check` are clean;
  - row counts outside `dso` are unchanged.
- [ ] **One-time step on real data:**
  - all 3 targets, 16 solve objects, 3 favorites and 701 sub-frame links stay,
    with the same ids;
  - 0 inserted, 0 removed, every key filled, and the flags set;
  - a forced reload afterwards changes nothing except `updated_at`;
  - the time is recorded against 13.8 s.
- [ ] **Rendered checks:** Task 5 Step 3, plus the overlays after the fix. The
  NGC 7380 XISF and its PNG solved in the app both show Sh2-143 at the top edge.
- [ ] **Full backend suite** outside the sandbox, from the worktree.
- [ ] **Fresh independent Codex review** (`REVIEW` profile) of the whole diff.
- [ ] **Integration:** once Fred has stopped his dev server, apply the worktree
  diff to the main checkout and re-run the full suite there.

## Codex review

- **Builder check (Claude subagent) before the baseline.** Five gaps were found,
  all answered as Claude's calls:
  - missing catalog files;
  - colliding wishlist plans;
  - a former duplicate taking its host's row;
  - merges inferred from shared names;
  - enrichment failure.
- **Mode:** independent plan review. Rounds: 4/5. Records:
  `.superpowers/codex/v0.42.0/` (local).
- **Adopted changes** (all findings were accepted; none were rejected):
  - Identity never comes from shared or former names.
    - Matching passes run globally.
    - Keyless rows pair by position only on a verified unchanged file, and
      otherwise only on an identical catalog row.
    - Merges come only from explicit duplicate or cross-reference signals.
  - The one-time keying step is gated by `keys_assigned`, and today's
    `OTHER <name>` display text is reproduced.
  - The object step is deferred while a loaded catalog's file is missing;
    "loaded" means a source row exists, whatever its row count.
  - The object set is resolved in memory in today's exact designation order,
    with duplicates retried before Sharpless.
  - The object step leaves distances and inactive rows alone. Enrichment clears
    only its own values on active rows, inside its own transaction. The augment
    CSV is an object input.
  - Invalidation is stored as a `''` hash for augment and enrichment, so
    failures and crashes re-run the right sources.
  - Planner: metadata is active-only; reads by id work for removed objects;
    single-target scores come from a one-object snapshot; the cache is cleared
    after every load.
  - Marking an inactive solve object as a main target is refused.
  - The CDELT/CROTA conversion is fixed. One rotation rule applies to
    corrected solutions; migration 0064 is a yoyo Python migration, and the
    test bootstrap runs it through yoyo.
  - Plan collisions record the old settings in the notes.
- **Tracked items:** none. No material finding was rejected, and no
  disagreement remains.

### Implementation review (2026-10-28)

- **Process.** Codex implemented the three phases in a separate worktree,
  because Fred's development server was watching the main checkout. Claude
  reviewed each phase, re-ran the checks, did the rendered checks, and staged
  the work in the worktree.
  - **Phase A, 9 findings, all fixed:**
    - quadratic matching (32 s → 3.5 s on real data);
    - display-name matching still possible after the upgrade;
    - a failing object step escaping the loader;
    - enrichment skipped while a catalog file was missing;
    - merged plans dropping most differing settings;
    - foreign keys declared without a column going undetected;
    - the caller's row factory being changed;
    - missing tests.
  - **Phase B:** no findings; rendered checks passed.
  - **Phase C, 3 findings, all fixed:**
    - a real XISF lost its WCS, because one stray PixInsight property made
      the reader skip the FITS keywords (caught on screen);
    - the flip now always uses the image's real height;
    - a timing-flaky test.
- **Fresh independent Codex review.** No blockers; 2 major findings and 1
  minor, all accepted and fixed:
  - a changed augment file was consumed while the object step was deferred;
  - workspace switches didn't clear the planner cache;
  - an in-flight visibility computation could repopulate the cache after a
    clear.
- **Tracked items:** none. No material finding was rejected, and no
  disagreement arose.

### Release preparation (2026-10-28)

- **Status:** no tracked items to update. Fred read the spec's §6 calls on
  2026-10-28 and asked for no changes.
- **Fixes during preparation** (Codex implemented, Claude reviewed; records
  70–77):
  - a conftest fixture restores the `nightcrate` logger after each test. This
    test-isolation bug was already present at base and failed `make test`;
  - two catalog helpers left without callers were removed, and the augment
    and external-refs loaders' "unchanged file" path is tested directly.
  - No tracked items arise from them.
- **App-data isolation in tests** (found during Fred's acceptance; Codex
  implemented, Claude reviewed; records 78–81). Test runs had deleted Fred's
  real planner thumbnails since v0.16–v0.17, because two cache modules copied
  `APP_DIR` at import. They now resolve it at call time, and a guard test
  fails on any import-time copy. No tracked items arise from it.
- **Planner star during acceptance** (Fred, 2026-10-28; Claude's narrow fix).
  In dark mode the off star used `text.disabled`, which nearly vanishes on the
  dialog's lighter paper (1.2:1 contrast), so Fred could not find it. Fred asked
  for the star left of the object name, and on the planner's cards and the
  wishlist tab left of the thumbnails instead of the far right. All three now
  sit there, and the off
  state takes the default icon colour, like the close button. A small layout
  change with a rendered check, so no Codex review. No tracked items arise
  from it.
- **PR review fixes** (Fred, 2026-10-28, after publishing PR #20; records
  82–85). A code-review agent found five low-severity issues in the changes
  made after the independent review. Codex hardened the app-data guard test
  (import-time code in class bodies, defaults, decorators and aliased
  imports; a pre-sweep folder check; a non-empty scan), and Claude fixed the
  dialog's accessible name and an empty wishlist column. No tracked items
  arise from them.
