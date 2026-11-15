"""Pure aggregation and ranking for the Home page."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal


@dataclass(frozen=True)
class MonthSummary:
    month: str
    minutes: float


@dataclass(frozen=True)
class BestNight:
    date: date
    minutes: float
    project_id: int
    project_name: str
    other_projects: int


@dataclass(frozen=True)
class YearSummary:
    since: date
    minutes: float
    nights: int
    new_pictures: int
    best_night: BestNight | None
    months: list[MonthSummary]


@dataclass(frozen=True)
class ForecastLocation:
    location_id: int
    name: str
    note: Literal["default", "used"] | None
    active_projects: int


@dataclass(frozen=True)
class RigRank:
    rig_id: int
    name: str
    sort_order: int
    minutes: float
    nights: int
    last_used: date | None
    active_projects: int


@dataclass(frozen=True)
class LocationRank:
    location_id: int
    name: str
    is_default: bool
    minutes: float
    nights: int
    last_used: date | None
    active_projects: int


def _shift_month(value: date, delta: int) -> date:
    index = value.year * 12 + value.month - 1 + delta
    return date(index // 12, index % 12 + 1, 1)


def window_start(today: date) -> date:
    """First day of the oldest month in the rolling twelve-month window."""
    return _shift_month(today.replace(day=1), -11)


def month_keys(today: date) -> list[str]:
    start = window_start(today)
    return [_shift_month(start, offset).strftime("%Y-%m") for offset in range(12)]


def stage_of(status: str, minutes: float) -> str:
    if status == "active":
        return "capturing" if minutes > 0 else "not_started"
    return status


def summarise_year(
    sessions: list[tuple[int, str, date, float]],
    images: list[tuple[date]],
    today: date,
) -> YearSummary:
    since = window_start(today)
    keys = month_keys(today)
    month_minutes = dict.fromkeys(keys, 0.0)
    night_projects: dict[date, dict[tuple[int, str], float]] = {}
    total = 0.0

    for project_id, project_name, session_date, minutes in sessions:
        if not since <= session_date <= today:
            continue
        value = float(minutes)
        total += value
        month_minutes[session_date.strftime("%Y-%m")] += value
        projects = night_projects.setdefault(session_date, {})
        key = (project_id, project_name)
        projects[key] = projects.get(key, 0.0) + value

    best: BestNight | None = None
    if night_projects:
        best_date, projects = max(
            night_projects.items(),
            key=lambda item: (sum(item[1].values()), item[0]),
        )
        (project_id, project_name), _ = min(
            projects.items(),
            key=lambda item: (-item[1], item[0][1].casefold(), item[0][0]),
        )
        best = BestNight(
            date=best_date,
            minutes=sum(projects.values()),
            project_id=project_id,
            project_name=project_name,
            other_projects=len(projects) - 1,
        )

    return YearSummary(
        since=since,
        minutes=total,
        nights=len(night_projects),
        new_pictures=sum(since <= added <= today for (added,) in images),
        best_night=best,
        months=[MonthSummary(month=key, minutes=month_minutes[key]) for key in keys],
    )


def rank_forecast_locations(
    locations: list[tuple[int, str, bool]],
    active_counts: dict[int, int],
) -> list[ForecastLocation]:
    """The default, then locations active projects use, then the rest by name; at most 4."""

    def by_name(row: tuple[int, str, bool]) -> tuple[str, int]:
        return (row[1].casefold(), row[0])

    defaults = sorted((row for row in locations if row[2]), key=by_name)
    used = [row for row in locations if active_counts.get(row[0], 0) > 0 and not row[2]]
    used.sort(key=lambda row: (-active_counts[row[0]], *by_name(row)))
    selected = [*defaults[:1], *used]
    chosen = {row[0] for row in selected}
    selected += sorted((row for row in locations if row[0] not in chosen), key=by_name)

    result = []
    for location_id, name, is_default in selected[:4]:
        count = active_counts.get(location_id, 0)
        result.append(
            ForecastLocation(
                location_id=location_id,
                name=name,
                note="default" if is_default else ("used" if count else None),
                active_projects=count,
            )
        )
    return result


def rank_rigs(rigs: list[RigRank]) -> list[RigRank]:
    return sorted(
        rigs,
        key=lambda rig: (-rig.minutes, rig.sort_order, rig.name.casefold(), rig.rig_id),
    )[:5]


def rank_locations(locations: list[LocationRank]) -> list[LocationRank]:
    return sorted(
        locations,
        key=lambda location: (
            not location.is_default,
            -location.minutes,
            location.name.casefold(),
            location.location_id,
        ),
    )[:5]
