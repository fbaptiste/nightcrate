import { apiFetch } from "./client";
import type { ProjectStatus, Stage } from "./projects";
import type { Verdict } from "./weather";

export interface StageCounts {
  not_started: number;
  capturing: number;
  ready_to_process: number;
  complete: number;
  paused: number;
  abandoned: number;
}

export interface HomeIntegrationLine {
  label: string;
  minutes: number;
  not_recorded: boolean;
}

export interface RecentProject {
  project_id: number;
  name: string;
  status: ProjectStatus;
  stage: Stage;
  target_label: string | null;
  constellation: string | null;
  thumbnail_version: string;
  has_image: boolean;
  total_minutes: number;
  lines: HomeIntegrationLine[];
  last_date: string;
  nights: number;
}

export interface LatestPicture {
  project_id: number;
  project_name: string;
  image_id: number;
  added: string;
  status: ProjectStatus;
  target_label: string | null;
  constellation: string | null;
}

export interface MonthSummary {
  month: string;
  minutes: number;
}

export interface BestNight {
  date: string;
  minutes: number;
  project_id: number;
  project_name: string;
  other_projects: number;
}

export interface YearSummary {
  since: string;
  minutes: number;
  nights: number;
  new_pictures: number;
  best_night: BestNight | null;
  months: MonthSummary[];
}

export interface RigSummary {
  rig_id: number;
  name: string;
  minutes: number;
  nights: number;
  last_used: string | null;
  active_projects: number;
}

export interface LocationSummary {
  location_id: number;
  name: string;
  is_default: boolean;
  minutes: number;
  nights: number;
  last_used: string | null;
  active_projects: number;
}

export interface ForecastLocation {
  location_id: number;
  name: string;
  note: "default" | "used" | null;
  active_projects: number;
}

export interface HomeSummary {
  today: string;
  stages: StageCounts;
  total_projects: number;
  recent: RecentProject[];
  latest_picture: LatestPicture | null;
  year: YearSummary;
  rigs: RigSummary[];
  locations: LocationSummary[];
  forecast_locations: ForecastLocation[];
  workspace_key: string;
}

export interface FortnightNight {
  date: string;
  verdict: Verdict;
  moonless_dark_hours: number;
}

export interface FortnightResponse {
  location_id: number;
  evaluated_at: string;
  stale_since: string | null;
  nights: FortnightNight[];
}

export function fetchHome(): Promise<HomeSummary> {
  return apiFetch<HomeSummary>("/home");
}

export function fetchFortnight(locationId: number): Promise<FortnightResponse> {
  return apiFetch<FortnightResponse>(`/weather/fortnight?location_id=${locationId}`);
}
