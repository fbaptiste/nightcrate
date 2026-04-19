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
