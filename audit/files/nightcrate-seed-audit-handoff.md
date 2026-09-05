# NightCrate seed data audit — correction handoff

**For:** Claude Code
**Scope:** correcting existing seeded rows. No new models. No schema changes. No migrations.
**Status of decisions:** all decisions in this document are final. Apply exactly as written.

---

## What to do

Apply the 10 line replacements in "Corrections" below to two files:

- `backend/src/nightcrate/data/seed/sensor.csv` — 3 lines
- `backend/src/nightcrate/data/seed/telescope_configuration.csv` — 7 lines

`camera.csv`, `mount.csv`, `filter.csv` and `filter_passband.csv` are **unchanged**. Do not touch them.

Each correction gives the complete OLD line and the complete NEW line. Match on the full OLD line, replace with the full NEW line. Do not reformat, reorder columns, or rewrite any other row in these files.

### Constraints

- **No commas inside any field.** Every NEW line below has been verified to contain zero commas in field values and to parse at exactly the header's column count. If you edit any of them further, re-verify both properties before committing.
- **No migration is required.** Every change is a value change to an already-seeded field. The loader updates rows the user has not edited and skips ones they have; that is the intended behaviour. No field is being added to any table's `seeded_fields`.
- **Do not touch `is_mine`** on any row.
- Preserve the `#` comment lines and blank lines in both files exactly as they are.

### Verification after applying

1. Every row in both files parses at the header's column count.
2. Row counts unchanged: `sensor.csv` 41 data rows, `telescope_configuration.csv` 84 data rows (excluding `#` comments and blank lines).
3. For each edited sensor row, `resolution_x * pixel_size_um / 1000` is within 1% of `sensor_width_mm`, same for height.
4. Every telescope still has exactly one config with `is_native=1` and `reduction_factor=1.0`.

---

## Corrections

### `sensor.csv`

**`sensor.sony.imx411_mono`**

```
OLD: sensor.sony.imx411_mono,manufacturer.sony,IMX411 (mono),mono,3.76,14192,10640,54.0,40.0,16,80.0,3.0,90.0,,1,Sony IMX411 monochrome variant. Medium format (54x40mm — larger than IMX461) back-illuminated (BSI) CMOS sensor with 16-bit native ADC. 151 megapixels at 14192x10640. 54x40mm ~67.4mm diagonal. 3.76um pixels. Zero amp glow. Rolling shutter. Full well ~80Ke. Read noise ~3e. The largest commercially available astronomy sensor — currently only QHY offers it.,
NEW: sensor.sony.imx411_mono,manufacturer.sony,IMX411 (mono),mono,3.76,14192,10640,53.36,40.0,16,80.0,3.0,90.0,,1,Sony IMX411 monochrome variant. Medium format (53.4x40.0mm — larger than IMX461) back-illuminated (BSI) CMOS sensor with 16-bit native ADC. 151 megapixels at 14192x10640. 53.4x40.0mm ~66.7mm diagonal. 3.76um pixels. Zero amp glow. Rolling shutter. Full well ~80Ke. Read noise ~3e. The largest commercially available astronomy sensor — currently only QHY offers it.,
```

**`sensor.sony.imx662_color`**

```
OLD: sensor.sony.imx662_color,manufacturer.sony,IMX662 (color),color,2.9,1920,1080,5.6,3.2,12,38.8,0.5,91.0,RGGB,1,Sony IMX662 color. 1/2.8 inch BSI STARVIS 2 (successor to IMX290/462). 2.1MP. 12-bit ADC. Full well 38.8Ke (much larger than IMX290/462). Read noise 0.5e HCG. Dual conversion gain. Released 2022.,
NEW: sensor.sony.imx662_color,manufacturer.sony,IMX662 (color),color,2.9,1936,1096,5.6,3.2,12,38.8,0.5,91.0,RGGB,1,Sony IMX662 color. 1/2.8 inch BSI STARVIS 2 (successor to IMX290/462). 2.1MP. 12-bit ADC. Full well 38.8Ke (much larger than IMX290/462). Read noise 0.5e HCG. Dual conversion gain. Released 2022.,
```

**`sensor.sony.imx662_mono`**

```
OLD: sensor.sony.imx662_mono,manufacturer.sony,IMX662 (mono),mono,2.9,1920,1080,5.6,3.2,12,38.8,0.5,91.0,,1,Sony IMX662 monochrome. 1/2.8 inch BSI STARVIS 2. 2.1MP. 12-bit ADC. Full well 38.8Ke. Read noise 0.5e HCG. Dual conversion gain.,
NEW: sensor.sony.imx662_mono,manufacturer.sony,IMX662 (mono),mono,2.9,1936,1096,5.6,3.2,12,38.8,0.5,91.0,,1,Sony IMX662 monochrome. 1/2.8 inch BSI STARVIS 2. 2.1MP. 12-bit ADC. Full well 38.8Ke. Read noise 0.5e HCG. Dual conversion gain.,
```

### `telescope_configuration.csv`

**`telescope_configuration.skywatcher.quattro_200p.native`**

```
OLD: telescope_configuration.skywatcher.quattro_200p.native,telescope.skywatcher.quattro_200p,,Native f/3.9,,800.0,3.9,,1,Native Newtonian configuration without coma corrector; inherent coma at field edges; oversized secondary provides illumination for full-frame sensors; backfocus depends on focuser position,1.0
NEW: telescope_configuration.skywatcher.quattro_200p.native,telescope.skywatcher.quattro_200p,,Native f/4,,800.0,4.0,,1,Native Newtonian configuration without coma corrector; inherent coma at field edges; oversized secondary provides illumination for full-frame sensors; backfocus depends on focuser position,1.0
```

**`telescope_configuration.skywatcher.quattro_200p.cc`**

```
OLD: telescope_configuration.skywatcher.quattro_200p.cc,telescope.skywatcher.quattro_200p,Sky-Watcher Quattro Coma Corrector (#S20204),With Coma Corrector f/3.9,55.0,800.0,3.9,,0,1.0x coma corrector (no focal length change); FPL51 and Schott glass; inserts into 2" focuser barrel; 55mm backfocus from corrector to sensor; M48 threads on camera side; corrects coma for pinpoint stars to field edge; handles up to full-frame sensors; optimized for f/4 Quattro Newtonians,1.0
NEW: telescope_configuration.skywatcher.quattro_200p.cc,telescope.skywatcher.quattro_200p,Sky-Watcher Quattro Coma Corrector (#S20204),With Coma Corrector f/4,55.0,800.0,4.0,,0,1.0x coma corrector (no focal length change); FPL51 and Schott glass; inserts into 2" focuser barrel; 55mm backfocus from corrector to sensor; M48 threads on camera side; corrects coma for pinpoint stars to field edge; handles up to full-frame sensors; optimized for f/4 Quattro Newtonians,1.0
```

**`telescope_configuration.skywatcher.quattro_250p.native`**

```
OLD: telescope_configuration.skywatcher.quattro_250p.native,telescope.skywatcher.quattro_250p,,Native f/3.94,,1000.0,3.94,,1,Native Newtonian configuration without coma corrector; inherent coma at field edges; oversized secondary provides illumination for full-frame sensors; backfocus depends on focuser position,1.0
NEW: telescope_configuration.skywatcher.quattro_250p.native,telescope.skywatcher.quattro_250p,,Native f/4,,1000.0,4.0,,1,Native Newtonian configuration without coma corrector; inherent coma at field edges; oversized secondary provides illumination for full-frame sensors; backfocus depends on focuser position,1.0
```

**`telescope_configuration.skywatcher.quattro_250p.cc`**

```
OLD: telescope_configuration.skywatcher.quattro_250p.cc,telescope.skywatcher.quattro_250p,Sky-Watcher Quattro Coma Corrector (#S20204),With Coma Corrector f/3.94,55.0,1000.0,3.94,,0,1.0x coma corrector (no focal length change); FPL51 and Schott glass; inserts into 2" focuser barrel; 55mm backfocus from corrector to sensor; M48 threads on camera side; corrects coma for pinpoint stars to field edge; handles up to full-frame sensors; optimized for f/4 Quattro Newtonians,1.0
NEW: telescope_configuration.skywatcher.quattro_250p.cc,telescope.skywatcher.quattro_250p,Sky-Watcher Quattro Coma Corrector (#S20204),With Coma Corrector f/4,55.0,1000.0,4.0,,0,1.0x coma corrector (no focal length change); FPL51 and Schott glass; inserts into 2" focuser barrel; 55mm backfocus from corrector to sensor; M48 threads on camera side; corrects coma for pinpoint stars to field edge; handles up to full-frame sensors; optimized for f/4 Quattro Newtonians,1.0
```

**`telescope_configuration.skywatcher.quattro_300p.native`**

```
OLD: telescope_configuration.skywatcher.quattro_300p.native,telescope.skywatcher.quattro_300p,,Native f/3.93,,1200.0,3.93,,1,Native Newtonian configuration without coma corrector; inherent coma at field edges; oversized secondary provides illumination for full-frame sensors; backfocus depends on focuser position,1.0
NEW: telescope_configuration.skywatcher.quattro_300p.native,telescope.skywatcher.quattro_300p,,Native f/4,,1200.0,4.0,,1,Native Newtonian configuration without coma corrector; inherent coma at field edges; oversized secondary provides illumination for full-frame sensors; backfocus depends on focuser position,1.0
```

**`telescope_configuration.skywatcher.quattro_300p.cc`**

```
OLD: telescope_configuration.skywatcher.quattro_300p.cc,telescope.skywatcher.quattro_300p,Sky-Watcher Quattro Coma Corrector (#S20204),With Coma Corrector f/3.93,55.0,1200.0,3.93,,0,1.0x coma corrector (no focal length change); FPL51 and Schott glass; inserts into 2" focuser barrel; 55mm backfocus from corrector to sensor; M48 threads on camera side; corrects coma for pinpoint stars to field edge; handles up to full-frame sensors; optimized for f/4 Quattro Newtonians,1.0
NEW: telescope_configuration.skywatcher.quattro_300p.cc,telescope.skywatcher.quattro_300p,Sky-Watcher Quattro Coma Corrector (#S20204),With Coma Corrector f/4,55.0,1200.0,4.0,,0,1.0x coma corrector (no focal length change); FPL51 and Schott glass; inserts into 2" focuser barrel; 55mm backfocus from corrector to sensor; M48 threads on camera side; corrects coma for pinpoint stars to field edge; handles up to full-frame sensors; optimized for f/4 Quattro Newtonians,1.0
```

**`telescope_configuration.sharpstar.61edph_ii.0_8x`**

```
OLD: telescope_configuration.sharpstar.61edph_ii.0_8x,telescope.sharpstar.61edph_ii,Sharpstar 0.8x f/4.5 Reducer for 61EDPH II (included),0.8x Reducer f/4.5,55.0,275.0,4.5,44.0,0,Included 2.3" 0.8x reducer/flattener (3-element air-spaced); shortens FL to 275mm and ratio to f/4.5; 44mm full-frame image circle; M63x1 telescope-side thread and M48x0.75 camera-side thread; 55mm backfocus from M48 thread (extendable to 99mm with spacers); 360 degree rotator,0.8
NEW: telescope_configuration.sharpstar.61edph_ii.0_8x,telescope.sharpstar.61edph_ii,Sharpstar 0.8x f/4.5 Reducer for 61EDPH II (included),0.8x Reducer f/4.5,55.0,275.0,4.5,44.0,0,Included 2.3" 0.8x reducer/flattener (3-element air-spaced); shortens FL to 275mm and ratio to f/4.5; 44mm full-frame image circle; M63x1 telescope-side thread and M48x0.75 camera-side thread; 55mm backfocus from M48 thread (extendable to 99mm with spacers); 360 degree rotator,0.821
```

---

## Why each change

**`sensor.sony.imx662_color` / `sensor.sony.imx662_mono` — resolution 1920x1080 to 1936x1096.**
Sony's IMX662-AAMR flyer distinguishes active pixels (1936x1096) from recommended recording pixels (1920x1080). The row was seeded with the recording figure, but its `sensor_width_mm`/`sensor_height_mm` (5.6 x 3.2) are the values implied by 1936x1096 — so the row failed the dimensions check and was internally inconsistent. Two independent confirmations that 1936x1096 is correct: the sibling `imx462`/`imx290` rows use exactly 1936x1096 with identical 5.6 x 3.2 dimensions, and `camera.dwarflab.dwarf_mini_imager`'s own note already states the sensor "is read out at 1936x1100 and cropped to 1920x1080 by the firmware." Dimensions are left alone; only the resolution changes.
Source: https://www.sony-semicon.com/files/62/flyer_security/IMX662-AAMR_Flyer.pdf

**`sensor.sony.imx411_mono` — width 54.0 to 53.36; note corrected.**
14192 x 3.76um = 53.36mm. The height already checked out exactly (10640 x 3.76 = 40.01), which isolates the error to width. The seeded 54.0 traces to QHY's rounded marketing copy ("sensor size is 54 mm x 40 mm"); FLI publishes the imaging area as 53.4 x 40mm for the same sensor and Sony gives the diagonal as 66.7mm (Type 4.2). The note carried the same wrong figures — "54x40mm" twice and a "~67.4mm diagonal" that matched neither the old nor the new width — so it is corrected in the same edit.
Source: https://www.sony-semicon.com/files/62/flyer_industry/IMX411AQR_Flyer.pdf

**Six Sky-Watcher Quattro configs — focal ratio to 4.0, `config_name` follows.**
The apertures (205/254/305mm) are correct — Sky-Watcher publishes those figures in their own product URLs, and I confirmed them before concluding otherwise. What is wrong is that these rows store the *computed* ratio (800/205 = 3.90) where Sky-Watcher publishes a flat f/4. That inverts the catalog's rule of keeping the manufacturer's published ratio where it disagrees by rounding. The file's own convention supports the fix: `edgehd_1100` stores 10.0 against a computed 10.02, and `rasa_8` stores 2.0 against a computed 1.97. The three Quattros were the only rows breaking it. Both the `.native` and `.cc` config of each scope are affected — the coma corrector is 1.0x and does not change the ratio. `config_name` is display text that would otherwise contradict the corrected value, so it changes with it.
Sources: https://www.skywatcherusa.com/products/sky-watcher-quattro-200p-imaging-newtonian-8-205-mm / https://www.skywatcherusa.com/products/sky-watcher-quattro-250p-imaging-newtonian-10-254-mm / https://www.skywatcherusa.com/products/sky-watcher-quattro-300p-imaging-newtonian-12-305-mm

**`telescope_configuration.sharpstar.61edph_ii.0_8x` — `reduction_factor` 0.8 to 0.821.**
Sharpstar's own site confirms 335mm native reducing to 275mm at f/4.5, so the focal length is right and "0.8x" is the product name rather than the true ratio (275/335 = 0.821). Every other config row in the file is self-consistent to FL/native within 1.5%; this was the only outlier. `accessory_name` and `config_name` keep "0.8x" because that is the product's actual name.
Source: https://www.sharpstar-optics.com/Products_1/18.html

---

## Explicitly not changed

Do not "fix" any of these. Each was examined and the current data is correct or deliberate.

- **`sensor.sony.imx347_color` stays at 2048x1536.** These are the eVscope 2 / eQuinox 2 readout window, not the IMX347 part spec (which is 2688x1520). The row's note already documents this in full. The window reproduces Unistellar's published 45.6 x 34.2 arcmin field at 450mm to within 0.5%, and `camera.csv` has no columns to express a crop, so correcting the row to the true sensor would break the one thing it currently gets right. Revisit only if camera gains crop columns.
- **`filter.antlia.triband_rgb_ultra_ii` and `filter.antlia.quad_band_alp` stay `filter_type.light_pollution` with no passband rows.** Both are broadband multi-bandpass filters — the Quad Band covers 390-1000nm continuum and the Triband is documented as passing balanced RGB and substituting for a luminance filter. Accumulating per-line integration hours through glass that also passes the full continuum is the exact failure the no-passband rule exists to prevent.
- **`camera.qhy.qhy268c` stays at 14.5mm back focus.** See open questions below.
- **Unistellar Odyssey / Odyssey Pro stay at f/3.9** against a computed 3.76. Manufacturer's published ratio wins.
- All 83 `filter_passband` rows, all 112 camera-to-sensor mappings, and all 24 mount worm periods were checked and are correct.

---

## If you find anything else

This document is the complete set of changes. If you believe another row is wrong, or that one of these corrections is mistaken, **stop and report it — do not act on it.** Unverified values must not enter these files; they load into a live database on startup. Sourcing new values is out of scope for this task.
