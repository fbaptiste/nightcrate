"""Pure construction of complete evaluator inputs from UTC forecast series."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from nightcrate.services.imaging_types import (
    HourInput,
    ModelHour,
)
from nightcrate.services.weather import (
    CLOUD_SPREAD_MODELS,
    CloudModelData,
    HourlyWeather,
)

_HOUR = timedelta(hours=1)


def _floor_hour(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _ceil_hour(value: datetime) -> datetime:
    floored = _floor_hour(value)
    return floored if value.astimezone(UTC) == floored else floored + _HOUR


def build_hours(
    hourly: list[HourlyWeather],
    cloud_models: CloudModelData | None,
    moon_altitudes: dict[datetime, float | None],
    start_utc: datetime,
    end_utc: datetime,
    *,
    expected: Mapping[str, datetime],
) -> list[HourInput]:
    """Build revised evaluator inputs with declared per-field coverage."""
    rows = {row.time_utc: row for row in hourly}
    result: list[HourInput] = []
    current = _floor_hour(start_utc)
    end = _ceil_hour(end_utc)
    model_names = ("best_match", *CLOUD_SPREAD_MODELS)
    while current < end:
        instant = rows.get(current)
        preceding = rows.get(current + _HOUR)
        models: dict[str, ModelHour] = {}
        for model in model_names:
            coverage_end = expected[model].astimezone(UTC)
            if model == "best_match":
                total = instant.cloud_cover_pct if instant is not None else None
                layers = (
                    instant.cloud_cover_low_pct if instant is not None else None,
                    instant.cloud_cover_mid_pct if instant is not None else None,
                    instant.cloud_cover_high_pct if instant is not None else None,
                )
                amount = preceding.precipitation_mm if preceding is not None else None
            else:
                series = cloud_models.models.get(model) if cloud_models is not None else None
                total = series.cloud_total_pct.get(current) if series is not None else None
                layers = (
                    series.cloud_low_pct.get(current) if series is not None else None,
                    series.cloud_mid_pct.get(current) if series is not None else None,
                    series.cloud_high_pct.get(current) if series is not None else None,
                )
                amount = (
                    series.precipitation_mm.get(current + _HOUR) if series is not None else None
                )
            models[model] = ModelHour(
                cloud_total_pct=total,
                cloud_layers_pct=layers,
                precip_mm=amount,
                cloud_expected=current <= coverage_end,
                amount_expected=current + _HOUR <= coverage_end,
            )

        result.append(
            HourInput(
                start_utc=current,
                models=models,
                precip_probability_pct=(
                    preceding.precipitation_probability_pct if preceding is not None else None
                ),
                precip_mm=preceding.precipitation_mm if preceding is not None else None,
                wind_kmh=instant.wind_speed_kmh if instant is not None else None,
                gust_kmh=preceding.wind_gusts_kmh if preceding is not None else None,
                temperature_c=instant.temperature_c if instant is not None else None,
                dew_point_c=instant.dew_point_c if instant is not None else None,
                moon_altitude_deg=moon_altitudes.get(current),
            )
        )
        current += _HOUR
    return result
