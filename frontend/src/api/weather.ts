import { apiFetch } from "./client";
import type { WeatherUnits } from "./settings";

export type { WeatherUnits };

export type Verdict = "go" | "uncertain" | "no" | "not_enough_data" | "night_over";
export type CheckState = "pass" | "fail" | "unknown" | "not_counted";
export type HourState = "clear" | "not_clear" | "unknown" | "outside";
export type SessionStyle = "all_night" | "short_session";
export type Darkness = "astronomical" | "nautical" | "civil";
export type RainPolicy = "night_off" | "hours_lost";
export type RainForecasts = "main" | "any_model";
export type CloudModel = "ecmwf_ifs025" | "gfs_seamless" | "icon_seamless";
export type CloudCombination = "majority" | "uncertain";
export type ModelStatus = "go" | "no" | "unresolved" | "not_expected";

export interface ImagingRules {
  session_style: SessionStyle;
  min_clear_fraction_pct: number;
  min_clear_hours: number;
  max_cloudy_gap_hours: number | null;
  short_session_hours: number;
  darkness: Darkness;
  cloud_max_pct: number;
  cloud_use_ecmwf: boolean;
  cloud_use_gfs: boolean;
  cloud_use_icon: boolean;
  cloud_preferred_model: CloudModel;
  cloud_combination: CloudCombination;
  gear_out_before_sunset_min: number;
  gear_out_after_sunrise_min: number;
  rain_max_probability_pct: number;
  rain_amount_threshold_mm: number;
  rain_forecasts: RainForecasts;
  rain_policy: RainPolicy;
  wind_counted: boolean;
  wind_max_kmh: number;
  gust_max_kmh: number;
  dew_counted: boolean;
  dew_min_spread_c: number;
  moon_must_be_down: boolean;
}

export interface NightControls {
  gear_out: string | null;
  gear_in: string | null;
  imaging_from: string | null;
  imaging_until: string | null;
}

export interface ForecastRequest {
  location_id: number;
  rules?: ImagingRules;
  night_controls?: Record<string, NightControls>;
}

export interface Reason {
  code: string;
  start: string | null;
  end: string | null;
  start_utc: string | null;
  end_utc: string | null;
  value: number | null;
  limit: number | null;
  requirement: string | null;
  models: Record<string, ModelStatus> | null;
  bound: "at_most" | "at_least" | null;
  model: string | null;
  missing_hours: number | null;
}

export interface Interval {
  start: string;
  end: string;
  start_utc: string;
  end_utc: string;
}

export interface Coverage {
  model: string;
  status: ModelStatus | "not_used";
  expected_until: string | null;
  expected_until_utc: string | null;
}

export interface NightExtremes {
  max_precip_probability_pct: number | null;
  max_precip_probability_at: string | null;
  max_precip_probability_at_utc: string | null;
  precip_mm_total: number | null;
  precip_missing_hours: number;
  precip_sum_start: string | null;
  precip_sum_end: string | null;
  precip_sum_start_utc: string | null;
  precip_sum_end_utc: string | null;
  max_gust_kmh: number | null;
  max_gust_at: string | null;
  max_gust_at_utc: string | null;
  min_dew_spread_c: number | null;
  min_dew_spread_at: string | null;
  min_dew_spread_at_utc: string | null;
}

export interface ExpectedFields {
  cloud: boolean;
  amount: boolean;
}

export interface Hour {
  time: string;
  start_utc: string;
  elapsed: boolean;
  excluded: boolean;
  dark_minutes: number;
  exposure_minutes: number;
  darkness_category: "day" | "civil" | "nautical" | "astro";
  state: HourState;
  session_state: HourState;
  model_states: Record<string, HourState>;
  disagrees: boolean;
  checks: Record<string, CheckState>;
  /** Every rule judged for this hour regardless of darkness (display only). */
  conditions: Record<string, CheckState>;
  cloud_total_pct: number | null;
  cloud_low_pct: number | null;
  cloud_mid_pct: number | null;
  cloud_high_pct: number | null;
  cloud_pct: Record<string, number | null>;
  expected: Record<string, ExpectedFields>;
  precip_probability_pct: number | null;
  precip_mm: number | null;
  model_precip_mm: Record<string, number | null>;
  gust_kmh: number | null;
  wind_kmh: number | null;
  temperature_c: number | null;
  dew_point_c: number | null;
  dew_spread_c: number | null;
  visibility_m: number | null;
  moon_altitude_deg: number | null;
  seeing: "good" | "fair" | "poor" | null;
  transparency: "good" | "fair" | "poor" | null;
  transparency_tier: "primary" | "fallback" | "degraded" | null;
}

export interface Night {
  date: string;
  verdict: Verdict;
  reason: Reason;
  other_reasons: Reason[];
  advisory: Reason | null;
  clear_hours: number;
  dark_hours: number;
  unknown_hours: number;
  clear_pct: number | null;
  longest_gap_start: string | null;
  longest_gap_end: string | null;
  longest_gap_start_utc: string | null;
  longest_gap_end_utc: string | null;
  window_start: string | null;
  window_end: string | null;
  window_start_utc: string | null;
  window_end_utc: string | null;
  gear_out_start: string;
  gear_out_end: string;
  gear_out_start_utc: string;
  gear_out_end_utc: string;
  evaluated_from: string | null;
  evaluated_end: string | null;
  evaluated_from_utc: string | null;
  evaluated_end_utc: string | null;
  dark_intervals: Interval[];
  /** Sun below −6° / −12° / −18°, in display time. */
  darkness_intervals: Record<"civil" | "nautical" | "astronomical", Interval[]>;
  exposure: Interval | null;
  imaging: Interval | null;
  controls: NightControls;
  model_statuses: Record<string, ModelStatus>;
  primary_model: string;
  cloud_combination: CloudCombination | "single";
  differing_hours: number;
  compared_hours: number;
  cloud_models: CloudModel[];
  cloud_models_used: CloudModel[];
  default_cloud_used: boolean;
  coverage: Coverage[];
  single_model: boolean;
  cloud_source: "ecmwf" | "best_match_fallback";
  layer_model: string;
  cloud_coarse_from: string | null;
  cloud_coarse_from_utc: string | null;
  stale_minutes: number | null;
  requirements: Record<string, CheckState | "info">;
  extremes: NightExtremes;
  sunset: string | null;
  sunset_utc: string | null;
  sunrise: string | null;
  sunrise_utc: string | null;
  moon_illumination_pct: number;
  moon_phase_name: string;
  moonrise: string | null;
  moonrise_utc: string | null;
  moonset: string | null;
  moonset_utc: string | null;
  hours: Hour[];
}

export interface ForecastResponse {
  location_id: number;
  location_name: string;
  timezone: string;
  geo_timezone: string | null;
  rules: ImagingRules;
  rules_saved: boolean;
  fetched_at: string;
  evaluated_at: string;
  stale_sources: { forecast: number | null; cloud_models: number | null };
  run_age_minutes: Record<string, number | null>;
  ignored_controls: string[];
  nights: Night[];
}

export interface ImagingRulesResponse {
  location_id: number;
  saved: boolean;
  rules: ImagingRules;
}

export interface ImagingRulesPreset {
  key: "left_out_all_night" | "attended_session" | "dome";
  label: string;
  rules: ImagingRules;
}

export interface Methodology {
  summary: string;
  details: string;
}

export const fetchForecast = (request: ForecastRequest) =>
  apiFetch<ForecastResponse>("/weather/forecast", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

export const fetchImagingRules = (locationId: number) =>
  apiFetch<ImagingRulesResponse>(`/locations/${locationId}/imaging-rules`);

export const saveImagingRules = (locationId: number, rules: ImagingRules) =>
  apiFetch<ImagingRulesResponse>(`/locations/${locationId}/imaging-rules`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rules),
  });

export const fetchPresets = () =>
  apiFetch<ImagingRulesPreset[]>("/imaging-rules/presets");

export function forecastQueryOptions(
  locationId: number,
  draftRules?: ImagingRules,
  nightControls?: Record<string, NightControls>,
) {
  return {
    queryKey: [
      "weather-forecast",
      locationId,
      draftRules ?? "saved",
      nightControls ?? {},
    ] as const,
    queryFn: () =>
      fetchForecast({
        location_id: locationId,
        ...(draftRules ? { rules: draftRules } : {}),
        ...(nightControls && Object.keys(nightControls).length > 0
          ? { night_controls: nightControls }
          : {}),
      }),
    refetchOnWindowFocus: true,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  };
}

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
