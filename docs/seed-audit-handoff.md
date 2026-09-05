# Seed data audit — handoff brief

**Task:** verify the *existing* seeded equipment rows against manufacturer
sources, and report what's wrong. Adding new models is being handled
separately — this brief is only about checking what's already there.

**Repository:** `~/dev/nightcrate` (readable via the Filesystem connector).

---

## What to check

| File | Rows | What matters most |
|------|------|-------------------|
| `backend/src/nightcrate/data/seed/camera.csv` | 112 | sensor mapping, cooled flag, back focus |
| `backend/src/nightcrate/data/seed/sensor.csv` | 41 | pixel size, resolution, physical dimensions |
| `backend/src/nightcrate/data/seed/telescope.csv` | 51 | aperture, obstruction, weight |
| `backend/src/nightcrate/data/seed/telescope_configuration.csv` | 84 | focal length, focal ratio, reduction factor |
| `backend/src/nightcrate/data/seed/mount.csv` | 56 | payload, periodic error, worm period |
| `backend/src/nightcrate/data/seed/filter.csv` + `filter_passband.csv` | 80 + 83 | line names, central wavelength, bandwidth |

Read the CSVs directly rather than working from a copied list — they change.

The full schema and every column's meaning is in `LLM_DB_SPECS.md` at the repo
root. `DB_SCHEMA.md` has the same in more depth.

---

## The checks that actually catch errors

Specs get copied between websites, so agreement between three sources proves
nothing. Arithmetic does. Every row that fails one of these is worth a second
look:

**Sensor dimensions must equal resolution × pixel size.**
`resolution_x × pixel_size_um / 1000 = sensor_width_mm` (same for height).
A sensor row that fails this has one of the three fields wrong.

**Pixel scale must reproduce the published field of view.**
`pixel_scale_arcsec = 206.265 × pixel_size_um / focal_length_mm`, then
`FOV_arcmin = pixel_scale × resolution / 60`. Compare against the
manufacturer's published field. Check whether the published figure is the
diagonal before concluding it disagrees — it usually is.

**Focal ratio must equal focal length ÷ aperture.** Where a manufacturer's own
published ratio disagrees (it often does, by rounding), keep theirs and note
the discrepancy rather than "correcting" it.

---

## Traps already hit on this data

These are real errors found in this catalog, not hypotheticals. Expect more of
the same shape:

- **Advertised megapixels are sometimes upscaled output, not sensor pixels.**
  The Unistellar eVscope 2 advertises 7.7MP from a 2048×1536 window on a
  2688×1520 IMX347. Seeding the marketing figure makes every field-of-view
  calculation wrong. The published FOV is what exposes it.
- **The sensor isn't always Sony.** The Seestar S50 Pro uses an OmniVision
  OS08B10. Several sources call it a Sony.
- **Third-party sensor attributions are frequently wrong.** The Seestar S50 was
  documented as IMX662 in one place and IMX462 by ZWO. Prefer the manufacturer.
- **Published focal length can be wrong for the individual instrument.** A
  Celestron C6's published 1500mm f/10 plate-solves at 1639mm. Where a measured
  value is recorded in a note, leave it — that is deliberate.
- **Manufacturers often don't publish what the schema wants.** ZWO's own
  ASI4400MC Pro page gives no sensor part number, resolution or pixel size. When
  a figure isn't published, say so — do not fill it from a retailer's guess.

---

## Hard rules for any CSV you produce

**Never put a comma inside any field.** These CSVs have no quoting convention.
A single comma in a `notes` field silently shifts every column after it: the
trailing fields come out blank and the real values land in a column the loader
ignores. This had already cost 19 telescope rows their weight, obstruction and
source URL — 14 product links were missing from the database for that reason
alone. Use semicolons and full stops. **Verify every row you write parses at
exactly the header's column count.**

**Closed vocabularies — a new value needs a migration, so don't invent one:**
- `sensor.sensor_type`, `sensor.bayer_pattern`
- `filter_passband.line_name` — `Ha, Hb, Oiii, Sii, Nii, OI, Lum, R, G, B, R+, UVIR, LP, ND, other`
- `mount.drive_type`, `software.category`, `connection_interface.category`
- `dso.obj_type`, `dso_designation.catalog`

**Blocking filters (UV/IR-cut, light pollution) get no `filter_passband` rows.**
None of the 13 already seeded has one. Passbands drive per-line integration
budgets and moon sensitivity; a UV/IR-cut row invents a line to accumulate
hours against.

**`bandwidth_nm` may be left empty** (migration 0051) when a manufacturer
publishes the emission line but not its width. `central_wavelength_nm` is still
required. Leaving it blank is correct; guessing a width is not.

**Do not touch `is_mine`.** It is user-managed and never seeded.

**Changing a seeded field changes its hash.** The loader will update rows the
user hasn't edited and skip ones they have. That is the intended behaviour — no
migration needed for a value change. Adding a *new* field to a table's
`seeded_fields`, however, requires a migration that backfills, or every existing
row is treated as user-modified and skipped forever.

---

## What to hand back

For each error found, one row of:

```
file | seed_key | column | current value | correct value | source URL
```

Plus a short list of rows where the manufacturer publishes nothing, so the gap
is recorded rather than silently filled.

Corrected CSV lines are welcome, but the table above is the important part —
it is reviewable, and the CSV can be regenerated from it.

**Please don't edit the repository directly.** These files are loaded into a
live database on startup and the changes need reviewing against the hash
contract first.
