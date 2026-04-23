# Target Planner — Scoring Algorithm

**NightCrate version:** 0.21.0
**Implementation:** `backend/src/nightcrate/services/planner_scoring.py`
**Settings:** `Settings.scoring_*` fields in `core/config.py`
**UI:** Settings → Planner Scoring (collapsible sub-sections).

---

## 1. What the score answers

The Target Planner's per-target **quality score** (0–100, plus a
categorical chip `Excellent` / `Good` / `Fair` / `Poor`) answers a
single question:

> **"How good a target is this for tonight's session, given my
> equipment and what I plan to capture?"**

It's computed for every target in tonight's candidate set (location,
date, horizon), and refreshes on every change to the session's
inputs (rig, filter intent, scoring settings). It is **opinionated
by default, and fully overridable** — every weight, threshold, and
sensitivity is a user setting with a defensible default rooted in
physics or community consensus.

The score is **not computed in Anytime mode** — that mode is a pure
catalog browser with no location / visibility / moon context.

---

## 2. Conceptual model — two stages

```
Stage 1: Hard gates.
  - min observable hours during astro-dark
  - above the custom horizon at all
  - max coverage % (optional, disabled by default)

  Pass all gates? -- no --> score = "—" (not scored)

  Pass → Stage 2.

Stage 2: Four quality dimensions, each 0–1.
  - Observability   — altitude-weighted hours during astro-dark
  - Meridian timing — peak altitude vs midnight of astro-dark
  - Moon impact     — phase × proximity × filter sensitivity
  - Frame fit       — Gaussian on FOV coverage %

Stage 3: Weighted geometric mean → 0–100 → quality chip.
```

**Why geometric mean?** It punishes weakness in any one dimension.
A target that's 0.95 on three dimensions but 0.20 on a fourth ranks
*below* one that's 0.70 across the board — matching the lived
experience that "the target with one bad property is rarely the
best choice."

**Why separate gates from dimensions?** A "—" is unambiguous ("this
isn't a scoreable target tonight"); a 0 score would invite the user
to wonder whether the algorithm is broken or whether the target is
just *that* bad. Hard gates also let the breakdown panel give a
clean explanation ("blocked by your tree line all night") instead
of a numerical rationale.

---

## 3. The four quality dimensions

### 3.1 Observability — how much *high-quality* time

**What it measures:** hours above the horizon during astro-dark,
weighted by altitude. Time at 80° counts more than time at 35°
because the atmosphere is thinner, seeing is better, light
pollution is lower, and extinction is milder.

**How it's calculated.** For each time sample where the target is
above both the custom horizon AND the scoring minimum altitude
(default 30°), we compute the airmass and map it to a 0–1 quality
via

$$
q(t) \;=\; \max\!\left(0,\; 1 - \frac{X(t) - 1}{X_{\max} - 1}\right)
$$

where the airmass $X(t) = 1 / \sin(\mathrm{alt}(t))$ and the
airmass cap is anchored to the minimum-altitude threshold:

$$
X_{\max} \;=\; \frac{1}{\sin(\mathrm{alt}_{\min})}
$$

The dimension score is the mean of $q(t)$ across the usable samples:

$$
S_{\mathrm{obs}} \;=\; \frac{1}{|\mathcal{T}_{\mathrm{usable}}|} \sum_{t \in \mathcal{T}_{\mathrm{usable}}} q(t)
$$

| Altitude | Airmass | Quality |
|---|---|---|
| 90° | 1.00 | 1.00 |
| 60° | 1.15 | 0.85 |
| 45° | 1.41 | 0.59 |
| 30° | 2.00 | 0.00 |

### 3.2 Meridian timing — peak vs dark midpoint

**What it measures:** whether the target's peak altitude falls near
the middle of astro-dark. The astrophotographer's intuition is
*"best images come from when the target is highest in the sky, and
ideally it's highest right when the sky is darkest."*

**How it's calculated.** Let $t_{\mathrm{peak}}$ be the time of
peak altitude (the meridian transit when it falls inside astro-dark,
otherwise the higher-altitude dark-window endpoint), $t_{\mathrm{mid}}$
the midpoint of the dark window, and $T_{\mathrm{dark}}$ the dark-
window duration. Then

$$
\Delta \;=\; \lvert t_{\mathrm{peak}} - t_{\mathrm{mid}} \rvert
$$

$$
S_{\mathrm{mer}} \;=\; \max\!\left(0,\; 1 - \frac{\Delta}{T_{\mathrm{dark}} / 2}\right)
$$

A target that transits at dark midnight scores 1.0. A target that
transits at dark start or dark end scores 0. A target that transits
1 h after midpoint of a 6-h dark window scores 0.67.

### 3.3 Moon impact — phase, proximity, filter sensitivity

**What it measures:** how much tonight's moon will degrade the
target under the user's selected filters.

**Filter intent** is a multi-select on the planner page: `Ha`,
`SII`, `OIII`, `L`, `R`, `G`, `B`. A dual-band filter is represented
by selecting multiple lines (L-eXtreme is modeled as Ha together
with OIII).

**The limiting-filter rule.** When multiple filters are selected,
the *most moon-sensitive* one bounds the whole session. A session
capturing L, R, G, B, and Ha together is functionally a broadband
session with bonus Ha — the broadband channels dominate the moon
problem. It would be wrong to average down the broadband penalty
by including Ha.

**Per-timestep impact.** With the limiting filter's sensitivity $s$
and minimum separation threshold $\sigma_{\min}$, the moon's
illuminated fraction $\phi \in [0, 1]$, its altitude
$\alpha_{\mathrm{moon}}(t)$, and the target–moon separation
$\sigma(t)$:

$$
p(t) \;=\; \min\!\left(1,\; \frac{\sigma(t)}{\sigma_{\min}}\right)
$$

$$
I(t) \;=\; s \cdot \phi \cdot \sqrt{\sin(\alpha_{\mathrm{moon}}(t))} \cdot \bigl(1 - p(t)\bigr)
$$

The square root on the altitude factor is intentional: it gives a
gentler curve than a linear $\sin$ and reflects that even a low
moon contributes meaningfully to skyglow via Rayleigh scattering,
not just direct illumination.

**Aggregation across the observation window.** Let
$\mathcal{T}_{\mathrm{obs}}$ be the samples where the target is
visible and $\mathcal{T}_{\uparrow}$ the subset where the moon is
also above the horizon. The fraction of the obs window with the
moon up is

$$
f_{\uparrow} \;=\; \frac{\lvert \mathcal{T}_{\uparrow} \rvert}{\lvert \mathcal{T}_{\mathrm{obs}} \rvert}
$$

and the mean impact (over moon-up samples only) is

$$
\overline{I} \;=\; \frac{1}{\lvert \mathcal{T}_{\uparrow} \rvert} \sum_{t \in \mathcal{T}_{\uparrow}} I(t)
$$

The dimension score, with the cluster modifier $\kappa \in [0, 1]$
applied when applicable, is

$$
S_{\mathrm{moon}} \;=\; 1 \;-\; \kappa \cdot \overline{I} \cdot f_{\uparrow}
$$

**Cluster softening.** Open clusters (`OCl`), globular clusters
(`GCl`), and stellar associations (`*Ass`) tolerate moonlit
broadband imaging much better than faint extended emission
targets. For those object types, $\kappa$ defaults to 0.5 (the
`scoring_cluster_moon_modifier` setting); for all others, $\kappa = 1$.
This reflects well-established community wisdom: globulars and
bright open clusters are the canonical "shoot during full moon"
targets.

**No filter intent declared implies $S_{\mathrm{moon}} = 1$.**
Without knowing what the user is capturing, the planner can't
reasonably score moon impact; the dimension drops out of
differentiation. The same fallback applies when the moon is below
the horizon for the entire observation window, or at new moon.

### 3.4 Frame fit — Gaussian on FOV coverage

**What it measures:** how well the target fills the camera's field
of view in the selected rig. Reuses the planner's existing
`coverage_pct` calculation.

**How it's calculated.** A Gaussian centered on the user's
preferred coverage percentage. With coverage $c$, ideal target
coverage $c_{\mathrm{ideal}}$, and spread $\sigma$:

$$
S_{\mathrm{fit}} \;=\; \exp\!\left(-\left(\frac{c - c_{\mathrm{ideal}}}{\sigma}\right)^{2}\right)
$$

Default ($c_{\mathrm{ideal}} = 55\%$, $\sigma = 35$):

| Coverage | Score |
|---|---|
| 5% | 0.04 |
| 20% | 0.34 |
| 40% | 0.84 |
| 55% | 1.00 |
| 70% | 0.84 |
| 100% | 0.21 |
| 130% | 0.02 |

**The two tuning knobs reshape this curve:**

- Bigger `ideal` rewards larger targets (mosaic enthusiast at 130%).
- Smaller `ideal` rewards smaller targets (galaxy hunter at 15%).
- Smaller `spread` is more demanding (tight-crop framer).
- Larger `spread` is more forgiving (wide-context shooter).

**When no rig is selected**, the frame-fit dimension drops out and
the other three dimensions combine with their weights renormalized.

---

## 4. Combination — weighted geometric mean

With dimension scores $s_{i} \in [0, 1]$ and non-negative weights
$w_{i}$:

$$
S \;=\; \left(\prod_{i} s_{i}^{\,w_{i}}\right)^{1 / \sum_{i} w_{i}}
$$

$$
\mathrm{score}_{\mathrm{pct}} \;=\; \mathrm{round}(100 \cdot S)
$$

Weights with value 0 remove a dimension entirely. Dropped
dimensions (frame-fit when no rig; moon when no filter intent)
don't appear in the formula at all; the remaining dimensions'
weights renormalize automatically because $\sum_{i} w_{i}$ in the
denominator is computed over the active dimensions only.

---

## 5. Quality chip labels

| Score | Label | Palette |
|---|---|---|
| ≥ `threshold_excellent` (80) | Excellent | saturated blue |
| ≥ `threshold_good` (60) | Good | lighter blue |
| ≥ `threshold_fair` (40) | Fair | neutral gray |
| below | Poor | muted orange |

All colorblind-safe — **no red / green anywhere.** The palette
mirrors the rig-calculator guide-suitability palette (blue /
orange / gray).

---

## 6. Tunable parameters

All of these live in Settings → Planner Scoring with a tooltip and
a slider / input. Defaults reflect community consensus and physics.

### Combination weights

| Parameter | Default | Meaning |
|---|---|---|
| `scoring_weight_observability` | 2.0 | Most important — can't fix a target that's barely up |
| `scoring_weight_meridian` | 1.0 | Tiebreaker between comparable targets |
| `scoring_weight_moon` | 1.5 | Varies most night-to-night |
| `scoring_weight_frame_fit` | 1.0 | Tiebreaker via composition |

### Moon filter sensitivities

| Parameter | Default | Notes |
|---|---|---|
| `scoring_moon_sensitivity_ha` | 0.15 | Deep red narrowband — very tolerant |
| `scoring_moon_sensitivity_sii` | 0.25 | Deep red, slightly more exposed |
| `scoring_moon_sensitivity_oiii` | 0.70 | Blue-green, hurt by Rayleigh scattering |
| `scoring_moon_sensitivity_l` | 0.95 | Full broadband |
| `scoring_moon_sensitivity_r` | 0.55 | Broadband red tolerates better |
| `scoring_moon_sensitivity_g` | 0.85 | Near moonlight's peak |
| `scoring_moon_sensitivity_b` | 1.00 | Most affected — shortest wavelength |

### Moon minimum separations

| Parameter | Default | Rationale |
|---|---|---|
| `scoring_moon_min_sep_ha` | 60° | Community rule of thumb |
| `scoring_moon_min_sep_sii` | 60° | Same as Ha |
| `scoring_moon_min_sep_oiii` | 90° | Stricter because OIII is sensitive |
| `scoring_moon_min_sep_l` | 90° | Broadband rule of thumb |
| `scoring_moon_min_sep_r` | 60° | Red has less Rayleigh scattering |
| `scoring_moon_min_sep_g` | 90° | Broadband rule of thumb |
| `scoring_moon_min_sep_b` | 90° | Most-affected broadband |

### Other

| Parameter | Default | Meaning |
|---|---|---|
| `scoring_cluster_moon_modifier` | 0.5 | Cluster impact multiplier (OCl / GCl / \*Ass) |
| `scoring_observability_min_altitude_deg` | 30° | Usable-altitude plus airmass-cap anchor |
| `scoring_frame_fit_ideal_coverage_pct` | 55% | Coverage that scores 1.0 |
| `scoring_frame_fit_spread` | 35 | Width of the Gaussian |
| `scoring_threshold_excellent` | 80 | Chip boundary |
| `scoring_threshold_good` | 60 | Chip boundary |
| `scoring_threshold_fair` | 40 | Chip boundary |
| `scoring_gate_min_obs_hours` | 1.0 h | Below this is unscored |
| `scoring_gate_max_coverage_pct` | `None` (off) | Coverage cap; off by default |

---

## 7. Worked examples

All three use the default weights (2, 1, 1.5, 1) unless noted.

### Example 1 — M42 in Askar V @ 600 mm on a new-moon January night

- Location: Phoenix, AZ
- Astro-dark window: 18:54 → 05:48 (~11 h)
- Moon: 5%, sets at 19:30
- Telescope: Askar V at 600 mm
- Camera: ZWO ASI 2600MM Pro (APS-C mono, 23.5 × 15.7 mm)
- Rig FOV: ~127′ × 85′
- M42 angular size: 85′ × 60′ → **coverage 100%**
- Filter intent: **Ha, SII, OIII** (SHO session)

**Per-dimension scores:**

- Observability ≈ 0.78 — 7 h above 30°, peak 58°
- Meridian timing ≈ 0.88 — transit 23:42 local, dark midpoint 00:21
- Moon impact ≈ 1.00 — moon sets before the obs window starts
- Frame fit ≈ 0.19 — coverage 100% is well past the 55% ideal

**Combined:** ~65 → **Good**

**Reading:** frame fit is the killer — M42 overfills the Askar V,
and the geometric mean correctly penalizes it. A user with
`scoring_frame_fit_ideal_coverage_pct = 100` (tight-crop framer)
would see this score jump dramatically.

### Example 2 — Same M42, same night, but in a C11

Only change: rig = Celestron C11 at native focal length (2800 mm,
f/10), same ZWO ASI 2600MM Pro camera. Rig FOV ≈ 29′ × 19′; M42's
85′ major axis gives **coverage ~ 500%**.

- Frame fit ≈ 0 (far past the right tail of the Gaussian)
- Other dimensions unchanged

**Combined:** ~0 → **Poor**

**Reading:** correctly tells the user "M42 in a C11 is a mosaic
project, not a single-frame target." A user with
`scoring_frame_fit_ideal_coverage_pct = 500` would see this recover.

### Example 3 — NGC 7000 in Askar V @ 400 mm, August, full moon, Ha only

- Location: Phoenix, AZ
- Astro-dark window: 21:34 → 04:32 (~7 h)
- Moon: 100%, up all night, mean separation 95°
- Telescope: Askar V at 400 mm (with reducer)
- Camera: ZWO ASI 2600MM Pro (APS-C mono, 23.5 × 15.7 mm)
- Rig FOV: ~191′ × 127′
- NGC 7000 size: 120′ × 100′ → **coverage 94%**
- Filter intent: **Ha only** (broadband would be hopeless)

**Per-dimension scores:**

- Observability ≈ 0.85 — solid altitudes
- Meridian timing ≈ 0.50 — transit 23:18, dark midpoint 01:03
  (1.75 h before)
- Moon impact ≈ 1.00 — Ha's low sensitivity and 95° separation
  together wipe the penalty
- Frame fit ≈ 0.29 — 94% is past the sweet spot

**Combined:** ~66 → **Good**

**Reading:** even under a full moon, Ha-only with far-from-moon
target produces a near-perfect moon score. The score is dragged
down by meridian timing (transit before dark midpoint) and frame
fit. A user who added OIII to the filter intent would see this
collapse because OIII would become the limiting filter and the
moon penalty would spike.

---

## 8. Tuning playbook

**I want to favor high-altitude targets.**
Raise `scoring_weight_observability` (e.g., 3.0 from 2.0).

**I only shoot Ha and don't care about the moon.**
Set `scoring_weight_moon = 0`. Or set
`scoring_moon_sensitivity_ha = 0`.

**I never want to see mosaic-scale targets in the score.**
Set `scoring_gate_max_coverage_pct = 100`. Targets above 100%
coverage will be gated out.

**I shoot from a dark site — my OIII handles moonlight well.**
Lower `scoring_moon_sensitivity_oiii` (e.g., from 0.70 to 0.40).

**I don't care where a target transits, only that it's up.**
Set `scoring_weight_meridian = 0`.

**Composition matters more to me than anything else.**
Raise `scoring_weight_frame_fit` (e.g., 3.0) and narrow
`scoring_frame_fit_spread` (e.g., 20) to punish any deviation from
ideal.

**I want the Excellent label to be rare.**
Raise `scoring_threshold_excellent` (e.g., from 80 to 90).

**I find the cluster modifier too aggressive.**
Lower `scoring_cluster_moon_modifier` (e.g., 0.3).

**I find it not aggressive enough.**
Raise it toward 1.0, which disables the softening entirely.

---

## 9. Colorblind-safe palette rationale

Fred is red-green color blind, which rules out the usual
red-for-bad / green-for-good convention. The score chip palette
uses **blue-for-good, orange-for-poor, neutral gray for middle**:

- **Excellent:** saturated blue (`#1976d2`)
- **Good:** lighter blue (`#64b5f6`)
- **Fair:** neutral gray (`#9e9e9e`)
- **Poor:** muted orange (`#ed6c02`)

This mirrors the rig-calculator guide-suitability palette
(`ratingColor` in `lib/rigColors.ts`) so the application feels
consistent, and every color is distinguishable even with
deuteranopia or protanopia.

---

## 10. What's explicitly out of scope

The scoring layer is deliberately narrow. It does **not** consider:

- Weather (cloud forecast, humidity, dew, seeing) — separate Weather
  feature
- Transparency / light-pollution level (SQM / Bortle)
- Imaging history (which targets the user has already captured)
- Integration-time estimation
- Multi-night scoring (this target vs next week)
- Filter-sequencer integration

These are future planner features that may build on this scoring
layer; they don't require changes to this spec.
