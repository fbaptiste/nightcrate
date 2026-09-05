# NightCrate seed data audit — sensor.csv findings

**For:** Fred. Not part of any Claude Code handoff.
**Companion:** `nightcrate-seed-audit-handoff-sensors.md` carries the single correction CC applies.
**Coverage:** all 41 rows checked by internal consistency; targeted source verification on every row those checks flagged.

Note: `sensor.sony.imx662_color`, `sensor.sony.imx662_mono` and `sensor.sony.imx411_mono` were corrected in batch 1 and appear in `nightcrate-seed-audit-handoff.md`, not here.

---

## Confirmed correction (1 row, 6 fields)

```
file       | seed_key                 | column                | current | correct | source URL
-----------|--------------------------|-----------------------|---------|---------|------------
sensor.csv | sensor.sony.imx676_color | pixel_size_um         | 3.76    | 2.0     | https://www.zwoastro.com/product/asi676/
sensor.csv | sensor.sony.imx676_color | sensor_width_mm       | 13.35   | 7.10    | (same)
sensor.csv | sensor.sony.imx676_color | sensor_height_mm      | 13.35   | 7.10    | (same)
sensor.csv | sensor.sony.imx676_color | full_well_capacity_ke | 50.0    | 10.55   | (same)
sensor.csv | sensor.sony.imx676_color | read_noise_e          | 1.1     | 0.56    | (same)
sensor.csv | sensor.sony.imx676_color | peak_qe_pct           | 85.0    | 83.0    | (same)
```

**This is the most serious error found in the audit so far.** The row was filled with IMX571/IMX455-family values rather than IMX676 values. The existing note admits it in writing — it describes "3.76um pixels (same as IMX571/455)" and a "1 inch" format, neither of which is true of the IMX676. ZWO's ASI676MC manual gives Type 1/1.6, 10.04mm diagonal, 2um pixels, 7.104 x 7.104mm imaging area.

The consequence is a plate-scale error that inflated the computed field by 88%: at 250mm the row produced a 184 arcmin square field against a true 98, and at 1000mm 46 against 24. Two cameras reference it.

**Method lesson.** This row passed the dimensions-equal-resolution-times-pixel-size check cleanly, because all four fields were mutually consistent — consistently wrong together. Arithmetic catches one mistyped field; it cannot catch a row filled coherently from the wrong sensor family. The checks that did catch it were diagonal-versus-optical-format plausibility and a read of the note itself.

---

## Suspects — need a source before changing (4)

| seed_key | column | seeded | issue |
|---|---|---|---|
| `sensor.sony.imx174_color` | peak_qe_pct | 77.0 | Identical to the mono row. See below. |
| `sensor.sony.imx462_color` | peak_qe_pct | 91.0 | Identical to the mono row. See below. |
| `sensor.sony.imx662_color` | peak_qe_pct | 91.0 | Identical to the mono row. See below. |
| `camera.player_one.apollo_mini` | sensor_seed_key | `sensor.sony.imx676_color` | The Apollo-M Mini is a **monochrome** camera mapped to a **colour** sensor row. The only mono/colour naming mismatch in all 112 camera rows. Player One's Apollo-M MINI is generally documented as IMX432 mono, which has no row in `sensor.csv` — so resolving this needs a new sensor row, which falls under the separate add-models work rather than this audit. |

### The identical-QE flag

A colour sensor has a Bayer matrix over the same silicon, so its peak QE is always below the mono version. Across the 14 mono/colour pairs the seed reflects this consistently — deltas of +4 to +15 points — except for three pairs where the two values are exactly equal:

| pair | mono | colour | delta |
|---|---|---|---|
| IMX174 | 77.0 | 77.0 | 0.0 |
| IMX462 | 91.0 | 91.0 | 0.0 |
| IMX662 | 91.0 | 91.0 | 0.0 |

**Caveat worth taking seriously before "fixing" these.** IMX462 and IMX662 are STARVIS sensors marketed on near-infrared sensitivity, and the widely quoted 91% figure for them is the **NIR peak**, not the visible peak. If the seed is recording peak QE wherever it falls in the spectrum, a colour row legitimately matching mono in the NIR is defensible, because the Bayer dyes are largely transparent there. The IMX174 pair has no such excuse — it is not an NIR-marketed part.

So this is really two questions: whether `peak_qe_pct` means visible peak or spectral peak (a schema/semantics decision), and only then whether these three values are wrong. I have not changed them.

---

## Verified correct

- **All 14 mono/colour pairs agree** on every field that must match between them: pixel size, both resolutions, both dimensions, ADC bit depth and dual-gain flag. Zero discrepancies.
- **`sensor.omnivision.os08b10_color`** — I suspected the 2.9um pixel size and checked it. It is correct. OmniVision's own page gives the OS08B10 as a 1/1.25" 3840 x 2160 part, and 2.9um yields a 12.78mm diagonal matching that format. My suspicion came from confusing it with the OV08B10, an unrelated 1/4" 1.12um smartphone sensor. The seeded row is right and should not be touched.
- **Diagonal-versus-format plausibility across all 41 rows** — every row except IMX676 lands on a sensible optical format for its stated dimensions.
- **ADC bit depths** — 12-bit (27 rows), 16-bit (7), 14-bit (6) are all standard. One row uses 10-bit, `sensor.sony.imx615_color`, which is unusual but that row is a gap case (see below) rather than a verified value.

---

## Gaps — recorded, not filled

**Four rows carry no `full_well_capacity_ke`, `read_noise_e` or `peak_qe_pct`:**

- `sensor.sony.imx415_color`
- `sensor.sony.imx347_color`
- `sensor.sony.imx615_color`
- `sensor.omnivision.os08b10_color`

All four are smart-telescope sensors rather than astronomy-camera parts, and the manufacturers publish video-security specifications rather than the astronomical figures the schema wants. Leaving them blank is correct.

For the OS08B10 specifically there is an independent characterisation by Cuiv (measured in SharpCap on a Seestar S50 Pro) covering QE, read noise and full well. It is measured rather than published, and its own author notes the QE curve is a proxy assumed from a paper rather than measured on the unit. If you ever want these fields populated, that is the best source available — but it is a different evidential standard from the rest of the file and should be marked as such if used.

**`source_url` is blank on 38 of 41 rows.** Unchanged from the first pass.

---

## Structural finding — `read_noise_e` holds two different quantities

Returning to the unverified read noise and full well values, I cross-referenced every sensor row against the `effective_read_noise_lcg_e` and `effective_read_noise_hcg_e` of every camera that uses it. Twenty sensors can be checked this way, and the result is unambiguous.

**Twelve dual-gain sensor rows hold the HCG (best-case) read noise. Six hold the LCG figure instead.**

| sensor | `read_noise_e` | cameras' LCG | cameras' HCG | which it matches |
|---|---|---|---|---|
| `imx571_color` | 3.30 | 3.30 | 0.70 | **LCG** |
| `imx571_mono` | 3.30 | 3.30 | 0.70–1.00 | **LCG** |
| `imx455_color` | 3.70 | 3.30–4.20 | 0.86–1.50 | **LCG** |
| `imx455_mono` | 3.70 | 3.30–4.20 | 0.86–1.50 | **LCG** |
| `imx533_color` | 3.80 | 3.40–4.46 | 1.00–1.30 | **LCG** |
| `imx533_mono` | 3.80 | 3.40–4.46 | 1.00–1.30 | **LCG** |
| `imx585` (both) | 0.70 | 6.67 | 0.70–0.90 | HCG |
| `imx461` (both) | 1.50 | 3.50 | 1.50 | HCG |
| `imx294`, `imx492` | 1.20 | 7.00–7.80 | 1.20–1.80 | HCG |
| `imx410` | 1.40 | 7.00 | 1.40 | HCG |
| `imx411` | 3.00 | 8.00 | 3.00 | HCG |
| `mn34230` (both), `sc2210`, `imx676` | — | — | — | HCG |

`imx183` matches LCG but is not part of this problem — it is a single-gain sensor, so its 1.60 is simply its only read noise.

**Why this matters more than most of the findings here.** The six affected rows are IMX571, IMX455 and IMX533 — the APS-C and full-frame sensors behind the most popular imaging cameras in the catalog, and precisely the ones any SNR, exposure-planning or AI-analysis feature would consume. Reading `read_noise_e` as "this sensor's read noise" makes the IMX571 look **4.7x noisier than it is** at the gain most people actually image at, 3.30e against 0.70e.

**Why I have not fixed it.** The obvious repair — set all dual-gain rows to their HCG value — runs into the fact that HCG read noise is a camera implementation detail, not a sensor constant. The IMX455 rows would need a value from a 0.86–1.50e spread across four cameras, and IMX571 mono spans 0.70–1.00e. There is no single correct number to write.

So this is a schema decision, and it is the same shape as the others in this audit: define whether `read_noise_e` means the LCG figure, the HCG figure, or the sensor's floor irrespective of mode — then align the rows to that definition. The evidence above tells you which rows move whichever way you decide.

The equivalent check on `full_well_capacity_ke` found no such split. Where a sensor value sits below its cameras' range the cause is explainable and documented: `imx492` at 14.0Ke is the unbinned figure against binned camera values, and `imx571` at 50Ke predates the ASI2600 P25 revision that raised it to 75Ke.

---

## Not done

**Peak QE** remains unverified on most rows. It is not reachable by the cross-reference above, because `effective_peak_qe_pct` is blank on 106 of 112 camera rows — there is nothing to compare against.

**Read noise and full well** are now covered by the cross-reference for the 20 sensors that cameras reference, which is the useful subset; the remaining 21 sensor rows have no camera in the catalog using them, so no internal check reaches them and no external source resolves the gain-point ambiguity described above.

The gain-dependence I flagged as a difficulty turned out to be the finding itself rather than an obstacle to it. A single seeded number is an approximation of a curve, and the audit's job was to establish *which point on the curve* the column holds — which the camera cross-reference answers, and the answer is that it is not consistent.
