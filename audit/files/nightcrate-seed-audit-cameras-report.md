# NightCrate seed data audit — camera.csv findings

**For:** Fred. Not part of any Claude Code handoff.
**Coverage:** all 112 rows checked by internal consistency across every column; targeted source verification on everything those checks flagged.

**There is no camera handoff file, because this pass produced no correction I can confirm.** That is a real result, not an unfinished one — the problems found in `camera.csv` are structural and semantic rather than single wrong values, and none of them can be fixed by substituting a number I have a source for. Details below.

---

## Verified correct

- **All 112 camera-to-sensor mappings resolve and are correct.** The 18 that failed a naive model-number match are ZWO/QHY megapixel naming (ASI2600 = 26MP IMX571, ASI6200 = 62MP IMX455, QHY268 = 26MP IMX571, QHY600 = 60MP IMX455, ASI2400 = 24MP IMX410), and ASI294MM/QHY294M to IMX492 mono is correct.
- **Cooling flags are fully consistent** — no row has `cooled=1` without a delta or `cooled=0` with one. Deltas cluster sensibly by manufacturer: ZWO all 35C, QHY 35/40, ToupTek 35/45, Player One 35/40.
- **HCG read noise is below LCG read noise on every row that has both.** Zero violations.
- **`hcg_threshold_gain` is never set on a non-dual-gain sensor.** Zero violations.
- **Back focus values are all standard** — 17.5mm (54 rows), 12.5mm (40), 14.5mm (1, the QHY268C SBFL case carried over from the mount-era batch). No implausible values.
- **Guide sensors**: all four Duo/Air rows point at `sensor.smartsens.sc2210_mono`, correctly mono.
- **QHY411 full well 80Ke** confirmed against QHY, matching the sensor row.

**Incidental confirmation of a batch-1 correction.** OPT's QHY411 listing describes the IMX411 as "a 66.7 mm diagonal (Type 4.2)" sensor. The corrected width of 53.36mm with the existing 40.01mm height gives a 66.7mm diagonal exactly; the seeded 54.0mm gives 67.2mm. That is independent support for the batch-1 IMX411 fix from a source I had not used when making it.

---

## Structural finding 1 — four cameras use the HCG column for a non-HCG sensor

`camera.zwo.asi1600mm_pro`, `camera.zwo.asi1600mc_pro`, `camera.qhy.qhy163m_pro` and `camera.qhy.qhy163c_pro` all carry `effective_read_noise_lcg_e=3.5` and `effective_read_noise_hcg_e=1.2`. Their sensor, `panasonic.mn34230`, is seeded `dual_gain=0` — correctly, because the MN34230 has no dual conversion gain mode. All four also leave `hcg_threshold_gain` blank, which is consistent with there being no HCG threshold to record.

So the columns are being used in two different senses across the file:

- **"LCG mode / HCG mode"** — two discrete conversion-gain states, which is what `dual_gain` and `hcg_threshold_gain` describe.
- **"read noise at low gain / at high gain"** — the ends of a continuous curve, which is what these four rows mean. The ASI1600's read noise falls smoothly from ~3.5e to ~1.2e as gain rises; there is no mode switch.

Nothing in the data distinguishes the two readings. Any code that treats `effective_read_noise_hcg_e` as "the read noise once HCG engages" will be wrong for these four rows, because HCG never engages. This is a schema semantics question, so I have changed nothing. The fix is either to define the columns as gain extremes and document that `dual_gain` is orthogonal, or to blank the HCG value on non-dual-gain rows and add a plain read-noise column.

---

## Structural finding 2 — four cameras have a sensor larger than their stated connector

A camera's connector sets the largest image circle that can reach the sensor. Comparing each row's connector against its sensor diagonal:

| seed_key | connector | thread clear aperture | sensor diagonal |
|---|---|---|---|
| `camera.qhy.qhy411m_pro` | `connector_size.m54` | ~52mm | **66.7mm** |
| `camera.zwo.asi461mm_pro` | `connector_size.m54` | ~52mm | 54.8mm |
| `camera.qhy.qhy461m_pro` | `connector_size.m54` | ~52mm | 54.8mm |
| `camera.qhy.qhy461c_pro` | `connector_size.m54` | ~52mm | 54.8mm |

The QHY411 case is not marginal — a 66.7mm image circle cannot physically pass through a 54mm outer-diameter thread. These are medium-format cameras and use larger front interfaces than M54; QHY's own adapter documentation describes M42 for small cameras and M54 for **medium** ones, with large-format bodies handled separately. I could not find the specific thread designation for the QHY411 or QHY461 front plate, so I have not proposed a value.

The three IMX461 rows at 54.8mm against ~52mm clear are tighter and could conceivably be correct with a well-designed flange, but they warrant the same check.

This matters beyond tidiness: if anything ever computes vignetting or validates an imaging train, these rows assert a physically impossible optical path.

---

## Structural finding 3 — `effective_full_well_ke` diverges hugely from the sensor row

21 rows differ from their sensor's `full_well_capacity_ke` by more than 25%. Most are legitimate and the notes explain them, but they fall into three distinct causes that the data does not distinguish:

- **Hardware revision.** The six ASI2600 rows and both QHY268 rows carry 75Ke against the sensor's 50Ke. The ASI2600MM Pro note explains this: the 2025 "P25" revision raised full well from 50Ke to 75Ke. Same silicon, better readout — so a camera-level override is the right modelling.
- **Binning mode.** `camera.zwo.asi294mm_pro` carries 66.4Ke against the IMX492's 14.0Ke, a 374% difference. The IMX492 in its binned "unlocked" mode genuinely reaches ~66Ke; 14Ke is the unbinned figure. Both are true of the same sensor at different settings.
- **Extended readout mode.** `camera.touptek.skyeye62am` at 111Ke and `atr533m` at 104.6Ke against sensor values of 51 and 50 are roughly double. These look like extended-full-well modes rather than errors, but ToupTek's figures are the largest unexplained deltas in the file and I have not sourced them.

The general point: `effective_full_well_ke` is doing at least three jobs, and a consumer cannot tell which. Worth a decision about whether the column means "this camera's headline figure" or "this camera at the sensor's native setting".

---

## Gaps — recorded, not filled

**Six non-integrated cameras have blank `back_focus_mm`:** `asi2600mm_duo`, `asi2600mc_duo`, `atr3cmos26000kma`, `atr3cmos26000kpa`, `minicam8_m`, `minicam8_c`. All six are T2-connector cameras that necessarily have a back focus figure. These are genuine omissions rather than unpublishable values, and are the most fillable gap in the file.

**Eleven integrated smart-telescope cameras have blank `back_focus_mm` and blank `connector_size_seed_key`** — Seestar S50/S30/S30 Pro/S50 Pro, DWARF mini/II, Origin, Origin Mark II, eVscope 2, eQuinox 2, Odyssey. **This is correct and should stay blank.** These have no user-accessible optical interface, so there is no back focus or connector to record.

**Other blank counts:** `weight_g` 100 of 112, `effective_peak_qe_pct` 106 of 112, `unity_gain` 90, `source_url` 101.

---

## Carried forward

`camera.player_one.apollo_mini` — a monochrome camera mapped to `sensor.sony.imx676_color`, the only mono/colour mismatch in all 112 rows. Reported under sensors; resolving it needs an IMX432 sensor row that does not exist, which falls under the separate add-models work.
