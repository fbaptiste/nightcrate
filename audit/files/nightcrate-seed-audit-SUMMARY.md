# NightCrate seed data audit — summary

**Status:** all six target files audited. Every deterministic check is complete across every row. Source verification is complete for everything those checks flagged, and partial for fields that no consistency check can reach.

---

## The files

| Handoff (for Claude Code) | Applies to | Corrections |
|---|---|---|
| `nightcrate-seed-audit-handoff.md` | sensor.csv (3 rows), telescope_configuration.csv (7 rows) | 10 |
| `nightcrate-seed-audit-handoff-mounts.md` | mount.csv | 4 |
| `nightcrate-seed-audit-handoff-sensors.md` | sensor.csv (1 row, 6 fields) | 1 |
| `nightcrate-seed-audit-handoff-telescopes.md` | telescope_configuration.csv | 1 |

All four are independent and can be applied in any order. **16 line replacements in total.** No file gets conflicting edits: the two that both touch `telescope_configuration.csv` address different rows.

| Report (for Fred) | Covers |
|---|---|
| `nightcrate-seed-audit-report.md` | batch 1 — sensors and configurations |
| `nightcrate-seed-audit-mounts-report.md` | mount.csv |
| `nightcrate-seed-audit-sensors-report.md` | sensor.csv |
| `nightcrate-seed-audit-cameras-report.md` | camera.csv |
| `nightcrate-seed-audit-telescopes-report.md` | telescope.csv and telescope_configuration.csv |
| `nightcrate-seed-audit-filters-report.md` | filter.csv and filter_passband.csv |

---

## The three findings that matter most

**1. `sensor.sony.imx676_color` was filled from the wrong sensor family.** Six fields wrong. The seeded 3.76um pixel size inflated the computed field of view by 88%. It passed the dimensions-equal-resolution-times-pixel-size check cleanly because all four fields were consistently wrong together — arithmetic catches one mistyped field, never a coherently wrong row. Fixed in the sensors handoff.

**2. `payload_capacity_kg` holds three incompatible conventions.** Instrument-only for most rows; without-counterweights for harmonic mounts that carry far more with them; and total-including-counterweights for `iexos100_2`. Several manufacturers also publish separate visual and photographic ratings and the seed takes different ones. The same 8 kg reading means materially different things across rows. Not fixed — it is a schema question.

**3. Four columns have unstated meanings and are inconsistently applied.** `sensor.read_noise_e` is the newest and best-evidenced: proven by camera cross-reference to hold LCG on six rows and HCG on twelve. The others: `effective_read_noise_hcg_e` (four cameras use it for a sensor with no HCG mode), `filter_passband` rows (physical bands in one place, emission lines in another), and `peak_qe_pct` (visible peak or spectral peak — the answer decides whether three identical mono/colour pairs are errors). Each needs a definition, not a value change.

---

## Structural health

Everything below is complete, not sampled.

- **CSV integrity is sound.** All seven files parse at their header width, row counts match the brief exactly, no field contains a stray comma. The 19-row telescope corruption described in the brief is fixed — `source_url` is populated on all 51 telescope rows.
- **Referential integrity is perfect.** Every camera-to-sensor, passband-to-filter and config-to-telescope key resolves. No orphans.
- **Closed vocabularies are respected everywhere.** No invented values in `sensor_type`, `bayer_pattern`, `line_name`, `drive_type` or `filter_type_seed_key`.
- **Rule compliance holds.** Every telescope has exactly one native config at `reduction_factor=1.0`; all 13 blocking filters carry zero passbands; no cooled/delta mismatch; HCG read noise is below LCG on every row that has both.

---

## Checks I ran, then discarded

Recorded because each looks reasonable and will be re-derived by someone otherwise.

- **Image circle scaled by reduction factor.** Flags four EdgeHD rows. Invalid — a designed reducer/corrector's illuminated field comes from its own optics, and Celestron's 0.7x preserves full-frame coverage rather than shrinking it.
- **Payload-to-weight comparison across a manufacturer's range.** Must be restricted to a single drive type. Harmonic mounts run 2.00–4.09 payload-to-weight, worm mounts 0.95–4.17; comparing across them is meaningless and produces three false positives.
- **Camera model number versus sensor part number.** Flags 18 rows, all correct — ZWO and QHY name by megapixel count, not sensor part.
- **Aperture versus the number in the telescope's model name.** Flags five rows, all correct — the Askar FRA300 and FRA400 are named for focal length, and Sky-Watcher publish the Quattros at 205/254/305mm against their nominal names.
- **Visible-light range applied to an "R+" band.** Flagged the Antlia Dark Red+ at 850nm; the filter is deliberately near-infrared, running 700–1000nm, and the row is correct.

---

## What is genuinely unfinished

- **`mount_weight_kg`** — 16 remaining suspects, after a further pass resolved three more rows (one correction, two flags cleared in favour of the seed). I went back to this field with direct page fetches rather than search and resolved one more (CQ350 Pro). The rest are **not resolvable by web search**: Sky-Watcher's spec tables are JavaScript-rendered and absent from the served HTML, and Celestron/iOptron weight queries match counterweight products instead of spec tables. They need per-model PDF manuals or a scale. I have stopped searching them rather than generate noise.
- **`mount.msm.nomad` and `mount.mlastro.one`** — no usable source found for either field.
- **Sensor read noise** — now resolved as a *finding* rather than a gap. Cross-referencing every sensor against the cameras that use it shows `read_noise_e` holds the HCG figure on 12 dual-gain rows and the **LCG** figure on 6 (IMX571, IMX455, IMX533 — the most popular imaging sensors in the catalog). Reading it as "the sensor's read noise" makes an IMX571 look 4.7x noisier than it is. Not fixable by value substitution, because HCG read noise varies by camera; it needs the column defined. See the sensors report.
- **Sensor peak QE** — unverifiable by cross-reference, because `effective_peak_qe_pct` is blank on 106 of 112 camera rows. No internal check reaches it.
- **Filter peak transmission** — partially closed. The 16 blanks turn out to be mostly appropriate (13 are blocking or smart-telescope filters where a single peak figure is not meaningful). One genuine suspect emerged: all eight Antlia 3nm Pro rows are seeded at 90%, while Antlia's own site states 88% for the OIII. Left alone deliberately — fixing only OIII would leave one sourced value beside two unsourced ones. `filter.optolong.nd_3_0` is a separate small schema question: an OD 3.0 filter transmits exactly 0.1%, which is not unpublished but may be outside the column's intended scope.
- **Camera back focus** on six T2 cameras where a value must exist (`asi2600mm_duo`, `asi2600mc_duo`, `atr3cmos26000kma`, `atr3cmos26000kpa`, `minicam8_m`, `minicam8_c`).
- **Reducer back focus** on eight non-native configs. Deliberately not guessed — 55mm is common but the Evostar 80/100/120 reducers are a different design from the 72ED unit.
- **`obstruction_pct`** on 16 telescopes that genuinely have a central obstruction.
- **`periodic_error_arcsec`** — blank on all 56 mounts.
- **`source_url`** — blank on 74/80 filters, 101/112 cameras, 54/56 mounts, 38/41 sensors. Complete only on telescope.csv.

---

## Corrections I made to my own earlier reports

- Told you the IMX347 window decision was undocumented. **Wrong** — the note documents it fully, including the derivation from Unistellar's published field.
- Recommended re-typing two Antlia filters as narrowband. **Reversed** — they are broadband multi-bandpass filters and the current typing is right.
- Listed Sky-Watcher EQ6-R Pro weight as verified at 17 kg. **Downgraded to suspect** — Agena gives 36 lb, which is 16.3 kg.
- Suspected the OS08B10 pixel size. **Cleared** — I had confused it with the OV08B10, an unrelated smartphone sensor.
- Stated coverage of 47 mount rows. **Recounted to 45** against the row dump.
