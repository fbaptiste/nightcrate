# Personal Imaging Verdict (v0.41.9) Implementation Plan

> **For agentic workers:** In this project, Codex implements one phase at a
> time under `docs/agent-collaboration.md` §4, and Claude reviews, re-runs
> checks and stages. Codex never stages, commits, pushes or opens PRs.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the weather page's 0–100 imaging score with a per-night
verdict (Go / Uncertain / No / Not enough data), computed from the hourly
forecast and imaging rules saved per location. Show the result as a week list,
a night-details numbers grid, a rules editor and a Tonight card.

**Architecture:**

- **Backend, pure.** A pure rules module (`services/imaging_rules.py`) and a
  pure evaluator (`services/imaging_verdict.py`). A pure input builder
  (`services/forecast_inputs.py`) turns cached Open-Meteo data into evaluator
  inputs.
- **Backend, HTTP.** `api/weather.py` keeps fetching, caching and astronomy.
  It now resolves rules and calls the evaluator for 7 nights through a single
  `POST /api/weather/forecast`, which replaces `GET /forecast` and
  `GET /hourly`. Rules are stored 1:1 per location in a new table; they are
  read and written through `api/imaging_rules.py`.
- **Frontend.** The frontend renders the server's verdicts and never derives
  one.

**Tech stack:** Python 3.14, FastAPI, Pydantic, aiosqlite, yoyo SQL
migrations, pytest (anyio). React 19, TypeScript, MUI 7, TanStack Query.

**Spec:** [docs/superpowers/specs/2026-10-17-weather-redesign-design.md](../specs/2026-10-17-weather-redesign-design.md).
Read it in full before any task. Section references (§) below are to the spec.

**Base:** `main` at `a3707b6`, branch `v0.41.9/weather-verdict`.

## Global Constraints

- **Times.** Join weather and astronomy by absolute UTC; never by `HH:MM`.
  Display times in the location's display timezone (`location.timezone`), and
  compute astronomy in `geo_timezone or timezone`, as today.
- **Units and missing values.** Store and compute in metric (°C, km/h, mm, %).
  The frontend formats per `weather_units`. A missing value is `None`/`null`:
  never 0, never 50, never "clear".
- **Provider time contract** (Open-Meteo docs, checked 2026-10-17). A response
  uses one fixed UTC offset (`utc_offset_seconds`) throughout, ignoring DST.
  - Request `timezone=GMT` and `timeformat=unixtime`, so every series sits
    on whole UTC hours. Normalize every hourly series (main, cloud models,
    PWV, AOD) to **aware UTC datetimes at parse time**.
  - A legacy cached row whose decoded times are not on whole UTC hours (a
    fractional offset such as +05:30) is treated as absent. It is never
    shifted or matched approximately.
  - Cached responses written before this change carry ISO labels. Decode them
    with their own `utc_offset_seconds`, never with `ZoneInfo`.
  - Local labels for display come from converting UTC with `ZoneInfo`.
- **Preceding-hour fields.** `precipitation`, `precipitation_probability` and
  `wind_gusts_10m` describe the **preceding** hour. The value at UTC `T+1h`
  covers `[T, T+1h)`. Cloud, wind speed, temperature and dew point are
  instantaneous at `T`, and stand for `[T, T+1h)`.
- **Complete timeline.** Evaluator inputs cover every whole UTC hour of the
  night's interval, and no hour is ever skipped. Each field is resolved from
  its own timestamp and source (Task 3). A field whose source row is missing
  is `None`, which means unknown.
- **Sources stay as they are** (Fred):
  - Cloud: `ecmwf_ifs025` when it covers every hour of a night; otherwise that
    night uses `best_match` cloud, labelled as a fallback.
  - GFS and ICON are used only for comparison.
  - Everything else comes from `best_match`.
- **No blended score anywhere.** Not in an API field, not as a sort key, and
  not in the UI.
- **Colour.**
  - Blue, orange, grey or teal only; never red/green; no purple/amber pairs.
  - Every state also has a text, shape or pattern.
  - Use theme tokens; any hex colour has six digits.
  - No question-mark help icons; no tooltip underlines.
  - Drill-down opens below with a Close button. Tap does what hover does.
- **Architecture rules.**
  - Services import neither `api/` nor FastAPI.
  - Outbound HTTP goes only through `services/http_client.py`.
  - Frontend calls are same-origin.
- **Migrations.** Never edit an existing migration; the new one is `0058`.
- **Delivery.** Codex leaves all work unstaged. Nothing is committed without
  Fred's authorization.

## Review Focus

These conditions are implied by the spec but not exercised by any obvious
test. Each has a test in its owning task.

1. **Open-Meteo returns `null` for a decisive field mid-series, or omits
   rows** (cloud or wind at a model's horizon; a truncated response). The
   hour must become `unknown`, with no crash and no "clear"
   (Task 3: `test_parse_hourly_null_decisive_fields`,
   `test_build_hour_inputs_fills_missing_rows`; Task 4:
   `test_forecast_null_context_inputs`).
2. **The display timezone differs from the site timezone** (remote
   observatory). Hours, darkness and moon must join by UTC, and reason times
   must be in the display zone (Task 4,
   `test_forecast_display_tz_differs_from_geo_tz`).
3. **Extreme saved rules.**
   - `min_clear_fraction_pct` must be < 100, because "> 100%" can never pass.
     Validate it (Task 1, `test_rules_reject_fraction_100`).
   - A cloud limit of 0% with a 0% cloud forecast must pass (Task 2,
     `test_zero_limits_pass_on_zero_values`).
4. **The persistent Weather page stays open across an hour boundary, local
   midnight or local noon.** Tonight's verdict must refresh:
   - an hour-aligned refetch (Task 5, `forecastQueryOptions`; R5);
   - the backend anchor (Task 4, `test_forecast_night_under_way_stays_listed`);
   - a frontend `tonightDate` that matches the backend (Task 7).
5. **Switching location while the rules editor holds an unsaved draft.** The
   draft is discarded and the editor closes, so it can never be saved to the
   new location (Task 6, rendered check R8).

---

## Phase A — Rules storage and evaluator (high-stakes: schema, decision logic)

### Task 1: Rules model, presets, migration and rules API

**Files:**

- Create:
  - `backend/src/nightcrate/services/imaging_rules.py`
  - `backend/src/nightcrate/db/migrations/0058.location_imaging_rules.sql`
  - `backend/src/nightcrate/api/imaging_rules.py`
  - `backend/tests/test_imaging_rules.py`
- Modify:
  - `backend/src/nightcrate/main.py` (include the router next to
    `locations.router`)
  - `DB_SCHEMA_DDL.sql` and `DB_SCHEMA.md` (add the table)

**Interfaces — produces:**

- `class ImagingRules(BaseModel)`. Strict field set, `extra="forbid"`:

  | Field | Type | Constraint |
  |---|---|---|
  | `session_style` | `Literal["all_night", "short_session"]` | |
  | `min_clear_fraction_pct` | `float` | `ge=0, lt=100`; a "more than" comparison |
  | `min_clear_hours` | `float` | `ge=0` |
  | `max_cloudy_gap_hours` | `float \| None` | `gt=0`; `None` = no limit |
  | `short_session_hours` | `float` | `gt=0, le=24` |
  | `darkness` | `Literal["astronomical", "nautical", "civil"]` | |
  | `cloud_max_pct` | `float` | `ge=0, le=100` |
  | `gear_out_before_sunset_min` | `int` | `ge=0, le=240` |
  | `gear_out_after_sunrise_min` | `int` | `ge=0, le=240` |
  | `rain_max_probability_pct` | `float` | `ge=0, le=100` |
  | `rain_policy` | `Literal["night_off", "hours_lost"]` | |
  | `wind_counted` | `bool` | |
  | `wind_max_kmh` | `float` | `gt=0` |
  | `gust_max_kmh` | `float` | `gt=0` |
  | `dew_counted` | `bool` | |
  | `dew_min_spread_c` | `float` | `ge=0` |
  | `moon_must_be_down` | `bool` | |

- `PresetKey = Literal["left_out_all_night", "attended_session", "dome"]`
- `PRESETS: dict[PresetKey, tuple[str, ImagingRules]]`, mapping a key to
  `(label, rules)`. Values from spec §3.2:

  | Key | Label | Session | Rain | Wind |
  |---|---|---|---|---|
  | `left_out_all_night` | "Left out all night" | all night, > 50%, ≥ 2 h, no gap limit | 0%, `night_off` | off |
  | `attended_session` | "Attended session" | short, 2 h in a row | 20%, `hours_lost` | on, 30 / 45 km/h |
  | `dome` | "Dome / roll-off" | all night, > 50%, ≥ 2 h | 20%, `hours_lost` | off |

  Values shared by every preset:
  - cloud ≤ 20%; astronomical darkness; gear out 30 / 30 min;
  - `wind_max_kmh=30`, `gust_max_kmh=45`;
  - `dew_counted=False`, `dew_min_spread_c=3.0`;
  - `moon_must_be_down=False`;
  - `short_session_hours=2.0`, `min_clear_fraction_pct=50`,
    `min_clear_hours=2.0`, `max_cloudy_gap_hours=None`.
- `DEFAULT_PRESET: PresetKey = "attended_session"`. This is used when a
  location has no saved rules (spec §3.2).
- **HTTP** (all return 404 for a missing or inactive location):
  - `GET /api/locations/{location_id}/imaging-rules` →
    `ImagingRulesResponse { location_id: int, saved: bool, rules: ImagingRules }`.
    With no row: `saved=false` and the default preset's rules.
  - `PUT /api/locations/{location_id}/imaging-rules` (body `ImagingRules`):
    upsert, returning `saved=true`.
  - `GET /api/imaging-rules/presets` →
    `list[PresetResponse { key, label, rules }]`, in the order above.
- **Repository helper**, used by Task 4:
  `async def load_rules(conn, location_id: int) -> tuple[ImagingRules, bool]`
  in `api/imaging_rules.py`. Returns `(rules, saved)`.

**Migration contract** (`0058.location_imaging_rules.sql`,
`-- depends: 0057.weather_cache_cloud_models`):

- Table `location_imaging_rules`:
  - `location_id INTEGER PRIMARY KEY REFERENCES location(id) ON DELETE CASCADE`.
  - One column per `ImagingRules` field, with the same name. Each is
    `NOT NULL`, except `max_cloudy_gap_hours`.
  - CHECK constraints mirroring the Pydantic bounds and the three
    vocabularies. Booleans are `INTEGER CHECK (x IN (0, 1))`.
  - `created_at` and `updated_at` default `datetime('now')`.
  - An `updated_at` trigger like `trg_location_updated_at`.
- No data is inserted. A missing row means "not saved".

- [ ] **Step 1: Write failing tests** in `backend/tests/test_imaging_rules.py`:
  - **`test_presets_values`:**
    - `PRESETS["left_out_all_night"][1]` has `rain_max_probability_pct == 0`,
      `rain_policy == "night_off"` and `wind_counted is False`.
    - `PRESETS["attended_session"][1].session_style == "short_session"`.
    - All three have `cloud_max_pct == 20`.
  - **`test_rules_reject_fraction_100`:** `ImagingRules(min_clear_fraction_pct=100, …)`
    raises `ValidationError`, and so does an unknown extra field.
  - **`test_get_rules_unsaved_returns_default`:** create a location; GET →
    `saved is False` and `rules == PRESETS["attended_session"][1]` dumped.
  - **`test_put_then_get_roundtrip`:**
    - PUT the left-out preset with `max_cloudy_gap_hours=1.5` → 200 and
      `saved is True`.
    - GET returns identical values (booleans as booleans).
  - **`test_put_overwrites`:** two PUTs leave exactly one row, holding the
    second values.
  - **`test_rules_404_inactive_location`:** a soft-deleted location gives 404
    on GET and PUT.
  - **`test_presets_endpoint_order`:** keys are
    `["left_out_all_night", "attended_session", "dome"]`.
  - **`test_migration_0058_fresh_via_yoyo`:**
    - Run `nightcrate.db.migrations.apply_migrations(tmp_path / "fresh.db")`.
      This is the production path (`db/migrations.py:11`), not the
      `conftest.py` executescript loop, which strips `-- depends:`.
    - → the table exists, and yoyo's `_yoyo_migration` lists
      `0058.location_imaging_rules`.
    - A second `apply_migrations` call changes nothing (the same
      `_yoyo_migration` row count).
  - **`test_migration_0058_upgrade_preserves_data`:**
    - Build a temp DB at 0057 through yoyo:
      `backend.apply_migrations(backend.to_apply(read_migrations(MIGRATIONS_DIR)).filter(lambda m: m.id <= "0057.weather_cache_cloud_models"))`.
    - Insert a `location` and a `weather_cache` row, then run
      `apply_migrations(path)`.
    - Assert:
      - both rows are unchanged, byte for byte;
      - `location_imaging_rules` exists and is empty;
      - `PRAGMA integrity_check` returns `ok`;
      - `PRAGMA foreign_key_check` returns no rows.
    - Then insert a rules row:
      - a soft delete (`UPDATE location SET active=0`) followed by a restore
        keeps the rules row;
      - with `PRAGMA foreign_keys=ON`, `DELETE FROM location WHERE id=?`
        cascades it away.
  - **`test_rules_check_constraints`:** a raw-SQL insert with
    `rain_policy='sometimes'` raises `sqlite3.IntegrityError`, and so does one
    with `wind_counted=2`.
- [ ] **Step 2: Run** `cd backend && uv run pytest tests/test_imaging_rules.py -q`.
  Expect failures: import and table missing.
- [ ] **Step 3: Implement** the model and presets, the migration, the router
  with `load_rules`, and the router registration. Use `api/_common.py`
  helpers where they fit.
- [ ] **Step 4: Run** the same command. Expect all to pass. Then run
  `uv run pytest tests/test_imaging_schema.py tests/test_equipment_schema.py -q`
  to confirm the migration chain still applies.
- [ ] **Step 5:** Add the table to `DB_SCHEMA_DDL.sql` (verbatim DDL) and
  `DB_SCHEMA.md` (one row in the table list, plus its relationship to
  `location`). Leave everything unstaged and report.

### Task 2: Pure evaluator

**Files:**

- Create:
  - `backend/src/nightcrate/services/imaging_verdict.py`
  - `backend/tests/test_imaging_verdict.py`

**Interfaces:**

- **Consumes:** `ImagingRules` (Task 1).
- **Produces** (frozen dataclasses unless noted):
  - `CloudFigures = tuple[float | None, float | None, float | None, float | None]`,
    meaning (total, low, mid, high).
  - `CheckState = Literal["pass", "fail", "unknown", "not_counted"]`
  - `HourState = Literal["clear", "not_clear", "unknown", "outside"]`.
    `outside` means the hour has no dark minutes in the evaluated interval.
  - `Verdict = Literal["go", "uncertain", "no", "not_enough_data", "night_over"]`
  - `HourInput(start_utc: datetime, cloud: dict[str, CloudFigures | None], precip_probability_pct: float | None, precip_mm: float | None, wind_kmh: float | None, gust_kmh: float | None, temperature_c: float | None, dew_point_c: float | None, moon_altitude_deg: float | None)`
    - `"best_match"` is always a key of `cloud`.
    - Precipitation and gust are already shifted to cover
      `[start_utc, start_utc + 1h)` (Task 3).
  - `NightInput(sunset_utc: datetime | None, sunrise_utc: datetime | None, noon_start_utc: datetime, noon_end_utc: datetime, dark_intervals: list[tuple[datetime, datetime]], hours: list[HourInput], now_utc: datetime, imaging_until_utc: datetime | None, primary_model: str, comparison_models: tuple[str, ...], stale_minutes: int | None)`
    - `dark_intervals` holds the sorted, disjoint intervals for
      `rules.darkness`. The caller resolves them with
      `astronomy.dark_intervals_for` (Task 4).
    - An empty list means the night never reaches that darkness.
    - Continuous polar darkness is `[(noon_start_utc, noon_end_utc)]`.
    - At extreme latitudes there can be two intervals. Clear runs and cloudy
      gaps never bridge the non-dark time between them.
  - `HourResult(start_utc, elapsed: bool, excluded: bool, dark_minutes: float, gear_out_minutes: float, checks: dict[str, CheckState], state: HourState, model_states: dict[str, HourState], effective_cloud_pct: dict[str, float | None], dew_spread_c: float | None)`
    - `elapsed` = `start_utc + 1h ≤ now_utc`, always the actual clock.
    - `excluded` = the hour starts at or after the `imaging_until` cap.
    - The `checks` keys are exactly `cloud`, `rain`, `wind`, `dew`, `moon`.
    - A rule that isn't counted gives `not_counted`.
    - Rain is `not_counted` on an hour with no gear-out minutes.
    - Cloud, wind, dew and moon are `not_counted` on an hour with no dark
      minutes. Only checks that can affect the verdict are ever `pass`,
      `fail` or `unknown`.
  - `ReasonCode = Literal["clear_all_night", "clear_with_gaps", "short_window", "rain", "rain_amount", "clear_fraction", "min_hours", "gap", "no_window", "never_dark", "no_dark_time", "models_disagree", "missing_data", "stale", "night_over"]`
  - `Reason(code: ReasonCode, start_utc: datetime | None = None, end_utc: datetime | None = None, value: float | None = None, limit: float | None = None, requirement: str | None = None, models: dict[str, Verdict] | None = None, bound: Literal["at_most", "at_least"] | None = None)`.
    `bound` is set when a `no` reason's value came from the optimistic
    computation while unknown minutes exist:
    - `at_most` for `clear_fraction`, `min_hours` and `no_window`;
    - `at_least` for `gap`.

    The UI says "at most …" or "at least …", followed by ", even if the
    missing hours are clear".
    Units are fixed per code:

    | Code | `value` | `limit` |
    |---|---|---|
    | `rain` | % | % |
    | `rain_amount` | mm | 0 mm |
    | `clear_fraction` | % | % |
    | `min_hours` | hours | hours |
    | `gap` | hours | hours |
    | `no_window` | hours (longest run) | hours (required) |
    | `stale` | minutes | — |
    | all other codes | — | — |

  - `NightResult(verdict: Verdict, reason: Reason, clear_minutes: float, dark_minutes: float, unknown_minutes: float, longest_gap: tuple[datetime, datetime] | None, longest_clear_run: tuple[datetime, datetime] | None, window: tuple[datetime, datetime] | None, gear_out: tuple[datetime, datetime], evaluated_from_utc: datetime | None, evaluated_end_utc: datetime | None, model_verdicts: dict[str, Verdict], single_model: bool, requirements: dict[str, CheckState], hours: list[HourResult])`
    - The minute totals and runs are pessimistic: unknown counts as not
      clear.
    - `evaluated_end_utc` is set only when `imaging_until_utc` caps the night.
  - `def effective_cloud_pct(figures: CloudFigures | None) -> float | None`.
    Take the max of the available values. When the total is missing but
    layers exist, the total is `100·(1 − Π(1 − f/100))`, as today
    (`imaging_quality.py:effective_cloud_fraction`). All missing → `None`.
  - `def evaluate_night(night: NightInput, rules: ImagingRules) -> NightResult`

**Algorithm decisions** (the tests below pin each one):

1. **Intervals.**
   - Gear-out:
     - start = `sunset_utc − before`;
     - end = `sunrise_utc + after`;
     - when sunset or sunrise is `None`, use `noon_start_utc` or
       `noon_end_utc` instead (the polar fallback, spec §4.2).
   - `imaging_until_utc` caps both the gear-out end and the darkness end.
   - Evaluation start = `max(now_utc, gear-out start)`.
   - `evaluated_from_utc` is set when `now_utc > gear-out start`.
2. **Night over** (Fred's decision D1, 2026-10-17). The verdict is
   `night_over` when either holds:
   - `now_utc ≥` the gear-out end;
   - `dark_intervals` is non-empty and `now_utc ≥` the end of its last
     interval (uncapped).

   Hour results are still computed over the whole night, so the details stay
   viewable. `elapsed` keeps its real-clock meaning: future gear-out hours
   are not marked elapsed.
3. **Per hour.**
   - The hour is `[start_utc, start_utc + 1h)`.
   - Dark minutes = its overlap with
     `⋃ dark_intervals ∩ [evaluation start, cap)`. The cap is
     `imaging_until_utc`, or none.
   - Gear-out minutes = its overlap with
     `[evaluation start, capped gear-out end)`.
   - Checks (a known `fail` beats `unknown`):
     - **cloud:** fails when `effective_cloud_pct > cloud_max_pct`.
     - **rain:** fails when probability > limit **or** `precip_mm > 0`. It
       passes only when both are known and pass; otherwise it is `unknown`.
     - **wind** (only when counted): fails when either value exceeds its
       limit.
     - **dew** (only when counted): fails when `temperature − dew point` is
       below `dew_min_spread_c`.
     - **moon** (only when required): passes only when the altitude is
       `< 0`. An altitude `≥ 0` fails; a missing altitude is `unknown`.
   - State:
     - `outside` if dark minutes are 0;
     - else `not_clear` if any counted check fails (rain included under both
       policies);
     - else `unknown` if any counted check is unknown;
     - else `clear`.
4. **Night, per cloud model.** Evaluate in this order; the first match
   decides:
   1. `night_over` (item 2).
   2. `dark_intervals == []` → `no` / `never_dark`.
   3. An `imaging_until` cap leaves no dark minutes, for example a cap before
      darkness starts → `no` / `no_dark_time`, with `start` = the cap. (Dark
      time that has merely elapsed is item 2, night over.)
   4. **Rain, `night_off`:** a rain `fail` on any hour with gear-out minutes →
      `no`.
      - The block is the maximal run of consecutive failing hours that
        contains the earliest failure.
      - The code is `rain_amount` when the earliest failure fails only on
        amount; then `value` is the block's maximum mm.
      - Otherwise the code is `rain`, and `value` is the block's maximum
        probability.
   5. **Session rule,** evaluated twice:
      - **Pessimistic:** unknown hours are not clear, and an unknown
        `night_off` rain check counts as a rain fail.
      - **Optimistic:** unknown hours are clear, and unknown rain passes.
      - Pessimistic passes → `go`.
      - Optimistic fails → `no`, with the first failing condition reported
        from the optimistic numbers. Set `bound` (see `Reason`) when unknown
        minutes exist.
      - Otherwise → `not_enough_data` / `missing_data`, naming the earliest
        `unknown` check: by hour, then cloud, rain, wind, dew, moon. Because
        of the `not_counted` rules above, only checks that matter can be
        `unknown`.
   - **All night,** in failure-report order:
     1. `clear/dark·100 > min_clear_fraction_pct` (`clear_fraction`);
     2. `clear ≥ min_clear_hours·60` (`min_hours`);
     3. when a gap limit is set, the longest run of contiguous non-clear dark
        minutes ≤ the limit (`gap`).
   - **Runs** are contiguous in time across hour boundaries. Partial hours
     contribute their dark minutes at the correct edge.
   - **Short session:** the longest contiguous clear run ≥
     `short_session_hours·60` → `go` / `short_window`, with
     `window = longest_clear_run`. The earliest run wins ties. Otherwise
     `no` / `no_window`.
   - **Go reasons:**
     - `clear_all_night` when there are no non-clear dark minutes;
     - otherwise `clear_with_gaps`, on the longest non-clear stretch (earliest
       on ties).
     - Its `requirement` is the failing requirement that occurs in the most
       of that stretch's hours. Ties go in the order cloud, rain, wind, dew,
       moon. A stretch of only unknown hours gives `"unknown"`.
5. **Models.**
   - Evaluate the primary model, then every comparison model.
   - A comparison model counts only if its cloud figures cover **every** hour
     with dark or gear-out minutes.
   - The night is `uncertain` (`models_disagree`, with `models` filled in)
     when the counted verdicts include both `go` and `no`.
   - **Short sessions:** when the primary is `go`, a comparison model
     *agrees* if it has a clear run of at least `short_session_hours` inside
     the primary's `window`. Otherwise it counts as `no`.
   - `single_model` = fewer than two counted models.
6. **Stale.** When `stale_minutes` is set and the verdict would be `go`, it
   becomes `not_enough_data` / `stale` (with `value` = minutes). Other
   verdicts stay as they are.
7. **Night-level `requirements`.** Each is aggregated over the evaluated
   (not elapsed) hours:
   - `clear_time`: `pass` if the session rule passes pessimistically; `fail`
     if it fails optimistically; otherwise `unknown`.
   - `rain`: `fail`, `unknown` or `pass` over the counted rain checks. Under
     `night_off` those are the gear-out hours; under `hours_lost`, the dark
     hours.
   - `wind`, `dew`, `moon`: `not_counted` when the rule is off; otherwise
     `fail`, `unknown` or `pass` over the dark hours.
   - `models`: `not_counted` if `single_model`; `fail` if `uncertain`;
     otherwise `pass`.

- [ ] **Step 1: Write failing tests** in `backend/tests/test_imaging_verdict.py`.

  **Fixture.** A builder `_night(**overrides)`:
  - UTC throughout; sunset 18:30, sunrise 05:30.
  - `dark_intervals` = [20:00 → 04:00] (8 h).
  - Hours from 18:00 to 06:00.
  - Defaults: cloud `(10,0,0,10)` for `ecmwf_ifs025` and `best_match`;
    rain 0% / 0.0 mm; wind 10 / gust 15; temperature 10, dew point 2; moon
    −10°.
  - `now_utc` = 12:00 the same day.
  - `rules()` = the left-out preset, overridable.
  - "at A–B" means the hours starting at A up to, but not including, B.
    "At 22" means the single hour starting at 22:00.

  Every assertion below uses these hand-computed values:

  - **`test_all_night_go`:** cloud 80 at 20–23 → `go`. `clear_minutes == 300`,
    `dark_minutes == 480`. Reason `clear_with_gaps`, start 20:00, end 23:00,
    requirement `cloud`.
  - **`test_all_night_exactly_half_is_no`:** 4 of 8 clear → `no` /
    `clear_fraction`, value 50.0, limit 50.0.
  - **`test_min_hours_short_night`:** `dark_intervals` = [23:30 → 01:00], all clear
    → `no` / `min_hours`, value 1.5, limit 2.0.
  - **`test_gap_limit`:** gap limit 1.0, cloud 80 at 22–24 → `no` / `gap`,
    start 22:00, value 2.0, limit 1.0.
  - **`test_reason_tie_earliest_stretch`:** cloud 80 at 21 and at 01 → `go`
    / `clear_with_gaps`, start 21:00.
  - **`test_short_session_window`:** short session of 2 h, clear only at
    20–22 → `go`, window (20:00, 22:00), `short_window`.
  - **`test_short_session_fragmented`:** clear at 20, 22 and 00 only →
    `no` / `no_window`, value 1.0, limit 2.0.
  - **`test_imaging_until_caps_short_session`:** short session of 2 h,
    `imaging_until` 21:30 → `no` / `no_window`, value 1.5, and
    `evaluated_end_utc` 21:30.
  - **`test_imaging_until_before_dark`:** `imaging_until` 19:30 → `no` /
    `no_dark_time`, start 19:30.
  - **`test_imaging_until_caps_gear_out_rain`:** `night_off`, rain 40% at
    02:00, `imaging_until` 01:00 → `go`; the 02:00 hour's rain check is
    `not_counted`.
  - **`test_night_off_rain_in_twilight`:** rain 10% in the 18:00 hour →
    `no` / `rain`, start 18:00, end 19:00, value 10, limit 0. With
    `hours_lost` → `go`.
  - **`test_night_off_rain_in_cloudy_hour`:** cloud 90 and rain 5% at 22 →
    `no` / `rain`, start 22:00.
  - **`test_rain_amount_fails_even_at_zero_probability`:** amount 0.2 mm,
    probability 0% at 22 → `no` / `rain_amount`, value 0.2, limit 0.0.
  - **`test_hours_lost_rain`:** `hours_lost`, rain 50% at 22 and 23 → those
    hours `not_clear`; `go`; `requirements["rain"] == "fail"` and
    `requirements["clear_time"] == "pass"`.
  - **`test_wind_not_counted_ignores_extreme_wind`:** wind 100 / gust 150 →
    `go`, wind `not_counted`, and `requirements["wind"] == "not_counted"`.
    Counted (30 / 45) with gust 50 at 22 → that hour `not_clear`, wind
    `fail`.
  - **`test_moon_boundary`:** moon must be down; altitude 0.0 at 22 → that
    hour's moon check fails. At −0.1 it passes.
  - **`test_zero_limits_pass_on_zero_values`:** cloud limit 0, all cloud 0,
    rain 0 → `go`.
  - **`test_missing_rain_is_not_enough_data`:** `night_off`, probability
    `None` at 02 → `not_enough_data` / `missing_data`, requirement `rain`,
    start 02:00.
  - **`test_missing_twilight_hour_under_night_off`:** every field of the
    18:00 hour is `None` → `not_enough_data` / `missing_data`, requirement
    `rain`, start 18:00. That hour's cloud check is `not_counted`, because it
    has no dark minutes.
  - **`test_missing_rain_but_provably_no`:** the 02:00 unknown, plus cloud 80
    at 20–01 → `no` / `clear_fraction`, value 37.5, `bound == "at_most"`.
    Optimistically 3 of 8 hours are clear: 01:00, 02:00 (unknown) and
    03:00. Pessimistically, `clear_minutes == 120`.
  - **`test_missing_cloud_hour_unknown`:** all models' cloud `None` at 23,
    other hours clear → `go` / `clear_with_gaps`, start 23:00, requirement
    `"unknown"`. The hour's state is `unknown`, and `unknown_minutes == 60`.
  - **`test_never_dark`:** `dark_intervals=[]` → `no` / `never_dark`.
  - **`test_continuous_darkness`:** `sunset_utc=None`, `sunrise_utc=None`,
    `dark_intervals=[(noon_start, noon_end)]`, hours spanning noon to noon, all
    clear → `go` with `dark_minutes == 1440`. Gear-out equals the noon
    bounds.
  - **`test_night_under_way`:** `now` 23:00; rain 20% at 19:00 (elapsed) →
    `go`. `evaluated_from_utc == 23:00` and `dark_minutes == 300`; the
    19:00 hour is `elapsed`.
  - **`test_no_remaining_darkness_is_night_over`:** `now` 04:30 →
    `night_over`. The 04:00 hour is not elapsed; the 03:00 hour is.
  - **`test_gap_lower_bound_with_unknown`:**
    - Gap limit 1.0; 21:00 unknown; cloud 80 at 22–00; everything else
      clear.
    - Pessimistically: 5 h clear, a 3 h gap. Optimistically: 6 h clear, a
      2 h gap.
    - → `no` / `gap`, value 2.0, `bound == "at_least"`, start 22:00.
  - **`test_two_dark_intervals`:**
    - Hours from noon to noon, `sunset_utc=None`, `sunrise_utc=None` (polar
      gear-out bounds).
    - `dark_intervals = [(12:00, 12:23), (13:33, 12:00 next day)]`, all
      clear.
    - Short session of 22.5 h → `no` / `no_window`, value 22.45 (1,347 min).
      The longest run does not bridge 12:23–13:33; bridging would give
      22.83 h and a wrong `go`.
    - All night → `go`, with `dark_minutes == 1370`.
  - **`test_imaging_until_marks_excluded`:** `imaging_until` 01:00 →
    the hours from 01:00 on are `excluded` and not `elapsed`.
  - **`test_night_over_after_gear_out`:** `now` 06:30 → `night_over`.
  - **`test_models_disagree`:**
    - ECMWF all clear; GFS cloud 90 everywhere → `uncertain`, with models
      `{"ecmwf_ifs025": "go", "gfs_seamless": "no"}`, and
      `requirements["models"] == "fail"`.
    - ICON missing at one dark hour → excluded.
  - **`test_single_model`:** only the primary covers the night →
    `single_model is True`, the verdict is not `uncertain`, and
    `requirements["models"] == "not_counted"`.
  - **`test_short_session_models_agree_inside_window`:** primary clear
    20–02 (window 6 h); GFS clear only 22–00 → `go`, not `uncertain`.
  - **`test_short_session_models_disagree`:** primary clear only at 20–22;
    GFS clear only at 00–02 → `uncertain`.
  - **`test_stale_go_becomes_not_enough_data`:** `stale_minutes=540` and all
    clear → `not_enough_data` / `stale`, value 540. The same input with 4 of
    8 cloudy stays `no`.
  - **`test_effective_cloud_pct`:**
    - `(10,0,0,36)` → 36.0;
    - `(None,50,50,0)` → 75.0;
    - `(None,None,None,None)` → `None`.
- [ ] **Step 2: Run** `uv run pytest tests/test_imaging_verdict.py -q`.
  Expect failures.
- [ ] **Step 3: Implement** `imaging_verdict.py`. It is pure: no I/O, no
  logging of user data.
- [ ] **Step 4: Run** it again; expect all to pass. Then run ruff and format
  on the new files.
- [ ] **Step 5:** Leave everything unstaged; report.

---

## Phase B — Data layer and endpoint (high-stakes: API contract, cache eviction)

### Task 3: UTC normalization, complete inputs and context estimates

**Files:**

- Create:
  - `backend/src/nightcrate/services/forecast_inputs.py`
  - `backend/tests/test_forecast_inputs.py`
- Modify:
  - `backend/src/nightcrate/services/weather.py`
  - `backend/src/nightcrate/services/transparency.py`
  - `backend/src/nightcrate/services/seeing.py`
  - `backend/src/nightcrate/main.py:168-177` (purge)
  - `backend/tests/test_weather_service.py`
  - `backend/tests/test_transparency.py`
  - `backend/tests/test_seeing.py`
  - `backend/tests/test_weather_cache.py`

**Interfaces — produces:**

- **`HourlyWeather`:**
  - `time_utc: datetime` (aware UTC) replaces `time: str`.
  - Every measured field becomes `float | None`.
  - `parse_hourly(hourly_dict, source, utc_offset_seconds: int)` accepts
    either form of `time`:
    - unixtime integers (new fetches);
    - legacy ISO labels, from cache rows written before this change. A label
      is decoded as naive local time minus `utc_offset_seconds`; it is never
      passed through `ZoneInfo`.
  - A `null` never raises.
- **Fetching.** `fetch_weather`, `fetch_cloud_models`, `fetch_pwv` and
  `fetch_air_quality` request `timezone=GMT` and `timeformat=unixtime`.
  Display conversion happens later, in the API.
  - The forecast and cloud-model calls also add `past_days=1` and keep
    `forecast_days=8`, so tonight's evening hours are still there after local
    midnight.
  - Every cached-row reader passes the stored response's
    `utc_offset_seconds`, defaulting to 0 when absent.
  - A cached row with any decoded time off the whole-UTC-hour grid is
    treated as absent (a cache miss).
- **Keys are UTC datetimes:**
  - `CloudModelData.models[model][time_utc]`. `parse_cloud_models(hourly, models, utc_offset_seconds)`
    keys by the same UTC normalization, so labels can no longer collide.
  - `SupplementaryData.values_by_time`.
  - `NearestMatchIndex(data: dict[datetime, float | None]).lookup(target_utc: datetime, max_gap_hours=3.0)`.
- **`build_hour_inputs`** in `forecast_inputs.py`:

  ```python
  build_hour_inputs(
      hourly: list[HourlyWeather],
      cloud_models: CloudModelData | None,
      moon_altitudes: dict[datetime, float | None],
      start_utc: datetime,
      end_utc: datetime,
  ) -> list[HourInput]
  ```

  - **One input per whole UTC hour,** from `floor(start_utc)` to
    `ceil(end_utc)` (exclusive), whatever rows exist.
  - **Each field is resolved from its own timestamp and source.** A missing
    row makes only the fields that row supplies `None`.
  - **From the row at exactly `T + 1h`:** `precip_probability_pct`,
    `precip_mm` and `gust_kmh`. They are `None` if that row is missing.
  - **From the row at `T`:** wind speed, temperature, dew point and
    `cloud["best_match"]`.
  - **`cloud[model]`** = `cloud_models.models[model].get(T)` for each of
    `CLOUD_SPREAD_MODELS`.
- **Constants.** `CLOUD_PRIMARY_MODEL` and `CLOUD_SPREAD_MODELS` are
  unchanged. Remove `FORECAST_UNCERTAIN_MIN_SPREAD`.
- **Required inputs for the context estimates.**
  - Seeing:
    - `estimate_seeing_surface` returns `None` unless temperature, dew point,
      humidity and wind are all present. The previous temperature stays
      optional.
    - `estimate_seeing_wind_shear` returns `None` unless all six
      pressure-level fields and the surface inputs are present.
    - Both return `int | None`.
  - `estimate_transparency` returns `score=None` unless every input of some
    tier is present. Tier 3 needs humidity **and** visibility. There is no
    fabricated 50.
- **Labels:** `def score_label(score: int | None) -> Literal["good", "fair", "poor"] | None`
  in `seeing.py`. 67 or more is good, 34 or more is fair, otherwise poor;
  `None` stays `None`.
- **Startup purge.** Move it into `async def purge_weather_cache(conn) -> int`
  in `main.py`. It deletes rows older than `WEATHER_CACHE_RETENTION_DAYS = 8`,
  not 2 × TTL, which would delete the stale data that freshness needs.
- `dew.py` stays until Task 4 removes its last importer.

- [ ] **Step 1: Write failing tests:**
  - **`test_parse_hourly_unixtime`:** times `[1793131200, 1793134800]` →
    aware UTC datetimes one hour apart.
  - **`test_parse_hourly_legacy_iso_fixed_offset`:**
    - Labels `2026-11-01T00:00` through `T03:00`, with
      `utc_offset_seconds=-14400`.
    - → UTC 04:00, 05:00, 06:00, 07:00.
    - These stay consecutive across the 06:00 UTC New York fall-back, because
      the offset is fixed.
  - **`test_parse_hourly_null_decisive_fields`:** `cloud_cover` and
    `wind_speed_10m` are `null` at index 1 → that record's fields are `None`;
    the other records are parsed.
  - **`test_parse_cloud_models_utc_keys`:** two models, two hours → keys are
    UTC datetimes; values as given.
  - **`test_fetch_requests_gmt_unixtime_and_past_day`:** mock `http_get`.
    - `fetch_weather` params include `timezone == "GMT"`,
      `timeformat == "unixtime"`, `past_days == 1` and `forecast_days == 8`.
    - Same for `fetch_cloud_models`.
    - `fetch_pwv` and `fetch_air_quality` include `timezone == "GMT"` and
      `timeformat == "unixtime"`.
  - **`test_legacy_cache_off_grid_ignored`:** a cached legacy row with
    `utc_offset_seconds=19800` (+05:30) is treated as a miss; the fetch is
    called.
  - **`test_build_hour_inputs_shifts_preceding_hour_fields`:**
    - Rows at 20:00 UTC (precip 0.0, prob 0, gust 10, wind 5) and 21:00
      (0.4, 60, 55, 30).
    - → the 20:00 input has `precip_mm 0.4`, prob 60, gust 55, and wind 5
      (instantaneous, from 20:00).
  - **`test_build_hour_inputs_fills_missing_rows`:**
    - Rows at 20:00 and 22:00 only; window 20:00–23:00.
    - → inputs at 20, 21 and 22.
    - The 21:00 input: wind, temperature, dew point and best-match cloud are
      `None`; precipitation and gust come from the 22:00 row; an ECMWF value
      present at 21:00 is kept.
    - The 20:00 input has precipitation and gust `None` (no 21:00 row).
    - The 22:00 input has precipitation `None` (no 23:00 row).
  - **`test_build_hour_inputs_models`:** `CloudModelData` holds ECMWF for
    the first hour only → `cloud["ecmwf_ifs025"]` is `None` for the second,
    and `cloud["best_match"]` is set for both.
  - **`test_seeing_missing_wind_is_none`:** the surface model with
    `wind_speed_kmh=None` → `None`. This reproduces today's `TypeError`.
  - **`test_transparency_one_input_missing_is_none`:** humidity present,
    visibility `None`, no PWV or AOD → `None`.
  - **`test_score_label_bands`:** 67 → good; 66 → fair; 34 → fair; 33 → poor;
    `None` → `None`.
  - **`test_purge_keeps_week_old_rows`:** a row 2 days old survives; a row
    9 days old is deleted; the return value is 1.
- [ ] **Step 2: Run** `uv run pytest tests/test_forecast_inputs.py tests/test_weather_service.py tests/test_transparency.py tests/test_seeing.py tests/test_weather_cache.py -q`.
  Expect the new tests to fail.
- [ ] **Step 3: Implement.** Keep `api/weather.py` importable by adapting its
  uses of `h.time` and the NearestMatchIndex keys just enough for the module
  to load. Task 4 rewrites that file.
- [ ] **Step 4: Run** the Step 2 command; expect all to pass. Tests in
  `test_weather_api.py` may fail until Task 4.
- [ ] **Step 5:** Leave everything unstaged; report.

### Task 4: Darkness intervals, `POST /api/weather/forecast`, and removal of the composite

**Files:**

- Modify:
  - `backend/src/nightcrate/services/astronomy.py`
  - `backend/src/nightcrate/api/weather.py`
  - `backend/src/nightcrate/api/weather_models.py` (rewrite)
  - `backend/src/nightcrate/core/config.py` (remove `weather_moon_penalty`)
  - `backend/tests/test_weather_api.py` (rewrite)
  - `backend/tests/test_weather_settings.py`
  - `backend/tests/test_astronomy.py` (or the existing astronomy test module)
  - `backend/tests/conftest.py` (keep the cloud-model network guard; point it
    at the renamed function if it is renamed)
- Delete:
  - `backend/src/nightcrate/services/imaging_quality.py`
  - `backend/tests/test_imaging_quality.py`
  - `backend/src/nightcrate/services/dew.py`
  - `backend/tests/test_dew.py`
  - `backend/tests/test_forecast_spread.py`. Move its `parse_cloud_models`
    tests to `test_weather_service.py` (rewritten for UTC keys), and its 0057
    CHECK test to `test_weather_cache.py`.

**Interfaces:**

- **Consumes:**
  - Tasks 1–3.
  - `compute_night_summary` and `moon_altitudes_at`.
  - `NearestMatchIndex` (UTC keys).
- **Produces — `astronomy.py`:**
- **New field `NightSummary.dark_intervals: dict[Literal["astronomical", "nautical", "civil"], list[tuple[datetime, datetime]]]`.**
  It is computed from the sampled sun altitudes (−18° / −12° / −6°),
  **independently of sunset**. Today's chained search returns `None` for
  every boundary when there is no sunset (`astronomy.py:226, 481`).
  - Walk the samples across noon-start → noon-end and emit every maximal run
    where the altitude is ≤ the threshold.
  - Run boundaries are the interpolated crossing instants, the same
    interpolation as `_find_crossing`. The window edges bound the runs.
  - This covers, in one rule: the normal night; Tromsø-style twilight with
    no sunset; continuous polar night (`[(noon_start, noon_end)]`); never
    dark (`[]`); and the ascending-then-descending case of two intervals.

- **Derived from `dark_intervals`,** so polar twilight and polar night are
  right for the Tonight calculator too (`calculators.py:350`):
  - `deepest_darkness_reached`;
  - `darkness_hours`;
  - `moonless_dark_hours`;
  - `no_imaging_window` (`= deepest == "none"`; it no longer requires a
    sunset).
- The existing `DarknessWindow` fields are unchanged.
- `def dark_intervals_for(summary, threshold) -> list[tuple[datetime, datetime]]`
  returns `summary.dark_intervals[threshold]`.
- `darkness_hours` and `moonless_dark_hours` sum over the intervals of the
  deepest threshold reached.

- **Produces — request `ForecastRequest`:**
  - `location_id: int`;
  - `rules: ImagingRules | None = None` (`None` means the saved or default
    rules);
  - `imaging_until: dict[str, datetime] = {}`.
    - Keys are night dates (`YYYY-MM-DD`).
    - Values must be **aware** ISO timestamps (an offset or `Z`). A naive
      value → 422.
    - An override whose date isn't a returned night (for example after the
      list moves on at noon) is **ignored**, not rejected. It is listed in
      `ignored_imaging_until: list[str]`.
    - An override for a returned night must lie within that night's
      noon-to-noon bounds; otherwise → 422. It applies **regardless of the
      darkness setting**, because the stop time is the user's, not the sky's.
      A cap before darkness gives `no` / `no_dark_time`; a cap after
      darkness still shortens the gear-out interval for rain.
- **Produces — response:**

  ```text
  ForecastResponse {
    location_id, location_name, timezone, geo_timezone,
    rules: ImagingRules, rules_saved: bool,
    fetched_at: str (ISO UTC),
    stale_sources: {forecast: int | null, cloud_models: int | null},  # minutes, null when fresh
    ignored_imaging_until: list[str],  # night dates whose override was dropped
    nights: NightResponse[7]
  }
  NightResponse {
    date, verdict, reason: ReasonResponse,
    clear_hours, dark_hours, unknown_hours: float,
    clear_pct: float | null,           # null when dark_hours == 0
    longest_gap_start, longest_gap_end,
    window_start, window_end,
    gear_out_start, gear_out_end,
    evaluated_from, evaluated_end,     # local "HH:MM" | null
    dark_intervals: [{start, end}],    # uncapped, for the rules' threshold; local "HH:MM" pairs
    imaging_until: str | null,         # ISO UTC
    model_verdicts: dict[str, Verdict], single_model: bool,
    cloud_source: "ecmwf" | "best_match_fallback",
    stale_minutes: int | null,         # decisive inputs actually used by this night
    requirements: dict[str, CheckState],
    extremes: {
      max_precip_probability_pct, max_precip_probability_at,
      precip_mm_total, max_gust_kmh, max_gust_at,
      min_dew_spread_c, min_dew_spread_at
    },                                 # each nullable; times local "HH:MM"
    sunset, sunrise,
    moon_illumination_pct, moon_phase_name, moonrise, moonset,
    hours: HourResponse[]
  }
  HourResponse {
    time,                              # local "YYYY-MM-DDTHH:MM" in the display tz, from start_utc via ZoneInfo
    start_utc, elapsed, excluded, dark_minutes, gear_out_minutes,
    darkness_category,                 # sun altitude band at the hour's midpoint: "day" | "civil" | "nautical" | "astro"
    state, model_states,
    checks: dict[str, CheckState],
    cloud_total_pct, cloud_low_pct, cloud_mid_pct, cloud_high_pct,  # primary model, nullable
    effective_cloud_pct: dict[str, float | null],
    precip_probability_pct, precip_mm, gust_kmh,  # shifted to cover this hour
    wind_kmh, temperature_c, dew_point_c, dew_spread_c,
    visibility_m, moon_altitude_deg,
    seeing: "good" | "fair" | "poor" | null,
    transparency: "good" | "fair" | "poor" | null
  }
  ReasonResponse {
    code, start, end,                  # local "HH:MM" | null
    value, limit, requirement, models, # units per Task 2's table
    bound                              # "at_most" | "at_least" | null
  }
  ```

  - Each night's `hours` cover `floor(gear-out start)` to `ceil(gear-out
    end)`, with the gear-out end **uncapped** by `imaging_until`, so later
    choices remain visible.
  - `extremes` cover the evaluated, non-elapsed interval: rain over gear-out
    hours, the others over dark hours.

- **Helpers:**
  - `async def _load_forecast_data(loc, ttl) -> ForecastData`, where
    `ForecastData(weather, cloud_models, pwv_by_time, aod_by_time, fetched_at: datetime, forecast_stale_minutes: int | None, cloud_stale_minutes: int | None)`.
  - **Freshness, per source:**
    - Fresh cache → use it.
    - Otherwise fetch. On a fetch failure, use the newest cached row of any
      age; the age becomes that source's stale minutes.
    - Main forecast with no row at all → `HTTPException(503, "Forecast unavailable — Open-Meteo could not be reached and nothing is cached")`.
    - Cloud models with no row at all → `None` (the fallback), not 503.
    - PWV and AOD are context only, so their staleness never affects a
      verdict.
  - **Per-night `stale_minutes`** = the maximum of the forecast's stale
    minutes (rain and wind always come from it) and, when that night's
    primary is ECMWF, the cloud models' stale minutes.
  - `def _now() -> datetime` returns `datetime.now(UTC)`. It is the only
    clock; tests patch it.
  - `_compute_seeing` falls back from the shear model to the surface model
    when shear inputs are incomplete. Either may return `None`.
- **Night anchoring.**
  - First night = the date of `_now()` in the display timezone **as a wall
    clock**: the previous date if the local hour is < 12, otherwise today.
    This is equivalent to `astronomy.tonight_date`, which subtracts 12 h on
    an aware datetime (Python does wall-clock arithmetic there).
  - Then the next 6 dates.
  - A date whose astronomy fails is skipped, as today, up to 8 attempts.
- **Primary choice per night.** `ecmwf_ifs025` when its figures cover every
  hour with dark or gear-out minutes; otherwise `best_match` with
  `cloud_source="best_match_fallback"` and no comparison models. Comparison
  models are the other members of `CLOUD_SPREAD_MODELS`.
- **Remove:**
  - `GET /forecast` and `GET /hourly`;
  - `_score_*`, `_aggregate_*` and `_mode_for`;
  - every `include_moon` parameter;
  - `weather_moon_penalty`;
  - the `imaging_quality` and `dew` modules.
- **Keep:** `/methodology` and the cache endpoints.
- **`METHODOLOGY`** is rewritten. It explains:
  - the verdicts;
  - the rules and how hours add up;
  - gear-out rain;
  - "rest of the night", and "night over" once darkness has ended;
  - model disagreement;
  - the ECMWF fallback;
  - stale data;
  - seeing and transparency as estimates;
  - the Open-Meteo attribution.

  No numbers it states may contradict `PRESETS`.

- [ ] **Step 1: Write failing tests.**

  **Fixtures.** In `test_weather_api.py`, build fixture weather from UTC
  timestamps anchored to a fixed date, and patch `_now`. Every test asserts
  exact values:

  - **`test_dark_interval_cases`** (astronomy tests):
    - 89°N on 2026-12-21 → continuous: `(noon_start, noon_end)`, and
      `deepest_darkness_reached == "astro"`.
    - Tromsø (`69.65, 18.96`, `Europe/Oslo`) on 2026-12-21:
      - `sunset is None`;
      - an astronomical interval from about 15:56 to 05:28 UTC (±5 min);
      - `darkness_hours` 13.55 ± 0.1;
      - `no_imaging_window is False`.
    - 78°N on 2026-06-21 → `[]` for astronomical, and
      `no_imaging_window is True`.
    - `84.5, −15.0`, `UTC`, 2026-12-21 → two astronomical intervals:
      noon-start to about 12:23:21, and about 13:32:47 to noon-end (±2 min),
      totalling 22.84 ± 0.05 h.
    - `33.45, −112.07` on 2026-10-17 → both crossings, and astronomical dark
      lasts between 9 and 11 h.
    - Existing `test_astronomy.py` expectations that encoded the old polar
      behaviour are updated, with the reason given in the test docstring.
  - **`test_forecast_returns_seven_nights`:** POST `{location_id}` → 200,
    7 nights, `rules_saved is False`, and `rules` equal to the
    attended-session preset.
  - **`test_forecast_uses_saved_rules`:** PUT the left-out rules, then POST →
    `rules_saved is True` and `rules.rain_policy == "night_off"`.
  - **`test_forecast_draft_rules_preview`:**
    - The fixture is clear all night, with rain 10% only at 02:00 local on
      night 1.
    - With the default rules (attended: 20%, `hours_lost`) → night 1 `go`.
    - With draft `rules` = left-out → night 1 `no` / `rain`, start `"02:00"`,
      end `"03:00"`.
    - Afterwards GET still returns `saved is False`.
  - **`test_forecast_imaging_until`:**
    - Short-session rules; `imaging_until` = night 1 at 21:30 local, as an
      aware ISO string.
    - → night 1 `no` / `no_window`, with `evaluated_end == "21:30"`.
    - Its `hours` still extend to the uncapped gear-out end.
    - Night 2 is unchanged from a request without the override.
  - **`test_forecast_rejects_naive_imaging_until`:** a naive
    `"2026-10-17T21:30"` → 422.
  - **`test_forecast_ignores_expired_imaging_until`:** an override keyed to
    the day before night 1 → 200, `ignored_imaging_until ==` [that date], and
    every night is unaffected.
  - **`test_forecast_override_survives_darkness_change`:**
    - An override at 19:45 local on night 1, which lies inside nautical
      darkness but before astronomical darkness.
    - Draft rules with `darkness="nautical"` → applied
      (`evaluated_end == "19:45"`).
    - With `"astronomical"` → still applied, giving `no` / `no_dark_time`;
      `ignored_imaging_until == []`.
  - **`test_forecast_override_outside_night_bounds_422`:** an aware time
    on the next afternoon (after noon-end) → 422.
  - **`test_forecast_anchor_noon_transition`:** `_now` at 11:59 local → the
    first night is yesterday's date; at 12:01 → today's.
  - **`test_forecast_night_under_way_stays_listed`:**
    - `_now` = night 1's date + 1 day at 01:00 local → nights[0].date is
      still night 1.
    - `evaluated_from == "01:00"`.
    - The hour starting 19:00 has `elapsed: true`.
  - **`test_forecast_stale_after_failed_fetch`:**
    - Control: a fresh cache whose weather makes night 1 `go`.
    - Then make the same cache row 9 h old (TTL 6) and make `fetch_weather`
      raise.
    - → 200, `stale_sources.forecast` in [538, 542], and night 1
      `not_enough_data` / `stale`.
  - **`test_forecast_stale_cloud_only_affects_ecmwf_nights`:**
    - Restore the real `_fetch_or_cached_cloud_models` over the autouse mock.
    - The cloud-model cache row is 9 h old; `fetch_cloud_models` raises; ECMWF
      in that row covers only nights 1–3; the main forecast is fresh.
    - → nights 1–3 have `stale_minutes ≈ 540` and are not `go`.
    - → night 5 has `cloud_source == "best_match_fallback"` and
      `stale_minutes is None`.
  - **`test_forecast_503_when_nothing_cached`:** no cache and the fetch
    raises → 503.
  - **`test_forecast_ecmwf_fallback_labelled`:** cloud models `None` → every
    night has `cloud_source == "best_match_fallback"` and `single_model` true.
  - **`test_forecast_models_disagree_end_to_end`:** cloud models with ECMWF
    clear and GFS overcast → night 1 `uncertain`, with both model verdicts.
  - **`test_forecast_dst_fallback_legacy_cache`:**
    - Location `America/New_York`; `_now` 2026-10-31 15:00 local.
    - A cached legacy ISO response with `utc_offset_seconds=-14400`.
    - → night 2026-10-31's hours have strictly increasing `start_utc`, one
      hour apart.
    - Their local `time` labels include `2026-11-01T01:00` twice.
    - Its `dark_intervals` match `compute_night_summary`'s astronomical intervals.
  - **`test_forecast_null_context_inputs`:**
    - Humidity, visibility and wind are `null` for night 1's 22:00 row.
    - Wind is not counted.
    - → 200; that hour has `seeing is None`, `transparency is None`,
      `wind_kmh is None`, and `checks.wind == "not_counted"`.
  - **`test_forecast_display_tz_differs_from_geo_tz`:**
    - Display `America/New_York`, site `America/Los_Angeles` (the pattern of
      `test_hourly_moon_aligned_by_utc_across_timezones`).
    - `sunset` and reason times are in the display zone.
    - Each hour's `time` equals `start_utc` converted to New York.
  - **`test_forecast_polar_summer`:** the existing polar location in June →
    every night `no` / `never_dark` under astronomical rules, with hours
    present.
  - **`test_forecast_polar_night`:** 89°N in December → `dark_hours == 24`
    for night 1, and the verdict is not `never_dark`.
  - **`test_forecast_polar_twilight_no_sunset`:** Tromsø in December →
    night 1 has `dark_hours` 13.55 ± 0.1, `sunset is None`, and gear-out
    bounded by the noon-to-noon night.
  - **`test_forecast_southern_winter`:** `-33.45, -70.66`,
    `America/Santiago`, a June anchor → night 1 has `dark_hours > 9`.
  - **`test_settings_ignore_retired_moon_key`:** a stored row
    `weather_moon_penalty=false` → `get_settings()` loads without error.
  - **`test_methodology_mentions_verdicts`:** the text contains "Go",
    "Uncertain", "Not enough data" and "rest of the night", and does not
    contain "0–100".
- [ ] **Step 2: Run**
  `uv run pytest tests/test_weather_api.py tests/test_weather_settings.py tests/test_astronomy.py -q`.
  Expect failures.
- [ ] **Step 3: Implement.** Then run
  `rg "imaging_quality|include_moon|weather_moon_penalty|FORECAST_UNCERTAIN|services.dew" backend/`
  and expect no hits outside migrations and docs.
- [ ] **Step 4: Run the backend gate:**
  `cd backend && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run bandit -r src/ -q && uv run pytest -q -n auto`.
  - Expect everything to pass.
  - Bandit reports only the three deferred low findings.
- [ ] **Step 5:** Leave everything unstaged. Report the exact test counts.

---

## Phase C — Frontend (Claude runs rendered checks; there is no frontend test runner)

Shared frontend facts:

- React Query with `apiFetch` (`frontend/src/api/client.ts`).
- The persistent `WeatherPage` and its deep link (`?location&date`) must keep
  working (`WeatherPage.tsx:107-137`).
- Units come from `useSettingsStore` (`weather_units`).
- **Tasks 5–7 are handed off as one phase,** because the API types change
  under both `WeatherPage` and `TonightCalc`.
- **Gate at the end of the phase:** `cd frontend && npm run build` succeeds
  (TypeScript and Vite); the existing bundle-size warning is acceptable.
  Builds between tasks may fail.

### Task 5: API client, week list and night details

**Files:**

- Modify:
  - `frontend/src/api/weather.ts` (rewrite types)
  - `frontend/src/pages/WeatherPage.tsx`
- Create:
  - `frontend/src/lib/weatherVerdict.ts`
  - `frontend/src/components/weather/VerdictPill.tsx`
  - `frontend/src/components/weather/HourStrip.tsx`
  - `frontend/src/components/weather/WeekList.tsx`
  - `frontend/src/components/weather/NightDetailPanel.tsx`
- Delete:
  - `frontend/src/components/weather/DailyCard.tsx`
  - `frontend/src/components/weather/HourlyTimeline.tsx`
  - `QualityBadge.tsx` and `lib/weatherColors.ts` are deleted in Task 7,
    after `TonightCalc` stops importing them. Run `rg` first to confirm
    there are no other importers.

**Interfaces:**

- **`api/weather.ts`:**
  - TypeScript types mirror Task 4's models exactly (snake_case).
  - `ImagingRules`, `Verdict`, `CheckState` and `HourState` are exported.
  - Functions:
    - `fetchForecast(req: ForecastRequest)`: POST `/weather/forecast`.
    - `fetchImagingRules(locationId)`
    - `saveImagingRules(locationId, rules)`: PUT.
    - `fetchPresets()`
  - **`forecastQueryOptions(locationId, draftRules?, imagingUntil?)`** returns
    the React Query options both `WeatherPage` and `TonightCalc` use:
    - key: `["weather-forecast", locationId, draftRules ?? "saved", imagingUntil ?? {}]`;
    - `refetchOnWindowFocus: true`;
    - `refetchInterval` = the time until the next whole hour plus 5 s, capped
      at 15 min, so tonight's "rest of the night" evaluation changes on hour
      boundaries.
- **`lib/weatherVerdict.ts`:**
  - **`buildClock(nights: Night[]): ClockColumn[]`:**
    - One column per local clock hour, from the earliest hour start to the
      latest hour end across `nights`.
    - Ordered from noon through the next noon.
    - `ClockColumn { hour: number /* 0-23 */, label: string /* "18" */ }`.
  - **`cellsFor(night: Night, clock: ClockColumn[]): Hour[][]`:** the hours in
    each column. Usually 1. On a 25-h night the repeated hour gives 2, drawn
    side by side at half width. On a 23-h night the skipped hour gives 0,
    drawn as an empty, dimmed cell.
  - **`reasonText(reason: Reason, units: WeatherUnits): string`.** When
    `reason.bound` is set, prefix the value with "at most" or "at least" and
    append ", even if the missing hours are clear". Templates:
    - `rain`: "Rain chance {value}% from {start}–{end} — your limit is {limit}%"
    - `rain_amount`: "Rain forecast ({value} mm/in) at {start}"
    - `clear_fraction`: "{value}% of dark hours clear — you need more than {limit}%"
    - `min_hours`: "Only {value} h clear — you need at least {limit} h"
    - `gap`: "Not clear for {value} h from {start} — longest allowed gap is {limit} h"
    - `no_window`: "No {limit} h clear stretch — longest is {value} h"
    - `short_window`: "Clear {start}–{end}"
    - `clear_all_night`: "Clear all night"
    - `clear_with_gaps`: "{Requirement} {start}–{end}" (Cloud, Rain, Wind,
      Dew, Moon), or "Not forecast {start}–{end}" when the requirement is
      `unknown`
    - `never_dark`: "Never dark enough for your setting"
    - `no_dark_time`: "No dark time before your stop time ({start})"
    - `models_disagree`: "Models disagree: ECMWF {v}, GFS {v}[, ICON {v}]"
    - `missing_data`: "{Requirement} not forecast from {start}"
    - `stale`: "Forecast is {value/60 rounded} h old — refresh failed"
    - `night_over`: "Night over"
    - Model display names: `ecmwf_ifs025` → ECMWF, `gfs_seamless` → GFS,
      `icon_seamless` → ICON, `best_match` → "Open-Meteo default".
  - Unit formatters for temperature, wind, rain amount and dew spread, using
    the primary unit from `weather_units`.
- **`VerdictPill({ verdict, size? })`:**
  - Go: filled blue, ✓.
  - Uncertain: orange outline, ?.
  - No: filled grey, ✕.
  - Not enough data: dashed outline, –.
  - Night over: grey text.
- **`HourStrip({ night, clock, height })`.** Cell patterns follow spec §5.1:

  | Cell | Pattern |
  |---|---|
  | clear | solid blue |
  | `not_clear` with a cloud fail | grey hatch |
  | `not_clear` with a rain fail | orange dots |
  | `not_clear` for another reason (wind, dew, moon) | blue/grey crosshatch |
  | models disagree on the hour | blue/grey vertical stripes |
  | `unknown` | dashed outline |
  | `outside` (and any elapsed hour) | dim |

  - Every cell has a Tooltip (`enterTouchDelay={0}`) showing the time, state
    and failing requirement(s).
- **`WeekList({ nights, clock, selectedDate, onSelect, units })`.**
  - Spec §5.1, layout B: an axis row, then one row per night: date, pill,
    strip, reason, and "{clear} h clear of {dark}" · window · moon.
  - The hours line also shows "from {evaluated_from}" when the night is under
    way, and "until {evaluated_end}" when an override is active. That way
    "Go · from 23:00 · until 01:00" can be read without opening the
    details.
  - Rows are keyboard-focusable buttons (Enter or Space selects).
  - The selected row is outlined in the primary (amber) colour.
- **`NightDetailPanel({ night, clock, rules, units, onImagingUntilChange, onClose })`.**
  - Spec §5.2.
  - **Checklist,** built from `night.requirements` plus `night.extremes`.
  - **"Imaging until" select.** Options: "end of darkness", then each whole
    hour inside the night's **uncapped** `dark_intervals`, taken from the
    `start_utc` of its hours, so an early choice never removes later ones.
    The value sent is the hour's `start_utc` (aware ISO). An active stop time
    that falls outside the current options (after a darkness change, say) is
    still listed and shown selected, so it stays visible and editable.
  - **Numbers grid** in three groups, aligned to `clock`, with the per-row
    summary column on the right.
  - **"Show each model's cloud" checkbox.** It defaults on when
    `verdict === "uncertain"` and adds one row per model from
    `effective_cloud_pct`.
  - Elapsed columns are faded, and the header says "from {evaluated_from}"
    when that is set.
  - Close button.
- **`WeatherPage`:**
  - **Removed:** the moon checkbox, `DailyCard` and `HourlyTimeline`.
  - **Top bar:** location selector, "Forecast fetched {local time}", and a
    Refresh button.
    - Refresh invalidates the query. If the server cache is still fresh it
      returns the same data; that is acceptable.
  - **Stale data:** when either `stale_sources` value is set, a caption
    reads "Showing a forecast {h} h old — Open-Meteo could not be reached",
    using the larger value.
  - **Fallback:** when any night's `cloud_source` is `best_match_fallback`, a
    caption reads "Cloud from Open-Meteo's default model — ECMWF unavailable".
  - **Queries** use `forecastQueryOptions`.
  - **"Imaging until"** is page state: `Record<date, string /* ISO UTC */>`.
    - It is cleared on location change.
    - It is pruned after every response: drop keys listed in
      `ignored_imaging_until`, or not among `nights[].date`.
  - **`MethodologyInfo`:** replace its "score"/"scoring" heading and error
    wording (`MethodologyInfo.tsx:52`) with "How the verdict works".
  - The detail panel renders under the `WeekList`.
  - Keep the attribution, the `EasterEggWand` and `MethodologyInfo`.

- [ ] **Step 1:** Implement the types and lib, then the components, then the
  page.
- [ ] **Step 2: Run** `cd frontend && npx tsc -p tsconfig.app.json --noEmit 2>&1 | rg -v TonightCalc`.
  Expect no errors outside `TonightCalc`.

### Task 6: Rules bar and rules editor

**Files:**

- Create:
  - `frontend/src/components/weather/RulesBar.tsx`
  - `frontend/src/components/weather/RulesEditor.tsx`
- Modify:
  - `frontend/src/pages/WeatherPage.tsx`
  - `frontend/src/pages/SettingsPage.tsx` (remove the moon toggle)
  - `frontend/src/api/settings.ts` (remove `weather_moon_penalty`)

**Interfaces:**

- **`RulesBar({ locationName, rules, onEdit, editing })`.** A one-line summary
  in the mockup's order:
  - "Your rules · {location}";
  - session;
  - "Go when …";
  - "Clear = cloud ≤ x%";
  - "Rain x% from {gear-out}";
  - wind;
  - darkness;
  - an "Edit rules" button, hidden while `editing`.
- **`RulesEditor({ locationId, locationName, saved, rules, presets, otherLocations, onDraftChange, onCancel, onSaved, previewCounts })`.**
  - Layout from spec §5.3: three groups.
  - A footer reads "Changes apply only to {location}".
  - **Presets** appear only when `!saved`. Choosing one replaces the draft.
  - **"Copy from another location"** is a select over `otherLocations`. It
    loads that location's rules via `fetchImagingRules` and replaces the draft.
  - **Number inputs** are bounded as in Task 1. Invalid input disables Save
    and shows the field's error text.
  - **Disabled limits** (wind, dew, moon unticked) are shown dimmed and are
    not editable.
  - **Live preview.** `onDraftChange(draft)` is debounced 300 ms. The page
    re-queries with `rules: draft`, and `previewCounts` comes from that
    response: "With these rules this week: n Go · n Uncertain · n No ·
    n Not enough data".
  - **Save** PUTs, then:
    - writes the response into `["imaging-rules", locationId]` with
      `setQueryData`, so presets disappear immediately;
    - invalidates `["weather-forecast", locationId]`;
    - clears the draft and calls `onSaved`.
  - **Cancel** discards the draft.
  - **A late "copy from" response** is ignored if the location changed while
    it was in flight (compare the location ID at resolution).
- **`WeatherPage`:**
  - Fetches rules (`["imaging-rules", locationId]`) and presets
    (`["imaging-rule-presets"]`).
  - When no rules are saved, shows "These are default rules — set your own
    for {location}" with an "Edit rules" button.
  - Switching location while editing discards the draft and closes the
    editor.
- [ ] **Step 1:** Implement.
- [ ] **Step 2:** `rg weather_moon_penalty frontend/src` → no hits.

### Task 7: Tonight card

**Files:**

- Create: `frontend/src/components/weather/NightCard.tsx`
- Modify: `frontend/src/components/calculators/TonightCalc.tsx`

**Interfaces:**

- **`NightCard({ night, clock, units, href })`.** The layout-A card from the
  mockup: date, `VerdictPill`, reason, `HourStrip`, clear hours and window,
  and moon. The whole card is a `RouterLink` to `href`.
- **`lib/timezoneDate.ts` `tonightDate`** must match the backend anchor
  exactly: take the wall-clock time in `timezone`; if the local hour is
  < 12, return the previous calendar date, otherwise today's. Today it
  subtracts 12 elapsed hours, which differs from the backend across DST, for
  example New York at 11:30 on 2026-11-01.
- **`TonightCalc`:**
  - The default date uses `tonightDate(timezone)` instead of
    `todayInTimezone`.
  - While the user hasn't picked a date, it follows `tonightDate`. It
    re-evaluates on each forecast refetch, so crossing local noon advances
    it. An explicitly picked date is kept.
  - The forecast query uses `forecastQueryOptions(locationId)`. This shares
    the Weather page's cache, and works when the Weather page has never
    mounted.
  - It finds the night whose `date` matches and renders `NightCard`, linking
    to `/weather?location={id}&date={date}`.
  - Text for "outside the 7-night window" stays.
  - The help paragraph about the "composite score" is replaced: it now
    describes the verdict and states that it uses the location's imaging
    rules.
- **`WeatherPage`'s deep-link effect** also opens the details panel for the
  linked date. It already selects that date.
- **Delete** `components/weather/QualityBadge.tsx` and `lib/weatherColors.ts`
  once `rg "QualityBadge|weatherColors" frontend/src` shows no importers.
- [ ] **Step 1:** Implement.
- [ ] **Step 2: Phase gate.** `cd frontend && npm run build` succeeds, and
  `npm run lint` reports no new errors in the changed files.
- [ ] **Step 3:** Leave everything unstaged; report. Claude runs rendered
  checks R1–R10.

---

## Phase D — Documentation (Claude, after Phase C review)

### Task 8: Current docs

**Files:**

- Modify:
  - `docs/development-decisions.md` (Weather section)
  - `docs/weather-algorithms.md`
  - `README.md` (Weather feature bullet and methodology mention)
  - `docs/README.md` (code map: new modules)
  - `PLAN.md` (v0.41.9 checklist)
- Move: `docs/imaging-quality-model.md` → `docs/archive/imaging-quality-model.md`.
  Leave a one-line pointer in `docs/README.md`.

What changes:

- **`docs/development-decisions.md`, Weather section:** replace "existing
  contract" with the verdict contract:
  - rules per location;
  - rain semantics, with the preceding-hour shift;
  - missing-data precedence;
  - complete-sequence model comparison;
  - the ECMWF fallback label;
  - stale data never gives Go;
  - rest of the night;
  - darkness independent of the moon;
  - no blended score;
  - presets only for unsaved locations.
- **`docs/weather-algorithms.md`:** rewrite §5–6 for the evaluator, keeping
  §4.
- [ ] **Step 1:** Edit.
- [ ] **Step 2:** Check that links resolve (`rg -o "\]\(([^)]+)\)"` on the
  changed files; every target exists), and that facts match the code.
- [ ] **Step 3:** Leave unstaged.

---

## Rendered checks (Claude, after each frontend task)

These run with Playwright against `make dev` on a disposable workspace. Each
uses forecast fixtures where the real sky won't give the needed case
(intercepted POST responses).

- **R1. Week list layout.** Seven rows line up on one clock. Patterns are
  visible in light and dark themes. Keyboard Tab and Enter select a row.
- **R2. Details panel.** It opens below with a Close button. Checklist values
  match the grid. Imperial units swap the primary unit.
- **R3. Tablet width (820 px).** No horizontal page scroll, with the strip
  scrolling inside its row if needed. Tap shows cell tooltips.
- **R4. Edge cases.** A fixture with a DST fall-back night, a stale response,
  an ECMWF fallback, and an Uncertain night (model rows on by default).
- **R5. Refresh.** With `page.clock`, confirm:
  - a forecast refetch fires just after the next whole hour, and on window
    focus;
  - `tonightDate` flips from the previous date to today between 11:59 and
    12:01 local, including on 2026-11-01 in New York. The browser clock can't move
  the backend's `_now`, so the night-under-way and noon behaviour are proven
  by the Task 4 tests, not here.
- **R6. New-location rules.** With no saved rules, presets are shown; after
  Save they are hidden, and a reload keeps them hidden.
- **R7. Live preview.** Ticking "Count wind" with a gusty fixture changes the
  verdicts and counts before Save; Cancel restores them.
- **R8. Unsaved draft.** Switching location with an unsaved draft discards it,
  and the new location's rules are unchanged.
- **R9. Tonight card.** It shows the same verdict as the Weather page row, and
  clicking it opens the Weather page with that night's details. Also check it
  on a fresh load where the Weather page has never mounted.
- **R10. Real endpoint, no interception.** Against the live backend with a
  disposable workspace:
  1. Edit rules and see the preview change.
  2. Save, then reopen the editor immediately: no presets, saved values
     shown.
  3. Reload.
  4. The Tonight card shows the same verdict as the Weather row.

## Delivery gates

1. **Per phase:**
   - Codex implements and leaves the work unstaged.
   - Claude diffs the before/after inventory, reads the diff, re-runs the
     task's commands, then stages.
   - Findings go back to Codex in one batch.
2. **High-stakes checks:**
   - The migration tests (Task 1).
   - A manual upgrade by Claude, outside Codex's writable roots:
     1. Copy Fred's workspace database (at 0057) into the session scratchpad.
     2. Record the row counts of every table.
     3. Run `apply_migrations(copy)`.
     4. Assert row counts unchanged for every table except yoyo's own
        bookkeeping tables (`_yoyo_*`, `yoyo_lock`), `integrity_check` ok, an
        empty `foreign_key_check`, and `0058` present in `_yoyo_migration`.
     5. Delete the copy.
   - Hand-computed evaluator examples (Task 2).
   - The API contract tests (Task 4).
3. **Before Fred's acceptance test:**
   - A fresh independent Codex review (`gpt-5.6-sol`, high, read-only) of the
     whole diff.
   - The full backend suite.
   - `npm run build`.
   - The rendered checks R1–R10.
4. **Release:** version files, `sync-docs` and publish follow
   `finalize-session`, with Fred's authorization.

## Codex review

- **Mode:** independent plan review. **Rounds:** 4 of 5. Records:
  `.superpowers/codex/v0.41.9/` (local). The design stage before this was a
  blinded pre-pass (`.superpowers/codex/2026-10-17-weather-redesign/`).
- **Adopted changes:**
  - **Provider time contract.** Open-Meteo uses one fixed offset per response
    and ignores DST. The plan now requests `timezone=GMT` and
    `timeformat=unixtime`, normalizes to UTC at parse time, decodes legacy
    cache rows with their offset, and ignores off-grid legacy rows.
  - **Inputs.** A complete hourly timeline with per-field source resolution.
    Preceding-hour shift for precipitation and gusts.
  - **Darkness.**
    - Intervals found independently of sunset. That covers Tromsø-style
      polar twilight, continuous polar night, and two intervals in one
      night.
    - The Tonight totals derive from them.
    - "Night over" at the end of darkness (Fred's decision D1).
  - **Freshness** tracked per source and per night.
  - **"Imaging until"** as an aware timestamp that survives darkness changes.
    Expired-night overrides are ignored, not rejected.
  - **Reasons.** Priority order and ties, units per code, and bound
    direction (`at_most` / `at_least`) when values are unknown.
    Relevance-filtered unknown reasons; night-level requirement aggregation.
  - **Missing context values** stay missing (seeing, transparency); no
    fabricated 50.
  - **Frontend.**
    - A shared, hour-aligned forecast refresh, and a `tonightDate` that
      matches the backend.
    - The rules cache is updated on save, and the stop time stays visible.
  - **Verification.**
    - Migrations tested through yoyo on fresh and 0057 databases.
    - Draft and stale tests with controls.
    - A real-endpoint rendered flow (R10).
  - Corrected hand-computed fixtures.
- **Fred's decision D1 (2026-10-17):** a night shows "Night over" once
  darkness has ended, not only once the gear comes in.
- **Tracked items:** none. No material Codex finding was rejected, and no
  disagreement remained.
- **Status at candidate preparation (2026-10-23):** unchanged; no tracked
  items.
