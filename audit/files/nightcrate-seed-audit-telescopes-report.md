# NightCrate seed data audit — telescope.csv and telescope_configuration.csv findings

**For:** Fred. Not part of any Claude Code handoff.
**Companion:** `nightcrate-seed-audit-handoff-telescopes.md` carries the single correction from this pass.
**Coverage:** all 51 telescope rows and all 84 configuration rows checked by internal consistency; targeted source verification on everything flagged.

The Quattro focal ratios (6 rows) and the Sharpstar reduction factor were found in batch 1 and live in `nightcrate-seed-audit-handoff.md`.

---

## Confirmed correction (1)

```
file                        | seed_key                                          | column                  | current | correct | source URL
----------------------------|---------------------------------------------------|-------------------------|---------|---------|------------
telescope_configuration.csv | ...skywatcher.evostar_72ed.0_85x                  | effective_back_focus_mm | (blank) | 55.0    | https://www.skywatcherusa.com/products/0-85x-reducer-flattener-for-evostar-72ed
```

---

## A check I ran, then discarded

I compared each configuration's `effective_image_circle_mm` against its telescope's `image_circle_mm` scaled by `reduction_factor`, on the assumption that a reducer shrinks the illuminated circle proportionally. Four rows failed — the EdgeHD 800, 925, 1100 and 1400 with the 0.7x reducer.

**The check is wrong and the rows are fine.** A dedicated reducer/corrector is not a simple scaling element; its illuminated field is a property of the corrector's own optics, and Celestron design the EdgeHD 0.7x reducer to preserve full-frame coverage rather than shrink it. The seeded 42mm values are the manufacturer's figures, not arithmetic outputs.

Recording this because the check looks reasonable and someone will re-derive it. Image circle does not scale with reduction factor, and rerunning this comparison will produce the same four false positives.

---

## Verified correct

- **All 51 apertures.** Five rows flagged where the model name's number disagrees with `aperture_mm`, and all five are false positives: the three Sky-Watcher Quattros are named for nominal aperture while Sky-Watcher publish 205/254/305mm (confirmed in batch 1 from their own product URLs), and the two Askar FRA models are named for **focal length**, not aperture — the FRA300 is a 60mm f/5 and the FRA400 a 72mm f/5.6. Both are correct.
- **Every telescope has exactly one native configuration** with `reduction_factor=1.0`. No orphan configs, no telescope without a config.
- **All 84 focal ratios** reconcile with focal length over aperture, except the six Quattro rows already handled in batch 1.
- **All 84 reduction factors** reconcile with native focal length, except the Sharpstar row already handled in batch 1.
- **Image circles are plausible against aperture** on every row that has one.
- **`accessory_name` is populated on every non-native configuration.** No blanks.
- **The two populated obstruction values are plausible**: EdgeHD 925 at 36% and RASA 8 at 46%. The RASA figure is high but correct in kind — the prime-focus camera assembly is a large obstruction by design.

---

## Suspects

| seed_key | column | seeded | issue |
|---|---|---|---|
| `telescope_configuration.william_optics.gt81_iv.native` | effective_back_focus_mm | 183.4 | An outlier by a wide margin. The other native refractor configs use 55mm and the SCTs 133–146mm; 183.4mm on a native GT81 looks like a full optical-train length rather than a back focus. Worth checking what the number was measured from. |

---

## Gaps — recorded, not filled

**Eight non-native configurations still have no `effective_back_focus_mm`.** Every reducer and flattener has a specified working distance, so these are genuine omissions rather than unpublishable values:

- `skywatcher.evostar_80ed.0_85x`, `skywatcher.evostar_100ed.0_85x`, `skywatcher.evostar_120ed.0_85x`
- `askar.fra400.reducer`, `askar.fra600.reducer`
- `explore_scientific.ed80_fcd100.0_8x`, `explore_scientific.ed102_fcd100.0_8x`, `explore_scientific.ed127_fcd100.0_8x`

I filled only the 72ED because only that one is stated on the manufacturer's page. **55mm should not be assumed for the other three Evostar reducers** — they are an older, different optical design from the 72ED unit, and Sky-Watcher's own listings for the 80/100/120 reducers do not state a back focus figure. Their own EvoStar 72ED rotator-adapter listing elsewhere on the same site quotes an 89mm back focus that becomes 55mm only with a spacer and M48 ring installed, which shows how easily these figures shift with configuration.

**`obstruction_pct` is populated on only 2 of 51 telescopes.** 16 of the blanks are on designs that genuinely have a central obstruction: 6 Celestron SCTs (EdgeHD 800/1100/1400, C6, C8, C11), RASA 11 v2, Origin, 4 Newtonians (Quattro 200P/250P/300P, Sharpstar 15028HNT) and 4 Unistellar Newtonians. The remaining blanks are refractors, where blank is correct — no refractor carries a spurious obstruction value, so the classification side is clean.

**`weight_kg` missing on 14 telescopes.**

**The C6 measured focal length is still absent.** The audit brief notes the C6's published 1500mm plate-solves at 1639mm and that measured values recorded in notes are deliberate. `telescope.celestron.c6` carries the published 1500mm, and neither its note nor either of its config notes mentions 1639. That measurement was either lost or never written down — it is not in the data to preserve.

**`source_url` is fully populated on all 51 telescope rows** — the one file where the URL backfill completed.

---

## Not done

Individual focal lengths and image circles were verified only where a consistency check flagged them or where I already had the manufacturer page open for another reason. The bulk of the 51 native focal lengths carry plausible values I have not individually sourced.
