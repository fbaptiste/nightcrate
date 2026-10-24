# Faster forecast astronomy and model-detail notes — implementation plan

> **For agentic workers:** this plan follows `docs/agent-collaboration.md`.
> Codex implements Tasks 1 and 2, one at a time, in the main checkout, and
> leaves the work unstaged. Claude reviews, stages, and owns Task 3. Nobody
> commits without Fred's authorization. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Cut 14-night forecast astronomy from about 6.7 s to about 1.2 s
with unchanged results, and make the ECMWF, GFS and ICON hover notes say where
each model has finer detail.

**Architecture:**

- **Backend:** the two dense one-minute crossing grids get their altitudes
  from exact astropy values at every 10th sample plus a cubic spline. This is
  done by a new private helper in `services/astronomy.py`, called explicitly
  at those two sites. Everything downstream of the altitude arrays is
  unchanged.
- **Frontend:** a copy change to three strings.

**Tech stack:** Python 3.14, astropy, numpy, scipy (already a dependency);
React/TypeScript.

**Spec:**
[2026-10-23-forecast-astronomy-speed-design.md](../specs/2026-10-23-forecast-astronomy-speed-design.md),
approved by Fred on 2026-10-23.

**Baseline:**

- `HEAD` is `a3707b6`, with the reviewed v0.41.9 changes staged (index tree
  `2ff1178`).
- `astronomy.py`, `test_astronomy.py`, `RulesEditor.tsx` and
  `weatherVerdict.ts` have no unstaged changes.

## Global Constraints

- **Grids and nodes:** nodes go at every 10th sample (`_SPLINE_NODE_EVERY =
  10`), always including the last sample, de-duplicated. That is about every
  10 minutes: 600.4 s apart on a 24 h night, 625.4 s on a 25 h night (spec
  §3.1). Only the 24 h Sun grid in `compute_night_summary` and the 48 h Moon
  grid in `_moon_rise_set` use it.
- **Downstream values:** Tonight's `HH:MM` times and the forecast's verdicts,
  rounded hours and display strings match the exact path in the endpoint
  tests (spec §3.3).
- **Versions:** IERS behavior matches the app (`auto_download = False`,
  `auto_max_age = None`). Measured with astropy 7.2.0, astropy-iers-data
  0.2026.3.30.0.54.34 and scipy 1.17.1. The grazing cases' 2.6–2.75″ margins
  are not verified against future IERS data.
- **Unchanged code:** `compute_hourly_astro`, `moon_altitudes_at`, moonless
  sampling, the Moon polyline and the Moon phase stay exact and untouched.
- **Equivalence (spec §3.3):**
  - every datetime within 1 s;
  - `darkness_hours` and `moonless_dark_hours` identical;
  - every other field identical, including None-ness, interval counts and
    `HH:MM` strings.

  Tolerances are never loosened without Fred.
- **Contracts:** no change to `NightSummary`, `MoonInfo`, API models, routes
  or TypeScript types.
- **Off limits:** no new dependency, no migration, no threading, and no
  change to `api/weather.py` caching.
- **Hover notes:**
  - at most two sentences and about 30 words each;
  - plain words;
  - they never say or imply that a model is "better" or "more accurate"
    anywhere.
- **Codex:** never stages, commits, pushes or edits the vault notes. It runs
  only the named test modules, never the whole suite or GPU tests
  (`docs/agent-collaboration.md` §10).

## Review Focus

- **DST nights:** a noon-to-noon grid spans 23 or 25 h, so samples aren't
  exactly one minute apart and nodes are 625.4 s apart on the 25 h night.
  The spline is parameterized by elapsed seconds. Pinned by the London
  2026-10-24 case in Task 1.
- **Grazing thresholds:** a minimum within arcseconds of −18° can create or
  lose a short interval. Pinned by the 48.5640°N / 48.5655°N cases in Task 1.
- **Very short grids:** fewer than 4 nodes fall back to exact evaluation and
  must not raise. Pinned by the helper tests in Task 1.
- **Non-zero elevation:** `_make_location` uses elevation. Pinned by the
  Phoenix case at 331 m in Task 1.
- **A moon that doesn't rise or set in the 48 h window:** `tromso-summer`
  and `split-astro` have neither, while `tromso-winter` has both (Codex round
  1 measured 12:43 and 19:23). Task 1 asserts this in the exact baseline, so
  both branches are exercised.

---

### Task 1: Spline-interpolated dense altitude grids (Codex; high-stakes)

**Files:**

- Modify: `backend/src/nightcrate/services/astronomy.py`:
  - constants near line 28;
  - the new helper after `_moon_altitudes` (about line 162);
  - `compute_night_summary` about line 521;
  - `_moon_rise_set` about line 405.
- Create: `backend/tests/test_astronomy_spline.py`
- Modify: `backend/tests/test_weather_api.py` and
  `backend/tests/test_calculators.py`, adding one endpoint-equivalence test
  each.

**Interfaces:**

- Produces:
  - `_SPLINE_NODE_EVERY: int = 10`, with the comment "exact altitude every
    10th sample of a one-minute grid; cubic spline between".
  - The helper:

    ```python
    def _spline_altitudes(
        altitude_fn: Callable[[Time, EarthLocation], np.ndarray],
        times: Time,
        location: EarthLocation,
        node_every: int = _SPLINE_NODE_EVERY,
    ) -> np.ndarray
    ```

  - **Nodes:** indices `0, node_every, 2·node_every, …`, plus `len(times) - 1`,
    de-duplicated in ascending order.
  - **Fewer than 4 nodes:** return `altitude_fn(times, location)` unchanged.
  - **Otherwise:** call `altitude_fn` once with `times[nodes]`, then evaluate
    `scipy.interpolate.CubicSpline` (default boundary condition) at
    `x = (times - times[0]).sec`. Node samples equal the exact values.
  - `Callable` comes from `collections.abc`.
- Call sites, which must stay explicit:
  - `sun_alts = _spline_altitudes(_sun_altitudes, times, location)` in
    `compute_night_summary`;
  - `moon_alts = _spline_altitudes(_moon_altitudes, times, location)` in
    `_moon_rise_set`.

  Look the functions up as module globals at call time, so tests can
  monkeypatch `astronomy._sun_altitudes` and `astronomy._moon_altitudes`.

- [ ] **Step 1: Write the helper tests in `test_astronomy_spline.py`.**
  - **IERS:** a module-level autouse fixture applies the app's IERS
    settings with `astropy.utils.iers.conf.set_temp("auto_download", False)`
    and `set_temp("auto_max_age", None)`.
  - **Synthetic `altitude_fn`:** it records each call's `times` and returns
    `60 * np.sin(2 * np.pi * (times.jd - times.jd[0]))`, a 24 h sinusoid in
    degrees.
  - **Grids:** build them with `astronomy._make_time_grid`.
  - `test_spline_nodes_include_last_sample`:
    - 1440 samples: one call of 145 samples;
    - 2881 samples: one call of 289;
    - 1445 samples: one call of 146.

    In each case, the requested times' first and last values equal `times[0]`
    and `times[-1]`, and they are strictly increasing.
  - `test_spline_matches_exact_at_nodes`: the result equals
    `altitude_fn(times)` at every node index, to 1e-12.
  - `test_spline_error_bound_smooth_curve`: on 1440 samples, max
    `|spline − exact|` < 1e-5 degrees.
  - `test_spline_short_grid_falls_back_to_exact`:
    - 21 samples (3 nodes): one call of 21 samples, and the result equals
      the exact values;
    - 2 samples and 1 sample: no exception, and the exact values come back.
  - `test_spline_non_minute_spacing`: a 25 h grid of 1440 samples, the DST
    shape, where samples are about 62.5 s apart. The error is < 1e-5
    degrees, and nodes still include the last sample. Claude's check gave
    1.2e-6, and 5.8e-7 for the 24 h and 48 h grids.
- [ ] **Step 2: Run them and confirm they fail.** Run
  `cd backend && uv run pytest tests/test_astronomy_spline.py -q`. Expected:
  failure on `AttributeError ... _spline_altitudes`.
- [ ] **Step 3: Implement** `_SPLINE_NODE_EVERY` and `_spline_altitudes` as
  specified, with a docstring that states the node rule and the fallback.
- [ ] **Step 4: Write the integration tests** in the same file.
  - `test_night_summary_exact_evaluation_counts`:
    - monkeypatch `astronomy._sun_altitudes` and `astronomy._moon_altitudes`
      with wrappers that record `len(times)` and delegate to the originals;
    - run `compute_night_summary(33.4484, -112.0740, 331.0, date(2026, 10,
      23), "America/Phoenix")`;
    - assert the Sun call sizes are exactly `[145]`, that 289 is among the
      Moon call sizes, and that no Moon call exceeds 289.
  - `test_night_summary_equivalent_to_exact`, parametrized over the cases
    below:
    - baseline: inside `monkeypatch.context()`, replace
      `astronomy._spline_altitudes` with
      `lambda fn, times, location, node_every=10: fn(times, location)`;
    - after the context exits, compute normally, with a recording wrapper on
      `astronomy._sun_altitudes`. Assert that its call sizes are `[145]`, so
      the fast run really used the spline;
    - compare with a recursive helper `_assert_equivalent(exact, fast)` over
      the dataclass fields: `datetime` within `timedelta(seconds=1)`;
      `dark_intervals` with the same keys, the same lengths and each endpoint
      within 1 s; everything else, including the rounded hours, the `HH:MM`
      strings and None-ness, with `==`.

    | id | lat | lon | elevation_m | night | timezone |
    |---|---|---|---|---|---|
    | phoenix | 33.4484 | -112.0740 | 331.0 | 2026-10-23 | America/Phoenix |
    | london-dst | 51.5074 | -0.1278 | None | 2026-10-24 | Europe/London |
    | quito | -0.1807 | -78.4678 | None | 2026-10-23 | America/Guayaquil |
    | sydney | -33.8688 | 151.2093 | None | 2026-12-14 | Australia/Sydney |
    | tromso-summer | 69.65 | 18.96 | None | 2026-06-14 | Europe/Oslo |
    | tromso-winter | 69.65 | 18.96 | None | 2026-12-14 | Europe/Oslo |
    | split-astro | 84.5 | -15 | 0 | 2026-12-21 | UTC |
    | graze-below | 48.5640 | 7.75 | None | 2026-06-20 | Europe/Paris |
    | graze-above | 48.5655 | 7.75 | None | 2026-06-20 | Europe/Paris |

  - `test_grazing_cases_are_grazing`: in the exact baseline,
    `graze-below.dark_intervals["astronomical"]` has length 1 with a
    duration under 10 minutes, and `graze-above`'s is `[]`. This guards the
    purpose of those two cases. Codex round 1 measured 169.3 s and none.
  - `test_moon_branch_cases`: in the exact baseline, `tromso-winter` has both
    `moonrise_utc` and `moonset_utc` set, and `tromso-summer` and
    `split-astro` have both `None`.
  - **Endpoint equivalence for the forecast,** in `test_weather_api.py`:
    `test_forecast_response_equivalent_to_exact_astronomy`.
    - Use the existing `_location` and `_forecast(client, body)` helpers:
      fixed `NOW`, mocked `_load_forecast_data`, and the attended preset.
    - Run once inside a `monkeypatch.context()` that makes
      `nightcrate.services.astronomy._spline_altitudes` exact, and call
      `nightcrate.api.weather._night_summary_cached.cache_clear()` before
      each run.
    - Compare the two JSON bodies recursively. ISO-8601 datetime strings
      must be within 1 s. Unrounded duration fields (`missing_hours`) must
      be within 2 s, that is 2/3600 h. Fred accepted this on 2026-10-23
      (spec §3.3).
    - Each tolerated `missing_hours` pair must also format identically
      through a Python mirror of the UI's `compact()`
      (`weatherVerdict.ts:101-104`): an integer prints as is; anything else
      gets one decimal, with a trailing `.0` removed.
    - Every other value must be equal, including verdicts, reason codes,
      rounded hours, `HH:MM` strings and list lengths.
    - Keep the default fixture's missing-data nights: it supplies 240 hours,
      so later nights exercise missing-data reasons.
    - About 8 s of exact computation (14 nights).
  - **Endpoint equivalence for Tonight,** in `test_calculators.py`:
    `test_tonight_response_equivalent_to_exact_astronomy`. Use the
    `phoenix_location_id` fixture, an explicit `date`, and the same
    comparison. Every `HH:MM` field must be identical.
- [ ] **Step 5: Wire the two call sites** as in Interfaces. Update the
  comment in `_moon_rise_set` ("1-minute resolution …") to say the samples
  are one minute apart, with exact values at every 10th sample (about 10
  minutes) and a spline between.
- [ ] **Step 6: Run the targeted checks.**

  ```bash
  cd backend
  uv run pytest tests/test_astronomy_spline.py tests/test_astronomy.py \
    tests/test_weather_api.py tests/test_calculators.py \
    tests/test_calculators_edge_cases.py tests/test_imaging_session.py -q
  uv run ruff check src/ tests/
  uv run ruff format --check src/ tests/
  uv run bandit -r src/
  ```

  Expected: all pass, and no existing test changes.
- [ ] **Step 7: Leave the work unstaged** and report in the handoff's
  format.

### Task 2: Model hover notes say where detail is finer (Codex)

**Files:**

- Modify: `frontend/src/components/weather/RulesEditor.tsx`, the
  `CLOUD_MODELS[].note` strings at lines 52, 58 and 64.
- Modify: `frontend/src/lib/weatherVerdict.ts`, `MODEL_DESCRIPTIONS` at
  lines 267–278.
  - GFS's "Over the US" becomes "Over the contiguous US" (HRRR is CONUS
    only; Codex round 1).
  - Change anything else there only if it contradicts spec §4.2, and report
    any change.

**Interfaces:** none. The strings only.

- [ ] **Step 1: Draft three notes** from spec §4.2's facts only. Each note
  keeps its current detail and reach facts ("about 14 days", "about 15
  days", "almost 7 days"). Say where detail is finer: everywhere the same
  for ECMWF; over the contiguous US for the first day or so for GFS; over
  Europe, and most of all central Europe, for ICON. Never "better" or "more
  accurate". At most two sentences and about 30 words each.
- [ ] **Step 2: Run** `cd frontend && npm run build`. Expected: success.
- [ ] **Step 3: Report** the three strings verbatim, with a word count for
  each, and leave the work unstaged.

### Task 3: Verification and documentation (Claude)

- [ ] **Review Task 1** per `docs/agent-collaboration.md` §4:
  - an inventory before and after;
  - read the full diff;
  - re-run Step 6;
  - stage what's accepted.
- [ ] **Full equivalence run:** a record-folder script compares the staged
  implementation with an exact baseline over spec §6.3's 210 nights, using
  the app's IERS settings. It records:
  - the largest datetime difference;
  - any other field difference;
  - how many Tonight-style `HH:MM` labels (sunset, twilights, sunrise,
    moonrise, moonset) would differ.

  Pass: spec §3.3, and no label differences.
- [ ] **Speed:** in a process that has already run one unrelated astropy
  Sun/Moon calculation:
  - call `_night_summary_cached.cache_clear()`, then time
    `_astronomy_nights` for Phoenix;
  - assert 14 summaries were returned and `cache_info().misses == 14`;
  - pass: ≤ 1.5 s, against about 6.7 s before.

  Also record a cold `POST /api/weather/forecast` after a backend restart,
  with the weather cache fresh and with it stale.
- [ ] **Review Task 2:**
  - fact-check each string against spec §4.2;
  - cut wording that runs long;
  - `npm run build`;
  - a rendered check with Playwright: hover ECMWF, GFS and ICON in the rules
    editor in light and dark themes at 1500 px and 820 px, and confirm each
    note fits and reads correctly.
- [ ] **Docs (`sync-docs`):**
  - `docs/weather-algorithms.md`: the sunset and twilight method, about line
    130, and moonrise, about line 225;
  - `docs/development-decisions.md`, Locations…: one bullet on the node rule,
    the equivalence requirement and the exact-only calls;
  - `PLAN.md`: a v0.41.9 item and a release note.
- [ ] **Independent review:** a fresh read-only Codex review of Task 1
  before Fred's acceptance test (high-stakes: a scientific calculation).

## Not in this plan

Loading Outlook nights on demand (spec §5). Fred's position is to leave it
out unless it truly makes a difference.

- **Codex (round 1, independent):** "Record 'meaningful saving, deferred for
  complexity,' rather than 'makes no difference.'" It estimates about 0.6 s
  on an uncached first load.
- **Claude** agrees on the number and the deferral.
- **Fred's decision (2026-10-23):** leave it out. Record it as "a small
  saving, deferred for complexity". Revisit it if the page still feels
  slow after this change. Task 3 adds it to PLAN.md's deferred Weather
  list.

## Codex review

- **Mode:** independent plan review. On the lazy-loading question, Claude's
  view was withheld until round 2. Rounds: 3/5. Records:
  `.superpowers/codex/v0.41.9/` (local), items 177–183.
- **Adopted changes:**
  - **Spec:**
    - nodes are every 10th sample (about 10 minutes);
    - the thread rationale is corrected (the app disables IERS
      auto-download);
    - §3.3 separates strict acceptance, a known limitation and a proposed
      duration tolerance.
  - **New tests:**
    - endpoint-equivalence tests for the forecast and Tonight, with the
      UI-formatting check for `missing_hours`;
    - explicit Moon-branch assertions;
    - IERS settings applied in the new test module.
  - **Stronger verification:**
    - the speed check clears the cache and asserts 14 misses;
    - the test isolation is scoped;
    - the requested node times are asserted;
    - the 210-night run counts `HH:MM` label differences;
    - astropy, IERS-data and scipy versions are recorded.
  - **Copy:** GFS "contiguous US" in `MODEL_DESCRIPTIONS`.
- **Rejected material findings:** none.
- **Unresolved disagreements:** none.
- **Claude's counter, accepted by Codex in round 2:** no constructed
  verdict-boundary test.
- **Fred's decisions (2026-10-23):**
  - Outlook on demand: left out.
  - The 2 s tolerance for unrounded durations: accepted.
  - The node-spacing wording (every 10th sample, about every 10
    minutes): accepted.
  - Final plan: approved.
- **Fresh independent review (2026-10-23):**
  - one minor finding: `_compact_duration` rounded midpoints unlike JS
    `toFixed`;
  - fixed by the writer with `Decimal` `ROUND_HALF_UP` and six regression
    cases;
  - re-run by Claude: 53 passed;
  - no blockers, majors or disagreements. Records 195–200.
- **Status at candidate preparation (2026-10-23):** no tracked items.
