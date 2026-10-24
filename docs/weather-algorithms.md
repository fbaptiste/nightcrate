# Weather Forecast — Algorithms, Calculations & Data Sources

Complete reference for all calculations, verdict rules, assumptions, and data
provenance used in the NightCrate weather forecast page.

---

## 1. Data Sources

### 1.1 Weather Data — Open-Meteo

**Provider:** Open-Meteo (free, open-source weather API)
**Forecast URL:** `https://api.open-meteo.com/v1/forecast`
**Archive URL:** `https://archive-api.open-meteo.com/v1/archive`

**Hourly surface variables requested:**
- `temperature_2m` → `temperature_c`
- `dew_point_2m` → `dew_point_c`
- `relative_humidity_2m` → `humidity_pct`
- `cloud_cover` → `cloud_cover_pct` (total cloud cover 0–100%)
- `cloud_cover_low` → `cloud_cover_low_pct`
- `cloud_cover_mid` → `cloud_cover_mid_pct`
- `cloud_cover_high` → `cloud_cover_high_pct`
- `wind_speed_10m` → `wind_speed_kmh`
- `wind_direction_10m` → `wind_direction_deg`
- `wind_gusts_10m` → `wind_gusts_kmh`
- `visibility` → `visibility_m`
- `precipitation` → `precipitation_mm`
- `precipitation_probability` → `precipitation_probability_pct`

**Pressure-level variables (forecast only, not available for archive):**
- `wind_speed_200hPa` → `wind_speed_200hpa_kmh`
- `wind_speed_300hPa` → `wind_speed_300hpa_kmh`
- `wind_speed_500hPa` → `wind_speed_500hpa_kmh`
- `geopotential_height_200hPa` → `geopotential_200hpa_m`
- `geopotential_height_300hPa` → `geopotential_300hpa_m`
- `geopotential_height_500hPa` → `geopotential_500hpa_m`

**Units:** Wind speed in km/h (`wind_speed_unit=kmh`).

**Time contract.** Every request uses `timezone=GMT` and `timeformat=unixtime`.
Open-Meteo applies one fixed UTC offset to a whole response and ignores DST, so
all series are parsed straight to aware UTC datetimes.
- Cache rows written before v0.41.9 carry local ISO labels; they are decoded
  with their own `utc_offset_seconds`.
- A row whose times are off the whole-UTC-hour grid is ignored.

The forecast and cloud-model calls add `past_days=1`, so tonight's evening hours
are still available after local midnight.

**Horizon and models.**

- **Request length.** The forecast and cloud-model calls request
  `forecast_days=16` (`FORECAST_NIGHTS + 2`), and water vapour `forecast_days=16`
  too.
- **The cloud-model call** asks for four models at once: ECMWF IFS 0.25, GFS
  seamless and ICON seamless.
  - Its fields are total cloud, low, mid and high cloud, `precipitation` and
    `precipitation_probability`, each parsed independently per model.
- **Model metadata.** Each successful cloud refresh also fetches Open-Meteo's
  model metadata (`/data/<domain>/static/meta.json` for `ecmwf_ifs025`,
  `ncep_gfs013` and `dwd_icon`). It is stored as a
  `model_meta` cache row, written in the same transaction as its cloud row and
  paired with it by timestamp and payload hash.
- **ECMWF steps** are 3-hourly, and 6-hourly after 144 hours; Open-Meteo fills
  the hours between.
- **The outlook.** Nights 8–14 are shown as an outlook.

**Declared coverage** (`services/forecast_coverage.py`).

- **Source.** A fixed number of hours from the fetch time, per source. It is
  never derived from which values arrived.
- **When an hour is expected.** An hour is expected for a model and field
  when its value's timestamp is no later than the earlier of fetch + declared
  coverage and the last timestamp the request asks for. The request range is
  computed from the request parameters.
- **Inside coverage,** a missing value is unknown (expected-missing).
- **Outside coverage,** values are informational only.
- **What coverage applies to:** each model's cloud, and the per-model
  precipitation amounts used by "Any model". The main forecast's own fields
  (precipitation chance and amount, wind, temperature, dew point) are always
  verdict inputs: a missing value is unknown, whatever the coverage.
- **The constants** are set below each model's observed reach (see
  `DECLARED_COVERAGE` and its comment for the values and the observation they
  rest on).

**Interval semantics.** `precipitation`, `precipitation_probability` and
`wind_gusts_10m` describe the **preceding** hour, so the value at `T+1h` is
attached to the hour `[T, T+1h)`. The other fields are instantaneous at `T`.

**Caching and freshness.** Responses are cached in the SQLite `weather_cache`
table per location and source, with a configurable TTL
(`weather_cache_ttl_hours`).

- **Stale data.** A failed refresh after the TTL serves the newest cached row
  as **stale**. Stale decisive data never produces Go, and No keeps the
  forecast's age.
- **No cached row.** If the main forecast has no cached row at all, the API
  returns 503.
- **Incomplete rows.** A row within its TTL that is incomplete, from an older
  contract or with missing metadata, is refetched at most once an hour per
  location and source. Concurrent requests share the refetch. Within its TTL
  such a row is never stale: its missing values are unknown hours.
- **Purge.** The startup purge keeps 8 days of rows.

### 1.2 Astronomy Data — Astropy

**Library:** `astropy` (Python astronomy library)
**Ephemeris:** Astropy's built-in ephemeris (JPL DE440s by default)
**Bodies computed:** Sun, Moon (via `astropy.coordinates.get_body`)
**Location:** `EarthLocation` from user-provided latitude, longitude, elevation

---

## 2. Astronomy Computations

**Source file:** `backend/src/nightcrate/services/astronomy.py`

### 2.1 Sun Altitude Thresholds

| Threshold | Degrees | Meaning |
|-----------|---------|---------|
| Horizon | -0.833° | Geometric horizon with atmospheric refraction correction |
| Civil | -6.0° | End of civil twilight / start of civil dark |
| Nautical | -12.0° | End of nautical twilight / start of nautical dark |
| Astronomical | -18.0° | End of astronomical twilight / start of astro dark (full darkness) |

### 2.2 Sunset/Sunrise and Twilight Boundary Detection

**Method:** Dense sampling + linear interpolation crossing detection.

1. Create a 24-hour time grid from local noon to local noon (1440 samples = 1-minute resolution)
2. Compute the sun's altitude exactly with `astropy`'s `AltAz` frame at every
   10th sample plus the last (about every 10 minutes; 625 s apart on a 25-hour
   DST night). A cubic spline through those values (`scipy`'s `CubicSpline`, in
   elapsed seconds) gives the altitude at every sample.
   - With exact sampling at every point, 14 night summaries took about 6.7 s.
     With the spline they take about 1.2 s.
   - Across 210 test nights (five sites, three seasons), every crossing stayed
     within 0.0003 s of exact sampling. All other values were identical.
   - Within 1° of a threshold, the spline's altitude error was at most 0.002″.
   - `services/astronomy.py:_spline_altitudes` does this. Grids that would have
     fewer than four nodes are evaluated exactly.
3. Find horizon crossings by detecting where altitude array changes sign relative to threshold:
   - **Descending crossing** (sunset, evening twilight boundaries): `alt[i] > threshold` AND `alt[i+1] <= threshold`
   - **Ascending crossing** (sunrise, morning twilight boundaries): `alt[i] < threshold` AND `alt[i+1] >= threshold`
4. Linear interpolation between the two adjacent samples for sub-minute precision:
   ```
   frac = (threshold - alt[i]) / (alt[i+1] - alt[i])
   crossing_time = time[i] + frac * (time[i+1] - time[i])
   ```

**Crossing sequence (evening, all descending after sunset):**
- Sunset: sun crosses -0.833°
- Civil end (`civil_end`): sun crosses -6.0°
- Nautical end (`nautical_end`): sun crosses -12.0°
- Astro start (`astro_start`): sun crosses -18.0°

**Crossing sequence (morning, all ascending before sunrise):**
- Astro end (`astro_end`): sun crosses -18.0°
- Nautical start (`nautical_start`): sun crosses -12.0°
- Civil start (`civil_start`): sun crosses -6.0°
- Sunrise: sun crosses -0.833°

**All times are UTC datetimes internally, converted to local HH:MM for display.**

### 2.3 Darkness Intervals and Hours

`NightSummary.dark_intervals` holds, for each threshold (−18°, −12°, −6°), the
maximal runs of the noon-to-noon window during which the sampled sun altitude is
at or below the threshold. Boundaries are interpolated crossing instants. They
are found **independently of sunset**, which covers:
- a normal night (one interval);
- polar twilight with no sunset (for example Tromsø in December: about 13.5 h of
  astronomical darkness);
- continuous polar night (`[(noon, noon)]`);
- never dark (`[]`);
- two intervals in one night near the pole.

`darkness_hours` and `moonless_dark_hours` sum the intervals of the deepest
threshold reached. `deepest_darkness_reached` and `no_imaging_window` derive
from the same intervals. The `DarknessWindow` boundary fields in §2.2 are still
chained from sunset; use the intervals for durations.

### 2.4 Moon Illumination (Meeus Method)

**Method:** Compute the phase angle `i` (Sun-Moon-Earth angle) from 3D barycentric
positions, then apply the standard illumination formula.

**Steps:**
1. Get barycentric cartesian positions (in km) for Sun, Moon, and Earth at the given time using `astropy.coordinates.get_body_barycentric`
2. Compute vectors from Moon's position:
   - `moon_to_sun = sun_pos - moon_pos`
   - `moon_to_earth = earth_pos - moon_pos`
3. Phase angle via dot product:
   ```
   cos(i) = dot(moon_to_sun, moon_to_earth) / (|moon_to_sun| * |moon_to_earth|)
   ```
4. Illumination fraction:
   ```
   illumination_pct = (1 + cos(i)) / 2 * 100
   ```

**Result:** 0% at new moon, 100% at full moon.

**Note:** The `phase_angle_deg` field in `MoonInfo` stores the elongation (angular
separation of Sun and Moon as seen from Earth), NOT the phase angle used for
illumination. This is kept for reference/display purposes.

### 2.5 Moon Phase Name

Determined from ecliptic longitude difference:
```
delta_lon = (moon_ecliptic_lon - sun_ecliptic_lon) mod 360°
```

| delta_lon range | Phase name |
|-----------------|------------|
| 0° – 22.5° | New Moon |
| 22.5° – 67.5° | Waxing Crescent |
| 67.5° – 112.5° | First Quarter |
| 112.5° – 157.5° | Waxing Gibbous |
| 157.5° – 202.5° | Full Moon |
| 202.5° – 247.5° | Waning Gibbous |
| 247.5° – 292.5° | Last Quarter |
| 292.5° – 337.5° | Waning Crescent |
| 337.5° – 360° | New Moon |

Uses `geocentricmeanecliptic` coordinates from astropy.

### 2.6 Moonrise / Moonset

Same crossing-detection method as sunset/sunrise, applied to Moon altitude
against the −0.833° horizon threshold. The search covers **48 hours from local
midnight** of the night's date, sampled every minute, with exact altitudes at
every 10th sample and the same spline as §2.2 between them. The lunar day is about
24 h 50 min, so a narrower window can miss a rise. The result is the first rise,
then the first set after it.
- If the Moon never rises in the window, the rise is `None`.
- A set is still reported when the Moon starts the window above the horizon.
- Both are `None` only if the Moon never crosses the horizon at all.

### 2.7 Moonless Dark Hours

How many hours of the deepest darkness reached have the Moon below the
horizon. "Deepest" is astronomical where reached, otherwise nautical or civil.

1. For each interval in `dark_intervals[deepest]` (§2.3), sample the Moon's
   altitude every 5 minutes.
2. Count the samples where the altitude is < −0.833°.
3. `moonless_hours = Σ (below_count / total_samples) × interval_minutes / 60`,
   summed over the intervals.

### 2.8 Hourly Darkness Classification

For each hour from sunset to sunrise, compute sun altitude and classify:

```python
if sun_alt > -0.833°:  return "daylight"
if sun_alt > -6.0°:    return "civil_twilight"
if sun_alt > -12.0°:   return "nautical_twilight"
if sun_alt > -18.0°:   return "astronomical_twilight"
return "night"
```

### 2.9 Hourly Moon Data

- Moon altitude computed per-hour using `astropy` `AltAz` frame
- Moon illumination computed once at local midnight and reused for all hours
  (illumination changes negligibly over one night)

---

## 3. Seeing Estimation

**Source file:** `backend/src/nightcrate/services/seeing.py`

Two models available; the API selects the best available model per hour.

### 3.1 Model Selection (in `weather.py`)

```python
if pressure_level_data_available:
    use wind_shear model (60% upper-atmosphere + 40% surface)
else:
    use surface-only model
```

Pressure-level data is only available from the forecast API, not the archive API.

### 3.2 Surface Model (`estimate_seeing_surface`)

**Methodology:** Based on JAG Lab (Just Another Geek Lab) methodology.

Four weighted components:

#### Component 1: Temperature–Dew Point Spread (30%)
```
spread = temperature_c - dew_point_c
spread_score = clamp(spread * 5.0, 0, 100)
```
- Spread of 0°C (saturated) → score 0
- Spread of 20°C+ → score 100
- **Rationale:** Wider spread = drier air = better seeing

#### Component 2: Surface Wind Speed (30%)
```
if wind < 5 km/h:   score = max(60, wind * 12)
if 5–10 km/h:       score = 100  (optimal range)
if > 10 km/h:       score = max(0, 100 - (wind - 10) * 5)
```
- Very light winds (<5): good but slight instability possible
- 5–10 km/h: optimal (gentle mixing without turbulence)
- Above 10: degrades at 5 points per km/h
- **Rationale:** Light winds mix the boundary layer; strong winds create turbulence

#### Component 3: Humidity (20%)
```
humidity_score = max(0, 100 - humidity_pct * 0.8)
```
- 0% humidity → 100
- 100% humidity → 20
- **Rationale:** Lower humidity = less atmospheric water vapor = better seeing

#### Component 4: Temperature Stability (20%)
```
temp_change = |temperature_c - prev_temperature_c|
stability_score = max(0, 100 - temp_change * 10)
```
- 0°C change → 100
- 10°C change → 0
- If no previous hour available: default to 70 (neutral)
- **Rationale:** Rapid temperature changes indicate thermal turbulence

**Final:** `combined = spread * 0.30 + wind * 0.30 + humidity * 0.20 + stability * 0.20`

### 3.3 Wind Shear Model (`estimate_seeing_wind_shear`)

**References:**
- Trinquet, H. & Vernin, J. (2006). "A Model to Forecast Seeing and the Isoplanatic Angle." PASP, 118, 756–764.
- Cherubini, T. & Businger, S. (2013). "Another Look at the Refractive Index Structure Function." Journal of Applied Meteorology and Climatology, 52, 498–506.

**Structure:** 60% upper-atmosphere + 40% surface model

#### Upper-Atmosphere Score (60% of total)

**Jet Stream Indicator (60% of upper score):**
```
v200_ms = wind_speed_200hPa / 3.6  (convert km/h to m/s)
jet_score = clamp((35 - v200_ms) / 25 * 100, 0, 100)
```
- < 10 m/s → 100 (no jet stream)
- 35 m/s → 0 (strong jet stream overhead)
- Based on ESO (European Southern Observatory) thresholds

**Wind Shear Penalty (40% of upper score):**
```
shear_200_300 = |v200_ms - v300_ms| / |height_200 - height_300|  [s⁻¹]
shear_300_500 = |v300_ms - v500_ms| / |height_300 - height_500|  [s⁻¹]
avg_shear = (shear_200_300 + shear_300_500) / 2

shear_score = clamp((0.003 - avg_shear) / 0.002 * 100, 0, 100)
```
- < 0.001 s⁻¹ → 100 (smooth upper atmosphere)
- > 0.003 s⁻¹ → 0 (severe turbulence)

**Upper combined:** `upper_score = jet_score * 0.60 + shear_score * 0.40`

#### Surface Score (40% of total)
Delegates to `estimate_seeing_surface()` described above.

**Final:** `combined = upper_score * 0.60 + surface_score * 0.40`

---

## 4. Imaging Verdict (v0.41.9)

**Source files:**
- `services/imaging_rules.py` (rules and presets);
- `services/imaging_types.py` (shared contracts);
- `services/imaging_hours.py` (hourly checks);
- `services/imaging_session.py` (two-pass session, shared window);
- `services/imaging_verdict.py` (orchestration, combiners, vetoes,
  freshness, evidence);
- `services/forecast_coverage.py` (declared coverage, model metadata);
- `services/forecast_inputs.py` (hour inputs);
- `api/weather.py` (`POST /api/weather/forecast`).

The design is in the
[v0.41.9 spec](superpowers/specs/2026-10-17-weather-redesign-design.md), as
revised by the
[forecaster revisions spec](superpowers/specs/2026-10-17-forecaster-revisions-design.md).
The 0–100 score it replaced is archived in
[archive/imaging-quality-model.md](archive/imaging-quality-model.md).

### 4.1 Inputs and intervals

For each of 14 noon-to-noon nights:

- **Natural gear interval:** sunset − `gear_out_before_sunset_min` to sunrise +
  `gear_out_after_sunrise_min`. With no sunset or sunrise, the noon bound is
  used and no gear minutes are added.
- **Exposure interval** (`night_off` only): the natural gear interval, or the
  night's "Gear out at" / "Gear in at" controls. Precipitation is judged here.
- **Imaging interval:** the dark part of the exposure interval
  (`night_off`), or of the night (`hours_lost`), narrowed by "Imaging from" /
  "Imaging until". Cloud, wind, dew, Moon and the session rule are judged
  here.
- **Night under way:** both intervals are clipped to now.
- **Hours:** one input per whole UTC hour covering the natural interval and
  any control times. Each model's total, layers and precipitation amount
  carry "expected" flags from declared coverage (§1.1).

### 4.2 Per hour

| Check | Fails when | Counted on |
|---|---|---|
| cloud | the evaluated model's **total** > `cloud_max_pct` (layers never count; a missing total is unknown) | the imaging interval |
| precipitation chance (main forecast only) | value > `rain_max_probability_pct`, applied to every hourly value as reported | the exposure interval (`night_off`) or the imaging interval (`hours_lost`) |
| precipitation amount (main forecast) | amount > `rain_amount_threshold_mm` (equal passes) | as chance |
| precipitation amount (ECMWF, GFS, ICON) | the same, only when `rain_forecasts` is `any_model` and the hour is inside that model's coverage | as chance |
| wind | sustained > `wind_max_kmh` or gust > `gust_max_kmh` | the imaging interval, if `wind_counted` |
| dew | temperature − dew point < `dew_min_spread_c` | the imaging interval, if `dew_counted` |
| moon | altitude ≥ 0° | the imaging interval, if `moon_must_be_down` |

- **Combining checks.** A known fail beats an unknown.
- **Session states** (the ones the verdict uses) leave out precipitation
  under `night_off`, where precipitation is a night-level veto. Displayed
  states include it.
- **Conditions.** Each hour also reports `conditions`: the checks with the
  intervals ignored. They are display only.

### 4.3 Per model, then per night

- **Per model.** Each model's night is evaluated twice (unknown = fail, then
  unknown = pass) over the whole imaging interval:
  - **go** if the pessimistic pass passes;
  - **no** if the optimistic pass fails;
  - otherwise **unresolved** if an expected value is missing, else **not
    expected** (only not-covered hours are in the way).
- **Which cloud forecasts count** (F4). The rules tick one to three of ECMWF,
  GFS and ICON (`cloud_use_*`), name a preferred one
  (`cloud_preferred_model`) and choose `cloud_combination`:
  - **`majority`** (the default):
    - Each hour's cloud check follows most of the ticked models expected at
      that hour (`decide_cloud`).
    - A tie goes to the preferred model. If the preferred model isn't
      expected at that hour, the first expected ticked model breaks ties, in
      the order ECMWF, GFS, ICON.
    - Unknown votes are bracketed: once all fail, once all pass, and the hour
      is unknown if the two results differ.
    - With no ticked model expected, `best_match` decides, labelled.
    - The night is then evaluated on that one decided sequence, like a single
      model, so it is never Uncertain from disagreement. The number of hours
      where known votes differ is reported (`forecasts_differ`).
  - **`uncertain`:** the comparison rules below.
    - The primary is the first of the preferred model, then the ticked models
      in order, that is not *not expected* for the night. The other ticked
      models are the comparisons.
    - If none qualifies, `best_match` is used, labelled, with no comparison.
    - A missing expected value never triggers a substitution or the fallback.
  - With one model ticked, both reduce to that model alone.
- **Early exits**, first match wins:
  1. Night over (darkness ended, or the imaging interval ended);
  2. never dark;
  3. no dark time (the user's times remove the darkness).

  Missing hours over remaining darkness give Not enough data.
- **All night** (`uncertain` mode). The comparison table: a primary Go with every expected model
  Go is **Go**. A Go/No split is **Uncertain**. A primary Go with a comparison
  unresolved is **Not enough data**. A primary No with no Go is **No**,
  disclosing any incomplete model.
- **Short session** (`uncertain` mode). The joint hourly state across the
  models expected at each hour must contain a run ≥ the required length. In
  `majority` mode the run comes from the decided sequence instead.
  - established → **Go**, naming the earliest window;
  - impossible → **Uncertain**;
  - otherwise → **Not enough data**.

  With a primary No, any comparison Go gives **Uncertain**.
- **Night-level outcomes, after the comparison:**
  1. a known precipitation failure in the exposure interval (`night_off`) →
     **No**;
  2. otherwise unknown precipitation there turns Go or Uncertain into **Not
     enough data**;
  3. then freshness: a stale decisive source turns Go, Uncertain or Not
     enough data into **Not enough data**, and a No stays No with the age.

  Every contributing cause is returned. The headline follows that
  precedence; the other causes are listed after it.
- **Guarantee.** With the rules, intervals and declared coverage fixed,
  replacing a known value with an unknown never turns a non-Go into Go. Tests
  in `tests/test_imaging_guarantee.py` check this exhaustively on reduced
  domains and on seeded raw payloads.

### 4.4 Freshness sources

- The main forecast always counts.
- The cloud row counts when any ticked model's cloud is used for the night, a
  comparison model is expected, or "Any model" amounts fall in the counted
  interval. It does not count when `best_match` decides alone.
- Model metadata never makes a verdict stale.

### 4.5 Context values

These are shown, never counted:
- seeing and transparency, as good / fair / poor, from §3 and the
  PWV/AOD/humidity/visibility tiers. Missing inputs stay missing, and the tier
  is shown when it is not the primary one;
- ECMWF's low, mid and high cloud, which Open-Meteo estimates from humidity;
- the temperature − dew-point gap;
- moon altitude and illumination;
- visibility;
- wind and gusts, when not counted.

---

## 5. Known Assumptions & Limitations

1. **Moon illumination** is computed once at local midnight and reused for all
   hours of the night. Illumination changes <1% over a single night, so this
   is acceptable.

2. **Seeing estimation** from surface weather data is inherently approximate.
   True seeing measurement requires a DIMM (Differential Image Motion Monitor)
   or similar instrument. The surface model is based on correlations, not
   direct measurement.

3. **Wind shear model** uses only three pressure levels (200, 300, 500 hPa).
   Professional observatories use full radiosonde profiles. The three-level
   approach captures the dominant jet stream and tropopause effects but misses
   finer-grained turbulence layers.

4. **Cloud cover** is a coverage fraction, not an optical thickness. Thin
   cirrus and thick stratus at the same cover count the same. The verdict uses
   each model's own total cloud. For ECMWF IFS 0.25, Open-Meteo estimates the
   low, mid and high layers from relative humidity on pressure levels (low
   1000/925/850 hPa; mid 700/600/500/400 hPa; high 300/250/200/150/100/50 hPa,
   as of the 2025-10-13 downloader change). They are shown for context and
   never count.

5. **Pressure-level data** (for wind shear seeing model) is only available from
   the forecast API, not the archive API. Archive queries fall back to the
   surface-only seeing model.

6. **Refraction correction** of -0.833° for sunset/sunrise includes standard
   atmospheric refraction but does not account for local topography or unusual
   atmospheric conditions.

7. **The "night" search window** spans local noon to local noon the next day.
   Polar cases are handled through the darkness intervals in §2.3. The
   twilight boundary fields in §2.2 can still be `None` when there is no
   sunset.

8. **Weather cache TTL** defaults to a configurable number of hours. During
   rapidly changing weather, cached data may not reflect the latest forecast.

9. **Precipitation chance** depends on its source.
   - **In North America** it is NOAA's NBM: the chance of more than
     0.254 mm, per hour up to about 36 h after the run, and per 6-hour block
     after that, copied into each hour.
   - **Elsewhere** it is the share of ensemble members with at least 0.1 mm
     per model step hour, interpolated to hours.
   - **In the US,** the main forecast's and GFS's chances are the same
     product.
   - **One limit.** One limit applies to every hourly value as reported
     (Fred, 2026-10-18). A 6-hour figure is repeated in each of its hours and
     judged in each.
   - **Night-level risk.** The night-level risk is higher than any single
     value, and no whole-night probability is computed.
   - **Zero limits.** The reported chance is rarely exactly 0%, so a 0% limit
     rejects most nights.

10. **Declared coverage** is a fixed policy below each model's observed reach.
    Hours past it are not expected from that model: a model covering only part
    of a night may be left out of that night's comparison, and is named in the
    coverage line. A coverage value that is too long would produce spurious Not
    enough data near the edge, and repeated refetches.
