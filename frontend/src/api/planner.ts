/**
 * Target Planner API client (v0.16.0).
 *
 * Thin typed wrappers around /api/planner/*. Thumbnail URLs are
 * composed client-side so the DataGrid can drop them straight into
 * <img src>.
 */
import { apiFetch, getActivity } from "./client";

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
  /** Meridian crossing — always populated (computed analytically from
   *  sidereal geometry). */
  transit_time_utc: string;
  altitude_at_transit_deg: number;
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
  /** Monotonic counter — appended to thumbnail URLs as ``&_g=N``.
   *  Increments on every cache clear so the browser HTTP cache can't
   *  serve stale images when the backend cache is wiped. */
  generation: number;
}

export interface NearbyDsoItem {
  id: number;
  primary_designation: string;
  ra_deg: number;
  dec_deg: number;
  maj_axis_arcmin: number | null;
  min_axis_arcmin: number | null;
  obj_type: string;
  type_group: string | null;
}

export interface NearbyDsosResponse {
  items: NearbyDsoItem[];
}

export function fetchNearbyDsos(params: {
  raCenterDeg: number;
  decCenterDeg: number;
  extentDeg: number;
  excludeId?: number | null;
  limit?: number;
}): Promise<NearbyDsosResponse> {
  const qs = new URLSearchParams({
    ra_center_deg: params.raCenterDeg.toFixed(6),
    dec_center_deg: params.decCenterDeg.toFixed(6),
    extent_deg: params.extentDeg.toFixed(6),
  });
  if (params.excludeId != null) qs.set("exclude_id", String(params.excludeId));
  if (params.limit != null) qs.set("limit", String(params.limit));
  return apiFetch<NearbyDsosResponse>(`/planner/dsos/in-region?${qs.toString()}`);
}

export const fetchThumbnailCacheStats = () =>
  apiFetch<ThumbnailCacheStats>("/planner/thumbnails/cache/stats");

export const clearThumbnailCache = () =>
  apiFetch<{ deleted_files: number }>("/planner/thumbnails/cache/clear", {
    method: "POST",
  });

export type ThumbnailVariant = "list" | "detail" | "rig_framed" | "fov_simulator";

export interface ThumbnailUrlOptions {
  /** Required for ``rig_framed`` + ``fov_simulator``; ignored otherwise. */
  fovMajorDeg?: number;
  fovMinorDeg?: number;
  /** Panned sky centre — only honoured for ``fov_simulator``. When
   *  omitted the backend falls back to the DSO's native coordinates. */
  centerRaDeg?: number;
  centerDecDeg?: number;
  /** Cache-generation counter — appended as ``&_g=N``. Bumps on cache
   *  clear so stale browser-cached entries are never reused. Sourced
   *  from ``useThumbnailCacheStore``. */
  generation?: number;
  /** Long-poll window in milliseconds. On a cache miss the backend
   *  holds the request open up to this long waiting for the CDS fetch
   *  to complete, then serves the real image in the same round trip.
   *  ``0`` (default) restores the old behaviour — immediate placeholder,
   *  client polls with backoff. Worth setting for the simulator
   *  (2–4 s) so the first visible image lands at CDS latency rather
   *  than CDS + next-poll-cadence. Backend caps at 10 s. */
  waitMs?: number;
}

/** Build the <img src> URL for a thumbnail — the backend handles cache lookup.
 *
 *  Image requests bypass the apiFetch wrapper, so we fold the current
 *  activity label into the query string directly (matches
 *  ``api/images.ts:imageUrl`` — required for the Activity Console).
 *  ``fovMajorDeg`` / ``fovMinorDeg`` are required for the rig-dependent
 *  variants; caller is trusted to pass them. */
export function thumbnailUrl(
  dsoId: number,
  variant: ThumbnailVariant = "list",
  opts: ThumbnailUrlOptions = {},
): string {
  const q = new URLSearchParams({ variant });
  if (opts.fovMajorDeg != null) q.set("fov_major_deg", opts.fovMajorDeg.toFixed(4));
  if (opts.fovMinorDeg != null) q.set("fov_minor_deg", opts.fovMinorDeg.toFixed(4));
  if (opts.centerRaDeg != null) q.set("center_ra_deg", opts.centerRaDeg.toFixed(4));
  if (opts.centerDecDeg != null) q.set("center_dec_deg", opts.centerDecDeg.toFixed(4));
  if (opts.generation != null) q.set("_g", String(opts.generation));
  if (opts.waitMs != null && opts.waitMs > 0) q.set("wait_ms", String(opts.waitMs));
  const activity = getActivity();
  if (activity) q.set("_activity", activity);
  return `/api/planner/thumbnails/${dsoId}?${q.toString()}`;
}
