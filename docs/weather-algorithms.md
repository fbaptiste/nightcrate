# Weather Forecast — Algorithms, Calculations & Data Sources

Complete reference for all calculations, scoring formulas, assumptions, and data
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

**Caching:** Responses cached in SQLite `weather_cache` table with a configurable
TTL (`weather_cache_ttl_hours` from settings). Cache is per-location, per-source.

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
2. Compute sun altitude at all sample points using `astropy`'s `AltAz` frame
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

### 2.3 Darkness Hours

```
darkness_hours = (astro_end - astro_start).total_seconds() / 3600
```

This is the duration of astronomical darkness — the period when the sun is below -18°.

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

Same crossing-detection method as sunset/sunrise, applied to moon altitude
against the -0.833° horizon threshold. Searches the full noon-to-noon window.

### 2.7 Moonless Dark Hours

How many hours of astronomical darkness have the moon below the horizon.

1. Sample moon altitude every 5 minutes between `astro_start` and `astro_end`
2. Count samples where moon altitude < -0.833°
3. ```moonless_hours = (below_count / total_samples) * total_darkness_minutes / 60```

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

## 4. Imaging Quality Score

**Source file:** `backend/src/nightcrate/services/imaging_quality.py`

### 4.1 Individual Factor Scores

| Factor | Computation | Range |
|--------|------------|-------|
| Sky Clarity | Weighted cloud layers (low×1.0, mid×0.9, high×0.6); falls back to `100 - cloud_cover_pct` | 0–100 |
| Seeing | Passed through from seeing model | 0–100 |
| Transparency | PWV + AOD + humidity + visibility (from transparency service) | 0–100 |
| Wind Calm | Piecewise linear (see below) | 0–100 |
| Moon Score | Moon-up fraction × illumination (see below) | 0–100 |

#### Wind Calm Score
```
≤ 5 km/h:    100
5–15 km/h:   100 → 60  (linear, -4/km/h)
15–30 km/h:  60 → ~8   (linear, -3.47/km/h)
> 30 km/h:   0
```

#### Moon Score
```
moon_up_fraction = 1 - moonless_dark_hours / darkness_hours
illumination_factor = moon_illumination_pct / 100
moon_score = (1 - moon_up_fraction * illumination_factor) * 100
```
- Moon never rises (moonless = darkness): moon_score = 100
- New moon (illumination = 0): moon_score = 100
- Full moon up all night: moon_score = 0

### 4.2 Composite Score — Moon Included (default, broadband)

```
sky_clarity = compute_sky_clarity(cloud layers)  # weighted multi-layer
sky_factor = sqrt(sky_clarity / 100)             # 0.0–1.0 gating multiplier

other_score = seeing * 0.25 + transparency * 0.15 + moon * 0.15 + wind_calm * 0.10

overall = sky_clarity * 0.35 + other_score * sky_factor
```

**Effective weights under clear skies (sky_factor ≈ 1.0):**
- Sky Clarity: 35%
- Seeing: 25%
- Transparency: 15%
- Moon: 15%
- Wind Calm: 10%

**Under heavy cloud (sky_factor → 0):** Sky clarity dominates; other factors are suppressed.

### 4.3 Composite Score — Moon Excluded (narrowband)

```
other_score = transparency * 0.25 + seeing * 0.25 + wind_calm * 0.10
overall = sky_clarity * 0.40 + other_score * sky_factor
```

**Effective weights under clear skies:**
- Sky Clarity: 40%
- Transparency: 25%
- Seeing: 25%
- Wind Calm: 10%

### 4.4 Quality Labels

| Score Range | Label |
|-------------|-------|
| 80–100 | Excellent |
| 55–79 | Good |
| 30–54 | Marginal |
| 0–29 | Poor |

---

## 5. Hourly Detail Computation (API Layer)

**Source file:** `backend/src/nightcrate/api/weather.py`

### 5.1 Time Window

The hourly detail view spans **sunset - 1 hour** through **sunrise + 1 hour**
to provide context before and after the imaging window.

### 5.2 Per-Hour Computation

For each weather hour in the window:

1. **Seeing:** `_compute_seeing(h, prev_h)` — selects wind-shear or surface model
2. **Sky Clarity:** `compute_sky_clarity()` — weighted multi-layer (low×1.0, mid×0.9, high×0.6), falls back to `100 - cloud_cover_pct`
3. **Wind Calm:** Same piecewise linear as in imaging_quality.py (duplicated inline):
   ```
   ≤ 5: 100
   5–15: 100 - (wind - 5) * 4
   15–30: 60 - (wind - 15) * (52/15)
   > 30: 0
   ```
4. **Dryness:** `int(round(clamp(100 - humidity_pct, 0, 100)))`
5. **Moon altitude & illumination:** Looked up from astronomy hourly data by HH:MM match
6. **Imaging Quality:** `compute_imaging_quality()` called with:
   - `moonless_dark_hours = 0 if moon_alt > 0 else 1` (per-hour binary: moon up or not)
   - `darkness_hours = 1` (per-hour: always 1 hour)
   - `moon_illumination_pct` from night summary
   - `include_moon = True` always for hourly view

### 5.3 Astronomy Data Merge

Astronomy data (darkness_category, moon_altitude_deg, moon_illumination_pct) is
computed by `compute_hourly_astro()` which returns one entry per hour from sunset
to sunrise. These are matched to weather hours by HH:MM local time string.

Hours outside the sunset–sunrise range (the ±1h context padding) will have
`darkness_category = None`, `moon_altitude_deg = None`, etc.

---

## 6. Daily Forecast Summary

### 6.1 Averaging

For each forecast day, weather data is averaged over the **sunset to sunrise window**:
- `avg_cloud_cover_pct` — mean of hourly cloud_cover
- `avg_cloud_low/mid/high_pct` — mean of hourly low/mid/high cloud
- `avg_wind` — mean of hourly wind speed (used in quality computation)
- `avg_humidity` — mean of hourly humidity (used in quality computation)
- `avg_seeing` — mean of hourly seeing scores
- `max_precipitation_probability_pct` — maximum across all hours

### 6.2 Daily Quality Score

Uses the same `compute_imaging_quality()` function with the averaged values:
- `cloud_cover_pct = avg_cloud`
- `seeing_score = avg_seeing`
- `wind_speed_kmh = avg_wind`
- `humidity_pct = avg_humidity`
- `moonless_dark_hours` and `darkness_hours` from astronomy (actual values, not per-hour)
- `moon_illumination_pct` from astronomy

---

## 7. Frontend Display Scores

**Source file:** `frontend/src/components/weather/HourlyTimeline.tsx`

The frontend computes some display-only scores that are NOT part of the backend
quality computation:

### 7.1 Moon Quality (display only)
```typescript
if (moon_altitude_deg === null) return 100;
if (moon_altitude_deg <= 0) return 100;     // moon below horizon = best
return max(0, round(100 - (altitude / 90) * 100));
```
- Moon at horizon (0°): 100
- Moon at zenith (90°): 0
- **Note:** This is different from the backend moon_score which uses
  illumination × fraction of dark hours. This is a simpler per-hour indicator.

### 7.2 Cloud Score (display only)
```typescript
cloud_score = round(100 - cloud_cover_pct)
```

### 7.3 Precipitation Score (display only)
```typescript
if (mm === null || mm <= 0) return 100;
if (mm < 0.5) return 70;
if (mm < 2) return 30;
return 0;
```

---

## 8. Darkness Gradient (Frontend)

The darkness bar uses an SVG linear gradient with stops at each twilight boundary.
The boundary positions are computed by mapping precise HH:MM times to fractional
positions within the bar width:

```
gradient position = (time_in_minutes - window_start) / (window_end - window_start)
```

Where `window_start` = first hour's time, `window_end` = last hour + 1 hour.

**Color palette:**
| Category | HSL Color |
|----------|-----------|
| Daylight | hsl(215, 15%, 60%) |
| Civil Twilight | hsl(215, 30%, 45%) |
| Nautical Twilight | hsl(215, 35%, 30%) |
| Astronomical Twilight | hsl(215, 40%, 18%) |
| Night | hsl(215, 45%, 8%) |

---

## 9. Known Assumptions & Limitations

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

4. **Cloud cover** is total column cloud cover from the weather model. It does
   not distinguish between thin cirrus (which may still allow some imaging) and
   thick stratus (which blocks everything). The cloud_cover_high/mid/low
   breakdown is available for display but not used in quality scoring.

5. **Pressure-level data** (for wind shear seeing model) is only available from
   the forecast API, not the archive API. Archive queries fall back to the
   surface-only seeing model.

6. **Refraction correction** of -0.833° for sunset/sunrise includes standard
   atmospheric refraction but does not account for local topography or unusual
   atmospheric conditions.

7. **The "night" search window** spans local noon to local noon the next day.
   This may not correctly handle polar regions where the sun doesn't set or
   doesn't rise. The code will raise an exception (caught and returned as
   HTTP 422) if crossings are not found.

8. **Weather cache TTL** defaults to a configurable number of hours. During
   rapidly changing weather, cached data may not reflect the latest forecast.
