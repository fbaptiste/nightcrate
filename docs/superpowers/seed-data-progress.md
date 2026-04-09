# Seed Data Population Progress

Tracking which CSV files have been populated with real data.

## Lookup Tables

| # | File | Status | Notes |
|---|------|--------|-------|
| 1 | `filter_type.csv` | DONE | 9 types, open vocabulary with display_name |
| 2 | `computer_type.csv` | DONE | 3 types: Imaging, Processing, Control |
| 3 | `mount_type.csv` | DONE | 5 types: German EQ, Harmonic EQ, Alt-Az, Fork, Star Tracker |
| 4 | `optical_design.csv` | DONE | 10 designs: SCT, Newtonian, RC, Doublet/Triplet/Quad Refractor, Petzval, Mak-Cass, DK/CDK, RASA |
| 5 | `connection_interface.csv` | DONE | 9 interfaces: USB 3.0 Type-B/C, USB 2.0/Micro-B, WiFi, Bluetooth, Ethernet, ST-4, Serial |
| 6 | `connector_size.csv` | DONE | 10 sizes: M54, M48, T2, 2", 1.25", 3", M68, M72, SCT, Large SCT |
| 7 | `filter_size.csv` | DONE | 5 sizes: 1.25", 36mm, 2", 50mm Round, 50mm Square |
| 8 | `manufacturer.csv` | DONE | 26 manufacturers |

## Simple Equipment

| # | File | Status | Notes |
|---|------|--------|-------|
| 9 | `software.csv` | TODO | Expand from 2 |
| 10 | `computer.csv` | TODO | Empty |
| 11 | `mount.csv` | TODO | Expand from 1 |
| 12 | `mount_interface.csv` | TODO | Follows mount |
| 13 | `focuser.csv` | TODO | Empty |
| 14 | `focuser_interface.csv` | TODO | Follows focuser |
| 15 | `filter_wheel.csv` | TODO | Empty |
| 16 | `filter_wheel_interface.csv` | TODO | Follows filter_wheel |
| 17 | `oag.csv` | TODO | Empty |
| 18 | `guide_scope.csv` | TODO | Empty |

## Complex Equipment (needs spec research)

| # | File | Status | Notes |
|---|------|--------|-------|
| 19 | `sensor.csv` | TODO | Expand from 2 |
| 20 | `camera.csv` | TODO | Expand from 2 |
| 21 | `camera_interface.csv` | TODO | Follows camera |
| 22 | `telescope.csv` | TODO | Expand from 1 |
| 23 | `telescope_connector.csv` | TODO | Follows telescope |
| 24 | `telescope_configuration.csv` | TODO | Follows telescope |
| 25 | `filter.csv` | TODO | Expand from 2 |
| 26 | `filter_passband.csv` | TODO | Follows filter |

## Alias Tables

| # | File | Status | Notes |
|---|------|--------|-------|
| 27 | `camera_alias.csv` | TODO | FITS INSTRUME strings |
| 28 | `telescope_alias.csv` | TODO | FITS TELESCOP strings |
| 29 | `filter_alias.csv` | TODO | FITS FILTER strings |
