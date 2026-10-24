# Imaging forecaster revisions — consolidated change specification

**Status:** Handed over by Fred on 2026-10-17 for planning. §11 records
Fred's decisions (F1–F3, decided 2026-10-18).

**Origin:** Two outside reviewers (Fable and Astra) wrote the body of this
document (§1–§10). They worked from a private review document that Claude wrote
for them, which explains the v0.41.9 forecaster. Claude and Codex then checked
the body against the code in a two-round discussion and agreed the
clarifications in §11. Local record: `.superpowers/codex/v0.41.9/`, items 73–84.

**How to read it:**

- The changes amend the v0.41.9 spec,
  [2026-10-17-weather-redesign-design.md](2026-10-17-weather-redesign-design.md).
  Where this document is silent, that spec, together with
  `docs/development-decisions.md` (Weather), stands.
- The body is kept as written. The original's references to the private review
  document now point to repository documents.
- **§11 overrides the body** wherever the two differ. The body marks each such
  place with "(see §11, Cn)".
- Existing rule names (`night_off`, `hours_lost`) are used where they already
  exist. New names for settings, fields and components are left to the
  implementer.

**Contents**

1. Scope and requirements
2. Terms
3. Sources, coverage and caching
4. User settings
5. Evaluation
6. Presentation
7. Migration
8. Documentation and text
9. Acceptance tests
10. Out of scope
11. Agreed clarifications and pending decisions

---

## 1. Scope and requirements

This change modifies how a night is evaluated and explained. It adds no data
source and no accuracy work. The v0.41.9 spec's constraints remain requirements:

- The answer is a verdict, never a score.
- A missing value is never treated as a good value. Stale data never produces
  Go.
- Every state is distinguishable without colour.

Two further requirements are added by this change:

- **Verdict guarantee.** With the rules, the evaluation interval and the
  declared coverage fixed, replacing any known forecast value with an unknown
  must not turn a non-Go verdict into Go. (§5.10)
- **Determinism of coverage.** Which models are expected to contribute to a
  night is decided by fixed per-model coverage, never by which values happen to
  be present in the latest response. (§3.2)

---

## 2. Terms

- **Verdicts:** Go, Uncertain, No, Not enough data, Night over (unchanged).
- **Imaging interval:** the part of the night on which cloud, wind, dew, Moon
  and the session rule are judged. Defaults to the dark period; bounded by the
  per-night controls (§4.5) and clipped to "now" for a night under way.
- **Exposure interval:** the part of the night in which the gear is outside and
  precipitation is judged under `night_off`. Defaults to sunset − gear-out
  minutes through sunrise + gear-in minutes; bounded by the per-night controls;
  clipped to "now". Under `hours_lost` there is no exposure interval;
  precipitation is judged on the imaging interval like any other check.
- **Hourly state** of a model for an hour: *pass*, *fail* or *unknown*. An
  unknown hour is tagged **expected-missing** (inside the model's declared
  coverage, value absent) or **not-covered** (outside its declared coverage).
- **Two-pass evaluation** (existing; v0.41.9 spec §4.2): *pessimistic* treats unknown as fail,
  *optimistic* treats unknown as pass. A test is **established Go** if it passes
  pessimistically, **established No** if it fails optimistically, otherwise
  **unresolved**.
- **Primary model:** ECMWF for cloud, or the labelled `best_match` fallback
  (§5.3). **Comparison models:** GFS and ICON cloud.
- **Established conflict:** a shared window (short session) is impossible even
  optimistically, or (all night) a comparison model's established verdict
  differs from the primary's.
- **Period** of a precipitation-chance value: *hourly*, *multi-hour block of
  known length*, or *unknown*.

---

## 3. Sources, coverage and caching

### 3.1 Sources

Unchanged: Open-Meteo main forecast (`best_match`), the three-model cloud
request (ECMWF IFS 0.25, GFS seamless, ICON seamless), water vapour and
aerosols for context. The three-model request additionally fetches each
model's **precipitation amount** (needed by §4.3).

### 3.2 Declared coverage (see §11, C4)

Each source has a **declared coverage**: a fixed number of hours from the fetch
time, held as a constant per model, set below the model's typical reach.

| Source | Starting value | Notes |
|---|---|---|
| ECMWF IFS 0.25 (cloud; primary) | 14 days | measured reach ≈ 14.5 days |
| GFS seamless (cloud; comparison) | 15 days | measured ≈ 15.5 |
| ICON seamless (cloud; comparison) | 6.75 days | measured ≈ 7 |
| Main forecast `best_match` (precipitation, wind, etc.; cloud fallback) | 15 days | 16-day product |
| NBM chance regime (CONUS only; §4.3) | 10 days | ≈ 11-day product |
| CAMS aerosol (context) | 4 days | context only |

Rules:

1. Inside declared coverage, a missing value is **unknown** (expected-missing)
   and participates in the two-pass.
2. Outside declared coverage, a model is **not expected** for that hour. Values
   present there are **informational only**: shown in per-model rows, never
   used in a verdict or named in a reason as agreement or disagreement.
3. The constants are tightened after observing actual reach across one day of
   refreshes (availability observation, not accuracy work). Err short: data
   past the cutoff is merely informational; a cutoff that is too long produces
   spurious Not enough data near the edge.

### 3.3 Model metadata (approximate aid; see §11, C8 and C10)

Open-Meteo publishes per-model metadata at
`https://api.open-meteo.com/data/<domain>/static/meta.json` (domains include
`ecmwf_ifs025`, `ncep_gfs013`, `dwd_icon`, `ncep_nbm_conus`) with
`last_run_initialisation_time`, `last_run_availability_time`,
`temporal_resolution_seconds`, `update_interval_seconds`. It is fetched in the
same refresh as the forecast and stored with the cache. It is used only for
three approximate purposes: locating NBM's 36-hour hourly/block boundary (§4.3),
locating ECMWF's 144-hour 3-hourly/6-hourly boundary (§6.3), and showing run
age next to retrieval age (§5.8). Association with a cached series is
approximate (±one update interval); every use below has a defined behaviour
when the metadata is unavailable.

### 3.4 Caching and refetch (see §11, C5)

- TTL and stale handling unchanged (v0.41.9 spec §4.4), except as §5.8 specifies for
  verdicts.
- The "refetch within TTL" rule is restated per source: refetch a cached source
  within its TTL only when the cached series ends earlier than that source's
  declared coverage measured from the cache's own fetch time (an obsolete or
  truncated cache). A night not being covered by a source is never a reason to
  refetch.

---

## 4. User settings

### 4.1 Session rule wording (see §11, F1)

The all-night share test becomes **"at least … % of dark time"** (was strictly
"more than"). Range 1–100. Existing saved values are kept as numbers; the
comparison becomes ≥. Release notes state the one-case effect (a night exactly
at the threshold is now Go).

### 4.2 Cloud

The cloud check compares the **reported total cloud** of whichever model is
being evaluated with the maximum-cloud limit. Low/mid/high layers never count. A
missing total is unknown; it is never rebuilt from layers. Editor text: "Uses
the model's total cloud cover."

### 4.3 Precipitation

**Chance limits.** Two fields:

- *Maximum chance — per hour* (existing field, renamed).
- *Maximum chance — per multi-hour period* (new). Defaults to the per-hour
  value for presets and for migrated locations. No ordering constraint between
  the two.

Which limit applies to a value depends on its **period**:

| Period of the value | Limit applied | Display |
|---|---|---|
| Hourly (established) | per-hour limit | per-hour cell |
| Multi-hour block (established) | per-period limit | one span across the block's hours |
| Unknown | **the lower of the two limits** | per-hour cell with a "period unknown" mark |

Establishing the period (best effort; see §11, C9): in CONUS the main forecast's chance comes
from NBM, which is hourly to 36 h after its run initialisation and 6-hour blocks
aligned to 00/06/12/18 UTC thereafter, copied into each hour. The implementer
may detect the NBM regime by also requesting NBM's chance series and comparing
it with the main forecast's, and may locate the 36-hour boundary from the stored
NBM metadata; within one update interval of that boundary, and whenever the
regime or the boundary cannot be determined, the period is **unknown**. Outside
the NBM regime the chance is an ensemble value interpolated to hourly and is
treated as **hourly**. When both limits are equal (the default) the choice of
limit has no effect and the period only affects display.

**Amount threshold.** New field: *Count precipitation above … mm/h*, default 0.
The check fails when amount **>** threshold; an amount equal to the threshold
passes. Default reproduces today's "any amount fails".

**Precipitation forecasts to check** (new, per location):

- **Main forecast** — today's behaviour.
- **Any model** — in addition, an hour fails if ECMWF's, GFS's or ICON's own
  forecast **amount** exceeds the threshold. Chance is not taken from the extra
  models. Each extra model participates only inside its declared coverage; an
  expected-missing amount is unknown; outside coverage the model is not
  expected. Help text states that this is a deliberately cautious rule using
  each model's own forecast amount, and that the main forecast's chance remains
  the only chance used.

**Help text** for the chance fields: the limit applies to each reported value;
beyond about 36 hours in North America a value describes a 6-hour period; the
night-level risk is higher than any single value; the reported chance is
rarely exactly 0%, so a 0% limit will reject most nights.

### 4.4 Presets

| Preset | Session | Cloud | Chance per hour / per period | Amount threshold | Policy | Forecasts to check | Gear out / in | Wind | Dew | Moon | Dark |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Left out all night | all night, ≥ 50%, ≥ 2 h | ≤ 20% | **10% / 10%** | 0 | whole night off | **Any model** | 30 / 30 | **on**, 30 / 45 km/h | off | off | astronomical |
| Attended session (default) | 2 h in a row | ≤ 20% | 20% / 20% | 0 | hours lost | Main forecast | — | on, 30 / 45 | off | off | astronomical |
| Dome / roll-off | all night, ≥ 50%, ≥ 2 h | ≤ 20% | 20% / 20% | 0 | hours lost | Main forecast | — | off | off | off | astronomical |

The "Left out all night" preset's chance note reads, in substance: the reported
chance is rarely exactly zero; with the any-amount rule still in force, 10% is
the practical floor. Presets still appear only for a location without saved
rules (v0.41.9 spec §3.2).

### 4.5 Per-night controls

Per night, not saved (v0.41.9 spec §3.4). Which pair is shown follows the location's
precipitation policy:

| Policy | Controls | Meaning |
|---|---|---|
| `night_off` | **Gear out at … / Gear in at …** | Bounds the exposure interval. The imaging interval is the dark part of it. |
| `night_off`, with the optional checkbox **"Imaging times differ from equipment times"** | adds **Imaging from … / Imaging until …** | Bounds the imaging interval, validated to lie inside the exposure interval. Cloud, wind, dew, Moon and the session rule use the imaging interval; precipitation uses the exposure interval. |
| `hours_lost` | **Imaging from … / Imaging until …** | Bounds the imaging interval. |

Defaults are the natural boundaries (sunset/sunrise ± gear minutes; start/end of
darkness). For a night under way both intervals also start at "now".

---

## 5. Evaluation

### 5.1 Checks per hour (see §11, C11)

| Check | Fails when | Unknown when | Counted on |
|---|---|---|---|
| Cloud | model's total > max cloud | total missing (expected) | imaging interval, hours with dark minutes |
| Chance (main forecast) | value > applicable limit (§4.3) | value missing (expected) | exposure interval under `night_off`; imaging interval under `hours_lost` |
| Amount (main forecast) | amount > threshold | missing (expected) | same as chance |
| Amount (each extra model, if "Any model") | amount > threshold | missing inside declared coverage | same as chance; not applicable outside coverage |
| Wind, Dew, Moon | unchanged | unchanged | imaging interval, if counted |

A known fail beats an unknown. An hour is **clear** when every counted check
passes, **unknown** when none fails and a counted check is unknown, otherwise
**not clear**. Non-cloud inputs are shared by every model at the primary's
values. "Conditions" for display (checks with intervals ignored) are unchanged
(`docs/development-decisions.md`, Weather: display conditions).

### 5.2 Per-model night status (see §11, C4)

For the primary and for each comparison model, run the existing two-pass over
the **whole** imaging interval, treating every unknown hour (expected-missing or
not-covered) as unknown; the denominator is the whole interval. Then:

| Two-pass result | Expected-missing hours among the unknowns that matter? | Status |
|---|---|---|
| Established Go / No | — | that status |
| Unresolved | yes | **unresolved** |
| Unresolved | no (only not-covered hours) | **not expected for this night** |

"Unknowns that matter" are those whose values would change the outcome. The
simpler sufficient test "any expected-missing hour exists in the interval" is
acceptable; it can only change a disclosure into Not enough data, never into Go.

### 5.3 Primary selection and fallback

ECMWF is the primary. If ECMWF's status is **not expected for this night**
(unresolved only for want of hours outside its declared coverage), the night
falls back to `best_match` cloud as primary, labelled. A fallback night performs
**no model comparison** (it cannot be Uncertain) and says so in the coverage
line. If ECMWF's status is established, it is used even when its coverage ends
inside the night. If ECMWF's status is unresolved with expected-missing hours,
the verdict is Not enough data naming those hours.

### 5.4 Early exits (first match wins; see §11, C2)

1. **Night over** — darkness has ended (and, under `night_off`, the exposure
   interval too; see §6.4).
2. **No — never dark enough.**
3. **No — no dark time** inside the imaging interval.
4. **No — precipitation**, under `night_off`: a known failing chance or amount
   (main forecast, or an extra model's amount if enabled) at any hour of the
   remaining exposure interval. Reason per §6.2.

An unknown precipitation value in the remaining exposure interval, with no known
failure, does **not** exit here; see §5.7.

### 5.5 Short session — shared window

Required run length R (dark minutes, as today). Runs never bridge non-dark time.

1. Primary status per §5.2. Established No → go to §5.6's No handling.
   Unresolved → Not enough data (primary's missing hours). Established Go →
   continue.
2. **Joint hourly state** per hour: *fail* if any model expected at that hour
   fails; else *unknown* if any expected model is unknown; else *pass*. A
   comparison model participates at an hour only if the hour is inside its
   declared coverage.
3. **Shared-window status** by two-pass over joint runs of length ≥ R:
   *established* (a run exists pessimistically), *impossible* (none exists
   optimistically), else *unresolved*.
4. Verdict:

| Primary | Shared window | Verdict | Reason |
|---|---|---|---|
| Go | established | **Go** | "Clear hh:mm–hh:mm — all expected models" (earliest established window), plus coverage line |
| Go | impossible | **Uncertain** | per comparison model, the known failures that break each candidate window |
| Go | unresolved | **Not enough data** | the missing comparison hours; any partial known conflicts |

5. If the primary is established **No**: for each comparison model, status per
   §5.2 over its own hourly states.

| Comparison models | Verdict | Reason |
|---|---|---|
| any established Go | **Uncertain** | primary's failing rule; each dissenting model's window |
| none established Go; all with evidence established No | **No** | primary's failing rule; "GFS and ICON agree" |
| none established Go; some unresolved | **No** | "Primary forecast fails your rules; ICON is incomplete" |

Models **not expected for this night** are omitted from these rows and named in
the coverage line.

### 5.6 All night — comparison

Primary status per §5.2 (Unresolved → Not enough data). Comparison models'
statuses per §5.2.

| Primary | Comparison models | Verdict |
|---|---|---|
| Go | all expected models established Go | **Go** |
| Go | any established No | **Uncertain** |
| Go | none established No; any unresolved | **Not enough data** (names the model and hours) |
| No | any established Go | **Uncertain** |
| No | none established Go; all with evidence established No | **No** |
| No | none established Go; some unresolved | **No**, disclosed ("…; ICON is incomplete") |

Models not expected for this night are omitted and named in the coverage line.
A primary established No is compared exactly as a primary Go is; two Nos agree.

### 5.7 Unknown precipitation veto and precedence (see §11, C3 and C11)

Under `night_off`, if a chance or amount value in the remaining exposure
interval is unknown and none is a known failure, take the cloud-side verdict V
from §5.5/§5.6:

- V = Go or Uncertain → **Not enough data**, naming the missing precipitation
  hours and, if applicable, the model disagreement.
- V = No or Not enough data → unchanged; the missing precipitation is listed as
  an additional unknown.

Under `hours_lost` an unknown precipitation hour is simply an unknown hour in
§5.1.

**Precedence when more than one outcome applies:** established No › Not enough
data › Uncertain › Go. The reason explains every contributing cause.

### 5.8 Freshness (see §11, C7)

Applied last, to the final verdict, when any decisive source the night used is
stale (refresh failed; served from cache past TTL):

| Verdict | Shown as |
|---|---|
| No | "No — forecast N h old, refresh failed" |
| Go, Uncertain, Not enough data | "Not enough data — forecast N h old, refresh failed" |

Astronomy-only verdicts (Night over, never dark, no dark time) are unaffected.
N is retrieval age; where stored metadata gives a per-model run age the label
says which is shown.

### 5.9 Evaluation time (see §11, C15)

Verdicts are not cached. Forecast inputs are cached; every request evaluates
against the current time. An open Weather or Tonight page re-evaluates whenever
the verdict could change — crossing of now past a control time, a darkness
boundary, or the point where remaining dark time equals the minimum hours or
the required run — and at least once a minute is acceptable.

### 5.10 Guarantee and its test (see §11, C17)

With the rules, intervals and declared coverage fixed, replacing any known value
by unknown must not create Go from a non-Go. Every Go condition is a pessimistic
pass (primary, comparison models or shared window), the absence of a known or
unknown veto, and fresh data; each is monotone in the required direction, and
declared coverage keeps the expected set fixed. Two exhaustive tests guard it
(§9, last two rows). Permitted and correct transitions when data is removed
include Uncertain → No (disclosed), No → Not enough data, Uncertain → Not enough
data.

---

## 6. Presentation

### 6.1 Week view (see §11, C1 and C10)

- Pills, strip, clock and legend unchanged in form. The Go pill's reason for a
  short session names the window and "all expected models".
- **Disagreement marks** appear in hour cells only on Uncertain nights, on hours
  where an expected comparison model's known state differs from the primary's.
  Go nights never show them.
- **Coverage qualifier:** when a model expected for part of the night is
  excluded as not expected for the whole night, or the primary is the fallback,
  the reason line carries a short qualifier ("ICON not used — covers only to
  23:00"; "best_match cloud — ECMWF beyond its reach"). Not enough data reasons
  name the missing source and hours and, where a refresh may help, say so.
- A night whose ECMWF cloud is 6-hourly for any dark hour carries a small
  **resolution indicator** ("6-hourly cloud data from hh:mm"). The boundary is
  144 h after ECMWF's run initialisation from stored metadata; without metadata,
  assume 136 h after fetch.
- Outlook tab unchanged.

### 6.2 Reason lines (see §11, C14)

- Structure: the **primary reason** (per the precedence in §5.4–5.7), then
  **other independent blockers** in a short clause ("Precipitation 11% for the
  6-hour period 17:00–23:00 — your limit is 10%; cloud also leaves 2.3 h of
  10.3 clear").
- Precipitation wording: name the failing hours and the peak value separately
  ("Precipitation over your limit 21:00–23:00; peak reported chance 20%, limit
  10%"); for a block, name the period and its overlap with the exposure
  interval; for an unknown period, say "period unknown".
- Attribution beside Uncertain: "ECMWF: 10 of 10 h meet your rules; ICON
  predicts cloud after 23:00".
- Extra-model vetoes name the model and amount ("ICON: 0.7 mm/h 20:00–22:00").

### 6.3 Night details (see §11, C13)

- "Counts toward your verdict": **Cloud % (ECMWF total)** or the fallback's
  name; per-model **total** rows (GFS, ICON) with their status; precipitation
  chance with **block spans** and "period unknown" marks; precipitation amount;
  extra-model amount rows when "Any model" is on; darkness band.
- The three layer rows move to "For information". For ECMWF they are labelled
  **"humidity estimate (Open-Meteo) — not counted"**; for the fallback, shown
  without that label.
- Values outside a model's declared coverage are shown in a muted style with a
  "beyond declared coverage — not counted" tooltip.
- A **coverage line** at the top of the model section: each model, its declared
  coverage end if inside the night, and its status (Go / No / incomplete / not
  expected / not used).
- Checklist glyph for "Models disagree" is the same **?** glyph as the Uncertain
  pill, never ✕.
- "Clear dark hours 10 of 10 h" is attributed to the primary when the night is
  Uncertain or Not enough data.
- Resolution indicator as in §6.1; row tooltip states which hours are 6-hourly.

### 6.4 Tonight card

Same strip and reason rules. "0 h clear of 7.2" becomes "0 h clear of 7.2
remaining". "Night over" means darkness has ended; where a `night_off` exposure
interval continues past it, the card does not imply exposure has ended (the
precipitation check for the tail is out of scope for this change; the wording
must not contradict it).

### 6.5 Rules editor (see §11, F2)

- Cloud text per §4.2. Chance fields and help per §4.3. New "Precipitation
  forecasts to check" control in the "Cloud and precipitation" group, with its
  help text. Amount threshold field.
- Rules summary bar: "Clear = cloud ≤ 20%" becomes **"Cloud limit ≤ 20%"**;
  "Longest cloudy stretch" becomes **"Longest interruption"**; "more than"
  becomes "at least".
- Live preview continues to use the same evaluator.

### 6.6 Display fixes (see §11, C1 and C12)

- One trace-aware formatter for all amounts: a positive amount never prints as
  zero ("<0.01 in" / "<0.1 mm").
- A night's total amount over an interval with missing hours is shown as
  incomplete ("≥ 0.3 mm, 2 h missing"), never as a plain total.
- Hour-cell icons have a minimum size with an overflow indicator.

---

## 7. Migration (see §11, F1)

For every saved location:

- *Maximum chance per multi-hour period* := its existing chance limit.
- *Count precipitation above* := 0.
- *Precipitation forecasts to check* := **Main forecast**, regardless of its
  `night_off` / `hours_lost` choice. The new option is visible in the editor;
  nothing switches silently.
- The share comparison becomes ≥ for all (§4.1).
- No other saved value changes. Locations without saved rules continue to use
  the "Attended session" defaults.

---

## 8. Documentation and text

- Rules editor, "How the verdict works", the design spec and the algorithm
  documentation describe the total-only cloud rule and record the reason: for
  ECMWF IFS 0.25 on Open-Meteo, low/mid/high cloud are estimated from relative
  humidity on pressure levels (low 1000/925/850 hPa; mid 700/600/500/400 hPa;
  high 300/250/200/150/100/50 hPa, as of the 2025-10-13 downloader change) and
  the total is the model's own field.
- "How the verdict works" explains: the chance's source and period (NBM in
  North America: P(> 0.254 mm) per hour to 36 h, per 6-hour block after;
  ensembles elsewhere: member share with ≥ 0.1 mm per hour of the model step,
  interpolated); that "Main" and "GFS" chances are the same product in CONUS;
  the two-limit rule and the lower-limit fallback; the coverage policy and what
  "all expected models" means; the freshness rule; the per-night controls'
  semantics.
- The history (`docs/archive/imaging-quality-model.md` §7 and the comment above
  `CLOUD_PRIMARY_MODEL` in `services/weather.py`) records that the v0.41.5 comparison was
  scored against ERA5, which is itself an IFS product, at one site over two
  weeks, with the scored cloud field unrecorded; ECMWF remains the primary as a
  pragmatic choice.
- Known limitations list (`docs/weather-algorithms.md` §5): replace the precipitation limitation with the period/source
  description above; add the declared-coverage behaviour; keep the rest.
- Seeing and transparency help: state which parts are heuristic; show when the
  transparency tier has degraded.

---

## 9. Acceptance tests

Hand-computed cases. Mode and interval are stated; "threshold" is the amount
threshold; "limits" are the two chance limits.

**Cloud (from the cloud-layer consensus, unchanged; see §11, C13)**

| Case | Expected |
|---|---|
| (total 4, layers 0/0/21) at a 20% limit | clear |
| total 0, layers missing | clear |
| total exactly at the limit | clear |
| total missing, layers present | unknown; no reconstruction |
| comparison model with missing total but layers present for an expected hour | that hour unknown for it |
| ECMWF total missing in an expected hour | ECMWF unresolved → Not enough data (not fallback) |

**Precipitation chance and amount**

| Case | Mode | Expected |
|---|---|---|
| limits 30% / 10%; value 20%, period unknown | night_off | fails (lower limit); "period unknown" mark |
| same, period established hourly | night_off | passes |
| limits equal; period unknown | any | same result as either limit |
| 6-hour block at 11% overlapping the exposure interval by 54 min; per-period limit 10% | night_off | No; block drawn as one span; reason names the period and overlap |
| same with per-period limit 25% | night_off | passes the chance check |
| amount 0.05 mm/h, threshold 0 | any | fails the amount check |
| amount 0.1 mm/h, threshold 0.1 | any | passes the amount check (equal passes); hour may still fail other checks |
| ICON amount above threshold inside the exposure interval; main forecast dry | Any model, night_off | No, naming ICON, hours, amount |
| same, ICON amount above threshold only outside the exposure interval | Any model, night_off | no effect |
| main 5%, ECMWF ensemble chance 60%, all amounts 0 | Any model, night_off, limit 10% | passes (chance is taken from the main forecast only) |
| previously vetoing ICON amount becomes expected-missing inside the exposure interval | Any model, night_off | Not enough data unless the night fails anyway; never Go |
| same gap under hours_lost with a fully known qualifying window elsewhere | Any model, hours_lost | Go |
| missing main-forecast precipitation only in a twilight setup hour | night_off | can produce Not enough data |
| rain before now | night under way, night_off | does not veto the remaining exposure interval |

**Coverage and comparison**

| Case | Mode | Expected |
|---|---|---|
| ICON beyond declared coverage; primary and GFS established Go | either | Go; coverage line "ICON not available beyond 6.75 days" |
| ICON value present beyond declared coverage and failing | either | Go; value shown muted, not in the reason; identical on the next refresh if the value is absent |
| ICON wholly missing inside declared coverage; primary and GFS Go | either | Not enough data, "ICON unavailable — refresh later" |
| ICON cloudy for 2 covered hours of an 8-hour interval, 6 not covered; ≥ 75% | all night | ICON not expected for the night; Go with disclosure |
| ICON cloudy for 7 covered hours of 8, 1 not covered; ≥ 75% | all night | ICON established No; Uncertain |
| ICON covers all 8 but one expected hour missing and that hour decides | all night | ICON unresolved; Not enough data |
| ECMWF covers 6 of 10 hours of night 14, all cloudy; ≥ 90% | all night | ECMWF established No; no fallback; comparison proceeds |
| ECMWF covers 6 of 10 hours of night 14, all clear; ≥ 90% | all night | ECMWF not expected for the night; fallback to best_match, labelled; no comparison |
| ECMWF 20–00 clear; GFS 20–22 clear, 22–00 cloudy; ICON 20–22 cloudy, 22–00 missing (expected); R = 2 h | short session | Uncertain; reason names GFS 22–00 and ICON 20–22 + gap |
| primary and GFS pass throughout; ICON pass then expected-missing over the only 2-h window | short session | Not enough data; no conflict named |
| ECMWF two windows; comparison models support only the second | short session | Go naming the second window |
| each model has a 2-h run, pairwise disjoint | short session | Uncertain, "no shared window" |
| night straddles ICON's declared coverage | short session | windows checked against the models expected for all their hours; reason names them |
| primary established No; GFS and ICON established Go | either | Uncertain |
| primary No; GFS No; ICON unresolved | either | No, "…; ICON is incomplete" |
| primary fails; GFS passes; GFS's passing values become unknown | either | Uncertain → No (disclosed); never Go |
| primary's decisive failure becomes unknown; comparisons fail | either | No → Not enough data |
| ICON's last known failing value disappears | either | Uncertain → Not enough data |
| established precipitation veto plus cloud disagreement | night_off | No (precipitation); disagreement as added context |
| unknown precipitation in the exposure interval plus cloud Go / cloud Uncertain | night_off | Not enough data, naming both where applicable |

**Time, freshness, display**

| Case | Expected |
|---|---|
| "Gear out at 23:00" set; 11% block ends 23:00; clear thereafter | exposure and imaging intervals start 23:00; Go |
| "Gear in at 00:00" set; shower forecast 02:00 | ignored; control label says the gear is indoors |
| imaging 20:00–01:00 inside exposure 17:00–07:00 (checkbox on) | cloud after 01:00 does not reduce the share; precipitation at 03:00 vetoes |
| "Imaging until 00:00" under hours_lost | dark minutes end at 00:00; no exposure interval |
| darkness ends before gear-in | card wording does not state exposure has ended |
| remaining dark time crosses the minimum-hours boundary at hh:31 | verdict changes within the hour, including on an open Tonight page |
| stale source, verdict would be Go / Uncertain / Not enough data | Not enough data with age |
| stale source, verdict No | "No — forecast N h old" |
| night with 6-hourly ECMWF hours inside the 7-day tab | resolution indicator shown |
| cached ECMWF series ends before its declared coverage from its fetch time | refetched within TTL; a night 14 not covered does not trigger a refetch |
| tiny positive amount; incomplete interval total | never shown as an unqualified zero / plain total |
| several rules fail on one night | reason gives the primary rule plus other blockers |
| location at UTC+5:30 (see §11, C16) | hour cells and labels align with the local clock; durations consistent |
| DST transition night (25 or 23 hours) | durations and timestamps consistent |
| Go night with an hourly state differing between ECMWF and GFS | no disagreement marks on a Go night |

**Exhaustive guarantee tests** (see §11, C17)

| Case | Expected |
|---|---|
| 3 expected models × 3 hours × R = 2 h; every assignment of pass/fail/unknown; every single replacement of a known value by unknown | no replacement turns a non-Go into Go |
| all night: 8-hour interval, ≥ 75%, 3 expected models, every assignment and single replacement | same |

---

## 10. Out of scope

Forecast-accuracy work or new sources; a precipitation check on the Tonight
card for the exposure tail after darkness ends; Moon illumination or
custom-horizon Moon rules; showing the primary's state inside disagreement
cells; changes to seeing or transparency computation.

---

## 11. Agreed clarifications and pending decisions

Claude and Codex agreed these in two rounds on 2026-10-17. Each one overrides
the body where they differ. The "Evidence" lines record what was checked.

### Clarifications

**C1. The hour strip does not change** (Fred, 2026-10-17). Its icons, their
sizing and its layout stay as they are. §6.6's third bullet (a minimum icon
size with an overflow indicator) is dropped.

The disagreement marks of §6.1 are the strip's existing "models" cell (split
icon). They appear only on Uncertain nights, on hours where an *expected*
comparison model's known state differs from the primary's. The backend sends
this as a per-hour flag.

**C2. Night over** means darkness has ended, or the imaging interval has
ended (an earlier "Imaging until"). This keeps Fred's earlier decision. The
exposure tail after darkness is not evaluated (§10). Under `night_off`, no
wording implies that the exposure has ended. This replaces the parenthesis in
§5.4 item 1.

**C3. Where precedence applies.** The precedence rule in §5.7 combines
night-level outcomes: the precipitation veto, the unknown-precipitation veto
and freshness. It applies after the comparison tables of §5.5 and §5.6 have
produced the cloud-side verdict, and never to individual model statuses.
Every contributing cause is returned, even when another cause decides the
headline.

**C4. The coverage contract.**

- **Anchor.** Coverage is measured from the fetch time of the cached source.
  If nothing has ever been cached, it is measured from the time of the attempt.
- **Request horizon.** The main and cloud requests ask for
  `FORECAST_NIGHTS + 2` (16) forecast days.
- **When an hour is expected.** An hour is expected for a model and a field
  when the timestamp its value comes from is no later than the earlier of:
  - fetch + the declared coverage;
  - the last timestamp the request asks for. This is computed from the
    request's parameters and the fetch time, never from the response's time
    axis.

  For instantaneous fields the value comes from the hour's start. For
  preceding-hour fields it comes from the hour's end. Expected coverage is
  never derived from which values happen to be present.
- **A whole missing response** inside declared coverage leaves those hours
  expected-missing. The night is then Not enough data where those hours
  decide, and it never falls back.
- **The main forecast** beyond its reach is unknown, never "not expected".
- **The fallback** has its own coverage. If the fallback is not expected
  either, the night is Not enough data.
- **§5.2's test.** Use the simpler sufficient test: any expected-missing hour
  in the interval makes the status unresolved.

**C5. The cache contract.**

- A cached cloud row without the new fields (model amounts, NBM keys and their
  metadata pair) is obsolete and is refetched within its TTL.
- Truncation is detected per model and per field, from the last non-null
  value against the expected coverage of C4. It is not detected from the
  shared time axis.
- A repair refetch within the TTL happens at most once per source per hour,
  per location, and concurrent attempts are coalesced. Polling every minute
  therefore cannot hammer Open-Meteo.

**C6. Parsing.** Each model's total cloud, cloud layers and amount are parsed
independently. Today one missing layer key drops that model's whole series.

**C7. Which sources count for freshness.**

- The main forecast always counts.
- The cloud row counts whenever any of these holds, fallback nights included:
  - ECMWF is the primary;
  - a comparison model is expected;
  - "Any model" amounts fall in the interval.
- Context sources (water vapour, aerosol, metadata, the NBM series) never make
  a verdict stale. Unusable or stale period evidence makes the chance period
  unknown instead (C9).

**C8. Metadata storage.**

- Raw `meta.json` for the four domains is stored as one JSON object in a new
  `weather_cache` row (`model_meta`). This needs a migration, because the
  `source` vocabulary is a closed CHECK.
- **Writing.** The metadata row is written in the same transaction as the
  cloud row, with the same full-precision `fetched_at`.
- **Reading.** Both rows are read in one statement, so the pair always comes
  from one committed write.
- **Pairing.** The metadata pairs with the cloud row only when the
  `fetched_at` values are equal and the metadata's recorded SHA-256 matches
  the cloud payload. The hash is a second check, not the identity.
- **Failure.** A failed metadata fetch deletes the old metadata row in the
  same transaction. If anything does not match, the metadata is
  "unavailable".

**C9. The chance period must not depend on comparing values.** If it did,
erasing one value could flip the regime and loosen other hours' limits,
breaking §5.10. The regime is decided as follows:

- **Clearly outside NBM's grid**, every period is **hourly**. The grid is
  NBM's own CONUS grid as Open-Meteo's NBM metadata defines it: a Lambert
  conformal projection on a sphere (R = 6 371 200 m), standard parallel 25°,
  central meridian −95°.
  - Its outer grid-point centres are at (19.228985°, −126.27699°) and
    (54.372913°, −59.042786°), with 2 345 × 1 597 points.
  - Open-Meteo picks the nearest grid point, so a location up to half a cell
    beyond an outer centre still gets NBM data.
  - "Clearly outside" therefore means more than two cells (≈ 5 km) beyond the
    outer centres. Any location within that edge band is treated as inside the
    grid.
  - The footprint is fixed constants and does not need metadata at run time.
- **Inside the grid, with NBM keys present and carrying values in a current
  cloud response**, NBM is available. *Routing assumption* (observed at CONUS
  sites, 2026-10-17): the main forecast's chance is NBM's. Under that
  assumption, up to NBM's declared coverage (10 days):
  - **hourly** until NBM initialisation + 36 h − one update interval;
  - **unknown** within ± one update interval of that boundary;
  - **6-hour blocks** after it, aligned to 00/06/12/18 UTC and stored with
    explicit UTC bounds;
  - **unknown** beyond NBM's coverage.
- **Anywhere else inside the grid**, the period is **unknown** and the lower
  limit applies. That covers:
  - NBM keys absent;
  - a failed, obsolete or stale cloud row;
  - a stale main forecast;
  - missing, unusable or unmatched metadata (C8);
  - main-forecast and cloud rows fetched more than an hour apart.

Evidence:

- **Grid size, 2026-10-18:** the projected corners span 2344 × 1596 cells at
  2.54 km, matching NBM's 2.5 km CONUS grid.
- **Probes, 2026-10-17 and 18:** 22 points, all classified correctly by the
  footprint.
  - NBM had values inside the grid at Phoenix, Toronto, Vancouver, Edmonton,
    Monterrey, Halifax, Seattle and Miami.
  - NBM keys were absent, and the points lie outside the grid, at Anchorage,
    Honolulu, San Juan, Mexico City, Bermuda, London, St John's and seven
    edge points.
- **Run timing, 2026-10-18:** NBM runs hourly (update interval 3 600 s).
  - At Seattle, Miami and Denver the chance varied hour to hour until about
    init + 36 h, and was constant in each aligned 6-hour block after that.
  - The 00Z stamp groups with the block covering 18–24Z, which is the
    preceding-hour convention.

**C10. The resolution indicator is approximate.** It reads "Cloud data may be
6-hourly from about hh:mm" and is informational only.

- **With metadata:** the boundary is the latest 00 or 12 UTC ECMWF
  initialisation at or before `last_run_initialisation_time`, plus 144 h. On
  2026-10-17 the latest 18z run ended at init + 147 h, so the 6-hourly tail
  comes from an earlier 00/12z run.
- **Without metadata:** the boundary is fetch + 136 h.

**C11. Session states and displayed states.** Under `night_off`, the hour
states that feed the cloud-side verdict V (§5.5–§5.7) exclude precipitation,
because precipitation is handled only by the vetoes. The displayed hour state
and the display conditions still include it, so a wet hour never shows as
clear.

**C12. Interval totals** read "Forecast-hour sum ≥ 0.3 mm; 2 hours missing".
They are summed over the forecast hours that touch the interval, never
prorated. Any time range shown names those hour bins.

**C13. Cloud details carried over from the cloud-layer consensus.**

- **The §9 case "ECMWF total missing in an expected hour"** uses a fixture
  where that hour decides the outcome.
- **The neutral layer advisory stays**, in the night-details checklist only.
  It is shown when all three of these hold:
  - ECMWF is primary;
  - its total passes the limit;
  - an estimated layer is over the limit in dark hours still to be judged.

  Example: "High-cloud estimate up to 44%; total cloud 3–8%, 02:00–04:00
  (limit 20%) — not counted toward the verdict." It has no effect on the
  verdict, the strip or the Tonight card.

**C14. Timestamps.** Every reason, period and boundary in the response
carries full UTC timestamps alongside its display labels, so repeated local
times on DST nights stay distinct. The response also carries `evaluated_at`.

**C15. Re-evaluation and stale results in the browser.**

- **Refresh.** Weather and Tonight share one query policy:
  - refetch every 60 s while the page is visible;
  - refetch at once when focus or visibility returns;
  - hidden mounted pages do no duplicate work.
- **Not current.** On the browser's own clock, a result older than 3 minutes
  is marked **not current**, whatever the state of the request. A failed
  refresh is reported at once.
- **How a stale result reads.** It shows as "Last result: Go — not current",
  in text, without the normal affirmative Go presentation. The 3-minute
  threshold is Claude's choice.
- **No verdicts in the browser.** The frontend never computes a verdict of
  its own.

A warm, cached forecast request takes about 110 ms (measured 2026-10-17).

**C16. Fractional-offset time zones.**

- The strip's geometry is unchanged.
- Column labels and the darkness band come from the actual timestamps, so
  they line up at offsets such as +5:30 or +5:45.
- Tooltips on repeated local times carry the offset.
- Tests cover UTC+5:30, UTC+5:45 and a zone with a fractional offset and DST.

**C17. Testing the guarantee.** Layered tests replace the infeasible 3²⁴
all-night case. Single-erasure preservation extends to any number of removals
by induction.

- **Short session:** exhaustive, through the production evaluator.
  - The case is 3 models, 3 hours and R = 2 h: 19 683 assignments, each
    evaluated once.
  - Every single erasure (118 098) is checked against that table.
- **All night, by counts:** each model reduces to its counts of (pass, fail,
  unknown). That is 91 125 three-model classes. The reduction is sound only
  with the interruption limit off and equal hour durations.
- **All night, sequences:** all 6 561 eight-hour sequences, with every erasure
  of each, go through the session kernel.
- **The combiner:** checked over every attainable tuple of model statuses.
- **End to end:** deterministic, seeded stdlib cases run through the evaluator.
  They cover:
  - partial coverage, absent sources and fallback;
  - both precipitation policies and unequal chance limits;
  - lost metadata, split darkness, stale sources and 23- or 25-hour nights;
  - erasure of raw values before normalization.
- **Runtime:** under 60 s on one core. No new dependency. The enumerations run
  inside a few tests rather than as parametrized cases, because each
  parametrized case would rebuild the database fixture.

### Fred's decisions

**F1. Saved rules are discarded, not migrated** (Fred, 2026-10-18). This
replaces §7.

- The rules table was added on the unreleased v0.41.9 branch, so no released
  install has saved rules.
- The next migration therefore recreates the table empty, with the new schema
  (share range 1–100%, the new precipitation fields).
- Every location then uses the default rules and shows the presets until its
  rules are saved again.
- Nothing else in the database changes.

**F3. One precipitation-chance limit; no hour-or-block distinction** (Fred,
2026-10-18, after seeing the implementation). This overrides §4.3's two chance
limits and "Establishing the period", the "period" column of §2, C9, the block
spans and "period unknown" marks of §6.3, and the related §9 cases.

- **Why.** The distinction could not be explained to Fred in plain words, and
  he judged users would understand it even less. A rendered night showed "?"
  on every hour, which meant nothing to him.
- **The setting.** There is one setting, "Maximum precipitation chance (%)".
  It applies to every hourly value as reported, near or far.
- **Help.** One sentence of help explains that further ahead, the forecast
  gives one chance per 6-hour stretch and repeats it in each hour.
- **Display.** The chance row shows plain numbers: no marks and no merged
  cells.
- **Code removed.** The code that classified values as hourly or block, and
  the NBM series it needed, are removed.
- **Data.** The stored per-period limit is dropped. Saved rules keep their
  single limit.

**F2. "Longest interruption"** (§6.5) is adopted (Fred, 2026-10-18). It
replaces his earlier "Longest cloudy stretch", because a stretch counts any
failing or unknown hour, not only cloudy ones.

**F4. Users choose the cloud forecasts, and by default the majority decides
each hour** (Fred, 2026-10-18, after Claude and Codex agreed the design).
This amends §5.2–§5.6 and C4.

- **Why.** Any disagreement made a night Uncertain. With the preset rules, 8
  of 14 nights at Fred's location came out Uncertain, which left too little to
  decide on.
- **Settings.**
  - **"Cloud forecasts":** ECMWF, GFS and ICON, at least one, all three by
    default.
  - **"Preferred cloud forecast":** one of the ticked ones, ECMWF by default.
  - **"When forecasts differ":** "Majority for each hour" (the default) or
    "Show Uncertain".
  - The last two are hidden when one forecast is ticked.
- **Majority for each hour.**
  - For each hour, the cloud check follows most of the ticked forecasts that
    reach that hour; a tie goes to the preferred one.
  - If the preferred forecast doesn't reach the hour, the first ticked one
    that does breaks ties (ECMWF, then GFS, then ICON).
  - If no ticked forecast reaches the hour, Open-Meteo's default forecast is
    used, and named.
  - A missing value is counted once as cloudy and once as clear. If the two
    disagree, the hour is unknown, so erasing data still never creates a Go.
  - The night is then judged on that one hourly sequence, like a single
    forecast, so a short session's window is one the majority supports hour
    by hour.
  - Uncertain does not occur from disagreement; the number of hours where the
    forecasts differ is shown in night details.
- **Show Uncertain.** Today's algorithm, using the ticked forecasts and the
  preferred one, with the same substitution rule when the preferred forecast
  doesn't reach the night.
- **Precipitation is unaffected.** The ticked cloud forecasts do not change the
  precipitation-amount check; its "any model" choice still checks ECMWF, GFS
  and ICON.
- **Defaults and data.** New rules, every preset and saved rules all start on
  all three forecasts, ECMWF preferred and the majority.
- **Rejected.**
  - A per-night vote: two forecasts can each support a session at different
    hours, with no hour that most of them support.
  - A third "follow the preferred forecast" choice: ticking only that forecast
    does the same, since unticked forecasts still show in night details.
