# NightCrate seed data audit — filter.csv and filter_passband.csv findings

**For:** Fred. Not part of any Claude Code handoff.
**Coverage:** all 80 filter rows and all 83 passband rows, every column.

**There is no filter handoff file. These two files are the cleanest in the catalog and I found nothing to correct.**

---

## Verified correct

- **All 83 central wavelengths match their line identity** against rest wavelengths (Ha 656.28, Hb 486.13, OIII 500.7, SII 671.6, NII 658.34). Zero outside tolerance.
- **All bandwidths agree with the bandwidth stated in the filter's own model name.** Where a model is called "3nm" or "6.5nm", the seeded `bandwidth_nm` matches. Zero mismatches across every row where the name states a figure — the single most useful check available on this file, and it passes completely.
- **No duplicate `line_name` within any filter.**
- **No passband claims a higher peak transmission than its parent filter.** A band cannot out-transmit the filter it belongs to; zero violations.
- **All peak transmission values are plausible** — the range runs 85% to 97%, with nothing below 70% or above 100%.
- **All 13 blocking filters correctly carry zero passband rows** (10 light-pollution, 3 UV/IR-cut), per the rule that a blocking filter must not invent a line to accumulate hours against.
- **Every `line_name` is inside the closed vocabulary.** No invented values.
- **No orphan passbands** — every `filter_seed_key` resolves.
- **Type-versus-passband-count reconciles on every row but one** (see below).

### A flag from batch 1 that I have now cleared

In the first pass I flagged `filter_passband.antlia.lrgbr_plus_dark_r_plus.r_plus` for a central wavelength of 850nm, which fell outside the range I had assumed for an "R+" band. **The row is correct and my range was wrong.** The filter is Antlia's LRGBR+ Dark Red+, a near-infrared band running 700–1000nm. Its midpoint is 850nm and its width is 300nm, exactly as seeded — the two fields are mutually consistent and both match the note. I had applied a visible-light red range to a deliberately NIR filter. No change needed; recorded so it is not re-flagged.

---

## Structural finding — line count and physical bands are conflated

`filter.optolong.l_enhance` is typed `filter_type.narrowband_tri`, whose definition in `filter_type.csv` is "Tri-narrowband filter combining three emission lines". It carries only **two** passband rows. It is the only row in the file where type and passband count disagree.

The row is not wrong so much as caught between two definitions, and its own note states the problem plainly: the L-eNhance passes Ha, Hb and OIII — three lines — through two physical passbands, a narrow ~10nm Ha band and a wide ~24nm band covering Hb and OIII together.

So `filter_passband` is being populated by *physical band* here, while `filter_type` counts *emission lines*. Both are defensible; they just are not the same thing, and nothing in the schema says which the table holds.

The practical consequence is on the two features passbands exist to drive:

- **Per-line integration budgets.** Hb has no passband row, so hours shot through an L-eNhance will never accumulate against Hb even though the filter passes it.
- **Moon sensitivity.** The single wide band is recorded as OIII at 24nm. OIII sits at 501nm where moonlight peaks and Rayleigh scattering is strongest, so a 24nm band there behaves very differently from a 10nm one — the width is doing real work in that model and is correctly recorded, but the Hb component inside the same band is invisible to it.

This is the same class of question as the Antlia typing decision reversed in batch 1, and the same class as `effective_read_noise_hcg_e` in `camera.csv`: a column whose meaning is unstated and inconsistently applied. It needs a definition, not a value change, so I have changed nothing.

---

## Suspect — the Antlia 3nm Pro transmission figures

All eight Antlia 3nm Pro rows (Ha, OIII, SII, the three Highspeed variants, and both ALP-T dualbands) are seeded at **90.0%** peak transmission, at both filter and passband level.

Antlia's own site states **88%** for the OIII 3nm Pro — "designed to deliver 88% transmission at the 500.7nm line" — on both the 36mm and 50mm listings. Retailers variously quote "85% or higher", "85% at the 500.7nm line", and "maximum transmission is 85% - 90%".

So the seeded 90 sits at the very top of the retailer range and above the manufacturer's own figure for at least the OIII filter. **I have not changed it**, for one specific reason: I only found Antlia's own page for OIII. If I set OIII to 88 and leave Ha and SII at 90, the set becomes a mixture of one sourced value and two unsourced ones, which is worse than a consistent unsourced 90. The right fix is to read all three product pages on antliafilter.com together and set the set coherently.

Worth noting that 90 may itself be Antlia's figure for the Ha and SII versions, applied across the whole family by someone who checked one page. That would make the OIII row the only wrong one — but it would also mean the value was propagated rather than sourced per filter, which is worth knowing either way.

Source: http://www.antliafilter.com/pd.jsp?id=87

---

## Gaps — recorded, not filled

- **`peak_transmission_pct` blank on 16 of 80 filters** and on 4 of 83 passbands. Having now looked at what these 16 are, the blanks are **mostly appropriate**: 13 of them are blocking or smart-telescope filters (L-Pro, UHC, CLS, CLS-CCD, IR Pass 685, Moon & Skyglow, both Antlia multi-bandpass rows, three ZWO/Seestar filters, and the three DwarfLab filters). A single peak-transmission number is not very meaningful for a broadband blocking filter, and manufacturers generally do not publish one.

  **One exception is worth a decision.** `filter.optolong.nd_3_0` is a neutral density filter with an optical density of 3.0, which is by definition a transmission of 0.1%. That figure is not unpublished — it is implied by the product name and is exact. Whether it belongs in `peak_transmission_pct` depends on whether that column means "signal throughput in the passband" (in which case 0.1% is correct and useful) or is implicitly about filters you image *through* (in which case blank is right and ND filters are simply outside the column's scope). Another small schema question rather than a missing value.
- **`bandwidth_nm` blank on 2 passbands** — both DWARF Duo-Band, for Ha and OIII. This is the migration 0051 case working as intended: DwarfLab publish the emission lines their filter passes but not the widths. Leaving these blank is correct, and guessing a width would be wrong. For contrast, ZWO do publish widths for the comparable Seestar Duo-Band (Ha 20nm, OIII 30nm) and those are seeded.
- **`source_url` blank on 74 of 80 filters** — the worst-covered file for source URLs alongside camera.csv.

---

## Not done

Peak transmission percentages were checked for plausibility and for internal consistency against their parent filter, but not verified against manufacturer transmission curves row by row. Bandwidths were verified wherever the model name states one, which covers most narrowband rows but not those named without a figure.
