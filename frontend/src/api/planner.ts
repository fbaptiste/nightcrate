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
}

export interface PlannerHorizonSummary {
  id: number;
  name: string;
  type: "artificial" | "custom";
  flat_altitude_deg: number | null;
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

/** One of the seven atomic filter-line codes the planner's
 *  filter-intent multi-select emits (v0.21.0 scoring). */
export type FilterLine = "Ha" | "SII" | "OIII" | "L" | "R" | "G" | "B";

export const FILTER_LINES: FilterLine[] = ["Ha", "SII", "OIII", "L", "R", "G", "B"];

/** One row of a scored target's breakdown — one per quality dimension. */
export interface DimensionBreakdown {
  key: "observability" | "meridian" | "moon" | "frame_fit";
  label: string;
  /** 0-1 dimensional score. */
  score: number;
  weight: number;
  /** Multiplicative contribution (score ** weight) to the geometric mean. */
  contribution: number;
  /** Human-readable facts that drove the dimension's score. */
  inputs: string[];
}

/** Score breakdown attached to every scored target. When ``score_pct``
 *  is ``null`` (hard gate tripped), ``dimensions`` is empty and
 *  ``gate_failures`` explains why. */
export interface ScoreBreakdown {
  dimensions: DimensionBreakdown[];
  gate_failures: string[];
}

export type QualityLabel = "Excellent" | "Good" | "Fair" | "Poor";

export interface PlannerTargetItem {
  dso_id: number;
  primary_designation: string;
  common_name: string | null;
  obj_type: string;
  ra_deg: number | null;
  dec_deg: number | null;
  constellation: string | null;
  maj_axis_arcmin: number | null;
  min_axis_arcmin: number | null;
  mag_v: number | null;
  distance_pc: number | null;
  // Visibility fields are ``null`` in "anytime" mode
  // (``restrict_tonight=false``) and for DSOs that don't clear the
  // altitude floor during tonight's astro-dark window.
  hours_visible: number | null;
  max_altitude_deg: number | null;
  peak_time_utc: string | null;
  transit_time_utc: string | null;
  altitude_at_transit_deg: number | null;
  min_moon_separation_deg: number | null;
  coverage_pct: number | null;
  /** "up" / "rising" / "set" relative to when the request was served.
   *  ``null`` in Anytime mode and when the location has no
   *  coordinates. Static at fetch time — doesn't update as time
   *  passes on a long-running page. */
  now_status: "up" | "rising" | "set" | null;
  /** Wikipedia article link for the chip on the planner card. ``null``
   *  when the DSO has no Wikipedia ref (either Wikidata didn't match
   *  it or the entity has no English sitelink). Wikidata QIDs stay on
   *  the DSO-detail endpoint — this is the minimal list-payload carve-
   *  out for the one chip the card shows. */
  wikipedia_url: string | null;
  wikipedia_label: string | null;
  /** Full catalog cross-references (NGC, IC, Messier, Caldwell, PGC, …).
   *  Sorted primary-first, then alphabetically. Always includes the
   *  primary designation; alternates follow. */
  designations: PlannerDesignation[];
  /** 0-100 score (v0.21.0). ``null`` in Anytime mode or when the
   *  target tripped a hard gate — the breakdown's ``gate_failures``
   *  explains why in the latter case. */
  score_pct: number | null;
  quality_label: QualityLabel | null;
  score_breakdown: ScoreBreakdown | null;
}

export interface PlannerDesignation {
  catalog: string;
  identifier: string;
  display_form: string;
  is_primary: boolean;
}

export interface PlannerTargetsResponse {
  // Null in Anytime mode when the caller omits ``location_id``.
  location: PlannerLocationSummary | null;
  /** Echo of the horizon used to compute the snapshot. Null in
   *  Anytime mode (no location → no horizon either). */
  horizon: PlannerHorizonSummary | null;
  rig: PlannerRigSummary | null;
  date: string;
  dark_window: PlannerDarkWindow | null;
  moon_phase_pct: number;
  /** Standard phase name ("New Moon", "Waxing Crescent", …) or null
   *  when no date/location anchor is available. Feeds the moon-phase
   *  icon in the Tonight-mode header. */
  moon_phase_name: string | null;
  total: number;
  offset: number;
  limit: number;
  items: PlannerTargetItem[];
  /** Per-chip tallies that reflect the current filter state
   *  (faceted-search semantics). One dict per filter dimension;
   *  each chip's count reflects the state with its own dimension
   *  held out, so users can keep adding chips to a pill filter
   *  without the picker collapsing to the first selection. */
  raw_type_counts: Record<string, number>;
  catalog_counts: Record<string, number>;
  constellation_counts: Record<string, number>;
}

export interface PlannerTargetsParams {
  /** Required in Tonight mode; omit (``null``) in Anytime — the
   *  backend then skips visibility + location metadata entirely. */
  location_id: number | null;
  /** Horizon to compute visibility against. Defaults to the
   *  location's default horizon server-side. Ignored in Anytime. */
  horizon_id?: number | null;
  rig_id?: number | null;
  date?: string | null;
  /** Raw OpenNGC ``obj_type`` codes — multi-select OR. */
  type?: string[];
  /** Designation catalog codes — multi-select OR. */
  catalog?: string[];
  /** 3-letter IAU constellation codes — multi-select OR. */
  constellation?: string[];
  has_distance?: boolean | null;
  min_hours?: number | null;
  max_magnitude?: number | null;
  min_size_arcmin?: number | null;
  /** Lower/upper bounds for the FOV coverage range filter. Only
   *  meaningful with a rig selected. Leave undefined to skip the
   *  filter entirely. */
  coverage_min_pct?: number | null;
  coverage_max_pct?: number | null;
  /** Free-text search. Same semantics as the DSO catalog's ``q`` —
   *  designation prefix or common-name substring match. */
  q?: string | null;
  /** ``true`` (default) filters to DSOs visible during tonight's
   *  astro-dark window. ``false`` returns the full catalog with
   *  ``null`` visibility fields — turns the planner into a catalog
   *  browser. */
  restrict_tonight?: boolean;
  limit?: number;
  offset?: number;
  /** Serialized multi-sort string in ``field:dir,field:dir`` form.
   *  Build with ``serializeSort()`` from ``lib/plannerSortFields``.
   *  ``null`` lets the backend apply its mode-appropriate default. */
  sort?: string | null;
  /** Filter-line codes the user is capturing tonight (v0.21.0 scoring).
   *  Empty / undefined → moon dimension is neutral. Ignored in Anytime. */
  filter_intent?: FilterLine[];
}

export function fetchPlannerTargets(
  params: PlannerTargetsParams,
): Promise<PlannerTargetsResponse> {
  const qs = new URLSearchParams();
  if (params.location_id != null) qs.set("location_id", String(params.location_id));
  if (params.horizon_id != null) qs.set("horizon_id", String(params.horizon_id));
  if (params.rig_id != null) qs.set("rig_id", String(params.rig_id));
  if (params.date) qs.set("date", params.date);
  if (params.type?.length) qs.set("type", params.type.join(","));
  if (params.catalog?.length) qs.set("catalog", params.catalog.join(","));
  if (params.constellation?.length)
    qs.set("constellation", params.constellation.join(","));
  if (params.has_distance === true) qs.set("has_distance", "true");
  else if (params.has_distance === false) qs.set("has_distance", "false");
  if (params.min_hours != null) qs.set("min_hours", String(params.min_hours));
  if (params.max_magnitude != null) qs.set("max_magnitude", String(params.max_magnitude));
  if (params.min_size_arcmin != null) qs.set("min_size_arcmin", String(params.min_size_arcmin));
  if (params.coverage_min_pct != null)
    qs.set("coverage_min_pct", String(params.coverage_min_pct));
  if (params.coverage_max_pct != null)
    qs.set("coverage_max_pct", String(params.coverage_max_pct));
  if (params.q) qs.set("q", params.q);
  if (params.restrict_tonight === false) qs.set("restrict_tonight", "false");
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.sort) qs.set("sort", params.sort);
  if (params.filter_intent?.length)
    qs.set("filter_intent", params.filter_intent.join(","));
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
  moon_separation_deg: number[];
  horizon_altitude_at_object_az: number[];
  twilight: TwilightBands;
  moon_phase_pct: number;
  peak_time_utc: string;
  peak_altitude_deg: number;
  transit_time_utc: string | null;
}

export interface SingleTargetScoreResponse {
  dso_id: number;
  score_pct: number | null;
  quality_label: QualityLabel | null;
  score_breakdown: ScoreBreakdown | null;
}

export interface SingleTargetScoreParams {
  locationId: number;
  horizonId?: number | null;
  rigId?: number | null;
  filterIntent?: FilterLine[];
  date?: string | null;
}

/** Score one target against a panel-local preview context. Used by
 *  the Planner detail panel when rig/horizon/location differ from
 *  the list-page values. */
export function fetchSingleTargetScore(
  dsoId: number,
  params: SingleTargetScoreParams,
): Promise<SingleTargetScoreResponse> {
  const qs = new URLSearchParams({ location_id: String(params.locationId) });
  if (params.horizonId != null) qs.set("horizon_id", String(params.horizonId));
  if (params.rigId != null) qs.set("rig_id", String(params.rigId));
  if (params.filterIntent?.length)
    qs.set("filter_intent", params.filterIntent.join(","));
  if (params.date) qs.set("date", params.date);
  return apiFetch<SingleTargetScoreResponse>(
    `/planner/targets/${dsoId}/score?${qs.toString()}`,
  );
}

export function fetchSkyTrack(
  dsoId: number,
  locationId: number,
  horizonId?: number | null,
  date?: string,
): Promise<SkyTrackResponse> {
  const qs = new URLSearchParams({ location_id: String(locationId) });
  if (horizonId != null) qs.set("horizon_id", String(horizonId));
  if (date) qs.set("date", date);
  return apiFetch<SkyTrackResponse>(
    `/planner/targets/${dsoId}/sky-track?${qs.toString()}`,
  );
}

export interface AnnualHoursPoint {
  /** Evening date ``YYYY-MM-DD`` — the night's hours span dusk D → dawn D+1. */
  date: string;
  hours: number;
}

export interface MoonDataPoint {
  date: string;
  illumination_pct: number;
  min_separation_deg: number | null;
}

export interface AnnualHoursResponse {
  dso_id: number;
  year: number;
  horizon_id: number;
  horizon_type: "artificial" | "custom";
  horizon_name: string;
  flat_altitude_deg: number | null;
  moon_sep_deg: number;
  points: AnnualHoursPoint[];
  filtered_points: AnnualHoursPoint[];
  moon_data: MoonDataPoint[];
}

export interface AnnualHoursParams {
  year?: number;
  horizonId?: number | null;
  moonSepDeg?: number;
  maxIlluminationPct?: number | null;
  minSeparationDeg?: number | null;
  moonCombine?: "and" | "or";
}

export function fetchAnnualHours(
  dsoId: number,
  locationId: number,
  params: AnnualHoursParams = {},
): Promise<AnnualHoursResponse> {
  const qs = new URLSearchParams({ location_id: String(locationId) });
  if (params.year) qs.set("year", String(params.year));
  if (params.horizonId != null) qs.set("horizon_id", String(params.horizonId));
  if (typeof params.moonSepDeg === "number") qs.set("moon_sep_deg", String(params.moonSepDeg));
  if (params.maxIlluminationPct != null) qs.set("max_illumination_pct", String(params.maxIlluminationPct));
  if (params.minSeparationDeg != null) qs.set("min_separation_deg", String(params.minSeparationDeg));
  if (params.moonCombine) qs.set("moon_combine", params.moonCombine);
  return apiFetch<AnnualHoursResponse>(
    `/planner/targets/${dsoId}/annual-hours?${qs.toString()}`,
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


// ─── Sky-tile cache (v0.18.0 / Pass C) ───────────────────────────────────────

export type SkyTileTier = "narrow" | "med" | "wide";

export interface SkyTileCellLayout {
  nside: number;
  ipix: number;
  tier: SkyTileTier;
  cell_i: number;
  cell_j: number;
  /** Top-left in east-left / north-up screen-coord source pixels. */
  pixel_x: number;
  pixel_y: number;
}

export interface SkyTileGridLayout {
  nside: number;
  ipix: number;
  tangent_ra_deg: number;
  tangent_dec_deg: number;
  tier: SkyTileTier;
  cell_size_deg: number;
  cell_width_px: number;
  cell_height_px: number;
  composite_width_px: number;
  composite_height_px: number;
  view_center_pixel_x: number;
  view_center_pixel_y: number;
  cells: SkyTileCellLayout[];
}

export interface SkyTileGridParams {
  raDeg: number;
  decDeg: number;
  tier?: SkyTileTier;
  fovMajorDeg?: number;
  extentDeg: number;
}

export function fetchSkyTileGrid(params: SkyTileGridParams): Promise<SkyTileGridLayout> {
  const qs = new URLSearchParams({
    ra_deg: params.raDeg.toFixed(6),
    dec_deg: params.decDeg.toFixed(6),
    extent_deg: params.extentDeg.toFixed(6),
  });
  if (params.tier) qs.set("tier", params.tier);
  if (params.fovMajorDeg != null) qs.set("fov_major_deg", params.fovMajorDeg.toFixed(4));
  return apiFetch<SkyTileGridLayout>(`/planner/sky-tile-grid?${qs.toString()}`);
}

export interface SkyTileCellUrlOptions {
  /** Long-poll window in milliseconds. Only honoured on the first
   *  attempt (retries should pass ``0`` to avoid stacked holds). */
  waitMs?: number;
  /** Cache-generation counter from ``useThumbnailCacheStore``. */
  generation?: number;
}

/** Build the ``<img src>`` URL for one cell of the sky-tile cache.
 *
 *  Bypasses ``apiFetch`` (used directly as an image element's ``src``)
 *  so the activity label is folded into the query string — matches the
 *  pattern in ``thumbnailUrl``. */
export function skyTileUrl(
  cell: Pick<SkyTileCellLayout, "nside" | "ipix" | "tier" | "cell_i" | "cell_j">,
  opts: SkyTileCellUrlOptions = {},
  hips: string = "CDS/P/DSS2/color",
): string {
  const q = new URLSearchParams({
    hips,
    nside: String(cell.nside),
    ipix: String(cell.ipix),
    tier: cell.tier,
    cell_i: String(cell.cell_i),
    cell_j: String(cell.cell_j),
  });
  if (opts.generation != null) q.set("_g", String(opts.generation));
  if (opts.waitMs != null && opts.waitMs > 0) q.set("wait_ms", String(opts.waitMs));
  const activity = getActivity();
  if (activity) q.set("_activity", activity);
  return `/api/planner/sky-tile?${q.toString()}`;
}

export const fetchSkyTileCacheStats = () =>
  apiFetch<ThumbnailCacheStats>("/planner/sky-tile/cache/stats");

export const clearSkyTileCache = () =>
  apiFetch<{ deleted_files: number }>("/planner/sky-tile/cache/clear", {
    method: "POST",
  });

export type ThumbnailVariant = "list" | "detail" | "rig_framed";

export interface ThumbnailUrlOptions {
  /** Required for ``rig_framed``; ignored otherwise. */
  fovMajorDeg?: number;
  fovMinorDeg?: number;
  /** Cache-generation counter — appended as ``&_g=N``. Bumps on cache
   *  clear so stale browser-cached entries are never reused. Sourced
   *  from ``useThumbnailCacheStore``. */
  generation?: number;
  /** Long-poll window in milliseconds. On a cache miss the backend
   *  holds the request open up to this long waiting for the CDS fetch
   *  to complete, then serves the real image in the same round trip.
   *  ``0`` (default) restores the old behaviour — immediate placeholder,
   *  client polls with backoff. Backend caps at 10 s. */
  waitMs?: number;
}

/** Build the <img src> URL for a thumbnail — the backend handles cache lookup.
 *
 *  Image requests bypass the apiFetch wrapper, so we fold the current
 *  activity label into the query string directly (matches
 *  ``api/images.ts:imageUrl`` — required for the Activity Console).
 *  ``fovMajorDeg`` / ``fovMinorDeg`` are required for ``rig_framed``;
 *  caller is trusted to pass them. */
export function thumbnailUrl(
  dsoId: number,
  variant: ThumbnailVariant = "list",
  opts: ThumbnailUrlOptions = {},
): string {
  const q = new URLSearchParams({ variant });
  if (opts.fovMajorDeg != null) q.set("fov_major_deg", opts.fovMajorDeg.toFixed(4));
  if (opts.fovMinorDeg != null) q.set("fov_minor_deg", opts.fovMinorDeg.toFixed(4));
  if (opts.generation != null) q.set("_g", String(opts.generation));
  if (opts.waitMs != null && opts.waitMs > 0) q.set("wait_ms", String(opts.waitMs));
  const activity = getActivity();
  if (activity) q.set("_activity", activity);
  return `/api/planner/thumbnails/${dsoId}?${q.toString()}`;
}
