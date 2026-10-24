# NightCrate — active plan

**Version:** v0.41.10 — Dependency fixes from issue #16

**Branch:** `v0.41.10/dependency-fixes`

**Status:** Complete — awaiting merge

## v0.41.10 — Dependency fixes from issue #16

A Windows user's [issue #16](https://github.com/fbaptiste/nightcrate/issues/16)
reported `npm audit` warnings, an `npm ci` failure, and a planner crash. Fred
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
  `make` listed neither `dev` nor `help`. Its help script shows a target only
  when the line directly above it is a `## ` summary, and variable assignments
  sat in between. The variables moved up with the others; `dev` has a
  one-line summary, and its browser notes are plain `#` comments. All 11
  targets are now listed. `make -n` confirmed the `LOG` and `BROWSER`
  defaults and overrides still apply. This change came after the Codex review
  and was not part of it.
- [x] Fresh Codex review of the full diff.
- [x] Release checks; version files and reference headers synchronized to
  0.41.10. Development decisions now record that users run the Vite
  development server, the `tzdata` requirement, and the KaTeX wrapper.
- [ ] Fred's acceptance test. Fred authorized publishing on 2026-10-24.
- [x] The PR description references #16, so the reporter can see which of
  their findings this release addresses. Fred also asked for a comment on
  the issue (both 2026-10-24).

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

### v0.42.0 — Calibration coverage and gallery promotion

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

### v0.43.0 — Guiding association and session timeline

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

### v0.44.0 — Capture logs and timeline context

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

- Cross-project object/filter/date search; planner "already imaged" indicators.
- Create a project from a planner target; richer home dashboard and equipment
  usage totals from catalog data.
- Track processed-image provenance (subs → stack → final).
- Slideshows, collections, curated observing lists, and export/sharing integrations.
- Catalog file verification and a database backup/export interface.
- Optional file copy/reorganization; cataloging in place remains the default.
- Native distribution (Tauri) and broader smart-scope ingest after the core workflow.

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
