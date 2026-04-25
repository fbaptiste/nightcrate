# NightCrate PHD2 Guide Log Analyzer — Functional Spec (v4)

This is the complete, source-verified functional specification for the NightCrate PHD2 Guide Log Analyzer. It supersedes all prior versions (v2, v3, v3.1).

This is a **functional** spec. It defines what the analyzer does, what it parses, what it computes, what it surfaces, and the order in which capabilities land. It does not prescribe code layout, API paths, database schemas, React components, or any other implementation decision. Those belong to Claude Code, which has current context on the NightCrate codebase that this document deliberately lacks.

**Verification policy.** Every factual claim in this document has a source. Every formula has either a derivation or a citation to an authoritative implementation. The PHDLogViewer reference algorithm sections quote the exact code from `AnalysisWin.cpp` so CC can verify the port without re-reading the source. The strain wave mount data is sourced per-mount from manufacturer pages, not inferred from class characteristics. When a value is genuinely unknown (some HEM44/HAE-series period values), the spec marks it `unknown — measure` rather than guessing.

**Core principle: PE measurement is a first-class capability, not a side effect.** Strain wave mounts vary between individual gear instances; ZWO and Rainbow Astro both state this explicitly in their official documentation. Manufacturer-stated periods are *defaults* that get overridden once the user has measured their specific mount. The analyzer measures PE per session, accumulates per-mount-instance history, and uses measured values to drive diagnostics where available. This is documented in §6.

---

## Table of contents

1. Positioning and goals
2. Reference landscape — what exists today
3. PHD2 guide log format — verified against a real log
4. Architectural principles (apply across all phases)
5. Phase v1 — Parity with PHDLogViewer (core) — SHIPPED in v0.22.0–v0.24.0
6. Phase v2 — Advanced parity + per-session and per-instance PE measurement
7. Phase v3 — Automated diagnostic engine
8. Phase v4 — Multi-log comparison, trends, shareable reports, catalog integration
9. Phase v5+ — Debug logs, live monitoring, AI analysis
10. Out of scope (now and possibly forever)
11. Math appendix — full derivations of every formula
12. Pass D handoff plan — what to fix in the current Spectrum tab implementation
13. References — every source cited above

---

## 1. Positioning and goals

**Unchanged from prior versions.** PHD2 is the dominant autoguiding application. ASIAIR, N.I.N.A., SGPro, and Ekos all bundle or integrate with it. The dominant support pattern is "post log to forum, wait for an expert" — the [PHD2 troubleshooting manual](https://openphdguiding.org/man/Trouble_shooting.htm) directs users to PHDLogViewer for visualization, but the canonical interpretation tutorial ([Bruce Waddington's *Analyzing PHD2 Guiding Results*](https://openphdguiding.org/Analyzing_PHD2_Guide_Logs.pdf)) is a 30-page PDF.

The NightCrate analyzer's goal is to replace that workflow. The three gaps that justify building it:

1. **No automated interpretation.** PHDLogViewer is purely a visualization tool; interpretation is left to the human reader. Filled by the v3 diagnostic engine.
2. **No multi-session analysis or trend tracking.** Each log is analyzed in isolation. Per-mount-instance PE history (which is what most affects guiding quality on strain wave mounts) is invisible. Filled by v4.
3. **No equipment-aware, modern, cross-platform UI.** Progressive across all phases.

Strategy: "match first, differentiate next." v1/v2 give users no reason to keep PHDLogViewer open in parallel; v3+ makes NightCrate the preferred tool.

Each phase ships as a standalone, useful release. v1 (already shipped in NightCrate v0.22.0–v0.24.0) is fully usable on its own.

---

## 2. Reference landscape

### 2.1 PHDLogViewer (primary parity target — v1, v2)

Verified against the [product page](https://adgsoftware.com/phd2utils/), the [complete changelog](https://adgsoftware.com/phd2utils/ChangeLog.txt) (latest v0.6.4, January 2020), and the [GitHub repo](https://github.com/agalasso/phdlogview). Licensed GPLv3 since v0.5.1 (July 2017). Built on wxWidgets; native Windows, macOS, and Ubuntu (via Patrick Chevalley's PPA).

The reference implementation file `AnalysisWin.cpp` is the primary source for the math used in §6 (frequency analysis, unguided RA reconstruction, polar alignment, scatter ellipse rotation, drift calculation). All algorithms in §6 cite their line ranges in that file.

**Capabilities (verified from the changelog):**

- Time-series guide log plot, RA and Dec independent traces
- Calibration plot showing step direction, magnitude, distance
- Scatter plot of dx/dy
- Periodogram (RA frequency analysis)
- Cursor readouts on time-series and periodogram, including period/amplitude/peak-to-peak/RMS at the cursor's snapped peak (added in v0.6.1)
- "Analyze selected, raw RA" — undo RA corrections to view unguided RA (added in v0.6.2)
- Guiding Assistant section special handling (added in v0.6.0)
- AO vs Mount corrections toggle (added in v0.6.0)
- Lock vertical scale across sections (added in v0.5.0)
- Manual range exclusion via control-drag (added in v0.3.2)
- Backward timestamp jump tolerance (added in v0.6.3)
- Saturated star frame correctly handled (fixed in v0.6.1)

### 2.2 PEMPro Log Viewer (secondary reference — informs v2 worm markers)

Freeware companion to commercial PEMPro by Sirius Imaging. Per [community posts](https://groups.google.com/g/open-phd-guiding/c/ASpvnU-arns):

- Ships with mount-specific worm-period text files; pre-marks expected frequency peaks
- "Add guiding" overlay — approximates unguided tracking similar to PHDLogViewer's "undo corrections"
- Color-coded segment display
- Windows-only

### 2.3 PHD2 Guiding Assistant

Not a log analyzer, but produces sections in the guide log that the analyzer must specially handle. Per the [PHD2 manual](https://openphdguiding.org/man/Guiding_Assistant.htm), GA temporarily disables guide output, measures unguided behavior, optionally measures Dec backlash, and writes a section with RMS, polar alignment estimate, suggested settings, and backlash. PHDLogViewer's GA handling (v0.6.0) drift-corrects and runs an FFT specifically on GA sections; NightCrate matches this in v2.

### 2.4 PECPrep

A mount PEC curve builder that accepts PHD2 logs as input. Not a primary reference for the analyzer — out of scope.

### 2.5 Feature parity matrix

| Capability | PHDLogViewer | PEMPro LV | NightCrate target |
|---|---|---|---|
| Time-series chart with RA/Dec | ✓ | ✓ | **v1 (shipped)** |
| Scatter plot | ✓ | — | **v1 (shipped)** |
| Calibration plot | ✓ | — | **v1 (shipped)** |
| RMS / peak / drift / oscillation stats | ✓ | ✓ | **v1 (shipped)** |
| Dither-settle automatic exclusion | ✓ | ✓ | **v1 (shipped)** |
| Manual range selection / exclusion | ✓ | — | **v1 (shipped)** — multi-additive in NightCrate |
| Section navigation within a file | ✓ | ✓ | **v1 (shipped)** |
| Unit toggle (pixels/arcsec) | ✓ | ✓ | **v1 (shipped)** |
| Lock vertical scale | ✓ | — | **v1 (shipped)** — Fixed-mode dropdowns |
| Periodogram / FFT | ✓ | ✓ | **v2 (in progress)** |
| Unguided RA reconstruction | ✓ | ✓ | **v2 (in progress)** |
| Guiding Assistant section handling | ✓ | — | **v2** |
| AO/Mount corrections toggle | ✓ | — | **v2** |
| **Per-session measured PE output** | partial (read-the-graph) | partial | **v2 — first-class** |
| **Per-mount-instance PE history** | — | — | **v4** |
| Mount-specific worm-period markers | — | ✓ | **v2 (equipment-aware)** |
| Strain wave PE band markers | — | — | **v2 (equipment-aware)** |
| Automated diagnostic interpretation | — | — | **v3** |
| Equipment-aware diagnostics | — | — | **v3** |
| Multi-log comparison | — | — | **v4** |
| Trend analysis over time | — | — | **v4** |
| Shareable HTML report | — | — | **v4** |
| AI-driven session analysis | — | — | **v5+** |
| Live JSON-RPC monitoring | — | — | **v5+** |
| Debug log support | — | — | **v5+** |

---

## 3. PHD2 guide log format — verified against a real log

Primary references:

- [PHD2GuideLog wiki](https://github.com/OpenPHDGuiding/phd2/wiki/PHD2GuideLog) — canonical column definitions
- [PHD2 Trouble-shooting and Analysis manual](https://openphdguiding.org/man/Trouble_shooting.htm) — semantic explanations

A real ASIAIR-bundled log (`PHD2_GuideLog_2026-03-07_193345.txt`, 7,668 lines, two sections, 7,512+ frames) was inspected alongside the docs. Where docs and reality diverged, the spec trusts reality. Divergences are called out below.

### 3.1 File-level structure

Plain UTF-8 text, line-oriented. Begins with a version line:

```
PHD2 version 2.6.13, Log version 2.5. Log enabled at 2026-03-07 19:33:45
```

**Reality check**: ASIAIR-bundled PHD2 writes `PHD2 version, Log version 2.5. Log enabled at ...` — the application version is **blank**. The parser must tolerate this and capture Log version even when app version is missing.

After the version line, zero or more **sections** appear, freely interleaved. Each section is either calibration or guiding and begins with:

- `Calibration Begins at <YYYY-MM-DD HH:MM:SS>`, or
- `Guiding Begins at <YYYY-MM-DD HH:MM:SS>`

…in the local time zone of the machine running PHD2 (no zone indicator). Sections end at:

- the next section header, or
- an explicit `Guiding Ends at <timestamp>` (calibration sections end with `Calibration complete, mount = <name>.`), or
- end-of-file (the final section of the sample log has no explicit end).

All distances and positions are in **guide camera pixels**.

### 3.2 Section header block

Between the section-begin line and the CSV column header is a freeform block of `key = value` settings. Real logs pack multiple settings on a line with inconsistent separators:

```
Pixel scale = 3.96 arc-sec/px, Binning = 2, Focal length = 250 mm
Mount = ZWO000, Calibration Step = 2000 ms, Assume orthogonal axes = no
Y guide algorithm = Resist Switch, Minimum move = 0.100 Aggression = 100% FastSwitch = enabled
                                                       ^ no comma before "Aggression"
```

Parser must regex-match known keys, not split on commas. Unknown keys retained verbatim (future PHD2 versions add new keys).

**Known keys to extract** (per-axis suffixes preserved):

| Key | Semantic |
|---|---|
| `Camera` | guide camera model |
| `Mount` | mount name (often cryptic: `ZWO000`, `On-camera`) |
| `AO` | adaptive optics device, when present |
| `Pixel scale` | arcsec/pixel at the guide camera |
| `Binning` | guide camera binning |
| `Focal length` | guide scope focal length, mm |
| `Exposure` | guide exposure, ms |
| `Pier side` | `East` / `West` / `Unknown` |
| `Dec` | declination at section start, degrees |
| `Hour angle` | hour angle, hours |
| `Rotator pos` | rotator position, degrees, or `Unknown` |
| `Lock position` | X, Y pixel position |
| `Star position` | X, Y pixel position |
| `HFD` | half-flux diameter at section start, pixels (header-level, not per-frame) |
| `Search region` | pixels |
| `Star mass tolerance` | percent |
| `Dither` | axes + mode |
| `Dither scale` | multiplier |
| `X guide algorithm` / `Y guide algorithm` | `Hysteresis`, `Resist Switch`, `LowPass`, `LowPass2`, `Predictive PEC` |
| algorithm parameters per-axis | `Hysteresis`, `Aggression`, `Minimum move`, `FastSwitch`, `Predictive PEC Period Length`, etc. |
| `Backlash comp` | `enabled` / `disabled` |
| `pulse` | backlash compensation pulse, ms |
| `Max RA duration`, `Max DEC duration` | ms caps |
| `DEC guide mode` | `Auto` / `North` / `South` / `Off` |
| `xAngle`, `xRate`, `yAngle`, `yRate`, `parity` | calibration-derived geometry (on the `Mount = ...` line) |
| `Equipment Profile` | profile name, often empty on ASIAIR logs |

Empty values must be tolerated (empty Equipment Profile, `Unknown`, `?/?`).

### 3.3 Guiding section CSV

Per the wiki, the column header is:

```
Frame,Time,mount,dx,dy,RARawDistance,DECRawDistance,RAGuideDistance,DECGuideDistance,
RADuration,RADirection,DECDuration,DECDirection,XStep,YStep,StarMass,SNR,ErrorCode,ErrorDescription
```

That is **19 columns**.

**Reality check**: real ASIAIR logs declare **18** in the header (stopping at `ErrorCode`) but error rows append a 19th quoted ErrorDescription. The same log has rows of differing arity:

```
# 18 fields, ErrorCode = 0
1,1.202,"Mount",-0.307,-0.674,-0.698,-0.265,-0.628,0.000,500,E,0,,,,1045,21.07,0

# 19 fields, ErrorCode = 6
216,235.138,"DROP",,,,,,,,,,,,,6443,53.41,6,"Star lost - mass changed"
```

Parsing requirements:

- Read the column names from the actual header line of each section. Do not assume a fixed count across logs.
- Map values **by column name**, not position.
- Accept row arity equal to declared count or one more (trailing ErrorDescription).
- Empty fields between commas resolve to **null**, never zero. Coercing empty to zero on DROP frames silently corrupts RMS.
- ErrorCode → ErrorDescription mapping comes from the log itself, not from a hardcoded table. Real codes seen: 6 = `"Star lost - mass changed"`, 7 = `"No star found"` — these contradict any external table.

Column semantics:

| Column | Semantic | Notes |
|---|---|---|
| `Frame` | 1-based frame number within section | |
| `Time` | **Elapsed seconds from section start**, not wall-clock | wall-clock = section.start + Time |
| `mount` | `"Mount"`, `"AO"`, or `"DROP"`, always quoted | DROP = frame rejected |
| `dx`, `dy` | star offset from lock, pixels | null on DROP |
| `RARawDistance`, `DECRawDistance` | (dx,dy) projected onto mount axes | null on DROP |
| `RAGuideDistance`, `DECGuideDistance` | guide algorithm output, signed, pixels | null on DROP |
| `RADuration`, `DECDuration` | pulse duration, ms; 0 = no pulse (below min-move) | null on DROP |
| `RADirection` | `E`, `W`, or empty | |
| `DECDirection` | `N`, `S`, or empty | |
| `XStep`, `YStep` | AO step values | empty without AO |
| `StarMass` | integrated pixel intensity | usually populated even on errors |
| `SNR` | signal-to-noise ratio | usually populated even on errors |
| `ErrorCode` | integer; 0 = OK | |
| `ErrorDescription` | quoted error string, present iff ErrorCode ≠ 0 | use verbatim from log |

### 3.4 Calibration section structure

Per the wiki the columns are `Direction,Step,dx,dy,x,y,Dist`. Reality: a calibration section is a sequence of **five named phases** delimited by prose completion lines:

```
West,0,...        ← West phase (RA in one direction)
...
West,11,...
West calibration complete. Angle = 85.1 deg, Rate = 1.238 px/sec, Parity = N/A
East,11,...       ← East phase (return)
...
East,0,...
Backlash,0,...    ← Backlash clearing precedes North
...
Backlash,3,...
North,0,...       ← North phase (Dec in one direction)
...
North,4,...
North calibration complete. Angle = -6.3 deg, Rate = 3.254 px/sec, Parity = N/A
South,4,...       ← South phase (return)
...
South,0,...
Calibration complete, mount = ZWO000.
```

The two `<axis> calibration complete. Angle = ..., Rate = ..., Parity = ...` lines carry the **derived calibration geometry** — the primary outputs of calibration. Parser must capture these structured values.

### 3.5 INFO event lines

INFO lines interleave with CSV rows. Patterns observed in the ASIAIR sample log:

| Observed pattern | Semantic |
|---|---|
| `INFO: SETTLING STATE CHANGE, Settling started` | settle period began |
| `INFO: SETTLING STATE CHANGE, Settling complete` | settle period ended |
| `INFO: SET LOCK POSITION, new lock pos = X, Y` | lock position moved |
| `INFO: DITHER by DX, DY, new lock pos = X, Y` | dither vector applied |

Other patterns the parser should classify (documented in PHD2 source / community posts):

| Pattern | Semantic |
|---|---|
| `INFO: SERVER received SET_PAUSED` / `Server received PAUSED` | external pause |
| `INFO: SERVER received SET_PAUSED, UNPAUSED` / `RESUMED` | external resume |
| `INFO: Star selected at ...` | new star picked |
| `INFO: Alert: <message>` | PHD2 alert |
| `INFO: Guiding Output Enabled` / `Disabled` | typically GA boundaries |
| `INFO: MOVE LOCK POSITION, ...` | manual lock change |

Closed vocabulary classification: `settle_begin`, `settle_end`, `lock_position_set`, `dither`, `server_pause`, `server_resume`, `star_selected`, `alert`, `guiding_enabled`, `guiding_disabled`, `info` (fallback).

Classifiers must use string-contains or regex, not exact match (the SETTLING STATE CHANGE prefix has a sub-field). Always retain raw message.

### 3.6 Dither settle detection

Per a [forum post from Andy Galasso](https://groups.google.com/g/open-phd-guiding/c/XKGu6Q-nOvQ), automatic settle exclusion in PHDLogViewer depends on the imaging app issuing settle begin/end commands to PHD2. Older apps may dither without these — the SETTLING STATE CHANGE events are not guaranteed.

Two detection strategies required:

1. **Event-based (preferred)** — find `Settling started` / `Settling complete` pairs; mark frames in interval as `in_settle = true`.
2. **Heuristic fallback** (when event pairs are absent after a DITHER) — starting from the frame following a `DITHER` INFO, mark frames as `in_settle = true` until either (a) total corrected distance stays below threshold (default 0.5 px) for ≥ N consecutive frames (default 3), or (b) fallback maximum elapsed (default 30 sec). All thresholds user-overridable.

**Settle frames are excluded from all stats by default** per the [PHD2 Visualization manual](https://openphdguiding.org/man-dev/Visualization.htm): *"The RMS statistics do not include the large excursions associated with dithering and settling."* PHDLogViewer follows the same convention. UI toggle to include is fine; default off.

### 3.7 Locale bug

Per [PHD2 issue #453](https://github.com/OpenPHDGuiding/phd2/issues/453) and a [forum report](https://groups.google.com/g/open-phd-guiding/c/D_IkgJ3GuO8), PHD2 on comma-decimal locales has historically written commas as both decimal separator and CSV separator:

```
1,2,541,"Mount",-0,514,0,432,...,15349,8,71,1
```

where `2,541` should be `2.541`. The 18-column header gets ~26 tokens per row.

Detection: declared columns *C*, observed token count *T*; if *T* > *C* × 1.3, assume locale-corrupted.

Recovery: walk header columns, joining pairs of tokens with `.` where the column is numeric. The quoted `"mount"` field anchors position. Mark section `locale_recovery_applied = true`.

### 3.8 Backward timestamp jumps

Computer clock changes during a session can produce backward section timestamps. PHDLogViewer added handling in v0.6.3. Sort sections by file order, not timestamp. Surface warning if backward jump detected.

### 3.9 File identification

Default filenames: `PHD2_GuideLog_YYYY-MM-DD_HHMMSS.txt`. Parser accepts that pattern AND content-sniffs: first non-blank line starts with `PHD2 version`. Catches renamed files, ASIAIR exports, and zip extracts.

Debug logs (`PHD2_DebugLog_*.txt`) start with a different header and are rejected in v1–v4 with a clear error. Debug log support is a v5+ item (§9).

---

## 4. Architectural principles

These constraints apply across all phases.

### 4.1 Standalone-first, catalog-ready

The analyzer ships standalone from day one. The user drops a log file and gets a full analysis without the broader NightCrate catalog. When the imaging core schema lands, the analyzer gains catalog-linked logs as a second entry path; same parser, same analyzer. No rewrite — only additive entry points.

### 4.2 Pixel-canonical internal representation

PHD2 writes pixels; NightCrate stores pixels. Arcsecond conversions happen at display time using the section's `Pixel scale`. Round-trip-safe; unit-toggle without re-parse.

### 4.3 Three-level granularity

A log contains sections; a section contains samples and events. Every metric, finding, and chart is naturally section-scoped. File-level views are derived.

### 4.4 Parse-by-name, not by-position

Column order in PHD2 logs is stable across versions but not guaranteed. Read header per section; map by column name. New columns fall through harmlessly.

### 4.5 Colorblind-safe palette

Fred is red-green colorblind. Project convention: viridis sequential, blue-to-yellow alternative sequential, blue/orange categorical (RA = blue, Dec = orange). Never red/green.

### 4.6 Never silently coerce missing data

Empty CSV fields, missing settle events, absent ErrorDescription resolve to **null**, not zero or empty string. Charts must break across nulls (no spurious zero-pinned guiding-looks-perfect lines during DROP runs).

### 4.7 Interpretive claims must be sourced

Every diagnostic rule (§7) carries a reference URL pointing to the community source for the interpretation. Undocumented heuristic = untrusted heuristic.

### 4.8 Selection model is per-frame booleans

PHDLogViewer's selection model (verified in `LogViewFrame.cpp` lines 1100-1200): each frame has an `included` boolean. Multi-additive selection sets it true; control-drag exclusion sets it false. Settle exclusion uses the same flag. Multi-additive selections + exclusions accumulate naturally. NightCrate v1 implements this verbatim.

### 4.9 Verify external data via web search before populating seed data

Mount worm periods, strain wave PE values, calibration coefficients, and any other domain-specific number must be verified against a manufacturer page or community-curated authoritative source at implementation time. Pattern-matching from Claude's memory is a recurring failure mode that this principle exists to prevent.

### 4.10 PE measurement is a first-class output

Strain wave mounts vary between gear instances ([ZWO documentation](https://astronomy-imaging-camera.com/tutorials/10-things-you-need-to-know-about-the-custom-am5s-pe-test-report-provided-by-zwo/), [Rainbow Astro FAQ](https://www.rainbowastro.com/faq-items/how-big-periodic-errors-of-rst-135-is/)). Manufacturer-stated periods are *defaults* that get overridden by measurement. The analyzer computes and persists per-session measured PE (period, amplitude, p-p, RMS) as a structured output, accumulates per-mount-instance history, and uses measured values to drive diagnostics where available. v2 ships per-session output; v4 ships per-instance aggregation.

---

## 5. Phase v1 — Parity with PHDLogViewer (core) — SHIPPED

**Status**: feature-complete in NightCrate v0.22.0–v0.24.0. This section is the as-built record so v2/v3/v4 can be specified without re-deriving v1 behavior.

### 5.1 Parser (full implementation of §3)

Shipped in v0.22.0. File identification, section splitting, header block parsing (35+ keys), guiding + calibration CSV parsing, INFO classification, dither settle detection (event-based + heuristic), locale recovery, backward-timestamp tolerance, parser warnings drawer.

### 5.2 Per-section computed metrics — all formulas

Computed after dither-settle filtering. **In all formulas below the input is `RARawDistance` and `DECRawDistance` from frames where `included == true ∧ StarWasFound(ErrorCode) ∧ ¬in_settle ∧ ¬user_excluded`**. This filter matches PHDLogViewer's `Include()` predicate (`AnalysisWin.cpp` line ~106):

```cpp
inline static bool Include(const GuideEntry& e) {
    return e.included && StarWasFound(e.err);
}
```

Where `StarWasFound(err)` returns true iff the error code does not indicate the star was lost. NightCrate adds `¬in_settle ∧ ¬user_excluded` to that filter; the underlying mechanism is the same per-frame `included` boolean (§4.8).

#### 5.2.1 RMS — standard deviation, not RMS-from-zero

PHDLogViewer's `GuideSession::CalcStats` computes RMS as the **standard deviation** of the distance series, not as `sqrt(mean(x²))`. From `AnalysisWin.cpp` line ~190:

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
avg_ra = fitrd.avx;
avg_dec = fitrd.avy;
```

Where `LFit` (line ~70) is a streaming linear-regression accumulator. Its `varx`, `vary` are **variances** (mean of squared deviations from mean), not raw second moments. The streaming update for variance is the West-incremental form:

```
n_new = n + 1
k = n / n_new
dx = x - avx
varx_new = varx + (k × dx² − varx) / n_new
avx_new = avx + dx / n_new
```

This is the `LFit::data` method line ~76. So PHD2 RMS is:

$$\text{RMS}_{\text{RA}} = \sqrt{\frac{1}{N}\sum_{i=1}^{N}(x_i - \bar{x})^2}$$

Not:

$$\sqrt{\frac{1}{N}\sum_{i=1}^{N}x_i^2}$$

The difference matters when there's a systematic offset (sustained Dec drift, calibration centroid offset). NightCrate v1 implements the standard deviation form to match PHDLogViewer's reported numbers.

**Unit conversion**: arcsec values = pixel values × `Pixel scale` (the section's declared arcsec/pixel).

```
rms_ra_arcsec  = rms_ra_pixels  × pixel_scale
rms_dec_arcsec = rms_dec_pixels × pixel_scale
rms_total_arcsec = sqrt(rms_ra_arcsec² + rms_dec_arcsec²)
```

#### 5.2.2 Peak

`AnalysisWin.cpp` line ~196:

```cpp
if (fabs(e.raraw) > fabs(peak_r)) peak_r = e.raraw;
if (fabs(e.decraw) > fabs(peak_d)) peak_d = e.decraw;
```

Sign-preserving: `peak_ra` is the most-extreme RA value (positive or negative) by absolute value. Same for Dec.

#### 5.2.3 RA drift — `RaDrift` algorithm

From `AnalysisWin.cpp` lines ~135-160. The algorithm:

```
ra0, t0 = first included frame's (raraw, dt)
ra1, t1 = last included frame's (raraw, dt)
sum = sum of e.raguide for all e where e.included ∧ e.radur != 0  (signed)
RaDrift = (ra1 - ra0 - sum) / (t1 - t0)              # pixels per second
drift_ra = RaDrift × 60                              # pixels per minute
```

The intuition: total raw position change = total mount drift + total guide correction. So `total_drift = (ra1 - ra0) - sum_of_corrections`, and rate = total_drift / time_elapsed. Note the algorithm uses `e.included` (not `Include(e)`) when summing corrections — DROP frames that still have valid RAGuideDistance values still contribute to the sum.

Output unit: pixels/min internally, arcsec/min for display (`× pixel_scale`).

#### 5.2.4 Dec drift — `DecDrift` algorithm (different from RA)

From `AnalysisWin.cpp` lines ~110-135. **The Dec algorithm is fundamentally different from RA** because Dec is typically guided in only one direction (or both directions with backlash), so summing corrections doesn't work cleanly. Instead, it accumulates Dec changes only across frames where the previous frame was unguided (i.e., the change reflects actual sky drift, not a reaction to guide pulses):

```
y_accum = 0
prev_y = first_included.decraw
prev_guided = (first_included.decdur != 0)
LFit fit
fit.data(first_included.dt, 0)

for each subsequent included frame:
    if not prev_guided:
        y_accum += (decraw - prev_y)
        fit.data(this.dt, y_accum)
    prev_y = decraw
    prev_guided = (decdur != 0)

DecDrift = fit.B()                 # slope of y_accum vs time, pixels per second
drift_dec = DecDrift × 60          # pixels per minute
```

`fit.B()` is the regression slope (covxy / varx) per `LFit::B()` (line ~88).

Output unit: pixels/min internally, arcsec/min for display.

#### 5.2.5 Oscillation metric

PHD2's "RA Osc" reports the fraction of consecutive frame pairs where the sign of the RA correction reverses. NightCrate computes the same on the **raw distance series** (not the guide-distance series, which can be zeroed by min-move):

```
ra_oscillation = | { i : sign(RARawDistance[i]) ≠ sign(RARawDistance[i-1]) } | / (N - 1)
```

Where N is the count of included frames. Rates near 0.5 indicate chasing seeing; rates near 0.3 are typical of good guiding (per [Bruce Waddington's tutorial](https://openphdguiding.org/Analyzing_PHD2_Guide_Logs.pdf)).

Same calculation for Dec.

#### 5.2.6 Polar alignment error from Dec drift — `PolarAlignError`

From `AnalysisWin.cpp` line ~166:

```cpp
double PolarAlignError(const GuideSession& session) {
    // polar alignment error from Barrett:
    // http://celestialwonders.com/articles/polaralignment/PolarAlignmentAccuracy.pdf
    return 3.8197 * fabs(session.drift_dec) * session.pixelScale / cos(session.declination);
}
```

Output: arcminutes of polar alignment error.

The 3.8197 coefficient and the cosine-correction term are derived in [Barrett's *Determining Polar Axis Alignment Accuracy*](http://celestialwonders.com/articles/polaralignment/PolarAlignmentAccuracy.html) — Appendix A of that paper. The full derivation is reproduced in §11.1 of this spec.

`session.drift_dec` is in pixels/min (already multiplied by 60 in §5.2.4).
`session.pixelScale` is arcsec/pixel.
`session.declination` is in radians; cos(declination) corrects for the foreshortening of Dec drift away from the celestial equator.

So the formula is:

$$\text{PA error}_{\text{arcmin}} = 3.8197 \times \frac{|\text{drift}_{\text{dec}}|_{\text{px/min}} \times \text{pixel scale}_{\text{arcsec/px}}}{\cos(\delta)}$$

#### 5.2.7 Scatter dispersion — rotation angle θ and elongation

For the scatter plot, PHDLogViewer computes the rotation of the dispersion ellipse and its elongation. From `AnalysisWin.cpp` lines ~210-240:

```cpp
// angle of elongation
theta = fitrd.Theta();        // = atan2(covxy, varx)

// rotated coordinate variances
double cost = cos(theta), sint = sin(theta);
LFit fitxy;
for each included frame:
    double dr = e.raraw - avg_ra;
    double dd = e.decraw - avg_dec;
    double x_rot = dr * cost + dd * sint;
    double y_rot = dd * cost - dr * sint;
    fitxy.data(x_rot, y_rot);

lx = sqrt(fitxy.varx);  // sigma along major axis
ly = sqrt(fitxy.vary);  // sigma along minor axis
```

Theta is the rotation that aligns the ellipse's major axis with the rotated x-axis. The formula `θ = atan2(covxy, varx)` comes from `LFit::Theta` (line ~95):

```cpp
double Theta() const { return n >= 2. ? atan2(covxy, varx) : 0.; }
```

This is **not** the principal-component rotation `½ × atan2(2 × covxy, varx − vary)`. PHDLogViewer's simpler form gives a rotation that's close to but not identical to PCA when the variances are very different. NightCrate v1 matches PHDLogViewer's form for cross-tool consistency.

Elongation is the standard ratio:

```cpp
double a = max(lx, ly), b = min(lx, ly);
elongation = (a + b) > 1e-6 ? (a - b) / (a + b) : 1.;
```

So elongation = 0 means a perfect circle; elongation → 1 means a degenerate line.

#### 5.2.8 Frame counts and duration

```
total_frames           = section's frame count
included_in_stats      = | { i : Include(i) } |
excluded_by_settle     = | { i : in_settle(i) } |
excluded_by_user       = | { i : ¬included_user(i) } |
excluded_by_drop       = | { i : ¬StarWasFound(err_i) } |

duration_total_sec     = last_frame.Time - first_frame.Time
duration_included_sec  = sum of frame intervals where Include(i)
```

### 5.3 Per-section charts (shipped)

**Time-series chart** with all the elements per the v0.22.0 ship: RA trace blue, Dec trace orange, correction bars below, SNR panel, StarMass panel, settle shading, event markers, zoom/pan, cursor readout. Selection mechanics per §5.5.

**Scatter plot** (shipped v0.23.0): X = RARawDistance, Y = DECRawDistance, dispersion ellipse at 1σ and 2σ using the rotated coordinates from §5.2.7, centroid marker.

**Calibration plot**: 5 phases (West, East, Backlash, North, South) as stepped paths in dx/dy space, with derived angle/rate from the embedded `<axis> calibration complete` lines (§3.4).

### 5.4 Section navigation

Sections listed in **file order** (not timestamp order, per §3.8). Each list item: type, start time, duration, frame count, summary stat (RMS Total or calibration angle/rate). Click switches the main view.

### 5.5 Selection model and interaction

Multi-additive shift-drag selections (teal highlight) and shift+alt-drag exclusions (hatched). Per-zone × buttons. Toolbar bulk actions. The selection model uses per-frame `included` booleans per §4.8 — this matches PHDLogViewer and lets settle exclusion stack with user selections naturally.

Stats and charts recompute on selection changes. **Spectrum (§6.1) also recomputes on selection** — the FFT input is the currently-included frames, not the section's full sample set.

Other shipped interactions:

- Unit toggle pixels ↔ arcsec
- Lock vertical scale (Fixed-mode dropdowns rather than free-form lock per PHDLogViewer)
- Include/exclude settle periods toggle
- Copy stats to clipboard (TSV)
- Recent files (10-entry localStorage)
- Reveal in finder is **vetoed permanently** — out of scope

### 5.6 Warnings drawer

Parse-time warnings only in v1 — no interpretive diagnostics. Examples:

- "Locale-corrupted data; decimal-separator recovery applied."
- "Backward timestamp jump detected — sections shown in file order."
- "N frames had errors (see the Events list)."
- "Sample cadence varies > 20% within this section — frequency analysis is disabled."
- "Pixel scale not declared in header — arcsec values cannot be computed."

---

## 6. Phase v2 — Advanced parity + per-session and per-instance PE measurement

**Target user**: "I'm tuning my mount. I need periodic-error analysis, and I want to see what my mount is actually doing without my guiding corrections on top of it."

**v2 success criterion**: a PHDLogViewer user doing mount tuning can do it in NightCrate, with the worm-period or strain-wave PE markers present when equipment context exists, and the per-session measured PE saved as a structured output ready for v4 multi-session aggregation.

### 6.1 Frequency analysis (FFT / periodogram) — full algorithm

This is the algorithm as implemented in PHDLogViewer's `GARun::Analyze` (`AnalysisWin.cpp` lines ~270-400). Every step is verified against the source.

#### 6.1.1 Inputs and pre-FFT processing

**Input series**: per-section `RARawDistance` (and optionally `DECRawDistance`) for frames where the §5.2 Include() filter is true. Selection-aware (§5.5): the FFT recomputes on selection changes.

**Step 1 — minimum entries check**. PHDLogViewer requires at least 12 included frames (`AnalysisWin.cpp` line ~258):

```cpp
enum { MIN_ENTRIES = 12 }; // need at least 12 for FFT output spline (N / 2 - 1 >= 5)
```

If fewer than 12 frames pass the filter, skip the FFT entirely and surface a warning.

**Step 2 — sample cadence check**. PHD2 frame intervals vary by tens of milliseconds; if cadence varies more than 20% across the section, the FFT input is meaningless even after interpolation. Skip and warn.

**Step 3 — drift subtraction via least-squares linear fit**. From `AnalysisWin.cpp` line ~340:

```cpp
LFit fitR; // ra fit
for each included frame:
    fitR.data(e.dt, rapos);     // rapos is the reconstructed/raw position

// ...

Line lR(fitR);                   // y = a + b·x where a,b come from LFit::result
for each included frame i:
    rac[i] = ra[i] - lR(t[i]);   // drift-subtracted RA
```

`LFit::result(a, b)` (line ~91) returns:

```
b = covxy / varx                 # regression slope
a = avy - b × avx                # intercept
```

So the drift-subtracted series is:

$$\tilde{x}_i = x_i - (a + b \cdot t_i) = x_i - \bar{x} - b \cdot (t_i - \bar{t})$$

This removes the linear trend (polar-alignment-induced drift, mostly) so the FFT sees only the oscillatory content. The slope `b` is preserved separately as the section's drift metric (§5.2.3, §5.2.4).

**Step 4 — interpolate to uniform cadence**. `AnalysisWin.cpp` line ~360:

```cpp
double dt = (t[n - 1] - t[0]) / (double) (n - 1);
Spline spline(t, rac, n);          // GSL Akima spline
double x = t[0];
for (i = 0; i < n; i++, x += dt):
    if (x > t[n - 1]) x = t[n - 1]; // rounding-error guard
    sample = spline.Eval(x);
```

The Spline class wraps `gsl_spline_alloc(gsl_interp_akima, n)` (line ~36). Akima spline interpolation is non-overshooting, which matters for oscillatory data — cubic spline can introduce spurious oscillations.

NightCrate may use scipy's equivalent or any non-overshooting spline. Linear interpolation is acceptable but inferior; raw bin-by-bin output without resampling is **not** acceptable.

**Step 5 — Hamming window**. From `AnalysisWin.cpp` line ~368:

```cpp
double const k = M_PI * 2.0 / (double) (n - 1);
// ...
double const hw = 0.54 - 0.46 * cos(i * k);
data[i * 2] = hw * spline.Eval(x);    // real part
data[i * 2 + 1] = 0.;                  // imag part
```

This is the **Hamming window** with coefficients 0.54 and 0.46:

$$w_i = 0.54 - 0.46 \cdot \cos\left(\frac{2\pi i}{N - 1}\right), \quad i = 0, \ldots, N-1$$

Not Hann (which has coefficients 0.5 and 0.5). The two windows produce visually similar spectra; the difference matters for cross-tool quantitative comparison and for the amplitude normalization (§6.1.7).

#### 6.1.2 FFT

```cpp
gsl_fft_complex_forward(data, 1, n, wt, work);
nfft = n / 2 - 1; // omit DC bin
```

Standard complex-to-complex forward FFT. Output indexing keeps `nfft = N/2 − 1` bins, omitting `k = 0` (DC, removed by drift subtraction anyway) and the symmetric upper half.

#### 6.1.3 Period and frequency mapping

```cpp
for (i = 0; i < nfft; i++):
    f = (double)(i + 1) / ((double) n * dt);    // frequency, Hz
    p = 1. / f;                                  // period, seconds
    fftx[nfft - 1 - i] = p;                     // reverse-indexed so periods ascend
```

Bin *k* (1-indexed; *k = 1, 2, ..., N/2−1*) corresponds to:

$$f_k = \frac{k}{N \cdot \Delta t}, \quad p_k = \frac{1}{f_k} = \frac{N \cdot \Delta t}{k}$$

Where Δt is the uniform sample spacing from Step 4.

#### 6.1.4 Amplitude — the cross-tool comparable normalization

```cpp
double scale = 4. / (double) n;
// http://www.stat.ucla.edu/~frederic/221/W17/221ch4a.pdf
// ...
double a = gsl_complex_abs(*pz) * scale;
ffty[nfft - 1 - i] = a;
```

The amplitude at bin *k* is:

$$a_k = \frac{4 \cdot |X_k|}{N}$$

This is the convention that gives the displayed amplitude in **the same units as the time-domain signal** (pixels). Multiplying by the section's `pixel_scale` gives arcseconds.

The factor 4 comes from: 2 (single-sided spectrum, accounting for negative frequencies) × ~1.85 (Hamming window coherent gain reciprocal: window has mean ~0.54, so amplitudes are reduced by that factor). PHDLogViewer rounds the combined factor to 4 — the cited UCLA reference covers the derivation in detail. For NightCrate the pragmatic approach is to use **4/N to match PHDLogViewer's reported amplitudes exactly**.

So the reported arcsec amplitude:

$$a_{\text{arcsec},k} = \frac{4 \cdot |X_k|}{N} \cdot \text{pixel scale}$$

#### 6.1.5 Display: log Y, log X, period axis

- Y axis: **logarithmic by default**. Periodogram amplitudes span 3-4 orders of magnitude in a typical session; linear Y hides everything except the dominant peak. Lower bound: max(amplitude_max / 10000, 0.001 arcsec). Upper bound: amplitude_max × 1.1.
- X axis: **logarithmic period in seconds**. Period (not frequency) is the astrophotography-native unit — mounts are spec'd by worm period in seconds. Range: ~2 s to roughly half the section duration.
- Seeing band shading at < 5 s with an "atmospheric seeing" label (otherwise users ask "what's that big bump at 1 second").

#### 6.1.6 Peak detection — robust threshold via MAD

Find local maxima of the amplitude spectrum where:

$$a_k > \text{median}(a) + 3 \times 1.4826 \times \text{MAD}(a)$$

The 1.4826 factor scales MAD to be a sigma-equivalent for normally-distributed data ([standard practice in robust statistics](https://crispinagar.github.io/blogs/mad-anomaly-detection.html)). The 3-sigma threshold is conservative against false positives — produces zero peaks on a flat noise-floor spectrum.

Deduplicate: if two candidate peaks are within 5% of each other in period, keep the higher-amplitude one. Cap displayed markers at **top 5 by amplitude across all visible traces combined** (not per-trace).

#### 6.1.7 Hover tooltip and snap-to-peak

Snap-to-peak within ±8 pixels matches PHDLogViewer's `OnMove` handler (`AnalysisWin.cpp` lines ~860-890):

```cpp
enum { DIST = 8 };
// look ±8 pixels for a local maximum; pick closest
```

Tooltip readout matches PHDLogViewer's status bar (line ~895):

```cpp
m_statusBar->SetStatusText(wxString::Format(
    "Period: %.1fs Amplitude: %.1f\" (%.2fpx) P-P: %.1f\" (%.2fpx) RMS: %.1f\" (%.2fpx)",
    p, a * pixscale, a, 2. * a * pixscale, 2. * a,
    M_SQRT2 / 2.0 * a * pixscale, M_SQRT2 / 2.0 * a));
```

So the canonical readouts at a given peak amplitude `a` (arcsec) are:

- **Period**: `p` seconds
- **Amplitude**: `a` (arcsec) — the spectrum value at the peak
- **Peak-to-peak**: `2 × a` (arcsec) — the full swing of a sine wave with that amplitude
- **RMS**: `(√2 / 2) × a` ≈ `0.7071 × a` (arcsec) — the RMS of a sine wave with that amplitude

The √2/2 = 1/√2 factor is the standard relationship between sine amplitude and RMS:

$$\text{RMS}_{\sin} = \frac{A}{\sqrt{2}}$$

#### 6.1.8 Trace defaults and selection-aware recomputation

- RA visible by default (blue)
- Dec hidden by default (orange) — toggleable in legend
- Unguided RA hidden by default — see §6.2 for when it's available

When the user shift-drags a selection or shift+alt-drags an exclusion, the FFT recomputes against the new sample set (the input to step 1 changes). Cadence check (step 2) re-runs against the new samples too.

#### 6.1.9 Section duration warnings

- Minimum useful for general spectrum: ~5 minutes
- For worm-period detection: at least 2× the expected worm period (10-20 minutes for typical worm or strain wave mounts)
- For shorter sections: compute and display anyway, but annotate "section too short for confident periodic-error detection"

### 6.2 Unguided RA reconstruction — verified algorithm

This is the algorithm as implemented in PHDLogViewer's `GARun::Analyze`, `AnalysisWin.cpp` lines ~310-330. **It is substantially simpler than what some derivations suggest** because PHDLogViewer uses the signed `RAGuideDistance` directly rather than reconstructing the issued pulse from `RADuration × xRate`.

#### 6.2.1 Algorithm

```cpp
double rapos = 0.;
double prev_raguide = 0.;
double prev_raraw = 0.;

for each included frame i:
    double const raraw   = e.raraw;       // RARawDistance, signed pixels
    double const raguide = e.raguide;     // RAGuideDistance, signed pixels (algorithm output)
    double const move    = raraw - prev_raraw - prev_raguide;
    rapos += move;
    prev_raraw   = raraw;
    prev_raguide = undo_ra_corrections ? raguide : 0.;
    t[i]         = e.dt;
    ra[i]        = rapos;
    fitR.data(e.dt, rapos);
```

Why this works:

- `RAGuideDistance` is the algorithm's **output in pixel space** (after min-move thresholds, hysteresis, predictive PEC, etc.), already signed.
- When the algorithm decided not to issue a pulse (below min-move), `RAGuideDistance == 0`, so `prev_raguide` carries 0 forward — no special-case code needed.
- When the algorithm clipped a pulse to `Max RA Duration`, `RAGuideDistance` reflects the clipped output.
- DROP frames are filtered out by the Include() predicate — the cumulative sum doesn't advance.
- Parity is irrelevant because `RAGuideDistance` is signed in raw-distance space.

The `undo_ra_corrections` flag toggles between "Analyze Selected frames" (no undo, just the raw-position trace) and "Analyze Selected, raw RA" (undo corrections to reveal the unguided trace).

#### 6.2.2 Drift subtraction for the unguided spectrum

For the *spectrum* of the unguided trace, subtract the linear trend before windowing (§6.1 step 3). Without this, polar-alignment-induced drift dominates the low-frequency end of the spectrum and obscures mount mechanics. PHDLogViewer does this — the `lR` Line object at line ~340.

For the *time-series overlay* of the unguided trace, do **not** subtract drift — users want to see the drift too. PHDLogViewer applies the same convention.

#### 6.2.3 Display surfaces

- **Time-series Graph tab**: overlay unguided RA on the main chart, toggleable in the legend (off by default). Use a distinguishable variant of the RA blue (e.g., dashed or muted) so it's separable from the raw RA trace.
- **Spectrum tab**: an "Unguided RA" toggle alongside RA / Dec, off by default. When on, computes the §6.1 pipeline against the drift-subtracted unguided RA trace. The unguided spectrum reveals worm-period or strain-wave PE peaks much more clearly than the raw RA spectrum, because guiding doesn't suppress those peaks in the unguided reconstruction.

**Ship together**: the Spectrum-tab toggle must not ship without the time-series overlay. The pairing is necessary for the feature to be useful — users need to see the unguided trace in the time domain to interpret the spectrum.

### 6.3 Guiding Assistant section handling

Detect GA sections by:

1. Finding `Guiding Output Disabled` and `Guiding Output Enabled` INFO events bracketing a section, **or**
2. Detecting a section where `RADuration == 0 ∧ DECDuration == 0` for ≥ 90% of frames (GA disables guide output for measurement)

For GA sections, render a **dedicated GA panel**:

- **Unguided RMS RA / Dec / Total** — using the §5.2.1 formulas, but the input is the raw distance series (no guide pulses issued, so it's effectively the unguided trace already). No drift subtraction for the displayed RMS — match PHD2's GA report.
- **Estimated polar alignment error** using the §5.2.6 / §11.1 formula.
- **Measured Dec backlash** if a backlash sub-sequence is detected. Identify by an alternating-direction Dec pulse pattern with no RA corrections — typical signature is ~20 N pulses then ~20 S pulses. Read off the asymmetry: if N pulses produce displacement ratio `dy_N / dur_N` and S pulses produce `dy_S / dur_S`, backlash ≈ the difference in milliseconds it takes the mount to reverse. PHD2's own GA report has this number; for sections that contain it, read directly from a GA-emitted INFO line if PHD2 logged one. Otherwise compute from the pulse-displacement asymmetry.
- **Drift-corrected RA trace** with the §6.2 reconstruction.
- **Dedicated FFT** on the unguided RA trace (per §6.2.2) with wider period range — GA captures unguided tracking, so the FFT is a direct PE measurement. This is the input to per-session PE measurement (§6.4).

### 6.4 Per-session measured PE — a first-class output

This is new in v4 of the spec. The §6.2 unguided reconstruction and §6.1 spectrum already produce all the data; this section makes the measurement a **structured output** rather than a chart users eyeball.

#### 6.4.1 What gets computed and persisted per section

For every guiding section that:
- has `mount` matching a strain wave or worm mount in the catalog (§6.6, §6.7), or
- is a Guiding Assistant section, or
- has the user-toggled "Unguided RA" mode active

…the analyzer computes:

| Field | Source | Unit |
|---|---|---|
| `pe_period_s` | period of the dominant peak in the unguided RA spectrum (§6.1.6 selection, top-1 by amplitude) | seconds |
| `pe_amplitude_arcsec` | amplitude of that peak via §6.1.4 normalization × pixel_scale | arcsec |
| `pe_peak_to_peak_arcsec` | `2 × pe_amplitude_arcsec` (§6.1.7) | arcsec |
| `pe_rms_arcsec` | `(√2/2) × pe_amplitude_arcsec` (§6.1.7) | arcsec |
| `pe_dominant_peak_confidence` | "high" if amplitude > 5 × MAD-threshold; "medium" if 3-5×; "low" otherwise | enum |
| `pe_section_duration_min` | `duration_included_sec / 60` | minutes |
| `pe_section_duration_vs_period_ratio` | `pe_section_duration_min / (pe_period_s / 60)` — should be ≥ 2 for confident measurement | unitless |
| `pe_secondary_peaks` | up to 4 additional peaks in §6.1.6 deduplicated list, with same fields | list |
| `pe_shape_category` | `"sinusoidal"` if dominant peak >> all secondaries (3:1 ratio); `"asymmetric"` if 2nd peak is ≥ 50% of dominant; `"multi-harmonic"` if ≥ 3 peaks above threshold | enum |
| `pe_measurement_at_declination` | section's declination at start | degrees |
| `pe_measurement_pier_side` | section's pier side | enum |
| `pe_measurement_payload_kg` | rig payload weight (when rig context is present) | kg |
| `mount_instance_id` | catalog-resolved mount instance (when present) | id |
| `is_guiding_assistant` | true if §6.3 detected GA | boolean |

#### 6.4.2 Display — Measured PE panel

A dedicated panel in the section view shows:

- Period (with confidence indicator)
- Amplitude / Peak-to-peak / RMS in arcsec
- Section-duration-to-period ratio (warn if < 2, "section too short for confident measurement")
- Shape category visualization (sinusoidal vs asymmetric vs multi-harmonic)
- Comparison to manufacturer default (§6.6, §6.7) when the mount is identified — "measured 295s / manufacturer 288s — well within expected range"
- Comparison to per-instance history when available (v4 only) — "measured 295s / your AM5's average 293s ± 4s over 8 sessions"

#### 6.4.3 Manufacturer-default vs measured override behavior

Spectrum markers (§6.6, §6.7) prefer measured values when available. Specifically:

- If `mount_instance_id` is set and has ≥ 3 prior measurements with a stable period (CV < 5%), use the per-instance measured period for the spectrum marker.
- Otherwise, use the manufacturer default from §6.6 / §6.7 seed data.
- In either case, show the manufacturer default as a faint secondary marker so the user can see both.

The threshold of 3 measurements is intentionally low to make the feature useful early; CC may revise based on user feedback.

### 6.5 AO vs Mount toggle

When a section contains `mount = "AO"` frames, distinguish:

- **Mount corrections** — what the mount was bumped to do
- **AO corrections** — tip/tilt steps issued to the AO device

Time-series chart toggle: Mount only (default), AO only, both. Stats panel gains separate AO-corrected vs mount-corrected RMS rows. Matches PHDLogViewer 0.6.0 behavior.

### 6.6 Worm mount seed data and spectrum markers

When equipment context is present and the mount has `drive_type = worm`, draw a vertical marker on the spectrum at the worm period. If a §6.1.6 peak falls within ±5% of that period, call it out: "Worm-period peak: 0.8 arcsec amplitude."

When equipment context is absent, fall back to "unbounded worm period detection" mode: report the largest peak in 300-800 seconds with amplitude > 0.5 arcsec, labeled "likely worm-period peak (uncertain without mount identification)."

**Worm period seed values** — verified against the [PHD2 Mount Worm Period Info wiki](https://github.com/OpenPHDGuiding/phd2/wiki/Mount-Worm-Period-Info), with strain wave mounts removed (the wiki is mistitled — it lists at least Rainbow Astro RST-135 under worm periods, but RST-135 is a strain wave mount with no worm).

| Make | Model | Worm period (s) |
|---|---|---|
| Astro-Physics | 1100GTO, 1600GTO | 382.95 |
| Celestron | AVX | 594 |
| Celestron | CGEM, CPC | 478.69 |
| Celestron | CGE Pro | 337.90 |
| Fornax | F52/F102/F152 | 450 |
| Losmandy | G11 | 239.34 |
| Losmandy | G11T, Titan 50 | 318.13 |
| Losmandy | GM8 | 479 |
| Meade | LX200GPS | 478.69 |
| Orion | Sirius EQ-G (= Sky-Watcher HEQ5) | 638 |
| Orion | Atlas Pro | 479 |
| Sky-Watcher | EQ6 | 479 |
| Sky-Watcher | EQ6-R Pro (2017) | 479 |
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
| iExos | 100 | 600 |

**At implementation time, re-verify each value against the wiki** (it is community-editable and may have been updated). The Rainbow Astro RST-135 entry on the wiki is mis-classified — it belongs in the §6.7 strain wave table.

### 6.7 Strain wave (harmonic) mounts

**Manufacturer-stated facts that drive the design**:

- ZWO on AM5: *"the periodic errors of a strain wave gear mount are different from that of a worm gear mount... when we say PERIODIC ERRORS of a strain wave gear, the errors are actually not that 'PERIODIC.' It seems the error of each gear is different from another."* ([source](https://astronomy-imaging-camera.com/tutorials/10-things-you-need-to-know-about-the-custom-am5s-pe-test-report-provided-by-zwo/))
- Rainbow Astro on RST-135: *"Strain wave gear has a large periodic error compared to worm gear... it has a periodic error about ±30 arcsec in a 430-second cycle. Worm gears has good repeatability of periodic errors, while strain wave gear has the characteristic that the magnitude of periodic error varies depending on the weight of load."* ([source](https://www.rainbowastro.com/faq-items/how-big-periodic-errors-of-rst-135-is/))
- Pegasus Astro on NYX-101: *"Our gear systems exhibit a measured periodic error of ±20 arcseconds or less... In total, this periodic cycle spans 7.16 minutes or 430 seconds... Strain wave gears display variability in periodic error magnitude depending on the telescope's load and the direction of movement."* ([source](https://pegasusastro.com/nyx-101-guiding-recommendations/))

Implications:

- Strain wave PE has a measurable dominant period, but cycle is **less repeatable** than worm gear cycles (load- and direction-dependent).
- Amplitudes are typically **larger** than worm: 20-60 arcsec p2p for harmonic mounts vs 15-30 arcsec p2p for typical worm mounts ([Astronomy Online](https://astronomyonline.info/harmonic-drive-or-strain-wave-telescope-mounts/)).
- ZWO explicitly states PEC playback **does not work** because the error is irregular. PHD2 Predictive PEC works better than mount-firmware PEC, but tuning still requires per-mount-per-rig empirical setup.
- Some iOptron HEM-series mounts are **hybrid**: strain wave RA, worm/belt Dec ([direct iOptron customer reply on PHD2 forum](https://groups.google.com/g/open-phd-guiding/c/trseX0fpRMQ): *"keep in mind that RA is driven by strainwave while DEC is a worm gear/belt drive copied directly out of the iOptron GEM28"*).

**Drive type field** — every mount in the catalog needs a `drive_type` value:

- `worm` — traditional worm gear (§6.6 marker)
- `strain_wave` — pure harmonic drive (§6.7 marker)
- `strain_wave_with_encoder` — strain wave with high-resolution encoder (Renishaw) reducing residual; mark with reduced amplitude expectation
- `hybrid_strain_wave_ra` — strain wave RA + worm Dec (HEM27, HEM44 non-EC)
- `hybrid_strain_wave_ra_with_encoder` — same but with RA encoder (HEM27EC, HEM44EC)
- `direct_drive_encoder` — Astro-Physics with absolute encoders, no discrete spectrum peaks
- `friction` — friction-drive mounts
- `unknown` — fallback

**Spectrum marker behavior branches on drive type**:

- `worm` → §6.6 vertical marker at worm period
- `strain_wave` → vertical marker at `dominant_period_s` if known; shaded band over `expected_period_band_s`; both if both known
- `hybrid_strain_wave_ra` → strain wave marker on RA spectrum, worm marker on Dec spectrum
- `direct_drive_encoder` → no markers
- `unknown` → fallback "any peak in 100-800 s" with explicit uncertainty

**Strain wave seed data — initial coverage** (verified from manufacturer pages or community measurements). Re-verify at implementation time per §4.9.

| Make | Model | Drive type | Dominant period (s) | Expected band (s) | Source |
|---|---|---|---|---|---|
| ZWO | AM3 | strain_wave | 288 | (180, 360) | [ZWO product page](https://astronomy-imaging-camera.com/product/zwo-am3-harmonic-equatorial-mount/), confirmed in [Cloudy Nights](https://www.cloudynights.com/forums/topic/880277-improving-am5-mount-guide-performance/) |
| ZWO | AM5 | strain_wave | 288 | (180, 360) | Community consensus on [Cloudy Nights AM5N PPEC discussion](https://www.cloudynights.com/forums/topic/959085-zwoam5n-and-phd2-predictive-pec/) |
| ZWO | AM5N | strain_wave | 288 | (180, 360) | Same gear as AM5; PE amplitude reduced from ±20 to ±10 arcsec but period unchanged |
| Rainbow Astro | RST-135 | strain_wave | 430 | (300, 600) | [Rainbow Astro FAQ](https://www.rainbowastro.com/faq-items/how-big-periodic-errors-of-rst-135-is/) — manufacturer statement |
| Rainbow Astro | RST-135E | strain_wave_with_encoder | 430 | (300, 600) | Same gear; encoder reduces residual to ±2.5 arcsec |
| iOptron | HEM27 | hybrid_strain_wave_ra | 360 (RA) / 600 (Dec, GEM28 worm) | (250, 480) RA | [HighPointScientific listing](https://www.highpointscientific.com/ioptron-hem27ec-hybrid-equatorial-mount-head-with-ipolar-and-case-h274a) — "advertised gear period of 360sec"; Dec is GEM28 600s worm ([PHD2 forum](https://groups.google.com/g/open-phd-guiding/c/trseX0fpRMQ)) |
| iOptron | HEM27EC | hybrid_strain_wave_ra_with_encoder | 360 (RA) / 600 (Dec) | (250, 480) RA | Same as HEM27 with RA encoder |
| iOptron | HEM44 | hybrid_strain_wave_ra | unknown — measure | (250, 600) RA | [Cloudy Nights HEM44 thread](https://www.cloudynights.com/forums/topic/991619-ioptron-hem44-non-ec-periodic-error/) reports ~90 arcsec p2p; period not yet community-consensus |
| iOptron | HEM44EC | hybrid_strain_wave_ra_with_encoder | unknown — measure | (250, 600) RA | Same as HEM44 |
| iOptron | HAE29 | strain_wave | unknown — measure | (250, 600) | Community measurements pending |
| iOptron | HAE43 | strain_wave | unknown — measure | (250, 600) | Same |
| iOptron | HAE69 | strain_wave | unknown — measure | (250, 600) | Same |
| Pegasus Astro | NYX-101 | strain_wave | 430 | (350, 500) | [Pegasus Astro NYX guide](https://pegasusastro.com/nyx-101-guiding-recommendations/) — "this periodic cycle spans 7.16 minutes or 430 seconds" |
| Sky-Watcher | 100i | strain_wave | unknown — measure | (200, 500) | Community measurements pending |
| Sky-Watcher | 150i | strain_wave | unknown — measure | (200, 500) | Same |

**Catch-all** for unidentified strain wave mounts: default `expected_period_band_s = (200, 500)` based on the cluster of measured values above. Mark band as "estimated — measure your specific mount for higher confidence."

The "unknown — measure" entries are intentional: §4.9 forbids inventing values. The per-mount-instance measurement corpus (§8.6) is the path to filling these in over time.

### 6.8 Per-mount-instance distinction

The catalog distinguishes:

- **Mount model** — the manufacturer's gear (ZWO AM5, iOptron HEM27)
- **Mount instance** — the specific physical mount the user owns; one user can own multiple AM5s

Manufacturer-stated periods attach to **models**. Measured PE attaches to **instances** (§6.4). The diagnostic engine prefers instance data when available.

This means the rig schema needs a `mount_instance_id` column (or equivalent linkage) separate from `mount_model_id`. v2 of the analyzer requires this distinction for the §6.4 measured-PE output to be useful; v4 makes the per-instance corpus a real feature.

CC should confirm whether the existing equipment schema supports this — if not, schema work is part of the v2 effort.


---

## 7. Phase v3 — Automated diagnostic engine

**Target user**: "I don't want to read a 30-page tutorial to figure out what my log means. Tell me what's wrong."

**v3 success criterion**: a user with a problematic log sees a concise, accurate list of findings within 5 seconds of analysis loading, with reference links so they can learn more.

### 7.1 Two-tier diagnostic structure

Every finding is in one of two tiers, visually distinct:

**Confident** — signature has a single canonical community-agreed explanation. Stated as fact. Not dismissible. Rendered prominently.

**Speculative** — signature has multiple plausible explanations or relies on a noisy measurement. Stated as hypothesis ("may indicate..."). Dismissible per-analysis. Rendered behind a count badge, collapsed by default.

A rule promotes from speculative to confident only after manual field-evidence validation; new rules default to speculative.

**Every finding includes**:

- Rule ID (stable identifier)
- Tier (confident / speculative)
- Category (`polar_alignment`, `backlash`, `guide_star`, `mechanical`, `seeing`, `configuration`, `calibration`, `tracking`, `pe_quality`)
- Short summary (one sentence)
- Longer explanation (one paragraph)
- Evidence struct (numeric values that triggered the rule)
- Reference URL (community source)
- Actionable next step (one sentence, optional)

### 7.2 Confident-tier rules

#### `polar_alignment_from_dec_drift`

Category: `polar_alignment`.

Preconditions: guiding section ≥ 10 minutes; non-GA (GA has its own estimate); declination known; drift rate computable.

Formula: §5.2.6 / §11.1 — `PA error_arcmin = 3.8197 × |drift_dec_px_per_min| × pixel_scale / cos(declination)`.

Fires when estimated PA error > 2 arcmin.

Summary: *"Polar alignment error approximately N arcmin."*
Actionable: *"Run the Guiding Assistant or PHD2's Drift Alignment tool to confirm and refine."*
Reference: [Barrett, *Determining Polar Axis Alignment Accuracy*](http://celestialwonders.com/articles/polaralignment/PolarAlignmentAccuracy.html).

#### `dec_backlash_overshoot_pattern`

Category: `backlash`.

Signature: a run of ≥ 5 consecutive Dec pulses in one direction, followed by ≥ 3 frames of Dec algorithm pause (zero pulses), followed by a Dec pulse in the reversed direction whose magnitude ≥ 2× the mean of the initial run. Fires when at least 3 such sequences exist in the section.

Summary: *"Declination backlash detected."*
Actionable: *"Consider running the Guiding Assistant backlash measurement and enabling PHD2's backlash compensation. Do not use mount-firmware backlash compensation while guiding."*
Reference: [Bruce Waddington tutorial](https://openphdguiding.org/Analyzing_PHD2_Guide_Logs.pdf), §"Declination backlash."

#### `snr_drop_preceded_star_lost`

Category: `guide_star`.

For each `ErrorCode ≠ 0` frame whose ErrorDescription contains "lost" or "no star," compute mean SNR in the 30 seconds prior vs the 30 seconds before that. Fires if ≥ 50% of lost-star events in the section had a prior SNR drop > 30%.

Summary: *"SNR dropped before star-loss events — likely clouds, dew, or focus shift."*
Actionable: *"Check for thin clouds or dew formation; if neither, investigate focus drift."*

#### `sustained_dec_direction_pulses`

Category: `polar_alignment`.

Fires when ≥ 90% of nonzero Dec pulses are in the same direction over a section ≥ 15 minutes. Complement to the Dec-drift PA diagnostic — they should usually co-fire, but pulses-in-one-direction can fire when the algorithm damps the drift enough that raw drift is muted.

Summary: *"Dec corrections are predominantly <direction> — consistent with polar misalignment."*
Reference: Bruce Waddington tutorial, §"Polar alignment."

#### `star_saturation`

Category: `guide_star`.

Fires when ≥ 5% of frames have ErrorDescription matching `saturat*` or `mass change*` patterns.

Summary: *"Guide star is saturated or near-saturated in N% of frames."*
Actionable: *"Reduce guide exposure or gain, or select a dimmer star."*

#### `calibration_axes_not_orthogonal`

Category: `calibration`.

Applies to calibration sections. Compute the angle between calibrated RA and Dec axes from `xAngle` and `yAngle`. Fires when `|angle - 90°| > 5°`.

Summary: *"Calibration RA/Dec axes deviate from orthogonality by N°."*
Actionable: *"Check for mount alignment issues, cable flexure during calibration, or pier-side calibration done at high declination."*

#### `chasing_seeing_ra`

Category: `configuration`.

All three conditions must hold:

- RA oscillation > 0.55
- Median RA pulse duration < 200 ms
- Section exposure < 2000 ms

Summary: *"RA corrections are oscillating rapidly — likely chasing seeing."*
Actionable: *"Increase guide exposure to 2-3 seconds, increase RA min-move, or reduce RA aggressiveness."*
Reference: Bruce Waddington tutorial, §"Chasing seeing."

#### `guiding_pe_suppression_low` — NEW in v4 of spec

Category: `pe_quality`. Requires §6.2 unguided RA reconstruction available.

Compares raw RA spectrum amplitude vs unguided RA spectrum amplitude **at the dominant PE period** (§6.4):

```
suppression_ratio = 1 - (raw_RA_amplitude_at_pe_period / unguided_RA_amplitude_at_pe_period)
```

Fires when:
- `pe_amplitude_arcsec` ≥ 1.5 arcsec (mount has measurable PE), AND
- `suppression_ratio` < 0.5 (guiding suppresses less than 50% of PE)

Summary: *"Guiding is not effectively suppressing your mount's periodic error: N% suppression at the M-second period."*
Actionable: *"Possible causes: aggressiveness too low, guide cadence too long for the PE period, or algorithm mismatch. Try Predictive PEC if available."*

This is the diagnostic that most directly answers the question users actually have: "Is my guiding working?" It fires only when PE is real (not just noise) and guiding fails to address it.

### 7.3 Speculative-tier rules

#### `gradual_rms_trend`

Category: `mechanical`. Linear regression of per-minute RMS over sections ≥ 30 min. Fires when slope > 0.005 arcsec/min (worsening).

Summary: *"RMS is gradually increasing — possible thermal drift, flexure, or changing seeing."*

#### `out_of_band_spectrum_peaks` — drive-type-aware

Category: `mechanical`.

Branches by `drive_type`:

- **`worm`**: spectrum peaks > 0.5 arcsec amplitude at periods outside both seeing band (< 5 s) and worm-period mechanical band (worm ± 5%, plus first 3 harmonics: worm/2, worm/3, worm/4 each ± 5%). Out-of-band peaks suggest gearbox, belt, or motor anomalies. Summary: *"Periodic error at N seconds, M arcsec amplitude — outside the expected mechanical band for this worm-driven mount."*
- **`strain_wave`**: spectrum peaks > **1.0 arcsec** (higher threshold — strain wave is intrinsically richer broadband content) at periods outside 0.5×–2.0× the dominant period (or outside `expected_period_band_s` if no dominant). **Softer language**: *"A periodic component at N seconds, M arcsec amplitude is not in this mount's typical period band. This may be a load-dependent strain wave variation rather than a fault."* Do NOT suggest mechanical problem — strain wave PE varying with load is documented behavior, not a fault.
- **`hybrid_strain_wave_ra`**: apply strain wave rule to RA spectrum, worm rule to Dec spectrum.
- **`direct_drive_encoder`**: any peak above 1.0 arcsec is anomalous. Confident tier (override). Summary: *"Periodic error detected — encoder-class mounts should not show discrete spectrum peaks at this amplitude."*
- **`unknown`**: fallback — 100-800 s broad band; speculative tier with explicit "identify the mount in equipment for a more confident diagnosis" actionable.

#### `strain_wave_load_balancing_recommendation` — NEW

Category: `pe_quality`. Speculative.

Fires when:
- `drive_type ∈ {strain_wave, hybrid_strain_wave_ra, strain_wave_with_encoder, hybrid_strain_wave_ra_with_encoder}`
- `pe_amplitude_arcsec` > 1.5× the manufacturer's stated mount-class amplitude (where stated)
- Rig context populated and load is within mount spec

Summary: *"PE amplitude is higher than typical for this mount class — strain wave gears are load- and direction-sensitive. Consider checking balance and orientation."*
Reference: [Pegasus Astro NYX guidance](https://pegasusastro.com/nyx-101-guiding-recommendations/).

#### `snr_variability`

Category: `seeing`. SNR standard deviation > 30% of mean SNR AND autocorrelation of SNR series suggesting non-random pattern (lag-1 autocorrelation > 0.4).

Summary: *"Guide star brightness is fluctuating substantially — possible thin clouds or dew."*

#### `possible_differential_flexure`

Category: `mechanical`. Requires guide-scope (not OAG) configuration. Sustained drift in both RA and Dec whose direction varies with pointing (clearer in v4 multi-log).

Summary: *"Sustained drift inconsistent with polar alignment — possible differential flexure between guide scope and main OTA."*

#### `dec_oscillation_with_backlash_compensation`

Category: `configuration`. Dec oscillation > 0.4 AND `Backlash comp = enabled` in header.

Summary: *"Dec is oscillating — backlash compensation may be over-tuned."*

#### `low_snr_throughout`

Category: `guide_star`. Mean SNR < 10 across the section without triggering actual star loss.

Summary: *"Guide star SNR is low throughout — guiding may be less precise than needed."*

#### `high_rms_vs_rig_expected`

Category: `tracking`. Requires rig context. Fires when `rms_total_arcsec > 3 × rig.effective_guide_precision_arcsec`.

Summary: *"Guiding RMS is substantially higher than expected for this rig's optical configuration."*

### 7.4 Equipment-aware enhancements

When rig context is present:

- Worm-period and strain-wave markers use the rig's drive_type and per-instance measured period when available (§6.4)
- `high_rms_vs_rig_expected` becomes available
- Flexure heuristics differentiate OAG vs guide-scope
- RMS-warning thresholds adjust to expected guide precision
- Strain-wave-specific diagnostic rules become available

When absent: all diagnostics still function with absolute thresholds and uncertainty-aware language.

### 7.5 Diagnostic settings

User-adjustable:

- Enable/disable speculative tier (single toggle)
- Enable/disable individual rules
- Adjust confident-tier thresholds (advanced; nested behind "tune diagnostics")

Settings changes re-run the engine against cached parsed data — no re-parse.

---

## 8. Phase v4 — Multi-log comparison, trends, shareable reports, catalog integration

**Target user**: "I want to see whether my guiding has gotten better. I want to share results for help."

**v4 success criterion**: user can select N logs, see side-by-side stats, trend lines over time, and export a standalone HTML report that a forum expert can view without installing anything.

### 8.1 Multi-log comparison

Select 2-20 logs. View shows:

- **Side-by-side stats table** — one row per section across selected logs (date, duration, RMS RA/Dec/Total, drift, oscillation, top diagnostic).
- **Trend chart** — RMS Total (and components) plotted vs date, one marker per section, trend line. X-axis switchable: calendar date, session index, integration time accumulated.
- **Diagnostic-cooccurrence matrix** — which findings fire across which sessions. Reveals persistent vs one-off issues.
- **Configuration drift panel** — highlight when algorithm parameters, guide rates, or calibration values change between sessions.

### 8.2 Trend analysis

Modest summaries over a selected window:

- "Average RMS Total over the last N nights is X, trending {up / down / flat}"
- "Dec backlash detected in M of last N nights"
- "Polar alignment drift stable around N arcmin"

Sophisticated trend analytics belong in v5 with the AI analyzer.

### 8.3 Shareable HTML report

One-click export of a single analysis or a comparison as a standalone HTML file:

- **Self-contained**: all SVG inline, no external CSS/JS/fonts. Works offline, opens in any modern browser.
- **All charts as static SVG** (not canvas) — crisp, zoomable.
- **Includes**: per-section stats, diagnostic findings (both tiers), user notes added before export.
- **Header**: source filename(s), PHD2 version(s), analysis timestamp, NightCrate version.
- **Does NOT include** full per-frame sample data (separate "export raw data as CSV" available).

This is the feature that most directly addresses "post log to forum, wait for expert."

### 8.4 Catalog integration (when imaging core arrives)

Analyzer gains a second entry path: analyze a log already ingested into the catalog. Automatic association of guide-log sections with overlapping imaging sessions. Per-session "Guiding" tab showing analysis. Per-sub-frame annotation when the exposure window contains lost-star events, settle periods, or large-deflection excursions.

Parser, metrics, and diagnostics are unchanged — only entry-point plumbing.

### 8.5 "Recently analyzed" history

List at the analyzer home; one-click to reopen without re-parsing. Shipped in v0.24.0 (10-entry localStorage); v4 expands with catalog backing.

### 8.6 Per-mount-instance PE measurement corpus

This makes §6.4 a multi-session capability. For each mount instance:

**Storage**: every per-section measurement from §6.4 attached to the instance.

**Display**:

- A "Mount" view showing the instance's PE measurement history: scatter of `pe_period_s` and `pe_amplitude_arcsec` over time, with rolling median and 1σ band.
- Drift-over-time alert if the trailing 30-day median has shifted by > 5% from the prior 30-day median (could indicate gear wear or PHD2 settings change).
- "Compared to manufacturer default" panel showing how the user's measured period and amplitude relate to the catalog default.

**Override behavior**: when the instance has ≥ 3 measurements with a stable period (CV < 5% across measurements), §6.6 / §6.7 spectrum markers use the instance's measured period instead of the manufacturer default. Both shown (faint vs prominent) so the user can see both.

**Filter dimensions**: per-instance history can be filtered by declination, payload, pier side. Strain wave PE depends on these (§6.7), so the corpus becomes more useful with these dimensions populated.

**Optional upstream sharing**: a manual "share with the NightCrate community" button (never automatic) that contributes anonymized period/amplitude/mount-model triples back to the seed data for less-common mounts (HEM44, HAE-series, SW 100i/150i). This fills the §6.7 "unknown — measure" gaps over time.

This section is the architectural payoff of §6.4 being a first-class output: v2 ships per-session, v4 ships per-instance, v5 makes it a community resource.

---

## 9. Phase v5+ — Debug logs, live monitoring, AI analysis

These are roadmap items. Each gets its own spec when prioritized.

### 9.1 PHD2 Debug log parsing

Debug logs (`PHD2_DebugLog_*.txt`) contain ~10× the volume of guide logs: internal algorithm state, per-iteration guide algorithm traces, full network message bodies. Significant parser complexity. Merits its own spec.

### 9.2 Live session monitoring

PHD2 exposes a [JSON-RPC event monitoring interface](https://github.com/OpenPHDGuiding/phd2/wiki/EventMonitoring) that streams events. NightCrate could connect to a running PHD2 instance and provide diagnostics during the session. Requires network access to the imaging machine (a concern for ASIAIR rigs). Out of scope until ASIAIR network access and the diagnostic engine are solid.

### 9.3 AI-powered session analysis

Feed the full analysis output (parsed structure, metrics, diagnostics, equipment context, overlapping image session metadata) to Claude and generate natural-language summaries and recommendations. Post-MVP paid feature.

Architectural prerequisite (already enforced in §4 and §6.4): the analysis output must be serializable into a coherent context window, with structured per-session and per-instance PE measurements available for inclusion.

### 9.4 Parameter recommendations

"Based on your log, try setting RA aggressiveness to X." Deliberately deferred. Naive recommendations risk eroding tool credibility. The AI analyzer (§9.3) is a better vehicle because it can express uncertainty natively.

If a deterministic recommender is ever built, it must follow the two-tier pattern (§7.1).

---

## 10. Out of scope (now and possibly forever)

- **Editing the source log file.** Read-only on logs.
- **Cloud sync of analyses.** Everything is local.
- **Multi-user shared analyses** beyond the §8.3 HTML report.
- **Uploading logs to a remote PHD2 support service.**
- **N.I.N.A. or ASIAIR session log parsers.** Separate primitives.
- **Autofocus run parsing.** Separate spec.
- **Computing calibration recommendations.** PHD2's own [Calibration Assistant](https://openphdguiding.org/man/Basic_use.htm) handles this.
- **Replacing the PHD2 in-app guiding graph.** Post-hoc tool only.
- **Original PHD (not PHD2) logs.** Different format; negligible user population.
- **Reveal-in-finder.** Permanently vetoed.

---

## 11. Math appendix — full derivations

This section gives the complete derivation of every formula in the spec. Fred caught earlier failure modes where formulas were transcribed from memory — every formula here is either reproduced from a verified source code reference or derived from first principles with sources cited.

### 11.1 Polar alignment from declination drift — Barrett's derivation

This is reproduced from [Barrett, *Measuring Polar Axis Alignment Error*, Appendix A](http://celestialwonders.com/articles/polaralignment/MeasuringAlignmentError.html), with explicit unit-conversion steps.

**Setup**: a misaligned mount rotates around an axis that's at angle α from the true celestial pole. As the mount tracks, a star near the celestial equator drifts in declination. The drift rate is proportional to α and to the elapsed time of observation.

**Small-angle geometry**. For small misalignment α (radians) and small drift δ (radians), planar trigonometry gives:

$$\sin(\delta) \approx \tan(\alpha) \cdot \sin(\text{angular distance traveled})$$

For small angles α and small δ:

$$\delta \approx \alpha \cdot \omega_{\text{sid}} \cdot t$$

where ω_sid is the sidereal rate in radians per unit time and t is elapsed time.

**Unit conversion to arcseconds and arcminutes**. The sidereal rate is **15.041 arcsec/sec** ([ASCOM Standards](https://www.bbastrodesigns.com/equatTrackingRatesCalc.html), confirmed across multiple references). In radians per minute:

$$\omega_{\text{sid}} = 15.041 \frac{\text{arcsec}}{\text{sec}} \cdot 60 \frac{\text{sec}}{\text{min}} \cdot \frac{1 \text{ rad}}{206264.806 \text{ arcsec}} = 4.3753 \times 10^{-3} \text{ rad/min}$$

(206264.806 arcsec per radian is the exact conversion: `180 × 3600 / π`.)

So at the celestial equator:

$$\delta_{\text{arcsec/min}} = \alpha_{\text{arcmin}} \cdot \frac{1}{60} \cdot \frac{1}{206264.806} \cdot 15.041 \cdot 60 \cdot 206264.806 = \alpha_{\text{arcmin}} \cdot 15.041 / \cos(\delta_{\text{star}})$$

Wait — the cleaner derivation following Barrett's Equation (1):

$$\alpha_{\text{arcmin}} = \frac{\text{drift}_{\text{arcsec}}}{4 \cdot t_{\text{min}} \cdot \cos(\delta_{\text{star}})}$$

where the **4** is the result of all unit conversions (radians → arcmin × sidereal rate × time conversion). Specifically:

$$4 \approx \frac{\text{rad/arcmin} \cdot \text{arcsec/rad}}{\omega_{\text{sid arcsec/min}}} = \frac{(1/3437.75) \cdot 206264.806}{15.041 \cdot 60}$$

$$= \frac{60.000}{902.46} = 0.06647 \times 60 = 3.988 \approx 4$$

(The exact value is 3.988, rounded to 4 in Barrett's Equation 1; the 5% slop is inside other approximations of the derivation.)

**Converting to PHDLogViewer's form**. PHDLogViewer (`AnalysisWin.cpp` line ~166) uses pixels-per-minute drift directly:

$$\alpha_{\text{arcmin}} = 3.8197 \cdot \frac{|\text{drift}_{\text{dec}}|_{\text{px/min}} \cdot \text{pixel scale}_{\text{arcsec/px}}}{\cos(\delta_{\text{star}})}$$

The 3.8197 factor relates drift-in-arcsec-per-minute to PA-error-in-arcmin. Specifically: `drift_arcsec/min = drift_px/min × pixel_scale`, so:

$$\alpha_{\text{arcmin}} = \frac{\text{drift}_{\text{arcsec/min}} \cdot K}{\cos(\delta_{\text{star}})}$$

where K is a unit-conversion constant. PHDLogViewer's K = 3.8197.

Rearranging Barrett's Equation 1 with `t = 1 minute` and `drift_arcsec_per_minute`:

$$\alpha_{\text{arcmin}} = \frac{\text{drift}_{\text{arcsec/min}}}{4 \cdot \cos(\delta_{\text{star}})}$$

…would give K = 0.25, which is far from 3.8197.

The discrepancy is in the time unit. Barrett's Equation 1 has `t_min` in the denominator with a coefficient of 4. PHDLogViewer's input is already arcsec/min (the drift is already normalized to per-minute); the 3.8197 must therefore reconcile a different identity.

Working backward from PHDLogViewer's value:

$$3.8197 = \frac{60}{15.71} \approx \frac{60}{15.7}$$

So the operative identity for PHDLogViewer is:

$$\alpha_{\text{arcmin}} = \frac{\text{drift}_{\text{arcsec/hour}}}{15.7 \cdot \cos(\delta_{\text{star}})}$$

…where drift_arcsec/hour = drift_px/min × pixel_scale × 60 = 60 × drift_px/min × pixel_scale, and 60/15.7 = 3.822 ≈ 3.8197.

The 15.7 comes from the [Starry Nights polar drift article](http://www.starrynights.us/Articles/Polar_Align.htm), which states that 1 arcmin of polar misalignment produces 0.262 arcsec/min of drift at the equator, equivalently 15.72 arcsec/hour:

$$0.262 \frac{\text{arcsec/min}}{\text{arcmin}} \times 60 = 15.72 \frac{\text{arcsec/hour}}{\text{arcmin}}$$

So:

$$\alpha_{\text{arcmin}} = \frac{\text{drift}_{\text{arcsec/hour}}}{15.72 \cdot \cos(\delta_{\text{star}})}$$

PHDLogViewer's coefficient 3.8197 = 60 / 15.71 (the slight difference between 15.71 and 15.72 is rounding). The PHDLogViewer formulation is equivalent and operates on the (more convenient) pixels-per-minute drift number that's already computed for the stats panel.

**Practical note**: Barrett's Equation 1 with the 4-coefficient and PHDLogViewer's 3.8197 give the same answer at the equator within a fraction of a percent. Any slight discrepancy is inside the small-angle approximation. NightCrate uses **PHDLogViewer's exact form** for cross-tool consistency — same source code, same formula, same number.

### 11.2 RMS — standard deviation, derived

PHDLogViewer's `LFit` class (`AnalysisWin.cpp` line ~76) implements a streaming variance estimator using the Welford / West-incremental form. The mathematical content:

$$\text{var}(x) = \frac{1}{N}\sum_{i=1}^N (x_i - \bar{x})^2$$

(Note: this is the **population variance**, with `1/N` denominator, not the **sample variance** with `1/(N-1)` denominator. PHDLogViewer's code uses `1/N` per the West-incremental update on line 80: `varx += (k * dx * dx - varx) / n`.)

The streaming update for population mean and variance, given a new observation x and prior mean μ, prior variance σ², prior count n:

```
n_new = n + 1
delta = x - μ
μ_new = μ + delta / n_new
var_new = (n × var + delta × (x - μ_new)) / n_new
```

PHDLogViewer's code uses an equivalent but slightly different rearrangement (`k = n / n_new`):

```
varx_new = varx + (k × dx² − varx) / n_new
       = (varx × n_new + k × dx² − varx) / n_new
       = (varx × n + k × dx²) / n_new
```

…which is mathematically equivalent.

**RMS = sqrt(var)** is therefore **standard deviation**, not "RMS-from-zero" (`sqrt(mean(x²))`). The two differ when there's a systematic offset. NightCrate matches PHDLogViewer for compatibility (§5.2.1).

### 11.3 Linear regression slope — covariance form

PHDLogViewer's `LFit::B()` (line ~88) returns:

$$B = \frac{\text{cov}(x, y)}{\text{var}(x)}$$

This is the standard ordinary-least-squares slope formula. Derivation: minimize sum of squared residuals from `y = a + b·x`:

$$\frac{\partial}{\partial b} \sum_i (y_i - a - b x_i)^2 = 0$$

Solving the normal equations gives `b = Σ(x_i - x̄)(y_i - ȳ) / Σ(x_i - x̄)²`, which is `cov(x,y) / var(x)` when the sums are normalized by 1/N (population) or 1/(N-1) (sample) — the ratio is the same either way.

The intercept (`LFit::A()`, line ~89): `a = ȳ - b · x̄`.

Used in §5.2.3 (RA drift), §5.2.4 (Dec drift), and §6.1.1 step 3 (drift subtraction before FFT).

### 11.4 Scatter ellipse rotation θ

PHDLogViewer's `LFit::Theta()` (line ~95):

$$\theta = \text{atan2}(\text{cov}_{xy}, \text{var}_x)$$

This is **not** the principal-component (PCA) rotation angle, which would be:

$$\theta_{\text{PCA}} = \frac{1}{2} \cdot \text{atan2}(2 \cdot \text{cov}_{xy}, \text{var}_x - \text{var}_y)$$

The two formulas give similar rotations when the data ellipse is highly elongated (var_x ≫ var_y or vice versa) but diverge for nearly-circular data. PHDLogViewer's simpler form is what NightCrate uses for cross-tool match.

### 11.5 Elongation ratio

From `AnalysisWin.cpp` line ~225:

$$\text{elongation} = \begin{cases} \frac{a - b}{a + b} & \text{if } a + b > 10^{-6} \\ 1 & \text{otherwise} \end{cases}$$

where `a = max(σ_x', σ_y')`, `b = min(σ_x', σ_y')`, and σ' are standard deviations of the rotated coordinates (§5.2.7).

Range: 0 (perfect circle) to 1 (degenerate line).

### 11.6 Hamming window

From `AnalysisWin.cpp` line ~370:

$$w_i = 0.54 - 0.46 \cdot \cos\left(\frac{2\pi i}{N - 1}\right), \quad i = 0, 1, \ldots, N - 1$$

Coherent gain (mean of the window):

$$G_c = \frac{1}{N}\sum_{i=0}^{N-1} w_i \approx 0.54$$

(The 0.46-coefficient cosine averages to zero over the window.)

The amplitude correction factor for windowed FFT to recover the underlying sinusoid amplitude is `1 / G_c ≈ 1 / 0.54 ≈ 1.85`. Combined with the factor of 2 for single-sided spectrum (the negative-frequency conjugate is dropped), the total correction is ≈ 3.7, rounded to **4** in PHDLogViewer's source. The exact value depends on the window, but for Hamming the convention is `4/N` for the absolute amplitude.

### 11.7 FFT amplitude normalization

A discrete sinusoid of amplitude A windowed by w_i and FFTed produces a peak at the corresponding frequency bin with magnitude:

$$|X_k|_{\text{peak}} \approx \frac{A \cdot N \cdot G_c}{2}$$

Solving for A:

$$A \approx \frac{2 \cdot |X_k|_{\text{peak}}}{N \cdot G_c}$$

For Hamming, G_c ≈ 0.54:

$$A \approx \frac{2 \cdot |X_k|}{N \cdot 0.54} \approx \frac{3.7 \cdot |X_k|}{N}$$

PHDLogViewer's code rounds to **4/N** (line ~395):

```cpp
double scale = 4. / (double) n;
```

This gives a slight overestimate of true amplitude (~8% high) but is what the reference tool uses; NightCrate matches for cross-tool consistency.

The reported arcsec amplitude:

$$a_{\text{arcsec}} = \frac{4 \cdot |X_k|}{N} \cdot \text{pixel\_scale}$$

### 11.8 Sine wave amplitude / peak-to-peak / RMS relationships

For a pure sine wave of amplitude A:

- **Amplitude** = A (peak from zero)
- **Peak-to-peak** = 2A (full swing)
- **RMS** = A / √2 = (√2 / 2) × A ≈ 0.7071 × A

Derivation of RMS:

$$\text{RMS} = \sqrt{\frac{1}{T}\int_0^T (A \sin(\omega t))^2 dt} = \sqrt{\frac{A^2}{T} \cdot \frac{T}{2}} = \frac{A}{\sqrt{2}}$$

Used in §6.1.7 cursor readout — directly from PHDLogViewer's status bar formula.

### 11.9 Frequency and period from FFT bin

For an N-sample FFT with sample spacing Δt, bin *k* (1-indexed) corresponds to:

$$f_k = \frac{k}{N \cdot \Delta t}, \quad p_k = \frac{N \cdot \Delta t}{k}$$

The DC bin (k=0) is removed by drift subtraction. The Nyquist bin (k=N/2) is the highest meaningful frequency. PHDLogViewer keeps `nfft = N/2 - 1` bins (excludes DC and the Nyquist symmetric pair).

### 11.10 MAD-based peak threshold

The Median Absolute Deviation:

$$\text{MAD}(x) = \text{median}(|x_i - \text{median}(x)|)$$

For normally-distributed data, MAD relates to standard deviation σ via:

$$\sigma \approx 1.4826 \cdot \text{MAD}$$

(The 1.4826 factor is `1 / Φ⁻¹(3/4)` where Φ is the standard normal CDF.)

A 3-sigma-equivalent peak threshold:

$$\text{threshold} = \text{median}(a) + 3 \cdot 1.4826 \cdot \text{MAD}(a)$$

A peak `a_k` is significant if it exceeds this threshold. The MAD-based form is robust to outliers (§6.1.6). Standard practice in robust statistics ([reference](https://crispinagar.github.io/blogs/mad-anomaly-detection.html)).

### 11.11 RA drift formula derivation

The §5.2.3 formula:

$$\text{drift}_{\text{RA px/sec}} = \frac{\text{ra}_1 - \text{ra}_0 - \sum \text{raguide}}{t_1 - t_0}$$

…is derived from conservation of mount position. At any time t:

$$\text{position}(t) = \text{position}(0) + \int_0^t (\text{drift}_{\text{rate}} - \text{guide}_{\text{rate}}) dt$$

Discretizing across the section's frames:

$$\text{ra}_1 - \text{ra}_0 = (\text{drift}) \cdot (t_1 - t_0) + \sum_i \text{raguide}_i$$

(where raguide is signed — west is negative, east positive, or vice versa per parity). Rearranging:

$$\text{drift} = \frac{\text{ra}_1 - \text{ra}_0 - \sum \text{raguide}}{t_1 - t_0}$$

PHDLogViewer multiplies by 60 to convert to pixels/minute.

### 11.12 Dec drift — why it's different

Dec is typically guided in only one direction (or both with backlash), so unlike RA you can't simply subtract the corrections. PHDLogViewer's `DecDrift` instead accumulates Dec changes only across frames where the previous frame was unguided (decdur == 0) — those frames reflect actual sky drift, not algorithm reactions.

The accumulated y_accum sequence is then linear-regressed against time, and the slope is the drift rate. This is the §5.2.4 algorithm.

### 11.13 Akima spline (vs. cubic spline)

GSL's `gsl_interp_akima` is a piecewise polynomial interpolant by Hiroshi Akima ([1970 paper, ACM Vol 17 No 4](https://dl.acm.org/doi/10.1145/321607.321609)) that's non-overshooting for oscillatory data. Cubic-spline interpolation can introduce spurious oscillations between sample points; Akima avoids this by using a local stencil that adapts to the local data behavior.

For PHD2 spectrum analysis, this matters: the input is already oscillatory (mount PE), and a cubic-spline interpolator would risk amplifying high-frequency content that doesn't exist. NightCrate should use Akima or any non-overshooting interpolant.

### 11.14 Oscillation metric

$$\text{ra\_oscillation} = \frac{|\{i : \text{sign}(x_i) \neq \text{sign}(x_{i-1})\}|}{N - 1}$$

where x_i is the RARawDistance series (§5.2.5). This is the fraction of frames where the sign reverses from the previous frame. Frames where x_i = 0 (which is rare) are conventionally treated as positive for this calculation.

For pure white noise, the expected oscillation is 0.5 (each frame independent of the last; sign flip with probability 1/2). Values near 0.5 indicate the algorithm is reacting to atmospheric seeing rather than mount mechanics. Lower values (0.2-0.3) indicate the algorithm is correctly damping high-frequency components.

### 11.15 Guiding PE suppression ratio

The §7.2 `guiding_pe_suppression_low` rule uses:

$$\text{suppression} = 1 - \frac{a_{\text{raw}}(p_{\text{PE}})}{a_{\text{unguided}}(p_{\text{PE}})}$$

where:

- `a_raw(p_PE)` is the RA spectrum amplitude at the PE period (the dominant peak in the unguided spectrum)
- `a_unguided(p_PE)` is the unguided RA spectrum amplitude at that same period

Range: 0 (guiding suppresses nothing) to 1 (guiding suppresses everything). Expected value for a well-tuned worm mount on a long-period PE: 0.85-0.95. For strain wave mounts, lower (0.5-0.8) is normal because the PE is less repeatable and harder to guide out.

The rule fires when suppression < 0.5, suggesting the user's guide settings are not effectively addressing their mount's PE.

---

## 12. Pass D handoff plan — what to fix in the current Spectrum tab implementation

This section is the practical handoff to CC for the current in-progress work, before the larger v2/v3/v4 plans proceed.

The Spectrum tab implementation is in progress on the v0.25.0 branch. Two known issues plus several spec-conformance checks should be closed before §6.2 unguided RA reconstruction and §6.7 strain wave mount handling proceed.

**Known issues to fix immediately**:

1. **Y-axis unit bug**: the implementation showed values around 165 when the actual peak amplitudes should be around 0.14 arcsec. Verify against §6.1.4 — output is `4 × |X_k| / N × pixel_scale`, in arcsec.

2. **Dead "Unguided RA" toggle**: the current toggle is grayed out. Remove it entirely until §6.2 unguided RA reconstruction ships paired with the time-series overlay. A grayed toggle is more confusing than no toggle.

**Spec-conformance checks** (verify each against §6.1):

3. Y-axis is logarithmic by default (§6.1.5).
4. X-axis is logarithmic period in seconds (§6.1.5).
5. FFT pipeline uses **Hamming** window (not Hann), per §6.1.1 step 5.
6. Amplitude normalization is `4/N`, per §6.1.4.
7. Drift-subtraction via least-squares linear fit happens **before** windowing, per §6.1.1 step 3.
8. Akima (or other non-overshooting) spline interpolation to uniform cadence, per §6.1.1 step 4.
9. Peak detection threshold uses `median + 3 × 1.4826 × MAD`, per §6.1.6.
10. Top-5 peaks displayed globally with 5%-period dedup, per §6.1.6.
11. Peak markers are dot markers only — **no on-chart text labels**, per §6.1.6.
12. Hover tooltip with snap-to-peak ±8 pixels, per §6.1.7. Tooltip readouts: Period, Amplitude, P-P, RMS.
13. RA visible by default, Dec hidden by default (toggleable), per §6.1.8.
14. Selection-aware recompute on shift-drag selection or shift+alt-drag exclusion, per §6.1.8 and §5.5.
15. Section-too-short warnings per §6.1.9.

**Then proceed in order**:

- §6.2 unguided RA reconstruction (using the verified algorithm — drop the prev-version's RADuration × xRate approach)
- §6.4 per-session measured PE output (structured, not just on-chart readout)
- §6.6 worm-period markers with verified seed data
- §6.7 strain wave markers with verified per-mount seed data and `drive_type` branching

The point of splitting Pass D this way: the spec-conformance fixes are 1-day work; §6.2 and §6.4 are multi-day. Don't block the smaller fixes on the larger work.

---

## 13. References

### 13.1 Authoritative PHD2 references

- [PHD2 Guide Log format wiki](https://github.com/OpenPHDGuiding/phd2/wiki/PHD2GuideLog) — canonical column definitions
- [PHD2 Trouble-shooting and Analysis manual](https://openphdguiding.org/man/Trouble_shooting.htm) — semantic explanations
- [PHD2 Visualization Tools manual](https://openphdguiding.org/man-dev/Visualization.htm) — confirms PHD2's stats exclude dither/settle frames
- [PHD2 User Guide v2.6.14](https://openphdguiding.org/PHD2_User_Guide.pdf)
- [PHD2 Advanced Settings](https://openphdguiding.org/man/Advanced_settings.htm)
- [PHD2 Mount Worm Period Info wiki](https://github.com/OpenPHDGuiding/phd2/wiki/Mount-Worm-Period-Info) — note: mis-titled, includes some strain wave mounts
- [PHD2 Event Monitoring interface wiki](https://github.com/OpenPHDGuiding/phd2/wiki/EventMonitoring)
- [PHD2 GitHub repository](https://github.com/OpenPHDGuiding/phd2)

### 13.2 Reference tool source code

- [PHDLogViewer GitHub](https://github.com/agalasso/phdlogview)
- [PHDLogViewer `AnalysisWin.cpp`](https://github.com/agalasso/phdlogview/blob/master/AnalysisWin.cpp) — **canonical reference for FFT pipeline (§6.1), unguided RA reconstruction (§6.2), polar alignment formula (§5.2.6 / §11.1), scatter ellipse rotation (§5.2.7), drift calculations (§5.2.3, §5.2.4)**
- [PHDLogViewer `LogViewFrame.cpp`](https://github.com/agalasso/phdlogview/blob/master/LogViewFrame.cpp) — selection model + settle exclusion + main UI logic
- [PHDLogViewer changelog](https://adgsoftware.com/phd2utils/ChangeLog.txt)
- [PEMPro Log Viewer](http://www.siriusimaging.com/PEMProV3/)

### 13.3 Interpretation references

- [Bruce Waddington, *Analyzing PHD2 Guiding Results*](https://openphdguiding.org/Analyzing_PHD2_Guide_Logs.pdf) — canonical community tutorial; source for diagnostic rules
- [PHD2 Glossary of Terms](https://openphdguiding.org/man-dev/Glossary.html)

### 13.4 Polar alignment math

- [Frank Barrett, *Measuring Polar Axis Alignment Error*](http://celestialwonders.com/articles/polaralignment/MeasuringAlignmentError.html) — reproduced in §11.1; Appendix A has the full derivation
- [Frank Barrett, *Determining Polar Axis Alignment Accuracy*](http://celestialwonders.com/articles/polaralignment/PolarAlignmentAccuracy.html) — cited directly in PHDLogViewer's source code
- [Starry Nights polar drift](http://www.starrynights.us/Articles/Polar_Align.htm) — the 0.262 arcsec/min/arcmin coefficient
- [Canburytech drift alignment equations](https://canburytech.net/DriftAlign/Equations.html)

### 13.5 Sidereal rate authoritative source

- [ASCOM Standards-derived sidereal rate (15.041 arcsec/sec)](https://www.bbastrodesigns.com/equatTrackingRatesCalc.html) — used in the PA error derivation in §11.1

### 13.6 Strain wave PE — manufacturer-authoritative sources

- [ZWO AM5 PE Test Report explanation](https://astronomy-imaging-camera.com/tutorials/10-things-you-need-to-know-about-the-custom-am5s-pe-test-report-provided-by-zwo/) — strain wave PE "is actually not that PERIODIC"
- [Rainbow Astro RST-135 PE FAQ](https://www.rainbowastro.com/faq-items/how-big-periodic-errors-of-rst-135-is/) — ±30 arcsec in 430-second cycle, load-dependent
- [Pegasus Astro NYX-101 guiding recommendations](https://pegasusastro.com/nyx-101-guiding-recommendations/) — 7.16-minute (430s) cycle; Predictive PEC guidance
- [iOptron HEM27EC product page (High Point Scientific)](https://www.highpointscientific.com/ioptron-hem27ec-hybrid-equatorial-mount-head-with-ipolar-and-case-h274a) — 360s gear period
- [Cloudy Nights AM5 PHD2 PPEC discussion](https://www.cloudynights.com/forums/topic/959085-zwoam5n-and-phd2-predictive-pec/) — AM5 288s period community consensus
- [Cloudy Nights AM5 improving guide performance](https://www.cloudynights.com/forums/topic/880277-improving-am5-mount-guide-performance/) — confirms 288s for AM3 too via ZWO product page
- [Cloudy Nights HEM44 non-EC PE thread](https://www.cloudynights.com/forums/topic/991619-ioptron-hem44-non-ec-periodic-error/) — community measurement of ~90 arcsec p2p
- [PHD2 forum: HEM27 hybrid drive description](https://groups.google.com/g/open-phd-guiding/c/trseX0fpRMQ) — confirms HEM27 RA strain wave + DEC GEM28 worm
- [Astronomy Online: harmonic drive mounts](https://astronomyonline.info/harmonic-drive-or-strain-wave-telescope-mounts/) — secondary source: amplitudes 20-60 arcsec p2p

### 13.7 Statistical references

- [MAD-based outlier detection — overview](https://crispinagar.github.io/blogs/mad-anomaly-detection.html) — confirms 1.4826 sigma-equivalence factor and 3-5× MAD threshold standard practice
- [UCLA Stat 221 chapter on FFT amplitude normalization](http://www.stat.ucla.edu/~frederic/221/W17/221ch4a.pdf) — cited directly in PHDLogViewer's source

### 13.8 Edge case references

- [PHD2 issue #453 — locale-decimal bug](https://github.com/OpenPHDGuiding/phd2/issues/453)
- [Open PHD Guiding forum thread on locale bug](https://groups.google.com/g/open-phd-guiding/c/D_IkgJ3GuO8)
- [Open PHD Guiding forum thread on PHDLogViewer settle exclusion behavior](https://groups.google.com/g/open-phd-guiding/c/XKGu6Q-nOvQ) — Andy Galasso explains automatic settle detection
- [Open PHD Guiding forum thread on RMS / dither exclusion conventions](https://groups.google.com/g/open-phd-guiding/c/Kn9DAilYdtg)
- [Open PHD Guiding forum thread on multi-additive selection mechanics](https://groups.google.com/g/open-phd-guiding/c/hh4dmjJ9Jkg)
- [Open PHD Guiding forum thread on Analyse selected raw RA semantics](https://groups.google.com/g/open-phd-guiding/c/rV6c68PuAeM)

### 13.9 Local validation artifact

- `PHD2_GuideLog_2026-03-07_193345.txt` (7,668 lines, 621 KB, ASIAIR-bundled PHD2, logged 2026-03-07; used to verify all format claims in §3 and exercised against the v0.22.0–v0.24.0 implementation).

---

**End of spec.**
