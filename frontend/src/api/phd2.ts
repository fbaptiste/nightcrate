import { apiFetch } from "./client";

// ── Type mirrors of backend Pydantic models ──────────────────────────────────

export type SectionKind = "calibration" | "guiding";
export type MountKind = "Mount" | "AO" | "DROP";
export type CalibrationDirection = "West" | "East" | "Backlash" | "North" | "South";
export type EventKind =
  | "settle_begin"
  | "settle_end"
  | "lock_position_set"
  | "dither"
  | "server_pause"
  | "server_resume"
  | "star_selected"
  | "alert"
  | "guiding_enabled"
  | "guiding_disabled"
  | "info";

export interface SectionHeader {
  camera: string | null;
  mount: string | null;
  ao: string | null;
  focal_length_mm: number | null;
  binning: number | null;
  pixel_scale_arcsec_per_px: number | null;
  exposure_ms: number | null;
  declination_deg: number | null;
  hour_angle_hr: number | null;
  pier_side: string | null;
  rotator_position: string | null;
  lock_position_x_px: number | null;
  lock_position_y_px: number | null;
  star_position_x_px: number | null;
  star_position_y_px: number | null;
  hfd_px: number | null;
  search_region_px: number | null;
  star_mass_tolerance_pct: number | null;
  x_guide_algorithm: string | null;
  y_guide_algorithm: string | null;
  dec_guide_mode: string | null;
  backlash_comp_enabled: boolean | null;
  backlash_pulse_ms: number | null;
  max_ra_duration_ms: number | null;
  max_dec_duration_ms: number | null;
  ra_guide_speed: string | null;
  dec_guide_speed: string | null;
  x_angle_deg: number | null;
  x_rate_px_per_sec: number | null;
  y_angle_deg: number | null;
  y_rate_px_per_sec: number | null;
  parity: string | null;
  calibration_step_ms: number | null;
  assume_orthogonal_axes: boolean | null;
  cal_declination_deg: number | null;
  last_cal_issue: string | null;
  dither_description: string | null;
  dither_scale: number | null;
  image_noise_reduction: string | null;
  equipment_profile: string | null;
  freeform_keys: Record<string, string>;
}

export interface GuidingSample {
  frame: number;
  time_seconds: number;
  mount_kind: MountKind;
  dx_px: number | null;
  dy_px: number | null;
  ra_raw_px: number | null;
  dec_raw_px: number | null;
  ra_guide_px: number | null;
  dec_guide_px: number | null;
  ra_duration_ms: number | null;
  dec_duration_ms: number | null;
  ra_direction: "W" | "E" | null;
  dec_direction: "N" | "S" | null;
  x_step: number | null;
  y_step: number | null;
  star_mass: number | null;
  snr: number | null;
  error_code: number;
  error_description: string | null;
}

export interface CalibrationSample {
  direction: CalibrationDirection;
  step: number;
  dx_px: number;
  dy_px: number;
  x_px: number;
  y_px: number;
  distance_px: number;
}

export interface CalibrationPhase {
  direction: CalibrationDirection;
  samples: CalibrationSample[];
  angle_deg: number | null;
  rate_px_per_sec: number | null;
  parity: string | null;
}

export interface LogEvent {
  time_seconds: number | null;
  kind: EventKind;
  raw_message: string;
  parsed_fields: Record<string, string>;
}

export interface LogSection {
  kind: SectionKind;
  index: number;
  start_time: string; // ISO-ish naive local timestamp
  end_time: string | null;
  header: SectionHeader;
  samples: GuidingSample[];
  calibration_phases: CalibrationPhase[];
  events: LogEvent[];
  locale_recovery_applied: boolean;
}

export interface ParseWarning {
  code: string;
  message: string;
  section_index: number | null;
}

export interface ParsedLog {
  file_path: string;
  phd2_version: string | null;
  log_version: string;
  log_enabled_at: string;
  sections: LogSection[];
  warnings: ParseWarning[];
}

export interface SectionMetrics {
  rms_ra_px: number | null;
  rms_dec_px: number | null;
  rms_total_px: number | null;
  peak_ra_px: number | null;
  peak_dec_px: number | null;
  drift_ra_px_per_min: number | null;
  drift_dec_px_per_min: number | null;
  polar_alignment_error_arcmin: number | null;
  oscillation_ra: number | null;
  oscillation_dec: number | null;
  elongation: number | null;
  frame_count_total: number;
  frame_count_error: number;
  frame_count_in_settle: number;
  frame_count_in_stats: number;
  duration_total_seconds: number;
  duration_included_seconds: number;
  mean_snr: number | null;
  median_snr: number | null;
  mean_star_mass: number | null;
  arcsec_scale: number | null;
}

// Per-section derived data; reserved for future analytics. Empty
// today after the v0.27.0 cleanup but kept as an interface so
// consumer code doesn't have to special-case its absence.
export type SectionAnalysis = Record<string, never>;

export interface SectionWithMetrics {
  section: LogSection;
  metrics: SectionMetrics;
  analysis: SectionAnalysis;
}

export interface ParseResponse {
  log: ParsedLog;
  sections: SectionWithMetrics[];
}

export interface CacheStatsResponse {
  entries: number;
  max_entries: number;
  ttl_seconds: number;
}

// ── Fetcher ──────────────────────────────────────────────────────────────────

export async function parseGuideLog(path: string): Promise<ParseResponse> {
  return apiFetch<ParseResponse>("/phd2/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
}

export async function fetchGuideLogCacheStats(): Promise<CacheStatsResponse> {
  return apiFetch<CacheStatsResponse>("/phd2/cache/stats");
}

export async function clearGuideLogCache(): Promise<{ cleared: number }> {
  return apiFetch<{ cleared: number }>("/phd2/cache/clear", { method: "POST" });
}

// ── Recent files ─────────────────────────────────────────────────────────────

interface RecentFileApi {
  path: string;
  opened_at: string;
}

export interface RecentFile {
  path: string;
  openedAt: string;
}

export async function fetchRecentPhd2Files(): Promise<RecentFile[]> {
  const data = await apiFetch<RecentFileApi[]>("/phd2/recent");
  return data.map((r) => ({ path: r.path, openedAt: r.opened_at }));
}

export async function recordRecentPhd2File(path: string): Promise<void> {
  await apiFetch<unknown>(`/phd2/recent?path=${encodeURIComponent(path)}`, {
    method: "POST",
  });
}

export async function deleteRecentPhd2File(path: string): Promise<void> {
  await apiFetch<unknown>(`/phd2/recent?path=${encodeURIComponent(path)}`, {
    method: "DELETE",
  });
}
