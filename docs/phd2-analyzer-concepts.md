# NightCrate PHD2 Analyzer — Concepts and Math

This document explains how the NightCrate PHD2 Guide Log Analyzer computes everything it shows you — the numbers in the stats panel, the shapes you see in the spectrum, the diagnoses it surfaces, and the periodic-error measurements it tracks over time.

It's written for astrophotographers, not software engineers. There's math in here, but every formula comes with a plain-English explanation of what it means and why it matters for your guiding.

If you've ever wondered:

- What "RMS" actually measures
- Why the spectrum chart shows what it shows
- How polar alignment error is estimated from drift
- How periodic error is reconstructed from a guided session
- Why strain wave mounts get treated differently from worm gear mounts
- How the "is my guiding actually working" diagnostic decides

…this is the document for you.

The analyzer is built to match the de facto reference tool, [PHDLogViewer](https://adgsoftware.com/phd2utils/) by Andy Galasso, formula-for-formula. If you cross-reference NightCrate's reported numbers against PHDLogViewer for the same log, they should agree. Where the two tools differ — for example, in the diagnostic engine that's unique to NightCrate — this document calls that out.

---

## Table of contents

1. The PHD2 guide log — what we're analyzing
2. The "included frames" filter — the foundation
3. Per-section metrics — RMS, peak, drift, oscillation, polar alignment, scatter ellipse
4. Frequency analysis — what the spectrum shows and how it's computed
5. Unguided RA reconstruction — seeing your mount without the guide corrections
6. Periodic error measurement — turning the spectrum into a structured number
7. Equipment-aware spectrum markers — worm vs strain wave vs hybrid
8. Guiding Assistant sections — special handling for the GA tool
9. Two-tier diagnostics — confident findings vs speculative hypotheses
10. Multi-log analysis — trends, comparisons, per-instance PE history
11. References and further reading

---

## 1. The PHD2 guide log — what we're analyzing

A PHD2 guide log is a plain text file that PHD2 writes during every guiding or calibration session. It contains a structured record of what your mount, guide camera, and guiding algorithms did frame-by-frame. The default location is `~/Documents/PHD2/` on Mac and Windows; ASIAIR users get one bundled with each session export.

### 1.1 What's in a log file

Each log file contains zero or more **sections**, freely interleaved. A section is either:

- A **calibration section** — recording the steps PHD2 took to learn your mount's geometry (one row per calibration step, with `Direction`, `Step`, `dx`, `dy`, etc.)
- A **guiding section** — recording every guide frame during an actual guiding run (one row per frame, with `RARawDistance`, `DECRawDistance`, `RADuration`, `RADirection`, `SNR`, `StarMass`, etc.)

A long observing night might produce a single log file with many sections in it, including re-calibrations and multiple guiding runs across different targets.

### 1.2 What "raw distance" means

The two numbers you'll see most often in this document are `RARawDistance` and `DECRawDistance`. These are PHD2's measurement of where the guide star was, relative to where it should be (the "lock position"), projected onto the mount's RA and Dec axes — measured in **guide camera pixels**.

- A positive `RARawDistance` means the star drifted away from the lock position in one direction along the RA axis; negative means the other.
- Same for Dec.
- The unit conversion to arcseconds uses the **pixel scale** declared in the section header: $\text{arcsec} = \text{pixels} \times \text{pixel\_scale}$, where pixel_scale is in arcsec/pixel for the guide camera.

NightCrate stores everything in pixels internally and converts to arcsec at display time. This matches PHD2's own convention and means switching between pixel and arcsec views never loses precision.

### 1.3 What "guide distance" means

`RAGuideDistance` and `DECGuideDistance` are different from raw distance. They're the **output of the guide algorithm** — how much PHD2 wanted to push the mount that frame, in pixel-space, after applying things like minimum-move thresholds, hysteresis, predictive PEC, and so on.

`RADuration` and `DECDuration` are the actual pulse durations PHD2 sent to the mount (in milliseconds), and `RADirection` / `DECDirection` indicate the sign (`E`/`W` or `N`/`S`). When `RADuration == 0`, no pulse was sent — usually because the algorithm decided the move was below its minimum threshold.

### 1.4 What "DROP" frames are

When PHD2 can't find the guide star on a frame (clouds, dew, focus shift, satellite, cosmic ray on the sensor), it logs that frame with `mount = "DROP"` and an `ErrorCode != 0`. The position fields are blank — there's no measurement to record.

The analyzer treats DROP frames as **missing data**, not as zero. Coercing them to zero would make your guiding look spuriously perfect during outages.

### 1.5 What dither and settle are

When your imaging app (NINA, ASIAIR, SGPro, etc.) finishes a sub-exposure, it tells PHD2 to dither — to deliberately move the guide star a small distance so that the next sub is pointed slightly differently. This breaks up sensor noise patterns when frames are stacked.

After the dither, PHD2 settles — waits for the star to stabilize within a small radius before reporting "I'm guiding again, you can start the next sub." Settle is a transient state where the star is bouncing around as the algorithm catches up.

Your imaging app emits `INFO: SETTLING STATE CHANGE, Settling started` and `Settling complete` lines into the log around each settle period. The analyzer detects these and **excludes settle frames from all statistics by default** — including RMS, peak, drift, and the FFT input. This matches PHD2's own internal convention: settle excursions are not failures of guiding, they're deliberate moves.

If your imaging app doesn't emit those events (some don't), the analyzer falls back to a heuristic: starting from the frame after each `INFO: DITHER by ...` line, exclude frames until the star settles below 0.5 px for 3 consecutive frames or 30 seconds elapses (all defaults are configurable).

---

## 2. The "included frames" filter — the foundation

Almost every metric and chart in the analyzer is computed over the **included** frames in a section. A frame is included when **all** of these are true:

$$\text{Include}(i) \iff \text{StarFound}(i) \wedge \neg\text{DROP}(i) \wedge \neg\text{InSettle}(i) \wedge \neg\text{UserExcluded}(i)$$

Plain English:

- The star was found (no `ErrorCode` indicating star loss)
- The frame wasn't a DROP frame
- The frame isn't inside a settle period (per §1.5)
- You haven't manually excluded it via shift+alt-drag on the time-series chart

This filter is the same one PHDLogViewer uses (with the addition of NightCrate-specific user exclusion). When you select a region on the time-series chart by shift-dragging, every metric in the stats panel and every chart in the analyzer recomputes against the new included set. The selection is per-frame: you can select multiple disjoint regions, exclude smaller regions inside them, and the metrics will follow your selection exactly.

Why this matters for interpreting numbers: when someone reports an RMS of "0.5 arcsec" for their guiding, they're reporting RMS over the included frames in the section they were looking at — typically with settle excluded. Two people analyzing the same log can report different RMS values if one of them includes settle and the other doesn't, or if they're looking at different time windows.

---

## 3. Per-section metrics

These are the numbers that appear in the stats panel for each section. All metrics are reported in both pixels and arcsec (using the section's declared pixel scale).

### 3.1 RMS — the headline number

RMS is the most-cited number in any guiding discussion. Lower is better. It measures how much the guide star wandered around its lock position over the course of the section.

The formula is the **standard deviation** of the raw distance series:

$$\text{RMS}_{\text{RA}} = \sqrt{\frac{1}{N}\sum_{i=1}^{N}(x_i - \bar{x})^2}$$

where $x_i$ is `RARawDistance` for frame *i*, $\bar{x}$ is the mean of the included frames, and *N* is the count of included frames. Same form for Dec. Total RMS combines them:

$$\text{RMS}_{\text{Total}} = \sqrt{\text{RMS}_{\text{RA}}^2 + \text{RMS}_{\text{Dec}}^2}$$

**Important: this is standard deviation, not "RMS-from-zero"**. The two are different when there's a systematic offset:

- **Standard deviation** (what we and PHDLogViewer report) measures spread *around the mean*.
- **RMS-from-zero** (what some other tools report) measures distance *from zero*.

For a series like `[1, 2, 3]`:
- Standard deviation = $\sqrt{((1-2)^2 + 0 + (3-2)^2)/3} = \sqrt{2/3} \approx 0.82$
- RMS-from-zero = $\sqrt{(1+4+9)/3} \approx 2.16$

If your guiding has a sustained offset (a slow drift you haven't fully damped), standard deviation reports a smaller number than RMS-from-zero. This is the right convention because the spread around the local mean is what actually matters for star roundness in your sub-exposures — a sustained slow offset just shifts where the star sits, but doesn't smear it.

If you compare numbers across tools and find a discrepancy, this is the most likely cause.

### 3.2 Peak — the worst single excursion

Peak is the single most-extreme value of `RARawDistance` (or `DECRawDistance`) in the included frames, **with sign preserved**:

$$\text{Peak}_{\text{RA}} = x_j \quad \text{where} \quad |x_j| = \max_i |x_i|$$

So `Peak RA = -2.3 arcsec` means the largest excursion was 2.3 arcsec in the negative direction. This is more useful than reporting the absolute value because the sign tells you which way the star went.

Peak is heavily influenced by single-frame outliers (a satellite passing through the guide star, a brief seeing burst). If you have a section with 1.0 arcsec RMS but a 5 arcsec peak, that single outlier is doing something to your data — but it's not necessarily affecting your sub-exposures, because one bad guide frame typically doesn't propagate into a noticeable smear unless it's an actual mount jolt.

### 3.3 Drift — the slow trend

Drift measures how much the guide star slowly walks away from the lock position over the section. It's reported in arcsec/minute (the conventional unit; PHDLogViewer uses pixels/minute internally).

**RA drift** uses a corrections-aware formula. Total RA position change over the section equals total mount drift plus total guide correction:

$$\Delta x_{\text{measured}} = \Delta x_{\text{drift}} + \sum_i \text{RAGuideDistance}_i$$

Solving for drift rate:

$$\text{drift}_{\text{RA}} = \frac{(x_{\text{last}} - x_{\text{first}}) - \sum_i \text{RAGuideDistance}_i}{t_{\text{last}} - t_{\text{first}}}$$

This matters because if your guide algorithm is successfully damping the drift, a naive linear regression on the raw position would report drift ≈ 0 (the algorithm is keeping the star close to the lock position). The corrections-subtraction form recovers the **mount's actual drift**, even when guiding is masking it.

**Dec drift** uses a different approach because Dec is typically guided in only one direction (or both, with backlash issues). Summing corrections doesn't work cleanly. Instead, the algorithm accumulates Dec position changes only across frames where the previous frame was unguided (i.e., `DECDuration` was zero on the previous frame). Those frames reflect actual sky drift, not algorithm reactions.

The accumulated `y_accum` series is then linear-regressed against time, and the slope is the drift rate:

$$\text{drift}_{\text{Dec}} = B \quad \text{where } B = \frac{\text{cov}(t, y_{\text{accum}})}{\text{var}(t)}$$

(`B` is the standard ordinary-least-squares regression slope.)

This complicated treatment is necessary for Dec because in many setups Dec is guided unidirectionally (the user has it set to "North only" or "South only" to avoid backlash on direction reversals), and the simple corrections-subtraction approach would give wrong answers in those cases.

### 3.4 Oscillation — chasing the seeing

The oscillation metric is the fraction of consecutive frame pairs where the sign of `RARawDistance` reverses:

$$\text{ra\_oscillation} = \frac{|\{i : \text{sign}(x_i) \neq \text{sign}(x_{i-1})\}|}{N - 1}$$

For pure white noise (each frame independent), the expected value is 0.5. Values:

- **~0.5** → algorithm is reacting to atmospheric seeing rather than mount mechanics. This is "chasing the seeing" — the guide algorithm is making a correction every other frame because the star is just bouncing around in turbulence.
- **~0.3** → typical of well-tuned guiding. The algorithm is correctly damping high-frequency components and only reacting to real mount drift.
- **<0.2** → algorithm is heavily damped, possibly to the point of missing real drift events.

Same calculation for Dec, though Dec oscillation is rarely large unless backlash compensation is over-tuned.

### 3.5 Polar alignment error from Dec drift

If your polar alignment is off, the Dec axis drifts at a rate that's proportional to the misalignment. The relationship comes from sidereal geometry: a misaligned mount tracks along an axis that's tilted from true north (or south), so as it tracks east-to-west it slowly walks the star up or down in declination.

The formula, due to [Frank Barrett](http://celestialwonders.com/articles/polaralignment/PolarAlignmentAccuracy.html):

$$\alpha_{\text{arcmin}} = 3.8197 \cdot \frac{|\text{drift}_{\text{Dec}}|_{\text{px/min}} \cdot \text{pixel\_scale}}{\cos(\delta)}$$

where:

- $\alpha_{\text{arcmin}}$ is the polar alignment error, in arcminutes
- $\text{drift}_{\text{Dec}}$ is from §3.3, in pixels per minute
- pixel_scale converts to arcsec
- $\delta$ is the declination of the target the section was guiding on, in radians
- The constant 3.8197 is a unit-conversion factor derived from the sidereal rate (15.041 arcsec/sec); equivalent forms use coefficients of 0.262 (for arcsec/min input) or 15.71 (for arcsec/hour input)

The cosine correction accounts for foreshortening: at high declinations, a given drift in arcsec corresponds to a smaller polar alignment error than the same drift at the equator.

**How to interpret the number**:

- < 1 arcmin: excellent polar alignment, no improvement worthwhile
- 1-3 arcmin: typical for good polar alignment; field rotation is minimal even on long subs
- 3-5 arcmin: noticeable; you'll see field rotation on long subs; worth re-aligning
- \> 5 arcmin: significant; consider re-doing your polar alignment from scratch

The analyzer requires at least 10 minutes of guiding data, a known declination in the section header, and a computable Dec drift before reporting a PA error. When any precondition fails, the value shows "—" instead of a guess.

### 3.6 Scatter ellipse — the shape of your guiding

The scatter plot shows every included sample as a point at coordinates $(\text{RARawDistance}, \text{DECRawDistance})$. A perfectly-tracking mount would put every point at the origin; a real mount produces a cloud.

The shape of that cloud tells you something. The analyzer fits a 2D dispersion ellipse to the cloud — characterizing it by:

- **Centroid** $(\bar{x}, \bar{y})$ — should be near (0, 0). A visible offset indicates calibration drift since the lock position was set.
- **Rotation angle** $\theta$ — how the ellipse is tilted relative to the RA/Dec axes
- **Semi-major and semi-minor axes** ($\sigma_{\text{maj}}, \sigma_{\text{min}}$) — how stretched or round the ellipse is

The rotation angle uses the same form as PHDLogViewer:

$$\theta = \text{atan2}(\text{cov}_{xy}, \text{var}_x)$$

(This is similar to but not identical to the textbook PCA rotation $\frac{1}{2}\text{atan2}(2\text{cov}_{xy}, \text{var}_x - \text{var}_y)$. The two agree when the ellipse is highly elongated and diverge slightly when it's nearly circular. We use the simpler form for cross-tool consistency.)

After computing $\theta$, the rotated coordinate variances give the major and minor axis sigmas:

$$\sigma_{\text{maj}} = \sqrt{\text{var}(x_{\text{rot}})}, \quad \sigma_{\text{min}} = \sqrt{\text{var}(y_{\text{rot}})}$$

Where the rotated coordinates are computed by applying the rotation $\theta$ to each centered sample point.

The 1σ dispersion ellipse on the chart shows the region containing roughly 68% of your samples. The 2σ ellipse contains roughly 95%.

**Elongation** is the ratio:

$$\text{elongation} = \frac{a - b}{a + b}, \quad a = \max(\sigma_{\text{maj}}, \sigma_{\text{min}}), \quad b = \min(\sigma_{\text{maj}}, \sigma_{\text{min}})$$

Range: 0 (perfect circle) to 1 (degenerate line).

**How to interpret the shape**:

- **Round, centered** — well-balanced guiding. RA and Dec both well-controlled.
- **Elongated along RA axis** — RA is noisier than Dec. Common cause: mount periodic error not fully suppressed, or chasing seeing on RA.
- **Elongated along Dec axis** — Dec is noisier. Common cause: backlash, polar alignment drift, or unidirectional Dec guiding catching up.
- **Tilted (angle far from 0° or 90°)** — calibration may be stale; the RA/Dec axes the algorithm thinks it's correcting on don't match the actual sky axes anymore.
- **Centroid offset from origin** — same; usually a calibration drift since the lock position was set.


---

## 4. Frequency analysis — what the spectrum shows

The Spectrum tab is one of the most powerful tools in the analyzer. It transforms your guide log from the time domain (position vs time) to the frequency domain (which oscillation periods are present and how strong they are).

The reason this matters: most mount imperfections produce **periodic errors** at characteristic frequencies. Your worm gear repeats once per full rotation; your strain wave gear has its own characteristic period; gearbox stages have their own; belt drives have theirs. A periodic error at 479 seconds is your EQ6-R Pro worm; a periodic error at 288 seconds is likely your AM5's strain wave gear. The spectrum lets you see these as distinct peaks and identify them.

### 4.1 What the spectrum shows

The X axis is **period in seconds** (logarithmic). The Y axis is **amplitude in arcseconds** (also logarithmic). A peak at period $p$ with amplitude $A$ means: there's an oscillation with that period in your guiding data, and the size of the oscillation is roughly $\pm A$ arcsec from its center.

Atmospheric seeing is broadband (no preferred period) and dominates the very-short-period end of the spectrum (< 5 seconds typically). The analyzer shades that region with an "atmospheric seeing" label so you don't mistake it for mount mechanics.

Mount mechanics produce **discrete peaks** at specific periods. Worm gear errors typically appear at periods between 200 and 800 seconds; gearbox harmonics at fractions of those; strain wave errors at periods between 200 and 500 seconds.

### 4.2 The pre-FFT pipeline

Before the FFT runs, the input series goes through several preprocessing steps. Each step matters for getting clean, accurate spectrum output:

**Step 1: filter to included frames.** Same `Include()` filter from §2. The spectrum recomputes when you change the selection.

**Step 2: minimum entries check.** At least 12 included frames are required. Fewer than that and the FFT output isn't statistically meaningful.

**Step 3: cadence check.** PHD2 frame intervals vary slightly (typically by tens of milliseconds depending on exposure, download time, and processing). If the cadence varies too much within a section — for example, due to long DROP-frame gaps — the FFT input becomes meaningless even after interpolation. The analyzer skips the FFT and warns when cadence variation exceeds 20%.

**Step 4: drift subtraction.** The mean and any linear trend are removed from the input series before the FFT. Without this, a slow drift (which is not periodic) would dominate the very-low-frequency end of the spectrum and obscure mount mechanics.

The drift line is fitted via ordinary least squares:

$$\tilde{x}_i = x_i - (a + b \cdot t_i)$$

where $a$ and $b$ are the regression intercept and slope of $x_i$ vs $t_i$. The slope $b$ is preserved separately as the section's drift metric (§3.3).

**Step 5: interpolate to uniform cadence.** The FFT requires evenly-spaced samples. PHD2 frames aren't quite evenly spaced, so the input is resampled to the mean inter-frame spacing using **Akima spline** interpolation. Akima is non-overshooting — it doesn't introduce spurious oscillations between sample points, which would matter a great deal for periodic-error analysis. (A naive cubic spline could amplify high-frequency content that doesn't exist.)

**Step 6: Hamming window.** The signal is multiplied by a Hamming window before the FFT. Without a window, frequency leakage spreads each peak's energy across many neighboring bins, blurring the spectrum. The Hamming window concentrates the peak's energy back into a tight cluster.

The Hamming window has the form:

$$w_i = 0.54 - 0.46 \cdot \cos\left(\frac{2\pi i}{N - 1}\right), \quad i = 0, 1, \ldots, N-1$$

The analyzer uses Hamming specifically (not Hann or another window) for cross-tool consistency with PHDLogViewer.

**Step 7: FFT.** The windowed series is run through a Fast Fourier Transform. Output: a complex value per frequency bin.

### 4.3 From FFT bins to period and amplitude

Each FFT bin corresponds to a specific frequency:

$$f_k = \frac{k}{N \cdot \Delta t}$$

where $k$ is the bin index, $N$ is the number of samples, and $\Delta t$ is the uniform sample spacing. The corresponding period is just the reciprocal:

$$p_k = \frac{N \cdot \Delta t}{k}$$

The DC bin ($k = 0$) is removed by drift subtraction; the symmetric upper half of the spectrum is redundant. The analyzer keeps bins 1 through $N/2 - 1$.

### 4.4 Amplitude normalization — why it's "4/N"

The raw FFT magnitude $|X_k|$ depends on how many samples you have, which window you used, and which FFT convention. To get a meaningful amplitude in pixel-space, the value is normalized:

$$A_k = \frac{4 \cdot |X_k|}{N}$$

…and then converted to arcsec by multiplying by the section's pixel scale.

The factor of 4 is a combination of:

- A factor of 2 for the **single-sided spectrum** (we drop the negative frequencies because they're redundant for real input)
- A factor of approximately 1.85 for the **Hamming window's coherent gain** — the window's mean value is about 0.54, so amplitudes are reduced by that factor and need to be inflated back

The product is approximately 3.7, which PHDLogViewer rounds to 4. The analyzer matches this rounding for cross-tool consistency. The result is a slight (~8%) overestimate of true peak amplitude, but the bias is consistent across all sessions and matches PHDLogViewer's reported values exactly.

### 4.5 Peak detection — the MAD-based threshold

Not every wiggle in the spectrum is a real peak. The analyzer needs a threshold to distinguish significant peaks from noise.

The threshold uses **Median Absolute Deviation (MAD)** — a robust statistic that's resistant to outliers:

$$\text{MAD}(A) = \text{median}(|A_i - \text{median}(A)|)$$

For normally-distributed data, MAD relates to the standard deviation σ via:

$$\sigma \approx 1.4826 \cdot \text{MAD}$$

(The 1.4826 factor comes from the inverse standard normal CDF at 3/4.)

The peak detection threshold is then:

$$\text{threshold} = \text{median}(A) + 3 \cdot 1.4826 \cdot \text{MAD}(A)$$

A bin is considered a peak if its amplitude exceeds the threshold AND it's a local maximum (greater than both neighbors). This 3-sigma threshold is conservative — it produces zero false peaks on a flat noise spectrum and only flags features that are genuinely above the noise floor.

After detection, peaks within ±5% of each other in period are deduplicated (keeping the higher-amplitude one), and the top 5 peaks across all visible traces are marked on the chart with dot markers.

### 4.6 The hover tooltip — what each readout means

When you hover near a peak, the cursor snaps to the nearest local maximum within 8 pixels and shows four readouts:

- **Period** — the period at the peak, in seconds
- **Amplitude** — the spectrum value at the peak, in arcsec
- **Peak-to-peak** — the full swing of a sine wave with that amplitude: $2A$
- **RMS** — the RMS value of a sine wave with that amplitude: $A / \sqrt{2} \approx 0.7071 \cdot A$

The relationships among these come from the math of pure sine waves. For $x(t) = A \sin(\omega t)$:

- Amplitude is $A$ (the peak value from zero)
- Peak-to-peak is $2A$ (the full distance from minimum to maximum)
- RMS is $\frac{A}{\sqrt{2}}$, which derives from the time integral of $A^2 \sin^2$:

$$\text{RMS} = \sqrt{\frac{1}{T}\int_0^T A^2 \sin^2(\omega t) \, dt} = \sqrt{\frac{A^2}{T} \cdot \frac{T}{2}} = \frac{A}{\sqrt{2}}$$

Why all four? Different conventions are used in different communities:

- Mount manufacturers often spec **peak-to-peak** PE (e.g. "±30 arcsec PE" means 60 arcsec p2p)
- PE measurement tools like PEMPro often report **RMS PE**
- The analyzer's spectrum natively reports **amplitude** (the peak value)

Having all four lets you cross-reference values from any community source.

### 4.7 What's a meaningful section duration?

The spectrum can compute as soon as you have 12 frames, but its usefulness depends on duration:

- **5+ minutes**: usable for sub-worm-period analysis (catches gearbox harmonics, motor stages)
- **10-20 minutes**: starts to show worm-period peaks reliably
- **2× the worm period or more**: required for confident worm-period detection
- **Several worm cycles**: needed for confident periodic-error measurement

Shorter sections still get a spectrum, but the analyzer annotates them with "section too short for confident periodic-error detection" so you don't over-interpret the result.

### 4.8 Per-trace toggles

By default, the spectrum shows the **RA raw distance** trace (blue). The Dec trace is hidden but toggleable from the legend — Dec periodic signals are usually small but can indicate balance or worm issues.

When unguided RA reconstruction is available (§5), an "Unguided RA" trace becomes available too — usually the most useful trace for mount tuning because it shows what the mount is doing without your guiding corrections.

---

## 5. Unguided RA reconstruction

This is the most powerful single feature for mount tuning. It computationally undoes your guide corrections to show what the mount would have done **without** any guiding — revealing the raw periodic error.

You can already see the unguided behavior of your mount by running PHD2's Guiding Assistant (which temporarily disables guide output) — but those sessions are typically short (a few minutes). Unguided reconstruction gives you the same data from any guided session, no matter how long it ran or what target you were on.

### 5.1 The recurrence algorithm

The reconstruction is conceptually simple. At any frame, the change in star position equals the mount's natural drift plus your guide correction:

$$\Delta \text{position} = \Delta \text{drift} + \text{guide correction}$$

So if you know the position change and you know the correction, you can recover the drift contribution:

$$\Delta \text{drift}_i = (x_i - x_{i-1}) - \text{RAGuideDistance}_{i-1}$$

Accumulating these drift contributions gives a position trace that represents what the star would have done if no corrections had been applied:

$$\text{rapos}_i = \sum_{j=1}^{i} \Delta \text{drift}_j$$

The full recurrence:

```
rapos = 0
prev_raraw = 0
prev_raguide = 0

for each included frame i:
    raraw = RARawDistance[i]
    raguide = RAGuideDistance[i]
    move = raraw - prev_raraw - prev_raguide
    rapos += move
    output[i] = rapos
    prev_raraw = raraw
    prev_raguide = raguide
```

This is the same algorithm PHDLogViewer uses for "Analyze selected, raw RA". It's elegant because `RAGuideDistance` is already the signed pixel-space output of the algorithm — it accounts naturally for:

- **Min-move frames** where no pulse was issued (`RAGuideDistance = 0` → no contribution)
- **Clipped pulses** where the algorithm wanted more correction than `Max RA Duration` allowed (the next frame's measurement reflects what the mount actually did)
- **DROP frames** (skipped by the include filter; the next valid frame's `move` correctly spans the gap)

You don't need to handle pulse durations, parities, calibration angles, or any of the other complications — the signed `RAGuideDistance` already encodes them.

### 5.2 What you see in the time-domain overlay

When you toggle "Unguided RA" on the time-series chart, the reconstructed trace overlays your raw RA trace. What jumps out:

- **A clear sine-like wave at your worm or strain wave period** — that's your mount's periodic error, naked.
- **A long-term linear trend** — that's polar alignment drift that's leaking through (the corrections subtract guide pulses, but slow trends accumulate).
- **Spikes** — usually moments where a guide pulse failed to do what the algorithm expected (mount slip, momentary backlash, command latency).

The unguided trace is **not drift-subtracted** in the time-domain view (you want to see the cumulative drift). It IS drift-subtracted before the FFT (so polar alignment doesn't dominate the spectrum's low-frequency end).

### 5.3 What you see in the spectrum

The Unguided RA trace in the spectrum is where periodic error becomes visible. Compare it to the raw RA spectrum:

- **Raw RA spectrum** typically shows mount peaks suppressed (because guiding is suppressing them), often muddled with short-period seeing artifacts.
- **Unguided RA spectrum** shows the mount peaks at their full natural amplitude, undimmed by the guide algorithm's response.

A well-tuned mount with effective guiding will show large peaks in the unguided spectrum and small peaks in the raw spectrum at the same period. A poorly-tuned guide will show similar peaks in both. The ratio is exactly what the §9.2 `guiding_pe_suppression_low` diagnostic measures.

### 5.4 Why this isn't a perfect substitute for unguided sessions

The reconstruction has limits:

- It assumes `RAGuideDistance` accurately represents the actual mount response. If your mount has slop, lag, or non-linearity, the reconstruction misses that — those effects appear as residual noise or as apparent drift in the unguided trace.
- It can't recover drift that's slower than the section duration. A truly long-period error (longer than the section) shows up as a linear trend and is removed by drift subtraction before the spectrum.
- It assumes guide pulses had the effect they were supposed to have. Failed pulses (mount didn't move when commanded) show up as spurious "drift" in the reconstruction.

For the cleanest possible PE measurement, run PHD2's Guiding Assistant for a few full worm cycles. The reconstruction is excellent for "I have lots of guided data, what does my PE look like?" — which is most of the time.

---

## 6. Periodic error measurement

The analyzer takes the unguided RA spectrum and turns it into a structured measurement: a single number for the dominant PE period, its amplitude, peak-to-peak, RMS, and a confidence indicator. This gets persisted per session and per mount instance, so you can track your specific mount's PE over time.

This is the analyzer's most distinctive capability — no other PHD2 log analysis tool does this.

### 6.1 What gets measured

For every guiding section that has a usable unguided spectrum (a Guiding Assistant section, or a guided section with the Unguided RA mode active, or any section where the mount's drive type indicates periodic error is expected), the analyzer computes:

| Field | Meaning |
|---|---|
| `pe_period_s` | Period of the dominant peak in the unguided spectrum, seconds |
| `pe_amplitude_arcsec` | Amplitude of that peak (peak from zero), arcsec |
| `pe_peak_to_peak_arcsec` | $2 \times$ amplitude, arcsec — matches manufacturer specs |
| `pe_rms_arcsec` | $A/\sqrt{2}$, arcsec — matches PEMPro-style RMS PE |
| `pe_dominant_peak_confidence` | High / medium / low (see §6.2) |
| `pe_section_duration_min` | How long the source section was, minutes |
| `pe_section_duration_vs_period_ratio` | Section length divided by detected period; should be ≥ 2 for confident measurement |
| `pe_secondary_peaks` | Up to 4 additional significant peaks, with their period and amplitude |
| `pe_shape_category` | Sinusoidal / asymmetric / multi-harmonic (see §6.3) |
| `pe_measurement_at_declination` | Declination at the start of the section, degrees |
| `pe_measurement_pier_side` | East / West / Unknown |
| `pe_measurement_payload_kg` | Rig payload weight, when known |

### 6.2 Confidence levels

Confidence is based on how strongly the dominant peak rises above the noise floor (in MAD-threshold units, per §4.5):

- **High** confidence: dominant peak amplitude > 5× the MAD threshold
- **Medium** confidence: 3-5× the threshold
- **Low** confidence: just above the threshold

Low-confidence measurements are still reported but flagged in the UI; users can choose whether to include them in trend analysis.

### 6.3 Shape category

Real-world periodic error isn't always a clean sine wave. The shape category tells you what kind of PE you're looking at:

- **Sinusoidal**: dominant peak is much larger than all secondary peaks (3:1 ratio or more). This is what an idealized worm gear produces.
- **Asymmetric**: a secondary peak is at least 50% of the dominant peak's amplitude. Often indicates a bent worm, gear runout, or off-center engagement.
- **Multi-harmonic**: three or more peaks above the threshold. Common with strain wave mounts (where the gear has many small irregularities) or worm mounts with significant gearbox contributions.

### 6.4 What "the dominant period" means for different mount types

For traditional **worm gear mounts**, the dominant period is exactly the worm rotation period (typically 200-800 seconds). It's stable across sessions because the gear geometry doesn't change.

For **strain wave / harmonic mounts**, the dominant period exists but is less stable. ZWO documents this for the AM5: *"the periodic errors of a strain wave gear mount are different from that of a worm gear mount... the error of each gear is different from another."* Rainbow Astro states the same for the RST-135: *"Strain wave gear has a large periodic error compared to worm gear... it has a periodic error about ±30 arcsec in a 430-second cycle."*

The implication: per-mount-instance measurement matters more for strain wave than for worm. Two AM5s off the same production line can have different PE amplitudes and slightly different dominant periods. The analyzer's per-instance tracking (§10.3) is designed for this.

### 6.5 Manufacturer default vs measured override

The analyzer ships with manufacturer-stated PE periods for known mount models in its catalog (§7.2 / §7.3). Spectrum markers initially use these defaults.

Once you have **3 or more measurements** from your specific mount instance with a stable period (coefficient of variation < 5% across measurements), the analyzer switches to using your measured period as the primary marker. The manufacturer default is still shown as a faint secondary marker so you can see the difference.

This means: as your measurement history grows, the analyzer's diagnostics become tuned to your specific mount, not just the model class.

---

## 7. Equipment-aware spectrum markers

When you've selected a rig in the rig picker, the analyzer knows what mount you're using and can mark expected PE periods on the spectrum. The marker style depends on the mount's drive type.

### 7.1 Drive types

The analyzer recognizes these drive types:

| Drive type | Examples | Spectrum marker behavior |
|---|---|---|
| `worm` | EQ6-R Pro, CEM26, AVX, Losmandy G11 | Vertical line at the worm period |
| `strain_wave` | ZWO AM3/AM5/AM5N, Rainbow RST-135, Pegasus NYX-101 | Vertical line at dominant period + shaded band over expected period range |
| `strain_wave_with_encoder` | Rainbow RST-135E | Same as strain_wave but with reduced amplitude expectation |
| `hybrid_strain_wave_ra` | iOptron HEM27, HEM44 | Strain wave marker on RA, worm marker on Dec |
| `hybrid_strain_wave_ra_with_encoder` | iOptron HEM27EC | Same as hybrid but with RA encoder |
| `direct_drive_encoder` | Astro-Physics 1100GTO with encoders, Planewave L-series | No markers (these mounts shouldn't have discrete spectrum peaks) |
| `friction` | Some lightweight star trackers | No markers |
| `unknown` | Catch-all | Heuristic fallback marker only |

When equipment context is absent (no rig selected, or rig has unknown drive type), the analyzer falls back to a **heuristic marker**: it reports the largest peak in the 300-800 second range with amplitude > 0.5 arcsec, labeled as "likely worm-period peak (uncertain without mount identification)."

### 7.2 Worm gear seed data

The analyzer ships with worm periods for common mounts, sourced from the [PHD2 Mount Worm Period Info wiki](https://github.com/OpenPHDGuiding/phd2/wiki/Mount-Worm-Period-Info):

| Make | Model | Worm period (s) |
|---|---|---|
| Astro-Physics | 1100GTO, 1600GTO | 382.95 |
| Celestron | AVX | 594 |
| Celestron | CGEM, CPC | 478.69 |
| Celestron | CGE Pro | 337.90 |
| Losmandy | G11 | 239.34 |
| Losmandy | G11T, Titan 50 | 318.13 |
| Losmandy | GM8 | 479 |
| Meade | LX200GPS | 478.69 |
| Orion | Sirius EQ-G (= Sky-Watcher HEQ5) | 638 |
| Orion | Atlas Pro | 479 |
| Sky-Watcher | EQ6, EQ6-R Pro (2017) | 479 |
| Software Bisque | Paramount ME / MEII | 149.6 |
| Software Bisque | Paramount MX / MX+ | 230 |
| Software Bisque | Paramount MyT | 269.26 |
| Takahashi | EM-400 | 480 |
| iOptron | CEM25P | 598 |
| iOptron | CEM26, GEM28 | 600 |
| iOptron | CEM40, GEM45 | 400 |
| iOptron | CEM70 | 348 |
| iOptron | CEM120 | 240 |
| iOptron | IEQ45PRO | 336.6 |
| iOptron | SkyGuider Pro | 600 |

This list isn't exhaustive — if your mount isn't here, the heuristic marker still works. You can also enter a custom worm period in the equipment configuration to get a precise marker.

### 7.3 Strain wave seed data

For strain wave mounts, the analyzer ships with a dominant period and an "expected period band" (the range within which strain wave PE is expected to fall, given that strain wave PE varies between individual gears):

| Make | Model | Dominant period (s) | Expected band (s) |
|---|---|---|---|
| ZWO | AM3 | 288 | 180-360 |
| ZWO | AM5 | 288 | 180-360 |
| ZWO | AM5N | 288 | 180-360 |
| Rainbow Astro | RST-135 | 430 | 300-600 |
| Rainbow Astro | RST-135E | 430 | 300-600 |
| iOptron | HEM27 | 360 (RA) / 600 (Dec worm) | 250-480 RA |
| iOptron | HEM27EC | 360 (RA) / 600 (Dec) | 250-480 RA |
| iOptron | HEM44 | unknown — measure | 250-600 RA |
| iOptron | HEM44EC | unknown — measure | 250-600 RA |
| iOptron | HAE29 | unknown — measure | 250-600 |
| iOptron | HAE43 | unknown — measure | 250-600 |
| iOptron | HAE69 | unknown — measure | 250-600 |
| Pegasus Astro | NYX-101 | 430 | 350-500 |
| Sky-Watcher | Wave 100i | unknown — measure | 200-500 |
| Sky-Watcher | Wave 150i | unknown — measure | 200-500 |

Sources: ZWO product documentation, Rainbow Astro and Pegasus Astro FAQs, community measurements on Cloudy Nights and the PHD2 forum. The "unknown — measure" entries reflect mounts where the manufacturer hasn't published a spec and community consensus hasn't formed yet — your specific mount's measured PE is the authoritative answer for those.

The expected band gives a range rather than a single period because strain wave PE varies between individual gears (per ZWO and Rainbow Astro documentation). When a peak in your spectrum falls inside the expected band, the analyzer flags it as consistent with strain wave PE; when it falls outside the band, the analyzer's diagnostics treat it differently (see §9.3).

### 7.4 Hybrid mounts

iOptron's HEM-series mounts are hybrid: strain wave RA + worm Dec (the Dec gear is borrowed from the matching GEM-series mount — HEM27 inherits GEM28's 600s Dec worm). For these, the analyzer renders two markers — strain wave on the RA spectrum, worm on the Dec spectrum — and applies the appropriate rules to each axis independently.


---

## 8. Guiding Assistant sections

PHD2's [Guiding Assistant](https://openphdguiding.org/man/Guiding_Assistant.htm) is an in-app tool that temporarily disables guide output, measures unguided mount behavior for a few minutes, optionally measures Dec backlash, and reports its findings as suggested guide settings.

GA produces a special section in the guide log: every frame has `RADuration = 0` and `DECDuration = 0` (because guide output is off), bracketed by `INFO: Guiding Output Disabled` and `INFO: Guiding Output Enabled` events. The section contains the raw star motion under no guiding — exactly the input you want for periodic error measurement.

### 8.1 Auto-detection

The analyzer detects GA sections by either:

1. Finding `Guiding Output Disabled` and `Guiding Output Enabled` events bracketing the section, **or**
2. Detecting that ≥ 90% of frames in the section have `RADuration = 0 ∧ DECDuration = 0`

Either condition is sufficient — both ways of identifying GA work even if one of them happens to be missing from a particular log.

### 8.2 The dedicated GA panel

When a GA section is detected, the analyzer shows a dedicated panel instead of the standard guiding-section view. The panel includes:

- **Unguided RMS RA / Dec / Total** — the same RMS formula from §3.1 applied to the raw distance series (which IS the unguided trace, because guide output was off).
- **Estimated polar alignment error** — using the §3.5 formula, which is especially accurate for GA sections because the drift is the mount's actual drift (no guide corrections to confound it).
- **Measured Dec backlash** — when the section includes a backlash measurement sub-sequence (PHD2 issues an alternating-direction Dec pulse pattern with no RA corrections, typically ~20 N pulses then ~20 S pulses, and measures the asymmetry). The analyzer reads this directly from PHD2's GA-emitted INFO line if logged; otherwise computes it from the pulse-displacement asymmetry.
- **Drift-corrected RA trace** — the unguided RA reconstruction with linear drift removed (matches PHD2's GA report).
- **Dedicated FFT** on the unguided RA trace, with a wider period range than the standard spectrum view to catch longer-period periodic errors.

The PE measurement (§6) for GA sections is typically the most reliable because the input is genuinely unguided, the section is intentional, and PHD2's own backlash measurement gives an independent cross-check.

---

## 9. Two-tier diagnostics

The most distinctive feature of NightCrate's analyzer — the one that no other PHD2 log analysis tool offers — is the **automated diagnostic engine**. It examines every section and surfaces findings about what looks wrong (or interesting) about your guiding.

Findings are classified into two tiers, visually distinct in the UI:

- **Confident** — the signature in the data has a single canonical explanation. Stated as fact. Not dismissible. Examples: "Polar alignment error approximately 4.2 arcmin." or "Declination backlash detected."
- **Speculative** — the signature has multiple plausible explanations or relies on a noisy measurement. Stated as hypothesis. Dismissible per-analysis. Examples: "RMS is gradually increasing — possible thermal drift, flexure, or changing seeing."

Every finding includes:

- A short summary
- A longer explanation
- The evidence (numeric values that triggered the rule)
- A reference URL pointing to the community source for the interpretation
- An actionable next step where appropriate

This two-tier approach is the analyzer's answer to the "post my log to the forum, wait for an expert" workflow. Confident findings give you the actionable answers a forum expert would; speculative findings raise the questions a forum expert would.

### 9.1 Confident-tier rules

#### Polar alignment error from Dec drift

Computes the §3.5 polar alignment error and fires when it exceeds 2 arcminutes. Requires a guiding section ≥ 10 minutes with known declination and computable Dec drift.

The finding gives you the estimated PA error and an actionable: re-run the Guiding Assistant or PHD2's Drift Alignment tool to confirm and refine.

#### Dec backlash overshoot pattern

Looks for the classic Dec backlash signature in the pulse series:

1. A run of ≥ 5 consecutive Dec pulses in one direction (the algorithm is correcting drift)
2. Followed by ≥ 3 frames of Dec algorithm pause (zero pulses — the algorithm is waiting to see if the star returns on its own)
3. Followed by a Dec pulse in the reversed direction whose magnitude is ≥ 2× the mean of the initial run (the algorithm finally gives up waiting and over-corrects)

This three-stage overshoot-pause-overshoot pattern is the canonical [Bruce Waddington tutorial](https://openphdguiding.org/Analyzing_PHD2_Guide_Logs.pdf) signature for Dec backlash. The rule fires when at least 3 such sequences exist in the section.

Actionable: run the Guiding Assistant backlash measurement and enable PHD2's backlash compensation. The tutorial is explicit that mount-firmware backlash compensation should NOT be used while guiding — PHD2's compensation is a different mechanism.

#### SNR drop preceding star loss

For each star-loss event in the section, the rule compares mean SNR in the 30 seconds before the event against mean SNR in the 30 seconds before that:

$$\text{SNR drop ratio} = 1 - \frac{\overline{\text{SNR}}_{\text{just before}}}{\overline{\text{SNR}}_{\text{earlier}}}$$

Fires when ≥ 50% of lost-star events in the section had a prior SNR drop > 30%.

This pattern indicates progressive loss of guide star quality before the algorithm finally couldn't track it — usually clouds, dew on the optics, or focus drift over the course of the night.

#### Sustained Dec direction pulses

Fires when ≥ 90% of nonzero Dec pulses are in the same direction over a section ≥ 15 minutes.

This is a complement to the Dec-drift PA diagnostic. They should usually fire together, but pulses-in-one-direction can fire even when the algorithm is damping the drift enough that the raw drift signal is muted.

The interpretation is the same: polar misalignment causing the mount to drift consistently in one Dec direction.

#### Star saturation

Fires when ≥ 5% of frames have `ErrorDescription` matching saturation patterns (the exact strings vary by PHD2 version: `"Saturated"`, `"mass changed"`, etc.).

Actionable: reduce guide exposure or gain, or select a dimmer star.

#### Calibration axes not orthogonal

Applies only to calibration sections. Computes the angle between the calibrated RA and Dec axes (from `xAngle` and `yAngle` in the calibration record). Fires when:

$$\left| \left| x_{\text{angle}} - y_{\text{angle}} \right| - 90° \right| > 5°$$

A perfect calibration produces axes 90° apart. Significant deviation indicates mount alignment issues, cable flexure during calibration, or pier-side calibration done at a high declination where geometric foreshortening matters.

#### Chasing seeing on RA

Fires when all three conditions hold:

- RA oscillation > 0.55 (per §3.4)
- Median RA pulse duration < 200 ms
- Section guide exposure < 2000 ms

This is the canonical "chasing seeing" signature: the algorithm is trying to correct atmospheric jitter rather than mount mechanics. The fix is to lengthen the exposure (which time-averages out the seeing) and increase RA min-move (which makes the algorithm ignore small movements).

#### Guiding PE suppression low

This is the diagnostic that most directly answers "is my guiding actually working?" It compares the raw RA spectrum against the unguided RA spectrum at the dominant PE period:

$$\text{suppression} = 1 - \frac{a_{\text{raw}}(p_{\text{PE}})}{a_{\text{unguided}}(p_{\text{PE}})}$$

Range: 0 (guiding suppresses nothing) to 1 (guiding suppresses everything completely).

Expected values:

- Well-tuned worm mount: 0.85-0.95 (guiding removes most of the PE)
- Strain wave mount: 0.5-0.8 (PE is less repeatable, harder to predict and suppress)

The rule fires when:

- `pe_amplitude_arcsec ≥ 1.5` (the mount has measurable PE in the first place), AND
- `suppression < 0.5` (guiding is removing less than half of it)

Actionable: possible causes include RA aggressiveness too low, guide cadence too long for the PE period, or algorithm mismatch (try Predictive PEC if it's available for your mount).

This rule depends on having unguided RA reconstruction available (§5) and a structured measured PE (§6) for the section.

### 9.2 Speculative-tier rules

#### Gradual RMS trend

Linear regression of per-minute RMS over sections ≥ 30 minutes. Fires when the slope > 0.005 arcsec/min (worsening over time).

Possible causes: thermal drift (your equipment cooling unevenly through the night), mechanical flexure (cables shifting, dew straps shifting), or changing seeing (a weather front coming through).

#### Out-of-band spectrum peaks

Drive-type-aware. Looks for spectrum peaks at periods that don't match the expected mount mechanics:

- **Worm mounts**: peaks > 0.5 arcsec amplitude at periods that aren't within ±5% of the worm period or its first three harmonics (worm/2, worm/3, worm/4), and outside the seeing band (< 5 s). Out-of-band peaks suggest gearbox stages, belt drives, or motor harmonics.

- **Strain wave mounts**: peaks > 1.0 arcsec amplitude (higher threshold because strain wave PE is intrinsically richer in broadband content) outside 0.5×-2.0× the dominant period or outside the expected band. The language is softer than for worm mounts: "this may be a load-dependent strain wave variation rather than a fault" — because strain wave PE varies with load is documented manufacturer behavior, not a defect.

- **Hybrid mounts**: applies the strain wave rule to RA and the worm rule to Dec.

- **Direct-drive encoder mounts**: any peak > 1.0 arcsec is anomalous (these mounts shouldn't have discrete spectrum peaks). For encoder mounts, this rule fires at the **confident tier** (overriding its default speculative tier) — because the signature genuinely doesn't have multiple plausible explanations for an encoder mount.

#### Strain wave load balancing recommendation

Fires when:

- Mount is strain wave (any variant)
- Measured PE amplitude > 1.5× the manufacturer's stated typical amplitude
- Rig context is populated and load is within mount spec

Strain wave PE is load- and direction-dependent ([Pegasus Astro NYX guidance](https://pegasusastro.com/nyx-101-guiding-recommendations/), [Rainbow Astro RST-135 FAQ](https://www.rainbowastro.com/faq-items/how-big-periodic-errors-of-rst-135-is/)). PE significantly above the typical value suggests the load distribution is something to investigate.

#### SNR variability

Fires when SNR standard deviation exceeds 30% of mean SNR AND the SNR series shows non-random structure (lag-1 autocorrelation > 0.4).

The lag-1 autocorrelation requirement distinguishes systematic variability (clouds passing, slow brightness changes) from random jitter (which would have low autocorrelation).

Possible causes: thin clouds, dew formation, focus drift.

#### Possible differential flexure

Requires guide-scope (not OAG) configuration. Looks for sustained drift in both RA and Dec whose direction varies with pointing across the session.

In a guide-scope setup, the guide camera and main imaging camera are mounted on physically separate optical paths. As the mount moves to different parts of the sky, gravity bends each path slightly differently — and if the guide scope and main scope flex differently, the guide star drifts relative to the main camera even though the mount is tracking perfectly.

This is hard to confirm from a single session; the rule becomes much stronger in multi-log analysis (§10) where the same drift pattern appearing across different targets is conclusive.

#### Dec oscillation with backlash compensation

Fires when Dec oscillation > 0.4 AND `Backlash comp = enabled` in the section header.

PHD2's backlash compensation can over-correct if it's tuned too aggressively, producing oscillations on direction reversals. The actionable is to reduce the backlash compensation pulse value.

#### Low SNR throughout

Fires when mean SNR < 10 across the section without triggering actual star loss events.

Low SNR by itself doesn't make guiding fail, but it does make every guide measurement noisier and the resulting corrections less precise. Selecting a brighter star or increasing exposure usually helps.

#### High RMS vs rig expected

Requires rig context. Fires when:

$$\text{RMS}_{\text{Total, arcsec}} > 3 \times \text{rig expected guide precision}$$

The rig's expected guide precision is computed by NightCrate's [rig-suitability calculator](https://en.wikipedia.org/wiki/Astrophotography) from the guide camera, guide scope focal length, sampling rate, and other rig-specific factors. When measured RMS substantially exceeds expectations, something is wrong beyond the mount's normal performance — could be rig-level (e.g., an actually-bad guide setup) or environment-level (poor seeing, wind).

### 9.3 Equipment-aware threshold scaling

When a rig is selected, several diagnostic thresholds scale with the rig's specific characteristics:

- The polar alignment threshold scales with the rig's effective guide precision (a rig that can't resolve sub-arcsec PA error gets a more lenient threshold)
- The chasing seeing oscillation threshold loosens for over-sampled rigs (where small RA pulses are expected even on quiet nights)
- The out-of-band amplitude floor adjusts to the rig's expected guide precision
- Strain-wave-specific rules become available (the load balancing recommendation rule, the softer language for out-of-band peaks)

When no rig is selected, all rules still function with absolute thresholds and uncertainty-aware language. The diagnostics are useful at any equipment-knowledge level; they get more precise the more you tell the analyzer about your gear.

---

## 10. Multi-log analysis

So far this document has talked about analyzing one log at a time. The analyzer also supports analyzing many logs together to surface trends and patterns over time.

### 10.1 Multi-log comparison

Select 2-20 logs from the recently-analyzed list. The comparison view shows:

- **Side-by-side stats table** — one row per section across all selected logs, sortable by date, RMS, drift, oscillation, or top diagnostic.
- **Trend chart** — RMS Total (and optionally each subcomponent) plotted against session date, with a trend line. The X axis can be switched between calendar date, session index, and integration time accumulated.
- **Diagnostic-cooccurrence matrix** — which diagnostic findings fire across which sessions. Reveals persistent issues vs one-off problems.
- **Configuration drift panel** — highlights when algorithm parameters, guide rates, or calibration values change between sessions. Useful for "did my guiding get worse after I changed that parameter last week?"

### 10.2 Trend analysis

Simple summaries over a selected time window:

- "Average RMS Total over the last N nights is X, trending {up / down / flat}"
- "Dec backlash detected in M of last N nights"
- "Polar alignment drift stable around N arcmin"

Sophisticated trend analytics (e.g., "you stopped improving around date X") are part of the AI analyzer in a later release.

### 10.3 Per-mount-instance PE history

This is the payoff of the per-session PE measurement (§6). Every measurement is attached not just to a mount **model** but to a specific mount **instance** — your physical mount, distinguished by a nickname you give it ("My AM5", "AM5 #2 in the second observatory").

The Mount Instance detail page shows:

- **PE history scatter** — period and amplitude over time, with rolling median and 1σ band
- **Drift-over-time alert** — fires if the trailing 30-day median has shifted by > 5% from the prior 30-day median. Could indicate gear wear, lubrication needing attention, or PHD2 settings change.
- **"Compared to manufacturer default"** — how your measured period and amplitude relate to the catalog default. For strain wave mounts especially, your measured values are the authoritative answer for your specific gear.
- **Filter dimensions** — per-instance history can be filtered by declination, payload weight, and pier side. Strain wave PE depends on these (per manufacturer documentation), so the corpus becomes more informative as these dimensions get populated.

For users who own multiple instances of the same mount model (e.g., two AM5s), each instance has its own history. The analyzer doesn't conflate them — measurements from instance A don't influence the spectrum markers shown when instance B is selected.

---

## 11. References and further reading

### Authoritative PHD2 references

- [PHD2 Guide Log format wiki](https://github.com/OpenPHDGuiding/phd2/wiki/PHD2GuideLog) — what's in a guide log, column-by-column
- [PHD2 Trouble-shooting and Analysis manual](https://openphdguiding.org/man/Trouble_shooting.htm) — semantic explanations of guide log fields
- [PHD2 User Guide](https://openphdguiding.org/PHD2_User_Guide.pdf) — feature documentation, Guiding Assistant included
- [PHD2 Mount Worm Period Info wiki](https://github.com/OpenPHDGuiding/phd2/wiki/Mount-Worm-Period-Info) — community-curated worm periods for known mounts

### Reference tools

- [PHDLogViewer](https://adgsoftware.com/phd2utils/) (Andy Galasso) — the de facto standard log analysis tool; NightCrate's analyzer is formula-compatible with it
- [PEMPro Log Viewer](http://www.siriusimaging.com/PEMProV3/) (Ray Gralak / Sirius Imaging) — freeware, secondary reference

### Interpretation guides

- [Bruce Waddington, *Analyzing PHD2 Guiding Results*](https://openphdguiding.org/Analyzing_PHD2_Guide_Logs.pdf) — the canonical 30-page community tutorial; source for many of the diagnostic rules
- [PHD2 Glossary of Terms](https://openphdguiding.org/man-dev/Glossary.html) — definitions of RMS, backlash, periodic error, image scale

### Polar alignment math

- [Frank Barrett, *Determining Polar Axis Alignment Accuracy*](http://celestialwonders.com/articles/polaralignment/PolarAlignmentAccuracy.html) — the source of the 3.8197 coefficient
- [Frank Barrett, *Measuring Polar Axis Alignment Error*](http://celestialwonders.com/articles/polaralignment/MeasuringAlignmentError.html) — full derivation in Appendix A

### Strain wave mount documentation

- [ZWO AM5 PE Test Report explanation](https://astronomy-imaging-camera.com/tutorials/10-things-you-need-to-know-about-the-custom-am5s-pe-test-report-provided-by-zwo/) — manufacturer documentation that strain wave PE is "actually not that PERIODIC" and varies between gears
- [Rainbow Astro RST-135 PE FAQ](https://www.rainbowastro.com/faq-items/how-big-periodic-errors-of-rst-135-is/) — manufacturer-stated 430-second cycle, ±30 arcsec, load-dependent
- [Pegasus Astro NYX-101 guiding recommendations](https://pegasusastro.com/nyx-101-guiding-recommendations/) — 430-second cycle, ±20 arcsec or less

---

## Appendix: Quick-reference formula card

For users who want all the math on one page.

### Metrics

$$\text{RMS}_{\text{RA}} = \sqrt{\frac{1}{N}\sum_{i=1}^{N}(x_i - \bar{x})^2}, \quad \text{RMS}_{\text{Total}} = \sqrt{\text{RMS}_{\text{RA}}^2 + \text{RMS}_{\text{Dec}}^2}$$

$$\text{Peak}_{\text{RA}} = x_j \text{ where } |x_j| = \max_i |x_i|$$

$$\text{drift}_{\text{RA}} = \frac{(x_{\text{last}} - x_{\text{first}}) - \sum_i \text{RAGuideDistance}_i}{t_{\text{last}} - t_{\text{first}}} \quad \text{(pixels/sec)}$$

$$\text{drift}_{\text{Dec}} = \frac{\text{cov}(t, y_{\text{accum}})}{\text{var}(t)}$$ where $y_{\text{accum}}$ accumulates Dec changes across previously-unguided frames only.

$$\text{ra\_oscillation} = \frac{|\{i : \text{sign}(x_i) \neq \text{sign}(x_{i-1})\}|}{N - 1}$$

$$\alpha_{\text{arcmin, PA error}} = 3.8197 \cdot \frac{|\text{drift}_{\text{Dec}}|_{\text{px/min}} \cdot \text{pixel\_scale}}{\cos(\delta)}$$

### Scatter ellipse

$$\theta = \text{atan2}(\text{cov}_{xy}, \text{var}_x), \quad \text{elongation} = \frac{a - b}{a + b}$$

### Frequency analysis

$$w_i = 0.54 - 0.46 \cdot \cos\left(\frac{2\pi i}{N - 1}\right) \quad \text{(Hamming window)}$$

$$f_k = \frac{k}{N \cdot \Delta t}, \quad p_k = \frac{N \cdot \Delta t}{k}$$

$$A_k = \frac{4 \cdot |X_k|}{N} \cdot \text{pixel\_scale} \quad \text{(arcsec amplitude)}$$

$$\text{peak threshold} = \text{median}(A) + 3 \cdot 1.4826 \cdot \text{MAD}(A)$$

### Sine wave relationships

$$\text{Peak-to-peak} = 2A, \quad \text{RMS} = \frac{A}{\sqrt{2}}$$

### Unguided RA reconstruction

$$\text{rapos}_i = \sum_{j=1}^{i} (x_j - x_{j-1} - \text{RAGuideDistance}_{j-1})$$

### Guiding PE suppression

$$\text{suppression} = 1 - \frac{a_{\text{raw}}(p_{\text{PE}})}{a_{\text{unguided}}(p_{\text{PE}})}$$

---

*This document is part of the NightCrate user documentation. For implementation details, see the [PHD2 Analyzer Spec v4](nightcrate-phd2-analyzer-spec-v4.md). For bug reports or feature requests, open an issue on the NightCrate GitHub repo.*
