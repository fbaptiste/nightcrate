# NightCrate — column semantics: recommendations and migration spec

**For:** Claude Code, after Fred signs off.
**Origin:** the seed data audit. Five columns hold values whose meaning is not defined and is not consistent across rows. These are not bad values — every row is well-formed and most are individually correct. The problem is that a consumer of the column cannot tell which of two or three meanings a given row used.

**Relationship to the correction handoffs:** independent. The four correction handoffs (`nightcrate-seed-audit-handoff*.md`, 16 line replacements) change values within the current schema and can be applied before or after this work. Nothing here depends on them.

---

## Read this first — the hash contract

Everything in this document adds or renames fields, which is a different risk class from the value corrections.

From the audit brief: **changing a seeded field's value changes its hash, and the loader handles that safely — it updates rows the user has not edited and skips ones they have. But adding a new field to a table's `seeded_fields` requires a migration that backfills it, or every existing row is treated as user-modified and skipped forever.**

So each change below needs a migration that both adds the column *and* populates it for every existing seeded row, in the same migration. A migration that adds a nullable column and leaves the backfill to the next loader run will permanently orphan the existing rows.

Item 5 is also destructive in one direction: it invalidates values that are currently present and plausible-looking. Read its "consequence" section before running it.

---

## 1. `sensor.read_noise_e` — split into two columns

### The problem

CMOS sensors with dual conversion gain have two read-noise figures. An IMX571 reads about 3.3e in low-gain mode and about 0.7e in high-gain mode — a factor of nearly five on the same silicon. The table has one column, so each row's author had to pick one, and they did not pick the same one.

Cross-referencing every sensor row against the `effective_read_noise_lcg_e` and `effective_read_noise_hcg_e` of every camera that uses it gives an unambiguous split. **Six dual-gain rows hold the low-gain figure; ten hold the high-gain figure.**

There is a second, sharper problem. `full_well_capacity_ke` holds the **low-gain** figure — 50Ke for the IMX571. If `read_noise_e` on the same row holds the high-gain 0.7e, then the two fields describe states the sensor cannot occupy simultaneously. Computing dynamic range from them gives 50000 / 0.7 ≈ 16.1 stops, which is impossible on a 16-bit sensor; the true figure is about 14.5. **A single row can already produce a fictitious number by combining the fields it has today.** That is the strongest argument for splitting.

### Recommendation

Replace `read_noise_e` with `read_noise_low_gain_e` and `read_noise_high_gain_e`. This mirrors the pattern `camera.csv` already uses, so nothing new is invented.

### Backfill — complete classification of all 41 rows

**Six rows: current value is the LOW gain figure.** Move to `read_noise_low_gain_e`. Leave `read_noise_high_gain_e` blank — do **not** derive it from the camera rows, because high-gain read noise is a camera implementation detail and the cameras disagree (IMX455 spans 0.86–1.50e across four cameras).

```
sensor.sony.imx455_color   3.7      sensor.sony.imx533_color   3.8      sensor.sony.imx571_color   3.3
sensor.sony.imx455_mono    3.7      sensor.sony.imx533_mono    3.8      sensor.sony.imx571_mono    3.3
```

**Ten rows: current value is the HIGH gain figure.** Move to `read_noise_high_gain_e`, leave low blank.

```
sensor.smartsens.sc2210_mono 0.6   sensor.sony.imx410_color 1.4   sensor.sony.imx461_color 1.5   sensor.sony.imx492_mono 1.2   sensor.sony.imx585_mono 0.7
sensor.sony.imx294_color     1.2   sensor.sony.imx411_mono  3.0   sensor.sony.imx461_mono  1.5   sensor.sony.imx585_color 0.7   sensor.sony.imx676_color 1.1
```

**Five rows: dual-gain, but no camera records a read noise, so the split is undetermined by cross-reference.** All five are seeded 0.5e. That is a high-gain figure — no dual-gain STARVIS 2 sensor reads at 0.5e in low gain — so put it in `read_noise_high_gain_e`, but flag these for confirmation rather than treating them as verified.

```
sensor.sony.imx662_color   sensor.sony.imx678_color   sensor.sony.imx715_color
sensor.sony.imx662_mono    sensor.sony.imx678_mono
```

**Sixteen rows: single-gain sensors (`dual_gain=0`).** There is only one read noise. Put the value in `read_noise_high_gain_e` and leave low blank, or add a third plain column — see the note under item 3, which affects this choice.

```
onsemi.ar0130_color/mono   panasonic.mn34230_color/mono   sony.imx174_color/mono   sony.imx178_color/mono
sony.imx183_color/mono     sony.imx290_color/mono         sony.imx462_color/mono   sony.imx464_color   sony.imx485_color
```

**Four rows have no read noise at all** and stay blank: `omnivision.os08b10_color`, `sony.imx347_color`, `sony.imx415_color`, `sony.imx615_color`. These are smart-telescope sensors whose makers publish video-security specs; blank is correct.

### Also worth doing

`full_well_capacity_ke` has the mirror-image ambiguity — it is the low-gain figure on the rows checked, but nothing says so. At minimum document it. If splitting it too is cheap while the migration is open, that closes the dynamic-range problem completely.

**Confidence: high.** Do this one first.

---

## 2. `payload_capacity_kg` — one convention, plus a second column

### The problem

Three conventions are in use and nothing distinguishes them:

1. **Instrument only, counterweights excluded** — most rows. Celestron state this explicitly; Sky-Watcher, Losmandy, Software Bisque and 10Micron follow it.
2. **Without counterweights, on a harmonic mount that carries more with them** — all five ZWO rows, plus Rainbow Astro, iOptron's HEM/HAE range, MLAstro. Conservative and self-consistent, but each has a substantially higher counterweighted rating: AM3 13, AM3N 13, AM5N 20, AM7 30, RST-300 50 kg.
3. **Total including counterweights** — `mount.explore_scientific.iexos100_2`. ES rate the iEXOS-100 at 19 lb *total*, explicitly counting tube, accessories, camera **and counterweights**. The seeded 8.6 kg is that figure.

A fourth wrinkle sits on top: several makers publish separate **visual** and **photographic** ratings that differ widely. Vixen SXD2 is 15 kg photographic against a 50 lb visual maximum; Explore Scientific EXOS-2 is 28 lb photographic against 40 lb visual.

The practical effect: the same 8 kg reading means "8 kg of telescope, counterweights on top" for a Celestron and "8 kg of telescope *and* counterweights combined" for the iEXOS-100-2 — roughly half the usable capacity the number implies.

### Recommendation

Define `payload_capacity_kg` as **maximum instrument payload excluding counterweights; the photographic rating where a manufacturer publishes separate visual and photographic figures.**

Photographic over visual because NightCrate is an imaging application — a mount that is fine visually at 20 kg may guide badly at 12.

Add `payload_capacity_with_cw_kg`, nullable, for the harmonic mounts. Known values to seed: AM3 13, AM3N 13, AM5N 20, AM7 30, RST-300 50, HEM27 20, HAE43 25.

### The row this does not solve

`mount.explore_scientific.iexos100_2`. ES publish only the 19 lb counterweight-inclusive total, so there is no instrument-only figure to convert to. **Leave the value and add an explicit note** rather than deriving one. Flag it in the UI if rig suitability ever surfaces payload, because an optimistic payload figure is the failure mode that damages equipment, and this is the row most likely to mislead.

**Confidence: high on the convention. Medium on the iEXOS row — it may warrant a nullable `payload_convention` marker instead.**

---

## 3. `camera.effective_read_noise_hcg_e` — rename, change no data

### The problem

Four cameras — `zwo.asi1600mm_pro`, `zwo.asi1600mc_pro`, `qhy.qhy163m_pro`, `qhy.qhy163c_pro` — carry `lcg=3.5` and `hcg=1.2`. Their sensor is the Panasonic MN34230, which has no dual conversion gain and is correctly seeded `dual_gain=0`. All four leave `hcg_threshold_gain` blank, because there is no threshold.

Those rows mean "read noise at low gain versus at high gain" — two ends of a smooth curve. The rest of the file means "read noise in LCG mode versus HCG mode" — two discrete hardware states. Code reading `effective_read_noise_hcg_e` as "the read noise once HCG engages" is wrong for these four, because it never engages.

### Recommendation

If item 1 is done as described, this dissolves. Rename the camera columns to `read_noise_low_gain_e` and `read_noise_high_gain_e` — describing **gain**, not **mode**. The four rows become correct as written: 3.5e at low gain and 1.2e at high gain is exactly true of the MN34230.

Whether a discrete conversion-gain switch exists is already captured by `dual_gain` and `hcg_threshold_gain`, which is where it belongs.

**Zero rows change. Rename plus a docstring.** This also settles the single-gain question in item 1's backfill: under gain-based naming, a single-gain sensor's value sits in `read_noise_high_gain_e` without needing a third column.

**Confidence: high.** Cheapest item here, and it only works if item 1 uses the same naming — treat the two as one change.

---

## 4. `filter_passband` — a row is one emission line

### The problem

`filter.optolong.l_enhance` is typed `filter_type.narrowband_tri`, defined in `filter_type.csv` as "three emission lines". It has **two** passband rows. It is the only row in the file where type and passband count disagree.

Both descriptions are true. The L-eNhance passes Ha, Hb and OIII — three lines — through two physical windows: a narrow ~10nm Ha window, and a wide ~24nm window covering Hb and OIII together. The type counted lines; the passband rows recorded windows.

Consequences on the two features passbands exist for:

- **Per-line integration budgets.** Hb has no row, so hours through an L-eNhance never accumulate against Hb even though the filter passes it.
- **Moon sensitivity.** The wide window is recorded as OIII at 24nm. OIII sits at 501nm where moonlight peaks and Rayleigh scattering is strongest, so the width is doing real work and is correctly captured — but the Hb inside that same window is invisible to the model.

### Recommendation

Define a `filter_passband` row as **one emission line the filter usefully passes**, not one physical window. Both consumers are line-oriented; window count feeds nothing.

Add the missing Hb row to the L-eNhance: `central_wavelength_nm` 486.1, `bandwidth_nm` 24.0 (it shares the OIII window), `line_name` `Hb`.

### Watch for

Two rows sharing a physical window means the bandwidth is recorded twice. That is correct input for moon scattering, which cares how much continuum the window admits around each line. **Make sure nothing sums `bandwidth_nm` across rows as though the windows were independent** — that would double-count this filter.

**Confidence: high on the definition. One row to add today.**

---

## 5. `sensor.peak_qe_pct` — define as peak within 400–700nm

### The problem

Quantum efficiency varies with wavelength, so "peak QE" must say peak *where*.

Across the fourteen mono/colour pairs, mono normally exceeds colour by 4–15 points, because the Bayer dye array costs light. Three pairs are exactly equal:

| pair | mono | colour |
|---|---|---|
| IMX174 | 77.0 | 77.0 |
| IMX462 | 91.0 | 91.0 |
| IMX662 | 91.0 | 91.0 |

For IMX462 and IMX662 that may be correct. Both are STARVIS parts marketed on near-infrared sensitivity and their widely quoted 91% is the **NIR** peak. Bayer dyes are largely transparent in the NIR, so colour genuinely can match mono there. Under a "highest QE anywhere in the response curve" reading, those two pairs are right. Under a visible-light reading they are wrong.

IMX174 has no such defence — it is not an NIR-marketed part — so that pair is suspect under either definition.

### Recommendation

Define `peak_qe_pct` as **peak QE within 400–700nm**. NightCrate is a deep-sky imaging application; visible-band response is what determines exposure, and a NIR peak answers a question no deep-sky imager is asking while making mono-versus-colour comparison meaningless.

Add `peak_qe_wavelength_nm` so the figure carries its own context and this cannot recur.

### Consequence — read before running

This **invalidates currently-present, plausible-looking values**. `sensor.sony.imx462_color` and `sensor.sony.imx662_color` both need re-sourcing to a visible-band figure; their 91% becomes wrong by definition. Do not leave the old value in place under the new definition. Either blank them pending a source, or source them in the same change. `sensor.sony.imx174_color` needs checking regardless.

### Where Fred should overrule me

**If you expect NightCrate to be used for planetary or IR-pass work**, the spectral peak is the more useful number and this recommendation inverts — define it as spectral peak, and make `peak_qe_wavelength_nm` mandatory rather than optional so the band is always explicit. This is the one item here that turns on intended use rather than on the data, and it is the reason I did not change these three rows during the audit: the same values are correct under one definition and wrong under the other.

**Confidence: medium-high, conditional on the above.**

---

## Suggested order

1. **Items 1 and 3 together** — same rename, one migration, and item 1 fixes an actively wrong dynamic-range calculation.
2. **Item 2** — rig suitability is a shipped feature reading a column with three meanings.
3. **Item 4** — one row; can ride along with any filter work.
4. **Item 5** — last, and only after Fred has answered the planetary/IR question above.

---

## What not to do

- **Do not add any of these columns without backfilling in the same migration.** See the hash contract at the top.
- **Do not derive `read_noise_high_gain_e` for the six LCG rows from the camera rows.** The cameras disagree; it is a camera property, not a sensor constant.
- **Do not carry the existing `peak_qe_pct` values forward unchanged into a visible-band definition** for the two NIR sensors — that silently converts a correct value into a wrong one.
- **Do not sum `bandwidth_nm` across passband rows** once the L-eNhance has two rows sharing one window.
- If any of these recommendations looks wrong once you are in the codebase, **stop and report rather than adapting.** These are product decisions Fred has signed off, not implementation details.
