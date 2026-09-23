import { apiFetch } from "./client";

export interface DewSafeWindow {
  label: "all_night" | "until" | "after" | "none";
  until_time: string | null;
  after_time: string | null;
}

export interface MoonPolylinePoint {
  time_utc: string;
  altitude_deg: number;
}

/** How a factor enters the score; drives grouping and colour in the UI. */
export type FactorRole = "gate" | "yield" | "quality" | "modifier";

/** Machine-readable advisories. Display text lives in the UI, not the API. */
export type WeatherFlag =
  | "no_darkness"
  | "precipitation"
  | "wind_gate"
  | "overcast"
  | "high_cloud_only"
  | "layers_unavailable"
  | "total_estimated"
  | "dew_risk";

export interface WeatherFactor {
  key: string;
  role: FactorRole;
  /** 0-100, always higher-is-better (cloud shows clear-sky %, precip shows dry %). */
  value: number | null;
  /** Gate/yield/modifier: the multiplier applied. Quality: the term's weight. */
  effect: number;
  /** False when ignored in this mode (moon under narrowband) or input absent. */
  applied: boolean;
}

export type QualityLabel = "Excellent" | "Good" | "Marginal" | "Poor" | "Unusable";

export interface HourlyWeather {
  time: string;
  temperature_c: number;
  dew_point_c: number;
  humidity_pct: number;
  cloud_cover_pct: number;
  cloud_cover_low_pct: number;
  cloud_cover_mid_pct: number;
  cloud_cover_high_pct: number;
  wind_speed_kmh: number;
  wind_direction_deg: number;
  wind_gusts_kmh: number;
  visibility_m: number | null;
  precipitation_mm: number | null;
  precipitation_probability_pct: number | null;
  pwv_mm: number | null;
  aod: number | null;
  dew_risk: "low" | "moderate" | "high" | "critical";
  imaging_quality: number;
  imaging_quality_label: QualityLabel;
  /** Fraction of the hour expected to yield keepable frames, 0-1. */
  availability: number;
  /** Expected quality of those frames, 0-100. */
  quality: number;
  factors: WeatherFactor[];
  flags: WeatherFlag[];
  /** Score range across the forecast models. Null when fewer than two cover it. */
  score_min: number | null;
  score_max: number | null;
  /** True when the models disagree enough to land in different quality labels. */
  forecast_uncertain: boolean;
  moon_altitude_deg: number | null;
  moon_illumination_pct: number | null;
  darkness_category: string | null;
}

export interface DailySummary {
  date: string;
  imaging_quality: number;
  imaging_quality_label: QualityLabel;
  availability: number;
  quality: number;
  /** Equivalent hours of perfect data across the night. */
  expected_useful_hours: number;
  factors: WeatherFactor[];
  flags: WeatherFlag[];
  /** Score range across the forecast models. Null when fewer than two cover it. */
  score_min: number | null;
  score_max: number | null;
  /** True when the models disagree enough to land in different quality labels. */
  forecast_uncertain: boolean;
  sunset: string | null;
  sunrise: string | null;
  astro_dark_start: string | null;
  astro_dark_end: string | null;
  darkness_hours: number;
  moonless_dark_hours: number;
  moon_illumination_pct: number;
  moon_phase_name: string;
  dew_safe_window: DewSafeWindow;
  no_imaging_window: boolean;
  deepest_darkness_reached: "astro" | "nautical" | "civil" | "none";
  temp_min_c: number;
  temp_max_c: number;
  max_precipitation_probability_pct: number;
  avg_cloud_cover_pct: number;
  avg_cloud_low_pct: number;
  avg_cloud_mid_pct: number;
  avg_cloud_high_pct: number;
}

export interface ForecastResponse {
  location_id: number;
  location_name: string;
  latitude: number;
  longitude: number;
  timezone: string;
  geo_timezone: string | null;
  moon_included: boolean;
  days: DailySummary[];
}

export interface TwilightTimes {
  civil_end: string | null;
  nautical_end: string | null;
  astro_start: string | null;
  astro_end: string | null;
  nautical_start: string | null;
  civil_start: string | null;
}

export interface HourlyDetailResponse {
  date: string;
  location_id: number;
  location_name: string;
  timezone: string;
  geo_timezone: string | null;
  sunset: string | null;
  sunrise: string | null;
  twilight: TwilightTimes;
  moon_polyline: MoonPolylinePoint[];
  hours: HourlyWeather[];
}

export interface Methodology {
  text: string;
}

export const fetchForecast = (locationId: number, includeMoon = true) =>
  apiFetch<ForecastResponse>(
    `/weather/forecast?location_id=${locationId}&include_moon=${includeMoon}`
  );

export const fetchHourlyDetail = (locationId: number, date: string, includeMoon = true) =>
  apiFetch<HourlyDetailResponse>(
    `/weather/hourly?location_id=${locationId}&date=${date}&include_moon=${includeMoon}`
  );

export const fetchMethodology = () =>
  apiFetch<Methodology>("/weather/methodology");

export interface WeatherCacheStats {
  rows: number;
  bytes: number;
}

export const fetchWeatherCacheStats = () =>
  apiFetch<WeatherCacheStats>("/weather/cache/stats");

export const clearWeatherCache = () =>
  apiFetch<{ ok: boolean; deleted: number }>("/weather/cache", { method: "DELETE" });
