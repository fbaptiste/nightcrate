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
  planner_min_visibility_hours: number;
  planner_max_magnitude: number;
  planner_min_size_arcmin: number;
  planner_frames_well_min_pct: number;
  planner_frames_well_max_pct: number;
  planner_moon_sep_deg: number;
  thumbnail_cache_max_mb: number;
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
