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
  sky_clarity: number;
  transparency_score: number;
  seeing_score: number;
  wind_calm: number;
  dew_risk: "low" | "moderate" | "high" | "critical";
  imaging_quality: number;
  imaging_quality_label: string;
  moon_score: number;
  moon_altitude_deg: number | null;
  moon_illumination_pct: number | null;
  darkness_category: string | null;
}

export interface DailySummary {
  date: string;
  imaging_quality: number;
  imaging_quality_label: string;
  sky_clarity: number;
  transparency_score: number;
  seeing_score: number;
  wind_calm: number;
  moon_score: number;
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
