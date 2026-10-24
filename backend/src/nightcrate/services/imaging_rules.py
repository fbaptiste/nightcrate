"""Typed per-location rules used by the imaging verdict evaluator."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SessionStyle = Literal["all_night", "short_session"]
Darkness = Literal["astronomical", "nautical", "civil"]
RainPolicy = Literal["night_off", "hours_lost"]
RainForecasts = Literal["main", "any_model"]
CloudModel = Literal["ecmwf_ifs025", "gfs_seamless", "icon_seamless"]
CloudCombination = Literal["majority", "uncertain"]
PresetKey = Literal["left_out_all_night", "attended_session", "dome"]

CLOUD_MODEL_ORDER: tuple[CloudModel, ...] = (
    "ecmwf_ifs025",
    "gfs_seamless",
    "icon_seamless",
)


class ImagingRules(BaseModel):
    """A location's complete, metric imaging-decision rule set."""

    model_config = ConfigDict(extra="forbid")

    session_style: SessionStyle
    min_clear_fraction_pct: Annotated[float, Field(ge=1, le=100)]
    min_clear_hours: Annotated[float, Field(ge=0)]
    max_cloudy_gap_hours: Annotated[float, Field(gt=0)] | None
    short_session_hours: Annotated[float, Field(gt=0, le=24)]
    darkness: Darkness
    cloud_max_pct: Annotated[float, Field(ge=0, le=100)]
    cloud_use_ecmwf: bool
    cloud_use_gfs: bool
    cloud_use_icon: bool
    cloud_preferred_model: CloudModel
    cloud_combination: CloudCombination
    gear_out_before_sunset_min: Annotated[int, Field(ge=0, le=240)]
    gear_out_after_sunrise_min: Annotated[int, Field(ge=0, le=240)]
    rain_max_probability_pct: Annotated[float, Field(ge=0, le=100)]
    rain_amount_threshold_mm: Annotated[float, Field(ge=0)]
    rain_forecasts: RainForecasts
    rain_policy: RainPolicy
    wind_counted: bool
    wind_max_kmh: Annotated[float, Field(gt=0)]
    gust_max_kmh: Annotated[float, Field(gt=0)]
    dew_counted: bool
    dew_min_spread_c: Annotated[float, Field(ge=0)]
    moon_must_be_down: bool

    @model_validator(mode="after")
    def validate_cloud_models(self) -> ImagingRules:
        selected = selected_cloud_models(self)
        if not selected:
            raise ValueError("Choose at least one cloud forecast")
        if self.cloud_preferred_model not in selected:
            raise ValueError("The preferred cloud forecast must be one of the ticked forecasts")
        return self


def selected_cloud_models(rules: ImagingRules) -> tuple[CloudModel, ...]:
    """Return the selected cloud models in the stable display/tie-break order."""
    enabled = {
        "ecmwf_ifs025": rules.cloud_use_ecmwf,
        "gfs_seamless": rules.cloud_use_gfs,
        "icon_seamless": rules.cloud_use_icon,
    }
    return tuple(model for model in CLOUD_MODEL_ORDER if enabled[model])


def _preset(
    *,
    session_style: SessionStyle,
    rain_max_probability_pct: float,
    rain_forecasts: RainForecasts,
    rain_policy: RainPolicy,
    wind_counted: bool,
) -> ImagingRules:
    return ImagingRules(
        session_style=session_style,
        min_clear_fraction_pct=50,
        min_clear_hours=2.0,
        max_cloudy_gap_hours=None,
        short_session_hours=2.0,
        darkness="astronomical",
        cloud_max_pct=20,
        cloud_use_ecmwf=True,
        cloud_use_gfs=True,
        cloud_use_icon=True,
        cloud_preferred_model="ecmwf_ifs025",
        cloud_combination="majority",
        gear_out_before_sunset_min=30,
        gear_out_after_sunrise_min=30,
        rain_max_probability_pct=rain_max_probability_pct,
        rain_amount_threshold_mm=0,
        rain_forecasts=rain_forecasts,
        rain_policy=rain_policy,
        wind_counted=wind_counted,
        wind_max_kmh=30,
        gust_max_kmh=45,
        dew_counted=False,
        dew_min_spread_c=3.0,
        moon_must_be_down=False,
    )


PRESETS: dict[PresetKey, tuple[str, ImagingRules]] = {
    "left_out_all_night": (
        "Left out all night",
        _preset(
            session_style="all_night",
            rain_max_probability_pct=10,
            rain_forecasts="any_model",
            rain_policy="night_off",
            wind_counted=True,
        ),
    ),
    "attended_session": (
        "Attended session",
        _preset(
            session_style="short_session",
            rain_max_probability_pct=20,
            rain_forecasts="main",
            rain_policy="hours_lost",
            wind_counted=True,
        ),
    ),
    "dome": (
        "Dome / roll-off",
        _preset(
            session_style="all_night",
            rain_max_probability_pct=20,
            rain_forecasts="main",
            rain_policy="hours_lost",
            wind_counted=False,
        ),
    ),
}

DEFAULT_PRESET: PresetKey = "attended_session"
