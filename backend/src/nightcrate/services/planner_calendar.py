"""Calendar-view data for the wishlist Gantt chart (v0.30.0).

Computes month labels and finds new/full moon dates by scanning
illumination across the date range for local minima/maxima.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from astropy.time import Time

from nightcrate.services.astronomy import compute_illumination_pct


@dataclass(frozen=True, slots=True)
class MoonPhaseMonth:
    month: str
    new_moon_date: str
    full_moon_date: str


def _generate_month_labels(start: date, num_months: int) -> list[str]:
    labels = []
    current = date(start.year, start.month, 1)
    for _ in range(num_months):
        labels.append(current.strftime("%Y-%m"))
        current = _month_add(current, 1)
    return labels


def _month_add(d: date, months: int) -> date:
    month = d.month + months - 1
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)


def _compute_moon_phases(month_labels: list[str]) -> list[MoonPhaseMonth]:
    if not month_labels:
        return []

    start = date.fromisoformat(f"{month_labels[0]}-01")
    last = date.fromisoformat(f"{month_labels[-1]}-01")
    end = _month_add(last, 1)

    days: list[tuple[date, float]] = []
    current = start - timedelta(days=1)
    while current <= end + timedelta(days=1):
        t = Time(f"{current.isoformat()}T12:00:00", scale="utc")
        days.append((current, compute_illumination_pct(t)))
        current += timedelta(days=1)

    new_moons: list[date] = []
    full_moons: list[date] = []
    for i in range(1, len(days) - 1):
        _, prev_ill = days[i - 1]
        d, ill = days[i]
        _, next_ill = days[i + 1]
        if ill <= prev_ill and ill <= next_ill and ill < 20:
            new_moons.append(d)
        if ill >= prev_ill and ill >= next_ill and ill > 80:
            full_moons.append(d)

    def find_in_month(events: list[date], y: int, m: int) -> str:
        for d in events:
            if d.year == y and d.month == m:
                return d.isoformat()
        return ""

    results = []
    for label in month_labels:
        y, m = int(label[:4]), int(label[5:])
        results.append(
            MoonPhaseMonth(
                month=label,
                new_moon_date=find_in_month(new_moons, y, m),
                full_moon_date=find_in_month(full_moons, y, m),
            )
        )
    return results
