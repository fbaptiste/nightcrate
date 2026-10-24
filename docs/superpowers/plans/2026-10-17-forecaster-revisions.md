# Imaging Forecaster Revisions (v0.41.9) Implementation Plan

> **For agentic workers:** In this project, Codex implements one task at a
> time under `docs/agent-collaboration.md` §4. Claude reviews, re-runs the
> checks and stages. Codex never stages, commits, pushes or opens PRs. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revise the v0.41.9 imaging verdict as the consolidated spec
describes. The main changes:

- cloud is judged on each model's total only;
- two chance limits, an amount threshold, and "Precipitation forecasts to
  check" (Main forecast or Any model);
- declared per-model coverage;
- per-model night statuses, with a shared window for short sessions;
- vetoes, precedence and freshness;
- per-night gear and imaging controls, and minute-level re-evaluation;
- clearer reasons and night details.

All of this keeps the hour-by-hour strip exactly as it is.

**Architecture:**

- **Backend, pure.**
  - `services/forecast_coverage.py` (new) decides which model is expected for
    which hour, and the period of each precipitation chance.
  - `services/forecast_inputs.py` builds complete hourly inputs carrying
    per-model total, layers, amount and expected flags.
  - The evaluator is split into `imaging_types.py`, `imaging_hours.py`,
    `imaging_session.py` and `imaging_verdict.py`. It now owns the choice of
    primary model and the fallback.
- **Backend, HTTP.**
  - `services/weather.py` widens the cloud request to precipitation amounts,
    the NBM chance and model metadata.
  - `api/weather.py` keeps caching. It loads each cloud row together with its
    metadata, and repairs truncated rows at most once an hour.
  - `api/weather.py` also takes per-night controls and returns structured
    evidence.
- **Frontend.** It renders the server's verdicts and evidence. It never
  derives a verdict.

**Tech stack:** Python 3.14, FastAPI, Pydantic, aiosqlite, yoyo SQL
migrations, pytest (anyio). React 19, TypeScript, MUI 7, TanStack Query.

**Spec:** [docs/superpowers/specs/2026-10-17-forecaster-revisions-design.md](../specs/2026-10-17-forecaster-revisions-design.md).
Read all of it before any task, especially §11. Its §11 clarifications (C1–C17)
override the body. Section references (§) below are to that spec. The v0.41.9
spec and its plan,
[2026-10-17-weather-verdict.md](2026-10-17-weather-verdict.md), still govern
everything this plan does not change.

**Base:** branch `v0.41.9/weather-verdict` on `a3707b6`. All v0.41.9 work is
staged and uncommitted. This plan extends that release; it adds no new
version.

## Global Constraints

- **Hour strip frozen (Fred, C1).** Do not change `HourStrip`'s icons,
  `iconSize`, cell geometry, colours or layout. Only the data behind it
  changes:
  - the `models` cell appears only when the backend sets `disagrees`;
  - with a fractional offset (C16), labels and the darkness band take their
    positions from the actual timestamps.
- **Verdict guarantee (§1, §5.10).** With rules, intervals and declared
  coverage fixed, replacing any known value by unknown never turns a non-Go
  into Go. Every new branch in the evaluator must keep this.
- **Coverage is declared, never inferred (C4).** Which models are expected
  for an hour depends only on the fetch time, the declared constants and the
  request range, never on which values arrived.
- **Time contract unchanged** (v0.41.9 plan, Global Constraints).
  - UTC everywhere; display labels come from `ZoneInfo`.
  - `precipitation`, `precipitation_probability` and `wind_gusts_10m` describe
    the preceding hour, so the value stamped `T+1h` covers `[T, T+1h)`.
  - Every new reason, period and boundary in the API carries a `*_utc` field
    next to its display label (C14).
- **Missing stays missing.**
  - A missing total is unknown, and is never rebuilt from layers (§4.2).
  - Nothing is prorated (C12).
  - A positive amount never prints as zero (§6.6).
- **Colour and text.**
  - Blue, orange, grey or teal only.
  - Every state also carries text, a shape or a pattern; "not current" is
    text (C15).
  - Use theme tokens, with six-digit hex.
  - No question-mark help icons or tooltip underlines. The "?" glyph in the
    checklist is a state mark, not a help icon.
- **Architecture rules.**
  - Services import neither `api/` nor FastAPI.
  - Outbound HTTP goes only through `services/http_client.get`.
  - No new dependency, including for tests.
- **Migrations.** Never edit 0057 or 0058. The new ones are 0059 (rules) and
  0060 (cache source). Verify each on a fresh database and on a copy at the
  preceding migration.
- **Delivery.** Codex leaves all work unstaged. Nothing is committed without
  Fred's authorization.

## Fred's decisions

- **F1 — saved rules are discarded** (Fred, 2026-10-18; spec §11 F1). 0059
  recreates `location_imaging_rules` empty with the new schema. This replaces
  spec §7, and no row is migrated.
- **F2 — "Longest interruption"** is adopted (Fred, 2026-10-18) for the
  editor label, the rules bar and the `gap` reason text (Task 9).
- **F3 — one chance limit, no hour-or-block distinction** (Fred, 2026-10-18,
  after acceptance-testing the "?" marks). It is implemented as a follow-up
  task after Task 11 (spec §11 F3). The per-period limit, the chance-period
  classification, the NBM series and the related display are removed.

## Review Focus

These failure modes are implied by the spec but not exercised by any §9
case. Each has a test in its owning task.

1. **Minute polling meets a truncated or obsolete cache.** A model that
   persistently falls short of its declared coverage, or a cloud row written
   before this change, must cause at most one repair refetch per source per
   hour. Concurrent requests must share that refetch, and an old row must
   never read as Not enough data for want of new fields. Tests (Task 2):
   - `test_repair_refetch_at_most_hourly`;
   - `test_concurrent_repairs_coalesce`;
   - `test_legacy_cloud_row_refetched_within_ttl`.
2. **Upgrading a database with saved rules (F1).** The rules table becomes
   empty. Every other table, including `location`, is untouched. A location
   whose rules were dropped evaluates with the default preset and shows the
   preset prompt, with no 500 and no stale draft (Task 1,
   `test_migration_0059_discards_rules_only`). Claude's manual upgrade runs on
   a copy of Fred's database (Delivery gates).
3. **The policy changes, or the night expires, while per-night controls are
   set.** A draft that switches `night_off` to `hours_lost` with gear controls
   set must be evaluated. The inapplicable controls are reported in
   `ignored_controls`; there is no 422 (Task 6,
   `test_inapplicable_controls_ignored_and_reported`).
4. **A site inside NBM's grid whose response lacks NBM keys** (an NBM
   outage). The period must be unknown and the lower limit must apply. With
   equal limits the verdict must be identical to the hourly case (Task 3,
   `test_grid_without_nbm_keys_is_unknown`; Task 4,
   `test_equal_limits_period_irrelevant`).
5. **The main forecast and the cloud/metadata pair come from different
   refreshes, or either is stale.** Chance periods must fall back to unknown;
   they must never be classified from metadata of another snapshot (Task 3,
   `test_periods_unknown_when_generations_differ`,
   `test_periods_unknown_when_stale`).

---

## Phase A — Rules (high-stakes: schema on user data)

### Task 1: Rules model, presets, share ≥, migration 0059, rules API

**Files:**
- Create: `backend/src/nightcrate/db/migrations/0059.imaging_rules_precipitation.sql`
- Modify: `backend/src/nightcrate/services/imaging_rules.py`,
  `backend/src/nightcrate/services/imaging_verdict.py`
  (the one-line share comparison only),
  `backend/src/nightcrate/api/imaging_rules.py` (only if needed: field
  lists come from the model)
- Modify: `DB_SCHEMA.md`, `DB_SCHEMA_DDL.sql`
- Test: `backend/tests/test_imaging_rules.py`, `backend/tests/test_imaging_verdict.py`

**Interfaces:**
- Produces, in `services/imaging_rules.py`:

```python
RainForecasts = Literal["main", "any_model"]

class ImagingRules(BaseModel):          # changed and added fields only
    min_clear_fraction_pct: Annotated[float, Field(ge=1, le=100)]   # "at least"
    rain_max_probability_pct: Annotated[float, Field(ge=0, le=100)]          # per hour
    rain_max_period_probability_pct: Annotated[float, Field(ge=0, le=100)]   # per multi-hour period
    rain_amount_threshold_mm: Annotated[float, Field(ge=0)]   # fails when amount > threshold; no upper bound (spec silent)
    rain_forecasts: RainForecasts
```

- Presets (§4.4). Fields not listed keep their current preset values.

| key | session | share / min h | chance h / period | threshold | policy | forecasts | wind |
|---|---|---|---|---|---|---|---|
| `left_out_all_night` | all_night | 50 / 2 | 10 / 10 | 0 | night_off | any_model | on 30/45 |
| `attended_session` | short_session 2 h | 50 / 2 | 20 / 20 | 0 | hours_lost | main | on 30/45 |
| `dome` | all_night | 50 / 2 | 20 / 20 | 0 | hours_lost | main | off |

- [ ] **Step 1: Write the failing tests** in `test_imaging_rules.py`:
  - `test_presets_match_spec`: every preset's full field set equals the table
    above plus the unchanged fields (cloud 20, gear 30/30, dew off at 3.0,
    moon off, astronomical).
  - `test_rules_accept_fraction_100` (replaces
    `test_rules_reject_fraction_100`) and `test_rules_reject_fraction_below_1`
    (0.5 raises `ValidationError`).
  - `test_rules_threshold_bounds`: 0 and 5 are accepted; −0.1 is rejected.
  - `test_put_get_roundtrip_new_fields`: PUT a rule set with period 25,
    threshold 0.1 and `any_model`; GET returns the same values.
  - `test_migration_0059_fresh_via_yoyo`: a fresh database has the table with
    the new columns and the trigger, and `0059…` is recorded.
  - `test_migration_0059_discards_rules_only` (F1):
    1. At 0058, insert two locations, each with a saved rules row.
    2. After migration, `location_imaging_rules` is empty and has the new
       columns and CHECKs.
    3. Both locations and all other tables' row counts are unchanged.
    4. `PRAGMA integrity_check` is `ok` and `foreign_key_check` is empty.
    5. A PUT then a GET round-trips, and an UPDATE changes `updated_at` (the
       trigger was recreated).
    6. `GET /api/locations/{id}/imaging-rules` returns `saved: false` with the
       default preset.
  - In `test_imaging_verdict.py`, replace `test_all_night_exactly_half_is_no`
    with `test_all_night_exactly_at_share_is_go`. At share 50 with 5.0 of 10.0
    dark hours clear and min hours 2, the verdict is `go` (§4.1).

- [ ] **Step 2: Run them and see them fail.**
  `cd backend && uv run pytest tests/test_imaging_rules.py tests/test_imaging_verdict.py -q`
  should fail on the new fields, the presets and the share comparison.

- [ ] **Step 3: Implement.**
  - **0059** drops `location_imaging_rules` and its trigger, then creates
    them again with the new schema (F1: no data is copied). No table
    references it. It sets these CHECKs:
    - `min_clear_fraction_pct >= 1 AND <= 100`;
    - `rain_max_period_probability_pct` between 0 and 100;
    - `rain_amount_threshold_mm >= 0`;
    - `rain_forecasts IN ('main','any_model')`.
  - The migration recreates `trg_location_imaging_rules_updated_at`.
  - **The share comparison** in `_session_evaluation` changes from failing on
    `fraction <= limit` to failing on `fraction < limit`.

- [ ] **Step 4: Run the tests and see them pass.** Same command, plus
  `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`.

---

## Phase B — Sources and coverage (high-stakes: cache contract, provider data)

### Task 2: Requests, parsing, migration 0060, metadata pair, cache contract

**Files:**
- Create: `backend/src/nightcrate/db/migrations/0060.weather_cache_model_meta.sql`
- Modify: `backend/src/nightcrate/services/weather.py`,
  `backend/src/nightcrate/api/weather.py` (cache functions only),
  `backend/src/nightcrate/main.py` (if the startup purge names sources)
- Create: `backend/src/nightcrate/services/forecast_coverage.py` (the
  coverage foundation)
- Test: `backend/tests/test_weather_service.py`, `backend/tests/test_weather_cache.py`,
  `backend/tests/test_forecast_coverage.py` (new)

**Interfaces:**
- Produces, in `services/weather.py`:

```python
FORECAST_DAYS = FORECAST_NIGHTS + 2          # 16 (C4)
CLOUD_REQUEST_MODELS = ("ecmwf_ifs025", "gfs_seamless", "icon_seamless", "ncep_nbm_conus")
META_DOMAINS = {"ecmwf_ifs025": "ecmwf_ifs025", "gfs_seamless": "ncep_gfs013",
                "icon_seamless": "dwd_icon", "ncep_nbm_conus": "ncep_nbm_conus"}

@dataclass(frozen=True)
class ModelSeries:                            # one model, each field independent (C6)
    cloud_total_pct: dict[datetime, float | None]
    cloud_low_pct: dict[datetime, float | None]
    cloud_mid_pct: dict[datetime, float | None]
    cloud_high_pct: dict[datetime, float | None]
    precipitation_mm: dict[datetime, float | None]
    precipitation_probability_pct: dict[datetime, float | None]
    fields_present: frozenset[str]            # Open-Meteo variable names present for this model

@dataclass(frozen=True)
class CloudModelData:
    models: dict[str, ModelSeries]            # a model whose keys were all absent is not in the dict
    raw_json: str

def parse_cloud_models(hourly: dict, models: tuple[str, ...], utc_offset_seconds: int = 0
                       ) -> dict[str, ModelSeries]: ...
async def fetch_cloud_models(latitude: float, longitude: float, timezone_str: str) -> CloudModelData: ...
async def fetch_model_meta() -> str           # raw JSON object {domain: meta.json body}; raises on any failure
```

- Produces, in `services/forecast_coverage.py` (created here; Task 3 extends
  it):

```python
DECLARED_COVERAGE: Final[dict[str, timedelta]] = {
    "ecmwf_ifs025": timedelta(days=14), "gfs_seamless": timedelta(days=15),
    "icon_seamless": timedelta(hours=162), "best_match": timedelta(days=15),
    "ncep_nbm_conus": timedelta(days=10), "cams": timedelta(days=4),
}   # starting values (§3.2); Task 11 tightens them from the availability observation

def requested_range(fetched_at: datetime, *, forecast_days: int, past_days: int) -> tuple[datetime, datetime]
    # first and last hourly stamp a GMT request asks for, from the request parameters only (C4)
def expected_until(source: str, fetched_at: datetime, last_requested_utc: datetime) -> datetime
    # min(fetched_at + DECLARED_COVERAGE[source], last_requested_utc)
def last_expected_stamp(source: str, fetched_at: datetime, last_requested_utc: datetime) -> datetime
    # expected_until floored to the whole UTC hour: the last stamp a complete series must reach
```

- Produces, in `api/weather.py`:
  - `_CachedCloud` gains `meta_raw: str | None` and `attempted_at: datetime`.
  - `ForecastData` gains `cloud_fetched_at`, `cloud_attempted_at`,
    `meta_raw` and `forecast_attempted_at`. These carry everything that
    Tasks 3–6 need for coverage, periods and run ages.
  - **Writing.** The cloud row and the `model_meta` row are written in one
    transaction with the same full-precision `fetched_at` (microseconds;
    today's writer truncates to seconds at `api/weather.py:219`). The
    metadata JSON is
    `{"cloud_sha256": <sha256 of the cloud raw_json>, "domains": {...}}`.
  - **Loading.** Both rows are read in a single `SELECT … WHERE source IN
    ('cloud_models', 'model_meta')`, so the pair always comes from one
    committed write.
  - **Pairing** needs equal `fetched_at` **and** a matching hash (C8).
    Otherwise the metadata is unavailable.

- [ ] **Step 1: Write the failing tests.**
  - `test_parse_cloud_models_fields_independent`: ECMWF has a total but no
    `cloud_cover_low_*` key. The model is still parsed, with total values and
    empty layer dicts, and `fields_present` lacks `cloud_cover_low`.
  - `test_parse_cloud_models_nbm_absent`: a response without NBM keys gives
    `"ncep_nbm_conus" not in models`.
  - `test_parse_cloud_models_unsuffixed_rejected`: a response with
    unsuffixed `cloud_cover` raises `ValueError`. The model's identity is never
    guessed.
  - `test_cloud_request_params`: `forecast_days == 16`; `models` lists the
    four models; `hourly` includes `precipitation` and
    `precipitation_probability`.
  - `test_forecast_request_days`: the main request also asks for 16 days.
  - `test_migration_0060_adds_model_meta`: on a fresh database and on a copy
    at 0059, `model_meta` inserts succeed, existing rows and ids are
    preserved, and integrity and FK checks are clean.
  - `test_model_meta_written_with_cloud_row`: the metadata's `cloud_sha256`
    equals the hash of the cloud payload. If `fetch_model_meta` fails, the
    cloud row is still written, the old metadata row is deleted in the same
    transaction, and the metadata loads as unavailable.
  - `test_meta_from_other_snapshot_not_attached`: a `model_meta` row whose
    hash names another cloud payload is ignored, even with an equal
    `fetched_at`.
  - `test_identical_payloads_pair_by_refresh`: two refreshes return identical
    cloud JSON but different metadata. A load interleaved between the two
    writes gets the metadata of the refresh whose cloud row it read, never a
    mix.
  - `test_requested_range_from_parameters`: a fetch at 23:30Z with 16 forecast
    days and 1 past day gives a last stamp of day 15, 23:00Z.
  - `test_expected_until_caps_at_request_end`: for that fetch, `best_match`
    coverage ends at the range's end, not at fetch + 15 d.
  - `test_truncated_axis_does_not_shrink_coverage`: a response whose time
    axis ends at day 9 counts as truncated against the requested range, and
    so does an empty axis.
  - `test_legacy_cloud_row_refetched_within_ttl`: a fresh-within-TTL row with
    the old field set triggers a fetch (Review Focus 1).
  - `test_truncated_model_refetched_once`: ICON's last non-null value is 20 h
    before its expected coverage. The first request refetches; a second one 10
    minutes later serves the cache.
  - `test_repair_refetch_at_most_hourly`: the limiter allows the next repair
    after 60 minutes, using `_now` monkeypatched.
  - `test_concurrent_repairs_coalesce`: two `asyncio.gather` loads of the same
    location call `fetch_cloud_models` once.
  - `test_union_axis_does_not_hide_truncation`: GFS reaches 15 d but ECMWF's
    values stop at 10 d, which counts as truncated. The current union test at
    `api/weather.py:304` would have passed it.

- [ ] **Step 2: Run them and see them fail.**
  `cd backend && uv run pytest tests/test_weather_service.py tests/test_weather_cache.py -q`

- [ ] **Step 3: Implement.**
  - **0060** rebuilds `weather_cache` exactly as 0057 does, with `'model_meta'`
    added to the source CHECK, and copies every row with its id.
  - **Truncation:** a row is current when, for each of ECMWF, GFS and ICON,
    and for each of `cloud_cover` and `precipitation`, the last non-null stamp
    reaches `last_expected_stamp(model, fetched_at, last_requested)`. The
    range comes from `requested_range` with the parameters actually sent,
    never from the response's time axis.
  - **NBM is not checked** for truncation; it is context.
  - **Main forecast:** the same rule applies to `cloud_cover`, `precipitation`,
    `precipitation_probability`, `wind_speed_10m`, `wind_gusts_10m`,
    `temperature_2m` and `dew_point_2m` against `best_match`'s coverage.
  - **The repair limiter** is a module-level `dict[(location_id, source),
    datetime]` of the last repair attempt.
  - **Coalescing** uses one `asyncio.Lock` per `(location_id, source)`.
  - **`_reaches_horizon`** is removed, along with its tests' expectations; they
    are replaced by the tests above.

- [ ] **Step 4: Keep the app working, then run the tests and see them
  pass.** The old `forecast_inputs.build_hour_inputs` reads the new
  `ModelSeries` through a small adapter that returns the old
  `(total, low, mid, high)` tuple. The adapter is removed at Task 5's
  switch-over.
  - Run the tests, then `make test-fast`.
  - Run an API smoke test: `POST /api/weather/forecast` against a seeded
    fixture returns 200 with 14 nights.

### Task 3: Declared coverage, chance periods and hourly inputs (pure)

**Files:**
- Modify: `backend/src/nightcrate/services/forecast_coverage.py` (from Task 2),
  `backend/src/nightcrate/services/forecast_inputs.py`
- Create: `backend/src/nightcrate/services/imaging_types.py` (input dataclasses only)
- Test: `backend/tests/test_forecast_coverage.py` (new), `backend/tests/test_forecast_inputs.py`

**Interfaces:**
- Consumes: `ModelSeries` and `CloudModelData` (Task 2), and `ChancePeriod`,
  `ModelHour` and `HourInput` (Task 4). Task 3 creates `imaging_types.py`
  holding only these dataclasses, and Task 4 extends it.
- Produces, in `services/forecast_coverage.py`:

```python
@dataclass(frozen=True)
class ModelMeta:
    domain: str
    init_utc: datetime
    available_utc: datetime
    temporal_resolution: timedelta
    update_interval: timedelta

def parse_model_meta(raw_json: str | None) -> dict[str, ModelMeta]        # {} on any defect; drops bad domains
def nbm_grid_position(latitude: float, longitude: float) -> Literal["inside", "edge", "outside"]
    # Lambert conformal on a sphere (R 6 371 200 m), standard parallel 25°, central meridian −95°;
    # outer grid-point centres (19.228985, −126.27699) and (54.372913, −59.042786), 2 345 × 1 597 points.
    # "outside" = more than 2 cells beyond the outer centres; "edge" = within 2 cells of them, on either
    # side; else "inside"  (C9; formulas: Snyder, Map Projections, §15)
def chance_periods(
    hour_starts_utc: Sequence[datetime], *, latitude: float, longitude: float,
    nbm_present: bool | None, nbm_meta: ModelMeta | None,
    nbm_expected_until: datetime | None, evidence_current: bool,
) -> dict[datetime, ChancePeriod]
def coarse_cloud_from(ecmwf_meta: ModelMeta | None, fetched_at: datetime) -> datetime
    # latest 00/12 UTC init ≤ meta.init_utc, + 144 h; without meta: fetched_at + 136 h  (C10)
```

- `chance_periods` rules, in order (C9):
  1. `outside` → `hourly`.
  2. `edge` or `inside`: the period is `unknown` when `nbm_present is not
     True`, when `nbm_meta is None`, or when `not evidence_current`. An `edge`
     location with NBM keys present follows rule 3 like `inside`.
  3. Otherwise, with B = `nbm_meta.init_utc + 36 h` and U =
     `nbm_meta.update_interval`, for an hour starting at H:
     - `hourly` if H + 1 h ≤ B − U;
     - `unknown` if H < B + U;
     - otherwise `block`, with bounds `[floor6(H), floor6(H) + 6 h)`
       (00/06/12/18 UTC), when its value stamp H + 1 h ≤
       `nbm_expected_until`;
     - `unknown` after that.
- `evidence_current` is true when all of these hold: neither the main
  forecast nor the cloud row is stale; the two rows were fetched within 1 h of
  each other; and the metadata's hash matches the cloud row (C8, C9).
- Adds `build_hours` beside the old `build_hour_inputs`. The old builder
  keeps feeding the old evaluator until Task 5 deletes it, so the app works
  between tasks.

```python
def build_hours(
    hourly: list[HourlyWeather], cloud_models: CloudModelData | None,
    moon_altitudes: dict[datetime, float | None], start_utc: datetime, end_utc: datetime, *,
    expected: Mapping[str, datetime],            # model → expected_until; "best_match" for the main forecast
    periods: Mapping[datetime, ChancePeriod],
) -> list[HourInput]
```

  - Each `HourInput.models[m]` is a `ModelHour`. Its `cloud_expected` is
    `start ≤ expected[m]`, and its `amount_expected` is
    `start + 1 h ≤ expected[m]`.
  - When nothing has been cached, the caller passes `expected` anchored at the
    attempt time (C4).
  - `best_match` cloud comes from the main forecast. The main forecast's
    precipitation and wind fields do not depend on coverage: missing is
    unknown.

- [ ] **Step 1: Write the failing tests.**
  - `test_nbm_grid_footprint`: the spec's 22 probe points (C9).
    - Inside: Phoenix, Toronto, Vancouver, Edmonton, Monterrey, Halifax,
      Seattle and Miami.
    - Outside: Anchorage, Honolulu, San Juan, Mexico City, Bermuda, London,
      St John's (47, −52.7), (60.5, −100), (59, −100), (45, −49), (14, −90),
      (50, −141), (55, −130) and (57, −135).
  - `test_grid_edges`: for each of the four edges, points 0.4 cell and
    1.9 cells beyond the outer centres are `edge`, a point 2.1 cells beyond is
    `outside`, and a point 2.1 cells inside is `inside`.
  - `test_outside_grid_hourly`: London with `nbm_present=None` gives every
    period `hourly`.
  - `test_grid_without_nbm_keys_is_unknown` (Review Focus 4): Phoenix with
    `nbm_present=False` gives every period `unknown`.
  - `test_nbm_regime_boundary`: init 05:00Z, U = 1 h, so B = next day
    17:00Z.
    - The hour starting 15:00Z is `hourly`.
    - 16:00Z and 17:00Z are `unknown`.
    - 18:00Z is a `block` [18:00Z, 00:00Z).
    - An hour past `nbm_expected_until` is `unknown`.
  - `test_block_bounds_preceding_hour`: the hour starting 23:00Z falls in
    block [18:00Z, 00:00Z), and the hour starting 00:00Z falls in
    [00:00Z, 06:00Z).
  - `test_periods_unknown_when_generations_differ` and
    `test_periods_unknown_when_stale` (Review Focus 5).
  - `test_coarse_cloud_from`: with the 18z init, the boundary is
    12z + 144 h; without metadata it is fetch + 136 h.
  - `test_parse_model_meta_rejects_garbage`: missing keys, or non-numeric
    times, give `{}` for that domain.
  - In `test_forecast_inputs.py` (testing `build_hours`):
    - `test_model_hours_carry_expected_flags`: ICON expected until 18:30Z
      gives the hour starting 18:00Z `cloud_expected` True and
      `amount_expected` False.
    - `test_missing_total_not_rebuilt`: a total of `None` with layers present
      gives `cloud_total_pct is None`.

- [ ] **Step 2: Run them and see them fail.**
  `cd backend && uv run pytest tests/test_forecast_coverage.py tests/test_forecast_inputs.py -q`
- [ ] **Step 3: Implement.** Pure functions only; there is no I/O in either
  module.
- [ ] **Step 4: Run the tests and see them pass**, plus ruff.

---

## Phase C — Evaluator (high-stakes: decision logic)

Tasks 4 and 5 build the new evaluator beside the old one. `api/weather.py`
keeps calling the old `evaluate_night` until Task 5's last step switches it
over (Codex, round 2). Guarantee tests start in Task 4.

### Task 4: Types, hourly checks, session kernel, model status, all-night combiner

**Files:**
- Create: `backend/src/nightcrate/services/imaging_types.py`,
  `imaging_hours.py`, `imaging_session.py`
- Modify: `backend/src/nightcrate/services/imaging_verdict.py` (the
  combiners only, for now)
- Test: `backend/tests/test_imaging_hours.py`, `test_imaging_session.py`,
  `test_imaging_guarantee.py` (all new)

**Interfaces:**
- Produces, in `imaging_types.py` (the shared contracts; no imports from the
  other evaluator modules):

```python
CheckState = Literal["pass", "fail", "unknown", "not_counted"]
HourState = Literal["clear", "not_clear", "unknown", "outside"]
Verdict = Literal["go", "uncertain", "no", "not_enough_data", "night_over"]
ModelStatus = Literal["go", "no", "unresolved", "not_expected"]
WindowStatus = Literal["established", "impossible", "unresolved"]

@dataclass(frozen=True)
class ChancePeriod:
    kind: Literal["hourly", "block", "unknown"]
    start_utc: datetime | None = None      # block bounds only
    end_utc: datetime | None = None

@dataclass(frozen=True)
class ModelHour:
    cloud_total_pct: float | None
    cloud_layers_pct: tuple[float | None, float | None, float | None]
    precip_mm: float | None
    cloud_expected: bool
    amount_expected: bool

@dataclass(frozen=True)
class HourInput:
    start_utc: datetime
    models: Mapping[str, ModelHour]         # "best_match", "ecmwf_ifs025", "gfs_seamless", "icon_seamless"
    precip_probability_pct: float | None
    chance_period: ChancePeriod
    precip_mm: float | None
    wind_kmh: float | None
    gust_kmh: float | None
    temperature_c: float | None
    dew_point_c: float | None
    moon_altitude_deg: float | None

@dataclass(frozen=True)
class NightControls:
    gear_out_utc: datetime | None = None
    gear_in_utc: datetime | None = None
    imaging_from_utc: datetime | None = None
    imaging_until_utc: datetime | None = None

@dataclass(frozen=True)
class NightInput:
    sunset_utc: datetime | None
    sunrise_utc: datetime | None
    noon_start_utc: datetime
    noon_end_utc: datetime
    dark_intervals: list[tuple[datetime, datetime]]
    hours: list[HourInput]
    now_utc: datetime
    controls: NightControls
    primary_model: str                      # "ecmwf_ifs025"
    fallback_model: str                     # "best_match"
    comparison_models: tuple[str, ...]      # ("gfs_seamless", "icon_seamless")
    stale_minutes: Mapping[str, int | None] # "forecast", "cloud_models"
```

- Also in `imaging_types.py`:
  - `Reason`, extended with `model: str | None`, `models: dict[str,
    ModelStatus] | None`, `period: ChancePeriod | None` and `missing_hours:
    float | None`;
  - `CoverageNote(model, expected_until_utc | None, status: ModelStatus |
    Literal["not_used"])`;
  - `HourResult` and `NightResult`, with the fields Task 5 lists.
- Produces, in `imaging_hours.py`:

```python
def chance_limit(period: ChancePeriod, rules: ImagingRules) -> float
    # hourly → per-hour; block → per-period; unknown → min of the two  (§4.3)
def precipitation_checks(hour: HourInput, rules: ImagingRules) -> dict[str, CheckState]
    # keys "chance", "amount", and "amount:<model>" for each expected extra model when rules.rain_forecasts == "any_model"
def conditions(hour: HourInput, rules: ImagingRules, cloud_model: str) -> dict[str, CheckState]
    # display conditions: cloud (model total only), rain (aggregate of precipitation_checks), wind, dew, moon
def hour_state(checks: Mapping[str, CheckState], *, dark_minutes: float) -> HourState
```

- Produces, in `imaging_session.py`:

```python
@dataclass(frozen=True)
class Segment:
    start: datetime
    end: datetime
    hour_index: int

@dataclass(frozen=True)
class SessionPass:
    passed: bool
    reason: Reason
    clear_minutes: float
    longest_gap: tuple[datetime, datetime] | None
    longest_clear: tuple[datetime, datetime] | None

def session_pass(states: Sequence[HourState], segments: Sequence[Segment], rules: ImagingRules,
                 dark_minutes: float, *, optimistic: bool) -> SessionPass
def model_status(states: Sequence[HourState], segments: Sequence[Segment], rules: ImagingRules,
                 dark_minutes: float, *, expected_missing: bool) -> tuple[ModelStatus, SessionPass, SessionPass]
    # pessimistic pass → go; optimistic fail → no; else unresolved if expected_missing else not_expected (§5.2, C4)
```

- Produces, in `imaging_verdict.py`:

```python
def combine_all_night(primary: ModelStatus, comparisons: Mapping[str, ModelStatus]) -> Verdict
```

  This is §5.6's table. `not_expected` comparisons are omitted. A `primary` of
  `unresolved` gives `not_enough_data`. A `primary` of `not_expected` is a
  `ValueError` (the caller falls back first).

- [ ] **Step 1: Write the failing tests.**
  - In `test_imaging_hours.py`:
    - The cloud cases of §9 ("Cloud"):
      - `test_total_4_layers_21_clear`;
      - `test_total_0_layers_missing_clear`;
      - `test_total_at_limit_clear`;
      - `test_total_missing_layers_present_unknown`.
    - The precipitation cases of §9:
      - `test_unknown_period_uses_lower_limit`, with limits 30/10 and a value
        of 20: fail;
      - `test_hourly_period_uses_hour_limit`: pass;
      - `test_equal_limits_period_irrelevant`;
      - `test_amount_005_threshold_0_fails`;
      - `test_amount_equal_threshold_passes` (0.1 / 0.1);
      - `test_chance_only_from_main` (main 5% with any_model: no chance check
        on the extra models).
    - `test_extra_amount_omitted_outside_coverage`: ICON
      `amount_expected=False` gives no `amount:icon_seamless` key.
  - In `test_imaging_session.py`:
    - `test_share_at_least`;
    - `test_runs_do_not_bridge_non_dark`;
    - `test_model_status_table`: one case per row of §5.2's table, including
      an unresolved case with only not-covered unknowns → `not_expected`.
  - In `test_imaging_guarantee.py` (C17):
    - `test_hour_checks_monotone`: exhaustive over (known pass, known fail,
      unknown) for each check, with every single erasure. A fail never becomes
      a pass, and an hour state never moves from `not_clear` or `unknown` to
      `clear`.
    - `test_session_kernel_8h_monotone`: all 6 561 eight-hour sequences ×
      every single erasure, at share ≥ 75%, min hours 2, with the interruption
      limit both off and at 1 h.
      - `model_status` never moves from {no, unresolved} to go.
      - Go only moves to {go, unresolved}, and no only to {no, unresolved}.
    - `test_all_night_counts_reduction`: 91 125 count classes over 3 models,
      with the interruption limit off.
      - A class's status is computed once.
      - Every single erasure edge is checked against the combined verdict.
    - `test_all_night_combiner_monotone`: every tuple of statuses for the
      primary and 2 comparisons, including `not_expected` comparisons, with
      every degradation (go→unresolved, no→unresolved): never non-Go → Go.

- [ ] **Step 2: Run them and see them fail.**
  `cd backend && uv run pytest tests/test_imaging_hours.py tests/test_imaging_session.py tests/test_imaging_guarantee.py -q`
- [ ] **Step 3: Implement.**
  - Move the run, longest and two-pass logic out of `imaging_verdict.py` into
    `imaging_session.py` unchanged, except that the share comparison stays ≥
    (Task 1).
  - The cloud check reads `models[m].cloud_total_pct` only.
- [ ] **Step 4: Run the tests and see them pass.** Then run
  `time uv run pytest tests/test_imaging_guarantee.py -q`. The
  whole file must finish in under 40 s on one core; record the time in the
  task report.

### Task 5: Shared window, precipitation, vetoes, precedence, freshness, evidence; switch-over

**Files:**
- Modify: `backend/src/nightcrate/services/imaging_verdict.py` (the new
  `evaluate_night`), `imaging_session.py` (shared window), `imaging_types.py`
  (results)
- Modify: `backend/src/nightcrate/api/weather.py`, to call the new evaluator
  with today's response fields; Task 6 then changes the contract. Remove
  `_primary_model` and `effective_cloud_pct`.
- Test: `backend/tests/test_imaging_verdict.py` (rewritten around the §9
  cases), `test_imaging_guarantee.py`

**Interfaces:**
- Produces, in `imaging_session.py`:

```python
def joint_states(states: Mapping[str, Sequence[HourState]], expected: Mapping[str, Sequence[bool]]) -> list[HourState]
    # per hour: fail if any expected model is not_clear; else unknown if any expected unknown; else clear (§5.5.2)
def shared_window(joint: Sequence[HourState], segments: Sequence[Segment], required_minutes: float
                  ) -> tuple[WindowStatus, tuple[datetime, datetime] | None]
    # established: a pessimistic run ≥ R exists (earliest); impossible: none optimistically; else unresolved
```

- Produces, in `imaging_verdict.py`:

```python
def combine_short_session(primary: ModelStatus, window: WindowStatus,
                          comparisons: Mapping[str, ModelStatus]) -> Verdict   # §5.5 tables
def apply_precedence(cloud: Verdict, *, precipitation_veto: bool, precipitation_unknown: bool,
                     stale: bool) -> Verdict
    # veto → no; unknown with cloud in {go, uncertain} → not_enough_data;
    # stale with result in {go, uncertain, not_enough_data} → not_enough_data; no stays no  (§5.7, §5.8, C3)
def evaluate_night(night: NightInput, rules: ImagingRules) -> NightResult
```

- `NightResult` fields:
  - `verdict`;
  - `reasons` (non-empty; `[0]` is the headline, the rest are the other
    causes);
  - `advisory: Reason | None`;
  - `clear_minutes`, `dark_minutes`, `unknown_minutes`;
  - `longest_gap`, `longest_clear_run`, `window`;
  - `exposure: tuple | None`, `imaging: tuple | None`;
  - `evaluated_from_utc`;
  - `primary_model`, `fallback: bool`;
  - `model_statuses: dict[str, ModelStatus]`;
  - `coverage: list[CoverageNote]`;
  - `requirements`, `hours`.
- `HourResult` fields:
  - `start_utc`, `elapsed`, `excluded`;
  - `dark_minutes`, `exposure_minutes`;
  - `checks`, `conditions`;
  - `state` (displayed) and `session_state` (C11);
  - `model_states` (expected models only);
  - `disagrees`;
  - `cloud_pct: dict[str, float | None]`;
  - `expected: dict[str, tuple[bool, bool]]`, giving (cloud expected, amount
    expected) per model. Their negation is what the UI mutes as "beyond
    declared coverage" (C14: by field, not by model);
  - `chance_limit_pct`;
  - `dew_spread_c`.
- New reason codes:
  - `rain` (chance; carries `period`);
  - `rain_amount`;
  - `rain_model_amount` (`model`);
  - `rain_missing` (`missing_hours`);
  - `model_incomplete` (`model`, missing hours);
  - `no_shared_window`;
  - `model_not_used` (coverage qualifier, `model`, `end_utc` = coverage end);
  - `fallback` (best_match cloud, ECMWF beyond its reach);
  - `layer_advisory`.

  `stale` keeps its code. When stale, it becomes `reasons[0]` and the
  original headline follows.

**Algorithm** (the order is decided here; everything else follows from the
signatures and the spec):

```text
1. Intervals (keep today's polar rule, imaging_verdict.py:485-490: with no sunset or sunrise,
   the natural bound is the noon boundary and no gear minutes are added):
   exposure (night_off) = [gear_out or sunset − gear min, gear_in or sunrise + gear min];
   imaging = the dark part of [imaging_from or exposure start / darkness start,
             imaging_until or exposure end / darkness end].
   Under hours_lost there is no exposure; imaging = the dark part of
   [imaging_from, imaging_until] or of the darkness. Both are clipped to now.
2. Early exits (§5.4, C2):
   night over (darkness ended, or the imaging interval ended) → never dark → no dark time.
3. Per hour: conditions; precipitation checks shared by all models; session state per model
   (precipitation counted only under hours_lost, C11); displayed state counts precipitation
   inside exposure or imaging.
4. Primary: model_status(primary).
   not_expected → model_status(fallback) with no comparisons (fallback=True).
   An unresolved primary, or a fallback that is unresolved or itself not_expected, sets the
   cloud-side verdict to not_enough_data. It never returns early: a known precipitation veto
   in step 6 still makes the night No (Codex, round 3).
5. Cloud verdict:
   all night → combine_all_night;
   short session → joint_states over the models expected per hour → shared_window
   → combine_short_session (when the primary is no, each comparison is judged on its own status).
6. Precipitation under night_off over the remaining exposure:
   a known failure → veto (reason rain / rain_amount / rain_model_amount);
   otherwise an unknown → precipitation_unknown.
7. apply_precedence; then add every other independent cause to reasons
   (other failing rules, disagreement attribution, coverage qualifiers, missing hours).
8. disagrees per hour = verdict is uncertain and an expected comparison model's known
   session state differs from the primary's.
9. advisory (C13): primary is ECMWF, its total passes, an estimated layer is over the limit
   in remaining dark hours → Reason(layer_advisory) with the clipped range and the peak.
```

- [ ] **Step 1: Write the failing tests.** Every row of §9's "Coverage and
  comparison" and "Precipitation chance and amount" tables gets a test named
  after its case, with the spec's expected verdict and reason fields asserted
  exactly, plus these:
  - `test_ecmwf_missing_decisive_hour_not_enough_data`: no fallback (C13).
  - `test_whole_cloud_response_missing_inside_coverage`: Not enough data, not
    a fallback (C4).
  - `test_fallback_not_expected_is_not_enough_data`.
  - `test_night_off_unknown_rain_keeps_cloud_no` (C11):
    - a cloud No with one unknown chance hour stays No;
    - a cloud Uncertain with one unknown chance hour becomes Not enough data.
  - `test_precip_veto_with_disagreement_context`: No; the reasons include
    the models' disagreement.
  - `test_rain_before_now_ignored`.
  - `test_stale_no_keeps_no_with_age` and `test_stale_uncertain_is_not_enough_data`.
  - `test_reasons_primary_plus_blockers`: precipitation 11% over a 6-hour
    period with cloud leaving 2.3 of 10.3 h clear. The first reason is
    `rain`, with the period and the overlap; the second is `clear_fraction`.
  - `test_disagrees_only_on_uncertain`: a Go night with differing ECMWF/GFS
    hour states has no `disagrees`.
  - `test_advisory_shown_and_suppressed`: shown in the right case; suppressed
    when the total fails, outside counted time, after the night is over, and
    on a fallback night.
  - `test_imaging_inside_exposure`: imaging 20–01 inside exposure 17–07.
    Cloud after 01:00 does not count; precipitation at 03:00 vetoes.
  - `test_gear_in_midnight_ignores_later_shower`.
  - `test_gear_out_23_starts_both_intervals`.
  - `test_imaging_until_hours_lost_no_exposure`.
  - `test_polar_intervals`: continuous darkness (no sunset or sunrise); twilight
    with no sunset; split darkness; and an expired imaging stop while the
    exposure continues (→ Night over, C2).
  - `test_unresolved_primary_with_precip_veto_is_no`.
  - `test_short_session_guarantee_exhaustive` in `test_imaging_guarantee.py`
    (C17):
    1. Run 3 models × 3 dark hours, R = 2 h, through `evaluate_night`, once
       per assignment (19 683).
    2. Check every single erasure edge (118 098) against the result table:
       never non-Go → Go.
  - `test_end_to_end_seeded`: `random.Random(seed)` for seeds 1–4, 2 500 cases
    each. Each case builds a raw Open-Meteo-shaped payload and runs the full
    path: `parse_cloud_models` / `parse_hourly` → `chance_periods` →
    `build_hours` → `evaluate_night`.
    - It erases one raw value in the payload (a cloud total, an amount, a
      chance, a wind value, a whole model's keys, NBM keys, or the metadata),
      then reruns the whole path and asserts never non-Go → Go.
    - The cases vary: policy, mode and unequal limits; coverage ends, fallback,
      split darkness and 23- or 25-hour nights; stale flags.
    - **Sanity:** before erasure, each seed's sample must contain at least
      15 % Go, 15 % No and 5 % Uncertain. At least half the erasures must hit
      a value that the night's evaluation counts. Otherwise the test fails as
      vacuous.
  - The existing tests in `test_imaging_verdict.py` stay, rewritten for the new
    inputs, except where §4.2's cloud rule (total-only) or §5 deliberately
    changes their outcome. Each such change is named in the task report.

- [ ] **Step 2: Run them and see them fail.**
  `cd backend && uv run pytest tests/test_imaging_verdict.py tests/test_imaging_guarantee.py -q`
- [ ] **Step 3: Implement** the algorithm above. Then switch
  `api/weather.py`:
  - pass the new inputs (`build_hours` from Task 3, and the Task 2 cache
    data);
  - delete the old `build_hour_inputs`, its adapter and the old
    `HourInput`;
  - build `stale_minutes` per source by C7;
  - delete `_primary_model`;
  - keep the **current response contract**, mapping the new results into it:
    - `reason` ← `reasons[0]`;
    - `model_verdicts` ← the statuses (`unresolved` and `not_expected` →
      `not_enough_data`);
    - `gear_out` ← the exposure, or the natural gear interval;
    - `evaluated_end` ← the imaging interval's end when it is capped;
    - `effective_cloud_pct` ← `cloud_pct`.

    Task 6 changes the contract. The frontend therefore keeps working at this
    boundary.
- [ ] **Step 4: Run the tests and see them pass.** Run the whole backend
  suite once (`make test-fast`), the API smoke test from Task 2, and
  `npm run build` (no frontend change expected). The guarantee file must still
  finish under 60 s on one core; record the time.

---

## Phase D — API (high-stakes: contract)

### Task 6: Per-night controls, response contract, totals, methodology

**Files:**
- Modify: `backend/src/nightcrate/api/weather_models.py`, `backend/src/nightcrate/api/weather.py`
- Test: `backend/tests/test_weather_api.py`

**Interfaces:**
- Produces, in `api/weather_models.py`:

```python
class NightControlsRequest(BaseModel):
    gear_out: AwareDatetime | None = None
    gear_in: AwareDatetime | None = None
    imaging_from: AwareDatetime | None = None
    imaging_until: AwareDatetime | None = None

class ForecastRequest(BaseModel):
    location_id: int
    rules: ImagingRules | None = None
    night_controls: dict[str, NightControlsRequest] = Field(default_factory=dict)  # key "YYYY-MM-DD"; replaces imaging_until

class ChancePeriodResponse(BaseModel):
    kind: Literal["hourly", "block", "unknown"]
    start: str | None; end: str | None; start_utc: datetime | None; end_utc: datetime | None

class ReasonResponse(BaseModel):          # added fields
    start_utc: datetime | None; end_utc: datetime | None
    model: str | None; models: dict[str, ModelStatus] | None
    period: ChancePeriodResponse | None; missing_hours: float | None

class CoverageResponse(BaseModel):
    model: str; status: Literal["go", "no", "unresolved", "not_expected", "not_used"]
    expected_until: str | None; expected_until_utc: datetime | None   # only when inside the night

class IntervalResponse(BaseModel):
    start: str; end: str; start_utc: datetime; end_utc: datetime
```

- `NightResponse` changes:
  - `reason` stays (the headline); added `other_reasons:
    list[ReasonResponse]` and `advisory: ReasonResponse | None`.
  - `model_verdicts` becomes `model_statuses: dict[str, ModelStatus]`;
    `primary_model: str`; `coverage: list[CoverageResponse]`.
  - `exposure: IntervalResponse | None`, `imaging: IntervalResponse | None`;
    `imaging_until` becomes `controls: NightControlsRequest` (the values in
    effect, echoed back).
  - `cloud_coarse_from` and `cloud_coarse_from_utc` (approximate, C10).
  - Every existing boundary gains a `*_utc` twin (C14): `dark_intervals` and
    `darkness_intervals` (via `IntervalResponse`), the window, the longest
    gap and `evaluated_from`.
  - `extremes` gains `precip_missing_hours: int`, `precip_sum_start` and
    `precip_sum_end` (the contributing hour bins, C12).
- `HourResponse` changes:
  - `gear_out_minutes` becomes `exposure_minutes`;
  - added `session_state` and `disagrees`;
  - `effective_cloud_pct` becomes `cloud_pct`;
  - added `expected: dict[str, ExpectedFieldsResponse]`, where
    `ExpectedFieldsResponse` has `cloud: bool` and `amount: bool`, and
    `model_precip_mm: dict[str, float | None]`,
    `chance_period: ChancePeriodResponse`, `chance_limit_pct` and
    `transparency_tier: Literal["primary", "fallback", "degraded"] | None`.
- `ForecastResponse` changes:
  - added `evaluated_at: datetime` (C14);
  - `ignored_imaging_until` becomes `ignored_controls: list[str]`;
  - added `run_age_minutes: dict[str, int | None]`, approximate and from the
    metadata.
- Validation, all 422:
  - a timestamp outside its noon-to-noon night;
  - `gear_out >= gear_in`;
  - `imaging_from >= imaging_until`;
  - under `night_off`, an imaging bound outside the effective exposure.
- Controls for a date not returned, or inapplicable under the policy (gear
  controls under `hours_lost`), are ignored and listed in
  `ignored_controls`.

- [ ] **Step 1: Write the failing tests.** Every row of §9's "Time,
  freshness, display" table that touches the API gets a test, plus these:
  - `test_controls_validation_422`: four cases, one per rule above.
  - `test_inapplicable_controls_ignored_and_reported` (Review Focus 3).
  - `test_fractional_offset_alignment`: Asia/Kolkata (+5:30) and
    Asia/Kathmandu (+5:45). Hour `time` labels end in `:30` and `:45`;
    `start_utc` is on the whole hour; durations agree.
  - `test_fractional_dst_night`: Australia/Lord_Howe (+10:30 ↔ +11:00). The
    night's hours carry distinct `start_utc` values and consistent durations.
  - `test_dst_23_and_25_hour_nights`.
  - `test_totals_incomplete`: two missing hours give
    `precip_missing_hours == 2`, the known sum, and the bin range.
  - `test_trace_amount_not_zero_in_extremes`: 0.05 mm is kept as 0.05; the
    formatting is in Task 7.
  - `test_methodology_mentions_total_only_and_periods`.
  - `test_evaluated_at_is_now`.
  - `test_resolution_indicator_fields`.
  - `test_coverage_line_fields`: ICON's coverage ends inside the night →
    `CoverageResponse(model="icon_seamless", status="not_expected",
    expected_until=…)`.
- [ ] **Step 2: Run them and see them fail.** `cd backend && uv run pytest tests/test_weather_api.py -q`
- [ ] **Step 3: Implement.** Rewrite `METHODOLOGY` per §8: the total-only
  cloud rule and its reason, the chance source and period, the two-limit
  rule, coverage and "all expected models", freshness, and the controls.
  Rewrite `_extremes` per C12.
- [ ] **Step 4: Run the tests and see them pass**, then the full backend
  checks:
  `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run bandit -r src/ -q && uv run pytest -n auto -q`.

---

## Phase E — Frontend (high-stakes: decision display; rendered checks by Claude)

There is no frontend test runner. Each task ends with `npm run build` (from
`frontend/`) and Claude's rendered checks R11–R20 below.

### Task 7: Client contract, formatters, reasons, query policy, "not current"

**Tasks 6 and 7 form one integration unit** (Codex, round 4). Task 6 changes
the API contract that today's frontend reads, so the app only works again
once Task 7 lands. Claude reviews each task's diff on its own, but stages
Task 6 only together with Task 7, after a real-endpoint run (R10 of the
v0.41.9 plan) with no interception.

**Files:** `frontend/src/api/weather.ts`, `frontend/src/lib/weatherVerdict.ts`,
`frontend/src/components/weather/VerdictPill.tsx`, `frontend/src/pages/WeatherPage.tsx`,
`frontend/src/components/calculators/TonightCalc.tsx`. Also every other
consumer of a renamed field (`NightDetailPanel.tsx`, `HourStrip.tsx`,
`WeekList.tsx`, `NightCard.tsx`), changed mechanically only.

- **Types** mirror Task 6 exactly.
- **This task is atomic for the contract.** Every consumer of a renamed or
  removed field is updated here, mechanically (e.g. `effective_cloud_pct` →
  `cloud_pct`, `model_verdicts` → `model_statuses`, `imaging_until` →
  `controls`), so `npm run build` passes at the end of this task. Tasks 8–10
  add the new displays (Codex, round 3).
- `forecastQueryOptions(locationId, draftRules?, nightControls?)` replaces
  `imagingUntil`.
  - `refetchInterval: 60_000` and `refetchOnWindowFocus: true`.
  - Background refetch stays off for hidden browser tabs.
  - Weather is kept mounted while hidden (`AppShell.tsx:486`). Its query
    therefore sets `enabled` and `refetchInterval` only while its route is
    the active one (`useLocation`), and Tonight does the same.
  - On focus or visibility return, the query refetches and the "not current"
    age is rechecked at once.
  - Weather and Tonight use the same key when both use saved rules and no
    controls (C15).
- `formatAmount(mm, units)` replaces `formatRain`:
  - `null` → "—";
  - it converts first, then rounds at the display precision (0.1 mm, or
    0.01 in);
  - a positive value that rounds to 0 prints as "<0.1 mm" or "<0.01 in";
    0.1 mm in imperial is therefore "<0.01 in", never "0.00 in" (Codex, round
    3).

  `NightDetailPanel`'s `rainCell` uses the same rule.
- `formatTotal(extremes, units)` gives "Forecast-hour sum ≥ 0.3 mm; 2 hours
  missing", or "0.3 mm" when complete (C12).
- `reasonText` covers every new code:
  - `rain`: "Precipitation over your limit 21:00–23:00; peak reported chance
    20%, limit 10%". For a block it names the period ("for the 6-hour period
    17:00–23:00, overlapping your gear-out by 54 min"); for an unknown period
    it adds "period unknown".
  - `rain_model_amount`: "ICON: 0.7 mm/h 20:00–22:00".
  - `model_not_used`: "ICON not used — covers only to 23:00".
  - `fallback`: "best_match cloud — ECMWF beyond its reach".
  - `model_incomplete`: "ICON unavailable 22:00–00:00 — refresh later".
  - `no_shared_window`: "No shared clear window".
  - `rain_missing`: "Precipitation not forecast 22:00–23:00".
  - `stale`: "forecast N h old, refresh failed".
- `reasonLine(night)`: the headline, then the other reasons joined with "; ".
- **"Not current" (C15).** A `useNow(15_000)` hook drives it.
  - A result is not current when `now − evaluated_at > 3 min`, or the last
    refetch errored.
  - `VerdictPill` takes `notCurrent`. When set, it renders the text "Last
    result: Go — not current" in the neutral style.
  - Weather shows "Not current — last evaluated hh:mm" above the list; Tonight
    shows it on its card.
- The rendered checks for this task are R11–R13.

### Task 8: Night details

**Files:** `frontend/src/components/weather/NightDetailPanel.tsx`

- **The header controls follow the policy** (§4.5).
  - `night_off`: "Gear out at" and "Gear in at", plus the checkbox "Imaging
    times differ from equipment times", which reveals "Imaging from" and
    "Imaging until".
  - `hours_lost`: "Imaging from" and "Imaging until".
  - The options are the night's hour starts, plus "Natural" (the default).
    When gear-in is before the end of darkness, the control's label says the
    gear is indoors.
  - The state lives in `WeatherPage` as `Record<date, NightControls>`.
- **Checklist.**
  - The models line uses "?" when the models disagree (§6.3).
  - "Clear dark hours … (ECMWF)" names `primary_model` when the night is
    Uncertain or Not enough data.
  - The precipitation line uses the Task 7 wording and `formatTotal`.
  - The advisory line, when present, has a neutral mark ("–") and the C13
    text.
  - The transparency row shows its tier when it is not `primary` (e.g. "fair
    — humidity-based").
- **The coverage line** sits at the top of the model section: one entry per
  model, with its status and its coverage end inside the night.
- **Rows.**
  - "Cloud % (ECMWF total)", or "Cloud % (Open-Meteo default)" on a fallback
    night.
  - Per-model total rows (GFS, ICON) carry their status in the summary column.
  - Low, mid and high cloud move to "For information". For ECMWF they are
    labelled "humidity estimate (Open-Meteo) — not counted".
  - The chance row draws a `block` as one cell spanning its hours, and marks
    an unknown period with a dashed outline and the text "period?". It judges
    each hour against `chance_limit_pct`.
  - The amount row judges each hour against `rain_amount_threshold_mm`.
  - When `rain_forecasts == "any_model"`, there are amount rows for ECMWF, GFS
    and ICON.
  - A value whose field is not expected (`expected[m].cloud` for cloud rows,
    `.amount` for amount rows) is muted, with the tooltip "beyond declared
    coverage — not counted".
  - The resolution note appears under the cloud row whenever any dark hour of
    the night is at or after `cloud_coarse_from`. It reads "Cloud data may be
    6-hourly from about hh:mm", or "Cloud data may be 6-hourly all night".
- The rendered checks are R14–R16.

### Task 9: Rules editor and rules bar

**Files:** `frontend/src/components/weather/RulesEditor.tsx`, `RulesBar.tsx`

- **Editor.**
  - The share field reads "Clear for at least (% of dark time)", 1–100.
  - Cloud caption: "Uses the model's total cloud cover."
  - "Maximum chance — per hour (%)" and "Maximum chance — per multi-hour
    period (%)" carry the §4.3 help text, plus the preset note for "Left out
    all night".
  - "Count precipitation above (mm/h)" is shown in inches per hour for
    imperial, and converted.
  - "Precipitation forecasts to check" is a select (Main forecast / Any
    model) in "Cloud and precipitation", with §4.3's help text.
  - `validate` mirrors Task 1's bounds.
- **Bar.**
  - "Clear = cloud" becomes "Cloud limit".
  - "more than" becomes "at least".
  - Precipitation shows both limits when they differ, adds "· any model" when
    that is set, and shows the threshold when it is above 0.
- **F2.** The gap label, the rules bar and the `gap` reason say "Longest
  interruption" (e.g. "Not clear for 3 h from 01:00 — longest interruption
  allowed is 2 h").
- The rendered check is R17.

### Task 10: Week rows, Tonight card, fractional offsets

**Files:** `frontend/src/components/weather/WeekList.tsx`, `NightCard.tsx`,
`HourStrip.tsx` (data only), `frontend/src/lib/weatherVerdict.ts` (`buildClock`)

- Week rows and the Tonight card use `reasonLine`.
- The Tonight card reads "0 h clear of 7.2 remaining". "Night over" never
  states that exposure has ended (C2, §6.4).
- The `models` cell's condition becomes `hour.disagrees`. **Nothing else in
  the strip changes** (C1).
- **Week rows** carry the §6.1 resolution indicator in the row's summary text
  ("6-hourly cloud from ~hh:mm"), outside the strip.
- **Fractional offsets and DST** (C16).
  - Cells keep today's column geometry. A cell is identified by its
    `start_utc`, never by its `HH:MM`, so repeated local times stay distinct;
    their tooltips show the offset ("01:30 +10:30").
  - The darkness band maps each crossing time through the cell that contains
    it: the cell's position, plus the fraction of that cell's UTC hour. It
    never uses a linear wall-clock axis, so Lord Howe's half-hour fall-back
    (01:00, 01:30, 02:30) and a +5:45 zone line up.
  - A non-zero minute shows as "20:30" on the first and last labels, and as
    "20" elsewhere.
  - Whole-hour zones render exactly as before.
- The rendered checks are R18–R20.

---

## Phase F — Documentation and observation

### Task 11: Docs, release notes, coverage constants (Claude)

- **Availability observation** (§3.2 rule 3; not accuracy work).
  - Run the read-only scratchpad probe hourly for 24 h, at the public test
    location, London and Sydney.
  - Record the minimum reach after fetch for each model and field.
  - Set each `DECLARED_COVERAGE` value to that minimum minus 6 h, rounded down
    to the hour, never above the spec's starting value.
  - Measured on 2026-10-17 (one sample): ECMWF cloud 343 h and precipitation
    341 h; GFS 376 h; ICON 173 h; NBM 257 h; best_match 376 h.
- **Docs.**
  - `docs/weather-algorithms.md` §1.1, §4 and §5 per spec §8; replace the
    precipitation limitation.
  - `docs/development-decisions.md` (Weather):
    - coverage;
    - periods and the NBM grid footprint;
    - session vs displayed state;
    - precedence;
    - client "not current";
    - the frozen strip.
  - The v0.41.9 spec: mark §3.1, §4.3 and §5.3 as superseded by the revisions
    spec.
  - `README.md`, if it mentions sources or rules.
  - `PLAN.md`: the scope line.
- **History note** (§8): add the ERA5/IFS caveat to the comment above
  `CLOUD_PRIMARY_MODEL` and to `docs/archive/imaging-quality-model.md` §7.
- **Release notes:**
  - the ≥ share; saved weather rules are reset (F1; unreleased table);
  - the total-only cloud;
  - the new precipitation settings, with migrated locations kept on Main
    forecast;
  - the presets;
  - "Night over" unchanged.
- **Vault:** "Product decisions" (F1, F2 and the C-list's product-facing
  items) and "Questions and observations" (the coverage observation).

---

## Rendered checks (Claude, after each frontend task)

These use Playwright against `make dev` with a disposable workspace.
Intercepted POST responses supply cases the sky won't give. Every check
compares the hour strip with a reference screenshot taken before Task 7 (C1).

- **R11. Strip frozen.** For the same fixture, cell geometry, icon sizes and
  colours are identical to the pre-change screenshot, at desktop and 820 px.
- **R12. Not current.** Use `page.clock` to move 4 minutes past `evaluated_at`
  with requests stalled. The pills read "Last result: … — not current". A
  focus event triggers a refetch.
- **R13. Minute refresh.** Exactly one forecast request per 60 s for the
  active route, with Weather and Tonight both mounted, including when
  Weather's key differs (a draft or controls set). There are none while the
  browser tab is hidden, and one immediately on focus return.
- **R14. Controls.** `night_off` shows gear controls and the checkbox;
  switching the draft to `hours_lost` swaps them. Setting "Gear out at 23:00"
  re-evaluates the row and the panel identically.
- **R15. Spans and marks.** A block fixture draws one chance span, and an
  unknown period shows "period?". Beyond-coverage ICON values are muted with
  their tooltip. The "?" glyph appears on an Uncertain night.
- **R16. Layers and advisory.** Layers sit under "For information" with the
  ECMWF label; the advisory text matches C13; a fallback night shows no
  estimate label.
- **R17. Editor.** All new fields validate, save, reload and preview; imperial
  conversion of the threshold round-trips.
- **R18. Reasons.** The week row shows the headline plus blockers; Uncertain
  shows the attribution; the coverage qualifier is visible.
- **R19. Tonight.** It shows "remaining", the Night-over wording and the same
  verdict as the Weather row.
- **R20. Fractional zones.** For +5:30 and +5:45 locations, and for a Lord
  Howe fall-back night, labels and the darkness band line up with the cells.
  Repeated local times show distinct tooltips with offsets. A whole-hour
  location is pixel-identical to R11's reference.

## Delivery gates

1. **Per task:**
   - Codex implements and leaves the work unstaged.
   - Claude takes inventory snapshots before and after and diffs them, reads
     the diff, re-runs the task's commands, then stages.
   - Findings go back in one batch.
2. **High-stakes checks:**
   - Claude upgrades a copy of Fred's workspace database (at 0058) through
     0059 and 0060.
   - Row counts are unchanged except in yoyo's own tables and in
     `location_imaging_rules`, which is empty (F1).
   - `integrity_check` is `ok` and `foreign_key_check` is empty.
   - The Weather page then shows the default rules and the preset prompt for
     Fred's locations.
   - The copy is then deleted.
3. **Before Fred's acceptance test:**
   - a fresh independent Codex review (`gpt-5.6-sol`, high, read-only) of the
     whole diff for this plan;
   - the full backend suite;
   - `npm run build`;
   - R11–R20 plus the v0.41.9 plan's R1–R10.
4. **Release:** follows `finalize-session`, with Fred's authorization.

## Spec coverage

| Spec | Task |
|---|---|
| §3.1 sources, model amounts | 2 |
| §3.2 declared coverage, C4 | 3 (constants), 11 (tightening) |
| §3.3 metadata, C8 | 2, 3 |
| §3.4 refetch, C5 | 2 |
| §4.1 share ≥, F1 | 1 (rules, migration), 9 (editor) |
| §4.2 total-only cloud | 3, 4, 8, 9 |
| §4.3 limits, periods, threshold, forecasts to check, C9 | 1, 3, 4, 5, 9 |
| §4.4 presets | 1 |
| §4.5 per-night controls | 5, 6, 8 |
| §5.1–5.7 evaluation, C2, C3, C11 | 4, 5 |
| §5.8 freshness, C7 | 5, 6 |
| §5.9 evaluation time, C15 | 7 |
| §5.10 guarantee, C17 | 4, 5 |
| §6.1 week view, C1, C10 | 6, 10 |
| §6.2 reasons, C14 | 5, 6, 7 |
| §6.3 night details, C13 | 8 |
| §6.4 Tonight card | 10 |
| §6.5 rules editor, F2 | 9 |
| §6.6 display fixes, C12 (icon minimum dropped, C1) | 6, 7 |
| §7 migration (replaced by F1: rules discarded) | 1 |
| §8 documentation | 6 (methodology), 11 |
| §9 acceptance tests | 1, 3–6, R11–R20 |
| C16 fractional offsets | 6, 10 |

## Codex review

- **Mode and records.** A blinded pre-pass (Codex's own architecture first),
  then independent plan review. 5 of 5 rounds were used. Records:
  `.superpowers/codex/v0.41.9/`, items 73–84 (local). Codex's verdict after
  round 5 was "ready to present".
- **Adopted changes:**
  - **Spec clarifications C1–C17** (spec §11). In particular:
    - the hour strip stays frozen;
    - "Night over" keeps its current meaning;
    - precedence is limited to night-level outcomes;
    - a whole missing response stays expected-missing and never falls back;
    - fields are parsed independently;
    - freshness is counted per source.
  - **Request horizon.** 16 forecast days. Expected coverage is capped by the
    requested range, which comes from the request parameters, never from the
    response axis.
  - **Cache.**
    - Rows written before this change are refetched.
    - Truncation is detected per model and per field.
    - Repairs are limited to one per source per hour and coalesced.
    - The cloud row and its metadata are written atomically, read in one
      statement and paired by full-precision timestamp plus hash.
  - **Chance period.**
    - It never depends on comparing values, which would break the guarantee.
    - NBM's footprint is the provider's own grid, with a 2-cell edge band
      treated as inside.
    - Absent, stale or unmatched evidence makes the period unknown.
  - **Evaluator.**
    - Precipitation is excluded from session states under `night_off`.
    - An unresolved primary never returns before a precipitation veto.
    - Today's polar rule is kept.
  - **Guarantee tests.** These are layered: exhaustive short-session cases,
    an all-night count reduction, every 8-hour sequence through the kernel,
    the combiners, and seeded end-to-end cases from raw payloads with sanity
    floors. There is no new dependency.
  - **Task boundaries.**
    - The coverage foundation moved into Task 2.
    - Task 5 keeps the current response contract.
    - Tasks 6–7 are staged together.
    - Smoke runs happen at each boundary.
  - **Frontend.**
    - Polling is gated on the active route.
    - The trace guard applies after unit conversion.
    - The resolution note covers wholly coarse nights.
    - Fractional-offset and DST cells are identified by UTC.
- **Rejected material findings:** none.
- **Codex withdrew** grandfathering of shares below 1% once it was shown that
  no released install has saved rules. Fred then decided (F1, 2026-10-18) to
  discard saved rules altogether.
- **Tracked items:** none at planning time.

### Implementation review (2026-10-18)

- **Process.** Codex implemented Tasks 1–10, and Claude reviewed each one:
  - an inventory diff and a full reading of the diff;
  - the full backend suite outside the sandbox;
  - rendered checks against an isolated copy of a real workspace database
    with live Open-Meteo data.

  Findings went back in batches. Notable fixes:
  - stale semantics within the TTL (Task 2);
  - restored regression tests, and "missing never a definite No" (Task 5);
  - the hour range kept under per-night controls (Task 6);
  - constrained time controls with a 422 fallback (Task 8);
  - concise reason lines with a full "Why" list in details (Task 10).
- **Independent review** (fresh session): no blockers. Three major findings
  were fixed:
  - a cooldown after failed refreshes;
  - local-hour clock grouping across half-hour DST;
  - coverage constants from observation.

  One minor finding was fixed: single-model reporting.
- **Gates passed:**
  - the full backend suite;
  - `npm run build`;
  - the upgrade of a copy of a real database through 0059 and 0060;
  - R11, the strip pixel-identical against pre-change references;
  - R14–R20.
- **Open:** the 24-hour availability observation, before the coverage
  constants are final.

### F4 — cloud forecasts and wording (2026-10-18)

- **Design.**
  - A blinded Codex pre-pass and Claude's frozen proposal converged in 2
    rounds on an hourly majority. A per-night vote and a third "follow the
    preferred forecast" mode were rejected.
  - A replay of 14 cached nights supplied the evidence.
  - Fred chose the majority (spec §11 F4).
- **Wording.**
  - Codex drafted "How the verdict works" and the rules-editor labels and
    hover notes; Claude checked every fact.
  - Two drafts were corrected: the 6-hour chance repetition applies only in
    North America, and a zero-limit claim was unverified. Fred's
    "Longest interruption" label was kept.
- **Review.**
  - Claude's review found 7 issues, all fixed. Among them:
    - a short-session window starting on hours no forecast reaches;
    - a "models agree" claim when nothing was compared;
    - the line-length waiver scoped to one file.
  - A fresh independent review found no blockers and no guarantee
    violation. Its 1 major and 3 minor findings were fixed:
    - the forecasts used are taken from per-hour reach, not session status;
    - the layer source is labelled;
    - the docs are corrected;
    - the notes open on keyboard focus.
- **Gates passed:**
  - the full backend suite;
  - `npm run build`;
  - 0062 on a copy of a real 0061 database (rows and timestamps kept,
    defaults added, both invalid combinations rejected, trigger working);
  - a rendered check: hover and focus notes, both explanation sections, and
    "Show Uncertain" giving 3 Uncertain against the majority's 2 Go, as the
    replay predicted.

### Status at candidate preparation (2026-10-23)

- **Closed:** the 24-hour availability observation. It ran on 2026-10-18/19
  (25 runs at three sites), and the constants are set from it: ECMWF 334 h,
  GFS 353 h, ICON 158 h, best_match 331 h. The batched Codex review of
  Claude-authored changes checked the arithmetic.
- **Coverage round.** A coverage check against `main` found reachable
  behavior without tests: the dew rule when counted, two parsing paths, and
  four model-metadata defenses. It also found two cloud-model methods left
  unused when the old spread code was removed. Codex added the tests and
  removed the methods, with no behavior change. Codex also corrected one of
  Claude's stated facts: a seeing branch Claude cited is unreachable. Claude
  verified that and reviewed the round. Records 201–206.
- **Tracked items:** none. No rejected material finding and no unresolved
  disagreement.
