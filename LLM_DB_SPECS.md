# NightCrate Equipment Database — Schema & CSV Reference

**NightCrate version:** 0.33.0

## Overview

NightCrate stores astrophotography equipment in a normalized SQLite database. Seed data is loaded from CSV files. Each CSV has a `seed_key` column (a human-readable unique identifier) used to track rows across seed updates. Foreign keys between tables are expressed in CSVs as `*_seed_key` references (e.g., `manufacturer_seed_key`) which the loader resolves to integer IDs at import time.

**CSV rules:**
- Empty cells = NULL
- Booleans = `0` or `1`
- Floats use `.` decimal separator
- Lines starting with `#` are comments (ignored)
- `seed_key` format: `{table}.{manufacturer_or_brand}.{model_slug}` (e.g., `camera.zwo.asi2600mm_pro`)
- Lookup table seed_keys: `{table}.{slug}` (e.g., `optical_design.sct`)

**Scope:** Common amateur astrophotography gear — popular ZWO/QHY/Player One cameras, common Celestron/Askar/Sky-Watcher/William Optics telescopes, popular mounts, standard filter sets, common accessories.

---

## SQL Schema

Schema lives across yoyo migrations `0005.equipment_schema.sql` (core equipment), `0006.camera_guide_sensor.sql` (guide-sensor FK on camera + effective specs), `0007.locations.sql` (user imaging locations), `0009.rig.sql` (rig builder), and `0010.rig_summary_telescope_id.sql` (recreates the rig view). All seeded tables share common columns: `id` (PK), `created_at`, `updated_at`, `active` (soft delete), `source` ('seed'/'user'), `seed_key`, `seed_hash`. Owned equipment tables (see "My Equipment" note below) additionally carry `is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1))` — user-managed, not seeded, not part of the hash contract. These common columns are omitted from the field descriptions below — only data columns are listed.

**My Equipment (v0.12.0):** 10 equipment tables — `camera`, `telescope`, `filter`, `mount`, `focuser`, `filter_wheel`, `oag`, `guide_scope`, `computer`, `software` — have an `is_mine` flag the user toggles to mark gear they personally own. Sensors and lookup tables do NOT have `is_mine`. CSV seed files do NOT contain `is_mine` — leave it out.

```sql
-- Schema assembled from migrations 0005, 0006, 0007, 0009, 0010.

-- LOOKUP TABLES

CREATE TABLE manufacturer (name TEXT UNIQUE, website TEXT, notes TEXT);
CREATE TABLE optical_design (name TEXT UNIQUE, description TEXT);
CREATE TABLE mount_type (name TEXT UNIQUE, description TEXT);
CREATE TABLE connection_interface (name TEXT UNIQUE, category TEXT CHECK (IN 'data','control','power','wireless'), notes TEXT);
CREATE TABLE connector_size (name TEXT UNIQUE, diameter_mm REAL, notes TEXT);
CREATE TABLE filter_size (name TEXT UNIQUE, description TEXT);
CREATE TABLE form_factor (name TEXT UNIQUE, description TEXT);
CREATE TABLE focuser_type (name TEXT UNIQUE, notes TEXT);
CREATE TABLE filter_type (name TEXT UNIQUE, display_name TEXT, description TEXT);

-- EQUIPMENT TABLES

CREATE TABLE sensor (manufacturer_id FK, model_name TEXT, sensor_type CHECK ('mono','color'),
    pixel_size_um REAL, resolution_x INT, resolution_y INT, sensor_width_mm REAL,
    sensor_height_mm REAL, adc_bit_depth INT, full_well_capacity_ke REAL,
    read_noise_e REAL, peak_qe_pct REAL, bayer_pattern CHECK ('RGGB','BGGR','GRBG','GBRG'),
    dual_gain BOOL, hcg_threshold_gain INT, notes TEXT);

CREATE TABLE camera (manufacturer_id FK, sensor_id FK, guide_sensor_id FK nullable,
    connector_size_id FK nullable, model_name TEXT, cooled BOOL, cooling_delta_c REAL,
    back_focus_mm REAL, weight_g REAL, tilt_adapter BOOL, has_usb_hub BOOL,
    usb_hub_interface_id FK nullable, unity_gain INT,
    -- Vendor-tuned photometric overrides (camera-level, take precedence over sensor baseline)
    effective_full_well_ke REAL, effective_read_noise_lcg_e REAL,
    effective_read_noise_hcg_e REAL, effective_peak_qe_pct REAL, hcg_threshold_gain INT,
    notes TEXT, source_url TEXT);
-- junction: camera_interface (camera_id, interface_id → connection_interface)

CREATE TABLE telescope (manufacturer_id FK, optical_design_id FK nullable, model_name TEXT,
    aperture_mm REAL, image_circle_mm REAL, weight_kg REAL, obstruction_pct REAL, notes TEXT);
-- junction: telescope_connector (telescope_id, connector_size_id)

CREATE TABLE telescope_configuration (telescope_id FK, config_name TEXT, accessory_name TEXT,
    reduction_factor REAL DEFAULT 1.0, effective_focal_length_mm REAL,
    effective_focal_ratio REAL, effective_image_circle_mm REAL,
    effective_back_focus_mm REAL, is_native BOOL, notes TEXT);
-- child of telescope; every telescope needs at least one config with is_native=1

CREATE TABLE filter (manufacturer_id FK, filter_type_id FK,
    model_name TEXT, peak_transmission_pct REAL, notes TEXT);

CREATE TABLE filter_passband (filter_id FK, line_name CHECK ('Ha','Hb','Oiii','Sii','Nii','OI',
    'Lum','R','G','B','UVIR','LP','ND','other'), central_wavelength_nm REAL,
    bandwidth_nm REAL, peak_transmission_pct REAL);
-- child of filter; dual/tri-band filters have multiple passband rows

CREATE TABLE filter_size_option (filter_id FK, filter_size_id FK,
    mounted_thickness_mm REAL, notes TEXT);
-- child of filter; one row per physical size option this filter product ships in

CREATE TABLE mount (manufacturer_id FK, mount_type_id FK nullable, model_name TEXT,
    payload_capacity_kg REAL, mount_weight_kg REAL, counterweight_required BOOL,
    goto_capable BOOL, periodic_error_arcsec REAL, drive_type TEXT,
    worm_period_seconds REAL, notes TEXT);
-- junction: mount_interface (mount_id, interface_id → connection_interface)

CREATE TABLE focuser (manufacturer_id FK, focuser_type_id FK nullable, model_name TEXT,
    motorized BOOL, travel_range_mm REAL, step_size_um REAL, total_steps INT,
    temperature_compensation BOOL, backlash_steps INT, notes TEXT);
-- junction: focuser_interface (focuser_id, interface_id → connection_interface)

CREATE TABLE filter_wheel (manufacturer_id FK, filter_size_id FK nullable,
    camera_side_connector_id FK nullable, telescope_side_connector_id FK nullable,
    model_name TEXT, num_positions INT, back_focus_contribution_mm REAL, notes TEXT);
-- junction: filter_wheel_interface (filter_wheel_id, interface_id → connection_interface)

CREATE TABLE oag (manufacturer_id FK, imaging_side_connector_id FK nullable,
    guide_camera_connector_id FK nullable, model_name TEXT, prism_size_mm REAL,
    back_focus_contribution_mm REAL, weight_g REAL, notes TEXT);

CREATE TABLE guide_scope (manufacturer_id FK, guide_camera_connector_id FK nullable,
    model_name TEXT, aperture_mm REAL, focal_length_mm REAL, weight_g REAL, notes TEXT);

CREATE TABLE computer (manufacturer_id FK, form_factor_id FK nullable, model_name TEXT, notes TEXT);

CREATE TABLE software (manufacturer_id FK, name TEXT, category CHECK ('capture','guiding',
    'processing','planetarium','plate_solving','utility','other'), website TEXT, notes TEXT);

-- ALIAS TABLES (no seed_key column; use alias as natural key)
CREATE TABLE camera_alias (camera_id FK, alias TEXT UNIQUE, source CHECK, confirmed BOOL);
CREATE TABLE telescope_alias (telescope_id FK, alias TEXT UNIQUE, source CHECK, confirmed BOOL);
CREATE TABLE filter_alias (filter_id FK, alias TEXT UNIQUE, source CHECK, confirmed BOOL);

-- ============================================================
-- USER DATA (NOT seeded — do not author CSV files for these)
-- ============================================================

-- Imaging locations (migrations 0007, 0012; inline-edited in v0.12.0).
CREATE TABLE location (name TEXT UNIQUE, latitude REAL, longitude REAL, elevation_m REAL,
    timezone TEXT, geo_timezone TEXT,
    bortle_class INT CHECK (1..9), sqm_reading REAL CHECK (10..25),
    typical_seeing_low_arcsec REAL, typical_seeing_high_arcsec REAL,
    city TEXT, state_province TEXT, country TEXT, postal_code TEXT,
    is_default BOOL, active BOOL,  -- v0.12.1 soft-delete
    notes TEXT);

-- Rigs (migration 0009; v0.12.0). User-composed equipment templates.
CREATE TABLE rig (name TEXT UNIQUE, description TEXT,
    telescope_configuration_id FK, camera_id FK,
    filter_wheel_id FK nullable, single_filter_id FK nullable,
    mount_id FK nullable, focuser_id FK nullable, oag_id FK nullable,
    guide_scope_id FK nullable, guide_camera_id FK nullable, computer_id FK nullable,
    is_default BOOL, active BOOL, notes TEXT);

CREATE TABLE rig_filter_slot (rig_id FK CASCADE, slot_number INT CHECK (>=1),
    filter_id FK, UNIQUE(rig_id, slot_number), UNIQUE(rig_id, filter_id));

CREATE TABLE rig_software (rig_id FK CASCADE, software_id FK, PRIMARY KEY (rig_id, software_id));

-- rig_summary: convenience view joining equipment names + guide-camera sensor for list rendering.
-- Recreated in migration 0010 to expose telescope_id for the Equipment tab's detail fetch.
-- Recreated in migration 0013 to expose sensor_adc_bit_depth for the File Size calculator.
```

---

## Populated Lookup Tables

### manufacturer.csv (57 rows)
Header: `seed_key,name,notes,website`

Seed_keys: `manufacturer.zwo`, `manufacturer.celestron`, `manufacturer.optolong`, `manufacturer.sony`, `manufacturer.pegasus_astro`, `manufacturer.qhy`, `manufacturer.skywatcher`, `manufacturer.ioptron`, `manufacturer.askar`, `manufacturer.sharpstar`, `manufacturer.antlia`, `manufacturer.chroma`, `manufacturer.baader`, `manufacturer.william_optics`, `manufacturer.starizona`, `manufacturer.primalucelab`, `manufacturer.takahashi`, `manufacturer.player_one`, `manufacturer.touptek`, `manufacturer.warpastron`, `manufacturer.planewave`, `manufacturer.explore_scientific`, `manufacturer.ts_optics`, `manufacturer.rainbow_astro`, `manufacturer.open_source`, `manufacturer.freeware`, `manufacturer.pleiades_astrophoto`, `manufacturer.sharpcap`, `manufacturer.main_sequence`, `manufacturer.ideiki`, `manufacturer.starkeeper`, `manufacturer.rc_astro`, `manufacturer.aries_productions`, `manufacturer.ascom_initiative`, `manufacturer.simulation_curriculum`, `manufacturer.diffraction_limited`, `manufacturer.adobe`, `manufacturer.serif`, `manufacturer.topaz_labs`, `manufacturer.nina_project`, `manufacturer.open_phd_guiding`, `manufacturer.seti_astro`, `manufacturer.emil_kraaikamp`, `manufacturer.han_kleijn`, `manufacturer.ilanga`, `manufacturer.stellarmate`, `manufacturer.software_bisque`, `manufacturer.losmandy`, `manufacturer.astro_physics`, `manufacturer.10micron`, `manufacturer.vixen`, `manufacturer.msm`, `manufacturer.generic`, `manufacturer.rigel_systems`, `manufacturer.lacerta`, `manufacturer.deep_sky_dad`, `manufacturer.moonlite`

### optical_design.csv (10 rows)
Header: `seed_key,description,name`

Seed_keys: `optical_design.sct` (SCT), `optical_design.newtonian` (Newtonian), `optical_design.rc` (RC), `optical_design.doublet_refractor` (Doublet Refractor), `optical_design.triplet_refractor` (Triplet Refractor), `optical_design.quadruplet_refractor` (Quadruplet Refractor), `optical_design.petzval` (Petzval), `optical_design.mak_cass` (Maksutov-Cassegrain), `optical_design.dk` (Dall-Kirkham / CDK), `optical_design.rasa` (RASA)

### mount_type.csv (5 rows)
Header: `seed_key,description,name`

Seed_keys: `mount_type.german_eq` (German Equatorial), `mount_type.harmonic_eq` (Harmonic Equatorial), `mount_type.alt_az` (Alt-Azimuth), `mount_type.fork` (Fork), `mount_type.star_tracker` (Star Tracker)

### connection_interface.csv (9 rows)
Header: `seed_key,category,name,notes`

Seed_keys: `connection_interface.usb_3_0` (USB 3.0 Type-B, data), `connection_interface.usb_2_0` (USB 2.0, data), `connection_interface.usb_3_0_type_c` (USB 3.0 Type-C, data), `connection_interface.usb_2_0_micro_b` (USB 2.0 Micro-B, data), `connection_interface.wifi` (WiFi, wireless), `connection_interface.bluetooth` (Bluetooth, wireless), `connection_interface.ethernet` (Ethernet, data), `connection_interface.st4` (ST-4, control), `connection_interface.serial_rs232` (Serial RS-232, data)

### connector_size.csv (10 rows)
Header: `seed_key,diameter_mm,name,notes`

Seed_keys: `connector_size.m54` (54mm), `connector_size.m48` (48mm), `connector_size.t2` (42mm, M42x0.75), `connector_size.2_inch` (50.8mm), `connector_size.1_25_inch` (31.75mm), `connector_size.3_inch` (76.2mm), `connector_size.m68` (68mm), `connector_size.m72` (72mm), `connector_size.sct` (50.8mm, SCT 2"-24 TPI), `connector_size.large_sct` (83.6mm, SCT Large 3.29"-16 TPI)

### filter_size.csv (5 rows)
Header: `seed_key,description,name`

Seed_keys: `filter_size.1_25_inch` (1.25 inch), `filter_size.36mm` (36mm), `filter_size.2_inch` (2 inch), `filter_size.50mm_round` (50mm Round), `filter_size.50mm_square` (50mm Square)

### form_factor.csv (5 rows)
Header: `seed_key,description,name`

Seed_keys: `form_factor.dedicated_controller` (Dedicated Controller), `form_factor.mini_pc` (Mini PC), `form_factor.laptop` (Laptop), `form_factor.desktop` (Desktop), `form_factor.sbc` (Single-Board Computer)

### focuser_type.csv (3 rows)
Header: `seed_key,name,notes`

Seed_keys: `focuser_type.focus_motor` (Focus Motor), `focuser_type.integrated_motorized` (Integrated Motorized), `focuser_type.manual` (Manual)

### filter_type.csv (9 rows)
Header: `seed_key,description,display_name,name`

Seed_keys: `filter_type.luminance` (Luminance), `filter_type.broadband_color` (Broadband Color), `filter_type.narrowband_single` (Narrowband Single), `filter_type.narrowband_dual` (Narrowband Dual), `filter_type.narrowband_tri` (Narrowband Tri), `filter_type.uv_ir_cut` (UV/IR Cut), `filter_type.light_pollution` (Light Pollution), `filter_type.neutral_density` (Neutral Density), `filter_type.other` (Other)

---

## Populated Equipment Tables

### software.csv (44 rows)
Header: `seed_key,manufacturer_seed_key,category,name,notes,website`

Seed_keys: `software.nina`, `software.sgp`, `software.apt`, `software.voyager`, `software.sharpcap`, `software.ekos`, `software.maximdl`, `software.firecapture`, `software.nina_hocus_focus`, `software.nina_tppa`, `software.nina_ground_station`, `software.nina_target_scheduler`, `software.phd2`, `software.metaguide`, `software.pixinsight`, `software.siril`, `software.dss`, `software.app`, `software.graxpert`, `software.bxt`, `software.nxt`, `software.sxt`, `software.seti_astro_suite`, `software.starnet`, `software.photoshop`, `software.affinity_photo`, `software.topaz_photo_ai`, `software.autostakkert`, `software.registax`, `software.pipp`, `software.winjupos`, `software.imppg`, `software.stellarium`, `software.kstars`, `software.theskyx`, `software.skysafari`, `software.cartes_du_ciel`, `software.astap`, `software.astrometry_net`, `software.platesolve2`, `software.ascom`, `software.indi`, `software.eqmod`, `software.astroplanner`

### computer.csv (16 rows)
Header: `seed_key,form_factor_seed_key,manufacturer_seed_key,model_name,notes`

Seed_keys: `computer.zwo.asiair`, `computer.zwo.asiair_mini`, `computer.zwo.asiair_pro`, `computer.zwo.asiair_plus_32gb`, `computer.zwo.asiair_plus_256gb`, `computer.primalucelab.eagle3`, `computer.primalucelab.eagle4_s`, `computer.primalucelab.eagle4`, `computer.primalucelab.eagle4_pro`, `computer.primalucelab.eagle5_s`, `computer.primalucelab.eagle5`, `computer.primalucelab.eagle5_pro`, `computer.stellarmate.plus`, `computer.stellarmate.pro`, `computer.stellarmate.x`, `computer.touptek.stellavita`

### mount.csv (54 rows)
Header: `seed_key,manufacturer_seed_key,mount_type_seed_key,counterweight_required,drive_type,goto_capable,model_name,mount_weight_kg,notes,payload_capacity_kg,periodic_error_arcsec,worm_period_seconds`

Seed_keys: `mount.zwo.am3`, `mount.zwo.am3n`, `mount.zwo.am5`, `mount.zwo.am5n`, `mount.zwo.am7`, `mount.skywatcher.heq5_pro`, `mount.skywatcher.eq6_r_pro`, `mount.skywatcher.cq350_pro`, `mount.skywatcher.eq8_r_pro`, `mount.skywatcher.eq8_rh_pro`, `mount.skywatcher.az_eq6`, `mount.skywatcher.wave_100i`, `mount.skywatcher.wave_150i`, `mount.skywatcher.star_adventurer_2i`, `mount.skywatcher.star_adventurer_gti`, `mount.ioptron.cem26`, `mount.ioptron.cem40`, `mount.ioptron.cem70`, `mount.ioptron.gem28`, `mount.ioptron.gem45`, `mount.ioptron.hem27`, `mount.ioptron.hem44`, `mount.ioptron.hae29`, `mount.ioptron.hae43`, `mount.ioptron.hae69`, `mount.ioptron.skyguider_pro`, `mount.celestron.avx`, `mount.celestron.cgem_ii`, `mount.celestron.cgx`, `mount.celestron.cgx_l`, `mount.warpastron.wd20`, `mount.warpastron.wd20p`, `mount.rainbow_astro.rst135`, `mount.rainbow_astro.rst135e`, `mount.rainbow_astro.rst300`, `mount.pegasus_astro.nyx101`, `mount.takahashi.em200_temma3`, `mount.takahashi.em11_temma2z`, `mount.losmandy.g11`, `mount.losmandy.gm8`, `mount.vixen.sxd2`, `mount.vixen.sxp2`, `mount.explore_scientific.iexos100_2`, `mount.explore_scientific.exos2_pmc8`, `mount.astro_physics.mach2gto`, `mount.astro_physics.ap1100gto`, `mount.10micron.gm1000_hps_ep`, `mount.10micron.gm2000_hps_ii`, `mount.software_bisque.myt`, `mount.software_bisque.mx_series6`, `mount.software_bisque.me_ii`, `mount.planewave.l350`, `mount.planewave.l500`, `mount.msm.nomad`

### mount_interface.csv (140 junction rows)
Header: `interface_seed_key,mount_seed_key`

### focuser.csv (21 rows)
Header: `seed_key,manufacturer_seed_key,focuser_type_seed_key,backlash_steps,model_name,motorized,notes,step_size_um,temperature_compensation,total_steps,travel_range_mm`

Seed_keys: `focuser.zwo.eaf`, `focuser.zwo.eaf_5v`, `focuser.zwo.eafn`, `focuser.zwo.eaf_pro`, `focuser.pegasus_astro.focuscube_v3`, `focuser.pegasus_astro.prodigy`, `focuser.primalucelab.sesto_senso_2`, `focuser.primalucelab.sesto_senso_3`, `focuser.primalucelab.esatto_2`, `focuser.primalucelab.esatto_2_lp`, `focuser.primalucelab.esatto_3`, `focuser.primalucelab.esatto_35_lp`, `focuser.primalucelab.esatto_4`, `focuser.celestron.focus_motor`, `focuser.rigel_systems.wifi_nstep`, `focuser.lacerta.mfoc`, `focuser.deep_sky_dad.af3`, `focuser.moonlite.nitecrawler_wr25`, `focuser.moonlite.nitecrawler_wr30`, `focuser.moonlite.nitecrawler_wr35`, `focuser.generic.manual`

### focuser_interface.csv (30 junction rows)
Header: `focuser_seed_key,interface_seed_key`

---

## Tables with Minimal Test Data (need expansion)

### sensor.csv (2 rows)
Header: `seed_key,manufacturer_seed_key,adc_bit_depth,bayer_pattern,dual_gain,full_well_capacity_ke,hcg_threshold_gain,model_name,notes,peak_qe_pct,pixel_size_um,read_noise_e,resolution_x,resolution_y,sensor_height_mm,sensor_type,sensor_width_mm`

Seed_keys: `sensor.sony.imx571`, `sensor.sony.imx533`

Note: mono and color variants of the same chip need separate rows (sensor_type='mono' vs 'color' with bayer_pattern).

### camera.csv (2 rows)
Header: `seed_key,connector_size_seed_key,guide_sensor_seed_key,manufacturer_seed_key,sensor_seed_key,usb_hub_interface_seed_key,back_focus_mm,cooled,cooling_delta_c,has_usb_hub,model_name,notes,tilt_adapter,unity_gain,weight_g`

Seed_keys: `camera.zwo.asi2600mm_pro`, `camera.zwo.asi533mm_pro`

### camera_interface.csv (2 junction rows)
Header: `camera_seed_key,interface_seed_key`

### telescope.csv (1 row)
Header: `seed_key,manufacturer_seed_key,optical_design_seed_key,aperture_mm,image_circle_mm,model_name,notes,obstruction_pct,weight_kg`

Seed_keys: `telescope.celestron.c11`

### telescope_connector.csv (1 junction row)
Header: `connector_size_seed_key,telescope_seed_key`

### telescope_configuration.csv (2 rows)
Header: `seed_key,telescope_seed_key,accessory_name,config_name,effective_back_focus_mm,effective_focal_length_mm,effective_focal_ratio,effective_image_circle_mm,is_native,notes,reduction_factor`

Seed_keys: `telescope_configuration.celestron.c11.native`, `telescope_configuration.celestron.c11.0_7x`

Every telescope MUST have at least one config with `is_native=1` and `reduction_factor=1.0`.

### filter.csv (2 rows)
Header: `seed_key,filter_type_seed_key,manufacturer_seed_key,model_name,notes,peak_transmission_pct`

Seed_keys: `filter.optolong.ha_7nm`, `filter.optolong.oiii_6_5nm`

### filter_passband.csv (2 rows)
Header: `seed_key,filter_seed_key,bandwidth_nm,central_wavelength_nm,line_name,peak_transmission_pct`

Seed_keys: `filter_passband.optolong.ha_7nm.ha`, `filter_passband.optolong.oiii_6_5nm.oiii`

Dual/tri-band filters have multiple passband rows.

### filter_size_option.csv (child of filter — one row per physical size)
Header: `seed_key,filter_seed_key,filter_size_seed_key,mounted_thickness_mm,notes`

One row per size a filter product is sold in. `mounted_thickness_mm` was previously on the `filter` table; it moved to this child table in the equipment schema revision so the same filter model can carry multiple sizes with per-size thickness.

---

## Empty Tables (need population)

### filter_wheel.csv
Header: `seed_key,camera_side_connector_seed_key,filter_size_seed_key,manufacturer_seed_key,telescope_side_connector_seed_key,back_focus_contribution_mm,model_name,notes,num_positions`

### filter_wheel_interface.csv
Header: `filter_wheel_seed_key,interface_seed_key`

### oag.csv
Header: `seed_key,guide_camera_connector_seed_key,imaging_side_connector_seed_key,manufacturer_seed_key,back_focus_contribution_mm,model_name,notes,prism_size_mm,weight_g`

### guide_scope.csv
Header: `seed_key,guide_camera_connector_seed_key,manufacturer_seed_key,aperture_mm,focal_length_mm,model_name,notes,weight_g`

### camera_alias.csv
Header: `camera_seed_key,alias,confirmed,source`
Maps FITS INSTRUME header values to cameras. source=seed, confirmed=1.

### telescope_alias.csv
Header: `telescope_seed_key,alias,confirmed,source`
Maps FITS TELESCOP header values to telescopes.

### filter_alias.csv
Header: `filter_seed_key,alias,confirmed,source`
Maps FITS FILTER header values to filters (e.g., "Ha", "H-alpha", "Halpha" → same filter).

## User-managed tables (NOT seeded)

The following tables are entirely user-created at runtime — they must **not** have seed CSVs:

- `location` — user's observing sites. Created via the Locations page.
- `location_horizon` and `location_horizon_point` — multi-horizon per location (v0.19.0 reshape of the v0.13.0 1:1 schema). Each location owns ≥1 horizon: at most one `type='custom'` polyline (with ≥2 points in `location_horizon_point`) plus any number of named `type='artificial'` flat-altitude rows (`flat_altitude_deg` in `[-5, 90]`). Exactly one row per location is marked `is_default=1` (partial unique index). Custom imports from N.I.N.A. `.hrz`, Stellarium, Telescopius, APCC, or Theodolite iPhone CSV via the Horizon Editor. `POST /api/locations` auto-seeds a `0° flat` artificial default.
- `rig`, `rig_filter_slot`, `rig_software` — user-composed imaging rigs.

## Loader-populated (not seed-loader) tables

Distinct from the equipment seed loader: the DSO catalog has its own
loader at `backend/src/nightcrate/catalog_loader/` that runs at startup
from files in the user's app-data catalogs folder
(`APP_DIR/catalogs/openngc/`). The repo does **not** ship catalog data;
files land there only after a user-triggered fetch from GitHub via
Admin → Catalogs. Until that fetch happens, these tables are empty.
Once populated, subsequent startups reload silently using a file-hash
idempotency check.

These tables must **not** have seed CSVs and are not part of the
equipment seed loader's hash contract.

- `dso` — canonical deep-sky objects (typical full install: ~13,371 OpenNGC + ~200 standalone Sharpless + ~349 Barnard). v0.15.0 adds `distance_pc` (parsecs), `distance_method` (CHECK ∈ `{'50mgc', 'curated', 'redshift'}`, nullable; precedence is `curated` > `50mgc` > `redshift`, enforced via `WHERE distance_pc IS NULL` in each augmenter), `common_name_augmented`/`surface_brightness_augmented` `{0,1}` provenance flags populated by the NightCrate augmentation CSV.
- `dso_designation` — catalog-specific names attached to each DSO. Closed 29-catalog vocabulary: NGC, IC, Messier, Caldwell, PGC, UGC, MCG, ESO, Arp, HCG, Sharpless2, Barnard, LBN, LDN, vdB, Cederblad, PK, RCW, Gum, Mrk, Terzan, Pal, Mel, Cr, Stock, Ruprecht, Abell, Dolidze, DWB. One `UNIQUE(catalog, identifier)` → designations are globally unique across all DSOs.
- `dso_catalog_source` — loader registry. Stores the sha256 of each source file; matching hashes on subsequent startup skip reloading. v0.15.0 registers 5 additional sources: `vizier_sharpless`, `vizier_barnard` (fetched from CDS VizieR via a 3-mirror fallback), `github_50mgc` (50 MGC FITS fetched from github.com/davidohlson/50MGC rather than VizieR because CDS was flaky), `nightcrate_augment`, `nightcrate_sharpless_crossref`, `nightcrate_barnard_crossref` (bundled in-repo under `backend/src/nightcrate/data/catalogs/nightcrate/`). v0.20.0 (migration 0022) widens the `category` CHECK to include `'wikidata'` and registers two more sources: `wikidata_external_refs` (SPARQL fetch from `query.wikidata.org`, CC0) and `nightcrate_external_refs` (editorial CSV overrides).
- `dso_external_ref` (v0.20.0, migration 0022) — external-knowledge-base links per DSO: Wikidata QIDs (`provider='wikidata'`, no language) and Wikipedia article URLs (`provider='wikipedia', language='en'`). One row per `(dso_id, provider, language)` (UNIQUE); a partial unique index on `(provider, language, identifier) WHERE provider != 'wikipedia'` keeps QIDs globally unique while admitting multi-object Wikipedia articles (Stephan's Quintet). Wikidata QIDs are stored silently for future features; only Wikipedia chips render in the MVP UI. Loader matches Wikidata records to DSOs via `dso_designation.search_key` (P528/P972 canonical form plus P3208/P4095/P6340 direct-ID shortcuts); ambiguous cross-references skip (CSV override is the escape hatch).
- `thumbnail_cache` (v0.16.0 migration 0017, extended by v0.17.0 migration 0018) — metadata for the Target Planner's LRU thumbnail cache. Files live on disk under `APP_DIR/thumbnails/`; rows carry the `dso_id` FK (cascade-delete), `variant` (`list`/`detail`/`rig_framed`/`fov_simulator`), dimensions, nullable `fov_major_deg_x1000` / `fov_minor_deg_x1000` (rounded deg × 1000 as int for rig-dependent variants), `source` (`dss2_color`/`dss2_red`/`dss2_blue`/`placeholder`), byte size, fetched/last-access timestamps, and a nullable `fetch_error` (non-null rows are backoff sentinels that expire after 1 hour). Unique index wraps the FOV columns in `COALESCE(..,-1)` so rig-independent + rig-dependent entries share a namespace. Not seed-loaded — populated entirely by runtime fetches from CDS Aladin's hips2fits.
