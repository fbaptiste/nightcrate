# Equipment Seed Loader — Design Spec

## Goal

Build a seed loader that reads CSV files from the repo and populates the equipment database with known gear (manufacturers, sensors, cameras, telescopes, filters, etc.) on first run and on manual re-seed. Never overwrites user-created or user-modified rows.

## Scope

**In scope:**
- Python module `nightcrate.seed_loader` with public API + CLI
- CSV file format and conventions
- Hash-based change detection (never clobber user edits)
- Full seed loader infrastructure (registry, CSV reader, FK resolution, re-seed logic)
- Minimal initial seed data for Fred's equipment + common astrophotography gear
- Automatic first-run seeding on app startup
- Tests covering all seed/re-seed scenarios

**Out of scope:**
- UI "Update seed data" button (future — loader is callable programmatically)
- FITS ingest or alias resolution (separate spec exists in PLAN.md)
- Schema changes (schema is already in place from v0.8.0)
- Auto-deletion of orphaned seed rows

## Architecture

The existing spec in PLAN.md (sections 1-12, starting at line 1318) defines the complete architecture. Key components:

1. **`seed_loader/hash.py`** — deterministic SHA-256 hash over predeclared field subsets. Versioned contract (v1). Once released, any format change requires a migration.

2. **`seed_loader/registry.py`** — `SeedableTable` dataclass registry declaring every seedable table, its CSV filename, seeded fields, FK column mappings, and load order.

3. **`seed_loader/csv_reader.py`** — CSV parsing with header validation, comment line support, FK seed_key column detection.

4. **`seed_loader/loader.py`** — core logic: mode detection (first_run vs update), per-table loading, FK resolution via in-memory map, re-seed decision logic, junction table handling, parent/child coherence, error collection. Single transaction — rollback on any error.

5. **`seed_loader/__main__.py`** — CLI: `python -m nightcrate.seed_loader --db <path> --csv-root <path> [--update] [--dry-run] [--verbose] [--json]`

6. **`seed_loader/__init__.py`** — public API: `load_all(conn, csv_root, mode) -> SeedReport`

7. **App startup integration** — call `load_all` in the FastAPI lifespan after migrations, auto-detecting first_run vs existing.

## Re-seed Decision Logic

For each CSV row during update mode:
1. Resolve FK seed_keys to integer IDs
2. Look up existing row by `seed_key`
3. If no existing row → INSERT (source='seed', seed_hash computed)
4. If existing row with `source != 'seed'` → SKIP (corrupt/unexpected)
5. If existing row's recomputed hash != stored `seed_hash` → SKIP (user modified)
6. If incoming hash == stored hash → UNCHANGED (no update needed)
7. Otherwise → UPDATE with new values and new seed_hash

Junction tables: delete-and-reinsert for parents that were inserted or updated. Leave junction rows alone for unchanged or user-modified parents.

Parent/child (telescope+configs, filter+passbands): evaluated as atomic seed units. If parent is user-modified, skip entire unit including children.

## CSV Seed File Tracking

All CSVs live under `backend/src/nightcrate/data/seed/`. One per seedable table. The infrastructure (loader) is built first, then files are populated iteratively.

### Lookup Tables

| File | Status | Notes |
|------|--------|-------|
| `manufacturer.csv` | - [ ] | ZWO, Celestron, Askar, Optolong, Antlia, Starizona, etc. |
| `optical_design.csv` | - [ ] | SCT, APO Refractor, RC, Newtonian, Mak-Cass, etc. |
| `mount_type.csv` | - [ ] | German EQ, Harmonic EQ, Alt-Az, Fork |
| `connection_interface.csv` | - [ ] | USB 2.0, USB 3.0, USB-C, WiFi, Ethernet, ASCOM, etc. |
| `connector_size.csv` | - [ ] | M48, M54, T2, 1.25", 2", 3" |
| `filter_size.csv` | - [ ] | 1.25", 2", 36mm round, 50mm square |
| `computer_type.csv` | - [ ] | Imaging, Processing, Control, General |

### Equipment Tables

| File | Status | Notes |
|------|--------|-------|
| `sensor.csv` | - [ ] | IMX571, IMX533, IMX585, IMX662, IMX178, IMX294, etc. |
| `camera.csv` | - [ ] | ZWO ASI series, QHY series |
| `camera_interface.csv` | - [ ] | Junction: camera ↔ connection interface |
| `telescope.csv` | - [ ] | Celestron C11/C8, Askar series, Sharpstar, etc. |
| `telescope_connector.csv` | - [ ] | Junction: telescope ↔ connector size |
| `telescope_configuration.csv` | - [ ] | Native configs + reducer combos |
| `filter.csv` | - [ ] | Optolong, Antlia, ZWO narrowband + LRGB |
| `filter_passband.csv` | - [ ] | Wavelength data for each filter |
| `mount.csv` | - [ ] | ZWO AM5, Celestron CGX-L, etc. |
| `mount_interface.csv` | - [ ] | Junction: mount ↔ connection interface |
| `focuser.csv` | - [ ] | ZWO EAF, PrimaLuceLab SESTO, etc. |
| `focuser_interface.csv` | - [ ] | Junction: focuser ↔ connection interface |
| `filter_wheel.csv` | - [ ] | ZWO EFW series |
| `filter_wheel_interface.csv` | - [ ] | Junction: filter wheel ↔ connection interface |
| `oag.csv` | - [ ] | ZWO OAG, etc. |
| `guide_scope.csv` | - [ ] | Mini guide scopes |
| `computer.csv` | - [ ] | ASIAIR Plus, mini PCs |
| `software.csv` | - [ ] | N.I.N.A., PHD2, PixInsight, ASTAP, etc. |

### Alias Tables

| File | Status | Notes |
|------|--------|-------|
| `camera_alias.csv` | - [ ] | FITS INSTRUME header mappings |
| `telescope_alias.csv` | - [ ] | FITS TELESCOP header mappings |
| `filter_alias.csv` | - [ ] | FITS FILTER header mappings |

## Seed Key Convention

Format: `{table}.{manufacturer_or_brand}.{model_slug}`

Examples:
- `manufacturer.zwo`
- `sensor.sony.imx571`
- `camera.zwo.asi2600mm_pro`
- `telescope.celestron.c11`
- `telescope_configuration.celestron.c11.native`
- `filter.optolong.l_extreme`

Lookup tables use: `{table}.{slug}` (e.g., `optical_design.sct`, `connector_size.m54`)

## Test Plan

- `test_hash.py` — canonical hash values, type encoding, key ordering, rejection of NaN/bytes
- `test_csv_reader.py` — parsing, header validation, comment lines, FK column detection
- `test_first_run.py` — in-memory SQLite, full load, verify all rows present
- `test_reseed_unchanged.py` — second run with identical CSVs → all UNCHANGED
- `test_reseed_user_modified.py` — modify row in DB, re-run → SKIPPED_USER_MODIFIED
- `test_reseed_csv_changed.py` — modify CSV, re-run → UPDATED
- `test_parent_child.py` — telescope + configurations loaded coherently
- `test_junction.py` — junction table delete-and-reinsert on parent update
- `test_orphaned.py` — row in DB not in CSV → ORPHANED_SEED, not deleted
- `test_fk_resolution.py` — missing FK seed_key → abort with clear error
- `test_transaction_rollback.py` — injected error → no partial state in DB
