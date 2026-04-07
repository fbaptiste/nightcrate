# Equipment Database Schema — Design Spec

**Version:** 0.8.0
**Date:** 2026-04-06

## Summary

Creates the full normalized equipment database for NightCrate. Schema only — no API, no UI, no seed loader, no FITS resolver. Covers telescopes, cameras, sensors, filters, mounts, focusers, filter wheels, OAGs, guide scopes, computers, and software.

Based on the comprehensive revision spec reviewed by Claude Desktop, incorporating normalization improvements, seed tracking infrastructure, FITS ingest alias tables, and closed-vocabulary CHECK constraints.

## Scope

- **Schema only** — migration script, triggers, views, indexes
- **No API endpoints** — CRUD comes in v0.9.0
- **No frontend** — Equipment page comes in v0.9.0
- **No seed loader** — separate spec, future version
- **No FITS resolver** — separate spec, future version

## Key Design Decisions

1. **No custom fields** — `custom_fields` JSON column and `custom_field_definition` table removed. Add real columns via migration when needed.

2. **Filter hierarchy rewrite** — `filter_type` is a closed vocabulary of roles (narrowband_single, broadband_color, etc.). Wavelengths/bandwidths live in `filter_passband` on the physical filter. `filter_category` and `filter_type_band` tables eliminated.

3. **Telescope configurations are the source of truth for focal length** — `telescope` carries only identity (manufacturer, model, aperture, optical design). All focal length/ratio/back_focus data lives on `telescope_configuration`. Every telescope must have at least one config with `is_native=1`.

4. **Software manufacturer normalized** — `software.developer` (free text) replaced by `software.manufacturer_id` FK to `manufacturer`.

5. **Camera connectivity normalized** — `camera.connectivity`/`camera.usb_hub` text fields replaced by `camera_interface` junction table + `has_usb_hub` boolean + `usb_hub_interface_id` FK.

6. **Seed tracking on every table** — `created_at`, `updated_at`, `active`, `source`, `seed_key`, `seed_hash` columns. `updated_at` trigger per table. Partial unique index on `seed_key`.

7. **FITS alias tables** — `camera_alias`, `telescope_alias`, `filter_alias` for auto-resolving FITS headers. Plus `unresolved_equipment_observation` for unknown headers.

8. **Closed vocabularies via CHECK** — `filter_type.name`, `filter_passband.line_name`, `software.category`, `connection_interface.category`, `sensor.bayer_pattern`. Extended only via migration.

9. **Lookup tables for open vocabularies** — `manufacturer`, `optical_design`, `mount_type`, `connection_interface`, `connector_size`, `filter_size`, `computer_type`.

## Tables Created

### Lookup / Reference (9)

| Table | Key columns |
|-------|-------------|
| `manufacturer` | name UNIQUE, website, notes |
| `optical_design` | name UNIQUE, description |
| `mount_type` | name UNIQUE, description |
| `connection_interface` | name UNIQUE, category CHECK (data/control/power/wireless) |
| `connector_size` | name UNIQUE, diameter_mm |
| `filter_size` | name UNIQUE, description |
| `computer_type` | name UNIQUE, description |
| `filter_type` | name UNIQUE + CHECK constraint (9 values), description |
| `seed_loader_meta` | key/value store for hash contract version and seed timestamps |

### Equipment (11)

| Table | Key relationships |
|-------|-------------------|
| `sensor` | → manufacturer. UNIQUE(manufacturer_id, model_name) |
| `camera` | → manufacturer, sensor, connector_size. has_usb_hub + usb_hub_interface_id |
| `telescope` | → manufacturer, optical_design. No focal length (that's on config) |
| `telescope_configuration` | → telescope. is_native + partial unique index |
| `filter` | → manufacturer, filter_type, filter_size |
| `mount` | → manufacturer, mount_type |
| `focuser` | → manufacturer |
| `filter_wheel` | → manufacturer, filter_size, connector_size (both sides) |
| `oag` | → manufacturer, connector_size (both sides) |
| `guide_scope` | → manufacturer, connector_size |
| `computer` | → manufacturer, computer_type |
| `software` | → manufacturer. category CHECK |

### Child / Passband (2)

| Table | Parent |
|-------|--------|
| `filter_passband` | → filter. line_name CHECK constraint |
| `telescope_connector` | → telescope, connector_size |

### Junction (5)

| Table | Links |
|-------|-------|
| `camera_interface` | camera ↔ connection_interface |
| `mount_interface` | mount ↔ connection_interface |
| `focuser_interface` | focuser ↔ connection_interface |
| `filter_wheel_interface` | filter_wheel ↔ connection_interface |
| `telescope_connector` | telescope ↔ connector_size |

### FITS Alias (4)

| Table | Purpose |
|-------|---------|
| `camera_alias` | INSTRUME header → camera row |
| `telescope_alias` | TELESCOP header → telescope row |
| `filter_alias` | FILTER header → filter row |
| `unresolved_equipment_observation` | Unknown header values pending user review |

### Views (1)

| View | Purpose |
|------|---------|
| `filter_summary` | Joins filter + filter_type + filter_passband with passband_count, wavelength ranges, GROUP_CONCAT of line names |

## Migration Seeded Data

The migration seeds `filter_type` with these 9 rows (`source='seed'`):

- broadband_luminance, broadband_color
- narrowband_single, narrowband_dual, narrowband_tri
- uv_ir_cut, light_pollution, neutral_density, other

`seed_hash` is left NULL — the seed loader will populate it on first run.

## Closed Vocabularies

These are extended only via migration:

- **`filter_type.name`**: broadband_luminance, broadband_color, narrowband_single, narrowband_dual, narrowband_tri, uv_ir_cut, light_pollution, neutral_density, other
- **`filter_passband.line_name`**: Ha, Hb, Oiii, Sii, Nii, OI, Lum, R, G, B, UVIR, LP, ND, other
- **`software.category`**: capture, guiding, processing, planetarium, plate_solving, utility, other
- **`connection_interface.category`**: data, control, power, wireless
- **`sensor.bayer_pattern`**: RGGB, GRBG, GBRG, BGGR (or NULL for mono)
- **`sensor.sensor_type`**: mono, color

## Testing

- Migration applies cleanly to empty database
- Migration applies cleanly to existing v0.7.0 database (with existing tables)
- CHECK constraints enforced for all closed vocabularies
- Partial unique indexes work (seed_key WHERE NOT NULL, is_native per telescope)
- ON DELETE CASCADE propagates (telescope → configs, filter → passbands, etc.)
- updated_at triggers fire on UPDATE
- filter_summary view returns correct aggregated data
- filter_type seed rows present after migration
- Bayer pattern constraint: mono sensor cannot have bayer_pattern, color must have one

## What's NOT in This Version

- API endpoints (v0.9.0)
- Frontend Equipment page (v0.9.0)
- Seed loader (separate spec)
- FITS resolver (separate spec)
- Seed data CSV files
- Rig/project/session/sub_frame tables (separate spec)
