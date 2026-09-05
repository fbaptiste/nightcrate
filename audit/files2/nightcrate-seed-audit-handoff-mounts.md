# NightCrate seed data audit — correction handoff (mounts, batch 2)

**For:** Claude Code
**Scope:** correcting existing seeded rows in `mount.csv`. No new models. No schema changes. No migrations.
**Status of decisions:** all decisions in this document are final. Apply exactly as written.

This is a **separate, self-contained batch** from `nightcrate-seed-audit-handoff.md` (sensor and telescope_configuration). Apply either independently.

---

## What to do

Apply the 4 line replacements below to:

- `backend/src/nightcrate/data/seed/mount.csv`

Match on each full OLD line, replace with the full NEW line. Do not reformat, reorder columns, or rewrite any other row.

### Constraints

- **No commas inside any field.** All four NEW lines have been verified to contain zero commas in field values and to parse at exactly the header's 13-column width.
- **No migration is required.** This is a value change to an already-seeded field. The loader updates rows the user has not edited and skips ones they have.
- **Do not touch `is_mine`.**
- Preserve the `#` comment lines and blank lines exactly as they are.

### Verification after applying

1. Every row in `mount.csv` parses at the header's column count (13).
2. Row count unchanged: 56 data rows, excluding `#` comments and blank lines.

---

## Corrections

### `mount.csv`

**`mount.zwo.am3n`**

```
OLD: mount.zwo.am3n,manufacturer.zwo,mount_type.harmonic_eq,0,Harmonic,1,AM3N,4,Updated AM3 with improved cable management and Bluetooth,8,,,
NEW: mount.zwo.am3n,manufacturer.zwo,mount_type.harmonic_eq,0,Harmonic,1,AM3N,4.1,Updated AM3 with improved cable management and Bluetooth,8,,,
```

**`mount.skywatcher.cq350_pro`**

```
OLD: mount.skywatcher.cq350_pro,manufacturer.skywatcher,mount_type.german_eq,1,Worm gear,1,CQ350 Pro,23,Mid-heavy belt-driven imaging mount introduced 2024,35,,,479
NEW: mount.skywatcher.cq350_pro,manufacturer.skywatcher,mount_type.german_eq,1,Worm gear,1,CQ350 Pro,19.9,Mid-heavy belt-driven imaging mount introduced 2024,35,,,479
```

**`mount.ioptron.cem70`**

```
OLD: mount.ioptron.cem70,manufacturer.ioptron,mount_type.german_eq,1,Worm gear,1,CEM70,11,Heavy-payload center-balanced mount,31,,,600
NEW: mount.ioptron.cem70,manufacturer.ioptron,mount_type.german_eq,1,Worm gear,1,CEM70,13.6,Heavy-payload center-balanced mount,31,,,600
```

**`mount.ioptron.hem27`**

```
OLD: mount.ioptron.hem27,manufacturer.ioptron,mount_type.harmonic_eq,0,Harmonic,1,HEM27,4,Hybrid harmonic equatorial mount,13.6,,,
NEW: mount.ioptron.hem27,manufacturer.ioptron,mount_type.harmonic_eq,0,Harmonic,1,HEM27,3.7,Hybrid harmonic equatorial mount,13.5,,,
```

**Why `mount.zwo.am3n`:** ZWO's own product page states the AM3N weighs 4.1 kg. The AM3 it supersedes weighs 3.9 kg; the seeded 4 appears to be the AM3 figure carried across and rounded. Payload (8 kg) is correct and unchanged.
Source: https://www.zwoastro.com/product/am3n-harmonic-equatorial-mount/

**Why `mount.ioptron.hem27`:** iOptron rate the HEM27 head at 8.15 lb (3.7 kg) carrying 29.74 lb (13.5 kg) without counterweights. Both figures appear verbatim across five independent sellers and trade outlets; that precision is propagating manufacturer spec-sheet text rather than retailer rounding.
Source: https://astronomics.com/products/ioptron-hem27ec-hybrid-harmonic-drive-mount-with-ipolar

**Why `mount.skywatcher.cq350_pro`:** Astronomics state the mount head alone weighs 43.8 lb (19.9 kg), and a separate comparison independently puts the CQ350 head at ~19 kg against the EQ6-R Pro's 17 kg. The seeded 23 kg (50.7 lb) matches neither and is most likely head plus counterweight bar. Payload (35 kg) is correct and unchanged.
Source: https://www.astronomics.com/sky-watcher-cq350-pro-mount-head-only-with-counterweights.html

**Why `mount.ioptron.cem70`:** a full iOptron specification table gives "Payload (excl. CW): 31.8 kg (70 lbs). Mount Weight: 13.6 kg (30 lbs). Payload/Mount Weight: 2.33." The ratio is internally consistent with its own two figures (31.8 / 13.6 = 2.34), which is what marks this as a spec table rather than a retailer approximation. The seeded 11 kg is 24 lb and would imply a ratio of 2.89. Payload (31 kg) is a rounding of 31.8 and is unchanged.
Source: https://optcorp.com/products/ioptron-cem70-center-balanced-equatorial-mount

---

## Explicitly not changed

Several other mount rows show payload or weight figures that disagree with retailer listings. **None of them are being changed**, because the disagreements are retailer-sourced only and the catalog's standard is to prefer the manufacturer and to leave a figure alone rather than fill it from a retailer's guess. They are recorded in `nightcrate-seed-audit-mounts-report.md` for follow-up against manufacturer sources.

Do not act on them.

---

## If you find anything else

This document is the complete set of changes. If you believe another row is wrong, or that this correction is mistaken, **stop and report it — do not act on it.** Unverified values must not enter these files; they load into a live database on startup. Sourcing new values is out of scope for this task.
