# NightCrate — active plan

**Version:** v0.42.0 — Catalog preservation, licence, planner star, mirrored overlays

**Branch:** `v0.42.0/catalog-preservation`

**Status:** Complete — awaiting merge

## v0.42.0 — Catalog preservation, licence, planner star, mirrored overlays

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
plate solver after catalog preservation, ahead of the gallery. Version numbers
are assigned when each version starts.

### Native plate solver

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

### Gallery

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

### Messier checklist

- 110 numbered slots from an explicit checklist mapping, separate from catalog
  designations: today the catalog merges M102 into M101 (110 numbers on 109
  objects), and one designation can belong to only one object.
- A slot is filled only by a project with that object among its main targets
  and a main image. The latest project wins, by latest session date: dated
  projects before undated ones, then creation time, then ID. The back of the
  card lists the other projects.
- Empty slots distinguish "no project" from "a project without an image".
- M102 needs Fred's decision; the recommendation is NGC 5866 with a note on the
  ambiguity. The M101 slot is never filled twice through the shared designation.

### Object search

- A submitted search matches identifiers exactly ("M1" is not M10–M110); prefix
  suggestions appear while typing. Common names and aliases are searched and
  deduplicated by object.
- Results are labelled "Main target", "In the plate-solved image", or both.
  In-field results show the solve image with the object marked; the solve image
  can differ from the gallery's main image.
- In-field membership is computed at query time from stored solves through one
  shared overlap function. Stored `project_dso` rows are computed once at solve
  time, from a capped candidate list, and can be incomplete.
- Messier slots gain an "in a solved field" marker.

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
