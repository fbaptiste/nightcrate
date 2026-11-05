import { apiFetch } from "./client";

export type PlateSolver = "native" | "astap";

export type SolveStep =
  | "load"
  | "near_index"
  | "near_catalog"
  | "blind_known_scale"
  | "blind_unknown_scale"
  | "astap_near"
  | "astap_blind";

export type AttemptOutcome =
  | "solved"
  | "no_match"
  | "skipped"
  | "step_timeout"
  | "overall_timeout"
  | "cancelled"
  | "ambiguous"
  | "too_few_stars"
  | "error";

export interface SolveAttempt {
  solver: PlateSolver;
  step: SolveStep;
  position_source: "request" | "header" | "none";
  scale_source: "request" | "header" | "none";
  ranges: string[];
  layers: string[];
  outcome: AttemptOutcome | null;
  seconds: number | null;
  detail: string | null;
}

export interface ProgressSnapshot {
  operation_id: string;
  solver: PlateSolver;
  attempts: SolveAttempt[];
  active_step: SolveAttempt | null;
  planned: SolveStep[];
  elapsed_seconds: number;
  state: "running" | "finished";
}

export interface PlateSolveRequest {
  image_path: string;
  hdu?: number;
  operation_id: string;
  ra_hint?: number;
  dec_hint?: number;
  fov_hint?: number;
  scale_hint_arcsec?: number;
  position?: "auto" | "none";
  scale?: "auto" | "none";
  timeout?: number;
  solver?: PlateSolver;
}

export interface PlateSolveResult {
  solved: boolean;
  solver: PlateSolver;
  star_catalog: string | null;
  stars_detected: number | null;
  stars_matched: number | null;
  rms_px: number | null;
  rms_arcsec: number | null;
  log_odds: number | null;
  solve_path: "near_index" | "near_catalog" | "blind" | null;
  scale_stage: string | null;
  failure_reason: string | null;
  ra_deg: number | null;
  dec_deg: number | null;
  ra_hms: string | null;
  dec_dms: string | null;
  pixel_scale_arcsec: number | null;
  rotation_deg: number | null;
  fov_width_arcmin: number | null;
  fov_height_arcmin: number | null;
  image_width: number | null;
  image_height: number | null;
  cd1_1: number | null;
  cd1_2: number | null;
  cd2_1: number | null;
  cd2_2: number | null;
  crpix1: number | null;
  crpix2: number | null;
  error_message: string | null;
  warning: string | null;
  solve_time_seconds: number | null;
  attempts: SolveAttempt[];
}

export function parseApiError(
  err: unknown,
): { message: string; failureReason: string | null; attempts: SolveAttempt[] } {
  const raw = err instanceof Error ? err.message : typeof err === "string" ? err : String(err ?? "");
  const fallback = raw.trim() || "Plate solve failed.";
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || !("detail" in parsed)) {
      return { message: fallback, failureReason: null, attempts: [] };
    }
    const detail = (parsed as { detail: unknown }).detail;
    if (typeof detail === "string") {
      return { message: detail || fallback, failureReason: null, attempts: [] };
    }
    if (typeof detail === "object" && detail !== null) {
      const message = "message" in detail ? (detail as { message: unknown }).message : null;
      const failureReason =
        "failure_reason" in detail
          ? (detail as { failure_reason: unknown }).failure_reason
          : null;
      const attempts = "attempts" in detail ? (detail as { attempts: unknown }).attempts : null;
      return {
        message: typeof message === "string" && message ? message : fallback,
        failureReason: typeof failureReason === "string" ? failureReason : null,
        attempts: Array.isArray(attempts) ? (attempts as SolveAttempt[]) : [],
      };
    }
  } catch {
    // apiFetch also uses plain response text for non-JSON errors.
  }
  if (raw.trimStart().startsWith("<")) {
    return {
      message: "The server returned an unexpected response. Check that NightCrate's backend is running.",
      failureReason: null,
      attempts: [],
    };
  }
  return { message: fallback, failureReason: null, attempts: [] };
}

export interface AstapValidation {
  valid: boolean;
  resolved_path: string | null;
  error: string | null;
}

export function plateSolve(req: PlateSolveRequest): Promise<PlateSolveResult> {
  return apiFetch<PlateSolveResult>("/plate-solve/solve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export function fetchSolveProgress(operationId: string): Promise<ProgressSnapshot> {
  return apiFetch<ProgressSnapshot>(
    `/plate-solve/progress?operation_id=${encodeURIComponent(operationId)}`,
  );
}

export function cancelSolve(operationId: string): Promise<{ cancelled: boolean; pending: boolean }> {
  return apiFetch<{ cancelled: boolean; pending: boolean }>("/plate-solve/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operation_id: operationId }),
  });
}

export function previewUrl(path: string, hdu: number = 0, maxPx: number = 1600): string {
  const qs = new URLSearchParams({ path, hdu: String(hdu), max_px: String(maxPx) });
  return `/api/images/preview?${qs.toString()}`;
}

export function validateAstapPath(path: string): Promise<AstapValidation> {
  return apiFetch<AstapValidation>(
    `/plate-solve/validate-path?path=${encodeURIComponent(path)}`,
    { method: "POST" },
  );
}

// ── Image annotation types ──────────────────────────────────────────

export interface WcsParams {
  crval1: number;
  crval2: number;
  cd1_1: number;
  cd1_2: number;
  cd2_1: number;
  cd2_2: number;
  crpix1: number;
  crpix2: number;
  naxis1: number;
  naxis2: number;
}

export interface AnnotatedDso {
  id: number;
  primary_designation: string;
  obj_type: string;
  type_group: string;
  common_name: string | null;
  other_names: string[];
  constellation: string | null;
  ra_deg: number;
  dec_deg: number;
  pixel_x: number;
  pixel_y: number;
  ellipse_semi_major_px: number | null;
  ellipse_semi_minor_px: number | null;
  ellipse_angle_deg: number | null;
  maj_axis_arcmin: number | null;
  min_axis_arcmin: number | null;
  distance_pc: number | null;
  distance_method: string | null;
  mag_b: number | null;
}

export interface ImageAnnotationResult {
  wcs: WcsParams;
  center_ra_deg: number;
  center_dec_deg: number;
  fov_width_arcmin: number;
  fov_height_arcmin: number;
  pixel_scale_arcsec: number;
  rotation_deg: number;
  dsos: AnnotatedDso[];
}

export function detectWcs(path: string, hdu: number = 0): Promise<WcsParams | null> {
  return apiFetch<WcsParams | null>(
    `/plate-solve/detect-wcs?path=${encodeURIComponent(path)}&hdu=${hdu}`,
  );
}

export function fetchAnnotations(
  path: string,
  hdu: number = 0,
  wcsOverride?: Partial<WcsParams>,
): Promise<ImageAnnotationResult> {
  const qs = new URLSearchParams({ path, hdu: String(hdu) });
  if (wcsOverride) {
    for (const [k, v] of Object.entries(wcsOverride)) {
      if (v != null) qs.set(k, String(v));
    }
  }
  return apiFetch<ImageAnnotationResult>(`/plate-solve/annotate?${qs.toString()}`);
}
