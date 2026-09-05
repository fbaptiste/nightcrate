# NightCrate seed data audit — correction handoff (telescopes, batch 4)

**For:** Claude Code
**Scope:** one existing row in `telescope_configuration.csv`. No new models. No schema changes. No migrations.
**Status of decisions:** final. Apply exactly as written.

Self-contained and independent of the other handoffs. Note that `telescope_configuration.csv` also receives 7 corrections from `nightcrate-seed-audit-handoff.md` (the Quattro focal ratios and the Sharpstar reduction factor). Those are different rows; there is no overlap and the two can be applied in either order.

---

## What to do

Apply the single line replacement below to `backend/src/nightcrate/data/seed/telescope_configuration.csv`.

Match on the full OLD line, replace with the full NEW line. Do not reformat, reorder columns, or rewrite any other row.

### Constraints

- **No commas inside any field.** The NEW line is verified to contain zero commas in field values and to parse at exactly the header's 11-column width.
- **No migration required.** This populates an already-seeded field that was blank.
- **Do not touch `is_mine`.**
- Preserve `#` comment lines and blank lines exactly.

### Verification after applying

1. Every row parses at 11 columns; 84 data rows excluding comments and blanks.
2. Every telescope still has exactly one config with `is_native=1` and `reduction_factor=1.0`.

---

## Correction

### `telescope_configuration.csv`

**`telescope_configuration.skywatcher.evostar_72ed.0_85x`** — `effective_back_focus_mm` blank to 55.0

```
OLD: telescope_configuration.skywatcher.evostar_72ed.0_85x,telescope.skywatcher.evostar_72ed,Sky-Watcher 0.85x Reducer/Flattener for Evostar 72ED,0.85x Reducer f/4.93,,357.0,4.93,,0,Dedicated 0.85x reducer/flattener specifically designed for Evostar 72ED; flattens field and reduces focal length; NOT interchangeable with other Evostar reducers; sold separately,0.85
NEW: telescope_configuration.skywatcher.evostar_72ed.0_85x,telescope.skywatcher.evostar_72ed,Sky-Watcher 0.85x Reducer/Flattener for Evostar 72ED,0.85x Reducer f/4.93,55.0,357.0,4.93,,0,Dedicated 0.85x reducer/flattener specifically designed for Evostar 72ED; flattens field and reduces focal length; NOT interchangeable with other Evostar reducers; sold separately,0.85
```

**Why:** every reducer/flattener has a specified working distance, and this row had none. Sky-Watcher's own product page for the 0.85x Reducer/Flattener for EvoStar 72ED states a 55mm back focus, matching the 55mm that 22 other configs in this file already use.

**Scope note:** eight other non-native configs are also missing `effective_back_focus_mm` — the Evostar 80/100/120 reducers, both Askar full-frame reducers, and the three Explore Scientific 0.8x reducers. **Do not fill those.** Only the 72ED figure was confirmed from the manufacturer; the older Evostar 80/100/120 reducers are a different optical design and 55mm must not be assumed for them.

Source: https://www.skywatcherusa.com/products/0-85x-reducer-flattener-for-evostar-72ed

---

## If you find anything else

This document is the complete set of changes. If you believe another row is wrong, or that this correction is mistaken, **stop and report it — do not act on it.** Unverified values must not enter these files; they load into a live database on startup. Sourcing new values is out of scope.
