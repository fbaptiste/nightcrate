"""Pydantic response models for the weather API."""

from typing import Literal

from pydantic import BaseModel


class DewSafeWindowResponse(BaseModel):
    label: Literal["all_night", "until", "after", "none"]
    until_time: str | None = None
    after_time: str | None = None


class MoonPolylinePointResponse(BaseModel):
    time_utc: str
    altitude_deg: float


class HourlyWeatherResponse(BaseModel):
    time: str
    temperature_c: float
    dew_point_c: float
    humidity_pct: float
    cloud_cover_pct: float
    cloud_cover_low_pct: float
    cloud_cover_mid_pct: float
    cloud_cover_high_pct: float
    wind_speed_kmh: float
    wind_direction_deg: float
    wind_gusts_kmh: float
    visibility_m: float | None
    precipitation_mm: float | None
    precipitation_probability_pct: float | None
    pwv_mm: float | None
    aod: float | None
    sky_clarity: int
    transparency_score: int
    seeing_score: int
    wind_calm: int
    dew_risk: Literal["low", "moderate", "high", "critical"]
    imaging_quality: int
    imaging_quality_label: str
    moon_altitude_deg: float | None
    moon_illumination_pct: float | None
    darkness_category: str | None


class DailySummaryResponse(BaseModel):
    date: str
    imaging_quality: int
    imaging_quality_label: str
    sky_clarity: int
    transparency_score: int
    seeing_score: int
    wind_calm: int
    moon_score: int
    sunset: str | None  # HH:MM local — None for polar day
    sunrise: str | None  # HH:MM local — None for polar day
    astro_dark_start: str | None  # HH:MM local — None if astro dark not reached
    astro_dark_end: str | None  # HH:MM local — None if astro dark not reached
    darkness_hours: float
    moonless_dark_hours: float
    moon_illumination_pct: float
    moon_phase_name: str
    dew_safe_window: DewSafeWindowResponse
    no_imaging_window: bool
    deepest_darkness_reached: Literal["astro", "nautical", "civil", "none"]
    temp_min_c: float
    temp_max_c: float
    max_precipitation_probability_pct: float
    avg_cloud_cover_pct: float
    avg_cloud_low_pct: float
    avg_cloud_mid_pct: float
    avg_cloud_high_pct: float


class ForecastResponse(BaseModel):
    location_id: int
    location_name: str
    latitude: float
    longitude: float
    timezone: str
    moon_included: bool
    days: list[DailySummaryResponse]


class TwilightTimesResponse(BaseModel):
    """Precise twilight boundary times (HH:MM local). All optional for polar latitudes."""

    civil_end: str | None  # evening: sun crosses -6°
    nautical_end: str | None  # evening: sun crosses -12°
    astro_start: str | None  # evening: sun crosses -18° (darkness begins)
    astro_end: str | None  # morning: sun crosses -18° (darkness ends)
    nautical_start: str | None  # morning: sun crosses -12°
    civil_start: str | None  # morning: sun crosses -6°


class HourlyDetailResponse(BaseModel):
    date: str
    location_id: int
    location_name: str
    sunset: str | None
    sunrise: str | None
    twilight: TwilightTimesResponse
    moon_polyline: list[MoonPolylinePointResponse]
    hours: list[HourlyWeatherResponse]


class MethodologyResponse(BaseModel):
    text: str
