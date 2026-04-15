"""Astronomical seeing estimation service.

Two complementary models for estimating atmospheric seeing quality:

1. Surface model (JAG Lab methodology) — uses ground-level weather observations.
2. Wind-shear model — combines upper-atmosphere jet stream and shear indicators
   with the surface model, based on the methodology described in:

   - Trinquet, H. & Vernin, J. (2006). "A Model to Forecast Seeing and the
     Isoplanatic Angle." PASP, 118, 756–764.
   - Cherubini, T. & Businger, S. (2013). "Another Look at the Refractive Index
     Structure Function." Journal of Applied Meteorology and Climatology, 52,
     498–506.

Both functions return a 0–100 integer score (higher = better seeing).

This module is pure computation — no database, no HTTP, no FastAPI dependencies.
"""

from __future__ import annotations


def estimate_seeing_surface(
    temperature_c: float,
    dew_point_c: float,
    humidity_pct: float,
    wind_speed_kmh: float,
    prev_temperature_c: float | None = None,
) -> int:
    """Estimate seeing quality from surface weather observations.

    Uses the JAG Lab methodology, combining four weighted components:

    - Temperature–dew point spread (30%): wider spread = drier air = better seeing
    - Surface wind speed (30%): light winds (5–10 km/h) are optimal
    - Relative humidity (20%): lower humidity = better seeing
    - Temperature stability (20%): stable temperature = stable air = better seeing

    Args:
        temperature_c: Current air temperature in degrees Celsius.
        dew_point_c: Current dew point in degrees Celsius.
        humidity_pct: Relative humidity as a percentage (0–100).
        wind_speed_kmh: Surface wind speed in km/h.
        prev_temperature_c: Air temperature from the previous hour (or reading),
            used to assess thermal stability. If None, a neutral default is used.

    Returns:
        Seeing quality score from 0 (terrible) to 100 (excellent).
    """
    # --- Component 1: Temperature–dew point spread (30%) ---
    # Spread of 0°C (saturated air) = 0; spread of 20°C+ = 100.
    spread = temperature_c - dew_point_c
    spread_score = min(100.0, max(0.0, spread * 5.0))

    # --- Component 2: Surface wind speed (30%) ---
    if wind_speed_kmh < 5.0:
        # Light winds are good but slight instability possible
        wind_score = max(60.0, wind_speed_kmh * 12.0)
    elif wind_speed_kmh <= 10.0:
        # Optimal range
        wind_score = 100.0
    else:
        # Stronger winds degrade seeing
        wind_score = max(0.0, 100.0 - (wind_speed_kmh - 10.0) * 5.0)

    # --- Component 3: Humidity (20%) ---
    humidity_score = max(0.0, 100.0 - humidity_pct * 0.8)

    # --- Component 4: Temperature stability (20%) ---
    if prev_temperature_c is not None:
        temp_change = abs(temperature_c - prev_temperature_c)
        stability_score = max(0.0, 100.0 - temp_change * 10.0)
    else:
        stability_score = 70.0  # Neutral default when no prior reading

    # Weighted combination
    combined = (
        spread_score * 0.30 + wind_score * 0.30 + humidity_score * 0.20 + stability_score * 0.20
    )

    return int(round(max(0.0, min(100.0, combined))))


def estimate_seeing_wind_shear(
    wind_speed_200hpa_kmh: float,
    wind_speed_300hpa_kmh: float,
    wind_speed_500hpa_kmh: float,
    geopotential_200hpa_m: float,
    geopotential_300hpa_m: float,
    geopotential_500hpa_m: float,
    temperature_c: float,
    dew_point_c: float,
    humidity_pct: float,
    wind_speed_surface_kmh: float,
    prev_temperature_c: float | None = None,
) -> int:
    """Estimate seeing quality using upper-atmosphere wind shear and surface data.

    Combines two components:
    - Upper-atmosphere score (60%): jet stream strength + wind shear between
      pressure levels, based on Trinquet/Cherubini methodology.
    - Surface score (40%): delegates to ``estimate_seeing_surface()``.

    The upper-atmosphere score itself blends:
    - Jet stream indicator (60%): based on 200 hPa wind speed. ESO thresholds:
      < 10 m/s → 100; degrades linearly to 0 at 35 m/s.
    - Wind shear penalty (40%): average vertical wind shear across pressure
      layer pairs. Shear < 0.001 s⁻¹ is good; > 0.003 s⁻¹ is bad.

    Args:
        wind_speed_200hpa_kmh: Wind speed at the 200 hPa level in km/h.
        wind_speed_300hpa_kmh: Wind speed at the 300 hPa level in km/h.
        wind_speed_500hpa_kmh: Wind speed at the 500 hPa level in km/h.
        geopotential_200hpa_m: Geopotential height of the 200 hPa surface in
            metres above sea level.
        geopotential_300hpa_m: Geopotential height of the 300 hPa surface in
            metres above sea level.
        geopotential_500hpa_m: Geopotential height of the 500 hPa surface in
            metres above sea level.
        temperature_c: Surface air temperature in degrees Celsius.
        dew_point_c: Surface dew point in degrees Celsius.
        humidity_pct: Surface relative humidity as a percentage (0–100).
        wind_speed_surface_kmh: Surface wind speed in km/h.
        prev_temperature_c: Prior surface temperature for stability estimate.

    Returns:
        Seeing quality score from 0 (terrible) to 100 (excellent).
    """
    # Convert km/h → m/s for atmospheric calculations
    v200_ms = wind_speed_200hpa_kmh / 3.6
    v300_ms = wind_speed_300hpa_kmh / 3.6
    v500_ms = wind_speed_500hpa_kmh / 3.6

    # --- Jet stream indicator (based on 200 hPa wind speed) ---
    # ESO threshold: < 10 m/s = 100, degrades to 0 at 35 m/s
    jet_score = max(0.0, min(100.0, (35.0 - v200_ms) / 25.0 * 100.0))

    # --- Wind shear between pressure levels ---
    # Shear = |delta_v| / delta_z  [s⁻¹]
    dz_200_300 = abs(geopotential_200hpa_m - geopotential_300hpa_m)
    dz_300_500 = abs(geopotential_300hpa_m - geopotential_500hpa_m)

    shear_200_300 = abs(v200_ms - v300_ms) / dz_200_300 if dz_200_300 > 0 else 0.0
    shear_300_500 = abs(v300_ms - v500_ms) / dz_300_500 if dz_300_500 > 0 else 0.0

    avg_shear = (shear_200_300 + shear_300_500) / 2.0

    # Map shear to score: good < 0.001 s⁻¹ → 100; bad > 0.003 s⁻¹ → 0
    shear_score = max(0.0, min(100.0, (0.003 - avg_shear) / 0.002 * 100.0))

    # --- Upper-atmosphere combined score ---
    upper_score = jet_score * 0.60 + shear_score * 0.40

    # --- Surface score ---
    surface_score = float(
        estimate_seeing_surface(
            temperature_c=temperature_c,
            dew_point_c=dew_point_c,
            humidity_pct=humidity_pct,
            wind_speed_kmh=wind_speed_surface_kmh,
            prev_temperature_c=prev_temperature_c,
        )
    )

    # --- Final combined score ---
    combined = upper_score * 0.60 + surface_score * 0.40

    return int(round(max(0.0, min(100.0, combined))))
