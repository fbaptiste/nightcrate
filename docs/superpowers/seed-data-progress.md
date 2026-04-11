# Seed Data Population Progress

Tracking which CSV files have been populated with real data.

## Lookup Tables — ALL DONE

| # | File | Rows | Status |
|---|------|------|--------|
| 1 | `filter_type.csv` | 9 | DONE |
| 2 | `form_factor.csv` | 5 | DONE |
| 3 | `focuser_type.csv` | 3 | DONE |
| 4 | `mount_type.csv` | 5 | DONE |
| 5 | `optical_design.csv` | 10 | DONE |
| 6 | `connection_interface.csv` | 9 | DONE |
| 7 | `connector_size.csv` | 10 | DONE |
| 8 | `filter_size.csv` | 5 | DONE |
| 9 | `manufacturer.csv` | 58 | DONE |

## Equipment Tables

| # | File | Rows | Status |
|---|------|------|--------|
| 10 | `software.csv` | 44 | DONE |
| 11 | `computer.csv` | 16 | DONE |
| 12 | `mount.csv` | 54 | DONE |
| 13 | `mount_interface.csv` | 140 | DONE |
| 14 | `focuser.csv` | 21 | DONE |
| 15 | `focuser_interface.csv` | 30 | DONE |
| 16 | `filter_wheel.csv` | 24 | DONE |
| 17 | `filter_wheel_interface.csv` | 23 | DONE |
| 18 | `oag.csv` | 13 | DONE |
| 19 | `guide_scope.csv` | 8 | DONE |
| 20 | `sensor.csv` | 2 | TODO — needs full expansion |
| 21 | `camera.csv` | 2 | TODO — needs full expansion |
| 22 | `camera_interface.csv` | 2 | TODO — follows camera |
| 23 | `telescope.csv` | 1 | TODO — OTA list prepared for Claude Desktop research |
| 24 | `telescope_connector.csv` | 1 | TODO — follows telescope |
| 25 | `telescope_configuration.csv` | 2 | TODO — follows telescope |
| 26 | `filter.csv` | 2 | TODO — needs full expansion |
| 27 | `filter_passband.csv` | 2 | TODO — follows filter |

## Alias Tables

| # | File | Rows | Status |
|---|------|------|--------|
| 28 | `camera_alias.csv` | 0 | TODO |
| 29 | `telescope_alias.csv` | 0 | TODO |
| 30 | `filter_alias.csv` | 0 | TODO |

## Schema Changes in This Version

- `source_url` column added to 10 equipment tables
- `focuser_type` lookup table added (3 types: Focus Motor, Integrated Motorized, Manual)
- `focuser_type_id` FK added to `focuser` table
- `form_factor` replaced `computer_type` (full rename)
- `filter_type` CHECK constraint removed (user-extensible), `display_name` column added
- `broadband_luminance` renamed to `luminance`
