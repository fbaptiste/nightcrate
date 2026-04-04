import { apiFetch } from "./client";

export interface RequestRecord {
  timestamp: string;
  method: string;
  path: string;
  query: string;
  status_code: number;
  duration_ms: number;
}

export interface ActivityGroup {
  activity: string;
  requests: RequestRecord[];
  total_duration_ms: number;
}

export interface ActivityResponse {
  groups: ActivityGroup[];
}

export function fetchActivity(): Promise<ActivityResponse> {
  return apiFetch<ActivityResponse>("/diagnostics/activity");
}

export function clearActivity(): Promise<void> {
  return apiFetch("/diagnostics/activity", { method: "DELETE" });
}
