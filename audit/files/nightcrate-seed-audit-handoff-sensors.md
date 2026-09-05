# NightCrate seed data audit — correction handoff (sensors, batch 3)

**For:** Claude Code
**Scope:** correcting one existing seeded row in `sensor.csv`. No new models. No schema changes. No migrations.
**Status of decisions:** final. Apply exactly as written.

Self-contained and independent of the other handoffs. Apply in any order.

---

## What to do

Apply the single line replacement below to `backend/src/nightcrate/data/seed/sensor.csv`.

Match on the full OLD line, replace with the full NEW line. Do not reformat, reorder columns, or rewrite any other row.

### Constraints

- **No commas inside any field.** The NEW line is verified to contain zero commas in field values and to parse at exactly the header's 17-column width.
- **No migration required.** All changes are value changes to already-seeded fields.
- **Do not touch `is_mine`.**
- Preserve `#` comment lines and blank lines exactly.

### Verification after applying

1. Every row in `sensor.csv` parses at 17 columns; 41 data rows excluding comments and blanks.
2. For this row: `resolution_x * pixel_size_um / 1000` equals `sensor_width_mm` within 1% (3552 x 2.0 / 1000 = 7.104 against 7.10).

---

## Correction

### `sensor.csv`

**`sensor.sony.imx676_color`** — six fields plus notes and source_url

```
OLD: sensor.sony.imx676_color,manufacturer.sony,IMX676 (color),color,3.76,3552,3552,13.35,13.35,12,50.0,1.1,85.0,RGGB,1,Sony IMX676 color. 1 inch BSI STARVIS 2. ~12.6MP at 3552x3552 (square format). 3.76um pixels (same as IMX571/455). 18.87mm diagonal. Released ~2023. Zero amp glow. Dual conversion gain. Full well ~50Ke. Read noise ~1.1e HCG. Modern replacement for IMX183 with better QE larger full well and zero amp glow. Limited vendor adoption so far.,
NEW: sensor.sony.imx676_color,manufacturer.sony,IMX676 (color),color,2.0,3552,3552,7.10,7.10,12,10.55,0.56,83.0,RGGB,1,Sony IMX676 color. STARVIS 2 back-illuminated square sensor. Type 1/1.6 with a 10.04mm diagonal. 12.61MP at 3552x3552. 2um pixels giving a 7.104 x 7.104mm imaging area. 12-bit ADC. Full well 10.55Ke. Read noise 0.56e in HCG mode. Peak QE 83%. Dual conversion gain with HCG engaging at gain 180. No amp glow.,https://www.zwoastro.com/product/asi676/
```

**Why:** the row was populated with IMX571/IMX455-family values rather than IMX676 values — the existing note says so outright, describing "3.76um pixels (same as IMX571/455)" and a "1 inch" format. ZWO's ASI676MC product manual gives the actual part: Type 1/1.6, 10.04mm diagonal, 3552x3552 at **2um**, imaging area **7.104 x 7.104mm**, full well **10.55Ke**, read noise **0.56e**, peak QE **83%**, 12-bit ADC. The seeded 12-bit ADC and RGGB pattern were already correct and are unchanged.

**Why it matters:** pixel size drives plate scale, so the seeded value inflated the computed field by 88%. At 250mm the row gave a 184 arcmin square field where the truth is 98; at 1000mm it gave 46 arcmin against 24. Two cameras reference this sensor — `camera.qhy.qhy5iii676c` and `camera.player_one.apollo_mini` — and both were affected.

**Why the arithmetic check did not catch it:** pixel size, resolution and both dimensions were mutually consistent. They were consistently wrong together. Dimension-versus-resolution arithmetic catches a single mistyped field; it cannot catch a row filled coherently from the wrong sensor family. That is a limit of the method worth knowing.

Source: https://www.zwoastro.com/product/asi676/

---

## If you find anything else

This document is the complete set of changes. If you believe another row is wrong, or that this correction is mistaken, **stop and report it — do not act on it.** Unverified values must not enter these files; they load into a live database on startup. Sourcing new values is out of scope.
