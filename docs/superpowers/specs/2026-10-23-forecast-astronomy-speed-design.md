# Faster forecast astronomy and model-detail notes — design

**Status:** Approved by Fred on 2026-10-23. Part of v0.41.9.

**Origin:** Fred found the Weather page slow after a `make dev` restart and
asked for a faster first load. While this was being designed, he also asked
for the ECMWF, GFS and ICON hover notes to say where in the world each model
has finer detail. Claude's measurements are recorded in §6. Raw spike scripts
are local and untracked.

Where this document is silent, the v0.41.9 specs and
`docs/development-decisions.md` (Weather; Locations, horizons, and target
planning) stand.

---

## 1. Why

- The first forecast for a location after the backend starts takes about
  7.5 s. Later requests take about 0.1 s.
- About 6.7 s of the first request is Sun and Moon altitude sampling for 14
  nights. The five Open-Meteo requests run in parallel and take about 1 s, and
  only when the cached forecast is past its 6-hour TTL.
- Night astronomy is cached only in process memory
  (`api/weather.py:_night_summary_cached`). Every backend restart starts
  again, including each `uvicorn --reload` after a backend file save.
- The forecast endpoint is `async def` and computes astronomy synchronously,
  so other requests wait while it runs.

## 2. Goals, non-goals, anti-goals

**Goals**

- G1. Cut 14-night astronomy from about 6.7 s to about 1.2 s on Fred's Mac,
  with no change to any value the forecast, verdict or Tonight card uses.
- G2. The ECMWF, GFS and ICON hover notes in the rules editor say where each
  model has finer detail.

**Non-goals**

- Persisting night astronomy across restarts. It would need a disk cache
  keyed by a stable sky identity, plus algorithm-version invalidation. G1
  makes it unnecessary. (Claude's call.)
- Overlapping astronomy with the Open-Meteo requests by running it in a worker
  thread. After G1 it would save about 1 s, and only when the forecast cache
  is stale (at most once per 6 h per location). It would also run astropy on a
  worker thread while other endpoints run astropy on the event loop.
  astropy's Earth-orientation (IERS) configuration and tables are
  process-global. The app turns automatic downloads off in
  `services/planner_visibility.py`. No astropy documentation found states
  whether concurrent use is safe. (Claude's call. The search was standard web
  search on 2026-10-23 and found no statement either way. The rationale was
  corrected after Codex round 1, which pointed out that the app does not
  download IERS data on demand.)
- Ranking the models by accuracy. Fred chose not to pursue accuracy work.

**Anti-goals**

- Any visible change to sunset, twilight, darkness intervals, moonrise or
  moonset times, darkness hours, moonless hours, or verdicts beyond the
  tolerances in §3.3.
- Wording that says or implies one model is more accurate in a region.

## 3. Part A — interpolated dense altitude grids

### 3.1 What changes (decided)

The two dense one-minute grids used to find crossings are:

- the 24-hour Sun grid (`_DENSE_SAMPLES = 1440`) in `compute_night_summary`;
- the 48-hour Moon grid (`48 * 60 + 1` samples) in `_moon_rise_set`.

Both keep their one-minute sample times and every downstream algorithm:
crossings, linear interpolation between samples, and `_intervals_below`. The
change is how the altitude at each sample is obtained:

- Exact astropy altitudes (`get_body` + `AltAz`, as today) are evaluated
  only at nodes, always including the grid's first and last sample.
- **Nodes:** every 10th sample of the grid, about every 10 minutes.
  - **Spacing:** a 24 h grid of 1440 samples has 1439 intervals, so its
    nodes are 600.4 s apart. On a 25 h DST night they are 625.4 s apart.
  - **Why samples:** this is the configuration the spike measured.
  - Clarified after Codex round 1, which noted that "every 10 minutes" and
    "every 10 samples" differ.
- A cubic spline through the nodes (`scipy.interpolate.CubicSpline`; scipy is
  already a dependency) gives the altitude at every one-minute sample.

All other altitude calls stay exact. These are `moon_altitudes_at`, the
5-minute moonless sampling, the 2-minute Moon polyline, and the single-instant
Moon phase. (Keeping the moonless sampling exact is Claude's call. It leaves
about 0.3 s that reusing the Moon spline could save, but it keeps the change
small.)

### 3.2 Why this approach

- The cost scales with the number of exact samples. Batching all 14 nights
  into one astropy call gave no speed-up: 1.93 s versus 1.98 s for the Sun
  grids.
- Sun and Moon altitudes are smooth on a 10-minute scale near the horizon and
  twilight thresholds. Over 15 days at Phoenix, the largest spline error was
  4.21″, at the Moon's 84° culmination, far from any threshold the code uses.
  Within 1° of a threshold (−0.833°, −6°, −12° or −18°), the error was at most
  0.002″.
- Coarser crossing search with local refinement was considered. It changes
  the crossing algorithm and can miss excursions shorter than the coarse step,
  whereas the spline keeps the algorithm unchanged.

### 3.3 Acceptance (decided)

- **Equivalence.** For the sites and dates of §6.3 and a polar grazing case
  chosen by the planner:
  - every datetime in `NightSummary` (including `dark_intervals` and
    `MoonInfo` UTC times) is within **1 s** of the exact one-minute result;
  - `darkness_hours` and `moonless_dark_hours`, which are rounded to 0.01 h,
    are identical;
  - every other field is identical. This includes None versus non-None
    values, the interval count and the local `HH:MM` strings.

  If a grazing case cannot meet this, the plan must show why and what the
  exact method itself does there. The planner must not loosen a tolerance on
  its own.
- **Downstream values (strict).** Endpoint tests compare the exact and
  spline paths for the forecast and Tonight. The full 210-night run counts
  how many Tonight-style `HH:MM` labels would differ. In those tests and that
  run, the following must be identical:
  - verdicts and reasons;
  - `HH:MM` labels;
  - rounded values.

  Clarified after Codex rounds 1–2.
- **Known limitation, not an exception.** A derived label or rounded value
  could still change if a datetime lands within its tolerance of a display or
  rounding boundary. That is inherent in any tolerance. None was observed.
- **Accepted by Fred on 2026-10-23:** compare unrounded durations in API
  responses within **2 s**, the difference of two datetimes that are each
  within 1 s. `missing_hours` on a reason is one such value.
  - **Evidence:** Codex measured `missing_hours` differing by about 3e-9 h
    (about 0.00001 s) on 18 missing-data reasons in the forecast test
    fixture.
  - **Display:** the UI shows `missing_hours` to 0.1 h.
- **Speed.** 14 nights for the public test location (Phoenix) take ≤ 1.5 s
  in a warm process on Fred's Mac. Automated tests should guard the number of
  exact evaluations rather than wall-clock time.
- **No contract change.** `NightSummary`, the API models and the frontend are
  unchanged.

## 4. Part B — model hover notes

### 4.1 What changes (decided)

The three `CLOUD_MODELS[].note` strings in
`frontend/src/components/weather/RulesEditor.tsx` gain where each model has
finer detail. Each note keeps its existing facts (detail and reach), stays at
most two sentences and about 30 words, and uses plain words. Codex drafts the
wording and Claude checks every fact. This follows the existing rule for
rules-editor hover notes and Fred's preference that Codex drafts user-facing
text.

### 4.2 Facts the notes may use

Sources: Open-Meteo's model documentation, read 2026-10-23
([GFS](https://open-meteo.com/en/docs/gfs-api),
[DWD ICON](https://open-meteo.com/en/docs/dwd-api),
[ECMWF](https://open-meteo.com/en/docs/ecmwf-api)), and Claude's live
comparisons the same day (§6.4).

- **ECMWF IFS 0.25°:** global, about 25 km everywhere, no regional
  finer-detail variant, 15-day forecast. The existing note's "about 14 days"
  is the reach NightCrate counts. Keep it.
- **GFS (`gfs_seamless`):** global GFS at about 13 km. Over the contiguous
  US, Open-Meteo blends in NOAA's 3 km HRRR, which runs 18 h (48 h for the 00,
  06, 12 and 18 UTC runs). Open-Meteo: "High-resolution data are only
  available for the United States. For other locations, only GFS is used."
- **ICON (`icon_seamless`):** global ICON at about 11 km (7.5 days). Over
  Europe, ICON-EU adds about 7 km (5 days), and over central Europe
  (Germany, Switzerland, Austria and nearby) ICON-D2 adds about 2 km
  (2 days).

The notes must not say a model is "better" or "more accurate" anywhere. They
may say its detail is finer there. The night-detail descriptions in
`frontend/src/lib/weatherVerdict.ts` (`MODEL_DESCRIPTIONS`) already state
these facts. They must stay consistent with the new notes.

## 5. Open question for Codex — loading Outlook nights on demand

Fred asked whether nights 8–14 (the Outlook tab) could be computed only when
the tab is opened. **His position:** leave it out if it truly makes no
difference. Codex is asked for an independent view, and the landing report
records both.

Facts:

- After Part A, nights 8–14 are about half of the 1.2 s. The saving would
  apply once per location per backend start, plus once per new night after
  local noon.
- The main forecast is one Open-Meteo request for all 16 days. The cloud
  and PWV requests also cover 16 days, and the aerosol request covers 7.
- The frontend sends the forecast request every 60 s and on every rules or
  night-control change. `?date=` links can open an Outlook night directly
  (`WeatherPage.tsx`). The Outlook tab label shows the number of outlook
  nights. The rules editor's "this week" counts cover nights 1–7.

## 6. Evidence (2026-10-23, Claude)

Each item is verified by running it, unless marked otherwise.

1. Running dev backend: three warm forecasts took 0.10–0.11 s. A forecast
   for a location whose cache was about 6 days old took 7.55 s cold, then
   0.10 s.
2. Fresh processes, `compute_night_summary` for 14 nights: 6.6–6.8 s at each
   of two sites (about 0.47 s a night). An in-process profile of a cold
   forecast attributed the time to `_astronomy_nights` and astropy `get_body`
   and transforms.
3. Spike (throwaway monkeypatch of `_sun_altitudes` and `_moon_altitudes`
   for grids of ≥ 1000 samples, nodes at every 10th sample plus the last):
   - **Sites and dates:** Phoenix, London, Quito, Tromsø and Sydney; 14
     nights from each of 2026-06-14, 2026-10-23 and 2026-12-14 (210 nights).
   - **Accuracy:** the largest datetime difference was 0.0003 s. Hours
     differed by < 0.0005 h. No other field differed.
   - **Speed:** 6.66 s → 1.20 s per 14 nights on average (5.6×).
   - **Remaining time (profiled):** the Moon rise/set grid, the Sun grid,
     the moonless sampling and the Moon phase, in that order.
4. Open-Meteo `cloud_cover`, 4-day request, seamless versus global model:
   - **Phoenix, GFS:** 10 of 96 hours differed, all within the first day.
   - **Munich, ICON:** 64 of 96 hours differed from global. Against ICON-EU,
     27 differed, all within about 46 hours.
   - **Barcelona, ICON:** 76 of 96 differed from global.
   - **Sydney:** both models were identical to their global versions.
5. Open-Meteo requests, five in parallel: 0.81–0.98 s across five runs at
   two sites.

## 7. Left to the planner and builder

- The code shape: a helper used by the dense callers, or an explicit option.
  The interpolation must be explicit at the call site, not triggered by grid
  length.
- Whether `compute_hourly_astro`, which has no API caller today, uses the
  helper.
- The test matrix, including the polar grazing case. Automated tests use a
  small set of nights, a few per site and season, chosen to cover the edge
  cases. The full 210-night comparison of §6.3 is run once as a recorded
  verification, not in the suite (Claude's call: it costs about 2 minutes of
  exact computation). The exact altitude functions stay callable so that both
  can compare against them.
- Tests are required for normal, edge (polar day and night, a grid length
  not a multiple of the node step, a grid whose last sample is already a
  node) and failure-adjacent cases (a grid shorter than two nodes).
  Appending the last sample without de-duplicating it makes `CubicSpline`
  reject the nodes.
  Claude's check script hit this on a 21,601-sample grid, and the
  2,881-sample Moon grid has the same shape.
