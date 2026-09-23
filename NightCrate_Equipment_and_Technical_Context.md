# NightCrate — Equipment & Technical Context

Reference document for development: the capture software, file formats, and
workflow patterns NightCrate must handle. Equipment named here is illustrative.

---

## Typical Setups

- **Several rigs per imager are common.** A long-focal-length SCT with an
  off-axis guider may run on one mount while a refractor runs on another. Two
  rigs can share one mount, so they never run on the same night.
- **Capture software differs by rig.** One rig may run N.I.N.A. on a Windows
  mini PC at the scope while another runs a ZWO ASIAIR; processing happens later
  on a separate computer.
- **Identical cameras on different rigs.** Two rigs can carry the same camera
  model (for example two ASI 2600MM Pro units), so a camera model alone does not
  identify a rig.
- **Published focal lengths can be wrong.** SCT focal length changes with back
  focus: a nominal 1500 mm C6 can plate-solve near 1640 mm. Prefer measured or
  plate-solved values downstream.
- **Guiding varies by rig:** an off-axis guider on one, a guide scope on another.
  A guide camera may move between rigs from night to night.
- **Smart telescopes** (for example ZWO Seestar S30/S50) produce their own file
  layouts and combine capture and stacking.

---

## Acquisition Software Details

### N.I.N.A.

N.I.N.A. (Nighttime Imaging 'N' Astronomy) runs on Windows, typically on a PC at
the scope.

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

### ASIAIR

ZWO's ASIAIR controls ZWO mounts, cameras, and accessories. It runs on a
dedicated ZWO hardware unit (ARM-based Linux appliance), not a general-purpose PC.

**Key differences from N.I.N.A.:**
- ASIAIR stores data on its internal storage or a USB drive attached to the ASIAIR unit
- Log format and file structure differ from N.I.N.A. — research needed for exact format
- ASIAIR has its own plan/sequence format
- Data must be transferred off the ASIAIR (typically via network or USB) before NightCrate can ingest it

**NightCrate implication:** The app needs to handle ASIAIR's directory structure and log formats as a separate ingestion path from N.I.N.A.

### PHD2

PHD2 handles autoguiding.

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

## Filters

Filters are a critical dimension for tracking integration time and matching
calibration frames. The same filter name can mean different physical filters on
different rigs: "Ha" might be a 7 nm Optolong on one rig and a 3 nm Antlia on
another, and some "7 nm" sets have 6.5 nm Oiii and Sii. Broadband sets also
differ by brand per rig.

**NightCrate implication:** Track filters per rig, not just by name. Integration
time tracking should be rig-aware.

---

## Typical Imaging Workflow (What NightCrate Needs to Catalog)

### Acquisition Phase (acquisition PC or ASIAIR at the scope)

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

### Post-Acquisition (processing computer)

1. Transfer data from acquisition devices to the processing computer (network transfer or USB)
2. Organize raw data into project folders
3. Stack sub frames (for example in PixInsight using WeightedBatchPreprocessing)
4. Process stacked masters in PixInsight or Siril
5. Export final image

**NightCrate enters the workflow between steps 1 and 2** — it should make step 2 (organizing) automatic and provide the analytical tools (guiding analysis, integration time tracking, calibration matching) that currently require manual effort or multiple disconnected tools.

---

## Exposure Planning Reference

Exposure ratios often follow sensor characteristics. An example broadband
allocation for an IMX571 mono sensor (ASI 2600MM Pro class):

| Channel | Share of Total Time | Reasoning |
|---------|-------------------|-----------|
| L | ~60% | Carries all structural detail |
| R | ~11% | Sensor efficient in red |
| G | ~11% | Sensor efficient in green |
| B | ~18% | IMX571 has weaker blue QE; R:G:B ≈ 1:1:1.5 compensates |

**Filter acquisition priority order:** L → B → R → G (most valuable first, so weather cutoffs lose least-critical data last)

**NightCrate implication:** The integration time dashboard should be able to show actual vs. target ratios for a project. If someone has 4 hours of L but only 20 minutes of B, the app should make that gap immediately obvious.

---

## Processing Software

Processing happens in specialist software such as PixInsight or Siril, often with
third-party tools (BlurXTerminator, NoiseXTerminator, StarXTerminator, and
scripts such as Seti Astro's).

**NightCrate implication:** The app should be able to attach processed/final images to a project. It does not need to understand or replicate the processing workflow — just catalog inputs (raw subs) and outputs (final images) and track the relationship.

---

## Color Vision Accessibility

NightCrate must be usable with red-green color vision deficiency (a core accessibility requirement). This affects:
- Any color-coded UI elements in NightCrate should use a color-blind-friendly palette (avoid red/green distinctions; use blue/orange, or add pattern/shape differentiation)
- Image preview features with auto-stretch should provide numerical readouts alongside visual displays
- Future color analysis features should report numbers (for example CIE L*a*b* values or channel medians), not rely on visual judgment alone

---

## Data Locations

Data may live in several places at once: the processing computer's local SSD, a
NAS, removable drives, or still on the acquisition PC or ASIAIR. Some volumes
are offline much of the time.

**NightCrate implication:** Handle paths flexibly and support network, mounted,
and offline volumes as data sources.

---

## Site Conditions

Seasonal weather (for example a monsoon season) can shut down imaging for
months, and suburban light pollution makes narrowband filters valuable. Sites
range from bright suburbs to dark remote locations, in both hemispheres.

---

## Known Data Quirks & Edge Cases

- **Multi-night projects are the norm:** A single target (like M101) will be imaged across many nights over weeks or months. NightCrate must handle accumulating data across sessions into a single project.
- **Dual-rig simultaneous imaging:** Two rigs may image the same target on the same night (wide-field + close-up), or completely different targets. The app must not conflate data from different rigs. A filter name alone does not identify a rig.
- **Session interruptions:** Weather (clouds, wind) frequently ends sessions early. Partial data sets are normal and expected, not error conditions.
- **Filter name inconsistency:** The same physical filter may be named differently across software (e.g., "Lum" vs "L" vs "Luminance"; "Ha" vs "H-alpha" vs "Hydrogen Alpha"). NightCrate should normalize filter names.
- **FITS header variability:** Different capture software (N.I.N.A. vs ASIAIR) may use different FITS keywords for the same information. The parser needs to handle multiple conventions.
- **Calibration frame reuse:** Dark and bias frames are often reused across many sessions if camera settings match. A single dark library may serve months of imaging.
- **Mosaic panels:** A mosaic project has multiple panels, each with its own sky coordinates but belonging to one logical project. Each panel accumulates its own integration time independently.
