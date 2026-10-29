# v0.42.0 design: catalog preservation, mirrored overlays, planner star

**Status:** written on the night of 2026-10-27, after Fred said "just build
everything". Fred made the product decisions marked **Fred**. He asked Claude to
settle the remaining questions; those are marked **Claude's call** and are listed
in §6 for his review. The GPL-3.0-or-later licence change is already done and is
not repeated here.

Evidence for every claim below about current behavior is in the local record
`.superpowers/codex/v0.42.0/01-claude-evidence.md` (measured on copies, never on
Fred's own data).

## 1. Catalog preservation

### 1.1 Why

Every catalog object a user's records point at lives in the `dso` table. A
catalog update deletes that catalog's `dso` rows and inserts new ones with new
IDs. Every foreign key to `dso` cascades, so the user's records go with them:

- wishlist entries (`favorite_target`), with their plans and date ranges
  (`target_plan`, `target_plan_date_range`);
- project main targets (`project_target`). Sub-frame, source-folder and
  project-owned-file target assignments that point at them are set to NULL,
  including ones the user corrected by hand;
- objects found by project plate solves (`project_dso`).

Catalog-derived rows go too (designations, external links, thumbnail cache rows),
but those are rebuilt.

On a copy of Fred's database, one Admin catalog reload deleted all 3 project
targets, all 16 solved-field objects and all 3 wishlist entries, and cleared 701
sub-frame target links (13.8 s). Every Admin fetch or reload button reloads
every catalog with `force=True`, not just the one fetched. A NightCrate update
that changes the bundled Sharpless cross-reference file would do the same to
Sharpless objects at the next startup, with no click.

Nobody has reported losing data yet. The aim is that, once other people install
and update NightCrate, catalog work can never silently delete their records.

### 1.2 Goals

1. Reloading or updating any catalog never deletes or unlinks a user record.
2. An object keeps its `dso.id` across reloads while its catalog still lists it,
   whatever else changes about it (coordinates, magnitudes, names, type).
3. **Fred:** an object that a new catalog version **merges** into another
   object (OpenNGC marks it a duplicate, or a NightCrate cross-reference maps a
   Sharpless number onto an NGC/IC object) is handled silently. The user's
   records move to the surviving object, and the old name stays attached to
   that object as a designation, so searching the old name still finds it.
   Nothing is flagged.
4. **Fred:** an object a new catalog version **removes** (no longer listed, or
   marked nonexistent) is kept. Where the user's records point at it, it is shown
   with a short note that the catalog no longer lists it. It is hidden from
   catalog browsing, search and the planner's target list, so it is not offered
   as a new target. The user's records are never deleted.
5. **Fred:** reloads update objects in place. Fetching one catalog no longer
   reloads the others.

### 1.3 Non-goals and anti-goals

- No user-facing merge or removal history, review screen or undo.
- No change to which catalogs exist, their precedence, or how the catalog page
  looks for normal (listed) objects.
- Not a fix for every pre-existing enrichment quirk (for example, removing a
  row from the editorial augment CSV leaves its old common name until the base
  catalog row changes). Behavior the spec does not mention stays as it is.
- **Anti-goal:** any path, including failures and partial loads, that leaves a
  user record deleted, re-pointed to the wrong object, or silently unlinked.
  The object step (§1.7) is one transaction: if it cannot complete, objects,
  designations and records stay exactly as they were. Enrichment does not
  touch user records. Its loaders keep their own transactions, and §1.7 covers
  their failures.

### 1.4 Object identity

Objects come from four **object sources**: `openngc`, `openngc_addendum`,
`vizier_sharpless` and `vizier_barnard`. Two bundled files also shape object
rows:
- `nightcrate_sharpless_crossref` (merges);
- the editorial augment CSV `nightcrate_augment`, which overwrites common names
  and surface brightness on object rows.

Together these six are the **object inputs**. `nightcrate_barnard_crossref` is
registered for attribution only, and no code reads it. The rest is
**enrichment**: 50 MGC distances, Wikidata links, the editorial
external-reference CSV, and the redshift distance pass.

Each object row records the source's own name for it, its **source key**:

- OpenNGC (main and addendum): the `Name` column exactly as written
  (`NGC0224`, `IC0434`, `Cl399`, …).
- Sharpless: the Sh2 number as the loader normalizes it (`142`).
- Barnard: the Barnard identifier as the loader normalizes it.

**The object step** works out the complete new object set before it touches
the database:
1. every object, with its designations, primary designation and display text
   computed exactly as today (including today's `OTHER <name>` text for
   OpenNGC rows with no catalog prefix);
2. duplicate folds and Sharpless cross-references resolved against that new
   set, keeping today's order exactly:
   - for each canonical row, its own designations and then its other-id
     designations, row by row in file order (an earlier row's alternate name
     can own a later row's canonical name, as today);
   - then that file's duplicates.

   OpenNGC duplicates that stay unresolved are retried until no further
   progress, **before** any Sharpless cross-reference is resolved. A
   duplicate that points forward (main file → addendum) or along a chain
   therefore still resolves, and Sharpless sees the final OpenNGC set.

It then matches new objects to existing rows in passes. **Each pass runs over
all new objects of all sources before the next pass starts.** Each existing row
is claimed at most once, and matching uses only the database as it was before
the step.

1. The row with the same source and source key.
2. Rows from the same source with no source key yet and the same
   `primary_designation` text.
   - **Unchanged file** (current hash equals the stored hash, so the rows were
     written from this file): the group is paired in file order with rows in
     id order, which is exact.
   - **Changed file**, for example newer shared catalog files met by a
     workspace that has not yet assigned keys: display text alone proves
     nothing, because Messier names come from cross-reference columns. A row
     pairs only with the one new object whose `source_row_hash` equals its
     stored one, meaning the catalog row itself is unchanged.

   Anything else is not guessed. Those rows stay unclaimed: they keep their
   records and become inactive, and the objects get new rows. Real data has
   such cases: two legacy rows can both read `M 7`, or `M 7` can move from
   one NGC row to another.
3. A row from the other OpenNGC file (main ↔ addendum) with the same `Name`
   key. This follows an object that moves between the two files.
4. Otherwise, a new row.

Shared or former names never establish identity. Real OpenNGC lists IC 1459
under NGC 7368 and NGC 7418 as well, and NGC 764's name is held by NGC 755.
Running pass 1 everywhere first also stops a name freed by a split from
claiming its old host. For example, NGC X was a duplicate of NGC Y and is now
listed on its own: Y keeps its row and records, and X gets a new row.

**First startup after the upgrade.** No row has a source key yet. Each object
source carries a `keys_assigned` flag. While any loaded object source with its
file present has the flag at 0, the loader runs the object step once, even
though no file changed. Normally the files still match the stored rows, so
every row pairs exactly by pass 2 and gets its key. The step then sets the flag, so rows left
unmatched (with no key) never trigger it again. This costs one startup of
about today's full-reload time. **Claude's call.**

**Missing catalog files.** A catalog can be loaded in the database while its
file is absent on this machine, for example a workspace opened on another
computer. A catalog counts as loaded when it has a `dso_catalog_source` row.
Loaders create that row only inside a successful load, never for a missing
file. Row counts don't decide it: a Sharpless load whose objects were all
merged has 0 rows but still contributed names. While any loaded object source
has no file, the object step does not run at all. Every object, designation and record stays as it is, and the
load summary says which file is missing. Enrichment still runs for its own
changes. Running the step with a catalog missing would mean guessing which
designations that catalog contributed. **Claude's call.**

### 1.5 Unclaimed rows: merged or removed

An existing row that no new object claimed is either merged or removed. Only
the catalog's own signals count as a merge:

- an OpenNGC duplicate row whose own name equals this row's source key,
  resolved to a surviving object;
- the Sharpless cross-reference mapping this row's Sh2 number (its source key)
  onto a surviving object.

A row with no source key is never treated as merged. Its records stay where
they are. **Claude's call.**

- **Merged.** The user's records move to the survivor:
  - **wishlist:**
    - the entry and its plans move. If the survivor is already on the
      wishlist, the plans move to the existing entry and the old entry goes;
    - if both have a plan for the same location, horizon and rig, they become
      one plan with the survivor's settings;
    - non-empty notes are joined, survivor's first, then `From {old
      designation}: {old notes}`. If any old setting differed, a line
      `From {old designation}, settings not kept: {name}={value}, …` is added;
    - date ranges are combined, and ranges that overlap or touch are merged
      into one.

    **Claude's call** (preserving old settings in the notes was proposed by
    Codex);
  - **main targets:** the target moves. If the same project already has the
    survivor as a target, everything that pointed at the old target row is
    re-pointed to the survivor's row before the old row is removed. At
    present that is sub-frames and source folders, but the code finds them by
    their foreign keys rather than from a fixed list;
  - **solved-field objects:** they move. If the solve already lists the
    survivor, it is kept once and stays a main object if either was one.

  Afterwards the old row is deleted only if nothing references it any more.
  That check covers every table with a foreign key to `dso`, found at run
  time, apart from the catalog-derived tables. Otherwise the old row is kept
  inactive and a warning is logged. This is a second line of defence in case a
  future table is forgotten. **Claude's call.**
- **Removed** (anything else). The row gets `active = 0` and keeps its
  records. Its former designations that no active object now holds are
  re-attached to it, so its detail view still lists its names. Removed rows
  are never deleted, even with no records. **Claude's call.**

A Sharpless object that a cross-reference used to merge and no longer does
becomes a standalone object again with a new row. Records made against the NGC
object stay on it.

### 1.6 What the object step writes

- **Kept on the row:** `id` and `created_at`. A matched row is set active again
  if it was inactive, which covers an object that reappears in a later catalog
  version together with its records.
- **Rewritten**, on claimed rows only: every column an object source owns,
  back to the source's own value, including `common_name` and
  `surface_brightness`. Only columns whose value differs are updated, and the
  augment flags (`common_name_augmented`, `surface_brightness_augmented`) on
  those rows are reset. The augment loader always runs after an object step and
  re-applies its overrides. This keeps the galaxy rule for surface brightness
  correct.
- **Not touched by the object step:** distances (`distance_pc`,
  `distance_method`) and anything on rows that become or stay inactive. Removed
  objects keep the names, brightness, distances and flags they had.
- **Each enrichment loader clears only its own values, on active rows only,
  inside its own transaction:**
  - augment clears curated distances and its flags, then re-applies;
  - 50 MGC clears 50 MGC and redshift distances, then fills empty ones;
  - redshift clears its own, then fills empty ones.

  A failure therefore leaves its previous values in place. A loader whose file
  is missing never runs and clears nothing. The precedence curated > 50 MGC >
  redshift holds: curated values are written unconditionally, and the other
  two fill only empty distances.
- **Designations and `primary_designation`:** rebuilt for all object rows in
  today's order (OpenNGC main and its duplicates, addendum and its duplicates,
  Sharpless, Barnard), with today's first-owner-wins rule for collisions.
  Nothing references designation rows.
- **Thumbnails:** cache keys are sky positions, so a moved object gets a new
  thumbnail and the old one ages out. No eviction.

### 1.7 When the loader runs what

- **The object step** runs when:
  - any object input's file hash changed;
  - a forced reload asks for it;
  - the one-time first-startup condition of §1.4 holds;

  and never while a loaded object source's file is missing. It is **one
  transaction**: if it fails, nothing changes.
- **Enrichment** runs in today's order: 50 MGC, Wikidata, editorial external
  references, then the redshift pass.
  - After an object step, all of it runs.
  - Otherwise it runs from the earliest changed enrichment source onward.
  - Before 50 MGC runs, both 50 MGC and redshift distances are cleared, so the
    precedence holds.
- **Invalidation is stored, not remembered.** A source that must re-run
  because something upstream changed has its stored file hash set to `''`:
  - the object step does this for augment and all enrichment, inside its own
    transaction;
  - an enrichment change does it for the later enrichment sources, just before
    they run.

  Every loader writes its real hash only when it succeeds. A stored `''` means
  "due again"; it is not a content change. So an invalidated augment re-runs
  augment and everything after it, but not the object step. A real change to
  the augment file runs the object step. A failure or a crash between steps
  leaves the source due at the next load, whatever triggered it, and whether
  the loader raised or returned "failed".
- **Startup:** as above.
- **Admin fetch buttons** (OpenNGC from GitHub, Sharpless, Barnard, 50 MGC,
  Wikidata) run the loader without force after downloading, so only what
  changed runs. **Fred** ("fetching one catalog stops reloading the others").
- **Admin "Reload"** (`POST /catalogs/reload`, force by default) and
  **NightCrate catalogs reload** keep their meaning, re-reading everything.
  They are now harmless. **Claude's call.**
- The per-source status in the load summary keeps its shape. A deferred object
  step reports each object source as `skipped`, with the missing file named.

### 1.8 Where removed objects appear

| Surface | Removed (inactive) objects |
|---|---|
| Catalog page list, search, facets; planner target list and search; "objects in this region"; new plate-solve object identification; augment designation lookup | hidden, as today |
| Planner target metadata (`_load_dso_metadata`) | filters `active = 1` too, so a visibility snapshot cached before a reload can't surface a newly removed object |
| Planner reads by object id: sky track, annual hours, single-target score, thumbnail | work as for any object |
| Object detail by id (`GET /api/dso/{id}`) | returned, marked inactive |
| Wishlist tab rows and calendar labels | shown with the short tag |
| Project main targets (Overview chips); project plate-solve objects | shown with the short tag |
| New wishlist entry, new main target (`POST /projects/{id}/targets` and marking a solve object as main, `PUT /projects/{id}/solve/objects/{dso_id}`) for an inactive object | refused with 409. Existing links can still be removed; plans for an existing wishlist entry can still be made and edited; marking an object main that already is one stays a no-op. **Claude's call.** |

The planner reads by id must keep working, because the wishlist's plan editor
and sparklines call annual hours, wishlist rows show thumbnails, and a planner
selection made before a reload survives it. A single-target score for an
object missing from the cached visibility snapshot is computed from a
one-object snapshot (time series included), with its own metadata lookup that
includes inactive objects. After every catalog load in the running app,
successful or not, the planner's visibility cache is cleared, so changed
coordinates and new objects show at once.

API responses that describe an object reached through a user record gain
`active: bool`: object detail, wishlist entries, calendar rows, project
targets, and identified solve objects. **Claude's call** on wording:
- in detail views, "No longer listed in {catalog}", where {catalog} is the
  source display name without its trailing parenthetical;
- in rows, a short "Not listed" tag.

Both are text, never colour alone.

### 1.9 Schema

One forward migration (0063):

- `dso.source_key TEXT` (NULL until the one-time object step).
- A unique index on `(source_catalog_id, source_key)` where `source_key IS NOT
  NULL`.
- `dso_catalog_source.keys_assigned INTEGER NOT NULL DEFAULT 0 CHECK
  (keys_assigned IN (0, 1))`.

`dso.active` already exists. Update `DB_SCHEMA_DDL.sql` and `DB_SCHEMA.md` for
these columns. `DB_SCHEMA_DDL.sql` already lacks the wishlist tables; adding
them is a separate docs fix.

### 1.10 Tests

The tests use small synthetic catalog files, no real catalog data. **Legacy
state** comes from a fixture captured with today's loader, before it is
changed. Loading with the new code and then clearing the keys would not
reproduce today's formatting or ownership.

**Reload behavior:**
- **Unchanged files:** a forced reload keeps every `dso.id` and every user
  record. A second run changes no column except `updated_at`.
- **Changed values:** new coordinates or magnitude keep the same id with the
  new values.
- **Removed and nonexistent rows:** inactive, records kept, designations
  re-attached. Reappearing later reactivates the row with its records.

**Merges and identity:**
- **OpenNGC duplicate merge**, for each record type, including the §1.5
  collisions (plans merged with notes, ranges and the settings line).
- **Sharpless cross-reference:** added (standalone → merged) and removed
  (merged → standalone).
- **Duplicates resolving out of order:** a forward duplicate (main → addendum)
  and a two-step chain both resolve.
- **Addendum → main move** keeps the id.
- **Freed names:** a former duplicate listed on its own again gets a new row.
  The object it was folded into keeps its id and records.
- **Shared names:** removing an object whose name another object also lists
  makes it inactive, with records kept.

**Upgrade and missing files:**
- **The one-time first-startup step** on the legacy fixture matches every row,
  including a prefix-less addendum row and a Barnard row whose designation lost
  a collision. It sets the flags and never runs again, even with an unmatched
  keyless row left.
- **Missing source file:** the object step is skipped and nothing changes. A
  source never loaded and absent never blocks it, across two runs.
- **Bootstrap against changed files:** pairing only on an identical
  catalog row. A legacy duplicate-text group (two `M 7` rows, one gone), and
  `M 7` moving from one NGC row to another, keep the old rows inactive with
  their records rather than guessing.
- **All-merged Sharpless:** a Sharpless load with no standalone objects whose
  file then goes missing blocks the object step.
- **Designation order:** an earlier row's alternate name still owns a later
  row's canonical name (`B 33`). An OpenNGC duplicate resolved through the
  addendum is final before Sharpless resolves against it.

**Failures and recovery:**
- **Rollback:** failures injected after designation deletion, after object
  updates, and after a user-record move each leave everything identical.
- **Invalidation:**
  - after an object step, a failing augment or enrichment loader (raised or
    returned "failed") runs again at the next load, as it does after a crash
    following the object commit, with the augment file unchanged;
  - an editorial pass that a Wikidata change triggered, and that then failed,
    also re-runs;
  - an invalidated augment does not run the object step.
- **Distance precedence:** a new 50 MGC distance replaces a stale redshift
  distance.
- **Surface brightness:** an object that becomes a galaxy loses its nebula
  override.
- **Removed objects keep their enrichment:** a removed object keeps its
  curated name, flags and distance. If it reappears after its augment entry
  was dropped, the curated distance goes.

**Load orchestration:**
- **Fetch routes:** changing the Wikidata file re-runs only Wikidata and the
  later sources. Changing Barnard runs the object step and all enrichment.
- **Guard test:** lists every foreign key to `dso` (from `PRAGMA
  foreign_key_list` on a fresh database). It fails if a table is neither
  handled by the merge code nor declared catalog-derived. A real synthetic
  table with a foreign key to `dso` keeps a merged row inactive.

**API:**
- `active` on each listed response, and 409 on each refused add or mark-main.
- Planner results exclude an object made inactive after its visibility
  snapshot was cached.
- Annual hours, sky track and thumbnail return real data for an inactive
  object. A single-target score for an object missing from a warm snapshot
  returns its computed visibility.
- After an object step, the planner shows changed coordinates.

### 1.11 Verification beyond tests (high-stakes)

- **Migration gate:** a copy of Fred's database at 0062 upgraded to 0064, and
  a fresh database. Integrity and foreign-key checks pass, and every row count
  outside `dso` is unchanged.
- **Real-data reload:** on that upgraded copy, the first startup runs the
  one-time object step with the real catalog files.
  - All 3 targets, 16 solved-field objects, 3 wishlist entries and 701
    sub-frame links stay, as do every `dso.id`.
  - Every row gets a key. The flags are set.
  - A forced reload afterwards changes nothing except `updated_at`.
  - The time is recorded against today's 13.8 s.
- **Rendered check:** a copy where one wishlisted, targeted object was made
  inactive shows the tag in the wishlist and project views, and the object is
  absent from catalog search.

## 2. Mirrored object overlays

### 2.1 Facts (measured, see the evidence record)

NightCrate draws images with row 0 at the top and uses WCS pixel coordinates
directly. FITS files are drawn as stored and their WCS used unchanged, which is
consistent. Two cases are not:

1. **XISF whose WCS is stored as FITS keywords.** PixInsight's
   `AstrometricSolution` properties are top-down and already read correctly.
   FITS WCS keywords inside an XISF count rows from the bottom, but
   `xisf_io.read_header` passes them through, and they also win key by key
   over the properties. On the NGC 7380 master, the overlay puts Sh2-143 at
   the bottom edge. It is actually just above the top edge.
2. **PNG, JPEG and TIFF files on disk solved with ASTAP.** ASTAP counts their
   rows from the bottom, and `_compute_results` stores its answer unchanged.
   The same image as FITS and as PNG, TIFF or JPEG gives
   `CRPIX2' = H + 1 − CRPIX2`, with `CD1_2` and `CD2_2` negated and the
   reported rotation 180° off. XISF, `.pxiproject` and archive entries go to
   ASTAP as a temporary FITS file and are already correct.

### 2.2 Changes

- **XISF, used for overlays and every other WCS use:**
  - **Properties present:** use them as one complete solution, never mixed key
    by key with FITS keywords.
  - **Only FITS keywords:** use them flipped to top-down: `CRPIX2' = NAXIS2 +
    1 − CRPIX2`, `CD1_2' = −CD1_2`, `CD2_2' = −CD2_2`. The CDELT/CROTA form is
    converted to CD first.
- **The CDELT/CROTA conversion is fixed for every format.** Codex found that
  `detect_wcs_from_cards` swaps the scales in the off-diagonal terms. The
  standard form is `CD1_1 = CDELT1·cos ρ`, `CD1_2 = −CDELT2·sin ρ`,
  `CD2_1 = CDELT1·sin ρ`, `CD2_2 = CDELT2·cos ρ` (Calabretta & Greisen
  2002). The existing test repeats the wrong formula. The fix is tested against
  astropy's own handling of the same CDELT/CROTA header.
  - The Header tab keeps showing the file's real keyword values.
  - This affects every caller that turns XISF header cards into a WCS: Image
    Analyzer annotation and the "From Reference Image" transfer. The plan lists
    the exact callers.
- **ASTAP on PNG, JPG, JPEG, TIF and TIFF files passed as-is:** flip CRPIX2,
  CD1_2 and CD2_2 as above, using the solved image height. This applies to
  Image Analyzer and project solves alike.
- **One rotation rule for corrected solutions:** `degrees(atan2(−CD1_2,
  CD2_2))` on the corrected matrix. That is ASTAP's own CROTA2 convention: on
  a raw ASTAP `.ini` it gives −152.343° against CROTA2 −152.335°, while the old
  fallback `atan2(CD2_1, CD1_1)` gives 27.660°. The same rule replaces the old
  fallback for any result without CROTA2. Results that are not flipped keep
  ASTAP's CROTA2 as today. Runtime and migration use the same formula, so a
  corrected solution has one rotation however it was produced.
- **Saved project solves:** forward migration 0064 corrects `crpix2`, `cd1_2`
  and `cd2_2` the same way. It touches only rows whose `image_path` ends in one
  of those extensions (case-insensitive) and contains no `::` (archive or
  project entries).
  - **Rotation:** recomputed from the corrected matrix with the rule above,
    whatever produced the stored value, so no guessing which formula did.
  - **Python migration:** SQL math functions depend on how SQLite was built,
    so 0064 is a yoyo Python migration, the first in the repository. yoyo
    9.0.0 supports it (checked by Codex). The test database bootstrap, which
    runs `.sql` files only, learns to run it too. The solved-object lists need no change:
  mirroring about the centre line keeps an object inside the frame if and only
  if it was inside before. Fred's database has no such rows. **Claude's call:**
  repair rather than asking for a re-solve.
- **`.pxiproject` images with FITS-keyword WCS:** probably the same as XISF,
  but no sample was available (the one solved project image has no WCS
  keywords). Left unchanged and listed as unverified. **Claude's call.**
- `docs/development-decisions.md`: replace "Real FITS WCS wins" in the XISF WCS
  rule with the above, and record the ASTAP row-order fact under plate solving.

### 2.3 Tests

- Synthetic WCS with an off-centre object at a hand-computed pixel position:
  - XISF FITS-keyword path, in both CD and CDELT/CROTA form;
  - properties-only XISF;
  - XISF with both: the properties win as a whole.
- `_compute_results` (or the code that now applies the flip) for a PNG path
  and a FITS path, using the measured relationship as the regression example,
  plus a result without CROTA2 on each path.
- CDELT/CROTA with unequal signed scales and ρ = 30°: both pixel coordinates
  of an off-centre object match astropy's answer for the same header.
- Migration 0064 on a database with one PNG, one archive PNG (`::`) and one
  FITS solve: only the PNG changes, and the values are exact.
- Rendered check after the fix: the NGC 7380 XISF and the same image as PNG
  solved in the app both show Sh2-143 at the top edge.

## 3. Planner: wishlist star on the open object

**Fred (2026-10-24):** the planner's detail panel gets the same wishlist star as
the target cards, planner only. Measured: `PlannerDetailPanel` is rendered only
by `PlannerPage`. `ProjectCatalogTab` mentions it only in a comment.

- Optional `isFavorite` and `onToggleFavorite` props, as on
  `PlannerTargetCard`. The star renders only when `onToggleFavorite` is passed,
  so a future caller gets no star by default.
- Same icons, colour (`RIG_ORANGE` on, `text.disabled` off) and aria labels as
  the card. It sits in the dialog title row, left of the close button.
  **Claude's call** on placement.
- It uses the page's existing `useFavoriteIds`, `useAddFavorite` and
  `useRemoveFavorite` wiring, so the card and the panel always agree.
- Rendered check in light and dark themes: toggling in the panel updates the
  card, and the reverse.

## 4. Process

High-stakes: migrations, bulk writes to user records, API contracts, and a
scientific calculation (WCS). Each gets the checks in
`docs/agent-collaboration.md` §5 and a fresh Codex review before Fred's
acceptance test.

Code is built in the worktree `../nightcrate-v042-wt`
(detached at 115f18f), because Fred's `make dev` server is still running from
the main checkout and would apply new migrations to his real database on reload.
The work is brought into the main checkout once he has stopped that server.

## 5. Out of scope

- The native plate solver (next version).
- Storing SIP distortion, and any other overlay accuracy work.
- Showing merge or removal history; repairing records already lost before this
  version.

## 6. Calls Claude made for Fred to check

Revised after the builder check and Codex's plan review. The record holds both.

1. **Merges.** Only the catalog's own merge signals count: an OpenNGC
   duplicate, or a Sharpless cross-reference. Shared or former names never
   establish identity or a merge, and a row without a key is never merged
   (§1.4, §1.5).
2. **Merged rows** are deleted only when nothing references them; otherwise
   they are kept inactive (§1.5).
3. **Colliding wishlist plans:**
   - the survivor's settings win;
   - notes are joined, and the old settings are listed in them;
   - date ranges are combined (§1.5).
4. **Removed rows** are never deleted, even with no records (§1.5).
5. **Missing catalog files:** while any loaded catalog's file is missing,
   object updates wait. Nothing changes until the file is back (§1.4).
6. **First startup after the upgrade:** one object step runs to set the keys
   while the files still match the database. It costs one slower startup:
   3.5–5 s measured on a copy of Fred's database (§1.4).
7. **Augment CSV changes** run the full object step, so the source's own names
   and brightness values come back before the overrides are applied again
   (§1.4, §1.6).
8. **No new links to removed objects:** no new wishlist entries or main
   targets for them. Existing links stay usable (§1.8).
9. **Wording:** "No longer listed in {catalog}" in full, and "Not listed" as
   the short tag (§1.8).
10. **Admin "Reload" buttons** keep their force behavior (§1.7).
11. **Saved mirrored solves** are repaired by migration, not by asking for a
    re-solve. The migration is the repository's first Python migration,
    because it needs `atan2` (§2.2).
12. **The CDELT/CROTA conversion** is fixed for all formats, and the rotation
    fallback follows ASTAP's convention (§2.2).
13. **`.pxiproject` FITS-keyword WCS** is left unchanged, for lack of
    evidence (§2.2).
14. **Star placement:** left of the close button (§3).
14a. **Bootstrap against changed catalog files** pairs only unambiguous rows.
     Ambiguous ones are kept inactive with their records (§1.4).
15. **Worktree:** code is built in a separate copy of the repository, because
    the dev server is running (§4).
