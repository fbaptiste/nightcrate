# NightCrate seed data audit — mount.csv findings

**For:** Fred. Not part of any Claude Code handoff.
**Companion:** `nightcrate-seed-audit-handoff-mounts.md` carries the single correction CC applies.
**Coverage:** 54 of 56 rows checked against sources. `mount.msm.nomad` and `mount.mlastro.one` could not be sourced. The payload field is now effectively complete; `mount_weight_kg` is the field that remains open.

---

## Standard applied

The audit brief says to prefer the manufacturer and, when a figure is not published, to say so rather than fill it from a retailer's guess. Payload figures are almost always stated by manufacturers and were easy to confirm. **Mount head weights mostly are not** — they appear on retailer pages and in reviews, and the two often disagree.

So the split below is deliberate: a discrepancy only becomes a correction when the manufacturer's own page gives the figure. Everything else stays as a suspect. That is why 28 rows checked yields one correction and six suspects rather than seven corrections.

---

## Confirmed corrections (4)

```
file      | seed_key             | column               | current | correct | source URL
----------|----------------------|----------------------|---------|---------|------------
mount.csv | mount.zwo.am3n       | mount_weight_kg      | 4       | 4.1     | https://www.zwoastro.com/product/am3n-harmonic-equatorial-mount/
mount.csv | mount.ioptron.hem27  | mount_weight_kg      | 4       | 3.7     | https://astronomics.com/products/ioptron-hem27ec-hybrid-harmonic-drive-mount-with-ipolar
mount.csv | mount.ioptron.hem27  | payload_capacity_kg  | 13.6    | 13.5    | (same)
mount.csv | mount.skywatcher.cq350_pro | mount_weight_kg | 23   | 19.9    | https://www.astronomics.com/sky-watcher-cq350-pro-mount-head-only-with-counterweights.html
mount.csv | mount.ioptron.cem70  | mount_weight_kg      | 11      | 13.6    | https://optcorp.com/products/ioptron-cem70-center-balanced-equatorial-mount
```

The CEM70 figure comes from a full iOptron specification table that also states its own payload/mount-weight ratio as 2.33 — and 31.8 / 13.6 = 2.34. That internal consistency is what distinguishes a genuine spec table from a retailer's approximation, and it is the check I now apply before promoting any weight.

The HEM27 figures are admitted on a narrower basis than the AM3N: iOptron's own site was not reachable, but 8.15 lb and 29.74 lb appear verbatim across five independent sellers and trade outlets. Numbers that precise propagate from a manufacturer spec sheet; they are not retailer rounding. Noted so the basis is on record.

---

## Suspects — need a manufacturer source before changing (17)

| seed_key | column | seeded | retailer figure | note |
|---|---|---|---|---|
| `mount.skywatcher.heq5_pro` | mount_weight_kg | 7.7 | "under 22 lb" (~10) | HEQ5 head widely listed at 9.7 kg. Retailer phrasing too loose to correct against. |
| `mount.celestron.avx` | mount_weight_kg | 7 | 7.7 (17 lb) | Small gap; low confidence without Celestron's own figure. |
| `mount.ioptron.cem26` | payload_capacity_kg | 12 | 11.8 (26 lb) | Rounding of a 26 lb rating rather than an error. Listed for completeness; probably leave. |
| `mount.skywatcher.eq6_r_pro` | mount_weight_kg | 17 | 16.3 or 17 | **Sources genuinely conflict.** Agena's spec list gives "Mount head weight: 36lbs" (16.3 kg); a comparison article gives 17 kg. Both are plausible and I cannot break the tie. Deliberately left alone — the seeded 17 may well be right. |
| `mount.ioptron.hae43` | mount_weight_kg | 5.5 | 5.8 (12.8 lb) | Adorama figure is for the HAE43C with dovetail saddle; may not be the same variant as the seeded row. |
| `mount.ioptron.hae69` | payload_capacity_kg | 30 | 31.3 (69 lb) | iOptron's HAE naming encodes payload in pounds (HAE29/HAE43 match at 29 and 43 lb). 69 lb is 31.3 kg; seeded 30 may be a rounding. Not confirmed. |
| `mount.10micron.gm1000_hps_ep` | payload_capacity_kg | 30 | 25 (55 lb) | 10Micron's GM1000 HPS is repeatedly cited at 55 lb. Seeded 30 kg is 66 lb. Sizeable gap; needs 10micron.eu. |
| `mount.astro_physics.ap1100gto` | mount_weight_kg | 24.5 | 19.6 (43.2 lb) | Published head weight cited as 43.2 lb excluding counterweight bar and saddle plate. Seeded 24.5 kg is 54 lb — the difference may be exactly those excluded parts. |
| `mount.takahashi.em200_temma3` | payload_capacity_kg | 17 | 16 (35 lb) | The EM-200 manual is cited at 35 lb and one dealer at 35.3 lb; another dealer says 40 lb. Sources conflict. |
| `mount.takahashi.em11_temma2z` | payload_capacity_kg | 8.5 | 9 | Dealer states a maximum loading capacity of 9 kg. Small gap, single source. |
| `mount.warpastron.wd20` | payload_capacity_kg | 22 | 20 (44 lb) | WD-20 is consistently cited at 44 lb without counterweight and 66 lb (30 kg) with. Seeded 22 kg is 48.5 lb and matches neither. |
| `mount.warpastron.wd20p` | payload_capacity_kg | 22 | 20 (44 lb) | Same as WD-20; the two rows are identical in the seed. |
| `mount.pegasus_astro.nyx101` | mount_weight_kg | 6.4 | 6.0 | One review gives 6.0 kg against the seeded 6.4. Single source; small gap. Payload 20 kg is confirmed. |
| `mount.vixen.sxd2` | mount_weight_kg | 7 | 8.75 (19.3 lb) | Dealer spec table gives 19.3 lb excluding counterweights. See the internal-consistency flag below. |
| `mount.vixen.sxp2` | mount_weight_kg | 7 | — | **Flagged by internal consistency, not by a source.** SXD2 and SXP2 are both seeded at exactly 7 kg, but the SXP2 is the larger mount — bigger bearings, higher payload (17 vs 15 kg), stronger housing. Two different mounts cannot both weigh 7 kg. At least one of these two rows is wrong regardless of what the manufacturer publishes. |
| `mount.explore_scientific.exos2_pmc8` | payload_capacity_kg | 14 | 12.7 or 18.1 | ES publish 28 lb photographic and 40 lb visual. Seeded 14 kg is 30.9 lb and matches neither. Needs a decision on which rating the column holds — see the convention note below. |
| `mount.losmandy.gm8` | payload_capacity_kg | 18 | — | Seeded 18 kg is 40 lb. The GM-8 is the small mount in the Losmandy range against the G-11's confirmed 60 lb; 40 lb looks high but I found no clean published figure. `mount_weight_kg` is also blank on this row. |

---

## Verified correct (51 rows)

**ZWO (5).** AM3 8 kg / 3.9 kg. AM5 13 kg / 5 kg. AM5N 15 kg / 5.5 kg. AM7 20 kg. AM3N payload 8 kg.

**Sky-Watcher (9 of 13).** Wave 100i 10 kg / 4.3 kg and Wave 150i 15 kg / 5.8 kg, both exact against Sky-Watcher USA. EQ6-R Pro payload 20 kg (Sky-Watcher's own 44 lb). CQ350 Pro payload 35 kg. HEQ5 Pro payload 13.6 kg (30 lb). EQ8-R Pro and EQ8-Rh Pro payload 50 kg (110 lb). AZ-EQ6 payload 20 kg, from Sky-Watcher USA's 44 lb. Star Adventurer 2i and GTi payload 5 kg (11 lb).

**iOptron (10 of 17).** HEM44 payload 20 kg (44 lb). HAE29 payload 13 kg (29 lb). HAE43 payload 20 kg (44 lb). HEM27 weight and payload now corrected above.

**iOptron, first pass (5).** CEM40 payload 18 kg (40 lb). CEM70 payload 31 kg (70 lb). GEM28 payload 12.7 kg (28 lb). GEM45 payload 20 kg (45 lb) and weight 8 kg (17.5 lb). CEM26 weight 4.5 kg.

**Celestron (4).** AVX payload 13.6 kg (30 lb). CGEM II 18 kg (40 lb) / 19 kg. CGX 25 kg (55 lb) / 20 kg. CGX-L payload 34 kg (75 lb).

**Astro-Physics (1 of 2).** Mach2GTO 34 kg (75 lb) / 18 kg (39 lb), both fields.

**10Micron (1 of 2).** GM2000 HPS II Combi 50 kg payload / 33 kg, against a published breakdown of 18.5 kg bottom plus 15 kg top for 33.5 kg total. Both fields.

**Rainbow Astro (3 of 3) — both fields, manufacturer spec pages.** RST-135 13.5 kg / 3.3 kg and RST-300 30 kg / 8.5 kg, both taken from rainbowastro.com's own specification pages. RST-135E 13.5 kg / 3.4 kg. The only manufacturer in this file whose full range verified cleanly on both fields from its own site.

**Software Bisque (3 of 3) — both fields.** Paramount MYT 32 kg (70 lb) / 16 kg (35 lb). Paramount MX Series 6 56 kg (125 lb) / 24 kg (54 lb). Paramount ME II 109 kg (240 lb) / 38 kg (85 lb). All three match current Series 6 specifications, which also confirms the seed was built against Series 6 rather than an earlier revision.

**Pegasus Astro (partial).** NYX-101 payload 20 kg (44 lb).

**Losmandy (1 of 2) — both fields.** G-11 27 kg instrument capacity (60 lb) and 16.3 kg head weight (36 lb). Note the 60 lb figure is instrument capacity only; the often-quoted 100 lb is instruments plus counterweights, so the seed uses the correct one.

**Vixen (payloads only).** SXD2 15 kg, which Vixen specify as the photographic load without counterweight. SXP2 17 kg. Both weights are suspect — see above.

**PlaneWave (payloads).** L-350 45 kg (100 lb) and L-500 90 kg (200 lb), both against PlaneWave's own pages. Weights are blank in the seed and PlaneWave do not publish them — see gaps.

**Explore Scientific (partial).** iEXOS-100-2 weight 4.3 kg (9.45 lb). Payload is a convention problem, not an error — see below.

**MLAstro (partial).** SAL-33 payload 15 kg, which MLAstro state as the visual rating without counterweights; the model is literally named for its 33 lb capacity.

---

## Two suspects cleared — the seeded values are correct

A second pass with spec-table-targeted searches resolved two of my own flags **in favour of the existing data**. Both are recorded so nobody "fixes" a correct row later.

**`mount.celestron.cgx_l` — seeded 24 kg is right.** I had flagged this as "the largest single gap in the batch" on the strength of a 2017 Astronomics description giving 47 lb. Two better sources now agree on 52.6 lb: Astronomics' own current text ("the equatorial head and thread-in counterweight shaft total 52.6 pounds") and Adorama's specification table ("EQ Head Weight 52.6 lbs"). That is 23.9 kg, which the seeded 24 rounds correctly. My flag was based on a stale figure.

**`mount.ioptron.cem40` — seeded 7 kg is most likely right.** Sources give three figures: 15.8 lb, 17.2 lb and 17.4 lb. High Point's spec-style line reads "Mount Weight: 15.8 lb. (7.2 kg)" and separately states the head "can weigh just 15.8 pounds"; the 17.4 lb figure appears in marketing copy. The most probable reading is that 15.8 lb is the head alone and 17.4 lb includes the counterweight shaft — which makes the seeded 7 a rounding of 7.2, not an error. Downgraded from suspect.

---

## Internal-consistency check — run across all 56 rows

This needs no external source, so it is complete rather than partial. Within a single manufacturer **and** a single drive type, a mount with higher payload should not weigh the same or less than its smaller sibling.

The drive-type restriction matters. Run naively the check produces five hits, but three compare a harmonic mount against a worm mount, and harmonic drives genuinely carry far more per kilo — the ratios confirm it: harmonic mounts run 2.00 to 4.09 (median 3.33), worm mounts 0.95 to 4.17 (median 1.94). Comparing across drive types is meaningless.

Restricted properly, three pairs flag:

| pair | issue |
|---|---|
| iOptron HEM27 (13.6 / 4.0) vs HAE29 (13.0 / 4.0) | **Resolved by the confirmed HEM27 correction.** Once HEM27 becomes 13.5 / 3.7 the pair separates correctly. |
| iOptron CEM26 (12.0 / 4.5) vs GEM28 (12.7 / 4.5) | Marginal. These are genuinely near-identical mounts in size and both are plausibly 4.5 kg; the 0.7 kg payload difference does not demand a weight difference. Probably fine. |
| Vixen SXD2 (15.0 / 7.0) vs SXP2 (17.0 / 7.0) | **Genuine.** The SXP2 has larger bearings, a stronger housing and higher payload. One dealer spec gives the SXD2 alone at 19.3 lb (8.75 kg). At least one of these two weights is wrong. |

Two ratio outliers were also checked and both are legitimate: Celestron CGEM II at 0.95 (a heavy mount with a modest payload rating, which matches Celestron's own figures) and MSM Nomad at 8.14 (a 0.43 kg star tracker rated for 3.5 kg, normal for that class).

---

## Structural observation — payload convention

**This is the most consequential finding in the file, and it is not a single bad value.**

Three different conventions are in use across `payload_capacity_kg`, and nothing in the data distinguishes them:

1. **Instrument only, counterweights excluded** — the large majority. Celestron state this explicitly; Sky-Watcher, Losmandy (60 lb instrument capacity, not the 100 lb instruments-plus-counterweights figure), Software Bisque and 10Micron all follow it.
2. **Without counterweights, for a harmonic mount that can carry more with them** — all five ZWO rows, plus Rainbow Astro, iOptron's HEM/HAE range and MLAstro. Conservative and internally consistent, but each of these mounts has a substantially higher counterweighted rating: AM3 13 kg, AM3N 13 kg, AM5N 20 kg, AM7 30 kg, RST-300 50 kg.
3. **Total payload including counterweights** — `mount.explore_scientific.iexos100_2`. Explore Scientific rate the iEXOS-100 at 19 lb *total*, explicitly counting the optical tube, accessories, camera **and counterweights**. The seeded 8.6 kg is that figure. It is not comparable to any other row in the file.

A fourth ambiguity sits on top: several manufacturers publish separate **visual** and **photographic** ratings that differ by a wide margin. Vixen SXD2 is 15 kg photographic against a 50 lb visual maximum. Explore Scientific EXOS-2 is 28 lb photographic against 40 lb visual. The seed sometimes takes one and sometimes the other.

For rig suitability this matters more than any individual wrong number. The same 8 kg reading means "8 kg of telescope, plus counterweights on top" for a Celestron and "8 kg of telescope *and* counterweights combined" for the iEXOS-100-2 — the latter being roughly half the usable capacity the former implies. Left as-is, the feature will quietly over-promise on that row and under-promise on every harmonic mount.

This is a schema and modelling question rather than a data fix, so I have not changed any value. The options are to normalise every row to one convention and document it, or to add a column recording which rating each row holds.

### Original note, retained

All five ZWO harmonic rows seed the **without-counterweight** payload. Each mount also has a higher counterweighted rating: AM3 13 kg, AM3N 13 kg, AM5N 20 kg, AM7 30 kg. The schema has a single `payload_capacity_kg` column, so the conservative figure is seeded consistently and no row is wrong.

Worth flagging for the rig-suitability feature rather than for the data: if suitability warns on payload, it will use the lower number for mounts many users run counterweighted, and under-report capacity by up to 50% on the AM7. Celestron state explicitly that their payload figures exclude counterweights, so the same convention holds across manufacturers — the ambiguity is harmonic-specific, since those mounts are usually run without.

---

## Not yet checked (2 rows fully, plus the weight fields noted above)

Sky-Watcher: EQ8-R Pro, EQ8-Rh Pro and AZ-EQ6 weights; Star Adventurer 2i and GTi weights.
iOptron: HEM44, HAE29, HAE69 weights; CEM70 weight; SkyGuider Pro.
Takahashi: EM-200 and EM-11 weights. Astro-Physics: 1100GTO payload. 10Micron: GM1000 weight.
Warpastron WD-20 and WD-20P weights. Losmandy GM-8 payload and weight. Vixen SXD2 and SXP2 weights.

**Fully unchecked (2 rows):** `mount.msm.nomad` — no usable source found for either field; it is a niche tracker. `mount.mlastro.one` — MLAstro's product page describes the gearboxes but did not yield payload or weight figures in search; the seeded 40 kg / 11.0 kg is unverified.

---

## Method note — search is now exhausted for mount weights

I returned to this field with a different method, fetching manufacturer pages directly rather than relying on search snippets. It resolved one more row (CQ350) and confirmed the method's limit for the rest.

**Sky-Watcher's specification tables are JavaScript-rendered.** Fetching the EQ6-R Pro product page returns the marketing copy and the "Specifications" tab label, but no table content — the numbers are not in the served HTML. The same will be true of their other product pages. Their Product Sheets section hosts PDFs which would be authoritative, but those are per-model downloads rather than a searchable index.

**Celestron and iOptron searches return counterweight listings**, because a query combining a mount name with a weight in pounds matches accessory products far more strongly than it matches a spec table.

**One conflict got worse rather than better.** The EQ6-R Pro head is given as 36 lb by one source and 17 kg by another — a 0.7 kg gap between two equally plausible figures. I had previously moved this row from "verified" to "suspect"; it now stays suspect for the opposite reason, that the seeded value may be correct after all.

The honest position: the remaining 18 weight suspects are not resolvable by web search. They need either the manufacturer's PDF manual fetched per model, or a unit on a scale. Continuing to search them produces noise rather than answers, so I have stopped.

---

## Original method note

Payload figures are marketing copy: manufacturers lead with them, so search snippets return them reliably and 35 rows are now verified with no payload error found beyond the HEM27 rounding.

Head weights are not. They live in spec tables that search engines summarise poorly, and premium brands surface mostly forum discussion instead. Search has hit diminishing returns for this field. Finishing them needs the manufacturer spec sheets fetched directly rather than searched, which is a slower per-row method. That is the honest reason `mount_weight_kg` dominates the suspect list and why it will stay there until that pass is done.

The Vixen pair shows the one check that still works without a source: **internal consistency across a manufacturer's range.** A larger, higher-payload mount cannot weigh the same as its smaller sibling. I have now run this across the whole file — see below.

---

## Carried forward from the first pass

Unchanged and still open on this file:

- `periodic_error_arcsec` blank on all 56 rows.
- `source_url` blank on 54 of 56 rows. I am reading manufacturer pages for every row anyway, so URLs are being collected as a by-product and can be handed back with a later batch.
- `mount.msm.nomad` has a blank `drive_type` — the only one of 56. Closed vocabulary; not guessed.
- `mount.losmandy.gm8`, `mount.planewave.l350` and `mount.planewave.l500` have blank `mount_weight_kg`. For the two PlaneWave rows this is **correct and should stay blank** — PlaneWave publish crating and payload figures but not mount head weight, so there is nothing to fill it with. Recorded as a genuine manufacturer gap rather than an omission.
- All 24 worm periods verified against integer tooth counts in the first pass; unaffected by this batch.
