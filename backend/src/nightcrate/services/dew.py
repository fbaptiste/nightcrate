"""Dew risk classification based on temperature-dew point spread.

Pure computation module — no DB, no HTTP, no FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass

DEW_RISK_LOW = "low"  # spread > 5.0 °C
DEW_RISK_MODERATE = "moderate"  # spread 3.0 - 5.0 °C
DEW_RISK_HIGH = "high"  # spread 1.0 - 3.0 °C
DEW_RISK_CRITICAL = "critical"  # spread < 1.0 °C


@dataclass(frozen=True)
class DewSafeWindow:
    label: str  # "all_night" | "until" | "after" | "none"
    until_time: str | None = None  # "HH:MM" local
    after_time: str | None = None  # "HH:MM" local


def classify_dew_risk(temperature_c: float, dew_point_c: float) -> str:
    """Classify dew risk from temperature-dew point spread."""
    spread = temperature_c - dew_point_c
    if spread < 1.0:
        return DEW_RISK_CRITICAL
    if spread < 3.0:
        return DEW_RISK_HIGH
    if spread < 5.0:
        return DEW_RISK_MODERATE
    return DEW_RISK_LOW


def compute_dew_safe_window(
    hourly_during_darkness: list[tuple[str, float, float]],
) -> DewSafeWindow:
    """Determine the dew-safe window from hourly darkness data.

    Args:
        hourly_during_darkness: List of (HH:MM_local, temperature_c, dew_point_c)
            tuples for hours during the darkness window.

    Returns:
        DewSafeWindow describing when conditions are dew-safe.
        Safe = spread >= 3.0 °C (below "high" risk threshold).
    """
    if not hourly_during_darkness:
        return DewSafeWindow(label="none")

    safe_flags = [(t - d) >= 3.0 for (_, t, d) in hourly_during_darkness]

    if all(safe_flags):
        return DewSafeWindow(label="all_night")
    if not any(safe_flags):
        return DewSafeWindow(label="none")

    # Find first unsafe hour
    first_unsafe_idx = next(i for i, s in enumerate(safe_flags) if not s)
    # Find last unsafe hour
    last_unsafe_idx = (
        len(safe_flags) - 1 - next(i for i, s in enumerate(reversed(safe_flags)) if not s)
    )

    if first_unsafe_idx == 0:
        # Starts unsafe, may become safe later
        if last_unsafe_idx + 1 < len(hourly_during_darkness):
            safe_time = hourly_during_darkness[last_unsafe_idx + 1][0]
            return DewSafeWindow(label="after", after_time=safe_time)
        return DewSafeWindow(label="none")

    if last_unsafe_idx == len(safe_flags) - 1:
        # Ends unsafe
        unsafe_time = hourly_during_darkness[first_unsafe_idx][0]
        return DewSafeWindow(label="until", until_time=unsafe_time)

    # Unsafe in the middle only — rare, treat as "until first unsafe"
    unsafe_time = hourly_during_darkness[first_unsafe_idx][0]
    return DewSafeWindow(label="until", until_time=unsafe_time)
