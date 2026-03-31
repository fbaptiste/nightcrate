import { apiFetch } from "./client";

export type Theme = "light" | "dark" | "browser";

export interface Settings {
  theme: Theme;
  gpu_acceleration: boolean;
  max_worker_cores: number | null;
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
