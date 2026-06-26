# "Best Time of Year" — Algorithm Reference

This document describes the complete mathematical algorithm behind
the `Best time of year` chart on the target-planner detail panel.
The implementation lives in
`backend/src/nightcrate/services/planner_annual_hours.py`. The
chart's per-night value is the number of hours the target spends
above a chosen altitude threshold during astronomical darkness,
optionally with moon avoidance.

The goal of this document is to let a reader re-implement the
algorithm from scratch: every astropy / ERFA call, every formula,
every optimisation, and the linear-interpolation scheme that
eliminates the 5-minute sample quantisation.

The code depends on:

- `astropy` ≥ 5.0 (we use `astropy.coordinates`, `astropy.time`,
  `astropy.units`).
- `numpy`.
- Python 3.14 standard library: `zoneinfo`, `datetime`,
  `concurrent.futures.ProcessPoolExecutor`, `multiprocessing`.
- `nightcrate.services.horizon.interpolate_horizon_altitude`
  (project-local; azimuth-indexed piecewise-linear interpolation
  over the user's custom horizon polyline).
- `nightcrate.services.planner_visibility._make_earth_location`
  (project-local; wraps `astropy.coordinates.EarthLocation`).

Astropy wraps the underlying IAU / SOFA algorithms via the ERFA C
library (<https://github.com/liberfa/erfa>). Where astropy delegates
to an ERFA routine we cite the routine name — those names match
SOFA one-for-one, and the published SOFA cookbook has the full
mathematical specification for each.

---

## 1. Inputs and constants

| Symbol | Quantity | Units | Default |
|---|---|---|---|
| φ | Observer geodetic latitude | deg | from `PlannerLocation` |
| λ | Observer geodetic longitude (E positive) | deg | from `PlannerLocation` |
| h_obs | Observer elevation above WGS84 ellipsoid | m | 0 when unset |
| `tz` | IANA timezone | — | location's |
| α, δ | Target ICRS right ascension / declination | deg | from DSO row |
| A | Altitude threshold (fixed mode) | deg | 20 / 25 / 30 / 35 / 40 / 45 / 50 |
| Y | Calendar year to plot | — | local-timezone current year |
| S = −18° | Sun altitude defining astronomical darkness | deg | constant |
| M = 60° | Target ↔ Moon separation threshold (LRGB mode) | deg | constant |
| Δt = 300 s | Sample interval (5 min) | s | constant |

WGS84 constants used inside astropy's `EarthLocation`:

- a = 6 378 137 m  (equatorial radius)
- e² = 6.694 379 99 × 10⁻³  (first eccentricity squared)

Code constants (Python module-level):

```python
_SAMPLE_MINUTES    = 5
_SAMPLE_SECONDS    = _SAMPLE_MINUTES * 60    # 300
_ASTRO_DARK_DEG    = -18.0
_MIN_MOON_SEP_DEG  = 60.0
```

---

## 2. One-paragraph summary of the algorithm

Build a 5-minute time grid spanning a year, each night bucketed by
its *evening* date. Use astropy / ERFA to compute the Sun's altitude,
the target's altitude, and (for moon-aware mode) the Moon's altitude
+ target–Moon angular separation at every sample. For each adjacent
pair of samples forming a 5-minute segment, treat every quantity as
a linear function of time across the segment and compute the exact
number of seconds inside that segment during which all of the
following hold simultaneously: sun altitude below −18°, target
altitude above the threshold (fixed degrees or an azimuth-dependent
horizon profile), and — in LRGB mode — Moon below the horizon OR
Moon–target separation greater than 60°. Sum seconds per evening-date
bucket; divide by 3600 to get hours per night.

---

## 3. Time grid

Let `L(t, tz)` convert a UTC instant `t` to the wall-clock instant
in zone `tz`.

Define the year's observation window in local time:

    t_start^local = Y-01-01 12:00:00 in tz
    t_end^local   = (Y+1)-01-01 12:00:00 in tz

Anchoring at local noon gives the bucketing its invariant: **every
second of imaging time on the night labelled by evening date D lands
in bucket D, with no split across adjacent buckets.** At mid-latitudes
this corresponds to the intuitive "each bucket contains exactly one
astronomical night" — but *that phrasing is wrong* at extreme
latitudes and in the polar circles (see below). The invariant that
actually matters is the no-split contract, and the noon anchor
enforces it for any latitude.

**Polar and date-line regions.** Above ≈48.5° latitude in summer
there are buckets with zero astronomical darkness at all (the sun
never dips below −18°); within the polar circles in winter the
darkness window is continuous for days or weeks at a time. The
algorithm produces correct per-bucket hours in both cases — the
``sun_alt < −18°`` predicate zeros out bright buckets, and the
integrator sums whatever seconds of darkness each calendar-date
bucket contains. In polar winter a single calendar day can yield
well over 12 h of imaging time; callers that render the output must
not cap the y-axis at 12 h (the frontend chart uses
``max(12, ⌈max_hours + 0.5⌉)`` exactly for this reason).

Compute:

    T_total  = (t_end^local − t_start^local).total_seconds()
    N        = floor(T_total / Δt)            ≈ 105 120 for a common year
    t_0      = t_start^local.astimezone(UTC)
    t_i      = t_0 + i · Δt,   i = 0, 1, …, N − 1

For timezones that observe DST, ``T_total`` is off by ±3600 s on the
year — spring-forward loses an hour, fall-back gains one, so ``N``
differs by ±12 samples. Python's tz-aware datetime subtraction
normalises both endpoints to UTC before subtracting, so this is
handled automatically without special-casing.

In code:

```python
local_start = datetime(Y, 1, 1, 12, 0, 0, tzinfo=tz)
local_end   = datetime(Y + 1, 1, 1, 12, 0, 0, tzinfo=tz)
total_seconds = (local_end - local_start).total_seconds()
N = int(total_seconds / 60.0 / _SAMPLE_MINUTES)
t_0 = astropy.time.Time(local_start.astimezone(UTC))
offsets = astropy.time.TimeDelta(
    np.arange(N, dtype=float) * _SAMPLE_SECONDS,
    format="sec",
)
times = t_0 + offsets        # astropy Time of length N
```

Astropy represents the whole vector as a single broadcastable
`Time` object; every transform below operates on it in vectorised
form.

---

## 4. Time-scale conversions

ERFA / SOFA handles all time-scale arithmetic internally when we
ask astropy for coordinates. For reference, the chain used is:

| Scale | Meaning | Offset |
|---|---|---|
| UTC | wall-clock UT | — |
| TAI | International Atomic Time | TAI = UTC + ΔAT(t) (integer leap-seconds, IERS table) |
| TT | Terrestrial Time | TT = TAI + 32.184 s (constant) |
| UT1 | mean solar time at Greenwich | UT1 = UTC + ΔUT1(t) (IERS Bulletin A, ~0.1 s) |

Planetary ephemerides (§7) are evaluated on TT. Earth rotation
(§5.1) is evaluated on UT1.

---

## 5. Earth rotation and orientation

### 5.1 Earth Rotation Angle (ERA)

The angle between the Celestial Intermediate Origin (CIO) and the
Terrestrial Intermediate Origin (TIO) is:

    ERA(UT1) = 2π · ( 0.779 057 273 264 0
                    + 1.002 737 811 911 354 48 · (UT1 − J2000.0) )
    (UT1 − J2000.0 expressed in days, result reduced mod 2π)

where J2000.0 = JD 2 451 545.0 TT (2000-01-01 12:00:00 TT).

ERFA routine: `erfa.era00(ut11, ut12)`.

### 5.2 Precession–nutation (IAU 2006/2000A)

Let N_PN(t) be the 3×3 rotation from GCRS to CIRS. It is the product
of three matrices:

- Frame-bias matrix **B** (constant, ≈ 23 mas rotation fixing the
  ICRS → mean-equinox-of-J2000 frame discrepancy).
- Precession matrix **P**(t) — IAU 2006 (Capitaine, Wallace,
  Chapront 2003): polynomial in the TT interval since J2000
  accounting for Earth's ~26 000 year axial precession.
- Nutation matrix **N**(t) — IAU 2000A (Mathews, Herring, Buffett
  2002): a sum of 1365 luni-solar periodic terms plus 687 planetary
  periodic terms representing Earth's wobble about its precession
  cone. Each term has the form

    Δψ = Σ_k [ (A_k + A'_k · T) sin(Φ_k) + (A''_k + A'''_k · T) cos(Φ_k) ]
    Δε = Σ_k [ (B_k + B'_k · T) cos(Φ_k) + (B''_k + B'''_k · T) sin(Φ_k) ]
    Φ_k = Σ_j  n_{k,j} · F_j(T)

  where F_j are the five Delaunay arguments (mean anomaly of moon
  and sun; mean argument of latitude of moon; mean elongation of
  moon from sun; longitude of ascending node of moon) plus the
  eight planetary mean longitudes. T = centuries of TT since
  J2000.0.

ERFA routine: `erfa.pnm06a(tt1, tt2)` returns the combined
**B · P · N** matrix.

### 5.3 Polar motion

ITRS (pole fixed to Earth's crust) → TIRS (pole at the CIO) uses
the IERS-supplied polar-motion parameters x_p, y_p:

    W(x_p, y_p) ≈ R_y(x_p) · R_x(y_p) · R_z(s')

Magnitude is a few tenths of an arc-second — below the precision
of a 5-minute grid — but included for correctness when astropy
has IERS data loaded.

ERFA routine: `erfa.pom00(xp, yp, sp)`.

### 5.4 Rotation matrices (glossary)

    R_x(θ) = ⎡ 1    0     0   ⎤
            ⎢ 0  cos θ  sin θ ⎥
            ⎣ 0 -sin θ  cos θ ⎦

    R_y(θ) = ⎡ cos θ  0  -sin θ ⎤
            ⎢   0    1     0   ⎥
            ⎣ sin θ  0   cos θ ⎦

    R_z(θ) = ⎡  cos θ  sin θ  0 ⎤
            ⎢ -sin θ  cos θ  0 ⎥
            ⎣    0      0    1 ⎦

---

## 6. Observer position (WGS84)

Observer geocentric position on the WGS84 ellipsoid, in ITRS:

    N(φ) = a / √(1 − e² sin² φ)
    r_obs^ITRS = (  (N + h_obs) cos φ cos λ,
                    (N + h_obs) cos φ sin λ,
                    (N(1 − e²) + h_obs) sin φ )

Built via:

```python
earth_loc = astropy.coordinates.EarthLocation(
    lat    = φ * u.deg,
    lon    = λ * u.deg,
    height = h_obs * u.m,
)
```

---

## 7. Planetary ephemerides

### 7.1 Sun — `erfa.epv00`

`epv00` is an analytic VSOP87-style expansion (Bretagnon & Francou
1988) giving Earth's heliocentric position + velocity, with
sub-milliarcsecond accuracy 1900–2100. The Sun's geocentric
direction is the negative of the Earth heliocentric vector,
transformed to GCRS.

Astropy API used: `astropy.coordinates.get_body("sun", times, earth_loc)`.
Returns a `SkyCoord` already parented to a GCRS-compatible frame
centred on Earth, with topocentric correction available when
transformed to AltAz.

### 7.2 Moon — `erfa.moon98`

`moon98` evaluates the ELP2000/82 truncated lunar theory of
Chapront-Touzé & Chapront (1988) — a periodic-term expansion of the
Moon's geocentric ecliptic position. Accuracy ≲ 30 arc-seconds over
1900–2100, more than sufficient for a 60° separation test.

Astropy API used: `astropy.coordinates.get_body("moon", times, earth_loc)`.

Returned positions are geocentric; topocentric parallax (up to
~57 arc-min for the Moon) is applied automatically when
`.transform_to(AltAz)` sees a non-geocentric `EarthLocation`.

---

## 8. Coordinate-frame transformations

### 8.1 ICRS unit vector for the target

Deep-sky targets are effectively at infinity: parallax is zero,
proper motion is absorbed upstream.

    r̂_ICRS = ( cos α · cos δ,  sin α · cos δ,  sin δ )

### 8.2 ICRS → GCRS (annual aberration + light deflection)

Aberration: classical formula to O(β²) with β = v_E / c and v_E
the Earth's barycentric velocity from `erfa.epv00`:

    r̂_GCRS = ( r̂_ICRS + β + (r̂_ICRS · β) · β / (1 + 1/γ) )
             / (1 + r̂_ICRS · β)

Magnitude up to 20 arc-seconds.

Gravitational light deflection by the Sun is < 10 mas except
within ~1° of the Sun — negligible here but included by astropy.

ERFA routine: `erfa.ab()`.

### 8.3 GCRS → CIRS

Apply the combined precession–nutation rotation from §5.2:

    r_CIRS = N_PN(t) · r̂_GCRS

### 8.4 CIRS → ITRS

Apply Earth rotation about z by ERA, plus polar motion:

    r_ITRS = W(x_p, y_p) · R_z(−ERA) · r_CIRS

### 8.5 ITRS → topocentric AltAz

Topocentric direction (for a DSO at infinity, the subtraction of
r_obs^ITRS is vanishing; for the Moon and Sun it is NOT — hence
the importance of supplying `earth_loc` to `get_body`):

    r_topo = r_ITRS − r_obs^ITRS

Local horizon basis at (φ, λ):

    ê_E = ( −sin λ,          cos λ,           0     )
    ê_N = ( −sin φ · cos λ, −sin φ · sin λ,  cos φ  )
    ê_U = (  cos φ · cos λ,  cos φ · sin λ,  sin φ  )

Project:

    E  = r̂_topo · ê_E
    N  = r̂_topo · ê_N
    U  = r̂_topo · ê_U

Altitude + azimuth:

    h  = atan2( U, √(E² + N²) )         (geometric altitude)
    Az = atan2( E, N )                   (azimuth N → E, 0..360°)

**No atmospheric refraction is applied.** Astropy's `AltAz` frame
is constructed without `pressure` / `temperature` / `obswl`, so
all altitudes downstream are *geometric*. Refraction raises a
star's apparent altitude by ~34 arc-min at the horizon, ~1.7
arc-min at 30°, and < 1 arc-min above 45°. For our altitude
thresholds and the 60° moon-separation rule this is safely
negligible.

Astropy condenses §8.2 – §8.5 into a single call:

```python
altaz_frame = astropy.coordinates.AltAz(obstime=times, location=earth_loc)
obj_altaz   = target.transform_to(altaz_frame)
obj_alt     = obj_altaz.alt.deg     # shape (N,)
obj_az      = obj_altaz.az.deg
```

The same pattern is used for the Sun and the Moon:

```python
sun_coord   = astropy.coordinates.get_body("sun",  times, earth_loc)
sun_alt     = sun_coord.transform_to(altaz_frame).alt.deg

moon_coord  = astropy.coordinates.get_body("moon", times, earth_loc)
moon_altaz  = moon_coord.transform_to(altaz_frame)
moon_alt    = moon_altaz.alt.deg
```

---

## 9. Angular separation (Vincenty formula)

Target–Moon separation σ at every sample:

    Δα = α_target − α_moon
    num   = √[ (cos δ_moon · sin Δα)²
             + (cos δ_target · sin δ_moon
                 − sin δ_target · cos δ_moon · cos Δα)² ]
    denom = sin δ_target · sin δ_moon
           + cos δ_target · cos δ_moon · cos Δα
    σ     = atan2(num, denom)

This is the numerically stable form of the great-circle distance
(Vincenty 1975), implemented in
`astropy.coordinates.angle_utilities.angular_separation`. The
`SkyCoord` convenience calls it for us:

```python
moon_sep = target.separation(moon_coord).deg        # shape (N,)
```

The small GCRS→ICRS rotation at the Moon's distance introduces a
sub-arcsecond discrepancy when the Moon coord is treated as
ICRS-compatible by `separation()`; astropy emits a
`NonRotationTransformationWarning` for it. Far below the 60°
threshold's sensitivity.

---

## 10. Per-sample quantities

At every sample i ∈ [0, N):

    obj_alt[i]      ← target altitude, deg
    obj_az[i]       ← target azimuth, deg  (needed only for local-horizon mode)
    sun_alt[i]      ← Sun altitude, deg
    moon_alt[i]     ← Moon altitude, deg           (LRGB only)
    moon_sep[i]     ← target–Moon separation, deg  (LRGB only)
    horizon_alt[i]  ← threshold altitude at obj_az[i]

`horizon_alt[i]` is either a constant `A` (fixed-degrees mode) or,
when the user has supplied a custom horizon polyline `H = {(az_k,
alt_k)}`, the piecewise-linear interpolation

    horizon_alt[i] = interpolate_horizon_altitude(H, obj_az[i])

(the helper wraps around at 0° / 360° azimuth).

Three *instantaneous* predicates — evaluated pointwise at sample i
— are:

    above_horizon(i) = obj_alt[i] > horizon_alt[i]
    is_dark(i)       = sun_alt[i] < S                     (S = −18°)
    moon_ok(i)       = (moon_alt[i] < 0)
                       ∨ (moon_sep[i] > M)                (M = 60°)
                       [LRGB; always True in narrowband]
    sample_valid(i)  = above_horizon(i) ∧ is_dark(i) ∧ moon_ok(i)

**Boundary policy.** Every threshold uses a strict inequality. A
sample landing exactly on any boundary — `sun_alt = −18°`,
`obj_alt = horizon_alt`, `moon_alt = 0°`, `moon_sep = 60°` — is
treated as **failing** the predicate. In practice floating-point
arithmetic makes exact equality effectively impossible; this rule
exists only to fully specify the algorithm.

These feed the fast-path check in §12. The accurate value used on
the chart comes from the per-segment linear-interpolation
integrator of §11.

---

## 11. Segment integrator — the core of the quantisation fix

Instead of counting valid samples and multiplying by Δt — which
quantises output to ±Δt / 2 ≈ ±2.5 min per night and shows as
jitter at the month scale — we integrate the valid time in each
segment analytically under a linear-in-time model of every
relevant quantity.

### 11.1 Linear model on a segment

Consider segment `s` spanning samples i and i+1. Let u ∈ [0, 1]
parameterise time across the segment:

    t(u) = t_i + u · Δt

Every quantity is assumed linear in u between the endpoints (which
is a very good approximation over 5 minutes — objects traverse the
sky at most ~15°/hour ≈ 1.25° per segment, and the Sun / Moon
move at most ~0.25° per segment):

    obj_alt(u)      = obj_alt[i]      + u · (obj_alt[i+1]     − obj_alt[i])
    horizon_alt(u)  = horizon_alt[i]  + u · (horizon_alt[i+1] − horizon_alt[i])
    sun_alt(u)      = sun_alt[i]      + u · (sun_alt[i+1]     − sun_alt[i])
    moon_alt(u)     = moon_alt[i]     + u · (moon_alt[i+1]    − moon_alt[i])   (LRGB)
    moon_sep(u)     = moon_sep[i]     + u · (moon_sep[i+1]    − moon_sep[i])   (LRGB)

Define four signed "predicate functions" — each strictly positive
when its predicate holds:

    f_h(u)     = obj_alt(u) − horizon_alt(u)               (> 0 ⇔ above horizon)
    f_d(u)     = S − sun_alt(u)                             (> 0 ⇔ astro dark)
    f_ma(u)    = − moon_alt(u)                              (> 0 ⇔ moon below 0°)
    f_sep(u)   = moon_sep(u) − M                            (> 0 ⇔ separation > 60°)

Each is linear in u with slope (f₂ − f₁).

### 11.2 Crossings

Any linear function with a strict sign change between u = 0 and
u = 1 crosses zero exactly once at:

    u_cross = f_endpoint1 / (f_endpoint1 − f_endpoint2)        ∈ (0, 1)

Helper (Python) that returns the root ∈ (0, 1), or `None` when no
crossing:

```python
def root(f1: float, f2: float) -> float | None:
    if f1 * f2 >= 0 or f1 == f2:
        return None
    uu = f1 / (f1 - f2)
    return uu if 0.0 < uu < 1.0 else None
```

Collect every predicate's crossing (up to four in LRGB mode, up
to two in narrowband mode). Prepend 0.0 and append 1.0:

```python
crossings = [0.0, 1.0]
u = root(obj_alt1 - horizon1, obj_alt2 - horizon2);  crossings += [u] if u is not None else []
u = root(S - sun_alt1,     S - sun_alt2);            crossings += [u] if u is not None else []
if lrgb:
    u = root(-moon_alt1,              -moon_alt2);            crossings += [u] if u is not None else []
    u = root(moon_sep1 - M,           moon_sep2 - M);         crossings += [u] if u is not None else []
crossings.sort()
```

### 11.3 Sub-interval integration

Between any two adjacent crossings u_lo < u_hi, every predicate's
sign is constant (by construction — we just inserted every
sign-change point). Evaluate the conjunction once at the midpoint:

    u_mid     = (u_lo + u_hi) / 2
    P_above_h = ( obj_alt(u_mid) > horizon_alt(u_mid) )
    P_dark    = ( sun_alt(u_mid) < S )
    P_moon_ok = ( moon_alt(u_mid) < 0 ) ∨ ( moon_sep(u_mid) > M )   [LRGB only]

If all predicates hold at the midpoint they hold throughout the
sub-interval. The sub-interval contributes

    Δseconds = (u_hi − u_lo) · Δt

Else the sub-interval contributes 0. Sum across all sub-intervals:

    seg_seconds = Σ  (u_hi − u_lo) · Δt
                  for each midpoint where all predicates hold

Implementation (`_integrate_segment`):

```python
total_u = 0.0
for i in range(len(crossings) - 1):
    u_lo, u_hi = crossings[i], crossings[i + 1]
    u_mid = 0.5 * (u_lo + u_hi)

    obj_m   = obj_alt1  + u_mid * (obj_alt2  - obj_alt1)
    horiz_m = horizon1  + u_mid * (horizon2  - horizon1)
    if obj_m <= horiz_m:
        continue
    sun_m   = sun_alt1  + u_mid * (sun_alt2  - sun_alt1)
    if sun_m >= S:
        continue
    if lrgb:
        moon_m = moon_alt1 + u_mid * (moon_alt2 - moon_alt1)
        sep_m  = moon_sep1 + u_mid * (moon_sep2 - moon_sep1)
        if not (moon_m < 0.0 or sep_m > M):
            continue
    total_u += u_hi - u_lo

return total_u * _SAMPLE_SECONDS
```

At most 4 crossings + 2 endpoints = 6 sub-interval boundaries, so
the inner loop runs ≤ 5 iterations. Typical segment has 0 crossings
→ 1 iteration; near a horizon / dusk / dawn / moon boundary it has
1 crossing → 2 iterations.

### 11.4 Validity of the linear assumption

The linear model's worst case is at meridian transit, where the
altitude curve has a local maximum and curvature is maximal.

For a star at declination δ observed from latitude φ, the exact
second derivative of altitude with respect to time at upper transit
is

    d²alt/dt² |_{transit} = −cos(φ) · cos(δ) · ω²

with ω = 2π / (sidereal day) ≈ 7.2921 × 10⁻⁵ rad/s (Earth's
sidereal rotation rate). Units: ω² gives rad/s², multiplied by the
dimensionless `cos(φ)cos(δ)` and converted to degrees — the peak
magnitude is ≈ 3.0 × 10⁻⁴ °/s² at the celestial equator viewed from
a latitude-0° observer (`cos(0)cos(0) = 1`), scaling down as either
the observer or the target moves away from the equator.

Worst-case linear-interpolation error over half a 5-minute segment
(Δt/2 = 150 s):

    ε_max = ½ · |d²alt/dt²| · (Δt/2)²
          = ½ · 3.0 × 10⁻⁴ °/s² · 150² s²
          ≈ 3.4 arc-min at (φ = 0°, δ = 0°)

At a mid-northern site (φ = 33.4°) viewing a mid-declination target
(`cos(φ)·cos(δ) ≈ 0.77`) the bound is ≈ 2.6 arc-min. Real observations
are much more benign because `ε_max` only applies at the single
transit instant — away from transit the curvature drops and the
error shrinks toward zero.

**High-latitude note:** because the bound carries a `cos(φ)` factor,
the linear approximation is *more* accurate at high-latitude
observatories, not less. An observer at 78° N (Longyearbyen) sees
the upper bound shrink to ≈ 0.2 · ω² · (Δt/2)² ≈ 30 arc-sec — better
than a 10× improvement over an equatorial observer.

For the Sun and Moon the apparent rates are much slower (sun < 0.3°/h
altitude change during the twilight window; moon < 0.5°/h), so the
linear model is even more accurate there — sub-arc-second.

None of these error bounds are within four orders of magnitude of
our 30°-ish altitude thresholds, so the linear model is essentially
exact at the precision we care about.

---

## 12. Vectorised fast path

The Python-loop integrator of §11.3 is clean but not free. For a
full year's ~105 119 segments, 99% are "stable" — none of the four
predicate sign functions changes sign between sample endpoints.
For those we compute the contribution in pure numpy:

    seg_stable_valid(i) = ¬ has_sign_change(i)
                        ∧ sample_valid(i)
                        ∧ sample_valid(i+1)

where

    has_sign_change(i) = sign(f_h[i])   · sign(f_h[i+1])   < 0
                       ∨ sign(f_d[i])   · sign(f_d[i+1])   < 0
                       ∨ sign(f_ma[i])  · sign(f_ma[i+1])  < 0   (LRGB only)
                       ∨ sign(f_sep[i]) · sign(f_sep[i+1]) < 0   (LRGB only)

Segments with `seg_stable_valid(i) = True` contribute Δt seconds
each; stable invalid segments contribute 0. Only segments with at
least one sign change fall into the slow path.

Implementation:

```python
# pointwise f's
f_h  = obj_alt - horizon_alt
f_d  = _ASTRO_DARK_DEG - sun_alt
if mode == "lrgb":
    f_ma  = -moon_alt
    f_sep = moon_sep - _MIN_MOON_SEP_DEG

# sign-change masks per predicate across adjacent samples
def has_sign_change(f):
    return f[:-1] * f[1:] < 0              # numpy bool vector of length N-1

has_cross = has_sign_change(f_h) | has_sign_change(f_d)
if mode == "lrgb":
    has_cross = has_cross | has_sign_change(f_ma) | has_sign_change(f_sep)

# fast path
sample_valid   = above_h & dark & moon_ok                    # length N
stable_full    = (~has_cross) & sample_valid[:-1] & sample_valid[1:]
seconds_per_segment = np.zeros(N - 1, dtype=float)
seconds_per_segment[stable_full] = _SAMPLE_SECONDS

# slow path — only for sign-change segments
for i in np.where(has_cross)[0]:
    seconds_per_segment[i] = _integrate_segment(…)
```

Empirically the slow path runs on a few hundred to a few thousand
segments per year (sunrise/sunset, moonrise/moonset, target rise/
set, moon-separation crossing 60°), i.e. ≲ 2% of total segments.
The pure-Python loop over those is inconsequential next to the
astropy transforms.

---

## 13. Evening-date bucketing

Each sample is assigned to exactly one calendar-date bucket, which
we label by its *evening* date. The bucket of a sample whose local
wall-clock time is `L_i` is:

    d_i   = (L_i − 12 hours).date()                 (shifted local date)
    j_i   = (d_i − Y-01-01).days                    (bucket index)

This maps the local-noon(D) → local-noon(D+1) window — which fully
contains the astronomical night anchored to evening date D — to a
single bucket labelled D. A midnight-local bucketing (the naive
choice) would split the night across two buckets, confusing the
per-night chart.

Segments are assigned to the bucket of their *left* endpoint:

    seg_day_index[i] = day_index[i]                 for i ∈ [0, N−1)

The single noon-crossing segment per day (i.e. sample 11:55 local
D+1 → sample 12:00 local D+1) lies entirely in daylight on day D,
so its integrated contribution is 0 regardless of which bucket
claims it. No special handling needed.

Implementation:

```python
utc_datetimes = times.to_datetime(timezone=UTC)     # array of aware datetimes
day_index = np.fromiter(
    (
        ((dt.astimezone(tz) - timedelta(hours=12)).date() - year_start).days
        for dt in utc_datetimes
    ),
    dtype=np.int32,
    count=len(utc_datetimes),
)
seg_day_index = day_index[:-1]
in_range = (seg_day_index >= 0) & (seg_day_index < n_days)
```

---

## 14. Per-day reduction and final output

Sum segment contributions per bucket with an unbuffered scatter-add:

    counts_seconds[j] = Σ_i  seconds_per_segment[i] · 𝟙[ seg_day_index[i] = j ]

NumPy primitive used:

```python
seconds_per_day = np.zeros(n_days, dtype=float)
np.add.at(seconds_per_day, seg_day_index[in_range], seconds_per_segment[in_range])
hours = seconds_per_day / 3600.0
```

Output: a list of (evening_date, hours) tuples for every calendar
date in the year.

---

## 15. Parallelism

The algorithm is embarrassingly parallel over date ranges: each
chunk of contiguous evening dates needs its own time grid (from
local noon of its first date to local noon of its last-plus-one
date) and produces independent `(date, hours)` tuples.

Implementation splits the year into `max_workers` equal date ranges
aligned on local-noon boundaries, runs each in a spawned worker
via `concurrent.futures.ProcessPoolExecutor`, then merges and
sorts the per-chunk output.

```python
ctx = multiprocessing.get_context("spawn")         # safe on macOS + Linux
with ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx) as pool:
    futures = [
        pool.submit(
            _compute_subrange,
            location, ra_deg, dec_deg,
            threshold_deg, mode,
            start_d, end_d,
        )
        for start_d, end_d in chunks
    ]
    pairs = [p for f in futures for p in f.result()]
```

The worker function `_compute_subrange` is picklable — a
module-level function whose arguments are all plain data
(`PlannerLocation` is a frozen dataclass of scalars and tuples;
date objects pickle fine; threshold and mode are a float and a
string literal).

Observed wall-clock on a mid-range Mac (M64 example, LRGB mode,
full 365-day year):

| Workers | Wall time |
|---|---|
| 1 | 20.7 s |
| 2 | 11.0 s |
| 4 |  6.1 s |
| 6 |  4.3 s |

Near-linear speedup up to the physical-core count; diminishing
beyond. The API caps at 12 workers to keep astropy-import overhead
(spawn-startup) from dominating for very short chunks on
many-core hosts.

The API endpoint reads the user's `settings.max_worker_cores`; a
`None` value defaults to `max(1, cpu_count − 1)`.

### Long-lived pool reuse

Creating a fresh `ProcessPoolExecutor` on each request pays ~1 s per
worker of astropy-import cost. For a FastAPI server serving several
DSO detail opens per night, that overhead dominates. The module
therefore caches a single `ProcessPoolExecutor` (keyed on worker
count) at the first call and reuses it for every subsequent request.
Observed first-call ≈ 4.3 s at 6 workers; subsequent calls drop to
≈ 2.5 s for the same target because the workers' astropy modules
are already imported.

Cleanup on interpreter shutdown is handled via `atexit.register`,
so normal process termination reaps all workers. `uvicorn --reload`
leaks old worker processes between reloads (no lifespan hook
coordinates shutdown); production deployments don't reload, so
this is acceptable. If that becomes a real problem, wrap the pool
in FastAPI's `lifespan` handler.

---

## 16. End-to-end code (full annotated flow)

```python
from __future__ import annotations

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import astropy.units as u
import numpy as np
from astropy.coordinates import AltAz, SkyCoord, get_body
from astropy.time import Time, TimeDelta

from nightcrate.services.horizon import interpolate_horizon_altitude
from nightcrate.services.planner_visibility import (
    PlannerLocation,
    _make_earth_location,
)

_SAMPLE_MINUTES    = 5
_SAMPLE_SECONDS    = _SAMPLE_MINUTES * 60          # 300
_ASTRO_DARK_DEG    = -18.0
_MIN_MOON_SEP_DEG  = 60.0


def _integrate_segment(
    obj_alt1, obj_alt2,
    horizon1, horizon2,
    sun_alt1, sun_alt2,
    moon_alt1, moon_alt2,          # may be None in narrowband
    moon_sep1, moon_sep2,          # may be None in narrowband
    lrgb: bool,
) -> float:
    """Return valid seconds within one 5-minute sample pair."""
    crossings = [0.0, 1.0]

    def root(f1, f2):
        if f1 * f2 >= 0 or f1 == f2:
            return None
        uu = f1 / (f1 - f2)
        return uu if 0.0 < uu < 1.0 else None

    # horizon crossing
    r = root(obj_alt1 - horizon1, obj_alt2 - horizon2)
    if r is not None: crossings.append(r)
    # darkness crossing (f_d = −18 − sun_alt)
    r = root(_ASTRO_DARK_DEG - sun_alt1, _ASTRO_DARK_DEG - sun_alt2)
    if r is not None: crossings.append(r)
    if lrgb:
        r = root(-moon_alt1, -moon_alt2)
        if r is not None: crossings.append(r)
        r = root(moon_sep1 - _MIN_MOON_SEP_DEG,
                 moon_sep2 - _MIN_MOON_SEP_DEG)
        if r is not None: crossings.append(r)
    crossings.sort()

    total_u = 0.0
    for i in range(len(crossings) - 1):
        u_lo, u_hi = crossings[i], crossings[i + 1]
        u_mid = 0.5 * (u_lo + u_hi)

        obj_m   = obj_alt1 + u_mid * (obj_alt2 - obj_alt1)
        horiz_m = horizon1 + u_mid * (horizon2 - horizon1)
        if obj_m <= horiz_m:
            continue
        sun_m   = sun_alt1 + u_mid * (sun_alt2 - sun_alt1)
        if sun_m >= _ASTRO_DARK_DEG:
            continue
        if lrgb:
            moon_m = moon_alt1 + u_mid * (moon_alt2 - moon_alt1)
            sep_m  = moon_sep1 + u_mid * (moon_sep2 - moon_sep1)
            if not (moon_m < 0.0 or sep_m > _MIN_MOON_SEP_DEG):
                continue
        total_u += u_hi - u_lo

    return total_u * _SAMPLE_SECONDS


def _compute_subrange(
    location,
    ra_deg, dec_deg,
    threshold_deg,                 # float or None for "use custom horizon"
    mode,                          # "lrgb" or "narrowband"
    start_date, end_date,
):
    coord     = SkyCoord(ra=ra_deg*u.deg, dec=dec_deg*u.deg, frame="icrs")
    earth_loc = _make_earth_location(location)
    tz        = ZoneInfo(location.timezone)

    # 5-min time grid spanning local-noon(start) → local-noon(end)
    local_start = datetime(start_date.year, start_date.month, start_date.day,
                           12, 0, 0, tzinfo=tz)
    local_end   = datetime(end_date.year,   end_date.month,   end_date.day,
                           12, 0, 0, tzinfo=tz)
    total_seconds = (local_end - local_start).total_seconds()
    n_samples = int(total_seconds / 60.0 / _SAMPLE_MINUTES)
    n_days    = (end_date - start_date).days

    t0       = Time(local_start.astimezone(UTC))
    offsets  = TimeDelta(
        np.arange(n_samples, dtype=float) * _SAMPLE_SECONDS, format="sec"
    )
    times    = t0 + offsets

    altaz_frame = AltAz(obstime=times, location=earth_loc)

    # §7.1 sun
    sun_alt = np.asarray(
        get_body("sun", times, earth_loc).transform_to(altaz_frame).alt.deg
    )

    # §8 target
    obj_altaz = coord.transform_to(altaz_frame)
    obj_alt   = np.asarray(obj_altaz.alt.deg)

    # §10 horizon
    if threshold_deg is not None:
        horizon_alt = np.full(n_samples, float(threshold_deg))
    else:
        obj_az      = np.asarray(obj_altaz.az.deg)
        horizon_alt = interpolate_horizon_altitude(location.horizon_points, obj_az)

    # §7.2 moon (LRGB only)
    if mode == "lrgb":
        moon_body  = get_body("moon", times, earth_loc)
        moon_altaz = moon_body.transform_to(altaz_frame)
        moon_alt   = np.asarray(moon_altaz.alt.deg)
        moon_sep   = np.asarray(coord.separation(moon_body).deg)  # §9
    else:
        moon_alt = moon_sep = None

    # §10 per-sample predicates
    above_h = obj_alt > horizon_alt
    dark    = sun_alt < _ASTRO_DARK_DEG
    if mode == "lrgb":
        moon_ok = (moon_alt < 0.0) | (moon_sep > _MIN_MOON_SEP_DEG)
    else:
        moon_ok = np.ones(n_samples, dtype=bool)
    sample_valid = above_h & dark & moon_ok

    # §11/12 sign-change masks
    f_h = obj_alt - horizon_alt
    f_d = _ASTRO_DARK_DEG - sun_alt

    def has_sign_change(f):
        return f[:-1] * f[1:] < 0

    has_cross = has_sign_change(f_h) | has_sign_change(f_d)
    if mode == "lrgb":
        has_cross = has_cross | has_sign_change(-moon_alt) | has_sign_change(
            moon_sep - _MIN_MOON_SEP_DEG
        )

    # fast path
    stable      = ~has_cross
    stable_full = stable & sample_valid[:-1] & sample_valid[1:]
    seconds_per_segment = np.zeros(n_samples - 1, dtype=float)
    seconds_per_segment[stable_full] = _SAMPLE_SECONDS

    # slow path
    for i in np.where(has_cross)[0]:
        seconds_per_segment[i] = _integrate_segment(
            float(obj_alt[i]),  float(obj_alt[i + 1]),
            float(horizon_alt[i]), float(horizon_alt[i + 1]),
            float(sun_alt[i]),  float(sun_alt[i + 1]),
            float(moon_alt[i]) if moon_alt is not None else None,
            float(moon_alt[i + 1]) if moon_alt is not None else None,
            float(moon_sep[i]) if moon_sep is not None else None,
            float(moon_sep[i + 1]) if moon_sep is not None else None,
            lrgb=(mode == "lrgb"),
        )

    # §13 evening-date bucketing
    utc_datetimes = times.to_datetime(timezone=UTC)
    day_index = np.fromiter(
        (
            ((dt.astimezone(tz) - timedelta(hours=12)).date() - start_date).days
            for dt in utc_datetimes
        ),
        dtype=np.int32,
        count=len(utc_datetimes),
    )
    seg_day_index = day_index[:-1]
    in_range      = (seg_day_index >= 0) & (seg_day_index < n_days)

    # §14 per-day reduction
    seconds_per_day = np.zeros(n_days, dtype=float)
    np.add.at(
        seconds_per_day,
        seg_day_index[in_range],
        seconds_per_segment[in_range],
    )
    hours = seconds_per_day / 3600.0

    return [
        (start_date + timedelta(days=i), round(float(hours[i]), 2))
        for i in range(n_days)
    ]


def compute_annual_hours(
    location,
    year,
    dso,                           # (id, ra_deg, dec_deg) tuple or SkyCoord
    *,
    threshold_deg,                 # float or None
    mode,                          # "lrgb" | "narrowband"
    max_workers=None,
):
    # validation + scalar extraction of (ra, dec) omitted for brevity
    year_start = date(year, 1, 1)
    year_end   = date(year + 1, 1, 1)
    n_days     = (year_end - year_start).days

    n_workers = max(1, max_workers or 1)
    if n_workers == 1:
        pairs = _compute_subrange(
            location, ra_deg, dec_deg, threshold_deg, mode,
            year_start, year_end,
        )
    else:
        n_workers = min(n_workers, n_days)
        bounds = [
            year_start + timedelta(days=(n_days * i) // n_workers)
            for i in range(n_workers + 1)
        ]
        chunks = list(zip(bounds[:-1], bounds[1:], strict=True))
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx) as pool:
            futures = [
                pool.submit(
                    _compute_subrange,
                    location, ra_deg, dec_deg, threshold_deg, mode,
                    start_d, end_d,
                )
                for start_d, end_d in chunks
            ]
            pairs = [p for f in futures for p in f.result()]

    pairs.sort(key=lambda p: p[0])
    return pairs        # [(date, hours), …] — wrap in your chosen output type
```

---

## 17. Precision and accuracy budget

| Source of error | Magnitude |
|---|---|
| Linear interpolation inside a 5-min segment (altitude curvature at meridian) | ≲ 3.4 arc-min at (φ = 0°, δ = 0°); ≲ 30 arc-sec at high-latitude observers (see §11.4) |
| Linear interpolation for sun altitude (twilight window) | ≲ 1 arc-sec |
| Linear interpolation for moon alt / sep | ≲ 1 arc-sec |
| ERFA `epv00` Earth/Sun position | << 1 arc-sec |
| ERFA `moon98` Moon position | ≲ 30 arc-sec |
| IAU 2006/2000A precession–nutation | ≲ 0.1 mas |
| No atmospheric refraction applied | +34 arc-min apparent at horizon; +1.7 arc-min at 30°; < 1 arc-min above 45° |
| IERS polar motion / UT1 — predicted values only (`astropy.utils.iers.conf.auto_download = False`) | ≲ 0.5 arc-sec for Earth-orientation parameters; our code sets this in `main.py` to silence the download-failure warning on offline observatory boxes |
| Sample-grid quantisation | **0** — integrator is analytic between samples |
| 60° separation boundary is strict (`>`) | `== 60°` fails the test (sub-arc-second edge case) |
| Moon-below-horizon boundary uses geometric 0° (no refraction) | up to 34 arc-min difference from "apparent horizon" |

Net result: per-night output is continuous in the input data to
better than 1 second of time. Month-to-month jitter that the old
sample-counting produced (±2.5 min) is eliminated.

---

## 18. Worked example

**Target:** M 64 (Black Eye Galaxy) — α = 12ʰ 56ᵐ 44.4ˢ, δ = +21°40′58″.
**Location:** Example site — φ = 33.45°, λ = −112.07°, h_obs = 331 m,
no DST.
**Year:** 2026 (non-leap).
**Mode:** `lrgb`, threshold `A = 30°`.

- `N = 365 × 86400 / 300 = 105 120` samples.
- `n_days = 365`.
- `out.len() = 365`.

A few representative outputs the service produces (rounded to
0.01 h):

    2026-01-01    3.92
    2026-01-04    4.08
    2026-01-07    4.42
    2026-01-25    5.50
    2026-01-28    1.33      ← Moon passing within 60° of M 64
    2026-01-31    0.00      ← Moon within 60° for the entire dark window
    2026-02-09    2.67
    2026-02-15    6.58
    2026-02-21    6.67
    2026-02-27    0.33

Peak months December–January, trough June–July (M 64 transits
during daylight in mid-summer). The ~29.5-day oscillation is the
lunar synodic month.

---

## 19. References

- Kaplan, G. H. 2005, *The IAU Resolutions on Astronomical
  Reference Systems, Time Scales, and Earth Rotation Models*,
  US Naval Observatory Circular 179.
- Capitaine, N., Wallace, P. T., Chapront, J. 2003, A&A 412, 567.
  (IAU 2006 precession.)
- Mathews, P. M., Herring, T. A., Buffett, B. A. 2002, JGR 107, B4.
  (IAU 2000A nutation.)
- Chapront-Touzé, M., Chapront, J. 1988, A&A 190, 342.
  (ELP2000/82 lunar theory.)
- Bretagnon, P., Francou, G. 1988, A&A 202, 309.
  (VSOP87 planetary theory.)
- Vincenty, T. 1975, *Survey Review* 23, 88.
  (Numerically stable great-circle distance.)
- ERFA Library: <https://github.com/liberfa/erfa>
- IAU SOFA: <http://www.iausofa.org/>
- astropy coordinates docs: <https://docs.astropy.org/en/stable/coordinates/>
- astropy ephemeris docs (solar-system body functions):
  <https://docs.astropy.org/en/stable/coordinates/solarsystem.html>
