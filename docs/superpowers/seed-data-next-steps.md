# Seed Data Population — Next Steps

## Current State

**Branch:** `v0.10.1/seed-data-population`
**Version:** 0.10.1 (not yet bumped/finalized)

### What's done this session

**Schema/infrastructure changes:**
- `filter_type` now has `display_name` column, CHECK constraint removed (user-extensible)
- `filter_type` has full CRUD endpoints + appears in Lookup Tables panel
- `broadband_luminance` renamed to `luminance`
- Re-seed button added to Admin page (POST /api/admin/reseed)

**Lookup tables fully populated (8/8):**
1. `filter_type.csv` — 9 types with display_name
2. `computer_type.csv` — 3 types (Imaging, Processing, Control)
3. `mount_type.csv` — 5 types (German EQ, Harmonic EQ, Alt-Az, Fork, Star Tracker)
4. `optical_design.csv` — 10 designs (SCT, Newtonian, RC, Doublet/Triplet/Quad Refractor, Petzval, Mak-Cass, DK/CDK, RASA)
5. `connection_interface.csv` — 9 interfaces (USB 3.0 Type-B/C, USB 2.0/Micro-B, WiFi, Bluetooth, Ethernet, ST-4, Serial RS-232)
6. `connector_size.csv` — 10 sizes (M54, M48, T2, 2", 1.25", 3", M68, M72, SCT, Large SCT)
7. `filter_size.csv` — 5 sizes (1.25", 36mm, 2", 50mm Round, 50mm Square)
8. `manufacturer.csv` — 26 manufacturers

### What's left to populate

**Simple equipment (next up):**
- `software.csv` — expand from 2 (add PixInsight, ASTAP, SharpCap, Stellarium, etc.)
- `computer.csv` — empty (ASIAIR Plus/Pro, mini-PCs)
- `mount.csv` — expand from 1 (AM5, CGX-L, EQ6-R, HEQ5, iOptron GEM45/CEM26, Paramount, RST-135, etc.)
- `mount_interface.csv` — junction rows following mount
- `focuser.csv` — empty (ZWO EAF, Pegasus FocusCube, PrimaLuceLab SESTO/ESATTO)
- `focuser_interface.csv` — junction rows
- `filter_wheel.csv` — empty (ZWO EFW series, QHY CFW)
- `filter_wheel_interface.csv` — junction rows
- `oag.csv` — empty (ZWO OAG, QHY OAG)
- `guide_scope.csv` — empty (mini guide scopes)

**Complex equipment (needs spec research):**
- `sensor.csv` — expand from 2 (IMX series: 571, 533, 585, 662, 178, 294, 678, 455, etc.)
- `camera.csv` — expand from 2 (ZWO ASI series, QHY series, Player One)
- `camera_interface.csv` — junction rows
- `telescope.csv` — expand from 1 (Celestron SCTs, Askar refractors, Sharpstar, Sky-Watcher, William Optics, etc.)
- `telescope_connector.csv` — junction rows
- `telescope_configuration.csv` — native + reducer configs per telescope
- `filter.csv` — expand from 2 (Optolong, Antlia, ZWO, Chroma LRGB + narrowband sets)
- `filter_passband.csv` — wavelength data per filter

**Alias tables (last):**
- `camera_alias.csv` — FITS INSTRUME header strings
- `telescope_alias.csv` — FITS TELESCOP header strings
- `filter_alias.csv` — FITS FILTER header strings

## Approach for research

Fred has been using a second AI (Claude Desktop) to help research and validate equipment decisions. The workflow:
1. Claude Code proposes a list for a table
2. Fred reviews/corrects with domain knowledge (often consulting the other AI)
3. Claude Code updates the CSV and commits

For complex equipment (sensors, cameras, telescopes), web research will be needed for specs. Claude Code has `WebSearch` and `WebFetch` tools available.

## Decisions made (for reference)

- **Connection interfaces:** physical only (no ASCOM/INDI protocols). Combined USB names ("USB 3.0 Type-B"). Power connections deferred to future version.
- **Optical designs:** Replaced generic "APO Refractor" with Doublet/Triplet/Quadruplet Refractor. Petzval kept as distinct from Quadruplet.
- **Filter types:** `broadband_luminance` → `luminance`. Now user-extensible (CHECK constraint removed).
- **Connector sizes:** Added SCT thread and Large SCT thread for accurate C11 modeling.
- **Scope:** "Common astrophotography gear" — popular ZWO/QHY cameras, common scopes, popular mounts, standard filter sets. Not an exhaustive catalog.

## When resuming

1. `git checkout v0.10.1/seed-data-population` (or it may already be checked out)
2. Check `docs/superpowers/seed-data-progress.md` for the current status table
3. Continue from **Table 9: `software.csv`**
4. After all tables populated, run `make dev`, verify data loads, test re-seed button
5. Finalize with `finalize-session` skill
