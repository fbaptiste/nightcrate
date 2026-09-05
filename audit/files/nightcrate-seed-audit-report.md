# NightCrate seed data audit — findings report

**For:** Fred. Not part of the Claude Code handoff.
**Companion:** `nightcrate-seed-audit-handoff.md` carries the 10 corrections CC applies.

---

## Corrections handed to CC

Summarised here for the record; the handoff document has the full OLD/NEW lines.

```
file                        | seed_key                                  | column                | current | correct
----------------------------|-------------------------------------------|-----------------------|---------|--------
sensor.csv                  | sensor.sony.imx662_color                  | resolution_x          | 1920    | 1936
sensor.csv                  | sensor.sony.imx662_color                  | resolution_y          | 1080    | 1096
sensor.csv                  | sensor.sony.imx662_mono                   | resolution_x          | 1920    | 1936
sensor.csv                  | sensor.sony.imx662_mono                   | resolution_y          | 1080    | 1096
sensor.csv                  | sensor.sony.imx411_mono                   | sensor_width_mm       | 54.0    | 53.36
telescope_configuration.csv | ...skywatcher.quattro_200p.native / .cc   | effective_focal_ratio | 3.9     | 4.0
telescope_configuration.csv | ...skywatcher.quattro_250p.native / .cc   | effective_focal_ratio | 3.94    | 4.0
telescope_configuration.csv | ...skywatcher.quattro_300p.native / .cc   | effective_focal_ratio | 3.93    | 4.0
telescope_configuration.csv | ...sharpstar.61edph_ii.0_8x               | reduction_factor      | 0.8     | 0.821
```

---

## Open questions

These need a human decision or a measurement.

1. **QHY268C back focus: 14.5 or 12.5?** The row's note says "14.5mm back focus (SBFL version since Jan 2023)", which is a deliberate sourced choice, so it is left alone. But QHYCCD's own page states that since 2023 the 268C top section changed to match the 268M's shorter design, and the 268M is seeded at 12.5. The 14.5 figure is the SBFL front portion standalone; it becomes 12.5 once a QHY filter wheel is attached. So the two rows may be describing different configurations of the same body. Worth confirming against a unit.
2. **The C6 measured focal length is not in the data.** The audit brief states the C6's published 1500mm plate-solves at 1639mm, and that measured values recorded in notes are deliberate and should be left. `telescope.celestron.c6` carries the published 1500mm and neither its note nor either config note mentions 1639. That measurement was either lost or never written down.
3. **`mount.msm.nomad` has a blank `drive_type`** — the only one of 56 rows. `drive_type` is a closed vocabulary; the values in use are "Worm gear", "Harmonic" and "Direct drive". Not guessed.
4. **`LLM_DB_SPECS.md` is stale.** It states `telescope_configuration.csv` has 73 rows and `filter.csv` has 74; actual counts are 84 and 80. Column semantics are where a drifted schema doc quietly produces wrong conclusions in future audits.

---

## Recorded gaps

Documented so the absence is on record rather than silently filled later.

- `mount.periodic_error_arcsec` is blank on **all 56** mount rows. Most manufacturers do not publish PE for belt-driven or encoder mounts, so part of this is genuinely unpublishable, but 56/56 suggests it was never populated rather than researched and found absent.
- `obstruction_pct` is missing on **16 rows with a genuine central obstruction**: 6 Celestron SCTs (EdgeHD 800/1100/1400, C6, C8, C11), RASA 11 v2, Origin, 4 Newtonians (Quattro 200P/250P/300P, Sharpstar 15028HNT) and 4 Unistellar Newtonians. Only 2 of 10 SCT/RASA rows have a value. No refractor carries a spurious obstruction, so the classification side is clean.
- `source_url` is blank on 74/80 filters, 101/112 cameras, 54/56 mounts, 38/41 sensors. `telescope.csv` is fully populated, so the URL backfill appears to have reached only that one file.
- `weight_g` blank on 100/112 cameras; `weight_kg` missing on 14 telescopes.
- `worm_period_seconds` blank on 32/56 mounts — legitimately N/A for harmonic and direct drives, which have no worm.
- **ZWO ASI4400MC Pro**: no sensor part number, resolution or pixel size published on ZWO's own page. Confirmed unpublished, not filled from a retailer's guess.

---

## Audit coverage

**Verified exhaustively (all rows, deterministic):** CSV column-count parsing and comma corruption across all 7 files; sensor dimensions against resolution x pixel size (41 rows); focal ratio against FL/aperture (84 configs); reduction factor against native FL (84 configs); camera-to-sensor and passband-to-filter foreign keys; closed-vocabulary conformance for `sensor_type`, `bayer_pattern` and `filter_passband.line_name`; the blocking-filter no-passband rule; native-config invariants; passband central wavelengths against rest wavelengths (83 rows); camera model numbers against mapped sensor part numbers (112 rows); mount worm periods against integer tooth counts (24 rows); cooled flag against cooling delta (112 rows).

The structural picture is clean: all seven files parse at header width, row counts match the brief exactly (41/112/51/84/56/80/83), and no field contains a stray comma. The earlier 19-row telescope corruption is fixed — `source_url` is populated on all 51 telescope rows.

**Verified against manufacturer sources:** only the rows the checks above flagged, plus the named trap cases (Seestar S50/S50 Pro/S30, eVscope 2, DWARF, Origin, ASI4400MC Pro).

**Not yet verified — the largest remaining piece of work:** individual mount payload and weight figures, filter peak transmission percentages, sensor QE / read noise / full well values, and camera back focus outside the QHY rows. None of these are reachable by arithmetic; they need row-by-row sourcing. The mount payloads are probably the most consequential, since they feed rig suitability.
