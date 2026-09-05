# NightCrate — Equipment & Technical Context

Reference document for development. Describes the developer's actual imaging setup, file formats, directory structures, and workflow patterns that NightCrate must handle.

---

## Imaging Rigs

Fred runs a multi-rig backyard observatory at a suburban site. Three deep-sky rigs exist, but only two can run on a given night: the C6 and the Askar V share a single AM5 mount, so a simultaneous night is the C11 plus **one** of them. Acquisition is split — the C11 runs N.I.N.A. on a Windows mini PC at the scope, while the C6 and Askar V each run a ZWO ASIAIR. All post-capture processing happens on a separate Mac.

The C6 is the current workhorse: it is lighter, and the rig has to be carried out and set up rather than living under a permanent roof, so aperture loses to weight in practice.

### Rig 1: C11 (Primary Deep-Sky Rig)

| Component | Detail |
|-----------|--------|
| **Telescope** | Celestron C11 SCT (280mm f/10, 2800mm FL) with Starizona SCT Corrector **LCF** 0.7x → effective ~f/7, ~1960mm FL |
| **Camera** | ZWO ASI 2600MM Pro (mono) — Sony IMX571, 26MP (6248×4176), 3.76μm pixels, APS-C (23.5×15.7mm), 16-bit ADC, TEC cooling (−35°C delta), USB 3.0 |
| **Image scale** | ~0.40″/pixel |
| **Mount** | WarpAstron WD-20 harmonic equatorial (servo direct drive, 22kg payload no counterweight, OnStep controller) |
| **Guide system** | ZWO OAG-L off-axis guider + ZWO ASI 174MM (Sony IMX174, 2.3MP 1936×1216, 5.86μm, 12-bit ADC). The larger pixels matter here — an ASI 220MM Mini was tried first and found too few stars in the OAG's field |
| **Guiding software** | PHD2 (~1″ RMS typical) |
| **Focuser** | PrimaLuceLab ESATTO 2″ (Crayford, 0.04μm/step resolution, USB-C, ASCOM compatible) |
| **Filters** | Optolong narrowband — Ha 7nm, Oiii 6.5nm, Sii 6.5nm (the Oiii and Sii are **not** 7nm) + ZWO Premium LRGB, in a ZWO EFW 7×2" |
| **Power/hub** | WandererBox Pro V3 (USB hub + power distribution) |
| **Acquisition PC** | Geekom AX8 Max (AMD Ryzen 7 8745HS, 32GB DDR5, 1TB SSD, Windows) |
| **Acquisition software** | N.I.N.A. (Advanced Sequencer), PHD2 |
| **Power supply** | Bluetti EB3A (268Wh) on mains pass-through |

### Rig 2: Askar V (Second Rig)

| Component | Detail |
|-----------|--------|
| **Telescope** | Askar V modular APO refractor — V60 config: 60mm f/6, 360mm FL; V80 config: 80mm f/6.25, 500mm FL; reducer/flattener/extender options covering 270–600mm FL |
| **Camera** | ZWO ASI 2600MM Pro (mono) — second unit, same specs as Rig 1 |
| **Mount** | ZWO AM5 harmonic (13kg payload no CW, WiFi, ASIAIR compatible) — **shared with the C6 rig**, so those two never run on the same night |
| **Guide system** | Askar 52mm SD Super ED guide scope + ZWO ASI 178MM (Sony IMX178, 6.4MP 3096×2080, 2.4μm, 14-bit ADC). The only rig of the three that guides off a scope rather than an OAG |
| **Focuser** | ZWO EAF |
| **Accessories** | ZWO camera rotator, ZWO EFW 7×2" |
| **Filters** | Antlia 3nm Pro narrowband (Ha, Sii, Oiii) + Optolong Red/Green/Blue + a ZWO Premium Luminance — the luminance is ZWO, not Optolong |
| **Controller** | ZWO ASIAIR Plus (32GB) — this is the acquisition controller, not N.I.N.A. |
| **Power supply** | Second Bluetti EB3A on mains pass-through |

### Rig 3: C6 (Current Workhorse)

Built as a complete rig rather than assembled from spares, and the one that goes out most — it is light enough to carry out and set up single-handed.

| Component | Detail |
|-----------|--------|
| **Telescope** | Celestron C6 SCT. **The published 1500mm f/10 is wrong for this OTA** — it plate solves at 1639mm bare and 1667mm with the 1" SCT extension tube (2"-24 TPI) fitted for EAF clearance, i.e. ~f/11. Use the measured value for anything downstream |
| **Camera** | ZWO ASI 533MM Pro (mono) — Sony IMX533, 9MP (3008×3008), 3.76μm pixels, 1" square, 14-bit ADC. HCG mode at gain 101 |
| **Image scale** | 0.465″/pixel, 23′ × 23′ field (at 1667mm) |
| **Mount** | ZWO AM5 harmonic — shared with the Askar V rig |
| **Guide system** | Celestron OAG (#93648) + ZWO ASI 174MM, on USB2 (correct — that camera is natively USB2). The same 174MM serves the C11's OAG; only one of those rigs guides through it on a given night |
| **Focuser** | ZWO EAF (5V) |
| **Filters** | Antlia throughout — LRGB-V Pro (Lum, Red, Green, Blue) + Antlia 3nm Pro (Ha, Sii, Oiii), in a ZWO EFW 8×1.25" |
| **Flats** | WandererAstro White Dwarf panel |
| **Controller** | ZWO ASIAIR Plus (32GB), with a USB thumb drive for storage |

### Smart Scopes (Post-MVP targets)

| Device | Detail |
|--------|--------|
| **ZWO Seestar S30 Pro** | 30mm quad APO, 160mm FL, IMX585 4K sensor, dual wide/tele cameras, 256GB storage |
| **ZWO Seestar S50** | 50mm triplet APO, 250mm FL, IMX662 sensor |

### Guide Cameras In Use

| Camera | Sensor | Resolution | Pixel Size | Rig |
|--------|--------|------------|------------|-----|
| ZWO ASI 174MM | Sony IMX174 | 1936×1216 | 5.86μm | C11 OAG and C6 OAG |
| ZWO ASI 178MM | Sony IMX178 | 3096×2080 | 2.4μm | Askar V, on the 52mm guide scope |

### Additional Cameras (Not Currently Assigned to a Rig)

| Camera | Sensor | Resolution | Pixel Size | Format | Notes |
|--------|--------|------------|------------|--------|-------|
| ZWO ASI 120MM Mini | ON Semi AR0130 | — | 3.75μm | Mono | Guide cam |
| ZWO ASI 220MM Mini | SmartSens SC2210 | — | 4.0μm | Mono | Guide cam; tried on the C11 OAG, too few stars |
| ZWO ASI 294MC Pro | Sony IMX294 | — | 4.63μm | Color, 4/3″ | Color one-shot camera |

---

## Acquisition Software Details

### N.I.N.A. (Rig 1 — C11)

N.I.N.A. (Nighttime Imaging 'N' Astronomy) is the primary capture software for the C11 rig.

**Key file locations on the Windows acquisition PC:**

| What | Path |
|------|------|
| Sequence templates | `Documents\N.I.N.A.\Templates\` (`.template.json` files) |
| Equipment profiles | `%LOCALAPPDATA%\NINA\Profiles\` |
| Image output | User-configured per sequence (typically a date/target folder structure) |
| Autofocus results | JSON files saved alongside image data |
| Session logs | N.I.N.A. log files (text format, timestamped entries) |

**N.I.N.A. Advanced Sequencer behavior:**
- Sequences are built as looping blocks (typically 2–3 hour loops)
- Each loop cycles through filters in a defined order and count
- Events logged include: filter changes, exposures, autofocus runs (with HFR results), plate solves, meridian flips, dither commands, slews, errors/failures
- Autofocus data is saved as JSON files containing HFR measurements, focus position, temperature, and V-curve data

**N.I.N.A. file naming:**
- Default pattern includes target name, filter, exposure, gain, date/time, and frame number
- Users can customize the naming template
- Example: `M101_L_120s_Gain100_-10C_2025-03-15_001.fits`

### ASIAIR (Rigs 2 and 3 — Askar V, C6)

ZWO's ASIAIR is the controller for both of the AM5-mounted rigs. It runs on a dedicated ZWO hardware unit (ARM-based Linux appliance), not a general-purpose PC.

**Key differences from N.I.N.A.:**
- ASIAIR stores data on its internal storage or a USB drive attached to the ASIAIR unit
- Log format and file structure differ from N.I.N.A. — research needed for exact format
- ASIAIR has its own plan/sequence format
- Data must be transferred off the ASIAIR (typically via network or USB) before NightCrate can ingest it

**NightCrate implication:** The app needs to handle ASIAIR's directory structure and log formats as a separate ingestion path from N.I.N.A.

### PHD2 (All Rigs)

PHD2 handles autoguiding on every rig.

**PHD2 log files:**
- Guiding logs are CSV-like text files with timestamped rows
- Each row contains: timestamp, RA error (arcsec), Dec error (arcsec), RA correction, Dec correction, guide star position, SNR, and other fields
- Dither events are logged as distinct entries
- Log files are typically stored alongside the imaging data or in a PHD2 log directory
- File naming includes the date and typically the guide camera name

**PHD2 log association:** Guiding data must be matched to sub frames by timestamp. A single PHD2 log file may span an entire night and cover multiple targets/sequences.

---

## FITS Header Metadata

NightCrate will parse FITS headers to extract metadata. Key headers from ZWO cameras via N.I.N.A.:

| FITS Keyword | Content | Example |
|-------------|---------|---------|
| `OBJECT` | Target name | `M101` |
| `FILTER` | Filter name | `Lum`, `Ha`, `Red`, `Green`, `Blue`, `Oiii`, `Sii` |
| `EXPTIME` | Exposure time (seconds) | `120.0` |
| `GAIN` | Camera gain setting | `100` |
| `CCD-TEMP` | Sensor temperature (°C) | `-10.0` |
| `SET-TEMP` | Target cooling temperature | `-10.0` |
| `INSTRUME` | Camera model | `ZWO ASI2600MM Pro` |
| `TELESCOP` | Telescope/rig description | User-configured string |
| `FOCALLEN` | Focal length (mm) | `1960` |
| `RA` / `OBJCTRA` | Right Ascension | `14h03m12.6s` or decimal degrees |
| `DEC` / `OBJCTDEC` | Declination | `+54°20'56.7"` or decimal degrees |
| `DATE-OBS` | Observation timestamp (UTC) | `2025-03-15T04:23:17.000` |
| `XBINNING` / `YBINNING` | Binning | `1` |
| `IMAGETYP` | Frame type | `Light`, `Dark`, `Flat`, `Bias` |
| `XPIXSZ` / `YPIXSZ` | Pixel size (μm) | `3.76` |
| `NAXIS1` / `NAXIS2` | Image dimensions (pixels) | `6248`, `4176` |
| `BITPIX` | Bit depth | `16` |
| `AIRMASS` | Atmospheric airmass | `1.23` |
| `SITEELEV` | Site elevation (m) | Varies |
| `SITELAT` / `SITELONG` | Site coordinates | Decimal or sexagesimal |

**N.I.N.A.-specific FITS keywords:** N.I.N.A. adds its own extended headers (prefixed with `NINA-` or similar) that may include sequence name, autofocus state, rotator angle, filter wheel position, and other metadata. These are non-standard but valuable.

**ASIAIR FITS headers:** Will follow a similar pattern but may use slightly different keyword names or formats. Needs verification.

**Calibration frame matching logic:**
Calibration frames (darks, flats, bias) need to match lights by:
- **Darks:** Same camera, gain, sensor temperature, exposure time, binning
- **Flats:** Same camera, gain, filter, binning, and ideally same optical train (rotator angle matters)
- **Bias:** Same camera, gain, binning

---

## Filter Inventory

Filters are a critical dimension for tracking integration time and matching calibration frames.

### C11 Rig Filters

| Filter | Type | Brand | Bandwidth |
|--------|------|-------|-----------|
| Lum | Broadband luminance | ZWO Premium | Full spectrum pass |
| Red | Broadband R | ZWO Premium | — |
| Green | Broadband G | ZWO Premium | — |
| Blue | Broadband B | ZWO Premium | — |
| Ha | Narrowband (Hydrogen-alpha) | Optolong | 7nm |
| Oiii | Narrowband (Oxygen-III) | Optolong | 6.5nm |
| Sii | Narrowband (Sulfur-II) | Optolong | 6.5nm |

### Askar V Rig Filters

| Filter | Type | Brand | Bandwidth |
|--------|------|-------|-----------|
| Lum | Broadband luminance | ZWO Premium | Full spectrum pass |
| Red | Broadband R | Optolong | — |
| Green | Broadband G | Optolong | — |
| Blue | Broadband B | Optolong | — |
| Ha | Narrowband (Hydrogen-alpha) | Antlia | 3nm Pro |
| Oiii | Narrowband (Oxygen-III) | Antlia | 3nm Pro |
| Sii | Narrowband (Sulfur-II) | Antlia | 3nm Pro |

### C6 Rig Filters

| Filter | Type | Brand | Bandwidth |
|--------|------|-------|-----------|
| Lum | Broadband luminance | Antlia LRGB-V Pro | Full spectrum pass |
| Red | Broadband R | Antlia LRGB-V Pro | — |
| Green | Broadband G | Antlia LRGB-V Pro | — |
| Blue | Broadband B | Antlia LRGB-V Pro | — |
| Ha | Narrowband (Hydrogen-alpha) | Antlia | 3nm Pro |
| Oiii | Narrowband (Oxygen-III) | Antlia | 3nm Pro |
| Sii | Narrowband (Sulfur-II) | Antlia | 3nm Pro |

The Antlia 3nm Pro set is assigned to both the C6's 1.25" wheel and the Askar V's 2" wheel.

**NightCrate implication:** The same filter name (e.g., "Ha") may appear on different rigs with different bandwidths. The app should track filters per equipment profile, not just by name. Integration time tracking should be rig-aware.

---

## Typical Imaging Workflow (What NightCrate Needs to Catalog)

### Acquisition Phase (Windows mini PC on the C11, ASIAIR on the others)

1. Set up rig, cool camera to target temperature (typically −10°C)
2. Polar align mount
3. Run N.I.N.A. (or ASIAIR) sequence:
   - Slew and plate solve to target
   - Start autoguiding (PHD2)
   - Run autofocus
   - Begin imaging loop: capture subs in filter sequence, dithering between frames
   - Autofocus periodically (triggered by temperature change or HFR drift)
   - Meridian flip if target crosses meridian
   - Continue loop until end condition (time, altitude, dawn)
4. Capture flats (dawn flats or panel flats, per filter used that night)

### Post-Acquisition (on Mac)

1. Transfer data from acquisition PCs to Mac (network transfer or USB)
2. Organize raw data into project folders
3. Stack sub frames (in PixInsight using WeightedBatchPreprocessing or similar)
4. Process stacked masters through the PixInsight workflow
5. Export final image

**NightCrate enters the workflow between steps 1 and 2** — it should make step 2 (organizing) automatic and provide the analytical tools (guiding analysis, integration time tracking, calibration matching) that currently require manual effort or multiple disconnected tools.

---

## Exposure Planning Reference

Fred uses specific exposure ratios based on sensor characteristics.

### Broadband LRGB Ratios (IMX571 / ASI 2600MM Pro)

| Channel | Share of Total Time | Reasoning |
|---------|-------------------|-----------|
| L | ~60% | Carries all structural detail |
| R | ~11% | Sensor efficient in red |
| G | ~11% | Sensor efficient in green |
| B | ~18% | IMX571 has weaker blue QE; R:G:B ≈ 1:1:1.5 compensates |

**Filter acquisition priority order:** L → B → R → G (most valuable first, so weather cutoffs lose least-critical data last)

**NightCrate implication:** The integration time dashboard should be able to show actual vs. target ratios for a project. If someone has 4 hours of L but only 20 minutes of B, the app should make that gap immediately obvious.

---

## Processing Software & Workflow

Fred processes exclusively in **PixInsight** on a Mac. The processing workflow is documented separately in `Broadband_LRGB_Processing_Workflow.md`.

**Key tools in the processing chain:**
- PixInsight (core platform)
- BlurXTerminator (AI deconvolution)
- NoiseXTerminator (AI noise reduction, being replaced by SyQon Prism Deep)
- StarXTerminator (AI star removal)
- SyQon Prism Deep (neural network denoiser/signal recovery)
- ScreenStars (star recombination script)
- Seti Astro scripts: AutoDBE (gradient removal), Statistical Stretch, Star Stretch
- SpectrophotometricColorCalibration (photometric color calibration)

**NightCrate implication:** The app should be able to attach processed/final images to a project. It does not need to understand or replicate the processing workflow — just catalog inputs (raw subs) and outputs (final images) and track the relationship.

---

## Color Blindness Context

NightCrate must be usable by red-green color blind users (a core accessibility requirement). This affects:
- Any color-coded UI elements in NightCrate should use a color-blind-friendly palette (avoid red/green distinctions; use blue/orange, or add pattern/shape differentiation)
- If NightCrate ever adds image preview features with auto-stretch, consider providing numerical readouts alongside visual displays
- The processing workflow document already uses numbers-based color assessment methods (CIE L*a*b* extraction, Statistics process medians) — any future NightCrate color analysis features should follow this pattern

---

## Network & Storage

| Component | Detail |
|-----------|--------|
| **NAS** | Network-attached storage on the local network, used for data storage |
| **Remote access** | VPN-based remote access (e.g. Tailscale) |
| **Data transfer** | Acquisition PCs → Mac via local network; raw data eventually archived to the NAS |

**NightCrate implication:** Data may live in multiple locations — local SSD on the Mac, Synology NAS, or even still on the acquisition PC. The app should handle paths flexibly and ideally support network/mounted volumes as data sources.

---

## Observatory Location

- **Location:** Suburban backyard observatory
- **Bortle class:** Likely 6–7 (suburban)
- **Typical conditions:** Excellent seeing many nights; monsoon season (July–September) largely shuts down imaging; light pollution is a factor, making narrowband filters valuable

**NightCrate implication:** Auto-detecting Bortle class from coordinates is a planned feature. Suburban coordinates should return Bortle 6–7.

---

## Known Data Quirks & Edge Cases

- **Multi-night projects are the norm:** A single target (like M101) will be imaged across many nights over weeks or months. NightCrate must handle accumulating data across sessions into a single project.
- **Dual-rig simultaneous imaging:** The C11 plus one AM5 rig may image the same target on the same night (wide-field + close-up), or completely different targets. The app must not conflate data from different rigs. Note that a filter name alone does not identify a rig — "Ha" is Optolong 7nm on the C11 and Antlia 3nm Pro on the other two.
- **Session interruptions:** Weather (clouds, wind) frequently ends sessions early. Partial data sets are normal and expected, not error conditions.
- **Filter name inconsistency:** The same physical filter may be named differently across software (e.g., "Lum" vs "L" vs "Luminance"; "Ha" vs "H-alpha" vs "Hydrogen Alpha"). NightCrate should normalize filter names.
- **FITS header variability:** Different capture software (N.I.N.A. vs ASIAIR) may use different FITS keywords for the same information. The parser needs to handle multiple conventions.
- **Calibration frame reuse:** Dark and bias frames are often reused across many sessions if camera settings match. A single dark library may serve months of imaging.
- **Mosaic panels:** A mosaic project has multiple panels, each with its own sky coordinates but belonging to one logical project. Each panel accumulates its own integration time independently.
