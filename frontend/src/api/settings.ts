import { apiFetch } from "./client";

export type Theme = "light" | "dark" | "browser";
export type WeatherUnits = "metric" | "imperial";

export interface BrowserFavorite {
  name: string;
  path: string;
}

export interface Settings {
  theme: Theme;
  gpu_acceleration: boolean;
  max_worker_cores: number | null;
  last_browse_path: string | null;
  browser_favorites: BrowserFavorite[];
  aberration_cache_ttl_days: number;
  weather_cache_ttl_hours: number;
  weather_moon_penalty: boolean;
  weather_units: WeatherUnits;
  calculators_clock_order: string[];
  nav_order: string[];
  planner_min_visibility_hours: number;
  planner_max_magnitude: number;
  planner_min_size_arcmin: number;
  planner_frames_well_min_pct: number;
  planner_frames_well_max_pct: number;
  planner_moon_sep_deg: number;
  thumbnail_cache_max_mb: number;
  // ─── Target Planner scoring (v0.21.0) ───────────────────────
  scoring_weight_observability: number;
  scoring_weight_meridian: number;
  scoring_weight_moon: number;
  scoring_weight_frame_fit: number;
  scoring_moon_sensitivity_ha: number;
  scoring_moon_sensitivity_sii: number;
  scoring_moon_sensitivity_oiii: number;
  scoring_moon_sensitivity_l: number;
  scoring_moon_sensitivity_r: number;
  scoring_moon_sensitivity_g: number;
  scoring_moon_sensitivity_b: number;
  scoring_moon_min_sep_ha: number;
  scoring_moon_min_sep_sii: number;
  scoring_moon_min_sep_oiii: number;
  scoring_moon_min_sep_l: number;
  scoring_moon_min_sep_r: number;
  scoring_moon_min_sep_g: number;
  scoring_moon_min_sep_b: number;
  scoring_cluster_moon_modifier: number;
  scoring_observability_min_altitude_deg: number;
  scoring_frame_fit_ideal_coverage_pct: number;
  scoring_frame_fit_spread: number;
  scoring_threshold_excellent: number;
  scoring_threshold_good: number;
  scoring_threshold_fair: number;
  scoring_gate_min_obs_hours: number;
  scoring_gate_max_coverage_pct: number | null;
  phd2_show_polar_drift: boolean;
  phd2_panel_heights: Record<string, number>;
  phd2_help_expanded: Record<string, boolean>;
  phd2_recurrence_mode: "boundary_skip" | "verbatim";
}

export function fetchSettings(): Promise<Settings> {
  return apiFetch<Settings>("/settings");
}

export function saveSettings(settings: Settings): Promise<Settings> {
  return apiFetch<Settings>("/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}
