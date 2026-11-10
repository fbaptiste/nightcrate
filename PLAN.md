# NightCrate — active plan

**Version:** v0.48.0 — Messier checklist

**Branch:** `v0.48.0/messier-checklist`

**Status:** Complete — awaiting merge

## v0.48.0 — Messier checklist

Fred started this version on 2026-11-09, after merging v0.47.0. Its scope is
the roadmap's next item, the Messier checklist, moved here unchanged below,
plus the Planner project pill Fred added.

- [x] Start from updated `main` on `v0.48.0/messier-checklist`.
- [x] Spec: [v0.48.0 design](docs/superpowers/specs/2026-11-09-v0.48.0-design.md).
  Fred skipped the questions and asked for the spec, Codex's review and
  the design skill (2026-11-09). Claude's calls are listed at its end for
  his review. Mockups (`.superpowers/mockups/v0.48.0/messier.html`,
  local) show the page and the pill in both themes.
  - **Fred's addition (2026-11-09):** a pill on Plan a Night and Full
    Catalog cards for objects that are a main target of a project,
    opening the project or a list of them; not on the Wishlist.
  - **Codex's spec review** converged after three rounds (records
    `00`–`06`, local): no blocker; ten findings, all adopted. They made
    "Open in Planner" survive the Planner's first load, kept one project
    filling several slots from breaking the shared Gallery parts, and
    tightened the pill's refresh, the survey-image fallback and cache, and
    the "not downloaded" test. Codex first preferred deferring the header
    map, then accepted it as a picture only.
  - **Fred's changes after the review (2026-11-09):** the survey images at
    full strength with a light X over the whole tile; a map tooltip
    listing projects (only on boxes with one); a "Projects under images"
    switch; a Location picker under the title; a "Rig field" picker that
    draws the rig's field centred on each picture.
  - **Fred's addition after approval (2026-11-09):** "Imaged as" (own image
    or sky image) and arrows that step through the images of a slot's
    projects; approved from the mockup ("approved, go ahead and build
    it").
  - **Fred approved the spec and mockups** (2026-11-09: "approved, go
    ahead with the plan") and authorised the whole version up to, but not
    including, finalisation while he is at work, database changes
    included.
- [x] Implementation plan: [v0.48.0 plan](docs/superpowers/plans/2026-11-09-v0.48.0.md).
  Codex's plan review converged after two rounds (the plan's Codex review
  section). Its findings gave the survey-image cache one canonical key,
  made the pill's refresh explicit at each project change, and fixed the
  viewer for two tiles sharing one image.
- [x] Implementation (Codex, worktree `.superpowers/wt-v0.48.0`, detached
  at `6a04481`), with Claude's review of each phase (records `21`–`54`,
  local):
  - [x] A, backend: the Messier service and endpoint, the 4:3 survey
    variant with one canonical cache key, migration 0071, the project
    target links, six settings. One fix round (picture scale per
    project for the arrows, two simplifications). Claude's checks: 362
    tests across the new and affected modules, ruff, format, bandit 0;
    0071 on a copy of Fred's database at 0070: all 88 tables' counts and
    the 1,121 cache rows unchanged, integrity ok, no foreign-key
    violations.
  - [x] B, frontend: the Gallery's tile pieces shared with a separate
    entry identity, and the Messier page. Two fix rounds: Serpens shown as
    "Se1"/"Se2" everywhere (a bug from before this version: OpenNGC's
    codes for Serpens Caput and Cauda, now named in both name lists),
    unnamed pickers, images released while the page was hidden, image
    readiness, pinning the default location, the shown-project dot.
  - [x] C, Planner: the project pill and its refresh at every project
    change (call sites audited), and "Open in Planner". Claude fixed one
    defect: an inline query `select` put the Planner in a re-render loop
    ("Maximum update depth exceeded"); a copy of `main` run against the
    same data showed no such error.
  - [x] Independent review (fresh Codex session, whole change): no blocker
    or major; three minors, all fixed in B's second round.
  - [x] Rendered checks (headless, private servers, a copy of Fred's
    database plus 500 synthetic projects with Messier targets): every
    state in both themes and three tile sizes; arrows; the map tooltip;
    turning and focus; the viewer stepping M 31 → M 32 on one image;
    blank and sky styles; the rig box against hand-computed sizes (M 101's
    real solve, a portrait solve, a matching export with framings,
    "Scale unknown"); a southern location marking M 40, M 52 and M 103;
    the Planner pill, its menu and its failure line; "Open in Planner" on
    a first visit and with the Planner open; the Gallery unchanged.
  - [x] **Brought into the main checkout** (2026-11-09, Fred's
    authorisation of database changes): the reviewed 53 files, staged. A
    backup of his database at 0070 was taken first
    (`.superpowers/tmp/v048/`, local). His dev server applied 0071: all 88
    tables' counts and the 1,121 cache rows unchanged, integrity ok, no
    foreign-key violations; both new endpoints answer.
- [x] Fred's look at the built version.
  - [x] **First look (2026-11-09):** opening M 101 full size took about a
    minute. Every tile he scrolled past kept asking for its survey image,
    and those requests filled the browser's six connections to the
    server; the full-size image waited behind them. Now at most three
    survey requests run at a time, nearest the visible part first, and a
    tile scrolled away cancels its request. With an empty survey cache,
    scrolling to M 101 and opening it took 0.24 s.
  - [x] **Fred's change (2026-11-09):** the controls moved beside the
    progress map, and the header stays on screen while the tiles scroll
    (mockup first). A compact form keeps the three areas side by side on
    narrower windows and iPads in landscape; below that, two rows.
    Codex built both (records `55`–`63`, local); Claude's rendered
    checks: the header lines up with the tiles from 960 to 2,300 px;
    216 px tall at Fred's width, 231–238 px in the compact form (349 px
    before it); keyboard focus and the viewer's return never leave a
    tile under the header; scroll position kept on return; nothing
    requested while the page is hidden; dark mode; the map tooltip and
    menus above the header.
- [x] Candidate preparation (2026-11-09, Fred: "please continue and
  finalize"):
  - version 0.48.0 in `VERSION`, `backend/pyproject.toml` and `uv.lock`;
    documentation synced (README, code map, development decisions, schema
    documents and their version headers);
  - checks: ruff, format, bandit (0 issues), the frontend build, ESLint on
    every changed frontend file (one warning in `PlannerPage.tsx`,
    unchanged from `main`). Full backend suite: 3,816 passed, 4 skipped,
    1 failed. The failure was `test_migration_0066`: it upgrades to the
    newest migration and compared whole rows, so 0071's new column broke
    it. It now compares the columns that existed before (Claude). The
    rig-field helper gained direct tests for incomplete rigs (Claude);
  - coverage: the Messier service 98%, its endpoint 99%; the modified
    modules no lower than on `main` (thumbnails 49% → 66%, planner API
    89% → 92%, on the same tests);
  - a final fresh Codex review of everything since the first review: no
    blocker, one major (loaded survey images dropped by the refetch on
    each visit) and three minors, all fixed and checked in a browser;
  - privacy scan of the staged diff: no personal details, ignored files
    or `instructions/`.
- [x] Fred's acceptance of the candidate (2026-11-09: "finalize").
- **From the start sweep (2026-11-09):**
  - v0.46.0-D1, the single rig list on gallery cards and in the filter:
    its named check, the v0.47.0 spec, is done. v0.47.0 kept one identity
    per rig, so a project no longer lists an old and a new rig; still
    pending (the v0.46.0 plan's Codex review section). It bears on this
    spec if a checklist card reuses the gallery card's back.
  - v0.46.0-R1 (one workspace per request) stays deferred to
    Distribution's design; v0.47.0-R1 and R2 wait on checks outside this
    scope. No new evidence, and nothing is overdue.
- **Still due from earlier versions:**
  - the CDS checks under v0.43.1 ("When CDS returns"). CDS's Strasbourg
    VizieR and tile servers still timed out on 2026-11-09;
  - the iPad/Safari check of v0.46.0's framing dialog: dragging the frame,
    and the long-press tooltip.

### Scope (Fred, 2026-10-24)

- 110 numbered slots from an explicit checklist mapping, separate from catalog
  designations; one designation can belong to only one object. Since v0.45.0
  M 102 names NGC 5866, so the catalog has 110 numbers on 110 objects.
- A slot is filled only by a project with that object among its main targets
  and a main image. The latest project wins, by latest session date: dated
  projects before undated ones, then creation time, then ID. The back of the
  card lists the other projects.
- Empty slots distinguish "no project" from "a project without an image".
- M102 is NGC 5866 (Fred, 2026-11-03, a reviewed `assign` override in
  v0.45.0); keep a note on the historical ambiguity in the checklist.

## v0.47.0 — Rigs in use don't change underneath their records

Merged in [PR #26](https://github.com/fbaptiste/nightcrate/pull/26) on 2026-11-08.

Fred started this version on 2026-11-07, after merging v0.46.0. Its scope is
the roadmap item he placed next on 2026-11-07, moved here unchanged below.
The spec comes next, decided with Fred one question at a time.

- [x] Start from updated `main` on `v0.47.0/rigs-in-use`.
- [x] Spec: [v0.47.0 design](docs/superpowers/specs/2026-11-07-v0.47.0-design.md),
  from Fred's answers on 2026-11-07. Claude's calls are listed at its end
  for his review. Mockups (`.superpowers/mockups/v0.47.0/rigs-and-software.html`,
  local) show the seven screens in both themes.
  - **Fred's additions (2026-11-07):**
    - a project can change a rig for itself only;
    - software versions, and the software used on each project;
    - SyQon's four programs.
  - **Fred's answer on "from now on":** no cutoff date ("let's keep it
    simple").
  - **Changed after review:** a fresh review of the first draft against
    the code found that storing earlier setups and project changes as
    extra rigs would break calibration matching, move old frames after a
    project change, and leak hidden rigs into lists. Earlier setups are now
    attached to the rig, and project changes stored as swapped parts.
  - **Fred approved the spec and mockups** on 2026-11-07 ("approved, go
    ahead with the plan").
- [x] Implementation plan: [v0.47.0 plan](docs/superpowers/plans/2026-11-07-v0.47.0.md).
  Codex's plan review converged after three rounds on 2026-11-07 (see the
  plan's Codex review section). Its findings made the stored history
  sturdier: setups survive untagged folders, re-derives and moves between
  rigs, and the guide camera follows the rig when a project swaps its
  guider. The spec was amended to match. One small addition to the
  approved mockup: rigs a project used but doesn't list appear as "Also
  used on this project's nights" chips.
  - **Fred approved the plan** on 2026-11-07 ("yes, go ahead and build
    it").
- [x] Implementation (Codex, worktree `.superpowers/wt-v0.47.0`, detached
  at `4020f5e`), with Claude's review of each part:
  - [x] A1: migration 0069 and the rig-setup service (Tasks 1–2).
    Accepted after one fix (records `07`–`10`): the prompt's night count
    now includes nights from untagged folders in a one-rig project.
    Claude's checks: 16 module tests and 120 migration, schema and
    calibration tests; ruff, format and bandit clean. 0069 on a copy of
    Fred's database: counts unchanged, integrity ok, no foreign-key
    problems.
  - [x] A2: rig API and records (Tasks 3–4), records `11`–`14`. Codex
    stopped once, correctly: the handoff left out three files the work
    needed (router registration and two model files). Claude's checks: 375
    tests across rigs, setups, ingest, sessions, derivation and plate
    solving; ruff, format and bandit clean. The frame list is 5–6.5%
    slower on a 2,400-frame library (budget 20%). Focal estimates still
    read capture batches only; moved to A3, where the project-setups
    function covers frames.
  - [x] A3: project setups, equipment usage, software (Tasks 5–7), records
    `15`–`18`, accepted after one fix round:
    - the equipment usage count took 919 ms on the 503-project library;
      rewritten with grouped queries, now 6 ms;
    - a duplicate version gave a misleading message, and swapping two
      version names failed.
    Claude's checks: 455, then 301 tests; ruff, format and bandit clean.
    The SyQon rows are in the seed files. A handoff named a test module
    that starts MLX inside the sandbox; it aborted once (the reason for
    the §10 rule), so later handoffs leave it out.
  - [x] Phase A gate and a fresh independent Codex review (records
    `19`–`23`). The review found no blocker:
    - moving a night to another setup left that night's darks, flats and
      bias behind (major); fixed, with a calibration-matching test;
    - bad parts input gave a server error (minor); now a clear 422.
    Full backend suite on the worktree (Phase A as reviewed, before those
    two fixes): 3,756 passed, 10 skipped, 0 failed. The fixes' modules: 100
    passed.
  - [x] Phase B, frontend (Tasks 8–11), with rendered checks (records
    `20`–`32`). Claude drove every screen in a headless browser on
    private servers with a copy of Fred's database migrated to 0069, in
    both themes, against the mockups. Fixed in three rounds:
    - near-invisible borders and fields in dark mode, a guiding toggle in
      capitals without the amber selection, no "Use the rig's" link;
    - dates as "Nov 8, 2026" instead of "8 Nov 2026"; versions added in
      one save stored in reverse; a read-only Software field;
    - the night move offered only setups the project already used (now
      every setup of the rig, through a new `setup_options` field);
    - the Sessions table wrapped and clipped with the Setup column;
    - the prompt counted 5 nights where the change touched 8: stale
      derived batches with no frames left were left out of the count;
    - an existing React key warning in the rig form's pickers.
    Checked live: the prompt and "From now on" (529 frames and 29 batches
    stamped), the earlier-setups list, the correction dialog, the
    equipment usage note, versions, the project setup panel with one and
    two setups, a guiding change for one project, project software with a
    version, moving a night (147 frames and 6 batches), "Also used on this
    project's nights" chips, and the setup named in plate-solve estimates.
    The SyQon programs were seeded into the copy at startup. After the
    last round: 44 backend tests, ruff, format, bandit and `npm run build`
    pass. All 74 files are staged in the worktree.
  - [x] **Brought into the main checkout** on Fred's "yes, bring it in"
    (2026-11-08): 74 files, identical to the reviewed worktree, now
    staged. A backup of his database at 0068 was taken first
    (`.superpowers/tmp/v047/`, local). His dev server applied 0069: every
    record count unchanged (15 rigs, 3 projects, 1,232 frames, 30 batches,
    45,436 objects), the four SyQon programs added (48 programs),
    integrity ok, no foreign-key violations.
  - [x] Phase C docs (Task 12, Claude, 2026-11-08): a "Rig history and
    project setups" section and the software, seed-link and calibration
    rules in the development decisions; the v0.47.0 tables and views and
    the software diagram in `DB_SCHEMA.md`; seed counts and keys (67
    manufacturers, 48 programs, checked against the CSVs) and the new
    user-data tables in `LLM_DB_SPECS.md`; the code map; README features.
    140 local links resolve; `git diff --check` clean.
- [x] **Fred's first look** on his own dev server, which now runs v0.47.0.
  - **Chip spacing** (Fred, 2026-11-08: "Too close to each other", the
    Software and Rigs fields). Chips in both fields, and the "Also used"
    chips, now have a 6 px gap between chips and rows (shared
    `components/projects/chipRow.ts`), so the open chip's outline no
    longer touches its neighbours. Claude's fix; checked in a browser,
    ESLint, type check and `npm run build` pass; staged.
- [x] **Candidate preparation** (Fred: "ok, continue", 2026-11-08, after his
  first look; Prepare only, no commit).
  - Version 0.47.0 in `VERSION`, `backend/pyproject.toml` and `uv.lock`,
    and in the headers of `DB_SCHEMA.md`, `DB_SCHEMA_DDL.sql` and
    `LLM_DB_SPECS.md`.
  - **Checks (Claude, main checkout):**
    - full backend suite: 3,768 passed, 4 skipped, 29 warnings (45 min).
      The 4 skips are v0.46.0's (missing star data and XISF fixtures); the
      worktree run's 10 skips were fixtures absent from the worktree. The
      suite started before the last fix round; its modules were re-run
      after it: 100 passed;
    - ruff check and format: clean (376 files);
    - bandit: 0 issues at any severity;
    - `npm run build`: passes; ESLint clean on every changed file (the
      repository's 7 errors in the touched folders are in files this
      version didn't change);
    - 140 local doc links resolve; `git diff --check`: clean; a privacy
      scan of the staged additions found nothing personal.
  - **Coverage of the new and changed backend modules,** from their tests:
    `services/rig_setups.py` 92%, `api/rigs.py` 88%, `api/project_sessions.py`
    93%, `services/session_derivation.py` 97%, `api/equipment_factory.py`
    95%, `seed_loader/loader.py` 86%. The two new route files were at 65%
    and 71%: the undo endpoint and the 404 paths had no tests, now added.
  - **Reviews before Fred's acceptance test:**
    - a fresh independent Codex review of the frontend and the later
      backend changes (`33`, `35`). One blocker: "Correct this setup" from
      the project panel started from the project's own view of the setup,
      so saving would copy its changes into a setup other projects share.
      Three majors and a minor: retired equipment and programs vanishing
      from the parts pickers (the rig form's software picker already did
      this before v0.47.0), the session nights in the prompt's count, and
      Escape committing a version rename. All fixed (`37`–`38`), except an
      undated-frame finding the schema rules out (v0.47.0-R3);
    - a batched Codex review of Claude's docs and the chip-spacing fix
      (`34`, `36`): one major (v0.47.0-R2: untagged frames still match
      calibration across a camera change, as before; the docs now say so)
      and two minors, fixed.
- [x] **Project Overview layout** (Fred, 2026-11-08, before his acceptance
  test: "Plate solved location seems random. Clicking on a rig to see the
  details all the way below is not user friendly."). Claude mocked two
  layouts with the design skill (`overview-layout.html`, local); Fred chose
  option A, with Integration moved under the description ("yes, go ahead
  with option A"):
  - beside the picture: main targets with the plate-solve line under them;
    imaging dates and nights, location, "Processed with" (the project's
    software); the description; integration per filter;
  - below: an Equipment section, one row per rig with its camera, image
    scale, field of view and nights; a row opens the setup panel directly
    under the rig list; a rig used but not listed is tagged in its row.
  - Claude's calls, accepted with it: the "Imaged" line drops the total
    (Integration shows it); a long description shows six lines, then "Show
    more"; declared rigs get a remove button in their row.
  - This changes the prepared candidate: affected checks and Fred's renewed
    acceptance follow.
  - **Built** by Codex in the main checkout (records `39`–`42`), with one
    fix round from Claude's rendered checks (both themes, 1280 and 1680 px
    windows, real-data copy): an earlier setup shown in a rig row without
    saying so, redundant "before" lines, the setup panel opening below the
    fold, software chips stacking one per line, a pale "+ Add software", a
    description clamp cutting a line in half, and an Emotion selector
    warning. Claude's own narrow fix: in a narrow side column, "Processed
    with" sits above its chips so they can use the full width.
  - Checks: `npm run build` passes; ESLint clean on every changed file; no
    console errors; frontend only, so the backend checks above stand.
- [x] **The other project tabs** (Fred, 2026-11-08, before his acceptance
  test: "see if there's room for improving each of the other tabs").
  Claude mocked a main design and an alternative for each tab
  (`tabs/project-tabs.html`, local); Fred chose every main design, in this
  version. Spec: "The other project tabs"; plan: "Amendment — the other
  project tabs".
  - **Fred's decisions (2026-11-08):** add a note per night that survives
    rebuilding (migration 0070); no "high" label on frames; frames sort by
    capture time by default.
  - Codex's plan review (one round, nine findings, all adopted): capture
    times sorted as instants, physical totals instead of passband credits,
    a block kept for a note whose night has no batches, the night on
    correction responses, and the quality states kept in the table.
    **Fred approved the plan** ("Start building").
  - **Built** by Codex in the worktree (Phase D backend, E1 Sessions and
    Notes, E2 Files and Plate Solve), each with a fix round from Claude's
    rendered checks on a copy of Fred's database upgraded to 0070:
    - Sessions: one block per night with a sub-heading per rig; the setup
      picker showing "Now"; filters ordered Ha, OIII, SII, then RGB;
    - Files: the table fitted to a 1280 px window with 33 px rows; header
      alignment; the folder row at narrow widths; unused card code removed;
    - Plate Solve: the focal-length and objects tables' proportions.
  - Checked live: night notes added, saved and opened from the Notes tab;
    585 frames over 10 pages under three night headings with no gaps or
    repeats; shift-click selection; sorting by HFR; thumbnails; both
    themes at 1440, 1280 and 800 px. The frame list answers in 5–10 ms
    for 60 or 600 frames. 0070 on the copy: every record count and the
    batch, stamp, project and frame tables unchanged, integrity ok, no
    foreign-key violations.
  - **Independent review** (fresh Codex session): no blocker. Fixed: the
    Others tab's selection mixed file and frame ids, so a shared id could
    remove the wrong item (older than v0.47.0, fixed now); unknown-type
    frames had lost their thumbnail; a Shift-click anchor survived a sort
    change. Rejected: touch zoom on the saved plate-solve image, which
    never had it (v0.47.0-R4); Fred: "no pinch zoom on tablet is fine."
  - **Brought into the main checkout** on Fred's "Yes, bring it in"
    (2026-11-08), after the full suite passed on the worktree: the
    reviewed tree, unchanged. A backup of his database at 0069 was taken
    first (`.superpowers/tmp/v047/`, local). His dev server applied 0070:
    every table's record count unchanged, projects, frames, capture
    batches and project software identical, integrity ok, no foreign-key
    violations. The one difference was his own rig save during the
    upgrade (Fred: "that was me"): the same filters, re-saved.
  - **Checks:** full backend suite on the worktree with this exact tree:
    3,782 passed, 10 skipped (fixtures absent from the worktree), 0 failed
    (47 min). In the main checkout: ruff and format clean (380 files),
    bandit 0 issues, `npm run build` passes, `git diff --check` clean, and
    a privacy scan of the additions found nothing personal.
- [x] **Fred's acceptance test** (2026-11-08: "accepted, please finalize so I
  can merge the PR").
  - Fred, 2026-11-08: hover explanations for "Change for this project
    only" and "Edit rig", and "Edit rig" as a button like the other.
    Claude's narrow fix in the project's rig setup panel: all three
    buttons there (with "Undo the project change") are outlined, each
    with a hover note drafted by Codex and checked against the code.
    ESLint clean, `npm run build` passes, checked in a browser.
  - **Filter colours** (Fred, 2026-11-08: SII was blue though it is the
    reddest, and L, R, G, B all grey). Claude mocked an Okabe-Ito palette
    in wavelength order (`filter-colours.html`, local), checked with the
    dataviz colour-vision validator; a mid grey for L was dropped because
    it matched G for green-weak vision. Fred added dual-band filters with
    SII, then approved: "colors look good, please implement". Built by
    Codex (records `64`–`65`): the Sessions chips, rows and night bars, the
    Overview's Integration bars and the Files tab's chips and Filter
    column; equipment dual-band filters are split between their lines'
    colours. Checked in a browser in both themes on the private copy (two
    dual-band batches added there); ESLint clean, `npm run build` passes.
    Order, Fred after seeing it: L, UV/IR and no filter first, then R, G,
    B, then narrowband from red to blue; the exposure table follows it;
    a dual-band swatch now shows its red line first (Claude's narrow
    changes, checked in a browser).
  - Also open: the iPad/Safari check of v0.46.0's framing dialog.
- **Found in passing:** one of Fred's projects has three derived capture
  batches on a rig with no frames left on it, the known "stale derived
  rows" limit (development decisions, sessions). They now count in the rig
  prompt's nights, because the Sessions tab shows them.
- **From the start sweep (2026-11-07):** v0.46.0-D1, the single rig list
  on gallery cards and in the filter, bears on this spec. After a rig is
  saved as a new one, a project can list both rigs.
- **Closed at the start:** the live HASH (V/163) add and remove under
  v0.44.0. Harvard serves V/163 again, and the check passed on a copy of
  Fred's database (the v0.44.0 plan's Codex review section).
- **Still due from earlier versions:**
  - the CDS checks under v0.43.1 ("When CDS returns"). CDS's Strasbourg
    VizieR and tile servers still didn't connect on 2026-11-07;
  - the iPad/Safari check of v0.46.0's framing dialog: dragging the frame,
    and the long-press tooltip.

### Scope (Fred, 2026-11-07)

Projects, sessions, frames and source folders point at a rig, and a rig
points at its equipment. Swapping a rig's camera therefore changes every
project that lists it, along with pixel scale, field of view, star sizes in
arcseconds and the plate-solve focal length. Fred: "it should not."

- **Fred's choice (2026-11-07):**
  - changing the equipment on a rig that is in use asks whether to **save
    it as a new rig**, so older records keep the old one, or **correct it
    everywhere**, for a mistake, after showing what it affects;
  - name and notes edits stay free;
  - the project page opens each rig's details in a panel.
- **Rejected:** copying rig values into each project.
  - The copy covers only projects, not sessions or frames.
  - It repeats equipment details, so corrected specs never reach them.
  - Rig versions were also offered; they are the most work.
- **For the spec:**
  - what counts as "in use";
  - what "correct it everywhere" lists;
  - names for a saved-as-new rig, which must be unique;
  - whether edits to an equipment record's own specs need the same choice.

## v0.46.0 — Gallery

Merged in [PR #25](https://github.com/fbaptiste/nightcrate/pull/25) on 2026-11-07.

Fred started this version on 2026-11-04, after merging v0.45.0. Its scope is
the roadmap's next item, the gallery, moved here unchanged below. The spec
comes next, decided with Fred one question at a time; the first is whether
to ship it in two parts.

- [x] Start from updated `main` on `v0.46.0/gallery`.
- [x] Spec: [v0.46.0 design](docs/superpowers/specs/2026-11-04-v0.46.0-design.md).
  Fred skipped the questions ("skip questions and proceed", 2026-11-04), so
  its decisions are Claude's calls, listed at its end for his review. A
  mockup (`.superpowers/mockups/v0.46.0/gallery.html`, local) shows the page
  in both themes.
- [x] Implementation plan: [v0.46.0 plan](docs/superpowers/plans/2026-11-04-v0.46.0.md).
  Codex's plan review converged after five rounds on 2026-11-04.
  - Most of its findings were in the Projects page image fix, which grew:
    - browsers stop caching project images;
    - a crop save changes everything or nothing;
    - a crop is deleted with the image it depends on.
  - Two disagreements are for Fred: the rig filter (v0.46.0-D1) and the
    Complete label (D2).
- [x] Fred's approval of the spec, mockup and plan (2026-11-04): "yes",
  with changes.
  - every project gets a card ("No main image" when it has none);
  - clicking the back of a card turns it back;
  - an expand button opens each image full size;
  - no Complete label;
  - a status choice on the project page. Nothing could set status, so all
    of his projects were Active.
  - On the rig filter he kept Claude's single list (D1).
- [x] Implementation (Tasks 1–6, Codex in a separate worktree,
  `.superpowers/wt-v0.46.0`). Started on 2026-11-04 (Fred: "ok, go ahead and
  start building"). Claude reviewed each handoff (records `14`–`25`) and
  re-ran its checks outside the sandbox.
  - Task 1 (project images): accepted first time; 148 tests.
  - Task 2 (gallery backend): one fix round. The workspace script copies
    with SQLite's backup API, and the synthetic library gained plate
    solves and 3–10 sessions per project. 205 and then 86 tests.
  - Tasks 3–5 (gallery page, cards, viewer): one fix round:
    - the scroll position was lost on return;
    - the code was reformatted from very long lines;
    - title-case view buttons and a single "Sort by";
    - new nav routes are now placed after their default neighbour, so
      Gallery sits after Projects in a saved order.
  - Task 6 (project page): accepted; 181 tests.
  - The code is staged in the main checkout. Fred's dev server loaded it:
    his three projects appear in the gallery, and his old crop files are
    still served.
- [x] Claude's checks and docs (Task 7). Next: Fred's first look on his own
  dev server, then candidate preparation (version bump, full backend suite,
  sync-docs) for his acceptance test.
  - [x] **Speed:** `GET /api/gallery` median 16–23 ms on a scratch copy of
    Fred's database with 503 projects (3,272 sessions, 153 plate-solved
    projects). The cases: no filters, three filters, designation, name,
    group and no-match searches, and "M1" and "NGC" with plate-solved
    projects. The budget is 200 ms.
  - [x] **Rendered checks** on private servers (8001 and 5174), in both
    themes, against the mockups:
    - views, turning cards by mouse and keyboard, the hidden face out of
      the accessibility tree, reduced motion;
    - the viewer's fixed arrows (the same pixels across six steps), its
      counter and focus return;
    - rendition choice at 1× and 2×, the solved-image search markers, "To
      is before From", the empty state, 1024 px width;
    - scroll and turned cards on return, nav placement;
    - the project page's status chip, plate-solved pill, and Description
      and Notes headings.
  - [x] Fresh independent Codex review (records `26`–`27`): no blocker or
    major finding. All four minor findings were fixed (records `28`–`31`):
    crop source id 0; the expand-ref cleanup; a failed status change now
    says why; line fitting re-measures on a size change.
  - [x] **Found by Claude's rendered check after the review, and fixed:**
    - target and date lists never wrapped, so the "+N" pill never
      appeared; the separator sat inside the no-wrap span;
    - the project page's main image and its thumbnail strip spun forever
      when a rendition was missing. They now say "No preview".
  - [x] Re-checked in the browser:
    - 8 targets show four names and "+4" in medium, all eight in large;
    - the project page shows "No preview" with no spinners;
    - the main checkout's staged code is identical to the reviewed
      worktree.
  - [x] Docs: a Gallery section in development decisions, README
    features, and the code map.
  - Fred's later review changes are in the spec's "Decisions for review"
    list:
    - the solved-image search ("Also search plate-solved projects");
    - imaging dates by month;
    - the viewer's arrows;
    - the project page's pill, description heading and status chip.
- [x] **Fred's first look (2026-11-07): additions.** Planned in the spec's
  2026-11-07 amendment and the plan's Task 8. Fred approved the plan the
  same day.
  - Fred approved the framing and picker mockup (`framing.html`, local) the
    same day: "mock looks good".
  - Codex's plan review, round 1 (records `33`–`34`): four major and two
    minor findings, all real, all adopted:
    - a race that could turn a new crop into a follow-the-main crop;
    - a missing crop file making the tile and the viewer disagree;
    - the focal length's rig list, now computed on the server;
    - page weight on the Projects page;
    - temporary-file cleanup;
    - the picker's null selection.
  - Round 2 converged with four minor refinements; Fred then said "yes,
    build it all".
  - **Implementation** (records `38`–`64`): Codex built each phase in the
    worktree; Claude reviewed it and re-ran its checks outside the sandbox.
    - **8a, backend:** accepted first time; 213 tests.
    - **8d, editor:** two fix rounds:
      - a blank image picker;
      - a saved frame not restored after a reload (an impure state
        updater);
      - a development-only update-depth error under fast key repeat,
        traced to MUI `FormControl`.
      - Checked by mouse, keyboard, emulated touch and touch cancel, with
        save, reopen and failed-save retry.
    - **8b, migration and gallery data:** accepted. 0068 on a copy of
      Fred's database removed its 6 old crops and kept everything else;
      integrity and foreign keys are clean.
    - **8c, pickers, Projects page, gallery:** one fix round. Unframed
      portraits overflowed their 4:3 boxes. Near-viewport loading checked:
      22 of 457 cards on first load. `/api/gallery` takes 20–25 ms.
    - **8e, focal length and tooltip:** accepted.
      - On a copy of Fred's data, one rig's estimate matched its focal
        length within 0.2%.
      - Another came out at almost exactly twice the rig's value, the
        pattern a 2× drizzle gives.
  - Independent Codex review of Task 8 (`61`–`62`): no blocker. Two major
    and one minor finding were sent back as fixes (`63`–`64`):
    - "Whole picture" during a slow load;
    - estimates not refreshed after a project's rigs change;
    - estimates not refreshed after a rig reorder.
  - [x] **Brought into the main checkout** on Fred's "yes" (2026-11-07):
    40 code files, identical to the reviewed worktree, now staged.
    - His dev server applied 0068: 6 old crops removed; 3 projects,
      6 images and 30 sessions unchanged.
    - The live solve response includes the new estimates.
    - Old crop files stay on disk until each project's next successful
      thumbnail save sweeps them.
  - [ ] **The iPad/Safari acceptance check:** dragging the frame (WebKit isn't
    available to Playwright here), and the long-press tooltip. Still due
    under v0.47.0.
  - [x] **Framed thumbnails.**
    - The gallery uses each project's custom thumbnails, one framing per
      size. Fred: "that was the whole reason for defining the customizable
      thumbnails."
    - All three sizes become 4:3, shared by the Projects page, whose square
      boxes become 4:3.
    - A frame may extend onto a black mat, so a portrait image can fill a
      4:3 tile with black at its sides.
    - Existing crops are cleared.
  - [x] **Bug found while planning, fixed by the above:** the editor
    enforces each size's shape in the image's proportions, not its pixels,
    so saved crops are squashed. Seen on Fred's data: an 800×403 image's
    "square" crop is a 2:1 area squeezed into 180×180.
  - [x] **View pickers:** icon buttons on both pages, with the selected one
    filled. The Projects page's "Gallery" view becomes "Pictures".
  - [x] **Plate-solve focal length:** calculated from the solved pixel scale
    and each project rig's camera pixel size, beside the rig's own focal
    length.
  - [x] **A tooltip on the "+" beside Main targets:** add targets here, or
    plate solve and choose from the objects found.
- [x] **Candidate preparation** (Fred: "please finalize", 2026-11-07, before
  his acceptance test, so this is Prepare: no commit).
  - Version 0.46.0 in `VERSION`, `backend/pyproject.toml` and `uv.lock`, and
    in the headers of `DB_SCHEMA.md`, `DB_SCHEMA_DDL.sql` and
    `LLM_DB_SPECS.md`.
  - **Checks (Claude, main checkout):**
    - full backend suite: 3,691 passed, 4 skipped, 29 warnings (38.7 min);
    - ruff check and format: clean (364 files);
    - bandit: 0 issues at any severity;
    - `npm run build`: passes;
    - 126 local doc links: none broken; `git diff --check`: clean.
  - **Coverage of the changed backend modules,** from their tests:
    - `api/gallery.py` and `api/project_models.py`: 100%;
    - `services/gallery.py`: 99%;
    - `rig_calculators.py`: 94%;
    - `api/project_solve.py`: 91%;
    - `api/projects.py` and `services/project_images.py`: 89%.
  - **Reviews:**
    - **Task 8:** an independent Codex review, with all three findings
      fixed.
    - **Claude's docs:** a batched Codex review (`65`–`66`). Two major and
      three minor findings, all fixed:
      - stale pre-amendment text, now marked superseded;
      - personal hardware mentions removed;
      - the cleanup trigger and distortion claims made precise;
      - the helper's name.
  - **Fred accepted the candidate** on 2026-11-07 ("finalize please"), which
    authorized publication.
    - He didn't report the iPad/Safari drag check, so it stays open in the
      PR.
- [x] **Published** as [PR #25](https://github.com/fbaptiste/nightcrate/pull/25)
  on 2026-11-07 (tag `v0.46.0`), and merged the same day.
- **Found in passing (kept, with reasons):** every endpoint reads the
  global database path, so a workspace switch during a request can mix two
  workspaces in one response (v0.46.0-R1). A wrong image can't be cached
  now, and fixing the race is a cross-cutting change. Raise it with
  Distribution's design.
- **Still due from earlier versions:**
  - the CDS checks under v0.43.1 ("When CDS returns");
  - the live HASH (V/163) add and remove under v0.44.0.

### Scope (Fred, 2026-10-24)

One page of finished images, possibly shipped in two parts: list and grid views
first, then the slideshow.

- **Cards.** One card per project, showing its main image. Several targets
  appear as labels on one card. Projects without targets still appear; retired
  projects are hidden by default.
- **Views.** A list of small thumbnails beside the project details; grids of
  small, medium and large thumbnails; a slideshow. Clicking an image in the grid
  or the slideshow flips it to a back with basic project details.
- **Filters.** Name or designation, catalog (through any designation), object
  type group, constellation, status, rig and imaging dates.
  - "Imaged between" means at least one session date falls in the range.
    Projects without session dates show when no date filter is set, with an
    "include unknown dates" option alongside one. No other date substitutes for
    a missing session date.
  - The default sort is latest session, with unknown dates last. `updated_at`
    is never an imaging date.
  - Integration filters and sorts wait until the manual/derived session overlap
    (see Later) is resolved; until then, totals can count the same subs twice.
- **Data.** One batched endpoint selects and sorts on the server; the views
  present the result.
- **Images.** The main image's aspect-preserving renditions (180/400/800 px);
  the slideshow uses the full image and preloads its neighbours. Whether to use
  the project's custom crops instead is decided in the spec. Fix cache busting
  first: thumbnail URLs are versioned by `project.updated_at`, which does not
  change when the main image or crops change.
- **Flip cards.** A labelled control that also responds to Enter and Space. The
  hidden face is out of the focus order, reduced motion swaps without rotating,
  and "Open project" is a separate control.
- **Slideshow.** Starts paused. Previous, next, play and pause, with ←, →, Space
  and Esc. Pauses on hover or focus, on a flipped card, and when hidden. Key
  handlers act only in the visible view, because persistent routes stay mounted.
- Test with a synthetic library of several hundred projects.

## v0.45.0 — Common names for galaxies and nebulae

Merged in [PR #24](https://github.com/fbaptiste/nightcrate/pull/24) on 2026-11-04.

Fred started this version on 2026-11-03, after merging v0.44.0. Its scope is
the roadmap item he placed next on 2026-11-03, moved here below, plus one
licence for everything in NightCrate.

- [x] Start from updated `main` on `v0.45.0/common-names`.
- [x] **One licence** (Fred, 2026-11-03: "let's just make everything in
  nightcrate the same license"). NightCrate's own catalog data in
  `backend/src/nightcrate/data/catalogs/nightcrate/` moves from MIT to
  GPL-3.0-or-later, like the code since 2026-10-26.
  - **Changes:** the CSV headers, `version.json`, the registry's source
    licences, the Catalogs page, the tests and the docs; `LICENSE-MIT.txt`
    is removed.
  - **Kept:** `LICENSE-CC0.txt` and other notices that describe third-party
    data (Wikidata, the xkcd colours).
  - **Earlier releases:** v0.12.0–v0.44.0 keep their MIT data.
  - **Authorship:** Fred is the only author of every commit to those
    files.
  - **Consequence for sources (verified 2026-11-03 on Creative Commons'
    compatible-licences page):** CC BY-SA 4.0 is one-way compatible with
    GPLv3, so material from Wikipedia (CC BY-SA 4.0) could be adapted with
    attribution. Whether to use it is a spec question.
  - **Done 2026-11-03, staged.** Codex implementation (records `01`–`04`):
    it stopped once, correctly, over the cross-reference sources. Those turned
    out to have no stored row, so there was nothing to update.
  - **Checked by Claude:** 480 targeted tests, ruff, ruff format and bandit
    (no medium or high findings), and `npm run build`. On a copy of Fred's
    database, one load records GPL-3.0-or-later for all six NightCrate
    sources (3.4 s, a one-time rebuild because the files changed), and a
    second load does nothing (0.21 s). The Catalogs page shows the new
    licence in a headless browser.
- [x] Spec: [v0.45.0 design](docs/superpowers/specs/2026-11-03-v0.45.0-design.md).
  Fred skipped the questions ("skip questions and proceed", 2026-11-03), so
  its decisions are Claude's calls, listed at its end for his review.
- [x] Implementation plan: [v0.45.0 plan](docs/superpowers/plans/2026-11-03-v0.45.0.md).
  Codex's plan review converged after three rounds on 2026-11-03, with every
  finding adopted. Fred added star clusters and a hover tooltip with the
  other names on every result name. He approved the spec and plan on
  2026-11-03 ("yes, approved, proceed").
- [x] Implementation (Tasks 0–5). Codex works in a separate worktree,
  because Fred's `make dev` applies migrations as soon as they appear in the
  main checkout.
  - [x] Task 1, migration 0067: checked on a copy of Fred's database. 20 comma
    names were split exactly; ids, links, integrity and foreign keys were
    unchanged.
  - [x] Task 2, names in the object step: one rebuild on upgrade (about 5 s),
    then no rebuild (0.25–0.37 s).
  - [x] Task 0, the names list: 225 names for 188 objects and groups, plus
    three removals (247 for 203 after Fred added the single-source names).
    - Each name has two independent sources: SIMBAD, NED, Wikidata or
      Wikipedia, and agency and society pages. The pages were fetched and
      checked for the name and the designation.
    - Single-source names went to Fred, and Codex checked them
      independently.
    - Fred decided the Cone, Elephant's Trunk, Fly, Lobster Claw and
      Spindle names and the three removals, and moved M 102 to NGC 5866.
    - Details: [names review](docs/superpowers/plans/2026-11-03-v0.45.0-names-review.md).
  - [x] Tasks 3 and 4, search, API, tooltips and panels: checked in a
    headless browser on a copy of Fred's database. Search costs 6–8 ms more
    in the catalog and nothing measurable in the planner, within the budget.
  - [x] Fix round 1: M 102 → NGC 5866 (an OpenNGC duplicate row ignored the
    override), and the name tooltip on the catalog table's designation cell.
  - [x] Independent Codex review: no blockers. One major fixed in round 2 (a
    missing augment file no longer blocks the object step). The 0067
    rollback finding was declined as Claude's call, for Fred to confirm. See
    the plan's Codex review section.
- [x] **Verification:**
  - the full backend suite: 3,576 passed, 4 skipped;
  - after fix round 2, the catalog tests: 510 passed;
  - ruff, ruff format and bandit (no medium or high findings), and
    `npm run build`;
  - on Fred's own database: 0067 applied by his dev server on 2026-11-04,
    234 named objects, 87 other names, no commas, M 102 = NGC 5866,
    integrity ok.
- [x] **Fred's acceptance test.** He asked to publish first ("please
  continue and finalize this version so I can review tomorrow morning",
  2026-11-04), then accepted it on 2026-11-04 ("accepted, please get PR
  ready for me to merge it").
- [x] **Checks before merge (Claude, 2026-11-04):**
  - the full backend suite: 3,586 passed, 4 skipped;
  - ruff, ruff format and bandit (no medium or high findings);
  - the review record's tracked items have their status at merge;
  - the development decision on keyboard access corrected (names in the
    grid have no tab stop since the PR review fixes).
- [x] **Published** as [PR #24](https://github.com/fbaptiste/nightcrate/pull/24)
  on 2026-11-04 (tag `v0.45.0`).
- [x] **PR review fixes** (Fred, 2026-11-04: fix all ten findings, keep the
  0067 rollback as it is, and add the 22 single-source names on his word).
  - The list now holds 247 names for 203 objects and groups.
  - Codex fixed the eight code findings in a separate worktree (records
    `30`–`31`).
  - **Verified by Claude:** 782 targeted tests, ruff, ruff format and bandit
    (no medium or high findings), and `npm run build`. The shipped list
    passes the stricter source rule. Fred's dev server loaded the fixes on
    his database: 246 named objects, 95 other names, integrity ok.
  - [x] Task 5, docs: schema, development decisions, catalog architecture,
    README and the code map.
- [x] **Two rows off the Catalogs page** (Fred, 2026-11-04: "yes, remove
  both in this version"). "NightCrate editorial augmentation" and "NightCrate
  external refs (editorial overrides)" had no actions, and the page intro
  already says NightCrate's own lists come with the app. The sources still
  load and are still listed by the API.
  - Codex removed them (records `32`–`33`).
  - **Verified by Claude:** `npm run build`, and the page on Fred's dev
    server shows neither row; the other rows and "Reload all from local
    cache" are unchanged, with no console errors.
- **Still due from earlier versions:**
  - the CDS checks under v0.43.1 ("When CDS returns");
  - the live HASH (V/163) add and remove under v0.44.0.

### Scope (Fred, 2026-11-03)

**Why.** Many popular imaging targets have no common name, so they can't be
found by name. Checked on a copy of Fred's database on 2026-11-03: NGC 891,
NGC 3628 (Hamburger Galaxy), IC 342 (Hidden Galaxy), NGC 5907 (Splinter
Galaxy), NGC 4656 (Hockey Stick), Sh2-129 (Flying Bat), Sh2-132 (Lion),
LBN 437 (Gecko), LBN 777 (Vulture Head) and IC 1795 (Fish Head) have none.
Only 20 of 370 HII regions and 49 of 10,521 galaxies carry a name; most of
those galaxies are faint and never had one.

**Sources.** No scraping of other sites: GPL covers NightCrate's code, not
their data. A single name is a fact, but copying a site's list copies its
compilation, sites such as Telescopius and AstroBin forbid scraping, and
Wikipedia's lists are CC BY-SA, which would carry over to NightCrate's data
files (the reason the Melotte list is NightCrate's own). *Revisit:* with
the data under GPL-3.0-or-later, CC BY-SA 4.0 material can be adapted with
attribution (see "One licence" above).
- **Claude drafts the list** from its own knowledge, marking how sure it is
  of each name.
- **Every name is verified** against at least two independent sources
  (SIMBAD's `NAME` identifiers, Wikidata, NASA, ESA or NOIRLab pages,
  observatory pages), with the sources recorded. A name that can't be
  confirmed stays out or goes to Fred. Claude's memory is fast but can put a
  real name on the wrong object.
- **Wikidata** (CC0) is a second source and catches objects the draft
  misses. It is not imported blindly: on 2026-11-03 it gave Sh2-129 the name
  "Squid Nebula", which belongs to Ou 4, a separate object inside it.

**Several names per object.** Today each object holds one common name, but
NGC 891 has two (Silver Sliver, Outer Limits). Every name should be
searchable, with one shown first. This needs a schema change.

**Open for the spec:** how names are shown and ranked; the file format and
licence for the reviewed list (GPL-3.0-or-later, like the rest of
NightCrate, from this version); whether Wikidata names are fetched at
runtime or reviewed into the shipped list; which object types and how many
names are in scope.

## v0.44.0 — More deep-sky catalogs and search links

Merged in [PR #23](https://github.com/fbaptiste/nightcrate/pull/23) on 2026-11-03.

Fred started this version on 2026-11-02, after merging v0.43.1. Its scope is
the roadmap item he placed next on 2026-11-01, moved here unchanged below.
The spec comes next, decided with Fred one question at a time.

- [x] Start from updated `main` on `v0.44.0/more-catalogs-and-search-links`.
- [x] Spec: [v0.44.0 design](docs/superpowers/specs/2026-11-02-v0.44.0-design.md),
  written from Fred's decisions and approved by him on 2026-11-02.
  One version, built in stages. Fred added a planner fix: Tonight's
  magnitude and size limits show what is applied.
- [x] Implementation plan: [v0.44.0 plan](docs/superpowers/plans/2026-11-02-v0.44.0.md).
  Codex's plan review converged after five rounds on 2026-11-02, with every
  finding adopted. Fred approved it on 2026-11-02 and removed the supernova
  remnant catalog: Green's table can't tell visible remnants from radio-only
  ones. LBN 191 now gives the whole Cygnus Loop.
- [x] Implementation, reviews, rendered checks and Fred's acceptance test.
  - [x] Phase A, the shared parts (A1–A10). Staged on 2026-11-02 after
    Codex implementation, independent Codex reviews and Claude's review of
    each handoff. Checked on copies of Fred's database: upgrade, loads,
    Barnard removal and re-add, live downloads, and the Catalogs, catalog
    and planner pages in a browser.
  - [x] Phase B, the ten catalogs (B2–B10; B1 removed). Staged on 2026-11-02.
    Each catalog had a match screen on its full download (20 reviewed
    overrides in all), an independent Codex review, and an add, remove and
    re-add on a copy of Fred's database, all live through the mirrors except
    HASH (see "Still due"). Two contract additions (a size gate and
    `require_match`) and a batched constellation lookup came out of review.
  - [x] C2 performance measured (plan's Codex review section). With every
    catalog on (49,289 objects), the planner pages run 2.5–3× today's
    times, against the plan's 2× rule. Fred accepted them with the
    candidate on 2026-11-03.
  - [x] C3 docs: catalog architecture, development decisions, README data
    sources, schema docs and the code map.
  - [x] Acceptance follow-ups on mirrors (Fred, 2026-11-03): every
    download started with Strasbourg, which has been down for weeks.
    - All mirrors are now checked at once before a download, and those
      that don't answer are skipped for an hour. Tokyo, Beijing and India
      join over plain HTTP.
    - A failed download says, in plain words, what each mirror did, and
      names the failing part of a multi-table catalog; the message no
      longer squeezes the row.
    - Checked live on a copy of Fred's database: HASH fails in 15 s (about
      45 s before) with the full explanation; LBN added from South Africa
      in 4.8 s.
  - [x] Acceptance fix (Fred, 2026-11-03): Plan a Night listed "Emission
    nebula (8)" but showed nothing. A type, catalog or constellation with
    nothing up tonight showed its catalog-wide total instead of 0 (since
    April 2026). Now the counts are tonight's, and a zero-count value is
    hidden unless selected. Checked in a browser on a copy of Fred's database.
  - [x] Acceptance change (Fred, 2026-11-03): one "Emission nebula" type
    choice covering OpenNGC's `HII` and `EmN`; `HII` objects read "Emission
    nebula (HII region)", and the catalog table's Type column widens to fit.
    Codex implementation, Claude's review; checked in a browser on a copy of
    Fred's database (planner list, saved selection, cards, catalog filter).
- [x] **Fred's acceptance test**, accepted on 2026-11-03 ("ok, I think this
  is good, please finalize") after the list of open decisions below; the
  planner timings, "Part of LBN 191" and the two calls stand as built. The
  checklist (start `make dev`; on first start it migrates the database to
  0066 and reloads the catalogs once):
  - **Catalogs section of Admin:** add a few catalogs, e.g. LBN, Melotte
    and Wolf-Rayet; remove one; add it back. Check the remove dialog's
    counts.
  - **Search:**
    - "LBN 437", "LBN 777", "Melotte 20", "Mel 15", "Cygnus Loop", "WR 134",
      "Arp 244";
    - check the "Part of" pills and the details panels' "Part of" and
      "Includes" chips.
  - **Planner:**
    - Plan a Night opens with the brightness and size boxes ticked, with
      their captions;
    - Full Catalog opens unticked;
    - picking a catalog leaves the boxes alone.
  - **Object panels:** the "Google search" and "Google Images" links.
  - **Decisions:**
    - the C2 planner timings (in the plan's Codex review section);
    - "Part of LBN 191" versus showing "Cygnus Loop";
    - the two calls in the Codex review section.
- [x] **Published** as [PR #23](https://github.com/fbaptiste/nightcrate/pull/23)
  on 2026-11-03 (tag `v0.44.0`).
- [x] **PR review fixes** (Fred asked for all ten findings and any speed-ups,
  2026-11-03). Codex implemented them, then Claude reviewed and measured them
  on a copy of a real database (45,436 objects). A fresh independent Codex
  review followed.
  - **Catalogs:**
    - Sharpless and Barnard no longer show "Files missing" on a fresh
      install.
    - MCG names are spelled one way ("MCG +07-02-016").
    - The Catalogs page names all six mirrors.
    - One unreadable Arp row no longer stops every catalog.
    - Two endpoints check that a database is set up.
    - Removal runs one dry run fewer (7.0 s to 5.3 s).
    - "Part of" groups can't collide with catalog groups.
    - File checksums are cached.
    - Partial MCG and PN G searches ("MCG-1-2") match.
  - **Startup:** a repair check fired on every start because of the Pease 1
    override, rebuilding every object: 4.1 s instead of 0.27 s.
  - **Planner:**
    - Transit times used J2000 RA and came out 1–2 min early (7 min near the
      pole). They now use apparent coordinates, in the snapshot and the sky
      track.
    - Tonight went from 1.43 s to 0.29 s, the first Tonight request from
      3.9 s to 1.2 s, and Anytime from 0.39 s to 0.24 s.
    - Review finding 7 (planner metadata) alone measured at 13 ms; the fix
      reads coordinates and metadata once.
- **Still due:**
  - the CDS checks under v0.43.1 ("When CDS returns");
  - a live HASH (V/163) add and remove: of the mirrors, only Strasbourg
    and Harvard carry it. Strasbourg is unreachable, and Harvard's VizieR
    returned HTTP 502 for every request on 2026-11-02 and 2026-11-03. The
    code path is tested with fixtures and the full sample.

### Scope (Fred, 2026-11-01)

**Why.** NightCrate loads only OpenNGC, Sharpless and Barnard in full. Other
catalogs appear only as alternate names on those objects, so popular targets
with no NGC, IC or Sharpless number are missing. For example, LBN 437 (the
Gecko Nebula), LBN 777 (the Vulture Head) and Melotte 15 (the cluster in the
Heart Nebula) return nothing (checked 2026-11-01).

**Catalogs to load in full (Fred):**

Researched 2026-11-01 (background agent; VizieR tables downloaded from the
Harvard and IDIA mirrors and counted against each catalogue's ReadMe):

| Catalog | Source | Size | In NightCrate today | Notes |
|---|---|---|---|---|
| LBN (Lynds 1965) | VizieR VII/9 | 1,125 | 93 as alternate names | B1950 to 1′, J2000 computed by VizieR; size, brightness 1–6; 740 rows are parts of complexes |
| Melotte (1915) | no catalogue table anywhere found | 245 | 7 | 233 are NGC/IC objects (Mel 15 is IC 1805); 6 new objects need positions; the only full list is Wikipedia (CC BY-SA) |
| LDN (Lynds 1962) | VizieR VII/7A | 1,791 | none | area and opacity, no size; 233 rows name Barnard objects |
| Abell planetary nebulae | inside the PN G catalogues | about 64–86 | none | NightCrate's `abell` name holds no data today |
| ACO, Abell galaxy clusters | VizieR VII/110A | 5,250 (4,076 + 1,174 southern "S") | none | no size or total magnitude; display as "ACO 2151" so it can't clash with Abell nebulae |
| APG, Arp (1966) | VizieR VII/192 | 338 entries, 592 member galaxies | none | an Arp number is a view of several galaxies (182 have two or more) |
| HH, Herbig-Haro | VizieR V/104 (Reipurth 1999) | 454 | none | over 1,000 now known; the 2026 catalogue (1,193) is CC BY-NC-ND, so unusable |
| PN G, planetary nebulae | VizieR V/163 (HASH) or V/84 (Acker 1992) | 3,973 Galactic (HASH) or 1,143 | none | OpenNGC's 129 PN G alternate names are dropped by NightCrate's name parser today |
| MCG | VizieR VII/62A + VII/100 | 30,637 | 7,553 as alternates | about 23,000 new, mostly faint; sizes are in 0.1′ units |
| ~~SNR (Green 2024)~~ | VizieR VII/297 | 310 | none | **Removed by Fred on 2026-11-02:** no optical-detection flag, so radio-only remnants would join tonight's list |
| WR, Wolf-Rayet stars | VizieR III/215 (van der Hucht 2001) | 226 | none | Crowther's current catalogue (718) has no licence or download; WR 2-1 and WR 21 collide in today's search keys |

**Terms.** VizieR data is "free of usage in a scientific context" with the
authors cited; commercial use depends on the origin; none of the ReadMes
states a copyright. Each user downloading at runtime, as Sharpless and
Barnard work today, is the safe model; shipping rows would need Fred's
decision.

**Each catalog is optional (Fred, 2026-11-01).** The user downloads only the
catalogs they want, each on its own from the Catalogs page, and can remove
one later. Constraints from today's rules (`docs/development-decisions.md`,
"Projects, catalog, and sessions"):
- A loaded source with a missing file currently defers the whole object step
  rather than guessing. A catalog the user removed must be told apart from
  one whose file went missing.
- Removing a catalog removes its names and the objects only it provides.
  Objects the user has linked (project targets, the wishlist) stay, inactive
  with their names, as catalog preservation already does.
- Objects that another catalog also provides (LBN 667 is IC 1848) keep that
  catalog's entry.
- Open for the spec: whether OpenNGC, Sharpless and Barnard also become
  removable.

**What it takes (to be researched for the spec):**
- a source, its terms and a fetcher per catalog (most through VizieR's
  mirrors), with J2000 positions;
- a migration for the new catalog names (HH, ACO, PN G, WR) and object
  types (Herbig-Haro object, galaxy cluster, Wolf-Rayet star), with matching
  loader changes;
- matching against objects NightCrate already has (many LBN and PN G
  entries are NGC, IC or Sharpless objects), so nothing appears twice;
- planner and catalog behaviour for tens of thousands of faint objects
  (MCG, ACO): filtering, scoring and thumbnails;
- credits in README and the attribution panel.

**Search links.** The catalog and planner object panels already link to SIMBAD
and Wikipedia (`DsoExternalRefs`, shared by both). Add Google search and Google
Images links for the object, as Telescopius does. The query wording is decided
in the spec.

## v0.43.1 — Sky images from tiles, faster downloads, processed finals

Merged in [PR #22](https://github.com/fbaptiste/nightcrate/pull/22) on 2026-11-02.

Fred started this version on 2026-11-01, after merging v0.43.0. Its scope is
the roadmap's v0.43.1 items plus two responses to the CDS outage. CDS's
Strasbourg services have been unreachable since about 2026-10-21, when the
University of Strasbourg suspended its web services over a security flaw.

- [x] Start from updated `main` on `v0.43.1/sky-tiles-and-downloads`.
- **Order (Fred, 2026-11-01):** the CDS work first, because the outage is
  current. Catalog thumbnails cannot be fetched, and the Sharpless and
  Barnard downloads fail.

### 1. VizieR mirror fix

**Checked 2026-11-01** with full Sharpless and Barnard downloads:
- Strasbourg times out.
- Harvard (`vizier.cfa.harvard.edu`) and IDIA South Africa
  (`vizier.idia.ac.za`) work over HTTPS and returned identical rows.
- Tokyo and Beijing answer over plain HTTP only.
- Pune and Moscow time out.
- Canada and Cambridge UK are no longer on CDS's mirror list.

**NightCrate's fallback fails.** Its three hosts are Strasbourg, Pune and
`vizieridia.saao.ac.za`. The last is now an alias whose certificate fails
HTTPS. Each dead host takes about 7 minutes to skip: 3 retries × 2 attempts ×
the macOS connect limit of about 75 s.

**Fix (Claude, a narrow fix):**
- `catalog_loader/vizier.py`:
  - hosts Strasbourg → Harvard → IDIA, HTTPS only;
  - one pass over the mirrors, relying on `http_client.get`'s single retry
    (drop `retry_with_backoff` here; the GitHub fetchers keep it);
  - a 10 s connect timeout within the 180 s total;
  - `version.json` records the URL that served the data;
  - the error names every host tried.
- `services/http_client.py`: an optional `connect_timeout`.
- **Text and docs:**
  - the Admin text in `CatalogsAdminSection.tsx`;
  - `docs/dso-catalog-architecture.md`;
  - a short VizieR/CDS entry in `docs/development-decisions.md`.
- **Tests:**
  - `test_vizier_fetch.py`: primary succeeds; primary cannot connect; short
    body; all fail;
  - `test_http_client.py`: `connect_timeout`.
- **Status:** implemented and checked by Claude (2026-11-01), accepted
  by Fred (2026-11-01). A small extra: a response that isn't a VizieR TSV, such
  as an HTML error page served with HTTP 200, now moves on to the next
  mirror instead of failing the fetch.
  - **Checks:** ruff, format and bandit (no issues); 256 tests in
    `tests/catalog_loader`, `test_http_client.py` and `test_admin_api.py`;
    `npm run build`.
  - **Live check** (2026-11-01): the real fetcher, with a private HOME and a
    scratch catalogs folder, during the outage. It did not go through the
    API, which needs a configured database; the endpoint's tests cover that
    wrapper.
    - **Sharpless:** Strasbourg was skipped after two 10 s connect timeouts,
      and Harvard served it in 21 s. 313 rows parsed, all with J2000
      positions.
    - **Barnard:** Strasbourg was skipped. Harvard then returned HTTP 200,
      sent nothing, and closed after 60 s. Three separate tries did the
      same, though it had served Barnard in 0.5 s that morning. IDIA served
      it, 82 s in all. 349 rows parsed, all with positions.
    - `version.json` names the mirror that served each file.

### 2. Sky images from tiles

**Decision (Fred, 2026-11-01).** NightCrate assembles its catalog and
planner sky images itself from the DSS2 colour HiPS tiles, instead of asking
CDS's hips2fits service for finished images.
- Tiles come from CDS first, and from ESA's copy when CDS is down.
- hips2fits has no mirror outside Strasbourg. Its backup, alaskybis, is in
  Strasbourg and failed with it.

**Prototype (Claude, 2026-11-01).**
- **Method:** 12 cached planner cells, four per tier, compared with the
  cached hips2fits renders. They include one 3° from the north pole, RA
  0/360 crossings, and the ±41.8° HEALPix base-cell boundary.
- **Source:** ESA's copy (`cdn.skies.esac.esa.int/DSSColor`) names
  `ivo://CDS/P/DSS2/color` as its source. Its release date is 2019-05-07,
  and it is marked `hips_status = public mirror unclonable`.
- **Geometry:**
  - One in-tile pixel rule orients all 12 cells. It matches HiPS 1.0 figure
    4 and the standard's note that JPEG rows run top-down.
  - Position is within 0.02 px.
  - The tile-order rule matches what hips2fits used: the coarsest order
    whose pixels are no larger than the output pixels.
- **Match (bilinear sampling):**
  - correlation 0.88–0.99 with hips2fits;
  - mean brightness within 0.6/255 in 8 cells, and 1–1.3 in 3;
  - about +5 on the near-pole background, where an ESA cell beside cached
    CDS cells shows as a faint lighter square.
- **Per planner cell:**
  - 10–13 tiles (0.6–1.9 MB), against one 56–93 KB hips2fits JPEG;
  - about 0.5–0.9 s cold and about 0.2 s with the tiles cached, against
    about 2.3 s from hips2fits, measured earlier;
  - a tile cache saves about 40% of downloads across a 3×3 block.
- **Not compared:** catalog thumbnails, because none were cached.
- **Files:** the script, report and comparison images are in
  `.superpowers/prototypes/2026-11-01-esa-sky-tiles/` (local, ignored).

**Status:** implemented (Codex), reviewed and checked by Claude; accepted by
Fred (2026-11-01). Spec and plan:
[design](docs/superpowers/specs/2026-11-01-v0.43.1-design.md) §1,
[plan](docs/superpowers/plans/2026-11-01-v0.43.1.md) Phase A.
- `services/hips_tiles.py` replaces `services/hips_client.py` (hips2fits)
  for both catalog thumbnails and planner cells. There is no red-survey
  fallback.
- At most 32 tiles per image; a source that times out is skipped for 10
  minutes; tiles are kept in a 64 MB memory cache only; at most 4 renders at
  once. Failed images retry after 10 minutes (was 1 hour).
- **Checks (Claude, 2026-11-01):**
  - live overlay against Gaia stars: median 0.21–0.62 px over 12 cells,
    including both poles, ±41.8°, the RA wrap and a face corner;
  - with CDS down: the first render waits about 5 s for the CDS probe, then
    about 0.2 s per render from ESA;
  - 45 renders at once in 7 s, with 178 MB of memory growth;
  - the Planner and catalog pages render the new images.

**When CDS returns (Fred asked for this reminder).** These checks do not
block the spec, because the source order stays one constant.
- Compare CDS's and ESA's tile download speeds, and settle the source order.
- Compare CDS's current `hips_release_date` with ESA's copy, to explain the
  brightness difference.
- Confirm CDS's tile address.
- Read CDS's HiPS usage rules, which were unreachable during the outage.

### 3. Faster star download

Fred's acceptance download of Siril's star file (1.14 GB) ran at about
0.66 MB/s. Zenodo is its only host; no mirror was found. On 2026-10-30 Fred
chose to download it in four parallel pieces, in v0.43.1 rather than in the
v0.43.0 candidate.

- **Measured on 2026-10-30** (range requests, data discarded):
  - one connection: 0.77 MB/s, about 25 minutes for the file;
  - four in parallel: 2.36 MB/s, about 8 minutes;
  - eight in parallel: 4.33 MB/s, each still at 0.5–0.7 MB/s.

  A single connection later reached 2.83 MB/s, so Zenodo's speed varies.
- Four pieces rather than eight keep the load modest on a free service.
- Keep resuming after an interruption, progress, cancel and the SHA-256
  check. Fall back to one connection when the server doesn't return the
  requested range.
- **Also (Fred, 2026-10-30): an already-built range in a build request.**
  Codex's review of the v0.43.0 acceptance fixes (record `77`, minor) found
  that a request naming an already-built range makes it `current_range`.
  `/status` then reports it as building at 100% until it publishes, which
  can wait on an active solve. The Admin page never sends one, because it
  leaves built ranges out.
  - Fix: leave already-built ranges out of the build, but still publish a
    range whose layers are ready and whose manifest entry is missing; give
    `built` precedence in `/status`.
  - Test it through the API: a request including a built range reports that
    range as built while another range builds.

**Status:** implemented (Codex), reviewed and checked by Claude; accepted by
Fred (2026-11-01). Design §2, plan Phase B.
- A request naming only built ranges is refused: "Those ranges are already
  built." (HTTP 422).
- A v0.43.0 partial download resumes as one stream; new downloads use four
  pieces.
- **Checks (Claude, 2026-11-01),** live against Zenodo with a private HOME:
  - four pieces at 6–8 MB/s combined;
  - cancel after 40 s stopped at once, keeping the pieces;
  - resume continued from exactly the bytes kept (269.6 MB);
  - completion joined the pieces, matched the SHA-256, unpacked and
    installed, leaving staging empty: 292 s in all.
- The independent review found that a second cancellation could release
  the operation while its thread still ran, and that much of the spec's
  crash and cancel test list was missing. Both were fixed; the same
  cancellation defect was fixed in the sky-image renderer.

### 4. Stellarity filter for processed finals

**Decided by Fred on 2026-11-01** (proposed by Claude on 2026-10-30). The
built-in solver still fails 10 corpus finals and a mosaic.
- **Finding:** in the IC 1805 final, only about 40% of the brightest
  detections are stars. Nebula knots and stars shrunk by star reduction
  crowd them out. The NA Nebula final, which now solves, matched 72%.
- **Decision:** a stellarity filter that rejects extended sources by shape
  and width against the image's typical star. Measure it on the corpus and
  the false-match trials, with no change to the acceptance thresholds.
- **Why not in v0.43.0:** it changes the search design, and v0.43.0 was
  ready. The failure screen points to the stacked image meanwhile.
- **Open:** for the M106 JPEG and the mosaic, the detections barely line up
  with ASTAP's unconfirmed solutions under any flip. That needs its own
  check.

**Status:** implemented (Codex), reviewed and checked by Claude; accepted by
Fred (2026-11-01). Design §3, plan Phase C.
- **Rule:** before choosing the brightest detections, drop any detection
  more than 6 times wider than the median detection. Every solve profile
  uses it. The thresholds are unchanged.
- **Why 6:** the agreed rule takes the least restrictive limit that gains
  solves repeatably with no losses. 4, 5 and 6 all qualified. Codex held
  to the rule when Claude proposed 4, and Claude agreed.
- **Corpus (149 images), shipped code:** `native` 132 → 134 and
  `native-blind` 128 → 132; the IC 1805 final, and the NGC 6888, IC 1396 and
  IC 443 crops. Nothing lost, no wrong solution, no negative solved.
  - Every new solve was checked independently, against ASTAP or a Gaia
    overlay.
  - The real-sky trials never call extraction, so they were not rerun.
- **Remaining limit (Codex review):** if real stars were more than 6 times
  wider than most detections (for example, badly defocused stars among
  compact artefacts), the cut would drop them. The corpus has no such case.
- Still failing: 8 finals and the mosaic, including M106.

### 5. Fetch progress on the Catalogs page (added during acceptance)

**Requested by Fred on 2026-11-01** during his acceptance test. His Sharpless
re-fetch spun for minutes while Strasbourg and Harvard failed and the South
Africa mirror served it, with nothing saying it was working.
- **Scope (Fred):** every fetch and reload button on the Catalogs page shows
  a line saying what it is doing now: trying a source, moving to a mirror,
  downloading, loading into the catalog.
- **Design:** spec §7. The catalog load also has to leave the server's main
  loop, which it blocks today, or the status could not be answered during
  it.
- **Status:** implemented (Codex), reviewed and checked by Claude, with a
  fresh independent review; accepted by Fred (2026-11-01). Checked live: a
  Sharpless re-fetch showed "Trying CDS Strasbourg… n s", "Strasbourg timed
  out. Trying the Harvard mirror… n s" and "Sharpless loaded."; leaving the
  page, a second tab and failed status polls all recover.

### 6. Bugs found during this version (Fred, 2026-11-01)

Fred: bugs found during a version are fixed in it when they can be. Spec
§8 lists the fixes: local fetch dates; cached images surviving a moved
app-data folder; one shared image-cache budget, with "Clear All" and the
statistics covering both caches; no traceback from star-data status without
a database; the solver's cancellation waits; and no database switch during
a catalog action. **Status:** implemented, reviewed (fresh independent
review) and checked; accepted by Fred (2026-11-01). A copy of a real app-data
folder kept all 2,965 cached sky cells after moving. Also fixed: the
attribution dialog's raw UTC timestamps and the Caches line's code text.

### 7. Catalog table sorting (Fred, 2026-11-01, acceptance test)

Header clicks alternate ascending and descending; designations sort by
catalog then number (M 1, M 2 … M 10), and a single-catalog view shows and
sorts by that catalog's own name (Fred chose this, 2026-11-01); Type,
Constellation and Common name sort as displayed; the nine "OTHER"-prefixed
names are fixed. Spec §9. Found while reviewing and fixed too: the Horsehead
and the Cave Nebula were each two objects, and NGC 764 and NGC 6839 had lost
their own names to other objects' alternate names. **Status:** implemented,
reviewed and checked on a copy of Fred's database (14,008 → 14,006 objects,
user links unchanged); his running dev server applied the same repairs to
his real database (read-only check: integrity clean). Also fixed after
three more reviews: upgrading a database from before v0.42.0 (no source
keys) could give an object another's identity and links when two old rows
shared a name or a row had moved between OpenNGC's main and addendum files;
the moved-row gap predates this branch. Every key-based match now runs
first, then unambiguous row hashes across both OpenNGC files, then names.
Fred's database already has keys; a copy reloaded unchanged. Accepted
by Fred (2026-11-01).

### 8. Second acceptance round (Fred, 2026-11-01)

Spec §10. The catalog table could not leave page 1, a regression from
item 7 (fixed: the sort no longer re-reports itself on every redraw).
With several catalogs selected, each object will show and sort by its name
from those catalogs (Fred chose this), and the alternate names become pills
next to Designation (Fred). VizieR mirror moves will name the failed
mirror's own time; the counter beside them counts the new attempt. Found
while reviewing and fixed too: two OpenNGC rows fuse a PGC number to the next
name through a missing comma ("PGC 056771SDSS J…"); the parser splits them
and a repair fixes existing databases. **Status:** implemented (paging by
Claude, the rest by Codex), fresh review clean, and checked: a copy of
Fred's database changed only those two names (objects and links
unchanged); in a browser, paging in every view and both directions, the
pills, and Enter opening the details; a live Sharpless reload read
"Strasbourg timed out after 21 s", then "Harvard dropped the connection
after 60 s", then loaded from South Africa. Accepted by Fred (2026-11-01).

- [x] **PR review of #22** (Claude's code-review agent, 2026-11-01), covering
  the changes made after the independent Codex reviews. Four findings, all
  verified by Claude, none high; Fred asked for all four to be fixed before
  merging:
  - **Two outcomes of the fused-name repair check were untested:** a missing
    split name, and one another object already owns (which must not trigger
    a rebuild on every load).
  - **A test that proved nothing:** the cheap-check assertion passed against
    a per-object query loop.
  - **An undeclared package:** the catalog table imported a helper from
    `@mui/utils`, installed only through MUI; replaced by a local style.
  - **Question-mark help icons** in the object detail panel (older than this
    version): Distance now has a "How it's computed" link, and B magnitude's
    note is plain text under the value.
  - Found while checking the fix in a browser (older than this version): the
    panel put chips inside a paragraph element, which React reported as an
    error in the console; the value is now a block element.

### Found in passing (kept, with reasons)

- **The catalog load blocks the server while it runs.** `api/admin.py`
  `_run_loader` runs the synchronous loader on the event loop, so no other
  request is answered meanwhile. Measured on a copy of a real-size database
  on 2026-11-01: 0.1–0.6 s for a fetch with nothing else changed, 3.1 s for
  "Reload all". Moving it to a thread needs a database-contention policy
  first (the database uses the rollback journal). Kept by design (spec §7).
- **Harvard's VizieR mirror on 2026-11-01:** it returned HTTP 200 with an
  empty body and closed after 60 s for Barnard, and later for Sharpless.
  The one-pass fallback to IDIA handled both.

## v0.43.0 — Native plate solver

Merged in [PR #21](https://github.com/fbaptiste/nightcrate/pull/21) on 2026-11-01.

Fred started this version on 2026-10-28, after merging v0.42.0. Its scope is
the native plate solver, moved here from the roadmap. The spec starts from the
accepted prototype's findings.

- [x] Start from updated `main` on `v0.43.0/native-plate-solver`.
  - **Start-version fix (Fred approved, 2026-10-28).** The skill switched to
    `main` before pulling. Local `main` was a release behind, so Fred's
    running `make dev` briefly ran v0.41.10 code against his database.
    Checked afterwards: no catalog reloaded and every user record survived.
    The skill now updates `main` without checking it out.
- **Fred's decisions (2026-10-28):**
  - the native solver replaces ASTAP in the two places that solve today, the
    Image Analyzer and a project's Plate Solve tab. Nothing new, such as
    solving subs during cataloging, is in scope.
  - star data is managed in Admin, next to the DSO catalog downloads:
    - download Siril's file, or import a copy. Zenodo publishes it only as
      one 1.14 GB file, but serves byte ranges (checked 2026-10-28), so the
      download resumes after an interruption;
    - users pick which field ranges to index, each shown with its size, with
      ranges matching their rigs' fields ticked to start with; each range
      builds and can be removed on its own;
    - an image whose field falls in an unbuilt range cannot solve fully
      blind, and the dialog names the range to build. With a header
      position it can still solve by the slower route that needs no index.
  - the star file and indexes live in the app data folder and are shared by
    every database; solve results and settings stay per database.
  - Fred approved the Admin "Plate-solving stars" mockup (three states:
    before download, downloading, installed with field ranges), with
    "blind solve" as the term for a solve without a position.
  - Fred approved the solve-dialog mockup: no near/blind choice (solve near
    a known position, then fall back to a blind solve); solver, stars
    matched and fit error added to results; "Solve with ASTAP" only after a
    failure or while stars are missing, and only when ASTAP is set up; a
    default-solver choice in Settings → Plate Solving. Confidence is saved
    but not shown (Claude's call).
  - the dialog keeps closing itself on a successful solve. The new rows go
    in the Image Analyzer's Astrometric Solution sidebar and the project's
    saved solve, not in an open "Solved" dialog.
  - Fred stopped his `make dev` server, so work happens in the main
    checkout with no worktree. It stays stopped until the migration gate
    passes; until then, any server running this branch uses a temporary home
    folder with a copy of his database.
- [x] Spec, brainstormed with Fred:
  [design](docs/superpowers/specs/2026-10-28-native-plate-solver-design.md).
  A fresh builder check raised four questions. Two were settled from the
  prototype's evidence: index searches use the blind acceptance limits they
  were measured with, and the bar's measurement method is fixed in advance.
  Fred answered the other two (above). Fred approved the spec on
  2026-10-28.
- [x] Implementation plan and Codex plan review:
  [plan](docs/superpowers/plans/2026-10-28-native-plate-solver.md).
  The independent Codex plan review converged in 4 of 5 rounds. Every
  finding was accepted; nothing was rejected, and there are no tracked items.
  The main changes:
  - a search cut short is never a solve;
  - the solve slot is held until the worker stops;
  - the prototype's whole-sky index builder runs in a child process, instead
    of building in sky portions;
  - a manifest records the built ranges;
  - the solve order uses only the measured modes.

  The review section is at the end of the plan.
- [x] Fred approves the final plan (2026-10-28). He accepted the build
  memory: about 5.4 GB for the 0.2–0.4° range and 3.2 GB for 0.4–0.8°,
  shown in Admin. That replaces the dropped plan to build in sky portions.
- [x] Implementation by phase, with Claude's review:
  - [x] **Phase A, star data** (Tasks 1–4): the Siril reader, the pinned
    download and import, the index format, field ranges and manifest, the
    builder in a child process, and the Admin routes. Staged.
    - **Claude's review** sent 4 major and 4 minor findings, all fixed:
      - thread and child ownership when the task is cancelled from outside;
      - the `.bz2` import disk check, and cleanup after a failed import;
      - build progress that jumped from 5% to 100%;
      - about 20 planned tests that were missing.
    - **Checks:** 121 targeted tests pass; Ruff, format and Bandit are
      clean. All the work stayed in scope.
  - [x] **Phase B, the solver** (Tasks 5–7): the ported solver core, the
    solve order and budgets, the dispatcher with the worker holding the
    solve slot, migration 0065, the `default_solver` setting and the API
    contracts. Staged.
    - **Codex stopped once** on a contradiction in the plan: one test
      conflicted with the agreed rule for which failure message wins. The
      rule was settled in the plan review, so Claude corrected the test.
    - **Claude's review:** 3 major and 2 minor findings, all fixed:
      - "field not built" was missing when there was no position;
      - the near index search used fewer layers than the measured mode;
      - the image header was read on the event loop;
      - a second cancellation released the slot early;
      - the early-stop checks re-read the clock instead of recording why the
        search stopped.
    - Claude fixed the DDL so the new columns follow `solved_at`, the order
      `ALTER TABLE` produces.
    - **Checks:** 222 targeted tests pass, including real end-to-end solves
      of synthetic FITS and PNG images. Ruff, format and Bandit are clean.
  - [x] **Phase C, frontend** (Tasks 8–9): the Admin section, the dialog's
    states A, C and D, the Settings radio, and the sidebar and project rows.
    Staged.
    - **Claude's review and rendered checks** found, across two cycles:
      - Retry re-ran the solve instead of returning to the form;
      - table cells wrapped ("✓ / Built"), doubling the table's height;
      - the wrong state D line for `no_ranges`;
      - an ASTAP-only hint;
      - discarded error parses;
      - then an 820 px regression, where the table widened the whole Admin
        page.
    - Codex fixed the first five. After its third cycle, Claude fixed the
      last itself:
      - the page box had shrink-wrapped to its widest content (its centring
        margins in a flex column), and now has `width: 100%`;
      - the narrow-screen column minimums and the actions column padding were
        trimmed.
    - **Measured with headless Chrome:** at 820 and 1500 px, neither the page
      nor the table scrolls sideways.
    - **Rendered against the approved mockups**, light and dark, 1500 and
      820 px:
      - the three Admin states;
      - dialog states A and C (a Moon JPEG: "Only 0 stars were detected…");
      - the Settings radio;
      - the sidebar rows;
      - an old ASTAP project solve showing "Solver: ASTAP".
  - **A real project solve through the built-in solver** (on the copy)
    first failed with a 500: the project route called `run_solve` without
    `timeout`.
    - Every route test mocked `run_solve` itself, so none caught it.
    - **Fixed** (180 s default, as `run_plate_solve` had) with a test that
      drives the route through the real dispatcher, faking only the worker.
      The test fails without the fix.
    - **After the fix,** the Pacman Nebula sub solves near its header
      position and saves. It is within 0.15″ and 0.008° of the old ASTAP
      solution, and finds the same NGC 281 and IC 1590. The fit is 1.48 px
      RMS over the full 6248 × 4176 frame, as expected with TAN only.
  - **Claude's fixes found during the checks** (staged, with tests):
    - "Your rigs" listed every seeded smart telescope. Rig coverage now uses
      only rigs marked as the user's (`is_mine = 1`). The old test mocked the
      database and only checked the query text; the new one uses the seeded
      test database and fails without the fix.
    - A hard kill during unpacking left a hidden temporary file of up to
      1.5 GB, and a killed build left its folder; nothing removed them.
      Claiming an operation now removes these, and keeps the resumable
      partial and the verified compressed file.
  - [x] **Phase D, benchmark, trials and docs** (Task 10). Staged.
    - Codex wrote:
      - the corpus benchmark script, which runs every image in its own child
        process, judges wrongness by the prototype's rule, and writes the
        §11.2 bar with a PASS/FAIL per item;
      - the opt-in real-sky trials, which write a fixture of their inputs;
      - the README credits, setup and "Methods and prior work";
      - the "Plate solving" rules in development decisions;
      - the code map.
    - **Claude's review:** checked the bar computation against spec §11.2 and
      the rule for using target positions. The documentation facts and the
      four external links resolve.
    - Claude added the corpus's two `variant-*` categories, which the
      handoff had left out of the script's list.
  - [x] **Phase E, two index choices** (Task 10b, added after Task 11's
    range check; Fred, 2026-10-29). Staged. Details are under the
    measurements below.
  - [x] **Two review-fix rounds** from the independent reviews. Staged.
    Details are under the measurements below.
- [x] **Migration gate (2026-10-29):** a copy of Fred's database at 0064,
  upgraded through the app's runner.
  - No row count changed in any of the 72 tables.
  - The 3 existing solves keep every original value and read back as
    `solver = 'astap'`, with the new columns NULL.
  - The 16 `project_dso` rows keep their ids and links.
  - The CHECK rejects an unknown solver.
  - `integrity_check` is `ok` and `foreign_key_check` is empty.
  - Re-running is a no-op, and a fresh database migrates to 0065.
- **Measurements so far (Task 11, 2026-10-29).** All against a temporary
  HOME with a database copy.
  - **Real download** through the Admin route: about 10 minutes for 1.14 GB
    (Zenodo varied between 0.6 and 1.9 MB/s).
    - Cancel, then Download, resumed with `Range: bytes=18553816-` against
      Zenodo itself.
    - A server stop during unpacking kept the verified compressed file, and
      the restart skipped the download.
    - A hard kill during unpacking left a hidden temporary file (fixed;
      see above).
  - **Every range built through the Admin route.** Each file is
    byte-identical in size to the prototype's (3.44 GB in all).
    - `q004` peaked at 5.4 GB in the build process, with the server at
      0.2 GB. It took 175 s through the server (which ran at nice 5) and
      81 s directly with 15 threads.
    - `q008` with the small layers peaked at 3.1 GB.
    - The first `q004` build took 1,100 s and did not reproduce.
      Hypothesis, not checked: the machine was busy indexing the newly
      unpacked file.
  - **Rendered solves through the dialog:**
    - the M3 PNG crop (no header) blind-solved, labelling M3 and NGC 5263,
      with 164 of 250 stars matched and a 0.71 px RMS;
    - the IC 1805 Hα sub (one of the two narrowband subs the prototype's
      fully blind mode missed) solved near its header position in 1.6 s.
  - **Native against ASTAP on that FITS sub:** 0.12 px median grid
    distance (max 0.21 px), and rotation differs by 0.004°. The rotation rule
    agrees with ASTAP's CROTA2 on FITS.
  - **Thread against process** (spec §5.4), on 20 corpus subs and masters
    after one warm-up: a worker thread takes 0.30 s at the median, and a
    per-run spawned process 0.82 s. The process adds 0.52 s per solve, so
    the thread stays.
  - **Corpus benchmark** (149 images, one child process per image and
    mode, 2026-10-29):
    - native solved 132 of 143 and ASTAP 123; ASTAP solved one image native
      missed (the M106 JPEG);
    - no wrong solution in any mode, and no negative solved;
    - fully blind on the 106 subs and masters: 0.63 s median, 2.2 s P95;
      it missed the two narrowband subs the prototype also missed;
    - against ASTAP: 0.35 px median grid distance (P90 1.4 px) and 0.006°
      median rotation difference;
    - peak memory follows image size: 5.4 GB native and 3.9 GB in ASTAP
      mode, both on the Veil mosaic XISF.
    - **Median time missed under the fixed method:** native 0.53 s against
      ASTAP's 0.39 s over the 122 images both solve.
      - The script counts the solver modules' import (0.13 s) inside the
        native timer but not ASTAP's.
      - A fresh process also opens the star files for every image.
      - Timed the server's way (one process, one uncounted warm-up),
        interleaved with ASTAP on the same 122 images: native 0.35 s
        against ASTAP's 0.37 s.
      - **Fred (2026-10-29):** the built-in solver stays the default; some
        users won't have ASTAP set up at all.
    - **Re-run with the solver imports before the timer** (Claude's fix):
      every bar item passes. Native took 0.35 s against ASTAP's 0.43 s at
      the median; fully blind took 0.46 s at the median and 2.0 s at P95.
      Solve counts, safety results and agreement were unchanged. ASTAP's
      median moved 0.39 → 0.43 s between runs, so the margin is about as
      large as the run-to-run variation.
  - **Port check:** the product against the prototype's phase 2c results
    on the same corpus images, as a 7 × 7 grid median distance.
    - Fully blind: both solve the same 128 images, with a median distance
      of 0.001 px and a maximum of 0.008 px.
    - The product flow against the prototype's header-plus-index mode:
      115 images both solve, with a maximum of 0.007 px. The product also
      solves 17 images that mode missed.
  - **Rendered checks, round 2** (headless, on a second temporary home
    with no stars):
    - Admin "before download" in light and dark at 1500 and 820 px, with
      no page overflow;
    - dialog state D (stars not installed) in the Image Analyzer, in both
      themes and at both widths, and in the project tab;
    - keyboard order in state D: Cancel → Open Admin → Solve with ASTAP;
    - "Solve with ASTAP" from state D closes the dialog in both views; the
      sidebar shows "Solver ASTAP", and the project's saved row has
      `solver = 'astap'` with null native metrics.
  - **Failure transports**, faked at the network layer in both views:
    `field_not_built` (a 200 result in the analyzer, an object-detail 422
    in the project tab), a string-detail 422, and a non-JSON 500. Each
    shows its message with Close, Solve with ASTAP and Retry.
    - A non-JSON body is shown raw (`<html>…`). Main did the same; it goes
      in the review-fix round.
    - The Image Analyzer's MUI X "empty height" console warning is
      pre-existing; this branch adds no DataGrid.
  - **Independent Codex review** (gpt-5.6-sol, high, read-only;
    `.superpowers/codex/v0.43.0/47-*`). Six findings:
    - **Accepted, five:**
      - an ASTAP process could outlive its solve slot on cancellation
        (also true on main);
      - an import could truncate NightCrate's own staged file if picked;
      - no cancel or deadline check between load, extraction and search;
      - native pixel scale and field use `sqrt(|det CD|)`, not ASTAP's
        rule (spec §5.3; at most 0.06% on the corpus);
      - Admin's rig field uses the arctangent formula, not the dialog's
        (spec §4.4).
    - **Rejected:** "the Siril licence is unconfirmed". Zenodo's API record
      has `license.id = cc-by-4.0`.
    - **Fix round** (Codex, `.superpowers/codex/v0.43.0/48–51`):
      - all five accepted fixes, plus a plain message for a non-JSON error
        body;
      - in scope (inventory: 9 files modified, none added or deleted);
      - Claude reviewed the diff, re-ran the six affected test modules
        (154 passed) and ruff, and staged it;
      - the browser now shows "The server returned an unexpected response…"
        instead of raw HTML, in both views.
  - **Range boundaries** (spec §4.4): one range's layers alone miss fields
    near the bottom of that range.
    - **Synthetic edges:** 100 seeded real-sky fields per edge. At 1.02 ×
      each range's minimum, the range's own layers solved 22–46, against
      38–98 with every layer. Near the top edge the gap was 1–15. None was
      wrong.
    - **Layer sweep:** 60 fields at the bottom, middle and top of each
      range. Own layers plus the next smaller layer solve as many as every
      layer, within 0–4 fields, except at the 0.4–0.8° top (35 against
      42). The 0.2–0.4° range has no smaller layer, and its own already
      matches every layer.
    - **Corpus, one range built alone** (product flow, images with a
      position):
      - 0.8–1.6° lost three M66 images at 1.01–1.04°;
      - 1.6–3.2° lost four images at 1.64–1.69°;
      - 0.2–0.4° lost one header-less PNG crop;
      - 0.4–0.8° and 3.2–6.4° lost none.
    - **Corpus, blind:** 11 losses in all; none wrong.
    - Every lost image solves with every range built.
    - The build already shares layers between ranges: it skips ready
      layers, and removal keeps layers a remaining range uses.
    - **Fred (2026-10-29):** two choices instead of six ranges, as Seti
      Astro Suite Pro does:
      - Standard (8′–256′, fields 0.4°–10°, 529 MB), ticked by default;
      - Narrow fields (4′, 0.2°–0.4°, 1.39 GB), ticked when a rig needs it.

      SASpro's help page builds every inexpensive layer by default, and
      says neighbouring layers overlap so a boundary field is covered
      twice. Spec §4.4 and the plan's Task 10b are revised; Codex is
      implementing it as Phase E.
  - **Real-sky synthetic trials** (product, seed 20261029, 53 min):
    - positives: 1,540 of 2,000 solved, none wrong;
    - negatives: 0 of 1,000 random-dot fields solved;
    - by field band: 158/334, 209/334, 258/333, 291/333, 313/333 and
      311/333, from 0.2° up to 10°;
    - by declination: −90…−30 425/541, −30…30 724/970, 30…90 391/489.
    - **Prototype on the same fixture** (its own `solve_blind`, layers and
      catalogue, 30 s, through a local script outside the repository):
      also 1,540 of 2,000 and 0 of 1,000. Recovery is identical in every
      field band and declination band (the bar allowed 2 points below).
      No search hit its time budget.
  - **Phase E reviewed and staged** (Codex, records `52–55`):
    - inventory: 15 files modified, none added or deleted;
    - Claude re-ran the star-catalogue, native-solver, star-catalogue API
      and plate-solve test modules: 208 passed, 1 skipped (the real-sky
      trials).
  - **Builds of the two choices through the Admin route** (2026-10-29):
    - **Standard:** 39 s; build child 3.09 GB, with the server 3.29 GB;
      temporary disk 695 MB (preflight 1.15 GB).
    - **Narrow fields:** 92 s; build child 5.41 GB, with the server
      6.03 GB; temporary disk 2.87 GB (preflight 4.16 GB). Layer sizes
      are unchanged.
    - **A solve during the Narrow build** (IC 1805 Hα sub) took 1.3 s by
      `near_index`. Server plus child was 5.72 GB while it ran.
    - `build_memory_bytes` (3.2 GB and 5.4 GB) and the 3 × disk preflight
      stand.
  - **Admin with two choices,** rendered headless:
    - light and dark at 1500 and 820 px, with no page or table overflow;
    - Standard is listed first with four of the test database's rigs, and
      Narrow fields with a 0.39° rig;
    - before a build (status faked at the network layer), Standard starts
      ticked with no rigs, and Narrow fields only when a rig needs it.
  - **Corpus with Standard alone** (`--ranges 0.4-10`):
    - every image 0.4° or wider solves as it does with every layer (normal
      flow 118 of 119, blind 114 of 119);
    - under 0.4°, 12 of 14 still solve in the normal flow (11 by
      `near_catalog`); two integrated images (0.24° and 0.30°) need Narrow
      fields;
    - no wrong answer, and no negative solved.
  - **Second independent review** (`56–57`, of the fix round and Phase E):
    three findings, each verified and accepted as minor:
    - ASTAP's ownership begins only once its process exists;
    - no stop check before a new extraction;
    - the import guard is case-sensitive.
    - Brief `58` sent them back to the writer session (records `58–61`):
      - ASTAP now runs as a task owned like the native worker. A stop flag
        prevents any start or retry after a cancel or shutdown, and the
        slot is held until the task ends.
      - Stop and deadline checks run before every new extraction.
      - The import guard compares folders by filesystem identity.
      - In scope (6 files modified). Claude reviewed it, re-ran the
        affected modules (214 passed, 1 skipped) and ruff, and staged it.
  - **Release checks on the final code:**
    - `bandit` exit 0;
    - `uv lock --check` in sync;
    - `npm run build` passed (only the existing chunk-size warning);
    - ruff and format clean;
    - full `uv run pytest` outside the sandbox: 2,902 passed, 4 skipped
      (including the opt-in real-sky trials), in 33 min 42 s.
  - **Cycle 3** (`62–69`):
    - The round 2 re-review found that `/cancel` didn't set ASTAP's stop
      flag. Codex fixed it, Claude reviewed it, and 104 tests passed;
      staged.
    - The full suite on that code: 2,902 passed, 4 skipped.
    - **Version files bumped to 0.43.0;** the schema and reference headers
      are synchronized.
    - **The closing re-review found one last window:** a cancel while
      ASTAP's process is being created. The cycle limit is reached, so it
      went to Fred with Claude's recommendation (a post-launch stop check).
    - **Fred (2026-10-29): make the fix,** as recommended, with no fourth
      review cycle. Claude added it:
      - once ASTAP's process exists, a cancel that came in during the
        launch kills it, and the solve reports "Solve cancelled.";
      - a new test holds the launch while Cancel arrives. It fails on the
        earlier code, and passed six runs in a row with the fix.
      - Afterwards the plate-solve, solve API and native-solver modules
        gave 152 passed, 1 skipped; ruff, format and bandit are clean.
        The full suite ran before this fix and was not repeated.
- [x] Benchmark against ASTAP on Fred's local corpus, and synthetic
  false-match trials (results above).
- [x] Rendered checks (above).
- [x] Fresh independent Codex review: two reviews (`47`, `57`) and two
  re-reviews (`63`, `69`), above and in the plan's Codex review section.
- [x] Release checks (above).
- [x] Fred's acceptance test. It led to the fixes and the rework below;
  Fred accepted the new candidate on 2026-11-01.
- [x] **Fix during acceptance (2026-10-30): index builds ran out of open
  files.** Fred's first build failed with "Too many open files". The builder
  kept all 256 of its temporary part files open at once. A process started
  from a macOS terminal may open 256 files, while Claude's shell allowed over a
  million, so no earlier build or test could fail.
  - The builder now opens one part file at a time, while appending to it.
  - A new test lowers the limit itself and fails on the old code.
  - At the 256 limit, all seven layers rebuilt from the real star file
    match the earlier builds byte for byte after the header, which differs
    only in build statistics. Times were 35 s for Standard and 88 s for
    Narrow fields, no slower than before. The two largest layers also build
    with a limit of 32 files.
  - At the 256 limit, the star-catalog, native-solver and star-catalog API
    tests gave 111 passed, 1 skipped; ruff is clean.
- [x] **Fix during acceptance (2026-10-30): build progress and the range
  table.** Building Standard and Narrow fields together, Fred saw both bars
  move in lockstep, and the table scrolled sideways with Cancel cut off.
  - **Causes:**
    - every building row showed the whole job's progress;
    - that progress counted layers equally, so Standard's six quick layers
      took it to 86% and Narrow's single 88 s layer filled the rest;
    - nothing was published until every layer was done;
    - each building row added a bar and a Cancel button that pushed the
      table past the card.
  - **Fred approved the fix:**
    - ranges build one at a time, Standard first, each published as soon
      as it is ready;
    - each range shows its own progress, weighted by layer size;
    - a queued range shows "Waiting";
    - one Cancel, on the row being built, which keeps finished ranges;
    - rig labels wrap rather than widen or truncate the table.

    Codex implemented it (records `70–75`); Claude reviewed it and sent one
    defect back (chips truncated with "…", hiding the field value).
  - **Checks:**
    - star-catalog, star-catalog API, native-solver and plate-solve API
      tests at a 256-file limit: 121 passed, 1 skipped; ruff clean;
      `npm run build` passed;
    - rendered headless at 820, 900, 1000, 1100, 1280 and 1500 px, dark and
      light, in four states (not built; Standard building with Narrow
      waiting; Standard built with Narrow building; both built): no
      sideways scroll and no truncated chip;
    - a real build of both ranges on the test copy: Standard built at 36 s
      while Narrow fields kept building; both were done at 130 s.
- [x] **Reopened during acceptance (2026-10-30): plate solving and its UI.**
  Fred's NA Nebula final (a stretched, cropped stack) solved with neither
  solver from the project Plate Solve tab, and he found the solve UI
  confusing: unclear options, an unexplained "From Reference Image", no view
  of the chosen image, and a failure that meant choosing the image again.
  - **Causes, each reproduced:**
    - the built-in solver's verification set left out stars with clipped
      cores, which in a stretched image are all the bright ones;
    - Rig and Equipment hints sent a field height computed from the full
      sensor, 14% too large for this crop, and ASTAP's position search
      failed with it;
    - ASTAP had no blind step, and its message suggested one.
  - **Other defects found in the audit:**
    - manual hints are never sent;
    - header binning is counted twice;
    - the project tab never prefills header equipment;
    - an ASTAP "solved" result isn't checked for a complete WCS;
    - an ASTAP failure can be hidden behind the star-setup screen;
    - dismissing the dialog doesn't cancel, so a late result can attach to
      another image;
    - cancel isn't tied to one solve.
  - **Fred (2026-10-30): fix all of it in v0.43.0 and redesign the
    plate-solving UI** for simplicity and clear options, using the design
    skill and a discussion with Codex. The backend design converged with
    Codex in five rounds (records `78–87`). The UI design follows in
    `docs/superpowers/specs/2026-10-30-plate-solve-ux-design.md`, with
    mockups for Fred's approval, then an implementation plan and a new
    candidate.
  - **Fred (2026-10-30):**
    - approved the clickable mockup ("I like this UX much better");
    - removed "From Reference Image";
    - dropped the telescope-and-camera scale picker;
    - chose ASTAP's automatic whole-sky step;
    - kept project solves on a file's first image;
    - asked for the tab's explanation text.
  - **The plan** (`docs/superpowers/plans/2026-10-30-plate-solve-fixes-and-ux.md`)
    converged with Codex in an independent review (records `94–99`). Fred
    approved it on 2026-10-30. Implementation: Phase A (built-in solver),
    Phase B (backend contracts and the ASTAP chain), Phase C (the panel).
  - **Implemented and reviewed** (Codex wrote, Claude reviewed each phase).
    The plan's Codex review section lists the review findings.
    - **Corpus benchmark** (143 images that should solve):
      - built-in 132 (unchanged);
      - ASTAP 130, up from 123: near the position, then the whole sky;
      - no wrong verified solution and no negative image solved;
      - the user's `astap.cfg` byte-identical after the run.
    - **The NA Nebula final** solves with both solvers through both the
      Image Analyzer and the project endpoints. The two agree to about 0.3″.
    - **Rendered checks** (headless, against a test copy):
      - project tab 44 of 44;
      - Image Analyzer and Admin 35 of 35.
    - **Preview speed:** a 26 MP FITS shows in 0.09 s. A 540 MB XISF shows
      in 0.27 s, using 2.7 GB at its peak; the existing project render uses
      5 GB.
    - **Removed:**
      - the solve dialog, "From Reference Image" and its route;
      - the request `mode`;
      - the old cancel and progress forms without an ID.
  - **Still failing with the built-in solver:** 10 finals, of which ASTAP
    solves 2, plus the Veil mosaic, which ASTAP solves.
    - A time-boxed look found that in a processed nebula final (IC 1805),
      only about 40% of the brightest detections are stars.
    - A fix changes the search design, so it is proposed for v0.43.1 (see
      the roadmap), not made now.
    - The failure screen points to the stacked image, which the built-in
      solver solved for 9 of the 10.
  - **Release checks on the new candidate (2026-10-30):**
    - ruff, format and bandit: clean (bandit: 0 issues at any severity);
    - `npm run build`: passed, with only the existing chunk-size warning;
    - **full backend suite** (`pytest -n auto`): 3,003 passed, 4 skipped,
      1 failed;
    - the failure was `test_migration_0064_rotation_cases`. It fed ASTAP's
      result parser a WCS without centre or reference pixel, which Phase B
      now correctly treats as unsolved. Claude completed the test's WCS, and
      the module now passes (3 of 3).
    - **Final tree (2026-11-01):** full backend suite (`pytest -n auto`)
      3,004 passed, 4 skipped; ruff, format, `uv lock --check` and
      `npm run build` clean; bandit reports no issues, with one new
      `# nosec B311` (random jitter for download retry delays).
    - **Coverage of the changed modules:** 86% overall, with
      `solve_operations` at 97% and the plate-solve routes at 82% (counting
      the annotation tests). The routes' remaining gap is error handling
      that was already untested.
  - [x] Fred accepted the new candidate (staged tree `9428a6e`) as feature
    complete and asked to finalize it on 2026-11-01.
- [x] **PR review of #21** (Claude's code-review agent, 2026-11-01), covering
  the changes made after the independent Codex review. Seven findings, all
  verified by Claude, none high; Fred asked for all seven to be fixed before
  merging:
  - **An unfinished step showed as "Done".** A project solve that couldn't
    read its image listed the reading step as done.
  - **"Try again" had gone missing** for errors sent without a reason, such
    as a busy solver. The previous fix round caused this.
  - **Two contract tests proved nothing:** they passed with the contract
    reverted.
  - **Failure titles were missing** for render, image, star-setup and range
    failures. A render failure read "No solution found" above "The image
    solved, but…".
  - **Deleting a solve during a replacement** in another tab could make the
    replacement fail with a server error.
  - **Folders left by a crash** stayed until the solve was deleted.
  - **Error labels were wrong:** internal errors were reported as reading
    errors, and a missing ASTAP program asked about a disconnected drive.

  **The fixes:**
  - Both solve endpoints now send every error as `{message,
    failure_reason, attempts}`, with reasons `invalid_configuration`,
    `read_error`, `busy`, `solve_exists`, `time_limit` and `error`.
  - The solvers mark reading failures and ASTAP launch failures with their
    own error types.
  - An unfinished step is reported as stopped.
  - The panel has a title for every reason, and "Try again" where retrying
    can help.
  - A successful save clears every leftover folder, and delete leaves
    in-progress renders alone.

  Codex implemented them in two rounds (records `150–156`); Claude
  reviewed them and updated the development decisions.
  - **Checks:**
    - the affected test modules (237 passed in Codex's run);
    - the full backend suite: 3,045 passed, 4 skipped;
    - ruff, format and bandit (no issues); `npm run build`;
    - rendered headless against a test copy: the failure screen 30 of 30
      (eight reasons, including an older server's responses), project tab
      44 of 44, Image Analyzer and Admin 35 of 35.

### Scope

Fred decided on 2026-10-26 to solve images inside NightCrate by default, with
ASTAP kept as an option. The method is derived from published work: 4-star
geometric hashing and Bayesian verification (Lang et al. 2010, AJ 139, 1782),
and TAN/SIP WCS (Calabretta & Greisen 2002; Shupe et al. 2005). Since the move
to GPL-3.0-or-later, Fred has allowed (2026-10-27) reading the source of
open-source solvers for concepts: Seti Astro Suite Pro, astrometry.net, ASTAP,
tetra3 and twirl. NightCrate writes its own code, copies none, and credits the
projects that informed the design in README's acknowledgments.

- **Stars.** Changed by Fred on 2026-10-26 after a Claude–Codex review.
  - The app downloads the **Siril Astrometry Catalogue extracted from Gaia
    DR3** (Zenodo DOI 10.5281/zenodo.14692304; CC BY 4.0; derived from Gaia
    DR3, whose data licence is CC BY-NC 3.0 IGO).
    - One 1.14 GB file, with published SHA-256 checksums.
    - It holds the 127 brightest stars in each level-8 HEALPix cell, to
      G = 20.
  - NightCrate reads the file from its published format specification
    (DOI 10.5281/zenodo.14697486, CC BY 4.0), not from Siril's code.
  - Each user downloads the file directly from Zenodo. A local copy can also
    be imported, for example one downloaded on another computer.
  - Stored in `APP_DIR/star_catalogs/` on the DSO catalog pattern (staging
    folder, atomic rename, `version.json`) and shared across workspaces.
  - NightCrate publishes and bundles no star files.
  - The 4-star index is built locally for the user's field-of-view range.
  - After the download, solving is fully offline and self-contained.
  - Credit both the Siril team and ESA/Gaia (DPAC). NightCrate's code is
    GPL-3.0-or-later; the star data keeps its own terms.
  - The CC BY 4.0 label on the Siril record (Zenodo API `license: cc-by-4.0`,
    checked 2026-10-26) cannot remove Gaia's non-commercial terms. NightCrate
    makes no claim that the star data may be used commercially. A user's use
    of it is governed by ESA's CC BY-NC 3.0 IGO terms as well.
- **Scope.**
  - Fields of 0.2–10°.
  - Fully blind: position and scale both unknown. Hints from the header,
    target or rig only speed the solve.
  - TAN output, so existing overlays, FOV and object search work unchanged.
    SIP comes later.
  - Each solve records its solver, catalog version, detected and matched
    stars, RMS and confidence.
- **ASTAP.** It stays user-installed. A setting picks the default solver. A
  failed native solve offers "Solve with ASTAP"; it never retries
  automatically.
- **No new Python dependencies.** numpy, scipy, astropy, sep and
  astropy-healpix cover the method. Avoid healpy, which is GPL.
- **First step: a throwaway prototype and benchmark against ASTAP.**
  - It runs outside the checkout and is not committed.
  - It measures solve and wrong-solution rates, speed, and the local index
    size and build time for the narrowest field range, using the Siril
    catalogue.
  - **Complete; Fred accepted it on 2026-10-27.** On the 106 subs and masters
    that the hinted prototype solved, measured one image at a time, including
    image load and star detection:

    | Solver | Solved | Median | 95% within |
    |---|---:|---:|---:|
    | Native, header position + index | 106 | 0.48 s | 1.4 s |
    | Native, fully blind | 104 | 0.75 s | 3.9 s |
    | ASTAP, header position | 106 | 0.70 s | 2.5 s |
    | ASTAP, position removed, field size given | 96 | 18 s | 60 s (limit) |

    - Of the 143 corpus images that should solve, native fully blind solved
      128 and ASTAP with header positions 123. Neither solver gave a wrong
      answer, and no negative image solved. The two solvers' solutions differ
      by 0.37 px at the median.
    - The index for fields of 0.4° and wider is 505 MB and builds in 35 s.
      The layer for 0.2–0.4° fields adds 1.3 GB.
    - 1,000 random-dot fields produced no solve. Simulated real-sky fields
      produced no wrong answer.
- **Carried into the spec from the prototype:**
  - Solve hinted images through the index restricted around the hint. The
    prototype's separate hinted solver is slower and needs no index.
  - Header scales can be wrong (binned masters were 2× off). Fall back to a
    fully blind solve when a scale-known solve fails.
  - Whether to offer the 1.3 GB narrow-field layer, chosen from the user's
    rigs.
  - Native fully blind missed two narrowband subs that ASTAP and the hinted
    path solve.
  - Calibrate the synthetic trials to real images before using them as a
    recovery measure. The prototype's generator made its spurious stars
    brighter than all real stars and scattered brightness about five times
    more than real images do.
  - Credit SASpro and astrometry.net in README's acknowledgments.
- **Test images.**
  - Fred's images plus licence-checked public samples, kept local and never
    committed.
  - The repo holds only the benchmark script, plus synthetic tests that
    generate their star fields in memory.
- **Bar for native as the default:**
  - a solve rate at least ASTAP's on the corpus;
  - no wrong solutions, on the corpus or in thousands of synthetic trials;
  - a median time no worse than ASTAP's;
  - fully blind solves in a few seconds (Fred, 2026-10-27). Working target:
    a median of 3 s or less and 95% within 10 s on the corpus, including
    image loading.

## v0.42.0 — Catalog preservation, licence, planner star, mirrored overlays

Merged in [PR #20](https://github.com/fbaptiste/nightcrate/pull/20) on 2026-10-28.

Fred started this version on 2026-10-27. Its scope is the four roadmap items
below. The licence change was already in the working tree and moved onto this
branch uncommitted. The native plate solver follows in the next version.

- [x] Start from updated `main` on `v0.42.0/catalog-preservation`.
- **Authorization (Fred, 2026-10-27 evening): "just build everything."** He
  waived his spec and plan approvals for the overnight run ("Fred says so") and
  asked Claude to settle open questions itself; those calls are listed in the
  spec's §6 for his review. Nothing is committed. High-stakes checks still
  apply.
- **Fred's decisions (2026-10-27):**
  - an object a catalog update merges into another moves the user's records to
    the survivor silently, keeping the old name as a designation;
  - an object a catalog update removes is kept, marked "no longer listed"
    wherever the user's records show it, and hidden from browsing and search;
  - reloads update objects in place;
  - fetching one catalog no longer reloads the others.
- **Worktree.** Fred's `make dev` server from 2026-10-24 is still running from
  the main checkout, and its auto-reload would apply new migrations to his
  real database. Code is therefore built in a detached worktree
  (`../nightcrate-v042-wt`) and brought back once that server is stopped.
- [x] Spec: [design](docs/superpowers/specs/2026-10-27-catalog-preservation-design.md).
  Before writing it, Claude confirmed the bugs on copies:
  - one Admin reload deleted every target, solved-field object and wishlist
    entry in a copy of Fred's database;
  - both mirrored-overlay cases appear on screen;
  - an experiment confirmed ASTAP's bottom-up rows for PNG, JPEG and TIFF.
- [x] Plan: [implementation plan](docs/superpowers/plans/2026-10-27-catalog-preservation.md).
  - **Builder check:** a fresh reviewer found 5 gaps, all settled as
    Claude's calls.
  - **Codex plan review:** converged in 4 of 5 rounds. Every finding was
    accepted; nothing was rejected, and there are no tracked items. The
    review section is at the end of the plan.
  - **Main changes:**
    - identity never comes from shared names;
    - catalog reloads wait while a loaded catalog's file is missing;
    - failed steps retry;
    - removed objects keep their wishlist data;
    - the existing CDELT/CROTA conversion swaps two scales, and is now fixed.
- [x] Implementation and review (Codex implements in the worktree; Claude
  reviews, re-runs the checks, and stages in the worktree):
  - [x] **Phase A, catalog object step** (migration 0063; reconcile engine;
    user-record moves; load orchestration; Admin fetch routes no longer force
    a full reload).
    - **Claude's review:** 9 findings, all fixed. The worst: matching was
      quadratic; display-name matching could still run after the upgrade; a
      failing object step escaped the loader; and merged plans dropped most
      differing settings from the notes.
    - **On a copy of Fred's database with the real catalog files:**
      - the one-time keying step took 3.5 s, and a forced reload 2.0 s (13.8 s
        before);
      - all 3 targets, 16 solved-field objects, 3 wishlist entries and 701
        sub-frame links survived, and every object kept its id;
      - all 42,088 designations, 35,951 external links, names and distances
        are identical; integrity and foreign-key checks are clean.
    - **Tests:** 235 targeted tests pass; Ruff, format and Bandit are clean.
  - [x] **Phase B:** API `active`, the "Not listed" tags, and the planner star.
    - Removed objects stay readable through the user's records and are refused
      as new wishlist entries or main targets (409).
    - **Tests:** 138 targeted tests pass; the build is clean.
    - **Rendered check** on a database copy with three objects marked removed,
      light and dark, 1500 and 820 px:
      - the tags show on the wishlist, the target chip and solve objects;
      - the main toggle is disabled for a removed non-main object;
      - catalog search hides the object;
      - the planner star syncs with the card both ways.
  - [x] **Phase C:** WCS row order, the CDELT fix, and migration 0064 (the
    first Python migration).
    - **Claude's review:**
      - **On-screen regression:** a real XISF lost its WCS, because one stray
        PixInsight property made the reader skip the FITS keywords. Fixed.
      - **Image height:** the flip now always uses the image's real height.
    - **After the fix, on screen:** the NGC 7380 XISF and the same image as a
      PNG solved with ASTAP both show Sh2-143 at the top edge, rotation
      28.71°.
    - **Across all 56 corpus XISF files:** exactly the 3 known mirrored ones
      flip; the other 53 are unchanged.
  - [x] **Migration gate:** a copy of Fred's database at 0062 → 0064 through
    the app's migration runner.
    - No row count changed in any table, either after migrating or after the
      first-startup load (5.2 s).
    - Integrity and foreign-key checks are clean; re-running is a no-op.
    - A fresh database builds cleanly.
- [x] **Fresh independent Codex review** of the whole change: no blockers;
  2 major findings and 1 minor, all fixed. The main one: a changed augment file
  was applied while object updates waited for a missing catalog file.
- [x] **Final checks in the worktree:**
  - full backend suite (`-n auto`): 2,749 passed, 3 skipped;
  - Ruff, format, Bandit (no issues) and `uv lock --check`;
  - frontend build.
- [x] **Integration into the main checkout (2026-10-28).**
  - The worktree's staged diff was applied and staged; it is byte-identical
    to the worktree and does not overlap the uncommitted licence and doc
    edits.
  - Checks in the main checkout:
    - full backend suite: 2,749 passed, 3 skipped;
    - Ruff, format, Bandit and `uv lock --check`;
    - frontend build.
- [x] **Release checks (2026-10-28).** Fred read the spec's §6 calls and asked
  for no changes.
  - Version files and reference headers synchronized to 0.42.0. README notes
    that catalog updates keep the user's records; the code map mentions
    Python migrations.
  - **Fixed during preparation** (Codex implemented, Claude reviewed):
    - **A test-isolation bug, already present before this release.** Tests that
      start the app left the `nightcrate` logger without propagation, so a later
      plate-solve log test failed in serial runs (`make test`). A conftest
      fixture now restores the logger after each test. Fred approved the fix.
    - **Coverage against base 115f18f:** two catalog helpers left without
      callers by the rewrite were removed, and the augment and external-refs
      loaders' "unchanged file" path has direct tests again.
    - **Test runs deleted the user's real planner thumbnails** (found by Fred
      during acceptance, 2026-10-28; present since v0.16–v0.17).
      - **Cause:** `services/thumbnails.py` and `services/sky_tile_cache.py`
        copied `APP_DIR` at import, so the tests' redirect never reached them.
        Tests that start the app ran the thumbnail orphan sweep against the
        real folder with a test database, and every file looked orphaned.
      - **Fix (Fred approved):**
        - those two modules, `db/session.py` and `api/admin.py` read
          `app_config.APP_DIR` at call time;
        - `tests/test_app_dir_isolation.py` fails on any import-time copy, and
          checks that the caches and the sweep follow the redirect.
      - **Evidence:**
        - reproduced with a fake home: the startup tests deleted a fake
          thumbnail before the fix and kept it after;
        - the whole suite under a fake home passed (2,755), and no file was
          added to or removed from the fake app-data folder.
      - Fred's cache index is intact, and the images download again as he
        views them. CDS was unreachable that evening, so the downloads failed
        and back off for an hour.
  - **Checks:**
    - full backend suite, serial, with coverage: 2,755 passed, 3 skipped;
      the real app-data caches' file counts were unchanged by the run;
    - coverage 92% (base 91%), with no module below its base figure;
      `api/plate_solve.py` shows 65% → 64% only through rounding, because
      the same lines are uncovered and there are two fewer statements;
    - Ruff, format, Bandit (0 findings at any severity), `uv lock --check`;
    - frontend build;
    - documentation links and `git diff --check`; no private paths in the
      staged changes.
- [x] **Fix during acceptance (2026-10-28): the planner star.** Fred could
  not find the star in the open object's panel: in dark mode its off colour
  had almost no contrast against the dialog. At his request:
  - in the panel it sits left of the object name;
  - on the planner's cards it moved from the far right to a column left of
    the thumbnails, outside the clickable area, so starring never opens the
    object;
  - on the wishlist tab it moved from the right-hand column to the left of
    the thumbnail (after the drag handle in planned sections);
  - the off star in the panel and on the cards has the same colour as the
    close button.
  - Rendered check on a database copy, light and dark, 1500 and 820 px:
    visible in both themes; toggling in the panel updates the card, and the
    reverse; a card's star does not open the object; the wishlist star
    still removes the entry.
  - Frontend build clean.
- [x] Fred's acceptance test. Fred accepted the candidate (staged tree
  `98af670`) and authorized publishing on 2026-10-28.
- [x] **PR review of #20** (Claude's code-review agent, 2026-10-28), covering
  the changes made after the independent Codex review: the test-isolation,
  coverage and app-data fixes, and the star moves. No high or medium
  findings; five low ones, all verified by Claude. Fred asked for all five to
  be fixed:
  - **The app-data guard skipped code Python runs at import.** Class bodies,
    default arguments, decorators, class bases and aliased imports of
    `app_config` went unchecked. They are now checked, with nine self-tests
    including a negative case for function bodies. The guard still flags the
    pre-fix `thumbnails.py`, `sky_tile_cache.py` and `admin.py`.
  - **The orphan-sweep test would have deleted real thumbnails before
    failing.** It now checks the redirected folder before the sweep.
  - **The source scan could pass with nothing scanned.** It now requires
    `services/thumbnails.py` and at least 100 files.
  - **Screen readers named the object panel "Add to wishlist, …".** The
    dialog is now named by the designation alone.
  - **Wishlist rows kept an empty column** when no sections exist. It is no
    longer rendered.
  - Codex implemented the three test fixes and Claude the two screen fixes.
    Checks: the guard, thumbnail, sky-tile and startup tests (51 passed), the
    real app-data caches' file counts unchanged by the run, Ruff, the
    frontend build, and a headless browser check of both screen fixes on a
    database copy.

### Catalog preservation

Fred decided on 2026-10-24 that this fix is part of the next version, whatever
else it contains.

Before this release, updating or reloading a catalog deleted and reinserted
that source's `dso` rows. With foreign keys on, this cascaded away main targets
(`project_target`), solved-field objects (`project_dso`) and wishlist entries,
and cleared frame and folder target links. The gallery, the Messier checklist
and object search all depend on these rows.

- **Built:** catalog rows are reconciled by a stable source identity
  (`dso.source_key`, migration 0063), so `dso` IDs survive every update.
  - Only explicit catalog merge signals merge objects, and the user's records
    move to the survivor.
  - Objects a catalog drops are kept inactive. They are marked "Not listed" in
    the user's records, hidden from browsing and search, and refused as new
    wishlist entries or main targets.
  - Admin fetches update only the fetched catalog.
- Tests cover targets, solved-field objects, wishlist entries and frame/folder
  links surviving reloads, merges and removals.

### Licence: GPL-3.0-or-later

Fred decided on 2026-10-26 to relicense NightCrate from MIT to GPL-3.0-or-later.
His aim is that nobody can turn NightCrate into a closed product they sell. The
GPL still permits selling copies, but only with source.

- This covers this release and later ones. v0.41.10 and the other MIT releases
  remain MIT, and a closed fork of them is still possible.
- Releases v0.3.0a–v0.10.1 were GPL-3.0. The project went back to MIT on
  2026-04-14 because no dependency needed the GPL.

- Changed in the working tree (uncommitted):
  - `LICENSE` holds the verified GNU GPL v3 text from gnu.org.
  - README: a licence notice; earlier releases keep their original licences;
    NightCrate's own catalog data stays MIT; Pillow (MIT-CMU) and sep
    (LGPL-3.0-or-later) identifiers corrected.
  - `CLAUDE.md`: product statement and dependency policy.
    - GPL-3.0-compatible dependencies only.
    - BSD-4-Clause and GPL-2.0-only are incompatible.
    - MPL-2.0 needs the Exhibit B check and notice/source obligations.
    - AGPL needs Fred.
  - Codex's independent licence review confirmed that every entry in both
    lockfiles is compatible.
  - The catalog attribution dialog's sentence about the application licence.
- Also corrected: README listed ASTAP as GPL-3.0. ASTAP's main program is
  MPL-2.0, with some LGPL-3.0+ and GPL-2.0+ files (SourceForge, Debian
  metadata).
- Follow-ups for Distribution (deferred until installers exist):
  - Declare `license = "GPL-3.0-or-later"` in `backend/pyproject.toml`
    (uv_build) and `frontend/package.json`. Deferred to avoid lockfile churn
    now.
  - Installers must ship the GPL text, the exact Corresponding Source for the
    shipped version (including build scripts), and a generated third-party
    notice bundle with the LGPL/MPL source obligations.
  - PyInstaller is GPL-2.0-or-later with a Bootloader Exception. That
    exception is what permits its frozen output under any licence.
  - Optional: `SPDX-License-Identifier: GPL-3.0-or-later` headers in
    NightCrate-owned source files, as GNU recommends; not required.

### Planner: wishlist star on the open object

Requested by Fred on 2026-10-24. In the planner, each object in the list has a
wishlist star (`PlannerTargetCard`), but the opened object
(`PlannerDetailPanel`) has none, so it cannot be added or removed there.

- **Built:** the detail panel has the same star, using the wishlist hooks in
  `api/wishlist.ts`, so the list and the panel always agree.
- The star shows only in the planner. `PlannerDetailPanel` also opens from a
  project's Catalog tab (`ProjectCatalogTab`); Fred decided on 2026-10-24 that
  no star appears there.

### Mirrored object overlays

Fred decided on 2026-10-27 to fix these in the next version. The native solver
benchmark found them. In both cases NightCrate reads a stored plate solution
with its rows counted from the wrong end. Overlays then appear mirrored top to
bottom; only the image centre is labelled correctly. Found from the benchmark
numbers and the code. Confirm both on screen in the app before fixing.

- **XISF files whose solution is stored as FITS keywords.** PixInsight can
  store a solution as its own XISF properties or as FITS keywords. The
  properties are read correctly. `xisf_io._astrometric_wcs_cards` uses the
  FITS keywords as they are, without the vertical flip they need.
  - Evidence:
    - Three corpus files (the M74 final and master, and the NGC 7380 master)
      are mirrored against both native and ASTAP.
    - After a vertical flip, the M74 final agrees with native to 0.29 px.
    - All 32 property-based XISF files agree.
  - The "Real FITS WCS wins" rule in `docs/development-decisions.md` (XISF
    WCS) was corrected with the fix.
- **PNG and JPG files solved with ASTAP.** `plate_solve` passes these files to
  ASTAP unchanged and stores ASTAP's CD matrix as it is. ASTAP counts rows from
  the bottom for these files; the overlays count from the top.
  - Evidence: on two M3 PNGs, ASTAP's solution is the native one mirrored. After
    a vertical flip they agree to 0.3 and 0.5 px. An experiment confirmed the
    same for TIFF and JPEG.
- **Built:**
  - Both readers flip the rows to NightCrate's top-down order.
  - Migration 0064 repairs solutions already saved for on-disk PNG, JPEG and
    TIFF images, so no re-solve is needed.
  - Also fixed: converting a header's pixel scale and rotation (CDELT/CROTA)
    swapped the two scales.
- Tests: one solution per affected format, checking an off-centre object's
  pixel position against a known answer.

## v0.41.10 — Dependency fixes from issue #16

Merged in [PR #19](https://github.com/fbaptiste/nightcrate/pull/19) on 2026-10-24.

A Windows user's [issue #16](https://github.com/fbaptiste/nightcrate/issues/16)
reported `npm audit` warnings, an `npm ci` failure, and weather-forecast and
planner crashes. Fred
approved the triage and fix plan on 2026-10-24 and asked for a separate
version. Inserted ahead of v0.42.0; the roadmap is not renumbered.

- [x] Start from updated `main` on `v0.41.10/dependency-fixes`.
- [x] **Triage.** Only Vite affected NightCrate, because users run the Vite
  development server. On Windows, a malicious web page could leak the user's
  password hash through Vite 8.0.3's open-in-editor route. Vite's file-read
  bugs need LAN mode. The React Router advisories cover a server mode we don't
  use, and KaTeX's needs an existing prototype-pollution bug. The remaining
  warnings are in build tools.
- [x] **Frontend dependencies:**
  - Vite 8.3.4 and React Router 7.18.4 (the minimum range raised to match).
  - KaTeX 0.19.0. `react-katex` was removed because it pinned KaTeX 0.16.
    `Math.tsx` now calls KaTeX directly.
  - The lockfile was resolved with a 7-day release cutoff. The regenerated
    lockfile also fixes the `npm ci` mismatch.
  - Checks: `npm audit` reports 0, both full and production-only. The old
    lockfile reproduced the reporter's `npm ci` error, and the new one installs
    cleanly. All 20 formulas render at identical sizes, and all 14 sidebar
    routes load in Playwright.
- [x] **Backend `tzdata`:** Windows has no system time-zone database. Tests
  hide the operating system's copy to simulate Windows, and a guard test
  confirms that lookups fail without the package.
- [x] **`make` help listing** (found by Fred during acceptance preparation).
  `make` listed neither `dev` nor `help`. Its help script showed a target only
  when the line directly above it was a `## ` summary, and variable
  assignments sat in between. After the PR review, each summary now sits on
  its target's own line (`target: ## summary`), so nothing can come between
  them.
- [x] Fresh Codex review of the full diff.
- [x] Release checks; version files and reference headers synchronized to
  0.41.10. Development decisions now record that users run the Vite
  development server, the `tzdata` requirement, and the KaTeX wrapper.
- [x] Fred's acceptance test. Fred authorized publishing on 2026-10-24
  and merged PR #19 the same day.
- [x] The PR description references #16, so the reporter can see which of
  their findings this release addresses. Fred also asked for a comment on
  the issue (both 2026-10-24).
- [x] **PR review of #19** (Claude's code-review agent, 2026-10-24). It found
  11 issues, none high-severity. Claude verified each one, and Fred asked for
  all to be fixed:
  - **Node 22.12+.** KaTeX 0.19's command-line dependency (commander 15)
    declares Node 22.12+; every KaTeX release with the fix does. Node 20
    reached end of life on 2026-04-30. The README prerequisite is updated.
  - **Docs named the planner only.** Issue #16 began with the weather forecast
    failing, and the planner came later; both had the same cause. The docs,
    PR description, and issue comment now name both.
  - **`Math.tsx` safety net.** It again catches what react-katex caught
    (`ParseError`, `TypeError`) and shows the message as text instead of
    failing the page. The `trust` comment now names `\includegraphics`.
  - **Tests:**
    - The fixture moved to `tests/conftest.py` and restores the previous
      search path.
    - `tonight_date` uses a frozen clock with exact dates.
    - New tests cover the weather forecast route and the time-zone list
      with the system database hidden.
    - With `tzdata` hidden as well, all five tzdata-dependent tests fail and
      the guard passes.
  - **Vite as a runtime dependency.** `vite` and its two plugins are now in
    `dependencies`, so `npm audit --omit=dev` covers them. No versions
    changed.
  - **`make install` runs `npm ci`**, so installs never rewrite the lockfile.
  - **`BROWSER` default.** "Brave Browser" is the default only on macOS;
    elsewhere Vite opens the default browser.
  - **Help listing.** `make help` uses the inline `target: ## summary`
    pattern.

Verified by Claude:
- **Backend:**
  - The full suite, run with `-n auto`: 2,664 passed, 3 skipped, 24 warnings.
  - `uv lock --check`, Ruff lint and formatting, and Bandit, which reports no
    issues.
- **Frontend:**
  - The production build passes, with the existing bundle-size warning.
  - ESLint is clean on `Math.tsx`.
  - `npm audit` reports 0, both full and production-only.
  - `npm ci` succeeds in a clean copy.
  - All 450 lockfile sources resolve to registry.npmjs.org.
- **Docs:** local links and `git diff --check` are clean.
- **Rendered checks** are listed above.
- **After the PR review fixes:**
  - **Backend:** the affected test files (astronomy, weather API, locations
    API) gave 119 passed. Ruff, formatting, Bandit, and `uv lock --check` are
    clean.
  - **Frontend:**
    - The build passes, and ESLint is clean on `Math.tsx`.
    - `npm audit` reports 0, both full and production-only.
    - `npm ci` succeeds both full and with `--omit=dev`; the production-only
      install includes Vite.
    - All 20 formulas match the original captures again.
  - **Makefile:** all 11 targets are listed. `make -n` confirms the `LOG` and
    `BROWSER` defaults and overrides, BROWSER unset with `UNAME_S=Linux`, and
    `npm ci` for `make install`.

Not verified: actual Windows installation and runtime.

### Codex review

- **Mode:** independent review of the full diff. It was required because
  dependencies and lockfiles are high-stakes. The work was Claude-authored
  under the "Fred says so" and "narrow, understood fix" hatches, so there
  was no plan discussion. Reviewer `gpt-5.6-sol`, high effort, read-only; one
  cycle.
- **Result:** no blockers or major findings.
  - One minor finding was adopted: PLAN.md still showed v0.41.9's
    acceptance test as open, and Weather "in progress". Both are corrected.
  - Codex independently confirmed lockfile/manifest agreement, the absence of
    `react-katex` references, the native bindings for Windows and Linux, and
    the licenses of new lock entries (MIT or Apache-2.0).
  - It also confirmed that `Math.tsx` behaves like react-katex, that the
    advisory triage matches the advisories, and that the timezone tests clean
    up correctly in either order.
  - Nothing was rejected; there were no disagreements and no tracked items.
- **Limits:** Codex's read-only sandbox could not run `npm ci`,
  `npm audit`, the build, or the full suite. That evidence is Claude's.

**Review of the PR review fixes (2026-10-24).** This was a fresh session with
the same profile, because the dependency classification and lockfile changed.
- **Result:** no blockers or major findings.
- **Codex confirmed:**
  - no package, version, or integrity change in the lockfile, only the 44
    classification changes;
  - Vite and both plugins in the production graph;
  - the GNU Make dry runs for macOS, Linux, and an explicit `BROWSER`;
  - strict TypeScript on `Math.tsx`;
  - fixture isolation under pytest-xdist;
  - documentation accuracy.
- **One minor finding, open for Fred:** no automated test covers the
  `Math.tsx` error path. The repository has no frontend test harness, and
  adding one (for example Vitest) means new dependencies. Claude checked the
  error path directly against KaTeX 0.19.0:
  - invalid TeX returns KaTeX's error markup without throwing;
  - a non-string input throws the `TypeError` the code catches.

  TypeScript already rejects non-string input at build time. Nothing was
  rejected, and there are no tracked items.

## v0.41.9 — Personal imaging verdict

Merged in [PR #18](https://github.com/fbaptiste/nightcrate/pull/18) on 2026-10-24.

Replace the weather page's 0–100 imaging score with a per-night verdict
(Go / Uncertain / No / Not enough data), computed from the hourly forecast and
the user's own imaging rules, saved per location. Fred approved the
[design spec](docs/superpowers/specs/2026-10-17-weather-redesign-design.md) on
2026-10-17 after a Claude–Codex design discussion. Inserted ahead of v0.42.0;
the roadmap is not renumbered. Forecast accuracy work is out of scope.

- [x] Start from updated `main` on `v0.41.9/weather-verdict`.
- [x] Implementation plan ([plan](docs/superpowers/plans/2026-10-17-weather-verdict.md)).
  Codex plan review converged in 4 of 5 rounds with nothing rejected.
  Fred decided D1 ("Night over" once darkness ends) and authorized
  implementation.
- [x] Implementation by phase, with review (migration, API contract, and decision
  logic are high-stakes). Codex implemented three phases (rules storage and
  evaluator; data layer and endpoint; frontend); Claude reviewed each, sent one
  batch of findings per phase, re-ran the checks, and staged the work.
- [x] Migration gate: a copy of a real workspace database rolled back to 0057
  and upgraded through yoyo. The only change is the new empty table; every other
  row count is unchanged; integrity and foreign-key checks are clean; re-running
  is a no-op.
- [x] Rendered checks with Playwright: light and dark themes, 1500 px and 820 px,
  keyboard selection, live preview, Save and Cancel, presets hidden after Save,
  an unsaved draft discarded on a location switch, and the Tonight card opening
  the night's details. These ran against a disposable backend with live
  Open-Meteo data.
- [x] Documentation: development decisions, weather algorithms, README, and
  the docs index; the 0–100 model is archived.
- [x] Independent Codex review of the whole change, before Fred's
  acceptance test. A fresh read-only session found no blockers, 2 major
  issues and 4 minor ones, all accepted and fixed:
  - Editing a location's coordinates now clears its weather cache.
  - ECMWF coverage ignores elapsed and post-cap hours.
  - Moon rise and set times are in the display timezone.
  - The rules editor and bar follow imperial units.
  - The final stop-time option is offered.
  - The astronomy docs are corrected.

  A follow-up check confirmed the fixes; one further edge case (an empty
  evaluated interval inside a single hour) was fixed with a test.
- [x] **Forecaster revisions.** Fable and Astra's consolidated spec was
  planned with Codex over 5 rounds: the
  [spec](docs/superpowers/specs/2026-10-17-forecaster-revisions-design.md),
  whose §11 holds the agreed clarifications, and the
  [plan](docs/superpowers/plans/2026-10-17-forecaster-revisions.md).
  - **What it adds:**
    - total-only cloud;
    - one precipitation-chance limit, an amount threshold, and "Any model"
      amounts;
    - declared per-model coverage;
    - a shared window for short sessions;
    - vetoes, precedence and freshness;
    - per-night gear and imaging times;
    - minute re-evaluation and the "not current" state.
  - **Fred's decisions (2026-10-18):**
    - saved rules are reset (F1);
    - the gap label is "Longest interruption" (F2);
    - one precipitation-chance limit, with no hour-or-block distinction and no
      "?" marks (F3, after he saw the result).
  - **Implementation:** Codex implemented 10 tasks, and Claude reviewed each,
    ran the full suite outside the sandbox and did rendered checks:
    - the hour strip is pixel-identical against pre-change references;
    - fractional time zones line up;
    - controls and editor work against the live backend.

    The migrations were verified on a copy of a real workspace database.
- [x] **Coverage constants.** Set from a 24-hour hourly observation at three
  sites (25 runs, 2026-10-18/19; the lowest reach minus 6 h, never above the
  spec's starting values): ECMWF 334 h, GFS 353 h, ICON 158 h, best_match
  331 h (NBM was dropped with F3).
- [x] **Independent Codex review of the revisions.** A fresh read-only
  session found no blockers, no contract mismatches and no
  verdict-guarantee violations, plus 3 major findings and 1 minor. All were
  accepted and fixed:
  - a 10-minute cooldown after failed refreshes, PWV and AQ included;
  - the clock axis groups by local hour, so a half-hour DST change can't
    double the strip;
  - the coverage constants above;
  - single-model reporting when the comparison models are beyond their
    coverage.

  After the fixes, the full backend suite passes. Its first run showed a single
  failure, a coverage test pinned to the old constant; it was rewritten to set
  the long value itself.
- [x] **Batched Codex review of Claude-authored changes** (the rules-editor
  changes of 2026-10-17, the coverage constants, the docs, the agent-process
  notes). It found no blockers and confirmed the constants' arithmetic. Its
  1 major and 4 minor findings were all about wording, and all are fixed:
  - the docs now say coverage applies to model cloud and "Any model"
    amounts, while the main forecast's own fields always count;
  - the rules bar always shows the amount rule;
  - precipitation labels no longer mention gear-out or dark hours under the
    hours-lost policy;
  - the ECMWF horizon comment is corrected;
  - the ERA5 caveat is reworded.
- [x] **Cloud forecasts, plain wording, and "How the verdict works"**
  (2026-10-18).
  - **Problem:** Fred found that "models disagree" came up too often. A replay
    of 14 nights at his site gave 8 Uncertain with the preset rules.
  - **The cloud forecasts (F4):** Claude and Codex designed this blind first,
    then converged in 2 rounds, and Fred chose the majority vote. Users tick
    ECMWF, GFS and/or ICON and a preferred forecast, and by default each
    hour's cloud check follows the majority (spec §11 F4).
  - **The wording:** Codex drafted "How the verdict works" ("In one minute"
    plus "The details") and every rules label with a hover note. Claude
    checked the facts and adopted "usable time" in place of "clear".
  - **Status:** done (Codex implementation, Claude review, a fresh Codex
    review with no blockers, rendered check). Details are in the plan's F4
    section.
- [x] **Faster first forecast load and model-detail notes** (2026-10-23).
  - **Problem:** Fred found the first forecast after a backend start slow, at
    about 7.5 s. Most of the time went to Sun and Moon positions for 14
    nights, calculated every minute.
  - **Speed-up:** exact positions are now calculated at every 10th sample,
    with a smooth curve between. For 14 nights that takes 1.2 s instead of
    6.7 s, and results match exact sampling. Measured on a disposable backend
    after a restart, the first forecast now takes 1.5 s with a fresh saved
    forecast and 2.5 s with a stale one.
  - **Hover notes:** the ECMWF, GFS and ICON notes say where each model has
    finer detail, never which is more accurate.
  - **Process:**
    - the [spec](docs/superpowers/specs/2026-10-23-forecast-astronomy-speed-design.md)
      and [plan](docs/superpowers/plans/2026-10-23-forecast-astronomy-speed.md);
    - Codex plan review converged in 3 of 5 rounds with nothing rejected;
    - Fred decided to leave out Outlook nights on demand, accepted a 2 s
      tolerance for unrounded API durations, and accepted the node wording;
    - Codex implemented both tasks; Claude reviewed and staged them.
  - **Verification:**
    - 266 targeted tests pass;
    - the 210-night run showed a largest difference of 0.0003 s and no label
      changes;
    - rendered hover notes were checked in light and dark themes.
  - [x] **Fresh Codex review** (high-stakes calculation, plus Claude's
    wording and doc edits).
    - **Result:** no blockers or majors. One minor finding was fixed: the
      test's copy of the UI's number formatting now rounds midpoints like
      JavaScript (1.25 shows as 1.3), with regression cases.
    - **Not re-checked by the reviewer:** external model facts.
- [x] **Candidate preparation** (2026-10-23).
  - **Version:** files and reference headers are synchronized to 0.41.9.
  - **Coverage check against `main`:**
    - **Untested behavior found:** the dew rule when counted, missing-data
      parsing, and model-metadata defenses.
    - **Unused code found:** two cloud-model methods left over from the old
      spread code.
    - **Fix:** Codex added 27 tests and removed the methods, with no behavior
      change; Claude reviewed the work and re-ran the checks.
- [x] **Bandit findings fixed** (Fred, 2026-10-23). The three long-deferred
  low findings in [plate_solve.py](backend/src/nightcrate/services/plate_solve.py)
  are fixed, with no suppressions:
  - the two stream assertions are explicit checks that stop the solve;
  - the optional image-size fallback logs at debug instead of passing
    silently.

  Codex implemented the fixes with tests; Claude reviewed them. Bandit now
  reports no issues.
- [x] **PR review of the changes made after the independent reviews**
  (Claude's code-review agent, 2026-10-23). Two findings, both fixed in a
  follow-up commit:
  - The missing-stream check raised `RuntimeError`, which both solve routes
    report as 409 "already in progress". It now raises `OSError`, which is
    logged with a traceback and returned as 500. A one-off request through
    the route confirmed this.
  - The new unresolved-primary combiner test could not fail. It now uses an
    impossible window, which would otherwise give Uncertain.
- [x] Fred's acceptance test. Fred authorized publishing on 2026-10-23 before
  testing, planning to test before merging. He merged PR #18 on 2026-10-24.

Verified by Claude on the candidate tree:
- **Full backend suite:** 2,661 passed and 3 skipped, run with `-n auto`
  outside the sandbox after the Bandit fixes.
- **Static checks:**
  - `uv lock --check`;
  - Ruff lint and formatting;
  - Bandit: no issues;
  - frontend TypeScript and production build (the existing bundle-size
    warning remains).
- **Docs:** relative links, skill structure and `git diff --check`.
- **Branch coverage of the weather verdict modules:**
  - `forecast_coverage`, `forecast_inputs`, `imaging_hours`, `imaging_rules`,
    `imaging_session`, `imaging_types` and `services/weather.py`: 100%.
  - `imaging_verdict`: 99%. Its uncovered branches are handled earlier, and
    one is a pass-through return.
  - Line coverage that changed against `main`:
    - `astronomy` 89 → 91%;
    - `api/weather` 88 → 91%;
    - `seeing` 100 → 98%. The one uncovered line only satisfies the type
      checker and cannot run.

**Release notes (v0.41.9 revisions):**

- **Saved weather rules are reset** by migration 0059; set your rules again.
  The share rule is now "clear for at least X%" (1–100); a night exactly at
  the share is now Go.
- **Cloud** is judged on each model's total cloud. ECMWF's low, mid and high
  layers, which Open-Meteo estimates from humidity, are shown for information
  only.
- **New precipitation settings:**
  - "Maximum precipitation amount";
  - "Precipitation amount forecasts": Main forecast, or Main forecast + ECMWF,
    GFS and ICON.
  Locations keep Main forecast unless you choose otherwise.
- **Presets:** "Left out all night" uses a 10% chance limit, counts wind and
  checks every model's amount.
- **Cloud forecasts:** choose ECMWF, GFS and/or ICON and a preferred one. By
  default each hour follows the majority, with the preferred forecast breaking
  ties, so disagreement no longer makes a night Uncertain. "Show Uncertain"
  keeps the stricter comparison. Saved rules start on the majority with all
  three (migration 0062).
- **Wording:** "usable time" replaces "clear" where wind, dew, the Moon or
  precipitation also count. Every rules setting has a hover note. "How the
  verdict works" has an "In one minute" summary and a details section.
- **Per night:** gear-out and gear-in times (whole night off), or imaging
  times. "Night over" still means darkness has ended.
- **Pages** re-evaluate every minute, and an old result is marked "not
  current".
- **Faster first load:** the Weather page's first forecast after the app
  starts takes about 1.5–2.5 s instead of about 7.5 s, with the same results.
- **Model notes:** the ECMWF, GFS and ICON hover notes in the rules editor
  say where each model has finer detail (the contiguous US for GFS, Europe for
  ICON).

## v0.41.8 — Subs by filter and exposure

Merged in [PR #17](https://github.com/fbaptiste/nightcrate/pull/17) on 2026-10-17.

Below the per-filter integration bars on a project's Imaging Sessions tab, add a
table of sub counts per filter and exposure, so what is available to stack is
visible at a glance. Fred approved the scope on 2026-10-16 and chose the
abbreviated process: Claude implements directly ("Fred says so" escape hatch),
with one fresh Codex review because the `/integration` response contract changes.

- [x] Start from updated `main` on `v0.41.8/exposure-table`.
- [x] Add a per-(filter, exposure) breakdown to the integration summary. Filters
  are labelled as shot: an equipment filter by its model name (a duoband filter
  is one row, not split into its lines), other sessions by the bars' label.
  Rows merge across nights, rigs, gains, and binnings.
- [x] Show the breakdown on the Sessions tab below the bars: filter, exposure,
  sub count, and time.
- [x] Show nonzero time under 30 s as "<1m" rather than "0m" wherever the
  shared hours-and-minutes formatter is used (found during the rendered check),
  and return unrounded minutes from the API so a sub-second session is not
  reported as zero.
- [x] A project whose filters have no recorded passband (UV/IR cut, L-Pro)
  showed "No integration yet" and hid the total on the Overview. Both now key
  off the total and explain why there are no bars.
- [x] Backend tests for normal, duoband, no-passband, derived, empty,
  sub-second, and ordering cases.
- [x] Rendered check of the Sessions tab and the Overview.
- [x] Fresh Codex review of the full diff.
- [x] Fred tested the staged change on 2026-10-16 ("this is good").
- [x] Release checks; version files and reference headers synchronized to 0.41.8.

Verified by Claude: full backend suite with `-n auto` (2,555 passed, 3 skipped,
30 warnings); the two affected test modules (91 passed; coverage 100% for the
models and 97% for the router, whose new uncovered branch is unreachable under
the table CHECK); `uv lock --check`; Ruff lint and
formatting; Bandit (only the three deferred low findings); frontend TypeScript
and production build (existing bundle-size warning). Rendered with Playwright
against the running development server using GET requests only: three real
projects' rows match their session rows and integration totals, in light and
dark mode; long labels truncate with a tooltip; the Overview shows no table.
Mocked responses covered the empty project, a no-passband-only project
(Sessions and Overview), and 10 × 0.5 s showing "<1m".

### Codex review

- Mode: independent review of the full diff (contract change; Claude-authored
  under the "Fred says so" hatch, so no plan discussion). Reviewer
  `gpt-5.6-sol`, high, read-only; two cycles; converged with no remaining finding.
- Adopted: both minor findings. The empty state ignored time from filters
  without passbands, and two-decimal rounding reported a 0.1 s sub as zero
  minutes. Nothing rejected; no disagreements; no tracked items.
- Codex could not run the tests or the build: its read-only sandbox has no
  writable temporary directory. Its review was static, and the test evidence
  above is Claude's.

## v0.41.7 — Agent collaboration

Merged in [PR #15](https://github.com/fbaptiste/nightcrate/pull/15) on 2026-09-23.

Record the Claude + Codex operating model Fred approved on 2026-09-22 and apply
documentation fixes found while reconciling agent notes with the repository.
Documentation and agent instructions only; application behavior is unchanged.
Claude writes the changes (documentation with no behavior change), and one fresh
Codex review covers the whole diff before Fred's acceptance test.

- [x] Start from updated `main` on `v0.41.7/agent-collaboration`.
- [x] Add `docs/agent-collaboration.md` from the approved draft and link it from
  `CLAUDE.md`; scope the staging rule to Claude-orchestrated work.
- [x] Add the Claude-only `codex` skill: command profiles, prompt templates, and
  the before/after file inventory.
- [x] Update `start-version` (pending-outcome sweep), `sync-docs` (lifecycle
  status), and `finalize-session` (Prepare/Publish split, outcome states,
  remote SHA check).
- [x] Canary the untested Codex profile combinations in a throwaway repository.
- [x] Record constraints that existed only in agent notes: tablet input and
  touch detection, pxiproject stored-path resolution with no project-relative
  fallback, WCS pixel orientation, sensor
  effective pixels, SQLite parent-table reshapes, UI consistency, file-browser
  and stretch interactions, and persistent pages.
- [x] Fix stale references: the `frontend/README.md` persistent-pages pointer and
  the PHD2 analyzer tab list.
- [x] Remove personal details from tracked files (Fred: current files only).
  Horizon test fixtures and tests use the public test location; color-vision
  and rig attributions are reworded; the equipment context is generic.
- [x] Codex review of the full diff; release checks.
- [x] Synchronize release version files and reference headers to 0.41.7.

Verified by Claude: full backend suite with `-n auto` (2,549 passed, 3 skipped,
30 warnings); the six directly affected test files (268 passed); Ruff lint and
formatting (238 files); frontend TypeScript/production build (existing
bundle-size warning); 147 local links across 24 changed Markdown files; skill
structure and pointers; diff whitespace; a scan of added lines for private
data. Bandit found zero medium/high and the three existing low-severity
findings deferred in v0.41.6. Codex canaries and the file inventory were
exercised as described in `docs/agent-collaboration.md` §10. Application
behavior is unchanged apart from test data, comments, and calculator help text.

### Codex review

- Mode: independent review of the full diff (documentation release, so no plan
  discussion). Reviewer `gpt-5.6-sol`, high, read-only; two cycles; converged
  with no remaining blocker.
- Adopted: remaining personal attributions and an overnight-equipment quote made
  generic; the review template covers uncommitted work; the file inventory also
  detects index and status changes; canary probes use unique, cleaned-up paths;
  the `.pxiproject` guidance matches the loader (code fix deferred above); exact
  outcome-aging wording; the plan-record template requires its own list; the
  Autocomplete sorting rule. One minor finding was rejected (duplicating
  device specifications in the equipment context).

#### v0.41.7-R1 — Home-directory paths in historical plans

- **Kind:** rejected finding (independent review)
- **Claude:** `/Users/<handle>/...` paths in historical plan commands expose only
  the public repository owner's handle; rewriting ~100 lines adds churn without
  reducing exposure.
- **Codex (round 2):** "historical home-directory paths do not expose sensitive
  personal information and should not block the release."
- **Disposition:** rejected (Codex agreed). **Implementation:** n/a — no change.
- **Outcome:** pending — Claude; revisit at the next privacy review of tracked files.
- **2026-10-27 (v0.42.0 sweep):** closed as inconclusive with Fred's
  agreement. Three releases completed with no privacy review of tracked files,
  and none is scheduled. The handle is the public repository owner's name.

## v0.41.6 — General cleanup

Merged in [PR #14](https://github.com/fbaptiste/nightcrate/pull/14) on 2026-09-22.

Tighten documentation and development workflows while preserving current design
and coding decisions. Finalization and PR publication are authorized; merging
remains with Fred. Forecast redesign is deferred.

- [x] Start from updated `main` on the cleanup branch.
- [x] Condense shared instructions and retain feature constraints in a linked reference.
- [x] Consolidate useful snapshot details into README, the code map and active roadmap.
- [x] Remove the retired brief, current-state snapshot, snapshot prompt and primitive inventory.
- [x] Keep the active roadmap short; archive release history and superseded designs.
- [x] Simplify project skills, remove stale agent/tool assumptions, and preserve authorization boundaries.
- [x] Support optional, untracked local agent instructions without publishing private configuration.
- [x] Verify documentation links, retained constraints, and staged changes.
- [x] Synchronize release version files and reference headers to 0.41.6.
- [x] Complete release checks and review the release diff.

Verified by Codex: backend Ruff lint and formatting (238 files); full pytest suite
(2,549 passed, 3 skipped); frontend TypeScript/production build; 148 local links;
skill structure, version consistency, and diff/privacy checks. Acknowledgment
tables and historical plan content are preserved, with archive link repairs.

Bandit found zero medium/high and three existing low-severity findings, deferred
with Fred's approval below. The frontend build reports its existing bundle-size
warning; pytest reports 28 warnings. Application behavior, schema, and dependency
versions are unchanged.

## Roadmap

These are planned capabilities, not implemented behavior. Current functionality
is in [README.md](README.md#features); coding constraints
are in [development decisions](docs/development-decisions.md).

Fred reordered the roadmap on 2026-10-24: galleries first, then distribution.
Claude and Codex agreed the order below; Codex's first round was a blinded
pre-pass, and the second round converged. On 2026-10-26 Fred placed a native
plate solver after catalog preservation, ahead of the gallery; it is now
v0.43.0. On 2026-10-30 he added a faster star download as v0.43.1. On 2026-11-01 he
placed more deep-sky catalogs and search links as the very next version,
ahead of the gallery; it became v0.44.0. On
2026-11-03 he placed common names for galaxies and nebulae as the version
after it, also ahead of the gallery; it became v0.45.0. The gallery became
v0.46.0. On 2026-11-07 Fred placed rigs that don't change underneath their
records as the very next version after the gallery; it became v0.47.0. The
Messier checklist became v0.48.0, the active version above.
Version numbers are otherwise assigned when each version starts.

### Object search

- A submitted search matches identifiers exactly ("M1" is not M10–M110); prefix
  suggestions appear while typing. Common names and aliases are searched and
  deduplicated by object.
- Results are labelled "Main target", "In the plate-solved image", or both.
  In-field results show the solve image with the object marked; the solve image
  can differ from the gallery's main image.
- **Fred (2026-10-30): the user chooses the scope.** A search covers either
  main targets only or every catalog object identified in a project's solve.
  A project can have several main targets; the Plate Solve tab already lets
  the user tick more than one.
- In-field membership is computed at query time from stored solves through one
  shared overlap function. Stored `project_dso` rows are computed once at solve
  time, from a capped candidate list, and can be incomplete.
- Messier slots gain an "in a solved field" marker.

### Updated XISF specification (before Distribution)

Fred (2026-10-30): PixInsight has published an updated XISF specification. A
version before Distribution reviews it against NightCrate's clean-room XISF
reader (`services/xisf_io.py`) and fixes what it affects. Nothing has been
assessed yet. The review should cover:
- image data;
- compression;
- properties, including the astrometric solution;
- FITS keywords;
- reading files written by older PixInsight versions.

The review uses the published specification only, as the existing reader
does.

### Distribution

Make NightCrate installable without Python or Node, and let it update itself.
A throwaway feasibility spike starts during the gallery work, in a separate
worktree: static serving, Windows and both Mac architectures, native imports,
image decoding, one spawned processing job, and one update between test builds.

- **Production runtime.**
  - FastAPI serves the built frontend.
  - A real entrypoint: no reload, a port choice, a readiness check, a single
    instance, and `freeze_support`.
  - The version comes from package metadata, not the repository's `VERSION`.
  - Rotating log files.
  - CI runs the tests.
- **Packaged app.** A Tauri shell with a frozen Python backend.
  - cx_Freeze is tried first (PSF licence). PyInstaller (GPL-2.0) and Nuitka
    (AGPL-3.0) carry exceptions for the apps they build, but need Fred's
    licence ruling before use.
  - Targets: macOS arm64, Windows x64 and a Linux x64 AppImage; Intel Mac is
    Fred's decision.
  - ASTAP stays user-installed. The package carries sep's and py7zr's LGPL
    notices and obligations.
  - Each target gets a clean-machine test of the built artifact.
  - LAN access is off by default, and needs access protection before a package
    offers it.
- **Updates.**
  - Signed artifacts, with their signatures in an HTTPS manifest on GitHub
    Releases. The updater rejects downgrades and mismatched versions, and
    signing-key recovery is planned.
  - The update check is disclosed, can be turned off, and can be run manually.
  - Workers stop before an update installs.
  - On every workspace activation, before migrations or seed and catalog
    reconciliation, the app refuses a database newer than itself and takes a
    consistent backup.
  - Tests cover an interrupted install, a failed migration and restoring the
    backup.
  - App updates and catalog updates stay separate.
- **Decisions for Fred.**
  - Code signing: the Apple Developer Program costs US$99 a year, and Windows
    signing goes through SignPath Foundation (free for open source, subject to
    acceptance) or Azure Artifact Signing.
  - Intel Mac builds.
  - Whether the update check is on by default.
  - LAN access in the packaged app.

### Project images: file locations, watermarks and export (after Distribution)

Fred (2026-10-30) asked for these, after the installable release. Nothing is
designed yet.

- **See where each image is stored.** A project's image strip shows
  thumbnails with "Set as main image" and "Remove", but not where each file
  lives (`ImageGalleryStrip.tsx`). Show each image's full file location,
  with a way to copy it and to reveal it in Finder or Explorer. Show
  clearly when the file is missing or its drive is offline.
- **Watermark an image.**
  - Choose from several styles: position, size, opacity and font.
  - Customizable content: text, with fields such as the target, the
    capture dates or the equipment taken from the project.
  - Overlay images that keep their transparency (a logo PNG, for example).
  - The original file is never changed: a watermark makes a new image.
- **Export an image**, watermarked or not, as JPEG (with a user-chosen
  quality / compression level), PNG or TIFF.
  - Decisions for the design:
    - bit depth and colour handling for TIFF;
    - whether to carry metadata (and plate-solve WCS) into exports;
    - where exports are saved.

### Later: calibration coverage and session overlap

- Show per-light dark/flat/bias coverage from the existing `calibration_coverage`
  view. Matching remains per project and rig; there is no shared calibration
  library. Binding an existing calibration folder to a project is supported.
- Guard manual/derived session overlap so the same captures do not silently
  inflate integration. Decide warning versus reconciliation before implementing;
  the old proposed `COALESCE(manual, derived)` model is not current behavior.
  Derived rows can also become stale after catalog changes; refreshing them
  currently requires an explicit derive request.
- Promote cataloged subs or processed images into the project gallery.
- Verify against real calibration data and gallery output. Integration describes
  cataloged capture time; it does not imply which subs survived processing.

### Later: guiding association and session timeline

Guiding storage tables exist; the app does not yet populate them.

- Reuse the PHD2 parser to populate `guiding_log_file`, `guiding_sample`, and
  `dither_event`. Associate logs with the correct rig/night session; guide
  equipment comes from its declared rig.
- Derive per-sub RMS, peaks, and sample counts from the exposure's time interval;
  do not store redundant per-sub guiding aggregates.
- Embed the PHD2 analyzer as a project overlay, following the image-analyzer
  pattern. Opening from a sub/timeline scopes the view to that time range.
- Build a vertical, time-proportional timeline: time axis, continuous RA/Dec
  strip, dither markers, and exposure blocks with thumbnails/filter/HFR.
  Fold long idle gaps (about 10 minutes or more); decimate guiding data server-side.
- Reuse data/metrics and the embedded analyzer, not a rotated copy of the PHD2
  chart. Clicking a sub opens the image analyzer; clicking guiding opens PHD2.
- Include twilight, target altitude, moon altitude/separation, illumination,
  moonrise/set, and transit from the existing astronomy services.
- Verify alignment on a real night, including multiple rigs and gap folding.

### Later: capture logs and timeline context

Session-log, event and autofocus tables exist; the app does not yet populate them.

- Research/parse ASIAIR Autorun and N.I.N.A. session logs into `session_event`;
  parse N.I.N.A. autofocus JSON into `autofocus_run`.
- Add autofocus, meridian flips, filter changes, solve failures, errors/warnings,
  and header-derived gain/offset/binning changes to the timeline.
- Add optional historical conditions, frame HFR/star-count/background trends,
  sensor temperature versus set point, dew spread, and guiding SNR/star-mass bands.
- Provide a shared time readout and strip toggles. Guiding, subs, sky context,
  and events default on; trends, thermal and conditions are optional.

### Later: mosaics

- Support panel identity, framing, solves and integration rollups, with a layout
  view and multi-panel FOV preview. Preserve current multiple-main-target support.
- Settle schema/uniqueness at implementation time; old panel-0 proposals and
  integration goals predate the current schema and are not migration instructions.
- Automatic panel detection from capture headers/plans remains a separate proposal.

## Deferred — known work not yet versioned

### Weather

The forecast redesign shipped in v0.41.9 (PR #18). Deferred by its spec:
per-rig rules, forecast accuracy and validation work, and any new forecast
sources.

- **Outlook nights on demand.** Fred decided on 2026-10-23 to defer computing
  nights 8–14 only when the Outlook tab opens. It would save about 0.6 s on a
  first, uncached load. It would also need:
  - a range field on the request;
  - handling for date links into Outlook nights;
  - the tab's night count;
  - keeping per-night controls for nights that weren't returned.

  Revisit if the page still feels slow.

### Frame quality and consolidation

- Reuse stored catalog measurements in the embedded analyzer; share/cache the
  overlapping image-quality and aberration detection work.
- Consider median subsampling only with pinned measurements and deliberate stored
  metric invalidation. Evaluate larger analysis batches against cancel latency.
- Virtualize long catalog lists if needed; keep sorting/filtering server-side.
- Frontend routes currently load without code splitting; no frontend test script
  is configured. Revisit these gaps as UI work warrants.
- Consolidate the three pixel-format dispatch paths with a resolved-source loader.
- Replace `path_resolver`'s FastAPI exception with a domain exception translated
  by routers; remove the dependent string-name exception checks.

### Project workflow

- Cross-project filter search beyond the gallery and object search; planner
  "already imaged" indicators.
- Create a project from a planner target; richer home dashboard and equipment
  usage totals from catalog data.
- Track processed-image provenance (subs → stack → final).
- Collections, curated observing lists, and export/sharing integrations.
- Catalog file verification and a database backup/export interface.
- Optional file copy/reorganization; cataloging in place remains the default.
- Broader smart-scope ingest.

### Analysis tools

- Aberration heatmaps/vector fields, comparisons across frames/filters/nights,
  user zones/notes, and image/CSV exports.
- Any automatic optical diagnosis needs validation; historical angle/eccentricity
  thresholds are proposals, not established diagnostic rules.
- Background-region statistics and quality indicators while browsing frames.
- Equipment/manufacturer links for specifications, manuals, drivers, and forums.

### Found during v0.41.7 review

- `pxiproject_io.load_image_data` accepts a relative stored `filePath`, which
  resolves against the server's working directory; reject it, with a test.
- The rig form's software Autocomplete groups by category, but `/api/rigs`
  options sort software by name only, so category headers can repeat. Sort by
  category, then name.

### Planner wording

- Stale mode names: the scope toggle reads "Plan a Night" / "Full Catalog"
  ([PlannerPage.tsx](frontend/src/pages/PlannerPage.tsx)), but the empty-results
  hint says to switch to "Browse the full catalog" mode, and the Wishlist empty
  state says "Tonight or Full Catalog tabs"
  ([WishlistTab.tsx](frontend/src/components/planner/WishlistTab.tsx)).
  Approved for this list on 2026-09-23; not yet checked in the running app.

## Settled scope

Current implementation constraints are maintained in
[development decisions](docs/development-decisions.md#projects-catalog-and-sessions).
In particular: header-driven classification, project-owned file identity, declared
rigs/targets, immediate project saves, on-demand session derivation, project-local
calibration matching, and no processing accept/reject workflow.

Automatic FITS equipment inference, alias review queues, per-filter integration
goals, and the PHD2 spectrum/unguided-RA features were removed. Historical plans
must not be used to reintroduce them. Speculative AI integrations are outside the
active roadmap; their old proposals remain only in the archive.

## History and references

[The plan through v0.41.5](docs/archive/plan-through-v0.41.5.md) preserves release
history, original design proposals, and library evaluations. Consult it for
rationale, not present-day status or executable migration definitions.

- [Schema diagrams](DB_SCHEMA.md) and [DDL](DB_SCHEMA_DDL.sql)
- [Equipment seed reference](LLM_DB_SPECS.md)
- [Planner scoring](docs/planner-scoring.md) and [annual visibility](docs/planner-annual-hours-algorithm.md)
- [DSO catalog architecture](docs/dso-catalog-architecture.md)

Dependency policy is in `CLAUDE.md`; installed dependencies and acknowledgments
are in `README.md`. Recheck a candidate's license at adoption time.
