/**
 * Target Planner API client (v0.16.0).
 *
 * Thin typed wrappers around /api/planner/*. Thumbnail URLs are
 * composed client-side so the DataGrid can drop them straight into
 * <img src>.
 */
import { apiFetch } from "./client";

export interface PlannerLocationSummary {
  id: number;
  name: string;
  has_custom_horizon: boolean;
}

export interface PlannerRigSummary {
  id: number;
  name: string;
  fov_major_deg: number;
  fov_minor_deg: number;
}

export interface PlannerDarkWindow {
  start_utc: string;
  end_utc: string;
  hours: number;
}

export interface PlannerTargetItem {
  dso_id: number;
  primary_designation: string;
  common_name: string | null;
  obj_type: string;
  type_group: string | null;
  ra_deg: number | null;
  dec_deg: number | null;
  constellation: string | null;
  maj_axis_arcmin: number | null;
  min_axis_arcmin: number | null;
  mag_v: number | null;
  distance_pc: number | null;
  hours_visible: number;
  max_altitude_deg: number;
  peak_time_utc: string;
  transit_time_utc: string | null;
  altitude_at_transit_deg: number | null;
  min_moon_separation_deg: number | null;
  coverage_pct: number | null;
}

export interface PlannerTargetsResponse {
  location: PlannerLocationSummary;
  rig: PlannerRigSummary | null;
  date: string;
  dark_window: PlannerDarkWindow | null;
  moon_phase_pct: number;
  total: number;
  offset: number;
  limit: number;
  items: PlannerTargetItem[];
}

export interface PlannerTargetsParams {
  location_id: number;
  rig_id?: number | null;
  date?: string | null;
  type_group?: string[];
  min_hours?: number | null;
  max_magnitude?: number | null;
  min_size_arcmin?: number | null;
  frames_well?: boolean;
  limit?: number;
  offset?: number;
  sort?: string;
  sort_dir?: "asc" | "desc";
}

export function fetchPlannerTargets(
  params: PlannerTargetsParams,
): Promise<PlannerTargetsResponse> {
  const qs = new URLSearchParams();
  qs.set("location_id", String(params.location_id));
  if (params.rig_id != null) qs.set("rig_id", String(params.rig_id));
  if (params.date) qs.set("date", params.date);
  if (params.type_group?.length) qs.set("type_group", params.type_group.join(","));
  if (params.min_hours != null) qs.set("min_hours", String(params.min_hours));
  if (params.max_magnitude != null) qs.set("max_magnitude", String(params.max_magnitude));
  if (params.min_size_arcmin != null) qs.set("min_size_arcmin", String(params.min_size_arcmin));
  if (params.frames_well) qs.set("frames_well", "true");
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.sort) qs.set("sort", params.sort);
  if (params.sort_dir) qs.set("sort_dir", params.sort_dir);
  return apiFetch<PlannerTargetsResponse>(`/planner/targets?${qs.toString()}`);
}

export interface TwilightBands {
  sunset_utc: string | null;
  civil_end_utc: string | null;
  nautical_end_utc: string | null;
  astro_start_utc: string | null;
  astro_end_utc: string | null;
  nautical_start_utc: string | null;
  civil_start_utc: string | null;
  sunrise_utc: string | null;
}

export interface SkyTrackResponse {
  dso_id: number;
  times_utc: string[];
  object_altitude_deg: number[];
  object_azimuth_deg: number[];
  moon_altitude_deg: number[];
  horizon_altitude_at_object_az: number[];
  twilight: TwilightBands;
  moon_phase_pct: number;
  peak_time_utc: string;
  peak_altitude_deg: number;
  transit_time_utc: string | null;
}

export function fetchSkyTrack(
  dsoId: number,
  locationId: number,
  date?: string,
): Promise<SkyTrackResponse> {
  const qs = new URLSearchParams({ location_id: String(locationId) });
  if (date) qs.set("date", date);
  return apiFetch<SkyTrackResponse>(
    `/planner/targets/${dsoId}/sky-track?${qs.toString()}`,
  );
}

export interface ThumbnailCacheStats {
  total_bytes: number;
  row_count: number;
  max_bytes: number;
}

export const fetchThumbnailCacheStats = () =>
  apiFetch<ThumbnailCacheStats>("/planner/thumbnails/cache/stats");

export const clearThumbnailCache = () =>
  apiFetch<{ deleted_files: number }>("/planner/thumbnails/cache/clear", {
    method: "POST",
  });

/** Build the <img src> URL for a thumbnail — the backend handles cache lookup. */
export function thumbnailUrl(dsoId: number, variant: "list" | "detail" = "list"): string {
  return `/api/planner/thumbnails/${dsoId}?variant=${variant}`;
}
