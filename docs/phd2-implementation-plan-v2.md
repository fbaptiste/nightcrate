# PHD2 Analyzer Arc — Plan (v4 spec alignment, complete arc)

## Context

Spec **v4** (`docs/nightcrate-phd2-analyzer-spec-v4.md`) supersedes v3.1.
v4 is source-verified — every formula either reproduces from
PHDLogViewer's `AnalysisWin.cpp` (with line citations) or derives
from first principles with cited sources. v4 also makes one
substantive functional addition: **PE measurement is a first-class
output** with a per-section structured payload (§6.4) and per-mount-
instance accumulation (§8.6). The v3.1 plan treated PE as a chart
to eyeball; v4 makes it data.

**Throw-away directive.** The in-flight `v0.25.0/phd2-pass-d`
branch is conceptually scrapped. All PHD2-specific code on that
branch is throwaway. Three exceptions worth carrying forward as
*design ideas* (not as code that survives):

1. **Spectrum tab structure** as a sibling of Graph + Data tabs.
2. **`RigSelectBar` UI pattern** wrapping the existing
   `RigPickerMenu` + per-log rig persistence in `phd2RecentFiles`.
3. **Bug findings** that should inform the new UI design:
   - Y-axis tick labels overflowed left margin → use wider margin
     and exponential-format big numbers.
   - Empty trace state crushed the toggle row → keep toggles
     mounted independently of chart body.
   - Peak markers got cluttered at top-8 → cap at top-5 globally.

Migrations 0024 (`mount.worm_period_seconds` + view rebuild) and
the seed-CSV worm period values are correct per v4 §6.6 — these
*can* be kept in the v0.25.0+ implementation, but the implementer
may also choose to start fresh and re-add them in v0.26.0 (where
worm markers actually ship). The plan below assumes a fresh restart
because Fred's directive was unambiguous.

### CD-review revision log

This plan was reviewed by Claude Desktop after the initial v4
draft. Three real bugs and several smaller fixes were identified;
all are now incorporated into the version-section bodies below.
Summary of changes since the initial v4 plan:

**Bug fixes:**

- **v0.27.0 unguided RA filter** (§6.2 / §M1): dropped the
  `mount_kind != "Mount"` clause. PHDLogViewer's `Include()` is
  mount-kind-agnostic; AO frames with valid star data should
  accumulate. The corrected filter keeps only `ra_raw_px is None`
  and `error_code != 0`. Test #5 flipped from "AO treated like
  DROP" to "AO accumulates with valid star data."
- **v0.30.0 GA detection**: changed AND → OR. Either explicit
  `Guiding Output Disabled` events OR ≥ 90 % all-zero pulse
  pattern triggers detection (matching spec §6.3 wording).
- **v0.31.0 calibration orthogonality formula**: replaced the
  literal `|x_angle − y_angle − 90°| > 5°` with a modulus-aware
  form `abs(abs(x − y) % 180 − 90) > 5` (after folding to [0, 90]
  for the line-angle convention). The literal form fails for
  axes oriented 270° apart (returns 180° instead of 0°). CD's
  suggested Option A also breaks for the 270° wrap; the `% 180`
  modulus is the load-bearing piece.

**Scope expansion (v0.25.0 §5.2):**

- Added §5.2.2 peak (sign-preserving max-by-abs — current code
  drops the sign).
- Added §5.2.5 oscillation (treat zero values as positive per
  spec §11.14 — current code skips them).
- Added §5.2.8 frame counts + duration breakdown (added
  `duration_total_seconds` vs `duration_included_seconds`
  distinction).

**Doc / seed-data fixes:**

- v0.25.0 §M2: separated Barrett (celestialwonders.com, cited in
  PHDLogViewer source) from Starry Nights (separate community
  resource that arrives at the same coefficient empirically).
- v0.28.0 seed table: HAE29/43/69 expanded to three separate rows;
  SW Wave 100i/150i to two rows. Earlier table compressed for
  brevity but the actual seed CSV must have one row per model.
- v0.28.0 migration: added explicit `SELECT DISTINCT drive_type
  FROM mount` verification step before writing the migration
  (don't let unmapped freeform values silently fall to `'unknown'`).
- v0.32.0 `out_of_band_spectrum_peaks`: rewrote the worm-rule
  notation as explicit `in_band(p)` predicate covering ±5%
  bands at worm + first three harmonics (the previous shorthand
  `[worm/4, worm × 1.05] ∪ harmonics` was ambiguous), and added
  the explicit seeing-band exclusion at < 5 s. Heading also
  corrected from "seven" to "eight" speculative rules.

**CD-resolved open questions (Part 5 below):** scipy approved
(scipy>=1.11), MeasuredPe auto-persist, mount instance auto-
backfill with `(auto)` suffix, tier-override Protocol baked into
v0.31.0, scipy version pin confirmed.

## Part 1 — Where the v0.25.0 branch goes

**Recommended:** revert all PHD2 changes on `v0.25.0/phd2-pass-d`
back to `main`'s state, OR open a fresh branch off `main` and
abandon `v0.25.0/phd2-pass-d`. Either way, the new v0.25.0 starts
from the v0.24.0-shipped baseline.

If the implementer prefers to keep migration 0024 + seed CSV worm
periods + the Mount form `worm_period_seconds` field intact (these
are narrow correct changes), that's acceptable — they'd land in
v0.25.0 as "infrastructure already in place" rather than as new
work. The plan below assumes everything is fresh; adjust at
implementation time.

## Part 2 — Version sequence

Ten versions plus a roadmap. Each is standalone-shippable with
user-visible value.

| Version | Pass | Spec §§ | Headline outcome |
|---|---|---|---|
| **v0.25.0** | D-1 | §5.2 | **Metric foundation correction** — RMS, drift (RA + Dec), PA error, scatter ellipse rotation all switch to PHDLogViewer's exact formulas. No FFT work. |
| **v0.26.0** | D-2 | §6.1, §6.6 | **Spectrum tab v4-conformance + worm markers** — Hamming, `4/N`, Akima spline, MAD threshold, snap-to-peak, full P-P/RMS hover readouts. Worm-period markers shipped (per-rig, with heuristic fallback at 0.5″ amp threshold). |
| **v0.27.0** | D-3 | §6.2 | **Unguided RA reconstruction** — PHDLogViewer's `move = raraw − prev_raraw − prev_raguide` recurrence. Time-series overlay AND Spectrum-tab Unguided toggle ship together (paired per spec). |
| **v0.28.0** | E-1 | §6.7 | **Drive-type-aware markers** — drive_type vocabulary, strain wave per-mount seed data, hybrid mount support (HEM27/HEM44 = strain wave RA + worm Dec). Replaces v0.26.0's worm-only marker model with `PeMarker`. |
| **v0.29.0** | E-2 | §6.4, §6.8 | **Per-session measured PE + per-instance schema** — structured measured-PE output per guiding section. Schema separates `mount_model_id` from `mount_instance_id`. First SQLite tier for measured-PE history. Override behavior: ≥ 3 stable measurements supersede the manufacturer default for spectrum markers. |
| **v0.30.0** | E-3 | §6.3, §6.5 | **GA section handling + AO/Mount toggle** — completes v2 phase parity with PHDLogViewer. |
| **v0.31.0** | F | §7.1, §7.2, §7.5 | **Diagnostic engine: confident tier** — engine scaffolding, 8 confident rules (including the new `guiding_pe_suppression_low` that consumes §6.4 measured PE), settings page. |
| **v0.32.0** | G | §7.3, §7.4 | **Diagnostic engine: speculative tier + equipment-aware** — 7 speculative rules (drive-type-aware `out_of_band_spectrum_peaks`, new `strain_wave_load_balancing_recommendation`), rig-context-aware threshold scaling. |
| **v0.33.0** | H | §8.1, §8.2, §8.5 | **Multi-log comparison + trends + DB-backed history** — second SQLite tier, multi-log compare view, trend chart, DB-backed recently-analyzed list. |
| **v0.34.0** | I | §8.3, §8.4, §8.6 | **HTML report + instance PE corpus UI + catalog integration** — self-contained HTML export, per-mount-instance PE history view (the storage from v0.29.0 + the multi-session aggregation from v0.33.0), catalog integration when imaging-core lands. |
| **v0.35.0+** | J–M | §9 | **Roadmap** — debug logs, live JSON-RPC monitoring, AI session analysis, parameter recommendations. Each gets its own spec when prioritized. |

## Part 3 — Detailed plans per version

### v0.25.0 — Metric Foundation (PHDLogViewer-aligned)

**Status:** Planned (replaces the abandoned v0.25.0/phd2-pass-d work)
**Branch:** `v0.25.0/phd2-metric-foundation`
**Spec refs:** v4 §5.2.1 – §5.2.8 (the full §5.2 metric set —
post-CD-review the scope was widened from §5.2.1/3/4/6/7 to
include §5.2.2 peak, §5.2.5 oscillation, and §5.2.8 frame counts
+ duration breakdowns)

#### Goal

Replace v0.22.0's metric formulas with PHDLogViewer's exact
formulas, so NightCrate's reported numbers (RMS, drift, PA error,
scatter ellipse rotation, peak, oscillation, frame counts) match
PHDLogViewer's for the same log. This is foundational: every
subsequent version (FFT, diagnostics, trends) consumes these
metrics, so getting them aligned to the reference tool first
avoids re-justifying differences later.

#### Why it stands on its own

Corrected metrics are immediately user-visible — the Section Summary
panel's RMS, drift, and oscillation rows all update. PA error
becomes a new visible metric. Users who cross-reference NightCrate
against PHDLogViewer will see matching numbers post-merge.

#### Scope

The v0.22.0 implementation has these formulas wrong (or missing)
relative to PHDLogViewer:

##### §5.2.1 — RMS as standard deviation

Current implementation (`backend/src/nightcrate/services/phd2_metrics.py`):
```python
def _rms(values: list[float]) -> float | None:
    if not values:
        return None
    return math.sqrt(sum(v * v for v in values) / len(values))
```

This is RMS-from-zero (`sqrt(mean(x²))`). PHDLogViewer uses
**standard deviation** (`sqrt(mean((x - x̄)²))`). The two differ
when there's a systematic offset — sustained Dec drift, calibration
centroid offset.

Per `AnalysisWin.cpp` line ~190:
```cpp
LFit fitrd;
for (auto it = entries.begin(); it != entries.end(); ++it) {
    const GuideEntry& e = *it;
    if (!Include(e)) continue;
    fitrd.data(e.raraw, e.decraw);
    ...
}
rms_ra = sqrt(fitrd.varx);
rms_dec = sqrt(fitrd.vary);
```

`LFit::varx` is the population variance (West-incremental form).
RMS is therefore standard deviation. **Mathematical form (M1
below):**

$$\text{RMS}_{\text{RA}} = \sqrt{\frac{1}{N}\sum_{i=1}^{N}(x_i - \bar{x})^2}$$

NOT:

$$\sqrt{\frac{1}{N}\sum_{i=1}^{N}x_i^2}$$

##### §5.2.3 — RA drift via corrections-subtraction

Current implementation: least-squares regression slope of `ra_raw_px`
vs `time_seconds`, then × 60 for px/min.

PHDLogViewer's algorithm (`AnalysisWin.cpp` lines ~135-160) is
materially different:

```
ra0, t0 = first included frame's (raraw, dt)
ra1, t1 = last included frame's (raraw, dt)
sum = Σ e.raguide for e where e.included ∧ e.radur ≠ 0  (signed)
RaDrift_px_per_sec = (ra1 − ra0 − sum) / (t1 − t0)
drift_ra_px_per_min = RaDrift_px_per_sec × 60
```

The intuition: total raw position change = total mount drift +
total guide correction. The least-squares slope on its own doesn't
back out the correction contribution; PHDLogViewer's form does.
For a section where the guide algorithm successfully damped the
drift, our least-squares slope undershoots the true mount drift
because the corrections themselves *are* the drift signal.

Note the algorithm uses `e.included` (not the stricter `Include(e)`)
when summing corrections — DROP frames that have valid
RAGuideDistance values still contribute to the sum. This is a
subtle but intentional design choice in PHDLogViewer.

##### §5.2.4 — Dec drift via unguided-frames-only accumulation

Current implementation: same least-squares slope as RA on
`dec_raw_px`.

PHDLogViewer's Dec algorithm (`AnalysisWin.cpp` lines ~110-135) is
fundamentally different from RA, because Dec is typically guided
in only one direction (or both directions with backlash) — summing
corrections doesn't work cleanly. Instead it accumulates Dec
position changes only across frames where the previous frame was
unguided (decdur == 0). Those frames reflect actual sky drift, not
algorithm reactions:

```
y_accum = 0
prev_y = first_included.decraw
prev_guided = (first_included.decdur != 0)
LFit fit
fit.data(first_included.dt, 0)

for each subsequent included frame:
    if not prev_guided:
        y_accum += (decraw − prev_y)
        fit.data(this.dt, y_accum)
    prev_y = decraw
    prev_guided = (decdur != 0)

DecDrift_px_per_sec = fit.B()              # regression slope
drift_dec_px_per_min = DecDrift × 60
```

Where `fit.B() = covxy / varx` (linear regression slope). This is
the §M3 derivation in the math appendix.

##### §5.2.6 — PA error as per-section metric

Currently: not computed at section level. (PA error is in our
v0.27.0 diagnostic plan as a *rule input*, but per v4 spec it's a
basic per-section metric in v1.)

Formula per `AnalysisWin.cpp` line ~166:

```cpp
double PolarAlignError(const GuideSession& session) {
    return 3.8197 * fabs(session.drift_dec) * session.pixelScale / cos(session.declination);
}
```

Where:
- `session.drift_dec` is in pixels/min (already × 60'd from §5.2.4)
- `session.pixelScale` is arcsec/pixel
- `session.declination` is in radians (cos-corrected for Dec
  foreshortening away from celestial equator)

Output: arcminutes of PA error. The 3.8197 = 60 / 15.71
derivation (Barrett's formula re-expressed for px/min input) is
in §M2 below.

**Pre-conditions for PA computation:**
- Section is guiding (calibration sections excluded)
- `declination_deg` is known on the header
- `drift_dec_px_per_min` is computable (≥ 2 non-None Dec samples
  with `decdur == 0` per the §5.2.4 algorithm)
- `pixel_scale` is known on the header

When any pre-condition fails, PA error = `None`; UI shows "PA
error: not available" instead of a number. This is consistent
with v1's never-coerce-missing-data principle.

##### §5.2.7 — Scatter ellipse rotation (Theta = atan2(covxy, varx))

Currently (`components/phd2/ScatterPlot.tsx`): the ellipse axes
are computed via 2×2 covariance matrix eigen-decomposition (closed-
form principal-component rotation: `θ = ½ × atan2(2·covxy, varx − vary)`).

PHDLogViewer's `LFit::Theta` (line ~95) uses a **simpler form**:

$$\theta = \text{atan2}(\text{cov}_{xy}, \text{var}_x)$$

Per `AnalysisWin.cpp` lines ~210-240, after computing θ, the
rotated coordinate variances are computed by re-iterating samples:

```cpp
double cost = cos(theta), sint = sin(theta);
LFit fitxy;
for each included frame:
    double dr = e.raraw − avg_ra;
    double dd = e.decraw − avg_dec;
    double x_rot = dr * cost + dd * sint;
    double y_rot = dd * cost − dr * sint;
    fitxy.data(x_rot, y_rot);

lx = sqrt(fitxy.varx);   // sigma along major axis
ly = sqrt(fitxy.vary);   // sigma along minor axis
elongation = (lx + ly > 1e-6) ? abs(lx − ly) / (lx + ly) : 1.0
```

The `θ = atan2(covxy, varx)` form gives a rotation that's close to
but not identical to PCA when the data ellipse isn't highly
elongated. **NightCrate adopts PHDLogViewer's form for cross-tool
consistency** even though it's not the textbook PCA rotation.

##### §5.2.2 — Peak (sign-preserving max-by-abs)

Per `AnalysisWin.cpp` line ~196:

```cpp
if (fabs(e.raraw) > fabs(peak_r)) peak_r = e.raraw;
if (fabs(e.decraw) > fabs(peak_d)) peak_d = e.decraw;
```

The peak is the most-extreme value (positive or negative) by
absolute value, with the **sign preserved**. So if RA values are
`[+0.3, -0.5, +0.4]`, peak_ra = `-0.5`, not `0.5`.

**Current implementation** (`backend/src/nightcrate/services/phd2_metrics.py`):

```python
peak_ra = max((abs(v) for v in ra_raw), default=None)
```

This drops the sign. Bug per CD review. Fix:

```python
def _signed_peak(values: list[float]) -> float | None:
    if not values:
        return None
    return max(values, key=abs)  # max-by-abs preserves sign
```

##### §5.2.5 — Oscillation (count zero values as positive)

Per spec v4 §5.2.5 + §11.14:

$$\text{ra\_oscillation} = \frac{|\{i : \text{sign}(\text{RARawDistance}[i]) \neq \text{sign}(\text{RARawDistance}[i-1])\}|}{N - 1}$$

Spec §11.14 explicitly notes: *"Frames where x_i = 0 (which is
rare) are conventionally treated as positive for this calculation."*

**Current implementation:**

```python
def _oscillation_rate(values: list[float]) -> float | None:
    nonzero = [v for v in values if v != 0]
    if len(nonzero) < 2:
        return None
    flips = sum(1 for a, b in zip(nonzero, nonzero[1:], strict=False) if (a > 0) != (b > 0))
    return flips / (len(nonzero) - 1)
```

This **skips zero values entirely**, which is a divergence from
spec. Fix: don't skip zeros; treat zero as positive. The spec's
convention is consistent across PHDLogViewer's `RaOsc` reporting.

```python
def _oscillation_rate(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    # Treat 0.0 as positive per spec §11.14 convention
    signs = [1 if v >= 0 else -1 for v in values]
    flips = sum(1 for a, b in zip(signs, signs[1:], strict=False) if a != b)
    return flips / (len(values) - 1)
```

##### §5.2.8 — Frame counts and duration breakdown

Per spec v4 §5.2.8, the counts and durations to expose:

```
total_frames           = section's frame count
included_in_stats      = | { i : Include(i) ∧ ¬in_settle ∧ ¬user_excluded } |
excluded_by_settle     = | { i : in_settle(i) } |
excluded_by_user       = | { i : ¬included_user(i) } |
excluded_by_drop       = | { i : ¬StarWasFound(err_i) } |

duration_total_sec     = last_frame.Time − first_frame.Time
duration_included_sec  = sum of frame intervals where Include(i) ∧ ¬in_settle ∧ ¬user_excluded
```

**Current implementation** has:
- `frame_count_total`
- `frame_count_error`
- `frame_count_in_settle`
- `frame_count_in_stats`

Plus `duration_seconds` (single field).

**Gap:** missing `excluded_by_user` (user-selection exclusions are
currently page-state, not section-state — this is OK for the
backend-stored per-section metric, since user selections re-apply
client-side). Missing the `duration_total` vs `duration_included`
distinction.

Fix: add `duration_total_seconds` and `duration_included_seconds`
fields to `SectionMetrics`. The backend computes both at parse
time (using the in_settle filter for `included`); user-exclusions
are layered on top client-side via the existing `phd2GuidingMetrics.ts`
helper.

#### Files to modify

**Backend:**

- `backend/src/nightcrate/services/phd2_metrics.py` — replace
  `_rms`, `_slope_per_minute`, and add `_dec_drift_unguided_only`
  + `_polar_alignment_error_arcmin`. Update `compute_section_metrics`
  to use the new helpers.
- `backend/src/nightcrate/api/phd2_models.py` — add
  `polar_alignment_error_arcmin: float | None` field to
  `SectionMetrics`. Update Pydantic mirrors on `frontend/src/api/phd2.ts`.

**Frontend:**

- `frontend/src/lib/phd2GuidingMetrics.ts` — port the new RMS,
  drift, PA formulas to TypeScript so the Viewport/Selection
  Summary panels recompute correctly client-side without a backend
  round trip.
- `frontend/src/components/phd2/StatsPanel.tsx` — add a "PA error"
  row (degree symbol + arcmin). Display "—" when None.
- `frontend/src/components/phd2/ScatterPlot.tsx` — replace the
  PCA eigen-decomposition with PHDLogViewer's `θ = atan2(covxy,
  varx)` rotation. Re-iterate for `lx` / `ly` per the algorithm
  above. Verify the visual ellipse alignment still looks right
  (Theta-based rotation shouldn't visibly differ for the typical
  guide-log scatter shape).

#### Math derivations

##### §M1 — RMS as population variance via West-incremental update

PHDLogViewer's `LFit::data` method (line ~76) computes the streaming
update for population mean and population variance:

```
n_new = n + 1
delta = x − μ_old
μ_new = μ_old + delta / n_new
var_new = (n × var_old + delta × (x − μ_new)) / n_new
```

The code uses an algebraically equivalent rearrangement (`k = n / n_new`):

```
varx_new = varx_old + (k × dx² − varx_old) / n_new
```

Both compute the population variance:

$$\text{var}(x) = \frac{1}{N}\sum_{i=1}^{N}(x_i - \bar{x})^2$$

(Note `1/N` denominator, not `1/(N-1)` — population, not sample.)

`RMS = sqrt(var)` is therefore standard deviation.

**Difference from RMS-from-zero.** For a series `[1, 2, 3]`:
- RMS-from-zero = `sqrt((1+4+9)/3) ≈ 2.16`
- Standard deviation = `sqrt(((1-2)² + (2-2)² + (3-2)²)/3) = sqrt(2/3) ≈ 0.82`

PHDLogViewer reports the smaller number. NightCrate currently
reports the larger. This is the difference users will see post-
v0.25.0.

##### §M2 — Polar alignment formula reconciliation

The `3.8197` constant comes from converting Barrett's
arcsec/hour-form derivation to px/min input.

**Source distinction.** Two independent sources arrive at the same
relationship:

- **Barrett** ([celestialwonders.com](http://celestialwonders.com/articles/polaralignment/PolarAlignmentAccuracy.html))
  — cited directly in PHDLogViewer's `AnalysisWin.cpp` line 166.
  Barrett's derivation uses the small-angle geometry of a polar-
  misaligned mount tracking through a sidereal day; the coefficient
  3.8197 follows from unit conversion.
- **Starry Nights** ([starrynights.us](http://www.starrynights.us/Articles/Polar_Align.htm))
  — derives the same relationship empirically with a 0.262
  arcsec/min/arcmin coefficient at the celestial equator.

Both produce the same number to within rounding (3.8197 = 60 / 15.71;
1 / 0.262 ≈ 3.8167). NightCrate uses PHDLogViewer's exact 3.8197
constant for cross-tool consistency, citing Barrett's derivation
(per PHDLogViewer's source code attribution).

**Form 1 — Barrett, arcsec/min:**

$$\alpha_{\text{arcmin}} = \frac{|\text{drift}|_{\text{arcsec/min}}}{0.262 \cdot \cos(\delta)}$$

**Form 2 — PHDLogViewer, px/min:**

Converting drift from arcsec/min to px/min via pixel_scale gives:

$$\alpha_{\text{arcmin}} = \frac{\text{drift}_{\text{px/min}} \cdot \text{pixel\_scale}}{0.262 \cdot \cos(\delta)} = \frac{3.8197 \cdot \text{drift}_{\text{px/min}} \cdot \text{pixel\_scale}}{\cos(\delta)}$$

(Since `1 / 0.262 ≈ 3.8167 ≈ 3.8197`.)

NightCrate uses **PHDLogViewer's exact constant 3.8197** for
cross-tool consistency. Same source code, same formula, same number.

##### §M3 — Dec-drift unguided-frames-only accumulation

The Dec drift algorithm bypasses the corrections-subtraction
approach used for RA because Dec guiding is typically asymmetric
(corrected only when needed in one direction; some mounts have
Dec guiding off entirely for portion of the session).

The y_accum sequence accumulates Dec position changes only when
the *previous* frame was unguided (decdur == 0). Those frames
reflect actual sky drift over the inter-frame interval. Frames
where the previous frame was guided are skipped because the
inter-frame change is dominated by the guide pulse, not by
genuine drift.

The slope of `y_accum vs t` (linear regression `B = cov(t,
y_accum) / var(t)`) gives the drift rate.

**Edge case handling:**
- First included frame: `y_accum = 0`, `fit.data(first.dt, 0)`
  initializes the regression. (Per `AnalysisWin.cpp` line ~120.)
- Single included frame OR all-guided frames: `fit.B()` returns
  0 because `var(t)` is undefined or trivial. This matches
  PHDLogViewer behavior.
- Sections with no Dec guiding at all: every frame has `decdur
  == 0`, so every change is accumulated — equivalent to a
  least-squares slope of `decraw` vs `t`. This is the correct
  fallback.

#### Tests (~15 new + many regression updates)

- `test_phd2_metrics.py` — update every existing pinned-value test
  for RMS / drift / oscillation. The new RMS values will be
  smaller (typically by 5-30% depending on the section's mean
  offset); the new drift values may be substantially different
  for sections with effective guide damping. Re-derive expected
  values by hand for each test case.
- New `test_phd2_metrics_pa.py` — 8 tests for PA error: known
  declination + known drift → expected PA value. Edge cases:
  declination None, drift None, very-low-declination cos-correction.
- `test_phd2_metrics_dec_drift_unguided_only.py` — 5 tests:
  all-guided section returns 0; alternating guided/unguided
  pattern returns the right slope; pure-drift no-guide section
  matches the simple least-squares slope.
- `test_scatter_ellipse_rotation_atan2_form.py` — frontend test
  (jest or similar) verifying the rotation matches PHDLogViewer's
  form for a synthetic dataset.

#### Verification

- `cd backend && uv run pytest tests/services/test_phd2_metrics.py`
  — all updated tests pass
- Full backend suite at ~1955 passed (we expect ~10 fewer than
  v0.24.0 because the failed-rest tests for the old algorithms
  are removed; new tests added)
- Manual: open the ASIAir sample log, verify RMS RA / RMS Dec
  match the values PHDLogViewer reports for the same log
  (cross-tool comparison test). Verify a new "PA error" row
  appears in the section summary.

#### Out of scope

- Spectrum tab work → v0.26.0
- Unguided RA → v0.27.0
- Strain wave markers → v0.28.0
- Per-instance schema → v0.29.0

---

### v0.26.0 — Spectrum Tab v4-Conformance + Worm-Period Markers

**Status:** Planned
**Branch:** `v0.26.0/phd2-spectrum-conformance`
**Spec refs:** v4 §6.1 (entire FFT pipeline), §6.6 (worm markers)

#### Goal

Implement the Spectrum tab strictly per spec v4 §6.1, with worm-
period markers per §6.6. After this version, NightCrate's
spectrum view matches PHDLogViewer's spectrum view's reported
values for the same log: same Hamming window, same `4/N`
normalization, same Akima interpolation, same MAD-3 threshold,
same snap-to-peak hover, same Period/Amplitude/P-P/RMS readouts.

#### Why it stands on its own

The Spectrum tab is a self-contained view. Worm markers add
diagnostic value when a rig is selected, fall back to a heuristic
otherwise. Users with worm-mount rigs immediately benefit.
Strain-wave-mount users see the heuristic fallback; better support
ships in v0.28.0.

#### Scope

##### §6.1 — Full FFT pipeline (verified port)

Pre-FFT pipeline (12 steps per spec v4 §6.1.1):

1. **Filter** to frames where `included == true ∧ StarWasFound(err) ∧
   ¬in_settle ∧ ¬user_excluded`. (The standard §5.2 Include filter,
   which v0.25.0 establishes.) Selection-aware: FFT recomputes on
   shift-drag selection / shift+alt-drag exclusion changes.
2. **Minimum 12 entries** (`MIN_ENTRIES` per `AnalysisWin.cpp` line
   ~258). Skip + warn if fewer.
3. **Cadence check.** IQR(dt) / median(dt) > 0.20 → skip + warn
   ("frequency analysis disabled — sample cadence varies > 20%").
   IQR-over-median is robust against DROP-frame gaps that would
   otherwise blow std/mean above threshold.
4. **Drift subtraction** via least-squares linear fit (`LFit`).
   The drift slope `b` is preserved separately as the section's
   drift metric (already produced by §5.2.3 in v0.25.0); the
   FFT input is `x_i − (a + b·t_i)`.
5. **Akima spline interpolation** to uniform cadence. PHDLogViewer
   uses GSL's `gsl_interp_akima` (line ~36) — non-overshooting
   for oscillatory data. For NightCrate this means
   `scipy.interpolate.Akima1DInterpolator`, which **adds scipy
   as a backend dependency**. Linear interpolation (`np.interp`)
   is acceptable per spec but inferior; we adopt Akima for
   PHDLogViewer alignment.
6. **Hamming window** (NOT Hann). Per `AnalysisWin.cpp` line ~370:
   `w_i = 0.54 − 0.46 · cos(2π·i / (N − 1))`. For NightCrate:
   `np.hamming(n_uniform)`.
7. **FFT** via `numpy.fft.rfft` on the windowed series.
8. **Bin → period** mapping. Per `AnalysisWin.cpp` line ~390:
   `f_k = k / (N · Δt)`, `p_k = N · Δt / k`. Skip DC (k=0) and
   the symmetric upper half. PHDLogViewer keeps `nfft = N/2 − 1`
   bins.
9. **Amplitude normalization** `4/N` (per `AnalysisWin.cpp` line
   ~395 `double scale = 4. / (double) n;`). Then `amp_arcsec =
   amp_pixels × pixel_scale`. The factor 4 = 2 (single-sided) ×
   ~1.85 (Hamming coherent gain reciprocal `1/0.54`) rounded.
   Slight 8% over-estimate vs the textbook one-sided peak-amp
   normalization, but matches PHDLogViewer's reported peaks.
   (See §M1 below for derivation.)
10. **Display Y axis: log scale.** Lower bound:
    `max(amp_max / 10000, 0.001 arcsec)`. Upper: `amp_max × 1.1`.
11. **Display X axis: log scale, period in seconds.** Range: 5 s
    to roughly half the section duration.
12. **Seeing-band shading** at < 5 s with "atmospheric seeing"
    label.

Peak detection (§6.1.6):

- Threshold: `median(amp) + 3 × 1.4826 × MAD(amp)` (§M2 below).
  The 1.4826 factor scales MAD to be sigma-equivalent for normal
  data. The 3-sigma threshold is conservative; produces zero
  peaks on flat noise floors.
- Find local maxima (`amp[i] > amp[i-1] ∧ amp[i] > amp[i+1] ∧
  amp[i] > threshold`).
- Deduplicate within ±5 % period (keep higher amplitude).
- Cap at top 5 by amplitude across all visible traces (NOT
  per-trace).
- Display: dot markers only, **no on-chart text labels**.

Hover tooltip (§6.1.7):

- Snap-to-peak within ±8 pixels of cursor (matches `OnMove`
  handler at `AnalysisWin.cpp` lines ~860-890).
- Tooltip readouts (per `AnalysisWin.cpp` line ~895):
  - **Period**: `p` seconds (formatted naturally — "23.4 s",
    "1m 17s", "11m 28s")
  - **Amplitude**: `a` arcsec (the spectrum value at the peak)
  - **Peak-to-peak**: `2 · a` arcsec
  - **RMS**: `(√2 / 2) · a` ≈ `0.7071 · a` arcsec
- All four readouts visible; per-visible-trace.

##### §6.6 — Worm-period markers

Per-rig worm period lookup via `mount.worm_period_seconds`
(migration that the v0.25.0 branch in-flight had as 0024 — re-add
here as a fresh migration if v0.25.0 doesn't carry it forward).

When `mount.drive_type == 'worm'` (or freeform value matches —
the controlled vocabulary lands in v0.28.0) AND
`worm_period_seconds` is set:
- Vertical dashed line at the worm period.
- If a detected peak falls within ±5% of the worm period: callout
  chip "Worm-period peak: 0.42″ amp @ 479 s (mount: <name>)".

Heuristic fallback (no rig OR no worm period known):
- Largest peak in [300, 800] s with amplitude > **0.5 arcsec**
  (NOT 2.0 — the v3.1 plan corrected this; v4 confirms 0.5).
- Labeled "likely worm-period peak (uncertain without mount
  identification)".

Worm-period seed values per v4 §6.6 table (carry forward from
the in-flight branch's seed CSV, which is correct).

#### Files to modify

**Backend:**

- `backend/src/nightcrate/services/phd2_fft.py` — full rewrite per
  §6.1. Use `scipy.interpolate.Akima1DInterpolator` for
  interpolation, `np.hamming` for window, `4/N` for normalization,
  MAD with 1.4826 factor.
- `backend/src/nightcrate/api/phd2_models.py` — `FftResult.peaks`
  capped at 5 (was 8); `FftPeak` adds `peak_to_peak_arcsec` and
  `rms_arcsec` derived fields (or computed client-side for display
  — TBD).
- `backend/src/nightcrate/api/phd2.py` — `_HEURISTIC_AMP_MIN_ARCSEC
  = 0.5` (was 2.0). Worm marker logic unchanged in shape.
- `backend/src/nightcrate/db/migrations/<NNNN>.mount_worm_period.sql`
  — re-add migration 0024-equivalent if v0.25.0 doesn't carry it.

**Backend new dep:**

- Add `scipy>=1.11` to `backend/pyproject.toml`. Justification:
  Akima spline is the right interpolation for oscillatory data
  per spec v4 §11.13, and re-implementing Akima in pure numpy is
  ~50 lines of non-trivial math. scipy is BSD-3-Clause.

**Frontend:**

- `frontend/src/components/phd2/FftChart.tsx` — full rewrite for
  the v4 conformance: snap-to-peak hover, P-P + RMS readouts in
  tooltip, top-5 peak dots, no on-chart text. Wider left margin
  (78 px) and exponential-format big numbers (lessons from
  v0.25.0 in-flight bugs). Empty-trace state keeps toggles
  visible.
- `frontend/src/api/phd2.ts` — type updates for new FftPeak fields.

#### Math derivations

##### §M1 — Hamming amplitude normalization 4/N (cross-tool consistency)

For a discrete sinusoid `x_i = A · cos(2π · k₀ · i / N)` windowed
by Hamming `w_i = 0.54 − 0.46 · cos(2π·i / (N−1))`:

The Hamming coherent gain `G_c = mean(w_i) ≈ 0.54` (the cosine
term averages to 0 over a full window).

The windowed signal's FFT magnitude at the tone's bin is:

$$|X_{k_0}| \approx \frac{A \cdot N \cdot G_c}{2}$$

(factor of N from FFT scaling, /2 from one-sided cosine projection).

To recover A from |X|:

$$A \approx \frac{2 \cdot |X_{k_0}|}{N \cdot G_c} \approx \frac{2 \cdot |X|}{0.54 \cdot N} \approx \frac{3.7 \cdot |X|}{N}$$

PHDLogViewer rounds the constant to **4** for compatibility:

$$a_{\text{arcsec}, k} = \frac{4 \cdot |X_k|}{N} \cdot \text{pixel\_scale}$$

This over-estimates true peak amplitude by ~8%, but **NightCrate
must match PHDLogViewer's value** so cross-tool comparisons line
up. The 8% bias is documented and consistent across all sessions.

##### §M2 — MAD-based peak threshold

Median Absolute Deviation:

$$\text{MAD}(x) = \text{median}(|x_i - \text{median}(x)|)$$

For normal data, MAD relates to standard deviation via:

$$\sigma \approx 1.4826 \cdot \text{MAD}$$

(The 1.4826 factor is `1 / Φ⁻¹(3/4)` where Φ is the standard
normal CDF.)

A 3-sigma-equivalent threshold:

$$\text{threshold} = \text{median}(a) + 3 \cdot 1.4826 \cdot \text{MAD}(a)$$

A peak is significant if it exceeds threshold. Robust against
outliers (the spectrum's noise floor); produces zero false peaks
on a flat noise spectrum.

#### Tests (~25 new)

- 10 FFT tests (synthetic sinusoids at various periods + amplitudes,
  cadence guards, too-short guards, noise floor produces zero
  peaks)
- 6 hover tooltip tests (snap-to-peak within 8 px, falls through
  to interp when no nearby peak, tooltip values match formula)
- 5 worm-marker tests (rig with worm → marker fires; heuristic
  threshold 0.5; harmonic mount produces no marker; rig invalid
  → 404; cache key includes rig_id)
- 4 new dep validation tests (`scipy.interpolate.Akima1DInterpolator`
  available; basic interpolation correctness on a known dataset)

#### Verification

- Backend pytest at ~1980 passed
- Manual: open ASIAir sample log → Spectrum tab → verify peak
  amplitudes match what PHDLogViewer reports for the same log
  (within rounding). Hover near a peak → snap activates within
  ±8 px. Tooltip shows Period / Amplitude / P-P / RMS.

#### Out of scope

- Unguided RA → v0.27.0
- Strain wave markers + drive_type vocab → v0.28.0
- Measured PE structured output → v0.29.0
- GA section handling → v0.30.0

---

### v0.27.0 — Unguided RA Reconstruction + Time-Series Overlay

**Status:** Planned
**Branch:** `v0.27.0/phd2-unguided-ra`
**Spec refs:** v4 §6.2 (algorithm), §6.1.8 (Spectrum-tab Unguided
toggle paired with overlay)

#### Goal

Ship the unguided RA reconstruction as paired surfaces: a
toggleable overlay on the time-series chart AND a toggleable
trace on the Spectrum tab. The two ship together because the
spectrum view alone is hard to interpret without seeing the
time-domain unguided trace alongside.

#### Why it stands on its own

Unguided RA is the killer feature for mount tuning — it shows
what the mount's native PE looks like without the algorithm's
corrections layered on. Users tuning their mount immediately
benefit. The §6.2 algorithm is a verified port of PHDLogViewer's
`AnalysisWin.cpp::GARun::Analyze`, so the math is settled.

#### Scope

##### §6.2 — PHDLogViewer recurrence algorithm

```python
def reconstruct_unguided_ra(section, undo_corrections=True):
    out = []
    rapos = 0.0
    prev_raraw = 0.0
    prev_raguide = 0.0
    for s in section.samples:
        # Match PHDLogViewer's Include() = e.included && StarWasFound(e.err).
        # NOT mount-kind-restricted — AO frames with valid star data
        # accumulate normally (the AO's correction is captured in
        # ra_guide_px just like a Mount pulse). DROP frames have
        # error_code != 0 AND ra_raw_px is None, so the null check
        # filters them out automatically.
        if s.ra_raw_px is None or s.error_code != 0:
            out.append(None)
            continue
        raraw = s.ra_raw_px
        raguide = s.ra_guide_px or 0.0
        move = raraw - prev_raraw - prev_raguide
        rapos += move
        out.append(rapos)
        prev_raraw = raraw
        prev_raguide = raguide if undo_corrections else 0.0
    return out
```

**Filter scope (post-CD-review).** The earlier draft of this
algorithm filtered `mount_kind != "Mount"` to skip AO frames.
That's wrong — PHDLogViewer's `Include()` predicate is
mount-kind-agnostic (`AnalysisWin.cpp` line ~106:
`return e.included && StarWasFound(e.err);`), and AO frames with
valid star data should accumulate. The AO's correction is captured
in `ra_guide_px` exactly like a Mount pulse; both contribute to
the cumulative correction the recurrence backs out. The corrected
filter keeps only the null-data check (`ra_raw_px is None`) and
the star-found check (`error_code != 0`).

Sign convention derivation (§M1 below): RAGuideDistance is signed
as the algorithm's *desired change* in star position; the
recurrence accumulates the cumulative drift trajectory.

##### Time-series overlay

In `TimeSeriesChart.tsx`:
- New `unguidedRa: Array<number | null> | null` prop sourced from
  `selected.analysis.unguided_ra_px` in `Phd2AnalyzerPage.tsx`.
- New `raUnguided: false` visibility key.
- Legend chip "Unguided RA" in teal, disabled when prop is null.
- Third path inside the existing main panel using `xScale` +
  `yDistScale`. `defined((_, i) => unguidedRa[i] !== null)` gate
  so the line breaks across DROP/AO frames.
- Tooltip row appended.
- **No drift subtraction** for the time-series overlay — users
  want to see the cumulative drift in the time-domain view.

##### Spectrum-tab Unguided RA toggle

In `FftChart.tsx`:
- New trace toggle "Unguided RA" alongside RA / Dec, off by default.
- When on: backend computes the FFT of the drift-subtracted
  unguided RA trace and surfaces as `analysis.fft_unguided`.
- Drift is subtracted before windowing (per §6.2.2) so polar-
  alignment-induced drift doesn't dominate the low-frequency end.

##### Backend integration

`api/phd2.py`:
- `_build_section_analysis` calls `reconstruct_unguided_ra`,
  attaches `unguided_ra_px: list[float | None]` and
  `fft_unguided: FftResult | None` to `SectionAnalysis`.
- The `compute_section_fft(series=unguided_ra, ...)` path uses
  the v0.26.0 pipeline (Hamming, Akima, etc.) on the unguided
  series.

#### Files to modify

**Backend:**

- `backend/src/nightcrate/services/phd2_unguided.py` — full rewrite
  per the §6.2 algorithm. ~80 lines.
- `backend/src/nightcrate/api/phd2.py` — extend
  `_build_section_analysis` to include unguided + fft_unguided.
- `backend/src/nightcrate/api/phd2_models.py` — extend
  `SectionAnalysis` with `unguided_ra_px` and `fft_unguided`.

**Frontend:**

- `frontend/src/components/phd2/TimeSeriesChart.tsx` — add
  unguided RA overlay (~70 LOC). Visibility key, legend chip,
  rendered path, tooltip row.
- `frontend/src/components/phd2/FftChart.tsx` — add Unguided RA
  trace toggle alongside RA / Dec.
- `frontend/src/pages/Phd2AnalyzerPage.tsx` — pass
  `selected.analysis.unguided_ra_px` to TimeSeriesChart.
- `frontend/src/api/phd2.ts` — type updates.

#### Math derivations

##### §M1 — Sign convention proof for the recurrence

PHD2's `RAGuideDistance` represents the algorithm's *desired
change* in star position. For positive raraw (star east of lock),
the algorithm wants the star to move back toward zero — a negative
change — so `RAGuideDistance < 0`.

Between consecutive frames:

$$\text{raraw}_{\text{next}} = \text{raraw}_{\text{prev}} + \text{raguide}_{\text{prev}} + \text{drift}_{\text{during}}$$

(The mount's response to prev_raguide takes effect by the next
measurement; drift_during is whatever PE/polar-alignment/wind
added on top.)

Solving for `drift_during`:

$$\text{drift}_{\text{during}} = \text{raraw}_{\text{next}} - \text{raraw}_{\text{prev}} - \text{raguide}_{\text{prev}} = \text{move}$$

So `rapos = Σ move_i` accumulates the unguided drift trajectory.

**Why this is materially simpler than the v3 algorithm.** v3 spec
(and the v0.25.0 in-flight implementation) used `RADuration ×
xRate × sign(direction)`. That approach required handling
min-move frames, clipped pulses, parity sign lookups, and DROP
frames specially. The PHDLogViewer recurrence handles all of these
implicitly because RAGuideDistance is already the signed pixel-
space output of the algorithm:

- Min-move frames: `ra_guide_px = 0` → recurrence skips that
  contribution naturally.
- Clipped pulses: PHDLogViewer's algorithm output reflects the
  clipped value; the next raraw measurement reflects what the
  mount actually did.
- DROP frames: filtered out by `error_code != 0` AND
  `ra_raw_px is None`; prev_raraw and prev_raguide don't update;
  the next valid frame's `move` correctly spans the gap.
- AO frames: NOT filtered out — `RAGuideDistance` on AO frames
  represents the AO's commanded motion in the same pixel-equivalent
  units, and accumulating that into the recurrence correctly
  backs out AO corrections alongside Mount corrections (the
  unguided trace shows what would have happened with NEITHER
  source of correction applied).
- Parity: `RAGuideDistance` is signed in the same sense as
  `RARawDistance`, so no parity table is needed.

#### Tests (~10 new)

- `test_phd2_unguided.py` — full rewrite. 8 tests:
  1. Zero corrections + zero drift → flat trace at 0
  2. Constant drift + zero corrections → linear trace
  3. Perfect correction + constant drift → recovers drift via
     raguide accumulation
  4. DROP frame skips without breaking recurrence (output is None
     at that index; prev_raraw/prev_raguide carry forward unchanged;
     the next valid frame's `move` correctly spans the gap)
  5. **AO frames accumulate alongside Mount frames** with valid
     ra_raw_px and ra_guide_px — they are NOT treated like DROP
     (CD-review correction)
  6. Missing ra_guide_px → falls back to 0
  7. undo_corrections=False produces raw-position-anchored-at-zero
     trace
  8. Mixed Mount + AO + DROP within one section: Mount + AO frames
     accumulate; DROP frames get None at their index but don't
     break the recurrence
- `test_phd2_api.py` — new tests for fft_unguided in
  SectionAnalysis. 2 tests (presence + correct length).

#### Verification

- Backend pytest at ~1990 passed
- Manual: open ASIAir sample log → Graph tab → toggle Unguided RA
  → teal trace appears. Switch to Spectrum tab → toggle Unguided
  RA → second trace appears in spectrum.

#### Out of scope

- Drive_type vocabulary + strain wave markers → v0.28.0
- Per-session measured PE structured output → v0.29.0

---

### v0.28.0 — Drive-Type-Aware Markers (Strain Wave + Hybrid)

**Status:** Planned
**Branch:** `v0.28.0/phd2-drive-types`
**Spec refs:** v4 §6.7 (strain wave + hybrid mounts), §6.6
(integration point — markers branch on drive_type now)

#### Goal

Replace v0.26.0's worm-only marker model with a drive-type-aware
PeMarker that handles worm, strain wave, hybrid (RA strain wave +
Dec worm), direct-drive-encoder, and friction mounts. Strain-wave-
mount users (ZWO AM5, Rainbow Astro RST-135, iOptron HEM-series,
Pegasus NYX) finally get rig-aware diagnostics.

#### Why it stands on its own

Strain wave mounts are mainstream — ZWO AM5 alone is one of the
most popular mounts sold in 2024-2026. v0.26.0's worm-only marker
model is silently wrong for them (heuristic fallback fires in
the wrong period range). v0.28.0 fixes this and adds proper
support.

#### Scope

##### Schema migration

New migration: `<NNNN>.mount_drive_type_strain_wave.sql`.

**Pre-migration verification step (CD-review correction):**

Before writing the migration, run:

```sql
SELECT DISTINCT drive_type FROM mount;
```

against the live database (or the seed-loaded test database) to
confirm the actual freeform strings present. The mapping below
assumes the canonical seed values; any unmapped strings must be
explicitly handled in the migration (don't silently fall to
`'unknown'`).

Currently expected values from the seed CSV:

- `'Worm gear'` → `'worm'`
- `'Harmonic'` → `'strain_wave'`
- `'Direct drive'` → `'direct_drive_encoder'` (Planewave L-series)
- empty / null → `'unknown'`

User-added mounts may have other strings. If `SELECT DISTINCT`
surfaces values like `'Strain wave'` or `'Friction drive'` or
`'Belt drive'`, add explicit mappings in the migration. The
migration should fail loudly (not silently degrade to `'unknown'`)
if any value can't be mapped.

- Add CHECK constraint:
  `CHECK (drive_type IN ('worm', 'strain_wave', 'strain_wave_with_encoder',
  'hybrid_strain_wave_ra', 'hybrid_strain_wave_ra_with_encoder',
  'direct_drive_encoder', 'friction', 'unknown'))`.
- Add three new REAL columns:
  - `dominant_period_s` (NULL when unknown)
  - `expected_period_band_min_s` (NULL when unknown)
  - `expected_period_band_max_s` (NULL when unknown)
- Add one column for hybrid mounts:
  - `dec_worm_period_s` (NULL except for hybrid_strain_wave_ra
    mounts; HEM27 = 600 s inherited from GEM28).
- Rebuild `rig_summary` view to expose all four new columns
  (prefixed `mount_dominant_period_s` etc.).

##### Strain wave seed data (per v4 §6.7 table)

| Mount | drive_type | dominant_period_s | band_min, band_max | dec_worm |
|---|---|---|---|---|
| ZWO AM3 | strain_wave | 288 | 180, 360 | — |
| ZWO AM5 | strain_wave | 288 | 180, 360 | — |
| ZWO AM5N | strain_wave | 288 | 180, 360 | — |
| Rainbow Astro RST-135 | strain_wave | 430 | 300, 600 | — |
| Rainbow Astro RST-135E | strain_wave_with_encoder | 430 | 300, 600 | — |
| iOptron HEM27 | hybrid_strain_wave_ra | 360 | 250, 480 | 600 |
| iOptron HEM27EC | hybrid_strain_wave_ra_with_encoder | 360 | 250, 480 | 600 |
| iOptron HEM44 | hybrid_strain_wave_ra | NULL | 250, 600 | 600 |
| iOptron HEM44EC | hybrid_strain_wave_ra_with_encoder | NULL | 250, 600 | 600 |
| iOptron HAE29 | strain_wave | NULL | 250, 600 | — |
| iOptron HAE43 | strain_wave | NULL | 250, 600 | — |
| iOptron HAE69 | strain_wave | NULL | 250, 600 | — |
| Pegasus Astro NYX-101 | strain_wave | 430 | 350, 500 | — |
| Sky-Watcher Wave 100i | strain_wave | NULL | 200, 500 | — |
| Sky-Watcher Wave 150i | strain_wave | NULL | 200, 500 | — |

**Per CD-review correction:** the seed CSV writes **one row per
mount model**. HAE29/43/69 are separate physical mounts with
different load capacities (29 / 43 / 69 lb) and almost certainly
different gear ratios; SW Wave 100i and 150i are similarly
distinct. Earlier draft of this table compressed them into single
rows for brevity — the actual seed CSV has eight separate rows
for these eight models, each with its own `seed_key` and
`mount_id`. Period values are placeholder `NULL — measure` until
community measurements arrive.

(Other mounts: existing worm rows stay `worm` with their existing
worm_period_seconds; star trackers and unknowns stay `unknown` or
`friction`.)

##### Backend `_build_pe_marker` (renamed from `_build_worm_marker`)

Replaces the v0.26.0 worm-only logic. Branches on `drive_type`:

```python
if drive_type == 'worm' and worm_period_seconds:
    return _worm_marker(...)
elif drive_type in ('strain_wave', 'strain_wave_with_encoder'):
    return _strain_wave_marker(dominant_period_s, expected_band)
elif drive_type in ('hybrid_strain_wave_ra', 'hybrid_strain_wave_ra_with_encoder'):
    # Two markers: strain wave on RA, worm on Dec
    return PeMarker(
        ra_marker=_strain_wave_marker(...),
        dec_marker=_worm_marker(period=dec_worm_period_s),
    )
elif drive_type == 'direct_drive_encoder':
    return None  # no markers
else:  # unknown or no rig
    return _heuristic_marker(...)
```

Strain wave marker variant: vertical line at `dominant_period_s`
if known + shaded band over `[band_min, band_max]` if known. Both
if both known. Callout chip when a peak falls within the band.

Encoder variants get the same band but with reduced amplitude
expectation (display only — the rule logic doesn't change).

##### PeMarker model

New Pydantic model replacing `WormMarker`:

```python
class PeMarker(BaseModel):
    kind: Literal['worm_point', 'strain_wave_band', 'hybrid', 'heuristic']
    # Point-marker variant
    period_s: float | None
    label: str
    source: Literal['mount', 'heuristic']
    matched_peak: FftPeak | None
    # Band-marker variant
    band_min_s: float | None
    band_max_s: float | None
    # Hybrid variant: separate markers for RA + Dec
    ra_marker: PeMarker | None
    dec_marker: PeMarker | None
```

#### Frontend

- `FftChart.tsx` — render the band variant as a translucent SVG
  `<rect>` covering `[band_min, band_max]` × full chart height.
  Render the dominant period as a sharper vertical line on top.
  Hybrid mounts render two markers (one per RA/Dec spectrum).
- `RigSelectBar.tsx` — chip hint text adapts to drive_type:
  - "EQ6-R Pro worm 479 s"
  - "AM5 strain wave ~288 s (band 180-360 s)"
  - "HEM27 hybrid: RA strain wave ~360 s + Dec worm 600 s"
  - "HEM44 strain wave (period unknown — measure)"

#### Tests (~20 new)

- 6 strain wave marker tests (dominant + band, dominant only,
  band only, neither known)
- 4 hybrid mount tests (HEM27 produces two markers; RA strain
  wave + Dec worm both present; band on RA, point on Dec)
- 4 direct-drive tests (no marker fires)
- 2 encoder variant tests (RST-135E gets reduced amplitude
  expectation)
- 4 schema migration regression tests (existing worm seeds still
  load; new strain wave seeds backfill correctly)

#### Verification

- Backend pytest at ~2010 passed
- Manual: pick AM5 rig → strain wave band marker on Spectrum tab.
  Pick HEM27 → two markers (RA strain wave band, Dec worm point).
  Pick L-500 → no marker.

#### Out of scope

- Per-session measured PE structured output → v0.29.0
- Override-with-measured behavior (use measured period when ≥3
  stable measurements available) → v0.29.0

---

### v0.29.0 — Per-Session Measured PE + Per-Instance Mount Schema

**Status:** Planned
**Branch:** `v0.29.0/phd2-measured-pe`
**Spec refs:** v4 §6.4 (per-session measured PE), §6.8 (per-instance
schema)

#### Goal

Make measured PE a first-class structured output (not just an
on-chart thing users eyeball), and introduce the per-mount-instance
distinction (one user can own two AM5s; their measurements should
attach to the specific physical mount, not just the model). This
is the foundational schema work that v0.34.0's per-instance corpus
UI builds on.

#### Why it stands on its own

The Measured PE panel is immediately user-visible: every guiding
section gets a structured PE measurement with confidence indicator
+ comparison to manufacturer default. The override behavior (use
measured period instead of seed default when ≥3 stable measurements
exist) makes the v0.28.0 spectrum markers smarter for users with
history.

#### Scope

##### Per-instance schema migration

Currently the rig schema attaches mounts as `mount_id` foreign key
into the `mount` table — which is the model. v4 §6.8 distinguishes
mount **model** (manufacturer's gear) from mount **instance** (the
specific physical mount the user owns).

New table:

```sql
CREATE TABLE mount_instance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mount_id INTEGER NOT NULL REFERENCES mount(id),  -- the model
    nickname TEXT NOT NULL,                          -- "My AM5", "AM5 #2"
    serial_number TEXT,                              -- optional
    purchase_date TEXT,                              -- optional ISO date
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Add `mount_instance_id INTEGER REFERENCES mount_instance(id)` to
the `rig` table. Migration backfills: for each existing rig with
a mount, auto-create one mount_instance with nickname = mount
model name + " (auto)".

Update `rig_summary` view to expose
`mount_instance_id`, `mount_instance_nickname`.

##### Measured PE persistence

New table for per-session measurements (first PHD2-specific SQLite
tier):

```sql
CREATE TABLE phd2_measured_pe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_file_path TEXT NOT NULL,
    log_file_mtime_ns INTEGER NOT NULL,
    log_file_size INTEGER NOT NULL,
    section_index INTEGER NOT NULL,
    measured_at TEXT NOT NULL DEFAULT (datetime('now')),
    rig_id INTEGER REFERENCES rig(id),
    mount_instance_id INTEGER REFERENCES mount_instance(id),
    -- All fields from v4 §6.4.1
    pe_period_s REAL,
    pe_amplitude_arcsec REAL,
    pe_peak_to_peak_arcsec REAL,
    pe_rms_arcsec REAL,
    pe_dominant_peak_confidence TEXT  -- 'high' | 'medium' | 'low'
        CHECK (pe_dominant_peak_confidence IN ('high', 'medium', 'low')),
    pe_section_duration_min REAL,
    pe_section_duration_vs_period_ratio REAL,
    pe_secondary_peaks_json TEXT,  -- JSON array of {period_s, amplitude_arcsec}
    pe_shape_category TEXT
        CHECK (pe_shape_category IN ('sinusoidal', 'asymmetric', 'multi-harmonic')),
    pe_measurement_at_declination REAL,
    pe_measurement_pier_side TEXT,
    pe_measurement_payload_kg REAL,
    is_guiding_assistant INTEGER NOT NULL DEFAULT 0,
    UNIQUE (log_file_path, log_file_mtime_ns, log_file_size, section_index, rig_id)
);
```

Indexes:
- `(mount_instance_id, measured_at)` — fast per-instance history
- `(rig_id, measured_at)` — fast per-rig history
- `(log_file_path)` — fast per-log lookup

##### Backend service `services/phd2_measured_pe.py`

```python
def measure_section_pe(
    section: LogSection,
    fft_unguided: FftResult,
    arcsec_scale: float | None,
) -> MeasuredPe | None:
    """Compute structured measured PE per v4 §6.4.1.
    
    Returns None when:
    - Unguided FFT unavailable (no x_rate or short section)
    - No dominant peak detected (flat noise spectrum)
    - Dominant peak below confidence threshold
    """
```

Returns the `MeasuredPe` Pydantic model with all the fields from
v4 §6.4.1.

##### MeasuredPe persistence

In `api/phd2.py`, after computing `SectionAnalysis`, persist the
`MeasuredPe` to `phd2_measured_pe` if:
- The section is guiding (not calibration)
- Either: `mount.drive_type ∈ {worm, strain_wave, hybrid_*}`, OR
  the section is a Guiding Assistant section, OR the user
  toggled "Unguided RA" mode.
- The MeasuredPe computation succeeded (returned non-None).

Persistence is idempotent on `(log_file_path, mtime_ns, size,
section_index, rig_id)` via the UNIQUE constraint.

##### Override behavior (§6.4.3)

When `mount_instance_id` is set and has ≥ 3 prior measurements
with stable period (CV < 5% across measurements), use the
per-instance measured period for the spectrum marker — overriding
the manufacturer default from §6.7 seed data.

Both shown on chart (manufacturer default as faint secondary
marker, measured as primary) so the user can see the difference.

##### Frontend Measured PE panel

In `Phd2AnalyzerPage.tsx`, new "Measured PE" panel under the
Section Summary on the Graph tab. Shows:

- Period (with confidence indicator: dot color)
- Amplitude / Peak-to-peak / RMS
- Section-duration-to-period ratio (warn icon if < 2)
- Shape category
- "Measured 295 s / manufacturer 288 s — well within expected range"
- "Measured 295 s / your AM5 #1's average 293 s ± 4 s over 8 sessions"
  (only when per-instance history exists)

Mount Instance management UI: simple "Mount Instances" page in
Settings or Equipment area where the user can:
- View existing instances
- Create new instances ("My AM5 #2")
- Edit nickname / serial / purchase date / notes
- Delete (with confirmation if measurements attached)

Rig form gets a `mount_instance` dropdown (auto-populated when a
mount is selected; user can pick "Create new instance...").

#### Files to modify

**Backend:**

- `backend/src/nightcrate/db/migrations/<NNNN>.mount_instance.sql`
- `backend/src/nightcrate/db/migrations/<NNNN+1>.phd2_measured_pe.sql`
- `backend/src/nightcrate/services/phd2_measured_pe.py` (new)
- `backend/src/nightcrate/api/phd2_models.py` — add `MeasuredPe`,
  attach to `SectionAnalysis`
- `backend/src/nightcrate/api/phd2.py` — measure + persist
- `backend/src/nightcrate/api/equipment_models.py` — MountInstance
  Pydantic models
- `backend/src/nightcrate/api/equipment.py` — MountInstance CRUD

**Frontend:**

- New page `pages/MountInstancesPage.tsx`
- `components/equipment/MountInstanceFormDialog.tsx`
- `components/phd2/MeasuredPePanel.tsx`
- `components/rigs/RigFormDialog.tsx` — add mount_instance picker

#### Tests (~25 new)

- 8 measured PE service tests (synthetic spectra → expected
  measurements; confidence levels; secondary peaks; shape category)
- 6 mount_instance schema tests (backfill correctness, CRUD,
  cascade behavior)
- 4 override behavior tests (≥3 stable → measured used; otherwise
  manufacturer default; both markers visible)
- 4 measured-pe persistence tests (idempotency on UNIQUE; per-rig
  query; per-instance query)
- 3 UI tests (panel renders correctly, history appears when
  available)

#### Verification

- Backend pytest at ~2035 passed
- Manual: open ASIAir sample log → Measured PE panel shows
  period/amplitude/P-P/RMS for the guiding section. Open the
  same log a second time → no duplicate row in `phd2_measured_pe`
  (idempotent).

#### Out of scope

- Per-instance corpus UI (history scatter, drift-over-time
  alert) → v0.34.0
- Diagnostic engine consumption of measured PE → v0.31.0
  (the new `guiding_pe_suppression_low` rule)

---

### v0.30.0 — GA Section Handling + AO/Mount Toggle

**Status:** Planned
**Branch:** `v0.30.0/phd2-ga-ao`
**Spec refs:** v4 §6.3, §6.5

#### Goal

Round out v2-phase parity with PHDLogViewer: detect Guiding
Assistant sections and render a dedicated panel; add AO vs Mount
corrections toggle when AO frames are present.

#### Why it stands on its own

GA sections currently render with the standard guiding-section
view, which misses the GA-specific outputs (unguided RMS, polar
alignment estimate, backlash). Users running GA get a much better
view post-v0.30.0. AO toggle is mainstream for SX AO and similar
adaptive-optics setups.

#### Scope

##### §6.3 — GA detection + panel

Detection (`is_guiding_assistant_section`). A section is GA when
**either** condition holds (per spec v4 §6.3 and CD-review
correction — earlier draft used AND, which is strictly more
restrictive and misses GA sections with partial all-zero patterns
or lost explicit events):

1. `Guiding Output Disabled` and `Guiding Output Enabled` INFO
   events bracketing the section, **OR**
2. `RADuration == 0 ∧ DECDuration == 0` for ≥ 90 % of frames in
   the section.

The OR form catches both GA sections where the explicit event was
lost or never logged (heuristic catches them) and sections where
a brief test pulse contaminates the all-zero pattern but the
explicit event marks them cleanly. PHDLogViewer doesn't auto-detect
GA at all (the user picks the "Analyze GA" menu item explicitly),
so this is a NightCrate-specific design decision; spec's permissive
OR is the right choice for an auto-detector.

GA panel:
- **Unguided RMS RA / Dec / Total** — using §5.2.1 RMS formula on
  the raw distance series. No drift subtraction (matches PHD2's
  GA report).
- **Estimated polar alignment error** — using §5.2.6 PA formula
  (the in-place per-section metric from v0.25.0).
- **Measured Dec backlash** if a backlash sub-sequence is detected
  (alternating-direction Dec pulse pattern with no RA corrections,
  ~20 N then ~20 S). Read directly from PHD2's GA-emitted INFO
  line if logged; otherwise compute from pulse-displacement
  asymmetry.
- **Drift-corrected RA trace** with §6.2 unguided reconstruction.
- **Dedicated FFT** on the unguided RA trace with wider period
  range (`[5, min(duration/2, 3600)]` instead of the standard
  `[5, min(duration/2, 1800)]`). This is the input to §6.4
  measured PE for GA sections.

##### §6.5 — AO/Mount toggle

When a section contains both `mount = "Mount"` and `mount = "AO"`
samples:
- Three-state toggle in TimeSeriesChart: "Mount only" (default) /
  "AO only" / "Both"
- Filter chart input data accordingly
- Stats panel shows separate "Mount-corrected RMS" / "AO-corrected
  RMS" rows
- Spectrum tab respects the toggle (computes FFT on the active
  subset)

#### Files to modify

**Backend:**

- `backend/src/nightcrate/services/phd2_ga.py` (new) — `is_guiding_assistant_section`,
  backlash sub-sequence detector
- `backend/src/nightcrate/api/phd2.py` — GA section detection in
  the section-analysis path

**Frontend:**

- `components/phd2/GuidingAssistantPanel.tsx` (new)
- `components/phd2/TimeSeriesChart.tsx` — AO/Mount toggle
- `components/phd2/StatsPanel.tsx` — AO-corrected vs mount-
  corrected rows
- `pages/Phd2AnalyzerPage.tsx` — special-case routing for GA

#### Tests (~15 new)

- 4 GA detection tests (positive/negative cases, edge cases with
  one stray pulse)
- 3 backlash sub-sequence detection tests
- 6 AO/Mount toggle tests
- 2 GA panel display tests

#### Verification

- Backend pytest at ~2050 passed
- Manual: open a real GA log → GA panel renders. Open AO log →
  toggle works.

---

### v0.31.0 — Diagnostic Engine: Confident Tier

**Status:** Planned
**Branch:** `v0.31.0/phd2-diagnostics-confident`
**Spec refs:** v4 §7.1, §7.2 (8 confident rules), §7.5 (settings)

#### Goal

Ship the diagnostic engine with eight confident-tier rules. After
this version, problematic logs surface 1-3 confident findings
within 5 seconds of loading, replacing the "post log to forum,
wait for expert" workflow for common cases.

#### Why it stands on its own

The diagnostic engine is the primary v3-phase NightCrate
differentiator. Confident-tier rules are the highest-value subset
— they fire only when the signature has a single canonical
explanation. Speculative rules ship in v0.32.0; confident rules
alone are immediately useful.

#### Scope

##### Engine scaffolding (§7.1)

- `services/phd2_diagnostics.py` (new) — `Rule` Protocol, `Finding`
  dataclass, `run_diagnostics(section, metrics, settings)`.
- **Tier-override hook on the Rule Protocol** (CD-review open
  question #4 resolution): every rule has an optional method
  `tier_override(evidence) -> Literal['confident', 'speculative']
  | None`. Default returns `None` (use the rule's class-level
  default tier). Used by `out_of_band_spectrum_peaks` in v0.32.0
  to elevate direct-drive-encoder peaks to confident tier even
  though the rule's default is speculative. Bake this into v0.31.0's
  Protocol so v0.32.0 doesn't need to retrofit.

##### Eight confident rules (§7.2)

1. **`polar_alignment_from_dec_drift`** — uses §5.2.6 PA formula
   (which already exists post-v0.25.0).
2. **`dec_backlash_overshoot_pattern`** — 5+3+2× signature, ≥3
   sequences threshold.
3. **`snr_drop_preceded_star_lost`** — 30 s SNR comparison.
4. **`sustained_dec_direction_pulses`** — ≥90% in one direction
   over ≥15 min.
5. **`star_saturation`** — ≥5% saturated/mass-change frames.
6. **`calibration_axes_not_orthogonal`** — direction-agnostic
   distance from perpendicular. Per CD review: the spec's literal
   `|x_angle − y_angle − 90°| > 5°` form fails for axes oriented
   the "other way" (e.g. `x − y = 270°` produces 180° instead of
   0°). Two angles representing axes (lines, not vectors) are
   perpendicular when `|x − y| ≡ 90° (mod 180°)`. The correct
   modulus-aware form:

   ```python
   def deviation_from_orthogonal_deg(x_angle: float, y_angle: float) -> float:
       diff_mod_180 = abs(x_angle - y_angle) % 180.0
       # Fold to [0, 90] (angle between two lines is always in this range)
       line_angle = min(diff_mod_180, 180.0 - diff_mod_180)
       # Deviation from perpendicular (90° = perfect orthogonal)
       return abs(line_angle - 90.0)
   ```

   Rule fires when `deviation_from_orthogonal_deg > 5`. Verified
   against edge cases:

   - `x=0, y=90`: diff=90, mod=90, fold=90, deviation=0 ✓
     (perpendicular)
   - `x=0, y=270`: diff=270, mod=90, fold=90, deviation=0 ✓
     (perpendicular, despite the 270° representation)
   - `x=0, y=0`: diff=0, mod=0, fold=0, deviation=90 ✓ (parallel)
   - `x=0, y=180`: diff=180, mod=0, fold=0, deviation=90 ✓
     (anti-parallel, treated as parallel for line geometry)
   - `x=0, y=85`: diff=85, mod=85, fold=85, deviation=5 (border)
   - `x=0, y=−95`: |−95|=95, mod=95, fold=85, deviation=5 (same)

   CD's suggested Option A (`||x−y| − 90°|`) is approximately
   correct for `|x − y| ≤ 180°` but fails for the 270° wrap;
   Option B doesn't handle parallel axes correctly. The `% 180`
   modulus is the load-bearing piece.
7. **`chasing_seeing_ra`** — three-way AND on oscillation +
   pulse + exposure.
8. **`guiding_pe_suppression_low`** (NEW per v4 §7.2) — compares
   raw RA spectrum amplitude vs unguided RA spectrum amplitude at
   the dominant PE period (uses v0.27.0 unguided FFT + v0.29.0
   measured PE):
   ```
   suppression_ratio = 1 - (raw_RA_amp_at_pe_period / unguided_RA_amp_at_pe_period)
   ```
   Fires when `pe_amplitude_arcsec ≥ 1.5` AND `suppression_ratio
   < 0.5`. This is the rule that answers "is my guiding actually
   working?"

##### Settings (§7.5)

- `phd2_diagnostics_speculative_enabled: bool` (false initially —
  speculative rules ship in v0.32.0)
- Per-rule enable/disable bitmap

##### FindingsPanel UI

- New `components/phd2/FindingsPanel.tsx` — collapsible card per
  finding with tier-colored chip, category icon, summary,
  expandable explanation, evidence table, reference link,
  actionable line.
- Mount under the rig-select-bar in Spectrum + Graph tabs.
- Suppression: "Dismiss this finding" button stores rule_id in
  localStorage.

#### Tests (~30 new)

- 8 rule-fires tests (one per rule, hand-crafted signature)
- 8 rule-doesn't-fire-when-precondition-fails tests
- 8 rule-doesn't-fire-when-signature-absent tests
- 4 reference-rule false-positive tests against ASIAir sample
- 2 settings tests

---

### v0.32.0 — Diagnostic Engine: Speculative Tier + Equipment-Aware

**Status:** Planned
**Branch:** `v0.32.0/phd2-diagnostics-speculative`
**Spec refs:** v4 §7.3, §7.4

#### Goal

Round out the diagnostic engine with **eight** speculative-tier
rules (including the drive-type-aware `out_of_band_spectrum_peaks`
and the new `strain_wave_load_balancing_recommendation`) plus
rig-context-aware threshold scaling.

#### Scope

Per v4 §7.3, the eight speculative rules:

1. **`gradual_rms_trend`** — slope > 0.005 arcsec/min over ≥30 min.

2. **`out_of_band_spectrum_peaks`** — drive-type-aware. Replaces
   the v3-era ambiguous notation with explicit per-band predicates
   (CD-review correction). The rule needs a clear `in_band(p)`
   predicate AND an explicit seeing-band exclusion at < 5 s.

   For **worm mounts**:

   ```
   in_band(p) := any of:
       |p − worm|     / worm     ≤ 0.05    # fundamental ±5%
       |p − worm/2|   / (worm/2) ≤ 0.05    # 2nd harmonic ±5%
       |p − worm/3|   / (worm/3) ≤ 0.05    # 3rd harmonic ±5%
       |p − worm/4|   / (worm/4) ≤ 0.05    # 4th harmonic ±5%

   fires for peaks where:
       amp > 0.5″
       AND p ≥ 5 s        (excludes seeing band)
       AND ¬in_band(p)    (outside worm fundamental + first 3 harmonics)
   ```

   Summary: *"Periodic error at N seconds, M arcsec amplitude —
   outside the expected mechanical band for this worm-driven
   mount."* Suggests gearbox, belt, or motor anomalies.

   For **strain wave mounts**: same shape but with:
   - Higher amplitude threshold: **1.0 arcsec** (strain wave is
     intrinsically richer broadband content per ZWO + Rainbow
     Astro documentation)
   - In-band predicate is centered on `dominant_period_s` ± 50 %
     (or `expected_period_band_s` if `dominant_period_s` unknown)
     rather than worm + harmonics
   - **Softer language**: *"A periodic component at N seconds, M
     arcsec amplitude is not in this mount's typical period band.
     This may be a load-dependent strain wave variation rather
     than a fault."* Do NOT suggest mechanical fault — strain
     wave PE varying with load is documented behaviour.

   For **hybrid mounts** (`hybrid_strain_wave_ra` /
   `hybrid_strain_wave_ra_with_encoder`): apply the strain wave
   rule to the RA spectrum, the worm rule (with `dec_worm_period_s`)
   to the Dec spectrum.

   For **direct_drive_encoder mounts**: any peak > 1.0″ at p ≥ 5 s
   is anomalous. **Confident tier override** via the Rule
   Protocol's `tier_override(evidence)` method (the encoder mount
   itself isn't supposed to show discrete spectrum peaks at this
   amplitude). Summary: *"Periodic error detected — encoder-class
   mounts should not show discrete spectrum peaks at this
   amplitude."*

   For **unknown drive type**: fallback uses 100–800 s as the
   broad expected band, plus the seeing-band exclusion. Speculative
   tier with explicit "identify the mount in equipment for a more
   confident diagnosis" actionable.

3. **`strain_wave_load_balancing_recommendation`** (NEW per v4
   §7.3) — fires when strain wave PE amp > 1.5× manufacturer
   default; suggests balance/orientation check.
4. **`snr_variability`** — SNR std > 30% mean + lag-1 autocorr
   > 0.4.
5. **`possible_differential_flexure`** — guide-scope-only; both-
   axis sustained drift varying with pointing.
6. **`dec_oscillation_with_backlash_compensation`** — Dec osc >
   0.4 + `Backlash comp = enabled`.
7. **`low_snr_throughout`** — mean SNR < 10 without star loss.
8. **`high_rms_vs_rig_expected`** — requires rig context;
   `rms_total_arcsec > 3 × rig.effective_guide_precision_arcsec`.

##### Equipment-aware threshold scaling (§7.4)

When rig context present:
- `polar_alignment` threshold scales with `rig.effective_guide_precision_arcsec`
- `chasing_seeing_ra` oscillation threshold loosens for oversampled rigs
- `out_of_band` amplitude floor adjusts to rig's expected guide precision
- Strain-wave-specific rules become available

#### Tests (~25 new)

- 8 speculative rule fires tests
- 8 doesn't-fire-when-not-applicable tests
- 4 equipment-aware threshold tests
- 4 settings-tunable threshold tests
- 1 dismiss-finding UX test

---

### v0.33.0 — Multi-Log Comparison + Trends + DB-Backed History

**Status:** Planned
**Branch:** `v0.33.0/phd2-multi-log`
**Spec refs:** v4 §8.1, §8.2, §8.5

#### Goal

Move from one-log-at-a-time to session-over-time analysis. Users
with N logs see RMS trending, configuration drift, persistent vs
one-off diagnostics.

#### Scope

##### Second SQLite tier

New tables `phd2_analysis`, `phd2_analysis_section`,
`phd2_analysis_finding` for persisting derived metrics + findings
per parse (the per-frame samples remain re-parseable; only derived
data is stored).

##### Multi-log comparison view

New `/phd2-analyzer/compare` route. Select 2-20 logs from Recent.

- Side-by-side stats table (sortable)
- Trend chart (RMS Total vs date)
- Diagnostic-cooccurrence heatmap (rule_id × session)
- Configuration drift panel

##### DB-backed Recently Analyzed

Replaces v0.24.0's localStorage list for catalog users; adds rig
filter, date range, finding filter.

##### Multi-section finding correlation

Findings firing across multiple sessions get a "persistent"
banner with N/M sessions count.

#### Tests (~30 new)

---

### v0.34.0 — HTML Report + Per-Instance PE Corpus UI + Catalog Integration

**Status:** Planned
**Branch:** `v0.34.0/phd2-report-corpus`
**Spec refs:** v4 §8.3, §8.4, §8.6

#### Goal

Three cohesive features: self-contained HTML report (the killer
feature for forum sharing), per-mount-instance PE history view
(the payoff of v0.29.0's per-instance schema), and catalog
integration (when imaging-core lands).

#### Scope

##### §8.3 — HTML report export

`services/phd2_report.py` renders self-contained HTML (inline CSS,
inline SVG charts, no external refs). Frontend "Export report"
button.

##### §8.6 — Per-instance PE corpus UI

Mount Instance detail page shows:
- PE history scatter (period + amplitude over time, with rolling
  median + 1σ band)
- Drift-over-time alert (if trailing 30-day median shifted > 5%
  from prior 30-day median)
- "Compared to manufacturer default" panel
- Filter dimensions: declination, payload, pier side
- Optional "share with NightCrate community" button (manual,
  contributes anonymized data back to seed gaps for HEM44/HAE-
  series/SW Wave i)

##### §8.4 — Catalog integration

Conditional on imaging-core schema landing. Auto-association of
guide-log sections with overlapping imaging sessions; per-session
"Guiding" tab; per-sub-frame `potentially_affected` annotation.

#### Tests (~30 new)

---

### v0.35.0+ — Roadmap

Per spec v4 §9, the post-MVP features are listed but not planned
in detail in PLAN.md:

- v0.35.0 PHD2 Debug log parsing (§9.1)
- v0.36.0 Live JSON-RPC monitoring (§9.2)
- v0.37.0 AI-powered session analysis (§9.3) — paid feature
- v0.38.0 Parameter recommendations (§9.4) — deferred until AI
  analyzer provides uncertainty vehicle

Each gets its own spec when prioritized.

## Part 4 — Math appendix (full derivations, reproduced for CD)

This appendix consolidates every formula referenced in the version
plans above, with sources. CD can verify the math without diving
into the spec or PHDLogViewer source.

### M1 — RMS as standard deviation

PHDLogViewer's `LFit` class implements the West-incremental form
for streaming variance:

```
n_new = n + 1
delta = x − μ_old
μ_new = μ_old + delta / n_new
var_new = (n × var_old + delta × (x − μ_new)) / n_new
```

This is the population variance (1/N denominator):

$$\text{var}(x) = \frac{1}{N}\sum_{i=1}^{N}(x_i - \bar{x})^2$$

`RMS = sqrt(var)` is therefore standard deviation, NOT
RMS-from-zero. Difference between the two for series `[1, 2, 3]`:

- RMS-from-zero: `sqrt((1+4+9)/3) ≈ 2.16`
- Standard deviation: `sqrt(((1-2)² + (2-2)² + (3-2)²)/3) ≈ 0.82`

### M2 — Polar alignment from Dec drift

**Sources** (per CD-review correction; these are independent
references):

- **Barrett** ([celestialwonders.com](http://celestialwonders.com/articles/polaralignment/PolarAlignmentAccuracy.html))
  — derives the formula from small-angle geometry. Cited directly
  in PHDLogViewer's `AnalysisWin.cpp` line 166.
- **Starry Nights** ([starrynights.us](http://www.starrynights.us/Articles/Polar_Align.htm))
  — derives the same relationship empirically with a 0.262
  arcsec/min/arcmin coefficient at the celestial equator.

Both arrive at the same number to within rounding (`3.8197 = 60 /
15.71` vs `1 / 0.262 ≈ 3.8167`).

**Form 1 — arcsec/min:**

$$\alpha_{\text{arcmin}} = \frac{|\text{drift}|_{\text{arcsec/min}}}{0.262 \cdot \cos(\delta)}$$

**Form 2 — px/min (PHDLogViewer):**

Converting drift from arcsec/min to px/min via pixel_scale:

$$\alpha_{\text{arcmin}} = \frac{3.8197 \cdot \text{drift}_{\text{px/min}} \cdot \text{pixel\_scale}}{\cos(\delta)}$$

NightCrate uses PHDLogViewer's exact constant **3.8197** for
cross-tool alignment, citing Barrett (per PHDLogViewer's source-code
attribution).

### M3 — Dec drift unguided-frames-only accumulation

The y_accum sequence accumulates Dec position changes only when
the *previous* frame was unguided (decdur == 0). Those changes
reflect actual sky drift over the inter-frame interval. Frames
where the previous frame was guided are skipped because the
inter-frame change is dominated by the guide pulse.

The slope of `y_accum vs t` (linear regression `B = cov(t, y_accum)
/ var(t)`) gives the drift rate in px/sec; × 60 for px/min.

Edge cases: see v0.25.0 §M3 above.

### M4 — Scatter ellipse rotation Theta

PHDLogViewer's `LFit::Theta()`:

$$\theta = \text{atan2}(\text{cov}_{xy}, \text{var}_x)$$

NOT the textbook PCA rotation:

$$\theta_{\text{PCA}} = \frac{1}{2} \cdot \text{atan2}(2 \cdot \text{cov}_{xy}, \text{var}_x - \text{var}_y)$$

The two give similar rotations for highly elongated ellipses but
diverge for nearly-circular data. PHDLogViewer's simpler form is
what NightCrate uses.

### M5 — Hamming amplitude normalization 4/N

For a discrete sinusoid `x_i = A · cos(2π · k₀ · i / N)` windowed
by Hamming `w_i = 0.54 − 0.46 · cos(2π·i / (N−1))`:

Hamming coherent gain `G_c = mean(w_i) ≈ 0.54`.

Windowed signal's FFT magnitude at the tone's bin:

$$|X_{k_0}| \approx \frac{A \cdot N \cdot G_c}{2}$$

Solving for A:

$$A \approx \frac{2 \cdot |X_{k_0}|}{N \cdot G_c} \approx \frac{3.7 \cdot |X|}{N}$$

PHDLogViewer rounds to **4/N** (over-estimates by ~8%, but matches
PHDLogViewer for cross-tool consistency).

### M6 — MAD-based peak threshold

$$\text{MAD}(x) = \text{median}(|x_i - \text{median}(x)|)$$

For normal data: $\sigma \approx 1.4826 \cdot \text{MAD}$.

Threshold: $\text{median}(a) + 3 \cdot 1.4826 \cdot \text{MAD}(a)$.

Robust against outliers; produces zero peaks on flat noise floors.

### M7 — Sine wave amplitude / P-P / RMS

For a pure sine wave of amplitude A:

- Amplitude = A (peak from zero)
- Peak-to-peak = 2A
- RMS = A / √2 ≈ 0.7071 × A

Used in §6.1.7 cursor readout — directly from PHDLogViewer's
status bar formula.

### M8 — Unguided RA reconstruction recurrence

`move = raraw − prev_raraw − prev_raguide` cumulative sum.

Sign convention proof: PHD2's `RAGuideDistance` is the algorithm's
*desired change* in star position. Between consecutive frames:

$$\text{raraw}_{\text{next}} = \text{raraw}_{\text{prev}} + \text{raguide}_{\text{prev}} + \text{drift}_{\text{during}}$$

Solving for drift_during:

$$\text{drift}_{\text{during}} = \text{raraw}_{\text{next}} - \text{raraw}_{\text{prev}} - \text{raguide}_{\text{prev}} = \text{move}$$

So `rapos = Σ move_i` accumulates the unguided drift trajectory.

**Filter for the recurrence (post-CD-review):** keep frames where
`error_code == 0 AND ra_raw_px is not None` — matching
PHDLogViewer's `Include() = e.included && StarWasFound(e.err)`.
**Mount-kind-agnostic:** AO frames with valid star data accumulate
alongside Mount frames. The AO's correction is captured in
`ra_guide_px` exactly like a Mount pulse, and the recurrence
correctly backs out both. DROP frames are filtered by the null
check. The earlier draft of this filter incorrectly excluded AO
frames via a `mount_kind != "Mount"` check; that's been removed.

### M9 — Akima spline (vs cubic spline)

GSL's `gsl_interp_akima` — non-overshooting piecewise polynomial
by Hiroshi Akima (1970). Cubic spline can introduce spurious
oscillations between sample points; Akima uses a local stencil
that adapts to the local data behavior.

For PHD2 spectrum analysis: input is already oscillatory (mount
PE), and a cubic spline interpolator would risk amplifying high-
frequency content that doesn't exist. NightCrate uses
`scipy.interpolate.Akima1DInterpolator` for this reason.

### M10 — Guiding PE suppression ratio (v0.31.0 confident rule input)

$$\text{suppression} = 1 - \frac{a_{\text{raw}}(p_{\text{PE}})}{a_{\text{unguided}}(p_{\text{PE}})}$$

Where:
- `a_raw(p_PE)` is the RA spectrum amplitude at the dominant PE
  period
- `a_unguided(p_PE)` is the unguided RA spectrum amplitude at that
  period

Range: 0 (guiding suppresses nothing) to 1 (guiding suppresses
everything). Expected for well-tuned worm mount: 0.85-0.95. For
strain wave: 0.5-0.8 (PE less repeatable, harder to guide out).

The `guiding_pe_suppression_low` rule fires when suppression < 0.5
AND `pe_amplitude_arcsec ≥ 1.5` (mount has measurable PE).

### M11 — Strain wave PE periods (manufacturer-sourced)

| Mount | Period (s) | Source |
|---|---|---|
| ZWO AM3/AM5/AM5N | 288 | Cloudy Nights community consensus, ZWO docs |
| Rainbow Astro RST-135 | 430 | Rainbow Astro FAQ (manufacturer-stated) |
| Pegasus Astro NYX-101 | 430 | Pegasus Astro guide (manufacturer-stated) |
| iOptron HEM27 | 360 (RA) / 600 (Dec, GEM28 worm inherited) | High Point listing + PHD2 forum |

Strain wave PE is **load- and direction-dependent** per ZWO and
Rainbow Astro documentation — cycle is less repeatable than worm
gear cycles. Manufacturer-stated periods are *defaults*; per-
instance measured periods supersede them when ≥3 stable measurements
exist (v0.29.0 override behavior).

## Part 5 — CD-review resolutions (questions closed)

The five open questions in the prior draft were all resolved by
CD's review. Decisions baked into the plan:

1. **scipy as a backend dependency** (v0.26.0): **Approved.** Pin
   `scipy>=1.11` (no upper bound). Akima1DInterpolator is stable
   since 1.4; scipy is already in the transitive tree via astropy.
   Akima is the right interpolant for oscillatory data per spec
   §11.13.

2. **MeasuredPe persistence cadence** (v0.29.0): **Auto-persist.**
   Idempotent UNIQUE means duplicates are impossible. Don't
   preemptively add an opt-out toggle — add it later if users
   object.

3. **Mount instance backfill on existing rigs** (v0.29.0):
   **Auto-create with `(auto)` suffix.** Asks-user friction at
   first-open is much higher than the cost of letting users
   ignore an auto-named instance.

4. **Tier override pattern** (v0.31.0 / v0.32.0): **Bake into
   v0.31.0's Rule Protocol.** Every rule has an optional
   `tier_override(evidence) -> Literal['confident', 'speculative']
   | None` method; default returns `None` (use rule's default
   tier). Used by `out_of_band_spectrum_peaks` in v0.32.0 to
   elevate direct-drive-encoder peaks to confident tier.

5. **scipy version pin** (v0.26.0): `scipy>=1.11` no upper bound.

## Part 5b — Caveats and known approximations

### Cadence guard threshold (v0.26.0)

PHDLogViewer doesn't have a cadence guard at all in
`AnalysisWin.cpp` — it interpolates and FFTs whatever it gets.
Spec v4 §6.1.1 step 2 says "if cadence varies more than 20%
across the section, the FFT input is meaningless even after
interpolation. Skip and warn" but doesn't specify how to measure
variation.

The plan's choice (`IQR(dt) / median(dt) > 0.20`) is robust
against DROP-frame gaps — a plain `std(dt) / mean(dt)` triggers
on the wide outlier dts even when the underlying exposure
cadence is perfectly uniform. **CD-review note:** this threshold
should be tested against the ASIAir sample log during v0.26.0
implementation to confirm it doesn't false-positive on valid
sessions. If it does, raise the threshold to 0.30 or 0.40 — the
goal is to catch only genuinely bimodal cadences (mixed-exposure
multi-target sessions), not occasional DROP gaps.

If cross-tool consistency demands matching PHDLogViewer's behaviour
exactly (FFT every section regardless of cadence variation), drop
the guard entirely and rely on the section-too-short warnings
to flag low-confidence outputs.

## Part 6 — Final notes

- Total versions: 10 + roadmap. Each is shippable standalone.
- No version requires the previous one to compile or test (each
  branches cleanly off the prior version's main merge).
- The throwaway directive on the in-flight v0.25.0 branch means
  the implementer should expect to revert all PHD2 changes back
  to v0.24.0's state before beginning v0.25.0 work. Migration 0024
  + seed CSV worm periods + Mount form fields can be re-added in
  v0.26.0 (where worm markers actually ship), or kept on the
  branch as "infrastructure already there."
- The Math appendix in Part 4 is the canonical derivation source
  for CD review. The version-specific math sub-sections in Part 3
  are excerpted from there.
- Implementation-time verification: every formula has a test that
  compares the output against a hand-computed value or against
  PHDLogViewer's reported value for the ASIAir sample log. Cross-
  tool consistency is a hard requirement.
