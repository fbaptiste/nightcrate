# Seed Data Population — Next Steps

## Current State

**Branch:** `v0.10.1/seed-data-population`
**Version:** 0.10.1 (not yet bumped/finalized)
**No commits yet this session** — all changes are uncommitted in the working tree.

### What's done

**Lookup tables (9/9):** All complete including new focuser_type (3 types).

**Equipment tables done (10/10 simple equipment):**
- software (44), computer (16), mount (54 + 140 junctions), focuser (21 + 30 junctions), filter_wheel (24 + 23 junctions), oag (13), guide_scope (8)

**Equipment tables TODO (complex, need spec research):**
- telescope — OTA list prepared for Claude Desktop research (38 OTAs across Celestron, Sky-Watcher, Askar, William Optics, Sharpstar, Explore Scientific)
- sensor — needs expansion from 2 test rows
- camera — needs expansion from 2 test rows
- filter + filter_passband — needs expansion from 2 test rows

**Alias tables TODO (3):** camera_alias, telescope_alias, filter_alias

### Schema changes made (uncommitted)

- `source_url TEXT` added to 10 equipment tables (migration 0005 + DDL)
- `focuser_type` lookup table added (migration 0005 + DDL)
- `focuser_type_id` FK added to `focuser` table
- Full stack updates: registry, Pydantic models, API endpoints, frontend types, detail panels
- Show/hide retired items toggle + restore button on all equipment lists and lookup tables
- Expandable read-only detail panels on all equipment lists (click row to see full specs)
- External links styled with primary.light color + open-in-new-tab icon
- DataGrid pagination removed (full load with scroll)

### UI improvements made (uncommitted)

- `EquipmentList` has `renderDetail` prop — click any row to see read-only detail panel
- `EquipmentList` has `showRetired` toggle — shows dimmed retired items with restore button
- `LookupTablesPanel` has same show/hide retired + restore per section
- `ExternalLink` shared component for consistent link styling
- `DetailField` shared component for label/value pairs in detail panels

### What's next

1. **Telescopes** — Claude Desktop is researching 38 OTAs. Handoff will include telescope.csv + telescope_connector.csv + telescope_configuration.csv
2. **Sensors** — IMX series specs (pixel size, resolution, QE, read noise, etc.)
3. **Cameras** — ZWO ASI, QHY, Player One (cooling, weight, back focus, connectors)
4. **Filters + passbands** — Optolong, Antlia, ZWO, Chroma, Baader narrowband + LRGB sets
5. **Alias tables** — FITS header string mappings (last)

### When resuming

1. `git checkout v0.10.1/seed-data-population`
2. Check `docs/superpowers/seed-data-progress.md` for current status
3. Check `LLM_DB_SPECS.md` for schema reference (may need regenerating if schema changed)
4. Wait for Claude Desktop handoffs for telescope/sensor/camera/filter data
5. After all tables populated, delete DB, run `make dev`, verify data loads, test re-seed
6. Commit all changes, then finalize with `finalize-session` skill
