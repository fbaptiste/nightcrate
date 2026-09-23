# Imaging-quality model — design rationale and sources

Scope: `backend/src/nightcrate/services/imaging_quality.py`, the per-hour 0–100
"imaging quality" score in the weather panel. Shipped in v0.41.4, replacing a
model in which cloud was an additive term.

This is the reasoning and the sourcing behind the model, kept because the
constants are judgement calls and the next person to touch them needs to know
which ones rest on a citation and which do not. The worked examples in §4 are
reproduced as pinned tests in `backend/tests/test_imaging_quality.py`.

---

## 0. The bug, and what actually causes it

Reported: 100% total cloud cover scores 46 ("Marginal"). Requirement: 100% cloud
is unusable, full stop.

The 0.6 high-cloud weight is the proximate cause but not the root cause. The
root cause is structural: cloud enters the old model as an additive *term*
(`sky_clarity × 0.35`) with a `sqrt` "gating" on the rest. Any weighted sum with
cloud as a term has a floor, and `sqrt(0.4) = 0.63` lets 63% of the other credit
through at sky clarity 40. Consequences beyond the reported rows:

- 60% cirrus (the 19:00 row) scores 60 "Good". That row is as wrong as the
  100% rows.
- 100% high cloud with every other factor perfect scores **55 "Good"**.
- 80% high cloud with every other factor perfect scores 65 "Good".
- 50% low cloud with the example-night factors scores 53 — nearly "Good".

Tuning the constant cannot fix this. Cloud has to be a gate, not a term.

---

## 1. The model

```
score        = 100 × availability × quality

availability = darkness × precip_gate × wind_gate × (1 − cloud)^k        ∈ [0, 1]
quality      = moon_factor × (0.45·seeing + 0.40·transparency + 0.15·wind_calm) / 100
```

### Two questions, two numbers

"Can I image at all?" and "how good will the data be if I can?" are different
questions, and a single weighted sum conflates them. The model answers them
separately and multiplies:

- **Availability** — expected fraction of the hour that yields keepable
  sub-frames. A *product*, so any closed gate zeroes it, and cloud enters as a
  yield curve that is exactly 0 at 100% cover. No structure downstream can
  rescue a zero.
- **Quality** — expected quality of the sub-frames you do keep. *Additive* on
  purpose: seeing, transparency and wind each degrade data, but none alone makes
  a night unimageable, which is exactly what a weighted mean encodes.

Both halves are returned, plus the per-factor rows, so the UI can show "0 — but
quality would have been 67" for a cirrus night.

### Reading the number

`score / 100` is expected useful data as a fraction of a perfect hour. Summed
over the night it is "equivalent hours of good data", which is the number that
belongs next to the go/no-go decision (`expected_useful_hours()` in the module).
Hours outside darkness contribute 0 automatically.

### Gates (multipliers on availability, floor 0)

| Gate | Behaviour |
|---|---|
| darkness | Fraction of the hour inside astronomical darkness, 0–1, supplied by the caller. No astronomical darkness → 0 for every hour. |
| precipitation | Any precipitation amount > 0 closes the hour. Probability ramps 1 → 0 linearly across 40% → 70%. Either input may be absent. |
| wind | Sustained 10 m wind ramps 1 → 0 across 40 → 60 km/h. Absent input disables the gate; the `wind_calm` quality term still applies. |

### Cloud yield curve

```
cloud = max(total, low, mid, high)  over whatever is available
yield = (1 − cloud) ^ k,   k = 1.5
```

Taking the max makes the result robust to an inconsistent feed (a model's total
should already be ≥ each layer) and monotonic in every input: adding cloud to
any layer can never raise the score, even if the total field doesn't move.

If the total is missing it is estimated from the layers with random overlap,
`1 − Π(1 − f_l)` — the conservative (higher) estimate — and flagged. If no cloud
figure at all is present the function raises: an hour cannot be scored without
cloud data, and treating "unknown" as "clear" would be worse than failing.

Yield at k = 1.5:

| cover % | 0 | 10 | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| yield | 1.00 | 0.85 | 0.72 | 0.59 | 0.46 | 0.35 | 0.25 | 0.16 | 0.09 | 0.03 | 0.00 |

### Quality terms (weighted mean)

seeing 0.45, transparency 0.40, wind_calm 0.15. Same weights in both modes.

### Moon (multiplier on quality with a floor)

Normal mode: `moon_factor = 0.35 + 0.65 × moon/100`. A full moon up all hour
keeps ~⅓ of a broadband hour's value. It is a floor and not a gate because bright
targets survive moonlight; target–moon separation belongs in the target planner,
not here. Narrowband mode: factor is 1 (moon ignored).

### Labels

`Unusable` when availability < 0.10 (≈ 78% cloud at k = 1.5, or any closed
gate), regardless of the quality half. Otherwise Excellent ≥ 75, Good ≥ 50,
Marginal ≥ 25, Poor below. Re-thresholded from the old 80/55/30 because the scale
now means something different.

### Monotonicity

More cloud never raises the score (yield is `(1 − f)^k`, k > 0, on the max of
all cover figures). Every sub-score enters with a non-negative weight. Every gate
is non-increasing in its input. The examples script sweeps cloud, each sub-score,
and "layer added while total unchanged"; all pass.

---

## 2. Cloud-layer treatment — what it rests on

### Sourced

- Open-Meteo layer definitions: low = up to 3 km, mid = 3–8 km, high = from
  8 km; `cloud_cover` is total as an area fraction. Pressure-level cloud cover is
  approximated from relative humidity (Sundqvist et al. 1989). The high-cloud
  field is therefore a *coverage* figure, not an opacity figure.
- Cirrus optical-depth classes (Sassen & Cho 1992): subvisual τ < 0.03, thin
  0.03–0.3, opaque 0.3–3. Extinction in magnitudes is 1.086·τ, so anything past
  "thin" costs ≥ 0.33 mag and comes with structure (halos, gradients).
- Mid-latitude lidar climatology (Thessaloniki, multi-year): of detected cirrus,
  ~10% subvisible, ~49% thin, ~41% opaque; mean optical depth 0.37 ± 0.18.
- ESO's "Clear" observing category already requires < 10% of the sky covered and
  transparency variations under 10%; "Thin cirrus" is anything above 10%.
- Gemini's "patchy cloud / thin cirrus" bin assumes extended cirrus attenuates by
  up to 0.3 mag (T ≈ 75%).
- Tools built for astronomers already treat cirrus as night-killing: Clear Sky
  Chart's distinguishing feature is its cirrus modelling, because a cirrus load
  sufficient to lose the night is still "clear" in civil forecasts; meteoblue's
  astronomy page warns that partial high-cloud coverage can fully block star
  visibility.

### Judgement calls (labelled as such)

**No partial credit for high cloud.** The physically "truer" model would give
frames under thin cirrus a non-zero keep probability. It is not used because:
(a) the forecast cannot distinguish thin from opaque — it reports coverage from
RH; (b) the requirement rules out a floor; (c) a floor is exactly what produced
the bug. So coverage from every layer counts fully toward obscuration. Layer
composition drives only the `HIGH_CLOUD_ONLY` advisory (high ≥ 50%, combined
low+mid ≤ 10%).

**k = 1.5.** k = 1 would mean lost time equals covered fraction. The extra
accounts for exposures spanning cloud passages, guider/focus recovery and dither
settling. 10% → 0.85 is consistent with ESO's < 10% "clear"; 20% → 0.72 keeps a
20% cirrus night worth imaging; 60% → 0.25 makes it not. 1.5–2.0 is the
defensible range. It is one constant, and monotonicity holds for any k > 0.

**100% high cloud → 0, with an asterisk.** By the climatology above, a 100%-high
forecast is a lost night roughly nine times in ten, and the forecast can't say
which night is the tenth. The score is 0 as required; the `HIGH_CLOUD_ONLY`
flag exists so the UI can say "check satellite IR before writing this off." That
is the one situation where a 0 deserves an annotation.

**Transparency is not detecting the cirrus.** It is derived from PWV, AOD,
humidity and visibility; none of those measures cloud. Upper-air moisture
correlates with cirrus, so transparency reads low on cirrus nights as a proxy,
not as a detection. In this structure that is fine: cloud removes frames,
transparency dims the ones you keep, and the two multiply rather than sum. At
partial cover there is mild double-counting through the correlation. If that
matters later, the fix is upstream in the transparency derivation, not here.

**Precipitation ramp 40 → 70%, wind gate 40 → 60 km/h, moon floor 0.35, dew
advisory at ≤ 2 °C spread, `Unusable` at availability < 0.10, labels 75/50/25.**
Calibration choices, exposed as module constants. The score's structure and
monotonicity do not depend on them.

---

## 3. Reference implementation

`imaging_quality.py` — Python 3.14-clean, standard library + `math`, keyword-only
arguments, frozen dataclasses, no I/O.

Public surface:

- `score_hour(...) -> ImagingQuality` — the per-hour function.
- `effective_cloud_fraction(...)` and `cloud_yield(...)` — the cloud half,
  separately testable.
- `expected_useful_hours(results)` — night summary, Σ score/100.
- `Mode` (NORMAL / NARROWBAND), `Role` (GATE / YIELD / QUALITY / MODIFIER),
  `Flag` (machine-readable advisories).

Result shape:

```
ImagingQuality
  score         int, 0–100
  label         str
  availability  float, 0–1
  quality       float, 0–100
  mode          Mode
  factors       tuple[FactorScore, ...]
  flags         tuple[Flag, ...]

FactorScore
  key      "darkness" | "precipitation" | "wind_gate" | "cloud" |
           "seeing" | "transparency" | "wind_calm" | "moon"
  role     Role
  value    float | None   — the 0–100 figure to display; every row reads
                            higher-is-better (cloud shows clear-sky %,
                            precipitation shows dry %)
  effect   float          — GATE/YIELD/MODIFIER: the multiplier applied;
                            QUALITY: the weight
  applied  bool           — False when ignored in this mode (moon in
                            NARROWBAND) or input absent (gates)
```

Inputs (all keyword-only):

| Argument | Notes |
|---|---|
| `cloud_cover`, `cloud_cover_low/mid/high` | Percent. Total may be None if any layer is present. |
| `seeing`, `transparency`, `wind_calm`, `moon` | 0–100 sub-scores, higher is better, derived upstream. Required. |
| `darkness` | 0–1 fraction of this hour in astronomical darkness. Default 1.0. |
| `precipitation_mm`, `precipitation_probability` | Optional. |
| `wind_speed_kmh` | Optional; enables the wind gate. |
| `temperature_c`, `dew_point_c` | Optional; advisory only, never affect the score. |
| `mode` | `Mode.NORMAL` (default) or `Mode.NARROWBAND`. |

`imaging_quality_examples.py` — transcribes the old algorithm, prints old-vs-new
tables for the real hours, boundary cases, moon/mode, and gates, and runs the
monotonicity sweep. Suitable as the seed for the test module.

### Caller responsibilities (this module cannot enforce them)

- **`moon` must be a per-hour value** — moon altitude and illumination at that
  hour. The inputs currently available upstream (darkness hours, moon-down
  hours, illumination %) are nightly. A post-moonset clearing scores wrong with a
  nightly figure.
- **`darkness` must be computed per hour** from sun altitude. How nautical
  twilight is treated for narrowband is the caller's decision; the module gates
  identically in both modes.
- Pass `precipitation_*` and `wind_speed_kmh` through from the forecast so the
  gates are live.

### UI implications

- Group or colour rows by `Role`; hide gate rows with `applied=False` if
  preferred.
- `Unusable` is a distinct label, not the bottom of the old scale.
- Map `Flag` values to display text in the UI; the module carries no strings
  meant for users. `HIGH_CLOUD_ONLY` is the one that deserves a call-to-action.
- Optional: show `availability` and `quality` alongside the score, and
  `expected_useful_hours` for the night.

---

## 4. Worked examples

Supporting factors for the five real hours were reconstructed inside the stated
ranges (seeing 83–91, transparency 40–42, moon 100, wind calm 48–95) so the old
algorithm reproduces the reported scores to ±1.

### Five real hours, normal mode

| Hour | L/M/H/T | Old | New | Availability | Quality | Flags |
|---|---|---|---|---|---|---|
| 19:00 | 0/0/60/60 | 60 Good | **16 Poor** | 0.25 | 61.5 | high_cloud_only |
| 20:00 | 0/0/100/100 | 46 Marginal | **0 Unusable** | 0.00 | 67.4 | overcast, high_cloud_only |
| 21:00 | 0/0/100/100 | 47 Marginal | **0 Unusable** | 0.00 | 70.0 | overcast, high_cloud_only |
| 22:00 | 0/0/100/100 | 42 Marginal | **0 Unusable** | 0.00 | 60.5 | overcast, high_cloud_only |
| 04:00 | 0/17/100/100 | 34 Marginal | **0 Unusable** | 0.00 | 67.9 | overcast |

(04:00 has 17% mid cloud, so the high-cloud-only advisory correctly does not fire.)

### Boundary cases

"Ideal" = all supporting factors 100 (isolates cloud). "Example night" = seeing
90, transparency 41, wind 70, new moon.

| Case | L/M/H/T | Old (ideal) | New (ideal) | New (example night) |
|---|---|---|---|---|
| Perfectly clear | 0/0/0/0 | 100 Excellent | 100 Excellent | 67 Good |
| 100% low | 100/0/0/100 | 0 Poor | 0 Unusable | 0 Unusable |
| 100% high | 0/0/100/100 | 55 Good | 0 Unusable | 0 Unusable |
| 50% high | 0/0/50/50 | 79 Good | 35 Marginal | 24 Poor |
| 50% low | 50/0/0/50 | 63 Good | 35 Marginal | 24 Poor |
| 20% high | 0/0/20/20 | 92 Excellent | 72 Good | 48 Marginal |
| 80% high | 0/0/80/80 | 65 Good | 9 Unusable | 6 Unusable |
| Total only, 30% | –/–/–/30 | 79 Good | 59 Good | 39 Marginal |

### Moon and mode — clear sky, seeing 90, transparency 80, wind 80

| Moon sub-score | Normal | Narrowband |
|---|---|---|
| 100 | 85 Excellent | 85 Excellent |
| 50 | 57 Good | 85 Excellent |
| 0 | 30 Marginal | 85 Excellent |

### Gates — baseline 10% high cloud, seeing 90, transparency 80, wind 80, new moon

| Case | Score | Availability | Flags |
|---|---|---|---|
| Baseline | 72 Good | 0.85 | – |
| No astronomical darkness (polar summer) | 0 Unusable | 0.00 | no_darkness |
| Half the hour in darkness | 36 Marginal | 0.43 | – |
| Precipitation probability 55% | 36 Marginal | 0.43 | – |
| Precipitation probability 80% | 0 Unusable | 0.00 | precipitation |
| 0.2 mm precipitation | 0 Unusable | 0.00 | precipitation |
| Wind 50 km/h sustained | 36 Marginal | 0.43 | – |
| Wind 65 km/h sustained | 0 Unusable | 0.00 | wind_gate |
| Dew spread 1.5 °C | 72 Good | 0.85 | dew_risk |
| Layers missing, total 40% | 39 Marginal | 0.46 | layers_unavailable |
| Total missing, layers 30/0/30 | 29 Marginal | 0.34 | total_estimated |

Monotonicity sweep: all pass.

---

## 5. Other things the old model gets wrong

- **Moon is night-level.** See caller responsibilities above.
- **No darkness gate.** Twilight hours score the same as dark ones.
- **Precipitation is ignored entirely.**
- **Wind cannot close an hour.** ~90 at 60 km/h with everything else perfect.
- **Dew-point spread unused.** Now an advisory flag; it's a preparation issue,
  not go/no-go.
- **Old "Marginal ≥ 30"** covered everything from "hazy but fine" to "60%
  overcast"; the label carried no decision information.

---

## 6. Calibration constants (defaults set; change in one place)

All in the module header, each with its rationale in the docstring:

| Constant | Default | Note |
|---|---|---|
| `CLOUD_YIELD_EXPONENT` | 1.5 | 1.5–2.0 defensible |
| `QUALITY_WEIGHTS` | 0.45 / 0.40 / 0.15 | seeing / transparency / wind_calm |
| `MOON_FLOOR` | 0.35 | normal mode only |
| `PRECIP_PROBABILITY_RAMP` | 40 → 70 % | |
| `WIND_GATE_RAMP_KMH` | 40 → 60 km/h | rig-dependent; a per-rig setting is a plausible later refinement |
| `UNUSABLE_AVAILABILITY` | 0.10 | ≈ 78% cloud at k = 1.5 |
| `LABEL_THRESHOLDS` | 75 / 50 / 25 | |
| `HIGH_CLOUD_ONLY_*` | high ≥ 50, low+mid ≤ 10 | advisory trigger |
| `DEW_RISK_SPREAD_C` | 2.0 | advisory trigger |

---

## Sources

- Open-Meteo forecast API docs (layer definitions, total as area fraction, RH-based
  pressure-level cloud cover): https://open-meteo.com/en/docs
- ESO observing-condition definitions (Photometric / Clear / Thin cirrus / Thick):
  https://www.eso.org/sci/observing/phase2/ObsConditions.html
- Gemini Observatory site conditions (thin-cirrus attenuation assumption):
  https://www.gemini.edu/observing/telescopes-and-sites/sites
- Sassen & Cho (1992) optical-depth classes, as summarised in Sassen et al. 2008,
  JGR: https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2008JD009972
- Mid-latitude cirrus climatology (subvisible / thin / opaque fractions, mean τ):
  Atmos. Chem. Phys. 20, 4427–4444 (2020):
  https://acp.copernicus.org/articles/20/4427/2020/acp-20-4427-2020.pdf
- Clear Sky Chart background (cirrus vs. civil "clear"):
  https://en.wikipedia.org/wiki/Clear_Sky_Chart
- meteoblue astronomy-seeing page (partial high cloud can fully block stars):
  https://content.meteoblue.com/en/private-customers/website-help/outdoor-and-sports/astronomy-seeing
