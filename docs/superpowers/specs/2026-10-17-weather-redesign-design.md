# Weather Forecast Redesign — Personal Imaging Verdict

**Status:** Approved by Fred (2026-10-17). **Revised** by the
[forecaster revisions spec](2026-10-17-forecaster-revisions-design.md)
(2026-10-18), which governs wherever the two differ. That includes the cloud rule
(§4.1), the presets (§3.2), "Imaging until" (§3.4, now per-night gear and
imaging times), model comparison (§4.3) and freshness (§4.4).

**Origin:** Fred's report that the imaging forecast misses in both directions
(good nights scored bad, bad nights scored good), and that even a correct number
"didn't decide it". Designed with Fred in brainstorming, with a Claude–Codex
design discussion (blinded pre-pass plus one comparison round; local record in
`.superpowers/codex/2026-10-17-weather-redesign/`). UI choices were made from
browser mockups.

---

## 1. Intent

The forecast should answer one question at a glance: **can I image tonight, the
way I image?** It does that with a per-night verdict computed from the hourly
forecast and the user's own rules, which are saved per observing location.

Today the night's number is the mean of `100 × availability × quality` over the
dark hours (`api/weather.py:780-790`). That is wrong for everyone:

- Three perfect hours plus five cloudy ones average to "Marginal". That is a
  "No" for an all-night unattended imager, and a "Go, 21:00–00:00" for someone
  who wants a two-hour window.
- It blends factors that decide whether the scope goes out (cloud, rain) with
  weak estimates (seeing, transparency) and target-dependent context (moon).
- No tuning of constants fixes this. Fred's view: what matters is the hourly
  conditions plus what each user cares about. A single blended number can't
  express "any chance of rain and the scopes don't go out".

## 2. Goals, non-goals, anti-goals

**Goals**

- One categorical verdict per night: **Go / Uncertain / No / Not enough data**.
  Every non-Go verdict carries a one-line reason. Every verdict shows clear
  hours and, where it applies, the clear window.
- Personal rules, saved per location. They must cover an all-night unattended
  imager (Fred), a short-session attended imager, and a dome or roll-off
  owner.
- An hourly breakdown that shows each forecast value against the user's own
  limit.
- The Tonight calculator shows the same verdict from the same evaluator.

**Non-goals (explicitly out of scope)**

- **Forecast accuracy work.** No benchmarking of models, no forecast snapshots
  or history, no "how did the night go" feedback, no validation against
  captures, and no new sources (NWS, ECMWF HRES 9 km). Fred: "let's just assume
  the open meteo models being used are going to be as accurate as we can get,
  and go from there".
- Per-rig rules (for example, a wind limit by OTA size). Deferred. The
  evaluator takes resolved rules, so rig-at-location overrides can be added
  later without moving storage.
- Weighting sliders ("how much each factor matters").
- Seeing or transparency limits. The estimates are too rough to rule a night
  in or out.
- Target-specific moon separation. That belongs to the target planner.
- Notifications or scheduled checks. The app stays request-driven.

**Anti-goals (failure even if it "works")**

- Reintroducing a blended score in any form: a secondary quality grade, a
  hidden sort key, or a 0–100 badge next to the verdict.
- Treating a missing value as a good value. Missing rain probability counts as
  0% today (`api/weather.py:723-726`), and missing transparency counts as 50
  (`services/transparency.py:98`). Both must stop.
- A verdict the user can't trace. Every verdict must be explainable from the
  checklist and the hourly grid on screen.
- Quietly loosening a user's literal rule. A 0% rain limit means 0%; it is not
  rounded to 10%.

## 3. Rules model

### 3.1 Fields

Rules are saved per location. Units are stored in metric and displayed
according to `weather_units`.

| Field | Values | Notes |
|---|---|---|
| Session style | `all_night` or `short_session` | |
| All night: minimum clear fraction | % of dark time, `>` comparison | Fred: more than 50% |
| All night: minimum clear hours | hours | Guards short summer nights |
| All night: longest cloudy stretch | hours, or no limit | |
| Short session: hours in a row | hours | Contiguous |
| Darkness | astronomical −18°, nautical −12°, civil −6° | Independent of moon. Today it is coupled to the moon toggle through narrowband mode (`api/weather.py:503`). |
| Clear-hour cloud ceiling | % | Compared with effective cover: max of total and every layer, as today |
| Gear-out interval | minutes before sunset, minutes after sunrise | Default 30 / 30 |
| Rain chance limit | % per hour | Plus: any forecast rain amount > 0 fails |
| Rain policy | `night_off` or `hours_lost` | `night_off`: rain risk anywhere in the gear-out interval makes the night No. `hours_lost`: affected hours just don't count as clear. |
| Wind | counted on/off; max sustained, max gust | Off: wind contributes nothing to the verdict |
| Dew | counted on/off; minimum temperature − dew point | Off: shown as an advisory only |
| Moon must be down | on/off | Broadband option; off means the moon is context only |

Session style and attendance are independent; the rain policy carries the
attendance meaning.

### 3.2 Presets

Presets fill the editor only for a location with **no saved rules**. Once rules
are saved, presets are no longer shown (Fred, 2026-10-17). "Copy from another
location" remains available as a small link.

| Preset | Session | Rain | Wind | Other |
|---|---|---|---|---|
| Left out all night | all night, > 50%, ≥ 2 h | 0%, `night_off`, ±30 min | off | cloud ≤ 20%, astronomical |
| Attended session | short, 2 h in a row | 20%, `hours_lost` | on | cloud ≤ 20%, astronomical |
| Dome / roll-off | all night, > 50%, ≥ 2 h | 20%, `hours_lost` | off | cloud ≤ 20%, astronomical |

All preset numbers except Fred's own (> 50%, 0% rain, wind off) are **Claude's
starting values, not validated thresholds**. The UI presents them as starting
preferences, never as safety ratings. Fred reviews them with this spec.

**Location without saved rules (Claude's call).** The forecast is evaluated
with the "Attended session" preset, and a visible prompt says the rules are
defaults and invites the user to set their own.

### 3.3 Storage

- A new typed table with a 1:1 relationship to `location` (`location_id`
  primary key and foreign key, `ON DELETE CASCADE`), added by a forward
  migration.
  - Typed columns with CHECK constraints for the enumerations.
  - Nullable only where "no limit" is a real value (the cloudy-gap limit).
  - The table name is the builder's choice.
- The row exists only once the user saves. "No row" is what triggers presets.
- Locations are soft-deleted (`active = 0`), so rules survive a restore. The
  cascade applies only to a hard delete.
- This is high-stakes work under `docs/agent-collaboration.md` §5. Verify the
  upgrade on a copy at the preceding migration and on a fresh database, with
  integrity and foreign-key checks.
- **Existing `weather_moon_penalty` setting (Claude's call).** It no longer
  drives anything: the moon is context, and darkness has its own rule. The
  builder removes its UI and its use. Whether the Settings field is deleted or
  left inert is decided in the plan; existing stored rows must not break
  loading.

### 3.4 Per-night "Imaging until"

An optional per-night end time, set from the night's details panel. "Best
2 h" must not land at 03:00 for someone stopping at midnight. It is
session-only UI state and is never saved (Claude's call). The detail panel
shows when it is active.

What it changes (Claude's call):

- **Every session style.** The night ends at that time: dark time, clear time,
  minimum hours and gap tests all stop there.
- **The gear-out interval** also ends there. The gear comes in, so later rain
  no longer matters for `night_off`.
- **The server re-evaluates that night with the override.** The week row and
  the details panel always show the same verdict.

## 4. Evaluation

The evaluator is pure, lives in `services/`, and takes resolved rules plus
hourly data. It is shared by the Weather page, the editor preview, and Tonight.

### 4.1 Per hour

- **Dark minutes:** the exact overlap of the hour with sun ≤ the darkness
  threshold. This is the same exact-overlap method as today, joined by
  absolute UTC.
- **Clear:** the hour has dark minutes, and every *counted* requirement passes:
  - cloud ≤ ceiling;
  - rain chance ≤ limit and rain amount = 0;
  - wind and gusts ≤ their limits (if counted);
  - dew spread ≥ its limit (if counted);
  - moon altitude < 0 (if required).
- Clear time is counted in dark minutes, so partial twilight hours count
  partially.
- **Missing data:**
  - A known failure stays failed, even when another input is unknown.
  - An hour with an unknown *counted* input and no known failure is
    **unknown**.
  - A missing input that isn't counted never blocks anything.
- **Reasons:** each hour records its failing requirement(s), which drive the
  hour colours and the reason line.

### 4.2 Per night

The night runs from local noon to noon. The gear-out interval runs from sunset
minus the "before" minutes to sunrise plus the "after" minutes.

- **Rain, `night_off`:** any hour overlapping the gear-out interval with
  probability > limit or amount > 0 makes the night **No** ("Rain chance 20%
  from 03:00–05:00 — your limit is 0%"). This includes twilight and cloudy
  hours: the gear is out.
- **All night:** **Go** when all three hold:
  - clear dark time ÷ total dark time > the minimum fraction;
  - clear dark time ≥ the minimum hours;
  - the longest contiguous non-clear dark stretch ≤ the gap limit, if one is
    set.

  Otherwise **No**, and the reason names the binding rule ("Mostly cloudy —
  21% of dark hours clear").
- **Short session:** **Go** when the longest contiguous clear dark stretch,
  clipped by "Imaging until", is ≥ the required hours. The verdict names that
  window.
- **Not enough data:** if unknown hours could change the outcome, the verdict
  is Not enough data, with a reason ("Rain chance not forecast after 01:00").
  If the night fails even with every unknown treated as favourable, it is
  **No**.
- **No darkness:** a night that never reaches the darkness threshold (polar
  summer, or a −18° setting at high latitude) is **No — never dark enough for
  your setting**. It is not "missing data".
- **Polar fallback:** when there is no sunset or sunrise to anchor the
  gear-out interval, the builder bounds it to the noon-to-noon night and
  documents the choice.

**A night already under way is judged on the rest of the night** (Fred,
2026-10-17).

- Once the current time is inside a night, only the time from now to the end
  counts. That applies to dark time, clear time, the fraction, minimum-hours
  and gap tests, the short-session window, and the gear-out interval for rain.
  At 21:00, a shower chance at 17:00 no longer matters. At 01:00, the clear
  share is measured on what remains.
- Tonight's row stays in the list until local noon the next day; today it
  disappears at 00:00 (`api/weather.py:897-898`). Fetch whatever earlier hours
  that needs (for example Open-Meteo `past_days`).
- The details panel shows elapsed hours, faded, and says the verdict covers
  "from now".
- Tonight's verdict depends on the time of day, so the evaluation must not be
  cached past the current hour.
- Tonight and the first week row use the same night definition. Today Tonight
  uses `todayInTimezone`.
- Once darkness has ended (or the gear-out interval has ended, if that is
  earlier), the row stays until noon, greyed, with "Night over" in place of
  a verdict. Its hours stay visible in the details. Fred chose the darkness
  end, 2026-10-17: with no dark time left, nothing can be imaged.

### 4.3 Uncertain (model disagreement)

- The three cloud models already fetched (ECMWF IFS 0.25 primary, GFS, ICON;
  `services/weather.py:58-59`) are each evaluated as a **complete sequence**
  through the same rules. All other inputs are held at the primary values.
  - This replaces today's approach of picking each hour's extreme model and
    averaging the extremes, which can produce a night no model predicts
    (`api/weather.py:578-601, 798-810`).
- When models covering the night reach different Go/No verdicts, the night is
  **Uncertain**, and the reason names who says what ("Models disagree after
  22:00: ECMWF clear, GFS cloudy").
- For short sessions, models are compared on the primary model's proposed
  window. Two clear windows at different times are not agreement.
- When only one model covers the night (ICON's horizon ends early), show its
  verdict with a "single model" note.
- No percentage confidence anywhere: model agreement is not a calibrated
  probability.
- **Sources stay as they are** (Fred). Cloud comes from ECMWF; everything else,
  including rain probability, from Open-Meteo `best_match`. Only cloud varies
  between the model evaluations, as today.
- **A model counts for a night** only if it covers every hour of that night.
- **When ECMWF cloud is unavailable** (Claude's call): the request failed, or an
  hour is missing, and no usable cached ECMWF data exists.
  - The verdict falls back to `best_match` cloud, as the code does today
    (`_cloud_for`). The fallback is never silent.
  - The page says "Cloud from Open-Meteo's default model — ECMWF unavailable",
    and that night carries a single-model note with no agreement check.
  - Rejected: blanking the week to Not enough data over one failed request.

### 4.4 Freshness

- Today a cache entry older than its TTL is never served, so a failed fetch
  fails the request. That contradicts `docs/development-decisions.md:360`.
- New behaviour: after a failed fetch, serve stale data with its age shown, but
  never an affirmative verdict from stale decisive data. The night shows Not
  enough data ("Forecast is 9 h old — refresh failed").
- The page shows when the forecast was fetched, and has a Refresh control.
- Serving stale data requires changing the startup purge: `main.py:168-177`
  deletes rows older than twice the TTL.
- **Source priority for decisive data:**
  1. Fresh ECMWF.
  2. Stale ECMWF, shown with its age, but never giving Go.
  3. The labelled `best_match` fallback (§4.3).

### 4.5 Context values

These are shown and never counted:

- Seeing and transparency (labelled "estimate"; missing stays missing).
- Temperature, dew-point gap, moon altitude and illumination, gusts and wind
  when wind isn't counted, and visibility.
- There is one dew definition throughout. Today there are three: a ≤ 2 °C flag,
  1/3/5 °C classes, and a ≥ 3 °C safe window. The builder unifies them, and the
  counted dew limit uses the same quantity.

## 5. UI

The mockups live in `.superpowers/brainstorm/` (local):

- `week-layout.html`: Fred chose layout B.
- `night-detail.html`: Fred chose A, the numbers grid.
- `rules-editor.html`: Fred accepted it, with presets shown for new locations
  only.

Colours follow the project rules: blue, orange, and grey/teal, with a text,
shape or pattern on every state.

### 5.1 Weather page

- **Top bar:** location picker; when the forecast was fetched; Refresh.
- **Rules bar:** a one-line summary of the location's rules, with an
  **Edit rules** button. The verdict is always read as personal: "Your rules ·
  Backyard".
- **Week list (layout B):** one row per night.
  - **Date.**
  - **Verdict pill:**
    - Go: blue filled, ✓.
    - Uncertain: orange outline, ?.
    - No: grey filled, ✕.
    - Not enough data: dashed outline, –.
  - **Hourly strip on a shared clock.** Every row uses the same hour columns,
    so windows line up down the week. The span covers the earliest gear-out
    start to the latest gear-out end across the displayed nights. Hour cells:
    - clear: solid blue;
    - too cloudy: grey hatch;
    - rain over the limit: orange dots;
    - models disagree: blue/grey stripes;
    - not forecast: dashed outline;
    - twilight / not dark enough: dim;
    - another counted failure (wind, dew, moon): one shared pattern, with the
      reason on hover or tap. Builder's choice within the palette rules.
  - **Reason and hours:** the reason line, then clear hours ("7.5 h clear of
    9.5"), the window when relevant, and moon phase and set time as context.
- Selecting a row outlines it and opens the **night details panel** below the
  list, with a close button (project drill-down rule).
- **Legend** under the list.
- **DST nights** (23 or 25 h) must render correctly on the shared clock. The
  builder decides how.

### 5.2 Night details panel (numbers grid)

- **Header:** night (date → next date), the **Imaging until** control, Close.
- **Checklist:** each rule with its actual value next to its limit. Examples:
  - ✓ "Clear dark hours 7.5 of 9.5 h (79%) — you need more than 50% and at
    least 2 h".
  - ✕ "Rain while gear is out (17:45–06:55): highest hourly chance 20% at 03:00
    — your limit is 0%; forecast amount 0.0 mm".
  - ✓ / ? "Models agree" / "Models disagree".
  - – "Wind not counted — gusts reach 36 km/h at 03:00".
  - Context lines for moon and dew.
- **Rain wording:** "highest hourly rain chance". Never compute a whole-night
  rain probability: hours are not independent.
- **Hourly grid,** aligned to the week strip's clock. Each cell shows the
  value; it is tinted blue when within the limit and hatched orange (cloud
  failures: grey hatch) when over it. Twilight columns are faded.
  - **Counts toward your verdict:**
    - Cloud total %, with low/mid/high on a sub-row;
    - Rain chance %;
    - Rain amount (mm or in);
    - Darkness (sun, dusk, dark, dawn);
    - wind, dew and moon rows when counted.
  - **Not counted (your rules):** the rows of disabled rules, dimmed.
  - **For information:** temperature, dew-point gap, moon altitude, seeing
    (estimate), transparency (estimate).
- A **"Show each model's cloud"** checkbox adds ECMWF, GFS and ICON cloud rows.
  It is on by default for Uncertain nights (Claude's call).
- The right-hand column summarises each row ("max 18% · limit ≤ 20%").
- Exact values come from the grid itself: no charts (Fred found the chart
  version unreadable for subtle changes).

### 5.3 Rules editor

- Opens under the rules bar on the Weather page, with **Cancel** and
  **Save for ⟨location⟩**.
- While editing, the week list re-evaluates with the draft rules (live
  preview). A summary line reads "With these rules this week: 3 Go ·
  1 Uncertain · 2 No · 1 Not enough data".
- **Layout:** Dark means on its own row, since every rule except the gear-out
  rain window is judged on dark hours; then three groups.
  - **How you image:** session style, showing only the selected style's fields
    (like tabs). An invalid value in the hidden style's fields says where to
    fix it. (Changed after Fred's review, 2026-10-17.)
  - **Cloud and rain:** cloud ceiling; rain chance limit; rain policy radio;
    gear-out minutes shown only under `night_off`, where they apply.
  - **Optional limits:** wind, dew, moon, each with a checkbox. Disabled
    fields are dimmed.
- Presets appear only for a location with no saved rules (§3.2).
- The editor states that changes apply only to that location.

### 5.4 Tonight calculator

- Replace its quality badge with the week-view card style (Fred's suggestion,
  from layout A): date, verdict pill, reason, mini hourly strip, clear hours
  and window, moon.
- Clicking the card opens the Weather page on that location and night
  (`/weather?location=…&date=…`, already supported). The night's details panel
  opens there.
- Remove the hardcoded moon flag (`TonightCalc.tsx:91-95`) and the outdated
  help text.

## 6. API (shape left to the plan; constraints here)

- **One evaluator, server-side.** Weather, the editor preview and Tonight all
  get verdicts from the backend; the frontend never re-derives a verdict.
- **Preview of unsaved rules.** The editor preview needs evaluation of draft
  rules, so the request must be able to carry them, for example in a body. Use
  same-origin requests only.
- **Responses expose everything the UI shows,** and nothing hides a missing
  value:
  - per night: verdict, reason, clear hours, dark hours, window, per-model
    verdicts, and the rules actually applied;
  - per hour: values, per-requirement pass/fail/unknown/not-counted.
- **Query keys and caching include the effective rules,** so a saved change
  re-evaluates immediately. Raw forecast data stays cached per location as
  today; only the evaluation depends on rules.
- **Methodology text** (`api/weather.py:METHODOLOGY`) is rewritten to describe
  the verdict model. It remains the UI's single methodology source.

## 7. What is removed or retired

- **User-facing removals:** the 0–100 score, its labels
  (Excellent/Good/Marginal/Poor/Unusable), "could be X–Y", the eight factor
  bars, "≈ N h usable", and the "Include moon in quality score" toggle.
- **The composite model** (`services/imaging_quality.py` scoring, its constants
  and pinned tests) is retired from the forecast. Pieces still needed (for
  example effective cloud cover, darkness overlap, and moon altitude) are kept
  or moved; the plan decides the exact disposition.
- `docs/imaging-quality-model.md` becomes historical, moving to
  `docs/archive/` with a pointer.
- The stale sections of `docs/weather-algorithms.md` (§5–6) are updated or
  archived.
- `docs/development-decisions.md` → "Weather" is rewritten for the new
  contract:
  - verdict rules;
  - missing data;
  - model comparison on complete sequences;
  - stale-data behaviour;
  - darkness independent of the moon.

## 8. Constraints carried forward

- Join weather and astronomy by absolute UTC; never by HH:MM. Fetch 8 days, as
  today. AOD's 7-day horizon matters only as context.
- Missing stays missing; units are explicit everywhere; the user's units
  setting applies.
- Colour-blind safe: no red/green; every colour has a text, shape or pattern
  partner. No question-mark help icons; no tooltip underlines.
- Drill-down opens below with a close button. Tablet: tap gives what hover
  gives.
- Outbound HTTP stays on `services/http_client.py`; no new sources.

## 9. Verification expectations

- **Hand-computed evaluator examples** (scientific/decision logic is
  high-stakes):
  - all-night pass and fail at the fraction boundary (exactly 50% is a fail
    for "> 50%");
  - minimum clear hours on a short night;
  - gap limit;
  - short-session contiguous vs fragmented;
  - "Imaging until" clipping;
  - `night_off` rain in twilight and in a cloudy hour;
  - `hours_lost` rain;
  - wind counted vs not counted (wind not counted with extreme wind still
    gives Go);
  - missing rain probability → Not enough data, or No when failure is
    provable;
  - no darkness; DST nights; a southern-hemisphere date; a polar
    no-sunset case;
  - a night under way: a past rain hour is ignored, the fraction is
    measured on what remains, and the night is still listed at 01:00;
  - per-model disagreement, including a single-model night.
- **Migration:** upgrade a copy at the preceding migration and a fresh
  database; integrity and foreign-key checks; a hard delete of a location in
  SQL cascades its rules.
- **API contract tests,** including draft-rule preview and a stale cache after
  a failed fetch.
- **Rendered checks in a real browser:**
  - the week view, details, editor live preview and Tonight card, in light and
    dark themes and at tablet width;
  - keyboard and tap selection.
- **Independent Codex review** before Fred's acceptance test (migration, API
  contract, decision logic).

## 10. Left to the builder and the plan

- Table and column names; Pydantic and TypeScript models; endpoint paths.
- The exact disposition of `imaging_quality.py`, `seeing.py` and
  `transparency.py`.
- The pattern for "other counted failure" cells.
- The DST rendering approach on the shared clock.
- The polar gear-out fallback.
- Reason-line wording beyond the examples above.
- Whether the `weather_moon_penalty` Settings field is deleted or left inert.
- Phasing. Suggested order:
  1. Evaluator and rules storage.
  2. API.
  3. Week view and details.
  4. Editor.
  5. Tonight.
  6. Docs.
