# NightCrate PHD2 Guide Log Analyzer — Functional Spec (v2)

This is a **functional** spec. It describes what the analyzer does, what it parses, what it computes, what it surfaces to users, and in what order those capabilities land. It does **not** prescribe code layout, API paths, database schemas, React components, caching mechanisms, module names, or any other implementation decision. Those belong to Claude Code, which has current context on the NightCrate codebase that this document deliberately lacks.

This spec supersedes `nightcrate-phd2-analyzer-spec.md`. Every factual claim about the PHD2 log format has been verified against (a) the [official PHD2 guide log wiki](https://github.com/OpenPHDGuiding/phd2/wiki/PHD2GuideLog), (b) the [PHD2 troubleshooting manual](https://openphdguiding.org/man/Trouble_shooting.htm), and (c) a real ASIAIR-produced PHD2 guide log from Fred's rig (`PHD2_GuideLog_2026-03-07_193345.txt`, 7,668 lines, two sections, 7,512+ frames). Worm-period seed values have been verified against the [PHD2 mount worm period wiki](https://github.com/OpenPHDGuiding/phd2/wiki/Mount-Worm-Period-Info). §11 enumerates everything that changed from the prior spec and why.

---

## Table of contents

1. Positioning and goals
2. Reference landscape — what exists today
3. PHD2 guide log format — verified against a real log
4. Architectural principles (applies to all phases)
5. **Phase v1 — Parity with PHDLogViewer (core)**
6. **Phase v2 — Parity with PHDLogViewer (advanced) + PEMPro LV differentiators**
7. **Phase v3 — Automated diagnostic engine (NightCrate differentiation starts here)**
8. **Phase v4 — Multi-log comparison, trends, shareable reports, catalog integration**
9. **Phase v5+ — Debug logs, live monitoring, AI analysis, recommendations**
10. Explicitly out of scope (for now and possibly forever)
11. Corrections from the prior spec (what changed and why)
12. References

---

## 1. Positioning and goals

PHD2 is the overwhelmingly dominant autoguiding application in amateur astrophotography. ASIAIR, N.I.N.A., SGPro, and Ekos all either bundle PHD2 or integrate with it, so a PHD2 guide log analyzer is not a niche feature — it is the common denominator across nearly every serious astrophotographer's workflow.

Today the community has three pragmatic options:

- **PHDLogViewer** (Andy Galasso) — the reference tool. Good visualization, minimal interpretation.
- **PEMPro Log Viewer** (Ray Gralak) — freeware, Windows-only, focused on periodic error analysis.
- **Excel / hand analysis** — the fallback, explicitly suggested by the PHD2 manual when neither tool fits.

The dominant support pattern is "post your log to the PHD2 Google Group and wait for an expert to interpret it." The PHD2 project acknowledges this: the interpretation tutorial ([Bruce Waddington's *Analyzing PHD2 Guiding Results*](https://openphdguiding.org/Analyzing_PHD2_Guide_Logs.pdf)) is a 30-page PDF. There is no automated interpreter today.

**Goal**: become the analyzer that replaces "post log, wait for expert." The three gaps that make this goal defensible:

1. **No automated interpretation exists today.** Filled in v3.
2. **No multi-session / trend analysis.** Each log is analyzed in isolation; patterns across weeks go invisible. Filled in v4.
3. **No modern, cross-platform, equipment-aware UI.** Progressive across all phases.

The delivery strategy is "match first, differentiate next":

- v1 + v2: give users no reason to keep PHDLogViewer open in parallel.
- v3+: make NightCrate the preferred tool.

Each phase ships as a standalone, useful release. The v1 analyzer is fully usable on its own even if v2+ never shipped.

---

## 2. Reference landscape — what exists today

### 2.1 PHDLogViewer (the reference tool)

**Verified against** the [product page](https://adgsoftware.com/phd2utils/), the [complete changelog](https://adgsoftware.com/phd2utils/ChangeLog.txt) (latest v0.6.4, Jan 2020), and the [GitHub repo](https://github.com/agalasso/phdlogview). Licensed GPLv3 since 0.5.1. Built on wxWidgets; native Windows, macOS (three separate builds for OS versions), and Ubuntu (via [Patrick Chevalley's PPA](https://launchpad.net/~pch/+archive/ubuntu/phd2)).

Capabilities, grouped:

**Visualization**
- Guide log plot (time series) with independent RA and Dec traces
- Calibration plot showing step direction, magnitude, and distance
- Scatter plot of dx / dy
- Periodogram (RA frequency analysis) for identifying drive harmonics
- Timestamps on horizontal axis
- Guide pulse directions labeled on the vertical axis
- PHD2 version displayed in the window title bar

**Statistics**
- Per-section RMS (RA, Dec, Total)
- RA and Dec drift
- Peak values
- Saturation indicator in the row info line
- Stats values copyable to clipboard

**Interaction**
- Pan / zoom toggle for vertical axis (keyboard: P or Z)
- Lock vertical scale across sessions (use the same arcsec or pixel scale for every section)
- Manual include / exclude range via mouse drag (control-drag to exclude)
- **Automatic exclusion of settle periods after dither**, triggered by "settle begin" / "settle end" events issued into the log by the imaging application (not generated by PHD2 itself — see §3.5)
- Cursor position readout for both the drift-corrected view and the periodogram
- Toggle display between AO corrections and Mount corrections
- Configurable RA / Dec colors with a legend
- Button to open the log file in an external text editor

**Advanced analysis**
- **"Analyze selected, raw RA"** — computationally undo RA guide corrections over a selected range to reconstruct the unguided RA trace (reveals periodic error without needing a dedicated unguided session). Added in 0.6.2.
- **Dedicated Guiding Assistant handling** — drift-corrected display plus frequency analysis on GA sections specifically. Added in 0.6.0.
- **Handles backward timestamp jumps** (computer clock changes mid-session). Added in 0.6.3.
- File-open dialog filters to `PHD2_GuideLog*.*` so debug logs don't get opened by mistake.

### 2.2 PEMPro Log Viewer (secondary reference)

Freeware companion to the commercial PEMPro. Per [community posts](https://groups.google.com/g/open-phd-guiding/c/ASpvnU-arns):

- Frequency analysis with **mount-specific worm-period annotations** — ships with external text files mapping mount → worm period → expected frequency peaks.
- **"Add guiding" overlay** — approximates what unguided tracking would have looked like (similar intent to PHDLogViewer's "undo corrections" but displayed as an overlay).
- Color-coded segment display distinguishing section starts, parameter lines, parameter values, samples with / without pulses issued, and dropped frames.
- Windows-only.

### 2.3 PECPrep

Mount-PEC-curve-building tool that accepts PHD2 logs as input. Not primarily a log analyzer; the overlap with NightCrate's analyzer is negligible. Out of scope as a reference.

### 2.4 PHD2's built-in Guiding Assistant

Not a log analyzer, but relevant: PHD2's [Guiding Assistant](https://openphdguiding.org/man/Guiding_Assistant.htm) is an in-app tool that temporarily disables guide output, measures unguided mount behavior for a user-chosen interval, optionally runs a dedicated Dec backlash measurement sequence, and writes its own distinct section into the guide log with RMS, polar alignment error estimate, suggested settings, and measured backlash. The last three GA reports are stored in the PHD2 equipment profile. PHDLogViewer has special handling for GA sections, and NightCrate should too (v2).

### 2.5 Feature parity matrix

| Capability | PHDLogViewer | PEMPro LV | NightCrate target |
|---|---|---|---|
| Time-series display | ✓ | ✓ | **v1** |
| Scatter plot | ✓ | — | **v1** |
| Basic stats (RMS, peak, drift) | ✓ | ✓ | **v1** |
| Automatic dither-settle exclusion | ✓ | ✓ | **v1** |
| Manual range exclusion | ✓ | — | **v1** |
| Multi-section navigation within a file | ✓ | ✓ | **v1** |
| Calibration plot | ✓ | — | **v1** |
| Unit toggle (pixels / arcsec) | ✓ | ✓ | **v1** |
| Lock vertical scale across sections | ✓ | — | **v1** |
| Periodogram / FFT | ✓ | ✓ | **v2** |
| Unguided-tracking reconstruction | ✓ | ✓ | **v2** |
| Guiding Assistant run handling | ✓ | — | **v2** |
| AO / Mount corrections toggle | ✓ | — | **v2** |
| Mount-specific worm-period markers | — | ✓ | **v2** (equipment-aware) |
| **Automated diagnostic interpretation** | — | — | **v3** |
| **Equipment-aware thresholds** | — | — | **v3** |
| **Multi-log comparison** | — | — | **v4** |
| **Trend analysis over time** | — | — | **v4** |
| **Shareable HTML report export** | — | — | **v4** |
| **AI-driven session analysis** | — | — | **v5+** |
| **Live session monitoring (JSONRPC)** | — | — | **v5+** |

---

## 3. PHD2 guide log format — verified against a real log

Primary authoritative references:

- [OpenPHDGuiding PHD2GuideLog wiki](https://github.com/OpenPHDGuiding/phd2/wiki/PHD2GuideLog)
- [PHD2 Trouble-shooting and Analysis manual](https://openphdguiding.org/man/Trouble_shooting.htm)

A real ASIAIR-bundled log was inspected alongside these docs; where the docs and reality diverged, the spec trusts **reality**. All divergences are called out explicitly below.

### 3.1 File-level structure

Plain UTF-8 text, line-oriented. The file begins with a version line of the form:

```
PHD2 version 2.6.13, Log version 2.5. Log enabled at 2026-03-07 19:33:45
```

**Reality check**: In the ASIAIR sample log, this line reads `PHD2 version, Log version 2.5. Log enabled at 2026-03-07 19:33:45` — the actual PHD2 application version is missing. The parser must tolerate a blank PHD2 version. The **Log version** (`2.5` here) is a distinct format-version number — capture it even when the app version is missing.

After the version line, the file contains zero or more **sections**, freely interleaved. Each section is either a **calibration section** or a **guiding section** and begins with:

- `Calibration Begins at <YYYY-MM-DD HH:MM:SS>`, or
- `Guiding Begins at <YYYY-MM-DD HH:MM:SS>`

…in the local time zone of the machine running PHD2 (no explicit zone indicator in the log). Every section ends at one of:

- the next section header,
- an explicit `Guiding Ends at <timestamp>` line (calibration sections have no parallel end marker; they are closed by a `Calibration complete, mount = <name>.` line),
- end-of-file (the final section frequently has no explicit end — the sample log ends this way).

All distances and positions in both section types are expressed in **guide camera pixels**, not arcseconds.

### 3.2 Section header block

After the section-begin line and before the CSV column header, a section contains a freeform block of `key = value` settings describing equipment, algorithms, and sky geometry at the start of the section.

**Reality check — formatting is irregular.** The PHD2 manual implies one setting per line; real logs commonly pack multiple settings onto a single line, separated sometimes by commas and sometimes by bare spaces:

```
Pixel scale = 3.96 arc-sec/px, Binning = 2, Focal length = 250 mm
Mount = ZWO000, Calibration Step = 2000 ms, Assume orthogonal axes = no
Dec = 69.0 deg, Hour angle = -3.84 hr, Pier side = West, Rotator pos = Unknown
Y guide algorithm = Resist Switch, Minimum move = 0.100 Aggression = 100% FastSwitch = enabled
                                                       ^ no comma before "Aggression"
```

The parser must therefore **search for known keys by regex, not split on commas**. Unknown keys are retained verbatim in a freeform collection on the section (don't drop them — future PHD2 versions add new keys and users often want to inspect them).

Known keys the analyzer should extract (per-axis suffixes like `X`/`Y` or `RA`/`Dec` must be preserved):

| Key | Semantic |
|---|---|
| `Camera` | guide camera model string |
| `Mount` | mount name string (often cryptic, e.g. `ZWO000`, `On-camera`) |
| `AO` | adaptive optics device (if present) |
| `Pixel scale` | arcsec / pixel at the guide camera |
| `Binning` | guide camera binning |
| `Focal length` | guide scope focal length, mm |
| `Exposure` | guide exposure, ms |
| `Pier side` | `East` / `West` / `Unknown` |
| `Dec` | target declination at section start (degrees; may be given as `DDdMMmSSs` or `NN.NN deg`) |
| `Hour angle` | hour angle at section start, hours |
| `Rotator pos` | rotator position in degrees, or `Unknown` |
| `Lock position` | X, Y pixel position of the lock point |
| `Star position` | X, Y pixel position of the selected star at section start |
| `HFD` | half-flux diameter of the selected star at section start, **pixels** — note: this is a section-header value, *not* a per-frame column (see §3.3) |
| `Search region` | tracking-rectangle half-size, pixels |
| `Star mass tolerance` | percent |
| `Dither` | axes + mode description |
| `Dither scale` | multiplier |
| `X guide algorithm` / `Y guide algorithm` | algorithm names (e.g. `Hysteresis`, `Resist Switch`, `LowPass`, `LowPass2`, `Predictive PEC`) |
| `Hysteresis`, `Aggression`, `Minimum move`, `FastSwitch`, `Predictive PEC Period Length`, etc. | algorithm parameters, per-axis |
| `Backlash comp` | `enabled` / `disabled` |
| `pulse` | backlash compensation pulse ms |
| `Max RA duration`, `Max DEC duration` | ms caps |
| `DEC guide mode` | `Auto` / `North` / `South` / `Off` |
| `RA Guide Speed`, `Dec Guide Speed` | sidereal multiple, often `Unknown` |
| `Cal Dec` | declination used at calibration time |
| `Last Cal Issue` | `None` or a diagnostic string |
| `xAngle`, `xRate`, `yAngle`, `yRate`, `parity` | calibration-derived geometry (on the `Mount = ...` line) |
| `Assume orthogonal axes` | `yes` / `no` |
| `Calibration Step` | ms, on calibration section headers |
| `Image noise reduction` | `none` / `2x2 mean` / `3x3 median` |
| `Equipment Profile` | profile name string (frequently empty on ASIAIR logs) |

Values can legitimately be empty (empty Equipment Profile, `Unknown`, `?/?`). The parser must tolerate these without dropping the row.

### 3.3 CSV columns — guiding sections

Per the [wiki](https://github.com/OpenPHDGuiding/phd2/wiki/PHD2GuideLog), a guiding section's CSV header is:

```
Frame,Time,mount,dx,dy,RARawDistance,DECRawDistance,RAGuideDistance,DECGuideDistance,
RADuration,RADirection,DECDuration,DECDirection,XStep,YStep,StarMass,SNR,ErrorCode,ErrorDescription
```

That is **19 columns** per the wiki.

**Reality check — the real header may only declare 18 columns.** The ASIAIR log's header line ends with `ErrorCode`, with no `ErrorDescription`. However, **error rows in the same log have 19 fields** — an appended quoted description string. Successful rows have 18. So the same log can have rows of differing arity.

Example from the ASIAIR log:

```
# 18 fields, ErrorCode = 0
1,1.202,"Mount",-0.307,-0.674,-0.698,-0.265,-0.628,0.000,500,E,0,,,,1045,21.07,0

# 19 fields, ErrorCode = 6, ErrorDescription appended
216,235.138,"DROP",,,,,,,,,,,,,6443,53.41,6,"Star lost - mass changed"
```

Parsing strategy (functional requirement, not implementation):

- Read column names from the actual header line of each section. Do not assume a fixed column count across logs or even across rows.
- Map values **by column name**, not position. Added or reordered columns in future PHD2 versions must not break the parser.
- Row arity may exceed the declared header by **one** trailing field, which is treated as `ErrorDescription`. Row arity may also equal the declared count with `ErrorDescription` absent.
- Missing fields (empty string between commas) resolve to null / not-measured. Do not coerce empty to zero — that silently corrupts all downstream stats.

Column semantics:

| Column | Semantic | Reality notes |
|---|---|---|
| `Frame` | 1-based frame number within the section | |
| `Time` | **Elapsed seconds from the section start timestamp**, not wall-clock | Wall-clock time = section-start + Time. Parser must compute wall-clock if wall-clock is needed downstream. |
| `mount` | one of `"Mount"`, `"AO"`, `"DROP"` (always quoted) | `DROP` = frame rejected by PHD2 (always has ErrorCode != 0) |
| `dx`, `dy` | star offset from lock position, camera pixels | null on DROP frames |
| `RARawDistance`, `DECRawDistance` | `(dx, dy)` projected onto mount axes | null on DROP frames |
| `RAGuideDistance`, `DECGuideDistance` | output of the guide algorithm (after min-move, hysteresis, etc.) | null on DROP frames |
| `RADuration`, `DECDuration` | guide pulse duration in ms. `0` = no pulse issued (below min-move). | null on DROP frames |
| `RADirection` | `E`, `W`, or empty when no pulse | |
| `DECDirection` | `N`, `S`, or empty when no pulse | |
| `XStep`, `YStep` | AO step values in AO steps | empty / null when no AO device |
| `StarMass` | integrated pixel intensity of the guide star | usually still populated on error rows (SNR-based errors still measure mass) |
| `SNR` | signal-to-noise ratio of the guide star | usually still populated on error rows |
| `ErrorCode` | integer error code, `0` = OK | |
| `ErrorDescription` | quoted error string, present iff ErrorCode ≠ 0 | **Authoritative: do not maintain a separate code-to-string table. Use the log's own ErrorDescription.** See §11 for why. |

### 3.4 CSV columns — calibration sections

Per the wiki:

```
Direction,Step,dx,dy,x,y,Dist
```

**Reality check — calibration has substructure.** A calibration section is actually a sequence of **five named phases** delimited by prose completion lines. From the ASIAIR sample:

```
West,0,...        ← West phase (tests RA movement in one direction)
West,1,...
...
West,11,...
West calibration complete. Angle = 85.1 deg, Rate = 1.238 px/sec, Parity = N/A
East,11,...       ← East phase (returns star toward origin)
...
East,0,...
Backlash,0,...    ← Backlash clearing phase (precedes North moves)
...
Backlash,3,...
North,0,...       ← North phase (tests Dec movement)
...
North,4,...
North calibration complete. Angle = -6.3 deg, Rate = 3.254 px/sec, Parity = N/A
South,4,...       ← South phase (returns star toward origin)
...
South,0,...
Calibration complete, mount = ZWO000.
```

The two phase-completion lines (`West calibration complete ...`, `North calibration complete ...`) carry the derived **angle (degrees)** and **rate (px/sec)** for each axis — these are the primary outputs of calibration and the analyzer should preserve them in the section model. The overall `Calibration complete, mount = ...` closes the section.

Calibration data semantics:

| Column | Semantic |
|---|---|
| `Direction` | One of `West`, `East`, `Backlash`, `North`, `South` |
| `Step` | Step index (ascending in forward phases, descending in return phases) |
| `dx`, `dy` | Pixel offset from the phase start position |
| `x`, `y` | Current pixel position |
| `Dist` | `sqrt(dx² + dy²)`, per the manual |

### 3.5 INFO: lines

INFO lines are interspersed with CSV data rows inside a section and represent events. **Reality check — my prior spec's INFO patterns were wrong.** The patterns actually observed in the ASIAIR log:

| Observed INFO line | Semantic |
|---|---|
| `INFO: SETTLING STATE CHANGE, Settling started` | settle period began (imaging app requested PHD2 to begin settling after a dither) |
| `INFO: SETTLING STATE CHANGE, Settling complete` | settle period ended |
| `INFO: SET LOCK POSITION, new lock pos = X, Y` | lock position moved (typically precedes a DITHER event) |
| `INFO: DITHER by DX, DY, new lock pos = X, Y` | dither vector applied; immediately followed by a settle-started |

Other patterns that may appear in other logs (documented in PHD2 source and community posts, not present in this sample):

| Pattern | Semantic |
|---|---|
| `INFO: SERVER received SET_PAUSED` / `INFO: Server received PAUSED` | external pause |
| `INFO: SERVER received SET_PAUSED, UNPAUSED` / `RESUMED` | external resume |
| `INFO: Star selected at ...` | user or auto-select picked a new star |
| `INFO: Alert: <message>` | PHD2 generated a user-visible alert |
| `INFO: Guiding Output Enabled` / `Disabled` | PHD2 guiding was paused (GA begin/end typically emits this) |
| `INFO: MOVE LOCK POSITION, ...` | manual lock position change |

**Functional requirement**: classify these into a small closed vocabulary (`settle_begin`, `settle_end`, `lock_position_set`, `dither`, `server_pause`, `server_resume`, `star_selected`, `alert`, `guiding_enabled`, `guiding_disabled`). Always retain the full raw message regardless of classification — if a new INFO pattern arrives in a future PHD2 version, it falls through to a generic `info` type and is still captured, just not structurally classified.

Classifiers should be string-contains or regex checks, not exact matches, because the SETTLING STATE CHANGE pattern contains a sub-field ("Settling started"/"Settling complete") that a prefix match misses.

### 3.6 Dither settle — how it actually works

Per a [community post from PHDLogViewer's author](https://groups.google.com/g/open-phd-guiding/c/XKGu6Q-nOvQ), the **automatic exclusion of settle periods depends on the imaging application issuing settle begin/end commands to PHD2**. Older imaging apps or custom pipelines may dither without issuing these commands, so the `SETTLING STATE CHANGE` events are not guaranteed to appear after every `DITHER` line. In the ASIAIR log they do appear consistently, but the spec cannot assume this.

Functional requirement: implement **two** dither-settle detection strategies:

1. **Event-based (preferred)** — find `SETTLING STATE CHANGE, Settling started` / `Settling complete` pairs within the section; mark all frames in each interval as `in_settle = true`.
2. **Heuristic fallback (when event pairs are absent after a DITHER)** — starting from the frame immediately following a `DITHER` INFO line, mark frames as `in_settle = true` until either (a) total corrected distance stays below a threshold (default 0.5 px) for ≥ N consecutive frames (default 3), or (b) a fallback maximum duration elapses (default 30 seconds). All three thresholds are user-overridable.

Statistics on a section are computed with in-settle frames excluded by default; a UI toggle can include them.

### 3.7 Locale bug

Per [PHD2 issue #453](https://github.com/OpenPHDGuiding/phd2/issues/453) and a [confirmed forum report](https://groups.google.com/g/open-phd-guiding/c/D_IkgJ3GuO8), PHD2 on Italian / German / French / other comma-decimal locales has historically written logs with commas as decimal separators **and** commas as CSV field separators, making rows ambiguous:

```
Frame,Time,mount,dx,dy,RARawDistance,DECRawDistance,...,ErrorCode
1,2,541,"Mount",-0,514,0,432,-0,671,-0,182,-0,423,0,000,54,E,0,,,,15349,8,71,1
```

where `2,541` should be `2.541`, `-0,514` should be `-0.514`, etc. The header declares 18 columns; the data row has 26 comma-separated tokens.

**Detection**: after parsing the header and determining the declared column count *C*, measure the token count *T* of the first data row. If *T* ≫ *C* (rule of thumb: *T* > *C* × 1.3), assume locale-corrupted data.

**Recovery**: re-parse the row under the rule "every numeric field occupies two adjacent comma-separated tokens joined by a `.`". The `mount` column (a quoted string) anchors the position. The parser should walk the header columns, promoting pairs of tokens to a single float where the expected type is numeric.

Mark the section with a `locale_recovery_applied = true` flag so the UI can surface a small indicator ("Decimal-separator recovery applied — verify values look correct").

### 3.8 Backward timestamp jumps

Computer clock changes during a session (NTP resync, manual adjustment, timezone change) can produce section timestamps that go backward. PHDLogViewer added handling for this in 0.6.3. The analyzer should not assume monotonic section-start timestamps — sort by file order, not by timestamp, and surface a warning on the log if a backward jump is detected.

### 3.9 File identification

Default PHD2 filenames: `PHD2_GuideLog_YYYY-MM-DD_HHMMSS.txt`. The parser accepts files matching that pattern, **and** content-sniffs by checking whether the first non-blank line starts with `PHD2 version` (catches renamed files, ASIAIR-bundled logs, zipped logs, user-uploaded logs with arbitrary filenames).

Debug logs (`PHD2_DebugLog_*.txt`) start with a different header and are rejected in v1–v4 with a clear error. Debug log support lands in v5 (§9).

---

## 4. Architectural principles (applies to all phases)

These are design constraints that hold across every phase. They are principles, not implementation details.

### 4.1 Standalone-first, catalog-ready

The analyzer ships as a standalone feature from day one. A user drops a log file on the page and gets a full analysis without the broader NightCrate imaging-core catalog existing. When the imaging core ships later, the analyzer gains catalog-linked logs as a second entry point; the same parser and analyzer serve both paths. No parser rewrite, no UI rewrite — only additive entry points.

### 4.2 Pixel-canonical internal representation

PHD2 writes pixels; NightCrate keeps pixels as the canonical representation. Arcsecond conversions are computed at display time from the section's declared `Pixel scale` value. This matches PHD2's native convention, avoids round-trip precision loss, and lets the user flip between pixels and arcsec without re-reading the source file.

### 4.3 Three-level section granularity

A log contains sections; a section contains per-frame samples and per-event entries. Every computed metric, every diagnostic finding, every displayed chart is naturally scoped to a section. This is the granularity users reason at. File-level aggregation (a "session" spanning all sections in a file) is a derived view, not a primary object.

### 4.4 Parse-by-name, never-by-position

Column order in PHD2 logs is stable across versions but **not guaranteed**. The parser reads headers per-section and extracts values by name. New columns from future PHD2 versions fall through harmlessly; reordered columns don't silently corrupt everything. The parser must never rely on "field 7 is always RARawDistance."

### 4.5 Colorblind-safe palette

Fred is red-green colorblind. Per project convention across all NightCrate visualizations: viridis for sequential data, blue-to-yellow for sequential alternatives, blue/orange categorical (RA = blue, Dec = orange). Never red/green. Error states use the project's blue/orange error palette.

### 4.6 Never silently coerce missing data

Empty CSV fields, empty header values, missing settle events, absent ErrorDescription — all resolve to explicit null / absent markers, never to zero or empty string. Downstream metrics distinguish "zero pulse issued" from "we don't know." This matters because a chart line falsely pinned to zero during DROP runs looks like ideal guiding.

### 4.7 Interpretive claims must be sourced

Every diagnostic rule in v3+ has a reference in the codebase pointing to the community source for its interpretation (usually the Bruce Waddington tutorial or a specific PHD2 manual page). This is non-negotiable for a tool whose differentiator is interpretation — an undocumented heuristic is an untrusted heuristic.

---

## 5. Phase v1 — Parity with PHDLogViewer (core)

**Target user**: "I just want to look at my PHD2 guide log and see what my guiding actually looked like." Casual users, users currently using PHDLogViewer, anyone sharing a log for forum help.

**v1 success criterion**: a PHDLogViewer user can open a log in NightCrate and do everything they'd normally do in PHDLogViewer's basic workflow, without needing PHDLogViewer open.

### 5.1 Parser (all of §3)

Full implementation of §3: file identification, section splitting, header block parsing, guiding + calibration CSV parsing, INFO classification, dither settle detection (event-based and heuristic), locale recovery, backward-timestamp-jump tolerance. Parser warnings are surfaced to the user (as a small "N warnings" indicator with click-to-expand detail).

### 5.2 Per-section computed metrics

Computed after dither-settle filtering. All metrics are reported in both **pixels** and **arcsec** (arcsec derived from the section's `Pixel scale`). If a selection within the section is made (§5.5), metrics recompute on the selection.

- **RMS RA** — `sqrt(mean(RARawDistance²))`
- **RMS Dec** — `sqrt(mean(DECRawDistance²))`
- **RMS Total** — `sqrt(RMS_RA² + RMS_Dec²)`
- **Peak RA** — `max(|RARawDistance|)`
- **Peak Dec** — `max(|DECRawDistance|)`
- **RA drift** — linear regression of RARawDistance against Time; slope reported in arcsec/minute
- **Dec drift** — same for DECRawDistance; sign-preserving (used in v3 diagnostics, displayed in v1)
- **RA oscillation** — fraction of consecutive-frame pairs where `sign(RARawDistance[i]) ≠ sign(RARawDistance[i-1])`; rates near 0.5 suggest chasing seeing, near 0.3 are typical of good guiding
- **Dec oscillation** — same for Dec (rarely large, but spikes when backlash-compensation is misbehaving)
- **Frame count** — total, excluded-by-settle, excluded-by-user, included-in-stats
- **Duration** — wall-clock duration of the included window

### 5.3 Per-section charts

**Time-series chart** — primary view. X axis: time (elapsed seconds or wall-clock, user-selectable). Y axis: distance (pixels or arcsec, user-selectable).

- RA raw trace (blue)
- Dec raw trace (orange)
- Correction bars below the trace showing RADuration and DECDuration with direction encoded (blue above-axis for West RA pulse, blue below-axis for East; orange above for North Dec, orange below for South; bar height ~ duration)
- SNR trace in a small secondary panel
- StarMass trace in a small tertiary panel
- Dither settle periods visually shaded (subtle blue-orange pattern, not red)
- Zoom (both axes), pan, reset
- **Cursor readout** showing the values at the cursor position for every trace (matching PHDLogViewer 0.6.1)

**Scatter plot** — secondary view. X = dx, Y = dy, one point per sample. Dispersion ellipse overlay at 1σ and 2σ. Centroid marker (should be near origin; a visible offset indicates calibration drift).

**Calibration plot** — for calibration sections. Shows the five phases (West, East, Backlash, North, South) as stepped paths in dx/dy pixel space, with phase markers and the derived angle / rate values displayed as a small table.

### 5.4 Section navigation within a file

When a log contains multiple sections, a section list is shown (time-ordered by file position, not by timestamp, per §3.8). Each list item shows:

- Section type (Calibration / Guiding)
- Start time (wall-clock)
- Duration
- Frame count
- A brief summary stat (RMS Total for guiding; derived angle/rate for calibration)

Clicking a section switches the main view.

### 5.5 Interaction parity features

- **Unit toggle** — pixels ↔ arcsec, applies everywhere (stats, chart axes, readouts)
- **Lock vertical scale across sections** — when enabled, switching sections preserves the Y axis range of the time-series chart (matches PHDLogViewer 0.5.0)
- **Manual range selection** — drag to select a time range on the chart; stats recompute on selection. A separate drag-gesture (matching PHDLogViewer's control-drag) excludes a range from stats rather than selecting it.
- **Include / exclude settle periods toggle** — one click to flip between "stats exclude settle frames" (default) and "stats include everything"
- **Copy stats to clipboard** — a button that copies the current per-section stats as tab-separated text, preserving the user's current unit choice (matches PHDLogViewer 0.5.0)
- **Open in external text editor** — a button that reveals the underlying log file in the user's OS file manager (matches PHDLogViewer 0.6.0 intent; opening a text editor directly requires knowing the user's editor, so "reveal in finder/explorer" is a reasonable alternative)

### 5.6 INFO event display

A collapsed list of events (dither, settle begin/end, lock position changes, alerts, server pauses) inside each section. Each event is clickable to jump the time-series cursor to that moment.

### 5.7 Warnings and diagnostics displayed in v1

Only **parse-time warnings** in v1. No interpretive diagnostics (those come in v3). Examples of v1 warnings:

- "Locale-corrupted data; decimal-separator recovery applied. Verify values look correct."
- "Backward timestamp jump detected between sections — sections are shown in file order."
- "N frames had errors (see the Events tab)."
- "Sample cadence varies by > 20% within this section — frequency analysis is disabled."
- "Pixel scale not declared in header; arcsec values cannot be computed."

### 5.8 Unit scope clarification

Throughout v1 the user sees guiding performance of a single log file, section by section. There is **no** cross-log comparison, trend analysis, or equipment-aware interpretation in v1. All of that arrives in later phases.

---

## 6. Phase v2 — Parity with PHDLogViewer (advanced) + PEMPro LV differentiators

**Target user**: "I'm tuning my mount — I need periodic-error analysis, and I want to see what my mount is doing without my guiding corrections on top of it."

**v2 success criterion**: a PHDLogViewer user doing mount tuning can do it in NightCrate, and the worm-period markers on the FFT (PEMPro LV's one real differentiator) are present when equipment context exists.

### 6.1 Frequency analysis (FFT / periodogram)

**Input**: per-section RA raw distance series. Resample to uniform cadence by linear interpolation to the mean frame cadence of the section. If cadence varies by > 20%, skip the FFT and surface a warning (per §5.7).

**Output**: power spectrum of RA raw distance. Preferred representation: arcsec² per cycle (so peaks report directly as arcsec amplitude squared). X axis can be displayed either as period (seconds) or frequency (Hz) — period is more intuitive for astrophotography. Secondary axis: cumulative power contribution vs. period (optional, on by default).

**Peak identification**: find local maxima above `median + 3 × MAD` of the spectrum. Report the top 8 by amplitude with their period (seconds) and amplitude (arcsec). Peaks at periods < 5 seconds are attributed to seeing, not to mount mechanics, and are shown separately or dimmed.

**Minimum section duration for FFT**: 5 minutes delivers usable frequency content for sub-worm-period analysis. For worm-period detection specifically, **at least 2× the expected worm period** (10–15 minutes for typical mounts) is needed for a reliable peak. Shorter sections: compute and display the FFT anyway, but annotate with a "section too short for confident worm-period detection" warning.

Also compute the FFT of Dec raw distance — less commonly useful, but Dec periodic signals can indicate balance or worm issues and users should be able to inspect them. Hidden behind a toggle; not shown by default.

### 6.2 Unguided RA reconstruction

Reconstruct the unguided RA trace by accumulating the issued guide corrections back onto the raw distance series. For each frame *i*:

```
unguided_RA[i] = RARawDistance[i] + cumulative sum of (RAGuideDistance[j]) for j < i that produced actual motion
```

The exact accumulation math needs to account for (a) Min-move frames where RAGuideDistance was computed but no pulse was issued (the mount didn't actually move), (b) frames where the pulse was issued but clipped by `Max RA duration`, (c) the known `xRate` (px/sec converted to px/pulse by multiplying by pulse duration). The canonical reference implementation is [PHDLogViewer's source](https://github.com/agalasso/phdlogview) — CC should cross-reference that implementation during v2.

Display: overlay unguided RA on the time-series chart (toggle on/off); feed the unguided trace into a dedicated FFT view that reveals periodic error.

This matches PHDLogViewer's "Analyze selected, raw RA" and PEMPro Log Viewer's "Add guiding" feature. Both tools confirm this is a valuable, differentiating capability.

### 6.3 Guiding Assistant section handling

Detect Guiding Assistant sections by checking the INFO events inside the section for `Guiding Output Disabled` / `Guiding Output Enabled` pairs, or by detecting sections with no RA/DEC guide corrections issued (all `RADuration == 0` and `DECDuration == 0`).

For GA sections, the UI shows a **dedicated GA panel**:

- Unguided RMS RA / Dec / Total (primary numbers GA reports)
- Estimated polar alignment error (derived from Dec drift — see §7.2 for the formula)
- Measured Dec backlash (if a backlash-measurement sub-sequence is present — identifiable by a characteristic alternating-direction Dec pulse pattern with no RA corrections)
- Drift-corrected RA trace (subtract linear Dec drift before displaying)
- Dedicated FFT on the unguided RA trace with wider period range (GA captures unguided tracking, so the FFT is a direct PE measurement)

This matches PHDLogViewer's GA-specific handling added in 0.6.0.

### 6.4 AO vs Mount toggle

When a section contains `mount = "AO"` frames, the analyzer distinguishes:

- **Mount corrections** — what the mount was asked to do (via bump-the-mount commands)
- **AO corrections** — what the AO device did (tip/tilt steps)

The time-series chart gains a toggle: show Mount corrections only (default), AO corrections only, or both. Stats gain separate rows for AO-corrected RMS vs mount-corrected RMS. Matches PHDLogViewer 0.6.0 behavior.

### 6.5 Worm-period markers on FFT

When the analyzer has equipment context (the section's `Mount` string matches a mount in the NightCrate equipment catalog, and that mount has a known worm period), draw a vertical marker on the FFT at the worm period with a label (e.g. "HEQ5 worm, 638s"). If the FFT has a peak within ±5% of that period, call it out explicitly ("Worm-period peak: 0.8 arcsec RMS").

When equipment context is absent, fall back to an **"unbounded worm period detection" mode**: report the single largest peak in the canonical worm-period range (300–800 seconds) with amplitude > 2 arcsec and label it as "likely worm-period peak (uncertain without mount identification)".

Canonical mount worm periods — **sourced from the [PHD2 Mount Worm Period Info wiki](https://github.com/OpenPHDGuiding/phd2/wiki/Mount-Worm-Period-Info)**:

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
| RainBow Astro | RST 135 | 430.82 |
| iOptron | CEM25P | 598 |
| iOptron | CEM26, GEM28 | 600 |
| iOptron | CEM40, GEM45 | 400 |
| iOptron | CEM70 | 348 |
| iOptron | CEM120 | 240 |
| iOptron | IEQ45PRO | 336.6 |
| iOptron | SkyGuider Pro | 600 |
| Iexos | 100 | 600 |

Harmonic-strain mounts (ZWO AM5, iOptron HEM-series, Rainbow Astro harmonic models) have **no worm and no worm-period** — the worm-period field is null, and the worm-period diagnostic does not fire for those mounts.

**All values to be entered into seed data verbatim from the wiki, not from Claude's recollection.** Re-verify via the wiki link at implementation time (the page is community-editable and updates).

---

## 7. Phase v3 — Automated diagnostic engine (NightCrate differentiation starts here)

**Target user**: "I don't want to read a 30-page tutorial to figure out what my log means. Tell me what's wrong."

**v3 success criterion**: a user with a problematic log sees a concise, accurate list of findings within 5 seconds of the log loading, with links to references so they can learn more.

### 7.1 Two-tier diagnostic structure

Every diagnostic finding lives in one of two tiers, visually distinct in the UI:

**Confident** — the signature in the data has a single canonical community-agreed explanation. Stated as a fact. Not dismissible. Examples: overshoot-pause-overshoot Dec pattern → Dec backlash; sustained Dec drift → polar alignment error of estimated magnitude; SNR collapse preceding `star_lost` events.

**Speculative** — the signature has multiple plausible explanations or relies on a known-noisy measurement. Stated as a hypothesis ("may indicate…"). Dismissible per-analysis. Examples: gradual RMS trend (thermal drift vs flexure vs changing seeing); non-worm-period FFT peak (gearbox, belt, or motor harmonic).

A finding can only be promoted from speculative to confident after field evidence validates it; new rules default to speculative. This is a manual, out-of-band decision tracked informally (e.g. a spreadsheet of real-world user reports where the rule fired correctly), not a runtime computation.

**Every finding includes**:

- Rule ID (stable identifier for the rule)
- Tier (confident / speculative)
- Category (one of: `polar_alignment`, `backlash`, `guide_star`, `mechanical`, `seeing`, `configuration`, `calibration`, `tracking`)
- Short summary (one sentence)
- Longer explanation (one paragraph)
- Evidence struct — the numeric values that made the rule fire (time ranges, magnitudes, ratios)
- Reference link — URL to the community source for this interpretation (typically a specific page of the Bruce Waddington tutorial or PHD2 manual)
- Actionable next step (one sentence, optional)

### 7.2 Confident-tier rules (v3)

**`polar_alignment_from_dec_drift`** — category `polar_alignment`.

Preconditions: guiding section ≥ 10 minutes, non-GA (GA has its own built-in estimate); declination known; drift rate computable.

Formula: `PA_error_arcmin ≈ |dec_drift_arcsec_per_hour| / (15.7 × cos(declination))`. The 15.7 coefficient derives from sidereal rate: a 1 arcmin PA error produces approximately 15.7 arcsec/hour of Dec drift at the celestial equator. Reference: [Gralak / CelestialWonders drift alignment article](http://www.celestialwonders.com/articles/polaralignment/MeasuringAlignmentError.html), [Starry Nights polar drift article](http://www.starrynights.us/Articles/Polar_Align.htm).

Fires when estimated PA error > 2 arcmin. Summary: *"Polar alignment error approximately N arcmin."* Actionable: *"Run the Guiding Assistant or PHD2's Drift Alignment tool to confirm and refine."*

**`dec_backlash_overshoot_pattern`** — category `backlash`.

Signature: a run of ≥ 5 consecutive Dec pulses in one direction, followed by ≥ 3 frames of Dec algorithm pause (zero pulses), followed by a Dec pulse in the reversed direction whose magnitude ≥ 2× the mean of the initial run.

Fires when at least 3 such sequences exist in the section. Reference: [Bruce Waddington tutorial](https://openphdguiding.org/Analyzing_PHD2_Guide_Logs.pdf), §"Declination backlash." Summary: *"Declination backlash detected."* Actionable: *"Consider running the Guiding Assistant backlash measurement and enabling PHD2's backlash compensation. Do not use mount-firmware backlash compensation."*

**`snr_drop_preceded_star_lost`** — category `guide_star`.

For each `ErrorCode ≠ 0` frame whose ErrorDescription contains "lost" or "no star," compute mean SNR in the 30 seconds prior vs the 30 seconds before that. Fires if ≥ 50% of lost-star events in the section had a prior SNR drop > 30%.

Summary: *"SNR dropped before star-loss events — likely clouds, dew, or focus shift."* Actionable: *"Check for thin clouds or dew formation; if neither, investigate focus drift."*

**`sustained_dec_direction_pulses`** — category `polar_alignment`.

Fires when ≥ 90% of nonzero Dec pulses are in the same direction over a section ≥ 15 minutes. This is a complement to the Dec-drift PA diagnostic — they should usually co-fire, but pulses-in-one-direction can fire even when the algorithm is damping the drift enough that the raw drift signal is muted.

Reference: Bruce Waddington tutorial, §"Polar alignment." Summary: *"Dec corrections are predominantly <direction> — consistent with polar misalignment."*

**`star_saturation`** — category `guide_star`.

Fires when ≥ 5% of frames have ErrorDescription matching "saturat*" or "mass change*" (the exact strings vary by PHD2 version). Summary: *"Guide star is saturated or near-saturated in N% of frames."* Actionable: *"Reduce guide exposure or gain, or select a dimmer star."*

**`calibration_axes_not_orthogonal`** — category `calibration`.

Applies to calibration sections. Compute the angle between calibrated RA and Dec axes from the section's recorded `xAngle` and `yAngle`. Fires when `|angle - 90°| > 5°`.

Summary: *"Calibration RA/Dec axes deviate from orthogonality by N°."* Actionable: *"Check for mount alignment issues, cable flexure during calibration, or pier-side calibration done at a high declination."*

**`chasing_seeing_ra`** — category `configuration`.

All three conditions must hold:

- RA oscillation > 0.55
- Median RA pulse duration < 200 ms
- Section exposure < 2000 ms

Reference: Bruce Waddington tutorial, §"Chasing seeing." Summary: *"RA corrections are oscillating rapidly — likely chasing seeing."* Actionable: *"Increase the guide exposure to 2–3 seconds, increase RA min-move, or reduce RA aggressiveness."*

### 7.3 Speculative-tier rules (v3)

**`gradual_rms_trend`** — category `mechanical`. Linear regression of per-minute RMS over sections ≥ 30 minutes. Fires when slope > 0.005 arcsec/minute (worsening). Summary: *"RMS is gradually increasing — possible thermal drift, flexure, or changing seeing."*

**`non_worm_fft_peaks`** — category `mechanical`. FFT peaks (> 0.5 arcsec) at periods outside the worm-period range (300–800 s) and outside the seeing range (< 5 s). Summary: *"Periodic errors at N seconds detected — possibly gearbox, belt, or motor harmonics."*

**`snr_variability`** — category `seeing`. SNR standard deviation > 30% of mean SNR AND autocorrelation suggesting non-random pattern. Summary: *"Guide star brightness is fluctuating substantially — possible thin clouds or dew."*

**`possible_differential_flexure`** — category `mechanical`. Requires knowledge that the section is from a guide-scope setup (not OAG) — equipment-context-dependent. Sustained drift in both RA and Dec whose direction varies with pointing across multiple sessions. Summary: *"Sustained drift inconsistent with polar alignment — possible differential flexure between guide scope and main OTA."* (Single-session version is weak; this rule gets stronger in v4 multi-log.)

**`dec_oscillation_with_backlash_compensation`** — category `configuration`. Dec oscillation > 0.4 AND `Backlash comp = enabled` in the header. Summary: *"Dec is oscillating — backlash compensation may be over-tuned."*

**`low_snr_throughout`** — category `guide_star`. Mean SNR < 10 across the section without triggering actual star loss. Summary: *"Guide star SNR is low throughout — guiding may be less precise than needed."*

**`high_rms_vs_rig_expected`** — category `tracking`. Requires rig context. Fires when `rms_total_arcsec > 3 × rig.effective_guide_precision_arcsec`. Summary: *"Guiding RMS is substantially higher than expected for this rig's optical configuration."* (This is the rule that most directly consumes NightCrate's rig-suitability calculation from the Rig Calculators v2 spec.)

### 7.4 Equipment-aware enhancements

When the analyzer has rig context (user has associated a rig from the NightCrate equipment catalog with the current analysis):

- Worm-period FFT marker uses the rig's mount worm period (§6.5)
- `high_rms_vs_rig_expected` becomes available
- Flexure heuristics differentiate OAG vs guide-scope configurations
- Thresholds on RMS warnings adjust to the rig's expected guide precision

When rig context is absent, all diagnostics still function using absolute thresholds and uncertainty-aware language ("likely worm period" vs "worm-period peak at ...").

### 7.5 Diagnostic settings

User-adjustable knobs (with sensible defaults):

- Enable / disable speculative tier
- Enable / disable individual rules
- Adjust the confident-tier thresholds (advanced users only; nested behind a "tune diagnostics" affordance, not a front-line control)

Settings changes re-run the diagnostic engine against already-cached parsed data — no re-parse.

---

## 8. Phase v4 — Multi-log comparison, trends, shareable reports, catalog integration

**Target user**: "I want to see whether my guiding has gotten better since I did X. I want to share my results with someone for help."

**v4 success criterion**: a user can select N logs and see side-by-side statistics, trend lines over time, and export a standalone HTML report that a forum expert can view without installing anything.

### 8.1 Multi-log comparison

Select 2–20 logs. The comparison view shows:

- **Side-by-side stats table** — one row per section across all selected logs, with columns for section date, duration, RMS RA, RMS Dec, RMS Total, drift rates, oscillation metrics, and a "diagnostics summary" chip showing the top finding if any.
- **Trend chart** — RMS Total (and optionally each subcomponent) plotted against session date, one marker per section, with a trend line. The X axis can be switched between calendar date, session index, and integration time accumulated.
- **Diagnostic-cooccurrence matrix** — which diagnostic findings fire across which sessions. Reveals persistent issues vs one-off problems.
- **Configuration drift panel** — highlight when algorithm parameters, guide rates, or calibration values change between sessions (useful for "did my guiding get worse after that parameter change?").

### 8.2 Trend analysis

Simple summary over a selected time window:

- "Your average RMS Total over the last N nights is X, trending {up / down / flat}"
- "Dec backlash was detected in M of the last N nights"
- "Your polar alignment drift has been stable around N arcmin"

Intentionally modest in v4. Sophisticated trend analytics (e.g. "you stopped improving around date X") belong in v5+ with the AI analyzer.

### 8.3 Shareable HTML report export

One-click export of the current analysis (single log) or comparison (multi-log) as a standalone HTML file. Requirements:

- Self-contained — all SVG inline, no external CSS, no external JS, no external font files. Works from any filesystem location, opens correctly in any modern browser, viewable offline.
- Includes all charts as static SVG (not canvas) so the report is crisp and zoomable.
- Includes the per-section stats, diagnostic findings (both tiers), and any user notes added before export.
- Header block identifies the source log filename(s), PHD2 version(s), analysis timestamp, and NightCrate version.
- **Does not include the full per-frame sample data** (too large; a separate "export raw data as CSV" is available for users who want that).

This is the feature that most directly addresses the "post log to forum, wait for expert" workflow. A report is a single file that a forum poster can attach; the recipient opens it in a browser and sees a NightCrate-quality rendering without installing anything.

### 8.4 Catalog integration (imaging core arrived)

When the NightCrate imaging-core schema lands, the analyzer gains:

- A second entry path: analyze a log already ingested into the catalog, in addition to the standalone drop-a-file path
- Automatic association of guide-log sections with imaging sessions that overlap their time window
- Per-session "Guiding" tab on the session detail page showing the analysis for any overlapping guide logs
- Per-sub-frame annotation: mark a sub-frame as potentially affected if its exposure window contains a lost-star event, a settle period, or a large-deflection excursion

Parser, metrics, and diagnostic engine are unchanged — only the entry-point plumbing changes. This is by design (§4.1).

### 8.5 "Recently analyzed" history

A list of recently analyzed logs at the analyzer's home — one-click to reopen an analysis without re-parsing. Each entry shows filename, date, top-line RMS, top diagnostic summary.

---

## 9. Phase v5+ — Debug logs, live monitoring, AI analysis, recommendations

These are roadmap items rather than detailed spec phases. Each will get its own spec when its time comes.

### 9.1 PHD2 Debug log parsing

Debug logs (`PHD2_DebugLog_*.txt`) contain 10× the information of guide logs: internal algorithm state, raw camera frames, per-iteration guide algorithm traces, full network message bodies. They're the source when a guide log doesn't have enough signal to diagnose a problem.

Features unlocked:

- Per-frame star detection quality (not just a "lost" flag)
- Per-algorithm-iteration state (for users tuning predictive PEC)
- PHD2 internal alerts and warnings that don't surface to the guide log
- Network interaction traces (for diagnosing integration issues with N.I.N.A. / ASIAIR)

Significant parser complexity — debug logs are semi-structured text. Merits its own spec when prioritized.

### 9.2 Live session monitoring

PHD2 exposes a [JSON-RPC event monitoring interface](https://github.com/OpenPHDGuiding/phd2/wiki/EventMonitoring) that streams guide events in real time. NightCrate could connect to a running PHD2 instance and provide diagnostics *during* the session rather than after.

Requires network connection to the imaging machine (a concern for the ASIAIR rig where PHD2 runs on the ASIAIR itself). Out of scope until both ASIAIR network access and the analyzer's core diagnostic engine are solid.

### 9.3 AI-powered session analysis

Feed the full analysis output (parsed structure, computed metrics, diagnostic findings, equipment context, any overlapping image session metadata) to Claude and generate natural-language session summaries and recommendations. This is the post-MVP paid feature on the NightCrate roadmap.

Architectural prerequisite: the analysis output must be serializable into a coherent context window. The data model designed in v1–v4 must accommodate this without rework. This is the "AI-readiness as a hard constraint" principle applied to the analyzer domain.

### 9.4 Parameter recommendations

"Based on your log, try setting RA aggressiveness to X." This is deliberately deferred. The risk of a naive recommendation engine giving users bad advice and eroding the tool's credibility is high. The AI analyzer (§9.3) is a better vehicle for recommendations because it can express uncertainty natively, whereas a deterministic recommendation engine feels authoritative even when it's wrong.

If a deterministic recommender is ever built, it must follow the two-tier pattern (§7.1): confident recommendations for situations with a single community-agreed answer; speculative recommendations for everything else.

---

## 10. Explicitly out of scope (for now and possibly forever)

- **Editing the source log file.** The analyzer is strictly read-only on logs.
- **Cloud sync of analyses.** Everything is local.
- **Multi-user shared analyses.** The HTML report (§8.3) covers the collaboration use case.
- **Uploading logs to a remote PHD2 support service.** That's the PHD2 project's domain.
- **N.I.N.A. or ASIAIR session log parsers.** Those are separate primitives and are covered by their own specs when they are written. This spec handles only PHD2 guide logs — which includes ASIAIR-bundled PHD2 logs because ASIAIR uses PHD2 under the hood.
- **Autofocus run parsing.** Separate spec.
- **Computing calibration recommendations.** PHD2's own [Calibration Assistant](https://openphdguiding.org/man/Basic_use.htm) is the right place for that.
- **Replacing the PHD2 in-app guiding graph.** The analyzer is a post-hoc tool for logs, not a real-time display.
- **Analyzing logs from PHD (original PHD, not PHD2).** Format is different; user population is negligible in 2026.

---

## 11. Corrections from the prior spec (what changed and why)

Every item below was verified against one of: the authoritative PHD2 wiki, the PHD2 troubleshooting manual, PHDLogViewer's published changelog, or the real ASIAIR log `PHD2_GuideLog_2026-03-07_193345.txt`.

### 11.1 Column count and ErrorDescription

- **Prior spec claim**: guiding sections have 18 columns, ending in `ErrorCode`. "Newer PHD2 adds HFD at the end."
- **Corrected**: the authoritative [wiki](https://github.com/OpenPHDGuiding/phd2/wiki/PHD2GuideLog) lists 19 columns, ending in `ErrorDescription`. Real ASIAIR logs declare **18** in the header (stopping at `ErrorCode`) but append a 19th quoted `ErrorDescription` field on error rows only. **The same log has rows of differing arity.** Parser must accept both. There is no HFD column in guide logs — HFD appears in the section header's `Lock position = ..., Star position = ..., HFD = X px` line, i.e., it is the star's HFD at section start, not per-frame.
- **Why it matters**: the old parser assumption would silently drop the ErrorDescription field on error rows (useful) and would fail to find HFD data that doesn't exist where expected.

### 11.2 Error code lookup table

- **Prior spec**: maintained a hardcoded table mapping ErrorCode integers to strings (0=OK, 1=Saturated, 2=Low mass, 3=Low SNR, 4=Edge, 5=Mass change, 6=Large deflection, 7=Star lost).
- **Corrected**: the real ASIAIR log shows `ErrorCode = 6` with description `"Star lost - mass changed"` (not "Large deflection") and `ErrorCode = 7` with `"No star found"` (not "Star lost"). **The prior table was wrong.** Replacement approach: use the ErrorDescription string from the log itself; fall back to raw integer on successful rows (where ErrorCode is always 0 anyway). No lookup table needed.
- **Why it matters**: showing users "Large deflection" when the log actually says "Star lost - mass changed" is a direct credibility hit for a tool whose value proposition is interpretation.

### 11.3 Time column semantics

- **Prior spec**: did not call out that `Time` is elapsed seconds from section start.
- **Corrected**: explicitly documented that Time is elapsed seconds, wall-clock is `section.start + Time`. Verified against the ASIAIR log: section starts at 19:35:40, frame 13 Time=13.865 → wall-clock 19:35:53.865, section ends at 19:35:54 (0.135 s later). Tracks.
- **Why it matters**: code or diagnostics assuming Time is wall-clock epoch would produce nonsense. Called out explicitly now.

### 11.4 Mount column values

- **Prior spec**: implied `Mount` or `AO` for normal frames.
- **Corrected**: real values are `"Mount"`, `"AO"`, and `"DROP"` (always quoted), per the wiki and confirmed in the ASIAIR log. `DROP` means frame rejected — always co-occurs with ErrorCode ≠ 0 and with all positional fields empty. Analyzer must treat DROP frames as "no measurement" rather than zero.
- **Why it matters**: coercing empty fields to zero on DROP frames corrupts RMS calculations and creates phantom ideal-guiding periods on charts.

### 11.5 Worm period seed data

- **Prior spec values (wrong)**:
  - Celestron AVX: 480s
  - Sky-Watcher EQ6-R Pro: 638s
  - iOptron CEM26/40: 638.4s (lumped together)
  - iOptron CEM70: 400s
  - "AM5: not applicable — harmonic mount"
- **Corrected from the [PHD2 Mount Worm Period wiki](https://github.com/OpenPHDGuiding/phd2/wiki/Mount-Worm-Period-Info)** (authoritative, community-curated):
  - Celestron AVX: **594s**
  - Sky-Watcher EQ6-R Pro (2017): **479s**
  - iOptron CEM26, GEM28: **600s**
  - iOptron CEM40, GEM45: **400s**
  - iOptron CEM70: **348s**
  - AM5 and other harmonic mounts: confirmed no worm period.
- **Why it matters**: a worm-period FFT diagnostic that marks the wrong period is actively misleading. See also the memory note about "verify field mappings via web search" — this was exactly the kind of miss that's expected to never happen again. Seed data must be entered **verbatim from the wiki**, not from Claude's recollection, every time.

### 11.6 INFO event patterns

- **Prior spec patterns (wrong)**: `INFO: DITHER by X, Y`, `INFO: Settling started`, `INFO: Settling complete`, `INFO: Alert: Star lost`, etc.
- **Corrected (from real ASIAIR log)**: the actual patterns are `INFO: SETTLING STATE CHANGE, Settling started`, `INFO: SETTLING STATE CHANGE, Settling complete`, `INFO: SET LOCK POSITION, new lock pos = X, Y`, and `INFO: DITHER by DX, DY, new lock pos = X, Y`. The `SETTLING STATE CHANGE` prefix would cause a prefix-exact matcher to miss the settle events entirely. Parser must use string-contains / regex matching, not exact-line matching.
- **Why it matters**: settle detection is the foundation of the auto-exclusion feature (§5.5, §3.6). Missing settle events means stats include post-dither bounces, which silently inflates RMS.

### 11.7 Calibration section substructure

- **Prior spec**: treated calibration as a flat sequence of steps.
- **Corrected**: real calibration has 5 named phases (West, East, Backlash, North, South) with two `X calibration complete. Angle = ..., Rate = ...` prose lines embedded between phases carrying the derived calibration geometry. The analyzer should parse these phase boundaries and derived values into a structured calibration model, not treat them as generic text.
- **Why it matters**: the calibration plot (§5.3) is much more useful when phases are distinguished, and the derived angle/rate values are the primary calibration diagnostics.

### 11.8 Section header line format

- **Prior spec**: implied one `key = value` per line.
- **Corrected**: real PHD2 packs multiple settings onto single lines with inconsistent separators (commas, bare spaces) and empty values. Parser must regex-match known keys rather than split lines.

### 11.9 PA error formula coefficient

- **Prior spec**: `PA_arcmin ≈ dec_drift_arcsec_per_hour / 15.04 / cos(dec)`.
- **Corrected**: correct coefficient is ~15.7 (derived from sidereal rate 15.04 arcsec/sec × 3600 s/hour ÷ 3437.7 arcmin-per-radian ≈ 15.75 arcsec/hour per arcmin of PA error at Dec 0). The ~5% error in the prior formula would bias PA estimates low. References: [CelestialWonders drift alignment](http://www.celestialwonders.com/articles/polaralignment/MeasuringAlignmentError.html), [Starry Nights polar alignment](http://www.starrynights.us/Articles/Polar_Align.htm).

### 11.10 Locale bug detection heuristic

- **Prior spec**: "if first data row has ~2× expected column count, assume locale."
- **Corrected**: locale-corrupted rows have `declared_columns + number_of_float_columns` tokens, not `2 × declared_columns`. For a typical 18-column guiding row with ~8 float fields, a locale-corrupted row has ~26 tokens, not ~36. Better rule: T > C × 1.3. Verified by walking a [known locale-bug report](https://groups.google.com/g/open-phd-guiding/c/D_IkgJ3GuO8) field-by-field.

### 11.11 PHD2 application version may be missing

- **Prior spec**: assumed first line is `PHD2 version <X>, Log version <Y>. ...`.
- **Corrected**: ASIAIR-bundled PHD2 writes `PHD2 version, Log version 2.5. ...` — the app version is empty. Parser must tolerate a blank PHD2 version and still capture Log version. Content-sniffing on `starts with "PHD2 version"` still works.

### 11.12 Section end marker is optional

- **Prior spec**: assumed `Guiding Ends at ...` closes every guiding section.
- **Corrected**: final sections often have no explicit end — the file just ends. Parser must handle EOF as a valid section terminator.

---

## 12. References

**Authoritative PHD2 references**

- [PHD2 Guide Log format wiki](https://github.com/OpenPHDGuiding/phd2/wiki/PHD2GuideLog) — canonical column definitions
- [PHD2 Troubleshooting and Analysis manual](https://openphdguiding.org/man/Trouble_shooting.htm) — field semantics with prose explanation
- [PHD2 User Guide v2.6.14](https://openphdguiding.org/PHD2_User_Guide.pdf) — feature descriptions including Guiding Assistant
- [PHD2 Advanced Settings](https://openphdguiding.org/man/Advanced_settings.htm) — algorithm parameters that appear in section headers
- [PHD2 Mount Worm Period Info wiki](https://github.com/OpenPHDGuiding/phd2/wiki/Mount-Worm-Period-Info) — authoritative mount worm periods (community-curated)
- [PHD2 Event Monitoring interface wiki](https://github.com/OpenPHDGuiding/phd2/wiki/EventMonitoring) — JSON-RPC for v5+ live monitoring
- [PHD2 GitHub repository](https://github.com/OpenPHDGuiding/phd2)

**Reference analyzers**

- [PHDLogViewer](https://adgsoftware.com/phd2utils/) (Andy Galasso) — the de facto standard tool; feature parity target for v1–v2
- [PHDLogViewer changelog](https://adgsoftware.com/phd2utils/ChangeLog.txt)
- [PHDLogViewer source](https://github.com/agalasso/phdlogview) — GPLv3 reference implementation for unguided-tracking reconstruction
- [PEMPro Log Viewer](http://www.siriusimaging.com/PEMProV3/) (Ray Gralak) — secondary reference, mount-specific worm-period annotations

**Interpretation references**

- [Analyzing PHD2 Guiding Results — Bruce Waddington](https://openphdguiding.org/Analyzing_PHD2_Guide_Logs.pdf) — the canonical community tutorial; source for most v3 diagnostic rules
- [PHD2 Glossary of Terms](https://openphdguiding.org/man-dev/Glossary.html) — RMS, backlash, PE, image scale definitions

**Drift-alignment / PA-error math**

- [Measuring Polar Axis Alignment Error — CelestialWonders](http://www.celestialwonders.com/articles/polaralignment/MeasuringAlignmentError.html)
- [Polar Drift Alignment — Starry Nights](http://www.starrynights.us/Articles/Polar_Align.htm)
- [Drift alignment equations — Canburytech](https://canburytech.net/DriftAlign/Equations.html)

**Bug / edge-case references**

- [PHD2 issue #453 — locale-decimal bug](https://github.com/OpenPHDGuiding/phd2/issues/453)
- [Open PHD Guiding forum thread on locale bug](https://groups.google.com/g/open-phd-guiding/c/D_IkgJ3GuO8)
- [Open PHD Guiding forum thread on PHDLogViewer settle exclusion behavior](https://groups.google.com/g/open-phd-guiding/c/XKGu6Q-nOvQ)

**Local validation artifact**

- `PHD2_GuideLog_2026-03-07_193345.txt` (7,668 lines, 621KB, ASIAIR-bundled PHD2, logged 2026-03-07; used to verify all format claims in §3 and all corrections in §11).
