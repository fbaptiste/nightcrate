"""Declared provider coverage derived only from fetch and request parameters."""

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Final

# Hours after fetch that each source is expected to cover (spec §3.2). Each is
# the lowest reach observed for any field the verdict uses, minus 6 h, floored
# to the hour and never above the spec's starting value (ECMWF 14 d, GFS 15 d,
# ICON 162 h, best_match 15 d). Observed hourly for 24 h (25 runs,
# 2026-10-18/19) from live Open-Meteo requests matching the app's own, at the
# public test location, London and Sydney. Lowest reach: ECMWF precipitation
# 340.7 h, GFS 359.8 h, ICON 164.7 h, best_match precipitation chance 337.7 h.
# Too long a value makes the tail expected-missing and triggers repair
# refetches; too short only makes the tail informational.
DECLARED_COVERAGE: Final[dict[str, timedelta]] = {
    "ecmwf_ifs025": timedelta(hours=334),
    "gfs_seamless": timedelta(hours=353),
    "icon_seamless": timedelta(hours=158),
    "best_match": timedelta(hours=331),
    "cams": timedelta(days=4),
}


@dataclass(frozen=True)
class ModelMeta:
    domain: str
    init_utc: datetime
    available_utc: datetime
    temporal_resolution: timedelta
    update_interval: timedelta


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("coverage timestamps must be timezone-aware")
    return value.astimezone(UTC)


def requested_range(
    fetched_at: datetime, *, forecast_days: int, past_days: int
) -> tuple[datetime, datetime]:
    """Return the first and last hourly stamps requested from a GMT calendar range."""
    if forecast_days < 1 or past_days < 0:
        raise ValueError("forecast_days must be positive and past_days non-negative")
    fetched_utc = _aware_utc(fetched_at)
    today = datetime.combine(fetched_utc.date(), time.min, tzinfo=UTC)
    first = today - timedelta(days=past_days)
    last = today + timedelta(days=forecast_days) - timedelta(hours=1)
    return first, last


def expected_until(source: str, fetched_at: datetime, last_requested_utc: datetime) -> datetime:
    """Cap a source's declared reach at the request's final timestamp."""
    fetched_utc = _aware_utc(fetched_at)
    last_requested = _aware_utc(last_requested_utc)
    return min(fetched_utc + DECLARED_COVERAGE[source], last_requested)


def last_expected_stamp(
    source: str, fetched_at: datetime, last_requested_utc: datetime
) -> datetime:
    """Return the last whole-UTC-hour stamp a complete series must reach."""
    return expected_until(source, fetched_at, last_requested_utc).replace(
        minute=0, second=0, microsecond=0
    )


def parse_model_meta(raw_json: str | None) -> dict[str, ModelMeta]:
    """Parse usable Open-Meteo model metadata, dropping defective domains."""
    if raw_json is None:
        return {}
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError, TypeError:
        return {}
    if not isinstance(payload, dict):
        return {}

    result: dict[str, ModelMeta] = {}
    for domain, body in payload.items():
        if not isinstance(domain, str) or not isinstance(body, dict):
            continue
        try:
            values = (
                body["last_run_initialisation_time"],
                body["last_run_availability_time"],
                body["temporal_resolution_seconds"],
                body["update_interval_seconds"],
            )
            if any(type(value) not in (int, float) for value in values):
                continue
            numeric = tuple(float(value) for value in values)
            if not all(math.isfinite(value) for value in numeric):
                continue
            init_seconds, available_seconds, resolution_seconds, update_seconds = numeric
            if resolution_seconds <= 0 or update_seconds <= 0:
                continue
            result[domain] = ModelMeta(
                domain=domain,
                init_utc=datetime.fromtimestamp(init_seconds, UTC),
                available_utc=datetime.fromtimestamp(available_seconds, UTC),
                temporal_resolution=timedelta(seconds=resolution_seconds),
                update_interval=timedelta(seconds=update_seconds),
            )
        except KeyError, OverflowError, OSError, ValueError:
            continue
    return result


def coarse_cloud_from(ecmwf_meta: ModelMeta | None, fetched_at: datetime) -> datetime:
    """Return the approximate start of ECMWF's coarse cloud-resolution tail."""
    if ecmwf_meta is None:
        return _aware_utc(fetched_at) + timedelta(hours=136)
    init = _aware_utc(ecmwf_meta.init_utc)
    base_hour = 12 if init.hour >= 12 else 0
    base = init.replace(hour=base_hour, minute=0, second=0, microsecond=0)
    return base + timedelta(hours=144)
