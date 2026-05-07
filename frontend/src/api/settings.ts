import { apiFetch } from "./client";

export type Theme = "light" | "dark" | "browser";
export type WeatherUnits = "metric" | "imperial";
export type PlannerTab = "tonight" | "anytime" | "wishlist";
export type FilterLine = "Ha" | "SII" | "OIII" | "L" | "R" | "G" | "B";
export type SortDir = "asc" | "desc";

export interface BrowserFavorite {
  name: string;
  path: string;
}

export interface PlannerSortEntry {
  field: string;
  dir: SortDir;
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
  astap_executable_path: string | null;
  // ─── Target Planner UI state (v0.34.0) ──────────────────────
  planner_selected_location_id: number | null;
  planner_selected_horizon_id: number | null;
  planner_selected_rig_id: number | null;
  planner_active_tab: PlannerTab;
  planner_sort_by: PlannerSortEntry[];
  planner_filter_intent: FilterLine[];
  planner_type_filter: string[];
  planner_catalog_filter: string[];
  planner_constellation_filter: string[];
  planner_detail_id: number | null;
  planner_min_hours: number | null;
  planner_max_mag: number | null;
  planner_min_size: number | null;
  planner_coverage_range: [number, number] | null;
  planner_calendar_location_id: number | null;
  planner_calendar_horizon_id: number | null;
  planner_calendar_rig_id: number | null;
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
