"""Old-vs-new comparison for services/imaging_quality.py and a monotonicity sweep.

Run:  python imaging_quality_examples.py

The five real hours use supporting factors reconstructed to sit inside the
stated ranges (seeing 83–91, transparency 40–42, moon 100, wind calm 48–95) and
chosen so the OLD algorithm reproduces the scores from the bug report to ±1.
"""

from __future__ import annotations

import math

from imaging_quality import Mode, score_hour, cloud_yield, UNUSABLE_AVAILABILITY

# --------------------------------------------------------------------------- #
# The algorithm being replaced, transcribed from the bug report.
# --------------------------------------------------------------------------- #

def old_score(*, low, mid, high, total, seeing, transparency, moon, wind_calm, narrowband=False):
    if None not in (low, mid, high):
        effective = min(100.0, low * 1.0 + mid * 0.9 + high * 0.6)
        sky = 100.0 - effective
    else:
        sky = 100.0 - total
    gating = math.sqrt(sky / 100.0)
    if narrowband:
        other = transparency * 0.25 + seeing * 0.25 + wind_calm * 0.10
        overall = sky * 0.40 + other * gating
    else:
        other = seeing * 0.25 + transparency * 0.15 + moon * 0.15 + wind_calm * 0.10
        overall = sky * 0.35 + other * gating
    return int(math.floor(overall + 0.5))


def old_label(s):
    return "Excellent" if s >= 80 else "Good" if s >= 55 else "Marginal" if s >= 30 else "Poor"


# --------------------------------------------------------------------------- #
# Cases
# --------------------------------------------------------------------------- #

NIGHT = dict(moon=100)  # new moon
IDEAL = dict(seeing=100, transparency=100, wind_calm=100, moon=100)

real_hours = [
    # hour, L, M, H, T, seeing, transparency, wind_calm, old score reported
    ("19:00",  0,  0,  60,  60, 85, 40, 48, 60),
    ("20:00",  0,  0, 100, 100, 90, 41, 70, 46),
    ("21:00",  0,  0, 100, 100, 91, 42, 82, 47),
    ("22:00",  0,  0, 100, 100, 83, 40, 48, 42),
    ("04:00",  0, 17, 100, 100, 88, 41, 79, 34),
]

boundary = [
    # name, L, M, H, T
    ("clear sky",        0,   0,   0,   0),
    ("100% low",       100,   0,   0, 100),
    ("100% high",        0,   0, 100, 100),
    ("50% high",         0,   0,  50,  50),
    ("50% low",         50,   0,   0,  50),
    ("20% high",         0,   0,  20,  20),
    ("80% high",         0,   0,  80,  80),
    ("total only 30%", None, None, None, 30),
]


def row(name, L, M, H, T, seeing, transparency, wind_calm, moon, reported=None, mode=Mode.NORMAL):
    o = old_score(low=L, mid=M, high=H, total=T, seeing=seeing, transparency=transparency,
                  moon=moon, wind_calm=wind_calm, narrowband=(mode is Mode.NARROWBAND))
    n = score_hour(cloud_cover=T, cloud_cover_low=L, cloud_cover_mid=M, cloud_cover_high=H,
                   seeing=seeing, transparency=transparency, wind_calm=wind_calm, moon=moon,
                   mode=mode)
    flags = ",".join(f.value for f in n.flags) or "-"
    rep = f"{reported:>3}" if reported is not None else "  -"
    print(f"| {name:<22} | {str(L):>4} {str(M):>4} {str(H):>4} {T:>4} | {rep} {o:>3} {old_label(o):<9} "
          f"| {n.score:>3} {n.label:<9} | {n.availability:>5.2f} | {n.quality:>5.1f} | {flags}")


def header(title):
    print(f"\n### {title}\n")
    print("| hour / case            |    L    M    H    T | old rep/calc lbl  | new score lbl | avail | qual  | flags")
    print("|------------------------|---------------------|-------------------|---------------|-------|-------|------")


header("Five real hours — example night factors (new moon), NORMAL mode")
for h, L, M, H, T, s, t, w, rep in real_hours:
    row(h, L, M, H, T, s, t, w, 100, rep)

header("Boundary cases — all supporting factors ideal (isolates cloud), NORMAL mode")
for name, L, M, H, T in boundary:
    row(name, L, M, H, T, **IDEAL)

header("Boundary cases — example night factors (seeing 90, transparency 41, wind 70), NORMAL")
for name, L, M, H, T in boundary:
    row(name, L, M, H, T, seeing=90, transparency=41, wind_calm=70, moon=100)

header("Moon and mode — clear sky, seeing 90, transparency 80, wind 80")
for moon in (100, 50, 0):
    row(f"moon {moon} NORMAL",     0, 0, 0, 0, 90, 80, 80, moon)
    row(f"moon {moon} NARROWBAND", 0, 0, 0, 0, 90, 80, 80, moon, mode=Mode.NARROWBAND)

# --------------------------------------------------------------------------- #
# Gates and edge cases
# --------------------------------------------------------------------------- #

print("\n### Gates\n")
base = dict(cloud_cover=10, cloud_cover_low=0, cloud_cover_mid=0, cloud_cover_high=10,
            seeing=90, transparency=80, wind_calm=80, moon=100)
for desc, kw in [
    ("baseline 10% high, ideal-ish", {}),
    ("no astronomical darkness (polar summer)", dict(darkness=0.0)),
    ("half the hour in darkness", dict(darkness=0.5)),
    ("precip probability 55%", dict(precipitation_probability=55)),
    ("precip probability 80%", dict(precipitation_probability=80)),
    ("0.2 mm precipitation", dict(precipitation_mm=0.2)),
    ("wind 50 km/h sustained", dict(wind_speed_kmh=50)),
    ("wind 65 km/h sustained", dict(wind_speed_kmh=65)),
    ("dew spread 1.5 C", dict(temperature_c=12.0, dew_point_c=10.5)),
    ("layers missing, total 40%", dict(cloud_cover=40, cloud_cover_low=None, cloud_cover_mid=None, cloud_cover_high=None)),
    ("total missing, layers 30/0/30", dict(cloud_cover=None, cloud_cover_low=30, cloud_cover_mid=0, cloud_cover_high=30)),
]:
    r = score_hour(**{**base, **kw})
    print(f"- {desc:<42} score {r.score:>3} {r.label:<9} avail {r.availability:.2f}  "
          f"flags: {','.join(f.value for f in r.flags) or '-'}")

# --------------------------------------------------------------------------- #
# Monotonicity sweep
# --------------------------------------------------------------------------- #

print("\n### Monotonicity sweep")
ok = True
prev = None
for c in range(0, 101):
    r = score_hour(cloud_cover=c, seeing=80, transparency=70, wind_calm=60, moon=90)
    if prev is not None and r.score > prev:
        ok = False
    prev = r.score
for name in ("seeing", "transparency", "wind_calm", "moon"):
    prev = None
    for v in range(0, 101):
        kw = dict(seeing=80, transparency=70, wind_calm=60, moon=90)
        kw[name] = v
        r = score_hour(cloud_cover=20, **kw)
        if prev is not None and r.score < prev:
            ok = False
        prev = r.score
# adding a layer never raises the score even if the (buggy) total stays put
for h in range(0, 101, 10):
    a = score_hour(cloud_cover=30, cloud_cover_low=30, cloud_cover_mid=0, cloud_cover_high=0,
                   seeing=80, transparency=70, wind_calm=60, moon=90).score
    b = score_hour(cloud_cover=30, cloud_cover_low=30, cloud_cover_mid=0, cloud_cover_high=h,
                   seeing=80, transparency=70, wind_calm=60, moon=90).score
    if b > a:
        ok = False
print("all monotonic:", ok)

print("\n### Cloud yield curve, k = 1.5 (availability at each total cover)")
print("cover%   " + " ".join(f"{c:>5}" for c in range(0, 101, 10)))
print("yield    " + " ".join(f"{cloud_yield(c / 100):>5.2f}" for c in range(0, 101, 10)))
print(f"Unusable label at availability < {UNUSABLE_AVAILABILITY} => cover > "
      f"{100 * (1 - UNUSABLE_AVAILABILITY ** (1 / 1.5)):.0f}%")
